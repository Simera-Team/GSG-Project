const SESSION_EVENT = "cverge:session";
let notice = "";
let revision = 0;
export const getSessionRevision = () => revision;
export const getAccessToken = () => sessionStorage.getItem("access_token");
export const getSessionNotice = () => notice;
export function subscribeSession(listener: () => void) {
  window.addEventListener(SESSION_EVENT, listener);
  window.addEventListener("storage", listener);
  return () => {
    window.removeEventListener(SESSION_EVENT, listener);
    window.removeEventListener("storage", listener);
  };
}
export function setAccessToken(token: string) {
  notice = "";
  revision += 1;
  sessionStorage.setItem("access_token", token);
  window.dispatchEvent(new Event(SESSION_EVENT));
}
export function clearSession(expired = false, requestToken?: string) {
  if (requestToken && requestToken !== getAccessToken()) return;
  revision += 1;
  notice = expired ? "Your session has expired. Please sign in again." : "";
  sessionStorage.removeItem("access_token");
  window.dispatchEvent(new Event(SESSION_EVENT));
}
export function safeReturnPath(value: unknown): string {
  return typeof value === "string" && /^\/(workspace(?:[?#].*)?|upload(?:[?#].*)?|documents(?:[?#].*)?|profile(?:[?#].*)?|files\/\d+(?:[?#].*)?)$/.test(value)
    ? value : "/workspace";
}