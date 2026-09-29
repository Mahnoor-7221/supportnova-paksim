"""Database seeding.

Creates the complete demo environment: roles and demo users, departments,
categories, the rule matrix, the bundled knowledge base (documents processed
through the traceable chunking pipeline plus their policy entries), versioned
prompts and the synthetic dataset (5,000 complaints with ground-truth cases).

Every sub-seed is idempotent: re-running the application does not duplicate
data. The optional demo pipeline run executes Pipeline 1 + Pipeline 2 on a
sample of dataset complaints (plus a small unseen-case primer for the
comparison report) so dashboards, queues and reports are populated on first
start (offline provider only — the real GenAI provider is never called at
startup).
"""
from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from .audit import log_action
from .config import DATASET_DIR, settings
from .models import (
    Complaint,
    ComplaintCategory,
    ComplaintHistory,
    ComplaintRule,
    DatasetCase,
    Department,
    Document,
    DocumentChunk,
    DocumentVersion,
    Policy,
    Role,
    User,
    ValidationResult,
)
from .python_validation import run_validation
from .security import hash_password
from .services import injection_guard
from .services.analysis_service import analyze_complaint
from .services.dataset_generator import generate_dataset
from .services.document_processor import process_file
from .services.prompt_manager import get_prompt_manager
from .services.rule_seed import CATEGORIES_SEED, DEPARTMENTS_SEED, RULE_SEED
from .services.rule_matcher import expected_from_rule, match_rule
from .utils import utcnow

logger = logging.getLogger("supportnova.seed")

KB_DIR = DATASET_DIR / "knowledge_base"
DUPLICATE_SUFFIX = " I already wrote about this - please do not ignore it again."

DEMO_USERS = [
    {"email": "admin@supportnova.demo", "full_name": "Nova Admin",
     "role": "admin", "password": "Admin#12345"},
    {"email": "agent@supportnova.demo", "full_name": "Alex Agent",
     "role": "agent", "password": "Agent#12345"},
    {"email": "customer@supportnova.demo", "full_name": "Casey Customer",
     "role": "customer", "password": "Customer#12345"},
    {"email": "reviewer@supportnova.demo", "full_name": "Riley Reviewer",
     "role": "reviewer", "password": "Reviewer#12345"},
    {"email": "manager@supportnova.demo", "full_name": "Morgan Manager",
     "role": "manager", "password": "Manager#12345"},
]


# ---------------------------------------------------------------------------
# Roles, users, organisation
# ---------------------------------------------------------------------------

def _seed_roles(db: Session) -> dict[str, Role]:
    roles: dict[str, Role] = {}
    for name in ("admin", "agent", "reviewer", "manager", "customer"):
        role = db.query(Role).filter(Role.name == name).first()
        if role is None:
            role = Role(name=name, description=f"{name.title()} role")
            db.add(role)
            db.flush()
        roles[name] = role
    db.commit()
    return roles


def _seed_users(db: Session, roles: dict[str, Role]) -> dict[str, User]:
    users: dict[str, User] = {}
    for spec in DEMO_USERS:
        user = db.query(User).filter(User.email == spec["email"]).first()
        if user is None:
            user = User(
                email=spec["email"],
                full_name=spec["full_name"],
                password_hash=hash_password(spec["password"]),
                role_id=roles[spec["role"]].id,
                is_active=True,
            )
            db.add(user)
            db.flush()
        users[spec["role"]] = user
    db.commit()
    return users


def _seed_departments(db: Session) -> int:
    created = 0
    for spec in DEPARTMENTS_SEED:
        if db.query(Department).filter(Department.name == spec["name"]).first():
            continue
        db.add(Department(
            name=spec["name"],
            description=spec.get("description", ""),
            is_escalation_target=bool(spec.get("is_escalation_target")),
        ))
        created += 1
    db.commit()
    return created


def _seed_categories(db: Session) -> int:
    created = 0
    for spec in CATEGORIES_SEED:
        if db.query(ComplaintCategory).filter(ComplaintCategory.name == spec["name"]).first():
            continue
        department = db.query(Department).filter(Department.name == spec["department"]).first()
        db.add(ComplaintCategory(
            name=spec["name"],
            description=spec.get("description", ""),
            default_department_id=department.id if department else None,
            sla_hours=int(spec.get("sla_hours", 72)),
            keywords=spec.get("keywords", []),
        ))
        created += 1
    db.commit()
    return created


