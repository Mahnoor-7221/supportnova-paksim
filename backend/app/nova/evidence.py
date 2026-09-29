"""Multimodal evidence intelligence.

Complaints can arrive as text, voice transcripts, images/screenshots, PDF, DOCX,
Markdown or TXT. Every modality is reduced to *claims* (what the customer says)
and *facts* (what a record/document shows) and then cross-checked. Neither the
user's words nor an uploaded document is trusted automatically: the transaction
system-of-record is the authority, uploaded evidence is corroboration, and any
disagreement is surfaced as an ``EVIDENCE CONFLICT`` with an explanation.
"""
from __future__ import annotations

import hashlib
import re
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from ..config import STORAGE_DIR, settings
from ..models import Complaint
from ..models_nova import EvidenceItem, TransactionRecord
from ..services import injection_guard
from ..services.document_processor import DocumentProcessingError, extract_units
from ..utils import utcnow
from . import media, pii

EVIDENCE_DIR = STORAGE_DIR / "evidence"

CLAIM_PATTERNS: dict[str, re.Pattern] = {k: re.compile(v, re.I) for k, v in {
    "payment_failed": r"(payment|transaction|card)\s+(has\s+|was\s+)?(failed|declined|unsuccessful|not\s+successful)|"
                      r"(payment|transaction)\s+(did\s+not|didn'?t)\s+go\s+through|(failed|declined)\s+payment",
    "payment_deducted": r"\b(charged|deducted|debited)\b",
    "not_delivered": r"(not|never|hasn'?t|has\s+not|haven'?t|have\s+not)\s+(been\s+)?(delivered|arrived|received)|"
                     r"never\s+(arrived|came)|still\s+waiting\s+for\s+(my\s+)?(order|parcel|package)|missing\s+(parcel|package)|"
                     r"lost\s+in\s+transit",
    "refund_not_received": r"refund\s+(was\s+|has\s+)?(not|n'?t)\s+(been\s+)?(received|processed|issued|credited|arrived)|"
                           r"(still\s+)?waiting\s+(for|on)\s+(my\s+|the\s+)?refund|no\s+refund",
    "damaged": r"(arrived|came|received|delivered)\s+(broken|damaged|defective|faulty)|"
               r"(broken|damaged|defective|faulty)\s+(on\s+arrival|out\s+of\s+the\s+box)",
    "overcharged": r"overcharg\w+|charged\s+(me\s+)?(twice|double)|double\s+charg\w+",
}.items()}

FACT_PATTERNS: dict[str, re.Pattern] = {k: re.compile(v, re.I) for k, v in {
    "payment_success": r"payment\s+(was\s+)?(successful|completed|approved|received|confirmed)|"
                       r"transaction\s+(successful|completed|approved)|successfully\s+paid|status\s*[:\-]?\s*(paid|success\w*|approved)",
    "payment_failed": r"payment\s+(has\s+)?(failed|declined)|transaction\s+(failed|declined)|status\s*[:\-]?\s*(failed|declined)",
    "delivered": r"\bdelivered\b|delivery\s+completed|status\s*[:\-]?\s*delivered",
    "not_delivered": r"delivery\s+failed|undelivered|status\s*[:\-]?\s*(in\s+transit|not\s+delivered|lost)",
    "refund_issued": r"refund\s+(was\s+|has\s+been\s+)?(issued|processed|completed|credited)",
    "damage_visible": r"cracked|shattered|dented|broken|damaged",
}.items()}

_ORDER_REF = re.compile(r"\b[A-Z]{2,5}-\d{3,}\b")
_AMOUNT = re.compile(r"(?:[$€£]|usd|eur|gbp|rs\.?|pkr)\s?(\d{1,7}(?:[.,]\d{1,2})?)|(\d{1,7}(?:[.,]\d{1,2})?)\s?(?:usd|eur|gbp|pkr|dollars?|euros?)", re.I)
VERIFY_CLAIMS = {"payment_failed", "not_delivered", "refund_not_received", "damaged", "overcharged"}


def extract_claims(text: str) -> dict[str, bool]:
    return {name: True for name, pattern in CLAIM_PATTERNS.items() if pattern.search(text or "")}


