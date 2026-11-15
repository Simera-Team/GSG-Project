import { useEffect, useState } from "react";
import { friendlyError } from "../services/apiClient";

// Ignore stale responses after navigation/retry and never overlap polling requests.
export function useRemoteData<T>(loader: () => Promise<T>, pollMs = 0) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    let busy = false;
    async function load(initial = false) {
      if (!active || busy) return;
      busy = true;
      if (initial) { setLoading(true); setError(""); setData(null); }
      try {
        const result = await loader();
        if (active) { setData(result); setError(""); }
      } catch (cause) {
        if (active) setError(friendlyError(cause, "We couldn't load this information. Please try again."));
      } finally {
        busy = false;
        if (active) setLoading(false);
      }
    }
    const initial = window.setTimeout(() => { void load(true); }, 0);
    const interval = pollMs ? window.setInterval(() => {
      if (document.visibilityState === "visible") void load();
    }, pollMs) : undefined;
    return () => { active = false; window.clearTimeout(initial); window.clearInterval(interval); };
  }, [loader, pollMs, revision]);
  return { data, loading, error, retry: () => setRevision(value => value + 1) };
}