def _seed_rules(db: Session) -> int:
    created = 0
    for spec in RULE_SEED:
        if db.query(ComplaintRule).filter(ComplaintRule.rule_id == spec["rule_id"]).first():
            continue
        db.add(ComplaintRule(
            rule_id=spec["rule_id"],
            category=spec["category"],
            subcategory=spec["subcategory"],
            conditions=spec.get("conditions", {}),
            keywords=spec.get("keywords", []),
            department=spec["department"],
            urgency=spec["urgency"],
            priority=spec["priority"],
            policy_id=spec.get("policy_id", ""),
            escalation=bool(spec.get("escalation")),
            escalation_reason=spec.get("escalation_reason", ""),
            escalation_department=spec.get("escalation_department", ""),
            required_actions=spec.get("required_actions", []),
            prohibited_actions=spec.get("prohibited_actions", []),
            follow_up=bool(spec.get("follow_up", True)),
            response_template=spec.get("response_template", ""),
            is_active=True,
        ))
        created += 1
    db.commit()
    return created


# ---------------------------------------------------------------------------
# Knowledge base
# ---------------------------------------------------------------------------

def _seed_knowledge_base(db: Session, admin_id: Optional[int]) -> dict:
    manifest_path = KB_DIR / "manifest.json"
    if not manifest_path.exists():
        logger.warning("Knowledge-base manifest not found at %s; continuing without bundled KB.", manifest_path)
        return {"documents": 0, "chunks": 0, "policies": 0, "skipped": True}
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    documents = chunks = policies = 0
    for entry in manifest.get("documents", []):
        if db.query(Document).filter(Document.code == entry["code"]).first():
            continue

        file_path = KB_DIR / entry["file"]
        processed = process_file(file_path, "md")
        scan = injection_guard.scan_document(
            "\n".join(chunk["text"] for chunk in processed["chunks"])
        )
        quarantined = bool(scan["suspected"] and scan.get("critical"))

        source_reference = f"supportnova/kb/{entry['file']}"
        document = Document(
            code=entry["code"],
            title=entry["title"],
            doc_type=entry.get("doc_type", "policy"),
            category=entry.get("category", ""),
            source_reference=source_reference,
            status="flagged" if quarantined else "active",
            current_version="v1",
            injection_flag=quarantined,
            injection_notes=", ".join(scan.get("matches", [])) if quarantined else "",
            uploaded_by=admin_id,
        )
        db.add(document)
        db.flush()

        version = DocumentVersion(
            document_id=document.id,
            version="v1",
            effective_date=utcnow(),
            file_name=entry["file"],
            stored_path=str(file_path),
            extension="md",
            size_bytes=file_path.stat().st_size,
            checksum=processed["checksum"],
            page_count=processed["page_count"],
            is_current=True,
            uploaded_by=admin_id,
        )
        db.add(version)
        db.flush()

        for chunk_data in processed["chunks"]:
            db.add(DocumentChunk(
                document_id=document.id,
                version_id=version.id,
                section_id=chunk_data["section_id"],
                section_title=chunk_data.get("section_title", ""),
                page=chunk_data.get("page", 1),
                chunk_index=chunk_data.get("chunk_index", 0),
                source_reference=source_reference,
                text=chunk_data["text"],
                injection_suspected=bool(scan["suspected"]),
                trust_level="untrusted" if quarantined else "approved",
            ))
            chunks += 1

        if entry.get("policy_id"):
            db.add(Policy(
                policy_id=entry["policy_id"],
                title=entry.get("policy_title") or entry["title"],
                document_id=document.id,
                version="v1",
                section="",
                summary=entry.get("summary", ""),
                is_active=True,
            ))
            policies += 1

        documents += 1

    db.commit()
    return {"documents": documents, "chunks": chunks, "policies": policies}


# ---------------------------------------------------------------------------
# Dataset (complaints + ground-truth cases)
# ---------------------------------------------------------------------------

def _check_injection(title: str, description: str) -> bool:
    return bool(injection_guard.scan_text(f"{title}\n{description}")["suspected"])


