import { FormEvent, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, errorMessage } from "../lib/api";
import { timeAgo } from "../lib/format";
import type { ComplaintBrief, Paginated } from "../lib/types";

const statusText: Record<string, string> = {
  NEW: "Received",
  ANALYZING: "AI checking",
  ANALYZED: "Under review",
  VALIDATION_FAILED: "Needs review",
  MANUAL_REVIEW: "Human review",
  ESCALATED: "Escalated",
  IN_PROGRESS: "Action in progress",
  RESOLVED: "Resolved",
  CLOSED: "Closed",
};

function progress(status: string) {
  if (status === "RESOLVED" || status === "CLOSED") return 4;
  if (["IN_PROGRESS", "ESCALATED", "MANUAL_REVIEW", "VALIDATION_FAILED"].includes(status)) return 3;
  if (["ANALYZED"].includes(status)) return 2;
  if (["ANALYZING"].includes(status)) return 2;
  return 1;
}

export default function TrackComplaintPage() {
  const navigate = useNavigate();
  const [code, setCode] = useState("");
  const [complaint, setComplaint] = useState<ComplaintBrief | null>(null);
  const [recent, setRecent] = useState<ComplaintBrief[]>([]);
  const [loading, setLoading] = useState(true);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    (async () => {
      try {
        const data = await api<Paginated<ComplaintBrief>>("/api/complaints", { query: { page: 1, page_size: 8 } });
        setRecent(data.items);
      } catch (e) {
        setError(errorMessage(e));
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  async function track(event: FormEvent) {
    event.preventDefault();
    const value = code.trim();
    if (!value) return;
    setSearching(true);
    setError("");
    setComplaint(null);
    try {
      const data = await api<Paginated<ComplaintBrief>>("/api/complaints", { query: { q: value, page: 1, page_size: 10 } });
      const exact = data.items.find(item => item.code.toLowerCase() === value.toLowerCase()) || data.items[0];
      if (!exact) setError("No complaint was found with that complaint code.");
      else setComplaint(exact);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSearching(false);
    }
  }

  const renderCard = (item: ComplaintBrief) => {
    const step = progress(item.status);
    return (
      <button key={item.id} className="track-complaint-card" onClick={() => navigate(`/complaints/${item.id}`)}>
        <div className="track-card-head">
          <span className="complaint-code">{item.code}</span>
          <span className={`customer-status status-${item.status.toLowerCase()}`}>{statusText[item.status] || item.status}</span>
        </div>
        <h2>{item.title}</h2>
        <p>{timeAgo(item.created_at)} · {item.issue_category || "Support request"}</p>
        <div className="track-progress" aria-label={`Complaint progress: step ${step} of 4`}>
          {[1, 2, 3, 4].map(n => <span key={n} className={n < step ? "done" : n === step ? "active" : ""} />)}
        </div>
        <div className="track-step-labels"><span>Received</span><span>Checked</span><span>Action</span><span>Resolved</span></div>
        <span className="view-link">Open live tracking →</span>
      </button>
    );
  };

  return (
    <div className="track-page">
      <div className="customer-page-heading">
        <div>
          <p className="customer-kicker">Live support</p>
          <h1>Track a complaint</h1>
          <p>Enter your complaint code to see its current status and what happens next.</p>
        </div>
        <div className="page-heading-actions">
          <button className="customer-button secondary" onClick={() => navigate("/complaints")}>← My complaints</button>
          <button className="customer-button primary" onClick={() => navigate("/?new=1")}>＋ New complaint</button>
        </div>
      </div>

      <section className="track-search-card">
        <div className="track-search-icon">✓</div>
        <div className="track-search-copy"><strong>Have your complaint code?</strong><span>Example: CMP-05000</span></div>
        <form onSubmit={track} className="track-search-form">
          <input value={code} onChange={e => setCode(e.target.value)} placeholder="Enter complaint code" aria-label="Complaint code" />
          <button className="customer-button primary" disabled={searching || !code.trim()}>{searching ? "Checking…" : "Track complaint"}</button>
        </form>
      </section>

      {error && <div className="customer-error">{error}</div>}
      {complaint && <section className="track-result"><div className="section-head"><div><strong>Live status</strong><small>{complaint.code}</small></div><button className="customer-link-button" onClick={() => navigate(`/complaints/${complaint.id}`)}>Full details →</button></div>{renderCard(complaint)}</section>}

      <section className="track-recent">
        <div className="section-head"><div><strong>Your recent complaints</strong><small>Only your own complaints are shown.</small></div></div>
        {loading ? <div className="customer-loading">Loading your complaints…</div> : recent.length === 0 ? <div className="customer-empty compact"><h2>No complaints yet</h2><p>Start with Nova whenever you need help.</p><button className="customer-button primary" onClick={() => navigate("/?new=1")}>Ask Nova</button></div> : <div className="track-list">{recent.map(renderCard)}</div>}
      </section>
    </div>
  );
}
