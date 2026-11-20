import assert from "node:assert/strict";
import { readFileSync, existsSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import ts from "typescript";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import * as router from "react-router-dom";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "../src");
const requireExternal = createRequire(import.meta.url);
const cache = new Map();
let sessionState = {};
let remoteState = {};
function load(path) {
  if (!path.startsWith(root)) path = resolve(root, path);
  if (!existsSync(path)) path += existsSync(path + ".tsx") ? ".tsx" : ".ts";
  if (cache.has(path)) return cache.get(path).exports;
  const source = readFileSync(path, "utf8").replace("import.meta.env.VITE_API_BASE_URL", "undefined");
  const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.ReactJSX } });
  const module = { exports: {} };
  cache.set(path, module);
  new Function("exports", "module", "require", outputText)(module.exports, module, dependency => {
    if (dependency.endsWith(".css")) return {};
    if (dependency.endsWith("/useSessionUser")) return { useSessionUser: () => sessionState };
    if (dependency.endsWith("/useRemoteData")) return { useRemoteData: () => remoteState };
    if (dependency === "react-router-dom") return { ...router, Navigate: ({ to, state }) => React.createElement("i", { "data-redirect": to, "data-from": state?.from }) };
    return dependency.startsWith(".") ? load(resolve(dirname(path), dependency)) : requireExternal(dependency);
  });
  return module.exports;
}
const storage = new Map();
globalThis.sessionStorage = { getItem: key => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key) };
globalThis.window = new EventTarget();
const session = load("services/session");
const auth = load("services/authService");
const access = load("services/roleAccess");
const review = load("services/reviewService");
const utils = load("utils/reviews");
const Gate = load("components/layout/RoleGate").default;
const Queue = load("pages/staff/ReviewQueuePage").default;
const Details = load("pages/staff/ReviewItemPage").default;
const json = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const account = { user_id: 7, name: "Reviewer", email: "reviewer@example.invalid", role: "reviewer" };

test("staff field edits clear corrected validation and duplicate-email errors without hiding other invalid fields", () => {
  const { staffErrorsAfterEdit, validateStaffForm } = load("utils/staffAccounts");
  const values = { name: "", email: "", password: "", role: "reviewer" };
  const errors = validateStaffForm(values);
  const correctedName = staffErrorsAfterEdit(errors, { ...values, name: "Valid Name" }, "name");
  assert.equal(correctedName.name, undefined);
  assert.ok(correctedName.email); assert.ok(correctedName.password);
  assert.ok(staffErrorsAfterEdit(errors, { ...values, name: "A" }, "name").name);
  const correctedEmail = staffErrorsAfterEdit({ email: "Already registered" }, { ...values, email: "new@example.com" }, "email");
  assert.deepEqual(correctedEmail, {});
  assert.deepEqual(staffErrorsAfterEdit({}, values, "password"), {}, "untouched fields do not suddenly become invalid");
  assert.equal(staffErrorsAfterEdit({ password: "Too short" }, { ...values, password: "valid-password" }, "password").password, undefined);
});

