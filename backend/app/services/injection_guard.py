"""Prompt-injection detection.

Complaint text and uploaded document text are untrusted data. This module
flags instruction-like content so it can be surfaced, audited, excluded from
the approved knowledge base and routed to manual review.
"""
from __future__ import annotations

import re

PATTERNS: list[tuple[str, str]] = [
    (r"ignore\s+(all\s+|any\s+|the\s+|your\s+)?(previous\s+|prior\s+)?instructions?", "ignore instructions"),
    (r"disregard\s+(all\s+|any\s+|the\s+|your\s+)?(previous\s+|prior\s+)?(instructions?|rules?|polic(y|ies))", "disregard rules"),
    (r"forget\s+(everything|all\s+rules|your\s+instructions)", "forget rules"),
    (r"you\s+are\s+now\s+(in\s+)?(developer|admin|god|unrestricted|debug)\s*mode", "role override"),
    (r"(approve|authorize|grant)\s+(every|all|any)\s+(refund|compensation|claim)s?", "mass approval request"),
    (r"give\s+me\s+a\s+(full|complete|100%)\s+refund", "full refund demand"),
    (r"(must|you\s+will|you\s+have\s+to)\s+(approve|refund|compensate)", "imperative override"),
    (r"(bypass|override)\s+(the\s+)?(system|safety|company)?\s*(rules?|polic(y|ies)|restrictions?|guardrails?)", "policy bypass"),
    (r"new\s+instructions?\s*:", "instruction injection"),
    (r"system\s+prompt", "system prompt probing"),
    (r"jailbreak|do\s+anything\s+now|\bDAN\b", "jailbreak"),
    (r"(reply|respond)\s+only\s+with\s+(the\s+)?(word|phrase)", "output forcing"),
    (r"ignore\s+(the\s+)?(above|below)\s+(rules|instructions)", "ignore above/below"),
]

_COMPILED = [(re.compile(p, re.IGNORECASE), label) for p, label in PATTERNS]

# Strong phrases that indicate a document is trying to reprogram the system.
DOCUMENT_CRITICAL = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
    re.compile(r"approve\s+every\s+refund", re.IGNORECASE),
    re.compile(r"disregard\s+(all\s+)?(company\s+)?polic", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(in\s+)?(developer|unrestricted)", re.IGNORECASE),
]


def scan_text(text: str) -> dict:
    """Return {'suspected': bool, 'matches': [labels], 'count': int}."""
    if not text:
        return {"suspected": False, "matches": [], "count": 0}
    labels: list[str] = []
    for pattern, label in _COMPILED:
        if pattern.search(text):
            labels.append(label)
    return {"suspected": bool(labels), "matches": sorted(set(labels)), "count": len(labels)}


def scan_document(text: str) -> dict:
    """Stricter scan used for uploaded knowledge-base documents."""
    result = scan_text(text)
    critical = any(p.search(text or "") for p in DOCUMENT_CRITICAL)
    result["critical"] = critical
    result["suspected"] = result["suspected"] or critical
    return result
