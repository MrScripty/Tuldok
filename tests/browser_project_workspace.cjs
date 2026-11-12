'use strict';
// The project workspace (docs/plans/definition-first-projects/spec-w2.md, slices T18 and T19) in a headless
// browser: Tuldok started with --project-folder on a copy of the minimal fixture, or with --lab-root on a real
// project folder (opened in place, read only: opening imports it into the disposable database named by
// TULDOK_DATABASE_URL). The fixture copy also gets the buildable fixture's definitions and stand-in commands
// (which finish in a second and train nothing), and before Tuldok starts the command line builds some of them,
// lets one fail, imports per-case values, and an agent asks for a build that waits for approval: so the Train,
// Data and Analysis tabs have runs, products, a request and values to show.
// Signs in, opens every tab in light and dark at 1440 by 900, opens a model and its card, hovers a map node, uses
// the kind and text filters, the track, the status strip and Needs you; on Benchmarks picks a benchmark, hovers
// and focuses a point, sorts the table and makes a compare set of two that the address keeps; opens a run and a
// build request on Train, a dataset on Data, picks a metric on Analysis; and fails on any script error, failed
// request, sideways overflow or empty main area. Nothing may be asked of the project that changes it: its
// activity log gains nothing while the page is open and the fixture copy is unchanged byte for byte.
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

/** Waits until neither the main area nor the drawer is still reading. */
async function settled(label) {
  await until(() => evaluate(`(() => { const reading = e => [...e.querySelectorAll('.note')].some(n => n.textContent === 'Reading…'); return !reading(document.getElementById('main')) && !reading(document.getElementById('aside')) && !document.getElementById('main').hasAttribute('aria-busy'); })()`), label);
  await pause(150);
}
async function choose(selector, value) {
  await evaluate(`(() => { const s = document.querySelector(${JSON.stringify(selector)}); s.value = ${JSON.stringify(value)}; s.dispatchEvent(new Event('change')); })()`);
  await settled('the choice ' + value);
}
async function tipShown() { return until(() => evaluate(`(() => { const t = [...document.querySelectorAll('#main .tip')].find(t => !t.hidden); return t && t.innerText; })()`), 'a chart tip'); }
async function drawerOpen() { await until(() => evaluate(`document.getElementById('drawer').classList.contains('open')`), 'the drawer'); await settled('the drawer filled'); assert.deepEqual(await evaluate(`[...document.querySelectorAll('#aside .failure')].map(e => e.textContent)`), [], 'The drawer reads without failure'); }
async function scrollTo(selector) { await evaluate(`(() => { const e = document.querySelector(${JSON.stringify(selector)}); const m = document.getElementById('main'); m.scrollTop += e.getBoundingClientRect().top - m.getBoundingClientRect().top - 8; })()`); }

