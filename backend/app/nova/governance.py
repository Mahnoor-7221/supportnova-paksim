"""Human governance (Phase 22): three resolution modes, never bypassed.

    AUTO_RESOLVE          — only low-risk, strongly verified cases
    HUMAN_APPROVAL         — default for anything uncertain
    MANDATORY_ESCALATION   — safety, fraud, legal, high-value, privacy/security

A kill switch (``NOVA_AUTO_RESOLVE_ENABLED=false``) disables autonomous
resolution globally regardless of any other signal.
"""
from __future__ import annotations

from ..config import settings

MANDATORY_ESCALATION_TRIGGERS = {
    "safety_issue", "fraud_indication", "prompt_injection",
}


def decide_resolution_mode(*, trust_decision: str, trust_score: int, risk_level: str,
                           evidence_status: str, escalation_triggers: list[str], fraud_decision: str,
                           estimated_amount: float = 0.0) -> dict:
    triggers = set(escalation_triggers or [])
    reasons: list[str] = []

    mandatory = triggers & MANDATORY_ESCALATION_TRIGGERS
    if mandatory:
        reasons.append(f"mandatory escalation trigger(s): {', '.join(sorted(mandatory))}")
        return {"mode": "MANDATORY_ESCALATION", "reasons": reasons, "auto_resolve_eligible": False}
    if evidence_status == "CONFLICT":
        reasons.append("unresolved conflicting evidence")
        return {"mode": "MANDATORY_ESCALATION", "reasons": reasons, "auto_resolve_eligible": False}
    if fraud_decision == "Potential Abuse Pattern":
        reasons.append("suspected fraud/abuse pattern")
        return {"mode": "MANDATORY_ESCALATION", "reasons": reasons, "auto_resolve_eligible": False}
    if estimated_amount > settings.nova_financial_approval_threshold:
        reasons.append(f"financial impact {estimated_amount:.2f} exceeds approval threshold "
                       f"{settings.nova_financial_approval_threshold:.2f}")
        return {"mode": "HUMAN_APPROVAL", "reasons": reasons, "auto_resolve_eligible": False}

    if not settings.nova_auto_resolve_enabled:
        reasons.append("autonomous resolution disabled by configuration (kill switch)")
        return {"mode": "HUMAN_APPROVAL", "reasons": reasons, "auto_resolve_eligible": False}

    eligible = (trust_decision == "VERIFIED" and trust_score >= settings.nova_auto_resolve_min_trust
               and risk_level == "Low" and evidence_status in {"SUPPORTED", "NOT_REQUIRED"} and not triggers)
    if eligible:
        reasons.append(f"trust={trust_score}>={settings.nova_auto_resolve_min_trust}, risk=Low, no escalation triggers")
        return {"mode": "AUTO_RESOLVE", "reasons": reasons, "auto_resolve_eligible": True}

    if trust_score < settings.nova_auto_resolve_min_trust:
        reasons.append(f"trust score {trust_score} below auto-resolve threshold {settings.nova_auto_resolve_min_trust}")
    if risk_level != "Low":
        reasons.append(f"risk level {risk_level}")
    if evidence_status not in {"SUPPORTED", "NOT_REQUIRED"}:
        reasons.append(f"evidence status {evidence_status}")
    return {"mode": "HUMAN_APPROVAL", "reasons": reasons, "auto_resolve_eligible": False}
