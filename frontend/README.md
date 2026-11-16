# CVerge frontend

React, TypeScript and Vite frontend for Candidate, Reviewer and Administrator workspaces.

## Local setup (Windows PowerShell)

Use a current Node.js version compatible with the installed Vite release (Node
22.12+ or Node 24) and npm. From the project root:

```powershell
Set-Location frontend
npm.cmd ci
npm.cmd run dev
```

Open the local URL printed by Vite (normally `http://localhost:5173`). The existing
Vite proxy forwards `/api` to `http://127.0.0.1:8000`. Start your existing local
backend separately using its established development setup. No environment or
backend changes are needed for the frontend QA fixes. Do not share credentials
or replace the Gemini configuration as part of frontend testing.

## Routes and permissions

| Role | Routes |
| --- | --- |
| Public | `/`, `/login`, `/register` |
| Candidate | `/workspace`, `/upload`, `/documents`, `/files/:fileId`, `/profile` |
| Reviewer | `/reviewer/reviews`, `/reviewer/reviews/:reviewId` |
| Administrator | `/admin/reviews`, `/admin/reviews/:reviewId`, `/admin/dashboard`, `/admin/documents`, `/admin/documents/:fileId`, `/admin/candidates`, `/admin/candidates/:profileId`, `/admin/staff` |

`/dashboard`, `/admin` and `/reviewer` resolve to the verified account's workspace.
Login defaults are `/workspace`, `/reviewer/reviews` and `/admin/reviews`.
Only safe destinations belonging to the signed-in role are preserved. Wrong-role
routes show access denied; admin content is not mounted for reviewers/candidates.
Unknown routes show the not-found page.

## Final QA status and refresh behavior

Current final QA checks: 87 automated tests, TypeScript, ESLint and production
build pass. The latest browser acceptance attempts are **blocked**, not passed:
isolated Chrome and Edge GPU subprocesses terminate with Windows access-denied
errors (exit code -1073741790), and the browser dies before application navigation.
Desktop/tablet/mobile rendering and interactive keyboard/modal acceptance of these
latest changes remain unverified. Earlier milestone validation notes below are
historical and do not replace this current result.

Confirmed fixes: staff field errors now clear as the respective field is corrected;
stale form-level feedback clears on edits; account creation still clears all
errors and password on success. Clarification confirmation returns keyboard focus
to its own trigger. Upload success no longer starts an unnecessary read using the
previous upload loader. When the full document list fails, Profile explicitly shows an unavailable total rather than treating its capped embedded source list as complete.

Workspace and Profile now share a document-then-profile refresh cycle using the
existing candidate APIs. All document metadata pages are read, including active
jobs beyond the profile response's embedded file limit. Polling runs every five
seconds only while candidate documents are uploaded/processing. Completion gets
the profile in the same refresh; failed/needs-review/completed/empty results stop
candidate overview/profile polling. Review decisions made later are picked up on
route entry, tab return or explicit Refresh profile; waiting for review does not
poll indefinitely. Account verification is reused instead of repeated on every
profile poll.

The shared polling controller permits at most 60 cycles and five minutes per
mount/explicit refresh. Each cycle may make multiple metadata-page requests.
Hidden tabs pause automatic reads; returning performs one throttled refresh, even
after the polling budget expires, without silently restarting its budget. Requests
do not overlap within a mounted loader. Errors stop automatic retries; 401/403/
404/422 also suppress focus retries until an explicit refresh. Pending responses
are ignored after unmount/loader replacement. Static pages without polling do not
refetch on focus, preserving unsaved review forms. Admin monitoring retains its
five-second checks with the same finite budget. No read/refresh triggers mutations.

## Validation and browser acceptance

```powershell
npm.cmd test
npx.cmd tsc -p tsconfig.app.json --noEmit
npx.cmd tsc -p tsconfig.node.json --noEmit
npm.cmd run lint
npm.cmd run build
```

For browser acceptance, run Vite in one PowerShell window:

