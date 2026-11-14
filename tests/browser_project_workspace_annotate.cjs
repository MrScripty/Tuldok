'use strict';
// Annotating from the page (docs/plans/definition-first-projects/spec-d4.md sections 7 and 9, slice D4d) in a headless
// browser, the owner signed in, no GPU. The fixture is a project of its own in a Git repository: code/samples holds a
// file of each kind (written by examples/tiny-project/code/make_samples.py, and an array written here), the dataset
// datasets/specimens imports them with the import step (built by the command line before Tuldok starts), and the task
// annotations/quality has three stale annotations in its line file (two whose content differs, one whose record is
// gone). datasets/later imports from the same source and is never built.
//   1. The Annotate tab opens on quality; the filter Stale lists the three, each tile marked stale; the record whose
//      content differs says so and Still right puts it right; the one that is gone is removed.
//   2. A task of each of the seven kinds is made with New task and one record annotated with it: review and text by
//      the form's buttons and field, class and tags by the keys 1 to 9 and Enter, boxes by dragging on the image
//      and the arrow keys, spans by selecting text with the pointer (after an astral character), segments by dragging
//      on the waveform and Shift and an arrow; a stretch is played.
//   3. The strip counts "7 definitions, 9 annotations unsaved"; Save writes them: each task's file has exactly the line
//      expected (a box's pixels, a span's offsets and the text they cover, a segment's seconds) and the strip's count
//      is gone. A reload shows each annotation again; the filter by state lists what it should.
//   4. With text typed into the form and not kept, the window regaining focus and a reading on the timer add, remove
//      and change no node of the main area, and the text, the focus and the caret are there. A second session (an
//      agent credential with the right to edit) sets an annotation: the grid shows it and the form is not touched.
//   5. A task on a dataset with no product says so and plans the dataset.
//   6. The Data tab's Import and Freeze forms each keep a definition, written by Save exactly as expected, which
//      `check` accepts; the freeze is planned from its drawer.
//   7. Screenshots of each task's form (an annotation drawn), the stale state, New task and the two Data forms, in light
//      and dark at 1440 by 900 and 1000 by 800 (with --shots <dir>, written there too); nothing overflows sideways.
// It fails on any script error, and on any failed request.
//   node tests/browser_project_workspace_annotate.cjs [--shots <dir>]
const assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const { spawn, execFileSync } = require('node:child_process'), { once } = require('node:events');
const { authenticatedFixture } = require('./auth_helpers.cjs'), { waitForDebugger } = require('./browser_startup.cjs'), { cdpSession } = require('./browser_cdp_session.cjs'), { qaDirectory } = require('./qa_artifacts.cjs');

const root = path.resolve(__dirname, '..');
const argv = process.argv.slice(2), option = name => { const i = argv.indexOf(name); return i >= 0 ? argv[i + 1] : null; };
assert.ok(process.env.TULDOK_DATABASE_URL, 'TULDOK_DATABASE_URL must name a disposable PostgreSQL cluster');
const venv = path.join(root, '.venv', 'bin');
if (fs.existsSync(path.join(venv, 'python'))) process.env.PATH = venv + path.delimiter + process.env.PATH;   // auth_helpers runs python3
const python = fs.existsSync(path.join(venv, 'python')) ? path.join(venv, 'python') : 'python3';
const IDLE_MS = 15000;   // the page's reading while nothing builds (app.js)
const WATCHED = ['summary', 'status', 'build_requests', 'environments', 'runs'];
const REF = 'datasets/specimens';
const IDS = ['arrays__grid.npy', 'clouds__ring.ply', 'images__shapes.png', 'meshes__pyramid.obj', 'sounds__two-tones.wav', 'texts__greeting.txt', 'texts__weather.txt'];

const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'tuldok-annotate-browser-'));
const report = qaDirectory(root, 'project-workspace-annotate');
const shots = option('--shots') ? path.resolve(option('--shots')) : null; if (shots) fs.mkdirSync(shots, { recursive: true });
const children = [], checks = [], errors = [], failures = [], refused = [];
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
/** An operation as the owner (bearer: as that agent credential instead). */
async function api(name, body = {}, bearer = null) {
  const headers = { 'Content-Type': 'application/json', 'Tuldok-Operation-Contract': await contract(name) };
  const response = bearer ? await globalThis.fetch(origin + '/api/project/' + name, { method: 'POST', headers: { ...headers, Authorization: 'Bearer ' + bearer }, body: JSON.stringify(body) })
    : await auth.fetch(origin + '/api/project/' + name, { method: 'POST', headers, body: JSON.stringify(body) });
  const value = await response.json(); assert.equal(response.status, 200, name + ': ' + JSON.stringify(value)); return value;
}
async function credential(label, scopes) {
  const response = await auth.fetch(origin + '/api/access/credentials', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ label, scopes, ttl_seconds: 3600 }) });
  const value = await response.json(); assert.equal(response.status, 201, JSON.stringify(value)); return value.token;
}

