import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { isStaffRole, useAuth } from "../lib/auth";

function LinkChip({
  to,
  label,
  active,
  urgent,
}: {
  to: string;
  label: string;
  active?: boolean;
  urgent?: boolean;
}) {
  return (
    <Link
      to={to}
      className={`filter-chip ${urgent ? "urgent-chip" : ""} ${active ? "is-active" : ""}`}
    >
      {label}
    </Link>
  );
}
import {
  Card,
  EmptyState,
  ErrorBox,
  FullPageSpinner,
  Modal,
  Pagination,
  StatusBadge,
  UrgencyBadge,
  VerificationBadge,
} from "../components/ui";
import { api, errorMessage } from "../lib/api";
import { timeAgo } from "../lib/format";
import type { CategoryRow, ComplaintBrief, ComplaintFull, DepartmentRow, Paginated } from "../lib/types";

const STATUS_OPTIONS = [
  "NEW",
  "ANALYZING",
  "ANALYZED",
  "VALIDATION_FAILED",
  "MANUAL_REVIEW",
  "ASSIGNED",
  "IN_PROGRESS",
  "PENDING",
  "ESCALATED",
  "RESOLVED",
  "REJECTED",
  "CLOSED",
];

const URGENCY_OPTIONS = ["Low", "Medium", "High", "Critical"];
const CHANNEL_OPTIONS = ["web", "email", "phone", "chat"];
const CUSTOMER_TYPE_OPTIONS = ["retail", "business", "enterprise"];
const FLAG_OPTIONS = [
  { value: "", label: "Any flag" },
  { value: "injection", label: "Injection detected" },
  { value: "duplicate", label: "Duplicate" },
  { value: "incomplete", label: "Incomplete" },
  { value: "multi_issue", label: "Multi issue" },
];

const PAGE_SIZE = 20;

interface CreateForm {
  title: string;
  description: string;
  customer_type: string;
  product_or_service: string;
  order_reference: string;
  channel: string;
  requested_resolution: string;
  previous_complaints: number;
}

const EMPTY_FORM: CreateForm = {
  title: "",
  description: "",
  customer_type: "retail",
  product_or_service: "",
  order_reference: "",
  channel: "web",
  requested_resolution: "",
  previous_complaints: 0,
};

function StaffComplaintsPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [items, setItems] = useState<ComplaintBrief[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [q, setQ] = useState("");
  const [appliedQ, setAppliedQ] = useState("");
  const [status, setStatus] = useState(searchParams.get("status") || "");
  const [urgency, setUrgency] = useState(
    searchParams.get("filter") === "urgent" ? "Critical" : searchParams.get("urgency") || ""
  );
  const [category, setCategory] = useState("");
  const [department, setDepartment] = useState("");
  const [flag, setFlag] = useState("");
  const filterMode = searchParams.get("filter") || "";

  const [categories, setCategories] = useState<CategoryRow[]>([]);
  const [departments, setDepartments] = useState<DepartmentRow[]>([]);

  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState<CreateForm>(EMPTY_FORM);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");

  useEffect(() => {
    const s = searchParams.get("status") || "";
    const f = searchParams.get("filter") || "";
    const u = searchParams.get("urgency") || "";
    if (f === "urgent") {
      setUrgency("Critical");
      setStatus("");
    } else {
      if (s) setStatus(s);
      if (u) setUrgency(u);
    }
    const qq = searchParams.get("q");
    if (qq) {
      setQ(qq);
      setAppliedQ(qq);
    }
  }, [searchParams]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const query: Record<string, string | number | undefined> = {
        q: appliedQ || undefined,
        status: status || undefined,
        urgency: urgency || undefined,
        category: category || undefined,
        department: department || undefined,
        flag: flag || undefined,
        page,
        page_size: PAGE_SIZE,
      };
      if (filterMode === "urgent") {
        query.urgency = "Critical";
      }
      const data = await api<Paginated<ComplaintBrief>>("/api/complaints", { query });
      setItems(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [appliedQ, status, urgency, category, department, flag, page, filterMode]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    api<CategoryRow[]>("/api/categories")
      .then(setCategories)
      .catch(() => setCategories([]));
    api<DepartmentRow[]>("/api/departments")
      .then(setDepartments)
      .catch(() => setDepartments([]));
  }, []);

  function applyFilters(event: FormEvent) {
    event.preventDefault();
    setPage(1);
    setAppliedQ(q.trim());
  }

  function resetFilters() {
    setQ("");
    setAppliedQ("");
    setStatus("");
    setUrgency("");
    setCategory("");
    setDepartment("");
    setFlag("");
    setPage(1);
  }

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    setCreating(true);
    setCreateError("");
    try {
      const created = await api<ComplaintFull>("/api/complaints", { method: "POST", body: form });
      setShowCreate(false);
      setForm(EMPTY_FORM);
      navigate(`/complaints/${created.id}`);
    } catch (err) {
      setCreateError(errorMessage(err));
    } finally {
      setCreating(false);
    }
  }

  function flagChips(complaint: ComplaintBrief) {
    const chips: { label: string; className: string }[] = [];
    if (complaint.injection_detected) chips.push({ label: "injection", className: "bg-rose-100 text-rose-700" });
    if (complaint.duplicate_of_id) chips.push({ label: "duplicate", className: "bg-amber-100 text-amber-700" });
    if (complaint.incomplete) chips.push({ label: "incomplete", className: "bg-sky-100 text-sky-700" });
    if (complaint.flags.includes("multi_issue"))
      chips.push({ label: "multi issue", className: "bg-purple-100 text-purple-700" });
    if (complaint.is_dataset_case) chips.push({ label: "dataset", className: "bg-slate-100 text-slate-500" });
    return chips;
  }

  return (
    <div className="adm-page space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">Complaints</h1>
          <p className="text-sm text-slate-500">
            Prioritize urgent cases first · assign · resolve with clear notes.
          </p>
        </div>
        <button type="button" className="btn btn-primary" onClick={() => setShowCreate(true)}>
          New complaint
        </button>
      </div>

      <div className="filter-chips">
        <LinkChip to="/complaints" active={!filterMode && !status && !urgency} label="All" />
        <LinkChip to="/complaints?filter=urgent" active={filterMode === "urgent"} label="⚠ Urgent" urgent />
        <LinkChip to="/complaints?status=NEW" active={status === "NEW"} label="New" />
        <LinkChip to="/complaints?status=ASSIGNED" active={status === "ASSIGNED"} label="Assigned" />
        <LinkChip to="/complaints?status=IN_PROGRESS" active={status === "IN_PROGRESS"} label="In Progress" />
        <LinkChip to="/complaints?status=PENDING" active={status === "PENDING"} label="Pending" />
        <LinkChip to="/complaints?status=ESCALATED" active={status === "ESCALATED"} label="Escalated" />
        <LinkChip to="/complaints?status=RESOLVED" active={status === "RESOLVED"} label="Resolved" />
        <LinkChip to="/complaints?status=REJECTED" active={status === "REJECTED"} label="Rejected" />
      </div>

      <Card>
        <form className="grid gap-3 md:grid-cols-3 xl:grid-cols-6" onSubmit={applyFilters}>
          <div className="xl:col-span-2">
            <label className="label">Search</label>
            <input
              className="input mt-1"
              placeholder="Code, title or description…"
              value={q}
              onChange={(event) => setQ(event.target.value)}
            />
          </div>
          <div>
            <label className="label">Status</label>
            <select className="input mt-1" value={status} onChange={(event) => { setStatus(event.target.value); setPage(1); }}>
              <option value="">All statuses</option>
              {STATUS_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Urgency</label>
            <select className="input mt-1" value={urgency} onChange={(event) => { setUrgency(event.target.value); setPage(1); }}>
              <option value="">All urgencies</option>
              {URGENCY_OPTIONS.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Category</label>
            <select className="input mt-1" value={category} onChange={(event) => { setCategory(event.target.value); setPage(1); }}>
              <option value="">All categories</option>
              {categories.map((option) => (
                <option key={option.id} value={option.name}>
                  {option.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Department</label>
            <select className="input mt-1" value={department} onChange={(event) => { setDepartment(event.target.value); setPage(1); }}>
              <option value="">All departments</option>
              {departments.map((option) => (
                <option key={option.id} value={option.name}>
                  {option.name}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Flag</label>
            <select className="input mt-1" value={flag} onChange={(event) => { setFlag(event.target.value); setPage(1); }}>
              {FLAG_OPTIONS.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-end gap-2 md:col-span-3 xl:col-span-6">
            <button type="submit" className="btn btn-primary btn-sm">
              Apply
            </button>
            <button type="button" className="btn btn-secondary btn-sm" onClick={resetFilters}>
              Reset
            </button>
          </div>
        </form>
      </Card>

      {error && <ErrorBox message={error} onRetry={() => void load()} />}

      <Card>
        {loading ? (
          <FullPageSpinner />
        ) : items.length === 0 ? (
          <EmptyState title="No complaints match your filters" hint="Try resetting the filters or submit a new complaint." />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className="table-th">Code</th>
                    <th className="table-th">Customer</th>
                    <th className="table-th">Title</th>
                    <th className="table-th">Status</th>
                    <th className="table-th">Urgency</th>
                    <th className="table-th">Category</th>
                    <th className="table-th">Department</th>
                    <th className="table-th">Agent</th>
                    <th className="table-th">Verification</th>
                    <th className="table-th">Flags</th>
                    <th className="table-th">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((complaint) => (
                    <tr
                      key={complaint.id}
                      className="cursor-pointer border-b border-slate-50 hover:bg-slate-50"
                      onClick={() => navigate(`/complaints/${complaint.id}`)}
                    >
                      <td className="table-td font-mono text-xs text-brand-600">{complaint.code}</td>
                      <td className="table-td"><div className="text-sm">{complaint.customer_name || "Customer"}</div><div className="text-xs text-slate-400">{complaint.customer_email || "—"}</div></td>
                      <td className="table-td max-w-[280px] truncate">{complaint.title}</td>
                      <td className="table-td">
                        <StatusBadge status={complaint.status} />
                      </td>
                      <td className="table-td">
                        <UrgencyBadge urgency={complaint.verified_urgency || complaint.urgency} />
                      </td>
                      <td className="table-td">{complaint.verified_category || complaint.issue_category || "Uncategorized"}</td>
                      <td className="table-td">{complaint.verified_department || complaint.department || "Unassigned"}</td>
                      <td className="table-td text-xs">{complaint.assigned_agent_name || "Unassigned"}</td>
                      <td className="table-td">
                        <VerificationBadge status={complaint.verification_status} />
                      </td>
                      <td className="table-td">
                        <div className="flex flex-wrap gap-1">
                          {flagChips(complaint).map((chip) => (
                            <span key={chip.label} className={`chip ${chip.className}`}>
                              {chip.label}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="table-td whitespace-nowrap text-xs text-slate-500">{timeAgo(complaint.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={page} pageSize={PAGE_SIZE} total={total} onPage={setPage} />
          </>
        )}
      </Card>

      <Modal open={showCreate} title="Submit a new complaint" onClose={() => setShowCreate(false)}>
        <form className="space-y-4" onSubmit={handleCreate}>
          <div>
            <label className="label">Title *</label>
            <input
              className="input mt-1"
              required
              minLength={3}
              maxLength={250}
              value={form.title}
              onChange={(event) => setForm({ ...form, title: event.target.value })}
              placeholder="Short summary of the issue"
            />
          </div>
          <div>
            <label className="label">Description *</label>
            <textarea
              className="input mt-1"
              required
              minLength={5}
              rows={4}
              value={form.description}
              onChange={(event) => setForm({ ...form, description: event.target.value })}
              placeholder="Describe what happened, including any order references or dates…"
            />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className="label">Customer type</label>
              <select
                className="input mt-1"
                value={form.customer_type}
                onChange={(event) => setForm({ ...form, customer_type: event.target.value })}
              >
                {CUSTOMER_TYPE_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Channel</label>
              <select
                className="input mt-1"
                value={form.channel}
                onChange={(event) => setForm({ ...form, channel: event.target.value })}
              >
                {CHANNEL_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Product or service</label>
              <input
                className="input mt-1"
                value={form.product_or_service}
                onChange={(event) => setForm({ ...form, product_or_service: event.target.value })}
                placeholder="e.g. Express delivery"
              />
            </div>
            <div>
              <label className="label">Order reference</label>
              <input
                className="input mt-1"
                value={form.order_reference}
                onChange={(event) => setForm({ ...form, order_reference: event.target.value })}
                placeholder="e.g. ORD-12345"
              />
            </div>
          </div>
          <div>
            <label className="label">Requested resolution</label>
            <input
              className="input mt-1"
              value={form.requested_resolution}
              onChange={(event) => setForm({ ...form, requested_resolution: event.target.value })}
              placeholder="What outcome does the customer want?"
            />
          </div>
          <div>
            <label className="label">Previous complaints</label>
            <input
              type="number"
              min={0}
              className="input mt-1 w-32"
              value={form.previous_complaints}
              onChange={(event) => setForm({ ...form, previous_complaints: Number(event.target.value) || 0 })}
            />
          </div>

          {createError && <ErrorBox message={createError} />}

          <div className="flex justify-end gap-2">
            <button type="button" className="btn btn-secondary" onClick={() => setShowCreate(false)}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={creating}>
              {creating ? "Submitting…" : "Submit complaint"}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}


function CustomerComplaintsPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [search, setSearch] = useState(searchParams.get("q") || "");
  const appliedSearch = searchParams.get("q") || "";
  const [items, setItems] = useState<ComplaintBrief[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState<CreateForm>(EMPTY_FORM);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await api<Paginated<ComplaintBrief>>("/api/complaints", { query: { q: appliedSearch || undefined, page: 1, page_size: 100 } });
      setItems(data.items);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [appliedSearch]);

  useEffect(() => { void load(); }, [load]);

  async function handleCreate(event: FormEvent) {
    event.preventDefault();
    setCreating(true);
    setCreateError("");
    try {
      const created = await api<ComplaintFull>("/api/complaints", { method: "POST", body: form });
      setShowCreate(false);
      setForm(EMPTY_FORM);
      navigate(`/complaints/${created.id}`);
    } catch (err) {
      setCreateError(errorMessage(err));
    } finally {
      setCreating(false);
    }
  }

  const statusText = (status: string) => {
    const labels: Record<string, string> = {
      NEW: "Submitted", ANALYZING: "Checking", ANALYZED: "Under review", IN_PROGRESS: "In progress",
      ESCALATED: "Escalated to support", MANUAL_REVIEW: "Human review", RESOLVED: "Resolved", CLOSED: "Closed",
      VALIDATION_FAILED: "Needs review",
    };
    return labels[status] || status.replace(/_/g, " ");
  };

  return (
    <div className="customer-complaints-page">
      <div className="customer-page-heading">
        <div>
          <p className="customer-kicker">Your support</p>
          <h1>My complaints</h1>
          <p>Everything you submitted is shown here. Open a complaint to see the latest update.</p>
        </div>
        <div className="heading-actions">
          <button className="customer-button secondary" onClick={() => navigate("/")}>← Ask Nova</button>
          <button className="customer-button secondary" onClick={() => navigate("/track")}>Track complaint</button>
          <button className="customer-button primary" onClick={() => navigate("/?new=1")}>＋ New complaint</button>
        </div>
      </div>

      <div className="customer-complaint-toolbar">
        <form onSubmit={(e) => { e.preventDefault(); const value = search.trim(); if (value) setSearchParams({ q: value }); else setSearchParams({}); }} className="customer-inline-search">
          <span>⌕</span><input value={search} onChange={e => setSearch(e.target.value)} placeholder="Search complaint title, code or issue…" /><button type="submit">Search</button>
        </form>
        {appliedSearch && <button className="customer-clear-search" onClick={() => { setSearch(""); setSearchParams({}); }}>Clear search</button>}
      </div>

      {error && <div className="customer-error">{error} <button onClick={() => void load()}>Try again</button></div>}
      {loading ? <div className="customer-loading">Loading your complaints…</div> : items.length === 0 ? (
        <div className="customer-empty"><div className="empty-icon">📋</div><h2>No complaints yet</h2><p>If you need help, start with Nova or submit a complaint directly.</p><div className="empty-actions"><button className="customer-button primary" onClick={() => navigate("/")}>Ask Nova</button><button className="customer-button secondary" onClick={() => navigate("/?new=1")}>Submit complaint</button></div></div>
      ) : (
        <div className="customer-complaint-list">
          {items.map(item => (
            <button key={item.id} className="customer-complaint-card" onClick={() => navigate(`/complaints/${item.id}`)}>
              <div className="complaint-card-top"><span className="complaint-code">{item.code}</span><span className={`customer-status status-${item.status.toLowerCase()}`}>{statusText(item.status)}</span></div>
              <div className="complaint-card-title-row"><h2>{item.title}</h2><span className={`priority-pill ${String(item.priority || item.urgency || "").toLowerCase()}`}>{item.priority || item.urgency || "Standard"}</span></div>
              <p>{timeAgo(item.created_at)} · {item.issue_category || "Support request"}</p>
              <div className="complaint-mini-track"><span className="done"/><span className={item.status === "NEW" ? "active" : "done"}/><span className={item.status === "IN_PROGRESS" || item.status === "ESCALATED" ? "active" : item.status === "RESOLVED" || item.status === "CLOSED" ? "done" : ""}/><span className={item.status === "RESOLVED" || item.status === "CLOSED" ? "done" : ""}/></div>
              <span className="complaint-card-actions"><span className="view-link">View live status →</span><span className="track-link">Track ↗</span></span>
            </button>
          ))}
        </div>
      )}

      <Modal open={showCreate} title="Tell us what happened" onClose={() => setShowCreate(false)}>
        <form className="space-y-4" onSubmit={handleCreate}>
          <div><label className="label">What is the problem? *</label><input className="input mt-1" required minLength={3} value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} placeholder="e.g. Recharge balance is not showing" /></div>
          <div><label className="label">Tell us a little more *</label><textarea className="input mt-1" required minLength={5} rows={5} value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} placeholder="What happened, when did it happen, and what do you need help with?" /></div>
          <div className="grid gap-4 md:grid-cols-2">
            <div><label className="label">Service / SIM / package</label><input className="input mt-1" value={form.product_or_service} onChange={e => setForm({ ...form, product_or_service: e.target.value })} placeholder="Optional" /></div>
            <div><label className="label">Reference / transaction ID</label><input className="input mt-1" value={form.order_reference} onChange={e => setForm({ ...form, order_reference: e.target.value })} placeholder="Optional" /></div>
          </div>
          <div><label className="label">What would you like us to do?</label><input className="input mt-1" value={form.requested_resolution} onChange={e => setForm({ ...form, requested_resolution: e.target.value })} placeholder="e.g. Check my recharge and update me" /></div>
          <p className="customer-safe-note">Please do not include OTPs, passwords, PINs or full card/bank details.</p>
          {createError && <ErrorBox message={createError} />}
          <div className="flex justify-end gap-2"><button type="button" className="btn btn-secondary" onClick={() => setShowCreate(false)}>Cancel</button><button type="submit" className="btn btn-primary" disabled={creating}>{creating ? "Submitting…" : "Submit complaint"}</button></div>
        </form>
      </Modal>
    </div>
  );
}

export default function ComplaintsPage() {
  const { user } = useAuth();
  return isStaffRole(user?.role) ? <StaffComplaintsPage /> : <CustomerComplaintsPage />;
}
