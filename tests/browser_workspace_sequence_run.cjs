// Default: recorded actual Rheon v1. --authored-v2: synthetic transport only; no actual-packet/physics acceptance.
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
const authoredV2 = process.argv.includes("--authored-v2");
const root = path.resolve(__dirname, ".."),
  report = qaDirectory(root, authoredV2 ? "workspace-sequence-v2-authored" : "workspace-sequence-run"),
  temporary = fs.mkdtempSync(path.join(os.tmpdir(), "tuldok-workspace-sequence-run-")),
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
  async function screenshot(name, width, height, frameSelector = null) {
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
    if (frameSelector) {
      await evaluate(`(async()=>{
        const iframe=document.getElementById('catalog-frame'), target=iframe.contentDocument.querySelector(${JSON.stringify(frameSelector)});
        iframe.scrollIntoView({block:'start'});
        target.scrollIntoView({block:'center'});
        await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
        const outer=iframe.getBoundingClientRect(), inner=target.getBoundingClientRect();
        window.scrollBy(0,outer.top+inner.top-innerHeight/3);
      })()`);
    }
    await pause(60);
    if (frameSelector) {
      const visible = await evaluate(`(()=>{
        const iframe=document.getElementById('catalog-frame'), outer=iframe.getBoundingClientRect(),
          summary=iframe.contentDocument.getElementById('sequence-controls-summary').getBoundingClientRect();
        return summary.height>0 && summary.top>=0 && summary.bottom<=iframe.contentWindow.innerHeight &&
          outer.top+summary.top>=0 && outer.top+summary.bottom<=innerHeight;
      })()`);
      assert.ok(visible, 'Controls summary must be visible in both iframe and screenshot: '+name);
    }
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
      inspector: frameSelector,
      mode: authoredV2 ? "Authored synthetic v2 transport; no actual-packet or physics acceptance" : "real native validation of recorded producer sequence bytes; no new producer or scientific qualification",
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
  const fixture = authoredV2 ? path.join(temporary, 'authored-v2') : path.join(root, 'tests/fixtures/rheon_actual_fee7b4a');
  if (authoredV2) {
    fs.mkdirSync(fixture);
    execFileSync('python3',['-c',"import sys;from pathlib import Path;sys.path.insert(0,'tests');from fixtures.rheon_controls_authored import fixture;p=Path(sys.argv[1]);[(p/name).write_bytes(raw) for name,raw in zip(('run.json','frames.jsonl','controls.json'),fixture())]",fixture],{cwd:root});
  }
  const runBytes = fs.readFileSync(path.join(fixture,'run.json'));
  const framesBytes = fs.readFileSync(path.join(fixture,'frames.jsonl'));
  const controlsBytes = authoredV2 ? fs.readFileSync(path.join(fixture,'controls.json')) : null;
  const sourceManifest = JSON.parse(runBytes), producerReceipt = authoredV2 ? null : JSON.parse(fs.readFileSync(path.join(fixture,'producer-receipt.json')));
  const sha = raw => require('node:crypto').createHash('sha256').update(raw).digest('hex');
  if (authoredV2) {
    assert.equal(sourceManifest.version,2);assert.equal(sourceManifest.controls_sha256,sha(controlsBytes));
    assert.match(JSON.parse(controlsBytes).provenance.source_note,/Authored synthetic/);
  } else {
    assert.equal(sha(runBytes),producerReceipt.run_sha256);assert.equal(sha(framesBytes),producerReceipt.frames_sha256);
    assert.equal(sourceManifest.provenance.source_commit,'fee7b4a139574f87b259796b1ba8698a41d31ac1');
    assert.equal(sourceManifest.provenance.source_dirty,false);assert.equal(sourceManifest.frame_count,9);
    assert.match(producerReceipt.basis,/actual producer execution/);
  }
  await click('.embed-toolbar button',true);
  await evaluate(`${element('#sequence-import-panel',true)}.open=true`);
  async function choose(selector,name,raw) {
    await evaluate(`(()=>{const bytes=Uint8Array.from(atob(${JSON.stringify(raw.toString('base64'))}),c=>c.charCodeAt(0));const transfer=new DataTransfer();transfer.items.add(new File([bytes],${JSON.stringify(name)}));${element(selector,true)}.files=transfer.files;})()`);
  }
  await choose('#sequence-run','run.json',runBytes);await choose('#sequence-frames','frames.jsonl',framesBytes);
  await fill('#sequence-name',authoredV2 ? 'Authored synthetic v2 transport (not native packet)' : 'Recorded Rheon capped pilot',true);
  if (authoredV2) {
    await click('#sequence-import-form button',true);
    await until(()=>evaluate(`${doc(true)}.defaultView.eval('sequenceImportBusy')===false`));
    assert.match(await text('#sequence-import-status',true),/controls|version|invalid|exactly/i);
    assert.equal((await(await fetch(base+'/api/workbench/records?kind=sequence')).json()).items.length,0);
    await choose('#sequence-controls','controls.json',controlsBytes);
    await choose('#sequence-run','run.json',fs.readFileSync(path.join(root,'tests/fixtures/rheon_actual_fee7b4a/run.json')));
    await click('#sequence-import-form button',true);
    await until(()=>evaluate(`${doc(true)}.defaultView.eval('sequenceImportBusy')===false`));
    assert.match(await text('#sequence-import-status',true),/controls|version|invalid|exactly/i);
    assert.equal((await(await fetch(base+'/api/workbench/records?kind=sequence')).json()).items.length,0);
    await choose('#sequence-run','run.json',runBytes);
    check('Authored v2 missing controls and mixed v1 manifest/controls refused before any record publication');
  }
  await click('#sequence-import-form button',true);
  await until(()=>text('#sequence-import-status',true).then(t=>/9 frames, unreviewed/.test(t)));
  await key('Escape');
  const row=(await(await fetch(base+'/api/workbench/records?kind=sequence')).json()).items[0];
  await evaluate(`${doc(true)}.defaultView.TuldokWorkspaceData.openCurrentRecord(${JSON.stringify(row.id)})`);
  await until(()=>evaluate(`${element('#sequence-note',true)}!==null && !${element('#sequence-inspection',true)}.hidden`));
  if (authoredV2) {
    assert.equal(row.sequence.manifest.version,2);
    assert.equal(row.sequence.controls_sha256,sha(controlsBytes));
    await until(()=>text('#sequence-controls-summary',true).then(t=>/Version 2.*8 accepted intervals/.test(t)));
    await screenshot('authored-v2-data-1440',1440,900,'#sequence-controls-inspection');
    await screenshot('authored-v2-data-390',390,844,'#sequence-controls-inspection');
    await send('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
  }
  await fill('#sequence-note',authoredV2 ? 'Inspect authored v2 transport bytes only; no actual producer packet or physics qualification.' : 'Inspect retained native pilot bytes; no scientific or training qualification.',true);
  await select('#record-review','human_reviewed',true);
  await focus('#editor button:not([type="button"])',true);await key('Enter');
  await until(()=>text('#notice',true).then(async()=>{const current=await(await fetch(base+'/api/workbench/records/'+row.id)).json();return current.review==='human_reviewed';}));
  await reload();
  await until(() => evaluate(`${doc(true)}.defaultView.TuldokWorkspaceData?.snapshot().record?.revision===2`));
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
  const releasePath=path.join(report,authoredV2?'authored-v2-sequence-release.zip':'actual-sequence-release.zip');
  fs.writeFileSync(releasePath,releaseBytes);
  await key('Escape');
  const nativeCheck=JSON.parse(execFileSync('python3',['-c',
    "import sys,json,zipfile,io,struct;from pathlib import Path;import rheon_sequence_contract as c;import rheon_sequences as a;z=zipfile.ZipFile(sys.argv[1]);f=Path(sys.argv[2]);m=json.loads(z.read('manifest.json'));assert len(m['records'])==1;r=m['records'][0];assert r['kind']=='sequence' and r['review']=='human_reviewed';b=zipfile.ZipFile(io.BytesIO(z.read(r['asset'])));run=(f/'run.json').read_bytes();raw=(f/'frames.jsonl').read_bytes();assert b.read('run.json')==run and b.read('frames.jsonl')==raw;controls=(f/'controls.json').read_bytes() if (f/'controls.json').exists() else None;assert b.namelist()==(['run.json','frames.jsonl','controls.json'] if controls else ['run.json','frames.jsonl']);assert controls is None or b.read('controls.json')==controls;prepared=a.prepare(run,raw,controls) if controls else a.prepare(run,raw);assert r['sequence']['frame_index']==prepared['metadata']['frame_index'];inputs=[c._fields(c.parse(line)) for line in raw.splitlines()];outputs=[c._fields(c.parse(line)) for line in b.read('frames.jsonl').splitlines()];assert len(outputs)==9;assert all(struct.pack('<'+('f' if c.FIELD_TYPES[name]=='f32' else 'd'),x)==struct.pack('<'+('f' if c.FIELD_TYPES[name]=='f32' else 'd'),y) for i in range(9) for name in c.FIELD_TYPES for x,y in zip(inputs[i][name],outputs[i][name]));print(json.dumps({'frames':9,'native_field_bits_preserved':True,'raw_bytes_exact':True,'controls_bytes_exact':controls is not None,'controls_sha256':__import__('hashlib').sha256(controls).hexdigest() if controls else None}))",
    releasePath,fixture],{cwd:root,encoding:'utf8'}));
  assert.equal(nativeCheck.native_field_bits_preserved,true);
  check(authoredV2 ? 'Authored v2 imported/reviewed/frozen; all three original files preserved, not actual-packet acceptance' : 'actual recorded native sequence imported/reviewed/frozen through Data; raw files and all native field bits preserved');
  if(authoredV2){assert.equal(nativeCheck.controls_bytes_exact,true);assert.equal(nativeCheck.controls_sha256,sha(controlsBytes));}
  await nav('pipeline');
  await until(() => evaluate('!!document.getElementById("real-create-form")'));
  await fill('#real-create-name',authoredV2?'Authored v2 transport integrity':'Recorded sequence integrity');
  await select('#real-create-release',releaseId);
  await click('#real-create-form button');
  await until(() => evaluate('!!document.getElementById("real-save")'));
  assert.equal(await evaluate('document.querySelectorAll("#real-pipeline-root [data-node]").length'),3);
  assert.equal(await evaluate('document.querySelectorAll("#real-pipeline-root [data-param]").length'),0);
  await fill('#real-name','Edited sequence integrity');
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
  await until(() => evaluate('document.getElementById("real-name")?.value==="Edited sequence integrity copy"'));
  await focus('#real-validate'); await key('Enter');
  await until(() => evaluate('document.getElementById("real-submit")?.disabled===false'));
  assert.match(await text('#real-validation'),/1 sequences.*9 accepted frames/);
  assert.match(await text('#real-validation'),/selected_records_only/);
  assert.doesNotMatch(await text('#real-validation'),/holdout|test-exposure/);
  await screenshot('pipeline-sequence-1440',1440,900);
  await screenshot('pipeline-sequence-390',390,844);
  await focus('#real-submit'); await key('Enter');
  await until(() => text('#real-run-state').then(t=>t==='completed'),'Sequence run did not complete');
  const run = (await (await fetch(base+'/api/workspace/runs')).json())[0];
  assert.equal(run.graph.recipe,'sequence_validate_export');
  assert.deepEqual(run.node_attempts.map(node=>node.type),['release','validate','publish']);
  assert.equal(await evaluate('document.querySelector(".real-predictions")'),null);
  assert.equal(await evaluate('document.getElementById("real-test-predictions")'),null);
  assert.match(await text('#real-runs-root .real-sequence-summary'),/1 sequences.*9 accepted frames/);
  assert.match(await text('#real-runs-root .real-sequence-summary'),/16 × 8 × 4 cells/);
  assert.match(await text('#real-runs-root .real-sequence-summary'),/Time: 0–0.5 s/);
  check('edited and cloned three-stage graph survives reload; invalid connection blocked; keyboard submits actual native validation');
  const links=await evaluate('[...document.querySelectorAll("#real-runs-root a[download]")].map(a=>({text:a.textContent,href:a.href}))');
  const reportLink=links.find(a=>a.text==='validation-report.json');assert.ok(reportLink);
  const reportResponse=await fetch(reportLink.href);assert.equal(reportResponse.status,200);
  const validationReport=await reportResponse.json();
  assert.equal(validationReport.validation_summary.sequence_count,1);
  assert.equal(validationReport.validation_summary.frame_count,9);
  assert.equal(validationReport.validation_summary.family_scope,'selected_records_only');
  assert.ok(validationReport.validation_summary.limitations.length);
  if(authoredV2){const summary=validationReport.validation_summary.sequences[0];assert.equal(summary.controls_sha256,sha(controlsBytes));assert.equal(summary.controls_summary.interval_count,8);assert.match(summary.controls_summary.provenance.source_note,/Authored synthetic/);}
  fs.writeFileSync(path.join(report,'validation-report.json'),JSON.stringify(validationReport,null,2));
  const frozenLink=links.find(a=>a.text==='Download verified frozen export');assert.ok(frozenLink);
  assert.deepEqual(Buffer.from(await(await fetch(frozenLink.href)).arrayBuffer()),releaseBytes);
  assert.ok(links.some(a=>a.text==='artifact-manifest.json'));
  assert.ok(!links.some(a=>/checkpoint|predictions|metrics/.test(a.text)));
  await screenshot('runs-sequence-390',390,844);
  await screenshot('runs-sequence-1440',1440,900);
  check('Runs exposes verified integrity report and unchanged release, frame/time/grid/units/scope/limitations without training or predictions');
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
  assert.ok(!requests.some(url=>/\/predictions|\/expose-test/.test(url)), 'Sequence UI must never request prediction or exposure routes');
  assert.deepEqual(errors,[]);assert.ok(!serverErrors.includes('Traceback'),serverErrors);
  fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify({
    source_commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),
    dirty:!!execFileSync('git',['status','--porcelain'],{cwd:root,encoding:'utf8'}).trim(),
    command:'node tests/browser_workspace_sequence_run.cjs'+(authoredV2?' --authored-v2':''),qualification:authoredV2?'Authored synthetic v2 transport only; not actual v2 packet or physics acceptance':'Recorded actual v1 transport only',actual_v2_packet_acceptance:false,browser:(await send('Browser.getVersion')).product,
    checks,captures,run_id:run.id,release_id:releaseId,training:false,physics_claim:false,
    native_check:nativeCheck,producer_receipt:producerReceipt,offline_canary:offlineCanary,fixture_provenance:authoredV2?'Authored synthetic v2 fixture; no actual producer packet, execution or physics acceptance':'Recorded actual Rheon fee7b4a capped pilot; no producer/simulation invoked',
  },null,2));
  console.log(authoredV2?'PASS authored v2 transport workspace gate (not actual packet/physics acceptance):':'PASS real sequence workspace gate:',report);
})().catch(async error=>{
  console.error(error);
  console.error("Application stderr:", serverErrors);
  if(evaluate)try{console.error(await evaluate('JSON.stringify({url:location.href,status:document.getElementById("workspace-status")?.textContent,body:document.body.innerText.slice(-7000),frame:document.getElementById("catalog-frame")?.contentDocument?.body.innerText.slice(-2000)})'));}catch{}
  process.exitCode=1;
}).finally(()=>{if(ws)ws.close();for(const child of children.reverse())child.kill("SIGTERM");});