```powershell
npm.cmd run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

In a second window in `frontend/`:

```powershell
$env:UI_CHECK_URL = 'http://127.0.0.1:5174'
node tests/run-browser-qa.mjs
```

The runner launches isolated Chrome, checks renderer availability before testing,
and runs five suites sequentially. It refuses an occupied debugger port. Optional
settings: `QA_DEBUG_PORT` (default 9223) and `BROWSER_PATH` for an installed Chrome
or Edge executable. It closes only its own browser. Diagnostics/screenshots are
stored under ignored `.ui-check/`. All API traffic and mutations are mocked. No
real account creation, upload, review decision or job rerun is needed. Browser
coverage includes 1440px desktop, 768px tablet and 360/390px mobile, role isolation,
validation cleanup, processing-to-profile refresh, modal focus, Escape, Tab,
loading/empty/error states and responsive overflow. Added assertions still require
a successful local browser run; unit/service passes are not browser passes.

## Manual final acceptance (read-only against the real backend)

1. Sign in with each existing account at `/login`. Check its default destination,
   logout, refresh/deep-link return and sidebar links. Open other roles' URLs;
   verify access denied and no forbidden API reads in DevTools Network.
2. As administrator, visit dashboard, candidate list/detail/history, review queue/
   details and documents/details. Test filters, pagination, refresh, loading/empty/
   error messaging, source limitations and safe failed-extraction explanations.
   Do not confirm review decisions or reprocessing.
3. At `/admin/staff`, submit blank values. Correct name/email/password one at a
   time: each corrected field should lose its error; unrelated invalid fields
   retain theirs. Check labels and password visibility. Open confirmation, Tab/
   Shift+Tab through it, Cancel and Escape. Focus should return to its opener.
   **Do not confirm account creation during QA.** Success/duplicate-email/server
   cases must be tested through the mocked suite.
4. As candidate, navigate Overview, Upload, My Documents, File Details and Profile.
   Check existing records without uploading. Check Refresh profile. In DevTools,
   settled/failed documents should not cause Overview/Profile polling. Returning
   to the tab should trigger one refresh, not duplicate requests.
5. Use the mocked browser suite for processing-to-done profile updates and the
   finite polling budget. No successful extraction is claimed from existing failed
   Gemini jobs. A real successful extraction acceptance test remains blocked by
   backend configuration; it is outside this read-only QA pass.
6. Repeat at 1440, 768 and 360/390px widths. Check sidebar, long names, source
   dialogs, tables, buttons and confirmations for clipping. Use keyboard only:
   skip links, visible focus, labels, Tab/Shift+Tab, Enter and Escape. Verify focus
   returns to the clarification button when its confirmation is cancelled.
7. Test session expiration, forbidden access, 404 and server/network failure using
   mocks. Verify safe messages and no raw provider payloads, invented evidence,
   complete-history claims or automatic-email claims.

Delivery priorities: (1) obtain a full local browser acceptance pass and resolve
any failures; (2) manually check keyboard/mobile presentation; (3) validate the
successful extraction/review/profile/history path once backend AI configuration
works. Original-file access, comprehensive field provenance/history, full candidate
enumeration and broader staff management still need backend support. Candidate
profile editing/document replacement/deletion should not be represented as
implemented when the required backend operations are unavailable.
## Candidate workspace integration

The candidate pages share `src/components/layout/CandidateLayout.tsx` and its teal,
cream and gold design tokens. Upload and Profile use their existing API resources;
File Details uses `GET /api/v1/cv/files/{file_id}`. No backend changes are required
for the implemented UI.

### Available document actions

Before upload, PDF and Markdown selections can be opened locally and all supported
files can be downloaded. DOCX requires a compatible external application. Object
URLs are revoked on replacement, removal, successful upload and page unmount.

The running API's OpenAPI contract was inspected during implementation. It exposes
upload, paginated file metadata and file-detail metadata, but **no authorized route
returning an original uploaded document**. Persisted files therefore offer View
Details only. Preview/download require a backend capability returning the original
bytes with appropriate authorization, content type and download filename; the UI
does not fabricate a URL or treat metadata as file content.

### Timestamp semantics

`FileOut.uploaded_at`, `FileOut.finished_at` and `ProfileOut.updated_at` are nullable
`date-time` values in the inspected OpenAPI contract. It does not define whether
naive values represent UTC or another timezone. The observed input supplied for
this task, `2026-11-14 16:52:18.564152`, has no offset. Its origin timezone remains
unconfirmed; no backend or serialization changes were made.

`src/utils/dateTime.ts` renders every timestamp as English date/time text such as
`Nov 14, 2026 at 4:52 PM`. UTC (`Z`) and explicit-offset inputs represent instants
and are converted to the browser's local timezone, including daylight-saving
rules. Inputs without an offset preserve their supplied date and clock components.
The UTC calendar container used internally for this branch only prevents browser
local/DST normalization; it does not assign UTC semantics to the original value.

The formatter validates calendar dates and times, hides seconds/subseconds, and
returns “Not available” for missing or invalid input. It never appends a guessed
zone or manually adjusts hours. All candidate timestamp displays use this helper,
including upload tracking, the library, File Details and profile updates/sources.
Career/education partial dates retain their original calendar precision.

The user interface contains no raw ISO values or timezone diagnostics. To make
naive timestamps convertible to an exact local instant, the backend still needs
to confirm their timezone semantics and return `Z` or an explicit offset.
### Authentication and safe errors

Only HTTP 401 responses to authenticated requests invalidate the current token.
Network, 403, 404, validation and server errors keep the session. Stale requests
cannot clear a newer token. Candidate routes redirect unauthenticated users to
Login with a safe internal return destination; expired sessions display a clear
notice. Login restores the destination after authenticating. Tokens remain in the
existing sessionStorage location; no refresh-token or persistent-token behavior
was introduced.

`ApiError.status` retains safe diagnostic context. Raw backend error bodies and
model exceptions are never displayed or logged, because they can contain secrets.

### Validation

- `npm run build` performs TypeScript checking and builds production assets.
- `npm run lint` checks the frontend.
- `npm test` uses Node's built-in test runner for API/session/error handling,
  document validation, duplicate responses and timezone behavior.
- `node tests/browser-check.mjs` is an optional Chrome DevTools regression check.
  First run Vite on `127.0.0.1:5174` and a separate headless Chrome instance with
  remote debugging on `127.0.0.1:9223`. Overrides: `UI_CHECK_URL` and
  `CHROME_DEBUG_URL`. All API traffic in this check is intercepted with explicit
  test fixtures; it does not write to the real backend. It checks file input and
  drag/drop, local preview/download, URL cleanup, submission protection, status
  polling, navigation, account fallback, authentication, and responsive overflow
  at 320, 390, 768, 1024 and 1440 pixels. Screenshots and downloads go in the ignored
  `.ui-check/` directory. Close the dedicated browser after testing.

Authenticated end-to-end uploads against real accounts require the user's own
session and documents; the automated browser check deliberately uses mocked API
responses. Original-file retrieval and timezone semantics remain backend gaps.
### Files added or updated in the redesign

- Candidate pages and styles: `src/pages/candidate/UploadPage.tsx`,
  `UploadPage.css`, `ProfilePage.tsx`, `ProfilePage.css`, `FileDetailsPage.tsx`,
  `FileDetailsPage.css`.
- Navigation/authentication UI: `src/routes/AppRoutes.tsx`,
  `src/components/layout/Navbar.tsx`, `src/pages/auth/LoginPage.tsx`,
  `src/pages/auth/RegisterPage.tsx`.
- Shared UI: `src/components/layout/CandidateLayout.tsx`, `CandidateLayout.css`,
  `src/components/common/DocumentStatus.tsx`, `src/hooks/useRemoteData.ts`.
- Services/utilities: `src/services/apiClient.ts`, `session.ts`, `authService.ts`,
  `fileService.ts`, `profileService.ts`, `src/utils/dateTime.ts`, `documents.ts`.
- Checks/configuration/documentation: `tests/integration.test.mjs`,
  `tests/browser-check.mjs`, `package.json`, `eslint.config.js`, `.gitignore`,
  `README.md`. No new dependencies were added.
### Separate upload and document-library routes

- `/upload`: local file selection/preview/download, upload feedback and processing
  tracking. After a successful upload it polls that exact file ID; on a fresh
  visit it requests only the latest document (`limit=1`). It contains no document
  table and links to My Documents.
- `/documents`: the dedicated authenticated document library. It reuses the file
  service, polling hook, status badges and date/type utilities, requests 20 files
  per page, and stores the page number in `?page=N`. It includes automatic/manual
  refresh, loading/empty/error/retry states, file-detail links and an upload action.
- `/files/:fileId` and `/profile` retain their integrations. Their My Documents
  links now point to `/documents`. Sidebar selection follows the route; File
  Details remains within the My Documents navigation section. Sign-in return
  destinations include `/documents` and its pagination query.

`DocumentsPage.tsx` / `DocumentsPage.css` were added. The document table/styles
were moved out of UploadPage. CandidateLayout, AppRoutes, ProfilePage,
FileDetailsPage, session return-path validation and existing frontend tests were
updated. The browser check verifies that the two pages contain different
workflows, pagination across 41 test documents, all five statuses, exact-file
upload polling, route-based navigation and all existing file interactions.
Backend services/contracts and environment files were not changed.
### Landing Page

HomePage uses a minimal hero, three workflow steps, three verified capability
summaries, a short About section and a footer. How It Works, Features and About
have separate section anchors. Registration/sign-in links, mobile menu keyboard
behavior, session-aware CTAs and reduced-motion support are retained.

The original animated `cv-flow-*` illustration was recovered from the complete
HomePage markup and CSS read earlier in this conversation, before the latest
redesign. Git has no tracked frontend history. The existing `hero.png` is an
unrelated starter graphic and was not substituted. Original illustration paths,
source labels, profile artwork, sample counts, colors, responsive rules and
animations are preserved; only the outer size/placement changes. A separate
caption identifies it as conceptual and clarifies that its Assessment input is
not an available candidate feature. Product copy only describes implemented
uploads, processing statuses and available unified-profile data; it promises no
guaranteed processing success, automatic review resolution or direct integrations.

The browser regression check verifies the original diagram paths/content,
minimal section structure, navigation/CTA destinations, mobile keyboard controls,
authenticated CTAs and responsive layouts. Protected candidate routes and their
existing session handling are unchanged.
### Candidate Overview and sign-in entry point

`/workspace` is the default candidate destination after sign-in. Protected-page
return paths (including document pagination and profile anchors) still take
priority. The public registration API returns account metadata, not a token, so
registration continues to Login with an account-created notice. The intended
candidate destination survives registration; after successful authentication,
new candidates see Overview onboarding. Verified reviewers and administrators
continue to their role-specific manual review queues.

WorkspacePage reuses the shared candidate layout, account/profile services,
status/date components and polling hook. `workspaceService.ts` reads every
100-record page from `GET /cv/files` to compute accurate document-status counts
and retain the first five recent records in the backend's order. Failed or
inconsistent pages do not produce zero or partial statistics. There is no
aggregate-count endpoint in the current API; reading all metadata pages keeps
the summary correct but costs more requests for large libraries. Profile review
counts come from `GET /profile/me` and are not estimated from partial file lists.
No original-file download or review-resolution actions are invented.

The sidebar contains Overview, Upload Documents, My Documents and My Profile.
File Details remains a nested candidate route within the document section.
Authenticated Landing Page workspace CTAs now link to `/workspace`. Existing
Upload, Documents, File Details, Profile APIs and session expiry behavior remain
in use. Tests cover multi-page totals, empty/error states, registration/sign-in
and protected destinations, both other login roles and responsive navigation.
### Candidate field provenance: verified scope and backend gaps

Inspected the running OpenAPI contract and the backend implementation available
in Git commit `6b84308` (read-only; no backend files were edited):

- `GET /profile/me` returns the merged profile and connected file metadata.
  `PersonalInfoRecord.field_ids` is explicitly a field-name-to-extracted-field-ID
  map. Entity `field_ids` arrays likewise reference extracted field records.
  They are not file IDs or stable per-property document mappings.
- `StoredDocumentReader.read` and `SqlProcessingRepository.load_profile_field_records`
  set each source to `str(file_id)`. `ProfileBuilder._skills` copies those source
  strings into `SkillRecord.sources` and unions supporting sources. This makes
  canonical numeric skill source references resolvable through candidate-owned
  file metadata. Source strings and `field_ids` arrays are not index-aligned.
- `GET /profile/{profile_id}/history` exposes change-file links but is restricted
  to administrators. Review queue/detail endpoints are restricted to reviewers
  and administrators. Candidate pages do not request or attempt to bypass them.
- The candidate profile omits pending-review values and has only an aggregate
  `open_reviews` count. There is no candidate-visible per-field review state,
  current-value provenance lookup, or original-value/evidence endpoint.

Implemented skill Source icon buttons and a small native dialog with keyboard
focus management, Escape/backdrop closing and responsive sizing. Each supporting
document has a separate name, known document type and authorized File Details
link. Metadata already in the profile is reused; older references outside the
backend's 100-file profile metadata cap are fetched on demand through
`GET /cv/files/{file_id}`. Missing or mismatched metadata produces an unavailable
state, never a guessed file. Non-numeric source labels/filenames are not matched.
The displayed skill is labeled “Profile value”; it is not presented as original
per-document extracted text. No confidence or evidence is fabricated.

Reliable provenance is currently available for skills with these verified source
references. Name, email, phone, title, city/country, summary, experience, education,
certifications, projects, languages and professional links cannot map their field
record IDs to documents with the candidate contract. They remain unbadged. No
field-level review badge is inferred from file statuses, aggregate review counts,
different-looking values or a skill's `verified` flag. The existing profile-level
review summary remains in place.

Full field-level support requires a candidate-authorized mapping from each
current profile field/path or extracted-field ID to its source file(s), with
ownership checks and document metadata. Source-specific values and explicit
field review state would also need to be exposed to candidates where permitted.
Documenting the encoding of `SkillRecord.sources` in OpenAPI would make that
existing convention explicit. Neither latest-upload guesses nor staff-only
history endpoints are a substitute for this missing contract.
### Verified sessions and route access

Login keeps the access token transient while `GET /auth/me` validates the
identity and supported role. Only a successful verification stores the token.
Failed credentials, network/server errors, malformed responses and unsupported
roles leave no login token behind. A session revision prevents an interrupted
login from restoring a logged-out session or replacing a newer login.

Candidate navigation requires a verified candidate role. Landing Page workspace
actions follow the verified account role. Stored sessions are checked again after a page reload; failures
block candidate content with retry/sign-in controls. Existing-session network
failures do not invalidate a token; authenticated 401 responses still do. Verified
roles are cached only in memory for the current session. Backend authorization
remains authoritative.

Candidates keep safe intended destinations, including queries and profile anchors.
Staff keep safe intended destinations within their own review workspace.
The legacy `/dashboard`, `/admin`, and `/reviewer` entry points follow the verified
account role; unknown addresses show a branded
404 page. Staff workspaces show actual backend review data and confirmed review
decisions.
Failed-file guidance explains that uploading identical bytes does not restart
processing and directs the candidate to their CVerge team.

### Staff manual review milestone

Verified reviewers land at `/reviewer/reviews`; administrators land at
`/admin/reviews`. Both workspaces use the same queue and detail components.
Each workspace checks the verified role before mounting its content. Wrong-role
access shows an access-denied page with a link to the user's own workspace.
Unauthenticated deep links continue through sign-in, preserving only safe
destinations belonging to the authenticated role.

The review service follows the current backend schemas and uses these endpoints:

- `GET /api/v1/review/items`
- `GET /api/v1/review/items/{review_id}`
- `POST /api/v1/review/items/{review_id}/resolve`
- `POST /api/v1/review/items/{review_id}/request-candidate`

The queue supports status (`open`, `waiting_candidate`, `resolved`, `all`),
reason, candidate profile ID, and 20-item pagination. Filters/page live in the URL
and survive opening details and returning. Open includes waiting-candidate items,
as implemented by the backend. Refresh is manual.

Details show candidate/source references, field/entity, reasons, context,
alternatives, available confidence/evidence/page, and existing resolution metadata.
No candidate profile, history, file-management, or original-file endpoint is
requested by these pages. Missing confidence/evidence is labeled unavailable.
Review decisions and clarification preparation are supported as described below.
The Admin Dashboard is implemented in the later milestone below. Original-file preview remains unavailable.
Production pages contain no fixture data.

Validation:

- `npm test`: service/session tests plus staff routing and rendered-page tests.
- `npm run lint`, `npm run build`: lint, TypeScript, and production bundling.
- `node tests/staff-browser-check.mjs`: local browser interactions, access guards,
  filters/pagination, details, error states, and mobile/desktop layouts.
- `node tests/browser-check.mjs`: existing candidate regression, updated staff
  destinations, and account switching.

Browser scripts use mocked API traffic in a dedicated headless Chrome with remote
debugging at `http://127.0.0.1:9223` and Vite at `http://127.0.0.1:5174`.
They write ignored artifacts only under `frontend/.ui-check/`. No real backend
records are created or changed. Live backend acceptance testing is still needed.

