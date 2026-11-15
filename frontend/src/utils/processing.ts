import type { FileStatus } from "../services/fileService";
import { processingStatuses } from "../services/adminFileService";

export const ADMIN_DOCUMENT_PAGE_SIZE = 20;
export function parseAdminDocumentQuery(params: URLSearchParams) {
  const rawStatus = params.get("status") || "";
  const status = processingStatuses.includes(rawStatus as FileStatus) ? rawStatus as FileStatus : undefined;
  const rawProfile = params.get("profile_id") || "";
  const profileId = /^[1-9]\d*$/.test(rawProfile) && Number.isSafeInteger(Number(rawProfile)) ? Number(rawProfile) : undefined;
  const rawPage = params.get("page") || "1";
  const number = Number(rawPage);
  const page = /^[1-9]\d*$/.test(rawPage) && Number.isSafeInteger(number * ADMIN_DOCUMENT_PAGE_SIZE) ? number : 1;
  return { status, profileId, page };
}
// Only fixed explanations leave this function; raw errors are never rendered or logged.
export function safeProcessingError(message: string | null, ai = false): string {
  const text = message || "";
  if (/API_KEY_INVALID|API key not valid|invalid.{0,20}(api.?key|credential)/i.test(text)) return "AI extraction failed due to an invalid API configuration. An administrator needs to check the configuration before retrying.";
  if (/RESOURCE_EXHAUSTED|quota|rate.limit|429/i.test(text)) return "AI extraction could not complete because the service reached a usage limit. An administrator can retry when capacity is available.";
  if (/PERMISSION_DENIED|permission denied|403/i.test(text)) return "AI extraction could not access the configured service. An administrator needs to check the service configuration.";
  if (/model.{0,40}(not.found|not.supported|unavailable)|NOT_FOUND/i.test(text)) return "AI extraction failed because the configured service or model is unavailable. An administrator needs to check the configuration.";
  if (/timeout|timed out|UNAVAILABLE|503/i.test(text)) return "AI extraction could not complete because the service was temporarily unavailable. An administrator can retry processing.";
  if (/no readable text|text extraction failed|unreadable|corrupt/i.test(text)) return "The document could not be read. Check that the original is readable and in a supported format before retrying.";
  if (/schema|validation/i.test(text)) return "The extracted information could not be validated. Review the source document before retrying.";
  return ai ? "AI extraction could not complete. An administrator can investigate the processing configuration and retry the document." : "Document processing could not complete. Check the document and processing configuration before requesting another run.";
}
export const attemptTriggers = { first_run: "Initial run", auto_retry: "Automatic retry", admin_rerun: "Administrator rerun" };
export const attemptOutcomes = { valid: "Valid extraction", invalid: "Invalid extraction", error: "Processing error" };
