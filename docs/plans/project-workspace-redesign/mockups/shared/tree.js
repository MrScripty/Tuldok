'use strict';
// Model lineage: one graph built from the portfolio plus any planned models,
// rendered as a vertical list (git-graph style) or a horizontal lane map.
// Solid lanes are derivations read from the model cards; the faint line is
// checkpoint order only; dashed edges are authored comparisons for the
// selected fit. Both renderers return select() and scrollTo() so a selection
// change never rebuilds the view.
window.LabTree = (() => {
  const GROUP_ORDER = ['pressure-inputs','pressure-stability','pressure-multigrid','pressure-direction','pressure-variants','pressure-successors','pressure-other','full_state_generator','pressure_head_component','pressure_component','pressure_request_component','guided_pressure_component','guided_shared_component','full_state_correction_component','full_state_readout_component','recurrent_transport_component','transport_component','viscosity_component'];
  const gi = id => { const i = GROUP_ORDER.indexOf(id); return i < 0 ? 99 : i; };
  const svgNS = 'http://www.w3.org/2000/svg';
  const el = (name, attrs = {}, text) => { const n = document.createElementNS(svgNS, name); for (const k in attrs) n.setAttribute(k, attrs[k]); if (text !== undefined) n.textContent = text; return n; };
  const h = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
  const reduced = () => window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
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

  function build(models, relationships) {
    const nodes = models.map(m => Object.assign({}, m)).sort((a, b) => gi(a.group) - gi(b.group) || ((a.n ?? 9999) - (b.n ?? 9999)) || a.label.localeCompare(b.label));
    nodes.forEach((m, i) => { m.t = i; });
    const byId = new Map(nodes.map(m => [m.id, m]));
    const families = new Map(); const laneLast = [0];
    for (const m of nodes) {
      const p = m.parents.find(id => byId.has(id));
      m.parent = p || null;
      if (!p) { m.lane = 0; continue; }
      if (!families.has(p)) {
        let lane = 1; const pt = byId.get(p).t;
        while (laneLast[lane] !== undefined && laneLast[lane] >= pt) lane++;
        families.set(p, { lane, parent: p, children: [], start: pt, end: pt });
      }
      const f = families.get(p); m.lane = f.lane; f.children.push(m.id); f.end = m.t; laneLast[f.lane] = m.t;
    }
    const edges = []; let prev = null;
    for (const m of nodes) {
      if (m.lane !== 0) continue;
      if (prev && ((prev.n != null && m.n != null) || prev.group === m.group)) edges.push({ from: prev.id, to: m.id, kind: 'sequence' });
      prev = m;
    }
    for (const m of nodes) if (m.parent) edges.push({ from: m.parent, to: m.id, kind: 'derivation' });
    for (const r of relationships) if (byId.has(r.from) && byId.has(r.to)) edges.push({ from: r.from, to: r.to, kind: 'comparison', explanation: r.explanation, excerpt: r.excerpt });
    const sections = [];
    for (const m of nodes) { const s = sections[sections.length - 1]; if (!s || s.group !== m.group) sections.push({ group: m.group, label: m.groupLabel, start: m.t, end: m.t, count: 1 }); else { s.end = m.t; s.count++; } }
    const seqSpan = new Array(nodes.length).fill(false);
    for (const e of edges) if (e.kind === 'sequence') for (let t = byId.get(e.from).t + 1; t < byId.get(e.to).t; t++) seqSpan[t] = true;
    const seqIn = new Set(edges.filter(e => e.kind === 'sequence').map(e => e.to));
    const seqOut = new Set(edges.filter(e => e.kind === 'sequence').map(e => e.from));
    return { nodes, byId, edges, sections, families: [...families.values()], laneCount: laneLast.length, seqIn, seqOut, seqSpan };
  }
  function related(graph, id) { const out = new Set(); for (const e of graph.edges) if (e.kind !== 'sequence' && (e.from === id || e.to === id)) out.add(e.from === id ? e.to : e.from); return out; }
  function comparisons(graph, id) { return graph.edges.filter(e => e.kind === 'comparison' && (e.from === id || e.to === id)).map(e => ({ other: e.from === id ? e.to : e.from, explanation: e.explanation, excerpt: e.excerpt })); }
  function metricFill(v) { if (v == null || !(v > 0)) return 0; const f = (Math.log10(1) - Math.log10(Math.max(v, 1e-4))) / 4; return Math.max(0, Math.min(1, f)); }
  function matches(m, q) { if (!q) return true; q = q.toLowerCase(); return m.label.toLowerCase().includes(q) || (m.alias || '').toLowerCase().includes(q) || (m.ck || '').toLowerCase().includes(q) || m.groupLabel.toLowerCase().includes(q); }
  function kindLabel(k) { return { training: 'Training policy', architecture: 'Architecture', refinement: 'Refinement', composition: 'Component' }[k] || k; }
  function fmtSci(v) { if (v == null) return '—'; if (v >= 0.01) return v.toFixed(3); const e = Math.floor(Math.log10(v)); return (v / Math.pow(10, e)).toFixed(2) + 'e' + e; }

  // ---- Vertical list -------------------------------------------------------
  function renderList(container, graph, { selected = null, onSelect = () => {}, kinds = null, query = '', barLabel = 'Accuracy', unit = 'ms' } = {}) {
    container.textContent = '';
    const laneW = 16, pad = 10, gw = pad * 2 + laneW * Math.max(1, graph.laneCount - 1) + 8, rowH = 30;
    container.style.setProperty('--graphw', gw + 'px');
    const ul = h('ul', 'tree-list'); ul.setAttribute('role', 'listbox'); ul.setAttribute('aria-label', 'Models in checkpoint order');
    const active = t => graph.families.filter(f => f.start < t && t <= f.end);
    const laneX = l => pad + 4 + l * laneW;
    const visible = m => (!kinds || kinds.has(m.kind)) && matches(m, query);
    const rows = new Map(); let shown = 0;
    for (const s of graph.sections) {
      const list = graph.nodes.slice(s.start, s.end + 1).filter(visible);
      if (!list.length) continue;
      const li = h('li'); const head = h('div', 'tsect');
      const hs = el('svg', { width: gw, height: 20, 'aria-hidden': 'true' });
      for (const f of active(s.start)) hs.appendChild(el('line', { x1: laneX(f.lane), y1: 0, x2: laneX(f.lane), y2: 20, class: 'lanek lk-' + graph.byId.get(f.children[0]).kind }));
      if (graph.seqIn.has(graph.nodes[s.start].id) || graph.seqSpan[s.start]) hs.appendChild(el('line', { x1: laneX(0), y1: 0, x2: laneX(0), y2: 20, class: 'lane0' }));
      head.appendChild(hs); head.appendChild(h('h3', null, s.label));
      const fam = graph.families.filter(f => graph.byId.get(f.parent).t >= s.start && graph.byId.get(f.parent).t <= s.end);
      head.appendChild(h('span', 'sum', list.length + (list.length === s.count ? '' : ' of ' + s.count) + (fam.length ? ' · ' + fam.map(f => f.children.length + ' from ' + (graph.byId.get(f.parent).ck || graph.byId.get(f.parent).short)).join(', ') : '')));
      li.appendChild(head); ul.appendChild(li);
      for (const m of list) {
        shown++;
        const row = h('li'); const b = h('button', 'trow' + (m.planned ? ' planned' : '')); b.type = 'button'; b.setAttribute('role', 'option'); b.setAttribute('aria-selected', 'false'); b.dataset.id = m.id; b.id = 'tree-' + m.id;
        const svg = el('svg', { width: gw, height: rowH, 'aria-hidden': 'true' });
        const x0 = laneX(0), mid = rowH / 2;
        if (graph.seqSpan[m.t]) svg.appendChild(el('line', { x1: x0, y1: 0, x2: x0, y2: rowH, class: 'lane0' }));
        if (graph.seqIn.has(m.id)) svg.appendChild(el('line', { x1: x0, y1: 0, x2: x0, y2: mid, class: 'lane0' }));
        if (graph.seqOut.has(m.id)) svg.appendChild(el('line', { x1: x0, y1: mid, x2: x0, y2: rowH, class: 'lane0' }));
        for (const f of active(m.t)) {
          const k = 'lanek lk-' + graph.byId.get(f.children[0]).kind, x = laneX(f.lane), isChild = f.children.includes(m.id);
          svg.appendChild(el('line', { x1: x, y1: 0, x2: x, y2: isChild ? mid : rowH, class: k }));
          if (isChild && m.t < f.end) svg.appendChild(el('line', { x1: x, y1: mid, x2: x, y2: rowH, class: k }));
        }
        for (const f of graph.families.filter(f => f.parent === m.id)) { const x = laneX(f.lane), k = 'lanek lk-' + graph.byId.get(f.children[0]).kind; svg.appendChild(el('path', { d: `M${x0},${mid} C${x0},${rowH} ${x},${mid} ${x},${rowH}`, class: k })); }
        const dot = el('circle', { cx: laneX(m.lane), cy: mid, r: 5, class: 'dot ' + m.kind + (m.planned ? ' planned' : '') });
        svg.appendChild(dot); b.appendChild(svg);
        b.appendChild(h('span', 'ck', m.planned ? 'new' : (m.ck || '—')));
        b.appendChild(h('span', 'nm', m.short));
        b.appendChild(h('span', 'pu', m.planned ? (m.setup && m.setup.change || 'not configured') : (m.purpose || '')));
        b.appendChild(h('span', 'chip ' + m.kind, m.planned ? (m.setup && m.setup.prepared ? 'prepared' : 'planned') : kindLabel(m.kind)));
        const bar = h('span', 'mbar'); const fill = h('i'); fill.style.width = Math.round(metricFill(m.worstP) * 100) + '%'; bar.appendChild(fill); bar.title = m.worstP == null ? 'No benchmark' : barLabel + ' ' + fmtSci(m.worstP); b.appendChild(bar);
        b.appendChild(h('span', 'ms', m.ms == null ? '' : m.ms.toFixed(2) + ' ' + unit));
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
      scrollTo(id, smooth) { const r = rows.get(id); if (!r) return; r.b.scrollIntoView({ block: 'center', behavior: smooth && !reduced() ? 'smooth' : 'auto' }); }
    };
    api.select(selected); return api;
  }

  // ---- Horizontal lane map, with an optional accuracy track -----------------
  function renderMap(container, graph, { selected = null, onSelect = () => {}, kinds = null, query = '', zoom = 1, track = false, metric = 'worstP', trackLabel = 'Accuracy, lower is better', unit = 'ms', timeId = 'ms' } = {}) {
    container.textContent = '';
    const dx = 30, left = 70, top = 44, laneH = 52, plotH = 120;
    const W = left + graph.nodes.length * dx + 60;
    const lanesH = top + 20 + graph.laneCount * laneH;
    const trackTop = lanesH + 40, H = track ? trackTop + plotH + 34 : lanesH + 30;
    const has = m => m[metric] != null && m[metric] > 0;
    const ty = v => trackTop + (0 - Math.log10(Math.min(Math.max(v, 1e-4), 1))) / 4 * plotH;
    const x = m => left + m.t * dx, y = m => top + 20 + m.lane * laneH;
    const inner = h('div', 'inner'); inner.style.width = W + 'px'; inner.style.height = H + 'px'; inner.style.transform = 'scale(' + zoom + ')';
    const svg = el('svg', { width: W, height: H, viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': 'Model lineage: checkpoints left to right, branches in lanes' + (track ? ', with ' + trackLabel + ' beneath' : '') });
    const visible = m => (!kinds || kinds.has(m.kind)) && matches(m, query);
    for (const s of graph.sections) {
      const x1 = left + s.start * dx - dx / 2;
      svg.appendChild(el('line', { x1, y1: 8, x2: x1, y2: H - 8, class: 'band' }));
      svg.appendChild(el('text', { x: x1 + 8, y: 22, class: 'bandlabel' }, s.label));
      if (track) { svg.appendChild(el('text', { x: x1 + 8, y: trackTop - 14, class: 'ttitle' }, trackLabel)); for (const v of [1, 0.01, 0.0001]) svg.appendChild(el('text', { x: x1 + 8, y: ty(v) - 3, class: 'tlabel' }, v >= 0.01 ? String(v) : '1e' + Math.log10(v))); }
    }
    for (const e of graph.edges) { if (e.kind !== 'sequence') continue; const a = graph.byId.get(e.from), b = graph.byId.get(e.to); svg.appendChild(el('line', { x1: x(a), y1: y(a), x2: x(b), y2: y(b), class: 'seq' })); }
    for (const f of graph.families) {
      const p = graph.byId.get(f.parent), last = graph.byId.get(f.children[f.children.length - 1]), ly = y(graph.byId.get(f.children[0])), k = graph.byId.get(f.children[0]).kind;
      const x0 = x(p), xb = x0 + dx * 1.6;
      svg.appendChild(el('path', { d: `M${x0},${y(p)} C${x0 + dx * 0.6},${y(p)} ${xb - dx * 0.6},${ly} ${xb},${ly} L${x(last)},${ly}`, class: 'der lk-' + k, 'data-family': f.parent }));
      svg.appendChild(el('text', { x: xb + 4, y: ly - 7, class: 'lanelabel' }, 'from ' + (p.ck || p.short)));
    }
    const gCmp = el('g', { class: 'cmp-layer' }); svg.appendChild(gCmp);
    const trackPts = new Map();
    if (track) {
      for (const v of [1, 0.1, 0.01, 0.001, 0.0001]) svg.appendChild(el('line', { x1: left - 16, y1: ty(v), x2: W - 20, y2: ty(v), class: 'tgrid' }));
      let d = '', prevT = null;
      for (const m of graph.nodes) { if (m.lane !== 0 || !has(m) || m.n == null) continue; d += (prevT !== null && m.t - prevT <= 3 ? 'L' : 'M') + x(m) + ',' + ty(m[metric]) + ' '; prevT = m.t; }
      if (d) svg.appendChild(el('path', { d: d.trim(), class: 'tline' }));
      for (const m of graph.nodes) {
        if (!has(m)) continue;
        const c = el('circle', { cx: x(m), cy: ty(m[metric]), r: 3.5, class: 'tpt ' + m.kind + (visible(m) ? '' : ' dim'), tabindex: 0, role: 'button', 'aria-label': (m.ck || m.short) + ', ' + fmtSci(m[metric]) });
        const t = el('title'); t.textContent = (m.ck ? m.ck + ' · ' : '') + m.short + ' · ' + fmtSci(m[metric]); c.appendChild(t);
        c.addEventListener('click', () => onSelect(m.id)); c.addEventListener('keydown', ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); onSelect(m.id); } });
        svg.appendChild(c); trackPts.set(m.id, c);
      }
    }
    const host = container.parentElement; host.style.position = 'relative';
    host.querySelectorAll('.minimap, .tip').forEach(n => n.remove());
    const tip = h('div', 'tip'); tip.hidden = true; host.appendChild(tip);
    const showTip = (m, ev) => {
      tip.textContent = ''; tip.appendChild(h('b', null, (m.ck ? m.ck + ' · ' : '') + m.short));
      const rows = m.planned ? [[m.setup && m.setup.prepared ? 'prepared' : 'planned', 'from ' + (graph.byId.get(m.parent).ck || graph.byId.get(m.parent).short)]] : [[has(m) ? fmtSci(m[metric]) : '—', trackLabel.split(',')[0]], [m[timeId] == null ? '—' : m[timeId].toFixed(2) + ' ' + unit, 'per call'], [kindLabel(m.kind), m.parent ? 'from ' + (graph.byId.get(m.parent).ck || graph.byId.get(m.parent).short) : '']];
      for (const [v, l] of rows) { const d = h('div'); d.appendChild(h('span', 'v', v)); d.appendChild(document.createTextNode(' ' + l)); tip.appendChild(d); }
      const r = host.getBoundingClientRect(); tip.hidden = false; tip.style.left = Math.min(ev.clientX - r.left + 14, host.clientWidth - 240) + 'px'; tip.style.top = Math.min(ev.clientY - r.top + 12, host.clientHeight - 90) + 'px';
    };
    const nodeEls = new Map();
    for (const m of graph.nodes) {
      const g = el('g', { class: 'node ' + m.kind + (m.planned ? ' planned' : '') + (visible(m) ? '' : ' dim'), tabindex: 0, role: 'button', 'aria-label': (m.ck ? m.ck + ' ' : '') + m.short, 'data-id': m.id });
      g.appendChild(el('rect', { x: x(m) - 14, y: y(m) - 14, width: 28, height: 28, class: 'hitr' }));
      g.appendChild(el('circle', { cx: x(m), cy: y(m), r: 5.5 }));
      const lbl = el('text', { x: x(m), y: y(m) + 18, class: 'nl' }, m.planned ? 'new' : (m.ck || m.short.slice(0, 10))); if (!(m.ck ? m.n % 2 === 1 : m.t % 2 === 1)) lbl.classList.add('off'); g.appendChild(lbl);
      g.addEventListener('click', () => onSelect(m.id));
      g.addEventListener('keydown', ev => { if (ev.key === 'Enter' || ev.key === ' ') { ev.preventDefault(); onSelect(m.id); } });
      g.addEventListener('pointerenter', ev => showTip(m, ev)); g.addEventListener('pointermove', ev => showTip(m, ev)); g.addEventListener('pointerleave', () => { tip.hidden = true; });
      g.addEventListener('focus', () => { const r = g.getBoundingClientRect(); showTip(m, { clientX: r.left + 14, clientY: r.top + 14 }); }); g.addEventListener('blur', () => { tip.hidden = true; });
      svg.appendChild(g); nodeEls.set(m.id, { g, lbl });
    }
    inner.appendChild(svg); container.appendChild(inner);
    const mini = h('div', 'minimap'); mini.setAttribute('role', 'img'); mini.setAttribute('aria-label', 'Whole map; click to move');
    const ms = el('svg', { viewBox: `0 0 ${W} ${H}`, preserveAspectRatio: 'none' });
    for (const m of graph.nodes) ms.appendChild(el('circle', { cx: x(m), cy: y(m), r: 7, class: 'd' }));
    const vp = el('rect', { class: 'vp', x: 0, y: 0, width: 10, height: 10 }); ms.appendChild(vp); mini.appendChild(ms); host.appendChild(mini);
    const sync = () => { vp.setAttribute('x', container.scrollLeft / zoom); vp.setAttribute('y', container.scrollTop / zoom); vp.setAttribute('width', container.clientWidth / zoom); vp.setAttribute('height', container.clientHeight / zoom); };
    container.addEventListener('scroll', sync); sync();
    mini.addEventListener('click', ev => { const r = mini.getBoundingClientRect(); container.scrollTo({ left: ((ev.clientX - r.left) / r.width) * W * zoom - container.clientWidth / 2, top: ((ev.clientY - r.top) / r.height) * H * zoom - container.clientHeight / 2, behavior: reduced() ? 'auto' : 'smooth' }); });
    let current = null; const walk = walker(); const order = graph.nodes.map(m => m.id);
    const api = {
      select(id) {
        const sel = graph.byId.get(id);
        gCmp.textContent = '';
        walk(order, current, id, (mid, on) => { const n = nodeEls.get(mid); if (n) n.g.classList.toggle('walk', on); }); current = id;
        for (const [mid, n] of nodeEls) { const m = graph.byId.get(mid); const on = mid === id; n.g.classList.toggle('sel', on); n.g.querySelector('circle').setAttribute('r', on ? 7 : 5.5); const fam = sel && (m.parent === id || mid === sel.parent || (sel.parent && m.parent === sel.parent)); n.lbl.classList.toggle('off', !(on || fam || (m.ck ? m.n % 2 === 1 : m.t % 2 === 1))); n.g.classList.toggle('kin', !!fam && !on); }
        for (const p of svg.querySelectorAll('.der')) p.classList.toggle('hot', !!sel && (p.dataset.family === id || p.dataset.family === sel.parent));
        for (const [mid, c] of trackPts) c.classList.toggle('sel', mid === id);
        if (sel) for (const e of graph.edges) if (e.kind === 'comparison' && (e.from === id || e.to === id)) {
          const a = graph.byId.get(e.from), b = graph.byId.get(e.to), other = e.from === id ? b : a;
          const path = el('path', { d: `M${x(a)},${y(a)} C${x(a)},${Math.min(y(a), y(b)) - 34} ${x(b)},${Math.min(y(a), y(b)) - 34} ${x(b)},${y(b)}`, class: 'cmp', tabindex: 0, role: 'link', 'aria-label': 'Compared with ' + (other.ck || other.short) });
          const t = el('title'); t.textContent = 'Compared with ' + (other.ck || other.short) + ': ' + (e.excerpt || e.explanation || ''); path.appendChild(t);
          const show = ev => { tip.textContent = ''; tip.appendChild(h('b', null, 'Compared with ' + (other.ck || other.short))); tip.appendChild(h('div', null, (e.excerpt || e.explanation || '').slice(0, 160) + ((e.excerpt || '').length > 160 ? '…' : ''))); const r = host.getBoundingClientRect(); tip.hidden = false; tip.style.left = Math.min(ev.clientX - r.left + 14, host.clientWidth - 240) + 'px'; tip.style.top = Math.min(ev.clientY - r.top + 12, host.clientHeight - 90) + 'px'; };
          path.addEventListener('pointerenter', show); path.addEventListener('pointermove', show); path.addEventListener('pointerleave', () => { tip.hidden = true; });
          path.addEventListener('click', () => onSelect(other.id)); path.addEventListener('keydown', ev => { if (ev.key === 'Enter') onSelect(other.id); });
          gCmp.appendChild(path);
        }
      },
      scrollTo(id, smooth) { const m = graph.byId.get(id); if (!m) return; container.scrollTo({ left: x(m) * zoom - container.clientWidth / 2, top: Math.max(0, y(m) * zoom - container.clientHeight / 2), behavior: smooth && !reduced() ? 'smooth' : 'auto' }); }
    };
    api.select(selected); return api;
  }
  return { build, renderList, renderMap, related, comparisons, kindLabel, fmtSci, metricFill, matches };
})();