### Confirmed review decisions and role entry points

Login preserves safe deep links for the verified role. Already authenticated users
visiting Login return to their workspace. The old dashboard entry now waits for
identity verification and routes administrators to /admin/reviews, reviewers to
/reviewer/reviews, and candidates to /workspace. Public Home remains available.

Field decisions support the backend's option, custom, and reject actions.
Document-level failed items expose dismiss only. Dismissal closes the queue item;
it does not retry processing or change the profile. Unknown skill names can be
approved or mapped using map_to_skill. There is no skill catalogue listing API,
so standard skill mapping uses a validated text field rather than invented options.

Each mutation requires a confirmation dialog. The UI prevents duplicate submits,
keeps corrections after validation errors, reloads on conflicts, and requires a
refresh after permission failures or uncertain saves. Saved responses are displayed
immediately, followed by a fresh item GET. Review changes invalidate queue data;
returning to the queue fetches its filtered list again.

Clarification uses the existing request-candidate endpoint, records the waiting
state, and displays the returned suggested message with an optional email draft.
CVerge does not send email. The UI never presents a recorded request as a sent email.

Raw review context/provider errors are not displayed. Known invalid API
configuration, usage-limit, permission, unavailable-model, and timeout cases have
fixed human-readable explanations. Unknown failures use a safe fallback.
Actual source alternatives/evidence remain visible and escaped as text.