def extract_facts(text: str) -> dict:
    """Facts visible in a document/screenshot text (never trusted as authoritative)."""
    facts: dict = {name: True for name, pattern in FACT_PATTERNS.items() if pattern.search(text or "")}
    facts["order_refs"] = sorted(set(_ORDER_REF.findall(text or "")))
    amounts = []
    for m in _AMOUNT.finditer(text or ""):
        raw = (m.group(1) or m.group(2) or "").replace(",", ".")
        try:
            amounts.append(float(raw))
        except ValueError:
            continue
    facts["amounts"] = amounts[:10]
    return facts


def transaction_facts(txn: Optional[TransactionRecord]) -> dict:
    if txn is None:
        return {}
    return {
        "payment_success": txn.payment_status in {"paid", "refunded"},
        "payment_failed": txn.payment_status == "failed",
        "delivered": txn.delivery_status == "delivered",
        "not_delivered": txn.delivery_status in {"in_transit", "delayed", "lost", "not_shipped"},
        "refund_issued": txn.refund_status == "refunded",
    }


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------

def _modality_for(ext: str, hint: str = "") -> str:
    if hint in {"screenshot", "voice"}:
        return hint
    return {"png": "image", "jpg": "image", "jpeg": "image", "webp": "image", "pdf": "pdf", "docx": "docx",
            "md": "markdown", "txt": "text"}.get(ext, "text")


def add_evidence(db: Session, complaint: Complaint, *, modality: str, file_name: str, text: str, method: str,
                 stored_path: str = "", size_bytes: int = 0, user_id: Optional[int] = None) -> EvidenceItem:
    """Persist one evidence item. Extracted text is scanned for indirect prompt injection."""
    scan = injection_guard.scan_document(text)
    item = EvidenceItem(
        complaint_id=complaint.id, modality=modality, file_name=file_name[:255], stored_path=stored_path,
        size_bytes=size_bytes, extracted_text=text[:20000], extraction_method=method,
        extracted_facts=extract_facts(text), injection=scan, pii_counts=pii.counts_only(text),
        quarantined=bool(scan.get("suspected")), uploaded_by=user_id,
    )
    db.add(item)
    db.flush()
    return item


def ingest_upload(db: Session, complaint: Complaint, file_name: str, data: bytes, user_id: Optional[int],
                  transcript: str = "", modality_hint: str = "") -> EvidenceItem:
    """Validate, store safely and extract text from an uploaded evidence file."""
    ext = Path(file_name).suffix.lstrip(".").lower()
    allowed = {e.strip() for e in settings.nova_evidence_extensions.split(",") if e.strip()}
    if ext not in allowed:
        raise ValueError(f"File type '.{ext}' is not allowed (allowed: {', '.join(sorted(allowed))})")
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise ValueError(f"File exceeds {settings.max_upload_mb} MB")
    if not data:
        raise ValueError("Empty file")

    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    safe_name = f"{utcnow().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}.{ext}"      # never trust the client name for the path
    path = EVIDENCE_DIR / safe_name
    path.write_bytes(data)

    text, method = "", "none"
    if ext in {"png", "jpg", "jpeg", "webp"}:
        if transcript.strip():
            text, method = transcript.strip(), "human-transcribed"
        else:
            text, method = media.ocr_image(path)
    else:
        try:
            units = extract_units(path, ext)
            text = "\n".join(u.get("text", "") for u in units)
            method = f"parser:{ext}"
        except DocumentProcessingError as exc:
            method = f"parser-failed: {str(exc)[:80]}"
    return add_evidence(db, complaint, modality=_modality_for(ext, modality_hint), file_name=Path(file_name).name,
                        text=text, method=method, stored_path=str(path), size_bytes=len(data), user_id=user_id)


def evidence_dict(item: EvidenceItem, include_text: bool = True) -> dict:
    return {
        "id": item.id, "modality": item.modality, "file_name": item.file_name, "size_bytes": item.size_bytes,
        "extraction_method": item.extraction_method, "facts": item.extracted_facts or {},
        "quarantined": item.quarantined, "injection": item.injection or {}, "pii": item.pii_counts or {},
        "text": (item.extracted_text if include_text else ""), "trust_level": "untrusted",
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "analyzed": bool(item.extracted_text.strip()),
    }


# ---------------------------------------------------------------------------
# Transactions
# ---------------------------------------------------------------------------

