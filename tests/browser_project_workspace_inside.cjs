'use strict';
// Looking inside a product (docs/plans/definition-first-projects/spec-d1.md sections 7 and 9, slice D1b) in a
// headless browser, the owner signed in, no GPU. Tuldok runs with --project-folder on a copy of the minimal fixture
// with the buildable fixture's definitions beside it, in a Git repository of its own, and one more dataset,
// datasets/specimens, whose command (tests/project_inside_browser_fixture.py, standard library only) writes a
// product of 57 records: at least one of every kind (text, image, audio, point cloud, mesh, array, file), a zip
// archive holding .npz arrays, and an array Tuldok refuses to read. The command line builds it before Tuldok starts.
//   1. Data shows "Look inside" on that dataset and not on one without a product; the dataset opens to 48 tiles,
//      the counts by kind are the fixture's, the pager reaches the rest, a kind filter narrows the grid.
//   2. Each kind's viewer shows its record: the text equals the file's; the image is decoded at its true size; the
//      sound plays, with the right length and a drawn waveform; a point cloud and a mesh draw a canvas that is not
//      blank and changes when dragged (and a mesh above 60,000 triangles says it is drawn as points); the array's
//      value under the pointer equals the fixture's at that place, and its slider moves the slice; the histogram
//      draws; the array Tuldok refuses shows the server's sentence and the grid stays usable; left and right
//      arrows move the selection.
//   3. "Files" lists the tree, opens the archive and an array inside it, whose value under the pointer is the
//      fixture's.
//   4. With the dataset open and a record selected, the window regaining focus and one reading on the timer add,
//      remove and change no node and keep every scroll (the counting of browser_project_workspace_still.cjs). When
//      something changes elsewhere (an agent asks for a build), the view is drawn again in place: same page, same
//      selection, same scroll, no "Reading…".
//   5. Light and dark: no viewer is blank in either, at 1440 by 900; screenshots of the view and every viewer in
//      both themes at 1440 by 900 and 1000 by 800 (with --shots <dir>, written there too).
// Step 6 of the spec (the existing workspace checks pass unchanged) is the running of those checks.
// With --lab-root nothing is asserted (spec-d1 section 9: a fresh database has no products for the lab).
// It fails on any script error, and on any failed request but the refusals the check asks for.
//   node tests/browser_project_workspace_inside.cjs [--shots <dir>] [--lab-root <folder>]
const assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const { spawn, execFileSync } = require('node:child_process'), { once } = require('node:events');
const { authenticatedFixture } = require('./auth_helpers.cjs'), { waitForDebugger } = require('./browser_startup.cjs'), { cdpSession } = require('./browser_cdp_session.cjs'), { qaDirectory } = require('./qa_artifacts.cjs');

const root = path.resolve(__dirname, '..');
const argv = process.argv.slice(2), option = name => { const i = argv.indexOf(name); return i >= 0 ? argv[i + 1] : null; };
if (argv.includes('--lab-root')) { console.log('Nothing is asserted with --lab-root (spec-d1 section 9): a fresh database has no products for the lab.'); process.exit(0); }
assert.ok(process.env.TULDOK_DATABASE_URL, 'TULDOK_DATABASE_URL must name a disposable PostgreSQL cluster');
const venv = path.join(root, '.venv', 'bin');
if (fs.existsSync(path.join(venv, 'python'))) process.env.PATH = venv + path.delimiter + process.env.PATH;   // auth_helpers runs python3
const python = fs.existsSync(path.join(venv, 'python')) ? path.join(venv, 'python') : 'python3';
const IDLE_MS = 15000;   // the page's reading while nothing builds (app.js)
const WATCHED = ['summary', 'status', 'build_requests', 'environments', 'runs'];
const REF = 'datasets/specimens', OPENED = 'data/' + encodeURIComponent('inside:' + REF);
const KINDS = { text: 45, image: 1, audio: 1, pointcloud: 2, mesh: 3, array: 3, file: 2 };   // what the fixture's command writes
const TOTAL = Object.values(KINDS).reduce((a, b) => a + b, 0);

