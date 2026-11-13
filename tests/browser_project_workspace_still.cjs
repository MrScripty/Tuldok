'use strict';
// The project workspace updates in place (docs/plans/definition-first-projects/spec-w4.md section 4) in a headless
// browser, signed in as the owner. Tuldok runs with --project-folder on a copy of the minimal fixture with the
// buildable fixture's definitions beside it, in a Git repository of its own, and one more recipe with a stand-in
// command that trains nothing: recipes/steady prints a progress line every half second for about a minute. The page
// is watched with a MutationObserver on the tab bar, the strip, the main area, the drawer and Needs you; the elements
// on screen are marked so that new ones can be told apart; and the page is sampled every 50 ms for "Reading…".
//   1. Nothing changed: on every tab, and with a model's, a run's, a build request's and a dataset's drawer, the plan
//      view and the editor open, the window regaining focus adds, removes and changes no node anywhere (but the
//      minute of "Read at") and every scroll position stays (the main area both ways, every scrolled element inside
//      it and the drawer, the map, the list, the drawer). On Train and on Overview the same holds across a reading on
//      the fifteen-second timer; Needs you open stays open and untouched.
//   2. Something changed elsewhere: on Train, scrolled, a control focused, a second session (an agent credential)
//      asks for a build; within one reading the strip's count and the Train list show it, "Reading…" is never shown,
//      the scroll and the focus stay. With that request's drawer open, scrolled, the owner approves it from outside
//      the page: the drawer shows the new state without "Reading…" and keeps its scroll.
//   3. A build runs: the strip's hairline moves, the open run's drawer reads on, and the run's row in Train's list
//      reads on with no node added or removed; on the Map tab, with the model's drawer open, the main area gains no
//      node until the run ends; then the model is drawn built, the map's and the list's scroll kept, and "Reading…"
//      never shown.
//   4. The editor is left alone: with text typed into a field of the editor and not kept, a change elsewhere (a
//      second request) and the window regaining focus do not touch the drawer; the typed text, the focus and the
//      caret stay.
//   5. A reading that fails: cut off from the server, the page keeps what it shows and the strip says the project
//      was not read; when the server answers again the strip says where the project stands, and nothing else was
//      touched.
// With --lab-root <project folder> only step 1 runs, on that folder opened in place, and nothing is asked of the
// project that changes it. It fails on any script error or failed request.
//   node tests/browser_project_workspace_still.cjs [--lab-root <project folder>]
const assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const { spawn, execFileSync } = require('node:child_process'), { once } = require('node:events');
const { authenticatedFixture } = require('./auth_helpers.cjs'), { waitForDebugger } = require('./browser_startup.cjs'), { cdpSession } = require('./browser_cdp_session.cjs'), { qaDirectory } = require('./qa_artifacts.cjs');

const root = path.resolve(__dirname, '..');
const argv = process.argv.slice(2), labAt = argv.indexOf('--lab-root');
const labRoot = labAt >= 0 ? path.resolve(argv[labAt + 1] || '') : null;
if (labAt >= 0) assert.ok(argv[labAt + 1] && fs.existsSync(path.join(labRoot, 'tuldok.json')), '--lab-root names a project folder (it holds tuldok.json)');
assert.ok(process.env.TULDOK_DATABASE_URL, 'TULDOK_DATABASE_URL must name a disposable PostgreSQL cluster');
const venv = path.join(root, '.venv', 'bin');
if (fs.existsSync(path.join(venv, 'python'))) process.env.PATH = venv + path.delimiter + process.env.PATH;   // auth_helpers runs python3
const python = fs.existsSync(path.join(venv, 'python')) ? path.join(venv, 'python') : 'python3';
const WIDTH = 1280, HEIGHT = 680;   // short enough that Train, the drawers and the list scroll on the fixture
const IDLE_MS = 15000;              // the page's reading while nothing builds (app.js)
const WATCHED = ['summary', 'status', 'build_requests', 'environments', 'runs'];

const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'tuldok-still-browser-'));
const report = qaDirectory(root, labRoot ? 'project-workspace-still-lab' : 'project-workspace-still');
const children = [], checks = [], errors = [], failures = [];
let offline = false;   // step 5 cuts the page off from the server on purpose: what fails then is not a fault
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
/** An operation as the owner (the fixture's session, not the page); bearer: as that agent credential instead. */
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

