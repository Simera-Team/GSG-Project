
import { Link } from "react-router-dom";

export default function BrandLogo() {
  return (
    <Link to="/" className="auth-brand" aria-label="CVerge Home">
      <svg viewBox="0 0 100 100" fill="none" aria-hidden="true">
        <rect width="100" height="100" rx="25" fill="#103B48" />
        <path
          d="M19 28 H47 C58 28 62 39 72 50"
          stroke="white"
          strokeWidth="6"
          strokeLinecap="round"
        />
        <path
          d="M19 50 H72"
          stroke="white"
          strokeWidth="6"
          strokeLinecap="round"
        />
        <path
          d="M19 72 H47 C58 72 62 61 72 50"
          stroke="white"
          strokeWidth="6"
          strokeLinecap="round"
        />
        <circle cx="76" cy="50" r="10" fill="#EFB54A" />
      </svg>
      <span>CVerge</span>
    </Link>
  );
}
