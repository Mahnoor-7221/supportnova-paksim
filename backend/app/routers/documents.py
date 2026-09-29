"""Knowledge base endpoints: upload, versions, chunks, quarantine handling."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy.orm import Session

from ..audit import log_action
from ..config import STORAGE_DIR
from ..database import get_db
from ..models import Document, DocumentChunk, DocumentVersion, User
from ..security import get_current_user, require_admin
from ..serializers import chunk_dict, document_dict, version_dict
from ..services import injection_guard
from ..services.document_processor import DocumentProcessingError, process_file, validate_upload
from ..services.security_events import log_security_event
from ..utils import utcnow

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _next_document_code(db: Session) -> str:
    count = db.query(Document).count()
    return f"DOC-{count + 1:03d}"


def _store_upload(file_bytes: bytes, file_name: str) -> Path:
    folder = STORAGE_DIR / "documents"
    folder.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file_name or "upload.bin").name
    stored = folder / f"{utcnow().strftime('%Y%m%d%H%M%S%f')}_{safe_name}"
    stored.write_bytes(file_bytes)
    return stored


def _ingest_version(
    db: Session,
    document: Document,
    version_label: str,
    is_first: bool,
    stored_path: Path,
    file_name: str,
    ext: str,
    processed: dict,
    scan: dict,
    user_id: Optional[int],
) -> DocumentVersion:
    if not is_first:
        db.query(DocumentVersion).filter(DocumentVersion.document_id == document.id).update({"is_current": False})

    version = DocumentVersion(
        document_id=document.id,
        version=version_label,
        effective_date=utcnow(),
        file_name=file_name,
        stored_path=str(stored_path),
        extension=ext,
        size_bytes=stored_path.stat().st_size if stored_path.exists() else 0,
        checksum=processed["checksum"],
        page_count=processed["page_count"],
        is_current=True,
        uploaded_by=user_id,
    )
    db.add(version)
    db.flush()

    flagged = bool(scan["suspected"] and scan.get("critical"))
    trust = "untrusted" if scan["suspected"] else "approved"
    for chunk_data in processed["chunks"]:
        chunk = chunk_data
        db.add(DocumentChunk(
            document_id=document.id,
            version_id=version.id,
            section_id=chunk["section_id"],
            section_title=chunk.get("section_title", ""),
            page=chunk.get("page", 1),
            chunk_index=chunk.get("chunk_index", 0),
            source_reference=document.source_reference or document.title,
            text=chunk["text"],
            injection_suspected=bool(scan["suspected"]),
            trust_level=trust,
        ))

    document.current_version = version_label
    if is_first:
        document.injection_flag = flagged or bool(scan.get("critical"))
        document.injection_notes = ", ".join(scan.get("matches", []))
        if document.injection_flag:
            document.status = "flagged"
    else:
        flagged_now = bool(scan.get("critical"))
        document.injection_flag = flagged_now
        document.injection_notes = ", ".join(scan.get("matches", []))
        if flagged_now:
            document.status = "flagged"
        elif document.status == "flagged":
            # latest version is clean; keep quarantined status for admin review
            document.injection_notes = (document.injection_notes or "") + " | latest version clean, awaiting admin review"
    document.updated_at = utcnow()

    if document.injection_flag:
        log_security_event(
            db,
            "document_quarantined",
            f"Document {document.code} quarantined — injection patterns detected",
            severity="high",
            document=document,
            detail={"matches": list(scan.get("matches") or [])[:6], "version": version_label},
        )
    elif scan["suspected"]:
        log_security_event(
            db,
            "document_flagged",
            f"Document {document.code} flagged as untrusted",
            severity="medium",
            document=document,
            detail={"matches": list(scan.get("matches") or [])[:6], "version": version_label},
        )
    return version


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_document(
    request: Request,
    file: UploadFile = File(...),
    title: str = Form(...),
    doc_type: str = Form("policy"),
    category: str = Form(""),
    source_reference: str = Form(""),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    content = await file.read()
    file_name = file.filename or "upload.bin"
    try:
        ext = validate_upload(file_name, len(content))
    except DocumentProcessingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    stored_path = _store_upload(content, file_name)
    try:
        processed = process_file(stored_path, ext)
    except DocumentProcessingError as exc:
        raise HTTPException(status_code=422, detail=f"Document processing failed: {exc}")

    full_text = "\n".join(chunk["text"] for chunk in processed["chunks"])
    scan = injection_guard.scan_document(full_text)

    document = Document(
        code=_next_document_code(db),
        title=title.strip(),
        doc_type=doc_type,
        category=category,
        source_reference=source_reference or title.strip(),
        status="active",
        current_version="v1",
        uploaded_by=admin.id,
    )
    db.add(document)
    db.flush()

    _ingest_version(db, document, "v1", True, stored_path, file_name, ext, processed, scan, admin.id)
    db.commit()
    db.refresh(document)

    log_action(db, "document.uploaded", "document", document.code,
               {"title": document.title, "chunks": processed["chunk_count"],
                "sections": processed["section_count"], "injection_flag": document.injection_flag,
                "scan_matches": scan.get("matches", [])},
               user=admin, request=request)

    return {
        "document": document_dict(document),
        "version": "v1",
        "sections": processed["section_count"],
        "chunks": processed["chunk_count"],
        "page_count": processed["page_count"],
        "injection_scan": scan,
        "quarantined": document.status == "flagged",
    }


@router.get("")
def list_documents(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    doc_type: Optional[str] = None,
    status_filter: Optional[str] = Query(None, alias="status"),
):
    query = db.query(Document)
    if doc_type:
        query = query.filter(Document.doc_type == doc_type)
    if status_filter:
        query = query.filter(Document.status == status_filter)
    documents = query.order_by(Document.id.desc()).all()
    return [
        {
            **document_dict(document),
            "chunk_count": db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).count(),
            "version_count": db.query(DocumentVersion).filter(DocumentVersion.document_id == document.id).count(),
        }
        for document in documents
    ]


@router.get("/{document_id}")
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    chunk_offset: int = Query(0, ge=0),
    chunk_limit: int = Query(40, ge=1, le=200),
):
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    versions = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.document_id == document.id)
        .order_by(DocumentVersion.id.desc())
        .all()
    )
    chunks = (
        db.query(DocumentChunk)
        .filter(DocumentChunk.document_id == document.id)
        .order_by(DocumentChunk.chunk_index)
        .offset(chunk_offset)
        .limit(chunk_limit)
        .all()
    )
    total_chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).count()
    return {
        "document": document_dict(document),
        "versions": [version_dict(v) for v in versions],
        "chunks": [chunk_dict(c) for c in chunks],
        "total_chunks": total_chunks,
    }


@router.post("/{document_id}/version", status_code=status.HTTP_201_CREATED)
async def upload_new_version(
    document_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    content = await file.read()
    file_name = file.filename or "upload.bin"
    try:
        ext = validate_upload(file_name, len(content))
    except DocumentProcessingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    stored_path = _store_upload(content, file_name)
    try:
        processed = process_file(stored_path, ext)
    except DocumentProcessingError as exc:
        raise HTTPException(status_code=422, detail=f"Document processing failed: {exc}")

    scan = injection_guard.scan_document("\n".join(chunk["text"] for chunk in processed["chunks"]))
    current_number = int((document.current_version or "v1").lstrip("v") or "1")
    new_label = f"v{current_number + 1}"

    _ingest_version(db, document, new_label, False, stored_path, file_name, ext, processed, scan, admin.id)
    db.commit()
    db.refresh(document)

    log_action(db, "document.version_added", "document", document.code,
               {"version": new_label, "chunks": processed["chunk_count"],
                "injection_flag": document.injection_flag}, user=admin, request=request)
    return {
        "document": document_dict(document),
        "version": new_label,
        "sections": processed["section_count"],
        "chunks": processed["chunk_count"],
        "injection_scan": scan,
    }


@router.post("/{document_id}/clear-flag")
def clear_flag(
    document_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")

    document.injection_flag = False
    document.injection_notes = "Cleared by admin after review"
    if document.status == "flagged":
        document.status = "active"
    document.updated_at = utcnow()
    db.query(DocumentChunk).filter(DocumentChunk.document_id == document.id).update(
        {"trust_level": "approved", "injection_suspected": False}
    )
    db.commit()
    log_action(db, "document.flag_cleared", "document", document.code, {}, user=admin, request=request)
    return document_dict(document)


@router.post("/{document_id}/archive")
def archive_document(
    document_id: int,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    document.status = "archived"
    document.updated_at = utcnow()
    db.commit()
    log_action(db, "document.archived", "document", document.code, {}, user=admin, request=request)
    return document_dict(document)
