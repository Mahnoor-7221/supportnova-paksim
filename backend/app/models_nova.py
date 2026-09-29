"""SupportNova v2 — additive ORM models for the investigation layer.

These tables are purely additive: no existing table is dropped or reshaped
(the two extra ``complaints`` columns are added by ``nova.migrate`` on
startup, so databases created by v1 keep working).

Every AI decision is reproducible from the rows stored here: the full agent
outputs, the pipeline version, the retrieved evidence, the Trust Gate verdict
and every later human interaction (challenge, feedback, decision).
"""
from __future__ import annotations

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .utils import utcnow

RESOLUTION_MODES = ["AUTO_RESOLVE", "HUMAN_APPROVAL", "MANDATORY_ESCALATION"]
FINAL_DECISIONS = ["AUTO RESOLVE", "HUMAN REVIEW", "ESCALATE", "BLOCK"]
FEEDBACK_VERDICTS = ["correct", "incorrect", "modified", "unsafe", "missing_evidence"]
CHALLENGE_TARGETS = ["evidence", "policy", "risk", "classification", "recommendation"]

NOVA_EVENT_TYPES = [
    "firewall_input_blocked",
    "firewall_input_flagged",
    "firewall_output_blocked",
    "investigation_completed",
    "auto_resolved",
    "redteam2_run",
]


class ComplaintLanguage(Base):
    """Original text is never destroyed: original + detection + translation + interpretation."""

    __tablename__ = "complaint_languages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id"), unique=True, nullable=False)
    original_text: Mapped[str] = mapped_column(Text, default="")
    detected_language: Mapped[str] = mapped_column(String(16), default="en")   # en | ur | roman_ur | unknown
    detection_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    translation: Mapped[str] = mapped_column(Text, default="")
    translation_method: Mapped[str] = mapped_column(String(64), default="none")
    interpretation: Mapped[dict] = mapped_column(JSON, default=dict)
    source_modality: Mapped[str] = mapped_column(String(16), default="text")   # text | voice
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)


class TransactionRecord(Base):
    """System-of-record order/payment data used to verify what customers claim."""

    __tablename__ = "transaction_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_reference: Mapped[str] = mapped_column(String(120), index=True, nullable=False)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    product: Mapped[str] = mapped_column(String(255), default="")
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    payment_status: Mapped[str] = mapped_column(String(32), default="paid")       # paid | failed | pending | refunded
    delivery_status: Mapped[str] = mapped_column(String(32), default="in_transit")  # in_transit | delivered | delayed | lost | not_shipped
    refund_status: Mapped[str] = mapped_column(String(32), default="none")         # none | requested | refunded
    placed_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    source: Mapped[str] = mapped_column(String(64), default="system")              # system | synthetic-demo-seed | demo-fixture
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)


class EvidenceItem(Base):
    """Uploaded / transcribed evidence. Always untrusted input, never an instruction."""

    __tablename__ = "evidence_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id"), nullable=False, index=True)
    modality: Mapped[str] = mapped_column(String(24), default="text")   # text | voice | image | screenshot | pdf | docx | markdown
    file_name: Mapped[str] = mapped_column(String(255), default="")
    stored_path: Mapped[str] = mapped_column(String(512), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    extracted_text: Mapped[str] = mapped_column(Text, default="")
    extraction_method: Mapped[str] = mapped_column(String(64), default="none")
    extracted_facts: Mapped[dict] = mapped_column(JSON, default=dict)
    injection: Mapped[dict] = mapped_column(JSON, default=dict)
    pii_counts: Mapped[dict] = mapped_column(JSON, default=dict)
    quarantined: Mapped[bool] = mapped_column(Boolean, default=False)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)


class Investigation(Base):
    __tablename__ = "investigations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), default="running", index=True)   # running | completed | failed
    pipeline_version: Mapped[str] = mapped_column(String(32), default="")
    triggered_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    plan: Mapped[dict] = mapped_column(JSON, default=dict)          # {run: [...], skipped: [{agent, reason}]}
    timeline: Mapped[list] = mapped_column(JSON, default=list)      # investigation timeline steps
    risk_score: Mapped[int] = mapped_column(Integer, default=0)
    risk_level: Mapped[str] = mapped_column(String(16), default="", index=True)
    resolution_mode: Mapped[str] = mapped_column(String(32), default="", index=True)
    final_decision: Mapped[str] = mapped_column(String(32), default="")
    trust_decision: Mapped[str] = mapped_column(String(32), default="")
    trust_score: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)       # judge output, explanations, response, sla, finance ...
    graph: Mapped[dict] = mapped_column(JSON, default=dict)         # evidence graph {nodes, edges}
    snapshot: Mapped[dict] = mapped_column(JSON, default=dict)      # audit snapshot (inputs, versions, evidence)
    governance_status: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    # pending | awaiting_human | auto_resolved | human_decided
    human_decision: Mapped[str] = mapped_column(String(24), default="")
    human_notes: Mapped[str] = mapped_column(Text, default="")
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow, index=True)
    completed_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)

    agent_runs: Mapped[list["AgentRun"]] = relationship(
        back_populates="investigation", cascade="all, delete-orphan", order_by="AgentRun.id"
    )


