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
let id = 0, role = "administrator", creationResult = 201, createdId = 500;
const initialPassword = "test-initial-password";
function command(method, params = {}) {
  const next = ++id;
  return new Promise((ok, bad) => {
    const timer = setTimeout(() => { pending.delete(next); bad(Error(method + " timed out")); }, 15000);
    pending.set(next, { ok, bad, timer }); socket.send(JSON.stringify({ id: next, method, params }));
  });
}
socket.addEventListener("message", async event => {
  const message = JSON.parse(event.data);
  if (message.id) {
    const request = pending.get(message.id); if (!request) return;
    clearTimeout(request.timer); pending.delete(message.id);
    if (message.error) request.bad(Error(JSON.stringify(message.error))); else request.ok(message.result);
  } else if (message.method === "Runtime.exceptionThrown") exceptions.push(message.params.exceptionDetails.text);
  else if (message.method === "Fetch.requestPaused") {
    const { requestId, request } = message.params, path = new URL(request.url).pathname;
    calls.push({ path, method: request.method, role, body: request.postData ? JSON.parse(request.postData) : undefined });
    let status = 200, body = {};
    try {
      if (path.endsWith("/auth/login")) body = { access_token: "staff-create-token-" + role, token_type: "bearer" };
      else if (path.endsWith("/auth/me")) body = { user_id: 7, name: "Current Admin", email: "current@example.invalid", role };
      else if (path === "/api/v1/admin/users" && request.method === "POST") {
        await new Promise(ok => setTimeout(ok, 400));
        const result = creationResult; creationResult = 201;
        if (result === "network") { await command("Fetch.failRequest", { requestId, errorReason: "InternetDisconnected" }); return; }
        if (role !== "administrator") { status = 403; body = { detail: "SECRET_FORBIDDEN" }; }
        else if (result === "malformed") { status = 201; body = { user_id: 0, name: "SECRET_INVALID_CONFIRMATION" }; }
        else if (result !== 201) { status = result; body = { detail: [{ input: { password: "SECRET_PASSWORD" }, msg: "SECRET_PROVIDER_PAYLOAD" }] }; }
        else { const values = JSON.parse(request.postData); status = 201; body = { user_id: ++createdId, name: "Stored " + values.name, email: values.email.toLowerCase(), role: values.role }; }
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
  const start = Date.now();
  while (Date.now() - start < 15000) { if (await evaluate("Boolean(" + expression + ")")) return; await new Promise(ok => setTimeout(ok, 80)); }
  throw Error("Timed out: " + label);
}
async function click(selector) { await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`); }
async function navigate(path) { await evaluate(`history.pushState({}, '', ${JSON.stringify(path)});window.dispatchEvent(new PopStateEvent('popstate'))`); }
async function fill(values) {
  await evaluate(`{for(const [selector,value] of Object.entries(${JSON.stringify(values)})){const input=document.querySelector(selector);const setter=Object.getOwnPropertyDescriptor(Object.getPrototypeOf(input),'value').set;setter.call(input,value);input.dispatchEvent(new Event(input.tagName==='SELECT'?'change':'input',{bubbles:true}));}}`);
}
async function login() {
  await until("!!document.querySelector('#login-email')", "login");
  await fill({ "#login-email": "current@example.invalid", "#login-password": "test-admin-password" });
  await click("button[type=submit]");
}
async function account(values = {}) {
  await fill({ ".sm-form input[name=name]": "New Reviewer", ".sm-form input[name=email]": "New-Reviewer@example.invalid", ".sm-form input[name=password]": initialPassword, ".sm-form select[name=role]": "reviewer", ...values });
}
async function prepare() {
  await click(".sm-form button[type=submit]");
  await until("!!document.querySelector('dialog[open]')", "account confirmation");
}
async function confirm() { await click(".rq-confirm-buttons button:last-child"); }
const creationCalls = () => calls.filter(call => call.path === "/api/v1/admin/users");
async function resetPage() {
  await navigate("/admin/reviews"); await until("!!document.querySelector('#review-queue-heading')", "leave staff form");
  await navigate("/admin/staff"); await until("!!document.querySelector('.sm-form')", "fresh staff form");
}
async function screenshot(name, width) {
  await command("Emulation.setDeviceMetricsOverride", { width, height: 1000, deviceScaleFactor: 1, mobile: width < 600 });
  await evaluate("window.scrollTo(0,0)");
  assert.ok(await evaluate("document.documentElement.scrollWidth <= innerWidth + 1"), name + " no overflow");
  const result = await command("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  writeFileSync(resolve(artifacts, name), Buffer.from(result.data, "base64"));
}
try {
  await command("Page.enable"); await command("Runtime.enable");
  await command("Fetch.enable", { patterns: [{ urlPattern: "*/api/v1/*" }] });
  await command("Page.navigate", { url: origin + "/admin/staff?from=dashboard" });
  await until("location.pathname === '/login'", "guest blocked"); await login();
  await until("!!document.querySelector('.sm-form')", "admin staff deep link");
  assert.equal(await evaluate("location.pathname + location.search"), "/admin/staff?from=dashboard");
  assert.equal(await evaluate("document.querySelector('.ws-nav a.active').getAttribute('href')"), "/admin/staff");
  assert.equal(creationCalls().length, 0);
  assert.ok(await evaluate("document.body.innerText.includes('not a staff directory')"));
  assert.deepEqual(await evaluate("Array.from(document.querySelectorAll('.sm-form select option'),option=>option.value)"), ["reviewer", "administrator"]);
  await click(".sm-form button[type=submit]");
  await until("document.querySelectorAll('.sm-form [aria-invalid=true]').length === 3", "required field validation");
  assert.equal(await evaluate("document.activeElement.name"), "name");
  assert.equal(creationCalls().length, 0);
  await account({ ".sm-form input[name=email]": "bad", ".sm-form input[name=password]": "short" });
  await click(".sm-form button[type=submit]");
  await until("document.querySelector('.sm-form input[name=email]').getAttribute('aria-invalid') === 'true'", "email and password validation");
  assert.equal(creationCalls().length, 0);
  await account();
  await until("document.querySelectorAll('.sm-form [aria-invalid=true]').length === 0 && !document.querySelector('.sm-panel [role=alert]')", "corrected fields clear stale validation before resubmission");
  await click('.sm-password button[aria-label="Show password"]');
  assert.equal(await evaluate("document.querySelector('.sm-form input[name=password]').type"), "text");
  await click('.sm-password button[aria-label="Hide password"]');
  assert.equal(await evaluate("document.querySelector('.sm-form input[name=password]').type"), "password");
  await screenshot("staff-management-desktop.png", 1440);
  await screenshot("staff-management-tablet.png", 768);
  await prepare();
  assert.equal(await evaluate("document.querySelector('dialog[open]').contains(document.activeElement)"), true);
  assert.equal(await evaluate("document.activeElement.textContent"), "Cancel");
  for (let n = 0; n < 3; n++) {
    await command("Input.dispatchKeyEvent", { type: "keyDown", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 });
    await command("Input.dispatchKeyEvent", { type: "keyUp", key: "Tab", code: "Tab", windowsVirtualKeyCode: 9 });
    assert.equal(await evaluate("document.querySelector('dialog[open]').contains(document.activeElement)"), true, "Tab stays inside modal");
  }
  assert.equal(await evaluate(`document.querySelector('dialog[open]').innerText.includes(${JSON.stringify(initialPassword)})`), false);
  await click(".rq-confirm-buttons button:first-child"); await until("!document.querySelector('dialog[open]')", "cancel");
  await until("document.activeElement === document.querySelector('.sm-form button[type=submit]')", "cancel restores trigger focus");
  assert.equal(creationCalls().length, 0);
  await prepare(); await command("Input.dispatchKeyEvent", { type: "keyDown", key: "Escape", code: "Escape" }); await command("Input.dispatchKeyEvent", { type: "keyUp", key: "Escape", code: "Escape" }); await until("!document.querySelector('dialog[open]')", "Escape cancels");
  assert.equal(creationCalls().length, 0);
  await prepare();
  await evaluate("document.querySelector('.rq-confirm-buttons button:last-child').click();document.querySelector('.rq-confirm-buttons button:last-child').click()");
  await until("!!document.querySelector('.sm-success') && document.querySelector('.sm-form input[name=password]').value === ''", "real response confirmation and password cleanup");
  assert.equal(creationCalls().length, 1, "double confirmation creates one request");
  assert.deepEqual(creationCalls()[0].body, { name: "New Reviewer", email: "new-reviewer@example.invalid", password: initialPassword, role: "reviewer" });
  assert.ok(await evaluate("document.querySelector('.sm-success').innerText.includes('Stored New Reviewer')"));
  assert.equal(await evaluate("document.querySelector('.sm-form input[name=password]').type"), "password");
  assert.equal(await evaluate("sessionStorage.getItem('access_token')"), "staff-create-token-administrator");
  assert.equal(await evaluate(`JSON.stringify(sessionStorage).includes(${JSON.stringify(initialPassword)})`), false);
  await until("document.activeElement === document.querySelector('.sm-success')", "success focus");
  assert.equal(await evaluate("!!document.querySelector('.sm-panel [role=alert]') || !!document.querySelector('.sm-field-error')"), false, "success clears stale error feedback");
  await screenshot("staff-created-mobile.png", 360);

  await account({ ".sm-form input[name=name]": "New Admin", ".sm-form input[name=email]": "new-admin@example.invalid", ".sm-form select[name=role]": "administrator" });
  await prepare();
  assert.ok(await evaluate("document.querySelector('dialog[open] h2').innerText.includes('Administrator')"));
  assert.ok(await evaluate("document.querySelector('dialog[open]').innerText.includes('staff account creation')"));
  await screenshot("staff-administrator-confirmation-mobile.png", 360);
  await confirm(); await until("document.querySelector('.sm-success')?.innerText.includes('Stored New Admin')", "administrator created response");
  assert.equal(creationCalls().length, 2);
  assert.equal(creationCalls()[1].body.role, "administrator");
  assert.equal(await evaluate("document.querySelectorAll('.sm-success').length"), 1);

  for (const code of [409, 422]) {
    await account(); creationResult = code; await prepare(); await confirm();
    await until(`document.querySelector('.sm-panel [role=alert]')?.innerText.includes(${JSON.stringify(code === 409 ? "already registered" : "server rejected")}) && document.querySelector('.sm-form input[name=password]').value === ''`, "server rejection " + code);
    assert.equal(await evaluate("!!document.querySelector('.sm-success')"), false);
    assert.equal(await evaluate("document.querySelector('.sm-form input[name=email]').value"), "New-Reviewer@example.invalid");
    assert.equal(await evaluate("document.body.innerText.includes('SECRET')"), false);
    if (code === 409) {
      await fill({ ".sm-form input[name=email]": "corrected@example.invalid" });
      await until("document.querySelector('.sm-form input[name=email]').getAttribute('aria-invalid') === 'false' && !document.querySelector('.sm-panel [role=alert]')", "edited duplicate email clears server feedback");
    }
  }
  await account(); creationResult = 403; await prepare(); await confirm();
  await until("document.querySelector('.sm-panel [role=alert]')?.innerText.includes('Only administrators')", "403 forbidden");
  assert.equal(await evaluate("document.querySelector('.sm-form fieldset').disabled"), true);
  await resetPage();

  for (const failure of [500, "network", "malformed"]) {
    await account(); creationResult = failure; await prepare(); await confirm();
    await until("!!document.querySelector('.sm-retry') && document.querySelector('.sm-form input[name=password]').value === ''", "uncertain " + failure);
    assert.equal(await evaluate("document.querySelector('.sm-form fieldset').disabled"), true);
    assert.equal(await evaluate("!!document.querySelector('.sm-success') || document.body.innerText.includes('SECRET')"), false);
    const count = creationCalls().length;
    await click(".sm-retry button");
    assert.equal(creationCalls().length, count, "preparing retry never submits automatically");
    assert.equal(await evaluate("document.querySelector('.sm-form fieldset').disabled"), false);
  }
  await account(); creationResult = 401; await prepare(); await confirm();
  await until("location.pathname === '/login' && document.body.innerText.includes('session has expired')", "401 expires session");
  assert.equal(await evaluate("sessionStorage.getItem('access_token')"), null);
  await login(); await until("location.pathname === '/admin/staff' && !!document.querySelector('.sm-form')", "staff return path after expiry");
  await click(".ws-logout"); await until("location.pathname === '/login'", "logout");
  role = "reviewer"; await login(); await until("location.pathname === '/reviewer/reviews'", "reviewer landing");
  assert.equal(await evaluate("!!document.querySelector('.ws-nav a[href=\"/admin/staff\"]')"), false);
  let count = creationCalls().length;
  await navigate("/admin/staff"); await until("document.body.innerText.includes('This workspace is for another role')", "reviewer guard"); assert.equal(creationCalls().length, count);
  await click(".page-notice-actions button"); await until("location.pathname === '/login'", "switch accounts");
  role = "candidate"; await login(); await until("location.pathname === '/workspace'", "candidate landing");
  count = creationCalls().length; await navigate("/admin/staff"); await until("document.body.innerText.includes('This workspace is for another role')", "candidate guard"); assert.equal(creationCalls().length, count);
  assert.ok(creationCalls().every(call => call.method === "POST" && call.role === "administrator"), "no invented staff listing or non-admin request");
  assert.ok(calls.filter(call => call.method !== "GET").every(call => call.path.endsWith("/auth/login") || call.path === "/api/v1/admin/users"), "only supported mocked mutations");
  assert.deepEqual(exceptions, []);
  console.log("Passed: staff route/role isolation, validation, password visibility/cleanup, confirmation/cancel/Escape/focus, duplicate prevention, Reviewer/Admin POSTs, actual response display, 401/403/409/422/server/network/malformed handling, safe retries, no staff directory and responsive views. All creation requests were mocked.");
} finally {
  await command("Fetch.disable").catch(() => {});
  socket.close();
}

