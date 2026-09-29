"""SupportNova — SQLAlchemy ORM models.

Normalized relational schema covering users/roles, knowledge base
(documents, versions, chunks, policies), the rule matrix, complaints and
their lifecycle, AI analyses, validation results/checks, escalations,
manual reviews, audit logs, prompt versions and dataset ground-truth cases.
"""
from __future__ import annotations

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .utils import utcnow

# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------

COMPLAINT_STATUSES = [
    "NEW", "ANALYZING", "ANALYZED", "VALIDATION_FAILED",
    "MANUAL_REVIEW", "ASSIGNED", "IN_PROGRESS", "PENDING", "WAITING_CUSTOMER",
    "ESCALATED", "RESOLVED", "REJECTED", "CLOSED",
]

VALIDATION_STATUSES = [
    "VERIFIED", "VERIFIED_WITH_WARNING", "MISMATCH",
    "MANUAL_REVIEW_REQUIRED", "FAILED",
]

CHECK_STATUSES = ["OK", "WARNING", "FAIL"]

# Trust Gate decisions — the independent verdict on an AI output.
TRUST_DECISIONS = ["VERIFIED", "REVIEW_REQUIRED", "BLOCKED"]

# Security event types recorded in the security timeline.
SECURITY_EVENT_TYPES = [
    "prompt_injection_detected",
    "document_quarantined",
    "document_flagged",
    "trust_blocked",
    "simulation_run",
    "security_suite_run",
    "firewall_input_blocked",
    "firewall_input_flagged",
    "firewall_output_blocked",
    "investigation_completed",
    "auto_resolved",
    "redteam2_run",
]

ROLES = ["admin", "agent", "reviewer", "manager", "customer"]


# ---------------------------------------------------------------------------
# Users / roles
# ---------------------------------------------------------------------------

class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="")

    users: Mapped[list["User"]] = relationship(back_populates="role")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), default="")
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    role_id: Mapped[int] = mapped_column(ForeignKey("roles.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)

    role: Mapped[Role] = relationship(back_populates="users")


# ---------------------------------------------------------------------------
# Organisation meta
# ---------------------------------------------------------------------------

class Department(Base):
    __tablename__ = "departments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="")
    is_escalation_target: Mapped[bool] = mapped_column(Boolean, default=False)


class ComplaintCategory(Base):
    __tablename__ = "complaint_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="")
    default_department_id: Mapped[int | None] = mapped_column(ForeignKey("departments.id"), nullable=True)
    sla_hours: Mapped[int] = mapped_column(Integer, default=72)
    keywords: Mapped[dict] = mapped_column(JSON, default=list)

    default_department: Mapped[Department | None] = relationship()


# ---------------------------------------------------------------------------
# Knowledge base
# ---------------------------------------------------------------------------

class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)  # DOC-001
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(64), default="policy")
    category: Mapped[str] = mapped_column(String(120), default="")
    source_reference: Mapped[str] = mapped_column(String(255), default="")
    # active | flagged | archived
    status: Mapped[str] = mapped_column(String(32), default="active")
    current_version: Mapped[str] = mapped_column(String(16), default="v1")
    injection_flag: Mapped[bool] = mapped_column(Boolean, default=False)
    injection_notes: Mapped[str] = mapped_column(Text, default="")
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[object] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    versions: Mapped[list["DocumentVersion"]] = relationship(
        back_populates="document", cascade="all, delete-orphan", order_by="DocumentVersion.id"
    )
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )


class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(16), nullable=False)
    effective_date: Mapped[object] = mapped_column(DateTime, default=utcnow)
    file_name: Mapped[str] = mapped_column(String(255), default="")
    stored_path: Mapped[str] = mapped_column(String(512), default="")
    extension: Mapped[str] = mapped_column(String(16), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    checksum: Mapped[str] = mapped_column(String(128), default="")
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)

    document: Mapped[Document] = relationship(back_populates="versions")
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="version", cascade="all, delete-orphan"
    )


class DocumentChunk(Base):
    """Traceable chunk: never loses its original source reference."""

    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"), nullable=False, index=True)
    version_id: Mapped[int] = mapped_column(ForeignKey("document_versions.id"), nullable=False)
    section_id: Mapped[str] = mapped_column(String(64), default="")
    section_title: Mapped[str] = mapped_column(String(255), default="")
    page: Mapped[int] = mapped_column(Integer, default=1)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0)
    source_reference: Mapped[str] = mapped_column(String(255), default="")
    text: Mapped[str] = mapped_column(Text, nullable=False)
    injection_suspected: Mapped[bool] = mapped_column(Boolean, default=False)
    trust_level: Mapped[str] = mapped_column(String(32), default="approved")  # approved | untrusted

    document: Mapped[Document] = relationship(back_populates="chunks")
    version: Mapped[DocumentVersion] = relationship(back_populates="chunks")


