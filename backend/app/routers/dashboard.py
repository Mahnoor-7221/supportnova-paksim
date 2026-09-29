"""Dashboard and analytics aggregation endpoints."""
from __future__ import annotations

from collections import Counter
from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    Complaint,
    ComplaintRule,
    DatasetCase,
    Department,
    Escalation,
    ManualReview,
    SecurityEvent,
    TrustAssessment,
    User,
)
from ..security import require_roles, require_staff
from ..serializers import complaint_brief, escalation_dict
from ..services.genai_client import provider_status
from ..utils import utcnow

router = APIRouter(prefix="/api", tags=["dashboard"])
dashboard_access = require_roles("admin", "agent", "manager")

RESOLVED_STATES = {"RESOLVED", "CLOSED"}
MISMATCH_STATES = {"MISMATCH", "VALIDATION_FAILED"}


def _effective(complaint: Complaint, field: str) -> str:
    """Verified (Python) value when present, otherwise the GenAI value."""
    verified = getattr(complaint, f"verified_{field}", "") or ""
    if verified:
        return verified
    return getattr(complaint, field, "") or "Unknown"


def _distribution(complaints: list[Complaint], field: str) -> list[dict]:
    counter = Counter(_effective(c, field) for c in complaints)
    return [{"name": name, "value": value} for name, value in counter.most_common()]


def _trend(complaints: list[Complaint], days: int = 14) -> list[dict]:
    today = utcnow().date()
    start = today - timedelta(days=days - 1)
    buckets = Counter()
    for complaint in complaints:
        if complaint.created_at and complaint.created_at.date() >= start:
            buckets[complaint.created_at.date().isoformat()] += 1
    return [
        {"date": (start + timedelta(days=offset)).isoformat(),
         "count": buckets.get((start + timedelta(days=offset)).isoformat(), 0)}
        for offset in range(days)
    ]


def _escalation_trend(db: Session, days: int = 14) -> list[dict]:
    today = utcnow().date()
    start = today - timedelta(days=days - 1)
    escalations = db.query(Escalation).all()
    buckets = Counter()
    for escalation in escalations:
        if escalation.created_at and escalation.created_at.date() >= start:
            buckets[escalation.created_at.date().isoformat()] += 1
    return [
        {"date": (start + timedelta(days=offset)).isoformat(),
         "count": buckets.get((start + timedelta(days=offset)).isoformat(), 0)}
        for offset in range(days)
    ]


def _totals(complaints: list[Complaint], db: Session) -> dict:
    now = utcnow()
    open_complaints = [c for c in complaints if c.status not in RESOLVED_STATES]
    sla_risk = [
        c for c in open_complaints
        if c.sla_due_at is not None and c.sla_due_at < now
    ]
    return {
        "total": len(complaints),
        "new": sum(1 for c in complaints if c.status == "NEW"),
        "analyzed": sum(1 for c in complaints if c.status == "ANALYZED"),
        "high_priority": sum(1 for c in complaints if (c.verified_priority or c.priority) in {"P1", "P2"}),
        "escalated": sum(1 for c in complaints if c.status == "ESCALATED"),
        "manual_review": db.query(ManualReview).filter(ManualReview.status == "OPEN").count(),
        "resolved": sum(1 for c in complaints if c.status in RESOLVED_STATES),
        "sla_risk": len(sla_risk),
        "mismatches": sum(1 for c in complaints if c.verification_status in MISMATCH_STATES),
        "validation_failed": sum(1 for c in complaints if c.status == "VALIDATION_FAILED"),
        "manual_review_required": sum(1 for c in complaints if c.verification_status == "MANUAL_REVIEW_REQUIRED"),
        "verified": sum(1 for c in complaints if c.verification_status == "VERIFIED"),
        "verified_with_warning": sum(1 for c in complaints if c.verification_status == "VERIFIED_WITH_WARNING"),
        "injections": sum(1 for c in complaints if c.injection_detected),
        "duplicates": sum(1 for c in complaints if c.duplicate_of_id is not None),
        "repeat_complaints": sum(1 for c in complaints if (c.previous_complaints or 0) > 0 or c.duplicate_of_id),
        "incomplete": sum(1 for c in complaints if c.incomplete),
        "unverified": sum(1 for c in complaints if not c.verification_status),
        "unassigned": sum(1 for c in open_complaints if c.assigned_agent_id is None),
        "in_progress": sum(1 for c in complaints if c.status == "IN_PROGRESS"),
        "open": len(open_complaints),
    }


