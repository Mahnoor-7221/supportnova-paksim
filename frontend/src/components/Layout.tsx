import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useState } from "react";
import { isStaffRole, useAuth } from "../lib/auth";
import AdminSidebar from "./AdminSidebar";
import AgentSidebar from "./AgentSidebar";

interface NavItem {
  to: string;
  label: string;
  end?: boolean;
}

function NavList({ items }: { items: NavItem[] }) {
  return (
    <nav className="nova-nav" aria-label="Primary navigation">
      {items.map((item) => (
        <NavLink
          key={`${item.to}-${item.label}`}
          to={item.to}
          end={item.end}
          className={({ isActive }) => `nova-nav-link ${isActive ? "is-active" : ""}`}
        >
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}

function StaffShell({
  roleLabel,
  Sidebar,
  user,
  logout,
  navigate,
}: {
  roleLabel: string;
  Sidebar: React.ComponentType<{ collapsed?: boolean; onToggle?: () => void }>;
  user: { full_name?: string; email?: string } | null;
  logout: () => void;
  navigate: (path: string) => void;
}) {
  const [search, setSearch] = useState("");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  return (
    <div className="adm-shell">
      <Sidebar collapsed={sidebarCollapsed} onToggle={() => setSidebarCollapsed((c) => !c)} />
      <div className="adm-main">
        <header className="adm-topbar">
          <form
            className="adm-search"
            onSubmit={(e) => {
              e.preventDefault();
              if (search.trim()) navigate(`/complaints?q=${encodeURIComponent(search.trim())}`);
            }}
          >
            <span>⌕</span>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search complaints, cases, customers…"
              aria-label="Search"
            />
          </form>
          <div className="adm-topbar-right">
            <span className="nova-role">{roleLabel}</span>
            <span className="nova-avatar">{(user?.full_name || roleLabel).charAt(0).toUpperCase()}</span>
            <div className="nova-user-copy">
              <strong>{user?.full_name || roleLabel}</strong>
              <small>{user?.email}</small>
            </div>
            <button
              className="nova-signout"
              type="button"
              onClick={() => {
                logout();
                navigate("/login");
              }}
            >
              Sign out
            </button>
          </div>
        </header>
        <main className="adm-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export default function Layout() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const role = user?.role || "";
  const isStaff = isStaffRole(role);
  const isAdmin = role === "admin";

  // ── Admin: dedicated sidebar layout ──
  if (isAdmin) {
    return (
      <StaffShell
        roleLabel="admin"
        Sidebar={AdminSidebar}
        user={user}
        logout={logout}
        navigate={navigate}
      />
    );
  }

  // ── Agent: dedicated sidebar layout (professional workspace) ──
  if (isStaff) {
    return (
      <StaffShell
        roleLabel="agent"
        Sidebar={AgentSidebar}
        user={user}
        logout={logout}
        navigate={navigate}
      />
    );
  }

  // ── Customer: top-nav layout ──
  const [search, setSearch] = useState("");
  const items: NavItem[] = [
    { to: "/", label: "Nova", end: true },
    { to: "/services", label: "Services" },
    { to: "/sims", label: "My SIMs" },
    { to: "/packages", label: "Packages" },
    { to: "/complaints", label: "Complaints" },
    { to: "/orders", label: "Activity" },
    { to: "/profile", label: "Profile" },
  ];

  function handleLogout() {
    logout();
    navigate("/login");
  }

  return (
    <div className="nova-shell">
      <div className="nova-ambient nova-ambient-one" />
      <div className="nova-ambient nova-ambient-two" />

      <header className="nova-header">
        <div className="nova-header-inner">
          <NavLink to="/" className="nova-brand" aria-label="PakSim home">
            <span className="nova-mark">✦</span>
            <span>
              <strong>PakSim</strong>
              <small>Customer Support Intelligence</small>
            </span>
          </NavLink>

          <form
            className="nova-search customer-search"
            onSubmit={(e) => {
              e.preventDefault();
              if (search.trim()) navigate(`/complaints?q=${encodeURIComponent(search.trim())}`);
            }}
            aria-label="Search PakSim support"
          >
            <span>⌕</span>
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search my complaints…"
              aria-label="Search"
            />
            <button type="submit">Search</button>
          </form>

          <div className="nova-userbar">
            <span className="nova-role">{role || "user"}</span>
            <NavLink to="/profile" className="nova-avatar" aria-label="Open profile">
              {(user?.full_name || "U").charAt(0).toUpperCase()}
            </NavLink>
            <div className="nova-user-copy">
              <strong>{user?.full_name || "User"}</strong>
              <small>{user?.email}</small>
            </div>
            <button className="nova-signout" onClick={handleLogout} type="button">
              Sign out
            </button>
          </div>
        </div>
      </header>

      <div className="nova-nav-wrap">
        <div className="nova-nav-inner">
          <NavList items={items} />
          <div className="nova-live-pill">
            <span /> Nova online
          </div>
        </div>
      </div>

      <main className="nova-main">
        <div className="nova-content">
          <Outlet />
        </div>
      </main>

      <footer className="nova-footer">
        <div className="nova-footer-brand">
          <span className="nova-footer-mark">✦</span>
          <div>
            <strong>PakSim</strong>
            <small>Customer Support Intelligence</small>
          </div>
        </div>
        <div className="nova-footer-links">
          <NavLink to="/">Support Home</NavLink>
          <NavLink to="/complaints">My Complaints</NavLink>
          <NavLink to="/track">Track Complaint</NavLink>
          <NavLink to="/chat-history">Chat History</NavLink>
          <NavLink to="/profile">Profile</NavLink>
        </div>
        <div className="nova-footer-note">
          <span>AI-assisted · Human governed</span>
          <small>© 2026 PakSim Communications</small>
        </div>
      </footer>
    </div>
  );
}
