"""Rule matrix matching — deterministic ground truth extraction.

Given a complaint, this module extracts deterministic signals (delay days,
amounts, previous complaints...), evaluates rule conditions and selects the
best-matching rule. The GenAI output is NEVER used here: routing correctness is
judged against this rule matrix, not against the model.
"""
from __future__ import annotations

import re
from typing import Optional

from sqlalchemy.orm import Session

from ..models import Complaint, ComplaintRule

_AMOUNT = re.compile(r"(?:€|\$|eur|usd|gbp|dkk)\s?(\d{1,6}(?:[.,]\d{1,2})?)|(\d{1,6}(?:[.,]\d{1,2})?)\s?(?:eur|usd|euro|euros|dollars)", re.IGNORECASE)
_DAYS = re.compile(r"(\d{1,3})\s*(?:days?|dage|tage|dias|giorni)\s*(?:late|delay|overdue|ago)?", re.IGNORECASE)
_DAYS_LATE = re.compile(r"(?:late|delay|overdue|waiting|wait)\D{0,20}?(\d{1,3})\s*(?:days?|weeks?)", re.IGNORECASE)
_WEEKS = re.compile(r"(\d{1,2})\s*weeks?\b", re.IGNORECASE)

CATEGORY_ALIASES = {
    "shipping": "Delivery", "logistics": "Delivery", "delivery": "Delivery", "parcel": "Delivery",
    "product": "Product", "item": "Product", "hardware": "Product", "device": "Product",
    "refund": "Refund", "refunds": "Refund", "reimbursement": "Refund",
    "billing": "Billing", "payment": "Billing", "payments": "Billing", "charge": "Billing",
    "warranty": "Warranty", "repair": "Warranty",
    "service": "Service", "support": "Service", "customer service": "Service",
    "account": "Account", "login": "Account", "privacy": "Account", "data": "Account",
    "safety": "Safety", "security": "Safety", "health": "Safety",
    "other": "Other", "general": "Other",
}

DEPARTMENT_ALIASES = {
    "logistics": "Logistics Support", "shipping": "Logistics Support", "delivery": "Logistics Support",
    "customer support": "Customer Support", "support": "Customer Support", "frontline": "Customer Support",
    "product support": "Product Support", "technical support": "Product Support",
    "billing": "Billing & Refunds", "refunds": "Billing & Refunds", "refund": "Billing & Refunds",
    "payments": "Billing & Refunds", "finance": "Billing & Refunds",
    "billing and refunds": "Billing & Refunds",
    "fraud": "Billing & Fraud", "billing and fraud": "Billing & Fraud",
    "warranty": "Warranty Services", "warranty services": "Warranty Services",
    "quality": "Quality & Safety", "safety": "Quality & Safety", "quality and safety": "Quality & Safety",
    "compliance": "Compliance & Legal", "legal": "Compliance & Legal", "compliance and legal": "Compliance & Legal",
    "management": "Customer Service Management", "customer service management": "Customer Service Management",
    "account security": "Account Security", "security": "Account Security", "account": "Account Security",
}


def normalize_category(value: str) -> str:
    key = (value or "").strip().lower()
    return CATEGORY_ALIASES.get(key, (value or "").strip())


def normalize_department(value: str) -> str:
    key = re.sub(r"\s+", " ", (value or "").strip().lower())
    if key in DEPARTMENT_ALIASES:
        return DEPARTMENT_ALIASES[key]
    return (value or "").strip()


def complaint_text(complaint: Complaint) -> str:
    parts = [
        complaint.title or "",
        complaint.description or "",
        complaint.product_or_service or "",
        complaint.requested_resolution or "",
        complaint.order_reference or "",
        # v2: English gloss of a non-English complaint (original text is untouched)
        getattr(complaint, "translated_text", "") or "",
    ]
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Deterministic signal extraction
# ---------------------------------------------------------------------------

def extract_signals(complaint: Complaint, text: Optional[str] = None) -> dict:
    text = text if text is not None else complaint_text(complaint)
    lower = text.lower()

    delay_days: Optional[int] = None
    match = _DAYS_LATE.search(text) or _DAYS.search(text)
    if match:
        try:
            delay_days = int(match.group(1))
        except (TypeError, ValueError):
            delay_days = None
    if delay_days is None:
        match = _WEEKS.search(text)
        if match:
            try:
                delay_days = int(match.group(1)) * 7
            except (TypeError, ValueError):
                delay_days = None

    amount: Optional[float] = None
    match = _AMOUNT.search(text)
    if match:
        raw = match.group(1) or match.group(2)
        try:
            amount = float((raw or "").replace(",", "."))
        except (TypeError, ValueError):
            amount = None

    signals = {
        "delay_days": delay_days,
        "amount": amount,
        "previous_complaints": int(complaint.previous_complaints or 0),
        "customer_type": (complaint.customer_type or "").lower(),
        "has_order": bool((complaint.order_reference or "").strip()),
        "channel": (complaint.channel or "").lower(),
        "mentions_fraud": any(word in lower for word in ["unauthorized", "fraud", "never made", "did not authorize"]),
        "mentions_safety": any(word in lower for word in ["smoke", "fire", "burn", "shock", "injury", "hazard", "sick", "allergic"]),
        # Use word boundaries so words such as "issue" do not accidentally
        # trigger the standalone "sue" escalation keyword.
        "mentions_manager": bool(re.search(r"\b(?:manager|supervisor|ombudsman|legal action|lawyer|sue)\b", lower)),
        "mentions_repeat": any(word in lower for word in ["again", "third time", "repeatedly", "still waiting", "multiple times", "second time"]),
    }
    return signals