The browser regression mocks all mutations and covers cancel/reopen confirmation,
double submission, option/custom/reject/dismiss, skill approval/mapping, clarification,
persisted-state/queue refresh, and 403/409/422 recovery. Unit tests also cover mutation
401s, safe error classification, validation, and email draft encoding.
Live field/conflict testing needs a successfully extracted review item; existing
failed AI jobs alone cannot provide alternatives. No backend, database, or AI
configuration changes are part of this implementation.

### Admin Documents & Processing

Administrators can open `/admin/documents` from their sidebar and
`/admin/documents/{file_id}` for details. Safe sign-in return paths include these
routes and their filter/page queries. Reviewers and candidates are blocked by the
role guard before admin pages mount or request data. The default admin landing
remains the Manual Review Queue.

The typed admin service uses only:

- `GET /api/v1/admin/files` with optional `status`, `profile_id`, `limit`, `offset`.
- `GET /api/v1/admin/files/{file_id}`.
- `POST /api/v1/admin/files/{file_id}/rerun`, only after explicit confirmation.

The list shows candidate name/user/profile references, source file, upload time,
actual processing status, attempt count and open-review count. Status/profile
filters and 20-item pages are stored in the URL. Details show available extraction
metadata, OCR confidence, timestamps and every returned attempt with trigger,
outcome, provider/model and safe failure explanations. A complete status-change
history, original-file download and additional processing stages are not exposed
by this contract and are not inferred.

