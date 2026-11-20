import { clearSession, getAccessToken } from "./session";
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "/api/v1").replace(/\/$/, "");
export class ApiError extends Error {
  readonly status: number;
  constructor(message: string, status = 0) { super(message); this.status = status; }
}
export function friendlyError(error: unknown, fallback = "Something went wrong. Please try again."): string {
  return error instanceof ApiError ? error.message : fallback;
}
type RequestOptions = RequestInit & { authenticated?: boolean; accessToken?: string; allowNotFound?: boolean; failureMessage?: string };
export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { authenticated = true, accessToken, allowNotFound = false, failureMessage = "We couldn't complete your request. Please try again.", ...init } = options;
  const token = authenticated ? accessToken ?? getAccessToken() : null;
  if (authenticated && !token) {
    clearSession();
    throw new ApiError("Please sign in to continue.", 401);
  }
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  let response: Response;
  try { response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers }); }
  catch { throw new ApiError("Unable to connect. Check your connection and try again."); }
  if (response.status === 401) {
    if (authenticated) clearSession(true, token || undefined);
    throw new ApiError(authenticated ? "Your session has expired. Please sign in again." : "The email or password is incorrect. Please try again.", 401);
  }
  if (allowNotFound && response.status === 404) return null as T;
  if (!response.ok) {
    const messages: Record<number, string> = {
      403: "You don't have permission to do that. Please contact support if you need help.",
      404: "This document is unavailable. Return to My Documents to select another file.",
      413: "Your document is too large. Please choose a file smaller than 10 MB.",
      429: "Too many requests. Please wait a moment and try again.",
    };
    // Error bodies may contain secrets or model output; do not display or log them.
    throw new ApiError(messages[response.status] || failureMessage, response.status);
  }
  try { return await response.json() as T; }
  catch { throw new ApiError("We couldn't read the server response. Please try again."); }
}