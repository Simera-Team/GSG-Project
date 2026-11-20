import { useCallback, useEffect, useRef, useState } from "react";
import { friendlyError } from "../services/apiClient";
import { startRemoteRefresh } from "../utils/remoteRefresh";

// Ignore stale responses after navigation/retry and never overlap polling requests.
export function useRemoteData<T>(loader: () => Promise<T>, pollMs = 0, shouldPoll?: (data: T) => boolean) {
  const [state, setState] = useState<{ loader: typeof loader; data: T | null; loading: boolean; error: string }>({ loader, data: null, loading: true, error: "" });
  const controller = useRef<ReturnType<typeof startRemoteRefresh<T>> | null>(null);
  useEffect(() => {
    const request = startRemoteRefresh({ loader, pollMs, shouldPoll,
      onData: result => setState({ loader, data: result, loading: false, error: "" }),
      onError: cause => setState(previous => ({ loader, data: previous.loader === loader ? previous.data : null, loading: false, error: friendlyError(cause, "We couldn't load this information. Please try again.") })),
      onLoading: value => setState(previous => ({ loader, data: previous.loader === loader ? previous.data : null, loading: value, error: value ? "" : previous.loader === loader ? previous.error : "" })),
    });
    controller.current = request;
    return () => { request.dispose(); controller.current = null; };
  }, [loader, pollMs, shouldPoll]);
  const retry = useCallback(() => controller.current?.refresh(), []);
  // A new route/filter/session loader must never expose a previous loader's data.
  const current = state.loader === loader ? state : { data: null, loading: true, error: "" };
  return { data: current.data, loading: current.loading, error: current.error, retry };
}
