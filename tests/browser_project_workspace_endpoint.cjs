'use strict';
// The Pumas endpoint on the page (docs/plans/definition-first-projects/spec-d5.md sections 5 and 7, slice D5c) in a
// headless browser, the owner signed in, no GPU. Every request for a model goes to a fake endpoint that this check
// starts itself (tests/browser_fake_pumas.py, built on tests/fake_pumas_typed.py from the released 0.8.0 contract);
// no real Pumas is contacted. Tuldok is started with gateway_discovery.listening_endpoints replaced by a list holding
// the fake's port alone, so "Find on this machine" asks only the fake and this machine's listeners are never scanned.
// The settings file is TULDOK_SETTINGS when it is set (else one in a temporary directory), written empty first.
// The fixture is a project of its own in Git: datasets/notes imports three texts and a PNG, datasets/subjects two lines
// of prompts; annotations/summaries (text) and annotations/topics (class) are tasks on datasets/notes.
//   1. No endpoint set: the Train tab says so; the Generate form says why it cannot be used and goes to the endpoint.
//   2. The endpoint set from the page: an address that is not loopback refused with the server's sentence, one that does
//      not answer refused; Find on this machine lists the fake; the fake's address accepted. Its seven models listed
//      with what each takes and makes, an unavailable capability with its reason.
//   3. Generate: only text and images offered, the models that make each, the option fields carrying the advertised
//      bounds, the seed shown only for a capability that takes one; a text dataset and an image dataset from a dataset
//      of prompts kept, written by Save exactly as expected, accepted by `check`.
//   4. The text dataset planned, requested and built through the page against the fake; its records in the dataset view.
//   5. Suggest: cancelled while the model answers (the answer dropped); asked, shown as a suggestion naming the model,
//      changed and kept; after Save the line on disk carries `from`. A refused suggestion (an answer that is not a term)
//      leaves the form as it was. Suggest for this page keeps drafts and reports its counts.
//   6. With text typed in the Generate form, the endpoint's address and the annotation form, the window regaining focus
//      and a reading on the timer add, remove and change no node, and the text is there.
//   7. Screenshots in light and dark at 1440 by 900 and 1000 by 800 (with --shots <dir>, written there too).
// It fails on any script error, and on any failed request but the refusals it asks for.
//   node tests/browser_project_workspace_endpoint.cjs [--shots <dir>]
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
const RIGHTS = 'Made by a model for this check; anything may be done with it.';
// Tuldok, with the scanner of find_endpoints answering the fake's port alone (argv[1]).
const LAUNCH = `import runpy, sys
import gateway_discovery
port = int(sys.argv[1])
gateway_discovery.listening_endpoints = lambda: [('127.0.0.1', port)]
sys.argv = ['app.py'] + sys.argv[2:]
runpy.run_path('app.py', run_name='__main__')`;

const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'tuldok-endpoint-browser-'));
const report = qaDirectory(root, 'project-workspace-endpoint');
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
const tiles = () => evaluate(`[...document.querySelectorAll('#main .ann-rec')].map(b => ({ id: b.dataset.id, state: b.dataset.state, pressed: b.getAttribute('aria-pressed') === 'true' }))`);
const lines = (folder, name) => { const file = path.join(folder, 'annotations', name + '.jsonl'); return fs.existsSync(file) ? fs.readFileSync(file, 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l)) : []; };

// The watcher of browser_project_workspace_still.cjs.
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

