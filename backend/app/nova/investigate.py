"""AI Digital Investigator — the top-level orchestrator.

    INPUT -> UNDERSTAND -> INVESTIGATE -> COLLECT EVIDENCE -> REASON -> VERIFY
    -> ASSESS RISK -> EXPLAIN -> RECOMMEND/ACT -> HUMAN GOVERNANCE -> LEARN

This module wires the v1 engines (rule matcher, escalation engine, retrieval,
Python validators, Trust Gate) together with the v2 agents, evidence,
similarity, RAG, governance and CAPA modules, and persists everything needed
for full auditability (``Investigation`` + ``AgentRun`` + timeline).

Human governance is never bypassed here: only ``AUTO_RESOLVE`` -- the
narrowest, most verified case -- changes complaint status without a human
click, and it always logs an ``auto_resolved`` event that a human can inspect
and reverse.
"""
from __future__ import annotations

import time
from typing import Optional

from sqlalchemy.orm import Session

from . import PIPELINE_VERSION
from ..models import AIAnalysis, Complaint, ComplaintHistory, ManualReview, User, ValidationResult
from ..models_nova import AgentRun, Investigation, InvestigationEvent
from ..python_validation import run_validation
from ..services.analysis_service import analyze_complaint
from ..services.escalation_engine import evaluate_escalation
from ..services.genai_client import AIProviderError
from ..services.rule_matcher import complaint_text, extract_signals, match_rule
from ..services.security_events import log_security_event
from ..services.trust_engine import assess_and_store, latest_assessment, serialize_assessment
from ..utils import utcnow
from . import agents as A
from . import capa as capa_mod
from . import evidence as evidence_mod
from . import finance, governance, language, rag, sla
from .firewall import input_firewall, log_input_event


def _timeline_step(label: str, detail: str, status: str = "done") -> dict:
    return {"label": label, "detail": detail, "status": status, "at": utcnow().isoformat()}


def _agent_run_row(investigation_id: int, result: "A.AgentResult") -> AgentRun:
    ts = utcnow().isoformat()
    return AgentRun(
        investigation_id=investigation_id, agent_name=result.agent_name, decision=result.decision,
        confidence=result.confidence, reasoning_summary=result.reasoning_summary,
        output=result.to_dict(ts), model_info=result.model_info, duration_ms=result.duration_ms,
    )


def _plan_agents(escalation_required: bool, evidence_needed: bool, has_evidence_items: bool) -> dict:
    """Which agents actually need to run for this complaint (spec: don't call every agent for every case)."""
    run = ["complaint_understanding_agent", "policy_agent", "evidence_agent", "risk_agent",
          "customer_history_agent", "similar_case_agent", "response_generation_agent",
          "explainability_agent", "final_judge_agent"]
    skipped = []
    if escalation_required or evidence_needed:
        run.append("fraud_abuse_agent")
    else:
        skipped.append({"agent": "fraud_abuse_agent", "reason": "no escalation trigger or evidence conflict risk"})
    if escalation_required:
        run.append("compliance_agent")
    else:
        skipped.append({"agent": "compliance_agent", "reason": "no legal/compliance signal detected"})
    run.append("root_cause_agent")
    return {"run": run, "skipped": skipped}


