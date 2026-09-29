"""PakSim telecom offline baseline for Pipeline 1.

This provider is intentionally deterministic and independent from the rule
matrix. It is used when no live GenAI key is configured, so the complete
application can be demonstrated offline while Pipeline 2 remains the
independent ground-truth authority.
"""
from __future__ import annotations

import re
from typing import Optional

from ..models import Complaint

# Deliberately separate from rule_seed.py: this is a small heuristic baseline,
# not a second copy of the complete ground-truth rule matrix.
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "SIM & Account": ["sim", "activation", "activated", "blocked", "verification", "account", "cnic", "registration"],
    "Mobile Internet": ["mobile internet", "internet", "data", "4g", "5g", "slow internet", "data package", "mb"],
    "Calls & SMS": ["call", "calling", "calls", "sms", "message", "text message", "voice"],
    "Network & Coverage": ["signal", "coverage", "network", "outage", "tower", "no service", "congestion"],
    "Balance & Billing": ["balance", "billing", "charge", "charged", "deduction", "recharge", "payment", "transaction"],
    "Packages & Bundles": ["package", "bundle", "renewal", "subscription", "package activation", "package expiry"],
    "SIM Replacement": ["replacement", "replace sim", "lost sim", "stolen sim", "duplicate sim", "sim replacement"],
    "Number Portability": ["mnp", "port", "portability", "network transfer", "porting"],
    "Roaming": ["roaming", "international", "abroad", "roam"],
    "Fraud & Security": ["fraud", "scam", "sim swap", "unauthorized", "security", "compromised", "suspicious activity"],
}

SUBCATEGORIES: dict[str, list[str]] = {
    "SIM & Account": ["SIM Activation", "SIM Blocked", "SIM Verification", "Account Access"],
    "Mobile Internet": ["Internet Not Working", "Slow Internet", "Data Package Issue", "4G/5G Issue"],
    "Calls & SMS": ["Outgoing Calls", "Incoming Calls", "Call Drops", "SMS Failure"],
    "Network & Coverage": ["No Signal", "Weak Signal", "Area Outage", "Network Congestion"],
    "Balance & Billing": ["Wrong Deduction", "Unexpected Charge", "Recharge Problem", "Billing Dispute"],
    "Packages & Bundles": ["Package Activation", "Package Cancellation", "Package Renewal", "Wrong Package"],
    "SIM Replacement": ["Lost SIM", "Stolen SIM", "SIM Swap", "Replacement Status"],
    "Number Portability": ["MNP Request", "MNP Rejection", "Porting Delay", "Porting Status"],
    "Roaming": ["Roaming Activation", "Roaming Not Working", "Roaming Charges", "International Calls"],
    "Fraud & Security": ["SIM Misuse", "Suspected SIM Swap", "Unauthorized Activity", "Account Compromise"],
}

DEPARTMENTS = {
    "SIM & Account": "SIM & Account Services",
    "Mobile Internet": "Technical Support",
    "Calls & SMS": "Technical Support",
    "Network & Coverage": "Network Operations",
    "Balance & Billing": "Billing & Payments",
    "Packages & Bundles": "Customer Support",
    "SIM Replacement": "SIM & Account Services",
    "Number Portability": "Number Portability",
    "Roaming": "Technical Support",
    "Fraud & Security": "Fraud & Security",
}

POLICIES = {
    "SIM & Account": "SIM-POL-01",
    "Mobile Internet": "NET-POL-02",
    "Calls & SMS": "CALL-POL-03",
    "Network & Coverage": "NET-POL-04",
    "Balance & Billing": "BIL-POL-05",
    "Packages & Bundles": "PKG-POL-06",
    "SIM Replacement": "SIM-POL-07",
    "Number Portability": "MNP-POL-08",
    "Roaming": "ROM-POL-09",
    "Fraud & Security": "SEC-POL-10",
}

