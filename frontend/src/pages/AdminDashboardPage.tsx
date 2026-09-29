import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Card, EmptyState, ErrorBox, FullPageSpinner, StatusBadge, UrgencyBadge } from "../components/ui";
import { api, errorMessage } from "../lib/api";
import { timeAgo, titleCase } from "../lib/format";
import type { AuditEntry, DashboardData } from "../lib/types";

function humanAction(action: string) {
  return action
    .replace(/[_\.]+/g, " ")
    .replace(/\b\w/g, (m) => m.toUpperCase());
}

export default function AdminDashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [activity, setActivity] = useState<AuditEntry[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError("");
    try {
      const [dash, audit] = await Promise.all([
        api<DashboardData>("/api/dashboard"),
        api<{ total: number; items: AuditEntry[] }>("/api/audit-logs", { query: { limit: 8, offset: 0 } })
          .catch(() => ({ total: 0, items: [] as AuditEntry[] })),
      ]);
      setData(dash);
      setActivity(audit.items || []);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = window.setInterval(() => void load(true), 15000);
    return () => window.clearInterval(timer);
  }, [load]);

  if (loading) return <FullPageSpinner />;
  if (error && !data) return <ErrorBox message={error} onRetry={() => void load()} />;
  if (!data) return <EmptyState title="No dashboard data" />;

  const t = data.totals || ({} as Record<string, number>);
  const kpis = [
    ["Total Complaints", t.total ?? 0, "forest"],
    ["New", t.new ?? 0, "amber"],
    ["Assigned", Math.max(0, (t.open ?? 0) - (t.unassigned ?? 0)), "forest"],
    ["In Progress", t.in_progress ?? 0, "forest"],
    ["Pending", data.charts.status?.find((x) => x.name === "PENDING")?.value ?? 0, "brass"],
    ["Escalated", t.escalated ?? 0, "rose"],
    ["Resolved", t.resolved ?? 0, "emerald"],
    ["SLA At Risk", t.sla_risk ?? 0, "coral"],
  ];
  const workload = data.department_workload || [];
  const maxOpen = Math.max(...workload.map((d) => d.open), 1);

  return (
    <div className="adm-page">
      <header className="adm-page-head">
        <div>
          <h1>Admin Dashboard</h1>
          <p>Live operational view of customer complaints, assignments, SLA risk and system activity.</p>
        </div>
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => void load()}>Refresh</button>
      </header>
      {error && <ErrorBox message={error} />}

      <div className="adm-kpi-grid">
        {kpis.map(([label, value, tone]) => (
          <div key={label as string} className={`adm-kpi adm-kpi-${tone}`}>
            <span className="adm-kpi-label">{label}</span>
            <span className="adm-kpi-value">{value}</span>
          </div>
        ))}
      </div>

      <div className="adm-grid-2 adm-dashboard-main">
        <Card title="Latest Customer Complaints" actions={<Link to="/complaints" className="text-xs text-[var(--nova-forest)]">View all →</Link>}>
          {data.recent_complaints?.length ? (
            <div className="adm-table-wrap">
              <table className="adm-table">
                <thead><tr><th>Complaint</th><th>Customer</th><th>Status</th><th>Priority</th><th>Created</th></tr></thead>
                <tbody>
                  {data.recent_complaints.slice(0, 8).map((c) => (
                    <tr key={c.id} className="adm-click-row">
                      <td><Link to={`/complaints/${c.id}`} className="font-semibold text-[var(--nova-forest)]">{c.code}</Link><div className="text-xs text-slate-500 truncate max-w-[210px]">{c.title}</div></td>
                      <td><div>{c.customer_name || "Customer"}</div><div className="text-xs text-slate-400">{c.customer_email || "—"}</div></td>
                      <td><StatusBadge status={c.status} /></td>
                      <td><UrgencyBadge urgency={c.verified_urgency || c.urgency} /></td>
                      <td className="text-xs text-slate-500">{timeAgo(c.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : <EmptyState title="No customer complaints yet" hint="New customer submissions will appear here automatically." />}
        </Card>

        <Card title="Operational Status" actions={<Link to="/reports" className="text-xs text-[var(--nova-forest)]">Reports →</Link>}>
          <div className="adm-status-list">
            {(data.charts.status || []).slice(0, 8).map((item) => (
              <div className="adm-status-row" key={item.name}>
                <span>{titleCase(item.name)}</span><strong>{item.value}</strong>
              </div>
            ))}
          </div>
          <div className="adm-dashboard-note"><strong>{t.unassigned ?? 0}</strong> open complaints still need an agent assignment.</div>
          <div className="adm-dashboard-note"><strong>{t.manual_review ?? 0}</strong> complaints are waiting for human review.</div>
        </Card>
      </div>

      <div className="adm-grid-2" style={{ marginTop: 16 }}>
        <Card title="Department Workload" actions={<Link to="/admin/departments" className="text-xs text-[var(--nova-forest)]">Manage →</Link>}>
          {workload.length ? <div className="adm-workload-list">{workload.map((d) => (
            <div className="adm-workload-row" key={d.name}>
              <div className="adm-workload-head"><strong>{d.name}</strong><span>{d.open} open · {d.sla_risk} SLA risk</span></div>
              <div className="adm-bar-track"><div className="adm-bar-fill" style={{ width: `${(d.open / maxOpen) * 100}%` }} /></div>
              <div className="adm-workload-meta"><span>{d.assigned} assigned</span><span>{d.unassigned} unassigned</span><span>{d.escalated} escalated</span></div>
            </div>
          ))}</div> : <EmptyState title="No department data" />}
        </Card>

        <Card title="Recent Activity" actions={<Link to="/admin/audit" className="text-xs text-[var(--nova-forest)]">All logs →</Link>}>
          {activity.length ? <ul className="adm-activity-list">{activity.map((a) => (
            <li key={a.id}><span className="adm-act-dot" /><div><strong>{humanAction(a.action || "System event")}</strong><small>{a.entity_type}{a.entity_id ? ` #${a.entity_id}` : ""} · {a.actor_email || "system"} · {a.created_at ? timeAgo(a.created_at) : "—"}</small></div></li>
          ))}</ul> : <EmptyState title="No recent activity" hint="Customer and staff actions will appear here." />}
        </Card>
      </div>

      <div className="adm-quick-links">
        <Link to="/complaints" className="adm-qlink">Manage Complaints →</Link>
        <Link to="/review" className="adm-qlink">AI Review Queue →</Link>
        <Link to="/reports" className="adm-qlink">Reports & Analytics →</Link>
        <Link to="/security" className="adm-qlink">Security Events →</Link>
      </div>
    </div>
  );
}
