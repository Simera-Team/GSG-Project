import { useEffect } from "react";
import { Link, Navigate, NavLink, Outlet, useLocation } from "react-router-dom";
import { Files, LayoutDashboard, LogOut, ShieldCheck, UploadCloud, UserRound } from "lucide-react";
import BrandLogo from "../common/BrandLogo";
import { clearSession, getSessionNotice } from "../../services/session";
import { useSessionUser } from "../../hooks/useSessionUser";
import PageNotice from "../common/PageNotice";
import "./CandidateLayout.css";
export default function CandidateLayout() {
  const { token, user, loading, error, retry } = useSessionUser();
  const location = useLocation();
  useEffect(() => {
    if (!location.hash) { window.scrollTo(0, 0); return; }
    const id = location.hash.slice(1);
    // A profile section may appear only after its data has finished loading.
    const scrollToSection = () => {
      const section = document.getElementById(id);
      if (!section) return false;
      section.scrollIntoView({ block: "start" });
      return true;
    };
    const observer = new MutationObserver(() => { if (scrollToSection()) observer.disconnect(); });
    if (!scrollToSection()) observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, [location.pathname, location.hash]);
  if (!token) return <Navigate to="/login" replace state={{ from: location.pathname + location.search + location.hash, message: getSessionNotice() }} />;
  if (loading) return <PageNotice label="Your account" title="Checking your account"><p role="status">Please wait while we verify your session.</p></PageNotice>;
  if (error || !user) return <PageNotice label="Your account" title="We couldn't verify your account"><p role="alert">{error || "Please try again to continue."}</p><div className="page-notice-actions"><button onClick={retry}>Try again</button><button onClick={() => clearSession()}>Sign in again</button></div></PageNotice>;
  if (user.role !== "candidate") return <PageNotice label="Account access" title="This workspace is for candidates"><p>You are signed in as {user.role === "administrator" ? "an administrator" : "a reviewer"}. Staff pages are not available in this frontend.</p><div className="page-notice-actions"><Link to="/">Go to Home</Link><button onClick={() => clearSession()}>Sign in with another account</button></div></PageNotice>;
  const title = location.pathname === "/workspace" ? "Overview" : location.pathname.startsWith("/files/") ? "File Details" : location.pathname === "/profile" ? "My Profile" : location.pathname === "/documents" ? "My Documents" : "Upload Documents";
  return <div className="ws-app">
    <a className="ws-skip" href="#candidate-main">Skip to content</a>
    <aside className="ws-sidebar">
      <BrandLogo />
      <span className="ws-nav-label">CANDIDATE WORKSPACE</span>
      <nav aria-label="Candidate navigation" className="ws-nav">
        <NavLink to="/workspace" end><LayoutDashboard size={19} />Overview</NavLink>
        <NavLink to="/upload" end><UploadCloud size={19} />Upload Documents</NavLink>
        <NavLink to="/documents" className={({ isActive }) => isActive || location.pathname.startsWith("/files/") ? "active" : ""}><Files size={19} />My Documents</NavLink>
        <NavLink to="/profile"><UserRound size={19} />My Profile</NavLink>
      </nav>
      <div className="ws-sidebar-bottom"><div className="ws-private"><ShieldCheck size={20} /><p>Your documents.<br /><strong>One clear profile.</strong></p></div><button className="ws-logout" onClick={() => clearSession()}><LogOut size={18} />Log out</button></div>
    </aside>
    <div className="ws-main"><header className="ws-topbar"><div>Candidate Workspace <span>/</span> <strong>{title}</strong></div><Link to="/profile" className="ws-account" aria-label="My Profile"><UserRound size={18} /></Link></header><main id="candidate-main" className="ws-content" tabIndex={-1}><Outlet /></main><footer className="ws-footer"><span>CVerge · Candidate Workspace</span><span>Your experience, brought together.</span></footer></div>
  </div>;
}