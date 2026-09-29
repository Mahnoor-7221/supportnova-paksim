"""Complaint lifecycle endpoints: submit, analyze, validate, review data."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, Request, UploadFile, status
from sqlalchemy.orm import Session

from ..audit import log_action
from ..config import STORAGE_DIR
from ..database import get_db
from ..models import (
    COMPLAINT_STATUSES,
    AIAnalysis,
    Complaint,
    ComplaintAttachment,
    ComplaintHistory,
    ComplaintRule,
    Escalation,
    ManualReview,
    PromptVersion,
    SimCard,
    User,
    ValidationResult,
)
from ..models_nova import SatisfactionFeedback, AssistantMessage, AssistantSession
from ..schemas import ComplaintCreate, ComplaintUpdate
from ..security import get_current_user
from ..serializers import (
    analysis_dict,
    complaint_brief,
    complaint_full,
    escalation_dict,
    history_dict,
    review_dict,
    validation_dict,
)
from ..services.analysis_service import analyze_complaint, regenerate_response
from ..services.document_processor import DocumentProcessingError, validate_upload
from ..services.duplicate_detector import find_duplicate
from ..services.genai_client import AIProviderError
from ..services.trust_engine import latest_assessment, serialize_assessment
from ..python_validation import run_validation
from ..utils import mask_pk_mobile, normalize_pk_mobile, utcnow

router = APIRouter(prefix="/api/complaints", tags=["complaints"])


def _is_staff(user: User) -> bool:
    return bool(user.role and user.role.name in {"admin", "agent"})


def _get_complaint_or_404(db: Session, complaint_id: int) -> Complaint:
    complaint = db.get(Complaint, complaint_id)
    if complaint is None:
        raise HTTPException(status_code=404, detail="Complaint not found")
    return complaint


def _ensure_access(complaint: Complaint, user: User) -> None:
    if _is_staff(user):
        return
    if complaint.customer_id != user.id and complaint.created_by != user.id:
        raise HTTPException(status_code=403, detail="You can only access your own complaints")


def _latest_analysis(db: Session, complaint_id: int) -> Optional[AIAnalysis]:
    return (
        db.query(AIAnalysis)
        .filter(AIAnalysis.complaint_id == complaint_id)
        .order_by(AIAnalysis.id.desc())
        .first()
    )


def _latest_validation(db: Session, complaint_id: int) -> Optional[ValidationResult]:
    return (
        db.query(ValidationResult)
        .filter(ValidationResult.complaint_id == complaint_id)
        .order_by(ValidationResult.id.desc())
        .first()
    )


def _prompt_version_label(db: Session, analysis: Optional[AIAnalysis]) -> Optional[str]:
    if analysis is None or analysis.prompt_version_id is None:
        return None
    row = db.get(PromptVersion, analysis.prompt_version_id)
    return f"{row.name} {row.version}" if row else None


def _rule_dict(rule: Optional[ComplaintRule]) -> Optional[dict]:
    if rule is None:
        return None
    return {
        "id": rule.id,
        "rule_id": rule.rule_id,
        "category": rule.category,
        "subcategory": rule.subcategory,
        "conditions": rule.conditions or {},
        "department": rule.department,
        "urgency": rule.urgency,
        "priority": rule.priority,
        "policy_id": rule.policy_id,
        "escalation": rule.escalation,
        "required_actions": rule.required_actions or [],
        "prohibited_actions": rule.prohibited_actions or [],
        "follow_up": rule.follow_up,
    }


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

@router.post("", status_code=status.HTTP_201_CREATED)
def create_complaint(
    payload: ComplaintCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # Only customers with a registered PakSim SIM can file complaints (staff can file on behalf).
    mobile = ""
    if not _is_staff(user):
        sims = db.query(SimCard).filter(SimCard.customer_id == user.id).all()
        if not sims:
            raise HTTPException(status_code=403, detail=(
                "Aapke account par koi PakSim SIM registered nahi hai, is liye complaint register nahi ho sakti."))
        if payload.mobile_number:
            mobile = normalize_pk_mobile(payload.mobile_number)
            if not mobile or not any(normalize_pk_mobile(s.phone_number) == mobile for s in sims):
                raise HTTPException(status_code=403, detail=(
                    "Yeh mobile number aapke account par PakSim registered nahi hai, is liye complaint register nahi ho sakti."))
    complaint = Complaint(
        code="TMP",
        title=payload.title.strip(),
        description=payload.description.strip(),
        customer_type=payload.customer_type,
        product_or_service=(f"PakSim SIM {mobile}" if mobile and not payload.product_or_service else payload.product_or_service),
        order_reference=payload.order_reference,
        channel=payload.channel,
        complaint_date=payload.complaint_date,
        requested_resolution=payload.requested_resolution,
        previous_complaints=max(0, payload.previous_complaints),
        supporting_document_name=payload.supporting_document_name,
        customer_id=user.id,
        created_by=user.id,
        status="NEW",
    )
    db.add(complaint)
    db.flush()
    complaint.code = f"CMP-{complaint.id:05d}"

    duplicate = find_duplicate(db, complaint)
    if duplicate["duplicate_of_id"]:
        complaint.duplicate_of_id = duplicate["duplicate_of_id"]
        complaint.duplicate_similarity = duplicate["similarity"]

    missing = [f for f in ("order_reference", "product_or_service", "complaint_date")
               if not getattr(complaint, f, None)]
    complaint.missing_fields = missing
    complaint.incomplete = bool(missing)

    db.add(ComplaintHistory(complaint_id=complaint.id, from_status="", to_status="NEW",
                            note="Complaint submitted", actor_id=user.id))
    db.commit()
    db.refresh(complaint)

    log_action(db, "complaint.created", "complaint", complaint.code,
               {"duplicate_similarity": complaint.duplicate_similarity}, user=user, request=request)
    return complaint_full(complaint)


@router.get("")
def list_complaints(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    q: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    category: Optional[str] = None,
    urgency: Optional[str] = None,
    priority: Optional[str] = None,
    department: Optional[str] = None,
    flag: Optional[str] = None,
    dataset: Optional[bool] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=200),
):
    query = db.query(Complaint)
    if not _is_staff(user):
        query = query.filter((Complaint.customer_id == user.id) | (Complaint.created_by == user.id))
    if q:
        pattern = f"%{q.strip()}%"
        query = query.filter(
            (Complaint.title.ilike(pattern)) | (Complaint.description.ilike(pattern)) | (Complaint.code.ilike(pattern))
        )
    if status_filter:
        query = query.filter(Complaint.status == status_filter)
    if category:
        query = query.filter((Complaint.issue_category == category) | (Complaint.verified_category == category))
    if urgency:
        query = query.filter((Complaint.urgency == urgency) | (Complaint.verified_urgency == urgency))
    if priority:
        query = query.filter((Complaint.priority == priority) | (Complaint.verified_priority == priority))
    if department:
        query = query.filter((Complaint.department == department) | (Complaint.verified_department == department))
    if flag == "injection":
        query = query.filter(Complaint.injection_detected.is_(True))
    elif flag == "duplicate":
        query = query.filter(Complaint.duplicate_of_id.isnot(None))
    elif flag == "incomplete":
        query = query.filter(Complaint.incomplete.is_(True))
    elif flag == "multi_issue":
        query = query.filter(Complaint.flags.like('%"multi_issue"%'))
    if dataset is not None:
        query = query.filter(Complaint.is_dataset_case.is_(dataset))

    total = query.count()
    rows = (
        query.order_by(Complaint.created_at.desc(), Complaint.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {"total": total, "items": [complaint_brief(row) for row in rows]}


@router.get("/{complaint_id}/messages")
def complaint_messages(complaint_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    complaint = _get_complaint_or_404(db, complaint_id)
    _ensure_access(complaint, user)
    if not complaint.source_session_uuid:
        return []
    session = db.query(AssistantSession).filter(AssistantSession.uuid == complaint.source_session_uuid).first()
    if not session:
        return []
    rows = db.query(AssistantMessage).filter(AssistantMessage.session_id == session.id).order_by(AssistantMessage.id.asc()).all()
    return [{
        "id": r.id, "role": r.role,
        "sender_type": (r.meta or {}).get("sender_type") or ("customer" if r.role == "user" else "ai"),
        "sender_name": (r.meta or {}).get("sender_name") or ("Customer" if r.role == "user" else "Nova"),
        "text": r.text, "language": r.language, "modality": r.modality,
        "created_at": r.created_at.isoformat() if r.created_at else None, "meta": r.meta or {},
    } for r in rows]


@router.post("/{complaint_id}/messages")
def customer_reply(complaint_id: int, payload: dict = Body(...), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Customer sends a message to the assigned agent in the same complaint thread."""
    complaint = _get_complaint_or_404(db, complaint_id)
    if complaint.customer_id != user.id:
        raise HTTPException(status_code=403, detail="Only the complaint owner can reply here")
    text = str(payload.get("message") or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="Message is required")
    if len(text) > 5000:
        raise HTTPException(status_code=422, detail="Message is too long")
    session = None
    if complaint.source_session_uuid:
        session = db.query(AssistantSession).filter(AssistantSession.uuid == complaint.source_session_uuid).first()
    if session is None:
        import uuid as _uuid
        session = AssistantSession(uuid=str(_uuid.uuid4()), user_id=user.id)
        db.add(session); db.flush()
        complaint.source_session_uuid = session.uuid
    row = AssistantMessage(session_id=session.id, role="user", text=text, language="en", modality="text",
                           meta={"sender_type": "customer", "sender_id": user.id, "sender_name": user.full_name or "Customer", "complaint_id": complaint.id})
    db.add(row)
    previous = complaint.status
    if complaint.status == "WAITING_CUSTOMER":
        complaint.status = "IN_PROGRESS"
    elif complaint.status in {"RESOLVED", "CLOSED"}:
        complaint.status = "PENDING"  # customer came back -> agent must look again
    complaint.updated_at = utcnow()
    db.add(ComplaintHistory(complaint_id=complaint.id, from_status=previous, to_status=complaint.status,
                            note=f"Customer replied: {text[:250]}", actor_id=user.id))
    db.commit(); db.refresh(row)
    return {"id": row.id, "role": row.role, "sender_type": "customer", "sender_name": row.meta.get("sender_name"),
            "text": row.text, "language": row.language, "modality": row.modality,
            "created_at": row.created_at.isoformat() if row.created_at else None, "meta": row.meta}


