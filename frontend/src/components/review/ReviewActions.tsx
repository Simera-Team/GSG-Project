import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { ApiError, friendlyError } from "../../services/apiClient";
import { requestCandidateClarification, resolveReviewItem, type CandidateClarification, type ResolveRequest, type ReviewItem } from "../../services/reviewService";
import { buildResolveRequest, correctionHint, isSkillNameReview } from "../../utils/reviewDecisions";

type Pending = { kind: "resolve"; request: ResolveRequest } | { kind: "clarification" };
interface Props {
  item: ReviewItem;
  disabled: boolean;
  onBusy: (busy: boolean) => void;
  onSaved: (item: ReviewItem, clarification?: CandidateClarification) => void;
  onConflict: (message: string) => void;
}
export default function ReviewActions({ item, disabled, onBusy, onSaved, onConflict }: Props) {
  const [action, setAction] = useState<ResolveRequest["action"]>(item.is_failed_job ? "dismiss" : item.options.length ? "option" : "custom");
  const [optionId, setOptionId] = useState("");
  const [value, setValue] = useState("");
  const [skillMode, setSkillMode] = useState("approve");
  const [mapping, setMapping] = useState("");
  const [pending, setPending] = useState<Pending | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [mustRefresh, setMustRefresh] = useState(false);
  const submitting = useRef(false);
  const mounted = useRef(true);
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement | null>(null);
  const id = useId();
  const skill = isSkillNameReview(item);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    if (pending && !dialog.current?.open) dialog.current?.showModal();
    if (!pending && dialog.current?.open) dialog.current.close();
  }, [pending]);
  if (item.resolved) return null;
  const locked = disabled || busy || mustRefresh;
  function prepare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (locked || submitting.current) return;
    trigger.current = event.currentTarget.querySelector<HTMLButtonElement>('button[type="submit"]');
    setError("");
    try {
      const request = buildResolveRequest(item, action, optionId, value, skill && skillMode === "map" && (action === "option" || action === "custom") ? mapping : null);
      setPending({ kind: "resolve", request });
    } catch (cause) { setError(friendlyError(cause)); }
  }
  async function confirm() {
    if (!pending || submitting.current || locked) return;
    submitting.current = true; setBusy(true); onBusy(true); setError("");
    try {
      const result = pending.kind === "resolve" ? await resolveReviewItem(item.review_id, pending.request) : await requestCandidateClarification(item.review_id);
      if (!mounted.current) return;
      setPending(null);
      onBusy(false);
      if ("item" in result) onSaved(result.item, result);
      else onSaved(result);
    } catch (cause) {
      if (!mounted.current) return;
      setPending(null);
      const message = friendlyError(cause, "We couldn't confirm the change. Refresh this item before retrying.");
      if (cause instanceof ApiError && cause.status === 409) onConflict(message);
      else {
        setError(message);
        if (!(cause instanceof ApiError) || cause.status === 0 || cause.status >= 500 || cause.status === 403) setMustRefresh(true);
      }
    } finally {
      submitting.current = false;
      if (mounted.current) { setBusy(false); onBusy(false); }
    }
  }
  const request = pending?.kind === "resolve" ? pending.request : null;
  const selected = request?.action === "option" ? item.options.find(option => option.option_id === request.option_id) : null;
  const summaryValue = request?.action === "custom" ? request.value : selected?.value;
  return <section className="ws-panel rq-panel rq-actions" aria-labelledby={id + "-heading"}>
    <h2 id={id + "-heading"}>{item.is_failed_job ? "Failed document action" : "Review decision"}</h2>
    <p className="ws-muted">{item.is_failed_job ? "Dismissal closes this queue item. It does not retry the document or repair extraction." : "A confirmed decision is recorded with your identity and applied to the profile."}</p>
    {error && <p className="ws-notice ws-notice-error" role="alert">{error}{mustRefresh && " Use Refresh item before attempting another change."}</p>}
    <form onSubmit={prepare}>
      <fieldset disabled={locked}>
        <legend className="ws-sr-only">Choose a review decision</legend>
        <label htmlFor={id + "-action"}>Decision</label>
        <select id={id + "-action"} value={action} onChange={event => setAction(event.target.value as ResolveRequest["action"])}>
          {item.is_failed_job ? <option value="dismiss">Dismiss failed document</option> : <>
            {item.options.length > 0 && <option value="option">Select an existing alternative</option>}
            <option value="custom">Enter a custom correction</option>
            <option value="reject">Reject this field</option>
          </>}
        </select>
        {action === "option" && <fieldset className="rq-alternatives"><legend>Choose an alternative</legend>{item.options.map((option, index) => <label className="rq-radio" key={option.option_id}><input type="radio" name={id + "-option"} value={option.option_id} checked={optionId === String(option.option_id)} onChange={event => setOptionId(event.target.value)} /><span>Option {index + 1}: {option.value ?? "No value supplied"}</span></label>)}</fieldset>}
        {action === "custom" && <><label htmlFor={id + "-value"}>Corrected value</label><textarea id={id + "-value"} value={value} onChange={event => setValue(event.target.value)} maxLength={5000} rows={3} aria-describedby={id + "-hint"} /><p id={id + "-hint"} className="ws-caption">{correctionHint(item)}</p></>}
        {skill && (action === "option" || action === "custom") && <div className="rq-skill-mapping"><label htmlFor={id + "-skill"}>Skill handling</label><select id={id + "-skill"} value={skillMode} onChange={event => setSkillMode(event.target.value)}><option value="approve">Approve skill name</option><option value="map">Map to an existing standard skill</option></select>{skillMode === "map" ? <><label htmlFor={id + "-mapping"}>Existing standard skill name</label><input id={id + "-mapping"} value={mapping} maxLength={100} onChange={event => setMapping(event.target.value)} /><p className="ws-caption">Enter the standard name. The server checks it and saves the alias for future sources.</p></> : <p className="ws-caption">Approving an unknown skill adds it to the shared standard skill list.</p>}</div>}
        {action === "reject" && <p className="ws-caption">The field will remain empty. The source evidence stays in the audit trail.</p>}
        <button ref={trigger} className="ws-button ws-button-primary" type="submit">{busy ? "Saving…" : "Review and confirm"}</button>
      </fieldset>
    </form>
    <div className="rq-clarification-action"><h3>Candidate clarification</h3><p className="ws-caption">Prepare a message and record that this item is waiting for the candidate. CVerge does not send email.</p><button className="ws-button ws-button-secondary" disabled={locked || item.assigned_to_candidate} onClick={event => { trigger.current = event.currentTarget; setError(""); setPending({ kind: "clarification" }); }}>{item.assigned_to_candidate ? "Already waiting for candidate" : "Prepare clarification request"}</button></div>
    <dialog ref={dialog} className="rq-confirm-dialog" aria-labelledby={id + "-confirm-heading"} aria-describedby={id + "-confirm-description"} onCancel={event => { if (busy) event.preventDefault(); else setPending(null); }} onClose={() => { if (!dialog.current?.open) trigger.current?.focus(); }}>
      <h2 id={id + "-confirm-heading"}>{pending?.kind === "clarification" ? "Record a clarification request?" : request?.action === "dismiss" ? "Dismiss this failed document?" : request?.action === "reject" ? "Reject this field?" : "Apply this review decision?"}</h2>
      <p id={id + "-confirm-description"}>{pending?.kind === "clarification" ? "This records a waiting-for-candidate state and prepares suggested text. No email will be sent." : request?.action === "dismiss" ? "This closes the review item without changing the profile or restarting processing." : request?.action === "reject" ? "This records your decision and leaves this field empty." : "This records your decision and rebuilds the candidate profile using the confirmed value."}</p>
      {summaryValue != null && <p className="rq-confirm-value">{summaryValue}</p>}
      {request && "map_to_skill" in request && request.map_to_skill && <p>Map to: <strong>{request.map_to_skill}</strong>. This alias will be reused for future sources.</p>}
      {skill && request && (request.action === "option" || request.action === "custom") && !request.map_to_skill && <p>An unknown approved skill will be added to the shared standard skill list.</p>}
      <div className="rq-confirm-buttons"><button type="button" className="ws-button ws-button-secondary" autoFocus disabled={busy} onClick={() => setPending(null)}>Cancel</button><button type="button" className="ws-button ws-button-primary" disabled={busy || disabled} onClick={() => void confirm()}>{busy ? "Saving…" : "Confirm"}</button></div>
    </dialog>
  </section>;
}
