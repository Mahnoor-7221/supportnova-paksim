"""Security timeline events.

Thin helper around the SecurityEvent table. Events are recorded from real
detections only (injection scans, quarantines, Trust Gate blocks, security
suite runs, red-team simulations). The helper never commits — the caller
controls the transaction — and it de-duplicates repeated events for the same
entity so re-running an analysis does not spam the timeline.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from ..models import Complaint, Document, SecurityEvent

SEVERITIES = ("critical", "high", "medium", "info")


def log_security_event(
    db: Session,
    event_type: str,
    title: str,
    *,
    severity: str = "info",
    complaint: Optional[Complaint] = None,
    document: Optional[Document] = None,
    detail: Optional[dict] = None,
    dedupe: bool = True,
) -> Optional[SecurityEvent]:
    """Add a security event to the session (no commit). Returns None if deduped."""
    if severity not in SEVERITIES:
        severity = "info"

    if dedupe:
        query = db.query(SecurityEvent).filter(SecurityEvent.event_type == event_type)
        if complaint is not None:
            query = query.filter(SecurityEvent.complaint_id == complaint.id)
        if document is not None:
            query = query.filter(SecurityEvent.document_id == document.id)
        if query.first() is not None:
            return None

    event = SecurityEvent(
        event_type=event_type,
        severity=severity,
        complaint_id=complaint.id if complaint is not None else None,
        document_id=document.id if document is not None else None,
        title=title[:255],
        detail=detail or {},
    )
    db.add(event)
    return event


def serialize_event(event: SecurityEvent) -> dict:
    return {
        "id": event.id,
        "event_type": event.event_type,
        "severity": event.severity,
        "title": event.title,
        "detail": event.detail or {},
        "complaint_id": event.complaint_id,
        "complaint_code": event.complaint.code if event.complaint is not None else None,
        "document_id": event.document_id,
        "created_at": event.created_at.isoformat() if event.created_at else None,
    }
