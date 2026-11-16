import { type FormEvent } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { ArrowLeft, ArrowRight, RefreshCw, UsersRound } from "lucide-react";
import { getCandidateDirectory, type CandidateDirectory } from "../../services/adminWorkspaceService";
import { processingStatuses } from "../../services/adminFileService";
import { useRemoteData } from "../../hooks/useRemoteData";
import { CANDIDATE_PAGE_SIZE, filterCandidateDirectory, parseCandidateQuery } from "../../utils/adminCandidates";
import { statusLabels } from "../../utils/documents";
import "./ReviewPages.css";
import "./AdminWorkspace.css";

export default function AdminCandidatesPage() {
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const request = useRemoteData(getCandidateDirectory);
  return <Directory key={location.key + params.toString()} request={request} params={params} setParams={setParams} />;
}
function Directory({ request, params, setParams }: { request: { data: CandidateDirectory | null; loading: boolean; error: string; retry: () => void }; params: URLSearchParams; setParams: (params: URLSearchParams) => void }) {
  const { data, loading, error, retry } = request;
  const navigate = useNavigate();
  const { query, status, page } = parseCandidateQuery(params);
  const filtered = data ? filterCandidateDirectory(data.entries, query, status) : [];
  const items = filtered.slice((page - 1) * CANDIDATE_PAGE_SIZE, page * CANDIDATE_PAGE_SIZE);
  const pages = Math.max(1, Math.ceil(filtered.length / CANDIDATE_PAGE_SIZE));
  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget), next = new URLSearchParams();
    for (const key of ["q", "status"]) { const value = String(form.get(key) || "").trim(); if (value) next.set(key, value); }
    setParams(next);
  }
  function changePage(value: number) { const next = new URLSearchParams(params); if (value === 1) next.delete("page"); else next.set("page", String(value)); setParams(next); }
  function openProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = String(new FormData(event.currentTarget).get("profile_id") || "");
    if (/^[1-9]\d*$/.test(value) && Number.isSafeInteger(Number(value))) navigate("/admin/candidates/" + value);
  }
  return <>
    <div className="ws-page-heading"><div><span className="ws-eyebrow">READ-ONLY ADMIN DIRECTORY</span><h1>Candidate Management</h1><p>Inspect candidate profiles, sources, documents and recorded changes.</p></div><button className="ws-button ws-button-secondary" disabled={loading} onClick={retry}><RefreshCw size={16} />Refresh directory</button></div>
    <p className="ws-notice aw-coverage">This directory includes candidates with uploaded documents. It is built from all document metadata pages; accounts without uploads cannot be listed by the available API. Search, status filtering and paging below apply locally to this directory.</p>
    <form className="aw-profile-lookup" onSubmit={openProfile}><label htmlFor="known-profile-id">Open a known profile ID<input id="known-profile-id" name="profile_id" type="number" min="1" max={Number.MAX_SAFE_INTEGER} step="1" required /></label><button className="ws-button ws-button-secondary" type="submit">Open profile</button></form>
    <section className="ws-panel rq-panel" aria-labelledby="candidate-directory-heading"><div className="ws-section-heading"><div><h2 id="candidate-directory-heading">Candidates with uploaded documents <span className="ws-count">{data && !error ? data.entries.length : "—"}</span></h2>{data && !error && <p>Derived from {data.documentTotal} uploaded documents. This is not the registered-account total.</p>}</div><UsersRound size={23} aria-hidden="true" /></div>
      <form className="rq-filters" onSubmit={search}><label>Search this directory<input name="q" defaultValue={query} placeholder="Name, profile ID or user ID" /></label><label>Has document status<select name="status" defaultValue={status || ""}><option value="">Any status</option>{processingStatuses.map(value => <option key={value} value={value}>{statusLabels[value]}</option>)}</select></label><button className="ws-button ws-button-primary" type="submit">Apply filters</button><Link className="ws-text-action" to="/admin/candidates">Clear filters</Link></form>
      {error && <div className="ws-notice ws-notice-error" role="alert"><span>{error}</span><button className="ws-text-action" onClick={retry}>Try again</button></div>}
      {loading ? <div className="ws-skeleton-list" role="status"><span className="ws-sr-only">Loading the candidate directory…</span>{[1, 2, 3].map(value => <div className="ws-skeleton" key={value} />)}</div> : data && !error && <>
        {items.length ? <ol className="rq-list aw-candidate-list">{items.map(candidate => <li className="rq-item" key={candidate.profileId}><div className="rq-item-title"><Link to={`/admin/candidates/${candidate.profileId}?${params}`}>{candidate.name}<ArrowRight size={16} /></Link><span className="ws-caption">Profile #{candidate.profileId} · User #{candidate.userId}</span></div><dl className="rq-context"><div><dt>Uploaded documents</dt><dd>{candidate.documents}</dd></div><div><dt>Open reviews on these documents</dt><dd>{candidate.openDocumentReviews}</dd></div></dl><div className="aw-row-links"><Link to={`/admin/documents?profile_id=${candidate.profileId}`}>Documents</Link><Link to={`/admin/reviews?profile_id=${candidate.profileId}`}>Review items</Link></div></li>)}</ol> : <div className="ws-empty"><UsersRound size={28} /><h3>{page > 1 ? "No candidates on this page" : "No candidates found in this directory"}</h3><p>{data.entries.length ? "Try another search or status filter." : "No uploaded documents were returned. Accounts without uploads are not included."}</p>{page > 1 && <button className="ws-button ws-button-secondary" onClick={() => changePage(1)}>Go to first page</button>}</div>}
        {(filtered.length > 0 || page > 1) && <nav className="rq-pagination" aria-label="Candidate directory pages"><span className="ws-caption" role="status">{filtered.length} matching candidates in this directory</span><div><button className="ws-button ws-button-secondary" disabled={page <= 1} onClick={() => changePage(page - 1)}><ArrowLeft size={15} />Previous</button><span className="ws-caption">Page {page} of {pages}</span><button className="ws-button ws-button-secondary" disabled={page >= pages} onClick={() => changePage(page + 1)}>Next<ArrowRight size={15} /></button></div></nav>}
      </>}
    </section>
  </>;
}

