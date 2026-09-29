import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Card, ErrorBox, FullPageSpinner, StatCard, StatusBadge, UrgencyBadge } from "../components/ui";
import { api, errorMessage } from "../lib/api";
import { formatDateTime, timeAgo } from "../lib/format";
import type { AgentDashboardData, ComplaintBrief } from "../lib/types";

function CaseRow({ c }: { c: ComplaintBrief }) {
  return <Link to={`/agent/cases/${c.id}`} className="agent-case-row">
    <div className="agent-case-main"><div className="agent-case-title"><strong>{c.title}</strong><span>{c.code}</span></div><div className="agent-case-meta"><span>{c.customer_name || "Customer"} · #{c.id}</span><span>{c.issue_category || c.verified_category || "Support"}</span><span>{timeAgo(c.updated_at || c.created_at)}</span></div></div>
    <div className="agent-case-status"><UrgencyBadge urgency={c.verified_urgency || c.urgency} /><StatusBadge status={c.status} /></div>
  </Link>;
}

export default function AgentDashboardPage() {
  const [data,setData]=useState<AgentDashboardData|null>(null); const [loading,setLoading]=useState(true); const [error,setError]=useState("");
  const load=useCallback(async()=>{try{setError("");setData(await api<AgentDashboardData>("/api/agent/dashboard"));}catch(e){setError(errorMessage(e));}finally{setLoading(false);}},[]);
  useEffect(()=>{void load(); const id=window.setInterval(()=>void load(),15000); return()=>window.clearInterval(id);},[load]);
  if(loading&&!data)return <FullPageSpinner/>; if(error&&!data)return <ErrorBox message={error} onRetry={()=>void load()}/>; if(!data)return null;
  return <div className="adm-page agent-workspace">
    <div className="agent-page-hero"><div><p className="agent-kicker">Agent workspace</p><h1>Focus on the customers who need you.</h1><p>Only your assigned support cases are shown here. Urgent cases rise to the top, and every reply stays inside the same complaint conversation.</p></div><div className="agent-live"><span/> Live queue · refreshes every 15s</div></div>
    <div className="agent-kpi-grid">
      <StatCard label="Pending (AI could not solve)" value={data.kpis.pending ?? data.kpis.new_assigned} tone="brand" hint="Needs your action"/>
      <StatCard label="In progress" value={data.kpis.in_progress} tone="emerald" hint="You are working on these"/>
      <StatCard label="Waiting for customer" value={data.kpis.waiting_customer} tone="amber" hint="Customer needs to reply"/>
      <StatCard label="Urgent" value={data.kpis.urgent} tone="rose" hint="High / critical"/>
      <StatCard label="SLA at risk" value={data.kpis.sla_at_risk} tone="amber" hint="Past or due now"/>
      <StatCard label="Resolved today" value={data.kpis.resolved_today} tone="purple" hint="Your completed cases"/>
    </div>
    <div className="grid gap-5 lg:grid-cols-[1.45fr_.9fr]">
      <Card title="My active queue" actions={<Link to="/agent/complaints" className="agent-link">View all →</Link>}>
        {data.recent.length ? <div className="agent-case-list">{data.recent.map(c=><CaseRow key={c.id} c={c}/>)}</div> : <div className="agent-empty"><div>✓</div><strong>Your queue is clear</strong><span>No assigned customer cases need attention right now.</span></div>}
      </Card>
      <Card title="Urgent attention" actions={<Link to="/agent/complaints?filter=urgent" className="agent-link">Open queue →</Link>}>
        {data.urgent_queue.length ? <div className="agent-urgent-list">{data.urgent_queue.map(c=><Link key={c.id} to={`/agent/cases/${c.id}`} className="agent-urgent-card"><div><strong>{c.customer_name || "Customer"}</strong><small>{c.code} · {c.customer_email || "Customer ID #"+c.customer_id}</small></div><div><UrgencyBadge urgency={c.verified_urgency || c.urgency}/><small>{c.sla_due_at ? formatDateTime(c.sla_due_at) : "SLA pending"}</small></div></Link>)}</div> : <div className="agent-empty compact"><div>✓</div><strong>No urgent cases</strong><span>You're caught up.</span></div>}
      </Card>
    </div>
  </div>;
}
