'use strict';
// The Compare tab (docs/plans/training-and-curation/spec-t3.md section 5.1), added to window.LabScreens: the page's
// compare set of two to four models, one column each. A table of who each model is (group, kind of change, the
// model it derives from, state, training date), what differs between their recipes (model_compare's differs: the
// settings, data and parent, only where they differ), and per benchmark that measures one of them its metrics with
// the tab's statistic, the 95 % interval from per-case values held here and the number of cases, the best of a row
// marked, and where each sits on the frontier of each tradeoff chart. Then the outputs: the cases the models' runs
// kept (spec-d6, fields.js's parts), matched by name; one case chosen; for each model its native field, its
// prediction and its signed error, three rows of panels with one colour scale a row (native and predicted share
// one), moved together by one control (the axis cut across, the position, "Remove the mean").
//
// Updating in place (spec-w4): the tab is read and built like the others (tabs.js's paint) and put in place in one
// step; the person's moves through the outputs ask field_compare of every column at once (one round in flight, the
// latest wins) and draw the canvases again in place, keeping the case, axis, position and mean option in the
// address (cmpCase, cmpAxis, cmpIndex, cmpMeanFree). Choosing another case draws the tab again in place.
(() => {
  const S = window.LabScreens, P = window.TuldokProject, Tree = window.LabTree, C = window.LabCharts, h = C.h;
  const { sect, putInPlace, modelState } = S.parts;
  const D = window.LabInside.drawing, R = P.product;
  const F = () => window.LabFields.parts;
  const fmt = C.fmtSci;
  const STATISTICS = ['median', 'mean', 'p10', 'p90', 'min', 'max'];
  const MOST = 4, CELL_MOST = 260;   // models in the set; the CSS height of a panel at most
  const button = (cls, text, onClick) => { const b = h('button', cls, text); b.type = 'button'; if (onClick) b.addEventListener('click', onClick); return b; };
  const units = m => m.units && m.units !== '1' ? ' (' + m.units + ')' : '';
  const shapeText = s => s && s.length ? s.join(' × ') : '—';
  const shown = v => v === undefined ? '—' : v === null ? 'null' : typeof v === 'object' ? JSON.stringify(v) : String(v);
  const KIND_WORDS = { group: 'group', change: 'kind of change', parent: 'derives from', data: 'data', setting: 'setting' };
  const ui4 = ui => ({ anaAxis: ui.cmpAxis, anaIndex: ui.cmpIndex, anaMeanFree: ui.cmpMeanFree });

  // ---- Reading ----------------------------------------------------------------------------------------------------
  /**
   * The outputs the tab shows: every model's kept cases, the cases kept by two models or more (comparable, matched by
   * name), the one chosen, the person's place in it and every column's first slice (null where the model did not
   * keep it or kept another shape).
   */
  async function readOutputs(models, ui) {
    const Fp = F();
    const kept = await Promise.all(models.map(m => Fp.keptCases(m).catch(error => ({ none: true, error }))));
    const byName = new Map();
    kept.forEach((k, i) => {
      if (!k || k.none) return;
      for (const c of k.cases) { if (!c.comparable) continue; if (!byName.has(c.name)) byName.set(c.name, models.map(() => null)); const row = byName.get(c.name); if (!row[i]) row[i] = c; }
    });
    const shared = [...byName].map(([name, cols]) => ({ name, cols, n: cols.filter(Boolean).length, split: cols.find(Boolean).split || null }))
      .filter(x => x.n >= 2).sort((a, b) => b.n - a.n || a.name.localeCompare(b.name));
    if (!shared.length) return { kept, shared, chosen: null };
    const chosen = shared.find(x => x.name === ui.cmpCase) || shared[0];
    const lead = chosen.cols.find(Boolean);
    const view = Fp.viewFor(lead, !ui.cmpCase || chosen.name === ui.cmpCase ? ui4(ui) : { anaMeanFree: ui.cmpMeanFree });
    const answers = await Promise.all(chosen.cols.map(c => c && sameShape(c, lead) ? R.fieldCompare(c.run, Fp.argsOf(c, view)).catch(error => ({ error })) : null));
    return { kept, shared, chosen, lead, view, answers };
  }
  const sameShape = (a, b) => a.shape.length === b.shape.length && a.shape.every((n, i) => n === b.shape[i]);

  // ---- The screen ---------------------------------------------------------------------------------------------------
  function compare(main, aside, state, act, data) {
    const ui = state.ui, sel = state.sel.compare || null, g = S.parts.graphFor(data.map);
    const models = state.cmp.filter(k => g.byId.has(k)), others = state.cmp.filter(k => !g.byId.has(k));
    const stat = STATISTICS.includes(ui.stat) ? ui.stat : 'median';
    S.paint(main, async () => {
      if (models.length < 2) return { models };
      const [cmp, outputs] = await Promise.all([P.read('model_compare', { recipes: models, statistic: stat }), readOutputs(models, ui)]);
      return { models, cmp, outputs };
    }, (frag, got) => {
      frag.appendChild(head(g, state, act, stat, others));
      if (got.models.length < 2) {
        frag.appendChild(h('p', 'empty cmpv-empty', 'Choose two to four models to compare: Compare in a model\'s drawer on the Map or on the Benchmarks tab, or the boxes of the Benchmarks table.'));
        return;
      }
      const list = got.models.map(id => g.byId.get(id));
      frag.appendChild(table(got.cmp, list, g, act, sel));
      frag.appendChild(outputs(got.outputs, list, act, ui));
    });
    if (!sel || !g.byId.has(sel)) { aside.textContent = ''; aside._for = null; return false; }
    S.inspectorModel(aside, sel, act, data, ins => S.compareActs(ins, sel, state, act, 'compare'));
    const ins = aside.querySelector('.inspector'); if (ins) S.compareActs(ins, sel, state, act, 'compare');
    return true;
  }

  /** The set as chips with ×, Clear, and the statistic. */
  function head(g, state, act, stat, others) {
    const box = h('div', 'cmpv-head');
    box.appendChild(sect('Compare', state.cmp.length + ' of ' + MOST + ' models'));
    const chips = h('div', 'cmp-chips');
    state.cmp.forEach((k, i) => {
      const m = g.byId.get(k), name = m ? Tree.nameOf(m) : k.replace(/^subject:/, '');
      const c = h('span', 'c s' + (i + 1)); c.appendChild(h('i')); c.appendChild(document.createTextNode(name));
      const x = button(null, '×', () => act.toggleCompare(k)); x.setAttribute('aria-label', 'Remove ' + name); x.dataset.key = 'cmpv-x-' + k; c.appendChild(x); chips.appendChild(c);
    });
    if (state.cmp.length) { const clear = button('btn sm ghost', 'Clear', () => act.clearCompare()); clear.dataset.key = 'cmpv-clear'; chips.appendChild(clear); }
    const s = h('select'); s.setAttribute('aria-label', 'Statistic'); s.dataset.key = 'cmpv-stat';
    for (const v of STATISTICS) { const o = h('option', null, v.charAt(0).toUpperCase() + v.slice(1)); o.value = v; o.selected = v === stat; s.appendChild(o); }
    s.addEventListener('change', () => act.setUI('stat', s.value));
    const l = h('label', 'iv-field'); l.appendChild(document.createTextNode('Statistic')); l.appendChild(s); chips.appendChild(l);
    box.appendChild(chips);
    if (others.length) box.appendChild(h('p', 'small muted', others.map(k => k.replace(/^subject:/, '')).join(', ') + (others.length === 1 ? ' is a benchmark subject' : ' are benchmark subjects') + ' made from no recipe on the map, and left out here.'));
    return box;
  }

  // ---- The table: who, what differs, the metrics and the frontier -------------------------------------------------------
  function table(cmp, list, g, act, sel) {
    const sec = h('section', 'cmpv-table');
    const t = h('table', 'tv cmpv'), thead = h('thead'), hr = h('tr');
    hr.appendChild(h('th', 'cmpv-row', ''));
    list.forEach((m, i) => {
      const th = h('th', 'cmpv-col s' + (i + 1)); th.dataset.model = m.id;
      const b = button('linkish', Tree.nameOf(m), () => act.select(m.id === sel ? null : m.id)); b.dataset.key = 'cmpv-open-' + m.id; b.title = 'Open ' + m.title;
      th.appendChild(h('i', 'swatch')); th.appendChild(b); hr.appendChild(th);
    });
    thead.appendChild(hr); t.appendChild(thead);
    const tb = h('tbody'), n = list.length;
    const group = (title, extra) => { const tr = h('tr', 'cmpv-group'); const th = h('th', null, title); th.colSpan = n + 1; if (extra) th.appendChild(h('span', 'sum', extra)); tr.appendChild(th); tb.appendChild(tr); };
    const row = (label, cells, cls, labelCls) => { const tr = h('tr', cls || null); const th = h('th', 'cmpv-row' + (labelCls ? ' ' + labelCls : '')); if (typeof label === 'string') th.textContent = label; else th.appendChild(label); tr.appendChild(th); for (const c of cells) tr.appendChild(c); tb.appendChild(tr); return tr; };
    const td = (text, cls) => h('td', cls || null, text);
    // Who.
    group('Who');
    row('Group', list.map(m => td(m.groupTitle || '—')));
    row('Kind of change', list.map(m => { const c = h('td'); c.appendChild(h('span', 'chip ' + m.kind, P.kindLabel(m.kind))); return c; }));
    row('Derives from', list.map(m => { const p = m.parent && g.byId.get(m.parent); return td(p ? Tree.nameOf(p) : m.parent || '—'); }));
    row('State', list.map(m => { const c = h('td'); c.appendChild(modelState(m.state)); return c; }));
    row('Trained', list.map(m => td(m.trainedAt ? P.day(m.trainedAt) : '—', 'nowrap')));
    // What differs.
    group('What differs', cmp.differs.length + (cmp.more ? ' of ' + (cmp.differs.length + cmp.more) : '') + ' paths differ · ' + cmp.same + ' the same');
    if (!cmp.differs.length) row('Nothing', list.map(() => td('the same', 'small faint')));
    for (const d of cmp.differs) {
      const label = h('span'); label.appendChild(h('span', 'mono cmpv-path', d.path)); label.appendChild(h('span', 'cmpv-kind small faint', KIND_WORDS[d.kind] || d.kind));
      const tr = row(label, d.values.map((v, i) => td(d.present[i] ? shown(v) : '—', 'mono cmpv-v' + (d.present[i] ? '' : ' faint'))), 'cmpv-diff');
      tr.dataset.path = d.path; tr.dataset.kind = d.kind;
    }
    if (cmp.more) row('…', list.map(() => td(cmp.more + ' more not listed', 'small faint')));
    // The benchmarks.
    if (!cmp.benchmarks.length) { group('Results'); row('None', list.map(() => td('no benchmark measures it', 'small faint'))); }
    for (const b of cmp.benchmarks) {
      group(b.title, cmp.statistic + ' · 95 % interval from ' + cmp.resamples.toLocaleString('en-GB') + ' resamples of the per-case values held here');
      for (const metric of b.metrics) {
        const values = b.models.map(c => c && c.values[metric.id] && c.values[metric.id].value != null ? c.values[metric.id].value : null).filter(v => v != null);
        const best = !values.length || metric.better === 'none' ? null : metric.better === 'higher' ? Math.max(...values) : Math.min(...values);
        const tr = row(metric.title + units(metric), b.models.map(c => {
          const v = c && c.values[metric.id];
          if (!c) return td('not a subject', 'small faint');
          if (!v || v.value == null) return td('—', 'n faint');
          const cell = h('td', 'n' + (values.length > 1 && v.value === best ? ' best' : ''));
          cell.appendChild(h('span', 'cmpv-value', fmt(v.value)));
          if (v.low != null) { const ci = h('span', 'ci', fmt(v.low) + ' – ' + fmt(v.high)); ci.title = 'The 95 % interval of the ' + cmp.statistic + ' from ' + cmp.resamples + ' resamples of its per-case values (seed ' + cmp.seed + ')'; cell.appendChild(ci); cell.dataset.low = String(v.low); cell.dataset.high = String(v.high); }
          if (v.count != null) cell.appendChild(h('span', 'cmpv-n small faint', v.count.toLocaleString('en-GB') + ' cases'));
          cell.dataset.value = String(v.value);
          return cell;
        }), 'cmpv-metric');
        tr.dataset.benchmark = b.benchmark; tr.dataset.metric = metric.id;
      }
      for (const f of b.frontiers) {
        const tr = row('Frontier · ' + f.title, f.models.map((r, i) => {
          if (!b.models[i]) return td('not a subject', 'small faint');
          if (!r) return td('not drawn', 'small faint');
          const words = r.on ? 'on the frontier' + (r.not_separated_from.length ? ', not separated from ' + r.not_separated_from.join(', ') : '') : 'off the frontier';
          const cell = td(words, r.on ? (r.not_separated_from.length ? 'cmpv-nsig' : 'cmpv-on') : 'faint');
          cell.dataset.on = String(r.on); cell.dataset.nsig = r.not_separated_from.join(',');
          return cell;
        }), 'cmpv-front');
        tr.dataset.chart = f.chart;
      }
    }
    t.appendChild(tb);
    const wrap = h('div', 'tv-wrap'); wrap.appendChild(t); sec.appendChild(wrap);
    return sec;
  }

  // ---- The outputs ----------------------------------------------------------------------------------------------------
  const ROWS = [['reference', 'Native', 'reference_f32'], ['predicted', 'Predicted', 'predicted_f32'], ['error', 'Signed error (predicted − native)', 'error_f32']];
  function outputs(o, list, act, ui) {
    const sec = h('section', 'cmpv-out'); sec.dataset.key = 'cmpv-out';
    if (!o.chosen) {
      sec.appendChild(sect('Outputs'));
      const said = list.map((m, i) => { const k = o.kept[i]; return Tree.nameOf(m) + ': ' + (!k ? 'no product on this machine' : k.none ? 'kept no fields' : k.cases.filter(c => c.comparable).length + ' comparable cases'); });
      sec.appendChild(h('p', 'empty cmpv-none', 'No case is kept by two of these models. ' + said.join('; ') + '.'));
      return sec;
    }
    const c = o.chosen, lead = o.lead, ctx = { o, list, act, view: o.view, answers: o.answers.slice(), busy: false, again: false };
    sec.appendChild(sect('Outputs', c.name + (c.split ? ' · ' + c.split : '') + ' · kept by ' + c.n + ' of ' + list.length));
    const hd = h('div', 'cmpv-outhead');
    if (o.shared.length > 1) {
      const s = h('select'); s.setAttribute('aria-label', 'Case'); s.dataset.key = 'cmpv-case';
      for (const x of o.shared) { const op = h('option', null, x.name + (x.split ? ' · ' + x.split : '') + ' · ' + x.n + ' of ' + list.length); op.value = x.name; op.selected = x === c; s.appendChild(op); }
      s.addEventListener('change', () => { act.keepUI('cmpAxis', null); act.keepUI('cmpIndex', null); act.setUI('cmpCase', s.value); });
      const l = h('label', 'iv-field'); l.appendChild(document.createTextNode('Case')); l.appendChild(s); hd.appendChild(l);
    } else hd.appendChild(h('p', 'mono cmpv-casename', c.name));
    hd.appendChild(h('p', 'small muted', [shapeText(lead.shape), lead.dtype, 'the native field of each model\'s own run'].filter(Boolean).join(' · ')));
    sec.appendChild(hd);
    ctx.ctl = h('div', 'iv-ctl cmpv-ctl'); controls(ctx); sec.appendChild(ctx.ctl);
    ctx.grid = grid(ctx); sec.appendChild(ctx.grid);
    ctx.say = h('p', 'small muted cmpv-where'); sec.appendChild(ctx.say);
    ctx.err = h('div', 'cmpv-err'); sec.appendChild(ctx.err);
    redraw(ctx, false);
    return sec;
  }
  /** The one control of every column: the axis, the sliders of the axes not drawn and "Remove the mean". */
  function controls(ctx) {
    const Fp = F(), lead = ctx.o.lead, v = ctx.view, nd = lead.shape.length, names = Fp.axisNames(nd), items = [];
    if (nd >= 3) {
      const s = h('select'); s.setAttribute('aria-label', 'The axis cut across, for every model'); s.dataset.key = 'cmpv-axis';
      for (let a = 0; a < nd; a++) { const op = h('option', null, names[a] + ' (' + lead.shape[a] + ')'); op.value = String(a); op.selected = a === v.axis; s.appendChild(op); }
      s.addEventListener('change', () => { v.axis = Number(s.value); ctx.act.keepUI('cmpAxis', String(v.axis)); controls(ctx); ask(ctx); });
      const l = h('label', 'iv-field'); l.appendChild(document.createTextNode('Cut across')); l.appendChild(s); items.push(l);
      for (const a of Fp.fixedAxes(nd, v.axis)) {
        const l2 = h('label', 'iv-field iv-slider'); l2.appendChild(h('span', null, a === v.axis ? 'Position on ' + names[a] : names[a]));
        const r = h('input'); r.type = 'range'; r.min = '0'; r.max = String(lead.shape[a] - 1); r.value = String(v.index[a]); r.dataset.key = 'cmpv-slider-' + a; r.dataset.axis = String(a);
        r.setAttribute('aria-label', 'Position on ' + names[a] + ' for every model, 0 to ' + (lead.shape[a] - 1));
        const at = h('span', 'num small', v.index[a] + ' of ' + lead.shape[a]);
        r.addEventListener('input', () => { v.index[a] = Number(r.value); at.textContent = v.index[a] + ' of ' + lead.shape[a]; ctx.act.keepUI('cmpIndex', v.index.join(',')); ask(ctx); });
        l2.appendChild(r); l2.appendChild(at); items.push(l2);
      }
    }
    const mean = button('btn sm', 'Remove the mean', () => { v.meanFree = !v.meanFree; mean.setAttribute('aria-pressed', String(v.meanFree)); ctx.act.keepUI('cmpMeanFree', v.meanFree ? '1' : null); ask(ctx); });
    mean.dataset.key = 'cmpv-mean'; mean.setAttribute('aria-pressed', String(v.meanFree)); mean.title = 'Take each field\'s mean from it before the error is formed, in every column';
    items.push(mean);
    if (ctx.ctl.isConnected) { const frag = document.createDocumentFragment(); frag.append(...items); putInPlace(ctx.ctl, frag, document.getElementById('main')); }
    else ctx.ctl.replaceChildren(...items);
  }
  /** Asks field_compare of every column for the place: one round in flight; a move meanwhile waits, the latest wins. */
  function ask(ctx) {
    if (ctx.busy) { ctx.again = true; return; }
    ctx.busy = true; ctx.again = false; ctx.grid.setAttribute('aria-busy', 'true');
    const Fp = F(), cols = ctx.o.chosen.cols, lead = ctx.o.lead;
    Promise.all(cols.map(c => c && sameShape(c, lead) ? R.fieldCompare(c.run, Fp.argsOf(c, ctx.view), true).catch(error => ({ error })) : null)).then(answers => {
      if (ctx.again || !ctx.grid.isConnected) return;
      ctx.answers = answers; redraw(ctx, true);
    }).finally(() => {
      ctx.busy = false;
      if (ctx.again && ctx.grid.isConnected) ask(ctx); else ctx.grid.removeAttribute('aria-busy');
    });
  }

  /** Three rows of panels, a column per model, a colour bar a row, the figures under each column. */
  function grid(ctx) {
    const { list, o } = ctx, n = list.length, wrap = h('div', 'cmpv-grid'); wrap.style.setProperty('--cols', String(n));
    ctx.cells = {}; ctx.bars = {};
    const heads = h('div', 'cmpv-cells cmpv-heads');
    list.forEach((m, i) => { const d = h('div', 'cmpv-colhead s' + (i + 1)); d.appendChild(h('i', 'swatch')); d.appendChild(h('span', null, Tree.nameOf(m))); heads.appendChild(d); });
    wrap.appendChild(heads);
    for (const [id, title] of ROWS) {
      const rowEl = h('div', 'cmpv-orow'); rowEl.dataset.row = id;
      const top = h('div', 'cmpv-otitle'); top.appendChild(h('span', 'fld-title', title));
      const bar = h('canvas', 'fld-bar cmpv-bar'); bar.setAttribute('aria-hidden', 'true'); const ends = h('div', 'iv-ends small faint cmpv-ends');
      const barBox = h('div', 'cmpv-barbox'); barBox.appendChild(bar); barBox.appendChild(ends); top.appendChild(barBox);
      rowEl.appendChild(top);
      ctx.bars[id] = { bar, ends }; D.paints(bar, () => drawBar(ctx, id));
      const cells = h('div', 'cmpv-cells');
      list.forEach((m, i) => {
        const fig = h('figure', 'cmpv-cell'); fig.dataset.model = m.id; fig.dataset.row = id;
        const c = o.chosen.cols[i];
        if (!c) fig.appendChild(h('p', 'small faint cmpv-missing', 'Not kept by this model.'));
        else if (!sameShape(c, o.lead)) fig.appendChild(h('p', 'small faint cmpv-missing', 'Kept with another shape (' + shapeText(c.shape) + '), not drawn.'));
        else {
          const cv = h('canvas', 'fld-cv cmpv-cv'); cv.setAttribute('role', 'img'); cv.dataset.model = m.id; cv.dataset.row = id; fig.appendChild(cv);
          ctx.cells[id + ' ' + i] = { cv, i, id };
          D.paints(cv, () => drawCell(ctx, id, i));
          cv.addEventListener('mousemove', ev => hover(ctx, id, i, ev)); cv.addEventListener('mouseleave', () => { ctx.tip.hidden = true; });
        }
        cells.appendChild(fig);
      });
      rowEl.appendChild(cells); wrap.appendChild(rowEl);
    }
    ctx.figs = h('div', 'cmpv-cells cmpv-figs'); wrap.appendChild(ctx.figs);
    ctx.tip = h('div', 'fld-tip cmpv-tip'); ctx.tip.hidden = true; ctx.tip.setAttribute('role', 'status'); wrap.appendChild(ctx.tip);
    return wrap;
  }
  /** The answers as floats, one scale a row over every column: native and predicted share one, the errors one diverging about zero. */
  function decode(ctx) {
    const Fp = F(), got = ctx.answers.filter(a => a && !a.error);
    const lows = got.map(a => a.range && a.range[0]).filter(v => v != null), highs = got.map(a => a.range && a.range[1]).filter(v => v != null);
    ctx.range = lows.length ? [Math.min(...lows), Math.max(...highs)] : [0, 0];
    ctx.limit = Math.max(0, ...got.map(a => a.error_limit || 0));
    ctx.values = ctx.answers.map(a => a && !a.error ? { reference: D.floats(a.reference_f32), predicted: D.floats(a.predicted_f32), error: D.floats(a.error_f32) } : null);
    const seq = Fp.sequential(ctx.range[0], ctx.range[1]);
    ctx.scale = { reference: seq, predicted: seq, error: Fp.diverging(ctx.limit) };
  }
  function redraw(ctx, draw) {
    decode(ctx);
    const Fp = F(), lead = ctx.o.lead, nd = lead.shape.length, names = Fp.axisNames(nd), first = ctx.answers.find(a => a && !a.error);
    const where = !first ? '' : nd >= 3 ? 'through ' + first.axes.map(x => names[x]).join(' and ') + ' at ' + Fp.fixedAxes(nd, first.axis).map(x => names[x] + ' = ' + first.index[x]).join(', ') : nd === 2 ? 'the whole field' : 'the whole line';
    for (const { cv, i, id } of Object.values(ctx.cells)) {
      const a = ctx.answers[i];
      cv.setAttribute('aria-label', ROWS.find(r => r[0] === id)[1] + ' of ' + Tree.nameOf(ctx.list[i]) + (a && !a.error ? ', ' + a.rows + ' by ' + a.columns + ' cells ' + where : ', not read'));
      if (draw) drawCell(ctx, id, i);
    }
    ctx.bars.reference.ends.replaceChildren(...[fmt(ctx.range[0]), 'native and predicted, every column', fmt(ctx.range[1])].map(t => h('span', null, t)));
    ctx.bars.predicted.ends.replaceChildren(...[fmt(ctx.range[0]), 'the same scale', fmt(ctx.range[1])].map(t => h('span', null, t)));
    ctx.bars.error.ends.replaceChildren(...['−' + fmt(ctx.limit), '0', '+' + fmt(ctx.limit)].map(t => h('span', null, t)));
    if (draw) for (const id of Object.keys(ctx.bars)) drawBar(ctx, id);
    ctx.say.textContent = first ? 'A slice ' + where + (first.stride > 1 ? ', every ' + D.ordinal(first.stride) + ' row and column' : '') + ' of each model\'s field; one scale for native and predicted from ' + fmt(ctx.range[0]) + ' to ' + fmt(ctx.range[1]) + ', the errors on ±' + fmt(ctx.limit) + ' about zero' + (first.mean_free ? ', each field\'s mean removed first' : '') + '.' : '';
    const errors = ctx.answers.filter(a => a && a.error);
    ctx.err.replaceChildren(...errors.slice(0, 1).map(a => window.LabActions.refusal(a.error)));
    figures(ctx);
    if (first) { ctx.grid.dataset.index = JSON.stringify(first.index); ctx.grid.dataset.axis = String(first.axis); ctx.grid.dataset.meanFree = String(first.mean_free); }
  }
  function drawCell(ctx, id, i) {
    const cell = ctx.cells[id + ' ' + i], a = ctx.answers[i], vals = ctx.values && ctx.values[i]; if (!cell || !a || a.error || !vals) return;
    const cv = cell.cv, w = cv.clientWidth; if (!w) return;
    const cssH = a.rows === 1 ? 28 : Math.max(32, Math.min(CELL_MOST, Math.round(w * a.rows / a.columns)));
    const size = D.fit(cv, cssH); if (!size) return; const gx = cv.getContext('2d'); gx.clearRect(0, 0, size[0], size[1]);
    const rect = a.rows === 1 ? [0, 0, size[0], size[1]] : D.contain(a.rows, a.columns, size[0], size[1]);
    cell.rect = rect.map(x => x / (window.devicePixelRatio || 1));
    D.heat(gx, vals[id], a.rows, a.columns, ctx.scale[id], rect[0], rect[1], rect[2], rect[3]);
    cv.dataset.drawn = String((cv._drawn = (cv._drawn || 0) + 1));
  }
  function drawBar(ctx, id) {
    const b = ctx.bars[id], size = D.fit(b.bar, 10); if (!size) return;
    const n = 64, vals = new Float32Array(n), m = ctx.limit || 0, range = ctx.range || [0, 0];
    for (let i = 0; i < n; i++) { const t = (i + 0.5) / n; vals[i] = id === 'error' ? -m + 2 * m * t : range[0] + (range[1] - range[0]) * t; }
    D.heat(b.bar.getContext('2d'), vals, 1, n, ctx.scale[id], 0, 0, size[0], size[1]);
  }
  function hover(ctx, id, i, ev) {
    const cell = ctx.cells[id + ' ' + i], a = ctx.answers[i]; if (!cell || !cell.rect || !a || a.error) return;
    const box = cell.cv.getBoundingClientRect(), x = ev.clientX - box.left - cell.rect[0], y = ev.clientY - box.top - cell.rect[1];
    const col = Math.floor(x / cell.rect[2] * a.columns), row = Math.floor(y / cell.rect[3] * a.rows);
    if (col < 0 || row < 0 || col >= a.columns || row >= a.rows) { ctx.tip.hidden = true; return; }
    const k = row * a.columns + col, at = a.index.slice(), nd = ctx.o.lead.shape.length, names = F().axisNames(nd), v = ctx.values[i];
    if (nd === 1) at[0] = col * a.stride; else { at[a.axes[0]] = row * a.stride; at[a.axes[1]] = col * a.stride; }
    ctx.tip.replaceChildren(h('b', null, Tree.nameOf(ctx.list[i])), h('div', 'mono fld-tip-at', nd === 3 ? at.map((q, j) => names[j] + ' ' + q).join(', ') : '(' + at.join(', ') + ')'));
    for (const [key, word] of [['reference', 'Native'], ['predicted', 'Predicted'], ['error', a.mean_free ? 'Error, means removed' : 'Error']]) { const r = h('div', 'fld-tip-row'); r.dataset.value = key; r.appendChild(h('span', null, word)); r.appendChild(h('span', 'num', fmt(v[key][k]))); ctx.tip.appendChild(r); }
    ctx.tip.dataset.cell = JSON.stringify(at); ctx.tip.dataset.model = ctx.list[i].id;
    ctx.tip.hidden = false;
    const wrap = ctx.grid.getBoundingClientRect(), tw = ctx.tip.offsetWidth;
    let left = ev.clientX - wrap.left + 14; if (left + tw > wrap.width) left = Math.max(0, ev.clientX - wrap.left - tw - 14);
    ctx.tip.style.left = left + 'px'; ctx.tip.style.top = (ev.clientY - wrap.top + 14) + 'px';
  }
  const FIGURES = [['relative_l2', 'Relative L2'], ['mean_free_relative_l2', 'Mean-free relative L2'], ['rmse', 'RMSE'], ['max_abs_error', 'Largest |error|']];
  /** The whole-field figures under each column. */
  function figures(ctx) {
    const items = ctx.answers.map((a, i) => {
      const box = h('div', 'cmpv-fig'); box.dataset.model = ctx.list[i].id;
      if (!a || a.error) { box.appendChild(h('p', 'small faint', a && a.error ? 'Not read.' : '—')); return box; }
      const dl = h('dl', 'cmpv-figdl');
      for (const [key, word] of FIGURES) { const d = h('div'); d.dataset.fig = key; d.dataset.value = a.figures[key] == null ? '' : String(a.figures[key]); d.appendChild(h('dt', null, word)); d.appendChild(h('dd', 'num', fmt(a.figures[key]))); dl.appendChild(d); }
      box.appendChild(dl); return box;
    });
    ctx.figs.replaceChildren(...items);
  }

  S.compare = compare;
})();
