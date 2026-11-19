'use strict';
// The fields a run kept, side by side, in the Analysis tab (docs/plans/definition-first-projects/spec-d6.md sections
// 3 and 5, slice D6b) in a headless browser, the owner signed in, no GPU. Tuldok runs with --project-folder on a copy
// of the minimal fixture, in a Git repository of its own, with three recipes of earlier work and a benchmark of
// earlier work whose subjects they are: recipes/fd-kept, whose adopted product keeps two cases of a 6 x 5 x 4 field
// (tests/project_fields_browser_fixture.py, with probe.json and a diagnostic file), recipes/fd-none, whose product
// keeps none, and recipes/fd-absent, with no product. The fixture prints the fields and their figures.
//   1. Analysis on fd-kept shows Kept fields with the case's name and split, three panels and the figures equal to
//      the fixture's arithmetic, and what the run reported; fd-none shows one line; fd-absent no section.
//   2. The panels' pixels: Native and Predicted differ where the fixture differs; the error panel is the middle
//      colour (--ramp-mid) where they agree.
//   3. Hover shows the cell's position and its three values.
//   4. The slider and the axis select change the slice (a different image) with one field_compare each, the
//      canvases drawn again in place and the rest of the tab untouched (marked elements survive).
//   5. "Remove the mean" turns the error panel of the constant-offset case to the middle colour, one request.
//   6. A reload restores the case, axis, position and mean option; a return to the window and a timer reading
//      touch nothing and ask nothing of the fields.
//   7. Light and dark at 1440 and 390 wide: no blank canvas, no sideways overflow, the panels side by side when
//      wide and stacked when narrow; no script error and no failed request.
//   node tests/browser_project_workspace_fields.cjs [--shots <dir>]
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
const KEPT = 'recipes/fd-kept', NONE = 'recipes/fd-none', ABSENT = 'recipes/fd-absent', BENCH = 'kept-fields';
const RECIPES = {
  'fd-kept': { title: 'Fields kept', labels: { short: 'FK', trained_at: '2026-10-01' }, change: 'architecture' },
  'fd-none': { title: 'Fields not kept', labels: { short: 'FN', trained_at: '2026-10-03' }, change: 'refinement' },
  'fd-absent': { title: 'Fields absent', labels: { short: 'FA', trained_at: '2026-10-05' }, change: 'component' }
};

const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'tuldok-fields-browser-'));
const report = qaDirectory(root, 'project-workspace-fields');
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
/** Waits until nothing reads: no "Reading…", nothing busy in the main area, no request of the project in flight. */
async function settled(label) {
  await until(() => evaluate(`(() => { const m = document.getElementById('main'); return ![...m.querySelectorAll('.note')].some(n => n.textContent === 'Reading…') && !m.hasAttribute('aria-busy') && !m.querySelector('[aria-busy]'); })()`).then(ok => ok && !calls.size), 'settled: ' + label);
  await pause(200);
}
const byKey = key => `[data-key=${JSON.stringify(key)}]`;
async function mouse(type, x, y, buttons = 0) { await send('Input.dispatchMouseEvent', { type, x, y, button: type === 'mouseMoved' ? (buttons ? 'left' : 'none') : 'left', buttons, clickCount: type === 'mouseMoved' ? 0 : 1 }); }
async function press(selector) {
  const at = await until(() => evaluate(`(() => { const e = document.querySelector(${JSON.stringify(selector)}); if (!e) return null; e.scrollIntoView({ block: 'center', inline: 'nearest' }); const r = e.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; })()`), 'shown: ' + selector, 100);
  await pause(100); await mouse('mouseMoved', at.x, at.y); await mouse('mousePressed', at.x, at.y, 1); await mouse('mouseReleased', at.x, at.y);
}
/** Chooses an option of a select the way the keyboard changes it (the change event the page listens to). */
async function choose(selector, value) { await evaluate(`(() => { const s = document.querySelector(${JSON.stringify(selector)}); s.focus(); s.value = ${JSON.stringify(value)}; s.dispatchEvent(new Event('change', { bubbles: true })); return true; })()`); }
/** Moves a slider to a value as a drag ends there (one input event). */
async function slide(selector, value) { await evaluate(`(() => { const r = document.querySelector(${JSON.stringify(selector)}); r.focus(); r.value = ${JSON.stringify(String(value))}; r.dispatchEvent(new Event('input', { bubbles: true })); return true; })()`); }
async function frames() { await evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))'); }
async function shot(name) {
  await frames();
  const png = Buffer.from((await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })).data, 'base64');
  fs.writeFileSync(path.join(report, name + '.png'), png); if (shots) fs.writeFileSync(path.join(shots, name + '.png'), png);
}
const close = (a, b, label, tol = 1e-12) => assert.ok(Math.abs(a - b) <= tol * Math.max(1, Math.abs(b)), label + ': ' + a + ' is not ' + b);

