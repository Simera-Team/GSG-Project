import { ApiError, apiRequest } from "./apiClient";
import type { CandidateFile, FileStatus } from "./fileService";
import { getAccessToken } from "./session";

export interface AdminFile extends CandidateFile {
  profile_id: number;
  user_id: number;
  candidate_name: string;
}
export interface ProcessingAttempt {
  attempt_number: number;
  trigger: "first_run" | "auto_retry" | "admin_rerun";
  outcome: "valid" | "invalid" | "error";
  provider: string;
  model_version: string;
  error_message: string | null;
  started_at: string;
  finished_at: string;
}
export interface AdminFileDetail extends AdminFile {
  attempts_detail: ProcessingAttempt[];
}
export interface AdminFileList {
  total: number;
  limit: number;
  offset: number;
  items: AdminFile[];
}
export interface RerunResult {
  file_id: number;
  status: FileStatus;
  message: string;
}
export interface AdminFileFilters {
  status?: FileStatus;
  profileId?: number;
  limit?: number;
  offset?: number;
}
export const processingStatuses: FileStatus[] = ["uploaded", "processing", "done", "needs_review", "failed"];
const positiveId = (id: number) => Number.isSafeInteger(id) && id > 0;
type RerunMarker = { token: string; attempts: number; sawProcessing: boolean; uncertain: boolean };
const markers = new Map<number, RerunMarker>();
const inFlight = new Map<number, string>();
const listeners = new Set<() => void>();
let revision = 0;
export const getAdminFileRevision = () => revision;
export function subscribeAdminFiles(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
function changed() { revision += 1; listeners.forEach(listener => listener()); }
export function rerunTracking(fileId: number): "submitting" | "accepted" | "uncertain" | null {
  const token = getAccessToken();
  if (!token) return null;
  if (inFlight.get(fileId) === token) return "submitting";
  const marker = markers.get(fileId);
  return marker?.token === token ? marker.uncertain ? "uncertain" : "accepted" : null;
}
function observe(file: AdminFile) {
  const marker = markers.get(file.file_id);
  if (!marker || marker.token !== getAccessToken()) return;
  if (file.status === "processing") marker.sawProcessing = true;
  if (["done", "failed", "needs_review"].includes(file.status) && (file.attempts > marker.attempts || marker.sawProcessing)) markers.delete(file.file_id);
}
async function request<T>(path: string, mutation = false): Promise<T> {
  try {
    return await apiRequest<T>(path, {
      ...(mutation ? { method: "POST" } : {}),
      failureMessage: mutation ? "We couldn't confirm whether the rerun was accepted. Check processing updates before requesting another run." : "We couldn't load the admin documents. Please try again.",
    });
  } catch (cause) {
    if (cause instanceof ApiError) {
      const messages: Record<number, string> = {
        403: "Only administrators can access document processing controls.",
        404: "This document is unavailable. Return to Documents & Processing.",
        409: "This document is already being processed. Refresh to see its latest status.",
        422: mutation ? "The rerun request was not accepted. Refresh the document before trying again." : "The document request was not valid. Check the filters or select a document from the list.",
      };
      if (messages[cause.status]) throw new ApiError(messages[cause.status], cause.status);
    }
    throw cause;
  }
}
export async function getAdminFiles({ status, profileId, limit = 20, offset = 0 }: AdminFileFilters = {}): Promise<AdminFileList> {
  if ((status !== undefined && !processingStatuses.includes(status)) || (profileId !== undefined && !positiveId(profileId)) || !Number.isInteger(limit) || limit < 1 || limit > 100 || !Number.isSafeInteger(offset) || offset < 0) throw new ApiError("Choose valid document filters and try again.");
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (status) params.set("status", status);
  if (profileId !== undefined) params.set("profile_id", String(profileId));
  const result = await request<AdminFileList>("/admin/files?" + params);
  result.items.forEach(observe);
  return result;
}
export async function getAdminFile(fileId: number): Promise<AdminFileDetail> {
  if (!positiveId(fileId)) throw new ApiError("This document link is invalid. Select a document from Documents & Processing.");
  const result = await request<AdminFileDetail>("/admin/files/" + fileId);
  observe(result);
  return result;
}
export async function rerunAdminFile(file: Pick<AdminFile, "file_id" | "status" | "attempts">): Promise<RerunResult> {
  if (!positiveId(file.file_id)) throw new ApiError("This document link is invalid.");
  if (file.status === "processing") throw new ApiError("This document is already being processed.", 409);
  if (rerunTracking(file.file_id)) throw new ApiError("A rerun request is already pending. Check processing updates before requesting another run.", 409);
  const token = getAccessToken();
  if (!token) throw new ApiError("Please sign in to continue.", 401);
  inFlight.set(file.file_id, token); changed();
  try {
    const result = await request<RerunResult>(`/admin/files/${file.file_id}/rerun`, true);
    if (result.file_id !== file.file_id || !processingStatuses.includes(result.status) || typeof result.message !== "string") throw new ApiError("We couldn't confirm the rerun response. Check processing updates before requesting another run.");
    markers.set(file.file_id, { token, attempts: file.attempts, sawProcessing: false, uncertain: false });
    return result;
  } catch (cause) {
    if (!(cause instanceof ApiError) || cause.status === 0 || cause.status >= 500) markers.set(file.file_id, { token, attempts: file.attempts, sawProcessing: false, uncertain: true });
    throw cause;
  } finally {
    if (inFlight.get(file.file_id) === token) inFlight.delete(file.file_id);
    changed();
  }
}