/** The Benchmarks, Train, Data and Analysis tabs, with what can be done on them, in both themes. */
async function otherTabs(map) {
  const overview = await api('results_overview'), charts = (await api('definitions', { kind: 'chart' })).definitions;
  const chartBench = {};
  for (const c of charts) { const d = await api('definition', { reference: c.reference }); chartBench[c.reference] = { benchmark: String(d.document.benchmark).replace(/^benchmarks\//, ''), form: d.document.form }; }
  // The benchmark with the most chart forms (the fixture's rollout has all four).
  const forms = name => new Set(Object.values(chartBench).filter(c => c.benchmark === name).map(c => c.form)).size;
  const bench = overview.benchmarks.slice().sort((a, b) => forms(b.benchmark) - forms(a.benchmark) || b.subjects_with_results - a.subjects_with_results)[0].benchmark;
  const runs = (await api('runs')).runs, requests = (await api('build_requests')).requests, products = (await api('products')).products;
  for (const theme of ['light', 'dark']) {
    // Benchmarks: pick, hover and focus a point, sort, compare two, open one.
    await open(theme, 'benchmarks'); await settled('benchmarks');
    await choose('#main select[data-key="benchmark"]', bench);
    const drawn = await evaluate(`({ charts: document.querySelectorAll('#main .bench-chart').length, svgs: document.querySelectorAll('#main .bench-chart svg').length, rows: document.querySelectorAll('#main .bench-all tbody tr').length, coverage: document.querySelector('#main .coverage').innerText, heads: [...document.querySelectorAll('#main .bench-chart .sect')].map(e => e.innerText.replace(/\\n/g, ' ')) })`);
    assert.equal(drawn.charts, Object.values(chartBench).filter(c => c.benchmark === bench).length, 'One section per chart of ' + bench);
    assert.ok(drawn.rows > 0, 'The all-subjects table has rows');
    await inspect(theme + ' benchmarks ' + bench); await shot(theme + '-benchmarks-picked');
    for (let i = 1; i < Math.min(drawn.charts, 4); i++) { await scrollTo(`#main .bench-chart:nth-of-type(${i + 1})`); await shot(theme + '-benchmarks-chart-' + (i + 1)); }
    await evaluate(`document.getElementById('main').scrollTop = 0`);
    if (drawn.svgs) {
      const hit = await evaluate(`(() => { const e = document.querySelector('#main .bench-chart .hit'); return e.getAttribute('aria-label'); })()`);
      const { x, y } = await centre('#main .bench-chart .hit'); await mouse(x, y);
      const tip = await tipShown(); assert.ok(tip.length > 0, 'The hovered point has a tip');
      await shot(theme + '-benchmarks-hover');
      await mouse(5, 5);
      await evaluate(`document.querySelectorAll('#main .bench-chart .hit')[1]?.focus() ?? document.querySelector('#main .bench-chart .hit').focus()`);
      const focused = await tipShown(); assert.ok(focused.length > 0, 'A focused point has a tip');
      await evaluate(`document.activeElement.blur()`);
      check(theme + ' Benchmarks ' + bench + ': ' + drawn.charts + ' charts (' + drawn.heads.join(' | ') + '); "' + drawn.coverage.replace(/\n/g, ' ') + '"; hovered "' + hit + '" and focused a point, each with a tip');
    } else check(theme + ' Benchmarks ' + bench + ': no chart drawn; "' + drawn.coverage.replace(/\n/g, ' ') + '"');
    // Sort by subject, then the other way.
    await press('#main .bench-all th button[data-key="sort-full"]'); await settled('sorted');
    const names = async () => evaluate(`[...document.querySelectorAll('#main .bench-all tbody td:nth-child(3)')].map(e => e.textContent)`);
    const up = await names(); assert.deepEqual(up, up.slice().sort((a, b) => a.localeCompare(b)), 'Sorted by subject');
    assert.equal(await evaluate(`document.querySelector('#main .bench-all th button[data-key="sort-full"]').getAttribute('aria-sort')`), 'ascending');
    await press('#main .bench-all th button[data-key="sort-full"]'); await settled('sorted back');
    assert.deepEqual(await names(), up.slice().reverse(), 'Sorted by subject, descending');
    await scrollTo('#main .bench-all'); await shot(theme + '-benchmarks-sorted');
    // A compare set of two, kept by the address.
    await press('#main .bench-all tbody tr:nth-child(1) input[type="checkbox"]'); await settled('compare one');
    await press('#main .bench-all tbody tr:nth-child(2) input[type="checkbox"]'); await settled('compare two');
    const cmp = await evaluate(`({ chips: document.querySelectorAll('#main .bench-cmp .cmp-chips .c').length, cols: document.querySelectorAll('#main .bench-cmp thead th').length, search: location.search })`);
    assert.equal(cmp.chips, 2); assert.equal(cmp.cols, 3); assert.match(cmp.search, /[?&]cmp=[^&,]+,[^&,]+/); assert.match(cmp.search, new RegExp('[?&]benchmark=' + bench));
    await scrollTo('#main .bench-cmp'); await inspect(theme + ' benchmarks compare'); await shot(theme + '-benchmarks-compare');
    // Open a subject in the drawer.
    await press('#main .bench-all tbody tr:nth-child(1) .linkish'); await drawerOpen();
    const opened = await evaluate(`({ title: document.querySelector('#aside h2').textContent, compare: !!document.querySelector('#aside .bench-acts'), hash: location.hash })`);
    assert.ok(opened.compare, 'The drawer offers Compare');
    await inspect(theme + ' benchmarks drawer'); await shot(theme + '-benchmarks-drawer');
    // The address alone gives the same compare set.
    const shared = origin + '/' + cmp.search + '#benchmarks';
    await send('Page.navigate', { url: shared }); await until(() => evaluate(`!!document.querySelector('#main .bench-cmp')`), 'the shared compare set');
    assert.equal(await evaluate(`document.querySelectorAll('#main .bench-cmp .cmp-chips .c').length`), 2);
    // The table view of the charts.
    await settled('shared'); if (drawn.svgs) { await press('#main .filters button[data-key="tables"]'); await settled('tables'); assert.ok(await evaluate(`document.querySelectorAll('#main table.pts').length > 0`)); await scrollTo('#main table.pts'); await shot(theme + '-benchmarks-tables'); await inspect(theme + ' benchmarks tables'); await press('#main .filters button[data-key="tables"]'); }
    check(theme + ' Benchmarks: table sorted both ways, a compare set of two (' + cmp.search + ') that the address restores, ' + opened.title + ' opened in the drawer (' + opened.hash + ')');

    // Train: open a run and a build request.
    await open(theme, 'train'); await settled('train');
    const train = await evaluate(`({ runs: document.querySelectorAll('#main .row.run').length, requests: document.querySelectorAll('#main .row.request').length, todo: document.querySelectorAll('#main .row.todo').length, envs: document.querySelectorAll('#main .row.env').length, text: document.getElementById('main').innerText })`);
    assert.equal(train.runs, Math.min(100, runs.length)); assert.equal(train.requests, requests.length);
    let trained = theme + ' Train: ' + train.todo + ' to build, ' + train.requests + ' build requests, ' + train.runs + ' runs, ' + train.envs + ' environments';
    if (runs.length) {
      const run = runs.find(r => r.state === 'failed') || runs[0];
      await press(`#main .row.run[data-run="${run.id}"]`); await drawerOpen();
      const shown = await evaluate(`({ blocks: [...document.querySelectorAll('#aside h3')].map(e => e.textContent), command: [...document.querySelectorAll('#aside .setup dt')].some(e => e.textContent === 'Command'), logs: [...document.querySelectorAll('#aside pre.evtext')].map(e => e.textContent.length) })`);
      assert.ok(shown.command, 'The run shows its command'); assert.ok(shown.blocks.some(b => b.startsWith('Standard error')), 'The run shows its logs');
      await inspect(theme + ' train run'); await shot(theme + '-train-run');
      trained += '; run ' + run.id.slice(0, 8) + ' (' + run.state + ') opened: ' + shown.blocks.join(', ');
    }
    if (requests.length) {
      await press('#main .row.request'); await drawerOpen();
      const req = await evaluate(`({ title: document.querySelector('#aside h2').textContent, buttons: [...document.querySelectorAll('#aside button')].map(b => b.textContent) })`);
      assert.ok(!req.buttons.some(t => /approve|decline|cancel/i.test(t)), 'No control that changes the project: ' + req.buttons.join(', '));
      await shot(theme + '-train-request');
      trained += '; request opened: ' + req.title;
    } else await shot(theme + '-train-empty');
    check(trained);

    // Data: open a dataset (one with files when there is one).
    await open(theme, 'data'); await settled('data');
    const withFiles = products.find(p => p.reference.startsWith('datasets/'));
    const pick = withFiles ? withFiles.reference : await evaluate(`document.querySelector('#main .ds-card').dataset.ref`);
    await press(`#main .ds-card[data-ref="${pick}"]`); await drawerOpen();
    const ds = await evaluate(`({ cards: document.querySelectorAll('#main .ds-card').length, blocks: [...document.querySelectorAll('#aside h3')].map(e => e.textContent), files: [...document.querySelectorAll('#aside .setup dd.mono')].map(e => e.textContent).filter(t => t.includes('/')).length })`);
    assert.deepEqual(ds.blocks.slice(0, 4), ['Description', 'Definition', 'Files', 'Used by']);
    if (withFiles) assert.ok(ds.files > 0, 'The dataset shows its files\' paths');
    await inspect(theme + ' data drawer'); await shot(theme + '-data-dataset');
    check(theme + ' Data: ' + ds.cards + ' cards; ' + pick + ' opened with ' + ds.files + ' paths');

    // Analysis: pick a metric; hover a case when there are values.
    await open(theme, 'analysis'); await settled('analysis');
    const metrics = await evaluate(`[...document.querySelectorAll('#main select[data-key="ana-metric"] option')].map(o => o.value)`);
    if (metrics.length > 1) await choose('#main select[data-key="ana-metric"]', metrics[1]);
    const ana = await evaluate(`({ marks: document.querySelectorAll('#main .cases .b').length, rows: document.querySelectorAll('#main table.cases-t tbody tr').length, none: document.querySelector('#main .ana-none')?.innerText || '' })`);
    if (ana.marks) {
      assert.equal(ana.marks, ana.rows);
      const { x, y } = await centre('#main .cases .hit'); await mouse(x, y); const tip = await tipShown();
      await inspect(theme + ' analysis'); await shot(theme + '-analysis-metric');
      check(theme + ' Analysis: metric ' + (metrics[1] || metrics[0]) + ', ' + ana.marks + ' cases, a hovered case reads "' + tip.replace(/\n/g, ' ') + '"');
    } else {
      assert.ok(ana.none.length > 0, 'Without per-case values a sentence says so');
      await inspect(theme + ' analysis'); await shot(theme + '-analysis-metric');
      check(theme + ' Analysis: no per-case values: "' + ana.none + '"');
    }
  }
}

(async () => {
  let folder;
  if (labRoot) folder = labRoot;
  else {
    fs.cpSync(path.join(root, 'tests', 'fixtures', 'tuldok_project', 'minimal'), path.join(temporary, 'fixture'), { recursive: true });
    folder = path.join(temporary, 'fixture', 'project');
    // One more model with no group, no kind of change, no training date and no result, to show each absence.
    fs.writeFileSync(path.join(folder, 'recipes', 'loose.json'), JSON.stringify({ format: 'tuldok_definition_v1', kind: 'recipe', title: 'A recipe with nothing set', description: 'Neither grouped, nor kinded, nor dated, nor measured.', earlier_work: { rebuild: 'no', reason: 'A browser check fixture.' }, model: 'models/stepper' }, null, 2) + '\n');
    // The buildable fixture's definitions and stand-in commands, beside the minimal fixture's (no name is shared).
    const buildable = path.join(root, 'tests', 'fixtures', 'tuldok_project', 'buildable');
    for (const kind of ['environments', 'datasets', 'recipes', 'benchmarks', 'charts']) for (const name of fs.readdirSync(path.join(buildable, 'project', kind))) fs.copyFileSync(path.join(buildable, 'project', kind, name), path.join(folder, kind, name));
    for (const name of fs.readdirSync(path.join(buildable, 'code'))) fs.cpSync(path.join(buildable, 'code', name), path.join(temporary, 'fixture', 'code', name), { recursive: true });
    const git = ['-c', 'user.name=Tuldok Test', '-c', 'user.email=test@example.invalid', '-c', 'commit.gpgsign=false', '-c', 'init.defaultBranch=main', '-C', path.join(temporary, 'fixture')];
    execFileSync('git', [...git, 'init', '-q']); execFileSync('git', [...git, 'add', '-A']); execFileSync('git', [...git, 'commit', '-q', '-m', 'The fixture.']);
  }
  const home = path.join(temporary, 'home'), catalog = path.join(temporary, 'catalog'); fs.mkdirSync(home);
  owned = [folder, catalog]; dropOwned(folder, catalog);
  if (!labRoot) {   // runs, products, a failed run, per-case values and a request awaiting approval, before Tuldok starts
    const cli = (...args) => execFileSync(python, ['-m', 'tuldok_project', ...args], { cwd: root, env: { ...process.env, TULDOK_PROJECT_HOME: home }, stdio: ['ignore', 'pipe', 'pipe'] }).toString();
    cli('connect', folder, 'test-python', python);
    cli('build', folder, 'datasets/numbers', 'recipes/fit-a', 'benchmarks/score', '--yes');
    try { cli('build', folder, 'recipes/fit-b', '--yes', '--env', 'BUILDABLE_FAIL=train'); assert.fail('The build of recipes/fit-b was to fail'); } catch (error) { if (error.code === 'ERR_ASSERTION') throw error; }
    cli('import-values', folder, ...fs.readdirSync(path.join(temporary, 'fixture', 'values')).map(name => path.join(temporary, 'fixture', 'values', name)));
    execFileSync(python, ['-c', `import sys
from tuldok_project import service
agent = {'actor_id': 'agent-browser-check', 'kind': 'agent', 'label': 'A browser check agent', 'scopes': ['inspect', 'execute']}
assert service.Service(sys.argv[1]).call('request_build', {'targets': ['recipes/fit-b']}, agent)['state'] == 'awaiting-approval'
`, folder], { cwd: root, env: { ...process.env, TULDOK_PROJECT_HOME: home }, stdio: ['ignore', 'pipe', 'pipe'] });
  }
  const before = labRoot ? null : snapshot(folder);
  let output = '';
  server = launch(python, ['-u', 'app.py', '--port', '0', '--data', catalog, '--project-folder', folder], { cwd: root, env: { ...process.env, TULDOK_PROJECT_HOME: home }, stdio: ['ignore', 'pipe', 'pipe'] });
  server.stdout.on('data', chunk => { output += chunk; }); server.stderr.on('data', chunk => { serverErrors += chunk; });
  const port = await until(() => { if (server.exitCode !== null) throw Error('Tuldok exited: ' + serverErrors); return output.match(/127\.0\.0\.1:(\d+)/)?.[1]; }, 'Tuldok start-up', 1800);
  origin = 'http://127.0.0.1:' + port;
  auth = authenticatedFixture(); await auth.register(origin, catalog, root);
  const map = await api('map'), summary = await api('summary'), activityBefore = (await api('activity')).total;
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
      assert.doesNotMatch(await evaluate(`document.getElementById('main').innerText`), /is not built yet/);
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
    check('Every tab in ' + theme + ' at ' + WIDTH + ' by ' + HEIGHT + ': no overflow, no empty main area');
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

  await otherTabs(map);
  const activity = await api('activity');
  assert.equal(activity.total, activityBefore, 'Nothing was asked of the project while the page was open: ' + JSON.stringify(activity.items));
  if (before) assert.deepEqual(snapshot(folder), before, 'The fixture copy is unchanged');
  assert.deepEqual(errors, [], 'Script errors'); assert.deepEqual(failedRequests, [], 'Failed requests');
  check('No script error, no failed request, nothing added to the activity log (' + activityBefore + ' entries from the set-up)' + (before ? ', the folder unchanged' : ''));
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
  try { execFileSync('chmod', ['-R', 'u+w', temporary]); } catch (_) { /* nothing was made read-only */ }   // finished runs leave their directories read-only
  fs.rmSync(temporary, { recursive: true, force: true });
});
