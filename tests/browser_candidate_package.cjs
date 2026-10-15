'use strict';
const fixtureAuth = require('./auth_helpers.cjs').authenticatedFixture();
const fetch = fixtureAuth.fetch;
// Actual package/fresh-consumer UI from a retained real training receipt.
// Runtime configuration and inventory are explicit; no injected completion or artifact rows.
"use strict";
const assert = require("node:assert/strict"),
  fs = require("node:fs"),
  os = require("node:os"),
  path = require("node:path");
const { spawn, execFileSync } = require("node:child_process");
const { pageLoadTracker } = require("./browser_page_load.cjs");
const tracker = pageLoadTracker();
const { waitForDebugger } = require("./browser_startup.cjs");
const { qaDirectory, screenshotOptions } = require("./qa_artifacts.cjs");
const root = path.resolve(__dirname, ".."),
  report = qaDirectory(root, "candidate-package"),
  temporary = fs.mkdtempSync(path.join(os.tmpdir(), "tuldok-candidate-package-")),
  children = [];
const sourceHashes=Object.fromEntries(['static/workspace-service.js','static/workspace-real.js','static/workspaces.css','candidate_packages.py','tests/browser_candidate_package.cjs'].map(file=>[file,require('node:crypto').createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex')]));
const errors = [],
  posts = [],
  captures = [],
  checks = [], compareRequests = [];
let ws, send, evaluate, serverErrors = "";
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function until(fn, message = "Timed out") {
  for (let i = 0; i < 1800; i++) {
    const result = await fn();
    if (result) return result;
    await pause(100);
  }
  throw Error(message);
}
function launch(command, args, options) {
  const child = spawn(command, args, options);
  children.push(child);
  return child;
}
(async () => {
  const sourceReceipt=JSON.parse(fs.readFileSync(process.env.TULDOK_MODEL_BROWSER_RECEIPT,'utf8'));
  assert.ok(sourceReceipt.catalog_path&&sourceReceipt.run_ids?.[0],'Use the completed real model browser receipt');
  const data=sourceReceipt.catalog_path,projectRoot=path.join(temporary,'projects');fs.mkdirSync(projectRoot);
  assert.ok(process.env.TULDOK_PACKAGE_RUNTIME_CONFIG&&/^[a-f0-9]{64}$/.test(process.env.TULDOK_PACKAGE_RUNTIME_INVENTORY||''),'Supply the reviewed captured CPU runtime configuration and exact inventory SHA');
  console.log('Capturing the explicitly selected runtime in the stopped browser catalog…');
  const runtime=JSON.parse(execFileSync('python3',['runtime_snapshots.py','create','--data',data,'--config',process.env.TULDOK_PACKAGE_RUNTIME_CONFIG,'--expected-inventory-sha256',process.env.TULDOK_PACKAGE_RUNTIME_INVENTORY,'--quiesced'],{cwd:root,encoding:'utf8',timeout:300000}));
  fs.writeFileSync(path.join(report,'runtime.json'),JSON.stringify(runtime,null,2));
  let server = launch(
    "python3",
    ["-u", "app.py", "--port", "0", "--data", data,"--project-root","qa="+projectRoot],
    { cwd: root, stdio: ["ignore", "pipe", "pipe"] },
  );
  let output = "";
  server.stdout.on("data", (chunk) => (output += chunk));
  server.stderr.on("data", (chunk) => (serverErrors += chunk));
  const port = await until(() => output.match(/127\.0\.0\.1:(\d+)/)?.[1]),
    base = "http://127.0.0.1:" + port;
  await fixtureAuth.register('http://127.0.0.1:'+port,data,root);
  const browser = launch(
    process.env.BROWSER || "/usr/bin/chromium",
    [
      ...(process.env.TULDOK_NATIVE_ZOOM ? [] : ["--headless"]),
      "--no-sandbox",
      "--disable-gpu",
      "--no-first-run",
      "--no-default-browser-check",
      "--remote-debugging-port=0",
      "--window-size=1440,900",
      "--user-data-dir=" + path.join(temporary, "browser"),
      "about:blank",
    ],
    {
      stdio: ["ignore", "ignore", "ignore"],
      env: {
        ...process.env,
        XDG_CONFIG_HOME: temporary,
        XDG_CACHE_HOME: temporary,
      },
    },
  );
  const debugPort = await waitForDebugger(
    browser,
    path.join(temporary, "browser", "DevToolsActivePort"),
  );
  const target = await until(async()=>{
    const tabs=await(await fetch("http://127.0.0.1:"+debugPort+"/json")).json();
    return tabs.find(tab=>tab.type==='page'&&tab.url==='about:blank');
  },'Chromium did not expose its initial page');
  assert.ok(target);
  ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.onopen = resolve;
    ws.onerror = reject;
  });
  let id = 0,
    pausedRequest = null, dialog = null;
  const pending = new Map();
  send = (method, params = {}) =>
    new Promise((resolve, reject) => {
      const key = ++id,
        timer = setTimeout(() => {
          pending.delete(key);
          reject(Error("CDP timeout " + method));
        }, 45000);
      pending.set(key, {
        resolve: (r) => {
          clearTimeout(timer);
          resolve(r);
        },
        reject: (e) => {
          clearTimeout(timer);
          reject(e);
        },
      });
      ws.send(JSON.stringify({ id: key, method, params }));
    });
  ws.onmessage = (event) => {
    const m = JSON.parse(event.data);
    tracker.observe(m);
    if (m.method === "Page.javascriptDialogOpening") dialog = m.params;
    if (m.id) {
      const p = pending.get(m.id);
      if (!p) return;
      pending.delete(m.id);
      m.error ? p.reject(m.error) : p.resolve(m.result);
    }
    if (m.method === "Runtime.exceptionThrown")
      errors.push(m.params.exceptionDetails);
    if (
      m.method === "Network.requestWillBeSent" &&
      m.params.request.method === "POST"
    )
      posts.push(m.params.request.url);
    if(m.method==="Network.requestWillBeSent"&&m.params.request.url.endsWith("/compare-model-evidence")&&m.params.request.postData)compareRequests.push(JSON.parse(m.params.request.postData));
    if (m.method === "Fetch.requestPaused") pausedRequest = m.params.requestId;
  };
  evaluate = async (expression) => {
    const r = await send("Runtime.evaluate", {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });
    if (r.exceptionDetails) throw Error(JSON.stringify(r.exceptionDetails));
    return r.result.value;
  };
  const doc = (frame) =>
    frame
      ? 'document.getElementById("catalog-frame").contentDocument'
      : "document";
  const element = (selector, frame = false) =>
    `${doc(frame)}.querySelector(${JSON.stringify(selector)})`;
  const text = (selector, frame = false) =>
    evaluate(`${element(selector, frame)}?.textContent`);
  async function click(selector, frame = false) {
    await evaluate("new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))");
    const box = await evaluate(
      `(()=>{const el=${element(selector, frame)};if(!el)throw Error('Missing '+${JSON.stringify(selector)});el.scrollIntoView({block:'center'});const r=el.getBoundingClientRect(),f=${frame ? 'document.getElementById("catalog-frame").getBoundingClientRect()' : "{left:0,top:0}"};return {x:r.x+r.width/2+f.left,y:r.y+r.height/2+f.top};})()`,
    );
    await send("Input.dispatchMouseEvent", {
      type: "mousePressed",
      button: "left",
      clickCount: 1,
      ...box,
    });
    await send("Input.dispatchMouseEvent", {
      type: "mouseReleased",
      button: "left",
      clickCount: 1,
      ...box,
    });
  }
  async function key(key, code = key, modifiers = 0) {
    await send("Input.dispatchKeyEvent", {
      type: "keyDown",
      key,
      code,
      modifiers,
      ...(key === "Enter" ? { text: "\r", unmodifiedText: "\r" } : {}),
      windowsVirtualKeyCode:
        {
          Enter: 13,
          Tab: 9,
          Escape: 27,
          ArrowDown: 40,
          ArrowUp: 38,
          Home: 36,
          End: 35,
        }[key] || 0,
    });
    await send("Input.dispatchKeyEvent", {
      type: "keyUp",
      key,
      code,
      modifiers,
    });
  }
  async function fill(selector, value, frame = false) {
    await click(selector, frame);
    await send("Input.dispatchKeyEvent", {
      type: "keyDown",
      key: "a",
      code: "KeyA",
      modifiers: 2,
      windowsVirtualKeyCode: 65,
    });
    await send("Input.dispatchKeyEvent", {
      type: "keyUp",
      key: "a",
      code: "KeyA",
      modifiers: 2,
    });
    await send("Input.insertText", { text: String(value) });
  }
  const select = (selector, value, frame = false) =>
    evaluate(
      `(()=>{const el=${element(selector, frame)};el.value=${JSON.stringify(value)};el.dispatchEvent(new Event('change',{bubbles:true}));})()`,
    );
  const focus = async (selector, frame = false) => {
    await until(()=>evaluate(`!!${element(selector, frame)}&&!${element(selector, frame)}.disabled`),'Native control did not become enabled: '+selector);
    await evaluate(`${element(selector, frame)}.focus()`);
  };
  async function nav(name) {
    // Activate the native anchor after viewport changes; original M1 gate and
    // the keyboard checks below separately exercise physical Enter navigation.
    await evaluate(`document.getElementById('nav-${name}').click()`);
    await until(() => evaluate(`!document.getElementById('view-${name}').hidden`));
    await evaluate("window.scrollTo(0,0)");
  }
  const check = (name) => {
    checks.push(name);
    console.log("PASS", name);
  };
  async function screenshot(name, width, height) {
    await send("Emulation.setDeviceMetricsOverride", {
      width,
      height,
      deviceScaleFactor: 1,
      mobile: false,
    });
    await evaluate("window.scrollTo(0,0)");
    if(name.startsWith("prepared"))await evaluate('document.querySelector("#real-model-root").scrollIntoView({block:"start"})');
    if(name.includes("evidence"))await evaluate('document.querySelector(".model-evidence").scrollIntoView({block:"start"})');
    if(name.startsWith("package")||name.startsWith("fresh"))await evaluate('document.querySelector(".model-export")?.scrollIntoView({block:"start"})');
    if (name.startsWith("catalog"))
      await evaluate(
        'document.getElementById("catalog-frame").contentWindow.scrollTo(0,0)',
      );
    await evaluate("document.fonts.ready.then(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))))");
    assert.ok(
      await evaluate("document.documentElement.scrollWidth<=innerWidth+1"),
      "Whole-page overflow " + name,
    );
    const result = await send("Page.captureScreenshot", screenshotOptions);
    const filename = name + ".jpg";
    fs.writeFileSync(
      path.join(report, filename),
      Buffer.from(result.data, "base64"),
    );
    captures.push({
      file: filename,
      width,
      height,
      mode: "real execution on explicitly authored CC0 inputs; no model-quality claim",
      quality: 85,
    });
  }
  async function reload() {
    const previous = (await send("Page.getFrameTree")).frameTree.frame;
    await send("Page.reload");
    await until(
      () => tracker.reloaded(previous),
      "Fresh main document did not finish reloading",
    );
  }
  await send("Page.enable");
  await send("Page.setLifecycleEventsEnabled", { enabled: true });
  await send("Runtime.enable");
  await send("Network.enable");

  const offlineCanary = process.env.LD_PRELOAD ? JSON.parse(execFileSync("python3", ["-c", "import sys;sys.path.insert(0,'tests');from test_workspace_offline import CANARY;exec(CANARY)"], {cwd:root,encoding:"utf8"})) : null;
  await send("DOM.enable");
  await fixtureAuth.browser(send,'http://127.0.0.1:'+port);
  await send("Page.navigate", { url: base + "/workspaces" });
  await until(() => evaluate('!!document.getElementById("fixture-label")'));
  await select("#dataset", "catalog");
  await until(() => text("#notice", true).then(t => t === "Collection ready."));
  await nav('runs');
  const sourceRun=process.env.TULDOK_MODEL_BROWSER_RUN_ID||sourceReceipt.run_ids[0];assert.ok(sourceReceipt.run_ids.includes(sourceRun),'Choose a real Run from the supplied model receipt');
  await until(()=>evaluate(`!!document.querySelector('[data-real-run="${sourceRun}"]')`));
  await click('[data-real-run="'+sourceRun+'"]');
  await until(()=>evaluate('!!document.getElementById("model-select-candidate")'));
  await focus('#model-select-candidate');await key('Enter');
  await until(()=>text('.model-candidate').then(value=>value?.includes('Diagnostic candidate retained')));
  await until(()=>evaluate('!!document.getElementById("model-export-setup")'));
  await focus('#model-export-setup');await key('Enter');
  await until(()=>evaluate('!!document.getElementById("model-export-form")'));
  const operationRuns=[];
  async function operation(mode){
    await select('#model-export-mode',mode);await select('#model-export-root','qa');
    await fill('#model-export-directory','browser-'+mode);await fill('#model-export-runtime',runtime.manifest_sha256);
    const before=(await(await fetch(base+'/api/workspace/runs')).json()).length;
    await focus('#model-export-prepare');await key('Enter');
    await until(()=>evaluate('!!document.getElementById("model-export-approve")'),'Exact operation preparation failed');
    assert.equal((await(await fetch(base+'/api/workspace/runs')).json()).length,before,'Preparation must not execute');
    await screenshot('package-prepared-'+mode+'-1440',1440,900);await screenshot('package-prepared-'+mode+'-390',390,844);
    await focus('#model-export-approve');await key('Enter');
    await until(()=>evaluate('!!document.getElementById("model-export-start")'),'Exact operation approval failed');
    assert.equal((await(await fetch(base+'/api/workspace/runs')).json()).length,before,'Approval must not execute');
    await focus('#model-export-start');await key('Enter');
    await until(()=>evaluate(`(()=>{const item=document.querySelector('[data-real-run][aria-current="true"]');return item&&item.dataset.realRun!==${JSON.stringify(sourceRun)};})()`),'The admitted operation did not become the selected Run');
    await until(()=>text('#real-run-state').then(value=>['completed','failed','unknown'].includes(value)),'Approved operation did not finish');
    assert.equal(await text('#real-run-state'),'completed',await text('#real-runs-root'));
    const admittedId=await evaluate("document.querySelector('[data-real-run][aria-current=true]').dataset.realRun"),run=await(await fetch(base+'/api/workspace/runs/'+admittedId)).json();
    assert.ok(run);assert.ok(run.study_membership,'The operation must remain under Study admission');operationRuns.push(run.id);
    await click('[data-real-run="'+sourceRun+'"]');
    await until(()=>evaluate('!!document.getElementById("model-export-refresh")'));
    await focus('#model-export-refresh');await key('Enter');
    await until(()=>text('.model-export').then(value=>mode==='package'?value?.includes('Package: complete'):value?.includes('Fresh inference: verified')));
    return run;
  }
  const packageRun=await operation('package');
  assert.match(await text('.model-export'),/Fresh inference: not verified/);
  await screenshot('package-complete-1440',1440,900);await screenshot('package-complete-390',390,844);
  // A new operation requires its own explicit preparation and exact approval.
  if(await evaluate('!!document.getElementById("model-export-setup")')){await focus('#model-export-setup');await key('Enter');}
  await until(()=>evaluate('!!document.getElementById("model-export-next")'));
  await focus('#model-export-next');await key('Enter');
  await until(()=>evaluate('!!document.getElementById("model-export-form")'));
  const verificationRun=await operation('verifier');
  await screenshot('fresh-verified-1440',1440,900);await screenshot('fresh-verified-390',390,844);
  await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-color-scheme',value:'dark'}]});
  const darkChecks=[];
  for(const width of [1440,390]){
    await send('Emulation.setDeviceMetricsOverride',{width,height:width===390?844:900,deviceScaleFactor:1,mobile:false});
    await focus('#model-export-refresh');await key('Tab');
    const colors=await evaluate(`(()=>{const el=document.activeElement,c=getComputedStyle(el),p=getComputedStyle(document.querySelector('.model-export')),surface=getComputedStyle(document.querySelector('.model-export').closest('.panel'));return {dark:matchMedia('(prefers-color-scheme:dark)').matches,focus:el.id,outline:c.outlineStyle,outlineWidth:c.outlineWidth,outlineColor:c.outlineColor,text:p.color,background:surface.backgroundColor};})()`);
    const luminance=color=>{const channels=color.match(/[0-9.]+/g).slice(0,3).map(v=>{v=Number(v)/255;return v<=0.04045?v/12.92:((v+0.055)/1.055)**2.4;});return channels[0]*0.2126+channels[1]*0.7152+channels[2]*0.0722;};
    const ratio=(a,b)=>(Math.max(luminance(a),luminance(b))+0.05)/(Math.min(luminance(a),luminance(b))+0.05);
    colors.textContrast=ratio(colors.text,colors.background);colors.focusContrast=ratio(colors.outlineColor,colors.background);
    assert.ok(colors.dark&&colors.textContrast>=4.5&&colors.focusContrast>=3&&colors.outline!=='none'&&parseFloat(colors.outlineWidth)>=2,JSON.stringify(colors));
    darkChecks.push({width,...colors});await screenshot('fresh-dark-verified-'+width,width,width===390?844:900);
  }
  const counts=(await(await fetch(base+'/api/workspace/studies/'+packageRun.study_membership.study_id,{headers:{'Tuldok-Operation-Contract':'studies.get/1/'+await evaluate('WorkspaceModelContracts["studies.get"]')}})).json()).charged;
  assert.equal(counts.attempt_slots,3,'Training, package and verifier consume exactly three finite slots');
  assert.equal(posts.filter(url=>url.endsWith('/runs/submit-external')).length,0,'No standalone submission may bypass Study accounting');
  const packageArtifact=packageRun.artifacts.find(item=>item.name==='package.zip'),response=await fetch(base+'/api/workspace/runs/'+packageRun.id+'/artifacts/package.zip');assert.equal(response.status,200);
  const raw=Buffer.from(await response.arrayBuffer());assert.equal(require('node:crypto').createHash('sha256').update(raw).digest('hex'),packageArtifact.sha256);
  fs.writeFileSync(path.join(report,'package.zip'),raw);
  check('Actual package preparation and exact approval are inert; Study-admitted packaging and a separate captured CPU consumer complete with three charged slots');
  check('Package complete and fresh inference verified are distinct UI states; the source candidate remains diagnostic');
  assert.deepEqual(errors,[]);assert.ok(!serverErrors.includes('Traceback'),serverErrors);
  fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify({source_commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),dirty:!!execFileSync('git',['status','--porcelain'],{cwd:root,encoding:'utf8'}).trim(),command:'node tests/browser_candidate_package.cjs',source_sha256:sourceHashes,dark_checks:darkChecks,catalog_path:data,source_model_receipt:path.resolve(process.env.TULDOK_MODEL_BROWSER_RECEIPT),runtime_snapshot_sha256:runtime.manifest_sha256,browser:(await send('Browser.getVersion')).product,checks,captures,source_run_id:sourceRun,package_run_id:packageRun.id,verification_run_id:verificationRun.id,package_sha256:packageArtifact.sha256,charged:counts,quality_claim:false},null,2));
  console.log('PASS actual candidate package browser:',report);
})().catch(async error=>{
  console.error(error);console.error('Application stderr:',serverErrors);
  if(evaluate)try{console.error(await evaluate('document.body.innerText.slice(-9000)'));}catch{}
  process.exitCode=1;
}).finally(()=>{if(ws)ws.close();for(const child of children.reverse())child.kill('SIGTERM');});
