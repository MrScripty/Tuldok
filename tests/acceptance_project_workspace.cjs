'use strict';
// The acceptance run of docs/plans/definition-first-projects/spec-w3.md ("Done when"): the project workspace on a
// copy of examples/tiny-project with real interpreters and a GPU, driven in a headless browser. After Tuldok
// starts, everything is done on the page: the owner connects the two interpreters, plans and requests a build of
// everything and watches the training's progress, branches the trained model, changes a setting in the form,
// keeps, saves, plans and requests the branch and sees it built on the map without a reload, adds it to the
// benchmark in the text view, and approves from Needs you a build an agent asked for (noticed by the idle page).
// Only the agent's request and the read-backs that check each step are made beside the page.
// It trains two small networks (seconds each on a GPU) and WRITES INTO THE PROJECT FOLDER it is given: give it a
// copy of examples/tiny-project committed to a Git repository of its own, with its own id in tuldok.json, and
// set TULDOK_DATABASE_URL (a disposable cluster), TULDOK_PROJECT_HOME and TULDOK_SETTINGS (scratch places).
//   node tests/acceptance_project_workspace.cjs <project folder> <python 3.12 with numpy> <python 3.14 with torch and CUDA> [output directory]
const assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const { spawn } = require('node:child_process'), { once } = require('node:events');
const root = path.resolve(__dirname, '..'), tests = __dirname;
const { authenticatedFixture } = require('./auth_helpers.cjs'), { waitForDebugger } = require('./browser_startup.cjs'), { cdpSession } = require('./browser_cdp_session.cjs'), { qaDirectory } = require('./qa_artifacts.cjs');
assert.ok(process.argv.length >= 5, 'usage: node tests/acceptance_project_workspace.cjs <project folder> <cpu interpreter> <gpu interpreter> [output directory]');
const [folder, CPU, GPU] = process.argv.slice(2, 5).map(p => path.resolve(p));
const out = process.argv[5] ? path.resolve(process.argv[5]) : qaDirectory(root, 'project-workspace-acceptance');
assert.ok(process.env.TULDOK_DATABASE_URL && process.env.TULDOK_PROJECT_HOME && process.env.TULDOK_SETTINGS, 'Set TULDOK_DATABASE_URL to a disposable cluster and TULDOK_PROJECT_HOME and TULDOK_SETTINGS to scratch places.');
assert.ok(fs.existsSync(path.join(folder, 'tuldok.json')), 'The first argument is a project folder (it holds tuldok.json).');
const venv = path.join(root, '.venv', 'bin');
if (fs.existsSync(path.join(venv, 'python'))) process.env.PATH = venv + path.delimiter + process.env.PATH;   // auth_helpers runs python3
const python = fs.existsSync(path.join(venv, 'python')) ? path.join(venv, 'python') : 'python3';
const WIDTH = 1440, HEIGHT = 900;
const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'tuldok-accept-'));
fs.mkdirSync(out, { recursive: true });
const children = [], errors = [], failures = [], log = [];
let server, serverErrors = '', origin, auth, socket, send, evaluate;
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(fn, label, tries = 300, every = 100) { for (let i = 0; i < tries; i++) { const value = await fn(); if (value) return value; await pause(every); } throw Error('Timed out: ' + label); }
function done(text) { log.push(text); console.log('DONE ' + text); }
function launch(command, args, options) { const child = spawn(command, args, options); children.push(child); return child; }
async function stop(child) { if (!child || child.exitCode !== null || child.signalCode !== null) return; const exited = once(child, 'exit'); child.kill('SIGTERM'); await Promise.race([exited, pause(40000)]); if (child.exitCode === null && child.signalCode === null) child.kill('SIGKILL'); }
function findBrowser() {
  const candidates = [process.env.BROWSER, '/usr/bin/chromium', '/usr/bin/chromium-browser', '/usr/bin/google-chrome'];
  const cache = path.join(os.homedir(), '.cache', 'ms-playwright');
  if (fs.existsSync(cache)) for (const name of fs.readdirSync(cache).filter(n => n.startsWith('chromium_headless_shell-')).sort().reverse()) candidates.push(path.join(cache, name, 'chrome-headless-shell-linux64', 'chrome-headless-shell'));
  const found = candidates.find(candidate => candidate && fs.existsSync(candidate)); assert.ok(found, 'No headless browser'); return found;
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
let shotNumber = 0;
async function shot(name) {
  await evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))');
  const file = path.join(out, String(++shotNumber).padStart(2, '0') + '-' + name + '.jpg');
  fs.writeFileSync(file, Buffer.from((await send('Page.captureScreenshot', { format: 'jpeg', quality: 88, captureBeyondViewport: false })).data, 'base64'));
  return file;
}
async function theme(name) { await evaluate(`(() => { document.documentElement.setAttribute('data-theme', '${name}'); document.getElementById('theme').lastChild.textContent = ' ${name === 'dark' ? 'Dark' : 'Light'}'; })()`); }
async function settled(label) {
  await until(() => evaluate(`(() => { const reading = e => [...e.querySelectorAll('.note')].some(n => n.textContent === 'Reading…'); return !reading(document.getElementById('main')) && !reading(document.getElementById('aside')) && !document.getElementById('main').hasAttribute('aria-busy') && !document.querySelector('.act-group [aria-busy]'); })()`), label, 1200);
  await pause(200);
}
async function open(hash) {
  await send('Page.navigate', { url: origin + '/?theme=light#' + hash });
  await until(() => evaluate(`document.readyState === 'complete' && !!document.getElementById('needs-btn') && !document.getElementById('needs-btn').disabled`), 'the project read (' + hash + ')', 600);
  await settled('opened ' + hash);
}
async function hash(value) { await evaluate(`location.hash = ${JSON.stringify('#' + value)}`); await settled('#' + value); }
async function mouse(x, y, click = false) {
  await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y });
  if (click) { await send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 }); await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 }); }
}
const byKey = key => `[data-key=${JSON.stringify(key)}]`;
const enc = encodeURIComponent;
async function centre(selector) {
  return until(() => evaluate(`(() => { const e = [...document.querySelectorAll(${JSON.stringify(selector)})].find(e => e.offsetParent !== null); if (!e) return null; e.scrollIntoView({ block: 'nearest', inline: 'nearest' }); const r = e.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; })()`), 'shown: ' + selector, 200);
}
async function press(selector) { const { x, y } = await centre(selector); await mouse(x, y, true); }
async function key(name, code = name, keyCode = 0) { await send('Input.dispatchKeyEvent', { type: 'keyDown', key: name, code, windowsVirtualKeyCode: keyCode }); await send('Input.dispatchKeyEvent', { type: 'keyUp', key: name, code, windowsVirtualKeyCode: keyCode }); }
async function replace(selector, text) {
  await press(selector);
  await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'a', code: 'KeyA', windowsVirtualKeyCode: 65, modifiers: 2, commands: ['selectAll'] });
  await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'a', code: 'KeyA', windowsVirtualKeyCode: 65, modifiers: 2 });
  await key('Delete', 'Delete', 46);
  if (text) await send('Input.insertText', { text });
}
const drawerText = () => evaluate(`document.getElementById('aside').innerText`);
const stripText = () => evaluate(`document.getElementById('strip').innerText`);
const drawerState = () => evaluate(`[...document.querySelectorAll('#aside header .state')].map(e => e.textContent.trim()).join(' | ')`);
const isBuilt = async () => { const t = await drawerState(); return /(^|\| )built($| \|)/.test(t) ? t : null; };
/** The width of the strip's hairline as a number of percent, or null when it is not drawn. */
const stripHair = () => evaluate(`(() => { const i = document.querySelector('#strip .hair i'); return i ? parseFloat(i.style.width) : null; })()`);
const drawerHair = () => evaluate(`(() => { const i = document.querySelector('#aside .hair i'); return i ? parseFloat(i.style.width) : null; })()`);
const requestState = async id => (await api('build_request', { request: id })).state;
const newestRequest = async () => (await api('build_requests', { limit: 1 })).requests[0];

