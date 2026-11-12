'use strict';
// The project workspace (docs/plans/definition-first-projects/spec-w2.md, slice T18) in a headless browser:
// Tuldok started with --project-folder on a copy of the minimal fixture, or with --lab-root on a real project
// folder (opened in place, read only: opening imports it into the disposable database named by
// TULDOK_DATABASE_URL). Signs in, opens every built tab in light and dark at 1440 by 900, opens a model and its
// card, hovers a map node, uses the kind and text filters, the track, the status strip and Needs you, and fails on
// any script error, failed request, sideways overflow or empty main area. Nothing may be asked of the project
// that changes it: its activity log stays empty and the fixture copy is unchanged byte for byte.
//   node tests/browser_project_workspace.cjs [--lab-root <project folder>]
const assert = require('node:assert/strict'), fs = require('node:fs'), os = require('node:os'), path = require('node:path'), crypto = require('node:crypto');
const { spawn, execFileSync } = require('node:child_process'), { once } = require('node:events');
const { authenticatedFixture } = require('./auth_helpers.cjs'), { waitForDebugger } = require('./browser_startup.cjs'), { cdpSession } = require('./browser_cdp_session.cjs'), { qaDirectory, screenshotOptions } = require('./qa_artifacts.cjs');

const root = path.resolve(__dirname, '..');
const argv = process.argv.slice(2), labAt = argv.indexOf('--lab-root');
const labRoot = labAt >= 0 ? path.resolve(argv[labAt + 1] || '') : null;
if (labAt >= 0) assert.ok(argv[labAt + 1] && fs.existsSync(path.join(labRoot, 'tuldok.json')), '--lab-root names a project folder (it holds tuldok.json)');
assert.ok(process.env.TULDOK_DATABASE_URL, 'TULDOK_DATABASE_URL must name a disposable PostgreSQL cluster');
const venv = path.join(root, '.venv', 'bin');
if (fs.existsSync(path.join(venv, 'python'))) process.env.PATH = venv + path.delimiter + process.env.PATH;   // auth_helpers runs python3
const python = fs.existsSync(path.join(venv, 'python')) ? path.join(venv, 'python') : 'python3';
const WIDTH = 1440, HEIGHT = 900;
const TABS = ['map', 'data', 'train', 'benchmarks', 'analysis', 'overview'];
const BUILT = ['map', 'overview'];

const temporary = fs.mkdtempSync(path.join(os.tmpdir(), 'tuldok-workspace-browser-'));
const report = qaDirectory(root, labRoot ? 'project-workspace-lab' : 'project-workspace');
const children = [], checks = [], errors = [], failedRequests = [], bounds = [];
let server, serverErrors = '', origin, auth, socket, session, send, evaluate;
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
async function until(fn, label, tries = 300) { for (let i = 0; i < tries; i++) { const value = await fn(); if (value) return value; await pause(100); } throw Error('Timed out: ' + label); }
function check(text) { checks.push(text); console.log('PASS ' + text); }
function launch(command, args, options) { const child = spawn(command, args, options); children.push(child); return child; }
async function stop(child) { if (!child || child.exitCode !== null || child.signalCode !== null) return; const exited = once(child, 'exit'); child.kill('SIGTERM'); await Promise.race([exited, pause(10000)]); if (child.exitCode === null && child.signalCode === null) { child.kill('SIGKILL'); await exited; } }
function snapshot(directory) {
  const files = {};
  (function walk(at) { for (const item of fs.readdirSync(at, { withFileTypes: true })) { const next = path.join(at, item.name); if (item.isDirectory()) walk(next); else files[path.relative(directory, next)] = item.isFile() ? crypto.createHash('sha256').update(fs.readFileSync(next)).digest('hex') : 'special'; } })(directory);
  return files;
}
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
let owned = null;
async function api(name, body = {}) {
  const capabilities = await (await auth.fetch(origin + '/api/agent/capabilities')).json();
  const operation = capabilities.operations.find(item => item.id === 'project.' + name), contract = operation.contracts[operation.contracts.length - 1];
  const response = await auth.fetch(origin + '/api/project/' + name, { method: 'POST', headers: { 'Content-Type': 'application/json', 'Tuldok-Operation-Contract': 'project.' + name + '/' + contract.version + '/' + contract.sha256 }, body: JSON.stringify(body) });
  const value = await response.json(); assert.equal(response.status, 200, JSON.stringify(value)); return value;
}

