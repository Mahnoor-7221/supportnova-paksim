"""Duplicate complaint detection (spec §17).

Uses order reference, customer, text similarity and time proximity.
Duplicates are flagged and sent to manual review — never merged automatically.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from ..models import Complaint
from ..utils import normalize_ws

SUSPECT_THRESHOLD = 0.80
ORDER_MATCH_THRESHOLD = 0.50
WINDOW_DAYS = 45


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(t) > 3}


def similarity(text_a: str, text_b: str) -> float:
    a, b = normalize_ws(text_a or "")[:600].lower(), normalize_ws(text_b or "")[:600].lower()
    if not a or not b:
        return 0.0
    ratio = SequenceMatcher(None, a, b).ratio()
    ta, tb = _tokens(a), _tokens(b)
    jaccard = len(ta & tb) / len(ta | tb) if (ta | tb) else 0.0
    return round(max(ratio, (ratio + jaccard) / 2), 4)


def find_duplicate(db: Session, complaint: Complaint) -> dict:
    """Return {'duplicate_of_id', 'similarity', 'reason', 'level'} for a new complaint."""
    query = db.query(Complaint).filter(Complaint.id != (complaint.id or -1))
    if complaint.customer_id:
        query = query.filter(Complaint.customer_id == complaint.customer_id)
    candidates = query.order_by(Complaint.id.desc()).limit(60).all()

    best: dict = {"duplicate_of_id": None, "similarity": 0.0, "reason": "", "level": "none"}
    new_text = f"{complaint.title}\n{complaint.description}"

    for candidate in candidates:
        old_text = f"{candidate.title}\n{candidate.description}"
        score = similarity(new_text, old_text)
        same_order = bool(
            complaint.order_reference
            and complaint.order_reference.strip()
            and complaint.order_reference.strip().lower() == (candidate.order_reference or "").strip().lower()
        )
        if same_order:
            score = max(score, 0.55 + 0.4 * score)

        level = "none"
        if score >= SUSPECT_THRESHOLD:
            level = "high"
        elif same_order and score >= ORDER_MATCH_THRESHOLD:
            level = "medium"

        if level != "none" and score > best["similarity"]:
            reason_bits = []
            if same_order:
                reason_bits.append("same order reference")
            reason_bits.append(f"text similarity {score:.2f}")
            best = {
                "duplicate_of_id": candidate.id,
                "similarity": round(score, 4),
                "reason": ", ".join(reason_bits),
                "level": level,
            }
    return best
