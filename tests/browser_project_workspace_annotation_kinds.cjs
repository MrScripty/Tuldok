'use strict';
// Review of generated annotations (docs/plans/training-and-curation/spec-t4.md sections 7 and 9, slices T4e and T4f)
// in a headless browser, the owner signed in, no GPU, no Pumas. The fixture (tests/browser_annotation_kinds_fixture.py)
// is a project in Git whose code is examples/tiny-project's make_scenes.py and stand-in annotator: datasets/scenes
// imports three images, two point clouds, an array of frames and a series, and a task of each of eight types (mask,
// polygons, depth, keypoints, points, box3d, timeseries, track) has two annotators, the stand-in at two thresholds,
// built by the command line before Tuldok starts.
//   1. Annotate → Review on the masks: the agreement shown is the server's, the most disputed records are listed in
//      the order computed, two panels side by side each draw their set's mask, and overlaid one panel draws both.
//   2. Every other type is drawn: polygons, depth maps and keypoints on the images, point objects and 3-D boxes on a
//      point cloud, stretches under the series, and tracks on the frames, where the frame slider shows B's identity
//      switch at frame 3.
//   3. One record is reviewed and B kept: the decision says so, the strip counts it, Save writes
//      annotations/masks.jsonl with the line naming the set and annotations/masks/<its mask>.
//   4. A kept polygon is corrected: a vertex dragged, the correction kept and saved.
//   5. Updates in place: a change elsewhere (an agent sets another task's annotation) and the window regaining focus
//      add, remove and change no node of the main area.
//   6. Light and dark at 1440 by 900 and 390 by 844: nothing overflows sideways (screenshots with --shots <dir>).
// It fails on any script error and any failed request.
//   node tests/browser_project_workspace_annotation_kinds.cjs [--shots <dir>]
const assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const { spawn, execFileSync } = require('node:child_process'), { once } = require('node:events');
const { authenticatedFixture } = require('./auth_helpers.cjs'), { waitForDebugger } = require('./browser_startup.cjs'), { cdpSession } = require('./browser_cdp_session.cjs'), { qaDirectory } = require('./qa_artifacts.cjs');

const root = path.resolve(__dirname, '..');
const argv = process.argv.slice(2), option = name => { const i = argv.indexOf(name); return i >= 0 ? argv[i + 1] : null; };
assert.ok(process.env.TULDOK_DATABASE_URL, 'TULDOK_DATABASE_URL must name a disposable PostgreSQL cluster');
const venv = path.join(root, '.venv', 'bin');
if (fs.existsSync(path.join(venv, 'python'))) process.env.PATH = venv + path.delimiter + process.env.PATH;
const python = fs.existsSync(path.join(venv, 'python')) ? path.join(venv, 'python') : 'python3';
const WATCHED = ['summary', 'status', 'build_requests', 'environments', 'runs'];

