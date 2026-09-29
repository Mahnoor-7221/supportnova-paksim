"""AI Firewall — the trust boundary around every model interaction.

    USER INPUT → INPUT FIREWALL → AI → OUTPUT FIREWALL → TRUST GATE → HUMAN GOVERNANCE / RESPONSE

INPUT firewall (untrusted text, documents, transcripts):
    prompt injection, jailbreaks, malicious/destructive instructions, data-extraction
    attempts, suspicious embedded document instructions, PII.
OUTPUT firewall (anything the AI wants to show/say):
    unsupported claims (hallucination checker), fabricated citations, unsupported
    promises, prohibited actions (policy violations), unsafe instructions, privacy
    violations, and unauthorised actions ("I have refunded you").

Both layers are deterministic and reuse the v1 detectors (injection guard,
hallucination checker, resolution validator) so that there is one source of truth.
Blocked events are written to the security timeline.
"""
from __future__ import annotations

import re
from typing import Optional

from sqlalchemy.orm import Session

from ..models import Complaint, Document, Policy
from ..python_validation import hallucination_checker, resolution_validator
from ..python_validation.common import ValidationContext, overlap_ratio
from ..python_validation.policy_validator import find_policy_ids
from ..services import injection_guard
from ..services.security_events import log_security_event
from . import pii

SEVERITY_RANK = {"info": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}

# ---------------------------------------------------------------------------
# INPUT FIREWALL
# ---------------------------------------------------------------------------

_JAILBREAK = [
    (r"pretend\s+(that\s+)?you\s+(have\s+no|are\s+not\s+bound|don'?t\s+have)\s+(any\s+)?(rules|restrictions|limits|guidelines)", "jailbreak: role-play without restrictions"),
    (r"act\s+as\s+(an?\s+)?(unrestricted|unfiltered|jailbroken|evil)\s+(ai|assistant|model|bot)", "jailbreak: unrestricted persona"),
    (r"(developer|god|admin|root|sudo)\s+mode\s+(enabled|on|activated|unlocked)", "jailbreak: privileged mode claim"),
    (r"(without|with\s+no)\s+(any\s+)?(safety|ethical|policy)\s+(filters?|checks?|restrictions?|guardrails?)", "jailbreak: disable safety"),
    (r"(from\s+now\s+on|starting\s+now)\s+you\s+(will|must|are)\s+", "jailbreak: persistent override"),
]
_EXTRACTION = [
    (r"(show|list|reveal|dump|give|send|print|tell)\s+(me\s+)?(all\s+|every\s+)?(the\s+)?(other\s+)?(customers?|users?|accounts?|clients?)('?s?)?\s+(data|details|records|emails?|phones?|complaints?|information|addresses)", "data extraction: other customers' data"),
    (r"(reveal|show|print|repeat|leak|tell\s+me)\s+(me\s+)?(your\s+|the\s+)?(system\s+prompt|hidden\s+(prompt|instructions)|initial\s+instructions|internal\s+rules)", "data extraction: system prompt"),
    (r"(api[\s_-]?key|secret[\s_-]?key|access\s+token|jwt|database\s+password|credentials?)\b.{0,40}\b(show|give|reveal|print|send|what\s+is)|\b(show|give|reveal|print|send)\b.{0,40}\b(api[\s_-]?key|secret[\s_-]?key|access\s+token|credentials?)", "data extraction: secrets"),
    (r"(dump|export|download)\s+(the\s+)?(entire\s+|whole\s+|full\s+)?(database|customer\s+table|all\s+records)", "data extraction: bulk export"),
]
_MALICIOUS = [
    (r"(drop\s+table|delete\s+from\s+\w+|truncate\s+table|rm\s+-rf|;\s*shutdown|xp_cmdshell)", "malicious instruction: destructive command"),
    (r"<\s*script\b|javascript:|onerror\s*=", "malicious instruction: script injection"),
    (r"(execute|run|call)\s+(the\s+)?(tool|function|command|shell|code)\s*[:(]", "malicious instruction: tool invocation"),
    (r"(refund|transfer|send)\s+(all|the\s+entire)\s+(money|funds|balance)", "malicious instruction: mass financial action"),
    (r"(delete|erase|wipe)\s+(all\s+)?(complaints?|logs?|audit|records?|history)", "malicious instruction: evidence destruction"),
]
_DOC_INSTRUCTION = [
    (r"(^|\n)\s*(system|assistant)\s*:", "document embeds a system/assistant role marker"),
    (r"\[/?(inst|sys)\]|<\|(im_start|system)\|>", "document embeds chat-template tokens"),
    (r"(when|if)\s+(you|the\s+ai|the\s+assistant)\s+(read|see|process)s?\s+this", "document addresses the AI directly"),
    (r"(note\s+to|message\s+for)\s+(the\s+)?(ai|assistant|model|llm)", "document addresses the AI directly"),
]
_JAIL_RE = [(re.compile(p, re.I), label) for p, label in _JAILBREAK]
_EXTRACT_RE = [(re.compile(p, re.I | re.S), label) for p, label in _EXTRACTION]
_MAL_RE = [(re.compile(p, re.I), label) for p, label in _MALICIOUS]
_DOC_RE = [(re.compile(p, re.I | re.M), label) for p, label in _DOC_INSTRUCTION]


