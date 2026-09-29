from __future__ import annotations
from typing import Any, Optional
from fastapi import Request
from sqlalchemy.orm import Session
from .models import AuditLog, User

def log_action(db: Session, action: str, entity_type: str, entity_id: Any, detail: Optional[dict] = None, user: Optional[User] = None, request: Optional[Request] = None):
    ip = None
    if request is not None and request.client:
        ip = request.client.host
    row = AuditLog(user_id=user.id if user else None, actor_email=user.email if user else None,
                   action=action, entity_type=entity_type, entity_id=str(entity_id),
                   detail=detail or {}, ip_address=ip)
    db.add(row)
    try: db.commit()
    except Exception: db.rollback()
    return row