// What a panel shows: a sum over its pixels that changes when the drawing does, how many are drawn, and the colour at
// the centre of each cell of a rows x columns grid drawn square in it (as inside.js's contain() places it).
const PANEL = `(id, rows, cols) => { const c = document.querySelector('section.fld canvas.fld-cv[data-panel="' + id + '"]'); if (!c || !c.width) return null;
  const g = c.getContext('2d'), d = g.getImageData(0, 0, c.width, c.height).data; let drawn = 0, sum = 0; for (let i = 0; i < d.length; i += 4) if (d[i + 3]) { drawn++; sum = (sum + (i / 4 + 1) * (d[i] * 3 + d[i + 1] * 5 + d[i + 2] * 7)) % 2147483647; }
  const W = c.width, H = c.height, s = rows === 1 ? null : Math.min(W / cols, H / rows), x0 = s ? (W - cols * s) / 2 : 0, y0 = s ? (H - rows * s) / 2 : 0, sx = s || W / cols, sy = s || H;
  const cells = []; for (let r = 0; r < rows; r++) { const row = []; for (let k = 0; k < cols; k++) { const p = g.getImageData(Math.floor(x0 + (k + 0.5) * sx), Math.floor(y0 + (r + 0.5) * sy), 1, 1).data; row.push([p[0], p[1], p[2], p[3]]); } cells.push(row); }
  const box = c.getBoundingClientRect(); return { drawn, sum, cells, label: c.getAttribute('aria-label'), times: Number(c.dataset.drawn || 0), box: { left: box.left, top: box.top, width: box.width, height: box.height }, cell: { x0, y0, sx, sy, dpr: window.devicePixelRatio || 1 } }; }`;
const panel = (id, rows, cols) => evaluate(`(${PANEL})(${JSON.stringify(id)}, ${rows}, ${cols})`);
const MID = `(() => { const v = getComputedStyle(document.documentElement).getPropertyValue('--ramp-mid').trim(), n = parseInt(v.slice(1), 16); return [n >> 16, (n >> 8) & 255, n & 255, 255]; })()`;
const figuresShown = () => evaluate(`Object.fromEntries([...document.querySelectorAll('section.fld .fld-figures tr')].map(r => [r.dataset.fig, r.dataset.value === '' ? null : Number(r.dataset.value)]))`);
const stateShown = () => evaluate(`(() => { const f = document.querySelector('section.fld'); if (!f) return null; const s = q => f.querySelector(q); return { kase: s('[data-key="fld-case"]') ? s('[data-key="fld-case"]').value : null, caseText: s('[data-key="fld-case"]') ? s('[data-key="fld-case"]').selectedOptions[0].textContent : (s('.fld-name') || {}).textContent, facts: (s('.fld-facts') || {}).textContent, axis: s('[data-key="fld-axis"]') ? s('[data-key="fld-axis"]').value : null, sliders: [...f.querySelectorAll('input[type=range]')].map(r => [r.dataset.axis, r.value]), mean: s('[data-key="fld-mean"]') ? s('[data-key="fld-mean"]').getAttribute('aria-pressed') : null, panels: f.querySelectorAll('canvas.fld-cv').length, none: (s('.fld-none') || {}).textContent || null, reported: [...f.querySelectorAll('.fld-reported tr')].map(r => [r.querySelector('th').textContent, Number(r.dataset.value)]) }; })()`);
/** The value of the fixture's field at an index of its shape, in C order. */
const at = (values, shape, i) => values[(i[0] * shape[1] + i[1]) * shape[2] + i[2]];

