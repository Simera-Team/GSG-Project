import { ApiError, apiRequest } from "./apiClient";

export type ReviewStatusFilter = "open" | "waiting_candidate" | "resolved" | "all";
export interface ReviewOption {
  option_id: number;
  file_id: number;
  file_name: string;
  file_type: string;
  field_id: number | null;
  value: string | null;
  confidence: number | null;
  evidence: string | null;
  page: number | null;
}
export interface ReviewItem {
  review_id: number;
  profile_id: number;
  candidate_name: string;
  candidate_email: string;
  file_id: number;
  file_name: string;
  file_type: string;
  entity: string | null;
  field_name: string | null;
  reasons: string[];
  message: string | null;
  is_failed_job: boolean;
  created_at: string | null;
  assigned_to_candidate: boolean;
  sent_to_candidate_at: string | null;
  resolved: boolean;
  resolution: "option" | "custom" | "rejected" | "dismissed" | null;
  resolved_value: string | null;
  resolved_option_id: number | null;
  resolved_by: number | null;
  resolved_by_name: string | null;
  resolved_at: string | null;
  options: ReviewOption[];
}
export interface ReviewList {
  total: number;
  limit: number;
  offset: number;
  items: ReviewItem[];
}
export interface ReviewFilters {
  status?: ReviewStatusFilter;
  reason?: string;
  profileId?: number;
  limit?: number;
  offset?: number;
}
function positiveId(value: number) {
  return Number.isSafeInteger(value) && value > 0;
}
export function getReviewItems({ status = "open", reason, profileId, limit = 20, offset = 0 }: ReviewFilters = {}): Promise<ReviewList> {
  if (!["open", "waiting_candidate", "resolved", "all"].includes(status)
    || !Number.isInteger(limit) || limit < 1 || limit > 100
    || !Number.isSafeInteger(offset) || offset < 0
    || (profileId !== undefined && !positiveId(profileId))) {
    return Promise.reject(new ApiError("Choose valid review filters and try again."));
  }
  const query = new URLSearchParams({ status, limit: String(limit), offset: String(offset) });
  if (reason?.trim()) query.set("reason", reason.trim());
  if (profileId !== undefined) query.set("profile_id", String(profileId));
  return apiRequest("/review/items?" + query, { failureMessage: "We couldn't load the review queue. Please try again." });
}
export async function getReviewItem(reviewId: number): Promise<ReviewItem> {
  if (!positiveId(reviewId)) throw new ApiError("This review link is invalid. Return to the review queue.");
  try {
    return await apiRequest("/review/items/" + reviewId, { failureMessage: "We couldn't load this review item. Please try again." });
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) throw new ApiError("This review item is unavailable. Return to the review queue.", 404);
    throw error;
  }
}

export type ResolveRequest =
  | { action: "option"; option_id: number; map_to_skill?: string }
  | { action: "custom"; value: string; map_to_skill?: string }
  | { action: "reject" }
  | { action: "dismiss" };
export interface CandidateClarification {
  item: ReviewItem;
  candidate_email: string;
  suggested_message: string;
}

let reviewRevision = 0;
const reviewListeners = new Set<() => void>();
export const getReviewRevision = () => reviewRevision;
export function subscribeReviewChanges(listener: () => void) {
  reviewListeners.add(listener);
  return () => { reviewListeners.delete(listener); };
}
function changed() {
  reviewRevision += 1;
  reviewListeners.forEach(listener => listener());
}
async function reviewMutation<T>(reviewId: number, operation: "resolve" | "request-candidate", body?: ResolveRequest): Promise<T> {
  if (!positiveId(reviewId)) throw new ApiError("This review link is invalid. Return to the review queue.");
  try {
    const response = await apiRequest<T>(`/review/items/${reviewId}/${operation}`, {
      method: "POST",
      ...(body ? { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) } : {}),
      failureMessage: "We couldn't confirm whether the change was saved. Refresh this item before retrying.",
    });
    changed();
    return response;
  } catch (cause) {
    if (cause instanceof ApiError) {
      const messages: Record<number, string> = {
        403: "You do not have permission to change this review item.",
        404: "This review item is unavailable. Return to the review queue.",
        409: "This item changed or is not ready for a decision. Refresh its status. A field may require successful document extraction before it can be decided.",
        422: operation === "resolve" ? "The server could not accept this decision. Check the alternative, correction format, or standard skill name and try again." : "The clarification request could not be accepted. Refresh the item and try again.",
      };
      if (messages[cause.status]) throw new ApiError(messages[cause.status], cause.status);
    }
    throw cause;
  }
}
export function resolveReviewItem(reviewId: number, body: ResolveRequest): Promise<ReviewItem> {
  return reviewMutation(reviewId, "resolve", body);
}
export function requestCandidateClarification(reviewId: number): Promise<CandidateClarification> {
  return reviewMutation(reviewId, "request-candidate");
}
