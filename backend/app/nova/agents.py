"""Multi-agent orchestration (Phase 1).

Every agent returns a structured ``AgentResult``. The Orchestrator decides
which agents actually run for a given complaint (not every agent runs for
every case). The Final Judge combines every agent result into one decision.

Agents are deterministic wrappers around the existing v1 engines (rule
matcher, escalation engine, retrieval, Python validators, duplicate
detector) plus the new v2 modules (evidence, similarity, rag, firewall).
Nothing here re-implements what already exists — it orchestrates it and
narrates it.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable, Optional

from sqlalchemy.orm import Session

from ..config import settings
from ..models import AIAnalysis, Complaint, ComplaintRule, ManualReview
from ..python_validation.common import ValidationContext
from ..python_validation import (
    contradiction_checker,
    hallucination_checker,
    resolution_validator,
)
from ..services.duplicate_detector import find_duplicate
from ..services.escalation_engine import evaluate_escalation
from ..services.rule_matcher import complaint_text, expected_from_rule, extract_signals, match_rule
from . import evidence as evidence_mod
from . import language, rag, similarity
from .capa import root_cause_candidates


@dataclass
class AgentResult:
    agent_name: str
    decision: str
    confidence: float
    evidence: list[dict] = field(default_factory=list)
    reasoning_summary: str = ""
    policy_references: list[dict] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    recommended_action: str = ""
    model_info: dict = field(default_factory=dict)
    duration_ms: int = 0

    def to_dict(self, timestamp: str) -> dict:
        return {
            "agent_name": self.agent_name, "decision": self.decision, "confidence": round(self.confidence, 2),
            "evidence": self.evidence, "reasoning_summary": self.reasoning_summary,
            "policy_references": self.policy_references, "risk_flags": self.risk_flags,
            "recommended_action": self.recommended_action, "timestamp": timestamp, "model_info": self.model_info,
        }


def _model_info(deterministic: bool = True) -> dict:
    if deterministic:
        return {"type": "deterministic", "engine": "rule-matrix / validators", "provider": "none"}
    return {"type": "llm-assisted", "provider": settings.resolved_ai_provider,
            "model": settings.lovable_model if settings.resolved_ai_provider == "lovable" else (settings.gemini_model if settings.resolved_ai_provider == "gemini" else "offline-heuristic-baseline")}


# ---------------------------------------------------------------------------
# 1. Complaint Understanding Agent
# ---------------------------------------------------------------------------

def run_understanding_agent(db: Session, complaint: Complaint, lang: dict) -> AgentResult:
    text = complaint_text(complaint)
    signals = extract_signals(complaint, text)
    detected = lang["detected"]["language"]
    entities = []
    if complaint.order_reference:
        entities.append({"type": "order", "value": complaint.order_reference})
    if signals.get("amount") is not None:
        entities.append({"type": "amount", "value": signals["amount"]})
    if signals.get("delay_days") is not None:
        entities.append({"type": "delay_days", "value": signals["delay_days"]})
    topics = lang.get("interpretation", {}).get("topics", [])
    summary = f"Language: {lang['detected']['label']}" + (
        f" (translated via {lang['method']})" if detected not in ("en", "unknown") else "") + \
        f". Detected topics: {', '.join(topics) or 'none'}. Entities found: {len(entities)}."
    return AgentResult(
        "complaint_understanding_agent", decision=f"topics={topics or ['general']}", confidence=lang["detected"]["confidence"],
        evidence=[{"type": "signals", "value": signals}], reasoning_summary=summary,
        recommended_action="proceed_to_policy_and_evidence_agents", model_info=_model_info(),
        risk_flags=(["mentions_safety"] if signals.get("mentions_safety") else []) +
                   (["mentions_fraud"] if signals.get("mentions_fraud") else []),
    )


# ---------------------------------------------------------------------------
# 2. Policy Agent
# ---------------------------------------------------------------------------

def run_policy_agent(db: Session, complaint: Complaint, rule: Optional[ComplaintRule], chunks: list[dict]) -> AgentResult:
    refs = [{"document_code": c["document_code"], "section_id": c.get("section_id", ""),
             "version": c.get("version", ""), "excerpt": c["text"][:200]} for c in chunks[:3]]
    if not chunks:
        return AgentResult("policy_agent", decision="POLICY_NOT_FOUND", confidence=0.3,
                           reasoning_summary=rag.INSUFFICIENT, risk_flags=["policy_not_found"],
                           recommended_action="route_to_manual_review", model_info=_model_info())
    applicable = rule.policy_id if rule else ""
    return AgentResult(
        "policy_agent", decision=f"applicable_policy={applicable or 'unmatched'}", confidence=0.85 if rule else 0.5,
        evidence=[{"type": "citation", **r} for r in refs], policy_references=refs,
        reasoning_summary=f"{len(chunks)} approved excerpt(s) retrieved via hybrid retrieval; "
                          f"top match {refs[0]['document_code']} §{refs[0]['section_id']}.",
        recommended_action="ground_resolution_in_cited_policy", model_info=_model_info(),
    )


# ---------------------------------------------------------------------------
# 3. Evidence Agent
# ---------------------------------------------------------------------------

def run_evidence_agent(db: Session, complaint: Complaint, working_text: str) -> tuple[AgentResult, dict]:
    analysis = evidence_mod.analyze_evidence(db, complaint, working_text)
    risk = []
    if analysis["status"] == "CONFLICT":
        risk.append("evidence_conflict")
    if analysis["missing"]:
        risk.append("missing_evidence")
    if analysis["quarantined"]:
        risk.append("quarantined_evidence")
    conf = {"CONFLICT": 0.9, "SUPPORTED": 0.85, "INSUFFICIENT": 0.35, "NOT_REQUIRED": 0.7}[analysis["status"]]
    summary = {
        "CONFLICT": f"EVIDENCE CONFLICT: {len(analysis['conflicts'])} contradiction(s) between the customer's "
                    f"statement and other evidence.",
        "SUPPORTED": f"{len(analysis['supports'])} corroborating fact(s) found across evidence and records.",
        "INSUFFICIENT": rag.INSUFFICIENT + " No transaction record or usable evidence verifies the customer's claim.",
        "NOT_REQUIRED": "No claim in this complaint required cross-modal verification.",
    }[analysis["status"]]
    return AgentResult(
        "evidence_agent", decision=analysis["status"], confidence=conf,
        evidence=[{"type": "conflict", **c} for c in analysis["conflicts"]] +
                 [{"type": "support", **s} for s in analysis["supports"]],
        reasoning_summary=summary, risk_flags=risk,
        recommended_action="mandatory_human_review" if analysis["status"] == "CONFLICT" else "proceed",
        model_info=_model_info(),
    ), analysis


# ---------------------------------------------------------------------------
# 4. Fraud / Abuse Agent
# ---------------------------------------------------------------------------

def run_fraud_agent(db: Session, complaint: Complaint, evidence_analysis: dict) -> AgentResult:
    dup = find_duplicate(db, complaint)
    signals = extract_signals(complaint, complaint_text(complaint))
    flags = []
    score = 0.1
    if dup.get("duplicate_of_id") and (dup.get("similarity") or 0) >= 0.80:
        flags.append("repeated_similar_complaint"); score += 0.25
    if int(complaint.previous_complaints or 0) >= 3:
        flags.append("high_complaint_frequency"); score += 0.2
    if any(c["type"] == "claim_vs_record" for c in evidence_analysis.get("conflicts", [])):
        flags.append("claim_contradicts_system_record"); score += 0.3
    if signals.get("mentions_fraud"):
        flags.append("self_reported_fraud_language"); score += 0.1
    decision = "Potential Abuse Pattern" if flags else "Low Concern"
    return AgentResult(
        "fraud_abuse_agent", decision=decision, confidence=min(0.95, score) if flags else 0.2,
        evidence=[{"type": "duplicate", **dup}] if dup.get("duplicate_of_id") else [],
        reasoning_summary=(f"Indicators: {', '.join(flags)}." if flags else "No abuse indicators detected.") +
                          " This is a pattern flag for human investigation, not a fraud confirmation.",
        risk_flags=flags, recommended_action="human_investigation_required" if flags else "no_action",
        model_info=_model_info(),
    )


# ---------------------------------------------------------------------------
# 5. Risk Agent
# ---------------------------------------------------------------------------

def run_risk_agent(complaint: Complaint, escalation: dict, evidence_analysis: dict, fraud: AgentResult) -> AgentResult:
    score = 10
    reasons = []
    if escalation["required"]:
        score += 30; reasons.append(f"escalation triggers: {escalation['reason']}")
    if evidence_analysis["status"] == "CONFLICT":
        score += 25; reasons.append("unresolved evidence conflict")
    if fraud.decision == "Potential Abuse Pattern":
        score += 20; reasons.append("potential abuse pattern")
    if evidence_analysis["status"] == "INSUFFICIENT":
        score += 10; reasons.append("insufficient evidence")
    if complaint.injection_detected:
        score += 15; reasons.append("prompt injection detected")
    score = min(100, score)
    level = "Critical" if score >= 75 else "High" if score >= 50 else "Medium" if score >= 25 else "Low"
    return AgentResult(
        "risk_agent", decision=level, confidence=0.8,
        evidence=[{"type": "factor", "value": r} for r in reasons],
        reasoning_summary=f"Risk score {score}/100 ({level}). Factors: {', '.join(reasons) or 'none'}.",
        risk_flags=[level.lower()], recommended_action="escalate" if level in {"High", "Critical"} else "standard_handling",
        model_info=_model_info(),
    )


# ---------------------------------------------------------------------------
# 6. Root Cause Agent
# ---------------------------------------------------------------------------

def run_root_cause_agent(db: Session, complaint: Complaint, rule: Optional[ComplaintRule]) -> AgentResult:
    candidates = root_cause_candidates(db, complaint, rule)
    top = candidates[0] if candidates else None
    return AgentResult(
        "root_cause_agent", decision=(top["cause"] if top else "insufficient_data"),
        confidence=(top["confidence"] if top else 0.2),
        evidence=[{"type": "candidate", **c} for c in candidates],
        reasoning_summary=(f"Most likely root cause: {top['cause']} ({top['category']}, {top['method']})."
                          if top else "Not enough recurring signal to identify a root cause."),
        recommended_action="feed_into_capa_engine", model_info=_model_info(),
    )


# ---------------------------------------------------------------------------
# 7. Customer History Agent
# ---------------------------------------------------------------------------

def run_customer_history_agent(db: Session, complaint: Complaint) -> AgentResult:
    if not complaint.customer_id:
        return AgentResult("customer_history_agent", decision="no_customer_on_record", confidence=0.5,
                           reasoning_summary="Complaint has no linked customer account.", model_info=_model_info())
    history = (db.query(Complaint).filter(Complaint.customer_id == complaint.customer_id, Complaint.id != complaint.id)
              .order_by(Complaint.created_at.desc()).limit(10).all())
    escalated = sum(1 for h in history if h.status == "ESCALATED")
    flags = ["repeat_customer"] if len(history) >= 2 else []
    return AgentResult(
        "customer_history_agent", decision=f"{len(history)}_prior_complaints", confidence=0.9,
        evidence=[{"type": "prior_complaint", "code": h.code, "status": h.status, "category": h.issue_category}
                 for h in history[:5]],
        reasoning_summary=f"{len(history)} prior complaint(s) on this account, {escalated} previously escalated.",
        risk_flags=flags, recommended_action="review_history_before_resolution", model_info=_model_info(),
    )


# ---------------------------------------------------------------------------
# 8. Similar Case Agent
# ---------------------------------------------------------------------------

def run_similar_case_agent(db: Session, complaint: Complaint) -> AgentResult:
    cases = similarity.similar_cases(db, complaint, top_k=5)
    return AgentResult(
        "similar_case_agent", decision=f"{len(cases)}_similar_cases", confidence=0.75 if cases else 0.3,
        evidence=[{"type": "similar_case", **c} for c in cases],
        reasoning_summary=(f"Most similar: {cases[0]['case_id']} (similarity {cases[0]['similarity']}) — "
                          f"{cases[0]['why']['explanation']}." if cases else "No sufficiently similar historical case found."),
        recommended_action="consider_precedent_resolution" if cases else "no_precedent", model_info=_model_info(),
    )


# ---------------------------------------------------------------------------
# 9. Compliance Agent
# ---------------------------------------------------------------------------

def run_compliance_agent(complaint: Complaint, signals: dict, chunks: list[dict]) -> AgentResult:
    flags = []
    if signals.get("mentions_manager"):
        flags.append("legal_threat_or_escalation_language")
    if any("data protection" in c.get("document_title", "").lower() or "compliance" in c.get("document_title", "").lower()
          for c in chunks):
        flags.append("compliance_policy_referenced")
    decision = "compliance_review_required" if flags else "no_compliance_concern"
    return AgentResult(
        "compliance_agent", decision=decision, confidence=0.7 if flags else 0.4,
        reasoning_summary=(f"Flags: {', '.join(flags)}." if flags else "No compliance/legal risk indicators found."),
        risk_flags=flags, recommended_action="legal_review" if flags else "no_action", model_info=_model_info(),
    )


# ---------------------------------------------------------------------------
# 10. Response Generation Agent
# ---------------------------------------------------------------------------

def run_response_agent(db: Session, complaint: Complaint, rule: Optional[ComplaintRule], chunks: list[dict],
                       tone: str = "Professional") -> tuple[AgentResult, str, dict]:
    from .firewall import output_firewall, log_output_event
    from ..services.offline_analyzer import analyze as offline_analyze

    base = offline_analyze(complaint, chunks)
    steps = base.get("resolution_steps") or []
    lead = {"Empathetic": "We're really sorry for the trouble this has caused you.",
            "Concise": "Update on your complaint:",
            "Formal": "We acknowledge receipt of your complaint and are addressing it as follows.",
            }.get(tone, "Thank you for reaching out — we're sorry for the inconvenience.")
    body = "\n".join(f"- {s}" for s in steps[:4]) or "- We are reviewing your case against our approved policy."
    text = f"{lead}\n\n{body}\n\nWe will follow up with next steps."

    fw = output_firewall(db, text, complaint=complaint, chunks=chunks, rule=rule,
                         known_policy_id=base.get("policy_id"))
    log_output_event(db, fw, complaint=complaint, where="response_generation_agent")
    if fw["action"] == "block":
        text = ("We are still reviewing your case. A member of our team will confirm the outcome and next "
               "steps shortly, once we have fully verified the details against our records and policy.")
    return AgentResult(
        "response_generation_agent", decision=f"tone={tone}", confidence=0.9 if fw["allowed"] else 0.4,
        evidence=[{"type": "policy_used", "value": base.get("policy_id")}], policy_references=[
            {"document_code": c["document_code"], "section_id": c.get("section_id", "")} for c in chunks[:2]],
        reasoning_summary=("Response passed the output firewall." if fw["allowed"]
                          else f"Draft was rewritten: output firewall blocked ({', '.join(fw['categories'])})."),
        risk_flags=fw["categories"], recommended_action="send_after_trust_gate_verification", model_info=_model_info(),
    ), text, fw


# ---------------------------------------------------------------------------
# 11. Explainability Agent
# ---------------------------------------------------------------------------

def run_explainability_agent(agent_results: list[AgentResult], risk: AgentResult, judge_decision: str) -> AgentResult:
    reasons = [f"{a.agent_name}: {a.reasoning_summary}" for a in agent_results if a.risk_flags]
    return AgentResult(
        "explainability_agent", decision=judge_decision, confidence=1.0,
        evidence=[{"type": "contributing_agent", "agent": a.agent_name, "decision": a.decision,
                  "confidence": a.confidence} for a in agent_results],
        reasoning_summary=f"Final decision '{judge_decision}' driven by: " + "; ".join(reasons[:5]) if reasons
                          else f"Final decision '{judge_decision}' — no elevated risk factors from any agent.",
        recommended_action="present_why_panel", model_info=_model_info(),
    )


# ---------------------------------------------------------------------------
# 12. Final Judge Agent
# ---------------------------------------------------------------------------

def run_final_judge(agent_results: list[AgentResult], trust_decision: str, trust_score: int,
                    evidence_analysis: dict, fraud: AgentResult, risk: AgentResult, escalation: dict) -> AgentResult:
    """Combine every agent result. Disagreement between agents is surfaced, never hidden."""
    disagreements = []
    decisions = {a.agent_name: a.decision for a in agent_results}
    if trust_decision == "BLOCKED":
        final = "BLOCK"
    elif escalation["required"] or risk.decision in {"High", "Critical"} or evidence_analysis["status"] == "CONFLICT" \
            or fraud.decision == "Potential Abuse Pattern":
        final = "ESCALATE" if escalation["required"] or risk.decision == "Critical" else "HUMAN REVIEW"
    elif trust_decision == "REVIEW_REQUIRED" or evidence_analysis["status"] == "INSUFFICIENT":
        final = "HUMAN REVIEW"
    elif trust_decision == "VERIFIED" and risk.decision == "Low":
        final = "AUTO RESOLVE"
    else:
        final = "HUMAN REVIEW"

    if risk.decision in {"High", "Critical"} and trust_decision == "VERIFIED":
        disagreements.append("Risk Agent flags elevated risk while the Trust Gate independently verified the AI output.")
    if fraud.decision == "Potential Abuse Pattern" and final == "AUTO RESOLVE":
        disagreements.append("Fraud Agent flagged a pattern that should block auto-resolution — overridden to HUMAN REVIEW.")
        final = "HUMAN REVIEW"

    return AgentResult(
        "final_judge_agent", decision=final, confidence=0.95,
        evidence=[{"type": "agent_decision", "agent": k, "decision": v} for k, v in decisions.items()],
        reasoning_summary=f"Trust Gate={trust_decision} ({trust_score}/100), Risk={risk.decision}, "
                          f"Fraud={fraud.decision}, Evidence={evidence_analysis['status']}, "
                          f"Escalation required={escalation['required']}." +
                          (" Disagreements: " + "; ".join(disagreements) if disagreements else ""),
        risk_flags=risk.risk_flags, recommended_action=final, model_info=_model_info(),
    )
