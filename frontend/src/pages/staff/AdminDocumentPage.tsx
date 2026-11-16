import { useCallback, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { ArrowLeft, RefreshCw } from "lucide-react";
import { getAdminFile, type RerunResult } from "../../services/adminFileService";
import { useRemoteData } from "../../hooks/useRemoteData";
import { attemptOutcomes, attemptTriggers, safeProcessingError } from "../../utils/processing";
import { fileType, statusLabels } from "../../utils/documents";
import { formatTimestamp } from "../../utils/dateTime";
import DocumentStatus from "../../components/common/DocumentStatus";
import AdminRerunPanel from "../../components/admin/AdminRerunPanel";
import "./ReviewPages.css";
import "./AdminDocuments.css";
import "./AdminWorkspace.css";

export default function AdminDocumentPage() {
  const { fileId } = useParams();
  return <DocumentDetails key={fileId} fileId={fileId} />;
}
function DocumentDetails({ fileId }: { fileId?: string }) {
  const location = useLocation();
  const loader = useCallback(() => getAdminFile(fileId && /^[1-9]\d*$/.test(fileId) ? Number(fileId) : NaN), [fileId]);
  const { data: file, loading, error, retry } = useRemoteData(loader, 5000);
  const [result, setResult] = useState<RerunResult | null>(null);
  const [rerunError, setRerunError] = useState("");
  const [actionVersion, setActionVersion] = useState(0);
  function refresh() { setActionVersion(value => value + 1); retry(); }
  return <>
    <Link to={"/admin/documents" + location.search} className="ws-text-action rq-back"><ArrowLeft size={15} />Documents &amp; Processing</Link>
    <div className="ws-page-heading"><div><span className="ws-eyebrow">DOCUMENT PROCESSING</span><h1>Admin Document Details</h1><p>Current status and recorded processing attempts for this source.</p></div><button className="ws-button ws-button-secondary" disabled={loading} onClick={refresh}><RefreshCw size={16} />Refresh document</button></div>
    {result && <div className="ws-notice ws-notice-success ad-rerun-result" role="status"><span>The server accepted the rerun request for File #{result.file_id}. Status returned: <strong>{statusLabels[result.status]}</strong>. Acceptance does not mean processing has started or finished. Follow the current status and attempts below.</span></div>}
    {rerunError && <p className="ws-notice ws-notice-error" role="alert">{rerunError}</p>}
    {error && <div className="ws-notice ws-notice-error" role="alert"><span>{error}</span><button className="ws-text-action" onClick={refresh}>Try again</button></div>}
    {loading ? <div className="ws-panel rq-panel" role="status"><span className="ws-sr-only">Loading admin document details…</span><div className="ws-skeleton" /><div className="ws-skeleton" /></div> : file && !error && <>
      <section className="ws-panel rq-panel" aria-labelledby="admin-file-heading"><div className="ws-section-heading"><h2 id="admin-file-heading" className="ad-filename">{file.original_name}</h2><DocumentStatus status={file.status} /></div>
        <dl className="rq-context"><div><dt>Candidate</dt><dd>{file.candidate_name}<br />Candidate user #{file.user_id} · Profile #{file.profile_id}</dd></div><div><dt>Source document</dt><dd>{fileType(file.file_type, file.original_name)} · File #{file.file_id}</dd></div><div><dt>Uploaded</dt><dd>{formatTimestamp(file.uploaded_at)}</dd></div><div><dt>Processing finished</dt><dd>{file.finished_at ? formatTimestamp(file.finished_at) : "Not available"}</dd></div><div><dt>Processing attempts</dt><dd>{file.attempts}</dd></div><div><dt>Open review items</dt><dd>{file.open_reviews}</dd></div><div><dt>Extraction method</dt><dd>{({ text: "Text extraction", ocr: "Optical character recognition", mixed: "Text and optical character recognition" } as Record<string, string>)[file.extraction_method || ""] || "Not available"}</dd></div><div><dt>OCR confidence</dt><dd>{file.ocr_confidence !== null && Number.isFinite(file.ocr_confidence) && file.ocr_confidence >= 0 && file.ocr_confidence <= 1 ? Math.round(file.ocr_confidence * 100) + "%" : "Not available"}</dd></div></dl>
        <div className="aw-row-links"><Link className="ws-text-action" to={`/admin/candidates/${file.profile_id}`}>View candidate profile</Link><Link className="ws-text-action" to={`/admin/reviews?profile_id=${file.profile_id}`}>View this candidate's review items</Link></div>
      </section>
      {(file.status === "failed" || file.error_message) && <section className="ws-panel rq-panel" aria-labelledby="processing-failure-heading"><h2 id="processing-failure-heading">Processing issue</h2><p className="ad-safe-error">{safeProcessingError(file.error_message)}</p></section>}
      <section className="ws-panel rq-panel" aria-labelledby="processing-attempts-heading"><div className="ws-section-heading"><h2 id="processing-attempts-heading">Processing attempts <span className="ws-count">{file.attempts_detail.length}</span></h2></div><p className="ws-caption">These are recorded attempts. A full document status-change history is not available.</p>
        {file.attempts_detail.length ? <ol className="ad-attempt-list">{file.attempts_detail.map(attempt => <li className="ad-attempt" key={attempt.attempt_number}><div className="rq-item-title"><h3>Attempt {attempt.attempt_number}</h3><span className={"rq-status" + (attempt.outcome === "valid" ? " is-resolved" : "")}>{attemptOutcomes[attempt.outcome]}</span></div><dl className="rq-context"><div><dt>Trigger</dt><dd>{attemptTriggers[attempt.trigger]}</dd></div><div><dt>Provider and model</dt><dd>{attempt.provider} · {attempt.model_version}</dd></div><div><dt>Started</dt><dd>{formatTimestamp(attempt.started_at)}</dd></div><div><dt>Finished</dt><dd>{formatTimestamp(attempt.finished_at)}</dd></div></dl>{(attempt.error_message || attempt.outcome !== "valid") && <p className="ad-safe-error">{attempt.outcome === "invalid" && !attempt.error_message ? "The extracted information did not pass validation." : safeProcessingError(attempt.error_message, true)}</p>}</li>)}</ol> : <div className="ws-empty"><h3>No recorded attempts yet</h3><p>No completed processing attempt has been returned for this document.</p></div>}
      </section>
      <AdminRerunPanel key={actionVersion} file={file} onResult={response => { setRerunError(""); setResult(response); refresh(); }} onConflict={message => { setRerunError(message); refresh(); }} />
      <p className="ws-caption">Status checks run every 5 seconds while visible, for up to 5 minutes. Refresh or return to this tab to check again. Original-file preview and a full status history are unavailable.</p>
    </>}
  </>;
}
