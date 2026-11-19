'use strict';
// The fields a run kept (docs/plans/definition-first-projects/spec-d6.md section 3): the section "Kept fields" of
// the Analysis tab, below "Per case", for the chosen subject. When the subject's model has a current product whose
// run kept fields (fields), the section shows one case (a select when there are several): its name, split and
// shape and the run it comes from; three panels side by side, Native, Predicted and Signed error (predicted −
// native), slices through the field read by field_compare; Native and Predicted on one sequential scale over the
// slice's range, the error on a diverging scale symmetric about zero; a colour bar under each with its ends; the
// axis cut across, a slider for the position on it (and one more for a fourth axis) and "Remove the mean"; a tip
// with the cell's position and its three values under the pointer; the error's figures over the whole field, and
// what the run reported beside them. The section is absent when the model has no product, one line when its
// products keep no fields.
//
// Updating in place (spec-w4): tabs.js reads what the section shows with the rest of the tab (read()) and builds
// it with the tab off the page (section()), so a reading that changed something draws it again in place, where the
// person left it (the case, axis, position and mean option are the tab's settings, kept in the address). The
// person's own moves are drawn here and nothing else of the tab: a slider, the axis or "Remove the mean" asks
// field_compare again (at most one request in flight, the last position wins) and the panels are drawn again in
// their canvases; another case builds the section again and puts it in place. A timer or a return to the window
// with nothing changed never reaches here.
window.LabFields = (() => {
  const P = window.TuldokProject, S = window.LabScreens, C = window.LabCharts, h = C.h, R = P.product;
  const { sect, putInPlace } = S.parts;
  const D = window.LabInside.drawing;
  const fmt = v => v == null ? '—' : C.fmtSci(v);
  const num = n => n == null ? '—' : n.toLocaleString('en-GB');
  const shapeText = s => s && s.length ? s.join(' × ') : '—';
  const button = (cls, text, onClick) => { const b = h('button', cls, text); b.type = 'button'; if (onClick) b.addEventListener('click', onClick); return b; };
  const refusal = error => window.LabActions.refusal(error);
  const PANEL_MOST = 420;   // the CSS height of a panel at most
  const axisNames = nd => nd === 3 ? ['x', 'y', 'z'] : Array.from({ length: nd }, (_, i) => 'axis ' + i);

  // ---- Colours: the tokens of base.css -------------------------------------------------------------------------------
  const mix = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
  /** Sequential from --ramp-lo to --ramp-hi over [min, max], whatever the signs. */
  function sequential(min, max) { const lo = D.token('--ramp-lo'), hi = D.token('--ramp-hi'), span = max - min || 1; return v => mix(lo, hi, Math.min(1, Math.max(0, (v - min) / span))); }
  /** Diverging about zero over [−m, m]: --ramp-mid at zero, --ramp-neg and --ramp-pos at the ends. */
  function diverging(m) { const neg = D.token('--ramp-neg'), mid = D.token('--ramp-mid'), pos = D.token('--ramp-pos'), s = m || 1; return v => v < 0 ? mix(mid, neg, Math.min(1, -v / s)) : mix(mid, pos, Math.min(1, v / s)); }

  // ---- Reading --------------------------------------------------------------------------------------------------------
  const keyOf = (run, entry, one) => run + ':' + entry + ':' + one;
  const intOr = (v, d) => { const n = Number(v); return v !== null && v !== undefined && v !== '' && Number.isInteger(n) && n >= 0 ? n : d; };
  /** The person's place in a case from the tab's settings (strings when they came from the address), checked against its shape. */
  function viewFor(c, ui) {
    const nd = c.shape ? c.shape.length : 0, mid = (c.shape || []).map(n => Math.floor(n / 2));
    let axis = intOr(ui.anaAxis, nd - 1); if (axis >= nd) axis = nd - 1;
    let index = typeof ui.anaIndex === 'string' ? ui.anaIndex.split(',').map(x => intOr(x, -1)) : Array.isArray(ui.anaIndex) ? ui.anaIndex.slice() : null;
    if (!index || index.length !== nd || index.some((p, i) => p < 0 || p >= c.shape[i])) index = mid;
    const meanFree = ui.anaMeanFree === true || ui.anaMeanFree === '1' || ui.anaMeanFree === 'true';
    return { axis, index, meanFree };
  }
  const argsOf = (c, v) => ({ entry: c.entry, case: c.case, axis: c.shape.length >= 3 ? v.axis : null, index: v.index.slice(), mean_free: v.meanFree });

  /**
   * What the section shows for a subject's recipe, read in full: null when the model has no current product (the
   * section is absent), { none } when none of its products keeps fields, else the cases, the one chosen, the
   * person's place in it and its first slice.
   */
  async function read(recipe, ui) {
    const found = await keptCases(recipe);
    if (!found || found.none) return found;
    const cases = found.cases;
    const chosen = cases.find(c => c.key === ui.anaCase) || cases.find(c => c.comparable) || cases[0];
    const out = { cases, chosen, view: null, cmp: null, error: null };
    if (chosen.comparable) {
      out.view = viewFor(chosen, !ui.anaCase || chosen.key === ui.anaCase ? ui : {});
      try { out.cmp = await R.fieldCompare(chosen.run, argsOf(chosen, out.view)); } catch (error) { out.error = error; }
    }
    return out;
  }

  /**
   * The cases kept by every current product of a recipe's model: null when it has no current product, { none } when
   * none of them keeps fields (with the first refusal, or empty when an index lists no case), else { cases }, each
   * case as fields lists it with its run, subject, key, the run's reported figures and a label. Shared with the
   * Compare tab (compare.js, spec-t3 section 5.1).
   */
  async function keptCases(recipe) {
    if (!recipe) return null;
    const products = (await P.read('products', { reference: recipe })).products.filter(p => p.run_id);
    if (!products.length) return null;
    const got = await Promise.all(products.map(p => R.fields(p.run_id).then(f => ({ p, f }), error => ({ p, error }))));
    const kept = got.filter(g => g.f && g.f.kept);
    if (!kept.length) { const failed = got.find(g => g.error); return { none: true, error: failed ? failed.error : null }; }
    const several = kept.length > 1;
    const cases = kept.flatMap(g => g.f.cases.map(c => Object.assign({}, c, { run: g.p.run_id, subject: g.p.subject || '', key: keyOf(g.p.run_id, c.entry, c.case), reported: g.f.reported, label: c.name + (several && g.p.subject ? ' · ' + g.p.subject : '') })));
    if (!cases.length) return { none: true, empty: true, run: kept[0].p.run_id };
    return { cases };
  }

  // ---- The section ----------------------------------------------------------------------------------------------------
  /** The section for what read() gave (built off the page); null when it is absent. act: the tab's actions (keepUI). */
  function section(model, act) {
    if (!model) return null;
    const box = h('section', 'fld'); box.dataset.key = 'fld';
    fill(box, model, act);
    return box;
  }
  function fill(box, model, act) {
    box.appendChild(sect('Kept fields', model.none ? undefined : model.chosen.label));
    if (model.none) {
      box.appendChild(h('p', 'empty fld-none', model.empty ? 'The run kept a field index that lists no case.' : model.error ? 'Whether this model\'s run kept fields could not be read: ' + (model.error.message || model.error) : 'The run of this model kept no fields: its product holds no field-index.json.'));
      return;
    }
    const c = model.chosen, ctx = { box, model, c, act, v: model.view, cmp: model.cmp, busy: false, again: false };
    box.appendChild(head(ctx));
    if (!c.comparable) { box.appendChild(h('p', 'empty fld-reason', 'This case cannot be compared: ' + c.reason)); return; }
    if (c.bytes_mismatch && c.bytes_mismatch.length) box.appendChild(h('p', 'small warnline fld-bytes', 'The index gives another size for ' + c.bytes_mismatch.join(' and ') + ' than the file has.'));
    if (model.error) { box.appendChild(refusal(model.error)); return; }
    ctx.ctl = h('div', 'iv-ctl fld-ctl'); controls(ctx); box.appendChild(ctx.ctl);
    ctx.panels = panels(ctx); box.appendChild(ctx.panels);
    ctx.figs = h('div', 'fld-figs'); figures(ctx); box.appendChild(ctx.figs);
  }
  /** The head: the case (a select when there are several), its split and shape, and the run, linked to Train. */
  function head(ctx) {
    const { model, c, act } = ctx, hd = h('div', 'fld-head');
    if (model.cases.length > 1) {
      const s = h('select'); s.setAttribute('aria-label', 'Case'); s.dataset.key = 'fld-case';
      for (const x of model.cases) { const o = h('option', null, x.label + (x.split ? ' · ' + x.split : '') + (x.comparable ? '' : ' (cannot be compared)')); o.value = x.key; o.selected = x === c; s.appendChild(o); }
      s.addEventListener('change', () => chooseCase(ctx, s.value));
      const l = h('label', 'iv-field fld-pick'); l.appendChild(document.createTextNode('Case')); l.appendChild(s); hd.appendChild(l);
    } else hd.appendChild(h('p', 'mono fld-name', c.name));
    const facts = [c.split ? 'split ' + c.split : null, c.shape ? shapeText(c.shape) : null, c.dtype, c.predicted + ' against ' + c.reference + (c.mask ? ', inside ' + c.mask : '')].filter(Boolean);
    const line = h('p', 'small muted fld-facts', facts.join(' · ') + ' · from run ');
    const run = h('a', 'mono fld-run', c.run.slice(0, 8)); run.href = '#train/' + encodeURIComponent('run:' + c.run); run.dataset.key = 'fld-run'; run.title = 'The run ' + c.run + ' on the Train tab';
    run.addEventListener('click', ev => { ev.preventDefault(); act.go('train', 'run:' + c.run); });
    line.appendChild(run); hd.appendChild(line);
    return hd;
  }
  /** Another case: its first slice read, then the section built again and put in place. */
  async function chooseCase(ctx, key) {
    const { model, act, box } = ctx, c = model.cases.find(x => x.key === key); if (!c) return;
    act.keepUI('anaCase', key); act.keepUI('anaAxis', null); act.keepUI('anaIndex', null);
    const next = { cases: model.cases, chosen: c, view: null, cmp: null, error: null };
    box.setAttribute('aria-busy', 'true');
    if (c.comparable) { next.view = viewFor(c, { anaMeanFree: ctx.v ? ctx.v.meanFree : false }); try { next.cmp = await R.fieldCompare(c.run, argsOf(c, next.view), true); } catch (error) { next.error = error; } }
    if (!box.isConnected) return;
    const fresh = h('div'); fill(fresh, next, act);
    const frag = document.createDocumentFragment(); frag.append(...fresh.childNodes);
    box.removeAttribute('aria-busy');
    putInPlace(box, frag, document.getElementById('main'));
  }

  /** The axis cut across, the sliders of the axes not drawn and "Remove the mean"; drawn again when the axis changes. */
  function controls(ctx) {
    const { c, v } = ctx, nd = c.shape.length, names = axisNames(nd), items = [];
    if (nd >= 3) {
      const s = h('select'); s.setAttribute('aria-label', 'The axis cut across'); s.dataset.key = 'fld-axis';
      for (let a = 0; a < nd; a++) { const o = h('option', null, names[a] + ' (' + c.shape[a] + ')'); o.value = String(a); o.selected = a === v.axis; s.appendChild(o); }
      s.addEventListener('change', () => { v.axis = Number(s.value); ctx.act.keepUI('anaAxis', String(v.axis)); controls(ctx); ask(ctx); });
      const l = h('label', 'iv-field'); l.appendChild(document.createTextNode('Cut across')); l.appendChild(s); items.push(l);
      for (const a of fixedAxes(nd, v.axis)) {
        const l2 = h('label', 'iv-field iv-slider'); l2.appendChild(h('span', null, a === v.axis ? 'Position on ' + names[a] : names[a]));
        const r = h('input'); r.type = 'range'; r.min = '0'; r.max = String(c.shape[a] - 1); r.value = String(v.index[a]); r.dataset.key = 'fld-slider-' + a; r.dataset.axis = String(a);
        r.setAttribute('aria-label', 'Position on ' + names[a] + ', 0 to ' + (c.shape[a] - 1));
        const at = h('span', 'num small fld-at', v.index[a] + ' of ' + c.shape[a]);
        r.addEventListener('input', () => { v.index[a] = Number(r.value); at.textContent = v.index[a] + ' of ' + c.shape[a]; ctx.act.keepUI('anaIndex', v.index.join(',')); ask(ctx); });
        l2.appendChild(r); l2.appendChild(at); items.push(l2);
      }
    }
    const mean = button('btn sm fld-mean', 'Remove the mean', () => { v.meanFree = !v.meanFree; mean.setAttribute('aria-pressed', String(v.meanFree)); ctx.act.keepUI('anaMeanFree', v.meanFree ? '1' : null); ask(ctx); });
    mean.dataset.key = 'fld-mean'; mean.setAttribute('aria-pressed', String(v.meanFree)); mean.title = 'Take each field\'s mean from it before the error is formed (a pressure is defined only up to a constant)';
    items.push(mean);
    if (ctx.ctl.isConnected) { const frag = document.createDocumentFragment(); frag.append(...items); putInPlace(ctx.ctl, frag, document.getElementById('main')); }
    else ctx.ctl.replaceChildren(...items);
  }
  /** The axes not drawn of a field of nd axes cut across axis: axis first, then the other. */
  const fixedAxes = (nd, axis) => { const others = []; for (let a = 0; a < nd; a++) if (a !== axis) others.push(a); return [axis].concat(others.slice(0, -2)); };

  /** Asks field_compare for the person's place: at most one request in flight; one asked meanwhile waits, the latest wins. */
  function ask(ctx) {
    if (ctx.busy) { ctx.again = true; return; }
    ctx.busy = true; ctx.again = false; ctx.panels.setAttribute('aria-busy', 'true');
    R.fieldCompare(ctx.c.run, argsOf(ctx.c, ctx.v), true).then(cmp => {
      if (ctx.again || !ctx.panels.isConnected) return;
      ctx.cmp = cmp; ctx.err.replaceChildren(); redraw(ctx); figures(ctx);
    }, error => { if (!ctx.again) ctx.err.replaceChildren(refusal(error)); }).finally(() => {
      ctx.busy = false;
      if (ctx.again && ctx.panels.isConnected) ask(ctx); else ctx.panels.removeAttribute('aria-busy');
    });
  }

  // ---- The three panels -----------------------------------------------------------------------------------------------
  const PANELS = [['reference', 'Native', 'reference_f32'], ['predicted', 'Predicted', 'predicted_f32'], ['error', 'Signed error (predicted − native)', 'error_f32']];
  function panels(ctx) {
    const wrap = h('div', 'fld-panels'); ctx.parts = {};
    for (const [id, title, field] of PANELS) {
      const fig = h('figure', 'fld-panel'); fig.dataset.panel = id;
      fig.appendChild(h('figcaption', 'fld-title', title));
      const cv = h('canvas', 'fld-cv'); cv.setAttribute('role', 'img'); cv.dataset.panel = id; fig.appendChild(cv);
      const bar = h('canvas', 'fld-bar'); bar.setAttribute('aria-hidden', 'true'); fig.appendChild(bar);
      const ends = h('div', 'iv-ends small faint fld-ends'); fig.appendChild(ends);
      ctx.parts[id] = { cv, bar, ends, field };
      D.paints(cv, () => drawPanel(ctx, id)); D.paints(bar, () => drawBar(ctx, id));
      cv.addEventListener('mousemove', ev => hover(ctx, id, ev)); cv.addEventListener('mouseleave', () => { ctx.tip.hidden = true; });
      wrap.appendChild(fig);
    }
    ctx.tip = h('div', 'fld-tip'); ctx.tip.hidden = true; ctx.tip.setAttribute('role', 'status'); wrap.appendChild(ctx.tip);
    ctx.say = h('p', 'small muted fld-where'); ctx.err = h('div', 'fld-err');
    const outer = h('div', 'fld-view'); outer.appendChild(wrap); outer.appendChild(ctx.say); outer.appendChild(ctx.err);
    ctx.wrap = wrap; decode(ctx); label(ctx);
    return outer;
  }
  /** The answer's three slices as floats, and the scales they are drawn on. */
  function decode(ctx) {
    const a = ctx.cmp, range = a.range || [0, 0];
    ctx.values = { reference: D.floats(a.reference_f32), predicted: D.floats(a.predicted_f32), error: D.floats(a.error_f32) };
    ctx.scale = { reference: sequential(range[0], range[1]), predicted: sequential(range[0], range[1]), error: diverging(a.error_limit || 0) };
  }
  function redraw(ctx) {
    decode(ctx); label(ctx);
    for (const id of Object.keys(ctx.parts)) { drawPanel(ctx, id); drawBar(ctx, id); }
    ctx.wrap.dataset.index = JSON.stringify(ctx.cmp.index); ctx.wrap.dataset.axis = String(ctx.cmp.axis); ctx.wrap.dataset.meanFree = String(ctx.cmp.mean_free);
  }
  /** What the panels show, in words: their labels, the colour bars' ends and the line under them. */
  function label(ctx) {
    const a = ctx.cmp, c = ctx.c, nd = c.shape.length, names = axisNames(nd), range = a.range;
    const where = nd >= 3 ? 'through ' + a.axes.map(x => names[x]).join(' and ') + ' at ' + fixedAxes(nd, a.axis).map(x => names[x] + ' = ' + a.index[x]).join(', ') : nd === 2 ? 'the whole field' : 'the whole line';
    for (const [id, title] of PANELS) {
      const p = ctx.parts[id];
      p.cv.setAttribute('aria-label', title + ', ' + a.rows + ' by ' + a.columns + ' cells ' + where + (id === 'error' ? ', ±' + fmt(a.error_limit) + ' about zero' + (a.mean_free ? ', each mean removed' : '') : range ? ', from ' + fmt(range[0]) + ' to ' + fmt(range[1]) : ''));
      p.ends.replaceChildren(...(id === 'error' ? ['−' + fmt(a.error_limit), '0', '+' + fmt(a.error_limit)] : range ? [fmt(range[0]), fmt(range[1])] : ['—', '—']).map(t => h('span', null, t)));
    }
    ctx.say.textContent = 'A slice ' + where + (a.stride > 1 ? ', every ' + D.ordinal(a.stride) + ' row and column' : '') + '. Native and predicted share one scale' + (range ? ' from ' + fmt(range[0]) + ' to ' + fmt(range[1]) : '') + '; the error is coloured on ±' + fmt(a.error_limit) + ' about zero' + (a.mean_free ? ', with each field\'s mean removed first' : '') + (c.mask ? '; outside the mask is left blank' : '') + '.';
  }
  function drawPanel(ctx, id) {
    const p = ctx.parts[id], cv = p.cv, a = ctx.cmp, w = cv.clientWidth; if (!w) return;
    const cssH = a.rows === 1 ? 28 : Math.max(32, Math.min(PANEL_MOST, Math.round(w * a.rows / a.columns)));
    const size = D.fit(cv, cssH); if (!size) return; const g = cv.getContext('2d'); g.clearRect(0, 0, size[0], size[1]);
    const rect = a.rows === 1 ? [0, 0, size[0], size[1]] : D.contain(a.rows, a.columns, size[0], size[1]);
    p.rect = rect.map(x => x / (window.devicePixelRatio || 1));
    D.heat(g, ctx.values[id], a.rows, a.columns, ctx.scale[id], rect[0], rect[1], rect[2], rect[3]);
    cv.dataset.drawn = String((cv._drawn = (cv._drawn || 0) + 1));
  }
  function drawBar(ctx, id) {
    const p = ctx.parts[id], size = D.fit(p.bar, 10); if (!size) return;
    const a = ctx.cmp, n = 64, vals = new Float32Array(n), m = a.error_limit || 0, range = a.range || [0, 0];
    for (let i = 0; i < n; i++) { const t = (i + 0.5) / n; vals[i] = id === 'error' ? -m + 2 * m * t : range[0] + (range[1] - range[0]) * t; }
    D.heat(p.bar.getContext('2d'), vals, 1, n, id === 'error' ? diverging(m) : ctx.scale[id], 0, 0, size[0], size[1]);
  }
  /** The tip under the pointer: the cell's position in the field and its three values. */
  function hover(ctx, id, ev) {
    const p = ctx.parts[id], a = ctx.cmp; if (!p.rect) return;
    const box = p.cv.getBoundingClientRect(), x = ev.clientX - box.left - p.rect[0], y = ev.clientY - box.top - p.rect[1];
    const col = Math.floor(x / p.rect[2] * a.columns), row = Math.floor(y / p.rect[3] * a.rows);
    if (col < 0 || row < 0 || col >= a.columns || row >= a.rows) { ctx.tip.hidden = true; return; }
    const i = row * a.columns + col, at = a.index.slice(), nd = ctx.c.shape.length;
    if (nd === 1) at[0] = col * a.stride; else { at[a.axes[0]] = row * a.stride; at[a.axes[1]] = col * a.stride; }
    const names = axisNames(nd), v = ctx.values;
    const outside = !Number.isFinite(v.reference[i]) && !Number.isFinite(v.predicted[i]) && ctx.c.mask;
    ctx.tip.replaceChildren(h('div', 'mono fld-tip-at', (nd === 3 ? at.map((q, k) => names[k] + ' ' + q).join(', ') : '(' + at.join(', ') + ')')));
    if (outside) ctx.tip.appendChild(h('div', null, 'outside the mask'));
    else for (const [key, word] of [['reference', 'Native'], ['predicted', 'Predicted'], ['error', a.mean_free ? 'Error, means removed' : 'Error']]) { const r = h('div', 'fld-tip-row'); r.dataset.value = key; r.appendChild(h('span', null, word)); r.appendChild(h('span', 'num', fmt(v[key][i]))); ctx.tip.appendChild(r); }
    ctx.tip.dataset.cell = JSON.stringify(at);
    ctx.tip.hidden = false;
    const wrap = ctx.wrap.getBoundingClientRect(), tw = ctx.tip.offsetWidth, th = ctx.tip.offsetHeight;
    let left = ev.clientX - wrap.left + 14, top = ev.clientY - wrap.top + 14;
    if (left + tw > wrap.width) left = Math.max(0, ev.clientX - wrap.left - tw - 14);
    if (top + th > wrap.height + 40) top = Math.max(0, ev.clientY - wrap.top - th - 14);
    ctx.tip.style.left = left + 'px'; ctx.tip.style.top = top + 'px';
  }

  // ---- The figures ----------------------------------------------------------------------------------------------------
  const FIGURES = [['count', 'Cells counted'], ['nonfinite', 'Values not finite'], ['max_abs_error', 'Largest |error|'], ['mean_error', 'Mean error'], ['rmse', 'RMSE'], ['relative_l2', 'Relative L2'], ['mean_free_relative_l2', 'Mean-free relative L2']];
  function figures(ctx) {
    const f = ctx.cmp.figures, c = ctx.c, items = [];
    const t = h('table', 'tv fld-figures'); t.appendChild(h('caption', 'small muted', 'Over the whole field' + (c.mask ? ', inside the mask' : '') + ', whatever the slice'));
    const tb = h('tbody');
    for (const [key, word] of FIGURES) { const tr = h('tr'); tr.dataset.fig = key; tr.dataset.value = f[key] == null ? '' : String(f[key]); tr.appendChild(h('th', null, word)); tr.appendChild(h('td', 'n', key === 'count' || key === 'nonfinite' ? num(f[key]) : fmt(f[key]))); tb.appendChild(tr); }
    t.appendChild(tb); items.push(t);
    if (c.reported && c.reported.length) {
      const r = h('table', 'tv fld-reported'); r.appendChild(h('caption', 'small muted', 'The run reported'));
      const rb = h('tbody');
      for (const x of c.reported) { const tr = h('tr'); tr.dataset.value = String(x.value); const th = h('th', 'mono', x.field); th.title = 'In ' + x.file; tr.appendChild(th); tr.appendChild(h('td', 'n', fmt(x.value))); rb.appendChild(tr); }
      r.appendChild(rb); items.push(r);
    }
    ctx.figs.replaceChildren(...items);
  }

  // The parts the Compare tab draws its outputs with (compare.js): the cases, the person's place in one, the request's
  // arguments, the axes' names and the colour scales.
  const parts = { keptCases, viewFor, argsOf, axisNames, fixedAxes, sequential, diverging, PANEL_MOST };
  return { read, section, parts };
})();
