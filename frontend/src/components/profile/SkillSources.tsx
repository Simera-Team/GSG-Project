import { useCallback, useId, useMemo, useRef, useState, type MouseEvent } from "react";
import { Link } from "react-router-dom";
import { createPortal } from "react-dom";
import { ArrowRight, FileText, Layers3, X } from "lucide-react";
import type { CandidateFile } from "../../services/fileService";
import { getSkillSupportingDocuments, skillSourceFileIds } from "../../services/provenanceService";
import { useRemoteData } from "../../hooks/useRemoteData";
import "./SkillSources.css";

function SourceDetails({ sources, files }: { sources: readonly string[]; files: readonly CandidateFile[] }) {
  const loader = useCallback(() => getSkillSupportingDocuments(sources, files), [sources, files]);
  const { data, loading, error, retry } = useRemoteData(loader);
  if (loading) return <p className="source-panel-note" role="status">Loading source documents…</p>;
  if (error || !data?.documents.length) return <div className="source-unavailable" role="status"><p>Source details are unavailable right now.</p><button type="button" className="source-action" onClick={retry}>Try again</button></div>;
  return <>
    <ol className="source-document-list">{data.documents.map((document, index) => <li key={document.fileId}>
      <span className="source-document-label">Supporting document {index + 1}</span>
      <div className="source-document-name"><FileText size={17} aria-hidden="true" /><strong>{document.name}</strong></div>
      {document.documentType && <span className="source-document-type">Document type: {document.documentType}</span>}
      <Link to={`/files/${document.fileId}`} className="source-action">View File Details<ArrowRight size={14} /></Link>
    </li>)}</ol>
    {data.unavailableCount > 0 && <div className="source-unavailable" role="status"><p>Some supporting documents could not be loaded.</p><button type="button" className="source-action" onClick={retry}>Try again</button></div>}
  </>;
}

export default function SkillSources({ name, sources, files }: {
  name: string;
  sources?: readonly string[];
  files: readonly CandidateFile[];
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const id = useId();
  const [open, setOpen] = useState(false);
  const ids = useMemo(() => skillSourceFileIds(sources), [sources]);
  if (!ids.length || !name.trim()) return null;

  function showSources() {
    if (!dialog.current || dialog.current.open) return;
    dialog.current.showModal();
    setOpen(true);
  }
  function closeFromBackdrop(event: MouseEvent<HTMLDialogElement>) {
    if (event.target !== event.currentTarget) return;
    const bounds = event.currentTarget.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) event.currentTarget.close();
  }
  return <>
    <button ref={trigger} type="button" className="skill-source-trigger" aria-label={`View sources for ${name}`} title="View sources" aria-haspopup="dialog" aria-controls={id} aria-expanded={open} onClick={showSources}>
      <Layers3 size={13} aria-hidden="true" />
    </button>
    {createPortal(<dialog ref={dialog} id={id} className="skill-source-dialog" aria-labelledby={`${id}-title`} onClick={closeFromBackdrop} onClose={() => { setOpen(false); trigger.current?.focus(); }}>
      <div className="source-panel-header"><h2 id={`${id}-title`}>Sources for {name}</h2><button type="button" className="source-close" aria-label="Close source details" onClick={() => dialog.current?.close()}><X size={18} /></button></div>
      <p className="source-profile-value"><span>Profile value</span><strong>{name}</strong></p>
      {open && sources && <SourceDetails sources={sources} files={files} />}
      <p className="source-panel-note">These documents support the skill in your profile. Original extracted wording is not available here.</p>
    </dialog>, document.body)}
  </>;
}