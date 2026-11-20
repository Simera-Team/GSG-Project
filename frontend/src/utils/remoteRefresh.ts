import { ApiError } from "../services/apiClient";

export const REFRESH_WINDOW_MS = 5 * 60 * 1000;
export const MAX_REFRESH_REQUESTS = 60;

// One request at a time, including explicit retries and visibility/focus events.
// A fresh explicit refresh restarts the budget; passive focus never does.
export function startRemoteRefresh<T>(options: {
  loader: () => Promise<T>;
  pollMs: number;
  shouldPoll?: (data: T) => boolean;
  onData: (data: T) => void;
  onError: (cause: unknown) => void;
  onLoading: (loading: boolean) => void;
}) {
  let active = true, busy = false, attempts = 0, canPoll = false, forbidden = false;
  let deadline = Date.now() + REFRESH_WINDOW_MS, lastStarted = -Infinity;
  let timer: number | undefined;
  function schedule() {
    window.clearTimeout(timer);
    if (active && options.pollMs && canPoll && attempts < MAX_REFRESH_REQUESTS && Date.now() < deadline) {
      timer = window.setTimeout(() => {
        if (document.visibilityState === "visible") void load(false);
        else schedule();
      }, options.pollMs);
    }
  }
  async function load(foreground: boolean, returnCheck = false) {
    if (!active || busy) return;
    if (!foreground && !returnCheck && (attempts >= MAX_REFRESH_REQUESTS || Date.now() >= deadline)) return;
    window.clearTimeout(timer);
    busy = true; attempts++; lastStarted = Date.now();
    if (foreground) options.onLoading(true);
    try {
      const result = await options.loader();
      if (!active) return;
      forbidden = false;
      canPoll = options.shouldPoll ? options.shouldPoll(result) : true;
      options.onData(result);
    } catch (cause) {
      if (!active) return;
      canPoll = false; // Stop automatic retries after an error.
      forbidden = cause instanceof ApiError && [401, 403, 404, 422].includes(cause.status);
      options.onError(cause);
    } finally {
      busy = false;
      if (active) { options.onLoading(false); schedule(); }
    }
  }
  function onReturn() {
    if (document.visibilityState === "visible" && !forbidden && Date.now() - lastStarted >= options.pollMs) void load(false, true);
  }
  timer = window.setTimeout(() => { void load(true); }, 0);
  if (options.pollMs) {
    window.addEventListener("focus", onReturn);
    document.addEventListener("visibilitychange", onReturn);
  }
  return {
    refresh() {
      if (!active || busy) return;
      attempts = 0; deadline = Date.now() + REFRESH_WINDOW_MS;
      void load(true);
    },
    dispose() {
      active = false; window.clearTimeout(timer);
      window.removeEventListener("focus", onReturn);
      document.removeEventListener("visibilitychange", onReturn);
    },
  };
}