// The watcher of browser_project_workspace_still.cjs: added, removed and changed nodes, "Reading…", the scrolls.
const WATCHER = `window.__still = (() => {
  const ids = ['tabs', 'strip', 'main', 'aside', 'needs-panel'], el = id => document.getElementById(id);
  let counts = null, flash = 0, timer = null;
  const name = n => !n ? '?' : n.nodeType === 1 ? n.tagName.toLowerCase() + (typeof n.className === 'string' && n.className ? '.' + n.className.trim().split(/\\s+/).join('.') : '') : '#text ' + JSON.stringify(String(n.data || '').slice(0, 30));
  for (const id of ids) new MutationObserver(list => {
    if (!counts) return;
    const c = counts[id];
    for (const r of list) {
      if (r.type === 'childList') { c.added += r.addedNodes.length; c.removed += r.removedNodes.length; for (const n of [...r.addedNodes, ...r.removedNodes]) if (c.what.length < 6) c.what.push(name(n) + ' in ' + name(r.target)); }
      else if (r.type === 'characterData') { const msg = el('strip').querySelector('.msg'); if (msg && r.target === msg.lastChild) c.readAt++; else { c.text++; if (c.what.length < 6) c.what.push('text of ' + name(r.target.parentNode)); } }
      else { c.attrs++; if (c.what.length < 6) c.what.push('@' + r.attributeName + ' on ' + name(r.target)); }
    }
  }).observe(el(id), { childList: true, subtree: true, characterData: true, attributes: true });
  return {
    start() { counts = {}; for (const id of ids) { counts[id] = { added: 0, removed: 0, attrs: 0, text: 0, readAt: 0, what: [] }; for (const e of el(id).querySelectorAll('*')) e.__seen = 1; } flash = 0; clearInterval(timer); timer = setInterval(() => { if (el('main').textContent.includes('Reading…')) flash++; }, 50); },
    stop() { clearInterval(timer); const fresh = {}; for (const id of ids) fresh[id] = [...el(id).querySelectorAll('*')].filter(e => !e.__seen).length; const r = { counts, flash, fresh, scroll: el('main').scrollTop }; counts = null; return r; }
  };
})(); true`;
const touched = (r, ids) => ids.filter(id => { const c = r.counts[id]; return c.added || c.removed || c.attrs || c.text || r.fresh[id]; }).map(id => id + ' ' + JSON.stringify(r.counts[id]) + ' new ' + r.fresh[id]);

