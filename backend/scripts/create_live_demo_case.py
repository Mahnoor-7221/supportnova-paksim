"""Create one non-dataset end-to-end demo case for Customer -> AI -> Agent -> Customer.

Idempotent by complaint title. Uses the offline baseline when invoked with
AI_PROVIDER=offline, so it is safe for local demos without an external key.
"""
from __future__ import annotations

import uuid
from datetime import timedelta

from app.database import SessionLocal
from app.models import Complaint, ComplaintHistory, User
from app.models_nova import AssistantMessage, AssistantSession, SatisfactionFeedback
from app.services.analysis_service import analyze_complaint
from app.python_validation import run_validation
from app.utils import utcnow

TITLE = "Demo: Customer Agent Handoff"


def main() -> None:
    db = SessionLocal()
    try:
        customer = db.query(User).filter(User.email == "customer@supportnova.demo").one()
        agent = db.query(User).filter(User.email == "agent@supportnova.demo").one()
        complaint = db.query(Complaint).filter(Complaint.title == TITLE).first()
        if complaint is None:
            complaint = Complaint(
                code="TMP",
                title=TITLE,
                description="My monthly data package is active but mobile internet is not working. Please investigate and resolve the service issue.",
                customer_type="retail",
                product_or_service="Mobile Internet",
                order_reference="PKSIM-DEMO-001",
                channel="web",
                complaint_date=utcnow(),
                requested_resolution="Restore the service or explain the verified resolution.",
                previous_complaints=0,
                customer_id=customer.id,
                created_by=customer.id,
                status="NEW",
                is_dataset_case=False,
                sla_due_at=utcnow() + timedelta(hours=48),
            )
            db.add(complaint)
            db.flush()
            complaint.code = f"CMP-{complaint.id:05d}"
            db.add(ComplaintHistory(complaint_id=complaint.id, from_status="", to_status="NEW", note="Live demo complaint submitted by customer", actor_id=customer.id))
            db.commit()
            db.refresh(complaint)

        # Refresh AI/validation evidence only when missing.
        if not complaint.analyses:
            analyze_complaint(db, complaint, customer.id)
        if not complaint.validations and complaint.analyses:
            run_validation(db, complaint, complaint.analyses[-1], customer.id)

        complaint.assigned_agent_id = agent.id
        previous = complaint.status
        complaint.status = "ASSIGNED"
        db.add(ComplaintHistory(complaint_id=complaint.id, from_status=previous, to_status="ASSIGNED", note=f"Assigned to {agent.full_name}", actor_id=agent.id))

        if not complaint.source_session_uuid:
            session = AssistantSession(uuid=str(uuid.uuid4()), user_id=customer.id)
            db.add(session)
            db.flush()
            complaint.source_session_uuid = session.uuid
        else:
            session = db.query(AssistantSession).filter(AssistantSession.uuid == complaint.source_session_uuid).first()
            if session is None:
                session = AssistantSession(uuid=complaint.source_session_uuid, user_id=customer.id)
                db.add(session)
                db.flush()

        existing_agent_message = db.query(AssistantMessage).filter(
            AssistantMessage.session_id == session.id,
            AssistantMessage.meta['sender_type'].as_string() == 'agent',
        ).first()
        if existing_agent_message is None:
            db.add(AssistantMessage(
                session_id=session.id,
                role="assistant",
                text="I have reviewed your complaint and will resolve the verified mobile internet issue according to the applicable policy.",
                language="en",
                modality="text",
                meta={"sender_type": "agent", "sender_id": agent.id, "sender_name": agent.full_name, "complaint_id": complaint.id},
            ))

        complaint.status = "RESOLVED"
        complaint.resolution_text = "The complaint was reviewed by the assigned agent and resolved using the verified support workflow."
        db.add(ComplaintHistory(complaint_id=complaint.id, from_status="ASSIGNED", to_status="RESOLVED", note="Agent resolved the live demo case", actor_id=agent.id))
        feedback = db.query(SatisfactionFeedback).filter_by(complaint_id=complaint.id, customer_id=customer.id).first()
        if feedback is None:
            db.add(SatisfactionFeedback(complaint_id=complaint.id, customer_id=customer.id, rating=5, comment="Demo customer feedback after agent resolution."))
        db.commit()
        print({"complaint": complaint.code, "status": complaint.status, "customer_id": customer.id, "agent_id": agent.id, "source_session": complaint.source_session_uuid})
    finally:
        db.close()


if __name__ == "__main__":
    main()
