'use strict';
// A model's weights in its drawer (docs/plans/definition-first-projects/spec-d2.md sections 4 and 6, slice D2b) in a
// headless browser, the owner signed in, no GPU. Tuldok runs with --project-folder on a copy of the minimal fixture,
// in a Git repository of its own, with three more recipes of earlier work whose products are adopted (the command
// line's adopt) from files tests/project_weights_browser_fixture.py writes with the standard library:
// recipes/wt-parent (weights.npz), recipes/wt-child, derived from it (weights.npz and initial-weights.npz), and
// recipes/wt-pickle (model.pt only). The fixture prints what it knows: layers, parameters, statistics, the change
// of each layer against the initial weights and against the parent.
//   1. The derived model's drawer shows Weights with the fixture's parameter count and its layers in file order,
//      each with the fixture's parameters and the shape of its first tensor; the third model's shows the reason
//      and nothing else.
//   2. A layer's distribution is asked for (array_summary, 32 bins) when its row comes on screen and not before,
//      and once: the page's requests are counted while the drawer scrolls.
//   3. Opening a tensor shows its statistics (equal to the fixture's), its larger distribution and its values: a
//      two-axis tensor as one image, the five-axis kernel as tiles whose range is the fixture's; a slider and the
//      paging change the tiles (and their range is the fixture's at the new place).
//   4. Comparing with the starting weights and with the parent asks weights_compare once each and shows the
//      fixture's change per layer ("from zero" for the layer that started at zero, the marks of a reshaped tensor,
//      one only here and one only in the other); "difference" draws a different image from "this", on the
//      fixture's range of the difference.
//   5. With the drawer open, comparing and a tensor opened, the window regaining focus and one reading on the timer
//      add, remove and change no node and keep every scroll.
//   6. Light and dark at 1440 by 900 and 1000 by 800: no canvas of the block blank, nothing overflowing the drawer
//      sideways; screenshots of the layers, an opened two-axis tensor, the kernel as tiles, the comparison and the
//      unreadable file (with --shots <dir>, written there too).
// It fails on any script error and any failed request.
//   node tests/browser_project_workspace_weights.cjs [--shots <dir>]
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
const CHILD = 'recipes/wt-child', PARENT = 'recipes/wt-parent', PICKLE = 'recipes/wt-pickle';
const RECIPES = {
  'wt-parent': { title: 'Weights parent', labels: { short: 'WP', trained_at: '2026-10-01' }, change: 'architecture' },
  'wt-child': { title: 'Weights child', labels: { short: 'WC', trained_at: '2026-10-05' }, change: 'refinement', derived_from: PARENT },
  'wt-pickle': { title: 'Weights in a pickle', labels: { short: 'WK', trained_at: '2026-10-07' }, change: 'component' }
};
const MARGIN = 40;   // weights.js asks for a row's distribution this near the drawer's view