List/detail reads refresh every five seconds while visible for up to five minutes; manual refresh is
also available. Reading, navigating, polling, and refreshing never request a rerun.
Reruns use the stored original and can update the profile/review items. A native
confirmation dialog explains this; double submissions and concurrent requests in
the current app session are blocked.

The backend returns 202 with file_id, status and message. Its status can still be
the old value: acceptance does not mean the worker started or finished. The UI
shows the accepted file/status separately and waits for actual GET updates.
Accepted or uncertain requests remain locked across in-app navigation until a
new completed attempt or an observed processing-to-terminal transition appears.
The backend exposes no durable queued-rerun flag or idempotency key. These
client-side markers live in memory; a full reload cannot reconstruct a pending
request whose backend status has not changed. Inspect status/attempts before
requesting another run.

Raw provider error payloads and response error bodies are never displayed.
Shared processing-error classification also preserves the existing safe review
messages. Forbidden/missing/error reads hide actionable document details.
A 409 rerun response refreshes current state; 403/404/422 failures require a manual
refresh before another attempt. Network/server failures are treated as uncertain,
rather than reported as definitely failed.

Validation includes the regular unit/service/render tests and
`node tests/admin-documents-browser-check.mjs`. Browser tests mock all admin
mutations, including 202 with unchanged status, double confirmation, pending and
uncertain outcomes, recorded-attempt updates, supported filters, pagination,
role isolation and HTTP error states. No real backend reruns are part of testing.

