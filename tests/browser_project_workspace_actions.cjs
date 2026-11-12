'use strict';
// The controls of the project workspace (docs/plans/definition-first-projects/spec-w3.md section 3.1, slice T21) in a
// headless browser. Tuldok runs with --project-folder on a copy of the minimal fixture with the buildable fixture's
// definitions beside it, committed to a Git repository of its own so builds run from a commit. Two more recipes have
// stand-in commands that train nothing: recipes/slow prints a progress line every half second for about four
// seconds; recipes/hold prints one every half second until it is cancelled. An agent credential asks for two builds.
// Signed in as the owner the check: approves one from Needs you and, with the model's drawer open on the Map, sees
// the strip's hairline partly filled while it runs and then the model built, without a reload; declines the other
// with a reason and sees the reason; plans the hold recipe from Train and requests it, and reads its run live (the
// hairline, the progress line, the log growing); while that runs, plans a model from its drawer and one from Train,
// requests each and cancels each with two presses (Escape leaves the two-press state, and the state outlives the
// two-second refresh); provokes a refusal (a plan with a blocked target, an interpreter path that is not absolute)
// and sees it inline; cancels the running run; connects an environment and checks one again; saves an unsaved edit
// from the strip; makes a conflict twice and resolves it both ways. Signed in with a credential that may only
// inspect, no control is drawn. Each new surface is captured in light and dark. It fails on any script error, any
// failed request other than the refusals it provokes, sideways overflow, or a control left disabled.
//   node tests/browser_project_workspace_actions.cjs
const assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const { spawn, execFileSync } = require('node:child_process'), { once } = require('node:events');
const { authenticatedFixture } = require('./auth_helpers.cjs'), { waitForDebugger } = require('./browser_startup.cjs'), { cdpSession } = require('./browser_cdp_session.cjs'), { qaDirectory, screenshotOptions } = require('./qa_artifacts.cjs');

const root = path.resolve(__dirname, '..');
assert.ok(process.env.TULDOK_DATABASE_URL, 'TULDOK_DATABASE_URL must name a disposable PostgreSQL cluster');
const venv = path.join(root, '.venv', 'bin');
if (fs.existsSync(path.join(venv, 'python'))) process.env.PATH = venv + path.delimiter + process.env.PATH;   // auth_helpers runs python3
const python = fs.existsSync(path.join(venv, 'python')) ? path.join(venv, 'python') : 'python3';
const WIDTH = 1440, HEIGHT = 900;

const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'tuldok-actions-browser-'));
const report = qaDirectory(root, 'project-workspace-actions');
const children = [], checks = [], errors = [], failures = [], allowed = [], bounds = [];
let server, serverErrors = '', origin, auth, socket, session, send, evaluate, folder, owned = null;
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

// ---- The page ------------------------------------------------------------------
/** Refusals provoked on purpose: a failed request is allowed while its window is open and it matches. */
function allow(re, status) { const entry = { re, status, from: Date.now(), to: Infinity, seen: 0 }; allowed.push(entry); return entry; }
function close(entry) { entry.to = Date.now() + 500; }
function failure(url, status, text) {
  const at = Date.now(), entry = allowed.slice().reverse().find(a => a.re.test(url || '') && (a.status === null || a.status === status) && a.from <= at && at <= a.to);
  if (entry) entry.seen++; else failures.push({ url, status, text });
}
async function shot(name) {
  await evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))');
  fs.writeFileSync(path.join(report, name + '.jpg'), Buffer.from((await send('Page.captureScreenshot', screenshotOptions)).data, 'base64'));
}
/** The same view in light and dark, switched in place (a reload would lose a two-press state). */
async function shots(name) {
  for (const theme of ['light', 'dark']) {
    await evaluate(`(() => { document.documentElement.setAttribute('data-theme', '${theme}'); const b = document.getElementById('theme'); b.lastChild.textContent = ' ${theme === 'dark' ? 'Dark' : 'Light'}'; })()`);
    await inspect(theme + ' ' + name); await shot(theme + '-' + name);
  }
  await evaluate(`(() => { document.documentElement.setAttribute('data-theme', 'light'); document.getElementById('theme').lastChild.textContent = ' Light'; })()`);
}
/** No sideways overflow (page, main, top bar, strip, drawer), no control left disabled or waiting, nothing outside the drawer. */
async function inspect(label) {
  const value = await evaluate(`(() => {
    const main = document.getElementById('main'), top = document.querySelector('.top'), strip = document.getElementById('strip'), drawer = document.getElementById('drawer');
    const open = drawer.classList.contains('open'), dr = drawer.getBoundingClientRect();
    const outside = open ? [...drawer.querySelectorAll('button, input, textarea, select, p, li, h2, h3')].filter(e => e.offsetParent !== null).map(e => [e, e.getBoundingClientRect()]).filter(([e, r]) => r.width && (r.right > dr.right + 1 || r.left < dr.left - 1)).map(([e]) => e.textContent.slice(0, 40)) : [];
    return { label: ${JSON.stringify(label)}, viewport: innerWidth, page: document.documentElement.scrollWidth, body: document.body.scrollWidth,
      main: main.classList.contains('map') ? null : [main.scrollWidth, main.clientWidth], top: [top.scrollWidth, top.clientWidth], strip: [strip.scrollWidth, strip.clientWidth],
      drawer: open ? [drawer.scrollWidth, drawer.clientWidth] : null, outside,
      stuck: [...document.querySelectorAll('.act-group button')].filter(b => b.disabled || b.getAttribute('aria-busy')).map(b => b.textContent) };
  })()`);
  bounds.push(value);
  assert.ok(value.page <= value.viewport && value.body <= value.viewport, 'Sideways overflow of the page: ' + JSON.stringify(value));
  assert.ok(!value.main || value.main[0] <= value.main[1] + 1, 'Sideways overflow of the main area: ' + JSON.stringify(value));
  assert.ok(value.top[0] <= value.top[1] + 1 && value.strip[0] <= value.strip[1] + 1, 'Sideways overflow of the top bar or strip: ' + JSON.stringify(value));
  assert.ok(!value.drawer || value.drawer[0] <= value.drawer[1] + 1, 'Sideways overflow of the drawer: ' + JSON.stringify(value));
  assert.deepEqual(value.outside, [], 'Controls outside the drawer: ' + label);
  assert.deepEqual(value.stuck, [], 'A control left disabled: ' + label);
}
async function open(hash) {
  await send('Page.navigate', { url: origin + '/?theme=light#' + hash });
  await until(() => evaluate(`document.readyState === 'complete' && !!document.getElementById('needs-btn') && !document.getElementById('needs-btn').disabled`), 'the project read (' + hash + ')');
  await settled('opened ' + hash);
}
async function hash(value) { await evaluate(`location.hash = ${JSON.stringify('#' + value)}`); await settled('#' + value); }
async function mouse(x, y, click = false) {
  await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y });
  if (click) { await send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 }); await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 }); }
}
const byKey = key => `[data-key=${JSON.stringify(key)}]`;
async function centre(selector) {
  const box = await until(() => evaluate(`(() => { const e = [...document.querySelectorAll(${JSON.stringify(selector)})].find(e => e.offsetParent !== null); if (!e) return null; e.scrollIntoView({ block: 'nearest', inline: 'nearest' }); const r = e.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; })()`), 'shown: ' + selector, 100);
  return box;
}
async function press(selector) { const { x, y } = await centre(selector); await mouse(x, y, true); }
async function key(name, code = name, keyCode = 0) { await send('Input.dispatchKeyEvent', { type: 'keyDown', key: name, code, windowsVirtualKeyCode: keyCode }); await send('Input.dispatchKeyEvent', { type: 'keyUp', key: name, code, windowsVirtualKeyCode: keyCode }); }
async function type(selector, text) {
  await press(selector);
  await evaluate(`(() => { const e = document.activeElement; e.select && e.select(); })()`);
  await key('Delete', 'Delete', 46);
  await send('Input.insertText', { text });
}
/** Waits until nothing reads and no control waits for its answer. */
async function settled(label) {
  await until(() => evaluate(`(() => { const reading = e => [...e.querySelectorAll('.note')].some(n => n.textContent === 'Reading…'); return !reading(document.getElementById('main')) && !reading(document.getElementById('aside')) && !document.getElementById('main').hasAttribute('aria-busy') && !document.querySelector('.act-group [aria-busy]'); })()`), label);
  await pause(150);
}
/** Replaces the whole value of a field (a number field too): select all, delete, then the text. */
async function replace(selector, text) {
  await press(selector);
  await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'a', code: 'KeyA', windowsVirtualKeyCode: 65, modifiers: 2, commands: ['selectAll'] });
  await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'a', code: 'KeyA', windowsVirtualKeyCode: 65, modifiers: 2 });
  await key('Delete', 'Delete', 46);
  if (text) await send('Input.insertText', { text });
}
async function drawerText() { return evaluate(`document.getElementById('aside').innerText`); }
const drawerState = () => evaluate(`[...document.querySelectorAll('#aside header .state')].map(e => e.textContent.trim()).join(' ')`);

