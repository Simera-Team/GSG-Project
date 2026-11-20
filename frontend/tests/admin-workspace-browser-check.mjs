/* global process, Buffer */
import assert from "node:assert/strict";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
const origin = process.env.UI_CHECK_URL || "http://127.0.0.1:5174";
const debuggerUrl = process.env.CHROME_DEBUG_URL || "http://127.0.0.1:9223";
const artifacts = resolve(".ui-check"); mkdirSync(artifacts, { recursive: true });
const target = await (await fetch(debuggerUrl + "/json/new?about:blank", { method: "PUT" })).json();
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((ok, bad) => { socket.addEventListener("open", ok, { once: true }); socket.addEventListener("error", bad, { once: true }); });
const pending = new Map(), calls = [], exceptions = [];
let nextId = 0, role = "administrator", errorTarget = "", errorStatus = 0, mode = "normal", delay = 0;
const statuses = ["uploaded", "processing", "done", "needs_review", "failed"];
const files = Array.from({ length: 125 }, (_, index) => ({
  file_id: 201 + index, profile_id: 8 + index % 21, user_id: 108 + index % 21,
  candidate_name: "Workspace Candidate " + (8 + index % 21), original_name: "source-" + (201 + index) + ".pdf", file_type: "pdf",
  status: statuses[index % 5], extraction_method: "text", ocr_confidence: null,
  error_message: index % 5 === 4 ? "API_KEY_INVALID SECRET_PROVIDER_PAYLOAD" : null,
  uploaded_at: "2026-11-15T10:00:00Z", finished_at: "2026-11-15T10:01:00Z", attempts: 1, open_reviews: index % 5 === 3 ? 1 : 0,
}));
const profile = {
  profile_id: 8, candidate_name: "Workspace Candidate 8", candidate_email: "candidate@example.invalid", updated_at: null, open_reviews: 2,
  files: [files[0]],
  profile: {
    rule_version: "1.0",
    personal_info: { first_name: "Workspace", last_name: "Candidate", email: "extracted@example.invalid", phone: "+12345", city: "Amman", country: { name: "Jordan", code: "JO" }, title: "Engineer", summary: "Profile summary from the source documents.", field_ids: { city: 8001 } },
    experience: [{ company: "Example Company", title: "Developer", start_date: { value: "2022", precision: "year" }, end_date: null, employment_status: "current", description: "Built services", field_ids: [8002] }],
    education: [{ institution: "Example University", degree: "BSc", field: "Computing", field_ids: [8003] }],
    skills: [{ name: "React", level: 4, verified: true, sources: ["201", "306", "resume.pdf"], field_ids: [8004] }],
    certifications: [{ name: "Cloud Certificate", issuer: "Issuer", field_ids: [8005] }],
    projects: [{ name: "Actual Project", tech_stack: ["TypeScript"], field_ids: [8006] }],
    languages: [{ name: "Arabic", proficiency: "native", field_ids: [8007] }],
    links: [{ type: "github", url: "javascript:alert(1)", field_ids: [8008] }],
  },
};
const history = Array.from({ length: 21 }, (_, index) => ({ change_id: 100 + index, field_name: "city", old_value: "Dubai", new_value: "Amman", changed_by: "Rania", reason: "review_decision", file_id: 201, changed_at: "2026-11-15T10:00:00Z" }));
const dashboard = { candidates: 30, files_total: 125, files_by_status: { uploaded: 25, processing: 25, done: 25, needs_review: 25, failed: 25 }, llm_attempts: 50, llm_failed_attempts: 10, valid_on_first_try_rate: 0.8, files_that_hit_3_attempts: 2, field_records: 100, average_confidence: null, share_of_fields_sent_to_review: 0.2, open_reviews: 8, resolved_reviews: 3, reviews_with_typed_correction: 1 };
function command(method, params = {}) {
  const id = ++nextId;
  return new Promise((ok, bad) => {
    const timer = setTimeout(() => { pending.delete(id); bad(Error(method + " timed out")); }, 15000);
    pending.set(id, { ok, bad, timer }); socket.send(JSON.stringify({ id, method, params }));
  });
}
socket.addEventListener("message", async event => {
  const message = JSON.parse(event.data);
  if (message.id) {
    const promise = pending.get(message.id); if (!promise) return;
    clearTimeout(promise.timer); pending.delete(message.id);
    if (message.error) promise.bad(Error(JSON.stringify(message.error))); else promise.ok(message.result);
  } else if (message.method === "Runtime.exceptionThrown") exceptions.push(message.params.exceptionDetails.text);
  else if (message.method === "Fetch.requestPaused") {
    const { requestId, request } = message.params, url = new URL(request.url), path = url.pathname;
    calls.push({ path, query: url.search, method: request.method, role });
    let status = 200, body = {};
    try {
      const resource = path.endsWith("/admin/dashboard") ? "dashboard" : path.endsWith("/history") ? "history" : /\/profile\/\d+$/.test(path) ? "profile" : path.endsWith("/admin/files") ? "files" : "";
      if (path.endsWith("/auth/login")) body = { access_token: "workspace-token-" + role, token_type: "bearer" };
      else if (path.endsWith("/auth/me")) body = { user_id: 7, name: "Workspace Staff", email: "staff@example.invalid", role };
      else if (request.method !== "GET") { status = 403; body = { detail: "UNEXPECTED_MUTATION" }; }
      else if (resource && role !== "administrator") { status = 403; body = { detail: "SECRET" }; }
      else if (errorTarget === resource && errorStatus) { status = errorStatus; body = { detail: "SECRET_PROVIDER_PAYLOAD" }; }
      else if (resource === "dashboard") {
        if (delay) await new Promise(ok => setTimeout(ok, delay));
        body = mode === "bad-dashboard" ? { candidates: 30 } : dashboard;
      } else if (resource === "files") {
        const limit = Number(url.searchParams.get("limit")), offset = Number(url.searchParams.get("offset"));
        let values = mode === "empty" ? [] : files;
        if (url.searchParams.get("profile_id")) values = values.filter(file => file.profile_id === Number(url.searchParams.get("profile_id")));
        if (url.searchParams.get("status")) values = values.filter(file => file.status === url.searchParams.get("status"));
        body = { total: mode === "changed" && offset ? values.length + 1 : values.length, limit, offset, items: values.slice(offset, offset + limit) };
      } else if (/\/admin\/files\/\d+$/.test(path)) {
        const file = files.find(file => file.file_id === Number(path.split("/").at(-1)));
        if (!file) { status = 404; body = {}; } else body = { ...file, attempts_detail: [] };
      } else if (resource === "profile") {
        const id = Number(path.split("/").at(-1));
        if (id === 29) body = { ...profile, profile_id: 29, profile: null, files: [], open_reviews: 0 };
        else if (id >= 8 && id <= 28) body = { ...profile, profile_id: id, candidate_name: "Workspace Candidate " + id };
        else { status = 404; body = {}; }
      } else if (resource === "history") {
        const limit = Number(url.searchParams.get("limit")), offset = Number(url.searchParams.get("offset"));
        const values = path.includes("/29/") ? [] : history;
        body = { total: values.length, limit, offset, items: values.slice(offset, offset + limit) };
      } else if (path.endsWith("/review/items")) body = { total: 0, limit: 20, offset: 0, items: [] };
      else if (path.endsWith("/cv/files")) body = { total: 0, limit: 100, offset: 0, items: [] };
      else if (path.endsWith("/profile/me")) { status = 404; body = {}; }
      else { status = 404; body = { detail: "UNEXPECTED_ENDPOINT" }; }
      await command("Fetch.fulfillRequest", { requestId, responseCode: status, responseHeaders: [{ name: "Content-Type", value: "application/json" }], body: Buffer.from(JSON.stringify(body)).toString("base64") });
    } catch (error) { exceptions.push(error.message); }
  }
});
async function evaluate(expression) {
  const response = await command("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
  if (response.exceptionDetails) throw Error(JSON.stringify(response.exceptionDetails));
  return response.result.value;
}
async function until(expression, label) {
  const start = Date.now();
  while (Date.now() - start < 15000) { if (await evaluate("Boolean(" + expression + ")")) return; await new Promise(ok => setTimeout(ok, 80)); }
  throw Error("Timed out: " + label);
}
async function click(selector) { await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`); }
async function navigate(path) { await evaluate(`history.pushState({}, '', ${JSON.stringify(path)});window.dispatchEvent(new PopStateEvent('popstate'))`); }
async function login() {
  await until("!!document.querySelector('#login-email')", "login");
  await evaluate(`{const setter=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;for(const [selector,value] of [['#login-email','staff@example.invalid'],['#login-password','test-password']]){const input=document.querySelector(selector);setter.call(input,value);input.dispatchEvent(new Event('input',{bubbles:true}));}}`);
  await click("button[type=submit]");
}
async function screenshot(name, width) {
  await command("Emulation.setDeviceMetricsOverride", { width, height: 1000, deviceScaleFactor: 1, mobile: width < 600 });
  await evaluate("window.scrollTo(0,0)");
  assert.ok(await evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), name + " no horizontal overflow");
  const result = await command("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  writeFileSync(resolve(artifacts, name), Buffer.from(result.data, "base64"));
}
const restricted = () => calls.filter(call => call.path.includes("/admin/") || /\/profile\/\d+/.test(call.path));
try {
  await command("Page.enable"); await command("Runtime.enable");
  await command("Fetch.enable", { patterns: [{ urlPattern: "*/api/v1/*" }] });
  await command("Page.navigate", { url: origin + "/admin/candidates/8?history_page=2" });
  await until("location.pathname === '/login'", "guest protected profile");
  await login();
  await until("!!document.querySelector('.aw-profile-header') && document.querySelectorAll('.aw-history > li').length === 1", "admin candidate deep link and second history page");
  assert.equal(await evaluate("location.pathname + location.search"), "/admin/candidates/8?history_page=2");
  assert.ok(calls.some(call => call.path.endsWith("/profile/8/history") && call.query.includes("offset=20")));
  assert.ok(await evaluate("document.body.innerText.includes('2022') && document.body.innerText.includes('Present')"));
  assert.equal(await evaluate("document.querySelectorAll('a[href^=\"javascript:\"]').length"), 0);
  await click(".aw-record button[aria-expanded]");
  await until("document.querySelectorAll('.aw-skill-documents a').length === 2", "explicit skill sources including older document");
  assert.ok(calls.some(call => call.path === "/api/v1/admin/files/306"));
  assert.equal(calls.some(call => /\/files\/800[1-8]$/.test(call.path)), false);
  assert.ok(await evaluate("document.querySelector('.aw-skill-documents').textContent.includes('Some source references are unavailable')"));
  await screenshot("admin-candidate-mobile.png", 360);
  await click('a[href="/admin/dashboard"]');
  await until("document.querySelectorAll('.aw-summary .aw-card').length === 4", "dashboard aggregates");
  assert.deepEqual(await evaluate("Array.from(document.querySelectorAll('.aw-card > strong'),node=>node.textContent)"), ["30", "125", "8", "3"]);
  assert.ok(await evaluate("document.body.innerText.includes('Not available') && document.body.innerText.includes('80.0%')"));
  assert.equal(await evaluate("document.querySelector('.ws-nav a.active').getAttribute('href')"), "/admin/dashboard");
  await screenshot("admin-dashboard-desktop.png", 1440); await screenshot("admin-dashboard-tablet.png", 768); await screenshot("admin-dashboard-mobile.png", 360);
  delay = 600; await click(".ws-page-heading button"); await until("!!document.querySelector('.ws-skeleton-list')", "dashboard loading"); await until("!!document.querySelector('.aw-summary')", "dashboard refreshed"); delay = 0;
  for (const code of [403, 500]) {
    errorTarget = "dashboard"; errorStatus = code; await click(".ws-page-heading button");
    await until("!!document.querySelector('[role=alert]') && !document.querySelector('.aw-summary')", "dashboard error " + code);
    assert.equal(await evaluate("document.body.innerText.includes('SECRET')"), false);
  }
  errorStatus = 0; mode = "bad-dashboard"; await click(".ws-page-heading button"); await until("document.body.innerText.includes('response is incomplete')", "incomplete totals rejected");
  mode = "normal"; await click(".ws-page-heading button"); await until("!!document.querySelector('.aw-summary')", "dashboard recovery");
  await click('.aw-quick-links a[href="/admin/candidates"]');
  await until("document.querySelectorAll('.aw-candidate-list > li').length === 20", "complete directory");
  const directoryCalls = calls.filter(call => call.path.endsWith("/admin/files") && call.query.includes("limit=100"));
  assert.ok(directoryCalls.some(call => call.query.includes("offset=100")));
  assert.ok(await evaluate("document.body.innerText.includes('125 uploaded documents') && document.body.innerText.includes('not the registered-account total')"));
  await click(".rq-pagination button:last-child");
  await until("document.querySelectorAll('.aw-candidate-list > li').length === 1 && document.body.innerText.includes('Page 2 of 2')", "local candidate pagination");
  const beforeSearch = calls.filter(call => call.path.endsWith("/admin/files")).length;
  await evaluate("document.querySelector('input[name=q]').value='108';document.querySelector('select[name=status]').value='failed';document.querySelector('.rq-filters').requestSubmit()");
  await until("document.querySelectorAll('.aw-candidate-list > li').length === 1 && document.querySelector('.rq-item-title > a')?.getAttribute('href') === '/admin/candidates/8?q=108&status=failed'", "local directory search");
  assert.equal(calls.filter(call => call.path.endsWith("/admin/files")).length, beforeSearch, "local filters do not refetch every page");
  await click(".rq-item-title > a");
  await until("location.pathname === '/admin/candidates/8' && !!document.querySelector('.aw-profile-header') && document.querySelectorAll('.aw-history > li').length === 20", "candidate profile from directory");
  await click(".aw-history + .rq-pagination button:last-child");
  await until("location.search.includes('history_page=2') && document.querySelectorAll('.aw-history > li').length === 1", "server-side history pagination");
  errorTarget = "history"; errorStatus = 500;
  await click('#candidate-history-heading + button');
  await until("!!document.querySelector('section[aria-labelledby=candidate-history-heading] [role=alert]')", "independent history error");
  assert.ok(await evaluate("!!document.querySelector('.aw-profile-header')"));
  errorStatus = 0; await click('#candidate-history-heading + button'); await until("document.querySelectorAll('.aw-history > li').length === 1", "history recovery");
  await click(".rq-back");
  await until("!!document.querySelector('.aw-candidate-list') && location.search.includes('q=108') && !location.search.includes('history_page')", "back preserves directory filters");
  mode = "changed"; await click(".ws-page-heading button");
  await until("document.body.innerText.includes('changed while loading') && !document.querySelector('.aw-candidate-list')", "changing directory cannot show partial counts");
  mode = "empty"; await click(".ws-page-heading button");
  await until("document.body.innerText.includes('No candidates found in this directory')", "empty directory");
  mode = "normal"; await click(".ws-page-heading button"); await until("!!document.querySelector('.aw-candidate-list')", "directory recovery");
  await evaluate("document.querySelector('#known-profile-id').value='29';document.querySelector('.aw-profile-lookup').requestSubmit()");
  await until("location.pathname === '/admin/candidates/29' && document.body.innerText.includes('No extracted profile is available yet')", "known empty profile");
  await navigate("/admin/candidates/9999"); await until("document.body.innerText.includes('candidate profile is unavailable')", "missing profile");
  const beforeInvalid = calls.length; await navigate("/admin/candidates/not-an-id"); await until("document.body.innerText.includes('profile reference is invalid')", "invalid profile reference"); assert.equal(calls.length, beforeInvalid);
  await navigate("/admin/candidates/8"); await until("!!document.querySelector('.aw-profile-header')", "profile ready");
  await click('.aw-profile-header a[href="/admin/documents?profile_id=8"]');
  await until("!!document.querySelector('.ad-list') && location.search === '?profile_id=8'", "candidate documents");
  await click(".ad-document-link"); await until("!!document.querySelector('#admin-file-heading')", "document detail");
  await click('a[href="/admin/candidates/8"]'); await until("!!document.querySelector('.aw-profile-header')", "document to candidate");
  await click('.aw-profile-header a[href="/admin/reviews?profile_id=8"]');
  await until("location.pathname === '/admin/reviews' && document.body.innerText.includes('No review items found')", "candidate reviews");
  await navigate("/admin/dashboard"); await until("!!document.querySelector('.aw-summary')", "dashboard ready");
  errorTarget = "dashboard"; errorStatus = 401; await click(".ws-page-heading button");
  await until("location.pathname === '/login' && document.body.innerText.includes('session has expired')", "401 session expiry");
  errorStatus = 0; role = "reviewer"; await login(); await until("location.pathname === '/reviewer/reviews'", "reviewer return restriction");
  let count = restricted().length;
  await navigate("/admin/candidates/8"); await until("document.body.innerText.includes('This workspace is for another role')", "reviewer denied profile");
  assert.equal(restricted().length, count);
  await click(".page-notice-actions button"); await until("location.pathname === '/login'", "switch role");
  role = "candidate"; await login(); await until("location.pathname === '/workspace'", "candidate destination");
  count = restricted().length; await navigate("/admin/dashboard"); await until("document.body.innerText.includes('This workspace is for another role')", "candidate denied dashboard"); assert.equal(restricted().length, count);
  assert.ok(restricted().every(call => call.role === "administrator"));
  assert.ok(calls.every(call => call.method === "GET" || call.path.endsWith("/auth/login")), "workspace never mutates backend data");
  assert.equal(calls.some(call => call.path.includes("/admin/candidates") || call.path.includes("/admin/users")), false, "no invented candidate endpoints");
  assert.deepEqual(exceptions, []);
  console.log("Passed: real dashboard contract, unavailable/incomplete metrics, full multi-page upload directory, local search/pagination, candidate profiles, explicit source lookups, history pagination/errors, navigation, empty/401/403/404/500, safe deep links, responsive views and read-only admin role isolation.");
} finally {
  await command("Fetch.disable").catch(() => {});
  socket.close();
}