async function shot(name) {
  await evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))');
  fs.writeFileSync(path.join(report, name + '.jpg'), Buffer.from((await send('Page.captureScreenshot', screenshotOptions)).data, 'base64'));
}
/** No sideways overflow of the page or of a non-map main area, and a main area that shows something. */
async function inspect(label) {
  const value = await evaluate(`(() => {
    const main = document.getElementById('main'), top = document.querySelector('.top'), strip = document.getElementById('strip');
    const text = main.innerText.trim();
    return { label: ${JSON.stringify(label)}, viewport: innerWidth, page: document.documentElement.scrollWidth, body: document.body.scrollWidth,
      main: main.classList.contains('map') ? null : [main.scrollWidth, main.clientWidth], top: [top.scrollWidth, top.clientWidth], strip: [strip.scrollWidth, strip.clientWidth],
      text: text.length, children: main.children.length, reading: /^Reading/.test(text),
      shifted: [document.body, document.querySelector('.stage')].some(e => e.scrollLeft || e.scrollTop) };
  })()`);
  bounds.push(value);
  assert.ok(value.page <= value.viewport && value.body <= value.viewport, 'Sideways overflow of the page: ' + JSON.stringify(value));
  assert.ok(!value.main || value.main[0] <= value.main[1] + 1, 'Sideways overflow of the main area: ' + JSON.stringify(value));
  assert.ok(value.top[0] <= value.top[1] + 1 && value.strip[0] <= value.strip[1] + 1, 'Sideways overflow of the top bar or strip: ' + JSON.stringify(value));
  assert.ok(value.text > 0 && value.children > 0 && !value.reading, 'Empty main area: ' + JSON.stringify(value));
  assert.ok(!value.shifted, 'The shell is scrolled: ' + JSON.stringify(value));
}
async function open(theme, hash) {
  await send('Emulation.setEmulatedMedia', { features: [{ name: 'prefers-color-scheme', value: theme }, { name: 'prefers-reduced-motion', value: 'reduce' }] });
  await send('Page.navigate', { url: origin + '/?theme=' + theme + '#' + hash });
  await until(() => evaluate(`document.readyState === 'complete' && !!document.getElementById('needs-btn') && !document.getElementById('needs-btn').disabled`), 'the project read (' + hash + ')');
}
async function tab(name) {
  await evaluate(`location.hash = '#${name}'`);
  await until(() => evaluate(`(() => { const t = document.getElementById('main').innerText; return t.trim().length > 0 && !t.includes('Reading'); })()`), 'tab ' + name);
}
async function mouse(x, y, click = false) {
  await send('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y });
  if (click) { await send('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 }); await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 }); }
}
async function centre(selector) {
  const box = await evaluate(`(() => { const e = document.querySelector(${JSON.stringify(selector)}); if (!e) return null; e.scrollIntoView({ block: 'nearest', inline: 'nearest' }); const r = e.getBoundingClientRect(); return { x: r.left + r.width / 2, y: r.top + r.height / 2 }; })()`);
  assert.ok(box, 'Missing ' + selector);
  return box;
}
async function press(selector) { const { x, y } = await centre(selector); await mouse(x, y, true); }

(async () => {
  let folder;
  if (labRoot) folder = labRoot;
  else {
    fs.cpSync(path.join(root, 'tests', 'fixtures', 'tuldok_project', 'minimal'), path.join(temporary, 'fixture'), { recursive: true });
    folder = path.join(temporary, 'fixture', 'project');
    // One more model with no group, no kind of change, no training date and no result, to show each absence.
    fs.writeFileSync(path.join(folder, 'recipes', 'loose.json'), JSON.stringify({ format: 'tuldok_definition_v1', kind: 'recipe', title: 'A recipe with nothing set', description: 'Neither grouped, nor kinded, nor dated, nor measured.', earlier_work: { rebuild: 'no', reason: 'A browser check fixture.' }, model: 'models/stepper' }, null, 2) + '\n');
  }
  const before = labRoot ? null : snapshot(folder);
  const home = path.join(temporary, 'home'), catalog = path.join(temporary, 'catalog'); fs.mkdirSync(home);
  owned = [folder, catalog]; dropOwned(folder, catalog);
  let output = '';
  server = launch(python, ['-u', 'app.py', '--port', '0', '--data', catalog, '--project-folder', folder], { cwd: root, env: { ...process.env, TULDOK_PROJECT_HOME: home }, stdio: ['ignore', 'pipe', 'pipe'] });
  server.stdout.on('data', chunk => { output += chunk; }); server.stderr.on('data', chunk => { serverErrors += chunk; });
  const port = await until(() => { if (server.exitCode !== null) throw Error('Tuldok exited: ' + serverErrors); return output.match(/127\.0\.0\.1:(\d+)/)?.[1]; }, 'Tuldok start-up', 1800);
  origin = 'http://127.0.0.1:' + port;
  auth = authenticatedFixture(); await auth.register(origin, catalog, root);
  const map = await api('map'), summary = await api('summary');
  check('Tuldok serves ' + summary.name + ' with ' + map.models.length + ' models, ' + map.groups.length + ' groups, ' + map.edges.filter(e => e.kind === 'derived').length + ' derivations, ' + map.comparisons.length + ' comparisons and ' + map.models.filter(m => m.value != null).length + ' track values');

  const browser = launch(findBrowser(), ['--headless', '--no-sandbox', '--disable-gpu', '--no-first-run', '--hide-scrollbars', '--remote-debugging-port=0', `--window-size=${WIDTH},${HEIGHT}`, '--user-data-dir=' + path.join(temporary, 'browser'), 'about:blank'], { stdio: 'ignore', env: { ...process.env, XDG_CONFIG_HOME: temporary, XDG_CACHE_HOME: temporary } });
  const debugPort = await waitForDebugger(browser, path.join(temporary, 'browser', 'DevToolsActivePort'));
  const target = (await (await fetch('http://127.0.0.1:' + debugPort + '/json')).json()).find(item => item.type === 'page');
  socket = new WebSocket(target.webSocketDebuggerUrl); await once(socket, 'open');
  session = cdpSession(socket, { timeoutMs: 60000, onEvent: event => {
    if (event.method === 'Runtime.exceptionThrown') errors.push(event.params.exceptionDetails.exception?.description || event.params.exceptionDetails.text);
    if (event.method === 'Runtime.consoleAPICalled' && event.params.type === 'error') errors.push(event.params.args.map(a => a.value ?? a.description).join(' '));
    if (event.method === 'Log.entryAdded' && event.params.entry.level === 'error') errors.push(event.params.entry.text + ' ' + (event.params.entry.url || ''));
    if (event.method === 'Network.loadingFailed' && !event.params.canceled) failedRequests.push({ id: event.params.requestId, error: event.params.errorText });
    if (event.method === 'Network.responseReceived' && event.params.response.status >= 400) failedRequests.push({ url: event.params.response.url, status: event.params.response.status });
  } });
  send = session.send;
  evaluate = async expression => { const result = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true }); if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails)); return result.result.value; };
  await send('Page.enable'); await send('Runtime.enable'); await send('Network.enable'); await send('Log.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: WIDTH, height: HEIGHT, deviceScaleFactor: 1, mobile: false });
  await auth.browser(send, origin);

  for (const theme of ['light', 'dark']) {
    await open(theme, 'map');
    assert.equal(await evaluate(`getComputedStyle(document.documentElement).colorScheme`), theme);
    for (const name of TABS) {
      await tab(name);
      await inspect(theme + ' ' + name);
      if (!BUILT.includes(name)) assert.match(await evaluate(`document.getElementById('main').innerText`), /is not built yet\.$/);
      await shot(theme + '-' + name);
      if (name === 'map') {   // the rest of a wide map, and the end of the list
        const wide = await evaluate(`(() => { const m = document.querySelector('.tree-map'); return m.scrollWidth > m.clientWidth + 10; })()`);
        if (wide) {
          await evaluate(`(() => { const m = document.querySelector('.tree-map'); m.scrollLeft = (m.scrollWidth - m.clientWidth) / 2; })()`); await shot(theme + '-map-middle');
          await evaluate(`(() => { const m = document.querySelector('.tree-map'); m.scrollLeft = m.scrollWidth; document.querySelector('.tree-host').scrollTop = 1e7; })()`); await shot(theme + '-map-end');
          await evaluate(`(() => { document.querySelector('.tree-map').scrollLeft = 0; document.querySelector('.tree-host').scrollTop = 0; })()`);
        }
      }
    }
    check('Every tab in ' + theme + ' at ' + WIDTH + ' by ' + HEIGHT + ': no overflow, no empty main area; the four tabs of the next slice say they are not built yet');
  }
  const fonts = await evaluate(`document.fonts.ready.then(() => [...document.fonts].filter(f => f.status === 'loaded').map(f => f.family + ' ' + f.style))`);
  assert.ok(fonts.some(f => /Ubuntu Sans"? normal/.test(f)) && fonts.some(f => /Ubuntu Sans Mono"? normal/.test(f)), 'The vendored faces load: ' + JSON.stringify(fonts));
  check('The vendored Ubuntu Sans and Ubuntu Sans Mono load: ' + fonts.join(', '));

  for (const theme of ['light', 'dark']) {
    await open(theme, 'map');
    const shown = await evaluate(`({ sections: [...document.querySelectorAll('.tree-map .bandlabel')].map(t => t.firstChild.textContent), nodes: document.querySelectorAll('.tree-map .node').length, rows: document.querySelectorAll('.tree-list .trow').length, lines: document.querySelectorAll('.tree-map .der').length,
      unset: document.querySelectorAll('.tree-map .node.unset').length, unsetChips: [...document.querySelectorAll('.tree-list .chip.unset')].map(c => c.textContent), noValue: document.querySelectorAll('.tree-list .mbar.none').length })`);
    assert.equal(shown.nodes, map.models.length); assert.equal(shown.rows, map.models.length);
    // Each absence is shown: a section for models without a group, a hollow mark named for those without a kind, an empty bar without a value.
    assert.equal(shown.sections.includes('Not in a group'), map.models.some(m => !m.group));
    assert.equal(shown.unset, map.models.filter(m => !m.change).length); assert.ok(shown.unsetChips.every(t => t === 'Kind not set'));
    assert.equal(shown.noValue, map.models.filter(m => m.value == null).length);
    // Hover a node with a track value: its tip names it.
    const hovered = map.models.find(m => m.value != null && m.short) || map.models[0];
    const { x, y } = await centre(`.tree-map .node[data-id="${hovered.reference}"]`);
    await mouse(x, y);
    const tip = await until(() => evaluate(`(() => { const t = document.querySelector('#main > .tip'); return t && !t.hidden && t.innerText; })()`), 'the hover tip');
    assert.ok(tip.includes(hovered.title), 'The tip names the hovered model: ' + tip);
    await shot(theme + '-map-hover');
    // Open a model with a card in the drawer.
    const opened = map.models.find(m => m.card && map.comparisons.some(c => c.from === m.reference || c.to === m.reference)) || map.models.find(m => m.card) || map.models[0];
    await press(`.tree-map .node[data-id="${opened.reference}"]`);
    await until(() => evaluate(`document.getElementById('drawer').classList.contains('open') && ![...document.querySelectorAll('#aside .note')].some(e => e.textContent === 'Reading…')`), 'the drawer filled');
    const drawer = await evaluate(`({ title: document.querySelector('#aside h2').textContent, card: document.querySelector('#aside .card-md') ? document.querySelector('#aside .card-md').children.length : 0, arcs: document.querySelectorAll('.tree-map .cmp').length, failures: [...document.querySelectorAll('#aside .failure')].map(e => e.textContent), hash: location.hash })`);
    assert.equal(drawer.title, opened.title); assert.deepEqual(drawer.failures, []);
    if (opened.card) assert.ok(drawer.card > 0, 'The card is rendered');
    assert.equal(drawer.hash, '#map/' + encodeURIComponent(opened.reference));
    await evaluate(`document.getElementById('drawer').scrollTop = 0`);
    await shot(theme + '-map-drawer');
    await evaluate(`(() => { const c = document.querySelector('#aside .card-md'); if (c) c.scrollIntoView({ block: 'start' }); })()`);
    await shot(theme + '-map-card');
    // The track.
    if (map.track) {
      await press('#main .filters button[title]');
      await until(() => evaluate(`document.querySelectorAll('.tree-map .tpt').length`), 'the track');
      assert.equal(await evaluate(`document.querySelectorAll('.tree-map .tpt').length`), map.models.filter(m => m.value != null).length);
      await evaluate(`document.querySelector('.tree-map').scrollTop = 1e6`);
      await shot(theme + '-map-track');
      await press('#main .filters button[title]');
    }
    await press('#drawer .close');
    await until(() => evaluate(`!document.getElementById('drawer').classList.contains('open')`), 'the drawer closed');
    check(theme + ': ' + shown.sections.length + ' sections, every model on the map and in the list, a hover tip, ' + opened.reference + ' opened with its card (' + drawer.card + ' blocks, ' + drawer.arcs + ' comparison arcs)' + (map.track ? ', the track drawn' : ''));
  }

  // The card renderer builds elements only, whatever the text holds.
  await open('light', 'map');
  const sample = ['# Title <img src=x>', '', 'Some **bold**, *italic*, `code` and [a link](https://example.invalid/x) <b>not bold</b>.', '',
    '- one', '  - nested *two*', '- three', '', '1. first', '2. second', '', '| A | B |', '| --- | ---: |', '| `x|y` | 2 |', '',
    '```js', 'const a = "<script>";', '```', '', '> quoted', '', '---', 'Setext', '======'].join('\n');
  const rendered = await evaluate(`(() => { const n = window.TuldokMarkdown.render(${JSON.stringify(sample)}); return {
    tags: [...n.querySelectorAll('*')].map(e => e.tagName.toLowerCase()).filter((t, i, a) => a.indexOf(t) === i).sort(),
    h1: n.querySelector('h1').textContent, code: n.querySelector('pre code').textContent, cell: n.querySelector('td code').textContent,
    nested: n.querySelector('ul ul li em').textContent, link: n.querySelector('.link').title, text: n.textContent }; })()`);
  assert.deepEqual(rendered.tags, ['blockquote', 'code', 'div', 'em', 'h1', 'hr', 'li', 'ol', 'p', 'pre', 'span', 'strong', 'table', 'tbody', 'td', 'th', 'thead', 'tr', 'ul']);
  assert.equal(rendered.h1, 'Title <img src=x>'); assert.equal(rendered.code, 'const a = "<script>";'); assert.equal(rendered.cell, 'x|y');
  assert.equal(rendered.nested, 'two'); assert.equal(rendered.link, 'https://example.invalid/x'); assert.ok(rendered.text.includes('<b>not bold</b>'));
  check('The card renderer makes headings, emphasis, code, nested lists, tables, quotes and rules as elements; markup in the text stays text');

  // Filters: one kind, then text; then both cleared.
  const kind = map.models.find(m => m.change)?.change;
  if (kind) {
    await press(`#main .filters button[data-kind="${kind}"]`);
    const dimmed = await until(() => evaluate(`document.querySelectorAll('.tree-map .node.dim').length || (document.querySelectorAll('.tree-list .trow').length === ${map.models.filter(m => m.change === kind).length} && -1)`), 'the kind filter');
    const rows = await evaluate(`document.querySelectorAll('.tree-list .trow').length`);
    assert.equal(rows, map.models.filter(m => m.change === kind).length, 'The list keeps only the chosen kind');
    assert.equal(await evaluate(`document.querySelector('#main .filters button[data-kind="${kind}"]').getAttribute('aria-pressed')`), 'true');
    await shot('light-map-kind-filter');
    await press(`#main .filters button[data-kind="${kind}"]`);
    await until(() => evaluate(`document.querySelectorAll('.tree-list .trow').length === ${map.models.length}`), 'the kind filter cleared');
    check('Kind filter ' + kind + ': ' + rows + ' rows, ' + Math.max(0, dimmed) + ' nodes dimmed; cleared again');
  }
  const word = (map.models.find(m => m.short) || map.models[0]).title.split(/\s+/)[0];
  await press('#main .filters input[type="search"]');
  await send('Input.insertText', { text: word });
  const wanted = map.models.filter(m => [m.title, m.short, m.description, m.reference].some(s => s && s.toLowerCase().includes(word.toLowerCase()))).length;
  await until(() => evaluate(`document.querySelectorAll('.tree-list .trow').length <= ${wanted}`), 'the text filter');
  const typed = await evaluate(`({ rows: document.querySelectorAll('.tree-list .trow').length, focus: document.activeElement && document.activeElement.type, value: document.activeElement && document.activeElement.value })`);
  assert.ok(typed.rows > 0 && typed.rows <= wanted, 'Text filter rows: ' + JSON.stringify(typed));
  assert.deepEqual([typed.focus, typed.value], ['search', word], 'The search box keeps the focus while typing');
  await shot('light-map-text-filter');
  check('Text filter "' + word + '": ' + typed.rows + ' rows, the search box keeps the focus');

  // Status strip and Needs you.
  for (const theme of ['light', 'dark']) {
    await open(theme, 'map');
    const strip = await evaluate(`document.getElementById('strip').innerText`);
    assert.match(strip, /\d+ models?: /); assert.match(strip, /Needs you · \d+/);
    await press('#needs-btn');
    await until(() => evaluate(`!document.getElementById('needs-panel').hidden && document.querySelectorAll('#needs-panel .needs li').length > 0`), 'Needs you opened');
    const needs = await evaluate(`[...document.querySelectorAll('#needs-panel .needs li')].map(li => li.innerText)`);
    await shot(theme + '-needs-you');
    await send('Input.dispatchKeyEvent', { type: 'keyDown', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 }); await send('Input.dispatchKeyEvent', { type: 'keyUp', key: 'Escape', code: 'Escape', windowsVirtualKeyCode: 27 });
    await until(() => evaluate(`document.getElementById('needs-panel').hidden`), 'Needs you closed by Escape');
    check(theme + ' strip: "' + strip.split('\n').join(' ') + '"; Needs you lists ' + needs.length + ': ' + needs.join(' | '));
  }

  // The report, from the Overview tab.
  await open('light', 'overview');
  await press('#main a[href="#overview/report"]');
  await until(() => evaluate(`(() => { const f = document.querySelector('iframe.report-frame'); return f && f.srcdoc.length > 100; })()`), 'the report');
  await pause(500); await inspect('light report'); await shot('light-overview-report');
  assert.deepEqual(await evaluate(`[document.getElementById('main').scrollLeft, document.querySelector('.report-bar').getBoundingClientRect().top > 0]`), [0, true], 'The report view starts at its top left');
  const frameBox = await evaluate(`(() => { const r = document.querySelector('iframe.report-frame').getBoundingClientRect(), b = document.querySelector('.report-bar').getBoundingClientRect(); return [Math.round(r.left), Math.round(r.top), Math.round(r.width), Math.round(r.height), Math.round(b.left), Math.round(b.top)]; })()`);
  check('The Overview links to the report, shown in a sandboxed frame at ' + frameBox.join(','));

  const activity = await api('activity');
  assert.equal(activity.total, 0, 'Nothing was asked of the project: ' + JSON.stringify(activity.items));
  if (before) assert.deepEqual(snapshot(folder), before, 'The fixture copy is unchanged');
  assert.deepEqual(errors, [], 'Script errors'); assert.deepEqual(failedRequests, [], 'Failed requests');
  check('No script error, no failed request, an empty activity log' + (before ? ', the folder unchanged' : ''));
  fs.writeFileSync(path.join(report, 'receipt.json'), JSON.stringify({ status: 'pass', folder, checks, bounds }, null, 2) + '\n');
  console.log('Screenshots and receipt in ' + report);
})().catch(async error => {
  process.exitCode = 1;
  console.error(error); if (serverErrors) console.error('Server:', serverErrors.slice(-4000));
  console.error('Script errors:', JSON.stringify(errors)); console.error('Failed requests:', JSON.stringify(failedRequests));
  try { if (evaluate) { await shot('failure'); console.error('Page:', (await evaluate('document.body.innerText')).slice(0, 2000)); } } catch (_) { /* the page is gone */ }
  fs.writeFileSync(path.join(report, 'failure.json'), JSON.stringify({ status: 'failed', error: String(error && error.stack || error), checks, bounds, errors, failedRequests }, null, 2) + '\n');
  console.error('Screenshots in ' + report);
}).finally(async () => {
  try { session?.close(); } catch (_) { /* closed */ }
  for (const child of children.reverse()) await stop(child);
  if (owned) try { dropOwned(...owned); } catch (error) { console.error('Dropping the disposable schemas failed:', error.message); process.exitCode = 1; }
  fs.rmSync(temporary, { recursive: true, force: true });
});
