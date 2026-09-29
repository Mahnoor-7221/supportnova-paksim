"""Knowledge retrieval / policy grounding.

Instead of sending the whole knowledge base to the model, relevant approved
chunks are retrieved with a dependency-free BM25-style scorer. Only documents
with status 'active' and chunks with trust_level 'approved' are searchable:
flagged (potentially malicious) uploads are excluded until an admin clears them.
"""
from __future__ import annotations

import math
import re
from collections import Counter

from sqlalchemy.orm import Session

from ..models import Document, DocumentChunk, DocumentVersion

_TOKEN = re.compile(r"[a-z0-9]+")

STOPWORDS = {
    "the", "and", "for", "with", "that", "this", "from", "have", "has", "was", "were",
    "are", "you", "your", "our", "but", "not", "all", "can", "will", "would", "there",
    "they", "them", "been", "into", "than", "then", "when", "what", "which", "who",
    "how", "why", "did", "does", "his", "her", "its", "it", "is", "of", "on", "in",
    "to", "a", "an", "i", "we", "my", "me", "be", "as", "at", "or", "if", "so", "do",
}


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall((text or "").lower()) if t not in STOPWORDS and len(t) > 2]


def _load_searchable_chunks(db: Session) -> list[dict]:
    rows = (
        db.query(DocumentChunk, Document, DocumentVersion)
        .join(Document, DocumentChunk.document_id == Document.id)
        .join(DocumentVersion, DocumentChunk.version_id == DocumentVersion.id)
        .filter(Document.status == "active")
        .filter(DocumentChunk.trust_level == "approved")
        .filter(DocumentVersion.is_current.is_(True))
        .all()
    )
    chunks = []
    for chunk, document, version in rows:
        chunks.append(
            {
                "chunk_id": chunk.id,
                "document_id": document.id,
                "document_code": document.code,
                "document_title": document.title,
                "doc_type": document.doc_type,
                "version": version.version,
                "section_id": chunk.section_id,
                "section_title": chunk.section_title,
                "page": chunk.page,
                "source_reference": chunk.source_reference or document.source_reference or document.title,
                "text": chunk.text,
            }
        )
    return chunks


def retrieve(db: Session, query_text: str, top_k: int = 6, min_score: float = 0.05) -> list[dict]:
    """Return the top_k most relevant approved chunks for the query."""
    chunks = _load_searchable_chunks(db)
    if not chunks:
        return []

    query_tokens = tokenize(query_text)
    if not query_tokens:
        return []
    query_counts = Counter(query_tokens)

    # document frequencies over the chunk corpus
    tokenized_corpus: list[Counter] = []
    df: Counter = Counter()
    for chunk in chunks:
        tokens = tokenize(chunk["text"]) + tokenize(chunk.get("section_title", ""))
        counts = Counter(tokens)
        tokenized_corpus.append(counts)
        for token in counts.keys():
            df[token] += 1

    total = len(chunks)
    avg_len = sum(sum(c.values()) for c in tokenized_corpus) / max(total, 1)
    k1, b = 1.5, 0.75

    scored: list[tuple[float, dict]] = []
    for chunk, counts in zip(chunks, tokenized_corpus):
        length = sum(counts.values()) or 1
        score = 0.0
        for token, q_count in query_counts.items():
            if token not in counts:
                continue
            idf = math.log(1 + (total - df[token] + 0.5) / (df[token] + 0.5))
            tf = counts[token]
            score += idf * ((tf * (k1 + 1)) / (tf + k1 * (1 - b + b * length / avg_len))) * q_count
        if score > 0:
            scored.append((score, chunk))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    results = []
    for score, chunk in scored[:top_k]:
        if score < min_score:
            continue
        enriched = dict(chunk)
        enriched["score"] = round(score, 4)
        results.append(enriched)
    return results


def format_policy_context(chunks: list[dict]) -> str:
    """Render retrieved chunks as a prompt-ready excerpt block."""
    if not chunks:
        return "NO APPROVED POLICY EXCERPTS FOUND FOR THIS COMPLAINT."
    blocks = []
    for chunk in chunks:
        blocks.append(
            f"[{chunk['document_code']} | {chunk['source_reference']} | "
            f"version {chunk['version']} | section {chunk['section_id']} | page {chunk['page']}]\n"
            f"{chunk['text']}"
        )
    return "\n\n---\n\n".join(blocks)


def collect_policy_references(chunks: list[dict]) -> list[dict]:
    """Compact references list stored alongside the analysis."""
    return [
        {
            "document_code": c["document_code"],
            "document_title": c["document_title"],
            "version": c["version"],
            "section_id": c["section_id"],
            "page": c["page"],
            "source_reference": c["source_reference"],
            "score": c.get("score", 0),
        }
        for c in chunks
    ]
