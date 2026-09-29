import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import {
  Card,
  EmptyState,
  ErrorBox,
  FullPageSpinner,
  MatchBadge,
  Pagination,
  StatCard,
  VerificationBadge,
} from "../components/ui";
import { api, downloadCsv, errorMessage } from "../lib/api";
import { useAuth } from "../lib/auth";
import { titleCase, timeAgo } from "../lib/format";
import type { AnalyticsData, ReportsOverview, UnseenRow, UnseenRunResult } from "../lib/types";

const PAGE_SIZE = 50;

function differs(left: string | undefined, right: string | undefined): boolean {
  if (!left || !right) return false;
  return left.trim().toLowerCase() !== right.trim().toLowerCase();
}

function OutcomeCell({
  category,
  department,
  urgency,
  compareCategory,
  compareDepartment,
  compareUrgency,
}: {
  category: string;
  department: string;
  urgency: string;
  compareCategory?: string;
  compareDepartment?: string;
  compareUrgency?: string;
}) {
  return (
    <div className="space-y-0.5 text-xs">
      <p className={differs(category, compareCategory) ? "font-semibold text-rose-600" : "font-medium text-slate-700"}>
        {category || "—"}
      </p>
      <p className={differs(department, compareDepartment) ? "text-rose-600" : "text-slate-500"}>
        {department || "—"}
      </p>
      <p className={differs(urgency, compareUrgency) ? "text-rose-600" : "text-slate-400"}>{urgency || "—"}</p>
    </div>
  );
}

