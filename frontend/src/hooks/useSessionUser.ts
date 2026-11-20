import { useCallback, useSyncExternalStore } from "react";
import { getVerifiedSessionUser } from "../services/authService";
import { getAccessToken, getSessionRevision, subscribeSession } from "../services/session";
import { useRemoteData } from "./useRemoteData";

// A stored token alone never grants candidate navigation. Recheck it after reload.
export function useSessionUser() {
  const token = useSyncExternalStore(subscribeSession, getAccessToken, () => null);
  const revision = useSyncExternalStore(subscribeSession, getSessionRevision, () => 0);
  const loader = useCallback(async () => ({ token, revision, user: token ? await getVerifiedSessionUser(token) : null }), [token, revision]);
  const request = useRemoteData(loader);
  const current = request.data?.token === token && request.data?.revision === revision;
  return { token, user: current ? request.data.user : null, loading: Boolean(token && (request.loading || (!current && !request.error))), error: request.error, retry: request.retry };
}