def run_investigation(db: Session, complaint: Complaint, user: Optional[User] = None,
                      tone: str = "Professional", force_reanalyze: bool = False) -> Investigation:
    started = time.perf_counter()
    investigation = Investigation(complaint_id=complaint.id, status="running",
                                  pipeline_version=PIPELINE_VERSION, triggered_by=user.id if user else None)
    db.add(investigation)
    db.flush()
    timeline: list[dict] = [_timeline_step("Complaint received", f"{complaint.code}: {complaint.title}")]

    try:
        # --- INPUT FIREWALL on the raw complaint text -----------------------------------------------
        raw_text = complaint_text(complaint)
        fw_in = input_firewall(raw_text, source="user", channel="complaint")
        log_input_event(db, fw_in, complaint=complaint, where="complaint_intake")
        timeline.append(_timeline_step("Input firewall", f"action={fw_in['action']}, risk={fw_in['risk']}"))

        # --- UNDERSTAND: language ---------------------------------------------------------------------
        lang_row = language.store_language(db, complaint, modality="text")
        lang_result = {"detected": {"language": lang_row.detected_language, "confidence": lang_row.detection_confidence,
                                    "label": lang_row.detection_confidence and lang_row.detected_language},
                      "translation": lang_row.translation, "method": lang_row.translation_method,
                      "interpretation": lang_row.interpretation}
        lang_result["detected"]["label"] = language.LANGUAGES.get(lang_row.detected_language, {}).get("label", "Unknown")
        timeline.append(_timeline_step("Language understood",
                                      f"{lang_result['detected']['label']}" +
                                      (f" -> gloss via {lang_row.translation_method}" if lang_row.translation else "")))
        db.commit()

        # --- Pipeline 1 (GenAI) + Pipeline 2 (Python) + Trust Gate, reusing v1 unless recent & not forced
        analysis = (db.query(AIAnalysis).filter(AIAnalysis.complaint_id == complaint.id)
                   .order_by(AIAnalysis.id.desc()).first())
        if analysis is None or force_reanalyze:
            try:
                analysis, _ctx = analyze_complaint(db, complaint, user.id if user else None)
            except AIProviderError as exc:
                investigation.status = "failed"
                investigation.error = f"GenAI provider error: {exc}"
                db.commit()
                return investigation
        timeline.append(_timeline_step("GenAI analysis", f"provider={analysis.provider}, schema_valid={analysis.is_valid_schema}"))

        validation = run_validation(db, complaint, analysis, user.id if user else None)
        db.commit()
        timeline.append(_timeline_step("Independent Python validation", f"status={validation.status}"))

        assessment = assess_and_store(db, complaint, validation, analysis, user.id if user else None)
        db.commit()
        timeline.append(_timeline_step("Trust Gate verification",
                                      f"{assessment.decision} (score {assessment.score}/100)"))

        # --- ground truth context for the agents --------------------------------------------------
        matched_rule, _score, _ranked = match_rule(db, complaint)
        signals = extract_signals(complaint, raw_text)
        query = raw_text + " " + (matched_rule.category if matched_rule else "")
        chunks = rag.hybrid_retrieve(db, query, top_k=6)
        escalation = evaluate_escalation(complaint, matched_rule, signals,
                                         injection_detected=complaint.injection_detected,
                                         policy_found=bool(chunks))
        timeline.append(_timeline_step("Policy matched",
                                      f"rule={matched_rule.rule_id if matched_rule else 'none'}, "
                                      f"{len(chunks)} approved excerpt(s) retrieved (hybrid retrieval)"))

        # --- COLLECT EVIDENCE ------------------------------------------------------------------------
        working_text = raw_text + ("\n" + lang_row.translation if lang_row.translation else "")
        evidence_agent, evidence_analysis = A.run_evidence_agent(db, complaint, working_text)
        timeline.append(_timeline_step(
            "Evidence checked",
            f"transaction record={'found' if evidence_analysis['transaction'] else 'not found'}, "
            f"{len(evidence_analysis['items'])} item(s), status={evidence_analysis['status']}"))
        if evidence_analysis["status"] == "CONFLICT":
            timeline.append(_timeline_step("EVIDENCE CONFLICT detected",
                                          "; ".join(c["detail"] for c in evidence_analysis["conflicts"][:2]),
                                          status="warning"))

        # --- REASON: run the planned agents ------------------------------------------------------------
        plan = _plan_agents(escalation["required"], evidence_analysis["status"] == "CONFLICT",
                            bool(evidence_analysis["items"]))
        agent_results: list[A.AgentResult] = [A.run_understanding_agent(db, complaint, lang_result),
                                              A.run_policy_agent(db, complaint, matched_rule, chunks),
                                              evidence_agent]
        agent_results.append(A.run_customer_history_agent(db, complaint))
        agent_results.append(A.run_similar_case_agent(db, complaint))
        fraud_result = A.run_fraud_agent(db, complaint, evidence_analysis) if "fraud_abuse_agent" in plan["run"] else \
            A.AgentResult("fraud_abuse_agent", "Not Run", 0.0, reasoning_summary="Skipped: no trigger for this complaint.")
        if "fraud_abuse_agent" in plan["run"]:
            agent_results.append(fraud_result)
        risk_result = A.run_risk_agent(complaint, escalation, evidence_analysis, fraud_result)
        agent_results.append(risk_result)
        if "compliance_agent" in plan["run"]:
            agent_results.append(A.run_compliance_agent(complaint, signals, chunks))
        root_cause_result = A.run_root_cause_agent(db, complaint, matched_rule)
        agent_results.append(root_cause_result)

        response_result, response_text, output_fw = A.run_response_agent(db, complaint, matched_rule, chunks, tone)
        agent_results.append(response_result)
        timeline.append(_timeline_step("Recommendation generated",
                                      f"tone={tone}, output_firewall={output_fw['action']}"))

        judge = A.run_final_judge(agent_results, assessment.decision, assessment.score,
                                  evidence_analysis, fraud_result, risk_result, escalation)
        agent_results.append(judge)
        explain = A.run_explainability_agent(agent_results, risk_result, judge.decision)
        agent_results.append(explain)
        timeline.append(_timeline_step("Trust Gate + agent verdicts combined", judge.reasoning_summary))

        # --- ASSESS RISK / GOVERNANCE ------------------------------------------------------------------
        txn = evidence_mod.transaction_for(db, complaint)
        fin = finance.financial_estimate(complaint, txn, escalation["required"])
        counterfactuals = finance.counterfactual_simulation(fin)
        mode = governance.decide_resolution_mode(
            trust_decision=assessment.decision, trust_score=assessment.score, risk_level=risk_result.decision,
            evidence_status=evidence_analysis["status"], escalation_triggers=escalation["triggers"],
            fraud_decision=fraud_result.decision, estimated_amount=fin["total_estimated_cost"])
        sla_info = sla.sla_status(complaint)
        timeline.append(_timeline_step("Resolution mode decided", f"{mode['mode']} ({'; '.join(mode['reasons'])})"))

        # CAPA proposal when there's a plausible recurring root cause worth acting on
        capa_record = None
        top_cause = (root_cause_result.evidence[0]["cause"] if root_cause_result.evidence else None)
        if top_cause and root_cause_result.confidence >= 0.4 and (escalation["required"] or judge.decision != "AUTO RESOLVE"):
            capa = capa_mod.generate_capa(db, complaint, root_cause_result.evidence[0], investigation.id)
            capa_record = capa_mod.capa_dict(capa)
            timeline.append(_timeline_step("CAPA proposed", f"{capa.code}: {capa.corrective_action[:80]}"))

        # --- RECOMMEND / ACT -----------------------------------------------------------------------------
        governance_status = "awaiting_human"
        if mode["mode"] == "AUTO_RESOLVE" and judge.decision == "AUTO RESOLVE":
            previous_status = complaint.status
            complaint.status = "RESOLVED"
            complaint.updated_at = utcnow()
            db.add(ComplaintHistory(complaint_id=complaint.id, from_status=previous_status, to_status="RESOLVED",
                                    note="Auto-resolved by SupportNova (low-risk, verified) -- reversible by staff.",
                                    actor_id=user.id if user else None))
            log_security_event(db, "auto_resolved", f"Complaint {complaint.code} auto-resolved by AI",
                               severity="info", complaint=complaint,
                               detail={"trust_score": assessment.score, "reasons": mode["reasons"]}, dedupe=False)
            governance_status = "auto_resolved"
            timeline.append(_timeline_step("Auto-resolved", "Trust >= threshold, Low risk, no escalation triggers.",
                                          status="auto"))
        else:
            exists = (db.query(ManualReview).filter(ManualReview.complaint_id == complaint.id,
                                                     ManualReview.reason == "AI investigation requires human governance",
                                                     ManualReview.status == "OPEN").first())
            if exists is None:
                db.add(ManualReview(complaint_id=complaint.id, reason="AI investigation requires human governance",
                                    source="investigation"))
            timeline.append(_timeline_step("Routed to human governance", mode["mode"]))
        timeline.append(_timeline_step("Investigation complete", f"final decision: {judge.decision}"))

        # --- persist ------------------------------------------------------------------------------------
        for result in agent_results:
            db.add(_agent_run_row(investigation.id, result))

        graph = rag.knowledge_graph(db, focus=matched_rule.category if matched_rule else None)

        investigation.status = "completed"
        investigation.timeline = timeline
        investigation.plan = plan
        investigation.risk_score = {"Low": 15, "Medium": 40, "High": 65, "Critical": 90}.get(risk_result.decision, 30)
        investigation.risk_level = risk_result.decision
        investigation.resolution_mode = mode["mode"]
        investigation.final_decision = judge.decision
        investigation.trust_decision = assessment.decision
        investigation.trust_score = assessment.score
        investigation.confidence = round(sum(a.confidence for a in agent_results) / max(len(agent_results), 1), 2)
        investigation.summary = {
            "judge": judge.to_dict(utcnow().isoformat()), "explainability": explain.to_dict(utcnow().isoformat()),
            "response_text": response_text, "response_tone": tone, "output_firewall": output_fw,
            "escalation": escalation, "evidence_analysis": evidence_analysis,
            "financial": fin, "counterfactuals": counterfactuals, "sla": sla_info,
            "capa": capa_record, "risk_flags": sorted({f for a in agent_results for f in a.risk_flags}),
            "governance_reasons": mode["reasons"],
        }
        investigation.graph = graph
        investigation.governance_status = governance_status
        investigation.snapshot = {
            "input_firewall": fw_in, "analysis_id": analysis.id, "validation_id": validation.id,
            "trust_assessment_id": assessment.id, "matched_rule_id": matched_rule.rule_id if matched_rule else None,
            "chunks_used": [{"document_code": c["document_code"], "section_id": c.get("section_id", ""),
                            "version": c.get("version", "")} for c in chunks],
            "language": {"detected": lang_row.detected_language, "method": lang_row.translation_method},
        }
        investigation.completed_at = utcnow()
        db.add(InvestigationEvent(investigation_id=investigation.id, complaint_id=complaint.id,
                                  event_type="investigation_completed", actor_id=user.id if user else None,
                                  actor_email=user.email if user else "system",
                                  payload={"final_decision": judge.decision, "trust": assessment.decision}))
        log_security_event(db, "investigation_completed", f"Investigation completed for {complaint.code}",
                           severity="info", complaint=complaint,
                           detail={"final_decision": judge.decision, "duration_ms": int((time.perf_counter() - started) * 1000)})
        db.commit()
        db.refresh(investigation)
        return investigation

    except Exception as exc:  # noqa: BLE001 - never leave an investigation half-written
        db.rollback()
        investigation = db.get(Investigation, investigation.id) or investigation
        investigation.status = "failed"
        investigation.error = str(exc)[:2000]
        investigation.timeline = timeline + [_timeline_step("Investigation failed", str(exc)[:300], status="error")]
        db.add(investigation)
        db.commit()
        raise