def input_firewall(text: str, *, source: str = "user", channel: str = "complaint") -> dict:
    """Scan untrusted input.

    ``channel`` decides the reaction:
      * ``complaint``  — the text is a customer complaint / evidence: it is *recorded* but
        neutralised (treated strictly as data) and forced to human review.
      * ``assistant``  — interactive chat/voice: dangerous input is refused outright.
    ``source`` is ``user`` | ``document`` | ``transcript``.
    """
    text = text or ""
    findings: list[dict] = []

    scan = injection_guard.scan_document(text) if source == "document" else injection_guard.scan_text(text)
    for label in scan.get("matches", []):
        findings.append({"category": "prompt_injection", "label": label, "severity": "high"})
    if scan.get("critical"):
        findings.append({"category": "prompt_injection", "label": "critical override phrase", "severity": "critical"})

    for pattern, label in _JAIL_RE:
        if pattern.search(text):
            findings.append({"category": "jailbreak", "label": label, "severity": "high"})
    for pattern, label in _EXTRACT_RE:
        if pattern.search(text):
            findings.append({"category": "data_extraction", "label": label, "severity": "high"})
    for pattern, label in _MAL_RE:
        if pattern.search(text):
            findings.append({"category": "malicious_instruction", "label": label, "severity": "critical"})
    if source == "document":
        for pattern, label in _DOC_RE:
            if pattern.search(text):
                findings.append({"category": "suspicious_document", "label": label, "severity": "medium"})

    pii_result = pii.redact(text)
    pii_counts = pii_result["counts"]

    seen: set[tuple[str, str]] = set()
    unique = []
    for finding in findings:
        key = (finding["category"], finding["label"])
        if key not in seen:
            seen.add(key)
            unique.append(finding)
    findings = unique

    top = max((SEVERITY_RANK[f["severity"]] for f in findings), default=0)
    risk = {0: "none", 1: "low", 2: "medium", 3: "high", 4: "critical"}[top]
    if findings and channel == "assistant":
        action = "block"
    elif findings:
        action = "flag"
    else:
        action = "allow"

    return {
        "allowed": action == "allow",
        "action": action,                 # allow | flag (record + neutralise + human review) | block (refuse)
        "risk": risk,
        "findings": findings,
        "pii": pii_counts,
        "pii_total": pii_result["total"],
        "source": source,
        "channel": channel,
        "categories": sorted({f["category"] for f in findings}),
    }


# ---------------------------------------------------------------------------
# OUTPUT FIREWALL
# ---------------------------------------------------------------------------

