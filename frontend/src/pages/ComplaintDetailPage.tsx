import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  Card,
  CheckBadge,
  EmptyState,
  ErrorBox,
  FullPageSpinner,
  KeyValue,
  MatchBadge,
  SectionList,
  StatusBadge,
  TrustBadge,
  UrgencyBadge,
  VerificationBadge,
  Badge,
} from "../components/ui";
import { AiVsPythonPanel, TrustGatePanel } from "../components/TrustGate";
import { api, errorMessage } from "../lib/api";
import { formatBytes, formatDateTime, timeAgo, titleCase, triggerLabel } from "../lib/format";
import { isStaffRole, useAuth } from "../lib/auth";
import type {
  Analysis,
  ComplaintDetail,
  Comparison,
  Rule,
  Validation,
  AgentMessage,
} from "../lib/types";

const STATUS_OPTIONS = [
  "NEW",
  "ANALYZING",
  "ANALYZED",
  "VALIDATION_FAILED",
  "MANUAL_REVIEW",
  "ESCALATED",
  "IN_PROGRESS",
  "RESOLVED",
  "CLOSED",
];

function ComparisonRows({ summary }: { summary: Record<string, unknown> }) {
  const keys = ["category", "subcategory", "department", "urgency", "priority", "escalation", "follow_up"];
  const rows = keys
    .map((key) => ({ key, comparison: summary[key] as Comparison | undefined }))
    .filter((row): row is { key: string; comparison: Comparison } =>
      Boolean(row.comparison && typeof row.comparison === "object" && "match" in row.comparison),
    );
  if (rows.length === 0) return <EmptyState title="No field comparisons recorded" />;
  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead>
          <tr className="border-b border-slate-100">
            <th className="table-th">Field</th>
            <th className="table-th">Expected (Python / rules)</th>
            <th className="table-th">Actual (GenAI)</th>
            <th className="table-th">Match</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.key} className="border-b border-slate-50">
              <td className="table-td font-medium">{titleCase(row.key)}</td>
              <td className="table-td">{row.comparison.expected || "—"}</td>
              <td className="table-td">{row.comparison.actual || "—"}</td>
              <td className="table-td">
                <MatchBadge match={row.comparison.match ? "MATCH" : "MISMATCH"} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AnalysisSection({ analysis, responseText }: { analysis: Analysis; responseText: string | null }) {
  const parsed = analysis.parsed || {};
  const response = responseText || parsed.professional_response || "";
  return (
    <Card
      title="Pipeline 1 — GenAI analysis"
      actions={
        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
          <span className="chip bg-slate-100 text-slate-600">{analysis.provider}</span>
          {analysis.model && <span className="chip bg-slate-100 text-slate-600">{analysis.model}</span>}
          {analysis.prompt_version && <span className="chip bg-slate-100 text-slate-600">{analysis.prompt_version}</span>}
          <span className="chip bg-slate-100 text-slate-600">{analysis.latency_ms} ms</span>
          {analysis.retry_count > 0 && <span className="chip bg-amber-100 text-amber-700">{analysis.retry_count} retries</span>}
          <span className={`chip ${analysis.is_valid_schema ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}`}>
            {analysis.is_valid_schema ? "schema OK" : "schema invalid"}
          </span>
        </div>
      }
    >
      <div className="grid gap-4 md:grid-cols-3">
        <KeyValue label="Category" value={parsed.issue_category || "—"} />
        <KeyValue label="Subcategory" value={parsed.subcategory || "—"} />
        <KeyValue label="Department" value={parsed.department || "—"} />
        <KeyValue label="Urgency" value={<UrgencyBadge urgency={parsed.urgency} />} />
        <KeyValue label="Priority" value={parsed.priority || "—"} />
        <KeyValue label="Sentiment" value={parsed.sentiment || "—"} />
        <KeyValue
          label="Policy"
          value={
            parsed.policy_id
              ? `${parsed.policy_id}${parsed.policy_section ? ` · s${parsed.policy_section}` : ""} (${parsed.policy_status || "FOUND"})`
              : parsed.policy_status || "POLICY_NOT_FOUND"
          }
        />
        <KeyValue label="Escalation required" value={parsed.escalation_required ? "Yes" : "No"} />
        <KeyValue label="Follow-up required" value={parsed.follow_up_required ? "Yes" : "No"} />
      </div>

      {parsed.escalation_reason && (
        <p className="mt-3 rounded-lg bg-purple-50 px-3 py-2 text-sm text-purple-700">
          Escalation reason: {parsed.escalation_reason}
        </p>
      )}

      {response && (
        <div className="mt-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Professional customer response</p>
          <p className="mt-1 whitespace-pre-wrap rounded-lg bg-slate-50 px-3 py-3 text-sm text-slate-700">{response}</p>
        </div>
      )}

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <SectionList title="Resolution steps" items={parsed.resolution_steps} />
        <SectionList title="Additional issues" items={parsed.additional_issues} />
        <SectionList title="Clarification questions" items={parsed.clarification_questions} />
        <SectionList title="Entities" items={parsed.entities} />
        {parsed.agent_guidance && (
          <div className="md:col-span-2">
            <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Agent guidance</p>
            <p className="mt-1 text-sm text-slate-700">{parsed.agent_guidance}</p>
          </div>
        )}
        {parsed.follow_up_message && (
          <div className="md:col-span-2">
            <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Follow-up message</p>
            <p className="mt-1 text-sm text-slate-700">{parsed.follow_up_message}</p>
          </div>
        )}
      </div>

      {analysis.policy_context.length > 0 && (
        <div className="mt-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Retrieved policy context (traceable)</p>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-100">
                  <th className="table-th">Document</th>
                  <th className="table-th">Section</th>
                  <th className="table-th">Page</th>
                  <th className="table-th">Version</th>
                  <th className="table-th">Source reference</th>
                  <th className="table-th">Score</th>
                </tr>
              </thead>
              <tbody>
                {analysis.policy_context.map((reference, index) => (
                  <tr key={`${reference.document_code}-${reference.section_id}-${index}`} className="border-b border-slate-50">
                    <td className="table-td">
                      <span className="font-mono text-xs">{reference.document_code}</span>
                      <span className="block text-xs text-slate-500">{reference.document_title}</span>
                    </td>
                    <td className="table-td">{reference.section_id || "—"}</td>
                    <td className="table-td">{reference.page}</td>
                    <td className="table-td">{reference.version}</td>
                    <td className="table-td font-mono text-xs text-slate-500">{reference.source_reference}</td>
                    <td className="table-td">{reference.score.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Card>
  );
}

function ValidationSection({ validation }: { validation: Validation }) {
  const summary = validation.summary || {};
  const checks = validation.checks || [];
  const listValue = (value?: string[] | null) => (value && value.length > 0 ? value : null);
  return (
    <Card
      title="Pipeline 2 — Python validation"
      actions={
        <div className="flex flex-wrap items-center gap-2">
          <VerificationBadge status={validation.status} />
          <span className={`chip ${summary.schema_valid ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}`}>
            schema {summary.schema_valid ? "valid" : "invalid"}
          </span>
          <span className={`chip ${summary.policy_valid ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
            policy {summary.policy_valid ? "valid" : "check"}
          </span>
        </div>
      }
    >
      <ComparisonRows summary={summary as Record<string, unknown>} />

      <div className="mt-4 grid gap-4 md:grid-cols-2">
        {listValue(summary.unsupported_claims) && (
          <div className="rounded-lg border border-rose-200 bg-rose-50 p-3">
            <SectionList title="Unsupported claims (hallucination check)" items={summary.unsupported_claims} />
          </div>
        )}
        {listValue(summary.missing_actions) && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
            <SectionList title="Missing required actions" items={summary.missing_actions} />
          </div>
        )}
        {listValue(summary.prohibited_actions_detected) && (
          <div className="rounded-lg border border-rose-200 bg-rose-50 p-3">
            <SectionList title="Prohibited actions detected" items={summary.prohibited_actions_detected} />
          </div>
        )}
        {listValue(summary.contradictions) && (
          <div className="rounded-lg border border-orange-200 bg-orange-50 p-3">
            <SectionList title="Contradictions" items={summary.contradictions} />
          </div>
        )}
        {listValue(summary.manual_review_reasons) && (
          <div className="rounded-lg border border-purple-200 bg-purple-50 p-3">
            <SectionList title="Manual review reasons" items={summary.manual_review_reasons} />
          </div>
        )}
        {summary.injection_detected && (
          <div className="rounded-lg border border-rose-300 bg-rose-100 p-3 text-sm text-rose-800">
            Prompt injection detected in the complaint text — validation escalated to a human reviewer.
          </div>
        )}
      </div>

      {checks.length > 0 && (
        <div className="mt-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-400">All validation checks</p>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-100">
                  <th className="table-th">Check</th>
                  <th className="table-th">Expected</th>
                  <th className="table-th">Actual</th>
                  <th className="table-th">Status</th>
                  <th className="table-th">Message</th>
                </tr>
              </thead>
              <tbody>
                {checks.map((check) => (
                  <tr key={check.id} className="border-b border-slate-50">
                    <td className="table-td font-medium">{titleCase(check.check_name)}</td>
                    <td className="table-td max-w-[200px] truncate">{check.expected || "—"}</td>
                    <td className="table-td max-w-[200px] truncate">{check.actual || "—"}</td>
                    <td className="table-td">
                      <CheckBadge status={check.status} />
                    </td>
                    <td className="table-td max-w-[280px] text-xs text-slate-500">{check.message}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Card>
  );
}

function CustomerSlaCountdown({ dueAt }: { dueAt: string | null }) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!dueAt) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [dueAt]);
  if (!dueAt) return <strong>Next update after review</strong>;
  const diff = new Date(dueAt).getTime() - now;
  if (diff <= 0) return <strong className="overdue">Update due now</strong>;
  const total = Math.floor(diff / 1000);
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const mins = Math.floor((total % 3600) / 60);
  const secs = total % 60;
  return <strong>{days > 0 ? `${days}d ${hours}h ${mins}m` : hours > 0 ? `${hours}h ${mins}m` : `${mins}m ${secs}s`}</strong>;
}

function CustomerLiveConversation({ complaintId }: { complaintId: number }) {
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [draft, setDraft] = useState("");
  const [sending, setSending] = useState(false);
  const load = useCallback(async () => {
    try {
      const data = await api<AgentMessage[]>(`/api/complaints/${complaintId}/messages`);
      setMessages(data || []); setError("");
    } catch (e) { setError(errorMessage(e)); } finally { setLoading(false); }
  }, [complaintId]);
  useEffect(() => { void load(); const id = window.setInterval(() => void load(), 8000); return () => window.clearInterval(id); }, [load]);
  const send = async () => {
    if (!draft.trim() || sending) return;
    setSending(true);
    try { await api(`/api/complaints/${complaintId}/messages`, { method: "POST", body: { message: draft.trim() } }); setDraft(""); await load(); }
    catch (e) { setError(errorMessage(e)); } finally { setSending(false); }
  };
  if (loading && messages.length === 0) return null;
  return <section className="customer-simple-card customer-live-thread">
    <div className="detail-card-label">LIVE SUPPORT CONVERSATION</div>
    <div className="customer-live-thread-head"><div><h2>Your support conversation</h2><p>Nova and your support agent are kept in the same complaint thread.</p></div><span><i/> Live updates</span></div>
    {error ? <p className="muted">{error}</p> : messages.length === 0 ? <p className="muted">Your support conversation will appear here when a team member joins the case.</p> : <div className="customer-live-messages">{messages.map(m => <div className={`customer-live-message ${m.sender_type}`} key={m.id}><div className="customer-live-avatar">{m.sender_type==='agent'?'A':m.sender_type==='ai'?'N':'You'}</div><div><div className="customer-live-meta"><strong>{m.sender_type==='agent'?(m.sender_name||'Support Agent'):m.sender_type==='ai'?'Nova':'You'}</strong><span>{m.created_at?new Date(m.created_at).toLocaleString():''}</span></div><div className="customer-live-bubble">{m.text}</div></div></div>)}</div>}
    <div className="customer-live-composer" style={{marginTop:16,display:"grid",gap:8}}>
      <textarea value={draft} onChange={e=>setDraft(e.target.value)} onKeyDown={e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();void send();}}} rows={3} placeholder="Write a message to your support agent…" style={{width:"100%",padding:12,borderRadius:12,border:"1px solid rgba(0,0,0,.15)"}}/>
      <div style={{display:"flex",justifyContent:"space-between",alignItems:"center"}}><small style={{opacity:.7}}>Your agent sees this message instantly in the same complaint thread.</small><button className="btn btn-primary" disabled={!draft.trim()||sending} onClick={()=>void send()}>{sending?"Sending…":"Send to agent →"}</button></div>
    </div>
  </section>;
}

function CustomerComplaintView({ detail }: { detail: ComplaintDetail }) {
  const { complaint, analysis } = detail;
  const parsed = analysis?.parsed || {};
  const response = parsed.professional_response || parsed.follow_up_message || "Your complaint has been received. Our support team will review it and update you here.";
  const [rating, setRating] = useState(detail.feedback?.rating || 0);
  const [comment, setComment] = useState(detail.feedback?.comment || "");
  const [feedbackBusy, setFeedbackBusy] = useState(false);
  const [feedbackMessage, setFeedbackMessage] = useState(detail.feedback ? "Thanks — your feedback is already recorded." : "");
  const [feedbackError, setFeedbackError] = useState("");

  const progressIndex = complaint.status === "NEW" ? 0 : ["ANALYZING", "ANALYZED", "VALIDATION_FAILED", "MANUAL_REVIEW", "ESCALATED"].includes(complaint.status) ? 1 : complaint.status === "IN_PROGRESS" ? 2 : 3;
  const steps = ["Complaint received", "Support is reviewing", "Our team is working", "Resolution"];
  const statusExplanation = complaint.status === "MANUAL_REVIEW" || complaint.status === "ESCALATED"
    ? "Your complaint has been sent to a support team member for the next step."
    : complaint.status === "VALIDATION_FAILED"
      ? "We need to verify some information before we can continue."
      : complaint.status === "IN_PROGRESS"
        ? "Our support team is actively working on your issue. We will post the next update here."
        : complaint.status === "RESOLVED" || complaint.status === "CLOSED"
          ? "Your issue has been marked as resolved. Check the resolution below to see what was done."
          : "Your complaint was received successfully and is being reviewed.";

  const submitFeedback = async () => {
    if (!rating || feedbackBusy) return;
    setFeedbackBusy(true);
    setFeedbackError("");
    try {
      await api(`/api/complaints/${complaint.id}/feedback`, { method: "POST", body: { rating, comment } });
      setFeedbackMessage("Thanks — your feedback has been saved.");
    } catch (err) {
      setFeedbackError(errorMessage(err));
    } finally {
      setFeedbackBusy(false);
    }
  };

  return (
    <div className="customer-detail-page">
      <div className="customer-page-heading">
        <div><button className="customer-link-button" onClick={() => window.history.back()}>← Back</button><p className="customer-kicker">Complaint {complaint.code}</p><h1>{complaint.title}</h1><p>{complaint.created_at ? formatDateTime(complaint.created_at) : ""}</p></div>
        <span className={`customer-status status-${complaint.status.toLowerCase()}`}>{({NEW:"Submitted",ANALYZING:"Under review",ANALYZED:"Under review",MANUAL_REVIEW:"Support review",ESCALATED:"Sent to support",IN_PROGRESS:"In progress",RESOLVED:"Resolved",CLOSED:"Closed",VALIDATION_FAILED:"Needs information"} as Record<string,string>)[complaint.status] || "In progress"}</span>
      </div>

      <div className="customer-detail-grid">
        <section className="customer-simple-card">
          <div className="detail-card-label">WHAT WE RECEIVED</div>
          <h2>Your complaint</h2>
          <p>{complaint.description}</p>
          <div className="detail-facts">
            {complaint.product_or_service && <div><small>Service</small><strong>{complaint.product_or_service}</strong></div>}
            {complaint.order_reference && <div><small>Reference</small><strong>{complaint.order_reference}</strong></div>}
            {complaint.requested_resolution && <div><small>You asked for</small><strong>{complaint.requested_resolution}</strong></div>}
          </div>
        </section>

        <section className="customer-simple-card">
          <div className="detail-card-label">NEXT UPDATE</div>
          <h2>What happens next?</h2>
          <div className="sla-highlight"><span>⏱</span><div><small>Expected update / SLA</small><CustomerSlaCountdown dueAt={complaint.sla_due_at} /></div></div>
          <p className="status-explanation">{statusExplanation}</p>
          <div className="customer-progress customer-progress-v2">
            {steps.map((label, i) => <div className={`progress-step ${i <= progressIndex ? "done" : ""} ${i === progressIndex ? "current" : ""}`} key={label}><span>{i < progressIndex ? "✓" : i + 1}</span><div><strong>{label}</strong>{i === progressIndex && <small>Current stage</small>}</div></div>)}
          </div>
        </section>

        <section className="customer-answer-card full-width">
          <div className="assistant-avatar">N</div>
          <div><div className="assistant-title"><strong>Nova Support</strong><span>Latest guidance</span></div><p>{response}</p>
            {parsed.escalation_reason && <div className="customer-followup"><strong>Why this was escalated:</strong><p>{parsed.escalation_reason}</p></div>}
            {(parsed.clarification_questions || []).length > 0 && <div className="customer-followup"><strong>Please send:</strong><ul>{(parsed.clarification_questions || []).map((q, i) => <li key={i}>{q}</li>)}</ul></div>}
          </div>
        </section>
      </div>

      <CustomerLiveConversation complaintId={complaint.id} />

      <section className="customer-simple-card customer-timeline-card">
        <div className="detail-card-label">LIVE TIMELINE</div>
        <h2>Everything that happened</h2>
        <div className="customer-history-timeline">
          {detail.history.length === 0 ? <p className="muted">Your complaint was received. More events will appear here as the workflow progresses.</p> : detail.history.map((event, index) => <div className="customer-history-event" key={event.id}><div className={`timeline-dot ${index === detail.history.length - 1 ? "current" : ""}`}>{index === detail.history.length - 1 ? "●" : "✓"}</div><div><div className="timeline-title"><strong>{event.to_status?.replace(/_/g, " ") || "Update"}</strong><span>{timeAgo(event.created_at)}</span></div><p>{event.note || "Complaint status updated."}</p></div></div>)}
        </div>
      </section>

      {(complaint.status === "RESOLVED" || complaint.status === "CLOSED") && (
        <section className="customer-feedback-card">
          <div><div className="detail-card-label">YOUR EXPERIENCE</div><h2>Was your issue resolved?</h2><p>Rate the support you received. Your feedback is attached to this complaint and helps improve the service.</p></div>
          <div className="feedback-stars">{[1,2,3,4,5].map(value => <button key={value} className={value <= rating ? "active" : ""} onClick={() => setRating(value)} aria-label={`${value} star${value > 1 ? "s" : ""}`}>★</button>)}</div>
          <textarea className="feedback-textarea" value={comment} onChange={e => setComment(e.target.value)} placeholder="Optional: tell us what went well or what we can improve…" rows={3} />
          <div className="feedback-actions"><span>{feedbackError || feedbackMessage}</span><button className="customer-button primary" disabled={!rating || feedbackBusy} onClick={() => void submitFeedback()}>{feedbackBusy ? "Saving…" : detail.feedback ? "Update feedback" : "Submit feedback →"}</button></div>
        </section>
      )}
    </div>
  );
}

function RuleSection({ rule }: { rule: Rule }) {
  return (
    <Card
      title="Matched rule (deterministic ground truth)"
      actions={
        <div className="flex items-center gap-2">
          <span className="chip bg-brand-100 text-brand-700 font-mono">{rule.rule_id}</span>
          {rule.escalation && <span className="chip bg-purple-100 text-purple-700">escalation</span>}
        </div>
      }
    >
      <div className="grid gap-4 md:grid-cols-4">
        <KeyValue label="Category" value={rule.category} />
        <KeyValue label="Subcategory" value={rule.subcategory || "—"} />
        <KeyValue label="Department" value={rule.department} />
        <KeyValue label="Urgency / Priority" value={`${rule.urgency} · ${rule.priority}`} />
        <KeyValue label="Policy" value={rule.policy_id || "—"} />
        <KeyValue label="Follow-up" value={rule.follow_up ? "Required" : "Not required"} />
        {rule.escalation_reason && <KeyValue label="Escalation reason" value={rule.escalation_reason} />}
        {rule.escalation_department && <KeyValue label="Escalate to" value={rule.escalation_department} />}
      </div>
      <div className="mt-4 grid gap-4 md:grid-cols-3">
        <SectionList title="Keywords" items={rule.keywords} />
        <SectionList title="Required actions" items={rule.required_actions} />
        <SectionList title="Prohibited actions" items={rule.prohibited_actions} />
      </div>
      {rule.response_template && (
        <div className="mt-4">
          <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Response template</p>
          <p className="mt-1 whitespace-pre-wrap rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600">
            {rule.response_template}
          </p>
        </div>
      )}
    </Card>
  );
}

export default function ComplaintDetailPage() {
  const { id } = useParams();
  const complaintId = Number(id);
  const { user } = useAuth();
  const isStaff = isStaffRole(user?.role);

  const [detail, setDetail] = useState<ComplaintDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionError, setActionError] = useState("");
  const [pending, setPending] = useState("");
  const [statusValue, setStatusValue] = useState("");
  const [statusNote, setStatusNote] = useState("");
  const [responseText, setResponseText] = useState<string | null>(null);
  const [attachment, setAttachment] = useState<File | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await api<ComplaintDetail>(`/api/complaints/${complaintId}`);
      setDetail(data);
      setStatusValue(data.complaint.status);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [complaintId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function runAction(name: string, action: () => Promise<unknown>) {
    setPending(name);
    setActionError("");
    try {
      await action();
      await load();
    } catch (err) {
      setActionError(errorMessage(err));
    } finally {
      setPending("");
    }
  }

  if (loading) return <FullPageSpinner />;
  if (error) return <ErrorBox message={error} onRetry={() => void load()} />;
  if (!detail) return null;

  if (!isStaff) return <CustomerComplaintView detail={detail} />;

  const { complaint, rule, analysis, validation, trust } = detail;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <Link to="/complaints" className="text-sm text-brand-600 hover:underline">
            ← Complaints
          </Link>
          <span className="font-mono text-sm text-slate-400">{complaint.code}</span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge status={complaint.status} />
          <UrgencyBadge urgency={complaint.verified_urgency || complaint.urgency} />
          {complaint.priority && <Badge label={complaint.priority} className="bg-slate-100 text-slate-600" />}
          <VerificationBadge status={complaint.verification_status} />
          {trust && <TrustBadge decision={trust.decision} />}
          {complaint.injection_detected && <Badge label="injection" className="bg-rose-100 text-rose-700" />}
          {complaint.is_dataset_case && <Badge label="dataset" className="bg-slate-100 text-slate-500" />}
        </div>
      </div>

      {actionError && <ErrorBox message={actionError} />}

      <Card
        title={complaint.title}
        actions={
          isStaff ? (
            <div className="flex flex-wrap gap-2">
              <Link to={`/case-room/${complaint.id}`} className="btn btn-secondary btn-sm">
                Open Case Room
              </Link>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                disabled={pending !== ""}
                onClick={() => void runAction("analyze", () => api(`/api/complaints/${complaint.id}/analyze`, { method: "POST" }))}
              >
                {pending === "analyze" ? "Analyzing…" : "Run GenAI analysis"}
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={pending !== "" || !analysis}
                onClick={() => void runAction("validate", () => api(`/api/complaints/${complaint.id}/validate`, { method: "POST" }))}
              >
                {pending === "validate" ? "Validating…" : "Run Python validation"}
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={pending !== "" || !analysis}
                onClick={() =>
                  void runAction("response", async () => {
                    const result = await api<{ professional_response: string }>(
                      `/api/complaints/${complaint.id}/response`,
                      { method: "POST" },
                    );
                    setResponseText(result.professional_response);
                  })
                }
              >
                {pending === "response" ? "Regenerating…" : "Regenerate response"}
              </button>
            </div>
          ) : undefined
        }
      >
        <p className="whitespace-pre-wrap text-sm text-slate-700">{complaint.description}</p>

        <div className="mt-4 grid gap-4 md:grid-cols-4">
          <KeyValue label="Customer type" value={complaint.customer_type || "—"} />
          <KeyValue label="Product / service" value={complaint.product_or_service || "—"} />
          <KeyValue label="Order reference" value={complaint.order_reference || "—"} />
          <KeyValue label="Channel" value={complaint.channel || "—"} />
          <KeyValue label="Complaint date" value={complaint.complaint_date ? formatDateTime(complaint.complaint_date) : "—"} />
          <KeyValue label="Requested resolution" value={complaint.requested_resolution || "—"} />
          <KeyValue label="Previous complaints" value={complaint.previous_complaints} />
          <KeyValue label="SLA due" value={formatDateTime(complaint.sla_due_at)} />
          <KeyValue label="Created" value={formatDateTime(complaint.created_at)} />
          <KeyValue label="Updated" value={formatDateTime(complaint.updated_at)} />
          {complaint.supporting_document_name && (
            <KeyValue label="Supporting document" value={complaint.supporting_document_name} />
          )}
          {complaint.matched_rule_id && <KeyValue label="Matched rule" value={<span className="font-mono text-xs">{complaint.matched_rule_id}</span>} />}
        </div>

        {complaint.missing_fields.length > 0 && (
          <p className="mt-3 text-sm text-amber-700">
            Missing fields: {complaint.missing_fields.join(", ")}
          </p>
        )}

        {complaint.attachments.length > 0 && (
          <div className="mt-4">
            <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Attachments</p>
            <ul className="mt-1 space-y-1 text-sm text-slate-600">
              {complaint.attachments.map((item) => (
                <li key={item.id}>
                  {item.file_name} <span className="text-xs text-slate-400">({formatBytes(item.size_bytes)})</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {isStaff && (
          <div className="mt-4 flex flex-wrap items-end gap-2 border-t border-slate-100 pt-4">
            <div>
              <label className="label">Update status</label>
              <select className="input mt-1" value={statusValue} onChange={(event) => setStatusValue(event.target.value)}>
                {STATUS_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </div>
            <div className="min-w-[200px] flex-1">
              <label className="label">Note</label>
              <input
                className="input mt-1"
                value={statusNote}
                onChange={(event) => setStatusNote(event.target.value)}
                placeholder="Reason for the status change…"
              />
            </div>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={pending !== "" || statusValue === complaint.status}
              onClick={() =>
                void runAction("status", async () => {
                  await api(`/api/complaints/${complaint.id}/status`, {
                    method: "POST",
                    body: { status: statusValue, note: statusNote },
                  });
                  setStatusNote("");
                })
              }
            >
              {pending === "status" ? "Updating…" : "Update"}
            </button>
            <div>
              <label className="label">Attachment</label>
              <div className="mt-1 flex items-center gap-2">
                <input
                  type="file"
                  className="text-xs text-slate-500"
                  onChange={(event) => setAttachment(event.target.files?.[0] || null)}
                />
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={!attachment || pending !== ""}
                  onClick={() => {
                    if (!attachment) return;
                    void runAction("attachment", () => {
                      const formData = new FormData();
                      formData.append("file", attachment);
                      return api(`/api/complaints/${complaint.id}/attachments`, { method: "POST", formData });
                    });
                    setAttachment(null);
                  }}
                >
                  {pending === "attachment" ? "Uploading…" : "Upload"}
                </button>
              </div>
            </div>
          </div>
        )}
      </Card>

      {detail.duplicate_of && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          Possible duplicate of{" "}
          <Link className="font-medium underline" to={`/complaints/${detail.duplicate_of.id}`}>
            {detail.duplicate_of.code} — {detail.duplicate_of.title}
          </Link>{" "}
          (similarity {(complaint.duplicate_similarity * 100).toFixed(0)}%). Linked, never auto-merged.
        </div>
      )}

      {trust && <TrustGatePanel trust={trust} />}

      {validation && <AiVsPythonPanel validation={validation} />}

      {analysis ? <AnalysisSection analysis={analysis} responseText={responseText} /> : (
        <Card title="Pipeline 1 — GenAI analysis">
          <EmptyState title="No analysis yet" hint="Run the GenAI analysis to populate this section." />
        </Card>
      )}

      {validation ? <ValidationSection validation={validation} /> : (
        <Card title="Pipeline 2 — Python validation">
          <EmptyState title="No validation yet" hint="Validation runs after the GenAI analysis exists." />
        </Card>
      )}

      {rule && <RuleSection rule={rule} />}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title="Escalations">
          {detail.escalations.length === 0 ? (
            <EmptyState title="No escalations" />
          ) : (
            <ul className="space-y-3">
              {detail.escalations.map((escalation) => (
                <li key={escalation.id} className="rounded-lg border border-slate-100 p-3">
                  <div className="flex items-center justify-between">
                    <span className="chip bg-purple-100 text-purple-700">{escalation.status}</span>
                    <span className="text-xs text-slate-400">{timeAgo(escalation.created_at)}</span>
                  </div>
                  <p className="mt-1 text-sm text-slate-700">{escalation.reason}</p>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {escalation.department} · priority {escalation.priority}
                  </p>
                  {escalation.triggers.length > 0 && (
                    <p className="mt-1 text-xs text-slate-400">
                      {escalation.triggers.map((trigger) => triggerLabel(trigger)).join(" · ")}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Manual reviews">
          {detail.manual_reviews.length === 0 ? (
            <EmptyState title="No manual reviews" />
          ) : (
            <ul className="space-y-3">
              {detail.manual_reviews.map((review) => (
                <li key={review.id} className="rounded-lg border border-slate-100 p-3">
                  <div className="flex items-center justify-between">
                    <span className={`chip ${review.status === "OPEN" ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-600"}`}>
                      {review.status}
                    </span>
                    <span className="text-xs text-slate-400">
                      {review.source} · {timeAgo(review.created_at)}
                    </span>
                  </div>
                  <p className="mt-1 text-sm text-slate-700">{review.reason}</p>
                  {review.decision && (
                    <p className="mt-1 text-xs text-slate-500">
                      Decision: <strong>{review.decision}</strong>
                      {review.decision_notes ? ` — ${review.decision_notes}` : ""}
                    </p>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>

      <Card title="History">
        {detail.history.length === 0 ? (
          <EmptyState title="No history yet" />
        ) : (
          <ol className="space-y-3">
            {detail.history.map((entry) => (
              <li key={entry.id} className="flex gap-3">
                <div className="mt-1 h-2 w-2 shrink-0 rounded-full bg-brand-500" />
                <div>
                  <p className="text-sm text-slate-700">
                    {entry.from_status ? `${entry.from_status} → ` : ""}
                    <strong>{entry.to_status}</strong>
                  </p>
                  <p className="text-xs text-slate-500">
                    {entry.note} · {timeAgo(entry.created_at)}
                    {entry.actor_id ? ` · actor #${entry.actor_id}` : ""}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        )}
      </Card>
    </div>
  );
}