Manual testing with the existing local admin:

1. Open `http://localhost:5173/login` and sign in with your existing admin account.
2. Open Documents & Processing, or `http://localhost:5173/admin/documents`.
3. Filter by Failed and candidate profile ID 1; open an existing file. Previous
   local files were IDs 2 and 3. Verify the actual list before selecting one.
4. Check source/candidate metadata, attempts and the safe invalid-AI-configuration
   explanation. Use Refresh document and return to the list to check URL filters.
5. Open Reprocess document and choose Cancel to test confirmation without mutation.
   Only choose Confirm reprocess when intentionally authorizing a real new job.
   The existing invalid AI configuration is not repaired by reprocessing.
6. Sign out and check the admin document URLs as a reviewer/candidate. Access must
   be denied without any admin file requests in the Network panel.

### Admin Dashboard and read-only Candidate Management

New routes:

- /admin/dashboard: global backend aggregation, processing status links, and
  navigation to review, documents and candidate management.
- /admin/candidates: candidates identified through uploaded-document metadata.
- /admin/candidates/{profile_id}: account/profile details, available skill sources,
  connected documents and paginated recorded profile history.

Default login destinations remain unchanged. Safe administrator returns now include
the new routes; reviewer/candidate guards still prevent admin content/API access.
Admin document/review screens link back to the corresponding candidate profile.

