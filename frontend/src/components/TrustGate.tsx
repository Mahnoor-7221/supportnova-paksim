// Trust Gate presentation: verdict banner, explainable rejection, transparent
// weighted scoring, failed checks, deterministic ground truth and evidence.
// AI vs Python comparison panel shows what GenAI produced vs what the
// independent Python pipeline verified. Every value is computed by the
// backend engines — nothing here is hardcoded.
import {
  Badge,
  EmptyState,
  MatchBadge,
  SeverityBadge,
} from "./ui";
import { scoreBarClass, titleCase } from "../lib/format";
import type { Comparison, TrustAssessment, Validation } from "../lib/types";

const BANNER_STYLES: Record<string, string> = {
  VERIFIED: "border-emerald-200 bg-emerald-50 text-emerald-900",
  REVIEW_REQUIRED: "border-amber-200 bg-amber-50 text-amber-900",
  BLOCKED: "border-rose-200 bg-rose-50 text-rose-900",
};

const ICON_STYLES: Record<string, string> = {
  VERIFIED: "bg-emerald-600",
  REVIEW_REQUIRED: "bg-amber-500",
  BLOCKED: "bg-rose-600",
};

const ICONS: Record<string, string> = {
  VERIFIED: "✓",
  REVIEW_REQUIRED: "!",
  BLOCKED: "✕",
};

function ScoreBar({ score }: { score: number }) {
  return (
    <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
      <div
        className={`h-full rounded-full ${scoreBarClass(score)}`}
        style={{ width: `${Math.max(0, Math.min(100, score))}%` }}
      />
    </div>
  );
}

