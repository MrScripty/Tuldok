'use strict';
// Curation by embeddings on the page (docs/plans/training-and-curation/spec-t5.md section 6): the Map mode of a dataset
// opened on the Data tab (inside.js draws the mode switch and the viewer; this module draws the map and its lists), and
// the Data tab's Embed form, which keeps a new dataset whose run is the step embed as an unsaved edit, as Generate does.
//
// The map is a canvas of the set's records in two dimensions (embedding_map), coloured by a choice, with the thin cells
// shaded; the wheel zooms about the pointer, Move drags the view, Box and Lasso choose points. Hovering a point shows its
// id; resting on it shows the record in inside.js's viewer; a click opens it and asks for its neighbours. The chosen
// points become a new dataset (a select definition, kept with set_definition) or fill the Freeze form (annotate.js).
// Beside the map: More like this, Duplicates, Outliers, Leakage and Thin regions, each asked for when first shown.
//
// Updating in place (spec-w4): the answers are not watched; a reading that changed something makes inside.js draw the
// opened view again, and this module draws the map again from its kept state (the set, the colour, the view, the tool,
// what is chosen and opened, each list's controls). A person's own changes redraw only the part they change.
window.LabCuration = (() => {
  const P = window.TuldokProject, S = window.LabScreens, A = window.LabActions, h = window.LabCharts.h;
  const { putInPlace } = S.parts;
  const FORMAT = 'tuldok_definition_v1';
  const SELECT_LIMIT = 20000;            // records one select names (check.py)
  const CATEGORIES = 8;                  // categorical colours: --cat-1 to --cat-8; the rest, and "other", are --ink-3
  const NO_CODE = 65535;
  const REST_MS = 300;                   // resting on a point this long shows its record in the viewer
  const button = (cls, text, key, onClick) => { const b = h('button', cls, text); b.type = 'button'; if (key) b.dataset.key = key; if (onClick) b.addEventListener('click', onClick); return b; };
  const count = (n, one, many) => n.toLocaleString('en-GB') + ' ' + (n === 1 ? one : many || one + 's');
  const pct = x => (x * 100).toFixed(x < 0.1 ? 1 : 0) + ' %';
  const cos = x => x.toFixed(4);
  const D = () => window.LabInside.drawing;
  const raw = b64 => { const s = atob(b64 || ''), u = new Uint8Array(s.length); for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i); return u; };
  const u16 = b64 => { const u = raw(b64), d = new DataView(u.buffer), out = new Uint16Array(u.length >> 1); for (let i = 0; i < out.length; i++) out[i] = d.getUint16(i * 2, true); return out; };

  // ---- What is kept per dataset across drawings -----------------------------------------------------------------
  const states = new Map();
  const stateOf = ref => {
    if (!states.has(ref)) states.set(ref, { key: null, colour: undefined, view: { k: 1, cu: 0.5, cv: 0.5 }, tool: 'box', chosen: new Set(), opened: null,
      list: 'duplicates', dup: '0.98', leak: '0.95', train: 'train', k: '5', form: false, kept: null });
    return states.get(ref);
  };
  const usable = em => ((em && em.sets) || []).filter(s => !s.problem && s.records_run);
  const keyOf = s => s.run + '/' + s.name;
  /** The embeddings sets of a dataset (kept like any answer until a reading finds a change). */
  const sets = ref => P.read('embeddings', { dataset: ref }).catch(error => ({ error, sets: [] }));
  const base = s => ({ run: s.run, name: s.name, records_run: s.records_run });

  // ---- The Map mode -------------------------------------------------------------------------------------------------
  /**
   * The map and its lists for a dataset opened in inside.js: ctx is {ref, em (the embeddings answer), act,
   * show(id, run) (shows a record in the viewer), live() (whether the view is still on screen)}.
   */
  function panel(ctx) {
    const st = stateOf(ctx.ref), list = usable(ctx.em);
    const root = h('section', 'cur'); root.setAttribute('aria-label', 'The records on a map of their embeddings');
    const broken = ((ctx.em && ctx.em.sets) || []).filter(s => s.problem);
    if (!list.length) {
      root.appendChild(h('p', 'empty', 'No embeddings of this dataset can be read.'));
      for (const s of broken) root.appendChild(h('p', 'small warnline', s.holder + ' · ' + s.name + ': ' + s.problem));
      return root;
    }
    const set = list.find(s => keyOf(s) === st.key) || list[0]; st.key = keyOf(set);
    const c = { ctx, st, set, root, m: null, pts: null, hover: null, rest: 0 };
    const head = h('div', 'cur-head');
    if (list.length > 1) {
      const sel = h('select'); sel.setAttribute('aria-label', 'Embeddings'); sel.dataset.key = 'cur-set';
      for (const s of list) { const o = h('option', null, s.holder.replace(/^datasets\//, '') + ' · ' + s.name + ' · ' + s.model.name); o.value = keyOf(s); o.selected = keyOf(s) === st.key; sel.appendChild(o); }
      sel.addEventListener('change', () => { st.key = sel.value; st.chosen = new Set(); st.opened = null; st.colour = undefined; st.view = { k: 1, cu: 0.5, cv: 0.5 }; putInPlace(root.parentNode, panel(ctx)); });
      head.appendChild(sel);
    }
    c.facts = h('p', 'small muted cur-facts', set.rows.toLocaleString('en-GB') + ' records · ' + set.dimensions + ' dimensions · ' + set.model.name + (set.prefix ? ' · prefix “' + set.prefix + '”' : ''));
    head.appendChild(c.facts);
    if (!set.current) head.appendChild(h('p', 'small warnline', 'These embeddings describe run ' + set.records_run.slice(0, 8) + ', not the dataset\'s current product: they may not match its records.'));
    for (const s of broken) head.appendChild(h('p', 'small warnline', s.holder + ' · ' + s.name + ': ' + s.problem));
    const bar = h('div', 'cur-bar');
    c.colourSlot = h('span', 'cur-colour'); bar.appendChild(c.colourSlot);
    const tools = h('div', 'seg'); tools.setAttribute('role', 'group'); tools.setAttribute('aria-label', 'Dragging on the map');
    for (const [tool, label] of [['move', 'Move'], ['box', 'Box'], ['lasso', 'Lasso']]) {
      const b = button(null, label, 'cur-tool-' + tool, () => { st.tool = tool; for (const x of tools.children) x.setAttribute('aria-pressed', String(x === b)); });
      b.setAttribute('aria-pressed', String(st.tool === tool)); tools.appendChild(b);
    }
    bar.appendChild(tools);
    bar.appendChild(button('btn sm ghost', 'Reset view', 'cur-reset', () => { st.view = { k: 1, cu: 0.5, cv: 0.5 }; paint(c); }));
    head.appendChild(bar);
    root.appendChild(head);
    const box = h('div', 'cur-map');
    c.canvas = h('canvas'); c.canvas.tabIndex = 0; c.canvas.setAttribute('role', 'img'); c.canvas.dataset.key = 'cur-canvas';
    c.canvas.setAttribute('aria-label', 'Map of ' + set.rows + ' records; the arrow keys move between the nearest records, Enter opens one');
    c.tip = h('div', 'cur-tip'); c.tip.hidden = true; c.tip.setAttribute('aria-hidden', 'true');
    c.live = h('p', 'sr-only'); c.live.setAttribute('aria-live', 'polite');
    box.appendChild(c.canvas); box.appendChild(c.tip); box.appendChild(c.live);
    root.appendChild(box);
    c.legend = h('div', 'cur-legend'); root.appendChild(c.legend);
    c.selBar = h('div', 'cur-chosen'); root.appendChild(c.selBar);
    c.lists = h('div', 'cur-lists'); root.appendChild(c.lists);
    c.canvas.parentNode.appendChild(h('p', 'note cur-reading', 'Reading the map…'));
    wire(c);
    load(c);
    return root;
  }

  async function load(c) {
    const { st, set } = c;
    let m;
    try {
      const first = await P.read('embedding_map', base(set));
      const colour = st.colour === undefined ? (first.colours.includes('split') ? 'split' : null) : st.colour;
      st.colour = colour;
      m = colour ? await P.read('embedding_map', { ...base(set), colour }) : first;
    } catch (error) {
      if (!c.ctx.live()) return;
      putInPlace(c.root.querySelector('.cur-map'), A.refusal(error)); return;
    }
    if (!c.ctx.live() || !c.root.isConnected && c.m) return;
    c.m = decode(m);
    const reading = c.root.querySelector('.cur-reading'); if (reading) reading.remove();
    c.facts.textContent = [count(m.rows, 'record'), m.dimensions + ' dimensions', set.model.name, m.method === 'pca' ? 'principal components (' + m.explained.map(pct).join(' and ') + ' of the variance, from ' + count(m.sample, 'row') + ')' : 'the script\'s ' + m.method,
      m.missing ? count(m.missing, 'row') + ' with no record in the product' : null, set.prefix ? 'prefix “' + set.prefix + '”' : null].filter(Boolean).join(' · ');
    colourChoice(c); legend(c);
    D().paints(c.canvas, () => paint(c));
    chosenBar(c); lists(c);
  }
  function decode(m) {
    const x = D().floats(m.x_f32), y = D().floats(m.y_f32), at = new Map(m.ids.map((id, i) => [id, i]));
    const col = m.colour ? (m.colour.type === 'category' ? { codes: u16(m.colour.codes_u16) } : { values: D().floats(m.colour.values_f32) }) : null;
    return { ...m, x, y, at, col };
  }

  // ---- Colour ----------------------------------------------------------------------------------------------------------
  const WORD = c => c === 'split' ? 'Split' : c === 'kind' ? 'Kind' : c.startsWith('annotation:') ? 'Annotation · ' + c.slice(11) : 'Field · ' + c.slice(6);
  function colourChoice(c) {
    const l = h('label', 'cur-pick'); l.appendChild(document.createTextNode('Colour by '));
    const sel = h('select'); sel.dataset.key = 'cur-colour';
    for (const [v, t] of [['', 'nothing']].concat(c.m.colours.map(x => [x, WORD(x)]))) { const o = h('option', null, t); o.value = v; o.selected = v === (c.st.colour || ''); sel.appendChild(o); }
    sel.addEventListener('change', async () => {
      c.st.colour = sel.value || null;
      try { c.m = decode(c.st.colour ? await P.read('embedding_map', { ...base(c.set), colour: c.st.colour }) : await P.read('embedding_map', base(c.set))); } catch (error) { putInPlace(c.legend, A.refusal(error)); return; }
      legend(c); paint(c);
    });
    l.appendChild(sel); putInPlace(c.colourSlot, l);
  }
  function palette() {
    const t = D().token; const cats = []; for (let i = 1; i <= CATEGORIES; i++) cats.push(t('--cat-' + i));
    return { cats, other: t('--ink-3'), ink: t('--ink'), accent: t('--accent'), surface: t('--surface'), thin: t('--warn'), grid: t('--grid') };
  }
  /** [r, g, b] of a row, or null for a row with no value. */
  function colourOf(c, pal, i) {
    const col = c.m.col;
    if (!col) return pal.cats[0];
    if (col.codes) { const k = col.codes[i]; if (k === NO_CODE) return null; const cat = c.m.colour.categories[k]; return cat && !cat.other && k < CATEGORIES ? pal.cats[k] : pal.other; }
    const v = col.values[i]; if (!Number.isFinite(v)) return null;
    return c._ramp(v);
  }
  function legend(c) {
    const box = h('div'); const m = c.m, pal = palette();
    if (!m.colour) { box.appendChild(h('span', 'small muted', 'One colour: choose what to colour by.')); }
    else if (m.colour.type === 'number') {
      c._ramp = D().ramp(m.colour.low, m.colour.high);
      const sw = h('span', 'cur-ramp'); sw.setAttribute('aria-hidden', 'true'); box.appendChild(h('span', 'small', WORD(m.colour.by) + ': ' + m.colour.low.toLocaleString('en-GB') + ' ')); box.appendChild(sw); box.appendChild(h('span', 'small', ' ' + m.colour.high.toLocaleString('en-GB')));
    } else {
      m.colour.categories.forEach((cat, k) => {
        const item = h('span', 'cur-key'); const sw = h('span', 'sw'); const rgb = !cat.other && k < CATEGORIES ? pal.cats[k] : pal.other; sw.style.background = 'rgb(' + rgb.join(',') + ')'; sw.dataset.cat = cat.other || k >= CATEGORIES ? 'other' : String(k + 1);
        item.appendChild(sw); item.appendChild(h('span', null, cat.name + ' · ' + cat.count.toLocaleString('en-GB'))); box.appendChild(item);
      });
    }
    if (m.thin.length) { const item = h('span', 'cur-key'); const sw = h('span', 'sw thin'); item.appendChild(sw); item.appendChild(h('span', null, 'thin region')); box.appendChild(item); }
    box.dataset.colour = m.colour ? m.colour.by : '';
    putInPlace(c.legend, box);
  }

  // ---- Drawing --------------------------------------------------------------------------------------------------------
  const PAD = 12;
  function frame(c, W, H) {
    const dpr = window.devicePixelRatio || 1, p = PAD * dpr, [x0, x1, y0, y1] = c.m.bounds, v = c.st.view;
    const iw = W - 2 * p, ih = H - 2 * p;
    const sx = x => p + ((((x - x0) / (x1 - x0)) - v.cu) * v.k + 0.5) * iw;
    const sy = y => p + (((1 - (y - y0) / (y1 - y0)) - v.cv) * v.k + 0.5) * ih;
    const back = (px, py) => [((px - p) / iw - 0.5) / v.k + v.cu, ((py - p) / ih - 0.5) / v.k + v.cv];
    return { dpr, p, iw, ih, sx, sy, back };
  }
  function paint(c) {
    if (!c.m || !c.canvas.isConnected) return;
    const wide = c.canvas.clientWidth; const size = D().fit(c.canvas, Math.max(260, Math.min(460, Math.round(wide * 0.7)))); if (!size) return;
    const [W, H] = size, ctx = c.canvas.getContext('2d'), m = c.m, pal = palette(), f = frame(c, W, H);
    if (m.colour && m.colour.type === 'number') c._ramp = D().ramp(m.colour.low, m.colour.high);
    c.f = f;
    ctx.clearRect(0, 0, W, H);
    ctx.fillStyle = 'rgb(' + pal.surface.join(',') + ')'; ctx.fillRect(0, 0, W, H);
    // Thin cells, washed.
    const [x0, x1, y0, y1] = m.bounds, cells = m.grid.cells;
    ctx.fillStyle = 'rgba(' + pal.thin.join(',') + ',0.14)';
    for (const t of m.thin) { const a = f.sx(t.x[0]), b = f.sx(t.x[1]), top = f.sy(t.y[1]), bot = f.sy(t.y[0]); ctx.fillRect(a, top, b - a, bot - top); }
    void x0; void x1; void y0; void y1; void cells;
    const r = Math.max(1.5, 2.4 * f.dpr), n = m.ids.length, px = new Float32Array(n), py = new Float32Array(n);
    for (let i = 0; i < n; i++) { px[i] = f.sx(m.x[i]); py[i] = f.sy(m.y[i]); }
    c.pts = { px, py };
    // Rows with no value first and faint, then the rest.
    for (let pass = 0; pass < 2; pass++) for (let i = 0; i < n; i++) {
      const rgb = colourOf(c, pal, i); if ((rgb === null) !== (pass === 0)) continue;
      if (px[i] < -r || py[i] < -r || px[i] > W + r || py[i] > H + r) continue;
      ctx.fillStyle = rgb === null ? 'rgba(' + pal.other.join(',') + ',0.45)' : 'rgb(' + rgb.join(',') + ')';
      ctx.beginPath(); ctx.arc(px[i], py[i], r, 0, 6.2832); ctx.fill();
    }
    // What is chosen: a ring in ink. The opened record: a ring in the accent, joined to its most alike.
    ctx.lineWidth = Math.max(1, f.dpr); ctx.strokeStyle = 'rgb(' + pal.ink.join(',') + ')';
    for (const id of c.st.chosen) { const i = m.at.get(id); if (i == null) continue; ctx.beginPath(); ctx.arc(px[i], py[i], r + 1.6 * f.dpr, 0, 6.2832); ctx.stroke(); }
    const o = c.st.opened != null ? m.at.get(c.st.opened) : null;
    if (o != null) {
      ctx.strokeStyle = 'rgb(' + pal.accent.join(',') + ')'; ctx.lineWidth = 1.5 * f.dpr;
      for (const nb of c.like || []) { const j = m.at.get(nb.id); if (j == null) continue; ctx.beginPath(); ctx.moveTo(px[o], py[o]); ctx.lineTo(px[j], py[j]); ctx.stroke(); }
      ctx.lineWidth = 2 * f.dpr; ctx.beginPath(); ctx.arc(px[o], py[o], r + 3 * f.dpr, 0, 6.2832); ctx.stroke();
    }
    if (c.drag && c.drag.tool !== 'move' && c.drag.path.length > 1) {
      ctx.strokeStyle = 'rgb(' + pal.accent.join(',') + ')'; ctx.lineWidth = f.dpr; ctx.setLineDash([4 * f.dpr, 3 * f.dpr]); ctx.beginPath();
      if (c.drag.tool === 'box') { const [a, b] = [c.drag.path[0], c.drag.path[c.drag.path.length - 1]]; ctx.rect(a[0], a[1], b[0] - a[0], b[1] - a[1]); }
      else { ctx.moveTo(c.drag.path[0][0], c.drag.path[0][1]); for (const q of c.drag.path) ctx.lineTo(q[0], q[1]); ctx.closePath(); }
      ctx.stroke(); ctx.setLineDash([]);
    }
    c.canvas.dataset.drawn = String(n);
  }
  /** The row nearest the canvas point (device pixels) within 10 CSS pixels, or null. */
  function nearest(c, X, Y) {
    if (!c.pts) return null;
    const { px, py } = c.pts, lim = (10 * (window.devicePixelRatio || 1)) ** 2; let best = null, bd = lim;
    for (let i = 0; i < px.length; i++) { const d = (px[i] - X) ** 2 + (py[i] - Y) ** 2; if (d < bd) { bd = d; best = i; } }
    return best;
  }
  const at = (c, e) => { const r = c.canvas.getBoundingClientRect(), dpr = window.devicePixelRatio || 1; return [(e.clientX - r.left) * dpr, (e.clientY - r.top) * dpr]; };
  function inside(poly, x, y) { let inn = false; for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) { const [xi, yi] = poly[i], [xj, yj] = poly[j]; if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inn = !inn; } return inn; }
  function valueWord(c, i) {
    const col = c.m.col; if (!col) return '';
    if (col.codes) { const k = col.codes[i]; return k === NO_CODE ? 'no ' + WORD(c.m.colour.by).toLowerCase() : c.m.colour.categories[k].name; }
    return Number.isFinite(col.values[i]) ? String(col.values[i]) : 'no value';
  }
  function wire(c) {
    const cv = c.canvas, st = c.st;
    cv.addEventListener('wheel', e => {
      if (!c.f) return; e.preventDefault();
      const [X, Y] = at(c, e), [u, v] = c.f.back(X, Y), k = Math.min(200, Math.max(1, st.view.k * Math.exp(-e.deltaY * 0.0015)));
      const fx = (X - c.f.p) / c.f.iw - 0.5, fy = (Y - c.f.p) / c.f.ih - 0.5;
      st.view = { k, cu: u - fx / k, cv: v - fy / k }; paint(c);
    }, { passive: false });
    cv.addEventListener('pointerdown', e => {
      if (!c.f || e.button !== 0) return;
      cv.setPointerCapture(e.pointerId);
      c.drag = { tool: e.shiftKey && st.tool === 'move' ? 'box' : st.tool, path: [at(c, e)], view: { ...st.view }, add: e.shiftKey, moved: false };
    });
    cv.addEventListener('pointermove', e => {
      const [X, Y] = at(c, e);
      if (c.drag) {
        const d = c.drag, [sx, sy] = d.path[0];
        if (Math.abs(X - sx) + Math.abs(Y - sy) > 4) d.moved = true;
        if (d.tool === 'move') st.view = { ...d.view, cu: d.view.cu - (X - sx) / c.f.iw / d.view.k, cv: d.view.cv - (Y - sy) / c.f.ih / d.view.k };
        else d.path.push([X, Y]);
        paint(c); return;
      }
      hover(c, nearest(c, X, Y), e);
    });
    const end = e => {
      const d = c.drag; c.drag = null; if (!d) return;
      if (!d.moved) { const i = nearest(c, ...at(c, e)); if (i != null) open(c, c.m.ids[i]); paint(c); return; }
      if (d.tool !== 'move') {
        const { px, py } = c.pts, chosen = d.add ? new Set(st.chosen) : new Set();
        if (d.tool === 'box') {
          const [a, b] = [d.path[0], d.path[d.path.length - 1]], lx = Math.min(a[0], b[0]), hx = Math.max(a[0], b[0]), ly = Math.min(a[1], b[1]), hy = Math.max(a[1], b[1]);
          for (let i = 0; i < px.length; i++) if (px[i] >= lx && px[i] <= hx && py[i] >= ly && py[i] <= hy) chosen.add(c.m.ids[i]);
        } else for (let i = 0; i < px.length; i++) if (inside(d.path, px[i], py[i])) chosen.add(c.m.ids[i]);
        st.chosen = chosen; st.form = false; st.kept = null; chosenBar(c);
        c.live.textContent = count(chosen.size, 'record') + ' chosen.';
      }
      paint(c);
    };
    cv.addEventListener('pointerup', end);
    cv.addEventListener('pointercancel', () => { c.drag = null; paint(c); });
    cv.addEventListener('pointerleave', () => hover(c, null));
    cv.addEventListener('keydown', e => {
      if (!c.m || !c.pts) return;
      const dirs = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
      if (e.key === 'Enter' && c.hover != null) { e.preventDefault(); open(c, c.m.ids[c.hover]); return; }
      if (e.key === 'Escape' && st.chosen.size) { st.chosen = new Set(); chosenBar(c); paint(c); return; }
      const d = dirs[e.key]; if (!d) return;
      e.preventDefault(); e.stopPropagation();
      const { px, py } = c.pts, from = c.hover != null ? c.hover : st.opened != null && c.m.at.has(st.opened) ? c.m.at.get(st.opened) : null;
      let best = null, bd = Infinity;
      for (let i = 0; i < px.length; i++) {
        if (from == null) { const dd = (px[i] - c.canvas.width / 2) ** 2 + (py[i] - c.canvas.height / 2) ** 2; if (dd < bd) { bd = dd; best = i; } continue; }
        if (i === from) continue;
        const dx = px[i] - px[from], dy = py[i] - py[from], along = dx * d[0] + dy * d[1]; if (along <= 0) continue;
        const across = Math.abs(dx * d[1] - dy * d[0]), score = along + 2 * across; if (score < bd) { bd = score; best = i; }
      }
      if (best != null) { hover(c, best); c.live.textContent = c.m.ids[best] + (c.m.col ? ', ' + valueWord(c, best) : '') + '.'; }
    });
  }
  function hover(c, i, e) {
    c.hover = i; clearTimeout(c.rest);
    if (i == null) { c.tip.hidden = true; return; }
    const dpr = window.devicePixelRatio || 1;
    c.tip.textContent = ''; c.tip.appendChild(h('b', 'mono', c.m.ids[i])); const w = valueWord(c, i); if (w) c.tip.appendChild(h('span', null, w));
    c.tip.style.left = Math.round(c.pts.px[i] / dpr + 10) + 'px'; c.tip.style.top = Math.round(c.pts.py[i] / dpr + 10) + 'px'; c.tip.hidden = false;
    const id = c.m.ids[i];
    c.rest = setTimeout(() => { if (c.hover === i && c.ctx.live()) c.ctx.show(id, c.set.records_run); }, REST_MS);
    void e;
  }
  /** Opens a record: the viewer shows it, the map rings it, More like this lists its neighbours. */
  function open(c, id) {
    c.st.opened = id; c.ctx.show(id, c.set.records_run);
    c.st.list = 'like'; lists(c); paint(c);
  }

  // ---- What is chosen ---------------------------------------------------------------------------------------------------
  function chosenBar(c) {
    const st = c.st, box = h('div'), n = st.chosen.size;
    if (st.kept) box.appendChild(h('p', 'small good-line', 'Kept ' + st.kept + ' as an unsaved edit; Save writes it to the project folder. Building it is planned as any build is.'));
    if (!n) { box.appendChild(h('p', 'small muted', 'Drag with Box or Lasso to choose records (Shift adds to them).')); putInPlace(c.selBar, box); return; }
    const line = h('div', 'cur-chosen-line'); line.appendChild(h('b', 'cur-count', count(n, 'record') + ' chosen'));
    const ordered = () => c.m.ids.filter(id => st.chosen.has(id));
    if (A.may('edit')) {
      line.appendChild(button('btn sm', 'New dataset from these', 'cur-new', () => { st.form = !st.form; chosenBar(c); }));
      line.appendChild(button('btn sm', 'Freeze these', 'cur-freeze', () => {
        if (n > SELECT_LIMIT) { st.form = false; putInPlace(c.selBar, refusalBox('At most ' + SELECT_LIMIT.toLocaleString('en-GB') + ' records can be frozen by name; ' + n.toLocaleString('en-GB') + ' are chosen.')); return; }
        window.LabAnnotate.fillFreeze(c.ctx.ref, ordered()); c.ctx.act.go('data', 'new:freeze');
      }));
    }
    line.appendChild(button('btn sm ghost', 'Clear', 'cur-clear', () => { st.chosen = new Set(); st.form = false; chosenBar(c); paint(c); }));
    box.appendChild(line);
    if (st.form && A.may('edit')) box.appendChild(newForm(c, ordered));
    putInPlace(c.selBar, box);
  }
  const refusalBox = text => A.refusal(Object.assign(Error(text), { code: 'invalid' }));
  function newForm(c, ordered) {
    const F = window.LabAnnotate.forms, key = 'curnew', s = A.slot(key), f = h('div', 'form cur-form');
    let nameBox = null;
    f.appendChild(F.input(s, key, 'title', 'Title (required)', { max: 200, onInput: () => { if (!s.text.nameTyped && nameBox) { nameBox.value = F.slug(s.text.title || ''); s.text.name = nameBox.value; } } }));
    const nl = F.input(s, key, 'name', 'Name', { max: 120, hint: 'the file is datasets/<name>.json', placeholder: 'made from the title', onInput: v => { s.text.nameTyped = !!v; } });
    nameBox = nl.querySelector('input'); if (!s.text.nameTyped) { nameBox.value = F.slug(s.text.title || ''); s.text.name = nameBox.value; }
    f.appendChild(nl);
    f.appendChild(h('p', 'small faint', 'A dataset of exactly these ' + count(c.st.chosen.size, 'record') + ' of ' + c.ctx.ref + ', in its order, each as it is there (its split and annotations kept): the step select.'));
    f.appendChild(A.group(key, [
      { id: 'keep', label: 'Keep', cls: 'btn primary', who: 'edit', op: 'set_definition', busy: 'Keeping…',
        args: st => {
          const ids = ordered();
          if (ids.length > SELECT_LIMIT) throw Object.assign(Error('At most ' + SELECT_LIMIT.toLocaleString('en-GB') + ' records can be selected by name; ' + ids.length.toLocaleString('en-GB') + ' are chosen.'), { code: 'invalid' });
          const doc = { format: FORMAT, kind: 'dataset', title: (st.text.title || '').trim(), run: { step: 'select', inputs: { records: c.ctx.ref }, settings: { records: ids } } };
          return { reference: 'datasets/' + (st.text.name || '').trim(), text: F.textOf(doc) };
        },
        done: r => { c.st.kept = r.reference; c.st.form = false; } },
      { id: 'back', label: 'Cancel', cls: 'btn ghost', onClick: () => { c.st.form = false; chosenBar(c); } }]));
    return f;
  }

  // ---- The lists ------------------------------------------------------------------------------------------------------
  const LISTS = [['like', 'More like this'], ['duplicates', 'Duplicates'], ['outliers', 'Outliers'], ['leakage', 'Leakage'], ['thin', 'Thin regions']];
  function lists(c) {
    const st = c.st, box = h('div');
    const seg = h('div', 'seg cur-tabs'); seg.setAttribute('role', 'group'); seg.setAttribute('aria-label', 'Lists');
    const shown = LISTS.filter(([id]) => id !== 'leakage' || c.m.colours.includes('split'));
    if (!shown.some(([id]) => id === st.list)) st.list = 'duplicates';
    for (const [id, label] of shown) { const b = button(null, label, 'cur-list-' + id, () => { if (st.list !== id) { st.list = id; lists(c); } }); b.setAttribute('aria-pressed', String(st.list === id)); seg.appendChild(b); }
    box.appendChild(seg);
    const body = h('div', 'cur-list'); body.dataset.list = st.list; box.appendChild(body);
    putInPlace(c.lists, box);
    fillList(c, body);
  }
  function rowButton(c, key, parts, onClick) {
    const li = h('li'), b = button('row cur-row', null, key, onClick);
    for (const [cls, text] of parts) b.appendChild(h('span', cls, text));
    li.appendChild(b); return li;
  }
  const status = r => r.complete ? 'Every one of the ' + count(r.rows, 'record') + ' was examined.' : count(r.examined, 'record') + ' of ' + r.rows.toLocaleString('en-GB') + ' were examined within the search\'s bound; what is listed is exact for those.';
  function numberControl(c, label, name, min, max, step) {
    const l = h('label', 'cur-num'); l.appendChild(document.createTextNode(label + ' '));
    const i = h('input'); i.type = 'number'; i.min = String(min); i.max = String(max); i.step = String(step); i.value = c.st[name]; i.dataset.key = 'cur-' + name;
    i.addEventListener('change', () => { const v = Number(i.value); if (Number.isFinite(v) && v >= min && v <= max) { c.st[name] = i.value; lists(c); } });
    l.appendChild(i); return l;
  }
  async function fillList(c, body) {
    const st = c.st, set = c.set, controls = h('div', 'cur-controls'), ul = h('ul', 'rows cur-rows'), note = h('p', 'small muted');
    const done = () => { if (body.isConnected) { const f = document.createDocumentFragment(); f.appendChild(controls); f.appendChild(note); f.appendChild(ul); putInPlace(body, f); } };
    body.appendChild(h('p', 'note', 'Reading…'));
    try {
      if (st.list === 'like') {
        if (st.opened == null) { note.textContent = 'Open a record (click it on the map, or a row of a list) to see the records most like it.'; c.like = []; return done(); }
        const r = await P.read('embedding_neighbours', { ...base(set), record: st.opened, limit: 12 });
        c.like = r.neighbours; paint(c);
        note.textContent = 'The ' + r.neighbours.length + ' records most like ' + r.record + ', by cosine.';
        for (const n of r.neighbours) ul.appendChild(rowButton(c, 'cur-like-' + n.id, [['title mono', n.id], ['sub', [n.split, n.kind].filter(Boolean).join(' · ')], ['num', cos(n.cosine)]], () => open(c, n.id)));
      } else if (st.list === 'duplicates') {
        controls.appendChild(numberControl(c, 'Cosine at least', 'dup', 0.5, 1, 0.001));
        const r = await P.read('embedding_duplicates', { ...base(set), threshold: Number(st.dup), limit: 200 });
        note.textContent = (r.total ? count(r.total, 'pair') + ' (' + count(r.groups, 'record') + ')' : 'No pair') + ' at or above ' + r.threshold + '. ' + status(r);
        for (const p of r.pairs) ul.appendChild(rowButton(c, 'cur-dup-' + p.a + '-' + p.b, [['title mono', p.a + '  ≈  ' + p.b], ['sub', [p.a_split, p.b_split].filter(Boolean).join(' · ')], ['num', cos(p.cosine)]], () => { st.chosen = new Set([p.a, p.b]); chosenBar(c); open(c, p.a); }));
      } else if (st.list === 'outliers') {
        controls.appendChild(numberControl(c, 'Neighbour', 'k', 1, 50, 1));
        const r = await P.read('embedding_outliers', { ...base(set), k: Number(st.k), limit: 50 });
        note.textContent = 'Farthest from their ' + ordinal(r.k) + ' nearest record' + (r.median != null ? '; the median distance is ' + r.median.toFixed(4) : '') + '. ' + status(r);
        for (const o of r.outliers) ul.appendChild(rowButton(c, 'cur-out-' + o.id, [['title mono', o.id], ['sub', 'nearest ' + o.nearest + (o.split ? ' · ' + o.split : '')], ['num', o.distance.toFixed(4)]], () => open(c, o.id)));
      } else if (st.list === 'leakage') {
        controls.appendChild(numberControl(c, 'Cosine at least', 'leak', 0.5, 1, 0.001));
        const splits = c.m.colour && c.m.colour.by === 'split' ? c.m.colour.categories.map(x => x.name) : [st.train];
        const l = h('label', 'cur-num'); l.appendChild(document.createTextNode('Trained on ')); const sel = h('select'); sel.dataset.key = 'cur-train';
        for (const s of new Set([st.train, ...splits])) { const o = h('option', null, s); o.value = s; o.selected = s === st.train; sel.appendChild(o); }
        sel.addEventListener('change', () => { st.train = sel.value; lists(c); }); l.appendChild(sel); controls.appendChild(l);
        const r = await P.read('embedding_leakage', { ...base(set), threshold: Number(st.leak), train: st.train, limit: 200 });
        note.textContent = !Object.keys(r.splits).length ? 'The records have no splits.' : (r.leaked ? count(r.leaked, 'record') + ' outside ' + r.train + ' ' + (r.leaked === 1 ? 'has' : 'have') + ' a near-copy in it' : 'No record outside ' + r.train + ' has a near-copy in it') + ' at or above ' + r.threshold + '. ' + status(r);
        for (const p of r.pairs) ul.appendChild(rowButton(c, 'cur-leak-' + p.record, [['title mono', p.record + '  ≈  ' + p.near], ['sub', p.split + ' · ' + r.train], ['num', cos(p.cosine)]], () => { st.chosen = new Set([p.record, p.near]); chosenBar(c); open(c, p.record); }));
      } else {
        const m = c.m;
        note.textContent = m.thin.length ? count(m.thin.length, 'cell') + ' of the map\'s ' + m.grid.cells + ' × ' + m.grid.cells + ' hold few records: at most a quarter of the median of the cells that hold any. A row chooses its records.' : 'No cell of the map is thin.';
        for (const t of m.thin) ul.appendChild(rowButton(c, 'cur-thin-' + t.cell.join('-'), [['title', 'Cell ' + (t.cell[1] + 1) + ', ' + (t.cell[0] + 1)], ['sub mono', t.records.slice(0, 4).join(', ') + (t.count > 4 ? ', …' : '')], ['num', String(t.count)]], () => { st.chosen = new Set(t.records); chosenBar(c); paint(c); }));
      }
    } catch (error) { controls.appendChild(A.refusal(error)); }
    done();
  }
  const ordinal = n => n + (n % 100 >= 11 && n % 100 <= 13 ? 'th' : ['th', 'st', 'nd', 'rd'][n % 10] || 'th');

  // ---- Data: the Embed form ------------------------------------------------------------------------------------------
  /** Embed: a new datasets/<name> whose run is the step embed, kept as an unsaved edit. */
  function form(aside, act) {
    const F = window.LabAnnotate.forms;
    F.formDrawer(aside, 'data:new:embed', () => Promise.all([P.read('endpoint').catch(error => ({ error })), P.read('definitions', { kind: 'dataset' })]), (ins, [ep, defs]) => {
      const key = 'newembed', s = A.slot(key), em = ep.embedder || null;
      F.header(ins, 'new dataset · embed', 'Embed a dataset',
        'A vector for each text and image record of a dataset, asked of an embedding model the Pumas endpoint serves, written as embeddings Tuldok draws as a map. When the definition names no model, the machine\'s embedder is used: EmbeddingGemma 2 unless the owner set another.');
      const embedders = em ? em.embedders : [];
      if (ep.error || !ep.address || !ep.answered || !embedders.length) {
        const why = h('div', 'gen-none'); why.setAttribute('role', 'status');
        why.appendChild(h('p', 'failure', ep.error ? 'What the endpoint serves could not be read: ' + ep.error.message
          : !ep.address ? 'No Pumas endpoint is set on this machine, so there is nothing to embed with.'
            : !ep.answered ? 'The Pumas endpoint at ' + ep.address + ' does not answer: ' + (ep.problem || 'no reason was given.')
              : 'The Pumas endpoint at ' + ep.address + ' serves no embedding model now.'));
        const acts = h('div', 'actions'); acts.appendChild(button('btn', 'The endpoint on the Train tab', 'emb:endpoint', () => act.go('train', 'endpoint'))); acts.appendChild(button('btn ghost', 'Cancel', 'emb:cancel', () => act.select(null)));
        why.appendChild(acts); ins.appendChild(why); return;
      }
      const sets = defs.definitions.filter(d => !d.removed), f = h('div', 'form emb-form');
      let nameBox = null;
      f.appendChild(F.input(s, key, 'title', 'Title (required)', { max: 200, onInput: () => { if (!s.text.nameTyped && nameBox) { nameBox.value = F.slug(s.text.title || ''); s.text.name = nameBox.value; } } }));
      const nl = F.input(s, key, 'name', 'Name', { max: 120, hint: 'the file is datasets/<name>.json', placeholder: 'made from the title', onInput: v => { s.text.nameTyped = !!v; } });
      nameBox = nl.querySelector('input'); if (!s.text.nameTyped) { nameBox.value = F.slug(s.text.title || ''); s.text.name = nameBox.value; }
      f.appendChild(nl);
      if (!sets.length) f.appendChild(h('p', 'failure', 'The project has no dataset to embed.'));
      else f.appendChild(F.choice(s, key, 'dataset', 'The dataset whose records are embedded', sets.map(d => [d.reference, d.title + ' · ' + d.reference]), sets[0].reference));
      const named = em.named_by === 'setting' ? 'this machine\'s embedder, ' + em.model : 'EmbeddingGemma 2';
      const resolved = em.chosen ? em.chosen.model + ' · ' + em.chosen.profile + ' (' + em.chosen.model_id + ')' : 'not served now';
      const options = [['', 'Default: ' + named + ' → ' + resolved]].concat(embedders.map(x => [x.model + '\u0000' + x.profile, x.model + ' · ' + x.profile + ' (' + x.model_id + ')']));
      f.appendChild(F.choice(s, key, 'model', 'Model', options, ''));
      const line = h('p', 'small faint emb-line'); line.dataset.key = 'emb-default';
      line.textContent = em.chosen ? 'With the default, the definition names no model: a build uses ' + named + ' as this machine resolves it then (now ' + resolved + '). Choose a model to write it into the definition.'
        : 'The default embedder cannot be used now: ' + (em.problem || 'it is not served.') + ' Choose a served model, or the owner sets the machine\'s embedder on the Train tab.';
      f.appendChild(line);
      f.appendChild(F.input(s, key, 'prefix', 'Prefix', { max: 1000, value: em.prefix, hint: 'put before each text; EmbeddingGemma expects a task, such as “task: clustering | query: ”. Unchanged, it is not written and the machine\'s applies.' }));
      const two = h('div', 'two');
      const bound = (embedders.find(x => x.model + '\u0000' + x.profile === s.text.model) || em.chosen && embedders.find(x => x.model === em.chosen.model && x.profile === em.chosen.profile) || {}).dimensions;
      const dims = F.input(s, key, 'dimensions', 'Dimensions', { type: 'number', hint: bound ? 'empty: the model\'s own; ' + bound.minimum + ' to ' + bound.maximum + ' (truncated by Pumas)' : 'empty: the model\'s own; Pumas truncates to fewer' });
      dims.querySelector('input').min = '1'; dims.querySelector('input').max = String(bound ? bound.maximum : 4096); two.appendChild(dims);
      const batch = F.input(s, key, 'batch', 'Batch', { type: 'number', hint: 'records a request carries; empty: 32' }); batch.querySelector('input').min = '1'; batch.querySelector('input').max = '256'; two.appendChild(batch);
      f.appendChild(two);
      ins.appendChild(f);
      ins.appendChild(A.group(key, [
        { id: 'keep', label: 'Keep', cls: 'btn primary', who: 'edit', op: 'set_definition', busy: 'Keeping…',
          args: st => ({ reference: 'datasets/' + (st.text.name || '').trim(), text: F.textOf(embedDoc(st.text, em)) }), done: r => { act.select(r.reference); } },
        { id: 'back', label: 'Cancel', cls: 'btn ghost', onClick: () => act.select(null) }]));
      ins.appendChild(h('p', 'note', 'Keep checks the definition and keeps it in Tuldok as an unsaved edit; Save writes it. Building it is planned and requested as any build is.'));
    });
  }
  function whole(text, label, min, max) {
    const raw_ = String(text == null ? '' : text).trim(); if (!raw_) return null;
    const v = Number(raw_); if (!Number.isInteger(v) || v < min || v > max) throw Object.assign(Error(label + ' is a whole number from ' + min + ' to ' + max + '; "' + raw_ + '" is not.'), { code: 'invalid' });
    return v;
  }
  /** The definition an embed writes (docs/contracts/project-folder.md, Steps Tuldok provides). */
  function embedDoc(x, em) {
    const settings = {};
    if (x.model) { const [model, profile] = x.model.split('\u0000'); settings.model = model; if (em.embedders.filter(e => e.model === model).length > 1) settings.profile = profile; }
    if (x.prefix != null && x.prefix !== em.prefix) settings.prefix = x.prefix;
    const d = whole(x.dimensions, 'Dimensions', 1, 4096); if (d !== null) settings.dimensions = d;
    const b = whole(x.batch, 'Batch', 1, 256); if (b !== null) settings.batch = b;
    return { format: FORMAT, kind: 'dataset', title: (x.title || '').trim(), run: { step: 'embed', inputs: { records: x.dataset }, settings } };
  }

  // ---- Train: the machine's embedder in the endpoint's drawer -----------------------------------------------------------
  /** The embedder part of the endpoint's drawer (generate.js): what it resolves to; for the owner, a model and prefix to set. */
  function embedderPart(ins, ep) {
    const em = ep.embedder; if (!em) return;
    const part = h('div', 'ep-part emb-part'); part.appendChild(h('h3', null, 'Embedder'));
    const dl = h('dl', 'setup'); const put = (k, v) => { dl.appendChild(h('dt', null, k)); dl.appendChild(h('dd', null, v)); };
    put('Named by', em.named_by === 'setting' ? 'this machine: ' + em.model + (em.profile ? ' · ' + em.profile : '') : 'the default, EmbeddingGemma 2');
    put('Resolves to', em.chosen ? em.chosen.model + ' · ' + em.chosen.profile + ' (' + em.chosen.model_id + ')' : 'nothing now');
    put('Prefix', em.prefix ? '“' + em.prefix + '”' : 'none');
    part.appendChild(dl);
    if (em.problem && ep.address) part.appendChild(h('p', 'small warnline', em.problem));
    if (A.may('owner')) {
      const key = 'endpoint:embedder', s = A.slot(key), F = window.LabAnnotate.forms, f = h('div', 'form');
      const options = [['', 'EmbeddingGemma 2 (the default)']].concat(em.embedders.map(x => [x.model + '\u0000' + x.profile, x.model + ' · ' + x.profile + ' (' + x.model_id + ')']));
      if (s.text.model == null) s.text.model = em.model ? em.model + '\u0000' + (em.profile || (em.chosen ? em.chosen.profile : '')) : '';
      f.appendChild(F.choice(s, key, 'model', 'Embed with, when a definition names no model', options, ''));
      f.appendChild(F.input(s, key, 'prefix', 'Prefix', { max: 1000, value: em.prefix }));
      f.appendChild(A.group(key, [{ id: 'set', label: 'Set the embedder', cls: 'btn', who: 'owner', op: 'set_embedder', busy: 'Checking…',
        args: st => { const [model, profile] = (st.text.model || '').split('\u0000'); const several = model && em.embedders.filter(e => e.model === model).length > 1; return { model: model || null, profile: several ? profile : null, prefix: st.text.prefix == null ? em.prefix : st.text.prefix }; } }]));
      part.appendChild(f);
    }
    ins.appendChild(part);
  }

  return { sets, usable, panel, form, embedderPart };
})();
