'use strict';
// Looking inside a product (docs/plans/definition-first-projects/spec-d1.md section 7): the Data tab's
// second state, one dataset opened (#data/inside:<reference>), and its viewers. The records are paged 48 at
// a time as tiles beside the selected record's viewer (below it under 1,100 px); a "Files" switch browses
// the product as a tree (directories, archives and the arrays of an .npy or .npz) from which a file or an
// array opens in the same viewers. Everything is read through window.TuldokProject's five operations
// (records, record, inside, array_slice, array_summary) and the file route for an image's or a sound's
// bytes; nothing is written. Drawing is Canvas 2D with the tokens of base.css, drawn again when the theme
// changes or a canvas's box changes size, and on requestAnimationFrame only while something changes.
//
// Updating in place (spec-w4): the view is built off the page and put in place in one step. A reading that
// changed nothing never reaches here (app.js draws nothing); one that changed something forgets these
// answers, and open() is called with again set: the view is read and drawn again in place, keeping the
// page, the filters, the selection, the viewer's settings and the scroll. A person's selection changes the
// tiles' pressed state and the viewer only; a page, a filter or the Files switch draws the view again.
window.LabInside = (() => {
  const P = window.TuldokProject, S = window.LabScreens, C = window.LabCharts, h = C.h;
  const { sect, putInPlace, bytes, time, failure } = S.parts;
  const PER_PAGE = 48;          // tiles on a page (spec-d1 section 7)
  const TILE_MOST = 48;         // rows and columns of an array tile's slice
  const VIEW_MOST = 256;        // rows and columns of the viewer's slice
  const STACK_MOST = 24, STACK_SLICES = 10;   // the stacked-slice drawing: slices read, and their size
  const MESH_AS_POINTS = 60000; // above this many triangles a mesh is drawn as its vertices
  const TREE_LIMIT = 200;       // entries of the Files tree read at a time
  const KINDS = ['text', 'image', 'audio', 'pointcloud', 'mesh', 'array', 'file'];
  const WORD = { text: 'Text', image: 'Image', audio: 'Sound', pointcloud: 'Point cloud', mesh: 'Mesh', array: 'Array', file: 'File' };
  const count = (n, one, many) => n.toLocaleString('en-GB') + ' ' + (n === 1 ? one : many || one + 's');
  const button = (cls, text, onClick) => { const b = h('button', cls, text); b.type = 'button'; if (onClick) b.addEventListener('click', onClick); return b; };
  const fmt = v => v == null ? '—' : C.fmtSci(v);

  // ---- Decoding -------------------------------------------------------------------------------------------
  function raw(b64) { const s = atob(b64 || ''), u = new Uint8Array(s.length); for (let i = 0; i < s.length; i++) u[i] = s.charCodeAt(i); return u; }
  /** Little-endian 32-bit floats from base64, whatever the machine's byte order. */
  function floats(b64) { const u = raw(b64), d = new DataView(u.buffer), out = new Float32Array(u.length >> 2); for (let i = 0; i < out.length; i++) out[i] = d.getFloat32(i * 4, true); return out; }
  function uints(b64) { const u = raw(b64), d = new DataView(u.buffer), out = new Uint32Array(u.length >> 2); for (let i = 0; i < out.length; i++) out[i] = d.getUint32(i * 4, true); return out; }

  // ---- Colours, from the tokens of base.css -----------------------------------------------------------------
  function token(name) {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    const m = /^#([0-9a-f]{6})$/i.exec(v); if (m) { const n = parseInt(m[1], 16); return [n >> 16, (n >> 8) & 255, n & 255]; }
    return [128, 128, 128];
  }
  const mix = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
  /** value -> [r, g, b]: diverging about zero when the range has both signs, else sequential from low to high. */
  function ramp(min, max) {
    const lo = token('--ramp-lo'), hi = token('--ramp-hi'), neg = token('--ramp-neg'), mid = token('--ramp-mid'), pos = token('--ramp-pos');
    if (min < 0 && max > 0) { const m = Math.max(-min, max); return v => v < 0 ? mix(mid, neg, Math.min(1, -v / m)) : mix(mid, pos, Math.min(1, v / m)); }
    const span = max - min || 1; return v => mix(lo, hi, Math.min(1, Math.max(0, (v - min) / span)));
  }

  // ---- Canvases: sized to their box, drawn again on a new size or theme -------------------------------------
  const painters = new Map();   // canvas -> draw()
  const sizes = new ResizeObserver(entries => { for (const e of entries) { const draw = painters.get(e.target); if (draw && e.target.isConnected) { e.target._shown = true; draw(); } } });
  /** Registers draw(canvas) for a canvas: it is called when the canvas's box gets a size, changes size, or the theme changes. */
  function paints(canvas, draw) { prune(); painters.set(canvas, draw); sizes.observe(canvas); }
  /** Forgets the canvases that were on the page and are no more (a viewer replaced, the view left), and what they drew from. */
  function prune() { for (const canvas of painters.keys()) if (canvas._shown && !canvas.isConnected) { painters.delete(canvas); sizes.unobserve(canvas); } }
  function retheme() { prune(); for (const [canvas, draw] of painters) if (canvas.isConnected) draw(); }
  new MutationObserver(retheme).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  matchMedia('(prefers-color-scheme: dark)').addEventListener('change', retheme);
  /** Sets a canvas's pixel size for its CSS width and a height (CSS pixels); returns [width, height] in device pixels or null when it has no width yet. */
  function fit(canvas, cssHeight) {
    const w = canvas.clientWidth; if (!w) return null;
    const dpr = window.devicePixelRatio || 1, W = Math.max(1, Math.round(w * dpr)), H = Math.max(1, Math.round(cssHeight * dpr));
    if (canvas.style.height !== cssHeight + 'px') canvas.style.height = cssHeight + 'px';
    if (canvas.width !== W) canvas.width = W; if (canvas.height !== H) canvas.height = H;
    return [W, H];
  }
  /** A heat map of rows x columns values into ctx's rectangle (x, y, w, h), unsmoothed; non-finite values left clear. */
  function heat(ctx, values, rows, cols, colour, x, y, w, hgt) {
    const off = document.createElement('canvas'); off.width = cols; off.height = rows;
    const o = off.getContext('2d'), img = o.createImageData(cols, rows);
    for (let i = 0; i < rows * cols; i++) { const v = values[i]; if (!Number.isFinite(v)) continue; const c = colour(v); img.data[i * 4] = c[0]; img.data[i * 4 + 1] = c[1]; img.data[i * 4 + 2] = c[2]; img.data[i * 4 + 3] = 255; }
    o.putImageData(img, 0, 0); ctx.imageSmoothingEnabled = false; ctx.drawImage(off, x, y, w, hgt);
  }
  /** The rectangle a rows x columns grid takes in W x H, keeping square cells. */
  function contain(rows, cols, W, H) { const s = Math.min(W / cols, H / rows), w = cols * s, hh = rows * s; return [(W - w) / 2, (H - hh) / 2, w, hh]; }

  // ---- Glyphs ---------------------------------------------------------------------------------------------
  const GLYPHS = {
    text: 'M5 6h14M5 10h14M5 14h10M5 18h12',
    image: 'M4 5h16v14H4zM4 16l5-5 4 4 3-3 4 4M15 9.5a1 1 0 1 0 0 .1',
    audio: 'M3 12h2M7 8v8M11 4v16M15 7v10M19 10v4',
    pointcloud: 'M6 7h.01M10 5h.01M15 6h.01M18 10h.01M8 11h.01M13 10h.01M5 15h.01M11 15h.01M16 14h.01M9 19h.01M14 18h.01M19 17h.01',
    mesh: 'M12 3 3 19h18zM12 3l-3 9 12 7M9 12 3 19',
    array: 'M4 4h16v16H4zM4 9.3h16M4 14.6h16M9.3 4v16M14.6 4v16',
    file: 'M6 3h8l4 4v14H6zM14 3v4h4',
    directory: 'M3 6h6l2 2h10v11H3z',
    archive: 'M5 4h14v16H5zM11 4v2h2v2h-2v2h2v2h-2v2',
    refused: 'M12 3 2 21h20zM12 10v5M12 18h.01'
  };
  function glyph(name) {
    const ns = 'http://www.w3.org/2000/svg', s = document.createElementNS(ns, 'svg'), p = document.createElementNS(ns, 'path');
    s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('aria-hidden', 'true'); s.setAttribute('class', 'glyph ' + name);
    p.setAttribute('d', GLYPHS[name] || GLYPHS.file); p.setAttribute('fill', 'none'); p.setAttribute('stroke', 'currentColor'); p.setAttribute('stroke-width', name === 'pointcloud' ? '2.6' : '1.6'); p.setAttribute('stroke-linecap', 'round'); p.setAttribute('stroke-linejoin', 'round');
    s.appendChild(p); return s;
  }

  // ---- What is kept per dataset, across drawings ---------------------------------------------------------------
  const views = new Map();   // reference -> the person's place in it
  const viewOf = ref => { if (!views.has(ref)) views.set(ref, { run: null, page: 0, kind: null, split: null, sel: null, mode: 'records', path: '', treeOffset: 0, treeTarget: null, viewers: new Map() }); return views.get(ref); };
  const settingsOf = (v, key, make) => { if (!v.viewers.has(key)) v.viewers.set(key, make()); return v.viewers.get(key); };
  let current = null;   // { ref, main, act, root, io, vturn }
  const R = P.product;   // the five reads and the file route (adapter.js)

  /**
   * Shows the dataset ref opened in main. What is on screen for it stays unless again (a reading changed
   * something): then it is read and drawn again in place. "Reading…" only when it is not on screen yet.
   */
  function open(main, ref, act, again) {
    const shown = !!(current && current.ref === ref && current.root && main.contains(current.root));
    if (shown && !again) { current.act = act; return; }
    if (!current || current.ref !== ref) { leave(); current = { ref, main, act, root: null, io: null, vturn: 0, focusSel: false }; }
    current.act = act;
    draw(current, !shown);
  }
  /** The dataset view is no longer shown: its tile observer stops. */
  function leave() { if (current && current.io) current.io.disconnect(); current = null; }
  /** Whether the page still shows this dataset opened (another tab may have been drawn meanwhile). */
  const here = c => current === c && decodeURIComponent(location.hash.slice(1)) === 'data/inside:' + c.ref;

  /** Reads what the view shows: the dataset, its products, a page of records or a level of the tree, and the viewer's subject. */
  async function load(c, v) {
    const [defs, prods] = await Promise.all([P.read('definitions', { kind: 'dataset' }), P.read('products', { reference: c.ref })]);
    const def = defs.definitions.find(d => d.reference === c.ref) || { reference: c.ref, title: c.ref };
    const products = prods.products.filter(p => p.run_id);
    if (!products.length) return { def, products };
    const product = products.find(p => p.run_id === v.run) || products[0]; v.run = product.run_id;
    const args = { offset: v.page * PER_PAGE, limit: PER_PAGE, kind: v.kind, split: v.split };
    let page = await R.records(v.run, args);
    if (!page.records.length && v.page > 0 && page.total) { v.page = Math.floor((page.total - 1) / PER_PAGE); args.offset = v.page * PER_PAGE; page = await R.records(v.run, args); }
    let tree = null;
    if (v.mode === 'files') tree = await R.inside(v.run, { path: v.path, offset: v.treeOffset, limit: TREE_LIMIT }).catch(error => ({ error }));
    if (v.mode === 'records' && !page.records.some(r => r.id === v.sel)) v.sel = page.records.length ? page.records[v.selAt === -1 ? page.records.length - 1 : 0].id : null;
    v.selAt = 0;
    const target = v.mode === 'files' ? v.treeTarget : v.sel ? { record: v.sel } : null;
    const viewer = target ? await viewerFor(c, v, target) : null;
    return { def, products, product, page, tree, viewer };
  }

  /** Draws the whole view (first: not on screen yet), built off the page and put in place in one step. */
  async function draw(c, first) {
    const main = c.main, mine = main._paint = (main._paint || 0) + 1, v = viewOf(c.ref);
    if (first) { main.textContent = ''; main.appendChild(h('p', 'note', 'Reading…')); main.scrollTop = 0; main.scrollLeft = 0; }
    main._painted = 'data/inside:' + c.ref;   // so that the cards, drawn again later, start from "Reading…" (tabs.js's paint)
    main.setAttribute('aria-busy', 'true');
    let got; try { got = await load(c, v); } catch (error) { got = { error }; }
    if (main._paint === mine) main.removeAttribute('aria-busy');
    if (main._paint !== mine || !here(c)) return;
    const root = h('div', 'inside');
    try { build(c, v, got, root); } catch (error) { root.textContent = ''; failure(root, error); console.error(error); }
    if (c.io) c.io.disconnect();
    putInPlace(main, root);
    c.root = root;
    if (c.focusSel) { c.focusSel = false; const t = root.querySelector('.rec[aria-pressed="true"]'); if (t) t.focus(); }
    watchTiles(c, root);
  }

  function build(c, v, got, root) {
    const back = button('btn sm ghost ds-back', '← All datasets', () => c.act.go('data')); back.dataset.key = 'inside-back'; root.appendChild(back);
    if (got.error) { root.appendChild(window.LabActions.refusal(got.error)); return; }
    const { def, products, product, page, tree } = got;
    const head = h('div', 'ds-head'); head.appendChild(h('h2', null, def.title));
    const meta = h('div', 'meta');
    if (product) {
      meta.appendChild(h('span', 'mono', 'run ' + product.run_id.slice(0, 8)));
      meta.appendChild(h('span', null, (product.adopted ? 'adopted ' : 'built ') + time(product.finished_at)));
      meta.appendChild(h('span', null, bytes(product.bytes)));
      if (page) meta.appendChild(h('span', null, count(Object.values(page.kinds).reduce((a, b) => a + b, 0), 'record') + ' · ' + ({ 'records.jsonl': 'from records.jsonl', view: 'from the dataset\'s view', files: 'one per file' }[page.source] || page.source)));
    }
    head.appendChild(meta);
    if (products.length > 1) {
      const s = h('select'); s.setAttribute('aria-label', 'Product'); s.dataset.key = 'inside-product';
      for (const p of products) { const o = h('option', null, (p.subject ? p.subject + ' · ' : '') + 'run ' + p.run_id.slice(0, 8) + ' · ' + time(p.finished_at)); o.value = p.run_id; o.selected = p.run_id === v.run; s.appendChild(o); }
      s.addEventListener('change', () => { Object.assign(v, { run: s.value, page: 0, sel: null, path: '', treeOffset: 0, treeTarget: null }); draw(c, false); });
      head.appendChild(s);
    }
    root.appendChild(head);
    if (!product) { root.appendChild(h('p', 'empty', 'This dataset has no product on this machine: there is nothing to look inside.')); return; }
    if (page.problems && page.problems.length) {
      const p = h('p', 'small warnline inside-problems', page.problems.slice(0, 3).map(x => (x.line != null ? 'Line ' + x.line + ': ' : '') + x.message).join(' ') + (page.problems.length > 3 ? ' (' + page.problems.length + ' problems in all)' : ''));
      root.appendChild(p);
    }
    // The Files switch, the kinds and the splits as filters.
    const bar = h('div', 'filters');
    const seg = h('div', 'seg'); seg.setAttribute('role', 'group'); seg.setAttribute('aria-label', 'Show');
    for (const [mode, label] of [['records', 'Records'], ['files', 'Files']]) { const b = button(null, label, () => { if (v.mode !== mode) { v.mode = mode; draw(c, false); } }); b.setAttribute('aria-pressed', String(v.mode === mode)); b.dataset.key = 'inside-mode-' + mode; seg.appendChild(b); }
    bar.appendChild(seg);
    if (v.mode === 'records') {
      const all = Object.values(page.kinds).reduce((a, b) => a + b, 0);
      bar.appendChild(chips('Kind', [[null, 'All', all]].concat(KINDS.filter(k => page.kinds[k]).map(k => [k, WORD[k], page.kinds[k]])), v.kind, k => { v.kind = k; v.page = 0; v.sel = null; draw(c, false); }, 'kind'));
      const splits = Object.entries(page.splits || {});
      if (splits.length) bar.appendChild(chips('Split', [[null, 'All', null]].concat(splits.map(([s, n]) => [s, s, n])), v.split, s => { v.split = s; v.page = 0; v.sel = null; draw(c, false); }, 'split'));
    }
    root.appendChild(bar);
    const body = h('div', 'ds-body');
    const left = h('div', 'inside-list');
    if (v.mode === 'records') records(c, v, page, left); else files(c, v, tree, left);
    body.appendChild(left);
    const panel = h('section', 'viewer'); panel.setAttribute('aria-label', 'Viewer');
    panel.appendChild(got.viewer || h('p', 'empty', v.mode === 'files' ? 'Choose a file or an array in the tree.' : 'Choose a record.'));
    body.appendChild(panel); root.appendChild(body);
  }
  function chips(label, items, value, pick, key) {
    const g = h('div', 'grp'); g.setAttribute('role', 'group'); g.setAttribute('aria-label', label);
    for (const [id, text, n] of items) { const b = button('btn sm', text + (n != null ? ' · ' + n.toLocaleString('en-GB') : ''), () => { if (value !== id) pick(id); }); b.setAttribute('aria-pressed', String(value === id)); b.dataset.key = 'inside-' + key + '-' + (id || 'all'); g.appendChild(b); }
    return g;
  }

  // ---- The records: a page of tiles ------------------------------------------------------------------------
  function records(c, v, page, left) {
    const first = v.page * PER_PAGE + 1, last = v.page * PER_PAGE + page.records.length;
    left.appendChild(sect('Records', page.total ? first.toLocaleString('en-GB') + '–' + last.toLocaleString('en-GB') + ' of ' + page.total.toLocaleString('en-GB') : '0'));
    if (!page.total) { left.appendChild(h('p', 'empty', v.kind || v.split ? 'No record matches the filters.' : 'This product holds no records.')); return; }
    const grid = h('div', 'rec-grid'); grid.setAttribute('role', 'group'); grid.setAttribute('aria-label', 'Records ' + first + ' to ' + last + ' of ' + page.total + '; the left and right arrows move the selection');
    for (const r of page.records) grid.appendChild(tile(c, v, r));
    left.appendChild(grid);
    const pages = Math.ceil(page.total / PER_PAGE);
    if (pages > 1) {
      const pg = h('div', 'pager');
      const pb = button('btn sm', 'Previous', () => turnPage(c, v, v.page - 1, 0)); pb.disabled = v.page === 0; pb.dataset.key = 'inside-prev';
      const nb = button('btn sm', 'Next', () => turnPage(c, v, v.page + 1, 0)); nb.disabled = v.page + 1 >= pages; nb.dataset.key = 'inside-next';
      pg.appendChild(pb); pg.appendChild(nb); pg.appendChild(h('span', null, 'page ' + (v.page + 1) + ' of ' + pages)); left.appendChild(pg);
    }
    left._records = page.records; left._pages = pages;
  }
  function turnPage(c, v, n, at) { v.page = n; v.sel = null; v.selAt = at; draw(c, false); }
  /** One record as a tile: its id always; text's first characters; an image or a small array slice once the tile is seen; else the kind's glyph. */
  function tile(c, v, r) {
    const b = h('button', 'rec ' + r.kind); b.type = 'button'; b.dataset.id = r.id; b.dataset.key = 'rec-' + r.id; b.dataset.kind = r.kind;
    b.setAttribute('aria-pressed', String(r.id === v.sel)); b.setAttribute('aria-label', WORD[r.kind] + ' ' + r.id); b.title = r.id;
    const th = h('span', 'th');
    if (r.kind === 'text' && r.preview != null) th.appendChild(h('span', 'pre', r.preview.slice(0, 160)));
    else th.appendChild(glyph(r.kind));
    if (r.kind === 'image' || r.kind === 'array') b.dataset.lazy = '1';
    const label = h('span', 'id'); label.appendChild(h('bdi', null, r.id)); b.appendChild(th); b.appendChild(label);   // cut at its start when long: the name shows
    b.addEventListener('click', () => select(c, v, r.id));
    return b;
  }
  /** Fills a tile's picture when it comes into view: the image by its url, an array by a small slice of the array shown first. */
  function watchTiles(c, root) {
    const lazy = root.querySelectorAll('.rec[data-lazy]'); if (!lazy.length) return;
    c.io = new IntersectionObserver(entries => { for (const e of entries) if (e.isIntersecting) { c.io.unobserve(e.target); fillTile(c, e.target); } }, { root: c.main, rootMargin: '120px 0px' });
    for (const t of lazy) c.io.observe(t);
  }
  async function fillTile(c, t) {
    const v = viewOf(c.ref), run = v.run, id = t.dataset.id, th = t.querySelector('.th'), kind = t.dataset.kind;
    const live = () => t.isConnected && current === c && viewOf(c.ref).run === run;
    try {
      const rec = await R.record(run, id); if (!live()) return;
      if (kind === 'image') {
        const img = h('img'); img.alt = ''; img.decoding = 'async'; img.src = rec.record.url;
        await new Promise(resolve => { img.onload = img.onerror = resolve; }); if (!live()) return;
        if (!img.naturalWidth) throw Error('The image could not be decoded.');
        th.replaceChildren(img);
      } else {
        const arrays = rec.content.arrays || [], name = rec.content.show, a = arrays.find(x => x.array === name) || arrays[0];
        if (!a) throw Error('No array.');
        const s = await R.slice(run, { path: rec.record.path, array: a.array, most: TILE_MOST }); if (!live()) return;
        const cv = h('canvas'); cv.setAttribute('aria-hidden', 'true');
        const values = floats(s.values_f32);
        paints(cv, () => { const size = fit(cv, cv.clientWidth); if (!size) return; const ctx = cv.getContext('2d'); ctx.clearRect(0, 0, size[0], size[1]); if (s.rows === 1 && s.columns > 1) line(ctx, values, s.min, s.max, 0, 0, size[0], size[1], 2); else { const [x, y, w, hh] = contain(s.rows, s.columns, size[0], size[1]); heat(ctx, values, s.rows, s.columns, ramp(s.min, s.max), x, y, w, hh); } });
        th.replaceChildren(cv);
      }
    } catch (error) {
      if (!live()) return;
      th.replaceChildren(glyph('refused')); t.title = id + ': ' + (error.message || error); t.classList.add('refused');
    }
  }
  /** Selects a record: the tiles' pressed state is set in place and the viewer replaced once its new content is read. */
  async function select(c, v, id) {
    if (!c.root) return;
    v.sel = id;
    for (const t of c.root.querySelectorAll('.rec')) { const on = String(t.dataset.id === id); if (t.getAttribute('aria-pressed') !== on) t.setAttribute('aria-pressed', on); }
    await showIn(c, v, { record: id });
  }
  async function showIn(c, v, target) {
    const panel = c.root && c.root.querySelector('.viewer'); if (!panel) return;
    const mine = ++c.vturn;
    panel.setAttribute('aria-busy', 'true');
    const slow = setTimeout(() => { if (c.vturn === mine) panel.replaceChildren(h('p', 'note', 'Reading…')); }, 250);
    const el = await viewerFor(c, v, target);
    clearTimeout(slow);
    if (c.vturn !== mine || !panel.isConnected) return;
    panel.removeAttribute('aria-busy');
    putInPlace(panel, el);
  }
  /** Left and right arrows move the selection in the grid, across pages, when the focus is not in a field or a viewer that turns. */
  function onKey(e) {
    if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey || (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight')) return;
    const c = current; if (!c || !c.root || !c.root.isConnected) return;
    const v = viewOf(c.ref); if (v.mode !== 'records') return;
    const t = e.target; if (t && t.closest && (t.closest('input, select, textarea, [contenteditable], audio, .turns') )) return;
    const list = c.root.querySelector('.inside-list'), recs = list && list._records; if (!recs || !recs.length) return;
    e.preventDefault();
    const i = recs.findIndex(r => r.id === v.sel), d = e.key === 'ArrowRight' ? 1 : -1, n = i + d;
    const onTile = !!(t && t.classList && t.classList.contains('rec'));
    if (n >= 0 && n < recs.length) { select(c, v, recs[n].id); if (onTile) { const next = c.root.querySelector('.rec[data-id="' + CSS.escape(recs[n].id) + '"]'); if (next) next.focus(); } return; }
    c.focusSel = onTile;
    if (n >= recs.length && v.page + 1 < list._pages) turnPage(c, v, v.page + 1, 0);
    else if (n < 0 && v.page > 0) turnPage(c, v, v.page - 1, -1);
    else c.focusSel = false;
  }
  window.addEventListener('keydown', onKey);

  // ---- Files: the product as a tree ------------------------------------------------------------------------
  function files(c, v, tree, left) {
    // The way down, each step a link back up.
    const crumbs = h('nav', 'crumbs'); crumbs.setAttribute('aria-label', 'Where in the product');
    const parts = v.path ? v.path.split(/(?<=!)|\//).filter(Boolean) : [];
    const steps = [['', 'Product']]; let at = '';
    for (const p of parts) { at = at ? (at.endsWith('!') ? at + p : at + '/' + p) : p; steps.push([at.replace(/!$/, ''), p.replace(/!$/, '')]); }
    steps.forEach(([path, name], i) => {
      if (i) crumbs.appendChild(h('span', 'sep', '/'));
      if (i === steps.length - 1) { const s = h('span', 'here', name); s.setAttribute('aria-current', 'location'); crumbs.appendChild(s); }
      else { const b = button('linkish', name, () => go(c, v, path)); b.dataset.key = 'crumb-' + path; crumbs.appendChild(b); }
    });
    left.appendChild(sect('Files', tree && !tree.error ? count(tree.total, 'entry', 'entries') : ''));
    left.appendChild(crumbs);
    if (!tree) return;
    if (tree.error) { left.appendChild(window.LabActions.refusal(tree.error)); return; }
    if (!tree.entries.length) { left.appendChild(h('p', 'empty', 'Nothing here.')); return; }
    const ul = h('ul', 'rows tree-rows');
    for (const e of tree.entries) {
      const li = h('li'), into = e.type === 'directory' || e.type === 'archive';
      const key = e.type === 'array' ? e.path + '#' + e.array : e.path;
      const b = button('row tree-entry'); b.dataset.key = 'entry-' + key; b.dataset.path = e.path; b.dataset.type = e.type; if (e.array) b.dataset.array = e.array;
      const t = v.treeTarget; if (!into) b.setAttribute('aria-pressed', String(!!t && t.path === e.path && (t.array || null) === (e.array || null)));
      b.appendChild(glyph(e.type === 'directory' ? 'directory' : e.type === 'archive' ? 'archive' : e.kind || 'file'));
      const name = h('span'); name.appendChild(h('span', 'title', e.type === 'array' ? e.array || '(the array)' : e.name));
      const what = e.type === 'array' ? e.dtype + ' · ' + e.shape.join(' × ') : e.type === 'directory' ? 'directory' : e.type === 'archive' ? 'archive' + (e.kind ? ' of ' + e.kind + 's' : '') : (WORD[e.kind] || 'File').toLowerCase();
      name.appendChild(h('span', 'sub', what)); b.appendChild(name);
      b.appendChild(h('span', 'sub num', e.bytes == null ? '' : bytes(e.bytes)));
      b.addEventListener('click', () => {
        if (into || (e.type === 'file' && e.kind === 'array')) { go(c, v, e.path); return; }
        const siblings = e.type === 'array' ? tree.entries.filter(x => x.type === 'array') : null;
        v.treeTarget = { path: e.path, array: e.array || null, kind: e.type === 'array' ? 'array' : e.kind || 'file', name: e.name, arrays: siblings };
        for (const x of left.querySelectorAll('.tree-entry[aria-pressed]')) { const on = String(x === b); if (x.getAttribute('aria-pressed') !== on) x.setAttribute('aria-pressed', on); }
        showIn(c, v, v.treeTarget);
      });
      li.appendChild(b); ul.appendChild(li);
    }
    left.appendChild(ul);
    if (tree.total > tree.entries.length) {
      const pg = h('div', 'pager');
      const pb = button('btn sm', 'Previous', () => { v.treeOffset = Math.max(0, v.treeOffset - TREE_LIMIT); draw(c, false); }); pb.disabled = v.treeOffset === 0; pb.dataset.key = 'tree-prev';
      const nb = button('btn sm', 'Next', () => { v.treeOffset += TREE_LIMIT; draw(c, false); }); nb.disabled = v.treeOffset + tree.entries.length >= tree.total; nb.dataset.key = 'tree-next';
      pg.appendChild(pb); pg.appendChild(nb); pg.appendChild(h('span', null, (v.treeOffset + 1) + '–' + (v.treeOffset + tree.entries.length) + ' of ' + tree.total)); left.appendChild(pg);
    }
  }
  function go(c, v, path) { v.path = path; v.treeOffset = 0; draw(c, false); }

  // ---- The viewers ---------------------------------------------------------------------------------------------
  /**
   * The viewer of a target, read in full before it is returned: {record: id}, or a place in the tree
   * {path, array, kind, arrays}. A refusal is shown as the server's sentence.
   */
  async function viewerFor(c, v, target) {
    const run = v.run, el = h('div', 'iv');
    try {
      if (target.record != null) await recordView(c, v, el, await R.record(run, target.record));
      else await placeView(c, v, el, target);
    } catch (error) {
      el.replaceChildren(heading(target.record != null ? target.record : target.path + (target.array ? ' · ' + target.array : ''), null));
      el.appendChild(window.LabActions.refusal(error));
    }
    return el;
  }
  function heading(id, line) { const hd = h('header', 'iv-head'); hd.appendChild(h('h3', 'mono', id)); if (line) hd.appendChild(h('p', 'small muted', line)); return hd; }
  async function recordView(c, v, el, got) {
    const r = got.record, k = got.content || {};
    el.appendChild(heading(r.id, [WORD[r.kind], bytes(r.bytes), r.path && r.path !== r.id ? r.path : null].filter(Boolean).join(' · ')));
    const key = 'rec:' + r.id;
    if (r.kind === 'text') textView(el, k);
    else if (r.kind === 'image') imageView(el, r.url, k.width, k.height, r.id, settingsOf(v, key, () => ({ actual: false })));
    else if (r.kind === 'audio') audioView(el, r.url, k, r.id);
    else if (r.kind === 'pointcloud') cloudView(el, k, settingsOf(v, key, turned));
    else if (r.kind === 'mesh') meshView(el, k, settingsOf(v, key, turned));
    else if (r.kind === 'array') await arrayView(el, v.run, r.path, k.arrays || [], k.show, settingsOf(v, key, () => ({})));
    else el.appendChild(h('p', 'note', 'A file of no kind Tuldok shows: it is listed, never opened.'));
    const facts = h('dl', 'setup iv-facts');
    const put = (name, value) => { if (value == null || value === '') return; facts.appendChild(h('dt', null, name)); facts.appendChild(h('dd', typeof value === 'string' ? null : 'mono pre', typeof value === 'string' ? value : JSON.stringify(value, null, 1))); };
    put('Split', r.split); put('Rights', r.rights); put('Origin', r.origin); put('Meta', r.meta);
    if (facts.children.length) el.appendChild(facts);
  }
  /** A place in the tree that is not a record: an array by its path, an image or a sound by the file route; other kinds only as a record. */
  async function placeView(c, v, el, t) {
    if (t.kind === 'array') { el.appendChild(heading(t.path, 'Array')); await arrayView(el, v.run, t.path, t.arrays || [], t.array, settingsOf(v, 'path:' + t.path + '#' + t.array, () => ({}))); return; }
    if (!t.path.includes('!')) {
      try { await recordView(c, v, el, await R.record(v.run, t.path)); return; } catch (error) { if (error.code !== 'not-found') throw error; el.replaceChildren(); }
    }
    el.appendChild(heading(t.path, WORD[t.kind] || 'File'));
    if (t.kind === 'image') imageView(el, R.fileUrl(v.run, t.path), null, null, t.path, settingsOf(v, 'path:' + t.path, () => ({ actual: false })));
    else if (t.kind === 'audio') audioView(el, R.fileUrl(v.run, t.path), null, t.path);
    else el.appendChild(h('p', 'note', 'Not one of the product\'s records: Tuldok reads arrays, images and sounds by their place, and other kinds only as records.'));
  }
  function textView(el, k) {
    const line = [count(k.characters != null ? k.characters : k.text.length, 'character'), k.truncated ? 'truncated: the first ' + k.text.length.toLocaleString('en-GB') + ' are shown' : null, k.replaced ? count(k.replaced, 'byte') + ' not UTF-8, shown as �' : null].filter(Boolean).join(' · ');
    el.appendChild(h('p', 'small muted', line));
    const pre = h('pre', 'iv-text'); pre.textContent = k.text; pre.tabIndex = 0; pre.setAttribute('aria-label', 'The text'); el.appendChild(pre);
  }
  function imageView(el, url, width, height, id, st) {
    const b = h('button', 'iv-img'); b.type = 'button'; b.dataset.key = 'iv-img'; b.setAttribute('aria-pressed', String(!!st.actual));
    const img = h('img'); img.src = url; img.alt = 'Image ' + id + (width && height ? ', ' + width + ' by ' + height + ' pixels' : '');
    b.appendChild(img);
    const size = h('p', 'small muted');
    const say = () => { const w = width || img.naturalWidth, hh = height || img.naturalHeight; size.textContent = (w && hh ? w + ' × ' + hh + ' pixels' : img.complete ? 'size not found' : 'size known once it loads') + ' · ' + (st.actual ? 'actual size; press for fitted' : 'fitted; press for actual size'); b.classList.toggle('actual', !!st.actual); b.setAttribute('aria-pressed', String(!!st.actual)); b.setAttribute('aria-label', 'Image ' + id + ', ' + (st.actual ? 'at actual size' : 'fitted to the panel') + '; press to toggle'); };
    img.addEventListener('load', () => { if (!width) say(); }, { once: true });
    img.addEventListener('error', () => { size.textContent = 'The image could not be shown.'; }, { once: true });
    b.addEventListener('click', () => { st.actual = !st.actual; say(); });
    say(); el.appendChild(size); const box = h('div', 'iv-imgbox'); box.appendChild(b); el.appendChild(box);
  }
  function audioView(el, url, k, id) {
    const has = k && k.seconds != null;
    el.appendChild(h('p', 'small muted', has ? [k.seconds.toFixed(k.seconds < 10 ? 2 : 1) + ' s', k.rate.toLocaleString('en-GB') + ' Hz', count(k.channels, 'channel'), count(k.frames, 'frame')].join(' · ') : 'Length, rate and channels are read from a WAV only; the player reads the rest.'));
    if (has && k.peaks && k.peaks.length) {
      const cv = h('canvas', 'iv-wave'); cv.setAttribute('role', 'img'); cv.setAttribute('aria-label', 'Waveform of ' + id + ', ' + k.seconds.toFixed(2) + ' seconds');
      paints(cv, () => { const size = fit(cv, 96); if (!size) return; const ctx = cv.getContext('2d'); ctx.clearRect(0, 0, size[0], size[1]); wave(ctx, size[0], size[1], k.peaks); });
      el.appendChild(cv);
    }
    const a = h('audio'); a.controls = true; a.preload = 'metadata'; a.src = url; a.dataset.key = 'iv-audio'; a.setAttribute('aria-label', 'Play ' + id); el.appendChild(a);
  }

  /** A sound's waveform from its peaks ([low, high] per bucket, -1 to 1) across a W by H canvas: the axis, then a bar per column. */
  function wave(ctx, W, H, peaks) {
    const ink = token('--mark'), axis = token('--line-strong'), n = peaks.length;
    ctx.fillStyle = 'rgb(' + axis.join(',') + ')'; ctx.fillRect(0, Math.floor(H / 2), W, 1);
    ctx.fillStyle = 'rgb(' + ink.join(',') + ')';
    for (let x = 0; x < W; x++) {
      const a = Math.floor(x / W * n), b = Math.max(a + 1, Math.floor((x + 1) / W * n)); let lo = 1, hi = -1;
      for (let i = a; i < b && i < n; i++) { lo = Math.min(lo, peaks[i][0]); hi = Math.max(hi, peaks[i][1]); }
      if (hi < lo) continue; const y0 = (1 - hi) / 2 * (H - 2) + 1, y1 = (1 - lo) / 2 * (H - 2) + 1; ctx.fillRect(x, y0, 1, Math.max(1, y1 - y0));
    }
  }

  // ---- Point clouds and meshes: turned by dragging, zoomed by the wheel ----------------------------------------------
  const turned = () => ({ yaw: -0.6, pitch: 0.45, zoom: 1 });
  function cloudView(el, k, st) {
    const pts = floats(k.points_f32), colours = k.colors_u8 ? raw(k.colors_u8) : null;
    el.appendChild(h('p', 'small muted', count(k.count, 'point') + (k.stride > 1 ? ' · every ' + ordinal(k.stride) + ' shown (' + count(pts.length / 3, 'point') + ')' : '') + ' · ' + (colours ? 'their own colours' : 'coloured by height')));
    space(el, { points: pts, colours, bounds: k.bounds }, st, 'Point cloud, ' + count(pts.length / 3, 'point') + (k.stride > 1 ? ' of ' + k.count.toLocaleString('en-GB') : ''));
  }
  function meshView(el, k, st) {
    const pos = floats(k.positions_f32), asPoints = k.triangles > MESH_AS_POINTS;
    el.appendChild(h('p', 'small muted', count(k.vertices, 'vertex', 'vertices') + ' · ' + count(k.triangles, 'triangle') + (asPoints ? ' · above ' + MESH_AS_POINTS.toLocaleString('en-GB') + ' triangles the vertices are drawn as points' : ' · flat shaded')));
    if (asPoints) space(el, { points: pos, colours: null, bounds: k.bounds }, st, 'Mesh of ' + count(k.triangles, 'triangle') + ', drawn as its ' + count(k.vertices, 'vertex', 'vertices') + ' as points');
    else space(el, { points: pos, triangles: uints(k.triangles_u32), bounds: k.bounds }, st, 'Mesh, ' + count(k.vertices, 'vertex', 'vertices') + ' and ' + count(k.triangles, 'triangle') + ', flat shaded');
  }
  const ordinal = n => n + (n % 100 >= 11 && n % 100 <= 13 ? 'th' : ['th', 'st', 'nd', 'rd'][n % 10] || 'th');
  /** A canvas showing points or triangles in 3-D; z is up. Drawn on requestAnimationFrame only after a change. */
  function space(el, m, st, label) {
    const cv = h('canvas', 'iv-3d turns'); cv.tabIndex = 0; cv.setAttribute('role', 'img'); cv.dataset.key = 'iv-3d';
    cv.setAttribute('aria-label', label + '. Drag or use the arrow keys to turn it, the wheel or + and − to zoom.');
    const [lo, hi] = m.bounds || [[-1, -1, -1], [1, 1, 1]], centre = [0, 1, 2].map(i => (lo[i] + hi[i]) / 2);
    const radius = Math.max(1e-9, Math.hypot(hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]) / 2);
    let frame = 0;
    const draw = () => {
      frame = 0;
      const size = fit(cv, Math.min(420, Math.round(cv.clientWidth * 0.75))); if (!size) return;
      const [W, H] = size, ctx = cv.getContext('2d'), img = ctx.createImageData(W, H), px = img.data, depth = new Float32Array(W * H).fill(Infinity);
      const cy = Math.cos(st.yaw), sy = Math.sin(st.yaw), cp = Math.cos(st.pitch), sp = Math.sin(st.pitch), s = st.zoom * 0.46 * Math.min(W, H) / radius;
      const n = m.points.length / 3, X = new Float32Array(n), Y = new Float32Array(n), Z = new Float32Array(n);
      for (let i = 0; i < n; i++) {
        const x = m.points[i * 3] - centre[0], y = m.points[i * 3 + 1] - centre[1], z = m.points[i * 3 + 2] - centre[2];
        const x1 = x * cy - y * sy, y1 = x * sy + y * cy, d = y1 * cp + z * sp, up = -y1 * sp + z * cp;
        X[i] = W / 2 + x1 * s; Y[i] = H / 2 - up * s; Z[i] = d;
      }
      if (m.triangles) {
        const base = token('--mark'), L = [-0.35, 0.55, -0.76], t = m.triangles;
        for (let f = 0; f + 2 < t.length; f += 3) {
          const a = t[f], b = t[f + 1], c = t[f + 2];
          // The normal in screen space (x right, y up, z away), for flat shading lit from the front.
          const ux = X[b] - X[a], uy = Y[a] - Y[b], uz = (Z[b] - Z[a]) * s, vx = X[c] - X[a], vy = Y[a] - Y[c], vz = (Z[c] - Z[a]) * s;
          const nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx, len = Math.hypot(nx, ny, nz) || 1;
          const shade = 0.32 + 0.68 * Math.abs((nx * L[0] + ny * L[1] + nz * L[2]) / len);
          triangle(px, depth, W, H, X[a], Y[a], Z[a], X[b], Y[b], Z[b], X[c], Y[c], Z[c], base[0] * shade, base[1] * shade, base[2] * shade);
        }
      } else {
        const r = Math.max(1, Math.round((window.devicePixelRatio || 1) * 1.6));
        const neg = token('--ramp-neg'), pos = token('--ramp-pos'), span = (hi[2] - lo[2]) || 1;
        for (let i = 0; i < n; i++) {
          const x0 = Math.round(X[i]), y0 = Math.round(Y[i]); if (x0 < 0 || y0 < 0 || x0 >= W || y0 >= H) continue;
          let R, G, B; if (m.colours) { R = m.colours[i * 3]; G = m.colours[i * 3 + 1]; B = m.colours[i * 3 + 2]; } else { const c = mix(neg, pos, (m.points[i * 3 + 2] - lo[2]) / span); R = c[0]; G = c[1]; B = c[2]; }
          for (let dy = 0; dy < r; dy++) for (let dx = 0; dx < r; dx++) {
            const xx = x0 + dx, yy = y0 + dy; if (xx >= W || yy >= H) continue; const o = yy * W + xx;
            if (Z[i] < depth[o]) { depth[o] = Z[i]; px[o * 4] = R; px[o * 4 + 1] = G; px[o * 4 + 2] = B; px[o * 4 + 3] = 255; }
          }
        }
      }
      ctx.putImageData(img, 0, 0);
    };
    const later = () => { if (!frame) frame = requestAnimationFrame(draw); };
    paints(cv, draw);
    let drag = null;
    cv.addEventListener('pointerdown', e => { if (e.button !== 0) return; drag = { x: e.clientX, y: e.clientY, id: e.pointerId }; cv.setPointerCapture(e.pointerId); cv.classList.add('dragging'); });
    cv.addEventListener('pointermove', e => { if (!drag || e.pointerId !== drag.id) return; st.yaw += (e.clientX - drag.x) * 0.01; st.pitch = Math.max(-1.55, Math.min(1.55, st.pitch + (e.clientY - drag.y) * 0.01)); drag.x = e.clientX; drag.y = e.clientY; later(); });
    const end = e => { if (drag && e.pointerId === drag.id) { drag = null; cv.classList.remove('dragging'); } };
    cv.addEventListener('pointerup', end); cv.addEventListener('pointercancel', end);
    cv.addEventListener('wheel', e => { e.preventDefault(); st.zoom = Math.max(0.2, Math.min(25, st.zoom * Math.exp(-e.deltaY * 0.0015))); later(); }, { passive: false });
    cv.addEventListener('keydown', e => {
      const k = e.key; let used = true;
      if (k === 'ArrowLeft') st.yaw -= 0.15; else if (k === 'ArrowRight') st.yaw += 0.15;
      else if (k === 'ArrowUp') st.pitch = Math.max(-1.55, st.pitch - 0.15); else if (k === 'ArrowDown') st.pitch = Math.min(1.55, st.pitch + 0.15);
      else if (k === '+' || k === '=') st.zoom = Math.min(25, st.zoom * 1.2); else if (k === '-' || k === '−') st.zoom = Math.max(0.2, st.zoom / 1.2);
      else used = false;
      if (used) { e.preventDefault(); later(); }
    });
    el.appendChild(cv);
    const bar = h('div', 'iv-ctl');
    const reset = button('btn sm', 'Reset view', () => { Object.assign(st, turned()); later(); }); reset.dataset.key = 'iv-reset'; bar.appendChild(reset);
    bar.appendChild(h('span', 'small faint', 'Drag to turn, wheel to zoom'));
    el.appendChild(bar);
  }
  /** Fills one triangle into the pixel and depth buffers (nearest wins). */
  function triangle(px, depth, W, H, ax, ay, az, bx, by, bz, cx, cy, cz, R, G, B) {
    const area = (bx - ax) * (cy - ay) - (by - ay) * (cx - ax); if (Math.abs(area) < 1e-9) return;
    const x0 = Math.max(0, Math.floor(Math.min(ax, bx, cx))), x1 = Math.min(W - 1, Math.ceil(Math.max(ax, bx, cx)));
    const y0 = Math.max(0, Math.floor(Math.min(ay, by, cy))), y1 = Math.min(H - 1, Math.ceil(Math.max(ay, by, cy)));
    for (let y = y0; y <= y1; y++) {
      const py = y + 0.5;
      for (let x = x0; x <= x1; x++) {
        const qx = x + 0.5;
        const w0 = ((cx - bx) * (py - by) - (cy - by) * (qx - bx)) / area, w1 = ((ax - cx) * (py - cy) - (ay - cy) * (qx - cx)) / area, w2 = 1 - w0 - w1;
        if (w0 < 0 || w1 < 0 || w2 < 0) continue;
        const z = w0 * az + w1 * bz + w2 * cz, o = y * W + x;
        if (z < depth[o]) { depth[o] = z; px[o * 4] = R; px[o * 4 + 1] = G; px[o * 4 + 2] = B; px[o * 4 + 3] = 255; }
      }
    }
  }

  // ---- Arrays: a slice along two axes, sliders for the others, the stacked slices and the histogram ---------------------
  /** A line of a one-row slice across (x, y, w, hh). */
  function line(ctx, values, min, max, x, y, w, hh, width) {
    const n = values.length, span = (max - min) || 1, ink = token('--mark');
    ctx.strokeStyle = 'rgb(' + ink.join(',') + ')'; ctx.lineWidth = width; ctx.beginPath();
    let on = false;
    for (let i = 0; i < n; i++) { const v = values[i]; if (!Number.isFinite(v)) { on = false; continue; } const px = x + (n === 1 ? w / 2 : i / (n - 1) * w), py = y + hh - 4 - (v - min) / span * (hh - 8); if (on) ctx.lineTo(px, py); else ctx.moveTo(px, py); on = true; }
    ctx.stroke();
  }
  async function arrayView(el, run, path, arrays, show, st) {
    if (!arrays.length) { el.appendChild(h('p', 'note', 'This file holds no array.')); return; }
    const pick = arrays.find(a => a.array === st.array) || arrays.find(a => a.array === show) || arrays.find(a => a.shape.length >= 2) || arrays[0];
    st.array = pick.array;
    const box = h('div', 'iv-array');
    /** Draws this array viewer again (another array or other axes), replacing it in one step with the focus kept. */
    const again = async () => {
      const host = h('div'); await arrayView(host, run, path, arrays, show, st);
      const fresh = host.firstChild; if (!fresh || !box.isConnected) return;
      const key = box.contains(document.activeElement) && document.activeElement.dataset ? document.activeElement.dataset.key : null;
      box.replaceWith(fresh);
      if (key) { const e = [...fresh.querySelectorAll('[data-key]')].find(x => x.dataset.key === key); if (e) e.focus({ preventScroll: true }); }
    };
    // The arrays, with shape and type; the one chosen is drawn.
    if (arrays.length > 1) {
      const s = h('select'); s.setAttribute('aria-label', 'Array'); s.dataset.key = 'iv-array';
      for (const a of arrays) { const o = h('option', null, (a.array == null ? '(the array)' : a.array) + ' · ' + a.dtype + ' · ' + (a.shape.length ? a.shape.join(' × ') : 'one value')); o.value = a.array; o.selected = a === pick; s.appendChild(o); }
      s.addEventListener('change', () => { st.array = s.value; st.axes = null; st.index = null; again(); });
      const l = h('label', 'iv-field'); l.appendChild(document.createTextNode('Array')); l.appendChild(s); box.appendChild(l);
    } else box.appendChild(h('p', 'small muted', (pick.array ? pick.array + ' · ' : '') + pick.dtype + ' · ' + (pick.shape.length ? pick.shape.join(' × ') : 'one value')));
    const shape = pick.shape, nd = shape.length;
    if (!st.axes || st.axes.some(a => a >= nd)) st.axes = nd >= 2 ? [nd - 2, nd - 1] : nd === 1 ? [0] : [];
    if (!st.index || st.index.length !== nd) st.index = shape.map(n => Math.floor(n / 2));
    const base = { path, array: pick.array, most: VIEW_MOST };
    const args = () => { const a = Object.assign({}, base); if (nd >= 2) { a.axes = st.axes.slice(); a.index = st.index.slice(); } return a; };
    // Two axes drawn (for three or more dimensions they can be chosen), a slider per other axis.
    const ctl = h('div', 'iv-ctl');
    if (nd > 2) for (const [i, label] of [[0, 'Rows'], [1, 'Columns']]) {
      const s = h('select'); s.setAttribute('aria-label', label + ' axis'); s.dataset.key = 'iv-axis-' + i;
      for (let a = 0; a < nd; a++) { const o = h('option', null, 'axis ' + a + ' (' + shape[a] + ')'); o.value = String(a); o.selected = st.axes[i] === a; o.disabled = st.axes[1 - i] === a; s.appendChild(o); }
      s.addEventListener('change', () => { st.axes[i] = Number(s.value); again(); });
      const l = h('label', 'iv-field'); l.appendChild(document.createTextNode(label)); l.appendChild(s); ctl.appendChild(l);
    }
    const others = nd >= 2 ? shape.map((_, a) => a).filter(a => !st.axes.includes(a)) : [];
    const sliders = [];
    for (const a of others) {
      const l = h('label', 'iv-field iv-slider'); const name = h('span', null, 'Axis ' + a); l.appendChild(name);
      const r = h('input'); r.type = 'range'; r.min = '0'; r.max = String(shape[a] - 1); r.value = String(st.index[a]); r.dataset.key = 'iv-axis-slider-' + a; r.dataset.axis = String(a);
      const at = h('span', 'num small', st.index[a] + ' of ' + shape[a]);
      r.setAttribute('aria-label', 'Position on axis ' + a + ', 0 to ' + (shape[a] - 1));
      l.appendChild(r); l.appendChild(at); ctl.appendChild(l); sliders.push({ a, r, at });
    }
    if (ctl.children.length) box.appendChild(ctl);
    // The slice, read now.
    let s;
    try { s = await R.slice(run, args(), true); } catch (error) { box.appendChild(window.LabActions.refusal(error)); el.appendChild(box); return; }
    const sliceBox = h('div', 'iv-slice'), cv = h('canvas', 'iv-heat'); cv.setAttribute('role', 'img'); sliceBox.appendChild(cv);
    const range = h('p', 'small muted iv-range'), probe = h('p', 'small iv-probe'); probe.textContent = 'Point at the slice to read a value.';
    let values = floats(s.values_f32), rect = null;
    const say = () => {
      cv.dataset.index = JSON.stringify(s.index); cv.dataset.axes = JSON.stringify(s.axes || []);
      const what = s.rows === 1 && nd <= 1 ? (nd === 0 ? 'The value' : 'The ' + s.columns + ' values') : 'Slice of ' + s.rows + ' by ' + s.columns + ' values along axes ' + (s.axes || []).join(' and ') + (others.length ? ' at ' + others.map(a => 'axis ' + a + ' = ' + s.index[a]).join(', ') : '');
      cv.setAttribute('aria-label', what + ' of ' + (pick.array || path) + ', from ' + fmt(s.min) + ' to ' + fmt(s.max));
      range.textContent = 'From ' + fmt(s.min) + ' to ' + fmt(s.max) + (s.stride > 1 ? ' · every ' + ordinal(s.stride) + ' row and column' : '') + (s.nonfinite ? ' · ' + count(s.nonfinite, 'value') + ' not finite, left clear' : '');
    };
    const paintSlice = () => {
      const wide = s.rows === 1, w = cv.clientWidth; if (!w) return;
      const cssH = wide ? 120 : Math.max(80, Math.min(360, Math.round(w * s.rows / s.columns)));
      const size = fit(cv, cssH); if (!size) return; const [W, H] = size, ctx = cv.getContext('2d'); ctx.clearRect(0, 0, W, H);
      if (wide) { rect = [0, 0, W, H]; line(ctx, values, s.min == null ? 0 : s.min, s.max == null ? 1 : s.max, 0, 0, W, H, Math.max(1.5, W / 400)); }
      else { rect = contain(s.rows, s.columns, W, H); heat(ctx, values, s.rows, s.columns, ramp(s.min == null ? 0 : s.min, s.max == null ? 1 : s.max), ...rect); }
      const where = rect.map(n => Math.round(n * 100) / 100).join(',') + ';' + s.rows + 'x' + s.columns;   // where the cells are, for a reader of the page
      if (cv.dataset.cells !== where) cv.dataset.cells = where;
    };
    paints(cv, paintSlice);
    cv.addEventListener('pointermove', e => {
      if (!rect) return; const dpr = cv.width / cv.clientWidth, x = e.offsetX * dpr - rect[0], y = e.offsetY * (cv.height / cv.clientHeight) - rect[1];
      if (x < 0 || y < 0 || x >= rect[2] || y >= rect[3]) { probe.textContent = 'Point at the slice to read a value.'; delete probe.dataset.index; return; }
      const col = Math.min(s.columns - 1, Math.floor(x / rect[2] * s.columns)), row = s.rows === 1 ? 0 : Math.min(s.rows - 1, Math.floor(y / rect[3] * s.rows));
      const index = (s.index || []).slice(); if (nd >= 2) { index[s.axes[0]] = row * s.stride; index[s.axes[1]] = col * s.stride; } else if (nd === 1) index[0] = col * s.stride;
      const v = values[row * s.columns + col];
      probe.textContent = '[' + index.join(', ') + '] = ' + (Number.isFinite(v) ? String(v) : String(v) + ' (not finite)');
      probe.dataset.index = JSON.stringify(index); probe.dataset.value = String(v);
    });
    cv.addEventListener('pointerleave', () => { probe.textContent = 'Point at the slice to read a value.'; delete probe.dataset.index; });
    box.appendChild(sliceBox); box.appendChild(range); box.appendChild(probe); say();
    // Three or more dimensions: the stacked slices along the first other axis, the slider's slice outlined (the mockup's drawVolume).
    let stack = null;
    if (nd >= 3) {
      const axis = others[0], n = shape[axis], at = Array.from(new Set(Array.from({ length: Math.min(n, STACK_SLICES) }, (_, i) => Math.round(n <= STACK_SLICES ? i : i * (n - 1) / (STACK_SLICES - 1)))));
      const vol = h('canvas', 'iv-vol'); vol.setAttribute('role', 'img');
      stack = { axis, at, vol, slices: null, key: null };
      const loadStack = async () => {
        const key = JSON.stringify([st.axes, st.index.filter((_, i) => i !== axis)]); if (stack.key === key) return; stack.key = key;
        const got = await Promise.all(at.map(p => { const a = args(); a.most = STACK_MOST; a.index[axis] = p; return R.slice(run, a); }));
        if (stack.key !== key) return;
        stack.slices = got.map(g => ({ values: floats(g.values_f32), rows: g.rows, cols: g.columns, min: g.min, max: g.max }));
      };
      const paintStack = () => {
        if (!stack.slices) return; const w = vol.clientWidth; if (!w) return;
        const size = fit(vol, Math.round(Math.min(360, w * 0.62))); if (!size) return;
        volume(vol, stack.slices, at.indexOf(nearest(at, st.index[axis])));
        vol.setAttribute('aria-label', 'Stacked slices of ' + (pick.array || path) + ' along axis ' + axis + ': ' + at.length + ' of its ' + n + ' positions, the one at ' + nearest(at, st.index[axis]) + ' outlined');
      };
      try { await loadStack(); } catch (error) { stack = null; box.appendChild(window.LabActions.refusal(error)); }
      if (stack) { paints(vol, paintStack); stack.paint = paintStack; stack.load = loadStack; const vb = h('div', 'iv-volbox'); vb.appendChild(vol); box.insertBefore(vb, sliceBox); }
    }
    // A slider moves the slice: read again (the latest wins), redraw in place.
    let wanted = 0, timer = 0;
    for (const { a, r, at } of sliders) r.addEventListener('input', () => {
      st.index[a] = Number(r.value); at.textContent = st.index[a] + ' of ' + shape[a];
      if (stack && a === stack.axis) stack.paint && stack.paint();
      clearTimeout(timer); const mine = ++wanted;
      timer = setTimeout(async () => {
        try {
          const next = await R.slice(run, args(), true); if (mine !== wanted) return;
          s = next; values = floats(s.values_f32); paintSlice(); say();
          probe.textContent = 'Point at the slice to read a value.'; delete probe.dataset.index;
          if (stack && a !== stack.axis) { await stack.load(); stack.paint(); }
        } catch (error) { if (mine === wanted) { probe.textContent = error.message; } }
      }, 90);
    });
    // The summary's histogram, on request.
    const hb = button('btn sm', st.hist ? 'Hide the histogram' : 'Show the histogram'); hb.dataset.key = 'iv-hist'; hb.setAttribute('aria-expanded', String(!!st.hist));
    const hist = h('div', 'iv-hist'); hist.hidden = !st.hist;
    const fillHist = async () => {
      if (hist.firstChild) return;
      try {
        const sum = await R.summary(run, { path, array: pick.array, bins: 64 });
        const hc = h('canvas', 'iv-histc'); hc.setAttribute('role', 'img'); hc.setAttribute('aria-label', 'Histogram of ' + (pick.array || path) + ' in ' + sum.histogram.counts.length + ' bins from ' + fmt(sum.histogram.low) + ' to ' + fmt(sum.histogram.high));
        paints(hc, () => {
          const size = fit(hc, 110); if (!size) return; const [W, H] = size, ctx = hc.getContext('2d'); ctx.clearRect(0, 0, W, H);
          const counts = sum.histogram.counts, most = Math.max(1, ...counts), bw = W / counts.length, ink = token('--mark'), axis = token('--line-strong');
          ctx.fillStyle = 'rgb(' + ink.join(',') + ')';
          counts.forEach((n, i) => { if (!n) return; const bh = Math.max(1, n / most * (H - 6)); ctx.fillRect(i * bw + 0.5, H - bh, Math.max(1, bw - 1), bh); });
          ctx.fillStyle = 'rgb(' + axis.join(',') + ')'; ctx.fillRect(0, H - 1, W, 1);
        });
        hist.appendChild(hc);
        const ends = h('div', 'iv-ends small faint'); ends.appendChild(h('span', null, fmt(sum.histogram.low))); ends.appendChild(h('span', null, fmt(sum.histogram.high))); hist.appendChild(ends);
        const dl = h('dl', 'setup iv-facts');
        for (const [k, val] of [['Values', sum.count.toLocaleString('en-GB') + (sum.stride > 1 ? ', every ' + ordinal(sum.stride) + ' read' : '')], ['Mean', fmt(sum.mean)], ['Deviation', fmt(sum.std)], ['Zeros', sum.zeros.toLocaleString('en-GB')], ['Not finite', sum.nonfinite.toLocaleString('en-GB')]]) { dl.appendChild(h('dt', null, k)); dl.appendChild(h('dd', 'num', val)); }
        hist.appendChild(dl);
      } catch (error) { hist.appendChild(window.LabActions.refusal(error)); }
    };
    hb.addEventListener('click', async () => { st.hist = !st.hist; hb.textContent = st.hist ? 'Hide the histogram' : 'Show the histogram'; hb.setAttribute('aria-expanded', String(st.hist)); if (st.hist) await fillHist(); hist.hidden = !st.hist; });
    if (st.hist) await fillHist();
    const hrow = h('div', 'iv-ctl'); hrow.appendChild(hb); box.appendChild(hrow); box.appendChild(hist);
    el.appendChild(box);
  }
  const nearest = (list, x) => list.reduce((a, b) => Math.abs(b - x) < Math.abs(a - x) ? b : a, list[0]);
  /** The stacked-slice drawing of the mockup (drawVolume): each slice a sheared sheet of cells, the chosen one outlined. */
  function volume(canvas, slices, hot) {
    const W = canvas.width, H = canvas.height, ctx = canvas.getContext('2d'); ctx.clearRect(0, 0, W, H);
    let min = Infinity, max = -Infinity; for (const sl of slices) { if (sl.min != null) min = Math.min(min, sl.min); if (sl.max != null) max = Math.max(max, sl.max); }
    if (!Number.isFinite(min)) { min = 0; max = 1; }
    const colour = ramp(min, max), first = slices[0], sx = Math.min(16, first.cols), sy = Math.max(2, Math.min(16, Math.round(16 * first.rows / Math.max(1, first.cols)), first.rows)), nsl = slices.length;
    const cw = Math.min(W * 0.62 / (sx + sy / 2), 30 * W / 480), ch = cw * 0.5, dz = Math.min(H * 0.07, (H - 30 - sy * ch) / Math.max(1, nsl - 1));
    const ox = W / 2 - (sx * cw) / 2 + (sy * cw) / 4, oy = H - 16 - (nsl - 1) * dz - sy * ch;
    const accent = token('--accent');
    for (let k = 0; k < nsl; k++) {
      const sl = slices[k], isHot = k === hot; ctx.globalAlpha = isHot ? 1 : 0.55;
      for (let j = 0; j < sy; j++) for (let i = 0; i < sx; i++) {
        const v = sl.values[Math.min(sl.rows - 1, Math.floor(j * sl.rows / sy)) * sl.cols + Math.min(sl.cols - 1, Math.floor(i * sl.cols / sx))];
        if (!Number.isFinite(v)) continue; const c = colour(v); ctx.fillStyle = 'rgb(' + c.map(Math.round).join(',') + ')';
        const px = ox + i * cw - j * (cw / 2), py = oy + (nsl - 1 - k) * dz + j * ch;
        ctx.beginPath(); ctx.moveTo(px, py); ctx.lineTo(px + cw, py); ctx.lineTo(px + cw / 2, py + ch); ctx.lineTo(px - cw / 2, py + ch); ctx.closePath(); ctx.fill();
      }
      if (isHot) { ctx.globalAlpha = 1; ctx.strokeStyle = 'rgb(' + accent.join(',') + ')'; ctx.lineWidth = Math.max(2, W / 300); const py = oy + (nsl - 1 - k) * dz; ctx.beginPath(); ctx.moveTo(ox, py); ctx.lineTo(ox + sx * cw, py); ctx.lineTo(ox + sx * cw - sy * cw / 2, py + sy * ch); ctx.lineTo(ox - sy * cw / 2, py + sy * ch); ctx.closePath(); ctx.stroke(); }
    }
    ctx.globalAlpha = 1;
  }

  /**
   * What the Annotate tab (annotate.js) draws with: a record's viewer as this module draws it, from the answer of
   * `record` (run: the product's run; store: a Map that keeps each viewer's settings, as a dataset opened here does),
   * and the parts its own drawing surfaces share with these viewers.
   */
  const viewers = { record: (el, got, run, store) => recordView(null, { run, viewers: store }, el, got), wave, paints, fit, token, glyph, WORD };
  return { open, leave, PER_PAGE, viewers };
})();