_PROMISE = re.compile(
    r"(we\s+(?:will|shall|are\s+going\s+to)\s+(?:refund|compensate|reimburse|replace|credit|pay)[^.\n]{0,80}"
    r"|you\s+(?:will|shall)\s+(?:receive|get)\s+(?:a\s+|an\s+|your\s+)?(?:full\s+)?(?:refund|replacement|compensation|credit)[^.\n]{0,60}"
    r"|(?:full|100\s?%)\s+refund\s+(?:is\s+|has\s+been\s+)?(?:approved|guaranteed|granted)"
    r"|refund\s+(?:has\s+been|is|was)\s+(?:approved|issued|processed|granted))",
    re.IGNORECASE)
_UNAUTH_ACTION = re.compile(
    r"\b(?:i|we)\s+(?:have|'ve|had)\s+(?:already\s+)?(?:refunded|approved|cancelled|canceled|deleted|closed|charged|transferred|"
    r"reversed|waived|blocked\s+your\s+account|reset\s+your\s+password)\b", re.IGNORECASE)
_UNSAFE_INSTRUCTION = re.compile(
    r"(share\s+(your\s+)?(password|otp|one[- ]time\s+code|pin|cvv|card\s+number)"
    r"|send\s+(us\s+)?(your\s+)?(password|otp|pin|cvv)"
    r"|disable\s+(your\s+)?(antivirus|firewall|security\s+(software|settings))"
    r"|(keep|continue)\s+using\s+(the\s+)?(device|product|charger|battery)\s+(despite|even\s+if|although)"
    r"|ignore\s+(the\s+)?(smoke|burning\s+smell|sparks|overheating)"
    r"|click\s+(on\s+)?(this|the\s+following)\s+link\s+to\s+(verify|confirm)\s+your\s+(account|password|card))",
    re.IGNORECASE)
_SECTION_REF = re.compile(r"(?:section|clause|§)\s*([0-9]+(?:\.[0-9]+)*)", re.IGNORECASE)
_DOC_CODE = re.compile(r"\bDOC-\d{3,}\b")


def _finding(category: str, severity: str, message: str, evidence: str = "") -> dict:
    return {"category": category, "severity": severity, "message": message, "evidence": evidence[:200]}


