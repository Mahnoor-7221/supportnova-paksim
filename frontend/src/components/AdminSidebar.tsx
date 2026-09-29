import { NavLink } from "react-router-dom";

const SECTIONS = [
  { to: "/", label: "Dashboard", end: true, icon: "◉" },
  { to: "/complaints", label: "Complaints", icon: "☰" },
  { to: "/orders", label: "Orders", icon: "▦" },
  { to: "/sims", label: "Registered SIMs", icon: "◈" },
  { to: "/admin/users", label: "Customers", icon: "☺" },
  { to: "/admin/agents", label: "Agents", icon: "◇" },
  { to: "/admin/departments", label: "Departments", icon: "▦" },
  { to: "/admin/categories", label: "Categories & SLA", icon: "◇" },
  { to: "/documents", label: "Knowledge Base", icon: "▤" },
  { to: "/review", label: "AI Review", icon: "✦" },
  { to: "/reports", label: "Reports", icon: "▣" },
  { to: "/security", label: "Security", icon: "⬡" },
  { to: "/admin/audit", label: "Audit Logs", icon: "◎" },
  { to: "/admin/settings", label: "Settings", icon: "⚙" },
];

export default function AdminSidebar({ collapsed, onToggle }: { collapsed?: boolean; onToggle?: () => void }) {
  return (
    <aside className={`adm-sidebar ${collapsed ? "is-collapsed" : ""}`}>
      <div className="adm-sidebar-head">
        <NavLink to="/" className="adm-sidebar-brand">
          <span className="nova-mark">✦</span>
          {!collapsed && (
            <span>
              <strong>PakSim</strong>
              <small>Admin Console</small>
            </span>
          )}
        </NavLink>
        {onToggle && (
          <button type="button" className="adm-collapse-btn" onClick={onToggle} aria-label="Toggle sidebar">
            {collapsed ? "»" : "«"}
          </button>
        )}
      </div>
      <nav className="adm-sidebar-nav" aria-label="Admin navigation">
        {SECTIONS.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) => `adm-nav-item ${isActive ? "is-active" : ""}`}
            title={item.label}
          >
            <span className="adm-nav-icon">{item.icon}</span>
            {!collapsed && <span className="adm-nav-label">{item.label}</span>}
          </NavLink>
        ))}
      </nav>
      <div className="adm-sidebar-foot">
        {!collapsed && <span>Human governed · Secure</span>}
      </div>
    </aside>
  );
}
