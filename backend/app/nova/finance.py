"""Financial Impact Engine (Phase 20) + Counterfactual Simulator (Phase 19).

Every number is either taken from an actual record (the transaction amount)
or clearly labelled as an assumption from ``settings``. Nothing is invented.
"""
from __future__ import annotations

from typing import Optional

from ..config import settings
from ..models import Complaint
from ..models_nova import TransactionRecord

ASSUMPTIONS = {
    "support_cost_per_contact": settings.nova_support_cost_per_contact,
    "escalation_cost": settings.nova_escalation_cost,
    "agent_hourly_cost": settings.nova_agent_hourly_cost,
    "compensation_pct_of_order": settings.nova_compensation_pct,
    "currency": settings.nova_currency,
    "note": "Editable defaults in backend/.env — these are modelling assumptions, not measured costs.",
}


def financial_estimate(complaint: Complaint, txn: Optional[TransactionRecord], escalation_required: bool) -> dict:
    order_amount = txn.amount if txn else 0.0
    direct_refund = round(order_amount, 2) if (txn and txn.refund_status in {"requested", "refunded"}) else 0.0
    compensation = round(order_amount * ASSUMPTIONS["compensation_pct_of_order"], 2) if order_amount else 0.0
    support_cost = ASSUMPTIONS["support_cost_per_contact"] * (1 + int(complaint.previous_complaints or 0) * 0.5)
    escalation_cost = ASSUMPTIONS["escalation_cost"] if escalation_required else 0.0
    total = round(direct_refund + support_cost + escalation_cost, 2)
    return {
        "currency": ASSUMPTIONS["currency"], "order_amount": round(order_amount, 2),
        "direct_refund": direct_refund, "potential_compensation": compensation,
        "support_cost": round(support_cost, 2), "escalation_cost": round(escalation_cost, 2),
        "total_estimated_cost": total, "assumptions": ASSUMPTIONS,
        "label": "ESTIMATE — not actual financial data",
    }


SCENARIOS = {
    "refund_approved": {"delta_cost": lambda base: base["order_amount"], "sla_impact": "resolved within SLA",
                        "escalation_risk": "low", "operational_impact": "one refund transaction processed"},
    "refund_rejected": {"delta_cost": lambda base: 0.0, "sla_impact": "resolved, but may reopen if disputed",
                        "escalation_risk": "medium (possible dispute/chargeback)",
                        "operational_impact": "customer response required with clear justification"},
    "human_review": {"delta_cost": lambda base: ASSUMPTIONS["support_cost_per_contact"],
                     "sla_impact": "adds review turnaround time to SLA clock",
                     "escalation_risk": "low", "operational_impact": "1 reviewer touch added to the queue"},
    "escalated": {"delta_cost": lambda base: ASSUMPTIONS["escalation_cost"],
                 "sla_impact": "SLA clock extended by escalation handling time",
                 "escalation_risk": "n/a (already escalated)", "operational_impact": "routed to specialist department"},
    "compensation_given": {"delta_cost": lambda base: base["potential_compensation"],
                           "sla_impact": "resolved with goodwill gesture",
                           "escalation_risk": "low", "operational_impact": "one compensation transaction processed"},
}


def counterfactual_simulation(base: dict) -> dict:
    """"What if?" — clearly labelled estimates, never guaranteed outcomes."""
    out = {}
    for name, spec in SCENARIOS.items():
        out[name] = {
            "estimated_delta_cost": round(spec["delta_cost"](base), 2), "currency": base["currency"],
            "sla_impact": spec["sla_impact"], "escalation_risk": spec["escalation_risk"],
            "operational_impact": spec["operational_impact"],
        }
    return {"scenarios": out, "label": "SIMULATION — estimates only, not guaranteed outcomes", "base": base}
