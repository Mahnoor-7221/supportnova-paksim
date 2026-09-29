"""Reports — including the 100+ unseen case GenAI vs Python comparison (spec §27)."""
from __future__ import annotations

import csv
import io
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..audit import log_action
from ..database import get_db
from ..models import AIAnalysis, Complaint, DatasetCase, User, ValidationResult
from ..schemas import UnseenRunRequest
from ..security import require_admin, require_staff
from ..services.analysis_service import analyze_complaint
from ..services.genai_client import AIProviderError
from ..python_validation import run_validation
from ..utils import utcnow

router = APIRouter(prefix="/api/reports", tags=["reports"])

MATCH_STATES = {"VERIFIED", "VERIFIED_WITH_WARNING"}
MISMATCH_STATES = {"MISMATCH"}
REVIEW_STATES = {"MANUAL_REVIEW_REQUIRED", "FAILED"}


def _latest(db: Session, model, complaint_id: int):
    return (
        db.query(model)
        .filter(model.complaint_id == complaint_id)
        .order_by(model.id.desc())
        .first()
    )


def _explanation(validation: ValidationResult, parsed: dict) -> str:
    summary = validation.summary or {}
    problems: list[str] = []
    for key in ("category", "subcategory", "department", "urgency", "priority", "escalation"):
        comparison = summary.get(key) or {}
        if comparison and comparison.get("match") is False:
            problems.append(f"{key}: expected '{comparison.get('expected')}' vs GenAI '{comparison.get('actual')}'")
    for claim in (summary.get("unsupported_claims") or [])[:2]:
        problems.append(str(claim))
    for action in (summary.get("missing_actions") or [])[:2]:
        problems.append(f"missing action: {action}")
    if not problems and validation.status != "VERIFIED":
        problems.append(f"status {validation.status}")
    if not problems:
        return "All independent checks passed"
    return " | ".join(problems)


def _row_for_case(db: Session, case: DatasetCase) -> Optional[dict]:
    complaint = db.get(Complaint, case.complaint_id)
    if complaint is None:
        return None
    analysis = _latest(db, AIAnalysis, complaint.id)
    validation = _latest(db, ValidationResult, complaint.id)
    if analysis is None or validation is None:
        return None

    parsed = analysis.parsed or {}
    summary = validation.summary or {}
    expected = case.expected or {}

    status = validation.status
    if status in MATCH_STATES:
        match = "MATCH"
    elif status in MISMATCH_STATES:
        match = "MISMATCH"
    elif status in REVIEW_STATES:
        match = "MANUAL_REVIEW"
    else:
        match = "UNKNOWN"

    policy_reference = parsed.get("policy_id") or "none"
    if parsed.get("policy_section"):
        policy_reference = f"{policy_reference} s{parsed['policy_section']}"

    return {
        "complaint_id": complaint.id,
        "case_code": case.case_code or complaint.code,
        "complaint_code": complaint.code,
        "expected_category": expected.get("category", ""),
        "genai_category": parsed.get("issue_category", ""),
        "python_category": (summary.get("category") or {}).get("expected", ""),
        "genai_department": parsed.get("department", ""),
        "python_department": (summary.get("department") or {}).get("expected", ""),
        "genai_urgency": parsed.get("urgency", ""),
        "python_urgency": (summary.get("urgency") or {}).get("expected", ""),
        "genai_escalation": "yes" if parsed.get("escalation_required") else "no",
        "python_escalation": "yes" if (summary.get("escalation") or {}).get("expected") == "required" else "no",
        "policy_reference": policy_reference,
        "match": match,
        "verification_status": status,
        "explanation": _explanation(validation, parsed),
        "flags": case.flags or [],
    }


def _collect_rows(db: Session, only_mismatches: bool = False) -> list[dict]:
    cases = db.query(DatasetCase).filter(DatasetCase.split == "unseen").order_by(DatasetCase.id).all()
    rows: list[dict] = []
    for case in cases:
        row = _row_for_case(db, case)
        if row is None:
            continue
        if only_mismatches and row["match"] == "MATCH":
            continue
        rows.append(row)
    return rows


@router.get("")
def reports_overview(db: Session = Depends(get_db), user: User = Depends(require_staff)):
    total_cases = db.query(DatasetCase).count()
    unseen_cases = db.query(DatasetCase).filter(DatasetCase.split == "unseen").count()
    compared = len(_collect_rows(db))
    return {
        "dataset": {
            "total_cases": total_cases,
            "unseen_cases": unseen_cases,
            "train_cases": total_cases - unseen_cases,
            "unseen_compared": compared,
            "unseen_remaining": max(0, unseen_cases - compared),
            "minimum_required": 100,
            "requirement_met": compared >= 100,
        },
        "generated_at": utcnow().isoformat(),
    }


@router.get("/unseen")
def unseen_comparison(
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
    only_mismatches: bool = False,
    offset: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
):
    all_rows = _collect_rows(db, only_mismatches=only_mismatches)
    return {
        "total": len(all_rows),
        "offset": offset,
        "limit": limit,
        "rows": all_rows[offset : offset + limit],
    }


@router.post("/unseen/run")
def run_unseen_comparison(
    payload: UnseenRunRequest,
    request: Request,
    db: Session = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """Run Pipeline 1 + Pipeline 2 on unseen dataset cases that lack results."""
    limit = max(1, min(payload.limit, 200))
    cases = (
        db.query(DatasetCase)
        .filter(DatasetCase.split == "unseen")
        .order_by(DatasetCase.id)
        .all()
    )

    processed = 0
    statuses: dict[str, int] = {}
    errors: list[str] = []
    for case in cases:
        if processed >= limit:
            break
        complaint = db.get(Complaint, case.complaint_id)
        if complaint is None:
            continue
        if _latest(db, ValidationResult, complaint.id) is not None:
            continue
        try:
            analysis, _context = analyze_complaint(db, complaint, admin.id)
            result = run_validation(db, complaint, analysis, admin.id)
        except AIProviderError as exc:
            errors.append(f"{complaint.code}: {exc}")
            break
        statuses[result.status] = statuses.get(result.status, 0) + 1
        processed += 1

    log_action(db, "reports.unseen_run", "system", "unseen-comparison",
               {"processed": processed, "statuses": statuses}, user=admin, request=request)
    return {
        "processed": processed,
        "statuses": statuses,
        "errors": errors,
        "compared_total": len(_collect_rows(db)),
    }


@router.get("/unseen/export.csv")
def export_unseen_csv(
    db: Session = Depends(get_db),
    user: User = Depends(require_staff),
    only_mismatches: bool = False,
):
    rows = _collect_rows(db, only_mismatches=only_mismatches)
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([
        "complaint_id", "case_code", "expected_category", "genai_category", "python_category",
        "genai_department", "python_department", "genai_urgency", "python_urgency",
        "genai_escalation", "python_escalation", "policy_reference", "match",
        "verification_status", "explanation",
    ])
    for row in rows:
        writer.writerow([
            row["complaint_id"], row["case_code"], row["expected_category"],
            row["genai_category"], row["python_category"], row["genai_department"],
            row["python_department"], row["genai_urgency"], row["python_urgency"],
            row["genai_escalation"], row["python_escalation"], row["policy_reference"],
            row["match"], row["verification_status"], row["explanation"],
        ])
    buffer.seek(0)
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=supportnova_unseen_comparison.csv"},
    )
