'use strict';
// Model lineage, from the mockup's tree.js: one graph built from the project's
// map, rendered as a horizontal lane map (with the track beneath it when
// asked) and as a vertical list (git-graph style) under it. A model's lane
// comes from what it was derived from; solid lines are derivations (always)
// and inputs (of the selected model); the faint line is training order only
// and makes no ancestry claim; dashed arcs are the authored comparisons of
// the selected model.
// Both renderers return select() and scrollTo() so a selection change never
// rebuilds the view.
window.LabTree = (() => {
  const P = window.TuldokProject, C = window.LabCharts, el = C.el, h = C.h;
  const reduced = () => window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const SHORT = 16;   // characters of a short label shown on the map (spec-w1 section 1)
  const shortOf = m => m.short ? m.short.slice(0, SHORT) : null;
  const nameOf = m => (m.short ? m.short + ' · ' : '') + m.title;
  const refName = m => m.short || (m.title.length > 24 ? m.title.slice(0, 23) + '…' : m.title);
  // A short run of highlights from the previous selection to the new one, so
  // the eye can follow the change. Never longer than ~450 ms; skipped when the
  // viewer prefers reduced motion.
  function walker() {
    let timers = [];
    return (ordered, fromId, toId, mark) => {
      for (const t of timers) clearTimeout(t); timers = [];
      if (reduced() || !fromId || !toId || fromId === toId) return;
      const i0 = ordered.indexOf(fromId), i1 = ordered.indexOf(toId); if (i0 < 0 || i1 < 0) return;
      let steps = i1 > i0 ? ordered.slice(i0 + 1, i1) : ordered.slice(i1 + 1, i0).reverse();
      if (steps.length > 22) { const out = []; for (let k = 0; k < 22; k++) out.push(steps[Math.round(k * (steps.length - 1) / 21)]); steps = out; }
      const delay = Math.min(34, 420 / Math.max(1, steps.length));
      steps.forEach((id, k) => { timers.push(setTimeout(() => { mark(id, true); timers.push(setTimeout(() => mark(id, false), 170)); }, k * delay)); });
    };
  }

  /**
   * The graph of a shaped map: nodes in section order with their index t and
   * lane, families (the models derived from one model share a lane, lanes
   * reused once free), the order line (consecutive models of the main lane
   * whose training dates go forward), derivations, inputs and comparisons.
   */
  function build(shaped) {
    const nodes = shaped.models.map((m, t) => Object.assign({}, m, { t, lane: 0 }));
    const byId = new Map(nodes.map(m => [m.id, m]));
    const sections = []; let t = 0;
    for (const s of shaped.sections) { sections.push({ id: s.id, label: s.title, up: s.up, loose: !!s.loose, start: t, end: t + s.models.length - 1, count: s.models.length }); for (const m of s.models) byId.get(m.id).section = sections.length - 1; t += s.models.length; }
    const byParent = new Map();
    for (const m of nodes) if (m.parent && byId.has(m.parent)) { if (!byParent.has(m.parent)) byParent.set(m.parent, []); byParent.get(m.parent).push(m.id); }
    const families = [...byParent].map(([parent, children]) => {
      const ts = children.map(id => byId.get(id).t).concat([byId.get(parent).t]);
      return { parent, children, start: Math.min(...ts), end: Math.max(...ts), lane: 0 };
    }).sort((a, b) => a.start - b.start || a.end - b.end);
    const laneLast = [Infinity];
    for (const f of families) {
      let lane = 1; while (laneLast[lane] !== undefined && laneLast[lane] >= f.start) lane++;
      f.lane = lane; laneLast[lane] = f.end;
      for (const id of f.children) byId.get(id).lane = lane;
    }
    // The order line joins consecutive models of the main lane whose training dates go forward, within a
    // section or across neighbouring sections of the same parent group (as the mockup's checkpoint line did).
    const sameParent = (a, b) => a === b || (Math.abs(a - b) === 1 && sections[a].up.length > 0 && sections[a].up.join('/') === sections[b].up.join('/'));
    const edges = []; let prev = null;
    for (const m of nodes) {
      if (m.lane !== 0) continue;
      if (prev && prev.trainedAt && m.trainedAt && prev.trainedAt <= m.trainedAt && sameParent(prev.section, m.section)) edges.push({ from: prev.id, to: m.id, kind: 'sequence' });
      prev = m;
    }
    for (const m of nodes) if (m.parent && byId.has(m.parent)) edges.push({ from: m.parent, to: m.id, kind: 'derivation' });
    for (const e of shaped.inputs) edges.push({ from: e.from, to: e.to, kind: 'input' });
    for (const r of shaped.comparisons) edges.push({ from: r.from, to: r.to, kind: 'comparison', explanation: r.explanation, excerpt: r.excerpt });
    const seqSpan = new Array(nodes.length).fill(false);
    for (const e of edges) if (e.kind === 'sequence') for (let k = byId.get(e.from).t + 1; k < byId.get(e.to).t; k++) seqSpan[k] = true;
    const seqIn = new Set(edges.filter(e => e.kind === 'sequence').map(e => e.to));
    const seqOut = new Set(edges.filter(e => e.kind === 'sequence').map(e => e.from));
    return { nodes, byId, edges, sections, families, laneCount: laneLast.length, seqIn, seqOut, seqSpan, track: shaped.track, scale: shaped.trackScale };
  }
  function related(graph, id) { const out = new Set(); for (const e of graph.edges) if (e.kind !== 'sequence' && (e.from === id || e.to === id)) out.add(e.from === id ? e.to : e.from); return out; }
  function comparisons(graph, id) { return graph.edges.filter(e => e.kind === 'comparison' && (e.from === id || e.to === id)).map(e => ({ other: e.from === id ? e.to : e.from, explanation: e.explanation, excerpt: e.excerpt })); }
  function matches(m, q) {
    if (!q) return true; q = q.toLowerCase();
    return [m.title, m.short, m.description, m.groupTitle, m.id].some(s => s && s.toLowerCase().includes(q));
  }
  const visibleFor = (kinds, query) => m => (!kinds || kinds.has(m.kind)) && matches(m, query);
  const trackText = (graph, m) => m.value == null ? 'no value' : C.fmtSci(m.value) + P.units(graph.track);

  // ---- Vertical list -------------------------------------------------------
  function renderList(container, graph, { selected = null, onSelect = () => {}, kinds = null, query = '' } = {}) {
    container.textContent = '';
    const laneW = 16, pad = 10, gw = pad * 2 + laneW * Math.max(1, graph.laneCount - 1) + 8, rowH = 30;
    const shortest = Math.max(3, ...graph.nodes.map(m => (shortOf(m) || '').length));
    container.style.setProperty('--graphw', gw + 'px');
    container.style.setProperty('--ckw', Math.ceil(shortest * 7 + 4) + 'px');
    const ul = h('ul', 'tree-list'); ul.setAttribute('role', 'listbox'); ul.setAttribute('aria-label', 'Models by section, in training order');
    const active = t => graph.families.filter(f => f.start < t && t <= f.end);
    const laneX = l => pad + 4 + l * laneW;
    const visible = visibleFor(kinds, query);
    const rows = new Map(); let shown = 0;
    for (const s of graph.sections) {
      const list = graph.nodes.slice(s.start, s.end + 1).filter(visible);
      if (!list.length) continue;
      const li = h('li'); const head = h('div', 'tsect' + (s.loose ? ' loose' : ''));
      const hs = el('svg', { width: gw, height: 20, 'aria-hidden': 'true' });
      for (const f of active(s.start)) hs.appendChild(el('line', { x1: laneX(f.lane), y1: 0, x2: laneX(f.lane), y2: 20, class: 'lanek lk-' + graph.byId.get(f.children[0]).kind }));
      if (graph.seqIn.has(graph.nodes[s.start].id) || graph.seqSpan[s.start]) hs.appendChild(el('line', { x1: laneX(0), y1: 0, x2: laneX(0), y2: 20, class: 'lane0' }));
      head.appendChild(hs);
      const title = h('h3'); if (s.up.length) title.appendChild(h('span', 'up', s.up.join(' / ') + ' / ')); title.appendChild(document.createTextNode(s.label)); title.title = s.up.concat([s.label]).join(' / '); head.appendChild(title);
      const fam = graph.families.filter(f => graph.byId.get(f.parent).section === graph.sections.indexOf(s));
      head.appendChild(h('span', 'sum', list.length + (list.length === s.count ? '' : ' of ' + s.count) + (fam.length ? ' · ' + fam.map(f => f.children.length + ' from ' + refName(graph.byId.get(f.parent))).join(', ') : '')));
      li.appendChild(head); ul.appendChild(li);
      for (const m of list) {
        shown++;
        const row = h('li'); const b = h('button', 'trow'); b.type = 'button'; b.setAttribute('role', 'option'); b.setAttribute('aria-selected', 'false'); b.dataset.id = m.id;
        const svg = el('svg', { width: gw, height: rowH, 'aria-hidden': 'true' });
        const x0 = laneX(0), mid = rowH / 2;
        if (graph.seqSpan[m.t]) svg.appendChild(el('line', { x1: x0, y1: 0, x2: x0, y2: rowH, class: 'lane0' }));
        if (graph.seqIn.has(m.id)) svg.appendChild(el('line', { x1: x0, y1: 0, x2: x0, y2: mid, class: 'lane0' }));
        if (graph.seqOut.has(m.id)) svg.appendChild(el('line', { x1: x0, y1: mid, x2: x0, y2: rowH, class: 'lane0' }));
        for (const f of active(m.t)) {
          const k = 'lanek lk-' + graph.byId.get(f.children[0]).kind, x = laneX(f.lane), isChild = f.children.includes(m.id);
          svg.appendChild(el('line', { x1: x, y1: 0, x2: x, y2: isChild && m.t === f.end ? mid : rowH, class: k }));
        }
        for (const f of graph.families.filter(f => f.parent === m.id)) { const x = laneX(f.lane), k = 'lanek lk-' + graph.byId.get(f.children[0]).kind; svg.appendChild(el('path', { d: `M${laneX(m.lane)},${mid} C${laneX(m.lane)},${rowH} ${x},${mid} ${x},${rowH}`, class: k })); }
        const dot = el('circle', { cx: laneX(m.lane), cy: mid, r: 5, class: 'dot ' + m.kind });
        svg.appendChild(dot); b.appendChild(svg);
        b.appendChild(h('span', 'ck', shortOf(m) || '—'));
        b.appendChild(h('span', 'nm', m.title));
        b.appendChild(h('span', 'pu', m.description));
        b.appendChild(h('span', 'chip ' + m.kind, P.kindLabel(m.kind)));
        const bar = h('span', 'mbar' + (m.value == null ? ' none' : ''));
        if (m.value != null && graph.scale) { const fill = h('i'); fill.style.width = Math.round(graph.scale.good(m.value) * 100) + '%'; bar.appendChild(fill); }
        bar.title = graph.track ? P.trackName(graph.track) + ': ' + trackText(graph, m) : 'The project names no track';
        b.appendChild(bar);
        b.appendChild(h('span', 'ms' + (m.value == null ? ' none' : ''), graph.track ? (m.value == null ? '—' : C.fmtSci(m.value)) : ''));
        b.title = nameOf(m);
        b.addEventListener('click', () => onSelect(m.id));
        row.appendChild(b); ul.appendChild(row); rows.set(m.id, { b, dot });
      }
    }
    ul.addEventListener('keydown', e => { if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return; const opts = [...ul.querySelectorAll('.trow')]; const i = opts.indexOf(document.activeElement); if (i < 0) return; const n = opts[i + (e.key === 'ArrowDown' ? 1 : -1)]; if (n) { n.focus(); e.preventDefault(); } });
    container.appendChild(ul);
    if (!shown) container.appendChild(h('p', 'empty', 'No models match.'));
    let current = null; const walk = walker(); const order = [...rows.keys()];
    const api = {
      shown,
      select(id) { const rel = id ? related(graph, id) : new Set(); for (const [mid, r] of rows) { r.b.setAttribute('aria-selected', String(mid === id)); r.b.classList.toggle('related', rel.has(mid)); r.dot.classList.toggle('sel', mid === id); } walk(order, current, id, (mid, on) => { const r = rows.get(mid); if (r) r.b.classList.toggle('walk', on); }); current = id; },
      scrollTo(id, smooth) { const r = rows.get(id); if (!r) return; const box = r.b.getBoundingClientRect(), frame = container.getBoundingClientRect(); const top = container.scrollTop + box.top - frame.top - container.clientHeight / 2 + box.height / 2; container.scrollTo({ top: Math.max(0, top), behavior: smooth && !reduced() ? 'smooth' : 'auto' }); }
    };
    api.select(selected); return api;
  }

  // ---- Horizontal lane map, with the track beneath when asked ----------------
  const labelWidth = text => text.length * 7 + 24;   // 12px semibold section titles, with room
  const nodeLabelWidth = text => text.length * 6.4;  // 10.5px mono
  function renderMap(container, graph, { selected = null, onSelect = () => {}, kinds = null, query = '', zoom = 1, track = false } = {}) {
    container.textContent = '';
    const dx = 30, left = 70, top = 44, laneH = 52, plotH = 120;
    // Each section is as wide as its models or its title, whichever is wider.
    const sx = []; let cursor = left - dx / 2;
    for (const s of graph.sections) { sx.push(cursor); cursor += Math.max(s.count * dx, labelWidth(s.label)); }
    const xOf = new Map(graph.nodes.map(m => [m.id, sx[m.section] + dx / 2 + (m.t - graph.sections[m.section].start) * dx]));
    const W = cursor + 60;
    const lanesH = top + 20 + graph.laneCount * laneH;
    const showTrack = track && graph.track && graph.scale;
    const trackTop = lanesH + 40, H = showTrack ? trackTop + plotH + 34 : lanesH + 30;
    const trackLabel = graph.track ? P.trackName(graph.track) + ', ' + P.better(graph.track) : '';
    const ty = v => trackTop + (1 - graph.scale.at(v)) * plotH;
    const x = m => xOf.get(m.id), y = m => top + 20 + m.lane * laneH;
    const inner = h('div', 'inner'); inner.style.width = W + 'px'; inner.style.height = H + 'px'; inner.style.transform = 'scale(' + zoom + ')';
    const svg = el('svg', { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'Model lineage: sections left to right in training order, branches in lanes' + (showTrack ? ', with ' + trackLabel + ' beneath' : '') });
    const visible = visibleFor(kinds, query);
    graph.sections.forEach((s, i) => {
      const x1 = sx[i], width = (sx[i + 1] || cursor) - x1;
      svg.appendChild(el('line', { x1, y1: 8, x2: x1, y2: H - 8, class: 'band' }));
      const t = el('text', { x: x1 + 8, y: 22, class: 'bandlabel' + (s.loose ? ' loose' : '') }, s.label); t.appendChild(el('title', {}, s.up.concat([s.label]).join(' / '))); svg.appendChild(t);
      if (showTrack) {
        if (i === 0 || width >= labelWidth(trackLabel) * 0.85) svg.appendChild(el('text', { x: x1 + 8, y: trackTop - 14, class: 'ttitle' }, trackLabel));
        if (i === 0 || width >= 60) for (const v of graph.scale.ticks) svg.appendChild(el('text', { x: x1 + 8, y: ty(v) - 3, class: 'tlabel' }, graph.scale.label(v)));
      }
    });
    for (const e of graph.edges) { if (e.kind !== 'sequence') continue; const a = graph.byId.get(e.from), b = graph.byId.get(e.to); svg.appendChild(el('line', { x1: x(a), y1: y(a), x2: x(b), y2: y(b), class: 'seq' })); }
    for (const f of graph.families) {
      const p = graph.byId.get(f.parent), kids = f.children.map(id => graph.byId.get(id)), k = kids[0].kind, ly = y(kids[0]);
      const x0 = x(p), forward = kids.some(c => x(c) > x0), xb = x0 + (forward ? 1 : -1) * dx * 1.6;
      const xs = kids.map(x).concat([xb]), a = Math.min(...xs), b = Math.max(...xs);
      svg.appendChild(el('path', { d: `M${x0},${y(p)} C${x0 + (xb - x0) * 0.4},${y(p)} ${xb - (xb - x0) * 0.4},${ly} ${xb},${ly} M${a},${ly} L${b},${ly}`, class: 'der lk-' + k, 'data-family': f.parent }));
      svg.appendChild(el('text', { x: Math.max(xb, a) + 4, y: ly - 7, class: 'lanelabel' }, 'from ' + refName(p)));
    }
    const gInp = el('g', { class: 'inp-layer' }); svg.appendChild(gInp);
    const gCmp = el('g', { class: 'cmp-layer' }); svg.appendChild(gCmp);
    const trackPts = new Map();
    if (showTrack) {
      for (const v of graph.scale.ticks) svg.appendChild(el('line', { x1: left - 16, y1: ty(v), x2: W - 20, y2: ty(v), class: 'tgrid' }));
      let d = '', prev = null;
      for (const m of graph.nodes) { if (m.lane !== 0 || m.value == null) continue; d += (prev && prev.section === m.section && m.t - prev.t <= 3 ? 'L' : 'M') + x(m) + ',' + ty(m.value) + ' '; prev = m; }
      if (d) svg.appendChild(el('path', { d: d.trim(), class: 'tline' }));
      for (const m of graph.nodes) {
        if (m.value == null) continue;
        const c = el('circle', { cx: x(m), cy: ty(m.value), r: 3.5, class: 'tpt ' + m.kind + (visible(m) ? '' : ' dim'), tabindex: 0, role: 'button', 'aria-label': refName(m) + ', ' + trackText(graph, m) });
        c.appendChild(el('title', {}, nameOf(m) + ' · ' + trackText(graph, m)));
        c.addEventListener('click', () => onSelect(m.id)); c.addEventListener('keydown', ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); onSelect(m.id); } });
        svg.appendChild(c); trackPts.set(m.id, c);
      }
    }
    const host = container.parentElement; host.style.position = 'relative';
    host.querySelectorAll(':scope > .minimap, :scope > .tip').forEach(n => n.remove());
    const tip = C.tooltip(host);
    const at = ev => { const r = host.getBoundingClientRect(); return [ev.clientX - r.left, ev.clientY - r.top]; };
    const showTip = (m, ev) => {
      const rows = [{ b: nameOf(m) }];
      rows.push(graph.track ? { v: m.value == null ? '—' : C.fmtSci(m.value) + P.units(graph.track), l: P.trackName(graph.track) } : { l: 'The project names no track' });
      rows.push({ l: m.trainedAt ? 'trained ' + P.day(m.trainedAt) : 'no training date' });
      rows.push({ v: P.kindLabel(m.kind), l: m.parent ? 'from ' + refName(graph.byId.get(m.parent)) : '' });
      const [px, py] = at(ev); tip.show(px, py, rows);
    };
    const nodeEls = new Map();
    // A node's short label is shown when it does not crowd the last label shown in its lane.
    const laneLabelEnd = new Map(), labelled = new Set();
    for (const m of graph.nodes) {
      const text = shortOf(m); if (!text) continue;
      const w = nodeLabelWidth(text), last = laneLabelEnd.get(m.lane);
      if (last === undefined || x(m) - w / 2 >= last + 14) { labelled.add(m.id); laneLabelEnd.set(m.lane, x(m) + w / 2); }
    }
    for (const m of graph.nodes) {
      const g = el('g', { class: 'node ' + m.kind + (visible(m) ? '' : ' dim'), tabindex: 0, role: 'button', 'aria-label': nameOf(m), 'data-id': m.id });
      g.appendChild(el('rect', { x: x(m) - 14, y: y(m) - 14, width: 28, height: 28, class: 'hitr' }));
      g.appendChild(el('circle', { cx: x(m), cy: y(m), r: 5.5 }));
      const text = shortOf(m);
      const lbl = text ? el('text', { x: x(m), y: y(m) + 18, class: 'nl' + (labelled.has(m.id) ? '' : ' off') }, text) : null;
      if (lbl) g.appendChild(lbl);
      g.addEventListener('click', () => onSelect(m.id));
      g.addEventListener('keydown', ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); onSelect(m.id); } });
      g.addEventListener('pointerenter', ev => showTip(m, ev)); g.addEventListener('pointermove', ev => showTip(m, ev)); g.addEventListener('pointerleave', () => tip.hide());
      g.addEventListener('focus', () => { const r = g.getBoundingClientRect(); showTip(m, { clientX: r.left + 14, clientY: r.top + 14 }); }); g.addEventListener('blur', () => tip.hide());
      svg.appendChild(g); nodeEls.set(m.id, { g, lbl });
    }
    inner.appendChild(svg); container.appendChild(inner);
    const mini = h('div', 'minimap'); mini.setAttribute('role', 'img'); mini.setAttribute('aria-label', 'Whole map; click to move');
    const ms = el('svg', { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'none' });
    for (const m of graph.nodes) ms.appendChild(el('circle', { cx: x(m), cy: y(m), r: 7, class: 'd' }));
    const vp = el('rect', { class: 'vp', x: 0, y: 0, width: 10, height: 10 }); ms.appendChild(vp); mini.appendChild(ms); host.appendChild(mini);
    const sync = () => { vp.setAttribute('x', container.scrollLeft / zoom); vp.setAttribute('y', container.scrollTop / zoom); vp.setAttribute('width', container.clientWidth / zoom); vp.setAttribute('height', container.clientHeight / zoom); };
    container.addEventListener('scroll', sync); sync();
    new ResizeObserver(sync).observe(container);
    mini.addEventListener('click', ev => { const r = mini.getBoundingClientRect(); container.scrollTo({ left: ((ev.clientX - r.left) / r.width) * W * zoom - container.clientWidth / 2, top: ((ev.clientY - r.top) / r.height) * H * zoom - container.clientHeight / 2, behavior: reduced() ? 'auto' : 'smooth' }); });
    let current = null; const walk = walker(); const order = graph.nodes.map(m => m.id);
    const api = {
      select(id) {
        const sel = graph.byId.get(id);
        gCmp.textContent = '';
        walk(order, current, id, (mid, on) => { const n = nodeEls.get(mid); if (n) n.g.classList.toggle('walk', on); }); current = id;
        for (const [mid, n] of nodeEls) {
          const m = graph.byId.get(mid), on = mid === id;
          n.g.classList.toggle('sel', on); n.g.querySelector('circle').setAttribute('r', on ? 7 : 5.5);
          const fam = !!sel && (m.parent === id || mid === sel.parent || (!!sel.parent && m.parent === sel.parent));
          if (n.lbl) n.lbl.classList.toggle('off', !(on || fam || labelled.has(mid)));
          n.g.classList.toggle('kin', fam && !on);
        }
        for (const p of svg.querySelectorAll('.der')) p.classList.toggle('hot', !!sel && (p.dataset.family === id || p.dataset.family === sel.parent));
        // Inputs are drawn for the selected model only, so that the map stays quiet (63 in the lab's project).
        gInp.textContent = '';
        if (sel) for (const e of graph.edges) if (e.kind === 'input' && (e.from === id || e.to === id)) {
          const a = graph.byId.get(e.from), b = graph.byId.get(e.to), lift = Math.min(40, 10 + Math.abs(x(b) - x(a)) / 20);
          gInp.appendChild(el('path', { d: `M${x(a)},${y(a)} C${x(a)},${y(a) + lift} ${x(b)},${y(b) + lift} ${x(b)},${y(b)}`, class: 'inp' }));
        }
        for (const [mid, c] of trackPts) c.classList.toggle('sel', mid === id);
        if (sel) for (const e of graph.edges) if (e.kind === 'comparison' && (e.from === id || e.to === id)) {
          const a = graph.byId.get(e.from), b = graph.byId.get(e.to), other = e.from === id ? b : a;
          const path = el('path', { d: `M${x(a)},${y(a)} C${x(a)},${Math.min(y(a), y(b)) - 34} ${x(b)},${Math.min(y(a), y(b)) - 34} ${x(b)},${y(b)}`, class: 'cmp', tabindex: 0, role: 'link', 'aria-label': 'Compared with ' + refName(other) });
          const said = e.excerpt || e.explanation || '';
          path.appendChild(el('title', {}, 'Compared with ' + nameOf(other) + ': ' + said));
          const show = ev => { const [px, py] = at(ev); tip.show(px, py, [{ b: 'Compared with ' + nameOf(other) }, { l: said.slice(0, 160) + (said.length > 160 ? '…' : '') }]); };
          path.addEventListener('pointerenter', show); path.addEventListener('pointermove', show); path.addEventListener('pointerleave', () => tip.hide());
          path.addEventListener('click', () => onSelect(other.id)); path.addEventListener('keydown', ev => { if (ev.key === 'Enter') onSelect(other.id); });
          gCmp.appendChild(path);
        }
      },
      scrollTo(id, smooth) { const m = graph.byId.get(id); if (!m) return; container.scrollTo({ left: x(m) * zoom - container.clientWidth / 2, top: Math.max(0, y(m) * zoom - container.clientHeight / 2), behavior: smooth && !reduced() ? 'smooth' : 'auto' }); }
    };
    api.select(selected); return api;
  }
  return { build, renderList, renderMap, related, comparisons, matches, nameOf, refName };
})();