def output_firewall(
    db: Session,
    text: str,
    *,
    complaint: Optional[Complaint] = None,
    chunks: Optional[list[dict]] = None,
    rule=None,
    allow_own_pii: bool = False,
    known_policy_id: Optional[str] = None,
    context_text: str = "",
) -> dict:
    """Vet AI-generated text before it can reach a customer, a voice synthesiser or an agent."""
    text = text or ""
    chunks = chunks or []
    findings: list[dict] = []
    policy_text = "\n".join(c.get("text", "") for c in chunks)
    if rule is not None and getattr(rule, "required_actions", None):
        policy_text += "\n" + " ".join(rule.required_actions or [])

    # 1) unsupported claims — reuse the v1 hallucination checker verbatim
    lookup = {p.policy_id: {"version": p.version} for p in db.query(Policy).filter(Policy.is_active.is_(True)).all()}
    ctx = ValidationContext(
        complaint=complaint or Complaint(code="FW", title="", description=""),
        parsed={"professional_response": text, "policy_id": known_policy_id},
        expected={}, matched_rule=rule, escalation_decision={}, chunks=chunks,
        policy_lookup=lookup, injection_detected=False, schema_valid=True,
    )
    for check in hallucination_checker.validate(ctx):
        if check.status == "FAIL":
            for claim in (check.data or [check.message]):
                category = "fabricated_citation" if "policy reference" in claim.lower() else "unsupported_claim"
                findings.append(_finding(category, "high", claim))

    # 2) fabricated citations (policy ids, document codes, section numbers)
    for pid in find_policy_ids(text):
        if pid not in lookup and not any(pid in f["message"] for f in findings):
            findings.append(_finding("fabricated_citation", "high", f"Policy '{pid}' does not exist in the knowledge base"))
    known_docs = {row[0] for row in db.query(Document.code).all()}
    for code in set(_DOC_CODE.findall(text)):
        if code not in known_docs:
            findings.append(_finding("fabricated_citation", "high", f"Document '{code}' does not exist"))
    known_sections = {str(c.get("section_id", "")) for c in chunks} | {
        str(p.section) for p in db.query(Policy).all() if p.section}
    for section in set(_SECTION_REF.findall(text)):
        if section not in known_sections:
            findings.append(_finding("fabricated_citation", "medium",
                                     f"Section {section} is not among the retrieved approved sources"))

    # 3) unsupported promises (allowed only when the wording comes from approved policy/rule text)
    for match in _PROMISE.finditer(text):
        sentence = match.group(0)
        if policy_text and overlap_ratio(sentence, policy_text) >= 0.6:
            continue
        findings.append(_finding("unsupported_promise", "high",
                                 "Commitment not grounded in an approved policy", sentence))

    # 4) policy violations — prohibited-action patterns from the rule matrix validator
    for label in resolution_validator._detect_prohibited(text):  # noqa: SLF001 (shared pattern list)
        findings.append(_finding("policy_violation", "high", f"Prohibited action pattern: {label}"))

    # 5) unsafe instructions
    for match in _UNSAFE_INSTRUCTION.finditer(text):
        findings.append(_finding("unsafe_instruction", "critical", "Unsafe instruction to the customer", match.group(0)))

    # 6) unauthorised actions
    for match in _UNAUTH_ACTION.finditer(text):
        findings.append(_finding("unauthorized_action", "critical",
                                 "AI claims to have executed a consequential action it is not authorised to take",
                                 match.group(0)))

    # 7) privacy violations
    own = pii.redact(f"{context_text}\n{complaint.description if complaint else ''}") if allow_own_pii else None
    own_types_present = {f["type"] for f in own["findings"]} if own else set()
    for finding in pii.detect(text):
        kind = finding["type"]
        if kind in {"card", "national_id", "iban", "account_number"}:
            findings.append(_finding("privacy_violation", "critical", f"Output exposes sensitive data ({kind})"))
        elif not (allow_own_pii and kind in own_types_present):
            findings.append(_finding("privacy_violation", "high", f"Output exposes personal data ({kind})"))

    unique, seen = [], set()
    for f in findings:
        key = (f["category"], f["message"])
        if key not in seen:
            seen.add(key)
            unique.append(f)
    findings = unique

    top = max((SEVERITY_RANK[f["severity"]] for f in findings), default=0)
    action = "block" if top >= SEVERITY_RANK["high"] else ("review" if findings else "allow")
    return {
        "allowed": action == "allow",
        "action": action,                     # allow | review | block
        "findings": findings,
        "categories": sorted({f["category"] for f in findings}),
    }


# ---------------------------------------------------------------------------
# Event logging (blocked events are always recorded)
# ---------------------------------------------------------------------------

def log_input_event(db: Session, result: dict, *, complaint: Optional[Complaint] = None,
                    document: Optional[Document] = None, where: str = "") -> None:
    if result["action"] == "allow":
        return
    event_type = "firewall_input_blocked" if result["action"] == "block" else "firewall_input_flagged"
    log_security_event(
        db, event_type,
        f"Input firewall {result['action']}: {', '.join(result['categories']) or 'suspicious input'}"
        + (f" ({where})" if where else ""),
        severity="high" if result["risk"] in {"high", "critical"} else "medium",
        complaint=complaint, document=document,
        detail={"findings": result["findings"][:6], "channel": result["channel"], "source": result["source"]},
        dedupe=False,
    )


def log_output_event(db: Session, result: dict, *, complaint: Optional[Complaint] = None, where: str = "") -> None:
    if result["action"] != "block":
        return
    log_security_event(
        db, "firewall_output_blocked",
        f"Output firewall blocked AI text: {', '.join(result['categories'])}" + (f" ({where})" if where else ""),
        severity="critical" if any(f["severity"] == "critical" for f in result["findings"]) else "high",
        complaint=complaint,
        detail={"findings": result["findings"][:6]},
        dedupe=False,
    )
