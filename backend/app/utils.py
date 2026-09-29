from __future__ import annotations
from datetime import datetime, timezone
import re

def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

def normalize_ws(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "")).strip()


# ── Pakistani mobile number helpers (used by Nova complaint intake + complaint API) ──
_PK_MOBILE_CANDIDATE = re.compile(r"(?<!\d)(?:\+?\s?92|0)?[\s\-]?3\d{2}[\s\-]?\d{7}(?!\d)")


def normalize_pk_mobile(value: str | None) -> str:
    """Return a mobile number as 03XXXXXXXXX, or '' if it is not a valid PK mobile number."""
    digits = re.sub(r"\D", "", value or "")
    if digits.startswith("0092"):
        digits = digits[4:]
    elif digits.startswith("92") and len(digits) == 12:
        digits = digits[2:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = digits[1:]
    if len(digits) == 10 and digits.startswith("3"):
        return "0" + digits
    return ""


def extract_pk_mobile(text: str | None) -> str:
    """Find the first valid PK mobile number inside free text (normalised), else ''."""
    for match in _PK_MOBILE_CANDIDATE.finditer(text or ""):
        number = normalize_pk_mobile(match.group(0))
        if number:
            return number
    return ""


def mask_pk_mobile(number: str | None) -> str:
    n = normalize_pk_mobile(number)
    return f"{n[:4]}XXXX{n[-3:]}" if n else "—"
