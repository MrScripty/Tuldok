'use strict';
const fixtureAuth = require('./auth_helpers.cjs').authenticatedFixture();
const fetch = fixtureAuth.fetch;
// Real authored image import, frozen release, edited graph, scratch CPU execution and immutable results.
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
  report = qaDirectory(root, "model-development"),
  temporary = fs.mkdtempSync(path.join(os.tmpdir(), "tuldok-model-development-")),
  children = [];
const sourceHashes=Object.fromEntries(['static/workspace-service.js','static/workspace-real.js','static/workspaces.css','tests/browser_model_development.cjs'].map(file=>[file,require('node:crypto').createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex')]));
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
  let server = launch(
    "python3",
    ["-u", "app.py", "--port", "0", "--data", path.join(temporary, "data")],
    { cwd: root, stdio: ["ignore", "pipe", "pipe"] },
  );
  let output = "";
  server.stdout.on("data", (chunk) => (output += chunk));
  server.stderr.on("data", (chunk) => (serverErrors += chunk));
  const port = await until(() => output.match(/127\.0\.0\.1:(\d+)/)?.[1]),
    base = "http://127.0.0.1:" + port;
  await fixtureAuth.register('http://127.0.0.1:'+port,path.join(temporary,'data'),root);
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
  const focus = (selector, frame = false) =>
    evaluate(`${element(selector, frame)}.focus()`);
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
  await focus('#nav-runs'); await key('Enter');
  await until(() => text('#real-runs-root').then(t => t?.includes('No real runs yet')));
  await focus('#nav-data'); await key('Enter');
  await until(() => evaluate('!document.getElementById("view-data").hidden'));
  check('keyboard navigation reaches honest empty real runs and returns to retained Data');
  const corpus = JSON.parse(execFileSync("python3", ["tests/fixtures/workspaces/image_corpus.py", "--output", path.join(temporary, "imports")], { cwd: root, encoding: "utf8" }));
  async function attachImage(filename) {
    const result = await send("Runtime.evaluate", { expression: `${element("#import-image", true)}` });
    await send("DOM.setFileInputFiles", { files: [filename], objectId: result.result.objectId });
  }
  for (const row of corpus) {
    await click(".embed-toolbar button", true);
    await evaluate(`${element("#import-form", true)}.closest('details').open=true`);
    await fill("#import-group", row.group, true);
    await fill("#rights", "CC0 authored tiny drawing; workflow verification only, no quality claim.", true);
    await attachImage(row.path);
    await focus("#import-form button", true); await key("Enter");
    await until(() => text("#notice", true).then(t => t === "Record imported."));
    await key("Escape");
    await select("#task", "image_classification", true);
    await fill("#label", row.label, true);
    await select("#record-review", "human_reviewed", true);
    await focus("#save", true); await key("Enter");
    await until(() => evaluate(`${doc(true)}.defaultView.TuldokWorkspaceData.snapshot().dirty===false`));
  }
  const collection = await (await fetch(base + "/api/workbench/records")).json();
  assert.equal(collection.items.length, 12);
  assert.ok(collection.items.every(row => row.review === "human_reviewed"));
  check("12 authored independent images imported, labelled and explicitly reviewed using Data controls");
  await click("#select-page", true);
  await click(".embed-toolbar button", true);
  await evaluate(`${element("#release-form", true)}.closest('details').open=true`);
  await select("#release-format", "image_classification_v1", true);
  await fill("#train", "100", true); await fill("#validation", "0", true); await fill("#test", "0", true);
  await click("#preview-release", true);
  await until(() => evaluate(`${doc(true)}.defaultView.eval('releaseBusy')===false`));
  assert.equal(await evaluate(`${element("#freeze-release", true)}.disabled`), true);
  check("invalid held-out class coverage blocks release before training");
  await fill("#train", "50", true); await fill("#validation", "25", true); await fill("#test", "25", true);
  for (let seed = 42; seed < 75; seed++) {
    await fill("#split-seed", String(seed), true);
    await click("#preview-release", true);
    await until(() => evaluate(`${doc(true)}.defaultView.eval('releaseBusy')===false`));
    if (!await evaluate(`${element("#freeze-release", true)}.disabled`)) break;
  }
  assert.equal(await evaluate(`${element("#freeze-release", true)}.disabled`), false, "Corrected independent family split has all-class coverage");
  await click("#freeze-release", true);
  await until(() => evaluate(`!!${doc(true)}.querySelector('#release-result a')`));
  const download = await evaluate(`${doc(true)}.querySelector('#release-result a').href`),
    releaseBytes = Buffer.from(await (await fetch(download)).arrayBuffer()),
    releaseId = /([a-f0-9]{64})/.exec(download)[1];
  fs.writeFileSync(path.join(report, "authored-image-release.zip"), releaseBytes);
  await key("Escape");
  await screenshot("catalog-data-1440", 1440, 900);
  await screenshot("catalog-data-390", 390, 844);
  await send("Emulation.setDeviceMetricsOverride", { width:1440,height:900,deviceScaleFactor:1,mobile:false });
  check("fixed split preview, exact reviewed source release and immutable ZIP download");
  await nav('pipeline');
  await until(()=>evaluate('!!document.getElementById("model-prepare")'));
  async function configure(name,release,width=8,epochs=3){
    await fill('#model-name',name);await select('#model-release',release);
    for(let i=0;i<3;i++)await fill('#model-width-'+i,String(width*(i+1)));
    await select('#model-size','32');await fill('#model-epochs',String(epochs));
  }
  async function train(name,release,width=8,epochs=3){
    await configure(name,release,width,epochs);
    const before=(await(await fetch(base+'/api/workspace/runs')).json()).length;
    await focus('#model-prepare');await key('Enter');
    await until(()=>evaluate('!!document.getElementById("model-start")'), 'Finite trial was not prepared');
    assert.equal((await(await fetch(base+'/api/workspace/runs')).json()).length,before,'Preparation is inert');
    assert.equal(await evaluate('document.querySelector("#model-width-0").matches(":disabled")'),true);
    await screenshot('prepared-'+name+'-1440',1440,900);
    await screenshot('prepared-'+name+'-390',390,844);
    await focus('#model-start');await key('Enter');
    await until(()=>evaluate('!document.getElementById("view-runs").hidden'));
    await until(()=>text('#real-run-state').then(value=>['completed','failed','unknown'].includes(value)), 'Actual CPU worker did not finish');
    assert.equal(await text('#real-run-state'),'completed',await text('#real-runs-root'));
    await until(()=>evaluate('document.querySelectorAll("[data-model-checkpoint]").length>=2'));
    const run=(await(await fetch(base+'/api/workspace/runs')).json()).find(item=>item.graph.name===name);
    assert.ok(run);return run;
  }
  const run=await train('First TinyCNN',releaseId),predictionURL=base+'/api/workspace/runs/'+run.id+'/predictions?split=validation',
    originalPredictions=await(await fetch(predictionURL)).json();
  const query=async(id,body={})=>{
    const sha=await evaluate('WorkspaceModelContracts["runs.model_evidence"]');
    const response=await fetch(base+'/api/workspace/runs/'+id+'/model-evidence',{method:'POST',headers:{'Content-Type':'application/json','Tuldok-Operation-Contract':'runs.model_evidence/1/'+sha},body:JSON.stringify(body)});
    assert.equal(response.status,200);return response.json();
  };
  const evidence=await query(run.id);
  assert.equal(evidence.state,'verified');assert.equal(evidence.checkpoint_index.entries.length,3);
  assert.equal(evidence.observations.length,9);
  assert.equal(run.test_exposure.exposed,false);
  const example=originalPredictions.rows[0];await select('#model-probe',example.id);
  for(const entry of evidence.checkpoint_index.entries){
    await focus('[data-model-checkpoint="'+entry.checkpoint.sha256+'"]');await key('Enter');
    await until(()=>evaluate(`document.querySelector('[data-model-checkpoint="${entry.checkpoint.sha256}"]').getAttribute('aria-pressed')==='true'`));
    assert.equal(await evaluate('document.getElementById("model-probe").value'),example.id,'Probe selection persists across checkpoints');
    const epoch=await query(run.id,{checkpoint_sha256:entry.checkpoint.sha256});
    assert.equal(epoch.predictions.rows.length,evidence.probe.members.length);
    assert.equal(epoch.checkpoint.clocks.epoch,entry.clocks.epoch);
    const weights=await fetch(base+'/api/workspace/runs/'+run.id+'/artifacts/'+epoch.checkpoint.weights.name);
    assert.equal(weights.status,200);assert.equal(require('node:crypto').createHash('sha256').update(Buffer.from(await weights.arrayBuffer())).digest('hex'),epoch.checkpoint.weights.sha256);
  }
  const selectedEntry=evidence.checkpoint_index.entries.find(item=>item.selected);
  await focus('[data-model-checkpoint="'+selectedEntry.checkpoint.sha256+'"]');await key('Enter');
  await until(()=>evaluate(`(()=>{const checkpoint=document.querySelector('[data-model-checkpoint="${selectedEntry.checkpoint.sha256}"]'),candidate=document.getElementById('model-select-candidate');return checkpoint?.getAttribute('aria-pressed')==='true'&&candidate&&!candidate.disabled;})()`),'The selected checkpoint candidate control did not become ready');
  await focus('#model-select-candidate');
  assert.equal(await evaluate('document.activeElement.id'),'model-select-candidate','Keyboard activation must focus the enabled candidate control');
  await key('Enter');
  await until(()=>text('.model-candidate').then(value=>value?.includes('Diagnostic candidate retained')));
  assert.match(await text('.model-candidate'),/no quality threshold/);
  check('Selected checkpoint candidate is retained as diagnostic with separate unfulfilled package and fresh-verifier states');
  await screenshot('linked-evidence-1440',1440,900);await screenshot('linked-evidence-390',390,844);
  check('H1 real finite training produces three checkpoint/probe sets; keyboard epoch selection preserves exact example; test remains locked');
  // Hold a real evidence response after dispatch, then navigate away.
  await send('Fetch.enable',{patterns:[{urlPattern:base+'/api/workspace/runs/'+run.id+'/model-evidence',requestStage:'Response'}]});
  pausedRequest=null;await click('[data-model-checkpoint="'+evidence.checkpoint_index.entries[0].checkpoint.sha256+'"]');
  await until(()=>pausedRequest);await nav('pipeline');
  await send('Fetch.continueRequest',{requestId:pausedRequest});await send('Fetch.disable');pausedRequest=null;
  assert.equal(await evaluate('document.getElementById("view-runs").hidden'),true);
  await until(()=>evaluate('!!document.getElementById("model-new")'));await click('#model-new');
  const second=await train('Second TinyCNN',releaseId,12,2);
  async function compareTo(other,evidence,mode='paired'){
    await select('#model-compare-run',other.id);
    const checkpoint=evidence.checkpoint_index.entries.find(item=>item.selected).checkpoint.sha256;
    await until(()=>evaluate(`!!document.querySelector('#model-compare-checkpoint option[value="${checkpoint}"]')`));
    await select('#model-compare-checkpoint',checkpoint);await select('#model-compare-metric','loss');await select('#model-compare-mode',mode);
    await focus('#model-compare');await key('Enter');
  }
  await compareTo(run,evidence);
  await until(()=>text('.model-evidence').then(value=>value?.includes('Identical compatible validation membership')));
  check('Compatible frozen validation membership supports measured comparison across actual trained models');
  // The correction bridge opens the current record from frozen model probes.
  await click('[data-real-run="'+run.id+'"]');await until(()=>evaluate('!!document.getElementById("model-probe")'));
  await select('#model-probe',example.id);await focus('#model-correct');await key('Enter');
  await until(()=>evaluate('!document.getElementById("view-data").hidden'));
  assert.match(await text('#real-correction-context'),/Frozen target/);
  await fill('#label',example.truth_label==='circle'?'square':'circle',true);
  await select('#record-review','human_reviewed',true);await focus('#save',true);await key('Enter');
  await until(()=>evaluate(`${doc(true)}.defaultView.TuldokWorkspaceData.snapshot().dirty===false`));
  await until(()=>text('#real-correction-context').then(value=>value?.includes('Current annotation r'+(example.revision+1))));
  await screenshot('current-correction-1440',1440,900);
  await click('#clear-selection',true);await click('#select-page',true);await click('.embed-toolbar button',true);
  await evaluate(`${element('#release-form',true)}.closest('details').open=true`);
  await select('#release-format','image_classification_v1',true);
  await fill('#train','50',true);await fill('#validation','25',true);await fill('#test','25',true);
  for(let seed=42;seed<100;seed++){
    await fill('#split-seed',String(seed),true);await click('#preview-release',true);
    await until(()=>evaluate(`${doc(true)}.defaultView.eval('releaseBusy')===false`));
    if(!await evaluate(`${element('#freeze-release',true)}.disabled`))break;
  }
  assert.equal(await evaluate(`${element('#freeze-release',true)}.disabled`),false);await click('#freeze-release',true);
  await until(async()=>{const href=await evaluate(`${doc(true)}.querySelector('#release-result a')?.href`);return href&&href!==download;});
  const correctedDownload=await evaluate(`${doc(true)}.querySelector('#release-result a').href`),correctedId=/([a-f0-9]{64})/.exec(correctedDownload)[1];
  await key('Escape');await nav('pipeline');await click('#real-refresh');
  await until(()=>evaluate('!!document.getElementById("model-new")'));await click('#model-new');
  const third=await train('Corrected TinyCNN',correctedId,8,2);
  await compareTo(run,evidence);
  await until(()=>text('.model-evidence').then(value=>value?.includes('paired delta is unavailable')));
  await select('#model-compare-mode','side_by_side');await focus('#model-compare');await key('Enter');
  await until(()=>text('.model-comparison-result').then(value=>value?.includes('Side-by-side values are shown without a paired delta')));
  assert.equal(await evaluate('document.querySelector(".model-comparison-result").innerText.includes("Paired delta:")'),false);
  assert.ok(compareRequests.length>=3);assert.ok(compareRequests.every(body=>body.checkpoint_sha256&&body.other_checkpoint_sha256&&body.evaluation_sha256&&body.other_evaluation_sha256&&body.metric_definition_sha256&&body.other_metric_definition_sha256&&body.metric_id==='loss'));
  check('Exact comparison requests bind both evaluations/checkpoints/metric definitions and explicit paired or side-by-side mode');
  assert.deepEqual(Buffer.from(await(await fetch(download)).arrayBuffer()),releaseBytes);
  const revisedPredictions=await(await fetch(predictionURL)).json();
  assert.deepEqual(revisedPredictions.rows.map(row=>row.frozen_reference),originalPredictions.rows.map(row=>row.frozen_reference));
  assert.equal(revisedPredictions.rows.find(row=>row.id===example.id).truth_label,example.truth_label);
  assert.deepEqual(await query(run.id),evidence);
  check('H4 keyboard model-probe correction creates reviewed current revision, new release and trained trial; original evidence is immutable; changed membership refuses paired deltas');
  // Simulated revoked response checks projection, while backend access tests own actual permission enforcement.
  await send('Fetch.enable',{patterns:[{urlPattern:base+'/api/workspace/runs/'+third.id+'/model-evidence',requestStage:'Response'}]});
  pausedRequest=null;await click('[data-model-checkpoint]');await until(()=>pausedRequest);
  await send('Fetch.fulfillRequest',{requestId:pausedRequest,responseCode:403,responseHeaders:[{name:'Content-Type',value:'application/json'}],body:Buffer.from(JSON.stringify({error:'Evidence access revoked',code:'forbidden'})).toString('base64')});
  await send('Fetch.disable');pausedRequest=null;
  await until(()=>text('.model-evidence').then(value=>value?.includes('Evidence access revoked')));
  assert.equal(await evaluate('document.querySelectorAll("[data-model-checkpoint]").length'),0);
  assert.equal(await evaluate('!!document.getElementById("model-probe")'),false);
  await click('#real-runs-refresh');await until(()=>evaluate('document.querySelectorAll("[data-model-checkpoint]").length===2'));
  check('H5 delayed query cannot override navigation; denied evidence clears checkpoint/probe values and explicit refresh recovers');
  await screenshot('corrected-evidence-390',390,844);await screenshot('corrected-evidence-1440',1440,900);
  // Native system preference, keyboard focus and real retained evidence at both requested widths.
  await send('Emulation.setEmulatedMedia',{features:[{name:'prefers-color-scheme',value:'dark'}]});
  const darkChecks=[];
  for(const width of [1440,390]){
    await send('Emulation.setDeviceMetricsOverride',{width,height:width===390?844:900,deviceScaleFactor:1,mobile:false});
    await focus('[data-model-checkpoint]');await key('Tab');
    const colors=await evaluate(`(()=>{const el=document.activeElement,c=getComputedStyle(el),p=getComputedStyle(document.querySelector('.model-evidence')),body=getComputedStyle(document.body);return {dark:matchMedia('(prefers-color-scheme:dark)').matches,focus:el.id,outline:c.outlineStyle,outlineWidth:c.outlineWidth,outlineColor:c.outlineColor,text:p.color,background:body.backgroundColor};})()`);
    const luminance=color=>{const channels=color.match(/[0-9.]+/g).slice(0,3).map(v=>{v=Number(v)/255;return v<=0.04045?v/12.92:((v+0.055)/1.055)**2.4;});return channels[0]*0.2126+channels[1]*0.7152+channels[2]*0.0722;};
    const ratio=(a,b)=>(Math.max(luminance(a),luminance(b))+0.05)/(Math.min(luminance(a),luminance(b))+0.05);
    colors.textContrast=ratio(colors.text,colors.background);colors.focusContrast=ratio(colors.outlineColor,colors.background);
    assert.ok(colors.dark&&colors.textContrast>=4.5&&colors.focusContrast>=3&&colors.outline!=='none'&&parseFloat(colors.outlineWidth)>=2,JSON.stringify(colors));
    darkChecks.push({width,...colors});await screenshot('dark-linked-evidence-'+width,width,width===390?844:900);
  }
  check('Automatic dark workspace preference has visible keyboard focus, measured text/focus contrast and bounded 1440/390 evidence layout');
  assert.deepEqual(errors,[]);assert.ok(!serverErrors.includes('Traceback'),serverErrors);
  fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify({source_commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),dirty:!!execFileSync('git',['status','--porcelain'],{cwd:root,encoding:'utf8'}).trim(),command:'node tests/browser_model_development.cjs',source_sha256:sourceHashes,dark_checks:darkChecks,catalog_path:path.join(temporary,'data'),browser:(await send('Browser.getVersion')).product,checks,captures,compare_selectors:compareRequests,run_ids:[run.id,second.id,third.id],release_ids:[releaseId,correctedId],training:true,quality_claim:false,fixture_provenance:'12 CC0 authored independent images imported and reviewed through ordinary Data UI',access_projection_test:'403 transport substitution; backend tests own actual revoke enforcement'},null,2));
  console.log('PASS real model development gate:',report);
})().catch(async error=>{
  console.error(error);console.error('Application stderr:',serverErrors);
  if(evaluate)try{console.error(await evaluate('JSON.stringify({url:location.href,status:document.getElementById("workspace-status")?.textContent,body:document.body.innerText.slice(-9000),frame:document.getElementById("catalog-frame")?.contentDocument?.body.innerText.slice(-2000)})'));}catch{}
  process.exitCode=1;
}).finally(()=>{if(ws)ws.close();for(const child of children.reverse())child.kill('SIGTERM');});
