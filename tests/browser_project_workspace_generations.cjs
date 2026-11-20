'use strict';
// Data generations on the page (docs/plans/training-and-curation/spec-generations.md section 4) in a headless
// browser, signed in with a credential that may only inspect. Tuldok runs with --project-folder on a copy of the
// minimal fixture whose solver step declares the generation toy-solver-1 (so datasets/waves, stepper-k1 and
// stepper-k2 inherit it), with a second solver step of toy-solver-2, a dataset made with it, and a recipe stepper-k3
// trained on that dataset and derived from stepper-k2 (a cross-generation fine-tune).
//   1. The Map's list shows each model's generation as a chip after its name (none for early-fit), k3's dashed.
//   2. The Generation filter: a chip per generation and one for models without; pressing toy-solver-2 leaves only
//      k3 in the list and makes the other nodes of the lane map faint; pressing it again shows them all.
//   3. k3's drawer shows its chip and "from a model of toy-solver-1".
//   4. The Data tab's cards show the datasets' generations.
//   5. Light and dark at 1440 and 390 wide: the chips shown (the list leaves them out at 390, for the names), no
//      sideways overflow of the page; no script error, no failed request.
//   node tests/browser_project_workspace_generations.cjs [--shots <dir>]
const assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const { spawn, execFileSync } = require('node:child_process'), { once } = require('node:events');
const { authenticatedFixture } = require('./auth_helpers.cjs'), { waitForDebugger } = require('./browser_startup.cjs'), { cdpSession } = require('./browser_cdp_session.cjs');

const root = path.resolve(__dirname, '..');
assert.ok(process.env.TULDOK_DATABASE_URL, 'TULDOK_DATABASE_URL must name a disposable PostgreSQL cluster');
const venv = path.join(root, '.venv', 'bin');
if (fs.existsSync(path.join(venv, 'python'))) process.env.PATH = venv + path.delimiter + process.env.PATH;   // auth_helpers runs python3
const python = fs.existsSync(path.join(venv, 'python')) ? path.join(venv, 'python') : 'python3';

const argv = process.argv.slice(2), shots = argv.includes('--shots') ? path.resolve(argv[argv.indexOf('--shots') + 1]) : null;
if (shots) fs.mkdirSync(shots, { recursive: true });
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'tuldok-generations-browser-'));
const children = [], errors = [], failedRequests = [];
let server, serverErrors = '', origin, auth, socket, session, send, evaluate, owned = null;
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(fn, label, tries = 300) { for (let i = 0; i < tries; i++) { const value = await fn(); if (value) return value; await pause(100); } throw Error('Timed out: ' + label); }
const check = text => console.log('PASS ' + text);
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
/** Drops the project's schema and the catalog's from the disposable database. */
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
async function api(name, body = {}) {
  const capabilities = await (await auth.fetch(origin + '/api/agent/capabilities')).json();
  const operation = capabilities.operations.find(item => item.id === 'project.' + name), contract = operation.contracts[operation.contracts.length - 1];
  const response = await auth.fetch(origin + '/api/project/' + name, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Tuldok-Operation-Contract': 'project.' + name + '/' + contract.version + '/' + contract.sha256 }, body: JSON.stringify(body) });
  const value = await response.json(); assert.equal(response.status, 200, JSON.stringify(value)); return value;
}
const readJson = file => JSON.parse(fs.readFileSync(file, 'utf8'));
const writeJson = (file, value) => fs.writeFileSync(file, JSON.stringify(value, null, 2) + '\n');
async function open(theme, width, hash) {
  await send('Emulation.setDeviceMetricsOverride', { width, height: 900, deviceScaleFactor: 1, mobile: width < 600 });
  await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: theme }, { name: 'prefers-reduced-motion', value: 'reduce' }] });
  await send('Page.navigate', { url: origin + '/?theme=' + theme + '#' + hash });
  await until(() => evaluate(`document.readyState === 'complete' && !!document.getElementById('needs-btn') && !document.getElementById('needs-btn').disabled`), 'the project read (' + hash + ')');
  await until(() => evaluate(`(() => { const t = document.getElementById('main').innerText; return t.trim().length > 0 && !t.includes('Reading'); })()`), 'tab ' + hash);
}
const listChips = () => evaluate(`[...document.querySelectorAll('.tree-list .trow')].map(r => { const g = r.querySelector('.nm .gen'); return [r.dataset.id, g ? g.textContent : null, !!(g && g.classList.contains('crosses'))]; })`);
async function shot(name) { if (shots) fs.writeFileSync(path.join(shots, name + '.png'), Buffer.from((await send('Page.captureScreenshot', { format: 'png' })).data, 'base64')); }
const press = selector => evaluate(`(() => { const e = document.querySelector(${JSON.stringify(selector)}); if (!e) return false; e.click(); return true; })()`);