class Policy(Base):
    __tablename__ = "policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    policy_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)  # DEL-POL-04
    title: Mapped[str] = mapped_column(String(255), default="")
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    version: Mapped[str] = mapped_column(String(16), default="v1")
    section: Mapped[str] = mapped_column(String(64), default="")
    summary: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)

    document: Mapped[Document | None] = relationship()


# ---------------------------------------------------------------------------
# Rule matrix (independent ground truth)
# ---------------------------------------------------------------------------

class ComplaintRule(Base):
    __tablename__ = "complaint_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)  # DEL-001
    category: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    subcategory: Mapped[str] = mapped_column(String(120), default="")
    conditions: Mapped[dict] = mapped_column(JSON, default=dict)
    keywords: Mapped[dict] = mapped_column(JSON, default=list)
    department: Mapped[str] = mapped_column(String(120), default="")
    urgency: Mapped[str] = mapped_column(String(32), default="Medium")
    priority: Mapped[str] = mapped_column(String(8), default="P3")
    policy_id: Mapped[str] = mapped_column(String(64), default="")
    escalation: Mapped[bool] = mapped_column(Boolean, default=False)
    escalation_reason: Mapped[str] = mapped_column(String(255), default="")
    escalation_department: Mapped[str] = mapped_column(String(120), default="")
    required_actions: Mapped[list] = mapped_column(JSON, default=list)
    prohibited_actions: Mapped[list] = mapped_column(JSON, default=list)
    follow_up: Mapped[bool] = mapped_column(Boolean, default=True)
    response_template: Mapped[str] = mapped_column(Text, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[object] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


# ---------------------------------------------------------------------------
# Complaints
# ---------------------------------------------------------------------------

class Complaint(Base):
    __tablename__ = "complaints"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    customer_type: Mapped[str] = mapped_column(String(64), default="retail")
    product_or_service: Mapped[str] = mapped_column(String(255), default="")
    order_reference: Mapped[str] = mapped_column(String(120), default="")
    channel: Mapped[str] = mapped_column(String(64), default="web")
    complaint_date: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    requested_resolution: Mapped[str] = mapped_column(Text, default="")
    previous_complaints: Mapped[int] = mapped_column(Integer, default=0)
    supporting_document_name: Mapped[str] = mapped_column(String(255), default="")
    # v2 multilingual support: the original text is never modified; a gloss/translation
    # used only for rule matching lives next to it.
    original_language: Mapped[str] = mapped_column(String(16), default="")
    translated_text: Mapped[str] = mapped_column(Text, default="")

    customer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    assigned_agent_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    # Links a complaint created from Nova chat to the exact customer conversation.
    source_session_uuid: Mapped[str] = mapped_column(String(36), default="", index=True)

    customer: Mapped["User | None"] = relationship("User", foreign_keys=[customer_id])
    created_by_user: Mapped["User | None"] = relationship("User", foreign_keys=[created_by])
    assigned_agent: Mapped["User | None"] = relationship("User", foreign_keys=[assigned_agent_id])

    status: Mapped[str] = mapped_column(String(32), default="NEW", index=True)
    resolution_text: Mapped[str] = mapped_column(Text, default="")
    rejection_reason: Mapped[str] = mapped_column(Text, default="")
    # filled after analysis
    issue_category: Mapped[str] = mapped_column(String(120), default="")
    subcategory: Mapped[str] = mapped_column(String(120), default="")
    sentiment: Mapped[str] = mapped_column(String(32), default="")
    urgency: Mapped[str] = mapped_column(String(32), default="")
    priority: Mapped[str] = mapped_column(String(8), default="")
    department: Mapped[str] = mapped_column(String(120), default="")
    matched_rule_id: Mapped[str] = mapped_column(String(32), default="")

    # ground-truth values produced by the Python validation pipeline
    verified_category: Mapped[str] = mapped_column(String(120), default="")
    verified_department: Mapped[str] = mapped_column(String(120), default="")
    verified_urgency: Mapped[str] = mapped_column(String(32), default="")
    verified_priority: Mapped[str] = mapped_column(String(8), default="")
    verified_escalation: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    verification_status: Mapped[str] = mapped_column(String(32), default="")

    duplicate_of_id: Mapped[int | None] = mapped_column(ForeignKey("complaints.id"), nullable=True)
    duplicate_similarity: Mapped[float] = mapped_column(Float, default=0.0)

    injection_detected: Mapped[bool] = mapped_column(Boolean, default=False)
    incomplete: Mapped[bool] = mapped_column(Boolean, default=False)
    missing_fields: Mapped[list] = mapped_column(JSON, default=list)
    flags: Mapped[list] = mapped_column(JSON, default=list)

    sla_due_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    is_dataset_case: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[object] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    history: Mapped[list["ComplaintHistory"]] = relationship(
        back_populates="complaint", cascade="all, delete-orphan", order_by="ComplaintHistory.id"
    )
    attachments: Mapped[list["ComplaintAttachment"]] = relationship(
        back_populates="complaint", cascade="all, delete-orphan"
    )
    analyses: Mapped[list["AIAnalysis"]] = relationship(
        back_populates="complaint", cascade="all, delete-orphan", order_by="AIAnalysis.id"
    )
    validations: Mapped[list["ValidationResult"]] = relationship(
        back_populates="complaint", cascade="all, delete-orphan", order_by="ValidationResult.id"
    )


class ComplaintHistory(Base):
    __tablename__ = "complaint_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id"), nullable=False, index=True)
    from_status: Mapped[str] = mapped_column(String(32), default="")
    to_status: Mapped[str] = mapped_column(String(32), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)

    complaint: Mapped[Complaint] = relationship(back_populates="history")


