"""Agent workspace APIs: authenticated, assigned-case operations only."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..audit import log_action
from ..database import get_db
from ..models import Complaint, ComplaintHistory, Role, User
from ..models_nova import AssistantMessage, AssistantSession
from ..security import get_current_user
from ..serializers import analysis_dict, complaint_brief, complaint_full
from ..utils import utcnow
from ..routers.complaints import _latest_analysis, _prompt_version_label

router = APIRouter(prefix="/api/agent", tags=["agent"])


def require_agent(user: User = Depends(get_current_user)) -> User:
    if not user.role or user.role.name != "agent":
        raise HTTPException(status_code=403, detail="Agent access required")
    return user


def _assigned_filter(query, user: User):
    return query.filter(Complaint.assigned_agent_id == user.id)


def _get_assigned(db: Session, complaint_id: int, user: User) -> Complaint:
    complaint = db.get(Complaint, complaint_id)
    if complaint is None:
        raise HTTPException(status_code=404, detail="Complaint not found")
    if complaint.assigned_agent_id != user.id:
        raise HTTPException(status_code=403, detail="This complaint is not assigned to you")
    return complaint


def _ensure_session(db: Session, complaint: Complaint) -> AssistantSession:
    if complaint.source_session_uuid:
        session = db.query(AssistantSession).filter(AssistantSession.uuid == complaint.source_session_uuid).first()
        if session:
            return session
    if complaint.customer_id is None:
        raise HTTPException(status_code=409, detail="This complaint has no customer conversation")
    import uuid
    session = AssistantSession(uuid=str(uuid.uuid4()), user_id=complaint.customer_id)
    db.add(session)
    db.flush()
    complaint.source_session_uuid = session.uuid
    db.add(complaint)
    db.flush()
    return session


def _message_dict(row: AssistantMessage) -> dict:
    meta = row.meta or {}
    sender_type = meta.get("sender_type") or ("customer" if row.role == "user" else "ai")
    return {
        "id": row.id,
        "role": row.role,
        "sender_type": sender_type,
        "sender_name": meta.get("sender_name") or ("Customer" if row.role == "user" else "Nova"),
        "text": row.text,
        "language": row.language,
        "modality": row.modality,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "meta": meta,
    }


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(require_agent)):
    base = _assigned_filter(db.query(Complaint), user)
    open_statuses = ["NEW", "ASSIGNED", "ANALYZING", "ANALYZED", "VALIDATION_FAILED", "MANUAL_REVIEW", "IN_PROGRESS", "PENDING", "WAITING_CUSTOMER", "ESCALATED"]
    rows = base.filter(Complaint.is_dataset_case.is_(False)).all()
    open_rows = [c for c in rows if c.status in open_statuses]
    today = utcnow().date()
    resolved_today = sum(1 for c in rows if c.status in {"RESOLVED", "CLOSED"} and c.updated_at and c.updated_at.date() == today)
    now = utcnow()
    sla_at_risk = sum(1 for c in open_rows if c.sla_due_at and c.sla_due_at <= now)
    waiting = sum(1 for c in open_rows if c.status == "WAITING_CUSTOMER")
    pending = sum(1 for c in open_rows if c.status in {"PENDING", "NEW", "ASSIGNED"})
    in_progress = sum(1 for c in open_rows if c.status == "IN_PROGRESS")
    urgent = sum(1 for c in open_rows if (c.verified_urgency or c.urgency or "").lower() in {"critical", "high", "urgent"} or (c.verified_priority or c.priority) in {"P1", "P2"})
    new_assigned = sum(1 for c in open_rows if c.status in {"NEW", "ASSIGNED"})
    latest = sorted(open_rows, key=lambda c: c.updated_at or c.created_at, reverse=True)[:8]
    urgent_rows = sorted([c for c in open_rows if ((c.verified_urgency or c.urgency or "").lower() in {"critical", "high", "urgent"} or (c.verified_priority or c.priority) in {"P1", "P2"})], key=lambda c: (c.verified_priority or c.priority or "P9", c.sla_due_at or datetime.max, c.created_at))[:6]
    return {
        "agent": {"id": user.id, "name": user.full_name, "email": user.email},
        "kpis": {"pending": pending, "new_assigned": new_assigned, "in_progress": in_progress, "waiting_customer": waiting, "urgent": urgent, "sla_at_risk": sla_at_risk, "resolved_today": resolved_today},
        "recent": [complaint_brief(c) for c in latest],
        "urgent_queue": [complaint_brief(c) for c in urgent_rows],
    }


@router.get("/complaints")
def my_complaints(
    db: Session = Depends(get_db),
    user: User = Depends(require_agent),
    q: Optional[str] = Query(None),
    filter: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    query = _assigned_filter(db.query(Complaint), user).filter(Complaint.is_dataset_case.is_(False))
    if q:
        pattern = f"%{q.strip()}%"
        query = query.filter(or_(Complaint.code.ilike(pattern), Complaint.title.ilike(pattern), Complaint.description.ilike(pattern)))
    if filter == "urgent":
        query = query.filter(or_(Complaint.urgency.in_(["Critical", "High", "Urgent"]), Complaint.priority.in_(["P1", "P2"]), Complaint.verified_urgency.in_(["Critical", "High", "Urgent"]), Complaint.verified_priority.in_(["P1", "P2"])))
    elif filter == "pending":
        query = query.filter(Complaint.status.in_(["PENDING", "NEW", "ASSIGNED"]))
    elif filter == "waiting":
        query = query.filter(Complaint.status == "WAITING_CUSTOMER")
    elif filter == "resolved":
        query = query.filter(Complaint.status.in_(["RESOLVED", "CLOSED"]))
    elif filter == "escalated":
        query = query.filter(Complaint.status == "ESCALATED")
    elif filter == "in_progress":
        query = query.filter(Complaint.status == "IN_PROGRESS")
    if status:
        query = query.filter(Complaint.status == status)
    total = query.count()
    rows = query.order_by(Complaint.updated_at.desc(), Complaint.id.desc()).offset((page-1)*page_size).limit(page_size).all()
    return {"total": total, "items": [complaint_brief(c) for c in rows]}


@router.get("/complaints/{complaint_id}")
def case_detail(complaint_id: int, db: Session = Depends(get_db), user: User = Depends(require_agent)):
    complaint = _get_assigned(db, complaint_id, user)
    analysis = _latest_analysis(db, complaint.id)
    session = None
    messages = []
    if complaint.source_session_uuid:
        session = db.query(AssistantSession).filter(AssistantSession.uuid == complaint.source_session_uuid).first()
        if session:
            messages = [_message_dict(m) for m in db.query(AssistantMessage).filter(AssistantMessage.session_id == session.id).order_by(AssistantMessage.id.asc()).all()]
    history = [{"id": h.id, "from_status": h.from_status, "to_status": h.to_status, "note": h.note, "actor_id": h.actor_id, "created_at": h.created_at.isoformat() if h.created_at else None} for h in complaint.history]
    parsed = (analysis.parsed or {}) if analysis else {}
    return {"complaint": complaint_full(complaint), "messages": messages, "history": history, "analysis": analysis_dict(analysis, _prompt_version_label(db, analysis)) if analysis else None, "ai_summary": {"category": parsed.get("issue_category") or complaint.issue_category, "urgency": parsed.get("urgency") or complaint.urgency, "priority": parsed.get("priority") or complaint.priority, "sentiment": parsed.get("sentiment") or complaint.sentiment, "summary": parsed.get("primary_issue") or complaint.title, "suggested_action": parsed.get("recommended_action") or (parsed.get("resolution_steps") or [""])[0], "guidance": parsed.get("agent_guidance") or ""}, "session_id": session.uuid if session else complaint.source_session_uuid}


@router.post("/complaints/{complaint_id}/reply")
def reply(complaint_id: int, payload: dict, request: Request, db: Session = Depends(get_db), user: User = Depends(require_agent)):
    complaint = _get_assigned(db, complaint_id, user)
    text = str(payload.get("message") or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="Message is required")
    if len(text) > 5000:
        raise HTTPException(status_code=422, detail="Message is too long")
    session = _ensure_session(db, complaint)
    row = AssistantMessage(session_id=session.id, role="assistant", text=text, language="en", modality="text", meta={"sender_type":"agent", "sender_id":user.id, "sender_name":user.full_name, "complaint_id":complaint.id})
    db.add(row)
    previous = complaint.status
    if complaint.status in {"NEW", "ASSIGNED", "ANALYZED", "MANUAL_REVIEW", "PENDING", "WAITING_CUSTOMER"}:
        complaint.status = "IN_PROGRESS"
    complaint.updated_at = utcnow()
    db.add(ComplaintHistory(complaint_id=complaint.id, from_status=previous, to_status=complaint.status, note=f"Agent replied: {text[:250]}", actor_id=user.id))
    db.commit()
    db.refresh(row)
    log_action(db, "complaint.agent_replied", "complaint", complaint.code, {"message_id": row.id}, user=user, request=request)
    return _message_dict(row)


@router.post("/complaints/{complaint_id}/action")
def action(complaint_id: int, payload: dict, request: Request, db: Session = Depends(get_db), user: User = Depends(require_agent)):
    complaint = _get_assigned(db, complaint_id, user)
    action_name = str(payload.get("action") or "").lower().strip()
    message = str(payload.get("message") or "").strip()
    allowed = {"approve", "reject", "request_info", "resolve", "escalate", "reopen", "set_status"}
    STATUS_CHOICES = {"PENDING", "IN_PROGRESS", "WAITING_CUSTOMER", "ESCALATED", "RESOLVED", "REJECTED", "CLOSED"}
    new_status = str(payload.get("status") or "").upper().strip()
    if action_name == "set_status" and new_status not in STATUS_CHOICES:
        raise HTTPException(status_code=422, detail="Unsupported status")
    if action_name not in allowed:
        raise HTTPException(status_code=422, detail="Unsupported agent action")
    if action_name in {"reject", "request_info", "escalate", "resolve"} and not message:
        raise HTTPException(status_code=422, detail="A message/reason is required for this action")
    session = _ensure_session(db, complaint)
    labels = {"approve":"Approved", "reject":"Rejected", "request_info":"More information requested", "resolve":"Resolved", "escalate":"Escalated", "reopen":"Reopened", "set_status":f"Status changed to {new_status.replace('_', ' ').title()}"}
    row = AssistantMessage(session_id=session.id, role="assistant", text=message or labels[action_name], language="en", modality="text", meta={"sender_type":"agent", "sender_id":user.id, "sender_name":user.full_name, "action":action_name, "complaint_id":complaint.id})
    db.add(row)
    previous = complaint.status
    if action_name == "approve":
        complaint.status = "IN_PROGRESS"
    elif action_name == "reject":
        complaint.status = "REJECTED"; complaint.rejection_reason = message
    elif action_name == "request_info":
        complaint.status = "WAITING_CUSTOMER"
    elif action_name == "resolve":
        complaint.status = "RESOLVED"; complaint.resolution_text = message
    elif action_name == "escalate":
        complaint.status = "ESCALATED"
    elif action_name == "reopen":
        complaint.status = "IN_PROGRESS"
    elif action_name == "set_status":
        complaint.status = new_status
        if new_status == "RESOLVED" and message:
            complaint.resolution_text = message
    complaint.updated_at = utcnow()
    db.add(ComplaintHistory(complaint_id=complaint.id, from_status=previous, to_status=complaint.status, note=f"{labels[action_name]}: {message[:500]}", actor_id=user.id))
    db.commit(); db.refresh(row)
    log_action(db, f"complaint.agent_{action_name}", "complaint", complaint.code, {"message_id": row.id}, user=user, request=request)
    return {"message": _message_dict(row), "status": complaint.status, "complaint": complaint_brief(complaint)}


@router.get("/complaints/{complaint_id}/messages")
def messages(complaint_id: int, db: Session = Depends(get_db), user: User = Depends(require_agent)):
    complaint = _get_assigned(db, complaint_id, user)
    if not complaint.source_session_uuid:
        return []
    session = db.query(AssistantSession).filter(AssistantSession.uuid == complaint.source_session_uuid).first()
    if not session:
        return []
    rows = db.query(AssistantMessage).filter(AssistantMessage.session_id == session.id).order_by(AssistantMessage.id.asc()).all()
    return [_message_dict(r) for r in rows]
