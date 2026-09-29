"""Knowledge upgrade: hybrid retrieval, citation grounding, policy version tracking.

* Hybrid retrieval = BM25 keyword retrieval (v1 ``services.retrieval``) fused with
  a TF-IDF/synonym semantic index using Reciprocal Rank Fusion.
* Every claim the AI makes can be traced to SOURCE / DOCUMENT / SECTION / VERSION /
  EXCERPT. Excerpts are verified to be literal substrings of the stored chunk —
  a citation that cannot be verified is never emitted.
* If nothing supports a claim the answer is literally ``Insufficient evidence.``
"""
from __future__ import annotations

import math
import re
from typing import Optional

from sqlalchemy.orm import Session

from ..models import (
    ComplaintCategory,
    ComplaintRule,
    Department,
    Document,
    DocumentChunk,
    DocumentVersion,
    Policy,
)
from ..services import retrieval
from ..services import genai_client
from ..config import settings
from . import intent_classifier
from .similarity import TfidfIndex, tokens

INSUFFICIENT = "Insufficient evidence."
_RRF_K = 60
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n{2,}|\n(?=[-*#\d])")

_INDEX_CACHE: dict = {"key": None, "index": None}


def _semantic_index(chunks: list[dict]) -> TfidfIndex:
    key = (len(chunks), max((c["chunk_id"] for c in chunks), default=0), sum(len(c["text"]) for c in chunks))
    if _INDEX_CACHE["key"] != key:
        _INDEX_CACHE.update(key=key, index=TfidfIndex((c["chunk_id"], f"{c.get('section_title', '')} {c['text']}") for c in chunks))
    return _INDEX_CACHE["index"]


def effective_dates(db: Session, document_ids: set[int]) -> dict[int, dict]:
    if not document_ids:
        return {}
    rows = (db.query(DocumentVersion).filter(DocumentVersion.document_id.in_(document_ids),
                                             DocumentVersion.is_current.is_(True)).all())
    return {r.document_id: {"version": r.version, "effective_date": r.effective_date.isoformat() if r.effective_date else None}
            for r in rows}


def hybrid_retrieve(db: Session, query: str, top_k: int = 6) -> list[dict]:
    """Keyword + semantic retrieval fused with RRF. Only approved, current, non-quarantined chunks."""
    pool = retrieval._load_searchable_chunks(db)  # noqa: SLF001 (shared v1 loader keeps the trust filters)
    if not pool or not (query or "").strip():
        return []
    by_id = {c["chunk_id"]: c for c in pool}

    keyword = retrieval.retrieve(db, query, top_k=max(top_k * 2, 10), min_score=0.05)
    k_rank = {c["chunk_id"]: i + 1 for i, c in enumerate(keyword)}
    semantic = _semantic_index(pool).query(query, top_k=max(top_k * 2, 10))
    s_rank = {cid: i + 1 for i, (cid, _score) in enumerate(semantic)}
    s_score = dict(semantic)

    fused: dict[int, float] = {}
    for cid in set(k_rank) | set(s_rank):
        fused[cid] = (1 / (_RRF_K + k_rank[cid]) if cid in k_rank else 0.0) + \
                     (1 / (_RRF_K + s_rank[cid]) if cid in s_rank else 0.0)

    ordered = sorted(fused, key=lambda cid: fused[cid], reverse=True)[:top_k]
    dates = effective_dates(db, {by_id[cid]["document_id"] for cid in ordered})
    results = []
    for cid in ordered:
        chunk = dict(by_id[cid])
        kw = next((c for c in keyword if c["chunk_id"] == cid), None)
        chunk["score"] = round(kw["score"], 4) if kw else round(s_score.get(cid, 0.0), 4)
        chunk["retrieval"] = {
            "methods": [m for m, present in (("keyword-bm25", cid in k_rank), ("semantic-tfidf", cid in s_rank)) if present],
            "keyword_rank": k_rank.get(cid), "semantic_rank": s_rank.get(cid),
            "semantic_similarity": round(s_score.get(cid, 0.0), 3), "fused_score": round(fused[cid], 5),
        }
        chunk["effective_date"] = dates.get(chunk["document_id"], {}).get("effective_date")
        results.append(chunk)
    return results


def _sentences(text: str) -> list[tuple[int, int]]:
    spans, start = [], 0
    for match in _SENTENCE.finditer(text):
        end = match.start()
        if text[start:end].strip():
            spans.append((start, end))
        start = match.end()
    if text[start:].strip():
        spans.append((start, len(text)))
    return spans


def _best_excerpt(text: str, question: str, max_len: int = 360) -> tuple[str, int]:
    """Choose the sentence span that best overlaps the question. Always a literal substring."""
    q_tokens = {t for t in tokens(question) if "_" not in t}
    best, best_score = (0, min(len(text), max_len)), -1
    for start, end in _sentences(text):
        overlap = len({t for t in tokens(text[start:end]) if "_" not in t} & q_tokens)
        if overlap > best_score:
            best_score, best = overlap, (start, min(end, start + max_len))
    return text[best[0]:best[1]].strip(), max(best_score, 0)


def citation_for(chunk: dict, excerpt: str) -> dict:
    return {
        "chunk_id": chunk["chunk_id"], "document_id": chunk["document_id"],
        "document_code": chunk["document_code"], "document": chunk["document_title"],
        "section_id": chunk.get("section_id", ""), "section_title": chunk.get("section_title", ""),
        "version": chunk["version"], "page": chunk.get("page", 1),
        "effective_date": chunk.get("effective_date"), "source": chunk.get("source_reference", ""),
        "excerpt": excerpt, "verified": excerpt in chunk["text"],
    }


def customer_answer(
    db: Session,
    question: str,
    top_k: int = 5,
    original_question: Optional[str] = None,
    language_label: str = "English",
    previous_category: Optional[str] = None,
    history: Optional[list] = None,
) -> dict:
    """Generate a plain-language, customer-facing answer grounded in approved policy excerpts.

    Every message is first run through the deterministic ``intent_classifier`` so the
    customer NEVER receives the same generic reply regardless of what they asked --
    each issue type (SIM fault, lost/stolen SIM, fraud, harassment, recharge, internet,
    etc.) gets its own correct, actionable answer, and safety-critical issues are always
    flagged with ``escalate=True`` for a human agent, independent of whether the GenAI
    provider is configured or reachable.

    For non-critical issues, if Gemini is available it is used to lightly personalise the
    already-correct classifier answer (grounded in it, plus any approved policy excerpts,
    so it can never contradict the safe baseline). Critical issues (theft, fraud,
    harassment) always use the exact vetted script -- they are never left to a generative
    model to improvise.
    """
    chunks = hybrid_retrieve(db, question, top_k=max(top_k, 5))
    citations = []
    context_parts = []
    for chunk in chunks:
        excerpt, overlap = _best_excerpt(chunk["text"], question, max_len=700)
        if excerpt:
            citations.append(citation_for(chunk, excerpt))
            context_parts.append(
                f"[{chunk['document_code']} | {chunk['source_reference']} | version {chunk['version']} | section {chunk.get('section_id','')}]\n{excerpt}"
            )

    classification = intent_classifier.classify(
        original_question or question, previous_category=previous_category
    )
    answer = classification["answer"]
    clarification_questions = classification.get("clarification_questions", [])
    needs_details = bool(clarification_questions)

    # Deterministic issue matches are the source of truth for customer support.
    # Do not let a generative model rewrite a known telecom intent: that can turn a
    # precise answer (for example recharge/balance) into a generic or unrelated reply.
    # AI may still be used by separate staff/RAG tooling, but the customer command
    # center uses the vetted intent answer for recognized customer intents.
    if classification["id"] == "general_inquiry" or classification.get("confidence", 1) < 0.3:
        # Offline + unsure: ask instead of giving an off-topic answer.
        answer = (
            "Maazrat, main aapka sawal theek se samajh nahi saka. "
            "Kya aap thora wazeh bata sakte hain — masla SIM, calls, internet, balance/recharge, "
            "package, SMS, ya kisi complaint se related hai?"
        )

    return {
        "answer": answer,
        "insufficient": False,
        "needs_details": needs_details,
        "clarification_questions": clarification_questions,
        "citations": citations[:top_k],
        "retrieved": len(chunks),
        "category": classification["id"],
        "severity": classification["severity"],
        "escalate": classification["escalate"],
        "escalation_reason": classification.get("escalation_reason", ""),
        "department": classification.get("department", ""),
        "priority": classification.get("priority", ""),
        "title": classification.get("title", ""),
        "follow_up": classification.get("follow_up", False),
    }


def answer_question(db: Session, question: str, top_k: int = 3) -> dict:
    """Extractive, citation-grounded answer. Never invents a source."""
    chunks = hybrid_retrieval_for_question(db, question, top_k)
    q_tokens = {t for t in tokens(question) if "_" not in t}
    citations, parts = [], []
    for chunk in chunks:
        excerpt, overlap = _best_excerpt(chunk["text"], question)
        need = 1 if len(q_tokens) <= 2 else max(2, math.ceil(0.34 * len(q_tokens)))
        if not excerpt or overlap < need:
            continue
        citation = citation_for(chunk, excerpt)
        if citation["verified"]:
            citations.append(citation)
            parts.append(excerpt)
    if not citations:
        return {"answer": INSUFFICIENT, "insufficient": True, "citations": [], "retrieved": len(chunks)}
    return {"answer": " ".join(dict.fromkeys(parts))[:900], "insufficient": False,
            "citations": citations[:top_k], "retrieved": len(chunks)}


def hybrid_retrieval_for_question(db: Session, question: str, top_k: int) -> list[dict]:
    return hybrid_retrieve(db, question, top_k=max(top_k, 4))


def ground_claim(db: Session, claim: str) -> dict:
    """Find the best approved source for one claim, else ``Insufficient evidence.``"""
    result = answer_question(db, claim, top_k=1)
    if result["insufficient"]:
        return {"claim": claim, "supported": False, "note": INSUFFICIENT, "citation": None}
    return {"claim": claim, "supported": True, "note": "supported by approved source", "citation": result["citations"][0]}


# ---------------------------------------------------------------------------
# Policy version tracking
# ---------------------------------------------------------------------------

def policy_versions(db: Session) -> list[dict]:
    out = []
    for doc in db.query(Document).order_by(Document.code).all():
        versions = sorted(doc.versions, key=lambda v: v.id)
        current = next((v for v in reversed(versions) if v.is_current), None)
        policy_ids = [p.policy_id for p in db.query(Policy).filter(Policy.document_id == doc.id).all()]
        out.append({
            "document_id": doc.id, "code": doc.code, "title": doc.title, "status": doc.status,
            "policy_ids": policy_ids, "current_version": current.version if current else doc.current_version,
            "effective_date": current.effective_date.isoformat() if current and current.effective_date else None,
            "superseded": [{"version": v.version, "effective_date": v.effective_date.isoformat() if v.effective_date else None}
                           for v in versions if not v.is_current],
            "trust": "quarantined" if doc.injection_flag or doc.status == "flagged" else "approved",
            "chunk_count": db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).count(),
        })
    return out


_CITED_VERSION = re.compile(r"\b([A-Z]{2,4}-POL-\d+)\b[^\n.]{0,50}?\b(?:v|version\s*)(\d+)\b", re.IGNORECASE)


def find_superseded_citations(db: Session, text: str) -> list[dict]:
    """Detect text that cites an outdated policy version (e.g. cites v1 when v2 is current)."""
    found = []
    for match in _CITED_VERSION.finditer(text or ""):
        policy_id, cited = match.group(1).upper(), f"v{match.group(2)}"
        policy = db.query(Policy).filter(Policy.policy_id == policy_id).first()
        if policy is None or policy.document_id is None:
            continue
        doc = db.get(Document, policy.document_id)
        current = (doc.current_version if doc else policy.version) or policy.version
        if current and cited.lower() != current.lower():
            found.append({"policy_id": policy_id, "cited_version": cited, "current_version": current,
                          "message": f"{policy_id} cited as {cited} but {current} is current"})
    return found


# ---------------------------------------------------------------------------
# Knowledge graph
# ---------------------------------------------------------------------------

def knowledge_graph(db: Session, focus: Optional[str] = None) -> dict:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    def node(nid: str, kind: str, label: str, **extra) -> str:
        nodes.setdefault(nid, {"id": nid, "type": kind, "label": label, **extra})
        return nid

    def edge(a: str, b: str, rel: str, source: str) -> None:
        edges.append({"source": a, "target": b, "relation": rel, "evidence_source": source, "confidence": 1.0, "basis": "recorded"})

    docs = {d.id: d for d in db.query(Document).all()}
    for d in docs.values():
        node(f"doc:{d.code}", "Document", d.title, version=d.current_version, status=d.status,
             sections=db.query(DocumentChunk).filter(DocumentChunk.document_id == d.id).count())
    policies = db.query(Policy).all()
    for p in policies:
        node(f"policy:{p.policy_id}", "Policy", p.title or p.policy_id, version=p.version)
        if p.document_id in docs:
            edge(f"doc:{docs[p.document_id].code}", f"policy:{p.policy_id}", "defines", f"db:policies#{p.id}")
    for c in db.query(ComplaintCategory).all():
        node(f"cat:{c.name}", "Category", c.name, sla_hours=c.sla_hours)
    for d in db.query(Department).all():
        node(f"dept:{d.name}", "Department", d.name)
    for r in db.query(ComplaintRule).filter(ComplaintRule.is_active.is_(True)).all():
        rid = node(f"rule:{r.rule_id}", "Rule", f"{r.rule_id} {r.subcategory}", priority=r.priority, escalation=r.escalation)
        edge(rid, f"cat:{r.category}", "applies_to", f"db:complaint_rules#{r.id}")
        if r.department:
            node(f"dept:{r.department}", "Department", r.department)
            edge(rid, f"dept:{r.department}", "routes_to", f"db:complaint_rules#{r.id}")
        if r.policy_id and f"policy:{r.policy_id}" in nodes:
            edge(rid, f"policy:{r.policy_id}", "governed_by", f"db:complaint_rules#{r.id}")
        if r.escalation and r.escalation_department:
            node(f"dept:{r.escalation_department}", "Department", r.escalation_department)
            edge(rid, f"dept:{r.escalation_department}", "escalates_to", f"db:complaint_rules#{r.id}")

    if focus:
        wanted = {n for n in nodes if focus.lower() in n.lower() or focus.lower() in nodes[n]["label"].lower()}
        neighbours = {e["source"] for e in edges if e["target"] in wanted} | {e["target"] for e in edges if e["source"] in wanted}
        keep = wanted | neighbours
        # add section nodes for focused documents
        for nid in list(wanted):
            if nid.startswith("doc:"):
                code = nid[4:]
                doc = next((d for d in docs.values() if d.code == code), None)
                if doc:
                    for ch in db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).limit(40).all():
                        sid = node(f"sec:{ch.id}", "Section", f"§{ch.section_id} {ch.section_title}".strip()[:60])
                        edge(nid, sid, "contains", f"db:document_chunks#{ch.id}")
                        keep.add(sid)
        nodes_out = [n for n in nodes.values() if n["id"] in keep]
        edges_out = [e for e in edges if e["source"] in keep and e["target"] in keep]
    else:
        nodes_out, edges_out = list(nodes.values()), edges
    return {"nodes": nodes_out, "edges": edges_out, "focus": focus}
