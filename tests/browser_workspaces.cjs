'use strict';
const fixtureAuth = require('./auth_helpers.cjs').authenticatedFixture();
const fetch = fixtureAuth.fetch;
// Real Chromium interactions, no npm dependency, no model or training execution.
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
  report = qaDirectory(root, "workspaces"),
  temporary = fs.mkdtempSync(path.join(os.tmpdir(), "tuldok-workspaces-")),
  children = [];
const errors = [],
  posts = [],
  captures = [],
  checks = [];
let ws, send, evaluate;
const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function until(fn, message = "Timed out") {
  for (let i = 0; i < 150; i++) {
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
  const server = launch(
    "python3",
    ["-u", "app.py", "--port", "0", "--data", path.join(temporary, "data")],
    { cwd: root, stdio: ["ignore", "pipe", "pipe"] },
  );
  let output = "",
    serverErrors = "";
  server.stdout.on("data", (chunk) => (output += chunk));
  server.stderr.on("data", (chunk) => (serverErrors += chunk));
  const port = await until(() => output.match(/127\.0\.0\.1:(\d+)/)?.[1]),
    base = "http://127.0.0.1:" + port;
  await fixtureAuth.register('http://127.0.0.1:'+port,path.join(temporary,'data'),root);
  const browser = launch(
    process.env.BROWSER || "/usr/bin/chromium",
    [
      "--headless",
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
    pausedRequest = null;
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
    await evaluate(`${element(selector, frame)}.scrollIntoView({block:'center'})`);
    // Closing a dialog and scrolling an embedded owner can move its hit target
    // at the next paint. Dispatch physical input only after that layout settles.
    await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
    const box = await evaluate(
      `(()=>{const el=${element(selector, frame)};if(!el)throw Error('Missing '+${JSON.stringify(selector)});const r=el.getBoundingClientRect(),f=${frame ? 'document.getElementById("catalog-frame").getBoundingClientRect()' : "{left:0,top:0}"};const hit=${doc(frame)}.elementFromPoint(r.x+r.width/2,r.y+r.height/2);if(!el.contains(hit))throw Error('Click target obscured: '+${JSON.stringify(selector)});return {x:r.x+r.width/2+f.left,y:r.y+r.height/2+f.top};})()`,
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
    await click("#nav-" + name);
    await until(() =>
      evaluate(`!document.getElementById('view-${name}').hidden`),
    );
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
      mode: "fixture unless catalog named",
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
  // A failed response is a visible error, never silently replaced by success fixtures.
  await send("Fetch.enable", {
    patterns: [{ urlPattern: "*workspace-fixtures.json" }],
  });
  await fixtureAuth.browser(send,'http://127.0.0.1:'+port);
  await send("Page.navigate", { url: base + "/workspaces" });
  await until(() => pausedRequest);
  assert.match(await text("#workspace-status"), /Loading/);
  check("loading state before fixture response");
  await send("Fetch.failRequest", {
    requestId: pausedRequest,
    errorReason: "Failed",
  });
  await until(() => evaluate('!document.getElementById("retry-load").hidden'));
  assert.match(await text("#workspace-error"), /fetch/i);
  await screenshot("loading-error-390", 390, 844);
  await send("Fetch.disable");
  await click("#retry-load");
  await until(() => evaluate('!!document.getElementById("fixture-label")'));
  check("fixture load failure and real retry");
  await screenshot("data-1440", 1440, 900);
  await screenshot("data-1024", 1024, 768);
  await screenshot("data-390", 390, 844);
  await screenshot("data-zoom200", 720, 450);
  await send("Emulation.setDeviceMetricsOverride", {
    width: 1440,
    height: 900,
    deviceScaleFactor: 1,
    mobile: false,
  });
  for (const kind of [
    "text",
    "audio",
    "mesh",
    "point_cloud",
    "volume",
    "sequence",
    "image",
  ]) {
    await click(`[data-record="fixture-${kind}"]`);
    assert.match(
      await text(".source-preview"),
      kind === "audio" ? /playback unavailable/ : /.*/,
    );
  }
  check("all seven modality/subtype fixture records and capability states");
  await click('[data-select="fixture-image"]');
  await fill("#fixture-label", "triangle");
  await nav("pipeline");
  await nav("data");
  assert.equal(
    await evaluate('document.getElementById("fixture-label").value'),
    "triangle",
  );
  assert.match(await text("#context"), /1 selected/);
  assert.match(await text("#fixture-dirty"), /Unsaved/);
  await select("#dataset", "catalog");
  assert.equal(
    await evaluate('document.getElementById("leave-dialog").open'),
    true,
  );
  await key("Escape");
  assert.equal(
    await evaluate('document.getElementById("dataset").value'),
    "fixtures",
  );
  assert.equal(await evaluate("document.activeElement.id"), "dataset");
  await select("#dataset", "catalog");
  await click("#keep-editing");
  assert.equal(
    await evaluate('document.getElementById("fixture-label").value'),
    "triangle",
  );
  await focus("#fixture-label");
  await key("Tab");
  assert.equal(
    await evaluate("document.activeElement.textContent"),
    "Save fixture draft",
  );
  await key("Enter");
  await until(() =>
    text("#fixture-dirty").then((x) => x === "Saved fixture draft"),
  );
  check(
    "draft/selection retained across workspaces, discard dialog Escape, keyboard save",
  );
  await nav("runs");
  assert.match(await text("#runs-root"), /No fixture runs yet/);
  check("empty Runs state");
  await nav("pipeline");
  await focus('[data-node="node-3"]');
  await key("Enter");
  await fill("#train-epochs", "7");
  assert.match(await text("#graph-dirty"), /Unsaved/);
  assert.equal(
    await evaluate('document.getElementById("fixture-run").disabled'),
    true,
  );
  await click("#graph-validate");
  assert.equal(
    await evaluate('document.getElementById("train-epochs").value'),
    "7",
  );
  await fill("#train-epochs", "8");
  assert.match(await text("#preview-status"), /stale/);
  await click("#graph-undo");
  assert.equal(
    await evaluate('document.getElementById("train-epochs").value'),
    "7",
  );
  await click("#graph-redo");
  assert.equal(
    await evaluate('document.getElementById("train-epochs").value'),
    "8",
  );
  await click("#graph-save");
  await click("#graph-validate");
  await screenshot("pipeline-1440", 1440, 900);
  await screenshot("pipeline-1024", 1024, 768);
  await screenshot("pipeline-390", 390, 844);
  await screenshot("pipeline-zoom200", 720, 450);
  await send("Emulation.setDeviceMetricsOverride", {
    width: 1440,
    height: 900,
    deviceScaleFactor: 1,
    mobile: false,
  });
  await click("#graph-clone");
  assert.match(
    await evaluate('document.getElementById("graph-name").value'),
    /copy/,
  );
  await click("#graph-undo");
  await click("#graph-connections summary");
  await click('[data-edge="0"]');
  await click("#graph-validate");
  assert.match(await text("#graph-validation"), /connect exactly one/);
  assert.equal(
    await evaluate('document.getElementById("fixture-run").disabled'),
    true,
  );
  await select("#edge-from", "node-1");
  await select("#edge-to", "node-3");
  await click("#connect-form button");
  assert.match(await text("#workspace-status"), /incompatible/);
  await select("#edge-to", "node-2");
  await focus("#connect-form button");
  await key("Enter");
  await click("#graph-validate");
  assert.match(await text("#graph-validation"), /valid/);
  await select("#node-definition", "audio");
  await click("#node-add");
  await click("#graph-validate");
  assert.match(await text("#graph-validation"), /Unavailable/);
  await click("#node-remove");
  await click("#graph-save");
  await click("#graph-validate");
  check(
    "graph parameters, undo/redo, clone, add/remove, compatible reconnect and unavailable node refusal",
  );
  const snapshot = await evaluate(
    "JSON.parse(localStorage.getItem(WorkspaceService.STORE_KEY)).graph",
  );
  await reload();
  await until(() => evaluate('!!document.getElementById("graph-save")'));
  assert.equal(
    await evaluate('document.getElementById("graph-dirty").textContent'),
    "Saved fixture",
  );
  assert.equal(
    await evaluate('document.getElementById("fixture-run").disabled'),
    true,
  );
  assert.deepEqual(
    await evaluate(
      "JSON.parse(localStorage.getItem(WorkspaceService.STORE_KEY)).graph",
    ),
    snapshot,
  );
  check("saved graph reload and stale validation after reload");
  await click("#graph-validate");
  await click("#fixture-run");
  await until(() => evaluate('!document.getElementById("view-runs").hidden'));
  assert.match(await text("#runs-root"), /75%/);
  await click('[data-cell="none"]');
  assert.match(await text("#prediction-heading"), /No examples/);
  assert.equal(
    await evaluate('!!document.getElementById("open-correction")'),
    false,
  );
  await click('[data-cell="error"]');
  assert.match(await text(".prediction"), /current draft|Current fixture/);
  assert.match(await text(".prediction"), /annotation r1/);
  assert.match(await text(".prediction"), /annotation r2/);
  await screenshot("runs-1440", 1440, 900);
  await screenshot("runs-1024", 1024, 768);
  await screenshot("runs-390", 390, 844);
  await screenshot("runs-zoom200", 720, 450);
  await send("Emulation.setDeviceMetricsOverride", {
    width: 1440,
    height: 900,
    deviceScaleFactor: 1,
    mobile: false,
  });
  const oldRun = await evaluate(
    "JSON.parse(localStorage.getItem(WorkspaceService.STORE_KEY)).runs[0]",
  );
  await click("#open-correction");
  await until(() => evaluate('!document.getElementById("view-data").hidden'));
  assert.equal(
    await evaluate('document.getElementById("fixture-label").value'),
    "triangle",
  );
  await fill("#fixture-label", "corrected square");
  await focus("#fixture-annotation button");
  await key("Enter");
  await nav("runs");
  assert.deepEqual(
    await evaluate(
      "JSON.parse(localStorage.getItem(WorkspaceService.STORE_KEY)).runs[0]",
    ),
    oldRun,
  );
  check(
    "cell meaning, exact frozen/current revisions and correction preserves historical run",
  );
  // Every scenario is explicit, with no timer masquerading as real work.
  for (const scenario of ["failed", "cancelled", "unknown", "running"]) {
    await nav("pipeline");
    await click("#graph-validate");
    await select("#run-scenario", scenario);
    await click("#fixture-run");
    await until(() => evaluate('!document.getElementById("view-runs").hidden'));
    assert.match(
      await text("#runs-root"),
      new RegExp(
        scenario === "unknown"
          ? "Completion unknown"
          : scenario === "running"
            ? "Total work.*unknown"
            : scenario === "failed"
              ? "Example failure"
              : "cancelled",
      ),
    );
  }
  await click("#cancel-fixture");
  assert.match(await text("#runs-root"), /scenario cancelled/);
  check(
    "failed/cancelled/unknown/running scenarios and explicit fixture cancellation",
  );
  assert.equal(posts.length, 0, "Fixture UI must not write to any real API");
  check("all fixture interactions issue zero POST requests");
  // Existing real owner remains mounted, keeping exact selections and drafts.
  await nav("data");
  await select("#dataset", "catalog");
  await until(() =>
    evaluate(
      '!!document.getElementById("catalog-frame").contentWindow.TuldokWorkspaceData',
    ),
  );
  await until(() =>
    text("#notice", true).then((x) => x === "Collection ready."),
  );
  await click(".embed-toolbar button", true);
  await click("#import-form", true).catch(() => {});
  await evaluate(
    'document.getElementById("catalog-frame").contentDocument.getElementById("import-form").closest("details").open=true',
  );
  await fill("#import-name", "M1 authored keyboard record", true);
  await fill("#import-text", "A local example for keyboard review.", true);
  await fill("#import-group", "m1-authored-family", true);
  await focus("#import-form button", true);
  await key("Enter");
  await until(() =>
    text("#notice", true).then((x) => x === "Record imported."),
  );
  await key("Escape");
  assert.equal(
    await evaluate(
      'document.getElementById("catalog-frame").contentDocument.activeElement.textContent',
    ),
    "Import / generate / release",
  );
  await click(".record input", true);
  await select("#task", "text_classification", true);
  await fill("#label", "authored-class", true);
  const before = await evaluate(
    'document.getElementById("catalog-frame").contentWindow.TuldokWorkspaceData.snapshot()',
  );
  assert.equal(before.dirty, true);
  assert.equal(before.selection.length, 1);
  await nav("pipeline");
  await nav("runs");
  await nav("data");
  const after = await evaluate(
    'document.getElementById("catalog-frame").contentWindow.TuldokWorkspaceData.snapshot()',
  );
  assert.deepEqual(after, before);
  assert.equal(
    await evaluate(
      'document.getElementById("catalog-frame").contentDocument.getElementById("label").value',
    ),
    "authored-class",
  );
  await select("#record-review", "human_reviewed", true);
  await focus("#save", true);
  await key("Enter");
  await until(() =>
    text("#notice", true).then((x) => x === "Annotation saved."),
  );
  check(
    "real catalog keyboard import/save/review and retained draft/selection through all workspaces",
  );
  await screenshot("catalog-1440", 1440, 900);
  await screenshot("catalog-390", 390, 844);
  assert.ok(
    await evaluate(
      '(()=>{const d=document.getElementById("catalog-frame").contentDocument;return d.documentElement.scrollWidth<=d.defaultView.innerWidth+1;})()',
    ),
  );
  // Repeated modal actions restore focus and do not create requests.
  for (let i = 0; i < 3; i++) {
    await click(".embed-toolbar button", true);
    await key("Escape");
    assert.equal(
      await evaluate(
        'document.getElementById("catalog-frame").contentDocument.getElementById("embed-tools").open',
      ),
      false,
    );
  }
  check("responsive current catalog and repeated modal focus restoration");
  const savedCatalog = await evaluate(
    'document.getElementById("catalog-frame").contentWindow.TuldokWorkspaceData.snapshot()',
  );
  await reload();
  await until(() =>
    text("#catalog-status").then((value) =>
      value?.startsWith("Restored exact"),
    ),
  );
  assert.equal(
    await evaluate('document.getElementById("dataset").value'),
    "catalog",
  );
  assert.deepEqual(
    await evaluate(
      'document.getElementById("catalog-frame").contentWindow.TuldokWorkspaceData.snapshot()',
    ),
    savedCatalog,
  );
  check(
    "catalog reload restores only exact saved record and selection revisions",
  );
  await evaluate(
    `(()=>{const frame=document.getElementById('catalog-frame'),w=frame.contentWindow,original=w.fetch;window.restoreCatalogFetch=()=>w.fetch=original;let failed=false;w.fetch=(url,...args)=>{if(String(url).includes('/api/workbench/records?')&&!failed){failed=true;return Promise.reject(Error('Authored refresh failure'));}return original(url,...args);};frame.dispatchEvent(new Event('load'));})()`,
  );
  await until(() =>
    text("#catalog-status").then((value) =>
      value?.includes("collection refresh failed"),
    ),
  );
  await evaluate("restoreCatalogFetch()");
  await click(".record input", true);
  await until(() =>
    text("#context").then((value) =>
      value?.includes("0 exact revisions selected"),
    ),
  );
  await click(".record input", true);
  await until(() =>
    text("#context").then((value) =>
      value?.includes("1 exact revisions selected"),
    ),
  );
  check(
    "failed restore refresh releases its gate and later catalog context still updates",
  );
  // A changed saved reference must not silently open the newer revision.
  await evaluate(
    `(async()=>{const old=await(await fetch('/api/workbench/records/${savedCatalog.record.id}')).json();await fetch('/api/workbench/records/'+old.id,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...old,annotation:{label:'remote correction'},review:'draft'})});})()`,
  );
  await reload();
  await until(() =>
    text("#catalog-status").then((value) =>
      value?.includes("Remembered source changed"),
    ),
  );
  assert.equal(
    await evaluate(
      'document.getElementById("catalog-frame").contentWindow.TuldokWorkspaceData.snapshot().record',
    ),
    null,
  );
  assert.equal(
    await evaluate(
      'document.getElementById("catalog-frame").contentWindow.TuldokWorkspaceData.snapshot().selection.length',
    ),
    0,
  );
  check("stale catalog context remains an explicit conflict after reload");
  await select("#dataset", "fixtures");
  await nav("pipeline");
  await focus("#graph-save");
  await focus("#nav-runs");
  await key("Enter");
  await until(() => evaluate('!document.getElementById("view-runs").hidden'));
  await focus("#nav-pipeline");
  await key("Enter");
  await until(() => evaluate('!document.getElementById("view-pipeline").hidden'));
  assert.equal(await evaluate("document.activeElement.id"), "graph-save");
  await evaluate("history.back()");
  await until(() => evaluate('!document.getElementById("view-runs").hidden'));
  check("keyboard navigation focus restoration and browser Back");
  await click('[data-run="' + oldRun.id + '"]');
  const downloadDir = path.join(temporary, "downloads");
  fs.mkdirSync(downloadDir);
  await send("Browser.setDownloadBehavior", {
    behavior: "allow",
    downloadPath: downloadDir,
  });
  await click("#download-fixture");
  const download = path.join(downloadDir, oldRun.id + ".json");
  await until(() => fs.existsSync(download));
  const artifact = JSON.parse(fs.readFileSync(download));
  assert.equal(artifact.mode, "fixture");
  assert.equal(artifact.quality_claim, false);
  assert.equal(artifact.checkpoint, null);
  assert.deepEqual(artifact.prediction, oldRun.prediction);
  await reload();
  await until(() =>
    evaluate('!!document.querySelector(".run-item[aria-current=true]")'),
  );
  assert.equal(
    await evaluate(
      'document.querySelector(".run-item[aria-current=true]").dataset.run',
    ),
    oldRun.id,
  );
  check(
    "downloaded JSON remains fixture-labelled and selected run survives reload",
  );
  await evaluate(
    "localStorage.setItem(WorkspaceService.STORE_KEY,JSON.stringify({version:99}))",
  );
  await reload();
  await until(() =>
    evaluate('!document.getElementById("workspace-error").hidden'),
  );
  assert.match(await text("#workspace-error"), /unsupported/);
  assert.equal(
    await evaluate(
      "JSON.parse(localStorage.getItem(WorkspaceService.STORE_KEY)).version",
    ),
    99,
  );
  check("unsupported stored version refused without overwrite");
  assert.deepEqual(errors, []);
  assert.ok(!serverErrors.includes("Traceback"), serverErrors);
  fs.writeFileSync(
    path.join(report, "receipt.json"),
    JSON.stringify(
      {
        source_commit: execFileSync("git", ["rev-parse", "HEAD"], {
          cwd: root,
          encoding: "utf8",
        }).trim(),
        dirty: !!execFileSync("git", ["status", "--porcelain"], {
          cwd: root,
          encoding: "utf8",
        }).trim(),
        command: "node tests/browser_workspaces.cjs",
        browser: (await send("Browser.getVersion")).product,
        checks,
        captures,
        realPosts: posts.length,
        training: false,
      },
      null,
      2,
    ),
  );
  console.log("PASS workspace browser gate:", report);
})()
  .catch(async (error) => {
    console.error(error);
    if (evaluate)
      try {
        console.error(
          await evaluate(
            'JSON.stringify({url:location.href,status:document.getElementById("workspace-status")?.textContent,error:document.getElementById("workspace-error")?.textContent,active:document.activeElement?.outerHTML,body:document.body.innerText.slice(-1500)})',
          ),
        );
      } catch {}
    process.exitCode = 1;
  })
  .finally(() => {
    if (ws) ws.close();
    for (const child of children.reverse()) child.kill("SIGTERM");
  });
