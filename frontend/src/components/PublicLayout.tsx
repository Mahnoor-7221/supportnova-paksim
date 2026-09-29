import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Link, NavLink, useLocation } from "react-router-dom";
import { useAuth } from "../lib/auth";

const NAV = [
  { to: "/features", label: "Features" },
  { to: "/how-it-works", label: "How it works" },
  { to: "/policies", label: "Policies" },
];

export default function PublicLayout({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [open, setOpen] = useState(false);
  const loc = useLocation();

  useEffect(() => { setOpen(false); window.scrollTo(0, 0); }, [loc.pathname]);

  return (
    <div className="lp-shell pp-shell">
      <div className="lp-orb lp-orb-1" />
      <div className="lp-orb lp-orb-2" />
      <div className="lp-orb lp-orb-3" />

      <header className="lp-header pp-header">
        <Link to="/" className="lp-brand">
          <span className="nova-mark">✦</span>
          <span><strong>PakSim</strong><small>Customer Support</small></span>
        </Link>
        <nav className={`pp-nav ${open ? "is-open" : ""}`} aria-label="Main">
          {NAV.map((n) => (
            <NavLink key={n.to} to={n.to} className={({ isActive }) => `lp-nav-link ${isActive ? "is-active" : ""}`}>
              {n.label}
            </NavLink>
          ))}
          <div className="pp-nav-actions">
            {user ? (
              <Link to="/" className="btn btn-primary btn-sm">Open dashboard</Link>
            ) : (
              <>
                <Link to="/login" className="btn btn-secondary btn-sm">Login</Link>
                <Link to="/signup" className="btn btn-primary btn-sm">Create account</Link>
              </>
            )}
          </div>
        </nav>
        <button type="button" className="pp-burger" aria-label="Toggle menu" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          <span /><span /><span />
        </button>
      </header>

      <main className="pp-main">{children}</main>

      <footer className="lp-footer">
        <span>PakSim support guidance is general information, not a promise about any specific account.</span>
        <span>Human governed · Secure · Traceable · © 2026 PakSim Communications</span>
      </footer>
    </div>
  );
}
