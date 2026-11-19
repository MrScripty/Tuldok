'use strict';
// The Annotate tab (docs/plans/definition-first-projects/spec-d4.md section 7): a task's records as a paged grid of
// 48 with a dot for the state of each, the record in its viewer (inside.js's), and the task's form beside it with
// the decision, a note, Keep and next, Skip, Revert and, for a stale annotation, Still right. Boxes are drawn on the
// image, spans marked in the text and segments on the waveform, in Canvas 2D and the DOM with the tokens of
// base.css, by pointer and by keyboard. The New task form (in the drawer) keeps a new annotations/<name>
// definition as an unsaved edit, as the editor keeps a new definition; the Data tab's Import and Freeze forms
// (datasetForm) keep a new dataset the same way. Annotations are kept with set_annotation and written by Save.
//
// Updating in place (spec-w4): the tab is drawn in four parts (the bar, the grid, the viewer, the form), each built
// off the page and put in place only when what it shows differs, so a reading that changed something elsewhere
// redraws the grid and leaves the form alone. What is typed or drawn in the form is a draft kept in page memory per
// task and record until it is kept, reverted or put right: a reading never replaces a form that holds one, and
// moving to another record keeps it. The forms in the drawer are never touched by a reading on the timer or on
// focus, and keep what is typed in their group's slot (actions.js). Keys (1 to 9, Enter, the left and right
// arrows) are ignored while typing in a field.
window.LabAnnotate = (() => {
  const P = window.TuldokProject, S = window.LabScreens, A = window.LabActions, C = window.LabCharts, h = C.h, V = window.LabInside.viewers;
  const { sect, putInPlace, putDrawer, turn, time, bytes } = S.parts;
  const PER_PAGE = 48;
  const TYPES = ['review', 'class', 'tags', 'text', 'boxes', 'spans', 'segments', 'polygons', 'mask', 'depth', 'keypoints', 'ranking', 'timeseries', 'track', 'points', 'box3d'];
  const TYPE_WORD = { review: 'Review', class: 'Class: one term', tags: 'Tags: any of the terms', text: 'Text: a caption or a transcript', boxes: 'Boxes on an image', spans: 'Spans of a text', segments: 'Segments of a sound',
    polygons: 'Polygons on an image', mask: 'A mask of an image', depth: 'A depth map of an image', keypoints: 'Keypoints on an image', ranking: 'A ranking of candidates', timeseries: 'Stretches of a series or a sound', track: 'Tracks across frames', points: 'Point objects of a point cloud', box3d: '3-D boxes in a point cloud' };
  const NEEDS_TERMS = ['class', 'tags', 'boxes', 'spans', 'segments', 'polygons', 'mask', 'keypoints', 'ranking', 'timeseries', 'track', 'points', 'box3d'];
  // The kinds of record a task describes (spec-d4, spec-t4 section 1); the others take any kind but file.
  const ONLY = { boxes: ['image'], spans: ['text'], segments: ['audio'], polygons: ['image'], mask: ['image'], depth: ['image'], keypoints: ['image'], timeseries: ['audio', 'array'], track: ['array'], points: ['pointcloud'], box3d: ['pointcloud'] };
  const GENERATED = ['polygons', 'mask', 'depth', 'keypoints', 'ranking', 'timeseries', 'track', 'points', 'box3d'];   // reviewed, not drawn here
  const FILTERS = [['all', 'All'], ['todo', 'To do'], ['accepted', 'Accepted'], ['needs-work', 'Needs work'], ['rejected', 'Rejected'], ['stale', 'Stale']];
  const DECISIONS = [['accepted', 'Accept', 'ok'], ['needs-work', 'Needs work', 'warn'], ['rejected', 'Reject', 'bad']];
  const STATE = { none: ['neutral', 'not annotated'], draft: ['neutral', 'draft'], accepted: ['good', 'accepted'], 'needs-work': ['warn', 'needs work'], rejected: ['serious', 'rejected'] };
  const SUGGESTS = ['text', 'class', 'tags'];   // the tasks a served model can suggest a value of (spec-d5 section 4)
  const FORMAT = 'tuldok_definition_v1';
  const count = (n, one, many) => n.toLocaleString('en-GB') + ' ' + (n === 1 ? one : many || one + 's');
  const button = (cls, text, key, onClick) => { const b = h('button', cls, text); b.type = 'button'; if (key) b.dataset.key = key; if (onClick) b.addEventListener('click', onClick); return b; };
  const kbd = text => h('span', 'kbd', text);
  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
  const rgb = (c, a) => a == null ? 'rgb(' + c.join(',') + ')' : 'rgba(' + c.join(',') + ',' + a + ')';
  const nameOf = ref => ref.slice(ref.indexOf('/') + 1);
  const copy = v => v == null ? v : JSON.parse(JSON.stringify(v));
  const textOf = doc => JSON.stringify(doc, null, 2) + '\n';

  // ---- What is kept in this page ------------------------------------------------------------------------------------
  const ui = { task: null, filter: 'all', page: 0, sel: new Map(), selAt: 0, terms: new Map(), mode: 'annotate' };   // sel and terms: per task
  const drafts = new Map();   // task + '\n' + record -> { state, value, note, dirty }
  const store = new Map();    // the viewers' settings (inside.js), per record
  let here = null;            // the tab on screen: { main, act, root, keys, parts, t, page, rec, pick, repaint, relist }

  const draftKey = (t, rec) => t.task + '\n' + rec.id;
  function emptyValue(type) { return type === 'class' || type === 'review' || GENERATED.includes(type) ? null : type === 'text' ? '' : []; }
  /** A draft from the annotation as it is (not typed yet), or the one typed. */
  function draftOf(t, rec, fresh) {
    const k = draftKey(t, rec), had = drafts.get(k);
    if (had && (had.dirty || !fresh)) return had;
    const a = rec.annotation, d = { state: a && a.state !== 'draft' ? a.state : null, value: a && a.value != null ? copy(a.value) : emptyValue(t.type), note: (a && a.note) || '', dirty: false };
    if (t.type === 'text' && typeof d.value !== 'string') d.value = '';
    if (['tags', 'boxes', 'spans', 'segments'].includes(t.type) && !Array.isArray(d.value)) d.value = [];
    drafts.set(k, d); return d;
  }
  /** The value a draft keeps, as the task's value: null for review, an empty text or no term. */
  function valueOf(t, d) {
    if (t.type === 'review') return null;
    if (t.type === 'class') return d.value || null;
    if (t.type === 'text') return d.value ? d.value : null;
    if (t.type === 'tags') return t.vocabulary.filter(v => d.value.includes(v));
    if (t.type === 'segments') return d.value.map(s => { const o = { term: s.term, start: s.start, end: s.end }; if (s.text) o.text = s.text; return o; });
    return copy(d.value);
  }
  function itemOf(t, rec, d) { const it = { record: rec.id, state: d.state || 'draft', value: valueOf(t, d) }; if (d.note && d.note.trim()) it.note = d.note; return it; }

  // ---- Reading ---------------------------------------------------------------------------------------------------
  /** A page of the task's records for the filter: "To do" is the records not annotated, then the drafts. */
  async function pageOf(t) {
    const offset = ui.page * PER_PAGE;
    if (ui.filter !== 'todo') { const r = await P.annotations.records(t.task, { state: ui.filter === 'all' ? null : ui.filter, offset, limit: PER_PAGE }); return { records: r.records, total: r.total }; }
    const u = await P.annotations.records(t.task, { state: 'unannotated', offset, limit: PER_PAGE });
    const need = PER_PAGE - u.records.length, d = await P.annotations.records(t.task, { state: 'draft', offset: Math.max(0, offset - u.total), limit: Math.max(1, need) });
    return { records: need > 0 ? u.records.concat(d.records.slice(0, need)) : u.records, total: u.total + d.total };
  }
  async function load() {
    const tasks = (await P.annotations.tasks()).tasks;
    if (!tasks.length) return { tasks };
    const t = tasks.find(x => x.task === ui.task) || tasks[0]; ui.task = t.task;
    if (!t.run) return { tasks, t };
    let page = await pageOf(t);
    if (!page.records.length && ui.page > 0 && page.total) { ui.page = Math.floor((page.total - 1) / PER_PAGE); page = await pageOf(t); }
    let id = ui.sel.get(t.task);
    if (!page.records.some(r => r.id === id)) id = page.records.length ? page.records[ui.selAt === -1 ? page.records.length - 1 : 0].id : null;
    ui.selAt = 0; if (id) ui.sel.set(t.task, id); else ui.sel.delete(t.task);
    // The models that can suggest (spec-d5 section 4), for a session that may annotate; none when they cannot be read.
    const offers = A.may('edit') && SUGGESTS.includes(t.type) ? await P.read('suggestion_models', { task: t.task }).then(r => r.kinds || {}, () => ({})) : {};
    // The task's annotation sets (spec-t4 section 6): Review is offered when an annotator made one.
    const sets = await P.read('annotation_sets', { task: t.task }).then(r => r.sets, () => []);
    return { tasks, t, page, rec: page.records.find(r => r.id === id) || null, offers, sets };
  }

  // ---- The tab -----------------------------------------------------------------------------------------------------
  /** The screen (app.js): the tab in main; the drawer holds the New task form when it is selected. */
  function annotate(main, aside, state, act) {
    draw(main, act);
    if (state.sel.annotate === 'new-task') { taskForm(aside, act); return true; }
    aside.textContent = ''; aside._for = null;
    return false;
  }
  /** A person's own move (a record, a page, a filter, a task): drawn again at once from what is kept. */
  const redraw = () => { if (here && here.root && here.root.isConnected) draw(here.main, here.act); };

  /**
   * Draws the tab: "Reading…" only when it is not on screen; otherwise each part whose content differs is built off
   * the page and put in place, the others are left alone. A form holding a draft of the record it shows is kept.
   */
  async function draw(main, act) {
    const view = main._view, mine = main._paint = (main._paint || 0) + 1;
    const shown = !!(here && here.root && main.contains(here.root) && main._painted === view);
    if (!shown) { main.textContent = ''; main.appendChild(h('p', 'note', 'Reading…')); here = { main, act, root: null, keys: {}, parts: {}, pick: -1 }; }
    here.act = act;
    main.setAttribute('aria-busy', 'true');
    let got; try { got = await load(); } catch (error) { got = { error }; }
    if (main._paint !== mine || main._view !== view) return;
    const reviewing = !got.error && got.t && got.t.run && ui.mode === 'review' && reviewable(got.sets);
    const kind = got.error ? 'error' : !got.tasks.length ? 'none' : !got.t.run ? 'unbuilt' : reviewing ? 'review' : 'records';
    const t = got.t || null, rec = got.rec || null, may = A.may('edit');
    const keys = { shape: kind, bar: kind === 'error' ? 'error' : JSON.stringify([got.tasks.map(x => [x.task, x.title, x.type]), t && [t.task, t.run, t.records, t.counts, t.dataset], ui.filter, may, ui.mode, reviewable(got.sets)]) };
    if (kind === 'records') {
      keys.list = JSON.stringify([t.task, t.run, ui.filter, ui.page, got.page.total, got.page.records.map(r => [r.id, r.kind, r.path, r.preview || null, r.in_product, r.annotation && [r.annotation.state, r.annotation.stale, r.annotation.unsaved]])]);
      keys.view = rec ? JSON.stringify([t.task, t.type, t.run, rec.id, rec.kind, rec.in_product]) : 'none';   // its place in the list is set in place (place())
      keys.form = rec ? JSON.stringify([t.task, t.type, t.vocabulary, rec.id, rec.kind, rec.in_product, rec.annotation, may, (got.offers || {})[rec.kind] || []]) : 'none';
      const same = here.rec && rec && here.t && here.t.task === t.task && here.rec.id === rec.id;
      if (same && here.keys.form && keys.form !== here.keys.form && (drafts.get(draftKey(t, rec)) || {}).dirty) keys.form = here.keys.form;   // what is typed stays
    } else keys.msg = JSON.stringify([kind, t && [t.task, t.dataset], may, got.error ? got.error.message : null]);
    // What changed is read before anything is put in place, so that it is put in one step.
    const build = {};
    try {
      if (keys.view && keys.view !== here.keys.view) { if (!here.rec || !rec || here.rec.id !== rec.id) here.pick = -1; build.view = rec ? await buildView(t, rec, got.page) : h('p', 'empty', 'Choose a record.'); }
      if (keys.form && keys.form !== here.keys.form && rec && rec.annotation && rec.annotation.stale) build.detail = await P.annotations.one(t.task, rec.id).catch(() => null);
    } catch (error) { build.view = h('div', 'iv'); build.view.appendChild(A.refusal(error)); }
    if (main._paint !== mine || main._view !== view) return;
    main.removeAttribute('aria-busy');
    here.t = t; here.page = got.page || null; here.rec = rec; here.tasks = got.tasks; here.offers = got.offers || {}; here.sets = got.sets || [];
    const fresh = !here.root || keys.shape !== here.keys.shape;
    if (fresh) {
      const root = h('div', 'annotate'); root.dataset.shape = kind;
      here.parts = { bar: h('div', 'ann-barbox') }; root.appendChild(here.parts.bar);
      if (kind === 'review') { here.parts.review = h('div', 'ann-review'); root.appendChild(here.parts.review); }
      else if (kind === 'records') { const body = h('div', 'ann-body'); for (const p of ['list', 'view', 'form']) { here.parts[p] = h('div', 'ann-' + p); body.appendChild(here.parts[p]); } here.parts.view.classList.add('viewer'); here.parts.view.setAttribute('aria-label', 'The record'); root.appendChild(body); }
      else { here.parts.msg = h('div', 'ann-msg'); root.appendChild(here.parts.msg); }
      here.keys = { shape: kind };
      here.root = root;
    }
    const put = (name, make) => {
      if (here.keys[name] === keys[name]) return;
      here.keys[name] = keys[name];
      const content = make(); if (fresh) here.parts[name].replaceChildren(content); else putInPlace(here.parts[name], content, main);
    };
    put('bar', () => kind === 'error' ? h('div') : buildBar(got.tasks, t, got.sets));
    if (kind === 'review') {
      if (fresh) putInPlace(main, here.root);
      main._painted = view;
      await window.LabReview.draw(here.parts.review, t, got.sets, here.act);
      return;
    }
    if (kind === 'records') {
      put('list', () => buildList(t, got.page));
      put('view', () => { const hooks = build.view._hooks || {}; here.repaint = hooks.repaint || null; here.textOf = hooks.textOf || null; here.play = hooks.play || null; return build.view; });
      put('form', () => rec ? buildForm(t, rec, build.detail) : h('p', 'empty', t.records ? 'No record matches the filter.' : 'The product of ' + t.dataset + ' holds no records.'));
      // The selection is set in place: the grid is not drawn again for it.
      for (const b of here.parts.list.querySelectorAll('.rec')) { const on = String(!!rec && b.dataset.id === rec.id); if (b.getAttribute('aria-pressed') !== on) b.setAttribute('aria-pressed', on); }
      if (rec) place(here.parts.view, got.page, rec);
      if (here.repaint) here.repaint();
    } else put('msg', () => buildMessage(kind, t, got.error));
    if (fresh) putInPlace(main, here.root);
    main._painted = view;
    if (here.focusAfter) { const k = here.focusAfter; here.focusAfter = null; A.focusKey(k); }
    if (here.focusSel) { here.focusSel = false; const b = here.root.querySelector('.rec[aria-pressed="true"]'); if (b) b.focus(); }
  }

  function buildMessage(kind, t, error) {
    const box = h('div', 'ann-empty');
    if (kind === 'error') { box.appendChild(A.refusal(error)); return box; }
    if (kind === 'none') {
      box.appendChild(h('p', 'empty', 'This project has no annotation task. A task says what is recorded about the records of one dataset: a decision, a class, tags, a text, boxes, spans or segments.'));
      if (!A.may('edit')) box.appendChild(h('p', 'note', 'Making a task needs the right to edit.'));
      return box;
    }
    box.appendChild(h('p', 'empty', t.dataset + ' has no product on this machine, so ' + t.task + ' has no records to annotate yet. Build the dataset first.'));
    box.appendChild(A.group('annotate:plan', [{ id: 'plan', label: 'Plan a build of ' + t.dataset, cls: 'btn', who: 'request', onClick: () => here.act.go('train', 'plan:' + t.dataset) }]));
    return box;
  }

  // ---- The bar -----------------------------------------------------------------------------------------------------
  /** Review needs a set made by an annotator besides the kept set. */
  const reviewable = sets => (sets || []).some(x => x.set !== 'kept');
  function buildBar(tasks, t, sets) {
    const bar = h('div', 'ann-bar');
    if (tasks.length) {
      const l = h('label', 'ann-task'); l.appendChild(document.createTextNode('Task'));
      const s = h('select'); s.dataset.key = 'ann:task';
      for (const x of tasks) { const o = h('option', null, x.title + ' · ' + x.type); o.value = x.task; o.selected = !!t && x.task === t.task; s.appendChild(o); }
      s.addEventListener('change', () => { ui.task = s.value; ui.page = 0; here.pick = -1; redraw(); });
      l.appendChild(s); bar.appendChild(l);
    }
    bar.appendChild(A.group('annotate:new', [{ id: 'new', label: 'New task', cls: 'btn sm', who: 'edit', onClick: () => here.act.select('new-task') }], { inline: true }));
    if (t && t.run && reviewable(sets)) {
      const seg = h('div', 'seg ann-mode'); seg.setAttribute('role', 'group'); seg.setAttribute('aria-label', 'Annotate or review the annotators\' sets');
      for (const [id, label] of [['annotate', 'Annotate'], ['review', 'Review']]) { const b = button(null, label, 'ann:mode-' + id, () => { if (ui.mode !== id) { ui.mode = id; redraw(); } }); b.setAttribute('aria-pressed', String(ui.mode === id)); seg.appendChild(b); }
      bar.appendChild(seg);
    }
    if (t && t.run && ui.mode === 'review' && reviewable(sets)) return bar;
    if (t && t.run) {
      const c = t.counts, n = { all: null, todo: c.unannotated + c.draft, accepted: c.accepted, 'needs-work': c['needs-work'], rejected: c.rejected, stale: c.stale };
      const seg = h('div', 'seg ann-filter'); seg.setAttribute('role', 'group'); seg.setAttribute('aria-label', 'Show the records');
      for (const [id, label] of FILTERS) { const b = button(null, label + (n[id] != null ? ' · ' + n[id].toLocaleString('en-GB') : ''), 'ann:filter-' + id, () => { if (ui.filter !== id) { ui.filter = id; ui.page = 0; redraw(); } }); b.setAttribute('aria-pressed', String(ui.filter === id)); seg.appendChild(b); }
      bar.appendChild(seg);
      const decided = Math.min(t.records, c.accepted + c['needs-work'] + c.rejected);
      const pr = h('span', 'ann-progress'); const bg = h('i'), fill = h('b'); fill.style.width = (t.records ? Math.round(100 * decided / t.records) : 0) + '%'; bg.appendChild(fill); pr.appendChild(bg);
      pr.appendChild(document.createTextNode(decided.toLocaleString('en-GB') + ' of ' + count(t.records, 'record') + ' decided'));
      bg.setAttribute('role', 'progressbar'); bg.setAttribute('aria-valuemin', '0'); bg.setAttribute('aria-valuemax', String(t.records)); bg.setAttribute('aria-valuenow', String(decided)); bg.setAttribute('aria-label', 'Decided');
      bar.appendChild(pr);
      const keys = h('span', 'ann-keys small faint');
      const say = (...parts) => { for (const p of parts) keys.appendChild(typeof p === 'string' ? document.createTextNode(p) : p); };
      say(kbd('←'), ' ', kbd('→'), ' move');
      if (['class', 'tags'].includes(t.type) && t.vocabulary.length) say(' · ', kbd('1'), '–', kbd(String(Math.min(9, t.vocabulary.length))), ' term');
      say(' · ', kbd('Enter'), ' keep and next');
      bar.appendChild(keys);
    }
    return bar;
  }

  // ---- The grid ----------------------------------------------------------------------------------------------------
  const marked = a => !a ? 'none' : a.state;
  function buildList(t, page) {
    const box = h('div');
    const first = ui.page * PER_PAGE + 1, last = ui.page * PER_PAGE + page.records.length;
    box.appendChild(sect('Records', page.total ? first.toLocaleString('en-GB') + '–' + last.toLocaleString('en-GB') + ' of ' + page.total.toLocaleString('en-GB') : '0'));
    if (!page.total) { box.appendChild(h('p', 'empty', ui.filter === 'all' ? 'The product holds no records.' : 'No record is ' + FILTERS.find(f => f[0] === ui.filter)[1].toLowerCase() + '.')); return box; }
    const grid = h('div', 'rec-grid ann-grid'); grid.setAttribute('role', 'group'); grid.setAttribute('aria-label', 'Records ' + first + ' to ' + last + ' of ' + page.total + '; the left and right arrows move the selection');
    for (const r of page.records) grid.appendChild(tile(t, r));
    box.appendChild(grid);
    const pages = Math.ceil(page.total / PER_PAGE);
    if (pages > 1) {
      const pg = h('div', 'pager');
      const pb = button('btn sm', 'Previous', 'ann:page-prev', () => turnPage(ui.page - 1, 0)); pb.disabled = ui.page === 0;
      const nb = button('btn sm', 'Next', 'ann:page-next', () => turnPage(ui.page + 1, 0)); nb.disabled = ui.page + 1 >= pages;
      pg.appendChild(pb); pg.appendChild(nb); pg.appendChild(h('span', null, 'page ' + (ui.page + 1) + ' of ' + pages)); box.appendChild(pg);
    }
    return box;
  }
  function turnPage(n, at) { ui.page = n; ui.sel.delete(ui.task); ui.selAt = at; redraw(); }
  function tile(t, r) {
    const a = r.annotation, st = marked(a), [, word] = STATE[st];
    const b = h('button', 'rec ann-rec ' + (r.kind || 'gone')); b.type = 'button'; b.dataset.id = r.id; b.dataset.key = 'ann-rec-' + r.id; b.dataset.state = st;
    if (a && a.stale) b.dataset.stale = '1'; if (a && a.unsaved) b.dataset.unsaved = '1';
    b.setAttribute('aria-pressed', 'false'); b.title = r.id;
    b.setAttribute('aria-label', (r.kind ? (V.WORD[r.kind] || r.kind) : 'Gone') + ' ' + r.id + ', ' + word + (a && a.stale ? ', stale' : '') + (a && a.unsaved ? ', unsaved' : ''));
    const th = h('span', 'th');
    if (!r.in_product) th.appendChild(V.glyph('refused'));
    else if (r.kind === 'text' && r.preview != null) th.appendChild(h('span', 'pre', r.preview.slice(0, 160)));
    else th.appendChild(V.glyph(r.kind));
    if (r.in_product && r.kind === 'image' && r.path) { const img = h('img'); img.alt = ''; img.loading = 'lazy'; img.decoding = 'async'; img.src = P.product.fileUrl(t.run, r.path); img.addEventListener('load', () => { const g = th.querySelector('svg'); if (g) g.remove(); }, { once: true }); img.addEventListener('error', () => img.remove(), { once: true }); th.appendChild(img); }
    const dot = h('i', 'badge ' + st); dot.setAttribute('aria-hidden', 'true'); th.appendChild(dot);
    const id = h('span', 'id'); id.appendChild(h('bdi', null, r.id));
    const line = h('span', 'st'); line.appendChild(document.createTextNode(word));
    if (a && a.stale) line.appendChild(h('b', 'stale', 'stale')); if (a && a.unsaved) line.appendChild(h('b', 'unsaved', 'unsaved'));
    b.appendChild(th); b.appendChild(id); b.appendChild(line);
    b.addEventListener('click', () => select(r.id));
    return b;
  }
  function select(id) { if (!here || !here.t) return; ui.sel.set(here.t.task, id); redraw(); }
  /** Moves the selection by d without keeping anything, across pages; on keep, done() moves on the same way. */
  function move(d, focusTile) {
    if (!here || !here.page || !here.rec) return;
    const list = here.page.records, i = list.findIndex(r => r.id === here.rec.id), n = i + d, pages = Math.ceil(here.page.total / PER_PAGE);
    here.focusSel = !!focusTile;
    if (n >= 0 && n < list.length) { ui.sel.set(here.t.task, list[n].id); return true; }
    if (n >= list.length && ui.page + 1 < pages) { ui.page++; ui.sel.delete(ui.task); ui.selAt = 0; return true; }
    if (n < 0 && ui.page > 0) { ui.page--; ui.sel.delete(ui.task); ui.selAt = -1; return true; }
    here.focusSel = false; return false;
  }

  // ---- The viewer ---------------------------------------------------------------------------------------------------
  function heading(id, line) { const hd = h('header', 'iv-head'); hd.appendChild(h('h3', 'mono', id)); if (line) hd.appendChild(h('p', 'small muted', line)); return hd; }
  /** Sets the record's place in the list into the viewer's Previous, Next and "3 of 48", in place: the viewer is not drawn again for it. */
  function place(view, page, rec) {
    const nav = view.querySelector('.ann-nav'); if (!nav) return;
    const at = page.records.indexOf(rec), pages = Math.ceil(page.total / PER_PAGE), [prev, where, next] = nav.children;
    const text = (ui.page * PER_PAGE + at + 1).toLocaleString('en-GB') + ' of ' + page.total.toLocaleString('en-GB');
    if (where.textContent !== text) where.textContent = text;
    const p = at <= 0 && ui.page === 0, n = at >= page.records.length - 1 && ui.page + 1 >= pages;
    if (prev.disabled !== p) prev.disabled = p; if (next.disabled !== n) next.disabled = n;
  }
  async function buildView(t, rec, page) {
    const el = h('div', 'iv ann-iv');
    const nav = h('div', 'ann-nav');
    nav.appendChild(button('btn sm', '← Previous', 'ann:prev', () => { if (move(-1)) redraw(); })); nav.appendChild(h('span', 'small muted')); nav.appendChild(button('btn sm', 'Next →', 'ann:next', () => { if (move(1)) redraw(); }));
    el.appendChild(nav); place(el, page, rec);
    el._hooks = {};
    if (!rec.in_product) { el.appendChild(heading(rec.id, 'Not in the current product')); el.appendChild(h('p', 'empty', 'This record is not in the current product of ' + t.dataset + ': it is gone, so its annotation is stale.')); return el; }
    const got = await P.product.record(t.run, rec.id);
    if (t.type === 'boxes' && rec.kind === 'image') boxView(el, got, t, rec);
    else if (t.type === 'spans' && rec.kind === 'text') spanView(el, got, t, rec);
    else if (t.type === 'segments' && rec.kind === 'audio') segmentView(el, got, t, rec);
    else if (GENERATED.includes(t.type) && (draftOf(t, rec).value != null) && (el.appendChild(heading(rec.id, 'The kept annotation drawn over the record')), window.LabReview.overlay(el, got, t, draftOf(t, rec).value))) { /* drawn */ }
    else await V.record(el, got, t.run, store);
    return el;
  }
  const cur = () => here && here.t && here.rec ? draftOf(here.t, here.rec) : null;
  /** The boxes, spans or segments of a record's draft (the one typed, or the annotation's). */
  const itemsOf = (t, rec) => { const d = draftOf(t, rec); if (!Array.isArray(d.value)) d.value = []; return d.value; };
  const newTerm = t => { const v = ui.terms.get(t.task); return t.vocabulary.includes(v) ? v : t.vocabulary[0]; };
  const fontOf = px => px + 'px ' + getComputedStyle(document.body).fontFamily;
  /** Something drawn or typed changed: the draft is marked, and the drawing and the list follow. */
  function touch(list = true) {
    const d = cur(); if (!d) return; d.dirty = true;
    const m = here.root && here.root.querySelector('.ann-form .umark'); if (m && m.textContent !== 'not kept yet') { m.textContent = 'not kept yet'; m.classList.add('typed'); }
    if (d.from) markSuggestion(d);
    if (list && here.relist) here.relist();
    if (here.repaint) here.repaint();
  }
  function pickItem(i) { here.pick = i; if (here.relist) here.relist(); if (here.repaint) here.repaint(); }
  /** The keys of a surface (boxes, segments): N adds one, [ and ] choose, Delete removes, Escape lets go; the rest is the surface's. */
  function surfaceKeys(e, items, add, step) {
    const list = items(); let used = true;
    if (e.key === 'n' || e.key === 'N') { list.push(add()); here.pick = list.length - 1; touch(); }
    else if (e.key === ']' || e.key === '[') { if (list.length) pickItem(((here.pick < 0 ? (e.key === ']' ? -1 : 0) : here.pick) + (e.key === ']' ? 1 : -1) + list.length) % list.length); }
    else if ((e.key === 'Delete' || e.key === 'Backspace') && list[here.pick]) { list.splice(here.pick, 1); here.pick = -1; touch(); }
    else if (e.key === 'Escape' && here.pick >= 0) { e.stopPropagation(); pickItem(-1); }
    else if (e.key.startsWith('Arrow') && list[here.pick]) { step(list[here.pick], e.key, e.shiftKey, e.altKey); touch(); }
    else used = false;
    if (used) e.preventDefault();
  }

  // Boxes, drawn on the image. Coordinates are pixels of the image, whatever its size on screen.
  function boxView(el, got, t, rec) {
    const r = got.record, k = got.content || {}, may = A.may('edit'), items = () => itemsOf(t, rec);
    el.appendChild(heading(r.id, ['Image', k.width && k.height ? k.width + ' × ' + k.height + ' pixels' : null, bytes(r.bytes)].filter(Boolean).join(' · ')));
    const stage = h('div', 'ann-stage'), wrap = h('div', 'ann-imgwrap'), img = h('img'), cv = h('canvas', 'ann-surface');
    img.src = r.url; img.alt = ''; img.draggable = false;
    cv.tabIndex = 0; cv.dataset.key = 'ann:surface'; cv.setAttribute('role', 'application');
    cv.setAttribute('aria-label', 'Image ' + r.id + ' with its boxes. ' + (may ? 'Drag to draw a box, drag a box to move it, a corner to resize it. N adds a box, [ and ] choose one, the arrows move it, Shift and the arrows resize it, Delete removes it.' : ''));
    const said = h('p', 'sr-only'); said.setAttribute('aria-live', 'polite');
    wrap.appendChild(img); wrap.appendChild(cv); stage.appendChild(wrap); el.appendChild(stage); el.appendChild(said);
    if (may) el.appendChild(h('p', 'small faint ann-help', 'Drag on the image to draw a box; drag a box to move it, a corner to resize it. With the image focused: N adds a box, [ and ] choose one, the arrows move it (Alt: by 10), Shift and the arrows resize it, Delete removes it.'));
    let nw = k.width || 0, nh = k.height || 0, frame = 0, drag = null;
    const layout = () => {
      if (!wrap.isConnected) return;
      if (!nw || !nh) { if (!img.naturalWidth) return; nw = img.naturalWidth; nh = img.naturalHeight; }
      const avail = stage.clientWidth; if (!avail) return;
      const s = Math.min(avail / nw, Math.max(180, innerHeight * 0.55) / nh), w = Math.max(1, Math.floor(nw * s)), hh = Math.max(1, Math.floor(nh * s));
      if (wrap.style.width !== w + 'px' || wrap.style.height !== hh + 'px') { wrap.style.width = w + 'px'; wrap.style.height = hh + 'px'; }
      wrap.classList.toggle('pixels', s >= 2);
      wrap.dataset.image = nw + 'x' + nh;
      paint();
    };
    const paint = () => {
      frame = 0;
      const W0 = cv.clientWidth, H0 = cv.clientHeight; if (!W0 || !H0 || !nw) return;
      const dpr = window.devicePixelRatio || 1, W = Math.round(W0 * dpr), H = Math.round(H0 * dpr);
      if (cv.width !== W) cv.width = W; if (cv.height !== H) cv.height = H;
      const ctx = cv.getContext('2d'); ctx.clearRect(0, 0, W, H);
      const sx = W / nw, sy = H / nh, list = items(), mark = V.token('--mark'), acc = V.token('--accent'), halo = V.token('--surface'), ink = V.token('--accent-ink');
      ctx.font = fontOf(Math.round(11.5 * dpr)); ctx.textBaseline = 'top';
      list.forEach((b, i) => {
        const on = i === here.pick, x = b.x * sx, y = b.y * sy, w = b.w * sx, hh = b.h * sy, c = on ? acc : mark;
        ctx.fillStyle = rgb(c, on ? 0.16 : 0.08); ctx.fillRect(x, y, w, hh);
        ctx.lineWidth = (on ? 4 : 3) * dpr; ctx.strokeStyle = rgb(halo, 0.9); ctx.strokeRect(x, y, w, hh);
        ctx.lineWidth = (on ? 2 : 1.5) * dpr; ctx.strokeStyle = rgb(c); ctx.strokeRect(x, y, w, hh);
        const label = (i + 1) + ' ' + b.term, tw = ctx.measureText(label).width + 8 * dpr, th = 16 * dpr, ty = y >= th ? y - th : y;
        ctx.fillStyle = rgb(c); ctx.fillRect(x, ty, Math.min(tw, Math.max(tw, w)), th); ctx.fillStyle = rgb(ink); ctx.fillText(label, x + 4 * dpr, ty + 2 * dpr);
        if (on) for (const [cx, cy] of [[x, y], [x + w, y], [x, y + hh], [x + w, y + hh]]) { const s = 7 * dpr; ctx.fillStyle = rgb(halo); ctx.fillRect(cx - s / 2, cy - s / 2, s, s); ctx.strokeStyle = rgb(acc); ctx.lineWidth = 1.5 * dpr; ctx.strokeRect(cx - s / 2, cy - s / 2, s, s); }
      });
      const b = list[here.pick]; const text = b ? 'Box ' + (here.pick + 1) + ', ' + b.term + ', at ' + b.x + ', ' + b.y + ', ' + b.w + ' by ' + b.h + ' pixels' : count(list.length, 'box', 'boxes');
      if (said.textContent !== text) said.textContent = text;
    };
    const later = () => { if (!frame) frame = requestAnimationFrame(paint); };
    el._hooks.repaint = later;
    img.addEventListener('load', layout);
    const ro = new ResizeObserver(() => { if (!stage.isConnected) { if (stage._seen) ro.disconnect(); return; } stage._seen = true; layout(); });
    ro.observe(stage);
    V.paints(cv, later);   // the theme
    const at = e => { const q = cv.getBoundingClientRect(); return { x: clamp((e.clientX - q.left) / q.width * nw, 0, nw), y: clamp((e.clientY - q.top) / q.height * nh, 0, nh) }; };
    const corners = b => [['nw', b.x, b.y], ['ne', b.x + b.w, b.y], ['sw', b.x, b.y + b.h], ['se', b.x + b.w, b.y + b.h]];
    const fitBox = b => { b.x = clamp(Math.round(b.x), 0, nw - 1); b.y = clamp(Math.round(b.y), 0, nh - 1); b.w = clamp(Math.round(b.w), 1, nw - b.x); b.h = clamp(Math.round(b.h), 1, nh - b.y); return b; };
    cv.addEventListener('pointerdown', e => {
      if (e.button !== 0 || !may || !nw) return;
      e.preventDefault(); cv.focus({ preventScroll: true });
      const p = at(e), list = items(), tol = 8 * nw / cv.clientWidth;
      let hit = null;
      const order = list.map((_, i) => i).reverse(); if (here.pick >= 0 && list[here.pick]) order.unshift(here.pick);
      for (const i of order) { for (const [corner, cx, cy] of corners(list[i])) if (Math.abs(p.x - cx) <= tol && Math.abs(p.y - cy) <= tol) { hit = { mode: 'resize', i, corner }; break; } if (hit) break; }
      if (!hit) for (const i of order) { const b = list[i]; if (p.x >= b.x && p.x <= b.x + b.w && p.y >= b.y && p.y <= b.y + b.h) { hit = { mode: 'move', i }; break; } }
      if (!hit) { list.push({ term: newTerm(t), x: p.x, y: p.y, w: 0, h: 0 }); hit = { mode: 'new', i: list.length - 1 }; }
      drag = Object.assign(hit, { from: p, orig: Object.assign({}, list[hit.i]), id: e.pointerId, moved: false });
      here.pick = hit.i; cv.setPointerCapture(e.pointerId); later();
    });
    cv.addEventListener('pointermove', e => {
      if (!drag || e.pointerId !== drag.id) return;
      const p = at(e), b = items()[drag.i], o = drag.orig; if (!b) return;
      drag.moved = true;
      if (drag.mode === 'new') Object.assign(b, { x: Math.min(drag.from.x, p.x), y: Math.min(drag.from.y, p.y), w: Math.abs(p.x - drag.from.x), h: Math.abs(p.y - drag.from.y) });
      else if (drag.mode === 'move') Object.assign(b, { x: clamp(o.x + p.x - drag.from.x, 0, nw - o.w), y: clamp(o.y + p.y - drag.from.y, 0, nh - o.h) });
      else { const fx = drag.corner.includes('w') ? o.x + o.w : o.x, fy = drag.corner.includes('n') ? o.y + o.h : o.y; Object.assign(b, { x: Math.min(fx, p.x), y: Math.min(fy, p.y), w: Math.abs(p.x - fx), h: Math.abs(p.y - fy) }); }
      later();
    });
    const end = e => {
      if (!drag || e.pointerId !== drag.id) return;
      const list = items(), b = list[drag.i], d = drag; drag = null;
      if (!b) return;
      if (d.mode === 'new' && (b.w < 1 || b.h < 1)) { list.splice(d.i, 1); here.pick = -1; if (here.relist) here.relist(); later(); return; }   // a press without a drag: nothing drawn, nothing chosen
      if (!d.moved) { if (here.relist) here.relist(); later(); return; }
      fitBox(b); touch();
    };
    cv.addEventListener('pointerup', end); cv.addEventListener('pointercancel', end);
    cv.addEventListener('keydown', e => {
      if (!may || !nw) return;
      surfaceKeys(e, items, () => fitBox({ term: newTerm(t), x: nw / 4, y: nh / 4, w: Math.max(1, nw / 2), h: Math.max(1, nh / 2) }), (b, key, shift, alt) => {
        const s = alt ? 10 : 1, dx = key === 'ArrowLeft' ? -s : key === 'ArrowRight' ? s : 0, dy = key === 'ArrowUp' ? -s : key === 'ArrowDown' ? s : 0;
        if (shift) { b.w = clamp(b.w + dx, 1, nw - b.x); b.h = clamp(b.h + dy, 1, nh - b.y); }
        else { b.x = clamp(b.x + dx, 0, nw - b.w); b.y = clamp(b.y + dy, 0, nh - b.h); }
      });
    });
  }

  // Spans, marked in the text. Offsets are characters (code points) of the record's text.
  function spanView(el, got, t, rec) {
    const r = got.record, k = got.content || {}, text = k.text || '', may = A.may('edit'), items = () => itemsOf(t, rec);
    const total = k.characters != null ? k.characters : Array.from(text).length;
    el.appendChild(heading(r.id, ['Text', count(total, 'character'), k.truncated ? 'truncated: spans can be marked in the first ' + Array.from(text).length.toLocaleString('en-GB') : null].filter(Boolean).join(' · ')));
    const pre = h('pre', 'iv-text ann-text'); pre.tabIndex = 0; pre.dataset.key = 'ann:text-surface';
    pre.setAttribute('aria-label', 'The text, with its spans marked' + (may ? '; select a stretch of it to mark a span' : ''));
    el.appendChild(pre);
    const cps = Array.from(text), u16 = [0]; for (const c of cps) u16.push(u16[u16.length - 1] + c.length);   // code point -> UTF-16 offset
    const toCp = u => { let lo = 0, hi = cps.length; while (lo < hi) { const m = (lo + hi + 1) >> 1; if (u16[m] <= u) lo = m; else hi = m - 1; } return lo; };
    const paint = () => {
      const list = items(), cuts = new Set([0, cps.length]);
      for (const s of list) { cuts.add(clamp(s.start, 0, cps.length)); cuts.add(clamp(s.end, 0, cps.length)); }
      const at = [...cuts].sort((a, b) => a - b), frag = document.createDocumentFragment();
      for (let j = 0; j + 1 < at.length; j++) {
        const a = at[j], b = at[j + 1], piece = cps.slice(a, b).join(''), over = list.map((s, i) => [s, i]).filter(([s]) => s.start <= a && s.end >= b);
        if (!over.length) frag.appendChild(document.createTextNode(piece));
        else { const m = h('mark', 'ann-span' + (over.some(([, i]) => i === here.pick) ? ' sel' : '') + (over.length > 1 ? ' many' : ''), piece); m.dataset.i = String(over[over.length - 1][1]); m.title = over.map(([s, i]) => (i + 1) + ' ' + s.term).join(', '); frag.appendChild(m); }
        for (const [s, i] of list.map((s, i) => [s, i])) if (s.end === b) { const tag = h('span', 'ann-tag' + (i === here.pick ? ' sel' : ''), (i + 1) + ' ' + s.term); tag.setAttribute('aria-hidden', 'true'); tag.contentEditable = 'false'; frag.appendChild(tag); }
      }
      pre.replaceChildren(frag);
    };
    el._hooks.repaint = paint;
    /** The UTF-16 offset in the text of a place in pre, the tags left out. */
    const offsetOf = (node, offset) => { const range = document.createRange(); range.setStart(pre, 0); range.setEnd(node, offset); const f = range.cloneContents(); for (const x of f.querySelectorAll('.ann-tag')) x.remove(); return f.textContent.length; };
    const mark = () => {
      if (!may) return false;
      const s = getSelection(); if (!s.rangeCount || s.isCollapsed) return false;
      const range = s.getRangeAt(0); if (!pre.contains(range.startContainer) || !pre.contains(range.endContainer)) return false;
      let a = toCp(offsetOf(range.startContainer, range.startOffset)), b = toCp(offsetOf(range.endContainer, range.endOffset)); if (a > b) [a, b] = [b, a];
      if (a === b) return false;
      const list = items(); list.push({ term: newTerm(t), start: a, end: b }); here.pick = list.length - 1;
      s.removeAllRanges(); touch(); return true;
    };
    pre.addEventListener('mouseup', () => { mark(); });
    pre.addEventListener('click', e => { const m = e.target.closest && e.target.closest('mark.ann-span'); if (m && getSelection().isCollapsed) pickItem(Number(m.dataset.i)); });
    if (may) { const row = h('div', 'iv-ctl'); row.appendChild(button('btn sm', 'Mark the selected text', 'ann:mark', () => { if (!mark()) say.textContent = 'Select a stretch of the text first.'; })); const say = h('span', 'small faint', 'Select a stretch of the text to mark it as a span of the term chosen in the form.'); say.setAttribute('aria-live', 'polite'); row.appendChild(say); el.appendChild(row); }
    paint();
    el._hooks.textOf = (a, b) => cps.slice(a, b).join('');
  }

  // Segments, drawn on the waveform. Times are seconds of the sound.
  function segmentView(el, got, t, rec) {
    const r = got.record, k = got.content || {}, may = A.may('edit'), items = () => itemsOf(t, rec);
    if (k.seconds == null || !k.peaks || !k.peaks.length) {
      el.appendChild(heading(r.id, 'Sound'));
      el.appendChild(h('p', 'note', 'Tuldok reads a sound\'s length from a WAV only, so segments cannot be drawn on this one; its viewer is below.'));
      V.record(el, got, t.run, store); return;
    }
    const secs = k.seconds;
    el.appendChild(heading(r.id, [secs.toFixed(secs < 10 ? 2 : 1) + ' s', k.rate.toLocaleString('en-GB') + ' Hz', count(k.channels, 'channel'), bytes(r.bytes)].join(' · ')));
    const cv = h('canvas', 'ann-surface ann-wave'); cv.tabIndex = 0; cv.dataset.key = 'ann:surface'; cv.setAttribute('role', 'application');
    cv.setAttribute('aria-label', 'Waveform of ' + r.id + ', ' + secs.toFixed(2) + ' seconds, with its segments. ' + (may ? 'Drag to mark a segment, drag a segment to move it, an end to move that end. N adds a segment, [ and ] choose one, the arrows move it, Shift and the arrows move its end, P plays it, Delete removes it.' : ''));
    const said = h('p', 'sr-only'); said.setAttribute('aria-live', 'polite');
    const audio = h('audio'); audio.controls = true; audio.preload = 'metadata'; audio.src = r.url; audio.dataset.key = 'ann:audio'; audio.setAttribute('aria-label', 'Play ' + r.id);
    el.appendChild(cv); el.appendChild(audio); el.appendChild(said);
    if (may) el.appendChild(h('p', 'small faint ann-help', 'Drag on the waveform to mark a segment; drag a segment to move it, an end to move that end. With the waveform focused: N adds a segment, [ and ] choose one, the arrows move it by 0.05 s (Alt: by 0.5 s), Shift and the arrows move its end, P plays it, Delete removes it.'));
    let frame = 0, drag = null, stopAt = null;
    const paint = () => {
      frame = 0;
      const size = V.fit(cv, 120); if (!size) return; const [W, H] = size, dpr = window.devicePixelRatio || 1, ctx = cv.getContext('2d');
      ctx.clearRect(0, 0, W, H); V.wave(ctx, W, H, k.peaks);
      const list = items(), mark = V.token('--k-refinement'), acc = V.token('--accent'), ink = V.token('--accent-ink');
      ctx.font = fontOf(Math.round(11.5 * dpr)); ctx.textBaseline = 'top';
      list.forEach((s, i) => {
        const on = i === here.pick, x0 = s.start / secs * W, x1 = s.end / secs * W, c = on ? acc : mark;
        ctx.fillStyle = rgb(c, on ? 0.26 : 0.16); ctx.fillRect(x0, 0, Math.max(1, x1 - x0), H);
        ctx.fillStyle = rgb(c); ctx.fillRect(x0, 0, Math.max(1, dpr * (on ? 2 : 1)), H); ctx.fillRect(x1 - Math.max(1, dpr * (on ? 2 : 1)), 0, Math.max(1, dpr * (on ? 2 : 1)), H);
        const label = (i + 1) + ' ' + s.term, tw = ctx.measureText(label).width + 8 * dpr;
        ctx.fillRect(x0, 0, tw, 16 * dpr); ctx.fillStyle = rgb(ink); ctx.fillText(label, x0 + 4 * dpr, 2 * dpr);
      });
      if (!audio.paused) { ctx.fillStyle = rgb(V.token('--ink')); ctx.fillRect(audio.currentTime / secs * W, 0, Math.max(1, dpr), H); }
      const s = list[here.pick], text = s ? 'Segment ' + (here.pick + 1) + ', ' + s.term + ', ' + s.start.toFixed(2) + ' to ' + s.end.toFixed(2) + ' seconds' : count(list.length, 'segment');
      if (said.textContent !== text) said.textContent = text;
    };
    const later = () => { if (!frame) frame = requestAnimationFrame(paint); };
    el._hooks.repaint = later;
    V.paints(cv, paint);
    const tick = () => { if (stopAt != null && audio.currentTime >= stopAt) { audio.pause(); stopAt = null; } later(); if (!audio.paused) requestAnimationFrame(tick); };
    audio.addEventListener('play', () => requestAnimationFrame(tick)); audio.addEventListener('pause', later);
    el._hooks.play = i => { const s = items()[i]; if (!s) return; stopAt = s.end; audio.currentTime = s.start; const p = audio.play(); if (p && p.catch) p.catch(() => {}); };
    const round = v => Math.round(v * 1000) / 1000;
    const at = e => { const q = cv.getBoundingClientRect(); return clamp((e.clientX - q.left) / q.width * secs, 0, secs); };
    cv.addEventListener('pointerdown', e => {
      if (e.button !== 0 || !may) return;
      e.preventDefault(); cv.focus({ preventScroll: true });
      const p = at(e), list = items(), tol = 6 * secs / cv.clientWidth;
      let hit = null;
      const order = list.map((_, i) => i).reverse(); if (here.pick >= 0 && list[here.pick]) order.unshift(here.pick);
      for (const i of order) { const s = list[i]; if (Math.abs(p - s.start) <= tol) { hit = { mode: 'start', i }; break; } if (Math.abs(p - s.end) <= tol) { hit = { mode: 'end', i }; break; } }
      if (!hit) for (const i of order) { const s = list[i]; if (p > s.start && p < s.end) { hit = { mode: 'move', i }; break; } }
      if (!hit) { list.push({ term: newTerm(t), start: p, end: p }); hit = { mode: 'new', i: list.length - 1 }; }
      drag = Object.assign(hit, { from: p, orig: Object.assign({}, list[hit.i]), id: e.pointerId, moved: false });
      here.pick = hit.i; cv.setPointerCapture(e.pointerId); later();
    });
    cv.addEventListener('pointermove', e => {
      if (!drag || e.pointerId !== drag.id) return;
      const p = at(e), s = items()[drag.i], o = drag.orig; if (!s) return;
      drag.moved = true;
      if (drag.mode === 'new') { s.start = Math.min(drag.from, p); s.end = Math.max(drag.from, p); }
      else if (drag.mode === 'move') { const len = o.end - o.start, a = clamp(o.start + p - drag.from, 0, secs - len); s.start = a; s.end = a + len; }
      else { const fixed = drag.mode === 'start' ? o.end : o.start; s.start = Math.min(fixed, p); s.end = Math.max(fixed, p); }
      later();
    });
    const end = e => {
      if (!drag || e.pointerId !== drag.id) return;
      const list = items(), s = list[drag.i], d = drag; drag = null;
      if (!s) return;
      s.start = round(s.start); s.end = round(s.end);
      if (s.end - s.start < 0.01) { if (d.mode === 'new') { list.splice(d.i, 1); here.pick = -1; if (here.relist) here.relist(); later(); return; } s.end = round(Math.min(secs, s.start + 0.01)); }
      if (!d.moved) { if (here.relist) here.relist(); later(); return; }
      touch();
    };
    cv.addEventListener('pointerup', end); cv.addEventListener('pointercancel', end);
    cv.addEventListener('keydown', e => {
      if (!may) return;
      if ((e.key === 'p' || e.key === 'P') && items()[here.pick]) { e.preventDefault(); el._hooks.play(here.pick); return; }
      surfaceKeys(e, items, () => { const a = round(clamp(audio.currentTime || 0, 0, Math.max(0, secs - 0.25))); return { term: newTerm(t), start: a, end: round(Math.min(secs, a + 0.25)) }; }, (s, key, shift, alt) => {
        const step = alt ? 0.5 : 0.05, d = key === 'ArrowLeft' || key === 'ArrowDown' ? -step : step;
        if (shift) s.end = round(clamp(s.end + d, s.start + 0.01, secs));
        else { const len = s.end - s.start; s.start = round(clamp(s.start + d, 0, secs - len)); s.end = round(s.start + len); }
      });
    });
  }

  // ---- The form ----------------------------------------------------------------------------------------------------
  function buildForm(t, rec, detail) {
    here.relist = null;
    const d = draftOf(t, rec, true), a = rec.annotation, may = A.may('edit'), fits = !ONLY[t.type] || ONLY[t.type].includes(rec.kind);
    const form = h('div', 'inspector ann-formbox');
    const hd = h('header'); hd.appendChild(h('span', 'kicker', t.title + ' · ' + t.type));
    const t2 = h('h2', 'mono', rec.id); t2.tabIndex = -1; hd.appendChild(t2);
    const meta = h('div', 'ins-meta'), [tone, word] = STATE[marked(a)]; meta.appendChild(S.stateEl(tone, word));
    if (a && a.stale) meta.appendChild(h('span', 'ann-flag stale', 'stale'));
    if (a && a.unsaved) meta.appendChild(h('span', 'ann-flag unsaved', 'unsaved'));
    const um = h('span', 'umark' + (d.dirty ? ' typed' : ''), d.dirty ? 'not kept yet' : ''); meta.appendChild(um);
    hd.appendChild(meta);
    if (a) hd.appendChild(h('p', 'small faint', (a.state === 'draft' ? 'Drafted' : 'Annotated') + ' by ' + a.by + ' · ' + time(a.at)));
    form.appendChild(hd);
    if (a && a.stale) {
      const box = h('div', 'ann-stale'); box.setAttribute('role', 'status');
      box.appendChild(h('p', null, rec.in_product ? 'Stale: the record\'s content differs from what was annotated.' : 'Stale: the record is gone from the current product of ' + t.dataset + '.'));
      if (rec.in_product && detail && detail.annotation) box.appendChild(h('p', 'small mono', 'annotated ' + String(detail.annotation.sha256 || 'without a hash').slice(0, 12) + ' · now ' + String(detail.sha256 || 'not hashed').slice(0, 12)));
      box.appendChild(h('p', 'small', rec.in_product ? 'The annotation as it was made is below. Still right keeps it for the content as it is now; or change it and keep it.' : 'Remove the annotation, or keep it until the record comes back.'));
      form.appendChild(box);
    }
    if (may && rec.in_product && ((here.offers || {})[rec.kind] || []).length) { const sb = h('div', 'ann-suggestbox'); sb.appendChild(suggestBox(t, rec)); form.appendChild(sb); }
    const f = h('div', 'form ann-fields');
    if (!rec.in_product) f.appendChild(h('p', 'note', 'Nothing can be set on a record that is not in the product.'));
    else if (rec.kind === 'file') f.appendChild(h('p', 'note', 'A file of no kind cannot be annotated.'));
    else if (!fits) f.appendChild(h('p', 'note', 'This task annotates ' + ONLY[t.type].join(' or ') + ' records; this record is ' + (V.WORD[rec.kind] || rec.kind).toLowerCase() + ', so only a decision and a note can be kept for it.'));
    if (rec.in_product && rec.kind !== 'file' && fits) valueControls(f, t, rec, d, may);
    // The decision.
    const dl = h('div', 'ann-field'); dl.appendChild(h('h3', null, 'Decision'));
    const seg = h('div', 'seg ann-decide'); seg.setAttribute('role', 'group'); seg.setAttribute('aria-label', 'Decision');
    for (const [v, label, cls] of DECISIONS) {
      const b = button(cls, label, 'ann:decide-' + v, () => { d.state = d.state === v ? null : v; for (const x of seg.children) x.setAttribute('aria-pressed', String(x.dataset.key === 'ann:decide-' + d.state)); touch(false); });
      b.setAttribute('aria-pressed', String(d.state === v)); b.disabled = !may || !rec.in_product; seg.appendChild(b);
    }
    dl.appendChild(seg); dl.appendChild(h('p', 'small faint', 'Without a decision, Keep and next keeps a draft.')); f.appendChild(dl);
    const nl = h('label'); nl.appendChild(document.createTextNode('Note'));
    const note = h('textarea'); note.rows = 2; note.maxLength = 4000; note.value = d.note; note.dataset.key = 'ann:note'; note.disabled = !may || !rec.in_product; note.placeholder = 'optional';
    note.addEventListener('input', () => { d.note = note.value; touch(false); }); nl.appendChild(note); f.appendChild(nl);
    form.appendChild(f);
    // Keep and next, Skip, Revert, Still right, Remove; a refusal is shown under them in the server's words.
    const slot = A.slot('annotate:form'); if (slot.for !== draftKey(t, rec)) { slot.refusal = null; slot.confirming = null; slot.for = draftKey(t, rec); }
    const k = draftKey(t, rec), after = () => { drafts.delete(k); };
    form.appendChild(A.group('annotate:form', [
      { id: 'keep', label: 'Keep and next', cls: 'btn primary', who: 'edit', op: 'set_annotation', busy: 'Keeping…', hidden: !rec.in_product, title: 'Enter',
        args: () => Object.assign({ task: t.task, items: [itemOf(t, rec, d)] }, d.from ? { from: d.from } : {}), done: () => { after(); move(1); } },
      { id: 'skip', label: 'Skip', cls: 'btn ghost', onClick: () => { if (move(1)) redraw(); } },
      { id: 'still', label: 'Still right', cls: 'btn', who: 'edit', op: 'set_annotation', busy: 'Keeping…', hidden: !(a && a.stale && rec.in_product),
        args: () => ({ task: t.task, items: [Object.assign({ record: rec.id, state: a.state, value: a.value }, a.note ? { note: a.note } : {})] }), done: after },
      { id: 'remove', label: 'Remove the annotation', cls: 'btn', who: 'edit', op: 'set_annotation', busy: 'Removing…', hidden: !(a && !rec.in_product),
        confirm: 'Remove the annotation of ' + rec.id + '; Save removes its line from the file.', args: () => ({ task: t.task, items: [{ record: rec.id, remove: true }] }), done: after },
      { id: 'revert', label: 'Revert', cls: 'btn ghost', who: 'edit', op: 'revert_annotations', busy: 'Reverting…', hidden: !(a && a.unsaved),
        confirm: 'Put back the saved annotation of ' + rec.id + ' in place of its unsaved one' + '; a record with no saved annotation has none again.', args: () => ({ task: t.task, records: [rec.id] }), done: after }
    ]));
    if (!may) form.appendChild(h('p', 'note', 'This session may look but not annotate: that needs the right to edit.'));
    else form.appendChild(h('p', 'note', 'Keep and next keeps the annotation in Tuldok as an unsaved edit; Save writes every task\'s annotations to its file.'));
    return form;
  }

  /** The controls of the value, by task. */
  function valueControls(f, t, rec, d, may) {
    if (t.type === 'review') return;
    if (GENERATED.includes(t.type)) {   // spec-t4: made by annotators and reviewed; the value is shown, not drawn here
      const box = h('div', 'ann-field'); box.appendChild(h('h3', null, 'Value'));
      box.appendChild(h('p', null, window.LabReview.summary(t, d.value)));
      box.appendChild(h('p', 'small faint', here.sets && here.sets.some(x => x.set !== 'kept') ? 'This task\'s annotations are made by annotators: choose Review in the bar to compare their sets and keep one.' : 'This task\'s annotations are made by annotators (a dataset with the step annotate); the decision and the note can be kept here.'));
      f.appendChild(box); return;
    }
    if (t.type === 'text') {
      const l = h('label'); l.appendChild(document.createTextNode('Text'));
      const area = h('textarea'); area.rows = 5; area.value = d.value || ''; area.dataset.key = 'ann:text'; area.disabled = !may; area.placeholder = 'a caption, a transcript or a summary';
      area.addEventListener('input', () => { d.value = area.value; touch(false); }); l.appendChild(area); f.appendChild(l); return;
    }
    if (t.type === 'class' || t.type === 'tags') {
      const one = t.type === 'class', box = h('div', 'ann-field'); box.appendChild(h('h3', null, one ? 'Term' : 'Terms'));
      const rd = h('div', 'radio ann-terms'); rd.setAttribute('role', one ? 'radiogroup' : 'group'); rd.setAttribute('aria-label', one ? 'Term' : 'Terms');
      t.vocabulary.forEach((term, i) => {
        const l = h('label'), inp = h('input'); inp.type = one ? 'radio' : 'checkbox'; inp.name = 'ann-term'; inp.value = term; inp.dataset.key = 'ann:term-' + i; inp.disabled = !may;
        inp.checked = one ? d.value === term : d.value.includes(term);
        inp.addEventListener('change', () => { if (one) { if (inp.checked) d.value = term; } else d.value = inp.checked ? d.value.concat([term]) : d.value.filter(x => x !== term); touch(false); });
        l.appendChild(inp); l.appendChild(h('span', null, term)); if (i < 9) l.appendChild(kbd(String(i + 1))); rd.appendChild(l);
      });
      box.appendChild(rd); f.appendChild(box); return;
    }
    // Boxes, spans and segments: the term of new ones, and the list of those drawn.
    const box = h('div', 'ann-field');
    const what = { boxes: ['Boxes', 'box', 'boxes'], spans: ['Spans', 'span', 'spans'], segments: ['Segments', 'segment', 'segments'] }[t.type];
    const tl = h('label', 'ann-newterm'); tl.appendChild(document.createTextNode('Term of new ' + what[2]));
    const ts = h('select'); ts.dataset.key = 'ann:new-term'; ts.disabled = !may;
    for (const term of t.vocabulary) { const o = h('option', null, term); o.value = term; o.selected = term === newTerm(t); ts.appendChild(o); }
    ts.addEventListener('change', () => { ui.terms.set(t.task, ts.value); });
    tl.appendChild(ts); box.appendChild(tl);
    box.appendChild(h('h3', null, what[0]));
    const listBox = h('div', 'ann-itembox'); box.appendChild(listBox);
    const relist = () => putInPlace(listBox, itemList(t, d, what, may));
    here.relist = relist; listBox.appendChild(itemList(t, d, what, may));
    f.appendChild(box);
  }
  function itemList(t, d, what, may) {
    const list = d.value;
    if (!list.length) return h('p', 'note', 'No ' + what[2] + ' yet. ' + { boxes: 'Drag on the image to draw one.', spans: 'Select a stretch of the text to mark one.', segments: 'Drag on the waveform to mark one.' }[t.type]);
    const ul = h('ul', 'ann-items');
    list.forEach((it, i) => {
      const row = h('li', i === here.pick ? 'sel' : null); row.dataset.i = String(i);
      const pick = button('linkish', (i + 1) + '', 'ann:item-' + i, () => { pickItem(here.pick === i ? -1 : i); }); pick.setAttribute('aria-label', 'Choose ' + what[1] + ' ' + (i + 1)); pick.setAttribute('aria-pressed', String(i === here.pick)); row.appendChild(pick);
      const li = h('span', 'ann-fields'); row.appendChild(li);   // the term, the place and Remove, after the number
      const ts = h('select'); ts.dataset.key = 'ann:item-' + i + '-term'; ts.setAttribute('aria-label', 'Term of ' + what[1] + ' ' + (i + 1)); ts.disabled = !may;
      for (const term of t.vocabulary.includes(it.term) ? t.vocabulary : [it.term].concat(t.vocabulary)) { const o = h('option', null, term); o.value = term; o.selected = term === it.term; ts.appendChild(o); }
      ts.addEventListener('change', () => { it.term = ts.value; touch(); }); li.appendChild(ts);
      const num = (name, label, step, lo, hi) => {
        const n = h('input'); n.type = 'number'; n.step = String(step); n.value = String(it[name]); n.dataset.key = 'ann:item-' + i + '-' + name; n.setAttribute('aria-label', label + ' of ' + what[1] + ' ' + (i + 1)); n.disabled = !may; n.className = 'ann-num';
        n.addEventListener('change', () => { const v = Number(n.value); if (!Number.isFinite(v)) { n.value = String(it[name]); return; } it[name] = clamp(step === 1 ? Math.round(v) : Math.round(v * 1000) / 1000, lo(), hi()); if (it.start !== undefined && it.end <= it.start) it.end = Math.min(hi(), it.start + (step === 1 ? 1 : 0.01)); touch(); });
        return n;
      };
      if (t.type === 'boxes') li.appendChild(h('span', 'mono small ann-coords', 'x ' + it.x + ', y ' + it.y + ' · ' + it.w + ' × ' + it.h));
      if (t.type === 'spans') {
        const n = here.textOf ? Array.from(here.textOf(0, 1e9)).length : 1e9;
        li.appendChild(num('start', 'Start', 1, () => 0, () => Math.max(0, it.end - 1))); li.appendChild(num('end', 'End', 1, () => it.start + 1, () => n));
        li.appendChild(h('q', 'ann-covered', here.textOf ? here.textOf(it.start, it.end) : ''));
      }
      if (t.type === 'segments') {
        li.appendChild(num('start', 'Start (s)', 0.01, () => 0, () => Math.max(0, it.end - 0.01))); li.appendChild(num('end', 'End (s)', 0.01, () => it.start + 0.01, () => 1e9));
        const tx = h('input'); tx.type = 'text'; tx.value = it.text || ''; tx.placeholder = 'what is said (optional)'; tx.dataset.key = 'ann:item-' + i + '-text'; tx.setAttribute('aria-label', 'What is said in segment ' + (i + 1)); tx.disabled = !may; tx.className = 'ann-saying';
        tx.addEventListener('input', () => { it.text = tx.value; touch(false); }); li.appendChild(tx);
        li.appendChild(button('btn sm', 'Play', 'ann:item-' + i + '-play', () => { if (here.play) here.play(i); }));
      }
      const rm = button('btn sm ghost', 'Remove', 'ann:item-' + i + '-remove', () => { list.splice(i, 1); here.pick = -1; touch(); }); rm.disabled = !may; rm.setAttribute('aria-label', 'Remove ' + what[1] + ' ' + (i + 1)); li.appendChild(rm);
      ul.appendChild(row);
    });
    return ul;
  }

  // ---- Suggestions (spec-d5 section 4) ----------------------------------------------------------------------------
  // Suggest asks the chosen model (suggestion_models' offers for the record's kind) for a value of the task for the
  // record on screen. The answer fills the record's draft with its `from`, marked as the model's suggestion until the
  // person changes or keeps it; Keep sends `from` with set_annotation, so the saved line names the model. Cancel drops
  // the answer when it comes (the endpoint is not told: no operation stops a suggestion). A refusal is shown beside the
  // form, which is left as it was. Suggest for this page asks, one record after another, for the records on screen that
  // have no annotation and no typed draft, and keeps each answer as a draft with its `from`. The model chosen is
  // remembered per task and kind of record while the page is open. A reading never asks anything.
  const sug = { choice: new Map(), asking: null, refusals: new Map(), batch: null, said: new Map(), turn: 0 };
  const offerKey = o => o.model + '\u0000' + o.profile;
  /** The model chosen for the task and kind: the one picked while the page is open, else the first offered. */
  function chosen(t, kind) { const list = (here && here.offers || {})[kind] || [], k = sug.choice.get(t.task + '\n' + kind); return list.find(o => offerKey(o) === k) || list[0] || null; }
  const fromWords = f => f.model + ' · ' + f.profile;
  function suggestionLine(d) {
    const same = JSON.stringify(valueOf(here.t, d)) === d.fromValue;
    return [same ? 'Suggested by ' + fromWords(d.from) + ' (' + d.from.capability + '): check it, change it or keep it.' : 'Changed from the suggestion of ' + fromWords(d.from) + '; kept, the line still names it.', same];
  }
  /** Sets the suggestion's mark in place: a suggestion, or one the person changed. */
  function markSuggestion(d) {
    const m = here.root && here.root.querySelector('.ann-form .ann-sugmark'); if (!m) return;
    const [text, same] = suggestionLine(d);
    if (m.textContent !== text) m.textContent = text;
    if (m.classList.contains('changed') === same) m.classList.toggle('changed', !same);
  }
  function suggestBox(t, rec) {
    const box = h('div', 'ann-suggest'), list = here.offers[rec.kind] || [], k = draftKey(t, rec), d = drafts.get(k);
    const asking = sug.asking && sug.asking.key === k ? sug.asking : null, batch = sug.batch && sug.batch.task === t.task ? sug.batch : null;
    const row = h('div', 'ann-suggest-row');
    const l = h('label', 'ann-suggest-model'); l.appendChild(document.createTextNode('Suggest with'));
    const sel = h('select'); sel.dataset.key = 'ann:suggest-model'; const pick = chosen(t, rec.kind);
    for (const o of list) { const op = h('option', null, fromWords(o) + ' (' + o.capability + ')'); op.value = offerKey(o); op.selected = !!pick && offerKey(o) === offerKey(pick); sel.appendChild(op); }
    sel.disabled = !!asking || !!batch;
    sel.addEventListener('change', () => { sug.choice.set(t.task + '\n' + rec.kind, sel.value); });
    l.appendChild(sel); row.appendChild(l);
    if (asking) {
      const b = button('btn sm', 'Asking ' + asking.model + '…', 'ann:suggest'); b.disabled = true; b.setAttribute('aria-busy', 'true'); row.appendChild(b);
      row.appendChild(button('btn sm ghost', 'Cancel', 'ann:suggest-cancel', () => { sug.asking = null; reboxed(t, rec, 'ann:suggest'); }));
    } else { const b = button('btn sm', 'Suggest', 'ann:suggest', () => ask(t, rec)); b.disabled = !!batch || !!sug.asking; row.appendChild(b); }
    box.appendChild(row);
    if (d && d.from) { const [text, same] = suggestionLine(d); const m = h('p', 'small ann-sugmark' + (same ? '' : ' changed'), text); m.setAttribute('role', 'status'); box.appendChild(m); }
    const refusal = sug.refusals.get(k);
    if (refusal) { const r = A.refusal(refusal); r.classList.add('ann-sugrefusal'); r.insertBefore(h('p', 'small', 'No suggestion: the form is as it was.'), r.children[1] || null); box.appendChild(r); }
    const page = h('div', 'ann-suggest-row ann-batch');
    if (batch) {
      const line = h('span', 'small ann-batch-line', batchWords(batch)); line.setAttribute('role', 'status'); page.appendChild(line);
      const stop = button('btn sm ghost', batch.stop ? 'Stopping…' : 'Stop', 'ann:suggest-stop', () => { batch.stop = true; reboxed(t, rec, 'ann:suggest-stop'); }); stop.disabled = batch.stop; page.appendChild(stop);
    } else {
      const b = button('btn sm', 'Suggest for this page', 'ann:suggest-page', () => suggestPage(t)); b.disabled = !!sug.asking; page.appendChild(b);
      const said = sug.said.get(t.task);
      page.appendChild(h('span', 'small faint ann-batch-line', said || 'Asks for each record on this page with no annotation, one after another, and keeps each answer as a draft.'));
    }
    box.appendChild(page);
    return box;
  }
  const shows = (t, rec) => !!(here && here.root && here.root.isConnected && here.t && here.rec && here.t.task === t.task && here.rec.id === rec.id);
  /** The suggestion part of the form on screen, drawn again in place; the focus goes to focus when it was lost. */
  function reboxed(t, rec, focus) {
    if (!shows(t, rec)) return;
    const w = here.parts.form && here.parts.form.querySelector('.ann-suggestbox'); if (!w) return;
    const r = putInPlace(w, suggestBox(t, rec));
    if (focus && (!r.inside || !r.found || document.activeElement === document.body)) A.focusKey(focus);
  }
  const rebox = focus => { if (here && here.t && here.rec) reboxed(here.t, here.rec, focus); };
  async function ask(t, rec) {
    const o = chosen(t, rec.kind); if (!o || sug.asking || sug.batch) return;
    const k = draftKey(t, rec), mine = { key: k, model: o.model, n: ++sug.turn };
    sug.asking = mine; sug.refusals.delete(k); reboxed(t, rec, 'ann:suggest-cancel');
    let got = null, error = null;
    try { got = await P.call('suggest_annotation', { task: t.task, record: rec.id, model: o.model, profile: o.profile }); } catch (e) { error = e; }
    if (sug.asking !== mine) return;   // cancelled: the answer is dropped
    sug.asking = null;
    if (error) { sug.refusals.set(k, error); reboxed(t, rec, 'ann:suggest'); return; }
    fill(t, rec, got.suggestion);
    if (shows(t, rec)) { here.keys.form = null; here.focusAfter = 'ann:suggest'; redraw(); }
  }
  /** The suggestion in the record's draft, with its `from`; what was decided and noted stays. */
  function fill(t, rec, s) {
    const d = draftOf(t, rec);
    if (t.type === 'text') d.value = typeof s.value === 'string' ? s.value : '';
    else if (t.type === 'class') d.value = typeof s.value === 'string' ? s.value : null;
    else if (t.type === 'tags') d.value = Array.isArray(s.value) ? s.value.slice() : [];
    d.from = s.from; d.fromValue = JSON.stringify(valueOf(t, d)); d.dirty = true;
  }
  const batchWords = b => 'Asking for ' + Math.max(1, b.at) + ' of ' + count(b.total, 'record') + ' · ' + b.kept + ' kept, ' + b.refused + ' refused';
  function progress(b) { const line = here && here.root && here.root.querySelector('.ann-form .ann-batch-line'); const text = batchWords(b); if (line && line.textContent !== text) line.textContent = text; }
  /** Suggest for this page: each record on screen with no annotation and no typed draft, one after another, kept as a draft. */
  async function suggestPage(t) {
    if (sug.batch || sug.asking || !here.page) return;
    const todo = here.page.records.filter(r => r.in_product && !r.annotation && chosen(t, r.kind) && !(drafts.get(draftKey(t, r)) || {}).dirty);
    const b = sug.batch = { task: t.task, total: todo.length, at: 0, kept: 0, refused: 0, first: null, stop: false };
    sug.said.delete(t.task); rebox('ann:suggest-stop');
    for (const r of todo) {
      if (b.stop) break;
      b.at++; progress(b);
      const o = chosen(t, r.kind);
      try {
        const got = await P.call('suggest_annotation', { task: t.task, record: r.id, model: o.model, profile: o.profile });
        if (b.stop) break;   // stopped while it was asked: the answer is dropped
        await P.call('set_annotation', { task: t.task, from: got.suggestion.from, items: [{ record: r.id, state: 'draft', value: got.suggestion.value }] });
        b.kept++;
        P.forgetBut(P.WATCHED); here.act.refresh();   // the grid shows the new draft
      } catch (error) { b.refused++; if (!b.first) b.first = r.id + ': ' + error.message; }
      progress(b);
    }
    sug.batch = null;
    sug.said.set(t.task, (b.stop ? 'Stopped. ' : 'Done. ') + 'Kept ' + count(b.kept, 'draft') + ', ' + b.refused + ' refused, of ' + count(b.total, 'record') + ' with no annotation' + (b.first ? '. First refused: ' + b.first : '.'));
    rebox('ann:suggest-page');
  }

  // ---- Keys --------------------------------------------------------------------------------------------------------
  function onKey(e) {
    if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey || !here || !here.root || !here.root.isConnected || !here.rec) return;
    const t = e.target, choice = !!(t && t.matches && t.matches('input[type="radio"], input[type="checkbox"]'));   // a term or a tag: its keys are the form's but the arrows
    if (t && t.closest && t.closest('#aside, #needs-panel, dialog, .session-bar, audio, .turns, .ann-surface')) return;
    if (!choice && t && t.closest && t.closest('input, select, textarea, [contenteditable="true"]')) return;
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { if (choice) return; e.preventDefault(); if (move(e.key === 'ArrowRight' ? 1 : -1, !!(t.classList && t.classList.contains('rec')))) redraw(); return; }
    if (e.key === 'Enter') { if (t.closest && t.closest('button, a, summary, [role="button"]') && !t.closest('.ann-decide')) return; const b = here.parts.form && here.parts.form.querySelector('[data-key="annotate:form:keep"]'); if (b && !b.disabled) { e.preventDefault(); b.click(); } return; }
    if (/^[1-9]$/.test(e.key) && ['class', 'tags'].includes(here.t.type)) {
      const box = here.parts.form && here.parts.form.querySelector('[data-key="ann:term-' + (Number(e.key) - 1) + '"]');
      if (!box || box.disabled) return;
      e.preventDefault(); if (here.t.type === 'class') box.checked = true; else box.checked = !box.checked;
      box.dispatchEvent(new Event('change'));
    }
  }
  window.addEventListener('keydown', onKey);

  // ---- Forms in the drawer: a new task, an import, a freeze -------------------------------------------------------
  /** A form in the drawer for sel: drawn once, and again only after a control's answer, from what its slot keeps. */
  function formDrawer(aside, sel, load, build) {
    if (aside._for === sel && aside._again !== 'control') return;
    const same = aside._for === sel && !!aside.firstChild, mine = turn(aside);
    aside._for = sel; aside._editing = null;
    if (!same) { aside.textContent = ''; aside.appendChild(h('p', 'note', 'Reading…')); }
    load().then(value => { if (aside._turn !== mine || aside._for !== sel) return; const ins = h('div', 'inspector ann-new'); build(ins, value); putDrawer(aside, ins); },
      error => { if (aside._turn !== mine || aside._for !== sel) return; putDrawer(aside, A.refusal(error)); });
  }
  const slug = text => text.toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 64).replace(/-+$/, '');
  /** A labelled field whose value lives in the slot s under name. */
  function input(s, key, name, label, { type = 'text', hint, max, placeholder, area, value, onInput } = {}) {
    const l = h('label'); l.appendChild(document.createTextNode(label));
    const i = area ? h('textarea') : h('input'); if (!area) i.type = type; else i.rows = area;
    if (max) i.maxLength = max; if (placeholder) i.placeholder = placeholder; i.autocomplete = 'off'; i.spellcheck = false;
    i.dataset.key = key + ':field:' + name; i.value = s.text[name] != null ? s.text[name] : value || '';
    if (s.text[name] == null && value) s.text[name] = value;
    i.addEventListener('input', () => { s.text[name] = i.value; if (onInput) onInput(i.value); });
    l.appendChild(i); if (hint) l.appendChild(h('span', 'hint', hint)); return l;
  }
  function choice(s, key, name, label, options, fallback, onChange) {
    const l = h('label'); l.appendChild(document.createTextNode(label));
    const sel = h('select'); sel.dataset.key = key + ':field:' + name;
    if (s.text[name] == null || !options.some(o => o[0] === s.text[name])) s.text[name] = fallback;
    for (const [v, text] of options) { const o = h('option', null, text); o.value = v; o.selected = v === s.text[name]; sel.appendChild(o); }
    sel.addEventListener('change', () => { s.text[name] = sel.value; if (onChange) onChange(sel.value); });
    l.appendChild(sel); return l;
  }
  const lines = text => (text || '').split('\n').map(x => x.trim()).filter(Boolean);
  const header = (ins, kicker, title, lead) => { const hd = h('header'); hd.appendChild(h('span', 'kicker', kicker)); const t2 = h('h2', null, title); t2.tabIndex = -1; hd.appendChild(t2); ins.appendChild(hd); if (lead) ins.appendChild(h('p', 'note', lead)); };

  /** New task: title, name, dataset, task and vocabulary; kept as a new annotations/<name> definition. */
  function taskForm(aside, act) {
    formDrawer(aside, 'annotate:new-task', () => P.read('definitions', { kind: 'dataset' }), (ins, defs) => {
      const key = 'newtask', s = A.slot(key), sets = defs.definitions.filter(d => !d.removed);
      header(ins, 'new annotation task', 'A new task', 'A task says what is recorded about the records of one dataset. It is kept as a new definition, an unsaved edit, until Save writes it to annotations/<name>.json.');
      const f = h('div', 'form');
      let nameBox = null;
      f.appendChild(input(s, key, 'title', 'Title (required)', { max: 200, placeholder: 'What is recorded', onInput: () => { if (!s.text.nameTyped && nameBox) { nameBox.value = slug(s.text.title || ''); s.text.name = nameBox.value; } } }));
      const nl = input(s, key, 'name', 'Name', { max: 120, hint: 'a to z, 0 to 9, . _ -; the file is annotations/<name>.json', placeholder: 'made from the title', onInput: v => { s.text.nameTyped = !!v; } });
      nameBox = nl.querySelector('input'); if (!s.text.nameTyped) { nameBox.value = slug(s.text.title || ''); s.text.name = nameBox.value; }
      f.appendChild(nl);
      if (!sets.length) f.appendChild(h('p', 'failure', 'The project has no dataset: a task annotates the records of one.'));
      f.appendChild(choice(s, key, 'dataset', 'Dataset', sets.map(d => [d.reference, d.title + ' · ' + d.reference]), sets.length ? sets[0].reference : ''));
      const vocab = input(s, key, 'vocabulary', 'Vocabulary: one term per line', { area: 5, hint: '1 to 500 different terms of 1 to 200 characters', placeholder: 'clean\nnoisy\nbroken' });
      const points = input(s, key, 'keypoints', 'Keypoints: one name per line', { area: 4, hint: 'the points of one instance, in the order its values list them', placeholder: 'head\ntail' });
      const units = input(s, key, 'units', 'Units of depth', { max: 40, placeholder: 'm' });
      const mode = choice(s, key, 'mask', 'A pixel\'s value is', [['semantic', 'its class (semantic)'], ['instance', 'one object (instance)']], 'semantic');
      const showVocab = type => { vocab.hidden = !NEEDS_TERMS.includes(type); points.hidden = type !== 'keypoints'; units.hidden = type !== 'depth'; mode.hidden = type !== 'mask'; };
      f.appendChild(choice(s, key, 'task', 'Task', TYPES.map(x => [x, x + ' · ' + TYPE_WORD[x]]), 'class', showVocab));
      f.appendChild(vocab); f.appendChild(points); f.appendChild(units); f.appendChild(mode); showVocab(s.text.task);
      ins.appendChild(f);
      const reference = () => 'annotations/' + (s.text.name || '').trim();
      ins.appendChild(A.group(key, [
        { id: 'keep', label: 'Keep', cls: 'btn primary', who: 'edit', op: 'set_definition', busy: 'Keeping…',
          args: st => {
            const doc = { format: FORMAT, kind: 'annotation', title: (st.text.title || '').trim(), dataset: st.text.dataset, task: st.text.task };
            if (NEEDS_TERMS.includes(st.text.task)) doc.vocabulary = lines(st.text.vocabulary);
            if (st.text.task === 'keypoints') doc.keypoints = lines(st.text.keypoints);
            if (st.text.task === 'depth') doc.units = (st.text.units || '').trim();
            if (st.text.task === 'mask' && st.text.mask === 'instance') doc.mask = 'instance';
            return { reference: reference(), text: textOf(doc) };
          },
          done: r => { ui.task = r.reference; ui.page = 0; ui.filter = 'all'; act.select(null); } },
        { id: 'back', label: 'Cancel', cls: 'btn ghost', onClick: () => act.select(null) }
      ]));
      ins.appendChild(h('p', 'note', 'Keep checks the definition and keeps it in Tuldok as an unsaved edit; Save writes it to the project folder.'));
    });
  }

  /** The Data tab's two forms (spec-d4 section 7): Import and Freeze, each kept as a new datasets/<name> definition. */
  function datasetForm(aside, which, act) {
    const freeze = which === 'freeze', key = 'new' + which, sel = 'data:new:' + which;
    if (!['import', 'freeze'].includes(which)) { aside.textContent = ''; aside._for = sel; aside.appendChild(h('p', 'empty', 'There is no form ' + which + ' here.')); return; }
    formDrawer(aside, sel, () => Promise.all([P.read('definitions', { kind: 'dataset' }), freeze ? P.annotations.tasks() : null]), (ins, [defs, tasks]) => {
      const s = A.slot(key), sets = defs.definitions.filter(d => !d.removed);
      header(ins, freeze ? 'new dataset · freeze' : 'new dataset · import', freeze ? 'Freeze a dataset' : 'Import files',
        freeze ? 'A dataset with splits made from another dataset\'s records and their annotations: the records the first task includes, ordered by the seed and cut by the shares. It reads the tasks\' annotations as saved and committed.'
          : 'A dataset of files on this machine: each file under the source (or each line, with lines) becomes a record. A source relative to the code root is read from the commit a build uses.');
      const f = h('div', 'form');
      let nameBox = null;
      f.appendChild(input(s, key, 'title', 'Title (required)', { max: 200, onInput: () => { if (!s.text.nameTyped && nameBox) { nameBox.value = slug(s.text.title || ''); s.text.name = nameBox.value; } } }));
      const nl = input(s, key, 'name', 'Name', { max: 120, hint: 'the file is datasets/<name>.json', placeholder: 'made from the title', onInput: v => { s.text.nameTyped = !!v; } });
      nameBox = nl.querySelector('input'); if (!s.text.nameTyped) { nameBox.value = slug(s.text.title || ''); s.text.name = nameBox.value; }
      f.appendChild(nl);
      if (!freeze) {
        f.appendChild(input(s, key, 'source', 'Source (required)', { hint: 'a directory: relative to the code root, or absolute (this machine only)', placeholder: 'data/photos' }));
        f.appendChild(input(s, key, 'pattern', 'Pattern', { hint: 'which files; empty: every file (**/*)', placeholder: '**/*.png' }));
        f.appendChild(choice(s, key, 'kind', 'Kind', [['', 'By each file\'s extension']].concat(['text', 'image', 'audio', 'pointcloud', 'mesh', 'array', 'file'].map(k => [k, 'Every file is ' + (V.WORD[k] || k).toLowerCase()])), ''));
        f.appendChild(input(s, key, 'rights', 'Rights (required)', { area: 2, max: 1000, hint: 'what may be done with the files', placeholder: 'Photographed by us; free to use.' }));
        const lab = h('label', 'check'), box = h('input'); box.type = 'checkbox'; box.checked = !!s.text.lines; box.dataset.key = key + ':field:lines';
        box.addEventListener('change', () => { s.text.lines = box.checked; }); lab.appendChild(box); lab.appendChild(document.createTextNode(' Each line of a text file is a record of its own')); f.appendChild(lab);
      } else {
        const ofTasks = h('div', 'ann-field');
        const drawTasks = ds => {
          const mine = tasks.tasks.filter(x => x.dataset === ds);
          if (!Array.isArray(s.text.tasks) || s.text.tasksOf !== ds) { s.text.tasks = mine.length ? [mine[0].task] : []; s.text.tasksOf = ds; }   // the dataset's first task, until the person chooses
          const box = h('div'); box.appendChild(h('h3', null, 'Its tasks'));
          if (!mine.length) box.appendChild(h('p', 'failure', ds ? ds + ' has no annotation task: a freeze takes its records by one.' : 'Choose the dataset first.'));
          for (const m of mine) {
            const lab = h('label', 'check'), c = h('input'); c.type = 'checkbox'; c.checked = s.text.tasks.includes(m.task); c.dataset.key = key + ':field:task-' + m.task;
            c.addEventListener('change', () => { s.text.tasks = c.checked ? s.text.tasks.concat([m.task]) : s.text.tasks.filter(x => x !== m.task); drawTasks(ds); });
            lab.appendChild(c); lab.appendChild(document.createTextNode(' ' + m.title + ' · ' + m.task + (s.text.tasks[0] === m.task ? ' (first: its states take a record in)' : ''))); box.appendChild(lab);
          }
          putInPlace(ofTasks, box);
        };
        const named = h('div', 'ann-field');
        // Records chosen on a map of embeddings (curation.js, spec-t5 section 5): only those are frozen.
        const drawNamed = ds => {
          const box = h('div');
          if (Array.isArray(s.text.records) && s.text.recordsOf === ds) {
            box.appendChild(h('p', 'small frz-records', 'Only the ' + s.text.records.length.toLocaleString('en-GB') + ' records chosen on the map: ' + s.text.records.slice(0, 3).join(', ') + (s.text.records.length > 3 ? ', …' : '') + '.'));
            const b = h('button', 'btn sm ghost', 'Freeze every record instead'); b.type = 'button'; b.dataset.key = key + ':field:records-clear';
            b.addEventListener('click', () => { s.text.records = null; drawNamed(ds); }); box.appendChild(b);
          }
          putInPlace(named, box);
        };
        f.appendChild(choice(s, key, 'dataset', 'The dataset whose records are frozen', sets.map(d => [d.reference, d.title + ' · ' + d.reference]), sets.length ? sets[0].reference : '', ds => { drawTasks(ds); drawNamed(ds); }));
        f.appendChild(named); drawNamed(s.text.dataset);
        f.appendChild(ofTasks); drawTasks(s.text.dataset);
        const two = h('div', 'two');
        two.appendChild(input(s, key, 'seed', 'Seed (required)', { type: 'number', value: '7', hint: 'an integer' }));
        two.appendChild(input(s, key, 'shares', 'Shares (required)', { value: 'train 8, validation 1, test 1', hint: 'each split and its relative size' }));
        f.appendChild(two);
        const st = h('div', 'ann-field'); st.appendChild(h('h3', null, 'Which states of the first task take a record in'));
        if (!Array.isArray(s.text.include)) s.text.include = ['accepted'];
        for (const [v, label] of [['accepted', 'Accepted'], ['needs-work', 'Needs work'], ['rejected', 'Rejected'], ['draft', 'Draft']]) {
          const lab = h('label', 'check'), c = h('input'); c.type = 'checkbox'; c.checked = s.text.include.includes(v); c.dataset.key = key + ':field:include-' + v;
          c.addEventListener('change', () => { s.text.include = c.checked ? s.text.include.concat([v]) : s.text.include.filter(x => x !== v); });
          lab.appendChild(c); lab.appendChild(document.createTextNode(' ' + label)); st.appendChild(lab);
        }
        f.appendChild(st);
      }
      ins.appendChild(f);
      const reference = () => 'datasets/' + (s.text.name || '').trim();
      ins.appendChild(A.group(key, [
        { id: 'keep', label: 'Keep', cls: 'btn primary', who: 'edit', op: 'set_definition', busy: 'Keeping…', args: st => ({ reference: reference(), text: textOf(freeze ? freezeDoc(st.text) : importDoc(st.text)) }),
          done: r => { act.select(r.reference); } },
        { id: 'back', label: 'Cancel', cls: 'btn ghost', onClick: () => act.select(null) }
      ]));
      ins.appendChild(h('p', 'note', 'Keep checks the definition and keeps it in Tuldok as an unsaved edit; Save writes it. Building it is planned and requested as any build is.'));
    });
  }
  /** The definition an import writes (docs/contracts/project-folder.md, Steps Tuldok provides). */
  function importDoc(x) {
    const settings = { source: (x.source || '').trim() };
    if ((x.pattern || '').trim()) settings.pattern = x.pattern.trim();
    if (x.kind) settings.kind = x.kind;
    settings.rights = (x.rights || '').trim();
    if (x.lines) settings.lines = true;
    return { format: FORMAT, kind: 'dataset', title: (x.title || '').trim(), run: { step: 'import', settings } };
  }
  /** The definition a freeze writes; shares are read from "train 8, validation 1, test 1". */
  function freezeDoc(x) {
    const shares = {};
    for (const part of String(x.shares || '').split(',').map(p => p.trim()).filter(Boolean)) {
      const m = /^(\S+)\s*[ :=]\s*(\d+)$/.exec(part);
      if (!m) throw Object.assign(Error('Shares are written as names and whole numbers, for example "train 8, validation 1, test 1"; "' + part + '" is not.'), { code: 'invalid' });
      shares[m[1]] = Number(m[2]);
    }
    const seed = Number(String(x.seed || '').trim());
    if (!Number.isInteger(seed) || String(x.seed || '').trim() === '') throw Object.assign(Error('The seed is a whole number.'), { code: 'invalid' });
    const settings = { seed, shares };
    if (Array.isArray(x.records) && x.records.length && x.recordsOf === x.dataset) settings.records = x.records.slice();
    const include = (x.include || []).slice().sort((a, b) => ['accepted', 'needs-work', 'rejected', 'draft'].indexOf(a) - ['accepted', 'needs-work', 'rejected', 'draft'].indexOf(b));
    if (!(include.length === 1 && include[0] === 'accepted')) settings.include = include;
    return { format: FORMAT, kind: 'dataset', title: (x.title || '').trim(), run: { step: 'freeze', inputs: { records: x.dataset }, annotations: (x.tasks || []).slice(), settings } };
  }

  /** The Freeze form filled in with records chosen on a map (curation.js): the dataset and only those records. */
  function fillFreeze(dataset, records) { const s = A.slot('newfreeze'); s.text.dataset = dataset; s.text.records = records.slice(); s.text.recordsOf = dataset; s.text.tasks = null; }

  /** Needs you: the Annotate tab opens on this task. */
  function choose(task) { ui.task = task; ui.page = 0; ui.filter = 'all'; }

  S.annotate = annotate;
  // The drawer forms' parts, for the Generate form (generate.js).
  const forms = { formDrawer, input, choice, header, slug, textOf };
  return { choose, datasetForm, forms, fillFreeze, redraw };
})();
