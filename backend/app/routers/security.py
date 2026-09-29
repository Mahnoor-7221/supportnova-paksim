"""Security center endpoints: status overview and live test-suite runs."""
from __future__ import annotations

from collections import Counter
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session

from ..audit import log_action
from ..database import get_db
from ..models import (
    AuditLog,
    Complaint,
    Document,
    ManualReview,
    SecurityEvent,
    TrustAssessment,
    User,
)
from ..security import require_admin
from ..serializers import audit_dict, review_dict
from ..services.genai_client import provider_status
from ..services.security_events import log_security_event, serialize_event
from ..services.security_suite import CASES, run_security_suite

router = APIRouter(prefix="/api/security", tags=["security"])


@router.get("/status")
def security_status(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    flagged_documents = db.query(Document).filter(Document.status == "flagged").count()
    open_reviews = db.query(ManualReview).filter(ManualReview.status == "OPEN").count()
    recent_audit = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(15).all()
    return {
        "provider": provider_status(),
        "flagged_documents": flagged_documents,
        "open_manual_reviews": open_reviews,
        "security_test_cases": len(CASES),
        "recent_audit": [audit_dict(entry) for entry in recent_audit],
    }


@router.get("/summary")
def security_summary(db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    """Security Command Center: real threat counters + the live event timeline."""
    assessments = db.query(TrustAssessment).all()
    decisions = Counter(row.decision for row in assessments)

    injected_complaints = db.query(Complaint).filter(Complaint.injection_detected.is_(True)).count()
    quarantined_documents = db.query(Document).filter(Document.status == "flagged").count()
    open_reviews = db.query(ManualReview).filter(ManualReview.status == "OPEN").count()

    event_type_counter = Counter(row[0] for row in db.query(SecurityEvent.event_type).all())
    severity_counter = Counter(row[0] for row in db.query(SecurityEvent.severity).all())
    recent_events = db.query(SecurityEvent).order_by(SecurityEvent.id.desc()).limit(15).all()

    queue_rows = (
        db.query(ManualReview)
        .filter(ManualReview.status == "OPEN")
        .order_by(ManualReview.id.desc())
        .limit(8)
        .all()
    )
    review_queue = []
    for review in queue_rows:
        complaint = db.get(Complaint, review.complaint_id)
        review_queue.append(review_dict(review, complaint))

    return {
        "provider": provider_status(),
        "counts": {
            "prompt_injection_complaints": injected_complaints,
            "quarantined_documents": quarantined_documents,
            "blocked_responses": decisions.get("BLOCKED", 0),
            "review_required_responses": decisions.get("REVIEW_REQUIRED", 0),
            "verified_responses": decisions.get("VERIFIED", 0),
            "open_manual_reviews": open_reviews,
            "total_security_events": sum(event_type_counter.values()),
            "critical_security_events": severity_counter.get("critical", 0),
        },
        "events_by_type": [
            {"name": name, "value": value} for name, value in event_type_counter.most_common()
        ],
        "events_by_severity": [
            {"name": name, "value": value} for name, value in severity_counter.most_common()
        ],
        "recent_events": [serialize_event(event) for event in recent_events],
        "review_queue": review_queue,
        "security_test_cases": {
            "total": len(CASES),
            "categories": sorted({case["category"] for case in CASES}),
        },
    }


@router.get("/events")
def security_events(
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
    limit: int = Query(50, ge=1, le=200),
    event_type: Optional[str] = None,
    severity: Optional[str] = None,
):
    query = db.query(SecurityEvent)
    if event_type:
        query = query.filter(SecurityEvent.event_type == event_type)
    if severity:
        query = query.filter(SecurityEvent.severity == severity)
    total = query.count()
    rows = query.order_by(SecurityEvent.id.desc()).limit(limit).all()
    return {"total": total, "items": [serialize_event(event) for event in rows]}


@router.get("/tests")
def list_tests(admin: User = Depends(require_admin)):
    return [
        {"case_id": case["case_id"], "name": case["name"], "category": case["category"]}
        for case in CASES
    ]


@router.post("/tests/run")
def run_tests(request: Request, db: Session = Depends(get_db), admin: User = Depends(require_admin)):
    report = run_security_suite(db)
    log_security_event(
        db,
        "security_suite_run",
        f"Security suite executed: {report['passed']}/{report['total']} cases passed",
        severity="info" if report["failed"] == 0 else "medium",
        detail={"passed": report["passed"], "failed": report["failed"], "total": report["total"]},
        dedupe=False,
    )
    db.commit()
    log_action(db, "security.tests_run", "system", "security-suite",
               {"passed": report["passed"], "failed": report["failed"]}, user=admin, request=request)
    return report
