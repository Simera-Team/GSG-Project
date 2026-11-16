import { ApiError } from "../services/apiClient";
import { safeProcessingError } from "./processing";
import type { ResolveRequest, ReviewItem } from "../services/reviewService";

export function isSkillNameReview(item: ReviewItem): boolean {
  return !!item.entity?.startsWith("skills[") && item.field_name === "name";
}
export function buildResolveRequest(item: ReviewItem, action: ResolveRequest["action"], optionId: string, value: string, mapping: string | null): ResolveRequest {
  if (item.resolved) throw new ApiError("This item has already been resolved. Refresh to see the recorded decision.");
  if (item.is_failed_job) {
    if (action !== "dismiss") throw new ApiError("A failed document can only be dismissed; it has no field value to correct.");
    return { action: "dismiss" };
  }
  if (action === "dismiss" || !item.entity || !item.field_name) throw new ApiError("Choose a supported decision for this field.");
  if (action === "reject") return { action: "reject" };
  if (action !== "option" && action !== "custom") throw new ApiError("Choose a supported review decision.");
  let map_to_skill: string | undefined;
  if (mapping !== null) {
    if (!isSkillNameReview(item)) throw new ApiError("Skill mapping is only available for skill names.");
    map_to_skill = mapping.trim();
    if (!map_to_skill || map_to_skill.length > 100) throw new ApiError("Enter an existing standard skill name of 1–100 characters.");
  }
  if (action === "option") {
    const id = Number(optionId);
    if (!item.options.some(option => option.option_id === id)) throw new ApiError("Select one of this item's alternatives.");
    return { action, option_id: id, ...(map_to_skill ? { map_to_skill } : {}) };
  }
  const correction = value.trim();
  if (!correction || correction.length > 5000) throw new ApiError("Enter a correction of 1–5,000 characters.");
  if (isSkillNameReview(item) && correction.length > 100) throw new ApiError("Skill names must be no longer than 100 characters.");
  if (item.field_name === "email" && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(correction)) throw new ApiError("Enter a valid email address.");
  if (item.field_name === "proficiency" && !["native", "fluent", "intermediate", "basic"].includes(correction.toLowerCase())) throw new ApiError("Use native, fluent, intermediate, or basic.");
  if (item.field_name === "is_current" && !["true", "false"].includes(correction.toLowerCase())) throw new ApiError("Use true or false for a current role.");
  return { action, value: correction, ...(map_to_skill ? { map_to_skill } : {}) };
}

export function correctionHint(item: ReviewItem): string {
  if (["start_date", "end_date", "issue_date"].includes(item.field_name || "")) return "Use a year, YYYY-MM, or a month and year." + (item.field_name === "end_date" ? " Use current for an ongoing role." : "");
  if (item.field_name === "country") return "Use a country name or two-letter code supported by the country list.";
  if (item.field_name === "proficiency") return "Use native, fluent, intermediate, or basic.";
  if (item.field_name === "is_current") return "Use true or false.";
  return "The server validates the correction before applying it to the profile.";
}

// Provider payloads are classified, never rendered. Unknown messages also use a safe fallback.
export function safeReviewContext(item: ReviewItem): string {
  if (item.reasons.includes("llm_failed")) return safeProcessingError(item.message, true);
  if (item.is_failed_job || item.reasons.includes("no_text")) return "The document could not be processed. Check that the source is readable; an administrator can retry processing.";
  if (item.reasons.includes("source_conflict")) return "The sources contain different values for this field. Compare their evidence before choosing a value.";
  if (item.reasons.includes("unknown_skill")) return "This skill is not recognized. Approve it, map it to an existing standard skill, or reject it.";
  if (item.reasons.includes("unknown_country")) return "This country is not recognized. Choose a supported country or leave the field empty.";
  return "This field needs a reviewer to check the available values and source evidence.";
}

export function clarificationMailto(email: string, message: string): string | null {
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return null;
  return `mailto:${encodeURIComponent(email)}?subject=${encodeURIComponent("CVerge profile clarification")}&body=${encodeURIComponent(message)}`;
}