class ComplaintAttachment(Base):
    __tablename__ = "complaint_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id"), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(255), default="")
    stored_path: Mapped[str] = mapped_column(String(512), default="")
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    uploaded_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)

    complaint: Mapped[Complaint] = relationship(back_populates="attachments")


# ---------------------------------------------------------------------------
# AI analyses & validation
# ---------------------------------------------------------------------------

class PromptVersion(Base):
    __tablename__ = "prompt_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)     # complaint_analysis
    version: Mapped[str] = mapped_column(String(16), nullable=False)   # v2
    file_path: Mapped[str] = mapped_column(String(255), default="")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    checksum: Mapped[str] = mapped_column(String(128), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)


class AIAnalysis(Base):
    __tablename__ = "ai_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id"), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(64), default="")
    model: Mapped[str] = mapped_column(String(120), default="")
    prompt_version_id: Mapped[int | None] = mapped_column(ForeignKey("prompt_versions.id"), nullable=True)
    raw_response: Mapped[str] = mapped_column(Text, default="")
    parsed: Mapped[dict] = mapped_column(JSON, default=dict)
    is_valid_schema: Mapped[bool] = mapped_column(Boolean, default=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    policy_context: Mapped[list] = mapped_column(JSON, default=list)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)

    complaint: Mapped[Complaint] = relationship(back_populates="analyses")
    prompt_version: Mapped[PromptVersion | None] = relationship()


class ValidationResult(Base):
    __tablename__ = "validation_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id"), nullable=False, index=True)
    analysis_id: Mapped[int | None] = mapped_column(ForeignKey("ai_analyses.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="FAILED", index=True)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)

    complaint: Mapped[Complaint] = relationship(back_populates="validations")
    checks: Mapped[list["ValidationCheck"]] = relationship(
        back_populates="result", cascade="all, delete-orphan", order_by="ValidationCheck.id"
    )


class ValidationCheck(Base):
    __tablename__ = "validation_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    validation_result_id: Mapped[int] = mapped_column(
        ForeignKey("validation_results.id"), nullable=False, index=True
    )
    check_name: Mapped[str] = mapped_column(String(64), default="")
    expected: Mapped[str] = mapped_column(Text, default="")
    actual: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="OK")   # OK | WARNING | FAIL
    message: Mapped[str] = mapped_column(Text, default="")

    result: Mapped[ValidationResult] = relationship(back_populates="checks")


# ---------------------------------------------------------------------------
# AI Trust Gate (independent verdict on an AI output)
# ---------------------------------------------------------------------------

