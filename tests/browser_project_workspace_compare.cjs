'use strict';
// Comparing chosen models deeply (docs/plans/training-and-curation/spec-t3.md sections 5 and 7, slices T3b and T3c)
// in a headless browser, the owner signed in, no GPU. Tuldok runs with --project-folder on a copy of the minimal
// fixture in a Git repository of its own, with what tests/project_compare_browser_fixture.py writes: five recipes of
// earlier work whose settings vary, a benchmark of the five with a tradeoff and a ranking chart, per-case values of
// each (imported through import_values), and adopted products of three of them that keep fields of one shared case.
//   1. The Map drawer's Compare adds three models; Open Compare shows the Compare tab: three columns, the paths that
//      differ (and not those that are the same), the metrics with intervals equal to the intervals operation's, and
//      the frontier rows (cm-b and cm-c not told apart).
//   2. Outputs: the shared case, nine panels drawn; the Native row the same colours in every column (one scale),
//      the Predicted row different where the predictions differ; one slider move asks field_compare three times and
//      draws every canvas again in place, the rest of the tab the same elements; hover names the column's values.
//   3. Benchmarks: parallel coordinates with the metric and setting axes; a range dragged on the error axis hides the
//      table rows outside it, makes the charts' points of those subjects faint, and asks nothing; moving an axis and
//      the log scale redraw it in place with the range kept; Clear ranges shows every row again.
//   4. Intervals: whiskers on the ranking chart, a low – high line in the table's cells, a dashed ring on the frontier
//      points the answer says are not told apart.
//   5. Light and dark at 1440 and 390 wide, the Compare and Benchmarks tabs: no blank canvas, nothing in the main area
//      wider than it outside the tables' own scrolling boxes; no script error and no failed request.
//   node tests/browser_project_workspace_compare.cjs [--shots <dir>]
const assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const { spawn, execFileSync } = require('node:child_process'), { once } = require('node:events');
const { authenticatedFixture } = require('./auth_helpers.cjs'), { waitForDebugger } = require('./browser_startup.cjs'), { cdpSession } = require('./browser_cdp_session.cjs'), { qaDirectory } = require('./qa_artifacts.cjs');

const root = path.resolve(__dirname, '..');
const argv = process.argv.slice(2), option = name => { const i = argv.indexOf(name); return i >= 0 ? argv[i + 1] : null; };
assert.ok(process.env.TULDOK_DATABASE_URL, 'TULDOK_DATABASE_URL must name a disposable PostgreSQL cluster');
const venv = path.join(root, '.venv', 'bin');
if (fs.existsSync(path.join(venv, 'python'))) process.env.PATH = venv + path.delimiter + process.env.PATH;   // auth_helpers runs python3
const python = fs.existsSync(path.join(venv, 'python')) ? path.join(venv, 'python') : 'python3';
const MODELS = ['recipes/cm-a', 'recipes/cm-b', 'recipes/cm-c'], BENCH = 'cmp-bench';