class AgentRun(Base):
    __tablename__ = "agent_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    investigation_id: Mapped[int] = mapped_column(ForeignKey("investigations.id"), nullable=False, index=True)
    agent_name: Mapped[str] = mapped_column(String(64), default="")
    decision: Mapped[str] = mapped_column(String(120), default="")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    reasoning_summary: Mapped[str] = mapped_column(Text, default="")
    output: Mapped[dict] = mapped_column(JSON, default=dict)        # full structured AgentResult
    model_info: Mapped[dict] = mapped_column(JSON, default=dict)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)

    investigation: Mapped[Investigation] = relationship(back_populates="agent_runs")


class InvestigationEvent(Base):
    """Append-only event log: challenges, feedback, decisions, CAPA approvals, auto-resolution."""

    __tablename__ = "investigation_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    investigation_id: Mapped[int | None] = mapped_column(ForeignKey("investigations.id"), nullable=True, index=True)
    complaint_id: Mapped[int | None] = mapped_column(ForeignKey("complaints.id"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(48), default="", index=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_email: Mapped[str] = mapped_column(String(255), default="system")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow, index=True)


class AIFeedback(Base):
    __tablename__ = "ai_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    investigation_id: Mapped[int] = mapped_column(ForeignKey("investigations.id"), nullable=False, index=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id"), nullable=False, index=True)
    verdict: Mapped[str] = mapped_column(String(24), default="correct", index=True)
    target: Mapped[str] = mapped_column(String(32), default="overall")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)


class CapaRecord(Base):
    """Corrective & Preventive Action. Stays PROPOSED until a human approves it."""

    __tablename__ = "capa_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(24), unique=True, nullable=False)
    complaint_id: Mapped[int | None] = mapped_column(ForeignKey("complaints.id"), nullable=True, index=True)
    investigation_id: Mapped[int | None] = mapped_column(ForeignKey("investigations.id"), nullable=True)
    root_cause: Mapped[str] = mapped_column(Text, default="")
    corrective_action: Mapped[str] = mapped_column(Text, default="")
    preventive_action: Mapped[str] = mapped_column(Text, default="")
    owner_department: Mapped[str] = mapped_column(String(120), default="")
    priority: Mapped[str] = mapped_column(String(8), default="P3")
    expected_outcome: Mapped[str] = mapped_column(Text, default="")
    suggested_deadline: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    required_evidence: Mapped[list] = mapped_column(JSON, default=list)
    supporting: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(16), default="PROPOSED", index=True)  # PROPOSED | APPROVED | REJECTED
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    decision_notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)


class CaseMemory(Base):
    """Controlled memory. Scope-separated; never shared across customers."""

    __tablename__ = "case_memory"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scope: Mapped[str] = mapped_column(String(24), index=True)   # session | customer_case | organization
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    complaint_id: Mapped[int | None] = mapped_column(ForeignKey("complaints.id"), nullable=True, index=True)
    session_uuid: Mapped[str] = mapped_column(String(36), default="", index=True)
    key: Mapped[str] = mapped_column(String(120), default="")
    value: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(120), default="")
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)


class AssistantSession(Base):
    __tablename__ = "assistant_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    uuid: Mapped[str] = mapped_column(String(36), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)

    messages: Mapped[list["AssistantMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="AssistantMessage.id"
    )


class AssistantMessage(Base):
    __tablename__ = "assistant_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("assistant_sessions.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), default="user")    # user | assistant
    text: Mapped[str] = mapped_column(Text, default="")              # PII-redacted transcript
    language: Mapped[str] = mapped_column(String(16), default="")
    modality: Mapped[str] = mapped_column(String(16), default="text")
    meta: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)

    session: Mapped[AssistantSession] = relationship(back_populates="messages")


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String(24), default="evaluation", index=True)   # evaluation | redteam2
    name: Mapped[str] = mapped_column(String(120), default="")
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict] = mapped_column(JSON, default=dict)
    results: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow, index=True)


class SatisfactionFeedback(Base):
    __tablename__ = "satisfaction_feedback"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id"), nullable=False, index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    rating: Mapped[int] = mapped_column(Integer, default=3)
    comment: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)