let folder;
(async () => {
  // ---- The fake endpoint, the fixture and Tuldok -------------------------------------------------------------------
  fake = launch(python, [path.join(root, 'tests', 'browser_fake_pumas.py')], { cwd: root, stdio: ['pipe', 'pipe', 'pipe'] });
  let fakeErrors = ''; fake.stderr.on('data', chunk => { fakeErrors += chunk; });
  fakeLines = readline.createInterface({ input: fake.stdout });
  const base = await Promise.race([once(fakeLines, 'line').then(([line]) => line.trim()), once(fake, 'exit').then(() => { throw Error('The fake endpoint exited: ' + fakeErrors); })]);
  assert.match(base, /^http:\/\/127\.0\.0\.1:\d+$/);
  const fakePort = Number(base.split(':').pop());

  const repo = path.join(temporary, 'fixture'), code = path.join(repo, 'code'); folder = path.join(repo, 'project');
  for (const d of ['datasets', 'annotations']) fs.mkdirSync(path.join(folder, d), { recursive: true });
  fs.mkdirSync(path.join(code, 'notes'), { recursive: true }); fs.mkdirSync(path.join(code, 'subjects'), { recursive: true });
  fs.writeFileSync(path.join(folder, 'tuldok.json'), JSON.stringify({ format: 'tuldok_project_v1', id: require('node:crypto').randomUUID().replace(/-/g, ''), name: 'Endpoint check', code_root: '../code' }, null, 2) + '\n');
  fs.writeFileSync(path.join(code, 'notes', 'a.txt'), 'A long text about a dog that runs after a red ball in the park.\n');
  fs.writeFileSync(path.join(code, 'notes', 'b.txt'), 'Rain is expected over the hills by the evening.\n');
  fs.writeFileSync(path.join(code, 'notes', 'c.txt'), 'The train to the coast leaves at nine.\n');
  execFileSync(python, ['-c', 'import sys; from PIL import Image; Image.new("RGB", (48, 32), (200, 120, 40)).save(sys.argv[1])', path.join(code, 'notes', 'photo.png')]);
  fs.writeFileSync(path.join(code, 'subjects', 'subjects.txt'), 'a red ball\na blue car\n');
  const doc = o => JSON.stringify(Object.assign({ format: 'tuldok_definition_v1' }, o), null, 2) + '\n';
  fs.writeFileSync(path.join(folder, 'datasets', 'notes.json'), doc({ kind: 'dataset', title: 'Notes and a photo', run: { step: 'import', settings: { source: 'notes', rights: 'Written for this check; free to use.' } } }));
  fs.writeFileSync(path.join(folder, 'datasets', 'subjects.json'), doc({ kind: 'dataset', title: 'Subjects to draw', run: { step: 'import', settings: { source: 'subjects', rights: 'Written for this check; free to use.', lines: true } } }));
  fs.writeFileSync(path.join(folder, 'annotations', 'summaries.json'), doc({ kind: 'annotation', title: 'Summaries', dataset: 'datasets/notes', task: 'text' }));
  fs.writeFileSync(path.join(folder, 'annotations', 'topics.json'), doc({ kind: 'annotation', title: 'Topics', dataset: 'datasets/notes', task: 'class', vocabulary: ['animals', 'weather', 'travel'] }));
  const git = ['-c', 'user.name=Tuldok Test', '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false', '-c', 'init.defaultBranch=main', '-C', repo];
  const commit = message => { execFileSync('git', [...git, 'add', '-A']); execFileSync('git', [...git, 'commit', '-q', '-m', message]); };
  execFileSync('git', [...git, 'init', '-q']); commit('The fixture.');
  const home = process.env.TULDOK_PROJECT_HOME || path.join(temporary, 'home'), catalog = path.join(temporary, 'catalog'); fs.mkdirSync(home, { recursive: true });
  const settingsFile = process.env.TULDOK_SETTINGS || path.join(temporary, 'settings.json');
  fs.mkdirSync(path.dirname(settingsFile), { recursive: true }); fs.writeFileSync(settingsFile, JSON.stringify({ format: 'tuldok_settings_v1' }) + '\n', { mode: 0o600 });
  const env = { ...process.env, TULDOK_PROJECT_HOME: home, TULDOK_SETTINGS: settingsFile };
  owned = [folder, catalog]; dropOwned(folder, catalog);
  const cli = (...args) => execFileSync(python, ['-m', 'tuldok_project', ...args], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] }).toString();
  assert.match(cli('check', folder), /^0 errors/m);
  cli('build', folder, 'datasets/notes', '--yes'); cli('build', folder, 'datasets/subjects', '--yes');
  let output = '';
  server = launch(python, ['-c', LAUNCH, String(fakePort), '--port', '0', '--data', catalog, '--project-folder', folder], { cwd: root, env: { ...env, PYTHONUNBUFFERED: '1' }, stdio: ['ignore', 'pipe', 'pipe'] });
  server.stdout.on('data', chunk => { output += chunk; }); server.stderr.on('data', chunk => { serverErrors += chunk; });
  const port = await until(() => { if (server.exitCode !== null) throw Error('Tuldok exited: ' + serverErrors); return output.match(/127\.0\.0\.1:(\d+)/)?.[1]; }, 'Tuldok start-up', 3000);
  origin = 'http://127.0.0.1:' + port;
  auth = authenticatedFixture(); await auth.register(origin, catalog, root);

  const browser = launch(findBrowser(), ['--headless', '--no-sandbox', '--disable-gpu', '--no-first-run', '--hide-scrollbars', '--remote-debugging-port=0', '--window-size=1440,900', '--user-data-dir=' + path.join(temporary, 'browser'), 'about:blank'], { stdio: 'ignore', env: { ...process.env, XDG_CONFIG_HOME: temporary, XDG_CACHE_HOME: temporary } });
  const debugPort = await waitForDebugger(browser, path.join(temporary, 'browser', 'DevToolsActivePort'));
  const target = (await (await fetch('http://127.0.0.1:' + debugPort + '/json')).json()).find(item => item.type === 'page');
  socket = new WebSocket(target.webSocketDebuggerUrl); await once(socket, 'open');
  const ASKED = /\/api\/project\/(set_endpoint|suggest_annotation)$/;   // the refusals this check asks for
  session = cdpSession(socket, { timeoutMs: 60000, onEvent: event => {
    network(event);
    if (event.method === 'Runtime.exceptionThrown') errors.push(event.params.exceptionDetails.exception?.description || event.params.exceptionDetails.text);
    if (event.method === 'Runtime.consoleAPICalled' && event.params.type === 'error') errors.push(event.params.args.map(a => a.value ?? a.description).join(' '));
    if (event.method === 'Log.entryAdded' && event.params.entry.level === 'error' && !ASKED.test(event.params.entry.url || '')) errors.push(event.params.entry.text + ' ' + (event.params.entry.url || ''));
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
  const drawerText = () => text('#aside');
  const settingsNow = () => JSON.parse(fs.readFileSync(settingsFile, 'utf8'));

  // ---- 1. No endpoint set ----------------------------------------------------------------------------------------------
  await load('light', 'train');
  const row = await text('#main [data-key="open-endpoint"]');
  assert.match(row, /not set/); assert.match(row, /No endpoint set/); assert.match(row, /No Pumas endpoint is set on this machine/);
  assert.equal(await evaluate(`document.querySelectorAll('#main .ep-model').length`), 0);
  await hash('data');
  await press(byKey('data:new:generate'));
  await until(() => evaluate(`!!document.querySelector('#aside .gen-none')`), 'the Generate form without an endpoint');
  const none = await drawerText();
  assert.match(none, /No Pumas endpoint is set on this machine, so there is nothing to generate with/);
  assert.equal(await evaluate(`!!document.querySelector('#aside [data-key="newgenerate:field:title"]')`), false, 'No field is offered');
  await press(byKey('gen:endpoint'));
  await until(() => evaluate(`location.hash === '#train/endpoint' && !!document.querySelector('#aside [data-key="endpoint:set:field:address"]')`), 'the endpoint\'s drawer on Train');
  await settled('endpoint drawer');
  check('1. No endpoint set: the Train tab says "' + row.split('\n').slice(0, 3).join(' · ') + '"; the Generate form says "' + none.match(/No Pumas endpoint[^\n]*/)[0] + '" and its button opens the endpoint on the Train tab');

  // ---- 2. The endpoint set from the page ----------------------------------------------------------------------------
  const refusal = async () => until(() => text('#aside [data-group="endpoint:set"] .refusal'), 'the refusal beside Set');
  await type(byKey('endpoint:set:field:address'), 'http://192.168.1.5:8765');
  await press(byKey('endpoint:set:set')); await kept('a remote address');
  const remote = await refusal();
  assert.match(remote, /'http:\/\/192\.168\.1\.5:8765' is not an address Tuldok can reach Pumas at: Pumas 0\.8\.0 serves on a numeric loopback address/);
  assert.equal(await value(byKey('endpoint:set:field:address')), 'http://192.168.1.5:8765', 'What was typed stays');
  await shot('light-1440-train-refusal');
  const closed = await new Promise(resolve => { const s = require('node:net').createServer(); s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => resolve(p)); }); });
  await type(byKey('endpoint:set:field:address'), 'http://127.0.0.1:' + closed);
  await press(byKey('endpoint:set:set')); await kept('an address that does not answer');
  const silent = await refusal();
  assert.match(silent, new RegExp('The Pumas endpoint at http://127\\.0\\.0\\.1:' + closed + ' did not answer, so it was not set'));
  assert.equal(settingsNow().pumas_endpoint, undefined, 'Nothing was set');
  await press(byKey('endpoint:find:find')); await kept('found');
  const found = await until(() => text('#aside .ep-found'), 'what Find found');
  assert.match(found, new RegExp(base.replace(/\./g, '\\.') + '\\nPumas 0\\.8\\.0 · pumas-rpc'), 'Find lists the fake: ' + found);
  await type(byKey('endpoint:set:field:address'), base);
  await press(byKey('endpoint:set:set')); await kept('the fake set');
  await until(async () => /answers/.test(await text('#main [data-key="open-endpoint"]') || ''), 'the endpoint answers');
  assert.equal(settingsNow().pumas_endpoint, base, 'The settings file holds the address');
  assert.equal(await evaluate(`!!document.querySelector('#aside [data-group="endpoint:set"] .refusal')`), false, 'The refusal is gone');
  const models = await evaluate(`[...document.querySelectorAll('#main .ep-model')].map(li => ({ id: li.dataset.model + ' · ' + li.dataset.profile, text: li.innerText }))`);
  assert.deepEqual(models.map(m => m.id), ['controlled-vision · vision-cpu', 'controlled-vision · vision-gpu', 'controlled-image · controlled-image-cpu', 'writer · writer-cpu', 'painter · painter-gpu', 'decider · decider-cpu', 'listener · listener-cpu']);
  const of = id => models.find(m => m.id === id).text;
  assert.match(of('writer · writer-cpu'), /Takes text · makes text/); assert.match(of('writer · writer-cpu'), /A dataset of: texts by chat_generation \(max_tokens 1 to 4,096, temperature 0 to 2, top_p 0 to 1\)/);
  assert.match(of('writer · writer-cpu'), /Unavailable: image_generation \(unsupported_adapter\)/);
  assert.match(of('painter · painter-gpu'), /A dataset of: images by image_generation \(width 1 to 4,294,967,295, height 1 to 4,294,967,295\), with a seed/);
  assert.match(of('controlled-vision · vision-gpu'), /No dataset can be made with it/); assert.match(of('controlled-vision · vision-gpu'), /chat_generation \(runtime_unavailable\)/);
  assert.match(of('decider · decider-cpu'), /Takes text, image and audio · makes json/);
  assert.match(of('listener · listener-cpu'), /Available: audio_transcription \(pcm_s16le, pcm_f32le → text\)/);
  assert.match(await text('#main [data-key="open-endpoint"]'), /Pumas 0\.8\.0 · 7 models served/);
  check('2. The endpoint set from the page: "' + remote.split('\n')[0].slice(0, 90) + '…" and "' + silent.split('\n')[0].slice(0, 70) + '…" refused beside Set, the typed address kept; Find on this machine listed ' + base + ' (Pumas 0.8.0); the fake\'s address accepted and written to the settings file; its 7 models listed with what each takes and makes, unavailable capabilities with their reasons');

  // ---- 3. Generate --------------------------------------------------------------------------------------------------
  await hash('data');
  await press(byKey('data:new:generate'));
  await until(() => evaluate(`!!document.querySelector('#aside [data-key="newgenerate:field:title"]')`), 'the Generate form');
  await settled('generate form');
  assert.deepEqual(await options('#aside [data-key="newgenerate:field:make"]'), ['text', 'image'], 'Only what some served model makes');
  assert.deepEqual(await options('#aside [data-key="newgenerate:field:model"]'), ['controlled-vision\u0000vision-cpu', 'writer\u0000writer-cpu'], 'The models that make texts');
  assert.match(await drawerText(), /The profile vision-cpu is written with the model: the endpoint requires it/);
  await choose(byKey('newgenerate:field:model'), 'writer\u0000writer-cpu');
  const field = name => evaluate(`(() => { const i = document.querySelector('#aside [data-key="newgenerate:field:${name}"]'); return i ? { min: i.min, max: i.max } : null; })()`);
  assert.deepEqual(await field('opt:max_tokens'), { min: '1', max: '4096' }); assert.deepEqual(await field('opt:temperature'), { min: '0', max: '2' }); assert.deepEqual(await field('opt:top_p'), { min: '0', max: '1' });
  assert.equal(await field('seed'), null, 'No seed for a capability that takes none');
  assert.doesNotMatch(await drawerText(), /The profile/);
  await type(byKey('newgenerate:field:title'), 'Poem lines');
  await type(byKey('newgenerate:field:prompt'), 'Write line {n} of a short poem.');
  await type(byKey('newgenerate:field:count'), '3');
  await type(byKey('newgenerate:field:opt:max_tokens'), '64'); await type(byKey('newgenerate:field:opt:temperature'), '0.7');
  await type(byKey('newgenerate:field:rights'), RIGHTS);
  await shot('light-1440-generate-text');
  await press(byKey('newgenerate:keep')); await kept('poem lines kept');
  await until(() => evaluate(`location.hash === '#data/' + encodeURIComponent('datasets/poem-lines')`), 'the new dataset\'s drawer'); await settled('poem drawer');
  await press(byKey('data:new:generate'));
  await until(() => evaluate(`!!document.querySelector('#aside [data-key="newgenerate:field:title"]')`), 'the Generate form again'); await settled('generate again');
  await choose(byKey('newgenerate:field:make'), 'image'); await settled('image');
  assert.deepEqual(await options('#aside [data-key="newgenerate:field:model"]'), ['controlled-image\u0000controlled-image-cpu', 'painter\u0000painter-gpu'], 'The models that make images');
  await choose(byKey('newgenerate:field:model'), 'painter\u0000painter-gpu');
  assert.deepEqual(await field('seed'), { min: '0', max: '4294967295' }, 'The seed of a capability that takes one');
  assert.deepEqual(await field('opt:width'), { min: '1', max: '4294967295' }); assert.deepEqual(await field('opt:height'), { min: '1', max: '4294967295' });
  assert.equal(await field('opt:max_tokens'), null);
  await type(byKey('newgenerate:field:title'), 'Pictures of subjects');
  await press(byKey('newgenerate:field:from-prompts')); await settled('from prompts');
  assert.match(await drawerText(), /\{text\} by the text of the prompting record/);
  await choose(byKey('newgenerate:field:prompts'), 'datasets/subjects');
  await type(byKey('newgenerate:field:per'), '2');
  await type(byKey('newgenerate:field:prompt'), 'A picture of {text}, number {n}.');
  await type(byKey('newgenerate:field:seed'), '100'); await type(byKey('newgenerate:field:opt:width'), '64');
  await type(byKey('newgenerate:field:rights'), RIGHTS);
  await press(byKey('newgenerate:keep')); await kept('height missing');
  assert.match(await text('#aside [data-group="newgenerate"] .refusal') || '', /height is required/, 'An image needs its height');
  await type(byKey('newgenerate:field:opt:height'), '32');
  assert.equal(await value(byKey('newgenerate:field:title')), 'Pictures of subjects', 'Nothing typed was lost');
  await shot('light-1440-generate-image');
  await press(byKey('newgenerate:keep')); await kept('pictures kept');
  await until(() => evaluate(`location.hash === '#data/' + encodeURIComponent('datasets/pictures-of-subjects')`), 'the image dataset\'s drawer'); await settled('pictures drawer');
  await press(byKey('save:save')); await kept('saved the datasets');
  const want = {
    'poem-lines': { format: 'tuldok_definition_v1', kind: 'dataset', title: 'Poem lines', run: { step: 'generate', settings: { make: 'text', model: 'writer', prompt: 'Write line {n} of a short poem.', count: 3, options: { max_tokens: 64, temperature: 0.7 }, rights: RIGHTS } } },
    'pictures-of-subjects': { format: 'tuldok_definition_v1', kind: 'dataset', title: 'Pictures of subjects', run: { step: 'generate', inputs: { prompts: 'datasets/subjects' }, settings: { make: 'image', model: 'painter', prompt: 'A picture of {text}, number {n}.', per: 2, seed: 100, options: { width: 64, height: 32 }, rights: RIGHTS } } }
  };
  for (const [name, d] of Object.entries(want)) assert.equal(fs.readFileSync(path.join(folder, 'datasets', name + '.json'), 'utf8'), JSON.stringify(d, null, 2) + '\n', 'The definition written for ' + name);
  const checked = cli('check', folder);
  assert.match(checked, /^0 errors/m, checked);
  check('3. Generate offered text and image only, the models making each, the options with the advertised bounds as minimum and maximum (max_tokens 1–4096 …, width 1–4294967295), the seed only for image_generation, the profile line for controlled-vision; a missing height refused with nothing lost; datasets/poem-lines and datasets/pictures-of-subjects written by Save exactly as expected; `check` reports ' + checked.trim().split('\n').pop().replace(/ in .*/, ''));

  // ---- 4. Built through the page, its records in the dataset view ----------------------------------------------------
  commit('The generated datasets.');
  await hash('data/' + encodeURIComponent('datasets/poem-lines'));
  await press(byKey('dataedit:datasets/poem-lines:plan'));
  await until(() => evaluate(`location.hash === '#train/' + encodeURIComponent('plan:datasets/poem-lines') && !!document.querySelector('#aside .plan-view')`), 'the plan of poem-lines'); await settled('plan');
  const plan = await drawerText();
  assert.match(plan, /1 step to build/); assert.match(plan, /can be built/);
  await press(byKey('request:plan:datasets/poem-lines:request')); await kept('requested');
  const product = await until(async () => { const p = (await api('products', { reference: 'datasets/poem-lines' })).products; return p.length ? p[0] : null; }, 'the generated product', 600);
  const posts = (await tell({ posts: true })).posts.filter(p => p.input === 'text');
  assert.deepEqual(posts.map(p => [p.model, p.capability]), [['writer', 'chat_generation'], ['writer', 'chat_generation'], ['writer', 'chat_generation']], 'Three requests to the fake');
  await hash('data/' + encodeURIComponent('inside:datasets/poem-lines'));
  await until(() => evaluate(`document.querySelectorAll('#main .rec').length === 3`), 'the three records in the dataset view');
  const ids = await evaluate(`[...document.querySelectorAll('#main .rec')].map(t => t.dataset.id)`);
  assert.deepEqual(ids, ['g000001', 'g000002', 'g000003']);
  await press('#main .rec[data-id="g000002"]');
  await until(async () => (await text('#main .viewer .iv-text')) === 'made: Write line 2 of a short poem.', 'the record\'s text in the viewer');
  check('4. datasets/poem-lines planned from its drawer ("1 step to build"), requested and built through the page against the fake (3 requests to writer by chat_generation; run ' + product.run_id.slice(0, 8) + '); the dataset view lists g000001 to g000003 and shows "made: Write line 2 of a short poem."');

  // ---- 5. Suggestions -------------------------------------------------------------------------------------------------
  await hash('annotate');
  const pickTask = async ref => { if ((await value(byKey('ann:task'))) !== ref) { await choose(byKey('ann:task'), ref); await settled('task ' + ref); } };
  const open = async id => { await press(byKey('ann-rec-' + id)); await until(() => evaluate(`(() => { const h = document.querySelector('#main .ann-form h2'); return !!h && h.textContent === ${JSON.stringify(id)}; })()`), 'the form of ' + id); await settled(id); };
  const mark = () => text('#main .ann-form .ann-sugmark');
  await pickTask('annotations/summaries'); await open('a.txt');
  assert.deepEqual(await options('#main [data-key="ann:suggest-model"]'), ['controlled-vision\u0000vision-cpu', 'writer\u0000writer-cpu'], 'The models that suggest a summary of a text');
  await choose(byKey('ann:suggest-model'), 'writer\u0000writer-cpu');
  // Cancelled while the model answers: the answer is dropped.
  await tell({ answer: 'An answer that comes too late.', modes: ['hold'] });
  await press(byKey('ann:suggest'));
  await until(async () => (await text('#main [data-key="ann:suggest"]')) === 'Asking writer…', 'the button says the model is asked');
  assert.equal(await evaluate(`document.activeElement.dataset.key`), 'ann:suggest-cancel', 'The focus is on Cancel');
  await press(byKey('ann:suggest-cancel'));
  await until(async () => (await text('#main [data-key="ann:suggest"]')) === 'Suggest', 'Suggest again');
  await pause(3500);   // the fake holds the answer up to 3 s
  assert.equal(await value(byKey('ann:text')), '', 'The cancelled answer was dropped'); assert.equal(await mark(), null);
  // Asked, shown as a suggestion naming the model, changed and kept.
  await tell({ answer: 'A dog chases a red ball.' });
  await press(byKey('ann:suggest'));
  await until(async () => /Suggested by writer · writer-cpu \(chat_generation\)/.test(await mark() || ''), 'the suggestion shown');
  assert.equal(await value(byKey('ann:text')), 'A dog chases a red ball.');
  assert.match(await text('#main .ann-form .umark'), /not kept yet/);
  await settled('suggested');
  await shot('light-1440-suggestion');
  await press(byKey('ann:text')); await evaluate(`(() => { const e = document.activeElement; e.setSelectionRange(e.value.length, e.value.length); return true; })()`); await send('Input.insertText', { text: ' In the park.' });
  assert.match(await mark(), /Changed from the suggestion of writer · writer-cpu/);
  await press(byKey('ann:decide-accepted')); await press(byKey('annotate:form:keep')); await kept('kept the summary');
  // A refused suggestion leaves the form as it was.
  await pickTask('annotations/topics'); await open('b.txt');
  assert.deepEqual(await options('#main [data-key="ann:suggest-model"]'), ['controlled-vision\u0000vision-cpu', 'writer\u0000writer-cpu', 'decider\u0000decider-cpu'], 'The models that suggest a class of a text (in the endpoint\'s order)');
  await choose(byKey('ann:suggest-model'), 'writer\u0000writer-cpu');
  await press(byKey('ann:term-1')); await type(byKey('ann:note'), 'clouds, maybe');
  await tell({ answer: 'a fluffy animal, probably' });
  await press(byKey('ann:suggest'));
  const refused = await until(() => text('#main .ann-form .ann-sugrefusal'), 'the refusal beside the form');
  assert.match(refused, /No suggestion: the form is as it was/); assert.match(refused, /a fluffy animal, probably/);
  assert.deepEqual([await evaluate(`document.querySelector('[data-key="ann:term-1"]').checked`), await value(byKey('ann:note')), await mark()], [true, 'clouds, maybe', null], 'The form is as it was');
  await settled('refused');
  await shot('light-1440-suggestion-refused');
  // Suggest for this page: a.txt, c.txt and photo.png have no annotation (b.txt holds a typed draft); the second is refused.
  await tell({ answer: 'travel', modes: ['success', 'unknown'] });
  await press(byKey('ann:suggest-page'));
  const said = await until(async () => { const t = await text('#main .ann-form .ann-batch .ann-batch-line'); return t && /^Done\./.test(t) ? t : null; }, 'the page suggested', 600);
  assert.match(said, /^Done\. Kept 2 drafts, 1 refused, of 3 records with no annotation\. First refused: c\.txt: /, said);
  await settled('page suggested');
  const after = await tiles();
  assert.deepEqual(after.map(x => [x.id, x.state]), [['a.txt', 'draft'], ['b.txt', 'none'], ['c.txt', 'none'], ['photo.png', 'draft']], 'The drafts kept: ' + JSON.stringify(after));
  assert.deepEqual([await evaluate(`document.querySelector('[data-key="ann:term-1"]').checked`), await value(byKey('ann:note'))], [true, 'clouds, maybe'], 'The typed draft of b.txt stays');
  await press(byKey('save:save')); await kept('saved the annotations');
  const summary = lines(folder, 'summaries');
  assert.deepEqual(summary.map(l => [l.record, l.state, l.value, l.from]), [['a.txt', 'accepted', 'A dog chases a red ball. In the park.', { model: 'writer', profile: 'writer-cpu', capability: 'chat_generation' }]]);
  assert.deepEqual(Object.keys(summary[0]), ['record', 'sha256', 'state', 'value', 'by', 'at', 'from'], 'The keys of the line');
  const topics = lines(folder, 'topics');
  assert.deepEqual(topics.map(l => [l.record, l.state, l.value, l.from]), [['a.txt', 'draft', 'travel', { model: 'writer', profile: 'writer-cpu', capability: 'chat_generation' }], ['photo.png', 'draft', 'travel', { model: 'controlled-vision', profile: 'vision-cpu', capability: 'image_to_text' }]]);
  check('5. Suggest: cancelled while writer was asked ("Asking writer…", the late answer dropped); asked again, shown "' + 'Suggested by writer · writer-cpu (chat_generation)' + '", changed by typing and kept; after Save the line of a.txt carries from {writer, writer-cpu, chat_generation}. "a fluffy animal, probably" refused beside the form with the term and the note as they were. Suggest for this page: "' + said.slice(0, 80) + '…"; the two drafts saved with their from');

  // ---- 6. Typed text is never lost to a reading ------------------------------------------------------------------------
  const typed = () => evaluate(`({ key: document.activeElement.dataset.key, value: document.activeElement.value })`);
  const still = async (label, typeInto, words) => {
    await type(typeInto, words);
    const before = await typed(); assert.deepEqual(before, { key: JSON.parse(typeInto.slice(10, -1)), value: words });
    await evaluate(WATCHER); await evaluate(`window.__still.start()`);
    let since = Date.now(); await evaluate(`window.dispatchEvent(new Event('focus')); true`); await reading(since, WATCHED.concat(['map']), label + ': focus');
    since = Date.now(); await reading(since, WATCHED, label + ': the timer', Math.round((IDLE_MS + 8000) / 100));
    const r = await evaluate(`window.__still.stop()`);
    for (const id of ['tabs', 'main', 'aside']) assert.deepEqual([r.counts[id].added, r.counts[id].removed, r.counts[id].attrs, r.counts[id].text, r.fresh[id]], [0, 0, 0, 0, 0], label + ': ' + id + ' untouched: ' + JSON.stringify(r.counts[id]));
    assert.equal(r.flash, 0, label + ': no "Reading…"');
    assert.deepEqual(await typed(), before, label + ': the typed text and the focus stay');
  };
  await load('light', 'data/new%3Agenerate');
  await until(() => evaluate(`!!document.querySelector('#aside [data-key="newgenerate:field:title"]')`), 'the Generate form'); await settled('generate');
  await still('Generate', byKey('newgenerate:field:prompt'), 'Describe {n} clouds.');
  await load('light', 'train/endpoint'); await still('The endpoint', byKey('endpoint:set:field:address'), 'http://127.0.0.1:9');
  await load('light', 'annotate'); await pickTask('annotations/summaries'); await open('c.txt');
  await still('Annotate', byKey('ann:text'), 'A train leaves at nine.');
  check('6. With text typed in the Generate form, the endpoint\'s address and the annotation form, the window regaining focus and a reading on the timer added, removed and changed no node of the tab bar, the main area or the drawer, showed no "Reading…", and the text and the focus stayed');

  // ---- 7. Screenshots ------------------------------------------------------------------------------------------------
  const seen = [];
  const over = async label => { const o = await evaluate(`(() => { const m = document.getElementById('main'), a = document.getElementById('drawer'); return { page: document.documentElement.scrollWidth - innerWidth, main: m.scrollWidth - m.clientWidth, drawer: a.scrollWidth - a.clientWidth }; })()`); assert.ok(o.page <= 0 && o.main <= 1 && o.drawer <= 1, label + ': sideways overflow ' + JSON.stringify(o)); };
  const toEndpoint = () => evaluate(`(() => { document.querySelector('#main [data-key="open-endpoint"]').closest('ul').previousElementSibling.scrollIntoView({ block: 'start' }); return true; })()`);
  const view = async (tag, name) => { await over(tag + ' ' + name); await shot(tag + '-' + name); seen.push(tag + ' ' + name); };
  const generateForm = async () => { await press(byKey('data:new:generate')); await until(() => evaluate(`!!document.querySelector('#aside .gen-form, #aside .gen-none')`), 'the Generate form'); await settled('generate'); };
  for (const [w, hgt] of [[1440, 900], [1000, 800]]) for (const name of ['light', 'dark']) {
    const tag = name + '-' + w;
    await size(w, hgt);
    await api('set_endpoint', { address: null });
    await load(name, 'train'); await toEndpoint(); await view(tag, 'train-not-set');
    await hash('data'); await generateForm(); await view(tag, 'generate-none');
    await api('set_endpoint', { address: base });
    await load(name, 'train'); await toEndpoint(); await view(tag, 'train-set');
    await press(byKey('open-endpoint')); await settled('drawer');
    await type(byKey('endpoint:set:field:address'), 'http://192.168.1.5:8765'); await press(byKey('endpoint:set:set')); await kept('refused'); await refusal();
    await toEndpoint(); await view(tag, 'train-refusal');
    await hash('data'); await generateForm();
    await choose(byKey('newgenerate:field:make'), 'text'); await choose(byKey('newgenerate:field:model'), 'writer\u0000writer-cpu');
    await type(byKey('newgenerate:field:title'), 'Short poems'); await type(byKey('newgenerate:field:prompt'), 'Write line {n} of a short poem.');
    await view(tag, 'generate-text');
    await choose(byKey('newgenerate:field:make'), 'image'); await choose(byKey('newgenerate:field:model'), 'painter\u0000painter-gpu');
    await press(byKey('newgenerate:field:from-prompts')); await settled('prompts');
    await evaluate(`(() => { document.getElementById('drawer').scrollTop = 1e6; return true; })()`);
    await view(tag, 'generate-image');
    await hash('annotate'); await pickTask('annotations/summaries'); await open('b.txt');
    await choose(byKey('ann:suggest-model'), 'writer\u0000writer-cpu'); await tell({ answer: 'Rain is coming to the hills tonight.' });
    await press(byKey('ann:suggest')); await until(async () => /Suggested by/.test(await mark() || ''), 'the suggestion'); await settled('suggestion');
    await view(tag, 'suggestion');
    await pickTask('annotations/topics'); await open('c.txt');
    await choose(byKey('ann:suggest-model'), 'writer\u0000writer-cpu'); await tell({ answer: 'trains and boats' });
    await press(byKey('ann:suggest')); await until(() => text('#main .ann-form .ann-sugrefusal'), 'the refusal'); await settled('refusal');
    if (w === 1000) await evaluate(`(() => { document.querySelector('#main .ann-form').scrollIntoView({ block: 'start' }); return true; })()`);
    await view(tag, 'suggestion-refused');
  }
  await size(1440, 900);
  check('7. Nothing overflows sideways in light and dark at 1440 × 900 and 1000 × 800 (' + seen.length + ' views: the endpoint not set, set and refused, the Generate form without an endpoint, for text and for images, and a suggestion and a refusal)' + (shots ? '; screenshots in ' + shots : ''));

  // ---- Nothing failed ---------------------------------------------------------------------------------------------------
  assert.deepEqual(errors, [], 'Script errors');
  const asked = failures.filter(f => f.url && ASKED.test(f.url));
  assert.ok(asked.length >= 7, 'The refusals asked for: ' + JSON.stringify(asked));
  assert.deepEqual(failures.filter(f => !asked.includes(f)), [], 'Failed requests');
  check('No script error, no failed request but the ' + asked.length + ' refusals of set_endpoint and suggest_annotation asked for');
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
