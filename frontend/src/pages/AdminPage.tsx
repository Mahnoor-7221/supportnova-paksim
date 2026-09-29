import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Card, EmptyState, ErrorBox, FullPageSpinner, Modal, Pagination } from "../components/ui";
import { api, errorMessage } from "../lib/api";
import { formatDateTime, timeAgo } from "../lib/format";
import type { AuditEntry, AuthUser, Paginated, PromptsResponse } from "../lib/types";

type Tab = "users" | "audit" | "prompts";

type UserRow = AuthUser & { created_at?: string | null };

const AUDIT_PAGE_SIZE = 50;
const ROLE_STYLES: Record<string, string> = {
  admin: "bg-purple-100 text-purple-700",
  agent: "bg-brand-100 text-brand-700",
  reviewer: "bg-amber-100 text-amber-800",
  manager: "bg-emerald-100 text-emerald-700",
  customer: "bg-slate-100 text-slate-600",
};

interface UserForm {
  email: string;
  full_name: string;
  password: string;
  role: "admin" | "agent" | "reviewer" | "manager" | "customer";
}

const EMPTY_USER_FORM: UserForm = { email: "", full_name: "", password: "", role: "agent" };

export default function AdminPage() {
  const [tab, setTab] = useState<Tab>("users");
  const [error, setError] = useState("");

  // Users
  const [users, setUsers] = useState<UserRow[]>([]);
  const [usersLoading, setUsersLoading] = useState(true);
  const [busyUserId, setBusyUserId] = useState<number | null>(null);
  const [showCreateUser, setShowCreateUser] = useState(false);
  const [userForm, setUserForm] = useState<UserForm>(EMPTY_USER_FORM);
  const [userFormError, setUserFormError] = useState("");
  const [creatingUser, setCreatingUser] = useState(false);

  // Audit logs
  const [audit, setAudit] = useState<Paginated<AuditEntry> | null>(null);
  const [auditLoading, setAuditLoading] = useState(false);
  const [auditPage, setAuditPage] = useState(1);
  const [auditAction, setAuditAction] = useState("");
  const [auditEntityType, setAuditEntityType] = useState("");
  const [auditActionInput, setAuditActionInput] = useState("");
  const [auditEntityInput, setAuditEntityInput] = useState("");

  // Prompts
  const [prompts, setPrompts] = useState<PromptsResponse | null>(null);
  const [promptsLoading, setPromptsLoading] = useState(false);

  const loadUsers = useCallback(async () => {
    setUsersLoading(true);
    setError("");
    try {
      setUsers(await api<UserRow[]>("/api/users"));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setUsersLoading(false);
    }
  }, []);

  const loadAudit = useCallback(async () => {
    setAuditLoading(true);
    setError("");
    try {
      setAudit(
        await api<Paginated<AuditEntry>>("/api/audit-logs", {
          query: {
            limit: AUDIT_PAGE_SIZE,
            offset: (auditPage - 1) * AUDIT_PAGE_SIZE,
            action: auditAction || undefined,
            entity_type: auditEntityType || undefined,
          },
        }),
      );
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setAuditLoading(false);
    }
  }, [auditPage, auditAction, auditEntityType]);

  const loadPrompts = useCallback(async () => {
    setPromptsLoading(true);
    setError("");
    try {
      setPrompts(await api<PromptsResponse>("/api/prompts"));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setPromptsLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadUsers();
  }, [loadUsers]);

  useEffect(() => {
    if (tab === "audit") void loadAudit();
  }, [tab, loadAudit]);

  useEffect(() => {
    if (tab === "prompts" && prompts === null) void loadPrompts();
  }, [tab, prompts, loadPrompts]);

  async function toggleActive(user: UserRow) {
    setBusyUserId(user.id);
    setError("");
    try {
      await api(`/api/users/${user.id}`, { method: "PUT", body: { is_active: !user.is_active } });
      await loadUsers();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusyUserId(null);
    }
  }

  async function handleCreateUser(event: FormEvent) {
    event.preventDefault();
    setCreatingUser(true);
    setUserFormError("");
    try {
      await api("/api/users", { method: "POST", body: userForm });
      setShowCreateUser(false);
      setUserForm(EMPTY_USER_FORM);
      await loadUsers();
    } catch (err) {
      setUserFormError(errorMessage(err));
    } finally {
      setCreatingUser(false);
    }
  }

  function applyAuditFilters(event: FormEvent) {
    event.preventDefault();
    setAuditPage(1);
    setAuditAction(auditActionInput.trim());
    setAuditEntityType(auditEntityInput.trim());
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">Administration</h1>
          <p className="text-sm text-slate-500">Users, audit trail and versioned prompt templates.</p>
        </div>
        <div className="flex gap-2">
          {(["users", "audit", "prompts"] as Tab[]).map((item) => (
            <button
              key={item}
              type="button"
              className={`btn btn-sm ${tab === item ? "btn-primary" : "btn-secondary"}`}
              onClick={() => setTab(item)}
            >
              {item === "users" ? "Users" : item === "audit" ? "Audit logs" : "Prompts"}
            </button>
          ))}
        </div>
      </div>

      {error && <ErrorBox message={error} />}

      {tab === "users" && (
        <>
          <div className="flex justify-end">
            <button type="button" className="btn btn-primary" onClick={() => setShowCreateUser(true)}>
              New user
            </button>
          </div>

          <Card>
            {usersLoading ? (
              <FullPageSpinner />
            ) : users.length === 0 ? (
              <EmptyState title="No users found" />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-slate-100">
                      <th className="table-th">ID</th>
                      <th className="table-th">Name</th>
                      <th className="table-th">Email</th>
                      <th className="table-th">Role</th>
                      <th className="table-th">Status</th>
                      <th className="table-th">Created</th>
                      <th className="table-th">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((user) => (
                      <tr key={user.id} className="border-b border-slate-50 hover:bg-slate-50">
                        <td className="table-td text-xs text-slate-400">#{user.id}</td>
                        <td className="table-td">{user.full_name || "—"}</td>
                        <td className="table-td">{user.email}</td>
                        <td className="table-td">
                          <span className={`chip ${ROLE_STYLES[user.role] || "bg-slate-100 text-slate-600"}`}>
                            {user.role || "unknown"}
                          </span>
                        </td>
                        <td className="table-td">
                          {user.is_active ? (
                            <span className="chip bg-emerald-100 text-emerald-700">active</span>
                          ) : (
                            <span className="chip bg-rose-100 text-rose-700">disabled</span>
                          )}
                        </td>
                        <td className="table-td whitespace-nowrap text-xs text-slate-500">
                          {formatDateTime(user.created_at)}
                        </td>
                        <td className="table-td">
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            disabled={busyUserId === user.id}
                            onClick={() => void toggleActive(user)}
                          >
                            {busyUserId === user.id ? "Saving…" : user.is_active ? "Disable" : "Enable"}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}

      {tab === "audit" && (
        <>
          <Card>
            <form className="flex flex-wrap items-end gap-3" onSubmit={applyAuditFilters}>
              <div>
                <label className="label">Action contains</label>
                <input
                  className="input mt-1"
                  value={auditActionInput}
                  onChange={(event) => setAuditActionInput(event.target.value)}
                  placeholder="e.g. complaint. or manual_review."
                />
              </div>
              <div>
                <label className="label">Entity type</label>
                <input
                  className="input mt-1"
                  value={auditEntityInput}
                  onChange={(event) => setAuditEntityInput(event.target.value)}
                  placeholder="e.g. complaint, document, user"
                />
              </div>
              <button type="submit" className="btn btn-primary btn-sm">
                Apply
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                onClick={() => {
                  setAuditActionInput("");
                  setAuditEntityInput("");
                  setAuditAction("");
                  setAuditEntityType("");
                  setAuditPage(1);
                }}
              >
                Reset
              </button>
            </form>
          </Card>

          <Card title={audit ? `${audit.total} entries` : "Audit trail"}>
            {auditLoading ? (
              <FullPageSpinner />
            ) : !audit || audit.items.length === 0 ? (
              <EmptyState title="No audit entries" hint="Actions across the system are recorded here." />
            ) : (
              <>
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-slate-100">
                        <th className="table-th">Action</th>
                        <th className="table-th">Entity</th>
                        <th className="table-th">Actor</th>
                        <th className="table-th">IP</th>
                        <th className="table-th">Detail</th>
                        <th className="table-th">When</th>
                      </tr>
                    </thead>
                    <tbody>
                      {audit.items.map((entry) => (
                        <tr key={entry.id} className="border-b border-slate-50">
                          <td className="table-td font-mono text-xs">{entry.action}</td>
                          <td className="table-td text-xs">
                            {entry.entity_type}
                            {entry.entity_id ? ` · ${entry.entity_id}` : ""}
                          </td>
                          <td className="table-td text-xs text-slate-500">{entry.actor_email || "system"}</td>
                          <td className="table-td font-mono text-xs text-slate-400">{entry.ip_address || "—"}</td>
                          <td className="table-td max-w-[300px] truncate font-mono text-xs text-slate-500" title={JSON.stringify(entry.detail)}>
                            {JSON.stringify(entry.detail)}
                          </td>
                          <td className="table-td whitespace-nowrap text-xs text-slate-500">{timeAgo(entry.created_at)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <Pagination page={auditPage} pageSize={AUDIT_PAGE_SIZE} total={audit.total} onPage={setAuditPage} />
              </>
            )}
          </Card>
        </>
      )}

      {tab === "prompts" && (
        <>
          {prompts && (
            <div className="card flex flex-wrap items-center gap-3 px-4 py-3 text-xs text-slate-500">
              <span className={`chip ${prompts.provider.genai_live ? "bg-emerald-100 text-emerald-700" : "bg-amber-100 text-amber-700"}`}>
                {prompts.provider.genai_live ? "GenAI live" : "Offline baseline"}
              </span>
              <span>
                provider <strong className="text-slate-700">{prompts.provider.effective_provider}</strong>
                {prompts.provider.model ? ` · ${prompts.provider.model}` : ""}
              </span>
              <span className="text-slate-400">{prompts.provider.note}</span>
            </div>
          )}
          <Card>
            {promptsLoading ? (
              <FullPageSpinner />
            ) : !prompts || prompts.prompts.length === 0 ? (
              <EmptyState title="No prompt versions" hint="Prompt templates are registered at startup." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-slate-100">
                      <th className="table-th">Name</th>
                      <th className="table-th">Version</th>
                      <th className="table-th">File</th>
                      <th className="table-th">Active</th>
                      <th className="table-th">Checksum</th>
                      <th className="table-th">Notes</th>
                      <th className="table-th">Created</th>
                    </tr>
                  </thead>
                  <tbody>
                    {prompts.prompts.map((prompt) => (
                      <tr key={prompt.id} className="border-b border-slate-50">
                        <td className="table-td font-medium">{prompt.name}</td>
                        <td className="table-td">{prompt.version}</td>
                        <td className="table-td max-w-[240px] truncate font-mono text-xs text-slate-500">
                          {prompt.file_path}
                        </td>
                        <td className="table-td">
                          {prompt.is_active ? (
                            <span className="chip bg-emerald-100 text-emerald-700">active</span>
                          ) : (
                            <span className="chip bg-slate-100 text-slate-500">inactive</span>
                          )}
                        </td>
                        <td className="table-td font-mono text-xs text-slate-400">{prompt.checksum.slice(0, 12)}…</td>
                        <td className="table-td max-w-[220px] truncate text-xs text-slate-500">{prompt.notes}</td>
                        <td className="table-td whitespace-nowrap text-xs text-slate-500">{formatDateTime(prompt.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}

      <Modal open={showCreateUser} title="Create a new user" onClose={() => setShowCreateUser(false)}>
        <form className="space-y-4" onSubmit={handleCreateUser}>
          <div>
            <label className="label">Email *</label>
            <input
              type="email"
              required
              className="input mt-1"
              value={userForm.email}
              onChange={(event) => setUserForm({ ...userForm, email: event.target.value })}
              placeholder="person@supportnova.demo"
            />
          </div>
          <div>
            <label className="label">Full name</label>
            <input
              className="input mt-1"
              value={userForm.full_name}
              onChange={(event) => setUserForm({ ...userForm, full_name: event.target.value })}
              placeholder="Jane Doe"
            />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className="label">Password * (min 8 characters)</label>
              <input
                type="password"
                required
                minLength={8}
                className="input mt-1"
                value={userForm.password}
                onChange={(event) => setUserForm({ ...userForm, password: event.target.value })}
              />
            </div>
            <div>
              <label className="label">Role</label>
              <select
                className="input mt-1"
                value={userForm.role}
                onChange={(event) => setUserForm({ ...userForm, role: event.target.value as UserForm["role"] })}
              >
                <option value="agent">agent</option>
                <option value="reviewer">reviewer</option>
                <option value="manager">manager</option>
                <option value="admin">admin</option>
                <option value="customer">customer</option>
              </select>
            </div>
          </div>

          {userFormError && <ErrorBox message={userFormError} />}

          <div className="flex justify-end gap-2">
            <button type="button" className="btn btn-secondary" onClick={() => setShowCreateUser(false)}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={creatingUser}>
              {creatingUser ? "Creating…" : "Create user"}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
