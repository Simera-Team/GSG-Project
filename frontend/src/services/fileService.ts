import { apiRequest, friendlyError } from "./apiClient";

export const getFileErrorMessage = friendlyError;

// Upload response
export interface UploadResponse {
  file_id: number;
  filename: string;
  size: number;
  status: string;
  duplicate?: boolean;
  message: string;
}

// File processing status
export type FileStatus =
  | "uploaded"
  | "processing"
  | "done"
  | "needs_review"
  | "failed";

// Candidate file
export interface CandidateFile {
  file_id: number;
  original_name: string;
  file_type: string;
  status: FileStatus;
  extraction_method: string | null;
  ocr_confidence: number | null;
  error_message: string | null;
  uploaded_at: string | null;
  finished_at: string | null;
  attempts: number;
  open_reviews: number;
}

// List response
export interface CandidateFilesResponse {
  total: number;
  limit: number;
  offset: number;
  items: CandidateFile[];
}

export function uploadCandidateFile(file: File): Promise<UploadResponse> {
  const body = new FormData();
  body.append("file", file);
  return apiRequest("/cv/upload", { method: "POST", body,
    failureMessage: "We couldn't upload this document. Check that it is a valid PDF, DOCX or Markdown file and try again." });
}
export function getCandidateFiles(limit = 50, offset = 0): Promise<CandidateFilesResponse> {
  return apiRequest(`/cv/files?limit=${limit}&offset=${offset}`, { failureMessage: "We couldn't load your documents. Please try again." });
}
export function getCandidateFileById(fileId: number): Promise<CandidateFile> {
  return apiRequest(`/cv/files/${fileId}`, { failureMessage: "We couldn't load this document. Please try again." });
}