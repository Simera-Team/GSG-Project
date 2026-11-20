import { ApiError, apiRequest } from "./apiClient";
import { staffReturnPath } from "./roleAccess";
import { clearSession, getAccessToken, getSessionRevision, safeReturnPath, setAccessToken } from "./session";

export interface LoginRequest {
  email: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: string;
}

export interface RegisterRequest {
  name: string;
  email: string;
  password: string;
}

export type UserRole = "candidate" | "reviewer" | "administrator";

export interface RegisterResponse {
  user_id: number;
  name: string;
  email: string;
  role: UserRole;
  created_at: string;
}
export interface CurrentUser {
  user_id: number;
  name: string;
  email: string;
  role: UserRole;
}

function validateUser(user: CurrentUser): CurrentUser {
  if (!user || !Number.isSafeInteger(user.user_id) || user.user_id <= 0 || typeof user.name !== "string" || typeof user.email !== "string" || !["candidate", "reviewer", "administrator"].includes(user.role)) {
    throw new ApiError("We couldn't verify your account. Please sign in again.");
  }
  return user;
}
export async function getCurrentUser(accessToken?: string): Promise<CurrentUser> {
  return validateUser(await apiRequest<CurrentUser>("/auth/me", { accessToken, failureMessage: "We couldn't verify your account. Please try again." }));
}

let verified: { token: string; revision: number; user: Promise<CurrentUser> } | undefined;
export function getVerifiedSessionUser(token: string): Promise<CurrentUser> {
  const revision = getSessionRevision();
  if (verified?.token === token && verified.revision === revision) return verified.user;
  const user = getCurrentUser(token).catch(error => {
    if (verified?.user === user) verified = undefined;
    throw error;
  });
  verified = { token, revision, user };
  return user;
}
export function loginDestination(role: UserRole, requested: unknown): string {
  return role === "candidate" ? safeReturnPath(requested) : staffReturnPath(requested, role);
}
export const authService = {
  async signIn(data: LoginRequest): Promise<CurrentUser> {
    // Keep the new token transient until /auth/me verifies both identity and role.
    clearSession();
    const revision = getSessionRevision();
    const response = await authService.login(data);
    if (typeof response?.access_token !== "string" || !response.access_token.trim()) throw new ApiError("We couldn't sign you in. Please try again.");
    const user = await getCurrentUser(response.access_token);
    // Logout or another login must win over a late response from this attempt.
    if (revision !== getSessionRevision() || getAccessToken()) throw new ApiError("Sign-in was interrupted. Please try again.");
    setAccessToken(response.access_token);
    verified = { token: response.access_token, revision: getSessionRevision(), user: Promise.resolve(user) };
    return user;
  },
  login(data: LoginRequest): Promise<LoginResponse> {
    return apiRequest("/auth/login", { authenticated: false, method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data), failureMessage: "We couldn't sign you in. Please try again." });
  },
  register(data: RegisterRequest): Promise<RegisterResponse> {
    return apiRequest("/auth/register", { authenticated: false, method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data), failureMessage: "We couldn't create your account. Check your details or try signing in if you already have an account." });
  },
};