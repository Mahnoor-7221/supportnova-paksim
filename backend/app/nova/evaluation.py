"""AI Evaluation Center (Phase 25).

Runs the real Pipeline 1 + Pipeline 2 + Trust Gate against a sample of dataset
cases with known ground truth and reports transparent metrics. No numbers are
hardcoded — everything is computed from the run.
"""
from __future__ import annotations

import random
from typing import Optional

from sqlalchemy.orm import Session

from ..models import AIAnalysis, Complaint, DatasetCase, ValidationResult
from ..models_nova import EvalRun
from ..python_validation import run_validation
from ..services.analysis_service import analyze_complaint
from ..services.genai_client import AIProviderError
from ..services import injection_guard
from ..services.trust_engine import assess_and_store
from ..utils import utcnow


def run_evaluation(db: Session, limit: int = 40, split: str = "unseen", seed: int = 7,
                   created_by: Optional[int] = None) -> EvalRun:
    cases = (db.query(DatasetCase).filter(DatasetCase.split == split).order_by(DatasetCase.id).all())
    rng = random.Random(seed)
    sample = rng.sample(cases, min(limit, len(cases))) if cases else []

    n = 0
    category_correct = policy_grounded = hallucination_free = citation_ok = escalation_correct = 0
    routing_correct = human_override = safety_ok = 0
    results = []
    injection_cases = 0
    injection_caught = 0

    for case in sample:
        complaint = db.get(Complaint, case.complaint_id)
        if complaint is None:
            continue
        try:
            analysis, _ctx = analyze_complaint(db, complaint, created_by)
        except AIProviderError:
            continue
        validation = run_validation(db, complaint, analysis, created_by)
        assess_and_store(db, complaint, validation, analysis, created_by)
        db.commit()
        db.refresh(complaint)

        n += 1
        expected = case.expected or {}
        summary = validation.summary or {}
        cat_ok = (summary.get("category") or {}).get("match") is True
        category_correct += int(cat_ok)
        policy_grounded += int((summary.get("checks") and any(
            c["check_name"] == "policy" and c["status"] == "OK" for c in summary["checks"])) or False)
        hallucination_free += int(not (summary.get("unsupported_claims")))
        citation_ok += int(bool((analysis.parsed or {}).get("policy_id")))
        esc_ok = (summary.get("escalation") or {}).get("match") is True
        escalation_correct += int(esc_ok)
        routing_correct += int((summary.get("department") or {}).get("match") is True)
        human_override += int(validation.status in {"MANUAL_REVIEW_REQUIRED", "FAILED", "MISMATCH"})
        scan = injection_guard.scan_text(f"{complaint.title}\n{complaint.description}")
        if scan["suspected"]:
            injection_cases += 1
            injection_caught += int(complaint.injection_detected)
        safety_ok += int(validation.status != "FAILED")

        results.append({
            "case_code": case.case_code, "complaint_code": complaint.code, "category_match": cat_ok,
            "escalation_match": esc_ok, "validation_status": validation.status,
            "trust_decision": complaint.verification_status,
        })

    def pct(x: int) -> float:
        return round(100.0 * x / n, 1) if n else 0.0

    metrics = {
        "cases_evaluated": n, "classification_accuracy": pct(category_correct),
        "policy_grounding_rate": pct(policy_grounded), "hallucination_free_rate": pct(hallucination_free),
        "citation_rate": pct(citation_ok), "escalation_accuracy": pct(escalation_correct),
        "routing_accuracy": pct(routing_correct), "human_override_rate": pct(human_override),
        "response_safety_rate": pct(safety_ok),
        "prompt_injection_resistance": round(100.0 * injection_caught / injection_cases, 1) if injection_cases else None,
        "injection_cases_seen": injection_cases,
    }
    run = EvalRun(kind="evaluation", name=f"eval-{split}-{utcnow():%Y%m%d%H%M%S}",
                 config={"limit": limit, "split": split, "seed": seed}, metrics=metrics, results=results,
                 created_by=created_by)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def eval_dict(run: EvalRun) -> dict:
    return {"id": run.id, "kind": run.kind, "name": run.name, "config": run.config, "metrics": run.metrics,
            "results": run.results, "created_at": run.created_at.isoformat() if run.created_at else None}


def compare_runs(a: EvalRun, b: EvalRun) -> dict:
    diff = {}
    for key in set(a.metrics) | set(b.metrics):
        va, vb = a.metrics.get(key), b.metrics.get(key)
        if isinstance(va, (int, float)) and isinstance(vb, (int, float)):
            diff[key] = {"a": va, "b": vb, "delta": round(vb - va, 2)}
    return {"a": eval_dict(a), "b": eval_dict(b), "diff": diff}
