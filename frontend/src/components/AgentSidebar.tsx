import { NavLink, useLocation } from "react-router-dom";

const SECTIONS = [
  { to: "/", label: "My Dashboard", end: true, icon: "⌂" },
  { to: "/agent/complaints?filter=urgent", label: "Urgent Queue", icon: "!" },
  { to: "/agent/complaints", label: "My Complaints", icon: "≡" },
  { to: "/agent/complaints?filter=pending", label: "Pending", icon: "●" },
  { to: "/agent/complaints?filter=in_progress", label: "In Progress", icon: "↻" },
  { to: "/agent/complaints?filter=waiting", label: "Waiting for Customer", icon: "◷" },
  { to: "/agent/complaints?filter=escalated", label: "Escalated", icon: "↑" },
  { to: "/agent/complaints?filter=resolved", label: "Resolved", icon: "✓" },
  { to: "/documents", label: "Knowledge Base", icon: "▤" },
];

export default function AgentSidebar({ collapsed, onToggle }: { collapsed?: boolean; onToggle?: () => void }) {
  const location = useLocation();
  // NavLink ignores ?filter=..., so every queue looked active. Compare path + filter ourselves.
  const isItemActive = (to: string, end?: boolean) => {
    const [path, qs] = to.split("?");
    if (end) return location.pathname === path;
    if (!location.pathname.startsWith(path)) return false;
    if (path !== "/agent/complaints") return true;
    const want = new URLSearchParams(qs || "").get("filter") || "";
    const have = new URLSearchParams(location.search).get("filter") || "";
    return want === have;
  };
  return (
    <aside className={`adm-sidebar agent-sidebar ${collapsed ? "is-collapsed" : ""}`}>
      <div className="adm-sidebar-head">
        <NavLink to="/" className="adm-sidebar-brand">
          <span className="nova-mark">✦</span>
          {!collapsed && <span><strong>PakSim</strong><small>Agent Workspace</small></span>}
        </NavLink>
        {onToggle && <button type="button" className="adm-collapse-btn" onClick={onToggle} aria-label="Toggle sidebar">{collapsed ? "»" : "«"}</button>}
      </div>
      <nav className="adm-sidebar-nav agent-nav" aria-label="Agent navigation">
        {SECTIONS.map((item) => <NavLink key={item.to} to={item.to} end={item.end} className={() => `adm-nav-item ${isItemActive(item.to, item.end) ? "is-active" : ""}`} title={item.label}>
          <span className="adm-nav-icon">{item.icon}</span>{!collapsed && <span className="adm-nav-label">{item.label}</span>}
        </NavLink>)}
      </nav>
      <div className="agent-sidebar-help">{!collapsed && <><strong>Human support workspace</strong><span>Focus on assigned customers, urgency and resolution.</span></>}</div>
      <div className="adm-sidebar-foot">{!collapsed && <span>Customer first · Human governed</span>}</div>
    </aside>
  );
}
