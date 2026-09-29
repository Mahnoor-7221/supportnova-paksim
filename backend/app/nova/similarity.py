"""Lightweight semantic similarity (TF-IDF + synonym expansion).

This is *not* a neural embedding model: it is a transparent lexical-semantic
index (stemmed unigrams + bigrams, IDF weighting and a small support-domain
synonym map) that runs fully offline and can explain *why* two texts are
similar. ``EmbeddingProvider`` documents the seam where a neural embedding
service can be plugged in later.
"""
from __future__ import annotations

import math
import re
from collections import Counter
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from ..models import AIAnalysis, Complaint, ManualReview
from ..services.retrieval import STOPWORDS

_TOKEN = re.compile(r"[a-z0-9]+")

SYNONYMS = {
    "late": "delay", "delayed": "delay", "overdue": "delay", "slow": "delay", "waiting": "delay",
    "arrive": "deliver", "arrived": "deliver", "arrival": "deliver", "shipment": "deliver", "shipping": "deliver",
    "parcel": "deliver", "package": "deliver", "delivery": "deliver", "delivered": "deliver", "dispatch": "deliver",
    "reimburse": "refund", "reimbursement": "refund", "moneyback": "refund", "repay": "refund", "credit": "refund",
    "broken": "defect", "defective": "defect", "faulty": "defect", "damaged": "defect", "malfunction": "defect",
    "charged": "charge", "overcharged": "charge", "billed": "charge", "billing": "charge", "invoice": "charge",
    "deducted": "charge", "debited": "charge", "payment": "charge",
    "smoke": "hazard", "fire": "hazard", "burn": "hazard", "shock": "hazard", "unsafe": "hazard", "injury": "hazard",
    "scam": "fraud", "unauthorized": "fraud", "unauthorised": "fraud", "stolen": "fraud", "hacked": "fraud",
    "rude": "service", "unhelpful": "service", "dismissive": "service", "agent": "service",
    "login": "account", "password": "account", "locked": "account", "access": "account",
    "warranty": "warranty", "guarantee": "warranty", "coverage": "warranty",
}


def _stem(token: str) -> str:
    for suffix in ("ing", "ed", "es", "s"):
        if len(token) > 4 and token.endswith(suffix):
            token = token[: -len(suffix)]
            break
    return SYNONYMS.get(token, token)


def tokens(text: str) -> list[str]:
    words = [w for w in _TOKEN.findall((text or "").lower()) if w not in STOPWORDS and len(w) > 2]
    stems = [_stem(w) for w in words]
    bigrams = [f"{a}_{b}" for a, b in zip(stems, stems[1:])]
    return stems + bigrams


class EmbeddingProvider:
    """Seam for a neural embedding backend (not bundled). Default = TF-IDF index below."""

    name = "tfidf-synonym"


class TfidfIndex:
    def __init__(self, docs: Iterable[tuple[object, str]]):
        self.keys: list[object] = []
        self.vectors: list[dict[str, float]] = []
        counts: list[Counter] = []
        df: Counter = Counter()
        for key, text in docs:
            c = Counter(tokens(text))
            counts.append(c)
            self.keys.append(key)
            df.update(c.keys())
        n = max(len(counts), 1)
        self.idf = {t: math.log(1 + n / (1 + f)) for t, f in df.items()}
        for c in counts:
            self.vectors.append(self._weigh(c))

    def _weigh(self, counter: Counter) -> dict[str, float]:
        vec = {t: (1 + math.log(f)) * self.idf.get(t, math.log(2 + len(self.keys))) for t, f in counter.items()}
        norm = math.sqrt(sum(v * v for v in vec.values())) or 1.0
        return {t: v / norm for t, v in vec.items()}

    def query(self, text: str, top_k: int = 5, exclude: Optional[object] = None) -> list[tuple[object, float]]:
        q = self._weigh(Counter(tokens(text)))
        scored = []
        for key, vec in zip(self.keys, self.vectors):
            if exclude is not None and key == exclude:
                continue
            small, big = (q, vec) if len(q) < len(vec) else (vec, q)
            score = sum(w * big.get(t, 0.0) for t, w in small.items())
            if score > 0:
                scored.append((key, score))
        scored.sort(key=lambda p: p[1], reverse=True)
        return scored[:top_k]

    def shared_terms(self, a: str, b: str, limit: int = 6) -> list[str]:
        """Human-readable shared words (surface forms), ranked by IDF."""
        def surface(text: str) -> dict[str, str]:
            return {_stem(w): w for w in _TOKEN.findall((text or "").lower()) if w not in STOPWORDS and len(w) > 2}
        sa, sb = surface(a), surface(b)
        common = set(sa) & set(sb)
        ranked = sorted(common, key=lambda t: -self.idf.get(t, 0))[:limit]
        return [sa[t] for t in ranked]


