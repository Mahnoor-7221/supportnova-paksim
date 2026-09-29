"""AI Trust Gate — the independent verdict layer.

The trust engine never generates anything: it consumes the output of the
Python validation pipeline (Pipeline 2) and converts the individual checks
into a transparent trust score, a three-state decision (VERIFIED /
REVIEW_REQUIRED / BLOCKED) and an explainable rejection report.

TRUST SCORE (0-100) — weighted average of six categories, each computed from
the actual check results (OK = 100%, WARNING = 50%, FAIL = 0%):

    Policy Compliance      20%   policy grounding, citation validity,
                                 required/prohibited actions
    Security               20%   prompt-injection scan on untrusted text
    Business Rules         20%   category / subcategory / department /
                                 urgency / priority vs the rule matrix
    Evidence Support       15%   unsupported-claim (hallucination) check
    Consistency            10%   contradictions + follow-up expectations
    Escalation Correctness 15%   deterministic escalation decision + reason

DECISION — a gate, not an average:
    BLOCKED           any critical blocker fired (injection, unsupported
                      promise, prohibited content, fabricated policy,
                      missed safety/fraud escalation) — the AI output must
                      not reach the customer
    REVIEW_REQUIRED   validation status is not clean VERIFIED, or any check
                      failed / warned — a human decides
    VERIFIED          every check passed cleanly

Both the score and the decision are derived exclusively from real check
results — there is no randomness and no hardcoded dataset.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from ..models import AIAnalysis, Complaint, TrustAssessment, ValidationCheck, ValidationResult
from .security_events import log_security_event

# ---------------------------------------------------------------------------
# Transparent scoring definition
# ---------------------------------------------------------------------------

CATEGORY_DEFINITION: list[dict] = [
    {
        "name": "Policy Compliance",
        "weight": 0.20,
        "checks": ["policy", "policy_applicability", "policy_version",
                   "policy_section", "policy_reference",
                   "required_actions", "prohibited_actions"],
    },
    {
        "name": "Security",
        "weight": 0.20,
        "checks": ["prompt_injection"],
    },
    {
        "name": "Business Rules",
        "weight": 0.20,
        "checks": ["schema", "category", "subcategory", "department", "urgency", "priority"],
    },
    {
        "name": "Evidence Support",
        "weight": 0.15,
        "checks": ["hallucination"],
    },
    {
        "name": "Consistency",
        "weight": 0.10,
        "checks": ["contradiction", "follow_up", "follow_up_message"],
    },
    {
        "name": "Escalation Correctness",
        "weight": 0.15,
        "checks": ["escalation", "escalation_reason"],
    },
]

CHECK_STATUS_VALUE = {"OK": 1.0, "WARNING": 0.5, "FAIL": 0.0}

CHECK_SEVERITY: dict[str, str] = {
    "prompt_injection": "critical",
    "prohibited_actions": "critical",
    "hallucination": "critical",
    "policy": "critical",
    "policy_section": "critical",
    "policy_reference": "critical",
    "schema": "critical",
    "escalation": "high",
    "category": "high",
    "department": "high",
    "urgency": "high",
    "priority": "high",
    "required_actions": "high",
    "contradiction": "high",
    "policy_applicability": "medium",
    "policy_version": "medium",
    "subcategory": "medium",
    "follow_up": "medium",
    "follow_up_message": "medium",
    "escalation_reason": "medium",
}

# Check names whose FAIL blocks the AI output outright.
CRITICAL_BLOCKING_CHECKS = {
    "prompt_injection",
    "prohibited_actions",
    "hallucination",
    "policy",
    "policy_section",
    "policy_reference",
    "schema",
}

CATEGORY_OF_CHECK: dict[str, str] = {
    check: category["name"]
    for category in CATEGORY_DEFINITION
    for check in category["checks"]
}


def _check_entries(validation: ValidationResult) -> list[dict]:
    """Normalise checks from the persisted ValidationCheck rows."""
    entries: list[dict] = []
    for row in validation.checks:
        entries.append({
            "check_name": row.check_name,
            "expected": row.expected,
            "actual": row.actual,
            "status": row.status,
            "message": row.message,
        })
    return entries


def _check_entries_from_db(db: Session, validation_id: int) -> list[dict]:
    """Load check rows by validation id (sessions run with autoflush=False,
    so freshly added rows are not visible through the relationship yet)."""
    rows = (
        db.query(ValidationCheck)
        .filter(ValidationCheck.validation_result_id == validation_id)
        .order_by(ValidationCheck.id)
        .all()
    )
    return [
        {
            "check_name": row.check_name,
            "expected": row.expected,
            "actual": row.actual,
            "status": row.status,
            "message": row.message,
        }
        for row in rows
    ]


def compute_score(checks: list[dict]) -> tuple[int, list[dict]]:
    """Weighted transparent score. Returns (score, category_breakdown)."""
    by_name = {check["check_name"]: check for check in checks}
    categories: list[dict] = []
    weighted_sum = 0.0

    for definition in CATEGORY_DEFINITION:
        present = [by_name[name] for name in definition["checks"] if name in by_name]
        if present:
            value = sum(CHECK_STATUS_VALUE.get(check["status"], 0.0) for check in present) / len(present)
        else:
            value = 1.0  # nothing to evaluate → no demerit
        category_score = round(value * 100)
        weighted_sum += category_score * definition["weight"]
        categories.append({
            "name": definition["name"],
            "weight": definition["weight"],
            "score": category_score,
            "checks": definition["checks"],
            "passed": sum(1 for check in present if check["status"] == "OK"),
            "warnings": sum(1 for check in present if check["status"] == "WARNING"),
            "failed": sum(1 for check in present if check["status"] == "FAIL"),
        })

    return int(round(weighted_sum)), categories


def _build_blockers(checks: list[dict], summary: dict, complaint: Complaint) -> list[str]:
    """Critical verification failures that must stop the AI output."""
    blockers: list[str] = []
    by_name = {check["check_name"]: check for check in checks}

    injection = by_name.get("prompt_injection")
    if injection is not None and injection["status"] == "FAIL":
        blockers.append(
            "Prompt injection detected in the untrusted complaint text — "
            "the AI output cannot be trusted and must not be sent."
        )

    prohibited = by_name.get("prohibited_actions")
    if prohibited is not None and prohibited["status"] == "FAIL":
        detected = summary.get("prohibited_actions_detected") or [prohibited["message"]]
        blockers.append(
            "Generated response contains prohibited content: " + "; ".join(str(item) for item in detected[:4])
        )

    hallucination = by_name.get("hallucination")
    if hallucination is not None and hallucination["status"] == "FAIL":
        claims = summary.get("unsupported_claims") or [hallucination["message"]]
        blockers.append(
            "Unsupported claims detected in the AI response: " + "; ".join(str(c) for c in claims[:4])
        )

    policy = by_name.get("policy")
    if policy is not None and policy["status"] == "FAIL":
        blockers.append(
            f"Fabricated or unknown policy reference '{policy['actual']}' — not present in the approved knowledge base."
        )

    section = by_name.get("policy_section")
    if section is not None and section["status"] == "FAIL":
        blockers.append(section["message"])

    policy_ref = by_name.get("policy_reference")
    if policy_ref is not None and policy_ref["status"] == "FAIL":
        blockers.append(
            f"Invented policy reference '{policy_ref['actual']}' found in the generated text."
        )

    schema_check = by_name.get("schema")
    if schema_check is not None and schema_check["status"] == "FAIL":
        blockers.append(f"AI output failed schema validation: {schema_check['message'][:200]}")

    escalation = by_name.get("escalation")
    missed_escalation = (
        escalation is not None
        and escalation["status"] == "FAIL"
        and bool(getattr(complaint, "verified_escalation", False))
    )
    if missed_escalation:
        triggers = ", ".join(summary.get("escalation_triggers") or []) or "deterministic triggers"
        blockers.append(
            f"Critical escalation missed by the AI — the deterministic engine required escalation ({triggers})."
        )

    return blockers


def compute_assessment(
    complaint: Complaint,
    validation: ValidationResult,
    analysis: Optional[AIAnalysis] = None,
    checks: Optional[list[dict]] = None,
) -> dict:
    """Pure computation of the Trust Gate verdict (no persistence)."""
    if checks is None:
        checks = _check_entries(validation)
    summary = validation.summary or {}
    score, categories = compute_score(checks)
    blockers = _build_blockers(checks, summary, complaint)

    if blockers:
        decision = "BLOCKED"
    elif validation.status == "VERIFIED":
        decision = "VERIFIED"
    else:
        decision = "REVIEW_REQUIRED"

    failed_checks = [
        {
            "check_name": check["check_name"],
            "category": CATEGORY_OF_CHECK.get(check["check_name"], "Other"),
            "severity": CHECK_SEVERITY.get(check["check_name"], "medium"),
            "status": check["status"],
            "expected": check["expected"],
            "actual": check["actual"],
            "message": check["message"],
        }
        for check in checks
        if check["status"] in {"FAIL", "WARNING"}
    ]

    total = len(checks)
    ok_count = sum(1 for check in checks if check["status"] == "OK")
    warning_count = sum(1 for check in checks if check["status"] == "WARNING")
    fail_count = sum(1 for check in checks if check["status"] == "FAIL")

    matched_rule = None
    if complaint.matched_rule_id:
        matched_rule = {
            "rule_id": complaint.matched_rule_id,
            "category": complaint.verified_category,
            "department": complaint.verified_department,
            "urgency": complaint.verified_urgency,
            "priority": complaint.verified_priority,
            "escalation_required": bool(complaint.verified_escalation),
            "matched_rule_source": "rule matrix (deterministic)",
        }

    if decision == "BLOCKED":
        headline = "AI RESPONSE BLOCKED"
        explanation = blockers[0] if blockers else "Critical verification failure."
    elif decision == "REVIEW_REQUIRED":
        headline = "HUMAN REVIEW REQUIRED"
        explanation = (
            f"{fail_count} failed and {warning_count} warning check(s) — "
            "the AI recommendation should not be sent automatically."
        )
    else:
        headline = "VERIFIED SAFE"
        explanation = f"All {total} independent checks passed — the AI output is policy-grounded."

    security = {
        "injection_detected": bool(complaint.injection_detected),
        "schema_valid": bool(analysis.is_valid_schema) if analysis is not None else True,
        "duplicate": complaint.duplicate_of_id is not None,
        "flags": list(complaint.flags or []),
        "validation_status": validation.status,
    }

    return {
        "decision": decision,
        "score": score,
        "headline": headline,
        "explanation": explanation,
        "categories": categories,
        "failed_checks": failed_checks,
        "blockers": blockers,
        "evidence": list(analysis.policy_context or []) if analysis is not None else [],
        "rule": matched_rule or {},
        "security": security,
        "counts": {
            "total": total,
            "ok": ok_count,
            "warnings": warning_count,
            "failed": fail_count,
        },
    }


def assess_and_store(
    db: Session,
    complaint: Complaint,
    validation: ValidationResult,
    analysis: Optional[AIAnalysis] = None,
    user_id: Optional[int] = None,
    checks: Optional[list[dict]] = None,
) -> TrustAssessment:
    """Compute the Trust Gate verdict and persist it (no commit).

    Callers that hold the freshly computed check list in memory should pass it
    explicitly (the validation session runs with autoflush disabled, so the
    rows may not be queryable yet). Otherwise the persisted ValidationCheck
    rows are loaded from the database.
    """
    if checks is None:
        checks = _check_entries_from_db(db, validation.id)
    data = compute_assessment(complaint, validation, analysis, checks)

    row = TrustAssessment(
        complaint_id=complaint.id,
        validation_id=validation.id,
        decision=data["decision"],
        score=data["score"],
        headline=data["headline"][:255],
        explanation=data["explanation"],
        categories=data["categories"],
        failed_checks=data["failed_checks"],
        blockers=data["blockers"],
        evidence=data["evidence"],
        rule=data["rule"],
        security=data["security"],
    )
    db.add(row)

    if data["decision"] == "BLOCKED":
        log_security_event(
            db,
            "trust_blocked",
            f"Trust Gate blocked the AI response for {complaint.code}",
            severity="critical",
            complaint=complaint,
            detail={"score": data["score"], "blockers": data["blockers"][:3]},
            dedupe=False,
        )

    return row


def latest_assessment(db: Session, complaint_id: int) -> Optional[TrustAssessment]:
    return (
        db.query(TrustAssessment)
        .filter(TrustAssessment.complaint_id == complaint_id)
        .order_by(TrustAssessment.id.desc())
        .first()
    )


def serialize_assessment(
    assessment: TrustAssessment,
    complaint: Optional[Complaint] = None,
) -> dict:
    from ..serializers import complaint_brief

    data = {
        "id": assessment.id,
        "complaint_id": assessment.complaint_id,
        "validation_id": assessment.validation_id,
        "decision": assessment.decision,
        "score": assessment.score,
        "headline": assessment.headline,
        "explanation": assessment.explanation,
        "categories": assessment.categories or [],
        "failed_checks": assessment.failed_checks or [],
        "blockers": assessment.blockers or [],
        "evidence": assessment.evidence or [],
        "rule": assessment.rule or {},
        "security": assessment.security or {},
        "created_at": assessment.created_at.isoformat() if assessment.created_at else None,
    }
    if complaint is not None:
        data["complaint"] = complaint_brief(complaint)
    return data


def ensure_trust_assessments(db: Session) -> int:
    """Backfill: assess every complaint whose latest validation has no verdict."""
    from ..models import ValidationResult as _VR  # noqa: F401

    created = 0
    complaint_ids = [
        row[0]
        for row in db.query(ValidationResult.complaint_id).distinct().all()
    ]
    for complaint_id in complaint_ids:
        latest = (
            db.query(ValidationResult)
            .filter(ValidationResult.complaint_id == complaint_id)
            .order_by(ValidationResult.id.desc())
            .first()
        )
        if latest is None:
            continue
        exists = (
            db.query(TrustAssessment)
            .filter(TrustAssessment.validation_id == latest.id)
            .first()
        )
        if exists is not None:
            continue
        complaint = db.get(Complaint, complaint_id)
        if complaint is None:
            continue
        analysis = (
            db.query(AIAnalysis)
            .filter(AIAnalysis.id == latest.analysis_id)
            .first()
        ) if latest.analysis_id else None
        try:
            assess_and_store(db, complaint, latest, analysis)
            created += 1
        except Exception:  # pragma: no cover — backfill must never break startup
            db.rollback()
            continue
    if created:
        db.commit()
    return created
