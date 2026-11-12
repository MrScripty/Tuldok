'use strict';
// Benchmark charts in plain SVG: an accuracy/time scatter with its Pareto
// frontier, and the worst-pressure curve along the checkpoint sequence.
// Every value is also in the table view; tooltips enhance, never gate.
window.LabCharts = (() => {
  const svgNS = 'http://www.w3.org/2000/svg';
  const el = (name, attrs = {}, text) => { const n = document.createElementNS(svgNS, name); for (const k in attrs) n.setAttribute(k, attrs[k]); if (text !== undefined) n.textContent = text; return n; };
  const h = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
  const fmtSci = v => window.LabTree.fmtSci(v);
  const logTicks = (lo, hi) => { const out = []; for (let e = Math.ceil(Math.log10(lo)); e <= Math.floor(Math.log10(hi)); e++) out.push(Math.pow(10, e)); return out; };
  const tickLabel = v => v >= 1 ? String(v) : (v >= 0.01 ? v.toString() : '1e' + Math.log10(v));

  function tooltip(host) {
    const t = h('div', 'tip'); t.hidden = true; host.appendChild(t);
    return {
      show(x, y, rows) { t.textContent = ''; for (const r of rows) { if (r.b) { t.appendChild(h('b', null, r.b)); continue; } const line = h('div'); const v = h('span', 'v', r.v); line.appendChild(v); line.appendChild(document.createTextNode(' ' + r.l)); t.appendChild(line); } t.hidden = false; const W = host.clientWidth; t.style.left = Math.min(x + 14, W - 200) + 'px'; t.style.top = (y + 12) + 'px'; },
      hide() { t.hidden = true; }
    };
  }

  function pareto(host, models, { selected = null, onSelect = () => {}, kinds = null, frontierOnly = false, metric = 'worstP', table = false, yLabel = '', xLabel = '', unit = 'ms', xMax = 10 } = {}) {
    host.textContent = ''; host.classList.add('chart');
    const pts = models.filter(m => m.ms != null && m.ms <= xMax && m[metric] != null && m[metric] > 0);
    const shown = pts.filter(m => !kinds || kinds.has(m.kind));
    const sorted = shown.slice().sort((a, b) => a.ms - b.ms || a[metric] - b[metric]);
    const front = []; let best = Infinity; for (const m of sorted) { if (m[metric] < best) { front.push(m); best = m[metric]; } }
    const frontSet = new Set(front.map(m => m.id));
    const W = 760, H = 340, L = 56, R = 16, T = 16, B = 40;
    const ylo = 1e-4, yhi = 1;
    const X = ms => L + (ms / xMax) * (W - L - R), Y = v => T + (Math.log10(yhi) - Math.log10(Math.min(Math.max(v, ylo), yhi))) / (Math.log10(yhi) - Math.log10(ylo)) * (H - T - B);
    const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': yLabel + ' on a log scale against ' + xLabel });
    const grid = el('g', { class: 'grid' }), axis = el('g', { class: 'axis' });
    for (const v of logTicks(ylo, yhi)) { grid.appendChild(el('line', { x1: L, y1: Y(v), x2: W - R, y2: Y(v) })); axis.appendChild(el('text', { x: L - 8, y: Y(v) + 4, 'text-anchor': 'end' }, tickLabel(v))); }
    const step = xMax > 10 ? 4 : 2; for (let ms = 0; ms <= xMax; ms += step) { axis.appendChild(el('line', { x1: X(ms), y1: H - B, x2: X(ms), y2: H - B + 4, class: 'base' })); axis.appendChild(el('text', { x: X(ms), y: H - B + 16, 'text-anchor': 'middle' }, ms + (ms + step > xMax ? ' ' + unit : ''))); }
    axis.appendChild(el('line', { x1: L, y1: H - B, x2: W - R, y2: H - B, class: 'base' }));
    axis.appendChild(el('text', { x: W - R, y: H - 4, 'text-anchor': 'end', class: 'label' }, xLabel));
    axis.appendChild(el('text', { x: L, y: T - 4, class: 'label' }, yLabel));
    svg.appendChild(grid); svg.appendChild(axis);
    if (front.length > 1) svg.appendChild(el('path', { class: 'frontier', d: front.map((m, i) => (i ? 'L' : 'M') + X(m.ms) + ',' + Y(m[metric])).join(' ') }));
    const tip = tooltip(host);
    const order = shown.slice().sort((a, b) => (a.id === selected) - (b.id === selected));
    for (const m of order) {
      const dim = frontierOnly && !frontSet.has(m.id);
      const g = el('g');
      const hit = el('circle', { cx: X(m.ms), cy: Y(m[metric]), r: 12, class: 'hit', tabindex: 0, role: 'button', 'aria-label': `${m.ck || m.short}, ${fmtSci(m[metric])} at ${m.ms.toFixed(2)} milliseconds${frontSet.has(m.id) ? ', on the frontier' : ''}` });
      const pt = el('circle', { cx: X(m.ms), cy: Y(m[metric]), r: 5, class: 'pt ' + m.kind + (dim ? ' dim' : '') });
      const rows = () => [{ b: (m.ck ? m.ck + ' · ' : '') + m.short }, { v: fmtSci(m[metric]), l: yLabel }, { v: m.ms.toFixed(2) + ' ' + unit, l: xLabel }, { v: window.LabTree.kindLabel(m.kind), l: frontSet.has(m.id) ? '· frontier' : '' }];
      const pos = () => { const r = host.getBoundingClientRect(); const s = svg.getBoundingClientRect(); return [s.left - r.left + X(m.ms) * s.width / W, s.top - r.top + Y(m[metric]) * s.height / H]; };
      hit.addEventListener('pointerenter', () => { const [x, y] = pos(); tip.show(x, y, rows()); });
      hit.addEventListener('focus', () => { const [x, y] = pos(); tip.show(x, y, rows()); });
      hit.addEventListener('pointerleave', () => tip.hide()); hit.addEventListener('blur', () => tip.hide());
      hit.addEventListener('click', () => onSelect(m.id)); hit.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(m.id); } });
      g.appendChild(hit); g.appendChild(pt);
      if (m.id === selected) g.appendChild(el('circle', { cx: X(m.ms), cy: Y(m[metric]), r: 9, class: 'sel' }));
      svg.appendChild(g);
    }
    if (front.length) { const b = front[front.length - 1]; svg.appendChild(el('text', { x: X(b.ms) + 10, y: Y(b[metric]) + 4, class: 'label' }, (b.ck || b.short) + ' · best accuracy')); const f = front[0]; if (f !== b) svg.appendChild(el('text', { x: X(f.ms) + 10, y: Y(f[metric]) + 18, class: 'label' }, (f.ck || f.short) + ' · fastest')); }
    host.appendChild(svg);
    const legend = h('ul', 'legend');
    for (const k of ['training', 'architecture', 'refinement', 'composition']) { const li = h('li', 'chip ' + k, window.LabTree.kindLabel(k)); legend.appendChild(li); }
    const fl = h('li', null, 'Line: Pareto frontier'); legend.appendChild(fl);
    host.appendChild(legend);
    if (table) {
      const tb = h('table', 'tv'); tb.setAttribute('aria-label', 'Plotted fits as a table');
      const thead = h('thead'); const tr = h('tr'); for (const [t, c] of [['Fit', ''], ['Kind', ''], [yLabel, 'n'], [xLabel, 'n'], ['Frontier', '']]) { const th = h('th', c, t); tr.appendChild(th); } thead.appendChild(tr); tb.appendChild(thead);
      const tbody = h('tbody'); for (const m of sorted) { const r = h('tr'); r.appendChild(h('td', null, (m.ck ? m.ck + ' · ' : '') + m.short)); r.appendChild(h('td', null, window.LabTree.kindLabel(m.kind))); r.appendChild(h('td', 'n', fmtSci(m[metric]))); r.appendChild(h('td', 'n', m.ms.toFixed(2))); r.appendChild(h('td', null, frontSet.has(m.id) ? 'yes' : '')); tbody.appendChild(r); } tb.appendChild(tbody); host.appendChild(tb);
    }
    return { count: shown.length, total: pts.length, frontier: front };
  }

  function curve(host, models, { selected = null, onSelect = () => {}, metric = 'worstP', sections = [], yLabel = '', secondary = null } = {}) {
    host.textContent = ''; host.classList.add('chart');
    const pts = models.filter(m => m.n != null && m.n <= 124 && m[metric] != null && m[metric] > 0).sort((a, b) => a.n - b.n);
    const W = 760, H = 220, L = 56, R = 16, T = 28, B = 34, ylo = 1e-4, yhi = 1, nlo = pts[0].n, nhi = pts[pts.length - 1].n;
    const X = n => L + (n - nlo) / (nhi - nlo) * (W - L - R), Y = v => T + (Math.log10(yhi) - Math.log10(Math.min(Math.max(v, ylo), yhi))) / 4 * (H - T - B);
    const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': yLabel + ' for each checkpoint from C' + nlo + ' to C' + nhi });
    const grid = el('g', { class: 'grid' }), axis = el('g', { class: 'axis' });
    for (const v of logTicks(ylo, yhi)) { grid.appendChild(el('line', { x1: L, y1: Y(v), x2: W - R, y2: Y(v) })); axis.appendChild(el('text', { x: L - 8, y: Y(v) + 4, 'text-anchor': 'end' }, tickLabel(v))); }
    for (let n = 20; n <= nhi; n += 20) axis.appendChild(el('text', { x: X(n), y: H - B + 16, 'text-anchor': 'middle' }, 'C' + n));
    axis.appendChild(el('line', { x1: L, y1: H - B, x2: W - R, y2: H - B, class: 'base' }));
    for (const s of sections) { const a = pts.find(m => m.n >= s.from); if (!a) continue; axis.appendChild(el('line', { x1: X(s.from), y1: T - 8, x2: X(s.from), y2: H - B, class: '' })); axis.appendChild(el('text', { x: X(s.from) + 4, y: T - 12, class: 'label' }, s.label)); }
    svg.appendChild(grid); svg.appendChild(axis);
    svg.appendChild(el('path', { class: 'line', d: pts.map((m, i) => (i ? 'L' : 'M') + X(m.n) + ',' + Y(m[metric])).join(' ') }));
    const cross = el('line', { class: 'cross', x1: 0, y1: T, x2: 0, y2: H - B }); cross.style.visibility = 'hidden'; svg.appendChild(cross);
    for (const m of pts) { svg.appendChild(el('circle', { cx: X(m.n), cy: Y(m[metric]), r: 4, class: 'pt ' + m.kind + (m.id === selected ? '' : '') })); if (m.id === selected) svg.appendChild(el('circle', { cx: X(m.n), cy: Y(m[metric]), r: 8, class: 'sel' })); }
    const tip = tooltip(host);
    const nearest = cx => { let b = pts[0], d = Infinity; for (const m of pts) { const dd = Math.abs(X(m.n) - cx); if (dd < d) { d = dd; b = m; } } return b; };
    const toSvg = e => { const r = svg.getBoundingClientRect(); return [(e.clientX - r.left) * W / r.width, (e.clientY - r.top) * H / r.height]; };
    svg.addEventListener('pointermove', e => { const [cx] = toSvg(e); const m = nearest(cx); cross.setAttribute('x1', X(m.n)); cross.setAttribute('x2', X(m.n)); cross.style.visibility = 'visible'; const r = host.getBoundingClientRect(), s = svg.getBoundingClientRect(); tip.show(s.left - r.left + X(m.n) * s.width / W, s.top - r.top + Y(m[metric]) * s.height / H, [{ b: m.ck + ' · ' + m.short }, { v: fmtSci(m[metric]), l: yLabel }].concat(secondary ? [{ v: m[secondary.id] == null ? '—' : fmtSci(m[secondary.id]), l: secondary.label }] : []).concat([{ v: window.LabTree.kindLabel(m.kind), l: '' }])); });
    svg.addEventListener('pointerleave', () => { cross.style.visibility = 'hidden'; tip.hide(); });
    svg.addEventListener('click', e => { const [cx] = toSvg(e); onSelect(nearest(cx).id); });
    host.appendChild(svg);
    return { count: pts.length };
  }
  // Multi-series line chart (training curves). series: [{id, label, slot, points: [[x, y]]}]
  function lines(host, series, { yLabel = '', xLabel = '', logY = true } = {}) {
    host.textContent = ''; host.classList.add('chart');
    const W = 760, H = 240, L = 56, R = 16, T = 16, B = 36;
    const all = series.flatMap(s => s.points); if (!all.length) { host.appendChild(h('p', 'empty', 'No curves.')); return; }
    const xlo = 0, xhi = Math.max(...all.map(p => p[0])), ylo = Math.min(...all.map(p => p[1])), yhi = Math.max(...all.map(p => p[1]));
    const X = x => L + (x - xlo) / (xhi - xlo || 1) * (W - L - R);
    const Y = logY ? v => T + (Math.log10(yhi) - Math.log10(v)) / (Math.log10(yhi) - Math.log10(ylo) || 1) * (H - T - B) : v => T + (yhi - v) / (yhi - ylo || 1) * (H - T - B);
    const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, role: 'img', 'aria-label': yLabel + ' against ' + xLabel + ' for ' + series.map(s => s.label).join(', ') });
    const grid = el('g', { class: 'grid' }), axis = el('g', { class: 'axis' });
    const ticks = logY ? logTicks(ylo, yhi).filter(v => v >= ylo && v <= yhi) : [ylo, (ylo + yhi) / 2, yhi];
    for (const v of ticks) { grid.appendChild(el('line', { x1: L, y1: Y(v), x2: W - R, y2: Y(v) })); axis.appendChild(el('text', { x: L - 8, y: Y(v) + 4, 'text-anchor': 'end' }, logY ? tickLabel(v) : v.toFixed(2))); }
    for (let i = 0; i <= 4; i++) { const x = xlo + (xhi - xlo) * i / 4; axis.appendChild(el('text', { x: X(x), y: H - B + 16, 'text-anchor': 'middle' }, Math.round(x).toLocaleString('en-GB'))); }
    axis.appendChild(el('line', { x1: L, y1: H - B, x2: W - R, y2: H - B, class: 'base' }));
    axis.appendChild(el('text', { x: W - R, y: H - 4, 'text-anchor': 'end', class: 'label' }, xLabel));
    axis.appendChild(el('text', { x: L, y: T - 4, class: 'label' }, yLabel));
    svg.appendChild(grid); svg.appendChild(axis);
    for (const s of series) { svg.appendChild(el('path', { class: 'line s' + s.slot, d: s.points.map((p, i) => (i ? 'L' : 'M') + X(p[0]) + ',' + Y(p[1])).join(' ') })); const last = s.points[s.points.length - 1]; svg.appendChild(el('circle', { cx: X(last[0]), cy: Y(last[1]), r: 4, class: 'pt s' + s.slot })); }
    const cross = el('line', { class: 'cross', x1: 0, y1: T, x2: 0, y2: H - B }); cross.style.visibility = 'hidden'; svg.appendChild(cross);
    const tip = tooltip(host);
    svg.addEventListener('pointermove', e => { const r = svg.getBoundingClientRect(); const cx = (e.clientX - r.left) * W / r.width; const xv = xlo + (cx - L) / (W - L - R) * (xhi - xlo); cross.setAttribute('x1', cx); cross.setAttribute('x2', cx); cross.style.visibility = 'visible'; const rows = [{ b: Math.round(xv).toLocaleString('en-GB') + ' ' + xLabel }]; for (const s of series) { let b = s.points[0]; for (const p of s.points) if (Math.abs(p[0] - xv) < Math.abs(b[0] - xv)) b = p; rows.push({ v: fmtSci(b[1]), l: s.label }); } const hr = host.getBoundingClientRect(); tip.show(e.clientX - hr.left, e.clientY - hr.top - 10, rows); });
    svg.addEventListener('pointerleave', () => { cross.style.visibility = 'hidden'; tip.hide(); });
    host.appendChild(svg);
    const legend = h('ul', 'legend'); for (const s of series) { const li = h('li', 'key s' + s.slot, s.label); legend.appendChild(li); } host.appendChild(legend);
  }
  return { pareto, curve, lines };
})();
