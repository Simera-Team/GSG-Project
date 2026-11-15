# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Oxc](https://oxc.rs)
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/)

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...

      // Remove tseslint.configs.recommended and replace with this
      tseslint.configs.recommendedTypeChecked,
      // Alternatively, use this for stricter rules
      tseslint.configs.strictTypeChecked,
      // Optionally, add this for stylistic rules
      tseslint.configs.stylisticTypeChecked,

      // Other configs...
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])

```

You can also install [eslint-plugin-react-x](https://npmx.dev/package/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://npmx.dev/package/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from 'eslint-plugin-react-x'
import reactDom from 'eslint-plugin-react-dom'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...
      // Enable lint rules for React
      reactX.configs['recommended-typescript'],
      // Enable lint rules for React DOM
      reactDom.configs.recommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])

```

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
new candidates see Overview onboarding. Verified administrators and reviewers return to the Landing Page with an account
notice because staff pages are not implemented in this frontend.

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
  and administrators. The frontend does not request or attempt to bypass them.
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

Candidate navigation and Landing Page workspace actions require a verified
candidate role. Stored sessions are checked again after a page reload; failures
block candidate content with retry/sign-in controls. Existing-session network
failures do not invalidate a token; authenticated 401 responses still do. Verified
roles are cached only in memory for the current session. Backend authorization
remains authoritative.

Candidates keep safe intended destinations, including queries and profile anchors.
Staff return to Home with a clear notice and account-switch/sign-out controls.
The legacy `/dashboard` address redirects Home; unknown addresses show a branded
404 page. No staff workspace or review-resolution functionality is fabricated.
Failed-file guidance explains that uploading identical bytes does not restart
processing and directs the candidate to their CVerge team.