(async () => {
  // ---- The fixture: minimal + buildable + two stand-in recipes, in Git ----------------
  fs.cpSync(path.join(root, 'tests', 'fixtures', 'tuldok_project', 'minimal'), path.join(temporary, 'fixture'), { recursive: true });
  folder = path.join(temporary, 'fixture', 'project');
  const code = path.join(temporary, 'fixture', 'code');
  const buildable = path.join(root, 'tests', 'fixtures', 'tuldok_project', 'buildable');
  for (const kind of ['environments', 'datasets', 'recipes', 'benchmarks', 'charts']) for (const name of fs.readdirSync(path.join(buildable, 'project', kind))) fs.copyFileSync(path.join(buildable, 'project', kind, name), path.join(folder, kind, name));
  for (const name of fs.readdirSync(path.join(buildable, 'code'))) fs.cpSync(path.join(buildable, 'code', name), path.join(code, name), { recursive: true });
  const progress = `import json, os, sys, time
def line(completed, total, value):
    print(json.dumps({'format': 'tuldok_progress_v1', 'stage': 'fit', 'completed': completed, 'total': total, 'metrics': {'loss': value}}), flush=True)
`;
  // About four seconds: eight progress lines, half a second apart.
  fs.writeFileSync(path.join(code, 'slow.py'), progress + `out = sys.argv[sys.argv.index('--out') + 1]
for step in range(1, 9):
    line(step, 8, 1.0 / step)
    print('step', step, 'of 8', file=sys.stderr, flush=True)
    time.sleep(0.5)
with open(os.path.join(out, 'weights.json'), 'w') as handle:
    json.dump({'constant': 1.0}, handle)
`);
  // Until it is cancelled (at most two minutes): a progress line every half second.
  fs.writeFileSync(path.join(code, 'hold_run.py'), progress + `out = sys.argv[sys.argv.index('--out') + 1]
for step in range(1, 241):
    line(step, 240, 1.0 / step)
    time.sleep(0.5)
with open(os.path.join(out, 'weights.json'), 'w') as handle:
    json.dump({'constant': 2.0}, handle)
`);
  const recipe = (title, script, extra, settingsFile) => JSON.stringify({ format: 'tuldok_definition_v1', kind: 'recipe', title, ...extra,
    run: { command: ['python', script].concat(settingsFile ? ['--settings', '{settings}'] : [], ['--out', '{output}']), environment: 'environments/test-python', ...(settingsFile ? { settings_file: settingsFile } : {}),
      outputs: { weights: { path: 'weights.json', role: 'weights' } }, sources: [script] } }, null, 2) + '\n';
  // The slow recipe reads its settings from a file holding a JSON object, so a branch of it carries them inline (T22).
  fs.writeFileSync(path.join(code, 'slow-settings.json'), JSON.stringify({ steps: 8, rate: 0.001, label: 'slow', schedule: [1, 2] }) + '\n');
  fs.writeFileSync(path.join(folder, 'recipes', 'slow.json'), recipe('Slow fit, four seconds', 'slow.py', { labels: { short: 'SLOW' }, change: 'refinement', derived_from: 'recipes/fit-a' }, 'slow-settings.json'));
  fs.writeFileSync(path.join(folder, 'recipes', 'hold.json'), recipe('Held fit, runs until cancelled', 'hold_run.py', { labels: { short: 'HOLD' }, change: 'training-policy' }));
  const git = ['-c', 'user.name=Tuldok Test', '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false', '-c', 'init.defaultBranch=main', '-C', path.join(temporary, 'fixture')];
  execFileSync('git', [...git, 'init', '-q']); execFileSync('git', [...git, 'add', '-A']); execFileSync('git', [...git, 'commit', '-q', '-m', 'The fixture.']);

  const home = path.join(temporary, 'home'), catalog = path.join(temporary, 'catalog'); fs.mkdirSync(home);
  const env = { ...process.env, TULDOK_PROJECT_HOME: home, TULDOK_SETTINGS: path.join(temporary, 'settings.json') };
  owned = [folder, catalog]; dropOwned(folder, catalog);
  const cli = (...args) => execFileSync(python, ['-m', 'tuldok_project', ...args], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] }).toString();
  cli('connect', folder, 'test-python', python);
  cli('build', folder, 'datasets/numbers', '--yes');

  let output = '';
  server = launch(python, ['-u', 'app.py', '--port', '0', '--data', catalog, '--project-folder', folder], { cwd: root, env, stdio: ['ignore', 'pipe', 'pipe'] });
  server.stdout.on('data', chunk => { output += chunk; }); server.stderr.on('data', chunk => { serverErrors += chunk; });
  const port = await until(() => { if (server.exitCode !== null) throw Error('Tuldok exited: ' + serverErrors); return output.match(/127\.0\.0\.1:(\d+)/)?.[1]; }, 'Tuldok start-up', 1800);
  origin = 'http://127.0.0.1:' + port;
  auth = authenticatedFixture(); await auth.register(origin, catalog, root);
  // An agent that may ask for builds asks for two; an inspector that may only read.
  const agent = await credential('A browser check agent', ['inspect', 'execute']);
  const inspector = await credential('A browser check inspector', ['inspect']);
  const slowAsk = await api('request_build', { targets: ['recipes/slow'] }, agent);
  const fitAsk = await api('request_build', { targets: ['recipes/fit-b'] }, agent);
  assert.equal(slowAsk.state, 'awaiting-approval'); assert.equal(fitAsk.state, 'awaiting-approval');
  check('Tuldok serves the fixture copy in Git; an agent asked for builds of recipes/slow (' + slowAsk.id.slice(0, 8) + ') and recipes/fit-b (' + fitAsk.id.slice(0, 8) + '), both awaiting approval');

  const browser = launch(findBrowser(), ['--headless', '--no-sandbox', '--disable-gpu', '--no-first-run', '--hide-scrollbars', '--remote-debugging-port=0', `--window-size=${WIDTH},${HEIGHT}`, '--user-data-dir=' + path.join(temporary, 'browser'), 'about:blank'], { stdio: 'ignore', env: { ...process.env, XDG_CONFIG_HOME: temporary, XDG_CACHE_HOME: temporary } });
  const debugPort = await waitForDebugger(browser, path.join(temporary, 'browser', 'DevToolsActivePort'));
  const target = (await (await fetch('http://127.0.0.1:' + debugPort + '/json')).json()).find(item => item.type === 'page');
  socket = new WebSocket(target.webSocketDebuggerUrl); await once(socket, 'open');
  session = cdpSession(socket, { timeoutMs: 60000, onEvent: event => {
    if (event.method === 'Runtime.exceptionThrown') errors.push(event.params.exceptionDetails.exception?.description || event.params.exceptionDetails.text);
    if (event.method === 'Runtime.consoleAPICalled' && event.params.type === 'error') errors.push(event.params.args.map(a => a.value ?? a.description).join(' '));
    if (event.method === 'Log.entryAdded' && event.params.entry.level === 'error') {
      const status = Number((event.params.entry.text.match(/status of (\d{3})/) || [])[1]);
      if (status) failure(event.params.entry.url, status, event.params.entry.text); else errors.push(event.params.entry.text + ' ' + (event.params.entry.url || ''));
    }
    if (event.method === 'Network.loadingFailed' && !event.params.canceled) failures.push({ id: event.params.requestId, error: event.params.errorText });
    if (event.method === 'Network.responseReceived' && event.params.response.status >= 400) failure(event.params.response.url, event.params.response.status, 'response');
  } });
  send = session.send;
  evaluate = async expression => { const result = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }); if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails)); return result.result.value; };
  await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable'); await send('Log.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: WIDTH, height: HEIGHT, deviceScaleFactor: 1, mobile: false });
  await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: 'light' }, { name: 'prefers-reduced-motion', value: 'reduce' }] });
  await auth.browser(send, origin);

  // ---- Needs you, with its controls ------------------------------------------------
  await open('map/recipes%2Fslow');
  assert.equal(await drawerState(), 'not built');
  await press('#needs-btn');
  await until(() => evaluate(`!!document.querySelector('#needs-panel ${byKey('need:request:' + slowAsk.id + ':approve')}')`), 'Needs you with Approve');
  const needs = await evaluate(`[...document.querySelectorAll('#needs-panel .needs > li')].map(li => [li.querySelector('.need > span').textContent, [...li.querySelectorAll('button')].map(b => b.textContent)])`);
  assert.ok(needs.filter(([, b]) => b.includes('Approve') && b.includes('Decline') && b.includes('Open on Train')).length === 2, 'Each request awaiting approval has Approve, Decline and a link: ' + JSON.stringify(needs));
  await shots('needs-you');
  check('Needs you lists ' + needs.length + ' items with their controls: ' + needs.map(([t, b]) => t.slice(0, 50) + '… [' + b.join(', ') + ']').join(' | '));

  // ---- Approve from Needs you; the hairline partly filled; the model built on the Map, no reload ----
  await evaluate(`window.__noReload = 1`);
  await press(byKey('need:request:' + slowAsk.id + ':approve'));
  const widths = [];
  const partly = await until(async () => { const w = await evaluate(`(() => { const i = document.querySelector('#strip .hair i'); return i ? parseFloat(i.style.width) : null; })()`); if (w !== null && !widths.includes(w)) widths.push(w); return w > 0 && w < 100 ? w : null; }, 'the strip hairline partly filled', 300);
  const stripText = await evaluate(`document.getElementById('strip').innerText.replace(/\\n/g, ' ')`);
  await shot('light-strip-hairline');
  await until(async () => (await drawerState()) === 'built', 'the model built in its drawer on the Map', 400);
  assert.equal(await evaluate(`window.__noReload`), 1, 'The page was not reloaded');
  assert.equal(await evaluate(`location.hash`), '#map/recipes%2Fslow');
  const slowRuns = (await api('runs', { reference: 'recipes/slow' })).runs;
  assert.equal(slowRuns[0].state, 'succeeded'); assert.equal((await api('build_request', { request: slowAsk.id })).state, 'succeeded');
  await key('Escape', 'Escape', 27); await until(() => evaluate(`document.getElementById('needs-panel').hidden`), 'Needs you closed');
  await settled('slow built');
  assert.match(await evaluate(`document.getElementById('aside').innerText`), /trained \d/);
  check('Approved from Needs you: the strip hairline read ' + widths.join(', ') + ' % (partly filled at ' + partly + ' %: "' + stripText.slice(0, 120) + '"), then the run succeeded and the drawer on the Map shows recipes/slow built, without a reload');

  // ---- A request awaiting approval: its controls; decline with a reason ---------------
  await hash('train/request:' + fitAsk.id);
  const buttons = await evaluate(`[...document.querySelectorAll('#aside .act-group button')].map(b => b.textContent)`);
  assert.deepEqual(buttons, ['Approve', 'Decline', 'Cancel']);
  await shots('request-awaiting');
  await press(byKey('request:' + fitAsk.id + ':decline'));
  await until(() => evaluate(`document.activeElement && document.activeElement.dataset.key === ${JSON.stringify('request:' + fitAsk.id + ':field:reason')}`), 'the reason field focused');
  const reason = 'Not now: fit-b waits for the new numbers.';
  await send('Input.insertText', { text: reason });
  await shots('decline-reason');
  await press(byKey('request:' + fitAsk.id + ':decline:confirm'));
  await until(async () => (await drawerText()).includes('Declined: ' + reason), 'the reason on the request');
  await settled('declined');
  const declined = await api('build_request', { request: fitAsk.id });
  assert.equal(declined.state, 'declined'); assert.equal(declined.problem, reason);
  assert.deepEqual(await evaluate(`[...document.querySelectorAll('#aside .act-group button')].map(b => b.textContent)`), []);
  check('Declined ' + fitAsk.id.slice(0, 8) + ' with the reason "' + reason + '", shown on the request; it has no control left');

  // ---- Plan the hold recipe from Train, request it, read its run live ------------------
  await hash('train');
  await press(byKey('todo:recipes/hold:plan'));
  await until(() => evaluate(`location.hash === '#train/plan%3Arecipes%2Fhold' && !!document.querySelector('#aside .plan-view')`), 'the plan view of recipes/hold');
  await settled('plan');
  const plan = await evaluate(`({ lead: document.querySelector('#aside .plan-lead').textContent, steps: [...document.querySelectorAll('#aside .steps > li')].map(li => li.querySelector('.title').textContent), totals: [...document.querySelectorAll('#aside .plan-view h3 + p, #aside .plan-view h3 ~ p.small')].map(p => p.textContent), scratch: !!document.querySelector('#aside input[type="checkbox"]'), request: document.querySelector('#aside .act-group button').textContent })`);
  assert.ok(plan.steps.some(t => /Build · Held fit/.test(t)), JSON.stringify(plan)); assert.ok(plan.scratch); assert.equal(plan.request, 'Request build');
  await shots('plan-view');
  await press(byKey('request:plan:recipes/hold:request'));
  await until(() => evaluate(`location.hash.startsWith('#train/request%3A')`), 'the request opened');
  const holdId = decodeURIComponent(await evaluate(`location.hash`)).slice('#train/request:'.length);
  const holdRun = await until(async () => { const r = await api('build_request', { request: holdId }); return r.runs.find(x => x.state === 'running'); }, 'the hold run running', 300);
  await hash('train/run:' + holdRun.id);
  const firstLines = await until(() => evaluate(`(() => { const p = document.querySelector('#aside pre[data-log="stdout"]'); const i = document.querySelector('#aside .progress-line .hair i'); return p && i && !p.hidden && parseFloat(i.style.width) > 0 ? p.textContent.split('\\n').length : 0; })()`), 'the run drawer with its hairline and log', 200);
  const grown = await until(() => evaluate(`(() => { const n = document.querySelector('#aside pre[data-log="stdout"]').textContent.split('\\n').length; return n > ${firstLines} ? n : 0; })()`), 'the log read on', 100);
  const liveLine = await evaluate(`document.querySelector('#aside .progress-line').innerText`);
  assert.ok(await evaluate(`[...document.querySelectorAll('#aside .act-group button')].some(b => b.textContent === 'Cancel run')`));
  await shots('run-live');
  check('Planned recipes/hold from Train (' + plan.steps.length + ' steps: ' + plan.steps.join(' | ') + '; "' + plan.lead + '"), requested it (' + holdId.slice(0, 8) + '); its run drawer reads on live: "' + liveLine + '", the log grew from ' + firstLines + ' to ' + grown + ' lines');

  // ---- While it runs: plan a model from its drawer on the Map, request, cancel with two presses ----
  await hash('map/recipes/fit-a');
  await press(byKey('model:recipes/fit-a:plan'));
  await until(() => evaluate(`location.hash === '#map/plan%3Arecipes%2Ffit-a' && !!document.querySelector('#aside .plan-view')`), 'the plan view from the drawer');
  await settled('plan from drawer');
  await shot('light-plan-view-map');
  await press(byKey('request:plan:recipes/fit-a:request'));
  await until(() => evaluate(`location.hash.startsWith('#train/request%3A')`), 'the fit-a request opened'); await settled('fit-a request');
  const fitAId = decodeURIComponent(await evaluate(`location.hash`)).slice('#train/request:'.length);
  assert.equal((await api('build_request', { request: fitAId })).state, 'queued');
  await press(byKey('request:' + fitAId + ':cancel'));
  await until(() => evaluate(`!!document.querySelector('#aside ${byKey('request:' + fitAId + ':cancel:confirm')}')`), 'the two-press state');
  assert.equal(await evaluate(`document.activeElement.dataset.key`), 'request:' + fitAId + ':cancel:confirm');
  const words = await evaluate(`document.querySelector('#aside .confirm-words').textContent`);
  await shots('two-press');
  await key('Escape', 'Escape', 27);
  await until(() => evaluate(`!document.querySelector('#aside .confirm-words') && document.activeElement.dataset.key === ${JSON.stringify('request:' + fitAId + ':cancel')}`), 'Escape leaves the two-press state and the focus is back on Cancel');
  assert.ok(await evaluate(`document.getElementById('drawer').classList.contains('open')`), 'Escape left the two-press state, not the drawer');
  await press(byKey('request:' + fitAId + ':cancel'));
  await until(() => evaluate(`!!document.querySelector('#aside ${byKey('request:' + fitAId + ':cancel:confirm')}')`), 'the two-press state again');
  await pause(4500);   // two refreshes of the strip and the tab while the hold run runs
  assert.equal(await evaluate(`document.activeElement.dataset.key`), 'request:' + fitAId + ':cancel:confirm', 'The two-press state and its focus outlive the refresh');
  await press(byKey('request:' + fitAId + ':cancel:confirm'));
  await until(async () => (await drawerState()) === 'cancelled', 'the fit-a request cancelled'); await settled('cancelled');
  assert.equal((await api('build_request', { request: fitAId })).state, 'cancelled');
  check('Planned recipes/fit-a from its drawer on the Map, requested it (queued behind the hold run), pressed Cancel: "' + words + '"; Escape left that state, which outlived two refreshes; Confirm cancelled it');

  // ---- A refusal shown inline: a plan with blocked targets ---------------------------------
  await hash('train');
  await press(byKey('train:every:plan'));
  await until(() => evaluate(`location.hash === '#train/plan%3A*' && !!document.querySelector('#aside .plan-view')`), 'the plan of everything'); await settled('plan everything');
  const blocked = await evaluate(`document.querySelector('#aside .plan-view .failure').textContent`);
  const refused = allow(/\/api\/project\/request_build$/, 409);
  await press(byKey('request:plan:*:request'));
  const refusal = await until(() => evaluate(`(() => { const r = document.querySelector('#aside .refusal'); return r && r.innerText; })()`), 'the refusal inline');
  close(refused);
  assert.match(refusal, /cannot be built/);
  assert.equal(await evaluate(`document.activeElement.dataset.key`), 'request:plan:*:request', 'The focus stays on the refused control');
  await evaluate(`document.querySelector('#aside .refusal').scrollIntoView({ block: 'center' })`);
  await shots('refusal');
  check('Plan everything buildable says "' + blocked.slice(0, 90) + '…"; Request build was refused inline: "' + refusal.replace(/\n/g, ' ').slice(0, 160) + '"');

  // ---- Plan from a Train row, request, cancel ---------------------------------------------------
  await hash('train');
  await press(byKey('todo:recipes/fit-b:plan'));
  await until(() => evaluate(`!!document.querySelector('#aside .plan-view') && location.hash === '#train/plan%3Arecipes%2Ffit-b'`), 'the plan of fit-b'); await settled('plan fit-b');
  await press(byKey('request:plan:recipes/fit-b:request'));
  await until(() => evaluate(`location.hash.startsWith('#train/request%3A')`), 'the fit-b request opened'); await settled('fit-b request');
  const fitBId = decodeURIComponent(await evaluate(`location.hash`)).slice('#train/request:'.length);
  await press(byKey('request:' + fitBId + ':cancel')); await press(byKey('request:' + fitBId + ':cancel:confirm'));
  await until(async () => (await drawerState()) === 'cancelled', 'the fit-b request cancelled'); await settled('cancelled b');
  assert.equal((await api('build_request', { request: fitBId })).state, 'cancelled');
  await inspect('fit-b cancelled');
  check('Planned recipes/fit-b from its row on Train, requested and cancelled it with two presses');

  // ---- Cancel the running run ------------------------------------------------------------------
  await hash('train/run:' + holdRun.id);
  await press(byKey('run:' + holdRun.id + ':cancel'));
  const runWords = await evaluate(`document.querySelector('#aside .confirm-words').textContent`);
  await press(byKey('run:' + holdRun.id + ':cancel:confirm'));
  await until(async () => (await drawerState()) === 'cancelled', 'the hold run cancelled in its drawer', 300); await settled('run cancelled');
  assert.equal((await api('run', { run: holdRun.id })).state, 'cancelled');
  await until(async () => !['queued', 'running'].includes((await api('build_request', { request: holdId })).state), 'the hold request ended');
  await inspect('run cancelled');
  check('Cancelled the running run ' + holdRun.id.slice(0, 8) + ' ("' + runWords + '"); its drawer turned to cancelled on its own');

  // ---- Environments: connect one (a refusal first), check one again ---------------------------
  await hash('train/env:environments/lab-cpu');
  const field = byKey('envconnect:environments/lab-cpu:field:interpreter');
  await type(field, 'python');
  const invalid = allow(/\/api\/project\/connect_environment$/, 400);
  await press(byKey('envconnect:environments/lab-cpu:connect'));
  const notAbsolute = await until(() => evaluate(`(() => { const r = document.querySelector('#aside .refusal'); return r && r.innerText; })()`), 'the connect refusal');
  close(invalid);
  assert.equal(await evaluate(`document.querySelector(${JSON.stringify('#aside ' + field)}).value`), 'python', 'The typed path stays after the refusal');
  await type(field, python);
  await press(byKey('envconnect:environments/lab-cpu:connect'));
  await until(async () => (await drawerText()).includes(python) && !(await evaluate(`!!document.querySelector('#aside .refusal')`)), 'lab-cpu connected'); await settled('connected');
  const labCpu = await api('environment', { reference: 'environments/lab-cpu' });
  assert.equal(labCpu.interpreter, python); assert.ok(labCpu.checked_at);
  assert.ok(await evaluate(`[...document.querySelectorAll('#aside .act-group button')].map(b => b.textContent).join() === 'Check again,Connect,Disconnect'`), 'Check again, Connect and Disconnect on a connected environment');
  await inspect('env connected'); await shot('light-environment');
  const before = (await api('environment', { reference: 'environments/test-python' })).checked_at;
  await pause(1100);
  await hash('train/env:environments/test-python');
  await press(byKey('envcheck:environments/test-python:check'));
  await until(async () => (await api('environment', { reference: 'environments/test-python' })).checked_at !== before, 'test-python checked again'); await settled('checked');
  await inspect('env checked');
  await hash('train/env:environments/lab-cpu');
  await press(byKey('envdisconnect:environments/lab-cpu:disconnect'));
  const forget = await evaluate(`document.querySelector('#aside .confirm-words').textContent`);
  await press(byKey('envdisconnect:environments/lab-cpu:disconnect:confirm'));
  await until(async () => (await drawerText()).includes('none recorded on this machine'), 'lab-cpu disconnected'); await settled('disconnected');
  assert.equal((await api('environment', { reference: 'environments/lab-cpu' })).interpreter, null);
  await inspect('env disconnected');
  check('lab-cpu: "python" was refused inline ("' + notAbsolute.replace(/\n/g, ' ') + '"), then ' + python + ' connected (' + labCpu.state + ') and disconnected again ("' + forget + '"); test-python checked again (' + before + ' → newer)');

  // ---- Save from the strip ----------------------------------------------------------------------
  const fitBText = (await api('definition', { reference: 'recipes/fit-b' })).text;
  await api('set_definition', { reference: 'recipes/fit-b', text: fitBText.replace('"Fit b, with inline settings"', '"Fit b, saved from the strip"') });
  await evaluate(`window.dispatchEvent(new Event('focus'))`);
  await until(() => evaluate(`!!document.querySelector('#strip ${byKey('save:save')}')`), 'Save on the strip');
  const unsaved = await evaluate(`document.querySelector('#strip .unsaved .count').textContent`);
  await shot('light-strip-save');
  await press('#strip ' + byKey('save:save'));
  await until(() => evaluate(`!document.querySelector('#strip .unsaved')`), 'nothing unsaved'); await settled('saved');
  assert.match(fs.readFileSync(path.join(folder, 'recipes', 'fit-b.json'), 'utf8'), /Fit b, saved from the strip/);
  await inspect('saved');
  check('The strip said "' + unsaved + '"; Save wrote recipes/fit-b.json');

  // ---- A conflict, resolved both ways --------------------------------------------------------------
  const fitAFile = path.join(folder, 'recipes', 'fit-a.json'), fitAText = fs.readFileSync(fitAFile, 'utf8');
  await api('set_definition', { reference: 'recipes/fit-a', text: fitAText.replace('"Fit a, from a settings file"', '"Fit a, my edit"') });
  fs.writeFileSync(fitAFile, fitAText.replace('"Fit a, from a settings file"', '"Fit a, changed on disk"'));
  let conflicted = allow(/\/api\/project\//, 409);
  await evaluate(`window.dispatchEvent(new Event('focus'))`);
  const panel = await until(() => evaluate(`(() => { const c = document.querySelector('#main .conflict'); return c && c.innerText; })()`), 'the conflict panel');
  assert.match(panel, /recipes\/fit-a/);
  await shots('conflict');
  await press(byKey('conflict:keep'));
  await until(() => evaluate(`!document.querySelector('#main .conflict') && !!document.querySelector('#strip .unsaved')`), 'the project read with my edit kept'); close(conflicted); await settled('kept');
  let fitA = await api('definition', { reference: 'recipes/fit-a' });
  assert.equal(fitA.title, 'Fit a, my edit'); assert.equal(fitA.unsaved, true);
  fs.writeFileSync(fitAFile, fitAText.replace('"Fit a, from a settings file"', '"Fit a, changed on disk again"'));
  conflicted = allow(/\/api\/project\//, 409);
  await evaluate(`window.dispatchEvent(new Event('focus'))`);
  await until(() => evaluate(`!!document.querySelector('#main .conflict')`), 'the conflict panel again');
  await press(byKey('conflict:discard'));
  const takeWords = await evaluate(`document.querySelector('#main .confirm-words').textContent`);
  await press(byKey('conflict:discard:confirm'));
  await until(() => evaluate(`!document.querySelector('#main .conflict') && !document.querySelector('#strip .unsaved')`), 'the project read with the files taken'); close(conflicted); await settled('taken');
  fitA = await api('definition', { reference: 'recipes/fit-a' });
  assert.equal(fitA.title, 'Fit a, changed on disk again'); assert.equal(fitA.unsaved, false);
  await inspect('conflict resolved');
  check('A conflict on recipes/fit-a: the panel named it; Keep my edits kept "Fit a, my edit" unsaved; a second one, Take the files ("' + takeWords + '"), took "Fit a, changed on disk again"');

  // ==== Editing and branching (spec-w3 section 3.2, slice T22) ===========================================
  const projectId = JSON.parse(fs.readFileSync(path.join(folder, 'tuldok.json'), 'utf8')).id;
  const stored = () => evaluate(`JSON.parse(sessionStorage.getItem(${JSON.stringify('tuldok-drafts:' + projectId)}) || '{"drafts": []}').drafts`);
  const onDisk = name => fs.existsSync(path.join(folder, name)) ? fs.readFileSync(path.join(folder, name), 'utf8') : null;
  const stripUnsaved = () => evaluate(`(() => { const c = document.querySelector('#strip .unsaved .count'); return c ? c.textContent : ''; })()`);
  const mapNodes = () => evaluate(`[...document.querySelectorAll('.tree-map .node')].map(g => { const c = g.querySelector('circle'); return { id: g.dataset.id, x: +c.getAttribute('cx'), y: +c.getAttribute('cy'), cls: g.getAttribute('class'), dash: getComputedStyle(c).strokeDasharray, fill: getComputedStyle(c).fill, label: (g.querySelector('text') || {}).textContent || '' }; })`);
  const listRows = () => evaluate(`[...document.querySelectorAll('.tree-list .trow')].map(b => ({ id: b.dataset.id, chip: b.querySelector('.chip').textContent, mark: b.querySelector('.umark').textContent, cls: b.className }))`);
  const editorValue = name => evaluate(`(() => { const e = [...document.querySelectorAll('#aside [data-key]')].find(e => e.dataset.key === ${JSON.stringify(name)}); return e ? e.value : null; })()`);
  const refusalText = () => evaluate(`(() => { const r = document.querySelector('#aside .refusal'); return r && r.innerText; })()`);

  // ---- Branch a built model: the draft on the map, after its parent; it survives a reload -----------------
  await hash('map/recipes%2Fslow');
  assert.equal(await drawerState(), 'built');
  await press(byKey('modelact:recipes/slow:branch'));
  await until(() => evaluate(`location.hash === '#map/branch%3Arecipes%2Fslow' && !!document.querySelector('#aside .branch')`), 'the branch form');
  const branchKinds = await evaluate(`[...document.querySelectorAll('#aside .branch input[type="radio"]')].filter(r => r.checked).map(r => r.value)`);
  assert.deepEqual(branchKinds, ['refinement'], 'The kind of change is the parent\'s to begin with');
  // Create without a title is refused in place.
  await press(byKey('branch:recipes/slow:create'));
  assert.match(await until(refusalText, 'the title refusal'), /needs a title/);
  await type(byKey('branch:recipes/slow:field:title'), 'Slow fit, a faster rate');
  await type(byKey('branch:recipes/slow:field:description'), 'Doubles the rate of the slow fit.');
  await shots('branch-form');
  await press(byKey('branch:recipes/slow:create'));
  const draftRef = 'recipes/slow-fit-a-faster-rate';
  await until(() => evaluate(`location.hash === '#map/' + encodeURIComponent(${JSON.stringify(draftRef)}) && !!document.querySelector('#aside .editor')`), 'the draft selected, its drawer the editor'); await settled('draft');
  const placeDraft = async () => {
    const nodes = await mapNodes(), rows = await listRows(), slow = nodes.find(n => n.id === 'recipes/slow'), draft = nodes.find(n => n.id === draftRef);
    assert.ok(draft, 'The draft is on the map');
    assert.equal(rows.findIndex(r => r.id === draftRef), rows.findIndex(r => r.id === 'recipes/slow') + 1, 'The draft is listed right after its parent');
    assert.equal(Math.min(...nodes.filter(n => n.x > slow.x).map(n => n.x)), draft.x, 'The draft is drawn right after its parent');
    assert.notEqual(draft.y, slow.y, 'The draft is in the lane of its parent\'s branches');
    assert.ok(await evaluate(`!!document.querySelector('.tree-map .der[data-family="recipes/slow"]')`), 'Its line from the parent');
    assert.equal(new Set(nodes.map(n => n.x + ',' + n.y)).size, nodes.length, 'No node is drawn on another');
    assert.match(draft.cls, /\bplanned\b/); assert.match(draft.cls, /\bdraft\b/); assert.notEqual(draft.dash, 'none', 'dashed'); assert.equal(draft.label, 'new');
    assert.equal(rows.find(r => r.id === draftRef).chip, 'draft');
    return { draft, slow, rows: rows.length };
  };
  const placed = await placeDraft();
  const drawerForm = await evaluate(`({ view: [...document.querySelectorAll('#aside .seg button')].map(b => b.textContent + '=' + b.getAttribute('aria-pressed')), inlined: [...document.querySelectorAll('#aside p.note')].map(p => p.textContent).find(t => t.includes('copied from')) || '', steps: [...document.querySelectorAll('#aside .new-steps li')].map(li => li.dataset.step + ':' + li.className), buttons: [...document.querySelectorAll('#aside .act-group button')].map(b => b.textContent) })`);
  assert.deepEqual(drawerForm.view, ['Form=true', 'Text=false']); assert.match(drawerForm.inlined, /slow-settings\.json/);
  assert.deepEqual(drawerForm.steps, ['Kept:todo', 'Saved:todo', 'Build requested:todo', 'Running:todo', 'Built:todo']); assert.deepEqual(drawerForm.buttons, ['Keep', 'Discard']);
  assert.equal((await stored()).map(d => d.reference).join(), draftRef);
  await open('map/' + encodeURIComponent(draftRef));
  await until(() => evaluate(`!!document.querySelector('#aside .editor')`), 'the draft drawer after a reload'); await settled('reloaded');
  await placeDraft();
  check('Branched recipes/slow ("' + drawerForm.inlined + '"): the draft ' + draftRef + ' is drawn hollow and dashed, labelled new, right after its parent (x ' + placed.slow.x + ' → ' + placed.draft.x + ', lane below), listed after it with the chip "draft", its drawer the form with the steps ' + drawerForm.steps.join(', ') + '; still there after a reload');

  // ---- Change a setting (a number stays a number), keep, save ------------------------------------------------------
  assert.equal(await editorValue('editor:' + draftRef + ':setting-rate'), '0.001');
  await replace(byKey('editor:' + draftRef + ':setting-rate'), '0.002');
  await until(async () => /"rate": 0\.002\b/.test((await stored())[0].text), 'the setting in the draft text');
  const draftText = (await stored())[0].text;
  assert.equal(JSON.parse(draftText).run.settings.rate, 0.002); assert.equal(JSON.parse(draftText).run.settings.steps, 8);
  assert.match(draftText, /\n  "run": \{\n    "command"/, 'Written with the indentation the text had'); assert.ok(draftText.endsWith('}\n'));
  await evaluate(`document.querySelector('#aside .new-steps').scrollIntoView({ block: 'end' })`);
  await shots('draft-on-map');
  await press(byKey('draft:' + draftRef + ':keep'));
  await until(async () => (await stripUnsaved()) === '1 definition unsaved', 'the strip says 1 unsaved'); await settled('kept');
  const keptView = await evaluate(`({ steps: [...document.querySelectorAll('#aside .new-steps li')].map(li => li.dataset.step + ':' + li.className), next: [...document.querySelectorAll('#aside .new-steps .act-group button')].map(b => b.textContent), mark: document.querySelector('#aside header .umark').textContent, node: !!document.querySelector('.tree-map .node[data-id="${draftRef}"] .unsaved-dot'), row: [...document.querySelectorAll('.tree-list .trow')].find(b => b.dataset.id === '${draftRef}').querySelector('.umark').textContent })`);
  assert.deepEqual(keptView.steps.slice(0, 2), ['Kept:done', 'Saved:todo']); assert.deepEqual(keptView.next, ['Save', 'Discard']);
  assert.equal(keptView.mark, 'unsaved'); assert.ok(keptView.node, 'The unsaved mark on the map node'); assert.equal(keptView.row, 'unsaved');
  assert.deepEqual(await stored(), [], 'A kept draft is no longer a draft');
  await press(byKey('model:' + draftRef + ':save'));
  await until(async () => (await stripUnsaved()) === '', 'nothing unsaved after Save'); await settled('saved branch');
  const savedBranch = JSON.parse(onDisk('recipes/slow-fit-a-faster-rate.json'));
  assert.equal(savedBranch.derived_from, 'recipes/slow'); assert.equal(savedBranch.run.settings.rate, 0.002); assert.equal(savedBranch.title, 'Slow fit, a faster rate');
  assert.equal(savedBranch.labels, undefined); assert.equal(savedBranch.card, undefined); assert.equal(savedBranch.run.settings_file, undefined);
  check('Changed the rate in the form (0.001 → 0.002, a number; steps stays 8), kept it (the strip said 1 unsaved; the drawer, list row and node marked unsaved; next step ' + keptView.next[0] + '), saved: ' + draftRef + '.json has derived_from, the setting and the title, and no labels or card');

  // ---- Plan build, request it: the model drawn built with its line, without a reload -------------------------------
  await evaluate(`window.__noReload = 2`);
  await press(byKey('model:' + draftRef + ':plan'));
  await until(() => evaluate(`location.hash === '#map/' + encodeURIComponent('plan:${draftRef}') && !!document.querySelector('#aside .plan-view')`), 'the plan view of the branch'); await settled('plan branch');
  await press(byKey('request:plan:' + draftRef + ':request'));
  await until(() => evaluate(`location.hash.startsWith('#train/request%3A')`), 'the branch request opened');
  const branchRequest = decodeURIComponent(await evaluate(`location.hash`)).slice('#train/request:'.length);
  await hash('map/' + encodeURIComponent(draftRef));
  await until(async () => { const n = (await mapNodes()).find(x => x.id === draftRef); return n && !/\bplanned\b/.test(n.cls) && n.dash === 'none'; }, 'the branch drawn built', 400);
  await until(() => evaluate(`!!document.querySelector('#aside .new-steps li[data-step="Built"].done')`), 'its steps say Built', 200); await settled('branch built');
  assert.equal(await evaluate(`window.__noReload`), 2, 'The page was not reloaded');
  assert.equal((await api('build_request', { request: branchRequest })).state, 'succeeded');
  assert.ok(await evaluate(`!!document.querySelector('.tree-map .der[data-family="recipes/slow"]')`), 'Its line from the parent');
  const builtSteps = await evaluate(`[...document.querySelectorAll('#aside .new-steps li')].map(li => li.dataset.step + ':' + li.className).join(', ')`);
  await shots('branch-built');
  check('Planned and requested the branch (' + branchRequest.slice(0, 8) + '); without a reload it is drawn built (solid) with its line from recipes/slow, and its steps read ' + builtSteps);

  // ---- A draft discarded is gone from the map, the list and sessionStorage ----------------------------------------------
  await hash('map/branch:recipes%2Fslow');
  await type(byKey('branch:recipes/slow:field:title'), 'A branch to throw away');
  await press(byKey('branch:recipes/slow:create'));
  const throwaway = 'recipes/a-branch-to-throw-away';
  await until(() => evaluate(`location.hash === '#map/' + encodeURIComponent('${throwaway}')`), 'the second draft'); await settled('second draft');
  assert.ok((await mapNodes()).some(n => n.id === throwaway));
  await press(byKey('draft:' + throwaway + ':discard'));
  const dropWords = await evaluate(`document.querySelector('#aside .confirm-words').textContent`);
  await press(byKey('draft:' + throwaway + ':discard:confirm'));
  await until(async () => !(await mapNodes()).some(n => n.id === throwaway), 'the draft gone from the map'); await settled('discarded');
  assert.ok(!(await listRows()).some(r => r.id === throwaway)); assert.deepEqual(await stored(), []);
  check('A second draft, discarded with two presses ("' + dropWords + '"), is gone from the map, the list and sessionStorage');

  // ---- A branch whose draft has errors: the problems, and Keep refused with them ------------------------------------------
  await hash('map/branch:recipes%2Fearly-fit');
  await type(byKey('branch:recipes/early-fit:field:title'), 'Early fit, run again');
  await press(byKey('branch:recipes/early-fit:create'));
  const broken = 'recipes/early-fit-run-again';
  await until(() => evaluate(`location.hash === '#map/' + encodeURIComponent('${broken}') && !!document.querySelector('#aside .editor')`), 'the earlier-work draft'); await settled('broken draft');
  const problems = await evaluate(`document.querySelector('#aside .problems').innerText`);
  assert.match(problems, /run/);
  const keepRefused = allow(/\/api\/project\/set_definition$/, 400);
  await press(byKey('draft:' + broken + ':keep'));
  const keepRefusal = await until(refusalText, 'Keep refused'); close(keepRefused);
  assert.ok(!(await api('definitions', { kind: 'recipe' })).definitions.some(d => d.reference === broken), 'Nothing stored');
  check('A branch of earlier work without run opens with its problems ("' + problems.replace(/\n/g, ' ').slice(0, 120) + '…"); Keep was refused with them ("' + keepRefusal.replace(/\n/g, ' ').slice(0, 120) + '…") and nothing was stored');

  // ---- Edit an existing recipe in the form; leave and come back; keep; discard the edit ---------------------------------
  const k1File = onDisk('recipes/stepper-k1.json');
  await hash('map/recipes%2Fstepper-k1');
  await press(byKey('modelact:recipes/stepper-k1:edit'));
  await until(() => evaluate(`location.hash === '#map/edit%3Arecipes%2Fstepper-k1' && !!document.querySelector('#aside .editor-form')`), 'the editor of stepper-k1'); await settled('editor k1');
  await type(byKey('editor:recipes/stepper-k1:description'), 'Trained again with a recorded command.');
  await until(() => evaluate(`document.querySelector('#aside header .umark').textContent === 'not kept yet'`), 'not kept yet in the header');
  await shots('editor-form');
  await hash('train'); await hash('map/edit%3Arecipes%2Fstepper-k1');
  const back = await evaluate(`({ value: document.querySelector('#aside [data-key="editor:recipes/stepper-k1:description"]').value, header: document.querySelector('#aside header .umark').textContent, row: [...document.querySelectorAll('.tree-list .trow')].find(b => b.dataset.id === 'recipes/stepper-k1').querySelector('.umark').textContent })`);
  assert.deepEqual(back, { value: 'Trained again with a recorded command.', header: 'not kept yet', row: 'not kept yet' });
  await press(byKey('edit:recipes/stepper-k1:keep'));
  await until(async () => (await api('definition', { reference: 'recipes/stepper-k1' })).unsaved, 'stepper-k1 kept'); await settled('k1 kept');
  assert.equal((await api('definition', { reference: 'recipes/stepper-k1' })).document.description, 'Trained again with a recorded command.');
  assert.equal(await evaluate(`document.querySelector('#aside header .umark').textContent`), 'unsaved');
  await press(byKey('edit:recipes/stepper-k1:discard'));
  const revertWords = await evaluate(`document.querySelector('#aside .confirm-words').textContent`);
  await press(byKey('edit:recipes/stepper-k1:discard:confirm'));
  await until(async () => !(await api('definition', { reference: 'recipes/stepper-k1' })).unsaved, 'stepper-k1 reverted'); await settled('k1 reverted');
  assert.equal((await api('definition', { reference: 'recipes/stepper-k1' })).text, k1File, 'The definition is the file again');
  check('Edited stepper-k1\'s description in the form; after Train and back the typing was there, marked "not kept yet" in the drawer and its row; kept (unsaved), then Discard edit with two presses ("' + revertWords + '") put the file back');

  // ---- Change a kind of change, keep, save --------------------------------------------------------------------------------
  await hash('map/edit%3Arecipes%2Fstepper-k2');
  await press(byKey('editor:recipes/stepper-k2:change-architecture'));
  await press(byKey('edit:recipes/stepper-k2:keep'));
  await until(async () => (await api('definition', { reference: 'recipes/stepper-k2' })).document.change === 'architecture', 'k2 kept'); await settled('k2 kept');
  await press(byKey('edit:recipes/stepper-k2:save'));
  await until(async () => (await stripUnsaved()) === '', 'k2 saved'); await settled('k2 saved');
  const k2 = JSON.parse(onDisk('recipes/stepper-k2.json'));
  assert.equal(k2.change, 'architecture'); assert.equal(k2.labels.short, 'K2'); assert.equal(k2.run.settings.learning_rate, 0.0005);
  const k2Node = (await mapNodes()).find(n => n.id === 'recipes/stepper-k2');
  assert.match(k2Node.cls, /\barchitecture\b/); assert.doesNotMatch(k2Node.cls, /\brefinement\b/);
  check('Changed stepper-k2\'s kind of change to Architecture, kept and saved: the file says "change": "architecture" (its other fields as they were) and its node is ' + k2Node.cls);

  // ---- The text view: invalid JSON refused with the problem, nothing kept; then a valid change kept --------------------------
  const fitBDef = await api('definition', { reference: 'recipes/fit-b' });
  await hash('map/edit%3Arecipes%2Ffit-b');
  await press(byKey('editor:recipes/fit-b:view-text'));
  await until(() => evaluate(`!!document.querySelector('#aside textarea.code')`), 'the text view');
  await replace(byKey('editor:recipes/fit-b:text'), fitBDef.text.replace('"title": "Fit b, saved from the strip",', '"title": "Fit b, broken",,'));
  const invalidRefused = allow(/\/api\/project\/set_definition$/, 400);
  await press(byKey('edit:recipes/fit-b:keep'));
  const invalidRefusal = await until(refusalText, 'the invalid JSON refused'); close(invalidRefused);
  assert.match(invalidRefusal, /not valid|JSON/i);
  assert.equal((await api('definition', { reference: 'recipes/fit-b' })).text, fitBDef.text, 'Nothing was kept');
  await evaluate(`document.querySelector('#aside .refusal').scrollIntoView({ block: 'center' })`);
  await shots('text-problem');
  await replace(byKey('editor:recipes/fit-b:text'), fitBDef.text.replace('"Fit b, saved from the strip"', '"Fit b, from the text view"'));
  await press(byKey('edit:recipes/fit-b:keep'));
  await until(async () => (await api('definition', { reference: 'recipes/fit-b' })).title === 'Fit b, from the text view', 'the text kept'); await settled('text kept');
  check('In the text view, invalid JSON was refused with the problem shown ("' + invalidRefusal.replace(/\n/g, ' ').slice(0, 120) + '") and nothing kept; then a valid change was kept');

  // ---- Pick on the map: Escape leaves the state; a pick sets the parent; its line is drawn -------------------------------------
  await hash('map/edit%3Arecipes%2Fhold');
  await press(byKey('editor:recipes/hold:pick'));
  await until(() => evaluate(`!!document.querySelector('#aside .picking')`), 'the picking state');
  const pickWords = await evaluate(`document.querySelector('#aside .picking p').textContent`);
  await shots('picking');
  await key('Escape', 'Escape', 27);
  await until(() => evaluate(`!document.querySelector('#aside .picking') && document.getElementById('drawer').classList.contains('open')`), 'Escape left the picking state, not the drawer');
  await press(byKey('editor:recipes/hold:pick'));
  await until(() => evaluate(`!!document.querySelector('#aside .picking')`), 'the picking state again');
  await press('.tree-map .node[data-id="recipes/hold"]');
  assert.match(await until(() => evaluate(`(() => { const p = document.querySelector('#aside .picking .warnline'); return p && p.textContent; })()`), 'itself refused'), /not derived from itself/);
  await press('.tree-map .node[data-id="recipes/fit-b"]');
  await until(() => evaluate(`!document.querySelector('#aside .picking') && document.querySelector('#aside .derived-name').textContent.includes('Fit b')`), 'fit-b as the parent'); await settled('picked');
  assert.equal(await evaluate(`location.hash`), '#map/edit%3Arecipes%2Fhold');
  await press(byKey('edit:recipes/hold:keep'));
  await until(async () => (await api('definition', { reference: 'recipes/hold' })).document.derived_from === 'recipes/fit-b', 'hold kept with its parent'); await settled('hold kept');
  await until(() => evaluate(`!!document.querySelector('.tree-map .der[data-family="recipes/fit-b"]')`), 'the derivation line from fit-b');
  await press('#strip ' + byKey('save:save')); await until(async () => (await stripUnsaved()) === '', 'saved'); await settled('saved hold');
  check('Pick on the map ("' + pickWords + '"): Escape left it; pressing hold itself was refused in place; pressing fit-b made it the parent, kept, with its line drawn');

  // ---- Remove: one nothing uses, and one in use (the refusal names its users) ------------------------------------------------
  await hash('overview');
  await until(() => evaluate(`!!document.querySelector('#main .ov-defs .row.def')`), 'the list of every definition');
  const listed = await evaluate(`[...document.querySelectorAll('#main .ov-defs h3')].map(e => e.textContent)`);
  await evaluate(`document.querySelector('#main .ov-defs').scrollIntoView({ block: 'start' })`);
  await shots('overview-list');
  await press(byKey('open-edit:charts/rollout-ranking'));
  await until(() => evaluate(`location.hash === '#overview/edit%3Acharts%2Frollout-ranking' && !!document.querySelector('#aside textarea.code')`), 'the chart in the text view'); await settled('chart editor');
  const chartText = (await api('definition', { reference: 'charts/rollout-ranking' })).text;
  await replace(byKey('editor:charts/rollout-ranking:text'), chartText.replace('"Rollout error by subject"', '"Rollout error, each subject"'));
  await press(byKey('edit:charts/rollout-ranking:keep'));
  await until(async () => (await api('definition', { reference: 'charts/rollout-ranking' })).title === 'Rollout error, each subject', 'the chart kept'); await settled('chart kept');
  await press(byKey('edit:charts/rollout-ranking:remove'));
  const removeWords = await evaluate(`document.querySelector('#aside .confirm-words').textContent`);
  await press(byKey('edit:charts/rollout-ranking:remove:confirm'));
  await until(async () => (await api('definition', { reference: 'charts/rollout-ranking' })).removed, 'the chart marked removed'); await settled('removed');
  assert.equal(await evaluate(`[...document.querySelectorAll('#main .ov-defs .row.def')].find(r => r.dataset.ref === 'charts/rollout-ranking').querySelector('.umark').textContent`), 'removed');
  await press(byKey('open-edit:datasets/waves'));
  await until(() => evaluate(`location.hash === '#overview/edit%3Adatasets%2Fwaves' && !!document.querySelector('#aside textarea.code')`), 'the waves dataset'); await settled('waves');
  const inUse = allow(/\/api\/project\/remove_definition$/, 409);
  await press(byKey('edit:datasets/waves:remove')); await press(byKey('edit:datasets/waves:remove:confirm'));
  const usedBy = await until(refusalText, 'the in-use refusal'); close(inUse);
  assert.match(usedBy, /recipes\/stepper-k1/);
  assert.equal((await api('definition', { reference: 'datasets/waves' })).removed, false);
  await hash('overview/edit%3Acharts%2Frollout-ranking');
  await press(byKey('edit:charts/rollout-ranking:discard')); await press(byKey('edit:charts/rollout-ranking:discard:confirm'));
  await until(async () => { const d = await api('definition', { reference: 'charts/rollout-ranking' }); return !d.removed && !d.unsaved; }, 'the chart back'); await settled('chart back');
  check('Overview lists every definition by kind (' + listed.join(', ') + '); a chart edited in the text view and kept, then removed with two presses ("' + removeWords + '") and put back; removing datasets/waves was refused naming its users ("' + usedBy.replace(/\n/g, ' ').slice(0, 140) + '")');

  // ---- Edit a dataset from the Data tab, in the text view --------------------------------------------------------------------
  await hash('data/datasets%2Fnumbers');
  await press(byKey('dataedit:datasets/numbers:edit'));
  await until(() => evaluate(`location.hash === '#data/edit%3Adatasets%2Fnumbers' && !!document.querySelector('#aside textarea.code')`), 'the dataset in the text view'); await settled('dataset editor');
  const numbersText = (await api('definition', { reference: 'datasets/numbers' })).text;
  await replace(byKey('editor:datasets/numbers:text'), numbersText.replace('"A few numbers"', '"A few numbers, renamed"'));
  await press(byKey('edit:datasets/numbers:keep'));
  await until(async () => (await api('definition', { reference: 'datasets/numbers' })).title === 'A few numbers, renamed', 'the dataset kept'); await settled('dataset kept');
  await press(byKey('edit:datasets/numbers:discard')); await press(byKey('edit:datasets/numbers:discard:confirm'));
  await until(async () => (await api('definition', { reference: 'datasets/numbers' })).text === numbersText, 'the dataset back'); await settled('dataset back');
  await inspect('dataset back');
  check('Edited datasets/numbers from the Data tab in the text view, kept it, and discarded the edit');

  // ---- Typed text and focus outlive the refresh while a build runs, and the end of that build -----------------------------------
  const holdAgain = await api('request_build', { targets: ['recipes/hold'] });
  await until(async () => (await api('build_request', { request: holdAgain.id })).state === 'running', 'hold running again', 300);
  await hash('map/edit%3Arecipes%2Ffit-a');
  await press(byKey('editor:recipes/fit-a:description'));
  await send('Input.insertText', { text: 'Typed while a build runs' });
  await pause(4500);
  const kept1 = await evaluate(`({ key: document.activeElement.dataset.key, value: document.activeElement.value, caret: document.activeElement.selectionStart })`);
  assert.deepEqual(kept1, { key: 'editor:recipes/fit-a:description', value: 'Typed while a build runs', caret: 24 }, 'Typing and focus outlive the two-second refresh');
  await api('cancel_build', { request: holdAgain.id });
  await until(async () => !['queued', 'running'].includes((await api('build_request', { request: holdAgain.id })).state), 'hold cancelled');
  await pause(3000);
  await send('Input.insertText', { text: '.' });
  const kept2 = await evaluate(`({ key: document.activeElement.dataset.key, value: document.activeElement.value })`);
  assert.deepEqual(kept2, { key: 'editor:recipes/fit-a:description', value: 'Typed while a build runs.' }, 'Typing and focus outlive the end of the build');
  await press(byKey('edit:recipes/fit-a:discard')); await press(byKey('edit:recipes/fit-a:discard:confirm'));
  await until(() => evaluate(`document.querySelector('#aside [data-key="editor:recipes/fit-a:description"]').value === '' && document.querySelector('#aside header .umark').textContent === ''`), 'the typing discarded'); await settled('typing discarded');
  check('Typed into fit-a\'s description while a build ran: the text, focus and caret outlived two refreshes and the end of the build; Discard edit dropped the typing');

  // ---- Train: Planned first ---------------------------------------------------------------------------------------------------
  await hash('train');
  const planned = await evaluate(`[...document.querySelectorAll('#main .rows.planned > li')].map(li => li.innerText.replace(/\\n/g, ' '))`);
  assert.ok(planned.some(t => t.includes('Early fit, run again') && t.includes('draft')), 'The draft is planned: ' + JSON.stringify(planned));
  const toBuild = await evaluate(`[...document.querySelectorAll('#main .sect h2')].map(e => e.textContent)`);
  assert.equal(toBuild[0], 'Planned'); assert.equal(toBuild[1], 'To build');
  const twice = await evaluate(`(() => { const keys = [...document.querySelectorAll('#main .row.todo')].map(b => b.dataset.key); return keys.filter((k, i) => keys.indexOf(k) !== i); })()`);
  assert.deepEqual(twice, [], 'No model listed twice');
  await shots('train-planned');
  check('Train lists Planned first: ' + planned.map(t => t.slice(0, 50)).join(' | '));

  // ---- A session that may only inspect: no control is drawn ---------------------------------------------
  await send('Page.navigate', { url: 'about:blank' });
  await send('Network.clearBrowserCookies');
  const result = await send('Network.setCookie', { name: 'tuldok_session', value: inspector, url: origin + '/', httpOnly: true, sameSite: 'Strict', path: '/' });
  assert.notEqual(result.success, false);
  const cookies = (await send('Network.getCookies', { urls: [origin + '/'] })).cookies.filter(c => c.name === 'tuldok_session');
  assert.deepEqual(cookies.map(c => c.value === inspector), [true], 'The browser holds the inspector\'s credential alone');
  const seen = [];
  for (const place of ['map/recipes%2Ffit-b', 'map/edit:recipes%2Ffit-b', 'map/branch:recipes%2Fslow', 'map/' + encodeURIComponent(broken), 'data/edit:datasets%2Fnumbers', 'overview/edit:charts%2Frollout-ranking', 'train', 'train/request:' + fitAsk.id, 'train/request:' + holdId, 'train/run:' + holdRun.id, 'train/env:environments%2Flab-cpu', 'train/plan:recipes%2Ffit-b', 'overview']) {
    await open(place);
    assert.equal(await evaluate(`document.getElementById('session-identity').textContent`), 'A browser check inspector · agent');
    if (place === 'train') { await press('#needs-btn'); await until(() => evaluate(`!document.getElementById('needs-panel').hidden`), 'Needs you'); }
    const drawn = await evaluate(`[...document.querySelectorAll('button.act, #aside input[type="checkbox"], .act-field')].filter(e => e.offsetParent !== null || e.closest('#needs-panel')).map(b => b.textContent || b.type)`);
    assert.deepEqual(drawn, [], 'No control for an inspector on ' + place);
    // T22: no editor, no branch form, no draft, no Edit, Branch from here, Keep, Save or Remove, and a list that opens nothing.
    const editing = await evaluate(`({ editor: !!document.querySelector('#aside .editor, #aside .branch'), labels: [...document.querySelectorAll('button')].filter(b => b.offsetParent !== null).map(b => b.textContent).filter(t => ['Edit', 'Branch from here', 'Keep', 'Save', 'Remove', 'Discard edit', 'Discard', 'Create', 'Pick on the map'].includes(t)), drafts: document.querySelectorAll('.tree-map .node.draft').length, rows: document.querySelectorAll('#main .ov-defs button.row').length })`);
    assert.deepEqual(editing, { editor: false, labels: [], drafts: 0, rows: 0 }, 'No editing for an inspector on ' + place);
    seen.push(place);
  }
  await shot('light-inspector-overview');
  check('Signed in with a credential that may only inspect: no control on ' + seen.join(', '));

  // ---- Nothing failed but what was provoked ---------------------------------------------------------------
  assert.deepEqual(errors, [], 'Script errors');
  assert.deepEqual(failures, [], 'Failed requests');
  for (const a of allowed) assert.ok(a.seen > 0, 'A provoked refusal was seen: ' + a.re);
  check('No script error, no failed request but the ' + allowed.reduce((n, a) => n + a.seen, 0) + ' provoked refusals, no overflow, no control left disabled');
  fs.writeFileSync(path.join(report, 'receipt.json'), JSON.stringify({ status: 'pass', folder, checks, bounds }, null, 2) + '\n');
  console.log('Screenshots and receipt in ' + report);
})().catch(async error => {
  process.exitCode = 1;
  console.error(error); if (serverErrors) console.error('Server:', serverErrors.slice(-4000));
  console.error('Script errors:', JSON.stringify(errors)); console.error('Failed requests:', JSON.stringify(failures));
  try { if (evaluate) { await shot('failure'); console.error('Page:', (await evaluate('document.body.innerText')).slice(0, 3000)); } } catch (_) { /* the page is gone */ }
  fs.writeFileSync(path.join(report, 'failure.json'), JSON.stringify({ status: 'failed', error: String(error && error.stack || error), checks, bounds, errors, failures }, null, 2) + '\n');
  console.error('Screenshots in ' + report);
}).finally(async () => {
  try { session?.close(); } catch (_) { /* closed */ }
  for (const child of children.reverse()) await stop(child);
  if (owned) try { dropOwned(...owned); } catch (error) { console.error('Dropping the disposable schemas failed:', error.message); process.exitCode = 1; }
  try { execFileSync('chmod', ['-R', 'u+w', temporary]); } catch (_) { /* nothing was made read-only */ }   // finished runs leave their directories read-only
  fs.rmSync(temporary, { recursive: true, force: true });
});
