/* global process, WebSocket */
// Launch an isolated browser and run mocked suites sequentially. No live mutations.
import { spawn } from "node:child_process";
import { mkdirSync, openSync, closeSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
const artifacts = resolve(".ui-check"); mkdirSync(artifacts, { recursive: true });
const binary = process.env.BROWSER_PATH || "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const port = Number(process.env.QA_DEBUG_PORT || 9223);
const debuggerUrl = `http://127.0.0.1:${port}`;
let existingDebugger = false;
try { existingDebugger = (await fetch(debuggerUrl + "/json/version", { signal: AbortSignal.timeout(500) })).ok; } catch { /* port is unused */ }
if (existingDebugger) { console.error("A debugger is already running on this port. Choose an unused QA_DEBUG_PORT; this runner only closes its own browser."); process.exit(1); }
const logPath = resolve(artifacts, `qa-browser-${Date.now()}.log`);
const log = openSync(logPath, "a");
const browser = spawn(binary, ["--headless=new", "--disable-gpu", "--disable-extensions", "--disable-background-networking", "--no-first-run", "--no-default-browser-check", `--remote-debugging-port=${port}`, `--user-data-dir=${resolve(artifacts, "qa-profile-" + Date.now())}`, "about:blank"], { windowsHide: true, stdio: ["ignore", log, log] });
let spawnError;
browser.on("error", error => { spawnError = error; });
let probe, browserSocket;
async function connection(url) {
  const ws = new WebSocket(url);
  await new Promise((ok, bad) => {
    const timer = setTimeout(() => bad(Error("DevTools connection timed out")), 8000);
    ws.addEventListener("open", () => { clearTimeout(timer); ok(); }, { once: true });
    ws.addEventListener("error", () => { clearTimeout(timer); bad(Error("DevTools connection failed")); }, { once: true });
  });
  return ws;
}
try {
  let version;
  for (let n = 0; n < 40; n++) {
    if (spawnError) throw spawnError;
    try { version = await (await fetch(debuggerUrl + "/json/version", { signal: AbortSignal.timeout(500) })).json(); break; } catch { /* wait for this browser */ }
    await new Promise(ok => setTimeout(ok, 250));
  }
  if (!version) throw Error("Browser did not expose DevTools within 30 seconds");
  browserSocket = await connection(version.webSocketDebuggerUrl);
  const target = await (await fetch(debuggerUrl + "/json/new?about:blank", { method: "PUT", signal: AbortSignal.timeout(3000) })).json();
  probe = await connection(target.webSocketDebuggerUrl);
  await new Promise((ok, bad) => {
    const timer = setTimeout(() => bad(Error("Page.enable timed out: browser renderer is unavailable before app navigation")), 8000);
    probe.addEventListener("message", event => { const value = JSON.parse(event.data); if (value.id === 1) { clearTimeout(timer); if (value.error) bad(Error(value.error.message)); else ok(); } });
    probe.send(JSON.stringify({ id: 1, method: "Page.enable" }));
  });
  probe.close();
  for (const script of ["staff-management-browser-check.mjs", "staff-browser-check.mjs", "admin-documents-browser-check.mjs", "admin-workspace-browser-check.mjs", "browser-check.mjs"]) {
    console.log("Running " + script);
    const child = spawn(process.execPath, ["tests/" + script], { windowsHide: true, stdio: "inherit", env: { ...process.env, CHROME_DEBUG_URL: debuggerUrl } });
    const code = await new Promise((ok, bad) => { child.on("exit", ok); child.on("error", bad); });
    if (code !== 0) throw Error(script + " failed; remaining suites were not run");
  }
  console.log("All five mocked browser suites passed.");
} catch (error) {
  console.error("Browser QA incomplete: " + error.message);
  console.error("Browser diagnostics: " + logPath);
  console.error(readFileSync(logPath, "utf8").split(/\r?\n/).filter(line => /FATAL|GPU process|Access is denied|DevTools listening/.test(line)).slice(-6).join("\n"));
  process.exitCode = 1;
} finally {
  probe?.close();
  if (browserSocket?.readyState === WebSocket.OPEN) {
    browserSocket.send(JSON.stringify({ id: 99, method: "Browser.close" }));
    browserSocket.close();
  }
  browser.kill();
  closeSync(log);
}
