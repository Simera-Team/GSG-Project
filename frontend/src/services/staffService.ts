import { ApiError, apiRequest } from "./apiClient";
import type { UserRole } from "./authService";
import { getAccessToken } from "./session";
import { prepareStaffRequest } from "../utils/staffAccounts";

export type StaffRole = Extract<UserRole, "reviewer" | "administrator">;
export interface CreateStaffRequest { name: string; email: string; password: string; role: StaffRole }
export interface StaffAccount { user_id: number; name: string; email: string; role: StaffRole }
const inFlight = new Set<string>();

// No staff-list endpoint exists. This is a single authenticated creation request.
export async function createStaffAccount(values: CreateStaffRequest): Promise<StaffAccount> {
  const payload = prepareStaffRequest(values);
  const key = (getAccessToken() || "") + "\0" + payload.email;
  if (inFlight.has(key)) throw new ApiError("A creation request for this email is already in progress.", 409);
  inFlight.add(key);
  try {
    const account = await apiRequest<StaffAccount>("/admin/users", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload),
      failureMessage: "The server could not confirm account creation. The account may have been created; verify before retrying this email.",
    });
    if (!account || !Number.isSafeInteger(account.user_id) || account.user_id < 1 || typeof account.name !== "string" || !account.name.trim() || typeof account.email !== "string" || !account.email.trim() || !["reviewer", "administrator"].includes(account.role)) throw new ApiError("The account confirmation was incomplete. The account may have been created; verify before retrying this email.");
    return { user_id: account.user_id, name: account.name, email: account.email, role: account.role };
  } catch (cause) {
    if (cause instanceof ApiError) {
      const messages: Record<number, string> = {
        403: "Only administrators can create staff accounts. Sign out and verify your administrator account.",
        404: "Staff account creation is unavailable on this backend.",
        409: "This email is already registered. Choose a different email.",
        422: "The server rejected the account details. Check the name, email, password length and role.",
      };
      if (messages[cause.status]) throw new ApiError(messages[cause.status], cause.status);
      if (cause.status === 0) throw new ApiError("The account-creation outcome could not be confirmed. The account may have been created; verify before retrying this email.");
    }
    throw cause;
  } finally { inFlight.delete(key); }
}

