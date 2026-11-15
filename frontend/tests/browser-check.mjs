/* global process, Buffer */
// Optional browser regression check. Uses a separate headless Chrome and mocks API traffic;
// never creates accounts, uploads documents, or changes records in the real backend.
import assert from "node:assert/strict";
import { mkdirSync, writeFileSync, existsSync, readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";
const frontend = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const artifacts = resolve(frontend, ".ui-check");
mkdirSync(artifacts, { recursive: true });
const downloads = resolve(artifacts, "downloads-" + Date.now());
mkdirSync(downloads, { recursive: true });
const origin = process.env.UI_CHECK_URL || "http://127.0.0.1:5174";
const debuggerUrl = process.env.CHROME_DEBUG_URL || "http://127.0.0.1:9223";
const target = await (await fetch(`${debuggerUrl}/json/new?${encodeURIComponent("about:blank")}`, { method: "PUT" })).json();
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((ok,bad) => { socket.addEventListener("open",ok,{once:true}); socket.addEventListener("error",bad,{once:true}); });
let nextId = 0;
const pending = new Map();
const exceptions = [];
const restrictedCalls = [];
function command(method, params = {}) {
  const id = ++nextId;
  return new Promise((ok,bad) => {
    const timer = setTimeout(() => { pending.delete(id); bad(new Error(`CDP timeout: ${method}`)); }, 15000);
    pending.set(id,{ok,bad,timer}); socket.send(JSON.stringify({id,method,params}));
  });
}
let mode = "normal";
let uploadCalls = 0;
let listCalls = 0;
let fileCalls = 0;
let currentStatus = "processing";
let addedDocument = null;
let slowList = true;
let failList = false;
let authRole = "candidate";
const document = { file_id: 42, original_name: "Candidate-professional-experience-and-qualifications-resume-with-a-long-filename.pdf", file_type: "pdf", status: "processing", extraction_method: null, ocr_confidence: null, error_message: null, uploaded_at: "2026-11-14 16:52:18.564152", finished_at: "2026-11-14T14:52:18.564152Z", attempts: 1, open_reviews: 0 };
const paginatedDocuments = Array.from({length:41}, (_, index) => ({...document,file_id:index+100,original_name:`test-document-${index+100}.pdf`,status:["uploaded","processing","done","needs_review","failed"][index%5]}));
const overviewDocuments = Array.from({length:125},(_,index)=>({...document,file_id:index+2000,original_name:`overview-document-${index+2000}.pdf`,status:["uploaded","processing","done","needs_review","failed"][index%5]}));
const user = { user_id: 7, name: "UI Test Candidate", email: "ui-test@example.invalid", role: "candidate" };
const profile = { profile_id: 7, candidate_name: user.name, candidate_email: user.email, updated_at: "2026-11-14T16:52:18.564152", open_reviews: 2, files: [{...document,status:"needs_review",open_reviews:2}], profile: { personal_info: { first_name: "UI Test", last_name: "Candidate", title: "Frontend engineer", summary: "This is test fixture data used only by the automated browser check.", phone: "+000 000 000", city: "Test city", country: { name: "Test country", code: "XX" }, field_ids: {first_name:42,last_name:43,title:42,email:43,city:42,country:43,summary:42} }, experience: [{ title: "Software engineer", company: "Test organization", start_date: { value: "2023", precision: "year" }, employment_status: "current", description: "Built accessible user interfaces." }], education: [{ degree: "Computer Science", institution: "Test institution", start_date: { value: "2019", precision: "year" }, end_date: { value: "2023", precision: "year" } }], skills: [{ name: "TypeScript", verified: true, sources:["42","43","42"],field_ids:[7001,7002] }, { name: "React",field_ids:[42] }, {name:"Ambiguous skill",sources:["resume.pdf","file:42"],field_ids:[42]}, {name:"Unresolved skill",sources:["9999"],field_ids:[7003]}], certifications: [{ name: "Test certification", issuer: "Test issuer", issue_date: { value: "2025", precision: "year" } }], projects: [{ name: "Test project", tech_stack: ["React"], description: "Automated UI fixture", url: "https://example.invalid/project" }], languages: [{ name: "English", proficiency: "Professional" }], links: [{ type: "Portfolio", url: "https://example.invalid" }] } };
socket.addEventListener("message", async event => {
  const message = JSON.parse(event.data);
  if (message.id) {
    const wait = pending.get(message.id); if (!wait) return;
    clearTimeout(wait.timer); pending.delete(message.id);
    if (message.error) wait.bad(new Error(JSON.stringify(message.error))); else wait.ok(message.result);
  } else if (message.method === "Runtime.exceptionThrown") exceptions.push(message.params.exceptionDetails.text);
  else if (message.method === "Fetch.requestPaused") {
    const { requestId, request } = message.params;
    const path = new URL(request.url).pathname;
    if (path.startsWith("/api/v1/review") || /\/profile\/\d+/.test(path)) restrictedCalls.push(path);
    let status = 200; let body;
    try {
      if (mode === "unauthorized") { status = 401; body = { detail: "SECRET_API_KEY_AND_MODEL_STACK_TRACE" }; }
      else if (mode === "network") { await command("Fetch.failRequest", {requestId,errorReason:"InternetDisconnected"}); return; }
      else if (path.endsWith("/auth/login")) body = { access_token: "browser-test-token", token_type: "bearer" };
      else if (path.endsWith("/auth/register")) body = {...user,created_at:"2026-11-15T00:00:00Z"};
      else if (path.endsWith("/auth/me")) {
        if (mode === "identity-error") { status=500; body={detail:"SECRET_IDENTITY_ERROR"}; }
        else if (mode === "identity-unauthorized") { status=401; body={detail:"SECRET_IDENTITY_ERROR"}; }
        else if (mode === "identity-network") { await command("Fetch.failRequest",{requestId,errorReason:"InternetDisconnected"}); return; }
        else body = {...user,role:mode === "identity-invalid-role" ? "unknown" : authRole};
      }
      else if (path.endsWith("/profile/me")) {
        if (mode === "empty") {status = 404; body = {};}
        else if (mode === "profile-error") {status = 500; body = { detail: "SECRET_API_KEY_AND_MODEL_STACK_TRACE" };}
        else body = profile;
      } else if (path.endsWith("/cv/upload")) {
        uploadCalls++; await new Promise(ok => setTimeout(ok, mode === "new-upload" ? 1200 : 250));
        if (mode === "upload-error") {status = 500; body = {detail: "SECRET_API_KEY_AND_MODEL_STACK_TRACE"};}
        else if (mode === "new-upload") {
          currentStatus = "uploaded";
          addedDocument = {...document, file_id:43, original_name:"resume.md", file_type:"md", attempts:0};
          body = {file_id:43,filename:"resume.md",size:20,status:"uploaded",duplicate:false,message:"SECRET"};
        } else body = {file_id:42,filename:"resume.md",size:20,status:"duplicate",duplicate:true,message:"SECRET"};
      } else if (/\/cv\/files\/\d+$/.test(path)) {
        fileCalls++;
        const id=Number(path.split("/").pop());
        if (id === 9999) { await command("Fetch.fulfillRequest",{requestId,responseCode:404,responseHeaders:[{name:"Content-Type",value:"application/json"}],body:Buffer.from(JSON.stringify({detail:"SECRET"})).toString("base64")}); return; }
        const file=overviewDocuments.find(item => item.file_id === id) || paginatedDocuments.find(item => item.file_id === id) || (id === addedDocument?.file_id ? addedDocument : document);
        body={...file,status:currentStatus,error_message:"SECRET_API_KEY_AND_MODEL_STACK_TRACE"};
      }
      else if (path.endsWith("/cv/files")) {
        listCalls++;
        if (slowList) await new Promise(ok => setTimeout(ok,800));
        if (failList) { status=500; body={detail:"SECRET_API_KEY_AND_MODEL_STACK_TRACE"}; }
        else {
          const all = mode === "empty" ? [] : mode === "pagination" ? paginatedDocuments : mode === "overview" ? overviewDocuments : [...(addedDocument ? [addedDocument] : []), document].map(file => ({...file,status:currentStatus,error_message:"SECRET_API_KEY_AND_MODEL_STACK_TRACE"}));
          const query=new URL(request.url).searchParams;
          const limit=Number(query.get("limit") || 50), offset=Number(query.get("offset") || 0);
          assert.ok(limit > 0 && limit <= 100);
          assert.ok(offset >= 0 && Number.isSafeInteger(offset));
          body={total:all.length,limit,offset,items:all.slice(offset,offset+limit)};
        }
      }
      else {status=404; body={};}
      await command("Fetch.fulfillRequest", {requestId,responseCode:status,responseHeaders:[{name:"Content-Type",value:"application/json"}],body:Buffer.from(JSON.stringify(body)).toString("base64")});
    } catch (error) { exceptions.push(error.message); }
  }
});
async function evaluate(expression) {
  const result = await command("Runtime.evaluate", { expression, returnByValue:true, awaitPromise:true });
  if (result.exceptionDetails) throw new Error(JSON.stringify(result.exceptionDetails));
  return result.result.value;
}
async function until(expression, label, timeout = 15000) {
  const start=Date.now();
  while (Date.now()-start < timeout) {if (await evaluate(`Boolean(${expression})`)) return; await new Promise(ok => setTimeout(ok,100));}
  throw new Error(`Timed out: ${label}`);
}
const text = () => evaluate("document.body.innerText");
async function click(selector) { await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`); }
async function navigate(path) {await evaluate(`history.pushState({},'',${JSON.stringify(path)}); window.dispatchEvent(new PopStateEvent('popstate'))`);}
async function screenshot(name) {
  await evaluate("window.scrollTo(0,0)");
  const result=await command("Page.captureScreenshot", {format:"png",captureBeyondViewport:true});
  writeFileSync(resolve(artifacts,name),Buffer.from(result.data,"base64"));
}
async function width(value) {await command("Emulation.setDeviceMetricsOverride", {width:value,height:1000,deviceScaleFactor:1,mobile:value<600});}
async function noOverflow(label) {assert.ok(await evaluate("document.documentElement.scrollWidth <= innerWidth + 1"),label);}
async function readableDates(selector) {
  const values=await evaluate(`Array.from(document.querySelectorAll(${JSON.stringify(selector)}),element=>element.textContent)`);
  assert.ok(values.length, `date elements exist: ${selector}`);
  for (const value of values) assert.ok(value.includes("Nov 14, 2026 at 4:52 PM"), `consistent readable date in ${selector}: ${value}`);
  assert.equal(await evaluate("/timezone unspecified|timezone information|GMT[+-]|\\d{4}-\\d{2}-\\d{2}[T ]\\d{2}:/.test(document.body.innerText)"),false,"no timestamp diagnostics or raw ISO in the UI");
}
async function fillInputs(values) {
  await evaluate(`{const set=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;for(const [selector,value] of Object.entries(${JSON.stringify(values)})){const input=document.querySelector(selector);set.call(input,value);input.dispatchEvent(new Event('input',{bubbles:true}));}}`);
}
async function signIn() {
  await until("!!document.querySelector('#login-email')","sign-in form");
  await fillInputs({"#login-email":"ui-test@example.invalid","#login-password":"test-password"});
  await click('button[type="submit"]');
}
async function register() {
  await until("!!document.querySelector('#register-name')","registration form");
  await fillInputs({"#register-name":"UI Test Candidate","#register-email":"ui-test@example.invalid","#register-password":"test-password","#register-confirm":"test-password"});
  await click('button[type="submit"]');
  await until("location.pathname === '/login' && document.body.innerText.includes('Account created')","registration continues through sign-in");
  assert.equal(await evaluate("sessionStorage.getItem('access_token')"),null,"registration metadata is not an authentication token");
}
async function overviewLoaded() {
  await until("document.querySelector('.ov-documents-summary .ws-count')?.textContent === '125'","full overview document total");
  await activeNavigation("/workspace");
  assert.match(await text(),/Welcome, UI Test Candidate/);
  for (const status of ["uploaded","processing","done","needs_review","failed"]) {
    assert.equal(await evaluate(`document.querySelector('.ov-status-counts [data-status="${status}"] dd').textContent`),"25");
  }
  assert.equal(await evaluate("document.querySelectorAll('.ov-recent-row').length"),5);
}
async function activeNavigation(path) {
  assert.equal(await evaluate(`document.querySelector('.ws-nav a.active')?.getAttribute('href')`),path);
  assert.equal(await evaluate("document.querySelectorAll('.ws-nav a.active').length"),1);
}
async function documentsLoaded() {
  await until("!!document.querySelector('.up-document-table')", "document library");
  assert.equal(await evaluate("!!document.querySelector('.up-upload')"),false,"Documents has no upload form");
  await activeNavigation("/documents");
  await readableDates(".up-date");
}
async function uploadLoaded() {
  await until("!!document.querySelector('.up-processing .ws-status')", "upload status");
  assert.equal(await evaluate("!!document.querySelector('.up-document-table')"),false,"Upload has no document table");
  await activeNavigation("/upload");
  await readableDates(".up-tracked-date");
  assert.equal(await evaluate("document.querySelector('#latest-upload-heading').textContent"),"Latest Upload");
  assert.equal(await evaluate("!!document.querySelector('.up-steps, .up-live')"),false);
  assert.equal(await evaluate("document.querySelector('.up-processing').textContent.includes('Live updates')"),false);
  assert.equal(await evaluate("document.querySelector('.up-latest-actions a:last-child').getAttribute('href')"),"/documents");
}
try {
  await command("Page.enable"); await command("Runtime.enable");
  await command("Fetch.enable", {patterns:[{urlPattern:"*/api/v1/*"}]});
  await command("Browser.setDownloadBehavior", {behavior:"allow",downloadPath:downloads});
  await command("Emulation.setTimezoneOverride", {timezoneId:"Asia/Jerusalem"});
  await command("Emulation.setEmulatedMedia", {features:[{name:"prefers-reduced-motion",value:"reduce"}]});
  await width(1440); await command("Page.navigate", {url:origin+"/"});
  await until("!!document.querySelector('.home-hero h1')", "landing page");
  assert.equal(await evaluate("document.querySelector('.home-hero-actions a').getAttribute('href')"),"/register");
  assert.equal(await evaluate("document.querySelectorAll('#home-main > section').length"),4,"only the requested hero/how/features/about sections");
  assert.equal(await evaluate("document.querySelectorAll('.home-steps > li').length"),3);
  assert.equal(await evaluate("document.querySelectorAll('.home-features-grid > article').length"),3);
  assert.equal(await evaluate("!!document.querySelector('.home-product-visual, .home-final-cta')"),false,"removed the replacement illustration and extra CTA section");
  assert.deepEqual(await evaluate("Array.from(document.querySelectorAll('.cv-flow-source strong'),element=>element.textContent)"),["Resume","LinkedIn","Assessment"]);
  assert.deepEqual(await evaluate("Array.from(document.querySelectorAll('.cv-flow-wires path'),element=>element.getAttribute('d'))"),["M221 58 C267 58 258 170 322 170","M221 170 H322","M221 282 C267 282 258 170 322 170","M221 58 C267 58 258 170 322 170","M221 170 H322","M221 282 C267 282 258 170 322 170"]);
  assert.equal(await evaluate("document.querySelector('.cv-flow-profile h3').textContent"),"Unified candidate profile");
  assert.match(await evaluate("document.querySelector('.cv-flow-tags').textContent"),/3 sources.*1 to review/);
  assert.match(await evaluate("document.querySelector('.home-original-illustration figcaption').textContent"),/Conceptual illustration.*Assessment inputs are not currently available/);
  assert.equal(await evaluate("getComputedStyle(document.querySelector('.cv-flow-profile')).backgroundColor"),"rgb(16, 59, 72)");
  assert.equal(await evaluate("getComputedStyle(document.querySelector('.cv-flow-wire-moving')).animationName"),"none","original illustration respects reduced motion");
  assert.equal(await evaluate("document.querySelector('.home-sign-in').getAttribute('href')"),"/login");
  assert.equal(await evaluate("document.querySelectorAll('.home-nav-actions a').length"),1);
  assert.equal(await evaluate("document.querySelector('.home-nav-actions a').textContent.trim()"),"Sign In");
  assert.equal(await evaluate("document.querySelector('.home-hero-actions a').textContent.trim()"),"Get Started");
  assert.equal(await evaluate("document.querySelector('.home-hero-actions a:last-child').getAttribute('href')"),"#how-it-works");
  const targets=await evaluate("Array.from(document.querySelectorAll('.home-section-links a'),link=>({hash:link.hash,tag:document.querySelector(link.hash)?.tagName}))");
  assert.deepEqual(targets.map(target=>target.hash),["#how-it-works","#features","#about"]);
  assert.ok(targets.every(target=>target.tag === "SECTION"));
  for (const target of targets) {
    await click(`.home-section-links a[href="${target.hash}"]`);
    await until(`location.hash === ${JSON.stringify(target.hash)}`, "landing anchor " + target.hash);
    assert.ok(await evaluate(`document.querySelector(${JSON.stringify(target.hash)}).getBoundingClientRect().top < innerHeight`));
  }
  const links=await evaluate("Array.from(document.querySelectorAll('.home-page a'),link=>link.getAttribute('href'))");
  for (const href of links) {
    assert.ok(href && href !== "#");
    if (href.startsWith("#")) assert.ok(await evaluate(`!!document.getElementById(${JSON.stringify(href.slice(1))})`));
    else assert.ok(["/","/register","/login"].includes(href),`working landing destination ${href}`);
  }
  await click('.home-hero-actions a[href="/register"]');
  await until("location.pathname === '/register' && !!document.querySelector('form')", "Get Started opens registration");
  await navigate("/"); await until("!!document.querySelector('.home-hero')","home return");
  await click('.home-sign-in');
  await until("location.pathname === '/login' && !!document.querySelector('#login-email')", "Sign In opens login");
  await navigate("/"); await until("!!document.querySelector('.home-hero')","home return");
  for (const size of [320,390,768,1024,1440]) {
    await width(size); await noOverflow(`landing width ${size}`);
    if (size <= 780) {
      assert.equal(await evaluate("getComputedStyle(document.querySelector('#home-navigation')).display"),"none");
      await click('.home-menu-button');
      await until("document.querySelector('.home-menu-button').getAttribute('aria-expanded') === 'true'","mobile menu opens");
      await evaluate("document.querySelector('.home-menu-button').focus()");
      await command("Input.dispatchKeyEvent",{type:"keyDown",key:"Escape",code:"Escape",windowsVirtualKeyCode:27});
      await command("Input.dispatchKeyEvent",{type:"keyUp",key:"Escape",code:"Escape",windowsVirtualKeyCode:27});
      await until("document.querySelector('.home-menu-button').getAttribute('aria-expanded') === 'false'","Escape closes menu");
      assert.equal(await evaluate("document.activeElement === document.querySelector('.home-menu-button')"),true);
      await click('.home-menu-button'); await click('.home-section-links a[href="#about"]');
      assert.equal(await evaluate("document.querySelector('.home-menu-button').getAttribute('aria-expanded')"),"false");
    }
  }
  assert.equal(await evaluate("getComputedStyle(document.documentElement).scrollBehavior"),"auto","reduced motion disables smooth scrolling");
  await width(1440); await screenshot("landing-desktop.png");
  await width(390); await screenshot("landing-mobile.png");
  await evaluate("sessionStorage.setItem('access_token','browser-test-token');window.dispatchEvent(new Event('cverge:session'))");
  await until("document.querySelector('.home-hero-actions a').getAttribute('href') === '/workspace'","authenticated CTA opens workspace");
  assert.equal(await evaluate("document.querySelector('.home-hero-actions a').textContent.trim()"),"Go to Workspace");
  assert.equal(await evaluate("document.querySelectorAll('.home-nav-actions a').length"),1);
  assert.equal(await evaluate("document.querySelector('.home-nav-actions a').textContent.trim()"),"My Workspace");
  assert.equal(await evaluate("document.querySelector('.home-nav-actions a').getAttribute('href')"),"/workspace");
  assert.equal(await evaluate("!!document.querySelector('.home-nav-actions a[href=\"/documents\"]')"),false);
  assert.equal(await evaluate("document.body.innerText.includes('Open Workspace')"),false);
  mode="overview"; slowList=true;
  await click('.home-hero-actions a[href="/workspace"]');
  await until("!!document.querySelector('.ov-documents-summary .ws-skeleton-list')","overview loading state");
  slowList=false; await overviewLoaded();
  assert.deepEqual(await evaluate("Array.from(document.querySelectorAll('.ws-nav a'),link=>[link.textContent.trim(),link.getAttribute('href')])"),[["Overview","/workspace"],["Upload Documents","/upload"],["My Documents","/documents"],["My Profile","/profile"]]);
  await until("document.querySelector('.ov-review-status')?.textContent.includes('2 items awaiting review')","real profile review status");
  await readableDates('.ov-recent-row div > span');
  for (const size of [320,390,768,1024,1440]) { await width(size); await noOverflow(`overview width ${size}`); }
  await screenshot("overview-desktop.png"); await width(390); await screenshot("overview-mobile.png");
  await click('.ov-recent-row');
  await until("document.querySelector('.fd-document-heading h2')?.textContent.includes('overview-document-2000.pdf')","overview recent document details");
  await click('.ws-nav a[href="/workspace"]'); await overviewLoaded();
  await click('.ov-profile a[href="/profile"]'); await until("!!document.querySelector('.pr-overview')","overview to My Profile");
  await click('.ws-nav a[href="/workspace"]'); await overviewLoaded();
  await click('.ws-page-heading a[href="/upload"]'); await uploadLoaded();

  mode="empty"; await click('.ws-nav a[href="/workspace"]');
  await until("!!document.querySelector('.ov-onboarding')","new candidate onboarding");
  assert.match(await text(),/Welcome, UI Test Candidate/);
  assert.equal(await evaluate("!!document.querySelector('.ov-status-counts')"),false);
  assert.equal(await evaluate("document.querySelector('.ov-onboarding .ws-button').textContent.trim()"),"Upload your first document");
  await screenshot("overview-empty-mobile.png");
  await click('.ov-onboarding a[href="/upload"]'); await until("!!document.querySelector('#candidate-file')","first upload action");
  await click('.ws-nav a[href="/workspace"]'); await until("!!document.querySelector('.ov-onboarding')","onboarding return");
  await click('.ws-logout'); await until("location.pathname === '/login'","logout before default login");
  await navigate('/login'); await signIn();
  await until("location.pathname === '/workspace' && !!document.querySelector('.ov-onboarding')","new candidate login defaults to overview");

  mode="overview"; await click('.ws-logout'); await until("location.pathname === '/login'","logout");
  await navigate('/login'); await signIn(); await overviewLoaded();
  failList=true;
  await click('.ov-documents-summary .ws-section-heading button');
  await until("!!document.querySelector('.ws-notice-error') && !document.querySelector('.ov-status-counts')","overview unavailable data");
  assert.equal(await evaluate("!!document.querySelector('.ov-onboarding')"),false,"an API failure is not an empty account");
  assert.equal((await text()).includes('SECRET'),false);
  failList=false; await click('.ws-notice-error button'); await overviewLoaded();
  mode="unauthorized"; await click('.ov-documents-summary .ws-section-heading button');
  await until("location.pathname === '/login' && document.body.innerText.includes('Your session has expired')","overview session expiration");
  assert.equal(await evaluate("history.state.usr.from"),"/workspace");
  mode="overview"; await signIn(); await overviewLoaded();

  await click('.ws-logout'); await until("location.pathname === '/login'","logout before registration");
  mode="empty"; await navigate('/register'); await register(); await signIn();
  await until("location.pathname === '/workspace' && !!document.querySelector('.ov-onboarding')","registration and sign-in open overview");
  await click('.ws-logout'); await until("location.pathname === '/login'","logout before requested destination");
  mode="normal"; await navigate('/files/42');
  await until("location.pathname === '/login' && !!document.querySelector('#login-email')","protected destination sign-in");
  await click('.auth-switch a[href="/register"]'); await register();
  assert.equal(await evaluate("history.state.usr.from"),"/files/42");
  await signIn(); await until("location.pathname === '/files/42' && !!document.querySelector('.fd-document')","registration preserves protected destination");
  await command("Page.addScriptToEvaluateOnNewDocument", {source:`sessionStorage.setItem('access_token','browser-test-token'); window.__urls={created:0,revoked:0}; const create=URL.createObjectURL.bind(URL); const revoke=URL.revokeObjectURL.bind(URL); URL.createObjectURL=(blob)=>{window.__urls.created++;return create(blob)}; URL.revokeObjectURL=(url)=>{window.__urls.revoked++;return revoke(url)};`});
  await width(1440); await command("Page.navigate", {url:origin+"/upload"});
  await uploadLoaded(); slowList=false;
  for (const size of [320,390,768,1024,1440]) { await width(size); await noOverflow(`upload width ${size}`); }
  const fixture=resolve(artifacts,"resume.md"); writeFileSync(fixture,"# Test resume\nAutomated browser fixture.");
  async function selectFile() {
    const dom=await command("DOM.getDocument"); const node=await command("DOM.querySelector", {nodeId:dom.root.nodeId,selector:"#candidate-file"});
    await command("DOM.setFileInputFiles", {nodeId:node.nodeId,files:[fixture]});
    await until("!!document.querySelector('.up-selection')","selected-file preview");
  }
  await selectFile();
  assert.match(await text(),/resume.md/);
  assert.match(await evaluate("fetch(document.querySelector('.up-selection a').href).then(r=>r.text())"),/Test resume/);
  await click('.up-selection a[download]'); await screenshot("upload-desktop.png");
  await click('button[aria-label="Remove selected document"]');
  assert.equal(await evaluate("window.__urls.created === window.__urls.revoked"),true);
  await evaluate(`{const transfer=new DataTransfer();transfer.items.add(new File(['dropped resume'],'dropped.pdf',{type:'application/pdf'}));document.querySelector('.up-dropzone').dispatchEvent(new DragEvent('drop',{bubbles:true,dataTransfer:transfer}));}`);
  await until("document.querySelector('.up-selection')?.textContent.includes('dropped.pdf')","drop selection");
  await selectFile();
  assert.equal(await evaluate("window.__urls.created - window.__urls.revoked"),1);
  mode="upload-error"; await click('.up-submit-row button');
  await until("document.querySelector('.up-upload .ws-notice-error')?.textContent.includes('couldn')","friendly upload failure");
  assert.equal((await text()).includes("SECRET"),false);
  mode="normal"; uploadCalls=0;
  await evaluate("{const button=document.querySelector('.up-submit-row button');button.click();button.click();}");
  await until("document.querySelector('.ws-notice-success')?.textContent.includes('No duplicate')","duplicate feedback");
  assert.equal(uploadCalls,1);
  await selectFile(); mode="new-upload"; uploadCalls=0;
  await click('.up-submit-row button');
  await until("document.querySelector('.up-submit-row button').disabled && document.querySelector('.up-submit-row button').textContent.includes('Uploading')","upload loading state");
  assert.equal(await evaluate("document.querySelector('#candidate-file').disabled"),true);
  await evaluate(`{const transfer=new DataTransfer();transfer.items.add(new File(['first'],'first.pdf'));transfer.items.add(new File(['second'],'second.pdf'));document.querySelector('.up-dropzone').dispatchEvent(new DragEvent('drop',{bubbles:true,dataTransfer:transfer}));}`);
  assert.equal(await evaluate("!!document.querySelector('.up-upload .ws-notice-error')"),false);
  await until("document.querySelector('.ws-notice-success')?.textContent.includes('Your document is saved')","new upload feedback");
  assert.equal(uploadCalls,1);
  await until("document.querySelector('.up-tracked-file')?.textContent.includes('resume.md')","track exactly the uploaded document");
  assert.equal(await evaluate("window.__urls.created === window.__urls.revoked"),true);
  const beforePoll=fileCalls; currentStatus="done"; mode="normal";
  await until("document.querySelector('.up-processing .ws-status')?.textContent.includes('Completed')","uploaded-file status polling",8000);
  assert.ok(fileCalls>beforePoll);
  await width(390); await screenshot("upload-mobile.png");

  slowList=true;
  await click('.ws-page-heading a[href="/documents"]');
  await until("!!document.querySelector('.ws-skeleton-list')","documents loading state");
  slowList=false; await documentsLoaded();
  assert.ok(await evaluate("!!document.querySelector('.up-file-name[href=\"/files/43\"]')"));
  assert.equal(await evaluate("!!document.querySelector('.up-processing')"),false);
  assert.equal(await evaluate("document.querySelectorAll('.up-document-table a[download]').length"),0);
  for (const size of [320,390,768,1024,1440]) { await width(size); await noOverflow(`documents width ${size}`); }
  await screenshot("documents-desktop.png"); await width(390); await screenshot("documents-mobile.png");
  for (const [status,label] of [["uploaded","Uploaded"],["processing","Processing"],["needs_review","Needs review"],["failed","Failed"],["done","Completed"]]) {
    currentStatus=status; await click('.up-documents .ws-section-heading button');
    await until(`document.querySelector('.up-document-table .ws-status')?.textContent.includes(${JSON.stringify(label)})`,`document status ${status}`);
    assert.equal((await text()).includes("SECRET"),false);
    await click('.ws-nav a[href="/upload"]'); await uploadLoaded();
    assert.equal(await evaluate("document.querySelector('.up-current-status .ws-status').textContent.trim()"),label);
    assert.ok(await evaluate("document.querySelector('.up-status-message').textContent.length > 0"));
    assert.equal(await evaluate("document.querySelector('.up-latest-actions a:first-child').getAttribute('href')"),"/files/43","View Details remains available for every backend status");
    await click('.ws-nav a[href="/documents"]'); await documentsLoaded();
  }
  currentStatus="processing"; await click('.up-documents .ws-section-heading button');
  await until("document.querySelector('.up-document-table .ws-status')?.textContent.includes('Processing')","list processing");
  failList=true;
  await until("!!document.querySelector('.up-documents .ws-notice-error')","background list failure",8000);
  assert.ok(await evaluate("!!document.querySelector('.up-document-table')"));
  assert.equal((await text()).includes("SECRET"),false);
  assert.equal(await evaluate("!!sessionStorage.getItem('access_token')"),true);
  failList=false;
  await until("!document.querySelector('.up-documents .ws-notice-error')","background list recovery",8000);
  const beforeListPoll=listCalls; currentStatus="done";
  await until("document.querySelector('.up-document-table .ws-status')?.textContent.includes('Completed')","list status polling",8000);
  assert.ok(listCalls>beforeListPoll);

  mode="pagination"; await click('.up-documents .ws-section-heading button');
  await until("document.querySelectorAll('.up-document-table tbody tr').length === 20","first page of 41 documents");
  assert.match(await text(),/Page 1 of 3/);
  await click('.doc-pagination button:last-child');
  await until("location.search.includes('page=2') && !!document.querySelector('.up-file-name[href=\"/files/120\"]')","second document page");
  await click('.doc-pagination button:last-child');
  await until("document.querySelector('.doc-pagination')?.textContent.includes('Page 3 of 3')","last document page");
  assert.equal(await evaluate("document.querySelectorAll('.up-document-table tbody tr').length"),1);
  assert.equal(await evaluate("document.querySelector('.doc-pagination button:last-child').disabled"),true);
  await click('.doc-pagination button:first-child');
  await until("!!document.querySelector('.up-file-name[href=\"/files/120\"]')","previous document page");
  await evaluate("window.__beforeReload = true");
  await command("Page.reload");
  await until("!window.__beforeReload && document.readyState === 'complete' && !!document.querySelector('.up-document-table')", "documents after hard refresh");
  await documentsLoaded();
  assert.match(await text(),/Page 2 of 3/);
  await click('.up-file-name[href="/files/120"]');
  await until("document.querySelector('.fd-document-heading h2')?.textContent.includes('test-document-120.pdf')","selected file details");
  assert.equal(await evaluate("location.pathname"),"/files/120");
  await readableDates(".fd-details-grid > div:nth-child(3) dd, .fd-details-grid > div:nth-child(4) dd");
  await command("Emulation.setTimezoneOverride",{timezoneId:"America/New_York"});
  await evaluate("window.__beforeTimezoneReload = true");
  await command("Page.reload");
  await until("!window.__beforeTimezoneReload && document.querySelector('.fd-details-grid > div:nth-child(3) dd')?.textContent === 'Nov 14, 2026 at 4:52 PM' && document.querySelector('.fd-details-grid > div:nth-child(4) dd')?.textContent === 'Nov 14, 2026 at 9:52 AM'","details loaded in another timezone");
  await command("Emulation.setTimezoneOverride",{timezoneId:"Asia/Jerusalem"});
  await activeNavigation("/documents");
  await click('.fd-back'); await documentsLoaded();
  assert.equal(await evaluate("location.pathname"),"/documents");

  mode="normal"; await click('.ws-nav a[href="/profile"]');
  await until("!!document.querySelector('.pr-overview')","profile navigation");
  await activeNavigation("/profile");
  assert.match(await text(),/UI Test Candidate/); assert.match(await text(),/2 items need review/);
  await readableDates(".pr-overview-footer > .ws-caption, .pr-source > .ws-caption");
  assert.equal(await evaluate("document.querySelectorAll('.skill-source-trigger').length"),2,"source indicators only for explicit numeric skill references");
  assert.equal(await evaluate("document.querySelectorAll('.pr-identity .skill-source-trigger, .pr-personal .skill-source-trigger, #summary .skill-source-trigger, #experience .skill-source-trigger, #education .skill-source-trigger, #certifications .skill-source-trigger, #projects .skill-source-trigger, #languages .skill-source-trigger, #links .skill-source-trigger').length"),0,"field record IDs do not invent provenance");
  assert.equal(await evaluate("document.querySelector('#skills').textContent.includes('Needs Review')"),false,"file/profile review flags do not mark accepted skills as needing review");
  const metadataBeforeSources=fileCalls;
  await evaluate("document.querySelector('.skill-source-trigger[aria-label=\"View sources for TypeScript\"]').focus()");
  await command("Input.dispatchKeyEvent",{type:"keyDown",key:"Enter",code:"Enter",windowsVirtualKeyCode:13,text:"\r"});
  await command("Input.dispatchKeyEvent",{type:"keyUp",key:"Enter",code:"Enter",windowsVirtualKeyCode:13});
  await until("document.querySelector('dialog[open] .source-document-list')?.children.length === 2","multiple verified supporting sources");
  assert.equal(fileCalls,metadataBeforeSources+1,"only uncached source metadata is fetched on demand");
  assert.equal(await evaluate("document.querySelector('dialog[open] .source-document-list').closest('.pr-tags')"),null,"dialog is isolated from skill-tag styling");
  assert.equal(await evaluate("document.querySelector('dialog[open] .source-profile-value').textContent.includes('TypeScript')"),true);
  assert.match(await evaluate("document.querySelector('dialog[open]').textContent"),/Candidate-professional-experience/);
  assert.match(await evaluate("document.querySelector('dialog[open]').textContent"),/resume.md/);
  assert.deepEqual(await evaluate("Array.from(document.querySelectorAll('dialog[open] .source-document-list a'),link=>link.getAttribute('href'))"),["/files/42","/files/43"]);
  assert.equal(await evaluate("document.querySelector('dialog[open]').contains(document.activeElement)"),true,"native dialog manages keyboard focus");
  for (const size of [320,390,768,1440]) { await width(size); await noOverflow(`source dialog width ${size}`); assert.ok(await evaluate("document.querySelector('dialog[open]').getBoundingClientRect().right <= innerWidth && document.querySelector('dialog[open]').getBoundingClientRect().left >= 0")); }
  await screenshot("profile-sources-desktop.png"); await width(390); await screenshot("profile-sources-mobile.png");
  await command("Input.dispatchKeyEvent",{type:"keyDown",key:"Escape",code:"Escape",windowsVirtualKeyCode:27});
  await command("Input.dispatchKeyEvent",{type:"keyUp",key:"Escape",code:"Escape",windowsVirtualKeyCode:27});
  await until("!document.querySelector('dialog[open]')","Escape closes source details");
  assert.equal(await evaluate("document.activeElement.getAttribute('aria-label')"),"View sources for TypeScript");
  await click('.skill-source-trigger[aria-label="View sources for Unresolved skill"]');
  await until("document.querySelector('dialog[open] .source-unavailable')?.textContent.includes('unavailable')","unknown source metadata stays unavailable");
  assert.equal(await evaluate("document.querySelectorAll('dialog[open] a[href]').length"),0,"unknown source metadata has no invented file link");
  assert.equal(await evaluate("document.querySelector('dialog[open]').textContent.includes('SECRET')"),false);
  await click('dialog[open] .source-close'); await until("!document.querySelector('dialog[open]')","close source details");
  await click('.skill-source-trigger[aria-label="View sources for TypeScript"]');
  await until("document.querySelectorAll('dialog[open] .source-document-list a').length === 2","reopen source details");
  await click('dialog[open] a[href="/files/43"]');
  await until("location.pathname === '/files/43' && document.querySelector('.fd-document-heading h2')?.textContent.includes('resume.md')","source link opens authorized File Details");
  await click('.ws-nav a[href="/profile"]'); await until("!!document.querySelector('.pr-overview')","return to profile after source details");
  for (const size of [320,390,768,1024,1440]) { await width(size); await noOverflow(`profile width ${size}`); }
  await screenshot("profile-desktop.png"); await width(390); await screenshot("profile-mobile.png");
  await click('.pr-source'); await until("!!document.querySelector('.fd-document')","profile source details");
  await screenshot("details-mobile.png");
  assert.equal((await text()).includes("SECRET"),false);
  await click('.fd-back'); await documentsLoaded();
  await click('.ws-page-heading a[href="/upload"]'); await uploadLoaded();

  mode="empty"; await click('.ws-nav a[href="/documents"]');
  await until("document.querySelector('.up-documents .ws-empty')?.textContent.includes('No documents yet')","empty document library");
  assert.equal(await evaluate("!!document.querySelector('#candidate-file')"),false);
  await click('.up-documents .ws-empty a[href="/upload"]');
  await until("!!document.querySelector('#candidate-file')","upload action from empty library");
  await until("document.querySelector('.up-status-empty h3')?.textContent === 'No uploads yet'","Latest Upload empty state");
  assert.equal(await evaluate("document.querySelectorAll('.up-latest-actions a').length"),1,"empty state offers My Documents without an invalid details link");
  assert.equal(await evaluate("!!document.querySelector('.up-document-table')"),false);
  await click('.ws-nav a[href="/profile"]'); await until("!!document.querySelector('.pr-welcome')","empty profile");
  assert.match(await text(),/ui-test@example.invalid/);
  await screenshot("profile-empty-mobile.png");
  mode="profile-error"; await click('.ws-nav a[href="/upload"]'); await uploadLoaded();
  await click('.ws-nav a[href="/profile"]'); await until("!!document.querySelector('.ws-notice-error')","profile failure");
  assert.match(await text(),/UI Test Candidate/); assert.equal((await text()).includes("SECRET"),false);
  mode="normal"; await navigate("/files/invalid"); await until("document.body.innerText.includes('link is invalid')","invalid file link");
  failList=true; await navigate("/documents");
  await until("!!document.querySelector('.up-documents .ws-notice-error')","initial list failure");
  assert.equal(await evaluate("!!document.querySelector('.up-document-table')"),false);
  assert.equal((await text()).includes("SECRET"),false);
  failList=false; await click('.up-documents .ws-notice-error button'); await documentsLoaded();
  mode="network"; await navigate("/upload"); await until("document.body.innerText.includes('Unable to connect')","upload status failure");
  assert.equal(await evaluate("!!sessionStorage.getItem('access_token')"),true);
  mode="normal"; await click('.up-processing .ws-notice-error button'); await uploadLoaded();
  mode="pagination"; await navigate("/documents?page=2"); await documentsLoaded();
  mode="unauthorized"; await click('.up-documents .ws-section-heading button');
  await until("location.pathname === '/login' && !!document.querySelector('#login-email') && document.body.innerText.includes('Your session has expired')","401 redirects to login with expiry notice");
  assert.match(await text(),/Your session has expired/);
  assert.equal(await evaluate("sessionStorage.getItem('access_token')"),null);
  assert.equal((await text()).includes("Log out"),false);
  assert.equal(await evaluate("history.state.usr.from"),"/documents?page=2");
  mode="pagination";
  await evaluate(`{const set=Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set;const email=document.querySelector('#login-email');set.call(email,'ui-test@example.invalid');email.dispatchEvent(new Event('input',{bubbles:true}));const password=document.querySelector('#login-password');set.call(password,'test-password');password.dispatchEvent(new Event('input',{bubbles:true}));}`);
  await click('button[type="submit"]');
  await until("location.pathname === '/documents' && location.search === '?page=2' && !!document.querySelector('.up-document-table')","login returns to document page");
  await click('.ws-logout'); await until("location.pathname === '/login'","logout");
  assert.equal(await evaluate("sessionStorage.getItem('access_token')"),null);
  for (const failure of ["identity-error","identity-unauthorized","identity-network","identity-invalid-role"]) {
    mode=failure; await navigate('/login'); await signIn();
    await until("!!document.querySelector('.auth-error[role=alert]') && !document.querySelector('button[type=submit]').disabled","failed identity verification stays on login");
    assert.equal(await evaluate("sessionStorage.getItem('access_token')"),null,"failed verification does not persist a token");
    assert.equal((await text()).includes("SECRET"),false);
  }
  mode="pagination";
  for (const role of ["administrator", "reviewer"]) {
    authRole=role; await navigate('/login'); await signIn();
    await until("location.pathname === '/' && document.body.innerText.includes('Staff pages are not available')", role + " returns to a truthful account notice");
    assert.equal(await evaluate("document.querySelectorAll('a[href=\"/workspace\"]').length"),0,"staff has no candidate workspace links");
    assert.equal(await evaluate("document.querySelector('.home-hero-actions a').getAttribute('href')"),"/login");
    const beforeList=listCalls, beforeFiles=fileCalls;
    await navigate('/documents?page=2');
    await until("document.body.innerText.includes('This workspace is for candidates')","staff candidate access is blocked");
    assert.equal(await evaluate("!!document.querySelector('.ws-nav')"),false);
    assert.equal(listCalls,beforeList); assert.equal(fileCalls,beforeFiles);
    await click('.page-notice-actions button');
    await until("location.pathname === '/login'","staff can switch accounts");
    assert.equal(await evaluate("sessionStorage.getItem('access_token')"),null);
  }
  authRole="candidate"; await signIn();
  await until("location.pathname === '/documents' && location.search === '?page=2' && !!document.querySelector('.up-document-table')","authorized destination survives account switch");
  // A reload must verify the saved token before mounting any candidate pages.
  mode="identity-error";
  const beforeUnverifiedList=listCalls;
  await command("Page.reload");
  await until("document.body.innerText.includes('verify your account') && !!document.querySelector('.page-notice-actions')","restored-session verification failure");
  assert.equal(await evaluate("!!document.querySelector('.ws-nav')"),false);
  assert.equal(listCalls,beforeUnverifiedList,"unverified session makes no document-list requests");
  mode="pagination"; await click('.page-notice-actions button'); await documentsLoaded();
  await navigate('/dashboard'); await until("location.pathname === '/' && !!document.querySelector('.home-page')","legacy dashboard redirects home");
  await navigate('/unknown/nested/path'); await until("document.body.innerText.includes('404') && document.body.innerText.includes('find that page')","unknown URL has branded not found page");
  for (const size of [320,390,768,1440]) { await width(size); await noOverflow('not found width '+size); }
  await click('.page-notice-actions a'); await until("location.pathname === '/'","not found home link");
  await evaluate("sessionStorage.removeItem('access_token');window.dispatchEvent(new Event('cverge:session'))");
  assert.equal(restrictedCalls.length,0,"candidate profile never probes staff history or review endpoints");
  assert.equal(exceptions.length,0,`No runtime exceptions: ${exceptions.join(', ')}`);
  assert.ok(existsSync(resolve(downloads,"resume.md")));
  assert.match(readFileSync(resolve(downloads,"resume.md"),"utf8"),/Test resume/);
  console.log("Passed: verified login failures, staff role guards, restored sessions, safe redirects, responsive 404, verified skill provenance, multiple sources, lazy metadata lookup, keyboard/mobile dialogs, unavailable source safety, no staff endpoint probes, and existing overview/authentication/upload/document/profile regressions.");
  console.log(`Screenshots: ${artifacts}`);
} finally {
  await command("Fetch.disable").catch(()=>{});
  socket.close();
}