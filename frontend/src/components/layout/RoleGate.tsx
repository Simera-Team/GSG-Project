import type { ReactNode } from "react";
import { Link, Navigate, useLocation } from "react-router-dom";
import { useSessionUser } from "../../hooks/useSessionUser";
import type { UserRole } from "../../services/authService";
import { canUseWorkspace, roleHome } from "../../services/roleAccess";
import { clearSession, getSessionNotice } from "../../services/session";
import PageNotice from "../common/PageNotice";

export default function RoleGate({ role, children }: { role: UserRole; children: ReactNode }) {
  const { token, user, loading, error, retry } = useSessionUser();
  const location = useLocation();
  if (!token) return <Navigate to="/login" replace state={{ from: location.pathname + location.search + location.hash, message: getSessionNotice() }} />;
  if (loading) return <PageNotice label="Your account" title="Checking your account"><p role="status">Please wait while we verify your session.</p></PageNotice>;
  if (error || !user) return <PageNotice label="Your account" title="We couldn't verify your account"><p role="alert">{error || "Please try again to continue."}</p><div className="page-notice-actions"><button onClick={retry}>Try again</button><button onClick={() => clearSession()}>Sign in again</button></div></PageNotice>;
  if (!canUseWorkspace(user.role, role)) return <PageNotice label="Access denied" title="This workspace is for another role"><p role="alert">Your account does not have access to this workspace.</p><div className="page-notice-actions"><Link to={roleHome[user.role]}>Go to my workspace</Link><button onClick={() => clearSession()}>Sign in with another account</button></div></PageNotice>;
  return children;
}
