"""Root Cause Engine (Phase 9) + CAPA Recommendation Engine (Phase 10).

Root causes are inferred from *recurring patterns* in the same category (never
claimed with certainty when the sample is small). CAPA records always start
as ``PROPOSED`` — nothing here creates an official CAPA record without a human
approval (``approve_capa`` / ``reject_capa``).
"""
from __future__ import annotations

from collections import Counter
from datetime import timedelta
from typing import Optional

from sqlalchemy.orm import Session

from ..models import Complaint, ComplaintRule, User
from ..models_nova import CapaRecord
from ..utils import utcnow

# Ishikawa-style categories for the delivery/product/service domain this system covers.
ISHIKAWA_CATEGORIES = ["Process", "People", "Systems/Technology", "Suppliers/Logistics", "Policy", "Materials/Product"]

_CAUSE_MAP: dict[str, list[tuple[str, str, str]]] = {
    "Delivery": [
        ("Dispatch/carrier delay", "Suppliers/Logistics", "recurring delay language in this category"),
        ("Inventory or stock mismatch", "Process", "co-occurring stock/availability mentions"),
        ("Address or routing error", "Systems/Technology", "co-occurring wrong-address mentions"),
    ],
    "Product": [
        ("Manufacturing/quality defect", "Materials/Product", "recurring defect/damage language"),
        ("Inadequate QA before dispatch", "Process", "recurring 'out of the box' failures"),
    ],
    "Refund": [
        ("Refund processing delay", "Process", "recurring 'waiting for refund' language"),
        ("Payment gateway reconciliation gap", "Systems/Technology", "co-occurring payment-system mentions"),
    ],
    "Billing": [
        ("Pricing/invoice calculation error", "Systems/Technology", "recurring overcharge language"),
        ("Promotion/discount misconfiguration", "Process", "co-occurring promo mentions"),
    ],
    "Warranty": [
        ("Warranty terms unclear to frontline staff", "People", "recurring 'coverage refused' language"),
        ("Repair/replacement partner SLA gap", "Suppliers/Logistics", "co-occurring partner delay mentions"),
    ],
    "Service": [
        ("Agent training gap", "People", "recurring service-quality language"),
        ("Understaffed support during peak volume", "Process", "recurring 'no response' language"),
    ],
    "Account": [
        ("Authentication/recovery flow failure", "Systems/Technology", "recurring login/reset language"),
    ],
    "Safety": [
        ("Product safety defect", "Materials/Product", "recurring hazard language — highest priority"),
    ],
}


def root_cause_candidates(db: Session, complaint: Complaint, rule: Optional[ComplaintRule]) -> list[dict]:
    category = (complaint.verified_category or complaint.issue_category or "").strip()
    templates = _CAUSE_MAP.get(category, [("Undetermined — insufficient recurring signal", "Process", "no matching pattern")])

    window_start = utcnow() - timedelta(days=90)
    peers = (db.query(Complaint)
            .filter(Complaint.issue_category == category, Complaint.created_at >= window_start)
            .count()) if category else 0
    total_recent = db.query(Complaint).filter(Complaint.created_at >= window_start).count() or 1
    recurrence = peers / total_recent

    candidates = []
    for i, (cause, ishikawa, basis) in enumerate(templates):
        # confidence: driven by category recurrence rate, decayed for lower-ranked candidates
        base_conf = min(0.9, 0.25 + recurrence * 2.0)
        confidence = round(max(0.15, base_conf - i * 0.15), 2)
        candidates.append({
            "cause": cause, "category": ishikawa, "method": "recurring-pattern (5 Whys style chain)", "basis": basis,
            "confidence": confidence,
            "supporting_count": peers,
            "chain": _five_whys_chain(category, cause),
        })
    return candidates


def _five_whys_chain(category: str, cause: str) -> list[str]:
    chains = {
        "Delivery": ["Complaint: late delivery", "Why? Dispatch was delayed", "Why? Carrier pickup missed cutoff",
                    "Why? Inventory location mismatch", f"Root cause candidate: {cause}"],
        "Product": ["Complaint: product defect on arrival", "Why? Unit failed at first use",
                   "Why? Defect not caught before shipping", f"Root cause candidate: {cause}"],
        "Refund": ["Complaint: refund not received", "Why? Refund not processed within SLA",
                  "Why? Manual approval step backlog", f"Root cause candidate: {cause}"],
    }
    return chains.get(category, ["Complaint reported", f"Root cause candidate: {cause}"])


# ---------------------------------------------------------------------------
# CAPA
# ---------------------------------------------------------------------------

def _next_capa_code(db: Session) -> str:
    count = db.query(CapaRecord).count()
    return f"CAPA-{count + 1:05d}"


def generate_capa(db: Session, complaint: Complaint, root_cause: dict, investigation_id: Optional[int] = None) -> CapaRecord:
    category = complaint.verified_category or complaint.issue_category or "General"
    priority = "P1" if root_cause["category"] == "Materials/Product" and category == "Safety" else \
              ("P2" if root_cause["confidence"] >= 0.5 else "P3")
    record = CapaRecord(
        code=_next_capa_code(db), complaint_id=complaint.id, investigation_id=investigation_id,
        root_cause=root_cause["cause"],
        corrective_action=f"Investigate and remediate the immediate cause behind complaint {complaint.code} "
                          f"({root_cause['cause']}); communicate resolution to the affected customer.",
        preventive_action=f"Address the recurring '{root_cause['category']}' pattern in {category} complaints: "
                          f"review the relevant process/system and add a monitoring check for recurrence.",
        owner_department=complaint.verified_department or complaint.department or "Customer Service Management",
        priority=priority, expected_outcome=f"Reduction in recurring {category} complaints of this kind.",
        suggested_deadline=utcnow() + timedelta(days=14 if priority == "P1" else 30),
        required_evidence=["Root-cause confirmation from the owning department",
                           "Before/after complaint-volume comparison for this category"],
        supporting={"root_cause": root_cause, "supporting_count": root_cause.get("supporting_count", 0)},
        status="PROPOSED",
    )
    db.add(record)
    db.flush()
    return record


def capa_dict(record: CapaRecord) -> dict:
    return {
        "id": record.id, "code": record.code, "complaint_id": record.complaint_id, "status": record.status,
        "root_cause": record.root_cause, "corrective_action": record.corrective_action,
        "preventive_action": record.preventive_action, "owner_department": record.owner_department,
        "priority": record.priority, "expected_outcome": record.expected_outcome,
        "suggested_deadline": record.suggested_deadline.isoformat() if record.suggested_deadline else None,
        "required_evidence": record.required_evidence or [], "supporting": record.supporting or {},
        "decision_notes": record.decision_notes, "decided_at": record.decided_at.isoformat() if record.decided_at else None,
        "created_at": record.created_at.isoformat() if record.created_at else None,
    }


def decide_capa(db: Session, record: CapaRecord, decision: str, user: Optional[User], notes: str = "") -> CapaRecord:
    if decision not in {"APPROVED", "REJECTED"}:
        raise ValueError("decision must be APPROVED or REJECTED")
    record.status = decision
    record.decided_by = user.id if user else None
    record.decided_at = utcnow()
    record.decision_notes = notes
    return record
