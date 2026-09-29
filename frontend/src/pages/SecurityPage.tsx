import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import {
  Card,
  EmptyState,
  ErrorBox,
  FullPageSpinner,
  SeverityBadge,
  StatCard,
} from "../components/ui";
import { api, errorMessage } from "../lib/api";
import { timeAgo } from "../lib/format";
import type {
  SecurityEventRow,
  SecurityEventsResponse,
  SecurityStatus,
  SecuritySummary,
  SecuritySuiteReport,
  SecurityTestMeta,
} from "../lib/types";

export default function SecurityPage() {
  const [status, setStatus] = useState<SecurityStatus | null>(null);
  const [summary, setSummary] = useState<SecuritySummary | null>(null);
  const [tests, setTests] = useState<SecurityTestMeta[]>([]);
  const [report, setReport] = useState<SecuritySuiteReport | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState("");
  const [eventType, setEventType] = useState("");
  const [filteredEvents, setFilteredEvents] = useState<SecurityEventsResponse | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [statusData, testsData, summaryData] = await Promise.all([
        api<SecurityStatus>("/api/security/status"),
        api<SecurityTestMeta[]>("/api/security/tests"),
        api<SecuritySummary>("/api/security/summary"),
      ]);
      setStatus(statusData);
      setTests(testsData);
      setSummary(summaryData);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function runSuite() {
    setRunning(true);
    setRunError("");
    try {
      setReport(await api<SecuritySuiteReport>("/api/security/tests/run", { method: "POST" }));
      await load();
    } catch (err) {
      setRunError(errorMessage(err));
    } finally {
      setRunning(false);
    }
  }

  async function applyFilter(type: string) {
    setEventType(type);
    if (!type) {
      setFilteredEvents(null);
      return;
    }
    try {
      setFilteredEvents(
        await api<SecurityEventsResponse>("/api/security/events", {
          query: { event_type: type, limit: 50 },
        }),
      );
    } catch (err) {
      setRunError(errorMessage(err));
    }
  }

  if (loading) return <FullPageSpinner />;
  if (error) return <ErrorBox message={error} onRetry={() => void load()} />;
  if (!status || !summary) return null;

  const counts = summary.counts;
  const timeline: SecurityEventRow[] = eventType
    ? filteredEvents?.items || []
    : summary.recent_events;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">Security Command Center</h1>
          <p className="text-sm text-slate-500">
            Prompt-injection defense, Trust Gate verdicts, document quarantine and the live security event timeline.
            Every counter below is computed from real records.
          </p>
        </div>
        <button type="button" className="btn btn-primary" disabled={running} onClick={() => void runSuite()}>
          {running ? "Running suite…" : "Run security suite"}
        </button>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <StatCard
          label="Blocked responses"
          value={counts.blocked_responses}
          tone={counts.blocked_responses > 0 ? "rose" : "emerald"}
          hint="Trust Gate stopped these"
        />
        <StatCard
          label="Review required"
          value={counts.review_required_responses}
          tone="amber"
          hint={`${counts.open_manual_reviews} open manual reviews`}
        />
        <StatCard
          label="Verified responses"
          value={counts.verified_responses}
          tone="emerald"
          hint="passed every independent check"
        />
        <StatCard
          label="Prompt injections"
          value={counts.prompt_injection_complaints}
          tone={counts.prompt_injection_complaints > 0 ? "rose" : "emerald"}
          hint="complaints with injection text"
        />
        <StatCard
          label="Quarantined documents"
          value={counts.quarantined_documents}
          tone={counts.quarantined_documents > 0 ? "amber" : "emerald"}
          hint="excluded from retrieval"
        />
        <StatCard
          label="Security events"
          value={counts.total_security_events}
          tone="brand"
          hint={`${counts.critical_security_events} critical`}
        />
        <StatCard
          label="Security test cases"
          value={summary.security_test_cases.total}
          tone="brand"
          hint={`${summary.security_test_cases.categories.length} attack categories`}
        />
        <StatCard
          label="Provider"
          value={<span className="text-base">{status.provider.effective_provider}</span>}
          tone={status.provider.genai_live ? "emerald" : "amber"}
          hint={status.provider.genai_live ? "live GenAI" : "offline baseline"}
        />
      </div>

      {runError && <ErrorBox message={runError} />}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card
          title="Security event timeline"
          className="lg:col-span-2"
          actions={
            eventType ? (
              <button type="button" className="btn btn-secondary btn-sm" onClick={() => void applyFilter("")}>
                Clear filter: {eventType}
              </button>
            ) : (
              <span className="text-xs text-slate-400">
                latest {summary.recent_events.length} of {counts.total_security_events} events
              </span>
            )
          }
        >
          {timeline.length === 0 ? (
            <EmptyState
              title={eventType ? "No events of this type" : "No security events recorded yet"}
              hint="Run the security suite or the Red-Team Lab to generate real events."
            />
          ) : (
            <ul className="space-y-3">
              {timeline.map((event) => (
                <li key={event.id} className="border-b border-slate-50 pb-2 last:border-0">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <SeverityBadge severity={event.severity} />
                      <span className="font-mono text-xs text-slate-500">{event.event_type}</span>
                    </div>
                    <span className="text-xs text-slate-400">{timeAgo(event.created_at)}</span>
                  </div>
                  <p className="mt-1 text-sm text-slate-700">{event.title}</p>
                  {event.complaint_id && (
                    <Link
                      className="text-xs text-brand-600 hover:underline"
                      to={`/complaints/${event.complaint_id}`}
                    >
                      {event.complaint_code || `complaint #${event.complaint_id}`} →
                    </Link>
                  )}
                </li>
              ))}
            </ul>
          )}
        </Card>

        <div className="space-y-4">
          <Card title="Events by type">
            {summary.events_by_type.length === 0 ? (
              <EmptyState title="No events yet" />
            ) : (
              <ul className="space-y-1.5">
                {summary.events_by_type.map((entry) => (
                  <li key={entry.name}>
                    <button
                      type="button"
                      onClick={() => void applyFilter(eventType === entry.name ? "" : entry.name)}
                      className={`flex w-full items-center justify-between rounded-lg px-2 py-1 text-sm transition ${
                        eventType === entry.name
                          ? "bg-brand-50 text-brand-700"
                          : "text-slate-600 hover:bg-slate-50"
                      }`}
                    >
                      <span className="font-mono text-xs">{entry.name}</span>
                      <span className="chip bg-slate-100 text-slate-600">{entry.value}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>

          <Card title="Events by severity">
            {summary.events_by_severity.length === 0 ? (
              <EmptyState title="No events yet" />
            ) : (
              <ul className="space-y-2">
                {summary.events_by_severity.map((entry) => (
                  <li key={entry.name} className="flex items-center justify-between text-sm">
                    <SeverityBadge severity={entry.name} />
                    <span className="font-semibold text-slate-700">{entry.value}</span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        </div>
      </div>

      <Card
        title={`Human-in-the-loop review queue (${summary.review_queue.length} open)`}
        actions={
          <Link className="text-xs text-brand-600 hover:underline" to="/review">
            Open the Manual Review workspace
          </Link>
        }
      >
        {summary.review_queue.length === 0 ? (
          <EmptyState title="No open manual reviews" hint="Flagged AI outputs will wait here for a human decision." />
        ) : (
          <ul className="space-y-3">
            {summary.review_queue.map((review) => (
              <li key={review.id} className="border-b border-slate-50 pb-2 last:border-0">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  {review.complaint ? (
                    <Link
                      className="font-mono text-xs text-brand-600 hover:underline"
                      to={`/complaints/${review.complaint.id}`}
                    >
                      {review.complaint.code} — {review.complaint.title}
                    </Link>
                  ) : (
                    <span className="font-mono text-xs text-slate-400">complaint #{review.complaint_id}</span>
                  )}
                  <span className="chip bg-amber-100 text-amber-700">{review.source}</span>
                </div>
                <p className="mt-1 text-sm text-slate-600">{review.reason}</p>
                <p className="mt-0.5 text-xs text-slate-400">{timeAgo(review.created_at)}</p>
              </li>
            ))}
          </ul>
        )}
      </Card>

      {report && (
        <Card
          title="Suite report"
          actions={
            <span className={`chip ${report.failed === 0 ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}`}>
              {report.passed}/{report.total} passed · {report.failed} failed
            </span>
          }
        >
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-100">
                  <th className="table-th">Case</th>
                  <th className="table-th">Name</th>
                  <th className="table-th">Category</th>
                  <th className="table-th">Result</th>
                  <th className="table-th">Details</th>
                </tr>
              </thead>
              <tbody>
                {report.results.map((result) => (
                  <tr key={result.case_id} className="border-b border-slate-50">
                    <td className="table-td font-mono text-xs text-brand-600">{result.case_id}</td>
                    <td className="table-td">{result.name}</td>
                    <td className="table-td">
                      <span className="chip bg-slate-100 text-slate-600">{result.category}</span>
                    </td>
                    <td className="table-td">
                      <span className={`chip ${result.passed ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}`}>
                        {result.passed ? "PASS" : "FAIL"}
                      </span>
                    </td>
                    <td className="table-td max-w-[380px]">
                      <ul className="list-inside list-disc space-y-0.5 text-xs text-slate-500">
                        {result.details.map((detail, index) => (
                          <li key={index}>{detail}</li>
                        ))}
                      </ul>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        <Card title={`Adversarial test cases (${tests.length})`}>
          {tests.length === 0 ? (
            <EmptyState title="No test cases registered" />
          ) : (
            <ul className="space-y-2">
              {tests.map((test) => (
                <li key={test.case_id} className="flex items-start justify-between gap-3 border-b border-slate-50 pb-2 last:border-0">
                  <div>
                    <p className="text-sm text-slate-700">
                      <span className="font-mono text-xs text-brand-600">{test.case_id}</span> {test.name}
                    </p>
                  </div>
                  <span className="chip shrink-0 bg-slate-100 text-slate-600">{test.category}</span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Recent audit trail">
          {status.recent_audit.length === 0 ? (
            <EmptyState title="No audit entries yet" />
          ) : (
            <ul className="space-y-2">
              {status.recent_audit.map((entry) => (
                <li key={entry.id} className="border-b border-slate-50 pb-2 text-sm last:border-0">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono text-xs text-slate-600">{entry.action}</span>
                    <span className="text-xs text-slate-400">{timeAgo(entry.created_at)}</span>
                  </div>
                  <p className="text-xs text-slate-500">
                    {entry.actor_email || "system"} · {entry.entity_type} {entry.entity_id}
                    {entry.ip_address ? ` · ${entry.ip_address}` : ""}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}
