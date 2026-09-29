"""Policy registry endpoints."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..audit import log_action
from ..database import get_db
from ..models import Document, Policy, User
from ..schemas import PolicyCreate
from ..security import get_current_user, require_admin
from ..serializers import policy_dict

router = APIRouter(prefix="/api/policies", tags=["policies"])


@router.get("")
def list_policies(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    active_only: bool = False,
):
    query = db.query(Policy)
    if active_only:
        query = query.filter(Policy.is_active.is_(True))
    policies = query.order_by(Policy.policy_id).all()
    results = []
    for policy in policies:
        data = policy_dict(policy)
        document = db.get(Document, policy.document_id) if policy.document_id else None
        data["document_code"] = document.code if document else None
        data["document_title"] = document.title if document else None
        results.append(data)
    return results


@router.post("", status_code=201)
def create_policy(
    payload: PolicyCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    existing = db.query(Policy).filter(Policy.policy_id == payload.policy_id).first()
    if existing is not None:
        raise HTTPException(status_code=409, detail=f"Policy '{payload.policy_id}' already exists")
    if payload.document_id is not None and db.get(Document, payload.document_id) is None:
        raise HTTPException(status_code=400, detail="Referenced document does not exist")

    policy = Policy(
        policy_id=payload.policy_id.strip(),
        title=payload.title,
        document_id=payload.document_id,
        version=payload.version,
        section=payload.section,
        summary=payload.summary,
        is_active=True,
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    log_action(db, "policy.created", "policy", policy.policy_id, {}, user=admin, request=request)
    return policy_dict(policy)


@router.put("/{policy_id}")
def update_policy(
    policy_id: str,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    policy = db.query(Policy).filter(Policy.policy_id == policy_id).first()
    if policy is None:
        raise HTTPException(status_code=404, detail="Policy not found")
    for field in ("title", "version", "section", "summary", "is_active"):
        if field in payload and payload[field] is not None:
            setattr(policy, field, payload[field])
    db.commit()
    log_action(db, "policy.updated", "policy", policy.policy_id, {"fields": list(payload.keys())},
               user=admin, request=request)
    return policy_dict(policy)
