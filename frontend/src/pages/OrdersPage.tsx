import { useCallback, useEffect, useState } from "react";
import { api, errorMessage } from "../lib/api";
import { FullPageSpinner, ErrorBox } from "../components/ui";

type Order = {
  id: number; order_code: string; order_type: string; product_label: string; amount: number;
  payment_status: string; order_status: string; created_at?: string;
};

const typeLabel: Record<string,string> = { SIM: "SIM purchase", PACKAGE: "Package activation", REPLACEMENT: "SIM replacement" };

export default function OrdersPage() {
  const [items,setItems]=useState<Order[]>([]); const [error,setError]=useState(""); const [loading,setLoading]=useState(true);
  const load=useCallback(async()=>{setLoading(true);setError("");try{const d=await api<{items:Order[]}>("/api/telecom/orders");setItems(d.items||[]);}catch(e){setError(errorMessage(e));}finally{setLoading(false);}},[]);
  useEffect(()=>{void load();},[load]);
  if(loading)return <FullPageSpinner/>;
  return <div className="activity-page">
    <header className="customer-page-heading activity-heading">
      <div><p className="customer-kicker">Your activity</p><h1>Activity</h1><p>One place for your SIM purchases, package activations, replacements and payment references.</p></div>
      <button className="customer-button secondary" onClick={load}>↻ Refresh</button>
    </header>
    {error&&<ErrorBox message={error}/>}
    <div className="activity-summary"><div><span>All activity</span><strong>{items.length}</strong></div><div><span>Completed</span><strong>{items.filter(x=>x.order_status === "COMPLETED").length}</strong></div><div><span>Payments recorded</span><strong>{items.filter(x=>x.payment_status === "PAID").length}</strong></div></div>
    <section className="activity-card">
      <div className="activity-card-head"><div><h2>Recent activity</h2><p>References are kept so you can track what happened.</p></div></div>
      {items.length===0 ? <div className="customer-empty compact"><div className="empty-icon">◌</div><h2>No activity yet</h2><p>When you buy a SIM, activate a package or request a replacement, it will appear here.</p></div> : <div className="activity-list">{items.map(o=><article className="activity-row" key={o.id}><div className="activity-icon">{o.order_type === "PACKAGE" ? "▣" : o.order_type === "REPLACEMENT" ? "↻" : "SIM"}</div><div className="activity-main"><div className="activity-title-row"><div><strong>{typeLabel[o.order_type]||o.order_type}</strong><small>{o.product_label}</small></div><span className={`activity-status ${String(o.order_status).toLowerCase()}`}>{o.order_status}</span></div><div className="activity-meta"><span>Reference <b>{o.order_code}</b></span><span>{o.created_at?.slice(0,10)||"—"}</span><span>{o.payment_status === "PAID" ? "Payment recorded" : o.payment_status}</span></div></div><div className="activity-amount">Rs {o.amount.toLocaleString()}</div></article>)}</div>}
    </section>
  </div>;
}
