// Authored native PLY → frozen release → edited graph → real integrity run/download/reopen.
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
  report = qaDirectory(root, "workspace-mesh-run"),
  temporary = fs.mkdtempSync(path.join(os.tmpdir(), "tuldok-workspace-mesh-run-")),
  children = [];
const errors = [],
  requests = [],
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
  let id = 0;
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
      m.params.request.url.includes("/api/workspace/")
    )
      requests.push(m.params.request.url);
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
    const box = await until(() => evaluate(
      `(async()=>{const el=${element(selector, frame)};
        if(!el?.isConnected || el.disabled || !el.getClientRects().length)return null;
        el.scrollIntoView({block:'center'});
        await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
        if(!el.isConnected || el.disabled)return null;
        const r=el.getBoundingClientRect(), x=r.x+r.width/2, y=r.y+r.height/2;
        const hit=${doc(frame)}.elementFromPoint(x,y);
        if(!hit || !(el===hit || el.contains(hit)))return null;
        const f=${frame ? 'document.getElementById("catalog-frame").getBoundingClientRect()' : "{left:0,top:0}"};
        return {x:x+f.left,y:y+f.top};})()`,
    ), "Click target never became ready: " + selector);
    for (const type of ["mousePressed", "mouseReleased"])
      await send("Input.dispatchMouseEvent", {type, button:"left",clickCount:1,...box});
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
      mode: "real native integrity validation on authored geometry; no training or physics claim",
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
  async function post(route, body) {
    const response = await fetch(base + route, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const value = await response.json(); assert.ok(response.ok,JSON.stringify(value)); return value;
  }
  const fixture = path.join(root, 'tests/fixtures/meshes');
  const row = await post('/api/workbench/mesh-import', {
    files: {'mesh.ply':fs.readFileSync(path.join(fixture,'asymmetric-prism.ply')).toString('base64'),
      'mesh.json':fs.readFileSync(path.join(fixture,'asymmetric-prism.json')).toString('base64')},
    name:'Authored asymmetric prism',
  });
  await post('/api/workbench/records/'+row.id, {revision:row.revision,source_revision:row.source_revision,
    task:'mesh_geometry',annotation:{note:'Inspected authored geometry and declared units.'},groups:row.groups,review:'human_reviewed'});
  await reload();
  await until(() => text('#notice',true).then(t=>t==='Collection ready.'));
  await click('#select-page',true);
  await click('.embed-toolbar button',true);
  await evaluate(`${element('#release-form',true)}.closest('details').open=true`);
  await fill('#train','100',true); await fill('#validation','0',true); await fill('#test','0',true);
  await click('#preview-release',true);
  await until(() => evaluate(`${element('#freeze-release',true)}?.disabled===false`));
  await click('#freeze-release',true);
  await until(() => evaluate(`!!${doc(true)}.querySelector('#release-result a')`));
  const download = await evaluate(`${doc(true)}.querySelector('#release-result a').href`), releaseId=/([a-f0-9]{64})/.exec(download)[1];
  const releaseResponse = await fetch(download); assert.equal(releaseResponse.status,200);
  const releaseBytes=Buffer.from(await releaseResponse.arrayBuffer());
  fs.writeFileSync(path.join(report,'authored-mesh-release.zip'),releaseBytes);
  await key('Escape');
  check('reviewed authored native PLY frozen through real Data release controls');
  await nav('pipeline');
  await until(() => evaluate('!!document.getElementById("real-create-form")'));
  await fill('#real-create-name','Authored mesh integrity');
  await select('#real-create-release',releaseId);
  await click('#real-create-form button');
  await until(() => evaluate('!!document.getElementById("real-save")'));
  assert.equal(await evaluate('document.querySelectorAll("#real-pipeline-root [data-node]").length'),3);
  assert.equal(await evaluate('document.querySelectorAll("#real-pipeline-root [data-param]").length'),0);
  await fill('#real-name','Edited mesh integrity');
  await click('#real-save');
  await until(() => text('#real-dirty').then(t=>t==='Saved r2'));
  await click('.real-connections summary');
  await click('#real-pipeline-root [data-edge="1"]');
  await click('#real-save');
  await until(() => text('#real-dirty').then(t=>t==='Saved r3'));
  await click('#real-validate');
  await until(() => evaluate('!!document.querySelector("#real-validation .error-panel")'));
  assert.equal(await evaluate('document.getElementById("real-submit").disabled'),true);
  await click('.real-connections summary');
  await click('#real-pipeline-root [data-edge="1"]');
  await click('#real-save');
  await until(() => text('#real-dirty').then(t=>t==='Saved r4'));
  await click('#real-clone');
  await until(() => text('#real-dirty').then(t=>t==='Saved r1'));
  await reload();
  await until(() => evaluate('document.getElementById("real-name")?.value==="Edited mesh integrity copy"'));
  await focus('#real-validate'); await key('Enter');
  await until(() => evaluate('document.getElementById("real-submit")?.disabled===false'));
  assert.match(await text('#real-validation'),/1 meshes.*6 vertices.*8 triangles/);
  assert.match(await text('#real-validation'),/selected_records_only/);
  assert.doesNotMatch(await text('#real-validation'),/holdout|test-exposure/);
  await screenshot('pipeline-mesh-1440',1440,900);
  await screenshot('pipeline-mesh-390',390,844);
  await focus('#real-submit'); await key('Enter');
  await until(() => text('#real-run-state').then(t=>t==='completed'),'Mesh run did not complete');
  const run = (await (await fetch(base+'/api/workspace/runs')).json())[0];
  assert.equal(run.graph.recipe,'mesh_validate_export');
  assert.deepEqual(run.node_attempts.map(node=>node.type),['release','validate','publish']);
  assert.equal(await evaluate('document.querySelector(".real-predictions")'),null);
  assert.equal(await evaluate('document.getElementById("real-test-predictions")'),null);
  assert.match(await text('#real-runs-root .real-mesh-summary'),/1 meshes.*6 vertices.*8 triangles/);
  check('edited and cloned three-stage graph survives reload; invalid connection blocked; keyboard submits actual native validation');
  const links=await evaluate('[...document.querySelectorAll("#real-runs-root a[download]")].map(a=>({text:a.textContent,href:a.href}))');
  const reportLink=links.find(a=>a.text==='validation-report.json');assert.ok(reportLink);
  const reportResponse=await fetch(reportLink.href);assert.equal(reportResponse.status,200);
  const validationReport=await reportResponse.json();
  assert.equal(validationReport.validation_summary.mesh_count,1);
  assert.equal(validationReport.validation_summary.triangle_count,8);
  assert.equal(validationReport.validation_summary.family_scope,'selected_records_only');
  assert.ok(validationReport.validation_summary.limitations.length);
  fs.writeFileSync(path.join(report,'validation-report.json'),JSON.stringify(validationReport,null,2));
  const frozenLink=links.find(a=>a.text==='Download verified frozen export');assert.ok(frozenLink);
  assert.deepEqual(Buffer.from(await(await fetch(frozenLink.href)).arrayBuffer()),releaseBytes);
  assert.ok(links.some(a=>a.text==='artifact-manifest.json'));
  assert.ok(!links.some(a=>/checkpoint|predictions|metrics/.test(a.text)));
  await screenshot('runs-mesh-390',390,844);
  await screenshot('runs-mesh-1440',1440,900);
  check('Runs exposes verified integrity report and unchanged release, counts, units/scope/limitations without training or predictions');
  server.kill('SIGINT');
  await until(()=>server.exitCode!==null,'Application did not drain and close');
  server=launch('python3',['-u','app.py','--port',port,'--data',path.join(temporary,'data')],{cwd:root,stdio:['ignore','pipe','pipe']});
  let reopened='';server.stdout.on('data',chunk=>reopened+=chunk);server.stderr.on('data',chunk=>serverErrors+=chunk);
  await until(()=>reopened.includes('Tuldok:'),'Reopened application did not start');
  await reload();await until(()=>text('#real-run-state').then(t=>t==='completed'));
  assert.equal((await(await fetch(base+'/api/workspace/runs')).json()).length,1);
  assert.deepEqual(await(await fetch(reportLink.href)).json(),validationReport);
  assert.deepEqual(Buffer.from(await(await fetch(frozenLink.href)).arrayBuffer()),releaseBytes);
  check('application restart retains exact completed report/release and does not replay submission');
  assert.ok(!requests.some(url=>/\/predictions|\/expose-test/.test(url)), 'Mesh UI must never request prediction or exposure routes');
  assert.deepEqual(errors,[]);assert.ok(!serverErrors.includes('Traceback'),serverErrors);
  fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify({
    source_commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),
    dirty:!!execFileSync('git',['status','--porcelain'],{cwd:root,encoding:'utf8'}).trim(),
    command:'node tests/browser_workspace_mesh_run.cjs',browser:(await send('Browser.getVersion')).product,
    checks,captures,run_id:run.id,release_id:releaseId,training:false,physics_claim:false,
    offline_canary:offlineCanary,fixture_provenance:'Project-authored asymmetric prism; real PLY, no physics producer',
  },null,2));
  console.log('PASS real mesh workspace gate:',report);
})().catch(async error=>{
  console.error(error);
  console.error("Application stderr:", serverErrors);
  if(evaluate)try{console.error(await evaluate('JSON.stringify({url:location.href,status:document.getElementById("workspace-status")?.textContent,body:document.body.innerText.slice(-7000),frame:document.getElementById("catalog-frame")?.contentDocument?.body.innerText.slice(-2000)})'));}catch{}
  process.exitCode=1;
}).finally(()=>{if(ws)ws.close();for(const child of children.reverse())child.kill("SIGTERM");});
