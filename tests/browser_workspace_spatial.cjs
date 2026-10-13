// Authored point and volume bytes through real Data and integrity workflows.
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
  report = qaDirectory(root, "workspace-spatial"),
  temporary = fs.mkdtempSync(path.join(os.tmpdir(), "tuldok-workspace-spatial-")),
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
    if(m.method==='Page.javascriptDialogOpening') send('Page.handleJavaScriptDialog',{accept:true}).catch(error=>errors.push(String(error)));
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
    if(name.includes('-data-')) {
      const kind=name.startsWith('pointcloud')?'pointcloud':'volume';
      await evaluate(`${element('#'+kind+'-inspection',true)}.scrollIntoView({block:'start'})`);
    }
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
      mode: "real authored spatial assets; native reader/coordinate evidence, no model or scientific qualification",
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
  const records={},releases={},nativeFiles={};
  async function choose(selector,name,raw) {
    await evaluate(`(()=>{const bytes=Uint8Array.from(atob(${JSON.stringify(raw.toString('base64'))}),c=>c.charCodeAt(0));const transfer=new DataTransfer();transfer.items.add(new File([bytes],${JSON.stringify(name)}));${element(selector,true)}.files=transfer.files;})()`);
  }
  async function openRecord(row) {
    await evaluate(`${doc(true)}.defaultView.TuldokWorkspaceData.openCurrentRecord(${JSON.stringify(row.id)})`);
    await until(()=>evaluate(`${doc(true)}.defaultView.TuldokWorkspaceData.snapshot().record?.id===${JSON.stringify(row.id)}`));
  }
  for(const [kind,fixture,rawName,sidecarName] of [['pointcloud','pointclouds/ordered','points.ply','points.json'],['volume','volumes/oriented','volume.npy','volume.json']]){
    const raw=fs.readFileSync(path.join(root,'tests/fixtures/'+fixture+(kind==='pointcloud'?'.ply':'.npy')));
    const sidecar=fs.readFileSync(path.join(root,'tests/fixtures/'+fixture+'.json'));
    nativeFiles[kind]={raw,sidecar};
    await click('.embed-toolbar button',true);
    await evaluate(`${element('#'+kind+'-import-panel',true)}.open=true`);
    await choose('#'+kind+'-file',rawName,raw);await choose('#'+kind+'-manifest',sidecarName,sidecar);
    await fill('#'+kind+'-name','Authored '+kind,true);await fill('#'+kind+'-rights','CC0 authored inspection fixture',true);
    await click('#'+kind+'-import-form button',true);
    await until(()=>text('#'+kind+'-import-status',true).then(t=>t?.includes('unreviewed.')));
    await key('Escape');
    const row=(await(await fetch(base+'/api/workbench/records?kind='+kind)).json()).items[0];records[kind]=row;
    await openRecord(row);
    await until(()=>text('#'+kind+'-preview-status',true).then(t=>kind==='pointcloud'?t?.includes('Showing first 3 of 3'):t?.includes('2 × 3 × 4')));
    if(kind==='pointcloud'){
      await until(()=>evaluate(`${doc(true)}.querySelectorAll('#pointcloud-svg circle').length===3`));
      assert.deepEqual(await evaluate(`[...${doc(true)}.querySelectorAll('#pointcloud-svg circle')].map(node=>node.dataset.sourceIndex)`),['0','1','2']);
      const before=await evaluate(`${doc(true)}.querySelector('#pointcloud-svg circle').getAttribute('cx')`);
      await focus('#pointcloud-preview button:nth-child(2)',true);await key('Enter');
      assert.notEqual(await evaluate(`${doc(true)}.querySelector('#pointcloud-svg circle').getAttribute('cx')`),before);
      assert.equal(await evaluate(`${doc(true)}.defaultView.TuldokWorkspaceData.snapshot().dirty`),false);
    }else{
      await until(()=>text('#volume-position-z',true).then(t=>t?.includes('Z index 0')));
      await focus('#volume-index-z',true);await key('ArrowUp');
      await until(()=>text('#volume-position-z',true).then(t=>t?.includes('Z index 1')));
      assert.match(await text('#volume-position-z',true),/origin \(10, -20, 35\) mm/);
      assert.equal(await evaluate(`${doc(true)}.defaultView.TuldokWorkspaceData.snapshot().dirty`),false);
      const slice=await(await fetch(base+'/api/workbench/volume-inspection/'+row.id+'?axis=z&index=1')).json();
      assert.deepEqual(slice.physical_origin,[10,-20,35]);assert.deepEqual(slice.physical_row_step,[-3,0,0]);assert.deepEqual(slice.physical_column_step,[0,2,0]);
      assert.deepEqual(slice.values,[[12,13,14,15],[16,17,18,19],[20,21,22,23]]);
      assert.equal(await evaluate(`${doc(true)}.querySelector('#volume-canvas-z').getContext('2d').getImageData(0,0,1,1).data[0]`),12);
    }
    await fill('#'+kind+'-note','Native inspection; preserve exact source and declared coordinates.',true);
    await select('#record-review','human_reviewed',true);await focus('#editor button:not([type="button"])',true);await key('Enter');
    await until(async()=>{const current=await(await fetch(base+'/api/workbench/records/'+row.id)).json();return current.review==='human_reviewed'&&current.revision===2;});
    const sourceResponse=await fetch(base+'/api/workbench/asset/'+row.id);assert.equal(sourceResponse.status,200);
    fs.writeFileSync(path.join(report,kind+'-original.zip'),Buffer.from(await sourceResponse.arrayBuffer()));
    await evaluate(`${element('#'+kind+'-inspection',true)}.scrollIntoView()`);
    await screenshot(kind+'-data-1440',1440,900);
    await screenshot(kind+'-data-390',390,844);
    await send('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
    await click('#clear-selection',true);
    await click('input[aria-label="Select Authored '+kind+'"]',true);
    await click('.embed-toolbar button',true);
    await evaluate(`${element('#release-form',true)}.closest('details').open=true`);
    await fill('#train','100',true);await fill('#validation','0',true);await fill('#test','0',true);
    await click('#preview-release',true);await until(()=>evaluate(`${element('#freeze-release',true)}?.disabled===false`));
    await click('#freeze-release',true);await until(()=>evaluate(`!!${doc(true)}.querySelector('#release-result a')`));
    const url=await evaluate(`${doc(true)}.querySelector('#release-result a').href`);
    const response=await fetch(url);assert.equal(response.status,200);const bytes=Buffer.from(await response.arrayBuffer());
    releases[kind]={id:/([a-f0-9]{64})/.exec(url)[1],bytes,url};fs.writeFileSync(path.join(report,kind+'-release.zip'),bytes);
    await key('Escape');
    check(kind+' real file import, keyboard inspection/review and whole-source freeze');
  }
  // A completed but delayed projection cannot overwrite a newer source/editor.
  await evaluate(`${doc(true)}.defaultView.eval(${JSON.stringify("(()=>{const original=window.fetch;window.holdPoint=true;window.fetch=async(...args)=>{const response=await original(...args);if(String(args[0]).includes('/pointcloud-inspection/')&&window.holdPoint){window.holdPoint=false;await new Promise(resolve=>window.releasePoint=resolve);}return response;};})()")})`);
  await openRecord(records.pointcloud);await until(()=>evaluate(`!!${doc(true)}.defaultView.releasePoint`));
  await openRecord(records.volume);await fill('#volume-note','Unsaved volume note survives old point response.',true);
  await evaluate(`${doc(true)}.defaultView.releasePoint()`);await pause(150);
  assert.equal(await evaluate(`${element('#pointcloud-inspection',true)}.hidden`),true);
  assert.equal(await evaluate(`${element('#volume-note',true)}.value`),'Unsaved volume note survives old point response.');
  assert.equal(await evaluate(`${doc(true)}.defaultView.TuldokWorkspaceData.snapshot().dirty`),true);
  await click('#reload',true);await until(()=>evaluate(`!${doc(true)}.defaultView.TuldokWorkspaceData.snapshot().dirty`));
  check('late point projection cannot overwrite a newer dirty volume editor');
  // Independent installed readers consume the downloaded native files, including signed zero/order and affine mapping.
  const nativeCheck=JSON.parse(execFileSync(process.env.TULDOK_NATIVE_READER_PYTHON||'python3',['-c',
    "import sys,io,json,zipfile,struct;from pathlib import Path;import numpy as np;from plyfile import PlyData;p=Path(sys.argv[1]);source=Path('tests/fixtures');out={};\nfor kind,folder,stem,rawname,sidecar in [('pointcloud','pointclouds','ordered','points.ply','points.json'),('volume','volumes','oriented','volume.npy','volume.json')]:\n z=zipfile.ZipFile(p/(kind+'-release.zip'));m=json.loads(z.read('manifest.json'));assert len(m['records'])==1;r=m['records'][0];assert r['review']=='human_reviewed';bundle=z.read(r['asset']);assert bundle==(p/(kind+'-original.zip')).read_bytes();b=zipfile.ZipFile(io.BytesIO(bundle));raw=b.read(rawname);assert raw==(source/folder/(stem+('.ply' if kind=='pointcloud' else '.npy'))).read_bytes();assert b.read(sidecar)==(source/folder/(stem+'.json')).read_bytes();\n if kind=='pointcloud':\n  a=PlyData.read(io.BytesIO(raw))['vertex'].data;assert len(a)==3 and np.signbit(a['x'][0]) and np.signbit(a['x'][2]);assert a['x'].dtype.itemsize==4 and a['y'].dtype.itemsize==8;assert a['red'].tolist()==[255,1,255];assert a['x'].tolist()==[-0.0,1.25,-0.0];out[kind]={'reader':'plyfile','ordered_points':3,'signed_zero_preserved':True}\n else:\n  a=np.load(io.BytesIO(raw),allow_pickle=False);assert a.dtype==np.uint8 and a.shape==(2,3,4);assert np.array_equal(a,np.arange(24,dtype=np.uint8).reshape(2,3,4));affine=np.array(json.loads(b.read(sidecar))['affine']);assert np.array_equal(affine@np.array([0,0,1,1]),[10,-20,35,1]);out[kind]={'reader':'numpy allow_pickle=False','shape':list(a.shape),'all_values_exact':True,'physical_mapping_verified':True}\nprint(json.dumps(out))",
    report],{cwd:root,encoding:'utf8'}));
  check('independent plyfile/NumPy readers preserve native order/types/signed zero, all voxels and affine mapping');
  const runIds=[];
  for(const kind of ['pointcloud','volume']){
    await nav('pipeline');await until(()=>evaluate('!!document.getElementById("real-create-form")'));
    await click('#real-refresh');await until(()=>evaluate('!!document.getElementById("real-create-form")'));
    await evaluate('document.getElementById("real-create-form").closest("details").open=true');
    await fill('#real-create-name','Native '+kind+' integrity');await select('#real-create-release',releases[kind].id);await click('#real-create-form button');
    await until(()=>evaluate('document.querySelectorAll("#real-pipeline-root [data-node]").length===3'));
    await fill('#real-name','Edited '+kind+' integrity');await click('#real-save');await until(()=>text('#real-dirty').then(t=>t==='Saved r2'));
    await click('#real-clone');await until(()=>text('#real-dirty').then(t=>t==='Saved r1'));
    await focus('#real-validate');await key('Enter');await until(()=>evaluate('document.getElementById("real-submit")?.disabled===false'));
    assert.match(await text('#real-validation'),kind==='pointcloud'?/3 points/:/24 voxels/);
    await screenshot(kind+'-pipeline-390',390,844);
    await focus('#real-submit');await key('Enter');await until(()=>evaluate(`!document.getElementById('view-runs').hidden && document.getElementById('real-run-state')?.textContent==='completed' && !${JSON.stringify(runIds)}.includes(history.state.realWorkspace.runId)`));
    const runs=await(await fetch(base+'/api/workspace/runs')).json(),run=runs.find(r=>r.graph.recipe===kind+'_validate_export');assert.ok(run);runIds.push(run.id);
    assert.equal(await evaluate('document.querySelector(".real-predictions")'),null);
    assert.deepEqual(run.node_attempts.map(node=>node.type),['release','validate','publish']);
    const links=await evaluate('[...document.querySelectorAll("#real-runs-root a[download]")].map(a=>({text:a.textContent,href:a.href}))');
    const reportLink=links.find(a=>a.text==='validation-report.json');assert.ok(reportLink);
    const response=await fetch(reportLink.href);assert.equal(response.status,200);const validation=await response.json();
    assert.equal(validation.validation_summary[kind+'_count'],1);assert.equal(validation.validation_summary[kind==='pointcloud'?'point_count':'voxel_count'],kind==='pointcloud'?3:24);
    const sourceLink=links.find(a=>a.text==='Download verified frozen export');assert.ok(sourceLink);
    assert.deepEqual(Buffer.from(await(await fetch(sourceLink.href)).arrayBuffer()),releases[kind].bytes);
    fs.writeFileSync(path.join(report,kind+'-validation-report.json'),JSON.stringify(validation,null,2));
    await screenshot(kind+'-runs-390',390,844);await screenshot(kind+'-runs-1440',1440,900);
    check(kind+' edited/cloned graph, keyboard actual run and exact frozen downloads');
  }
  server.kill('SIGINT');await until(()=>server.exitCode!==null,'Application did not drain and close');
  server=launch('python3',['-u','app.py','--port',port,'--data',path.join(temporary,'data')],{cwd:root,stdio:['ignore','pipe','pipe']});
  let reopened='';server.stdout.on('data',chunk=>reopened+=chunk);server.stderr.on('data',chunk=>serverErrors+=chunk);
  await until(()=>reopened.includes('Tuldok:'));await reload();await until(()=>text('#real-run-state').then(t=>t==='completed'));
  const retained=await(await fetch(base+'/api/workspace/runs')).json();assert.deepEqual(retained.map(r=>r.id).sort(),runIds.sort());
  for(const kind of ['pointcloud','volume'])assert.deepEqual(Buffer.from(await(await fetch(releases[kind].url)).arrayBuffer()),releases[kind].bytes);
  assert.ok(!requests.some(url=>/\/predictions|\/expose-test/.test(url)));
  assert.deepEqual(errors,[]);assert.ok(!serverErrors.includes('Traceback'),serverErrors);
  check('both durable spatial runs and unchanged releases survive application restart');
  fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify({source_commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),dirty:!!execFileSync('git',['status','--porcelain'],{cwd:root,encoding:'utf8'}).trim(),command:'node tests/browser_workspace_spatial.cjs',checks,captures,native_check:nativeCheck,run_ids:runIds,training:false,scientific_claim:false,fixture_provenance:'Authored ordered PLY points and oriented uint8 scalar ramp; independent native readers',offline_canary:offlineCanary},null,2));
  console.log('PASS real spatial workspace gate:',report);
})().catch(async error=>{
  console.error(error);console.error('Application stderr:',serverErrors);
  if(evaluate)try{console.error(await evaluate('JSON.stringify({url:location.href,body:document.body.innerText.slice(-5000),frame:document.getElementById("catalog-frame")?.contentDocument?.body.innerText.slice(-4000)})'));}catch{}
  process.exitCode=1;
}).finally(()=>{if(ws)ws.close();for(const child of children.reverse())child.kill('SIGTERM');});
