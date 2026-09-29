import { useCallback, useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import {
  Badge,
  Card,
  EmptyState,
  ErrorBox,
  FullPageSpinner,
  KeyValue,
  Spinner,
} from "../components/ui";
import { api, errorMessage } from "../lib/api";
import { formatDateTime } from "../lib/format";

// The Nova v2 API returns rich nested JSON; we model it loosely here rather
// than duplicating ~20 backend dataclasses into TypeScript interfaces.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Json = any;

const DECISION_TONE: Record<string, string> = {
  "AUTO RESOLVE": "bg-emerald-100 text-emerald-700",
  "HUMAN REVIEW": "bg-amber-100 text-amber-700",
  ESCALATE: "bg-orange-100 text-orange-700",
  BLOCK: "bg-rose-100 text-rose-700",
};

function DecisionBadge({ decision }: { decision?: string }) {
  if (!decision) return <span className="text-slate-400">—</span>;
  return <Badge label={decision} className={DECISION_TONE[decision] || "bg-slate-100 text-slate-600"} />;
}

function TimelineView({ steps }: { steps: Json[] }) {
  if (!steps?.length) return <EmptyState title="No timeline yet" />;
  return (
    <ol className="space-y-3">
      {steps.map((step, i) => (
        <li key={i} className="flex gap-3">
          <div
            className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${
              step.status === "error" ? "bg-rose-500" : step.status === "warning" ? "bg-amber-500" : "bg-brand-500"
            }`}
          />
          <div>
            <p className="text-sm font-medium text-slate-700">{step.label}</p>
            <p className="text-xs text-slate-500">{step.detail}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}

function AgentCard({ agent }: { agent: Json }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg border border-slate-200 p-3">
      <button type="button" className="flex w-full items-center justify-between text-left" onClick={() => setOpen(!open)}>
        <div>
          <p className="text-sm font-semibold text-slate-700">{agent.agent_name.replace(/_/g, " ")}</p>
          <p className="text-xs text-slate-500">{String(agent.decision)}</p>
        </div>
        <span className="text-xs text-slate-400">{open ? "Hide" : "Why?"}</span>
      </button>
      {open && (
        <div className="mt-2 space-y-1 border-t border-slate-100 pt-2 text-xs text-slate-600">
          <p>{agent.reasoning_summary}</p>
          <p className="text-slate-400">Confidence: {agent.confidence} · {agent.model_info?.type}</p>
          {(agent.risk_flags || []).length > 0 && (
            <p className="text-rose-600">Risk flags: {(agent.risk_flags as string[]).join(", ")}</p>
          )}
        </div>
      )}
    </div>
  );
}

export default function CaseRoomPage() {
  const { id } = useParams<{ id: string }>();
  const complaintId = Number(id);
  const [room, setRoom] = useState<Json | null>(null);
  const [loading, setLoading] = useState(true);
  const [investigating, setInvestigating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [challengeTarget, setChallengeTarget] = useState("recommendation");
  const [challengeAnswer, setChallengeAnswer] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api<Json>(`/api/nova/case-room/${complaintId}`);
      setRoom(data);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [complaintId]);

  useEffect(() => {
    void load();
  }, [load]);

  async function runInvestigation() {
    setInvestigating(true);
    setError(null);
    try {
      await api(`/api/nova/investigations/${complaintId}`, { method: "POST" });
      await load();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setInvestigating(false);
    }
  }

  async function decide(decision: string) {
    if (!room?.investigation?.id) return;
    await api(`/api/nova/investigations/${room.investigation.id}/decision`, {
      method: "POST",
      formData: (() => {
        const fd = new FormData();
        fd.set("decision", decision);
        fd.set("notes", "");
        return fd;
      })(),
    });
    await load();
  }

  async function askChallenge() {
    if (!room?.investigation?.id) return;
    const fd = new FormData();
    fd.set("target", challengeTarget);
    fd.set("question", "Challenge from Case Room");
    const result = await api<Json>(`/api/nova/investigations/${room.investigation.id}/challenge`, {
      method: "POST",
      formData: fd,
    });
    setChallengeAnswer(result.response);
  }

  if (loading) return <FullPageSpinner />;
  if (error) return <ErrorBox message={error} onRetry={load} />;
  if (!room) return <EmptyState title="Case not found" />;

  const inv = room.investigation;
  const evidence = room.evidence;

  return (
    <div className="space-y-4">
      <Card
        title={`Case Room — ${room.complaint.code}`}
        actions={
          <button type="button" className="btn btn-primary btn-sm" onClick={runInvestigation} disabled={investigating}>
            {investigating ? <Spinner className="h-4 w-4" /> : inv ? "Re-run investigation" : "Run AI investigation"}
          </button>
        }
      >
        <div className="grid gap-4 sm:grid-cols-2">
          <KeyValue label="Title" value={room.complaint.title} />
          <KeyValue label="Status" value={room.complaint.status} />
          <KeyValue label="SLA" value={`${room.sla.status} — ${room.sla.reason}`} />
          <KeyValue
            label="Trust Gate"
            value={room.trust ? `${room.trust.decision} (${room.trust.score}/100)` : "Not yet assessed"}
          />
        </div>
      </Card>

      {!inv && <EmptyState title="No investigation yet" hint="Run the AI investigation to see agents, evidence and the recommendation." />}

      {inv && (
        <>
          <Card title="Final decision">
            <div className="flex flex-wrap items-center gap-3">
              <DecisionBadge decision={inv.final_decision} />
              <span className="text-sm text-slate-600">
                Trust Gate: <strong>{inv.trust_decision}</strong> ({inv.trust_score}/100)
              </span>
              <span className="text-sm text-slate-600">
                Risk: <strong>{inv.risk_level}</strong>
              </span>
              <span className="text-sm text-slate-600">
                Governance: <strong>{inv.governance_status}</strong>
              </span>
            </div>
            <p className="mt-2 text-sm text-slate-600">{inv.summary?.judge?.reasoning_summary}</p>
            {inv.governance_status !== "auto_resolved" && inv.governance_status !== "human_decided" && (
              <div className="mt-3 flex flex-wrap gap-2">
                <button type="button" className="btn btn-primary btn-sm" onClick={() => decide("approve")}>
                  Approve
                </button>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => decide("modify")}>
                  Modify
                </button>
                <button type="button" className="btn btn-secondary btn-sm" onClick={() => decide("escalate")}>
                  Escalate
                </button>
                <button type="button" className="btn btn-danger btn-sm" onClick={() => decide("reject")}>
                  Reject
                </button>
              </div>
            )}
          </Card>

          <Card title="Investigation timeline">
            <TimelineView steps={inv.timeline || []} />
          </Card>

          <Card title="Evidence">
            <p className="mb-2 text-sm">
              Status:{" "}
              <Badge
                label={evidence.status}
                className={evidence.status === "CONFLICT" ? "bg-rose-100 text-rose-700" : "bg-emerald-100 text-emerald-700"}
              />
            </p>
            {evidence.conflicts?.length > 0 && (
              <div className="mb-2 space-y-1">
                <p className="text-xs font-semibold uppercase text-rose-600">Evidence conflicts</p>
                {evidence.conflicts.map((c: Json, i: number) => (
                  <p key={i} className="text-sm text-rose-700">
                    {c.detail}
                  </p>
                ))}
              </div>
            )}
            {evidence.transaction && (
              <KeyValue
                label="Transaction record"
                value={`${evidence.transaction.payment_status} / ${evidence.transaction.delivery_status} / refund: ${evidence.transaction.refund_status}`}
              />
            )}
          </Card>

          <Card title="Agents">
            <div className="grid gap-2 sm:grid-cols-2">
              {(inv.agents || []).map((agent: Json) => (
                <AgentCard key={agent.id} agent={agent} />
              ))}
            </div>
          </Card>

          <Card title="Challenge AI">
            <div className="flex flex-wrap items-center gap-2">
              <select className="input w-auto" value={challengeTarget} onChange={(e) => setChallengeTarget(e.target.value)}>
                {["evidence", "policy", "risk", "classification", "recommendation"].map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              <button type="button" className="btn btn-secondary btn-sm" onClick={askChallenge}>
                Challenge
              </button>
            </div>
            {challengeAnswer && <p className="mt-2 text-sm text-slate-600">{challengeAnswer}</p>}
          </Card>

          <Card title="Recommended response">
            <p className="whitespace-pre-wrap text-sm text-slate-700">{inv.summary?.response_text}</p>
          </Card>

          {inv.summary?.capa && (
            <Card title={`CAPA proposal — ${inv.summary.capa.code}`}>
              <KeyValue label="Root cause" value={inv.summary.capa.root_cause} />
              <KeyValue label="Corrective action" value={inv.summary.capa.corrective_action} />
              <KeyValue label="Preventive action" value={inv.summary.capa.preventive_action} />
              <KeyValue label="Status" value={inv.summary.capa.status} />
            </Card>
          )}

          <Card title="Financial impact (estimate)">
            <div className="grid gap-2 sm:grid-cols-3">
              <KeyValue label="Direct refund" value={`${inv.summary?.financial?.direct_refund} ${inv.summary?.financial?.currency}`} />
              <KeyValue label="Support cost" value={`${inv.summary?.financial?.support_cost} ${inv.summary?.financial?.currency}`} />
              <KeyValue label="Total estimate" value={`${inv.summary?.financial?.total_estimated_cost} ${inv.summary?.financial?.currency}`} />
            </div>
            <p className="mt-1 text-xs text-slate-400">{inv.summary?.financial?.label}</p>
          </Card>

          <p className="text-xs text-slate-400">Investigation completed {formatDateTime(inv.completed_at)}</p>
        </>
      )}
    </div>
  );
}