export default function ReportsPage() {
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [overview, setOverview] = useState<ReportsOverview | null>(null);
  const [rows, setRows] = useState<UnseenRow[]>([]);
  const [analytics, setAnalytics] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [onlyMismatches, setOnlyMismatches] = useState(false);
  const [page, setPage] = useState(1);

  const [runLimit, setRunLimit] = useState(100);
  const [running, setRunning] = useState(false);
  const [runResult, setRunResult] = useState<UnseenRunResult | null>(null);
  const [runError, setRunError] = useState("");
  const [exportError, setExportError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [overviewData, comparison] = await Promise.all([
        api<ReportsOverview>("/api/reports"),
        api<{ total: number; offset: number; limit: number; rows: UnseenRow[] }>("/api/reports/unseen", {
          query: { limit: 500, offset: 0 },
        }),
      ]);
      setOverview(overviewData);
      setRows(comparison.rows);
      try {
        setAnalytics(await api<AnalyticsData>("/api/analytics"));
      } catch {
        setAnalytics(null);
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const summary = useMemo(() => {
    const counts = { MATCH: 0, MISMATCH: 0, MANUAL_REVIEW: 0, UNKNOWN: 0 };
    for (const row of rows) {
      if (row.match in counts) counts[row.match as keyof typeof counts] += 1;
      else counts.UNKNOWN += 1;
    }
    return counts;
  }, [rows]);

  const filteredRows = useMemo(
    () => (onlyMismatches ? rows.filter((row) => row.match !== "MATCH") : rows),
    [rows, onlyMismatches],
  );
  const pageRows = filteredRows.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);

  async function handleRun() {
    setRunning(true);
    setRunError("");
    try {
      const result = await api<UnseenRunResult>("/api/reports/unseen/run", {
        method: "POST",
        body: { limit: runLimit },
      });
      setRunResult(result);
      await load();
    } catch (err) {
      setRunError(errorMessage(err));
    } finally {
      setRunning(false);
    }
  }

  async function handleExport() {
    setExportError("");
    try {
      await downloadCsv(
        `/api/reports/unseen/export.csv${onlyMismatches ? "?only_mismatches=true" : ""}`,
        "supportnova_unseen_comparison.csv",
      );
    } catch (err) {
      setExportError(errorMessage(err));
    }
  }

  if (loading) return <FullPageSpinner />;
  if (error) return <ErrorBox message={error} onRetry={() => void load()} />;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">Reports — GenAI vs Python (unseen cases)</h1>
          <p className="text-sm text-slate-500">
            Pipeline 2 independently validates Pipeline 1 on cases the prompts were never tuned on.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-2 text-sm text-slate-600">
            <input
              type="checkbox"
              checked={onlyMismatches}
              onChange={(event) => {
                setOnlyMismatches(event.target.checked);
                setPage(1);
              }}
            />
            Only mismatches / review
          </label>
          <button type="button" className="btn btn-secondary" onClick={() => void handleExport()}>
            Export CSV
          </button>
        </div>
      </div>

      {exportError && <ErrorBox message={exportError} />}

      {overview && (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
          <StatCard label="Dataset cases" value={overview.dataset.total_cases} tone="brand" hint={`${overview.dataset.train_cases} training`} />
          <StatCard label="Unseen cases" value={overview.dataset.unseen_cases} tone="sky" hint={`${overview.dataset.unseen_remaining} not yet compared`} />
          <StatCard
            label="Unseen compared"
            value={overview.dataset.unseen_compared}
            tone={overview.dataset.requirement_met ? "emerald" : "amber"}
            hint={`minimum required: ${overview.dataset.minimum_required}`}
          />
          <StatCard
            label="Verification outcome"
            value={`${summary.MATCH} / ${filteredRows.length}`}
            tone="slate"
            hint={`${summary.MISMATCH} mismatch · ${summary.MANUAL_REVIEW} manual review`}
          />
        </div>
      )}

      {isAdmin && (
        <Card title="Run pipeline comparison on unseen cases">
          <div className="flex flex-wrap items-end gap-3">
            <div>
              <label className="label">Batch size</label>
              <input
                type="number"
                min={1}
                max={200}
                className="input mt-1 w-32"
                value={runLimit}
                onChange={(event) => setRunLimit(Math.max(1, Math.min(200, Number(event.target.value) || 1)))}
              />
            </div>
            <button type="button" className="btn btn-primary" disabled={running} onClick={() => void handleRun()}>
              {running ? "Running pipelines…" : "Run comparison"}
            </button>
            <p className="pb-2 text-xs text-slate-400">
              Runs GenAI analysis + Python validation on the next unseen cases without results (offline baseline is
              deterministic).
            </p>
          </div>
          {runError && (
            <div className="mt-3">
              <ErrorBox message={runError} />
            </div>
          )}
          {runResult && (
            <div className="mt-3 rounded-lg bg-slate-50 p-3 text-sm text-slate-600">
              Processed <strong>{runResult.processed}</strong> cases · compared total{" "}
              <strong>{runResult.compared_total}</strong>
              {Object.keys(runResult.statuses).length > 0 && (
                <span>
                  {" "}
                  · outcomes:{" "}
                  {Object.entries(runResult.statuses)
                    .map(([status, count]) => `${status} ×${count}`)
                    .join(", ")}
                </span>
              )}
              {runResult.errors.length > 0 && (
                <ul className="mt-2 list-inside list-disc text-rose-600">
                  {runResult.errors.map((message, index) => (
                    <li key={index}>{message}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </Card>
      )}

      <Card title={`Unseen comparison (${filteredRows.length} rows)`}>
        {pageRows.length === 0 ? (
          <EmptyState
            title="No comparison rows yet"
            hint={isAdmin ? "Run the comparison above to populate this report." : "An admin needs to run the comparison first."}
          />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className="table-th">Case</th>
                    <th className="table-th">Expected (rules)</th>
                    <th className="table-th">GenAI output</th>
                    <th className="table-th">Python validated</th>
                    <th className="table-th">Escalation G/P</th>
                    <th className="table-th">Policy reference</th>
                    <th className="table-th">Match</th>
                    <th className="table-th">Explanation</th>
                  </tr>
                </thead>
                <tbody>
                  {pageRows.map((row) => (
                    <tr key={row.complaint_id} className="border-b border-slate-50 hover:bg-slate-50">
                      <td className="table-td">
                        <Link
                          to={`/complaints/${row.complaint_id}`}
                          className="font-mono text-xs text-brand-600 hover:underline"
                        >
                          {row.case_code || row.complaint_code}
                        </Link>
                        <span className="mt-1 flex flex-wrap gap-1">
                          {row.flags.slice(0, 3).map((flagValue) => (
                            <span key={flagValue} className="chip bg-slate-100 text-slate-500">
                              {flagValue}
                            </span>
                          ))}
                        </span>
                      </td>
                      <td className="table-td">
                        <div className="space-y-0.5 text-xs">
                          <p className="font-medium text-slate-700">{row.expected_category || "—"}</p>
                        </div>
                      </td>
                      <td className="table-td">
                        <OutcomeCell
                          category={row.genai_category}
                          department={row.genai_department}
                          urgency={row.genai_urgency}
                          compareCategory={row.python_category}
                          compareDepartment={row.python_department}
                          compareUrgency={row.python_urgency}
                        />
                      </td>
                      <td className="table-td">
                        <OutcomeCell
                          category={row.python_category}
                          department={row.python_department}
                          urgency={row.python_urgency}
                          compareCategory={row.expected_category}
                        />
                      </td>
                      <td className="table-td text-xs">
                        <span className="text-slate-500">G: {row.genai_escalation}</span>
                        <span className="block text-slate-500">P: {row.python_escalation}</span>
                      </td>
                      <td className="table-td font-mono text-xs text-slate-500">{row.policy_reference || "—"}</td>
                      <td className="table-td">
                        <div className="space-y-1">
                          <MatchBadge match={row.match} />
                          <VerificationBadge status={row.verification_status} />
                        </div>
                      </td>
                      <td className="table-td max-w-[260px] text-xs text-slate-500" title={row.explanation}>
                        {row.explanation}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={page} pageSize={PAGE_SIZE} total={filteredRows.length} onPage={setPage} />
          </>
        )}
      </Card>

      {analytics && (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            <Card title="Mismatch rate by category">
              {analytics.mismatch_by_category.length === 0 ? (
                <EmptyState title="No validated complaints yet" />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full">
                    <thead>
                      <tr className="border-b border-slate-100">
                        <th className="table-th">Category</th>
                        <th className="table-th">Total</th>
                        <th className="table-th">Mismatch</th>
                        <th className="table-th">Manual review</th>
                        <th className="table-th">Warning</th>
                        <th className="table-th">Verified</th>
                        <th className="table-th">Rate</th>
                      </tr>
                    </thead>
                    <tbody>
                      {analytics.mismatch_by_category.map((bucket) => (
                        <tr key={bucket.category} className="border-b border-slate-50">
                          <td className="table-td font-medium">{bucket.category}</td>
                          <td className="table-td">{bucket.total}</td>
                          <td className="table-td text-rose-600">{bucket.mismatched}</td>
                          <td className="table-td text-amber-600">{bucket.manual_review}</td>
                          <td className="table-td">{bucket.warning}</td>
                          <td className="table-td text-emerald-600">{bucket.verified}</td>
                          <td className="table-td">
                            <div className="flex items-center gap-2">
                              <div className="h-1.5 w-16 overflow-hidden rounded-full bg-slate-100">
                                <div
                                  className="h-full rounded-full bg-rose-500"
                                  style={{ width: `${Math.min(100, Math.round(bucket.rate * 100))}%` }}
                                />
                              </div>
                              <span className="text-xs text-slate-500">{Math.round(bucket.rate * 100)}%</span>
                            </div>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>

            <div className="space-y-4">
              <Card title="Escalation triggers">
                {analytics.escalation_triggers.length === 0 ? (
                  <EmptyState title="No escalations recorded" />
                ) : (
                  <ul className="space-y-2">
                    {analytics.escalation_triggers.map((entry) => (
                      <li key={entry.name} className="flex items-center justify-between text-sm">
                        <span className="text-slate-600">{titleCase(String(entry.name))}</span>
                        <span className="chip bg-purple-100 text-purple-700">{entry.value}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
              <Card title="Manual review sources">
                {analytics.manual_review_sources.length === 0 ? (
                  <EmptyState title="No manual reviews recorded" />
                ) : (
                  <ul className="space-y-2">
                    {analytics.manual_review_sources.map((entry) => (
                      <li key={entry.name} className="flex items-center justify-between text-sm">
                        <span className="text-slate-600">{titleCase(String(entry.name))}</span>
                        <span className="chip bg-amber-100 text-amber-700">{entry.value}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </Card>
            </div>
          </div>

          <Card title={`SLA risk (${analytics.sla_risk.length})`}>
            {analytics.sla_risk.length === 0 ? (
              <EmptyState title="No complaints at SLA risk" />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-slate-100">
                      <th className="table-th">Code</th>
                      <th className="table-th">Title</th>
                      <th className="table-th">Status</th>
                      <th className="table-th">Priority</th>
                      <th className="table-th">SLA due</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analytics.sla_risk.map((complaint) => (
                      <tr key={complaint.id} className="border-b border-slate-50 hover:bg-slate-50">
                        <td className="table-td font-mono text-xs">
                          <Link to={`/complaints/${complaint.id}`} className="text-brand-600 hover:underline">
                            {complaint.code}
                          </Link>
                        </td>
                        <td className="table-td max-w-[320px] truncate">{complaint.title}</td>
                        <td className="table-td text-xs">{complaint.status}</td>
                        <td className="table-td text-xs">{complaint.priority || "—"}</td>
                        <td className="table-td text-xs text-rose-600">{timeAgo(complaint.sla_due_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
