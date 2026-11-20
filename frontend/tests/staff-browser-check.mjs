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
let id = 0, role = "reviewer", responseMode = "normal", slow = false, mutationStatus = 0;
const base = {
  review_id: 42, profile_id: 8, candidate_name: "Browser Candidate", candidate_email: "candidate@example.invalid",
  file_id: 12, file_name: "candidate-resume.pdf", file_type: "pdf", entity: "personal_info", field_name: "city",
  reasons: ["source_conflict"], message: "The uploaded sources disagree about the candidate's city.",
  is_failed_job: false, created_at: "2026-11-15T10:00:00Z", assigned_to_candidate: false,
  sent_to_candidate_at: null, resolved: false, resolution: null, resolved_value: null, resolved_option_id: null,
  resolved_by: null, resolved_by_name: null, resolved_at: null,
  options: [
    { option_id: 11, file_id: 12, file_name: "candidate-resume.pdf", file_type: "pdf", field_id: 90, value: "Amman", confidence: 0.82, evidence: "Contact: Amman, Jordan", page: 2 },
    { option_id: 12, file_id: 13, file_name: "linkedin.md", file_type: "md", field_id: 91, value: "Dubai", confidence: null, evidence: "<script>window.__unsafe=true</script>", page: null },
  ],
};
const records = Array.from({ length: 21 }, (_, index) => ({
  ...base, review_id: 42 + index,
  resolved: index === 2, resolution: index === 2 ? "option" : null,
  assigned_to_candidate: index === 1,
  reasons: index === 1 ? ["low_confidence"] : ["source_conflict"],
}));
records[3] = { ...records[3], entity: "skills[2]", field_name: "name", reasons: ["unknown_skill"] };
records[4] = { ...records[4], entity: null, field_name: null, reasons: ["llm_failed"], is_failed_job: true, options: [], message: "API_KEY_INVALID SECRET_PROVIDER_PAYLOAD traceback api_key=DO_NOT_RENDER" };
records[8] = { ...records[8], entity: "work_experience[0]", field_name: "end_date" };
records[12] = { ...records[12], entity: "skills[3]", field_name: "name", reasons: ["unknown_skill"] };
function command(method, params = {}) {
  const next = ++id;
  return new Promise((ok, bad) => {
    const timer = setTimeout(() => { pending.delete(next); bad(Error(method + " timed out")); }, 15000);
    pending.set(next, { ok, bad, timer });
    socket.send(JSON.stringify({ id: next, method, params }));
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
    calls.push({ path, query: url.search, method: request.method, role, body: request.postData ? JSON.parse(request.postData) : undefined });
    let status = 200, body;
    try {
      if (path.endsWith("/auth/login")) body = { access_token: "staff-browser-token", token_type: "bearer" };
      else if (path.endsWith("/auth/me")) body = { user_id: 7, name: "Staff Browser", email: "staff@example.invalid", role };
      else if (request.method === "POST" && /\/review\/items\/\d+\/(resolve|request-candidate)$/.test(path)) {
        const record = records.find(item => item.review_id === Number(path.split("/").at(-2)));
        await new Promise(ok => setTimeout(ok, 400));
        if (mutationStatus) {
          status = mutationStatus; mutationStatus = 0; body = { detail: "SECRET_PROVIDER_PAYLOAD" };
          if (status === 409) Object.assign(record, { resolved: true, resolution: "option", resolved_value: "Other reviewer", resolved_by_name: "Another reviewer", resolved_at: "2026-11-15T12:00:00Z" });
        } else if (path.endsWith("/request-candidate")) {
          Object.assign(record, { assigned_to_candidate: true, sent_to_candidate_at: "2026-11-15T12:00:00Z" });
          body = { item: record, candidate_email: record.candidate_email, suggested_message: "Please confirm the correct value for your profile." };
        } else {
          const decision = JSON.parse(request.postData);
          const option = record.options.find(option => option.option_id === decision.option_id);
          Object.assign(record, { resolved: true, resolution: { option: "option", custom: "custom", reject: "rejected", dismiss: "dismissed" }[decision.action], resolved_value: decision.map_to_skill || (decision.action === "custom" ? decision.value : option?.value ?? null), resolved_option_id: option?.option_id ?? null, resolved_by: 7, resolved_by_name: "Staff Browser", resolved_at: "2026-11-15T12:00:00Z" });
          body = record;
        }
      }
      else if (responseMode === "unauthorized") { status = 401; body = { detail: "SECRET" }; }
      else if (responseMode === "forbidden") { status = 403; body = { detail: "SECRET" }; }
      else if (responseMode === "error") { status = 500; body = { detail: "SECRET" }; }
      else if (path.endsWith("/review/items")) {
        if (slow) await new Promise(ok => setTimeout(ok, 700));
        const query = url.searchParams, state = query.get("status");
        let items = responseMode === "empty" ? [] : records.filter(item => state === "all" || state === "resolved" ? (state === "all" || item.resolved) : !item.resolved && (state !== "waiting_candidate" || item.assigned_to_candidate));
        if (query.get("reason")) items = items.filter(item => item.reasons.includes(query.get("reason")));
        if (query.get("profile_id")) items = items.filter(item => item.profile_id === Number(query.get("profile_id")));
        const limit = Number(query.get("limit")), offset = Number(query.get("offset"));
        body = { total: items.length, limit, offset, items: items.slice(offset, offset + limit) };
      } else if (/\/review\/items\/\d+$/.test(path)) {
        body = records.find(item => item.review_id === Number(path.split("/").pop()));
        if (!body) { status = 404; body = { detail: "SECRET" }; }
      } else { status = 403; body = { detail: "UNEXPECTED_ENDPOINT" }; }
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
  const start = Date.now();
  while (Date.now() - start < 15000) {
    if (await evaluate("Boolean(" + expression + ")")) return;
    await new Promise(ok => setTimeout(ok, 80));
  }
  throw Error("Timed out: " + label);
}
async function navigate(path) { await evaluate(`history.pushState({}, '', ${JSON.stringify(path)});window.dispatchEvent(new PopStateEvent('popstate'))`); }
async function click(selector) { await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`); }
async function screenshot(name, width) {
  await command("Emulation.setDeviceMetricsOverride", { width, height: 1000, deviceScaleFactor: 1, mobile: width < 600 });
  assert.ok(await evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), name + " no overflow");
  const result = await command("Page.captureScreenshot", { format: "png", captureBeyondViewport: true });
  writeFileSync(resolve(artifacts, name), Buffer.from(result.data, "base64"));
}
async function login() {
  await until("!!document.querySelector('#login-email')", "login");
  await evaluate(`{const set=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;for(const [selector,value] of [['#login-email','staff@example.invalid'],['#login-password','test-password']]){const input=document.querySelector(selector);set.call(input,value);input.dispatchEvent(new Event('input',{bubbles:true}));}}`);
  await click("button[type=submit]");
}
try {
  await command("Page.enable"); await command("Runtime.enable");
  await command("Fetch.enable", { patterns: [{ urlPattern: "*/api/v1/*" }] });
  await command("Page.navigate", { url: origin + "/reviewer/reviews/42?status=all&page=2" });
  await until("location.pathname === '/login'", "guest guard");
  await login();
  await until("document.querySelector('#review-context-heading')?.textContent === 'Review #42'", "staff deep link after login");
  assert.equal(await evaluate("location.search"), "?status=all&page=2");
  assert.equal(await evaluate("window.__unsafe"), undefined);
  assert.equal(await evaluate("document.querySelectorAll('.rq-option').length"), 2);
  assert.equal(await evaluate("!!document.querySelector('.rq-option blockquote script')"), false);
  assert.equal(await evaluate("document.querySelectorAll('a[href^=\"/files/\"],a[href^=\"/profile/\"],a[href^=\"/admin/\"]').length"), 0);
  await screenshot("review-details-desktop.png", 1440); await screenshot("review-details-mobile.png", 360);
  await click(".rq-back");
  await until("document.body.innerText.includes('Page 2 of 2')", "back preserves pagination");
  assert.equal(await evaluate("document.querySelectorAll('.rq-item').length"), 1);
  await click(".rq-pagination button:first-child");
  await until("document.querySelectorAll('.rq-item').length === 20", "previous page");
  await evaluate("document.querySelector('select[name=status]').value='waiting_candidate';document.querySelector('select[name=reason]').value='low_confidence';document.querySelector('input[name=profile_id]').value='8';document.querySelector('.rq-filters').requestSubmit()");
  await until("document.querySelectorAll('.rq-item').length === 1 && location.search.includes('waiting_candidate')", "filter submit");
  assert.ok(calls.some(call => call.query.includes("profile_id=8") && call.query.includes("reason=low_confidence")));
  assert.equal(await evaluate("location.search.includes('page=')"), false);
  await click(".rq-filters a");
  await until("document.querySelectorAll('.rq-item').length === 20 && location.search === ''", "clear filters");
  await evaluate("document.querySelector('select[name=reason]').value='low_confidence'");
  await click(".rq-filters a");
  await until("document.querySelector('select[name=reason]')?.value === '' && !!document.querySelector('.rq-list')", "clear unsaved filters");
  await screenshot("review-queue-desktop.png", 1440); await screenshot("review-queue-tablet.png", 768); await screenshot("review-queue-mobile.png", 360);
  for (const [mode, expected] of [["empty", "No review items found"], ["error", "couldn't load the review queue"], ["forbidden", "don't have permission"]]) {
    responseMode = mode; await click(".ws-page-heading button");
    await until(`document.body.innerText.includes(${JSON.stringify(expected)})`, mode);
    assert.equal(await evaluate("!!document.querySelector('.rq-item')"), false);
    assert.equal(await evaluate("document.body.innerText.includes('SECRET')"), false);
  }
  responseMode = "normal"; slow = true;
  await click(".ws-page-heading button");
  await until("!!document.querySelector('.ws-skeleton-list')", "loading state");
  await until("document.querySelectorAll('.rq-item').length === 20", "retry recovery"); slow = false;
  await navigate("/reviewer/reviews/99999"); await until("document.body.innerText.includes('review item is unavailable')", "missing item");
  await navigate("/reviewer/reviews/not-a-number"); await until("document.body.innerText.includes('review link is invalid')", "invalid item");
  await navigate("/documents"); await until("document.body.innerText.includes('This workspace is for another role')", "reviewer cannot enter candidate pages");
  await click(".page-notice-actions a"); await until("!!document.querySelector('.rq-list')", "own workspace recovery");
  await navigate("/admin/reviews"); await until("document.body.innerText.includes('This workspace is for another role')", "reviewer cannot enter admin workspace");
  await click(".page-notice-actions button"); await until("location.pathname === '/login'", "switch account");
  role = "administrator"; await login();
  await until("location.pathname === '/admin/reviews' && !!document.querySelector('.rq-list')", "admin destination");
  await click(".rq-item-title a"); await until("!!document.querySelector('#review-context-heading')", "admin details");

  // Mutations below are fulfilled by this browser harness, never by the real backend.
  async function changeValue(selector, value) {
    await evaluate(`{const input=document.querySelector(${JSON.stringify(selector)});const setter=Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input),'value').set;setter.call(input,${JSON.stringify(value)});input.dispatchEvent(new Event(input.tagName==='SELECT'?'change':'input',{bubbles:true}));}`);
  }
  async function openItem(id) {
    await navigate("/admin/reviews/" + id);
    await until("document.querySelector('#review-context-heading')?.textContent === " + JSON.stringify("Review #" + id) + " && !!document.querySelector('.rq-actions')", "open decision item " + id);
  }
  async function prepare() {
    await click(".rq-actions button[type=submit]");
    await until("!!document.querySelector('.rq-confirm-dialog[open]')", "decision confirmation");
  }
  async function confirmDecision() {
    await click(".rq-confirm-buttons button:last-child");
    await until("!!document.querySelector('#review-resolution-heading') && !document.querySelector('.rq-actions')", "persisted decision");
  }
  await until("!!document.querySelector('.rq-actions')", "decision form");
  const beforeDecision = calls.filter(call => call.method === "POST" && call.path.includes("/review/")).length;
  await click(".rq-actions button[type=submit]");
  await until("document.querySelector('.rq-actions [role=alert]')?.textContent.includes('Select one')", "alternative required");
  assert.equal(await evaluate("!!document.querySelector('.rq-confirm-dialog[open]')"), false);
  await click(".rq-radio input");
  await prepare();
  await click(".rq-confirm-buttons button:first-child");
  await until("!document.querySelector('.rq-confirm-dialog[open]')", "cancel confirmation");
  assert.equal(calls.filter(call => call.method === "POST" && call.path.includes("/review/")).length, beforeDecision);
  await prepare();
  await evaluate("document.querySelector('.rq-confirm-buttons button:last-child').click();document.querySelector('.rq-confirm-buttons button:last-child').click()");
  await until("!!document.querySelector('#review-resolution-heading') && !document.querySelector('.rq-actions')", "saved alternative");
  assert.equal(calls.filter(call => call.method === "POST" && call.path.includes("/review/")).length, beforeDecision + 1, "double confirm sends once");
  assert.ok(calls.some(call => call.path === "/api/v1/review/items/42/resolve" && call.body.action === "option" && call.body.option_id === 11));
  assert.ok(await evaluate("document.querySelector('#review-resolution-heading').parentElement.innerText.includes('Staff Browser')"));
  await screenshot("review-decision-persisted.png", 1440);
  await click(".rq-back");
  await until("!!document.querySelector('.rq-list')", "queue refreshed after decision");
  assert.equal(await evaluate("!!document.querySelector('.rq-item-title a[href^=\"/admin/reviews/42?\"]')"), false, "resolved item removed from open queue");

  await openItem(47);
  await changeValue(".rq-actions form select", "custom");
  await changeValue(".rq-actions textarea", "Berlin");
  await prepare(); await confirmDecision();
  assert.ok(await evaluate("document.querySelector('#review-resolution-heading').parentElement.innerText.includes('Berlin')"));

  await openItem(48);
  await changeValue(".rq-actions form select", "reject");
  await prepare(); await confirmDecision();
  assert.ok(calls.some(call => call.path.endsWith("/48/resolve") && call.body.action === "reject"));

  await openItem(46);
  assert.ok(await evaluate("document.querySelector('.rq-message').innerText.includes('invalid API configuration')"));
  assert.equal(await evaluate("document.body.innerText.includes('SECRET_PROVIDER_PAYLOAD') || document.body.innerText.includes('API_KEY_INVALID')"), false);
  assert.deepEqual(await evaluate("Array.from(document.querySelectorAll('.rq-actions form select option'),option=>option.value)"), ["dismiss"]);
  await prepare(); await confirmDecision();
  assert.ok(calls.some(call => call.path.endsWith("/46/resolve") && call.body.action === "dismiss"));

  await openItem(45);
  await click(".rq-radio input");
  await changeValue(".rq-skill-mapping select", "map");
  await click(".rq-actions button[type=submit]");
  await until("document.querySelector('.rq-actions [role=alert]')?.textContent.includes('standard skill')", "mapping required");
  await changeValue(".rq-skill-mapping input", "React");
  await prepare(); await screenshot("review-skill-confirmation-mobile.png", 360);
  assert.ok(await evaluate("document.querySelector('dialog[open]').innerText.includes('reused for future sources')"));
  await confirmDecision();
  assert.ok(calls.some(call => call.path.endsWith("/45/resolve") && call.body.map_to_skill === "React"));

  await openItem(54); await click(".rq-radio input"); await prepare(); await confirmDecision();
  assert.ok(calls.some(call => call.path.endsWith("/54/resolve") && !("map_to_skill" in call.body)), "skill approval uses normal option decision");

  await openItem(49);
  await click(".rq-clarification-action button");
  await until("!!document.querySelector('dialog[open]')", "clarification confirmation");
  await command("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape" });
  await command("Input.dispatchKeyEvent", { type: "keyUp", key: "Escape", code: "Escape" });
  await until("!document.querySelector('dialog[open]') && document.activeElement === document.querySelector('.rq-clarification-action button')", "clarification Escape restores its own trigger");
  await click(".rq-clarification-action button");
  await until("!!document.querySelector('dialog[open]')", "clarification reopened");
  assert.ok(await evaluate("document.querySelector('dialog[open]').innerText.includes('No email will be sent')"));
  await click(".rq-confirm-buttons button:last-child");
  await until("!!document.querySelector('#clarification-text') && document.body.innerText.includes('Waiting for candidate')", "recorded clarification");
  assert.ok(await evaluate("document.body.innerText.includes('No email was sent')"));
  assert.equal(await evaluate("document.querySelector('.rq-clarification-action button').disabled"), true);
  assert.ok((await evaluate("document.querySelector('.rq-clarification-message a').getAttribute('href')")).startsWith("mailto:"));
  await screenshot("review-clarification-mobile.png", 360);

  await openItem(50); await changeValue(".rq-actions form select", "custom"); await changeValue(".rq-actions textarea", "invalid date");
  mutationStatus = 422; await prepare(); await click(".rq-confirm-buttons button:last-child");
  await until("document.querySelector('.rq-actions [role=alert]')?.textContent.includes('could not accept')", "422 validation");
  assert.equal(await evaluate("document.querySelector('.rq-actions textarea').value"), "invalid date");
  assert.equal(await evaluate("document.body.innerText.includes('SECRET')"), false);
  await changeValue(".rq-actions textarea", "2024"); await prepare(); await confirmDecision();

  await openItem(51); await click(".rq-radio input");
  mutationStatus = 409; await prepare(); await click(".rq-confirm-buttons button:last-child");
  await until("!!document.querySelector('#review-resolution-heading') && document.body.innerText.includes('not ready for a decision')", "409 reloads persisted state");

  await openItem(52); await click(".rq-radio input");
  mutationStatus = 403; await prepare(); await click(".rq-confirm-buttons button:last-child");
  await until("document.querySelector('.rq-actions [role=alert]')?.textContent.includes('permission')", "403 denied");
  assert.equal(await evaluate("document.querySelector('.rq-actions button[type=submit]').matches(':disabled')"), true);
  await click(".ws-page-heading button");
  await until("document.querySelector('.rq-actions button[type=submit]')?.matches(':disabled') === false", "refresh restores action state");

  // Reloading Login with a verified administrator cannot send it to public Home.
  await navigate("/login"); await until("location.pathname === '/admin/reviews' && !!document.querySelector('.rq-list')", "existing admin login destination");
  await navigate("/dashboard"); await until("location.pathname === '/admin/reviews' && !!document.querySelector('.rq-list')", "legacy admin dashboard destination");

  await navigate("/"); await until("document.querySelector('.home-hero-actions a')?.getAttribute('href') === '/admin/reviews'", "staff home CTA");
  await navigate("/admin/reviews"); await until("!!document.querySelector('.rq-list')", "return to admin");
  responseMode = "unauthorized"; await click(".ws-page-heading button");
  await until("location.pathname === '/login' && document.body.innerText.includes('session has expired')", "401 expires session");
  assert.equal(await evaluate("sessionStorage.getItem('access_token')"), null);
  responseMode = "normal"; role = "candidate"; await login();
  await until("location.pathname === '/workspace'", "candidate role destination");
  const count = calls.filter(call => call.path.includes("/review/")).length;
  await navigate("/reviewer/reviews/42");
  await until("document.body.innerText.includes('This workspace is for another role')", "candidate denied staff details");
  assert.equal(calls.filter(call => call.path.includes("/review/")).length, count, "candidate denial never fetches review data");
  assert.ok(calls.filter(call => call.role !== "candidate").every(call => /\/auth\//.test(call.path) || /\/review\/items/.test(call.path)), "staff never requests candidate/admin data endpoints");
  assert.ok(calls.filter(call => call.path.includes("/review/") && call.method === "POST").every(call => /\/(resolve|request-candidate)$/.test(call.path)), "only supported review mutations");
  assert.deepEqual(exceptions, []);
  console.log("Passed: staff deep links/login, filters, pagination/back navigation, reviewer/admin/candidate guards, details/evidence escaping, loading/empty/error/403/404/401, responsive 360px/1440px, confirmed decisions, duplicate-submit protection, skill mapping/approval, clarification, persisted refresh, and no forbidden endpoint calls.");
} finally {
  await command("Fetch.disable").catch(() => {});
  socket.close();
}
