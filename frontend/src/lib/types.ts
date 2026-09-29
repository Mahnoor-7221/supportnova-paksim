// Shared API response types (mirror the FastAPI serializers).

export interface AuthUser {
  id: number;
  email: string;
  full_name: string;
  is_active: boolean;
  role: string;
}

export interface ProviderStatus {
  configured_provider: string;
  effective_provider: string;
  model: string;
  genai_live: boolean;
  note: string;
}

export interface NameValue {
  name: string;
  value: number;
}

export interface TrendPoint {
  date: string;
  count: number;
}

export interface ComplaintBrief {
  id: number;
  code: string;
  title: string;
  status: string;
  urgency: string | null;
  priority: string | null;
  issue_category: string | null;
  subcategory: string | null;
  department: string | null;
  sentiment: string | null;
  verified_category: string | null;
  verified_priority?: string | null;
  verified_department: string | null;
  verified_urgency: string | null;
  verification_status: string | null;
  injection_detected: boolean;
  incomplete: boolean;
  flags: string[];
  duplicate_of_id: number | null;
  duplicate_similarity: number;
  is_dataset_case: boolean;
  assigned_agent_id?: number | null;
  customer_id?: number | null;
  customer_name?: string;
  customer_email?: string;
  assigned_agent_name?: string;
  assigned_agent_email?: string;
  source_session_uuid?: string;
  sla_due_at: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface Attachment {
  id: number;
  file_name: string;
  size_bytes: number;
}

export interface ComplaintFull extends ComplaintBrief {
  description: string;
  customer_type: string;
  product_or_service: string;
  order_reference: string;
  channel: string;
  complaint_date: string | null;
  requested_resolution: string;
  previous_complaints: number;
  supporting_document_name: string;
  customer_id: number | null;
  matched_rule_id: string | null;
  missing_fields: string[];
  verified_priority: string | null;
  verified_escalation: boolean | null;
  attachments: Attachment[];
}

export interface AnalysisParsed {
  issue_category?: string;
  subcategory?: string;
  additional_issues?: string[];
  sentiment?: string;
  urgency?: string;
  priority?: string;
  department?: string;
  product_or_service?: string;
  entities?: string[];
  policy_id?: string | null;
  policy_section?: string | null;
  policy_version?: string | null;
  policy_status?: string;
  resolution_steps?: string[];
  escalation_required?: boolean;
  escalation_reason?: string | null;
  response_type?: string;
  professional_response?: string;
  follow_up_required?: boolean;
  follow_up_message?: string | null;
  agent_guidance?: string;
  clarification_questions?: string[];
  source_references?: string[];
  [key: string]: unknown;
}

export interface PolicyReference {
  document_code: string;
  document_title: string;
  version: string;
  section_id: string;
  page: number;
  source_reference: string;
  score: number;
}

export interface Analysis {
  id: number;
  complaint_id: number;
  provider: string;
  model: string;
  prompt_version: string | null;
  is_valid_schema: boolean;
  retry_count: number;
  latency_ms: number;
  parsed: AnalysisParsed;
  policy_context: PolicyReference[];
  created_at: string | null;
}

export interface Comparison {
  expected: string;
  actual: string;
  match: boolean;
}

export interface ValidationCheck {
  id: number;
  check_name: string;
  expected: string;
  actual: string;
  status: string; // OK | WARNING | FAIL
  message: string;
}

export interface ValidationSummary {
  status: string;
  category?: Comparison;
  subcategory?: Comparison;
  department?: Comparison;
  urgency?: Comparison;
  priority?: Comparison;
  escalation?: Comparison;
  follow_up?: Comparison;
  policy_valid?: boolean;
  escalation_valid?: boolean;
  schema_valid?: boolean;
  missing_actions?: string[];
  prohibited_actions_detected?: string[];
  unsupported_claims?: string[];
  contradictions?: string[];
  injection_detected?: boolean;
  manual_review_reasons?: string[];
  matched_rule_id?: string;
  escalation_triggers?: unknown[];
  checks?: ValidationCheck[];
  [key: string]: unknown;
}

export interface Validation {
  id: number;
  complaint_id: number;
  analysis_id: number;
  status: string;
  summary: ValidationSummary;
  created_at: string | null;
  checks?: ValidationCheck[];
}

export interface TrustCategory {
  name: string;
  weight: number;
  score: number;
  checks: string[];
  passed: number;
  warnings: number;
  failed: number;
}

export interface TrustFailedCheck {
  check_name: string;
  category: string;
  severity: string; // critical | high | medium | low
  status: string; // FAIL | WARNING
  expected: string;
  actual: string;
  message: string;
}

export interface TrustRuleInfo {
  rule_id?: string;
  category?: string | null;
  department?: string | null;
  urgency?: string | null;
  priority?: string | null;
  escalation_required?: boolean;
  matched_rule_source?: string;
}

export interface TrustSecurityInfo {
  injection_detected: boolean;
  schema_valid: boolean;
  duplicate: boolean;
  flags: string[];
  validation_status: string;
}

export interface TrustAssessment {
  id: number;
  complaint_id: number;
  validation_id: number;
  decision: string; // VERIFIED | REVIEW_REQUIRED | BLOCKED
  score: number;
  headline: string;
  explanation: string;
  categories: TrustCategory[];
  failed_checks: TrustFailedCheck[];
  blockers: string[];
  evidence: PolicyReference[];
  rule: TrustRuleInfo;
  security: TrustSecurityInfo;
  created_at: string | null;
  complaint?: ComplaintBrief;
}

export interface Rule {
  id: number;
  rule_id: string;
  category: string;
  subcategory: string;
  conditions?: Record<string, unknown>;
  keywords?: string[];
  department: string;
  urgency: string;
  priority: string;
  policy_id: string;
  escalation: boolean;
  escalation_reason?: string;
  escalation_department?: string;
  required_actions?: string[];
  prohibited_actions?: string[];
  follow_up?: boolean;
  is_active?: boolean;
  response_template?: string;
}

export interface Escalation {
  id: number;
  complaint_id: number;
  reason: string;
  triggers: unknown[];
  department: string;
  priority: string;
  status: string;
  created_at: string | null;
  resolved_at: string | null;
}

export interface HistoryEntry {
  id: number;
  from_status: string;
  to_status: string;
  note: string;
  actor_id: number | null;
  created_at: string | null;
}

export interface ManualReview {
  id: number;
  complaint_id: number;
  reason: string;
  source: string;
  status: string;
  decision: string | null;
  decision_notes: string | null;
  modifications: Record<string, unknown>;
  decided_by: number | null;
  decided_at: string | null;
  created_at: string | null;
  complaint?: ComplaintBrief;
}

export interface ManualReviewDetail {
  review: ManualReview;
  complaint: ComplaintFull | null;
  analysis: Analysis | null;
  validation: Validation | null;
}

export interface ComplaintFeedback {
  rating: number;
  comment: string;
  created_at: string | null;
}

export interface ComplaintDetail {
  complaint: ComplaintFull;
  rule: Rule | null;
  analysis: Analysis | null;
  validation: Validation | null;
  trust: TrustAssessment | null;
  history: HistoryEntry[];
  escalations: Escalation[];
  manual_reviews: ManualReview[];
  feedback?: ComplaintFeedback | null;
  duplicate_of: ComplaintBrief | null;
}

export interface DocumentRow {
  id: number;
  code: string;
  title: string;
  doc_type: string;
  category: string;
  source_reference: string;
  status: string;
  current_version: string;
  injection_flag: boolean;
  injection_notes: string;
  created_at: string | null;
  updated_at: string | null;
  chunk_count?: number;
  version_count?: number;
}

export interface DocumentChunkRow {
  id: number;
  section_id: string;
  section_title: string;
  page: number;
  chunk_index: number;
  source_reference: string;
  text: string;
  injection_suspected: boolean;
  trust_level: string;
}

export interface DocumentVersionRow {
  id: number;
  version: string;
  effective_date: string | null;
  file_name: string;
  extension: string;
  size_bytes: number;
  checksum: string;
  page_count: number;
  is_current: boolean;
  created_at: string | null;
}

export interface DocumentDetail {
  document: DocumentRow;
  versions: DocumentVersionRow[];
  chunks: DocumentChunkRow[];
  total_chunks: number;
}

export interface UploadScan {
  suspected: boolean;
  matches: string[];
  count: number;
  critical?: boolean;
}

export interface DocumentUploadResult {
  document: DocumentRow;
  version: string;
  sections: number;
  chunks: number;
  page_count: number;
  injection_scan: UploadScan;
  quarantined: boolean;
}

export interface DocumentVersionUploadResult {
  document: DocumentRow;
  version: string;
  sections: number;
  chunks: number;
  injection_scan: UploadScan;
}

export interface PolicyRow {
  id: number;
  policy_id: string;
  title: string;
  document_id: number | null;
  version: string;
  section: string;
  summary: string;
  is_active: boolean;
  document_code?: string | null;
  document_title?: string | null;
}

export interface DashboardTotals {
  total: number;
  new: number;
  analyzed: number;
  high_priority: number;
  escalated: number;
  manual_review: number;
  resolved: number;
  sla_risk: number;
  mismatches: number;
  validation_failed: number;
  manual_review_required: number;
  verified: number;
  verified_with_warning: number;
  injections: number;
  duplicates: number;
  repeat_complaints: number;
  incomplete: number;
  unverified: number;
  unassigned: number;
  in_progress: number;
  open: number;
}

export interface DashboardTrust {
  assessed: number;
  verified: number;
  review_required: number;
  blocked: number;
  average_score: number | null;
}

export interface DashboardRisk {
  levels: { critical: number; high: number; medium: number; low: number };
  ai_risks: {
    hallucination: number;
    policy_mismatch: number;
    injection: number;
    escalation_gap: number;
  };
  critical_open_escalations: number;
  sla_risk_open: number;
  open_security_events: number;
  critical_security_events: number;
}

export interface DashboardData {
  totals: DashboardTotals;
  trust: DashboardTrust;
  risk: DashboardRisk;
  charts: {
    category: NameValue[];
    priority: NameValue[];
    urgency: NameValue[];
    sentiment: NameValue[];
    department: NameValue[];
    verification: NameValue[];
    status: NameValue[];
    policy_usage: NameValue[];
    complaints_trend: TrendPoint[];
    escalation_trend: TrendPoint[];
  };
  recent_complaints: ComplaintBrief[];
  recent_escalations: Escalation[];
  department_workload?: Array<{name: string; total: number; open: number; assigned: number; unassigned: number; escalated: number; sla_risk: number}>;
  provider: ProviderStatus;
}

export interface MismatchBucket {
  category: string;
  total: number;
  mismatched: number;
  warning: number;
  manual_review: number;
  verified: number;
  rate: number;
}

export interface AnalyticsData {
  totals: DashboardTotals;
  charts: {
    category: NameValue[];
    priority: NameValue[];
    urgency: NameValue[];
    sentiment: NameValue[];
    department: NameValue[];
    verification: NameValue[];
    complaints_trend: TrendPoint[];
    escalation_trend: TrendPoint[];
  };
  mismatch_by_category: MismatchBucket[];
  sla_risk: ComplaintBrief[];
  manual_review_sources: NameValue[];
  manual_review_status: NameValue[];
  escalation_triggers: NameValue[];
  escalation_status: NameValue[];
  policy_usage: NameValue[];
  dataset: { total: number; unseen: number; train: number };
  provider: ProviderStatus;
}

export interface UnseenRow {
  complaint_id: number;
  case_code: string;
  complaint_code: string;
  expected_category: string;
  genai_category: string;
  python_category: string;
  genai_department: string;
  python_department: string;
  genai_urgency: string;
  python_urgency: string;
  genai_escalation: string;
  python_escalation: string;
  policy_reference: string;
  match: string;
  verification_status: string;
  explanation: string;
  flags: string[];
}

export interface UnseenRunResult {
  processed: number;
  statuses: Record<string, number>;
  errors: string[];
  compared_total: number;
}

export interface UnseenComparison {
  total: number;
  offset: number;
  limit: number;
  rows: UnseenRow[];
}

export interface ReportsOverview {
  dataset: {
    total_cases: number;
    unseen_cases: number;
    train_cases: number;
    unseen_compared: number;
    unseen_remaining: number;
    minimum_required: number;
    requirement_met: boolean;
  };
  generated_at: string;
}

export interface SecurityCaseResult {
  case_id: string;
  name: string;
  category: string;
  passed: boolean;
  details: string[];
}

export interface SecuritySuiteReport {
  total: number;
  passed: number;
  failed: number;
  results: SecurityCaseResult[];
}

export interface SecurityStatus {
  provider: ProviderStatus;
  flagged_documents: number;
  open_manual_reviews: number;
  security_test_cases: number;
  recent_audit: AuditEntry[];
}

export interface AuditEntry {
  id: number;
  actor_email: string;
  action: string;
  entity_type: string;
  entity_id: string;
  detail: Record<string, unknown>;
  ip_address: string;
  created_at: string | null;
}

export interface Paginated<T> {
  total: number;
  items: T[];
}

export interface PromptRow {
  id: number;
  name: string;
  version: string;
  file_path: string;
  is_active: boolean;
  checksum: string;
  notes: string;
  created_at: string | null;
}

export interface PromptsResponse {
  provider: ProviderStatus;
  prompts: PromptRow[];
}

export interface DepartmentRow {
  id: number; name: string; description: string; is_escalation_target: boolean;
  total_complaints?: number; open_complaints?: number; assigned_complaints?: number;
  unassigned_complaints?: number; escalated_complaints?: number; sla_risk?: number; agent_count?: number;
}

export interface CategoryRow {
  id: number; name: string; description: string; sla_hours: number; keywords: string[];
  department_id?: number | null; department_name?: string; total_complaints?: number;
  open_complaints?: number; escalated_complaints?: number; sla_breaches?: number; active?: boolean;
}

export interface SecurityTestMeta {
  case_id: string;
  name: string;
  category: string;
}

export interface TrustScoringCategory {
  name: string;
  weight: number;
  checks: string[];
}

export interface TrustSummary {
  total_assessed: number;
  counts: { verified: number; review_required: number; blocked: number };
  verified_rate: number | null;
  blocked_rate: number | null;
  average_score: number | null;
  open_manual_reviews: number;
  failure_hotspots: NameValue[];
  failing_by_severity: NameValue[];
  failing_by_category: NameValue[];
  scoring: {
    categories: TrustScoringCategory[];
    check_values: Record<string, number>;
    scale: string;
    decision_rule: string;
  };
  recent: TrustAssessment[];
}

export interface LabScenario {
  id: string;
  name: string;
  category: string;
  description: string;
  attack: string;
  expectation: string;
  registry: string;
  uses_fixture: boolean;
  note: string;
}

export interface LabScenarioList {
  registry: string;
  note: string;
  scenarios: LabScenario[];
}

export interface LabRunOutcome {
  expected: string;
  actual: string;
  matched: boolean;
}

export interface LabStep {
  key: string;
  label: string;
  status: string;
  detail: string;
}

export interface LabCheckSummary {
  check_name: string;
  status: string;
  message: string;
}

export interface LabValidationSummary {
  status: string;
  checks: LabCheckSummary[];
}

export interface LabAiOutput {
  provider: string;
  category: string;
  department: string;
  urgency: string;
  priority: string;
  escalation_required: boolean;
  professional_response: string;
  policy_id: string;
}

export interface LabRunResult {
  simulation: boolean;
  note: string;
  scenario: LabScenario;
  outcome: LabRunOutcome;
  complaint: { id: number; code: string; title: string; status: string; flags: string[] };
  ai_output: LabAiOutput;
  validation: LabValidationSummary;
  trust: TrustAssessment | null;
  steps: LabStep[];
  escalation_required: boolean;
  run_at: string;
}

export interface SecurityEventRow {
  id: number;
  event_type: string;
  severity: string;
  title: string;
  detail: Record<string, unknown>;
  complaint_id: number | null;
  complaint_code: string | null;
  document_id: number | null;
  created_at: string | null;
}

export interface SecuritySummary {
  provider: ProviderStatus;
  counts: {
    prompt_injection_complaints: number;
    quarantined_documents: number;
    blocked_responses: number;
    review_required_responses: number;
    verified_responses: number;
    open_manual_reviews: number;
    total_security_events: number;
    critical_security_events: number;
  };
  events_by_type: NameValue[];
  events_by_severity: NameValue[];
  recent_events: SecurityEventRow[];
  review_queue: ManualReview[];
  security_test_cases: { total: number; categories: string[] };
}

export interface SecurityEventsResponse {
  total: number;
  items: SecurityEventRow[];
}

export interface AgentMessage {
  id: number;
  role: "user" | "assistant";
  sender_type: "customer" | "ai" | "agent" | string;
  sender_name: string;
  text: string;
  language?: string;
  modality?: string;
  created_at: string | null;
  meta?: Record<string, unknown>;
}

export interface AgentDashboardData {
  agent: { id: number; name: string; email: string };
  kpis: { pending?: number; new_assigned: number; in_progress: number; waiting_customer: number; urgent: number; sla_at_risk: number; resolved_today: number };
  recent: ComplaintBrief[];
  urgent_queue: ComplaintBrief[];
}

export interface AgentCaseData {
  complaint: ComplaintFull;
  messages: AgentMessage[];
  history: { id: number; from_status: string; to_status: string; note: string; actor_id: number | null; created_at: string | null }[];
  analysis: Analysis | null;
  ai_summary: { category: string; urgency: string; priority: string; sentiment: string; summary: string; suggested_action: string; guidance: string };
  session_id: string;
}
