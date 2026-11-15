import { Link } from "react-router-dom";
import { ArrowRight, RefreshCw } from "lucide-react";
import { getAdminDashboard } from "../../services/adminWorkspaceService";
import { processingStatuses } from "../../services/adminFileService";
import { useRemoteData } from "../../hooks/useRemoteData";
import { dashboardRate } from "../../utils/adminCandidates";
import { statusLabels } from "../../utils/documents";
import "./ReviewPages.css";
import "./AdminWorkspace.css";

export default function AdminDashboardPage() {
  const { data, loading, error, retry } = useRemoteData(getAdminDashboard);
  return <>
    <div className="ws-page-heading"><div><span className="ws-eyebrow">ADMIN WORKSPACE</span><h1>Admin Dashboard</h1><p>A system overview from the backend's recorded accounts, documents and reviews.</p></div><button className="ws-button ws-button-secondary" disabled={loading} onClick={retry}><RefreshCw size={16} />Refresh dashboard</button></div>
    <nav className="aw-quick-links" aria-label="Admin destinations"><Link to="/admin/reviews">Review Queue<ArrowRight size={16} /></Link><Link to="/admin/documents">Documents &amp; Processing<ArrowRight size={16} /></Link><Link to="/admin/candidates">Candidate Management<ArrowRight size={16} /></Link><Link to="/admin/staff">Staff Management<ArrowRight size={16} /></Link></nav>
    {error && <div className="ws-notice ws-notice-error" role="alert"><span>{error}</span><button className="ws-text-action" onClick={retry}>Try again</button></div>}
    {loading ? <div className="ws-skeleton-list" role="status"><span className="ws-sr-only">Loading admin dashboard…</span>{[1, 2, 3].map(value => <div className="ws-skeleton" key={value} />)}</div> : data && !error && <>
      <section className="aw-summary" aria-label="System totals">
        <article className="ws-panel aw-card"><span>Registered candidate accounts</span><strong>{data.candidates}</strong><p>Includes accounts without uploaded documents.</p></article>
        <article className="ws-panel aw-card"><span>Documents</span><strong>{data.files_total}</strong><p>All recorded source documents.</p></article>
        <article className="ws-panel aw-card"><span>Open review items</span><strong>{data.open_reviews}</strong><Link to="/admin/reviews?status=open">Open queue<ArrowRight size={14} /></Link></article>
        <article className="ws-panel aw-card"><span>Resolved review items</span><strong>{data.resolved_reviews}</strong><Link to="/admin/reviews?status=resolved">View resolved items<ArrowRight size={14} /></Link></article>
      </section>
      {data.files_total === 0 && <p className="ws-notice" role="status">No documents have been uploaded yet. Candidate accounts may already exist.</p>}
      <section className="ws-panel rq-panel" aria-labelledby="dashboard-processing-heading"><h2 id="dashboard-processing-heading">Documents by processing status</h2><dl className="aw-statuses">{processingStatuses.map(status => <div key={status}><dt><Link to={`/admin/documents?status=${status}`}>{statusLabels[status]}</Link></dt><dd>{data.files_by_status[status]}</dd></div>)}</dl></section>
      <section className="ws-panel rq-panel" aria-labelledby="dashboard-quality-heading"><h2 id="dashboard-quality-heading">Recorded extraction quality</h2><dl className="rq-context"><div><dt>Valid on first try</dt><dd>{dashboardRate(data.valid_on_first_try_rate)}</dd></div><div><dt>Average field confidence</dt><dd>{dashboardRate(data.average_confidence)}</dd></div><div><dt>Fields sent to review</dt><dd>{dashboardRate(data.share_of_fields_sent_to_review)}</dd></div><div><dt>Reviews with typed corrections</dt><dd>{data.reviews_with_typed_correction}</dd></div><div><dt>Total extraction attempts</dt><dd>{data.llm_attempts}</dd></div><div><dt>Unsuccessful extraction attempts</dt><dd>{data.llm_failed_attempts}</dd></div><div><dt>Files reaching three processing attempts</dt><dd>{data.files_that_hit_3_attempts}</dd></div><div><dt>Extracted field records</dt><dd>{data.field_records}</dd></div></dl><p className="ws-caption">Fields sent to review includes all review reasons. Typed corrections are a count, not the share of reviewed values changed. The three-attempt count excludes administrator reruns. Unavailable rates mean there are no applicable records.</p></section>
      <p className="ws-caption">These totals come from the dashboard aggregation endpoint, not a paginated document list. Use Refresh dashboard to request current values.</p>
    </>}
  </>;
}