def _trust_block(db: Session) -> dict:
    """Trust Gate verdicts (computed by trust_engine, never hardcoded here)."""
    assessments = db.query(TrustAssessment).all()
    decisions = Counter(row.decision for row in assessments)
    scores = [row.score for row in assessments if row.score is not None]
    return {
        "assessed": len(assessments),
        "verified": decisions.get("VERIFIED", 0),
        "review_required": decisions.get("REVIEW_REQUIRED", 0),
        "blocked": decisions.get("BLOCKED", 0),
        "average_score": round(sum(scores) / len(scores)) if scores else None,
    }


def _risk_block(db: Session, complaints: list[Complaint]) -> dict:
    """Complaint Risk Radar — every number comes from real records."""
    now = utcnow()
    open_complaints = [c for c in complaints if c.status not in RESOLVED_STATES]
    assessments = db.query(TrustAssessment).all()

    def failed_count(check_names: set[str]) -> int:
        return sum(
            1
            for assessment in assessments
            if any(
                (failed.get("check_name") in check_names)
                for failed in (assessment.failed_checks or [])
            )
        )

    return {
        "levels": {
            "critical": sum(
                1 for c in open_complaints
                if (c.verified_priority or c.priority) == "P1"
                or (c.verified_urgency or c.urgency) == "Critical"
            ),
            "high": sum(1 for c in open_complaints if (c.verified_priority or c.priority) == "P2"),
            "medium": sum(1 for c in open_complaints if (c.verified_priority or c.priority) == "P3"),
            "low": sum(1 for c in open_complaints if (c.verified_priority or c.priority) == "P4"),
        },
        "ai_risks": {
            "hallucination": failed_count({"hallucination"}),
            "policy_mismatch": failed_count(
                {"policy", "policy_section", "policy_applicability", "policy_version"}
            ),
            "injection": sum(1 for c in complaints if c.injection_detected),
            "escalation_gap": failed_count({"escalation", "escalation_reason"}),
        },
        "critical_open_escalations": (
            db.query(Escalation)
            .filter(Escalation.status != "RESOLVED", Escalation.priority == "P1")
            .count()
        ),
        "sla_risk_open": len(
            [c for c in open_complaints if c.sla_due_at is not None and c.sla_due_at < now]
        ),
        "open_security_events": db.query(SecurityEvent).count(),
        "critical_security_events": (
            db.query(SecurityEvent).filter(SecurityEvent.severity == "critical").count()
        ),
    }


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(dashboard_access)):
    complaints = db.query(Complaint).all()

    policy_counter: Counter = Counter()
    rules = {rule.rule_id: rule for rule in db.query(ComplaintRule).all()}
    for complaint in complaints:
        if complaint.matched_rule_id and complaint.matched_rule_id in rules:
            policy_id = rules[complaint.matched_rule_id].policy_id
            if policy_id:
                policy_counter[policy_id] += 1

    recent = (
        db.query(Complaint)
        .filter(Complaint.is_dataset_case.is_(False))
        .order_by(Complaint.id.desc())
        .limit(8)
        .all()
    )
    if len(recent) < 8:
        extra = db.query(Complaint).order_by(Complaint.id.desc()).limit(8).all()
        seen = {c.id for c in recent}
        for complaint in extra:
            if complaint.id not in seen and len(recent) < 8:
                recent.append(complaint)

    recent_escalations = db.query(Escalation).order_by(Escalation.id.desc()).limit(8).all()
    department_workload = []
    department_names = {d.name for d in db.query(Department).all()}
    for name in sorted(department_names):
        rows = [c for c in complaints if (c.verified_department or c.department) == name]
        open_rows = [c for c in rows if c.status not in RESOLVED_STATES]
        department_workload.append({
            "name": name, "total": len(rows), "open": len(open_rows),
            "assigned": sum(1 for c in open_rows if c.assigned_agent_id),
            "unassigned": sum(1 for c in open_rows if not c.assigned_agent_id),
            "escalated": sum(1 for c in rows if c.status == "ESCALATED"),
            "sla_risk": sum(1 for c in open_rows if c.sla_due_at and c.sla_due_at < utcnow()),
        })

    return {
        "totals": _totals(complaints, db),
        "trust": _trust_block(db),
        "risk": _risk_block(db, complaints),
        "charts": {
            "category": _distribution(complaints, "category"),
            "priority": _distribution(complaints, "priority"),
            "urgency": _distribution(complaints, "urgency"),
            "sentiment": _distribution(complaints, "sentiment"),
            "department": _distribution(complaints, "department"),
            "verification": [
                {"name": name, "value": value}
                for name, value in Counter(
                    c.verification_status or "NOT_VALIDATED" for c in complaints
                ).most_common()
            ],
            "status": [
                {"name": name, "value": value}
                for name, value in Counter(c.status for c in complaints).most_common()
            ],
            "policy_usage": [
                {"name": name, "value": value} for name, value in policy_counter.most_common(10)
            ],
            "complaints_trend": _trend(complaints),
            "escalation_trend": _escalation_trend(db),
        },
        "recent_complaints": [complaint_brief(c) for c in recent],
        "department_workload": department_workload,
        "recent_escalations": [escalation_dict(e) for e in recent_escalations],
        "provider": provider_status(),
    }


