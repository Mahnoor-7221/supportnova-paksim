import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  Card,
  EmptyState,
  ErrorBox,
  FullPageSpinner,
  KeyValue,
  Modal,
  Pagination,
  StatusBadge,
  UrgencyBadge,
  VerificationBadge,
} from "../components/ui";
import { api, errorMessage } from "../lib/api";
import { timeAgo } from "../lib/format";
import type { ManualReview, ManualReviewDetail, Paginated } from "../lib/types";

const PAGE_SIZE = 25;
const REVIEW_SOURCES = ["validation", "analysis", "genai", "security", "manual"];

interface ModifyFields {
  issue_category: string;
  subcategory: string;
  urgency: string;
  priority: string;
  department: string;
}

const EMPTY_MODIFY: ModifyFields = {
  issue_category: "",
  subcategory: "",
  urgency: "",
  priority: "",
  department: "",
};

export default function ManualReviewPage() {
  const [items, setItems] = useState<ManualReview[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState("OPEN");
  const [sourceFilter, setSourceFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<ManualReviewDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");

  const [notes, setNotes] = useState("");
  const [modify, setModify] = useState<ModifyFields>(EMPTY_MODIFY);
  const [showModify, setShowModify] = useState(false);
  const [deciding, setDeciding] = useState("");
  const [decisionError, setDecisionError] = useState("");
  const [decisionMessage, setDecisionMessage] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await api<Paginated<ManualReview>>("/api/manual-review", {
        query: {
          status: statusFilter || undefined,
          source: sourceFilter || undefined,
          page,
          page_size: PAGE_SIZE,
        },
      });
      setItems(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [statusFilter, sourceFilter, page]);

  useEffect(() => {
    void load();
  }, [load]);

  const loadDetail = useCallback(async (reviewId: number) => {
    setDetailLoading(true);
    setDetailError("");
    try {
      setDetail(await api<ManualReviewDetail>(`/api/manual-review/${reviewId}`));
    } catch (err) {
      setDetailError(errorMessage(err));
    } finally {
      setDetailLoading(false);
    }
  }, []);

  function openReview(reviewId: number) {
    setSelectedId(reviewId);
    setDetail(null);
    setNotes("");
    setModify(EMPTY_MODIFY);
    setShowModify(false);
    setDecisionError("");
    setDecisionMessage("");
    void loadDetail(reviewId);
  }

  function closeReview() {
    setSelectedId(null);
    setDetail(null);
  }

  async function decide(kind: "approve" | "reject" | "escalate" | "modify") {
    if (selectedId === null) return;
    setDeciding(kind);
    setDecisionError("");
    try {
      const modifications: Record<string, string> = {};
      if (kind === "modify") {
        for (const [key, value] of Object.entries(modify)) {
          if (value.trim()) modifications[key] = value.trim();
        }
      }
      await api(`/api/manual-review/${selectedId}/${kind}`, {
        method: "POST",
        body: { notes, modifications },
      });
      closeReview();
      setDecisionMessage(`Review #${selectedId} ${kind}d.`);
      await load();
    } catch (err) {
      setDecisionError(errorMessage(err));
    } finally {
      setDeciding("");
    }
  }

  const openReviewRow = detail?.review;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-800">Manual review queue</h1>
        <p className="text-sm text-slate-500">
          Human-in-the-loop decisions for low-confidence or validation-escalated complaints.
        </p>
      </div>

      {decisionMessage && (
        <p className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-700">
          {decisionMessage}
        </p>
      )}

      <Card>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="label">Status</label>
            <select className="input mt-1" value={statusFilter} onChange={(event) => { setStatusFilter(event.target.value); setPage(1); }}>
              <option value="">All</option>
              <option value="OPEN">Open</option>
              <option value="RESOLVED">Resolved</option>
            </select>
          </div>
          <div>
            <label className="label">Source</label>
            <select className="input mt-1" value={sourceFilter} onChange={(event) => { setSourceFilter(event.target.value); setPage(1); }}>
              <option value="">All sources</option>
              {REVIEW_SOURCES.map((source) => (
                <option key={source} value={source}>
                  {source}
                </option>
              ))}
            </select>
          </div>
        </div>
      </Card>

      {error && <ErrorBox message={error} onRetry={() => void load()} />}

      <Card>
        {loading ? (
          <FullPageSpinner />
        ) : items.length === 0 ? (
          <EmptyState title="Queue is empty" hint="Validation-driven escalations appear here automatically." />
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-100">
                    <th className="table-th">Review</th>
                    <th className="table-th">Complaint</th>
                    <th className="table-th">Reason</th>
                    <th className="table-th">Source</th>
                    <th className="table-th">Complaint status</th>
                    <th className="table-th">Opened</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((review) => (
                    <tr
                      key={review.id}
                      className="cursor-pointer border-b border-slate-50 hover:bg-slate-50"
                      onClick={() => openReview(review.id)}
                    >
                      <td className="table-td">
                        <span className="font-medium">#{review.id}</span>
                        <span className={`chip ml-2 ${review.status === "OPEN" ? "bg-amber-100 text-amber-700" : "bg-slate-100 text-slate-600"}`}>
                          {review.status}
                        </span>
                      </td>
                      <td className="table-td">
                        {review.complaint ? (
                          <>
                            <span className="font-mono text-xs text-brand-600">{review.complaint.code}</span>
                            <span className="block max-w-[260px] truncate text-sm">{review.complaint.title}</span>
                          </>
                        ) : (
                          `#${review.complaint_id}`
                        )}
                      </td>
                      <td className="table-td max-w-[260px] text-xs text-slate-600">{review.reason}</td>
                      <td className="table-td">
                        <span className="chip bg-slate-100 text-slate-600">{review.source}</span>
                      </td>
                      <td className="table-td">
                        <StatusBadge status={review.complaint?.status} />
                      </td>
                      <td className="table-td whitespace-nowrap text-xs text-slate-500">{timeAgo(review.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <Pagination page={page} pageSize={PAGE_SIZE} total={total} onPage={setPage} />
          </>
        )}
      </Card>

      <Modal
        open={selectedId !== null}
        title={openReviewRow ? `Review #${openReviewRow.id} — ${openReviewRow.source}` : "Review detail"}
        onClose={closeReview}
        wide
        footer={
          openReviewRow && openReviewRow.status === "OPEN" ? (
            <div className="flex flex-wrap items-center justify-between gap-3">
              <p className="text-xs text-slate-400">
                Decisions are audited; approve sets the complaint to IN_PROGRESS, reject closes it, escalate creates an
                escalation.
              </p>
              <div className="flex flex-wrap gap-2">
                <button type="button" className="btn btn-secondary btn-sm" disabled={deciding !== ""} onClick={() => void decide("approve")}>
                  {deciding === "approve" ? "Approving…" : "Approve"}
                </button>
                <button type="button" className="btn btn-secondary btn-sm" disabled={deciding !== ""} onClick={() => void decide("escalate")}>
                  {deciding === "escalate" ? "Escalating…" : "Escalate"}
                </button>
                <button
                  type="button"
                  className="btn btn-primary btn-sm"
                  disabled={deciding !== ""}
                  onClick={() => {
                    setShowModify(true);
                  }}
                >
                  Modify fields…
                </button>
                <button type="button" className="btn btn-danger btn-sm" disabled={deciding !== ""} onClick={() => void decide("reject")}>
                  {deciding === "reject" ? "Rejecting…" : "Reject"}
                </button>
              </div>
            </div>
          ) : undefined
        }
      >
        {detailLoading && <FullPageSpinner />}
        {detailError && <ErrorBox message={detailError} onRetry={() => selectedId !== null && void loadDetail(selectedId)} />}
        {detail && !detailLoading && (
          <div className="space-y-4">
            <div className="grid gap-4 md:grid-cols-3">
              <KeyValue label="Reason" value={detail.review.reason} />
              <KeyValue label="Source" value={detail.review.source} />
              <KeyValue label="Opened" value={timeAgo(detail.review.created_at)} />
              {detail.review.decision && <KeyValue label="Decision" value={detail.review.decision} />}
              {detail.review.decision_notes && <KeyValue label="Decision notes" value={detail.review.decision_notes} />}
            </div>

            {detail.complaint && (
              <div className="rounded-lg border border-slate-200 p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <Link
                    to={`/complaints/${detail.complaint.id}`}
                    className="font-mono text-xs text-brand-600 hover:underline"
                  >
                    {detail.complaint.code}
                  </Link>
                  <div className="flex items-center gap-2">
                    <StatusBadge status={detail.complaint.status} />
                    <UrgencyBadge urgency={detail.complaint.verified_urgency || detail.complaint.urgency} />
                    <VerificationBadge status={detail.complaint.verification_status} />
                  </div>
                </div>
                <p className="mt-1 text-sm font-medium text-slate-700">{detail.complaint.title}</p>
                <p className="mt-1 max-h-24 overflow-y-auto whitespace-pre-wrap text-sm text-slate-600">
                  {detail.complaint.description}
                </p>
              </div>
            )}

            {detail.analysis && (
              <div className="rounded-lg border border-slate-200 p-3">
                <p className="text-xs font-medium uppercase tracking-wide text-slate-400">GenAI output</p>
                <div className="mt-2 grid gap-3 md:grid-cols-3">
                  <KeyValue label="Category" value={detail.analysis.parsed.issue_category || "—"} />
                  <KeyValue label="Department" value={detail.analysis.parsed.department || "—"} />
                  <KeyValue label="Urgency / Priority" value={`${detail.analysis.parsed.urgency || "—"} · ${detail.analysis.parsed.priority || "—"}`} />
                </div>
              </div>
            )}

            {detail.validation && (
              <div className="rounded-lg border border-slate-200 p-3">
                <p className="text-xs font-medium uppercase tracking-wide text-slate-400">Validation verdict</p>
                <div className="mt-2 flex flex-wrap items-center gap-2">
                  <VerificationBadge status={detail.validation.status} />
                </div>
                {detail.validation.summary.manual_review_reasons &&
                  detail.validation.summary.manual_review_reasons.length > 0 && (
                    <ul className="mt-2 list-inside list-disc text-sm text-slate-600">
                      {detail.validation.summary.manual_review_reasons.map((reason, index) => (
                        <li key={index}>{reason}</li>
                      ))}
                    </ul>
                  )}
                {detail.validation.summary.unsupported_claims &&
                  detail.validation.summary.unsupported_claims.length > 0 && (
                    <div className="mt-2">
                      <p className="text-xs font-medium text-rose-600">Unsupported claims</p>
                      <ul className="list-inside list-disc text-sm text-slate-600">
                        {detail.validation.summary.unsupported_claims.map((claim, index) => (
                          <li key={index}>{claim}</li>
                        ))}
                      </ul>
                    </div>
                  )}
              </div>
            )}

            {openReviewRow?.status === "OPEN" && (
              <form
                className="space-y-3 border-t border-slate-100 pt-4"
                onSubmit={(event: FormEvent) => event.preventDefault()}
              >
                <div>
                  <label className="label">Decision notes</label>
                  <textarea
                    className="input mt-1"
                    rows={3}
                    value={notes}
                    onChange={(event) => setNotes(event.target.value)}
                    placeholder="Explain the decision for the audit trail…"
                  />
                </div>

                {showModify && (
                  <div className="grid gap-3 rounded-lg border border-brand-100 bg-brand-50/50 p-3 md:grid-cols-2">
                    <p className="text-xs text-slate-500 md:col-span-2">
                      Correct the complaint fields, then press Modify to apply them.
                    </p>
                    <div>
                      <label className="label">Issue category</label>
                      <input
                        className="input mt-1"
                        value={modify.issue_category}
                        onChange={(event) => setModify({ ...modify, issue_category: event.target.value })}
                        placeholder={detail?.complaint?.issue_category || "e.g. Delivery"}
                      />
                    </div>
                    <div>
                      <label className="label">Subcategory</label>
                      <input
                        className="input mt-1"
                        value={modify.subcategory}
                        onChange={(event) => setModify({ ...modify, subcategory: event.target.value })}
                        placeholder={detail?.complaint?.subcategory || "e.g. Late delivery"}
                      />
                    </div>
                    <div>
                      <label className="label">Urgency</label>
                      <select
                        className="input mt-1"
                        value={modify.urgency}
                        onChange={(event) => setModify({ ...modify, urgency: event.target.value })}
                      >
                        <option value="">Keep current</option>
                        {["Low", "Medium", "High", "Critical"].map((option) => (
                          <option key={option} value={option}>
                            {option}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div>
                      <label className="label">Priority</label>
                      <select
                        className="input mt-1"
                        value={modify.priority}
                        onChange={(event) => setModify({ ...modify, priority: event.target.value })}
                      >
                        <option value="">Keep current</option>
                        {["P1", "P2", "P3", "P4"].map((option) => (
                          <option key={option} value={option}>
                            {option}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="md:col-span-2">
                      <label className="label">Department</label>
                      <input
                        className="input mt-1"
                        value={modify.department}
                        onChange={(event) => setModify({ ...modify, department: event.target.value })}
                        placeholder={detail?.complaint?.department || "e.g. Logistics"}
                      />
                    </div>
                    <div className="md:col-span-2 flex justify-end">
                      <button
                        type="button"
                        className="btn btn-primary btn-sm"
                        disabled={deciding !== ""}
                        onClick={() => void decide("modify")}
                      >
                        {deciding === "modify" ? "Applying…" : "Apply modifications"}
                      </button>
                    </div>
                  </div>
                )}

                {decisionError && <ErrorBox message={decisionError} />}
              </form>
            )}
          </div>
        )}
      </Modal>
    </div>
  );
}
