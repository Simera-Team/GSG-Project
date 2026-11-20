import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { ArrowRight, Award, BriefcaseBusiness, CheckCircle2, ExternalLink, FileText, FolderGit2, GraduationCap, Languages, Link2, Mail, MapPin, Phone, Plus, RefreshCw, ShieldCheck, Sparkles, UserRound } from "lucide-react";
import { type ProfileDate } from "../../services/profileService";
import { getVerifiedSessionUser } from "../../services/authService";
import { getAccessToken } from "../../services/session";
import { getCandidateOverview, overviewNeedsRefresh } from "../../services/workspaceService";
import { friendlyError } from "../../services/apiClient";
import { useRemoteData } from "../../hooks/useRemoteData";
import { formatTimestamp } from "../../utils/dateTime";
import { fileType, safeWebUrl } from "../../utils/documents";
import DocumentStatus from "../../components/common/DocumentStatus";
import SkillSources from "../../components/profile/SkillSources";
import "./ProfilePage.css";

function dateRange(start?: ProfileDate | null, end?: ProfileDate | null, current = false) {
  // Partial career dates are calendar values, not timestamps; preserve API precision.
  return [start?.value, current ? "Present" : end?.value].filter(Boolean).join(" – ");
}
function Section({ id, title, icon, count, children }: { id: string; title: string; icon: ReactNode; count?: number; children: ReactNode }) {
  return <section className="ws-panel pr-section" id={id} aria-labelledby={`${id}-heading`}><div className="pr-section-title"><span className="ws-icon-tile">{icon}</span><h2 id={`${id}-heading`}>{title}</h2>{count !== undefined && <span className="ws-count">{count}</span>}</div>{children}</section>;
}
function Empty({ children }: { children: ReactNode }) { return <p className="pr-empty-note">{children}</p>; }
function WebLink({ url, children }: { url?: string | null; children: ReactNode }) {
  const safe = safeWebUrl(url);
  return safe ? <a className="ws-text-action" href={safe} target="_blank" rel="noopener noreferrer">{children}<ExternalLink size={13} /></a> : null;
}
async function loadProfile() {
  const [account, overview] = await Promise.all([getVerifiedSessionUser(getAccessToken() || "").then(user => ({ user, error: "" }), cause => ({ user: null, error: friendlyError(cause) })), getCandidateOverview()]);
  return {
    ...overview, user: account.user, data: overview.profile, files: overview.documents,
    accountError: account.error, profileError: overview.profileError, filesError: overview.documentsError,
  };
}
function profileNeedsRefresh(result: Awaited<ReturnType<typeof loadProfile>>) { return !result.accountError && overviewNeedsRefresh(result); }
export default function ProfilePage() {
  const { data: result, loading, error, retry } = useRemoteData(loadProfile, 5000, profileNeedsRefresh);
  const data = result?.data;
  const profile = data?.profile;
  const personal = profile?.personal_info;
  const name = [personal?.first_name, personal?.last_name].filter(Boolean).join(" ") || data?.candidate_name || result?.user?.name || "My Profile";
  const email = personal?.email || data?.candidate_email || result?.user?.email;
  const location = [personal?.city, personal?.country?.name].filter(Boolean).join(", ");
  const initials = name.split(/\s+/).slice(0,2).map(part => part[0]).join("").toUpperCase();
  const experience = profile?.experience || [];
  const education = profile?.education || [];
  const skills = profile?.skills || [];
  const certifications = profile?.certifications || [];
  const projects = profile?.projects || [];
  const languages = profile?.languages || [];
  const links = profile?.links || [];
  const files = result?.files?.items || data?.files || [];
  const sourceCount = result?.files?.total;
  const hasDetails = Boolean(profile && (personal?.summary || personal?.title || location || experience.length || education.length || skills.length || certifications.length || projects.length || languages.length || links.length));
  return <>
    <div className="ws-page-heading"><div><span className="ws-eyebrow">YOUR PROFESSIONAL STORY</span><h1>My Profile</h1><p>Your experience and skills, brought together from your documents.</p></div><Link to="/upload" className="ws-button ws-button-primary"><Plus size={17} />Add a document</Link></div>
    <div className="ws-section-heading pr-refresh"><p className="ws-caption">Active processing refreshes every 5 seconds while visible, for up to 5 minutes. Return to this tab or refresh to check for later changes.</p><button className="ws-button ws-button-secondary" disabled={loading} onClick={retry}><RefreshCw size={15} />Refresh profile</button></div>
    {loading ? <div className="pr-loading" role="status"><div className="ws-panel"><div className="ws-skeleton pr-skeleton-hero" /><div className="ws-skeleton" /></div><div className="pr-loading-grid">{[1,2,3,4].map(i => <div className="ws-panel" key={i}><div className="ws-skeleton" /><div className="ws-skeleton" /></div>)}</div><span className="ws-sr-only">Loading your profile…</span></div> : <>
      {(error || result?.profileError || result?.accountError) && <div className="ws-notice ws-notice-error" role="alert"><span>{error || result?.profileError || result?.accountError} Your available information is shown below.</span><button className="ws-text-action" onClick={retry}><RefreshCw size={15} />Try again</button></div>}
      {result?.filesError && <div className="ws-notice ws-notice-error" role="alert"><span>{result.filesError} The full document count is unavailable. {files.length > 0 && "Only profile-linked documents are shown below."}</span><button className="ws-text-action" onClick={retry}>Try again</button></div>}
      <section className="ws-panel pr-overview" aria-label="Profile overview"><div className="pr-overview-main"><div className="pr-avatar" aria-hidden="true">{initials}</div><div className="pr-identity"><span className="ws-eyebrow">PROFILE OVERVIEW</span><h2>{name}</h2>{personal?.title ? <p className="pr-title">{personal.title}</p> : <p className="ws-muted">Your professional title will appear as your documents are processed.</p>}<div className="pr-contact">{email && <span><Mail size={14} />{email}</span>}{location && <span><MapPin size={14} />{location}</span>}</div></div>{profile && <span className="pr-source-badge"><ShieldCheck size={15} />Built from your sources</span>}</div><div className="pr-overview-footer"><div className="pr-metrics"><span><strong>{sourceCount ?? "—"}</strong> {sourceCount === 1 ? "document" : "documents"}</span><span><strong>{experience.length}</strong> {experience.length === 1 ? "experience" : "experiences"}</span><span><strong>{skills.length}</strong> {skills.length === 1 ? "skill" : "skills"}</span></div><span className="ws-caption">{data?.updated_at ? `Updated ${formatTimestamp(data.updated_at)}` : "Your profile grows as documents are processed."}</span></div></section>
      {!hasDetails && !result?.profileError && !result?.filesError && <div className="pr-welcome"><span className="ws-icon-tile"><Sparkles size={22} /></span><div><h3>Your profile is ready to grow</h3><p>{files.length ? "Your documents are connected. Profile information will appear once processing and any required review are complete." : "Start with a resume or LinkedIn export. Your account is ready, even before your first upload."}</p></div><Link to="/upload" className="ws-text-action">Upload Documents <ArrowRight size={16} /></Link></div>}
      <nav className="pr-section-nav" aria-label="Profile sections"><a href="#summary">Overview</a><a href="#experience">Experience</a><a href="#education">Education</a><a href="#skills">Skills</a><a href="#sources">Documents</a></nav>
      <div className="pr-grid"><div className="pr-main-column">
        <Section id="summary" title="Professional summary" icon={<UserRound size={19} />}>{personal?.summary ? <p className="pr-summary">{personal.summary}</p> : <Empty>Your professional summary will appear here after it’s extracted from your documents.</Empty>}</Section>
        <Section id="experience" title="Work experience" count={experience.length} icon={<BriefcaseBusiness size={19} />}>{experience.length ? <div className="pr-timeline">{experience.map((item,index) => <article className="pr-record" key={index}><span className="pr-timeline-dot" /><div className="pr-record-heading"><h3>{item.title || "Position not provided"}</h3><span>{dateRange(item.start_date, item.end_date, item.employment_status === "current")}</span></div>{item.company && <strong className="pr-company">{item.company}</strong>}{item.location && <p className="pr-record-meta"><MapPin size={13} />{item.location}</p>}{item.description && <p>{item.description}</p>}</article>)}</div> : <Empty>Your roles, companies and career milestones will appear here.</Empty>}</Section>
        <Section id="education" title="Education" count={education.length} icon={<GraduationCap size={20} />}>{education.length ? education.map((item,index) => <article className="pr-record" key={index}><div className="pr-record-heading"><h3>{item.degree || "Qualification not provided"}</h3><span>{dateRange(item.start_date,item.end_date)}</span></div>{item.institution && <strong className="pr-company">{item.institution}</strong>}{item.field && <p>{item.field}</p>}</article>) : <Empty>Your academic background and qualifications will appear here.</Empty>}</Section>
        <Section id="skills" title="Skills" count={skills.length} icon={<Sparkles size={19} />}>{skills.length ? <ul className="pr-tags">{skills.map((skill,index) => <li key={index}>{skill.name}{skill.verified && <CheckCircle2 size={13} aria-label="Verified skill" />}<SkillSources name={skill.name} sources={skill.sources} files={files} /></li>)}</ul> : <Empty>Skills from your documents will be collected here.</Empty>}</Section>
        <Section id="projects" title="Projects" count={projects.length} icon={<FolderGit2 size={19} />}>{projects.length ? projects.map((item,index) => <article className="pr-record" key={index}><h3>{item.name || "Project name not provided"}</h3>{item.description && <p>{item.description}</p>}{!!item.tech_stack?.length && <ul className="pr-tags pr-tags-small">{item.tech_stack.map((tech,i) => <li key={i}>{tech}</li>)}</ul>}<WebLink url={item.url}>View project</WebLink></article>) : <Empty>Projects and the technologies you’ve worked with will appear here.</Empty>}</Section>
        <Section id="certifications" title="Certifications" count={certifications.length} icon={<Award size={19} />}>{certifications.length ? certifications.map((item,index) => <article className="pr-record" key={index}><div className="pr-record-heading"><h3>{item.name || "Certification name not provided"}</h3><span>{item.issue_date?.value}</span></div>{item.issuer && <p>{item.issuer}</p>}<WebLink url={item.url}>View credential</WebLink></article>) : <Empty>Your certifications and professional achievements will appear here.</Empty>}</Section>
      </div><aside className="pr-side-column" aria-label="Profile information and sources">
        <Section id="personal" title="Personal information" icon={<UserRound size={18} />}><dl className="pr-personal"><div><dt><Mail size={14} />Email</dt><dd>{email || "Not provided yet"}</dd></div><div><dt><Phone size={14} />Phone</dt><dd>{personal?.phone || "Not provided yet"}</dd></div><div><dt><MapPin size={14} />Location</dt><dd>{location || "Not provided yet"}</dd></div></dl></Section>
        <Section id="languages" title="Languages" icon={<Languages size={19} />}>{languages.length ? <ul className="pr-language-list">{languages.map((item,index) => <li key={index}><strong>{item.name}</strong>{item.proficiency && <span>{item.proficiency}</span>}</li>)}</ul> : <Empty>Your languages and proficiency levels will appear here.</Empty>}</Section>
        <Section id="links" title="Professional links" icon={<Link2 size={18} />}>{links.length ? <ul className="pr-link-list">{links.map((link,index) => <li key={index}>{safeWebUrl(link.url) ? <WebLink url={link.url}>{link.type || "Website"}</WebLink> : <span>{link.type || "Link"} — link unavailable</span>}</li>)}</ul> : <Empty>Your portfolio and professional links will appear here.</Empty>}</Section>
        <p className="pr-provenance-note">Source details are available for skills with linked documents. Sources for other individual profile details are currently unavailable.</p>
        <Section id="sources" title="Connected documents" count={files.length} icon={<FileText size={18} />}>{files.length ? <div className="pr-source-list">{files.map(file => <Link to={`/files/${file.file_id}`} key={file.file_id} className="pr-source"><div><FileText size={17} /><strong>{file.original_name}</strong><ArrowRight size={14} /></div><span className="ws-caption">{fileType(file.file_type,file.original_name)} · {formatTimestamp(file.uploaded_at)}</span><DocumentStatus status={file.status} /></Link>)}</div> : <Empty>{result?.filesError || "Your uploaded documents will be connected here. Add a source to get started."}</Empty>}<Link to="/documents" className="ws-text-action pr-all-documents">My Documents <ArrowRight size={15} /></Link></Section>
        <section className="pr-review" aria-labelledby="review-heading"><ShieldCheck size={23} /><h2 id="review-heading">Review status</h2>{data ? <><strong>{data.open_reviews > 0 ? `${data.open_reviews} ${data.open_reviews === 1 ? "item needs" : "items need"} review` : "No open reviews"}</strong><p>{data.open_reviews > 0 ? "Uncertain or conflicting details are held for review before they’re added to your profile." : "Any information that needs review will be flagged here."}</p></> : <p>Review status will be available once your profile has been created.</p>}</section>
      </aside></div>
    </>}
  </>;
}
