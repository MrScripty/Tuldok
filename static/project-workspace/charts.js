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
  return { el, h, fmtSci, scale, tooltip };
})();