// ---- The page's readings, from the browser's network -----------------------------
// Each call of an operation the page makes, by name, with when it was sent and when it finished.
const calls = new Map(), finished = [];
function network(event) {
  const p = event.params;
  if (event.method === 'Network.requestWillBeSent' && /\/api\/project\/[a-z_]+$/.test(p.request.url)) calls.set(p.requestId, { name: p.request.url.split('/').pop(), sent: Date.now() });
  if ((event.method === 'Network.loadingFinished' || event.method === 'Network.loadingFailed') && calls.has(p.requestId)) { finished.push(Object.assign(calls.get(p.requestId), { done: Date.now() })); calls.delete(p.requestId); }
}
/** Waits for a reading begun after since: each of names asked for and answered, then nothing asked for 700 ms, then the page settled. */
async function reading(since, names, label, tries = 300) {
  await until(() => names.every(name => finished.some(f => f.name === name && f.sent >= since)), 'a reading: ' + label, tries);
  await until(() => !calls.size && Date.now() - Math.max(0, ...finished.map(f => f.done)) > 700, 'the reading done: ' + label, 300);
  await settled(label);
}
/** Waits until nothing reads and no control waits for its answer. */
async function settled(label) {
  await until(() => evaluate(`(() => { const reading = e => [...e.querySelectorAll('.note')].some(n => n.textContent === 'Reading…'); return !reading(document.getElementById('main')) && !reading(document.getElementById('aside')) && !document.getElementById('main').hasAttribute('aria-busy') && !document.querySelector('.act-group [aria-busy]'); })()`), 'settled: ' + label);
  await pause(150);
}
async function hash(value) { await evaluate(`location.hash = ${JSON.stringify('#' + value)}`); await settled('#' + value); await pause(250); await settled('#' + value); }
const byKey = key => `[data-key=${JSON.stringify(key)}]`;
async function press(selector) {
  const { x, y } = await until(() => evaluate(`(() => { const e = [...document.querySelectorAll(${JSON.stringify(selector)})].find(e => e.offsetParent !== null); if (!e) return null; e.scrollIntoView({ block: 'nearest', inline: 'nearest' }); const r = e.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; })()`), 'shown: ' + selector, 100);
  await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y });
  await send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 }); await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 });
}
const drawerState = () => evaluate(`[...document.querySelectorAll('#aside header .state')].map(e => e.textContent.trim()).join(' ')`);
const needsCount = () => evaluate(`Number((document.getElementById('needs-btn').textContent.match(/(\\d+)$/) || [])[1])`);

