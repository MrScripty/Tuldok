'use strict';
// Chart helpers in plain SVG, shared by the map's track and the charts of the
// other tabs: element builders, a value scale fitted to the values it shows,
// number formats and the hover tip. Every value a chart draws is also written
// as text somewhere on the page; tips enhance, never gate.
window.LabCharts = (() => {
  const svgNS = 'http://www.w3.org/2000/svg';
  const el = (name, attrs = {}, text) => { const n = document.createElementNS(svgNS, name); for (const k in attrs) n.setAttribute(k, attrs[k]); if (text !== undefined) n.textContent = text; return n; };
  const h = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };

  /** A number in at most four significant figures, scientific below 0.01 and from 1e5. */
  function fmtSci(v) {
    if (v == null || !Number.isFinite(v)) return '—';
    const a = Math.abs(v);
    if (a === 0) return '0';
    if (a >= 0.01 && a < 1e5) return a >= 100 ? String(Math.round(v * 10) / 10) : v.toPrecision(3).replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '');
    const e = Math.floor(Math.log10(a));
    return (v / Math.pow(10, e)).toFixed(2) + 'e' + e;
  }
  const tickLabel = v => v >= 0.01 && v < 1e5 ? String(v) : '1e' + Math.round(Math.log10(v));

  /**
   * A scale for values: logarithmic over whole decades when every value is
   * positive, linear from zero otherwise. at(v) is 0 at the low end and 1 at
   * the high end; good(v) is the share of the scale that is better than the
   * worst end, by better ('lower' or 'higher'), for bars that grow as a value
   * improves.
   */
  function scale(values, better = 'lower') {
    const xs = values.filter(v => v != null && Number.isFinite(v));
    if (!xs.length) return null;
    const positive = xs.every(v => v > 0);
    let lo, hi, at, ticks;
    if (positive) {
      lo = Math.floor(Math.log10(Math.min(...xs))); hi = Math.ceil(Math.log10(Math.max(...xs)));
      if (hi === lo) hi = lo + 1;
      at = v => (Math.log10(Math.min(Math.max(v, Math.pow(10, lo)), Math.pow(10, hi))) - lo) / (hi - lo);
      const step = Math.ceil((hi - lo) / 5); ticks = [];
      for (let e = hi; e >= lo; e -= step) ticks.push(Math.pow(10, e));
    } else {
      lo = Math.min(0, ...xs); hi = Math.max(...xs); if (hi === lo) hi = lo + 1;
      at = v => (v - lo) / (hi - lo);
      ticks = [hi, (hi + lo) / 2, lo];
    }
    return { log: positive, at, ticks, label: positive ? tickLabel : fmtSci, good: v => better === 'higher' ? at(v) : 1 - at(v) };
  }

  /** A tip inside host, placed near (x, y) in host coordinates and kept inside it. */
  function tooltip(host) {
    const t = h('div', 'tip'); t.hidden = true; host.appendChild(t);
    return {
      node: t,
      show(x, y, rows) {
        t.textContent = '';
        for (const r of rows) {
          if (r.b) { t.appendChild(h('b', null, r.b)); continue; }
          const line = h('div'); if (r.v) { line.appendChild(h('span', 'v', r.v)); line.appendChild(document.createTextNode(' ')); }
          line.appendChild(document.createTextNode(r.l || '')); t.appendChild(line);
        }
        t.hidden = false;
        t.style.left = Math.max(4, Math.min(x + 14, host.clientWidth - t.offsetWidth - 8)) + 'px';
        t.style.top = Math.max(4, Math.min(y + 12, host.clientHeight - t.offsetHeight - 8)) + 'px';
      },
      hide() { t.hidden = true; }
    };
  }
  // ---- Charts of benchmark results (the Benchmarks and Analysis tabs) --------
  // Each draws from data the page holds (the chart operation's points, or
  // per-case values) at a given pixel width, so its text stays at the type
  // scale whatever the window; every point can be hovered and focused, and
  // Enter or a click selects it when the chart is given onSelect.

  /** A nice step (1, 2 or 5 times a power of ten) near span / count. */
  function niceStep(span, count) { const raw = span / Math.max(1, count), p = Math.pow(10, Math.floor(Math.log10(raw))), f = raw / p; return (f <= 1 ? 1 : f <= 2 ? 2 : f <= 5 ? 5 : 10) * p; }
  /**
   * The brief's axis: logarithmic over whole decades when every value is
   * positive and they span at least two decades, linear otherwise (from zero
   * when every value is positive). at(v) is 0 at the low end, 1 at the high.
   */
  function axis(values) {
    const xs = values.filter(v => v != null && Number.isFinite(v));
    if (!xs.length) return null;
    const min = Math.min(...xs), max = Math.max(...xs);
    if (min > 0 && max / min >= 100) {
      const lo = Math.floor(Math.log10(min)), hi = Math.max(lo + 1, Math.ceil(Math.log10(max))), step = Math.ceil((hi - lo) / 6), ticks = [];
      for (let e = lo; e <= hi; e += step) ticks.push(Math.pow(10, e));
      return { log: true, ticks, at: v => (Math.log10(Math.max(v, Math.pow(10, lo))) - lo) / (hi - lo), label: tickLabel };
    }
    let lo = min >= 0 ? 0 : min, hi = max <= 0 ? 0 : max; if (hi === lo) hi = lo + (Math.abs(lo) || 1);
    const step = niceStep(hi - lo, 5); lo = Math.floor(lo / step) * step; hi = Math.ceil(hi / step - 1e-9) * step;
    const ticks = []; for (let v = lo; v <= hi + step / 2; v += step) ticks.push(Math.abs(v) < step / 1e6 ? 0 : v);
    return { log: false, ticks, at: v => (v - lo) / (hi - lo), label: fmtSci };
  }
  const axisWords = (title, a) => title + (a && a.log ? ' (log scale)' : '');
  /** Wires hover, focus, click and Enter of a focusable mark to a tip and onSelect. */
  function interactive(node, host, svg, at, rows, onSelect) {
    const tip = host._tip || (host._tip = tooltip(host));
    const show = () => { const r = host.getBoundingClientRect(), s = svg.getBoundingClientRect(), [x, y] = at(); tip.show(s.left - r.left + x * s.width / svg.viewBox.baseVal.width, s.top - r.top + y * s.height / svg.viewBox.baseVal.height, rows()); };
    node.addEventListener('pointerenter', show); node.addEventListener('focus', show);
    node.addEventListener('pointerleave', () => tip.hide()); node.addEventListener('blur', () => tip.hide());
    if (onSelect) { node.addEventListener('click', onSelect); node.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(); } }); }
  }
  function frame(width, height, label) { const svg = el('svg', { viewBox: `0 0 ${width} ${height}`, role: 'group', 'aria-label': label }); return svg; }
  function yGrid(svg, ax, Y, L, R, W) { const grid = el('g', { class: 'grid' }), labels = el('g', { class: 'axis' }); for (const v of ax.ticks) { grid.appendChild(el('line', { x1: L, y1: Y(v), x2: W - R, y2: Y(v) })); labels.appendChild(el('text', { x: L - 8, y: Y(v) + 4, 'text-anchor': 'end' }, ax.label(v))); } svg.appendChild(grid); svg.appendChild(labels); }
  const textWidth = (text, size = 12) => text.length * size * 0.56;

  /**
   * A scatter of points {id, name, x, y, kind, frontier, rows} with the
   * frontier drawn through the points marked on it (in x order); the ends of
   * the frontier are named. opts: width, height, xTitle, yTitle, xBetter,
   * yBetter, selected, onSelect(id), dimOff (dim points off the frontier).
   */
  function scatter(host, points, opts) {
    host.textContent = ''; host.classList.add('chart'); host._tip = null;
    const W = Math.max(360, opts.width), H = opts.height || 340, L = 64, R = 20, T = 22, B = 40;
    const xa = axis(points.map(p => p.x)), ya = axis(points.map(p => p.y));
    const X = v => L + xa.at(v) * (W - L - R), Y = v => T + (1 - ya.at(v)) * (H - T - B);
    const svg = frame(W, H, axisWords(opts.yTitle, ya) + ' against ' + axisWords(opts.xTitle, xa) + ', ' + points.length + ' points');
    yGrid(svg, ya, Y, L, R, W);
    const ax = el('g', { class: 'axis' });
    xa.ticks.forEach((v, i) => { ax.appendChild(el('line', { x1: X(v), y1: H - B, x2: X(v), y2: H - B + 4, class: 'base' })); ax.appendChild(el('text', { x: X(v), y: H - B + 16, 'text-anchor': i === xa.ticks.length - 1 ? 'end' : 'middle' }, xa.label(v))); });
    ax.appendChild(el('line', { x1: L, y1: H - B, x2: W - R, y2: H - B, class: 'base' }));
    ax.appendChild(el('text', { x: W - R, y: H - 4, 'text-anchor': 'end', class: 'label' }, axisWords(opts.xTitle, xa)));
    ax.appendChild(el('text', { x: L, y: T - 8, class: 'label' }, axisWords(opts.yTitle, ya)));
    svg.appendChild(ax);
    const front = points.filter(p => p.frontier).sort((a, b) => a.x - b.x || a.y - b.y);
    if (front.length > 1) svg.appendChild(el('path', { class: 'frontier', d: front.map((p, i) => (i ? 'L' : 'M') + X(p.x).toFixed(1) + ',' + Y(p.y).toFixed(1)).join(' ') }));
    const order = points.slice().sort((a, b) => (a.id === opts.selected) - (b.id === opts.selected));
    for (const p of order) {
      const g = el('g'), cx = X(p.x), cy = Y(p.y);
      const hit = el('circle', { cx, cy, r: 11, class: 'hit', tabindex: 0, role: 'button', 'data-id': p.id, 'aria-label': p.name + ', ' + opts.yTitle + ' ' + fmtSci(p.y) + ', ' + opts.xTitle + ' ' + fmtSci(p.x) + (p.frontier ? ', on the frontier' : '') });
      g.appendChild(hit); g.appendChild(el('circle', { cx, cy, r: 6, class: 'pt ' + p.kind + ((opts.dimOff && !p.frontier) || p.dim ? ' dim' : '') }));
      if (p.nsig) g.appendChild(el('circle', { cx, cy, r: 10, class: 'nsig' }));   // on the frontier, not told apart from a neighbour (spec-t3)
      if (p.id === opts.selected) g.appendChild(el('circle', { cx, cy, r: 9, class: 'sel' }));
      interactive(hit, host, svg, () => [cx, cy], p.rows, opts.onSelect && (() => opts.onSelect(p.id)));
      svg.appendChild(g);
    }
    if (front.length) {   // name the two ends of the frontier, as the mockup does
      const lowY = opts.yBetter === 'higher' ? front.reduce((a, b) => b.y > a.y ? b : a) : front.reduce((a, b) => b.y < a.y ? b : a);
      const lowX = opts.xBetter === 'higher' ? front.reduce((a, b) => b.x > a.x ? b : a) : front.reduce((a, b) => b.x < a.x ? b : a);
      const word = (better, title) => { const t = (better === 'higher' ? 'highest ' : 'lowest ') + title.charAt(0).toLowerCase() + title.slice(1); return t.length > 34 ? t.slice(0, 33) + '…' : t; };
      const put = (p, text, dy) => { const w = textWidth(text), right = X(p.x) + 10 + w <= W - R; svg.appendChild(el('text', { x: right ? X(p.x) + 10 : X(p.x) - 10, y: Math.min(H - B - 4, Math.max(T + 10, Y(p.y) + dy)), 'text-anchor': right ? 'start' : 'end', class: 'label' }, text)); };
      put(lowY, lowY.short + ' · ' + word(opts.yBetter, opts.yName || opts.yTitle), 4);
      if (lowX !== lowY) {   // on the side the frontier does not leave by, so the line does not run through the words
        const at = front.indexOf(lowX), next = front[at + 1] || front[at - 1];
        put(lowX, lowX.short + ' · ' + word(opts.xBetter, opts.xName || opts.xTitle), next && Y(next.y) >= Y(lowX.y) ? -12 : 18);
      }
    }
    host.appendChild(svg);
    return { frontier: front };
  }

  /**
   * Values in training order {id, name, y, best, kind, rows}: the values as a
   * line of points, the best so far as a step line in the good colour.
   */
  function progression(host, points, opts) {
    host.textContent = ''; host.classList.add('chart'); host._tip = null;
    const W = Math.max(360, opts.width), H = opts.height || 240, L = 64, R = 20, T = 22, B = 36, n = points.length;
    const ya = axis(points.map(p => p.y).concat(points.map(p => p.best)));
    const X = i => L + (n > 1 ? i / (n - 1) : 0.5) * (W - L - R), Y = v => T + (1 - ya.at(v)) * (H - T - B);
    const svg = frame(W, H, axisWords(opts.yTitle, ya) + ' for ' + n + ' subjects in training order, with the best so far');
    yGrid(svg, ya, Y, L, R, W);
    const ax = el('g', { class: 'axis' });
    ax.appendChild(el('line', { x1: L, y1: H - B, x2: W - R, y2: H - B, class: 'base' }));
    const every = Math.max(1, Math.ceil(n / Math.max(1, Math.floor((W - L - R) / 90))));
    points.forEach((p, i) => { if (i % every === 0 || i === n - 1) { const t = p.short.length > 12 ? p.short.slice(0, 11) + '…' : p.short; ax.appendChild(el('text', { x: X(i), y: H - B + 16, 'text-anchor': n === 1 ? 'middle' : i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle' }, t)); } });
    ax.appendChild(el('text', { x: L, y: T - 8, class: 'label' }, axisWords(opts.yTitle, ya)));
    ax.appendChild(el('text', { x: W - R, y: H - 4, 'text-anchor': 'end', class: 'label' }, 'training order'));
    svg.appendChild(ax);
    if (n > 1) {
      svg.appendChild(el('path', { class: 'line', d: points.map((p, i) => (i ? 'L' : 'M') + X(i).toFixed(1) + ',' + Y(p.y).toFixed(1)).join(' ') }));
      svg.appendChild(el('path', { class: 'best', d: points.map((p, i) => (i ? 'H' + X(i).toFixed(1) + 'V' : 'M' + X(i).toFixed(1) + ',') + Y(p.best).toFixed(1)).join(' ') }));
    }
    points.forEach((p, i) => {
      const g = el('g'), cx = X(i), cy = Y(p.y);
      const hit = el('circle', { cx, cy, r: Math.max(6, Math.min(11, (W - L - R) / Math.max(1, n) / 2)), class: 'hit', tabindex: 0, role: 'button', 'data-id': p.id, 'aria-label': p.name + ', ' + opts.yTitle + ' ' + fmtSci(p.y) + ', best so far ' + fmtSci(p.best) });
      g.appendChild(hit); g.appendChild(el('circle', { cx, cy, r: n > 80 ? 3 : 4, class: 'pt ' + p.kind + (p.dim ? ' dim' : '') }));
      if (p.id === opts.selected) g.appendChild(el('circle', { cx, cy, r: 8, class: 'sel' }));
      interactive(hit, host, svg, () => [cx, cy], p.rows, opts.onSelect && (() => opts.onSelect(p.id)));
      svg.appendChild(g);
    });
    host.appendChild(svg);
  }

  /** Subjects best first {id, name, y, kind, rows, lo, hi}: one row each, a dot on the value axis with a hairline from its start, and a whisker from lo to hi when given (an interval, spec-t3). */
  function ranking(host, points, opts) {
    host.textContent = ''; host.classList.add('chart'); host._tip = null;
    const n = points.length, RH = n > 60 ? 16 : 20, W = Math.max(360, opts.width), L = Math.min(260, Math.max(120, W * 0.24)), R = 64, T = 26, H = T + n * RH + 8;
    const xa = axis(points.map(p => p.y).concat(points.map(p => p.lo), points.map(p => p.hi))), X = v => L + xa.at(v) * (W - L - R);
    const svg = frame(W, H, axisWords(opts.yTitle, xa) + ' for ' + n + ' subjects, best first');
    const grid = el('g', { class: 'grid' }), ax = el('g', { class: 'axis' });
    xa.ticks.forEach((v, i) => { grid.appendChild(el('line', { x1: X(v), y1: T - 4, x2: X(v), y2: H - 8 })); ax.appendChild(el('text', { x: X(v), y: T - 10, 'text-anchor': i === xa.ticks.length - 1 && xa.ticks.length > 1 ? 'end' : 'middle' }, xa.label(v))); });
    svg.appendChild(grid); svg.appendChild(ax);
    points.forEach((p, i) => {
      const cy = T + i * RH + RH / 2, cx = X(p.y), g = el('g');
      const max = Math.floor((L - 14) / 6.6), t = p.name.length > max ? p.name.slice(0, max - 1) + '…' : p.name;
      g.appendChild(el('text', { x: L - 10, y: cy + 4, 'text-anchor': 'end', class: 'rk' + (p.id === opts.selected ? ' on' : '') }, t));
      g.appendChild(el('line', { x1: L, y1: cy, x2: cx, y2: cy, class: 'stem' }));
      const ci = p.lo != null && p.hi != null;
      const hit = el('rect', { x: 0, y: cy - RH / 2, width: W, height: RH, class: 'hit band', tabindex: 0, role: 'button', 'data-id': p.id, 'aria-label': p.name + ', ' + opts.yTitle + ' ' + fmtSci(p.y) + (ci ? ', 95% interval ' + fmtSci(p.lo) + ' to ' + fmtSci(p.hi) : '') });
      g.insertBefore(hit, g.firstChild);
      if (ci) { const a = X(p.lo), b = X(p.hi), w = el('g', { class: 'ci', 'data-lo': p.lo, 'data-hi': p.hi }); w.appendChild(el('line', { x1: a, y1: cy, x2: b, y2: cy })); w.appendChild(el('line', { x1: a, y1: cy - 4, x2: a, y2: cy + 4 })); w.appendChild(el('line', { x1: b, y1: cy - 4, x2: b, y2: cy + 4 })); g.appendChild(w); }
      g.appendChild(el('circle', { cx, cy, r: 4.5, class: 'pt ' + p.kind + (p.dim ? ' dim' : '') }));
      if (p.id === opts.selected) g.appendChild(el('circle', { cx, cy, r: 8, class: 'sel' }));
      g.appendChild(el('text', { x: W - 4, y: cy + 4, 'text-anchor': 'end', class: 'rv' }, fmtSci(p.y)));
      interactive(hit, host, svg, () => [cx, cy], p.rows, opts.onSelect && (() => opts.onSelect(p.id)));
      svg.appendChild(g);
    });
    host.appendChild(svg);
  }

  /** One mark per case {label, value, reason}: a bar for a value, a hollow tick at the base for a missing one. */
  function strip(host, items, opts) {
    host.textContent = ''; host.classList.add('chart', 'cases'); host._tip = null;
    const W = Math.max(360, opts.width), H = opts.height || 96, L = 64, R = 12, T = 10, B = 14, n = items.length;
    const ya = axis(items.map(c => c.value)) || axis([0, 1]), Y = v => T + (1 - ya.at(v)) * (H - T - B);
    const svg = frame(W, H, opts.label + ', ' + n + ' cases');
    yGrid(svg, ya, Y, L, R, W);
    const step = (W - L - R) / Math.max(1, n), bw = Math.max(1.5, Math.min(18, step - (step > 4 ? 2 : 0.5))), base = Y(ya.log ? ya.ticks[0] : 0);
    svg.appendChild(el('line', { x1: L, y1: H - B, x2: W - R, y2: H - B, class: 'base' }));
    items.forEach((c, i) => {
      const x = L + i * step + (step - bw) / 2, g = el('g');
      const has = c.value != null && Number.isFinite(c.value), top = has ? Y(c.value) : H - B - 3;
      const mark = has ? el('rect', { x, y: Math.min(top, base), width: bw, height: Math.max(1.5, Math.abs(base - top)), rx: Math.min(1.5, bw / 3), class: 'b' + (c.id === opts.selected ? ' sel' : '') })
        : el('rect', { x, y: H - B - 3, width: bw, height: 3, class: 'b none' });
      const hit = el('rect', { x: L + i * step, y: T, width: Math.max(step, 2), height: H - T - B, class: 'hit', tabindex: 0, role: 'button', 'aria-label': c.label + ', ' + (has ? fmtSci(c.value) : 'no value' + (c.reason ? ': ' + c.reason : '')) });
      g.appendChild(hit); g.appendChild(mark);
      interactive(hit, host, svg, () => [x + bw / 2, top], () => [{ b: c.label }, has ? { v: fmtSci(c.value), l: opts.valueTitle } : { l: 'no value' + (c.reason ? ': ' + c.reason : '') }], opts.onSelect && (() => opts.onSelect(c.id)));
      svg.appendChild(g);
    });
    host.appendChild(svg);
  }

  return { el, h, fmtSci, scale, tooltip, axis, scatter, progression, ranking, strip };
})();
