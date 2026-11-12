'use strict';
// The shell of the project workspace (the mockup's b-map.html script): tabs,
// routing by hash (#<tab>/<selected>), the status strip and Needs you, the
// drawer, and when the project is read. The first screen reads summary and
// map; the strip's other sources are read right after; a tab reads what it
// needs when it is first shown; everything is read again when the window
// regains focus and after a control's answer (actions.js). While a build is
// queued or running the strip asks again every two seconds for what can
// change, the open run reads on its progress and logs, and when a run ends
// the map and everything else is read again, so a model turns to built
// without a reload. A read refused conflict shows the conflict panel.
(() => {
  const P = window.TuldokProject, S = window.LabScreens, A = window.LabActions;
  const TABS = [['map', 'Map'], ['data', 'Data'], ['train', 'Train'], ['benchmarks', 'Benchmarks'], ['analysis', 'Analysis'], ['overview', 'Overview']];
  const POLL_MS = 2000;
  const ACTIVE_RUN = ['queued', 'running'], ACTIVE_REQUEST = ['queued', 'running'];
  const $ = id => document.getElementById(id);
  const state = { screen: 'map', sel: {}, kinds: null, query: '', zoom: 1, track: false, ui: {}, benchmark: null, cmp: [] };
  const data = { summary: null, map: null, standing: null, needs: null, status: null, readAt: '', polling: false };
  let failed = null, conflict = null, mapText = null, pollTimer = null, states = null, opener = null;
  const clock = () => new Date().toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });

  function parse() {
    const hash = location.hash.replace(/^#/, ''), cut = hash.indexOf('/');
    const screen = cut < 0 ? hash : hash.slice(0, cut), id = cut < 0 ? '' : decodeURIComponent(hash.slice(cut + 1));
    state.screen = TABS.some(t => t[0] === screen) ? screen : 'map';
    if (id) state.sel[state.screen] = id; else delete state.sel[state.screen];
  }
  function go(screen, id) {
    // What opened a drawer gets the focus back when it closes.
    if (id && !state.sel[screen]) opener = document.activeElement && document.activeElement.dataset ? { key: document.activeElement.dataset.key || null, el: document.activeElement } : null;
    const closing = !id && state.sel[screen];
    const next = '#' + screen + (id ? '/' + encodeURIComponent(id) : '');
    if (location.hash === next) { parse(); render(); } else location.hash = next;
    if (closing && opener) { const o = opener; opener = null; setTimeout(() => { if (o.el && o.el.isConnected) o.el.focus(); else if (o.key) A.focusKey(o.key); }, 0); }
  }
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
    clearCompare: () => { state.cmp = []; address(); render(); },
    /** Reads everything again (a control's answer came, or a view asks for it). */
    refresh: () => changed()
  };
  /** Writes the benchmark and compare set into the address without reloading, so the view can be shared. */
  function address() {
    const q = new URLSearchParams(location.search);
    if (state.benchmark) q.set('benchmark', state.benchmark); else q.delete('benchmark');
    if (state.cmp.length) q.set('cmp', state.cmp.join(',')); else q.delete('cmp');
    const text = q.toString().replace(/%2C/g, ',').replace(/%2F/g, '/');   // references read as they are
    history.replaceState(null, '', location.pathname + (text ? '?' + text : '') + location.hash);
  }

  /** Rebuilds container with build(), giving back the focused control (by data-key), its caret and the scroll. */
  function keepFocus(container, build) {
    const active = document.activeElement, key = active && container.contains(active) && active.dataset ? active.dataset.key : null;
    const caret = key && typeof active.selectionStart === 'number' ? active.selectionStart : null, top = container.scrollTop;
    build();
    container.scrollTop = top;
    if (key) { const again = [...container.querySelectorAll('[data-key]')].find(e => e.dataset.key === key); if (again) { again.focus({ preventScroll: true }); if (caret !== null && again.setSelectionRange) again.setSelectionRange(caret, caret); } }
  }

  // ---- The status strip and Needs you ---------------------------------------
  function strip() {
    const el = $('strip');
    keepFocus(el, () => {
      el.textContent = '';
      if (failed) { el.appendChild(S.stateEl('serious', conflict ? 'Conflict' : 'Not read')); el.appendChild(Object.assign(document.createElement('span'), { className: 'msg', textContent: failed })); return; }
      if (!data.standing) { el.appendChild(Object.assign(document.createElement('span'), { className: 'msg', textContent: 'Reading the project…' })); return; }
      el.appendChild(S.stateEl(data.standing.tone, data.standing.word));
      if (data.progress) { const hair = document.createElement('span'); hair.className = 'hair'; const i = document.createElement('i'); i.style.width = Math.round(100 * data.progress.completed / Math.max(1, data.progress.total)) + '%'; hair.appendChild(i); hair.title = data.progress.stage + ' ' + data.progress.completed + ' of ' + data.progress.total; hair.setAttribute('role', 'progressbar'); hair.setAttribute('aria-valuemin', '0'); hair.setAttribute('aria-valuemax', String(data.progress.total)); hair.setAttribute('aria-valuenow', String(data.progress.completed)); el.appendChild(hair); }
      const m = document.createElement('span'); m.className = 'msg';
      m.textContent = data.standing.text + (data.progress ? ' ' + data.progress.stage + ': ' + data.progress.completed + ' of ' + data.progress.total + '.' : '') + ' Read at ' + data.readAt + '.';
      el.appendChild(m);
      const save = data.status ? A.stripSave(data.status, $('strip-note')) : null;
      if (save) el.appendChild(save); else $('strip-note').textContent = '';
      const b = document.createElement('button'); b.className = 'btn sm needs-btn'; b.type = 'button'; b.id = 'needs-btn'; b.dataset.key = 'needs-btn';
      b.textContent = 'Needs you · ' + (data.needs ? data.needs.length : '…'); b.disabled = !data.needs;
      const panel = $('needs-panel'); b.setAttribute('aria-expanded', String(!panel.hidden)); b.setAttribute('aria-controls', 'needs-panel');
      b.addEventListener('click', () => { panel.hidden = !panel.hidden; b.setAttribute('aria-expanded', String(!panel.hidden)); fillNeeds(); });
      el.appendChild(b);
    });
    fillNeeds();
  }
  /** Places Needs you sends to: the panel closes and the focus goes to the drawer that opens. */
  function needsGo(screen, id) { const panel = $('needs-panel'); panel.hidden = true; const b = $('needs-btn'); if (b) b.setAttribute('aria-expanded', 'false'); opener = { key: 'needs-btn', el: null }; go(screen, id); }
  function fillNeeds() {
    const panel = $('needs-panel'); if (panel.hidden || !data.needs) return;
    keepFocus(panel, () => { panel.textContent = ''; panel.appendChild(S.needsList(data.needs, n => A.needControls(n, needsGo))); });
  }

  // ---- Rendering --------------------------------------------------------------
  function render() {
    const tabs = $('tabs'); tabs.textContent = '';
    for (const [id, label] of TABS) { const a = document.createElement('a'); a.href = '#' + id; a.textContent = label; if (id === state.screen) a.setAttribute('aria-current', 'page'); tabs.appendChild(a); }
    const main = $('main'), aside = $('aside'), drawer = $('drawer');
    const name = data.summary ? data.summary.name : '';
    document.title = TABS.find(t => t[0] === state.screen)[1] + (name ? ' · ' + name : '') + ' · Tuldok';
    if (failed || !data.map) {
      main.className = 'content'; main.textContent = ''; main._tree = null; main._view = null; main._painted = null;
      if (conflict) A.conflictPanel(main, conflict);
      else { const p = document.createElement('p'); p.className = failed ? 'failure' : 'note'; p.textContent = failed || 'Reading the project…'; main.appendChild(p); }
      drawer.classList.remove('open'); drawer.setAttribute('aria-hidden', 'true'); main.classList.remove('with-drawer'); aside.textContent = ''; aside._for = null;
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
  function fail(error) { failed = error.message; conflict = error.code === 'conflict' ? error : null; }

  // ---- Reading ------------------------------------------------------------------
  async function first() {
    try {
      data.summary = await P.read('summary');
      $('projname').textContent = data.summary.name;
      data.map = await P.map(); mapText = JSON.stringify(await P.read('map'));
      data.standing = P.standing(data.map, null, null); data.readAt = clock(); failed = null; conflict = null;
    } catch (error) { fail(error); }
    strip(); render();
    if (!failed) await standing();
  }
  /**
   * The strip's other sources: status, build requests, environments and runs.
   * Asks again in two seconds while a build is queued or running. Compares
   * the states of the runs and requests with the last reading: when a run
   * has ended everything is read again (the map too); when the open run or
   * request changed state, its drawer is drawn again.
   */
  async function standing() {
    let ended = false, moved = new Set(), lists = null;
    try {
      const [status, requests, environments, runs] = await Promise.all([P.read('status'), P.read('build_requests'), P.read('environments'), P.read('runs')]);
      lists = [runs.runs, requests.requests];
      data.status = status;
      data.standing = P.standing(data.map, runs.runs, requests.requests);
      data.needs = P.needs({ summary: data.summary, status, requests: requests.requests, environments: environments.environments, runs: runs.runs, shaped: data.map });
      const running = runs.runs.find(r => r.state === 'running');
      data.progress = running ? (await P.call('progress', { run: running.id })).event : null;
      data.readAt = clock();
      const now = new Map(runs.runs.map(r => ['run:' + r.id, r.state]).concat(requests.requests.map(r => ['request:' + r.id, r.state])));
      if (states) for (const [key, st] of now) {
        const was = states.get(key);
        if (was !== st) moved.add(key);
        // A run or a request that was active and is no more, or a run that came and went between two readings.
        if (key.startsWith('run:') ? (was === undefined || ACTIVE_RUN.includes(was)) && !ACTIVE_RUN.includes(st) : ACTIVE_REQUEST.includes(was) && !ACTIVE_REQUEST.includes(st)) ended = true;
      }
      states = now;
      const busy = runs.runs.some(r => ACTIVE_RUN.includes(r.state)) || requests.requests.some(r => ACTIVE_REQUEST.includes(r.state));
      if (busy && !pollTimer) pollTimer = setTimeout(poll, POLL_MS);
    } catch (error) {
      if (error.code === 'conflict') { fail(error); strip(); render(); return; }
      data.needs = null; data.standing = Object.assign({}, data.standing, { text: data.standing.text + ' ' + error.message });
    }
    const aside = $('aside');
    if (ended) {
      // A run ended: what it made changes the map, the lists and the drawers.
      for (const name of ['summary', 'map', 'definitions', 'definition', 'products', 'recipe_results', 'results_overview', 'results', 'values', 'chart', 'graph', 'activity', 'run', 'build_request', 'plan', 'estimates'])
        P.forget([name]);
      try {
        data.summary = await P.read('summary');
        const text = JSON.stringify(await P.read('map'));
        if (text !== mapText) { mapText = text; data.map = await P.map(); aside._for = null; if (lists) data.standing = P.standing(data.map, ...lists); }
      } catch (error) { fail(error); strip(); render(); return; }
    }
    let redraw = ended;
    if (aside._for && moved.has(aside._for)) { P.forget(['run', 'build_request']); aside._for = null; redraw = true; }
    strip();
    if (redraw || ['overview', 'train'].includes(state.screen)) render();
  }
  async function poll() {
    pollTimer = null;
    P.forget(['summary', 'runs', 'build_requests']);
    try { data.summary = await P.read('summary'); } catch (error) { /* the strip says what failed below */ }
    await standing();
    if (S.tick) await S.tick();
  }
  /** Everything again, when the window regains focus; the map is redrawn only when it changed. */
  async function again() {
    if (failed) { P.forgetAll(); return first(); }
    P.forgetAll();
    try {
      data.summary = await P.read('summary');
      const text = JSON.stringify(await P.read('map'));
      if (text !== mapText) { mapText = text; data.map = await P.map(); $('aside')._for = null; render(); }
      else if (state.screen !== 'map') render();
    } catch (error) { fail(error); strip(); render(); return; }
    await standing();
  }
  /** After a control's answer: forget everything, read again, draw the drawer afresh; the focus stays on the control when it is still there. */
  async function changed(info) {
    P.forgetAll();
    if (failed) { await first(); }
    else {
      try {
        data.summary = await P.read('summary');
        const text = JSON.stringify(await P.read('map'));
        if (text !== mapText) { mapText = text; data.map = await P.map(); }
      } catch (error) { fail(error); strip(); render(); return; }
      $('aside')._for = null; render();
      await standing();
    }
    if (info && info.focus && (!document.activeElement || document.activeElement === document.body)) {
      if (!A.focusKey(info.focus)) setTimeout(() => { if (document.activeElement === document.body) { const t = $('aside').querySelector('h2') || $('main'); if (t.tabIndex < 0 && t !== $('main')) t.tabIndex = -1; t.focus(); } }, 300);
    }
  }
  A.connect({ changed, refused: () => standing(), reread: () => changed() });

  function start() {
    // auth.js puts its session controls first in the body; they belong at the right of the top bar.
    const session = document.querySelector('body > .session-bar'); if (session) $('top-right').appendChild(session);
    S.theme.init($('theme'));
    $('close').appendChild(S.icon('x'));
    $('close').addEventListener('click', () => go(state.screen));
    window.addEventListener('keydown', e => {
      if (e.key !== 'Escape') return;
      if (A.escape()) return;
      if (!$('needs-panel').hidden) { $('needs-panel').hidden = true; const b = $('needs-btn'); if (b) { b.setAttribute('aria-expanded', 'false'); b.focus(); } return; }
      if ($('drawer').classList.contains('open') && state.sel[state.screen]) go(state.screen);
    });
    window.addEventListener('hashchange', () => { parse(); render(); });
    window.addEventListener('focus', () => { if (data.summary || failed) again(); });
    // Who may use a control comes from the session: draw the controls again when it changes.
    window.addEventListener('tuldok-session', () => { if (failed) again(); else { $('aside')._for = null; strip(); render(); } });
    { const q = new URLSearchParams(location.search); state.benchmark = q.get('benchmark') || null; state.cmp = (q.get('cmp') || '').split(',').filter(Boolean).slice(0, 3); }
    parse(); strip(); render(); first();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true }); else start();
})();
