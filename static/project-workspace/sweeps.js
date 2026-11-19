'use strict';
// The Sweeps tab (docs/plans/training-and-curation/spec-t7.md section 7), added to window.LabScreens: one sweep at a
// time (the chooser, kept in the address as ?sweep=), its state live (the run, the trials by how they ended, the
// budget used, the running trial, the best so far), its controls (Plan sweep, Approve and Decline when a request
// awaits approval, Cancel), its trials through parallel coordinates (parallel.js, the trials as a benchmark's subjects,
// the main view), its frontier with two objectives (charts.js's tradeoff chart) or the progression of its one
// objective, and every trial in a table that opens it in the drawer or on the Map. The drawer holds a trial (the
// model's drawer), the plan view of the sweep, or New sweep: a recipe chosen, a sweep's text written from its
// settings, kept with Keep.
//
// Updating in place (spec-w4): the tab is built once for a sweep and the person's choices (tabs.js's paint). A
// reading of the page (app.js marks the drawer _again, and S.tick while a sweep runs) asks `sweep` again and sets what
// changed in place: the texts and bars of the state block (no node of it added or removed), the cells of the trials'
// rows (a row appended for a new trial), the charts drawn again in their hosts and parallel coordinates in their
// section, the controls when what they offer differs. The tab is never emptied by a reading.
(() => {
  const S = window.LabScreens, P = window.TuldokProject, Tree = window.LabTree, C = window.LabCharts, h = C.h;
  const A = window.LabActions;
  const { sect, failure, putInPlace } = S.parts;
  const fmt = C.fmtSci;
  const TRIAL_TONE = { completed: 'good', running: 'pending', pruned: 'warn', stopped: 'neutral', failed: 'serious' };
  const TRIAL_STATES = ['completed', 'running', 'pruned', 'stopped', 'failed'];
  const RUN_TONE = { running: 'pending', finished: 'good', cancelled: 'neutral', failed: 'serious' };
  const ENDED = { schedule: 'its schedule was done', trials: 'its trials were spent', minutes: 'its minutes were spent', cancelled: 'it was cancelled', failed: 'it failed' };
  const STATE_WORD = { 'not-built': 'not run yet', running: 'running', built: 'finished', failed: 'failed' };
  const REFRESH_MS = 500;   // S.tick asks nothing when the drawing of this reading has just asked
  const button = (cls, text, onClick, key) => { const b = h('button', cls, text); b.type = 'button'; if (key) b.dataset.key = key; if (onClick) b.addEventListener('click', onClick); return b; };
  const shown = v => v === null || v === undefined ? '—' : typeof v === 'number' ? fmt(v) : typeof v === 'string' ? v : JSON.stringify(v);
  const plural = (n, one, many) => n + ' ' + (n === 1 ? one : many || one + 's');
  const minutes = s => s == null ? '—' : s < 90 ? Math.round(s) + ' s' : (s / 60).toFixed(1) + ' min';
  const title = o => o.title || o.metric;
  let live = null;   // the sweep on screen: { reference, main, answer, parts, at, busy }

  // ---- Reading ------------------------------------------------------------------------------------------------------
  const sweepOf = reference => P.call('sweep', { sweep: reference });

  // ---- The screen ---------------------------------------------------------------------------------------------------
  function sweeps(main, aside, state, act, data) {
    const ui = state.ui, sel = state.sel.sweeps || null;
    const again = document.getElementById('aside')._again;
    if (again && live && live.main === main && main._painted === main._view && live.wanted === (ui.sweep || null)) refresh(act);
    else S.paint(main, async () => {
      const list = (await P.read('sweeps')).sweeps;
      const chosen = list.find(s => s.reference === ui.sweep) || list[0] || null;
      return { list, answer: chosen ? await sweepOf(chosen.reference) : null };
    }, (frag, { list, answer }, width) => {
      live = null;
      frag.appendChild(head(list, answer, act, ui));
      if (!answer) { frag.appendChild(h('p', 'empty', 'This project has no sweep yet. A sweep tries settings of a recipe, one trial after another, within a budget: New sweep writes one from a recipe.')); return; }
      live = { reference: answer.reference, wanted: ui.sweep || null, main, answer, width, state, act, data, at: Date.now(), parts: {} };
      build(frag, live);
    });
    return drawer(aside, sel, state, act, data);
  }

  /** The drawer: New sweep, the plan view of the sweep, or a trial (the model's drawer). */
  function drawer(aside, sel, state, act, data) {
    if (!sel) { aside.textContent = ''; aside._for = null; return false; }
    if (sel === 'new') { newSweep(aside, act, data); return true; }
    if (sel.startsWith('plan:')) { A.planView(aside, sel, act.go, () => act.select(null)); return true; }
    if (data.map.byId.has(sel)) { S.inspectorModel(aside, sel, act, data); return true; }
    aside.textContent = ''; aside._for = null; return false;
  }

  /** The chooser, what the sweep is, and New sweep. */
  function head(list, answer, act, ui) {
    const box = h('div', 'sw-head');
    const bar = h('div', 'filters');
    if (list.length) {
      const s = h('select'); s.setAttribute('aria-label', 'Sweep'); s.dataset.key = 'sweep';
      for (const item of list) { const o = h('option', null, item.title + ' · ' + (STATE_WORD[item.state] || item.state)); o.value = item.reference; o.selected = answer && item.reference === answer.reference; s.appendChild(o); }
      s.addEventListener('change', () => act.setUI('sweep', s.value));
      bar.appendChild(s);
    }
    if (A.may('edit')) bar.appendChild(button('btn sm', 'New sweep', () => act.select('new'), 'sweep-new'));
    box.appendChild(bar);
    if (!answer) return box;
    box.appendChild(sect(answer.title, answer.reference));
    const what = h('p', 'small muted sw-what');
    what.appendChild(document.createTextNode('Varies '));
    const link = button('linkish mono', answer.recipe, () => act.go('map', answer.recipe), 'sweep-recipe'); link.title = 'Open the recipe on the Map'; what.appendChild(link);
    what.appendChild(document.createTextNode(': ' + answer.parameters.map(p => p.path + ' ' + rangeWords(p)).join('; ') + '. ' + strategyWords(answer.strategy) + ' Objectives: ' + answer.objectives.map(o => title(o) + ' (' + (o.take === 'best' ? 'best' : 'last') + ', ' + o.better + ' is better)').join(' and ') + '. Budget: ' + plural(answer.budget.trials, 'trial') + (answer.budget.minutes ? ', ' + answer.budget.minutes + ' min' : '') + ', one at a time.'));
    box.appendChild(what);
    if (answer.description) box.appendChild(h('p', 'small faint sw-what', answer.description));
    return box;
  }
  const rangeWords = p => p.values ? 'in ' + p.values.map(shown).join(', ') : 'from ' + fmt(p.low) + ' to ' + fmt(p.high) + (p.scale === 'log' ? ' (log)' : '') + (p.integer ? ', whole numbers' : '') + (p.count ? ', ' + p.count + ' points' : '');
  function strategyWords(s) {
    if (s.kind === 'grid') return 'Every point of the grid, in order.';
    if (s.kind === 'random') return 'Random draws (seed ' + s.seed + ').';
    return 'Random draws (seed ' + s.seed + '), stopping a trial at a rung (' + (s.unit === 'time' ? 'seconds' : 'steps') + ' ' + s.min + ', ×' + (s.factor || 3) + ' after) when its ' + s.metric + ' is not among the best 1/' + (s.factor || 3) + ' there.';
  }

  /** The sweep's sections, into frag; the parts that a reading sets in place are kept in v.parts. */
  function build(frag, v) {
    const a = v.answer;
    const controls = h('div', 'sw-controls'); controls.dataset.key = 'sw-controls'; v.parts.controls = controls; fillControls(v);
    frag.appendChild(controls);
    frag.appendChild(stateBlock(v));
    const pc = h('div', 'sw-pc'); v.parts.pc = pc; frag.appendChild(pc); drawAxes(v);
    const chart = h('section', 'bench-chart sw-chart'); v.parts.chart = chart; frag.appendChild(chart); drawChart(v);
    frag.appendChild(trialTable(v));
    if (window.LabParallel) window.LabParallel.apply(frag, viewOf(a), v.state);
    setState(v);
  }

  // ---- The state, set in place --------------------------------------------------------------------------------------
  function stateBlock(v) {
    const sec = h('section', 'sw-state'); sec.dataset.key = 'sw-state'; sec.setAttribute('aria-live', 'polite');
    sec.appendChild(sect('Where it stands'));
    const dl = h('dl', 'setup sw-dl'), p = v.parts;
    const text = (cls) => { const t = document.createTextNode(''); const dd = h('dd', cls || null); dd.appendChild(t); return [dd, t]; };
    const row = (label, dd) => { dl.appendChild(h('dt', null, label)); dl.appendChild(dd); };
    { const dd = h('dd'); const chip = h('span', 'state neutral sw-chip'); p.chipText = document.createTextNode(''); chip.appendChild(p.chipText); p.chip = chip; dd.appendChild(chip); const t = document.createTextNode(''); p.runText = t; dd.appendChild(h('span', 'small faint sw-gap')).appendChild(t); row('Run', dd); }
    { const [dd, t] = text(); p.counts = t; row('Trials', dd); }
    { const dd = h('dd', 'sw-meter'); const hair = h('span', 'hair'); const i = h('i'); hair.appendChild(i); p.trialsBar = i; dd.appendChild(hair); const t = document.createTextNode(''); p.trialsText = t; dd.appendChild(h('span', 'small')).appendChild(t); row('Budget, trials', dd); }
    { const dd = h('dd', 'sw-meter'); const hair = h('span', 'hair'); const i = h('i'); hair.appendChild(i); p.minutesBar = i; dd.appendChild(hair); const t = document.createTextNode(''); p.minutesText = t; dd.appendChild(h('span', 'small')).appendChild(t); row('Budget, time', dd); }
    { const [dd, t] = text('mono'); p.running = t; row('Running', dd); }
    { const [dd, t] = text(); p.best = t; row('Best so far', dd); }
    sec.appendChild(dl);
    p.state = sec;
    return sec;
  }
  const setText = (node, text) => { if (node.data !== text) node.data = text; };
  function setState(v) {
    const a = v.answer, p = v.parts, run = a.run, counts = run ? run.counts : {};
    const tone = run ? RUN_TONE[run.state] || 'neutral' : 'neutral';
    const cls = 'state sw-chip ' + (tone === 'pending' ? 'warn' : tone);
    if (p.chip.className !== cls) p.chip.className = cls;
    setText(p.chipText, run ? run.state : (a.request ? a.request.state.replace('-', ' ') : 'not run yet'));
    setText(p.runText, run ? ' · started ' + S.parts.time(run.started_at) + (run.finished_at ? ', ended: ' + (ENDED[run.ended] || run.ended) : ' · ' + minutes(run.seconds) + ' so far') + (run.problem ? ' · ' + run.problem : '') + (a.changed ? ' · the sweep has changed since' : '') : a.request ? ' · a build request ' + a.request.state.replace('-', ' ') : ' · ask for a build of the sweep: Plan sweep');
    setText(p.counts, TRIAL_STATES.map(s => (counts[s] || 0) + ' ' + s).join(' · '));
    const used = run ? run.trials : 0, most = a.budget.trials;
    const width = Math.round(100 * Math.min(1, used / Math.max(1, most))) + '%'; if (p.trialsBar.style.width !== width) p.trialsBar.style.width = width;
    setText(p.trialsText, used + ' of ' + most);
    const limit = a.budget.minutes ? a.budget.minutes * 60 : null, spent = run ? run.seconds : 0;
    const mw = limit ? Math.round(100 * Math.min(1, (spent || 0) / limit)) + '%' : '0%'; if (p.minutesBar.style.width !== mw) p.minutesBar.style.width = mw;
    setText(p.minutesText, minutes(spent || 0) + (limit ? ' of ' + minutes(limit) : ', no limit'));
    const now = a.trials.find(t => t.state === 'running');
    setText(p.running, now ? 'Trial ' + now.number + ' · step ' + shown(now.latest && now.latest.step) + a.objectives.map(o => ' · ' + title(o) + ' ' + shown(now.objectives && now.objectives[o.metric])).join('') : '—');
    setText(p.best, a.best ? 'Trial ' + a.best.number + ' · ' + title(a.objectives[0]) + ' ' + fmt(a.best.value) : '—');
  }

  // ---- Controls -----------------------------------------------------------------------------------------------------
  function fillControls(v) {
    const a = v.answer, r = a.request, waiting = r && r.state === 'awaiting-approval', active = r && ['awaiting-approval', 'queued', 'running'].includes(r.state);
    const key = JSON.stringify([a.reference, a.state, r && r.id, r && r.state, A.may('owner'), A.may('request'), A.may('cancel')]);
    const box = v.parts.controls;
    if (box._key === key) return;
    box._key = key;
    const items = [{ id: 'plan', label: 'Plan sweep', cls: 'btn' + (active ? '' : ' primary'), who: 'request', onClick: () => v.act.select('plan:' + a.reference), hidden: !!active }];
    if (r) {
      items.push({ id: 'approve', label: 'Approve', cls: 'btn primary', who: 'owner', op: 'approve_build', args: () => ({ request: r.id }), busy: 'Approving…', hidden: !waiting });
      items.push(Object.assign(A.declineItem(r.id), { cls: 'btn', hidden: !waiting }));
      items.push({ id: 'cancel', label: 'Cancel', cls: 'btn ghost', who: 'cancel', op: 'cancel_build', args: () => ({ request: r.id }), busy: 'Cancelling…', hidden: !active,
        confirm: r.state === 'running' ? 'Cancel the sweep: the running trial is stopped and no other starts.' : 'Cancel this request; no trial runs.' });
    }
    const frag = document.createDocumentFragment();
    if (waiting) frag.appendChild(h('p', 'note sw-ask', (r.requested_by && (r.requested_by.label || r.requested_by.kind) || 'Someone') + ' asks for this sweep. One approval covers its whole budget: up to ' + plural(a.budget.trials, 'trial') + (a.budget.minutes ? ' and ' + a.budget.minutes + ' min' : '') + ', one after another.'));
    frag.appendChild(A.group('sweep:' + a.reference + ':' + (r ? r.id : ''), items, { inline: true }));
    if (box.isConnected) putInPlace(box, frag, document.getElementById('main')); else box.replaceChildren(frag);
  }

  // ---- Parallel coordinates and the chart ---------------------------------------------------------------------------
  /** The trials as parallel.js and its apply() see a benchmark's subjects: by reference, coloured by their state. */
  function viewOf(a) {
    const byName = new Map();
    for (const t of a.trials) byName.set(t.reference, { name: t.reference, key: t.reference, full: 'Trial ' + t.number, kind: 'tr-' + t.state });
    return { name: 'sweep:' + a.reference, byName, byKey: byName, selected: null, noun: 'trials', lead: 'One line per trial through the settings it was given and its objectives (the colour is how it ended). Drag along an axis to keep the trials inside a range; the table below follows.' };
  }
  function drawAxes(v) {
    const a = v.answer, host = v.parts.pc;
    host._key = JSON.stringify(a.axes);
    if (!window.LabParallel || !a.axes || a.trials.length < 2) { host.replaceChildren(h('p', 'empty', a.trials.length ? 'Parallel coordinates are drawn from two trials on.' : 'No trial yet: its trials are drawn here as lines through their settings and objectives.')); return; }
    const data = Object.assign({}, a.axes, { benchmark: 'sweep:' + a.reference, statistic: 'value' });
    const view = viewOf(a);
    host.replaceChildren(window.LabParallel.section(data, view, v.state, v.act, v.width));
  }
  function drawChart(v) {
    const a = v.answer, host = v.parts.chart, done = a.trials.filter(t => t.state === 'completed');
    host._key = JSON.stringify([a.objectives, done.map(t => [t.number, t.objectives]), a.frontier]);
    host.dataset.chart = 'sweep';
    const [y, x] = a.objectives;
    const parts = [];
    if (x) parts.push(sect(title(y) + ' against ' + title(x), done.length + ' completed trials · ' + a.frontier.length + ' on the frontier'));
    else parts.push(sect(title(y) + ' by trial', done.length + ' completed trials, the best so far as a step line'));
    const draw = h('div');
    const valued = done.filter(t => t.objectives && t.objectives[y.metric] != null && (!x || t.objectives[x.metric] != null));
    if (!valued.length) parts.push(h('p', 'empty', 'No completed trial has its objectives yet.'));
    else {
      parts.push(draw);
      const front = new Set(a.frontier);
      const rows = t => () => [{ b: 'Trial ' + t.number }].concat(a.objectives.map(o => ({ v: fmt(t.objectives[o.metric]), l: title(o) }))).concat(Object.entries(t.values).map(([k, val]) => ({ v: shown(val), l: k })));
      const select = id => v.act.select(v.state.sel.sweeps === id ? null : id);
      if (x) {
        C.scatter(draw, valued.map(t => ({ id: t.reference, name: 'Trial ' + t.number, short: 'T' + t.number, kind: 'sweep-trial', x: t.objectives[x.metric], y: t.objectives[y.metric], frontier: front.has(t.number), rows: rows(t) })),
          { width: v.width, height: 320, xTitle: title(x), yTitle: title(y), xName: title(x), yName: title(y), xBetter: x.better, yBetter: y.better, selected: v.state.sel.sweeps, onSelect: select });
        parts.push(h('p', 'small faint', 'Line: the frontier of the completed trials, where no other is at least as good on both and better on one. Pruned and stopped trials are left out: they did not finish.'));
      } else {
        let best = null;
        C.progression(draw, valued.map(t => { const val = t.objectives[y.metric]; if (best === null || (y.better === 'higher' ? val > best : val < best)) best = val; return { id: t.reference, name: 'Trial ' + t.number, short: 'T' + t.number, kind: 'sweep-trial', y: val, best, rows: rows(t) }; }),
          { width: v.width, height: 240, yTitle: title(y), selected: v.state.sel.sweeps, onSelect: select });
      }
    }
    if (host.isConnected) { const frag = document.createDocumentFragment(); frag.append(...parts); putInPlace(host, frag, document.getElementById('main')); }
    else host.replaceChildren(...parts);
  }

  // ---- The trials ---------------------------------------------------------------------------------------------------
  function trialTable(v) {
    const a = v.answer, sec = h('section', 'bench-all sw-trials');
    sec.appendChild(sect('Trials', plural(a.trials.length, 'trial') + (a.run ? ' of this run' : '')));
    const t = h('table', 'tv sw-table'); t.setAttribute('aria-label', 'The trials of ' + a.title);
    const thead = h('thead'), tr = h('tr');
    for (const [label, cls] of [['#', 'n']].concat(a.parameters.map(p => [p.path, 'n mono']), [['State'], ['Rung']], a.objectives.map(o => [title(o), 'n']), [['Time', 'n'], ['']])) tr.appendChild(h('th', cls || null, label));
    thead.appendChild(tr); t.appendChild(thead);
    const tb = h('tbody'); v.parts.rows = new Map(); v.parts.tbody = tb;
    for (const trial of a.trials) tb.appendChild(trialRow(v, trial));
    t.appendChild(tb);
    const wrap = h('div', 'tv-wrap'); wrap.appendChild(t); sec.appendChild(wrap);
    if (!a.trials.length) sec.appendChild(h('p', 'note', a.run ? 'No trial has started yet.' : 'No trial yet.'));
    return sec;
  }
  function trialRow(v, trial) {
    const a = v.answer, tr = h('tr'); tr.dataset.subject = trial.reference; tr.dataset.trial = String(trial.number);
    const cells = { values: [], objectives: [] };
    const td = (cls, text) => { const c = h('td', cls || null); const t = document.createTextNode(text); c.appendChild(t); tr.appendChild(c); return t; };
    td('n', String(trial.number));
    for (const p of a.parameters) cells.values.push(td('n mono', shown(trial.values[p.path])));
    const st = h('td'); const chip = h('span', 'state'); const chipText = document.createTextNode(''); chip.appendChild(chipText); st.appendChild(chip); tr.appendChild(st);
    cells.chip = chip; cells.chipText = chipText;
    cells.rung = td('small');
    for (const o of a.objectives) cells.objectives.push(td('n'));
    cells.seconds = td('n small');
    const act = h('td', 'nowrap');
    const open = button('btn sm ghost', 'Open on the Map', ev => { ev.stopPropagation(); v.act.go('map', trial.reference); }, 'sweep-map-' + trial.number); open.disabled = !trial.defined; act.appendChild(open); tr.appendChild(act);
    tr.tabIndex = 0; tr.classList.add('sw-row');
    tr.addEventListener('click', () => v.act.select(v.state.sel.sweeps === trial.reference ? null : trial.reference));
    tr.addEventListener('keydown', ev => { if (ev.key === 'Enter' && ev.target === tr) v.act.select(trial.reference); });
    v.parts.rows.set(trial.number, { tr, cells, open });
    setRow(v, trial);
    return tr;
  }
  function setRow(v, trial) {
    const { tr, cells, open } = v.parts.rows.get(trial.number), a = v.answer;
    const tone = TRIAL_TONE[trial.state] || 'neutral', cls = 'state ' + (tone === 'pending' ? 'warn' : tone);
    if (cells.chip.className !== cls) cells.chip.className = cls;
    setText(cells.chipText, trial.state + (trial.reused ? ' (built before)' : ''));
    const last = (trial.rungs || []).slice(-1)[0];
    setText(cells.rung, last ? 'rung ' + (last.rung + 1) + (last.goes_on ? '' : ', stopped there') : '');
    a.objectives.forEach((o, i) => setText(cells.objectives[i], shown(trial.objectives && trial.objectives[o.metric])));
    setText(cells.seconds, trial.seconds == null ? (trial.state === 'running' && trial.latest ? 'step ' + trial.latest.step : '') : minutes(trial.seconds));
    if (open.disabled !== !trial.defined) open.disabled = !trial.defined;
    if (trial.problem && tr.title !== trial.problem) tr.title = trial.problem;
    const on = v.state.sel.sweeps === trial.reference; if (tr.classList.contains('on') !== on) tr.classList.toggle('on', on);
  }

  // ---- A reading: everything set in place ---------------------------------------------------------------------------
  async function refresh(act) {
    const v = live;
    if (!v || !v.main.isConnected || v.busy) return;
    v.busy = true;
    try {
      const answer = await sweepOf(v.reference);
      if (live !== v) return;
      v.at = Date.now(); v.answer = answer;
      if (act) v.act = act;
      setState(v); fillControls(v);
      const option = v.main.querySelector('select[data-key="sweep"] option:checked'), word = option && option.textContent.replace(/ · [^·]*$/, ' · ' + (STATE_WORD[answer.state] || answer.state));
      if (option && option.textContent !== word) option.textContent = word;
      for (const trial of answer.trials) { if (v.parts.rows.has(trial.number)) setRow(v, trial); else v.parts.tbody.appendChild(trialRow(v, trial)); }
      if (v.parts.pc._key !== JSON.stringify(answer.axes)) drawAxes(v);
      const done = answer.trials.filter(t => t.state === 'completed');
      if (v.parts.chart._key !== JSON.stringify([answer.objectives, done.map(t => [t.number, t.objectives]), answer.frontier])) drawChart(v);
      if (window.LabParallel) window.LabParallel.apply(v.main, viewOf(answer), v.state);
    } catch (error) { /* the strip says when the project could not be read; what is on screen stays */ }
    finally { v.busy = false; }
  }
  // Every reading of the page (app.js calls S.tick after drawing): the sweep on screen, while it runs or is asked for.
  const before = S.tick;
  S.tick = async () => {
    if (before) await before();
    const v = live;
    if (v && v.main.isConnected && Date.now() - v.at >= REFRESH_MS && document.location.hash.startsWith('#sweeps') && (v.answer.state === 'running' || (v.answer.request && ['awaiting-approval', 'queued', 'running'].includes(v.answer.request.state)))) await refresh();
  };

  // ---- New sweep ----------------------------------------------------------------------------------------------------
  const drafting = { recipe: null, name: '', text: '', touched: false };
  /** A sweep's text from a recipe's settings: its numeric ones as ranges about their values, random draws, eight trials. */
  function template(reference, doc, name) {
    const settings = doc.run && doc.run.settings && typeof doc.run.settings === 'object' ? doc.run.settings : {};
    const parameters = [];
    for (const [k, val] of Object.entries(settings)) {
      if (parameters.length >= 4) break;
      if (typeof val === 'number' && Number.isInteger(val) && val >= 1) parameters.push({ path: k, low: Math.max(1, Math.floor(val / 2)), high: val * 2, integer: true });
      else if (typeof val === 'number' && val > 0) parameters.push({ path: k, low: +(val / 10).toPrecision(6), high: +(val * 10).toPrecision(6), scale: 'log' });
      else if (typeof val === 'boolean') parameters.push({ path: k, values: [true, false] });
    }
    return JSON.stringify({ format: 'tuldok_definition_v1', kind: 'sweep', title: 'A search over ' + (doc.title || reference),
      recipe: reference, parameters: parameters.length ? parameters : [{ path: 'learning_rate', low: 0.0001, high: 0.01, scale: 'log' }],
      strategy: { kind: 'random', seed: 1 }, objectives: [{ metric: 'loss', better: 'lower' }], budget: { trials: 8 } }, null, 2) + '\n';
  }
  function newSweep(aside, act, data) {
    if (aside._for === 'new' && !aside._again) return;
    const recipes = data.map.models.filter(m => m.kind !== 'sweep-trial' && !m.draft);
    if (!drafting.recipe || !recipes.some(m => m.id === drafting.recipe)) { drafting.recipe = recipes.length ? recipes[0].id : null; drafting.touched = false; }
    aside._for = 'new';
    const ins = h('div', 'inspector sw-new');
    const hd = h('header'); hd.appendChild(h('span', 'kicker', 'new sweep · kept as an unsaved edit')); const t = h('h2', null, 'A sweep of a recipe\'s settings'); t.tabIndex = -1; hd.appendChild(t); ins.appendChild(hd);
    ins.appendChild(h('p', 'note', 'Choose the recipe; the text is written from its settings. Change the parameters, the objectives (the series its script logs) and the budget, then Keep. A recipe whose settings are in a file is branched first: Branch from here gives the branch its own copy.'));
    const f = h('div', 'form');
    const lab = h('label', null, 'Recipe'); const s = h('select'); s.dataset.key = 'sweep-new-recipe';
    for (const m of recipes) { const o = h('option', null, Tree.nameOf(m) + ' · ' + m.id); o.value = m.id; o.selected = m.id === drafting.recipe; s.appendChild(o); }
    lab.appendChild(s); f.appendChild(lab);
    const nl = h('label', null, 'Name'); const name = h('input'); name.dataset.key = 'sweep-new-name'; name.value = drafting.name; name.placeholder = 'lowercase letters, digits, . _ -'; nl.appendChild(name); f.appendChild(nl);
    const tl = h('label', null, 'Text'); const area = h('textarea', 'mono sw-text'); area.dataset.key = 'sweep-new-text'; area.rows = 18; area.spellcheck = false; area.value = drafting.text; tl.appendChild(area); f.appendChild(tl);
    ins.appendChild(f);
    const fill = async () => {
      if (!drafting.recipe) return;
      const def = await P.read('definition', { reference: drafting.recipe });
      if (!drafting.name || !drafting.touchedName) { drafting.name = drafting.recipe.slice(8, 100) + '-sweep'; name.value = drafting.name; }
      drafting.text = template(drafting.recipe, def.document || {}, drafting.name); area.value = drafting.text; drafting.touched = false;
    };
    s.addEventListener('change', () => { drafting.recipe = s.value; fill(); });
    name.addEventListener('input', () => { drafting.name = name.value; drafting.touchedName = true; });
    area.addEventListener('input', () => { drafting.text = area.value; drafting.touched = true; });
    ins.appendChild(A.group('sweep:new', [{ id: 'keep', label: 'Keep', cls: 'btn primary', who: 'edit', op: 'set_definition', busy: 'Keeping…',
      args: () => ({ reference: 'sweeps/' + drafting.name.trim(), text: drafting.text }),
      done: r => { const ref = r.reference; drafting.text = ''; drafting.name = ''; drafting.touched = false; drafting.touchedName = false; act.setUI('sweep', ref); act.select(null); } }]));
    if (!drafting.text) fill().catch(error => failure(ins, error));
    S.parts.putDrawer(aside, ins);
  }

  S.sweeps = sweeps;
})();
