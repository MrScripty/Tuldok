'use strict';
// The Sweeps tab (docs/plans/training-and-curation/spec-t7.md sections 7 and 9, slice T7b), in a headless browser, the
// owner signed in, no GPU. Tuldok runs with --project-folder on a project the check writes into a Git repository of
// its own: one recipe, recipes/base, that runs the stand-in tests/project_sweep_stand_in.py (plain Python, logging
// through tuldok_log, which the recipe puts on PYTHONPATH; its loss falls to a floor its settings decide).
//   1. The tab with no sweep says so; New sweep writes a sweep's text from the recipe; the check sets a halving
//      sweep of six trials with two objectives (loss, and time) and keeps it; the tab shows it, not run yet.
//   2. An agent credential asks for a build of the sweep; the page shows that it awaits approval, with Approve.
//      The owner approves it on the tab: one approval for the whole budget.
//   3. While the trials run, the state block's counts, budget and running trial change across readings while the
//      block is the same element and no node of it is added or removed; rows are added to the trials table.
//   4. When the sweep has finished: six trials, some pruned; the frontier chart shows the completed trials and
//      parallel coordinates one line per trial; a range dragged on an axis hides the table's rows outside it.
//   5. A trial's Open on the Map selects it on the Map, in a section of the sweep, its drawer naming it.
//   6. Light and dark at 1440 and 390 wide: nothing overflowing sideways; no script error and no failed request.
//   node tests/browser_project_workspace_sweeps.cjs [--shots <dir>]
const assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const { spawn, execFileSync } = require('node:child_process'), { once } = require('node:events');
const { authenticatedFixture } = require('./auth_helpers.cjs'), { waitForDebugger } = require('./browser_startup.cjs'), { cdpSession } = require('./browser_cdp_session.cjs'), { qaDirectory } = require('./qa_artifacts.cjs');

const root = path.resolve(__dirname, '..');
const argv = process.argv.slice(2), option = name => { const i = argv.indexOf(name); return i >= 0 ? argv[i + 1] : null; };
assert.ok(process.env.TULDOK_DATABASE_URL, 'TULDOK_DATABASE_URL must name a disposable PostgreSQL cluster');
const venv = path.join(root, '.venv', 'bin');
if (fs.existsSync(path.join(venv, 'python'))) process.env.PATH = venv + path.delimiter + process.env.PATH;   // auth_helpers runs python3
const python = fs.existsSync(path.join(venv, 'python')) ? path.join(venv, 'python') : 'python3';
const TRIALS = 6;

const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'tuldok-sweeps-browser-'));
const report = qaDirectory(root, 'project-workspace-sweeps');
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
/** An operation as the owner (the fixture's session); bearer: as that agent credential instead. */
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

