import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Card, EmptyState, ErrorBox, FullPageSpinner, Modal } from "../components/ui";
import { api, errorMessage } from "../lib/api";
import { timeAgo } from "../lib/format";
import { useAuth } from "../lib/auth";
import type { DocumentRow, DocumentUploadResult } from "../lib/types";

const DOC_TYPES = ["policy", "guide", "faq", "terms", "sop"];

const STATUS_STYLES: Record<string, string> = {
  active: "bg-emerald-100 text-emerald-700",
  flagged: "bg-rose-100 text-rose-700",
  archived: "bg-slate-200 text-slate-600",
};

interface UploadForm {
  title: string;
  doc_type: string;
  category: string;
  source_reference: string;
}

const EMPTY_FORM: UploadForm = { title: "", doc_type: "policy", category: "", source_reference: "" };

export default function DocumentsPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [items, setItems] = useState<DocumentRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [docType, setDocType] = useState("");
  const [status, setStatus] = useState("");
  const [message, setMessage] = useState("");

  const [showUpload, setShowUpload] = useState(false);
  const [form, setForm] = useState<UploadForm>(EMPTY_FORM);
  const [file, setFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [busyId, setBusyId] = useState<number | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await api<DocumentRow[]>("/api/documents", {
        query: { doc_type: docType || undefined, status: status || undefined },
      });
      setItems(data);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [docType, status]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleUpload(event: FormEvent) {
    event.preventDefault();
    if (!file) {
      setUploadError("Choose a file to upload (PDF, DOCX, MD or TXT).");
      return;
    }
    setUploading(true);
    setUploadError("");
    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("title", form.title);
      formData.append("doc_type", form.doc_type);
      formData.append("category", form.category);
      formData.append("source_reference", form.source_reference);
      const result = await api<DocumentUploadResult>("/api/documents/upload", { method: "POST", formData });
      setShowUpload(false);
      setForm(EMPTY_FORM);
      setFile(null);
      setMessage(
        result.quarantined
          ? `Upload stored but quarantined: injection patterns detected (${result.injection_scan.matches.join(", ")}). Its chunks are excluded from retrieval until an admin clears the flag.`
          : `Uploaded ${result.document.code} — ${result.sections} sections, ${result.chunks} chunks, ${result.page_count} pages.`,
      );
      await load();
    } catch (err) {
      setUploadError(errorMessage(err));
    } finally {
      setUploading(false);
    }
  }

  async function documentAction(id: number, action: "clear-flag" | "archive") {
    setBusyId(id);
    setMessage("");
    try {
      await api(`/api/documents/${id}/${action}`, { method: "POST" });
      setMessage(action === "clear-flag" ? "Flag cleared — chunks restored to approved trust." : "Document archived.");
      await load();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusyId(null);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-slate-800">Knowledge base</h1>
          <p className="text-sm text-slate-500">
            Policy documents with traceable chunks. Only approved chunks are used by retrieval.
          </p>
        </div>
        {isAdmin && (
          <button type="button" className="btn btn-primary" onClick={() => setShowUpload(true)}>
            Upload document
          </button>
        )}
      </div>

      {message && (
        <p className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-700">{message}</p>
      )}

      <Card>
        <div className="flex flex-wrap items-end gap-3">
          <div>
            <label className="label">Type</label>
            <select className="input mt-1" value={docType} onChange={(event) => setDocType(event.target.value)}>
              <option value="">All types</option>
              {DOC_TYPES.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Status</label>
            <select className="input mt-1" value={status} onChange={(event) => setStatus(event.target.value)}>
              <option value="">All statuses</option>
              <option value="active">Active</option>
              <option value="flagged">Flagged</option>
              <option value="archived">Archived</option>
            </select>
          </div>
        </div>
      </Card>

      {error && <ErrorBox message={error} onRetry={() => void load()} />}

      <Card>
        {loading ? (
          <FullPageSpinner />
        ) : items.length === 0 ? (
          <EmptyState title="No documents" hint="Upload a policy document to populate the knowledge base." />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-100">
                  <th className="table-th">Code</th>
                  <th className="table-th">Title</th>
                  <th className="table-th">Type</th>
                  <th className="table-th">Status</th>
                  <th className="table-th">Version</th>
                  <th className="table-th">Chunks</th>
                  <th className="table-th">Updated</th>
                  <th className="table-th">Actions</th>
                </tr>
              </thead>
              <tbody>
                {items.map((document) => (
                  <tr key={document.id} className="border-b border-slate-50 hover:bg-slate-50">
                    <td className="table-td font-mono text-xs text-brand-600">{document.code}</td>
                    <td className="table-td max-w-[280px]">
                      <span className="block truncate">{document.title}</span>
                      <span className="block truncate font-mono text-xs text-slate-400">{document.source_reference}</span>
                    </td>
                    <td className="table-td">{document.doc_type}</td>
                    <td className="table-td">
                      <span className={`chip ${STATUS_STYLES[document.status] || "bg-slate-100 text-slate-600"}`}>
                        {document.status}
                      </span>
                      {document.injection_flag && (
                        <span className="chip ml-1 bg-rose-100 text-rose-700" title={document.injection_notes}>
                          injection
                        </span>
                      )}
                    </td>
                    <td className="table-td">{document.current_version}</td>
                    <td className="table-td">
                      {document.chunk_count ?? "—"}
                      <span className="text-xs text-slate-400"> / {document.version_count ?? 1} versions</span>
                    </td>
                    <td className="table-td whitespace-nowrap text-xs text-slate-500">{timeAgo(document.updated_at)}</td>
                    <td className="table-td">
                      <div className="flex flex-wrap gap-1.5">
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          onClick={() => navigate(`/documents/${document.id}`)}
                        >
                          Open
                        </button>
                        {isAdmin && document.status === "flagged" && (
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            disabled={busyId === document.id}
                            onClick={() => void documentAction(document.id, "clear-flag")}
                          >
                            Clear flag
                          </button>
                        )}
                        {isAdmin && document.status !== "archived" && (
                          <button
                            type="button"
                            className="btn btn-secondary btn-sm"
                            disabled={busyId === document.id}
                            onClick={() => void documentAction(document.id, "archive")}
                          >
                            Archive
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Modal open={showUpload} title="Upload a knowledge base document" onClose={() => setShowUpload(false)}>
        <form className="space-y-4" onSubmit={handleUpload}>
          <div>
            <label className="label">File * (PDF, DOCX, MD, TXT — max size enforced by backend)</label>
            <input
              type="file"
              required
              className="input mt-1"
              onChange={(event) => setFile(event.target.files?.[0] || null)}
            />
          </div>
          <div>
            <label className="label">Title *</label>
            <input
              className="input mt-1"
              required
              value={form.title}
              onChange={(event) => setForm({ ...form, title: event.target.value })}
              placeholder="e.g. Returns & Refunds Addendum"
            />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className="label">Document type</label>
              <select
                className="input mt-1"
                value={form.doc_type}
                onChange={(event) => setForm({ ...form, doc_type: event.target.value })}
              >
                {DOC_TYPES.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="label">Category</label>
              <input
                className="input mt-1"
                value={form.category}
                onChange={(event) => setForm({ ...form, category: event.target.value })}
                placeholder="e.g. Billing"
              />
            </div>
          </div>
          <div>
            <label className="label">Source reference</label>
            <input
              className="input mt-1"
              value={form.source_reference}
              onChange={(event) => setForm({ ...form, source_reference: event.target.value })}
              placeholder="e.g. supportnova/kb/returns_addendum.md (defaults to the title)"
            />
          </div>

          {uploadError && <ErrorBox message={uploadError} />}

          <div className="flex justify-end gap-2">
            <button type="button" className="btn btn-secondary" onClick={() => setShowUpload(false)}>
              Cancel
            </button>
            <button type="submit" className="btn btn-primary" disabled={uploading}>
              {uploading ? "Uploading…" : "Upload & process"}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
