from __future__ import annotations
from datetime import date
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field, model_validator

class LoginRequest(BaseModel): email: str; password: str
class RegisterRequest(BaseModel): email: str; password: str = Field(min_length=6); full_name: str
class UserCreate(BaseModel): email: str; password: str = Field(min_length=6); full_name: str; role: str = "customer"
class UserOut(BaseModel):
    id: int; email: str; full_name: str; is_active: bool; role: str
    @classmethod
    def from_user(cls, user): return cls(id=user.id,email=user.email,full_name=user.full_name,is_active=user.is_active,role=user.role.name if user.role else "")
class TokenResponse(BaseModel): access_token: str; token_type: str = "bearer"; user: UserOut
class ProfileUpdate(BaseModel): full_name: str
class PasswordChange(BaseModel): current_password: str; new_password: str = Field(min_length=6)
class PolicyCreate(BaseModel):
    policy_id: str; title: str = ""; document_id: Optional[int] = None; version: str = "v1"; section: str = ""; summary: str = ""; is_active: bool = True
class RuleCreate(BaseModel):
    rule_id: str; category: str; subcategory: str = ""; conditions: dict = {}; keywords: list = []; department: str = ""; urgency: str = "Medium"; priority: str = "P3"; policy_id: str = ""; escalation: bool = False; escalation_reason: str = ""; escalation_department: str = ""; required_actions: list = []; prohibited_actions: list = []; follow_up: bool = True; response_template: str = ""; is_active: bool = True
class RuleUpdate(RuleCreate):
    rule_id: Optional[str] = None; category: Optional[str] = None
class ComplaintCreate(BaseModel):
    title: str; description: str; customer_type: str = "retail"; product_or_service: str = ""; order_reference: str = ""; channel: str = "web"; complaint_date: Optional[Any] = None; requested_resolution: str = ""; previous_complaints: int = 0; supporting_document_name: str = ""; mobile_number: str = ""
class ComplaintUpdate(BaseModel):
    title: Optional[str]=None; description: Optional[str]=None; customer_type: Optional[str]=None; product_or_service: Optional[str]=None; order_reference: Optional[str]=None; channel: Optional[str]=None; complaint_date: Optional[Any]=None; requested_resolution: Optional[str]=None; previous_complaints: Optional[int]=None; supporting_document_name: Optional[str]=None; status: Optional[str]=None
    assigned_agent_id: Optional[int]=None; resolution_text: Optional[str]=None; rejection_reason: Optional[str]=None; department: Optional[str]=None; priority: Optional[str]=None; urgency: Optional[str]=None
class ReviewDecisionRequest(BaseModel): decision_notes: str = ""; modifications: dict = {}
class LabRunRequest(BaseModel): scenario_id: str
class UnseenRunRequest(BaseModel): limit: int = Field(default=100, ge=1, le=200)
class AIAnalysisContent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    complaint_id: str
    issue_category: str
    subcategory: str
    primary_issue: str
    secondary_issues: list[str]
    entities: list[str]
    sentiment: str
    emotion: str
    urgency: str
    priority: str
    department: str
    supporting_departments: list[str]
    policy_id: Optional[str]
    policy_section: Optional[str]
    policy_version: Optional[str]
    policy_applicability: str
    resolution_steps: list[str]
    refund_eligibility: str
    replacement_eligibility: str
    compensation_eligibility: str
    compensation_limit: Optional[float]
    required_actions: list[str]
    prohibited_actions: list[str]
    escalation_required: bool
    escalation_level: str
    escalation_reason: str
    escalation_notes: str
    response_type: str
    response_tone: str
    professional_response: str
    follow_up_required: bool
    follow_up_type: str
    follow_up_details: str
    agent_guidance: str
    clarification_questions: list[str]
    missing_information: list[str]
    unsupported_claims: list[str]
    source_references: list[str]

    additional_issues: list[str] = Field(default_factory=list)
    product_or_service: str = ""
    policy_status: str = ""
    follow_up_message: Optional[str] = None
    recommended_action: str = ""
    escalation: Optional[bool] = None
