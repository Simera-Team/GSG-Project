import { useCallback } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft, ArrowRight, FileText, RefreshCw } from "lucide-react";
import { getCandidateFileById } from "../../services/fileService";
import { ApiError } from "../../services/apiClient";
import { useRemoteData } from "../../hooks/useRemoteData";
import { fileType, statusMessage } from "../../utils/documents";
import { formatTimestamp } from "../../utils/dateTime";
import DocumentStatus from "../../components/common/DocumentStatus";
import "./FileDetailsPage.css";

function FileDetails({ fileId }: { fileId?: string }) {
  const loader = useCallback(() => {
    const id = Number(fileId);
    if (!fileId || !/^\d+$/.test(fileId) || !Number.isSafeInteger(id) || id <= 0) throw new ApiError("This document link is invalid. Please select a file from My Documents.");
    return getCandidateFileById(id);
  }, [fileId]);
  const { data: file, loading, error, retry } = useRemoteData(loader, 5000);
  return <>
    <Link to="/documents" className="ws-text-action fd-back"><ArrowLeft size={15} />My Documents</Link>
    <div className="ws-page-heading"><div><span className="ws-eyebrow">YOUR DOCUMENTS</span><h1>File Details</h1><p>Document information and its latest processing status.</p></div><button className="ws-button ws-button-secondary" disabled={loading} onClick={retry}><RefreshCw size={15} />Refresh</button></div>
    {error && <div className="ws-notice ws-notice-error" role="alert"><span>{error} {file && "The last loaded information is still shown. We’ll retry automatically."}</span><button className="ws-text-action" onClick={retry}>Try again</button></div>}
    {loading ? <section className="ws-panel fd-loading" role="status"><div className="ws-skeleton" /><div className="ws-skeleton" /><span className="ws-sr-only">Loading document details…</span></section> : file && <>
      <section className="ws-panel fd-document"><div className="fd-document-heading"><span className="ws-icon-tile"><FileText size={24} /></span><div><h2>{file.original_name}</h2><span className="ws-caption">{fileType(file.file_type,file.original_name)} document · File #{file.file_id}</span></div><DocumentStatus status={file.status} /></div><div className={`fd-processing-note ${file.status === "failed" ? "fd-failed" : ""}`} role="status"><p>{statusMessage(file.status)}</p>{file.status === "done" && <Link to="/profile" className="ws-text-action">View My Profile <ArrowRight size={15} /></Link>}{file.status === "needs_review" && <Link to="/profile#sources" className="ws-text-action">View profile review status <ArrowRight size={15} /></Link>}</div></section>
      <section className="ws-panel fd-information"><div className="ws-section-heading"><h2>Document information</h2></div><dl className="fd-details-grid"><div><dt>Filename</dt><dd>{file.original_name}</dd></div><div><dt>File type</dt><dd>{fileType(file.file_type,file.original_name)}</dd></div><div><dt>Uploaded</dt><dd>{formatTimestamp(file.uploaded_at)}</dd></div><div><dt>Processing finished</dt><dd>{file.finished_at ? formatTimestamp(file.finished_at) : ["uploaded", "processing"].includes(file.status) ? "Not finished yet" : "Not available"}</dd></div><div><dt>Processing attempts</dt><dd>{file.attempts}</dd></div><div><dt>Items awaiting review</dt><dd>{file.open_reviews}</dd></div><div><dt>Extraction method</dt><dd>{({ text: "Text extraction", ocr: "Optical character recognition", mixed: "Text and optical character recognition" } as Record<string,string>)[file.extraction_method || ""] || "Not available"}</dd></div><div><dt>OCR confidence</dt><dd>{file.ocr_confidence == null || !Number.isFinite(file.ocr_confidence) ? "Not available" : `${(file.ocr_confidence * 100).toFixed(1)}%`}</dd></div></dl></section>
      <div className="fd-availability"><FileText size={18} /><p>Original-file preview and download are not available yet. Your document’s information and processing status are available here.</p></div><p className="ws-caption">Status refreshes every 5 seconds while this page is visible.</p>
    </>}
  </>;
}
export default function FileDetailsPage() {
  const { fileId } = useParams<{ fileId: string }>();
  return <FileDetails key={fileId} fileId={fileId} />;
}