'use strict';
// The shell of the project workspace (the mockup's b-map.html script): tabs,
// routing by hash (#<tab>/<selected>), the status strip and Needs you, the
// drawer, and when the project is read. The first screen reads summary and
// map; the strip's other sources are read right after; a tab reads what it
// needs when it is first shown; everything is read again when the window
// regains focus, and while a build is queued or running the strip asks again
// every two seconds for what can change.
(() => {
  const P = window.TuldokProject, S = window.LabScreens;
  const TABS = [['map', 'Map'], ['data', 'Data'], ['train', 'Train'], ['benchmarks', 'Benchmarks'], ['analysis', 'Analysis'], ['overview', 'Overview']];
  const POLL_MS = 2000;
  const $ = id => document.getElementById(id);
  const state = { screen: 'map', sel: {}, kinds: null, query: '', zoom: 1, track: false, ui: {}, benchmark: null, cmp: [] };
  const data = { summary: null, map: null, standing: null, needs: null, readAt: '', polling: false };
  let failed = null, mapText = null, pollTimer = null;
  const clock = () => new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });

  function parse() {
    const hash = location.hash.replace(/^#/, ''), cut = hash.indexOf('/');
    const screen = cut < 0 ? hash : hash.slice(0, cut), id = cut < 0 ? '' : decodeURIComponent(hash.slice(cut + 1));
    state.screen = TABS.some(t => t[0] === screen) ? screen : 'map';
    if (id) state.sel[state.screen] = id; else delete state.sel[state.screen];
  }
  function go(screen, id) { const next = '#' + screen + (id ? '/' + encodeURIComponent(id) : ''); if (location.hash === next) { parse(); render(); } else location.hash = next; }
  const act = {
    go, select: id => go(state.screen, id || undefined),
    setQuery: q => { state.query = q; render(); },
    zoom: d => { state.zoom = Math.round(Math.min(1.6, Math.max(0.5, (state.zoom || 1) + d)) * 10) / 10; render(); },
    toggleKind: (k, all) => { if (!state.kinds) state.kinds = new Set([k]); else if (state.kinds.has(k)) { state.kinds.delete(k); if (!state.kinds.size) state.kinds = null; } else { state.kinds.add(k); if (state.kinds.size === all.length) state.kinds = null; } render(); },
    toggleTrack: () => { state.track = !state.track; render(); },
    // The other tabs: their own settings (state.ui), and the benchmark and compare set, which the address keeps (?benchmark=, ?cmp=).
    setUI: (k, v) => { state.ui[k] = v; render(); },
    setBenchmark: name => { state.benchmark = name; state.cmp = []; address(); render(); },
    toggleCompare: id => { const i = state.cmp.indexOf(id); if (i >= 0) state.cmp.splice(i, 1); else if (state.cmp.length < 3) state.cmp.push(id); address(); render(); },
    clearCompare: () => { state.cmp = []; address(); render(); }
  };
  /** Writes the benchmark and compare set into the address without reloading, so the view can be shared. */
  function address() {
    const q = new URLSearchParams(location.search);
    if (state.benchmark) q.set('benchmark', state.benchmark); else q.delete('benchmark');
    if (state.cmp.length) q.set('cmp', state.cmp.join(',')); else q.delete('cmp');
    const text = q.toString().replace(/%2C/g, ',').replace(/%2F/g, '/');   // references read as they are
    history.replaceState(null, '', location.pathname + (text ? '?' + text : '') + location.hash);
  }

  // ---- The status strip and Needs you ---------------------------------------
  function strip() {
    const el = $('strip'); el.textContent = '';
    if (failed) { el.appendChild(S.stateEl('serious', 'Not read')); el.appendChild(Object.assign(document.createElement('span'), { className: 'msg', textContent: failed })); return; }
    if (!data.standing) { el.appendChild(Object.assign(document.createElement('span'), { className: 'msg', textContent: 'Reading the project…' })); return; }
    el.appendChild(S.stateEl(data.standing.tone, data.standing.word));
    if (data.progress) { const hair = document.createElement('span'); hair.className = 'hair'; const i = document.createElement('i'); i.style.width = Math.round(100 * data.progress.completed / Math.max(1, data.progress.total)) + '%'; hair.appendChild(i); hair.title = data.progress.stage + ' ' + data.progress.completed + ' of ' + data.progress.total; el.appendChild(hair); }
    const m = document.createElement('span'); m.className = 'msg';
    m.textContent = data.standing.text + (data.progress ? ' ' + data.progress.stage + ': ' + data.progress.completed + ' of ' + data.progress.total + '.' : '') + ' Read at ' + data.readAt + '.';
    el.appendChild(m);
    const b = document.createElement('button'); b.className = 'btn sm needs-btn'; b.type = 'button'; b.id = 'needs-btn';
    b.textContent = 'Needs you · ' + (data.needs ? data.needs.length : '…'); b.disabled = !data.needs;
    const panel = $('needs-panel'); b.setAttribute('aria-expanded', String(!panel.hidden)); b.setAttribute('aria-controls', 'needs-panel');
    b.addEventListener('click', () => { panel.hidden = !panel.hidden; b.setAttribute('aria-expanded', String(!panel.hidden)); fillNeeds(); });
    el.appendChild(b);
    fillNeeds();
  }
  function fillNeeds() { const panel = $('needs-panel'); if (panel.hidden || !data.needs) return; panel.textContent = ''; panel.appendChild(S.needsList(data.needs)); }

  // ---- Rendering --------------------------------------------------------------
  function render() {
    const tabs = $('tabs'); tabs.textContent = '';
    for (const [id, label] of TABS) { const a = document.createElement('a'); a.href = '#' + id; a.textContent = label; if (id === state.screen) a.setAttribute('aria-current', 'page'); tabs.appendChild(a); }
    const main = $('main'), aside = $('aside'), drawer = $('drawer');
    const name = data.summary ? data.summary.name : '';
    document.title = TABS.find(t => t[0] === state.screen)[1] + (name ? ' · ' + name : '') + ' · Tuldok';
    if (failed || !data.map) {
      main.className = 'content'; main.textContent = ''; main._tree = null;
      const p = document.createElement('p'); p.className = failed ? 'failure' : 'note'; p.textContent = failed || 'Reading the project…'; main.appendChild(p);
      drawer.classList.remove('open'); drawer.setAttribute('aria-hidden', 'true'); main.classList.remove('with-drawer');
      return;
    }
    const wasMap = main.classList.contains('map'), view = state.screen + '/' + (state.screen === 'overview' ? state.sel.overview || '' : '');   // a selection elsewhere opens the drawer and keeps the place
    main.className = state.screen === 'map' ? 'map' : 'content';
    if (state.screen !== 'map' && wasMap) main._tree = null;
    if (main._view !== view) { main.scrollTop = 0; main.scrollLeft = 0; main._view = view; }   // a new screen starts at its top
    const has = S[state.screen](main, aside, state, act, data);
    drawer.classList.toggle('open', !!has); drawer.setAttribute('aria-hidden', String(!has)); main.classList.toggle('with-drawer', !!has);
    if (!has) aside._for = null;
  }

  // ---- Reading ------------------------------------------------------------------
  async function first() {
    try {
      data.summary = await P.read('summary');
      $('projname').textContent = data.summary.name;
      data.map = await P.map(); mapText = JSON.stringify(await P.read('map'));
      data.standing = P.standing(data.map, null, null); data.readAt = clock(); failed = null;
    } catch (error) { failed = error.message; }
    strip(); render();
    if (!failed) await standing();
  }
  /** The strip's other sources: status, build requests, environments and runs. */
  async function standing() {
    try {
      const [status, requests, environments, runs] = await Promise.all([P.read('status'), P.read('build_requests'), P.read('environments'), P.read('runs')]);
      data.standing = P.standing(data.map, runs.runs, requests.requests);
      data.needs = P.needs({ summary: data.summary, status, requests: requests.requests, environments: environments.environments, runs: runs.runs, shaped: data.map });
      const running = runs.runs.find(r => r.state === 'running');
      data.progress = running ? (await P.call('progress', { run: running.id })).event : null;
      data.readAt = clock();
      const busy = !!running || requests.requests.some(r => r.state === 'queued' || r.state === 'running');
      if (busy && !pollTimer) pollTimer = setTimeout(poll, POLL_MS);
    } catch (error) { data.needs = null; data.standing = Object.assign({}, data.standing, { text: data.standing.text + ' ' + error.message }); }
    strip();
    if (state.screen === 'overview' || state.screen === 'train') render();
  }
  async function poll() {
    pollTimer = null;
    P.forget(['summary', 'runs', 'build_requests']);
    try { data.summary = await P.read('summary'); } catch (error) { /* the strip says what failed below */ }
    await standing();
  }
  /** Everything again, when the window regains focus; the map is redrawn only when it changed. */
  async function again() {
    if (failed) { P.forget(['summary', 'map']); return first(); }
    P.forget(['summary', 'status', 'build_requests', 'environments', 'runs', 'map', 'activity', 'definitions', 'definition', 'recipe_results', 'products', 'note',
      'graph', 'results_overview', 'results', 'chart', 'values', 'build_request', 'run']);
    try {
      data.summary = await P.read('summary');
      const text = JSON.stringify(await P.read('map'));
      if (text !== mapText) { mapText = text; data.map = await P.map(); $('aside')._for = null; render(); }
      else if (state.screen !== 'map') render();
    } catch (error) { failed = error.message; render(); }
    await standing();
  }

  function start() {
    // auth.js puts its session controls first in the body; they belong at the right of the top bar.
    const session = document.querySelector('body > .session-bar'); if (session) $('top-right').appendChild(session);
    S.theme.init($('theme'));
    $('close').appendChild(S.icon('x'));
    $('close').addEventListener('click', () => go(state.screen));
    window.addEventListener('keydown', e => {
      if (e.key !== 'Escape') return;
      if (!$('needs-panel').hidden) { $('needs-panel').hidden = true; const b = $('needs-btn'); if (b) { b.setAttribute('aria-expanded', 'false'); b.focus(); } return; }
      if ($('drawer').classList.contains('open') && state.sel[state.screen]) go(state.screen);
    });
    window.addEventListener('hashchange', () => { parse(); render(); });
    window.addEventListener('focus', () => { if (data.summary || failed) again(); });
    window.addEventListener('tuldok-session', () => { if (failed) again(); });
    { const q = new URLSearchParams(location.search); state.benchmark = q.get('benchmark') || null; state.cmp = (q.get('cmp') || '').split(',').filter(Boolean).slice(0, 3); }
    parse(); strip(); render(); first();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true }); else start();
})();