class TrustAssessment(Base):
    """Trust Gate verdict for one validation run.

    The score and decision are computed by the deterministic trust engine from
    the actual validation checks — never randomly, never hardcoded.
    """

    __tablename__ = "trust_assessments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id"), nullable=False, index=True)
    validation_id: Mapped[int | None] = mapped_column(ForeignKey("validation_results.id"), nullable=True)
    decision: Mapped[str] = mapped_column(String(32), default="REVIEW_REQUIRED", index=True)
    score: Mapped[int] = mapped_column(Integer, default=0)
    headline: Mapped[str] = mapped_column(String(255), default="")
    explanation: Mapped[str] = mapped_column(Text, default="")
    categories: Mapped[list] = mapped_column(JSON, default=list)      # [{name, score, weight, checks, passed, warnings, failed}]
    failed_checks: Mapped[list] = mapped_column(JSON, default=list)    # [{check_name, expected, actual, status, severity, category, message}]
    blockers: Mapped[list] = mapped_column(JSON, default=list)         # critical reasons that blocked the AI output
    evidence: Mapped[list] = mapped_column(JSON, default=list)         # traceable policy references used for the verdict
    rule: Mapped[dict] = mapped_column(JSON, default=dict)             # matched rule matrix entry (ground truth)
    security: Mapped[dict] = mapped_column(JSON, default=dict)         # {injection_detected, schema_valid, duplicate, flags}
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow, index=True)

    complaint: Mapped[Complaint] = relationship()


class SecurityEvent(Base):
    """Security timeline entry backed by real detections (no static numbers)."""

    __tablename__ = "security_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_type: Mapped[str] = mapped_column(String(64), default="", index=True)
    severity: Mapped[str] = mapped_column(String(16), default="info")  # critical | high | medium | info
    complaint_id: Mapped[int | None] = mapped_column(ForeignKey("complaints.id"), nullable=True, index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(255), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow, index=True)

    complaint: Mapped[Complaint | None] = relationship()


# ---------------------------------------------------------------------------
# Escalations / manual review / audit
# ---------------------------------------------------------------------------

class Escalation(Base):
    __tablename__ = "escalations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id"), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    triggers: Mapped[list] = mapped_column(JSON, default=list)
    department: Mapped[str] = mapped_column(String(120), default="")
    priority: Mapped[str] = mapped_column(String(8), default="P2")
    status: Mapped[str] = mapped_column(String(32), default="OPEN")   # OPEN | ACKNOWLEDGED | RESOLVED
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)
    resolved_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)


class ManualReview(Base):
    __tablename__ = "manual_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id"), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(64), default="validation")
    status: Mapped[str] = mapped_column(String(32), default="OPEN", index=True)  # OPEN | RESOLVED
    decision: Mapped[str] = mapped_column(String(32), default="")   # approve | modify | reject | escalate
    decision_notes: Mapped[str] = mapped_column(Text, default="")
    modifications: Mapped[dict] = mapped_column(JSON, default=dict)
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)

    complaint: Mapped[Complaint] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    actor_email: Mapped[str] = mapped_column(String(255), default="")
    action: Mapped[str] = mapped_column(String(120), default="", index=True)
    entity_type: Mapped[str] = mapped_column(String(64), default="")
    entity_id: Mapped[str] = mapped_column(String(64), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow, index=True)


# ---------------------------------------------------------------------------
# Dataset ground truth (100+ unseen cases report)
# ---------------------------------------------------------------------------

class DatasetCase(Base):
    __tablename__ = "dataset_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    complaint_id: Mapped[int] = mapped_column(ForeignKey("complaints.id"), unique=True, nullable=False)
    case_code: Mapped[str] = mapped_column(String(32), default="")
    expected: Mapped[dict] = mapped_column(JSON, default=dict)
    flags: Mapped[list] = mapped_column(JSON, default=list)
    split: Mapped[str] = mapped_column(String(16), default="train")   # train | unseen

    complaint: Mapped[Complaint] = relationship()


# v2 additive tables (registered on the same metadata).
from . import models_nova  # noqa: E402,F401


# ---------------------------------------------------------------------------
# Telecom platform: SIMs, packages, orders, notifications, locations
# ---------------------------------------------------------------------------

SIM_STATUSES = [
    "ACTIVE", "INACTIVE", "BLOCKED", "LOST", "REPLACEMENT_REQUESTED", "DEACTIVATED", "PENDING",
]
ORDER_STATUSES = ["PENDING", "PROCESSING", "APPROVED", "COMPLETED", "CANCELLED", "FAILED"]
PAYMENT_STATUSES = ["PENDING", "PAID", "FAILED", "REFUNDED"]
PACKAGE_CATEGORIES = ["Internet", "Calls", "SMS", "Hybrid", "Daily", "Weekly", "Monthly"]


