// Red-Team Lab & Demo Mode runner. Every scenario executes through the REAL
// pipeline (rule matrix -> AI output -> Python validation -> Trust Gate ->
// security timeline). Scenarios that need a specific AI answer use a prepared
// fixture, clearly labelled below; the detection and scoring shown here are
// computed by the backend engines on every run.
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Card, EmptyState, ErrorBox, FullPageSpinner, Spinner } from "./ui";
import { TrustGatePanel } from "./TrustGate";
import { api, errorMessage } from "../lib/api";
import { decisionClass, timeAgo, titleCase } from "../lib/format";
import type { LabRunResult, LabScenario, LabScenarioList } from "../lib/types";

const STEP_STYLES: Record<string, string> = {
  info: "bg-slate-400",
  OK: "bg-emerald-500",
  FAIL: "bg-rose-500",
  VERIFIED: "bg-emerald-500",
  REVIEW_REQUIRED: "bg-amber-500",
  BLOCKED: "bg-rose-500",
};

export default function LabRunner({ registry }: { registry: "redteam" | "demo" }) {
  const isRedteam = registry === "redteam";
  const [data, setData] = useState<LabScenarioList | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [runningId, setRunningId] = useState("");
  const [runError, setRunError] = useState("");
  const [result, setResult] = useState<LabRunResult | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setData(await api<LabScenarioList>(`/api/${registry}/scenarios`));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [registry]);

  useEffect(() => {
    void load();
  }, [load]);

  async function run(scenario: LabScenario) {
    setRunningId(scenario.id);
    setRunError("");
    try {
      setResult(
        await api<LabRunResult>(`/api/${registry}/run`, {
          method: "POST",
          body: { scenario_id: scenario.id },
        }),
      );
    } catch (err) {
      setRunError(errorMessage(err));
    } finally {
      setRunningId("");
    }
  }

  if (loading) return <FullPageSpinner />;
  if (error) return <ErrorBox message={error} onRetry={() => void load()} />;
  if (!data) return null;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-800">
          {isRedteam ? "Red-Team Lab" : "Demo Mode"}
        </h1>
        <p className="text-sm text-slate-500">
          {isRedteam
            ? "Attack the AI pipeline — every scenario runs through the real engines and the verdict you see is genuinely computed."
            : "Five prepared end-to-end scenarios for a live walkthrough of Generate → Verify → Explain → Protect."}
        </p>
      </div>

      <div className="rounded-lg border border-sky-200 bg-sky-50 px-4 py-3 text-xs text-sky-800">
        {data.note}
      </div>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {data.scenarios.map((scenario) => (
          <div key={scenario.id} className="card flex flex-col p-4">
            <div className="flex flex-wrap items-start justify-between gap-2">
              <div>
                <p className="font-mono text-xs text-slate-400">{scenario.id}</p>
                <h2 className="text-sm font-semibold text-slate-800">{scenario.name}</h2>
              </div>
              <Badge label={`expect: ${scenario.expectation.replace(/_/g, " ")}`} className={decisionClass(scenario.expectation)} />
            </div>
            <p className="mt-2 flex-1 text-xs text-slate-500">{scenario.description}</p>
            <p className="mt-2 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
              <span className="font-semibold uppercase tracking-wide text-slate-400">Attack · </span>
              {scenario.attack}
            </p>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2">
              <div className="flex flex-wrap gap-1.5">
                <Badge label={scenario.category} className="bg-slate-100 text-slate-600" />
                {scenario.uses_fixture ? (
                  <Badge label="fixture AI answer" className="bg-violet-100 text-violet-700" />
                ) : (
                  <Badge label="live pipeline AI" className="bg-emerald-100 text-emerald-700" />
                )}
              </div>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                disabled={runningId !== ""}
                onClick={() => void run(scenario)}
              >
                {runningId === scenario.id ? (
                  <span className="flex items-center gap-2">
                    <Spinner className="h-3.5 w-3.5" /> Running…
                  </span>
                ) : (
                  "Run scenario"
                )}
              </button>
            </div>
          </div>
        ))}
      </div>

      {runError && <ErrorBox message={runError} />}

      {result && (
        <div className="space-y-4">
          <div
            className={`rounded-lg border px-4 py-3 ${
              result.outcome.matched
                ? "border-emerald-200 bg-emerald-50"
                : "border-rose-200 bg-rose-50"
            }`}
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span
                  className={`chip ${result.outcome.matched ? "bg-emerald-600 text-white" : "bg-rose-600 text-white"}`}
                >
                  {result.outcome.matched ? "OUTCOME MATCHED" : "OUTCOME MISMATCHED"}
                </span>
                <Badge label={`expected: ${result.outcome.expected.replace(/_/g, " ")}`} className={decisionClass(result.outcome.expected)} />
                <span className="text-slate-400">→</span>
                <Badge label={`actual: ${result.outcome.actual.replace(/_/g, " ")}`} className={decisionClass(result.outcome.actual)} />
              </div>
              <span className="text-xs text-slate-500">
                {result.complaint.code} · {timeAgo(result.run_at)} ·{" "}
                <Link className="text-brand-600 hover:underline" to={`/complaints/${result.complaint.id}`}>
                  open complaint record
                </Link>
              </span>
            </div>
          </div>

          <Card title="Pipeline trace" actions={<Badge label={result.scenario.name} className="bg-slate-100 text-slate-600" />}>
            <ol className="space-y-3">
              {result.steps.map((step) => (
                <li key={step.key} className="flex gap-3">
                  <div className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${STEP_STYLES[step.status] || "bg-slate-300"}`} />
                  <div>
                    <p className="text-sm font-medium text-slate-700">
                      {step.label}
                      {step.status !== "info" && (
                        <span className="ml-2">
                          <Badge
                            label={step.status.replace(/_/g, " ")}
                            className={
                              step.status === "OK" || step.status === "VERIFIED"
                                ? "bg-emerald-100 text-emerald-700"
                                : step.status === "REVIEW_REQUIRED"
                                  ? "bg-amber-100 text-amber-700"
                                  : "bg-rose-100 text-rose-700"
                            }
                          />
                        </span>
                      )}
                    </p>
                    <p className="mt-0.5 text-xs text-slate-500">{step.detail}</p>
                  </div>
                </li>
              ))}
            </ol>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card
              title="AI output (Pipeline 1)"
              actions={
                <Badge
                  label={result.ai_output.provider === "simulation-fixture" ? "labelled fixture" : result.ai_output.provider}
                  className={
                    result.ai_output.provider === "simulation-fixture"
                      ? "bg-violet-100 text-violet-700"
                      : "bg-slate-100 text-slate-600"
                  }
                />
              }
            >
              <div className="grid grid-cols-2 gap-3 text-sm text-slate-700">
                <p><span className="text-xs text-slate-400">Category</span><br />{result.ai_output.category || "—"}</p>
                <p><span className="text-xs text-slate-400">Department</span><br />{result.ai_output.department || "—"}</p>
                <p><span className="text-xs text-slate-400">Urgency</span><br />{result.ai_output.urgency || "—"}</p>
                <p><span className="text-xs text-slate-400">Priority</span><br />{result.ai_output.priority || "—"}</p>
                <p><span className="text-xs text-slate-400">Escalation required</span><br />{result.ai_output.escalation_required ? "Yes" : "No"}</p>
                <p><span className="text-xs text-slate-400">Policy cited</span><br />{result.ai_output.policy_id || "—"}</p>
              </div>
              {result.ai_output.professional_response && (
                <div className="mt-3">
                  <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Professional response</p>
                  <p className="mt-1 max-h-48 overflow-y-auto whitespace-pre-wrap rounded-lg bg-slate-50 px-3 py-2 text-sm text-slate-600">
                    {result.ai_output.professional_response}
                  </p>
                </div>
              )}
            </Card>

            <Card
              title="Independent Python validation (Pipeline 2)"
              actions={
                <Badge
                  label={result.validation.status.replace(/_/g, " ")}
                  className={result.validation.status === "VERIFIED" ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"}
                />
              }
            >
              <ul className="space-y-1.5">
                {result.validation.checks.map((check) => (
                  <li key={check.check_name} className="flex items-start gap-2 text-sm">
                    <span
                      className={`mt-0.5 chip shrink-0 ${
                        check.status === "OK"
                          ? "bg-emerald-100 text-emerald-700"
                          : check.status === "WARNING"
                            ? "bg-amber-100 text-amber-700"
                            : "bg-rose-100 text-rose-700"
                      }`}
                    >
                      {check.status}
                    </span>
                    <div>
                      <span className="font-medium text-slate-700">{titleCase(check.check_name)}</span>
                      {check.message && <span className="block text-xs text-slate-500">{check.message}</span>}
                    </div>
                  </li>
                ))}
              </ul>
            </Card>
          </div>

          {result.trust ? (
            <TrustGatePanel trust={result.trust} />
          ) : (
            <Card title="AI Trust Gate">
              <EmptyState title="No trust assessment recorded" hint="The validation step did not produce a verdict for this run." />
            </Card>
          )}

          {result.escalation_required && (
            <div className="rounded-lg border border-purple-200 bg-purple-50 px-4 py-3 text-sm text-purple-800">
              The deterministic escalation engine required an escalation for this scenario — a record was created on the
              complaint record.
            </div>
          )}
        </div>
      )}

      {!result && !runError && (
        <Card title="How this lab works">
          <p className="text-sm text-slate-600">
            Pick a scenario above and press <strong>Run scenario</strong>. The complaint is created in the database, the
            AI analysis step runs, the independent Python pipeline verifies it and the Trust Gate issues a real verdict.
            You can open the created complaint to inspect every recorded artifact. Scenarios marked{" "}
            <Badge label="fixture AI answer" className="bg-violet-100 text-violet-700" /> supply a prepared AI answer so
            the attack can be demonstrated deterministically — the verification, trust score and security events are
            still genuinely computed.
          </p>
        </Card>
      )}
    </div>
  );
}
