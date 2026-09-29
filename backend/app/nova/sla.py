"""SLA Intelligence (Phase 16). Builds on the v1 sla_due_at field — adds a
transparent status classification, breach prediction and explanation.
"""
from __future__ import annotations

from ..models import Complaint
from ..utils import utcnow

RESOLVED_STATES = {"RESOLVED", "CLOSED"}


def sla_status(complaint: Complaint) -> dict:
    if complaint.sla_due_at is None:
        return {"status": "UNKNOWN", "reason": "No SLA due date recorded for this complaint.", "hours_remaining": None}
    now = utcnow()
    remaining = (complaint.sla_due_at - now).total_seconds() / 3600
    if complaint.status in RESOLVED_STATES:
        return {"status": "SAFE", "reason": "Complaint already resolved/closed.", "hours_remaining": round(remaining, 1)}
    if remaining < 0:
        return {"status": "BREACHED", "reason": f"SLA due date passed {abs(remaining):.1f}h ago.",
                "hours_remaining": round(remaining, 1)}
    if remaining <= 24:
        return {"status": "AT_RISK", "reason": f"Only {remaining:.1f}h remain before the SLA deadline.",
                "hours_remaining": round(remaining, 1)}
    return {"status": "SAFE", "reason": f"{remaining:.1f}h remain before the SLA deadline.",
            "hours_remaining": round(remaining, 1)}