// The watcher in the page: the observer starts counting at start(), so a record queued before it is not counted.
const WATCHER = `window.__still = (() => {
  const ids = ['tabs', 'strip', 'main', 'aside', 'needs-panel'], el = id => document.getElementById(id);
  let counts = null, flash = 0, timer = null;
  const name = n => !n ? '?' : n.nodeType === 1 ? n.tagName.toLowerCase() + (typeof n.className === 'string' && n.className ? '.' + n.className.trim().split(/\\s+/).join('.') : '') : '#text ' + JSON.stringify(String(n.data || '').slice(0, 30));
  for (const id of ids) new MutationObserver(list => {
    if (!counts) return;
    const c = counts[id];
    for (const r of list) {
      if (r.type === 'childList') { c.added += r.addedNodes.length; c.removed += r.removedNodes.length; for (const n of [...r.addedNodes, ...r.removedNodes]) if (c.what.length < 6) c.what.push(name(n) + ' in ' + name(r.target)); }
      else if (r.type === 'characterData') { const msg = el('strip').querySelector('.msg'), parent = r.target.parentNode; if ((msg && r.target === msg.lastChild) || (parent && parent.dataset && parent.dataset.readAt)) c.readAt++; else { c.text++; if (c.what.length < 6) c.what.push('text of ' + name(r.target.parentNode) + ': ' + String(r.target.data).slice(0, 40)); } }
      else { c.attrs++; if (c.what.length < 6) c.what.push('@' + r.attributeName + ' on ' + name(r.target)); }
    }
  }).observe(el(id), { childList: true, subtree: true, characterData: true, attributes: true });
  const where = (e, top) => { const p = []; while (e && e !== top) { p.unshift(e.tagName.toLowerCase() + ':' + [...e.parentElement.children].indexOf(e)); e = e.parentElement; } return p.join('>'); };
  function scrolls() {
    const main = el('main'), drawer = el('drawer'), out = { main: [main.scrollLeft, main.scrollTop].map(Math.round), drawer: [drawer.scrollLeft, drawer.scrollTop].map(Math.round) };
    for (const [id, top] of [['main', main], ['aside', el('aside')]]) for (const e of top.querySelectorAll('*')) if (e.scrollLeft || e.scrollTop) out[id + ' ' + where(e, top)] = [Math.round(e.scrollLeft), Math.round(e.scrollTop)];
    return out;
  }
  return {
    start() { counts = {}; for (const id of ids) { counts[id] = { added: 0, removed: 0, attrs: 0, text: 0, readAt: 0, what: [] }; for (const e of el(id).querySelectorAll('*')) e.__seen = 1; } flash = 0; clearInterval(timer); timer = setInterval(() => { if ((el('main').textContent + el('aside').textContent).includes('Reading…')) flash++; }, 50); },
    peek() { return { counts: JSON.parse(JSON.stringify(counts)), flash }; },
    stop() { clearInterval(timer); const fresh = {}; for (const id of ids) fresh[id] = [...el(id).querySelectorAll('*')].filter(e => !e.__seen).length; const r = { counts, flash, fresh, scrolls: scrolls(), needsOpen: !el('needs-panel').hidden }; counts = null; return r; },
    scrolls,
    /** Scrolls the main area, every element in it and in the drawer that overflows (a little), and the drawer. */
    scrollAll() {
      const main = el('main'), drawer = el('drawer'), bit = (e, x, y) => { if (e.scrollWidth > e.clientWidth + 1) e.scrollLeft = Math.min(x, e.scrollWidth - e.clientWidth); if (e.scrollHeight > e.clientHeight + 1) e.scrollTop = Math.min(y, e.scrollHeight - e.clientHeight); };
      for (const top of [main, el('aside')]) for (const e of top.querySelectorAll('*')) bit(e, 37, 41);
      bit(main, 23, 160); if (drawer.classList.contains('open')) bit(drawer, 0, 90);
      return scrolls();
    }
  };
})(); true`;
async function start() { await evaluate(`window.__still.start(); true`); }
async function stopWatch() { return evaluate(`window.__still.stop()`); }
const touched = (r, ids) => ids.filter(id => { const c = r.counts[id]; return c.added || c.removed || c.attrs || c.text || r.fresh[id]; }).map(id => id + ' ' + JSON.stringify(r.counts[id]) + ' new ' + r.fresh[id]);

