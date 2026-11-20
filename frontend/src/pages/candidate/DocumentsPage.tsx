import { useCallback } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowLeft, ArrowRight, Files, Plus, RefreshCw } from "lucide-react";
import { getCandidateFiles } from "../../services/fileService";
import { useRemoteData } from "../../hooks/useRemoteData";
import { fileType } from "../../utils/documents";
import { formatTimestamp } from "../../utils/dateTime";
import DocumentStatus from "../../components/common/DocumentStatus";
import "./DocumentsPage.css";

const PAGE_SIZE = 20;

function DocumentList({ page, onPageChange }: {
  page: number;
  onPageChange: (page: number) => void;
}) {
  const loader = useCallback(() => getCandidateFiles(PAGE_SIZE, (page - 1) * PAGE_SIZE), [page]);
  const { data, loading, error, retry } = useRemoteData(loader, 5000);
  const totalPages = Math.max(1, Math.ceil((data?.total || 0) / PAGE_SIZE));

  return <>
    <div className="ws-page-heading">
      <div>
        <span className="ws-eyebrow">YOUR DOCUMENT LIBRARY</span>
        <h1>My Documents</h1>
        <p>Manage your uploaded documents and follow their processing status.</p>
      </div>
      <Link to="/upload" className="ws-button ws-button-primary">
        <Plus size={17} />Upload New Document
      </Link>
    </div>

    <section className="ws-panel up-documents" aria-labelledby="documents-heading">
      <div className="ws-section-heading">
        <div>
          <h2 id="documents-heading">Document library <span className="ws-count">{data?.total ?? "—"}</span></h2>
          <p>Status refreshes every 5 seconds while visible, for up to 5 minutes. Refresh or return to this tab to check again.</p>
        </div>
        <button type="button" className="ws-button ws-button-quiet" disabled={loading} onClick={retry}>
          <RefreshCw size={15} />Refresh
        </button>
      </div>

      {error && <div className="ws-notice ws-notice-error" role="alert">
        <span>{error} {data && "The last loaded documents are still shown."}</span>
        <button type="button" className="ws-text-action" onClick={retry}>Try again</button>
      </div>}

      {loading ? <div className="ws-skeleton-list" role="status" aria-label="Loading documents">
        {[1, 2, 3].map(row => <div className="ws-skeleton" key={row} />)}
        <span className="ws-sr-only">Loading documents…</span>
      </div> : data?.items.length ? <>
        <div className="up-table-wrap">
          <table className="up-document-table">
            <caption className="ws-sr-only">Uploaded documents and their processing statuses</caption>
            <thead><tr>
              <th scope="col">Document</th>
              <th scope="col">Uploaded</th>
              <th scope="col">Status</th>
              <th scope="col"><span className="ws-sr-only">Actions</span></th>
            </tr></thead>
            <tbody>{data.items.map(file => <tr key={file.file_id}>
              <td><div className="up-table-file">
                <span className="up-type-icon">{fileType(file.file_type, file.original_name)}</span>
                <div>
                  <Link to={`/files/${file.file_id}`} className="up-file-name">{file.original_name}</Link>
                  <span>{fileType(file.file_type, file.original_name)} document</span>
                </div>
              </div></td>
              <td className="up-date">{formatTimestamp(file.uploaded_at)}</td>
              <td><DocumentStatus status={file.status} /></td>
              <td><Link className="ws-text-action up-details-link" to={`/files/${file.file_id}`} aria-label={`View details for ${file.original_name}`}>
                View Details <ArrowRight size={14} />
              </Link></td>
            </tr>)}</tbody>
          </table>
        </div>
      </> : !error && <div className="ws-empty">
        <span className="ws-icon-tile"><Files size={28} /></span>
        <h3>{data?.total || page > 1 ? "No documents on this page" : "No documents yet"}</h3>
        <p>{data?.total || page > 1 ? "Return to the first page to see your available documents." : "Upload your first document to start building your professional profile."}</p>
        {data?.total || page > 1 ? <button type="button" className="ws-button ws-button-secondary" onClick={() => onPageChange(1)}>Go to first page</button> : <Link to="/upload" className="ws-button ws-button-secondary">Upload New Document <ArrowRight size={16} /></Link>}
      </div>}

      {!loading && data && (data.total > 0 || page > 1) && <nav className="doc-pagination" aria-label="Document pages">
        <span className="ws-caption">{data.items.length ? `${(page - 1) * PAGE_SIZE + 1}–${(page - 1) * PAGE_SIZE + data.items.length} of ${data.total} documents` : `${data.total} documents`}</span>
        <div>
          <button type="button" className="ws-button ws-button-secondary" disabled={page <= 1} onClick={() => onPageChange(page - 1)}><ArrowLeft size={14} />Previous</button>
          <span className="ws-caption" aria-current="page">Page {page} of {totalPages}</span>
          <button type="button" className="ws-button ws-button-secondary" disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>Next<ArrowRight size={14} /></button>
        </div>
      </nav>}

      <div className="up-document-footer">

        <span>Original-file preview and download are not available yet.</span>
      </div>
    </section>
  </>;
}

export default function DocumentsPage() {
  const [params, setParams] = useSearchParams();
  const value = params.get("page") || "1";
  const requested = Number(value);
  const page = /^\d+$/.test(value) && Number.isSafeInteger(requested) && requested > 0 && Number.isSafeInteger(requested * PAGE_SIZE) ? requested : 1;

  function changePage(nextPage: number) {
    setParams(previous => {
      const next = new URLSearchParams(previous);
      if (nextPage === 1) next.delete("page");
      else next.set("page", String(nextPage));
      return next;
    });
    window.scrollTo(0, 0);
  }

  return <DocumentList key={page} page={page} onPageChange={changePage} />;
}