GET /admin/dashboard supplies the registered candidate count, document total and
status counts, review counts, and available extraction quality aggregates.
Incomplete/inconsistent responses are rejected rather than filled with zeros.
Null rates display as unavailable. The field-review share includes all review
reasons; typed corrections are a count and do not stand in for all changed
review decisions. No missing conflict, duplicate, trend or cost metrics are invented.

There is no candidate enumeration or server-side candidate search API. The
directory loads every 100-item page of GET /admin/files, verifies total/uniqueness/
coverage, and groups actual profile/user references. It stops if pagination changes
or the session changes while loading. Its name/ID search, document-status filter
and 20-item pagination run locally without refetching every page. Coverage is
explicitly candidates with uploads, not all registered accounts. Accounts without
uploads cannot be enumerated; a known profile ID can be opened directly.

GET /profile/{profile_id} and GET /profile/{profile_id}/history?limit=20&offset=...
provide the read-only profile and recorded history. Professional sections render
only returned fields, dates retain their supplied precision, and unsafe links are
not activated. A null extracted profile preserves account/source navigation.
The profile's embedded source list is capped at 100; full document pagination
remains available in Documents & Processing.

Skill document links use explicit numeric sources, never field_ids or filename
guesses. Missing older metadata is resolved through administrator file GETs, with
a profile-ID match check. Sources not resolved by the contract remain unavailable.
The API does not expose full per-field source/confidence/rule/evidence lookup.
Field-record IDs are displayed as references only. History displays actual
before/after, actor, reason, time and source references; backend logging does not
guarantee every automatic child-record change is covered.

No candidate edit/delete/role mutation or processing mutation is included.
The available POST /admin/users creates staff accounts and does not supply a
candidate directory. The linked wireframe could not be accessed; these screens
follow requirements.md and the existing CVerge visual system.

Validation: npm test, npm run lint, npm run build, plus
node tests/admin-workspace-browser-check.mjs and the existing staff, admin-document,
and candidate browser regressions. The new browser check fulfills API reads with
fixtures and rejects unexpected mutations; other regression mutations remain
mocked. Nothing writes to the real database or queues processing.

Manual test with your existing local administrator:

1. Open http://localhost:5173/login and sign in using your existing account.
   The preserved default destination is /admin/reviews.
2. Open Dashboard in the sidebar or http://localhost:5173/admin/dashboard.
   Check aggregate cards, unavailable rates, status links and manual refresh.
3. Open Candidate Management or http://localhost:5173/admin/candidates.
   Check the upload-only coverage note, name/ID search, document-status filter,
   local paging, clear filters and refresh.
4. Open a candidate from the actual list. Check /admin/candidates/{profile_id},
   returned professional sections or the null-profile state, documents/reviews,
   field-reference limitations, and skill supporting documents where supplied.
5. Check recorded history and Next/Previous when enough changes exist. An empty
   history is valid; no records are fabricated. Follow a source to Documents &
   Processing and return through View candidate profile.
6. Refresh a profile deep link and sign out/in to verify its safe return. Repeat
   admin URLs using a reviewer/candidate account: access should be denied and
   no admin dashboard/profile/history requests should appear in Network.
7. Keep this milestone read-only during manual testing. Do not confirm existing
   review decisions or reruns merely to test dashboard/candidate navigation.

## Staff Account Management

Administrator-only route: `/admin/staff`, available through Staff Management in
the sidebar and the dashboard. Reviewer and candidate sessions cannot enter this
page. Login destinations are unchanged, and an administrator can return safely to
this deep link after login or session expiry.

