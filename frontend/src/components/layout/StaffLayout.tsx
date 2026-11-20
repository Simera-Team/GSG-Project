import { useEffect } from "react";
import { LogOut, ListChecks, ShieldCheck, Files, LayoutDashboard, UsersRound, UserPlus } from "lucide-react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import type { UserRole } from "../../services/authService";
import { clearSession } from "../../services/session";
import { roleHome } from "../../services/roleAccess";
import BrandLogo from "../common/BrandLogo";
import RoleGate from "./RoleGate";
import "./CandidateLayout.css";

export default function StaffLayout({ role }: { role: Extract<UserRole, "reviewer" | "administrator"> }) {
  const location = useLocation();
  useEffect(() => { window.scrollTo(0, 0); }, [location.pathname, location.search]);
  const label = role === "administrator" ? "Admin Workspace" : "Reviewer Workspace";
  const title = location.pathname === "/admin/staff" ? "Staff Management" : location.pathname === "/admin/dashboard" ? "Dashboard" : location.pathname.startsWith("/admin/candidates/") ? "Candidate Details" : location.pathname === "/admin/candidates" ? "Candidate Management" : location.pathname.startsWith("/admin/documents/") ? "Document Details" : location.pathname === "/admin/documents" ? "Documents & Processing" : /\/reviews\/\d+$/.test(location.pathname) ? "Review Item Details" : "Manual Review Queue";
  return <RoleGate role={role}><div className="ws-app staff-app">
    <a className="ws-skip" href="#staff-main">Skip to content</a>
    <aside className="ws-sidebar">
      <BrandLogo />
      <span className="ws-nav-label">{label.toUpperCase()}</span>
      <nav className="ws-nav" aria-label={label + " navigation"}><NavLink to={roleHome[role]}><ListChecks size={19} />Manual Review Queue</NavLink>{role === "administrator" && <><NavLink to="/admin/dashboard"><LayoutDashboard size={19} />Dashboard</NavLink><NavLink to="/admin/documents"><Files size={19} />Documents &amp; Processing</NavLink><NavLink to="/admin/candidates"><UsersRound size={19} />Candidate Management</NavLink><NavLink to="/admin/staff"><UserPlus size={19} />Staff Management</NavLink></>}</nav>
      <div className="ws-sidebar-bottom"><div className="ws-private"><ShieldCheck size={20} /><p>Source evidence.<br /><strong>Clear review context.</strong></p></div><button className="ws-logout" onClick={() => clearSession()}><LogOut size={18} />Log out</button></div>
    </aside>
    <div className="ws-main"><header className="ws-topbar"><div>{label} <span>/</span><strong>{title}</strong></div><ShieldCheck size={19} aria-hidden="true" /></header><main id="staff-main" className="ws-content" tabIndex={-1}><Outlet context={{ role, queuePath: roleHome[role] }} /></main><footer className="ws-footer"><span>CVerge · {label}</span><span>Every detail, with context.</span></footer></div>
  </div></RoleGate>;
}
