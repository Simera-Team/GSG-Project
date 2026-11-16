import { ApiError, apiRequest } from "./apiClient";
import { getAdminFile, getAdminFiles, processingStatuses, type AdminFile } from "./adminFileService";
import type { CandidateProfileResponse } from "./profileService";
import type { CandidateFile, FileStatus } from "./fileService";
import { skillSourceFileIds } from "./provenanceService";
import { getAccessToken, getSessionRevision } from "./session";

export interface AdminDashboard {
  candidates: number;
  files_total: number;
  files_by_status: Record<FileStatus, number>;
  llm_attempts: number;
  llm_failed_attempts: number;
  valid_on_first_try_rate: number | null;
  files_that_hit_3_attempts: number;
  field_records: number;
  average_confidence: number | null;
  share_of_fields_sent_to_review: number | null;
  open_reviews: number;
  resolved_reviews: number;
  reviews_with_typed_correction: number;
}
export interface CandidateDirectoryEntry {
  profileId: number;
  userId: number;
  name: string;
  documents: number;
  openDocumentReviews: number;
  statuses: Record<FileStatus, number>;
}
export interface CandidateDirectory {
  entries: CandidateDirectoryEntry[];
  documentTotal: number;
}
export interface ProfileChange {
  change_id: number;
  field_name: string;
  old_value: string | null;
  new_value: string | null;
  changed_by: string;
  reason: string | null;
  file_id: number | null;
  changed_at: string | null;
}
export interface ProfileHistory {
  total: number;
  limit: number;
  offset: number;
  items: ProfileChange[];
}
async function read<T>(path: string, resource: string): Promise<T> {
  try { return await apiRequest<T>(path, { failureMessage: `We couldn't load ${resource}. Please try again.` }); }
  catch (cause) {
    if (cause instanceof ApiError) {
      if (cause.status === 403) throw new ApiError("Only administrators can access this information.", 403);
      if (cause.status === 404) throw new ApiError(`The requested ${resource} is unavailable. Check the profile reference or return to the admin workspace.`, 404);
      if (cause.status === 422) throw new ApiError("This request was not valid. Check the profile reference and try again.", 422);
    }
    throw cause;
  }
}
export async function getAdminDashboard(): Promise<AdminDashboard> {
  const data = await read<AdminDashboard>("/admin/dashboard", "dashboard");
  const counts = [data?.candidates, data?.files_total, data?.llm_attempts, data?.llm_failed_attempts, data?.files_that_hit_3_attempts, data?.field_records, data?.open_reviews, data?.resolved_reviews, data?.reviews_with_typed_correction, ...processingStatuses.map(status => data?.files_by_status?.[status])];
  const rates = [data?.valid_on_first_try_rate, data?.average_confidence, data?.share_of_fields_sent_to_review];
  if (counts.some(value => !Number.isSafeInteger(value) || value < 0) || rates.some(value => value !== null && (typeof value !== "number" || !Number.isFinite(value) || value < 0 || value > 1))) throw new ApiError("The dashboard response is incomplete. Refresh to load verified totals.");
  if (processingStatuses.reduce((sum, status) => sum + data.files_by_status[status], 0) !== data.files_total) throw new ApiError("The document totals are inconsistent. Refresh the dashboard.");
  return data;
}
export async function getCandidateDirectory(): Promise<CandidateDirectory> {
  const token = getAccessToken(), sessionRevision = getSessionRevision();
  const checkSession = () => {
    if (token !== getAccessToken() || sessionRevision !== getSessionRevision()) throw new ApiError("Your account changed while the directory was loading. Refresh after signing in.");
  };
  const size = 100;
  const first = await getAdminFiles({ limit: size, offset: 0 });
  checkSession();
  if (!Number.isSafeInteger(first.total) || first.total < 0 || first.items.length !== Math.min(size, first.total)) throw new ApiError("The document directory response is incomplete. Refresh before using these counts.");
  const all: AdminFile[] = [...first.items];
  for (let offset = size; offset < first.total; offset += size) {
    const page = await getAdminFiles({ limit: size, offset });
    checkSession();
    if (page.total !== first.total || page.items.length !== Math.min(size, first.total - offset)) throw new ApiError("The document directory changed while loading. Refresh to load the complete directory.");
    all.push(...page.items);
  }
  const unique = new Map(all.map(file => [file.file_id, file]));
  if (unique.size !== first.total || all.length !== first.total) throw new ApiError("We couldn't load the complete document directory. Refresh before using these counts.");
  const candidates = new Map<number, CandidateDirectoryEntry>();
  for (const file of all) {
    if (!Number.isSafeInteger(file.file_id) || file.file_id < 1 || !Number.isSafeInteger(file.open_reviews) || file.open_reviews < 0 || !Number.isSafeInteger(file.profile_id) || file.profile_id < 1 || !Number.isSafeInteger(file.user_id) || file.user_id < 1 || !processingStatuses.includes(file.status)) throw new ApiError("A candidate reference could not be verified. Refresh the directory.");
    const entry = candidates.get(file.profile_id) || { profileId: file.profile_id, userId: file.user_id, name: file.candidate_name, documents: 0, openDocumentReviews: 0, statuses: { uploaded: 0, processing: 0, done: 0, needs_review: 0, failed: 0 } };
    if (entry.userId !== file.user_id || entry.name !== file.candidate_name) throw new ApiError("Candidate information changed while loading. Refresh the directory.");
    entry.documents += 1;
    entry.openDocumentReviews += file.open_reviews;
    entry.statuses[file.status] += 1;
    candidates.set(file.profile_id, entry);
  }
  return { entries: [...candidates.values()], documentTotal: first.total };
}
function checkProfileId(profileId: number) {
  if (!Number.isSafeInteger(profileId) || profileId < 1) throw new ApiError("This candidate profile reference is invalid. Select a candidate or enter a valid profile ID.");
}
export function getAdminCandidate(profileId: number): Promise<CandidateProfileResponse> {
  checkProfileId(profileId);
  return read(`/profile/${profileId}`, "candidate profile");
}
export function getAdminProfileHistory(profileId: number, limit = 20, offset = 0): Promise<ProfileHistory> {
  checkProfileId(profileId);
  if (!Number.isInteger(limit) || limit < 1 || limit > 200 || !Number.isSafeInteger(offset) || offset < 0) throw new ApiError("Choose a valid history page.");
  return read(`/profile/${profileId}/history?limit=${limit}&offset=${offset}`, "profile history");
}
export async function getAdminSkillDocuments(profileId: number, sources: readonly string[], files: readonly CandidateFile[]) {
  checkProfileId(profileId);
  const ids = skillSourceFileIds(sources);
  const known = new Map(files.map(file => [file.file_id, file]));
  const results = await Promise.allSettled(ids.map(async id => {
    const embedded = known.get(id);
    if (embedded?.original_name?.trim()) return embedded;
    const file = await getAdminFile(id);
    if (file.file_id !== id || file.profile_id !== profileId || !file.original_name?.trim()) return null;
    return file;
  }));
  const documents = results.flatMap(result => result.status === "fulfilled" && result.value ? [result.value] : []);
  const unsupported = new Set(sources.filter(source => !skillSourceFileIds([source]).length)).size;
  return { documents, unavailableCount: unsupported + ids.length - documents.length };
}