const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'tuldok-annotation-kinds-'));
const report = qaDirectory(root, 'project-workspace-annotation-kinds');
const shots = option('--shots') ? path.resolve(option('--shots')) : null; if (shots) fs.mkdirSync(shots, { recursive: true });
const children = [], checks = [], errors = [], failures = [];
let server, serverErrors = '', origin, auth, socket, session, send, evaluate, owned = null, folder;
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
function dropOwned(id, catalog) {
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

// ---- The page's readings, from the browser's network ------------------------------------------------------------
const calls = new Map(), finished = [];
function network(event) {
  const p = event.params;
  if (event.method === 'Network.requestWillBeSent' && /\/api\/project\/[a-z_]+$/.test(p.request.url)) calls.set(p.requestId, { name: p.request.url.split('/').pop(), sent: Date.now() });
  if ((event.method === 'Network.loadingFinished' || event.method === 'Network.loadingFailed') && calls.has(p.requestId)) { finished.push(Object.assign(calls.get(p.requestId), { done: Date.now() })); calls.delete(p.requestId); }
}
async function settled(label) {
  await until(async () => !calls.size && await evaluate(`(() => { const reading = e => [...e.querySelectorAll('.note')].some(n => n.textContent === 'Reading…'); return !reading(document.getElementById('main')) && !reading(document.getElementById('aside')) && !document.getElementById('main').hasAttribute('aria-busy') && !document.querySelector('.act-group [aria-busy]'); })()`), 'settled: ' + label);
  await pause(250);
  await until(async () => !calls.size, 'settled again: ' + label);
}
async function reading(since, names, label) {
  await until(() => names.every(name => finished.some(f => f.name === name && f.sent >= since)), 'a reading: ' + label);
  await until(() => !calls.size && Date.now() - Math.max(0, ...finished.map(f => f.done)) > 700, 'the reading done: ' + label);
  await settled(label);
}
const byKey = key => `[data-key=${JSON.stringify(key)}]`;
async function centre(selector) {
  return until(() => evaluate(`(() => { const e = [...document.querySelectorAll(${JSON.stringify(selector)})].find(e => e.offsetParent !== null); if (!e) return null; e.scrollIntoView({ block: 'nearest', inline: 'nearest' }); const r = e.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2, hit = document.elementFromPoint(x, y); return hit && (hit === e || e.contains(hit)) ? { x, y } : null; })()`), 'shown: ' + selector, 100);
}
async function mouse(type, x, y, buttons = 0) { await send('Input.dispatchMouseEvent', { type, x, y, button: type === 'mouseMoved' ? (buttons ? 'left' : 'none') : 'left', buttons, clickCount: type === 'mouseMoved' ? 0 : 1 }); }
async function press(selector) { const { x, y } = await centre(selector); await mouse('mouseMoved', x, y); await mouse('mousePressed', x, y, 1); await mouse('mouseReleased', x, y); }
async function dragFrom(a, b, steps = 8) { await mouse('mouseMoved', a.x, a.y); await mouse('mousePressed', a.x, a.y, 1); for (let i = 1; i <= steps; i++) await mouse('mouseMoved', a.x + (b.x - a.x) * i / steps, a.y + (b.y - a.y) * i / steps, 1); await mouse('mouseReleased', b.x, b.y); }
async function choose(selector, value) { await evaluate(`(() => { const s = document.querySelector(${JSON.stringify(selector)}); s.value = ${JSON.stringify(value)}; s.dispatchEvent(new Event('change', { bubbles: true })); return true; })()`); }
async function shot(name) {
  await evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))');
  const png = Buffer.from((await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })).data, 'base64');
  fs.writeFileSync(path.join(report, name + '.png'), png); if (shots) fs.writeFileSync(path.join(shots, name + '.png'), png);
}
const fixed = v => v == null ? '—' : v.toFixed(2);
const drawn = selector => evaluate(`[...document.querySelectorAll(${JSON.stringify(selector)})].map(e => e.dataset.drawn)`);
/** Pixels of a canvas that are neither empty nor the page's white: something was drawn on it. */
const inked = selector => evaluate(`[...document.querySelectorAll(${JSON.stringify(selector)})].map(c => { const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let n = 0; for (let i = 0; i < d.length; i += 4) if (d[i + 3] && !(d[i] > 245 && d[i + 1] > 245 && d[i + 2] > 245)) n++; return n; })`);
const lines = name => { const file = path.join(folder, 'annotations', name + '.jsonl'); return fs.existsSync(file) ? fs.readFileSync(file, 'utf8').split('\n').filter(Boolean).map(l => JSON.parse(l)) : []; };

