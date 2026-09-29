import type { ReactNode } from "react";
import {
  checkClass,
  decisionClass,
  matchClass,
  severityClass,
  statusClass,
  urgencyClass,
  verificationClass,
} from "../lib/format";

export function Spinner({ className = "h-5 w-5" }: { className?: string }) {
  return (
    <svg className={`${className} animate-spin text-slate-400`} viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 0 1 8-8v4a4 4 0 0 0-4 4H4z" />
    </svg>
  );
}

export function FullPageSpinner() {
  return (
    <div className="flex h-screen items-center justify-center">
      <Spinner className="h-8 w-8" />
    </div>
  );
}

export function Card({
  title,
  actions,
  children,
  className = "",
}: {
  title?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-700">{title}</h2>
          {actions}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  );
}

const STAT_TONES: Record<string, string> = {
  slate: "text-slate-800",
  brand: "text-brand-600",
  emerald: "text-emerald-600",
  amber: "text-amber-600",
  rose: "text-rose-600",
  purple: "text-purple-600",
  sky: "text-sky-600",
};

export function StatCard({
  label,
  value,
  tone = "slate",
  hint,
}: {
  label: string;
  value: ReactNode;
  tone?: string;
  hint?: string;
}) {
  return (
    <div className="card px-4 py-3">
      <p className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${STAT_TONES[tone] || STAT_TONES.slate}`}>{value}</p>
      {hint && <p className="mt-0.5 text-xs text-slate-400">{hint}</p>}
    </div>
  );
}

export function Badge({ label, className = "" }: { label: string; className?: string }) {
  return <span className={`chip ${className || "bg-slate-100 text-slate-600"}`}>{label}</span>;
}

export function StatusBadge({ status }: { status?: string | null }) {
  if (!status) return <span className="text-slate-400">—</span>;
  return <Badge label={status.replace(/_/g, " ")} className={statusClass(status)} />;
}

export function VerificationBadge({ status }: { status?: string | null }) {
  if (!status) return <span className="text-slate-400">—</span>;
  return <Badge label={status.replace(/_/g, " ")} className={verificationClass(status)} />;
}

export function UrgencyBadge({ urgency }: { urgency?: string | null }) {
  if (!urgency) return <span className="text-slate-400">—</span>;
  return <Badge label={urgency} className={urgencyClass(urgency)} />;
}

export function CheckBadge({ status }: { status?: string | null }) {
  return <Badge label={status || "—"} className={checkClass(status)} />;
}

export function TrustBadge({ decision }: { decision?: string | null }) {
  if (!decision) return <span className="text-slate-400">—</span>;
  return <Badge label={decision.replace(/_/g, " ")} className={decisionClass(decision)} />;
}

export function SeverityBadge({ severity }: { severity?: string | null }) {
  if (!severity) return <span className="text-slate-400">—</span>;
  return <Badge label={severity} className={severityClass(severity)} />;
}

export function MatchBadge({ match }: { match?: string | null }) {
  if (!match) return <span className="text-slate-400">—</span>;
  return <Badge label={match.replace(/_/g, " ")} className={matchClass(match)} />;
}

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
      <span>{message}</span>
      {onRetry && (
        <button type="button" className="btn btn-secondary btn-sm" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="py-10 text-center">
      <p className="text-sm font-medium text-slate-500">{title}</p>
      {hint && <p className="mt-1 text-xs text-slate-400">{hint}</p>}
    </div>
  );
}

export function Modal({
  open,
  title,
  onClose,
  children,
  footer,
  wide = false,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  wide?: boolean;
}) {
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 p-4"
      onClick={onClose}
    >
      <div
        className={`max-h-[88vh] w-full overflow-auto rounded-xl bg-white shadow-xl ${wide ? "max-w-4xl" : "max-w-2xl"}`}
        onClick={(event) => event.stopPropagation()}
      >
        <header className="flex items-center justify-between border-b border-slate-100 px-4 py-3">
          <h3 className="text-sm font-semibold text-slate-700">{title}</h3>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
            aria-label="Close"
          >
            ✕
          </button>
        </header>
        <div className="px-4 py-4">{children}</div>
        {footer && <footer className="border-t border-slate-100 px-4 py-3">{footer}</footer>}
      </div>
    </div>
  );
}

export function Pagination({
  page,
  pageSize,
  total,
  onPage,
}: {
  page: number;
  pageSize: number;
  total: number;
  onPage: (page: number) => void;
}) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (total === 0) return null;
  return (
    <div className="flex items-center justify-between pt-3 text-sm text-slate-500">
      <span>
        {total} total · page {page} of {pages}
      </span>
      <div className="flex gap-2">
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
        >
          Previous
        </button>
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          disabled={page >= pages}
          onClick={() => onPage(page + 1)}
        >
          Next
        </button>
      </div>
    </div>
  );
}

export function KeyValue({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <dt className="text-xs font-medium uppercase tracking-wide text-slate-400">{label}</dt>
      <dd className="mt-0.5 text-sm text-slate-700">{value}</dd>
    </div>
  );
}

export function SectionList({
  title,
  items,
  emptyText = "None",
}: {
  title: string;
  items?: (string | unknown)[] | null;
  emptyText?: string;
}) {
  const rows = (items || []).map((item) =>
    typeof item === "string" ? item : JSON.stringify(item),
  );
  return (
    <div>
      <p className="text-xs font-medium uppercase tracking-wide text-slate-400">{title}</p>
      {rows.length === 0 ? (
        <p className="mt-1 text-sm text-slate-400">{emptyText}</p>
      ) : (
        <ul className="mt-1 list-inside list-disc space-y-1 text-sm text-slate-700">
          {rows.map((row, index) => (
            <li key={index}>{row}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
