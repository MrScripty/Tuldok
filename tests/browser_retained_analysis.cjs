// Actual Chromium renderer/CSP test over authored boundary data. No DB or Runs claim.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {spawn} = require('node:child_process');
const {waitForDebugger} = require('./browser_startup.cjs');
const root = path.resolve(__dirname, '..');
const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'tuldok-retained-renderer-'));
const children = [];
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(test) { for (let i = 0; i < 200; ++i) { if (await test()) return; await pause(50); } throw Error('Renderer assertion timed out'); }
(async () => {
  let output = '', serverError = '';
  const server = spawn(process.env.PYTHON || 'python3', ['-u', 'tests/retained_analysis_browser_fixture.py'], {cwd: root}); children.push(server);
  server.stdout.on('data', chunk => output += chunk); server.stderr.on('data', chunk => serverError += chunk);
  await until(() => /^\d+\n/.test(output));
  const base = 'http://127.0.0.1:' + output.trim();
  const browser = spawn(process.env.BROWSER || '/usr/bin/chromium', ['--headless', '--no-sandbox', '--disable-gpu', '--remote-debugging-port=0', '--user-data-dir=' + profile, 'about:blank'], {stdio: 'ignore'}); children.push(browser);
  // Headless/no-sandbox is confined to this isolated disposable browser fixture;
  // it is not a product startup configuration or an application sandbox claim.
  const port = await waitForDebugger(browser, path.join(profile, 'DevToolsActivePort'));
  const targets = await (await fetch(`http://127.0.0.1:${port}/json`)).json();
  const ws = new WebSocket(targets.find(target => target.type === 'page').webSocketDebuggerUrl);
  await new Promise(resolve => ws.addEventListener('open', resolve));
  let id = 0; const calls = new Map(), errors = [], external = [];
  ws.addEventListener('message', event => {
    const value = JSON.parse(event.data);
    if (value.id) { const call = calls.get(value.id); calls.delete(value.id); value.error ? call.reject(Error(JSON.stringify(value.error))) : call.resolve(value.result); }
    if (value.method === 'Runtime.exceptionThrown') errors.push(value.params.exceptionDetails.text);
    if (value.method === 'Network.requestWillBeSent' && !value.params.request.url.startsWith(base) && !value.params.request.url.startsWith('data:')) external.push(value.params.request.url);
  });
  const send = (method, params = {}) => new Promise((resolve, reject) => { const next = ++id; calls.set(next, {resolve, reject}); ws.send(JSON.stringify({id: next, method, params})); });
  const evaluate = async expression => {
    const result = await send('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true});
    if (result.exceptionDetails) throw Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    return result.result.value;
  };
  await send('Runtime.enable'); await send('Network.enable'); await send('Page.enable');
  await send('Page.navigate', {url: base});
  const ready = () => evaluate('!!document.querySelector("svg") && document.querySelector("#analysis").getAttribute("aria-busy")==="false"');
  await until(async () => {
    const alert = await evaluate('document.querySelector("[role=alert]")?.textContent');
    if (alert) throw Error(alert);
    return ready();
  });
  assert.equal(await evaluate('document.querySelector("[role=alert]")?.textContent || ""'), '');
  assert.match(await evaluate('document.body.textContent'), /Epoch 1: 0.125/);
  assert.match(await evaluate('document.querySelector("tbody").textContent'), /frozen-example-first/);
  await evaluate('document.querySelectorAll("button")[1].focus()');
  await send('Input.dispatchKeyEvent', {type: 'keyDown', key: 'Enter', code: 'Enter', text: '\r', windowsVirtualKeyCode: 13});
  await send('Input.dispatchKeyEvent', {type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13});
  await until(() => evaluate('document.querySelector("tbody")?.textContent.includes("frozen-example-second") && document.querySelector("#analysis").getAttribute("aria-busy")==="false"')).catch(async error => {
    throw Error(error.message + ' ' + JSON.stringify(await evaluate('({text:document.body.textContent,csp:fixtureCsp,requests:fixtureRequests,selection:fixtureSelections})')) + ' errors=' + JSON.stringify(errors));
  });
  assert.equal(await evaluate('document.activeElement.tagName'), 'H3');
  assert.equal(await evaluate('fixtureSelections.length'), 1);
  const point = await evaluate('(()=>{const b=document.querySelector("g.mark-symbol path").getBoundingClientRect();return {x:b.x+b.width/2,y:b.y+b.height/2}})()');
  await send('Input.dispatchMouseEvent', {type: 'mousePressed', button: 'left', clickCount: 1, ...point});
  await send('Input.dispatchMouseEvent', {type: 'mouseReleased', button: 'left', clickCount: 1, ...point});
  await until(() => evaluate('document.querySelector("tbody")?.textContent.includes("frozen-example-first") && document.querySelector("#analysis").getAttribute("aria-busy")==="false"'));
  assert.equal(await evaluate('fixtureSelections.length'), 2);
  await evaluate('[...document.querySelectorAll("button")].find(button=>button.textContent==="Next examples").click()');
  await until(() => evaluate('fixtureAdapter.selection()?.offset === 1'));
  assert.match(await evaluate('document.querySelector("tbody").textContent'), /frozen-example-first-1/);
  await evaluate('document.querySelector("input").click()'); await until(ready);
  assert.equal(await evaluate('fixtureAdapter.selection().errors_only'), true);
  await send('Emulation.setDeviceMetricsOverride', {width: 390, height: 844, deviceScaleFactor: 1, mobile: false}); await pause(200);
  assert.equal(await evaluate('document.documentElement.scrollWidth <= 390'), true);
  await evaluate('fixtureMode="stale"; void fixtureStart()');
  await until(() => evaluate('fixturePending.length === 1'));
  await evaluate('fixtureMode="revoked"; void fixtureStart()');
  await until(() => evaluate('!!document.querySelector("[role=alert]")'));
  await evaluate('fixturePending.shift()()'); await pause(100);
  assert.equal(await evaluate('!!document.querySelector("svg,tbody")'), false);
  assert.equal(await evaluate('fixtureAdapter.selection()'), null);
  for (const mode of ['malformed', 'oversized', 'support-mismatch', 'ordinal-mismatch', 'count-mismatch', 'missing-provenance', 'missing-definition', 'missing-column-type']) {
    await evaluate(`fixtureMode=${JSON.stringify(mode)}; void fixtureStart()`);
    await until(() => evaluate('document.querySelector("[role=alert]")?.textContent.includes("invalid")'));
    assert.equal(await evaluate('!!document.querySelector("svg,tbody")'), false);
  }
  for (const mode of ['malformed', 'oversized']) {
    await evaluate(`fixtureMode="normal"; fixtureSpecMode=${JSON.stringify(mode)}; void fixtureStart()`);
    await until(() => evaluate('!!document.querySelector("[role=alert]")'));
    assert.match(await evaluate('document.querySelector("[role=alert]").textContent'), mode === 'oversized' ? /specification exceeds/ : /specification identity/);
    assert.equal(await evaluate('!!document.querySelector("svg,tbody")'), false);
    assert.equal(await evaluate('fixtureRequests.at(-1).aborted()'), true);
  }
  await evaluate('fixtureSpecMode="normal"');
  await evaluate('fixtureMode="normal"; void fixtureStart()'); await until(ready);
  const downloadPath = path.join(profile, 'downloads'); fs.mkdirSync(downloadPath);
  await send('Browser.setDownloadBehavior', {behavior: 'allow', downloadPath});
  await evaluate('[...document.querySelectorAll("button")].find(button=>button.textContent==="Export this page").click()');
  await until(() => fs.existsSync(path.join(downloadPath, 'retained-analysis-page.json')));
  const exported = JSON.parse(fs.readFileSync(path.join(downloadPath, 'retained-analysis-page.json'), 'utf8'));
  assert.deepEqual(exported.curve.map(point => point.value), [.125, .375]);
  assert.equal(exported.provenance.evaluation_sha256, 'd'.repeat(64));
  await evaluate('fixtureMode="revoked"; [...document.querySelectorAll("button")].find(button=>button.textContent==="Export this page").click()');
  await until(() => evaluate('document.querySelector("[role=alert]")?.textContent.includes("export failed")'));
  assert.equal(await evaluate('!!document.querySelector("svg,tbody")'), false);
  assert.equal(await evaluate('fixtureRequests.at(-1).exported'), true);
  await send('Page.reload', {ignoreCache: true}); await until(ready);
  assert.match(await evaluate('document.querySelector("tbody").textContent'), /frozen-example-first/);
  assert.deepEqual(await evaluate('fixtureCsp'), []);
  assert.deepEqual(errors, []); assert.deepEqual(external, []);
  await evaluate('fixtureAdapter.dispose()');
  assert.equal(await evaluate('document.querySelector("#analysis").childElementCount'), 0);
  console.log(JSON.stringify({status: 'passed', evidence: 'actual-headless-Chromium-authored-renderer-fixture', checks: ['strict CSP/interpreter', 'self-hosted/offline external assets', 'exact numbers', 'keyboard linked selection/focus', 'visible error filter', '390px layout', 'stale reply after revocation', 'malformed/oversized response and spec rejection', 'support/ordinal/provenance/type validation', 'fresh export authorization path', 'cold page reopen', 'dispose']}, null, 2));
  ws.close();
})().catch(error => { console.error(error); process.exitCode = 1; }).finally(async () => {
  for (const child of children.reverse()) {
    if (child.exitCode !== null || child.signalCode !== null) continue;
    await new Promise(resolve => {
      const timer = setTimeout(() => child.kill('SIGKILL'), 3000);
      child.once('exit', () => { clearTimeout(timer); resolve(); });
      child.kill('SIGTERM');
    });
  }
  fs.rmSync(profile, {recursive: true, force: true});
});
