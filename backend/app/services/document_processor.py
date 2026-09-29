"""Document processing: validation, extraction, section detection, traceable chunking.

Supports PDF (pypdf) and DOCX (python-docx), plus MD/TXT for bundled
knowledge-base documents. Every chunk keeps its full source traceability:
document code, version, section, page and source reference.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Optional

from ..config import settings

HEADING_MD = re.compile(r"^(#{1,4})\s+(.+?)\s*$")
HEADING_NUM = re.compile(r"^(?:section\s+)?(\d+(?:\.\d+)*)[\.\):]?\s+(.{2,120})$", re.IGNORECASE)
HEADING_ALLCAPS = re.compile(r"^([A-Z][A-Z0-9 \-/&]{4,60})$")


class DocumentProcessingError(Exception):
    pass


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_upload(file_name: str, size_bytes: int) -> str:
    """Return the lowercase extension or raise DocumentProcessingError."""
    ext = Path(file_name or "").suffix.lower().lstrip(".")
    if not ext:
        raise DocumentProcessingError("File has no extension")
    if ext not in settings.allowed_extensions:
        raise DocumentProcessingError(
            f"File type '.{ext}' not allowed. Allowed: {sorted(settings.allowed_extensions)}"
        )
    max_bytes = settings.max_upload_mb * 1024 * 1024
    if size_bytes > max_bytes:
        raise DocumentProcessingError(
            f"File too large ({size_bytes / 1024 / 1024:.1f} MB). Limit: {settings.max_upload_mb} MB"
        )
    if size_bytes <= 0:
        raise DocumentProcessingError("File is empty")
    return ext


def file_checksum(path: str | Path) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(65536), b""):
            sha.update(block)
    return sha.hexdigest()


# ---------------------------------------------------------------------------
# Text extraction
# ---------------------------------------------------------------------------

def extract_units(path: str | Path, ext: str) -> list[dict]:
    """Extract text as a list of units: [{'text': str, 'page': int}].

    PDF: one unit per page (real page numbers preserved).
    DOCX: paragraph text grouped into one unit (page numbers are not
    available in DOCX; sections + numbering provide traceability).
    MD/TXT: single unit.
    """
    if ext == "pdf":
        return _extract_pdf(path)
    if ext == "docx":
        return _extract_docx(path)
    if ext in {"md", "txt"}:
        return _extract_text_file(path)
    raise DocumentProcessingError(f"Unsupported extension: {ext}")


def _extract_pdf(path: str | Path) -> list[dict]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise DocumentProcessingError("pypdf is required for PDF processing") from exc
    reader = PdfReader(str(path))
    units = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        units.append({"text": text, "page": index})
    if not any(u["text"].strip() for u in units):
        raise DocumentProcessingError("PDF contains no extractable text (scanned image?)")
    return units


def _extract_docx(path: str | Path) -> list[dict]:
    try:
        from docx import Document as DocxDocument
    except ImportError as exc:  # pragma: no cover
        raise DocumentProcessingError("python-docx is required for DOCX processing") from exc
    document = DocxDocument(str(path))
    lines: list[str] = []
    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        style = (paragraph.style.name or "").lower() if paragraph.style is not None else ""
        if "heading" in style:
            lines.append(f"# {text}")
        else:
            lines.append(text)
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                lines.append(" | ".join(cells))
    if not lines:
        raise DocumentProcessingError("DOCX contains no extractable text")
    return [{"text": "\n".join(lines), "page": 1}]


def _extract_text_file(path: str | Path) -> list[dict]:
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        raise DocumentProcessingError("Text file is empty")
    return [{"text": text, "page": 1}]


# ---------------------------------------------------------------------------
# Section detection
# ---------------------------------------------------------------------------

def detect_sections(units: list[dict]) -> list[dict]:
    """Split extracted units into numbered, traceable sections."""
    sections: list[dict] = []
    auto_counter = 0
    current: Optional[dict] = None

    def start_section(section_id: str, title: str, page: int) -> None:
        nonlocal current
        current = {
            "section_id": section_id,
            "title": title,
            "page": page,
            "lines": [],
        }
        sections.append(current)

    for unit in units:
        page = int(unit.get("page") or 1)
        for raw_line in (unit["text"] or "").splitlines():
            line = raw_line.strip()
            if not line:
                if current is not None:
                    current["lines"].append("")
                continue

            match_md = HEADING_MD.match(line)
            if match_md:
                title = match_md.group(2).strip()
                num_match = HEADING_NUM.match(title)
                section_id = num_match.group(1) if num_match else ""
                start_section(section_id, title, page)
                continue

            match_num = HEADING_NUM.match(line)
            if match_num and len(line) <= 130:
                start_section(match_num.group(1), line, page)
                continue

            match_caps = HEADING_ALLCAPS.match(line)
            if match_caps and len(line.split()) <= 8:
                auto_counter += 1
                start_section(f"S{auto_counter}", line.title(), page)
                continue

            if current is None:
                auto_counter += 1
                start_section(f"S{auto_counter}", "Preamble", page)
            current["lines"].append(line)

    # finalise
    cleaned: list[dict] = []
    for section in sections:
        text = "\n".join(section["lines"]).strip()
        if not text and section["title"]:
            text = section["title"]
        if not text:
            continue
        cleaned.append(
            {
                "section_id": section["section_id"] or f"S{len(cleaned) + 1}",
                "title": section["title"],
                "page": section["page"],
                "text": text,
            }
        )
    return cleaned


# ---------------------------------------------------------------------------
# Chunking with traceability
# ---------------------------------------------------------------------------

def chunk_sections(
    sections: list[dict],
    max_chars: int = 900,
    min_chars: int = 60,
    overlap: int = 120,
) -> list[dict]:
    """Split sections into chunks, preserving section/page traceability."""
    chunks: list[dict] = []
    for section in sections:
        paragraphs = [p.strip() for p in section["text"].split("\n") if p.strip()]
        buffer = ""
        for paragraph in paragraphs:
            candidate = (buffer + "\n" + paragraph).strip() if buffer else paragraph
            if len(candidate) <= max_chars:
                buffer = candidate
                continue
            if buffer:
                chunks.append(_make_chunk(section, buffer, len(chunks)))
            if len(paragraph) <= max_chars:
                buffer = paragraph
            else:
                # hard-split very long paragraphs with overlap
                start = 0
                while start < len(paragraph):
                    piece = paragraph[start : start + max_chars]
                    chunks.append(_make_chunk(section, piece, len(chunks)))
                    start += max_chars - overlap
                buffer = ""
        if buffer:
            if buffer and len(buffer) >= min_chars:
                chunks.append(_make_chunk(section, buffer, len(chunks)))
            elif chunks:
                chunks[-1]["text"] = chunks[-1]["text"] + "\n" + buffer
    return chunks


def _make_chunk(section: dict, text: str, index: int) -> dict:
    return {
        "section_id": section["section_id"],
        "section_title": section["title"],
        "page": section["page"],
        "chunk_index": index,
        "text": text.strip(),
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def process_file(path: str | Path, ext: str) -> dict:
    """Full pipeline: extract -> detect sections -> chunk."""
    units = extract_units(path, ext)
    sections = detect_sections(units)
    chunks = chunk_sections(sections)
    if not chunks:
        raise DocumentProcessingError("No usable text content found in document")
    page_count = max((u.get("page") or 1) for u in units) if ext == "pdf" else 1
    return {
        "sections": sections,
        "chunks": chunks,
        "page_count": page_count,
        "section_count": len(sections),
        "chunk_count": len(chunks),
        "checksum": file_checksum(path),
    }
