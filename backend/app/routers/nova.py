"""SupportNova v2 API surface: investigations, evidence, knowledge graph,
CAPA, feedback, evaluation, Red-Team 2.0, analytics and the assistant.

All endpoints are additive under /api/nova/* -- nothing here replaces a v1
route.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from ..audit import log_action
from ..config import settings
from ..database import get_db
from ..models import Complaint, DatasetCase, ManualReview, User
from ..models_nova import CapaRecord, EvalRun, Investigation
from ..security import get_current_user, require_admin, require_staff
from ..serializers import complaint_brief, complaint_full, review_dict
from ..services.trust_engine import latest_assessment, serialize_assessment
from ..nova import analytics, assistant, capa as capa_mod, evidence as evidence_mod
from ..nova import governance, investigate, memory, rag, redteam2, sla
from ..nova.evaluation import compare_runs, eval_dict, run_evaluation

router = APIRouter(prefix="/api/nova", tags=["nova"])


def _complaint_or_404(db: Session, complaint_id: int) -> Complaint:
    complaint = db.get(Complaint, complaint_id)
    if complaint is None:
        raise HTTPException(404, "Complaint not found")
    return complaint


def _ensure_access(complaint: Complaint, user: User) -> None:
    staff = bool(user.role and user.role.name in {"admin", "agent"})
    if not staff and complaint.customer_id != user.id and complaint.created_by != user.id:
        raise HTTPException(403, "You can only access your own complaints")


def _investigation_or_404(db: Session, investigation_id: int) -> Investigation:
    row = db.get(Investigation, investigation_id)
    if row is None:
        raise HTTPException(404, "Investigation not found")
    return row


# ---------------------------------------------------------------------------
# Investigations / Case Room
# ---------------------------------------------------------------------------

@router.post("/investigations/{complaint_id}")
def run_investigation(complaint_id: int, tone: str = "Professional", force: bool = False,
                      db: Session = Depends(get_db), user: User = Depends(require_staff)):
    complaint = _complaint_or_404(db, complaint_id)
    investigation = investigate.run_investigation(db, complaint, user, tone=tone, force_reanalyze=force)
    log_action(db, "nova.investigation.run", "complaint", complaint.code, {"investigation_id": investigation.id}, user=user)
    return investigate.investigation_dict(db, investigation)


@router.get("/investigations/{complaint_id}")
def get_latest_investigation(complaint_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    complaint = _complaint_or_404(db, complaint_id)
    _ensure_access(complaint, user)
    investigation = investigate.latest_investigation(db, complaint_id)
    if investigation is None:
        return None
    return investigate.investigation_dict(db, investigation)


@router.get("/investigations/by-id/{investigation_id}")
def get_investigation(investigation_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    investigation = _investigation_or_404(db, investigation_id)
    complaint = _complaint_or_404(db, investigation.complaint_id)
    _ensure_access(complaint, user)
    return investigate.investigation_dict(db, investigation)


@router.post("/investigations/{investigation_id}/decision")
def decide_investigation(investigation_id: int, decision: str = Form(...), notes: str = Form(""),
                         db: Session = Depends(get_db), user: User = Depends(require_staff)):
    investigation = _investigation_or_404(db, investigation_id)
    try:
        investigation = investigate.human_decide(db, investigation, decision, notes, user)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    log_action(db, "nova.investigation.decision", "investigation", investigation_id, {"decision": decision}, user=user)
    return investigate.investigation_dict(db, investigation)


@router.post("/investigations/{investigation_id}/challenge")
def challenge_investigation(investigation_id: int, target: str = Form(...), question: str = Form(""),
                            db: Session = Depends(get_db), user: User = Depends(require_staff)):
    investigation = _investigation_or_404(db, investigation_id)
    try:
        return investigate.challenge(db, investigation, target, question, user)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/investigations/{investigation_id}/feedback")
def feedback_investigation(investigation_id: int, verdict: str = Form(...), target: str = Form("overall"),
                           notes: str = Form(""), db: Session = Depends(get_db), user: User = Depends(require_staff)):
    investigation = _investigation_or_404(db, investigation_id)
    try:
        row = memory.submit_feedback(db, investigation, verdict, target, notes, user.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    db.commit()
    return {"id": row.id, "verdict": row.verdict, "target": row.target}


@router.get("/feedback/dashboard")
def feedback_dashboard(db: Session = Depends(get_db), user: User = Depends(require_staff)):
    return memory.feedback_dashboard(db)


@router.get("/case-room/{complaint_id}")
def case_room(complaint_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    complaint = _complaint_or_404(db, complaint_id)
    _ensure_access(complaint, user)
    investigation = investigate.latest_investigation(db, complaint_id)
    items = evidence_mod.analyze_evidence(db, complaint, complaint.description + " " + (complaint.translated_text or ""))
    return {
        "complaint": complaint_full(complaint),
        "investigation": investigate.investigation_dict(db, investigation) if investigation else None,
        "trust": serialize_assessment(latest_assessment(db, complaint_id)) if latest_assessment(db, complaint_id) else None,
        "evidence": items,
        "sla": sla.sla_status(complaint),
        "capa": [capa_mod.capa_dict(c) for c in db.query(CapaRecord).filter(CapaRecord.complaint_id == complaint_id).all()],
        "memory": memory.memory_visibility(db, complaint_id),
    }


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------

@router.post("/evidence/{complaint_id}/upload")
async def upload_evidence(complaint_id: int, file: UploadFile = File(...), transcript: str = Form(""),
                          modality_hint: str = Form(""), db: Session = Depends(get_db),
                          user: User = Depends(get_current_user)):
    complaint = _complaint_or_404(db, complaint_id)
    _ensure_access(complaint, user)
    data = await file.read()
    try:
        item = evidence_mod.ingest_upload(db, complaint, file.filename or "evidence", data, user.id,
                                          transcript=transcript, modality_hint=modality_hint)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    db.commit()
    log_action(db, "nova.evidence.upload", "complaint", complaint.code, {"file": item.file_name}, user=user)
    return evidence_mod.evidence_dict(item)


@router.get("/evidence/{complaint_id}")
def list_evidence(complaint_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    complaint = _complaint_or_404(db, complaint_id)
    _ensure_access(complaint, user)
    return evidence_mod.analyze_evidence(db, complaint, complaint.description)


# ---------------------------------------------------------------------------
# Knowledge / graphs / RAG
# ---------------------------------------------------------------------------

@router.get("/knowledge-graph")
def knowledge_graph(focus: Optional[str] = None, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    return rag.knowledge_graph(db, focus=focus)


@router.get("/evidence-graph/{complaint_id}")
def evidence_graph(complaint_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    complaint = _complaint_or_404(db, complaint_id)
    _ensure_access(complaint, user)
    investigation = investigate.latest_investigation(db, complaint_id)
    if investigation and investigation.graph:
        return investigation.graph
    return rag.knowledge_graph(db, focus=complaint.issue_category or None)


@router.get("/policy-versions")
def policy_versions(db: Session = Depends(get_db), user: User = Depends(require_staff)):
    return rag.policy_versions(db)


@router.get("/rag/ask")
def rag_ask(q: str = Query(..., min_length=2), db: Session = Depends(get_db), user: User = Depends(require_staff)):
    return rag.answer_question(db, q)


@router.get("/similar-cases/{complaint_id}")
def similar_cases(complaint_id: int, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    from ..nova.similarity import similar_cases as sim
    complaint = _complaint_or_404(db, complaint_id)
    return sim(db, complaint)


# ---------------------------------------------------------------------------
# CAPA
# ---------------------------------------------------------------------------

@router.get("/capa")
def list_capa(status_filter: Optional[str] = Query(None, alias="status"), db: Session = Depends(get_db),
             user: User = Depends(require_staff)):
    q = db.query(CapaRecord)
    if status_filter:
        q = q.filter(CapaRecord.status == status_filter)
    return [capa_mod.capa_dict(c) for c in q.order_by(CapaRecord.id.desc()).all()]


@router.post("/capa/{capa_id}/approve")
def approve_capa(capa_id: int, notes: str = Form(""), db: Session = Depends(get_db), user: User = Depends(require_admin)):
    record = db.get(CapaRecord, capa_id)
    if record is None:
        raise HTTPException(404, "CAPA not found")
    capa_mod.decide_capa(db, record, "APPROVED", user, notes)
    db.commit()
    log_action(db, "nova.capa.approved", "capa", record.code, {}, user=user)
    return capa_mod.capa_dict(record)


@router.post("/capa/{capa_id}/reject")
def reject_capa(capa_id: int, notes: str = Form(""), db: Session = Depends(get_db), user: User = Depends(require_admin)):
    record = db.get(CapaRecord, capa_id)
    if record is None:
        raise HTTPException(404, "CAPA not found")
    capa_mod.decide_capa(db, record, "REJECTED", user, notes)
    db.commit()
    log_action(db, "nova.capa.rejected", "capa", record.code, {}, user=user)
    return capa_mod.capa_dict(record)


# ---------------------------------------------------------------------------
# Evaluation Center / Red-Team 2.0
# ---------------------------------------------------------------------------

@router.post("/eval/run")
def eval_run(limit: int = 40, split: str = "unseen", seed: int = 7, db: Session = Depends(get_db),
            user: User = Depends(require_admin)):
    run = run_evaluation(db, limit=limit, split=split, seed=seed, created_by=user.id)
    return eval_dict(run)


@router.get("/eval")
def eval_list(db: Session = Depends(get_db), user: User = Depends(require_staff)):
    rows = db.query(EvalRun).filter(EvalRun.kind == "evaluation").order_by(EvalRun.id.desc()).limit(20).all()
    return [eval_dict(r) for r in rows]


@router.get("/eval/{eval_id}")
def eval_detail(eval_id: int, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    row = db.get(EvalRun, eval_id)
    if row is None:
        raise HTTPException(404, "Not found")
    return eval_dict(row)


@router.get("/eval/compare")
def eval_compare(a: int, b: int, db: Session = Depends(get_db), user: User = Depends(require_staff)):
    ra, rb = db.get(EvalRun, a), db.get(EvalRun, b)
    if ra is None or rb is None:
        raise HTTPException(404, "Run not found")
    return compare_runs(ra, rb)


@router.post("/redteam2/run")
def redteam2_run(db: Session = Depends(get_db), user: User = Depends(require_staff)):
    run = redteam2.run_redteam2(db, created_by=user.id)
    return {"id": run.id, "metrics": run.metrics, "results": run.results}


@router.get("/redteam2")
def redteam2_list(db: Session = Depends(get_db), user: User = Depends(require_staff)):
    rows = db.query(EvalRun).filter(EvalRun.kind == "redteam2").order_by(EvalRun.id.desc()).limit(10).all()
    return [{"id": r.id, "metrics": r.metrics, "results": r.results, "created_at": r.created_at.isoformat()} for r in rows]


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

@router.get("/analytics/early-warning")
def early_warning(db: Session = Depends(get_db), user: User = Depends(require_staff)):
    return analytics.early_warning(db)


@router.get("/analytics/anomalies")
def anomalies(db: Session = Depends(get_db), user: User = Depends(require_staff)):
    return analytics.anomaly_detection(db)


@router.post("/analytics/digital-twin")
def digital_twin(levers: dict, db: Session = Depends(get_db), user: User = Depends(require_admin)):
    return analytics.digital_twin_simulate(db, levers)


# ---------------------------------------------------------------------------
# Assistant (voice + text command center)
# ---------------------------------------------------------------------------

@router.post("/assistant/message")
def assistant_message(text: str = Form(...), session_id: Optional[str] = Form(None), modality: str = Form("text"),
                      db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    session = assistant.get_or_create_session(db, user, session_id)
    result = assistant.handle_message(db, session, text, user, modality=modality)
    result["session_id"] = session.uuid
    return result


@router.post("/assistant/voice")
async def assistant_voice(
    audio: UploadFile = File(...),
    session_id: Optional[str] = Form(None),
    language_hint: str = Form(""),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Server-side voice path: uploaded audio -> Gemini STT -> normal validated assistant pipeline."""
    from ..nova.media import ProviderUnavailable, transcribe_audio

    filename = (audio.filename or "voice.webm").lower()
    ext = filename.rsplit(".", 1)[-1] if "." in filename else "webm"
    allowed = {x.strip().lower() for x in settings.nova_audio_extensions.split(",") if x.strip()}
    if ext not in allowed:
        raise HTTPException(400, f"Unsupported audio type: .{ext}. Allowed: {sorted(allowed)}")
    data = await audio.read()
    if len(data) > settings.nova_audio_max_mb * 1024 * 1024:
        raise HTTPException(413, "Audio file is too large")
    mime = audio.content_type or {
        "webm": "audio/webm", "ogg": "audio/ogg", "mp3": "audio/mpeg",
        "wav": "audio/wav", "m4a": "audio/mp4"
    }.get(ext, "application/octet-stream")
    try:
        transcript = transcribe_audio(data, mime, language_hint=language_hint)
    except ProviderUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    text = transcript.get("text", "").strip()
    if not text:
        raise HTTPException(422, "No speech could be transcribed from the audio")
    session = assistant.get_or_create_session(db, user, session_id)
    result = assistant.handle_message(db, session, text, user, modality="voice")
    result["session_id"] = session.uuid
    result["transcript"] = text
    result["stt"] = transcript
    return result


