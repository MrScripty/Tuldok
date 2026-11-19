'use strict';
// Serving a trained model on the page (docs/plans/training-and-curation/spec-t6.md sections 7 and 9) in a headless
// browser, the owner signed in, no GPU. Tuldok runs with --project-folder on a copy of the minimal fixture with the
// buildable fixture's definitions and code, a serve.py (pure Python, its load slowed by two seconds so that starting
// can be seen) and a serve block on fit-a, which is built with the stand-in trainer before Tuldok starts.
//   1. fit-a's drawer on the Map has a Serving block, not served; Serve starts it; the block shows starting, then
//      ready in place: the same element, the drawer not rebuilt, only `served` asked meanwhile.
//   2. Try it sends the example inputs to POST /api/serve/fit-a/predict and shows the answer (the test's own
//      arithmetic) and its times; the session's summary appears in place.
//   3. The Train tab lists fit-a under Served models as ready; its row opens the serving drawer.
//   4. Light and dark at 1440 and 390 wide, the Map drawer and the Train tab with the serving drawer: nothing wider
//      than the drawer, nor than the main area on Train (the Map's main area is the map, which scrolls sideways).
//   5. Stop (two presses) stops it: the block says stopped, the process is gone, and the endpoint refuses.
//   6. No script error and no failed request.
//   node tests/browser_project_workspace_serving.cjs [--shots <dir>]
const assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const { spawn, execFileSync } = require('node:child_process'), { once } = require('node:events');
const { authenticatedFixture } = require('./auth_helpers.cjs'), { waitForDebugger } = require('./browser_startup.cjs'), { cdpSession } = require('./browser_cdp_session.cjs'), { qaDirectory } = require('./qa_artifacts.cjs');

const root = path.resolve(__dirname, '..');
const argv = process.argv.slice(2), option = name => { const i = argv.indexOf(name); return i >= 0 ? argv[i + 1] : null; };
assert.ok(process.env.TULDOK_DATABASE_URL, 'TULDOK_DATABASE_URL must name a disposable PostgreSQL cluster');
const venv = path.join(root, '.venv', 'bin');
if (fs.existsSync(path.join(venv, 'python'))) process.env.PATH = venv + path.delimiter + process.env.PATH;   // auth_helpers runs python3
const python = fs.existsSync(path.join(venv, 'python')) ? path.join(venv, 'python') : 'python3';
const MODEL = 'recipes/fit-a';
const SERVE_PY = `"""fit-a as served: y = constant + x; load waits two seconds so that starting is seen."""
import json, os, time

def load(product):
    time.sleep(2)
    with open(os.path.join(product, 'weights.json')) as handle:
        return json.load(handle)

def predict(model, inputs):
    return {'y': [model['constant'] + x for x in inputs['x']]}
`;