export function TrustGatePanel({ trust }: { trust: TrustAssessment }) {
  const totals = trust.categories.reduce(
    (acc, category) => ({
      passed: acc.passed + category.passed,
      warnings: acc.warnings + category.warnings,
      failed: acc.failed + category.failed,
    }),
    { passed: 0, warnings: 0, failed: 0 },
  );
  const totalChecks = totals.passed + totals.warnings + totals.failed;
  const rule = trust.rule || {};

  return (
    <section className="card overflow-hidden">
      <div className={`border-b px-4 py-4 ${BANNER_STYLES[trust.decision] || "border-slate-200 bg-slate-50 text-slate-800"}`}>
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex min-w-0 items-center gap-3">
            <span
              className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full text-lg font-bold text-white ${ICON_STYLES[trust.decision] || "bg-slate-400"}`}
              aria-hidden
            >
              {ICONS[trust.decision] || "?"}
            </span>
            <div className="min-w-0">
              <p className="text-[11px] font-semibold uppercase tracking-widest opacity-70">
                AI Trust Gate · {trust.headline}
              </p>
              <p className="mt-0.5 text-sm font-medium">{trust.explanation}</p>
            </div>
          </div>
          <div className="text-right">
            <p className="text-3xl font-bold leading-none">
              {trust.score}
              <span className="text-base font-medium opacity-60">/100</span>
            </p>
            <p className="mt-1 text-[11px] uppercase tracking-wide opacity-70">trust score</p>
          </div>
        </div>
      </div>

      <div className="space-y-4 p-4">
        {trust.blockers.length > 0 && (
          <div className="rounded-lg border border-rose-200 bg-rose-50 p-3">
            <p className="text-xs font-semibold uppercase tracking-wide text-rose-700">
              Explainable rejection — why this AI output is blocked
            </p>
            <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-rose-800">
              {trust.blockers.map((blocker, index) => (
                <li key={index}>{blocker}</li>
              ))}
            </ul>
          </div>
        )}

        <div>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
              Weighted categories — transparent scoring
            </p>
            <p className="text-xs text-slate-400">
              {totals.passed} passed · {totals.warnings} warning · {totals.failed} failed
              {totalChecks > 0 ? ` of ${totalChecks} checks` : ""}
            </p>
          </div>
          <div className="mt-2 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {trust.categories.map((category) => (
              <div key={category.name} className="rounded-lg border border-slate-100 p-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-sm font-medium text-slate-700">{category.name}</p>
                  <span className="text-xs text-slate-400">weight {Math.round(category.weight * 100)}%</span>
                </div>
                <div className="mt-2 flex items-center gap-2">
                  <ScoreBar score={category.score} />
                  <span className="w-9 text-right text-sm font-semibold text-slate-700">{category.score}</span>
                </div>
                <p className="mt-1.5 text-xs text-slate-500">
                  {category.passed} ok · {category.warnings} warning · {category.failed} failed
                </p>
              </div>
            ))}
          </div>
        </div>

        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
            Failed &amp; warning checks
          </p>
          {trust.failed_checks.length === 0 ? (
            <p className="mt-2 rounded-lg bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
              Every independent check passed — no failed or warning checks.
            </p>
          ) : (
            <div className="mt-2 overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className="table-th">Check</th>
                    <th className="table-th">Category</th>
                    <th className="table-th">Severity</th>
                    <th className="table-th">Status</th>
                    <th className="table-th">Expected</th>
                    <th className="table-th">Actual</th>
                    <th className="table-th">Message</th>
                  </tr>
                </thead>
                <tbody>
                  {trust.failed_checks.map((check, index) => (
                    <tr key={`${check.check_name}-${index}`} className="border-b border-slate-50">
                      <td className="table-td font-medium">{titleCase(check.check_name)}</td>
                      <td className="table-td text-xs text-slate-500">{check.category}</td>
                      <td className="table-td">
                        <SeverityBadge severity={check.severity} />
                      </td>
                      <td className="table-td">
                        <Badge
                          label={check.status}
                          className={check.status === "FAIL" ? "bg-rose-100 text-rose-700" : "bg-amber-100 text-amber-700"}
                        />
                      </td>
                      <td className="table-td max-w-[180px] truncate">{check.expected || "—"}</td>
                      <td className="table-td max-w-[180px] truncate">{check.actual || "—"}</td>
                      <td className="table-td max-w-[280px] text-xs text-slate-500">{check.message}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        <div className="grid gap-4 lg:grid-cols-2">
          <div className="rounded-lg border border-slate-100 p-3">
            <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
              Deterministic ground truth
            </p>
            {rule.rule_id ? (
              <div className="mt-2 space-y-1 text-sm text-slate-700">
                <p>
                  <span className="font-mono text-xs text-slate-500">{rule.rule_id}</span>
                  {rule.matched_rule_source ? ` · ${rule.matched_rule_source}` : ""}
                </p>
                <p>
                  {rule.category || "—"} · {rule.department || "—"} · {rule.urgency || "—"} · {rule.priority || "—"}
                </p>
                <p className="text-xs text-slate-500">
                  Escalation required by rules: {rule.escalation_required ? "Yes" : "No"}
                </p>
              </div>
            ) : (
              <p className="mt-1 text-sm text-slate-400">No deterministic rule matched this complaint.</p>
            )}
          </div>
          <div className="rounded-lg border border-slate-100 p-3">
            <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Security signals</p>
            <div className="mt-2 flex flex-wrap gap-2">
              <Badge
                label={trust.security.injection_detected ? "injection detected" : "no injection"}
                className={
                  trust.security.injection_detected
                    ? "bg-rose-100 text-rose-700"
                    : "bg-emerald-100 text-emerald-700"
                }
              />
              <Badge
                label={trust.security.schema_valid ? "schema valid" : "schema invalid"}
                className={
                  trust.security.schema_valid
                    ? "bg-emerald-100 text-emerald-700"
                    : "bg-rose-100 text-rose-700"
                }
              />
              {trust.security.duplicate && (
                <Badge label="possible duplicate" className="bg-amber-100 text-amber-700" />
              )}
              {trust.security.validation_status && (
                <Badge label={trust.security.validation_status.replace(/_/g, " ")} className="bg-slate-100 text-slate-600" />
              )}
            </div>
          </div>
        </div>

        {trust.evidence.length > 0 && (
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-slate-400">
              Policy evidence the AI was grounded on (traceable citations)
            </p>
            <ul className="mt-2 space-y-1 text-sm text-slate-700">
              {trust.evidence.map((reference, index) => (
                <li key={`${reference.document_code}-${index}`}>
                  <span className="font-mono text-xs">{reference.document_code}</span>
                  {" · "}
                  {reference.section_id ? `section ${reference.section_id} · ` : ""}
                  page {reference.page} · v{reference.version}
                  <span className="ml-2 text-xs text-slate-400">{reference.source_reference}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </section>
  );
}

const COMPARISON_KEYS = [
  "category",
  "subcategory",
  "department",
  "urgency",
  "priority",
  "escalation",
  "follow_up",
];

export function AiVsPythonPanel({ validation }: { validation: Validation }) {
  const summary = validation.summary || {};
  const rows = COMPARISON_KEYS
    .map((key) => ({ key, comparison: summary[key] as Comparison | undefined }))
    .filter((row): row is { key: string; comparison: Comparison } =>
      Boolean(row.comparison && typeof row.comparison === "object" && "match" in row.comparison),
    );
  const checks = validation.checks || [];
  const okCount = checks.filter((check) => check.status === "OK").length;
  const warningCount = checks.filter((check) => check.status === "WARNING").length;
  const failedCount = checks.filter((check) => check.status === "FAIL").length;
  const mismatches = rows.filter((row) => !row.comparison.match).length;

  if (rows.length === 0) {
    return (
      <section className="card">
        <header className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-700">AI vs Python — independent verification</h2>
        </header>
        <div className="p-4">
          <EmptyState
            title="No field comparison recorded yet"
            hint="Run the GenAI analysis and then the Python validation to compare both pipelines."
          />
        </div>
      </section>
    );
  }

  return (
    <section className="card">
      <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
        <h2 className="text-sm font-semibold text-slate-700">
          AI vs Python — independent verification
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          <span className={`chip ${mismatches === 0 ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}`}>
            {mismatches === 0 ? "all compared fields match" : `${mismatches} mismatch${mismatches === 1 ? "" : "es"}`}
          </span>
          <span className="chip bg-emerald-100 text-emerald-700">{okCount} ok</span>
          {warningCount > 0 && <span className="chip bg-amber-100 text-amber-700">{warningCount} warning</span>}
          {failedCount > 0 && <span className="chip bg-rose-100 text-rose-700">{failedCount} failed</span>}
        </div>
      </header>
      <div className="p-4">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-100">
                <th className="table-th">Field</th>
                <th className="table-th">GenAI said (Pipeline 1)</th>
                <th className="table-th">Python verified (Pipeline 2)</th>
                <th className="table-th">Verdict</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr
                  key={row.key}
                  className={`border-b border-slate-50 ${row.comparison.match ? "" : "bg-rose-50/60"}`}
                >
                  <td className="table-td font-medium">{titleCase(row.key)}</td>
                  <td className="table-td">{row.comparison.actual || "—"}</td>
                  <td className="table-td">{row.comparison.expected || "—"}</td>
                  <td className="table-td">
                    <MatchBadge match={row.comparison.match ? "MATCH" : "MISMATCH"} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-xs text-slate-500">
          {mismatches === 0
            ? "The GenAI output agrees with the deterministic rule engine on every compared field."
            : "Mismatched fields are overridden with the Python-verified values and the case is routed to a human reviewer — the AI never ships unverified fields."}
        </p>
      </div>
    </section>
  );
}
