// Prepared authenticated Runs acceptance. Requires the coordinated production hooks.
// Uses the existing retained fixture and normal app.py; no handler/data substitutes.
'use strict';
const assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const {spawn} = require('node:child_process');
const {waitForDebugger} = require('./browser_startup.cjs');
const fixtureAuth = require('./auth_helpers.cjs').authenticatedFixture();
const root = path.resolve(__dirname, '..'), children = [], profile = fs.mkdtempSync(path.join(os.tmpdir(), 'tuldok-retained-actual-browser-'));
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(check, message) { for (let i = 0; i < 300; i++) { if (await check()) return; await pause(50); } throw Error(message || 'Actual Runs acceptance timed out'); }
async function stop(child) {
  if (child.exitCode !== null || child.signalCode !== null) return;
  await new Promise(resolve => {
    const timer = setTimeout(() => child.kill('SIGKILL'), 5000);
    child.once('exit', () => { clearTimeout(timer); resolve(); }); child.kill('SIGINT');
  });
}
(async () => {
  if (process.env.TULDOK_ANALYSIS_HTTP !== '1' || !process.env.TULDOK_ANALYSIS_FIXTURE) throw Error('Explicit integrated acceptance and a prepared actual retained fixture are required.');
  const fixture = JSON.parse(fs.readFileSync(path.join(process.env.TULDOK_ANALYSIS_FIXTURE, 'fixture.json'), 'utf8'));
  let output = '', serverErrors = '';
  const server = spawn(process.env.PYTHON || 'python3', ['-u', 'app.py', '--port', '0', '--data', fixture.catalog_path], {cwd: root}); children.push(server);
  server.stdout.on('data', chunk => output += chunk); server.stderr.on('data', chunk => serverErrors += chunk);
  await until(() => /127\.0\.0\.1:(\d+)/.test(output), 'Actual app did not publish its local endpoint');
  const base = 'http://127.0.0.1:' + output.match(/127\.0\.0\.1:(\d+)/)[1];
  await fixtureAuth.register(base, fixture.catalog_path, root);
  const response = await fixtureAuth.fetch(base + '/api/agent/capabilities');
  assert.equal(response.status, 200);
  const capabilities = await response.json();
  const operation = capabilities.operations.find(item => item.id === 'runs.retained_analysis' || item.operation_id === 'runs.retained_analysis');
  assert.ok(operation, 'The coordinated retained-analysis operation must be registered before actual browser acceptance');
  const contract = operation.contracts.find(item => item.version === 1);
  assert.ok(contract?.sha256, 'The browser must use the exact named v1 contract');
  const query = async body => {
    const {run_id, ...arguments_} = body;
    const reply = await fixtureAuth.fetch(base + '/api/workspace/runs/' + run_id + '/retained-analysis', {
      method: 'POST', headers: {'Content-Type': 'application/json', 'Tuldok-Operation-Contract': 'runs.retained_analysis/1/' + contract.sha256}, body: JSON.stringify(arguments_)
    });
    assert.equal(reply.status, 200); return reply.json();
  };
  const expected = await query(fixture.request);
  const browser = spawn(process.env.BROWSER || '/usr/bin/chromium', ['--headless', '--no-sandbox', '--disable-gpu', '--remote-debugging-port=0', '--user-data-dir=' + profile, 'about:blank'], {stdio: 'ignore'}); children.push(browser);
  const debuggerPort = await waitForDebugger(browser, path.join(profile, 'DevToolsActivePort'));
  const targets = await (await fetch(`http://127.0.0.1:${debuggerPort}/json`)).json();
  const ws = new WebSocket(targets.find(item => item.type === 'page').webSocketDebuggerUrl);
  await new Promise(resolve => ws.addEventListener('open', resolve));
  let sequence = 0, held; const calls = new Map(), errors = [], remote = [], actualReplies = [];
  const send = (method, params = {}) => new Promise((resolve, reject) => { const id = ++sequence; calls.set(id, {resolve, reject}); ws.send(JSON.stringify({id, method, params})); });
  ws.addEventListener('message', event => {
    const value = JSON.parse(event.data);
    if (value.id) { const pending = calls.get(value.id); calls.delete(value.id); value.error ? pending.reject(Error(JSON.stringify(value.error))) : pending.resolve(value.result); }
    if (value.method === 'Runtime.exceptionThrown') errors.push(value.params.exceptionDetails.text);
    if (value.method === 'Network.requestWillBeSent' && /^https?:/.test(value.params.request.url) && !value.params.request.url.startsWith(base)) remote.push(value.params.request.url);
    if (value.method === 'Fetch.requestPaused') held = value.params;
    if (value.method === 'Network.responseReceived' && value.params.response.url.endsWith('/retained-analysis')) actualReplies.push(value.params.response.status);
  });
  const evaluate = async expression => {
    const value = await send('Runtime.evaluate', {expression, returnByValue: true, awaitPromise: true});
    if (value.exceptionDetails) throw Error(value.exceptionDetails.exception?.description || value.exceptionDetails.text);
    return value.result.value;
  };
  const host = '([...document.querySelectorAll("#real-runs-root h3")].find(node=>node.textContent==="Retained checkpoint analysis")?.parentElement)';
  const ready = () => evaluate(`!!${host}?.querySelector('svg') && ${host}?.getAttribute('aria-busy')==='false'`);
  await send('Runtime.enable'); await send('Network.enable'); await send('Page.enable');
  await fixtureAuth.browser(send, base);
  await send('Page.navigate', {url: base + '/workspaces'});
  await until(() => evaluate('!!document.querySelector("#dataset") && !document.querySelector("#dataset").disabled'));
  await evaluate('document.querySelector("#dataset").value="catalog";document.querySelector("#dataset").dispatchEvent(new Event("change",{bubbles:true}))');
  await until(() => evaluate('document.querySelector("#notice")?.textContent==="Collection ready."'));
  await evaluate('document.querySelector("#nav-runs").click()');
  await until(ready, 'Actual authenticated Runs did not mount the retained renderer');
  for (const point of expected.curve) assert.ok((await evaluate(`${host}.textContent`)).includes(`Epoch ${point.epoch}: ${point.value}`));
  await evaluate(`${host}.querySelectorAll('button')[0].focus()`);
  await send('Input.dispatchKeyEvent', {type: 'keyDown', key: 'Enter', code: 'Enter', text: '\r', windowsVirtualKeyCode: 13});
  await send('Input.dispatchKeyEvent', {type: 'keyUp', key: 'Enter', code: 'Enter', windowsVirtualKeyCode: 13});
  await until(ready);
  for (const row of expected.examples.rows) assert.ok((await evaluate(`${host}.querySelector('tbody').textContent`)).includes(row.example_id));
  await send('Emulation.setDeviceMetricsOverride', {width: 390, height: 844, deviceScaleFactor: 1, mobile: false}); await pause(100);
  assert.equal(await evaluate('document.documentElement.scrollWidth<=390'), true);
  // Hold an actual response after dispatch, navigate away, then release it.
  await send('Fetch.enable', {patterns: [{urlPattern: base + '/api/workspace/runs/' + fixture.run_id + '/retained-analysis', requestStage: 'Response'}]});
  await evaluate(`${host}.querySelectorAll('button')[1].click()`);
  await until(() => !!held, 'Expected an actual retained query response to pause');
  await evaluate('document.querySelector("#nav-data").click()');
  await send('Fetch.continueRequest', {requestId: held.requestId}); await send('Fetch.disable'); held = null;
  await pause(100);
  assert.equal(await evaluate('document.querySelector("#view-runs").hidden'), true);
  await evaluate('document.querySelector("#nav-runs").click()'); await until(ready);
  await send('Page.reload', {ignoreCache: true}); await until(ready);
  for (const point of expected.curve) assert.ok((await evaluate(`${host}.textContent`)).includes(`Epoch ${point.epoch}: ${point.value}`));
  assert.deepEqual(errors, []); assert.deepEqual(remote, []);
  assert.ok(actualReplies.includes(200));
  console.log(JSON.stringify({status: 'passed', evidence: 'actual-PostgreSQL-native-Run-authenticated-Runs-browser', run_id: fixture.run_id, evaluation_sha256: fixture.request.evaluation_sha256, exact_curve: expected.curve, checks: ['actual named query', 'retained numeric oracle', 'linked keyboard example table', '390px layout', 'held real response after navigation', 'cache-bypassed page reopen', 'local chart assets']}, null, 2));
  ws.close();
})().catch(error => { console.error(error); process.exitCode = 1; }).finally(async () => {
  for (const child of children.reverse()) await stop(child);
  fs.rmSync(profile, {recursive: true, force: true});
});