@router.get("/analytics")
def analytics(db: Session = Depends(get_db), user: User = Depends(dashboard_access)):
    complaints = db.query(Complaint).all()
    now = utcnow()

    # mismatch rate per verified category
    per_category: dict[str, dict] = {}
    for complaint in complaints:
        if not complaint.verification_status:
            continue
        category = complaint.verified_category or complaint.issue_category or "Unknown"
        bucket = per_category.setdefault(category, {"category": category, "total": 0, "mismatched": 0,
                                                    "warning": 0, "manual_review": 0, "verified": 0})
        bucket["total"] += 1
        if complaint.verification_status in MISMATCH_STATES:
            bucket["mismatched"] += 1
        elif complaint.verification_status == "MANUAL_REVIEW_REQUIRED":
            bucket["manual_review"] += 1
        elif complaint.verification_status == "VERIFIED_WITH_WARNING":
            bucket["warning"] += 1
        elif complaint.verification_status == "VERIFIED":
            bucket["verified"] += 1
    mismatch_by_category = sorted(per_category.values(), key=lambda b: b["total"], reverse=True)
    for bucket in mismatch_by_category:
        bucket["rate"] = round((bucket["mismatched"] + bucket["manual_review"]) / max(bucket["total"], 1), 3)

    sla_risk = [
        complaint_brief(c) for c in complaints
        if c.status not in RESOLVED_STATES and c.sla_due_at is not None and c.sla_due_at < now
    ][:50]

    review_sources = Counter(r.source for r in db.query(ManualReview).all())
    review_status = Counter(r.status for r in db.query(ManualReview).all())
    escalation_triggers: Counter = Counter()
    for escalation in db.query(Escalation).all():
        for trigger in escalation.triggers or []:
            escalation_triggers[trigger] += 1
    escalation_status = Counter(e.status for e in db.query(Escalation).all())

    dataset_total = db.query(DatasetCase).count()
    dataset_unseen = db.query(DatasetCase).filter(DatasetCase.split == "unseen").count()

    policy_counter: Counter = Counter()
    rules = {rule.rule_id: rule for rule in db.query(ComplaintRule).all()}
    for complaint in complaints:
        if complaint.matched_rule_id and complaint.matched_rule_id in rules:
            policy_id = rules[complaint.matched_rule_id].policy_id
            if policy_id:
                policy_counter[policy_id] += 1

    return {
        "totals": _totals(complaints, db),
        "charts": {
            "category": _distribution(complaints, "category"),
            "priority": _distribution(complaints, "priority"),
            "urgency": _distribution(complaints, "urgency"),
            "sentiment": _distribution(complaints, "sentiment"),
            "department": _distribution(complaints, "department"),
            "verification": [
                {"name": name, "value": value}
                for name, value in Counter(
                    c.verification_status or "NOT_VALIDATED" for c in complaints
                ).most_common()
            ],
            "escalation_trend": _escalation_trend(db, days=30),
            "complaints_trend": _trend(complaints, days=30),
        },
        "mismatch_by_category": mismatch_by_category,
        "sla_risk": sla_risk,
        "manual_review_sources": [{"name": k, "value": v} for k, v in review_sources.most_common()],
        "manual_review_status": [{"name": k, "value": v} for k, v in review_status.most_common()],
        "escalation_triggers": [{"name": k, "value": v} for k, v in escalation_triggers.most_common()],
        "escalation_status": [{"name": k, "value": v} for k, v in escalation_status.most_common()],
        "policy_usage": [{"name": k, "value": v} for k, v in policy_counter.most_common(10)],
        "dataset": {"total": dataset_total, "unseen": dataset_unseen, "train": dataset_total - dataset_unseen},
        "provider": provider_status(),
    }
