"""Administration endpoints: users, departments, categories, audit logs, prompts."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from sqlalchemy import func, or_

from ..audit import log_action
from ..database import get_db
from ..models import (
    AuditLog,
    Complaint,
    ComplaintCategory,
    Department,
    PromptVersion,
    Role,
    User,
)
from ..schemas import UserCreate
from ..security import get_current_user, hash_password, require_admin, require_staff
from ..serializers import audit_dict, user_dict
from ..services.genai_client import provider_status
from ..utils import utcnow

router = APIRouter(prefix="/api", tags=["admin"])


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@router.get("/users")
def list_users(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    return [user_dict(user) for user in db.query(User).order_by(User.id).all()]


@router.post("/users", status_code=201)
def create_user(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    email = payload.email.strip().lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="A user with this email already exists")
    role = db.query(Role).filter(Role.name == payload.role).first()
    if role is None:
        raise HTTPException(status_code=400, detail=f"Unknown role '{payload.role}'")

    user = User(
        email=email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role_id=role.id,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    log_action(db, "user.created", "user", user.id, {"email": email, "role": payload.role},
               user=admin, request=request)
    return user_dict(user)


@router.put("/users/{user_id}")
def update_user(
    user_id: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if "is_active" in payload:
        user.is_active = bool(payload["is_active"])
    if "full_name" in payload:
        user.full_name = str(payload["full_name"])
    if payload.get("password"):
        user.password_hash = hash_password(str(payload["password"]))
    db.commit()
    log_action(db, "user.updated", "user", user.id, {"fields": list(payload.keys())},
               user=admin, request=request)
    return user_dict(user)


# ---------------------------------------------------------------------------
# Departments / categories
# ---------------------------------------------------------------------------

@router.get("/departments")
def list_departments(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    complaints = db.query(Complaint).all()
    users = db.query(User).all()
    result = []
    for d in db.query(Department).order_by(Department.name).all():
        name = d.name
        relevant = [c for c in complaints if (c.verified_department or c.department) == name]
        open_rows = [c for c in relevant if c.status not in {"RESOLVED", "CLOSED"}]
        assigned = [c for c in open_rows if c.assigned_agent_id is not None]
        unassigned = [c for c in open_rows if c.assigned_agent_id is None]
        escalated = [c for c in relevant if c.status == "ESCALATED"]
        sla_risk = [c for c in open_rows if c.sla_due_at and c.sla_due_at < utcnow()]
        agent_count = sum(1 for u in users if u.role and u.role.name == "agent")
        result.append({
            "id": d.id, "name": name, "description": d.description,
            "is_escalation_target": d.is_escalation_target,
            "total_complaints": len(relevant), "open_complaints": len(open_rows),
            "assigned_complaints": len(assigned), "unassigned_complaints": len(unassigned),
            "escalated_complaints": len(escalated), "sla_risk": len(sla_risk),
            "agent_count": agent_count,
        })
    return result


@router.post("/departments", status_code=201)
def create_department(
    payload: dict, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin),
):
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Department name is required")
    if db.query(Department).filter(Department.name == name).first():
        raise HTTPException(status_code=409, detail="Department already exists")
    department = Department(name=name, description=str(payload.get("description") or ""),
                            is_escalation_target=bool(payload.get("is_escalation_target")))
    db.add(department); db.commit(); db.refresh(department)
    log_action(db, "department.created", "department", department.id, {"name": name}, user=admin, request=request)
    return {"id": department.id, "name": department.name, "description": department.description,
            "is_escalation_target": department.is_escalation_target}


@router.get("/categories")
def list_categories(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    complaints = db.query(Complaint).all()
    result = []
    for c in db.query(ComplaintCategory).order_by(ComplaintCategory.name).all():
        relevant = [x for x in complaints if (x.verified_category or x.issue_category) == c.name]
        open_rows = [x for x in relevant if x.status not in {"RESOLVED", "CLOSED"}]
        escalated = [x for x in relevant if x.status == "ESCALATED"]
        now = utcnow()
        sla_breach = [x for x in open_rows if x.sla_due_at and x.sla_due_at < now]
        dept = c.default_department
        result.append({
            "id": c.id, "name": c.name, "description": c.description, "sla_hours": c.sla_hours,
            "keywords": c.keywords or [], "department_id": c.default_department_id,
            "department_name": dept.name if dept else "", "total_complaints": len(relevant),
            "open_complaints": len(open_rows), "escalated_complaints": len(escalated),
            "sla_breaches": len(sla_breach), "active": True,
        })
    return result


@router.post("/categories", status_code=201)
def create_category(
    payload: dict, request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin),
):
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Category name is required")
    if db.query(ComplaintCategory).filter(ComplaintCategory.name == name).first():
        raise HTTPException(status_code=409, detail="Category already exists")
    department_id = payload.get("default_department_id")
    if department_id is not None and db.get(Department, int(department_id)) is None:
        raise HTTPException(status_code=400, detail="Default department not found")
    category = ComplaintCategory(name=name, description=str(payload.get("description") or ""),
                                 sla_hours=max(1, int(payload.get("sla_hours") or 72)),
                                 keywords=payload.get("keywords") or [],
                                 default_department_id=int(department_id) if department_id is not None else None)
    db.add(category); db.commit(); db.refresh(category)
    log_action(db, "category.created", "category", category.id, {"name": name}, user=admin, request=request)
    return {"id": category.id, "name": category.name, "description": category.description,
            "sla_hours": category.sla_hours, "keywords": category.keywords or [],
            "default_department_id": category.default_department_id}


# ---------------------------------------------------------------------------
# Audit logs & prompts
# ---------------------------------------------------------------------------

@router.get("/audit-logs")
def audit_logs(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
    action: Optional[str] = None,
    entity_type: Optional[str] = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action.like(f"%{action}%"))
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    total = query.count()
    rows = query.order_by(AuditLog.id.desc()).offset(offset).limit(limit).all()
    return {"total": total, "items": [audit_dict(entry) for entry in rows]}


@router.get("/prompts")
def list_prompts(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    rows = db.query(PromptVersion).order_by(PromptVersion.name, PromptVersion.version).all()
    return {
        "provider": provider_status(),
        "prompts": [
            {
                "id": row.id,
                "name": row.name,
                "version": row.version,
                "file_path": row.file_path,
                "is_active": row.is_active,
                "checksum": row.checksum,
                "notes": row.notes,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ],
    }


@router.get("/system/status")
def system_status(db: Session = Depends(get_db), user: User = Depends(require_staff)):
    return {
        "app": "SupportNova",
        "provider": provider_status(),
        "counts": {
            "complaints": db.query(Complaint).count(),
            "users": db.query(User).count(),
        },
    }
