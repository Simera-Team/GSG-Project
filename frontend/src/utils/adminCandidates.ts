import type { CandidateDirectoryEntry } from "../services/adminWorkspaceService";
import { processingStatuses } from "../services/adminFileService";
import type { FileStatus } from "../services/fileService";

export const CANDIDATE_PAGE_SIZE = 20;
export function positivePage(raw: string | null, size = CANDIDATE_PAGE_SIZE): number {
  const value = raw || "1", number = Number(value);
  return /^[1-9]\d*$/.test(value) && Number.isSafeInteger(number * size) ? number : 1;
}
export function parseCandidateQuery(params: URLSearchParams) {
  const value = params.get("status");
  return { query: params.get("q")?.trim() || "", status: processingStatuses.includes(value as FileStatus) ? value as FileStatus : undefined, page: positivePage(params.get("page")) };
}
export function filterCandidateDirectory(entries: readonly CandidateDirectoryEntry[], query: string, status?: FileStatus) {
  const search = query.trim().toLowerCase();
  return entries.filter(candidate => (!search || candidate.name.toLowerCase().includes(search) || String(candidate.profileId).includes(search) || String(candidate.userId).includes(search)) && (!status || candidate.statuses[status] > 0));
}
export function dashboardRate(value: number | null): string {
  return value === null ? "Not available" : (value * 100).toFixed(1) + "%";
}