// ---- The page's readings, from the browser's network (as browser_project_workspace_still.cjs) ----------------
const calls = new Map(), finished = [];
function network(event) {
  const p = event.params;
  if (event.method === 'Network.requestWillBeSent' && /\/api\/project\/[a-z_]+$/.test(p.request.url)) calls.set(p.requestId, { name: p.request.url.split('/').pop(), sent: Date.now() });
  if ((event.method === 'Network.loadingFinished' || event.method === 'Network.loadingFailed') && calls.has(p.requestId)) { finished.push(Object.assign(calls.get(p.requestId), { done: Date.now() })); calls.delete(p.requestId); }
}
async function reading(since, names, label, tries = 300) {
  await until(() => names.every(name => finished.some(f => f.name === name && f.sent >= since)), 'a reading: ' + label, tries);
  await until(() => !calls.size && Date.now() - Math.max(0, ...finished.map(f => f.done)) > 700, 'the reading done: ' + label, 300);
  await settled(label);
}
/** Waits until nothing reads: no call of the project in flight, no "Reading…", nothing busy. */
async function settled(label) {
  await until(async () => !calls.size && await evaluate(`(() => { const reading = e => [...e.querySelectorAll('.note')].some(n => n.textContent === 'Reading…'); return !reading(document.getElementById('main')) && !reading(document.getElementById('aside')) && !document.getElementById('main').hasAttribute('aria-busy') && !document.querySelector('.act-group [aria-busy]'); })()`), 'settled: ' + label);
  await pause(200);
  await until(async () => !calls.size, 'settled again: ' + label);
}
async function hash(value) { await evaluate(`location.hash = ${JSON.stringify('#' + value)}`); await settled('#' + value); await pause(200); await settled('#' + value); }
const byKey = key => `[data-key=${JSON.stringify(key)}]`;
async function centre(selector) {
  return until(() => evaluate(`(() => { const e = [...document.querySelectorAll(${JSON.stringify(selector)})].find(e => e.offsetParent !== null); if (!e) return null; e.scrollIntoView({ block: 'nearest', inline: 'nearest' }); const r = e.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2, hit = document.elementFromPoint(x, y); return hit && (hit === e || e.contains(hit)) ? { x, y } : null; })()`), 'shown: ' + selector, 100);
}
async function mouse(type, x, y, buttons = 0, modifiers = 0) { await send('Input.dispatchMouseEvent', { type, x, y, modifiers, button: type === 'mouseMoved' ? (buttons ? 'left' : 'none') : 'left', buttons, clickCount: type === 'mouseMoved' ? 0 : 1 }); }
async function press(selector) { const { x, y } = await centre(selector); await mouse('mouseMoved', x, y); await mouse('mousePressed', x, y, 1); await mouse('mouseReleased', x, y); }
async function dragFrom(a, b, steps = 8) { await mouse('mouseMoved', a.x, a.y); await mouse('mousePressed', a.x, a.y, 1); for (let i = 1; i <= steps; i++) await mouse('mouseMoved', a.x + (b.x - a.x) * i / steps, a.y + (b.y - a.y) * i / steps, 1); await mouse('mouseReleased', b.x, b.y); }
const KEYS = { Enter: 13, ArrowLeft: 37, ArrowUp: 38, ArrowRight: 39, ArrowDown: 40, Delete: 46 };
async function key(name, modifiers = 0) {
  const code = KEYS[name] || name.toUpperCase().charCodeAt(0), text = name.length === 1 ? name : name === 'Enter' ? '\r' : undefined;
  await send('Input.dispatchKeyEvent', { type: text ? 'keyDown' : 'rawKeyDown', key: name, code: /^\d$/.test(name) ? 'Digit' + name : name.length === 1 ? 'Key' + name.toUpperCase() : name, windowsVirtualKeyCode: code, modifiers, text });
  await send('Input.dispatchKeyEvent', { type: 'keyUp', key: name, windowsVirtualKeyCode: code, modifiers });
}
async function type(selector, text) { await press(selector); await evaluate(`(() => { const e = document.activeElement; if (e.select) e.select(); return true; })()`); await send('Input.insertText', { text }); }
/** Sets a select's value as a person would choose it, with its change event. */
async function choose(selector, value) { await press(selector); await evaluate(`(() => { const s = document.querySelector(${JSON.stringify(selector)}); s.value = ${JSON.stringify(value)}; s.dispatchEvent(new Event('change', { bubbles: true })); return true; })()`); await key('Escape'); }
async function shot(name) {
  await evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))');
  const png = Buffer.from((await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })).data, 'base64');
  fs.writeFileSync(path.join(report, name + '.png'), png); if (shots) fs.writeFileSync(path.join(shots, name + '.png'), png);
}
const stripText = () => evaluate(`document.getElementById('strip').innerText.replace(/\\s+/g, ' ')`);
const form = () => evaluate(`(() => { const f = document.querySelector('#main .ann-form'); return f ? f.innerText : ''; })()`);
const tiles = () => evaluate(`[...document.querySelectorAll('#main .ann-rec')].map(b => ({ id: b.dataset.id, state: b.dataset.state, stale: b.dataset.stale === '1', unsaved: b.dataset.unsaved === '1', pressed: b.getAttribute('aria-pressed') === 'true' }))`);
const lines = name => { const file = path.join(folder, 'annotations', name + '.jsonl'); return fs.existsSync(file) ? fs.readFileSync(file, 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l)) : []; };

// The watcher of browser_project_workspace_still.cjs, and the form of the Annotate tab on its own.
const WATCHER = `window.__still = (() => {
  const ids = ['tabs', 'strip', 'main', 'aside', 'needs-panel'], el = id => document.getElementById(id);
  let counts = null, flash = 0, timer = null, observers = [];
  const name = n => !n ? '?' : n.nodeType === 1 ? n.tagName.toLowerCase() + (typeof n.className === 'string' && n.className ? '.' + n.className.trim().split(/\\s+/).join('.') : '') : '#text ' + JSON.stringify(String(n.data || '').slice(0, 30));
  const watch = (key, node) => { const o = new MutationObserver(list => {
    if (!counts) return;
    const c = counts[key];
    for (const r of list) {
      if (r.type === 'childList') { c.added += r.addedNodes.length; c.removed += r.removedNodes.length; for (const n of [...r.addedNodes, ...r.removedNodes]) if (c.what.length < 6) c.what.push(name(n) + ' in ' + name(r.target)); }
      else if (r.type === 'characterData') { const msg = el('strip').querySelector('.msg'); if (msg && r.target === msg.lastChild) c.readAt++; else { c.text++; if (c.what.length < 6) c.what.push('text of ' + name(r.target.parentNode)); } }
      else { c.attrs++; if (c.what.length < 6) c.what.push('@' + r.attributeName + ' on ' + name(r.target)); }
    }
  }); o.observe(node, { childList: true, subtree: true, characterData: true, attributes: true }); observers.push(o); };
  return {
    start() {
      for (const o of observers) o.disconnect(); observers = [];
      counts = {}; for (const id of ids.concat(['form'])) counts[id] = { added: 0, removed: 0, attrs: 0, text: 0, readAt: 0, what: [] };
      for (const id of ids) { watch(id, el(id)); for (const e of el(id).querySelectorAll('*')) e.__seen = 1; }
      const f = document.querySelector('#main .ann-form'); if (f) watch('form', f);
      flash = 0; clearInterval(timer); timer = setInterval(() => { if ((el('main').textContent + el('aside').textContent).includes('Reading…')) flash++; }, 50);
    },
    stop() { clearInterval(timer); const fresh = {}; for (const id of ids) fresh[id] = [...el(id).querySelectorAll('*')].filter(e => !e.__seen).length; const r = { counts, flash, fresh }; counts = null; for (const o of observers) o.disconnect(); observers = []; return r; }
  };
})(); true`;

