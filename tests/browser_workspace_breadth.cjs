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
  report = qaDirectory(root, "workspace-breadth"),
  temporary = fs.mkdtempSync(path.join(os.tmpdir(), "tuldok-workspace-breadth-")),
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
        if (${frame}) {
          const frameBox=document.getElementById('catalog-frame').getBoundingClientRect(), childBox=el.getBoundingClientRect();
          window.scrollBy(0, frameBox.top+childBox.top+childBox.height/2-innerHeight/2);
          await new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)));
        }
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
      mode: "real embedded existing Data task editors and exports; authored fixtures",
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
  const frame = expression => evaluate(`${doc(true)}.defaultView.eval(${JSON.stringify(expression)})`);
  const api = async (route,body) => body===undefined ? (await fetch(base+'/api/workbench/'+route)).json() : post('/api/workbench/'+route,body);
  async function openRow(row) {
    await frame('openRecord('+JSON.stringify(row.id)+')');
    await until(()=>frame('current?.id==='+JSON.stringify(row.id)+' && !responseListBusy && !preferenceListBusy'));
  }
  async function panel(selector) { await evaluate(`for(let e=${element(selector,true)};e;e=e.parentElement)if(e.tagName==='DETAILS')e.open=true`); }
  async function captureData(name, selector) {
    await panel(selector);
    for(const width of [1440,390]) {
      await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});
      await evaluate(`${element(selector,true)}.scrollIntoView({block:'start'})`);
      await screenshot(name+'-'+width,width,900);
      assert.ok(await evaluate(`${doc(true)}.documentElement.scrollWidth<=${doc(true)}.defaultView.innerWidth+1`));
    }
    await send('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
  }
  async function saved() { await until(()=>frame('!dirty && !document.getElementById("editor").dataset.busy')); }
  async function saveRecord() { await select('#record-review','human_reviewed',true);await focus('#save',true);await key('Enter');await saved(); }
  async function tools(selector) { await click('.embed-toolbar button',true);await panel(selector); }
  async function exportRecords(rows,format,name) {
    await frame('refresh()');
    await frame('document.querySelectorAll("#records input[type=checkbox]").forEach(el=>{if(el.checked)el.click()})');
    for(const row of rows) { const actual=await api('records/'+row.id);await click('input[aria-label='+JSON.stringify('Select '+actual.name)+']',true); }
    await tools('#release-form');await select('#release-format',format,true);
    await fill('#train',format==='canonical_v1'?'100':'34',true);await fill('#validation',format==='canonical_v1'?'0':'33',true);await fill('#test',format==='canonical_v1'?'0':'33',true);
    await click('#preview-release',true);await until(()=>frame('!releaseBusy'));
    assert.equal(await evaluate(`${element('#freeze-release',true)}.disabled`),false,await text('#release-preview',true));
    await click('#freeze-release',true);await until(()=>evaluate(`!!${element('#release-result a',true)}`));
    const url=await evaluate(`${element('#release-result a',true)}.href`), file=path.join(report,name+'.zip');
    const response=await fetch(url);assert.equal(response.status,200);fs.writeFileSync(file,Buffer.from(await response.arrayBuffer()));
    await key('Escape');return file;
  }
  const entity=await api('import',{kind:'text',name:'Unicode entities',text:'Cafe\u0301 😀 山',groups:['breadth-entity'],rights:'Authored QA'});
  await openRow(entity);await select('#task','text_entities',true);await fill('#label','emoji',true);await fill('#span-start','5',true);await fill('#span-end','6',true);await click('#add-offset-span',true);
  const draft=await frame('JSON.stringify({targets,dirty,selection:[...selected.keys()]})');
  await nav('pipeline');await nav('runs');await nav('data');assert.equal(await frame('JSON.stringify({targets,dirty,selection:[...selected.keys()]})'),draft);
  await saveRecord();let stored=await api('records/'+entity.id);assert.deepEqual(stored.annotation.spans,[{label:'emoji',start:5,end:6}]);
  await click('#history',true);await until(()=>evaluate(`${element('#history-output',true)}.hidden===false`));assert.match(await text('#history-output',true),/text_entities/);
  await captureData('entities','#editor');
  const stale=await fetch(base+'/api/workbench/records/'+entity.id,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...stored,revision:entity.revision})});assert.equal(stale.status,409);
  await exportRecords([stored],'canonical_v1','entities');check('Embedded Unicode entity spans, keyboard review/history and retained draft through three workspaces');
  const corpus=[];
  for(let i=0;i<3;i++) {
    await tools('#import-form');await fill('#import-name','Corpus '+i,true);await fill('#import-group','breadth-corpus-'+i,true);
    await fill('#import-text',('Café 😀 山 document '+i+' with exact newlines.\n').repeat(5),true);
    await focus('#import-form button',true);await key('Enter');await until(()=>text('#notice',true).then(t=>t==='Record imported.'));await key('Escape');
    await select('#task','text_corpus',true);await fill('#corpus-note','Reviewed complete document '+i,true);await saveRecord();corpus.push(await frame('current'));
  }
  await captureData('corpus','#editor');
  const corpusFile=await exportRecords(corpus,'text_corpus_v1','corpus');
  execFileSync('python3',['-c',"import json,zipfile,sys;z=zipfile.ZipFile(sys.argv[1]);m=json.loads(z.read('manifest.json'));assert m['format']=='text_corpus_v1';assert len(m['records'])==3;assert all('Café 😀 山' in z.read(s+'.txt').decode() for s in ('train','validation','test'))",corpusFile],{cwd:root});
  check('Embedded corpus import/review and existing byte-corpus export preserve Unicode');
  const generated=await api('generate',{recipe:'rectangles-v1',seed:926,count:3});const captions=[];
  for(const item of generated.created) {
    const row=typeof item==='string'?await api('records/'+item):item;
    await openRow(row);await select('#task','image_caption',true);await fill('#caption','Authored scene '+row.id.slice(0,5)+' · Café 😀',true);await saveRecord();captions.push(await frame('current'));
  }
  await captureData('captions','#editor');
  const captionFile=await exportRecords(captions,'image_caption_v1','captions');
  execFileSync('python3',['-c',"import json,zipfile,sys;z=zipfile.ZipFile(sys.argv[1]);m=json.loads(z.read('manifest.json'));assert m['format']=='image_caption_v1';assert len(m['records'])==3;assert all('Café 😀' in z.read(s+'/metadata.jsonl').decode() for s in ('train','val','test'))",captionFile],{cwd:root});
  check('Embedded image caption editor/review and existing imagefolder export retain captions');
  await openRow(await api('records/'+entity.id));await panel('#responses-panel');
  const exact='\ufeff e\u0301\r\n😀  ';const answers=[];
  for(const content of [exact,'Alternative 山 answer']) {
    await click('#response-new',true);await select('#response-entry-format','json',true);await fill('#response-completion',JSON.stringify(content),true);
    await select('#response-review','human_reviewed',true);await focus('#response-save',true);await key('Enter');
    await until(()=>frame('!responseBusy && !responseListBusy && !responseDirty'));
    answers.push((await api('records/'+entity.id+'/responses')).responses.find(row=>row.completion===content));
    await click('#response-cancel',true);
  }
  await captureData('answers','#responses-panel');
  assert.ok(answers.every(Boolean));await frame('document.querySelectorAll("#response-list input[type=checkbox]").forEach(e=>e.click())');
  await tools('#response-release-panel');await click('#response-preview',true);await until(()=>frame('!responseReleaseBusy && !!responsePreview'));
  assert.equal(await frame('responsePreview.eligible'),true);await focus('#response-freeze',true);await key('Enter');await until(()=>evaluate(`!!${element('#response-release-result a',true)}`));
  const responseURL=await evaluate(`${element('#response-release-result a',true)}.href`);fs.writeFileSync(path.join(report,'responses.zip'),Buffer.from(await(await fetch(responseURL)).arrayBuffer()));await key('Escape');
  await panel('#preferences-panel');await click('#preference-refresh',true);await until(()=>frame('!preferenceListBusy'));
  await click('#preference-new',true);await select('#preference-left',answers[0].id,true);await select('#preference-right',answers[1].id,true);await select('#preference-outcome','left',true);await fill('#preference-rationale','Compared exact Unicode and alternative response.',true);
  await nav('pipeline');await nav('data');assert.equal(await frame('preferenceDirty'),true);assert.match(await evaluate(`${element('#preference-rationale',true)}.value`),/Compared exact/);
  await select('#preference-review','human_reviewed',true);await focus('#preference-save',true);await key('Enter');await until(()=>frame('!preferenceBusy && !preferenceListBusy && !preferenceDirty'));
  await captureData('preferences','#preferences-panel');
  await frame('document.querySelector("#preference-list input[type=checkbox]").click()');await tools('#preference-release-panel');await focus('#preference-preview',true);await key('Enter');await until(()=>frame('!preferenceReleaseBusy && !!preferencePreview'));assert.equal(await frame('preferencePreview.eligible'),true);
  await focus('#preference-freeze',true);await key('Enter');await until(()=>evaluate(`!!${element('#preference-release-result a',true)}`));
  const preferenceURL=await evaluate(`${element('#preference-release-result a',true)}.href`);fs.writeFileSync(path.join(report,'preferences.zip'),Buffer.from(await(await fetch(preferenceURL)).arrayBuffer()));await key('Escape');
  const exactRows=execFileSync('python3',['-c',"import json,zipfile,sys;out=[]\nfor p in sys.argv[1:]:\n z=zipfile.ZipFile(p);out.append([json.loads(line) for name in z.namelist() if name.endswith('.jsonl') for line in z.read(name).decode().splitlines()])\nprint(json.dumps(out))",path.join(report,'responses.zip'),path.join(report,'preferences.zip')],{cwd:root,encoding:'utf8'});
  assert.ok(JSON.stringify(JSON.parse(exactRows)).includes(JSON.stringify(exact).slice(1,-1)));check('Embedded answer/preference forms preserve exact strings, human judgments and draft navigation; existing adapters export both');
  await screenshot('catalog-breadth-1440',1440,900);await screenshot('catalog-breadth-390',390,844);
  assert.ok(await evaluate(`${doc(true)}.documentElement.scrollWidth<=${doc(true)}.defaultView.innerWidth+1`));
  await reload();await until(()=>text('#catalog-status').then(t=>t?.includes('Restored exact saved catalog context')));await openRow(await api('records/'+entity.id));
  assert.equal((await api('records/'+entity.id+'/responses')).responses.length,2);assert.equal((await api('records/'+entity.id)).review,'human_reviewed');
  assert.deepEqual(errors,[]);check('All embedded owners remain usable after reload; desktop and narrow shell have no horizontal overflow');
  fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify({source_commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),dirty:!!execFileSync('git',['status','--porcelain'],{cwd:root,encoding:'utf8'}).trim(),command:'node tests/browser_workspace_breadth.cjs',offline_canary:offlineCanary,checks,captures,fixture_provenance:'Authored local records; no model calls',qualification:'Shell integration and downloaded strings; pinned consumer suites retain independent qualification ownership.'},null,2));
  console.log('PASS embedded existing-task breadth:',report);
})().catch(async error=>{
  console.error(error);
  console.error("Application stderr:", serverErrors);
  if(evaluate)try{console.error(await evaluate('JSON.stringify({url:location.href,status:document.getElementById("workspace-status")?.textContent,body:document.body.innerText.slice(-7000),frame:document.getElementById("catalog-frame")?.contentDocument?.body.innerText.slice(-2000)})'));}catch{}
  process.exitCode=1;
}).finally(()=>{if(ws)ws.close();for(const child of children.reverse())child.kill("SIGTERM");});
