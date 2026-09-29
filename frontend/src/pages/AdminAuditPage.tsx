import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Card, EmptyState, ErrorBox, FullPageSpinner, Pagination } from "../components/ui";
import { api, errorMessage } from "../lib/api";
import { formatDateTime } from "../lib/format";
import type { AuditEntry, Paginated } from "../lib/types";

function humanAction(action: string) { return action.replace(/[_.]+/g, " ").replace(/\b\w/g, (m) => m.toUpperCase()); }

const PAGE_SIZE = 25;

export default function AdminAuditPage() {
  const [data, setData] = useState<Paginated<AuditEntry> | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [page, setPage] = useState(1);
  const [action, setAction] = useState("");
  const [entityType, setEntityType] = useState("");
  const [actionInput, setActionInput] = useState("");
  const [entityInput, setEntityInput] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(
        await api<Paginated<AuditEntry>>("/api/audit-logs", {
          query: {
            limit: PAGE_SIZE,
            offset: (page - 1) * PAGE_SIZE,
            action: action || undefined,
            entity_type: entityType || undefined,
          },
        }),
      );
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [page, action, entityType]);

  useEffect(() => {
    void load();
  }, [load]);

  function applyFilters(e: FormEvent) {
    e.preventDefault();
    setPage(1);
    setAction(actionInput.trim());
    setEntityType(entityInput.trim());
  }

  const totalPages = data ? Math.max(1, Math.ceil((data.total || 0) / PAGE_SIZE)) : 1;

  return (
    <div className="adm-page">
      <header className="adm-page-head">
        <div>
          <h1>Audit Logs</h1>
          <p>Read-only record of administrative and system actions.</p>
        </div>
      </header>

      {error && <ErrorBox message={error} onRetry={load} />}

      <form className="adm-filters" onSubmit={applyFilters}>
        <input
          className="input"
          style={{ maxWidth: 200 }}
          placeholder="Action (e.g. user.created)"
          value={actionInput}
          onChange={(e) => setActionInput(e.target.value)}
        />
        <input
          className="input"
          style={{ maxWidth: 160 }}
          placeholder="Entity type"
          value={entityInput}
          onChange={(e) => setEntityInput(e.target.value)}
        />
        <button type="submit" className="btn btn-secondary btn-sm">
          Filter
        </button>
        <span className="adm-filter-meta">{data?.total ?? 0} entries</span>
      </form>

      <Card>
        {loading ? (
          <FullPageSpinner />
        ) : !data?.items?.length ? (
          <EmptyState title="No audit entries" />
        ) : (
          <div className="adm-table-wrap">
            <table className="adm-table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>User</th>
                  <th>Action</th><th>Details</th>
                  <th>Resource</th>
                  <th>ID</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((row) => (
                  <tr key={row.id}>
                    <td className="text-xs">{row.created_at ? formatDateTime(row.created_at) : "—"}</td>
                    <td className="text-xs">{row.actor_email || "system"}</td>
                    <td>
                      <code className="adm-code">{row.action}</code>
                    </td>
                    <td>{row.entity_type}</td>
                    <td className="mono">{row.entity_id ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {totalPages > 1 && (
          <div className="mt-4">
            <Pagination page={page} pageSize={PAGE_SIZE} total={data?.total ?? 0} onPage={setPage} />
          </div>
        )}
      </Card>
    </div>
  );
}
