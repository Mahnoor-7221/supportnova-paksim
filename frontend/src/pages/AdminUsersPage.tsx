import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Card, EmptyState, ErrorBox, FullPageSpinner, Modal, Pagination } from "../components/ui";
import { api, errorMessage } from "../lib/api";
import { formatDateTime } from "../lib/format";
import type { AuthUser } from "../lib/types";

type UserRow = AuthUser & { created_at?: string | null };

interface UserForm {
  email: string;
  full_name: string;
  password: string;
  role: "customer";
}

const EMPTY: UserForm = { email: "", full_name: "", password: "", role: "customer" };

export default function AdminUsersPage() {
  const [users, setUsers] = useState<UserRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [q, setQ] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState<UserForm>(EMPTY);
  const [formError, setFormError] = useState("");
  const [creating, setCreating] = useState(false);
  const [page, setPage] = useState(1);
  const PAGE = 15;

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const all = await api<UserRow[]>("/api/users");
      setUsers(all.filter((u) => u.role === "customer"));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const filtered = users.filter((u) => {
    if (!q.trim()) return true;
    const s = q.toLowerCase();
    return (
      u.full_name?.toLowerCase().includes(s) ||
      u.email?.toLowerCase().includes(s) ||
      String(u.id).includes(s)
    );
  });
  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE));
  const slice = filtered.slice((page - 1) * PAGE, page * PAGE);

  async function toggleActive(user: UserRow) {
    if (!confirm(`${user.is_active ? "Deactivate" : "Activate"} ${user.full_name}?`)) return;
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
          <h1>Users</h1>
          <p>Manage customer accounts. Agents are managed under Agents.</p>
        </div>
        <button type="button" className="btn btn-primary btn-sm" onClick={() => setShowCreate(true)}>
          + Add customer
        </button>
      </header>

      {error && <ErrorBox message={error} onRetry={load} />}

      <div className="adm-filters">
        <input
          className="input"
          style={{ maxWidth: 320 }}
          placeholder="Search name, email, ID…"
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setPage(1);
          }}
        />
        <span className="adm-filter-meta">{filtered.length} customers</span>
      </div>

      <Card>
        {slice.length === 0 ? (
          <EmptyState title="No customers found" />
        ) : (
          <div className="adm-table-wrap">
            <table className="adm-table">
              <thead>
                <tr>
                  <th>ID</th>
                  <th>Name</th>
                  <th>Email</th>
                  <th>Status</th>
                  <th>Registered</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {slice.map((u) => (
                  <tr key={u.id}>
                    <td className="mono">#{u.id}</td>
                    <td>
                      <strong>{u.full_name}</strong>
                    </td>
                    <td>{u.email}</td>
                    <td>
                      <span className={`adm-badge ${u.is_active ? "ok" : "muted"}`}>
                        {u.is_active ? "Active" : "Inactive"}
                      </span>
                    </td>
                    <td>{u.created_at ? formatDateTime(u.created_at) : "—"}</td>
                    <td>
                      <button
                        type="button"
                        className="btn btn-secondary btn-sm"
                        disabled={busyId === u.id}
                        onClick={() => toggleActive(u)}
                      >
                        {u.is_active ? "Deactivate" : "Activate"}
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {totalPages > 1 && (
          <div className="mt-4">
            <Pagination page={page} pageSize={PAGE} total={filtered.length} onPage={setPage} />
          </div>
        )}
      </Card>

      {showCreate && (
        <Modal open title="Add customer" onClose={() => setShowCreate(false)}>
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