const WATCHER = `window.__still = (() => {
  const ids = ['tabs', 'main', 'aside', 'review'], el = id => id === 'review' ? document.querySelector('#main .rv-body') : document.getElementById(id);
  let counts = null, observers = [];
  return {
    start() {
      for (const o of observers) o.disconnect(); observers = []; counts = {};
      for (const id of ids) { counts[id] = { added: 0, removed: 0, attrs: 0, text: 0, what: [] }; const c = counts[id];
        const o = new MutationObserver(list => { for (const r of list) { if (r.type === 'childList') { c.added += r.addedNodes.length; c.removed += r.removedNodes.length; } else if (r.type === 'characterData') c.text++; else { c.attrs++; if (c.what.length < 6) c.what.push('@' + r.attributeName + ' ' + (r.target.className || r.target.tagName)); } } });
        o.observe(el(id), { childList: true, subtree: true, characterData: true, attributes: true }); observers.push(o); }
    },
    stop() { for (const o of observers) o.disconnect(); observers = []; const r = counts; counts = null; return r; }
  };
})(); true`;

(async () => {
  // ---- The fixture ------------------------------------------------------------------------------------------------
  const repo = path.join(temporary, 'fixture'); folder = path.join(repo, 'project');
  const info = JSON.parse(execFileSync(python, [path.join(root, 'tests', 'browser_annotation_kinds_fixture.py'), repo], { cwd: root }).toString().trim().split('\n').pop());
  const home = path.join(temporary, 'home'), catalog = path.join(temporary, 'catalog'); fs.mkdirSync(home);
  const env = { ...process.env, TULDOK_PROJECT_HOME: home, TULDOK_SETTINGS: path.join(temporary, 'settings.json') };
  owned = [info.project_id, catalog]; dropOwned(...owned);
  const cli = (...args) => execFileSync(python, ['-m', 'tuldok_project', ...args], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] }).toString();
  assert.match(cli('check', folder), /^0 errors/m);
  cli('connect', folder, 'environments/test-python', python);
  cli('build', folder, ...info.annotators, '--yes');
  let output = '';
  server = launch(python, ['-u', 'app.py', '--port', '0', '--data', catalog, '--project-folder', folder], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] });
  server.stdout.on('data', chunk => { output += chunk; }); server.stderr.on('data', chunk => { serverErrors += chunk; });
  const port = await until(() => { if (server.exitCode !== null) throw Error('Tuldok exited: ' + serverErrors); return output.match(/127\.0\.0\.1:(\d+)/)?.[1]; }, 'Tuldok start-up', 3000);
  origin = 'http://127.0.0.1:' + port;
  auth = authenticatedFixture(); await auth.register(origin, catalog, root);
  for (const task of Object.keys(info.tasks)) assert.equal((await api('annotation_sets', { task })).sets.filter(s => s.annotated).length, 2, task + ' has two sets');

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
  await size(1440, 900); await theme('light');
  await auth.browser(send, origin);
  const load = async name => {
    await theme(name);
    await send('Page.navigate', { url: 'about:blank' }); await pause(100);
    await send('Page.navigate', { url: origin + '/?theme=' + name + '#annotate' });
    await until(() => evaluate(`document.readyState === 'complete' && !!document.getElementById('needs-btn') && !document.getElementById('needs-btn').disabled`), 'the project read', 1200);
    await settled('opened');
  };
  const pickTask = async name => {
    const ref = 'annotations/' + name;
    if ((await evaluate(`document.querySelector('[data-key="ann:task"]').value`)) !== ref) { await choose(byKey('ann:task'), ref); await settled('task ' + name); }
    if ((await evaluate(`(document.querySelector('[data-key="ann:mode-review"]') || {}).getAttribute?.('aria-pressed')`)) !== 'true') { await press(byKey('ann:mode-review')); await settled('review ' + name); }
    await until(() => evaluate(`!!document.querySelector('#main .rv-body .rv-rec')`), 'review of ' + name);
  };
  const mode = async which => { if ((await evaluate(`document.querySelector('[data-key="rv:mode-${which}"]').getAttribute('aria-pressed')`)) !== 'true') { await press(byKey('rv:mode-' + which)); await settled('mode ' + which); } };
  const over = async label => { const o = await evaluate(`(() => { const m = document.getElementById('main'); return { page: document.documentElement.scrollWidth - innerWidth, main: m.scrollWidth - m.clientWidth }; })()`); assert.ok(o.page <= 0 && o.main <= 1, label + ': sideways overflow ' + JSON.stringify(o)); };
  await load('light');

  // ---- 1. Masks: the agreement, the disputed order, side by side and overlaid ------------------------------------------
  await pickTask('masks');
  const ag = await api('annotation_agreement', { task: 'masks', sets: ['datasets/masks-a', 'datasets/masks-b'], limit: 200 });
  assert.equal(await evaluate(`document.querySelector('#main .rv-score').textContent`), fixed(ag.pairs[0].agreement));
  const listed = await evaluate(`[...document.querySelectorAll('#main .rv-rec')].map(b => [b.dataset.id, b.querySelector('.rv-dis').textContent])`);
  assert.deepEqual(listed, ag.disputed.map(r => [r.record, fixed(r.disagreement)]), 'the most disputed, as computed');
  assert.equal(await evaluate(`document.querySelector('#main .rv-rec[aria-pressed="true"]').dataset.id`), ag.disputed[0].record);
  await mode('side');
  const first = await api('annotation_compare', { task: 'masks', record: ag.disputed[0].record, sets: ['datasets/masks-a', 'datasets/masks-b'] });
  const pixels = s => s.drawn.runs.reduce((n, [v, c]) => n + (v ? c : 0), 0);
  assert.deepEqual(await drawn('#main .rv-panel canvas'), ['a:' + pixels(first.sets[0]), 'b:' + pixels(first.sets[1])]);
  assert.ok((await inked('#main .rv-panel canvas')).every(n => n > 0), 'both canvases drawn');
  await mode('over');
  assert.deepEqual(await drawn('#main .rv-panel canvas'), ['a:' + pixels(first.sets[0]) + ' b:' + pixels(first.sets[1])]);
  await shot('light-1440-masks-overlaid');
  check('1. Review of the masks: the agreement ' + fixed(ag.pairs[0].agreement) + ' and the ' + ag.disputed.length + ' most disputed records (' + listed.map(r => r.join(' ')).join(', ') + ') as the server computed them; side by side two canvases each draw their mask (' + pixels(first.sets[0]) + ' and ' + pixels(first.sets[1]) + ' pixels), overlaid one draws both');

  // ---- 2. Every other type drawn ------------------------------------------------------------------------------------
  await mode('side');
  const seen = [];
  for (const [task, selector] of [['shapes', '#main .rv-panel canvas'], ['depths', '#main .rv-panel canvas'], ['corners', '#main .rv-panel canvas'], ['tops', '#main .rv-panel'], ['boxes3d', '#main .rv-panel'], ['stretches', '#main .rv-panel canvas'], ['tracks', '#main .rv-panel canvas']]) {
    await pickTask(task);
    const values = await drawn(selector);
    assert.equal(values.length, 2, task + ': two panels');
    if (task === 'boxes3d') for (const v of values) assert.match(v, /^[ab]:0\/1$/, 'a 3-D box drawn: ' + v);
    else for (const v of values) assert.match(v, /^(frame \d+ )?[ab]:[1-9]/, task + ' drew its set: ' + v);
    assert.ok((await inked('#main .rv-panel canvas')).every(n => n > 0), task + ': canvases drawn');
    seen.push(task + ' ' + values.join(' | '));
    await shot('light-1440-' + task);
  }
  // Tracks: B's identity switch at frame 3, seen with the slider.
  const before = await drawn('#main .rv-panel canvas');
  await evaluate(`(() => { const r = document.querySelector('[data-key="rv:frame"]'); r.value = '3'; r.dispatchEvent(new Event('input', { bubbles: true })); return true; })()`);
  const after = await drawn('#main .rv-panel canvas');
  assert.deepEqual(before, ['frame 0 a:1=square', 'frame 0 b:1=square']);
  assert.deepEqual(after, ['frame 3 a:1=square', 'frame 3 b:1=square-2']);
  assert.match(await evaluate(`document.querySelector('#main .rv-figures').innerText`), /Identity switches\s+1/);
  check('2. Drawn: ' + seen.join('; ') + '; on the frames the slider moved to frame 3 shows B\'s track renamed (an identity switch, counted 1)');

  // ---- 3. One record reviewed and kept, then saved ----------------------------------------------------------------
  await pickTask('masks');
  const record = ag.disputed[0].record;
  await press(byKey('rv-rec-' + record)); await settled('record');
  await press(byKey('review:decide:keep-b')); await settled('kept B');
  const said = await evaluate(`document.querySelector('#main .rv-kept').textContent`);
  assert.match(said, /^Kept: accepted · from masks-b · unsaved/);
  assert.match(await evaluate(`document.getElementById('strip').innerText`), /1 annotation unsaved/);
  await press(byKey('save:save')); await settled('saved');
  const saved = lines('masks');
  assert.equal(saved.length, 1); assert.equal(saved[0].record, record); assert.equal(saved[0].state, 'accepted');
  assert.equal(saved[0].from.set, 'datasets/masks-b'); assert.equal(saved[0].from.by.name, 'stand-in B');
  assert.ok(fs.existsSync(path.join(folder, 'annotations', 'masks', saved[0].value.file)), 'the mask saved beside it');
  assert.match(await evaluate(`document.querySelector('#main .rv-kept').textContent`), /^Kept: accepted · from masks-b ·(?! unsaved)/);
  check('3. ' + record + ' reviewed and B kept ("' + said.trim() + '"); Save wrote annotations/masks.jsonl naming datasets/masks-b and stand-in B, and annotations/masks/' + saved[0].value.file);

  // ---- 4. A kept polygon corrected -------------------------------------------------------------------------------------
  await pickTask('shapes');
  const shape = (await api('annotation_agreement', { task: 'shapes', sets: ['datasets/shapes-a', 'datasets/shapes-b'] })).disputed[0].record;
  await press(byKey('rv-rec-' + shape)); await settled('shape');
  await press(byKey('review:decide:keep-a')); await settled('kept A');
  const keptValue = (await api('annotation', { task: 'shapes', record: shape })).annotation.value;
  await press(byKey('review:correct:correct')); await settled('correcting');
  const vertex = keptValue[0].points[0];
  const at = await evaluate(`(() => { const c = document.querySelector('#main .rv-panel canvas'); c.scrollIntoView({ block: 'center' }); const r = c.getBoundingClientRect(); return { x: r.left + ${vertex[0]} / 24 * r.width, y: r.top + ${vertex[1]} / 16 * r.height, w: r.width }; })()`);
  await dragFrom({ x: at.x, y: at.y }, { x: at.x + at.w / 24 * 2, y: at.y + at.w / 24 * 1 }); await settled('dragged');
  await press(byKey('review:correction:keep-correction')); await settled('correction kept');
  const corrected = (await api('annotation', { task: 'shapes', record: shape })).annotation.value;
  assert.deepEqual(corrected[0].points[0], [vertex[0] + 2, vertex[1] + 1], 'the vertex moved by 2 and 1 pixels');
  assert.deepEqual(corrected[0].points.slice(1), keptValue[0].points.slice(1));
  await press(byKey('save:save')); await settled('saved shapes');
  assert.deepEqual(lines('shapes')[0].value[0].points[0], [vertex[0] + 2, vertex[1] + 1]);
  check('4. The polygon kept from A on ' + shape + ' corrected: its vertex at ' + vertex.join(', ') + ' dragged to ' + corrected[0].points[0].join(', ') + ', kept and saved');

  // A kept point object corrected: a rectangle over the right half of the cloud's view (where its top is drawn) removes
  // the points shown there.
  await pickTask('tops');
  await press(byKey('rv-rec-clouds__p.ply')); await settled('cloud');
  await press(byKey('review:decide:keep-b')); await settled('kept B of the cloud');
  const keptPoints = (await api('annotation', { task: 'tops', record: 'clouds__p.ply' })).annotation.value[0].indices;
  await press(byKey('review:correct:correct')); await settled('correcting points');
  const box = await evaluate(`(() => { const c = document.querySelector('#main .rv-panel canvas'); c.scrollIntoView({ block: 'center' }); const r = c.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; })()`);
  await dragFrom({ x: box.x + box.w * 0.5, y: box.y + 2 }, { x: box.x + box.w - 2, y: box.y + box.h - 2 }); await settled('points removed');
  assert.match(await evaluate(`document.querySelector('#main .rv-correct').innerText`), /\d+ points? removed so far/);
  await press(byKey('review:correction:keep-correction')); await settled('points correction kept');
  const left = (await api('annotation', { task: 'tops', record: 'clouds__p.ply' })).annotation.value;
  const remaining = left.length ? left[0].indices : [];
  assert.ok(remaining.length < keptPoints.length && remaining.every(i => keptPoints.includes(i)), 'some points removed, none added: ' + JSON.stringify([keptPoints, remaining]));
  check('4b. The point object kept from B on clouds__p.ply corrected: a rectangle over the right half of the view removed ' + (keptPoints.length - remaining.length) + ' of its ' + keptPoints.length + ' points, kept as an unsaved edit');

  // ---- 5. Updates in place ------------------------------------------------------------------------------------------
  await pickTask('masks');
  await evaluate(WATCHER); await evaluate('window.__still.start()');
  const agent = await credential('An annotating agent', ['inspect', 'edit']);
  let since = Date.now();
  await api('set_annotation', { task: 'stretches', items: [{ record: 'series__signal.npy', state: 'draft', value: [{ term: 'high', start: 10, end: 20 }] }] }, agent);
  await evaluate(`window.dispatchEvent(new Event('focus')); true`); await reading(since, WATCHED, 'focus after the agent');
  since = Date.now(); await evaluate(`window.dispatchEvent(new Event('focus')); true`); await reading(since, WATCHED, 'focus');
  const still = await evaluate('window.__still.stop()');
  for (const id of ['tabs', 'review']) assert.deepEqual([still[id].added, still[id].removed, still[id].attrs, still[id].text], [0, 0, 0, 0], id + ' untouched: ' + JSON.stringify(still[id]));
  assert.deepEqual([still.main.added, still.main.removed, still.main.text], [0, 0, 0], 'no node of the main area added, removed or written: ' + JSON.stringify(still.main));
  check('5. With the review of the masks on screen, an agent setting another task\'s annotation (a change, so the tab was read again) and the window regaining focus added, removed and changed no node of the review; the main area only had its busy mark set and cleared while it read (' + still.main.attrs + ' attribute changes on it)');

  // ---- 6. Light and dark, 1440 and 390 ------------------------------------------------------------------------------
  const views = [];
  for (const [w, hgt] of [[1440, 900], [390, 844]]) for (const name of ['light', 'dark']) {
    await size(w, hgt); await load(name);
    for (const task of ['masks', 'tops', 'tracks']) {
      await pickTask(task); await over(name + ' ' + w + ' ' + task); await shot(name + '-' + w + '-' + task); views.push(name + ' ' + w + ' ' + task);
    }
  }
  await size(1440, 900);
  check('6. Nothing overflows sideways in ' + views.length + ' views (light and dark, 1440 × 900 and 390 × 844)' + (shots ? '; screenshots in ' + shots : ''));

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
  for (const child of children.reverse()) await stop(child);
  if (owned) try { dropOwned(...owned); } catch (error) { console.error('Dropping the disposable schemas failed:', error.message); process.exitCode = 1; }
  try { execFileSync('chmod', ['-R', 'u+w', temporary]); } catch (_) { /* nothing was made read-only */ }
  fs.rmSync(temporary, { recursive: true, force: true });
});
