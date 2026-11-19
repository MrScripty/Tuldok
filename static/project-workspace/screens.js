'use strict';
// The screens, from the mockup's screens.js. A screen is one function
// (main, aside, state, act, data) that fills the main area, fills the drawer when it
// has something to show there, and returns whether the drawer is open. It
// reads the project only through window.TuldokProject. Rule: the chrome holds
// no project words; names, groups, metrics and text come from the project.
// What is drawn again is built off the page and put in place whole, in one
// step, keeping the scroll and the focus (putInPlace, spec-w4.md); the map
// keeps its tree while its answer is unchanged, and keeps its place when
// rebuilt. The editor, the branch form, a draft's drawer, the steps of a new model and
// the Overview's list of every definition are editor.js's (window.LabEditor).
window.LabScreens = (() => {
  const P = window.TuldokProject, Tree = window.LabTree, C = window.LabCharts, h = C.h;
  const svgNS = 'http://www.w3.org/2000/svg';
  const ICONS = {
    check: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm-1.3 14.2-3.6-3.6 1.4-1.4 2.2 2.2 5.1-5.1 1.4 1.4z',
    alert: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm-1 5h2v6h-2zm0 8h2v2h-2z',
    triangle: 'M12 3 1 21h22zm-1 7h2v5h-2zm0 7h2v2h-2z',
    minus: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm-5 9h10v2H7z',
    branch: 'M7 3a3 3 0 0 0-1 5.8v6.4A3 3 0 1 0 8 15.2V9.9c1.2 1.3 2.9 2.1 5 2.1 2.8 0 4.4-1.5 5-4.1A3 3 0 1 0 16 7.6c-.5 1.6-1.4 2.4-3 2.4-2.6 0-4.3-1.6-5-3.2A3 3 0 0 0 7 3z',
    clock: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm1 5h-2v6l5 3 1-1.7-4-2.3z',
    x: 'M18.3 5.7 12 12l6.3 6.3-1.4 1.4L10.6 13.4 4.3 19.7 2.9 18.3 9.2 12 2.9 5.7l1.4-1.4 6.3 6.3 6.3-6.3z',
    theme: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zm0 2v14a7 7 0 0 1 0-14z'
  };
  const icon = name => { const s = document.createElementNS(svgNS, 'svg'); s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('aria-hidden', 'true'); const p = document.createElementNS(svgNS, 'path'); p.setAttribute('d', ICONS[name] || ICONS.minus); p.setAttribute('fill', 'currentColor'); p.setAttribute('fill-rule', 'evenodd'); s.appendChild(p); return s; };
  const stateEl = (kind, text) => { const map = { good: 'check', warn: 'alert', serious: 'triangle', neutral: 'minus', pending: 'clock' }; const s = h('span', 'state ' + (kind === 'pending' ? 'warn' : kind)); s.appendChild(icon(map[kind] || 'minus')); s.appendChild(document.createTextNode(text)); return s; };
  const modelState = s => { const [word, tone] = P.stateWord(s); return stateEl(tone, word); };
  const sect = (title, sum) => { const d = h('div', 'sect'); d.appendChild(h('h2', null, title)); if (sum !== undefined) d.appendChild(h('span', 'sum', sum)); return d; };
  const cell = (k, v, u) => { const d = h('div'); d.appendChild(h('dt', null, k)); const dd = h('dd', null, v); if (u) dd.appendChild(h('small', null, u)); d.appendChild(dd); return d; };
  const block = (title, ...children) => { const d = h('div'); d.appendChild(h('h3', null, title)); for (const c of children) if (c) d.appendChild(c); return d; };
  const time = iso => iso ? new Date(iso).toLocaleString('en-GB', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';
  const bytes = b => b == null ? '—' : b >= 1e9 ? (b / 1e9).toFixed(1) + ' GB' : b >= 1e6 ? (b / 1e6).toFixed(1) + ' MB' : b >= 1e3 ? Math.round(b / 1e3) + ' KB' : b + ' B';
  const failure = (parent, error) => { parent.appendChild(h('p', 'failure', error.message || String(error))); };
  // ---- Putting in place (spec-w4 R4) ------------------------------------------
  /** Every element under root that is scrolled, by its path of child indexes and its tag. */
  function scrolls(root) {
    const out = [];
    const walk = (el, path) => { for (let i = 0; i < el.children.length; i++) { const c = el.children[i], p = path.concat([i]); if (c.scrollTop || c.scrollLeft) out.push({ path: p, tag: c.tagName, top: c.scrollTop, left: c.scrollLeft }); walk(c, p); } };
    walk(root, []); return out;
  }
  /**
   * Puts content, built off the page, in box in one step in place of what it
   * holds, keeping the scroll of scroller (box unless named) in both
   * directions, the scroll of every scrolled element inside box (the same
   * path and tag), and the focused control (by data-key) with its caret.
   * Returns whether the focus was inside and whether its control was found.
   */
  function putInPlace(box, content, scroller = box) {
    const active = document.activeElement, inside = !!active && box.contains(active), key = inside && active.dataset ? active.dataset.key : null;
    let caret = null; try { caret = key && typeof active.selectionStart === 'number' ? [active.selectionStart, active.selectionEnd, active.scrollTop] : null; } catch (e) { caret = null; }
    const top = scroller.scrollTop, left = scroller.scrollLeft, inner = scrolls(box);
    box.replaceChildren(content);
    scroller.scrollTop = top; scroller.scrollLeft = left;
    for (const s of inner) { let e = box; for (const i of s.path) { e = e.children[i]; if (!e) break; } if (e && e.tagName === s.tag) { e.scrollTop = s.top; e.scrollLeft = s.left; } }
    const again = key && [...box.querySelectorAll('[data-key]')].find(e => e.dataset.key === key);
    if (again) { again.focus({ preventScroll: true }); if (caret && again.setSelectionRange) { try { again.setSelectionRange(caret[0], caret[1]); } catch (e) { /* not a text field */ } again.scrollTop = caret[2]; } }
    return { inside, found: !!again };
  }
  /** Puts a drawer's content in place (the drawer's own scroll kept); when the focused control is gone, the heading takes the focus. */
  function putDrawer(aside, content) {
    const r = putInPlace(aside, content, aside.parentElement);
    if (r.inside && !r.found) { const t = aside.querySelector('h2'); if (t) t.focus({ preventScroll: true }); }
  }
  /** A new turn of the drawer: a read started for an older turn puts nothing in it. */
  const turn = aside => (aside._turn = (aside._turn || 0) + 1);

  const NEEDS_ICON = { approval: 'clock', changed: 'alert', missing: 'triangle' };
  /** What needs the person, one sentence each; controls(item) gives the controls drawn under a sentence. */
  function needsList(items, controls) {
    const ul = h('ul', 'needs');
    if (!items.length) { ul.appendChild(h('li', 'empty', 'Nothing needs you.')); return ul; }
    for (const n of items) {
      const li = h('li', n.kind); li.appendChild(icon(NEEDS_ICON[n.kind]));
      const body = h('div', 'need'); body.appendChild(h('span', null, n.text));
      const c = controls ? controls(n) : null; if (c) body.appendChild(c);
      li.appendChild(body); ul.appendChild(li);
    }
    return ul;
  }

  // ---- Map -----------------------------------------------------------------
  let graph = null, graphOf = null;
  function graphFor(shaped) { if (graphOf !== shaped) { graph = Tree.build(shaped); graphOf = shaped; } return graph; }
  function map(main, aside, state, act, data) {
    // A selection 'plan:<targets>' is the plan view in the drawer, with its first target selected on the map;
    // 'edit:<reference>' and 'branch:<reference>' are the editor and the branch form (editor.js), with that model selected.
    const shaped = data.map, g = graphFor(shaped), raw = state.sel.map || '', planSel = raw.startsWith('plan:') ? raw : null, E = window.LabEditor;
    const focus = planSel ? planSel.slice(5).split(',')[0] : E ? E.subject(raw) : raw, sel = focus && g.byId.has(focus) ? focus : null;
    const kinds = P.KINDS.map(k => k.id).concat(g.nodes.some(m => m.kind === P.UNSET) ? [P.UNSET] : []);
    const withValue = g.nodes.filter(m => m.value != null).length;
    const buildBar = () => {
      const bar = h('div', 'filters');
      const q = h('input'); q.type = 'search'; q.placeholder = 'Find a model'; q.value = state.query || ''; q.setAttribute('aria-label', 'Find a model'); q.addEventListener('input', () => act.setQuery(q.value)); bar.appendChild(q);
      const grp = h('div', 'grp'); grp.setAttribute('role', 'group'); grp.setAttribute('aria-label', 'Kind of change');
      for (const k of kinds) { const b = h('button', 'btn sm chip ' + k, P.kindLabel(k)); b.type = 'button'; b.dataset.kind = k; b.setAttribute('aria-pressed', String(!state.kinds || state.kinds.has(k))); b.addEventListener('click', () => act.toggleKind(k, kinds)); grp.appendChild(b); }
      bar.appendChild(grp);
      if (g.track) { const tb = h('button', 'btn sm', 'Accuracy track'); tb.type = 'button'; tb.title = P.trackName(g.track) + ', ' + P.better(g.track); tb.setAttribute('aria-pressed', String(!!state.track)); tb.addEventListener('click', () => act.toggleTrack()); bar.appendChild(tb); }
      const z = h('div', 'zoomctl'); for (const [t, d, l] of [['−', -0.2, 'Zoom out'], ['+', 0.2, 'Zoom in']]) { const b = h('button', 'btn sm', t); b.type = 'button'; b.setAttribute('aria-label', l); b.addEventListener('click', () => act.zoom(d)); z.appendChild(b); } bar.appendChild(z);
      bar.appendChild(h('span', 'pop', g.nodes.length + ' models · ' + (g.track ? withValue + ' on the track' : 'no track')));
      return bar;
    };
    if (!g.nodes.length) { main.textContent = ''; main._tree = null; main.appendChild(h('p', 'empty', 'This project has no recipes, so there are no models to map.')); aside.textContent = ''; return false; }
    const sig = JSON.stringify([state.kinds ? [...state.kinds] : null, state.query || '', state.zoom || 1, !!state.track]);
    const prev = main._tree;
    // While a parent is being picked (editor.js), the next model pressed is the parent instead.
    const common = { onSelect: id => { if (!(E && E.picked(id, act))) act.select(id); }, kinds: state.kinds, query: state.query };
    if (prev && prev.sig === sig && prev.shaped === shaped && main.contains(prev.bar)) {
      // The same tree: only a new selection is drawn (spec-w4 R2, R6).
      if (sel !== prev.sel) { if (sel) { prev.map.scrollTo(sel, true); prev.list.scrollTo(sel, true); } prev.map.select(sel); prev.list.select(sel); prev.sel = sel; }
    } else {
      const focused = prev && prev.bar && prev.bar.contains(document.activeElement) && document.activeElement.type === 'search' ? document.activeElement.selectionStart : null;
      // A changed map (the same filters) is rebuilt where it was: the scroll of the map and of the list kept (R6).
      const place = prev && prev.sig === sig && main.contains(prev.bar) ? [main.querySelector('.tree-map'), main.querySelector('.tree-host')].map(e => e ? [e.scrollLeft, e.scrollTop] : null) : null;
      main.textContent = ''; const bar = buildBar(); main.appendChild(bar);
      const mh = h('div', 'tree-map'); main.appendChild(mh);
      const inst = { sig, bar, sel, shaped, map: null, list: null };
      inst.map = Tree.renderMap(mh, g, Object.assign({ selected: sel, zoom: state.zoom || 1, track: !!state.track }, common));
      const lh = h('div', 'tree-host'); main.appendChild(lh); inst.list = Tree.renderList(lh, g, Object.assign({ selected: sel }, common));
      if (place) { for (const [e, at] of [[mh, place[0]], [lh, place[1]]]) if (at) { e.scrollLeft = at[0]; e.scrollTop = at[1]; } }
      else if (sel) { inst.map.scrollTo(sel, false); inst.list.scrollTo(sel, false); }
      if (focused !== null) { const q = bar.querySelector('input[type="search"]'); q.focus(); q.setSelectionRange(focused, focused); }
      main._tree = inst;
    }
    if (E) E.decorate(main);
    if (planSel) { window.LabActions.planView(aside, planSel, act.go, sel ? () => act.select(sel) : null); return true; }
    if (E && E.owns(raw, data)) { E.drawer(aside, raw, act, data, 'map'); return true; }
    if (sel) {
      // Compare (spec-t3 section 5.1): the model into the page's compare set, kept current on every render (tabs.js).
      const more = window.LabScreens.compareActs ? ins => window.LabScreens.compareActs(ins, sel, state, act, 'map') : undefined;
      inspectorModel(aside, sel, act, data, more);
      const ins = aside.querySelector('.inspector'); if (ins && more) more(ins);
      return true;
    }
    aside.textContent = ''; aside._for = null; return false;
  }

  // ---- Drawer: one model ---------------------------------------------------
  const TO_BUILD = ['not-built', 'out-of-date', 'failed'];
  /**
   * The drawer of one model: its header, controls and lineage at once, and
   * four blocks filled as their reads arrive (Results, Runs and product, Uses,
   * Card; and the steps of a new model). Read again for the model on screen
   * (aside._again), the new drawer is built off the page and put in place in
   * one step once every block is filled. more(ins): added by the caller to
   * each drawing (the Benchmarks tab's Compare).
   */
  function inspectorModel(aside, id, act, data, more) {
    const E = window.LabEditor, A = window.LabActions;
    if (E && E.isDraft(id)) return E.drawer(aside, id, act, data, 'map');   // a draft's drawer is the editor
    if (aside._for === id && !aside._again) return;
    const same = aside._for === id && !!aside.firstChild, mine = turn(aside);
    aside._for = id; if (!same) aside.textContent = '';
    const live = () => aside._turn === mine && aside._for === id, reads = [];
    const g = graphFor(data.map), m = g.byId.get(id);
    const ins = h('div', 'inspector');
    const hd = h('header');
    hd.appendChild(h('span', 'kicker', (m.short ? m.short + ' · ' : '') + (m.groupTitle || '')));
    const t = h('h2', null, m.title); t.tabIndex = -1; hd.appendChild(t);
    const meta = h('div', 'ins-meta'); meta.appendChild(h('span', 'chip ' + m.kind, P.kindLabel(m.kind))); meta.appendChild(modelState(m.state));
    meta.appendChild(h('span', 'small faint', m.trainedAt ? 'trained ' + P.day(m.trainedAt) : m.planned ? 'never built' : 'no training date'));
    meta.appendChild(Tree.mark(m));
    hd.appendChild(meta); ins.appendChild(hd);
    if (E) E.decorate(hd);
    // Plan build, for a model to build (spec-w3 section 3.1): the plan view, never a request from here. A model
    // never built that is not earlier work has the steps of a new model instead (editor.js), whose next step it is.
    const planGroup = () => A.group('model:' + m.id, [{ id: 'plan', label: 'Plan build', cls: 'btn primary', who: 'request', onClick: () => act.select('plan:' + m.id) }]);
    if (E && E.followsSteps(m)) { const box = h('div', 'steps-box'); box.appendChild(h('p', 'note', 'Reading…')); ins.appendChild(box); reads.push(E.steps(box, m, act, data, planGroup)); }
    else if (TO_BUILD.includes(m.state)) ins.appendChild(planGroup());
    // Edit and Branch from here (spec-w3 section 3.2), for a session that may edit.
    ins.appendChild(A.group('modelact:' + m.id, [
      { id: 'edit', label: 'Edit', cls: 'btn sm', who: 'edit', onClick: () => act.go('map', 'edit:' + m.id) },
      { id: 'branch', label: 'Branch from here', cls: 'btn sm', who: 'edit', onClick: () => act.go('map', 'branch:' + m.id) }
    ], { inline: true }));
    // Lineage: what it was derived from, what derives from it, what it takes as input.
    const lin = h('div', 'actions');
    const jump = (target, text) => { const b = h('button', 'btn sm ghost'); b.type = 'button'; b.appendChild(icon('branch')); b.appendChild(document.createTextNode(' ' + text)); b.addEventListener('click', () => act.select(target.id)); return b; };
    if (m.parent) lin.appendChild(jump(g.byId.get(m.parent), 'From ' + Tree.refName(g.byId.get(m.parent))));
    else lin.appendChild(h('span', 'small faint', 'No recorded ancestry'));
    const kids = g.nodes.filter(n => n.parent === m.id);
    if (kids.length === 1) lin.appendChild(jump(kids[0], Tree.refName(kids[0]) + ' derives from it'));
    else if (kids.length) { const b = h('button', 'btn sm ghost', kids.length + ' models derive from it'); b.type = 'button'; b.addEventListener('click', () => act.select(kids[0].id)); lin.appendChild(b); }
    ins.appendChild(lin);
    const uses = g.edges.filter(e => e.kind === 'input' && e.to === m.id).map(e => g.byId.get(e.from));
    const usedBy = g.edges.filter(e => e.kind === 'input' && e.from === m.id).map(e => g.byId.get(e.to));
    for (const [title, list] of [['Takes as input', uses], ['Is an input of', usedBy]]) if (list.length) {
      const ul = h('ul', 'links'); for (const o of list) { const li = h('li'); const b = h('button'); b.type = 'button'; b.textContent = Tree.nameOf(o); b.addEventListener('click', () => act.select(o.id)); li.appendChild(b); ul.appendChild(li); }
      ins.appendChild(block(title, ul));
    }
    // The track value.
    const dl = h('dl', 'metrics');
    if (g.track) dl.appendChild(cell(g.track.metric.title, m.value == null ? '—' : C.fmtSci(m.value), m.value == null ? '' : P.units(g.track).trim()));
    dl.appendChild(cell('Cases', m.count == null ? '—' : m.count.toLocaleString('en-GB')));
    dl.appendChild(cell('Benchmarks with results', String(m.benchmarks)));
    dl.appendChild(cell('State', P.stateWord(m.state)[0] + (m.adopted ? ', adopted' : '')));
    ins.appendChild(dl);
    ins.appendChild(h('p', 'note', g.track ? (m.value == null ? 'No result on ' + g.track.benchmark + ' for this model.' : 'The ' + g.track.statistic + ' over ' + m.count + ' cases of ' + g.track.benchmark + ', ' + P.better(g.track) + '.') : 'The project names no track for the map.'));
    if (m.description) ins.appendChild(block('Description', h('p', null, m.description)));
    const cmp = Tree.comparisons(g, m.id);
    if (cmp.length) {
      const ul = h('ul', 'links');
      for (const c of cmp) { const o = g.byId.get(c.other); const li = h('li'); const b = h('button'); b.type = 'button'; b.appendChild(document.createTextNode(Tree.nameOf(o))); const said = c.excerpt || c.explanation || ''; b.appendChild(h('span', 'why', said.slice(0, 140) + (said.length > 140 ? '…' : ''))); b.title = c.explanation || ''; b.addEventListener('click', () => act.select(o.id)); li.appendChild(b); ul.appendChild(li); }
      ins.appendChild(block('Compared with', ul));
    }
    // What is read when the model is opened.
    const results = block('Results'), runs = block('Runs and product'), uses2 = block('Uses'), card = block('Card');
    for (const b of [results, runs, uses2, card]) { b.appendChild(h('p', 'note', 'Reading…')); ins.appendChild(b); }
    // Weights (weights.js, spec-d2 section 4), after Runs and product: shown only when the model has a current product with a weights file.
    if (window.LabWeights) {
      const wts = h('div', 'wts-box'); wts.hidden = true; ins.insertBefore(wts, uses2);
      reads.push(window.LabWeights.block(wts, m, g, aside.parentElement, live).catch(error => { if (!live()) return; wts.hidden = false; wts.replaceChildren(h('h3', null, 'Weights'), A.refusal(error)); }));
    }
    // Structure (structure.js, spec-t2 section 4), after Weights: shown only when a current product holds model-graph.json.
    if (window.LabStructure) {
      const stb = h('div', 'st-box'); stb.hidden = true; ins.insertBefore(stb, uses2);
      reads.push(window.LabStructure.block(stb, m, g, aside.parentElement, live).catch(error => { if (!live()) return; stb.hidden = false; stb.replaceChildren(h('h3', null, 'Structure'), A.refusal(error)); }));
    }
    if (more) more(ins);
    if (!same) aside.appendChild(ins);   // first shown: at once, its blocks filled as they come
    const fill = (b, build) => p => { if (!live()) return; b.lastChild.remove(); try { build(b, p); } catch (error) { failure(b, error); } };
    const fail = b => error => { if (!live()) return; b.lastChild.remove(); failure(b, error); };
    reads.push(Promise.all([P.read('recipe_results', { recipe: m.id }), P.read('definitions', { kind: 'benchmark' }).catch(() => ({ definitions: [] }))])
      .then(fill(results, (b, [found, defs]) => {
        if (!found.rows.length) { b.appendChild(h('p', 'empty', found.benchmarks.length ? 'Named in ' + found.benchmarks.length + ' benchmarks, with no results yet.' : 'No benchmark measures this model.')); return; }
        const titles = new Map(defs.definitions.map(d => [d.reference.split('/').slice(1).join('/'), d.title]));
        const byBench = new Map(); for (const r of found.rows) { if (!byBench.has(r.benchmark)) byBench.set(r.benchmark, []); byBench.get(r.benchmark).push(r); }
        for (const [bench, rows] of byBench) {
          b.appendChild(h('p', 'small muted', titles.get(bench) || bench));
          const t = h('table', 'tv'); const hr = h('tr'); for (const [c, k] of [['Metric', ''], ['Median', 'n'], ['Cases', 'n']]) hr.appendChild(h('th', k, c)); const th = h('thead'); th.appendChild(hr); t.appendChild(th);
          const tb = h('tbody'); for (const r of rows) { const tr = h('tr'); tr.appendChild(h('td', 'ck', r.metric)); tr.appendChild(h('td', 'n', C.fmtSci(r.median))); tr.appendChild(h('td', 'n', String(r.count))); tb.appendChild(tr); } t.appendChild(tb); b.appendChild(t);
        }
      }), fail(results)));
    reads.push(Promise.all([P.read('runs', { reference: m.id }), P.read('products', { reference: m.id })])
      .then(fill(runs, (b, [r, p]) => {
        if (!r.runs.length) b.appendChild(h('p', 'empty', 'No run of this model in this project.'));
        else { const ul = h('ul', 'rows'); for (const run of r.runs.slice(0, 8)) { const li = h('li'); const row = h('div', 'row'); row.style.gridTemplateColumns = 'minmax(0, 1fr) auto'; const t = h('span'); t.appendChild(h('span', 'title', (run.subject ? run.subject + ' · ' : '') + time(run.finished_at || run.started_at || run.queued_at))); t.appendChild(h('span', 'sub', [run.seconds != null ? Math.round(run.seconds) + ' s' : null, run.bytes != null ? bytes(run.bytes) : null, run.scratch ? 'scratch' : null].filter(Boolean).join(' · ') || run.id)); row.appendChild(t); row.appendChild(modelState(run.state)); li.appendChild(row); ul.appendChild(li); } b.appendChild(ul); if (r.runs.length > 8) b.appendChild(h('p', 'note', (r.runs.length - 8) + ' earlier runs are not listed.')); }
        if (!p.products.length) b.appendChild(h('p', 'note', 'No product on this machine.'));
        else { const dl = h('dl', 'facts'); for (const pr of p.products) { dl.appendChild(h('dt', null, (pr.subject || 'Product') + (pr.adopted ? ' (adopted)' : ''))); dl.appendChild(h('dd', 'mono', pr.directory + ' · ' + bytes(pr.bytes))); } b.appendChild(dl); }
      }), fail(runs)));
    reads.push(P.read('definition', { reference: m.id })
      .then(fill(uses2, (b, d) => {
        const other = d.uses.filter(u => !u.reference.startsWith('recipes/'));
        if (!other.length) { b.appendChild(h('p', 'empty', 'It uses no dataset, model or environment.')); return; }
        const dl = h('dl', 'facts'); for (const u of other) { dl.appendChild(h('dt', null, u.role)); dl.appendChild(h('dd', 'mono', u.reference)); } b.appendChild(dl);
      }), fail(uses2)));
    if (!m.card) fill(card, b => b.appendChild(h('p', 'empty', 'This model has no card.')))();
    else if (!m.card.startsWith('notes/')) fill(card, b => b.appendChild(h('p', 'empty', 'Its card ' + m.card + ' is not under notes/ and is not read.')))();
    else reads.push(P.read('note', { path: m.card.slice('notes/'.length) }).then(fill(card, (b, note) => { b.appendChild(h('p', 'note mono', m.card)); b.appendChild(window.TuldokMarkdown.render(note.text)); }), fail(card)));
    // Read again: the drawer on screen stays until the new one is complete.
    if (same) Promise.all(reads).then(() => { if (live()) putDrawer(aside, ins); });
  }

  // ---- Overview --------------------------------------------------------------
  // Read once and built off the page (tabs.js's paint), so the refresh while a build runs keeps the place.
  function overview(main, aside, state, act, data) {
    const E = window.LabEditor, sel = state.sel.overview || '';
    if (sel === 'report') { aside.textContent = ''; aside._for = null; return report(main, data); }
    const editing = !!(E && E.owns(sel, data));
    if (editing) E.drawer(aside, sel, act, data, 'overview'); else { aside.textContent = ''; aside._for = null; }
    S.paint(main, () => Promise.all([P.read('definitions'), P.read('environments'), P.read('activity', { limit: 12 })].map(p => p.then(v => ({ v }), error => ({ error })))), (frag, [d, e, a]) => {
      const standing = data.standing;
      const top = h('section', 'ov-status');
      const line = h('div', 'ov-line'); line.appendChild(stateEl(standing.tone, standing.word)); line.appendChild(h('p', 'ov-text', standing.text)); top.appendChild(line);
      const at = h('p', 'small faint', 'Read at ' + data.readAt); at.dataset.readAt = '1'; top.appendChild(at);   // set in place on every reading (app.js)
      frag.appendChild(top);
      const row = h('div', 'ov-row');
      const needs = h('section'); needs.appendChild(sect('Needs you', data.needs ? String(data.needs.length) : '…'));
      if (data.needs) needs.appendChild(needsList(data.needs, n => window.LabActions.needControls(n, act.go))); else needs.appendChild(h('p', 'note', 'Reading…'));
      row.appendChild(needs);
      const facts = h('section'); facts.appendChild(sect('Project'));
      const dl = h('dl', 'facts'), s = data.summary;
      for (const [k, v, c] of [['Folder', s.folder, 'mono'], ['Code root', s.code_root, 'mono'], ['Project', s.project_id, 'mono'], ['Build worker', s.worker]]) { dl.appendChild(h('dt', null, k)); dl.appendChild(h('dd', c || '', v)); }
      dl.appendChild(h('dt', null, 'Report')); const dd = h('dd'); const link = h('a', null, 'Open the report'); link.href = '#overview/report'; dd.appendChild(link); dl.appendChild(dd);
      facts.appendChild(dl); row.appendChild(facts); frag.appendChild(row);
      const cols = h('div', 'ov-cols');
      const defs = h('section'); defs.appendChild(sect('Definitions', String(Object.values(s.kinds).reduce((x, y) => x + y, 0)))); cols.appendChild(defs);
      const envs = h('section'); envs.appendChild(sect('Environments', String(s.kinds.environment || 0))); cols.appendChild(envs);
      frag.appendChild(cols);
      // Every definition by kind, each opening the editor (editor.js) for a session that may edit.
      const every = h('section', 'ov-defs'); frag.appendChild(every);
      const act2 = h('section', 'ov-history'); act2.appendChild(sect('Latest activity')); frag.appendChild(act2);
      const fill = (b, got, build) => { if (got.error) failure(b, got.error); else build(b, got.v); };
      fill(defs, d, (b, d) => {
        const states = [...new Set(d.definitions.map(x => x.state))].sort();
        const kinds = [...new Set(d.definitions.map(x => x.kind))].sort();
        if (!kinds.length) { b.appendChild(h('p', 'empty', 'The project has no definitions.')); return; }
        const t = h('table', 'tv kinds'), th = h('thead'), hr = h('tr'); hr.appendChild(h('th', null, 'Kind')); for (const st of states) hr.appendChild(h('th', 'n', P.stateWord(st)[0])); hr.appendChild(h('th', 'n', 'All')); th.appendChild(hr); t.appendChild(th);
        const tb = h('tbody'); for (const k of kinds) { const tr = h('tr'); tr.appendChild(h('td', null, k)); const mine = d.definitions.filter(x => x.kind === k); for (const st of states) { const n = mine.filter(x => x.state === st).length; tr.appendChild(h('td', 'n' + (n ? '' : ' faint'), n ? String(n) : '·')); } tr.appendChild(h('td', 'n', String(mine.length))); tb.appendChild(tr); } t.appendChild(tb);
        const wrap = h('div'); wrap.style.overflowX = 'auto'; wrap.appendChild(t); b.appendChild(wrap);
      });
      fill(every, d, (b, d) => { if (E) E.definitionList(b, d.definitions, sel, act); });
      fill(envs, e, (b, e) => {
        if (!e.environments.length) { b.appendChild(h('p', 'empty', 'The project defines no environment.')); return; }
        const ul = h('ul', 'rows'); for (const env of e.environments) { const li = h('li'); const r = h('div', 'row ov-env'); const t = h('span'); t.appendChild(h('span', 'title', env.title)); t.appendChild(h('span', 'sub', ['Python ' + env.python, env.device, Object.keys(env.packages || {}).length + ' packages', env.checked_at ? 'checked ' + P.day(env.checked_at) : 'never checked'].filter(Boolean).join(' · '))); r.appendChild(t); r.appendChild(modelState(env.state)); li.appendChild(r); ul.appendChild(li); } b.appendChild(ul);
      });
      fill(act2, a, (b, a) => {
        if (!a.items.length) { b.appendChild(h('p', 'empty', 'Nothing has been asked of this project through Tuldok yet.')); return; }
        const ul = h('ul', 'rows'); for (const it of a.items) { const li = h('li'); const r = h('div', 'row ov-act'); r.appendChild(h('span', 'sub num', time(it.at))); const t = h('span'); t.appendChild(h('span', 'title', it.operation + (it.target ? ' · ' + it.target : ''))); t.appendChild(h('span', 'sub', [(it.actor && (it.actor.label || it.actor.kind)) || '', it.detail].filter(Boolean).join(' · '))); r.appendChild(t); r.appendChild(stateEl(it.outcome === 'done' ? 'good' : 'serious', it.outcome)); li.appendChild(r); ul.appendChild(li); }
        b.appendChild(ul); if (a.total > a.items.length) b.appendChild(h('p', 'note', (a.total - a.items.length) + ' earlier entries are not shown.'));
      });
      if (E) E.decorate(frag);
    });
    return editing;
  }
  /** The report in a frame: "Reading…" the first time; read again, the frame on screen stays until the new one is put in its place. */
  function report(main, data) {
    const view = main._view, mine = main._paint = (main._paint || 0) + 1;
    const head = () => { const bar = h('div', 'report-bar'); const back = h('a', 'btn sm ghost', '← Overview'); back.href = '#overview'; bar.appendChild(back); bar.appendChild(h('h2', null, 'Report')); return bar; };
    if (main._painted !== view) { main.textContent = ''; main.appendChild(head()); main.appendChild(h('p', 'note', 'Reading…')); }
    const theme = getComputedStyle(document.documentElement).colorScheme === 'dark' ? 'dark' : 'light';
    const put = add => { if (main._paint !== mine || main._view !== view) return; const frag = document.createDocumentFragment(); frag.appendChild(head()); add(frag); putInPlace(main, frag); main._painted = view; };
    P.call('report', { theme }).then(r => put(frag => { const frame = h('iframe', 'report-frame'); frame.title = 'Project report'; frame.setAttribute('sandbox', ''); frame.srcdoc = r.html; frag.appendChild(frame); }), error => put(frag => failure(frag, error)));
    return false;
  }

  // ---- Theme toggle (system, light, dark) -----------------------------------
  const theme = {
    init(btn) {
      let cur = 'auto'; try { cur = localStorage.getItem('tuldok-theme') || 'auto'; } catch (e) { /* storage refused: the system theme */ }
      const q = new URLSearchParams(location.search).get('theme'); if (q === 'light' || q === 'dark') cur = q;
      const apply = () => { if (cur === 'auto') document.documentElement.removeAttribute('data-theme'); else document.documentElement.setAttribute('data-theme', cur); btn.textContent = ''; btn.appendChild(icon('theme')); btn.appendChild(document.createTextNode(' ' + { auto: 'System', light: 'Light', dark: 'Dark' }[cur])); btn.setAttribute('aria-label', 'Theme: ' + { auto: 'system', light: 'light', dark: 'dark' }[cur]); };
      btn.addEventListener('click', () => { cur = { auto: 'light', light: 'dark', dark: 'auto' }[cur]; try { localStorage.setItem('tuldok-theme', cur); } catch (e) { /* kept for this page only */ } apply(); });
      apply();
    }
  };

  // The Data, Train, Benchmarks and Analysis screens are added by tabs.js, which builds with these parts.
  const parts = { sect, cell, block, time, bytes, failure, modelState, graphFor, putInPlace, putDrawer, turn };
  const S = { map, overview, inspectorModel, needsList, icon, stateEl, theme, parts };
  return S;
})();
