import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowDown, ArrowRight, BriefcaseBusiness, ChartNoAxesColumnIncreasing, Check, FileText, ListChecks, Menu, UploadCloud, UserRound, X } from "lucide-react";
import BrandLogo from "../components/common/BrandLogo";
import { clearSession } from "../services/session";
import { useSessionUser } from "../hooks/useSessionUser";
import "./HomePage.css";

const steps = [
  { icon: UploadCloud, title: "Upload a document", description: "Choose a PDF or DOCX resume, or a LinkedIn Markdown export." },
  { icon: ListChecks, title: "Track processing", description: "Follow your document’s status and see if information needs review." },
  { icon: UserRound, title: "View your profile", description: "Access the professional information added from your processed sources." },
];
const features = [
  { title: "Your documents, organized", description: "Find your uploads, file details and processing statuses in one workspace." },
  { title: "Clear processing status", description: "See what’s waiting, processing, completed, awaiting review or unsuccessful." },
  { title: "A unified professional profile", description: "View available experience, education and skills alongside their connected documents." },
];

export default function HomePage() {
  const { token, user, loading, error, retry } = useSessionUser();
  const candidate = user?.role === "candidate";
  const staff = Boolean(user && !candidate);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const destination = candidate ? "/workspace" : token ? "/login" : "/register";
  const heroActionLabel = candidate ? "Go to Workspace" : token ? "Use a candidate account" : "Get Started";

  return <div className="home-page">
    <a className="home-skip" href="#home-main">Skip to content</a>
    <header className="home-header" onKeyDown={event => {
      if (event.key === "Escape" && menuOpen) { setMenuOpen(false); menuButton.current?.focus(); }
    }}>
      <div className="home-container home-header-inner">
        <BrandLogo />
        <button ref={menuButton} type="button" className="home-menu-button" aria-controls="home-navigation" aria-expanded={menuOpen} aria-label={menuOpen ? "Close navigation" : "Open navigation"} onClick={() => setMenuOpen(open => !open)}>
          {menuOpen ? <X size={22} /> : <Menu size={22} />}
        </button>
        <nav id="home-navigation" className={`home-navigation ${menuOpen ? "is-open" : ""}`} aria-label="Main navigation">
          <div className="home-section-links">
            <a href="#how-it-works" onClick={() => setMenuOpen(false)}>How It Works</a>
            <a href="#features" onClick={() => setMenuOpen(false)}>Features</a>
            <a href="#about" onClick={() => setMenuOpen(false)}>About</a>
          </div>
          <div className="home-nav-actions">
            {candidate ? (
              <Link className="home-button home-button-primary home-nav-cta" to="/workspace" onClick={() => setMenuOpen(false)}>My Workspace<ArrowRight size={15} /></Link>
            ) : staff ? (
              <button type="button" className="home-sign-in home-account-action" onClick={() => clearSession()}>Sign Out</button>
            ) : (
              <Link className="home-sign-in" to="/login" onClick={() => setMenuOpen(false)}>Sign In</Link>
            )}
          </div>
        </nav>
      </div>
    </header>

    <main id="home-main" tabIndex={-1}>
      <section className="home-container home-hero" aria-labelledby="hero-heading">
        <div className="home-hero-copy">
          <h1 id="hero-heading">Your experience.<br /><em>One clear profile.</em></h1>
          <p>Upload professional documents, track their processing, and access a unified profile built from your available sources.</p>
          {staff && <p className="home-account-notice" role="status">You are signed in as {user?.role === "administrator" ? "an administrator" : "a reviewer"}. Staff pages are not available in this frontend.</p>}
          {error && token && <p className="home-account-notice" role="alert">{error} <button type="button" className="home-account-action" onClick={retry}>Try again</button></p>}
          <div className="home-hero-actions">
            {loading ? <button type="button" className="home-button home-button-primary" disabled role="status">Checking your account...</button> : <Link to={destination} className="home-button home-button-primary">{heroActionLabel}<ArrowRight size={17} /></Link>}
            <a href="#how-it-works" className="home-button home-button-secondary">How It Works<ArrowDown size={15} /></a>
          </div>
        </div>

        <figure className="home-original-illustration">
          <div className="cv-flow-scene" role="img" aria-label="Animated diagram showing Resume, LinkedIn and Assessment data flowing into one unified candidate profile">
            <svg className="cv-flow-wires" viewBox="0 0 620 340" preserveAspectRatio="none" aria-hidden="true">
              <path className="cv-flow-wire-base" d="M221 58 C267 58 258 170 322 170" />
              <path className="cv-flow-wire-base" d="M221 170 H322" />
              <path className="cv-flow-wire-base" d="M221 282 C267 282 258 170 322 170" />
              <path className="cv-flow-wire-moving" d="M221 58 C267 58 258 170 322 170" />
              <path className="cv-flow-wire-moving" d="M221 170 H322" />
              <path className="cv-flow-wire-moving" d="M221 282 C267 282 258 170 322 170" />
            </svg>
            <div className="cv-flow-sources">
              <div className="cv-flow-source"><span className="cv-flow-source-icon"><FileText size={20}/></span><span><strong>Resume</strong><small>PDF · DOCX</small></span></div>
              <div className="cv-flow-source"><span className="cv-flow-source-icon"><BriefcaseBusiness size={20}/></span><span><strong>LinkedIn</strong><small>Markdown export</small></span></div>
              <div className="cv-flow-source"><span className="cv-flow-source-icon"><ChartNoAxesColumnIncreasing size={20}/></span><span><strong>Assessment</strong><small>Skill results</small></span></div>
            </div>
            <div className="cv-flow-junction" aria-hidden="true" />
            <div className="cv-flow-profile">
              <div className="cv-flow-approved"><Check size={18} strokeWidth={2.5}/></div>
              <div className="cv-flow-profile-top"><span className="cv-flow-person"><UserRound size={23}/></span><span className="cv-flow-header-bars"><i/><i/></span></div>
              <h3>Unified candidate profile</h3>
              <div className="cv-flow-field"><i/><i/><b/><b/><b/></div>
              <div className="cv-flow-field cv-flow-field-review"><i/><i/><b/><b/><b/></div>
              <div className="cv-flow-field"><i/><i/><b/><b/><b/></div>
              <div className="cv-flow-tags"><span><Check size={13}/> 3 sources</span><span><em/> 1 to review</span></div>
            </div>
          </div>
          <figcaption>Conceptual illustration. Assessment inputs are not currently available in the candidate workspace.</figcaption>
        </figure>
      </section>

      <section id="how-it-works" className="home-container home-how" aria-labelledby="how-heading">
        <h2 id="how-heading">How It Works</h2>
        <ol className="home-steps">{steps.map(({icon: Icon,title,description},index) => <li key={title}>
          <div className="home-step-heading"><span className="home-step-number">0{index+1}</span><Icon size={21} strokeWidth={1.5} aria-hidden="true" /></div>
          <h3>{title}</h3><p>{description}</p>
        </li>)}</ol>
      </section>

      <section id="features" className="home-container home-features" aria-labelledby="features-heading">
        <h2 id="features-heading">Built around your professional information</h2>
        <div className="home-features-grid">{features.map(({title,description}) => <article key={title}><h3>{title}</h3><p>{description}</p></article>)}</div>
      </section>

      <section id="about" className="home-container home-about" aria-labelledby="about-heading">
        <h2 id="about-heading">About CVerge</h2>
        <p>CVerge gives candidates a clearer view of professional information spread across different documents. Its purpose is to keep that information organized and connected to the sources behind it.</p>
      </section>
    </main>

    <footer className="home-container home-footer">
      <BrandLogo />
      <nav aria-label="Footer navigation"><a href="#how-it-works">How It Works</a><a href="#features">Features</a><a href="#about">About</a><Link to={destination}>{candidate ? "My Workspace" : token ? "Use a candidate account" : "Get Started"}</Link>{!token && <Link to="/login">Sign In</Link>}</nav>
      <span className="home-copyright">© {new Date().getFullYear()} CVerge</span>
    </footer>
  </div>;
}