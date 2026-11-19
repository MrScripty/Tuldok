'use strict';
// Curation by embeddings on the page (docs/plans/training-and-curation/spec-t5.md sections 6 and 8, slice T5c) in a
// headless browser, the owner signed in, no GPU. The fixture is a project of its own in Git: datasets/curated, whose
// command (tests/project_curation_browser_fixture.py, standard library only) writes 244 texts with splits and the
// embeddings a script would write beside them, with near-duplicates planted in train, one validation record that is a
// near-copy of a training one and one record far from everything; annotations/quality, a class task on it; and
// datasets/notes, three texts imported. The machine's Pumas endpoint is a fake this check starts
// (tests/browser_fake_pumas.py --embedders: the vision fixture's models, embeddinggemma-2 and nomic-embed); no real
// Pumas is contacted, and nothing here builds an embed (test_tuldok_project_curation does, against the same fake).
//   1. The dataset opened shows Map beside Records and Files; the map is drawn, coloured by split (the legend's counts
//      and the canvas's colours), and by a field when chosen.
//   2. Duplicates lists the three planted pairs; Leakage lists the leaked validation record alone; Outliers puts the far
//      record first; a pair pressed opens its record (the viewer shows it) and More like this lists its copy first.
//   3. A box dragged on the map chooses exactly the records the test computes from embedding_map; "New dataset from
//      these" keeps a select definition holding exactly those ids; "Freeze these" opens the Freeze form filled in, and
//      its Keep writes them as records.
//   4. The Embed form shows EmbeddingGemma 2 as the default model, resolved to the served embeddinggemma-2, and keeps an
//      embed definition; the endpoint's drawer shows the embedder.
//   5. With the map open, a record opened and points chosen, the window regaining focus and a reading on the timer add,
//      remove and change no node.
//   6. Light and dark at 1440 by 900 and 390 by 844: nothing in the map or the drawer overflows sideways (the page's
//      own overflow at 390, which is not this phase's, is recorded).
// It fails on any script error and on any failed request.
//   node tests/browser_project_workspace_curation.cjs [--shots <dir>]
const assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os'), path = require('node:path'), readline = require('node:readline');
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

