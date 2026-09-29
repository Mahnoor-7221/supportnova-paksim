// Small presentation helpers shared across pages.

export function titleCase(value: string): string {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function formatDateTime(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDate(value?: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "2-digit" });
}

export function timeAgo(value?: string | null): string {
  if (!value) return "—";
  const timestamp = new Date(value).getTime();
  if (Number.isNaN(timestamp)) return "—";
  const seconds = Math.floor((Date.now() - timestamp) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days}d ago`;
  return formatDate(value);
}

export function formatBytes(bytes?: number | null): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const index = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)));
  const value = bytes / Math.pow(1024, index);
  return `${value.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

export function triggerLabel(trigger: unknown): string {
  if (typeof trigger === "string") return titleCase(trigger);
  if (trigger && typeof trigger === "object") {
    const record = trigger as Record<string, unknown>;
    const name = typeof record.trigger === "string" ? record.trigger
      : typeof record.name === "string" ? record.name : "";
    const reason = typeof record.reason === "string" ? record.reason : "";
    if (name && reason && name !== reason) return `${titleCase(name)}: ${reason}`;
    if (name) return titleCase(name);
    if (reason) return reason;
    return JSON.stringify(trigger);
  }
  return String(trigger ?? "");
}

export const STATUS_STYLES: Record<string, string> = {
  WAITING_CUSTOMER: "bg-amber-100 text-amber-800",
  PENDING: "bg-orange-100 text-orange-800",
  NEW: "bg-sky-100 text-sky-700",
  ANALYZING: "bg-amber-100 text-amber-700",
  ANALYZED: "bg-emerald-100 text-emerald-700",
  VALIDATION_FAILED: "bg-rose-100 text-rose-700",
  MANUAL_REVIEW: "bg-amber-100 text-amber-800",
  ESCALATED: "bg-purple-100 text-purple-700",
  IN_PROGRESS: "bg-indigo-100 text-indigo-700",
  RESOLVED: "bg-emerald-100 text-emerald-800",
  CLOSED: "bg-slate-200 text-slate-600",
};

export const VERIFICATION_STYLES: Record<string, string> = {
  VERIFIED: "bg-emerald-100 text-emerald-700",
  VERIFIED_WITH_WARNING: "bg-amber-100 text-amber-700",
  MISMATCH: "bg-rose-100 text-rose-700",
  MANUAL_REVIEW_REQUIRED: "bg-orange-100 text-orange-700",
  FAILED: "bg-rose-200 text-rose-800",
};

export const URGENCY_STYLES: Record<string, string> = {
  Low: "bg-slate-100 text-slate-600",
  Medium: "bg-sky-100 text-sky-700",
  High: "bg-amber-100 text-amber-700",
  Critical: "bg-rose-100 text-rose-700",
};

export const CHECK_STYLES: Record<string, string> = {
  OK: "bg-emerald-100 text-emerald-700",
  WARNING: "bg-amber-100 text-amber-700",
  FAIL: "bg-rose-100 text-rose-700",
};

export const DECISION_STYLES: Record<string, string> = {
  VERIFIED: "bg-emerald-100 text-emerald-700",
  REVIEW_REQUIRED: "bg-amber-100 text-amber-700",
  BLOCKED: "bg-rose-100 text-rose-700",
};

export const SEVERITY_STYLES: Record<string, string> = {
  critical: "bg-rose-100 text-rose-700",
  high: "bg-orange-100 text-orange-700",
  medium: "bg-amber-100 text-amber-700",
  low: "bg-slate-100 text-slate-600",
  info: "bg-sky-100 text-sky-700",
};

export const MATCH_STYLES: Record<string, string> = {
  MATCH: "bg-emerald-100 text-emerald-700",
  MISMATCH: "bg-rose-100 text-rose-700",
  MANUAL_REVIEW: "bg-amber-100 text-amber-700",
  UNKNOWN: "bg-slate-100 text-slate-600",
};

export function statusClass(status?: string | null): string {
  return STATUS_STYLES[status || ""] || "bg-slate-100 text-slate-600";
}

export function verificationClass(status?: string | null): string {
  return VERIFICATION_STYLES[status || ""] || "bg-slate-100 text-slate-600";
}

export function urgencyClass(urgency?: string | null): string {
  return URGENCY_STYLES[urgency || ""] || "bg-slate-100 text-slate-600";
}

export function checkClass(status?: string | null): string {
  return CHECK_STYLES[status || ""] || "bg-slate-100 text-slate-600";
}

export function matchClass(match?: string | null): string {
  return MATCH_STYLES[match || ""] || "bg-slate-100 text-slate-600";
}

export function decisionClass(decision?: string | null): string {
  return DECISION_STYLES[decision || ""] || "bg-slate-100 text-slate-600";
}

export function severityClass(severity?: string | null): string {
  return SEVERITY_STYLES[(severity || "").toLowerCase()] || "bg-slate-100 text-slate-600";
}

// Shared score → colour ramp used by the Trust Gate and Risk Radar.
export function scoreBarClass(score: number): string {
  if (score >= 90) return "bg-emerald-500";
  if (score >= 70) return "bg-amber-500";
  return "bg-rose-500";
}
