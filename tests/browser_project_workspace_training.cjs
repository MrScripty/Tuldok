'use strict';
// What a training script logged, drawn live in a run's drawer on the Train tab
// (docs/plans/training-and-curation/spec-t1.md sections 6 and 8, slice T1c), in a headless browser, the owner signed
// in, no GPU. Tuldok runs with --project-folder on a copy of the minimal fixture with the buildable fixture's
// definitions beside it, in a Git repository of its own, and three recipes that run a stand-in training script
// (tests/project_training_stand_in.py: a linear model fitted in plain Python, logged through tuldok_log, which the
// recipe puts on PYTHONPATH): trainer-a and trainer-b are built before Tuldok starts (sixty steps, finished in a
// moment), trainer-live is asked for while the page watches and runs about ten seconds.
//   1. trainer-a's drawer shows Training: the loss drawn, with trainer-b overlaid from "Compare with" (two lines,
//      a legend of two); the address keeps it, and a reload draws the same.
//   2. Smoothing, log scale and By time draw the chart again (another image), the block the same element; another
//      series chosen adds its chart.
//   3. Histograms drawn (strips not blank, one per tensor, weights and gradients) and samples drawn (images
//      loaded, arrays drawn, steps under them).
//   4. trainer-live, opened while it runs: its curve grows across readings (more points, a later last step) while
//      a marker on the block, its chart and its strips survives and no node of the block is added or removed
//      outside the samples strip (where new samples are appended); when it ends, all sixty lines are drawn.
//   5. With the finished run open, a return to the window touches nothing in the drawer.
//   6. Light and dark at 1440 and 390 wide: no blank chart, nothing overflowing sideways; no script error and no
//      failed request.
//   node tests/browser_project_workspace_training.cjs [--shots <dir>]
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
const STEPS = 60, LIVE_STEPS = 50, LIVE_SLEEP = 0.25;

const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'tuldok-training-browser-'));
const report = qaDirectory(root, 'project-workspace-training');
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

// ---- The page's requests, from the browser's network ---------------------------------------------------------------------
const calls = new Map(), finished = [];
function network(event) {
  const p = event.params;
  if (event.method === 'Network.requestWillBeSent' && /\/api\/project\/[a-z_]+$/.test(p.request.url)) { let body = null; try { body = p.request.postData ? JSON.parse(p.request.postData) : null; } catch (_) { body = null; } calls.set(p.requestId, { name: p.request.url.split('/').pop(), body, sent: Date.now() }); }
  if ((event.method === 'Network.loadingFinished' || event.method === 'Network.loadingFailed') && calls.has(p.requestId)) { finished.push(Object.assign(calls.get(p.requestId), { done: Date.now() })); calls.delete(p.requestId); }
}
const asked = (name, since = 0) => finished.concat([...calls.values()]).filter(f => f.name === name && f.sent >= since);
async function settled(label) {
  await until(() => evaluate(`(() => { const a = document.getElementById('aside'), m = document.getElementById('main'); return ![...a.querySelectorAll('.note'), ...m.querySelectorAll('.note')].some(n => n.textContent === 'Reading…') && !a.querySelector('[aria-busy]') && !m.hasAttribute('aria-busy'); })()`).then(ok => ok && !calls.size), 'settled: ' + label);
  await pause(250);
}
async function frames() { await evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))'); }
async function shot(name) {
  await frames();
  const png = Buffer.from((await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false })).data, 'base64');
  fs.writeFileSync(path.join(report, name + '.png'), png); if (shots) fs.writeFileSync(path.join(shots, name + '.png'), png);
}
const byKey = key => `[data-key=${JSON.stringify(key)}]`;
async function choose(selector, value) { await evaluate(`(() => { const s = document.querySelector(${JSON.stringify(selector)}); s.focus(); s.value = ${JSON.stringify(value)}; s.dispatchEvent(new Event('change', { bubbles: true })); return true; })()`); }
async function slide(selector, value) { await evaluate(`(() => { const r = document.querySelector(${JSON.stringify(selector)}); r.focus(); r.value = ${JSON.stringify(String(value))}; r.dispatchEvent(new Event('input', { bubbles: true })); return true; })()`); }
async function click(selector) { await evaluate(`(() => { const b = document.querySelector(${JSON.stringify(selector)}); b.click(); return true; })()`); }
// What a canvas shows: a sum over its pixels that changes when the drawing does, and how many are drawn.
const PIXELS = `c => { if (!c || !c.width) return null; const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data; let drawn = 0, sum = 0; for (let i = 0; i < d.length; i += 4) if (d[i + 3]) { drawn++; sum = (sum + (i / 4 + 1) * (d[i] * 3 + d[i + 1] * 5 + d[i + 2] * 7)) % 2147483647; } return { drawn, sum, points: Number(c.dataset.points || 0), lines: Number(c.dataset.lines || 0), last: Number(c.dataset.last || -1), times: Number(c.dataset.drawn || 0) }; }`;
const chart = series => evaluate(`(${PIXELS})(document.querySelector('#aside .trn canvas.trn-chart[data-series=${JSON.stringify(series)}]'))`);
const block = () => evaluate(`(() => { const t = document.querySelector('#aside .trn'); if (!t) return null; return { run: t.dataset.run, legend: [...t.querySelectorAll('.trn-legend li')].map(li => li.dataset.run), charts: [...t.querySelectorAll('canvas.trn-chart')].map(c => c.dataset.series), strips: [...t.querySelectorAll('canvas.trn-strip')].map(c => [c.dataset.tensor, c.dataset.kind, Number(c.dataset.drawn || 0)]), samples: [...t.querySelectorAll('.trn-sample')].map(f => Number(f.dataset.step)), at: (t.querySelector('.trn-at') || {}).textContent || '', none: (t.querySelector('.trn-none') || {}).textContent || null }; })()`);

