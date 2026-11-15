import { CheckCircle2, Clock3, LoaderCircle, CircleAlert } from "lucide-react";
import { statusLabels } from "../../utils/documents";
import type { FileStatus } from "../../services/fileService";
export default function DocumentStatus({ status }: { status: FileStatus }) {
  const Icon = status === "done" ? CheckCircle2 : status === "processing" ? LoaderCircle : status === "failed" || status === "needs_review" ? CircleAlert : Clock3;
  return <span className={`ws-status ws-status-${status}`}><Icon size={14} aria-hidden="true" className={status === "processing" ? "ws-spin" : undefined} />{statusLabels[status] || "Unknown"}</span>;
}