(async () => {
  let output = '';
  const catalog = path.join(temporary, 'catalog');
  server = launch(python, ['-u', 'app.py', '--port', '0', '--data', catalog, '--project-folder', folder], { cwd: root, env: process.env, stdio: ['ignore', 'pipe', 'pipe'] });
  server.stdout.on('data', chunk => { output += chunk; }); server.stderr.on('data', chunk => { serverErrors += chunk; });
  const port = await until(() => { if (server.exitCode !== null) throw Error('Tuldok exited: ' + serverErrors); return output.match(/127\.0\.0\.1:(\d+)/)?.[1]; }, 'Tuldok start-up', 1800);
  origin = 'http://127.0.0.1:' + port;
  auth = authenticatedFixture(); await auth.register(origin, catalog, root);
  const browser = launch(findBrowser(), ['--headless', '--no-sandbox', '--disable-gpu', '--no-first-run', '--hide-scrollbars', '--remote-debugging-port=0', `--window-size=${WIDTH},${HEIGHT}`, '--user-data-dir=' + path.join(temporary, 'browser'), 'about:blank'], { stdio: 'ignore', env: { ...process.env, XDG_CONFIG_HOME: temporary, XDG_CACHE_HOME: temporary } });
  const debugPort = await waitForDebugger(browser, path.join(temporary, 'browser', 'DevToolsActivePort'));
  const target = (await (await fetch('http://127.0.0.1:' + debugPort + '/json')).json()).find(item => item.type === 'page');
  socket = new WebSocket(target.webSocketDebuggerUrl); await once(socket, 'open');
  const session = cdpSession(socket, { timeoutMs: 120000, onEvent: event => {
    if (event.method === 'Runtime.exceptionThrown') errors.push(event.params.exceptionDetails.exception?.description || event.params.exceptionDetails.text);
    if (event.method === 'Runtime.consoleAPICalled' && event.params.type === 'error') errors.push(event.params.args.map(a => a.value ?? a.description).join(' '));
    if (event.method === 'Network.loadingFailed' && !event.params.canceled) failures.push({ error: event.params.errorText });
    if (event.method === 'Network.responseReceived' && event.params.response.status >= 400) failures.push({ url: event.params.response.url, status: event.params.response.status });
  } });
  send = session.send;
  evaluate = async expression => { const result = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }); if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails)); return result.result.value; };
  for (const domain of ['Page', 'Runtime', 'Network', 'Log']) await send(domain + '.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: WIDTH, height: HEIGHT, deviceScaleFactor: 1, mobile: false });
  await auth.browser(send, origin);

  // ---- 1. The page opens on a project with nothing built; the owner connects the two interpreters ----------
  await open('map');
  done('Opened: ' + (await stripText()).replace(/\s+/g, ' ').slice(0, 160));
  await shot('map-nothing-built');
  for (const [name, interpreter] of [['cpu', CPU], ['gpu', GPU]]) {
    const ref = 'environments/' + name;
    await hash('train/env:' + enc(ref));
    await replace(byKey('envconnect:' + ref + ':field:interpreter'), interpreter);
    await press(byKey('envconnect:' + ref + ':connect'));
    await until(async () => (await api('environment', { reference: ref })).state === 'ready', ref + ' ready', 900);
    await settled(ref + ' connected');
    done('Connected ' + ref + ' from the page: ' + (await api('environment', { reference: ref })).found.python);
  }
  await shot('environments-connected');

  // ---- 2. Plan and request a build of everything; watch the training on the page ----------------------------
  await hash('train');
  await press(byKey('train:every:plan')); await settled('plan of everything');
  await shot('plan-everything');
  await press(byKey('request:plan:*:request'));
  const first = await until(async () => { const r = await newestRequest(); return r && r.every ? r : null; }, 'the request of everything', 100);
  let seen = null;
  await until(async () => {
    const runs = (await api('runs')).runs, run = runs.find(r => r.state === 'running' && r.reference === 'recipes/small-net-a');
    if (run && !seen) {
      await hash('train/run:' + run.id);
      const width = await until(async () => { const w = await drawerHair(); return (w > 0 && w < 100) ? w : ((await api('run', { run: run.id })).state !== 'running' ? -1 : null); }, 'a hairline partly filled', 600);
      if (width > 0) { seen = { width, strip: await stripHair(), text: (await stripText()).replace(/\s+/g, ' ') }; await shot('training-small-net-a-running'); }
    }
    return ['succeeded', 'failed', 'cancelled'].includes(await requestState(first.id));
  }, 'the build of everything to end', 3600, 250);
  const firstEnd = await api('build_request', { request: first.id });
  assert.equal(firstEnd.state, 'succeeded', JSON.stringify(firstEnd));
  assert.ok(seen, 'the training was never seen running on the page');
  done('Built everything from the page (request ' + first.id.slice(0, 8) + ', ' + firstEnd.runs.length + ' runs). While small-net-a trained the run drawer hairline stood at ' + seen.width + '% and the strip at ' + seen.strip + '%: "' + seen.text.slice(0, 200) + '"');
  await hash('map/' + enc('recipes/small-net-a')); await until(isBuilt, 'small-net-a built in its drawer', 200);
  await shot('map-small-net-a-built');
  await hash('benchmarks'); await shot('benchmarks-two-subjects');

  // ---- 3. Branch from here: a draft, a changed setting, kept, saved ---------------------------------------
  const parent = 'recipes/small-net-a', ref = 'recipes/small-net-3-000-updates';
  await hash('map/' + enc(parent));
  await press(byKey('modelact:' + parent + ':branch')); await settled('the branch form');
  await replace(byKey('branch:' + parent + ':field:title'), 'Small net, 3,000 updates');
  await press(byKey('branch:' + parent + ':change-training-policy'));
  await replace(byKey('branch:' + parent + ':field:description'), 'Half the updates, to see how much accuracy that costs.');
  await shot('branch-form');
  await press(byKey('branch:' + parent + ':create'));
  await centre(byKey('draft:' + ref + ':keep')); await settled('the draft');
  const updates = await evaluate(`document.querySelector(${JSON.stringify(byKey('editor:' + ref + ':setting-updates'))}).value`);
  assert.equal(updates, '6000', 'the parent settings were copied into the draft');
  await evaluate(`document.getElementById('aside').scrollTop = 0`);
  await shot('draft-on-map');
  await replace(byKey('editor:' + ref + ':setting-updates'), '3000'); await key('Tab', 'Tab', 9);
  await shot('draft-updates-changed');
  assert.equal(fs.existsSync(path.join(folder, 'recipes', 'small-net-3-000-updates.json')), false);
  await press(byKey('draft:' + ref + ':keep')); await settled('kept');
  assert.equal((await api('definition', { reference: ref })).unsaved, true);
  done('Branched ' + parent + ' on the page, changed updates 6000 → 3000 in the form, kept: ' + ref + ' is an unsaved definition; strip: "' + (await stripText()).replace(/\s+/g, ' ').slice(0, 140) + '"');
  await shot('draft-kept-unsaved');
  await press(byKey('model:' + ref + ':save')); await settled('saved');
  const saved = JSON.parse(fs.readFileSync(path.join(folder, 'recipes', 'small-net-3-000-updates.json'), 'utf8'));
  assert.equal(saved.derived_from, parent); assert.equal(saved.run.settings.updates, 3000); assert.equal(saved.run.settings.learning_rate, 0.001); assert.equal(saved.change, 'training-policy');
  assert.ok(!('settings_file' in saved.run) && !('labels' in saved) && !('card' in saved));
  done('Saved from the page: recipes/small-net-3-000-updates.json is in the folder with derived_from, change and settings.updates 3000');

  // ---- 4. Plan, request, watch it train, see it built on the map ---------------------------------------------
  await press(byKey('model:' + ref + ':plan')); await settled('the plan of the branch');
  await shot('plan-branch');
  await press(byKey('request:plan:' + ref + ':request'));
  const second = await until(async () => { const r = await newestRequest(); return r && r.id !== first.id ? r : null; }, 'the request of the branch', 100);
  seen = null;
  await until(async () => {
    const run = (await api('runs', { reference: ref })).runs.find(r => r.state === 'running');
    if (run && !seen) {
      await hash('train/run:' + run.id);
      const width = await until(async () => { const w = await drawerHair(); return (w > 0 && w < 100) ? w : ((await api('run', { run: run.id })).state !== 'running' ? -1 : null); }, 'a hairline partly filled', 600);
      if (width > 0) { seen = { width, strip: await stripHair(), text: (await drawerText()).replace(/\s+/g, ' ') }; await shot('training-branch-running'); await theme('dark'); await shot('training-branch-running-dark'); await theme('light'); }
    }
    return ['succeeded', 'failed', 'cancelled'].includes(await requestState(second.id));
  }, 'the build of the branch to end', 3600, 250);
  assert.equal(await requestState(second.id), 'succeeded');
  assert.ok(seen, 'the branch was never seen training on the page');
  const marker = await evaluate(`(window.__acceptance = window.__acceptance || Math.random())`);
  await hash('map/' + enc(ref));
  const turned = Date.now(); await until(isBuilt, 'the branch built in its drawer', 300);
  const turnedIn = Date.now() - turned;
  await until(async () => /^Idle/.test((await stripText()).trim()), 'the strip idle after the branch', 100);
  assert.equal(await evaluate('window.__acceptance'), marker, 'the page was not reloaded');
  const node = await evaluate(`(() => { const g = document.querySelector('#main svg g.node[data-id=${JSON.stringify(ref)}]'); return g ? g.getAttribute('class') : null; })()`);
  const model = (await api('map')).models.find(m => m.reference === ref);
  assert.equal(model.state, 'built'); assert.equal(model.derived_from, parent); assert.equal(model.unsaved, false); assert.ok(model.trained_at);
  done('Requested from the plan view; the branch trained on the GPU (hairline at ' + seen.width + '% in the run drawer); request ' + second.id.slice(0, 8) + ' succeeded; ' + turnedIn + ' ms later, with no reload, the drawer said built; the map shows it built, dated by its run ' + model.trained_at + ', node class "' + node + '"');
  await evaluate(`document.getElementById('aside').scrollTop = 0`);
  await shot('map-branch-built'); await theme('dark'); await shot('map-branch-built-dark'); await theme('light');

  // ---- 5. Edit another definition in the text view: the benchmark gains the new model as a subject ------------
  await hash('overview'); await press(byKey('open-edit:benchmarks/held-out')); await settled('the benchmark editor');
  const text = await evaluate(`document.querySelector(${JSON.stringify(byKey('editor:benchmarks/held-out:text'))}).value`);
  const subject = '    {"name": "small-net-b", "title": "Small net, 3,000 updates", "recipe": "' + ref + '", "argument": "model:{recipe}/model.pt"},\n';
  const changed = text.replace('    {"name": "predict-zero"', subject + '    {"name": "predict-zero"');
  assert.notEqual(changed, text);
  await replace(byKey('editor:benchmarks/held-out:text'), changed);
  await press(byKey('edit:benchmarks/held-out:keep')); await settled('the benchmark kept');
  await shot('benchmark-edited-unsaved');
  await press(byKey('save:save')); await settled('the benchmark saved');
  assert.equal(fs.readFileSync(path.join(folder, 'benchmarks', 'held-out.json'), 'utf8'), changed);
  done('Edited benchmarks/held-out in the text view (a third subject), kept and saved from the strip: the file is the text typed, byte for byte');

  // ---- 6. An agent asks for the benchmark; the owner approves it from Needs you ------------------------------
  const agent = await credential('Acceptance agent', ['inspect', 'execute']);
  const asked = await api('request_build', { targets: ['benchmarks/held-out'] }, agent);
  assert.equal(asked.state, 'awaiting-approval');
  // The page is open and idle; nothing tells it but its own fifteen-second look.
  const before = await evaluate(`document.getElementById('needs-btn').textContent`), mark = await evaluate('window.__acceptance');
  const noticed = Date.now();
  await until(() => evaluate(`document.getElementById('needs-btn').textContent !== ${JSON.stringify(before)}`), 'Needs you to count the agent request without a reload', 400);
  assert.equal(await evaluate('window.__acceptance'), mark, 'the page was not reloaded');
  done('The idle page noticed the agent request by itself after ' + Math.round((Date.now() - noticed) / 1000) + ' s: "' + before + '" became "' + await evaluate(`document.getElementById('needs-btn').textContent`) + '"');
  await press('#needs-btn'); await centre(byKey('need:request:' + asked.id + ':approve'));
  await shot('needs-you-agent-request');
  await press(byKey('need:request:' + asked.id + ':approve'));
  const t0 = Date.now(), seenStrip = [];
  const sample = async () => { const t = (await stripText()).replace(/\s+/g, ' ').replace(/ Read at.*$/, '').slice(0, 110); if (!seenStrip.length || seenStrip[seenStrip.length - 1][1] !== t) seenStrip.push([Date.now() - t0, t]); };
  await until(async () => { await sample(); return ['succeeded', 'failed', 'cancelled'].includes(await requestState(asked.id)); }, 'the agent build to end', 3600, 250);
  const ended = Date.now() - t0;
  await until(async () => { await sample(); return /^Idle/.test(seenStrip[seenStrip.length - 1][1]); }, 'the strip idle after the agent build: ' + JSON.stringify(seenStrip), 60, 250);
  done('The strip while the agent build ran (ms after Approve; the request ended at ' + ended + '): ' + seenStrip.map(([at, t]) => at + ' "' + t + '"').join(' → '));
  const agentEnd = await api('build_request', { request: asked.id });
  assert.equal(agentEnd.state, 'succeeded', JSON.stringify(agentEnd));
  await key('Escape', 'Escape', 27);
  await hash('benchmarks'); await settled('benchmarks');
  const rows = (await api('results', { benchmark: 'held-out', metric: 'error' })).rows;
  const errorOf = name => (rows.find(r => r.subject === name) || {}).median;
  assert.ok(errorOf('small-net-b') != null, 'the new model has a result: ' + JSON.stringify(rows.map(r => r.subject)));
  done('An agent asked for benchmarks/held-out (awaiting approval); approved from Needs you on the page; it ran ' + agentEnd.runs.length + ' run(s) and succeeded. Median error: small-net-a ' + errorOf('small-net-a') + ', small-net-b (3,000 updates) ' + errorOf('small-net-b') + ', predict-zero ' + errorOf('predict-zero'));
  await shot('benchmarks-three-subjects'); await theme('dark'); await shot('benchmarks-three-subjects-dark'); await theme('light');
  await hash('train'); await shot('train-after');
  await hash('map'); await shot('map-after');

  const summary = await api('summary'), activity = await api('activity', { limit: 100 });
  done('In the end: states ' + JSON.stringify(summary.states) + '; activity: ' + activity.items.map(i => i.operation || i.name).reverse().join(', '));
  assert.deepEqual(errors, [], 'script errors: ' + JSON.stringify(errors));
  assert.deepEqual(failures, [], 'failed requests: ' + JSON.stringify(failures));
  done('No script error and no failed request in the whole run');
  fs.writeFileSync(path.join(out, 'receipt.json'), JSON.stringify({ at: new Date().toISOString(), log }, null, 2) + '\n');
})().catch(async error => {
  console.error('FAILED', error.stack || error); console.error('script errors', JSON.stringify(errors).slice(0, 2000)); console.error('failed requests', JSON.stringify(failures).slice(0, 2000));
  console.error('server stderr tail', serverErrors.slice(-3000));
  try { await shot('failure'); } catch (e) { /* no page */ }
  process.exitCode = 1;
}).finally(async () => {
  try { socket && socket.close(); } catch (e) { /* closed */ }
  for (const child of children.slice().reverse()) await stop(child);
  fs.rmSync(temporary, { recursive: true, force: true });
});
