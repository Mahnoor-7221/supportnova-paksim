"""Serialization helpers shared by the API routers."""
from __future__ import annotations

from typing import Optional

from .models import (
    AIAnalysis,
    AuditLog,
    Complaint,
    ComplaintHistory,
    Document,
    DocumentChunk,
    DocumentVersion,
    Escalation,
    ManualReview,
    Policy,
    User,
    ValidationResult,
)


def user_dict(user: User) -> dict:
    return {
        "id": user.id,
        "email": user.email,
        "full_name": user.full_name,
        "role": user.role.name if user.role else "",
        "is_active": user.is_active,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


def complaint_brief(complaint: Complaint) -> dict:
    return {
        "id": complaint.id,
        "code": complaint.code,
        "title": complaint.title,
        "status": complaint.status,
        "urgency": complaint.urgency,
        "priority": complaint.priority,
        "issue_category": complaint.issue_category,
        "subcategory": complaint.subcategory,
        "department": complaint.department,
        "sentiment": complaint.sentiment,
        "verified_category": complaint.verified_category,
        "verified_department": complaint.verified_department,
        "verified_urgency": complaint.verified_urgency,
        "verification_status": complaint.verification_status,
        "injection_detected": complaint.injection_detected,
        "incomplete": complaint.incomplete,
        "flags": complaint.flags or [],
        "duplicate_of_id": complaint.duplicate_of_id,
        "duplicate_similarity": complaint.duplicate_similarity,
        "is_dataset_case": complaint.is_dataset_case,
        "assigned_agent_id": getattr(complaint, "assigned_agent_id", None),
        "customer_id": getattr(complaint, "customer_id", None),
        "customer_name": getattr(getattr(complaint, "customer", None), "full_name", "") or "",
        "customer_email": getattr(getattr(complaint, "customer", None), "email", "") or "",
        "assigned_agent_name": getattr(getattr(complaint, "assigned_agent", None), "full_name", "") or "",
        "assigned_agent_email": getattr(getattr(complaint, "assigned_agent", None), "email", "") or "",
        "source_session_uuid": getattr(complaint, "source_session_uuid", "") or "",
        "resolution_text": getattr(complaint, "resolution_text", "") or "",
        "rejection_reason": getattr(complaint, "rejection_reason", "") or "",
        "sla_due_at": complaint.sla_due_at.isoformat() if complaint.sla_due_at else None,
        "created_at": complaint.created_at.isoformat() if complaint.created_at else None,
        "updated_at": complaint.updated_at.isoformat() if complaint.updated_at else None,
    }


def complaint_full(complaint: Complaint) -> dict:
    data = complaint_brief(complaint)
    data.update({
        "description": complaint.description,
        "customer_type": complaint.customer_type,
        "product_or_service": complaint.product_or_service,
        "order_reference": complaint.order_reference,
        "channel": complaint.channel,
        "complaint_date": complaint.complaint_date.isoformat() if complaint.complaint_date else None,
        "requested_resolution": complaint.requested_resolution,
        "previous_complaints": complaint.previous_complaints,
        "supporting_document_name": complaint.supporting_document_name,
        "customer_id": complaint.customer_id,
        "matched_rule_id": complaint.matched_rule_id,
        "missing_fields": complaint.missing_fields or [],
        "verified_priority": complaint.verified_priority,
        "verified_escalation": complaint.verified_escalation,
        "attachments": [
            {"id": a.id, "file_name": a.file_name, "size_bytes": a.size_bytes}
            for a in complaint.attachments
        ],
    })
    return data


def analysis_dict(analysis: AIAnalysis, prompt_version_name: Optional[str] = None) -> dict:
    return {
        "id": analysis.id,
        "complaint_id": analysis.complaint_id,
        "provider": analysis.provider,
        "model": analysis.model,
        "prompt_version": prompt_version_name,
        "is_valid_schema": analysis.is_valid_schema,
        "retry_count": analysis.retry_count,
        "latency_ms": analysis.latency_ms,
        "parsed": analysis.parsed or {},
        "policy_context": analysis.policy_context or [],
        "created_at": analysis.created_at.isoformat() if analysis.created_at else None,
    }


def validation_dict(result: ValidationResult, include_checks: bool = True) -> dict:
    data = {
        "id": result.id,
        "complaint_id": result.complaint_id,
        "analysis_id": result.analysis_id,
        "status": result.status,
        "summary": result.summary or {},
        "created_at": result.created_at.isoformat() if result.created_at else None,
    }
    if include_checks:
        data["checks"] = [
            {
                "id": check.id,
                "check_name": check.check_name,
                "expected": check.expected,
                "actual": check.actual,
                "status": check.status,
                "message": check.message,
            }
            for check in result.checks
        ]
    return data


def history_dict(entry: ComplaintHistory) -> dict:
    return {
        "id": entry.id,
        "from_status": entry.from_status,
        "to_status": entry.to_status,
        "note": entry.note,
        "actor_id": entry.actor_id,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }


def escalation_dict(escalation: Escalation) -> dict:
    return {
        "id": escalation.id,
        "complaint_id": escalation.complaint_id,
        "reason": escalation.reason,
        "triggers": escalation.triggers or [],
        "department": escalation.department,
        "priority": escalation.priority,
        "status": escalation.status,
        "created_at": escalation.created_at.isoformat() if escalation.created_at else None,
        "resolved_at": escalation.resolved_at.isoformat() if escalation.resolved_at else None,
    }


def review_dict(review: ManualReview, complaint: Optional[Complaint] = None) -> dict:
    data = {
        "id": review.id,
        "complaint_id": review.complaint_id,
        "reason": review.reason,
        "source": review.source,
        "status": review.status,
        "decision": review.decision,
        "decision_notes": review.decision_notes,
        "modifications": review.modifications or {},
        "decided_by": review.decided_by,
        "decided_at": review.decided_at.isoformat() if review.decided_at else None,
        "created_at": review.created_at.isoformat() if review.created_at else None,
    }
    if complaint is not None:
        data["complaint"] = complaint_brief(complaint)
    return data


def document_dict(document: Document) -> dict:
    return {
        "id": document.id,
        "code": document.code,
        "title": document.title,
        "doc_type": document.doc_type,
        "category": document.category,
        "source_reference": document.source_reference,
        "status": document.status,
        "current_version": document.current_version,
        "injection_flag": document.injection_flag,
        "injection_notes": document.injection_notes,
        "created_at": document.created_at.isoformat() if document.created_at else None,
        "updated_at": document.updated_at.isoformat() if document.updated_at else None,
    }


def version_dict(version: DocumentVersion) -> dict:
    return {
        "id": version.id,
        "version": version.version,
        "effective_date": version.effective_date.isoformat() if version.effective_date else None,
        "file_name": version.file_name,
        "extension": version.extension,
        "size_bytes": version.size_bytes,
        "checksum": version.checksum,
        "page_count": version.page_count,
        "is_current": version.is_current,
        "created_at": version.created_at.isoformat() if version.created_at else None,
    }


def chunk_dict(chunk: DocumentChunk) -> dict:
    return {
        "id": chunk.id,
        "section_id": chunk.section_id,
        "section_title": chunk.section_title,
        "page": chunk.page,
        "chunk_index": chunk.chunk_index,
        "source_reference": chunk.source_reference,
        "text": chunk.text,
        "injection_suspected": chunk.injection_suspected,
        "trust_level": chunk.trust_level,
    }


def policy_dict(policy: Policy) -> dict:
    return {
        "id": policy.id,
        "policy_id": policy.policy_id,
        "title": policy.title,
        "document_id": policy.document_id,
        "version": policy.version,
        "section": policy.section,
        "summary": policy.summary,
        "is_active": policy.is_active,
    }


def audit_dict(entry: AuditLog) -> dict:
    return {
        "id": entry.id,
        "actor_email": entry.actor_email,
        "action": entry.action,
        "entity_type": entry.entity_type,
        "entity_id": entry.entity_id,
        "detail": entry.detail or {},
        "ip_address": entry.ip_address,
        "created_at": entry.created_at.isoformat() if entry.created_at else None,
    }