const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'tuldok-compare-browser-'));
const report = qaDirectory(root, 'project-workspace-compare');
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
const asked = (name, since = 0, test = () => true) => finished.concat([...calls.values()]).filter(f => (name === null || f.name === name) && f.sent >= since && test(f.body || {}));
/** Waits until nothing reads: no "Reading…", nothing busy in the main area, no request of the project in flight. */
async function settled(label) {
  await until(() => evaluate(`(() => { const m = document.getElementById('main'); return ![...m.querySelectorAll('.note')].some(n => n.textContent === 'Reading…') && !m.hasAttribute('aria-busy') && !m.querySelector('[aria-busy]'); })()`).then(ok => ok && !calls.size), 'settled: ' + label);
  await pause(250);
}
const byKey = key => `[data-key=${JSON.stringify(key)}]`;
async function mouse(type, x, y, buttons = 0) { await send('Input.dispatchMouseEvent', { type, x, y, button: type === 'mouseMoved' ? (buttons ? 'left' : 'none') : 'left', buttons, clickCount: type === 'mouseMoved' ? 0 : 1 }); }
async function press(selector) {
  const at = await until(() => evaluate(`(() => { const e = document.querySelector(${JSON.stringify(selector)}); if (!e) return null; e.scrollIntoView({ block: 'center', inline: 'nearest' }); const r = e.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; })()`), 'shown: ' + selector, 100);
  await pause(100); await mouse('mouseMoved', at.x, at.y); await mouse('mousePressed', at.x, at.y, 1); await mouse('mouseReleased', at.x, at.y);
}
async function slide(selector, value) { await evaluate(`(() => { const r = document.querySelector(${JSON.stringify(selector)}); r.focus(); r.value = ${JSON.stringify(String(value))}; r.dispatchEvent(new Event('input', { bubbles: true })); return true; })()`); }
async function frames() { await evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))'); }
async function shot(name) {
  await frames();
  const png = Buffer.from((await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })).data, 'base64');
  fs.writeFileSync(path.join(report, name + '.png'), png); if (shots) fs.writeFileSync(path.join(shots, name + '.png'), png);
}
const close = (a, b, label, tol = 1e-12) => assert.ok(Math.abs(a - b) <= tol * Math.max(1, Math.abs(b)), label + ': ' + a + ' is not ' + b);
const same = (a, b) => a.every((v, i) => v === b[i]);
// A panel of the outputs: the colour at the centre of each cell of a rows x columns grid drawn square in it, and how
// often it was drawn.
const CELLS = `(sel, rows, cols) => { const c = document.querySelector(sel); if (!c || !c.width) return null;
  const g = c.getContext('2d'), W = c.width, H = c.height, s = Math.min(W / cols, H / rows), x0 = (W - cols * s) / 2, y0 = (H - rows * s) / 2;
  const cells = []; for (let r = 0; r < rows; r++) { const row = []; for (let k = 0; k < cols; k++) { const p = g.getImageData(Math.floor(x0 + (k + 0.5) * s), Math.floor(y0 + (r + 0.5) * s), 1, 1).data; row.push([p[0], p[1], p[2], p[3]]); } cells.push(row); }
  const box = c.getBoundingClientRect(); return { cells, times: Number(c.dataset.drawn || 0), box: { left: box.left, top: box.top }, cell: { x0, y0, s, dpr: window.devicePixelRatio || 1 } }; }`;
const cellSel = (row, model) => `canvas.cmpv-cv[data-row="${row}"][data-model="${model}"]`;
const cells = (row, model, rows, cols) => evaluate(`(${CELLS})(${JSON.stringify(cellSel(row, model))}, ${rows}, ${cols})`);