def _seed_dataset(db: Session, customer_id: Optional[int], admin_id: Optional[int]) -> dict:
    if db.query(DatasetCase).count() > 0:
        return {"cases": 0, "skipped": True}

    dataset = generate_dataset(
        total=settings.seed_complaint_count,
        unseen=settings.seed_unseen_count,
    )

    sla_by_category = {
        category.name: category.sla_hours
        for category in db.query(ComplaintCategory).all()
    }

    description_to_complaint: dict[str, Complaint] = {}
    ground_truth_rules = db.query(ComplaintRule).filter(ComplaintRule.is_active.is_(True)).all()
    duplicates_linked = 0
    created = 0

    for case in dataset["cases"]:
        data = case["complaint"]
        complaint = Complaint(
            code="TMP",
            title=data["title"],
            description=data["description"],
            customer_type=data["customer_type"],
            product_or_service=data["product_or_service"],
            order_reference=data["order_reference"],
            channel=data["channel"],
            complaint_date=utcnow() - timedelta(days=int(data.get("age_days") or 0)),
            requested_resolution=data["requested_resolution"],
            previous_complaints=int(data.get("previous_complaints") or 0),
            customer_id=customer_id,
            created_by=customer_id or admin_id,
            status="NEW",
            is_dataset_case=True,
        )
        db.add(complaint)
        db.flush()
        complaint.code = f"CMP-{complaint.id:05d}"

        flags = list(case.get("flags") or [])
        complaint.flags = flags
        complaint.injection_detected = _check_injection(data["title"], data["description"])

        missing = [
            field for field in ("order_reference", "product_or_service", "complaint_date")
            if not getattr(complaint, field, None)
        ]
        complaint.missing_fields = missing
        complaint.incomplete = bool(missing)

        sla_hours = sla_by_category.get(case["expected"].get("category", ""), 72)
        complaint.sla_due_at = complaint.complaint_date + timedelta(hours=sla_hours)

        # link duplicates to their source complaint (never auto-merge)
        if "duplicate" in flags:
            base_description = data["description"].replace(DUPLICATE_SUFFIX, "")
            source = description_to_complaint.get(base_description)
            if source is not None:
                complaint.duplicate_of_id = source.id
                complaint.duplicate_similarity = 0.92
                duplicates_linked += 1
        elif not flags:
            description_to_complaint[data["description"]] = complaint

        # Ground truth must come from the deterministic rule matcher that
        # Pipeline 2 uses, not from a separately guessed generator label.
        # This keeps unseen evaluation valid: GenAI is compared against the
        # same rule-matrix decision used by the independent validator.
        matched_rule, _rule_score, _ranked = match_rule(db, complaint, rules=ground_truth_rules)
        expected = expected_from_rule(matched_rule)

        db.add(DatasetCase(
            complaint_id=complaint.id,
            case_code=case["case_code"],
            expected=expected,
            flags=flags,
            split=case.get("split", "train"),
        ))
        db.add(ComplaintHistory(
            complaint_id=complaint.id,
            from_status="",
            to_status="NEW",
            note="Dataset complaint registered",
            actor_id=customer_id or admin_id,
        ))
        created += 1

    db.commit()
    return {"cases": created, "duplicates_linked": duplicates_linked, "skipped": False}


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def _seed_telecom(db: Session, users: dict) -> dict:
    """Packages, customer profile, SIMs, orders, notifications — idempotent."""
    from .models import (
        AppNotification,
        CustomerProfile,
        CustomerSubscription,
        DeviceLocation,
        SimCard,
        TelecomOrder,
        TelecomPackage,
    )

    packages_spec = [
        ("PKG-DAILY-1GB", "Daily 1GB", "Internet", 50, 1, 1024, 0, 0),
        ("PKG-WEEK-5GB", "Weekly 5GB", "Internet", 250, 7, 5120, 0, 0),
        ("PKG-MONTH-15GB", "Monthly 15GB Super", "Hybrid", 800, 30, 15360, 500, 500),
        ("PKG-CALL-500", "500 Minutes", "Calls", 300, 30, 0, 500, 0),
        ("PKG-SMS-1000", "1000 SMS Bundle", "SMS", 100, 30, 0, 0, 1000),
        ("PKG-HYBRID-PRO", "Hybrid Pro 20GB", "Hybrid", 1200, 30, 20480, 1000, 1000),
        ("PKG-DAILY-UNL", "Daily Unlimited Social", "Daily", 80, 1, 2048, 50, 50),
        ("PKG-WEEK-CALL", "Weekly Talk", "Weekly", 200, 7, 0, 300, 100),
    ]
    created_pkg = 0
    pkg_ids = {}
    for code, name, cat, price, days, data, mins, sms in packages_spec:
        row = db.query(TelecomPackage).filter(TelecomPackage.code == code).first()
        if row is None:
            row = TelecomPackage(
                code=code, name=name, description=f"{name} — PakSim official package",
                category=cat, price=price, validity_days=days,
                internet_data_mb=data, call_minutes=mins, sms_count=sms, status="ACTIVE",
            )
            db.add(row)
            db.flush()
            created_pkg += 1
        pkg_ids[code] = row.id
    db.commit()

    customer = users.get("customer")
    if customer is None:
        return {"packages": created_pkg, "sims": 0}

    profile = db.query(CustomerProfile).filter(CustomerProfile.user_id == customer.id).first()
    if profile is None:
        profile = CustomerProfile(
            user_id=customer.id,
            phone_number="03001234567",
            cnic="42101-1234567-1",
            address="Gulshan-e-Iqbal, Karachi",
            date_of_birth="1995-05-15",
            verification_status="VERIFIED",
            last_login=utcnow(),
        )
        db.add(profile)
        db.flush()

    sims_created = 0
    if db.query(SimCard).filter(SimCard.customer_id == customer.id).count() == 0:
        hybrid = pkg_ids.get("PKG-MONTH-15GB")
        s1 = SimCard(
            sim_number="8992200000000000001",
            phone_number="03001234567",
            customer_id=customer.id,
            sim_type="Prepaid",
            network="4G",
            status="ACTIVE",
            activation_date=utcnow() - timedelta(days=40),
            registration_date=utcnow() - timedelta(days=40),
            current_package_id=hybrid,
        )
        s2 = SimCard(
            sim_number="8992200000000000002",
            phone_number="03009876543",
            customer_id=customer.id,
            sim_type="Prepaid",
            network="5G",
            status="ACTIVE",
            activation_date=utcnow() - timedelta(days=10),
            registration_date=utcnow() - timedelta(days=10),
            current_package_id=pkg_ids.get("PKG-WEEK-5GB"),
        )
        db.add_all([s1, s2])
        db.flush()
        sims_created = 2
        for sim, lat, lon in ((s1, 24.8607, 67.0011), (s2, 24.9056, 67.0822)):
            db.add(DeviceLocation(
                sim_id=sim.id, latitude=lat, longitude=lon, accuracy_m=45.0,
                source="SIMULATED_DEMO_LOCATION", location_status="Available",
            ))
        db.add(CustomerSubscription(
            customer_id=customer.id, sim_id=s1.id, package_id=hybrid or list(pkg_ids.values())[0],
            status="ACTIVE", start_date=utcnow() - timedelta(days=5),
            end_date=utcnow() + timedelta(days=25),
        ))
        o1 = TelecomOrder(
            order_code="TMP", customer_id=customer.id, order_type="SIM", product_id=s1.id,
            product_label="Prepaid SIM 03001234567", sim_id=s1.id, amount=500,
            payment_status="PAID", order_status="COMPLETED", completed_at=utcnow() - timedelta(days=40),
        )
        db.add(o1)
        db.flush()
        o1.order_code = f"ORD-{o1.id:05d}"
        o2 = TelecomOrder(
            order_code="TMP", customer_id=customer.id, order_type="PACKAGE",
            product_id=hybrid, product_label="Monthly 15GB Super", sim_id=s1.id, amount=800,
            payment_status="PAID", order_status="COMPLETED", completed_at=utcnow() - timedelta(days=5),
        )
        db.add(o2)
        db.flush()
        o2.order_code = f"ORD-{o2.id:05d}"
        for title, body, cat in [
            ("Welcome to PakSim", "Your account is verified. Explore SIMs and packages.", "account"),
            ("SIM activated", "03001234567 is active on your account.", "sim"),
            ("Package activated", "Monthly 15GB Super is running on your primary SIM.", "package"),
        ]:
            db.add(AppNotification(user_id=customer.id, title=title, body=body, category=cat, is_read=False))
    db.commit()
    return {"packages": len(pkg_ids), "packages_created": created_pkg, "sims": sims_created}


