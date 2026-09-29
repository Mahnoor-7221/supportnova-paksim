"""Manual review queue — human decision workflow with audit trail."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from ..audit import log_action
from ..database import get_db
from ..models import (
    AIAnalysis,
    Complaint,
    ComplaintHistory,
    Escalation,
    ManualReview,
    User,
    ValidationResult,
)
from ..schemas import ReviewDecisionRequest
from ..security import require_roles
from ..serializers import (
    analysis_dict,
    complaint_full,
    review_dict,
    validation_dict,
)
from ..utils import utcnow

router = APIRouter(prefix="/api/manual-review", tags=["manual-review"])
review_access = require_roles("admin", "agent", "reviewer", "manager")


def _open_review_or_404(db: Session, review_id: int) -> ManualReview:
    review = db.get(ManualReview, review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Manual review entry not found")
    return review


def _decide(
    db: Session,
    review: ManualReview,
    decision: str,
    notes: str,
    modifications: dict,
    user: User,
    new_status: str,
    history_note: str,
) -> ManualReview:
    complaint = db.get(Complaint, review.complaint_id)
    review.status = "RESOLVED"
    review.decision = decision
    review.decision_notes = notes
    review.modifications = modifications or {}
    review.decided_by = user.id
    review.decided_at = utcnow()

    if complaint is not None:
        previous = complaint.status
        complaint.status = new_status
        complaint.updated_at = utcnow()
        db.add(ComplaintHistory(complaint_id=complaint.id, from_status=previous,
                                to_status=new_status, note=history_note, actor_id=user.id))
    db.commit()
    db.refresh(review)
    return review


@router.get("")
def list_reviews(
    db: Session = Depends(get_db),
    user: User = Depends(review_access),
    status_filter: Optional[str] = Query(None, alias="status"),
    source: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
):
    query = db.query(ManualReview)
    if status_filter:
        query = query.filter(ManualReview.status == status_filter)
    if source:
        query = query.filter(ManualReview.source == source)

    total = query.count()
    rows = (
        query.order_by(ManualReview.status.asc(), ManualReview.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = []
    for review in rows:
        complaint = db.get(Complaint, review.complaint_id)
        items.append(review_dict(review, complaint))
    return {"total": total, "items": items}


@router.get("/{review_id}")
def get_review(
    review_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(review_access),
):
    review = _open_review_or_404(db, review_id)
    complaint = db.get(Complaint, review.complaint_id)
    analysis = (
        db.query(AIAnalysis)
        .filter(AIAnalysis.complaint_id == review.complaint_id)
        .order_by(AIAnalysis.id.desc())
        .first()
    )
    validation = (
        db.query(ValidationResult)
        .filter(ValidationResult.complaint_id == review.complaint_id)
        .order_by(ValidationResult.id.desc())
        .first()
    )
    return {
        "review": review_dict(review),
        "complaint": complaint_full(complaint) if complaint else None,
        "analysis": analysis_dict(analysis) if analysis else None,
        "validation": validation_dict(validation) if validation else None,
    }


@router.post("/{review_id}/approve")
def approve(
    review_id: int,
    payload: ReviewDecisionRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(review_access),
):
    review = _open_review_or_404(db, review_id)
    if review.status == "RESOLVED":
        raise HTTPException(status_code=409, detail="This review has already been decided")
    review = _decide(db, review, "approve", payload.notes, payload.modifications, user,
                     "IN_PROGRESS", f"Manual review #{review.id}: approved - {payload.notes or 'AI output accepted'}")
    log_action(db, "manual_review.approved", "manual_review", review.id,
               {"complaint_id": review.complaint_id, "notes": payload.notes}, user=user, request=request)
    return review_dict(review)


@router.post("/{review_id}/reject")
def reject(
    review_id: int,
    payload: ReviewDecisionRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(review_access),
):
    review = _open_review_or_404(db, review_id)
    if review.status == "RESOLVED":
        raise HTTPException(status_code=409, detail="This review has already been decided")
    review = _decide(db, review, "reject", payload.notes, payload.modifications, user,
                     "CLOSED", f"Manual review #{review.id}: rejected - {payload.notes or 'AI output rejected'}")
    log_action(db, "manual_review.rejected", "manual_review", review.id,
               {"complaint_id": review.complaint_id, "notes": payload.notes}, user=user, request=request)
    return review_dict(review)


@router.post("/{review_id}/escalate")
def escalate(
    review_id: int,
    payload: ReviewDecisionRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(review_access),
):
    review = _open_review_or_404(db, review_id)
    if review.status == "RESOLVED":
        raise HTTPException(status_code=409, detail="This review has already been decided")
    complaint = db.get(Complaint, review.complaint_id)

    if complaint is not None:
        existing = (
            db.query(Escalation)
            .filter(Escalation.complaint_id == complaint.id, Escalation.status != "RESOLVED")
            .first()
        )
        if existing is None:
            db.add(Escalation(
                complaint_id=complaint.id,
                reason=payload.notes or "Escalated from manual review",
                triggers=["management_approval_required"],
                department="Customer Service Management",
                priority=complaint.priority or "P2",
                created_by=user.id,
            ))

    review = _decide(db, review, "escalate", payload.notes, payload.modifications, user,
                     "ESCALATED", f"Manual review #{review.id}: escalated - {payload.notes or 'to management'}")
    log_action(db, "manual_review.escalated", "manual_review", review.id,
               {"complaint_id": review.complaint_id, "notes": payload.notes}, user=user, request=request)
    return review_dict(review)


@router.post("/{review_id}/modify")
def modify(
    review_id: int,
    payload: ReviewDecisionRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(review_access),
):
    review = _open_review_or_404(db, review_id)
    if review.status == "RESOLVED":
        raise HTTPException(status_code=409, detail="This review has already been decided")

    complaint = db.get(Complaint, review.complaint_id)
    allowed_fields = {"issue_category", "subcategory", "urgency", "priority", "department",
                      "sentiment", "requested_resolution", "description", "title"}
    applied: dict = {}
    if complaint is not None:
        for field, value in (payload.modifications or {}).items():
            if field in allowed_fields and value is not None:
                setattr(complaint, field, value)
                applied[field] = value

    review = _decide(db, review, "modify", payload.notes, applied, user,
                     "IN_PROGRESS", f"Manual review #{review.id}: modified - {payload.notes or 'fields corrected'}")
    log_action(db, "manual_review.modified", "manual_review", review.id,
               {"complaint_id": review.complaint_id, "applied": applied}, user=user, request=request)
    return review_dict(review)