def transaction_for(db: Session, complaint: Complaint) -> Optional[TransactionRecord]:
    ref = (complaint.order_reference or "").strip()
    if not ref:
        return None
    return (db.query(TransactionRecord).filter(TransactionRecord.order_reference == ref)
            .order_by(TransactionRecord.id.desc()).first())


def transaction_dict(txn: Optional[TransactionRecord]) -> Optional[dict]:
    if txn is None:
        return None
    return {"id": txn.id, "order_reference": txn.order_reference, "product": txn.product, "amount": txn.amount,
            "currency": txn.currency, "payment_status": txn.payment_status, "delivery_status": txn.delivery_status,
            "refund_status": txn.refund_status, "customer_id": txn.customer_id, "source": txn.source,
            "placed_at": txn.placed_at.isoformat() if txn.placed_at else None}


# ---------------------------------------------------------------------------
# Cross-modal analysis
# ---------------------------------------------------------------------------

_CLAIM_LABEL = {
    "payment_failed": "payment failed", "not_delivered": "order not delivered", "refund_not_received": "refund not received",
    "damaged": "item arrived damaged", "overcharged": "overcharged / charged twice", "payment_deducted": "money deducted",
}


def analyze_evidence(db: Session, complaint: Complaint, working_text: str) -> dict:
    claims = extract_claims(working_text)
    txn = transaction_for(db, complaint)
    txn_facts = transaction_facts(txn)
    items = (db.query(EvidenceItem).filter(EvidenceItem.complaint_id == complaint.id)
             .order_by(EvidenceItem.id).all())
    usable = [i for i in items if not i.quarantined and i.extracted_text.strip()]

    conflicts: list[dict] = []
    supports: list[dict] = []
    missing: list[str] = []

    def add_conflict(kind, claim, source, detail, severity="high"):
        conflicts.append({"type": kind, "claim": claim, "contradicted_by": source, "detail": detail, "severity": severity})

    def check(claim: str, fact: str, opposite_label: str) -> None:
        if claim not in claims:
            return
        if txn is not None and txn_facts.get(fact):
            add_conflict("claim_vs_record", _CLAIM_LABEL[claim], "transaction record",
                         f"Customer states '{_CLAIM_LABEL[claim]}' but the transaction record shows {opposite_label}.")
        for item in usable:
            if (item.extracted_facts or {}).get(fact):
                add_conflict("claim_vs_evidence", _CLAIM_LABEL[claim], f"{item.modality}: {item.file_name}",
                             f"Customer states '{_CLAIM_LABEL[claim]}' but the {item.modality} evidence shows {opposite_label}.")

    check("payment_failed", "payment_success", "the payment was successful")
    check("not_delivered", "delivered", "the order was delivered")
    check("refund_not_received", "refund_issued", "a refund was issued")

    # evidence vs system-of-record disagreements
    if txn is not None:
        for item in usable:
            facts = item.extracted_facts or {}
            if facts.get("payment_failed") and txn_facts.get("payment_success"):
                add_conflict("evidence_vs_record", "evidence shows payment failed", "transaction record",
                             f"{item.file_name} shows a failed payment but the record shows success.", "medium")
            if facts.get("payment_success") and txn_facts.get("payment_failed"):
                add_conflict("evidence_vs_record", "evidence shows payment success", "transaction record",
                             f"{item.file_name} shows a successful payment but the record shows failure.", "medium")
            amounts = facts.get("amounts") or []
            if amounts and txn.amount and not any(abs(a - txn.amount) <= 0.05 * txn.amount for a in amounts):
                add_conflict("amount_discrepancy", "evidence amount", "transaction record",
                             f"Amounts in {item.file_name} {amounts[:3]} differ from the record ({txn.amount:.2f}).", "medium")
        if txn.customer_id and complaint.customer_id and txn.customer_id != complaint.customer_id:
            add_conflict("ownership_mismatch", "order ownership", "transaction record",
                         "The order reference belongs to a different customer account.", "high")

    ref = (complaint.order_reference or "").strip()
    for item in usable:
        refs = (item.extracted_facts or {}).get("order_refs") or []
        if ref and refs and ref not in refs:
            add_conflict("order_reference_mismatch", "order reference", f"{item.modality}: {item.file_name}",
                         f"Evidence references {', '.join(refs[:3])} but the complaint concerns {ref}.", "medium")

    # supporting evidence
    def support(claim: str, fact: str, label: str) -> None:
        if claim in claims:
            if txn is not None and txn_facts.get(fact):
                supports.append({"claim": _CLAIM_LABEL[claim], "source": "transaction record", "detail": label})
            for item in usable:
                if (item.extracted_facts or {}).get(fact):
                    supports.append({"claim": _CLAIM_LABEL[claim], "source": f"{item.modality}: {item.file_name}", "detail": label})

    support("payment_failed", "payment_failed", "payment failure confirmed")
    support("not_delivered", "not_delivered", "delivery not completed per record")
    support("refund_not_received", "refund_issued", "n/a")
    supports = [s for s in supports if s["detail"] != "n/a"]
    if "damaged" in claims:
        for item in usable:
            if (item.extracted_facts or {}).get("damage_visible"):
                supports.append({"claim": _CLAIM_LABEL["damaged"], "source": f"{item.modality}: {item.file_name}",
                                 "detail": "damage described in evidence"})
    if "refund_not_received" in claims and txn is not None and txn.refund_status == "requested":
        supports.append({"claim": _CLAIM_LABEL["refund_not_received"], "source": "transaction record",
                         "detail": "refund is recorded as requested but not issued"})

    needs = sorted(claims.keys() & VERIFY_CLAIMS)
    if needs and txn is None:
        missing.append("No transaction record found for the order reference" if ref else "No order reference provided")
    if needs and not usable:
        missing.append("No usable supporting evidence (document, screenshot or transcript) attached")
    unanalysed = [i for i in items if not i.extracted_text.strip() and not i.quarantined]
    for item in unanalysed:
        missing.append(f"{item.file_name} could not be read ({item.extraction_method}); add a transcription")
    quarantined = [i.file_name for i in items if i.quarantined]

    if conflicts:
        status = "CONFLICT"
    elif not needs:
        status = "NOT_REQUIRED"
    elif supports or (txn is not None and usable):
        status = "SUPPORTED"
    elif txn is None and not usable:
        status = "INSUFFICIENT"
    else:
        status = "SUPPORTED" if supports else "INSUFFICIENT"

    return {
        "status": status,
        "claims": [{"key": k, "label": _CLAIM_LABEL.get(k, k)} for k in claims],
        "conflicts": conflicts, "supports": supports, "missing": missing,
        "items": [evidence_dict(i, include_text=False) for i in items],
        "quarantined": quarantined,
        "transaction": transaction_dict(txn),
        "verification_required": bool(needs),
    }


