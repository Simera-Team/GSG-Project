import type { UserRole } from "./authService";

export const roleHome: Record<UserRole, string> = {
  candidate: "/workspace",
  reviewer: "/reviewer/reviews",
  administrator: "/admin/reviews",
};
const adminPath = /^\/admin\/(?:(?:dashboard|staff)(?:[?#].*)?|(?:reviews|documents|candidates)(?:\/[1-9]\d*)?(?:[?#].*)?)$/;
const reviewerPath = /^\/reviewer\/reviews(?:\/[1-9]\d*)?(?:[?#].*)?$/;
export function canUseWorkspace(role: UserRole, workspace: UserRole): boolean {
  return role === workspace;
}
export function staffReturnPath(value: unknown, role: UserRole): string {
  return typeof value === "string" && (role === "administrator" ? adminPath : reviewerPath).test(value) ? value : roleHome[role];
}
export function safeLoginReturnPath(value: unknown): string | undefined {
  if (typeof value !== "string") return undefined;
  return /^\/(workspace|upload|documents|profile)(?:[?#].*)?$/.test(value)
    || /^\/files\/\d+(?:[?#].*)?$/.test(value)
    || reviewerPath.test(value) || adminPath.test(value) ? value : undefined;
}
