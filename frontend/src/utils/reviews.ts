import type { ReviewItem, ReviewStatusFilter } from "../services/reviewService";

export const REVIEW_PAGE_SIZE = 20;
// Values from the backend ReviewReason constants; unknown reasons remain readable.
export const reviewReasons: Record<string, string> = {
  low_confidence: "Low confidence",
  low_ocr_confidence: "Low OCR confidence",
  evidence_missing: "Evidence missing",
  evidence_not_found: "Evidence not found",
  value_not_in_evidence: "Value not in evidence",
  unparseable_date: "Unparseable date",
  current_job_has_end_date: "Current job has end date",
  unknown_country: "Unknown country",
  unknown_skill: "Unknown skill",
  invalid_format: "Invalid format",
  source_conflict: "Source conflict",
  llm_failed: "Extraction failed",
  no_text: "No readable text",
  profile_invalid: "Invalid profile",
};
export function reasonLabel(reason: string): string {
  return reviewReasons[reason] || reason.replaceAll("_", " ");
}
export function reviewStatus(item: ReviewItem): string {
  return item.resolved ? "Resolved" : item.assigned_to_candidate ? "Waiting for candidate" : "Open";
}
export function confidenceLabel(value: number | null): string {
  return value !== null && Number.isFinite(value) && value >= 0 && value <= 1 ? `${Math.round(value * 100)}%` : "Not available";
}
export function parseReviewQuery(params: URLSearchParams) {
  const rawStatus = params.get("status") || "open";
  const status: ReviewStatusFilter = ["open", "waiting_candidate", "resolved", "all"].includes(rawStatus) ? rawStatus as ReviewStatusFilter : "open";
  const rawPage = params.get("page") || "1";
  const number = Number(rawPage);
  const page = /^[1-9]\d*$/.test(rawPage) && Number.isSafeInteger(number * REVIEW_PAGE_SIZE) ? number : 1;
  const rawProfile = params.get("profile_id") || "";
  const profileId = /^[1-9]\d*$/.test(rawProfile) && Number.isSafeInteger(Number(rawProfile)) ? Number(rawProfile) : undefined;
  return { status, page, profileId, reason: params.get("reason")?.trim() || "" };
}