test("candidate profile never presents a capped embedded source list as the full document count after a list failure", () => {
  const Profile = load("pages/candidate/ProfilePage").default;
  const file = { file_id: 12, original_name: "source.pdf", file_type: "pdf", status: "failed", uploaded_at: null };
  remoteState = { loading: false, error: "", retry() {}, data: {
    data: { profile: null, files: [file], candidate_name: "Candidate", open_reviews: 0 },
    files: null, filesError: "We could not load your documents.", profileError: "", accountError: "",
  } };
  const unavailable = render(React.createElement(Profile), "/profile");
  assert.match(unavailable, /full document count is unavailable/);
  assert.match(unavailable, /Only profile-linked documents/);
  assert.match(unavailable, /pr-metrics"><span><strong>—<\/strong> documents/);
  assert.doesNotMatch(unavailable, /pr-welcome/);
  remoteState.data.files = { total: 101, items: [file] };
  remoteState.data.filesError = "";
  const available = render(React.createElement(Profile), "/profile");
  assert.match(available, /pr-metrics"><span><strong>101<\/strong> documents/);
  assert.doesNotMatch(available, /full document count is unavailable/);
});
const fixture = {
  review_id: 42, profile_id: 8, candidate_name: "Test Candidate", candidate_email: "candidate@example.invalid",
  file_id: 12, file_name: "cv.pdf", file_type: "pdf", entity: "personal_info", field_name: "city",
  reasons: ["source_conflict"], message: "The sources contain different values", is_failed_job: false, created_at: null,
  assigned_to_candidate: false, sent_to_candidate_at: null, resolved: false, resolution: null,
  resolved_value: null, resolved_option_id: null, resolved_by: null, resolved_by_name: null, resolved_at: null,
  options: [{ option_id: 11, file_id: 12, file_name: "cv.pdf", file_type: "pdf", field_id: 90, value: "Amman", confidence: 0.82, evidence: "<script>unsafe()</script>", page: 2 }],
};
function render(element, path = "/reviewer/reviews") {
  return renderToStaticMarkup(React.createElement(router.MemoryRouter, { initialEntries: [path] }, element));
}
function page(Component, path = "/reviewer/reviews") {
  return render(React.createElement(router.Routes, null,
    React.createElement(router.Route, { path: "/reviewer/reviews", element: React.createElement(router.Outlet, { context: { queuePath: "/reviewer/reviews" } }) },
      React.createElement(router.Route, { index: true, element: React.createElement(Component) }),
      React.createElement(router.Route, { path: ":reviewId", element: React.createElement(Component) }))), path);
}

test("role destinations preserve only the matching workspace and reject external returns", () => {
  assert.equal(auth.loginDestination("candidate", "/documents?page=2"), "/documents?page=2");
  for (const [role, home] of Object.entries(access.roleHome)) {
    assert.equal(auth.loginDestination(role, undefined), home);
    for (const unsafe of ["//evil.example", "https://evil.example", "/login", "/reviewer/reviews/1/extra", "/admin/users"]) {
      assert.equal(auth.loginDestination(role, unsafe), home);
    }
  }
  assert.equal(auth.loginDestination("reviewer", "/reviewer/reviews/42?status=all&page=2"), "/reviewer/reviews/42?status=all&page=2");
  assert.equal(auth.loginDestination("administrator", "/admin/reviews?reason=no_text"), "/admin/reviews?reason=no_text");
  assert.equal(auth.loginDestination("reviewer", "/admin/reviews"), "/reviewer/reviews");
  assert.equal(auth.loginDestination("administrator", "/reviewer/reviews/42"), "/admin/reviews");
  assert.equal(auth.loginDestination("candidate", "/reviewer/reviews"), "/workspace");
  assert.equal(access.safeLoginReturnPath("/reviewer/reviews/42?status=all"), "/reviewer/reviews/42?status=all");
  assert.equal(access.safeLoginReturnPath("//evil.example"), undefined);
});

test("route gate blocks guests, pending identities, verification failures and every wrong role", () => {
  const child = React.createElement("b", null, "PROTECTED CONTENT");
  sessionState = { token: null };
  let html = render(React.createElement(Gate, { role: "reviewer" }, child), "/reviewer/reviews/42?status=all");
  assert.match(html, /data-redirect="\/login"/);
  assert.match(html, /data-from="\/reviewer\/reviews\/42\?status=all"/);
  for (const state of [{ token: "token", loading: true }, { token: "token", error: "Verification failed" }, { token: "token", user: null }]) {
    sessionState = state;
    assert.doesNotMatch(render(React.createElement(Gate, { role: "reviewer" }, child)), /PROTECTED CONTENT/);
  }
  for (const role of Object.keys(access.roleHome)) {
    for (const workspace of Object.keys(access.roleHome)) {
      sessionState = { token: "token", user: { ...account, role } };
      html = render(React.createElement(Gate, { role: workspace }, child));
      if (role === workspace) assert.match(html, /PROTECTED CONTENT/);
      else {
        assert.doesNotMatch(html, /PROTECTED CONTENT/);
        assert.match(html, /Access denied/);
        assert.ok(html.includes('href="' + access.roleHome[role] + '"'));
      }
    }
  }
});

test("review list uses the actual query contract and bearer authentication", async () => {
  session.setAccessToken("staff-token");
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push(url);
    assert.equal(init.headers.get("Authorization"), "Bearer staff-token");
    assert.equal(init.method, undefined);
    return json({ total: 1, limit: 20, offset: 20, items: [fixture] });
  };
  const result = await review.getReviewItems({ status: "waiting_candidate", reason: "source_conflict", profileId: 8, limit: 20, offset: 20 });
  const query = new URL(calls[0], "https://example.invalid").searchParams;
  assert.equal(query.get("status"), "waiting_candidate");
  assert.equal(query.get("reason"), "source_conflict");
  assert.equal(query.get("profile_id"), "8");
  assert.equal(query.get("offset"), "20");
  assert.equal(result.items[0].review_id, 42);
  for (const status of ["open", "waiting_candidate", "resolved", "all"]) await review.getReviewItems({ status });
  assert.ok(calls.every(url => url.startsWith("/api/v1/review/items?")));
});

test("invalid review IDs and pagination never reach the server", async () => {
  globalThis.fetch = async () => { throw Error("Should not fetch"); };
  for (const id of [0, -1, NaN, 1.2, Number.MAX_SAFE_INTEGER + 1]) await assert.rejects(review.getReviewItem(id), /invalid/);
  for (const options of [{ limit: 101 }, { offset: -1 }, { profileId: 0 }, { status: "made_up" }]) await assert.rejects(review.getReviewItems(options), /valid review filters/);
  assert.deepEqual(utils.parseReviewQuery(new URLSearchParams("status=bad&page=-1&profile_id=oops")), { status: "open", reason: "", page: 1, profileId: undefined });
  assert.equal(utils.parseReviewQuery(new URLSearchParams("page=9007199254740991")).page, 1);
});

test("details use only review GET, handle missing records and preserve forbidden sessions", async () => {
  session.setAccessToken("staff-token");
  globalThis.fetch = async (url, init) => {
    assert.equal(url, "/api/v1/review/items/42");
    assert.equal(init.method, undefined);
    return json(fixture);
  };
  assert.deepEqual(await review.getReviewItem(42), fixture);
  globalThis.fetch = async () => json({ detail: "SECRET" }, 404);
  await assert.rejects(review.getReviewItem(42), error => error.status === 404 && /review item is unavailable/.test(error.message));
  globalThis.fetch = async () => json({ detail: "SECRET" }, 403);
  await assert.rejects(review.getReviewItems(), error => error.status === 403 && !error.message.includes("SECRET"));
  assert.equal(session.getAccessToken(), "staff-token");
  globalThis.fetch = async () => json({}, 401);
  await assert.rejects(review.getReviewItem(42), error => error.status === 401);
  assert.equal(session.getAccessToken(), null);
});

test("queue renders supplied records, filter values, confidence and preserved detail links", () => {
  remoteState = { data: { total: 21, limit: 20, offset: 20, items: [fixture] }, loading: false };
  const html = page(Queue, "/reviewer/reviews?status=all&reason=source_conflict&profile_id=8&page=2");
  for (const text of ["Test Candidate", "Source conflict", "82%", "Profile #", "Page 2 of 2"]) assert.ok(html.includes(text), text);
  assert.match(html, /value="all" selected/);
  assert.match(html, /value="source_conflict" selected/);
  assert.match(html, /\/reviewer\/reviews\/42\?status=all&amp;reason=source_conflict&amp;profile_id=8&amp;page=2/);
  assert.doesNotMatch(html, /href="\/(admin|profile|files)\//);
});

test("queue distinguishes loading, empty and failed requests without exposing stale rows", () => {
  remoteState = { loading: true };
  assert.match(page(Queue), /Loading review items/);
  remoteState = { loading: false, data: { total: 0, items: [] } };
  assert.match(page(Queue), /No review items found/);
  remoteState = { loading: false, error: "You do not have permission.", data: { total: 1, items: [fixture] } };
  const html = page(Queue);
  assert.match(html, /role="alert"/);
  assert.doesNotMatch(html, /Test Candidate/);
});

test("details render escaped evidence, alternatives, source references and resolution context", () => {
  remoteState = { loading: false, data: fixture };
  let html = page(Details, "/reviewer/reviews/42?status=all&page=2");
  for (const value of ["Amman", "82%", "Page 2", "cv.pdf", "Field record #", "The sources contain different values"]) assert.ok(html.includes(value), value);
  assert.ok(html.includes("&lt;script&gt;unsafe()&lt;/script&gt;"));
  assert.doesNotMatch(html, /<script>|href="\/(admin|profile|files)\//);
  assert.ok(html.includes('href="/reviewer/reviews?status=all&amp;page=2"'));
  assert.match(html, /Review and confirm/);
  remoteState = { loading: false, data: { ...fixture, resolved: true, resolution: "option", resolved_value: "Amman", resolved_by_name: "Rania", resolved_at: "2026-11-15T10:00:00Z" } };
  html = page(Details, "/reviewer/reviews/42");
  assert.match(html, /Recorded resolution/);
  assert.match(html, /Rania/);
});

test("failed jobs and null evidence render honest fallbacks", () => {
  remoteState = { loading: false, data: { ...fixture, is_failed_job: true, field_name: null, entity: null, options: [] } };
  assert.match(page(Details, "/reviewer/reviews/42"), /Failed document — no field to review/);
  assert.match(page(Details, "/reviewer/reviews/42"), /No field alternatives supplied/);
  remoteState = { loading: false, data: { ...fixture, options: [{ ...fixture.options[0], confidence: null, evidence: null, value: null, page: null }] } };
  const html = page(Details, "/reviewer/reviews/42");
  assert.match(html, /Confidence: Not available/);
  assert.match(html, /No evidence snippet supplied/);
  assert.equal(utils.reviewStatus({ ...fixture, assigned_to_candidate: true }), "Waiting for candidate");
});

const decisions = load("utils/reviewDecisions");
const WorkspaceRedirect = load("components/layout/WorkspaceRedirect").default;
const Login = load("pages/auth/LoginPage").default;

test("verified Admin login and legacy entries route to the queue, retaining safe deep links", () => {
  for (const [role, destination] of Object.entries(access.roleHome)) {
    sessionState = { token: "verified", user: { ...account, role }, loading: false };
    assert.ok(render(React.createElement(WorkspaceRedirect), "/dashboard").includes('data-redirect="' + destination + '"'));
    assert.ok(render(React.createElement(Login), "/login").includes('data-redirect="' + destination + '"'));
  }
  sessionState = { token: "verified", user: { ...account, role: "administrator" }, loading: false };
  assert.ok(render(React.createElement(Login), { pathname: "/login", state: { from: "/admin/reviews/42?status=all" } }).includes('data-redirect="/admin/reviews/42?status=all"'));
  sessionState = { token: "unverified", user: null, loading: true };
  assert.doesNotMatch(render(React.createElement(WorkspaceRedirect), "/dashboard"), /data-redirect/);
});

test("decision validation follows field/failed-document actions and item-owned alternatives", () => {
  assert.deepEqual(decisions.buildResolveRequest(fixture, "option", "11", "", null), { action: "option", option_id: 11 });
  assert.deepEqual(decisions.buildResolveRequest(fixture, "custom", "", "  Dubai  ", null), { action: "custom", value: "Dubai" });
  assert.deepEqual(decisions.buildResolveRequest(fixture, "reject", "", "", null), { action: "reject" });
  const failed = { ...fixture, is_failed_job: true, field_name: null, entity: null, options: [] };
  assert.deepEqual(decisions.buildResolveRequest(failed, "dismiss", "", "", null), { action: "dismiss" });
  for (const action of ["option", "custom", "reject"]) assert.throws(() => decisions.buildResolveRequest(failed, action, "11", "value", null), /only be dismissed/);
  assert.throws(() => decisions.buildResolveRequest(fixture, "dismiss", "", "", null), /supported/);
  assert.throws(() => decisions.buildResolveRequest(fixture, "option", "999", "", null), /Select one/);
  assert.throws(() => decisions.buildResolveRequest(fixture, "custom", "", " ", null), /correction/);
  assert.throws(() => decisions.buildResolveRequest(fixture, "custom", "", "x".repeat(5001), null), /correction/);
  assert.throws(() => decisions.buildResolveRequest({ ...fixture, resolved: true }, "reject", "", "", null), /already been resolved/);
});

test("unknown skills support approval/mapping and reject blank or inappropriate mappings", () => {
  const skill = { ...fixture, entity: "skills[2]", field_name: "name", reasons: ["unknown_skill"] };
  assert.deepEqual(decisions.buildResolveRequest(skill, "option", "11", "", null), { action: "option", option_id: 11 });
  assert.deepEqual(decisions.buildResolveRequest(skill, "option", "11", "", " PostgreSQL "), { action: "option", option_id: 11, map_to_skill: "PostgreSQL" });
  assert.deepEqual(decisions.buildResolveRequest(skill, "custom", "", "React", "React"), { action: "custom", value: "React", map_to_skill: "React" });
  assert.throws(() => decisions.buildResolveRequest(skill, "option", "11", "", ""), /standard skill/);
  assert.throws(() => decisions.buildResolveRequest(fixture, "option", "11", "", "React"), /only available/);
  assert.throws(() => decisions.buildResolveRequest(skill, "custom", "", "x".repeat(101), null), /Skill names/);
});

test("custom validation supplies backend-compatible format hints without inventing catalogues", () => {
  assert.throws(() => decisions.buildResolveRequest({ ...fixture, field_name: "email" }, "custom", "", "bad", null), /email/);
  assert.throws(() => decisions.buildResolveRequest({ ...fixture, field_name: "proficiency" }, "custom", "", "expert", null), /native/);
  assert.throws(() => decisions.buildResolveRequest({ ...fixture, field_name: "is_current" }, "custom", "", "maybe", null), /true or false/);
  assert.match(decisions.correctionHint({ ...fixture, field_name: "end_date" }), /current/);
  assert.match(decisions.correctionHint({ ...fixture, field_name: "country" }), /supported/);
});

test("resolve posts only actual request fields and invalidates queue data after success", async () => {
  session.setAccessToken("staff-token");
  let changes = 0;
  const before = review.getReviewRevision();
  const unsubscribe = review.subscribeReviewChanges(() => changes++);
  for (const body of [{ action: "option", option_id: 11 }, { action: "custom", value: "Dubai" }, { action: "reject" }, { action: "dismiss" }, { action: "option", option_id: 11, map_to_skill: "React" }]) {
    globalThis.fetch = async (url, init) => {
      assert.equal(url, "/api/v1/review/items/42/resolve");
      assert.equal(init.method, "POST");
      assert.equal(init.headers.get("Authorization"), "Bearer staff-token");
      assert.equal(init.headers.get("Content-Type"), "application/json");
      assert.deepEqual(JSON.parse(init.body), body);
      return json({ ...fixture, resolved: true, resolution: body.action === "dismiss" ? "dismissed" : "option" });
    };
    assert.equal((await review.resolveReviewItem(42, body)).resolved, true);
  }
  assert.equal(changes, 5);
  assert.equal(review.getReviewRevision(), before + 5);
  unsubscribe();
});

test("clarification returns the recorded waiting state and suggested text without an email claim", async () => {
  session.setAccessToken("staff-token");
  globalThis.fetch = async (url, init) => {
    assert.equal(url, "/api/v1/review/items/42/request-candidate");
    assert.equal(init.method, "POST");
    assert.equal(init.body, undefined);
    return json({ item: { ...fixture, assigned_to_candidate: true }, candidate_email: fixture.candidate_email, suggested_message: "Please confirm your city." });
  };
  const result = await review.requestCandidateClarification(42);
  assert.equal(result.item.assigned_to_candidate, true);
  assert.equal(result.suggested_message, "Please confirm your city.");
  assert.equal(result.email_sent, undefined);
});

test("mutation errors preserve 401/403/409/422 semantics and never expose provider payloads", async () => {
  for (const status of [403, 404, 409, 422, 500]) {
    session.setAccessToken("staff-token");
    const before = review.getReviewRevision();
    globalThis.fetch = async () => json({ detail: "SECRET_PROVIDER_PAYLOAD" }, status);
    await assert.rejects(review.resolveReviewItem(42, { action: "reject" }), error => error.status === status && !error.message.includes("SECRET"));
    assert.equal(review.getReviewRevision(), before);
    assert.equal(session.getAccessToken(), "staff-token");
  }
  globalThis.fetch = async () => json({}, 401);
  await assert.rejects(review.resolveReviewItem(42, { action: "reject" }), error => error.status === 401);
  assert.equal(session.getAccessToken(), null);
});

test("known failure payloads produce safe summaries, including rendered queue and details", () => {
  for (const [message, expected] of [["API_KEY_INVALID SECRET_PROVIDER_PAYLOAD", /invalid API configuration/], ["RESOURCE_EXHAUSTED SECRET_PROVIDER_PAYLOAD", /usage limit/], ["PERMISSION_DENIED SECRET_PROVIDER_PAYLOAD", /access the configured service/], ["NOT_FOUND SECRET_PROVIDER_PAYLOAD", /model is unavailable/], ["timed out SECRET_PROVIDER_PAYLOAD", /temporarily unavailable/], ["SECRET_PROVIDER_PAYLOAD", /could not complete/]]) {
    const failed = { ...fixture, is_failed_job: true, field_name: null, entity: null, reasons: ["llm_failed"], message, options: [] };
    const summary = decisions.safeReviewContext(failed);
    assert.match(summary, expected);
    assert.doesNotMatch(summary, /SECRET_PROVIDER_PAYLOAD|API_KEY_INVALID/);
    remoteState = { loading: false, data: failed };
    assert.doesNotMatch(page(Details, "/reviewer/reviews/42"), /SECRET_PROVIDER_PAYLOAD|API_KEY_INVALID/);
    remoteState = { loading: false, data: { total: 1, items: [failed] } };
    assert.doesNotMatch(page(Queue), /SECRET_PROVIDER_PAYLOAD|API_KEY_INVALID/);
  }
});

test("action UI offers dismissal only for failed jobs and no edits after resolution", () => {
  remoteState = { loading: false, data: { ...fixture, is_failed_job: true, field_name: null, entity: null, options: [] } };
  let html = page(Details, "/reviewer/reviews/42");
  assert.match(html, /Dismiss failed document/);
  assert.doesNotMatch(html, /Enter a custom correction|Reject this field|Select an existing alternative/);
  assert.match(html, /CVerge does not send email/);
  remoteState = { loading: false, data: { ...fixture, resolved: true } };
  html = page(Details, "/reviewer/reviews/42");
  assert.doesNotMatch(html, /Review and confirm|Prepare clarification request/);
});

test("clarification draft validates the address and encodes message content", () => {
  const draft = decisions.clarificationMailto("candidate@example.invalid", "Please confirm city & country.\nThank you.");
  assert.ok(draft.startsWith("mailto:candidate%40example.invalid?"));
  assert.ok(draft.includes("city%20%26%20country"));
  assert.equal(decisions.clarificationMailto("bad address", "hello"), null);
  assert.equal(decisions.clarificationMailto("candidate@example.invalid\nBcc:someone", "hello"), null);
});

const adminFiles = load("services/adminFileService");
const processing = load("utils/processing");
const AdminDocuments = load("pages/staff/AdminDocumentsPage").default;
const AdminDocument = load("pages/staff/AdminDocumentPage").default;
const StaffLayout = load("components/layout/StaffLayout").default;
const adminFixture = {
  file_id: 201, profile_id: 8, user_id: 9, candidate_name: "Admin Test Candidate",
  original_name: "review-resume.pdf", file_type: "pdf", status: "failed",
  extraction_method: "text", ocr_confidence: null, error_message: "API_KEY_INVALID SECRET_PROVIDER_PAYLOAD",
  uploaded_at: "2026-11-15T10:00:00Z", finished_at: "2026-11-15T10:01:00Z",
  attempts: 1, open_reviews: 2,
  attempts_detail: [{ attempt_number: 1, trigger: "first_run", outcome: "error", provider: "gemini",
    model_version: "test-model", error_message: "API_KEY_INVALID SECRET_PROVIDER_PAYLOAD",
    started_at: "2026-11-15T10:00:00Z", finished_at: "2026-11-15T10:01:00Z" }],
};
function adminPage(Component, path = "/admin/documents") {
  return render(React.createElement(router.Routes, null,
    React.createElement(router.Route, { path: "/admin/documents" },
      React.createElement(router.Route, { index: true, element: React.createElement(Component) }),
      React.createElement(router.Route, { path: ":fileId", element: React.createElement(Component) }))), path);
}

test("admin document deep links are preserved only for administrators", () => {
  for (const path of ["/admin/documents", "/admin/documents?status=failed&page=2", "/admin/documents/201?profile_id=8"]) {
    assert.equal(auth.loginDestination("administrator", path), path);
    assert.equal(access.safeLoginReturnPath(path), path);
    assert.equal(auth.loginDestination("reviewer", path), "/reviewer/reviews");
    assert.equal(auth.loginDestination("candidate", path), "/workspace");
  }
  assert.equal(auth.loginDestination("administrator", "//evil.example/admin/documents"), "/admin/reviews");
});

test("staff navigation exposes document monitoring only to verified administrators", () => {
  sessionState = { token: "token", user: { ...account, role: "administrator" } };
  assert.match(render(React.createElement(StaffLayout, { role: "administrator" }), "/admin/documents"), /href="\/admin\/documents"/);
  sessionState = { token: "token", user: account };
  assert.doesNotMatch(render(React.createElement(StaffLayout, { role: "reviewer" })), /href="\/admin\/documents"/);
  assert.match(render(React.createElement(StaffLayout, { role: "administrator" })), /Access denied/);
});

test("admin document list uses only supported filters, pagination and bearer authentication", async () => {
  session.setAccessToken("admin-test-token");
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push(url);
    assert.equal(init.headers.get("Authorization"), "Bearer admin-test-token");
    assert.equal(init.method, undefined);
    return json({ total: 1, limit: 20, offset: 20, items: [adminFixture] });
  };
  const result = await adminFiles.getAdminFiles({ status: "failed", profileId: 8, limit: 20, offset: 20 });
  assert.equal(result.items[0].candidate_name, "Admin Test Candidate");
  const query = new URL(calls[0], "https://example.invalid").searchParams;
  assert.equal(query.get("status"), "failed");
  assert.equal(query.get("profile_id"), "8");
  assert.equal(query.get("offset"), "20");
  await adminFiles.getAdminFiles();
  assert.equal(new URL(calls[1], "https://example.invalid").searchParams.has("status"), false);
  assert.ok(calls.every(url => url.startsWith("/api/v1/admin/files?")));
});

test("admin file detail preserves the actual attempt contract and rejects invalid identifiers", async () => {
  session.setAccessToken("admin-test-token");
  globalThis.fetch = async (url, init) => {
    assert.equal(url, "/api/v1/admin/files/201");
    assert.equal(init.method, undefined);
    return json(adminFixture);
  };
  assert.deepEqual(await adminFiles.getAdminFile(201), adminFixture);
  globalThis.fetch = async () => { throw Error("Invalid requests must not fetch"); };
  for (const id of [0, -1, NaN, 1.2, Number.MAX_SAFE_INTEGER + 1]) await assert.rejects(adminFiles.getAdminFile(id), /invalid/);
  for (const filters of [{ status: "queued" }, { limit: 101 }, { offset: -1 }, { profileId: 0 }]) await assert.rejects(adminFiles.getAdminFiles(filters), /valid document filters/);
  assert.deepEqual(processing.parseAdminDocumentQuery(new URLSearchParams("status=queued&page=-1&profile_id=bad")), { status: undefined, page: 1, profileId: undefined });
});

test("rerun sends the supported POST once, keeps the reported status and waits for observed progress", async () => {
  session.setAccessToken("admin-rerun-test");
  const file = { ...adminFixture, file_id: 301 };
  let release, calls = 0;
  globalThis.fetch = async (url, init) => {
    calls++;
    assert.equal(url, "/api/v1/admin/files/301/rerun");
    assert.equal(init.method, "POST");
    assert.equal(init.body, undefined);
    return new Promise(ok => { release = () => ok(json({ file_id: 301, status: "failed", message: "Re-run queued; follow it with GET /admin/files/{file_id}" }, 202)); });
  };
  const pending = adminFiles.rerunAdminFile(file);
  assert.equal(adminFiles.rerunTracking(301), "submitting");
  await assert.rejects(adminFiles.rerunAdminFile(file), error => error.status === 409);
  assert.equal(calls, 1);
  release();
  const result = await pending;
  assert.equal(result.status, "failed", "acceptance must not fabricate a processing status");
  assert.equal(adminFiles.rerunTracking(301), "accepted");
  await assert.rejects(adminFiles.rerunAdminFile(file), error => error.status === 409);
  globalThis.fetch = async () => json({ ...file, status: "processing" });
  await adminFiles.getAdminFile(301);
  assert.equal(adminFiles.rerunTracking(301), "accepted");
  globalThis.fetch = async () => json({ ...file, status: "failed", attempts: 2 });
  await adminFiles.getAdminFile(301);
  assert.equal(adminFiles.rerunTracking(301), null);
});

test("processing documents cannot be rerun and uncertain request outcomes prevent automatic retries", async () => {
  session.setAccessToken("admin-uncertain-test");
  globalThis.fetch = async () => { throw Error("No automatic retry"); };
  await assert.rejects(adminFiles.rerunAdminFile({ ...adminFixture, status: "processing" }), error => error.status === 409);
  const file = { ...adminFixture, file_id: 302 };
  globalThis.fetch = async () => json({ detail: "SECRET_PROVIDER_PAYLOAD" }, 500);
  await assert.rejects(adminFiles.rerunAdminFile(file), error => error.status === 500 && !error.message.includes("SECRET"));
  assert.equal(adminFiles.rerunTracking(302), "uncertain");
  let calls = 0;
  globalThis.fetch = async () => { calls++; return json(file); };
  await assert.rejects(adminFiles.rerunAdminFile(file), error => error.status === 409);
  assert.equal(calls, 0);
  session.setAccessToken("different-session");
  assert.equal(adminFiles.rerunTracking(302), null);
});

test("admin errors keep 401/403/404/409/422 semantics without disclosing response bodies", async () => {
  for (const status of [403, 404, 409, 422, 500]) {
    session.setAccessToken("admin-errors-test");
    globalThis.fetch = async () => json({ detail: "SECRET_PROVIDER_PAYLOAD" }, status);
    await assert.rejects(adminFiles.getAdminFile(201), error => error.status === status && !error.message.includes("SECRET"));
    await assert.rejects(adminFiles.rerunAdminFile({ ...adminFixture, file_id: 400 + status }), error => error.status === status && !error.message.includes("SECRET"));
    assert.equal(session.getAccessToken(), "admin-errors-test");
  }
  globalThis.fetch = async () => json({}, 401);
  await assert.rejects(adminFiles.getAdminFile(201), error => error.status === 401);
  assert.equal(session.getAccessToken(), null);
});

test("admin list renders supplied documents, filters and pagination without raw processing errors", () => {
  remoteState = { loading: false, data: { total: 21, limit: 20, offset: 20, items: [adminFixture] } };
  const html = adminPage(AdminDocuments, "/admin/documents?status=failed&profile_id=8&page=2");
  for (const value of ["Admin Test Candidate", "review-resume.pdf", "Page 2 of 2", "invalid API configuration"]) assert.ok(html.includes(value), value);
  assert.match(html, /value="failed" selected/);
  assert.ok(html.includes('href="/admin/documents/201?status=failed&amp;profile_id=8&amp;page=2"'));
  assert.doesNotMatch(html, /SECRET_PROVIDER_PAYLOAD|API_KEY_INVALID/);
});

test("admin detail shows recorded attempts and honest history limitations, with confirmed rerun controls", () => {
  session.setAccessToken("admin-render-test");
  remoteState = { loading: false, data: adminFixture };
  const html = adminPage(AdminDocument, "/admin/documents/201?status=failed&page=2");
  for (const value of ["Initial run", "Processing error", "test-model", "invalid API configuration", "Reprocess document", "A full document status-change history is not available"]) assert.ok(html.includes(value), value);
  assert.ok(html.includes('href="/admin/documents?status=failed&amp;page=2"'));
  assert.doesNotMatch(html, /SECRET_PROVIDER_PAYLOAD|API_KEY_INVALID|Download original/);
  assert.match(html, /<dialog/);
  assert.doesNotMatch(html, /<dialog[^>]* open/);
  remoteState = { loading: false, data: { ...adminFixture, status: "processing" } };
  assert.match(adminPage(AdminDocument, "/admin/documents/201"), /<button[^>]*disabled=""[^>]*>Reprocess document/);
});

test("monitoring screens distinguish loading, empty, failure and missing attempts", () => {
  remoteState = { loading: true };
  assert.match(adminPage(AdminDocuments), /Loading admin documents/);
  remoteState = { loading: false, data: { total: 0, items: [] } };
  assert.match(adminPage(AdminDocuments), /No documents found/);
  remoteState = { loading: false, error: "Only administrators can access document processing controls.", data: adminFixture };
  assert.match(adminPage(AdminDocument, "/admin/documents/201"), /role="alert"/);
  assert.doesNotMatch(adminPage(AdminDocument, "/admin/documents/201"), /Reprocess document/);
  remoteState = { loading: false, data: { ...adminFixture, attempts_detail: [] } };
  assert.match(adminPage(AdminDocument, "/admin/documents/201"), /No recorded attempts yet/);
});

test("processing errors always use fixed explanations, including malformed source and validation failures", () => {
  for (const message of ["API_KEY_INVALID SECRET", "RESOURCE_EXHAUSTED SECRET", "PERMISSION_DENIED SECRET", "NOT_FOUND SECRET", "timeout SECRET", "Text extraction failed SECRET", "schema validation SECRET", "SECRET arbitrary stack trace"]) {
    assert.doesNotMatch(processing.safeProcessingError(message), /SECRET|stack trace|API_KEY_INVALID/);
  }
});

const workspace = load("services/adminWorkspaceService");
const candidateUtils = load("utils/adminCandidates");
const Dashboard = load("pages/staff/AdminDashboardPage").default;
const CandidateDirectoryPage = load("pages/staff/AdminCandidatesPage").default;
const CandidateProfilePage = load("pages/staff/AdminCandidatePage").default;
const ProfileContent = load("components/admin/AdminProfileContent").default;
const ProfileHistory = load("components/admin/AdminProfileHistory").default;
const dashboardFixture = {
  candidates: 17, files_total: 125, files_by_status: { uploaded: 25, processing: 25, done: 25, needs_review: 25, failed: 25 },
  llm_attempts: 50, llm_failed_attempts: 10, valid_on_first_try_rate: 0.8, files_that_hit_3_attempts: 2,
  field_records: 100, average_confidence: null, share_of_fields_sent_to_review: 0.2,
  open_reviews: 8, resolved_reviews: 3, reviews_with_typed_correction: 1,
};
const profileFixture = {
  profile_id: 8, candidate_name: "Profile Candidate", candidate_email: "profile@example.invalid", updated_at: null, open_reviews: 2,
  files: [adminFixture],
  profile: {
    rule_version: "1.0", personal_info: { first_name: "Profile", last_name: "Candidate", email: "extracted@example.invalid", phone: "+12345", city: "Amman", country: { name: "Jordan", code: "JO" }, title: "Engineer", summary: "Actual professional summary", field_ids: { city: 9001 } },
    experience: [{ company: "Example Company", title: "Developer", start_date: { value: "2022", precision: "year" }, end_date: null, employment_status: "current", description: "Built services", field_ids: [9002] }],
    education: [{ institution: "Example University", degree: "BSc", field: "Computing", field_ids: [9003] }],
    skills: [{ name: "React", level: 4, verified: true, sources: ["201"], field_ids: [9004] }],
    certifications: [{ name: "Certificate", issuer: "Issuer", issue_date: { value: "2023-06", precision: "month" }, url: "https://example.invalid/cert", field_ids: [9005] }],
    projects: [{ name: "Actual Project", description: "A source-backed project", tech_stack: ["TypeScript"], url: "https://example.invalid/project", field_ids: [9006] }],
    languages: [{ name: "Arabic", proficiency: "native", field_ids: [9007] }],
    links: [{ type: "github", url: "javascript:alert(1)", field_ids: [9008] }],
  },
};
const historyFixture = { total: 21, limit: 20, offset: 20, items: [{ change_id: 42, field_name: "city", old_value: "<script>old()</script>", new_value: "Amman", changed_by: "Rania", reason: "review_decision", file_id: 201, changed_at: "2026-11-15T10:00:00Z" }] };
function workspacePage(Component, path = "/admin/dashboard") {
  return render(React.createElement(router.Routes, null,
    React.createElement(router.Route, { path: "/admin/dashboard", element: React.createElement(Component) }),
    React.createElement(router.Route, { path: "/admin/candidates", element: React.createElement(Component) }),
    React.createElement(router.Route, { path: "/admin/candidates/:profileId", element: React.createElement(Component) })), path);
}

test("dashboard reads real aggregates directly without deriving totals from a document page", async () => {
  session.setAccessToken("dashboard-test");
  const calls = [];
  globalThis.fetch = async (url, init) => { calls.push(url); assert.equal(init.method, undefined); assert.equal(init.headers.get("Authorization"), "Bearer dashboard-test"); return json(dashboardFixture); };
  assert.deepEqual(await workspace.getAdminDashboard(), dashboardFixture);
  assert.deepEqual(calls, ["/api/v1/admin/dashboard"]);
  assert.equal(candidateUtils.dashboardRate(null), "Not available");
  assert.equal(candidateUtils.dashboardRate(0), "0.0%");
});
test("incomplete or inconsistent aggregate responses cannot produce misleading dashboard totals", async () => {
  for (const response of [{}, { ...dashboardFixture, files_total: 126 }, { ...dashboardFixture, average_confidence: undefined }, { ...dashboardFixture, candidates: -1 }]) {
    globalThis.fetch = async () => json(response);
    await assert.rejects(workspace.getAdminDashboard(), error => /incomplete|inconsistent/.test(error.message));
  }
});
test("candidate directory fetches every metadata page and groups actual profile references", async () => {
  session.setAccessToken("directory-test");
  const files = Array.from({ length: 101 }, (_, index) => ({ ...adminFixture, file_id: 1000 + index, profile_id: index % 21 + 1, user_id: index % 21 + 101, candidate_name: "Candidate " + (index % 21 + 1) }));
  const offsets = [];
  globalThis.fetch = async url => {
    assert.ok(url.startsWith("/api/v1/admin/files?"));
    const params = new URL(url, "https://example.invalid").searchParams;
    assert.equal(params.get("limit"), "100"); assert.equal(params.has("status"), false);
    const offset = Number(params.get("offset")); offsets.push(offset);
    return json({ total: files.length, limit: 100, offset, items: files.slice(offset, offset + 100) });
  };
  const result = await workspace.getCandidateDirectory();
  assert.deepEqual(offsets, [0, 100]);
  assert.equal(result.documentTotal, 101);
  assert.equal(result.entries.length, 21);
  assert.equal(result.entries[0].documents, 5);
  assert.equal(result.entries[0].statuses.failed, 5);
  assert.equal(result.entries[0].openDocumentReviews, 10);
  assert.equal(candidateUtils.filterCandidateDirectory(result.entries, "Candidate 21").length, 1);
  assert.equal(candidateUtils.filterCandidateDirectory(result.entries, "", "done").length, 0);
});
test("directory rejects changing, duplicate or incomplete pagination instead of showing a partial list", async () => {
  const first = Array.from({ length: 100 }, (_, index) => ({ ...adminFixture, file_id: 1000 + index }));
  for (const failure of ["changed", "duplicate", "missing"]) {
    globalThis.fetch = async url => {
      const offset = Number(new URL(url, "https://example.invalid").searchParams.get("offset"));
      if (offset === 0) return json({ total: 101, limit: 100, offset, items: first });
      return json({ total: failure === "changed" ? 102 : 101, limit: 100, offset, items: failure === "missing" ? [] : [{ ...adminFixture, file_id: failure === "duplicate" ? 1000 : 2000 }] });
    };
    await assert.rejects(workspace.getCandidateDirectory());
  }
  globalThis.fetch = async () => json({ total: 0, limit: 100, offset: 0, items: [] });
  assert.deepEqual(await workspace.getCandidateDirectory(), { entries: [], documentTotal: 0 });
});
test("admin candidate and history services match existing read-only APIs and validate IDs/pages", async () => {
  const calls = [];
  globalThis.fetch = async (url, init) => { calls.push(url); assert.equal(init.method, undefined); return json(url.includes("/history?") ? historyFixture : profileFixture); };
  assert.deepEqual(await workspace.getAdminCandidate(8), profileFixture);
  assert.deepEqual(await workspace.getAdminProfileHistory(8, 20, 20), historyFixture);
  assert.deepEqual(calls, ["/api/v1/profile/8", "/api/v1/profile/8/history?limit=20&offset=20"]);
  for (const id of [0, -1, 1.2, NaN]) assert.throws(() => workspace.getAdminCandidate(id), /invalid/);
  assert.throws(() => workspace.getAdminProfileHistory(8, 201, 0), /valid history/);
});
test("admin profile skill sources use authorized file lookups and never mistake field IDs for files", async () => {
  const calls = [];
  globalThis.fetch = async url => { calls.push(url); return json({ ...adminFixture, file_id: Number(url.split("/").at(-1)), profile_id: url.endsWith("/999") ? 9 : 8 }); };
  const result = await workspace.getAdminSkillDocuments(8, ["201", "777", "999", "resume.pdf"], [adminFixture]);
  assert.deepEqual(result.documents.map(file => file.file_id), [201, 777]);
  assert.equal(result.unavailableCount, 2);
  assert.deepEqual(calls, ["/api/v1/admin/files/777", "/api/v1/admin/files/999"]);
});
test("new admin safe returns and sidebar navigation remain restricted to administrators", () => {
  for (const path of ["/admin/dashboard", "/admin/dashboard?refresh=1", "/admin/candidates", "/admin/candidates/8?history_page=2"]) {
    assert.equal(auth.loginDestination("administrator", path), path);
    assert.equal(access.safeLoginReturnPath(path), path);
    assert.equal(auth.loginDestination("reviewer", path), "/reviewer/reviews");
    assert.equal(auth.loginDestination("candidate", path), "/workspace");
  }
  assert.equal(access.safeLoginReturnPath("/admin/dashboard/8"), undefined);
  sessionState = { token: "token", user: { ...account, role: "administrator" } };
  let html = render(React.createElement(StaffLayout, { role: "administrator" }));
  assert.ok(html.includes('href="/admin/dashboard"')); assert.ok(html.includes('href="/admin/candidates"'));
  sessionState = { token: "token", user: account };
  html = render(React.createElement(StaffLayout, { role: "reviewer" }));
  assert.doesNotMatch(html, /href="\/admin\//);
});
test("dashboard cards distinguish registered accounts from uploaded-document candidates and unavailable rates", () => {
  remoteState = { loading: false, data: dashboardFixture };
  const html = workspacePage(Dashboard);
  for (const value of ["Registered candidate accounts", "17", "125", "Includes accounts without uploaded documents", "Not available", "80.0%", "not the share of reviewed values changed"]) assert.ok(html.includes(value), value);
  assert.ok(html.includes('href="/admin/candidates"'));
  assert.ok(html.includes('href="/admin/documents?status=failed"'));
});
test("directory UI labels limited coverage, offers local filters, and links profiles/documents/reviews", () => {
  remoteState = { loading: false, data: { documentTotal: 125, entries: [{ profileId: 8, userId: 9, name: "Profile Candidate", documents: 125, openDocumentReviews: 2, statuses: { uploaded: 0, processing: 0, done: 0, failed: 125, needs_review: 0 } }] } };
  const html = workspacePage(CandidateDirectoryPage, "/admin/candidates?q=Profile&status=failed");
  for (const value of ["Candidates with uploaded documents", "accounts without uploads", "apply locally", "Profile Candidate"]) assert.ok(html.includes(value), value);
  assert.ok(html.includes('href="/admin/candidates/8?q=Profile&amp;status=failed"'));
  assert.ok(html.includes('href="/admin/documents?profile_id=8"'));
  assert.ok(html.includes('href="/admin/reviews?profile_id=8"'));
});
test("admin profile content shows all actual professional sections, preserves dates and escapes unsafe links", () => {
  const html = render(React.createElement(ProfileContent, { data: profileFixture }));
  for (const value of ["Actual professional summary", "Example Company", "Example University", "2022", "Present", "Actual Project", "TypeScript", "Certificate", "Arabic", "Level: 4/5", "Sources for React", "Field-record references"]) assert.ok(html.includes(value), value);
  assert.doesNotMatch(html, /href="javascript:|href="\/files\/9004|href="\/profile\/me/);
  assert.ok(html.includes('href="/admin/documents/201"'));
  assert.ok(html.includes("up to the backend limit of 100"));
  const pending = render(React.createElement(ProfileContent, { data: { ...profileFixture, profile: null } }));
  assert.match(pending, /No extracted profile is available yet/);
});
test("history renders actual before/after/cause/source references and backend pagination", () => {
  remoteState = { loading: false, data: historyFixture };
  const html = render(React.createElement(ProfileHistory, { profileId: 8 }), "/admin/candidates/8?history_page=2");
  for (const value of ["Before", "After", "Amman", "Rania", "Review decision", "21 recorded changes", "Page 2 of 2", "coverage of every generated profile field is not guaranteed"]) assert.ok(html.includes(value), value);
  assert.ok(html.includes("&lt;script&gt;old()&lt;/script&gt;"));
  assert.doesNotMatch(html, /<script>/);
  assert.ok(html.includes('href="/admin/documents/201"'));
});
test("dashboard, directory and profile distinguish loading, empty and API-error states", () => {
  remoteState = { loading: true };
  assert.match(workspacePage(Dashboard), /Loading admin dashboard/);
  assert.match(workspacePage(CandidateDirectoryPage), /Loading the candidate directory/);
  assert.match(workspacePage(CandidateProfilePage, "/admin/candidates/8"), /Loading candidate profile/);
  remoteState = { loading: false, data: { entries: [], documentTotal: 0 } };
  assert.match(workspacePage(CandidateDirectoryPage), /No candidates found in this directory/);
  remoteState = { loading: false, error: "Only administrators can access this information." };
  assert.match(workspacePage(Dashboard), /role="alert"/);
  assert.match(workspacePage(CandidateProfilePage, "/admin/candidates/8"), /role="alert"/);
  assert.doesNotMatch(workspacePage(CandidateProfilePage, "/admin/candidates/8"), /Recorded profile history/);
});
test("new read APIs preserve 401/403/404/422/server error behavior without displaying response details", async () => {
  for (const status of [403, 404, 422, 500]) {
    session.setAccessToken("workspace-errors");
    globalThis.fetch = async () => json({ detail: "SECRET_SERVER_PAYLOAD" }, status);
    await assert.rejects(workspace.getAdminDashboard(), error => error.status === status && !error.message.includes("SECRET"));
    await assert.rejects(workspace.getAdminCandidate(8), error => error.status === status && !error.message.includes("SECRET"));
    await assert.rejects(workspace.getAdminProfileHistory(8), error => error.status === status && !error.message.includes("SECRET"));
    assert.equal(session.getAccessToken(), "workspace-errors");
  }
  globalThis.fetch = async () => json({}, 401);
  await assert.rejects(workspace.getAdminCandidate(8), error => error.status === 401);
  assert.equal(session.getAccessToken(), null);
});

test("directory pagination stops if the authenticated session changes during loading", async () => {
  session.setAccessToken("initial-admin-session");
  const first = Array.from({ length: 100 }, (_, index) => ({ ...adminFixture, file_id: 3000 + index }));
  let calls = 0;
  globalThis.fetch = async () => { calls++; session.setAccessToken("different-session"); return json({ total: 101, limit: 100, offset: 0, items: first }); };
  await assert.rejects(workspace.getCandidateDirectory(), /account changed/);
  assert.equal(calls, 1, "no follow-up admin requests use the replacement session");
});

const staffCreation = load("services/staffService");
const staffForm = load("utils/staffAccounts");
const StaffManagement = load("pages/staff/StaffManagementPage").default;
const staffRequest = { name: "New Reviewer", email: "new-reviewer@example.invalid", password: "test-staff-password", role: "reviewer" };
const staffResponse = { user_id: 501, name: "Stored Reviewer", email: "stored-reviewer@example.invalid", role: "reviewer" };

test("staff creation validation matches supported fields, roles and character limits", () => {
  assert.deepEqual(staffForm.validateStaffForm(staffRequest), {});
  for (const name of [" ", "A", "a".repeat(256)]) assert.ok(staffForm.validateStaffForm({ ...staffRequest, name }).name);
  for (const password of ["", "1234567", "x".repeat(129)]) assert.ok(staffForm.validateStaffForm({ ...staffRequest, password }).password);
  assert.ok(staffForm.validateStaffForm({ ...staffRequest, email: "bad address" }).email);
  assert.ok(staffForm.validateStaffForm({ ...staffRequest, role: "candidate" }).role);
  assert.ok(staffForm.validateStaffForm({ ...staffRequest, role: "owner" }).role);
  assert.deepEqual(staffForm.validateStaffForm({ ...staffRequest, name: "🙂🙂", password: "🙂".repeat(128) }), {});
  assert.ok(staffForm.validateStaffForm({ ...staffRequest, password: "🙂".repeat(7) }).password);
  assert.deepEqual(staffForm.prepareStaffRequest({ ...staffRequest, name: "  Reviewer Name  ", email: " NEW@example.invalid ", password: " 123456 " }), { name: "Reviewer Name", email: "new@example.invalid", password: " 123456 ", role: "reviewer" });
});

test("staff service uses the authenticated admin POST and returns only actual account confirmation fields", async () => {
  session.setAccessToken("staff-management-admin");
  const calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push(url);
    assert.equal(url, "/api/v1/admin/users");
    assert.equal(init.method, "POST");
    assert.equal(init.headers.get("Authorization"), "Bearer staff-management-admin");
    assert.equal(init.headers.get("Content-Type"), "application/json");
    assert.deepEqual(JSON.parse(init.body), staffRequest);
    return json({ ...staffResponse, password_hash: "SECRET_MUST_NOT_BE_EXPOSED" }, 201);
  };
  assert.deepEqual(await staffCreation.createStaffAccount(staffRequest), staffResponse);
  assert.deepEqual(calls, ["/api/v1/admin/users"]);
  assert.equal(session.getAccessToken(), "staff-management-admin", "creating staff must not replace the current admin session");
  globalThis.fetch = async () => json({ ...staffResponse, user_id: 502, role: "administrator" }, 201);
  assert.equal((await staffCreation.createStaffAccount({ ...staffRequest, role: "administrator" })).role, "administrator");
});

test("staff creation rejects invalid input and concurrent duplicate submissions before another POST", async () => {
  let count = 0, release;
  session.setAccessToken("staff-management-duplicates");
  globalThis.fetch = async () => { count++; return new Promise(ok => { release = () => ok(json(staffResponse, 201)); }); };
  await assert.rejects(staffCreation.createStaffAccount({ ...staffRequest, role: "candidate" }), /staff role/);
  assert.equal(count, 0);
  const first = staffCreation.createStaffAccount(staffRequest);
  await assert.rejects(staffCreation.createStaffAccount({ ...staffRequest, email: staffRequest.email.toUpperCase() }), error => error.status === 409 && /in progress/.test(error.message));
  assert.equal(count, 1);
  release(); await first;
});

test("staff API errors preserve duplicate/validation/permission/session semantics without leaking secrets", async () => {
  for (const status of [403, 404, 409, 422, 429, 500]) {
    session.setAccessToken("staff-management-errors");
    globalThis.fetch = async () => json({ detail: [{ input: { password: "SECRET_PASSWORD" }, msg: "SECRET_PROVIDER_PAYLOAD" }] }, status);
    await assert.rejects(staffCreation.createStaffAccount(staffRequest), error => error.status === status && !error.message.includes("SECRET"));
    assert.equal(session.getAccessToken(), "staff-management-errors");
  }
  globalThis.fetch = async () => json({ detail: "SECRET" }, 401);
  await assert.rejects(staffCreation.createStaffAccount(staffRequest), error => error.status === 401);
  assert.equal(session.getAccessToken(), null);
});

test("network, unreadable and malformed confirmations are uncertain outcomes rather than fabricated successes", async () => {
  session.setAccessToken("staff-management-uncertain");
  for (const response of [null, {}, { ...staffResponse, user_id: 0 }, { ...staffResponse, role: "candidate" }]) {
    globalThis.fetch = async () => json(response, 201);
    await assert.rejects(staffCreation.createStaffAccount(staffRequest), /may have been created/);
  }
  globalThis.fetch = async () => { throw Error("SECRET_NETWORK"); };
  await assert.rejects(staffCreation.createStaffAccount(staffRequest), error => error.status === 0 && /outcome could not be confirmed/.test(error.message) && !error.message.includes("SECRET"));
  globalThis.fetch = async () => new Response("SECRET_BAD_RESPONSE", { status: 201 });
  await assert.rejects(staffCreation.createStaffAccount(staffRequest), /may have been created/);
});

test("staff page exposes no directory or unsupported account management actions and keeps passwords out of confirmation text", () => {
  const html = render(React.createElement(StaffManagement), "/admin/staff");
  for (const text of ["Staff Management", "Existing staff accounts cannot be listed here", "not a staff directory", "Review account creation", "No invitation email", "Reviewer", "Administrator"]) assert.ok(html.includes(text), text);
  assert.match(html, /type="password"/);
  assert.match(html, /autocomplete="new-password"/i);
  assert.match(html, /aria-label="Show password"/);
  assert.doesNotMatch(html, /<dialog[^>]* open|Account created|Send invitation|Reset password|Delete account/);
  assert.doesNotMatch(html, /<option value="candidate"/);
});

test("staff route, safe returns and navigation are administrator-only", () => {
  for (const path of ["/admin/staff", "/admin/staff?from=dashboard#account"]) {
    assert.equal(auth.loginDestination("administrator", path), path);
    assert.equal(access.safeLoginReturnPath(path), path);
    assert.equal(auth.loginDestination("reviewer", path), "/reviewer/reviews");
    assert.equal(auth.loginDestination("candidate", path), "/workspace");
  }
  assert.equal(access.safeLoginReturnPath("/admin/staff/501"), undefined);
  sessionState = { token: "token", user: { ...account, role: "administrator" } };
  assert.ok(render(React.createElement(StaffLayout, { role: "administrator" }), "/admin/staff").includes('href="/admin/staff"'));
  sessionState = { token: "token", user: account };
  assert.doesNotMatch(render(React.createElement(StaffLayout, { role: "reviewer" })), /href="\/admin\/staff"/);
  assert.match(render(React.createElement(Gate, { role: "administrator" }, React.createElement(StaffManagement))), /Access denied/);
});
