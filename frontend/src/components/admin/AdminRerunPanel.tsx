import { useEffect, useId, useRef, useState, useSyncExternalStore } from "react";
import { ApiError, friendlyError } from "../../services/apiClient";
import { getAdminFileRevision, rerunAdminFile, rerunTracking, subscribeAdminFiles, type AdminFileDetail, type RerunResult } from "../../services/adminFileService";

export default function AdminRerunPanel({ file, onResult, onConflict }: {
  file: AdminFileDetail;
  onResult: (result: RerunResult) => void;
  onConflict: (message: string) => void;
}) {
  useSyncExternalStore(subscribeAdminFiles, getAdminFileRevision, getAdminFileRevision);
  const tracking = rerunTracking(file.file_id);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [blocked, setBlocked] = useState(false);
  const submitting = useRef(false);
  const mounted = useRef(true);
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const id = useId();
  const locked = busy || blocked || !!tracking || file.status === "processing";
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    if (open && !dialog.current?.open) dialog.current?.showModal();
    if (!open && dialog.current?.open) dialog.current.close();
  }, [open]);
  async function confirm() {
    if (locked || submitting.current) return;
    submitting.current = true; setBusy(true); setError("");
    try {
      const result = await rerunAdminFile(file);
      if (mounted.current) { setOpen(false); onResult(result); }
    } catch (cause) {
      if (!mounted.current) return;
      setOpen(false);
      setError(friendlyError(cause, "We couldn't confirm the rerun. Check processing updates before trying again."));
      if (cause instanceof ApiError && cause.status === 409) onConflict(friendlyError(cause));
      if (cause instanceof ApiError && [403, 404, 422].includes(cause.status)) setBlocked(true);
    } finally {
      submitting.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  return <section className="ws-panel rq-panel ad-rerun" aria-labelledby={id + "-heading"}>
    <h2 id={id + "-heading"}>Reprocess document</h2>
    <p className="ws-muted">Request another run from the stored original. Earlier attempts remain available. This may use the AI service again.</p>
    {tracking && <p className="ws-notice" role="status">{tracking === "submitting" ? "Submitting the rerun request…" : tracking === "uncertain" ? "The request outcome could not be confirmed. Check status and attempts before requesting another run." : "The rerun request was accepted. Waiting for processing updates; the document status below still comes from the server."}</p>}
    {file.status === "processing" && <p className="ws-caption">This document is currently processing. Another run cannot be requested now.</p>}
    {error && <p className="ws-notice ws-notice-error" role="alert">{error}{blocked && " Use Refresh document to check access and the latest state."}</p>}
    <button ref={trigger} type="button" className="ws-button ws-button-primary" disabled={locked} onClick={() => { setError(""); setOpen(true); }}>Reprocess document</button>
    <dialog ref={dialog} className="rq-confirm-dialog" aria-labelledby={id + "-confirm-heading"} aria-describedby={id + "-description"} onCancel={event => { if (busy) event.preventDefault(); else setOpen(false); }} onClose={() => { if (!dialog.current?.open) trigger.current?.focus(); }}>
      <h2 id={id + "-confirm-heading"}>Reprocess this document?</h2>
      <p className="ad-filename">{file.original_name}</p>
      <p id={id + "-description"}>This submits a new processing request for the stored original and may update the candidate profile or review items. It does not repair processing configuration problems.</p>
      <div className="rq-confirm-buttons"><button type="button" className="ws-button ws-button-secondary" autoFocus disabled={busy} onClick={() => setOpen(false)}>Cancel</button><button type="button" className="ws-button ws-button-primary" disabled={locked} onClick={() => void confirm()}>{busy ? "Submitting…" : "Confirm reprocess"}</button></div>
    </dialog>
  </section>;
}
