'use strict';
// What a run's training script logged (docs/plans/training-and-curation/spec-t1.md section 6): the block "Training"
// of a run's drawer on the Train tab. Curves of the chosen series, one small chart a series (never two scales on
// one axis), each run in its own colour (the run opened and up to three overlaid from "Compare with"), smoothing,
// a log scale, step or time across, the band of each bucket's least and greatest value when a long series is
// reduced, and the checkpoints as ticks; under them, each tensor's histograms over the steps as a heat strip
// (weights or gradients), read when the strip comes on screen; and the last samples of a name as a strip.
//
// Updating in place (spec-w4): tabs.js reads the block's data with the drawer (read()) and builds it with the
// drawer off the page (block()); the answers are kept here by run for as long as the page lives, so a drawer drawn
// again (the run ended) builds the block from what is held. While a run in view is active, every reading of the
// page (tick(), every two seconds while something builds) asks `training` once a run; when lines were added it asks
// for the new buckets only (training_series from where the page is), draws the canvases again, reads again the
// strips on screen when histograms were added, and appends the new samples. The block is never built again by a
// reading, and a reading that found nothing new touches no element. The person's own choices (a series, a run to
// compare, weights or gradients, all the tensors, a sample name) build the block's content again in the same
// element; smoothing, log scale and step or time only draw the canvases again. The settings that are not of one
// run are kept in the address (trWith, trSeries, trSmooth, trLog, trX).
window.LabTraining = (() => {
  const P = window.TuldokProject, C = window.LabCharts, h = C.h, D = window.LabInside.drawing;
  const fmt = v => v == null || !Number.isFinite(v) ? '—' : C.fmtSci(v);
  const button = (cls, text, onClick) => { const b = h('button', cls, text); b.type = 'button'; if (onClick) b.addEventListener('click', onClick); return b; };
  const COLOURS = ['--run-1', '--run-2', '--run-3', '--run-4'];   // the runs in view, in the order they were added
  const RUNS_MOST = 4, SERIES_MOST = 4, POINTS = 800, HIST_ROWS = 120, HIST_BINS = 32, STRIPS_FIRST = 8, SAMPLES_SHOWN = 12;
  const CHART_HEIGHT = 150, STRIP_HEIGHT = 36, SAMPLE_SIZE = 72;
  const ACTIVE = ['queued', 'running'];
  /** Sets an element's text in place: its one text node's data when it has one, so no node is added or removed. */
  const setText = (el, text) => { if (el.childNodes.length === 1 && el.firstChild.nodeType === 3) { if (el.firstChild.data !== text) el.firstChild.data = text; } else if (el.textContent !== text) el.textContent = text; };
  const seconds = s => s == null ? '—' : s < 90 ? s.toFixed(s < 10 ? 1 : 0) + ' s' : s < 5400 ? (s / 60).toFixed(1) + ' min' : (s / 3600).toFixed(2) + ' h';

  // ---- What is held, by run, for the page's life ---------------------------------------------------------------
  const held = new Map();   // run id -> { over, series: Map(name -> {size, points, lines, buckets}), samples: Map(name -> {total, items}), arrays: Map(index -> answer), hist: Map(key -> {answer, at}) }
  const runOf = id => { let r = held.get(id); if (!r) { r = { over: null, series: new Map(), samples: new Map(), arrays: new Map(), hist: new Map() }; held.set(id, r); } return r; };
  let view = null;   // the block on screen: { el, id, ids, settings, act, labelOf, sampleName, kind, all, charts: Map(name -> canvas), redraw() }

  /** The settings the address keeps, from the tab's state. */
  function settingsOf(ui, id) {
    const others = String(ui.trWith || '').split(',').filter(x => x && x !== id).slice(0, RUNS_MOST - 1);
    const smooth = Math.min(0.99, Math.max(0, Number(ui.trSmooth) || 0));
    return { with: others, series: String(ui.trSeries || '').split(',').filter(Boolean).slice(0, SERIES_MOST), smooth, log: ui.trLog === '1', x: ui.trX === 'time' ? 'time' : 'step' };
  }
  /** The series shown: the chosen ones the runs logged, else loss (or the first). */
  function shownSeries(ids, chosen) {
    const names = [];
    for (const id of ids) { const o = runOf(id).over; if (o) for (const s of o.series) if (!names.includes(s.name)) names.push(s.name); }
    const picked = chosen.filter(n => names.includes(n));
    if (picked.length) return { names, picked };
    const first = names.includes('loss') ? 'loss' : names[0];
    return { names, picked: first ? [first] : [] };
  }

  // ---- Reading ---------------------------------------------------------------------------------------------------
  async function overview(id) { const r = runOf(id); r.over = await P.call('training', { run: id }); return r.over; }
  /** The buckets of the named series of a run that are new since what is held (all of them when the size changed). */
  async function seriesOf(id, names) {
    const r = runOf(id), o = r.over; if (!o) return false;
    const want = names.filter(n => o.series.some(s => s.name === n) && (!r.series.has(n) || r.series.get(n).lines !== o.lines));
    if (!want.length) return false;
    const answer = await P.call('training_series', { run: id, most: POINTS, series: want.map(n => { const s = r.series.get(n); return s ? { name: n, size: s.size, since: Math.max(0, s.buckets.length - 1) } : { name: n }; }) });
    for (const a of answer.series) {
      const s = r.series.get(a.name);
      if (s && s.size === a.size && a.first <= s.buckets.length) s.buckets.splice(a.first, Infinity, ...a.buckets);
      else r.series.set(a.name, { size: a.size, buckets: a.buckets });
      Object.assign(r.series.get(a.name), { size: a.size, points: a.points, lines: answer.lines });
    }
    return true;
  }
  /** The last samples of one name; only those added since what is held. */
  async function samplesOf(id, name) {
    const r = runOf(id), o = r.over; if (!o || !name) return false;
    const listed = o.samples.find(s => s.name === name); if (!listed) return false;
    const s = r.samples.get(name);
    if (s && s.total === listed.count) return false;
    const from = s ? s.total : Math.max(0, listed.count - SAMPLES_SHOWN);
    const answer = await P.call('training_samples', { run: id, name, offset: Math.max(from, listed.count - SAMPLES_SHOWN), limit: SAMPLES_SHOWN });
    const items = (s ? s.items : []).concat(answer.samples).slice(-SAMPLES_SHOWN);
    r.samples.set(name, { total: answer.total, items });
    return answer.samples;
  }
  const sampleName = (o, chosen) => o && o.samples.length ? (o.samples.some(s => s.name === chosen) ? chosen : o.samples[0].name) : null;

  /**
   * What the block of run id needs, for the drawer's load: the run's and the overlaid runs' overviews (asked
   * afresh), the new buckets of the series shown and the last samples. Resolves once complete.
   */
  async function read(id, ui) {
    const settings = settingsOf(ui || {}, id), ids = [id].concat(settings.with);
    await Promise.all(ids.map(x => overview(x).catch(error => { if (x === id) throw error; runOf(x).over = null; })));
    const { picked } = shownSeries(ids, settings.series);
    await Promise.all(ids.map(x => seriesOf(x, picked)));
    const r = runOf(id); r.sampleName = sampleName(r.over, r.sampleName);
    await samplesOf(id, r.sampleName);
    return { id, settings };
  }

  // ---- The block -------------------------------------------------------------------------------------------------
  /** The block for what read() gave, built off the page; act: the tab's actions (keepUI); labelOf(run id) names a run. */
  function block(value, act, labelOf, runs) {
    const el = h('div', 'trn'); el.dataset.run = value.id;
    view = { el, id: value.id, settings: value.settings, act, labelOf, runs: runs || [], charts: new Map(), kind: (view && view.id === value.id && view.kind) || 'weights', all: view && view.id === value.id ? view.all : false };
    fill(view);
    return el;
  }
  const idsOf = v => [v.id].concat(v.settings.with.filter(x => runOf(x).over));
  /** Builds the content of the block (in its element, on or off the page). */
  function fill(v) {
    const el = v.el, o = runOf(v.id).over;
    el.textContent = '';
    el.appendChild(h('h3', null, 'Training'));
    if (!o || !o.present || (!o.lines && !o.histogram_lines && !o.sample_lines)) {
      const p = h('p', 'note trn-none', o && o.run.active ? 'Nothing logged yet. A script logs its training into training/ of its output (tuldok_log, or by hand); it is drawn here as it arrives.' : 'This run logged no training. A script logs into training/ of its output, with tuldok_log or by hand.');
      el.appendChild(p); v.charts = new Map(); return;
    }
    const ids = idsOf(v);
    // The line under the title: where the run is.
    const at = h('p', 'small trn-at'); at.dataset.key = 'trn-at'; el.appendChild(at); v.at = at; setAt(v);
    // Series and controls.
    const { names, picked } = shownSeries(ids, v.settings.series);
    v.picked = picked;
    const chooser = h('div', 'trn-series'); chooser.setAttribute('role', 'group'); chooser.setAttribute('aria-label', 'Series shown');
    v.chooser = chooser; chooserButtons(v, names);
    el.appendChild(chooser);
    el.appendChild(controls(v));
    // The runs in view: a legend, and Compare with.
    el.appendChild(legend(v, ids));
    // One chart a series.
    v.charts = new Map();
    for (const n of picked) {
      const fig = h('figure', 'trn-fig'); const cap = h('figcaption', 'small trn-cap'); cap.appendChild(h('b', null, n)); const sum = h('span', 'faint'); cap.appendChild(sum); fig.appendChild(cap);
      const wrap = h('div', 'trn-plot'); const c = h('canvas', 'trn-chart'); c.dataset.series = n; c.setAttribute('role', 'img'); wrap.appendChild(c);
      const tip = h('div', 'trn-tip'); tip.hidden = true; wrap.appendChild(tip); fig.appendChild(wrap);
      const note = h('p', 'small faint trn-note'); fig.appendChild(note);
      el.appendChild(fig);
      const chart = { canvas: c, tip, sum, note, name: n };
      v.charts.set(n, chart);
      D.paints(c, () => drawChart(v, chart));
      hover(v, chart);
    }
    if (!picked.length) el.appendChild(h('p', 'note', 'This run logged no scalar series.'));
    // Histograms and samples.
    v.histBox = h('div', 'trn-hists-slot'); v.sampleBox = h('div', 'trn-samples-slot');
    el.appendChild(v.histBox); el.appendChild(v.sampleBox);
    histograms(v);
    samples(v);
    const problems = o.problems || [];
    if (o.bad_lines || o.truncated) {
      const p = h('p', 'small warnline trn-problems', (o.bad_lines ? o.bad_lines + ' line' + (o.bad_lines === 1 ? '' : 's') + ' could not be read' + (problems.length ? ' (first: ' + problems[0].file + ' line ' + problems[0].line + ', ' + problems[0].problem.replace(/\.$/, '') + ')' : '') + '. ' : '') + (o.truncated ? 'Only the first part of a long file is read.' : ''));
      el.appendChild(p);
    }
    if (o.other_keys && o.other_keys.length) el.appendChild(h('p', 'small faint', 'Also logged, not drawn: ' + o.other_keys.slice(0, 8).join(', ') + (o.other_keys.length > 8 ? '…' : '')));
  }
  /** The buttons of the series chooser, one a name; a name already there keeps its button. */
  function chooserButtons(v, names) {
    const have = new Set([...v.chooser.children].map(b => b.dataset.series));
    for (const n of names) {
      if (have.has(n)) continue;
      const b = button('btn sm', n, () => toggleSeries(v, n)); b.setAttribute('aria-pressed', String(v.picked.includes(n))); b.dataset.key = 'trn-series-' + n; b.dataset.series = n;
      if (!v.picked.includes(n) && v.picked.length >= SERIES_MOST) b.disabled = true;
      v.chooser.appendChild(b);
    }
  }
  function setAt(v) {
    const o = runOf(v.id).over; if (!v.at || !o) return;
    const text = (o.last_step == null ? 'No metrics yet' : 'Step ' + o.last_step.toLocaleString('en-GB') + ' · ' + seconds(o.last_time)) + ' · ' + o.lines.toLocaleString('en-GB') + ' lines' + (o.started_at ? ' · started ' + P.day(o.started_at) : '') + (o.run.active ? ' · read live' : '');
    setText(v.at, text);
  }
  function controls(v) {
    const row = h('div', 'trn-controls');
    const sm = h('label', 'trn-smooth'); sm.appendChild(h('span', 'small', 'Smoothing'));
    const range = h('input'); range.type = 'range'; range.min = '0'; range.max = '0.99'; range.step = '0.01'; range.value = String(v.settings.smooth); range.dataset.key = 'trn-smooth';
    const shown = h('span', 'small num', v.settings.smooth.toFixed(2)); sm.appendChild(range); sm.appendChild(shown);
    range.addEventListener('input', () => { v.settings.smooth = Number(range.value); shown.textContent = v.settings.smooth.toFixed(2); v.act.keepUI('trSmooth', v.settings.smooth ? String(v.settings.smooth) : null); drawAll(v); });
    row.appendChild(sm);
    const log = button('btn sm', 'Log scale', () => { v.settings.log = !v.settings.log; log.setAttribute('aria-pressed', String(v.settings.log)); v.act.keepUI('trLog', v.settings.log ? '1' : null); drawAll(v); });
    log.setAttribute('aria-pressed', String(v.settings.log)); log.dataset.key = 'trn-log'; row.appendChild(log);
    const x = h('select'); x.dataset.key = 'trn-x'; x.setAttribute('aria-label', 'Across'); for (const [val, text] of [['step', 'By step'], ['time', 'By time']]) { const op = h('option', null, text); op.value = val; x.appendChild(op); } x.value = v.settings.x;
    x.addEventListener('change', () => { v.settings.x = x.value; v.act.keepUI('trX', x.value === 'time' ? 'time' : null); drawAll(v); });
    row.appendChild(x);
    return row;
  }
  function legend(v, ids) {
    const box = h('div', 'trn-runs');
    const ul = h('ul', 'trn-legend');
    ids.forEach((id, i) => {
      const o = runOf(id).over, li = h('li'); li.dataset.run = id;
      const sw = h('span', 'trn-swatch'); sw.style.background = 'var(' + COLOURS[i] + ')'; li.appendChild(sw);
      li.appendChild(h('span', null, v.labelOf(id)));
      li.appendChild(h('span', 'small faint', o ? o.run.state : ''));
      if (i > 0) { const x = button('btn sm ghost trn-remove', '×', () => setWith(v, v.settings.with.filter(w => w !== id))); x.setAttribute('aria-label', 'Stop comparing with ' + v.labelOf(id)); x.dataset.key = 'trn-remove-' + id; li.appendChild(x); }
      ul.appendChild(li);
    });
    box.appendChild(ul);
    if (ids.length < RUNS_MOST) {
      const s = h('select'); s.dataset.key = 'trn-with'; s.setAttribute('aria-label', 'Compare with another run');
      const first = h('option', null, 'Compare with…'); first.value = ''; s.appendChild(first);
      const me = v.runs.find(r => r.id === v.id);
      const others = v.runs.filter(r => !ids.includes(r.id) && r.state !== 'queued');
      others.sort((a, b) => (me && b.reference === me.reference) - (me && a.reference === me.reference));
      for (const r of others.slice(0, 50)) { const op = h('option', null, v.labelOf(r.id) + ' · ' + r.state); op.value = r.id; s.appendChild(op); }
      s.disabled = !others.length;
      s.addEventListener('change', () => { if (s.value) setWith(v, v.settings.with.concat([s.value])); });
      box.appendChild(s);
    }
    return box;
  }
  /** The person chose other runs to compare with: read them, then build the content again in place. */
  async function setWith(v, others) {
    v.settings.with = others.slice(0, RUNS_MOST - 1);
    v.act.keepUI('trWith', v.settings.with.join(',') || null);
    await rebuild(v);
  }
  function toggleSeries(v, n) {
    const now = v.picked.includes(n) ? v.picked.filter(x => x !== n) : v.picked.concat([n]).slice(0, SERIES_MOST);
    v.settings.series = now;
    v.act.keepUI('trSeries', now.join(',') || null);
    rebuild(v);
  }
  /** Reads what the content needs and builds it again in the block's element, the focus kept by data-key. */
  async function rebuild(v) {
    v.el.setAttribute('aria-busy', 'true');
    try {
      const ids = [v.id].concat(v.settings.with);
      await Promise.all(ids.map(x => runOf(x).over ? null : overview(x).catch(() => null)));
      const { picked } = shownSeries(ids, v.settings.series);
      await Promise.all(ids.map(x => seriesOf(x, picked)));
      await samplesOf(v.id, runOf(v.id).sampleName);
    } catch (error) { console.warn(error); }
    v.el.removeAttribute('aria-busy');
    if (view !== v || !v.el.isConnected) return;
    const key = document.activeElement && v.el.contains(document.activeElement) ? document.activeElement.dataset.key : null;
    fill(v);
    if (key) { const again = v.el.querySelector('[data-key="' + CSS.escape(key) + '"]'); if (again) again.focus({ preventScroll: true }); }
  }
  const drawAll = v => { for (const chart of v.charts.values()) drawChart(v, chart); };

  // ---- A chart ---------------------------------------------------------------------------------------------------
  /** The lines of a chart: for each run in view, its points [x, y, low, high] (y the bucket's mean). */
  function linesOf(v, name) {
    return idsOf(v).map((id, i) => {
      const s = runOf(id).series.get(name), colour = D.token(COLOURS[i]);
      const pts = s ? s.buckets.filter(b => b[3] != null).map(b => [v.settings.x === 'time' ? b[2] : b[1], b[3], b[4], b[5], b[1], b[2]]) : [];
      return { id, colour, pts, size: s ? s.size : 1, points: s ? s.points : 0 };
    });
  }
  /** Exponential moving average with the start's bias removed, as TensorBoard draws it. */
  function smooth(values, w) {
    if (!w) return values;
    let last = 0, n = 0; return values.map(y => { last = last * w + (1 - w) * y; n++; return last / (1 - Math.pow(w, n)); });
  }
  function scaleOf(lines, log) {
    let x0 = Infinity, x1 = -Infinity, y0 = Infinity, y1 = -Infinity;
    for (const l of lines) for (const p of l.pts) {
      x0 = Math.min(x0, p[0]); x1 = Math.max(x1, p[0]);
      for (const y of [p[1], p[2], p[3]]) if (y != null && (!log || y > 0)) { y0 = Math.min(y0, y); y1 = Math.max(y1, y); }
    }
    if (!Number.isFinite(x0)) return null;
    if (x1 === x0) { x0 -= 0.5; x1 += 0.5; }
    if (!Number.isFinite(y0)) return null;
    let t = log ? [Math.log10(y0), Math.log10(y1)] : [y0, y1];
    if (t[1] === t[0]) t = [t[0] - (Math.abs(t[0]) || 1) * 0.05, t[1] + (Math.abs(t[1]) || 1) * 0.05];
    const pad = (t[1] - t[0]) * 0.06;
    return { x0, x1, y0: t[0] - pad, y1: t[1] + pad, log };
  }
  const ticks = (a, b, n) => { const span = b - a, step0 = Math.pow(10, Math.floor(Math.log10(span / n))), err = n / (span / step0), step = step0 * (err <= 0.15 ? 10 : err <= 0.35 ? 5 : err <= 0.75 ? 2 : 1); const out = []; for (let t = Math.ceil(a / step) * step; t <= b + step * 1e-9; t += step) out.push(+t.toPrecision(12)); return out; };
  function drawChart(v, chart) {
    const c = chart.canvas, size = D.fit(c, CHART_HEIGHT); if (!size) return;
    const [W, H] = size, dpr = window.devicePixelRatio || 1, g = c.getContext('2d');
    g.setTransform(1, 0, 0, 1, 0, 0); g.clearRect(0, 0, W, H); g.scale(dpr, dpr);
    const w = W / dpr, hh = H / dpr, L = 48, R = 8, T = 8, B = 20;
    const lines = linesOf(v, chart.name), sc = scaleOf(lines, v.settings.log);
    chart.lines = lines; chart.scale = sc; chart.box = { L, R, T, B, w, hh };
    const ink = 'rgb(' + D.token('--ink-3').join(',') + ')', grid = 'rgb(' + D.token('--grid').join(',') + ')';
    g.font = '11px ' + getComputedStyle(document.body).fontFamily; g.fillStyle = ink; g.strokeStyle = grid; g.lineWidth = 1;
    const total = lines.reduce((n, l) => n + l.pts.length, 0);
    c.dataset.points = String(total); c.dataset.drawn = String(Number(c.dataset.drawn || 0) + 1);
    c.dataset.last = lines[0] && lines[0].pts.length ? String(lines[0].pts[lines[0].pts.length - 1][4]) : '';
    c.dataset.lines = String(lines.filter(l => l.pts.length).length);
    const nonpos = v.settings.log && lines.some(l => l.pts.some(p => p[1] <= 0));
    const reduced = lines.find(l => l.size > 1);
    setText(chart.note, [reduced ? 'Each point is the mean of ' + reduced.size + ' logged values; the band their least and greatest.' : '', nonpos ? 'Values of 0 or less are left out on the log scale.' : '', v.settings.smooth ? 'Smoothed (' + v.settings.smooth.toFixed(2) + '); the faint line is as logged.' : ''].filter(Boolean).join(' '));
    const main = runOf(v.id).series.get(chart.name), last = main && main.buckets.length ? main.buckets[main.buckets.length - 1][3] : null;
    setText(chart.sum, main ? ' · ' + main.points.toLocaleString('en-GB') + ' points · last ' + fmt(last) : ' · not logged by this run');
    c.setAttribute('aria-label', chart.name + ' against the ' + v.settings.x + ', ' + lines.filter(l => l.pts.length).length + ' run' + (lines.length === 1 ? '' : 's') + (last != null ? '; the last value of this run ' + fmt(last) : ''));
    if (!sc) { g.fillText('Nothing to draw yet.', L, T + 14); return; }
    const X = x => L + (x - sc.x0) / (sc.x1 - sc.x0) * (w - L - R), Y = y => T + (1 - ((sc.log ? Math.log10(y) : y) - sc.y0) / (sc.y1 - sc.y0)) * (hh - T - B);
    chart.X = X; chart.Y = Y;
    // Grid and axes.
    const yt = sc.log ? ticks(sc.y0, sc.y1, 3).filter(t => Number.isInteger(t)).map(t => Math.pow(10, t)) : ticks(sc.y0, sc.y1, 3);
    g.textAlign = 'right'; g.textBaseline = 'middle';
    for (const t of yt) { const y = Y(t); if (y < T - 1 || y > hh - B + 1) continue; g.beginPath(); g.moveTo(L, Math.round(y) + 0.5); g.lineTo(w - R, Math.round(y) + 0.5); g.stroke(); g.fillText(C.fmtSci(t), L - 4, y); }
    g.textAlign = 'center'; g.textBaseline = 'top';
    for (const t of ticks(sc.x0, sc.x1, 4)) { const x = X(t); if (x < L - 1 || x > w - R + 1) continue; g.fillText(v.settings.x === 'time' ? seconds(t) : t.toLocaleString('en-GB'), x, hh - B + 4); }
    // Checkpoints of the run opened, as ticks on the step axis.
    const o = runOf(v.id).over;
    if (o && v.settings.x === 'step') { g.strokeStyle = ink; for (const k of o.checkpoints || []) { const x = X(k.step); if (x < L || x > w - R) continue; g.beginPath(); g.moveTo(x, hh - B); g.lineTo(x, hh - B - 5); g.stroke(); } }
    // Bands, then raw lines (faint when smoothed), then smoothed lines.
    g.save(); g.beginPath(); g.rect(L, T, w - L - R, hh - T - B); g.clip();
    const ok = y => y != null && (!sc.log || y > 0);
    for (const l of lines) {
      const rgb = l.colour.join(',');
      if (l.size > 1) {
        const band = l.pts.filter(p => ok(p[2]) && ok(p[3]));
        if (band.length > 1) { g.fillStyle = 'rgba(' + rgb + ',0.16)'; g.beginPath(); band.forEach((p, i) => (i ? g.lineTo : g.moveTo).call(g, X(p[0]), Y(p[3]))); for (let i = band.length - 1; i >= 0; i--) g.lineTo(X(band[i][0]), Y(band[i][2])); g.closePath(); g.fill(); }
      }
      const path = (ys, alpha, width) => { g.strokeStyle = 'rgba(' + rgb + ',' + alpha + ')'; g.lineWidth = width; g.lineJoin = 'round'; g.beginPath(); let on = false; l.pts.forEach((p, i) => { const y = ys[i]; if (!ok(y)) { on = false; return; } if (on) g.lineTo(X(p[0]), Y(y)); else { g.moveTo(X(p[0]), Y(y)); on = true; } }); g.stroke(); if (l.pts.length === 1 && ok(ys[0])) { g.fillStyle = g.strokeStyle; g.beginPath(); g.arc(X(l.pts[0][0]), Y(ys[0]), 3, 0, 7); g.fill(); } };
      const raw = l.pts.map(p => p[1]);
      if (v.settings.smooth) { path(raw, 0.25, 1); path(smoothLog(raw, v.settings.smooth, sc.log), 1, 2); }
      else path(raw, 1, 2);
    }
    g.restore();
  }
  /** Smoothing in the drawn space: on a log scale the logarithms are smoothed, so a falling loss is not pulled up. */
  function smoothLog(raw, w, log) {
    if (!log) return smooth(raw, w);
    const out = new Array(raw.length).fill(null), idx = [], logs = [];
    raw.forEach((y, i) => { if (y > 0) { idx.push(i); logs.push(Math.log10(y)); } });
    smooth(logs, w).forEach((y, k) => { out[idx[k]] = Math.pow(10, y); });
    return out;
  }
  function hover(v, chart) {
    const c = chart.canvas, tip = chart.tip;
    c.addEventListener('mousemove', e => {
      const sc = chart.scale; if (!sc || !chart.X) return;
      const r = c.getBoundingClientRect(), mx = e.clientX - r.left, { L, R, w } = chart.box;
      if (mx < L || mx > w - R) { tip.hidden = true; return; }
      const x = sc.x0 + (mx - L) / (w - L - R) * (sc.x1 - sc.x0);
      tip.textContent = '';
      const head = h('div', 'trn-tip-head', (v.settings.x === 'time' ? 'at ' + seconds(x) : 'step ' + Math.round(x).toLocaleString('en-GB'))); tip.appendChild(head);
      chart.lines.forEach(l => {
        if (!l.pts.length) return;
        let best = l.pts[0]; for (const p of l.pts) if (Math.abs(p[0] - x) < Math.abs(best[0] - x)) best = p;
        const row = h('div', 'trn-tip-row'); const sw = h('span', 'trn-swatch'); sw.style.background = 'rgb(' + l.colour.join(',') + ')'; row.appendChild(sw);
        row.appendChild(h('span', null, v.labelOf(l.id) + ': ' + fmt(best[1]) + ' at step ' + best[4].toLocaleString('en-GB') + ' · ' + seconds(best[5])));
        tip.appendChild(row);
      });
      tip.hidden = false;
      const left = Math.min(Math.max(0, mx + 12), r.width - tip.offsetWidth - 2); tip.style.left = Math.max(0, left) + 'px'; tip.style.top = '4px';
    });
    c.addEventListener('mouseleave', () => { tip.hidden = true; });
  }

  // ---- Histograms ------------------------------------------------------------------------------------------------
  function histograms(v) {
    v.histBox.textContent = '';
    const o = runOf(v.id).over; if (!o || !o.histograms.length) return;
    const box = h('div', 'trn-hists'); box.appendChild(h('h4', null, 'Histograms over the steps'));
    const kinds = [...new Set(o.histograms.map(x => x.kind))];
    if (!kinds.includes(v.kind)) v.kind = kinds[0];
    const head = h('div', 'trn-controls');
    if (kinds.length > 1) {
      const sw = h('div', 'seg'); sw.setAttribute('role', 'group'); sw.setAttribute('aria-label', 'Which values');
      for (const k of kinds) { const b = button('btn sm', k === 'weights' ? 'Weights' : 'Gradients', () => { v.kind = k; rebuild(v); }); b.setAttribute('aria-pressed', String(k === v.kind)); b.dataset.key = 'trn-kind-' + k; sw.appendChild(b); }
      head.appendChild(sw);
    }
    head.appendChild(h('span', 'small faint', 'Steps across, values up; each column shaded by its share of the values.'));
    box.appendChild(head);
    const list = o.histograms.filter(x => x.kind === v.kind), shown = v.all ? list : list.slice(0, STRIPS_FIRST);
    for (const item of shown) {
      const row = h('div', 'trn-strip-row');
      const label = h('div', 'small trn-strip-label'); label.appendChild(h('span', 'mono', item.name)); const range = h('span', 'faint'); label.appendChild(range); row.appendChild(label);
      const c = h('canvas', 'trn-strip'); c.dataset.tensor = item.name; c.dataset.kind = item.kind; c.setAttribute('role', 'img'); c.setAttribute('aria-label', 'The ' + item.kind + ' of ' + item.name + ' over the steps'); row.appendChild(c);
      box.appendChild(row);
      const strip = { canvas: c, range, name: item.name, kind: item.kind };
      D.paints(c, () => drawStrip(v, strip));
      watch(v, strip);
    }
    if (list.length > shown.length) { const more = button('btn sm ghost', 'Show all ' + list.length, () => { v.all = true; rebuild(v); }); more.dataset.key = 'trn-all'; box.appendChild(more); }
    v.histBox.appendChild(box);
  }
  const histKey = (name, kind) => name + '\u0000' + kind;
  const seen = new IntersectionObserver(entries => { for (const e of entries) if (e.isIntersecting && e.target._strip) { seen.unobserve(e.target); readStrip(e.target._strip.v, e.target._strip.s); } });
  /** A strip is read when it comes on screen, and again then when histograms were added since it was read. */
  function watch(v, strip) { strip.canvas._strip = { v, s: strip }; const r = runOf(v.id), kept = r.hist.get(histKey(strip.name, strip.kind)); if (kept && r.over && kept.at === r.over.histogram_lines) return; seen.observe(strip.canvas); }
  async function readStrip(v, strip) {
    const r = runOf(v.id), key = histKey(strip.name, strip.kind), at = r.over ? r.over.histogram_lines : 0;
    try { r.hist.set(key, { answer: await P.call('training_histograms', { run: v.id, name: strip.name, kind: strip.kind, most: HIST_ROWS, bins: HIST_BINS }), at }); }
    catch (error) { strip.range.textContent = ' · ' + error.message; return; }
    if (strip.canvas.isConnected) drawStrip(v, strip);
  }
  function drawStrip(v, strip) {
    const kept = runOf(v.id).hist.get(histKey(strip.name, strip.kind)), c = strip.canvas, size = D.fit(c, STRIP_HEIGHT);
    if (!size || !kept) return;
    const a = kept.answer, cols = a.rows.length, rows = a.bins, values = new Float32Array(rows * cols);
    for (let j = 0; j < cols; j++) { const total = a.totals[j] || 1, col = a.counts[j]; for (let b = 0; b < rows; b++) values[(rows - 1 - b) * cols + j] = Math.sqrt(col[b] / total); }
    const lo = D.token('--ramp-lo'), hi = D.token('--ramp-hi'), colour = t => [lo[0] + (hi[0] - lo[0]) * t, lo[1] + (hi[1] - lo[1]) * t, lo[2] + (hi[2] - lo[2]) * t];
    const g = c.getContext('2d'); g.setTransform(1, 0, 0, 1, 0, 0); g.clearRect(0, 0, size[0], size[1]);
    D.heat(g, values, rows, cols, colour, 0, 0, size[0], size[1]);
    c.dataset.drawn = String(Number(c.dataset.drawn || 0) + 1); c.dataset.rows = String(cols);
    const text = ' · ' + fmt(a.low) + ' to ' + fmt(a.high) + ' · steps ' + a.rows[0].step.toLocaleString('en-GB') + '–' + a.rows[cols - 1].step.toLocaleString('en-GB');
    setText(strip.range, text);
  }

  // ---- Samples ---------------------------------------------------------------------------------------------------
  function samples(v) {
    v.sampleBox.textContent = ''; v.samplesStrip = null;
    const r = runOf(v.id), o = r.over; if (!o || !o.samples.length) return;
    const box = h('div', 'trn-samples-box'); const head = h('div', 'trn-controls'); head.appendChild(h('h4', null, 'Samples'));
    if (o.samples.length > 1) {
      const s = h('select'); s.dataset.key = 'trn-sample'; s.setAttribute('aria-label', 'Which samples');
      for (const x of o.samples) { const op = h('option', null, x.name + ' · ' + x.count); op.value = x.name; s.appendChild(op); }
      s.value = r.sampleName; s.addEventListener('change', () => { r.sampleName = s.value; rebuild(v); }); head.appendChild(s);
    } else head.appendChild(h('span', 'small faint', o.samples[0].name));
    box.appendChild(head);
    const strip = h('div', 'trn-samples'); strip.setAttribute('role', 'list'); strip.tabIndex = 0; strip.setAttribute('aria-label', 'The last samples, newest last');
    const held_ = r.samples.get(r.sampleName);
    for (const item of held_ ? held_.items : []) strip.appendChild(sampleFigure(v, item));
    v.samplesStrip = strip;
    box.appendChild(strip); v.sampleBox.appendChild(box);
    requestAnimationFrame(() => { strip.scrollLeft = strip.scrollWidth; });
  }
  function sampleFigure(v, item) {
    const fig = h('figure', 'trn-sample'); fig.setAttribute('role', 'listitem'); fig.dataset.step = String(item.step); fig.dataset.index = String(item.index);
    if (item.problem) fig.appendChild(h('div', 'trn-thumb small faint', item.problem));
    else if (item.kind === 'image') { const img = h('img', 'trn-thumb'); img.alt = item.name + ' at step ' + item.step; img.src = item.url; img.width = SAMPLE_SIZE; img.height = SAMPLE_SIZE; img.loading = 'lazy'; fig.appendChild(img); }
    else { const c = h('canvas', 'trn-thumb'); c.setAttribute('role', 'img'); c.setAttribute('aria-label', item.name + ' at step ' + item.step); fig.appendChild(c); D.paints(c, () => drawArray(v, item, c)); }
    fig.appendChild(h('figcaption', 'small num', 'step ' + item.step.toLocaleString('en-GB')));
    return fig;
  }
  async function drawArray(v, item, c) {
    const r = runOf(v.id); let a = r.arrays.get(item.index);
    if (!a) { try { a = (await P.call('training_sample', { run: v.id, index: item.index })).content; r.arrays.set(item.index, a); } catch (error) { c.title = error.message; return; } }
    const size = D.fit(c, SAMPLE_SIZE); if (!size) return;
    const values = D.floats(a.values_f32), g = c.getContext('2d'); g.setTransform(1, 0, 0, 1, 0, 0); g.clearRect(0, 0, size[0], size[1]);
    const [x, y, w, hh] = D.contain(a.rows, a.columns, size[0], size[1]);
    D.heat(g, values, a.rows, a.columns, D.ramp(a.min == null ? 0 : a.min, a.max == null ? 1 : a.max), x, y, w, hh);
    c.dataset.drawn = String(Number(c.dataset.drawn || 0) + 1);
  }

  // ---- Live ------------------------------------------------------------------------------------------------------
  let ticking = false;
  /**
   * One step of the live block (tabs.js calls it on every reading): for each run in view whose last answer said it
   * was active, `training` once; then only what grew is read and drawn, in place.
   */
  async function tick() {
    const v = view; if (!v || !v.el.isConnected || ticking) return;
    const ids = [v.id].concat(v.settings.with).filter(id => { const o = runOf(id).over; return o && o.run.active; });
    if (!ids.length) return;
    ticking = true;
    try {
      for (const id of ids) {
        const r = runOf(id), before = r.over;
        const o = await overview(id);
        if (view !== v || !v.el.isConnected) return;
        const grewLines = o.lines !== before.lines, grewHist = o.histogram_lines !== before.histogram_lines, grewSamples = o.sample_lines !== before.sample_lines;
        const wasEmpty = !before.lines && !before.histogram_lines && !before.sample_lines;
        if (id === v.id && wasEmpty && (grewLines || grewHist || grewSamples)) { await rebuild(v); continue; }   // its first lines: the block's content is drawn
        let samplesDrawn = false;
        if (id === v.id) {   // a name not there before: its control or its part is added, the rest left as it is
          const names = shownSeries(idsOf(v), v.settings.series).names;
          if (names.some(n => !before.series.some(b => b.name === n))) chooserButtons(v, names);
          if (o.histograms.length !== before.histograms.length) histograms(v);
          if (o.samples.length !== before.samples.length) { r.sampleName = sampleName(o, r.sampleName); await samplesOf(id, r.sampleName); if (view !== v) return; samples(v); samplesDrawn = true; }
        }
        if (grewLines) { await seriesOf(id, v.picked || []); if (view !== v) return; drawAll(v); }
        if (id === v.id) {
          setAt(v);
          if (grewHist) for (const c of v.el.querySelectorAll('canvas.trn-strip')) { const s = c._strip && c._strip.s; if (s && r.hist.has(histKey(s.name, s.kind))) await readStrip(v, s); }
          if (grewSamples && v.samplesStrip && !samplesDrawn) {
            const added = await samplesOf(id, r.sampleName);
            if (added && added.length && view === v) {
              for (const item of added) v.samplesStrip.appendChild(sampleFigure(v, item));
              while (v.samplesStrip.children.length > SAMPLES_SHOWN) v.samplesStrip.firstChild.remove();
              v.samplesStrip.scrollLeft = v.samplesStrip.scrollWidth;
            }
          }
        }
      }
    } catch (error) { /* the next reading asks again */ }
    finally { ticking = false; }
  }
  /** Whether a run in the block on screen is read live (app.js keeps reading every two seconds while one is). */
  const live = () => !!(view && view.el.isConnected && [view.id].concat(view.settings.with).some(id => { const o = runOf(id).over; return o && o.run.active; }));

  return { read, block, tick, live, ACTIVE };
})();
