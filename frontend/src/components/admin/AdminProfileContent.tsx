import { useCallback, useId, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import type { CandidateProfileResponse, ProfileDate } from "../../services/profileService";
import type { CandidateFile } from "../../services/fileService";
import { getAdminSkillDocuments } from "../../services/adminWorkspaceService";
import { useRemoteData } from "../../hooks/useRemoteData";
import { safeWebUrl } from "../../utils/documents";
import DocumentStatus from "../common/DocumentStatus";

function Section({ title, children }: { title: string; children: ReactNode }) {
  const id = useId();
  return <section className="ws-panel rq-panel" aria-labelledby={id}><h2 id={id}>{title}</h2>{children}</section>;
}
function Empty() { return <p className="ws-muted">No information returned for this section.</p>; }
function Dates({ start, end, current }: { start?: ProfileDate | null; end?: ProfileDate | null; current?: boolean }) {
  return <span className="ws-caption">{[start?.value, current ? "Present" : end?.value].filter(Boolean).join(" – ")}</span>;
}
function WebLink({ url, label }: { url?: string | null; label: string }) {
  const safe = safeWebUrl(url);
  return safe ? <a className="ws-text-action" href={safe} target="_blank" rel="noopener noreferrer">{label}</a> : url ? <p className="ws-caption">{label}: link unavailable</p> : null;
}
function References({ ids }: { ids?: number[] }) {
  return ids?.length ? <details className="aw-references"><summary>Field-record references</summary><p className="ws-caption">{ids.join(", ")}. These identify stored fields, not source documents.</p></details> : null;
}
function SkillDocuments({ profileId, sources, files }: { profileId: number; sources: readonly string[]; files: readonly CandidateFile[] }) {
  const loader = useCallback(() => getAdminSkillDocuments(profileId, sources, files), [profileId, sources, files]);
  const { data, loading, error, retry } = useRemoteData(loader);
  if (loading) return <p role="status" className="ws-caption">Loading supporting documents…</p>;
  if (error) return <p role="alert">{error} <button className="ws-text-action" onClick={retry}>Try again</button></p>;
  return <div className="aw-skill-documents">{data?.documents.map(file => <Link key={file.file_id} to={`/admin/documents/${file.file_id}`}>{file.original_name}</Link>)}{!data?.documents.length && <p className="ws-caption">No supporting documents could be resolved.</p>}{!!data?.unavailableCount && <p className="ws-caption">Some source references are unavailable. No document match has been guessed.</p>}</div>;
}
function SkillSources({ name, profileId, sources, files }: { name: string; profileId: number; sources: readonly string[]; files: readonly CandidateFile[] }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return sources.length ? <><button className="ws-text-action" aria-expanded={open} aria-controls={id} onClick={() => setOpen(value => !value)}>Sources for {name}</button><div id={id}>{open && <SkillDocuments profileId={profileId} sources={sources} files={files} />}</div></> : null;
}
export default function AdminProfileContent({ data }: { data: CandidateProfileResponse }) {
  const profile = data.profile, personal = profile?.personal_info;
  return <>
    {!profile && <p className="ws-notice" role="status">No extracted profile is available yet. Account details and source documents remain available.</p>}
    <div className="aw-profile-grid">
      <div>
        <Section title="Personal information">{personal ? <><dl className="rq-context"><div><dt>Extracted name</dt><dd>{[personal.first_name, personal.last_name].filter(Boolean).join(" ") || "Not provided"}</dd></div><div><dt>Email</dt><dd>{personal.email || "Not provided"}</dd></div><div><dt>Phone</dt><dd>{personal.phone || "Not provided"}</dd></div><div><dt>Location</dt><dd>{[personal.city, personal.country?.name].filter(Boolean).join(", ") || "Not provided"}</dd></div><div><dt>Professional title</dt><dd>{personal.title || "Not provided"}</dd></div></dl>{personal.field_ids && Object.keys(personal.field_ids).length > 0 && <details className="aw-references"><summary>Personal field-record references</summary><dl>{Object.entries(personal.field_ids).map(([name, id]) => <div key={name}><dt>{name}</dt><dd>{id}</dd></div>)}</dl></details>}</> : <Empty />}</Section>
        <Section title="Professional summary">{personal?.summary ? <p className="aw-preserve-text">{personal.summary}</p> : <Empty />}</Section>
        <Section title="Work experience">{profile?.experience?.length ? profile.experience.map((item, index) => <article className="aw-record" key={index}><h3>{item.title || "Title not provided"}</h3>{item.company && <strong>{item.company}</strong>}<p><Dates start={item.start_date} end={item.end_date} current={item.employment_status === "current"} /></p>{item.location && <p>{item.location}</p>}{item.description && <p className="aw-preserve-text">{item.description}</p>}<References ids={item.field_ids} /></article>) : <Empty />}</Section>
        <Section title="Education">{profile?.education?.length ? profile.education.map((item, index) => <article className="aw-record" key={index}><h3>{item.institution || "Institution not provided"}</h3><p>{[item.degree, item.field].filter(Boolean).join(" · ")}</p><Dates start={item.start_date} end={item.end_date} /><References ids={item.field_ids} /></article>) : <Empty />}</Section>
        <Section title="Projects">{profile?.projects?.length ? profile.projects.map((item, index) => <article className="aw-record" key={index}><h3>{item.name || "Name not provided"}</h3>{item.description && <p className="aw-preserve-text">{item.description}</p>}{!!item.tech_stack?.length && <p>{item.tech_stack.join(", ")}</p>}<WebLink url={item.url} label="View project" /><References ids={item.field_ids} /></article>) : <Empty />}</Section>
        <Section title="Certifications">{profile?.certifications?.length ? profile.certifications.map((item, index) => <article className="aw-record" key={index}><h3>{item.name || "Name not provided"}</h3>{item.issuer && <p>{item.issuer}</p>}{item.issue_date && <p className="ws-caption">{item.issue_date.value}</p>}<WebLink url={item.url} label="View credential" /><References ids={item.field_ids} /></article>) : <Empty />}</Section>
      </div>
      <div>
        <Section title="Skills">{profile?.skills?.length ? profile.skills.map((skill, index) => <article className="aw-record" key={index}><h3>{skill.name}</h3>{skill.level != null && <p>Level: {skill.level}/5</p>}{skill.verified && <p className="ws-caption">Verified skill</p>}<SkillSources name={skill.name} profileId={data.profile_id} sources={skill.sources || []} files={data.files} /><References ids={skill.field_ids} /></article>) : <Empty />}</Section>
        <Section title="Languages">{profile?.languages?.length ? profile.languages.map((item, index) => <article className="aw-record" key={index}><h3>{item.name}</h3>{item.proficiency && <p>{item.proficiency}</p>}<References ids={item.field_ids} /></article>) : <Empty />}</Section>
        <Section title="Professional links">{profile?.links?.length ? profile.links.map((item, index) => <article className="aw-record" key={index}><WebLink url={item.url} label={item.type || "Website"} /><References ids={item.field_ids} /></article>) : <Empty />}</Section>
        <Section title="Connected documents"><p className="ws-caption">Showing {data.files.length} sources returned with this profile, up to the backend limit of 100. Open the document list for complete pagination.</p><div className="aw-source-list">{data.files.map(file => <article key={file.file_id}><Link to={`/admin/documents/${file.file_id}`}>{file.original_name}</Link><DocumentStatus status={file.status} /></article>)}</div>{data.files.length === 0 && <Empty />}<Link className="ws-text-action" to={`/admin/documents?profile_id=${data.profile_id}`}>All candidate documents</Link></Section>
        <p className="ws-caption">Field-record IDs do not resolve to evidence through the current API. Skill document links use explicit source references; full field-level confidence, rules and evidence are unavailable here.{profile?.rule_version && ` Merge rule version: ${profile.rule_version}.`}</p>
      </div>
    </div>
  </>;
}

