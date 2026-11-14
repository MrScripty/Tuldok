'use strict';
// A model's weights (docs/plans/definition-first-projects/spec-d2.md section 4): the block "Weights" of a model's
// drawer, after "Runs and product", when the model has a current product with a weights file. Its head names the
// file (a select when there are several), its size and parameters; a file Tuldok does not read shows its reason
// and nothing else. "Compare with" offers the weights the run started from and the models the map draws a
// derivation line from; choosing one asks weights_compare once. The layers are a table (name, shape of the first
// tensor, parameters, a small distribution asked for when its row comes on screen, and when comparing a bar of
// how much it changed); a layer opened shows a tensor's statistics, its larger distribution and its values as
// images, one image for two axes (array_slice), tiles for three or more (array_tiles), coloured diverging about
// zero; when comparing, this, the other, or their difference (computed here, tile by tile).
//
// Updating in place (spec-w4): the block is built off the page and put in place whole. Read again for the model
// on screen (screens.js), it is built from the person's place in it (file, comparison, sort, layer and tensor
// opened, axes, page, mode) and resolves only once complete, so the drawer puts it in place in one step. The
// person's own choices draw the block again the same way (putInPlace, the focus kept by data-key); a slider moves
// only the tiles. A product does not change once its run finished: the distributions and tiles read are kept here
// for the page's life (bounded), so a block drawn again draws them at once and asks for none again.
window.LabWeights = (() => {
  const P = window.TuldokProject, S = window.LabScreens, C = window.LabCharts, h = C.h, R = P.product;
  const { bytes, putInPlace } = S.parts;
  const D = window.LabInside.drawing;
  const SMALL_BINS = 32, BIG_BINS = 64;   // a row's distribution, the opened tensor's
  const TILES = 16;                       // tiles on a page
  const SLICE_MOST = 256;                 // rows and columns of a two-axis image
  const KEEP = 64;                        // tiles and slices kept
  const MARGIN = '40px 0px';              // how near the drawer's view a row's distribution is asked for
  const fmt = v => v == null ? '—' : C.fmtSci(v);
  const num = n => n == null ? '—' : n.toLocaleString('en-GB');
  const shapeText = s => s.length ? s.join(' × ') : 'one value';
  const plural = (n, one, many) => num(n) + ' ' + (n === 1 ? one : many || one + 's');
  const button = (cls, text, onClick) => { const b = h('button', cls, text); b.type = 'button'; if (onClick) b.addEventListener('click', onClick); return b; };
  const refusal = error => window.LabActions.refusal(error);

  // ---- What is kept ------------------------------------------------------------------------------------------------
  const places = new Map();   // model id -> the person's place in its block
  const placeOf = id => { if (!places.has(id)) places.set(id, { file: null, compare: '', sort: 'file', layer: null, tensor: null, mode: 'this', views: new Map() }); return places.get(id); };
  const summaries = new Map();   // run \n path \n array \n bins -> an answer of array_summary
  const sumKey = (run, path, array, bins) => [run, path, array, bins].join('\n');
  const answers = new Map();     // the tiles and slices read, the latest last
  async function kept(key, ask) {
    if (answers.has(key)) { const v = answers.get(key); answers.delete(key); answers.set(key, v); return v; }
    const v = await ask(); answers.set(key, v); while (answers.size > KEEP) answers.delete(answers.keys().next().value); return v;
  }
  async function summary(run, path, array, bins) {
    const key = sumKey(run, path, array, bins);
    if (!summaries.has(key)) summaries.set(key, await R.summary(run, { path, array, bins }));
    return summaries.get(key);
  }

  // ---- Reading ---------------------------------------------------------------------------------------------------------
  /** The weights files of a model's current products, each with its run and a key. */
  async function filesOf(reference) {
    const products = (await P.read('products', { reference })).products.filter(p => p.run_id);
    const lists = await Promise.all(products.map(p => R.weights(p.run_id).then(w => w.files.map(f => Object.assign({ run: p.run_id, subject: p.subject || '', key: p.run_id + '\n' + f.path }, f)))));
    return lists.flat();
  }
  /** What a file can be compared with: the weights it started from, and the readable weights of each model it derives from. */
  async function choicesFor(m, g, f) {
    const out = [];
    if (f.starts_from) out.push({ key: 'start', label: 'The weights it started from', detail: f.starts_from, run: f.run, path: f.starts_from });
    const parents = [m.parent].filter(p => p && g.byId.has(p));
    for (const ref of parents) {
      const files = await filesOf(ref).catch(() => []), readable = files.filter(x => x.readable), o = g.byId.get(ref);
      for (const x of readable) out.push({ key: 'model\n' + ref + '\n' + x.key, label: 'The model it derives from', detail: (o.short ? o.short + ' · ' : '') + o.title + (readable.length > 1 ? ' · ' + x.path : ''), run: x.run, path: x.path, model: ref });
    }
    return out;
  }

  /**
   * Fills box (a block of the drawer of model m, on the page or not yet) with the Weights block, or hides it
   * when the model has no weights file. Resolves once the block is complete. scroller: the drawer's own scroll
   * (the root of the rows' observer); live(): whether the drawer still shows this model.
   */
  async function block(box, m, g, scroller, live) {
    const st = placeOf(m.id), ctx = { box, m, g, st, scroller, live, io: null, turn: 0 };
    const root = await build(ctx);
    if (!live()) return;
    if (st.ctx && st.ctx !== ctx && st.ctx.io) st.ctx.io.disconnect();   // the block it replaces asks for nothing more
    st.ctx = ctx;
    if (!root) { box.hidden = true; box.replaceChildren(); return; }
    box.hidden = false; box.replaceChildren(root); watch(ctx, root);
  }
  /** Draws the block again for the person's own choice: built off the page, then put in place with the focus and the scroll kept. */
  async function again(ctx) {
    const mine = ++ctx.turn;
    ctx.box.setAttribute('aria-busy', 'true');
    let root; try { root = await build(ctx); } catch (error) { root = h('div'); root.appendChild(h('h3', null, 'Weights')); root.appendChild(refusal(error)); }
    if (mine !== ctx.turn || !ctx.box.isConnected) return;
    ctx.box.removeAttribute('aria-busy');
    if (ctx.io) ctx.io.disconnect();
    putInPlace(ctx.box, root || h('div'), ctx.scroller);
    watch(ctx, root);
  }

  /** The block's content, read in full; null when the model has no weights file. */
  async function build(ctx) {
    const { m, g, st } = ctx;
    const files = await filesOf(m.id);
    if (!files.length) return null;
    const f = files.find(x => x.key === st.file) || files.find(x => x.readable) || files[0]; st.file = f.key;
    const root = h('div', 'wts');
    root.appendChild(h('h3', null, 'Weights'));
    // The head: the file, its size and parameters.
    const head = h('div', 'wts-head');
    if (files.length > 1) {
      const s = h('select'); s.setAttribute('aria-label', 'Weights file'); s.dataset.key = 'wts-file';
      for (const x of files) { const o = h('option', null, x.path + (x.subject ? ' · ' + x.subject : '') + (x.readable ? '' : ' (not read)')); o.value = x.key; o.selected = x === f; s.appendChild(o); }
      s.addEventListener('change', () => { Object.assign(st, { file: s.value, compare: '', layer: null, tensor: null, mode: 'this' }); again(ctx); });
      const l = h('label', 'iv-field wts-pick'); l.appendChild(document.createTextNode('File')); l.appendChild(s); head.appendChild(l);
    } else head.appendChild(h('p', 'mono wts-path', f.path));
    head.appendChild(h('p', 'small muted wts-size', [bytes(f.bytes), f.readable ? plural(f.parameters, 'parameter') : null, f.readable ? plural(f.layers.length, 'layer') + ', ' + plural(f.tensors, 'tensor') : null].filter(Boolean).join(' · ')));
    root.appendChild(head);
    if (!f.readable) { root.appendChild(h('p', 'empty wts-reason', f.reason)); return root; }
    if (f.layers.length && f.tensors > f.layers.reduce((n, l) => n + l.tensors.length, 0)) root.appendChild(h('p', 'note', 'The first ' + num(f.layers.reduce((n, l) => n + l.tensors.length, 0)) + ' tensors are listed.'));
    // Compare with.
    const choices = await choicesFor(m, g, f);
    if (!choices.some(c => c.key === st.compare)) st.compare = '';
    const choice = choices.find(c => c.key === st.compare) || null;
    let cmp = null, cmpError = null;
    if (choice) try { cmp = await R.compare(f.run, f.path, choice.run, choice.path); } catch (error) { cmpError = error; }
    if (choices.length) {
      const s = h('select'); s.setAttribute('aria-label', 'Compare with'); s.dataset.key = 'wts-compare';
      const none = h('option', null, 'Nothing'); none.value = ''; s.appendChild(none);
      for (const c of choices) { const o = h('option', null, c.label + ': ' + c.detail); o.value = c.key; o.selected = c === choice; s.appendChild(o); }
      s.addEventListener('change', () => { st.compare = s.value; if (!s.value && st.sort === 'change') st.sort = 'file'; if (!s.value) st.mode = 'this'; again(ctx); });
      const l = h('label', 'iv-field wts-pick'); l.appendChild(document.createTextNode('Compare with')); l.appendChild(s); root.appendChild(l);
    }
    if (cmpError) root.appendChild(refusal(cmpError));
    const cmpd = cmp ? compared(cmp) : null;
    if (cmp) {
      const t = cmp.total;
      root.appendChild(h('p', 'small muted wts-total', 'All compared: ' + plural(t.parameters, 'parameter') + ', relative change ' + (t.relative_change == null ? (t.other_norm === 0 ? 'from zero' : '—') : fmt(t.relative_change)) + ', cosine ' + fmt(t.cosine) + ', largest change ' + fmt(t.largest_change) + '.'));
      if (cmp.only_there.length) root.appendChild(h('p', 'small muted wts-there', 'Only in the other: ' + cmp.only_there.join(', ') + '.'));
    }
    // Sorting.
    if (st.sort === 'change' && !cmp) st.sort = 'file';
    const seg = h('div', 'seg wts-sort'); seg.setAttribute('role', 'group'); seg.setAttribute('aria-label', 'Sort the layers by');
    for (const [key, label] of [['file', 'File order'], ['size', 'Size']].concat(cmp ? [['change', 'Change']] : [])) {
      const b = button(null, label, () => { if (st.sort !== key) { st.sort = key; again(ctx); } }); b.setAttribute('aria-pressed', String(st.sort === key)); b.dataset.key = 'wts-sort-' + key; seg.appendChild(b);
    }
    const bar = h('div', 'wts-bar'); bar.appendChild(h('span', 'small muted', 'Sort by')); bar.appendChild(seg); root.appendChild(bar);
    // The layers.
    const rows = f.layers.map((layer, i) => ({ layer, i, change: cmpd ? layerChange(layer, cmpd) : null }));
    const rel = r => r.change && r.change.rel != null ? r.change.rel : r.change && r.change.zero ? Infinity : -1;
    if (st.sort === 'size') rows.sort((a, b) => b.layer.parameters - a.layer.parameters || a.i - b.i);
    if (st.sort === 'change') rows.sort((a, b) => rel(b) - rel(a) || a.i - b.i);
    const most = Math.max(0, ...rows.map(r => r.change && r.change.rel != null ? r.change.rel : 0));
    const table = h('table', 'tv wts-table' + (cmp ? ' comparing' : ''));
    const cols = h('colgroup'); for (const c of ['name', 'n', 'dist'].concat(cmp ? ['chg'] : [])) cols.appendChild(h('col', 'wc-' + c)); table.appendChild(cols);
    const th = h('thead'), hr = h('tr');
    for (const [label, cls] of [['Layer', ''], ['Parameters', 'n'], ['Values', '']].concat(cmp ? [['Change', '']] : [])) hr.appendChild(h('th', cls, label));
    th.appendChild(hr); table.appendChild(th);
    const tb = h('tbody');
    for (const r of rows) {
      const { layer } = r, open = st.layer === layer.name, first = layer.tensors[0];
      const tr = h('tr', 'wts-row'); tr.dataset.layer = layer.name;
      const name = h('td', 'wts-name');
      const nb = button('linkish', null, () => { if (st.layer === layer.name) { st.layer = null; st.tensor = null; } else { st.layer = layer.name; st.tensor = layer.tensors[0].array; } again(ctx); });
      nb.dataset.key = 'wts-layer-' + layer.name; nb.setAttribute('aria-expanded', String(open));
      nb.appendChild(h('span', 'mono wts-lname', layer.name));
      nb.setAttribute('aria-label', 'Layer ' + layer.name + ', ' + plural(layer.parameters, 'parameter') + (open ? '; press to close' : '; press to open'));
      name.appendChild(nb);
      name.appendChild(h('span', 'wts-shape', shapeText(first.shape) + (layer.tensors.length > 1 ? ' · ' + plural(layer.tensors.length, 'tensor') : '')));
      if (r.change && r.change.marks.length) for (const mk of r.change.marks) { const s = h('span', 'wts-mark ' + mk.kind, mk.text); s.title = mk.title; name.appendChild(s); }
      tr.appendChild(name);
      tr.appendChild(h('td', 'n', num(layer.parameters)));
      const dist = h('td', 'wts-dist'), cv = h('canvas', 'wts-spark'); cv.setAttribute('role', 'img'); cv.setAttribute('aria-label', 'Distribution of ' + first.array + ': not read yet');
      cv.dataset.run = f.run; cv.dataset.path = f.path; cv.dataset.array = first.array;
      dist.appendChild(cv); tr.appendChild(dist);
      if (cmp) tr.appendChild(changeCell(r.change, most));
      tb.appendChild(tr);
      if (open) {
        const or = h('tr', 'wts-open'), td = h('td'); td.colSpan = cmp ? 4 : 3;
        td.appendChild(await tensorPanel(ctx, f, layer, cmpd, choice));
        or.appendChild(td); tb.appendChild(or);
      }
    }
    table.appendChild(tb);
    const wrap = h('div', 'wts-tablebox'); wrap.appendChild(table); root.appendChild(wrap);
    return root;
  }

  /** The comparison by array: rows of tensors compared, and the marks of those that are not. */
  function compared(cmp) {
    const rows = new Map(cmp.tensors.map(t => [t.array, t])), marks = new Map();
    for (const a of cmp.only_here) marks.set(a, { kind: 'only', text: 'only here', title: a + ' is not in the other file' });
    for (const r of cmp.reshaped) marks.set(r.array, { kind: 'reshaped', text: 'reshaped', title: r.array + ' is ' + shapeText(r.shape) + ' here and ' + shapeText(r.other_shape) + ' in the other' });
    for (const u of cmp.unread || []) marks.set(u.array, { kind: 'unread', text: 'not read', title: u.array + ' is ' + u.dtype + ' here and ' + u.other_dtype + ' in the other; one of them is a type Tuldok does not read' });
    return { rows, marks };
  }
  /** A layer's change over its tensors compared: the norm of their differences over the norm of the other's; null when that is zero (started at zero) or not finite. */
  function layerChange(layer, cmpd) {
    const got = layer.tensors.map(t => cmpd.rows.get(t.array)).filter(Boolean);
    const marks = layer.tensors.map(t => cmpd.marks.has(t.array) ? Object.assign({ array: t.array, name: t.name }, cmpd.marks.get(t.array)) : null).filter(Boolean)
      .map(mk => Object.assign({}, mk, { text: (layer.tensors.length > 1 ? mk.name + ' ' : '') + mk.text }));
    if (!got.length) return { rel: null, none: true, marks };
    if (got.some(r => r.difference_norm == null || r.other_norm == null)) return { rel: null, nonfinite: true, marks };
    const d = Math.sqrt(got.reduce((a, r) => a + r.difference_norm * r.difference_norm, 0)), o = Math.sqrt(got.reduce((a, r) => a + r.other_norm * r.other_norm, 0));
    return { rel: o ? d / o : null, zero: !o, marks, partial: got.length < layer.tensors.length };
  }
  function changeCell(c, most) {
    const td = h('td', 'wts-chg');
    if (c.none) { td.appendChild(h('span', 'small faint', 'not compared')); td.dataset.change = 'none'; return td; }
    if (c.zero) { const s = h('span', 'wts-zero', 'from zero'); s.title = 'It started at zero, so its change has no relative size'; td.appendChild(s); td.dataset.change = 'zero'; return td; }
    if (c.rel == null) { td.appendChild(h('span', 'small faint', 'not finite')); td.dataset.change = 'nonfinite'; return td; }
    const bar = h('span', 'wts-cbar'); bar.setAttribute('aria-hidden', 'true'); const i = h('i'); i.style.width = (most > 0 ? Math.max(1, 100 * c.rel / most) : 0).toFixed(1) + '%'; bar.appendChild(i);
    td.appendChild(bar); td.appendChild(h('span', 'wts-fig', fmt(c.rel))); td.dataset.change = String(c.rel);
    td.title = 'Relative change ' + fmt(c.rel) + (c.partial ? ', over the tensors compared' : '');
    return td;
  }

  // ---- A row's distribution, when it comes on screen ---------------------------------------------------------------------
  function watch(ctx, root) {
    if (ctx.io) ctx.io.disconnect(); ctx.io = null;
    if (!root) return;
    const lazy = [];
    for (const cv of root.querySelectorAll('canvas.wts-spark')) {
      const got = summaries.get(sumKey(cv.dataset.run, cv.dataset.path, cv.dataset.array, SMALL_BINS));
      if (got) spark(cv, got); else lazy.push(cv);
    }
    if (!lazy.length) return;
    const io = ctx.io = new IntersectionObserver(entries => {
      for (const e of entries) if (e.isIntersecting && e.target.isConnected) {
        io.unobserve(e.target);
        const cv = e.target;
        summary(cv.dataset.run, cv.dataset.path, cv.dataset.array, SMALL_BINS).then(s => spark(cv, s), error => { cv.setAttribute('aria-label', 'Distribution of ' + cv.dataset.array + ': ' + (error.message || error)); cv.title = error.message || String(error); cv.classList.add('refused'); });
      }
    }, { root: ctx.scroller, rootMargin: MARGIN });
    for (const cv of lazy) io.observe(cv);
  }
  function spark(cv, s) {
    cv.dataset.drawn = '1';
    cv.setAttribute('aria-label', 'Distribution of ' + cv.dataset.array + ' in ' + s.histogram.counts.length + ' bins from ' + fmt(s.histogram.low) + ' to ' + fmt(s.histogram.high) + ', mean ' + fmt(s.mean));
    D.paints(cv, () => histogram(cv, s, 22, false));
  }
  /** Bars of a histogram in a canvas of a CSS height; a mark at zero when zero is inside the range. */
  function histogram(cv, s, cssH, axis) {
    const size = D.fit(cv, cssH); if (!size) return; const [W, H] = size, ctx = cv.getContext('2d'); ctx.clearRect(0, 0, W, H);
    const counts = s.histogram.counts, most = Math.max(1, ...counts), bw = W / Math.max(1, counts.length), ink = D.token('--mark'), line = D.token('--line-strong'), dpr = window.devicePixelRatio || 1;
    const { low, high } = s.histogram;
    if (low != null && high != null && low < 0 && high > 0) { ctx.fillStyle = 'rgb(' + D.token('--ink-3').join(',') + ')'; ctx.fillRect(Math.round((0 - low) / (high - low) * W), 0, Math.max(1, Math.round(dpr)), H); }
    ctx.fillStyle = 'rgb(' + ink.join(',') + ')';
    counts.forEach((n, i) => { if (!n) return; const bh = Math.max(Math.round(dpr), n / most * (H - 2 * dpr)); ctx.fillRect(i * bw + (bw > 3 ? 0.5 : 0), H - bh, Math.max(1, bw - (bw > 3 ? 1 : 0)), bh); });
    if (axis) { ctx.fillStyle = 'rgb(' + line.join(',') + ')'; ctx.fillRect(0, H - Math.max(1, Math.round(dpr)), W, Math.max(1, Math.round(dpr))); }
  }

  // ---- A tensor opened ---------------------------------------------------------------------------------------------------
  const viewOf = (st, f, t) => { const key = f.key + '\n' + t.array; if (!st.views.has(key)) st.views.set(key, { across: null, index: t.shape.map(n => Math.floor(n / 2)), first: 0 }); return st.views.get(key); };
  async function tensorPanel(ctx, f, layer, cmpd, choice) {
    const { st } = ctx;
    const t = layer.tensors.find(x => x.array === st.tensor) || layer.tensors[0]; st.tensor = t.array;
    const panel = h('div', 'wts-tensor'); panel.setAttribute('aria-label', 'Tensor ' + t.array);
    if (layer.tensors.length > 1) {
      const seg = h('div', 'seg wts-tensors'); seg.setAttribute('role', 'group'); seg.setAttribute('aria-label', 'Tensor of ' + layer.name);
      for (const x of layer.tensors) { const b = button(null, x.name, () => { if (st.tensor !== x.array) { st.tensor = x.array; again(ctx); } }); b.setAttribute('aria-pressed', String(x === t)); b.dataset.key = 'wts-tensor-' + x.array; b.title = x.array + ' · ' + shapeText(x.shape); seg.appendChild(b); }
      panel.appendChild(seg);
    }
    panel.appendChild(h('p', 'small muted wts-what', [t.array, t.dtype, shapeText(t.shape), plural(t.parameters, 'value')].join(' · ')));
    // When comparing: how it changed, or why it is not compared; this, the other or their difference.
    const row = cmpd ? cmpd.rows.get(t.array) : null, mark = cmpd ? cmpd.marks.get(t.array) : null;
    if (!row) st.mode = 'this';
    if (cmpd) {
      if (row) panel.appendChild(h('p', 'small wts-row-cmp', 'Against ' + choice.detail + ': relative change ' + (row.relative_change == null ? (row.other_norm === 0 ? 'from zero' : '—') : fmt(row.relative_change)) + ', cosine ' + fmt(row.cosine) + ', largest change ' + fmt(row.largest_change) + '.'));
      else panel.appendChild(h('p', 'small warnline', mark ? mark.title + ': it is not compared.' : 'Not compared.'));
      if (row) {
        const seg = h('div', 'seg wts-mode'); seg.setAttribute('role', 'group'); seg.setAttribute('aria-label', 'Show');
        for (const [key, label] of [['this', 'This'], ['other', 'The other'], ['difference', 'Difference']]) { const b = button(null, label, () => { if (st.mode !== key) { st.mode = key; again(ctx); } }); b.setAttribute('aria-pressed', String(st.mode === key)); b.dataset.key = 'wts-mode-' + key; seg.appendChild(b); }
        panel.appendChild(seg);
      }
    }
    // Its statistics and the larger distribution (of this file's tensor).
    try {
      const s = await summary(f.run, f.path, t.array, BIG_BINS);
      if (row) panel.appendChild(h('p', 'small faint', 'Statistics of this file\'s tensor'));
      const dl = h('dl', 'setup iv-facts wts-stats');
      const put = (k, text, stat, value) => { dl.appendChild(h('dt', null, k)); const dd = h('dd', 'num', text); dd.dataset.stat = stat; if (value != null) dd.dataset.value = String(value); dl.appendChild(dd); };
      put('Range', fmt(s.min) + ' to ' + fmt(s.max), 'range', JSON.stringify([s.min, s.max]));
      put('Mean', fmt(s.mean), 'mean', s.mean); put('Spread', fmt(s.std), 'std', s.std);
      put('Zeros', num(s.zeros), 'zeros', s.zeros);
      put('Values', num(s.count) + (s.stride > 1 ? ', every ' + D.ordinal(s.stride) + ' read' : ''), 'count', s.count);
      if (s.nonfinite) put('Not finite', num(s.nonfinite), 'nonfinite', s.nonfinite);
      panel.appendChild(dl);
      if (s.histogram && s.histogram.counts.length) {
        const hc = h('canvas', 'wts-hist'); hc.setAttribute('role', 'img');
        hc.setAttribute('aria-label', 'Distribution of ' + t.array + ' in ' + s.histogram.counts.length + ' bins from ' + fmt(s.histogram.low) + ' to ' + fmt(s.histogram.high));
        D.paints(hc, () => histogram(hc, s, 72, true)); panel.appendChild(hc);
        const ends = h('div', 'iv-ends small faint'); ends.appendChild(h('span', null, fmt(s.histogram.low))); ends.appendChild(h('span', null, fmt(s.histogram.high))); panel.appendChild(ends);
      }
    } catch (error) { panel.appendChild(refusal(error)); }
    // Its values as images.
    const images = h('div', 'wts-images');
    await fillImages(ctx, images, images, f, t, row ? choice : null);
    panel.appendChild(images);
    return panel;
  }

  /** The drawn axes for a tensor of three or more axes counted across one: the last two of the others. */
  const drawnFor = (nd, across) => { const others = []; for (let a = 0; a < nd; a++) if (a !== across) others.push(a); return others.slice(-2); };
  /** Reads what the images show for the mode: this, the other, or their difference (each tile by tile). */
  async function readImages(f, t, v, mode, other) {
    const nd = t.shape.length;
    const ask = (run, path) => {
      if (nd >= 3) { const args = { path, array: t.array, across: v.across, index: v.index.slice(), first: v.first, most: TILES }; return kept(JSON.stringify(['tiles', run, args]), () => R.tiles(run, args, true)); }
      const args = { path, array: t.array, most: SLICE_MOST }; return kept(JSON.stringify(['slice', run, args]), () => R.slice(run, args, true));
    };
    const here = await ask(f.run, f.path);
    if (mode === 'this') return { a: here, values: D.floats(here.values_f32) };
    const there = await ask(other.run, other.path), tv = D.floats(there.values_f32);
    if (mode === 'other') return { a: there, values: tv };
    const hv = D.floats(here.values_f32), d = new Float32Array(hv.length);
    for (let i = 0; i < d.length; i++) d[i] = hv[i] - tv[i];
    let min = Infinity, max = -Infinity, nonfinite = 0; for (const x of d) { if (!Number.isFinite(x)) { nonfinite++; continue; } if (x < min) min = x; if (x > max) max = x; }
    return { a: Object.assign({}, here, { min: Number.isFinite(min) ? min : null, max: Number.isFinite(max) ? max : null, nonfinite }), values: d };
  }
  const MODE_WORD = { this: 'this file', other: 'the other file', difference: 'this minus the other' };
  /**
   * Fills target with the controls and the images of tensor t (built in full before it returns); host is the
   * element they are shown in (target itself, or the box they will be put in place in).
   */
  async function fillImages(ctx, target, host, f, t, other) {
    const { st } = ctx, nd = t.shape.length, v = viewOf(st, f, t), mode = other ? st.mode : 'this';
    if (nd === 0) return;
    if (nd >= 3) { if (v.across == null || v.across >= nd) v.across = 0; if (v.first >= t.shape[v.across]) v.first = 0; }
    const ctl = h('div', 'iv-ctl wts-ctl');
    let sliders = [];
    if (nd >= 3) {
      const s = h('select'); s.setAttribute('aria-label', 'Axis counted across the tiles'); s.dataset.key = 'wts-across';
      for (let a = 0; a < nd; a++) { const o = h('option', null, 'axis ' + a + ' (' + t.shape[a] + ')'); o.value = String(a); o.selected = a === v.across; s.appendChild(o); }
      s.addEventListener('change', () => { v.across = Number(s.value); v.first = 0; redrawImages(ctx, host, f, t, other); });
      const l = h('label', 'iv-field'); l.appendChild(document.createTextNode('Tiles across')); l.appendChild(s); ctl.appendChild(l);
      const drawn = drawnFor(nd, v.across);
      for (let a = 0; a < nd; a++) if (a !== v.across && !drawn.includes(a)) {
        const l2 = h('label', 'iv-field iv-slider'); l2.appendChild(h('span', null, 'Axis ' + a));
        const r = h('input'); r.type = 'range'; r.min = '0'; r.max = String(t.shape[a] - 1); r.value = String(v.index[a]); r.dataset.key = 'wts-axis-slider-' + a; r.dataset.axis = String(a);
        r.setAttribute('aria-label', 'Position on axis ' + a + ', 0 to ' + (t.shape[a] - 1));
        const at = h('span', 'num small', v.index[a] + ' of ' + t.shape[a]);
        l2.appendChild(r); l2.appendChild(at); ctl.appendChild(l2); sliders.push({ a, r, at });
      }
    }
    let got;
    try { got = await readImages(f, t, v, mode, other); } catch (error) { target.replaceChildren(ctl, refusal(error)); return; }
    const pics = h('div', 'wts-pics'), legend = h('div', 'wts-legend');
    const paint = g => { drawPics(pics, legend, g, t, v, mode); };
    paint(got);
    if (nd >= 3) {
      const n = t.shape[v.across], last = v.first + got.a.tiles;
      const pg = h('div', 'pager wts-pager');
      const pb = button('btn sm', 'Previous', () => { v.first = Math.max(0, v.first - TILES); redrawImages(ctx, host, f, t, other); }); pb.disabled = v.first === 0; pb.dataset.key = 'wts-prev';
      const nb = button('btn sm', 'Next', () => { v.first += TILES; redrawImages(ctx, host, f, t, other); }); nb.disabled = last >= n; nb.dataset.key = 'wts-next';
      pg.appendChild(pb); pg.appendChild(nb); pg.appendChild(h('span', 'small muted', 'Tiles ' + (v.first + 1) + '–' + last + ' of ' + n + ' along axis ' + v.across));
      target.replaceChildren(ctl, pics, legend, pg);
      // A slider moves the tiles: read again (the latest wins), drawn again in place; the controls stay.
      let wanted = 0, timer = 0;
      for (const { a, r, at } of sliders) r.addEventListener('input', () => {
        v.index[a] = Number(r.value); at.textContent = v.index[a] + ' of ' + t.shape[a];
        clearTimeout(timer); const mine = ++wanted; host.setAttribute('aria-busy', 'true');
        timer = setTimeout(async () => {
          try { const next = await readImages(f, t, v, mode, other); if (mine !== wanted || !pics.isConnected) return; paint(next); }
          catch (error) { if (mine === wanted) legend.replaceChildren(refusal(error)); }
          if (mine === wanted) host.removeAttribute('aria-busy');
        }, 90);
      });
    } else target.replaceChildren(pics, legend);
    host.dataset.mode = mode;
  }
  /** Draws the images again for a control (an axis, a page): built off the page, put in place with the focus kept. */
  async function redrawImages(ctx, box, f, t, other) {
    const mine = box._turn = (box._turn || 0) + 1, fresh = h('div'); box.setAttribute('aria-busy', 'true');
    await fillImages(ctx, fresh, box, f, t, other);
    if (mine !== box._turn || !box.isConnected) return;
    box.removeAttribute('aria-busy');
    const frag = document.createDocumentFragment(); frag.append(...fresh.childNodes);
    putInPlace(box, frag, ctx.scroller);
  }

  /** The tiles (three or more axes) or the one image (one or two axes), on a range symmetric about zero, and the legend. */
  function drawPics(pics, legend, g, t, v, mode) {
    const a = g.a, nd = t.shape.length, m = Math.max(Math.abs(a.min || 0), Math.abs(a.max || 0)) || 1, colour = D.ramp(-m, m);
    const tiles = nd >= 3 ? a.tiles : 1, rows = a.rows, cols = a.columns, per = rows * cols;
    const where = nd >= 3 ? ' along axes ' + a.axes.join(' and ') + (a.index.some((_, i) => i !== a.across && !a.axes.includes(i)) ? ' at ' + a.index.map((p, i) => i !== a.across && !a.axes.includes(i) ? 'axis ' + i + ' = ' + p : null).filter(Boolean).join(', ') : '') : '';
    const els = [];
    for (let k = 0; k < tiles; k++) {
      const fig = h('figure', 'wts-tile'), cv = h('canvas'); cv.setAttribute('role', 'img');
      const values = g.values.subarray(k * per, (k + 1) * per);
      if (nd >= 3) cv.setAttribute('aria-label', 'Tile at axis ' + a.across + ' = ' + (a.first + k) + ' of ' + t.array + ' (' + MODE_WORD[mode] + '): ' + rows + ' by ' + cols + ' values' + where);
      else cv.setAttribute('aria-label', (nd === 1 ? 'The ' + cols + ' values' : rows + ' by ' + cols + ' values') + ' of ' + t.array + ' (' + MODE_WORD[mode] + '), from ' + fmt(a.min) + ' to ' + fmt(a.max) + (a.stride > 1 ? ', every ' + D.ordinal(a.stride) + ' row and column' : ''));
      D.paints(cv, () => {
        const w = cv.clientWidth; if (!w) return;
        const cssH = nd === 1 ? 28 : Math.max(nd >= 3 ? 24 : 32, Math.min(nd >= 3 ? w * 1.5 : 320, Math.round(w * rows / cols)));
        const size = D.fit(cv, cssH); if (!size) return; const ctx = cv.getContext('2d'); ctx.clearRect(0, 0, size[0], size[1]);
        const [x, y, ww, hh] = nd === 1 ? [0, 0, size[0], size[1]] : D.contain(rows, cols, size[0], size[1]);
        D.heat(ctx, values, rows, cols, colour, x, y, ww, hh);
      });
      fig.appendChild(cv);
      if (nd >= 3) fig.appendChild(h('figcaption', 'num', String(a.first + k)));
      els.push(fig);
    }
    pics.className = 'wts-pics' + (nd >= 3 ? ' tiles' : ' one');
    pics.dataset.mode = mode; pics.dataset.first = String(a.first || 0); pics.dataset.index = JSON.stringify(a.index || []); pics.dataset.across = String(nd >= 3 ? a.across : '');
    pics.replaceChildren(...els);
    // The legend: the ramp from -m to +m.
    const ramp = h('canvas', 'wts-ramp'); ramp.setAttribute('aria-hidden', 'true');
    D.paints(ramp, () => { const size = D.fit(ramp, 10); if (!size) return; const n = 64, vals = new Float32Array(n); for (let i = 0; i < n; i++) vals[i] = -m + 2 * m * (i + 0.5) / n; D.heat(ramp.getContext('2d'), vals, 1, n, colour, 0, 0, size[0], size[1]); });
    const ends = h('div', 'iv-ends small faint'); ends.appendChild(h('span', null, '−' + fmt(m))); ends.appendChild(h('span', null, '0')); ends.appendChild(h('span', null, '+' + fmt(m)));
    const say = h('p', 'small muted wts-range', (mode === 'difference' ? 'This minus the other' : mode === 'other' ? 'The other file' : 'This file') + ': from ' + fmt(a.min) + ' to ' + fmt(a.max) + ', coloured on ±' + fmt(m) + ' about zero' + (a.stride > 1 ? ' · every ' + D.ordinal(a.stride) + ' row and column' : '') + (a.nonfinite ? ' · ' + plural(a.nonfinite, 'value') + ' not finite, left clear' : '') + '.');
    legend.replaceChildren(ramp, ends, say);
  }

  return { block };
})();