@router.get("/assistant/history")
def assistant_history(session_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    session = assistant.get_or_create_session(db, user, session_id)
    return assistant.history(db, session)


@router.get("/assistant/sessions")
def assistant_sessions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Return the customer's own chat sessions with a compact preview.

    Sessions are strictly scoped to the authenticated user. This powers the
    customer-facing chat history page without exposing another customer's
    conversations.
    """
    from ..models_nova import AssistantMessage, AssistantSession
    sessions = (db.query(AssistantSession)
        .filter(AssistantSession.user_id == user.id)
        .order_by(AssistantSession.created_at.desc())
        .limit(50).all())
    result = []
    for session in sessions:
        messages = (db.query(AssistantMessage)
            .filter(AssistantMessage.session_id == session.id)
            .order_by(AssistantMessage.id.asc()).limit(4).all())
        if not messages:
            continue
        first_user = next((m for m in messages if m.role == "user"), messages[0])
        last = (db.query(AssistantMessage)
            .filter(AssistantMessage.session_id == session.id)
            .order_by(AssistantMessage.id.desc()).first())
        result.append({
            "session_id": session.uuid,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "title": (first_user.text or "Nova conversation")[:70],
            "preview": (last.text or "")[:160],
            "language": first_user.language or "en",
            "message_count": db.query(AssistantMessage).filter(AssistantMessage.session_id == session.id).count(),
        })
    return result


@router.get("/assistant/memory/{complaint_id}")
def assistant_memory(complaint_id: int, session_id: Optional[str] = None, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)):
    complaint = _complaint_or_404(db, complaint_id)
    _ensure_access(complaint, user)
    return memory.memory_visibility(db, complaint_id, session_uuid=session_id or "", owner_user_id=user.id)
