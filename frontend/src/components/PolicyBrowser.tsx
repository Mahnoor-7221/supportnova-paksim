import { useMemo, useState } from "react";
import data from "../data/publicPolicies.json";

type Policy = { id: string; category: string; title: string; guidance: string; escalates: boolean; kb_ref: string };
const ALL: Policy[] = (data as { policies: Policy[] }).policies;
const CATS = Array.from(new Set(ALL.map((p) => p.category)));

export const POLICY_COUNT = ALL.length;
export const POLICY_PREVIEW = ALL.filter((p) => p.id.endsWith("-01")).slice(0, 6);

export function PolicyCard({ p }: { p: Policy }) {
  return (
    <article className="pp-policy">
      <div className="pp-policy-top">
        <span className="pp-chip">{p.category}</span>
        {p.escalates && <span className="pp-chip pp-chip-gold" title="Handled by a human agent">Human review</span>}
      </div>
      <h3>{p.title}</h3>
      <p>{p.guidance}</p>
      <small>{p.id} · ref {p.kb_ref}</small>
    </article>
  );
}

/** Searchable + category-filterable list of every public policy. */
export default function PolicyBrowser({ compact = false }: { compact?: boolean }) {
  const [q, setQ] = useState("");
  const [cat, setCat] = useState("All");
  const [onlyHuman, setOnlyHuman] = useState(false);

  const list = useMemo(() => {
    const s = q.trim().toLowerCase();
    return ALL.filter(
      (p) =>
        (cat === "All" || p.category === cat) &&
        (!onlyHuman || p.escalates) &&
        (!s || `${p.title} ${p.guidance} ${p.category} ${p.id}`.toLowerCase().includes(s)),
    );
  }, [q, cat, onlyHuman]);

  return (
    <div className={`pp-browser ${compact ? "is-compact" : ""}`}>
      <div className="pp-toolbar">
        <input
          className="pp-search"
          type="search"
          placeholder={`Search ${ALL.length}+ policies…`}
          value={q}
          onChange={(e) => setQ(e.target.value)}
          aria-label="Search policies"
        />
        <label className="pp-toggle">
          <input type="checkbox" checked={onlyHuman} onChange={(e) => setOnlyHuman(e.target.checked)} />
          Human-review cases only
        </label>
      </div>
      <div className="pp-filters" role="tablist" aria-label="Policy categories">
        {["All", ...CATS].map((c) => (
          <button key={c} type="button" className={`pp-filter ${cat === c ? "is-active" : ""}`} onClick={() => setCat(c)}>
            {c}
          </button>
        ))}
      </div>
      <p className="pp-count" aria-live="polite">Showing {list.length} of {ALL.length} policies</p>
      {list.length === 0 ? (
        <div className="pp-empty">No policy matches your search. Try another word or ask Nova.</div>
      ) : (
        <div className="pp-policy-grid">{list.map((p) => <PolicyCard key={p.id} p={p} />)}</div>
      )}
    </div>
  );
}
