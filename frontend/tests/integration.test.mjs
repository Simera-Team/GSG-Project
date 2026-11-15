/* global process */
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import ts from "typescript";
const root = resolve(dirname(fileURLToPath(import.meta.url)), "../src");
const cache = new Map();
function load(relative) {
  const path = resolve(root, relative);
  if (cache.has(path)) return cache.get(path).exports;
  const source = readFileSync(path, "utf8").replace("import.meta.env.VITE_API_BASE_URL", "undefined");
  const { outputText } = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } });
  const module = { exports: {} };
  cache.set(path, module);
  new Function("exports", "module", "require", outputText)(module.exports, module, dependency => load(resolve(dirname(path), dependency + ".ts")));
  return module.exports;
}
const store = new Map();
globalThis.sessionStorage = { getItem: key => store.get(key) ?? null, setItem: (key,value) => store.set(key,value), removeItem: key => store.delete(key) };
globalThis.window = new EventTarget();
const session = load("services/session.ts");
const api = load("services/apiClient.ts");
const files = load("services/fileService.ts");
const auth = load("services/authService.ts");
const profile = load("services/profileService.ts");
const workspace = load("services/workspaceService.ts");
const provenance = load("services/provenanceService.ts");
const docs = load("utils/documents.ts");
const dates = load("utils/dateTime.ts");
const json = (body,status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

test("protected requests use the expected endpoint and bearer token", async () => {
  session.setAccessToken("test-token");
  globalThis.fetch = async (url,init) => {
    assert.equal(url, "/api/v1/cv/files/42");
    assert.equal(init.headers.get("Authorization"), "Bearer test-token");
    return json({ file_id: 42, status: "processing" });
  };
  assert.equal((await files.getCandidateFileById(42)).status,"processing");
});
test("only an authenticated HTTP 401 clears the session", async () => {
  for (const status of [403,404,422,429,500]) {
    session.setAccessToken("test-token");
    globalThis.fetch = async () => json({ detail: "SECRET_INTERNAL_MODEL_ERROR" },status);
    await assert.rejects(files.getCandidateFileById(42), error => !api.friendlyError(error).includes("SECRET"));
    assert.equal(session.getAccessToken(),"test-token");
  }
  globalThis.fetch = async () => { throw new Error("SECRET_NETWORK_ERROR"); };
  await assert.rejects(files.getCandidateFileById(42));
  assert.equal(session.getAccessToken(),"test-token");
  globalThis.fetch = async () => json({ detail: "SECRET" },401);
  await assert.rejects(files.getCandidateFileById(42));
  assert.equal(session.getAccessToken(),null);
  assert.match(session.getSessionNotice(), /session has expired/);
});
test("an old unauthorized response cannot invalidate a new login", async () => {
  session.setAccessToken("old-token");
  globalThis.fetch = async () => { session.setAccessToken("new-token"); return json({},401); };
  await assert.rejects(files.getCandidateFileById(42));
  assert.equal(session.getAccessToken(),"new-token");
});
test("login failures do not expire unrelated authentication; no open redirect", async () => {
  session.setAccessToken("test-token");
  globalThis.fetch = async () => json({ detail: "SECRET" },401);
  await assert.rejects(api.apiRequest("/auth/login", { authenticated: false }));
  assert.equal(session.getAccessToken(),"test-token");
  assert.equal(session.safeReturnPath("/files/42?source=profile"),"/files/42?source=profile");
  assert.equal(session.safeReturnPath("//evil.example"),"/workspace");
  assert.equal(session.safeReturnPath("https://evil.example"),"/workspace");
  assert.equal(session.safeReturnPath("/login"),"/workspace");
  assert.equal(session.safeReturnPath("/documents?page=2"),"/documents?page=2");
  assert.equal(session.safeReturnPath(undefined),"/workspace");
  assert.equal(session.safeReturnPath("/workspace"),"/workspace");
  assert.equal(session.safeReturnPath("/upload"),"/upload");
  assert.equal(session.safeReturnPath("/profile#sources"),"/profile#sources");
  assert.equal(session.safeReturnPath("/documents-other"),"/workspace");
});
test("missing profile is an empty profile, malformed JSON is sanitized", async () => {
  session.setAccessToken("test-token");
  globalThis.fetch = async () => json({},404);
  assert.equal(await profile.getMyProfile(),null);
  globalThis.fetch = async () => new Response("SECRET non-JSON response");
  await assert.rejects(files.getCandidateFileById(42), error => !api.friendlyError(error).includes("SECRET"));
  assert.equal(api.friendlyError(new Error("SECRET"),"Friendly fallback"),"Friendly fallback");
});
test("upload retains FormData and duplicate responses without leaking backend messages", async () => {
  session.setAccessToken("test-token");
  globalThis.fetch = async (url,init) => {
    assert.equal(url,"/api/v1/cv/upload");
    assert.equal(init.method,"POST");
    assert.equal(init.body.get("file").name,"resume.md");
    assert.equal(init.headers.has("Content-Type"),false);
    return json({ file_id: 42, duplicate: true, status: "duplicate", message: "SECRET" });
  };
  assert.equal((await files.uploadCandidateFile(new File(["Resume"],"resume.md"))).duplicate,true);
});
test("file validation rejects empty, oversized and unsupported documents", () => {
  assert.equal(docs.validateFile(new File(["resume"],"resume.PDF")),"");
  assert.ok(docs.validateFile(new File([],"resume.pdf")));
  assert.ok(docs.validateFile(new File(["text"],"script.html")));
  assert.ok(docs.validateFile({ name: "big.docx", size: 10 * 1024 * 1024 + 1 }));
  assert.equal(docs.safeWebUrl("javascript:alert(1)"),undefined);
});
function inTimezone(zone, callback) {
  const original = process.env.TZ;
  try { process.env.TZ = zone; callback(); }
  finally { if (original === undefined) delete process.env.TZ; else process.env.TZ = original; }
}
test("UTC timestamps convert to the local timezone with a readable format", () => {
  inTimezone("America/New_York", () => {
    assert.equal(dates.formatTimestamp("2026-11-14T16:52:18.564152Z"),"Nov 14, 2026 at 11:52 AM");
  });
  inTimezone("Asia/Jerusalem", () => {
    assert.equal(dates.formatTimestamp("2026-11-14T16:52:18.564152Z"),"Nov 14, 2026 at 6:52 PM");
  });
});
test("explicit positive and negative offsets describe the same instant", () => {
  inTimezone("UTC", () => {
    const expected="Nov 14, 2026 at 2:52 PM";
    for (const value of ["2026-11-14T16:52:18+02:00","2026-11-14T09:52:18-05:00","2026-11-14T16:52:18+0200","2026-11-14T14:52:18Z"]) {
      assert.equal(dates.formatTimestamp(value),expected);
    }
  });
});
test("naive timestamps retain their supplied clock time in every browser timezone", () => {
  for (const zone of ["UTC","Asia/Jerusalem","America/New_York","Pacific/Auckland"]) {
    inTimezone(zone, () => {
      for (const value of ["2026-11-14T16:52:18.564152","2026-11-14 16:52:18.564152","2026-11-14T16:52"]) {
        assert.equal(dates.formatTimestamp(value),"Nov 14, 2026 at 4:52 PM");
      }
      assert.equal(dates.formatTimestamp("2026-03-08T02:30:00"),"Mar 8, 2026 at 2:30 AM");
      assert.equal(dates.formatTimestamp("2026-11-14T00:00:00"),"Nov 14, 2026 at 12:00 AM");
      assert.equal(dates.formatTimestamp("2026-11-14T12:00:00"),"Nov 14, 2026 at 12:00 PM");
    });
  }
});
test("explicit timestamps follow daylight-saving transitions automatically", () => {
  inTimezone("America/New_York", () => {
    assert.equal(dates.formatTimestamp("2026-03-08T06:30:00Z"),"Mar 8, 2026 at 1:30 AM");
    assert.equal(dates.formatTimestamp("2026-03-08T07:30:00Z"),"Mar 8, 2026 at 3:30 AM");
  });
});
test("invalid, missing and impossible timestamps never expose raw input", () => {
  for (const value of [undefined,null,"","invalidZ","SECRET_BACKEND_DIAGNOSTIC","2026-02-30T12:00:00","2026-02-29T12:00:00Z","2026-11-14T24:00:00","2026-11-14T12:60:00","2026-11-14T12:00:00+24:00","2026-11-14T12:00:00+02:60","2026-11-14"]) {
    assert.equal(dates.formatTimestamp(value),"Not available");
  }
  assert.equal(dates.formatTimestamp("2024-02-29T12:00:00"),"Feb 29, 2024 at 12:00 PM");
  assert.equal(dates.hasTimezone("2026-11-14"),false);
});
test("status-list request keeps pagination, authentication and all backend statuses", async () => {
  session.setAccessToken("test-token");
  const statuses = ["uploaded", "processing", "done", "needs_review", "failed"];
  globalThis.fetch = async (url,init) => {
    assert.equal(url,"/api/v1/cv/files?limit=50&offset=50");
    assert.equal(init.headers.get("Authorization"),"Bearer test-token");
    return json({total:55,limit:50,offset:50,items:statuses.map((status,index) => ({file_id:index+51,status}))});
  };
  const result = await files.getCandidateFiles(50,50);
  assert.deepEqual(result.items.map(file => file.status),statuses);
  for (const status of statuses) {
    assert.ok(docs.statusLabels[status]);
    assert.ok(docs.statusMessage(status));
    assert.equal(docs.statusMessage(status).includes("Processing is complete"),status === "done");
  }
});
test("supported extensions and the exact file-size boundary remain valid", () => {
  for (const name of ["resume.pdf","resume.docx","linkedin.md","RESUME.DOCX"]) {
    assert.equal(docs.validateFile({name,size:10*1024*1024}),"");
  }
  assert.ok(docs.validateFile({name:"resume.pdf",size:10*1024*1024+1}));
  assert.ok(docs.validateFile({name:"resume.pdf.exe",size:100}));
});
test("workspace counts include every document page and keep recent server ordering", async () => {
  session.setAccessToken("test-token");
  const statuses=["uploaded","processing","done","needs_review","failed"];
  const records=Array.from({length:205},(_,index)=>({file_id:205-index,status:statuses[index%5]}));
  const offsets=[];
  globalThis.fetch=async (url,init) => {
    const query=new URL(url,"http://test.invalid").searchParams;
    assert.equal(query.get("limit"),"100");
    assert.equal(init.headers.get("Authorization"),"Bearer test-token");
    const offset=Number(query.get("offset")); offsets.push(offset);
    return json({total:records.length,limit:100,offset,items:records.slice(offset,offset+100)});
  };
  const summary=await workspace.getWorkspaceDocuments();
  assert.equal(summary.total,205);
  assert.deepEqual(offsets,[0,100,200]);
  assert.deepEqual(summary.counts,{uploaded:41,processing:41,done:41,needs_review:41,failed:41});
  assert.deepEqual(summary.recent.map(file=>file.file_id),[205,204,203,202,201]);
});
test("workspace distinguishes an empty account from unavailable or incomplete data", async () => {
  session.setAccessToken("test-token");
  globalThis.fetch=async ()=>json({total:0,limit:100,offset:0,items:[]});
  const summary=await workspace.getWorkspaceDocuments();
  assert.equal(summary.total,0); assert.deepEqual(summary.recent,[]);
  assert.equal(Object.values(summary.counts).reduce((total,value)=>total+value,0),0);
  globalThis.fetch=async ()=>json({detail:"SECRET"},500);
  await assert.rejects(workspace.getWorkspaceDocuments(),error=>!api.friendlyError(error).includes("SECRET"));
  globalThis.fetch=async ()=>json({total:2,limit:100,offset:0,items:[{file_id:1,status:"done"}]});
  await assert.rejects(workspace.getWorkspaceDocuments(),/full document summary/);
});
test("workspace avoids false counts when paginated records change during loading", async () => {
  session.setAccessToken("test-token");
  globalThis.fetch=async url => {
    const offset=Number(new URL(url,"http://test.invalid").searchParams.get("offset"));
    return json(offset === 0 ? {total:101,items:Array.from({length:100},(_,i)=>({file_id:i+1,status:"done"}))} : {total:102,items:[{file_id:101,status:"uploaded"},{file_id:102,status:"uploaded"}]});
  };
  await assert.rejects(workspace.getWorkspaceDocuments(),/list changed/);
});
test("skill source references require canonical file-ID strings, never guessed names or field IDs", async () => {
  assert.deepEqual(provenance.skillSourceFileIds(["42","43","42"]),[42,43]);
  assert.deepEqual(provenance.skillSourceFileIds(["resume.pdf","42.pdf","file:42"," 42 ","042","42.0","0","-1","9007199254740992"]),[]);
  assert.deepEqual(provenance.skillSourceFileIds([42,null,{}]),[]);
  const skill={name:"React",field_ids:[42]};
  globalThis.fetch=async ()=>{throw new Error("No lookup is permitted without source references");};
  const result=await provenance.getSkillSupportingDocuments(skill.sources,[{file_id:42,original_name:"resume.pdf",file_type:"pdf"}]);
  assert.deepEqual(result,{documents:[],unavailableCount:0});
});
test("skill provenance preserves multiple supporting documents without extra cached lookups", async () => {
  globalThis.fetch=async ()=>{throw new Error("Cached metadata should be reused");};
  const known=[{file_id:42,original_name:"resume.pdf",file_type:"pdf"},{file_id:43,original_name:"linkedin.md",file_type:"md"}];
  const result=await provenance.getSkillSupportingDocuments(["42","43","42"],known);
  assert.deepEqual(result.documents,[{fileId:42,name:"resume.pdf",documentType:"PDF"},{fileId:43,name:"linkedin.md",documentType:"MD"}]);
  assert.equal(result.unavailableCount,0);
  assert.equal(JSON.stringify(result).includes("confidence"),false);
});
test("older source metadata is resolved through the authorized candidate file endpoint", async () => {
  session.setAccessToken("test-token");
  globalThis.fetch=async (url,init)=>{
    assert.equal(url,"/api/v1/cv/files/43");
    assert.equal(init.headers.get("Authorization"),"Bearer test-token");
    return json({file_id:43,original_name:"older-resume.docx",file_type:"docx",error_message:"SECRET"});
  };
  const result=await provenance.getSkillSupportingDocuments(["43"],[]);
  assert.deepEqual(result,{documents:[{fileId:43,name:"older-resume.docx",documentType:"DOCX"}],unavailableCount:0});
  assert.equal(JSON.stringify(result).includes("SECRET"),false);
});
test("unavailable and mismatched source metadata cannot create false document links", async () => {
  session.setAccessToken("test-token");
  const known=[{file_id:42,original_name:"resume.pdf",file_type:"pdf"}];
  globalThis.fetch=async url=>url.endsWith("/43") ? json({file_id:99,original_name:"wrong-owner.pdf",file_type:"pdf"}) : json({detail:"SECRET"},404);
  const result=await provenance.getSkillSupportingDocuments(["42","43","9999"],known);
  assert.deepEqual(result,{documents:[{fileId:42,name:"resume.pdf",documentType:"PDF"}],unavailableCount:2});
  assert.equal(JSON.stringify(result).includes("SECRET"),false);
  globalThis.fetch=async ()=>{throw new Error("SECRET_NETWORK_ERROR");};
  assert.deepEqual(await provenance.getSkillSupportingDocuments(["9999"],[]),{documents:[],unavailableCount:1});
  assert.equal(session.getAccessToken(),"test-token");
});
test("mixed unsupported source labels are reported as incomplete rather than guessed", async () => {
  const known=[{file_id:42,original_name:"resume.pdf",file_type:"pdf"}];
  globalThis.fetch=async ()=>{throw new Error("No lookup for filenames is allowed");};
  assert.deepEqual(await provenance.getSkillSupportingDocuments(["42","resume.pdf","resume.pdf"],known),{documents:[{fileId:42,name:"resume.pdf",documentType:"PDF"}],unavailableCount:1});
});
const accountFixture = { user_id: 7, name: "Test Candidate", email: "candidate@example.invalid", role: "candidate" };
const loginFixture = { email: accountFixture.email, password: "test-password" };

test("login keeps its token transient until identity and role are verified", async () => {
  session.setAccessToken("old-session");
  const calls = [];
  globalThis.fetch = async (url, init) => {
    assert.equal(session.getAccessToken(), null, "no partial session during either request");
    calls.push(url);
    if (url.endsWith("/auth/login")) {
      assert.equal(init.headers.has("Authorization"), false);
      return json({ access_token: "verified-token", token_type: "bearer" });
    }
    assert.equal(init.headers.get("Authorization"), "Bearer verified-token");
    return json(accountFixture);
  };
  assert.deepEqual(await auth.authService.signIn(loginFixture), accountFixture);
  assert.deepEqual(calls, ["/api/v1/auth/login", "/api/v1/auth/me"]);
  assert.equal(session.getAccessToken(), "verified-token");
  globalThis.fetch = async () => { throw Error("already verified for this session"); };
  assert.deepEqual(await auth.getVerifiedSessionUser("verified-token"), accountFixture);
});

test("login and identity verification failures never leave a stored token", async () => {
  for (const failureAt of ["login", "me"]) {
    for (const failure of [401, 403, 500, "network", "invalid-json"]) {
      session.setAccessToken("old-session");
      globalThis.fetch = async url => {
        const target = url.endsWith(failureAt === "login" ? "/auth/login" : "/auth/me");
        if (!target) return json({ access_token: "temporary-token" });
        if (failure === "network") throw Error("SECRET_NETWORK");
        if (failure === "invalid-json") return new Response("SECRET_BAD_JSON");
        return json({ detail: "SECRET_SERVER" }, failure);
      };
      await assert.rejects(auth.authService.signIn(loginFixture), error => !api.friendlyError(error).includes("SECRET"));
      assert.equal(session.getAccessToken(), null, failureAt + ":" + failure);
    }
  }
});

test("malformed tokens, identities and unsupported roles cannot establish a session", async () => {
  for (const response of [{}, { access_token: "" }, { access_token: " " }, null]) {
    session.setAccessToken("old-session");
    globalThis.fetch = async () => json(response);
    await assert.rejects(auth.authService.signIn(loginFixture));
    assert.equal(session.getAccessToken(), null);
  }
  for (const user of [null, {}, {...accountFixture, role: "owner"}, {...accountFixture, user_id: "7"}]) {
    globalThis.fetch = async url => json(url.endsWith("/login") ? {access_token:"temporary-token"} : user);
    await assert.rejects(auth.authService.signIn(loginFixture));
    assert.equal(session.getAccessToken(), null);
  }
});

test("verified staff roles cannot use candidate return destinations", async () => {
  for (const role of ["administrator", "reviewer", "candidate"]) {
    globalThis.fetch = async url => json(url.endsWith("/login") ? {access_token:"role-token"} : {...accountFixture, role});
    const user = await auth.authService.signIn(loginFixture);
    assert.equal(user.role, role);
    assert.equal(auth.loginDestination(role, "/documents?page=2"), role === "candidate" ? "/documents?page=2" : "/");
    assert.equal(auth.loginDestination(role, "/profile#skills"), role === "candidate" ? "/profile#skills" : "/");
    assert.equal(auth.loginDestination(role, "https://evil.example"), role === "candidate" ? "/workspace" : "/");
    assert.equal(auth.loginDestination(role, "/dashboard"), role === "candidate" ? "/workspace" : "/");
  }
});

test("a late login response cannot restore a logged-out session or replace a newer login", async () => {
  for (const replacement of [null, "new-session"]) {
    globalThis.fetch = async url => {
      if (url.endsWith("/login")) return json({ access_token: "late-token" });
      if (replacement) session.setAccessToken(replacement); else session.clearSession();
      return json(accountFixture);
    };
    await assert.rejects(auth.authService.signIn(loginFixture), /interrupted/);
    assert.equal(session.getAccessToken(), replacement);
  }
});

test("restored sessions verify roles once and failed verification remains retryable", async () => {
  session.setAccessToken("restored-token");
  let calls = 0;
  globalThis.fetch = async (_url, init) => {
    calls++;
    assert.equal(init.headers.get("Authorization"), "Bearer restored-token");
    return json({...accountFixture, role:"reviewer"});
  };
  const [first, second] = await Promise.all([auth.getVerifiedSessionUser("restored-token"), auth.getVerifiedSessionUser("restored-token")]);
  assert.equal(first.role, "reviewer"); assert.deepEqual(first, second); assert.equal(calls, 1);
  session.setAccessToken("restored-token");
  globalThis.fetch = async () => json({ detail:"SECRET" }, 500);
  await assert.rejects(auth.getVerifiedSessionUser("restored-token"));
  // This is an existing session, not an incomplete login: block navigation and allow retry.
  assert.equal(session.getAccessToken(), "restored-token");
  globalThis.fetch = async () => json(accountFixture);
  assert.equal((await auth.getVerifiedSessionUser("restored-token")).role, "candidate");
});

test("failed-document guidance does not suggest a duplicate upload as a retry", () => {
  assert.match(docs.statusMessage("failed"), /same file again won't restart processing/);
  assert.match(docs.statusMessage("failed"), /CVerge team/);
  assert.doesNotMatch(docs.statusMessage("failed"), /try uploading it again/i);
});
