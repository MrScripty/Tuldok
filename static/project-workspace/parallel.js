'use strict';
// Parallel coordinates on the Benchmarks tab (docs/plans/training-and-curation/spec-t3.md section 5.2): one vertical
// axis per metric of the benchmark and per recipe setting that varies between its subjects (benchmark_axes), one
// line per subject in its kind of change's colour. The person chooses the axes (at most twelve; the metrics and the
// six settings that go most with the first metric to begin with), moves them left and right, puts a metric whose
// values are all positive on a logarithmic scale, and drags a range on any axis: the lines outside every range are
// faint, the subjects table hides their rows and the charts above draw their points faint. A click on an axis
// without a drag clears its range; "Clear ranges" clears all.
//
// Updating in place (spec-w4): the section is built with the tab (tabs.js's paint) from the tab's settings
// (pcAxes, pcLog, pcBrush, kept per benchmark in state.ui), so a reading that changed something draws it again where
// the person left it. The person's own moves touch only this section (drawn again in place) and, for a range, the
// table's rows and the charts' marks (apply()); nothing is read again.
window.LabParallel = (() => {
  const C = window.LabCharts, h = C.h, el = C.el, S = window.LabScreens;
  const MOST = 12, SETTINGS_FIRST = 6, H = 300, T = 46, B = 30;
  const fmt = C.fmtSci;
  let last = null;   // the benchmark drawn last: { benchmark, data, axes } (apply() reads it)
  const button = (cls, text, onClick, key, label) => { const b = h('button', cls, text); b.type = 'button'; if (key) b.dataset.key = key; if (label) b.setAttribute('aria-label', label); if (onClick) b.addEventListener('click', onClick); return b; };
  const tail = path => { const m = path.match(/([^.\[\]]+|\[[^\]]*\])$/); return m ? m[1].replace(/^\["?|"?\]$/g, '') : path; };

  /** Every axis the answer offers, metrics first: id, kind (metric, number, category), titles and range. */
  function axesOf(data) {
    const out = data.metrics.map(m => ({ id: 'm:' + m.id, kind: 'metric', title: m.title, short: m.title, low: m.low, high: m.high, positive: m.positive, better: m.better, units: m.units, key: m.id }));
    for (const s of data.settings) out.push({ id: 's:' + s.path, kind: s.kind, title: s.path, short: tail(s.path), low: s.low, high: s.high, categories: s.categories, association: s.association, positive: s.kind === 'number' && s.low > 0, key: s.path, count: s.count });
    return out;
  }
  const defaults = all => all.filter(a => a.kind === 'metric').concat(all.filter(a => a.kind !== 'metric').slice(0, SETTINGS_FIRST)).slice(0, MOST).map(a => a.id);
  /** The axes shown, in the person's order: those of the tab's settings that this benchmark has, else the defaults. */
  function shownAxes(all, ui) {
    const byId = new Map(all.map(a => [a.id, a]));
    const kept = Array.isArray(ui.pcAxes) ? ui.pcAxes.filter(id => byId.has(id)).slice(0, MOST) : [];
    return (kept.length ? kept : defaults(all)).map(id => byId.get(id));
  }
  const valueOf = (row, a) => { const v = a.kind === 'metric' ? row.metrics[a.key] : row.settings[a.key]; return v == null ? null : v; };
  const isLog = (a, ui) => a.positive && (ui.pcLog || []).includes(a.id) && a.low > 0 && a.high > a.low;
  /** The axis's scale: t(v) in [0, 1] from its low to its high end, and back. */
  function scaleOf(a, ui) {
    const lo = a.low, hi = a.high;
    if (lo == null || hi == null) return { t: () => 0.5, v: () => null };
    if (isLog(a, ui)) { const l0 = Math.log10(lo), l1 = Math.log10(hi); return { t: v => (Math.log10(Math.max(v, lo)) - l0) / (l1 - l0), v: t => Math.pow(10, l0 + t * (l1 - l0)) }; }
    if (hi === lo) return { t: () => 0.5, v: () => lo };
    return { t: v => (v - lo) / (hi - lo), v: t => lo + t * (hi - lo) };
  }
  /** The ranges drawn, of axes that exist: {id: [low, high]}. */
  function rangesOf(all, ui) { const ids = new Set(all.map(a => a.id)), out = {}; for (const [id, r] of Object.entries(ui.pcBrush || {})) if (ids.has(id) && Array.isArray(r) && r.length === 2) out[id] = r; return out; }
  /** The names of the subjects inside every range, or null when no range is drawn. */
  function keptOf(data, all, ui) {
    const ranges = rangesOf(all, ui), ids = Object.keys(ranges); if (!ids.length) return null;
    const byId = new Map(all.map(a => [a.id, a])), keep = new Set();
    for (const row of data.subjects) if (ids.every(id => { const v = valueOf(row, byId.get(id)); return v != null && v >= ranges[id][0] && v <= ranges[id][1]; })) keep.add(row.subject);
    return keep;
  }

  // ---- The section ------------------------------------------------------------------------------------------------
  function section(data, view, state, act, width) {
    const ui = state.ui;
    if (ui.pcFor !== data.benchmark) { ui.pcFor = data.benchmark; ui.pcAxes = null; ui.pcLog = null; ui.pcBrush = null; }   // the settings are per benchmark
    const all = axesOf(data);
    last = { benchmark: data.benchmark, data, all };
    const sec = h('section', 'pc'); sec.dataset.key = 'pc';
    const ctx = { data, view, state, act, width, sec, all };
    fill(ctx);
    return sec;
  }
  /** Builds the section's content (put in place when it is on the page). */
  function fill(ctx) {
    const { data, state, sec, all } = ctx, ui = state.ui, axes = shownAxes(all, ui), keep = keptOf(data, all, ui);
    const items = [];
    const head = S.parts.sect('Settings and metrics', data.subjects.length + ' ' + (ctx.view.noun || 'subjects') + ' · ' + axes.length + ' of ' + all.length + ' axes');
    const count = h('span', 'pc-count small'); count.setAttribute('aria-live', 'polite'); head.appendChild(count); ctx.count = count;
    items.push(head);
    items.push(h('p', 'small faint bench-desc', ctx.view.lead ? ctx.view.lead + (data.left_out ? ' ' + data.left_out + ' more settings are not offered.' : '') : 'One line per subject through its metrics (the ' + data.statistic + ' over its cases) and the recipe settings that vary between subjects. Drag along an axis to keep the subjects inside a range; the table and the charts above follow. ' + (data.left_out ? data.left_out + ' more settings are not offered.' : '')));
    const host = h('div', 'pc-draw'); ctx.host = host; items.push(host);
    items.push(axisControls(ctx, axes));
    items.push(chooser(ctx, axes));
    draw(ctx, axes, keep);
    setCount(ctx, keep);
    if (sec.isConnected) { const frag = document.createDocumentFragment(); frag.append(...items); S.parts.putInPlace(sec, frag, document.getElementById('main')); }
    else sec.replaceChildren(...items);
  }
  function setCount(ctx, keep) {
    const n = ctx.data.subjects.length, text = keep ? keep.size + ' of ' + n + ' inside the ranges' : 'no range drawn';
    if (ctx.count.textContent !== text) ctx.count.textContent = text;
    ctx.count.dataset.kept = keep ? String(keep.size) : '';
  }

  /** The SVG: the axes, their names and ends, the lines, the ranges, and the axes' hit areas for dragging. */
  function draw(ctx, axes, keep) {
    const { data, view, state, host } = ctx, ui = state.ui, W = Math.max(320, ctx.width), k = axes.length;
    const L = 30, R = 30, X = i => k > 1 ? L + i * (W - L - R) / (k - 1) : W / 2, Y = t => T + (1 - t) * (H - T - B);
    const gap = k > 1 ? (W - L - R) / (k - 1) : W, chars = Math.max(4, Math.floor(gap / 6.4) - 1);
    const cut = (t, n) => t.length > n ? t.slice(0, Math.max(1, n - 1)) + '…' : t;
    const svg = el('svg', { viewBox: `0 0 ${W} ${H}`, role: 'group', 'aria-label': 'Parallel coordinates: ' + data.subjects.length + ' subjects through ' + k + ' axes: ' + axes.map(a => a.short).join(', '), class: 'pc-svg' });
    const scales = axes.map(a => scaleOf(a, ui));
    // The lines.
    const lines = el('g', { class: 'pc-lines' });
    const sel = view.selected !== undefined ? view.selected : state.sel.benchmarks || null;   // a sweep's view gives its own
    for (const row of data.subjects) {
      const s = view.byName.get(row.subject), kind = s ? s.kind : 'other';
      let d = '', open = false;
      axes.forEach((a, i) => { const v = valueOf(row, a); if (v == null || !Number.isFinite(v)) { open = false; return; } d += (open ? 'L' : 'M') + X(i).toFixed(1) + ',' + Y(scales[i].t(v)).toFixed(1); open = true; });
      if (!d) continue;
      const on = s && s.key === sel;
      const p = el('path', { d, class: 'pcl ' + kind + (keep && !keep.has(row.subject) ? ' out' : '') + (on ? ' on' : ''), 'data-subject': row.subject });
      p.appendChild(el('title', {}, (s ? s.full : row.title) + ': ' + axes.map(a => a.short + ' ' + shownValue(a, valueOf(row, a))).join(', ')));
      lines.appendChild(p);
    }
    svg.appendChild(lines);
    // The axes.
    const ranges = rangesOf(ctx.all, ui);
    axes.forEach((a, i) => {
      const x = X(i), g = el('g', { class: 'pc-axis', 'data-axis': a.id }), right = i < k - 1 || k === 1, anchor = right ? 'start' : 'end', dx = right ? 5 : -5;
      g.appendChild(el('line', { x1: x, y1: Y(0), x2: x, y2: Y(1), class: 'pc-line' }));
      const title = el('text', { x, y: 14, 'text-anchor': i === 0 && k > 1 ? 'start' : i === k - 1 && k > 1 ? 'end' : 'middle', class: 'pc-title' }, cut(a.short, chars));
      title.appendChild(el('title', {}, a.title + (a.kind === 'metric' ? '' : ' (' + a.kind + ')')));
      g.appendChild(title);
      const sub = a.kind === 'metric' ? (a.better === 'lower' ? 'lower better' : a.better === 'higher' ? 'higher better' : '') + (isLog(a, ui) ? ' · log' : '') : a.association == null ? '' : 'ρ ' + a.association.toFixed(2);
      g.appendChild(el('text', { x, y: 28, 'text-anchor': i === 0 && k > 1 ? 'start' : i === k - 1 && k > 1 ? 'end' : 'middle', class: 'pc-sub' }, cut(sub, chars)));
      if (a.kind === 'category') {
        const n = a.categories.length, every = Math.max(1, Math.ceil(n / Math.max(1, Math.floor((H - T - B) / 13))));
        a.categories.forEach((c, j) => { if (j % every && j !== n - 1) return; g.appendChild(el('text', { x: x + dx, y: Y(n > 1 ? j / (n - 1) : 0.5) + 4, 'text-anchor': anchor, class: 'pc-tick' }, cut(typeof c === 'string' ? c : JSON.stringify(c), Math.min(12, chars)))); });
      } else if (a.low != null) {
        g.appendChild(el('text', { x: x + dx, y: Y(1) + 4, 'text-anchor': anchor, class: 'pc-tick' }, fmt(a.high)));
        g.appendChild(el('text', { x: x + dx, y: Y(0) + 4, 'text-anchor': anchor, class: 'pc-tick' }, fmt(a.low)));
      }
      const r = ranges[a.id];
      if (r) { const y0 = Y(scales[i].t(r[1])), y1 = Y(scales[i].t(r[0])); g.appendChild(el('rect', { x: x - 7, y: Math.min(y0, y1), width: 14, height: Math.max(2, Math.abs(y1 - y0)), class: 'pc-brush', 'data-low': r[0], 'data-high': r[1] })); }
      const hit = el('rect', { x: x - 12, y: Y(1) - 6, width: 24, height: Y(0) - Y(1) + 12, class: 'pc-hit', 'data-axis': a.id });
      hit.appendChild(el('title', {}, 'Drag to keep a range of ' + a.title + '; a click clears it'));
      g.appendChild(hit);
      brushing(ctx, hit, g, a, scales[i], Y, x);
      svg.appendChild(g);
    });
    host.replaceChildren(svg);
    ctx.svg = svg;
  }
  const shownValue = (a, v) => v == null ? '—' : a.kind === 'category' ? (c => typeof c === 'string' ? c : JSON.stringify(c))(a.categories[v]) : fmt(v);

  /** A range dragged on an axis: kept in the tab's settings, the lines, the table and the charts set in place. */
  function brushing(ctx, hit, g, a, scale, Y, x) {
    let start = null, box = null;
    const at = ev => { const pt = ctx.svg.createSVGPoint(); pt.x = ev.clientX; pt.y = ev.clientY; return pt.matrixTransform(ctx.svg.getScreenCTM().inverse()).y; };
    const clamp = y => Math.min(Y(0), Math.max(Y(1), y));
    hit.addEventListener('pointerdown', ev => {
      ev.preventDefault(); start = clamp(at(ev)); try { hit.setPointerCapture(ev.pointerId); } catch (e) { /* a synthetic pointer */ }
      box = el('rect', { x: x - 7, y: start, width: 14, height: 0, class: 'pc-brush pc-dragging' }); g.insertBefore(box, hit);
    });
    hit.addEventListener('pointermove', ev => { if (start === null) return; const y = clamp(at(ev)); box.setAttribute('y', String(Math.min(start, y))); box.setAttribute('height', String(Math.abs(y - start))); });
    const end = ev => {
      if (start === null) return;
      const y = clamp(at(ev)), moved = Math.abs(y - start) >= 3, ui = ctx.state.ui, ranges = Object.assign({}, ui.pcBrush || {});
      const y0 = start; start = null;
      if (moved) { const t0 = (Y(0) - Math.max(y, y0)) / (Y(0) - Y(1)), t1 = (Y(0) - Math.min(y, y0)) / (Y(0) - Y(1)); ranges[a.id] = [scale.v(t0), scale.v(t1)]; }
      else delete ranges[a.id];
      ctx.act.keepUI('pcBrush', Object.keys(ranges).length ? ranges : null);
      fill(ctx); apply(document.getElementById('main'), ctx.view, ctx.state);
    };
    hit.addEventListener('pointerup', end);
    hit.addEventListener('pointercancel', () => { start = null; if (box) box.remove(); });
  }

  /** The chosen axes in order, each moved left or right, put on a log scale or taken away; and Clear ranges. */
  function axisControls(ctx, axes) {
    const ui = ctx.state.ui, box = h('div', 'pc-axes'), ids = axes.map(a => a.id);
    const set = (k, v) => { ctx.act.keepUI(k, v); fill(ctx); apply(document.getElementById('main'), ctx.view, ctx.state); };
    axes.forEach((a, i) => {
      const chip = h('span', 'pc-ax' + (a.kind === 'metric' ? ' metric' : '')); chip.dataset.axis = a.id;
      const move = (d) => { const next = ids.slice(); next.splice(i, 1); next.splice(i + d, 0, a.id); set('pcAxes', next); };
      const left = button('pc-mv', '◀', () => move(-1), 'pc-left-' + a.id, 'Move ' + a.short + ' left'); left.disabled = i === 0; chip.appendChild(left);
      const name = h('span', 'pc-name', a.short); name.title = a.title; chip.appendChild(name);
      const right = button('pc-mv', '▶', () => move(1), 'pc-right-' + a.id, 'Move ' + a.short + ' right'); right.disabled = i === axes.length - 1; chip.appendChild(right);
      if (a.positive && a.kind !== 'category') { const on = isLog(a, ui), lg = button('pc-log', 'log', () => { const list = (ui.pcLog || []).filter(x => x !== a.id); if (!on) list.push(a.id); set('pcLog', list); }, 'pc-log-' + a.id, (on ? 'Linear scale for ' : 'Logarithmic scale for ') + a.short); lg.setAttribute('aria-pressed', String(on)); chip.appendChild(lg); }
      const x = button('pc-x', '×', () => set('pcAxes', ids.filter(id => id !== a.id)), 'pc-drop-' + a.id, 'Take ' + a.short + ' away'); x.disabled = axes.length <= 2; chip.appendChild(x);
      box.appendChild(chip);
    });
    const clear = button('btn sm ghost', 'Clear ranges', () => set('pcBrush', null), 'pc-clear'); clear.disabled = !Object.keys(rangesOf(ctx.all, ui)).length; box.appendChild(clear);
    return box;
  }
  /** Every axis on offer, the settings with how strongly they go with the first metric; at most twelve on. */
  function chooser(ctx, axes) {
    const ui = ctx.state.ui, on = new Set(axes.map(a => a.id)), d = h('details', 'pc-choose'); d.dataset.key = 'pc-choose';
    if (ui.pcChooser) d.open = true;
    d.addEventListener('toggle', () => { ctx.state.ui.pcChooser = d.open; });
    d.appendChild(h('summary', null, 'Choose axes · ' + on.size + ' of at most ' + MOST));
    const ul = h('ul', 'pc-list');
    for (const a of ctx.all) {
      const li = h('li'), l = h('label'), cb = h('input'); cb.type = 'checkbox'; cb.checked = on.has(a.id); cb.disabled = !cb.checked && on.size >= MOST || cb.checked && on.size <= 2; cb.dataset.key = 'pc-pick-' + a.id;
      cb.addEventListener('change', () => { const ids = axes.map(x => x.id); ctx.act.keepUI('pcAxes', cb.checked ? ids.concat([a.id]) : ids.filter(id => id !== a.id)); fill(ctx); apply(document.getElementById('main'), ctx.view, ctx.state); });
      l.appendChild(cb); l.appendChild(h('span', a.kind === 'metric' ? null : 'mono', a.title));
      l.appendChild(h('span', 'small faint', a.kind === 'metric' ? ' metric' : ' ' + a.kind + (a.association == null ? '' : ' · ρ ' + a.association.toFixed(2)) + ' · ' + a.count + ' subjects'));
      li.appendChild(l); ul.appendChild(li);
    }
    d.appendChild(ul);
    return d;
  }

  /**
   * Sets the ranges drawn on the axes into the rest of the tab, under root (the main area, or the tab's content
   * while it is built): the subjects table hides the rows outside them and says how many it shows, and the
   * charts' marks of those subjects are faint. Nothing is read; nothing else is drawn.
   */
  function apply(root, view, state) {
    const keep = last && last.benchmark === view.name ? keptOf(last.data, last.all, state.ui) : null;
    for (const tr of root.querySelectorAll('.bench-all tr[data-subject]')) { const hide = !!keep && !keep.has(tr.dataset.subject); if (tr.hidden !== hide) tr.hidden = hide; }
    for (const mark of root.querySelectorAll('.bench-chart [data-id]')) { const s = view.byKey.get(mark.dataset.id), out = !!keep && !!s && !keep.has(s.name); mark.parentNode.classList.toggle('pc-out', out); }
    const table = root.querySelector('.bench-all');
    if (table) {
      let note = table.querySelector('.pc-filtered');
      const shown = keep ? [...table.querySelectorAll('tr[data-subject]')].filter(tr => !tr.hidden).length : null;
      if (keep && !note) { note = h('p', 'small muted pc-filtered'); const sect = table.querySelector('.sect'); if (sect) sect.after(note); else table.prepend(note); }
      if (keep) { const text = shown + ' rows shown: the subjects inside the ranges drawn on the axes of Settings and metrics.'; if (note.textContent !== text) note.textContent = text; note.dataset.shown = String(shown); }
      else if (note) note.remove();
    }
  }

  return { section, apply };
})();
