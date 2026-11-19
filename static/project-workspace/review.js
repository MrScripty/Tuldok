'use strict';
// Review mode of the Annotate tab (docs/plans/training-and-curation/spec-t4.md section 7): two of a task's annotation
// sets (the kept set and the annotators' products) compared. Left: the set choosers, side by side or overlaid, the
// confidence filter, the agreement of the two and the records they disagree on most. Middle: the record with each
// set drawn over it (masks, polygons, boxes, keypoints and depth on an image; point objects and 3-D boxes on a point
// cloud; timeseries and segments as bands under a sound or a series; tracks on an array's frames with a frame
// slider). Right: each set's value in words, this record's agreement, and the decision (Keep A, Keep B, Keep both,
// Reject both), kept with keep_annotation as an unsaved edit that Save writes. A light correction of the kept value
// (a polygon's vertices moved or deleted, points removed from a point object) is kept with set_annotation.
//
// Updating in place (spec-w4): the three parts are each built off the page and put in place only when what they show
// differs; the selection is set in place; the frame slider repaints the canvases without drawing anything again.
// The choices (sets, mode, filter, record, frame, a correction under way) are the page's and survive readings.
window.LabReview = (() => {
  const P = window.TuldokProject, S = window.LabScreens, A = window.LabActions, C = window.LabCharts, h = C.h, V = window.LabInside.viewers, D = window.LabInside.drawing;
  const { sect, putInPlace } = S.parts;
  const NEW = ['polygons', 'mask', 'depth', 'keypoints', 'ranking', 'timeseries', 'track', 'points', 'box3d'];
  const LISTS = ['boxes', 'spans', 'segments', 'polygons', 'keypoints', 'timeseries', 'track', 'box3d'];
  const KEPT = 'kept';
  const count = (n, one, many) => n.toLocaleString('en-GB') + ' ' + (n === 1 ? one : many || one + 's');
  const button = (cls, text, key, onClick) => { const b = h('button', cls, text); b.type = 'button'; if (key) b.dataset.key = key; if (onClick) b.addEventListener('click', onClick); return b; };
  const rgb = (c, a) => a == null ? 'rgb(' + c.join(',') + ')' : 'rgba(' + c.join(',') + ',' + a + ')';
  const fixed = (v, n = 2) => v == null || !Number.isFinite(v) ? '—' : v.toFixed(n);
  const shortSet = name => name === KEPT ? 'kept' : name.slice(name.indexOf('/') + 1);
  const copy = v => v == null ? v : JSON.parse(JSON.stringify(v));

  // ---- What is kept in this page -------------------------------------------------------------------------------
  const ui = { pick: new Map(), mode: 'side', min: new Map(), sel: new Map(), frame: 0, editing: null, removing: false, notes: new Map() };
  const store = new Map();    // the 3-D views' settings, per record and panel
  let here = null;            // { box, t, keys, parts, repaint: [] }

  const keepPaint = paint => { if (here && here.repaint) here.repaint.push(paint); };
  /** Is list value: the types whose value may be two sets' together. */
  const isList = (t, v) => Array.isArray(v) && (LISTS.includes(t.type) || t.type === 'points');
  function choose(t, sets) {
    const usable = sets.filter(s => !s.problem && (s.annotated || s.set === KEPT)).map(s => s.set);
    let [a, b] = ui.pick.get(t.task) || [];
    const made = usable.filter(n => n !== KEPT);
    if (!usable.includes(a)) a = made[0] || usable[0];
    if (!usable.includes(b) || b === a) b = made.find(n => n !== a) || usable.find(n => n !== a);
    ui.pick.set(t.task, [a, b]);
    return { a, b, usable };
  }

  async function load(t, sets) {
    const { a, b, usable } = choose(t, sets), min = ui.min.get(t.task);
    if (!a || !b) return { a, b, usable, agreement: null };
    const args = { task: t.task, sets: [a, b], limit: 200 }; if (min != null) args.min_confidence = min;
    const agreement = await P.read('annotation_agreement', args);
    let fleiss = null;
    if (t.type === 'class' && usable.length >= 3) fleiss = await P.read('annotation_agreement', { task: t.task, sets: usable.slice(0, 8), limit: 1 }).then(r => r.fleiss, () => null);
    let id = ui.sel.get(t.task);
    if (!id || !agreement.disputed.some(r => r.record === id)) id = agreement.disputed.length ? agreement.disputed[0].record : null;
    if (id) ui.sel.set(t.task, id);
    let compare = null, record = null, kept = null;
    if (id) {
      const names = [a, b].concat(a !== KEPT && b !== KEPT ? [KEPT] : []), cargs = { task: t.task, record: id, sets: names }; if (min != null) cargs.min_confidence = min;
      [compare, kept] = await Promise.all([P.read('annotation_compare', cargs), P.annotations.one(t.task, id).catch(() => null)]);
      if (compare.in_product) record = await P.product.record(t.run, id).catch(error => ({ error }));
    }
    return { a, b, usable, agreement, fleiss, id, compare, record, kept };
  }

  /** Draws review mode into box: each part put in place only when its content differs. */
  async function draw(box, t, sets, act) {
    const mine = (box._review = (box._review || 0) + 1);
    if (!here || here.box !== box) here = { box, keys: {}, parts: null, repaint: [] };
    here.act = act; here.t = t;
    let got; try { got = await load(t, sets); } catch (error) { got = { error }; }
    if (box._review !== mine) return;
    const may = A.may('edit');
    const keys = {
      left: JSON.stringify([t.task, got.error ? got.error.message : null, got.a, got.b, got.usable, ui.mode, ui.min.get(t.task), got.agreement, got.fleiss]),
      middle: JSON.stringify([t.task, got.id, got.compare, got.record && (got.record.error ? 'error' : got.record.record), ui.mode, ui.editing && [ui.editing.key, ui.editing.version], ui.removing]),
      right: JSON.stringify([t.task, got.id, got.compare && got.compare.sets.map(s => [s.set, s.value, s.confidence]), got.compare && got.compare.pairs, got.kept && [got.kept.annotation, got.kept.unsaved], may, ui.editing && [ui.editing.key, ui.editing.dirty, ui.editing.removed], ui.removing, got.a, got.b])
    };
    if (!here.parts) {
      const body = h('div', 'ann-body rv-body');
      here.parts = { left: h('div', 'ann-list rv-left'), middle: h('div', 'ann-view viewer rv-middle'), right: h('div', 'ann-form rv-right') };
      here.parts.middle.setAttribute('aria-label', 'The record and its annotations');
      for (const p of ['left', 'middle', 'right']) body.appendChild(here.parts[p]);
      box.replaceChildren(body);
    }
    here.got = got;
    const put = (name, make) => { if (here.keys[name] === keys[name]) return; here.keys[name] = keys[name]; putInPlace(here.parts[name], make(), box.closest('main') || box); };
    put('left', () => buildLeft(t, sets, got));
    put('middle', () => { here.repaint = []; return buildMiddle(t, got); });
    put('right', () => buildRight(t, got, may));
    for (const b of here.parts.left.querySelectorAll('.rv-rec')) { const on = String(b.dataset.id === got.id); if (b.getAttribute('aria-pressed') !== on) b.setAttribute('aria-pressed', on); }
  }
  const again = () => { if (here && here.box && here.box.isConnected) window.LabAnnotate.redraw(); };

  // ---- Left: choosers, agreement, the disputed list -------------------------------------------------------------
  function buildLeft(t, sets, got) {
    const box = h('div', 'rv-leftbox');
    if (got.error) { box.appendChild(A.refusal(got.error)); return box; }
    const pick = (label, which, value) => {
      const l = h('label', 'rv-pick'); l.appendChild(document.createTextNode(label));
      const s = h('select'); s.dataset.key = 'rv:set-' + which;
      for (const name of got.usable) { const found = sets.find(x => x.set === name) || {}; const o = h('option', null, shortSet(name) + (found.by && found.by.name ? ' · ' + found.by.name : '') + ' (' + count(found.annotated || 0, 'record') + ')'); o.value = name; o.selected = name === value; s.appendChild(o); }
      s.addEventListener('change', () => { const pair = ui.pick.get(t.task).slice(); pair[which === 'a' ? 0 : 1] = s.value; if (pair[0] === pair[1]) pair[which === 'a' ? 1 : 0] = got.usable.find(n => n !== s.value); ui.pick.set(t.task, pair); ui.editing = null; again(); });
      l.appendChild(s); return l;
    };
    box.appendChild(sect('Compare', count(got.usable.length, 'set')));
    const picks = h('div', 'rv-picks'); picks.appendChild(pick('A', 'a', got.a)); picks.appendChild(pick('B', 'b', got.b)); box.appendChild(picks);
    const seg = h('div', 'seg rv-mode'); seg.setAttribute('role', 'group'); seg.setAttribute('aria-label', 'How the two sets are drawn');
    for (const [id, label] of [['side', 'Side by side'], ['over', 'Overlaid']]) { const b = button(null, label, 'rv:mode-' + id, () => { if (ui.mode !== id) { ui.mode = id; again(); } }); b.setAttribute('aria-pressed', String(ui.mode === id)); seg.appendChild(b); }
    box.appendChild(seg);
    const fl = h('label', 'rv-min'); fl.appendChild(document.createTextNode('Confidence at least'));
    const fi = h('input'); fi.type = 'number'; fi.min = '0'; fi.max = '1'; fi.step = '0.05'; fi.placeholder = 'any'; fi.dataset.key = 'rv:min'; fi.className = 'ann-num';
    const min = ui.min.get(t.task); fi.value = min == null ? '' : String(min);
    fi.addEventListener('change', () => { const v = fi.value === '' ? null : Number(fi.value); if (v != null && !(v >= 0 && v <= 1)) { fi.value = min == null ? '' : String(min); return; } ui.min.set(t.task, v); again(); });
    fl.appendChild(fi); box.appendChild(fl);
    if (!got.agreement) { box.appendChild(h('p', 'empty', 'Two sets are needed to compare; build an annotator of this task.')); return box; }
    const ag = got.agreement, pair = ag.pairs[0] || {};
    const card = h('div', 'rv-agree'); card.setAttribute('data-key', 'rv:agreement');
    card.appendChild(h('span', 'kicker', 'Agreement of A and B'));
    card.appendChild(h('b', 'rv-score mono', fixed(pair.agreement)));
    card.appendChild(h('p', 'small muted', 'over ' + count(pair.records || 0, 'record') + '. ' + ag.measure));
    const figures = [];
    if (pair.kappa !== undefined) figures.push(['Cohen\'s κ', fixed(pair.kappa)]);
    if (got.fleiss != null) figures.push(['Fleiss\' κ, all sets', fixed(got.fleiss)]);
    if (pair.mean_iou !== undefined) figures.push(['Mean IoU of matches', fixed(pair.mean_iou)]);
    if (pair.mean_oks !== undefined) figures.push(['Mean OKS of matches', fixed(pair.mean_oks)]);
    if (pair.f1 !== undefined) figures.push([pair.mean_oks !== undefined ? 'F1 at OKS 0.5' : 'F1 at IoU 0.5', fixed(pair.f1)]);
    if (pair.matches !== undefined) figures.push(['Matches', String(pair.matches)]);
    if (pair.tau !== undefined) figures.push(['Mean Kendall τ', fixed(pair.tau)]);
    if (pair.exact !== undefined) figures.push(['Exactly equal', String(pair.exact)]);
    if (pair.mean_abs !== undefined) figures.push(['Mean |A − B|' + (t.units ? ' (' + t.units + ')' : ''), fixed(pair.mean_abs, 3)]);
    if (pair.delta !== undefined) figures.push(['Within δ 1.25', fixed(pair.delta)]);
    if (pair.switches !== undefined) figures.push(['Identity switches', String(pair.switches)], ['Fragments A · B', pair.fragments.join(' · ')]);
    if (figures.length) { const dl = h('dl', 'setup rv-figures'); for (const [k, v] of figures) { dl.appendChild(h('dt', null, k)); dl.appendChild(h('dd', 'mono', v)); } card.appendChild(dl); }
    if (ag.truncated) card.appendChild(h('p', 'small warn', 'A set holds more records than are compared here; the first 20,000 of each are.'));
    box.appendChild(card);
    box.appendChild(sect('Most disputed', ag.total ? count(ag.total, 'record') : '0'));
    if (!ag.disputed.length) { box.appendChild(h('p', 'empty', 'Neither set annotates a record.')); return box; }
    const ol = h('ol', 'rv-disputed'); ol.setAttribute('aria-label', 'The records A and B disagree on most, most first');
    for (const row of ag.disputed) {
      const li = h('li'), b = button('rv-rec', null, 'rv-rec-' + row.record, () => { if (ui.sel.get(t.task) !== row.record) { ui.sel.set(t.task, row.record); ui.editing = null; ui.removing = false; again(); } });
      b.dataset.id = row.record; b.setAttribute('aria-pressed', 'false');
      b.appendChild(h('bdi', 'mono rv-id', row.record));
      const bar = h('i', 'rv-bar'), fill = h('b'); fill.style.width = Math.round(100 * row.disagreement) + '%'; bar.appendChild(fill); b.appendChild(bar);
      b.appendChild(h('span', 'mono small rv-dis', fixed(row.disagreement)));
      if (row.missing.length) b.appendChild(h('span', 'small faint', 'only in ' + ['A', 'B'].filter((x, i) => !row.missing.includes([got.a, got.b][i])).join(' ')));
      b.setAttribute('aria-label', row.record + ', disagreement ' + fixed(row.disagreement) + (row.missing.length ? ', missing in ' + row.missing.map(shortSet).join(' and ') : ''));
      li.appendChild(b); ol.appendChild(li);
    }
    box.appendChild(ol);
    if (ag.total > ag.disputed.length) box.appendChild(h('p', 'small faint', 'The ' + ag.disputed.length + ' most disputed of ' + ag.total.toLocaleString('en-GB') + ' are listed.'));
    return box;
  }

  // ---- Colours ------------------------------------------------------------------------------------------------------
  const colourOf = which => V.token(which === 'a' ? '--ramp-neg' : which === 'b' ? '--ramp-pos' : '--good');
  const PALETTE = ['--ramp-neg', '--ramp-pos', '--good', '--warn', '--serious', '--accent'];
  const termColour = (t, term) => { const i = Math.max(0, (t.vocabulary || []).indexOf(term)); return V.token(PALETTE[i % PALETTE.length]); };

  // ---- Middle: the record with the sets drawn over it -----------------------------------------------------------
  function buildMiddle(t, got) {
    const el = h('div', 'iv rv-iv');
    if (!got.id) { el.appendChild(h('p', 'empty', 'Choose a record.')); return el; }
    const cmp = got.compare, byName = Object.fromEntries(cmp.sets.map(s => [s.set, s]));
    el.appendChild(h('header', 'iv-head')).appendChild(h('h3', 'mono', got.id));
    if (!cmp.in_product) { el.appendChild(h('p', 'empty', 'This record is not in the current product of ' + t.dataset + '.')); return el; }
    if (got.record && got.record.error) { el.appendChild(A.refusal(got.record.error)); return el; }
    const legend = h('p', 'small rv-legend');
    const swatch = (which, text) => { const s = h('span', 'rv-sw'); s.style.background = rgb(colourOf(which)); legend.appendChild(s); legend.appendChild(document.createTextNode(text + '  ')); };
    if (ui.mode === 'over' && !ui.editing) { swatch('a', 'A ' + shortSet(got.a)); swatch('b', 'B ' + shortSet(got.b)); swatch('both', 'both'); legend.appendChild(h('span', 'faint', ' · dashed: only in one')); el.appendChild(legend); }
    for (const s of cmp.sets) if (s.problem) el.appendChild(h('p', 'small warn', shortSet(s.set) + ': ' + s.problem));
    if (cmp.problem) el.appendChild(h('p', 'small warn', cmp.problem));
    const panels = ui.editing ? [['kept', [ui.editing.set]]] : ui.mode === 'over' ? [['over', [got.a, got.b]]] : [['a', [got.a]], ['b', [got.b]]];
    const grid = h('div', 'rv-panels' + (panels.length > 1 ? ' two' : '')); el.appendChild(grid);
    const r = got.record ? got.record.record : null, k = got.record ? got.record.content || {} : {};
    for (const [which, names] of panels) {
      const panel = h('figure', 'rv-panel'); grid.appendChild(panel);
      const values = ui.editing ? [{ set: KEPT, value: ui.editing.value, drawn: null }] : names.map(n => byName[n]);
      const cap = h('figcaption', 'small'); cap.textContent = ui.editing ? 'Correcting the kept annotation' : which === 'over' ? 'A and B' : which.toUpperCase() + ' · ' + shortSet(names[0]); panel.appendChild(cap);
      const roles = ui.editing ? ['kept'] : which === 'over' ? ['a', 'b'] : [which];
      if (r && r.kind === 'image') imagePanel(panel, t, r, k, values, roles, cmp);
      else if (r && r.kind === 'pointcloud') cloudPanel(panel, t, got.id, k, values, roles, which);
      else if (cmp.frames) framesPanel(panel, t, cmp.frames, values, roles);
      else if (cmp.series || (r && r.kind === 'audio')) bandsPanel(panel, t, cmp.series, k, values, roles);
      else textPanel(panel, t, values, roles, r, k);
    }
    if (cmp.frames) el.appendChild(frameSlider(cmp.frames));
    return el;
  }

  /** Matching for marking: an object of one side with no object of the same term at IoU 0.5 or more on the other. */
  function unmatched(objs, others) {
    const iou = (a, b) => { const ix = Math.max(0, Math.min(a[0] + a[2], b[0] + b[2]) - Math.max(a[0], b[0])), iy = Math.max(0, Math.min(a[1] + a[3], b[1] + b[3]) - Math.max(a[1], b[1])), i = ix * iy, u = a[2] * a[3] + b[2] * b[3] - i; return u > 0 ? i / u : 0; };
    return objs.map(o => !others.some(p => p.term === o.term && iou(o.box, p.box) >= 0.5));
  }
  const bboxOf = pts => { const xs = pts.filter(Boolean).map(p => p[0]), ys = pts.filter(Boolean).map(p => p[1]); if (!xs.length) return [0, 0, 0, 0]; const x0 = Math.min(...xs), y0 = Math.min(...ys); return [x0, y0, Math.max(...xs) - x0 || 1, Math.max(...ys) - y0 || 1]; };
  function objectsOf(t, value) {
    if (!Array.isArray(value)) return [];
    if (t.type === 'boxes') return value.map(o => ({ term: o.term, box: [o.x, o.y, o.w, o.h], o }));
    if (t.type === 'polygons') return value.map(o => ({ term: o.term, box: bboxOf(o.points), o }));
    if (t.type === 'keypoints') return value.map(o => ({ term: o.term, box: bboxOf(o.points), o }));
    return [];
  }

  function imagePanel(panel, t, r, k, values, roles, cmp) {
    const cv = h('canvas', 'rv-canvas'); cv.tabIndex = 0; cv.dataset.key = 'rv:canvas-' + roles.join(''); cv.setAttribute('role', 'img');
    cv.setAttribute('aria-label', 'Image ' + r.id + ' with ' + roles.map(x => x === 'kept' ? 'the kept annotation' : 'set ' + x.toUpperCase()).join(' and ') + ' drawn over it');
    panel.appendChild(cv);
    const img = new Image(); img.src = r.url;
    const nw = k.width || (cmp.size || [])[0] || 1, nh = k.height || (cmp.size || [])[1] || 1;
    const layers = values.map((s, i) => ({ s, role: roles[i], mask: s && s.drawn && s.drawn.runs ? maskPixels(s.drawn) : null }));
    const objs = layers.map(l => objectsOf(t, l.s && l.s.value));
    const lone = layers.length === 2 ? [unmatched(objs[0], objs[1]), unmatched(objs[1], objs[0])] : [objs[0].map(() => false)];
    const edit = ui.editing && t.type === 'polygons' ? ui.editing : null;
    // What is drawn, per set, as data-drawn (objects, or pixels of a mask or a depth map): read by the browser check.
    cv.dataset.drawn = layers.map((l, i) => roles[i] + ':' + (l.mask ? l.mask.px.reduce((n, v) => n + (v ? 1 : 0), 0) : l.s && l.s.drawn && l.s.drawn.values_u8 ? atob(l.s.drawn.values_u8).split('').filter(c => c !== '\0').length : objs[i].length)).join(' ');
    const paint = () => {
      const size = V.fit(cv, Math.max(120, Math.round(cv.clientWidth * nh / nw))); if (!size) return;
      const [W, H] = size, ctx = cv.getContext('2d'), sx = W / nw, sy = H / nh;
      ctx.clearRect(0, 0, W, H); ctx.imageSmoothingEnabled = false;
      if (img.complete && img.naturalWidth) ctx.drawImage(img, 0, 0, W, H);
      if (t.type === 'mask') paintMasks(ctx, t, layers, W, H);
      if (t.type === 'depth') paintDepth(ctx, layers, W, H);
      const dpr = window.devicePixelRatio || 1;
      layers.forEach((l, li) => {
        if (!l.s || !Array.isArray(l.s.value)) return;
        const col = roles.length > 1 ? colourOf(l.role) : null;
        objs[li].forEach((ob, oi) => {
          const c = col || termColour(t, ob.term), dashed = lone[li][oi] && roles.length > 1;
          ctx.strokeStyle = rgb(c); ctx.fillStyle = rgb(c, 0.16); ctx.lineWidth = (dashed ? 2.5 : 1.6) * dpr; ctx.setLineDash(dashed ? [5 * dpr, 3 * dpr] : []);
          const o = ob.o;
          if (t.type === 'boxes') { ctx.strokeRect(o.x * sx, o.y * sy, o.w * sx, o.h * sy); }
          else if (t.type === 'polygons') { ctx.beginPath(); o.points.forEach((p, i) => i ? ctx.lineTo(p[0] * sx, p[1] * sy) : ctx.moveTo(p[0] * sx, p[1] * sy)); ctx.closePath(); ctx.fill(); ctx.stroke(); }
          else if (t.type === 'keypoints') {
            const names = t.keypoints || [], at = n => o.points[names.indexOf(n)];
            ctx.setLineDash([]); for (const [m, n] of t.skeleton || []) { const p = at(m), q = at(n); if (p && q) { ctx.beginPath(); ctx.moveTo(p[0] * sx, p[1] * sy); ctx.lineTo(q[0] * sx, q[1] * sy); ctx.stroke(); } }
            for (const p of o.points) if (p && (p.length < 3 || p[2] > 0)) { ctx.beginPath(); ctx.arc(p[0] * sx, p[1] * sy, 3 * dpr, 0, 7); ctx.fillStyle = rgb(c); ctx.fill(); }
          }
          ctx.setLineDash([]); ctx.fillStyle = rgb(c); ctx.font = (11 * dpr) + 'px ' + getComputedStyle(document.body).fontFamily;
          ctx.fillText(ob.term + (o.confidence != null ? ' ' + o.confidence.toFixed(2) : ''), ob.box[0] * sx + 2 * dpr, Math.max(11 * dpr, ob.box[1] * sy - 3 * dpr));
        });
      });
      if (edit) for (const [pi, p] of edit.value.entries()) p.points.forEach((q, qi) => { const on = edit.vertex && edit.vertex[0] === pi && edit.vertex[1] === qi; ctx.fillStyle = rgb(on ? V.token('--serious') : V.token('--accent')); ctx.fillRect(q[0] * sx - 4 * dpr, q[1] * sy - 4 * dpr, 8 * dpr, 8 * dpr); });
    };
    img.addEventListener('load', paint, { once: true });
    V.paints(cv, paint); keepPaint(paint);
    if (t.type === 'depth') { const d = values.map(s => s && s.drawn).filter(Boolean)[0]; if (d) panel.appendChild(h('p', 'small faint', roles.length > 1 ? 'Overlaid: the difference A − B, blue where A is nearer.' : 'Depth ' + fixed(d.low, 2) + ' to ' + fixed(d.high, 2) + (t.units ? ' ' + t.units : '') + ', light to dark.')); }
    if (edit) correctPolygons(cv, edit, nw, nh, paint);
  }

  /** A drawn mask's runs decoded to its pixel values. */
  function maskPixels(d) { const out = new Uint16Array(d.width * d.height); let at = 0; for (const [v, n] of d.runs) { out.fill(v, at, at + n); at += n; } return { d, px: out }; }
  function paintMasks(ctx, t, layers, W, H) {
    const ms = layers.map(l => l.mask); if (!ms.some(Boolean)) return;
    const d = ms.find(Boolean).d, off = document.createElement('canvas'); off.width = d.width; off.height = d.height;
    const o = off.getContext('2d'), img = o.createImageData(d.width, d.height), both = colourOf('both');
    const instance = t.mask === 'instance';
    for (let i = 0; i < d.width * d.height; i++) {
      let c = null;
      if (ms.length === 2) { const a = ms[0] ? ms[0].px[i] : 0, b = ms[1] ? ms[1].px[i] : 0; c = a && b ? both : a ? colourOf('a') : b ? colourOf('b') : null; }
      else if (ms[0] && ms[0].px[i]) { const v = ms[0].px[i]; c = instance ? V.token(PALETTE[v % PALETTE.length]) : termColour(t, (ms[0].d.classes || {})[String(v)]); }
      if (c) { img.data[i * 4] = c[0]; img.data[i * 4 + 1] = c[1]; img.data[i * 4 + 2] = c[2]; img.data[i * 4 + 3] = 170; }
    }
    o.putImageData(img, 0, 0); ctx.imageSmoothingEnabled = false; ctx.drawImage(off, 0, 0, W, H);
  }
  function paintDepth(ctx, layers, W, H) {
    const ds = layers.map(l => l.s && l.s.drawn).filter(Boolean); if (!ds.length) return;
    const raw = d => { const s = atob(d.values_u8), out = new Float32Array(s.length); for (let i = 0; i < s.length; i++) { const u = s.charCodeAt(i); out[i] = u ? d.low + (u - 1) / 254 * (d.high - d.low) : NaN; } return out; };
    let values = raw(ds[0]), colour = D.ramp(ds[0].low, ds[0].high);
    if (ds.length === 2 && ds[1].width === ds[0].width) { const b = raw(ds[1]); values = values.map((v, i) => v - b[i]); const m = Math.max(1e-9, ...Array.from(values).filter(Number.isFinite).map(Math.abs)); colour = D.ramp(-m, m); }
    ctx.globalAlpha = 0.85; D.heat(ctx, values, ds[0].height, ds[0].width, colour, 0, 0, W, H); ctx.globalAlpha = 1;
  }

  /** The light correction of polygons: a vertex dragged, or chosen and deleted (a polygon keeps three). */
  function correctPolygons(cv, edit, nw, nh, paint) {
    cv.setAttribute('aria-label', cv.getAttribute('aria-label') + '. Drag a vertex to move it; click one to choose it and Delete removes it.');
    const at = e => { const q = cv.getBoundingClientRect(); return [(e.clientX - q.left) / q.width * nw, (e.clientY - q.top) / q.height * nh]; };
    const near = p => { let best = null, dist = 8 * nw / cv.getBoundingClientRect().width; edit.value.forEach((poly, pi) => poly.points.forEach((q, qi) => { const d = Math.hypot(q[0] - p[0], q[1] - p[1]); if (d <= dist) { dist = d; best = [pi, qi]; } })); return best; };
    let dragging = null;
    cv.addEventListener('pointerdown', e => { const v = near(at(e)); edit.vertex = v; if (v) { dragging = e.pointerId; cv.setPointerCapture(e.pointerId); } paint(); });
    cv.addEventListener('pointermove', e => { if (dragging !== e.pointerId || !edit.vertex) return; const [x, y] = at(e), q = edit.value[edit.vertex[0]].points[edit.vertex[1]]; q[0] = Math.round(Math.min(nw, Math.max(0, x)) * 10) / 10; q[1] = Math.round(Math.min(nh, Math.max(0, y)) * 10) / 10; edit.dirty = true; paint(); });
    cv.addEventListener('pointerup', e => { if (dragging === e.pointerId) { dragging = null; again(); } });
    cv.addEventListener('keydown', e => {
      if ((e.key === 'Delete' || e.key === 'Backspace') && edit.vertex) { const poly = edit.value[edit.vertex[0]]; if (poly.points.length > 3) { poly.points.splice(edit.vertex[1], 1); edit.vertex = null; edit.dirty = true; paint(); again(); } e.preventDefault(); }
    });
  }

  function cloudPanel(panel, t, id, k, values, roles, which) {
    if (!k.points_f32) { panel.appendChild(h('p', 'note', 'The point cloud could not be read.')); return; }
    const pts = D.floats(k.points_f32), n = pts.length / 3, stride = k.stride || 1, colours = new Uint8Array(n * 3), base = V.token('--ink-2');
    for (let i = 0; i < n; i++) colours.set(base, i * 3);
    const objects = values.map(s => !s ? [] : s.drawn && s.drawn.points ? s.drawn.points : Array.isArray(s.value) && t.type === 'points' ? s.value : []);
    const member = objects.map(list => { const m = new Map(); list.forEach(o => { for (const idx of o.indices) if (idx % stride === 0) m.set(idx / stride, o.term); }); return m; });
    for (let i = 0; i < n; i++) {
      const inA = member[0] && member[0].has(i), inB = member[1] && member[1].has(i);
      if (roles.length === 2) { if (inA || inB) colours.set(inA && inB ? colourOf('both') : inA ? colourOf('a') : colourOf('b'), i * 3); }
      else if (inA) colours.set(termColour(t, member[0].get(i)), i * 3);
    }
    const lines = [];
    values.forEach((s, li) => {
      if (!s || t.type !== 'box3d' || !Array.isArray(s.value)) return;
      const col = roles.length > 1 ? colourOf(roles[li]) : null;
      for (const b of s.value) {
        const [cx, cy, cz] = b.center, [l, w, hh] = b.size, c = Math.cos(b.yaw), sn = Math.sin(b.yaw);
        const corner = (dx, dy, dz) => [cx + c * dx - sn * dy, cy + sn * dx + c * dy, cz + dz];
        const pts8 = []; for (const dz of [-hh / 2, hh / 2]) for (const [dx, dy] of [[l / 2, w / 2], [-l / 2, w / 2], [-l / 2, -w / 2], [l / 2, -w / 2]]) pts8.push(corner(dx, dy, dz));
        const edges = [[0, 1], [1, 2], [2, 3], [3, 0], [4, 5], [5, 6], [6, 7], [7, 4], [0, 4], [1, 5], [2, 6], [3, 7]];
        for (const [p, q] of edges) lines.push(pts8[p].concat(pts8[q], [col || termColour(t, b.term)]));
      }
    });
    const st = store.get(id + '\n' + which) || V.turned(); store.set(id + '\n' + which, st);
    panel.dataset.drawn = roles.map((role, i) => role + ':' + member[i].size + '/' + values.filter((s, j) => j === i && s && Array.isArray(s.value) && t.type === 'box3d').reduce((n, s) => n + s.value.length, 0)).join(' ');
    const editing = ui.editing && t.type === 'points' ? ui.editing : null;
    st.selecting = !!(editing && ui.removing);
    const m = { points: pts, colours, bounds: k.bounds, lines };
    if (editing) m.select = shown => { const gone = new Set(shown.map(i => i * stride)); let removed = 0; for (const o of editing.value) { const before = o.indices.length; o.indices = o.indices.filter(x => !gone.has(x)); removed += before - o.indices.length; } editing.value = editing.value.filter(o => o.indices.length); if (removed) { editing.dirty = true; editing.version = (editing.version || 0) + 1; editing.removed = (editing.removed || 0) + removed; again(); } };
    V.space(panel, m, st, 'Point cloud ' + id + ' with ' + roles.map(x => x === 'kept' ? 'the kept point objects' : 'set ' + x.toUpperCase()).join(' and ') + (st.selecting ? '. Drag a rectangle to remove the points in it from the kept objects.' : ''));
    const said = t.type === 'box3d' ? values.map((s, i) => (roles[i] === 'kept' ? 'Kept' : roles[i].toUpperCase()) + ': ' + count(Array.isArray(s && s.value) ? s.value.length : 0, 'box', 'boxes')).join(' · ')
      : objects.map((list, i) => (roles[i] === 'kept' ? 'Kept' : roles[i].toUpperCase()) + ': ' + (list.length ? list.map(o => o.term + ' ' + count(o.indices.length, 'point')).join(', ') : 'no object')).join(' · ');
    panel.appendChild(h('p', 'small faint', said));
  }

  function framesPanel(panel, t, frames, values, roles) {
    const cv = h('canvas', 'rv-canvas'); cv.tabIndex = 0; cv.dataset.key = 'rv:frames-' + roles.join(''); cv.setAttribute('role', 'img');
    cv.setAttribute('aria-label', 'Frames of the array with the tracks of ' + roles.map(x => 'set ' + x.toUpperCase()).join(' and ') + '; the left and right arrows change the frame');
    panel.appendChild(cv);
    const paint = () => {
      const f = frames.frames[Math.min(ui.frame, frames.frames.length - 1)]; if (!f) return;
      const size = V.fit(cv, Math.max(120, Math.round(cv.clientWidth * frames.height / frames.width))); if (!size) return;
      const [W, H] = size, ctx = cv.getContext('2d'), raw = atob(f.u8), off = document.createElement('canvas'); off.width = frames.width; off.height = frames.height;
      const o = off.getContext('2d'), img = o.createImageData(frames.width, frames.height);
      for (let i = 0; i < raw.length; i++) { const v = raw.charCodeAt(i); img.data[i * 4] = img.data[i * 4 + 1] = img.data[i * 4 + 2] = v; img.data[i * 4 + 3] = 255; }
      o.putImageData(img, 0, 0); ctx.imageSmoothingEnabled = false; ctx.drawImage(off, 0, 0, W, H);
      const sx = W / (frames.width * frames.scale), sy = H / (frames.height * frames.scale), dpr = window.devicePixelRatio || 1;
      const drawn = values.map(() => 0);
      values.forEach((s, li) => {
        if (!s || !Array.isArray(s.value)) return;
        for (const tr of s.value) { const b = tr.frames.find(x => x.frame === f.frame); if (!b) continue; drawn[li]++; const c = roles.length > 1 ? colourOf(roles[li]) : termColour(t, tr.term); ctx.strokeStyle = rgb(c); ctx.lineWidth = 1.8 * dpr; ctx.strokeRect(b.x * sx, b.y * sy, b.w * sx, b.h * sy); ctx.fillStyle = rgb(c); ctx.font = (11 * dpr) + 'px ' + getComputedStyle(document.body).fontFamily; ctx.fillText(tr.track, b.x * sx + 2 * dpr, Math.max(11 * dpr, b.y * sy - 3 * dpr)); }
      });
      const said = 'frame ' + f.frame + ' ' + roles.map((role, i) => role + ':' + drawn[i] + (values[i] && Array.isArray(values[i].value) ? '=' + values[i].value.filter(tr => tr.frames.some(x => x.frame === f.frame)).map(tr => tr.track).join(',') : '')).join(' ');
      if (cv.dataset.drawn !== said) cv.dataset.drawn = said;
    };
    cv.addEventListener('keydown', e => { if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); setFrame(ui.frame + (e.key === 'ArrowRight' ? 1 : -1), frames); } });
    V.paints(cv, paint); keepPaint(paint);
  }
  function frameSlider(frames) {
    const box = h('label', 'rv-frame'); const n = frames.frames.length;
    ui.frame = Math.min(ui.frame, n - 1);
    const out = h('span', 'mono small'), say = () => { out.textContent = 'frame ' + frames.frames[ui.frame].frame + ' of ' + frames.count; };
    const r = h('input'); r.type = 'range'; r.min = '0'; r.max = String(n - 1); r.value = String(ui.frame); r.dataset.key = 'rv:frame'; r.setAttribute('aria-label', 'Frame');
    r.addEventListener('input', () => setFrame(Number(r.value), frames));
    box.appendChild(document.createTextNode('Frame')); box.appendChild(r); box.appendChild(out); say(); box._say = say;
    return box;
  }
  /** A new frame: the canvases repainted and the slider set, in place. */
  function setFrame(i, frames) {
    ui.frame = Math.max(0, Math.min(frames.frames.length - 1, i));
    const slider = here.parts.middle.querySelector('.rv-frame'); if (slider) { slider.querySelector('input').value = String(ui.frame); slider._say(); }
    for (const p of here.repaint) p();
  }

  /** Timeseries or segments: bands of each set under a series (an array) or a waveform (a sound). */
  function bandsPanel(panel, t, series, k, values, roles) {
    const cv = h('canvas', 'rv-canvas rv-bands'); cv.setAttribute('role', 'img'); cv.dataset.key = 'rv:bands-' + roles.join('');
    const length = series ? series.positions : k.seconds || 1;
    cv.setAttribute('aria-label', (series ? 'The series' : 'The waveform') + ' with the stretches of ' + roles.map(x => 'set ' + x.toUpperCase()).join(' and '));
    panel.appendChild(cv);
    const rows = values.length, terms = t.vocabulary || [];
    cv.dataset.drawn = roles.map((role, i) => role + ':' + (values[i] && Array.isArray(values[i].value) ? values[i].value.length : 0)).join(' ');
    const paint = () => {
      const size = V.fit(cv, 96 + rows * 22); if (!size) return;
      const [W, H] = size, ctx = cv.getContext('2d'), dpr = window.devicePixelRatio || 1, top = 96 * dpr;
      ctx.clearRect(0, 0, W, H);
      if (series) {
        const all = series.channels.flat().filter(Number.isFinite), lo = Math.min(...all), hi = Math.max(...all), span = hi - lo || 1;
        series.channels.forEach((line, ci) => { ctx.strokeStyle = rgb(V.token(PALETTE[(ci + 2) % PALETTE.length])); ctx.lineWidth = dpr; ctx.beginPath(); line.forEach((v, i) => { const x = i / Math.max(1, line.length - 1) * W, y = top - 4 * dpr - (v - lo) / span * (top - 8 * dpr); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }); ctx.stroke(); });
      } else if (k.peaks) V.wave(ctx, W, top, k.peaks);
      values.forEach((s, li) => {
        const y = top + li * 22 * dpr + 3 * dpr, c0 = roles.length > 1 ? colourOf(roles[li]) : null;
        ctx.fillStyle = rgb(V.token('--line-strong'), 0.25); ctx.fillRect(0, y, W, 16 * dpr);
        for (const it of (s && Array.isArray(s.value) ? s.value : [])) { const c = c0 || termColour(t, it.term); ctx.fillStyle = rgb(c, 0.75); const x0 = it.start / length * W, x1 = it.end / length * W; ctx.fillRect(x0, y, Math.max(1, x1 - x0), 16 * dpr); ctx.fillStyle = rgb(V.token('--ink') || c); ctx.font = (10 * dpr) + 'px ' + getComputedStyle(document.body).fontFamily; ctx.fillText(it.term, x0 + 2 * dpr, y + 12 * dpr); }
        ctx.fillStyle = rgb(c0 || V.token('--line-strong')); ctx.fillText(roles[li].toUpperCase(), W - 14 * dpr, y + 12 * dpr);
      });
      void terms;
    };
    V.paints(cv, paint); keepPaint(paint);
    panel.appendChild(h('p', 'small faint', series ? count(series.positions, 'position') + (series.step > 1 ? ', every ' + series.step + 'th drawn' : '') : (k.seconds ? k.seconds.toFixed(2) + ' s' : 'The sound\'s length is read from WAV only.')));
  }

  /** What has no drawing surface here: each set's value in words (ranking, class, tags, text, spans). */
  function textPanel(panel, t, values, roles) {
    const dl = h('dl', 'setup rv-values');
    values.forEach((s, i) => { dl.appendChild(h('dt', null, roles[i].toUpperCase())); dl.appendChild(h('dd', 'mono pre', s && s.value != null ? (Array.isArray(s.value) && t.type === 'ranking' ? s.value.map((x, j) => (j + 1) + '. ' + x).join('\n') : JSON.stringify(s.value, null, 1)) : 'not annotated')); });
    panel.appendChild(dl);
  }

  // ---- Right: the values in words, this record's agreement, the decision -------------------------------------
  function summary(t, value) {
    if (value == null) return 'not annotated';
    if (t.type === 'mask') return 'a mask of ' + count(Object.keys(value.classes || {}).length, 'class', 'classes') + (value.file ? ' (PNG)' : ' (runs)');
    if (t.type === 'depth') return 'a depth map';
    if (t.type === 'ranking') return value.join(' › ');
    if (typeof value === 'string') return value.length > 80 ? value.slice(0, 80) + '…' : value;
    if (!Array.isArray(value)) return value.file ? 'point ids in a file' : JSON.stringify(value).slice(0, 80);
    if (t.type === 'tags') return value.join(', ') || 'no tag';
    if (t.type === 'points') return value.map(o => o.term + ' (' + count(o.indices.length, 'point') + ')').join(', ') || 'no object';
    const terms = {}; for (const o of value) terms[o.term] = (terms[o.term] || 0) + 1;
    const conf = value.map(o => o.confidence).filter(x => x != null);
    return (count(value.length, t.type === 'track' ? 'track' : 'object') + (value.length ? ': ' + Object.entries(terms).map(([k, n]) => n + ' ' + k).join(', ') : '')) + (conf.length ? ' · confidence ' + Math.min(...conf).toFixed(2) + '–' + Math.max(...conf).toFixed(2) : '');
  }
  function buildRight(t, got, may) {
    const box = h('div', 'inspector rv-decide');
    if (!got.id || !got.compare) { box.appendChild(h('p', 'empty', 'Choose a record from the list.')); return box; }
    const cmp = got.compare, byName = Object.fromEntries(cmp.sets.map(s => [s.set, s])), line = got.kept ? got.kept.annotation : null;
    const hd = h('header'); hd.appendChild(h('span', 'kicker', t.title + ' · ' + t.type)); const t2 = h('h2', 'mono', got.id); t2.tabIndex = -1; hd.appendChild(t2); box.appendChild(hd);
    const dl = h('dl', 'setup');
    for (const [label, name] of [['A', got.a], ['B', got.b]]) { const s = byName[name]; dl.appendChild(h('dt', null, label + ' · ' + shortSet(name))); dl.appendChild(h('dd', null, summary(t, s && s.value) + (s && s.confidence != null ? ' · line confidence ' + s.confidence.toFixed(2) : ''))); }
    const ab = cmp.pairs.find(p => (p.a === got.a && p.b === got.b) || (p.a === got.b && p.b === got.a));
    dl.appendChild(h('dt', null, 'Agreement here')); dl.appendChild(h('dd', 'mono', ab ? (ab.problem || fixed(ab.agreement)) : '—'));
    box.appendChild(dl);
    // What is kept now.
    const kept = h('p', 'small rv-kept');
    if (line) kept.textContent = 'Kept: ' + line.state + (line.from && line.from.set ? ' · from ' + shortSet(line.from.set) : line.from && line.from.both ? ' · from both' : line.from && line.from.rejected ? ' · both rejected' : '') + (got.kept.unsaved ? ' · unsaved' : '') + ' · ' + summary(t, line.value);
    else kept.textContent = 'Nothing is kept for this record yet.';
    box.appendChild(kept);
    if (ui.editing) { box.appendChild(correctionBox(t, got)); return box; }
    // The decision.
    const note = h('textarea'); note.rows = 2; note.maxLength = 4000; note.placeholder = 'a note (optional)'; note.dataset.key = 'rv:note'; note.disabled = !may;
    const nk = t.task + '\n' + got.id; note.value = ui.notes.get(nk) || ''; note.addEventListener('input', () => ui.notes.set(nk, note.value));
    const nl = h('div', 'form rv-note'), lab = h('label'); lab.appendChild(document.createTextNode('Note')); lab.appendChild(note); nl.appendChild(lab);
    const va = byName[got.a] && byName[got.a].value, vb = byName[got.b] && byName[got.b].value;
    const args = (keep, sets) => () => { const a = { task: t.task, record: got.id, keep, sets }; const n = (ui.notes.get(nk) || '').trim(); if (n) a.note = n; return a; };
    const done = () => { ui.notes.delete(nk); };
    box.appendChild(A.group('review:decide', [
      { id: 'keep-a', label: 'Keep A', cls: 'btn primary', who: 'edit', op: 'keep_annotation', busy: 'Keeping…', hidden: got.a === KEPT || va == null, args: args('one', [got.a]), done },
      { id: 'keep-b', label: 'Keep B', cls: 'btn primary', who: 'edit', op: 'keep_annotation', busy: 'Keeping…', hidden: got.b === KEPT || vb == null, args: args('one', [got.b]), done },
      { id: 'keep-both', label: 'Keep both', cls: 'btn', who: 'edit', op: 'keep_annotation', busy: 'Keeping…', hidden: got.a === KEPT || got.b === KEPT || !isList(t, va) || !isList(t, vb), args: args('both', [got.a, got.b]), done },
      { id: 'reject', label: 'Reject both', cls: 'btn', who: 'edit', op: 'keep_annotation', busy: 'Rejecting…', args: args('none', [got.a, got.b]), done }
    ]));
    box.appendChild(nl);
    const correctable = line && line.state !== 'rejected' && Array.isArray(line.value) && ((t.type === 'polygons' && line.value.length) || (t.type === 'points' && line.value.length));
    if (may && correctable) box.appendChild(A.group('review:correct', [{ id: 'correct', label: t.type === 'polygons' ? 'Correct the kept polygons' : 'Correct the kept point objects', cls: 'btn ghost', onClick: () => { ui.editing = { key: nk, set: KEPT, value: copy(line.value), from: line.from || null, state: line.state, note: line.note || null, dirty: false }; ui.removing = t.type === 'points'; again(); } }]));
    box.appendChild(h('p', 'note', may ? 'A decision is kept in Tuldok as an unsaved edit of ' + t.task + '.jsonl, naming the set it came from; Save writes it.' : 'This session may look but not decide: that needs the right to edit.'));
    return box;
  }
  function correctionBox(t, got) {
    const e = ui.editing, box = h('div', 'rv-correct');
    box.appendChild(h('p', 'small', t.type === 'polygons' ? 'Drag a vertex to move it. Click a vertex to choose it, then Delete removes it (a polygon keeps three).' : 'Drag a rectangle on the cloud to remove the points in it from the kept objects.' + (e.removed ? ' ' + count(e.removed, 'point') + ' removed so far.' : '')));
    const item = () => { const it = { record: got.id, state: 'accepted', value: e.value }; if (e.note) it.note = e.note; return it; };
    box.appendChild(A.group('review:correction', [
      { id: 'keep-correction', label: 'Keep the correction', cls: 'btn primary', who: 'edit', op: 'set_annotation', busy: 'Keeping…', hidden: !e.dirty,
        args: () => Object.assign({ task: t.task, items: [item()] }, e.from ? { from: e.from } : {}), done: () => { ui.editing = null; ui.removing = false; } },
      { id: 'drop-correction', label: 'Drop the correction', cls: 'btn ghost', onClick: () => { ui.editing = null; ui.removing = false; again(); } }
    ]));
    return box;
  }

  /** For annotate mode: a kept value of a new type drawn read-only over its record (no drawing tools). */
  function overlay(el, got, t, value) {
    const panel = h('figure', 'rv-panel'), r = got.record, k = got.content || {}, s = { set: KEPT, value, drawn: null };
    const cmp = { size: k.width ? [k.width, k.height] : null };
    if (r.kind === 'image' && !['mask', 'depth'].includes(t.type)) imagePanel(panel, t, r, k, [s], ['kept'], cmp);
    else if (r.kind === 'pointcloud' && ['points', 'box3d'].includes(t.type) && Array.isArray(value)) cloudPanel(panel, t, r.id, k, [s], ['kept'], 'annotate');
    else return false;
    el.appendChild(panel); return true;
  }

  return { draw, NEW, summary, overlay };
})();
