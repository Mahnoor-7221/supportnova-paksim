"""Pipeline 1 orchestration — GenAI complaint intelligence.

Complaint -> context -> retrieved approved knowledge -> GenAI -> structured
JSON -> persisted AI analysis. Ground-truth values are produced separately by
the rule matrix; nothing here approves the model's answer.
"""
from __future__ import annotations

import json
import time
from typing import Optional

from pydantic import ValidationError
from sqlalchemy.orm import Session

from ..config import settings
from ..models import (
    AIAnalysis,
    Complaint,
    ComplaintHistory,
    Escalation,
    ManualReview,
)
from ..schemas import AIAnalysisContent
from ..utils import utcnow
from . import genai_client, injection_guard, offline_analyzer, retrieval
from .escalation_engine import evaluate_escalation
from .prompt_manager import get_prompt_manager
from .rule_matcher import (
    complaint_text,
    detect_secondary_issues,
    extract_signals,
    match_rule,
)
from .security_events import log_security_event

REQUIRED_FIELDS_FOR_COMPLETENESS = ["order_reference", "product_or_service", "complaint_date"]


def _without_internal_fields(data: dict) -> dict:
    return {key: value for key, value in data.items() if not str(key).startswith("_")}


def build_rule_context(db: Session) -> str:
    """Routing targets for the prompt — generic lists only, no per-case outcome."""
    from ..models import ComplaintCategory, ComplaintRule, Department

    lines: list[str] = []
    rules = db.query(ComplaintRule).filter(ComplaintRule.is_active.is_(True)).all()
    by_category: dict[str, list[str]] = {}
    for rule in rules:
        by_category.setdefault(rule.category, []).append(rule.subcategory)
    for category, subcategories in sorted(by_category.items()):
        unique = [s for s in dict.fromkeys(subcategories) if s]
        lines.append(f"- {category}: {', '.join(unique)}")

    departments = [d.name for d in db.query(Department).all()] or sorted(
        {rule.department for rule in rules if rule.department}
    )
    categories = [c.name for c in db.query(ComplaintCategory).all()]

    return (
        "KNOWN CATEGORIES: " + (", ".join(categories) if categories else ", ".join(by_category)) + "\n"
        "CATEGORY -> SUBCATEGORIES:\n" + "\n".join(lines) + "\n"
        "ROUTING TARGETS (choose exactly one department from this list): " + ", ".join(departments)
    )


def build_complaint_block(complaint: Complaint) -> str:
    return (
        f"Complaint ID: {complaint.code}\n"
        f"Title: {complaint.title}\n"
        f"Customer type: {complaint.customer_type}\n"
        f"Product/service: {complaint.product_or_service or 'unknown'}\n"
        f"Order reference: {complaint.order_reference or 'not provided'}\n"
        f"Channel: {complaint.channel}\n"
        f"Previous complaints: {complaint.previous_complaints}\n"
        f"Requested resolution: {complaint.requested_resolution or 'not specified'}\n"
        f"Description: {complaint.description}"
    )


