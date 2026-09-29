// Shared rendering helpers for Nova chat bubbles: turns Nova's plain-text replies
// (numbered steps, "- " bullets, **bold**) into readable paragraphs/lists, and
// renders the escalation banner for issues that need a human agent.
// Pure text in -> React elements out; nothing is ever injected as raw HTML.

import { Link } from "react-router-dom";

export type MessageData = {
  awaiting_mobile?: boolean;
  complaint_refused?: string;
  category?: string;
  severity?: "critical" | "urgent" | "normal" | string;
  escalate?: boolean;
  escalation_reason?: string;
  complaint_code?: string;
  needs_details?: boolean;
  clarification_questions?: string[];
};

function renderInline(text: string, keyPrefix: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**")
      ? <strong key={`${keyPrefix}-${i}`}>{part.slice(2, -2)}</strong>
      : <span key={`${keyPrefix}-${i}`}>{part}</span>
  );
}

export function formatMessage(text: string) {
  const lines = (text || "").split("\n");
  const blocks: JSX.Element[] = [];
  let list: { type: "ol" | "ul"; items: string[] } | null = null;
  let para: string[] = [];

  const flushPara = () => {
    if (para.length) { blocks.push(<p key={blocks.length}>{renderInline(para.join(" "), `p${blocks.length}`)}</p>); para = []; }
  };
  const flushList = () => {
    if (list) {
      const items = list.items; const Tag = list.type;
      blocks.push(Tag === "ol"
        ? <ol key={blocks.length}>{items.map((it, i) => <li key={i}>{renderInline(it, `l${blocks.length}-${i}`)}</li>)}</ol>
        : <ul key={blocks.length}>{items.map((it, i) => <li key={i}>{renderInline(it, `l${blocks.length}-${i}`)}</li>)}</ul>);
      list = null;
    }
  };

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) { flushPara(); flushList(); continue; }
    const numbered = line.match(/^(\d+)[.)]\s+(.*)/);
    const bulleted = line.match(/^[-*•]\s+(.*)/);
    if (numbered) { flushPara(); if (!list || list.type !== "ol") { flushList(); list = { type: "ol", items: [] }; } list.items.push(numbered[2]); continue; }
    if (bulleted) { flushPara(); if (!list || list.type !== "ul") { flushList(); list = { type: "ul", items: [] }; } list.items.push(bulleted[1]); continue; }
    flushList();
    para.push(line);
  }
  flushPara(); flushList();
  return blocks.length ? blocks : [<p key="0">{text}</p>];
}

const SEVERITY_COPY: Record<string, { icon: string; title: string }> = {
  critical: { icon: "🚨", title: "Yeh masla sirf AI resolve nahi kar sakta" },
  urgent: { icon: "⏳", title: "Isay priority par dekha ja raha hai" },
};

export function EscalationBanner({ data }: { data?: MessageData }) {
  if (data?.complaint_refused === "no_sim") {
    return (
      <div className="escalation-banner urgent">
        <span className="esc-icon">📵</span>
        <div>
          <strong>PakSim SIM registered nahi hai</strong>
          <p>Complaint sirf registered PakSim SIM wale customers ke liye register hoti hai.</p>
          <Link className="esc-code" to="/services">Buy New SIM →</Link>
        </div>
      </div>
    );
  }
  if (data?.complaint_code && !data.escalate) {
    return (
      <div className="escalation-banner registered">
        <span className="esc-icon">✅</span>
        <div>
          <strong>Complaint register ho gayi</strong>
          <p>Aapki complaint save ho chuki hai aur My Complaints mein nazar aayegi.</p>
          <Link className="esc-code" to="/complaints">{data.complaint_code} · View →</Link>
        </div>
      </div>
    );
  }
  if (!data?.escalate) return null;
  const level = data.severity === "critical" ? "critical" : "urgent";
  const copy = SEVERITY_COPY[level];
  return (
    <div className={`escalation-banner ${level}`}>
      <span className="esc-icon">{copy.icon}</span>
      <div>
        <strong>{copy.title}</strong>
        <p>{data.escalation_reason || "Yeh case ek human support agent ko bhej diya gaya hai."}</p>
        {data.complaint_code && <Link className="esc-code" to="/complaints">Complaint {data.complaint_code} · View →</Link>}
      </div>
    </div>
  );
}