(async () => {
  // ---- The fixture: minimal + three recipes and a benchmark of earlier work, in Git; two products adopted ----------------
  fs.cpSync(path.join(root, 'tests', 'fixtures', 'tuldok_project', 'minimal'), path.join(temporary, 'fixture'), { recursive: true });
  const folder = path.join(temporary, 'fixture', 'project');
  for (const [name, r] of Object.entries(RECIPES)) fs.writeFileSync(path.join(folder, 'recipes', name + '.json'), JSON.stringify({ format: 'tuldok_definition_v1', kind: 'recipe', title: r.title, description: 'A model for the browser check of kept fields.', labels: r.labels,
    earlier_work: { rebuild: 'no', reason: 'Written by the browser check of kept fields; only its product remains.' }, model: 'models/stepper', group: 'steppers', change: r.change }, null, 2) + '\n');
  fs.writeFileSync(path.join(folder, 'benchmarks', BENCH + '.json'), JSON.stringify({ format: 'tuldok_definition_v1', kind: 'benchmark', title: 'Kept pressure fields', description: 'The pressure the models predicted, beside the native field.',
    earlier_work: { rebuild: 'no', reason: 'Measured before this format.' }, metrics: [{ id: 'pressure_l2', title: 'Pressure relative L2', better: 'lower' }],
    subjects: [{ name: 'fd-kept', title: 'Fields kept', recipe: KEPT }, { name: 'fd-none', title: 'Fields not kept', recipe: NONE }, { name: 'fd-absent', title: 'Fields absent', recipe: ABSENT }] }, null, 2) + '\n');
  const git = ['-c', 'user.name=Tuldok Test', '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false', '-c', 'init.defaultBranch=main', '-C', path.join(temporary, 'fixture')];
  execFileSync('git', [...git, 'init', '-q']); execFileSync('git', [...git, 'add', '-A']); execFileSync('git', [...git, 'commit', '-q', '-m', 'The fixture.']);
  const files = path.join(temporary, 'fields');
  const X = JSON.parse(execFileSync(python, [path.join(root, 'tests', 'project_fields_browser_fixture.py'), '--out', files]).toString());
  const home = path.join(temporary, 'home'), catalog = path.join(temporary, 'catalog'); fs.mkdirSync(home);
  const env = { ...process.env, TULDOK_PROJECT_HOME: home, TULDOK_SETTINGS: path.join(temporary, 'settings.json') };
  owned = [folder, catalog]; dropOwned(folder, catalog);
  const cli = (...args) => execFileSync(python, ['-m', 'tuldok_project', ...args], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] }).toString();
  const manifest = path.join(temporary, 'adopt.json'), keptFiles = fs.readdirSync(path.join(files, 'kept'));
  fs.writeFileSync(manifest, JSON.stringify({ format: 'tuldok_adoption_v1', products: [
    { reference: KEPT, files: Object.fromEntries(keptFiles.map(n => [n, path.join(files, 'kept', n)])) },
    { reference: NONE, files: { 'notes.txt': path.join(files, 'none', 'notes.txt') } }
  ] }));
  cli('adopt', folder, manifest, '--copy');
  let output = '';
  server = launch(python, ['-u', 'app.py', '--port', '0', '--data', catalog, '--project-folder', folder], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] });
  server.stdout.on('data', chunk => { output += chunk; }); server.stderr.on('data', chunk => { serverErrors += chunk; });
  const port = await until(() => { if (server.exitCode !== null) throw Error('Tuldok exited: ' + serverErrors); return output.match(/127\.0\.0\.1:(\d+)/)?.[1]; }, 'Tuldok start-up', 3000);
  origin = 'http://127.0.0.1:' + port;
  auth = authenticatedFixture(); await auth.register(origin, catalog, root);
  const products = (await api('products')).products, keptRun = products.find(p => p.reference === KEPT).run_id;
  const listed = await api('fields', { run: keptRun });
  assert.equal(listed.cases.length, 2);

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
  /** Loads the Analysis tab in a theme with the address's settings (a page of its own, not a change of hash). */
  const load = async (name, query) => {
    await theme(name);
    await send('Page.navigate', { url: 'about:blank' }); await pause(100);
    await send('Page.navigate', { url: origin + '/?theme=' + name + (query ? '&' + query : '') + '#analysis' });
    await until(() => evaluate(`document.readyState === 'complete' && !!document.getElementById('needs-btn') && !document.getElementById('needs-btn').disabled`), 'the project read', 1200);
    await until(() => evaluate(`!!document.querySelector('[data-key="ana-subject"]')`), 'the Analysis tab');
    await settled('opened ' + query);
  };
  const drawnPanels = () => until(() => evaluate(`(() => { const c = [...document.querySelectorAll('section.fld canvas.fld-cv')]; return c.length === 3 && c.every(x => Number(x.dataset.drawn) > 0); })()`), 'the three panels drawn');
  const search = () => evaluate('location.search');
  const shape = X.shape, rows0 = shape[0], cols0 = shape[1];
  const same = (a, b) => a.every((v, i) => v === b[i]);

  // ---- 1. Kept fields on fd-kept, one line on fd-none, nothing on fd-absent ------------------------------------------------
  await size(1440, 900); await load('light', 'anaBench=' + BENCH + '&anaSubject=fd-kept');
  await until(() => evaluate(`!!document.querySelector('section.fld')`), 'Kept fields'); await drawnPanels(); await settled('Kept fields');
  const s1 = await stateShown(), c0 = X.cases[0];
  assert.equal(s1.panels, 3, 'Three panels');
  assert.ok(s1.caseText.startsWith(c0.name + ' · ' + c0.split), 'The case is named from the probe with its split: ' + s1.caseText);
  assert.match(s1.facts, /6 × 5 × 4/); assert.match(s1.facts, /split validation/); assert.match(s1.facts, new RegExp('from run ' + keptRun.slice(0, 8)));
  const f1 = await figuresShown();
  for (const [k, v] of Object.entries(c0.figures)) { if (v === null) assert.equal(f1[k], null, k); else close(f1[k], v, 'figure ' + k); }
  assert.deepEqual(s1.reported, [['mean_free_same_request_pressure_relative_l2', X.reported]], 'What the run reported');
  assert.equal(await evaluate(`[...document.querySelectorAll('#main section')].map(s => s.className).join(' ')`).then(t => t.endsWith('fld')), true, 'Kept fields comes after the rest');
  const runHref = await evaluate(`document.querySelector('section.fld .fld-run').getAttribute('href')`);
  assert.equal(runHref, '#train/' + encodeURIComponent('run:' + keptRun), 'The run is linked to Train');
  await shot('light-1440-1-kept-fields');
  await choose(byKey('ana-subject'), 'fd-none'); await settled('fd-none');
  const sNone = await until(() => stateShown(), 'the one line');
  assert.ok(sNone.none && /kept no fields/.test(sNone.none), 'fd-none says its run kept no fields: ' + JSON.stringify(sNone)); assert.equal(sNone.panels, 0);
  await choose(byKey('ana-subject'), 'fd-absent'); await settled('fd-absent');
  assert.equal(await evaluate(`document.querySelector('section.fld')`), null, 'fd-absent has no section');
  check('1. fd-kept: "' + s1.caseText + '", "' + s1.facts + '", three panels, figures as the fixture computes (relative L2 ' + f1.relative_l2 + ', mean-free ' + f1.mean_free_relative_l2 + ') and the run\'s own ' + X.reported + '; fd-none: "' + sNone.none + '"; fd-absent: no section');

  // ---- 2. The pixels: where native and predicted differ, and the middle colour where they agree ---------------------------------
  await choose(byKey('ana-subject'), 'fd-kept'); await settled('fd-kept again'); await drawnPanels();
  const mid = await evaluate(MID);
  const [pn, pp, pe] = [await panel('reference', rows0, cols0), await panel('predicted', rows0, cols0), await panel('error', rows0, cols0)];
  let agreeing = 0, differing = 0;
  for (let r = 0; r < rows0; r++) for (let c = 0; c < cols0; c++) {
    const i = [r, c, 2], differs = at(c0.predicted, shape, i) !== at(c0.reference, shape, i);
    if (differs) { differing++; assert.ok(!same(pn.cells[r][c], pp.cells[r][c]), 'Native and Predicted differ at ' + i); assert.ok(!same(pe.cells[r][c], mid), 'The error is coloured at ' + i); }
    else { agreeing++; assert.deepEqual(pn.cells[r][c], pp.cells[r][c], 'Native and Predicted agree at ' + i); assert.deepEqual(pe.cells[r][c], mid, 'The error is the middle colour at ' + i); }
  }
  assert.ok(agreeing > 0 && differing > 0);
  assert.ok(pn.drawn > 1000 && pe.drawn > 1000, 'The panels are drawn');
  check('2. At z = 2: ' + differing + ' cells where the fixture differs are different in Native and Predicted and coloured in the error; ' + agreeing + ' where it agrees are the same colour and the error there is --ramp-mid ' + JSON.stringify(mid.slice(0, 3)));

  // ---- 3. Hover: the cell's position and its three values -------------------------------------------------------------------
  const hr = 4, hc = 3, hi = [hr, hc, 2];
  const px = pn.box.left + (pn.cell.x0 + (hc + 0.5) * pn.cell.sx) / pn.cell.dpr, py = pn.box.top + (pn.cell.y0 + (hr + 0.5) * pn.cell.sy) / pn.cell.dpr;
  await mouse('mouseMoved', px, py); await pause(150);
  const tip = await evaluate(`(() => { const t = document.querySelector('section.fld .fld-tip'); return { hidden: t.hidden, cell: t.dataset.cell, rows: [...t.querySelectorAll('.fld-tip-row')].map(r => [r.dataset.value, r.lastChild.textContent]), at: t.querySelector('.fld-tip-at').textContent }; })()`);
  assert.equal(tip.hidden, false, 'The tip shows');
  assert.equal(tip.cell, JSON.stringify(hi), 'The tip is of the cell under the pointer'); assert.equal(tip.at, 'x 4, y 3, z 2');
  const fmtF = v => evaluate(`window.LabCharts.fmtSci(Math.fround(${v}))`);
  const want = [['reference', await fmtF(at(c0.reference, shape, hi))], ['predicted', await fmtF(at(c0.predicted, shape, hi))], ['error', await fmtF(Math.fround(at(c0.predicted, shape, hi) - at(c0.reference, shape, hi)))]];
  assert.deepEqual(tip.rows, want, 'The three values of the cell');
  await mouse('mouseMoved', 5, 5); await pause(100);
  assert.equal(await evaluate(`document.querySelector('section.fld .fld-tip').hidden`), true, 'The tip goes when the pointer leaves');
  check('3. Hover on Native at ' + tip.at + ': ' + tip.rows.map(r => r.join(' ')).join(', ') + ', the fixture\'s values');

  // ---- 4. The slider and the axis select: one request each, a different image, drawn in place ------------------------------------
  await evaluate(`(() => { document.querySelector('[data-key="ana-bench"]').__mark = 1; document.querySelector('section.fld').__mark = 2; document.querySelector('section.fld canvas.fld-cv[data-panel="error"]').__mark = 3; document.querySelector('section.fld .fld-figures').__mark = 4; return true; })()`);
  const marks = () => evaluate(`[document.querySelector('[data-key="ana-bench"]').__mark, document.querySelector('section.fld').__mark, document.querySelector('section.fld canvas.fld-cv[data-panel="error"]').__mark, document.querySelector('#main .cases-t, #main .ana-none') ? 1 : 0]`);
  const since4 = Date.now(), before4 = await panel('reference', rows0, cols0);
  await slide(byKey('fld-slider-2'), 0); await until(() => asked('field_compare', since4).length >= 1 && !calls.size, 'the slider\'s request'); await settled('slider');
  const after4 = await panel('reference', rows0, cols0);
  assert.equal(asked('field_compare', since4).length, 1, 'One field_compare for the slider');
  assert.deepEqual(asked('field_compare', since4)[0].body.index, [3, 2, 0]);
  assert.notEqual(after4.sum, before4.sum, 'The slider changes the slice'); assert.ok(after4.times > before4.times, 'The canvas is drawn again in place');
  assert.deepEqual(await marks(), [1, 2, 3, 1], 'The rest of the tab and the section are the same elements');
  const since4b = Date.now();
  await choose(byKey('fld-axis'), '0'); await until(() => asked('field_compare', since4b).length >= 1 && !calls.size, 'the axis\'s request'); await settled('axis');
  const axis4 = await panel('reference', 5, 4);
  assert.equal(asked('field_compare', since4b).length, 1, 'One field_compare for the axis'); assert.equal(asked('field_compare', since4b)[0].body.axis, 0);
  assert.notEqual(axis4.sum, after4.sum, 'The axis changes the slice'); assert.match(axis4.label, /5 by 4 cells through y and z at x = 3/);
  assert.deepEqual(await marks(), [1, 2, 3, 1], 'Still the same elements');
  assert.equal(await evaluate(`document.activeElement.dataset.key`), 'fld-axis', 'The axis select keeps the focus');
  const f4 = await figuresShown(); for (const [k, v] of Object.entries(c0.figures)) if (v !== null) close(f4[k], v, 'figure ' + k + ' after the axis');
  check('4. The slider (z to 0) and the axis (to x): one field_compare each, the images different (' + before4.sum + ' → ' + after4.sum + ' → ' + axis4.sum + '), the canvases drawn again in place, the tab and the section the same elements, the figures unchanged');

  // ---- 5. "Remove the mean" on the constant-offset case -----------------------------------------------------------------------
  const kase1 = keptRun + ':0:1', since5 = Date.now();
  await choose(byKey('fld-case'), kase1); await settled('case 1'); await drawnPanels();
  assert.equal(asked('field_compare', since5).length, 1, 'One field_compare for the case');
  assert.deepEqual(await marks().then(m => [m[0], m[1]]), [1, 2], 'Another case is drawn in the same section');
  const s5 = await stateShown(); assert.ok(s5.caseText.startsWith('scene-b-frame-9 · test'), s5.caseText); assert.equal(s5.axis, '2', 'Another case starts on its last axis');
  const off = await panel('error', rows0, cols0);
  assert.ok(off.cells.flat().every(c => !same(c, mid)), 'The offset is coloured everywhere');
  await choose(byKey('fld-axis'), '1'); await settled('case 1 axis y');
  await slide(byKey('fld-slider-1'), 3); await settled('case 1 y = 3');
  const sinceMean = Date.now();
  await press(byKey('fld-mean')); await until(() => asked('field_compare', sinceMean).length >= 1 && !calls.size, 'the mean\'s request'); await settled('mean removed');
  assert.equal(asked('field_compare', sinceMean).length, 1, 'One field_compare for the mean'); assert.equal(asked('field_compare', sinceMean)[0].body.mean_free, true);
  const free = await panel('error', 6, 4);
  assert.ok(free.cells.flat().every(c => same(c, mid)), 'Without the mean the offset\'s error is the middle colour: ' + JSON.stringify(free.cells[0]));
  assert.equal(await evaluate(`document.querySelector('[data-key="fld-mean"]').getAttribute('aria-pressed')`), 'true');
  const f5 = await figuresShown(); close(f5.mean_free_relative_l2, 0, 'mean-free relative L2 of the offset'); close(f5.relative_l2, X.cases[1].figures.relative_l2, 'its relative L2');
  await shot('light-1440-5-mean-removed');
  check('5. The offset case: its error coloured everywhere, then "Remove the mean" (one field_compare) draws it in the middle colour; mean-free relative L2 ' + f5.mean_free_relative_l2 + ', relative L2 ' + f5.relative_l2);

  // ---- 6. A reload restores the place; a return to the window and a timer reading touch nothing --------------------------------------
  const query = (await search()).replace(/^\?/, '').split('&').filter(p => !p.startsWith('theme=')).join('&');
  const params = new URLSearchParams(query);
  assert.equal(params.get('anaCase'), kase1); assert.equal(params.get('anaAxis'), '1'); assert.equal(params.get('anaIndex'), '3,3,2'); assert.equal(params.get('anaMeanFree'), '1');
  const before6 = await stateShown(), sinceLoad = Date.now();
  await load('light', query); await drawnPanels(); await settled('reloaded');
  const after6 = await stateShown();
  assert.deepEqual(after6, before6, 'The reload restores the case, axis, position and mean option');
  assert.deepEqual(asked('field_compare', sinceLoad).map(f => f.body), [{ run: keptRun, entry: 0, case: 1, axis: 1, index: [3, 3, 2], mean_free: true }], 'The reload asks for that slice once');
  assert.ok((await panel('error', 6, 4)).cells.flat().every(c => same(c, mid)), 'and draws it as before');
  await evaluate(WATCHER);
  const rows6 = [];
  for (const cause of ['focus', 'timer']) {
    const since = Date.now();
    await evaluate(`window.__still.start(); true`);
    if (cause === 'focus') { await evaluate(`window.dispatchEvent(new Event('focus')); true`); await reading(since, WATCHED.concat(['map']), 'focus'); }
    else await reading(since, WATCHED, 'the timer', Math.round((IDLE_MS + 15000) / 100));
    const r = await evaluate(`window.__still.stop()`);
    assert.deepEqual(touched(r, ['tabs', 'main', 'aside', 'needs-panel']), [], cause + ': nothing is touched');
    assert.equal(r.flash, 0, cause + ': "Reading…" is never shown');
    assert.equal(asked('fields', since).length + asked('field_compare', since).length, 0, cause + ': nothing of the fields is asked again');
    rows6.push(cause + ': 0 nodes added, removed or changed, nothing of the fields asked');
  }
  check('6. The address kept ' + query + '; the reload drew the same case, axis, position and mean option with one field_compare; ' + rows6.join('; '));

  // ---- 7. Light and dark, 1440 and 390 wide -----------------------------------------------------------------------------------
  const seen7 = [];
  for (const [w, hgt] of [[1440, 900], [390, 844]]) for (const name of ['light', 'dark']) {
    const tag = name + '-' + w;
    await size(w, hgt); await load(name, 'anaBench=' + BENCH + '&anaSubject=fd-kept');
    await drawnPanels(); await settled(tag);
    await evaluate(`(() => { document.querySelector('section.fld').scrollIntoView({ block: 'start' }); return true; })()`); await pause(300);
    const r = await evaluate(`(() => { const m = document.getElementById('main'), f = document.querySelector('section.fld'); const cv = [...f.querySelectorAll('canvas')].map(c => { if (!c.width) return 0; const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let n = 0; for (let i = 3; i < d.length; i += 4) if (d[i]) n++; return n; }); const tops = [...f.querySelectorAll('.fld-panel')].map(p => Math.round(p.getBoundingClientRect().top)); const widths = [...f.querySelectorAll('.fld-panel')].map(p => Math.round(p.getBoundingClientRect().width)); const wide = [...m.querySelectorAll('*')].filter(e => e.getBoundingClientRect().right > m.getBoundingClientRect().right + 1 && e.getBoundingClientRect().width > 0 && !e.closest('.tv-wrap')).map(e => e.tagName + '.' + e.className).slice(0, 4); return { cv, tops, widths, page: document.documentElement.scrollWidth - innerWidth, main: m.scrollWidth - m.clientWidth, wide }; })()`);
    assert.ok(r.cv.every(n => n > 10), tag + ': no blank canvas ' + JSON.stringify(r.cv));
    assert.ok(r.page <= 0 && r.main <= 1 && !r.wide.length, tag + ': nothing overflows sideways ' + JSON.stringify(r));
    assert.ok(Math.max(...r.widths) - Math.min(...r.widths) <= 1, tag + ': the panels are of equal size ' + JSON.stringify(r.widths));
    if (w >= 1000) assert.equal(new Set(r.tops).size, 1, tag + ': side by side ' + JSON.stringify(r.tops));
    else assert.ok(r.tops[0] < r.tops[1] && r.tops[1] < r.tops[2], tag + ': stacked ' + JSON.stringify(r.tops));
    await shot(tag + '-7-kept-fields');
    seen7.push(tag + ' (' + (w >= 1000 ? 'side by side' : 'stacked') + ')');
  }
  await size(1440, 900);
  check('7. No blank canvas and nothing overflowing sideways: ' + seen7.join(', ') + (shots ? '; screenshots in ' + shots : ''));

  // ---- Nothing failed -----------------------------------------------------------------------------------------------------
  assert.deepEqual(errors, [], 'Script errors');
  assert.deepEqual(failures, [], 'Failed requests');
  check('No script error, no failed request');
  fs.writeFileSync(path.join(report, 'receipt.json'), JSON.stringify({ status: 'pass', folder, checks }, null, 2) + '\n');
  console.log('Receipt in ' + report);
})().catch(async error => {
  process.exitCode = 1;
  console.error(error); if (serverErrors) console.error('Server:', serverErrors.slice(-4000));
  console.error('Script errors:', JSON.stringify(errors)); console.error('Failed requests:', JSON.stringify(failures));
  try { if (evaluate) { await shot('failure'); console.error('Main:', (await evaluate('document.getElementById("main").innerText')).slice(0, 2500)); } } catch (_) { /* the page is gone */ }
  fs.writeFileSync(path.join(report, 'failure.json'), JSON.stringify({ status: 'failed', error: String(error && error.stack || error), checks, errors, failures }, null, 2) + '\n');
}).finally(async () => {
  try { session?.close(); } catch (_) { /* closed */ }
  for (const child of children.reverse()) await stop(child);
  if (owned) try { dropOwned(...owned); } catch (error) { console.error('Dropping the disposable schemas failed:', error.message); process.exitCode = 1; }
  try { execFileSync('chmod', ['-R', 'u+w', temporary]); } catch (_) { /* nothing was made read-only */ }   // finished runs leave their directories read-only
  fs.rmSync(temporary, { recursive: true, force: true });
});