def analyze_complaint(
    db: Session,
    complaint: Complaint,
    user_id: Optional[int] = None,
) -> tuple[AIAnalysis, dict]:
    """Run Pipeline 1 for a complaint. Returns (analysis_row, context)."""
    from_status = complaint.status
    complaint.status = "ANALYZING"
    db.add(ComplaintHistory(complaint_id=complaint.id, from_status=from_status,
                            to_status="ANALYZING", note="GenAI analysis started", actor_id=user_id))
    db.commit()

    text = complaint_text(complaint)
    injection = injection_guard.scan_text(text)
    signals = extract_signals(complaint, text)
    matched_rule, rule_score, ranked = match_rule(db, complaint)

    query = text
    if matched_rule is not None:
        query += " " + matched_rule.category + " " + " ".join((matched_rule.keywords or [])[:8])
    chunks = retrieval.retrieve(db, query, top_k=6)
    policy_found = len(chunks) > 0

    secondary_issues = detect_secondary_issues(complaint, matched_rule, ranked)

    escalation = evaluate_escalation(
        complaint, matched_rule, signals,
        injection_detected=injection["suspected"], policy_found=policy_found,
    )

    prompt_manager = get_prompt_manager()
    rule_context = build_rule_context(db)
    policy_context = retrieval.format_policy_context(chunks)
    complaint_block = build_complaint_block(complaint)

    provider = settings.resolved_ai_provider
    retry_count = 0
    latency_ms = 0
    raw_response = ""
    parsed: Optional[dict] = None
    schema_valid = False
    schema_error = ""

    if provider != "offline":
        prompt, _entry = prompt_manager.render("complaint_analysis", {
            "company_name": settings.app_name,
            "complaint": complaint_block,
            "rule_context": rule_context,
            "policy_context": policy_context,
        })
        attempts = 1 + max(0, settings.ai_max_retries)
        for attempt in range(attempts):
            data, raw_text, latency = genai_client.call_ai(prompt)
            raw_response = raw_text
            latency_ms += latency
            retry_count = attempt
            if data is None:
                schema_error = "Model did not return parseable JSON"
            else:
                try:
                    candidate = _without_internal_fields(data)
                    AIAnalysisContent.model_validate(candidate)
                    parsed = candidate
                    schema_valid = True
                    break
                except ValidationError as exc:
                    schema_error = str(exc)[:800]
            repair_prompt, _ = prompt_manager.render("validation_repair", {
                "error": schema_error,
                "previous": (raw_response or "")[:4000],
            })
            prompt = repair_prompt
    else:
        raw_data = offline_analyzer.analyze(complaint, chunks)
        raw_response = json.dumps(raw_data)
        parsed = _without_internal_fields(raw_data)
        try:
            AIAnalysisContent.model_validate(parsed)
            schema_valid = True
        except ValidationError as exc:
            schema_error = str(exc)[:800]

    # strip internal keys before persistence
    persisted = {k: v for k, v in (parsed or {}).items() if not str(k).startswith("_")}

    prompt_row = prompt_manager.active_version_row(db, "complaint_analysis")
    analysis = AIAnalysis(
        complaint_id=complaint.id,
        provider=(provider if provider != "offline" else "offline-heuristic-baseline"),
        model=(settings.lovable_model if provider == "lovable" else (settings.gemini_model if provider == "gemini" else "keyword-baseline")),
        prompt_version_id=prompt_row.id if prompt_row else None,
        raw_response=raw_response,
        parsed=persisted,
        is_valid_schema=schema_valid,
        retry_count=retry_count,
        latency_ms=latency_ms,
        policy_context=retrieval.collect_policy_references(chunks),
        created_by=user_id,
    )
    db.add(analysis)
    db.flush()

    # --- persist onto the complaint -------------------------------------
    if parsed:
        complaint.issue_category = str(parsed.get("issue_category") or "")
        complaint.subcategory = str(parsed.get("subcategory") or "")
        complaint.sentiment = str(parsed.get("sentiment") or "")
        complaint.urgency = str(parsed.get("urgency") or "")
        complaint.priority = str(parsed.get("priority") or "")
        complaint.department = str(parsed.get("department") or "")

    complaint.matched_rule_id = matched_rule.rule_id if matched_rule else ""
    complaint.injection_detected = injection["suspected"]

    flags: list[str] = list(complaint.flags or [])
    for flag in ["multi_issue", "injection_suspected", "policy_not_found", "high_risk", "duplicate_suspected"]:
        if flag in flags:
            flags.remove(flag)
    if secondary_issues:
        flags.append("multi_issue")
    if injection["suspected"]:
        flags.append("injection_suspected")
    if not policy_found:
        flags.append("policy_not_found")
    if escalation["required"]:
        flags.append("high_risk")
    if complaint.duplicate_of_id:
        flags.append("duplicate_suspected")
    complaint.flags = flags

    missing_fields = [f for f in REQUIRED_FIELDS_FOR_COMPLETENESS if not getattr(complaint, f, None)]
    complaint.missing_fields = missing_fields
    complaint.incomplete = bool(missing_fields)

    # --- escalation record (deterministic) --------------------------------
    if escalation["required"]:
        existing = (
            db.query(Escalation)
            .filter(Escalation.complaint_id == complaint.id, Escalation.status != "RESOLVED")
            .first()
        )
        if existing is None:
            db.add(Escalation(
                complaint_id=complaint.id,
                reason=escalation["reason"],
                triggers=escalation["triggers"],
                department=escalation["department"],
                priority=escalation["priority"],
                created_by=user_id,
            ))

    # --- manual review entries --------------------------------------------
    def open_review(reason: str, source: str) -> None:
        exists = (
            db.query(ManualReview)
            .filter(ManualReview.complaint_id == complaint.id,
                    ManualReview.reason == reason,
                    ManualReview.status == "OPEN")
            .first()
        )
        if exists is None:
            db.add(ManualReview(complaint_id=complaint.id, reason=reason, source=source))

    if injection["suspected"]:
        open_review(f"Prompt injection suspected in complaint text ({', '.join(injection['matches'])})", "injection")
    if not policy_found and matched_rule is not None and matched_rule.policy_id:
        open_review("Policy not found for this complaint - manual review required", "policy")
    if not schema_valid:
        open_review(f"AI output failed schema validation: {schema_error[:300]}", "schema")
    if complaint.duplicate_of_id and (complaint.duplicate_similarity or 0) >= 0.80:
        open_review(
            f"Possible duplicate of complaint #{complaint.duplicate_of_id} "
            f"(similarity {complaint.duplicate_similarity:.2f})",
            "duplicate",
        )

    if injection["suspected"]:
        log_security_event(
            db,
            "prompt_injection_detected",
            f"Prompt injection suspected in complaint {complaint.code}",
            severity="high" if injection.get("critical") else "medium",
            complaint=complaint,
            detail={"matches": list(injection.get("matches") or [])[:6]},
        )

    if not schema_valid:
        new_status = "MANUAL_REVIEW"
    elif escalation["required"]:
        new_status = "ESCALATED"
    else:
        new_status = "ANALYZED"
    complaint.status = new_status
    db.add(ComplaintHistory(complaint_id=complaint.id, from_status="ANALYZING",
                            to_status=new_status,
                            note=f"Analysis complete (provider={analysis.provider}, rule={complaint.matched_rule_id or 'none'})",
                            actor_id=user_id))
    complaint.updated_at = utcnow()
    db.commit()
    db.refresh(analysis)

    context = {
        "matched_rule": matched_rule,
        "rule_score": rule_score,
        "signals": signals,
        "injection": injection,
        "escalation": escalation,
        "secondary_issues": secondary_issues,
        "policy_found": policy_found,
        "chunks": chunks,
        "schema_valid": schema_valid,
    }
    return analysis, context