(async () => {
  // ---- The fixture: generations on the minimal project -------------------------------------------------------------
  fs.cpSync(path.join(root, 'tests', 'fixtures', 'tuldok_project', 'minimal'), path.join(temporary, 'fixture'), { recursive: true });
  const folder = path.join(temporary, 'fixture', 'project');
  const project = readJson(path.join(folder, 'tuldok.json')); project.id = require('node:crypto').randomUUID().replace(/-/g, ''); writeJson(path.join(folder, 'tuldok.json'), project);
  const solver = readJson(path.join(folder, 'steps', 'solver.json'));
  writeJson(path.join(folder, 'steps', 'solver.json'), Object.assign({}, solver, { generation: 'toy-solver-1' }));
  writeJson(path.join(folder, 'steps', 'solver-new.json'), Object.assign({}, solver, { title: 'The new toy solver', generation: 'toy-solver-2' }));
  const waves = readJson(path.join(folder, 'datasets', 'waves.json'));
  writeJson(path.join(folder, 'datasets', 'waves-new.json'), Object.assign({}, waves, { title: 'Wave scenes, new solver',
    run: Object.assign({}, waves.run, { inputs: { solver: { from: 'steps/solver-new', output: 'binary' } } }) }));
  const k2 = readJson(path.join(folder, 'recipes', 'stepper-k2.json'));
  const k3 = Object.assign({}, k2, { title: 'Stepper fine-tuned on the new solver', labels: { short: 'K3' }, derived_from: 'recipes/stepper-k2' });
  delete k3.compared_with;
  k3.run = Object.assign({}, k2.run, { inputs: { start: { from: 'recipes/stepper-k2', output: 'weights' }, training: 'datasets/waves-new' } });
  writeJson(path.join(folder, 'recipes', 'stepper-k3.json'), k3);
  const checked = JSON.parse(execFileSync(python, ['-m', 'tuldok_project', 'check', folder, '--json'], { cwd: root }).toString());
  assert.equal(checked.errors, 0, JSON.stringify(checked.problems));

  const home = path.join(temporary, 'home'), catalog = path.join(temporary, 'catalog'); fs.mkdirSync(home);
  owned = [folder, catalog]; dropOwned(folder, catalog);
  let output = '';
  server = launch(python, ['-u', 'app.py', '--port', '0', '--data', catalog, '--project-folder', folder], { cwd: root, env: { ...process.env, TULDOK_PROJECT_HOME: home }, stdio: ['ignore', 'pipe', 'pipe'] });
  server.stdout.on('data', chunk => { output += chunk; }); server.stderr.on('data', chunk => { serverErrors += chunk; });
  const port = await until(() => { if (server.exitCode !== null) throw Error('Tuldok exited: ' + serverErrors); return output.match(/127\.0\.0\.1:(\d+)/)?.[1]; }, 'Tuldok start-up', 1800);
  origin = 'http://127.0.0.1:' + port;
  auth = authenticatedFixture(); await auth.register(origin, catalog, root);
  const map = await api('map'), byRef = Object.fromEntries(map.models.map(m => [m.reference, m.generation || null]));
  assert.deepEqual(byRef, { 'recipes/early-fit': null, 'recipes/stepper-k1': 'toy-solver-1', 'recipes/stepper-k2': 'toy-solver-1', 'recipes/stepper-k3': 'toy-solver-2' });
  check('map answers the generations: ' + JSON.stringify(byRef));

  const browser = launch(findBrowser(), ['--headless', '--no-sandbox', '--disable-gpu', '--no-first-run', '--hide-scrollbars', '--remote-debugging-port=0', '--window-size=1440,900', '--user-data-dir=' + path.join(temporary, 'browser'), 'about:blank'], { stdio: 'ignore', env: { ...process.env, XDG_CONFIG_HOME: temporary, XDG_CACHE_HOME: temporary } });
  const debugPort = await waitForDebugger(browser, path.join(temporary, 'browser', 'DevToolsActivePort'));
  const target = (await (await fetch('http://127.0.0.1:' + debugPort + '/json')).json()).find(item => item.type === 'page');
  socket = new WebSocket(target.webSocketDebuggerUrl); await once(socket, 'open');
  session = cdpSession(socket, { timeoutMs: 60000, onEvent: event => {
    if (event.method === 'Runtime.exceptionThrown') errors.push(event.params.exceptionDetails.exception?.description || event.params.exceptionDetails.text);
    if (event.method === 'Runtime.consoleAPICalled' && event.params.type === 'error') errors.push(event.params.args.map(a => a.value ?? a.description).join(' '));
    if (event.method === 'Network.loadingFailed' && !event.params.canceled) failedRequests.push({ id: event.params.requestId, error: event.params.errorText });
    if (event.method === 'Network.responseReceived' && event.params.response.status >= 400) failedRequests.push({ url: event.params.response.url, status: event.params.response.status });
  } });
  send = session.send;
  evaluate = async expression => { const result = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }); if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails)); return result.result.value; };
  await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable');
  const issued = await auth.fetch(origin + '/api/access/credentials', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ label: 'A read-only browser check', scopes: ['inspect'], ttl_seconds: 3600 }) });
  const inspector = await issued.json(); assert.equal(issued.status, 201, JSON.stringify(inspector));
  assert.notEqual((await send('Network.setCookie', { name: 'tuldok_session', value: inspector.token, url: origin + '/', httpOnly: true, sameSite: 'Strict', path: '/' })).success, false);

  // ---- 1. The chips of the list ----------------------------------------------------------------------------------------
  await open('light', 1440, 'map');
  const chips = await until(async () => { const c = await listChips(); return c.length === 4 ? c : null; }, 'four rows');
  const shown = Object.fromEntries(chips.map(([id, g, crosses]) => [id, [g, crosses]]));
  assert.deepEqual(shown, { 'recipes/early-fit': [null, false], 'recipes/stepper-k1': ['toy-solver-1', false], 'recipes/stepper-k2': ['toy-solver-1', false], 'recipes/stepper-k3': ['toy-solver-2', true] });
  check('The list shows each model\'s generation after its name, k3\'s dashed (its parent is of toy-solver-1)');

  // ---- 2. The Generation filter ------------------------------------------------------------------------------------------
  const filter = await evaluate(`[...document.querySelectorAll('.filters [aria-label="Data generation"] button')].map(b => [b.dataset.generation, b.textContent, b.getAttribute('aria-pressed')])`);
  assert.deepEqual(filter, [['toy-solver-1', 'toy-solver-1', 'true'], ['toy-solver-2', 'toy-solver-2', 'true'], ['', 'no generation', 'true']]);
  assert.ok(await press('.filters button[data-generation="toy-solver-2"]'));
  await until(async () => (await listChips()).length === 1, 'the list filtered');
  assert.deepEqual((await listChips()).map(c => c[0]), ['recipes/stepper-k3']);
  const faint = await evaluate(`[...document.querySelectorAll('.tree-map g.node')].map(g => [g.dataset.id, g.classList.contains('dim')])`);
  assert.deepEqual(Object.fromEntries(faint), { 'recipes/early-fit': true, 'recipes/stepper-k1': true, 'recipes/stepper-k2': true, 'recipes/stepper-k3': false });
  assert.deepEqual(await evaluate(`[...document.querySelectorAll('.filters [aria-label="Data generation"] button')].map(b => b.getAttribute('aria-pressed'))`), ['false', 'true', 'false']);
  assert.ok(await press('.filters button[data-generation="toy-solver-2"]'));
  await until(async () => (await listChips()).length === 4, 'the list whole again');
  check('The Generation filter: toy-solver-2 alone leaves k3 in the list and the other nodes faint; pressed again, all four');

  // ---- 3. The drawer -----------------------------------------------------------------------------------------------------
  await evaluate(`location.hash = '#map/' + encodeURIComponent('recipes/stepper-k3')`);
  const drawer = await until(() => evaluate(`(() => { const g = document.querySelector('#aside .ins-meta .gen'), f = document.querySelector('#aside .gen-from'); return g && f ? [g.textContent, f.textContent] : null; })()`), 'the drawer of k3');
  assert.deepEqual(drawer, ['toy-solver-2', 'from a model of toy-solver-1']);
  await shot('drawer-k3');
  check('k3\'s drawer: its generation and "from a model of toy-solver-1"');

  // ---- 4. The Data tab ---------------------------------------------------------------------------------------------------
  await evaluate(`location.hash = '#data'`);
  const cards = await until(() => evaluate(`(() => { const c = [...document.querySelectorAll('.ds-card')]; return c.length === 2 ? c.map(x => [x.dataset.ref, (x.querySelector('.meta .gen') || {}).textContent || null]) : null; })()`), 'the dataset cards');
  assert.deepEqual(Object.fromEntries(cards), { 'datasets/waves': 'toy-solver-1', 'datasets/waves-new': 'toy-solver-2' });
  check('The Data tab\'s cards show the datasets\' generations');

  // ---- 5. Themes and widths -----------------------------------------------------------------------------------------------
  for (const theme of ['light', 'dark']) for (const width of [1440, 390]) for (const hash of ['map', 'data']) {
    await open(theme, width, hash); await pause(200);
    const sizes = await evaluate(`[innerWidth, document.documentElement.scrollWidth, document.body.scrollWidth, [...document.querySelectorAll('#main .gen')].filter(e => e.offsetWidth > 0).length]`);
    assert.ok(sizes[1] <= sizes[0] && sizes[2] <= sizes[0], theme + ' ' + width + ' ' + hash + ': sideways overflow ' + JSON.stringify(sizes));
    // Narrow, the list leaves the chips out so that the names have the room (the drawer and the filter keep them).
    assert.equal(sizes[3], hash === 'data' ? 2 : width < 600 ? 0 : 3, theme + ' ' + width + ' ' + hash + ': generation chips shown ' + JSON.stringify(sizes));
    await shot(theme + '-' + width + '-' + hash);
  }
  check('Light and dark at 1440 and 390 wide, Map and Data: the chips shown (the list\'s left out at 390), nothing overflows sideways');
  assert.deepEqual(errors, [], 'Script errors'); assert.deepEqual(failedRequests, [], 'Failed requests');
  check('No script error, no failed request');
})().catch(async error => {
  process.exitCode = 1;
  console.error(error); if (serverErrors) console.error('Server:', serverErrors.slice(-4000));
  console.error('Script errors:', JSON.stringify(errors)); console.error('Failed requests:', JSON.stringify(failedRequests));
  try { if (evaluate) console.error('Page:', (await evaluate('document.body.innerText')).slice(0, 2000)); } catch (_) { /* the page is gone */ }
}).finally(async () => {
  try { session?.close(); } catch (_) { /* closed */ }
  for (const child of children.reverse()) await stop(child);
  if (owned) try { dropOwned(...owned); } catch (error) { console.error('Dropping the disposable schemas failed:', error.message); process.exitCode = 1; }
  try { execFileSync('chmod', ['-R', 'u+w', temporary]); } catch (_) { /* nothing was made read-only */ }
  fs.rmSync(temporary, { recursive: true, force: true });
});