let folder;
(async () => {
  // ---- The fixture: a project in Git, code/samples of each kind, datasets/specimens built --------------------------
  const repo = path.join(temporary, 'fixture'), code = path.join(repo, 'code'); folder = path.join(repo, 'project');
  for (const d of ['datasets', 'annotations']) fs.mkdirSync(path.join(folder, d), { recursive: true });
  fs.mkdirSync(code, { recursive: true });
  fs.writeFileSync(path.join(folder, 'tuldok.json'), JSON.stringify({ format: 'tuldok_project_v1', id: require('node:crypto').randomUUID().replace(/-/g, ''), name: 'Annotation check', code_root: '../code' }, null, 2) + '\n');
  fs.copyFileSync(path.join(root, 'examples', 'tiny-project', 'code', 'make_samples.py'), path.join(code, 'make_samples.py'));
  execFileSync(python, ['make_samples.py'], { cwd: code, env: { ...process.env, PYTHONDONTWRITEBYTECODE: '1' } });
  // An array of 3 by 4 float32, element (i, j) = i * 10 + j.
  { const header = "{'descr': '<f4', 'fortran_order': False, 'shape': (3, 4), }"; const pad = header + ' '.repeat((64 - (10 + header.length + 1) % 64) % 64) + '\n'; const data = Buffer.alloc(48); for (let i = 0; i < 12; i++) data.writeFloatLE(Math.floor(i / 4) * 10 + i % 4, i * 4); const head = Buffer.alloc(10); Buffer.from('\x93NUMPY', 'latin1').copy(head); head[6] = 1; head[7] = 0; head.writeUInt16LE(pad.length, 8); fs.mkdirSync(path.join(code, 'samples', 'arrays'), { recursive: true }); fs.writeFileSync(path.join(code, 'samples', 'arrays', 'grid.npy'), Buffer.concat([head, Buffer.from(pad, 'latin1'), data])); }
  const doc = o => JSON.stringify(Object.assign({ format: 'tuldok_definition_v1' }, o), null, 2) + '\n';
  fs.writeFileSync(path.join(folder, 'datasets', 'specimens.json'), doc({ kind: 'dataset', title: 'Specimens of each kind', run: { step: 'import', settings: { source: 'samples', rights: 'Written for this check; free to use.' } } }));
  fs.writeFileSync(path.join(folder, 'datasets', 'later.json'), doc({ kind: 'dataset', title: 'Texts, not built', run: { step: 'import', settings: { source: 'samples', pattern: '**/*.txt', rights: 'Written for this check; free to use.' } } }));
  fs.writeFileSync(path.join(folder, 'annotations', 'quality.json'), doc({ kind: 'annotation', title: 'Quality', dataset: REF, task: 'class', vocabulary: ['clean', 'noisy'] }));
  const old = 'f'.repeat(64), at = '2026-11-13T09:00:00Z';
  fs.writeFileSync(path.join(folder, 'annotations', 'quality.jsonl'), [
    { record: 'texts__gone.txt', sha256: old, state: 'accepted', value: 'clean', by: 'owner', at },
    { record: 'texts__greeting.txt', sha256: old, state: 'accepted', value: 'clean', by: 'owner', at },
    { record: 'texts__weather.txt', sha256: old, state: 'needs-work', value: 'noisy', note: 'is it rain?', by: 'agent:helper', at }
  ].map(l => JSON.stringify(l) + '\n').join(''));
  const git = ['-c', 'user.name=Tuldok Test', '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false', '-c', 'init.defaultBranch=main', '-C', repo];
  execFileSync('git', [...git, 'init', '-q']); execFileSync('git', [...git, 'add', '-A']); execFileSync('git', [...git, 'commit', '-q', '-m', 'The fixture.']);
  const home = path.join(temporary, 'home'), catalog = path.join(temporary, 'catalog'); fs.mkdirSync(home);
  const env = { ...process.env, TULDOK_PROJECT_HOME: home, TULDOK_SETTINGS: path.join(temporary, 'settings.json') };
  owned = [folder, catalog]; dropOwned(folder, catalog);
  const cli = (...args) => execFileSync(python, ['-m', 'tuldok_project', ...args], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] }).toString();
  assert.match(cli('check', folder), /^0 errors/m);
  cli('build', folder, REF, '--yes');
  let output = '';
  server = launch(python, ['-u', 'app.py', '--port', '0', '--data', catalog, '--project-folder', folder], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] });
  server.stdout.on('data', chunk => { output += chunk; }); server.stderr.on('data', chunk => { serverErrors += chunk; });
  const port = await until(() => { if (server.exitCode !== null) throw Error('Tuldok exited: ' + serverErrors); return output.match(/127\.0\.0\.1:(\d+)/)?.[1]; }, 'Tuldok start-up', 3000);
  origin = 'http://127.0.0.1:' + port;
  auth = authenticatedFixture(); await auth.register(origin, catalog, root);
  const run = (await api('products', { reference: REF })).products[0].run_id;
  const listed = (await api('records', { run, limit: 50 })).records;
  assert.deepEqual(listed.map(r => r.id).sort(), IDS, 'The import made a record of each file');
  const kinds = Object.fromEntries(listed.map(r => [r.id, r.kind]));
  assert.deepEqual([kinds['arrays__grid.npy'], kinds['clouds__ring.ply'], kinds['images__shapes.png'], kinds['meshes__pyramid.obj'], kinds['sounds__two-tones.wav'], kinds['texts__greeting.txt']], ['array', 'pointcloud', 'image', 'mesh', 'audio', 'text']);
  const greeting = fs.readFileSync(path.join(code, 'samples', 'texts', 'greeting.txt'), 'utf8');

  const browser = launch(findBrowser(), ['--headless', '--no-sandbox', '--disable-gpu', '--no-first-run', '--hide-scrollbars', '--autoplay-policy=no-user-gesture-required', '--remote-debugging-port=0', '--window-size=1440,900', '--user-data-dir=' + path.join(temporary, 'browser'), 'about:blank'], { stdio: 'ignore', env: { ...process.env, XDG_CONFIG_HOME: temporary, XDG_CACHE_HOME: temporary } });
  const debugPort = await waitForDebugger(browser, path.join(temporary, 'browser', 'DevToolsActivePort'));
  const target = (await (await fetch('http://127.0.0.1:' + debugPort + '/json')).json()).find(item => item.type === 'page');
  socket = new WebSocket(target.webSocketDebuggerUrl); await once(socket, 'open');
  session = cdpSession(socket, { timeoutMs: 60000, onEvent: event => {
    network(event);
    if (event.method === 'Runtime.exceptionThrown') errors.push(event.params.exceptionDetails.exception?.description || event.params.exceptionDetails.text);
    if (event.method === 'Runtime.consoleAPICalled' && event.params.type === 'error') errors.push(event.params.args.map(a => a.value ?? a.description).join(' '));
    if (event.method === 'Log.entryAdded' && event.params.entry.level === 'error' && !/\/api\/project\/set_annotation$/.test(event.params.entry.url || '')) errors.push(event.params.entry.text + ' ' + (event.params.entry.url || ''));
    if (event.method === 'Network.loadingFailed' && !event.params.canceled) failures.push({ id: event.params.requestId, error: event.params.errorText });
    if (event.method === 'Network.responseReceived' && event.params.response.status >= 400) failures.push({ url: event.params.response.url, status: event.params.response.status });   // the one refusal asked for is taken out below
  } });
  send = session.send;
  evaluate = async expression => { const result = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }); if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails)); return result.result.value; };
  await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable'); await send('Log.enable');
  const size = async (width, height) => send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: false });
  const theme = async name => { await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: name }, { name: 'prefers-reduced-motion', value: 'reduce' }] }); };
  await size(1440, 900); await theme('light');
  await auth.browser(send, origin);   // the owner's session
  const load = async (name, place) => {
    await theme(name);
    await send('Page.navigate', { url: 'about:blank' }); await pause(100);
    await send('Page.navigate', { url: origin + '/?theme=' + name + '#' + place });
    await until(() => evaluate(`document.readyState === 'complete' && !!document.getElementById('needs-btn') && !document.getElementById('needs-btn').disabled`), 'the project read', 1200);
    await settled('opened ' + place);
  };
  const pickTask = async ref => { if ((await evaluate(`document.querySelector('[data-key="ann:task"]').value`)) !== ref) { await choose(byKey('ann:task'), ref); await settled('task ' + ref); } };
  const open = async id => { await press(byKey('ann-rec-' + id)); await until(() => evaluate(`(() => { const h = document.querySelector('#main .ann-form h2'); return !!h && h.textContent === ${JSON.stringify(id)}; })()`), 'the form of ' + id); await settled(id); };
  const filter = async id => { await press(byKey('ann:filter-' + id)); await until(() => evaluate(`document.querySelector('[data-key="ann:filter-${id}"]').getAttribute('aria-pressed') === 'true'`), 'filter ' + id); await settled('filter ' + id); };
  const kept = async label => { await until(async () => !(await evaluate(`!!document.querySelector('.act-group [aria-busy]')`)), 'kept: ' + label); await settled(label); };
  await load('light', 'annotate');

  // ---- 1. Stale annotations, marked and put right -----------------------------------------------------------------
  assert.equal(await evaluate(`[...document.querySelectorAll('#tabs a')].map(a => a.textContent).join(' ')`), 'Map Data Annotate Train Benchmarks Analysis Overview');
  assert.equal(await evaluate(`document.querySelector('[data-key="ann:task"]').value`), 'annotations/quality');
  await filter('stale');
  let t = await tiles();
  assert.deepEqual(t.map(x => [x.id, x.stale]), [['texts__greeting.txt', true], ['texts__weather.txt', true], ['texts__gone.txt', true]], 'The filter Stale lists the three, each marked: ' + JSON.stringify(t));
  await open('texts__greeting.txt');
  assert.match(await form(), /Stale: the record's content differs from what was annotated/);
  await shot('light-1440-stale');
  await press(byKey('annotate:form:still')); await kept('still right');
  await filter('all');
  t = await tiles(); const greet = t.find(x => x.id === 'texts__greeting.txt');
  assert.deepEqual([greet.stale, greet.unsaved, greet.state], [false, true, 'accepted'], 'Still right: no longer stale, unsaved');
  assert.equal((await api('annotation', { task: 'quality', record: 'texts__greeting.txt' })).stale, false);
  await open('texts__gone.txt');
  assert.match(await form(), /Stale: the record is gone from the current product of datasets\/specimens/);
  await press(byKey('annotate:form:remove')); await press(byKey('annotate:form:remove:confirm')); await kept('removed');
  assert.equal((await api('annotation', { task: 'quality', record: 'texts__gone.txt' })).annotation, null, 'The annotation of the record that is gone was removed');
  check('1. The filter Stale listed the three stale annotations, each marked; Still right put texts__greeting.txt right (now unsaved, not stale) and the one whose record is gone was removed');

  // ---- 2. A task of each kind made from the page, one record annotated with each ---------------------------------
  const TASKS = [
    { name: 'looked-at', title: 'Looked at', type: 'review', record: 'meshes__pyramid.obj' },
    { name: 'shape-kind', title: 'Shape kind', type: 'class', vocab: ['round', 'angular', 'flat'], record: 'clouds__ring.ply' },
    { name: 'scene-tags', title: 'Scene tags', type: 'tags', vocab: ['blue', 'orange', 'small', 'large'], record: 'images__shapes.png' },
    { name: 'captions', title: 'Captions', type: 'text', record: 'arrays__grid.npy' },
    { name: 'shapes', title: 'Shapes', type: 'boxes', vocab: ['blue', 'orange'], record: 'images__shapes.png' },
    { name: 'names', title: 'Names', type: 'spans', vocab: ['PER', 'PLACE', 'DATE'], record: 'texts__greeting.txt' },
    { name: 'tones', title: 'Tones', type: 'segments', vocab: ['tone', 'silence'], record: 'sounds__two-tones.wav' }
  ];
  const drawn = {};
  for (const task of TASKS) {
    await press(byKey('annotate:new:new'));
    await until(() => evaluate(`!!document.querySelector('#aside [data-key="newtask:field:title"]')`), 'the New task form');
    await type(byKey('newtask:field:title'), task.title);
    assert.equal(await evaluate(`document.querySelector('[data-key="newtask:field:name"]').value`), task.name, 'The name is made from the title');
    await choose(byKey('newtask:field:dataset'), REF);
    await choose(byKey('newtask:field:task'), task.type);
    assert.equal(await evaluate(`document.querySelector('[data-key="newtask:field:vocabulary"]').closest('label').hidden`), !task.vocab, 'The vocabulary is asked only of the tasks that have one');
    if (task.vocab) { await type(byKey('newtask:field:vocabulary'), task.vocab.join('\n')); }
    if (task.type === 'segments') await shot('light-1440-new-task');
    await press(byKey('newtask:keep')); await kept('kept ' + task.name);
    await until(() => evaluate(`!document.getElementById('drawer').classList.contains('open') && document.querySelector('[data-key="ann:task"]').value === 'annotations/${task.name}'`), 'the new task chosen: ' + task.name);
    await settled(task.name);
    const def = await api('definition', { reference: 'annotations/' + task.name });
    assert.equal(def.unsaved, true);
    assert.equal(def.text, JSON.stringify(Object.assign({ format: 'tuldok_definition_v1', kind: 'annotation', title: task.title, dataset: REF, task: task.type }, task.vocab ? { vocabulary: task.vocab } : {}), null, 2) + '\n', 'The definition text of ' + task.name);
    await open(task.record);
    if (task.type === 'review') {
      // The arrows move without keeping anything.
      await press('#main .ann-form h2'); await key('ArrowRight');
      await until(async () => ((await tiles()).find(x => x.pressed) || {}).id === 'sounds__two-tones.wav', 'the right arrow moved on'); await settled('moved');
      await key('ArrowLeft'); await until(async () => ((await tiles()).find(x => x.pressed) || {}).id === task.record, 'the left arrow moved back'); await settled('moved back');
      await press(byKey('ann:decide-accepted')); await key('Enter');
    }
    if (task.type === 'class') {
      // Accepted without a term is refused: the server's sentence beside the form, the decision still chosen.
      await press(byKey('ann:decide-accepted')); await key('Enter'); await kept('refused');
      const refusal = await evaluate(`(() => { const r = document.querySelector('#main .ann-form .refusal'); return r ? r.innerText : null; })()`);
      assert.match(refusal || '', /cannot be kept; nothing was changed/, 'The refusal is shown beside the form: ' + refusal);
      assert.equal(await evaluate(`document.querySelector('[data-key="ann:decide-accepted"]').getAttribute('aria-pressed')`), 'true', 'Nothing chosen is lost');
      refused.push(refusal.split('\n')[0]);
      await press(byKey('ann:decide-accepted'));
      await press('#main .ann-form h2'); await key('2'); await key('1'); assert.equal(await evaluate(`document.querySelector('[data-key="ann:term-0"]').checked`), true, 'Key 1 chose the first term'); await key('Enter'); }
    if (task.type === 'tags') { await press('#main .ann-form h2'); for (const k of ['1', '2', '3', '3']) await key(k); await press(byKey('ann:decide-needs-work')); await key('Enter'); }
    if (task.type === 'text') { await type(byKey('ann:text'), 'A grid of values that rise by ten a row.'); await press(byKey('ann:decide-accepted')); await press(byKey('annotate:form:keep')); }
    if (task.type === 'boxes') {
      // Pixels (6, 8) to (28, 26) of the 64 by 48 image, wherever it is drawn; then two to the right and one taller by keys.
      const g = await evaluate(`(() => { const c = document.querySelector('#main .ann-view canvas.ann-surface'); c.scrollIntoView({ block: 'center' }); const r = c.getBoundingClientRect(); return { left: r.left, top: r.top, width: r.width, height: r.height, image: c.parentElement.dataset.image }; })()`);
      assert.equal(g.image, '64x48');
      const px = (x, y) => ({ x: g.left + x * g.width / 64, y: g.top + y * g.height / 48 });
      await dragFrom(px(6, 8), px(28, 26));
      await key('ArrowRight'); await key('ArrowRight'); await key('ArrowDown', 8);
      drawn.box = await evaluate(`document.querySelector('#main .ann-items li .ann-coords').textContent`);
      assert.equal(drawn.box, 'x 8, y 8 · 22 × 19', 'The box drawn and moved, in pixels of the image');
      await shot('light-1440-boxes-drawn');
      await press(byKey('ann:decide-accepted')); await key('Enter');
    }
    if (task.type === 'spans') {
      await choose(byKey('ann:new-term'), 'DATE');
      const u = greeting.indexOf('1843');
      const r = await evaluate(`(() => { const pre = document.querySelector('#main .ann-text'); pre.scrollIntoView({ block: 'center' }); const node = [...pre.childNodes].find(n => n.nodeType === 3); const range = document.createRange(); range.setStart(node, ${u}); range.setEnd(node, ${u + 4}); const q = range.getClientRects()[0]; return { left: q.left, right: q.right, y: q.top + q.height / 2 }; })()`);
      await dragFrom({ x: r.left + 1, y: r.y }, { x: r.right - 1, y: r.y });
      drawn.span = await evaluate(`[...document.querySelectorAll('#main .ann-items li')].map(li => ({ start: Number(li.querySelector('[data-key$="-start"]').value), end: Number(li.querySelector('[data-key$="-end"]').value), term: li.querySelector('select').value, covered: li.querySelector('.ann-covered').textContent }))`);
      assert.equal(drawn.span.length, 1); assert.equal(drawn.span[0].covered, '1843'); assert.equal(drawn.span[0].term, 'DATE');
      assert.equal(await evaluate(`document.querySelector('#main .ann-text mark.ann-span').textContent`), '1843', 'The span is shown in the text');
      await shot('light-1440-spans-marked');
      await press(byKey('ann:decide-accepted')); await key('Enter');
    }
    if (task.type === 'segments') {
      const g = await evaluate(`(() => { const c = document.querySelector('#main .ann-view canvas.ann-surface'); c.scrollIntoView({ block: 'center' }); const r = c.getBoundingClientRect(); return { left: r.left, width: r.width, y: r.top + r.height / 2 }; })()`);
      const sx = s => g.left + s / 1.2 * g.width;
      await dragFrom({ x: sx(0.2), y: g.y }, { x: sx(0.55), y: g.y });
      await key('ArrowRight', 8);
      await type(byKey('ann:item-0-text'), 'the first tone');
      await evaluate(`(() => { document.querySelector('#main .ann-view audio').muted = true; return true; })()`);   // the headless browser has no sound to play to
      await press(byKey('ann:item-0-play'));
      const played = await until(() => evaluate(`(() => { const a = document.querySelector('#main .ann-view audio'); return a.currentTime > 0.21 ? a.currentTime : null; })()`), 'the stretch plays', 60);
      await until(() => evaluate(`document.querySelector('#main .ann-view audio').paused`), 'the stretch stops at its end', 60);
      const stoppedAt = await evaluate(`document.querySelector('#main .ann-view audio').currentTime`);
      drawn.segment = await evaluate(`(() => { const li = document.querySelector('#main .ann-items li'); return { start: Number(li.querySelector('[data-key$="-start"]').value), end: Number(li.querySelector('[data-key$="-end"]').value), term: li.querySelector('select').value }; })()`);
      assert.ok(Math.abs(drawn.segment.start - 0.2) <= 0.01 && Math.abs(drawn.segment.end - 0.6) <= 0.01, 'The segment dragged and lengthened by a key: ' + JSON.stringify(drawn.segment));
      assert.ok(stoppedAt >= drawn.segment.end - 0.05 && stoppedAt <= drawn.segment.end + 0.3, 'The stretch stopped at its end: ' + stoppedAt);
      drawn.played = played;
      await shot('light-1440-segments-marked');
      await press(byKey('ann:decide-accepted')); await press(byKey('annotate:form:keep'));
    }
    await kept('annotated ' + task.name);
    const got = await api('annotation', { task: task.name, record: task.record });
    assert.ok(got.annotation && got.unsaved, 'Kept and unsaved: ' + task.name + ' ' + JSON.stringify(got));
    task.line = got.annotation;
  }
  check('2. Seven tasks made with New task (review, class, tags, text, boxes, spans, segments), each kept as the definition expected, and one record annotated with each: class and tags by the keys, boxes by dragging on the image and the arrows (' + drawn.box + '), spans by selecting "1843" after the 🌍, segments by dragging on the waveform and Shift with an arrow (' + drawn.segment.start + ' to ' + drawn.segment.end + ' s, played from ' + drawn.played.toFixed(2) + ' s)');

  // ---- 3. The strip, Save, the files, a reload, the filter ------------------------------------------------------
  const status = await api('status');
  assert.equal(status.unsaved.length, 7); assert.equal(status.annotations_unsaved.reduce((n, x) => n + x.records, 0), 9);
  assert.match(await stripText(), /7 definitions, 9 annotations unsaved/, 'The strip counts both');
  await press(byKey('save:save')); await kept('saved');
  await until(async () => !/unsaved/.test(await stripText()), 'the strip without unsaved');
  const after = await api('status'); assert.deepEqual([after.unsaved, after.annotations_unsaved], [[], []]);
  const expected = {
    'looked-at': { state: 'accepted', value: null }, 'shape-kind': { state: 'draft', value: 'round' }, 'scene-tags': { state: 'needs-work', value: ['blue', 'orange'] },
    captions: { state: 'accepted', value: 'A grid of values that rise by ten a row.' }, shapes: { state: 'accepted', value: [{ term: 'blue', x: 8, y: 8, w: 22, h: 19 }] }
  };
  const cps = Array.from(greeting), start = cps.indexOf('1');
  assert.ok(cps.length < greeting.length, 'The greeting holds an astral character before the span');
  expected.names = { state: 'accepted', value: [{ term: 'DATE', start, end: start + 4 }] };
  expected.tones = { state: 'accepted', value: [{ term: 'tone', start: drawn.segment.start, end: drawn.segment.end, text: 'the first tone' }] };
  for (const task of TASKS) {
    const file = lines(task.name);
    assert.equal(file.length, 1, task.name + ' has one line');
    const line = file[0];
    assert.deepEqual(Object.keys(line), ['record', 'sha256', 'state', 'value', 'by', 'at'], 'The keys of a line, in order');
    assert.deepEqual({ record: line.record, state: line.state, value: line.value, by: line.by }, Object.assign({ record: task.record, by: 'owner' }, expected[task.name]), 'The line of ' + task.name);
    assert.equal(line.sha256, listed.find(r => r.id === task.record).sha256, 'The line carries the record\'s hash');
  }
  assert.equal(cps.slice(lines('names')[0].value[0].start, lines('names')[0].value[0].end).join(''), '1843', 'The span\'s offsets, in code points, cover 1843');
  assert.deepEqual(lines('quality').map(l => [l.record, l.state, l.sha256 === old]), [['texts__greeting.txt', 'accepted', false], ['texts__weather.txt', 'needs-work', true]], 'quality: put right, left stale, the gone one removed');
  check('3. The strip read "7 definitions, 9 annotations unsaved"; Save wrote each task\'s file with exactly the line expected (the box at 8, 8, 22 by 19 pixels; the span ' + start + ' to ' + (start + 4) + ' covering "1843"; the segment ' + drawn.segment.start + ' to ' + drawn.segment.end + ' s), and the count is gone');
  await load('light', 'annotate');
  for (const task of TASKS) {
    await pickTask('annotations/' + task.name);
    const tile = (await tiles()).find(x => x.id === task.record);
    assert.equal(tile.state, expected[task.name].state, 'After a reload the tile of ' + task.name + ' shows its state');
    await open(task.record);
    const text = await form();
    if (task.type === 'boxes') assert.match(text, /x 8, y 8 · 22 × 19/);
    if (task.type === 'spans') assert.match(text, /1843/);
    if (task.type === 'class') assert.equal(await evaluate(`document.querySelector('[data-key="ann:term-0"]').checked`), true);
    if (task.type === 'tags') assert.deepEqual(await evaluate(`[0, 1, 2, 3].map(i => document.querySelector('[data-key="ann:term-' + i + '"]').checked)`), [true, true, false, false]);
    if (task.type === 'text') assert.equal(await evaluate(`document.querySelector('[data-key="ann:text"]').value`), expected.captions.value);
    if (task.type === 'segments') assert.equal(await evaluate(`document.querySelector('[data-key="ann:item-0-text"]').value`), 'the first tone');
  }
  await pickTask('annotations/captions');
  await filter('accepted'); assert.deepEqual((await tiles()).map(x => x.id), ['arrays__grid.npy'], 'Accepted lists the one accepted');
  await filter('todo'); assert.equal((await tiles()).length, 6, 'To do lists the six others');
  await filter('rejected'); assert.equal((await tiles()).length, 0);
  await filter('all'); assert.equal((await tiles()).length, 7);
  check('3. After a reload each task shows its annotation (tile state and form); the filter lists 1 accepted, 6 to do, 0 rejected, 7 in all');

  // ---- 4. Typed and not kept: nothing is touched; a second session's annotation reaches the grid -------------------
  await open('texts__weather.txt');
  await press(byKey('ann:text'));
  await send('Input.insertText', { text: 'Rain over Manila' });
  await evaluate(`(() => { const e = document.activeElement; e.setSelectionRange(4, 4); return true; })()`);
  const typed = () => evaluate(`({ key: document.activeElement.dataset.key, value: document.activeElement.value, caret: document.activeElement.selectionStart })`);
  const before = await typed();
  assert.deepEqual(before, { key: 'ann:text', value: 'Rain over Manila', caret: 4 });
  await evaluate(WATCHER); await evaluate(`window.__still.start()`);
  let since = Date.now(); await evaluate(`window.dispatchEvent(new Event('focus')); true`); await reading(since, WATCHED.concat(['map']), 'focus');
  since = Date.now(); await reading(since, WATCHED, 'the timer', Math.round((IDLE_MS + 8000) / 100));
  const r4 = await evaluate(`window.__still.stop()`);
  for (const id of ['tabs', 'main', 'aside']) assert.deepEqual([r4.counts[id].added, r4.counts[id].removed, r4.counts[id].attrs, r4.counts[id].text, r4.fresh[id]], [0, 0, 0, 0, 0], id + ' untouched: ' + JSON.stringify(r4.counts[id]));
  assert.equal(r4.flash, 0);
  assert.deepEqual(await typed(), before, 'The typed text, the focus and the caret stay');
  check('4. With "' + before.value + '" typed and not kept (caret at 4), the window regaining focus and a reading on the timer added, removed and changed no node; the text, focus and caret are there');
  const agent = await credential('An annotating agent', ['inspect', 'edit']);
  await api('set_annotation', { task: 'captions', items: [{ record: 'clouds__ring.ply', state: 'accepted', value: 'A ring of points.' }] }, agent);
  assert.equal(lines('captions').length, 1);
  await evaluate(`window.__still.start()`);
  since = Date.now(); await evaluate(`window.dispatchEvent(new Event('focus')); true`); await reading(since, WATCHED.concat(['map']), 'focus after the agent');
  await until(async () => ((await tiles()).find(x => x.id === 'clouds__ring.ply') || {}).state === 'accepted', 'the agent\'s annotation in the grid');
  const r5 = await evaluate(`window.__still.stop()`);
  assert.ok(r5.counts.main.added > 0, 'The grid was drawn again');
  assert.deepEqual([r5.counts.form.added, r5.counts.form.removed, r5.counts.form.attrs, r5.counts.form.text], [0, 0, 0, 0], 'The form was not touched: ' + JSON.stringify(r5.counts.form));
  assert.deepEqual(await typed(), before, 'The typed text, the focus and the caret stay');
  const ring = (await tiles()).find(x => x.id === 'clouds__ring.ply'); assert.equal(ring.unsaved, true);
  assert.equal((await api('annotation', { task: 'captions', record: 'clouds__ring.ply' })).annotation.by, 'agent:An annotating agent');
  check('4. A second session (an agent allowed to edit) annotated clouds__ring.ply: the grid shows it accepted and unsaved after one reading, the form was not touched and the typed text is there');
  // Revert from the page: the agent's annotation goes; the typed text of the record left stays in this page.
  await open('clouds__ring.ply');
  await press(byKey('annotate:form:revert')); await press(byKey('annotate:form:revert:confirm')); await kept('reverted');
  assert.equal((await api('annotation', { task: 'captions', record: 'clouds__ring.ply' })).annotation, null, 'Reverted: no annotation');
  assert.equal(((await tiles()).find(x => x.id === 'clouds__ring.ply') || {}).state, 'none');
  await open('texts__weather.txt');
  assert.equal(await evaluate(`document.querySelector('[data-key="ann:text"]').value`), 'Rain over Manila', 'The typed text of the record left is there when it is chosen again');
  check('4. Revert on the page put back clouds__ring.ply (no annotation again); the text typed on texts__weather.txt was there on coming back to it');

  // ---- 5. A task on a dataset with no product ------------------------------------------------------------------------
  await load('light', 'annotate');
  await press(byKey('annotate:new:new'));
  await until(() => evaluate(`!!document.querySelector('#aside [data-key="newtask:field:title"]')`), 'the New task form');
  await type(byKey('newtask:field:title'), 'Later review'); await choose(byKey('newtask:field:dataset'), 'datasets/later'); await choose(byKey('newtask:field:task'), 'review');
  await press(byKey('newtask:keep')); await kept('later review');
  await until(() => evaluate(`/datasets\\/later has no product on this machine/.test(document.getElementById('main').innerText)`), 'no product');
  await press(byKey('annotate:plan:plan'));
  await until(() => evaluate(`location.hash === '#train/' + encodeURIComponent('plan:datasets/later')`), 'the plan of datasets/later');
  await settled('plan of later');
  assert.match(await evaluate(`document.getElementById('aside').innerText`), /datasets\/later/);
  check('5. A task on datasets/later, which has no product, says so and its "Plan a build" opens the plan of datasets/later');

  // ---- 6. Import and Freeze on the Data tab ---------------------------------------------------------------------------
  await hash('data');
  await press(byKey('data:new:import'));
  await until(() => evaluate(`!!document.querySelector('#aside [data-key="newimport:field:title"]')`), 'the Import form');
  await type(byKey('newimport:field:title'), 'Notes only');
  await type(byKey('newimport:field:source'), 'samples'); await type(byKey('newimport:field:pattern'), '**/*.txt');
  await type(byKey('newimport:field:rights'), 'Written for this check.'); await press(byKey('newimport:field:lines'));
  await shot('light-1440-import');
  await press(byKey('newimport:keep')); await kept('import kept');
  await until(() => evaluate(`location.hash === '#data/' + encodeURIComponent('datasets/notes-only')`), 'the new dataset\'s drawer');
  await press(byKey('data:new:freeze'));
  await until(() => evaluate(`!!document.querySelector('#aside [data-key="newfreeze:field:title"]')`), 'the Freeze form');
  await type(byKey('newfreeze:field:title'), 'Specimens v1');
  await choose(byKey('newfreeze:field:dataset'), REF); await settled('freeze dataset');
  const boxes = await evaluate(`[...document.querySelectorAll('#aside [data-key^="newfreeze:field:task-"]')].map(c => [c.dataset.key.slice(21), c.checked])`);
  assert.deepEqual(boxes.map(b => b[0]), ['annotations/captions', 'annotations/looked-at', 'annotations/names', 'annotations/quality', 'annotations/scene-tags', 'annotations/shape-kind', 'annotations/shapes', 'annotations/tones'], 'The tasks on specimens');
  await press(byKey('newfreeze:field:task-annotations/captions'));   // off: the first task is then looked-at
  await press(byKey('newfreeze:field:task-annotations/looked-at')); await press(byKey('newfreeze:field:task-annotations/shapes'));
  await type(byKey('newfreeze:field:seed'), '3'); await type(byKey('newfreeze:field:shares'), 'train 2, test 1');
  await press(byKey('newfreeze:field:include-needs-work'));
  await shot('light-1440-freeze');
  await press(byKey('newfreeze:keep')); await kept('freeze kept');
  await until(() => evaluate(`location.hash === '#data/' + encodeURIComponent('datasets/specimens-v1')`), 'the frozen dataset\'s drawer');
  await settled('frozen drawer');
  await press(byKey('dataedit:datasets/specimens-v1:plan'));
  await until(() => evaluate(`location.hash === '#train/' + encodeURIComponent('plan:datasets/specimens-v1')`), 'the plan of the freeze'); await settled('plan of the freeze');
  const plan = await evaluate(`document.getElementById('aside').innerText`);
  assert.match(plan, /A build of datasets\/specimens-v1/); assert.match(plan, /1 step to build/);
  const planned = await api('plan', { targets: ['datasets/specimens-v1'] });
  assert.deepEqual(planned.steps.filter(s => s.action === 'build').map(s => [s.reference, s.step]), [['datasets/specimens-v1', 'freeze']], 'The freeze is planned');
  await hash('data'); await press(byKey('save:save')); await kept('saved the datasets');
  const want = {
    'notes-only': { format: 'tuldok_definition_v1', kind: 'dataset', title: 'Notes only', run: { step: 'import', settings: { source: 'samples', pattern: '**/*.txt', rights: 'Written for this check.', lines: true } } },
    'specimens-v1': { format: 'tuldok_definition_v1', kind: 'dataset', title: 'Specimens v1', run: { step: 'freeze', inputs: { records: REF }, annotations: ['annotations/looked-at', 'annotations/shapes'], settings: { seed: 3, shares: { train: 2, test: 1 }, include: ['accepted', 'needs-work'] } } }
  };
  for (const [name, d] of Object.entries(want)) assert.equal(fs.readFileSync(path.join(folder, 'datasets', name + '.json'), 'utf8'), JSON.stringify(d, null, 2) + '\n', 'The definition written for ' + name);
  const checked = cli('check', folder);
  assert.match(checked, /^0 errors/m, checked);
  check('6. Import and Freeze kept datasets/notes-only and datasets/specimens-v1, written by Save exactly as expected; `check` reports ' + checked.trim().split('\n').pop().replace(/ in .*/, '') + '; the freeze was planned from its drawer (1 step to build: tuldok freeze)');

  // ---- 7. Screenshots in both themes at two sizes; nothing overflows sideways --------------------------------------
  const seen = [];
  const over = async label => { const o = await evaluate(`(() => { const m = document.getElementById('main'), a = document.getElementById('drawer'); return { page: document.documentElement.scrollWidth - innerWidth, main: m.scrollWidth - m.clientWidth, drawer: a.scrollWidth - a.clientWidth }; })()`); assert.ok(o.page <= 0 && o.main <= 1 && o.drawer <= 1, label + ': sideways overflow ' + JSON.stringify(o)); };
  for (const [w, hgt] of [[1440, 900], [1000, 800]]) for (const name of ['light', 'dark']) {
    await size(w, hgt); await load(name, 'annotate');
    const tag = name + '-' + w;
    for (const task of TASKS.concat([{ name: 'quality', record: 'texts__weather.txt', type: 'stale' }])) {
      await pickTask('annotations/' + task.name); await open(task.record);
      await evaluate(`(() => { document.getElementById('main').scrollTop = 0; return true; })()`);
      if (task.type === 'boxes') { await press('#main canvas.ann-surface'); await key(']'); }   // a box chosen, its handles drawn
      await over(tag + ' ' + task.type); await shot(tag + '-' + task.type); seen.push(tag + ' ' + task.type);
      if (['spans', 'segments', 'boxes'].includes(task.type) && w === 1000) { await evaluate(`(() => { document.querySelector('#main .ann-form').scrollIntoView({ block: 'start' }); return true; })()`); await shot(tag + '-' + task.type + '-form'); }
    }
    await press(byKey('annotate:new:new')); await until(() => evaluate(`!!document.querySelector('#aside [data-key="newtask:field:title"]')`), 'the New task form');
    await type(byKey('newtask:field:title'), 'Mood of each sound'); await type(byKey('newtask:field:vocabulary'), 'calm\nlively');
    await over(tag + ' new task'); await shot(tag + '-new-task');
    await hash('data'); await press(byKey('data:new:import')); await until(() => evaluate(`!!document.querySelector('#aside [data-key="newimport:field:title"]')`), 'the Import form'); await settled('import');
    await over(tag + ' import'); await shot(tag + '-import');
    await press(byKey('data:new:freeze')); await until(() => evaluate(`!!document.querySelector('#aside [data-key="newfreeze:field:title"]')`), 'the Freeze form'); await settled('freeze');
    await over(tag + ' freeze'); await shot(tag + '-freeze');
  }
  await size(1440, 900);
  check('7. Nothing overflows sideways in light and dark at 1440 × 900 and 1000 × 800 (' + seen.length + ' views of the forms, and New task, Import and Freeze)' + (shots ? '; screenshots in ' + shots : ''));

  // ---- Nothing failed ---------------------------------------------------------------------------------------------------
  assert.deepEqual(errors, [], 'Script errors');
  const asked = failures.filter(f => f.url && /\/api\/project\/set_annotation$/.test(f.url));
  assert.equal(asked.length, 1, 'The one refusal asked for: ' + JSON.stringify(failures));
  assert.deepEqual(failures.filter(f => !asked.includes(f)), [], 'Failed requests');
  check('No script error, no failed request but the refusal of set_annotation asked for ("' + refused[0] + '")');
  fs.writeFileSync(path.join(report, 'receipt.json'), JSON.stringify({ status: 'pass', folder, checks }, null, 2) + '\n');
  console.log('Receipt in ' + report);
})().catch(async error => {
  process.exitCode = 1;
  console.error(error); if (serverErrors) console.error('Server:', serverErrors.slice(-4000));
  console.error('Script errors:', JSON.stringify(errors)); console.error('Failed requests:', JSON.stringify(failures));
  try { if (evaluate) { await shot('failure'); console.error('Page:', (await evaluate('document.body.innerText')).slice(0, 3000)); } } catch (_) { /* the page is gone */ }
  fs.writeFileSync(path.join(report, 'failure.json'), JSON.stringify({ status: 'failed', error: String(error && error.stack || error), checks, errors, failures }, null, 2) + '\n');
}).finally(async () => {
  try { session?.close(); } catch (_) { /* closed */ }
  for (const child of children.reverse()) await stop(child);
  if (owned) try { dropOwned(...owned); } catch (error) { console.error('Dropping the disposable schemas failed:', error.message); process.exitCode = 1; }
  try { execFileSync('chmod', ['-R', 'u+w', temporary]); } catch (_) { /* nothing was made read-only */ }
  fs.rmSync(temporary, { recursive: true, force: true });
});