The inspected backend supports only authenticated `POST /api/v1/admin/users`.
The request contains name (2–255 characters), email, password (8–128 characters),
and role (`reviewer` or `administrator`). The 201 response contains `user_id`,
`name`, `email`, and `role`. Email is normalized to lowercase; password whitespace
is preserved. Backend email validation remains authoritative.

The form validates fields, offers password visibility, and requires a second
confirmation showing the selected identity and access. Concurrent submissions
are prevented. Success displays the returned account, not a fabricated directory.
Passwords are cleared after each completed request and are never displayed in
the confirmation/success panel or stored by this feature. Duplicate email (409),
validation (422), expired session (401), forbidden (403), and server/network errors
have safe feedback. Uncertain outcomes require an explicit preparation step and
a fresh confirmation before another request; there are no automatic retries.

There is no staff listing, editing, deletion, role-change, password-reset or
invitation endpoint. This feature sends no invitation email and does not add
unsupported account-management actions.

Validation for this milestone: explicit TypeScript checks, ESLint, all 80 frontend
tests, and the production build passed. The new
`tests/staff-management-browser-check.mjs` intercepts all account creation calls
and covers both roles, confirmation/cancellation, validation, errors, safe return,
role guards and responsive views. Browser execution was attempted in the managed
environment but blocked by Chrome renderer startup (`Page.enable` timeout);
browser regression checks still need a successful local run. No real accounts
were created during implementation/testing.

Run the mocked browser checks locally in PowerShell from `frontend/`, with Vite
running separately. Use an isolated Chrome test profile:

```powershell
npm.cmd run dev -- --host 127.0.0.1 --port 5174 --strictPort
```

In another PowerShell window in `frontend/`:

```powershell
$testProfile = Join-Path (Get-Location) '.ui-check\staff-manual-chrome'
Start-Process 'C:\Program Files\Google\Chrome\Application\chrome.exe' -WindowStyle Hidden -ArgumentList @('--headless=new', '--disable-gpu', '--remote-debugging-port=9223', "--user-data-dir=`"$testProfile`"", 'about:blank')
$env:UI_CHECK_URL = 'http://127.0.0.1:5174'
node tests/staff-management-browser-check.mjs
node tests/staff-browser-check.mjs
node tests/admin-documents-browser-check.mjs
node tests/admin-workspace-browser-check.mjs
node tests/browser-check.mjs
```

Run scripts sequentially. Their API responses and mutations are mocked; they do
not require a real account or create real records. Close the isolated test Chrome
instance afterward. The app's normal local backend/frontend setup is unchanged.

Manual testing with the existing local administrator:

1. Start the existing local backend and frontend as usual. Open the frontend's
   printed local URL, sign in with the existing administrator account, then use
   Staff Management or `/admin/staff`.
2. Submit empty/invalid fields and check focused, readable validation. Enter
   intended account details, toggle password visibility, and inspect both role
   descriptions. Opening confirmation does not create an account.
3. Check the normalized email, selected role and access warning in confirmation.
   Cancel or press Escape; verify no POST request was sent. This is the safe
   stopping point when no real account creation is intended.
4. Only when you explicitly intend to create a real account, select the intended
   role and confirm creation once. This writes to the real database. Check the
   returned name/email/role/user ID and cleared password. No email is sent.
5. If an account was deliberately created, sign out and sign in with that email
   and the password you supplied. A reviewer lands at `/reviewer/reviews`; an
   administrator lands at `/admin/reviews`. Only administrators see Staff
   Management. Use a different email for each intended new account.
6. With a reviewer and candidate session, open `/admin/staff` directly. Verify
   the role restriction and absence of `/admin/users` calls. Check sidebar
   navigation, mobile width, keyboard focus, and sign-out/login deep-link return.
7. Exercise 401/403/409/422/network/server cases through the mocked test rather
   than creating unwanted accounts or changing the real database. An uncertain
   real response may already have created the account: verify before retrying.

Before final delivery: complete the browser checks above and keyboard/mobile
acceptance; verify extraction-to-review-to-profile/history with a working backend
AI configuration (currently blocked by the reported Gemini configuration error);
and verify the implemented bounded candidate profile refresh flow with successful processing.
Backend gaps remain for full candidate enumeration/search, comprehensive field
source evidence, and unsupported account-management operations. These require
backend support rather than invented frontend endpoints or records.