(async () => {
  // ---- The fixture -------------------------------------------------------------------------------------------------
  fs.cpSync(path.join(root, 'tests', 'fixtures', 'tuldok_project', 'minimal'), path.join(temporary, 'fixture'), { recursive: true });
  const folder = path.join(temporary, 'fixture', 'project'), made = path.join(temporary, 'made');
  const X = JSON.parse(execFileSync(python, [path.join(root, 'tests', 'project_compare_browser_fixture.py'), '--out', made], { maxBuffer: 64 << 20 }).toString());
  for (const dir of ['recipes', 'benchmarks', 'charts']) for (const name of fs.readdirSync(path.join(made, dir))) fs.copyFileSync(path.join(made, dir, name), path.join(folder, dir, name));
  const git = ['-c', 'user.name=Tuldok Test', '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false', '-c', 'init.defaultBranch=main', '-C', path.join(temporary, 'fixture')];
  execFileSync('git', [...git, 'init', '-q']); execFileSync('git', [...git, 'add', '-A']); execFileSync('git', [...git, 'commit', '-q', '-m', 'The fixture.']);
  const home = path.join(temporary, 'home'), catalog = path.join(temporary, 'catalog'); fs.mkdirSync(home);
  const env = { ...process.env, TULDOK_PROJECT_HOME: home, TULDOK_SETTINGS: path.join(temporary, 'settings.json') };
  owned = [folder, catalog]; dropOwned(folder, catalog);
  const cli = (...args) => execFileSync(python, ['-m', 'tuldok_project', ...args], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] }).toString();
  const manifest = path.join(temporary, 'adopt.json');
  fs.writeFileSync(manifest, JSON.stringify({ format: 'tuldok_adoption_v1', products: MODELS.map(ref => { const dir = path.join(made, 'products', ref.split('/')[1]); return { reference: ref, files: Object.fromEntries(fs.readdirSync(dir).map(n => [n, path.join(dir, n)])) }; }) }));
  cli('adopt', folder, manifest, '--copy');
  let output = '';
  server = launch(python, ['-u', 'app.py', '--port', '0', '--data', catalog, '--project-folder', folder], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] });
  server.stdout.on('data', chunk => { output += chunk; }); server.stderr.on('data', chunk => { serverErrors += chunk; });
  const port = await until(() => { if (server.exitCode !== null) throw Error('Tuldok exited: ' + serverErrors); return output.match(/127\.0\.0\.1:(\d+)/)?.[1]; }, 'Tuldok start-up', 3000);
  origin = 'http://127.0.0.1:' + port;
  auth = authenticatedFixture(); await auth.register(origin, catalog, root);
  for (const name of fs.readdirSync(path.join(made, 'values'))) await api('import_values', { text: fs.readFileSync(path.join(made, 'values', name), 'utf8') });
  const IV = await api('intervals', { benchmark: BENCH });
  const ivOf = (s, m) => IV.intervals.find(r => r.subject === s && r.metric === m);
  const [front] = IV.frontiers;
  assert.deepEqual(front.not_separated, ['cm-b', 'cm-c'], 'The fixture: cm-b and cm-c are not told apart');

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
  const load = async (name, query, hash) => {
    await theme(name);
    await send('Page.navigate', { url: 'about:blank' }); await pause(100);
    await send('Page.navigate', { url: origin + '/?theme=' + name + (query ? '&' + query : '') + '#' + hash });
    await until(() => evaluate(`document.readyState === 'complete' && !!document.getElementById('needs-btn') && !document.getElementById('needs-btn').disabled`), 'the project read', 1200);
    await settled('opened ' + hash);
  };
  const drawn = () => until(() => evaluate(`(() => { const c = [...document.querySelectorAll('canvas.cmpv-cv')]; return c.length === 9 && c.every(x => Number(x.dataset.drawn) > 0); })()`), 'nine panels drawn');

  // ---- 1. Compare from the Map's drawers, then the Compare tab ---------------------------------------------------------
  await size(1440, 900); await load('light', '', 'map');
  for (const ref of MODELS) {
    await evaluate(`(() => { location.hash = '#map/' + encodeURIComponent(${JSON.stringify(ref)}); return true; })()`);
    await press(byKey('cmp-toggle-' + ref)); await settled('compare ' + ref);
    assert.equal(await evaluate(`document.querySelector(${JSON.stringify(byKey('cmp-toggle-' + ref))}).textContent`), 'Remove from compare');
  }
  assert.equal(new URLSearchParams(await evaluate('location.search')).get('cmp'), MODELS.join(','), 'The set is in the address');
  await press(byKey('cmp-open')); await until(() => evaluate(`location.hash === '#compare' && !!document.querySelector('table.cmpv')`), 'the Compare tab'); await settled('compare tab'); await drawn();
  const t1 = await evaluate(`(() => ({ cols: [...document.querySelectorAll('th.cmpv-col')].map(t => t.dataset.model), diffs: [...document.querySelectorAll('tr.cmpv-diff')].map(r => [r.dataset.kind, r.dataset.path, [...r.querySelectorAll('td')].map(t => t.textContent)]),
    group: [...document.querySelectorAll('tr.cmpv-group th')].map(t => t.textContent), metrics: [...document.querySelectorAll('tr.cmpv-metric')].map(r => [r.dataset.metric, [...r.querySelectorAll('td')].map(t => [Number(t.dataset.value), Number(t.dataset.low), Number(t.dataset.high), t.classList.contains('best')])]),
    front: [...document.querySelectorAll('tr.cmpv-front td')].map(t => [t.dataset.on, t.dataset.nsig]), tab: document.querySelector('#tabs [aria-current]').dataset.tab }))()`);
  assert.deepEqual(t1.cols, MODELS, 'One column per model, in the set\'s order'); assert.equal(t1.tab, 'compare');
  assert.deepEqual(t1.diffs.map(d => d[1]), ['change', 'derived_from', 'run.inputs.extra', 'run.settings.learning_rate', 'run.settings.optimizer', 'run.settings.width'], 'Only the paths that differ, in order');
  assert.deepEqual(t1.diffs.map(d => d[0]), ['change', 'parent', 'data', 'setting', 'setting', 'setting']);
  assert.deepEqual(t1.diffs[3][2], ['0.01', '0.001', '0.001']); assert.deepEqual(t1.diffs[1][2], ['—', '—', 'recipes/cm-b']);
  assert.ok(t1.group.some(t => /6 paths differ · \d+ the same/.test(t)), 'The count of the same: ' + t1.group.join(' | '));
  for (const [metric, row] of t1.metrics) row.forEach(([v, lo, hi], i) => { const r = ivOf(MODELS[i].split('/')[1], metric); close(lo, r.median[0], 'low ' + metric + ' ' + i); close(hi, r.median[1], 'high ' + metric + ' ' + i); assert.ok(lo <= v && v <= hi, 'the value inside its interval'); });
  assert.deepEqual(t1.metrics.find(m => m[0] === 'err')[1].map(c => c[3]), [false, false, true], 'The best error is marked (cm-c)');
  assert.deepEqual(t1.front, [['true', ''], ['true', 'cm-c'], ['true', 'cm-b']], 'The frontier row');
  await shot('light-1440-1-compare');
  check('1. Compare from three Map drawers, Open Compare: three columns ' + t1.cols.join(', ') + '; the differing paths ' + t1.diffs.map(d => d[1]).join(', ') + ' (epochs, the same, not listed); intervals equal to the intervals operation; cm-b and cm-c on the frontier, not told apart');

  // ---- 2. The outputs: one case, nine panels, one control for all ----------------------------------------------------
  const [R0, C0] = [X.shape[0], X.shape[1]], at = (values, i) => values[(i[0] * X.shape[1] + i[1]) * X.shape[2] + i[2]];
  assert.equal(await evaluate(`document.querySelector('[data-key="cmpv-case"]').value`), 'scene-a-frame-3', 'The case all three kept comes first');
  const native = await Promise.all(MODELS.map(m => cells('reference', m, R0, C0))), pred = await Promise.all(MODELS.map(m => cells('predicted', m, R0, C0)));
  let agree = 0, differ = 0;
  for (let r = 0; r < R0; r++) for (let c = 0; c < C0; c++) {
    assert.ok(same(native[0].cells[r][c], native[1].cells[r][c]) && same(native[0].cells[r][c], native[2].cells[r][c]), 'The native field is one colour in every column at ' + [r, c]);
    const values = MODELS.map(m => at(X.predicted[m.split('/')[1]], [r, c, 2]));
    if (values[0] !== values[1]) { differ++; assert.ok(!same(pred[0].cells[r][c], pred[1].cells[r][c]), 'Predictions differ at ' + [r, c]); }
    else { agree++; assert.deepEqual(pred[0].cells[r][c], pred[1].cells[r][c], 'Predictions agree at ' + [r, c]); }
  }
  assert.ok(differ > 0 && agree > 0);
  await evaluate(`(() => { document.querySelector('table.cmpv').__mark = 1; document.querySelector('section.cmpv-out').__mark = 2; return true; })()`);
  const before2 = await evaluate(`[...document.querySelectorAll('canvas.cmpv-cv')].map(c => Number(c.dataset.drawn))`), since2 = Date.now();
  await slide(byKey('cmpv-slider-2'), 0); await until(() => asked('field_compare', since2).length >= 3 && !calls.size, 'three requests'); await settled('slider');
  const req2 = asked('field_compare', since2);
  assert.equal(req2.length, 3, 'One field_compare per column'); assert.ok(req2.every(f => JSON.stringify(f.body.index) === '[3,2,0]'), 'All at z = 0');
  const after2 = await evaluate(`[...document.querySelectorAll('canvas.cmpv-cv')].map(c => Number(c.dataset.drawn))`);
  assert.ok(after2.every((n, i) => n > before2[i]), 'Every canvas drawn again: ' + before2 + ' → ' + after2);
  assert.deepEqual(await evaluate(`[document.querySelector('table.cmpv').__mark, document.querySelector('section.cmpv-out').__mark]`), [1, 2], 'The rest of the tab is the same elements');
  assert.equal(new URLSearchParams(await evaluate('location.search')).get('cmpIndex'), '3,2,0', 'The place is in the address');
  await evaluate(`(() => { document.querySelector(${JSON.stringify(cellSel('predicted', MODELS[2]))}).scrollIntoView({ block: 'center' }); return true; })()`); await pause(200);
  const p2 = await cells('predicted', MODELS[2], R0, C0), hr = 4, hc = 3;
  await mouse('mouseMoved', p2.box.left + (p2.cell.x0 + (hc + 0.5) * p2.cell.s) / p2.cell.dpr, p2.box.top + (p2.cell.y0 + (hr + 0.5) * p2.cell.s) / p2.cell.dpr); await pause(150);
  const tip = await evaluate(`(() => { const t = document.querySelector('.cmpv-tip'); return { hidden: t.hidden, model: t.dataset.model, cell: t.dataset.cell, rows: [...t.querySelectorAll('.fld-tip-row')].map(r => r.lastChild.textContent) }; })()`);
  const fmtF = v => evaluate(`window.LabCharts.fmtSci(Math.fround(${v}))`), hi2 = [hr, hc, 0];
  assert.equal(tip.hidden, false); assert.equal(tip.model, MODELS[2]); assert.equal(tip.cell, JSON.stringify(hi2));
  assert.deepEqual(tip.rows, [await fmtF(at(X.reference, hi2)), await fmtF(at(X.predicted['cm-c'], hi2)), await fmtF(Math.fround(at(X.predicted['cm-c'], hi2) - at(X.reference, hi2)))], 'The tip gives the column\'s three values');
  await mouse('mouseMoved', 5, 5);
  await shot('light-1440-2-outputs');
  check('2. Outputs of scene-a-frame-3: the native row one colour in all three columns, the predictions different at ' + differ + ' cells and the same at ' + agree + '; one slider move asked field_compare 3 times and drew all 9 canvases again in place; the tip gives cm-c\'s values');

  // ---- 3 and 4. Benchmarks: parallel coordinates, brushing, intervals --------------------------------------------------
  await load('light', 'benchmark=' + BENCH, 'benchmarks');
  await until(() => evaluate(`!!document.querySelector('.bench-iv') && !!document.querySelector('section.pc svg')`), 'the intervals and parallel coordinates'); await settled('benchmarks with intervals');
  const axes = await evaluate(`[...document.querySelectorAll('section.pc .pc-axis')].map(a => a.dataset.axis)`);
  assert.deepEqual(axes.slice(0, 2), ['m:err', 'm:ms'], 'The metrics first');
  for (const a of ['s:run.settings.learning_rate', 's:run.settings.width', 's:run.settings.optimizer', 's:change']) assert.ok(axes.includes(a), a + ' is an axis: ' + axes);
  assert.ok(!axes.includes('s:run.settings.epochs'), 'A setting the same everywhere is not an axis');
  assert.equal(await evaluate(`document.querySelectorAll('section.pc path.pcl').length`), 5, 'One line per subject');
  // 4. Intervals.
  const iv4 = await evaluate(`(() => ({ whiskers: [...document.querySelectorAll('.bench-chart[data-chart="charts/cmp-ranking"] g.ci')].map(g => [Number(g.dataset.lo), Number(g.dataset.hi), g.parentNode.querySelector('[data-id]').dataset.id]), table: [...document.querySelectorAll('.bench-all tr[data-subject]')].map(r => [r.dataset.subject, [...r.querySelectorAll('td[data-low]')].map(t => [Number(t.dataset.low), Number(t.dataset.high)])]),
    rings: [...document.querySelectorAll('.bench-chart[data-chart="charts/cmp-tradeoff"] circle.nsig')].map(c => c.parentNode.querySelector('[data-id]').dataset.id).sort() }))()`);
  assert.equal(iv4.whiskers.length, 5, 'A whisker per subject on the ranking chart');
  for (const [lo, hi, id] of iv4.whiskers) { const r = ivOf(id.split('/')[1], 'err'); close(lo, r.median[0], 'whisker low'); close(hi, r.median[1], 'whisker high'); }
  for (const [s, cellsOf] of iv4.table) { assert.equal(cellsOf.length, 2, s + ' has two intervals in the table'); close(cellsOf[0][0], ivOf(s, 'err').median[0], s + ' err low'); close(cellsOf[1][1], ivOf(s, 'ms').median[1], s + ' ms high'); }
  assert.deepEqual(iv4.rings, ['recipes/cm-b', 'recipes/cm-c'], 'The frontier points not told apart are ringed');
  await shot('light-1440-4-intervals');
  check('4. Intervals: 5 whiskers on the ranking chart and 10 low – high lines in the table, equal to the intervals operation; dashed rings on ' + iv4.rings.join(' and '));
  // 3. Brushing.
  await evaluate(`(() => { document.querySelector('.bench-all table').__mark = 7; document.querySelector('section.pc').__mark = 8; return true; })()`);
  const line = await evaluate(`(() => { const l = document.querySelector('section.pc .pc-axis[data-axis="m:err"] line.pc-line'); l.scrollIntoView({ block: 'center' }); const r = l.getBoundingClientRect(); return { x: r.left + r.width / 2, top: r.top, bottom: r.bottom }; })()`);
  await pause(200);
  const line2 = await evaluate(`(() => { const r = document.querySelector('section.pc .pc-axis[data-axis="m:err"] line.pc-line').getBoundingClientRect(); return { x: r.left + r.width / 2, top: r.top, bottom: r.bottom }; })()`);
  const since3 = Date.now(), y0 = line2.bottom + 4, y1 = line2.bottom - 0.5 * (line2.bottom - line2.top);
  await mouse('mouseMoved', line2.x, y0); await mouse('mousePressed', line2.x, y0, 1);
  for (let k = 1; k <= 5; k++) { await mouse('mouseMoved', line2.x, y0 + (y1 - y0) * k / 5, 1); await pause(20); }
  await mouse('mouseReleased', line2.x, y1); await pause(300);
  assert.ok(line.x > 0);
  const b3 = await evaluate(`(() => ({ kept: document.querySelector('.pc-count').dataset.kept, rows: [...document.querySelectorAll('.bench-all tr[data-subject]')].filter(r => !r.hidden).map(r => r.dataset.subject), out: [...document.querySelectorAll('.bench-chart g.pc-out [data-id]')].map(e => e.dataset.id), faint: [...document.querySelectorAll('section.pc path.pcl.out')].map(p => p.dataset.subject), note: (document.querySelector('.pc-filtered') || {}).textContent, marks: [document.querySelector('.bench-all table').__mark, document.querySelector('section.pc').__mark], brush: !!document.querySelector('.pc-axis[data-axis="m:err"] .pc-brush') }))()`);
  assert.equal(b3.kept, '3', 'Three subjects inside the range'); assert.deepEqual(b3.rows.slice().sort(), ['cm-b', 'cm-c', 'cm-e'], 'The table keeps the rows inside');
  assert.deepEqual([...new Set(b3.out)].sort(), ['recipes/cm-a', 'recipes/cm-d'], 'The charts make the others faint');
  assert.equal(b3.out.length, 4, 'in both charts'); assert.deepEqual(b3.faint.sort(), ['cm-a', 'cm-d']); assert.ok(/3 rows shown/.test(b3.note), b3.note);
  assert.deepEqual(b3.marks, [7, 8], 'The table and the section are the same elements'); assert.ok(b3.brush);
  assert.equal(asked(null, since3).length, 0, 'Brushing asks nothing');
  await shot('light-1440-3-brushed');
  const since3b = Date.now();
  await press(byKey('pc-right-m:err')); await pause(200);
  const order = await evaluate(`[...document.querySelectorAll('section.pc .pc-axis')].map(a => a.dataset.axis).slice(0, 2)`);
  assert.deepEqual(order, ['m:ms', 'm:err'], 'The error axis moved right');
  await press(byKey('pc-log-m:err')); await pause(200);
  const after3 = await evaluate(`(() => ({ log: document.querySelector('[data-key="pc-log-m:err"]').getAttribute('aria-pressed'), sub: document.querySelector('.pc-axis[data-axis="m:err"] .pc-sub').textContent, kept: document.querySelector('.pc-count').dataset.kept, brush: !!document.querySelector('.pc-axis[data-axis="m:err"] .pc-brush'), mark: document.querySelector('.bench-all table').__mark }))()`);
  assert.equal(after3.log, 'true'); assert.match(after3.sub, /log/); assert.equal(after3.kept, '3', 'The range is kept'); assert.ok(after3.brush); assert.equal(after3.mark, 7);
  assert.equal(asked(null, since3b).length, 0, 'Moving an axis and the log scale ask nothing');
  await press(byKey('pc-clear')); await pause(200);
  const cleared = await evaluate(`(() => ({ rows: [...document.querySelectorAll('.bench-all tr[data-subject]')].filter(r => !r.hidden).length, out: document.querySelectorAll('.bench-chart g.pc-out').length, note: !!document.querySelector('.pc-filtered'), faint: document.querySelectorAll('section.pc path.pcl.out').length }))()`);
  assert.deepEqual(cleared, { rows: 5, out: 0, note: false, faint: 0 }, 'Clear ranges shows everything again');
  check('3. Parallel coordinates over ' + axes.length + ' axes (' + axes.join(', ') + '); a range dragged on the error axis kept cm-b, cm-c and cm-e in the table and made cm-a and cm-d faint in both charts and the lines, with no request; the error axis moved right and on a log scale in place with the range kept; Clear ranges showed all 5 again');

  // ---- 5. Light and dark, 1440 and 390 wide -------------------------------------------------------------------------
  const seen = [];
  for (const [w, hgt] of [[1440, 900], [390, 844]]) for (const name of ['light', 'dark']) for (const tab of ['compare', 'benchmarks']) {
    const tag = name + '-' + w + '-' + tab;
    await size(w, hgt); await load(name, 'benchmark=' + BENCH + '&cmp=' + MODELS.join(','), tab);
    if (tab === 'compare') await drawn(); else await until(() => evaluate(`!!document.querySelector('.bench-iv')`), 'intervals ' + tag);
    await settled(tag);
    const r = await evaluate(`(() => { const m = document.getElementById('main'); const cv = [...m.querySelectorAll('canvas.cmpv-cv')].map(c => { if (!c.width) return 0; const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let n = 0; for (let i = 3; i < d.length; i += 4) if (d[i]) n++; return n; }); const wide = [...m.querySelectorAll('*')].filter(e => e.getBoundingClientRect().right > m.getBoundingClientRect().right + 1 && e.getBoundingClientRect().width > 0 && !e.closest('.tv-wrap')).map(e => e.tagName + '.' + e.className).slice(0, 4); return { cv, page: document.documentElement.scrollWidth - innerWidth, main: m.scrollWidth - m.clientWidth, wide }; })()`);
    assert.ok(r.cv.every(n => n > 10), tag + ': no blank canvas ' + JSON.stringify(r.cv));
    assert.ok(r.main <= 1 && !r.wide.length, tag + ': nothing in the main area overflows sideways ' + JSON.stringify(r));
    await evaluate(`(() => { const s = document.querySelector(${JSON.stringify(tab === 'compare' ? 'section.cmpv-out' : 'section.pc')}); if (s) s.scrollIntoView({ block: 'start' }); return true; })()`); await pause(200);
    await shot(tag + '-5');
    seen.push(tag + (r.page > 0 ? ' (the page ' + r.page + ' px wider: its header)' : ''));
  }
  await size(1440, 900);
  check('5. No blank canvas and nothing in the main area wider than it: ' + seen.join(', ') + (shots ? '; screenshots in ' + shots : ''));

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
  try { execFileSync('chmod', ['-R', 'u+w', temporary]); } catch (_) { /* nothing was made read-only */ }
  fs.rmSync(temporary, { recursive: true, force: true });
});