def investigation_dict(db: Session, investigation: Investigation, include_agents: bool = True) -> dict:
    out = {
        "id": investigation.id, "complaint_id": investigation.complaint_id, "status": investigation.status,
        "pipeline_version": investigation.pipeline_version, "timeline": investigation.timeline,
        "plan": investigation.plan, "risk_score": investigation.risk_score, "risk_level": investigation.risk_level,
        "resolution_mode": investigation.resolution_mode, "final_decision": investigation.final_decision,
        "trust_decision": investigation.trust_decision, "trust_score": investigation.trust_score,
        "confidence": investigation.confidence, "summary": investigation.summary, "graph": investigation.graph,
        "governance_status": investigation.governance_status, "human_decision": investigation.human_decision,
        "human_notes": investigation.human_notes, "snapshot": investigation.snapshot, "error": investigation.error,
        "created_at": investigation.created_at.isoformat() if investigation.created_at else None,
        "completed_at": investigation.completed_at.isoformat() if investigation.completed_at else None,
        "decided_at": investigation.decided_at.isoformat() if investigation.decided_at else None,
    }
    if include_agents:
        out["agents"] = [
            {"id": a.id, "agent_name": a.agent_name, "decision": a.decision, "confidence": a.confidence,
            "reasoning_summary": a.reasoning_summary, "output": a.output, "model_info": a.model_info,
            "created_at": a.created_at.isoformat() if a.created_at else None}
            for a in sorted(investigation.agent_runs, key=lambda r: r.id)
        ]
    return out


