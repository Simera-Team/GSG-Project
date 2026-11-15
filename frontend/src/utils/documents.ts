import type { FileStatus } from "../services/fileService";
export const MAX_FILE_SIZE = 10 * 1024 * 1024;
export function extension(name: string): string { return name.includes(".") ? name.slice(name.lastIndexOf(".") + 1).toLowerCase() : ""; }
export function validateFile(file: File): string {
  if (!["pdf", "docx", "md"].includes(extension(file.name))) return "Choose a PDF, DOCX or Markdown (.md) document.";
  if (!file.size || file.size > MAX_FILE_SIZE) return "Choose a non-empty file no larger than 10 MB.";
  return "";
}
export function fileSize(bytes: number): string { return bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1024 / 1024).toFixed(2)} MB`; }
export function fileType(type?: string, name = ""): string {
  const ext = extension(name);
  if (["pdf", "docx", "md"].includes(ext)) return ext.toUpperCase();
  return ({ "application/pdf": "PDF", "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "DOCX", "text/markdown": "MD" } as Record<string, string>)[type || ""] || type?.toUpperCase() || "Document";
}
export const statusLabels: Record<FileStatus, string> = { uploaded: "Uploaded", processing: "Processing", done: "Completed", needs_review: "Needs review", failed: "Failed" };
export function statusMessage(status: FileStatus): string {
  return { uploaded: "Your document is uploaded and waiting to be processed.", processing: "We're processing your document. Its status updates automatically.", done: "Processing is complete. You can view the information in My Profile.", needs_review: "Some information needs review before it can be added to your profile.", failed: "We couldn't process this document. Uploading the same file again won't restart processing. Contact your CVerge team for help." }[status] || "Waiting for a document status update.";
}
export function safeWebUrl(value?: string | null): string | undefined {
  if (!value) return undefined;
  try { const url = new URL(value); return ["https:", "http:"].includes(url.protocol) ? url.href : undefined; } catch { return undefined; }
}