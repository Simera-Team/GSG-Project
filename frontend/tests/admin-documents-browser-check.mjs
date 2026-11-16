/* global process, Buffer */
import assert from "node:assert/strict";
import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";
const origin = process.env.UI_CHECK_URL || "http://127.0.0.1:5174";
const debuggerUrl = process.env.CHROME_DEBUG_URL || "http://127.0.0.1:9223";
const artifacts = resolve(".ui-check");
mkdirSync(artifacts, { recursive: true });
const target = await (await fetch(debuggerUrl + "/json/new?about:blank", { method: "PUT" })).json();
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((ok, bad) => { socket.addEventListener("open", ok, { once: true }); socket.addEventListener("error", bad, { once: true }); });
const pending = new Map(), calls = [], exceptions = [];
let nextId = 0, role = "administrator", readError = 0, postError = 0, empty = false, slow = false;
const statuses = ["failed", "processing", "done", "uploaded", "needs_review"];
const attempt = { attempt_number: 1, trigger: "first_run", outcome: "error", provider: "gemini", model_version: "test-model", error_message: "API_KEY_INVALID SECRET_PROVIDER_PAYLOAD", started_at: "2026-11-15T10:00:00Z", finished_at: "2026-11-15T10:01:00Z" };
const records = Array.from({ length: 21 }, (_, index) => ({
  file_id: 101 + index, profile_id: index === 20 ? 9 : 8, user_id: index === 20 ? 10 : 9,
  candidate_name: "Monitoring Candidate " + (index === 20 ? "Two" : "One"),
  original_name: "candidate-source-" + (101 + index) + ".pdf", file_type: "pdf", status: statuses[index % 5],
  extraction_method: "text", ocr_confidence: null,
  error_message: index % 5 === 0 ? "API_KEY_INVALID SECRET_PROVIDER_PAYLOAD traceback api_key=DO_NOT_RENDER" : null,
  uploaded_at: "2026-11-15T10:00:00Z", finished_at: index % 5 === 1 || index % 5 === 3 ? null : "2026-11-15T10:01:00Z",
  attempts: index % 5 === 1 || index % 5 === 3 ? 0 : 1, open_reviews: index % 5 === 0 ? 1 : 0,
  attempts_detail: index % 5 === 1 || index % 5 === 3 ? [] : [{ ...attempt, outcome: index % 5 === 0 ? "error" : "valid", error_message: index % 5 === 0 ? attempt.error_message : null }],
}));
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
    const promise = pending.get(message.id);
    if (!promise) return;
    clearTimeout(promise.timer); pending.delete(message.id);
    if (message.error) promise.bad(Error(JSON.stringify(message.error))); else promise.ok(message.result);
  } else if (message.method === "Runtime.exceptionThrown") exceptions.push(message.params.exceptionDetails.text);
  else if (message.method === "Fetch.requestPaused") {
    const { requestId, request } = message.params;
    const url = new URL(request.url), path = url.pathname;
    calls.push({ path, query: url.search, method: request.method, role });
    let status = 200, body = {};
    try {
      if (path.endsWith("/auth/login")) body = { access_token: "admin-browser-" + role, token_type: "bearer" };
      else if (path.endsWith("/auth/me")) body = { user_id: 7, name: "Monitoring Staff", email: "staff@example.invalid", role };
      else if (path.startsWith("/api/v1/admin/")) {
        if (role !== "administrator") { status = 403; body = { detail: "SECRET" }; }
        else if (request.method === "POST" && /\/admin\/files\/\d+\/rerun$/.test(path)) {
          await new Promise(ok => setTimeout(ok, 400));
          const file = records.find(file => file.file_id === Number(path.split("/").at(-2)));
          if (postError) {
            status = postError; postError = 0; body = { detail: "SECRET_PROVIDER_PAYLOAD" };
            if (status === 409) file.status = "processing";
          } else if (!file) { status = 404; body = { detail: "SECRET" }; }
          else body = { file_id: file.file_id, status: file.status, message: "SECRET_RESULT_PAYLOAD" }, status = 202;
        } else if (readError) { status = readError; body = { detail: "SECRET_PROVIDER_PAYLOAD" }; }
        else if (path.endsWith("/admin/files")) {
          if (slow) await new Promise(ok => setTimeout(ok, 700));
          const params = url.searchParams;
          let items = empty ? [] : records;
          if (params.get("status")) items = items.filter(file => file.status === params.get("status"));
          if (params.get("profile_id")) items = items.filter(file => file.profile_id === Number(params.get("profile_id")));
          const limit = Number(params.get("limit")), offset = Number(params.get("offset"));
          body = { total: items.length, limit, offset, items: items.slice(offset, offset + limit).map(file => {
            const metadata = { ...file }; delete metadata.attempts_detail; return metadata;
          }) };
        } else if (/\/admin\/files\/\d+$/.test(path)) {
          body = records.find(file => file.file_id === Number(path.split("/").at(-1)));
          if (!body) { status = 404; body = { detail: "SECRET" }; }
        } else { status = 404; body = { detail: "UNEXPECTED_ENDPOINT" }; }
      } else if (path.endsWith("/review/items")) body = { total: 0, limit: 20, offset: 0, items: [] };
      else if (path.endsWith("/cv/files")) body = { total: 0, limit: 100, offset: 0, items: [] };
      else if (path.endsWith("/profile/me")) { status = 404; body = {}; }
      else { status = 404; body = { detail: "UNEXPECTED_ENDPOINT" }; }
      await command("Fetch.fulfillRequest", { requestId, responseCode: status, responseHeaders: [{ name: "Content-Type", value: "application/json" }], body: Buffer.from(JSON.stringify(body)).toString("base64") });
    } catch (error) { exceptions.push(error.message); }
  }
});
async function evaluate(expression) {
  const result = await command("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
  if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
}
async function until(expression, label) {
  const started = Date.now();
  while (Date.now() - started < 15000) {
    if (await evaluate("Boolean(" + expression + ")")) return;
    await new Promise(ok => setTimeout(ok, 80));
  }
  throw Error("Timed out: " + label);
}
async function click(selector) { await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`); }
async function navigate(path) { await evaluate(`history.pushState({}, '', ${JSON.stringify(path)});window.dispatchEvent(new PopStateEvent('popstate'))`); }
async function login() {
  await until("!!document.querySelector('#login-email')", "login");
  await evaluate(`{const set=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;for(const [selector,value] of [['#login-email','staff@example.invalid'],['#login-password','test-password']]){const input=document.querySelector(selector);set.call(input,value);input.dispatchEvent(new Event('input',{bubbles:true}));}}`);
  await click("button[type=submit]");
}
async function screenshot(name, width, full = true) {
  await command("Emulation.setDeviceMetricsOverride", { width, height: 1000, deviceScaleFactor: 1, mobile: width < 600 });
  await evaluate("window.scrollTo(0,0)");
  assert.ok(await evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), name + " no horizontal overflow");
  const result = await command("Page.captureScreenshot", { format: "png", captureBeyondViewport: full });
  writeFileSync(resolve(artifacts, name), Buffer.from(result.data, "base64"));
}
const mutationCount = () => calls.filter(call => call.path.includes("/admin/") && call.method === "POST").length;
async function openFile(id) {
  await navigate("/admin/documents/" + id);
  await until("document.querySelector('#admin-file-heading')?.textContent === " + JSON.stringify("candidate-source-" + id + ".pdf"), "file " + id);
}
async function prepare() {
  await click(".ad-rerun > button");
  await until("!!document.querySelector('.rq-confirm-dialog[open]')", "rerun confirmation");
}
async function confirm() { await click(".rq-confirm-buttons button:last-child"); }
try {
  await command("Page.enable"); await command("Runtime.enable");
  await command("Fetch.enable", { patterns: [{ urlPattern: "*/api/v1/*" }] });
  await command("Page.navigate", { url: origin + "/admin/documents/101?page=2" });
  await until("location.pathname === '/login'", "guest blocked");
  await login();
  await until("!!document.querySelector('#admin-file-heading')", "admin deep link");
  assert.equal(await evaluate("location.pathname + location.search"), "/admin/documents/101?page=2");
  assert.equal(mutationCount(), 0, "opening details never starts processing");
  assert.ok(await evaluate("document.body.innerText.includes('invalid API configuration')"));
  assert.equal(await evaluate("/SECRET|API_KEY_INVALID|traceback|DO_NOT_RENDER/.test(document.body.innerText)"), false);
  assert.ok(await evaluate("document.body.innerText.includes('full document status-change history is not available')"));
  await screenshot("admin-document-details-mobile.png", 360);
  await click(".rq-back");
  await until("document.body.innerText.includes('Page 2 of 2')", "back preserves page");
  assert.equal(await evaluate("document.querySelectorAll('.ad-list > li').length"), 1);
  await click(".rq-pagination button:first-child");
  await until("document.querySelectorAll('.ad-list > li').length === 20", "previous page");
  assert.deepEqual(new Set(await evaluate("Array.from(document.querySelectorAll('.ad-list .ws-status'),element=>element.textContent)")), new Set(["Failed", "Processing", "Completed", "Uploaded", "Needs review"]));
  assert.equal(await evaluate("document.querySelector('.ws-nav a.active').getAttribute('href')"), "/admin/documents");
  await evaluate("document.querySelector('select[name=status]').value='failed';document.querySelector('input[name=profile_id]').value='8';document.querySelector('.rq-filters').requestSubmit()");
  await until("document.querySelectorAll('.ad-list > li').length === 4 && location.search.includes('profile_id=8')", "supported filters");
  assert.ok(calls.some(call => call.query.includes("status=failed") && call.query.includes("profile_id=8")));
  await click(".rq-filters a");
  await until("document.querySelectorAll('.ad-list > li').length === 20 && location.search === ''", "clear filters");
  await screenshot("admin-document-list-desktop.png", 1440, false);
  slow = true; await click(".ws-page-heading button");
  await until("!!document.querySelector('.ws-skeleton-list')", "list loading");
  await until("document.querySelectorAll('.ad-list > li').length === 20", "list reload"); slow = false;
  empty = true; await click(".ws-page-heading button"); await until("document.body.innerText.includes('No documents found')", "empty results"); empty = false;
  for (const code of [403, 422, 500]) {
    readError = code; await click(".ws-page-heading button");
    await until("!!document.querySelector('[role=alert]') && !document.querySelector('.ad-list')", "list error " + code);
    assert.equal(await evaluate("document.body.innerText.includes('SECRET')"), false);
  }
  readError = 0; await click(".ws-page-heading button"); await until("!!document.querySelector('.ad-list')", "read recovery");
  await navigate("/admin/documents/99999"); await until("document.body.innerText.includes('document is unavailable')", "404 document");
  const beforeInvalid = calls.length;
  await navigate("/admin/documents/not-an-id"); await until("document.body.innerText.includes('document link is invalid')", "invalid link");
  assert.equal(calls.length, beforeInvalid);
  await openFile(102);
  assert.equal(await evaluate("document.querySelector('.ad-rerun > button').disabled"), true, "processing cannot be rerun");

  await openFile(101); await prepare();
  assert.equal(await evaluate("document.querySelector('dialog[open]').contains(document.activeElement)"), true, "confirmation focus");
  await screenshot("admin-rerun-confirmation-mobile.png", 360, false);
  await click(".rq-confirm-buttons button:first-child");
  await until("!document.querySelector('dialog[open]')", "cancel");
  assert.equal(mutationCount(), 0);
  await prepare();
  await evaluate("document.querySelector('.rq-confirm-buttons button:last-child').click();document.querySelector('.rq-confirm-buttons button:last-child').click()");
  await until("!!document.querySelector('.ad-rerun-result') && !!document.querySelector('#admin-file-heading')", "202 acceptance and detail refresh");
  assert.equal(mutationCount(), 1, "double confirmation only sends one POST");
  assert.ok(await evaluate("document.querySelector('.ad-rerun-result').textContent.includes('Status returned: Failed')"));
  assert.equal(await evaluate("document.querySelector('.ad-rerun > button').disabled"), true, "accepted request stays locked");
  assert.equal(await evaluate("document.body.innerText.includes('SECRET_RESULT_PAYLOAD')"), false);
  await click(".rq-back"); await until("!!document.querySelector('.ad-list')", "list after rerun");
  await openFile(101);
  assert.equal(await evaluate("document.querySelector('.ad-rerun > button').disabled"), true, "pending latch survives navigation");
  records[0].status = "processing"; await click(".ws-page-heading button");
  await until("document.querySelector('#admin-file-heading')?.parentElement.querySelector('.ws-status')?.textContent === 'Processing'", "actual processing update");
  records[0].status = "failed"; records[0].attempts = 2;
  records[0].attempts_detail.push({ ...attempt, attempt_number: 2, trigger: "admin_rerun" });
  await click(".ws-page-heading button");
  await until("document.querySelectorAll('.ad-attempt').length === 2 && document.querySelector('.ad-rerun > button')?.disabled === false", "new recorded attempt releases latch");
  assert.ok(await evaluate("document.body.innerText.includes('Administrator rerun')"));

  postError = 409; await prepare(); await confirm();
  await until("document.body.innerText.includes('already being processed') && document.querySelector('.ad-rerun > button')?.disabled === true", "409 refresh and locked current processing");
  await openFile(104); postError = 422; await prepare(); await confirm();
  await until("document.querySelector('.ad-rerun [role=alert]')?.textContent.includes('not accepted')", "422 rerun validation");
  assert.equal(await evaluate("document.querySelector('.ad-rerun > button').disabled"), true);
  await click(".ws-page-heading button"); await until("document.querySelector('.ad-rerun > button')?.disabled === false", "refresh after rejection");

  await openFile(105); postError = 403; await prepare(); await confirm();
  await until("document.querySelector('.ad-rerun [role=alert]')?.textContent.includes('administrators')", "403 rerun denied");
  assert.equal(await evaluate("document.querySelector('.ad-rerun > button').disabled"), true);
  await openFile(106); postError = 500; await prepare(); await confirm();
  await until("document.querySelector('.ad-rerun [role=alert]')?.textContent.includes('confirm')", "uncertain server error");
  const beforeRefresh = mutationCount();
  await click(".ws-page-heading button");
  await until("document.querySelector('.ad-rerun > button')?.disabled === true && !!document.querySelector('#admin-file-heading')", "uncertain latch after refresh");
  assert.equal(mutationCount(), beforeRefresh, "refresh never reruns");

  await openFile(110); postError = 401; await prepare(); await confirm();
  await until("location.pathname === '/login' && document.body.innerText.includes('session has expired')", "mutation 401");
  assert.equal(await evaluate("sessionStorage.getItem('access_token')"), null);
  await login(); await until("location.pathname === '/admin/documents/110' && !!document.querySelector('#admin-file-heading')", "expired admin deep link survives login");
  await click(".ws-logout"); await until("location.pathname === '/login'", "admin logout");
  role = "reviewer"; await login(); await until("location.pathname === '/reviewer/reviews'", "reviewer landing");
  let adminCalls = calls.filter(call => call.path.startsWith("/api/v1/admin/")).length;
  await navigate("/admin/documents/101");
  await until("document.body.innerText.includes('This workspace is for another role')", "reviewer denied admin details");
  assert.equal(calls.filter(call => call.path.startsWith("/api/v1/admin/")).length, adminCalls);
  await click(".page-notice-actions button"); await until("location.pathname === '/login'", "account switch");
  role = "candidate"; await login(); await until("location.pathname === '/workspace'", "candidate landing");
  adminCalls = calls.filter(call => call.path.startsWith("/api/v1/admin/")).length;
  await navigate("/admin/documents"); await until("document.body.innerText.includes('This workspace is for another role')", "candidate denied admin list");
  assert.equal(calls.filter(call => call.path.startsWith("/api/v1/admin/")).length, adminCalls);
  assert.ok(calls.filter(call => call.path.startsWith("/api/v1/admin/")).every(call => call.role === "administrator"));
  assert.ok(calls.filter(call => call.path.startsWith("/api/v1/admin/") && call.method === "POST").every(call => /\/files\/\d+\/rerun$/.test(call.path)));
  assert.equal(await evaluate("document.body.innerText.includes('SECRET')"), false);
  assert.deepEqual(exceptions, []);
  console.log("Passed: admin document deep links, role isolation, supported filters/pagination, attempts, safe errors, responsive views, confirmed/mocked reruns, cancel/double-submit/pending/uncertain protection, real returned status, 401/403/404/409/422/500, and no automatic reruns.");
} finally {
  await command("Fetch.disable").catch(() => {});
  socket.close();
}
