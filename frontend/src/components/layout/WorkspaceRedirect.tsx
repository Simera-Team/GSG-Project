import { Navigate, useLocation } from "react-router-dom";
import { useSessionUser } from "../../hooks/useSessionUser";
import { loginDestination } from "../../services/authService";
import { clearSession, getSessionNotice } from "../../services/session";
import PageNotice from "../common/PageNotice";

// Compatibility entry points must wait for the server-verified role.
export default function WorkspaceRedirect() {
  const { token, user, loading, error, retry } = useSessionUser();
  const location = useLocation();
  if (!token) return <Navigate to="/login" replace state={{ from: location.pathname + location.search + location.hash, message: getSessionNotice() }} />;
  if (loading) return <PageNotice label="Your account" title="Checking your account"><p role="status">Please wait while we verify your session.</p></PageNotice>;
  if (error || !user) return <PageNotice label="Your account" title="We couldn't verify your account"><p role="alert">{error || "Please sign in again."}</p><div className="page-notice-actions"><button onClick={retry}>Try again</button><button onClick={() => clearSession()}>Sign in again</button></div></PageNotice>;
  return <Navigate to={loginDestination(user.role, undefined)} replace />;
}
