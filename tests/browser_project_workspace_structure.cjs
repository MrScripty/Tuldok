'use strict';
// A model's structure in its drawer (docs/plans/training-and-curation/spec-t2.md sections 4 and 6, slice T2b) in a
// headless browser, the owner signed in, no GPU and no PyTorch. Tuldok runs with --project-folder on a copy of the
// minimal fixture, in a Git repository of its own, with three recipes of earlier work whose products are adopted
// (the command line's adopt): recipes/st-parent (the committed graph tests/fixtures/model_graph/parent.json and a
// weights.npz), recipes/st-derived, derived from it (derived.json, weights.npz and initial-weights.npz), and
// recipes/st-plain (a weights.npz and no graph). The weights are written by tests/project_structure_browser_fixture.py,
// which prints the graphs' counts and the derived model's change per module against its initial weights.
//   1. The derived model's drawer shows Structure right after Weights, with the graph's counts and every node
//      drawn; the plain model has no Structure block.
//   2. Folding: the outline folds blocks (one model_graph asked; a group node replaces its operations, nothing
//      outside the block is rebuilt), pressing the group opens it again.
//   3. An operation pressed shows its details; its tensor link opens that layer in the Weights block.
//   4. Colour by parameters, then by the change from the starting weights: the nodes' fills change and differ
//      between nodes, and each value is the server's (the change also the fixture's arithmetic). Fit to width
//      shrinks the drawing to the drawer, and back.
//   5. Compare with the parent: the second drawing, the derived model's changed and added modules marked as
//      model_graph_compare says, and listed.
//   6. Nothing changed: the window regaining focus adds, removes and changes no node of the drawer.
//   7. Light and dark at 1440 by 900 and 390 by 844: every node drawn, nothing in the drawer overflowing sideways
//      (the page's header, strip and map are wider than 390 px on every tab; recorded, not asserted); screenshots
//      (with --shots <dir>, written there too).
// It fails on any script error and any failed request.
//   node tests/browser_project_workspace_structure.cjs [--shots <dir>]
const assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const { spawn, execFileSync } = require('node:child_process'), { once } = require('node:events');
const { authenticatedFixture } = require('./auth_helpers.cjs'), { waitForDebugger } = require('./browser_startup.cjs'), { cdpSession } = require('./browser_cdp_session.cjs'), { qaDirectory } = require('./qa_artifacts.cjs');

const root = path.resolve(__dirname, '..');
const argv = process.argv.slice(2), option = name => { const i = argv.indexOf(name); return i >= 0 ? argv[i + 1] : null; };
assert.ok(process.env.TULDOK_DATABASE_URL, 'TULDOK_DATABASE_URL must name a disposable PostgreSQL cluster');
const venv = path.join(root, '.venv', 'bin');
if (fs.existsSync(path.join(venv, 'python'))) process.env.PATH = venv + path.delimiter + process.env.PATH;   // auth_helpers runs python3
const python = fs.existsSync(path.join(venv, 'python')) ? path.join(venv, 'python') : 'python3';
const WATCHED = ['summary', 'status', 'build_requests', 'environments', 'runs'];
const DERIVED = 'recipes/st-derived', PARENT = 'recipes/st-parent', PLAIN = 'recipes/st-plain';
const RECIPES = {
  'st-parent': { title: 'Structure parent', labels: { short: 'SP', trained_at: '2026-10-01' }, change: 'architecture' },
  'st-derived': { title: 'Structure derived', labels: { short: 'SD', trained_at: '2026-10-05' }, change: 'architecture', derived_from: PARENT },
  'st-plain': { title: 'Weights without a graph', labels: { short: 'SN', trained_at: '2026-10-07' }, change: 'component' }
};
const GRAPHS = path.join(root, 'tests', 'fixtures', 'model_graph');

const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'tuldok-structure-browser-'));
const report = qaDirectory(root, 'project-workspace-structure');
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