@router.post("/{complaint_id}/feedback")
def submit_customer_feedback(
    complaint_id: int,
    payload: dict = Body(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Store one customer satisfaction rating for a resolved/closed complaint."""
    complaint = _get_complaint_or_404(db, complaint_id)
    _ensure_access(complaint, user)
    if _is_staff(user):
        raise HTTPException(status_code=403, detail="Only customers can submit satisfaction feedback")
    if complaint.status not in {"RESOLVED", "CLOSED"}:
        raise HTTPException(status_code=400, detail="Feedback is available after the complaint is resolved")

    try:
        rating = int(payload.get("rating", 0))
    except (TypeError, ValueError):
        rating = 0
    if rating < 1 or rating > 5:
        raise HTTPException(status_code=422, detail="Rating must be between 1 and 5")
    comment = str(payload.get("comment", "") or "").strip()[:2000]

    feedback = (
        db.query(SatisfactionFeedback)
        .filter(SatisfactionFeedback.complaint_id == complaint.id, SatisfactionFeedback.customer_id == user.id)
        .order_by(SatisfactionFeedback.id.desc())
        .first()
    )
    if feedback is None:
        feedback = SatisfactionFeedback(complaint_id=complaint.id, customer_id=user.id)
        db.add(feedback)
    feedback.rating = rating
    feedback.comment = comment
    db.commit()
    db.refresh(feedback)
    return {"rating": feedback.rating, "comment": feedback.comment, "created_at": feedback.created_at.isoformat() if feedback.created_at else None}


@router.get("/{complaint_id}")
def get_complaint(
    complaint_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    complaint = _get_complaint_or_404(db, complaint_id)
    _ensure_access(complaint, user)

    rule = None
    if complaint.matched_rule_id:
        rule = db.query(ComplaintRule).filter(ComplaintRule.rule_id == complaint.matched_rule_id).first()
    analysis = _latest_analysis(db, complaint.id)
    validation = _latest_validation(db, complaint.id)
    assessment = latest_assessment(db, complaint.id)

    duplicate_of = None
    if complaint.duplicate_of_id:
        original = db.get(Complaint, complaint.duplicate_of_id)
        if original is not None:
            duplicate_of = complaint_brief(original)

    feedback = (
        db.query(SatisfactionFeedback)
        .filter(SatisfactionFeedback.complaint_id == complaint.id, SatisfactionFeedback.customer_id == user.id)
        .order_by(SatisfactionFeedback.id.desc())
        .first()
    )

    return {
        "complaint": complaint_full(complaint),
        "rule": _rule_dict(rule),
        "analysis": analysis_dict(analysis, _prompt_version_label(db, analysis)) if analysis else None,
        "validation": validation_dict(validation) if validation else None,
        "trust": serialize_assessment(assessment) if assessment else None,
        "history": [history_dict(h) for h in complaint.history],
        "escalations": [
            escalation_dict(e)
            for e in db.query(Escalation).filter(Escalation.complaint_id == complaint.id).all()
        ],
        "manual_reviews": [
            review_dict(r)
            for r in db.query(ManualReview).filter(ManualReview.complaint_id == complaint.id).all()
        ],
        "feedback": (
            {"rating": feedback.rating, "comment": feedback.comment, "created_at": feedback.created_at.isoformat() if feedback.created_at else None}
            if feedback else None
        ),
        "duplicate_of": duplicate_of,
    }


@router.put("/{complaint_id}")
def update_complaint(
    complaint_id: int,
    payload: ComplaintUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    complaint = _get_complaint_or_404(db, complaint_id)
    _ensure_access(complaint, user)

    if not _is_staff(user) and complaint.status not in {"NEW", "ANALYZING"}:
        raise HTTPException(status_code=403, detail="Complaints can only be edited before analysis starts")

    data = payload.model_dump(exclude_unset=True)
    status_change = data.pop("status", None)
    agent_change = data.pop("assigned_agent_id", None) if "assigned_agent_id" in data else None
    resolution_text = data.pop("resolution_text", None) if "resolution_text" in data else None
    rejection_reason = data.pop("rejection_reason", None) if "rejection_reason" in data else None

    for field, value in data.items():
        if value is not None:
            setattr(complaint, field, value)

    if agent_change is not None:
        if not _is_staff(user):
            raise HTTPException(status_code=403, detail="Only staff can assign agents")
        prev_agent = complaint.assigned_agent_id
        complaint.assigned_agent_id = agent_change if agent_change else None
        if prev_agent != complaint.assigned_agent_id:
            note = f"Assigned to agent #{complaint.assigned_agent_id}" if complaint.assigned_agent_id else "Unassigned"
            db.add(ComplaintHistory(
                complaint_id=complaint.id,
                from_status=complaint.status,
                to_status="ASSIGNED" if complaint.assigned_agent_id else complaint.status,
                note=note,
                actor_id=user.id,
            ))
            if complaint.assigned_agent_id and complaint.status in {"NEW", "ANALYZING"}:
                previous = complaint.status
                complaint.status = "ASSIGNED"
                db.add(ComplaintHistory(
                    complaint_id=complaint.id, from_status=previous, to_status="ASSIGNED",
                    note="Auto-status on assignment", actor_id=user.id,
                ))

    if resolution_text is not None:
        if not _is_staff(user):
            raise HTTPException(status_code=403, detail="Only staff can set resolution")
        complaint.resolution_text = resolution_text

    if rejection_reason is not None:
        if not _is_staff(user):
            raise HTTPException(status_code=403, detail="Only staff can set rejection reason")
        if not str(rejection_reason).strip() and (status_change or "").upper() == "REJECTED":
            raise HTTPException(status_code=400, detail="Rejection reason is required")
        complaint.rejection_reason = rejection_reason

    if status_change:
        if not _is_staff(user):
            raise HTTPException(status_code=403, detail="Only staff can change the complaint status")
        if status_change not in COMPLAINT_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid status '{status_change}'")
        if status_change != complaint.status:
            if status_change.upper() == "REJECTED" and not (complaint.rejection_reason or "").strip():
                raise HTTPException(status_code=400, detail="Rejection reason is required when rejecting")
            if status_change.upper() == "RESOLVED" and not (complaint.resolution_text or "").strip():
                # allow resolve without text but prefer having one
                pass
            previous = complaint.status
            complaint.status = status_change
            note = "Status updated manually"
            if status_change.upper() == "REJECTED":
                note = f"Rejected: {complaint.rejection_reason}"
            elif status_change.upper() == "RESOLVED":
                note = f"Resolved: {(complaint.resolution_text or '')[:200]}"
            db.add(ComplaintHistory(complaint_id=complaint.id, from_status=previous,
                                    to_status=status_change, note=note, actor_id=user.id))
            if status_change in {"RESOLVED", "CLOSED"}:
                for escalation in db.query(Escalation).filter(
                    Escalation.complaint_id == complaint.id, Escalation.status != "RESOLVED"
                ):
                    escalation.status = "RESOLVED"
                    escalation.resolved_at = utcnow()

    complaint.updated_at = utcnow()
    db.commit()
    db.refresh(complaint)
    log_action(db, "complaint.updated", "complaint", complaint.code, {"fields": list(data.keys())},
               user=user, request=request)
    return complaint_full(complaint)


# ---------------------------------------------------------------------------
# Pipeline 1 / Pipeline 2 triggers
# ---------------------------------------------------------------------------

@router.post("/{complaint_id}/analyze")
def analyze(
    complaint_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    complaint = _get_complaint_or_404(db, complaint_id)
    _ensure_access(complaint, user)
    if complaint.status == "ANALYZING":
        raise HTTPException(status_code=409, detail="Analysis already running for this complaint")

    try:
        analysis, context = analyze_complaint(db, complaint, user.id)
    except AIProviderError as exc:
        complaint.status = "NEW"
        db.add(ComplaintHistory(complaint_id=complaint.id, from_status="ANALYZING", to_status="NEW",
                                note=f"Analysis aborted: {exc}", actor_id=user.id))
        db.commit()
        raise HTTPException(status_code=502, detail=f"GenAI provider error: {exc}")

    log_action(db, "complaint.analyzed", "complaint", complaint.code,
               {"provider": analysis.provider, "rule": complaint.matched_rule_id}, user=user, request=request)
    return {
        "analysis": analysis_dict(analysis, _prompt_version_label(db, analysis)),
        "matched_rule": _rule_dict(context["matched_rule"]),
        "escalation": context["escalation"],
        "injection": context["injection"],
        "secondary_issues": context["secondary_issues"],
        "status": complaint.status,
    }


@router.post("/{complaint_id}/validate")
def validate(
    complaint_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    complaint = _get_complaint_or_404(db, complaint_id)
    _ensure_access(complaint, user)
    analysis = _latest_analysis(db, complaint.id)
    if analysis is None:
        raise HTTPException(status_code=409, detail="Run the GenAI analysis before validation")

    result = run_validation(db, complaint, analysis, user.id)
    log_action(db, "complaint.validated", "complaint", complaint.code,
               {"status": result.status}, user=user, request=request)
    return validation_dict(result)


@router.get("/{complaint_id}/analysis")
def get_analysis(
    complaint_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    complaint = _get_complaint_or_404(db, complaint_id)
    _ensure_access(complaint, user)
    analysis = _latest_analysis(db, complaint.id)
    if analysis is None:
        raise HTTPException(status_code=404, detail="No analysis available for this complaint")
    return analysis_dict(analysis, _prompt_version_label(db, analysis))


@router.get("/{complaint_id}/validation")
def get_validation(
    complaint_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    complaint = _get_complaint_or_404(db, complaint_id)
    _ensure_access(complaint, user)
    validation = _latest_validation(db, complaint.id)
    if validation is None:
        raise HTTPException(status_code=404, detail="No validation result available for this complaint")
    return validation_dict(validation)


@router.get("/{complaint_id}/verification")
def get_verification(
    complaint_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Trust Gate verdict for this complaint (latest assessment)."""
    complaint = _get_complaint_or_404(db, complaint_id)
    _ensure_access(complaint, user)
    assessment = latest_assessment(db, complaint.id)
    if assessment is None:
        raise HTTPException(status_code=404, detail="No trust assessment available for this complaint")
    return serialize_assessment(assessment)


@router.get("/{complaint_id}/history")
def get_history(
    complaint_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    complaint = _get_complaint_or_404(db, complaint_id)
    _ensure_access(complaint, user)
    return [history_dict(entry) for entry in complaint.history]


@router.post("/{complaint_id}/response")
def regenerate_customer_response(
    complaint_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    complaint = _get_complaint_or_404(db, complaint_id)
    _ensure_access(complaint, user)
    analysis = _latest_analysis(db, complaint.id)
    if analysis is None:
        raise HTTPException(status_code=409, detail="Run the GenAI analysis first")

    try:
        text = regenerate_response(db, complaint, analysis, user.id)
    except AIProviderError as exc:
        raise HTTPException(status_code=502, detail=f"GenAI provider error: {exc}")

    analysis.parsed = {**(analysis.parsed or {}), "professional_response": text}
    db.commit()
    log_action(db, "complaint.response_regenerated", "complaint", complaint.code, {}, user=user, request=request)
    return {"professional_response": text}


# ---------------------------------------------------------------------------
# Attachments & status
# ---------------------------------------------------------------------------

@router.post("/{complaint_id}/attachments", status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    complaint_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    complaint = _get_complaint_or_404(db, complaint_id)
    _ensure_access(complaint, user)

    content = await file.read()
    try:
        ext = validate_upload(file.filename or "", len(content))
    except DocumentProcessingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    folder = STORAGE_DIR / "attachments" / str(complaint.id)
    folder.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or f"attachment.{ext}").name
    stored = folder / f"{utcnow().strftime('%Y%m%d%H%M%S')}_{safe_name}"
    stored.write_bytes(content)

    attachment = ComplaintAttachment(
        complaint_id=complaint.id,
        file_name=safe_name,
        stored_path=str(stored),
        size_bytes=len(content),
        uploaded_by=user.id,
    )
    db.add(attachment)
    db.commit()
    log_action(db, "complaint.attachment_uploaded", "complaint", complaint.code,
               {"file": safe_name, "size": len(content)}, user=user, request=request)
    return {"id": attachment.id, "file_name": attachment.file_name, "size_bytes": attachment.size_bytes}


@router.post("/{complaint_id}/status")
def update_status(
    complaint_id: int,
    request: Request,
    payload: dict,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not _is_staff(user):
        raise HTTPException(status_code=403, detail="Only staff can change the complaint status")
    complaint = _get_complaint_or_404(db, complaint_id)

    new_status = str(payload.get("status") or "").upper()
    note = str(payload.get("note") or "")
    if new_status not in COMPLAINT_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status '{new_status}'")
    if new_status == complaint.status:
        return {"status": complaint.status, "changed": False}

    previous = complaint.status
    complaint.status = new_status
    db.add(ComplaintHistory(complaint_id=complaint.id, from_status=previous, to_status=new_status,
                            note=note or "Status updated", actor_id=user.id))
    if new_status in {"RESOLVED", "CLOSED"}:
        for escalation in db.query(Escalation).filter(
            Escalation.complaint_id == complaint.id, Escalation.status != "RESOLVED"
        ):
            escalation.status = "RESOLVED"
            escalation.resolved_at = utcnow()
    db.commit()
    log_action(db, "complaint.status_changed", "complaint", complaint.code,
               {"from": previous, "to": new_status, "note": note}, user=user, request=request)
    return {"status": complaint.status, "changed": True}


@router.get("/{complaint_id}/duplicates")
def get_duplicates(
    complaint_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    complaint = _get_complaint_or_404(db, complaint_id)
    _ensure_access(complaint, user)
    if not complaint.duplicate_of_id:
        return {"possible_duplicate": False, "original": None, "similarity": 0.0}
    original = db.get(Complaint, complaint.duplicate_of_id)
    return {
        "possible_duplicate": True,
        "original": complaint_brief(original) if original else None,
        "similarity": complaint.duplicate_similarity,
    }
