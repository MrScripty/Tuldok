'use strict';
// The shell of the project workspace (the mockup's b-map.html script): tabs,
// routing by hash (#<tab>/<selected>), the status strip and Needs you, the
// drawer, and when the project is read. The first screen reads summary and
// map; the strip's other sources are read right after; a tab reads what it
// needs when it is first shown. The page reads again in one way (reread(),
// spec-w4.md): on its timer (every two seconds while a build is queued or
// running, every fifteen otherwise), when the window regains focus and after
// a control's answer (actions.js), asking again for what it watches (summary,
// status, build requests, environments, runs, and the map except on the
// timer unless a run or request ended or status changed). When no answer
// differs nothing is drawn again; only the progress of a running run (the
// strip's and its row's in Train's list) and the minute of "Read at" are set
// in place. When one does, what is not watched is forgotten and the strip,
// the tab and the open drawer are drawn again in place, keeping the scroll
// and the focus, so a model turns to built without a reload. The open run
// reads on its progress and logs on every reading. A reading that fails
// leaves the page as it is and the strip says so; a read refused conflict
// shows the conflict panel.
(() => {
  const P = window.TuldokProject, S = window.LabScreens, A = window.LabActions;
  const TABS = [['map', 'Map'], ['data', 'Data'], ['annotate', 'Annotate'], ['train', 'Train'], ['sweeps', 'Sweeps'], ['benchmarks', 'Benchmarks'], ['compare', 'Compare'], ['analysis', 'Analysis'], ['overview', 'Overview']];
  const POLL_MS = 2000, IDLE_MS = 15000;   // how often the page asks again while something builds, and while nothing does
  const ACTIVE_RUN = ['queued', 'running'], ACTIVE_REQUEST = ['queued', 'running'];
  const $ = id => document.getElementById(id);
  const state = { screen: 'map', sel: {}, kinds: null, generations: null, query: '', zoom: 1, track: false, ui: {}, benchmark: null, cmp: [] };
  const data = { summary: null, map: null, standing: null, needs: null, status: null, readAt: '', polling: false };
  let failed = null, conflict = null, pollTimer = null, pollFast = false, states = null, opener = null;
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
    // The Map's Generation filter (spec-generations.md): as the kinds, '' for the models without one.
    toggleGeneration: (g, all) => { if (!state.generations) state.generations = new Set([g]); else if (state.generations.has(g)) { state.generations.delete(g); if (!state.generations.size) state.generations = null; } else { state.generations.add(g); if (state.generations.size === all.length) state.generations = null; } render(); },
    // The other tabs: their own settings (state.ui), and the benchmark and compare set, which the address keeps (?benchmark=, ?cmp=).
    setUI: (k, v) => { state.ui[k] = v; if (ADDRESSED.includes(k)) address(); render(); },
    /** Keeps a setting of the tab that a view has already drawn in place (fields.js's slider): into the address, and nothing drawn again. */
    keepUI: (k, v) => { state.ui[k] = v; if (ADDRESSED.includes(k)) address(); },
    // The compare set is the page's, of up to COMPARE_MOST models from any benchmark or the map (spec-t3 section 5.1): another benchmark keeps it.
    setBenchmark: name => { state.benchmark = name; address(); render(); },
    toggleCompare: id => { const i = state.cmp.indexOf(id); if (i >= 0) state.cmp.splice(i, 1); else if (state.cmp.length < COMPARE_MOST) state.cmp.push(id); address(); render(); },
    clearCompare: () => { state.cmp = []; address(); render(); },
    /** Reads everything again (a control's answer came, or a view asks for it). */
    refresh: () => changed(),
    /** Draws the map again from what is read (the page's drafts changed, editor.js); the drawer is kept. */
    redraw: async () => { try { data.map = await P.map(); } catch (error) { fail(error); } strip(); render(); },
    /** Draws the drawer afresh. */
    reopen: () => { $('aside')._for = null; render(); }
  };
  // The settings of the Analysis tab the address keeps, so that a reload opens it where it was (spec-d6 section 3).
  // And those of the Training block of a run's drawer (spec-t1 section 6): the runs compared, the series, smoothing, log scale, across.
  const ADDRESSED = ['anaBench', 'anaSubject', 'anaMetric', 'anaCase', 'anaAxis', 'anaIndex', 'anaMeanFree', 'trWith', 'trSeries', 'trSmooth', 'trLog', 'trX', 'cmpCase', 'cmpAxis', 'cmpIndex', 'cmpMeanFree', 'sweep'];   // sweep: the Sweeps tab's (spec-t7)
  const COMPARE_MOST = 4;
  /** Writes the benchmark, the compare set and the Analysis tab's settings into the address without reloading, so the view can be shared. */
  function address() {
    const q = new URLSearchParams(location.search);
    if (state.benchmark) q.set('benchmark', state.benchmark); else q.delete('benchmark');
    if (state.cmp.length) q.set('cmp', state.cmp.join(',')); else q.delete('cmp');
    for (const k of ADDRESSED) { const v = state.ui[k]; if (v === null || v === undefined || v === '' || v === false) q.delete(k); else q.set(k, String(v)); }
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
  // The strip is drawn by parts, each made again only when what it shows differs (spec-w4 R2): a reading
  // that changed nothing touches no element of it but the text of "Read at", when its minute changes.
  const parts = {};   // by name: { key, el }
  const part = (name, key, make) => { const p = parts[name]; if (p && p.key === key) return p.el; const el = make(); parts[name] = { key, el }; return el; };
  const span = (cls, text) => Object.assign(document.createElement('span'), { className: cls, textContent: text });
  const setText = (node, text) => { if (node.data !== text) node.data = text; };
  function hairline(p) {
    const hair = span('hair', ''), i = document.createElement('i'); i.style.width = Math.round(100 * p.completed / Math.max(1, p.total)) + '%'; hair.appendChild(i);
    hair.title = p.stage + ' ' + p.completed + ' of ' + p.total; hair.setAttribute('role', 'progressbar'); hair.setAttribute('aria-valuemin', '0'); hair.setAttribute('aria-valuemax', String(p.total)); hair.setAttribute('aria-valuenow', String(p.completed));
    return hair;
  }
  /** The Needs you button: made once, its words, state and aria-expanded set when they differ. */
  function needsButton() {
    if (!parts.needs) {
      const b = document.createElement('button'); b.className = 'btn sm needs-btn'; b.type = 'button'; b.id = 'needs-btn'; b.dataset.key = 'needs-btn'; b.setAttribute('aria-controls', 'needs-panel');
      b.addEventListener('click', () => { const panel = $('needs-panel'); panel.hidden = !panel.hidden; b.setAttribute('aria-expanded', String(!panel.hidden)); fillNeeds(true); });
      parts.needs = { key: null, el: b };
    }
    const b = parts.needs.el, text = 'Needs you · ' + (data.needs ? data.needs.length : '…'), open = String(!$('needs-panel').hidden);
    if (b.textContent !== text) b.textContent = text;
    if (b.disabled !== !data.needs) b.disabled = !data.needs;
    if (b.getAttribute('aria-expanded') !== open) b.setAttribute('aria-expanded', open);
    return b;
  }
  function strip() {
    const el = $('strip'), want = [];
    if (failed) { want.push(part('state', 'failed ' + !!conflict, () => S.stateEl('serious', conflict ? 'Conflict' : 'Not read'))); want.push(part('msg', 'failed ' + failed, () => span('msg', failed))); }
    else if (!data.standing) want.push(part('msg', 'reading', () => span('msg', 'Reading the project…')));
    else {
      const { tone, word, text } = data.standing, p = data.progress;
      want.push(part('state', tone + ' ' + word, () => S.stateEl(tone, word)));
      if (p) want.push(part('hair', [p.stage, p.completed, p.total].join(' '), () => hairline(p)));
      const m = part('msg', 'standing', () => { const s = span('msg', ''); s.append(document.createTextNode(''), document.createTextNode('')); return s; });
      setText(m.firstChild, text + (p ? ' ' + p.stage + ': ' + p.completed + ' of ' + p.total + '.' : ''));
      setText(m.lastChild, ' Read at ' + data.readAt + '.');
      want.push(m);
      const n = data.status ? data.status.unsaved.length + data.status.removed.length : 0, a = P.annotationsUnsaved(data.status);
      if (n || a) want.push(part('save', n + ' ' + a + ' ' + A.may('edit'), () => A.stripSave(data.status, $('strip-note'))));
      else if ($('strip-note').firstChild) $('strip-note').textContent = '';
      want.push(needsButton());
    }
    const now = [...el.children];
    if (now.length !== want.length || want.some((e, i) => now[i] !== e)) keepFocus(el, () => {
      want.forEach((e, i) => { if (el.children[i] !== e) el.insertBefore(e, el.children[i] || null); });
      while (el.children.length > want.length) el.lastElementChild.remove();
    });
    fillNeeds();
  }
  /** Places Needs you sends to: the panel closes and the focus goes to the drawer that opens. */
  function needsGo(screen, id) { const panel = $('needs-panel'); panel.hidden = true; const b = $('needs-btn'); if (b) b.setAttribute('aria-expanded', 'false'); opener = { key: 'needs-btn', el: null }; go(screen, id); }
  /** Needs you, when open: drawn again when what it lists (or who may use its controls) differs, or when it is opened (force). */
  function fillNeeds(force) {
    const panel = $('needs-panel'); if (panel.hidden || !data.needs) return;
    const key = JSON.stringify([data.needs.map(n => [n.kind, n.key || '', n.text, n.references || null]), (window.TuldokAuth && window.TuldokAuth.identity()) || null]);
    if (!force && panel._key === key) return;
    panel._key = key;
    keepFocus(panel, () => { panel.textContent = ''; panel.appendChild(S.needsList(data.needs, n => A.needControls(n, needsGo))); });
  }

  // ---- Rendering --------------------------------------------------------------
  /**
   * Draws the tab on screen. The tab bar is built once (start()); this sets
   * which link is current. The drawer is drawn again in place when app.js
   * marked it (aside._again: 'data' after a reading that changed something,
   * 'control' after a control's answer, which the editor and the branch form
   * take too); otherwise a drawer already showing its subject is left alone.
   */
  function render() {
    for (const a of $('tabs').children) { const on = a.dataset.tab === state.screen; if (on !== a.hasAttribute('aria-current')) { if (on) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); } }
    const main = $('main'), aside = $('aside'), drawer = $('drawer');
    const name = data.summary ? data.summary.name : '';
    document.title = TABS.find(t => t[0] === state.screen)[1] + (name ? ' · ' + name : '') + ' · Tuldok';
    if (failed || !data.map) {
      main.className = 'content'; main.textContent = ''; main._tree = null; main._view = null; main._painted = null;
      if (conflict) A.conflictPanel(main, conflict);
      else { const p = document.createElement('p'); p.className = failed ? 'failure' : 'note'; p.textContent = failed || 'Reading the project…'; main.appendChild(p); }
      drawer.classList.remove('open'); drawer.setAttribute('aria-hidden', 'true'); main.classList.remove('with-drawer'); aside.textContent = ''; aside._for = null; aside._again = false;
      return;
    }
    const wasMap = main.classList.contains('map'), view = state.screen + '/' + (state.screen === 'overview' && state.sel.overview === 'report' ? 'report' : '');   // a selection opens the drawer and keeps the place; the report is its own view
    main.className = state.screen === 'map' ? 'map' : 'content';
    if (state.screen !== 'map' && wasMap) main._tree = null;
    if (main._view !== view) { main.scrollTop = 0; main.scrollLeft = 0; main._view = view; }   // a new screen starts at its top
    const has = S[state.screen](main, aside, state, act, data);
    aside._again = false;
    drawer.classList.toggle('open', !!has); drawer.setAttribute('aria-hidden', String(!has)); main.classList.toggle('with-drawer', !!has);
    if (!has) aside._for = null;
  }
  function fail(error) { failed = error.message; conflict = error.code === 'conflict' ? error : null; }

  // ---- Reading ------------------------------------------------------------------
  const WATCH = P.WATCHED.filter(n => n !== 'map');   // asked again on every reading; the map too on some (step())
  async function first() {
    try {
      data.summary = await P.read('summary');
      $('projname').textContent = data.summary.name;
      if (window.LabEditor) window.LabEditor.load(data.summary.project_id);   // the drafts of this project, kept for this tab
      data.map = await P.map();
      data.standing = P.standing(data.map, null, null); data.readAt = clock(); failed = null; conflict = null;
    } catch (error) { fail(error); }
    strip(); render();
    if (failed) return;
    const read = await sources();
    if (read.error && read.error.code === 'conflict') { fail(read.error); strip(); render(); return; }
    ended(read); await stand(read);
    strip();
    if (state.screen === 'overview') render();   // it shows where the project stands and Needs you
  }
  /** The strip's other sources, as kept: status, build requests, environments and runs. */
  async function sources() {
    try { const [status, requests, environments, runs] = await Promise.all([P.read('status'), P.read('build_requests'), P.read('environments'), P.read('runs')]); return { status, requests: requests.requests, environments: environments.environments, runs: runs.runs }; }
    catch (error) { return { error }; }
  }
  /** Whether a run or a build request that was active is no more (or a run came and went) since the last reading. */
  function ended(read) {
    if (read.error) return false;
    const now = new Map(read.runs.map(r => ['run:' + r.id, r.state]).concat(read.requests.map(r => ['request:' + r.id, r.state])));
    let gone = false;
    if (states) for (const [key, st] of now) {
      const was = states.get(key);
      if (key.startsWith('run:') ? (was === undefined || ACTIVE_RUN.includes(was)) && !ACTIVE_RUN.includes(st) : ACTIVE_REQUEST.includes(was) && !ACTIVE_REQUEST.includes(st)) gone = true;
    }
    states = now;
    return gone;
  }
  /** Where the project stands, Needs you and the running run's progress, from the sources; asks again later (in two seconds while something builds). */
  async function stand(read) {
    try {
      if (read.error) throw read.error;
      data.status = read.status;
      data.standing = P.standing(data.map, read.runs, read.requests);
      data.needs = P.needs({ summary: data.summary, status: read.status, requests: read.requests, environments: read.environments, runs: read.runs, shaped: data.map });
      // The latest progress of each running run: the first is the strip's, all are set into Train's rows (tabs.js's S.progress).
      const running = read.runs.filter(r => r.state === 'running');
      data.progressOf = new Map(await Promise.all(running.map(r => P.call('progress', { run: r.id }).then(p => [r.id, p.event], () => [r.id, null]))));
      data.progress = running.length ? data.progressOf.get(running[0].id) : null;
      data.readAt = clock();
      later(read.runs.some(r => ACTIVE_RUN.includes(r.state)) || read.requests.some(r => ACTIVE_REQUEST.includes(r.state)));
    } catch (error) {
      unread(error);
    }
  }
  /** A reading that failed (not a conflict): what is on screen stays, the strip says the project was not read and why, and it is asked again later. */
  function unread(error) {
    data.progress = null; data.progressOf = new Map();
    data.standing = { tone: 'serious', word: 'Not read', text: P.standing(data.map, null, null).text + ' The last reading failed: ' + error.message.replace(/\.$/, '') + '.' };
    later(false);
  }
  /** What a reading sets in place in the main area whether or not anything changed: Overview's "Read at" and the progress of the running runs in Train's list. */
  function current() {
    const at = $('main').querySelector('[data-read-at]'), text = 'Read at ' + data.readAt;
    if (at && at.firstChild) setText(at.firstChild, text);
    if (S.progress && data.progressOf) S.progress(data.progressOf);
  }
  /** Asks again later: in two seconds while something builds, otherwise in fifteen, so a request an agent makes or an edit made elsewhere shows without the window losing and regaining focus. */
  function later(busy) {
    if (pollTimer && busy && !pollFast) { clearTimeout(pollTimer); pollTimer = null; }
    if (!pollTimer) { pollFast = busy; pollTimer = setTimeout(() => { pollTimer = null; reread('timer'); }, busy ? POLL_MS : IDLE_MS); }
  }
  /**
   * The one way of reading again (spec-w4 R1 to R3), for a cause: 'timer',
   * 'focus' (the window regained it, or a control was refused) or 'control'
   * (a control's answer, which always counts as a change). One reading at a
   * time: a cause arriving meanwhile waits, the strongest of those waiting kept.
   */
  const RANK = { timer: 0, focus: 1, control: 2 };
  let reading = null, waiting = null, owed = false;   // owed: a control was answered and the reading after it failed, so the next one counts as a change
  function reread(cause, info) {
    if (!reading) { reading = step(cause, info).catch(error => console.error(error)).finally(() => { reading = null; }); return reading; }
    if (!waiting) { const w = waiting = { cause, info }; w.done = reading.then(() => { waiting = null; return reread(w.cause, w.info); }); }
    else if (RANK[cause] > RANK[waiting.cause] || (cause === waiting.cause && info)) Object.assign(waiting, { cause, info });
    return waiting.done;
  }
  /**
   * One reading: asks again for what the page watches (the map too, except
   * on the timer unless a run or request ended or status changed). Nothing
   * changed: only the strip's parts that differ (the progress, the minute of
   * "Read at") and the same two in the main area are touched. A reading that
   * failed touches nothing but the strip, which says so. Something changed: what is not watched is
   * forgotten, and the strip, the tab and the open drawer are drawn again in
   * place (a drawer holding the editor or the branch form only after a
   * control). The open run reads on (tabs.js's S.tick).
   */
  async function step(cause, info) {
    if (failed) { if (cause === 'timer') return; P.forgetAll(); await first(); return settleFocus(info); }
    const control = cause === 'control';
    let changed;
    try {
      changed = await P.again(cause === 'timer' ? WATCH : P.WATCHED);
      if (changed.includes('map')) data.map = await P.map();
    } catch (error) { return notRead(error, control); }
    if (changed.includes('summary')) try { data.summary = await P.read('summary'); } catch (error) { /* the strip says what failed */ }
    const read = await sources();
    if (read.error && read.error.code === 'conflict') return notRead(read.error, control);
    if (cause === 'timer' && (ended(read) || changed.includes('status'))) {
      try { if ((await P.again(['map'])).length) { changed = changed.concat(['map']); data.map = await P.map(); } } catch (error) { return notRead(error, control); }
    } else if (cause !== 'timer') ended(read);
    await stand(read);
    const anything = control || owed || changed.length > 0; owed = false;
    if (anything) P.forgetBut(P.WATCHED);
    strip();
    if (anything) { $('aside')._again = control ? 'control' : 'data'; render(); } else current();
    if (S.tick) await S.tick();
    if (control) settleFocus(info);
  }
  /** A reading that could not be made: a conflict shows the conflict panel; anything else leaves the page as it is and says so in the strip. */
  function notRead(error, control) {
    if (error.code === 'conflict') { fail(error); strip(); render(); return; }
    if (control) owed = true;
    unread(error); strip();
  }
  /** After a control's answer: the focus stays on the control when it is still there, else goes to the drawer's heading. */
  function settleFocus(info) {
    if (info && info.focus && (!document.activeElement || document.activeElement === document.body)) {
      if (!A.focusKey(info.focus)) setTimeout(() => { if (document.activeElement === document.body) { const t = $('aside').querySelector('h2') || $('main'); if (t.tabIndex < 0 && t !== $('main')) t.tabIndex = -1; t.focus(); } }, 300);
    }
  }
  const changed = info => reread('control', info);
  A.connect({ changed, refused: () => reread('focus'), reread: () => reread('control') });

  function start() {
    // auth.js puts its session controls first in the body; they belong at the right of the top bar.
    const session = document.querySelector('body > .session-bar'); if (session) $('top-right').appendChild(session);
    S.theme.init($('theme'));
    $('close').appendChild(S.icon('x'));
    $('close').addEventListener('click', () => go(state.screen));
    window.addEventListener('keydown', e => {
      if (e.key !== 'Escape') return;
      if (A.escape()) return;
      if (window.LabEditor && window.LabEditor.escape()) return;
      if (!$('needs-panel').hidden) { $('needs-panel').hidden = true; const b = $('needs-btn'); if (b) { b.setAttribute('aria-expanded', 'false'); b.focus(); } return; }
      if ($('drawer').classList.contains('open') && state.sel[state.screen]) go(state.screen);
    });
    window.addEventListener('hashchange', () => { parse(); render(); });
    window.addEventListener('focus', () => { if (data.summary || failed) reread('focus'); });
    // Who may use a control comes from the session: draw the controls again when it changes.
    window.addEventListener('tuldok-session', () => { if (failed) reread('focus'); else { $('aside')._for = null; if (data.map) act.redraw(); else { strip(); render(); } } });
    { const q = new URLSearchParams(location.search); state.benchmark = q.get('benchmark') || null; state.cmp = (q.get('cmp') || '').split(',').filter(Boolean).slice(0, COMPARE_MOST); for (const k of ADDRESSED) if (q.get(k)) state.ui[k] = q.get(k); }
    // The tab bar, once (spec-w4 R5): render() sets which link is current.
    for (const [id, label] of TABS) { const a = document.createElement('a'); a.href = '#' + id; a.textContent = label; a.dataset.tab = id; $('tabs').appendChild(a); }
    parse(); strip(); render(); first();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true }); else start();
})();
