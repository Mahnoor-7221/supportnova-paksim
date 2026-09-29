"""Deterministic escalation engine (spec §19).

Escalation is decided by explicit business triggers — not by the model.
"""
from __future__ import annotations

from typing import Optional

from ..models import Complaint, ComplaintRule

TRIGGER_LABELS = {
    "safety_issue": "Safety issue",
    "fraud_indication": "Fraud indication",
    "repeated_unresolved": "Repeated unresolved complaint",
    "sla_breach": "SLA breach",
    "high_risk_customer": "High-risk customer issue",
    "mandatory_policy_escalation": "Mandatory policy escalation",
    "high_urgency": "High urgency / critical priority",
    "management_approval_required": "Management approval required",
    "prompt_injection": "Prompt injection detected",
    "policy_not_found": "Policy not found - manual review required",
}


def evaluate_escalation(
    complaint: Complaint,
    rule: Optional[ComplaintRule],
    signals: Optional[dict] = None,
    injection_detected: bool = False,
    policy_found: bool = True,
) -> dict:
    signals = signals or {}
    triggers: list[str] = []

    if signals.get("mentions_safety"):
        triggers.append("safety_issue")
    if signals.get("mentions_fraud"):
        triggers.append("fraud_indication")

    previous = int(complaint.previous_complaints or 0)
    if previous >= 3 or (previous >= 1 and signals.get("mentions_repeat")):
        triggers.append("repeated_unresolved")

    delay_days = signals.get("delay_days")
    if delay_days is not None and delay_days > 7:
        triggers.append("sla_breach")

    if (complaint.customer_type or "").lower() in {"vip", "enterprise", "business"} and (
        previous >= 2 or signals.get("mentions_repeat")
    ):
        triggers.append("high_risk_customer")

    if rule is not None and rule.escalation:
        triggers.append("mandatory_policy_escalation")

    if rule is not None and (rule.urgency == "Critical" or rule.priority == "P1"):
        triggers.append("high_urgency")

    if signals.get("mentions_manager"):
        triggers.append("management_approval_required")

    if injection_detected:
        triggers.append("prompt_injection")

    if not policy_found and rule is not None and rule.policy_id:
        triggers.append("policy_not_found")

    # de-duplicate preserving order
    triggers = list(dict.fromkeys(triggers))
    required = len(triggers) > 0

    escalation_department = ""
    if rule is not None and rule.escalation_department:
        escalation_department = rule.escalation_department
    elif "fraud_indication" in triggers:
        escalation_department = "Billing & Fraud"
    elif "safety_issue" in triggers:
        escalation_department = "Quality & Safety"
    elif required:
        escalation_department = "Customer Service Management"

    priority = rule.priority if rule is not None else "P3"
    if any(t in triggers for t in ("safety_issue", "fraud_indication")):
        priority = "P1"
    elif required and len(triggers) >= 2:
        priority = "P1" if priority in {"P1", "P2"} else "P2"

    reason = ""
    if required:
        reason = "; ".join(TRIGGER_LABELS.get(t, t) for t in triggers)

    return {
        "required": required,
        "triggers": triggers,
        "reason": reason,
        "department": escalation_department,
        "priority": priority,
    }
