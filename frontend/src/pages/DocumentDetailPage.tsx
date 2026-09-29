import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Card, EmptyState, ErrorBox, FullPageSpinner, KeyValue, Modal } from "../components/ui";
import { api, errorMessage } from "../lib/api";
import { formatBytes, formatDateTime } from "../lib/format";
import { useAuth } from "../lib/auth";
import type { DocumentDetail, DocumentVersionUploadResult } from "../lib/types";

const CHUNK_PAGE_SIZE = 25;

const STATUS_STYLES: Record<string, string> = {
  active: "bg-emerald-100 text-emerald-700",
  flagged: "bg-rose-100 text-rose-700",
  archived: "bg-slate-200 text-slate-600",
};

export default function DocumentDetailPage() {
  const { id } = useParams();
  const documentId = Number(id);
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";

  const [detail, setDetail] = useState<DocumentDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [chunkOffset, setChunkOffset] = useState(0);
  const [expandedChunk, setExpandedChunk] = useState<number | null>(null);
  const [message, setMessage] = useState("");
  const [actionError, setActionError] = useState("");
  const [busy, setBusy] = useState(false);
  const [showVersion, setShowVersion] = useState(false);
  const [versionFile, setVersionFile] = useState<File | null>(null);
  const [versionError, setVersionError] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await api<DocumentDetail>(`/api/documents/${documentId}`, {
        query: { chunk_offset: chunkOffset, chunk_limit: CHUNK_PAGE_SIZE },
      });
      setDetail(data);
      setExpandedChunk(null);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, [documentId, chunkOffset]);

  useEffect(() => {
    void load();
  }, [load]);

  async function documentAction(action: "clear-flag" | "archive") {
    setBusy(true);
    setActionError("");
    try {
      await api(`/api/documents/${documentId}/${action}`, { method: "POST" });
      setMessage(action === "clear-flag" ? "Flag cleared — all chunks restored to approved trust." : "Document archived.");
      await load();
    } catch (err) {
      setActionError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function uploadVersion() {
    if (!versionFile) {
      setVersionError("Choose a file for the new version.");
      return;
    }
    setBusy(true);
    setVersionError("");
    try {
      const formData = new FormData();
      formData.append("file", versionFile);
      const result = await api<DocumentVersionUploadResult>(`/api/documents/${documentId}/version`, {
        method: "POST",
        formData,
      });
      setShowVersion(false);
      setVersionFile(null);
      setMessage(
        `Version ${result.version} ingested — ${result.sections} sections, ${result.chunks} chunks${
          result.injection_scan.suspected ? " (injection patterns detected in the new version)" : ""
        }.`,
      );
      await load();
    } catch (err) {
      setVersionError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  if (loading && !detail) return <FullPageSpinner />;
  if (error) return <ErrorBox message={error} onRetry={() => void load()} />;
  if (!detail) return null;

  const { document, versions, chunks, total_chunks } = detail;
  const chunkPages = Math.max(1, Math.ceil(total_chunks / CHUNK_PAGE_SIZE));
  const currentPage = Math.floor(chunkOffset / CHUNK_PAGE_SIZE) + 1;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <Link to="/documents" className="text-sm text-brand-600 hover:underline">
            ← Knowledge base
          </Link>
          <span className="font-mono text-sm text-slate-400">{document.code}</span>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <span className={`chip ${STATUS_STYLES[document.status] || "bg-slate-100 text-slate-600"}`}>
            {document.status}
          </span>
          {document.injection_flag && (
            <span className="chip bg-rose-100 text-rose-700" title={document.injection_notes}>
              injection flagged
            </span>
          )}
        </div>
      </div>

      {message && (
        <p className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm text-emerald-700">{message}</p>
      )}
      {actionError && <ErrorBox message={actionError} />}

      <Card
        title={document.title}
        actions={
          isAdmin ? (
            <div className="flex flex-wrap gap-2">
              <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={() => setShowVersion(true)}>
                New version
              </button>
              {document.status === "flagged" && (
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={busy}
                  onClick={() => void documentAction("clear-flag")}
                >
                  Clear flag
                </button>
              )}
              {document.status !== "archived" && (
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  disabled={busy}
                  onClick={() => void documentAction("archive")}
                >
                  Archive
                </button>
              )}
            </div>
          ) : undefined
        }
      >
        <div className="grid gap-4 md:grid-cols-4">
          <KeyValue label="Type" value={document.doc_type} />
          <KeyValue label="Category" value={document.category || "—"} />
          <KeyValue label="Current version" value={document.current_version} />
          <KeyValue label="Source reference" value={<span className="font-mono text-xs">{document.source_reference}</span>} />
          <KeyValue label="Chunks" value={`${total_chunks} total`} />
          <KeyValue label="Created" value={formatDateTime(document.created_at)} />
          <KeyValue label="Updated" value={formatDateTime(document.updated_at)} />
        </div>
        {document.injection_notes && (
          <p className="mt-3 rounded-lg bg-amber-50 px-3 py-2 text-sm text-amber-800">
            Injection notes: {document.injection_notes}
          </p>
        )}
      </Card>

      <Card title={`Versions (${versions.length})`}>
        {versions.length === 0 ? (
          <EmptyState title="No versions recorded" />
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-100">
                  <th className="table-th">Version</th>
                  <th className="table-th">File</th>
                  <th className="table-th">Size</th>
                  <th className="table-th">Pages</th>
                  <th className="table-th">Checksum</th>
                  <th className="table-th">Effective</th>
                  <th className="table-th">Current</th>
                </tr>
              </thead>
              <tbody>
                {versions.map((version) => (
                  <tr key={version.id} className="border-b border-slate-50">
                    <td className="table-td font-medium">{version.version}</td>
                    <td className="table-td max-w-[240px] truncate">{version.file_name}</td>
                    <td className="table-td whitespace-nowrap">{formatBytes(version.size_bytes)}</td>
                    <td className="table-td">{version.page_count}</td>
                    <td className="table-td font-mono text-xs text-slate-500">{version.checksum.slice(0, 12)}…</td>
                    <td className="table-td whitespace-nowrap text-xs text-slate-500">{formatDateTime(version.effective_date)}</td>
                    <td className="table-td">
                      {version.is_current ? (
                        <span className="chip bg-emerald-100 text-emerald-700">current</span>
                      ) : (
                        <span className="chip bg-slate-100 text-slate-500">archived</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <Card
        title={`Chunks (${total_chunks})`}
        actions={
          total_chunks > CHUNK_PAGE_SIZE ? (
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <span>
                page {currentPage} of {chunkPages}
              </span>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={chunkOffset <= 0}
                onClick={() => setChunkOffset(Math.max(0, chunkOffset - CHUNK_PAGE_SIZE))}
              >
                Prev
              </button>
              <button
                type="button"
                className="btn btn-secondary btn-sm"
                disabled={chunkOffset + CHUNK_PAGE_SIZE >= total_chunks}
                onClick={() => setChunkOffset(chunkOffset + CHUNK_PAGE_SIZE)}
              >
                Next
              </button>
            </div>
          ) : undefined
        }
      >
        {chunks.length === 0 ? (
          <EmptyState title="No chunks" hint="The document may still be processing." />
        ) : (
          <ul className="space-y-2">
            {chunks.map((chunk) => (
              <li key={chunk.id} className="rounded-lg border border-slate-100 p-3">
                <button
                  type="button"
                  className="flex w-full items-start justify-between gap-3 text-left"
                  onClick={() => setExpandedChunk(expandedChunk === chunk.id ? null : chunk.id)}
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="chip bg-brand-50 text-brand-700 font-mono">§ {chunk.section_id || "—"}</span>
                      <span className="text-sm font-medium text-slate-700">{chunk.section_title || "Untitled section"}</span>
                      <span className="text-xs text-slate-400">page {chunk.page}</span>
                    </div>
                    <p className="mt-1 truncate text-xs text-slate-400">source: {chunk.source_reference}</p>
                  </div>
                  <div className="flex shrink-0 items-center gap-1.5">
                    <span
                      className={`chip ${
                        chunk.trust_level === "approved" ? "bg-emerald-100 text-emerald-700" : "bg-rose-100 text-rose-700"
                      }`}
                    >
                      {chunk.trust_level}
                    </span>
                    {chunk.injection_suspected && <span className="chip bg-rose-100 text-rose-700">injection</span>}
                  </div>
                </button>
                <p className={`mt-2 whitespace-pre-wrap text-sm text-slate-600 ${expandedChunk === chunk.id ? "" : "line-clamp-2"}`}>
                  {chunk.text}
                </p>
                {expandedChunk !== chunk.id && chunk.text.length > 180 && (
                  <button
                    type="button"
                    className="mt-1 text-xs text-brand-600 hover:underline"
                    onClick={() => setExpandedChunk(chunk.id)}
                  >
                    Show full text
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Modal open={showVersion} title="Upload a new version" onClose={() => setShowVersion(false)}>
        <div className="space-y-4">
          <p className="text-sm text-slate-500">
            The new file replaces the current version for retrieval. The previous version is kept for traceability.
          </p>
          <input
            type="file"
            className="input"
            onChange={(event) => setVersionFile(event.target.files?.[0] || null)}
          />
          {versionError && <ErrorBox message={versionError} />}
          <div className="flex justify-end gap-2">
            <button type="button" className="btn btn-secondary" onClick={() => setShowVersion(false)}>
              Cancel
            </button>
            <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void uploadVersion()}>
              {busy ? "Uploading…" : "Upload version"}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
