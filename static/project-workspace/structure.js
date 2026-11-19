'use strict';
// A model's structure (docs/plans/training-and-curation/spec-t2.md section 4): the block "Structure" of a model's
// drawer, right after Weights, when one of the model's current products holds model-graph.json. The graph the
// project's script recorded is drawn left to right in SVG (ranks by the longest path from the inputs, each rank
// ordered by the barycentre of its neighbours), its modules folded into groups that open when pressed and close
// from the module outline under the drawing. An operation pressed shows its details, whose tensors open in the
// Weights block (LabWeights.reveal). "Colour by" fills the nodes from model_graph_overlay; "Compare with" draws
// the graph of the model it derives from, or of one derived from it, under this one, folded the same way, and
// marks the modules model_graph_compare finds added, missing or changed.
//
// Updating in place (spec-w4): the block is built off the page and put in place whole, like weights.js's. Read
// again for the model on screen (screens.js), it is built from the person's place in it (folding, selection,
// colour, comparison) and resolves only once complete; the person's own choices draw it again the same way, the
// focus kept by data-key and the drawing's scroll by putInPlace.
window.LabStructure = (() => {
  const P = window.TuldokProject, S = window.LabScreens, C = window.LabCharts, h = C.h, R = P.product;
  const { putInPlace } = S.parts;
  const SVG = 'http://www.w3.org/2000/svg';
  const W = 132, H = 42, GAP = 40, VGAP = 14, PAD = 10, SWEEPS = 4, LABEL = 18;
  const num = n => n == null ? '—' : n.toLocaleString('en-GB');
  const plural = (n, one, many) => num(n) + ' ' + (n === 1 ? one : many || one + 's');
  const shapeText = s => !s ? '' : s.length ? s.join('×') : 'scalar';
  const valuesText = list => (list || []).map(v => shapeText(v.shape) + ' ' + v.dtype).join(', ') || '—';
  const short = text => text.length > LABEL ? text.slice(0, LABEL - 1) + '…' : text;
  const classShort = c => c ? c.split('.').pop() : '';
  const button = (cls, text, onClick) => { const b = h('button', cls, text); b.type = 'button'; if (onClick) b.addEventListener('click', onClick); return b; };
  const refusal = error => window.LabActions.refusal(error);
  const svg = (tag, attrs) => { const e = document.createElementNS(SVG, tag); for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v); return e; };
  const COLOURS = [['', 'Nothing'], ['parameters', 'Parameters'], ['outputs', 'Output size'], ['operations', 'Operations'], ['change:start', 'Change from the weights it started from'], ['change:parent', 'Change from the model it derives from']];
  let drawings = 0;   // a number per drawing, for the ids of its arrow markers

  // ---- The person's place in each model's block -------------------------------------------------------------------
  const places = new Map();
  const placeOf = id => { if (!places.has(id)) places.set(id, { depth: null, open: [], close: [], selected: null, colour: '', compare: '', fit: false }); return places.get(id); };
  const foldArgs = (st, depth) => st.depth == null && !st.open.length && !st.close.length && depth == null ? {} : { depth: st.depth == null ? depth : st.depth, open: st.open.slice().sort(), close: st.close.slice().sort() };

  // ---- Reading ----------------------------------------------------------------------------------------------------------
  /** The first current product of a model that holds a graph: { run, subject, graph } (its graph folded the default way), or null. */
  async function graphRun(reference) {
    const products = (await P.read('products', { reference })).products.filter(p => p.run_id);
    for (const p of products) {
      const graph = await R.graph(p.run_id, {});
      if (graph.path) return { run: p.run_id, subject: p.subject || '', graph };   // path null: no graph in this product
    }
    return null;
  }

  /**
   * Fills box (a block of the drawer of model m, on the page or not yet) with the Structure block, or hides it
   * when no product of the model holds a graph. Resolves once the block is complete.
   */
  async function block(box, m, g, scroller, live) {
    const st = placeOf(m.id), ctx = { box, m, g, st, scroller, live, turn: 0 };
    let root;
    try { root = await build(ctx); } catch (error) { root = h('div', 'st'); root.appendChild(h('h3', null, 'Structure')); root.appendChild(refusal(error)); }
    if (!live()) return;
    st.ctx = ctx;
    if (!root) { box.hidden = true; box.replaceChildren(); return; }
    box.hidden = false; box.replaceChildren(root);
  }
  async function again(ctx) {
    const mine = ++ctx.turn;
    ctx.box.setAttribute('aria-busy', 'true');
    let root; try { root = await build(ctx); } catch (error) { root = h('div', 'st'); root.appendChild(h('h3', null, 'Structure')); root.appendChild(refusal(error)); }
    if (mine !== ctx.turn || !ctx.box.isConnected) return;
    ctx.box.removeAttribute('aria-busy');
    putInPlace(ctx.box, root || h('div'), ctx.scroller);
  }

  /** The Structure block drawn again over the page, full width; Escape or "Back to the drawer" closes it. */
  function openWide(ctx) {
    if (ctx.st.wideCtx) return;
    const box = h('div', 'st-overlay'); box.setAttribute('role', 'dialog'); box.setAttribute('aria-label', 'Structure, full width');
    document.body.appendChild(box);
    const w = { ...ctx, box, scroller: box, turn: 0, wide: true, base: ctx };
    w.esc = ev => { if (ev.key === 'Escape') closeWide(w); };
    document.addEventListener('keydown', w.esc);
    ctx.st.wideCtx = w;
    again(w).then(() => { const b = box.querySelector('[data-key="st-wide"]'); if (b) b.focus(); });
  }
  function closeWide(w) {
    document.removeEventListener('keydown', w.esc);
    w.box.remove(); w.st.wideCtx = null;
    again(w.base).then(() => { const b = w.base.box.querySelector('[data-key="st-wide"]'); if (b) b.focus(); });
  }

  /** The other models it can be compared with: the model it derives from and those derived from it, with a graph. */
  async function choicesFor(m, g) {
    const refs = [m.parent].filter(p => p && g.byId.has(p)).map(p => ['parent', p]).concat(g.nodes.filter(n => n.parent === m.id).map(n => ['child', n.id]));
    const out = [];
    for (const [rel, ref] of refs) {
      const got = await graphRun(ref).catch(() => null), o = g.byId.get(ref);
      if (got) out.push({ key: ref, run: got.run, label: (rel === 'parent' ? 'The model it derives from: ' : 'Derived from it: ') + (o.short ? o.short + ' · ' : '') + o.title });
    }
    return out;
  }

  async function build(ctx) {
    const { m, g, st } = ctx;
    const found = await graphRun(m.id);
    if (!found) return null;
    const { run } = found;
    const args = foldArgs(st, null);
    const graph = Object.keys(args).length ? await R.graph(run, args) : found.graph;
    const root = h('div', 'st');
    root.appendChild(h('h3', null, 'Structure'));
    const c = graph.counts;
    root.appendChild(h('p', 'small muted st-size', [graph.path + (found.subject ? ' · ' + found.subject : ''), plural(c.operations, 'operation'), plural(c.modules, 'module'), plural(c.tensors, 'tensor')].join(' · ')));
    root.appendChild(h('p', 'small faint st-how', 'Recorded by ' + (graph.method || 'the project') + (graph.torch ? ' with PyTorch ' + graph.torch : '') + (graph.inputs.length ? '; example input ' + graph.inputs.map(v => v.name + ' ' + shapeText(v.shape)).join(', ') : '') + '.'));
    for (const note of graph.notes) root.appendChild(h('p', 'small warnline', note));
    if (!graph.complete) {
      root.appendChild(h('p', 'empty st-reason', 'Only the module tree was recorded: ' + (graph.reason || 'no reason given') + '.'));
      root.appendChild(outline(ctx, graph, null));
      return root;
    }
    // The controls: colour, comparison, folding.
    const colourChoices = COLOURS.filter(([k]) => k !== 'change:parent' || m.parent);
    if (!colourChoices.some(([k]) => k === st.colour)) st.colour = '';
    const compareChoices = await choicesFor(m, g);
    if (!compareChoices.some(x => x.key === st.compare)) st.compare = '';
    const bar = h('div', 'st-bar');
    const sel = (label, key, options, value, onChange) => {
      const s = h('select'); s.setAttribute('aria-label', label); s.dataset.key = key;
      for (const [v, t] of options) { const o = h('option', null, t); o.value = v; o.selected = v === value; s.appendChild(o); }
      s.addEventListener('change', () => onChange(s.value));
      const l = h('label', 'iv-field st-pick'); l.appendChild(document.createTextNode(label)); l.appendChild(s); return l;
    };
    bar.appendChild(sel('Colour by', 'st-colour', colourChoices, st.colour, v => { st.colour = v; again(ctx); }));
    if (compareChoices.length) bar.appendChild(sel('Compare with', 'st-compare', [['', 'Nothing']].concat(compareChoices.map(x => [x.key, x.label])), st.compare, v => { st.compare = v; again(ctx); }));
    const folds = h('div', 'st-folds');
    const all = button('btn sm', 'Open all', () => { Object.assign(st, { depth: 64, open: [], close: [] }); again(ctx); }); all.dataset.key = 'st-open-all';
    const one = button('btn sm', 'Fold to depth 1', () => { Object.assign(st, { depth: 1, open: [], close: [] }); again(ctx); }); one.dataset.key = 'st-fold-1';
    const fit = button('btn sm', 'Fit to width', () => { st.fit = !st.fit; again(ctx); }); fit.dataset.key = 'st-fit'; fit.setAttribute('aria-pressed', String(st.fit));
    fit.title = 'Shrink the drawings to the drawer\'s width, for an overview; press again for their actual size';
    // The drawer is narrow: the same view, with the same state, opens over the page at its full width.
    const wide = button('btn sm', ctx.wide ? 'Back to the drawer' : 'Open wide', () => (ctx.wide ? closeWide(ctx) : openWide(ctx)));
    wide.dataset.key = 'st-wide';
    folds.appendChild(all); folds.appendChild(one); folds.appendChild(fit); folds.appendChild(wide); bar.appendChild(folds);
    root.appendChild(bar);
    // The overlay and the comparison, read in full before anything is drawn.
    let overlay = null, overlayError = null;
    if (st.colour) {
      const [kind, against] = st.colour.split(':');
      const oargs = { kind };
      if (against === 'start') oargs.against = 'start';
      if (against === 'parent') { const p = (await P.read('products', { reference: m.parent })).products.find(x => x.run_id); oargs.against = 'run'; oargs.other_run = p ? p.run_id : null; }
      try { overlay = await R.graphOverlay(run, oargs); } catch (error) { overlayError = error; }
    }
    const choice = compareChoices.find(x => x.key === st.compare) || null;
    let other = null, cmp = null, cmpError = null;
    if (choice) {
      try { [other, cmp] = await Promise.all([R.graph(choice.run, { depth: graph.depth, open: st.open.slice().sort(), close: st.close.slice().sort() }), R.graphCompare(run, choice.run)]); }
      catch (error) { cmpError = error; }
    }
    if (overlayError) root.appendChild(refusal(overlayError));
    if (cmpError) root.appendChild(refusal(cmpError));
    const status = cmp ? statuses(cmp, false) : null;
    root.appendChild(drawing(ctx, graph, overlay, status, 'This model', true));
    if (overlay) root.appendChild(legend(overlay));
    const chosen = graph.nodes.find(n => n.id === st.selected);
    if (chosen) root.appendChild(details(ctx, graph, chosen, overlay, status));
    if (other) {
      const head = h('h4', 'st-sub', (g.byId.get(choice.key).short ? g.byId.get(choice.key).short + ' · ' : '') + g.byId.get(choice.key).title);
      root.appendChild(head);
      root.appendChild(drawing(ctx, other, null, statuses(cmp, true), 'The other model', false));
      root.appendChild(differences(cmp));
    }
    root.appendChild(outline(ctx, graph, status));
    return root;
  }

  // ---- The comparison --------------------------------------------------------------------------------------------------
  /** {path: status} from a model_graph_compare answer, seen from this graph or (mirrored) from the other's. */
  function statuses(cmp, mirrored) {
    const out = new Map();
    for (const r of cmp.modules) out.set(r.path, mirrored ? ({ added: 'missing', missing: 'added' }[r.status] || r.status) : r.status);
    return out;
  }
  /** A node's mark: its module's status; a group's, or "inside" when a module within it differs. */
  function markOf(node, status) {
    if (!status || node.kind === 'input' || node.kind === 'output') return null;
    const own = status.get(node.module);
    if (own && own !== 'same' && own !== 'missing') return own;
    if (node.kind === 'group') for (const [path, s] of status) if (s !== 'same' && s !== 'missing' && path.startsWith(node.module + '.')) return 'inside';
    return null;
  }
  const MARK_WORD = { added: 'only in this model', missing: 'only in the other model', changed: 'changed', inside: 'something inside it differs' };
  function differences(cmp) {
    const box = h('div', 'st-diff'); const rows = cmp.modules.filter(r => r.status !== 'same');
    box.appendChild(h('p', 'small muted', rows.length ? 'Modules matched by path: ' + ['changed', 'added', 'missing'].map(k => cmp.counts[k] + ' ' + { changed: 'changed', added: 'only here', missing: 'only in the other' }[k]).join(', ') + '.' : 'Every module matches by path, class and tensor shapes.'));
    if (!rows.length) return box;
    const ul = h('ul', 'st-difflist');
    for (const r of rows) {
      const li = h('li', 'st-d-' + r.status); li.dataset.path = r.path; li.dataset.status = r.status;
      li.appendChild(h('span', 'mono', r.path || '(the model)'));
      const why = r.status === 'added' ? 'only in this model' : r.status === 'missing' ? 'only in the other' : [r.class !== r.other_class ? classShort(r.other_class) + ' → ' + classShort(r.class) : null].concat(r.reshaped.map(x => x.name.split('.').pop() + ' ' + shapeText(x.other_shape) + ' → ' + shapeText(x.shape)), r.only_here.map(n => n.split('.').pop() + ' added'), r.only_there.map(n => n.split('.').pop() + ' removed')).filter(Boolean).join('; ');
      li.appendChild(h('span', 'small muted', ' ' + why)); ul.appendChild(li);
    }
    box.appendChild(ul); return box;
  }

  // ---- The layout ----------------------------------------------------------------------------------------------------------
  /** Positions of the shown nodes: ranks by the longest path from the inputs, each rank ordered by barycentre. */
  function layout(nodes, edges) {
    const at = new Map(nodes.map((n, i) => [n.id, i])), rank = new Array(nodes.length).fill(0);
    const into = nodes.map(() => []), out = nodes.map(() => []), forward = [];
    for (const e of edges) { const a = at.get(e.from), b = at.get(e.to); if (a == null || b == null) continue; if (a < b) { into[b].push(a); out[a].push(b); forward.push(e); } }
    for (let i = 0; i < nodes.length; i++) for (const a of into[i]) rank[i] = Math.max(rank[i], rank[a] + 1);
    const ranks = []; for (let i = 0; i < nodes.length; i++) (ranks[rank[i]] = ranks[rank[i]] || []).push(i);
    const pos = new Array(nodes.length).fill(0);
    const place = () => { for (const r of ranks) r.forEach((i, k) => { pos[i] = k; }); };
    place();
    const bary = (i, side) => { const n = side[i]; return n.length ? n.reduce((s, j) => s + pos[j], 0) / n.length : pos[i]; };
    for (let sweep = 0; sweep < SWEEPS; sweep++) {
      const down = sweep % 2 === 0, order = down ? ranks.slice(1) : ranks.slice(0, -1).reverse();
      for (const r of order) { const b = new Map(r.map(i => [i, bary(i, down ? into : out)])); r.sort((x, y) => b.get(x) - b.get(y) || x - y); r.forEach((i, k) => { pos[i] = k; }); }
    }
    const most = Math.max(1, ...ranks.map(r => r.length));
    const xy = nodes.map((_, i) => { const r = ranks[rank[i]]; return { x: PAD + rank[i] * (W + GAP), y: PAD + (pos[i] + (most - r.length) / 2) * (H + VGAP) }; });
    return { xy, at, width: PAD * 2 + ranks.length * W + (ranks.length - 1) * GAP, height: PAD * 2 + most * H + (most - 1) * VGAP + 18, rank };
  }

  // ---- The drawing ------------------------------------------------------------------------------------------------------
  /** The value of a node in an overlay: a group's module's, an operation's own. */
  const valueOf = (node, overlay) => !overlay ? null : node.kind === 'group' ? overlay.modules[node.module] : node.kind === 'operation' ? overlay.nodes[node.id] : null;
  const LOG = { parameters: true, outputs: true, operations: true };
  /** 0..1 of a value on the overlay's scale (logarithmic for counts). */
  function scaled(v, overlay) {
    if (v == null || !Number.isFinite(v)) return null;
    const f = LOG[overlay.kind] ? x => Math.log10(1 + Math.max(0, x)) : x => x;
    const lo = Math.min(f(0), f(overlay.low == null ? 0 : overlay.low)), hi = f(overlay.high == null ? 0 : overlay.high);
    return hi > lo ? Math.min(1, Math.max(0, (f(v) - lo) / (hi - lo))) : 0;
  }
  const fmtValue = (v, overlay) => v == null ? 'no value' : overlay.kind === 'change' ? C.fmtSci(v) : num(v) + ' ' + overlay.unit;

  function drawing(ctx, graph, overlay, status, title, mine) {
    const { st } = ctx, id = ++drawings, lay = layout(graph.nodes, graph.edges);
    const box = h('div', 'st-draw'); box.dataset.which = mine ? 'this' : 'other';
    const s = svg('svg', { width: lay.width, height: lay.height, viewBox: '0 0 ' + lay.width + ' ' + lay.height, role: 'group', 'aria-label': title + ': ' + plural(graph.nodes.length, 'node') + ', ' + plural(graph.edges.length, 'edge') + ', drawn left to right' });
    const defs = svg('defs'), marker = svg('marker', { id: 'st-arrow-' + id, viewBox: '0 0 8 8', refX: 7, refY: 4, markerWidth: 7, markerHeight: 7, orient: 'auto-start-reverse' });
    marker.appendChild(svg('path', { d: 'M0 0 L8 4 L0 8 z', class: 'st-arrowhead' })); defs.appendChild(marker); s.appendChild(defs);
    const edges = svg('g', { class: 'st-edges' });
    for (const e of graph.edges) {
      const a = lay.at.get(e.from), b = lay.at.get(e.to); if (a == null || b == null) continue;
      const p = lay.xy[a], q = lay.xy[b];
      let d;
      if (lay.rank[b] > lay.rank[a]) { const x1 = p.x + W, y1 = p.y + H / 2, x2 = q.x - 2, y2 = q.y + H / 2, mx = (x1 + x2) / 2; d = `M${x1} ${y1} C${mx} ${y1} ${mx} ${y2} ${x2} ${y2}`; }
      else { const x1 = p.x + W / 2, y1 = p.y + H, x2 = q.x + W / 2, y2 = q.y + H + 2, low = Math.max(y1, y2) + 16; d = `M${x1} ${y1} C${x1} ${low} ${x2} ${low} ${x2} ${y2}`; }
      const path = svg('path', { d, class: 'st-edge' + (lay.rank[b] > lay.rank[a] ? '' : ' back'), 'marker-end': 'url(#st-arrow-' + id + ')' });
      const t = svg('title'); t.textContent = e.from + ' → ' + e.to + (e.shape ? ': ' + shapeText(e.shape) + ' ' + e.dtype : '') + (e.count > 1 ? ' (' + e.count + ' values)' : ''); path.appendChild(t);
      edges.appendChild(path);
    }
    s.appendChild(edges);
    const layer = svg('g', { class: 'st-nodes' });
    graph.nodes.forEach((n, i) => {
      const { x, y } = lay.xy[i], v = valueOf(n, overlay), t = overlay ? scaled(v, overlay) : null, mark = markOf(n, status);
      const gEl = svg('g', { class: 'st-node ' + n.kind + (mark ? ' mark-' + mark : '') + (mine && st.selected === n.id ? ' selected' : '') + (t != null && t > 0.55 ? ' deep' : ''), transform: `translate(${x} ${y})`, tabindex: '0', role: 'button' });
      gEl.dataset.key = (mine ? 'st-node-' : 'st-other-') + n.id; gEl.dataset.id = n.id; gEl.dataset.module = n.module; if (mark) gEl.dataset.mark = mark;
      if (t != null) gEl.dataset.value = String(v);
      const sub = n.kind === 'group' ? classShort(n.class) + ' · ' + plural(n.operations, 'op') : n.outputs.length ? shapeText(n.outputs[0].shape) : '';
      const what = n.kind === 'group' ? 'Module ' + n.module + ' (' + classShort(n.class) + '), ' + plural(n.operations, 'operation') + ' folded; press to open it' : n.kind === 'operation' ? 'Operation ' + n.label + ' in ' + (n.module || 'the model') + ', gives ' + valuesText(n.outputs) + (mine ? '; press for its details' : '') : (n.kind === 'input' ? 'Input ' : 'Output ') + n.id + ', ' + valuesText(n.outputs);
      gEl.setAttribute('aria-label', what + (overlay ? '; ' + fmtValue(v, overlay) : '') + (mark ? '; ' + MARK_WORD[mark] : ''));
      const rect = svg('rect', { width: W, height: H, rx: n.kind === 'operation' ? 6 : n.kind === 'group' ? 3 : 14, class: 'st-box' });
      if (t != null) rect.style.fill = `color-mix(in srgb, var(--ramp-hi) ${Math.round(t * 100)}%, var(--ramp-lo))`;
      gEl.appendChild(rect);
      if (n.kind === 'group') gEl.appendChild(svg('rect', { x: 3, y: 3, width: W - 6, height: H - 6, rx: 2, class: 'st-inner' }));
      const l1 = svg('text', { x: 8, y: 17, class: 'st-label' }); l1.textContent = short(n.kind === 'group' ? n.module.split('.').slice(-2).join('.') : n.label); gEl.appendChild(l1);
      const l2 = svg('text', { x: 8, y: 32, class: 'st-subl' }); l2.textContent = short(sub); gEl.appendChild(l2);
      if (mark) { const b = svg('circle', { cx: W - 8, cy: 8, r: 4, class: 'st-badge' }); gEl.appendChild(b); }
      const tip = svg('title'); tip.textContent = what; gEl.appendChild(tip);
      const act = () => {
        if (n.kind === 'group') { openModule(st, n.module, graph.depth); st.selected = null; again(ctx); return; }
        if (!mine) return;
        st.selected = st.selected === n.id ? null : n.id; again(ctx);
      };
      gEl.addEventListener('click', act);
      gEl.addEventListener('keydown', ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); act(); } });
      layer.appendChild(gEl);
    });
    s.appendChild(layer);
    if (st.fit) { s.setAttribute('width', '100%'); s.removeAttribute('height'); s.style.maxWidth = lay.width + 'px'; }   // shrunk to the box, never grown
    const scroll = h('div', 'st-scroll' + (st.fit ? ' fit' : '')); scroll.appendChild(s); box.appendChild(scroll);
    return box;
  }
  function openModule(st, path, depth) {
    if (st.depth == null) st.depth = depth;
    st.close = st.close.filter(p => p !== path);
    // Its parents must be open too for it to show.
    const parts = path.split('.');
    for (let k = 1; k <= parts.length; k++) { const p = parts.slice(0, k).join('.'); st.close = st.close.filter(x => x !== p); if (k > st.depth && !st.open.includes(p)) st.open.push(p); }
  }
  function closeModule(st, path, depth) {
    if (st.depth == null) st.depth = depth;
    st.open = st.open.filter(p => p !== path && !p.startsWith(path + '.'));
    if (path.split('.').length <= st.depth && !st.close.includes(path)) st.close.push(path);
  }

  function legend(overlay) {
    const box = h('div', 'st-legend');
    const ramp = h('span', 'st-ramp'); ramp.setAttribute('aria-hidden', 'true'); box.appendChild(ramp);
    const lo = LOG[overlay.kind] ? 0 : overlay.low;
    box.appendChild(h('span', 'small faint', fmtValue(lo, overlay) + ' to ' + fmtValue(overlay.high, overlay) + (LOG[overlay.kind] ? ', on a logarithmic scale' : '') + (overlay.against ? '; against ' + overlay.against.other_path + (overlay.against.other_run !== overlay.against.run ? ' of run ' + overlay.against.other_run.slice(0, 8) : '') : '') + '. Plain: no value.'));
    box.dataset.kind = overlay.kind;
    return box;
  }

  // ---- A node's details --------------------------------------------------------------------------------------------------
  function details(ctx, graph, n, overlay, status) {
    const { st, m } = ctx, box = h('div', 'st-detail'); box.dataset.id = n.id;
    const head = h('p', 'st-dtitle'); head.appendChild(h('strong', 'mono', n.kind === 'operation' ? n.label : n.id)); if (n.kind === 'operation') head.appendChild(h('span', 'small muted mono', ' ' + n.operation)); box.appendChild(head);
    const dl = h('dl', 'setup iv-facts st-facts');
    const put = (k, v) => { dl.appendChild(h('dt', null, k)); dl.appendChild(h('dd', null, v)); };
    put('Module', (n.module || 'the model itself') + (n.class ? ' · ' + classShort(n.class) : ''));
    put('Takes', valuesText(n.inputs)); put('Gives', valuesText(n.outputs));
    const attrs = Object.entries(n.attributes || {});
    if (attrs.length) put('Attributes', attrs.map(([k, v]) => k + ' = ' + JSON.stringify(v)).join(', '));
    if (overlay) put(COLOURS.find(([k]) => k.startsWith(overlay.kind))[1], fmtValue(valueOf(n, overlay), overlay));
    const mark = markOf(n, status); if (mark) put('Compared', MARK_WORD[mark]);
    box.appendChild(dl);
    if (n.tensors.length) {
      box.appendChild(h('p', 'small muted', 'Its tensors, in the Weights block above:'));
      const ul = h('ul', 'st-tensors');
      for (const name of n.tensors) {
        const t = graph.tensors[name], li = h('li');
        const b = button('linkish mono', name, () => { if (window.LabWeights && window.LabWeights.reveal) window.LabWeights.reveal(m.id, name); });
        b.dataset.key = 'st-tensor-' + name; b.dataset.tensor = name; li.appendChild(b);
        if (t) li.appendChild(h('span', 'small muted', ' ' + shapeText(t.shape) + ' ' + t.dtype + (t.kind !== 'parameter' ? ' · ' + t.kind : '')));
        ul.appendChild(li);
      }
      box.appendChild(ul);
    }
    if (n.module) { const c = button('btn sm', 'Fold ' + n.module, () => { closeModule(st, n.module, graph.depth); st.selected = null; again(ctx); }); c.dataset.key = 'st-fold-here'; box.appendChild(c); }
    return box;
  }

  // ---- The module outline ------------------------------------------------------------------------------------------------
  /** The module tree as a list; a module's row opens or closes it; the children of a closed module are not listed. */
  function outline(ctx, graph, status) {
    const { st } = ctx, open = new Set(graph.open), box = h('div', 'st-outline');
    box.appendChild(h('p', 'small muted', 'Modules'));
    const walk = (node, depth) => {
      const ul = h('ul', 'st-tree');
      for (const child of node.children) {
        const li = h('li'); li.dataset.path = child.path;
        const isOpen = open.has(child.path), mark = status ? status.get(child.path) : null;
        const row = h('div', 'st-row');
        const b = button('st-toggle', null, () => { if (isOpen) closeModule(st, child.path, graph.depth); else openModule(st, child.path, graph.depth); again(ctx); });
        b.dataset.key = 'st-mod-' + child.path; b.setAttribute('aria-expanded', String(isOpen));
        b.setAttribute('aria-label', (isOpen ? 'Fold ' : 'Open ') + child.path);
        b.appendChild(h('span', 'st-caret', isOpen ? '▾' : '▸'));
        b.appendChild(h('span', 'mono', child.path.split('.').pop()));
        row.appendChild(b);
        row.appendChild(h('span', 'small muted', classShort(child.class) + ' · ' + num(child.parameters)));
        if (mark && mark !== 'same') { const s = h('span', 'wts-mark st-m-' + mark, { added: 'only here', missing: 'only there', changed: 'changed' }[mark]); row.appendChild(s); }
        li.appendChild(row);
        if (isOpen && child.children.length && depth < 64) li.appendChild(walk(child, depth + 1));
        ul.appendChild(li);
      }
      return ul;
    };
    box.appendChild(graph.modules.children.length ? walk(graph.modules, 1) : h('p', 'small faint', 'The model has no modules inside it.'));
    return box;
  }

  return { block };
})();