# ---------------------------------------------------------------------------
# Demo transaction seeding (clearly labelled synthetic)
# ---------------------------------------------------------------------------

def _h(text: str) -> int:
    return int(hashlib.sha1(text.encode()).hexdigest()[:8], 16)


def seed_transactions(db: Session, limit: int = 2000) -> int:
    """Create a transaction record per complaint order reference (idempotent, labelled synthetic)."""
    have = {r[0] for r in db.query(TransactionRecord.order_reference).all()}
    created = 0
    rows = (db.query(Complaint).filter(Complaint.order_reference != "").order_by(Complaint.id).limit(limit).all())
    for c in rows:
        ref = c.order_reference.strip()
        if not ref or ref in have:
            continue
        claims = extract_claims(f"{c.title}\n{c.description}")
        payment, delivery, refund = "paid", "delivered", "none"
        if "not_delivered" in claims:
            delivery = ("delayed", "in_transit", "lost")[_h(ref) % 3]
        if "refund_not_received" in claims:
            refund = "requested"
        if "payment_failed" in claims:
            payment = "failed"
        # ~8% of records deliberately disagree with the customer's claim to exercise conflict detection
        if _h(ref + "x") % 100 < 8:
            if "not_delivered" in claims:
                delivery = "delivered"
            elif "payment_failed" in claims:
                payment = "paid"
            elif "refund_not_received" in claims:
                refund = "refunded"
        db.add(TransactionRecord(
            order_reference=ref, customer_id=c.customer_id, product=c.product_or_service or "",
            amount=round(15 + (_h(ref) % 38500) / 100, 2), currency=settings.nova_currency,
            payment_status=payment, delivery_status=delivery, refund_status=refund,
            placed_at=(c.complaint_date or utcnow()) - timedelta(days=10), source="synthetic-demo-seed"))
        have.add(ref)
        created += 1
    db.commit()
    return created