const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'tuldok-inside-browser-'));
const report = qaDirectory(root, 'project-workspace-inside');
const shots = option('--shots') ? path.resolve(option('--shots')) : null; if (shots) fs.mkdirSync(shots, { recursive: true });
const children = [], checks = [], errors = [], failures = [], refusedOk = [];
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
/** An operation as the owner (bearer: as that agent credential instead); refused: the refusal is answered instead of failing. */
async function api(name, body = {}, refused = false, bearer = null) {
  const headers = { 'Content-Type': 'application/json', 'Tuldok-Operation-Contract': await contract(name) };
  const response = bearer ? await globalThis.fetch(origin + '/api/project/' + name, { method: 'POST', headers: { ...headers, Authorization: 'Bearer ' + bearer }, body: JSON.stringify(body) })
    : await auth.fetch(origin + '/api/project/' + name, { method: 'POST', headers, body: JSON.stringify(body) });
  const value = await response.json(); if (!refused) assert.equal(response.status, 200, name + ': ' + JSON.stringify(value)); return value;
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
/** Waits until nothing reads: no "Reading…", the main area and the viewer not busy. */
async function settled(label) {
  await until(() => evaluate(`(() => { const reading = e => [...e.querySelectorAll('.note')].some(n => n.textContent === 'Reading…'); const v = document.querySelector('#main .viewer'); return !reading(document.getElementById('main')) && !reading(document.getElementById('aside')) && !document.getElementById('main').hasAttribute('aria-busy') && !(v && v.hasAttribute('aria-busy')); })()`), 'settled: ' + label);
  await pause(150);
}
async function hash(value) { await evaluate(`location.hash = ${JSON.stringify('#' + value)}`); await settled('#' + value); await pause(200); await settled('#' + value); }
const byKey = key => `[data-key=${JSON.stringify(key)}]`;
let moved = 0;   // presses whose target was not under its point when measured (the layout moved between); counted, then measured again
async function centre(selector) {
  for (;;) {
    const at = await until(() => evaluate(`(() => { const e = [...document.querySelectorAll(${JSON.stringify(selector)})].find(e => e.offsetParent !== null); if (!e) return null; e.scrollIntoView({ block: 'nearest', inline: 'nearest' }); const r = e.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2, hit = document.elementFromPoint(x, y); return { x, y, ok: !!hit && (hit === e || e.contains(hit)) }; })()`), 'shown: ' + selector, 100);
    if (at.ok) return at;
    if (++moved > 20) throw Error('The target of ' + selector + ' is never under its point');
    await pause(100);
  }
}
async function mouse(type, x, y, buttons = 0) { await send('Input.dispatchMouseEvent', { type, x, y, button: type === 'mouseMoved' ? (buttons ? 'left' : 'none') : 'left', buttons, clickCount: type === 'mouseMoved' ? 0 : 1 }); }
async function press(selector) { const { x, y } = await centre(selector); await mouse('mouseMoved', x, y); await mouse('mousePressed', x, y, 1); await mouse('mouseReleased', x, y); }
async function key(name, code) { for (const type of ['rawKeyDown', 'keyUp']) await send('Input.dispatchKeyEvent', { type, key: name, code: name, windowsVirtualKeyCode: code, nativeVirtualKeyCode: code }); }
async function shot(name) {
  await evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))');
  const png = Buffer.from((await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })).data, 'base64');
  fs.writeFileSync(path.join(report, name + '.png'), png); if (shots) fs.writeFileSync(path.join(shots, name + '.png'), png);
}
/** What a canvas shows: how many pixels are drawn, how many colours, and a sum that changes when the drawing does. */
const pixels = selector => evaluate(`(() => { const c = document.querySelector(${JSON.stringify(selector)}); if (!c || !c.width) return null; const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let drawn = 0, sum = 0; const colours = new Set(); for (let i = 0; i < d.length; i += 4) if (d[i + 3]) { drawn++; sum = (sum + (i / 4 + 1) * (d[i] * 3 + d[i + 1] * 5 + d[i + 2] * 7)) % 2147483647; if (colours.size < 64) colours.add(d[i] + ',' + d[i + 1] + ',' + d[i + 2]); } return { drawn, colours: colours.size, sum, label: c.getAttribute('aria-label') || '' }; })()`);
/** Selects a record by its tile and waits for its viewer. */
async function open(id) {
  await press(`#main .rec${byKey('rec-' + id)}`);
  await until(() => evaluate(`(() => { const v = document.querySelector('#main .viewer'); const t = v && v.querySelector('.iv-head h3'); return !!t && t.textContent === ${JSON.stringify(id)} && !v.hasAttribute('aria-busy'); })()`), 'the viewer of ' + id);
  await settled(id);
}
/** The value under the pointer at a cell (row, column) of the slice drawn: moves the mouse there and reads the probe. */
async function probe(row, col) {
  const at = await evaluate(`(() => { const c = document.querySelector('#main .viewer canvas.iv-heat'); c.scrollIntoView({ block: 'nearest' }); const [rect, grid] = c.dataset.cells.split(';'), [x, y, w, h] = rect.split(',').map(Number), [rows, cols] = grid.split('x').map(Number); const r = c.getBoundingClientRect(), kx = r.width / c.width, ky = r.height / c.height; return { x: r.left + (x + (${col} + 0.5) * w / cols) * kx, y: r.top + (y + (${row} + 0.5) * h / rows) * ky }; })()`);
  await mouse('mouseMoved', at.x, at.y);
  return until(() => evaluate(`(() => { const p = document.querySelector('#main .viewer .iv-probe'); return p && p.dataset.index ? { index: JSON.parse(p.dataset.index), value: Number(p.dataset.value), text: p.textContent } : null; })()`), 'a value under the pointer');
}
async function drag(selector) {
  const { x, y } = await centre(selector);
  await mouse('mouseMoved', x, y); await mouse('mousePressed', x, y, 1);
  for (let i = 1; i <= 6; i++) await mouse('mouseMoved', x + i * 14, y + i * 5, 1);
  await mouse('mouseReleased', x + 84, y + 30);
  await evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))');
}

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
    const main = el('main'), out = { main: [main.scrollLeft, main.scrollTop].map(Math.round) };
    for (const e of main.querySelectorAll('*')) if (e.scrollLeft || e.scrollTop) out['main ' + where(e, main)] = [Math.round(e.scrollLeft), Math.round(e.scrollTop)];
    return out;
  }
  return {
    start() { counts = {}; for (const id of ids) { counts[id] = { added: 0, removed: 0, attrs: 0, text: 0, readAt: 0, what: [] }; for (const e of el(id).querySelectorAll('*')) e.__seen = 1; } flash = 0; clearInterval(timer); timer = setInterval(() => { if ((el('main').textContent + el('aside').textContent).includes('Reading…')) flash++; }, 50); },
    stop() { clearInterval(timer); const fresh = {}; for (const id of ids) fresh[id] = [...el(id).querySelectorAll('*')].filter(e => !e.__seen).length; const r = { counts, flash, fresh, scrolls: scrolls() }; counts = null; return r; },
    scrolls
  };
})(); true`;
const touched = (r, ids) => ids.filter(id => { const c = r.counts[id]; return c.added || c.removed || c.attrs || c.text || r.fresh[id]; }).map(id => id + ' ' + JSON.stringify(r.counts[id]) + ' new ' + r.fresh[id]);

(async () => {
  // ---- The fixture: minimal + buildable + datasets/specimens, in Git; the specimens built ------------------------------
  fs.cpSync(path.join(root, 'tests', 'fixtures', 'tuldok_project', 'minimal'), path.join(temporary, 'fixture'), { recursive: true });
  const folder = path.join(temporary, 'fixture', 'project'), code = path.join(temporary, 'fixture', 'code'), buildable = path.join(root, 'tests', 'fixtures', 'tuldok_project', 'buildable');
  for (const kind of ['environments', 'datasets', 'recipes', 'benchmarks', 'charts']) for (const name of fs.readdirSync(path.join(buildable, 'project', kind))) fs.copyFileSync(path.join(buildable, 'project', kind, name), path.join(folder, kind, name));
  for (const name of fs.readdirSync(path.join(buildable, 'code'))) fs.cpSync(path.join(buildable, 'code', name), path.join(code, name), { recursive: true });
  fs.copyFileSync(path.join(root, 'tests', 'project_inside_browser_fixture.py'), path.join(code, 'make_specimens.py'));
  fs.writeFileSync(path.join(folder, 'datasets', 'specimens.json'), JSON.stringify({ format: 'tuldok_definition_v1', kind: 'dataset', title: 'Specimens of every kind',
    description: 'One record of every kind and more, for looking inside.', run: { command: ['python', 'make_specimens.py', '--out', '{output}'], environment: 'environments/test-python', sources: ['make_specimens.py'] } }, null, 2) + '\n');
  const git = ['-c', 'user.name=Tuldok Test', '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false', '-c', 'init.defaultBranch=main', '-C', path.join(temporary, 'fixture')];
  execFileSync('git', [...git, 'init', '-q']); execFileSync('git', [...git, 'add', '-A']); execFileSync('git', [...git, 'commit', '-q', '-m', 'The fixture.']);
  const home = path.join(temporary, 'home'), catalog = path.join(temporary, 'catalog'); fs.mkdirSync(home);
  const env = { ...process.env, TULDOK_PROJECT_HOME: home, TULDOK_SETTINGS: path.join(temporary, 'settings.json') };
  owned = [folder, catalog]; dropOwned(folder, catalog);
  const cli = (...args) => execFileSync(python, ['-m', 'tuldok_project', ...args], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] }).toString();
  cli('connect', folder, 'test-python', python);
  cli('build', folder, REF, '--yes');
  let output = '';
  server = launch(python, ['-u', 'app.py', '--port', '0', '--data', catalog, '--project-folder', folder], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] });
  server.stdout.on('data', chunk => { output += chunk; }); server.stderr.on('data', chunk => { serverErrors += chunk; });
  const port = await until(() => { if (server.exitCode !== null) throw Error('Tuldok exited: ' + serverErrors); return output.match(/127\.0\.0\.1:(\d+)/)?.[1]; }, 'Tuldok start-up', 3000);
  origin = 'http://127.0.0.1:' + port;
  auth = authenticatedFixture(); await auth.register(origin, catalog, root);
  const product = (await api('products', { reference: REF })).products[0], run = product.run_id, out = product.directory;
  const datasets = (await api('definitions', { kind: 'dataset' })).definitions.filter(d => !d.removed).map(d => d.reference);
  const withProduct = new Set((await api('products')).products.map(p => p.reference));
  const without = datasets.filter(d => !withProduct.has(d));
  assert.ok(without.length > 0, 'The fixture has a dataset without a product');

  const browser = launch(findBrowser(), ['--headless', '--no-sandbox', '--disable-gpu', '--no-first-run', '--hide-scrollbars', '--autoplay-policy=no-user-gesture-required', '--remote-debugging-port=0', '--window-size=1440,900', '--user-data-dir=' + path.join(temporary, 'browser'), 'about:blank'], { stdio: 'ignore', env: { ...process.env, XDG_CONFIG_HOME: temporary, XDG_CACHE_HOME: temporary } });
  const debugPort = await waitForDebugger(browser, path.join(temporary, 'browser', 'DevToolsActivePort'));
  const target = (await (await fetch('http://127.0.0.1:' + debugPort + '/json')).json()).find(item => item.type === 'page');
  socket = new WebSocket(target.webSocketDebuggerUrl); await once(socket, 'open');
  session = cdpSession(socket, { timeoutMs: 60000, onEvent: event => {
    network(event);
    if (event.method === 'Runtime.exceptionThrown') errors.push(event.params.exceptionDetails.exception?.description || event.params.exceptionDetails.text);
    if (event.method === 'Runtime.consoleAPICalled' && event.params.type === 'error') errors.push(event.params.args.map(a => a.value ?? a.description).join(' '));
    if (event.method === 'Log.entryAdded' && event.params.entry.level === 'error' && !/\/api\/project\/array_slice/.test(event.params.entry.url || '')) errors.push(event.params.entry.text + ' ' + (event.params.entry.url || ''));
    if (event.method === 'Network.loadingFailed' && !event.params.canceled) failures.push({ id: event.params.requestId, error: event.params.errorText });
    if (event.method === 'Network.responseReceived' && event.params.response.status >= 400) {
      // The array Tuldok refuses (arrays/complex.npy) is asked for by its tile and its viewer: those refusals are expected.
      if (event.params.response.status === 409 && /\/api\/project\/array_slice$/.test(event.params.response.url)) refusedOk.push(event.params.response.url);
      else failures.push({ url: event.params.response.url, status: event.params.response.status });
    }
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
    await send('Page.navigate', { url: 'about:blank' }); await pause(100);   // a page of its own, not a change of hash
    await send('Page.navigate', { url: origin + '/?theme=' + name + '#' + place });
    await until(() => evaluate(`document.readyState === 'complete' && !!document.getElementById('needs-btn') && !document.getElementById('needs-btn').disabled`), 'the project read', 1200);
    await settled('opened ' + place);
  };
  await load('light', 'data');
  // For a failure's report: when the main area's scroll went back to 0, and what it showed then.
  await evaluate(`(() => { const m = document.getElementById('main'); window.__resets = []; let last = 0; m.addEventListener('scroll', () => { if (last > 50 && m.scrollTop === 0) window.__resets.push('from ' + last + ', height ' + m.scrollHeight + '/' + m.clientHeight + ' at ' + Math.round(performance.now()) + ' ms, ' + ((document.querySelector('#main .inside-list .sect .sum') || {}).textContent || '')); last = m.scrollTop; }); return true; })()`);

  // ---- 1. The cards, the dataset opened, the pager and a filter ----------------------------------------------------
  const looks = await evaluate(`[...document.querySelectorAll('#main .ds-item')].map(i => ({ ref: i.querySelector('.ds-card').dataset.ref, look: !!i.querySelector('[data-key^="inside-"]') }))`);
  assert.ok(looks.find(x => x.ref === REF).look, '"Look inside" on the dataset with a product');
  for (const ref of without) assert.equal(looks.find(x => x.ref === ref).look, false, 'No "Look inside" on ' + ref + ', which has no product');
  await shot('light-1440-data-cards');
  await press(byKey('inside-' + REF));
  await until(() => evaluate(`location.hash === ${JSON.stringify('#' + OPENED)}`), 'the dataset opened'); await settled('the dataset opened');
  const grid = await evaluate(`({ tiles: document.querySelectorAll('#main .rec').length, sum: document.querySelector('#main .inside-list .sect .sum').textContent, chips: Object.fromEntries([...document.querySelectorAll('#main [data-key^="inside-kind-"]')].map(b => [b.dataset.key.slice('inside-kind-'.length), Number(b.textContent.split('·')[1].replace(/\\D/g, ''))])), title: document.querySelector('#main .ds-head h2').textContent, meta: document.querySelector('#main .ds-head .meta').textContent })`);
  assert.equal(grid.tiles, 48, '48 tiles on the first page');
  assert.equal(grid.sum, '1–48 of ' + TOTAL);
  assert.deepEqual(grid.chips, Object.assign({ all: TOTAL }, KINDS), 'The counts by kind are the fixture\'s');
  assert.equal(grid.title, 'Specimens of every kind'); assert.match(grid.meta, new RegExp('run ' + run.slice(0, 8)));
  // Every tile carries its record's id; tiles never jump: each is a square picture and a line.
  const ids = await evaluate(`[...document.querySelectorAll('#main .rec')].map(t => t.dataset.id)`);
  const listed = (await api('records', { run, limit: 48 })).records.map(r => r.id);
  assert.deepEqual(ids, listed, 'The tiles are the first page of records, in order');
  await press(byKey('inside-next'));
  await until(() => evaluate(`document.querySelector('#main .inside-list .sect .sum').textContent.startsWith('49')`), 'page 2 drawn'); await settled('page 2');
  const second = await evaluate(`({ tiles: document.querySelectorAll('#main .rec').length, sum: document.querySelector('#main .inside-list .sect .sum').textContent, ids: [...document.querySelectorAll('#main .rec')].map(t => t.dataset.id) })`);
  assert.equal(second.tiles, TOTAL - 48); assert.equal(second.sum, '49–' + TOTAL + ' of ' + TOTAL);
  assert.deepEqual(second.ids, (await api('records', { run, offset: 48, limit: 48 })).records.map(r => r.id), 'The pager reaches the rest');
  await press(byKey('inside-prev')); await settled('page 1');
  await press(byKey('inside-kind-mesh')); await settled('meshes');
  const meshes = await evaluate(`[...document.querySelectorAll('#main .rec')].map(t => t.dataset.kind + ' ' + t.dataset.id)`);
  assert.deepEqual(meshes, ['mesh meshes/cube.obj', 'mesh meshes/sphere.stl', 'mesh meshes/terrain.ply'], 'The kind filter narrows the grid');
  await press(byKey('inside-kind-all')); await settled('all');
  assert.equal(await evaluate(`document.querySelectorAll('#main .rec').length`), 48);
  check('1. "Look inside" on ' + REF + ' and on none of ' + without.join(', ') + '; opened at #' + OPENED + ' to 48 tiles of ' + TOTAL + ' with the counts ' + JSON.stringify(grid.chips) + '; Next showed ' + second.tiles + ' more (' + second.sum + '); Mesh narrowed the grid to ' + meshes.length);

  // ---- 2. Each kind's viewer -------------------------------------------------------------------------------------------
  const note = 'texts/note-03.txt', expected = fs.readFileSync(path.join(out, note), 'utf8');
  await open(note);
  const text = await evaluate(`({ text: document.querySelector('#main .viewer .iv-text').textContent, line: document.querySelector('#main .viewer .iv > p.small.muted').textContent })`);
  assert.equal(text.text, expected, 'The text shown is the file\'s');
  // Left and right arrows move the selection (the focus on a tile).
  await evaluate(`document.querySelector('#main .rec[aria-pressed="true"]').focus(); true`);
  await key('ArrowRight', 39);
  await until(() => evaluate(`document.querySelector('#main .rec[aria-pressed="true"]').dataset.id === 'texts/note-04.txt' && document.activeElement.dataset.id === 'texts/note-04.txt' && document.querySelector('#main .viewer .iv-head h3').textContent === 'texts/note-04.txt'`), 'the right arrow selects the next record');
  await key('ArrowLeft', 37);
  await until(() => evaluate(`document.querySelector('#main .viewer .iv-head h3').textContent === ${JSON.stringify(note)}`), 'the left arrow selects it back');
  await settled('arrows');

  await open('images/gradient.png');
  const image = await until(() => evaluate(`(() => { const i = document.querySelector('#main .viewer .iv-img img'); return i && i.complete && i.naturalWidth ? { w: i.naturalWidth, h: i.naturalHeight, alt: i.alt, src: i.getAttribute('src'), size: i.closest('.iv').querySelector(':scope > p.small').textContent } : null; })()`), 'the image decoded');
  const imageRecord = (await api('record', { run, id: 'images/gradient.png' })).record;
  assert.deepEqual([image.w, image.h], [37, 23], 'The image is decoded at its true size');
  assert.equal(image.src, imageRecord.url, 'The image\'s src is the url the record operation gives');
  await press('#main .viewer .iv-img'); assert.ok(await evaluate(`document.querySelector('#main .viewer .iv-img').classList.contains('actual')`), 'A press shows the actual size');
  await press('#main .viewer .iv-img');

  await open('sounds/tone.wav');
  const sound = await until(() => evaluate(`(() => { const a = document.querySelector('#main .viewer audio'); return a && a.readyState >= 1 && Number.isFinite(a.duration) ? { duration: a.duration, src: a.getAttribute('src'), error: a.error && a.error.code } : null; })()`), 'the sound\'s metadata');
  assert.ok(Math.abs(sound.duration - 1.5) < 0.01, 'The sound lasts 1.5 s: ' + sound.duration);
  assert.equal(sound.src, (await api('record', { run, id: 'sounds/tone.wav' })).record.url);
  const played = await evaluate(`(async () => { const a = document.querySelector('#main .viewer audio'); a.muted = true; await a.play(); await new Promise(r => setTimeout(r, 400)); const t = a.currentTime; a.pause(); a.currentTime = 0; return t; })()`);
  assert.ok(played > 0, 'The sound plays: ' + played);
  const wave = await pixels('#main .viewer canvas.iv-wave');
  assert.ok(wave && wave.drawn > 200 && wave.colours >= 2, 'The waveform is drawn: ' + JSON.stringify(wave));

  const turned = {};
  for (const id of ['clouds/helix.ply', 'meshes/sphere.stl', 'meshes/cube.obj']) {
    await open(id);
    const before = await pixels('#main .viewer canvas.iv-3d');
    assert.ok(before && before.drawn > 500 && before.colours >= 2, id + ' is drawn: ' + JSON.stringify(before));
    await drag('#main .viewer canvas.iv-3d');
    const after = await pixels('#main .viewer canvas.iv-3d');
    assert.notEqual(after.sum, before.sum, id + ' changes when dragged');
    await press(byKey('iv-reset')); await evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))');
    assert.equal((await pixels('#main .viewer canvas.iv-3d')).sum, before.sum, id + ': Reset view draws it as at first');
    turned[id] = before.label.split('.')[0] + ' (' + before.drawn + ' pixels, ' + after.drawn + ' after a drag)';
  }
  await open('meshes/terrain.ply');
  const terrain = await evaluate(`({ line: document.querySelector('#main .viewer .iv > p.small.muted').textContent, label: document.querySelector('#main .viewer canvas.iv-3d').getAttribute('aria-label') })`);
  assert.match(terrain.line, /61,250 triangles · above 60,000 triangles the vertices are drawn as points/); assert.match(terrain.label, /drawn as its 30,976 vertices as points/);
  assert.ok((await pixels('#main .viewer canvas.iv-3d')).drawn > 500, 'The large mesh is drawn as points');

  await open('arrays/field.npy');
  const f = ([i, j, k]) => i * 10000 + j * 100 + k;
  const p1 = await probe(7, 11);
  assert.deepEqual(p1.index, [3, 7, 11], 'The middle slice along axes 1 and 2'); assert.equal(p1.value, f(p1.index), 'The value under the pointer is the fixture\'s');
  const vol = await pixels('#main .viewer canvas.iv-vol');
  assert.ok(vol && vol.drawn > 500 && vol.colours > 4, 'The stacked slices are drawn: ' + JSON.stringify(vol));
  await evaluate(`document.querySelector('#main .viewer [data-key="iv-axis-slider-0"]').focus(); true`);
  await key('ArrowRight', 39);
  await until(() => evaluate(`document.querySelector('#main .viewer canvas.iv-heat').dataset.index === '[4,6,8]'`), 'the slider moves the slice');
  const p2 = await probe(2, 5);
  assert.deepEqual(p2.index, [4, 2, 5]); assert.equal(p2.value, f(p2.index), 'After the slider the value is the fixture\'s at the new place');
  const vol1 = await pixels('#main .viewer canvas.iv-vol');
  assert.notEqual(vol1.sum, vol.sum, 'The stacked slices outline the new slice');
  await press(byKey('iv-hist'));
  await until(() => evaluate(`!!document.querySelector('#main .viewer canvas.iv-histc')`), 'the histogram');
  const hist = await pixels('#main .viewer canvas.iv-histc'); assert.ok(hist.drawn > 100, 'The histogram is drawn');
  const mean = await evaluate(`[...document.querySelectorAll('#main .viewer .iv-hist dt')].find(d => d.textContent === 'Mean').nextElementSibling.textContent`);
  await open('arrays/pair.npz');
  const pair = await probe(3, 4);
  assert.deepEqual(pair.index, [3, 4]); assert.equal(pair.value, Math.fround(3 - 4 / 10), 'The npz\'s array shown first is velocity, with the fixture\'s values');

  await open('arrays/complex.npy');
  const refusal = await evaluate(`document.querySelector('#main .viewer .refusal p').textContent`);
  const answered = await api('array_slice', { run, path: 'arrays/complex.npy', most: 256 }, true);
  assert.equal(answered.code, 'unsupported'); assert.equal(refusal, answered.error, 'The refusal is the server\'s sentence');
  assert.ok(await evaluate(`document.querySelector('#main .rec[data-id="arrays/complex.npy"]').classList.contains('refused')`), 'Its tile shows it is refused');
  await open('misc/blob.bin');
  assert.match(await evaluate(`document.querySelector('#main .viewer .iv .note').textContent`), /listed, never opened/);
  await open('arrays/field.npy');   // the grid stays usable after a refusal
  check('2. Viewers: the text of ' + note + ' equals the file (' + text.line + '); the arrows moved the selection; the image decoded at ' + image.w + ' × ' + image.h + ' from the record\'s url; the sound lasts ' + sound.duration + ' s and played to ' + played.toFixed(2) + ' s, its waveform drawn; ' + Object.values(turned).join('; ') + ', each changed when dragged and came back with Reset view; meshes/terrain.ply: "' + terrain.line + '"; arrays/field.npy read ' + JSON.stringify(p1.index) + ' = ' + p1.value + ', then after the slider ' + JSON.stringify(p2.index) + ' = ' + p2.value + ', its stacked slices and histogram (mean ' + mean + ') drawn; pair.npz showed velocity ' + JSON.stringify(pair.index) + ' = ' + pair.value + '; arrays/complex.npy showed "' + refusal + '"');

  // ---- 3. Files: the tree, the archive, an array inside it -----------------------------------------------------------
  await press(byKey('inside-mode-files')); await settled('files');
  const top = await evaluate(`[...document.querySelectorAll('#main .tree-entry')].map(b => b.dataset.path + ':' + b.dataset.type)`);
  assert.deepEqual(top, (await api('inside', { run })).entries.map(e => e.path + ':' + e.type), 'Files lists the product\'s top');
  await press(byKey('entry-bundles')); await settled('bundles');
  await press(byKey('entry-bundles/training-view.zip')); await settled('the archive');
  const inArchive = await evaluate(`[...document.querySelectorAll('#main .tree-entry')].map(b => b.dataset.path + ':' + b.dataset.type)`);
  assert.deepEqual(inArchive, ['bundles/training-view.zip!samples:directory', 'bundles/training-view.zip!readme.txt:file'], 'The archive opens to its members');
  await press(byKey('entry-bundles/training-view.zip!samples')); await settled('samples');
  await press(byKey('entry-bundles/training-view.zip!samples/s1.npz')); await settled('s1.npz');
  const crumbs = await evaluate(`document.querySelector('#main .crumbs').textContent`);
  await press(byKey('entry-bundles/training-view.zip!samples/s1.npz#target'));
  await until(() => evaluate(`!!document.querySelector('#main .viewer canvas.iv-heat') && !document.querySelector('#main .viewer').hasAttribute('aria-busy')`), 'the array inside the archive'); await settled('target');
  const inner = await probe(5, 7);
  assert.deepEqual(inner.index, [5, 7]); assert.equal(inner.value, 1000 + 5 * 10 + 7, 'The value inside the archive is the fixture\'s');
  await press(byKey('crumb-bundles/training-view.zip')); await settled('back up');
  await press(byKey('entry-bundles/training-view.zip!readme.txt')); await settled('readme');
  const readme = await evaluate(`document.querySelector('#main .viewer .iv .note').textContent`);
  check('3. Files listed ' + top.length + ' entries at the top; the archive opened to ' + inArchive.length + ' members; "' + crumbs.replace(/\s+/g, ' ') + '" listed target, whose value at ' + JSON.stringify(inner.index) + ' is ' + inner.value + '; a text inside the archive says: "' + readme + '"');

  // ---- 4. Nothing changed: the window regains focus, the timer reads -------------------------------------------------
  await press(byKey('inside-mode-records')); await settled('records');
  await open('clouds/helix.ply');
  await until(() => evaluate(`[...document.querySelectorAll('#main .rec[data-lazy]')].every(t => { const r = t.getBoundingClientRect(); return r.top > innerHeight || r.bottom < 0 || !t.querySelector('svg.glyph:not(.refused)'); })`), 'the tiles in view filled');
  await pause(300);
  await evaluate(WATCHER);
  const rows = [];
  for (const cause of ['focus', 'timer']) {
    const before = await evaluate(`window.__still.scrolls()`), since = Date.now();
    await evaluate(`window.__still.start(); true`);
    if (cause === 'focus') { await evaluate(`window.dispatchEvent(new Event('focus')); true`); await reading(since, WATCHED.concat(['map']), 'focus'); }
    else await reading(since, WATCHED, 'the timer', Math.round((IDLE_MS + 15000) / 100));
    const r = await evaluate(`window.__still.stop()`);
    assert.deepEqual(touched(r, ['tabs', 'strip', 'main', 'aside', 'needs-panel']), [], cause + ': nothing is touched');
    assert.equal(r.flash, 0, cause + ': "Reading…" is never shown'); assert.deepEqual(r.scrolls, before, cause + ': every scroll stays');
    rows.push(cause + ': 0 nodes added or removed, 0 changed' + (r.counts.strip.readAt ? ' ("Read at" ticked)' : ''));
  }
  check('4. With ' + REF + ' open and clouds/helix.ply selected: ' + rows.join('; '));
  // Something changed elsewhere (an agent asks for a build, which awaits approval): the view is drawn again in place, its page and selection kept.
  await press(byKey('inside-next')); await settled('page 2');
  const picked = second.ids[3]; await open(picked);
  const before4 = await evaluate(`({ sum: document.querySelector('#main .inside-list .sect .sum').textContent, scroll: document.getElementById('main').scrollTop })`);
  const since4 = Date.now(); await evaluate(`window.__still.start(); true`);
  const asked = await api('request_build', { targets: ['recipes/fit-b'] }, false, await credential('A second session', ['inspect', 'execute']));
  assert.equal(asked.state, 'awaiting-approval');
  await evaluate(`window.dispatchEvent(new Event('focus')); true`); await reading(since4, WATCHED.concat(['map', 'records', 'record']), 'a request elsewhere');
  const r4 = await evaluate(`window.__still.stop()`);
  const after4 = await evaluate(`({ sum: document.querySelector('#main .inside-list .sect .sum').textContent, scroll: document.getElementById('main').scrollTop, pressed: document.querySelector('#main .rec[aria-pressed="true"]').dataset.id, viewer: document.querySelector('#main .viewer .iv-head h3').textContent })`);
  assert.ok(r4.fresh.main > 0, 'The view was drawn again: ' + JSON.stringify(r4.counts.main));
  assert.equal(r4.flash, 0, '"Reading…" is never shown when the view is drawn again');
  assert.deepEqual([after4.sum, after4.scroll, after4.pressed, after4.viewer], [before4.sum, before4.scroll, picked, picked], 'The page, the scroll and the selection are kept');
  check('4. An agent asked for a build elsewhere: the opened view was read and drawn again in place (' + r4.fresh.main + ' new nodes), still at ' + after4.sum + ' with ' + picked + ' selected, no "Reading…"');

  // ---- 5. Light and dark, two sizes: nothing blank; the screenshots ---------------------------------------------------------
  const VIEWERS = [['text', 'texts/note-03.txt'], ['image', 'images/gradient.png'], ['audio', 'sounds/tone.wav'], ['pointcloud', 'clouds/helix.ply'], ['mesh', 'meshes/sphere.stl'], ['mesh-points', 'meshes/terrain.ply'], ['array', 'arrays/field.npy'], ['refused', 'arrays/complex.npy'], ['file', 'misc/blob.bin']];
  const seen = [];
  for (const [w, hgt] of [[1440, 900], [1000, 800]]) for (const name of ['light', 'dark']) {
    await size(w, hgt); await load(name, OPENED);
    const tag = name + '-' + w;
    await shot(tag + '-dataset');
    for (const [kind, id] of VIEWERS) {
      await open(id);
      if (kind === 'array') { await press(byKey('iv-hist')); await until(() => evaluate(`!!document.querySelector('#main .viewer canvas.iv-histc')`), 'the histogram'); await probe(7, 11); }
      const blank = await evaluate(`(() => { const v = document.querySelector('#main .viewer .iv'); const cs = [...v.querySelectorAll('canvas')].map(c => { if (!c.width) return 0; const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let n = 0; for (let i = 3; i < d.length; i += 4) if (d[i]) n++; return n; }); const img = v.querySelector('img'); return { canvases: cs, text: v.innerText.trim().length, image: img ? img.naturalWidth : null }; })()`);
      assert.ok(blank.text > 0, tag + ' ' + kind + ': the viewer says something');
      assert.ok(blank.canvases.every(n => n > 50), tag + ' ' + kind + ': no blank canvas ' + JSON.stringify(blank.canvases));
      if (kind === 'image') assert.equal(blank.image, 37);
      // Nothing overflows sideways: the page, the main area, the viewer.
      const over = await evaluate(`(() => { const m = document.getElementById('main'), v = document.querySelector('#main .viewer'); return { page: document.documentElement.scrollWidth - innerWidth, main: m.scrollWidth - m.clientWidth, viewer: v.scrollWidth - v.clientWidth }; })()`);
      assert.ok(over.page <= 0 && over.main <= 1 && over.viewer <= 1, tag + ' ' + kind + ': sideways overflow ' + JSON.stringify(over));
      // The viewer from its top; an array's also from its end (the value under the pointer and the histogram).
      await evaluate(`(() => { const v = document.querySelector('#main .viewer'); v.scrollTop = 0; v.scrollIntoView({ block: 'start' }); return true; })()`);
      await shot(tag + '-' + kind);
      if (kind === 'array') { await evaluate(`(() => { const v = document.querySelector('#main .viewer'); v.scrollTop = v.scrollHeight; v.scrollIntoView({ block: 'end' }); return true; })()`); await shot(tag + '-array-end'); }
      seen.push(tag + ' ' + kind + (blank.canvases.length ? ' ' + blank.canvases.length + ' canvas' + (blank.canvases.length > 1 ? 'es' : '') : ''));
    }
    await press(byKey('inside-mode-files')); await settled('files');
    await press(byKey('entry-arrays')); await settled('arrays'); await press(byKey('entry-arrays/pair.npz')); await settled('pair'); await press(byKey('entry-arrays/pair.npz#velocity')); await settled('velocity');
    await shot(tag + '-files');
  }
  await size(1440, 900);
  check('5. No viewer blank and nothing overflowing sideways in light and dark at 1440 × 900 and 1000 × 800 (' + seen.length + ' viewers: ' + seen.slice(0, VIEWERS.length).join(', ') + ', …)' + (shots ? '; screenshots in ' + shots : ''));

  // ---- Nothing failed ---------------------------------------------------------------------------------------------------------
  assert.deepEqual(errors, [], 'Script errors');
  assert.deepEqual(failures, [], 'Failed requests');
  assert.ok(refusedOk.length > 0, 'The refused array was asked for');
  check('No script error, no failed request but the ' + refusedOk.length + ' refusals of arrays/complex.npy asked for' + (moved ? '; ' + moved + ' presses measured again because their target was not under its point' : ''));
  fs.writeFileSync(path.join(report, 'receipt.json'), JSON.stringify({ status: 'pass', folder, checks }, null, 2) + '\n');
  console.log('Receipt in ' + report);
})().catch(async error => {
  process.exitCode = 1;
  console.error(error); if (serverErrors) console.error('Server:', serverErrors.slice(-4000));
  console.error('Script errors:', JSON.stringify(errors)); console.error('Failed requests:', JSON.stringify(failures));
  try { if (evaluate) { console.error('Main scrolled back to 0:', JSON.stringify(await evaluate('window.__resets || null'))); await shot('failure'); console.error('Page:', (await evaluate('document.body.innerText')).slice(0, 2000)); } } catch (_) { /* the page is gone */ }
  fs.writeFileSync(path.join(report, 'failure.json'), JSON.stringify({ status: 'failed', error: String(error && error.stack || error), checks, errors, failures }, null, 2) + '\n');
}).finally(async () => {
  try { session?.close(); } catch (_) { /* closed */ }
  for (const child of children.reverse()) await stop(child);
  if (owned) try { dropOwned(...owned); } catch (error) { console.error('Dropping the disposable schemas failed:', error.message); process.exitCode = 1; }
  try { execFileSync('chmod', ['-R', 'u+w', temporary]); } catch (_) { /* nothing was made read-only */ }   // finished runs leave their directories read-only
  fs.rmSync(temporary, { recursive: true, force: true });
});
