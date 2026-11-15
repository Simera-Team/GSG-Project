
import { useRef, useState, type FormEvent } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { Eye, EyeOff, ArrowRight } from "lucide-react";
import BrandLogo from "../../components/common/BrandLogo";
import PageNotice from "../../components/common/PageNotice";
import { useSessionUser } from "../../hooks/useSessionUser";
import { authService, loginDestination } from "../../services/authService";
import { safeLoginReturnPath } from "../../services/roleAccess";
import { friendlyError } from "../../services/apiClient";
import "./Auth.css";

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const session = useSessionUser();
  const returnTo = safeLoginReturnPath(location.state?.from);
  const sessionMessage = location.state?.message === "Your session has expired. Please sign in again." ? location.state.message : "";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  const submitting = useRef(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();

    if (submitting.current) return;
    submitting.current = true;

    setError("");
    setSuccess("");
    setIsLoading(true);

    try {
      const user = await authService.signIn({ email: email.trim(), password });
      setSuccess("Signed in successfully!");
      navigate(loginDestination(user.role, returnTo), { replace: true });
    } catch (err) {
      setError(
        friendlyError(err, "Unable to sign in. Please try again.")
      );
    } finally {
      submitting.current = false;
      setIsLoading(false);
    }
  };

  if (session.token && session.loading && !isLoading) return <PageNotice label="Your account" title="Checking your account"><p role="status">Please wait while we verify your session.</p></PageNotice>;
  if (session.user && !isLoading) return <Navigate to={loginDestination(session.user.role, returnTo)} replace />;

  return (
    <div className="auth-page">
      <div className="auth-left">
        <BrandLogo />

        <div className="auth-form-container">
          <span className="auth-eyebrow">WELCOME BACK</span>

          <h1>Sign in to CVerge</h1>

          <p className="auth-description">
            Sign in to continue to your workspace.
          </p>

          {location.state?.registered === true && !success && <p className="auth-success" role="status">Account created. Sign in to continue to your workspace.</p>}
          {sessionMessage && !success && <p className="auth-error" role="status">{sessionMessage}</p>}
          <form onSubmit={handleSubmit}>
            <div className="auth-field">
              <label htmlFor="login-email">
                Email address
              </label>

              <input
                id="login-email"
                type="email"
                placeholder="name@example.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                required
                disabled={isLoading}
              />
            </div>

            <div className="auth-field">
              <div className="auth-label-row">
                <label htmlFor="login-password">
                  Password
                </label>
              </div>

              <div className="auth-password-wrapper">
                <input
                  id="login-password"
                  type={showPassword ? "text" : "password"}
                  placeholder="Enter your password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  required
                  disabled={isLoading}
                />

                <button
                  type="button"
                  className="auth-toggle-password"
                  onClick={() => setShowPassword(!showPassword)}
                  aria-label={
                    showPassword
                      ? "Hide password"
                      : "Show password"
                  }
                >
                  {showPassword ? (
                    <EyeOff size={18} />
                  ) : (
                    <Eye size={18} />
                  )}
                </button>
              </div>
            </div>

            {error && (
              <p className="auth-error" role="alert">
                {error}
              </p>
            )}

            {success && (
              <p className="auth-success" role="status">
                {success}
              </p>
            )}

            <button
              type="submit"
              className="auth-submit"
              disabled={isLoading}
            >
              {isLoading ? "Signing in..." : "Sign in"}

              {!isLoading && <ArrowRight size={18} />}
            </button>
          </form>

          <p className="auth-switch">
            New to CVerge?{" "}
            <Link to="/register" state={{ from: returnTo }}>
              Create an account
            </Link>
          </p>
        </div>

        <p className="auth-copyright">
          © 2026 CVerge
        </p>
      </div>

      <div className="auth-right">
        <div className="auth-decorative">
          <div className="auth-orbit auth-orbit-one" />
          <div className="auth-orbit auth-orbit-two" />
          <div className="auth-center-icon">CV</div>
        </div>
      </div>
    </div>
  );
}
