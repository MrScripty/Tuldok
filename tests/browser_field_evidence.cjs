'use strict';
const fixtureAuth = require('./auth_helpers.cjs').authenticatedFixture();
const fetch = fixtureAuth.fetch;
// Read-only native field inspection from a real qualified external Study Run receipt.
// No producer execution, admission, array fixture, or injected successful evidence is used here.
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
  report = qaDirectory(root, "external-field-evidence"),
  temporary = fs.mkdtempSync(path.join(os.tmpdir(), "tuldok-field-evidence-")),
  children = [];
const sourceHashes=Object.fromEntries(['static/workspace-service.js','static/workspace-real.js','static/workspaces.css','tests/browser_field_evidence.cjs'].map(file=>[file,require('node:crypto').createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex')]));
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
  assert.ok(process.env.TULDOK_FIELD_BROWSER_RECEIPT,'Provide a real external Study qualification receipt');
  const sourceReceipt=JSON.parse(fs.readFileSync(process.env.TULDOK_FIELD_BROWSER_RECEIPT,'utf8'));
  const data=sourceReceipt.catalog_path,sourceRun=sourceReceipt.run_id;
  assert.ok(data&&sourceRun,'The real receipt must retain catalog_path and run_id');
  const projectRoots=sourceReceipt.project_roots||{};
  const server=launch('python3',['-u','app.py','--port','0','--data',data,...Object.entries(projectRoots).flatMap(([alias,directory])=>['--project-root',alias+'='+directory])],{cwd:root,stdio:['ignore','pipe','pipe']});
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
    if(name.includes('field'))await evaluate('document.querySelector(".field-evidence")?.scrollIntoView({block:"start"})');
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
  const initialRuns=await(await fetch(base+'/api/workspace/runs')).json();
  await until(()=>evaluate(`!!document.querySelector('[data-real-run="${sourceRun}"]')`));
  await click('[data-real-run="'+sourceRun+'"]');
  await until(()=>evaluate('!!document.getElementById("field-prediction")'),'The real Run did not expose retained field evidence');
  const pin=await evaluate('WorkspaceModelContracts["runs.model_evidence/2"]');
  async function query(body){const response=await fetch(base+'/api/workspace/runs/'+sourceRun+'/model-evidence',{method:'POST',headers:{'Content-Type':'application/json','Tuldok-Operation-Contract':'runs.model_evidence/2/'+pin},body:JSON.stringify(body)});assert.equal(response.status,200,await response.clone().text());return response.json();}
  const index=await query({});assert.equal(index.state,'verified');assert.ok(index.fields.length&&index.checkpoint_index.entries.length&&index.probe.members.length);
  const exactRequests=[];
  for(const entry of index.checkpoint_index.entries){
    await select('#field-checkpoint',entry.checkpoint.sha256);
    for(const member of index.probe.members){
      await select('#field-member',String(member.ordinal));
      const fields=index.fields.filter(item=>item.checkpoint_sha256===entry.checkpoint.sha256&&item.member_ordinal===member.ordinal);
      for(const field of fields){
        await select('#field-stage',field.stage);await select('#field-id',field.field_id);
        for(const axis of ['z','y','x']){
          await select('#field-axis',axis);
          const sliceIndex=field.shape_zyx['zyx'.indexOf(axis)]-1;
          await fill('#field-index',String(sliceIndex));await key('Tab');
          await until(()=>text('.field-evidence').then(value=>value?.includes('Standalone slice '+axis.toUpperCase()+' '+sliceIndex)));
          const body={checkpoint_sha256:entry.checkpoint.sha256,member_ordinal:member.ordinal,field_id:field.field_id,axis,index:sliceIndex,split:'validation'},result=await query(body),value=result.field;
          exactRequests.push(body);assert.equal(value.time_units,'not_applicable');assert.match(value.gauge_policy_sha256,/^[a-f0-9]{64}$/);
          assert.ok((await text('.field-metadata')).includes(value.gauge_policy_sha256));assert.deepEqual(await evaluate('JSON.parse(document.getElementById("field-gauge-policy").textContent)'),value.gauge_policy);
          assert.equal(await evaluate('document.getElementById("field-checkpoint").value'),body.checkpoint_sha256);
          const row=value.prediction.length-1,column=value.prediction[0].length-1;
          await fill('#field-probe-row',String(row));await fill('#field-probe-column',String(column));
          const sample=await text('#field-probe-value');
          assert.ok(sample.includes(String(value.prediction[row][column]))&&sample.includes(String(value.reference[row][column])),sample);
          assert.ok(sample.includes(value.units));
          const boxes=await evaluate(`['prediction','reference'].map(key=>{const c=document.getElementById('field-'+key),r=c.getBoundingClientRect();return {width:r.width,height:r.height,columns:c.width,rows:c.height,hidden:c.hidden,aria:c.getAttribute('aria-label')};})`);
          assert.equal(boxes[0].width,boxes[1].width);assert.equal(boxes[0].height,boxes[1].height);assert.equal(boxes[0].columns,value.prediction[0].length);assert.equal(boxes[0].rows,value.prediction.length);
          if(boxes.some(box=>box.hidden))assert.match(await text('.field-evidence'),/cannot be represented at this viewport resolution/);
          else assert.ok(boxes.every(box=>box.aria.includes('Shared display grayscale range')));
        }
      }
    }
  }
  assert.equal(await evaluate('!!document.getElementById("field-frame")'),false);
  assert.match(await text('.field-evidence'),/Difference unavailable|Physical acceptance is not established/);
  check('H3 real retained checkpoints, fixed members, declared stages and all orthogonal slices drive exact numeric probes with shared display and physical scales');
  await screenshot('linked-field-1440',1440,900);await screenshot('linked-field-390',390,844);
  await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-color-scheme',value:'dark'}]});
  const darkChecks=[];
  for(const width of [1440,390]){
    await send('Emulation.setDeviceMetricsOverride',{width,height:width===390?844:900,deviceScaleFactor:1,mobile:false});
    await focus('#field-checkpoint');await key('Tab');
    const style=await evaluate(`(()=>{const c=getComputedStyle(document.activeElement),p=getComputedStyle(document.querySelector('.field-evidence'));return {preference:matchMedia('(prefers-color-scheme:dark)').matches,focus:document.activeElement.id,outline:c.outlineStyle,outlineWidth:c.outlineWidth,color:p.color};})()`);
    assert.ok(style.preference&&style.outline!=='none'&&parseFloat(style.outlineWidth)>=2,JSON.stringify(style));darkChecks.push({width,...style});
    await screenshot('dark-linked-field-'+width,width,width===390?844:900);
  }
  await send('Fetch.enable',{patterns:[{urlPattern:base+'/api/workspace/runs/'+sourceRun+'/model-evidence',requestStage:'Response'}]});
  pausedRequest=null;await select('#field-axis','z');await until(()=>pausedRequest);await nav('pipeline');await send('Fetch.continueRequest',{requestId:pausedRequest});await send('Fetch.disable');
  assert.equal(await evaluate('document.getElementById("view-runs").hidden'),true);
  await nav('runs');await until(()=>evaluate('!!document.getElementById("field-prediction")'));
  await send('Fetch.enable',{patterns:[{urlPattern:base+'/api/workspace/runs/'+sourceRun+'/model-evidence',requestStage:'Response'}]});
  pausedRequest=null;await select('#field-axis','y');await until(()=>pausedRequest);
  await send('Fetch.fulfillRequest',{requestId:pausedRequest,responseCode:403,responseHeaders:[{name:'Content-Type',value:'application/json'}],body:Buffer.from(JSON.stringify({error:'Field evidence access denied',code:'forbidden'})).toString('base64')});await send('Fetch.disable');
  await until(()=>text('.field-evidence').then(value=>value?.includes('Field evidence access denied')));
  assert.equal(await evaluate('!!document.getElementById("field-prediction")'),false);assert.equal(await evaluate('!!document.getElementById("field-checkpoint")'),false);
  await click('#real-runs-refresh');await until(()=>evaluate('!!document.getElementById("field-prediction")'));
  check('H6 standalone physical geometry, explicit unsupported difference/test/physical acceptance and late/denied-query exclusion remain honest');
  const finalRuns=await(await fetch(base+'/api/workspace/runs')).json();assert.deepEqual(finalRuns.map(item=>item.id).sort(),initialRuns.map(item=>item.id).sort(),'Field inspection must not admit or execute another Run');
  assert.ok(posts.every(url=>url.endsWith('/model-evidence')),'Read-only field inspection used a mutation route');
  assert.deepEqual(errors,[]);assert.ok(!serverErrors.includes('Traceback'),serverErrors);
  fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify({source_commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),source_sha256:sourceHashes,command:'node tests/browser_field_evidence.cjs',catalog_path:data,run_id:sourceRun,source_receipt:path.resolve(process.env.TULDOK_FIELD_BROWSER_RECEIPT),browser:(await send('Browser.getVersion')).product,checks,captures,dark_checks:darkChecks,exact_requests:exactRequests,producer_execution:false,existing_actual_run:true,quality_claim:false,access_projection_test:'403 transport substitution; backend tests own actual current authority enforcement'},null,2));
  console.log('PASS actual external field browser:',report);
})().catch(async error=>{
  console.error(error);console.error('Application stderr:',serverErrors);
  if(evaluate)try{console.error(await evaluate('document.body.innerText.slice(-9000)'));}catch{}
  process.exitCode=1;
}).finally(()=>{if(ws)ws.close();for(const child of children.reverse())child.kill('SIGTERM');});
