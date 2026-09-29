"""Trust Gate endpoints — aggregate verdicts and per-complaint assessments.

The Trust Gate sits behind every validation run: it converts the independent
Python verification checks into a transparent 0-100 score, a three-state
decision (VERIFIED / REVIEW_REQUIRED / BLOCKED) and an explainable rejection
report. These endpoints expose exactly what was computed — nothing is
hardcoded here.
"""
from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Complaint, ManualReview, TrustAssessment, User
from ..security import get_current_user, require_staff
from ..services.trust_engine import (
    CATEGORY_DEFINITION,
    latest_assessment,
    serialize_assessment,
)

router = APIRouter(prefix="/api/trust", tags=["trust"])

DECISION_RULE = (
    "BLOCKED if any critical blocker fired (prompt injection, unsupported "
    "promise, prohibited content, fabricated policy, missed critical "
    "escalation); otherwise VERIFIED only when every independent check "
    "passed cleanly, else REVIEW_REQUIRED."
)


def _is_staff(user: User) -> bool:
    return bool(user.role and user.role.name in {"admin", "agent"})


@router.get("/summary")
def trust_summary(db: Session = Depends(get_db), staff: User = Depends(require_staff)):
    assessments = db.query(TrustAssessment).all()
    decisions = Counter(row.decision for row in assessments)
    scores = [row.score for row in assessments if row.score is not None]
    total = len(assessments)

    hotspot_counter: Counter = Counter()
    severity_counter: Counter = Counter()
    category_counter: Counter = Counter()
    for row in assessments:
        for failed in row.failed_checks or []:
            hotspot_counter[failed.get("check_name") or "unknown"] += 1
            severity_counter[failed.get("severity") or "medium"] += 1
            category_counter[failed.get("category") or "Other"] += 1

    recent_rows = (
        db.query(TrustAssessment)
        .order_by(TrustAssessment.id.desc())
        .limit(12)
        .all()
    )
    recent = []
    for row in recent_rows:
        complaint = db.get(Complaint, row.complaint_id)
        recent.append(serialize_assessment(row, complaint))

    return {
        "total_assessed": total,
        "counts": {
            "verified": decisions.get("VERIFIED", 0),
            "review_required": decisions.get("REVIEW_REQUIRED", 0),
            "blocked": decisions.get("BLOCKED", 0),
        },
        "verified_rate": round(decisions.get("VERIFIED", 0) / total, 3) if total else None,
        "blocked_rate": round(decisions.get("BLOCKED", 0) / total, 3) if total else None,
        "average_score": round(sum(scores) / len(scores)) if scores else None,
        "open_manual_reviews": db.query(ManualReview).filter(ManualReview.status == "OPEN").count(),
        "failure_hotspots": [
            {"name": name, "value": value} for name, value in hotspot_counter.most_common(8)
        ],
        "failing_by_severity": [
            {"name": name, "value": value} for name, value in severity_counter.most_common()
        ],
        "failing_by_category": [
            {"name": name, "value": value} for name, value in category_counter.most_common()
        ],
        "scoring": {
            "categories": CATEGORY_DEFINITION,
            "check_values": {"OK": 1.0, "WARNING": 0.5, "FAIL": 0.0},
            "scale": "0-100 (100 = every check passed cleanly)",
            "decision_rule": DECISION_RULE,
        },
        "recent": recent,
    }


@router.get("/{complaint_id}")
def complaint_trust(
    complaint_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    complaint = db.get(Complaint, complaint_id)
    if complaint is None:
        raise HTTPException(status_code=404, detail="Complaint not found")
    if not _is_staff(user) and complaint.customer_id != user.id and complaint.created_by != user.id:
        raise HTTPException(status_code=403, detail="You can only access your own complaints")

    assessment = latest_assessment(db, complaint_id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="No trust assessment available for this complaint")
    return serialize_assessment(assessment, complaint)