const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'tuldok-curation-browser-'));
const report = qaDirectory(root, 'project-workspace-curation');
const shots = option('--shots') ? path.resolve(option('--shots')) : null; if (shots) fs.mkdirSync(shots, { recursive: true });
const children = [], checks = [], errors = [], failures = [];
let server, serverErrors = '', origin, auth, socket, session, send, evaluate, owned = null, fake = null, fakeLines = null;
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
/** A command to the fake endpoint (tests/browser_fake_pumas.py), and its answer. */
async function tell(command) { fake.stdin.write(JSON.stringify(command) + '\n'); const [line] = await once(fakeLines, 'line'); return JSON.parse(line); }

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
  await until(async () => !calls.size && await evaluate(`(() => { const reading = e => [...e.querySelectorAll('.note')].some(n => n.textContent === 'Reading…'); return !reading(document.getElementById('main')) && !reading(document.getElementById('aside')) && !document.getElementById('main').hasAttribute('aria-busy') && !document.querySelector('.act-group [aria-busy]') && !document.querySelector('#main [data-key="ann:suggest"][aria-busy]'); })()`), 'settled: ' + label);
  await pause(200);
  await until(async () => !calls.size, 'settled again: ' + label);
}
async function hash(value) { await evaluate(`location.hash = ${JSON.stringify('#' + value)}`); await settled('#' + value); await pause(200); await settled('#' + value); }
const byKey = key => `[data-key=${JSON.stringify(key)}]`;
async function centre(selector) {
  return until(() => evaluate(`(() => { const e = [...document.querySelectorAll(${JSON.stringify(selector)})].find(e => e.offsetParent !== null); if (!e) return null; e.scrollIntoView({ block: 'nearest', inline: 'nearest' }); const r = e.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2, hit = document.elementFromPoint(x, y); return hit && (hit === e || e.contains(hit)) ? { x, y } : null; })()`), 'shown: ' + selector, 100);
}
async function mouse(type, x, y, buttons = 0) { await send('Input.dispatchMouseEvent', { type, x, y, button: type === 'mouseMoved' ? (buttons ? 'left' : 'none') : 'left', buttons, clickCount: type === 'mouseMoved' ? 0 : 1 }); }
async function press(selector) { const { x, y } = await centre(selector); await mouse('mouseMoved', x, y); await mouse('mousePressed', x, y, 1); await mouse('mouseReleased', x, y); }
const KEYS = { Enter: 13, Escape: 27, Tab: 9 };
async function key(name) {
  const code = KEYS[name] || name.toUpperCase().charCodeAt(0), text = name.length === 1 ? name : name === 'Enter' ? '\r' : undefined;
  await send('Input.dispatchKeyEvent', { type: text ? 'keyDown' : 'rawKeyDown', key: name, code: name.length === 1 ? 'Key' + name.toUpperCase() : name, windowsVirtualKeyCode: code, text });
  await send('Input.dispatchKeyEvent', { type: 'keyUp', key: name, windowsVirtualKeyCode: code });
}
async function type(selector, text) { await press(selector); await evaluate(`(() => { const e = document.activeElement; if (e.select) e.select(); return true; })()`); await send('Input.insertText', { text }); }
/** Sets a select's value as a person would choose it, focused and with its change event (no popup is opened: a form that draws itself again on a change would leave an Escape to the page). */
async function choose(selector, value) { await centre(selector); await evaluate(`(() => { const s = document.querySelector(${JSON.stringify(selector)}); s.focus(); s.value = ${JSON.stringify(value)}; s.dispatchEvent(new Event('change', { bubbles: true })); return true; })()`); }
async function shot(name) {
  await evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))');
  const png = Buffer.from((await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })).data, 'base64');
  fs.writeFileSync(path.join(report, name + '.png'), png); if (shots) fs.writeFileSync(path.join(shots, name + '.png'), png);
}
const text = selector => evaluate(`(() => { const e = document.querySelector(${JSON.stringify(selector)}); return e ? e.innerText : null; })()`);
const value = selector => evaluate(`(() => { const e = document.querySelector(${JSON.stringify(selector)}); return e ? e.value : null; })()`);
const options = selector => evaluate(`[...document.querySelectorAll(${JSON.stringify(selector + ' option')})].map(o => o.value)`);


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
      counts = {}; for (const id of ids) counts[id] = { added: 0, removed: 0, attrs: 0, text: 0, readAt: 0, what: [] };
      for (const id of ids) { watch(id, el(id)); for (const e of el(id).querySelectorAll('*')) e.__seen = 1; }
      flash = 0; clearInterval(timer); timer = setInterval(() => { if ((el('main').textContent + el('aside').textContent).includes('Reading…')) flash++; }, 50);
    },
    stop() { clearInterval(timer); const fresh = {}; for (const id of ids) fresh[id] = [...el(id).querySelectorAll('*')].filter(e => !e.__seen).length; const r = { counts, flash, fresh }; counts = null; for (const o of observers) o.disconnect(); observers = []; return r; }
  };
})(); true`;

const REF = 'datasets/curated';
let folder;
(async () => {
  // ---- The fake endpoint, the fixture and Tuldok ---------------------------------------------------------------------
  fake = launch(python, [path.join(root, 'tests', 'browser_fake_pumas.py'), '--embedders'], { cwd: root, stdio: ['pipe', 'pipe', 'pipe'] });
  let fakeErrors = ''; fake.stderr.on('data', chunk => { fakeErrors += chunk; });
  fakeLines = readline.createInterface({ input: fake.stdout });
  const base = await Promise.race([once(fakeLines, 'line').then(([line]) => line.trim()), once(fake, 'exit').then(() => { throw Error('The fake endpoint exited: ' + fakeErrors); })]);
  assert.match(base, /^http:\/\/127\.0\.0\.1:\d+$/);

  const repo = path.join(temporary, 'fixture'), code = path.join(repo, 'code'); folder = path.join(repo, 'project');
  for (const d of ['datasets', 'annotations', 'environments']) fs.mkdirSync(path.join(folder, d), { recursive: true });
  fs.mkdirSync(path.join(code, 'notes'), { recursive: true });
  fs.writeFileSync(path.join(folder, 'tuldok.json'), JSON.stringify({ format: 'tuldok_project_v1', id: require('node:crypto').randomUUID().replace(/-/g, ''), name: 'Curation check', code_root: '../code' }, null, 2) + '\n');
  fs.copyFileSync(path.join(root, 'tests', 'project_curation_browser_fixture.py'), path.join(code, 'make_curated.py'));
  for (const [n, t] of [['a', 'Apples in a bowl.'], ['b', 'Boats in a bay.'], ['c', 'Cats on a wall.']]) fs.writeFileSync(path.join(code, 'notes', n + '.txt'), t + '\n');
  const doc = o => JSON.stringify(Object.assign({ format: 'tuldok_definition_v1' }, o), null, 2) + '\n';
  fs.writeFileSync(path.join(folder, 'environments', 'test-python.json'), doc({ kind: 'environment', title: 'The interpreter running the tests', python: '3.12', device: 'cpu', packages: { jsonschema: '4.26.0' } }));
  fs.writeFileSync(path.join(folder, 'datasets', 'curated.json'), doc({ kind: 'dataset', title: 'Curated notes', description: 'Texts with splits and their embeddings, for curation.', run: { command: ['python', 'make_curated.py', '--out', '{output}'], environment: 'environments/test-python', sources: ['make_curated.py'] } }));
  fs.writeFileSync(path.join(folder, 'datasets', 'notes.json'), doc({ kind: 'dataset', title: 'Three notes', run: { step: 'import', settings: { source: 'notes', rights: 'Written for this check; free to use.' } } }));
  fs.writeFileSync(path.join(folder, 'annotations', 'quality.json'), doc({ kind: 'annotation', title: 'Quality', dataset: REF, task: 'class', vocabulary: ['good', 'bad'] }));
  const git = ['-c', 'user.name=Tuldok Test', '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false', '-c', 'init.defaultBranch=main', '-C', repo];
  execFileSync('git', [...git, 'init', '-q']); execFileSync('git', [...git, 'add', '-A']); execFileSync('git', [...git, 'commit', '-q', '-m', 'The fixture.']);
  const home = process.env.TULDOK_PROJECT_HOME || path.join(temporary, 'home'), catalog = path.join(temporary, 'catalog'); fs.mkdirSync(home, { recursive: true });
  const settingsFile = process.env.TULDOK_SETTINGS || path.join(temporary, 'settings.json');
  fs.mkdirSync(path.dirname(settingsFile), { recursive: true }); fs.writeFileSync(settingsFile, JSON.stringify({ format: 'tuldok_settings_v1', pumas_endpoint: base }) + '\n', { mode: 0o600 });
  const env = { ...process.env, TULDOK_PROJECT_HOME: home, TULDOK_SETTINGS: settingsFile };
  owned = [folder, catalog]; dropOwned(folder, catalog);
  const cli = (...args) => execFileSync(python, ['-m', 'tuldok_project', ...args], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] }).toString();
  assert.match(cli('check', folder), /^0 errors/m);
  cli('connect', folder, 'test-python', python);
  cli('build', folder, REF, '--yes'); cli('build', folder, 'datasets/notes', '--yes');
  let output = '';
  server = launch(python, ['-u', 'app.py', '--port', '0', '--data', catalog, '--project-folder', folder], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] });
  server.stdout.on('data', chunk => { output += chunk; }); server.stderr.on('data', chunk => { serverErrors += chunk; });
  const port = await until(() => { if (server.exitCode !== null) throw Error('Tuldok exited: ' + serverErrors); return output.match(/127\.0\.0\.1:(\d+)/)?.[1]; }, 'Tuldok start-up', 3000);
  origin = 'http://127.0.0.1:' + port;
  auth = authenticatedFixture(); await auth.register(origin, catalog, root);
  const run = (await api('products', { reference: REF })).products[0].run_id;

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
  await size(1440, 900); await theme('light');
  await auth.browser(send, origin);
  const load = async (name, place) => {
    await theme(name);
    await send('Page.navigate', { url: 'about:blank' }); await pause(100);
    await send('Page.navigate', { url: origin + '/?theme=' + name + '#' + place });
    await until(() => evaluate(`document.readyState === 'complete' && !!document.getElementById('needs-btn') && !document.getElementById('needs-btn').disabled`), 'the project read', 1200);
    await settled('opened ' + place);
  };
  const kept = async label => { await until(async () => !(await evaluate(`!!document.querySelector('.act-group [aria-busy]')`)), 'kept: ' + label); await settled(label); };
  const drawn = () => evaluate(`(() => { const c = document.querySelector('#main .cur-map canvas'); return c ? Number(c.dataset.drawn || 0) : 0; })()`);
  const listRows = () => evaluate(`[...document.querySelectorAll('#main .cur-list .cur-row')].map(b => b.dataset.key)`);
  const listShown = async (name, label) => { await until(() => evaluate(`(() => { const l = document.querySelector('#main .cur-list'); return !!l && l.dataset.list === ${JSON.stringify(name)} && !/^Reading…$/.test(l.innerText.trim()); })()`), label); await settled(label); };
  const openMap = async name => {
    await load(name, 'data/inside%3A' + REF);
    await press(byKey('inside-mode-map'));
    await until(async () => (await drawn()) === 244, 'the map drawn');
    await listShown('duplicates', 'the duplicates listed');
  };
  /** Colours present on the map's canvas: how many of its pixels are each of the tokens named. */
  const colours = names => evaluate(`(() => {
    const c = document.querySelector('#main .cur-map canvas'), d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
    const want = ${JSON.stringify(names)}.map(n => { const v = getComputedStyle(document.documentElement).getPropertyValue(n).trim(), x = parseInt(v.slice(1), 16); return [n, [x >> 16, (x >> 8) & 255, x & 255]]; });
    const found = Object.fromEntries(want.map(([n]) => [n, 0]));
    for (let i = 0; i < d.length; i += 4) for (const [n, rgb] of want) if (d[i] === rgb[0] && d[i + 1] === rgb[1] && d[i + 2] === rgb[2]) found[n]++;
    return found; })()`);

  // ---- 1. The map, coloured by split -------------------------------------------------------------------------------
  await openMap('light');
  assert.equal(await value(byKey('cur-colour')), 'split', 'Coloured by split first');
  const legend = await text('#main .cur-legend');
  for (const words of ['train · 195', 'validation · 25', 'test · 24']) assert.ok(legend.includes(words), 'The legend: ' + legend);
  const bySplit = await colours(['--cat-1', '--cat-2', '--cat-3']);
  assert.ok(bySplit['--cat-1'] > 50 && bySplit['--cat-2'] > 10 && bySplit['--cat-3'] > 10, 'The three splits\' colours are drawn: ' + JSON.stringify(bySplit));
  const facts = await text('#main .cur-facts');
  assert.match(facts, /244 records · 16 dimensions · stand-in · principal components/);
  await choose(byKey('cur-colour'), 'field:topic');
  await until(async () => /boats · 40/.test(await text('#main .cur-legend') || ''), 'coloured by topic');
  const byTopic = await colours(['--cat-1', '--cat-2', '--cat-3', '--cat-4', '--cat-5', '--cat-6']);
  assert.ok(Object.values(byTopic).every(n => n > 10), 'Six topics drawn: ' + JSON.stringify(byTopic));
  await choose(byKey('cur-colour'), 'split'); await until(async () => /train · 195/.test(await text('#main .cur-legend') || ''), 'back to split');
  check('1. The dataset opened shows Map; the map draws 244 records ("' + facts.slice(0, 90) + '…") coloured by split (' + JSON.stringify(bySplit) + ' pixels of the three colours) and by a field (six topics)');

  // ---- 2. The lists ---------------------------------------------------------------------------------------------------
  const dups = await listRows();
  assert.deepEqual(dups.sort(), ['cur-dup-r010-d001', 'cur-dup-r020-d002', 'cur-dup-r040-v001'], 'The planted pairs');
  await press(byKey('cur-list-leakage')); await listShown('leakage', 'leakage');
  assert.deepEqual(await listRows(), ['cur-leak-v001'], 'The leaked record alone');
  const leakNote = await text('#main .cur-list');
  assert.match(leakNote, /1 record outside train has a near-copy in it/);
  await press(byKey('cur-list-outliers')); await listShown('outliers', 'outliers');
  assert.equal((await listRows())[0], 'cur-out-far01', 'The far record first');
  await press(byKey('cur-list-duplicates')); await listShown('duplicates', 'duplicates again');
  await press(byKey('cur-dup-r010-d001')); await listShown('like', 'more like r010');
  assert.equal((await listRows())[0], 'cur-like-d001', 'Its copy is the most alike');
  await until(async () => (await text('#main .viewer .iv-head h3')) === 'r010', 'the viewer shows r010');
  assert.match(await text('#main .viewer'), /Note 10 about bees\./);
  check('2. Duplicates lists the 3 planted pairs; Leakage lists v001 alone ("' + leakNote.split('\n').find(l => /near-copy/.test(l)).slice(0, 80) + '…"); Outliers puts far01 first; pressing r010 ≈ d001 opens r010 in the viewer and More like this lists d001 first');

  // ---- 3. A region chosen becomes a dataset, and fills Freeze ---------------------------------------------------------
  await press(byKey('cur-clear'));
  const m = await api('embedding_map', { run, name: 'curated' });
  const f32 = b => { const buf = Buffer.from(b, 'base64'); return Array.from({ length: buf.length / 4 }, (_, i) => buf.readFloatLE(i * 4)); };
  const xs = f32(m.x_f32), ys = f32(m.y_f32), [x0, x1, y0, y1] = m.bounds;
  const rect = await evaluate(`(() => { const r = document.querySelector('#main .cur-map canvas').getBoundingClientRect(); return { left: r.left, top: r.top, width: r.width, height: r.height }; })()`);
  const PAD = 12, iw = rect.width - 2 * PAD, ih = rect.height - 2 * PAD;
  const from = [rect.left + 4, rect.top + 4], to = [rect.left + rect.width * 0.42, rect.top + rect.height - 4];
  const expected = m.ids.filter((id, i) => { const px = rect.left + PAD + (xs[i] - x0) / (x1 - x0) * iw, py = rect.top + PAD + (1 - (ys[i] - y0) / (y1 - y0)) * ih; return px >= from[0] && px <= to[0] && py >= from[1] && py <= to[1]; });
  assert.ok(expected.length > 20 && expected.length < 200, 'The box holds some of the records: ' + expected.length);
  await mouse('mouseMoved', ...from); await mouse('mousePressed', ...from, 1);
  for (let t = 1; t <= 8; t++) await mouse('mouseMoved', from[0] + (to[0] - from[0]) * t / 8, from[1] + (to[1] - from[1]) * t / 8, 1);
  await mouse('mouseReleased', ...to);
  await until(async () => (await text('#main .cur-count')) === expected.length + ' records chosen', 'the box chosen: ' + expected.length);
  await press(byKey('cur-new'));
  await type(byKey('curnew:field:title'), 'Left of the map');
  await press(byKey('curnew:keep')); await kept('the new dataset');
  await until(async () => /Kept datasets\/left-of-the-map as an unsaved edit/.test(await text('#main .cur-chosen') || ''), 'kept, said beside the map');
  const picked = (await api('definition', { reference: 'datasets/left-of-the-map' })).document;
  assert.deepEqual(picked.run, { step: 'select', inputs: { records: REF }, settings: { records: expected } }, 'The definition holds exactly the chosen records');
  assert.equal(await text('#main .cur-count'), expected.length + ' records chosen', 'The choice stays');
  await press(byKey('cur-freeze'));
  await until(() => evaluate(`decodeURIComponent(location.hash) === '#data/new:freeze' && !!document.querySelector('#aside .frz-records')`), 'Freeze filled in');
  await settled('freeze');
  assert.equal(await value(byKey('newfreeze:field:dataset')), REF);
  assert.match(await text('#aside .frz-records'), new RegExp('Only the ' + expected.length + ' records chosen on the map'));
  await type(byKey('newfreeze:field:title'), 'Left frozen');
  await press(byKey('newfreeze:keep')); await kept('the freeze');
  const frozen = (await api('definition', { reference: 'datasets/left-frozen' })).document;
  assert.deepEqual(frozen.run.inputs, { records: REF }); assert.deepEqual(frozen.run.annotations, ['annotations/quality']);
  assert.deepEqual(frozen.run.settings.records, expected, 'Freeze names exactly the chosen records');
  check('3. A box dragged on the map chose exactly the ' + expected.length + ' records the test computed from embedding_map; New dataset from these kept datasets/left-of-the-map, a select of exactly those ids; Freeze these opened the Freeze form filled in, whose Keep wrote them as records');

  // ---- 4. The Embed form and the embedder -----------------------------------------------------------------------------
  await load('light', 'data');
  await press(byKey('data:new:embed'));
  await until(() => evaluate(`!!document.querySelector('#aside [data-key="newembed:field:model"]')`), 'the Embed form'); await settled('embed form');
  const first = await evaluate(`document.querySelector('#aside [data-key="newembed:field:model"] option').textContent`);
  assert.equal(first, 'Default: EmbeddingGemma 2 → embeddinggemma-2 · embeddinggemma-2-gpu (unsloth/embeddinggemma-2-GGUF)');
  assert.deepEqual(await options('#aside [data-key="newembed:field:model"]'), ['', 'embeddinggemma-2\u0000embeddinggemma-2-gpu', 'nomic-embed\u0000nomic-embed-gpu']);
  assert.equal(await value(byKey('newembed:field:prefix')), 'task: clustering | query: ');
  await type(byKey('newembed:field:title'), 'Notes embedded'); await choose(byKey('newembed:field:dataset'), 'datasets/notes');
  await press(byKey('newembed:keep')); await kept('the embed');
  assert.deepEqual((await api('definition', { reference: 'datasets/notes-embedded' })).document.run, { step: 'embed', inputs: { records: 'datasets/notes' }, settings: {} });
  await load('light', 'train/endpoint');
  await until(() => text('#aside .emb-part'), 'the embedder in the endpoint\'s drawer');
  const part = await text('#aside .emb-part');
  assert.match(part, /the default, EmbeddingGemma 2/); assert.match(part, /embeddinggemma-2 · embeddinggemma-2-gpu \(unsloth\/embeddinggemma-2-GGUF\)/);
  check('4. The Embed form offers "' + first + '" first, then the served embedders, with the prefix "task: clustering | query: ", and keeps an embed of datasets/notes naming no model; the endpoint\'s drawer shows the embedder and what it resolves to');

  // ---- 5. Nothing redrawn by a reading ---------------------------------------------------------------------------------
  await openMap('light');
  await press(byKey('cur-dup-r020-d002')); await listShown('like', 'more like r020');
  await evaluate(WATCHER); await evaluate(`window.__still.start()`);
  let since = Date.now(); await evaluate(`window.dispatchEvent(new Event('focus')); true`); await reading(since, WATCHED.concat(['map']), 'focus');
  since = Date.now(); await reading(since, WATCHED, 'the timer', Math.round((IDLE_MS + 8000) / 100));
  const r = await evaluate(`window.__still.stop()`);
  for (const id of ['tabs', 'main', 'aside']) assert.deepEqual([r.counts[id].added, r.counts[id].removed, r.counts[id].attrs, r.counts[id].text, r.fresh[id]], [0, 0, 0, 0, 0], id + ' untouched: ' + JSON.stringify(r.counts[id]));
  assert.equal(r.flash, 0, 'no "Reading…"');
  assert.equal(await text('#main .cur-count'), '2 records chosen');
  check('5. With the map open, r020 opened and two records chosen, the window regaining focus and a reading on the timer added, removed and changed no node of the tab bar, the main area or the drawer');

  // ---- 6. Light and dark, wide and narrow -----------------------------------------------------------------------------
  const seen = [], pageOver = {};
  const over = async label => {
    const o = await evaluate(`(() => { const m = document.getElementById('main'), cur = document.querySelector('#main .cur'), a = document.getElementById('drawer');
      const inner = cur ? [...cur.querySelectorAll('*')].filter(e => e.scrollWidth - e.clientWidth > 1 && getComputedStyle(e).overflowX !== 'auto' && getComputedStyle(e).overflowX !== 'hidden').map(e => e.className) : [];
      const r = cur ? cur.getBoundingClientRect() : null, mr = m.getBoundingClientRect();
      return { page: document.documentElement.scrollWidth - innerWidth, cur: cur ? cur.scrollWidth - cur.clientWidth : 0, past: r ? Math.round(r.right - mr.right) : 0, drawer: a.scrollWidth - a.clientWidth, inner }; })()`);
    assert.ok(o.cur <= 1 && o.past <= 1 && o.drawer <= 1 && !o.inner.length, label + ': sideways overflow ' + JSON.stringify(o));
    pageOver[label] = o.page;
  };
  const view = async (tag, name) => { await over(tag + ' ' + name); await shot(tag + '-' + name); seen.push(tag + ' ' + name); };
  for (const [w, hgt] of [[1440, 900], [390, 844]]) for (const name of ['light', 'dark']) {
    const tag = name + '-' + w;
    await size(w, hgt);
    await openMap(name); await view(tag, 'map');
    await press(byKey('cur-list-leakage')); await listShown('leakage', 'leakage'); await press(byKey('cur-leak-v001')); await listShown('like', 'more like v001');
    await evaluate(`(() => { document.querySelector('#main .cur-lists').scrollIntoView({ block: 'start' }); return true; })()`);
    await view(tag, 'more-like-this');
    await hash('data'); await press(byKey('data:new:embed')); await until(() => evaluate(`!!document.querySelector('#aside [data-key="newembed:field:model"]')`), 'the Embed form'); await settled('embed');
    await view(tag, 'embed-form');
  }
  await size(1440, 900);
  const wide = Object.entries(pageOver).filter(([k, v]) => v > 0);
  assert.ok(wide.every(([k]) => / 390 /.test(' ' + k.replace('-', ' ') + ' ') || k.includes('-390')), 'The page overflows only at 390: ' + JSON.stringify(wide));
  check('6. Nothing in the map, its lists or the drawer overflows sideways in light and dark at 1440 × 900 and 390 × 844 (' + seen.length + ' views); the page itself is ' + (wide.length ? 'wider than 390 by ' + [...new Set(wide.map(([, v]) => v))].join(', ') + ' px (its header and strip, as found in phase 2)' : 'never wider than the window') + (shots ? '; screenshots in ' + shots : ''));

  // ---- Nothing failed ---------------------------------------------------------------------------------------------------
  assert.deepEqual(errors, [], 'Script errors');
  assert.deepEqual(failures, [], 'Failed requests');
  check('No script error, no failed request');
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
  try { fake?.stdin.end(); } catch (_) { /* gone */ }
  for (const child of children.reverse()) await stop(child);
  if (owned) try { dropOwned(...owned); } catch (error) { console.error('Dropping the disposable schemas failed:', error.message); process.exitCode = 1; }
  try { execFileSync('chmod', ['-R', 'u+w', temporary]); } catch (_) { /* nothing was made read-only */ }
  fs.rmSync(temporary, { recursive: true, force: true });
});