def latest_investigation(db: Session, complaint_id: int) -> Optional[Investigation]:
    return (db.query(Investigation).filter(Investigation.complaint_id == complaint_id)
           .order_by(Investigation.id.desc()).first())


def human_decide(db: Session, investigation: Investigation, decision: str, notes: str, user: User) -> Investigation:
    """Human governance action: approve / reject / escalate / modify the AI's recommendation."""
    if decision not in {"approve", "reject", "escalate", "modify"}:
        raise ValueError("invalid decision")
    investigation.human_decision = decision
    investigation.human_notes = notes
    investigation.decided_by = user.id
    investigation.decided_at = utcnow()
    investigation.governance_status = "human_decided"
    complaint = db.get(Complaint, investigation.complaint_id)
    if complaint is not None:
        previous = complaint.status
        new_status = {"approve": "RESOLVED", "reject": "IN_PROGRESS", "escalate": "ESCALATED", "modify": "IN_PROGRESS"}[decision]
        complaint.status = new_status
        db.add(ComplaintHistory(complaint_id=complaint.id, from_status=previous, to_status=new_status,
                                note=f"Human governance decision: {decision}. {notes}"[:500], actor_id=user.id))
    db.add(InvestigationEvent(investigation_id=investigation.id, complaint_id=investigation.complaint_id,
                              event_type="human_decision", actor_id=user.id, actor_email=user.email,
                              payload={"decision": decision, "notes": notes}))
    db.commit()
    db.refresh(investigation)
    return investigation