SPECIAL_ACTIONS = {
    "SIM & Account|SIM Activation": ("Verify customer identity and activation eligibility.", "Do not confirm activation without verification."),
    "SIM & Account|SIM Blocked": ("Verify identity and determine block reason.", "Do not bypass security verification."),
    "Mobile Internet|Internet Not Working": ("Check service status, package validity and device/network basics.", "Do not promise a network restoration time without evidence."),
    "Mobile Internet|Slow Internet": ("Check coverage, congestion and package/device conditions.", "Do not label a network outage without evidence."),
    "Network & Coverage|Area Outage": ("Check outage information and create/attach network incident reference.", "Do not promise immediate restoration."),
    "Fraud & Security|Suspected SIM Swap": ("Perform identity verification and security escalation.", "Do not state that the account is safe before verification."),
    "Fraud & Security|Unauthorized Activity": ("Secure the account and escalate for investigation.", "Do not authorize a refund or restoration without verification."),
    "SIM Replacement|Lost SIM": ("Verify identity and initiate replacement according to policy.", "Do not issue replacement without required verification."),
    "SIM Replacement|Stolen SIM": ("Verify identity and escalate security risk.", "Do not disclose sensitive account information."),
    "Balance & Billing|Recharge Problem": ("Collect transaction reference and verify recharge status.", "Do not promise a refund before transaction verification."),
    "Balance & Billing|Wrong Deduction": ("Verify balance ledger and applicable package charges.", "Do not promise compensation without eligibility verification."),
    "Number Portability|MNP Rejection": ("Verify rejection reason and required customer information.", "Do not guarantee port approval."),
}

SUBCATEGORY_KEYWORDS = {
    "SIM Activation": ["activation", "activated"],
    "SIM Blocked": ["blocked", "block"],
    "SIM Verification": ["verification", "verify", "cnic"],
    "Account Access": ["account access", "account", "login"],
    "Internet Not Working": ["not working", "doesn't work", "does not work", "stopped working"],
    "Slow Internet": ["slow", "slow internet"],
    "Data Package Issue": ["data package", "data package issue"],
    "4G/5G Issue": ["4g", "5g"],
    "Outgoing Calls": ["outgoing call", "can't call", "cannot call"],
    "Incoming Calls": ["incoming call", "can't receive calls"],
    "Call Drops": ["call drop", "dropped call"],
    "SMS Failure": ["sms", "message"],
    "No Signal": ["no signal", "no service"],
    "Weak Signal": ["weak signal", "weak coverage"],
    "Area Outage": ["outage", "area outage"],
    "Network Congestion": ["congestion", "busy network"],
    "Wrong Deduction": ["deduction", "deducted"],
    "Unexpected Charge": ["unexpected charge", "charged unexpectedly"],
    "Recharge Problem": ["recharge", "recharge problem"],
    "Billing Dispute": ["billing dispute", "billing"],
    "Package Activation": ["package activation", "activate package"],
    "Package Cancellation": ["cancel package", "package cancellation"],
    "Package Renewal": ["renewal", "renew package"],
    "Wrong Package": ["wrong package"],
    "Lost SIM": ["lost sim"],
    "Stolen SIM": ["stolen sim"],
    "SIM Swap": ["sim swap"],
    "Replacement Status": ["replacement status", "replacement"],
    "MNP Request": ["mnp request", "port request"],
    "MNP Rejection": ["mnp rejection", "port rejected"],
    "Porting Delay": ["porting delay", "port delay"],
    "Porting Status": ["porting status", "port status"],
    "Roaming Activation": ["roaming activation", "activate roaming"],
    "Roaming Not Working": ["roaming not working", "roaming issue"],
    "Roaming Charges": ["roaming charge", "roaming charges"],
    "International Calls": ["international call", "international calls"],
    "SIM Misuse": ["sim misuse"],
    "Suspected SIM Swap": ["suspected sim swap", "sim swap"],
    "Unauthorized Activity": ["unauthorized", "unauthorised"],
    "Account Compromise": ["compromised", "account compromise"],
}

