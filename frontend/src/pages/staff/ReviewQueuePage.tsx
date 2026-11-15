import { useCallback, useSyncExternalStore, type FormEvent } from "react";
import { Link, useLocation, useOutletContext, useSearchParams } from "react-router-dom";
import { ArrowLeft, ArrowRight, ListChecks, RefreshCw } from "lucide-react";
import { getReviewItems, getReviewRevision, subscribeReviewChanges } from "../../services/reviewService";
import { useRemoteData } from "../../hooks/useRemoteData";
import { confidenceLabel, parseReviewQuery, reasonLabel, REVIEW_PAGE_SIZE, reviewReasons, reviewStatus } from "../../utils/reviews";
import { formatTimestamp } from "../../utils/dateTime";
import { safeReviewContext } from "../../utils/reviewDecisions";
import "./ReviewPages.css";

export default function ReviewQueuePage() {
  const { queuePath } = useOutletContext<{ queuePath: string }>();
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const reviewRevision = useSyncExternalStore(subscribeReviewChanges, getReviewRevision, getReviewRevision);
  const { status, reason, profileId, page } = parseReviewQuery(params);
  const loader = useCallback(() => getReviewItems({ status, reason, profileId, limit: REVIEW_PAGE_SIZE, offset: (page - 1) * REVIEW_PAGE_SIZE }), [status, reason, profileId, page]);
  // No stale rows remain actionable while a changed filter is loading.
  return <Queue key={location.key + params.toString() + ":" + reviewRevision} loader={loader} queuePath={queuePath} params={params} setParams={setParams} />;
}

function Queue({ loader, queuePath, params, setParams }: {
  loader: () => ReturnType<typeof getReviewItems>;
  queuePath: string;
  params: URLSearchParams;
  setParams: (params: URLSearchParams) => void;
}) {
  const { status, reason, profileId, page } = parseReviewQuery(params);
  const { data, loading, error, retry } = useRemoteData(loader);
  const pages = Math.max(1, Math.ceil((data?.total || 0) / REVIEW_PAGE_SIZE));
  function filter(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const next = new URLSearchParams();
    for (const key of ["status", "reason", "profile_id"]) {
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
    <div className="ws-page-heading"><div><span className="ws-eyebrow">REVIEW WORKSPACE</span><h1>Manual Review Queue</h1><p>Inspect flagged fields and failed documents alongside their source evidence.</p></div><button className="ws-button ws-button-secondary" disabled={loading} onClick={retry}><RefreshCw size={16} />Refresh queue</button></div>
    <section className="ws-panel rq-panel" aria-labelledby="review-queue-heading">
      <div className="ws-section-heading"><div><h2 id="review-queue-heading">Review items <span className="ws-count">{data?.total ?? "—"}</span></h2><p>Oldest first. Open items include those waiting for the candidate.</p></div><ListChecks size={23} aria-hidden="true" /></div>
      <form className="rq-filters" onSubmit={filter}>
        <label>Status<select name="status" defaultValue={status}><option value="open">Open</option><option value="waiting_candidate">Waiting for candidate</option><option value="resolved">Resolved</option><option value="all">All statuses</option></select></label>
        <label>Reason<select name="reason" defaultValue={reason}><option value="">All reasons</option>{reason && !Object.hasOwn(reviewReasons, reason) && <option value={reason}>{reasonLabel(reason)}</option>}{Object.entries(reviewReasons).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
        <label>Candidate profile ID<input name="profile_id" type="number" min="1" step="1" max={Number.MAX_SAFE_INTEGER} defaultValue={profileId || ""} placeholder="All candidates" /></label>
        <button className="ws-button ws-button-primary" type="submit">Apply filters</button>
        <Link className="ws-text-action" to={queuePath}>Clear filters</Link>
      </form>
      {error && <div className="ws-notice ws-notice-error" role="alert"><span>{error}</span><button className="ws-text-action" onClick={retry}>Try again</button></div>}
      {loading ? <div className="ws-skeleton-list" role="status"><span className="ws-sr-only">Loading review items…</span>{[1, 2, 3].map(row => <div className="ws-skeleton" key={row} />)}</div> : data && !error && <>
        {data.items.length ? <ol className="rq-list">{data.items.map(item => <li key={item.review_id} className="rq-item">
          <div className="rq-item-title"><Link to={`${queuePath}/${item.review_id}?${params}`}>{item.is_failed_job ? "Failed document" : item.field_name || "Field review"}<ArrowRight size={16} /><span className="ws-sr-only"> — Review #{item.review_id}</span></Link><span className={`rq-status ${item.resolved ? "is-resolved" : ""}`}>{reviewStatus(item)}</span></div>
          <p className="rq-candidate"><strong>{queuePath === "/admin/reviews" ? <Link to={`/admin/candidates/${item.profile_id}`}>{item.candidate_name}</Link> : item.candidate_name}</strong> · {item.candidate_email} · Profile #{item.profile_id}</p>
          <p className="ws-caption">{item.entity || "Document-level review"} · {item.file_name} · File #{item.file_id} · {formatTimestamp(item.created_at)}</p>
          <ul className="rq-reasons" aria-label="Review reasons">{item.reasons.map(value => <li key={value}>{reasonLabel(value)}</li>)}</ul>
          {item.is_failed_job && <p className="ws-muted">{safeReviewContext(item)}</p>}
          <p className="rq-confidence">{item.options.length ? item.options.map((option, index) => `Option ${index + 1}: ${confidenceLabel(option.confidence)}`).join(" · ") : "Confidence: Not available"}</p>
        </li>)}</ol> : <div className="ws-empty"><ListChecks size={30} /><h3>{page > 1 ? "No items on this page" : "No review items found"}</h3><p>{page > 1 ? "Return to the first page to see available items." : "There are no review items matching these filters."}</p>{page > 1 && <button className="ws-button ws-button-secondary" onClick={() => changePage(1)}>Go to first page</button>}</div>}
        {(data.total > 0 || page > 1) && <nav className="rq-pagination" aria-label="Review queue pages"><span className="ws-caption" role="status">{data.items.length ? `${(page - 1) * REVIEW_PAGE_SIZE + 1}–${(page - 1) * REVIEW_PAGE_SIZE + data.items.length} of ${data.total} items` : `${data.total} items`}</span><div><button className="ws-button ws-button-secondary" disabled={page <= 1} onClick={() => changePage(page - 1)}><ArrowLeft size={15} />Previous</button><span className="ws-caption">Page {page} of {pages}</span><button className="ws-button ws-button-secondary" disabled={page >= pages} onClick={() => changePage(page + 1)}>Next<ArrowRight size={15} /></button></div></nav>}
      </>}
    </section>
  </>;
}