// ---- The page's requests, from the browser's network, with their bodies ------------------------------------------------
const calls = new Map(), finished = [];
function network(event) {
  const p = event.params;
  if (event.method === 'Network.requestWillBeSent' && /\/api\/project\/[a-z_]+$/.test(p.request.url)) { let body = null; try { body = p.request.postData ? JSON.parse(p.request.postData) : null; } catch (_) { body = null; } calls.set(p.requestId, { name: p.request.url.split('/').pop(), body, sent: Date.now() }); }
  if ((event.method === 'Network.loadingFinished' || event.method === 'Network.loadingFailed') && calls.has(p.requestId)) { finished.push(Object.assign(calls.get(p.requestId), { done: Date.now() })); calls.delete(p.requestId); }
}
const asked = (name, since = 0, test = () => true) => finished.concat([...calls.values()]).filter(f => f.name === name && f.sent >= since && test(f.body || {}));
async function reading(since, names, label, tries = 300) {
  await until(() => names.every(name => finished.some(f => f.name === name && f.sent >= since)), 'a reading: ' + label, tries);
  await until(() => !calls.size && Date.now() - Math.max(0, ...finished.map(f => f.done)) > 700, 'the reading done: ' + label, 300);
  await settled(label);
}
/** Waits until nothing reads: no "Reading…", nothing busy in the drawer, no request of the project in flight. */
async function settled(label) {
  await until(() => evaluate(`(() => { const reading = e => [...e.querySelectorAll('.note')].some(n => n.textContent === 'Reading…'); return !reading(document.getElementById('main')) && !reading(document.getElementById('aside')) && !document.querySelector('#aside [aria-busy]'); })()`).then(ok => ok && !calls.size), 'settled: ' + label);
  await pause(200);
}
async function hash(value) { await evaluate(`location.hash = ${JSON.stringify('#' + value)}`); await settled('#' + value); await pause(200); await settled('#' + value); }
const byKey = key => `[data-key=${JSON.stringify(key)}]`;
async function centre(selector) {
  for (let moved = 0; ; moved++) {
    const at = await until(() => evaluate(`(() => { const e = [...document.querySelectorAll(${JSON.stringify(selector)})].find(e => e.getClientRects().length); if (!e) return null; e.scrollIntoView({ block: 'nearest', inline: 'nearest' }); const r = e.getBoundingClientRect(), x = r.left + Math.min(r.width / 2, 20), y = r.top + r.height / 2, hit = document.elementFromPoint(x, y); return { x, y, ok: !!hit && (hit === e || e.contains(hit)) }; })()`), 'shown: ' + selector, 100);
    if (at.ok) return at;
    if (moved > 20) throw Error('The target of ' + selector + ' is never under its point');
    await pause(100);
  }
}
async function mouse(type, x, y, buttons = 0) { await send('Input.dispatchMouseEvent', { type, x, y, button: type === 'mouseMoved' ? (buttons ? 'left' : 'none') : 'left', buttons, clickCount: type === 'mouseMoved' ? 0 : 1 }); }
async function press(selector) { const { x, y } = await centre(selector); await mouse('mouseMoved', x, y); await mouse('mousePressed', x, y, 1); await mouse('mouseReleased', x, y); }
/** Chooses an option of a select by the keyboard's way of changing it (the change event the page listens to). */
async function choose(selector, value) { await evaluate(`(() => { const s = document.querySelector(${JSON.stringify(selector)}); s.focus(); s.value = ${JSON.stringify(value)}; s.dispatchEvent(new Event('change', { bubbles: true })); return true; })()`); }
async function frames() { await evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))'); }
async function shot(name) {
  await frames();
  const png = Buffer.from((await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })).data, 'base64');
  fs.writeFileSync(path.join(report, name + '.png'), png); if (shots) fs.writeFileSync(path.join(shots, name + '.png'), png);
}
const close = (a, b, label, tol = 1e-9) => assert.ok(Math.abs(a - b) <= tol * Math.max(1, Math.abs(b)), label + ': ' + a + ' is not ' + b);
/** The nodes of a drawing ('this' or 'other'): id, kind, mark, value, the computed fill of the box. */
const nodes = (which = 'this') => evaluate(`[...document.querySelectorAll('#aside .st-draw[data-which="${which}"] g.st-node')].map(g => ({ id: g.dataset.id, kind: [...g.classList].find(c => ['input', 'operation', 'output', 'group'].includes(c)), module: g.dataset.module, mark: g.dataset.mark || null, value: g.dataset.value == null ? null : Number(g.dataset.value), fill: getComputedStyle(g.querySelector('rect.st-box')).fill, label: g.getAttribute('aria-label'), w: g.getBBox().width }))`);