def challenge(db: Session, investigation: Investigation, target: str, question: str, user: User) -> dict:
    """'Challenge AI' -- ask the relevant agent to re-explain or reconsider using the same evidence."""
    from ..models_nova import CHALLENGE_TARGETS

    if target not in CHALLENGE_TARGETS:
        raise ValueError(f"target must be one of {CHALLENGE_TARGETS}")
    agent_map = {"evidence": "evidence_agent", "policy": "policy_agent", "risk": "risk_agent",
                "classification": "complaint_understanding_agent", "recommendation": "final_judge_agent"}
    run = next((a for a in investigation.agent_runs if a.agent_name == agent_map[target]), None)
    if run is None:
        response = "That aspect was not evaluated for this complaint."
    else:
        response = (f"Re-examining {target}: {run.reasoning_summary} "
                   f"(confidence {run.confidence}). Supporting evidence: "
                   f"{'; '.join(str(e) for e in (run.output.get('evidence') or [])[:3]) or 'none recorded'}.")
    db.add(InvestigationEvent(investigation_id=investigation.id, complaint_id=investigation.complaint_id,
                              event_type="challenge", actor_id=user.id, actor_email=user.email,
                              payload={"target": target, "question": question, "response": response}))
    db.commit()
    return {"target": target, "question": question, "response": response}