NEGATIVE_WORDS = ["angry", "frustrated", "annoyed", "unacceptable", "disappointed", "upset", "terrible", "awful", "useless"]
VERY_NEGATIVE_WORDS = ["furious", "outraged", "ridiculous", "worst", "unbelievable", "never again", "scam", "disgusting"]
URGENT_WORDS = ["urgent", "asap", "immediately", "emergency", "right now", "still waiting", "multiple times"]
_DAYS = re.compile(r"(\d{1,3})\s*(?:days?)\s*(?:late|delay|overdue|ago|waiting)?", re.IGNORECASE)
_AMOUNT = re.compile(r"(?:rs\.?|pkr|€|\$|eur|usd)\s?(\d{1,7}(?:[.,]\d{1,2})?)", re.IGNORECASE)


def _category(text: str, product_or_service: str = "") -> tuple[str, dict[str, int]]:
    product = (product_or_service or "").strip()
    if product in CATEGORY_KEYWORDS:
        scores = {product: max(2, sum(1 for w in CATEGORY_KEYWORDS[product] if w in text))}
        # Still count the rest so the baseline remains text-sensitive.
        for category, words in CATEGORY_KEYWORDS.items():
            if category == product:
                continue
            hits = sum(1 for word in words if word in text)
            if hits:
                scores[category] = hits
        return max(scores.items(), key=lambda pair: pair[1])[0], scores

    scores = {category: sum(1 for word in words if word in text) for category, words in CATEGORY_KEYWORDS.items()}
    scores = {k: v for k, v in scores.items() if v}
    if not scores:
        return "SIM & Account", {}
    return max(scores.items(), key=lambda pair: pair[1])[0], scores


def _subcategory(category: str, text: str) -> str:
    options = SUBCATEGORIES[category]
    scored = []
    for sub in options:
        words = SUBCATEGORY_KEYWORDS.get(sub, [sub.lower()])
        scored.append((sub, sum(1 for word in words if word in text)))
    best = max(scored, key=lambda pair: pair[1])
    return best[0] if best[1] else options[0]


def _urgency(category: str, subcategory: str, text: str) -> str:
    if category == "Fraud & Security" or subcategory in {"Stolen SIM", "Suspected SIM Swap", "Unauthorized Activity", "Account Compromise"}:
        return "Critical"
    if category == "Network & Coverage" and any(w in text for w in ["outage", "no service"]):
        return "High"
    if category == "SIM Replacement" and subcategory == "Lost SIM":
        return "High"
    if any(word in text for word in URGENT_WORDS):
        return "High"
    return "Medium"


def n_days(complaint: Complaint) -> Optional[int]:
    match = _DAYS.search((complaint.title or "") + " " + (complaint.description or ""))
    if match:
        try:
            return int(match.group(1))
        except (TypeError, ValueError):
            return None
    return None