(async () => {
  // ---- The fixture: minimal + three recipes of earlier work, in Git; their products adopted ------------------------------------
  fs.cpSync(path.join(root, 'tests', 'fixtures', 'tuldok_project', 'minimal'), path.join(temporary, 'fixture'), { recursive: true });
  const folder = path.join(temporary, 'fixture', 'project');
  for (const [name, r] of Object.entries(RECIPES)) fs.writeFileSync(path.join(folder, 'recipes', name + '.json'), JSON.stringify(Object.assign({ format: 'tuldok_definition_v1', kind: 'recipe', title: r.title, description: 'A model for the browser check of a model\'s structure.', labels: r.labels,
    earlier_work: { rebuild: 'no', reason: 'Written by the browser check of the structure; only its graph and weights remain.' }, model: 'models/stepper', group: 'steppers', change: r.change }, r.derived_from ? { derived_from: r.derived_from } : {}), null, 2) + '\n');
  const git = ['-c', 'user.name=Tuldok Test', '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false', '-c', 'init.defaultBranch=main', '-C', path.join(temporary, 'fixture')];
  execFileSync('git', [...git, 'init', '-q']); execFileSync('git', [...git, 'add', '-A']); execFileSync('git', [...git, 'commit', '-q', '-m', 'The fixture.']);
  const files = path.join(temporary, 'weights');
  const X = JSON.parse(execFileSync(python, [path.join(root, 'tests', 'project_structure_browser_fixture.py'), '--out', files]).toString());
  const home = path.join(temporary, 'home'), catalog = path.join(temporary, 'catalog'); fs.mkdirSync(home);
  const env = { ...process.env, TULDOK_PROJECT_HOME: home, TULDOK_SETTINGS: path.join(temporary, 'settings.json') };
  owned = [folder, catalog]; dropOwned(folder, catalog);
  const cli = (...args) => execFileSync(python, ['-m', 'tuldok_project', ...args], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] }).toString();
  const manifest = path.join(temporary, 'adopt.json');
  fs.writeFileSync(manifest, JSON.stringify({ format: 'tuldok_adoption_v1', products: [
    { reference: PARENT, files: { 'weights.npz': path.join(files, 'parent', 'weights.npz'), 'model-graph.json': path.join(GRAPHS, 'parent.json') } },
    { reference: DERIVED, files: { 'weights.npz': path.join(files, 'derived', 'weights.npz'), 'initial-weights.npz': path.join(files, 'derived', 'initial-weights.npz'), 'model-graph.json': path.join(GRAPHS, 'derived.json') } },
    { reference: PLAIN, files: { 'weights.npz': path.join(files, 'plain', 'weights.npz') } }
  ] }));
  cli('adopt', folder, manifest, '--copy');
  let output = '';
  server = launch(python, ['-u', 'app.py', '--port', '0', '--data', catalog, '--project-folder', folder], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] });
  server.stdout.on('data', chunk => { output += chunk; }); server.stderr.on('data', chunk => { serverErrors += chunk; });
  const port = await until(() => { if (server.exitCode !== null) throw Error('Tuldok exited: ' + serverErrors); return output.match(/127\.0\.0\.1:(\d+)/)?.[1]; }, 'Tuldok start-up', 3000);
  origin = 'http://127.0.0.1:' + port;
  auth = authenticatedFixture(); await auth.register(origin, catalog, root);
  const products = (await api('products')).products, runOf = ref => products.find(p => p.reference === ref).run_id;
  const compared = await api('model_graph_compare', { run: runOf(DERIVED), other_run: runOf(PARENT) });
  const parameters = await api('model_graph_overlay', { run: runOf(DERIVED), kind: 'parameters' });
  const change = await api('model_graph_overlay', { run: runOf(DERIVED), kind: 'change', against: 'start' });
  for (const [p, v] of Object.entries(X.against_initial)) { if (v === null) assert.equal(change.modules[p], null, p); else close(change.modules[p], v, 'The change of ' + p + ' is the fixture\'s'); }

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
  const size = async (width, height) => send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false });
  const theme = async name => { await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: name }, { name: 'prefers-reduced-motion', value: 'reduce' }] }); };
  await auth.browser(send, origin);   // the owner's session
  const model = ref => 'map/' + encodeURIComponent(ref);
  const load = async (name, place) => {
    await theme(name);
    await send('Page.navigate', { url: 'about:blank' }); await pause(100);
    await send('Page.navigate', { url: origin + '/?theme=' + name + '#' + place });
    await until(() => evaluate(`document.readyState === 'complete' && !!document.getElementById('needs-btn') && !document.getElementById('needs-btn').disabled`), 'the project read', 1200);
    await settled('opened ' + place);
  };
  const shown = () => until(() => evaluate(`!!document.querySelector('#aside .st svg g.st-node')`), 'the Structure block');

  // ---- 1. The derived model's drawer: Structure after Weights, the counts, every node; the plain model: no block -------------
  await size(1440, 900); await load('light', model(DERIVED)); await shown(); await settled('the derived drawer');
  const b1 = await evaluate(`(() => { const s = document.querySelector('#aside .st-box'); return { after: s.previousElementSibling.className, size: s.querySelector('.st-size').textContent, how: s.querySelector('.st-how').textContent }; })()`);
  assert.equal(b1.after, 'wts-box', 'Structure follows Weights');
  const d = X.graphs.derived;
  assert.match(b1.size, new RegExp('^model-graph\\.json · ' + d.operations + ' operations · ' + d.modules + ' modules · ' + d.tensors + ' tensors$'));
  assert.match(b1.how, /^Recorded by torch\.export with PyTorch 2\.8\.0\+cpu; example input x 2×1×8×8\.$/);
  const n1 = await nodes();
  assert.equal(n1.length, d.nodes, 'every node of a small graph is drawn, nothing folded');
  assert.ok(n1.every(n => n.w > 50), 'every node has a box');
  assert.equal(n1.filter(n => n.kind === 'group').length, 0);
  await hash(model(PLAIN)); await until(() => evaluate(`!!document.querySelector('#aside .wts table')`), 'the plain model\'s weights'); await settled('plain');
  assert.equal(await evaluate(`document.querySelector('#aside .st-box').hidden && !document.querySelector('#aside .st')`), true, 'No graph: no Structure block');
  check('1. ' + DERIVED + ': Structure after Weights, "' + b1.size + '", ' + n1.length + ' nodes drawn; ' + PLAIN + ' has weights and no Structure block');

  // ---- 2. Folding in place: the outline folds blocks, the group opens it again ------------------------------------------------
  await hash(model(DERIVED)); await shown(); await settled('derived again');
  await evaluate(`(() => { for (const e of document.querySelectorAll('#aside *')) e.__seen = 1; return true; })()`);
  const since2 = Date.now();
  await press(byKey('st-mod-blocks')); await settled('blocks folded');
  assert.equal(asked('model_graph', since2).length, 1, 'One model_graph for the fold');
  assert.deepEqual(asked('model_graph', since2)[0].body.close, ['blocks']);
  const n2 = await nodes();
  const blockOps = n1.filter(n => n.kind === 'operation' && n.module.startsWith('blocks')).length;
  assert.equal(n2.length, n1.length - blockOps + 1, 'The ' + blockOps + ' operations of blocks are one group');
  assert.deepEqual(n2.filter(n => n.kind === 'group').map(n => n.id), ['module:blocks']);
  const outside = await evaluate(`[...document.querySelectorAll('#aside *')].filter(e => !e.__seen && !e.closest('.st-box')).length`);
  assert.equal(outside, 0, 'Nothing outside the Structure block is rebuilt');
  assert.equal(await evaluate(`document.querySelector('#aside [data-key="st-mod-blocks"]').getAttribute('aria-expanded')`), 'false');
  assert.equal(await evaluate(`document.activeElement.dataset.key`), 'st-mod-blocks', 'The outline\'s button keeps the focus');
  await shot('light-1440-1-folded');
  const since2b = Date.now();
  await press(byKey('st-node-module:blocks')); await settled('blocks opened');
  assert.equal(asked('model_graph', since2b).length, 1, 'One model_graph to open it');
  const n2b = await nodes();
  assert.equal(n2b.length, n1.length, 'Opened again: every node');
  check('2. The outline folded blocks (' + blockOps + ' operations into one group, one model_graph, nothing outside the block rebuilt); pressing the group opened it again (' + n2b.length + ' nodes)');

  // ---- 3. An operation's details; its tensor reaches the Weights block ----------------------------------------------------
  const stem = n1.find(n => n.module === 'stem');
  await press(byKey('st-node-' + stem.id)); await settled('stem selected');
  const det = await evaluate(`(() => { const e = document.querySelector('#aside .st-detail'); return { id: e.dataset.id, text: e.textContent, tensors: [...e.querySelectorAll('[data-tensor]')].map(b => b.dataset.tensor) }; })()`);
  assert.equal(det.id, stem.id); assert.deepEqual(det.tensors, ['stem.weight', 'stem.bias']);
  assert.match(det.text, /aten\.conv2d\.default/); assert.match(det.text, /2×1×8×8 float32/); assert.match(det.text, /padding = \[1,1\]/);
  await press(byKey('st-tensor-stem.weight'));
  await until(() => evaluate(`!!document.querySelector('#aside tr.wts-row[data-layer="stem"] [aria-expanded="true"]')`), 'the stem layer opened in Weights');
  await settled('weights opened');
  const w3 = await evaluate(`({ focus: document.activeElement.dataset.key, tensor: document.querySelector('#aside .wts-tensor').getAttribute('aria-label'), top: document.querySelector('#aside tr.wts-row[data-layer="stem"]').getBoundingClientRect().top, view: (r => ({ top: r.top, bottom: r.bottom }))(document.getElementById('drawer').getBoundingClientRect()) })`);
  assert.equal(w3.focus, 'wts-layer-stem', 'The layer\'s button has the focus');
  assert.equal(w3.tensor, 'Tensor stem.weight');
  assert.ok(w3.top >= w3.view.top - 1 && w3.top < w3.view.bottom, 'The layer is scrolled into the drawer\'s view: ' + JSON.stringify(w3));
  await shot('light-1440-2-tensor-in-weights');
  check('3. ' + stem.id + ' pressed: its details (aten.conv2d.default, 2×1×8×8 in, padding [1,1]) with stem.weight and stem.bias; stem.weight opened the stem layer in Weights, focused and in view');

  // ---- 4. Colour by parameters, then by the change from the starting weights ------------------------------------------------
  await evaluate(`document.querySelector('#aside .st').scrollIntoView(); true`);
  const plainFill = (await nodes()).find(n => n.id === stem.id).fill;
  await choose('#aside [data-key="st-colour"]', 'parameters'); await settled('parameters');
  const n4 = await nodes();
  for (const n of n4) if (n.kind === 'operation') assert.equal(n.value, parameters.nodes[n.id], n.id + '\'s parameters are the server\'s');
  const fills4 = new Set(n4.filter(n => n.kind === 'operation' && n.value != null).map(n => n.fill));
  assert.ok(fills4.size >= 3, 'The fills differ between nodes: ' + [...fills4].join(' | '));
  assert.notEqual(n4.find(n => n.id === stem.id).fill, plainFill, 'Colouring changes the fill');
  assert.equal(await evaluate(`document.querySelector('#aside .st-legend').dataset.kind`), 'parameters');
  await choose('#aside [data-key="st-colour"]', 'change:start'); await settled('change');
  const n4b = await nodes();
  for (const n of n4b) if (n.kind === 'operation') { const want = change.nodes[n.id]; if (want == null) assert.equal(n.value, null, n.id); else close(n.value, want, n.id + '\'s change'); }
  close(n4b.find(n => n.id === stem.id).value, X.against_initial.stem, 'the stem\'s change is the fixture\'s');
  assert.notDeepEqual(n4b.map(n => n.fill), n4.map(n => n.fill), 'The change colours differently from the parameters');
  await shot('light-1440-3-change');
  // Fit to width: the whole drawing in the drawer's width, every node still a box; pressed again, its actual size.
  await press(byKey('st-fit')); await settled('fit');
  const fit4 = await evaluate(`(() => { const sc = document.querySelector('#aside .st-draw[data-which="this"] .st-scroll'), s = sc.querySelector('svg'); return { box: sc.clientWidth, svg: s.getBoundingClientRect().width, scroll: sc.scrollWidth - sc.clientWidth, natural: s.viewBox.baseVal.width }; })()`);
  assert.ok(fit4.svg <= fit4.box + 1 && fit4.scroll <= 1 && fit4.natural > fit4.box, 'Fitted to the width: ' + JSON.stringify(fit4));
  await shot('light-1440-3b-fit');
  await press(byKey('st-fit')); await settled('actual size');
  assert.ok(await evaluate(`(() => { const sc = document.querySelector('#aside .st-draw[data-which="this"] .st-scroll'); return sc.scrollWidth - sc.clientWidth > 100; })()`), 'Actual size scrolls again');
  check('4. Coloured by parameters (' + fills4.size + ' fills, each value the server\'s), then by the change from the starting weights (stem ' + n4b.find(n => n.id === stem.id).value.toFixed(4) + ', the fixture\'s ' + X.against_initial.stem.toFixed(4) + ')');

  // ---- 5. Compared with the parent ------------------------------------------------------------------------------------------
  const since5 = Date.now();
  await choose('#aside [data-key="st-compare"]', PARENT); await settled('compare');
  assert.equal(asked('model_graph_compare', since5).length, 1);
  const n5 = await nodes(), o5 = await nodes('other');
  assert.equal(o5.length, X.graphs.parent.nodes, 'The parent\'s graph is drawn');
  const status = Object.fromEntries(compared.modules.map(r => [r.path, r.status]));
  for (const n of n5) if (n.kind === 'operation') { const s = status[n.module]; assert.equal(n.mark, s && s !== 'same' ? s : null, n.id + ' in ' + n.module); }
  assert.deepEqual(n5.filter(n => n.mark).map(n => n.module + ':' + n.mark).sort(), ['gate:added', 'head.0:changed', 'head.2:changed']);
  const listed = await evaluate(`[...document.querySelectorAll('#aside .st-difflist li')].map(li => li.dataset.path + ':' + li.dataset.status)`);
  assert.deepEqual(listed, compared.modules.filter(r => r.status !== 'same').map(r => r.path + ':' + r.status));
  assert.deepEqual(o5.filter(n => n.mark).map(n => n.module + ':' + n.mark).sort(), ['head.0:changed', 'head.2:changed']);
  // Folded at depth 0 both drawings fold the same way; head is marked as holding a change.
  await press(byKey('st-fold-1')); await settled('depth 1');
  await press(byKey('st-mod-head')); await settled('head folded');
  const head5 = (await nodes()).find(n => n.id === 'module:head'), headOther = (await nodes('other')).find(n => n.id === 'module:head');
  assert.equal(head5.mark, 'inside'); assert.equal(headOther.mark, 'inside');
  await evaluate(`document.querySelector('#aside .st-sub').scrollIntoView(); true`); await shot('light-1440-4-compare');
  check('5. Compared with ' + PARENT + ' (one model_graph_compare): ' + listed.join(', ') + ' marked and listed; the parent\'s ' + o5.length + ' nodes drawn below with head.0 and head.2 changed; head folded is marked as holding a change in both');

  // ---- 6. Nothing changed: the window regains focus ---------------------------------------------------------------------------
  await evaluate(`window.__changes = 0; window.__mo = new MutationObserver(list => { window.__changes += list.length; }); window.__mo.observe(document.getElementById('aside'), { childList: true, subtree: true, attributes: true, characterData: true }); true`);
  const since6 = Date.now();
  await evaluate(`window.dispatchEvent(new Event('focus')); true`); await reading(since6, WATCHED.concat(['map']), 'focus');
  const changes6 = await evaluate(`(() => { window.__mo.disconnect(); return window.__changes; })()`);
  assert.equal(changes6, 0, 'The drawer is not touched');
  assert.equal(asked('model_graph', since6).length + asked('model_graph_overlay', since6).length + asked('model_graph_compare', since6).length, 0, 'Nothing of the graph is asked again');
  check('6. The window regaining focus: 0 changes in the drawer, nothing of the graph asked again');

  // ---- 7. Light and dark, 1440 and 390 wide ---------------------------------------------------------------------------------
  const seen7 = [], fills7 = {}, headerOver = [];
  for (const [w, hgt] of [[1440, 900], [390, 844]]) for (const name of ['light', 'dark']) {
    const tag = name + '-' + w;
    await size(w, hgt); await load(name, model(DERIVED)); await shown(); await settled(tag);
    await choose('#aside [data-key="st-colour"]', 'change:start'); await settled(tag + ' colour');
    await choose('#aside [data-key="st-compare"]', PARENT); await settled(tag + ' compare');
    await evaluate(`document.querySelector('#aside .st').scrollIntoView(); true`); await pause(200);
    const r = await evaluate(`(() => { const s = document.querySelector('#aside .st'), d = document.getElementById('drawer'); const wide = [...s.querySelectorAll('*')].filter(e => !e.closest('.st-scroll') && e.getBoundingClientRect().width > 0 && e.getBoundingClientRect().right > d.getBoundingClientRect().right + 1).map(e => e.tagName + '.' + e.getAttribute('class')).slice(0, 4); return { drawerRight: Math.round(d.getBoundingClientRect().right - d.parentElement.getBoundingClientRect().right), offenders: [...d.querySelectorAll('*')].filter(e => e.getBoundingClientRect().right > d.getBoundingClientRect().right + 1 && !e.closest('.st-scroll')).map(e => e.tagName + '.' + e.getAttribute('class') + ':' + Math.round(e.getBoundingClientRect().right)).slice(0, 8), nodes: s.querySelectorAll('g.st-node').length, over: d.scrollWidth - d.clientWidth, page: document.documentElement.scrollWidth - innerWidth, wide, scroll: s.querySelector('.st-scroll').getBoundingClientRect().right <= d.getBoundingClientRect().right + 1, label: getComputedStyle(s.querySelector('g.st-node .st-label')).fill }; })()`);
    assert.equal(r.nodes, d.nodes + X.graphs.parent.nodes, tag + ': both drawings');
    // At 390 px the page's own header, strip and map are wider than the window on every tab before this block draws
    // (found here; not this phase's; the drawer's stage among them): the drawer must not pass its stage, nothing in it
    // the drawer, and the page's overflow is recorded.
    assert.ok(r.over <= 1 && r.drawerRight <= 0 && !r.offenders.length && !r.wide.length && r.scroll, tag + ': nothing in the drawer overflows sideways ' + JSON.stringify(r));
    if (r.page > 0) headerOver.push(tag + ' ' + r.page + ' px');
    fills7[tag] = r.label;
    await shot(tag + '-5-structure');
    await evaluate(`document.querySelector('#aside .st-draw[data-which="other"]').scrollIntoView(); true`); await pause(150); await shot(tag + '-6-other');
    seen7.push(tag);
  }
  assert.notEqual(fills7['light-1440'], fills7['dark-1440'], 'The labels follow the theme');
  await size(1440, 900);
  check('7. Both drawings drawn and nothing in the drawer overflowing sideways in ' + seen7.join(', ') + (headerOver.length ? ' (the page itself, outside the drawer, is wider than the window: ' + headerOver.join(', ') + ')' : '') + (shots ? '; screenshots in ' + shots : ''));

  // ---- Nothing failed ---------------------------------------------------------------------------------------------------------
  assert.deepEqual(errors, [], 'Script errors');
  assert.deepEqual(failures, [], 'Failed requests');
  check('No script error, no failed request');
  fs.writeFileSync(path.join(report, 'receipt.json'), JSON.stringify({ status: 'pass', folder, checks }, null, 2) + '\n');
  console.log('Receipt in ' + report);
})().catch(async error => {
  process.exitCode = 1;
  console.error(error); if (serverErrors) console.error('Server:', serverErrors.slice(-4000));
  console.error('Script errors:', JSON.stringify(errors)); console.error('Failed requests:', JSON.stringify(failures));
  try { if (evaluate) { await shot('failure'); console.error('Drawer:', (await evaluate('document.getElementById("aside").innerText')).slice(0, 2500)); } } catch (_) { /* the page is gone */ }
  fs.writeFileSync(path.join(report, 'failure.json'), JSON.stringify({ status: 'failed', error: String(error && error.stack || error), checks, errors, failures }, null, 2) + '\n');
}).finally(async () => {
  try { session?.close(); } catch (_) { /* closed */ }
  for (const child of children.reverse()) await stop(child);
  if (owned) try { dropOwned(...owned); } catch (error) { console.error('Dropping the disposable schemas failed:', error.message); process.exitCode = 1; }
  try { execFileSync('chmod', ['-R', 'u+w', temporary]); } catch (_) { /* nothing was made read-only */ }
  fs.rmSync(temporary, { recursive: true, force: true });
});