(async () => {
  // ---- The fixture -----------------------------------------------------------------------------------------------------------
  fs.cpSync(path.join(root, 'tests', 'fixtures', 'tuldok_project', 'minimal'), path.join(temporary, 'fixture'), { recursive: true });
  const folder = path.join(temporary, 'fixture', 'project'), code = path.join(temporary, 'fixture', 'code'), buildable = path.join(root, 'tests', 'fixtures', 'tuldok_project', 'buildable');
  for (const kind of ['environments', 'datasets', 'recipes', 'benchmarks', 'charts']) for (const name of fs.readdirSync(path.join(buildable, 'project', kind))) fs.copyFileSync(path.join(buildable, 'project', kind, name), path.join(folder, kind, name));
  for (const name of fs.readdirSync(path.join(buildable, 'code'))) fs.cpSync(path.join(buildable, 'code', name), path.join(code, name), { recursive: true });
  fs.copyFileSync(path.join(root, 'tests', 'project_training_stand_in.py'), path.join(code, 'logged_train.py'));
  const recipe = (name, title, short, args) => fs.writeFileSync(path.join(folder, 'recipes', name + '.json'), JSON.stringify({ format: 'tuldok_definition_v1', kind: 'recipe', title, labels: { short }, change: 'training-policy', derived_from: 'recipes/fit-a',
    run: { command: ['python', 'logged_train.py', '--out', '{output}', ...args], environment: 'environments/test-python', env: { PYTHONPATH: root }, outputs: { weights: { path: 'weights.json', role: 'weights' } }, sources: ['logged_train.py'] } }, null, 2) + '\n');
  recipe('trainer-a', 'Stand-in trainer, rate 0.05', 'TRA', ['--steps', String(STEPS), '--lr', '0.05', '--seed', '1']);
  recipe('trainer-b', 'Stand-in trainer, rate 0.02', 'TRB', ['--steps', String(STEPS), '--lr', '0.02', '--seed', '1']);
  recipe('trainer-live', 'Stand-in trainer, slowed', 'TRL', ['--steps', String(LIVE_STEPS), '--lr', '0.05', '--seed', '2', '--sleep', String(LIVE_SLEEP)]);
  const git = ['-c', 'user.name=Tuldok Test', '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false', '-c', 'init.defaultBranch=main', '-C', path.join(temporary, 'fixture')];
  execFileSync('git', [...git, 'init', '-q']); execFileSync('git', [...git, 'add', '-A']); execFileSync('git', [...git, 'commit', '-q', '-m', 'The fixture.']);
  const home = path.join(temporary, 'home'), catalog = path.join(temporary, 'catalog'); fs.mkdirSync(home);
  const env = { ...process.env, TULDOK_PROJECT_HOME: home, TULDOK_SETTINGS: path.join(temporary, 'settings.json') };
  owned = [folder, catalog]; dropOwned(folder, catalog);
  const cli = (...args) => execFileSync(python, ['-m', 'tuldok_project', ...args], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] }).toString();
  cli('connect', folder, 'test-python', python);
  cli('build', folder, 'recipes/trainer-a', '--yes'); cli('build', folder, 'recipes/trainer-b', '--yes');
  let output = '';
  server = launch(python, ['-u', 'app.py', '--port', '0', '--data', catalog, '--project-folder', folder], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] });
  server.stdout.on('data', chunk => { output += chunk; }); server.stderr.on('data', chunk => { serverErrors += chunk; });
  const port = await until(() => { if (server.exitCode !== null) throw Error('Tuldok exited: ' + serverErrors); return output.match(/127\.0\.0\.1:(\d+)/)?.[1]; }, 'Tuldok start-up', 3000);
  origin = 'http://127.0.0.1:' + port;
  auth = authenticatedFixture(); await auth.register(origin, catalog, root);
  const runs = (await api('runs')).runs, runA = runs.find(r => r.reference === 'recipes/trainer-a').id, runB = runs.find(r => r.reference === 'recipes/trainer-b').id;
  for (const id of [runA, runB]) { const o = await api('training', { run: id }); assert.equal(o.lines, STEPS, 'the stand-in logged every step'); }

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
  await auth.browser(send, origin);
  /** Opens a run's drawer on the Train tab in a theme with the address's settings (a page of its own). */
  const load = async (name, run, query) => {
    await theme(name);
    await send('Page.navigate', { url: 'about:blank' }); await pause(100);
    await send('Page.navigate', { url: origin + '/?theme=' + name + (query ? '&' + query : '') + '#train/' + encodeURIComponent('run:' + run) });
    await until(() => evaluate(`document.readyState === 'complete' && !!document.getElementById('needs-btn') && !document.getElementById('needs-btn').disabled`), 'the project read', 1200);
    await until(() => evaluate(`!!document.querySelector('#aside .trn')`), 'the Training block');
    await settled('opened ' + run);
  };
  const drawnChart = (series, lines) => until(async () => { const c = await chart(series); return c && c.times > 0 && c.drawn > 100 && (!lines || c.lines === lines) ? c : null; }, 'the chart of ' + series);

  // ---- 1. trainer-a with trainer-b overlaid --------------------------------------------------------------------------------------
  await size(1440, 900); await load('light', runA);
  const one = await drawnChart('loss', 1);
  let b1 = await block();
  assert.deepEqual(b1.legend, [runA], 'one run in the legend'); assert.deepEqual(b1.charts, ['loss'], 'the loss is drawn first');
  assert.equal(one.points, STEPS, 'every logged step is a point'); assert.equal(one.last, STEPS);
  assert.match(b1.at, new RegExp('Step ' + STEPS + ' '));
  await choose(byKey('trn-with'), runB); await settled('compared');
  const two = await drawnChart('loss', 2);
  b1 = await block();
  assert.deepEqual(b1.legend, [runA, runB], 'two runs in the legend'); assert.equal(two.points, 2 * STEPS);
  const query1 = (await evaluate('location.search')).replace(/^\?/, '').split('&').filter(p => !p.startsWith('theme=')).join('&');
  assert.equal(new URLSearchParams(query1).get('trWith'), runB, 'the address keeps the run compared with');
  await load('light', runA, query1);
  const two2 = await drawnChart('loss', 2);
  assert.equal(two2.sum, two.sum, 'a reload draws the same');
  await shot('light-1440-1-overlaid');
  check('1. ' + runA.slice(0, 8) + ' drew its loss (' + one.points + ' points, last step ' + one.last + '); "Compare with" added ' + runB.slice(0, 8) + ': two lines, a legend of two; the address kept trWith and a reload drew the same image');

  // ---- 2. Smoothing, log scale, by time; another series ----------------------------------------------------------------------------
  await evaluate(`(() => { document.querySelector('#aside .trn').__mark = 1; document.querySelector('#aside canvas.trn-chart').__mark = 2; return true; })()`);
  const marks = () => evaluate(`(() => { const t = document.querySelector('#aside .trn'), c = document.querySelector('#aside canvas.trn-chart'); return [t && t.__mark, c && c.__mark]; })()`);
  const since2 = Date.now(), images = [two2.sum];
  await slide(byKey('trn-smooth'), 0.8); await frames(); images.push((await chart('loss')).sum);
  await click(byKey('trn-log')); await frames(); images.push((await chart('loss')).sum);
  await choose(byKey('trn-x'), 'time'); await frames(); images.push((await chart('loss')).sum);
  assert.equal(new Set(images).size, 4, 'each control draws another image: ' + images);
  assert.deepEqual(await marks(), [1, 2], 'the block and the chart are the same elements');
  assert.equal(asked('training_series', since2).length + asked('training', since2).length, 0, 'drawing again asks nothing');
  const q2 = new URLSearchParams(await evaluate('location.search'));
  assert.deepEqual([q2.get('trSmooth'), q2.get('trLog'), q2.get('trX')], ['0.8', '1', 'time']);
  await shot('light-1440-2-smoothed-log-time');
  await click(byKey('trn-series-val/loss')); await settled('val/loss');
  const val = await drawnChart('val/loss', 2);
  assert.deepEqual((await block()).charts, ['loss', 'val/loss']); assert.equal(val.points, 2 * STEPS / 10, 'val/loss has a point every ten steps');
  assert.equal((await marks())[0], 1, 'a series added builds the content in the same block');
  check('2. Smoothing 0.8, log scale and by time each drew another image (' + images.join(' → ') + ') with nothing asked and the block and chart the same elements; the address kept them; val/loss added its chart (' + val.points + ' points)');

  // ---- 3. Histograms and samples -----------------------------------------------------------------------------------------------------
  const intoView = sel => evaluate(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); if (e) e.scrollIntoView({ block: 'start' }); return !!e; })()`);
  await intoView('#aside .trn-hists');   // a strip is read when it comes on screen
  const strips = await until(async () => { const b = await block(); return b.strips.length === 2 && b.strips.every(s => s[2] > 0) ? b.strips : null; }, 'the strips drawn');
  assert.deepEqual(strips.map(s => s.slice(0, 2)), [['linear.weight', 'weights'], ['linear.bias', 'weights']]);
  const stripPixels = await evaluate(`[...document.querySelectorAll('#aside canvas.trn-strip')].map(c => (${PIXELS})(c).drawn)`);
  assert.ok(stripPixels.every(n => n > 200), 'the strips are not blank ' + stripPixels);
  const stripRows = await evaluate(`[...document.querySelectorAll('#aside canvas.trn-strip')].map(c => Number(c.dataset.rows))`);
  assert.deepEqual(stripRows, [STEPS / 5 + 1, STEPS / 5 + 1], 'one column a logged step (every five, and the first)');
  await click(byKey('trn-kind-gradients')); await settled('gradients'); await intoView('#aside .trn-hists');
  await until(async () => { const b = await block(); return b.strips.length === 2 && b.strips.every(s => s[1] === 'gradients' && s[2] > 0); }, 'the gradients drawn');
  const samples = (await block()).samples;
  assert.deepEqual(samples, [10, 20, 30, 40, 50, 60], 'the samples strip, newest last');
  const arrays = await until(() => evaluate(`(() => { const c = [...document.querySelectorAll('#aside .trn-sample canvas')]; return c.length === 6 && c.every(x => Number(x.dataset.drawn) > 0) ? c.map(x => (${PIXELS})(x).drawn) : null; })()`), 'the array samples drawn');
  assert.ok(arrays.every(n => n > 100), 'array samples not blank');
  await choose(byKey('trn-sample'), 'prediction'); await settled('prediction samples');
  const loaded = await until(() => evaluate(`(() => { const i = [...document.querySelectorAll('#aside .trn-sample img')]; return i.length === 6 && i.every(x => x.complete && x.naturalWidth === 8) ? i.length : null; })()`), 'the PNG samples loaded');
  await evaluate(`document.querySelector('#aside .trn-hists').scrollIntoView(); true`); await shot('light-1440-3-histograms-samples');
  check('3. Histograms: ' + strips.length + ' strips of ' + stripRows[0] + ' steps each, not blank (' + stripPixels + ' pixels), weights then gradients; samples: ' + arrays.length + ' arrays drawn at steps ' + samples.join(', ') + ', and ' + loaded + ' PNG images loaded');

  // ---- 4. A run drawn live -----------------------------------------------------------------------------------------------------------
  await load('light', runA, '');   // no settings: the loss alone, by step
  const asking = await api('request_build', { targets: ['recipes/trainer-live'] });
  const liveRun = await until(async () => { const r = (await api('runs')).runs.find(x => x.reference === 'recipes/trainer-live' && x.state === 'running'); return r ? r.id : null; }, 'the live run running', 300);
  // The page learns of a build asked for elsewhere on its next reading (at most fifteen seconds while idle, spec-w4 R1);
  // a return to the window makes that reading now, and from then on it reads every two seconds while the run runs.
  await evaluate(`window.dispatchEvent(new Event('focus')); true`);
  await evaluate(`location.hash = '#train/' + encodeURIComponent('run:${liveRun}'); true`);
  // From its tenth step it has logged every name it will (val/loss, the samples): from then on a reading adds nothing but points and samples.
  await until(async () => { const b = await block(); return b && b.samples.length && (await evaluate(`!!document.querySelector('#aside [data-series="val/loss"]')`)); }, 'the live run\'s names', 300);
  // From its tenth step it has logged every name it will (val/loss, the samples): from then on a reading adds nothing but points and samples.
  await until(async () => { const b = await block(); return b && b.samples.length > 0 && await evaluate(`!!document.querySelector('#aside [data-series="val/loss"]')`); }, 'the live run\'s names', 300);
  const first = await until(async () => { const c = await chart('loss'); return c && c.points >= 3 ? c : null; }, 'the live run\'s first points', 300);
  await evaluate(`window.__trn = (() => { const t = document.querySelector('#aside .trn'); t.__mark = 'live'; t.querySelector('canvas.trn-chart').__mark = 'chart'; for (const c of t.querySelectorAll('canvas.trn-strip')) c.__mark = 'strip';
    const counts = { added: 0, removed: 0, what: [] }; new MutationObserver(list => { for (const r of list) { if (r.target.closest && r.target.closest('.trn-samples')) continue; if (r.type === 'childList' && (r.addedNodes.length || r.removedNodes.length)) { counts.added += r.addedNodes.length; counts.removed += r.removedNodes.length; if (counts.what.length < 6) counts.what.push(r.target.className); } } }).observe(t, { childList: true, subtree: true });
    return { counts, still: () => { const now = document.querySelector('#aside .trn'); return !!now && now.__mark === 'live' && now.querySelector('canvas.trn-chart').__mark === 'chart' && [...now.querySelectorAll('canvas.trn-strip')].every(c => c.__mark === 'strip'); } }; })(); true`);
  const seenPoints = [first.points], seenLast = [first.last];
  for (let i = 0; i < 3; i++) {
    const before = seenPoints[seenPoints.length - 1];
    const c = await until(async () => { const x = await chart('loss'); return x && x.points > before ? x : null; }, 'the curve grows (' + i + ')', 100);
    seenPoints.push(c.points); seenLast.push(c.last);
    const kept = await evaluate('window.__trn.still()'); assert.ok(kept, 'the block, its chart and its strips are the same elements after a reading');
  }
  const counts4 = await evaluate('window.__trn.counts');
  assert.deepEqual([counts4.added, counts4.removed], [0, 0], 'no node of the block added or removed by the readings: ' + JSON.stringify(counts4));
  const grownSamples = (await block()).samples;
  await shot('light-1440-4-live');
  const ended = await until(async () => { const r = (await api('runs')).runs.find(x => x.id === liveRun); return r.state !== 'running' ? r.state : null; }, 'the live run ends', 400);
  assert.equal(ended, 'succeeded');
  const last4 = await until(async () => { const c = await chart('loss'); const b = await block(); return c && c.points === LIVE_STEPS && !/read live/.test(b.at) ? c : null; }, 'all its lines drawn once it ended', 300);
  assert.equal(last4.last, LIVE_STEPS);
  assert.equal(asking.state, 'queued');
  check('4. ' + liveRun.slice(0, 8) + ' opened while running: points ' + seenPoints.join(' → ') + ', last step ' + seenLast.join(' → ') + ' across readings, the block, its chart and strips the same elements, no node added or removed outside the samples strip (samples now ' + grownSamples.join(', ') + '); ended ' + ended + ' with all ' + last4.points + ' points drawn');

  // ---- 5. A return to the window touches nothing -------------------------------------------------------------------------------------
  await settled('after the live run');
  await pause(500);
  await evaluate(`window.__quiet = { n: 0, what: [] }; new MutationObserver(list => { for (const r of list) { window.__quiet.n++; if (window.__quiet.what.length < 6) window.__quiet.what.push(r.type + ' ' + (r.target.className || r.target.nodeName)); } }).observe(document.getElementById('aside'), { childList: true, subtree: true, characterData: true, attributes: true }); true`);
  const since5 = Date.now();
  await evaluate(`window.dispatchEvent(new Event('focus')); true`);
  await until(() => WATCHED.every(name => finished.some(f => f.name === name && f.sent >= since5)), 'the reading on focus');
  await settled('focus'); await pause(700);
  const quiet = await evaluate('window.__quiet');
  assert.equal(quiet.n, 0, 'a return to the window touches nothing in the drawer: ' + JSON.stringify(quiet));
  assert.equal(asked('training', since5).length + asked('training_series', since5).length, 0, 'and asks nothing of the training');
  check('5. With the finished run open, a return to the window read the project and touched nothing in the drawer, nothing of its training asked');

  // ---- 6. Light and dark, 1440 and 390 wide --------------------------------------------------------------------------------------------
  const seen6 = [];
  for (const [w, hgt] of [[1440, 900], [390, 844]]) for (const name of ['light', 'dark']) {
    const tag = name + '-' + w;
    await size(w, hgt); await load(name, runA, 'trWith=' + runB + '&trSeries=loss,grad_norm');
    await drawnChart('loss', 2); await drawnChart('grad_norm', 2);
    const r = await evaluate(`(() => { const a = document.getElementById('aside'), t = a.querySelector('.trn'); const cv = [...t.querySelectorAll('canvas.trn-chart')].map(c => (${PIXELS})(c).drawn); const wide = [...t.querySelectorAll('*')].filter(e => { const b = e.getBoundingClientRect(); return b.width > 0 && b.right > a.getBoundingClientRect().right + 1 && !e.closest('.trn-samples'); }).map(e => e.tagName + '.' + e.className).slice(0, 4); return { cv, page: document.documentElement.scrollWidth - innerWidth, aside: a.scrollWidth - a.clientWidth, wide }; })()`);
    assert.ok(r.cv.every(n => n > 100), tag + ': no blank chart ' + JSON.stringify(r.cv));
    assert.ok(r.page <= 0 && r.aside <= 1 && !r.wide.length, tag + ': nothing overflows sideways ' + JSON.stringify(r));
    await shot(tag + '-6-training');
    seen6.push(tag);
  }
  await size(1440, 900);
  check('6. Two charts of two runs drawn and nothing overflowing sideways: ' + seen6.join(', ') + (shots ? '; screenshots in ' + shots : ''));

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
