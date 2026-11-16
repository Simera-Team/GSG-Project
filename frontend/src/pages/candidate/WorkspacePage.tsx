import { Link } from "react-router-dom";
import { ArrowRight, FileText, Files, Plus, RefreshCw, ShieldCheck } from "lucide-react";
import { getCurrentUser } from "../../services/authService";
import { getCandidateOverview, overviewNeedsRefresh } from "../../services/workspaceService";
import { useRemoteData } from "../../hooks/useRemoteData";
import { statusLabels, fileType } from "../../utils/documents";
import { formatTimestamp } from "../../utils/dateTime";
import type { FileStatus } from "../../services/fileService";
import DocumentStatus from "../../components/common/DocumentStatus";
import "./WorkspacePage.css";

const statuses: FileStatus[] = ["uploaded", "processing", "done", "needs_review", "failed"];

export default function WorkspacePage() {
  const account = useRemoteData(getCurrentUser);
  const overview = useRemoteData(getCandidateOverview, 5000, overviewNeedsRefresh);
  const documents = { ...overview, data: overview.data?.documents, error: overview.error || overview.data?.documentsError };
  const profile = { ...overview, data: overview.data?.profile, error: overview.error || overview.data?.profileError };
  const name = account.data?.name?.trim() || profile.data?.candidate_name?.trim();
  const summary = documents.data;
  const isNew = summary?.total === 0;

  return <>
    <div className="ws-page-heading">
      <div>
        <span className="ws-eyebrow">YOUR CANDIDATE WORKSPACE</span>
        <h1>{name ? `Welcome, ${name}.` : "Your workspace"}</h1>
        <p>Your documents, processing updates and professional profile in one place.</p>
      </div>
      {!isNew && <Link to="/upload" className="ws-button ws-button-primary"><Plus size={17} />Upload New Document</Link>}
    </div>

    {account.error && <div className="ws-notice ws-notice-error" role="alert"><span>{account.error}</span><button className="ws-text-action" onClick={account.retry}>Try again</button></div>}
    {documents.error && <div className="ws-notice ws-notice-error" role="alert"><span>{documents.error} {summary && "The last loaded summary is still shown."}</span><button className="ws-text-action" onClick={documents.retry}>Try again</button></div>}

    {isNew ? <section className="ws-panel ws-empty ov-onboarding" aria-labelledby="first-upload-heading">
      <span className="ws-icon-tile"><Files size={27} aria-hidden="true" /></span>
      <h2 id="first-upload-heading">Your workspace is ready</h2>
      <p>Start with your resume or a LinkedIn Markdown export. You can follow its processing and view the information added to your profile.</p>
      <Link to="/upload" className="ws-button ws-button-primary">Upload your first document<ArrowRight size={17} /></Link>
      <Link to="/profile" className="ws-text-action ov-empty-profile">View My Profile<ArrowRight size={15} /></Link>
    </section> : <div className="ov-grid">
      <section className="ws-panel ov-documents-summary" aria-labelledby="overview-documents-heading" aria-busy={documents.loading}>
        <div className="ws-section-heading">
          <div><h2 id="overview-documents-heading">Your documents {summary && <span className="ws-count">{summary.total}</span>}</h2><p>A summary of all your uploaded documents.</p></div>
          <button className="ws-button ws-button-quiet" disabled={documents.loading} onClick={() => { documents.retry(); profile.retry(); }}><RefreshCw size={15} />Refresh</button>
        </div>
        {documents.loading ? <div className="ws-skeleton-list" role="status"><span className="ws-sr-only">Loading your document summary…</span>{[1,2,3].map(row => <div className="ws-skeleton" key={row} />)}</div> : summary ? <>
          <dl className="ov-status-counts" aria-label="Documents by processing status">
            {statuses.map(status => <div key={status} data-status={status}><dt>{statusLabels[status]}</dt><dd>{summary.counts[status]}</dd></div>)}
          </dl>
          <section className="ov-recent" aria-labelledby="recent-documents-heading">
            <div className="ov-recent-heading"><h3 id="recent-documents-heading">Recent Documents</h3><Link to="/documents" className="ws-text-action">My Documents<ArrowRight size={15} /></Link></div>
            <div className="ov-recent-list">{summary.recent.map(file => <Link to={`/files/${file.file_id}`} className="ov-recent-row" key={file.file_id} aria-label={`View details for ${file.original_name}`}>
              <FileText size={19} aria-hidden="true" />
              <div><strong>{file.original_name}</strong><span>{fileType(file.file_type,file.original_name)} · {formatTimestamp(file.uploaded_at)}</span></div>
              <DocumentStatus status={file.status} /><ArrowRight size={14} aria-hidden="true" />
            </Link>)}</div>
          </section>
          <p className="ws-caption ov-poll-note">Active processing refreshes every 5 seconds while visible, for up to 5 minutes. Return to this tab or use Refresh to check again.</p>
        </> : <p className="ws-muted">Your document summary is unavailable. You can still <Link to="/documents">open My Documents</Link> or upload a document.</p>}
      </section>

      <section className="ws-panel ov-profile" aria-labelledby="overview-profile-heading">
        <span className="ws-icon-tile"><ShieldCheck size={21} aria-hidden="true" /></span>
        <h2 id="overview-profile-heading">My Profile</h2>
        {profile.loading ? <p className="ws-muted" role="status">Loading profile status…</p> : profile.error ? <div className="ws-notice ws-notice-error" role="alert"><span>{profile.error}</span><button className="ws-text-action" onClick={profile.retry}>Try again</button></div> : <>
          <p>{profile.data?.profile ? "View the experience, skills and education added from your processed documents." : "Your profile grows as documents are processed. Your account information is available even before your first document is complete."}</p>
          {profile.data && <div className="ov-review-status"><strong>{profile.data.open_reviews > 0 ? `${profile.data.open_reviews} ${profile.data.open_reviews === 1 ? "item awaiting" : "items awaiting"} review` : "No open reviews"}</strong><span>Uncertain or conflicting details may need review before they join your profile.</span></div>}
        </>}
        <Link to="/profile" className="ws-text-action">View My Profile<ArrowRight size={15} /></Link>
      </section>
    </div>}
  </>;
}
