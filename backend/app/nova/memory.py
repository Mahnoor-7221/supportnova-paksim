"""AI Memory / Case Memory (Phase 23) + Feedback Learning Loop (Phase 24).

Scopes are kept strictly separate: ``session`` (this chat/voice session only),
``customer_case`` (this complaint/customer only) and ``organization`` (shared
facts such as policy summaries — never personal data). Nothing here silently
retrains a model; feedback is recorded and aggregated for the dashboard only.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from ..models_nova import AIFeedback, CaseMemory, Investigation

FEEDBACK_VERDICTS = {"correct", "incorrect", "modified", "unsafe", "missing_evidence"}


def remember(db: Session, *, scope: str, key: str, value: str, source: str, owner_user_id: Optional[int] = None,
            complaint_id: Optional[int] = None, session_uuid: str = "") -> CaseMemory:
    if scope not in {"session", "customer_case", "organization"}:
        raise ValueError("invalid memory scope")
    row = CaseMemory(scope=scope, owner_user_id=owner_user_id, complaint_id=complaint_id,
                     session_uuid=session_uuid, key=key[:120], value=value, source=source)
    db.add(row)
    return row


def recall(db: Session, *, scope: str, owner_user_id: Optional[int] = None, complaint_id: Optional[int] = None,
          session_uuid: str = "", limit: int = 50) -> list[dict]:
    q = db.query(CaseMemory).filter(CaseMemory.scope == scope)
    if owner_user_id is not None:
        q = q.filter(CaseMemory.owner_user_id == owner_user_id)
    if complaint_id is not None:
        q = q.filter(CaseMemory.complaint_id == complaint_id)
    if session_uuid:
        q = q.filter(CaseMemory.session_uuid == session_uuid)
    rows = q.order_by(CaseMemory.id.desc()).limit(limit).all()
    return [{"key": r.key, "value": r.value, "source": r.source, "created_at": r.created_at.isoformat() if r.created_at else None}
           for r in rows]


def memory_visibility(db: Session, complaint_id: int, session_uuid: str = "", owner_user_id: Optional[int] = None) -> dict:
    """'What information is being used?' — for the transparency panel."""
    return {
        "customer_case": recall(db, scope="customer_case", complaint_id=complaint_id),
        "session": recall(db, scope="session", session_uuid=session_uuid, owner_user_id=owner_user_id) if session_uuid else [],
        "organization": recall(db, scope="organization", limit=10),
    }


def submit_feedback(db: Session, investigation: Investigation, verdict: str, target: str, notes: str,
                    user_id: Optional[int]) -> AIFeedback:
    if verdict not in FEEDBACK_VERDICTS:
        raise ValueError(f"verdict must be one of {sorted(FEEDBACK_VERDICTS)}")
    row = AIFeedback(investigation_id=investigation.id, complaint_id=investigation.complaint_id, verdict=verdict,
                     target=target, notes=notes, created_by=user_id)
    db.add(row)
    return row


def feedback_dashboard(db: Session) -> dict:
    rows = db.query(AIFeedback).all()
    total = len(rows) or 1
    from collections import Counter
    verdicts = Counter(r.verdict for r in rows)
    investigations = db.query(Investigation).all()
    inv_total = len(investigations) or 1
    human_overrides = sum(1 for i in investigations if i.human_decision and i.human_decision != i.final_decision)
    blocked = sum(1 for i in investigations if i.trust_decision == "BLOCKED")
    return {
        "total_feedback": len(rows),
        "ai_accuracy": round(100.0 * verdicts.get("correct", 0) / total, 1),
        "correction_rate": round(100.0 * (verdicts.get("incorrect", 0) + verdicts.get("modified", 0)) / total, 1),
        "unsafe_rate": round(100.0 * verdicts.get("unsafe", 0) / total, 1),
        "missing_evidence_rate": round(100.0 * verdicts.get("missing_evidence", 0) / total, 1),
        "human_override_rate": round(100.0 * human_overrides / inv_total, 1),
        "blocked_response_rate": round(100.0 * blocked / inv_total, 1),
        "verdict_breakdown": dict(verdicts),
        "common_failure_types": [k for k, _ in Counter(
            f for i in investigations for f in (i.summary or {}).get("risk_flags", [])).most_common(5)],
    }
