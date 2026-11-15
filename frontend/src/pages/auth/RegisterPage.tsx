
import { useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { Eye, EyeOff, ArrowRight } from "lucide-react";
import BrandLogo from "../../components/common/BrandLogo";
import { authService } from "../../services/authService";
import { friendlyError } from "../../services/apiClient";
import { safeReturnPath } from "../../services/session";
import "./Auth.css";

export default function RegisterPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const returnTo = safeReturnPath(location.state?.from);
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);

  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();

    if (isLoading) return;

    setError("");

    const name = fullName.trim();

    if (name.length < 2 || name.length > 255) {
      setError("Full name must be between 2 and 255 characters.");
      return;
    }

    if (password.length < 8 || password.length > 128) {
      setError("Password must be between 8 and 128 characters.");
      return;
    }

    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }

    setIsLoading(true);

    try {
      await authService.register({
        name,
        email: email.trim(),
        password,
      });

      navigate("/login", { replace: true, state: { from: returnTo, registered: true } });
    } catch (err) {
      setError(
        friendlyError(err, "Unable to create your account. Please try again.")
      );
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="auth-page">
      <div className="auth-left">
        <BrandLogo />

        <div className="auth-form-container">
          <span className="auth-eyebrow">GET STARTED</span>
          <h1>Create your account</h1>

          <p className="auth-description">
            Join CVerge to manage candidate information in one place.
          </p>

          <form onSubmit={handleSubmit}>
            <div className="auth-field">
              <label htmlFor="register-name">Full name</label>
              <input
                id="register-name"
                type="text"
                placeholder="Enter your full name"
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
                autoComplete="name"
                minLength={2}
                maxLength={255}
                required
                disabled={isLoading}
              />
            </div>

            <div className="auth-field">
              <label htmlFor="register-email">Email address</label>
              <input
                id="register-email"
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
              <label htmlFor="register-password">Password</label>

              <div className="auth-password-wrapper">
                <input
                  id="register-password"
                  type={showPassword ? "text" : "password"}
                  placeholder="Create a password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="new-password"
                  minLength={8}
                  maxLength={128}
                  required
                  disabled={isLoading}
                />

                <button
                  type="button"
                  className="auth-toggle-password"
                  onClick={() => setShowPassword(!showPassword)}
                  aria-label={showPassword ? "Hide password" : "Show password"}
                >
                  {showPassword ? (
                    <EyeOff size={18} />
                  ) : (
                    <Eye size={18} />
                  )}
                </button>
              </div>
            </div>

            <div className="auth-field">
              <label htmlFor="register-confirm">Confirm password</label>
              <input
                id="register-confirm"
                type={showPassword ? "text" : "password"}
                placeholder="Confirm your password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                autoComplete="new-password"
                required
                disabled={isLoading}
              />
            </div>

            {error && (
              <p className="auth-error" role="alert">
                {error}
              </p>
            )}



            <button
              type="submit"
              className="auth-submit"
              disabled={isLoading}
            >
              {isLoading ? "Creating account..." : "Create account"}
              {!isLoading && <ArrowRight size={18} />}
            </button>
          </form>

          <p className="auth-switch">
            Already have an account?{" "}
            <Link to="/login" state={{ from: returnTo }}>Sign in</Link>
          </p>
        </div>

        <p className="auth-copyright">© 2026 CVerge</p>
      </div>

      <div className="auth-right">
        <div className="auth-decorative">
          <div className="auth-orbit auth-orbit-one" />
          <div className="auth-orbit auth-orbit-two" />
          <div className="auth-center-icon">CV</div>
        </div>

        <div className="auth-right-content">
          <span>BUILT FOR CLARITY</span>
          <h2>
            Connected data.
            <br />
            Confident reviews.
          </h2>
          <p>
            Organize candidate information, identify conflicts,
            and keep important details traceable.
          </p>
        </div>
      </div>
    </div>
  );
}
