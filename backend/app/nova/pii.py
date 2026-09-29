"""PII detection & redaction.

* Detects phone numbers, e-mails, payment cards (Luhn-checked), national ids
  (CNIC / SSN), IBANs, account numbers and street addresses.
* ``redact`` never mutates the original: it returns a redacted *copy* plus the
  finding list. Findings never contain the raw value (safe to log/audit).
"""
from __future__ import annotations

import hashlib
import re
from typing import Iterable

# (type, regex, group index carrying the value, priority — lower wins on overlap)
_PATTERNS: list[tuple[str, re.Pattern, int, int]] = [
    ("email", re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}"), 0, 1),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}[A-Z0-9]{0,16}\b"), 0, 2),
    ("national_id", re.compile(r"\b\d{5}-\d{7}-\d\b"), 0, 3),                       # Pakistan CNIC
    ("national_id", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), 0, 3),                    # US SSN
    ("account_number", re.compile(
        r"\b(?:account|acct|a/c)\s*(?:number|no\.?|#)?\s*[:#]?\s*(\d[\d\- ]{5,22}\d)", re.IGNORECASE), 1, 4),
    ("card", re.compile(r"\b(?:\d[ \-]?){13,19}\b"), 0, 5),
    ("phone", re.compile(r"(?<![\w])\+\d{1,3}[\s\-]?\(?\d{2,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{3,4}\b"), 0, 6),
    ("phone", re.compile(r"(?<![\w])0\d{3}[\s\-]?\d{7}\b"), 0, 6),                  # PK mobile 03xx-xxxxxxx
    ("phone", re.compile(r"(?<![\w])\(?\d{3}\)?[\s.\-]\d{3}[\s.\-]\d{4}\b"), 0, 6),  # US style
    ("address", re.compile(
        r"\b(?:house|h\.?\s?no\.?|plot|flat|apt\.?|apartment)\s*#?\s*\d+[A-Za-z]?[^.\n]{0,60}?"
        r"\b(?:street|st\.?|road|rd\.?|avenue|ave\.?|block|sector|phase|colony|town|lane)\b[^.\n]{0,40}",
        re.IGNORECASE), 0, 7),
    ("address", re.compile(
        r"\b\d{1,5}\s+[A-Z][a-z]+(?:\s[A-Z][a-z]+)?\s+(?:Street|St|Road|Rd|Avenue|Ave|Lane|Drive|Dr)\b"), 0, 7),
]

_TOKEN = {
    "email": "[EMAIL]", "iban": "[IBAN]", "national_id": "[ID-NUMBER]",
    "account_number": "[ACCOUNT]", "card": "[CARD]", "phone": "[PHONE]", "address": "[ADDRESS]",
}


def _luhn(digits: str) -> bool:
    total, alt = 0, False
    for ch in reversed(digits):
        n = int(ch)
        if alt:
            n *= 2
            if n > 9:
                n -= 9
        total += n
        alt = not alt
    return total % 10 == 0


def detect(text: str) -> list[dict]:
    """Return non-overlapping findings ``[{type, start, end}]`` (no raw values)."""
    if not text:
        return []
    raw: list[tuple[int, int, str, int]] = []
    for kind, pattern, group, priority in _PATTERNS:
        for match in pattern.finditer(text):
            start, end = match.span(group) if group else match.span()
            value = text[start:end]
            if kind == "card":
                digits = re.sub(r"\D", "", value)
                if not (13 <= len(digits) <= 19 and _luhn(digits)):
                    continue
            if kind == "phone" and len(re.sub(r"\D", "", value)) < 9:
                continue
            raw.append((start, end, kind, priority))
    raw.sort(key=lambda r: (r[3], -(r[1] - r[0]), r[0]))
    taken: list[tuple[int, int, str]] = []
    for start, end, kind, _ in raw:
        if any(start < t_end and end > t_start for t_start, t_end, _ in taken):
            continue
        taken.append((start, end, kind))
    taken.sort()
    return [{"type": kind, "start": start, "end": end} for start, end, kind in taken]


def redact(text: str) -> dict:
    """Redacted copy + findings. The original text is returned untouched."""
    findings = detect(text or "")
    out: list[str] = []
    cursor = 0
    counts: dict[str, int] = {}
    enriched: list[dict] = []
    for finding in findings:
        start, end, kind = finding["start"], finding["end"], finding["type"]
        out.append(text[cursor:start])
        token = _TOKEN[kind]
        if kind == "card":
            digits = re.sub(r"\D", "", text[start:end])
            token = f"[CARD ending {digits[-4:]}]"
        out.append(token)
        cursor = end
        counts[kind] = counts.get(kind, 0) + 1
        enriched.append({**finding, "masked": token})
    out.append(text[cursor:])
    return {
        "original": text or "",
        "redacted": "".join(out),
        "findings": enriched,
        "counts": counts,
        "total": len(enriched),
    }


def redact_text(text: str) -> str:
    return redact(text)["redacted"]


def counts_only(text: str) -> dict:
    return redact(text)["counts"]


def fingerprint(text: str) -> str:
    """Stable non-reversible digest for audit trails (never store raw PII in logs)."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def contains_pii(text: str, types: Iterable[str] | None = None) -> bool:
    found = {f["type"] for f in detect(text or "")}
    return bool(found & set(types)) if types else bool(found)
