'use strict';
// The Data, Train, Benchmarks and Analysis screens, from the mockup's
// screens.js, added to window.LabScreens. Each is a screen like the others
// (main, aside, state, act, data): it shows "Reading…" the first time, reads
// what it needs through window.TuldokProject, then builds its content off the
// page and puts it in place in one step, so a re-render (a sort, a filter, a
// reading that found something changed) keeps the scroll, inside tables too,
// and the focus; a drawer read again for its subject stays on screen until
// its new content replaces it whole (spec-w4.md). Data, Benchmarks and Analysis
// only read. Train draws the controls of spec-w3.md section 3.1 (actions.js):
// Plan build, a build request's Approve, Decline and Cancel, a run's Cancel
// run and Stop, an environment's Check again, Connect and Disconnect, and it
// shows a running run live; it lists first what is planned (the page's drafts
// and the models never built, spec-w3 section 3.2). Data's drawer has Edit;
// the editor itself is editor.js's. Rule: the chrome holds no project words; titles,
// metrics and text come from the project.
(() => {
  const S = window.LabScreens, P = window.TuldokProject, Tree = window.LabTree, C = window.LabCharts, h = C.h, A = window.LabActions;
  const { sect, cell, block, time, bytes, failure, modelState, graphFor, putInPlace, putDrawer, turn } = S.parts;
  const fmt = C.fmtSci;
  const STATISTICS = ['median', 'mean', 'p10', 'p90', 'min', 'max'];
  const plural = (n, one, many) => n.toLocaleString('en-GB') + ' ' + (n === 1 ? one : many || one + 's');
  const nameOfRef = ref => ref.slice(ref.indexOf('/') + 1);
  const seconds = s => s == null ? '' : s < 1 ? '<1 s' : s < 90 ? Math.round(s) + ' s' : s < 5400 ? Math.round(s / 60) + ' min' : (s / 3600).toFixed(1) + ' h';
  const button = (cls, text, onClick) => { const b = h('button', cls, text); b.type = 'button'; if (onClick) b.addEventListener('click', onClick); return b; };
  const better = m => m.better === 'higher' ? 'higher is better' : m.better === 'lower' ? 'lower is better' : 'no better direction';
  const units = m => m.units && m.units !== '1' ? ' (' + m.units + ')' : '';

  /**
   * The pixel width the main area gives its content, for charts drawn before
   * they are on the page: from the drawer's class, not the padding, which may
   * be mid-transition.
   */
  function contentWidth(main) { const left = parseFloat(getComputedStyle(main).paddingLeft) || 20; return Math.max(360, main.clientWidth - left - (main.classList.contains('with-drawer') ? Math.min(420, 0.92 * innerWidth) + 20 : left)); }

  /**
   * Fills main from load() (a promise of what build reads): "Reading…" only
   * when this view has not been painted, the content built off the page and
   * put in place in one step when it is still the newest render of the same
   * view, keeping what spec-w4 R4 lists (screens.js's putInPlace): the scroll
   * of main and of every scrolled element in it, and the focused control (by
   * data-key) with its caret.
   */
  function paint(main, load, build) {
    const view = main._view, mine = main._paint = (main._paint || 0) + 1;
    if (main._painted !== view) { main.textContent = ''; main.appendChild(h('p', 'note', 'Reading…')); }
    main.setAttribute('aria-busy', 'true');
    const done = () => { if (main._paint === mine) main.removeAttribute('aria-busy'); };
    load().then(value => {
      done(); if (main._paint !== mine || main._view !== view) return;
      const width = contentWidth(main), frag = document.createDocumentFragment();
      try { build(frag, value, width); } catch (error) { frag.textContent = ''; failure(frag, error); console.error(error); }
      swap(main, frag); main._painted = view;
    }, error => {
      done(); if (main._paint !== mine || main._view !== view) return;
      const frag = document.createDocumentFragment(); failure(frag, error); swap(main, frag); main._painted = view;
    });
  }
  const swap = (main, frag) => putInPlace(main, frag);
  /**
   * Fills the drawer from load() for the subject id; build(ins, value). Once
   * per id; read again for the subject on screen (app.js marks the drawer
   * with _again after a change), what is on screen stays until the new
   * content is built off the page, then is replaced in one step with the
   * drawer's scroll kept. "Reading…" only for a subject not on screen yet.
   */
  function drawer(aside, id, load, build) {
    if (aside._for === id && !aside._again) return;
    const same = aside._for === id && !!aside.firstChild, mine = turn(aside);
    aside._for = id;
    if (!same) { aside.textContent = ''; aside.appendChild(h('p', 'note', 'Reading…')); }
    const live = () => aside._turn === mine && aside._for === id;
    load().then(value => { if (!live()) return; const ins = h('div', 'inspector'); try { build(ins, value); } catch (error) { failure(ins, error); } putDrawer(aside, ins); },
      error => { if (!live()) return; const frag = document.createDocumentFragment(); failure(frag, error); putDrawer(aside, frag); });
  }
  const closeDrawer = aside => { aside.textContent = ''; aside._for = null; return false; };
  const setup = () => { const dl = h('dl', 'setup'); return { dl, put(k, v, cls) { dl.appendChild(h('dt', null, k)); const dd = h('dd', cls || null); if (typeof v === 'string') dd.textContent = v; else if (v) dd.appendChild(v); dl.appendChild(dd); } }; };
  const searchBox = (state, act, placeholder) => { const q = h('input'); q.type = 'search'; q.placeholder = placeholder; q.value = state.query || ''; q.dataset.key = 'search'; q.setAttribute('aria-label', placeholder); q.addEventListener('input', () => act.setQuery(q.value)); return q; };
  function kindChips(state, act, present) {
    const kinds = P.KINDS.map(k => k.id).concat(present.includes(P.UNSET) ? [P.UNSET] : []);
    const grp = h('div', 'grp'); grp.setAttribute('role', 'group'); grp.setAttribute('aria-label', 'Kind of change');
    for (const k of kinds) { const b = button('btn sm chip ' + k, P.kindLabel(k), () => act.toggleKind(k, kinds)); b.dataset.kind = k; b.dataset.key = 'kind-' + k; b.setAttribute('aria-pressed', String(!state.kinds || state.kinds.has(k))); grp.appendChild(b); }
    return grp;
  }
  const toggle = (label, on, onClick, key) => { const b = button('btn sm', label, onClick); b.dataset.key = key; b.setAttribute('aria-pressed', String(!!on)); return b; };
  const select = (label, options, value, onChange, key) => {
    const s = h('select'); s.setAttribute('aria-label', label); s.dataset.key = key;
    for (const [v, t] of options) { const o = h('option', null, t); o.value = v; o.selected = v === value; s.appendChild(o); }
    s.addEventListener('change', () => onChange(s.value)); return s;
  };
  const wrapTable = t => { const d = h('div', 'tv-wrap'); d.appendChild(t); return d; };
  function headRow(cols) { const thead = h('thead'), tr = h('tr'); for (const [t, cls] of cols) tr.appendChild(h('th', cls || null, t)); thead.appendChild(tr); return thead; }

  // ---- Benchmarks: what is read --------------------------------------------
  async function allResults(name) {
    const rows = []; let offset = 0;
    for (;;) { const page = await P.read('results', { benchmark: name, group: '', offset, limit: 2000 }); rows.push(...page.rows); offset += page.rows.length; if (!page.rows.length || offset >= page.total) return rows; }
  }
  /** Each chart definition's benchmark and form, read once. */
  async function chartIndex() {
    const defs = (await P.read('definitions', { kind: 'chart' })).definitions.filter(d => !d.removed);
    return Promise.all(defs.map(async d => { const full = await P.read('definition', { reference: d.reference }); const doc = full.document || {}; return { reference: d.reference, title: d.title, benchmark: typeof doc.benchmark === 'string' ? nameOfRef(doc.benchmark) : null, form: doc.form }; }));
  }
  async function benchmarkList() {
    const [overview, defs] = await Promise.all([P.read('results_overview'), P.read('definitions', { kind: 'benchmark' })]);
    const titles = new Map(defs.definitions.map(d => [nameOfRef(d.reference), d]));
    return overview.benchmarks.map(b => ({ ...b, title: titles.has(b.benchmark) ? titles.get(b.benchmark).title : b.benchmark, state: titles.has(b.benchmark) ? titles.get(b.benchmark).state : null }));
  }
  const pickBenchmark = (list, wanted) => (list.find(b => b.benchmark === wanted) || list.find(b => b.subjects_with_results > 0) || list[0] || null);
  /**
   * One benchmark as the tab shows it: its metrics, its subjects (each with
   * the model of its recipe from the map, its values per metric for every
   * statistic, and whether its summaries come from per-case values held
   * here), and its charts' data.
   */
  async function benchmarkView(name, mapShaped) {
    const [def, rows, charts] = await Promise.all([P.read('definition', { reference: 'benchmarks/' + name }), allResults(name), chartIndex()]);
    const doc = def.document || {}, metrics = (doc.metrics || []).map(m => ({ id: m.id, title: m.title || m.id, units: m.units, better: m.better || 'none' }));
    const subjects = (doc.subjects || []).map(s => {
      const model = s.recipe && mapShaped.byId.get(s.recipe) || null;
      return { name: s.name, title: s.title || s.name, recipe: s.recipe || null, model, key: model ? model.id : 'subject:' + s.name,
        short: model ? Tree.refName(model) : s.name, full: model ? Tree.nameOf(model) : s.title || s.name, kind: model ? model.kind : 'other',
        group: model ? model.groupTitle || '' : '', values: {}, count: null, perCase: false };
    });
    const byName = new Map(subjects.map(s => [s.name, s]));
    for (const r of rows) { const s = byName.get(r.subject); if (!s) continue; s.values[r.metric] = r; s.count = Math.max(s.count || 0, r.count); if (r.origin === 'values') s.perCase = true; }
    const ORDER = ['tradeoff', 'progression', 'ranking', 'comparison'];   // the mockup leads with accuracy against time
    const mine = charts.filter(c => c.benchmark === name).sort((a, b) => ORDER.indexOf(a.form) - ORDER.indexOf(b.form) || a.title.localeCompare(b.title));
    const data = await Promise.all(mine.map(c => P.read('chart', { chart: c.reference }).then(r => ({ ...c, data: r.data }), error => ({ ...c, error }))));
    return { name, title: def.title, description: doc.description || '', metrics, subjects, byName, byKey: new Map(subjects.map(s => [s.key, s])), charts: data, cases: doc.cases || null };
  }
  const valueOf = (s, metric, stat) => { const r = s.values[metric]; return r && r.count > 0 && r[stat] != null ? r[stat] : null; };
  const visibleSubject = (state) => s => (!state.kinds || state.kinds.has(s.kind)) && (!state.query || [s.full, s.name, s.title, s.recipe].some(t => t && t.toLowerCase().includes(state.query.toLowerCase())));

  // ---- Benchmarks: the screen -------------------------------------------------
  function benchmarks(main, aside, state, act, data) {
    const sel = state.sel.benchmarks || null, ui = state.ui;
    paint(main, async () => { const list = await benchmarkList(); const b = pickBenchmark(list, state.benchmark); return { list, view: b ? await benchmarkView(b.benchmark, data.map) : null, picked: b }; }, (frag, { list, view, picked }, width) => {
      if (!view) { frag.appendChild(h('p', 'empty', 'This project defines no benchmark.')); return; }
      const stat = STATISTICS.includes(ui.stat) ? ui.stat : 'median', cmp = state.cmp.filter(k => view.byKey.has(k));
      const bar = h('div', 'filters');
      bar.appendChild(select('Benchmark', list.map(b => [b.benchmark, b.title + ' · ' + plural(b.subjects_with_results, 'subject') + ' with results']), view.name, v => act.setBenchmark(v), 'benchmark'));
      bar.appendChild(kindChips(state, act, view.subjects.map(s => s.kind)));
      bar.appendChild(select('Statistic', STATISTICS.map(s => [s, s.charAt(0).toUpperCase() + s.slice(1)]), stat, v => act.setUI('stat', v), 'stat'));
      if (view.charts.some(c => c.form === 'tradeoff')) bar.appendChild(toggle('Frontier only', ui.frontierOnly, () => act.setUI('frontierOnly', !ui.frontierOnly), 'frontier'));
      bar.appendChild(toggle('With results only', ui.resultsOnly, () => act.setUI('resultsOnly', !ui.resultsOnly), 'results-only'));
      bar.appendChild(toggle('Table view', ui.chartTables, () => act.setUI('chartTables', !ui.chartTables), 'tables'));
      bar.appendChild(searchBox(state, act, 'Find a subject'));
      frag.appendChild(bar);
      // Coverage: how many subjects have a result here, so the smaller plotted counts are explained.
      const every = view.subjects.filter(s => view.metrics.length && view.metrics.every(m => valueOf(s, m.id, stat) != null)).length;
      const some = view.subjects.filter(s => view.metrics.some(m => valueOf(s, m.id, stat) != null)).length - every;
      const none = view.subjects.length - every - some, perCase = view.subjects.filter(s => s.perCase).length;
      const cov = h('div', 'coverage'); const add = (n, t) => { const sp = h('span'); sp.appendChild(h('b', null, n.toLocaleString('en-GB'))); sp.appendChild(document.createTextNode(' ' + t)); cov.appendChild(sp); };
      add(view.subjects.length, view.subjects.length === 1 ? 'subject' : 'subjects'); if (every) add(every, view.metrics.length === 1 ? 'with a result' : 'with every metric'); if (some) add(some, 'with some metrics'); if (none) add(none, 'with no result'); add(perCase, 'with per-case values on this machine');
      frag.appendChild(cov);
      if (picked.differs_from_file) frag.appendChild(h('p', 'small muted bench-note', 'The results held here differ from the results file of this benchmark.'));
      const show = visibleSubject(state), select_ = key => act.select(key === sel ? null : key);
      // Charts, by their form.
      if (!view.charts.length) frag.appendChild(h('p', 'empty bench-note', 'No chart is defined for this benchmark; every value is in the table below.'));
      for (const c of view.charts) frag.appendChild(chartSection(c, view, { width, sel, onSelect: select_, show, frontierOnly: !!ui.frontierOnly, tables: !!ui.chartTables }));
      // The compare set.
      if (cmp.length) frag.appendChild(compareSection(view, cmp, stat, act));
      // Every subject.
      frag.appendChild(subjectTable(view, state, act, stat, sel, cmp));
    });
    if (!sel) return closeDrawer(aside);
    benchmarkDrawer(aside, sel, state, act, data);
    return true;
  }
  /** The drawer of a selected subject: the model's drawer when it is made from a recipe of the map, with Compare. */
  function benchmarkDrawer(aside, sel, state, act, data) {
    const isModel = data.map.byId.has(sel);
    if (isModel) S.inspectorModel(aside, sel, act, data, ins => compareActs(ins, sel, state, act, true));
    else if (aside._for !== sel || aside._again) {
      const name = sel.startsWith('subject:') ? sel.slice('subject:'.length) : sel;
      drawer(aside, sel, async () => { const list = await benchmarkList(); const b = pickBenchmark(list, state.benchmark); return b ? benchmarkView(b.benchmark, data.map) : null; }, (ins, view) => {
        const s = view && view.byName.get(name);
        const hd = h('header'); hd.appendChild(h('span', 'kicker', 'benchmark subject · ' + name)); hd.appendChild(h('h2', null, s ? s.title : name)); ins.appendChild(hd);
        if (!s) { ins.appendChild(h('p', 'empty', 'This benchmark has no subject ' + name + '.')); return; }
        ins.appendChild(h('p', 'note', s.recipe ? 'Made from ' + s.recipe + ', which is not on the map.' : 'Not made from a recipe of this project.'));
        const dl = h('dl', 'metrics'); for (const m of view.metrics) dl.appendChild(cell(m.title, fmt(valueOf(s, m.id, 'median')), m.units && m.units !== '1' ? m.units : '')); ins.appendChild(dl);
        ins.appendChild(h('p', 'note', 'Medians over ' + (s.count == null ? 'no cases' : plural(s.count, 'case')) + ' of ' + view.title + '.'));
        compareActs(ins, sel, state, act, false);
      });
    }
    const ins = aside.querySelector('.inspector'); if (ins) compareActs(ins, sel, state, act, isModel);
  }
  /** Compare, kept current on every render (a drawer is built once per selection). */
  function compareActs(ins, sel, state, act, isModel) {
    const old = ins.querySelector('.bench-acts'); if (old) old.remove();
    const acts = h('div', 'actions bench-acts'), on = state.cmp.includes(sel);
    const b = button('btn', on ? 'Remove from compare' : 'Compare', () => act.toggleCompare(sel)); b.disabled = !on && state.cmp.length >= 3; acts.appendChild(b);
    if (isModel) acts.appendChild(button('btn ghost', 'On the map', () => act.go('map', sel)));
    const head = ins.querySelector('header'); head.after(acts);
  }

  /** One chart: its heading and population in words, the drawing by form (a panel per group value), and its table when asked. */
  function chartSection(c, view, o) {
    const sec = h('section', 'bench-chart'); sec.dataset.chart = c.reference;
    if (c.error) { sec.appendChild(sect(c.title)); failure(sec, c.error); return sec; }
    const d = c.data, series = d.series || [];
    const plotted = d.form === 'comparison' ? new Set(d.rows.map(r => r.subject)).size : new Set(series.flatMap(s => s.points.map(p => p.subject))).size;
    const words = [plotted + ' of ' + plural(d.subject_count, 'subject') + ' drawn', d.statistic + ' over each subject\'s cases'];
    if (d.form === 'tradeoff') words.push(series.reduce((n, s) => n + s.points.filter(p => p.frontier).length, 0) + ' on the frontier');
    if (d.missing.length) words.push(d.missing.length + ' without a value not drawn');
    sec.appendChild(sect(c.title, words.join(' · ')));
    if (d.description) sec.appendChild(h('p', 'small muted bench-desc', d.description));
    const subjectOf = p => view.byName.get(p.subject);
    const point = p => { const s = subjectOf(p); return { id: s ? s.key : 'subject:' + p.subject, name: s ? s.full : p.title, short: s ? s.short : p.subject, kind: s ? s.kind : 'other', dim: s ? !o.show(s) : false }; };
    const tipRows = (p, extra) => () => { const s = subjectOf(p); return [{ b: s ? s.full : p.title }, { v: fmt(p.value), l: d.metric.title + units(d.metric) }].concat(extra || []).concat([{ v: s && s.model ? P.kindLabel(s.kind) : 'not a model of the map', l: (p.count != null ? '· ' + plural(p.count, 'case') : '') }]); };
    const panels = series.length > 1 || d.group;
    if (d.form === 'comparison') { sec.appendChild(comparisonTable(d, view, o)); return sec; }
    if (!series.some(s => s.points.length)) { sec.appendChild(h('p', 'empty', 'No subject has a value for this chart yet.')); return sec; }
    for (const s of series) {
      const host = h('div'); host.dataset.series = s.group;
      if (panels) sec.appendChild(h('h3', 'panel', d.group + ' = ' + s.group));
      if (!s.points.length) { sec.appendChild(h('p', 'empty', 'No subject has a value here.')); continue; }
      sec.appendChild(host);
      if (d.form === 'tradeoff') {
        const pts = s.points.map(p => ({ ...point(p), x: p.x, y: p.value, frontier: p.frontier, rows: tipRows(p, [{ v: fmt(p.x), l: d.metric_x.title + units(d.metric_x) }, { l: p.frontier ? 'on the frontier' : '' }]) }));
        C.scatter(host, pts, { width: o.width, height: 340, xTitle: d.metric_x.title + units(d.metric_x), yTitle: d.metric.title + units(d.metric), xName: d.metric_x.title, yName: d.metric.title, xBetter: d.metric_x.better, yBetter: d.metric.better, selected: o.sel, onSelect: o.onSelect, dimOff: o.frontierOnly });
        host.appendChild(legend(pts, 'Line: the frontier, where no other subject is at least as good on both and better on one'));
      } else if (d.form === 'progression') {
        const pts = s.points.map(p => ({ ...point(p), y: p.value, best: p.best_so_far, rows: tipRows(p, [{ v: fmt(p.best_so_far), l: 'best so far' }, { l: p.trained_at ? 'trained ' + P.day(p.trained_at) : 'no training date' }]) }));
        C.progression(host, pts, { width: o.width, height: 240, yTitle: d.metric.title + units(d.metric), selected: o.sel, onSelect: o.onSelect });
        host.appendChild(legend(pts, 'Step line: the best so far, ' + better(d.metric)));
      } else {
        const pts = s.points.map(p => ({ ...point(p), y: p.value, rows: tipRows(p) }));
        C.ranking(host, pts, { width: o.width, yTitle: d.metric.title + units(d.metric), selected: o.sel, onSelect: o.onSelect });
        host.appendChild(legend(pts, 'Best first, ' + better(d.metric)));
      }
      if (o.tables) sec.appendChild(pointsTable(d, s));
    }
    return sec;
  }
  function legend(points, line) {
    const ul = h('ul', 'legend'), kinds = new Set(points.map(p => p.kind));
    for (const k of P.KINDS.map(x => x.id).concat([P.UNSET, 'other'])) if (kinds.has(k)) ul.appendChild(h('li', 'chip ' + k, k === 'other' ? 'Not a model of the map' : P.kindLabel(k)));
    ul.appendChild(h('li', null, line)); return ul;
  }
  /** The table view of one chart panel: every drawn value as text. */
  function pointsTable(d, s) {
    const cols = [['Subject'], [d.metric.title + units(d.metric), 'n']];
    if (d.form === 'tradeoff') cols.push([d.metric_x.title + units(d.metric_x), 'n'], ['Frontier']);
    if (d.form === 'progression') cols.push(['Best so far', 'n'], ['Trained']);
    cols.push(['Cases', 'n']);
    const t = h('table', 'tv pts'); t.setAttribute('aria-label', d.title + (s.group ? ', ' + d.group + ' = ' + s.group : '') + ', as a table'); t.appendChild(headRow(cols));
    const tb = h('tbody');
    for (const p of s.points) {
      const tr = h('tr'); tr.appendChild(h('td', null, p.title)); tr.appendChild(h('td', 'n', fmt(p.value)));
      if (d.form === 'tradeoff') { tr.appendChild(h('td', 'n', fmt(p.x))); tr.appendChild(h('td', null, p.frontier ? 'yes' : '')); }
      if (d.form === 'progression') { tr.appendChild(h('td', 'n', fmt(p.best_so_far))); tr.appendChild(h('td', 'small faint nowrap', p.trained_at ? P.day(p.trained_at) : '—')); }
      tr.appendChild(h('td', 'n', String(p.count))); tb.appendChild(tr);
    }
    t.appendChild(tb); return wrapTable(t);
  }
  /** A comparison chart: every metric per subject, the best of each column marked. */
  function comparisonTable(d, view, o) {
    if (!d.rows.length) return h('p', 'empty', 'No subject has a value for this chart yet.');
    const best = {};
    for (const m of d.metrics) { const xs = d.rows.map(r => r.values[m.id]).filter(v => v != null); if (xs.length && m.better !== 'none') best[m.id] = m.better === 'higher' ? Math.max(...xs) : Math.min(...xs); }
    const cols = [['Subject']].concat(d.group ? [[d.group]] : []).concat(d.metrics.map(m => [m.title + units(m), 'n']));
    const t = h('table', 'tv cmpgrid'); t.appendChild(headRow(cols)); const tb = h('tbody');
    for (const r of d.rows) {
      const s = view.byName.get(r.subject), key = s ? s.key : 'subject:' + r.subject;
      const tr = h('tr', 'rowbtn' + (key === o.sel ? ' is-sel' : '')); tr.tabIndex = 0; tr.dataset.key = 'cmpgrid-' + key + '-' + r.group;
      tr.addEventListener('click', () => o.onSelect(key)); tr.addEventListener('keydown', e => { if (e.key === 'Enter') o.onSelect(key); });
      tr.appendChild(h('td', null, s ? s.full : r.title)); if (d.group) tr.appendChild(h('td', 'small faint', r.group));
      for (const m of d.metrics) { const v = r.values[m.id], td = h('td', 'n' + (v != null && v === best[m.id] ? ' best' : ''), fmt(v)); if (v != null && v === best[m.id]) td.title = 'Best of the column, ' + better(m); tr.appendChild(td); }
      tb.appendChild(tr);
    }
    t.appendChild(tb); const w = wrapTable(t);
    const foot = h('p', 'small faint bench-desc', 'Marked: the best value of each column.'); const box = h('div'); box.appendChild(w); box.appendChild(foot); return box;
  }
  /** Up to three subjects side by side: every metric, with the change from the first. */
  function compareSection(view, cmp, stat, act) {
    const sec = h('section', 'bench-cmp'); sec.appendChild(sect('Compare', cmp.length + ' of 3'));
    const list = cmp.map(k => view.byKey.get(k));
    const chips = h('div', 'cmp-chips');
    list.forEach((s, i) => { const c = h('span', 'c s' + (i + 1)); c.appendChild(h('i')); c.appendChild(document.createTextNode(s.full)); const x = button(null, '×', () => act.toggleCompare(s.key)); x.setAttribute('aria-label', 'Remove ' + s.full); c.appendChild(x); chips.appendChild(c); });
    chips.appendChild(button('btn sm ghost', 'Clear', () => act.clearCompare())); sec.appendChild(chips);
    const t = h('table', 'tv cmpt'); t.appendChild(headRow([['']].concat(list.map(s => [s.full, 'n'])))); const tb = h('tbody'), base = list[0];
    for (const m of view.metrics) {
      const tr = h('tr'); tr.appendChild(h('td', null, m.title + units(m) + ' · ' + stat));
      list.forEach((s, i) => {
        const v = valueOf(s, m.id, stat), td = h('td', 'n', fmt(v)), b0 = valueOf(base, m.id, stat);
        if (i > 0 && v != null && b0 != null && b0 !== 0) { const d = (v - b0) / Math.abs(b0), good = m.better === 'higher' ? d > 0 : m.better === 'lower' ? d < 0 : null; td.appendChild(h('span', 'd' + (d === 0 || good === null ? '' : good ? ' better' : ' worse'), ' ' + (d > 0 ? '+' : '') + (Math.abs(d) >= 10 ? (d * 100).toFixed(0) : (d * 100).toFixed(1)) + '%')); }
        tr.appendChild(td);
      });
      tb.appendChild(tr);
    }
    const cr = h('tr'); cr.appendChild(h('td', null, 'Cases')); list.forEach(s => cr.appendChild(h('td', 'n', s.count == null ? '—' : String(s.count)))); tb.appendChild(cr);
    const vr = h('tr'); vr.appendChild(h('td', null, 'Per-case values here')); list.forEach(s => vr.appendChild(h('td', 'n', s.perCase ? 'yes' : 'no'))); tb.appendChild(vr);
    t.appendChild(tb); sec.appendChild(wrapTable(t));
    sec.appendChild(h('p', 'small faint bench-desc', 'The change is from ' + base.full + '; it is coloured only for metrics with a better direction.'));
    return sec;
  }
  /** Every subject of the benchmark, sortable by any column; a row opens the subject, its box adds it to the compare set. */
  function subjectTable(view, state, act, stat, sel, cmp) {
    const sec = h('section', 'bench-all'), show = visibleSubject(state);
    const rows = view.subjects.filter(s => show(s) && (!state.ui.resultsOnly || view.metrics.some(m => valueOf(s, m.id, stat) != null)));
    const sort = state.ui.sort || { key: view.metrics.length ? 'm:' + view.metrics[0].id : 'full', dir: 1 };
    const keyOf = (s, k) => k === 'short' ? (s.model && s.model.short) || null : k === 'full' ? (s.model ? s.model.title : s.title) : k === 'kind' ? (s.model ? P.kindLabel(s.kind) : null) : k === 'group' ? s.group || null : k === 'count' ? s.count : k === 'perCase' ? (s.perCase ? 1 : null) : k.startsWith('m:') ? valueOf(s, k.slice(2), stat) : null;
    const metricOf = k => k.startsWith('m:') ? view.metrics.find(m => m.id === k.slice(2)) : null;
    const flip = (metricOf(sort.key) || {}).better === 'higher' ? -1 : 1;   // a metric column sorts best first
    rows.sort((a, b) => { const ka = keyOf(a, sort.key), kb = keyOf(b, sort.key); if (ka == null && kb == null) return a.full.localeCompare(b.full); if (ka == null) return 1; if (kb == null) return -1; return (typeof ka === 'number' ? (ka - kb) * flip : String(ka).localeCompare(String(kb))) * sort.dir; });
    sec.appendChild(sect('All subjects', rows.length + ' of ' + view.subjects.length + ' · ' + stat + ' of each metric'));
    const cols = [['', 'cmp'], ['', 'short', 'ck'], ['Subject', 'full'], ['Kind', 'kind'], ['Group', 'group']].concat(view.metrics.map(m => [m.title + units(m), 'm:' + m.id, 'n'])).concat([['Cases', 'count', 'n'], ['Per case', 'perCase']]);
    const t = h('table', 'tv all'), thead = h('thead'), tr = h('tr');
    for (const [label, key, cls] of cols) {
      const th = h('th', cls === 'n' ? 'n' : null);
      if (key === 'cmp') { th.appendChild(h('span', 'sr-only', 'Compare')); tr.appendChild(th); continue; }
      const b = button(null, label || 'Short name', () => act.setUI('sort', sort.key === key ? { key, dir: -sort.dir } : { key, dir: 1 })); b.dataset.key = 'sort-' + key;
      if (!label) { b.textContent = ''; b.appendChild(h('span', 'sr-only', 'Short name')); b.appendChild(document.createTextNode('#')); }
      if (sort.key === key) { b.setAttribute('aria-sort', sort.dir > 0 ? 'ascending' : 'descending'); th.setAttribute('aria-sort', sort.dir > 0 ? 'ascending' : 'descending'); }
      th.appendChild(b); tr.appendChild(th);
    }
    thead.appendChild(tr); t.appendChild(thead);
    const tb = h('tbody');
    for (const s of rows) {
      const row = h('tr', 'rowbtn' + (s.key === sel ? ' is-sel' : '')); row.dataset.subject = s.name; row.addEventListener('click', () => act.select(s.key === sel ? null : s.key));
      const tdc = h('td'), cb = h('input'); cb.type = 'checkbox'; cb.checked = cmp.includes(s.key); cb.disabled = !cb.checked && cmp.length >= 3; cb.dataset.key = 'cmp-' + s.key; cb.setAttribute('aria-label', 'Compare ' + s.full);
      cb.addEventListener('click', ev => { ev.stopPropagation(); act.toggleCompare(s.key); }); tdc.appendChild(cb); row.appendChild(tdc);
      row.appendChild(h('td', 'ck', s.model && s.model.short ? s.model.short : ''));
      const nt = h('td'); const nb = button('linkish', s.model ? s.model.title : s.title, ev => { ev.stopPropagation(); act.select(s.key === sel ? null : s.key); }); nb.dataset.key = 'open-' + s.key; nt.appendChild(nb); row.appendChild(nt);
      const kt = h('td'); kt.appendChild(s.model ? h('span', 'chip ' + s.kind, P.kindLabel(s.kind)) : h('span', 'small faint', 'not on the map')); row.appendChild(kt);
      row.appendChild(h('td', 'small faint nowrap grp', s.group));
      for (const m of view.metrics) row.appendChild(h('td', 'n', valueOf(s, m.id, stat) == null ? '' : fmt(valueOf(s, m.id, stat))));
      row.appendChild(h('td', 'n', s.count == null ? '' : String(s.count))); row.appendChild(h('td', 'small faint', s.perCase ? 'held here' : ''));
      tb.appendChild(row);
    }
    t.appendChild(tb); sec.appendChild(wrapTable(t));
    if (!rows.length) sec.appendChild(h('p', 'empty', 'No subject matches the filters.'));
    return sec;
  }

  // ---- Train --------------------------------------------------------------------
  const TO_BUILD = ['not-built', 'out-of-date', 'failed'];
  const RUN_TONE = { succeeded: 'good', adopted: 'good', running: 'pending', queued: 'pending', failed: 'serious', 'timed-out': 'serious', 'over-disk': 'serious', unknown: 'warn', cancelled: 'neutral' };
  const REQUEST_TONE = { 'awaiting-approval': 'pending', queued: 'pending', running: 'pending', succeeded: 'good', failed: 'serious', cancelled: 'neutral', declined: 'neutral', expired: 'neutral' };
  const runState = st => S.stateEl(RUN_TONE[st] || 'neutral', st === 'timed-out' ? 'ran out of time' : st === 'over-disk' ? 'over its disk budget' : st);
  const requestState = st => S.stateEl(REQUEST_TONE[st] || 'neutral', st === 'awaiting-approval' ? 'awaiting approval' : st);
  const who = r => r && (r.label || r.kind) || 'someone';
  const covering = r => r.every ? 'everything buildable' : (r.targets || []).join(', ') || 'nothing named';
  function train(main, aside, state, act, data) {
    const sel = state.sel.train || null;
    paint(main, async () => {
      const [recipes, runs, requests, envs] = await Promise.all([P.read('definitions', { kind: 'recipe' }), P.read('runs'), P.read('build_requests'), P.read('environments')]);
      const running = runs.runs.filter(r => r.state === 'running');
      const progress = new Map(await Promise.all(running.map(r => P.call('progress', { run: r.id }).then(p => [r.id, p.event], () => [r.id, null]))));
      return { recipes: recipes.definitions, runs: runs.runs, requests: requests.requests, envs: envs.environments, progress };
    }, (frag, { recipes, runs, requests, envs, progress }) => {
      const g = graphFor(data.map), deviceOf = new Map(envs.map(e => [e.reference, e.device]));
      // Planned (spec-w3 section 3.2): the drafts of this page, then the models never built.
      const E = window.LabEditor, drafts = g.nodes.filter(m => m.draft);
      const never = recipes.filter(d => !d.removed && d.state === 'not-built' && (!g.byId.has(d.reference) || g.byId.get(d.reference).planned));
      const neverRefs = new Set(never.map(d => d.reference));
      frag.appendChild(sect('Planned', String(drafts.length + never.length)));
      if (!drafts.length && !never.length) frag.appendChild(h('p', 'empty', 'Nothing is planned. Branch from a model on the map to plan a new one.'));
      else {
        const ul = h('ul', 'rows planned');
        for (const m of drafts) {
          const li = h('li'), b = button('row todo'); b.dataset.key = 'open-' + m.id; b.dataset.draft = m.id;
          b.appendChild(S.stateEl('neutral', 'not kept yet')); const t = h('span'); t.appendChild(h('span', 'title', m.title)); t.appendChild(h('span', 'sub', 'from ' + (g.byId.has(m.parent) ? Tree.nameOf(g.byId.get(m.parent)) : m.parent) + ' · on the map until it is kept')); b.appendChild(t);
          b.appendChild(h('span', 'chip ' + m.kind + ' draft', 'draft'));
          b.addEventListener('click', () => act.go('map', m.id)); li.appendChild(b); ul.appendChild(li);
        }
        for (const d of never) ul.appendChild(todoRow(d, g, sel, act));
        frag.appendChild(ul);
      }
      // Models to build again: out of date or failed.
      const todo = recipes.filter(d => !d.removed && TO_BUILD.includes(d.state) && !neverRefs.has(d.reference));
      const th = sect('To build', todo.length + ' of ' + plural(recipes.length, 'model')); th.classList.add('gap'); th.appendChild(h('span', 'spacer'));
      th.appendChild(A.group('train:every', [{ id: 'plan', label: 'Plan everything buildable', cls: 'btn sm', who: 'request', onClick: () => act.select('plan:*') }], { inline: true }));
      frag.appendChild(th);
      if (!todo.length) frag.appendChild(h('p', 'empty', 'No model is out of date or failed.'));
      else {
        const ul = h('ul', 'rows');
        for (const d of todo) ul.appendChild(todoRow(d, g, sel, act));
        frag.appendChild(ul);
      }
      // Build requests.
      const rh = sect('Build requests', String(requests.length)); rh.classList.add('gap'); frag.appendChild(rh);
      if (!requests.length) frag.appendChild(h('p', 'empty', 'Nobody has asked for a build of this project through Tuldok.'));
      else {
        const ul = h('ul', 'rows');
        for (const r of requests) {
          const li = h('li'), key = 'request:' + r.id, b = button('row request'); b.setAttribute('aria-pressed', String(key === sel)); b.dataset.key = 'open-' + key;
          b.appendChild(requestState(r.state)); const t = h('span'); t.appendChild(h('span', 'title', 'A build of ' + covering(r))); t.appendChild(h('span', 'sub', 'asked by ' + who(r.requested_by) + (r.scratch ? ' · from the code as it is' : '') + (r.problem ? ' · ' + r.problem : ''))); b.appendChild(t);
          b.appendChild(h('span', 'sub num', time(r.requested_at)));
          b.addEventListener('click', () => act.select(key === sel ? null : key)); li.appendChild(b); ul.appendChild(li);
        }
        frag.appendChild(ul);
      }
      // Runs, newest first.
      const bar = h('div', 'filters gap'); bar.appendChild(searchBox(state, act, 'Find a run')); bar.appendChild(kindChips(state, act, g.nodes.map(m => m.kind)));
      bar.appendChild(h('span', 'pop', plural(runs.length, 'run') + ' on this machine'));
      frag.appendChild(bar);
      const q = (state.query || '').toLowerCase();
      const shown = runs.filter(r => { const m = g.byId.get(r.reference); return (!state.kinds || (m && state.kinds.has(m.kind))) && (!q || [r.reference, r.subject, r.id, m && Tree.nameOf(m)].some(t => t && t.toLowerCase().includes(q))); });
      frag.appendChild(sect('Runs', shown.length + ' of ' + runs.length + ' · newest first'));
      if (!runs.length) frag.appendChild(h('p', 'empty', 'Nothing has been built or adopted in this project on this machine.'));
      else {
        const ul = h('ul', 'rows');
        for (const r of shown) {
          const m = g.byId.get(r.reference), li = h('li'), key = 'run:' + r.id, b = button('row run'); b.setAttribute('aria-pressed', String(key === sel)); b.dataset.key = 'open-' + key; b.dataset.run = r.id;
          b.appendChild(h('span', 'ck', m ? Tree.refName(m) : nameOfRef(r.reference)));
          const t = h('span'); t.appendChild(h('span', 'title', (m ? m.title : r.reference) + (r.subject ? ' · ' + r.subject : '')));
          const when = r.finished_at || r.started_at || r.queued_at, ev = progress.get(r.id);
          if (r.state === 'running' && ev) t.appendChild(rowProgress(ev));
          else t.appendChild(h('span', 'sub', [r.state === 'running' ? 'started ' + time(r.started_at) + ' · no progress reported yet' : time(when), seconds(r.seconds), r.bytes != null ? bytes(r.bytes) : null, r.scratch ? 'from the code as it is' : null].filter(Boolean).join(' · ')));
          b.appendChild(t);
          b.appendChild(m ? h('span', 'chip ' + m.kind, P.kindLabel(m.kind)) : h('span', 'small faint', nameOfRef(r.reference).length ? r.reference.split('/')[0].replace(/s$/, '') : ''));
          b.appendChild(h('span', 'sub', (r.environment && deviceOf.get(r.environment.reference)) || '—'));
          b.appendChild(runState(r.state));
          b.addEventListener('click', () => act.select(key === sel ? null : key)); li.appendChild(b); ul.appendChild(li);
        }
        frag.appendChild(ul);
        if (runs.length >= 100) frag.appendChild(h('p', 'note', 'The hundred newest runs are listed.'));
      }
      // Environments.
      const eh = sect('Environments', String(envs.length)); eh.classList.add('gap'); frag.appendChild(eh);
      if (!envs.length) frag.appendChild(h('p', 'empty', 'The project defines no environment.'));
      else {
        const ul = h('ul', 'rows');
        for (const e of envs) {
          const li = h('li'), key = 'env:' + e.reference, r = button('row env'); r.appendChild(modelState(e.state)); r.setAttribute('aria-pressed', String(key === sel)); r.dataset.key = 'open-' + key; r.dataset.env = e.reference;
          r.addEventListener('click', () => act.select(key === sel ? null : key));
          const t = h('span'); t.appendChild(h('span', 'title', e.title));
          const asks = ['asks Python ' + (e.python || '—'), e.device, plural(Object.keys(e.packages || {}).length, 'package')].filter(Boolean).join(', ');
          const found = e.found ? 'found Python ' + (e.found.python || '?') + ', ' + plural(Object.keys(e.found.packages || {}).length, 'package') : e.interpreter ? 'not checked' : 'no interpreter recorded here';
          t.appendChild(h('span', 'sub', asks + ' · ' + found + (e.checked_at ? ' · checked ' + P.day(e.checked_at) : '')));
          if (e.problems && e.problems.length) t.appendChild(h('span', 'sub warnline', e.problems.join(' ')));
          r.appendChild(t); r.appendChild(h('span', 'sub mono', e.interpreter || '')); li.appendChild(r); ul.appendChild(li);
        }
        frag.appendChild(ul);
      }
    });
    if (!sel) return closeDrawer(aside);
    if (sel.startsWith('run:')) runDrawer(aside, sel, act, data);
    else if (sel.startsWith('request:')) requestDrawer(aside, sel, act, data);
    else if (sel.startsWith('plan:')) A.planView(aside, sel, act.go, () => { const one = sel.slice(5); act.select(data.map.byId.has(one) ? one : null); });
    else if (sel.startsWith('env:')) envDrawer(aside, sel, act, data);
    else if (window.LabEditor && window.LabEditor.owns(sel, data)) window.LabEditor.drawer(aside, sel, act, data, 'train');
    else if (data.map.byId.has(sel)) S.inspectorModel(aside, sel, act, data);
    else if (aside._for !== sel) { aside.textContent = ''; aside._for = sel; aside.appendChild(h('p', 'empty', 'There is no ' + sel + ' here.')); }
    return true;
  }
  /** A row of a model to build, opening its drawer, with Plan build. */
  function todoRow(d, g, sel, act) {
    const m = g.byId.get(d.reference), li = h('li'), b = button('row todo'); b.setAttribute('aria-pressed', String(d.reference === sel)); b.dataset.key = 'open-' + d.reference;
    b.appendChild(modelState(d.state)); const t = h('span'); const title = h('span', 'title', m ? Tree.nameOf(m) : d.title); if (m) title.appendChild(Tree.mark(m)); t.appendChild(title); t.appendChild(h('span', 'sub', m ? m.groupTitle + (m.description ? ' · ' + m.description : '') : d.reference)); b.appendChild(t);
    b.appendChild(m ? h('span', 'chip ' + m.kind, P.kindLabel(m.kind)) : h('span'));
    b.addEventListener('click', () => act.select(d.reference === sel ? null : d.reference)); li.appendChild(b);
    const plan = A.group('todo:' + d.reference, [{ id: 'plan', label: 'Plan build', cls: 'btn sm', who: 'request', onClick: () => act.select('plan:' + d.reference) }], { inline: true });
    if (!plan.hidden) { li.classList.add('with-act'); li.appendChild(plan); }
    if (window.LabEditor) window.LabEditor.decorate(li);
    return li;
  }
  const tail = (text, lines) => { const all = text.replace(/\n$/, '').split('\n'); return (all.length > lines ? '…\n' : '') + all.slice(-lines).join('\n'); };
  /** A definition's value in one line: a list of words as a command line, an object as key: value pairs. */
  const brief = v => v == null ? '—' : typeof v !== 'object' ? String(v) : Array.isArray(v) ? (v.every(x => typeof x === 'string') ? v.join(' ') : v.map(brief).join(', ')) : Object.entries(v).map(([k, x]) => k + ': ' + (x && typeof x === 'object' && !Array.isArray(x) ? '{' + brief(x) + '}' : brief(x))).join(', ');
  const json = v => { if (typeof v === 'string') { try { v = JSON.parse(v); } catch (e) { return v; } } return brief(v); };
  const ACTIVE = ['queued', 'running'];
  const LOG_LINES = 200;   // lines of each log kept on the page while a run is read live
  const hairOf = ev => { const hair = h('span', 'hair'); const i = h('i'); i.style.width = Math.round(100 * ev.completed / Math.max(1, ev.total)) + '%'; hair.appendChild(i); hair.setAttribute('role', 'progressbar'); hair.setAttribute('aria-valuemin', '0'); hair.setAttribute('aria-valuemax', String(ev.total)); hair.setAttribute('aria-valuenow', String(ev.completed)); return hair; };
  const eventText = ev => ev.stage + ': ' + ev.completed + ' of ' + ev.total + Object.entries(ev.metrics).map(([k, v]) => ' · ' + k + ' ' + fmt(v)).join('');
  // A running run's progress in its row of Train's list: a hairline and a line.
  const rowWidth = ev => Math.round(100 * ev.completed / Math.max(1, ev.total)) + '%';
  const rowText = ev => ev.stage + ' ' + ev.completed + ' of ' + ev.total + Object.entries(ev.metrics).slice(0, 2).map(([k, v]) => ' · ' + k + ' ' + fmt(v)).join('');
  function rowProgress(ev) { const line = h('span', 'sub live'); const hair = h('span', 'hair'); const i = h('i'); i.style.width = rowWidth(ev); hair.appendChild(i); line.appendChild(hair); line.appendChild(document.createTextNode(rowText(ev))); return line; }
  /**
   * Sets the latest progress of the running runs (a Map of run id to event,
   * app.js on every reading) into their rows of Train's list, in place: the
   * hairline's width and the line's text, when they differ (spec-w4 R7).
   */
  S.progress = events => {
    for (const b of document.querySelectorAll('#main button.row.run[data-run]')) {
      const ev = events.get(b.dataset.run); if (!ev) continue;
      const line = b.querySelector('.sub.live');
      if (!line) { const sub = b.children[1] && b.children[1].querySelector('.sub'); if (sub) sub.replaceWith(rowProgress(ev)); continue; }   // its first progress
      const i = line.querySelector('i'), width = rowWidth(ev), text = rowText(ev);
      if (i.style.width !== width) i.style.width = width;
      if (line.lastChild.data !== text) line.lastChild.data = text;
    }
  };
  let live = null;   // the open run read live: {key, run, offsets, update(progress), ended()}
  /**
   * One step of the live run (app.js calls it on every reading, every two
   * seconds while a build runs): its progress and its logs from the offsets,
   * updated in place (spec-w4 R7). When it has ended, the project is read
   * again and its drawer is drawn again in place.
   */
  S.tick = async () => {
    const aside = document.getElementById('aside');
    if (!live || aside._for !== live.key) { live = null; return; }
    const mine = live;
    try {
      const pr = await P.call('progress', { run: mine.run, stdout_offset: mine.offsets.stdout, stderr_offset: mine.offsets.stderr });
      if (live !== mine || aside._for !== mine.key) return;
      mine.update(pr);
      if (pr.ended) { live = null; mine.ended(); }   // not awaited: the reading it starts waits for the one calling this
    } catch (error) { /* the next tick asks again; the strip says what fails */ }
  };
  function runDrawer(aside, key, act, data) {
    const id = key.slice(4);
    drawer(aside, key, () => Promise.all([P.read('run', { run: id }), P.call('progress', { run: id })]), (ins, [r, pr]) => {
      const m = graphFor(data.map).byId.get(r.reference);
      const hd = h('header'); hd.appendChild(h('span', 'kicker', 'run ' + r.id)); const t2 = h('h2', null, (m ? Tree.nameOf(m) : r.reference) + (r.subject ? ' · ' + r.subject : '')); t2.tabIndex = -1; hd.appendChild(t2);
      const meta = h('div', 'ins-meta'); if (m) meta.appendChild(h('span', 'chip ' + m.kind, P.kindLabel(m.kind))); meta.appendChild(runState(r.state)); if (r.scratch) meta.appendChild(h('span', 'small faint', 'from the code as it is')); hd.appendChild(meta); ins.appendChild(hd);
      if (m) { const acts = h('div', 'actions'); acts.appendChild(button('btn sm ghost', 'On the map', () => act.go('map', m.id))); acts.appendChild(button('btn sm ghost', 'Its model', () => act.select(m.id))); ins.appendChild(acts); }
      // Cancel run while it is queued or running; Stop what it left running when its build is gone.
      const active = ACTIVE.includes(r.state), orphan = active && r.builder_alive === false;
      ins.appendChild(A.group('run:' + r.id, [
        { id: 'cancel', label: 'Cancel run', cls: 'btn', who: 'cancel', op: 'cancel_run', args: () => ({ run: r.id }), busy: 'Cancelling…', hidden: !active || orphan,
          confirm: 'Ask this run to stop. It ends cancelled and leaves no product.' },
        { id: 'stop', label: 'Stop what it left running', cls: 'btn', who: 'cancel', op: 'stop_run', args: () => ({ run: r.id }), busy: 'Stopping…', hidden: !orphan,
          confirm: 'Kill every process this run left behind and mark it unknown; its build is gone.' }
      ]));
      const su = setup();
      su.put('Definition', r.reference, 'mono');
      if (r.subject) su.put('Subject', r.subject);
      su.put('Queued', time(r.queued_at)); su.put('Started', time(r.started_at)); su.put('Finished', time(r.finished_at));
      su.put('Took', r.seconds == null ? '—' : seconds(r.seconds)); if (r.exit_status != null) su.put('Exit status', String(r.exit_status));
      if (r.environment) su.put('Environment', r.environment.reference + (r.environment.found ? ' · Python ' + r.environment.found.python : '') + (r.environment.interpreter ? ' · ' + r.environment.interpreter : ''), 'mono');
      su.put('Commit', r.commit || '—', 'mono');
      su.put('Command', (r.argv || []).join(' ') || '—', 'mono cmdline');
      const inputs = Object.entries(r.inputs || {});
      su.put('Inputs', inputs.length ? inputs.map(([k, v]) => k + ' ← ' + (v.reference || '?') + (v.output ? ' (' + v.output + ')' : '') + (v.run_id ? ' · run ' + v.run_id.slice(0, 8) : '')).join('\n') : 'none', 'mono pre');
      if (r.settings != null) su.put('Settings', json(r.settings), 'mono');
      if (r.env_names && r.env_names.length) su.put('Variables', r.env_names.join(', ') + ' (values not shown)', 'mono');
      if (r.product) su.put('Product', r.product.directory + '\n' + Object.entries(r.product.outputs || {}).map(([k, v]) => k + ': ' + v.path + ' · ' + bytes(v.bytes)).join('\n') + (r.product.current ? '' : '\n(no longer current)') + (r.product.adopted ? '\n(adopted)' : ''), 'mono pre');
      else su.put('Product', 'none');
      if (r.bytes != null) su.put('Size', bytes(r.bytes));
      if (r.problem) su.put('Problem', r.problem);
      // The latest progress: a hairline and its line, kept current while the run is read live.
      const prog = h('div', 'progress-line');
      const showEvent = ev => { prog.textContent = ''; if (ev) { prog.appendChild(hairOf(ev)); prog.appendChild(h('span', 'small', eventText(ev))); } else prog.appendChild(h('p', 'note', active ? 'No progress reported yet.' : 'No progress was reported.')); };
      showEvent(pr.event);
      const progBlock = block('Latest progress', prog); if (!pr.event && !active) progBlock.hidden = true;
      // A run read live shows its progress and logs first; an ended one its record first.
      ins.appendChild(progBlock);
      if (!active) ins.appendChild(su.dl);
      const logs = {};
      for (const [name, title] of [['stdout', 'Standard output'], ['stderr', 'Standard error']]) {
        const log = pr[name] || { text: '' }, b = h('div'), head = h('h3', null, title + (log.size != null ? ' · ' + bytes(log.size) : ''));
        b.appendChild(head);
        const pre = h('pre', 'evtext'); pre.dataset.log = name; let lines = log.text ? log.text.replace(/\n$/, '').split('\n').slice(-LOG_LINES) : [];
        const note = h('p', 'note', log.size == null ? 'No log on this machine.' : 'Empty.');
        const paintLog = () => { pre.textContent = (lines.length >= LOG_LINES ? '…\n' : '') + lines.join('\n'); pre.hidden = !lines.length; note.hidden = !!lines.length; pre.scrollTop = pre.scrollHeight; };
        b.appendChild(pre); b.appendChild(note); paintLog(); ins.appendChild(b);
        logs[name] = { head, title, add: text => { if (!text) return; lines = lines.concat(text.replace(/\n$/, '').split('\n')).slice(-LOG_LINES); paintLog(); } };
      }
      if (active) ins.appendChild(su.dl);
      if (!active && live && live.key === key) live = null;   // drawn again once it ended
      if (active) {
        live = { key, run: r.id, offsets: { stdout: (pr.stdout || {}).offset || 0, stderr: (pr.stderr || {}).offset || 0 },
          update: p => {
            showEvent(p.event); progBlock.hidden = false;
            for (const name of ['stdout', 'stderr']) { const log = p[name]; if (!log) continue; logs[name].add(log.text); live.offsets[name] = log.offset; if (log.size != null) logs[name].head.textContent = logs[name].title + ' · ' + bytes(log.size); }
          },
          ended: () => act.refresh() };
        ins.appendChild(h('p', 'note live-note', 'Read live every two seconds while it runs.'));
      }
    });
  }
  function requestDrawer(aside, key, act, data) {
    const id = key.slice(8);
    drawer(aside, key, () => P.read('build_request', { request: id }), (ins, r) => {
      const hd = h('header'); hd.appendChild(h('span', 'kicker', 'build request ' + r.id)); hd.appendChild(h('h2', null, 'A build of ' + covering(r)));
      const meta = h('div', 'ins-meta'); meta.appendChild(requestState(r.state)); hd.appendChild(meta); ins.appendChild(hd);
      if (r.state === 'declined' && r.problem) ins.appendChild(h('p', 'reason', 'Declined: ' + r.problem));
      // Approve and Decline while it awaits approval; Cancel while it awaits approval, is queued or runs.
      const waiting = r.state === 'awaiting-approval', cancellable = ['awaiting-approval', 'queued', 'running'].includes(r.state);
      ins.appendChild(A.group('request:' + r.id, [
        { id: 'approve', label: 'Approve', cls: 'btn primary', who: 'owner', op: 'approve_build', args: () => ({ request: r.id }), busy: 'Approving…', hidden: !waiting },
        Object.assign(A.declineItem(r.id), { cls: 'btn', hidden: !waiting }),
        { id: 'cancel', label: 'Cancel', cls: 'btn ghost', who: 'cancel', op: 'cancel_build', args: () => ({ request: r.id }), busy: 'Cancelling…', hidden: !cancellable,
          confirm: r.state === 'running' ? 'Cancel this build: its running step is asked to stop and nothing after it runs.' : 'Cancel this build request; nothing of it runs.' }
      ]));
      const su = setup();
      su.put('Asked by', who(r.requested_by) + ' · ' + time(r.requested_at));
      su.put('Targets', r.every ? 'everything buildable' + ((r.targets || []).length ? ', and ' + r.targets.join(', ') : '') : (r.targets || []).join(', ') || '—', 'mono');
      if (r.decided_at) su.put('Decided by', who(r.decided_by) + ' · ' + time(r.decided_at));
      if (r.started_at) su.put('Started', time(r.started_at)); if (r.finished_at) su.put('Finished', time(r.finished_at));
      if (r.expires_at) su.put('Expires', time(r.expires_at));
      su.put('Code', r.scratch ? 'as it is on disk, uncommitted changes included; the product is marked scratch' : (r.covers && r.covers.commit ? 'commit ' + r.covers.commit : 'committed'), 'mono');
      if (r.covers && r.covers.definitions) su.put('Definitions', plural(Object.keys(r.covers.definitions).length, 'definition') + ', as they stand when it is asked');
      if (r.problem) su.put(r.state === 'declined' ? 'Reason' : 'Problem', r.problem);
      if (r.result) su.put('Result', json(r.result), 'mono');
      ins.appendChild(su.dl);
      const steps = (r.covers && r.covers.steps) || [];
      const ul = h('ul', 'links');
      for (const s of steps) { const m = data.map.byId.get(s.reference), li = h('li'); const b = button(null, m ? Tree.nameOf(m) : s.reference, m ? () => act.select(m.id) : null); if (!m) b.disabled = true; if (s.subjects && s.subjects.length) b.appendChild(h('span', 'why', 'subjects: ' + s.subjects.join(', '))); li.appendChild(b); ul.appendChild(li); }
      ins.appendChild(block('What it covers · ' + plural(steps.length, 'step'), steps.length ? ul : h('p', 'note', 'Nothing.')));
      if (r.covers && r.covers.definitions) ins.appendChild(h('p', 'note', 'Approved as these ' + Object.keys(r.covers.definitions).length + ' definitions stand now: ' + Object.keys(r.covers.definitions).join(', ') + '.'));
      const rl = h('ul', 'rows');
      for (const run of r.runs || []) { const li = h('li'), b = button('row'); b.style.gridTemplateColumns = 'minmax(0, 1fr) auto'; const t = h('span'); t.appendChild(h('span', 'title', run.reference + (run.subject ? ' · ' + run.subject : ''))); t.appendChild(h('span', 'sub', [time(run.finished_at || run.started_at || run.queued_at), seconds(run.seconds)].filter(Boolean).join(' · '))); b.appendChild(t); b.appendChild(runState(run.state)); b.addEventListener('click', () => act.select('run:' + run.id)); li.appendChild(b); rl.appendChild(li); }
      ins.appendChild(block('Its runs', (r.runs || []).length ? rl : h('p', 'note', r.state === 'awaiting-approval' ? 'None: it has not been approved.' : 'None.')));
    });
  }

  // ---- Data -----------------------------------------------------------------------
  // The tab has two states (spec-d1 section 7): the cards, and one dataset opened, '#data/inside:<reference>'
  // (inside.js); a selection '<reference>' is that dataset's drawer beside the cards, as before.
  const INSIDE = 'inside:';
  const lookInside = (ref, act) => { const b = button('btn sm', 'Look inside', ev => { ev.stopPropagation(); act.go('data', INSIDE + ref); }); b.dataset.key = 'inside-' + ref; return b; };
  /** Data: the dataset cards, a dataset's drawer, or one dataset opened (inside.js). */
  function data_(main, aside, state, act, data) {
    const E = window.LabEditor, raw = state.sel.data || null;
    if (raw && raw.startsWith(INSIDE)) { closeDrawer(aside); window.LabInside.open(main, raw.slice(INSIDE.length), act, !!aside._again); return false; }
    if (window.LabInside) window.LabInside.leave();
    if (main._painted && String(main._painted).startsWith('data/' + INSIDE)) { main.scrollTop = 0; main.scrollLeft = 0; }   // back to the cards: from their top
    const sel = raw && E ? E.subject(raw) : raw;
    paint(main, () => Promise.all([P.read('definitions', { kind: 'dataset' }), P.read('products'), P.read('graph')]), (frag, [defs, products, graph]) => {
      const sets = defs.definitions.filter(d => !d.removed), byRef = new Map();
      for (const p of products.products) { if (!byRef.has(p.reference)) byRef.set(p.reference, []); byRef.get(p.reference).push(p); }
      const users = new Map(); for (const e of graph.edges) { if (!users.has(e.to)) users.set(e.to, new Set()); users.get(e.to).add(e.from); }
      const built = sets.filter(d => byRef.has(d.reference)).length, adopted = sets.filter(d => (byRef.get(d.reference) || []).some(p => p.adopted)).length;
      const total = sets.reduce((n, d) => n + (byRef.get(d.reference) || []).reduce((a, p) => a + (p.bytes || 0), 0), 0);
      const head = sect('Datasets', sets.length + ' · ' + built + ' with files on this machine' + (adopted ? ', ' + adopted + ' adopted' : '') + (total ? ' · ' + bytes(total) : ''));
      // Two forms that keep a new dataset as an unsaved edit (spec-d4 section 7, annotate.js): files brought in, and a dataset frozen with splits.
      if (window.LabAnnotate) { head.appendChild(h('span', 'spacer')); head.appendChild(A.group('data:new', [
        { id: 'import', label: 'Import files', cls: 'btn sm', who: 'edit', onClick: () => act.select(sel === 'new:import' ? null : 'new:import') },
        { id: 'freeze', label: 'Freeze a dataset', cls: 'btn sm', who: 'edit', onClick: () => act.select(sel === 'new:freeze' ? null : 'new:freeze') }], { inline: true })); }
      frag.appendChild(head);
      if (!sets.length) { frag.appendChild(h('p', 'empty', 'The project defines no dataset.')); return; }
      const grid = h('div', 'ds-grid');
      for (const d of sets) {
        const ps = byRef.get(d.reference) || [], outputs = ps.flatMap(p => Object.entries(p.outputs || {}).map(([k, v]) => ({ name: k, ...v, directory: p.directory }))), size = ps.reduce((a, p) => a + (p.bytes || 0), 0);
        const card = button('ds-card'); card.setAttribute('aria-pressed', String(d.reference === sel)); card.dataset.key = 'open-' + d.reference; card.dataset.ref = d.reference;
        const pv = h('div', 'pv text'); pv.setAttribute('aria-hidden', 'true');
        // A product with no declared outputs is its directory as a whole.
        const whole = !outputs.length && ps.length > 0;
        pv.textContent = outputs.length ? outputs.slice(0, 4).map(o => o.path + '  ' + bytes(o.bytes)).join('\n') + (outputs.length > 4 ? '\n…' : '') : whole ? 'the whole directory  ' + bytes(size) : 'no files on this machine';
        card.appendChild(pv);
        const t = h('div', 't'); t.appendChild(h('div', 'title', d.title));
        const meta = h('div', 'meta'); meta.appendChild(h('span', null, outputs.length ? plural(outputs.length, 'output') + ' · ' + bytes(size) : whole ? 'a directory · ' + bytes(size) : 'no files here'));
        const st = ps.some(p => p.adopted) ? S.stateEl('good', 'adopted') : modelState(d.state); st.classList.add('glyphs'); meta.appendChild(st); t.appendChild(meta);
        const used = [...(users.get(d.reference) || [])].sort();
        t.appendChild(h('div', 'uses', used.length ? 'used by ' + used.length + ': ' + used.map(nameOfRef).join(', ') : 'used by nothing'));
        t.appendChild(h('div', 'path', ps.length ? ps[0].directory : d.reference)); card.appendChild(t);
        card.title = d.title;
        card.addEventListener('click', () => act.select(d.reference === sel ? null : d.reference));
        // "Look inside" beside the card (a button cannot hold a button), when the dataset has a product here.
        const item = h('div', 'ds-item'); item.appendChild(card);
        if (ps.some(p => p.run_id)) { const foot = h('div', 'ds-foot'); foot.appendChild(lookInside(d.reference, act)); item.appendChild(foot); }
        grid.appendChild(item);
      }
      frag.appendChild(grid);
    });
    if (!sel) return closeDrawer(aside);
    if (raw.startsWith('new:') && window.LabAnnotate) { window.LabAnnotate.datasetForm(aside, raw.slice(4), act); return true; }
    if (E && E.owns(raw, data)) { E.drawer(aside, raw, act, data, 'data'); return true; }
    drawer(aside, sel, () => Promise.all([P.read('definition', { reference: sel }), P.read('products', { reference: sel })]), (ins, [d, p]) => {
      const hd = h('header'); hd.appendChild(h('span', 'kicker', d.reference)); const t2 = h('h2', null, d.title); t2.tabIndex = -1; hd.appendChild(t2);
      const meta = h('div', 'ins-meta'); meta.appendChild(p.products.some(x => x.adopted) ? S.stateEl('good', 'adopted') : modelState(d.state)); meta.appendChild(Tree.mark({ id: d.reference, unsaved: d.unsaved })); hd.appendChild(meta); ins.appendChild(hd);
      // Edit (spec-w3 section 3.2): the editor, in the text view.
      if (p.products.some(x => x.run_id)) { const look = h('div', 'actions'); look.appendChild(lookInside(d.reference, act)); ins.appendChild(look); }
      const doc = d.document || {};
      ins.appendChild(A.group('dataedit:' + d.reference, [{ id: 'edit', label: 'Edit', cls: 'btn sm', who: 'edit', onClick: () => act.select('edit:' + d.reference) },
        { id: 'plan', label: 'Plan build', cls: 'btn sm', who: 'request', hidden: !(doc.run && typeof doc.run === 'object'), onClick: () => act.go('train', 'plan:' + d.reference) }]));
      if (E) E.decorate(hd);
      ins.appendChild(block('Description', doc.description ? h('p', null, doc.description) : h('p', 'note', 'The definition has no description.')));
      const su = setup(); const skip = new Set(['format', 'kind', 'title', 'description']);
      for (const [k, v] of Object.entries(doc)) {
        if (skip.has(k)) continue;
        if (v && typeof v === 'object' && !Array.isArray(v)) for (const [k2, v2] of Object.entries(v)) su.put(k + ' · ' + k2, brief(v2), 'mono');
        else su.put(k, brief(v), 'mono');
      }
      ins.appendChild(block('Definition', su.dl.children.length ? su.dl : h('p', 'note', 'No other fields.')));
      const files = h('div');
      if (!p.products.length) files.appendChild(h('p', 'note', 'No files of this dataset on this machine.'));
      for (const pr of p.products) {
        const dl = setup(); dl.put('Folder', pr.directory, 'mono');
        for (const [k, o] of Object.entries(pr.outputs || {})) dl.put(k, pr.directory.replace(/\/$/, '') + '/' + o.path + ' · ' + bytes(o.bytes), 'mono');
        dl.put('Made', (pr.adopted ? 'adopted' : 'built') + ' · ' + time(pr.finished_at) + (pr.commit ? ' · ' + pr.commit.slice(0, 12) : '') + (pr.scratch ? ' · from the code as it is' : ''));
        if (pr.subject) dl.put('Subject', pr.subject);
        files.appendChild(dl.dl);
      }
      ins.appendChild(block('Files', files));
      const ul = h('ul', 'links');
      for (const u of d.used_by) { const m = data.map.byId.get(u.reference), li = h('li'); const b = button(null, m ? Tree.nameOf(m) : u.reference, m ? () => act.go('map', m.id) : null); b.appendChild(h('span', 'why', u.role)); if (!m) b.disabled = true; li.appendChild(b); ul.appendChild(li); }
      ins.appendChild(block('Used by', d.used_by.length ? ul : h('p', 'note', 'Nothing uses it.')));
    });
    return true;
  }

  // ---- Analysis: per-case values ---------------------------------------------------
  const PAGE = 200;
  function analysis(main, aside, state, act, data) {
    const ui = state.ui, sel = state.sel.analysis || null;
    paint(main, async () => {
      const list = await benchmarkList();
      const b = list.find(x => x.benchmark === (ui.anaBench || state.benchmark)) || list.find(x => x.subjects_with_values > 0) || pickBenchmark(list, null);
      if (!b) return { list };
      const view = await benchmarkView(b.benchmark, data.map);
      const subject = view.byName.get(ui.anaSubject) || view.subjects.find(s => s.perCase) || view.subjects[0] || null;
      const metric = view.metrics.find(m => m.id === ui.anaMetric) || view.metrics[0] || null;
      const page = Math.max(0, ui.anaPage || 0);
      const values = subject && metric ? await P.read('values', { benchmark: view.name, subject: subject.name, metric: metric.id, offset: page * PAGE, limit: PAGE }) : null;
      return { list, b, view, subject, metric, page, values };
    }, (frag, { list, view, subject, metric, page, values }, width) => {
      if (!view) { frag.appendChild(h('p', 'empty', 'This project defines no benchmark.')); return; }
      const bar = h('div', 'viewer-bar');
      bar.appendChild(select('Benchmark', list.map(x => [x.benchmark, x.title + (x.subjects_with_values ? ' · ' + x.subjects_with_values + ' with per-case values' : '')]), view.name, v => { state.ui.anaSubject = null; state.ui.anaPage = 0; act.setUI('anaBench', v); }, 'ana-bench'));
      if (view.subjects.length) bar.appendChild(select('Subject', view.subjects.map(s => [s.name, s.full + (s.perCase ? ' · per-case values' : '')]), subject.name, v => { state.ui.anaPage = 0; act.setUI('anaSubject', v); }, 'ana-subject'));
      if (view.metrics.length) bar.appendChild(select('Metric', view.metrics.map(m => [m.id, m.title + units(m)]), metric.id, v => { state.ui.anaPage = 0; act.setUI('anaMetric', v); }, 'ana-metric'));
      frag.appendChild(bar);
      if (!subject || !metric) { frag.appendChild(h('p', 'empty', 'This benchmark has no ' + (subject ? 'metric' : 'subject') + '.')); return; }
      if (!values.total) {
        frag.appendChild(sect('Per case', metric.title + units(metric) + ' · ' + subject.full));
        const p = h('p', 'empty ana-none'); p.appendChild(document.createTextNode('This machine holds no per-case values of ' + subject.full + ' for ' + metric.title + ' on ' + view.title + '; its summaries are on the '));
        const a = h('a', null, 'Benchmarks tab'); a.href = '#benchmarks'; a.addEventListener('click', ev => { ev.preventDefault(); act.setBenchmark(view.name); act.go('benchmarks'); }); p.appendChild(a); p.appendChild(document.createTextNode('.')); frag.appendChild(p); return;
      }
      const rows = values.rows.map(r => ({ ...r, id: r.case + (r.group ? ' · ' + r.group : ''), label: r.case + (r.group ? ' · ' + r.group.replace(/;/g, ', ') : '') }));
      const pages = Math.ceil(values.total / PAGE), first = page * PAGE + 1, last = page * PAGE + rows.length;
      const sec = h('section'); sec.appendChild(sect('Per case', metric.title + units(metric) + ' · ' + subject.full + ' · ' + (pages > 1 ? first + '–' + last + ' of ' : '') + plural(values.total, 'value')));
      const xs = rows.map(r => r.value).filter(v => v != null), sorted = xs.slice().sort((a, b) => a - b);
      const dl = h('dl', 'metrics ana-sum');
      const worst = !xs.length ? null : metric.better === 'higher' ? sorted[0] : sorted[sorted.length - 1];
      dl.appendChild(cell(pages > 1 ? 'Values on this page' : 'Values', String(xs.length)));
      dl.appendChild(cell('Median', fmt(sorted.length ? sorted[Math.floor(sorted.length / 2)] : null)));
      dl.appendChild(cell(metric.better === 'none' ? 'Largest' : 'Worst', fmt(metric.better === 'none' ? (sorted.length ? sorted[sorted.length - 1] : null) : worst)));
      dl.appendChild(cell('Without a value', String(rows.length - xs.length)));
      sec.appendChild(dl);
      const host = h('div'); sec.appendChild(host);
      C.strip(host, rows, { width, height: 110, label: metric.title + ' per case of ' + subject.full, valueTitle: metric.title + units(metric), selected: sel, onSelect: id => act.select(id === sel ? null : id) });
      sec.appendChild(h('p', 'small faint bench-desc', 'One mark per case' + (rows.some(r => r.group) ? ' and group' : '') + ', in the order of the cases; ' + better(metric) + '.' + (rows.length > xs.length ? ' A short hollow mark has no value.' : '')));
      if (pages > 1) {
        const pg = h('div', 'pager');
        const pb = button('btn sm', 'Previous', () => act.setUI('anaPage', page - 1)); pb.disabled = page === 0; pb.dataset.key = 'prev';
        const nb = button('btn sm', 'Next', () => act.setUI('anaPage', page + 1)); nb.disabled = page + 1 >= pages; nb.dataset.key = 'next';
        pg.appendChild(pb); pg.appendChild(nb); pg.appendChild(h('span', null, 'page ' + (page + 1) + ' of ' + pages)); sec.appendChild(pg);
      }
      const t = h('table', 'tv cases-t'); t.appendChild(headRow([['Case'], ['Group'], [metric.title + units(metric), 'n'], ['Why no value']])); const tb = h('tbody');
      for (const r of rows) { const tr = h('tr', 'rowbtn' + (r.id === sel ? ' is-sel' : '')); tr.addEventListener('click', () => act.select(r.id === sel ? null : r.id)); tr.appendChild(h('td', 'ck', r.case)); tr.appendChild(h('td', 'small faint', r.group || '')); tr.appendChild(h('td', 'n', r.value == null ? '—' : fmt(r.value))); tr.appendChild(h('td', 'small faint', r.reason || '')); tb.appendChild(tr); }
      t.appendChild(tb); sec.appendChild(wrapTable(t)); frag.appendChild(sec);
    });
    return closeDrawer(aside);
  }

  /** An environment: what it asks, what was found on this machine, and Check again, Connect and Disconnect. */
  function envDrawer(aside, key, act, data) {
    const ref = key.slice(4);
    drawer(aside, key, () => P.read('environment', { reference: ref }), (ins, e) => {
      const hd = h('header'); hd.appendChild(h('span', 'kicker', 'environment · ' + e.reference)); const t = h('h2', null, e.title); t.tabIndex = -1; hd.appendChild(t);
      const meta = h('div', 'ins-meta'); meta.appendChild(modelState(e.state)); if (e.origin) meta.appendChild(h('span', 'small faint', e.origin)); hd.appendChild(meta); ins.appendChild(hd);
      const su = setup();
      su.put('Asks', ['Python ' + (e.python || '—'), e.device, plural(Object.keys(e.packages || {}).length, 'package')].filter(Boolean).join(', '));
      if (Object.keys(e.packages || {}).length) su.put('Packages', Object.entries(e.packages).map(([k, v]) => k + ' ' + v).join(', '), 'mono');
      su.put('Interpreter', e.interpreter || 'none recorded on this machine', e.interpreter ? 'mono' : null);
      if (e.found) su.put('Found', 'Python ' + (e.found.python || '?') + ', ' + plural(Object.keys(e.found.packages || {}).length, 'package'));
      su.put('Checked', e.checked_at ? time(e.checked_at) + (e.ok === false ? ', failed' : e.ok ? ', passed' : '') : 'never');
      if (e.recorded_at) su.put('Recorded', time(e.recorded_at));
      ins.appendChild(su.dl);
      if (e.problems && e.problems.length) { const ul = h('ul', 'plain'); for (const p of e.problems) ul.appendChild(h('li', 'small warnline', typeof p === 'string' ? p : p.message || JSON.stringify(p))); ins.appendChild(block('What the check found', ul)); }
      const connected = !!e.interpreter;
      ins.appendChild(A.group('envcheck:' + ref, [Object.assign(A.checkItem(ref), { cls: 'btn', hidden: !connected })]));
      if (A.may('owner')) {
        const d = h('div'); d.appendChild(h('h3', null, connected ? 'Connect another interpreter' : 'Connect an interpreter'));
        d.appendChild(h('p', 'note', 'An existing Python on this machine, by its absolute path; Tuldok records it for this project and checks it. Nothing is installed.'));
        const f = h('div', 'form');
        f.appendChild(A.group('envconnect:' + ref, [{ id: 'connect', label: 'Connect', cls: 'btn', who: 'owner', op: 'connect_environment', busy: 'Connecting…',
          input: { name: 'interpreter', label: 'Interpreter (absolute path)', placeholder: '/path/to/python', max: 4096, always: true },
          args: s => ({ reference: ref, interpreter: (s.text.interpreter || '').trim() }) }]));
        d.appendChild(f); ins.appendChild(d);
        if (connected) ins.appendChild(A.group('envdisconnect:' + ref, [{ id: 'disconnect', label: 'Disconnect', cls: 'btn ghost', who: 'owner', op: 'disconnect_environment', args: () => ({ reference: ref }), busy: 'Disconnecting…',
          confirm: 'Forget the interpreter recorded for ' + e.title + ' on this machine; nothing is deleted.' }]));
      }
    });
  }

  S.paint = paint;
  Object.assign(S, { benchmarks, train, data: data_, analysis });
})();
