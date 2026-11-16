import { useCallback } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { ArrowLeft, RefreshCw } from "lucide-react";
import { getAdminCandidate } from "../../services/adminWorkspaceService";
import { useRemoteData } from "../../hooks/useRemoteData";
import { formatTimestamp } from "../../utils/dateTime";
import AdminProfileContent from "../../components/admin/AdminProfileContent";
import AdminProfileHistory from "../../components/admin/AdminProfileHistory";
import "./ReviewPages.css";
import "./AdminWorkspace.css";

export default function AdminCandidatePage() {
  const { profileId } = useParams();
  return <CandidateDetails key={profileId} profileId={profileId} />;
}
function CandidateDetails({ profileId }: { profileId?: string }) {
  const location = useLocation();
  const loader = useCallback(() => getAdminCandidate(profileId && /^[1-9]\d*$/.test(profileId) ? Number(profileId) : NaN), [profileId]);
  const { data, loading, error, retry } = useRemoteData(loader);
  const directoryParams = new URLSearchParams(location.search);
  directoryParams.delete("history_page");
  return <>
    <Link className="ws-text-action rq-back" to={"/admin/candidates" + (directoryParams.size ? "?" + directoryParams : "")}><ArrowLeft size={15} />Candidate Management</Link>
    <div className="ws-page-heading"><div><span className="ws-eyebrow">READ-ONLY CANDIDATE PROFILE</span><h1>Candidate Details</h1><p>Available profile information, connected sources and recorded history.</p></div><button className="ws-button ws-button-secondary" disabled={loading} onClick={retry}><RefreshCw size={16} />Refresh profile</button></div>
    {error && <div className="ws-notice ws-notice-error" role="alert"><span>{error}</span><button className="ws-text-action" onClick={retry}>Try again</button></div>}
    {loading ? <div className="ws-skeleton-list" role="status"><span className="ws-sr-only">Loading candidate profile…</span><div className="ws-skeleton" /><div className="ws-skeleton" /></div> : data && !error && <>
      <section className="ws-panel rq-panel aw-profile-header" aria-label="Candidate account"><h2>{data.candidate_name}</h2><p>{data.candidate_email}</p><p className="ws-caption">Profile #{data.profile_id} · Updated {formatTimestamp(data.updated_at)}</p><p>{data.open_reviews} open review {data.open_reviews === 1 ? "item" : "items"}</p><div className="aw-row-links"><Link to={`/admin/documents?profile_id=${data.profile_id}`}>Candidate documents</Link><Link to={`/admin/reviews?profile_id=${data.profile_id}`}>Candidate review items</Link><a href="#candidate-history-heading">Profile history</a></div></section>
      <AdminProfileContent data={data} />
      <AdminProfileHistory profileId={data.profile_id} />
    </>}
  </>;
}