def seed_database(db: Session) -> dict:
    """Seed everything. Safe to call on every startup (idempotent)."""
    roles = _seed_roles(db)
    users = _seed_users(db, roles)
    departments = _seed_departments(db)
    categories = _seed_categories(db)
    rules = _seed_rules(db)
    kb = _seed_knowledge_base(db, users["admin"].id)

    prompt_manager = get_prompt_manager()
    active_prompts = prompt_manager.sync_db(db)

    dataset = _seed_dataset(db, users["customer"].id, users["admin"].id)
    telecom = _seed_telecom(db, users)

    summary = {
        "users": len(users),
        "departments": departments,
        "categories": categories,
        "rules": rules,
        "knowledge_base": kb,
        "prompts": len(active_prompts),
        "dataset": dataset,
        "telecom": telecom,
    }
    logger.info("Seed complete: %s", summary)
    return summary


def _log_pipeline_run(db: Session, complaint: Complaint, result: ValidationResult) -> None:
    """Startup pipeline runs are real events and belong in the audit trail."""
    log_action(db, "complaint.analyzed", "complaint", complaint.code,
               {"provider": "offline-baseline", "pipeline": "startup-demo"})
    log_action(db, "complaint.validated", "complaint", complaint.code,
               {"status": result.status, "pipeline": "startup-demo"})