const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'tuldok-serving-browser-'));
const report = qaDirectory(root, 'project-workspace-serving');
const shots = option('--shots') ? path.resolve(option('--shots')) : null; if (shots) fs.mkdirSync(shots, { recursive: true });
const children = [], checks = [], errors = [], failures = [];
let server, serverErrors = '', origin, auth, socket, session, send, evaluate, owned = null;
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(fn, label, tries = 300) { for (let i = 0; i < tries; i++) { const value = await fn(); if (value) return value; await pause(100); } throw Error('Timed out: ' + label); }
function check(text) { checks.push(text); console.log('PASS ' + text); }
function launch(command, args, options) { const child = spawn(command, args, options); children.push(child); return child; }
async function stop(child) { if (!child || child.exitCode !== null || child.signalCode !== null) return; const exited = once(child, 'exit'); child.kill('SIGTERM'); await Promise.race([exited, pause(10000)]); if (child.exitCode === null && child.signalCode === null) { child.kill('SIGKILL'); await exited; } }
function findBrowser() {
  const candidates = [process.env.BROWSER, '/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/google-chrome'];
  const cache = path.join(os.homedir(), '.cache', 'ms-playwright');
  if (fs.existsSync(cache)) for (const name of fs.readdirSync(cache).filter(n => n.startsWith('chromium_headless_shell-')).sort().reverse()) candidates.push(path.join(cache, name, 'chrome-headless-shell-linux64', 'chrome-headless-shell'));
  const found = candidates.find(candidate => candidate && fs.existsSync(candidate));
  assert.ok(found, 'No headless browser: set BROWSER');
  return found;
}
/** Drops the project's schema and the catalog's from the disposable database, so each run imports afresh. */
function dropOwned(folder, catalog) {
  const id = JSON.parse(fs.readFileSync(path.join(folder, 'tuldok.json'), 'utf8')).id;
  execFileSync(python, ['-c', `import json, os, pathlib, sys, psycopg
from psycopg import sql
from tuldok_project import store
store.drop_project(sys.argv[1], os.environ['TULDOK_DATABASE_URL'])
root = pathlib.Path(sys.argv[2])
if root.exists():
    with psycopg.connect(os.environ['TULDOK_DATABASE_URL'], autocommit=True) as c:
        for p in root.rglob('.tuldok.json'):
            v = json.loads(p.read_text())
            name = 'projection_' + v['projection_id'] if v.get('version') == 2 else 'catalog_' + v['dataset_id']
            c.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(name)))
`, id, catalog], { cwd: root, stdio: ['ignore', 'pipe', 'pipe'] });
}
async function contract(name) {
  const capabilities = await (await auth.fetch(origin + '/api/agent/capabilities')).json();
  const operation = capabilities.operations.find(item => item.id === 'project.' + name), c = operation.contracts[operation.contracts.length - 1];
  return 'project.' + name + '/' + c.version + '/' + c.sha256;
}
/** An operation as the owner. */
async function api(name, body = {}) {
  const headers = { 'Content-Type': 'application/json', 'Tuldok-Operation-Contract': await contract(name) };
  const response = await auth.fetch(origin + '/api/project/' + name, { method: 'POST', headers, body: JSON.stringify(body) });
  const value = await response.json(); assert.equal(response.status, 200, name + ': ' + JSON.stringify(value)); return value;
}

// ---- The page's requests, from the browser's network ------------------------------------------------------------------
const calls = new Map(), finished = [];
function network(event) {
  const p = event.params;
  if (event.method === 'Network.requestWillBeSent' && /\/api\/(project\/[a-z_]+|serve\/[a-z0-9._-]+\/predict)$/.test(p.request.url)) calls.set(p.requestId, { name: p.request.url.includes('/api/serve/') ? 'predict' : p.request.url.split('/').pop(), sent: Date.now() });
  if ((event.method === 'Network.loadingFinished' || event.method === 'Network.loadingFailed') && calls.has(p.requestId)) { finished.push(Object.assign(calls.get(p.requestId), { done: Date.now() })); calls.delete(p.requestId); }
}
const asked = (since = 0) => finished.concat([...calls.values()]).filter(f => f.sent >= since).map(f => f.name);
async function settled(label) {
  await until(() => evaluate(`(() => { const m = document.getElementById('main'), a = document.getElementById('aside'); return ![...m.querySelectorAll('.note'), ...a.querySelectorAll('.note')].some(n => n.textContent === 'Reading…') && !m.hasAttribute('aria-busy'); })()`).then(ok => ok && !calls.size), 'settled: ' + label);
  await pause(250);
}
const byKey = key => `[data-key=${JSON.stringify(key)}]`;
async function mouse(type, x, y, buttons = 0) { await send('Input.dispatchMouseEvent', { type, x, y, button: type === 'mouseMoved' ? (buttons ? 'left' : 'none') : 'left', buttons, clickCount: type === 'mouseMoved' ? 0 : 1 }); }
async function press(selector) {
  const at = await until(() => evaluate(`(() => { const e = document.querySelector(${JSON.stringify(selector)}); if (!e || e.disabled) return null; e.scrollIntoView({ block: 'center', inline: 'nearest' }); const r = e.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; })()`), 'shown: ' + selector, 100);
  await pause(100); await mouse('mouseMoved', at.x, at.y); await mouse('mousePressed', at.x, at.y, 1); await mouse('mouseReleased', at.x, at.y);
}
async function frames() { await evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))'); }
async function shot(name) {
  await frames();
  const png = Buffer.from((await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })).data, 'base64');
  fs.writeFileSync(path.join(report, name + '.png'), png); if (shots) fs.writeFileSync(path.join(shots, name + '.png'), png);
}
const panel = (where = '#aside') => evaluate(`(() => { const p = document.querySelector(${JSON.stringify(where + ' .srv[data-serve-model="' + MODEL + '"]')}); if (!p) return null;
  return { state: p.dataset.serveState, mark: p.__mark || null, word: (p.querySelector('.srv-mark') || {}).textContent || '', line: p.querySelector('.srv-line').textContent, address: p.querySelector('.srv-address').textContent,
    tryShown: !p.querySelector('.srv-try').hidden, buttons: [...p.querySelectorAll('.srv-acts button')].map(b => b.textContent), times: p.querySelector('.srv-times').hidden ? null : p.querySelector('.srv-times').textContent,
    drawer: (document.querySelector('#aside .inspector') || {}).__mark || null }; })()`);
