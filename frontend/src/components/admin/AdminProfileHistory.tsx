import { useCallback } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { ArrowLeft, ArrowRight, RefreshCw } from "lucide-react";
import { getAdminProfileHistory } from "../../services/adminWorkspaceService";
import { useRemoteData } from "../../hooks/useRemoteData";
import { positivePage } from "../../utils/adminCandidates";
import { formatTimestamp } from "../../utils/dateTime";

export default function AdminProfileHistory({ profileId }: { profileId: number }) {
  const [params, setParams] = useSearchParams();
  const page = positivePage(params.get("history_page")), size = 20;
  const loader = useCallback(() => getAdminProfileHistory(profileId, size, (page - 1) * size), [profileId, page]);
  return <History key={profileId + ":" + page} loader={loader} page={page} onPage={next => { const value = new URLSearchParams(params); if (next === 1) value.delete("history_page"); else value.set("history_page", String(next)); setParams(value); }} />;
}
function History({ loader, page, onPage }: { loader: () => ReturnType<typeof getAdminProfileHistory>; page: number; onPage: (value: number) => void }) {
  const { data, loading, error, retry } = useRemoteData(loader);
  const pages = Math.max(1, Math.ceil((data?.total || 0) / 20));
  const reasons: Record<string, string> = { auto_merge: "Automatic merge", review_decision: "Review decision", manual_edit: "Manual edit" };
  return <section className="ws-panel rq-panel" aria-labelledby="candidate-history-heading"><div className="ws-section-heading"><h2 id="candidate-history-heading">Recorded profile history</h2><button className="ws-button ws-button-quiet" disabled={loading} onClick={retry}><RefreshCw size={14} />Refresh history</button></div><p className="ws-caption">Newest first. This displays the changes recorded by the backend; coverage of every generated profile field is not guaranteed.</p>
    {error && <div className="ws-notice ws-notice-error" role="alert"><span>{error}</span><button className="ws-text-action" onClick={retry}>Try again</button></div>}
    {loading ? <p role="status">Loading profile history…</p> : data && !error && <>
      {data.items.length ? <ol className="rq-list aw-history">{data.items.map(change => <li className="rq-item" key={change.change_id}><h3>{change.field_name}</h3><dl className="rq-context"><div><dt>Before</dt><dd className="aw-preserve-text">{change.old_value ?? "No value"}</dd></div><div><dt>After</dt><dd className="aw-preserve-text">{change.new_value ?? "No value"}</dd></div><div><dt>Changed by</dt><dd>{change.changed_by === "system" ? "System" : change.changed_by}</dd></div><div><dt>Reason</dt><dd>{change.reason ? reasons[change.reason] || "Other recorded change" : "Not recorded"}</dd></div><div><dt>Changed</dt><dd>{formatTimestamp(change.changed_at)}</dd></div><div><dt>Source</dt><dd>{change.file_id ? <Link to={`/admin/documents/${change.file_id}`}>Document #{change.file_id}</Link> : "No source reference returned"}</dd></div></dl></li>)}</ol> : <p className="ws-muted">{page > 1 ? "No recorded changes on this page." : "No profile changes were returned."}</p>}
      {(data.total > 0 || page > 1) && <nav className="rq-pagination" aria-label="Profile history pages"><span className="ws-caption">{data.total} recorded changes</span><div><button className="ws-button ws-button-secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}><ArrowLeft size={15} />Previous</button><span className="ws-caption">Page {page} of {pages}</span><button className="ws-button ws-button-secondary" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next<ArrowRight size={15} /></button></div></nav>}
    </>}
  </section>;
}