def run_demo_pipeline(db: Session, limit: int, actor_id: Optional[int] = None) -> dict:
    """Run Pipeline 1 + Pipeline 2 on a spread sample of dataset complaints.

    Intended for the offline provider only: it populates dashboards, the
    manual review queue and the audit trail with realistic, validation-checked
    results on first start without consuming any GenAI quota. A small slice of
    unseen cases is also primed (always leaving >= 100 reserved for the
    explicit comparison run) so the Reports comparison table is never empty.
    """
    if limit <= 0:
        return {"processed": 0, "skipped": True}

    unseen_cases = (
        db.query(DatasetCase).filter(DatasetCase.split == "unseen").order_by(DatasetCase.id).all()
    )
    unseen_ids = {case.complaint_id for case in unseen_cases}
    candidates = [
        complaint
        for complaint in db.query(Complaint).filter(Complaint.status == "NEW").order_by(Complaint.id).all()
        if complaint.id not in unseen_ids and complaint.is_dataset_case
    ]

    step = max(1, len(candidates) // limit) if candidates else 1
    selected = candidates[::step][:limit]

    processed = 0
    statuses: dict[str, int] = {}
    errors = 0
    for complaint in selected:
        try:
            analysis, _context = analyze_complaint(db, complaint, actor_id)
            result = run_validation(db, complaint, analysis, actor_id)
        except Exception as exc:  # never let demo seeding break startup
            errors += 1
            logger.warning("Demo pipeline failed for %s: %s", complaint.code, exc)
            db.rollback()
            continue
        statuses[result.status] = statuses.get(result.status, 0) + 1
        processed += 1
        _log_pipeline_run(db, complaint, result)

    # Prepare the SRS unseen-comparison evidence automatically on offline/demo
    # startup. The target is configurable and capped by the available unseen
    # dataset. This remains idempotent because already validated cases are skipped.
    unprocessed: list[Complaint] = []
    for case in unseen_cases:
        complaint = db.get(Complaint, case.complaint_id)
        if complaint is None or complaint.status != "NEW":
            continue
        if db.query(ValidationResult).filter(ValidationResult.complaint_id == complaint.id).first():
            continue
        unprocessed.append(complaint)

    unseen_primed = 0
    prime_target = max(0, int(settings.demo_unseen_evaluation_limit))
    already_compared = len(unseen_cases) - len(unprocessed)
    prime_budget = min(prime_target - already_compared, len(unprocessed))
    for complaint in unprocessed[:prime_budget]:
        try:
            analysis, _context = analyze_complaint(db, complaint, actor_id)
            result = run_validation(db, complaint, analysis, actor_id)
        except Exception as exc:  # never let demo seeding break startup
            errors += 1
            logger.warning("Unseen priming failed for %s: %s", complaint.code, exc)
            db.rollback()
            continue
        statuses[result.status] = statuses.get(result.status, 0) + 1
        processed += 1
        unseen_primed += 1
        _log_pipeline_run(db, complaint, result)

    summary = {
        "processed": processed,
        "unseen_primed": unseen_primed,
        "statuses": statuses,
        "errors": errors,
        "skipped": False,
    }
    logger.info("Demo pipeline: %s", summary)
    return summary