// ---- The page's requests, from the browser's network ---------------------------------------------------------------------
const calls = new Map(), finished = [];
function network(event) {
  const p = event.params;
  if (event.method === 'Network.requestWillBeSent' && /\/api\/project\/[a-z_]+$/.test(p.request.url)) calls.set(p.requestId, { name: p.request.url.split('/').pop(), sent: Date.now() });
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
async function click(selector) { await evaluate(`(() => { const b = document.querySelector(${JSON.stringify(selector)}); if (!b) throw Error('no ' + ${JSON.stringify(selector)}); b.click(); return true; })()`); }
async function type(selector, value) { await evaluate(`(() => { const t = document.querySelector(${JSON.stringify(selector)}); t.focus(); t.value = ${JSON.stringify(value)}; t.dispatchEvent(new Event('input', { bubbles: true })); return true; })()`); }
const stateOf = () => evaluate(`(() => { const s = document.querySelector('#main .sw-state'); if (!s) return null; const dd = [...s.querySelectorAll('dd')].map(d => d.textContent); return { chip: s.querySelector('.sw-chip').textContent, run: dd[0], counts: dd[1], trials: dd[2], time: dd[3], running: dd[4], best: dd[5], bar: s.querySelector('.sw-meter .hair i').style.width }; })()`);
const rows = () => evaluate(`[...document.querySelectorAll('#main .sw-table tbody tr')].map(tr => ({ n: Number(tr.dataset.trial), ref: tr.dataset.subject, state: tr.children[3].textContent, hidden: tr.hidden }))`);
const buttonText = text => `[...document.querySelectorAll('#main .sw-controls button')].find(b => b.textContent === ${JSON.stringify(text)})`;

(async () => {
  // ---- The project ----------------------------------------------------------------------------------------------------------
  const repo = path.join(temporary, 'repo'), folder = path.join(repo, 'project'), code = path.join(repo, 'code');
  for (const d of ['recipes', 'environments']) fs.mkdirSync(path.join(folder, d), { recursive: true });
  fs.mkdirSync(code, { recursive: true });
  fs.copyFileSync(path.join(root, 'tests', 'project_sweep_stand_in.py'), path.join(code, 'stand_in.py'));
  const write = (rel, value) => fs.writeFileSync(path.join(folder, rel), JSON.stringify(value, null, 2) + '\n');
  const id = require('node:crypto').randomUUID().replace(/-/g, '');
  write('tuldok.json', { format: 'tuldok_project_v1', id, name: 'Sweep check', code_root: '../code', groups: [{ id: 'small', title: 'Small models' }] });
  const version = execFileSync(python, ['-c', 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")']).toString().trim();
  const jsonschema = execFileSync(python, ['-c', 'import importlib.metadata as m; print(m.version("jsonschema"))']).toString().trim();
  write('environments/here.json', { format: 'tuldok_definition_v1', kind: 'environment', title: 'This interpreter', python: version, device: 'cpu', packages: { jsonschema } });
  write('recipes/base.json', { format: 'tuldok_definition_v1', kind: 'recipe', title: 'The stand-in model', group: 'small', change: 'training-policy', labels: { short: 'BASE' },
    run: { command: ['python', 'stand_in.py', '--settings', '{settings}', '--out', '{output}'], environment: 'environments/here', settings: { learning_rate: 0.01, width: 8, steps: 40, sleep: 0.05 },
      env: { PYTHONPATH: root }, outputs: { weights: { path: 'weights.json', role: 'weights' } }, sources: ['stand_in.py'] } });
  const git = ['-c', 'user.name=Tuldok Test', '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false', '-c', 'init.defaultBranch=main', '-C', repo];
  execFileSync('git', [...git, 'init', '-q']); execFileSync('git', [...git, 'add', '-A']); execFileSync('git', [...git, 'commit', '-q', '-m', 'The project.']);
  const home = path.join(temporary, 'home'), catalog = path.join(temporary, 'catalog'); fs.mkdirSync(home);
  const env = { ...process.env, TULDOK_PROJECT_HOME: home, TULDOK_SETTINGS: path.join(temporary, 'settings.json') };
  owned = [folder, catalog]; dropOwned(folder, catalog);
  execFileSync(python, ['-m', 'tuldok_project', 'connect', folder, 'here', python], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] });
  let output = '';
  server = launch(python, ['-u', 'app.py', '--port', '0', '--data', catalog, '--project-folder', folder], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] });
  server.stdout.on('data', chunk => { output += chunk; }); server.stderr.on('data', chunk => { serverErrors += chunk; });
  const port = await until(() => { if (server.exitCode !== null) throw Error('Tuldok exited: ' + serverErrors); return output.match(/127\.0\.0\.1:(\d+)/)?.[1]; }, 'Tuldok start-up', 3000);
  origin = 'http://127.0.0.1:' + port;
  auth = authenticatedFixture(); await auth.register(origin, catalog, root);

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
  const load = async (name, hash, query) => {
    await theme(name);
    await send('Page.navigate', { url: 'about:blank' }); await pause(100);
    await send('Page.navigate', { url: origin + '/?theme=' + name + (query ? '&' + query : '') + hash });
    await until(() => evaluate(`document.readyState === 'complete' && !!document.getElementById('needs-btn') && !document.getElementById('needs-btn').disabled`), 'the project read', 1200);
    await settled('opened ' + hash);
  };

  // ---- 1. New sweep ------------------------------------------------------------------------------------------------------------
  await size(1440, 900); await load('light', '#sweeps');
  assert.match(await evaluate(`document.querySelector('#main .empty').textContent`), /no sweep yet/);
  await click(byKey('sweep-new')); await settled('new sweep');
  const written = await until(() => evaluate(`(() => { const t = document.querySelector(${JSON.stringify(byKey('sweep-new-text'))}); return t && t.value ? t.value : null; })()`), 'the text written from the recipe');
  const drafted = JSON.parse(written);
  assert.equal(drafted.recipe, 'recipes/base'); assert.deepEqual(drafted.parameters.map(p => p.path).sort(), ['learning_rate', 'sleep', 'steps', 'width']);   // the stored document's order
  await shot('light-1440-1-new');
  const text = JSON.stringify({ format: 'tuldok_definition_v1', kind: 'sweep', title: 'Learning rate and width', recipe: 'recipes/base',
    parameters: [{ path: 'learning_rate', low: 0.001, high: 0.1, scale: 'log' }, { path: 'width', values: [4, 8, 16, 32] }],
    strategy: { kind: 'halving', seed: 3, metric: 'loss', better: 'lower', min: 2, factor: 2 },
    objectives: [{ metric: 'loss', better: 'lower' }, { metric: 'time', better: 'lower', title: 'Seconds' }], budget: { trials: TRIALS } }, null, 2) + '\n';
  await type(byKey('sweep-new-name'), 'lr-width'); await type(byKey('sweep-new-text'), text);
  await click('[data-group="sweep:new"] button'); await settled('kept');
  await until(() => evaluate(`!!document.querySelector('#main .sw-state') && !document.getElementById('drawer').classList.contains('open')`), 'the sweep shown');
  assert.equal(await evaluate(`document.querySelector(${JSON.stringify(byKey('sweep'))}).value`), 'sweeps/lr-width');
  const s1 = await stateOf();
  assert.match(s1.chip, /not run yet/); assert.equal(s1.trials, '0 of ' + TRIALS);
  assert.equal(new URLSearchParams(await evaluate('location.search')).get('sweep'), 'sweeps/lr-width', 'the address keeps the sweep');
  check('1. New sweep wrote a sweep of recipes/base from its settings (' + drafted.parameters.map(p => p.path).join(', ') + '); a halving sweep of ' + TRIALS + ' trials kept as sweeps/lr-width, shown not run yet');

  // ---- 2. Asked for by an agent, approved on the tab ---------------------------------------------------------------------------
  const agent = await credential('A sweep check agent', ['inspect', 'execute']);
  const ask = await api('request_build', { targets: ['sweeps/lr-width'] }, agent);
  assert.equal(ask.state, 'awaiting-approval');
  await evaluate(`window.dispatchEvent(new Event('focus')); true`);
  await until(() => evaluate(`!!(${buttonText('Approve')})`), 'Approve on the tab');
  assert.match(await evaluate(`document.querySelector('#main .sw-ask').textContent`), /One approval covers its whole budget/);
  const s2 = await stateOf(); assert.match(s2.chip, /awaiting approval/);
  await shot('light-1440-2-awaiting');
  // The block is marked before the approval: a reading must never replace it or add or remove a node of it.
  await evaluate(`window.__sw = (() => { const s = document.querySelector('#main .sw-state'); s.__mark = 'state'; const counts = { added: 0, removed: 0 }; new MutationObserver(list => { for (const r of list) { counts.added += r.addedNodes.length; counts.removed += r.removedNodes.length; } }).observe(s, { childList: true, subtree: true }); return { counts, still: () => { const now = document.querySelector('#main .sw-state'); return !!now && now.__mark === 'state'; } }; })(); true`);
  await evaluate(`${buttonText('Approve')}.click(); true`);
  const running = await until(async () => { const s = await stateOf(); return s && /running/.test(s.chip) ? s : null; }, 'the sweep running', 300);
  check('2. An agent asked for the sweep; the tab showed it awaiting approval with Approve and the sentence that one approval covers the budget; the owner approved it there and it runs');

  // ---- 3. Live, in place ---------------------------------------------------------------------------------------------------------
  const seen = [running];
  for (let i = 0; i < 3; i++) {
    const before = seen[seen.length - 1];
    const next = await until(async () => { const s = await stateOf(); return s && (s.counts !== before.counts || s.running !== before.running) ? s : null; }, 'the state changes (' + i + ')', 300);
    seen.push(next);
    assert.ok(await evaluate('window.__sw.still()'), 'the state block is the same element after a reading');
  }
  const counts3 = await evaluate('window.__sw.counts');
  assert.deepEqual([counts3.added, counts3.removed], [0, 0], 'no node of the state block added or removed: ' + JSON.stringify(counts3));
  const rowsLive = (await rows()).length;
  await shot('light-1440-3-live');
  check('3. While it ran the state changed in place across readings (' + seen.map(s => s.counts.replace(/ · /g, '/')).join(' → ') + '; running: ' + seen.map(s => s.running).slice(-2).join(' → ') + '), the block the same element, no node of it added or removed; ' + rowsLive + ' rows in the table so far');

  // ---- 4. Finished: the frontier, parallel coordinates, the table ----------------------------------------------------------------
  const done = await until(async () => { const r = (await api('build_request', { request: ask.id })); return ['succeeded', 'failed', 'cancelled'].includes(r.state) ? r : null; }, 'the sweep ends', 1200);
  assert.equal(done.state, 'succeeded', done.problem);
  const answer = await api('sweep', { sweep: 'lr-width' });
  await until(async () => { const s = await stateOf(); return /finished/.test(s.chip) && (await rows()).length === TRIALS; }, 'the tab shows it finished', 300);
  assert.ok(await evaluate('window.__sw.still()'), 'the state block is still the same element');
  const states = answer.trials.map(t => t.state), completed = states.filter(s => s === 'completed').length;
  assert.equal(states.length, TRIALS); assert.ok(states.includes('pruned'), 'halving pruned some trials: ' + states);
  const table = await rows();
  assert.deepEqual(table.map(r => r.n), answer.trials.map(t => t.number));
  assert.deepEqual(table.map(r => r.state.split(' ')[0]), states);
  const points = await evaluate(`document.querySelectorAll('#main .sw-chart circle.pt').length`);
  assert.equal(points, completed, 'the frontier chart draws each completed trial');
  const frontierLine = await evaluate(`!!document.querySelector('#main .sw-chart path.frontier') || ${answer.frontier.length} < 2`);
  assert.ok(frontierLine, 'the frontier is drawn');
  const lines = await evaluate(`document.querySelectorAll('#main .sw-pc path.pcl').length`);
  assert.equal(lines, TRIALS, 'one line a trial in parallel coordinates');
  const axes = await evaluate(`[...document.querySelectorAll('#main .sw-pc .pc-axis')].map(g => g.dataset.axis)`);
  assert.deepEqual(axes, ['m:loss', 'm:time', 's:learning_rate', 's:width']);
  // A range dragged on the loss axis keeps the best trials; the table hides the rest.
  await evaluate(`document.querySelector('#main .sw-pc').scrollIntoView({ block: 'center' }); true`); await frames();
  const box2 = await evaluate(`(() => { const r = document.querySelector('#main .sw-pc .pc-hit[data-axis="m:loss"]').getBoundingClientRect(); return { x: r.x + r.width / 2, top: r.y + 8, bottom: r.y + r.height - 8 }; })()`);
  const lowY = box2.bottom, highY = box2.bottom - (box2.bottom - box2.top) * 0.5;
  await send('Input.dispatchMouseEvent', { type: 'mousePressed', x: box2.x, y: lowY, button: 'left', clickCount: 1 });
  await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x: box2.x, y: highY, button: 'left' });
  await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: box2.x, y: highY, button: 'left', clickCount: 1 });
  await frames();
  const filtered = await rows();
  const hiddenRows = filtered.filter(r => r.hidden).length;
  assert.ok(hiddenRows > 0 && hiddenRows < TRIALS, 'a range on the loss axis hides some rows: ' + JSON.stringify(filtered));
  await shot('light-1440-4-finished');
  await click(byKey('pc-clear')); await frames();
  assert.equal((await rows()).filter(r => r.hidden).length, 0, 'Clear ranges shows every row');
  check('4. Finished: ' + states.join(', ') + '; the frontier chart drew the ' + completed + ' completed trials (' + answer.frontier.length + ' on the frontier), parallel coordinates ' + lines + ' lines through ' + axes.join(', ') + '; a range on the loss axis hid ' + hiddenRows + ' rows, Clear ranges showed them');

  // ---- 5. A trial on the Map --------------------------------------------------------------------------------------------------------
  const trial = answer.trials[0];
  await click(byKey('sweep-map-' + trial.number)); await settled('the map');
  assert.equal(await evaluate('location.hash'), '#map/' + encodeURIComponent(trial.reference));
  await until(() => evaluate(`(() => { const h = document.querySelector('#aside h2'); return h && h.textContent === ${JSON.stringify('Learning rate and width · trial ' + trial.number)}; })()`), 'the trial\'s drawer on the Map');
  const section = await evaluate(`[...document.querySelectorAll('#main h3, #main text.bandlabel')].map(e => e.title || (e.querySelector('title') || {}).textContent || e.textContent).find(t => /Learning rate and width/.test(t)) || null`);
  assert.equal(section, 'Small models / Learning rate and width', 'the map has a section of the sweep under its recipe\'s group');
  const chip = await evaluate(`document.querySelector('#aside .ins-meta .chip').textContent`);
  assert.equal(chip, 'Sweep trial');
  await shot('light-1440-5-map');
  check('5. Open on the Map selected ' + trial.reference + ' on the Map: its drawer names it, its kind of change "Sweep trial", in the section "' + section + '"');

  // ---- 6. Light and dark, 1440 and 390 wide ---------------------------------------------------------------------------------------
  const seen6 = [];
  for (const [w, hgt] of [[1440, 900], [390, 844]]) for (const name of ['light', 'dark']) {
    const tag = name + '-' + w;
    await size(w, hgt); await load(name, '#sweeps', 'sweep=sweeps/lr-width');
    await until(() => evaluate(`document.querySelectorAll('#main .sw-pc path.pcl').length === ${TRIALS}`), tag + ': drawn');
    const r = await evaluate(`(() => { const m = document.getElementById('main'); const wide = [...m.querySelectorAll('*')].filter(e => { const b = e.getBoundingClientRect(); return b.width > 0 && b.right > m.getBoundingClientRect().right + 1 && !e.closest('.tv-wrap'); }).map(e => e.tagName + '.' + (typeof e.className === 'string' ? e.className : '')).slice(0, 4); return { page: document.documentElement.scrollWidth - innerWidth, main: m.scrollWidth - m.clientWidth, wide }; })()`);
    assert.ok(r.page <= 0 && r.main <= 1 && !r.wide.length, tag + ': nothing overflows sideways ' + JSON.stringify(r));
    await shot(tag + '-6-sweeps');
    seen6.push(tag);
  }
  await size(1440, 900);
  check('6. The tab drawn with nothing overflowing sideways outside the table\'s own scrolling box: ' + seen6.join(', ') + (shots ? '; screenshots in ' + shots : ''));

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