def evaluate_conditions(conditions: dict, signals: dict) -> tuple[bool, bool, list[str]]:
    """Return (all_passed, any_signal_missing, notes)."""
    if not conditions:
        return True, False, []
    passed = True
    missing = False
    notes: list[str] = []
    for key, expected in conditions.items():
        actual = signals.get(key)
        if actual is None:
            missing = True
            notes.append(f"{key} not detectable")
            continue
        ok = _compare(actual, str(expected))
        notes.append(f"{key}={actual} vs {expected} -> {'pass' if ok else 'fail'}")
        if not ok:
            passed = False
    return passed, missing, notes


def _compare(actual, expected: str) -> bool:
    match = re.match(r"^(>=|<=|==|!=|>|<)\s*(.+)$", expected.strip())
    if not match:
        return str(actual).lower() == expected.strip().lower()
    op, raw = match.group(1), match.group(2).strip()
    try:
        expected_num = float(raw)
        actual_num = float(actual)
        numeric = True
    except (TypeError, ValueError):
        numeric = False
    if numeric:
        if op == ">":
            return actual_num > expected_num
        if op == ">=":
            return actual_num >= expected_num
        if op == "<":
            return actual_num < expected_num
        if op == "<=":
            return actual_num <= expected_num
        if op == "==":
            return actual_num == expected_num
        if op == "!=":
            return actual_num != expected_num
    left, right = str(actual).lower(), raw.lower()
    if op == "==":
        return left == right
    if op == "!=":
        return left != right
    return False


# ---------------------------------------------------------------------------
# Rule matching
# ---------------------------------------------------------------------------

def _rule_score(rule: ComplaintRule, text_lower: str, signals: dict) -> tuple[float, bool]:
    conditions = rule.conditions or {}
    conditions_passed, missing, _ = evaluate_conditions(conditions, signals)
    if not conditions_passed:
        return -1.0, False

    # Amount-threshold rules (e.g. high-value refunds) require a detected amount.
    if missing and "amount" in conditions:
        return -1.0, False

    score = 0.0
    if conditions and not missing:
        score += 3.0

    keywords = rule.keywords or []
    for keyword in keywords:
        if keyword and keyword.lower() in text_lower:
            score += 2.0

    if rule.category and rule.category.lower() in text_lower:
        score += 1.0

    subcategory_tokens = [t for t in re.findall(r"[a-z]+", (rule.subcategory or "").lower()) if len(t) > 3]
    if subcategory_tokens and all(t in text_lower for t in subcategory_tokens):
        score += 3.0

    return score, True


def match_rule(
    db: Session,
    complaint: Complaint,
    rules: Optional[list[ComplaintRule]] = None,
) -> tuple[Optional[ComplaintRule], float, list[tuple[ComplaintRule, float]]]:
    """Select the best-matching rule.

    ``rules`` is an optional preloaded active-rule list used by bulk dataset
    seeding. Normal request-time callers keep the database-backed default.
    """
    text = complaint_text(complaint)
    text_lower = text.lower()
    signals = extract_signals(complaint, text)

    if rules is None:
        rules = db.query(ComplaintRule).filter(ComplaintRule.is_active.is_(True)).all()
    scored: list[tuple[ComplaintRule, float]] = []
    for rule in rules:
        if (rule.rule_id or "").upper().startswith("OTH"):
            continue
        score, eligible = _rule_score(rule, text_lower, signals)
        if eligible and score > 0:
            scored.append((rule, score))

    scored.sort(key=lambda pair: pair[1], reverse=True)

    if scored and scored[0][1] >= 2.0:
        return scored[0][0], scored[0][1], scored

    fallback = next((r for r in rules if (r.rule_id or "").upper().startswith("OTH")), None)
    return fallback, (1.0 if fallback else 0.0), scored


def detect_secondary_issues(
    complaint: Complaint, primary_rule: Optional[ComplaintRule], ranked: list[tuple[ComplaintRule, float]]
) -> list[str]:
    """Multiple problems in one complaint must not be collapsed (spec §18)."""
    issues: list[str] = []
    primary_category = primary_rule.category if primary_rule else ""
    for rule, score in ranked[1:]:
        if score < 4.0:
            continue
        if rule.category == primary_category:
            continue
        label = f"{rule.category} - {rule.subcategory}"
        if label not in issues:
            issues.append(label)
        if len(issues) >= 3:
            break
    return issues


def expected_from_rule(rule: Optional[ComplaintRule]) -> dict:
    """Ground-truth expectation used by the validators and the dataset report."""
    if rule is None:
        return {
            "category": "", "subcategory": "", "department": "", "urgency": "",
            "priority": "", "policy_id": "", "escalation": False,
            "required_actions": [], "prohibited_actions": [], "follow_up": True,
        }
    return {
        "category": rule.category,
        "subcategory": rule.subcategory,
        "department": rule.department,
        "urgency": rule.urgency,
        "priority": rule.priority,
        "policy_id": rule.policy_id,
        "escalation": bool(rule.escalation),
        "escalation_reason": rule.escalation_reason,
        "escalation_department": rule.escalation_department,
        "required_actions": list(rule.required_actions or []),
        "prohibited_actions": list(rule.prohibited_actions or []),
        "follow_up": bool(rule.follow_up),
    }