def analyze(complaint: Complaint, chunks: Optional[list[dict]] = None) -> dict:
    text = " ".join(filter(None, [
        complaint.title, complaint.description, complaint.product_or_service,
        complaint.requested_resolution, getattr(complaint, "translated_text", "")
    ])).lower()
    chunks = chunks or []

    category, scores = _category(text, complaint.product_or_service)
    subcategory = _subcategory(category, text)
    urgency = _urgency(category, subcategory, text)
    priority = {"Critical": "P1", "High": "P2", "Medium": "P3", "Low": "P4"}[urgency]

    if any(word in text for word in VERY_NEGATIVE_WORDS):
        sentiment = "Strongly Negative"
    elif any(word in text for word in NEGATIVE_WORDS):
        sentiment = "Negative"
    else:
        sentiment = "Neutral"

    escalation_required = category == "Fraud & Security" or subcategory in {
        "Area Outage", "Stolen SIM", "Suspected SIM Swap", "Unauthorized Activity", "Account Compromise"
    } or any(word in text for word in ["escalate", "manager", "supervisor", "ombudsman", "legal"])
    escalation_reason = "Mandatory security/network escalation condition" if escalation_required else ""

    policy_id = POLICIES[category]
    policy_status = "FOUND" if chunks else "POLICY_NOT_FOUND"
    policy_section = chunks[0].get("section_id") if chunks else None
    policy_version = chunks[0].get("version") if chunks else None

    entities = []
    if complaint.order_reference:
        entities.append(complaint.order_reference)
    if complaint.product_or_service:
        entities.append(complaint.product_or_service)
    amount_match = _AMOUNT.search(text)
    if amount_match:
        entities.append(f"Amount {amount_match.group(1)}")
    days = n_days(complaint)
    if days is not None:
        entities.append(f"{days} days")

    required_action, prohibited_action = SPECIAL_ACTIONS.get(
        f"{category}|{subcategory}",
        ("Acknowledge the complaint, verify required information and apply the approved policy.",
         "Do not make unsupported promises."),
    )
    resolution_steps = [
        required_action,
        "Verify the customer and relevant service details",
        f"Apply the approved {category} rule and policy",
        "Record the evidence reviewed and the action taken",
        "Provide only a verified customer-facing resolution",
    ]
    if escalation_required:
        resolution_steps.append("Route the case through the applicable escalation workflow")

    clarification_questions = []
    missing_information = []
    if not complaint.order_reference:
        clarification_questions.append("Could you share the relevant reference or transaction number if available?")
        missing_information.append("order_reference")
    if not complaint.product_or_service:
        clarification_questions.append("Which PakSim service or product is affected?")
        missing_information.append("product_or_service")
    if not complaint.complaint_date:
        missing_information.append("complaint_date")

    reference = chunks[0] if chunks else None
    source_references = [c.get("document_code") for c in chunks[:2] if c.get("document_code")]
    if reference:
        resolution_steps.append(f"Follow {policy_id} section {reference.get('section_id', '')}".strip())

    professional_response = (
        "Dear customer,\n\nThank you for contacting PakSim Customer Support. "
        f"We have registered your {category.lower()} complaint and are reviewing it under the applicable policy. "
        "We will provide the verified next step through the complaint reference.\n\n"
        "Kind regards,\nPakSim Customer Support"
    )

    return {
        "complaint_id": complaint.code,
        "issue_category": category,
        "subcategory": subcategory,
        "primary_issue": complaint.title or complaint.description[:240],
        "secondary_issues": [],
        "additional_issues": [],
        "emotion": "anger" if any(word in text for word in VERY_NEGATIVE_WORDS) else "frustration" if any(word in text for word in NEGATIVE_WORDS) else "neutral",
        "sentiment": sentiment,
        "urgency": urgency,
        "priority": priority,
        "department": DEPARTMENTS[category],
        "supporting_departments": [],
        "product_or_service": complaint.product_or_service or "",
        "entities": entities,
        "policy_id": policy_id,
        "policy_section": policy_section,
        "policy_version": policy_version,
        "policy_status": policy_status,
        "policy_applicability": "Unknown",
        "resolution_steps": resolution_steps,
        "refund_eligibility": "Unknown",
        "replacement_eligibility": "Unknown",
        "compensation_eligibility": "Unknown",
        "compensation_limit": None,
        "required_actions": [required_action],
        "prohibited_actions": [prohibited_action],
        "escalation_required": escalation_required,
        "escalation_level": "Supervisor Review" if escalation_required else "No Escalation",
        "escalation_reason": escalation_reason,
        "escalation_notes": escalation_reason,
        "response_type": "Apology and Resolution Update",
        "response_tone": "Empathetic",
        "professional_response": professional_response,
        "follow_up_required": True,
        "follow_up_type": "resolution_confirmation",
        "follow_up_details": "Provide an update after the complaint review.",
        "follow_up_message": "We will contact you with an update after the complaint review.",
        "agent_guidance": f"Offline baseline routing to {DEPARTMENTS[category]}. Do not promise compensation or restoration without verified policy evidence.",
        "clarification_questions": clarification_questions,
        "missing_information": missing_information,
        "unsupported_claims": [],
        "source_references": source_references,
        "_provider_label": "offline-heuristic-baseline",
        "_category_scores": scores,
    }