const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'tuldok-weights-browser-'));
const report = qaDirectory(root, 'project-workspace-weights');
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
  await until(() => evaluate(`(() => { const reading = e => [...e.querySelectorAll('.note')].some(n => n.textContent === 'Reading…'); return !reading(document.getElementById('main')) && !reading(document.getElementById('aside')) && !document.querySelector('#aside [aria-busy]'); })()`) .then(ok => ok && !calls.size), 'settled: ' + label);
  await pause(200);
}
async function hash(value) { await evaluate(`location.hash = ${JSON.stringify('#' + value)}`); await settled('#' + value); await pause(200); await settled('#' + value); }
const byKey = key => `[data-key=${JSON.stringify(key)}]`;
async function centre(selector) {
  for (let moved = 0; ; moved++) {
    const at = await until(() => evaluate(`(() => { const e = [...document.querySelectorAll(${JSON.stringify(selector)})].find(e => e.offsetParent !== null); if (!e) return null; e.scrollIntoView({ block: 'nearest', inline: 'nearest' }); const r = e.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2, hit = document.elementFromPoint(x, y); return { x, y, ok: !!hit && (hit === e || e.contains(hit)) }; })()`), 'shown: ' + selector, 100);
    if (at.ok) return at;
    if (moved > 20) throw Error('The target of ' + selector + ' is never under its point');
    await pause(100);
  }
}
async function mouse(type, x, y, buttons = 0) { await send('Input.dispatchMouseEvent', { type, x, y, button: type === 'mouseMoved' ? (buttons ? 'left' : 'none') : 'left', buttons, clickCount: type === 'mouseMoved' ? 0 : 1 }); }
async function press(selector) { const { x, y } = await centre(selector); await mouse('mouseMoved', x, y); await mouse('mousePressed', x, y, 1); await mouse('mouseReleased', x, y); }
async function key(name, code) { for (const type of ['rawKeyDown', 'keyUp']) await send('Input.dispatchKeyEvent', { type, key: name, code: name, windowsVirtualKeyCode: code, nativeVirtualKeyCode: code }); }
/** Chooses an option of a select by the keyboard's way of changing it (the change event the page listens to). */
async function choose(selector, value) { await evaluate(`(() => { const s = document.querySelector(${JSON.stringify(selector)}); s.focus(); s.value = ${JSON.stringify(value)}; s.dispatchEvent(new Event('change', { bubbles: true })); return true; })()`); }
async function frames() { await evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))'); }
async function shot(name) {
  await frames();
  const png = Buffer.from((await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })).data, 'base64');
  fs.writeFileSync(path.join(report, name + '.png'), png); if (shots) fs.writeFileSync(path.join(shots, name + '.png'), png);
}
/** What a canvas shows: how many pixels are drawn, how many colours, and a sum that changes when the drawing does. */
const PIXELS = `c => { if (!c || !c.width) return null; const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let drawn = 0, sum = 0; const colours = new Set(); for (let i = 0; i < d.length; i += 4) if (d[i + 3]) { drawn++; sum = (sum + (i / 4 + 1) * (d[i] * 3 + d[i + 1] * 5 + d[i + 2] * 7)) % 2147483647; if (colours.size < 64) colours.add(d[i] + ',' + d[i + 1] + ',' + d[i + 2]); } return { drawn, colours: colours.size, sum, label: c.getAttribute('aria-label') || '' }; }`;
const pixels = selector => evaluate(`(${PIXELS})(document.querySelector(${JSON.stringify(selector)}))`);
const tilesNow = () => evaluate(`(() => { const p = document.querySelector('#aside .wts-pics'); return { mode: p.dataset.mode, first: Number(p.dataset.first), index: JSON.parse(p.dataset.index), across: p.dataset.across, tiles: p.querySelectorAll('canvas').length, captions: [...p.querySelectorAll('figcaption')].map(c => c.textContent), sums: [...p.querySelectorAll('canvas')].map(c => (${PIXELS})(c)), range: document.querySelector('#aside .wts-range').textContent }; })()`);
const close = (a, b, label, tol = 1e-6) => assert.ok(Math.abs(a - b) <= tol * Math.max(1, Math.abs(b)), label + ': ' + a + ' is not ' + b);

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
  const where = (e, top) => { const p = []; while (e && e !== top) { p.unshift(e.tagName.toLowerCase() + ':' + [...e.parentElement.children].indexOf(e)); e = e.parentElement; } return p.join('>'); };
  function scrolls() {
    const out = {};
    for (const top of [el('main'), el('drawer')]) { out[top.id] = [top.scrollLeft, top.scrollTop].map(Math.round); for (const e of top.querySelectorAll('*')) if (e.scrollLeft || e.scrollTop) out[top.id + ' ' + where(e, top)] = [Math.round(e.scrollLeft), Math.round(e.scrollTop)]; }
    return out;
  }
  return {
    start() { counts = {}; for (const id of ids) { counts[id] = { added: 0, removed: 0, attrs: 0, text: 0, readAt: 0, what: [] }; for (const e of el(id).querySelectorAll('*')) e.__seen = 1; } flash = 0; clearInterval(timer); timer = setInterval(() => { if ((el('main').textContent + el('aside').textContent).includes('Reading…')) flash++; }, 50); },
    stop() { clearInterval(timer); const fresh = {}; for (const id of ids) fresh[id] = [...el(id).querySelectorAll('*')].filter(e => !e.__seen).length; const r = { counts, flash, fresh, scrolls: scrolls() }; counts = null; return r; },
    scrolls
  };
})(); true`;
const touched = (r, ids) => ids.filter(id => { const c = r.counts[id]; return c.added || c.removed || c.attrs || c.text || r.fresh[id]; }).map(id => id + ' ' + JSON.stringify(r.counts[id]) + ' new ' + r.fresh[id]);

/** The lowest and highest of tiles of the fixture's five-axis kernel (C order), across axis 0 from first, drawn on axes 3 and 4, at index on axes 1 and 2. */
function tileRange(values, shape, first, count, index, minus = null) {
  let lo = Infinity, hi = -Infinity;
  const at = i => [i[0] * shape[1] * shape[2] * shape[3] * shape[4] + i[1] * shape[2] * shape[3] * shape[4] + i[2] * shape[3] * shape[4] + i[3] * shape[4] + i[4]];
  for (let t = first; t < first + count; t++) for (let r = 0; r < shape[3]; r++) for (let c = 0; c < shape[4]; c++) {
    const k = at([t, index[1], index[2], r, c])[0], v = minus ? Math.fround(Math.fround(values[k]) - Math.fround(minus[k])) : values[k];
    lo = Math.min(lo, v); hi = Math.max(hi, v);
  }
  return [lo, hi];
}

(async () => {
  // ---- The fixture: minimal + three recipes of earlier work, in Git; their products adopted ------------------------------------
  fs.cpSync(path.join(root, 'tests', 'fixtures', 'tuldok_project', 'minimal'), path.join(temporary, 'fixture'), { recursive: true });
  const folder = path.join(temporary, 'fixture', 'project');
  for (const [name, r] of Object.entries(RECIPES)) fs.writeFileSync(path.join(folder, 'recipes', name + '.json'), JSON.stringify(Object.assign({ format: 'tuldok_definition_v1', kind: 'recipe', title: r.title, description: 'Weights for the browser check of a model\'s weights.', labels: r.labels,
    earlier_work: { rebuild: 'no', reason: 'Written by the browser check of the weights; only its weights remain.' }, model: 'models/stepper', group: 'steppers', change: r.change }, r.derived_from ? { derived_from: r.derived_from } : {}), null, 2) + '\n');
  const git = ['-c', 'user.name=Tuldok Test', '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false', '-c', 'init.defaultBranch=main', '-C', path.join(temporary, 'fixture')];
  execFileSync('git', [...git, 'init', '-q']); execFileSync('git', [...git, 'add', '-A']); execFileSync('git', [...git, 'commit', '-q', '-m', 'The fixture.']);
  const files = path.join(temporary, 'weights');
  const X = JSON.parse(execFileSync(python, [path.join(root, 'tests', 'project_weights_browser_fixture.py'), '--out', files]).toString());
  const home = path.join(temporary, 'home'), catalog = path.join(temporary, 'catalog'); fs.mkdirSync(home);
  const env = { ...process.env, TULDOK_PROJECT_HOME: home, TULDOK_SETTINGS: path.join(temporary, 'settings.json') };
  owned = [folder, catalog]; dropOwned(folder, catalog);
  const cli = (...args) => execFileSync(python, ['-m', 'tuldok_project', ...args], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] }).toString();
  const manifest = path.join(temporary, 'adopt.json');
  fs.writeFileSync(manifest, JSON.stringify({ format: 'tuldok_adoption_v1', products: [
    { reference: PARENT, files: { 'weights.npz': path.join(files, 'parent', 'weights.npz') } },
    { reference: CHILD, files: { 'weights.npz': path.join(files, 'child', 'weights.npz'), 'initial-weights.npz': path.join(files, 'child', 'initial-weights.npz') } },
    { reference: PICKLE, files: { 'model.pt': path.join(files, 'pickle', 'model.pt') } }
  ] }));
  cli('adopt', folder, manifest, '--copy');
  let output = '';
  server = launch(python, ['-u', 'app.py', '--port', '0', '--data', catalog, '--project-folder', folder], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] });
  server.stdout.on('data', chunk => { output += chunk; }); server.stderr.on('data', chunk => { serverErrors += chunk; });
  const port = await until(() => { if (server.exitCode !== null) throw Error('Tuldok exited: ' + serverErrors); return output.match(/127\.0\.0\.1:(\d+)/)?.[1]; }, 'Tuldok start-up', 3000);
  origin = 'http://127.0.0.1:' + port;
  auth = authenticatedFixture(); await auth.register(origin, catalog, root);
  const products = (await api('products')).products, runOf = ref => products.find(p => p.reference === ref).run_id;
  const pickled = (await api('weights', { run: runOf(PICKLE) })).files[0];
  assert.equal(pickled.readable, false);

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
    await send('Page.navigate', { url: 'about:blank' }); await pause(100);   // a page of its own, not a change of hash
    await send('Page.navigate', { url: origin + '/?theme=' + name + '#' + place });
    await until(() => evaluate(`document.readyState === 'complete' && !!document.getElementById('needs-btn') && !document.getElementById('needs-btn').disabled`), 'the project read', 1200);
    await settled('opened ' + place);
  };
  const block = () => evaluate(`(() => { const w = document.querySelector('#aside .wts'); if (!w) return null; return { size: w.querySelector('.wts-size').textContent, path: (w.querySelector('.wts-path') || {}).textContent || null, reason: (w.querySelector('.wts-reason') || {}).textContent || null, table: !!w.querySelector('table'), compare: !!w.querySelector('[data-key="wts-compare"]'),
    rows: [...w.querySelectorAll('tr.wts-row')].map(r => ({ layer: r.dataset.layer, parameters: Number(r.children[1].textContent.replace(/\\D/g, '')), shape: r.querySelector('.wts-shape').textContent, marks: [...r.querySelectorAll('.wts-mark')].map(m => m.textContent), change: r.querySelector('.wts-chg') ? r.querySelector('.wts-chg').dataset.change : null, figure: r.querySelector('.wts-fig') ? r.querySelector('.wts-fig').textContent : null })) }; })()`);
  const stats = () => evaluate(`Object.fromEntries([...document.querySelectorAll('#aside .wts-stats dd')].map(d => [d.dataset.stat, d.dataset.value]))`);
  const sparks = () => evaluate(`(() => { const d = document.getElementById('drawer'), top = d.getBoundingClientRect(); return [...document.querySelectorAll('#aside canvas.wts-spark')].map(c => { const r = c.getBoundingClientRect(); return { array: c.dataset.array, near: r.bottom > top.top - ${MARGIN} && r.top < top.bottom + ${MARGIN}, drawn: c.dataset.drawn === '1' }; }); })()`);
  const summaries32 = (since = 0) => asked('array_summary', since, b => b.bins === 32).map(f => f.body.array);

  // ---- 1 and 2. The derived model's drawer: the file, the layers in file order; distributions asked for as rows come on screen --------
  await size(1440, 640); await load('light', 'map');
  const since2 = Date.now();
  await hash(model(CHILD));
  await until(() => evaluate(`!!document.querySelector('#aside .wts table')`), 'the Weights block');
  await settled('the child\'s drawer');
  const b1 = await block();
  assert.equal(b1.path, 'weights.npz');
  assert.match(b1.size, new RegExp(X.parameters.toLocaleString('en-GB') + ' parameters · ' + X.layers.length + ' layers, 8 tensors'), 'The parameter count is the fixture\'s');
  assert.deepEqual(b1.rows.map(r => r.layer), X.layers.map(l => l.name), 'The layers in file order');
  assert.deepEqual(b1.rows.map(r => r.parameters), X.layers.map(l => l.parameters), 'Each layer\'s parameters');
  assert.deepEqual(b1.rows.map(r => r.shape.split(' · ')[0]), X.layers.map(l => l.tensors[0].shape.join(' × ')), 'The shape of each layer\'s first tensor');
  // 2. Opened below the fold, no row has asked for its distribution; scrolled so that the first rows come on screen, only those ask.
  await pause(400);
  let seen = await sparks();
  assert.ok(seen.every(s => !s.near), 'At 1440 × 640 the table opens below the drawer\'s view: ' + JSON.stringify(seen));
  assert.deepEqual(summaries32(since2), [], 'No row off screen asked for its distribution');
  await evaluate(`(() => { const d = document.getElementById('drawer'), r = document.querySelectorAll('#aside tr.wts-row')[1].getBoundingClientRect(); d.scrollTop += r.bottom - d.getBoundingClientRect().bottom + 4; return true; })()`);
  await until(async () => (await sparks()).filter(s => s.near).every(s => s.drawn), 'the rows on screen drawn'); await pause(400);
  seen = await sparks();
  const off = seen.filter(s => !s.near).map(s => s.array);
  assert.ok(off.length > 0 && off.length < seen.length, 'Some rows are on screen and some below: ' + JSON.stringify(seen));
  assert.deepEqual(summaries32(since2).sort(), seen.filter(s => s.near).map(s => s.array).sort(), 'Only the rows on screen asked for their distribution');
  const before2 = summaries32(since2).length;
  await evaluate(`(() => { const d = document.getElementById('drawer'); d.scrollTop = d.scrollHeight; return true; })()`);
  await until(async () => (await sparks()).every(s => s.drawn), 'every row drawn once on screen');
  await evaluate(`(() => { const d = document.getElementById('drawer'); d.scrollTop = 0; return true; })()`); await pause(300);
  await evaluate(`(() => { const d = document.getElementById('drawer'); d.scrollTop = d.scrollHeight; return true; })()`); await pause(300);
  const all2 = summaries32(since2);
  assert.deepEqual(all2.slice().sort(), X.layers.map(l => l.tensors[0].name).sort(), 'Each row asked once, for its first tensor');
  const spark = await pixels('#aside canvas.wts-spark');
  assert.ok(spark.drawn > 20, 'A distribution is drawn: ' + JSON.stringify(spark));
  // The third model: the reason and nothing else; the parent: no comparison offered.
  await hash(model(PICKLE));
  await until(() => evaluate(`!!document.querySelector('#aside .wts')`), 'the pickle\'s Weights');
  const b3 = await block();
  assert.equal(b3.reason, pickled.reason, 'The reason is the server\'s'); assert.equal(b3.path, 'model.pt'); assert.equal(b3.table, false); assert.equal(b3.compare, false);
  assert.equal(await evaluate(`[...document.querySelector('#aside .wts').children].map(e => e.className || e.tagName).join(' ')`), 'H3 wts-head empty wts-reason', 'Nothing else is shown');
  await hash(model(PARENT)); await until(() => evaluate(`!!document.querySelector('#aside .wts table')`), 'the parent\'s Weights');
  const bp = await block(); assert.equal(bp.compare, false, 'The parent has nothing to compare with');
  assert.match(bp.size, new RegExp(X.parent_parameters.toLocaleString('en-GB') + ' parameters'));
  await hash('map/' + encodeURIComponent('recipes/early-fit'));
  assert.equal(await evaluate(`!!document.querySelector('#aside .wts-box') && document.querySelector('#aside .wts-box').hidden`), true, 'A model without a product has no Weights block');
  check('1. ' + CHILD + ': "' + b1.size + '", layers ' + b1.rows.map(r => r.layer + ' (' + r.parameters + ', ' + r.shape + ')').join(', ') + '; ' + PICKLE + ' shows only "' + b3.reason + '"; the parent offers no comparison; early-fit has no block');
  check('2. At 1440 × 640 the drawer first asked for ' + before2 + ' distributions, those of its rows on screen, not for ' + off.join(', ') + '; scrolled down and back, each of the ' + all2.length + ' rows had asked once');

  // ---- 3. A tensor opened: a two-axis tensor, then the five-axis kernel as tiles; the slider and the pages ------------------------
  await size(1440, 900); await hash(model(CHILD));
  await press(byKey('wts-layer-head')); await settled('head opened');
  const hs = await stats(), xh = X.stats['head.weight'];
  assert.deepEqual(JSON.parse(hs.range), [xh.min, xh.max], 'head.weight\'s range'); close(Number(hs.mean), xh.mean, 'head.weight\'s mean'); close(Number(hs.std), xh.std, 'head.weight\'s spread');
  assert.equal(Number(hs.zeros), xh.zeros); assert.equal(Number(hs.count), xh.count);
  const tensors = await evaluate(`[...document.querySelectorAll('#aside .wts-tensors button')].map(b => b.textContent + ':' + b.getAttribute('aria-pressed'))`);
  assert.deepEqual(tensors, ['weight:true', 'bias:false'], 'A layer of two tensors offers both, the first opened');
  const head = await pixels('#aside .wts-pics.one canvas');
  assert.ok(head.drawn > 200 && head.colours > 4, 'The two-axis tensor is drawn as one image: ' + JSON.stringify(head));
  assert.match(head.label, /^3 by 16 values of head\.weight \(this file\), from -1\.5 to 2$/);
  const hist = await pixels('#aside canvas.wts-hist'); assert.ok(hist.drawn > 100, 'The larger distribution is drawn');
  await press(byKey('wts-tensor-head.bias')); await settled('head.bias');
  assert.match((await pixels('#aside .wts-pics.one canvas')).label, /^The 3 values of head\.bias/);
  await press(byKey('wts-layer-conv')); await settled('conv opened');
  const cs = await stats(), xc = X.stats['conv.weight'];
  assert.deepEqual(JSON.parse(cs.range), [xc.min, xc.max], 'conv.weight\'s range'); close(Number(cs.mean), xc.mean, 'conv.weight\'s mean'); close(Number(cs.std), xc.std, 'conv.weight\'s spread');
  assert.equal(Number(cs.zeros), xc.zeros); assert.equal(Number(cs.count), 7200);
  const shape = [20, 3, 4, 5, 6], t0 = await tilesNow();
  assert.equal(t0.tiles, 16); assert.deepEqual(t0.captions, Array.from({ length: 16 }, (_, i) => String(i))); assert.deepEqual(t0.index, [0, 1, 2, 2, 3]);
  assert.ok(t0.sums.every(s => s.drawn > 50), 'Every tile is drawn'); assert.ok(new Set(t0.sums.map(s => s.sum)).size > 12, 'The tiles differ');
  const r0 = tileRange(X.conv_weight, shape, 0, 16, [0, 1, 2]);
  const fmtR = async (word, r) => word + ': from ' + await evaluate(`window.LabCharts.fmtSci(${r[0]})`) + ' to ' + await evaluate(`window.LabCharts.fmtSci(${r[1]})`);
  assert.ok(t0.range.startsWith(await fmtR('This file', r0)), 'The tiles\' range is the fixture\'s: ' + t0.range);
  // The slider on axis 1 (by the keyboard), then the pages.
  await evaluate(`document.querySelector('#aside [data-key="wts-axis-slider-1"]').focus(); true`);
  await key('ArrowRight', 39);
  await until(async () => JSON.stringify((await tilesNow()).index) === '[0,2,2,2,3]', 'the slider moves the tiles'); await settled('slider');
  const t1 = await tilesNow(), r1 = tileRange(X.conv_weight, shape, 0, 16, [0, 2, 2]);
  assert.notEqual(t1.sums[0].sum, t0.sums[0].sum, 'The slider changes the tiles'); assert.ok(t1.range.startsWith(await fmtR('This file', r1)), 'At axis 1 = 2 the range is the fixture\'s: ' + t1.range);
  assert.equal(await evaluate(`document.activeElement.dataset.key`), 'wts-axis-slider-1', 'The slider keeps the focus');
  await press(byKey('wts-next')); await settled('next tiles');
  const t2 = await tilesNow(), r2 = tileRange(X.conv_weight, shape, 16, 4, [0, 2, 2]);
  assert.equal(t2.first, 16); assert.equal(t2.tiles, 4); assert.deepEqual(t2.captions, ['16', '17', '18', '19']);
  assert.ok(t2.range.startsWith(await fmtR('This file', r2)), 'The second page\'s range is the fixture\'s: ' + t2.range);
  assert.equal(await evaluate(`document.querySelector('#aside .wts-pager').textContent.includes('Tiles 17–20 of 20 along axis 0')`), true);
  await press(byKey('wts-prev')); await settled('first tiles');
  await choose('#aside [data-key="wts-across"]', '2'); await settled('across axis 2');
  const t3 = await tilesNow();
  assert.equal(t3.across, '2'); assert.equal(t3.tiles, 4, 'Across axis 2 there are 4 tiles'); assert.deepEqual(await evaluate(`[...document.querySelectorAll('#aside .wts-ctl input[type=range]')].map(r => r.dataset.axis)`), ['0', '1'], 'Sliders for axes 0 and 1');
  await choose('#aside [data-key="wts-across"]', '0'); await settled('across axis 0');
  check('3. head.weight: range ' + hs.range + ', mean ' + hs.mean + ', spread ' + hs.std + ', zeros ' + hs.zeros + ' as the fixture\'s, drawn as one 3 × 16 image; conv.weight: range ' + cs.range + ', mean ' + cs.mean + ', zeros ' + cs.zeros + ', 16 tiles ("' + t0.range.split(',')[0] + '"); axis 1 to 2 by the keyboard: "' + t1.range.split(',')[0] + '"; Next: tiles 16–19, "' + t2.range.split(',')[0] + '"; across axis 2: 4 tiles');

  // ---- 4. Comparing: with the starting weights, with the parent; this, the other, the difference ------------------------------
  const since4 = Date.now();
  await choose('#aside [data-key="wts-compare"]', 'start'); await settled('compare with the start');
  assert.equal(asked('weights_compare', since4).length, 1, 'One weights_compare for the choice');
  const b4 = await block();
  for (const r of b4.rows) {
    const want = X.against_initial.relative[r.layer];
    if (want === null) { assert.equal(r.change, 'zero', r.layer + ' started at zero'); continue; }
    close(Number(r.change), want, r.layer + '\'s change against its initial weights', 1e-9);
  }
  assert.ok(b4.rows.find(r => r.layer === 'scale').figure === null && (await evaluate(`document.querySelector('#aside tr[data-layer="scale"] .wts-zero').textContent`)) === 'from zero');
  const widths = await evaluate(`Object.fromEntries([...document.querySelectorAll('#aside tr.wts-row')].filter(r => r.querySelector('.wts-cbar i')).map(r => [r.dataset.layer, parseFloat(r.querySelector('.wts-cbar i').style.width)]))`);
  assert.equal(Math.max(...Object.values(widths)), 100, 'The largest change fills its bar');
  close(widths['encoder.0'], 100 * X.against_initial.relative['encoder.0'] / X.against_initial.relative.conv, 'encoder.0\'s bar is scaled to the largest', 1e-3);
  // Sorted by change, the largest first.
  await press(byKey('wts-sort-change')); await settled('sorted by change');
  const sorted = (await block()).rows.map(r => r.layer);
  assert.deepEqual(sorted, ['scale'].concat(Object.entries(X.against_initial.relative).filter(([, v]) => v !== null).sort((a, b) => b[1] - a[1]).map(([k]) => k)), 'Sorted by change');
  await press(byKey('wts-sort-file')); await settled('file order');
  // The kernel still open: this, then the difference.
  const this4 = await tilesNow();
  assert.equal(this4.mode, 'this');
  await press(byKey('wts-mode-difference')); await settled('difference');
  const diff4 = await tilesNow(), rd = tileRange(X.conv_weight, shape, diff4.first, diff4.tiles, diff4.index, X.conv_weight_initial);
  assert.equal(diff4.mode, 'difference');
  assert.ok(diff4.sums.every(s => s.drawn > 50), 'The difference is drawn');
  assert.notEqual(diff4.sums[0].sum, this4.sums[0].sum, '"Difference" draws a different image from "this"');
  assert.ok(diff4.range.startsWith(await fmtR('This minus the other', rd)), 'The difference\'s range is the fixture\'s: ' + diff4.range);
  await press(byKey('wts-mode-other')); await settled('the other');
  const other4 = await tilesNow(), ro = tileRange(X.conv_weight_initial, shape, other4.first, other4.tiles, other4.index);
  assert.ok(other4.range.startsWith(await fmtR('The other file', ro)), 'The other\'s range is the initial weights\': ' + other4.range);
  await shot('light-1440-compare-difference-check');
  await press(byKey('wts-mode-difference')); await settled('difference again');
  const since4b = Date.now();
  const parentKey = await evaluate(`[...document.querySelectorAll('#aside [data-key="wts-compare"] option')].find(o => o.value.startsWith('model')).value`);
  await choose('#aside [data-key="wts-compare"]', parentKey); await settled('compare with the parent');
  assert.equal(asked('weights_compare', since4b).length, 1, 'One weights_compare for the parent');
  const b5 = await block();
  for (const r of b5.rows) {
    const want = X.against_parent.relative[r.layer];
    if (want === undefined) { assert.equal(r.change, 'none', r.layer + ' is not compared'); continue; }
    close(Number(r.change), want, r.layer + '\'s change against the parent', 1e-9);
  }
  assert.deepEqual(b5.rows.find(r => r.layer === 'head').marks, ['weight reshaped']); assert.deepEqual(b5.rows.find(r => r.layer === 'extra').marks, ['only here']);
  assert.match(await evaluate(`document.querySelector('#aside .wts-there').textContent`), /Only in the other: old\.weight\./);
  check('4. Against initial-weights.npz (one weights_compare): ' + b4.rows.map(r => r.layer + ' ' + (r.figure || r.change)).join(', ') + ', as the fixture computes; sorted by change: ' + sorted.join(', ') + '; the difference drawn apart from this, "' + diff4.range.split(',')[0] + '"; against the parent (one more): ' + b5.rows.map(r => r.layer + ' ' + (r.figure || r.change) + (r.marks.length ? ' [' + r.marks.join(', ') + ']' : '')).join(', ') + ', old.weight only in the other');

  // ---- 5. Nothing changed: the window regains focus, the timer reads ---------------------------------------------------------
  await choose('#aside [data-key="wts-compare"]', 'start'); await settled('compare with the start again');
  await press(byKey('wts-mode-difference')); await settled('difference');
  await evaluate(`(() => { const d = document.getElementById('drawer'); d.scrollTop = Math.min(d.scrollHeight, 500); return true; })()`); await pause(400); await settled('scrolled');
  await evaluate(WATCHER);
  const rows5 = [];
  for (const cause of ['focus', 'timer']) {
    const before = await evaluate(`window.__still.scrolls()`), since = Date.now();
    await evaluate(`window.__still.start(); true`);
    if (cause === 'focus') { await evaluate(`window.dispatchEvent(new Event('focus')); true`); await reading(since, WATCHED.concat(['map']), 'focus'); }
    else await reading(since, WATCHED, 'the timer', Math.round((IDLE_MS + 15000) / 100));
    const r = await evaluate(`window.__still.stop()`);
    assert.deepEqual(touched(r, ['tabs', 'strip', 'main', 'aside', 'needs-panel']), [], cause + ': nothing is touched');
    assert.equal(r.flash, 0, cause + ': "Reading…" is never shown'); assert.deepEqual(r.scrolls, before, cause + ': every scroll stays');
    assert.equal(asked('weights_compare', since).length + asked('array_summary', since).length + asked('array_tiles', since).length + asked('weights', since).length, 0, cause + ': nothing of the weights is asked again');
    rows5.push(cause + ': 0 nodes added or removed, 0 changed, nothing of the weights asked');
  }
  // Something changed elsewhere (a definition added to the project folder, which status reports): the drawer is drawn again in place, the block keeping its comparison, the tensor opened and its mode.
  const before5 = await evaluate(`({ scroll: document.getElementById('drawer').scrollTop, compare: document.querySelector('#aside [data-key="wts-compare"]').value, mode: document.querySelector('#aside .wts-pics').dataset.mode, open: document.querySelector('#aside [aria-expanded="true"]').dataset.key })`);
  const tilesBefore = await tilesNow(), since5 = Date.now();
  await evaluate(`window.__still.start(); true`);
  fs.writeFileSync(path.join(folder, 'datasets', 'added-elsewhere.json'), JSON.stringify(Object.assign(JSON.parse(fs.readFileSync(path.join(folder, 'datasets', 'waves.json'), 'utf8')), { title: 'Added elsewhere' }), null, 2) + '\n');
  await evaluate(`window.dispatchEvent(new Event('focus')); true`); await reading(since5, WATCHED.concat(['map']), 'a file added');
  await until(() => evaluate(`!!document.querySelector('#aside .wts-pics canvas')`), 'the block drawn again'); await settled('drawn again');
  const r5 = await evaluate(`window.__still.stop()`);
  const after5 = await evaluate(`({ scroll: document.getElementById('drawer').scrollTop, compare: document.querySelector('#aside [data-key="wts-compare"]').value, mode: document.querySelector('#aside .wts-pics').dataset.mode, open: document.querySelector('#aside [aria-expanded="true"]').dataset.key })`);
  const tilesAfter = await tilesNow();
  assert.ok(r5.fresh.aside > 0, 'The drawer was drawn again: ' + JSON.stringify(r5.counts.aside));
  assert.equal(r5.flash, 0, '"Reading…" is never shown when the drawer is drawn again');
  assert.deepEqual(after5, before5, 'The scroll, the comparison, the layer opened and the mode are kept');
  assert.deepEqual(tilesAfter.sums.map(s => s.sum), tilesBefore.sums.map(s => s.sum), 'The tiles are drawn as before');
  assert.equal(asked('array_summary', since5).length, 0, 'No distribution is asked for again');
  rows5.push('a file added elsewhere: the drawer drawn again in place (' + r5.fresh.aside + ' new nodes, ' + asked('weights_compare', since5).length + ' weights_compare asked again), its scroll, comparison, opened layer and mode kept, no "Reading…"');
  check('5. With ' + CHILD + '\'s drawer open, compared with its starting weights and the kernel\'s difference shown: ' + rows5.join('; '));

  // ---- 6. Light and dark, two sizes: nothing blank, nothing overflowing the drawer; the screenshots -----------------------------------
  const seen6 = [];
  const scrollTo = async selector => { await evaluate(`(() => { const e = document.querySelector(${JSON.stringify(selector)}); e.scrollIntoView({ block: 'start' }); return true; })()`); await pause(250); await settled('scrolled to ' + selector); };
  const sound = async tag => {
    const r = await evaluate(`(() => { const w = document.querySelector('#aside .wts'), d = document.getElementById('drawer'); const blank = [...w.querySelectorAll('canvas')].filter(c => c.getBoundingClientRect().height > 0).map(c => { if (!c.width) return 0; const x = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let n = 0; for (let i = 3; i < x.length; i += 4) if (x[i]) n++; return n; }); const wide = [...w.querySelectorAll('*')].filter(e => e.getBoundingClientRect().right > d.getBoundingClientRect().right - 1 && e.getBoundingClientRect().width > 0).map(e => e.tagName + '.' + e.className); return { blank, over: d.scrollWidth - d.clientWidth, page: document.documentElement.scrollWidth - innerWidth, wide: wide.slice(0, 4) }; })()`);
    assert.ok(r.blank.every(n => n > 20), tag + ': no blank canvas ' + JSON.stringify(r.blank));
    assert.ok(r.over <= 1 && r.page <= 0, tag + ': nothing overflows the drawer sideways ' + JSON.stringify(r));
    seen6.push(tag + ' (' + r.blank.length + ' canvases)');
  };
  for (const [w, hgt] of [[1440, 900], [1000, 800]]) for (const name of ['light', 'dark']) {
    const tag = name + '-' + w;
    await size(w, hgt); await load(name, model(CHILD));
    await until(() => evaluate(`!!document.querySelector('#aside .wts table')`), 'the Weights block');
    await scrollTo('#aside .wts'); await until(async () => (await sparks()).filter(s => s.near).every(s => s.drawn), 'the rows drawn');
    await sound(tag + ' layers'); await shot(tag + '-1-layers');
    await press(byKey('wts-layer-head')); await settled('head');
    await scrollTo('#aside .wts-tensor'); await sound(tag + ' two-axis'); await shot(tag + '-2-tensor-2d');
    await press(byKey('wts-layer-conv')); await settled('conv');
    await scrollTo('#aside .wts-tensor'); await sound(tag + ' kernel'); await shot(tag + '-3-kernel-tiles');
    await evaluate(`(() => { const e = document.querySelector('#aside .wts-pics'); e.scrollIntoView({ block: 'start' }); return true; })()`); await pause(200); await shot(tag + '-3b-kernel-tiles-end');
    await choose('#aside [data-key="wts-compare"]', 'start'); await settled('compare');
    await scrollTo('#aside .wts'); await sound(tag + ' compare'); await shot(tag + '-4-compare-start');
    await evaluate(`(() => { document.querySelector('#aside tr[data-layer="scale"]').scrollIntoView({ block: 'end' }); return true; })()`); await pause(200); await shot(tag + '-4b-compare-from-zero');
    await press(byKey('wts-mode-difference')); await settled('difference');
    await scrollTo('#aside .wts-tensor'); await sound(tag + ' difference'); await shot(tag + '-5-compare-difference');
    await hash(model(PICKLE)); await until(() => evaluate(`!!document.querySelector('#aside .wts-reason')`), 'the reason');
    await scrollTo('#aside .wts'); await sound(tag + ' unreadable'); await shot(tag + '-6-unreadable');
  }
  await size(1440, 900);
  check('6. No canvas blank and nothing overflowing the drawer sideways in light and dark at 1440 × 900 and 1000 × 800: ' + seen6.length + ' views' + (shots ? '; screenshots in ' + shots : ''));

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
  try { execFileSync('chmod', ['-R', 'u+w', temporary]); } catch (_) { /* nothing was made read-only */ }   // finished runs leave their directories read-only
  fs.rmSync(temporary, { recursive: true, force: true });
});
