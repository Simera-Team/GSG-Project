import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { Eye, EyeOff, UserPlus } from "lucide-react";
import { createStaffAccount, type StaffAccount, type StaffRole } from "../../services/staffService";
import { ApiError, friendlyError } from "../../services/apiClient";
import { prepareStaffRequest, staffErrorsAfterEdit, staffRoleLabels, validateStaffForm, type StaffFormErrors, type StaffFormValues } from "../../utils/staffAccounts";
import "./ReviewPages.css";
import "./StaffManagement.css";

export default function StaffManagementPage() {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<StaffRole>("reviewer");
  const [showPassword, setShowPassword] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<StaffFormErrors>({});
  const [error, setError] = useState("");
  const [pending, setPending] = useState<{ name: string; email: string; role: StaffRole } | null>(null);
  const [busy, setBusy] = useState(false);
  const [outcome, setOutcome] = useState<"ready" | "uncertain" | "forbidden">("ready");
  const [created, setCreated] = useState<StaffAccount | null>(null);
  const form = useRef<HTMLFormElement>(null);
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const success = useRef<HTMLElement>(null);
  const submitting = useRef(false), mounted = useRef(true);
  const id = useId(), locked = busy || outcome !== "ready";
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    if (pending && !dialog.current?.open) dialog.current?.showModal();
    if (!pending && dialog.current?.open) dialog.current.close();
  }, [pending]);
  useEffect(() => { if (created) success.current?.focus(); }, [created]);
  function edit(field: keyof StaffFormValues, value: string) {
    const values = { name, email, password, role, [field]: value };
    setFieldErrors(previous => staffErrorsAfterEdit(previous, values, field));
    if (outcome === "ready") setError("");
    if (field === "name") setName(value);
    if (field === "email") setEmail(value);
    if (field === "password") setPassword(value);
    if (field === "role") setRole(value as StaffRole);
  }
  function review(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (locked || submitting.current) return;
    setCreated(null); setError("");
    const errors = validateStaffForm({ name, email, password, role });
    setFieldErrors(errors);
    const first = Object.keys(errors)[0];
    if (first) {
      setError("Correct the highlighted account details before continuing.");
      (form.current?.elements.namedItem(first) as HTMLElement | null)?.focus();
      return;
    }
    const payload = prepareStaffRequest({ name, email, password, role });
    setShowPassword(false);
    setPending({ name: payload.name, email: payload.email, role: payload.role });
  }
  async function confirm() {
    if (!pending || locked || submitting.current) return;
    submitting.current = true; setBusy(true); setError("");
    try {
      const response = await createStaffAccount({ ...pending, password });
      if (!mounted.current) return;
      setCreated(response); setName(""); setEmail(""); setRole("reviewer"); setFieldErrors({});
    } catch (cause) {
      if (!mounted.current) return;
      setError(friendlyError(cause, "The account-creation outcome could not be confirmed. Verify before retrying."));
      if (cause instanceof ApiError && cause.status === 409) setFieldErrors({ email: "This email is already registered. Choose a different email." });
      if (cause instanceof ApiError && cause.status === 422) setError("The server rejected the account details. Check the name, email, password length and role. Re-enter the password before trying again.");
      if (cause instanceof ApiError && cause.status === 403) setOutcome("forbidden");
      else if (!(cause instanceof ApiError) || cause.status === 0 || cause.status >= 500) setOutcome("uncertain");
    } finally {
      submitting.current = false;
      if (mounted.current) { setPending(null); setPassword(""); setShowPassword(false); setBusy(false); }
    }
  }
  return <>
    <div className="ws-page-heading"><div><span className="ws-eyebrow">ADMIN WORKSPACE</span><h1>Staff Management</h1><p>Create Reviewer and Administrator accounts with email and password.</p></div><span className="ws-icon-tile"><UserPlus size={24} aria-hidden="true" /></span></div>
    <p className="ws-notice sm-scope">The backend supports account creation only. Existing staff accounts cannot be listed here. This page is not a staff directory.</p>
    {created && <section ref={success} tabIndex={-1} className="ws-panel rq-panel sm-success" aria-labelledby={id + "-success"}><h2 id={id + "-success"}>Account created</h2><p role="status">The backend confirmed the account below. No invitation email was sent.</p><dl className="rq-context"><div><dt>Name</dt><dd>{created.name}</dd></div><div><dt>Email</dt><dd>{created.email}</dd></div><div><dt>Role</dt><dd>{staffRoleLabels[created.role]}</dd></div><div><dt>User ID</dt><dd>{created.user_id}</dd></div></dl><p className="ws-caption">This is the latest account created here, not a list of all staff. The account signs in with its email and the password you supplied.</p></section>}
    <section className="ws-panel rq-panel sm-panel" aria-labelledby={id + "-heading"}><h2 id={id + "-heading"}>Create a staff account</h2>
      {error && <p className="ws-notice ws-notice-error" role="alert">{error}</p>}
      {outcome === "uncertain" && <div className="sm-retry"><p className="ws-caption">This page cannot list accounts to verify the result. Retrying the same email may report it is already registered. No retry happens automatically.</p><button className="ws-button ws-button-secondary" onClick={() => { setOutcome("ready"); setError(""); }}>Prepare another attempt</button></div>}
      <form ref={form} className="sm-form" noValidate onSubmit={review}>
        <fieldset disabled={locked}><legend className="ws-sr-only">Staff account details</legend>
          <div className="sm-fields">
            <div><label htmlFor={id + "-name"}>Full name</label><input id={id + "-name"} name="name" value={name} onChange={event => edit("name", event.target.value)} autoComplete="off" required aria-invalid={!!fieldErrors.name} aria-describedby={fieldErrors.name ? id + "-name-error" : undefined} />{fieldErrors.name && <p id={id + "-name-error"} className="sm-field-error">{fieldErrors.name}</p>}</div>
            <div><label htmlFor={id + "-email"}>Email address</label><input id={id + "-email"} name="email" type="email" value={email} onChange={event => edit("email", event.target.value)} autoComplete="off" required aria-invalid={!!fieldErrors.email} aria-describedby={fieldErrors.email ? id + "-email-error" : undefined} />{fieldErrors.email && <p id={id + "-email-error"} className="sm-field-error">{fieldErrors.email}</p>}</div>
            <div><label htmlFor={id + "-password"}>Initial password</label><div className="sm-password"><input id={id + "-password"} name="password" type={showPassword ? "text" : "password"} value={password} onChange={event => edit("password", event.target.value)} autoComplete="new-password" required aria-invalid={!!fieldErrors.password} aria-describedby={id + "-password-hint" + (fieldErrors.password ? " " + id + "-password-error" : "")} /><button type="button" aria-label={showPassword ? "Hide password" : "Show password"} aria-pressed={showPassword} onClick={() => setShowPassword(value => !value)}>{showPassword ? <EyeOff size={18} /> : <Eye size={18} />}</button></div><p id={id + "-password-hint"} className="ws-caption">8–128 characters. The password is never included in the confirmation or success message.</p>{fieldErrors.password && <p id={id + "-password-error"} className="sm-field-error">{fieldErrors.password}</p>}</div>
            <div><label htmlFor={id + "-role"}>Staff role</label><select id={id + "-role"} name="role" value={role} onChange={event => edit("role", event.target.value)} required aria-invalid={!!fieldErrors.role} aria-describedby={id + "-role-hint" + (fieldErrors.role ? " " + id + "-role-error" : "")}><option value="reviewer">Reviewer</option><option value="administrator">Administrator</option></select><p id={id + "-role-hint"} className="ws-caption">{role === "administrator" ? "Administrators can access candidate data, processing controls, and create other staff accounts." : "Reviewers can inspect and decide review items. Admin management pages remain restricted."}</p>{fieldErrors.role && <p id={id + "-role-error"} className="sm-field-error">{fieldErrors.role}</p>}</div>
          </div>
          <p className="ws-caption">No invitation email is sent. This creates an account that signs in using the email and password you set.</p>
          <button ref={trigger} type="submit" className="ws-button ws-button-primary">{busy ? "Creating account…" : "Review account creation"}</button>
        </fieldset>
      </form>
    </section>
    <dialog ref={dialog} className="rq-confirm-dialog" aria-labelledby={id + "-confirm"} aria-describedby={id + "-confirm-description"} onCancel={event => { if (busy) event.preventDefault(); else setPending(null); }} onClose={() => { if (!dialog.current?.open && !created) trigger.current?.focus(); }}>
      <h2 id={id + "-confirm"}>Create {pending?.role === "administrator" ? "an Administrator" : "a Reviewer"} account?</h2>
      <p id={id + "-confirm-description"}>This creates a real staff account with the selected access. No invitation email will be sent.</p>
      {pending && <dl className="rq-context"><div><dt>Name</dt><dd>{pending.name}</dd></div><div><dt>Email</dt><dd>{pending.email}</dd></div><div><dt>Role</dt><dd>{staffRoleLabels[pending.role]}</dd></div></dl>}
      <p className="ws-caption">{pending?.role === "administrator" ? "Administrator access includes candidate data, processing controls and staff account creation." : "Reviewer access includes the review queue and review decisions."}</p>
      <div className="rq-confirm-buttons"><button className="ws-button ws-button-secondary" type="button" autoFocus disabled={busy} onClick={() => setPending(null)}>Cancel</button><button className="ws-button ws-button-primary" type="button" disabled={busy} onClick={() => void confirm()}>{busy ? "Creating…" : "Confirm creation"}</button></div>
    </dialog>
  </>;
}

