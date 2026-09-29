import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Card, EmptyState, ErrorBox, FullPageSpinner, Modal } from "../components/ui";
import { api, errorMessage } from "../lib/api";
import type { AuthUser } from "../lib/types";

type UserRow = AuthUser & { created_at?: string | null; department?: string | null };

interface AgentForm {
  email: string;
  full_name: string;
  password: string;
  role: "agent";
}

const EMPTY: AgentForm = { email: "", full_name: "", password: "", role: "agent" };

export default function AdminAgentsPage() {
  const [agents, setAgents] = useState<UserRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState<AgentForm>(EMPTY);
  const [formError, setFormError] = useState("");
  const [creating, setCreating] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const all = await api<UserRow[]>("/api/users");
      setAgents(all.filter((u) => u.role === "agent" || u.role === "admin"));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = agents.filter((u) => {
    if (!q.trim()) return true;
    const s = q.toLowerCase();
    return u.full_name?.toLowerCase().includes(s) || u.email?.toLowerCase().includes(s);
  });

  async function toggleActive(user: UserRow) {
    if (!confirm(`${user.is_active ? "Suspend" : "Activate"} ${user.full_name}?`)) return;
    setBusyId(user.id);
    try {
      await api(`/api/users/${user.id}`, { method: "PUT", body: { is_active: !user.is_active } });
      await load();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusyId(null);
    }
  }

  async function handleCreate(e: FormEvent) {
    e.preventDefault();
    setCreating(true);
    setFormError("");
    try {
      await api("/api/users", { method: "POST", body: form });
      setShowCreate(false);
      setForm(EMPTY);
      await load();
    } catch (err) {
      setFormError(errorMessage(err));
    } finally {
      setCreating(false);
    }
  }

  if (loading) return <FullPageSpinner />;

  return (
    <div className="adm-page">
      <header className="adm-page-head">
        <div>
          <h1>Agents</h1>
          <p>Manage support agents and their availability.</p>
        </div>
        <button type="button" className="btn btn-primary btn-sm" onClick={() => setShowCreate(true)}>
          + Add agent
        </button>
      </header>

      {error && <ErrorBox message={error} onRetry={load} />}

      <div className="adm-filters">
        <input
          className="input"
          style={{ maxWidth: 320 }}
          placeholder="Search agent…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
        <span className="adm-filter-meta">{filtered.length} agents</span>
      </div>

      <Card>
        {filtered.length === 0 ? (
          <EmptyState title="No agents found" />
        ) : (
          <div className="adm-table-wrap">
            <table className="adm-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Role</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((u) => (
                  <tr key={u.id}>
                    <td className="mono">#{u.id}</td>
                    <td>
                      <strong>{u.full_name}</strong>
                    </td>
                    <td>{u.email}</td>
                    <td>
                      <span className="adm-badge info">{u.role}</span>
                    </td>
                    <td>
                      <span className={`adm-badge ${u.is_active ? "ok" : "muted"}`}>
                        {u.is_active ? "Available" : "Suspended"}
                      </span>
                    </td>
                    <td>
                      {u.role !== "admin" && (
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          disabled={busyId === u.id}
                          onClick={() => toggleActive(u)}
                        >
                          {u.is_active ? "Suspend" : "Activate"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {showCreate && (
        <Modal open title="Add agent" onClose={() => setShowCreate(false)}>
          <form className="space-y-3" onSubmit={handleCreate}>
            <div>
              <label className="label">Full name</label>
              <input
                className="input mt-1"
                required
                value={form.full_name}
                onChange={(e) => setForm({ ...form, full_name: e.target.value })}
              />
            </div>
            <div>
              <label className="label">Email</label>
              <input
                className="input mt-1"
                type="email"
                required
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
              />
            </div>
            <div>
              <label className="label">Password</label>
              <input
                className="input mt-1"
                type="password"
                required
                minLength={8}
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
              />
            </div>
            {formError && <p className="text-sm text-rose-600">{formError}</p>}
            <div className="flex justify-end gap-2 pt-2">
              <button type="button" className="btn btn-secondary" onClick={() => setShowCreate(false)}>
                Cancel
              </button>
              <button type="submit" className="btn btn-primary" disabled={creating}>
                {creating ? "Creating…" : "Create"}
              </button>
            </div>
          </form>
        </Modal>
      )}
    </div>
  );
}
