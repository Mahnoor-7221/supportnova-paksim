"""Predictive Complaint Intelligence (Phase 11), Anomaly Detection (Phase 12)
and a lightweight Digital Twin / Support Simulator (Phase 27).

All numbers are computed from the actual complaint table at request time --
nothing is precomputed/faked. Explanations are always attached to a number.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import timedelta

from sqlalchemy.orm import Session

from ..config import settings
from ..models import Complaint
from ..utils import utcnow


def _window_counts(db: Session, days: int, field: str) -> Counter:
    since = utcnow() - timedelta(days=days)
    rows = db.query(getattr(Complaint, field)).filter(Complaint.created_at >= since).all()
    return Counter(r[0] for r in rows if r[0])


def early_warning(db: Session) -> dict:
    recent = _window_counts(db, 7, "issue_category")
    prior = _window_counts(db, 14, "issue_category")
    prior = Counter({k: v - recent.get(k, 0) for k, v in prior.items()})
    warnings = []
    for category, count in recent.items():
        baseline = max(prior.get(category, 0), 1)
        change = (count - baseline) / baseline
        if count >= 5 and change >= 0.5:
            warnings.append({
                "category": category, "recent_7d": count, "previous_7d": prior.get(category, 0),
                "change_pct": round(change * 100, 1),
                "message": f"{category} complaints increased {change * 100:.0f}% over the last 7 days "
                          f"({prior.get(category, 0)} -> {count}).",
                "confidence": "medium" if count < 15 else "high",
            })
    dept_recent = _window_counts(db, 7, "department")
    for dept, count in dept_recent.items():
        if count >= 8:
            warnings.append({"category": f"department:{dept}", "recent_7d": count, "previous_7d": None,
                             "change_pct": None,
                             "message": f"{dept} has an unusually high complaint volume this week ({count} cases).",
                             "confidence": "medium"})
    warnings.sort(key=lambda w: w.get("change_pct") or 0, reverse=True)
    return {"warnings": warnings, "window_days": 7, "generated_at": utcnow().isoformat()}


def anomaly_detection(db: Session) -> dict:
    by_day = defaultdict(int)
    since = utcnow() - timedelta(days=30)
    for (created,) in db.query(Complaint.created_at).filter(Complaint.created_at >= since).all():
        if created:
            by_day[created.date().isoformat()] += 1
    values = list(by_day.values())
    if not values:
        return {"anomalies": [], "baseline": {}, "note": "not enough data"}
    mean = sum(values) / len(values)
    variance = sum((v - mean) ** 2 for v in values) / len(values)
    stdev = variance ** 0.5 or 1.0
    anomalies = []
    for day, count in sorted(by_day.items()):
        z = (count - mean) / stdev
        if abs(z) >= 2.0:
            anomalies.append({
                "date": day, "current_behavior": count, "normal_baseline": round(mean, 1),
                "deviation": round(z, 2),
                "possible_explanation": "Volume spike -- investigate category/department breakdown for that day."
                                       if z > 0 else "Unusually quiet day -- check for an intake or reporting issue.",
                "confidence": "medium",
                "label": "statistical deviation -- not proof of fraud or a specific cause",
            })
    return {"anomalies": anomalies, "baseline": {"mean_per_day": round(mean, 1), "stdev": round(stdev, 2)},
           "window_days": 30}


DIGITAL_TWIN_LEVERS = {
    "complaint_volume_increase_pct": 0.0, "staff_reduction_pct": 0.0, "policy_change": "",
    "sla_change_hours": 0, "regional_spike_category": "",
}


def digital_twin_simulate(db: Session, levers: dict) -> dict:
    """Simulation only -- never mutates real data."""
    current_open = db.query(Complaint).filter(Complaint.status.notin_(["RESOLVED", "CLOSED"])).count()
    current_total = db.query(Complaint).count() or 1
    volume_pct = float(levers.get("complaint_volume_increase_pct") or 0)
    staff_pct = float(levers.get("staff_reduction_pct") or 0)
    sla_change = float(levers.get("sla_change_hours") or 0)

    projected_volume = round(current_open * (1 + volume_pct / 100))
    capacity_factor = max(0.1, 1 - staff_pct / 100)
    workload_multiplier = round((1 + volume_pct / 100) / capacity_factor, 2)
    resolution_time_multiplier = round(workload_multiplier, 2)
    escalation_risk = "high" if workload_multiplier >= 1.5 else "medium" if workload_multiplier >= 1.15 else "low"
    projected_cost = round(projected_volume * settings.nova_support_cost_per_contact * workload_multiplier, 2)

    return {
        "inputs": levers, "current_open_complaints": current_open,
        "projected_open_complaints": projected_volume, "workload_multiplier": workload_multiplier,
        "resolution_time_multiplier": resolution_time_multiplier, "escalation_risk": escalation_risk,
        "projected_support_cost": projected_cost, "currency": settings.nova_currency,
        "sla_note": (f"SLA target changed by {sla_change:+.0f}h; effective pressure "
                    f"{'increases' if sla_change < 0 else 'eases'} accordingly.") if sla_change else "No SLA change modelled.",
        "label": "SIMULATION -- projected impact only, not a forecast guarantee",
    }
