import { Fragment, useCallback, useEffect, useState } from "react";
import { Card, EmptyState, ErrorBox, FullPageSpinner, SectionList, UrgencyBadge } from "../components/ui";
import { api, errorMessage } from "../lib/api";
import type { PolicyRow, Rule } from "../lib/types";

type Tab = "rules" | "policies";

export default function RulesPage() {
  const [tab, setTab] = useState<Tab>("rules");

  const [rules, setRules] = useState<Rule[]>([]);
  const [rulesLoading, setRulesLoading] = useState(true);
  const [rulesError, setRulesError] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [expandedRule, setExpandedRule] = useState<number | null>(null);

  const [policies, setPolicies] = useState<PolicyRow[]>([]);
  const [policiesLoading, setPoliciesLoading] = useState(false);
  const [policiesError, setPoliciesError] = useState("");

  const loadRules = useCallback(async () => {
    setRulesLoading(true);
    setRulesError("");
    try {
      setRules(await api<Rule[]>("/api/rules"));
    } catch (err) {
      setRulesError(errorMessage(err));
    } finally {
      setRulesLoading(false);
    }
  }, []);

  const loadPolicies = useCallback(async () => {
    setPoliciesLoading(true);
    setPoliciesError("");
    try {
      setPolicies(await api<PolicyRow[]>("/api/policies"));
    } catch (err) {
      setPoliciesError(errorMessage(err));
    } finally {
      setPoliciesLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRules();
  }, [loadRules]);

  useEffect(() => {
    if (tab === "policies" && policies.length === 0) void loadPolicies();
  }, [tab, policies.length, loadPolicies]);

  const categories = Array.from(new Set(rules.map((rule) => rule.category))).sort();
  const visibleRules = categoryFilter ? rules.filter((rule) => rule.category === categoryFilter) : rules;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">Rule matrix &amp; policies</h1>
          <p className="text-sm text-slate-500">
            Deterministic ground truth used by the validation engine — every complaint is compared against these rules.
          </p>
        </div>
        <div className="flex gap-2">
          <button
            type="button"
            className={`btn btn-sm ${tab === "rules" ? "btn-primary" : "btn-secondary"}`}
            onClick={() => setTab("rules")}
          >
            Rules ({rules.length})
          </button>
          <button
            type="button"
            className={`btn btn-sm ${tab === "policies" ? "btn-primary" : "btn-secondary"}`}
            onClick={() => setTab("policies")}
          >
            Policies
          </button>
        </div>
      </div>

      {tab === "rules" && (
        <>
          <Card>
            <div className="flex flex-wrap items-end gap-3">
              <div>
                <label className="label">Category</label>
                <select
                  className="input mt-1"
                  value={categoryFilter}
                  onChange={(event) => setCategoryFilter(event.target.value)}
                >
                  <option value="">All categories</option>
                  {categories.map((category) => (
                    <option key={category} value={category}>
                      {category}
                    </option>
                  ))}
                </select>
              </div>
              <p className="pb-2 text-xs text-slate-400">
                {visibleRules.length} rule{visibleRules.length === 1 ? "" : "s"} shown
              </p>
            </div>
          </Card>

          {rulesError && <ErrorBox message={rulesError} onRetry={() => void loadRules()} />}

          <Card>
            {rulesLoading ? (
              <FullPageSpinner />
            ) : visibleRules.length === 0 ? (
              <EmptyState title="No rules" hint="Seed the database to load the rule matrix." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-slate-100">
                      <th className="table-th">Rule</th>
                      <th className="table-th">Category</th>
                      <th className="table-th">Subcategory</th>
                      <th className="table-th">Department</th>
                      <th className="table-th">Urgency</th>
                      <th className="table-th">Priority</th>
                      <th className="table-th">Policy</th>
                      <th className="table-th">Escalation</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleRules.map((rule) => (
                      <Fragment key={rule.id}>
                        <tr
                          className="cursor-pointer border-b border-slate-50 hover:bg-slate-50"
                          onClick={() => setExpandedRule(expandedRule === rule.id ? null : rule.id)}
                        >
                          <td className="table-td font-mono text-xs text-brand-600">{rule.rule_id}</td>
                          <td className="table-td">{rule.category}</td>
                          <td className="table-td">{rule.subcategory || "—"}</td>
                          <td className="table-td">{rule.department}</td>
                          <td className="table-td">
                            <UrgencyBadge urgency={rule.urgency} />
                          </td>
                          <td className="table-td">{rule.priority}</td>
                          <td className="table-td font-mono text-xs">{rule.policy_id || "—"}</td>
                          <td className="table-td">
                            {rule.escalation ? (
                              <span className="chip bg-purple-100 text-purple-700">yes</span>
                            ) : (
                              <span className="chip bg-slate-100 text-slate-500">no</span>
                            )}
                          </td>
                        </tr>
                        {expandedRule === rule.id && (
                          <tr className="border-b border-slate-100 bg-slate-50/60">
                            <td colSpan={8} className="px-4 py-4">
                              <div className="grid gap-4 md:grid-cols-3">
                                <SectionList title="Keywords" items={rule.keywords} />
                                <SectionList title="Required actions" items={rule.required_actions} />
                                <SectionList title="Prohibited actions" items={rule.prohibited_actions} />
                              </div>
                              <div className="mt-3 grid gap-4 md:grid-cols-2">
                                {rule.escalation_reason && (
                                  <p className="text-sm text-slate-600">
                                    <span className="font-medium">Escalation reason:</span> {rule.escalation_reason}
                                  </p>
                                )}
                                {rule.escalation_department && (
                                  <p className="text-sm text-slate-600">
                                    <span className="font-medium">Escalate to:</span> {rule.escalation_department}
                                  </p>
                                )}
                              </div>
                              {rule.conditions && Object.keys(rule.conditions).length > 0 && (
                                <pre className="mt-3 overflow-x-auto rounded-lg bg-white p-3 text-xs text-slate-500">
                                  {JSON.stringify(rule.conditions, null, 2)}
                                </pre>
                              )}
                              {rule.response_template && (
                                <p className="mt-3 whitespace-pre-wrap rounded-lg bg-white p-3 text-sm text-slate-600">
                                  {rule.response_template}
                                </p>
                              )}
                            </td>
                          </tr>
                        )}
                      </Fragment>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        </>
      )}

      {tab === "policies" && (
        <>
          {policiesError && <ErrorBox message={policiesError} onRetry={() => void loadPolicies()} />}
          <Card>
            {policiesLoading ? (
              <FullPageSpinner />
            ) : policies.length === 0 ? (
              <EmptyState title="No policies" hint="Policies are seeded alongside the knowledge base." />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-slate-100">
                      <th className="table-th">Policy</th>
                      <th className="table-th">Title</th>
                      <th className="table-th">Version</th>
                      <th className="table-th">Section</th>
                      <th className="table-th">Document</th>
                      <th className="table-th">Active</th>
                      <th className="table-th">Summary</th>
                    </tr>
                  </thead>
                  <tbody>
                    {policies.map((policy) => (
                      <tr key={policy.id} className="border-b border-slate-50 hover:bg-slate-50">
                        <td className="table-td font-mono text-xs text-brand-600">{policy.policy_id}</td>
                        <td className="table-td">{policy.title}</td>
                        <td className="table-td">{policy.version}</td>
                        <td className="table-td">{policy.section || "—"}</td>
                        <td className="table-td font-mono text-xs text-slate-500">
                          {policy.document_code || policy.document_title || "—"}
                        </td>
                        <td className="table-td">
                          {policy.is_active ? (
                            <span className="chip bg-emerald-100 text-emerald-700">active</span>
                          ) : (
                            <span className="chip bg-slate-100 text-slate-500">inactive</span>
                          )}
                        </td>
                        <td className="table-td max-w-[320px] text-xs text-slate-500">{policy.summary}</td>
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
