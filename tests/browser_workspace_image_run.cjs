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
  report = qaDirectory(root, "workspace-image-run"),
  temporary = fs.mkdtempSync(path.join(os.tmpdir(), "tuldok-workspace-image-run-")),
  children = [];
const errors = [],
  posts = [],
  captures = [],
  checks = [];
let ws, send, evaluate, serverErrors = "";
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function until(fn, message = "Timed out") {
  for (let i = 0; i < 600; i++) {
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
  const tabs = await (
      await fetch("http://127.0.0.1:" + debugPort + "/json")
    ).json(),
    target = tabs.find((t) => t.type === "page" && t.url === "about:blank");
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
        }, 20000);
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
    if (name.startsWith("catalog"))
      await evaluate(
        'document.getElementById("catalog-frame").contentWindow.scrollTo(0,0)',
      );
    await pause(60);
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
  await send('Fetch.enable', {patterns:[{urlPattern:base + '/api/workspace/definitions',requestStage:'Response'}]});
  pausedRequest = null;
  await nav("pipeline");
  await until(() => pausedRequest);
  assert.match(await text('#real-pipeline-root'), /Loading saved recipes/);
  await nav('runs');
  await send('Fetch.continueRequest', {requestId:pausedRequest});
  await send('Fetch.disable'); pausedRequest = null;
  await until(() => text('#real-runs-root').then(t => t?.includes('No real runs yet')));
  assert.equal(await evaluate('document.getElementById("view-pipeline").hidden'), true);
  await send('Fetch.enable', {patterns:[{urlPattern:base + '/api/workspace/definitions',requestStage:'Response'}]});
  await nav('pipeline');
  await until(() => pausedRequest);
  await send('Fetch.fulfillRequest', {requestId:pausedRequest,responseCode:503,
    responseHeaders:[{name:'Content-Type',value:'application/json'}],
    body:Buffer.from(JSON.stringify({error:'Injected definition transport failure',code:'unavailable'})).toString('base64')});
  await send('Fetch.disable'); pausedRequest = null;
  await until(() => evaluate('!!document.getElementById("real-load-retry")'));
  assert.match(await text('#real-pipeline-root'), /Injected definition transport failure/);
  await click('#real-load-retry');
  await until(() => evaluate('!!document.getElementById("real-create-form")'));
  check('real Pipeline loading, late-response navigation fence and explicit error retry');
  await fill("#real-create-name", "Authored shape baseline");
  await select("#real-create-release", releaseId);
  await click("#real-create-form button");
  await until(() => evaluate('!!document.getElementById("real-param-epochs")'));
  await fill("#real-param-epochs", "2");
  assert.match(await text("#real-dirty"), /Unsaved/);
  assert.equal(await evaluate('document.getElementById("real-validate").disabled'), true);
  await click("#real-save");
  await until(() => text("#real-dirty").then(t => t === "Saved r2"));
  await reload();
  await until(() => evaluate('document.getElementById("real-param-epochs")?.value==="2"'));
  await click(".real-connections summary");
  await click("#real-pipeline-root [data-edge='1']");
  await click("#real-save");
  await until(() => text("#real-dirty").then(t => t === "Saved r3"));
  await click("#real-validate");
  await until(() => text("#real-validation").then(t => /Connect the five typed stages/.test(t)));
  assert.equal(await evaluate('document.getElementById("real-submit").disabled'), true);
  await click(".real-connections summary");
  await click("#real-pipeline-root [data-edge='1']");
  await click("#real-save");
  await until(() => text("#real-dirty").then(t => t === "Saved r4"));
  await focus("#real-validate"); await key("Enter");
  await until(() => evaluate('document.getElementById("real-submit")?.disabled===false'));
  assert.match(await text("#real-validation"), /Verified frozen input/);
  // A peer saves after this browser validated: rejection must clear the pending
  // receipt so explicit reload + validation can recover without a new page.
  const graphBefore = (await (await fetch(base + '/api/workspace/graphs')).json())[0];
  const peerSave = await fetch(base + '/api/workspace/graphs/' + graphBefore.id, {
    method:'POST', headers:{'Content-Type':'application/json'},
    body:JSON.stringify({revision:graphBefore.revision,document:graphBefore}),
  });
  assert.equal(peerSave.status, 200);
  await click('#real-submit');
  await until(() => text('#real-pipeline-root .real-status').then(t => t?.includes('No run was admitted')));
  assert.equal(await evaluate('history.state.realWorkspace.pendingSubmission'), null);
  assert.equal((await (await fetch(base + '/api/workspace/runs')).json()).length, 0);
  await click('#real-reload');
  await until(() => text('#real-dirty').then(t => t === 'Saved r5'));
  await click('#real-validate');
  await until(() => evaluate('document.getElementById("real-submit")?.disabled===false'));
  check('real HTTP stale validation rejects before admission and explicit reload/revalidation recovers');
  await screenshot("pipeline-real-1440", 1440, 900);
  await screenshot("pipeline-real-390", 390, 844);
  await send("Emulation.setDeviceMetricsOverride", { width:1440,height:900,deviceScaleFactor:1,mobile:false });
  check("actual trainer parameter edit/save/reload, disconnected graph refusal, keyboard validation and runtime preview");
  const submittedBefore = posts.filter(p => p.endsWith("/api/workspace/runs")).length;
  // Fail only delivery of the committed POST response. The browser must retain
  // its exact key/body and require explicit reconciliation, without auto retry.
  await send('Fetch.enable', {patterns:[{urlPattern:base + '/api/workspace/runs',requestStage:'Response'}]});
  pausedRequest = null;
  await evaluate('document.getElementById("real-submit").click();document.getElementById("real-submit").click()');
  await until(() => pausedRequest);
  await send('Fetch.failRequest', {requestId:pausedRequest,errorReason:'Failed'});
  await send('Fetch.disable'); pausedRequest = null;
  await until(() => text('#real-pipeline-root .real-status').then(t => t?.includes('Failed to fetch')));
  const uncertain = await evaluate('history.state.realWorkspace.pendingSubmission');
  assert.ok(uncertain?.request_key);
  assert.equal(posts.filter(p => p.endsWith('/api/workspace/runs')).length - submittedBefore, 1);
  assert.equal((await (await fetch(base + '/api/workspace/runs')).json()).length, 1);
  await click('#real-submit');
  await until(() => evaluate('!!document.getElementById("real-run-state")'));
  assert.equal(posts.filter(p => p.endsWith("/api/workspace/runs")).length - submittedBefore, 2);
  assert.equal(await evaluate('history.state.realWorkspace.pendingSubmission'), null);
  check('lost committed response retains exact receipt; explicit reconciliation returns the same single run');
  await screenshot("running-real-1440", 1440, 900);
  await until(() => text("#real-run-state").then(t => ["completed","failed","unknown"].includes(t)));
  assert.equal(await text("#real-run-state"), "completed", await text("#real-runs-root"));
  const runList = await (await fetch(base + "/api/workspace/runs")).json(), run = runList[0];
  assert.equal(run.parameters.epochs, 2);
  assert.equal(run.state, "completed"); assert.equal(runList.length, 1);
  const predictionURL = base + `/api/workspace/runs/${run.id}/predictions`,
    originalPredictions = await (await fetch(predictionURL)).json();
  assert.ok(originalPredictions.rows.length > 0);
  assert.equal(originalPredictions.split, "validation");
  const checkpoint = await fetch(base + `/api/workspace/runs/${run.id}/artifacts/checkpoint.pt`);
  assert.equal(checkpoint.status, 200); assert.ok((await checkpoint.arrayBuffer()).byteLength > 1000);
  assert.equal((await fetch(base + `/api/workspace/runs/${run.id}/artifacts/test-metrics.json`)).status, 409);
  assert.ok(!JSON.stringify(run.metrics).includes('"test"'));
  await screenshot("results-real-1440", 1440, 900);
  await screenshot("results-real-1024", 1024, 768);
  await screenshot("results-real-390", 390, 844);
  if (process.env.TULDOK_NATIVE_ZOOM) {
    await send('Emulation.clearDeviceMetricsOverride');
    const xdotool = process.env.TULDOK_XDOTOOL || 'xdotool';
    const windows = execFileSync(xdotool, ['search','--onlyvisible','--class','Chromium'], {encoding:'utf8'}).trim().split('\n');
    assert.equal(windows.length, 1, 'Native zoom requires one owned visible Chromium window');
    execFileSync(xdotool, ['windowfocus','--sync',windows[0]]);
    execFileSync(xdotool, ['key','--clearmodifiers','ctrl+0']);
    const unzoomed = await evaluate('({width:innerWidth,ratio:devicePixelRatio})');
    for (let i=0;i<5;i++) execFileSync(xdotool, ['key','--clearmodifiers','ctrl+plus']);
    await until(() => evaluate('devicePixelRatio') .then(r => Math.abs(r / unzoomed.ratio - 2) < .01));
    assert.ok(await evaluate('document.documentElement.scrollWidth <= innerWidth+1'));
    const zoomed = await evaluate('({width:innerWidth,ratio:devicePixelRatio})');
    assert.ok(Math.abs(zoomed.width * 2 - unzoomed.width) < 20);
    for (const [view, target] of [['pipeline','#real-param-epochs'],['data','#catalog-frame'],['runs','.metric-grid']]) {
      await focus('#nav-' + view); await key('Enter');
      await until(() => evaluate(`!document.getElementById('view-${view}').hidden`));
      await until(() => evaluate(`!!document.querySelector(${JSON.stringify(target)})`));
      await evaluate(`document.querySelector(${JSON.stringify(target)}).scrollIntoView({block:'center'})`);
      assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'), view+' native zoom overflow');
      if (view === 'data') assert.ok(await evaluate(`${doc(true)}.documentElement.scrollWidth<=${doc(true)}.defaultView.innerWidth+1`));
      const filename = view + '-native-200.jpg', shot = await send('Page.captureScreenshot', screenshotOptions);
      fs.writeFileSync(path.join(report,filename), Buffer.from(shot.data,'base64'));
      captures.push({file:filename,native_browser_zoom:200,unzoomed,zoomed,quality:85});
    }
    execFileSync(xdotool, ['key','--clearmodifiers','ctrl+0']);
    await until(() => evaluate('devicePixelRatio').then(r => r === unzoomed.ratio));
    check('native Chromium 200% menu zoom verified by doubled device ratio and halved CSS viewport; no horizontal overflow');
  }
  check("one admitted real child completed; verified checkpoint, validation metrics and exact predictions; test access remains locked");
  await send("Emulation.setDeviceMetricsOverride", { width:1440,height:900,deviceScaleFactor:1,mobile:false });
  const example = originalPredictions.rows.find(p => p.truth_index !== p.predicted_index) || originalPredictions.rows[0];
  const previousRecord = await evaluate(`${doc(true)}.defaultView.TuldokWorkspaceData.snapshot().record.id`);
  await send('Fetch.enable', {patterns:[{urlPattern:base + '/api/workbench/records/' + example.id,requestStage:'Response'}]});
  pausedRequest = null;
  await click(`[data-correct-record="${example.id}"]`);
  await until(() => pausedRequest);
  await nav('pipeline');
  await send('Fetch.continueRequest', {requestId:pausedRequest});
  await send('Fetch.disable'); pausedRequest = null;
  await evaluate('new Promise(resolve=>setTimeout(resolve,150))');
  assert.equal(await evaluate('document.getElementById("view-data").hidden'), true);
  assert.equal(await evaluate(`${doc(true)}.defaultView.TuldokWorkspaceData.snapshot().record.id`), previousRecord);
  await nav('runs');
  await until(() => evaluate(`!!document.querySelector('[data-correct-record="${example.id}"]')`));
  check('late correction response cannot override newer Pipeline navigation or the active Data record');
  await click(`[data-correct-record="${example.id}"]`);
  await until(() => evaluate('!document.getElementById("view-data").hidden'));
  assert.match(await text("#real-correction-context"), /Frozen target/);
  await fill("#label", example.truth_label === "circle" ? "square" : "circle", true);
  await select("#record-review", "human_reviewed", true);
  await click("#save", true);
  await until(() => evaluate(`${doc(true)}.defaultView.TuldokWorkspaceData.snapshot().dirty===false`));
  await until(() => text('#real-correction-context').then(t => t?.includes(`Current annotation r${example.revision+1}`)));
  await screenshot("catalog-correction-1440", 1440, 900);
  await click("#clear-selection", true); await click("#select-page", true);
  await click(".embed-toolbar button", true);
  await evaluate(`${element("#release-form", true)}.closest('details').open=true`);
  await select("#release-format", "image_classification_v1", true);
  await fill("#train", "50", true); await fill("#validation", "25", true); await fill("#test", "25", true);
  // The correction is an authored custody exercise; preserve coverage by finding a valid explicit seed.
  for (let seed = 42; seed < 100; seed++) {
    await fill("#split-seed", String(seed), true); await click("#preview-release", true);
    await until(() => evaluate(`${doc(true)}.defaultView.eval('releaseBusy')===false`));
    if (!await evaluate(`${element("#freeze-release", true)}.disabled`)) break;
  }
  assert.equal(await evaluate(`${element("#freeze-release", true)}.disabled`), false);
  await click("#freeze-release", true);
  await until(async () => { const href = await evaluate(`${doc(true)}.querySelector('#release-result a')?.href`); return !!href && href !== download; });
  const correctedDownload = await evaluate(`${doc(true)}.querySelector('#release-result a').href`);
  assert.ok(correctedDownload && correctedDownload !== download);
  await key("Escape");
  // Another active record must never inherit the first example's provenance.
  const otherRecord = originalPredictions.rows.find(p => p.id !== example.id);
  await evaluate(`${doc(true)}.defaultView.TuldokWorkspaceData.openCurrentRecord(${JSON.stringify(otherRecord.id)})`);
  await until(() => evaluate('document.getElementById("real-correction-context").hidden'));
  assert.deepEqual(Buffer.from(await (await fetch(download)).arrayBuffer()), releaseBytes);
  const revisedPredictions = await (await fetch(predictionURL)).json();
  assert.deepEqual(revisedPredictions.rows.map(p => p.frozen_reference), originalPredictions.rows.map(p => p.frozen_reference));
  assert.equal(revisedPredictions.rows.find(p => p.id === example.id).truth_label, example.truth_label);
  check("result correction saves a new reviewed revision/release while old release bytes and frozen predictions remain unchanged");
  await nav("runs"); await until(() => evaluate('!!document.getElementById("real-test-predictions")'));
  const exposing = click("#real-test-predictions");
  await until(() => dialog?.type === "prompt");
  await send("Page.handleJavaScriptDialog", { accept:true,promptText:"Authored acceptance scenario: inspect held-out examples and prove exposure tracking." });
  await exposing; dialog = null;
  await until(() => text(".real-predictions .badge").then(t => t.includes("test · exposed")));
  for (const artifact of run.artifacts) {
    const response = await fetch(base + `/api/workspace/runs/${run.id}/artifacts/${artifact.name}`);
    assert.equal(response.status, 200, artifact.name);
    const bytes = Buffer.from(await response.arrayBuffer());
    assert.equal(bytes.length, artifact.bytes, artifact.name);
    assert.equal(require('node:crypto').createHash('sha256').update(bytes).digest('hex'), artifact.sha256, artifact.name);
  }
  const releases = await (await fetch(base + "/api/workspace/releases")).json();
  assert.equal(releases.find(r => correctedDownload.includes(r.id)).prior_test_exposure.exposed, true);
  check("explicit test inspection is durable; later releases containing the records/pixels are marked exposed/reused");
  // Reopen the same durable catalog without replaying any request.
  server.kill("SIGINT");
  await until(() => server.exitCode !== null, "Application did not drain and close");
  server = launch("python3", ["-u", "app.py", "--port", port, "--data", path.join(temporary, "data")], { cwd: root, stdio: ["ignore", "pipe", "pipe"] });
  let reopened = "";
  server.stdout.on("data", chunk => reopened += chunk);
  server.stderr.on("data", chunk => serverErrors += chunk);
  await until(() => reopened.includes("Tuldok:"), "Reopened application did not start");
  await reload();
  await until(() => text("#real-run-state").then(t => t === "completed"));
  const afterRestart = await (await fetch(base + "/api/workspace/runs")).json();
  assert.equal(afterRestart.length, 1);
  assert.equal(afterRestart[0].id, run.id);
  assert.equal(afterRestart[0].test_exposure.exposed, true);
  assert.deepEqual(Buffer.from(await (await fetch(download)).arrayBuffer()), releaseBytes);
  assert.deepEqual((await (await fetch(predictionURL)).json()).rows.map(p => p.frozen_reference), originalPredictions.rows.map(p => p.frozen_reference));
  check("application restart retains exact run, immutable inputs/predictions and durable test exposure without replay");
  assert.deepEqual(errors, []);
  assert.ok(!serverErrors.includes("Traceback"), serverErrors);
  fs.writeFileSync(path.join(report,"receipt.json"),JSON.stringify({
    source_commit:execFileSync("git",["rev-parse","HEAD"],{cwd:root,encoding:"utf8"}).trim(),
    dirty:!!execFileSync("git",["status","--porcelain"],{cwd:root,encoding:"utf8"}).trim(),
    command:"node tests/browser_workspace_image_run.cjs", browser:(await send("Browser.getVersion")).product,
    checks,captures,run_id:run.id,release_id:releaseId,training:true,quality_claim:false,
    offline_canary: offlineCanary,
    outbound_transport: process.env.LD_PRELOAD ? "libc loopback-only injection (not a direct-syscall security sandbox)" : "unrestricted; no offline claim",
    fixture_provenance:"12 CC0 authored independent images imported through ordinary Data UI",
  },null,2));
  console.log("PASS real image workspace gate:",report);
})().catch(async error=>{
  console.error(error);
  console.error("Application stderr:", serverErrors);
  if(evaluate)try{console.error(await evaluate('JSON.stringify({url:location.href,status:document.getElementById("workspace-status")?.textContent,body:document.body.innerText.slice(-7000),frame:document.getElementById("catalog-frame")?.contentDocument?.body.innerText.slice(-2000)})'));}catch{}
  process.exitCode=1;
}).finally(()=>{if(ws)ws.close();for(const child of children.reverse())child.kill("SIGTERM");});
