import { ApiError } from "./apiClient";
import { getCandidateFiles, type CandidateFile, type FileStatus } from "./fileService";

export async function getWorkspaceDocuments() {
  const pageSize = 100;
  const first = await getCandidateFiles(pageSize, 0);
  const items = [...first.items];
  for (let offset = pageSize; offset < first.total; offset += pageSize) {
    const page = await getCandidateFiles(pageSize, offset);
    if (page.total !== first.total) {
      throw new ApiError("Your document list changed while refreshing. Please try again.");
    }
    items.push(...page.items);
  }
  const unique = new Map<number, CandidateFile>(items.map(file => [file.file_id, file]));
  if (unique.size !== first.total) {
    throw new ApiError("We couldn't refresh the full document summary. Please try again.");
  }
  const counts: Record<FileStatus, number> = { uploaded: 0, processing: 0, done: 0, needs_review: 0, failed: 0 };
  for (const file of unique.values()) {
    if (!Object.hasOwn(counts, file.status)) {
      throw new ApiError("We couldn't read a document status. Please try again.");
    }
    counts[file.status] += 1;
  }
  // Preserve the backend's newest-first order without guessing timestamp timezones.
  return { total: first.total, counts, recent: Array.from(unique.values()).slice(0, 5) };
}