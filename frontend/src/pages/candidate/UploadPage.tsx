import { useCallback, useEffect, useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { Link } from "react-router-dom";
import { ArrowDownToLine, ArrowRight, CheckCircle2, CloudUpload, ExternalLink, FileText, Files, LoaderCircle, ShieldCheck, Trash2 } from "lucide-react";
import { getCandidateFileById, getCandidateFiles, uploadCandidateFile } from "../../services/fileService";
import { friendlyError } from "../../services/apiClient";
import { useRemoteData } from "../../hooks/useRemoteData";
import { extension, fileSize, fileType, statusMessage, validateFile } from "../../utils/documents";
import { formatTimestamp } from "../../utils/dateTime";
import DocumentStatus from "../../components/common/DocumentStatus";
import "./UploadPage.css";

type Selection = { file: File; url: string };
export default function UploadPage() {
  const input = useRef<HTMLInputElement>(null);
  const selectionRef = useRef<Selection | null>(null);
  const submitting = useRef(false);
  const mounted = useRef(true);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [dragging, setDragging] = useState(false);
  const dragDepth = useRef(0);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [uploadedId, setUploadedId] = useState<number | null>(null);
  const [wasDuplicate, setWasDuplicate] = useState(false);
  const [showUploadSuccess, setShowUploadSuccess] = useState(false);
  const loader = useCallback(async () => {
    if (uploadedId) return getCandidateFileById(uploadedId);
    const files = await getCandidateFiles(1, 0);
    return files.items[0] || null;
  }, [uploadedId]);
  const { data: latest, error, loading, retry } = useRemoteData(loader, 5000);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; if (selectionRef.current) URL.revokeObjectURL(selectionRef.current.url); };
  }, []);

  function clearSelection() {
    if (selectionRef.current) URL.revokeObjectURL(selectionRef.current.url);
    selectionRef.current = null;
    setSelection(null);
    if (input.current) input.current.value = "";
  }
  function chooseFile(file?: File) {
    if (!file || submitting.current) return;
    const message = validateFile(file);
    setUploadError(message);
    if (message) return;
    if (selectionRef.current) URL.revokeObjectURL(selectionRef.current.url);
    const type = extension(file.name);
    const blob = type === "md" ? new Blob([file], { type: "text/plain;charset=utf-8" }) : type === "pdf" ? new Blob([file], { type: "application/pdf" }) : file;
    const next = { file, url: URL.createObjectURL(blob) };
    selectionRef.current = next;
    setSelection(next);
    setShowUploadSuccess(false);
  }
  function onInput(event: ChangeEvent<HTMLInputElement>) { chooseFile(event.target.files?.[0]); event.target.value = ""; }
  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault(); dragDepth.current = 0; setDragging(false);
    if (submitting.current) return;
    if (event.dataTransfer.files.length > 1) { setUploadError("Please choose one document at a time."); return; }
    chooseFile(event.dataTransfer.files[0]);
  }
  async function handleUpload() {
    if (!selectionRef.current || submitting.current) return;
    submitting.current = true; setUploading(true); setUploadError(""); setShowUploadSuccess(false);
    try {
      const response = await uploadCandidateFile(selectionRef.current.file);
      if (!mounted.current) return;
      clearSelection(); setUploadedId(response.file_id); setWasDuplicate(Boolean(response.duplicate)); setShowUploadSuccess(true); retry();
    } catch (cause) {
      if (mounted.current) setUploadError(friendlyError(cause, "We couldn't upload your document. Please try again."));
    } finally {
      submitting.current = false;
      if (mounted.current) setUploading(false);
    }
  }
  const selectedType = selection ? extension(selection.file.name) : "";
  return <>
    <div className="ws-page-heading"><div><span className="ws-eyebrow">YOUR CANDIDATE WORKSPACE</span><h1>Bring your experience together.</h1><p>Upload your documents. We’ll turn them into one clear professional profile.</p></div><Link className="ws-button ws-button-secondary" to="/documents">My Documents <ArrowRight size={16} /></Link></div>
    <div className="up-workspace-grid">
      <section className="ws-panel up-upload" aria-labelledby="upload-heading">
        <div className="ws-section-heading"><div><span className="ws-eyebrow">START WITH YOUR SOURCES</span><h2 id="upload-heading">Upload a document</h2><p>Add a resume or a LinkedIn Markdown export.</p></div><span className="ws-icon-tile"><CloudUpload size={23} /></span></div>
        <input ref={input} id="candidate-file" type="file" accept=".pdf,.docx,.md" className="ws-sr-only" aria-label="Choose a document to upload" disabled={uploading} onChange={onInput} tabIndex={-1} />
        <div className={`up-dropzone ${dragging ? "is-dragging" : ""} ${uploading ? "is-disabled" : ""}`} onDragEnter={event => { event.preventDefault(); if (!submitting.current) { dragDepth.current += 1; setDragging(true); } }} onDragOver={event => { event.preventDefault(); event.dataTransfer.dropEffect = submitting.current ? "none" : "copy"; }} onDragLeave={event => { event.preventDefault(); dragDepth.current -= 1; if (dragDepth.current <= 0) setDragging(false); }} onDrop={onDrop}>
          <span className="up-drop-icon"><CloudUpload size={32} strokeWidth={1.5} /></span><h3>{dragging ? "Drop your document here" : "Drag & drop your document"}</h3><p>or choose a file from your device</p><button type="button" className="ws-button ws-button-secondary" disabled={uploading} onClick={() => input.current?.click()}>Choose a file <ArrowRight size={16} /></button><span className="up-file-hint">PDF, DOCX or Markdown <span aria-hidden="true">·</span> Up to 10 MB</span>
        </div>
        {selection && <div className="up-selection"><div className="up-selection-main"><span className="up-file-icon"><FileText size={24} /></span><div><strong>{selection.file.name}</strong><span>{fileType(undefined, selection.file.name)} <span aria-hidden="true">·</span> {fileSize(selection.file.size)} <span aria-hidden="true">·</span> Ready to upload</span></div><button type="button" className="ws-icon-button" aria-label="Remove selected document" disabled={uploading} onClick={() => { clearSelection(); setUploadError(""); }}><Trash2 size={18} /></button></div><div className="up-selection-actions">{["pdf", "md"].includes(selectedType) && <a href={selection.url} target="_blank" rel="noopener noreferrer" className="ws-text-action"><ExternalLink size={15} />Preview</a>}<a href={selection.url} download={selection.file.name} className="ws-text-action"><ArrowDownToLine size={15} />Download</a><button type="button" className="ws-text-action" disabled={uploading} onClick={() => input.current?.click()}>Change file</button></div>{selectedType === "docx" && <p className="ws-caption">To preview this Word document, download it and open it in a compatible application.</p>}</div>}
        {uploadError && <div className="ws-notice ws-notice-error" role="alert">{uploadError}</div>}
        {showUploadSuccess && uploadedId && <div className="ws-notice ws-notice-success" role="status"><CheckCircle2 size={18} /><span>{wasDuplicate ? "You already uploaded this document. No duplicate was created." : "Your document is saved. Check Latest Upload for its processing status."} <Link to={`/files/${uploadedId}`}>View Details</Link></span></div>}
        <div className="up-submit-row"><span><ShieldCheck size={16} />Connected to your profile</span><button type="button" className="ws-button ws-button-primary" disabled={!selection || uploading} onClick={() => void handleUpload()}>{uploading ? <><LoaderCircle size={17} className="ws-spin" />Uploading document…</> : <>Upload document <ArrowRight size={17} /></>}</button></div>
      </section>
      <section className="ws-panel up-processing" aria-labelledby="latest-upload-heading">
        <div className="ws-section-heading"><h2 id="latest-upload-heading">Latest Upload</h2></div>
        {error && <div className="ws-notice ws-notice-error" role="alert">
          <span>{error} {latest && "The last loaded status is still shown."}</span>
          <button type="button" className="ws-text-action" onClick={retry}>Try again</button>
        </div>}
        {latest ? <>
          <div className="up-tracked-file">
            <FileText size={20} aria-hidden="true" />
            <div><strong>{latest.original_name}</strong><span className="up-tracked-date">Uploaded {formatTimestamp(latest.uploaded_at)}</span></div>
          </div>
          <div className="up-current-status" role="status" aria-atomic="true">
            <DocumentStatus status={latest.status} />
            <p className={`up-status-message ${latest.status === "failed" ? "up-failed" : ""}`}>{statusMessage(latest.status)}</p>
          </div>
        </> : <div className="up-status-empty" role={loading ? "status" : undefined}>
          <span className="ws-icon-tile"><Files size={23} aria-hidden="true" /></span>
          <h3>{loading ? "Loading your latest upload…" : error ? "Latest upload unavailable" : "No uploads yet"}</h3>
          <p>{error ? "Try again or open My Documents to find your uploads." : "Upload a document to see its details and processing status here."}</p>
        </div>}
        <div className="up-latest-actions">
          {latest && <Link to={`/files/${latest.file_id}`} className="ws-text-action">View Details<ArrowRight size={15} /></Link>}
          <Link to="/documents" className="ws-text-action">My Documents<ArrowRight size={15} /></Link>
        </div>
        {latest && <p className="up-poll-note">Checks for status updates every 5 seconds while this page is visible.</p>}
      </section>
    </div>
  </>;
}