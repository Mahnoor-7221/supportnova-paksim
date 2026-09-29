import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Card,
  EmptyState,
  ErrorBox,
  FullPageSpinner,
  StatCard,
  StatusBadge,
  VerificationBadge,
  UrgencyBadge,
} from "../components/ui";
import { api, errorMessage } from "../lib/api";
import { timeAgo, titleCase, triggerLabel } from "../lib/format";
import type { DashboardData, NameValue, TrendPoint } from "../lib/types";

const PALETTE = ["#1d5649", "#6e927d", "#b18a4b", "#86a88f", "#b95f55", "#526b61", "#9b8b69", "#c8bda4"];

function PieBlock({ title, data }: { title: string; data: NameValue[] }) {
  return (
    <Card title={title}>
      {data.length === 0 ? (
        <EmptyState title="No data yet" />
      ) : (
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie data={data} dataKey="value" nameKey="name" innerRadius={42} outerRadius={78} paddingAngle={2}>
                {data.map((entry, index) => (
                  <Cell key={entry.name} fill={PALETTE[index % PALETTE.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>
      )}
      <div className="mt-2 flex flex-wrap gap-2">
        {data.slice(0, 6).map((entry, index) => (
          <span key={entry.name} className="inline-flex items-center gap-1.5 text-xs text-slate-500">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ backgroundColor: PALETTE[index % PALETTE.length] }}
            />
            {titleCase(entry.name)} · {entry.value}
          </span>
        ))}
      </div>
    </Card>
  );
}

function BarBlock({ title, data }: { title: string; data: NameValue[] }) {
  return (
    <Card title={title}>
      {data.length === 0 ? (
        <EmptyState title="No data yet" />
      ) : (
        <div className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data.slice(0, 8)} margin={{ top: 4, right: 8, bottom: 4, left: -18 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#ddd8ca" vertical={false} />
              <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} angle={-18} textAnchor="end" height={50} />
              <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="value" fill="#1d5649" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </Card>
  );
}

function TrendBlock({ title, data }: { title: string; data: TrendPoint[] }) {
  return (
    <Card title={title}>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: -18 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#ddd8ca" vertical={false} />
            <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(value: string) => value.slice(5)} />
            <YAxis tick={{ fontSize: 11 }} allowDecimals={false} />
            <Tooltip />
            <Line type="monotone" dataKey="count" stroke="#b18a4b" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </Card>
  );
}

function RiskRow({ label, value, max, tone }: { label: string; value: number; max: number; tone: string }) {
  return (
    <div>
      <div className="flex items-center justify-between text-sm">
        <span className="text-slate-600">{label}</span>
        <span className="font-semibold text-slate-700">{value}</span>
      </div>
      <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-100">
        <div
          className={`h-full rounded-full ${tone}`}
          style={{ width: value === 0 ? "0%" : `${Math.max(4, Math.round((value / max) * 100))}%` }}
        />
      </div>
    </div>
  );
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await api<DashboardData>("/api/dashboard"));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) return <FullPageSpinner />;
  if (error) return <ErrorBox message={error} onRetry={() => void load()} />;
  if (!data) return null;

  const { totals, charts, provider, trust, risk } = data;
  const maxLevel = Math.max(1, risk.levels.critical, risk.levels.high, risk.levels.medium, risk.levels.low);
  const maxAi = Math.max(
    1,
    risk.ai_risks.hallucination,
    risk.ai_risks.policy_mismatch,
    risk.ai_risks.injection,
    risk.ai_risks.escalation_gap,
  );
  const trustCells = [
    { label: "Assessed", value: trust.assessed, tone: "text-slate-800", hint: "Trust Gate verdicts" },
    { label: "Verified", value: trust.verified, tone: "text-emerald-600", hint: "released clean" },
    { label: "Review required", value: trust.review_required, tone: "text-amber-600", hint: "human decides" },
    { label: "Blocked", value: trust.blocked, tone: "text-rose-600", hint: "never shipped" },
    { label: "Average score", value: trust.average_score ?? "—", tone: "text-brand-600", hint: "transparent 0–100" },
  ];

  return (
    <div className="adm-page">
      <div className="agent-dash-hero">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-[0.2em] text-emerald-100/90">
              Agent Workspace
            </p>
            <h1>Your queue · Prioritize · Resolve</h1>
            <p>
              Urgent and critical complaints appear first. Work through assigned cases, update status with clear notes,
              and escalate when SLA is at risk.
            </p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Link to="/complaints?filter=urgent" className="btn btn-sm bg-white/15 text-white hover:bg-white/25">
                ⚠ Urgent queue
              </Link>
              <Link to="/complaints?filter=mine" className="btn btn-sm bg-white/15 text-white hover:bg-white/25">
                My complaints
              </Link>
              <Link to="/review" className="btn btn-sm bg-white/15 text-white hover:bg-white/25">
                AI review
              </Link>
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-slate-200">
            <span className={`chip ${provider.genai_live ? "bg-emerald-500/25 text-emerald-100" : "bg-amber-500/25 text-amber-100"}`}>
              {provider.genai_live ? "GenAI live" : "Offline baseline"}
            </span>
            <span className="chip bg-white/10">
              {provider.effective_provider}{provider.model ? ` · ${provider.model}` : ""}
            </span>
          </div>
        </div>
      </div>

      {/* KPI strip */}
      <div className="adm-kpi-grid">
        <div className="adm-kpi adm-kpi-coral">
          <span className="adm-kpi-label">Critical / P1</span>
          <span className="adm-kpi-value">{risk.levels.critical ?? 0}</span>
        </div>
        <div className="adm-kpi adm-kpi-amber">
          <span className="adm-kpi-label">High / P2</span>
          <span className="adm-kpi-value">{risk.levels.high ?? 0}</span>
        </div>
        <div className="adm-kpi adm-kpi-brass">
          <span className="adm-kpi-label">In progress</span>
          <span className="adm-kpi-value">{totals.in_progress ?? totals.open ?? 0}</span>
        </div>
        <div className="adm-kpi adm-kpi-emerald">
          <span className="adm-kpi-label">Resolved</span>
          <span className="adm-kpi-value">{totals.resolved ?? 0}</span>
        </div>
        <div className="adm-kpi adm-kpi-rose">
          <span className="adm-kpi-label">Escalated</span>
          <span className="adm-kpi-value">{totals.escalated ?? 0}</span>
        </div>
        <div className="adm-kpi adm-kpi-forest">
          <span className="adm-kpi-label">Trust verified</span>
          <span className="adm-kpi-value">{trust.verified ?? 0}</span>
        </div>
      </div>

      {/* Urgent callout */}
      {(risk.levels.critical > 0 || risk.levels.high > 0) && (
        <div className="urgent-queue">
          <h2>⚠ Urgent / Critical queue</h2>
          <p className="text-sm text-slate-600 mb-3">
            {risk.levels.critical} critical and {risk.levels.high} high-priority open cases need attention.
            Open the urgent filter to work them first.
          </p>
          <Link to="/complaints?filter=urgent" className="btn btn-sm" style={{ background: "#9f4f49", color: "#fff" }}>
            Open urgent queue →
          </Link>
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Complaint Risk Radar — open cases by level">
          <div className="space-y-3">
            <RiskRow label="Critical (P1 / Critical urgency)" value={risk.levels.critical} max={maxLevel} tone="bg-rose-500" />
            <RiskRow label="High (P2)" value={risk.levels.high} max={maxLevel} tone="bg-orange-500" />
            <RiskRow label="Medium (P3)" value={risk.levels.medium} max={maxLevel} tone="bg-amber-400" />
            <RiskRow label="Low (P4)" value={risk.levels.low} max={maxLevel} tone="bg-slate-300" />
          </div>
          <p className="mt-3 text-xs text-slate-400">
            Priority uses the verified (Python) values, falling back to the GenAI values on existing records.
          </p>
        </Card>

        <Card title="AI risk signals (from Trust assessments)">
          <div className="space-y-3">
            <RiskRow label="Hallucination — unsupported claims" value={risk.ai_risks.hallucination} max={maxAi} tone="bg-rose-500" />
            <RiskRow label="Policy mismatch or fake citation" value={risk.ai_risks.policy_mismatch} max={maxAi} tone="bg-orange-500" />
            <RiskRow label="Prompt injection" value={risk.ai_risks.injection} max={maxAi} tone="bg-rose-500" />
            <RiskRow label="Escalation gap — missed escalation" value={risk.ai_risks.escalation_gap} max={maxAi} tone="bg-amber-400" />
          </div>
          <p className="mt-3 text-xs text-slate-400">
            Counted from genuinely failed checks across every Trust Gate assessment.
          </p>
        </Card>

        <Card title="Operational risk">
          <ul className="space-y-3">
            <li className="flex items-center justify-between text-sm">
              <span className="text-slate-600">Critical open escalations</span>
              <span className={`chip ${risk.critical_open_escalations > 0 ? "bg-rose-100 text-rose-700" : "bg-emerald-100 text-emerald-700"}`}>
                {risk.critical_open_escalations}
              </span>
            </li>
            <li className="flex items-center justify-between text-sm">
              <span className="text-slate-600">SLA at risk (open)</span>
              <span className={`chip ${risk.sla_risk_open > 0 ? "bg-amber-100 text-amber-700" : "bg-emerald-100 text-emerald-700"}`}>
                {risk.sla_risk_open}
              </span>
            </li>
            <li className="flex items-center justify-between text-sm">
              <span className="text-slate-600">Security events recorded</span>
              <span className="chip bg-slate-100 text-slate-600">{risk.open_security_events}</span>
            </li>
            <li className="flex items-center justify-between text-sm">
              <span className="text-slate-600">Critical security events</span>
              <span className={`chip ${risk.critical_security_events > 0 ? "bg-rose-100 text-rose-700" : "bg-emerald-100 text-emerald-700"}`}>
                {risk.critical_security_events}
              </span>
            </li>
          </ul>
          <p className="mt-3 text-xs text-slate-400">
            The full event timeline lives in the Security Command Center (admin role).
          </p>
        </Card>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard label="Total complaints" value={totals.total} tone="brand" hint={`${totals.open} open`} />
        <StatCard label="Escalated" value={totals.escalated} tone="purple" hint={`${totals.high_priority} high priority`} />
        <StatCard label="Manual review" value={totals.manual_review} tone="amber" hint={`${totals.manual_review_required} validation-required`} />
        <StatCard label="SLA risk" value={totals.sla_risk} tone="rose" hint="past SLA due date" />
        <StatCard label="Verified" value={totals.verified} tone="emerald" hint={`${totals.verified_with_warning} with warning`} />
        <StatCard label="Mismatches" value={totals.mismatches} tone="rose" hint={`${totals.validation_failed} validation failed`} />
        <StatCard label="Injections" value={totals.injections} tone="rose" hint={`${totals.duplicates} duplicates flagged`} />
        <StatCard label="Unverified" value={totals.unverified} tone="slate" hint={`${totals.incomplete} incomplete · ${totals.resolved} resolved`} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <TrendBlock title="Complaints — last 14 days" data={charts.complaints_trend} />
        <TrendBlock title="Escalations — last 14 days" data={charts.escalation_trend} />
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <PieBlock title="Status" data={charts.status} />
        <PieBlock title="Verification" data={charts.verification} />
        <BarBlock title="Categories" data={charts.category} />
        <BarBlock title="Departments" data={charts.department} />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card title="Recent complaints" className="lg:col-span-2">
          {data.recent_complaints.length === 0 ? (
            <EmptyState title="No complaints yet" hint="Submit a complaint to get started." />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className="table-th">Code</th>
                    <th className="table-th">Title</th>
                    <th className="table-th">Status</th>
                    <th className="table-th">Urgency</th>
                    <th className="table-th">Verification</th>
                    <th className="table-th">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent_complaints.map((complaint) => (
                    <tr key={complaint.id} className="border-b border-slate-50 hover:bg-slate-50">
                      <td className="table-td font-mono text-xs">
                        <Link className="text-brand-600 hover:underline" to={`/complaints/${complaint.id}`}>
                          {complaint.code}
                        </Link>
                      </td>
                      <td className="table-td max-w-[240px] truncate">{complaint.title}</td>
                      <td className="table-td">
                        <StatusBadge status={complaint.status} />
                      </td>
                      <td className="table-td">
                        <UrgencyBadge urgency={complaint.verified_urgency || complaint.urgency} />
                      </td>
                      <td className="table-td">
                        <VerificationBadge status={complaint.verification_status} />
                      </td>
                      <td className="table-td text-xs text-slate-500">{timeAgo(complaint.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>

        <div className="space-y-4">
          <Card title="Recent escalations">
            {data.recent_escalations.length === 0 ? (
              <EmptyState title="No escalations yet" />
            ) : (
              <ul className="space-y-3">
                {data.recent_escalations.map((escalation) => (
                  <li key={escalation.id} className="border-b border-slate-50 pb-2 last:border-0">
                    <div className="flex items-center justify-between gap-2">
                      <Link
                        className="font-mono text-xs text-brand-600 hover:underline"
                        to={`/complaints/${escalation.complaint_id}`}
                      >
                        #{escalation.complaint_id}
                      </Link>
                      <span className="chip bg-purple-100 text-purple-700">{escalation.priority}</span>
                    </div>
                    <p className="mt-1 text-sm text-slate-600">{escalation.reason}</p>
                    <p className="mt-0.5 text-xs text-slate-400">
                      {escalation.department} · {timeAgo(escalation.created_at)}
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

          {charts.policy_usage.length > 0 && (
            <Card title="Policy usage (matched rules)">
              <ul className="space-y-2">
                {charts.policy_usage.map((entry) => (
                  <li key={entry.name} className="flex items-center justify-between text-sm">
                    <span className="font-mono text-xs text-slate-600">{entry.name}</span>
                    <span className="chip bg-slate-100 text-slate-600">{entry.value}</span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