class TelecomPackage(Base):
    __tablename__ = "telecom_packages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(32), default="Hybrid", index=True)
    price: Mapped[float] = mapped_column(Float, default=0.0)
    validity_days: Mapped[int] = mapped_column(Integer, default=30)
    internet_data_mb: Mapped[int] = mapped_column(Integer, default=0)
    call_minutes: Mapped[int] = mapped_column(Integer, default=0)
    sms_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", index=True)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[object] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class SimCard(Base):
    __tablename__ = "sim_cards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sim_number: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    phone_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    sim_type: Mapped[str] = mapped_column(String(32), default="Prepaid")  # Prepaid / Postpaid
    network: Mapped[str] = mapped_column(String(32), default="4G")
    status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True)
    activation_date: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    registration_date: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    current_package_id: Mapped[int | None] = mapped_column(ForeignKey("telecom_packages.id"), nullable=True)
    replaced_by_id: Mapped[int | None] = mapped_column(ForeignKey("sim_cards.id"), nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[object] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class CustomerSubscription(Base):
    __tablename__ = "customer_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    sim_id: Mapped[int | None] = mapped_column(ForeignKey("sim_cards.id"), nullable=True, index=True)
    package_id: Mapped[int] = mapped_column(ForeignKey("telecom_packages.id"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), default="ACTIVE", index=True)
    start_date: Mapped[object] = mapped_column(DateTime, default=utcnow)
    end_date: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)


class TelecomOrder(Base):
    __tablename__ = "telecom_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    order_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    order_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)  # SIM | PACKAGE | REPLACEMENT
    product_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    product_label: Mapped[str] = mapped_column(String(255), default="")
    sim_id: Mapped[int | None] = mapped_column(ForeignKey("sim_cards.id"), nullable=True)
    amount: Mapped[float] = mapped_column(Float, default=0.0)
    payment_status: Mapped[str] = mapped_column(String(32), default="PENDING")
    order_status: Mapped[str] = mapped_column(String(32), default="PENDING", index=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)
    completed_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)


class LostSimRequest(Base):
    __tablename__ = "lost_sim_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    sim_id: Mapped[int] = mapped_column(ForeignKey("sim_cards.id"), nullable=False, index=True)
    verification_status: Mapped[str] = mapped_column(String(32), default="PENDING")
    sim_status_after: Mapped[str] = mapped_column(String(32), default="LOST")
    replacement_order_id: Mapped[int | None] = mapped_column(ForeignKey("telecom_orders.id"), nullable=True)
    assigned_agent_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[object] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class DeviceLocation(Base):
    """Demo / authorized location snapshot for a SIM. Always labelled simulated in API."""
    __tablename__ = "device_locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    sim_id: Mapped[int] = mapped_column(ForeignKey("sim_cards.id"), nullable=False, index=True)
    latitude: Mapped[float] = mapped_column(Float, default=0.0)
    longitude: Mapped[float] = mapped_column(Float, default=0.0)
    accuracy_m: Mapped[float] = mapped_column(Float, default=50.0)
    source: Mapped[str] = mapped_column(String(64), default="SIMULATED_DEMO_LOCATION")
    location_status: Mapped[str] = mapped_column(String(32), default="Available")
    recorded_at: Mapped[object] = mapped_column(DateTime, default=utcnow)


class AppNotification(Base):
    __tablename__ = "app_notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(64), default="general")
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    link: Mapped[str] = mapped_column(String(255), default="")
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)


class CustomerProfile(Base):
    """Extended customer profile (phone, CNIC masked, address). Linked 1:1 to users."""
    __tablename__ = "customer_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, nullable=False, index=True)
    phone_number: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    cnic: Mapped[str] = mapped_column(String(20), default="")  # stored; API masks
    address: Mapped[str] = mapped_column(Text, default="")
    date_of_birth: Mapped[str] = mapped_column(String(32), default="")
    verification_status: Mapped[str] = mapped_column(String(32), default="PENDING")  # PENDING | VERIFIED
    otp_code: Mapped[str] = mapped_column(String(12), default="")
    otp_expires_at: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    last_login: Mapped[object | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[object] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