const alive = pid => { try { return fs.readFileSync('/proc/' + pid + '/stat', 'utf8').split(') ').pop().split(' ')[0] !== 'Z'; } catch (_) { return false; } };

(async () => {
  // ---- The fixture -----------------------------------------------------------------------------------------------------------
  fs.cpSync(path.join(root, 'tests', 'fixtures', 'tuldok_project', 'minimal'), path.join(temporary, 'fixture'), { recursive: true });
  const folder = path.join(temporary, 'fixture', 'project'), code = path.join(temporary, 'fixture', 'code'), buildable = path.join(root, 'tests', 'fixtures', 'tuldok_project', 'buildable');
  for (const kind of ['environments', 'datasets', 'recipes', 'benchmarks', 'charts']) for (const name of fs.readdirSync(path.join(buildable, 'project', kind))) fs.copyFileSync(path.join(buildable, 'project', kind, name), path.join(folder, kind, name));
  for (const name of fs.readdirSync(path.join(buildable, 'code'))) fs.cpSync(path.join(buildable, 'code', name), path.join(code, name), { recursive: true });
  fs.writeFileSync(path.join(code, 'serve.py'), SERVE_PY);
  const recipeFile = path.join(folder, 'recipes', 'fit-a.json'), recipe = JSON.parse(fs.readFileSync(recipeFile, 'utf8'));
  recipe.serve = { module_file: 'serve.py', load: 'load', example: { x: [1, 2.5] } };
  fs.writeFileSync(recipeFile, JSON.stringify(recipe, null, 2) + '\n');
  const git = ['-c', 'user.name=Tuldok Test', '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false', '-c', 'init.defaultBranch=main', '-C', path.join(temporary, 'fixture')];
  execFileSync('git', [...git, 'init', '-q']); execFileSync('git', [...git, 'add', '-A']); execFileSync('git', [...git, 'commit', '-q', '-m', 'The fixture.']);
  const home = path.join(temporary, 'home'), catalog = path.join(temporary, 'catalog'); fs.mkdirSync(home);
  const env = { ...process.env, TULDOK_PROJECT_HOME: home, TULDOK_SETTINGS: path.join(temporary, 'settings.json') };
  owned = [folder, catalog]; dropOwned(folder, catalog);
  const cli = (...args) => execFileSync(python, ['-m', 'tuldok_project', ...args], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] }).toString();
  cli('connect', folder, 'test-python', python);
  cli('build', folder, MODEL, '--yes');
  let output = '';
  server = launch(python, ['-u', 'app.py', '--port', '0', '--data', catalog, '--project-folder', folder], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] });
  server.stdout.on('data', chunk => { output += chunk; }); server.stderr.on('data', chunk => { serverErrors += chunk; });
  const port = await until(() => { if (server.exitCode !== null) throw Error('Tuldok exited: ' + serverErrors); return output.match(/127\.0\.0\.1:(\d+)/)?.[1]; }, 'Tuldok start-up', 3000);
  origin = 'http://127.0.0.1:' + port;
  auth = authenticatedFixture(); await auth.register(origin, catalog, root);
  const product = (await api('products', { reference: MODEL })).products[0];
  const constant = JSON.parse(fs.readFileSync(path.join(product.directory, 'weights.json'), 'utf8')).constant;
  assert.equal((await api('served')).servable[0].built, true, 'fit-a is built and declares serve');

  const browser = launch(findBrowser(), ['--headless', '--no-sandbox', '--disable-gpu', '--no-first-run', '--hide-scrollbars', '--remote-debugging-port=0', '--window-size=1440,900', '--user-data-dir=' + path.join(temporary, 'browser'), 'about:blank'], { stdio: 'ignore', env: { ...process.env, XDG_CONFIG_HOME: temporary, XDG_CACHE_HOME: temporary } });
  const debugPort = await waitForDebugger(browser, path.join(temporary, 'browser', 'DevToolsActivePort'));
  const target = (await (await fetch('http://127.0.0.1:' + debugPort + '/json')).json()).find(item => item.type === 'page');
  socket = new WebSocket(target.webSocketDebuggerUrl); await once(socket, 'open');
  session = cdpSession(socket, { timeoutMs: 60000, onEvent: event => {
    network(event);
    if (event.method === 'Runtime.exceptionThrown') errors.push(event.params.exceptionDetails.exception?.description || event.params.exceptionDetails.text);
    if (event.method === 'Runtime.consoleAPICalled' && event.params.type === 'error') errors.push(event.params.args.map(a => a.value ?? a.description).join(' '));
    if (event.method === 'Log.entryAdded' && event.params.entry.level === 'error') errors.push(event.params.entry.text + ' ' + (event.params.entry.url || ''));
    if (event.method === 'Network.loadingFailed' && !event.params.canceled) failures.push({ id: event.params.requestId, error: event.params.errorText });
    if (event.method === 'Network.responseReceived' && event.params.response.status >= 400) failures.push({ url: event.params.response.url, status: event.params.response.status });
  } });
  send = session.send;
  evaluate = async expression => { const result = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }); if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails)); return result.result.value; };
  await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable'); await send('Log.enable');
  const size = async (width, height) => send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: width < 600 });
  const theme = async name => { await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: name }, { name: 'prefers-reduced-motion', value: 'reduce' }] }); };
  await auth.browser(send, origin);   // the owner's session
  const load = async (name, hash) => {
    await theme(name);
    await send('Page.navigate', { url: 'about:blank' }); await pause(100);
    await send('Page.navigate', { url: origin + '/?theme=' + name + '#' + hash });
    await until(() => evaluate(`document.readyState === 'complete' && !!document.getElementById('needs-btn') && !document.getElementById('needs-btn').disabled`), 'the project read', 1200);
    await settled('opened ' + hash);
  };
  const mapDrawer = 'map/' + encodeURIComponent(MODEL), trainDrawer = 'train/' + encodeURIComponent('serve:' + MODEL);

  // ---- 1. Serve from the drawer; starting, then ready in place -------------------------------------------------------------
  await size(1440, 900); await load('light', mapDrawer);
  let p = await until(() => panel(), 'the Serving block');
  assert.equal(p.state, 'none'); assert.equal(p.word, 'not served'); assert.equal(p.address, 'POST /api/serve/fit-a/predict'); assert.deepEqual(p.buttons, ['Serve']); assert.equal(p.tryShown, false);
  await shot('light-1440-1-not-served');
  await press(byKey('serve:' + MODEL + ':none:serve'));
  p = await until(async () => { const q = await panel(); return q && q.state === 'starting' ? q : null; }, 'starting', 100);
  assert.equal(p.word, 'starting'); assert.deepEqual(p.buttons, ['Stop']); assert.equal(p.tryShown, false);
  await evaluate(`(() => { document.querySelector('#aside .srv').__mark = 7; document.querySelector('#aside .inspector').__mark = 8; return true; })()`);
  await shot('light-1440-1-starting');
  const since1 = Date.now();
  p = await until(async () => { const q = await panel(); return q && q.state === 'ready' ? q : null; }, 'ready', 150);
  assert.equal(p.mark, 7, 'The Serving block is the same element: set in place'); assert.equal(p.drawer, 8, 'The drawer was not rebuilt');
  assert.equal(p.word, 'ready'); assert.deepEqual(p.buttons, ['Stop']); assert.equal(p.tryShown, true); assert.match(p.line, /0 requests/);
  const between = asked(since1);
  assert.ok(between.length && between.every(n => n === 'served' || n === 'serve_session'), 'Only served (and the summary) asked while starting: ' + between.join(', '));
  const sessionId = (await api('served')).servable[0].session.id, pid = (await api('serve_session', { session: sessionId })).pid;
  assert.ok(alive(pid), 'The served process runs');
  check('1. fit-a\'s drawer: not served, Serve; starting, then ready in place (the same block, the drawer not rebuilt, only ' + [...new Set(between)].join(' and ') + ' asked), Try it shown');

  // ---- 2. Try it -----------------------------------------------------------------------------------------------------------------
  assert.deepEqual(JSON.parse(await evaluate(`document.querySelector('#aside .srv-inputs').value`)), { x: [1, 2.5] }, 'The example fills Try it');
  const since2 = Date.now();
  await press(byKey('serve-send-' + MODEL));
  const answer = await until(() => evaluate(`(() => { const o = document.querySelector('#aside .srv-outputs'); return o ? { outputs: JSON.parse(o.textContent), timing: document.querySelector('#aside .srv-timing').textContent } : null; })()`), 'the answer');
  assert.deepEqual(answer.outputs, { y: [constant + 1, constant + 2.5] }, 'The answer is y = constant + x');
  assert.match(answer.timing, /^total [0-9.]+ m?s · model [0-9.]+ m?s · queue [0-9.]+ m?s$/);
  p = await until(async () => { const q = await panel(); return q && q.times ? q : null; }, 'the summary');
  assert.match(p.times, /Requests1/); assert.match(p.times, /p50 .* p95 .* p99/); assert.equal(p.mark, 7); assert.match(p.line, /^1 request /, 'The line counts it');
  assert.deepEqual([...new Set(asked(since2))].sort(), ['predict', 'serve_session'], 'Try it asks the endpoint and the summary only');
  await shot('light-1440-2-tried');
  check('2. Try it answered ' + JSON.stringify(answer.outputs) + ' (' + answer.timing + '); the summary appeared in place');

  // ---- 3. The Train tab --------------------------------------------------------------------------------------------------------------
  await load('light', 'train');
  const row = await until(() => evaluate(`(() => { const r = document.querySelector('#main .srv-row[data-serve-model="${MODEL}"]'); return r ? { state: r.dataset.serveState, text: r.textContent } : null; })()`), 'the row');
  assert.equal(row.state, 'ready'); assert.match(row.text, /ready/); assert.match(row.text, /1 request/);
  await press(byKey('open-serve:' + MODEL)); await settled('serving drawer');
  p = await until(() => panel(), 'the serving drawer');
  assert.equal(p.state, 'ready'); assert.equal(p.tryShown, true);
  check('3. Train lists fit-a under Served models, ready with 1 request; its row opens the serving drawer');

  // ---- 4. Light and dark, 1440 and 390 ---------------------------------------------------------------------------------------------
  const seen = [];
  for (const [w, hgt] of [[1440, 900], [390, 844]]) for (const name of ['light', 'dark']) for (const hash of [mapDrawer, trainDrawer]) {
    const tag = name + '-' + w + '-' + hash.split('/')[0];
    await size(w, hgt); await load(name, hash);
    await until(() => panel(), 'the panel ' + tag);
    // On the Map the main area is the map, which scrolls sideways by design at 390 wide; the drawer is checked there.
    const boxes = hash === mapDrawer ? ['aside'] : ['main', 'aside'];
    const r = await evaluate(`(() => { const out = []; for (const id of ${JSON.stringify(boxes)}) { const box = document.getElementById(id); const right = box.getBoundingClientRect().right; out.push(...[...box.querySelectorAll('*')].filter(e => { const b = e.getBoundingClientRect(); return b.width > 0 && b.right > right + 1 && !e.closest('.tv-wrap') && !e.closest('pre'); }).map(e => id + ' ' + e.tagName + '.' + e.className).slice(0, 4)); } return { wide: out, page: document.documentElement.scrollWidth - innerWidth, main: document.getElementById('main').scrollWidth - document.getElementById('main').clientWidth }; })()`);
    assert.ok(!r.wide.length && (hash === mapDrawer || r.main <= 1), tag + ': nothing overflows sideways ' + JSON.stringify(r));
    await evaluate(`(() => { const s = document.querySelector('#aside .srv'); if (s) s.scrollIntoView({ block: 'start' }); return true; })()`); await pause(150);
    await shot(tag + '-4');
    seen.push(tag + (r.page > 0 ? ' (the page ' + r.page + ' px wider)' : ''));
  }
  await size(1440, 900);
  check('4. Nothing wider than the main area or the drawer: ' + seen.join(', ') + (shots ? '; screenshots in ' + shots : ''));

  // ---- 5. Stop -------------------------------------------------------------------------------------------------------------------------
  await load('light', mapDrawer);
  await until(async () => { const q = await panel(); return q && q.state === 'ready'; }, 'ready again');
  const stopKey = 'serve:' + MODEL + ':' + sessionId + ':ready:stop';
  await press(byKey(stopKey));
  await until(() => evaluate(`!!document.querySelector(${JSON.stringify(byKey(stopKey + ':confirm'))})`), 'the confirm state');
  await press(byKey(stopKey + ':confirm')); await settled('stopped');
  p = await until(async () => { const q = await panel(); return q && q.state === 'stopped' ? q : null; }, 'stopped');
  assert.deepEqual(p.buttons, ['Serve']); assert.equal(p.tryShown, false); assert.match(p.line, /asked/);
  await until(() => !alive(pid), 'the process gone', 50);
  const refused = await auth.fetch(origin + '/api/serve/fit-a/predict', { method: 'POST', headers: { 'Content-Type': 'application/json', Origin: origin }, body: JSON.stringify({ inputs: { x: [1] } }) });
  assert.equal(refused.status, 404, 'The endpoint refuses once it is stopped');
  await shot('light-1440-5-stopped');
  check('5. Stop, in two presses: stopped, Serve offered again, the process gone, the endpoint answers 404');

  assert.deepEqual(errors, [], 'Script errors');
  assert.deepEqual(failures, [], 'Failed requests');
  check('6. No script error, no failed request');
  fs.writeFileSync(path.join(report, 'receipt.json'), JSON.stringify({ status: 'pass', folder, checks }, null, 2) + '\n');
  console.log('Receipt in ' + report);
})().catch(async error => {
  process.exitCode = 1;
  console.error(error); if (serverErrors) console.error('Server:', serverErrors.slice(-4000));
  console.error('Script errors:', JSON.stringify(errors)); console.error('Failed requests:', JSON.stringify(failures));
  try { if (evaluate) { await shot('failure'); console.error('Aside:', (await evaluate('document.getElementById("aside").innerText')).slice(0, 2500)); } } catch (_) { /* the page is gone */ }
  fs.writeFileSync(path.join(report, 'failure.json'), JSON.stringify({ status: 'failed', error: String(error && error.stack || error), checks, errors, failures }, null, 2) + '\n');
}).finally(async () => {
  try { session?.close(); } catch (_) { /* closed */ }
  for (const child of children.reverse()) await stop(child);
  if (owned) try { dropOwned(...owned); } catch (error) { console.error('Dropping the disposable schemas failed:', error.message); process.exitCode = 1; }
  try { execFileSync('chmod', ['-R', 'u+w', temporary]); } catch (_) { /* nothing was made read-only */ }
  fs.rmSync(temporary, { recursive: true, force: true });
});