_CACHE: dict = {"key": None, "index": None, "texts": {}}


def _complaint_index(db: Session) -> tuple[TfidfIndex, dict[int, str]]:
    from sqlalchemy import func

    key = (db.query(func.count(Complaint.id)).scalar(), db.query(func.max(Complaint.id)).scalar(),
           db.query(func.max(Complaint.updated_at)).scalar())
    if _CACHE["key"] != key:
        rows = db.query(Complaint.id, Complaint.title, Complaint.description, Complaint.translated_text).all()
        texts = {r[0]: f"{r[1]} {r[2]} {r[3] or ''}" for r in rows}
        _CACHE.update(key=key, index=TfidfIndex(texts.items()), texts=texts)
    return _CACHE["index"], _CACHE["texts"]


def _previous_resolution(db: Session, complaint: Complaint) -> str:
    review = (db.query(ManualReview).filter(ManualReview.complaint_id == complaint.id, ManualReview.status == "RESOLVED")
              .order_by(ManualReview.id.desc()).first())
    if review is not None and review.decision:
        return f"Human review: {review.decision}" + (f" — {review.decision_notes[:120]}" if review.decision_notes else "")
    analysis = (db.query(AIAnalysis).filter(AIAnalysis.complaint_id == complaint.id)
                .order_by(AIAnalysis.id.desc()).first())
    steps = (analysis.parsed or {}).get("resolution_steps") if analysis else None
    if steps:
        return f"AI-proposed (unconfirmed): {steps[0]}"
    return "No recorded resolution"


def _policy_used(db: Session, complaint: Complaint) -> str:
    analysis = (db.query(AIAnalysis).filter(AIAnalysis.complaint_id == complaint.id)
                .order_by(AIAnalysis.id.desc()).first())
    return str((analysis.parsed or {}).get("policy_id") or "") if analysis else ""


def similar_cases(db: Session, complaint: Complaint, top_k: int = 5, min_similarity: float = 0.25) -> list[dict]:
    index, texts = _complaint_index(db)
    own_text = f"{complaint.title} {complaint.description} {complaint.translated_text or ''}"
    out = []
    for cid, score in index.query(own_text, top_k=top_k + 1, exclude=complaint.id if complaint.id else None):
        if score < min_similarity:
            continue
        other = db.get(Complaint, cid)
        if other is None or other.id == complaint.id:
            continue
        shared = index.shared_terms(own_text, texts.get(cid, ""))
        same_cat = bool(other.issue_category and other.issue_category == (complaint.issue_category or other.issue_category))
        out.append({
            "complaint_id": other.id, "case_id": other.code, "title": other.title,
            "similarity": round(score, 3),
            "previous_resolution": _previous_resolution(db, other),
            "policy_used": _policy_used(db, other),
            "outcome": other.status, "category": other.verified_category or other.issue_category,
            "department": other.verified_department or other.department,
            "why": {
                "shared_terms": shared,
                "same_category": same_cat,
                "same_department": bool(other.department and other.department == complaint.department),
                "method": EmbeddingProvider.name,
                "explanation": (f"Shares key terms ({', '.join(shared[:5])})" if shared else "Weak lexical overlap")
                               + ("; same category" if same_cat else ""),
            },
        })
        if len(out) >= top_k:
            break
    return out
