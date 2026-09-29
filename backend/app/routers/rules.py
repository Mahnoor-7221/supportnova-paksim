"""Rule matrix endpoints (deterministic ground truth management)."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..audit import log_action
from ..database import get_db
from ..models import ComplaintRule, User
from ..schemas import RuleCreate, RuleUpdate
from ..security import get_current_user, require_admin

router = APIRouter(prefix="/api/rules", tags=["rules"])


def _rule_dict(rule: ComplaintRule) -> dict:
    return {
        "id": rule.id,
        "rule_id": rule.rule_id,
        "category": rule.category,
        "subcategory": rule.subcategory,
        "conditions": rule.conditions or {},
        "keywords": rule.keywords or [],
        "department": rule.department,
        "urgency": rule.urgency,
        "priority": rule.priority,
        "policy_id": rule.policy_id,
        "escalation": rule.escalation,
        "escalation_reason": rule.escalation_reason,
        "escalation_department": rule.escalation_department,
        "required_actions": rule.required_actions or [],
        "prohibited_actions": rule.prohibited_actions or [],
        "follow_up": rule.follow_up,
        "response_template": rule.response_template,
        "is_active": rule.is_active,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
    }


@router.get("")
def list_rules(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    category: Optional[str] = None,
    active_only: bool = False,
):
    query = db.query(ComplaintRule)
    if category:
        query = query.filter(ComplaintRule.category == category)
    if active_only:
        query = query.filter(ComplaintRule.is_active.is_(True))
    return [_rule_dict(rule) for rule in query.order_by(ComplaintRule.rule_id).all()]


@router.post("", status_code=201)
def create_rule(
    payload: RuleCreate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    rule_id = (payload.rule_id or "").strip()
    if not rule_id:
        prefix = (payload.category or "GEN")[:3].upper()
        count = db.query(ComplaintRule).filter(ComplaintRule.rule_id.like(f"{prefix}-%")).count()
        rule_id = f"{prefix}-{count + 1:03d}"
    if db.query(ComplaintRule).filter(ComplaintRule.rule_id == rule_id).first():
        raise HTTPException(status_code=409, detail=f"Rule '{rule_id}' already exists")

    rule = ComplaintRule(
        rule_id=rule_id,
        category=payload.category,
        subcategory=payload.subcategory,
        conditions=payload.conditions,
        keywords=payload.keywords,
        department=payload.department,
        urgency=payload.urgency,
        priority=payload.priority,
        policy_id=payload.policy_id,
        escalation=payload.escalation,
        escalation_reason=payload.escalation_reason,
        escalation_department=payload.escalation_department,
        required_actions=payload.required_actions,
        prohibited_actions=payload.prohibited_actions,
        follow_up=payload.follow_up,
        response_template=payload.response_template,
        is_active=payload.is_active,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    log_action(db, "rule.created", "rule", rule.rule_id, {}, user=admin, request=request)
    return _rule_dict(rule)


@router.put("/{rule_id}")
def update_rule(
    rule_id: str,
    payload: RuleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    rule = db.query(ComplaintRule).filter(ComplaintRule.rule_id == rule_id).first()
    if rule is None:
        raise HTTPException(status_code=404, detail="Rule not found")

    updates = payload.model_dump(exclude_unset=True)
    for field, value in updates.items():
        if value is not None:
            setattr(rule, field, value)
    db.commit()
    db.refresh(rule)
    log_action(db, "rule.updated", "rule", rule.rule_id, {"fields": list(updates.keys())},
               user=admin, request=request)
    return _rule_dict(rule)
