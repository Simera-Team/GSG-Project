import { useCallback, useSyncExternalStore, type FormEvent } from "react";
import { Link, useLocation, useSearchParams } from "react-router-dom";
import { ArrowLeft, ArrowRight, Files, RefreshCw } from "lucide-react";
import { getAdminFiles, getAdminFileRevision, processingStatuses, subscribeAdminFiles } from "../../services/adminFileService";
import { useRemoteData } from "../../hooks/useRemoteData";
import { ADMIN_DOCUMENT_PAGE_SIZE, parseAdminDocumentQuery, safeProcessingError } from "../../utils/processing";
import { fileType, statusLabels } from "../../utils/documents";
import { formatTimestamp } from "../../utils/dateTime";
import DocumentStatus from "../../components/common/DocumentStatus";
import "./ReviewPages.css";
import "./AdminDocuments.css";

export default function AdminDocumentsPage() {
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const revision = useSyncExternalStore(subscribeAdminFiles, getAdminFileRevision, getAdminFileRevision);
  const { status, profileId, page } = parseAdminDocumentQuery(params);
  const loader = useCallback(() => getAdminFiles({ status, profileId, limit: ADMIN_DOCUMENT_PAGE_SIZE, offset: (page - 1) * ADMIN_DOCUMENT_PAGE_SIZE }), [status, profileId, page]);
  return <Documents key={location.key + params.toString() + ":" + revision} params={params} setParams={setParams} loader={loader} />;
}
function Documents({ params, setParams, loader }: {
  params: URLSearchParams;
  setParams: (params: URLSearchParams) => void;
  loader: () => ReturnType<typeof getAdminFiles>;
}) {
  const { status, profileId, page } = parseAdminDocumentQuery(params);
  const { data, loading, error, retry } = useRemoteData(loader, 5000);
  const pages = Math.max(1, Math.ceil((data?.total || 0) / ADMIN_DOCUMENT_PAGE_SIZE));
  function filter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const next = new URLSearchParams();
    for (const key of ["status", "profile_id"]) {
      const value = String(form.get(key) || "").trim();
      if (value) next.set(key, value);
    }
    setParams(next);
  }
  function changePage(nextPage: number) {
    const next = new URLSearchParams(params);
    if (nextPage === 1) next.delete("page"); else next.set("page", String(nextPage));
    setParams(next);
  }
  return <>
    <div className="ws-page-heading"><div><span className="ws-eyebrow">ADMIN WORKSPACE</span><h1>Documents &amp; Processing</h1><p>Monitor candidate documents, processing results, and recorded attempts.</p></div><button className="ws-button ws-button-secondary" disabled={loading} onClick={retry}><RefreshCw size={16} />Refresh documents</button></div>
    <section className="ws-panel rq-panel" aria-labelledby="admin-documents-heading">
      <div className="ws-section-heading"><div><h2 id="admin-documents-heading">Documents <span className="ws-count">{data?.total ?? "—"}</span></h2><p>Newest uploads first. Checks every 5 seconds while visible, for up to 5 minutes. Refresh or return to this tab to check again.</p></div><Files size={23} aria-hidden="true" /></div>
      <form className="rq-filters" onSubmit={filter}><label>Status<select name="status" defaultValue={status || ""}><option value="">All statuses</option>{processingStatuses.map(value => <option key={value} value={value}>{statusLabels[value]}</option>)}</select></label><label>Candidate profile ID<input name="profile_id" type="number" min="1" max={Number.MAX_SAFE_INTEGER} step="1" defaultValue={profileId || ""} placeholder="All candidates" /></label><button type="submit" className="ws-button ws-button-primary">Apply filters</button><Link className="ws-text-action" to="/admin/documents">Clear filters</Link></form>
      {error && <div className="ws-notice ws-notice-error" role="alert"><span>{error}</span><button className="ws-text-action" onClick={retry}>Try again</button></div>}
      {loading ? <div className="ws-skeleton-list" role="status"><span className="ws-sr-only">Loading admin documents…</span>{[1, 2, 3].map(row => <div className="ws-skeleton" key={row} />)}</div> : data && !error && <>
        {data.items.length ? <ol className="rq-list ad-list">{data.items.map(file => <li key={file.file_id} className="rq-item">
          <div className="rq-item-title"><Link className="ad-document-link" to={`/admin/documents/${file.file_id}?${params}`}>{file.original_name}<ArrowRight size={16} /><span className="ws-sr-only"> — File #{file.file_id}</span></Link><DocumentStatus status={file.status} /></div>
          <p className="rq-candidate"><strong><Link to={`/admin/candidates/${file.profile_id}`}>{file.candidate_name}</Link></strong> · Candidate user #{file.user_id} · Profile #{file.profile_id}</p>
          <dl className="ad-list-metadata"><div><dt>Document</dt><dd>{fileType(file.file_type, file.original_name)} · File #{file.file_id}</dd></div><div><dt>Uploaded</dt><dd>{formatTimestamp(file.uploaded_at)}</dd></div><div><dt>Attempts</dt><dd>{file.attempts}</dd></div><div><dt>Open reviews</dt><dd>{file.open_reviews}</dd></div></dl>
          {(file.status === "failed" || file.error_message) && <p className="ad-safe-error">{safeProcessingError(file.error_message)}</p>}
        </li>)}</ol> : <div className="ws-empty"><Files size={28} /><h3>{page > 1 ? "No documents on this page" : "No documents found"}</h3><p>{page > 1 ? "Return to the first page to see available documents." : "No documents match the selected filters."}</p>{page > 1 && <button className="ws-button ws-button-secondary" onClick={() => changePage(1)}>Go to first page</button>}</div>}
        {(data.total > 0 || page > 1) && <nav className="rq-pagination" aria-label="Admin document pages"><span className="ws-caption" role="status">{data.items.length ? `${(page - 1) * ADMIN_DOCUMENT_PAGE_SIZE + 1}–${(page - 1) * ADMIN_DOCUMENT_PAGE_SIZE + data.items.length} of ${data.total} documents` : `${data.total} documents`}</span><div><button className="ws-button ws-button-secondary" disabled={page <= 1} onClick={() => changePage(page - 1)}><ArrowLeft size={15} />Previous</button><span className="ws-caption">Page {page} of {pages}</span><button className="ws-button ws-button-secondary" disabled={page >= pages} onClick={() => changePage(page + 1)}>Next<ArrowRight size={15} /></button></div></nav>}
      </>}
    </section>
  </>;
}
