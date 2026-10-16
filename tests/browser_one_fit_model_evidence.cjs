'use strict';
const fixtureAuth = require('./auth_helpers.cjs').authenticatedFixture();
const fetch = fixtureAuth.fetch;
// Actual text/audio Study fixtures and retained Runs; no completed rows or artifacts are injected.
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
  report = qaDirectory(root, "one-fit-model-evidence"),
  temporary = fs.mkdtempSync(path.join(os.tmpdir(), "tuldok-one-fit-browser-")),
  children = [];
const sourceHashes=Object.fromEntries(['static/workspace-service.js','static/workspace-real.js','static/workspaces.css','app.py','pipeline.py','runs.py','experiments.py','model_evidence.py','one_fit_evidence.py','text_training.py','audio_training.py','tests/qualify_one_fit.py','tests/browser_one_fit_model_evidence.cjs'].map(file=>[file,require('node:crypto').createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex')]));
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
  const task = process.env.TULDOK_ONE_FIT_TASK || 'text';
  assert.ok(['text','audio'].includes(task));
  const fixture = path.join(temporary, 'actual-' + task);
  await new Promise((resolve,reject)=>{
    const worker=launch(process.env.TULDOK_TRAINING_PYTHON || 'python3',
      ['tests/qualify_model_development.py','--task',task,'--fixture','tests/fixtures/model_development','--output',fixture],
      {cwd:root,stdio:['ignore','pipe','pipe']});
    let stdout='',stderr='';worker.stdout.on('data',data=>stdout+=data);worker.stderr.on('data',data=>stderr+=data);
    worker.on('error',reject);worker.on('exit',code=>code===0?resolve():reject(Error('Actual fixture failed: '+stdout+stderr)));
  });
  const original=JSON.parse(fs.readFileSync(path.join(fixture,'run.json'))),
    originalEvidence=JSON.parse(fs.readFileSync(path.join(fixture,'evidence.json')));
  checks.push('Actual '+task+' authored fixture ran through authenticated HTTP Study and independent cold reconstruction');
  let server = launch(
    "python3",
    ["-u", "app.py", "--port", "0", "--data", path.join(fixture, "catalog")],
    { cwd: root, stdio: ["ignore", "pipe", "pipe"] },
  );
  let output = "";
  server.stdout.on("data", (chunk) => (output += chunk));
  server.stderr.on("data", (chunk) => (serverErrors += chunk));
  const port = await until(() => output.match(/127\.0\.0\.1:(\d+)/)?.[1]),
    base = "http://127.0.0.1:" + port;
  await fixtureAuth.register('http://127.0.0.1:'+port,path.join(fixture,'catalog'),root);
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
      mode: "real execution on authored mathematical contract fixtures; no model-quality claim",
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


  await send('DOM.enable');
  await fixtureAuth.browser(send,base);
  // Fixture construction uses real public HTTP; browser assertions use ordinary
  // authenticated Runs controls. This does not qualify browser import/model setup.
  const headers=JSON.parse(execFileSync(process.env.TULDOK_TRAINING_PYTHON||'python3',['-c',
    "import agent_api,json;print(json.dumps({op:{str(v):agent_api.selected_header(op,v) for v in agent_api._CONTRACTS[op]} for op in agent_api._CONTRACTS}))"],{cwd:root,encoding:'utf8'}));
  async function api(operation,url,body,version=1){
    const response=await fetch(base+'/api/workspace/'+url,{method:body===undefined?'GET':'POST',
      headers:{'Content-Type':'application/json',...(headers[operation]?.[version]?{'Tuldok-Operation-Contract':headers[operation][version]}:{})},
      ...(body===undefined?{}:{body:JSON.stringify(body)})});
    const value=await response.json();assert.ok(response.ok,JSON.stringify(value));return value;
  }
  async function finished(run){
    return until(async()=>{
      const value=await api('runs.get','runs/'+run.id);
      if(['queued','running','cancelling'].includes(value.state))return null;
      assert.equal(value.state,'completed',JSON.stringify(value));return value;
    },'Actual worker did not complete');
  }
  const definition=(await api('recipes.list','definitions')).recipes.find(item=>item.id===task+'_classification_model_v2');
  const model=await api('models.create','models',definition.model_template);
  const material=await api('models.publish','models/'+model.id+'/publish',{revision:model.revision});
  const graph=await api('graphs.create','graphs',{name:'Second actual '+task+' fit',release_id:original.release_id,recipe:definition.id},3);
  const validation=await api('graphs.validate','graphs/'+graph.id+'/validate',{revision:graph.revision});
  const study=await api('studies.create','studies',{name:'Browser comparison actual fit',policy:validation.selection_policy,
    limits:{attempt_slots:1,admitted_wall_seconds:1000,retained_bytes:268435456,peak_staging_bytes:536870912}});
  const trial=await api('studies.prepare_trial','studies/'+study.id+'/prepare-trial',{request_key:'prepare-browser-onefit',revision:study.revision,
    graph_id:graph.id,graph_revision:graph.revision,model:material.ref,replicate:0});
  let state=(await api('studies.get','studies/'+study.id)).study;
  await api('studies.continue','studies/'+study.id+'/continue',{request_key:'continue-browser-onefit',revision:state.revision,admission_epoch:state.admission_epoch});
  state=(await api('studies.get','studies/'+study.id)).study;
  const admitted=await api('studies.admit','studies/'+study.id+'/admit',{request_key:'admit-browser-onefit',revision:state.revision,
    admission_epoch:state.admission_epoch,trial_id:trial.id});
  const second=await finished(admitted.run),secondEvidence=await api('runs.model_evidence','runs/'+second.id+'/model-evidence',{});
  const legacyGraph=await api('graphs.create','graphs',{name:'Actual legacy '+task+' fit',release_id:original.release_id,recipe:task+'_classification'});
  const legacyValidation=await api('graphs.validate','graphs/'+legacyGraph.id+'/validate',{revision:legacyGraph.revision});
  const legacy=await finished(await api('runs.submit','runs',{request_key:'legacy-browser-onefit',graph_id:legacyGraph.id,
    graph_revision:legacyGraph.revision,validation_token:legacyValidation.validation_token}));
  assert.ok(legacy.metrics.history.length===1);
  check('Second actual Study fit and unchanged legacy recipe fit completed without fixture completion injection');
  await send('Page.navigate',{url:base+'/workspaces'});
  await until(()=>evaluate('!!document.getElementById("fixture-label")'));
  await select('#dataset','catalog');
  await until(()=>text('#notice',true).then(value=>value==='Collection ready.'));
  // Every user action below is a native keyboard activation or selection.
  async function activate(selector){await focus(selector);await key('Enter');}
  async function choose(selector,value){
    const index=await evaluate(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});return [...el.options].findIndex(o=>o.value===${JSON.stringify(value)});})()`);
    assert.ok(index>=0,'Missing native option '+selector+' '+value);
    await focus(selector);await key('Home');for(let i=0;i<index;i++)await key('ArrowDown');await key('Tab');
    await until(()=>evaluate(`document.querySelector(${JSON.stringify(selector)})?.value===${JSON.stringify(value)}`));
  }
  async function openRun(run){
    await activate('#nav-runs');await until(()=>evaluate('!document.getElementById("view-runs").hidden'));
    await until(()=>evaluate(`!!document.querySelector('[data-real-run="${run.id}"]')`));
    await activate('[data-real-run="'+run.id+'"]');
    await until(()=>text('#real-run-state').then(value=>value==='completed'));
  }
  await openRun(original);
  await until(()=>text('.model-evidence').then(value=>value?.includes('Linked fit evidence')));
  const entry=originalEvidence.checkpoint_index.entries[0];
  assert.equal(originalEvidence.checkpoint_index.entries.length,1);
  assert.equal(entry.clocks.fit_pass,1);assert.equal(entry.clocks.epoch,null);assert.equal(entry.clocks.optimizer_update,null);
  assert.equal('history' in original.metrics,false);
  const checkpoint=await api('runs.model_evidence','runs/'+original.id+'/model-evidence',{checkpoint_sha256:entry.checkpoint.sha256});
  const weights=await fetch(base+'/api/workspace/runs/'+original.id+'/artifacts/'+checkpoint.checkpoint.weights.name);
  assert.equal(weights.status,200);const retained=Buffer.from(await weights.arrayBuffer());
  assert.equal(retained.length,checkpoint.checkpoint.weights.bytes);
  assert.equal(require('node:crypto').createHash('sha256').update(retained).digest('hex'),checkpoint.checkpoint.weights.sha256);
  const testArtifacts=original.artifacts.filter(item=>item.split==='test');
  assert.ok(testArtifacts.length>0&&testArtifacts.every(item=>item.locked));
  for(const artifact of testArtifacts)assert.equal((await fetch(base+artifact.url)).status,409);
  assert.equal(original.test_exposure.exposed,false);
  const viewportChecks=[];
  for(const width of [1440,390]){
    await send('Emulation.setDeviceMetricsOverride',{width,height:width===390?844:900,deviceScaleFactor:1,mobile:false});
    await activate('[data-model-checkpoint="'+entry.checkpoint.sha256+'"]');
    await until(()=>evaluate(`document.querySelector('[data-model-checkpoint="${entry.checkpoint.sha256}"]')?.getAttribute('aria-pressed')==='true'`));
    assert.equal(await evaluate('document.querySelectorAll("[data-model-checkpoint]").length'),1);
    assert.match(await text('[data-model-checkpoint]'),/Fit pass 1/);
    assert.doesNotMatch(await text('.model-evidence'),/Epoch [0-9]|[0-9] updates/);
    assert.equal(await evaluate('document.querySelectorAll(".model-evidence svg,.model-evidence canvas").length'),0);
    await focus('[data-model-checkpoint]');await key('Tab');
    const focusState=await evaluate(`(()=>{const e=document.activeElement,c=getComputedStyle(e);return {tag:e.tagName,id:e.id,text:e.textContent.slice(0,80),outline:c.outlineStyle,width:c.outlineWidth};})()`);
    assert.ok(focusState.outline!=='none'&&parseFloat(focusState.width)>=2,JSON.stringify(focusState));
    viewportChecks.push({width,focus:focusState});await screenshot(task+'-linked-fit-evidence-'+width,width,width===390?844:900);
  }
  check('Linked Fit pass 1 stays a single checkpoint without epoch/update curve at1440/390; retained whole weights hash matches; test artifacts stay locked');
  await choose('#model-compare-run',second.id);
  const other=secondEvidence.checkpoint_index.entries[0];
  await until(()=>evaluate(`!!document.querySelector('#model-compare-checkpoint option[value="${other.checkpoint.sha256}"]')`));
  await choose('#model-compare-checkpoint',other.checkpoint.sha256);await choose('#model-compare-metric','loss');await choose('#model-compare-mode','paired');
  await activate('#model-compare');
  await until(()=>text('.model-comparison-result').then(value=>value?.includes('Exact paired comparison is available')));
  assert.match(await text('.model-comparison-result'),/Paired delta: 0/);
  assert.equal(compareRequests.length,1);
  const selected=compareRequests[0];
  assert.equal(selected.checkpoint_sha256,entry.checkpoint.sha256);assert.equal(selected.other_checkpoint_sha256,other.checkpoint.sha256);
  assert.equal(selected.evaluation_sha256,original.artifacts.find(item=>item.name==='model-evidence.json').sha256);
  assert.equal(selected.other_evaluation_sha256,second.artifacts.find(item=>item.name==='model-evidence.json').sha256);
  assert.equal(selected.metric_definition_sha256,originalEvidence.metric_definition_hashes.loss);
  assert.equal(selected.other_metric_definition_sha256,secondEvidence.metric_definition_hashes.loss);
  assert.equal(selected.metric_id,'loss');assert.equal(selected.mode,'paired');
  await screenshot(task+'-exact-comparison-evidence-390',390,844);
  check('Native keyboard comparison binds both checkpoints/evaluations/metric definitions and shows actual zero paired delta');
  const example=checkpoint.predictions.rows[0], member=originalEvidence.probe.members.find(item=>item.ordinal===example.ordinal);
  await choose('#model-probe',member.frozen_reference.id);await activate('#model-correct');
  await until(()=>evaluate('!document.getElementById("view-data").hidden'));
  await until(()=>text('#real-correction-context').then(value=>value?.includes('Frozen target')));
  await until(()=>evaluate(`document.getElementById('catalog-frame').contentWindow.TuldokWorkspaceData?.snapshot().record?.id===${JSON.stringify(member.frozen_reference.id)}`));
  const current=await evaluate(`document.getElementById('catalog-frame').contentWindow.TuldokWorkspaceData.snapshot().record`);
  assert.equal(current.id,member.frozen_reference.id);assert.equal(current.revision,member.frozen_reference.revision);
  await screenshot(task+'-current-data-390',390,844);
  check('Frozen validation correction link opens the exact current Data record with its frozen target context');
  await openRun(legacy);await until(()=>text('.model-history').then(value=>value?.includes('not captured')));
  assert.equal(await evaluate('document.querySelectorAll("[data-model-checkpoint]").length'),0);
  assert.equal(await evaluate('!!document.querySelector(".model-evidence")'),false);
  await screenshot(task+'-legacy-history-390',390,844);
  check('Actual legacy one-fit result honestly reports that checkpoint/probe history was not captured');
  await openRun(original);await until(()=>evaluate('document.querySelectorAll("[data-model-checkpoint]").length===1'));
  const previous=(await send('Page.getFrameTree')).frameTree.frame;await send('Page.reload');await until(()=>tracker.reloaded(previous));
  await until(()=>evaluate('document.querySelectorAll("[data-model-checkpoint]").length===1'));
  assert.deepEqual(await api('runs.model_evidence','runs/'+original.id+'/model-evidence',{}),originalEvidence);
  const finalRun=await api('runs.get','runs/'+original.id);assert.equal(finalRun.test_exposure.exposed,false);
  assert.deepEqual(errors,[]);assert.ok(!serverErrors.includes('Traceback'),serverErrors);
  const receipt={source_commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),
    source_sha256:sourceHashes,command:'TULDOK_ONE_FIT_TASK='+task+' node tests/browser_one_fit_model_evidence.cjs',
    task,browser:(await send('Browser.getVersion')).product,checks,captures,viewport_checks:viewportChecks,
    actual_run_ids:[original.id,second.id,legacy.id],actual_training:true,actual_http_studies:2,legacy_actual_fit:true,
    catalog_path:path.join(fixture,'catalog'),fixture_receipt:JSON.parse(fs.readFileSync(path.join(fixture,'receipt.json'))),
    selected_comparison:selected,retained_weight:{sha256:checkpoint.checkpoint.weights.sha256,bytes:retained.length},
    test_exposed:false,completion_injection:false,cold_browser_reload:true,
    limitations:['Authored fixtures verify plumbing, not accuracy or generalization.','Browser gate starts with actual HTTP-prepared runs; it does not qualify browser import/model configuration.','Current Data link is qualified; correction editing is covered by retained task browser suites.','No physical or generic inference-package claim.']};
  fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify(receipt,null,2)+'\n');
  console.log('PASS one-fit browser qualification:',report);
})().catch(async error=>{
  console.error(error);console.error('Application stderr:',serverErrors);
  if(evaluate)try{console.error(await evaluate('JSON.stringify({url:location.href,status:document.getElementById("workspace-status")?.textContent,body:document.body.innerText.slice(-9000),frame:document.getElementById("catalog-frame")?.contentDocument?.body.innerText.slice(-2000)})'));}catch{}
  process.exitCode=1;
}).finally(()=>{if(ws)ws.close();for(const child of children.reverse())child.kill('SIGTERM');});
