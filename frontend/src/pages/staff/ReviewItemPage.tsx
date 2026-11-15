import { useCallback, useState } from "react";
import { Link, useLocation, useOutletContext, useParams } from "react-router-dom";
import { ArrowLeft, RefreshCw } from "lucide-react";
import { getReviewItem, type CandidateClarification, type ReviewItem } from "../../services/reviewService";
import { useRemoteData } from "../../hooks/useRemoteData";
import { confidenceLabel, reasonLabel, reviewStatus } from "../../utils/reviews";
import { formatTimestamp } from "../../utils/dateTime";
import ReviewActions from "../../components/review/ReviewActions";
import { clarificationMailto, safeReviewContext } from "../../utils/reviewDecisions";
import "./ReviewPages.css";

export default function ReviewItemPage() {
  const { reviewId } = useParams();
  return <ReviewItemDetails key={reviewId} reviewId={reviewId} />;
}
function ReviewItemDetails({ reviewId }: { reviewId?: string }) {
  const { queuePath, role } = useOutletContext<{ queuePath: string; role?: string }>();
  const location = useLocation();
  const loader = useCallback(() => getReviewItem(reviewId && /^[1-9]\d*$/.test(reviewId) ? Number(reviewId) : NaN), [reviewId]);
  const { data, loading, error, retry } = useRemoteData(loader);
  const [snapshot, setSnapshot] = useState<{ item: ReviewItem; replacedData: ReviewItem | null } | null>(null);
  const [clarification, setClarification] = useState<CandidateClarification | null>(null);
  const [notice, setNotice] = useState("");
  const [conflict, setConflict] = useState("");
  const [busy, setBusy] = useState(false);
  const [actionVersion, setActionVersion] = useState(0);
  const item = snapshot && (!data || data === snapshot.replacedData) ? snapshot.item : data;
  function refresh() {
    setSnapshot(item ? { item, replacedData: data } : null);
    setActionVersion(version => version + 1);
    retry();
  }
  function saved(updated: ReviewItem, message?: CandidateClarification) {
    setBusy(false);
    setSnapshot({ item: updated, replacedData: data });
    setClarification(message || null);
    setConflict("");
    setNotice(message ? "Clarification recorded. No email was sent. Send the suggested message yourself." : "Your decision was saved. The recorded status and decision are shown below.");
    setActionVersion(version => version + 1);
    retry();
  }
  const back = queuePath + location.search;
  const emailDraft = clarification ? clarificationMailto(clarification.candidate_email, clarification.suggested_message) : null;
  return <>
    <Link to={back} className="ws-text-action rq-back"><ArrowLeft size={15} />Manual Review Queue</Link>
    <div className="ws-page-heading"><div><span className="ws-eyebrow">SOURCE EVIDENCE AND CONTEXT</span><h1>Review Item Details</h1><p>Compare the available source values and evidence.</p></div><button className="ws-button ws-button-secondary" disabled={loading || busy} onClick={refresh}><RefreshCw size={16} />Refresh item</button></div>
    {notice && <p className="ws-notice ws-notice-success" role="status">{notice}</p>}
    {conflict && <p className="ws-notice ws-notice-error" role="alert">{conflict}</p>}
    {error && <div className="ws-notice ws-notice-error" role="alert"><span>{error}</span><button className="ws-text-action" disabled={busy} onClick={refresh}>Try again</button></div>}
    {loading && !snapshot ? <div className="ws-panel rq-panel" role="status"><span className="ws-sr-only">Loading review item…</span><div className="ws-skeleton" /><div className="ws-skeleton" /></div> : item && (!error || snapshot) && <>
      <section className="ws-panel rq-panel" aria-labelledby="review-context-heading">
        <div className="ws-section-heading"><h2 id="review-context-heading">Review #{item.review_id}</h2><span className={`rq-status ${item.resolved ? "is-resolved" : ""}`}>{reviewStatus(item)}</span></div>
        <dl className="rq-context"><div><dt>Candidate</dt><dd>{role === "administrator" ? <Link to={`/admin/candidates/${item.profile_id}`}>{item.candidate_name}</Link> : item.candidate_name}<br />{item.candidate_email}<br />Profile #{item.profile_id}</dd></div><div><dt>Field</dt><dd>{item.is_failed_job ? "Failed document — no field to review" : item.field_name || "Not available"}<br />{item.entity || "Document-level review"}</dd></div><div><dt>Source document</dt><dd>{role === "administrator" ? <Link to={`/admin/documents/${item.file_id}`}>{item.file_name}</Link> : item.file_name}<br />{item.file_type.toUpperCase()} · File #{item.file_id}</dd></div><div><dt>Created</dt><dd>{formatTimestamp(item.created_at)}</dd></div></dl>
        <ul className="rq-reasons" aria-label="Review reasons">{item.reasons.map(reason => <li key={reason}>{reasonLabel(reason)}</li>)}</ul>
        <div className="rq-message"><h3>Review context</h3><p>{safeReviewContext(item)}</p></div>
        {item.sent_to_candidate_at && <p className="ws-caption">Clarification recorded: {formatTimestamp(item.sent_to_candidate_at)}</p>}
      </section>
      <section className="rq-evidence-section" aria-labelledby="review-evidence-heading"><h2 id="review-evidence-heading">Source values and evidence <span className="ws-count">{item.options.length}</span></h2>
        {item.options.length ? <div className="rq-options">{item.options.map((option, index) => <article className="ws-panel rq-option" key={option.option_id}>
          <div className="ws-section-heading"><h3>Option {index + 1}</h3><span className="ws-caption">Confidence: {confidenceLabel(option.confidence)}</span></div>
          <dl><div><dt>Extracted value</dt><dd className="rq-value">{option.value ?? "No value supplied"}</dd></div><div><dt>Source</dt><dd>{option.file_name}<br />{option.file_type.toUpperCase()} · File #{option.file_id}{option.field_id !== null && <><br />Field record #{option.field_id}</>}</dd></div><div><dt>Evidence{option.page !== null ? ` · Page ${option.page}` : ""}</dt><dd>{option.evidence ? <blockquote>{option.evidence}</blockquote> : "No evidence snippet supplied."}</dd></div></dl>
        </article>)}</div> : <div className="ws-panel ws-empty"><h3>No field alternatives supplied</h3><p>{item.is_failed_job ? "This item concerns a failed document. The source reference and review context are shown above." : "This review item has no source values or evidence to display."}</p></div>}
      </section>
      {item.resolved && <section className="ws-panel rq-panel" aria-labelledby="review-resolution-heading"><h2 id="review-resolution-heading">Recorded resolution</h2><dl className="rq-context"><div><dt>Decision</dt><dd>{item.resolution ? reasonLabel(item.resolution) : "Not available"}{item.resolved_option_id !== null && ` · Option #${item.resolved_option_id}`}</dd></div><div><dt>Final value</dt><dd className="rq-value">{item.resolved_value ?? "No value recorded"}</dd></div><div><dt>Reviewer</dt><dd>{item.resolved_by_name || (item.resolved_by !== null ? `Reviewer #${item.resolved_by}` : "Not available")}</dd></div><div><dt>Resolved</dt><dd>{formatTimestamp(item.resolved_at)}</dd></div></dl></section>}
      <ReviewActions key={actionVersion} item={item} disabled={loading || !!error} onBusy={setBusy} onSaved={saved} onConflict={message => { setBusy(false); setConflict(message); refresh(); }} />
      {clarification && <section className="ws-panel rq-panel rq-clarification-message" aria-labelledby="clarification-heading"><h2 id="clarification-heading">Suggested candidate message</h2><p className="ws-caption">CVerge has not sent an email. Review this text and send it using your email application.</p><p>To: {clarification.candidate_email}</p><label htmlFor="clarification-text">Message</label><textarea id="clarification-text" value={clarification.suggested_message} readOnly rows={6} />{emailDraft && <a className="ws-button ws-button-secondary" href={emailDraft}>Open email draft</a>}</section>}
      {item.assigned_to_candidate && !item.resolved && !clarification && <p className="ws-caption">This item is recorded as waiting for the candidate. CVerge does not send email.</p>}
      <p className="ws-caption">Original document preview is unavailable here.</p>
    </>}
  </>;
}