def regenerate_response(
    db: Session,
    complaint: Complaint,
    analysis: AIAnalysis,
    user_id: Optional[int] = None,
) -> str:
    """Regenerate the customer response with the dedicated prompt."""
    from .escalation_engine import evaluate_escalation
    from .rule_matcher import extract_signals, match_rule

    parsed = analysis.parsed or {}
    matched_rule, _, _ = match_rule(db, complaint)
    signals = extract_signals(complaint)
    escalation = evaluate_escalation(complaint, matched_rule, signals,
                                     injection_detected=complaint.injection_detected)

    provider = settings.resolved_ai_provider
    if provider != "offline":
        prompt_manager = get_prompt_manager()
        prompt, _ = prompt_manager.render("response_generation", {
            "company_name": settings.app_name,
            "complaint_summary": f"{complaint.title}. {complaint.description[:400]}",
            "resolution_steps": "; ".join(parsed.get("resolution_steps") or []),
            "policy_reference": f"{parsed.get('policy_id') or 'none'} section {parsed.get('policy_section') or 'n/a'}",
            "escalation": "yes" if escalation["required"] else "no",
        })
        data, raw_text, _ = genai_client.call_ai(prompt, json_mode=False)
        if raw_text and raw_text.strip():
            text = raw_text.strip()
            parsed_text = genai_client.extract_json_object(text)
            if isinstance(parsed_text, dict) and parsed_text.get("professional_response"):
                return str(parsed_text["professional_response"])
            if not text.startswith("{"):
                return text[:1500]
    return offline_analyzer.analyze(complaint, [])["professional_response"]