(async () => {
  let folder;
  if (labRoot) folder = labRoot;
  else {
    // ---- The fixture: minimal + buildable + a stand-in recipe of about a minute, in Git ----------------
    fs.cpSync(path.join(root, 'tests', 'fixtures', 'tuldok_project', 'minimal'), path.join(temporary, 'fixture'), { recursive: true });
    folder = path.join(temporary, 'fixture', 'project');
    const code = path.join(temporary, 'fixture', 'code'), buildable = path.join(root, 'tests', 'fixtures', 'tuldok_project', 'buildable');
    for (const kind of ['environments', 'datasets', 'recipes', 'benchmarks', 'charts']) for (const name of fs.readdirSync(path.join(buildable, 'project', kind))) fs.copyFileSync(path.join(buildable, 'project', kind, name), path.join(folder, kind, name));
    for (const name of fs.readdirSync(path.join(buildable, 'code'))) fs.cpSync(path.join(buildable, 'code', name), path.join(code, name), { recursive: true });
    fs.writeFileSync(path.join(code, 'steady.py'), `import json, os, sys, time
out = sys.argv[sys.argv.index('--out') + 1]
for step in range(1, 121):
    print(json.dumps({'format': 'tuldok_progress_v1', 'stage': 'fit', 'completed': step, 'total': 120, 'metrics': {'loss': 1.0 / step}}), flush=True)
    print('step', step, 'of 120', file=sys.stderr, flush=True)
    time.sleep(0.5)
with open(os.path.join(out, 'weights.json'), 'w') as handle:
    json.dump({'constant': 3.0}, handle)
`);
    fs.writeFileSync(path.join(folder, 'recipes', 'steady.json'), JSON.stringify({ format: 'tuldok_definition_v1', kind: 'recipe', title: 'Steady fit, about a minute', labels: { short: 'STEADY' }, change: 'refinement', derived_from: 'recipes/fit-a',
      run: { command: ['python', 'steady.py', '--out', '{output}'], environment: 'environments/test-python', outputs: { weights: { path: 'weights.json', role: 'weights' } }, sources: ['steady.py'] } }, null, 2) + '\n');
    const git = ['-c', 'user.name=Tuldok Test', '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false', '-c', 'init.defaultBranch=main', '-C', path.join(temporary, 'fixture')];
    execFileSync('git', [...git, 'init', '-q']); execFileSync('git', [...git, 'add', '-A']); execFileSync('git', [...git, 'commit', '-q', '-m', 'The fixture.']);
  }
  const home = path.join(temporary, 'home'), catalog = path.join(temporary, 'catalog'); fs.mkdirSync(home);
  const env = { ...process.env, TULDOK_PROJECT_HOME: home, TULDOK_SETTINGS: path.join(temporary, 'settings.json') };
  owned = [folder, catalog]; dropOwned(folder, catalog);
  if (!labRoot) {
    const cli = (...args) => execFileSync(python, ['-m', 'tuldok_project', ...args], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] }).toString();
    cli('connect', folder, 'test-python', python);
    cli('build', folder, 'datasets/numbers', '--yes');   // a run and a product, for the run's and the dataset's drawers
  }
  let output = '';
  server = launch(python, ['-u', 'app.py', '--port', '0', '--data', catalog, '--project-folder', folder], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] });
  server.stdout.on('data', chunk => { output += chunk; }); server.stderr.on('data', chunk => { serverErrors += chunk; });
  const port = await until(() => { if (server.exitCode !== null) throw Error('Tuldok exited: ' + serverErrors); return output.match(/127\.0\.0\.1:(\d+)/)?.[1]; }, 'Tuldok start-up', 3000);
  origin = 'http://127.0.0.1:' + port;
  auth = authenticatedFixture(); await auth.register(origin, catalog, root);
  // A second session: an agent that may ask for builds (the fixture only).
  const agent = labRoot ? null : await credential('A second session', ['inspect', 'execute']);
  const firstAsk = agent ? await api('request_build', { targets: ['recipes/fit-b'] }, agent) : null;
  if (firstAsk) assert.equal(firstAsk.state, 'awaiting-approval');

  const browser = launch(findBrowser(), ['--headless', '--no-sandbox', '--disable-gpu', '--no-first-run', '--hide-scrollbars', '--remote-debugging-port=0', `--window-size=${WIDTH},${HEIGHT}`, '--user-data-dir=' + path.join(temporary, 'browser'), 'about:blank'], { stdio: 'ignore', env: { ...process.env, XDG_CONFIG_HOME: temporary, XDG_CACHE_HOME: temporary } });
  const debugPort = await waitForDebugger(browser, path.join(temporary, 'browser', 'DevToolsActivePort'));
  const target = (await (await fetch('http://127.0.0.1:' + debugPort + '/json')).json()).find(item => item.type === 'page');
  socket = new WebSocket(target.webSocketDebuggerUrl); await once(socket, 'open');
  session = cdpSession(socket, { timeoutMs: 60000, onEvent: event => {
    network(event);
    if (event.method === 'Runtime.exceptionThrown') errors.push(event.params.exceptionDetails.exception?.description || event.params.exceptionDetails.text);
    if (event.method === 'Runtime.consoleAPICalled' && event.params.type === 'error') errors.push(event.params.args.map(a => a.value ?? a.description).join(' '));
    if (event.method === 'Log.entryAdded' && event.params.entry.level === 'error' && !offline) errors.push(event.params.entry.text + ' ' + (event.params.entry.url || ''));
    if (event.method === 'Network.loadingFailed' && !event.params.canceled && !offline) failures.push({ id: event.params.requestId, error: event.params.errorText });
    if (event.method === 'Network.responseReceived' && event.params.response.status >= 400) failures.push({ url: event.params.response.url, status: event.params.response.status });
  } });
  send = session.send;
  evaluate = async expression => { const result = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }); if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails)); return result.result.value; };
  await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable'); await send('Log.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: WIDTH, height: HEIGHT, deviceScaleFactor: 1, mobile: false });
  await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-reduced-motion', value: 'reduce' }] });
  await auth.browser(send, origin);   // the owner's session, so the controls are drawn
  await send('Page.navigate', { url: origin + '/?theme=light#map' });
  await until(() => evaluate(`document.readyState === 'complete' && !!document.getElementById('needs-btn') && !document.getElementById('needs-btn').disabled`), 'the project read', 1200);
  await settled('opened');
  await evaluate(WATCHER);

  // ---- 1. Nothing changed ------------------------------------------------------------------------
  const map = await api('map'), runs = (await api('runs')).runs, requests = (await api('build_requests')).requests;
  const datasets = (await api('definitions', { kind: 'dataset' })).definitions.filter(d => !d.removed);
  const model = (map.models[Math.min(40, map.models.length - 1)] || {}).reference;
  const enc = s => encodeURIComponent(s);
  const places = [
    ['Map', 'map'], ['Map, a model\'s drawer', 'map/' + enc(model)], ['Map, the editor', 'map/' + enc('edit:' + model)], ['Map, the plan view', 'map/' + enc('plan:' + model)],
    ['Data', 'data'], datasets.length ? ['Data, a dataset\'s drawer', 'data/' + enc(datasets[0].reference)] : null,
    ['Train', 'train'], runs.length ? ['Train, a run\'s drawer', 'train/' + enc('run:' + runs[0].id)] : null, requests.length ? ['Train, a build request\'s drawer', 'train/' + enc('request:' + requests[0].id)] : null,
    ['Benchmarks', 'benchmarks'], ['Analysis', 'analysis'], ['Overview', 'overview']
  ].filter(Boolean);
  const skipped = [!datasets.length && 'a dataset\'s drawer (no dataset)', !runs.length && 'a run\'s drawer (no run)', !requests.length && 'a build request\'s drawer (no request)'].filter(Boolean);
  const ALL = ['tabs', 'strip', 'main', 'aside', 'needs-panel'];
  const rows = [];
  async function still(label, cause) {
    const before = await evaluate(`window.__still.scrolls()`), since = Date.now();
    await start();
    if (cause === 'focus') { await evaluate(`window.dispatchEvent(new Event('focus')); true`); await reading(since, WATCHED.concat(['map']), label + ' on focus'); }
    else await reading(since, WATCHED, label + ' on the timer', Math.round((IDLE_MS + 15000) / 100));
    const r = await stopWatch();
    assert.deepEqual(touched(r, ALL), [], label + ', ' + cause + ': nothing is touched');
    assert.equal(r.flash, 0, label + ', ' + cause + ': "Reading…" is never shown');
    assert.deepEqual(r.scrolls, before, label + ', ' + cause + ': every scroll position stays');
    rows.push(label + ' · ' + cause + ': 0 nodes added or removed, ' + Object.keys(before).length + ' scroll positions kept' + (r.counts.strip.readAt ? ', "Read at" ticked' : ''));
    return { r, before };
  }
  for (const [label, place] of places) {
    await hash(place);
    if (place === 'map' || place.startsWith('map/')) await evaluate(`(() => { const t = document.querySelector('#main .tree-map'); if (t) { t.scrollLeft = 2000; t.scrollTop = 30; } const l = document.querySelector('#main .tree-host'); if (l) l.scrollTop = 400; return true; })()`);
    const set = await evaluate(`window.__still.scrollAll()`);
    await pause(200);
    await still(label + ' (' + Object.keys(set).length + ' scrolled)', 'focus');
    if (place === 'train') await still(label, 'timer');
    if (place === 'overview') {
      await press('#needs-btn'); await until(() => evaluate(`!document.getElementById('needs-panel').hidden && !!document.querySelector('#needs-panel .needs')`), 'Needs you open'); await pause(200);
      await evaluate(`document.getElementById('needs-panel').scrollTop = 20; true`);
      for (const cause of ['focus', 'timer']) { const { r } = await still('Overview with Needs you open', cause); assert.ok(r.needsOpen, 'Needs you stays open'); }
      await press('#needs-btn'); await until(() => evaluate(`document.getElementById('needs-panel').hidden`), 'Needs you closed');
    }
  }
  check('1. Nothing changed (' + places.length + ' places' + (skipped.length ? '; not on this project: ' + skipped.join(', ') : '') + '):\n    ' + rows.join('\n    '));

  if (!labRoot) {
    // ---- 2. Something changed elsewhere ----------------------------------------------------------
    await hash('train');
    const trainScroll = await evaluate(`(() => { const m = document.getElementById('main'); m.scrollTop = Math.min(140, m.scrollHeight - m.clientHeight); return [m.scrollLeft, m.scrollTop]; })()`);
    assert.ok(trainScroll[1] > 0, 'Train scrolls at this size: ' + JSON.stringify(trainScroll));
    const focusKey = await evaluate(`(() => { const b = [...document.querySelectorAll('#main .act-group button')].find(b => { const r = b.getBoundingClientRect(); return r.top > 120 && r.bottom < innerHeight; }) || document.querySelector('#main .act-group button'); b.focus({ preventScroll: true }); return b.dataset.key; })()`);
    assert.ok(focusKey, 'A control of Train is focused');
    const count0 = await needsCount();
    await start(); const asked = Date.now();
    const second = await api('request_build', { targets: ['recipes/steady'] }, agent);
    assert.equal(second.state, 'awaiting-approval');
    await until(async () => (await needsCount()) === count0 + 1 && await evaluate(`!!document.querySelector('#main ${byKey('open-request:' + second.id)}')`), 'the strip and Train show the request', Math.round((IDLE_MS + 10000) / 100));
    const shownAfter = Date.now() - asked;
    await settled('shown'); await pause(300);
    const r2 = await stopWatch();
    assert.equal(r2.flash, 0, '"Reading…" is never shown on Train');
    assert.deepEqual(r2.scrolls.main, trainScroll, 'The scroll of Train stays');
    assert.equal(await evaluate(`document.activeElement && document.activeElement.dataset.key`), focusKey, 'The focus stays on the control');
    assert.ok(r2.counts.main.added > 0 && r2.counts.tabs.added === 0, 'Train was drawn again in place, the tab bar was not: ' + JSON.stringify([r2.counts.main, r2.counts.tabs]));
    await send('Emulation.setDeviceMetricsOverride', { width: WIDTH, height: 420, deviceScaleFactor: 1, mobile: false });   // so the request's drawer scrolls
    await hash('train/' + enc('request:' + second.id));
    assert.equal(await drawerState(), 'awaiting approval');
    const drawerScroll = await evaluate(`(() => { const d = document.getElementById('drawer'); d.scrollTop = Math.min(60, d.scrollHeight - d.clientHeight); return d.scrollTop; })()`);
    assert.ok(drawerScroll > 0, 'The request\'s drawer scrolls at this size');
    await start();
    await api('approve_build', { request: second.id });
    const seen = await until(async () => { const s = await drawerState(); return s !== 'awaiting approval' ? s : null; }, 'the drawer shows the request approved', Math.round((IDLE_MS + 10000) / 100));
    await settled('approved'); await pause(300);
    const r3 = await stopWatch();
    assert.equal(r3.flash, 0, '"Reading…" is never shown in the drawer');
    assert.equal(r3.scrolls.drawer[1], drawerScroll, 'The drawer keeps its scroll');
    await send('Emulation.setDeviceMetricsOverride', { width: WIDTH, height: HEIGHT, deviceScaleFactor: 1, mobile: false });
    check('2. A second session asked for a build (' + second.id.slice(0, 8) + '): within ' + (shownAfter / 1000).toFixed(1) + ' s (one reading) the strip said "Needs you · ' + (count0 + 1) + '" and Train listed it, with no "Reading…", the scroll (' + trainScroll.join(',') + ') and the focus (' + focusKey + ') kept; approved from outside the page, its drawer turned to "' + seen + '" in place, its scroll (' + drawerScroll + ') kept');

    // ---- 3. A build runs ------------------------------------------------------------------------------
    const run = await until(async () => (await api('build_request', { request: second.id })).runs.find(x => x.state === 'running'), 'the steady run running', 600);
    await hash('train/' + enc('run:' + run.id));
    const stripWidths = new Set(), drawerLines = new Set();
    for (let i = 0; i < 40 && (stripWidths.size < 3 || drawerLines.size < 3); i++) {
      const v = await evaluate(`(() => { const s = document.querySelector('#strip .hair i'), p = document.querySelector('#aside .progress-line'); return [s ? s.style.width : null, p ? p.textContent : null]; })()`);
      if (v[0]) stripWidths.add(v[0]); if (v[1]) drawerLines.add(v[1]);
      await pause(500);
    }
    assert.ok(stripWidths.size >= 2, 'The strip\'s hairline moves: ' + [...stripWidths]);
    assert.ok(drawerLines.size >= 2, 'The run\'s drawer reads on: ' + [...drawerLines]);
    const logLines = await evaluate(`document.querySelector('#aside pre[data-log="stdout"]').textContent.split('\\n').length`);
    // The run's row in Train's list reads on too, in place: its line changes and no node is added or removed.
    await hash('train');
    const rowLine = `(() => { const l = document.querySelector('#main button.row.run[data-run=${JSON.stringify(run.id)}] .sub.live'); return l ? l.textContent : null; })()`;
    await until(() => evaluate(rowLine), 'the run\'s row shows its progress', 100);
    await start();
    const rowLines = new Set();
    for (let i = 0; i < 30 && rowLines.size < 3; i++) { const v = await evaluate(rowLine); if (v) rowLines.add(v); await pause(500); }
    const rRow = await stopWatch();
    assert.ok(rowLines.size >= 2, 'The run\'s row in Train\'s list reads on: ' + [...rowLines]);
    assert.equal(rRow.counts.main.added + rRow.counts.main.removed + rRow.fresh.main, 0, 'Train\'s list gains no node while its row reads on: ' + JSON.stringify(rRow.counts.main));
    assert.equal(rRow.flash, 0, '"Reading…" is never shown on Train while the run runs');
    // Short and zoomed in, so the map and the list scroll with room to spare when the strip changes height as the run ends.
    await send('Emulation.setDeviceMetricsOverride', { width: WIDTH, height: 520, deviceScaleFactor: 1, mobile: false });
    await hash('map/' + enc('recipes/steady'));
    for (let i = 0; i < 3; i++) { await press('#main .zoomctl button[aria-label="Zoom in"]'); await settled('zoom'); }
    const stripRunning = await evaluate(`document.getElementById('strip').offsetHeight`);
    await evaluate(`(() => { const set = (e, x, y) => { e.scrollLeft = Math.max(0, Math.min(x, e.scrollWidth - e.clientWidth - 60)); e.scrollTop = Math.max(0, Math.min(y, e.scrollHeight - e.clientHeight - 60)); }; set(document.querySelector('#main .tree-map'), 120, 20); set(document.querySelector('#main .tree-host'), 0, 60); return true; })()`);
    const mapScroll = await evaluate(`[document.querySelector('#main .tree-map'), document.querySelector('#main .tree-host')].map(e => [Math.round(e.scrollLeft), Math.round(e.scrollTop)])`);
    assert.ok(mapScroll.some(([x, y]) => x || y), 'The map or the list scrolls at this size: ' + JSON.stringify(mapScroll));
    const planned = () => evaluate(`/\\bplanned\\b/.test(document.querySelector('#main .tree-map .node[data-id="recipes/steady"]').getAttribute('class'))`);
    assert.ok(await planned(), 'The steady model is drawn never built while it runs');
    await start();
    // A sample of the page taken before the server still says running was taken while the run ran.
    let last = null, samples = 0;
    await until(async () => {
      const v = await evaluate(`(() => { const n = document.querySelector('#main .tree-map .node[data-id="recipes/steady"]'); return { planned: !!n && /\\bplanned\\b/.test(n.getAttribute('class')), main: window.__still.peek().counts.main }; })()`);
      const st = (await api('run', { run: run.id })).state;
      if (['queued', 'running'].includes(st)) { samples++; assert.equal(v.main.added + v.main.removed, 0, 'The main area of the Map gains no node while the run runs: ' + JSON.stringify(v.main)); last = v; return false; }
      return !v.planned;
    }, 'the steady model drawn built', 1500);
    await until(async () => (await drawerState()).startsWith('built'), 'its drawer says built', 200);
    await settled('built');
    const r4 = await stopWatch();
    const after = await evaluate(`[document.querySelector('#main .tree-map'), document.querySelector('#main .tree-host')].map(e => [Math.round(e.scrollLeft), Math.round(e.scrollTop)])`);
    const stripEnded = await evaluate(`document.getElementById('strip').offsetHeight`);
    assert.deepEqual(after, mapScroll, 'The map and the list keep their scroll when the map is drawn again');
    await send('Emulation.setDeviceMetricsOverride', { width: WIDTH, height: HEIGHT, deviceScaleFactor: 1, mobile: false });
    assert.equal(r4.flash, 0, '"Reading…" is never shown while the run ends');
    assert.equal((await api('run', { run: run.id })).state, 'succeeded');
    check('3. While the steady build ran, the strip\'s hairline read ' + [...stripWidths].join(', ') + ' and the run\'s drawer read on (' + drawerLines.size + ' progress lines, ' + logLines + ' log lines); its row in Train\'s list read on in place (' + rowLines.size + ' lines, no node added or removed); on the Map tab the main area gained no node over ' + samples + ' samples until the run ended (attributes changed: ' + (last ? last.main.attrs : 0) + '); then the model was drawn built, the map and the list kept their scroll ' + JSON.stringify(after) + ' (the strip ' + stripRunning + ' px high while it ran, ' + stripEnded + ' px after), and "Reading…" was never shown');

    // ---- 4. The editor is left alone ------------------------------------------------------------------
    await hash('map/' + enc('edit:recipes/fit-a'));
    await press(byKey('editor:recipes/fit-a:description'));
    await send('Input.insertText', { text: 'Typed here and not kept.' });
    await evaluate(`(() => { const e = document.activeElement; e.setSelectionRange(5, 5); return true; })()`);
    const typed = await evaluate(`({ key: document.activeElement.dataset.key, value: document.activeElement.value, caret: document.activeElement.selectionStart })`);
    const count1 = await needsCount();
    await start();
    const third = await api('request_build', { targets: ['recipes/fit-a'] }, agent);
    await until(async () => (await needsCount()) === count1 + 1, 'the strip shows the second request', Math.round((IDLE_MS + 10000) / 100));
    await settled('third'); await pause(300);
    const since = Date.now(); await evaluate(`window.dispatchEvent(new Event('focus')); true`); await reading(since, WATCHED.concat(['map']), 'focus with the editor');
    const r5 = await stopWatch();
    assert.deepEqual(touched(r5, ['aside']), [], 'The editor\'s drawer is not touched');
    assert.ok(r5.counts.strip.added > 0, 'The strip was drawn again');
    assert.deepEqual(await evaluate(`({ key: document.activeElement.dataset.key, value: document.activeElement.value, caret: document.activeElement.selectionStart })`), typed, 'The typed text, the focus and the caret stay');
    check('4. With "' + typed.value + '" typed into fit-a\'s description (caret at ' + typed.caret + '), a second request (' + third.id.slice(0, 8) + ') reached the strip and the window regained focus: the drawer was not touched, the text, focus and caret are there');
    void firstAsk;

    // ---- 5. A reading that fails leaves the page alone ------------------------------------------------
    await hash('overview');
    await evaluate(`window.__still.scrollAll()`); await pause(200);
    const before5 = await evaluate(`window.__still.scrolls()`);
    await start();
    offline = true;
    await send('Network.emulateNetworkConditions', { offline: true, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
    await evaluate(`window.dispatchEvent(new Event('focus')); true`);
    await until(() => evaluate(`/Not read/.test(document.getElementById('strip').textContent)`), 'the strip says the project was not read', 200);
    const said = await evaluate(`document.getElementById('strip').textContent.trim().replace(/\\s+/g, ' ')`);
    await send('Network.emulateNetworkConditions', { offline: false, latency: 0, downloadThroughput: -1, uploadThroughput: -1 });
    await pause(500); offline = false;
    const back = Date.now(); await evaluate(`window.dispatchEvent(new Event('focus')); true`); await reading(back, WATCHED.concat(['map']), 'focus once the server answers again');
    await until(() => evaluate(`!/Not read/.test(document.getElementById('strip').textContent)`), 'the strip says where the project stands again', 100);
    const r6 = await stopWatch();
    assert.deepEqual(touched(r6, ['tabs', 'main', 'aside', 'needs-panel']), [], 'A reading that failed, and the one after it, touch nothing but the strip');
    assert.equal(r6.flash, 0, '"Reading…" is never shown when a reading fails');
    assert.deepEqual(r6.scrolls, before5, 'Every scroll position stays when a reading fails');
    check('5. Cut off from the server, the page kept Overview as it was and the strip said: "' + said.slice(0, 160) + '"; when the server answered again the strip said where the project stands, and nothing else was touched');
  }

  // ---- Nothing failed ------------------------------------------------------------------------------
  assert.deepEqual(errors, [], 'Script errors');
  assert.deepEqual(failures, [], 'Failed requests');
  check('No script error, no failed request');
  fs.writeFileSync(path.join(report, 'receipt.json'), JSON.stringify({ status: 'pass', folder, checks }, null, 2) + '\n');
  console.log('Receipt in ' + report);
})().catch(async error => {
  process.exitCode = 1;
  console.error(error); if (serverErrors) console.error('Server:', serverErrors.slice(-4000));
  console.error('Script errors:', JSON.stringify(errors)); console.error('Failed requests:', JSON.stringify(failures));
  try { if (evaluate) console.error('Page:', (await evaluate('document.body.innerText')).slice(0, 2000)); } catch (_) { /* the page is gone */ }
  fs.writeFileSync(path.join(report, 'failure.json'), JSON.stringify({ status: 'failed', error: String(error && error.stack || error), checks, errors, failures }, null, 2) + '\n');
}).finally(async () => {
  try { session?.close(); } catch (_) { /* closed */ }
  for (const child of children.reverse()) await stop(child);
  if (owned) try { dropOwned(...owned); } catch (error) { console.error('Dropping the disposable schemas failed:', error.message); process.exitCode = 1; }
  try { execFileSync('chmod', ['-R', 'u+w', temporary]); } catch (_) { /* nothing was made read-only */ }   // finished runs leave their directories read-only
  fs.rmSync(temporary, { recursive: true, force: true });
});
