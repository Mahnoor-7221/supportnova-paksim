import { useCallback, useEffect, useState } from "react";
import { Card, ErrorBox, FullPageSpinner } from "../components/ui";
import { api, errorMessage } from "../lib/api";
import type { PromptsResponse } from "../lib/types";

type Tab = "general" | "ai" | "notifications";

export default function AdminSettingsPage() {
  const [tab, setTab] = useState<Tab>("general");
  const [system, setSystem] = useState<{ app?: string; provider?: unknown; counts?: Record<string, number> } | null>(null);
  const [prompts, setPrompts] = useState<PromptsResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [status, pr] = await Promise.all([
        api<{ app?: string; provider?: unknown; counts?: Record<string, number> }>("/api/system/status"),
        api<PromptsResponse>("/api/prompts").catch(() => null),
      ]);
      setSystem(status);
      setPrompts(pr);
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

  return (
    <div className="adm-page">
      <header className="adm-page-head">
        <div>
          <h1>Settings</h1>
          <p>System configuration. Category-specific SLA is managed under Categories & SLA.</p>
        </div>
      </header>

      {error && <ErrorBox message={error} onRetry={load} />}

      <div className="adm-tabs">
        {(
          [
            ["general", "General"],
            ["ai", "AI Configuration"],
            ["notifications", "Notifications"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            className={`adm-tab ${tab === id ? "is-active" : ""}`}
            onClick={() => setTab(id)}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "general" && (
        <Card title="General">
          <div className="adm-settings-grid">
            <div>
              <span className="label">System name</span>
              <p className="mt-1 font-medium">{system?.app || "SupportNova"}</p>
            </div>
            <div>
              <span className="label">Total complaints</span>
              <p className="mt-1 font-medium">{system?.counts?.complaints ?? "—"}</p>
            </div>
            <div>
              <span className="label">Total users</span>
              <p className="mt-1 font-medium">{system?.counts?.users ?? "—"}</p>
            </div>
            <div>
              <span className="label">Contact</span>
              <p className="mt-1 text-sm text-slate-500">support@paksim.demo</p>
            </div>
          </div>
        </Card>
      )}

      {tab === "ai" && (
        <Card title="AI Configuration">
          <div className="adm-settings-grid">
            <div>
              <span className="label">Provider status</span>
              <pre className="adm-pre mt-2">
                {JSON.stringify(system?.provider || prompts?.provider || {}, null, 2)}
              </pre>
            </div>
          </div>
          {prompts?.prompts && prompts.prompts.length > 0 && (
            <div className="mt-6">
              <h3 className="text-sm font-semibold text-slate-700 mb-3">Prompt versions</h3>
              <div className="adm-table-wrap">
                <table className="adm-table">
                  <thead>
                    <tr>
                      <th>Name</th>
                      <th>Version</th>
                      <th>Active</th>
                      <th>Notes</th>
                    </tr>
                  </thead>
                  <tbody>
                    {prompts.prompts.map((p) => (
                      <tr key={p.id}>
                        <td>{p.name}</td>
                        <td className="mono">v{p.version}</td>
                        <td>
                          <span className={`adm-badge ${p.is_active ? "ok" : "muted"}`}>
                            {p.is_active ? "Active" : "—"}
                          </span>
                        </td>
                        <td className="text-xs text-slate-500">{p.notes || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </Card>
      )}

      {tab === "notifications" && (
        <Card title="Notifications">
          <p className="text-sm text-slate-500 mb-4">
            Notification channels for complaint alerts, SLA risk and escalations.
          </p>
          <ul className="adm-settings-list">
            <li>
              <strong>Email notifications</strong>
              <span>Enabled for assigned agents and escalations</span>
            </li>
            <li>
              <strong>SLA alerts</strong>
              <span>Triggered when a case is within 20% of SLA deadline</span>
            </li>
            <li>
              <strong>Escalation notifications</strong>
              <span>Sent to escalation-target departments</span>
            </li>
            <li>
              <strong>AI review alerts</strong>
              <span>When confidence is low or manual review is required</span>
            </li>
          </ul>
        </Card>
      )}
    </div>
  );
}
