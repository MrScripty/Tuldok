'use strict';
// Screen content shared by every layout. A shell decides where the main
// content and the inspector live; these functions fill them from window.LAB.
// Rule: the chrome holds no project words. Metric names, populations, group
// names and decisions come from the project data.
window.LabScreens = (() => {
  const LAB = window.LAB, Tree = window.LabTree, Charts = window.LabCharts;
  const h = (tag, cls, text) => { const n = document.createElement(tag); if (cls) n.className = cls; if (text !== undefined) n.textContent = text; return n; };
  const svgNS = 'http://www.w3.org/2000/svg';
  const ICONS = {
    check: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm-1.3 14.2-3.6-3.6 1.4-1.4 2.2 2.2 5.1-5.1 1.4 1.4z',
    alert: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm-1 5h2v6h-2zm0 8h2v2h-2z',
    triangle: 'M12 3 1 21h22zm-1 7h2v5h-2zm0 7h2v2h-2z',
    minus: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm-5 9h10v2H7z',
    branch: 'M7 3a3 3 0 0 0-1 5.8v6.4A3 3 0 1 0 8 15.2V9.9c1.2 1.3 2.9 2.1 5 2.1 2.8 0 4.4-1.5 5-4.1A3 3 0 1 0 16 7.6c-.5 1.6-1.4 2.4-3 2.4-2.6 0-4.3-1.6-5-3.2A3 3 0 0 0 7 3z',
    clock: 'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm1 5h-2v6l5 3 1-1.7-4-2.3z',
    x: 'M18.3 5.7 12 12l6.3 6.3-1.4 1.4L10.6 13.4 4.3 19.7 2.9 18.3 9.2 12 2.9 5.7l1.4-1.4 6.3 6.3 6.3-6.3z',
    theme: 'M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18zm0 2v14a7 7 0 0 1 0-14z'
  };
  const icon = name => { const s = document.createElementNS(svgNS, 'svg'); s.setAttribute('viewBox', '0 0 24 24'); s.setAttribute('aria-hidden', 'true'); const p = document.createElementNS(svgNS, 'path'); p.setAttribute('d', ICONS[name] || ICONS.minus); p.setAttribute('fill', 'currentColor'); p.setAttribute('fill-rule', 'evenodd'); s.appendChild(p); return s; };
  const stateEl = (kind, text) => { const map = { good: 'check', warn: 'alert', serious: 'triangle', neutral: 'minus', pending: 'clock' }; const s = h('span', 'state ' + (kind === 'pending' ? 'warn' : kind)); s.appendChild(icon(map[kind] || 'minus')); s.appendChild(document.createTextNode(text)); return s; };
  const fmtDate = iso => new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' });
  const fmtBytes = b => b == null ? '—' : b > 1e6 ? (b / 1e6).toFixed(1) + ' MB' : b > 1e3 ? Math.round(b / 1e3) + ' KB' : b + ' B';
  let graph = Tree.build(LAB.models, LAB.relationships), byId = graph.byId, plannedVersion = 0;
  function setPlanned(list) {
    const extra = list.map(pl => { const p = LAB.models.find(m => m.id === pl.parent); return Object.assign({ id: pl.id, ck: null, n: p && p.n != null ? p.n + 0.5 : null, label: 'New model from ' + (p ? (p.ck || p.short) : '?'), short: pl.name || 'new model', alias: null, group: p ? p.group : 'pressure-other', groupLabel: p ? p.groupLabel : '', kind: pl.kind || 'refinement', worstP: null, eq: null, ms: null, params: null, purpose: '', outcome: '', lesson: '', parents: [pl.parent], planned: true, setup: pl.setup }); });
    graph = Tree.build(LAB.models.concat(extra), LAB.relationships); byId = graph.byId; plannedVersion++;
  }
  const MET = LAB.metrics, ACC = MET.accuracy, TIME = MET.time;
  const accLabel = id => (ACC.find(a => a.id === id) || ACC[0]).label;
  const benchModels = () => LAB.models.filter(m => m.group !== MET.excludedGroup);
  const withBench = LAB.models.filter(m => m[ACC[0].id] != null && m[TIME.id] != null).length;
  const KINDS = ['training', 'architecture', 'refinement', 'composition'];
  // Checkpoint sections for the sequence chart, read from authored group labels of the form "C16–C25 · name".
  const CURVE_SECTIONS = LAB.groups.map(g => { const m = /^C(\d+)[–-]C(\d+)\s*·\s*(.+)$/.exec(g.label); return m ? { from: +m[1], label: m[3].split(/\s+/)[0] } : null; }).filter(Boolean);
  const studyState = s => s.state === 'closed' ? 'pending' : s.decision.includes('failed') ? 'serious' : s.decision.includes('no promotion') ? 'neutral' : 'good';
  const sect = (title, sum) => { const d = h('div', 'sect'); d.appendChild(h('h2', null, title)); if (sum) d.appendChild(h('span', 'sum', sum)); return d; };
  const DOC_ROLE = path => /plan\.md$/.test(path) ? 'Plan' : /ledger\.md$/.test(path) ? 'Methods' : /(results?\.md|current\.json|results\.json)$/.test(path) ? 'Results' : null;
  const docsOf = plan => { const g = LAB.project.evidence.find(x => x.plan === plan); return g ? g.items.map(([id, label, path]) => ({ id, label: DOC_ROLE(path) || label, path })) : []; };
  const docChips = (plan, sel, onPick) => { const d = h('span', 'docs'); for (const doc of docsOf(plan)) { const b = h('button', null, doc.label); b.type = 'button'; b.title = doc.path; b.setAttribute('aria-pressed', String(doc.id === sel)); b.addEventListener('click', ev => { ev.stopPropagation(); onPick(doc.id); }); d.appendChild(b); } return d; };
  const fileLink = (rel, text) => { const a = h('a', 'path', text || rel); const dir = rel.includes('/') ? rel.slice(0, rel.lastIndexOf('/')) : ''; a.href = 'file://' + LAB.project.rootPath + '/' + dir; a.title = 'Open folder'; a.addEventListener('click', ev => ev.stopPropagation()); return a; };
  const KIND_ICON = { fields: 'M3 3h18v18H3zm2 2v4h4V5zm6 0v4h4V5zm6 0v4h2V5zM5 11v4h4v-4zm6 0v4h4v-4zm6 0v4h2v-4zM5 17v2h4v-2zm6 0v2h4v-2zm6 0v2h2v-2z', records: 'M4 4h16v3H4zm0 5h16v3H4zm0 5h16v3H4zm0 5h10v2H4z', manifest: 'M6 2h9l5 5v15H6zm8 1.5V8h4.5zM8 11h8v2H8zm0 4h8v2H8z', results: 'M3 21V3h2v16h16v2zm4-4 4-6 3 3 5-8 1.5 1-6.5 10-3-3-3 4.5z' };
  const kindIcon = k => { const sv = document.createElementNS(svgNS, 'svg'); sv.setAttribute('viewBox', '0 0 24 24'); sv.setAttribute('aria-hidden', 'true'); const pth = document.createElementNS(svgNS, 'path'); pth.setAttribute('d', KIND_ICON[k] || KIND_ICON.records); pth.setAttribute('fill', 'currentColor'); pth.setAttribute('fill-rule', 'evenodd'); sv.appendChild(pth); return sv; };
  function fieldPreview(canvas, seed) {
    const ctx = canvas.getContext('2d'), W = canvas.width = 320, Hh = canvas.height = 180, nx = 32, ny = 18;
    const dark = getComputedStyle(document.documentElement).colorScheme === 'dark';
    const mid = dark ? [56, 56, 53] : [240, 239, 236], neg = dark ? [79, 138, 224] : [46, 111, 207], pos = dark ? [217, 111, 60] : [210, 101, 47];
    for (let j = 0; j < ny; j++) for (let i = 0; i < nx; i++) {
      const u = i / nx, v = j / ny, val = Math.sin(6.3 * u + seed) * Math.cos(4.7 * v - seed * 0.5) * 0.7 + Math.sin(12 * u * v + seed) * 0.3;
      const c = val < 0 ? neg : pos, t = Math.min(1, Math.abs(val)); const rgb = mid.map((m, k) => Math.round(m + (c[k] - m) * t));
      ctx.fillStyle = `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`; ctx.fillRect(i * W / nx, j * Hh / ny, W / nx + 1, Hh / ny + 1);
    }
  }
  const seeded = str => { let x = 0; for (const ch of str) x = (x * 31 + ch.charCodeAt(0)) % 1000003; return () => { x = (x * 1103515245 + 12345) % 2147483648; return x / 2147483648; }; };
  // Training curve for a fit: shaped by its recorded update count and final loss (mock data for the layout).
  const curveFor = m => { const U = m.updates || 2000, L = m.loss || (m.worstP ? m.worstP * 2000 : 10), rnd = seeded(m.id), pts = []; for (let i = 0; i <= 40; i++) { const u = U * i / 40; pts.push([u, L * (1 + 30 * Math.exp(-6 * u / U)) * (1 + 0.06 * (rnd() - 0.5))]); } return pts; };
  const recipeOf = id => (LAB.recipes || []).find(r => r.id === id);
  const runtimeOf = id => (LAB.runtimes || []).find(r => r.id === id);
  const datasetOf = id => LAB.project.data.find(r => r.id === id);
  const modelName = m => (m.ck ? m.ck + ' · ' : '') + m.short;
  const popOf = state => (MET.populations || []).find(p => p.id === (state.pop || 'pressure')) || { id: 'all', label: 'All' };
  const inPop = (m, pop) => pop.only ? m.group === pop.only : pop.exclude ? m.group !== pop.exclude : true;
  const benchState = m => { const a = m[ACC[0].id] != null, t = m[TIME.id] != null; return m.group === MET.excludedGroup ? 'generator benchmark' : a && t ? 'accuracy and time' : a ? 'accuracy only' : t ? 'time only' : 'none retained'; };
  const runStudy = m => { for (const [sid, trials] of Object.entries(LAB.project.trials || {})) for (const t of trials) if (t.run && t.run === m.ck) return LAB.project.studies.find(x => x.id === sid); return null; };
  const cell = (k, v, u) => { const d = h('div'); d.appendChild(h('dt', null, k)); const dd = h('dd', null, v); if (u) dd.appendChild(h('small', null, u)); d.appendChild(dd); return d; };

  function statusLine() { const a = LAB.project.activity; return { state: a.state, text: a.phase + '. ' + a.message, updated: fmtDate(a.updated), producer: a.producer }; }
  function stageSummaries() {
    const d = LAB.project.data, verified = d.filter(r => r.integrity === 'verified').length, missing = d.filter(r => r.state === 'missing').length;
    const st = LAB.project.studies, pending = st.filter(s => s.state === 'closed').length;
    return [
      { id: 'overview', label: 'Overview', sum: `${LAB.project.needs.length} need you` },
      { id: 'data', label: 'Data', sum: `${d.length} datasets` + (missing ? ` · ${missing} missing` : '') },
      { id: 'annotate', label: 'Annotate', sum: 'No records' },
      { id: 'models', label: 'Models', sum: `${LAB.models.length} fits · ${graph.families.length} branch points` },
      { id: 'train', label: 'Train', sum: `${LAB.models.length} runs · ${st.length} studies` + (pending ? ` · ${pending} waiting` : '') },
      { id: 'benchmarks', label: 'Benchmarks', sum: `${withBench} benchmarked` },
      { id: 'analysis', label: 'Analysis', sum: `${LAB.project.evidence.reduce((n, g) => n + g.items.length, 0)} notes` }
    ];
  }

  // ---- Overview ------------------------------------------------------------
  function overview(main, aside, state, act) {
    main.textContent = ''; aside.textContent = '';
    const s = statusLine();
    const top = h('section', 'ov-status');
    const line = h('div', 'ov-line');
    line.appendChild(stateEl(s.state === 'completed' ? 'good' : s.state === 'failed' ? 'serious' : 'pending', s.state === 'completed' ? 'Completed' : s.state));
    line.appendChild(h('p', 'ov-text', s.text)); top.appendChild(line);
    top.appendChild(h('p', 'small faint', `${s.producer} · ${s.updated}`));
    main.appendChild(top);

    const row = h('div', 'ov-row');
    const needs = h('section'); needs.appendChild(sect('Needs you', String(LAB.project.needs.length)));
    const ul = h('ul', 'needs');
    for (const n of LAB.project.needs) {
      const li = h('li', n.kind); li.appendChild(icon(n.kind === 'approval' ? 'clock' : n.kind === 'changed' ? 'alert' : 'triangle'));
      li.appendChild(h('span', null, n.text));
      const b = h('button', 'btn sm', n.kind === 'approval' ? 'Review' : 'Open'); b.type = 'button'; b.addEventListener('click', () => act.go(n.where, n.ref)); li.appendChild(b);
      ul.appendChild(li);
    }
    needs.appendChild(ul); row.appendChild(needs);
    const facts = h('section'); facts.appendChild(sect('Project'));
    const dl = h('dl', 'facts');
    for (const [k, v, c] of [['Manifest', `${LAB.project.root}/${LAB.project.manifest}`, 'mono'], ['Schema', String(LAB.project.schema)], ['Snapshot', LAB.project.id, 'mono'], ['Requirements', LAB.project.requirements.map(r => r.label).join('; ')], ['Execution', 'inspection only']]) { dl.appendChild(h('dt', null, k)); dl.appendChild(h('dd', c || '', v)); }
    facts.appendChild(dl); row.appendChild(facts); main.appendChild(row);

    const cols = h('div', 'ov-cols');
    const st = h('section'); st.appendChild(sect('Stages'));
    const sl = h('ul', 'rows');
    for (const g of stageSummaries().filter(x => x.id !== 'overview')) { const li = h('li'); const b = h('button', 'row ov-stage'); b.type = 'button'; b.appendChild(h('span', 'title', g.label)); b.appendChild(h('span', 'sub', g.sum)); b.addEventListener('click', () => act.go(g.id)); li.appendChild(b); sl.appendChild(li); }
    st.appendChild(sl); cols.appendChild(st);
    const rs = h('section'); rs.appendChild(sect('Studies', 'newest first'));
    const rl = h('ul', 'rows');
    for (const s2 of LAB.project.studies.slice().sort((a, b) => b.updated.localeCompare(a.updated)).slice(0, 6)) {
      const li = h('li'); const b = h('button', 'row ov-study'); b.type = 'button';
      b.appendChild(stateEl(studyState(s2), ''));
      const t = h('span'); t.appendChild(h('span', 'title', s2.label)); t.appendChild(h('span', 'sub', s2.decision)); b.appendChild(t);
      b.appendChild(h('span', 'sub num', fmtDate(s2.updated)));
      b.addEventListener('click', () => act.go('train', s2.id)); li.appendChild(b); rl.appendChild(li);
    }
    rs.appendChild(rl); cols.appendChild(rs); main.appendChild(cols);

    const lg = h('section', 'ov-history'); lg.appendChild(sect('Model history', `${accLabel(ACC[0].id)} per checkpoint`));
    const c = h('div'); lg.appendChild(c);
    Charts.curve(c, LAB.models, { selected: null, onSelect: id => act.go('models', id), metric: ACC[0].id, sections: CURVE_SECTIONS, yLabel: accLabel(ACC[0].id), secondary: ACC[1] || null });
    const bp = h('div', 'actions');
    for (const f of graph.families) { const pp = byId.get(f.parent); const b = h('button', 'btn sm'); b.type = 'button'; b.appendChild(icon('branch')); b.appendChild(document.createTextNode(` ${pp.ck || pp.short} · ${f.children.length} fits`)); b.addEventListener('click', () => act.go('models', pp.id)); bp.appendChild(b); }
    const open = h('button', 'btn sm ghost', 'All models'); open.type = 'button'; open.addEventListener('click', () => act.go('models')); bp.appendChild(open);
    lg.appendChild(bp); main.appendChild(lg);
    return false;
  }

  // ---- Data: datasets, then the records inside one, with a volume viewer ----
  const DIV = () => { const dark = getComputedStyle(document.documentElement).colorScheme === 'dark'; return { mid: dark ? [56, 56, 53] : [240, 239, 236], neg: dark ? [79, 138, 224] : [46, 111, 207], pos: dark ? [217, 111, 60] : [210, 101, 47] }; };
  const SEQ = () => { const dark = getComputedStyle(document.documentElement).colorScheme === 'dark'; return { lo: dark ? [31, 38, 46] : [236, 240, 246], hi: dark ? [79, 138, 224] : [28, 92, 171] }; };
  // Synthetic volume field for the layout: smooth structure that varies by record, field and position.
  const volumeFn = (seed, field) => (u, v, w) => { const a = seed * 0.37, b = seed * 0.11; const base = Math.sin(6.3 * u + a) * Math.cos(4.7 * v - b) * Math.cos(3.1 * w + a) * 0.7 + Math.sin(9 * u * v + 5 * w + b) * 0.3; if (/velocity/.test(field)) return Math.abs(base) * 0.9; if (/tracer/.test(field)) return Math.max(0, Math.sin(7 * (u - 0.5) * (v - 0.5) * 8 + w * 4 + a)) * 0.9; if (/error/.test(field)) return Math.sin(17 * u + 3 * a) * Math.cos(13 * v + b) * Math.sin(5 * w) * 0.6; return base; };
  const paint = (val, signed, c, q) => { if (signed) { const col = val < 0 ? c.neg : c.pos, t = Math.min(1, Math.abs(val)); return c.mid.map((m, k) => Math.round(m + (col[k] - m) * t)); } const t = Math.min(1, Math.max(0, val)); return q.lo.map((m, k) => Math.round(m + (q.hi[k] - m) * t)); };
  function drawSlice2(canvas, fn, signed, n, size, w) {
    const ctx = canvas.getContext('2d'); canvas.width = size; canvas.height = size; const c = DIV(), q = SEQ();
    for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) { const rgb = paint(fn(i / n, j / n, w), signed, c, q); ctx.fillStyle = `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`; ctx.fillRect(i * size / n, j * size / n, size / n + 1, size / n + 1); }
  }
  // Isometric stack of slices: a voxel-like impression of the whole grid.
  function drawVolume(canvas, fn, signed, dims, wSel) {
    const W = canvas.width = 480, H = canvas.height = 360, ctx = canvas.getContext('2d'); ctx.clearRect(0, 0, W, H); const c = DIV(), q = SEQ();
    const [nx, ny, nz] = dims, sx = 16, sy = Math.max(4, Math.round(16 * ny / nx)), nsl = Math.min(nz, 10);
    const cw = Math.min(14, 300 / sx), ch = cw * 0.5, dz = Math.min(22, 220 / nsl);
    const ox = W / 2 - (sx * cw) / 2 + (sy * cw) / 4, oy = H - 40 - (nsl - 1) * dz - (sy * ch) / 2;
    for (let k = 0; k < nsl; k++) {
      const w = (k + 0.5) / nsl, hot = wSel != null && Math.abs(w - wSel) < 0.5 / nsl + 1e-6;
      ctx.globalAlpha = hot ? 1 : 0.55;
      for (let j = 0; j < sy; j++) for (let i = 0; i < sx; i++) {
        const rgb = paint(fn(i / sx, j / sy, w), signed, c, q); ctx.fillStyle = `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
        const px = ox + i * cw - j * (cw / 2), py = oy + (nsl - 1 - k) * dz + j * ch + i * (ch / 2) * 0;
        ctx.beginPath(); ctx.moveTo(px, py); ctx.lineTo(px + cw, py); ctx.lineTo(px + cw - cw / 2, py + ch); ctx.lineTo(px - cw / 2, py + ch); ctx.closePath(); ctx.fill();
      }
      if (hot) { ctx.globalAlpha = 1; ctx.strokeStyle = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#2c5fb8'; ctx.lineWidth = 2; const py = oy + (nsl - 1 - k) * dz; ctx.beginPath(); ctx.moveTo(ox, py); ctx.lineTo(ox + sx * cw, py); ctx.lineTo(ox + sx * cw - sy * cw / 2, py + sy * ch); ctx.lineTo(ox - sy * cw / 2, py + sy * ch); ctx.closePath(); ctx.stroke(); }
    }
    ctx.globalAlpha = 1;
  }
  function data(main, aside, state, act) {
    main.textContent = ''; aside.textContent = '';
    const sel = state.sel.data, d0 = LAB.project.data, ACTIONS = ['import', 'generate', 'release'];
    const ds = d0.find(x => x.id === sel);
    if (ds && ds.state !== 'missing') return datasetView(main, aside, ds, state, act);
    const ac = h('div', 'ds-actions');
    for (const [id, t] of [['import', 'Import'], ['generate', 'Generate'], ['annotate', 'Annotate'], ['release', 'Release']]) { const b = h('button', 'btn', t); b.type = 'button'; b.setAttribute('aria-pressed', String(sel === id)); b.addEventListener('click', () => id === 'annotate' ? act.go('annotate') : act.select(sel === id ? null : id)); ac.appendChild(b); }
    main.appendChild(ac);
    main.appendChild(sect('Datasets', String(d0.length)));
    const grid = h('div', 'ds-grid');
    for (const r of d0) {
      const b = h('button', 'ds-card'); b.type = 'button'; b.setAttribute('aria-pressed', String(r.id === sel));
      if (r.state !== 'missing') { const cv = h('canvas', 'pv'); b.appendChild(cv); const fn = volumeFn(r.id.length * 3 + 1, r.fields[0]); const ctx = cv.getContext('2d'); cv.width = 320; cv.height = 180; const c = DIV(), q = SEQ(); const n = 32, m = 18; for (let j = 0; j < m; j++) for (let i = 0; i < n; i++) { const rgb = paint(fn(i / n, j / m, 0.5), !/velocity|tracer/.test(r.fields[0]), c, q); ctx.fillStyle = `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`; ctx.fillRect(i * 10, j * 10, 11, 11); } }
      else b.appendChild(h('div', 'pv text', 'file missing'));
      const t = h('div', 't'); t.appendChild(h('div', 'title', r.label));
      const meta = h('div', 'meta'); meta.appendChild(h('span', null, r.records.toLocaleString('en-GB') + ' ' + r.recordKind + (r.records === 1 ? '' : 's') + ' · ' + r.grid.join('×'))); meta.appendChild(h('span', null, fmtBytes(r.bytes)));
      const g = h('span', 'glyph ' + (r.state === 'missing' ? 'serious' : r.integrity === 'verified' ? 'good' : 'neutral')); g.appendChild(icon(r.state === 'missing' ? 'triangle' : r.integrity === 'verified' ? 'check' : 'minus')); g.title = r.state === 'missing' ? 'Missing' : r.integrity === 'verified' ? 'Hash verified' : 'No declared hash'; meta.appendChild(g); t.appendChild(meta);
      t.appendChild(fileLink(r.path)); b.appendChild(t);
      b.addEventListener('click', () => act.select(r.id)); grid.appendChild(b);
    }
    main.appendChild(grid);
    if (ACTIONS.includes(sel)) { dataPanel(aside, sel, state, act); return true; }
    if (ds && ds.state === 'missing') {
      const ins = h('div', 'inspector'); const hd = h('header'); hd.appendChild(h('span', 'kicker', ds.kind + ' · ' + ds.id)); hd.appendChild(h('h2', null, ds.label)); ins.appendChild(hd);
      const dl = h('dl', 'metrics'); dl.appendChild(cell('Records', `${ds.records} ${ds.recordKind}s`)); dl.appendChild(cell('Grid', ds.grid.join(' × '))); dl.appendChild(cell('State', 'file missing')); ins.appendChild(dl);
      const pa = h('p', 'note'); pa.appendChild(fileLink(ds.path)); ins.appendChild(pa); ins.appendChild(h('p', 'note', 'Restore the file, or open a new snapshot without it.')); aside.appendChild(ins); return true;
    }
    const ins = h('div', 'inspector'); const dl = h('dl', 'metrics');
    dl.appendChild(cell('Datasets', String(d0.length))); dl.appendChild(cell('Records', d0.reduce((a, x) => a + (x.records || 0), 0).toLocaleString('en-GB'))); dl.appendChild(cell('On disk', fmtBytes(d0.reduce((a, x) => a + (x.bytes || 0), 0)))); dl.appendChild(cell('Missing', String(d0.filter(x => x.state === 'missing').length)));
    ins.appendChild(dl); aside.appendChild(ins); return false;
  }
  function datasetView(main, aside, r, state, act) {
    const ui = state.ui || {}, per = 48, page = ui['page:' + r.id] || 0, rec = ui['rec:' + r.id] != null ? ui['rec:' + r.id] : 0, field = ui['field:' + r.id] || r.fields[0], w = ui['w:' + r.id] != null ? ui['w:' + r.id] : 0.5;
    const back = h('button', 'btn sm ghost ds-back', '← All datasets'); back.type = 'button'; back.addEventListener('click', () => act.select(null)); main.appendChild(back);
    const head = h('div', 'ds-head'); head.appendChild(h('h2', null, r.label));
    const meta = h('div', 'meta'); meta.appendChild(h('span', null, `${r.records.toLocaleString('en-GB')} ${r.recordKind}${r.records === 1 ? '' : 's'}` + (r.scenes ? ` · ${r.scenes} scenes` : ''))); meta.appendChild(h('span', null, r.grid.join(' × ') + ' cells')); meta.appendChild(h('span', null, fmtBytes(r.bytes)));
    const g = h('span', 'glyph ' + (r.integrity === 'verified' ? 'good' : 'neutral')); g.appendChild(icon(r.integrity === 'verified' ? 'check' : 'minus')); g.title = r.integrity === 'verified' ? 'Hash verified' : 'No declared hash'; meta.appendChild(g); meta.appendChild(fileLink(r.path)); head.appendChild(meta);
    const acts = h('div', 'actions'); const a1 = h('a', 'btn sm', 'Open folder'); a1.href = fileLink(r.path).href; acts.appendChild(a1); const b2 = h('button', 'btn sm', 'Annotate'); b2.type = 'button'; b2.disabled = r.kind !== 'records'; acts.appendChild(b2); const b3 = h('button', 'btn sm', 'Release'); b3.type = 'button'; b3.addEventListener('click', () => { act.setDataAction('dataset', r.id); act.select('release'); }); acts.appendChild(b3); head.appendChild(acts);
    main.appendChild(head);
    if (r.describes) main.appendChild(h('p', 'small muted', r.describes)).style.marginBottom = '12px';
    const body = h('div', 'ds-body');
    const left = h('div'); left.appendChild(sect(r.recordKind.charAt(0).toUpperCase() + r.recordKind.slice(1) + 's', `${page * per + 1}–${Math.min(r.records, (page + 1) * per)} of ${r.records}`));
    const grid = h('div', 'rec-grid');
    for (let i = page * per; i < Math.min(r.records, (page + 1) * per); i++) {
      const b = h('button', 'rec'); b.type = 'button'; b.setAttribute('aria-pressed', String(i === rec)); b.setAttribute('aria-label', r.recordKind + ' ' + (i + 1));
      const cv = h('canvas'); drawSlice2(cv, volumeFn(i + 1, field), !/velocity|tracer/.test(field), 16, 64, 0.5); b.appendChild(cv); b.appendChild(h('span', null, String(i + 1)));
      b.addEventListener('click', () => act.setUI('rec:' + r.id, i)); grid.appendChild(b);
    }
    left.appendChild(grid);
    if (r.records > per) { const pg = h('div', 'pager'); const pb = h('button', 'btn sm', 'Previous'); pb.type = 'button'; pb.disabled = page === 0; pb.addEventListener('click', () => act.setUI('page:' + r.id, page - 1)); const nb = h('button', 'btn sm', 'Next'); nb.type = 'button'; nb.disabled = (page + 1) * per >= r.records; nb.addEventListener('click', () => act.setUI('page:' + r.id, page + 1)); pg.appendChild(pb); pg.appendChild(nb); pg.appendChild(h('span', null, `page ${page + 1} of ${Math.ceil(r.records / per)}`)); left.appendChild(pg); }
    body.appendChild(left);
    const vw = h('div', 'viewer');
    const fn = volumeFn(rec + 1, field), signed = !/velocity|tracer/.test(field);
    const vol = h('canvas', 'vol'); vol.setAttribute('role', 'img'); vol.setAttribute('aria-label', `${field} volume of ${r.recordKind} ${rec + 1}, ${r.grid.join(' by ')} cells`); drawVolume(vol, fn, signed, r.grid, w); vw.appendChild(vol);
    const row2 = h('div', 'row2'); const sl = h('canvas', 'sl'); sl.setAttribute('role', 'img'); sl.setAttribute('aria-label', 'Slice'); drawSlice2(sl, fn, signed, 32, 240, w); row2.appendChild(sl);
    const facts = h('dl', 'facts facts-sm'); for (const [k, v] of [[r.recordKind.charAt(0).toUpperCase() + r.recordKind.slice(1), String(rec + 1) + (r.dt ? ' · t = ' + (rec * (r.dt.includes('/') ? 1 / +r.dt.split('/')[1].replace(/\D/g, '') : +r.dt)).toFixed(3) + ' s' : '')], ['Grid', r.grid.join(' × ')], ['Spacing', r.spacing || '—'], ['Fields', r.fields.join(', ')], ['Slice', 'z = ' + Math.round(w * (r.grid[2] - 1) + 1) + ' of ' + r.grid[2]]]) { facts.appendChild(h('dt', null, k)); facts.appendChild(h('dd', null, v)); }
    row2.appendChild(facts); vw.appendChild(row2);
    const ctl = h('div', 'ctl');
    const fl = h('label'); fl.appendChild(document.createTextNode('Field')); const fs = h('select'); for (const f of r.fields) { const o = h('option', null, f); o.selected = f === field; fs.appendChild(o); } fs.addEventListener('change', () => act.setUI('field:' + r.id, fs.value)); fl.appendChild(fs); ctl.appendChild(fl);
    const zl = h('label'); zl.appendChild(document.createTextNode('Slice')); const zi = h('input'); zi.type = 'range'; zi.min = 0; zi.max = r.grid[2] - 1; zi.value = Math.round(w * (r.grid[2] - 1)); zi.addEventListener('input', () => { const ww = +zi.value / Math.max(1, r.grid[2] - 1); drawVolume(vol, fn, signed, r.grid, ww); drawSlice2(sl, fn, signed, 32, 240, ww); const dd = facts.querySelectorAll('dd'); dd[dd.length - 1].textContent = 'z = ' + (+zi.value + 1) + ' of ' + r.grid[2]; }); zi.addEventListener('change', () => { state.ui['w:' + r.id] = +zi.value / Math.max(1, r.grid[2] - 1); }); zl.appendChild(zi); ctl.appendChild(zl);
    const an = h('button', 'btn sm', 'Compare in Analysis'); an.type = 'button'; an.addEventListener('click', () => { act.setCase(rec + 1); act.go('analysis'); }); ctl.appendChild(an);
    vw.appendChild(ctl); body.appendChild(vw); main.appendChild(body);
    return false;
  }
  function dataPanel(aside, kind, state, act) {
    const n = state.dataAction || {};
    const ins = h('div', 'inspector'); const f = h('div', 'form');
    const field = (label, control, hint) => { const l = h('label'); l.appendChild(document.createTextNode(label)); l.appendChild(control); if (hint) l.appendChild(h('span', 'hint', hint)); return l; };
    const radio = (name, opts, cur, key) => { const r = h('div', 'radio'); for (const [v, t] of opts) { const l = h('label'); const i = h('input'); i.type = 'radio'; i.name = name; i.checked = v === cur; i.addEventListener('change', () => act.setDataAction(key, v)); l.appendChild(i); l.appendChild(document.createTextNode(t)); r.appendChild(l); } return r; };
    const hd = h('header');
    if (kind === 'import') {
      hd.appendChild(h('span', 'kicker', 'data')); hd.appendChild(h('h2', null, 'Import')); ins.appendChild(hd);
      f.appendChild(field('Source', radio('src', [['files', 'Files or folder'], ['release', 'Catalog release'], ['project', 'Another project']], n.src || 'files', 'src')));
      const pathI = h('input'); pathI.type = 'text'; pathI.placeholder = 'relative to ' + LAB.project.root; pathI.value = n.path || ''; f.appendChild(field('Path', pathI));
      f.appendChild(field('Kind', radio('kind', [['fields', 'Fields'], ['images', 'Images'], ['text', 'Text'], ['audio', 'Audio'], ['mesh', 'Mesh']], n.kind || 'fields', 'kind')));
      const nm = h('input'); nm.type = 'text'; nm.placeholder = 'dataset name'; f.appendChild(field('Name', nm));
      const rights = h('input'); rights.type = 'text'; rights.value = 'unknown'; f.appendChild(field('Rights', rights, 'unknown rights allow local use and deny redistribution'));
      ins.appendChild(f);
      const acts = h('div', 'actions'); const b = h('button', 'btn primary', 'Import'); b.type = 'button'; acts.appendChild(b); const c = h('button', 'btn ghost', 'Close'); c.type = 'button'; c.addEventListener('click', () => act.select(null)); acts.appendChild(c); ins.appendChild(acts);
      ins.appendChild(h('p', 'note', 'Bytes are hashed on import; the dataset keeps the hash and the source path.'));
    } else if (kind === 'generate') {
      hd.appendChild(h('span', 'kicker', 'data')); hd.appendChild(h('h2', null, 'Generate')); ins.appendChild(hd);
      const gens = LAB.generators || []; const gsel = h('select'); for (const g of gens) { const o = h('option', null, g.label); o.value = g.id; o.selected = g.id === (n.generator || (gens[0] && gens[0].id)); gsel.appendChild(o); } gsel.addEventListener('change', () => act.setDataAction('generator', gsel.value)); const g = gens.find(x => x.id === (n.generator || (gens[0] && gens[0].id))); f.appendChild(field('Generator', gsel, g ? g.command : ''));
      if (g) for (const prm of g.params) { const i = h('input'); i.type = prm.type || 'text'; i.value = n['p_' + prm.id] != null ? n['p_' + prm.id] : prm.value; i.addEventListener('change', () => act.setDataAction('p_' + prm.id, i.value)); f.appendChild(field(prm.label, i, prm.hint || '')); }
      const out = h('input'); out.type = 'text'; out.value = n.out || (g ? g.out : ''); f.appendChild(field('Output dataset', out));
      ins.appendChild(f);
      const acts = h('div', 'actions'); const b = h('button', 'btn primary', 'Generate'); b.type = 'button'; acts.appendChild(b); const c = h('button', 'btn ghost', 'Close'); c.type = 'button'; c.addEventListener('click', () => act.select(null)); acts.appendChild(c); ins.appendChild(acts);
      ins.appendChild(h('p', 'note', 'Runs as an ordinary recipe. The result appears here as a dataset with its receipt.'));
    } else {
      hd.appendChild(h('span', 'kicker', 'data')); hd.appendChild(h('h2', null, 'Release')); ins.appendChild(hd);
      const dsel = h('select'); for (const r of LAB.project.data) { if (r.state === 'missing') continue; const o = h('option', null, r.label); o.value = r.id; o.selected = r.id === n.dataset; dsel.appendChild(o); } dsel.addEventListener('change', () => act.setDataAction('dataset', dsel.value)); f.appendChild(field('Dataset', dsel));
      const nm = h('input'); nm.type = 'text'; nm.placeholder = 'release name'; nm.value = n.releaseName || ''; f.appendChild(field('Name', nm));
      const three = h('div', 'two'); three.style.gridTemplateColumns = '1fr 1fr 1fr'; for (const [k, v] of [['Train %', 70], ['Validation %', 15], ['Test %', 15]]) { const i = h('input'); i.type = 'number'; i.min = 0; i.max = 100; i.value = v; three.appendChild(field(k, i)); } f.appendChild(three);
      f.appendChild(field('Selection', radio('selr', [['all', 'All records'], ['saved', 'Saved selection']], n.selr || 'all', 'selr')));
      ins.appendChild(f);
      const acts = h('div', 'actions'); const b = h('button', 'btn primary', 'Freeze release'); b.type = 'button'; acts.appendChild(b); const c = h('button', 'btn ghost', 'Close'); c.type = 'button'; c.addEventListener('click', () => act.select(null)); acts.appendChild(c); ins.appendChild(acts);
      ins.appendChild(h('p', 'note', 'A release freezes exact revisions. Training reads releases, never live records.'));
    }
    aside.appendChild(ins);
  }

  // ---- Annotate: records, viewer, labels, review, history --------------------
  function annotate(main, aside, state, act) {
    main.textContent = ''; aside.textContent = '';
    const A = LAB.annotation || { tasks: [] }, ui = state.ui || {}, ann = state.annotations || {};
    const sets = LAB.project.data.filter(r => r.state !== 'missing');
    const dsId = ui['ann:ds'] || A.defaultDataset || (sets[0] && sets[0].id), r = sets.find(x => x.id === dsId) || sets[0];
    const task = A.tasks.find(t => t.id === (ui['ann:task'] || (A.tasks[0] && A.tasks[0].id))) || A.tasks[0];
    const per = 48, page = ui['ann:page'] || 0, rec = ui['ann:rec'] != null ? ui['ann:rec'] : 0, filter = ui['ann:filter'] || 'all';
    const store = ann[r.id] || {}; const seedOf = i => { const sd = (A.seed || {})[r.id]; return sd && i < sd.reviewed ? { label: sd.labels[i], review: sd.labels[i] === 'needs work' ? 'needs' : 'accepted', revisions: [{ at: 'imported', label: sd.labels[i], review: 'accepted' }] } : null; };
    const recOf = i => store[i] || seedOf(i) || null;
    const reviewed = Array.from({ length: r.records }, (_, i) => recOf(i)).filter(Boolean).length;
    const bar = h('div', 'ann-bar');
    const dl = h('label'); dl.appendChild(document.createTextNode('Dataset')); const dsel = h('select'); for (const x of sets) { const o = h('option', null, x.label); o.value = x.id; o.selected = x.id === r.id; dsel.appendChild(o); } dsel.addEventListener('change', () => { act.setUI('ann:rec', 0); act.setUI('ann:page', 0); act.setUI('ann:ds', dsel.value); }); dl.appendChild(dsel); bar.appendChild(dl);
    const tl = h('label'); tl.appendChild(document.createTextNode('Task')); const tsel = h('select'); for (const t of A.tasks) { const o = h('option', null, t.label); o.value = t.id; o.selected = t.id === task.id; tsel.appendChild(o); } tsel.addEventListener('change', () => act.setUI('ann:task', tsel.value)); tl.appendChild(tsel); bar.appendChild(tl);
    const seg = h('div', 'seg'); for (const [v, t] of [['all', 'All'], ['unreviewed', 'Unreviewed'], ['accepted', 'Accepted'], ['needs', 'Needs work']]) { const b = h('button', null, t); b.type = 'button'; b.setAttribute('aria-pressed', String(filter === v)); b.addEventListener('click', () => { act.setUI('ann:page', 0); act.setUI('ann:filter', v); }); seg.appendChild(b); } bar.appendChild(seg);
    const pr = h('span', 'progress'); const pi = h('i'); const pb = h('b'); pb.style.width = Math.round(100 * reviewed / r.records) + '%'; pi.appendChild(pb); pr.appendChild(pi); pr.appendChild(document.createTextNode(`${reviewed} of ${r.records} reviewed`)); bar.appendChild(pr);
    const kb = h('span', 'small faint'); kb.appendChild(h('span', 'kbd', '←')); kb.appendChild(document.createTextNode(' ')); kb.appendChild(h('span', 'kbd', '→')); kb.appendChild(document.createTextNode(' move · ')); kb.appendChild(h('span', 'kbd', '1')); kb.appendChild(document.createTextNode('–')); kb.appendChild(h('span', 'kbd', String((task.classes || task.options || []).length))); kb.appendChild(document.createTextNode(' label · ')); kb.appendChild(h('span', 'kbd', 'Enter')); kb.appendChild(document.createTextNode(' save and next')); bar.appendChild(kb);
    main.appendChild(bar);
    const all = Array.from({ length: r.records }, (_, i) => i).filter(i => { const a = recOf(i); return filter === 'all' ? true : filter === 'unreviewed' ? !a : filter === 'accepted' ? a && a.review === 'accepted' : a && a.review === 'needs'; });
    const body = h('div', 'ann-body');
    const left = h('div'); left.appendChild(sect(r.recordKind.charAt(0).toUpperCase() + r.recordKind.slice(1) + 's', all.length ? `${page * per + 1}–${Math.min(all.length, (page + 1) * per)} of ${all.length}` : '0'));
    const grid = h('div', 'rec-grid');
    for (const i of all.slice(page * per, (page + 1) * per)) {
      const b = h('button', 'rec'); b.type = 'button'; b.setAttribute('aria-pressed', String(i === rec)); const a = recOf(i); b.setAttribute('aria-label', r.recordKind + ' ' + (i + 1) + (a ? ', ' + (a.label || '') + ' ' + a.review : ', unreviewed'));
      const cv = h('canvas'); drawSlice2(cv, volumeFn(i + 1, r.fields[0]), !/velocity|tracer/.test(r.fields[0]), 16, 64, 0.5); b.appendChild(cv); b.appendChild(h('span', null, String(i + 1)));
      if (a) b.appendChild(h('i', 'badge ' + (a.review || 'labelled')));
      b.addEventListener('click', () => act.setUI('ann:rec', i)); grid.appendChild(b);
    }
    left.appendChild(grid);
    if (all.length > per) { const pg = h('div', 'pager'); const pb2 = h('button', 'btn sm', 'Previous'); pb2.type = 'button'; pb2.disabled = page === 0; pb2.addEventListener('click', () => act.setUI('ann:page', page - 1)); const nb = h('button', 'btn sm', 'Next'); nb.type = 'button'; nb.disabled = (page + 1) * per >= all.length; nb.addEventListener('click', () => act.setUI('ann:page', page + 1)); pg.appendChild(pb2); pg.appendChild(nb); pg.appendChild(h('span', null, `page ${page + 1} of ${Math.ceil(all.length / per)}`)); left.appendChild(pg); }
    body.appendChild(left);
    const vw = h('div', 'viewer'); const fn = volumeFn(rec + 1, r.fields[0]), signed = !/velocity|tracer/.test(r.fields[0]);
    let w = ui['ann:w'] != null ? ui['ann:w'] : 0.5;
    const vol = h('canvas', 'vol'); vol.setAttribute('role', 'img'); vol.setAttribute('aria-label', `${r.fields[0]} volume of ${r.recordKind} ${rec + 1}`); drawVolume(vol, fn, signed, r.grid, w); vw.appendChild(vol);
    const row2 = h('div', 'row2'); const sl = h('canvas', 'sl'); sl.setAttribute('role', 'img'); sl.setAttribute('aria-label', 'Slice'); drawSlice2(sl, fn, signed, 32, 240, w); row2.appendChild(sl);
    const facts = h('dl', 'facts'); const sliceDd = h('dd', null, 'z = ' + Math.round(w * (r.grid[2] - 1) + 1) + ' of ' + r.grid[2]);
    for (const [k, v] of [[r.recordKind.charAt(0).toUpperCase() + r.recordKind.slice(1), String(rec + 1) + ' of ' + r.records], ['Grid', r.grid.join(' × ')], ['Fields', r.fields.join(', ')]]) { facts.appendChild(h('dt', null, k)); facts.appendChild(h('dd', null, v)); } facts.appendChild(h('dt', null, 'Slice')); facts.appendChild(sliceDd);
    row2.appendChild(facts); vw.appendChild(row2);
    const ctl = h('div', 'ctl'); const zl = h('label'); zl.appendChild(document.createTextNode('Slice')); const zi = h('input'); zi.type = 'range'; zi.min = 0; zi.max = r.grid[2] - 1; zi.value = Math.round(w * (r.grid[2] - 1));
    zi.addEventListener('input', () => { w = +zi.value / Math.max(1, r.grid[2] - 1); drawVolume(vol, fn, signed, r.grid, w); drawSlice2(sl, fn, signed, 32, 240, w); sliceDd.textContent = 'z = ' + (+zi.value + 1) + ' of ' + r.grid[2]; });
    zi.addEventListener('change', () => { state.ui['ann:w'] = w; }); zl.appendChild(zi); ctl.appendChild(zl);
    const prev = h('button', 'btn sm', 'Previous'); prev.type = 'button'; prev.disabled = rec === 0; prev.addEventListener('click', () => act.setUI('ann:rec', rec - 1)); const next = h('button', 'btn sm', 'Next'); next.type = 'button'; next.disabled = rec >= r.records - 1; next.addEventListener('click', () => act.setUI('ann:rec', rec + 1)); ctl.appendChild(prev); ctl.appendChild(next);
    vw.appendChild(ctl); body.appendChild(vw); main.appendChild(body);
    // Form for the current record.
    const cur = recOf(rec) || {}, draft = Object.assign({ label: cur.label || null, tags: cur.tags || [], review: cur.review || null, notes: cur.notes || '' }, state.draft && state.draft.key === r.id + ':' + rec ? state.draft.v : {});
    const ins = h('div', 'inspector');
    const hd = h('header'); hd.appendChild(h('span', 'kicker', r.label)); hd.appendChild(h('h2', null, r.recordKind.charAt(0).toUpperCase() + r.recordKind.slice(1) + ' ' + (rec + 1))); const meta = h('div', 'ins-meta'); meta.appendChild(cur.review ? stateEl(cur.review === 'accepted' ? 'good' : cur.review === 'needs' ? 'warn' : 'serious', cur.review === 'needs' ? 'needs work' : cur.review) : stateEl('neutral', 'unreviewed')); hd.appendChild(meta); ins.appendChild(hd);
    const f = h('div', 'form');
    const field = (label, control) => { const l = h('div'); l.appendChild(h('h3', null, label)); l.appendChild(control); return l; };
    const setDraft = (k, v) => { state.draft = { key: r.id + ':' + rec, v: Object.assign({}, draft, { [k]: v }) }; act.setUI('ann:tick', (ui['ann:tick'] || 0) + 1); };
    if (task.type === 'class') { const rd = h('div', 'radio'); task.classes.forEach((c, i) => { const l = h('label'); const inp = h('input'); inp.type = 'radio'; inp.name = 'lbl'; inp.checked = draft.label === c; inp.addEventListener('change', () => setDraft('label', c)); l.appendChild(inp); l.appendChild(document.createTextNode(c)); l.appendChild(h('span', 'kbd', String(i + 1))); rd.appendChild(l); }); f.appendChild(field(task.label, rd)); }
    else { const rd = h('div', 'radio'); task.options.forEach((c, i) => { const l = h('label'); const inp = h('input'); inp.type = 'checkbox'; inp.checked = draft.tags.includes(c); inp.addEventListener('change', () => setDraft('tags', inp.checked ? draft.tags.concat([c]) : draft.tags.filter(x => x !== c))); l.appendChild(inp); l.appendChild(document.createTextNode(c)); l.appendChild(h('span', 'kbd', String(i + 1))); rd.appendChild(l); }); f.appendChild(field(task.label, rd)); }
    const rv = h('div', 'seg'); for (const [v, t, c] of [['accepted', 'Accept', 'ok'], ['needs', 'Needs work', 'warn'], ['reject', 'Reject', 'bad']]) { const b = h('button', c, t); b.type = 'button'; b.setAttribute('aria-pressed', String(draft.review === v)); b.addEventListener('click', () => setDraft('review', v)); rv.appendChild(b); } f.appendChild(field('Review', rv));
    const notes = h('textarea'); notes.rows = 2; notes.value = draft.notes; notes.placeholder = 'notes'; notes.addEventListener('change', () => setDraft('notes', notes.value)); f.appendChild(field('Notes', notes));
    ins.appendChild(f);
    const acts = h('div', 'actions'); const save = h('button', 'btn primary', 'Save and next'); save.type = 'button'; save.disabled = !draft.review && !draft.label && !draft.tags.length; save.addEventListener('click', () => act.saveAnnotation(r.id, rec, draft)); acts.appendChild(save); const skip = h('button', 'btn ghost', 'Skip'); skip.type = 'button'; skip.addEventListener('click', () => act.setUI('ann:rec', Math.min(r.records - 1, rec + 1))); acts.appendChild(skip); ins.appendChild(acts);
    const hist = cur.revisions || []; if (hist.length) { const d = h('div'); d.appendChild(h('h3', null, 'History')); const ul = h('ul', 'hist'); for (const rv2 of hist.slice().reverse()) { const li = h('li'); li.appendChild(h('b', null, rv2.at)); li.appendChild(document.createTextNode((rv2.label || (rv2.tags || []).join(', ') || '—') + ' · ' + (rv2.review === 'needs' ? 'needs work' : rv2.review || ''))); ul.appendChild(li); } d.appendChild(ul); ins.appendChild(d); }
    aside.appendChild(ins);
    main.tabIndex = -1;
    main.onkeydown = ev => { if (ev.target.tagName === 'TEXTAREA' || ev.target.tagName === 'INPUT' || ev.target.tagName === 'SELECT') return; if (ev.key === 'ArrowRight') { act.setUI('ann:rec', Math.min(r.records - 1, rec + 1)); ev.preventDefault(); } else if (ev.key === 'ArrowLeft') { act.setUI('ann:rec', Math.max(0, rec - 1)); ev.preventDefault(); } else if (/^[1-9]$/.test(ev.key)) { const opts = task.classes || task.options; const c = opts[+ev.key - 1]; if (c) { if (task.type === 'class') setDraft('label', c); else setDraft('tags', draft.tags.includes(c) ? draft.tags.filter(x => x !== c) : draft.tags.concat([c])); } } else if (ev.key === 'Enter' && !save.disabled) act.saveAnnotation(r.id, rec, draft); };
    return true;
  }

  // ---- Models --------------------------------------------------------------
  function models(main, aside, state, act, opts = {}) {
    aside.textContent = '';
    const sel = state.sel.models;
    const buildBar = () => {
      const bar = h('div', 'filters');
      const q = h('input'); q.type = 'search'; q.placeholder = 'Find a fit'; q.value = state.query || ''; q.setAttribute('aria-label', 'Find a fit'); q.addEventListener('input', () => act.setQuery(q.value)); bar.appendChild(q);
      const grp = h('div', 'grp'); grp.setAttribute('role', 'group'); grp.setAttribute('aria-label', 'Kind of change');
      for (const k of KINDS) { const b = h('button', 'btn sm chip ' + k, Tree.kindLabel(k)); b.type = 'button'; b.setAttribute('aria-pressed', String(!state.kinds || state.kinds.has(k))); b.addEventListener('click', () => act.toggleKind(k)); grp.appendChild(b); }
      bar.appendChild(grp);
      const showMap = opts.stacked || state.view === 'map';
      if (!opts.stacked && opts.views && opts.views.length > 1) { const vg = h('div', 'grp'); vg.setAttribute('role', 'group'); vg.setAttribute('aria-label', 'View'); for (const v of opts.views) { const b = h('button', 'btn sm', v === 'list' ? 'List' : 'Map'); b.type = 'button'; b.setAttribute('aria-pressed', String(state.view === v)); b.addEventListener('click', () => act.setView(v)); vg.appendChild(b); } bar.appendChild(vg); }
      if (showMap) {
        const tb = h('button', 'btn sm', 'Accuracy track'); tb.type = 'button'; tb.setAttribute('aria-pressed', String(!!state.track)); tb.addEventListener('click', () => act.toggleTrack()); bar.appendChild(tb);
        const z = h('div', 'zoomctl'); for (const [t, d, l] of [['−', -0.2, 'Zoom out'], ['+', 0.2, 'Zoom in']]) { const b = h('button', 'btn sm', t); b.type = 'button'; b.setAttribute('aria-label', l); b.addEventListener('click', () => act.zoom(d)); z.appendChild(b); } bar.appendChild(z);
      }
      if (sel && byId.get(sel) && !byId.get(sel).planned) { const bb = h('button', 'btn sm primary'); bb.type = 'button'; bb.appendChild(icon('branch')); bb.appendChild(document.createTextNode(' Branch from ' + (byId.get(sel).ck || byId.get(sel).short))); bb.addEventListener('click', () => act.branch(sel)); bar.appendChild(bb); }
      bar.appendChild(h('span', 'pop', `${LAB.models.length} fits · ${withBench} benchmarked`));
      return bar;
    };
    const sig = JSON.stringify([state.kinds ? [...state.kinds] : null, state.query || '', state.zoom || 1, !!state.track, !!opts.stacked, state.view, plannedVersion]);
    const prev = main._tree;
    const common = { onSelect: id => act.select(id), kinds: state.kinds, query: state.query, barLabel: accLabel(ACC[0].id), unit: TIME.unit, trackLabel: accLabel(ACC[0].id) + ', lower is better', metric: ACC[0].id, timeId: TIME.id };
    if (prev && prev.sig === sig && main.contains(prev.bar)) {
      const bar = buildBar(); prev.bar.replaceWith(bar); prev.bar = bar;
      if (prev.map) prev.map.select(sel); if (prev.list) prev.list.select(sel);
      if (sel && sel !== prev.sel) { if (prev.map) prev.map.scrollTo(sel, true); if (prev.list) prev.list.scrollTo(sel, true); }
      prev.sel = sel;
    } else {
      main.textContent = ''; const bar = buildBar(); main.appendChild(bar);
      const inst = { sig, bar, sel, map: null, list: null };
      const mapOpts = Object.assign({ selected: sel, zoom: state.zoom || 1, track: !!state.track }, common);
      if (opts.stacked) { const mh = h('div', 'tree-map'); main.appendChild(mh); inst.map = Tree.renderMap(mh, graph, mapOpts); const lh = h('div', 'tree-host'); main.appendChild(lh); inst.list = Tree.renderList(lh, graph, Object.assign({ selected: sel }, common)); }
      else { const host = h('div', state.view === 'map' ? 'tree-map' : 'tree-host'); main.appendChild(host); if (state.view === 'map') inst.map = Tree.renderMap(host, graph, mapOpts); else inst.list = Tree.renderList(host, graph, Object.assign({ selected: sel }, common)); }
      if (sel) { if (inst.map) inst.map.scrollTo(sel, false); if (inst.list) inst.list.scrollTo(sel, false); }
      main._tree = inst;
    }
    if (sel && byId.get(sel)) { if (byId.get(sel).planned) inspectorPlanned(aside, sel, state, act); else inspectorModel(aside, sel, act); return true; }
    modelsGuide(aside, act); return false;
  }
  function modelsGuide(aside, act) {
    const ins = h('div', 'inspector');
    const key = h('ul', 'keylist');
    for (const [cls, t] of [['k-solid', 'Derived from an earlier fit'], ['k-faint', 'Checkpoint order'], ['k-dash', 'Compared with (selected fit)'], ['k-bar', accLabel(ACC[0].id) + ', log scale, longer is better']]) { const li = h('li', cls); li.appendChild(h('i')); li.appendChild(h('span', null, t)); key.appendChild(li); }
    ins.appendChild(key);
    const d = h('div'); d.appendChild(h('h3', null, 'Branch points'));
    const ul = h('ul', 'links');
    for (const f of graph.families) { const p = byId.get(f.parent); const first = byId.get(f.children[0]), last = byId.get(f.children[f.children.length - 1]); const li = h('li'); const b = h('button'); b.type = 'button'; b.appendChild(document.createTextNode(`${p.ck || p.short} · ${f.children.length} fits`)); b.appendChild(h('span', 'why', `${first.ck || first.short} to ${last.ck || last.short} · ${Tree.kindLabel(first.kind).toLowerCase()}`)); b.addEventListener('click', () => act.select(p.id)); li.appendChild(b); ul.appendChild(li); }
    d.appendChild(ul); ins.appendChild(d);
    const k = h('div'); k.appendChild(h('h3', null, 'Kinds of change'));
    const dl = h('dl', 'metrics');
    for (const kind of KINDS) { const c = h('div'); c.appendChild(h('dt', 'chip ' + kind, Tree.kindLabel(kind))); c.appendChild(h('dd', null, String(LAB.models.filter(m => m.kind === kind).length))); dl.appendChild(c); }
    k.appendChild(dl); ins.appendChild(k);
    aside.appendChild(ins);
  }
  // A planned model: configured on its node, trained from Train.
  function inspectorPlanned(aside, id, state, act) {
    aside.textContent = '';
    const m = byId.get(id), p = byId.get(m.parent), n = m.setup || {};
    const ins = h('div', 'inspector');
    const hd = h('header'); hd.appendChild(h('span', 'kicker', 'planned · from ' + (p.ck || p.short))); hd.appendChild(h('h2', null, m.label));
    const meta = h('div', 'ins-meta'); meta.appendChild(stateEl(n.prepared ? 'good' : 'pending', n.prepared ? 'trial prepared' : 'not prepared')); hd.appendChild(meta); ins.appendChild(hd);
    const lin = h('div', 'actions'); const pb = h('button', 'btn sm ghost'); pb.type = 'button'; pb.appendChild(icon('branch')); pb.appendChild(document.createTextNode(' From ' + (p.ck || p.short) + (p.worstP ? ' · ' + Tree.fmtSci(p.worstP) : ''))); pb.addEventListener('click', () => act.select(p.id)); lin.appendChild(pb); ins.appendChild(lin);
    const f = h('div', 'form');
    const field = (label, control, hint) => { const l = h('label'); l.appendChild(document.createTextNode(label)); l.appendChild(control); if (hint) l.appendChild(h('span', 'hint', hint)); return l; };
    const nm = h('input'); nm.type = 'text'; nm.value = n.name || ''; nm.placeholder = 'name'; nm.addEventListener('change', () => act.setPlan(id, 'name', nm.value)); f.appendChild(field('Name', nm));
    const kr = h('div', 'radio'); for (const k of KINDS.slice(0, 3)) { const l = h('label'); const r = h('input'); r.type = 'radio'; r.name = 'kind-' + id; r.checked = (n.kind || 'refinement') === k; r.addEventListener('change', () => act.setPlan(id, 'kind', k)); l.appendChild(r); l.appendChild(document.createTextNode(Tree.kindLabel(k))); kr.appendChild(l); } f.appendChild(field('Kind of change', kr));
    const selRecipe = h('select'); for (const r of LAB.recipes || []) { if (r.kind === 'evaluation') continue; const o = h('option', null, r.label); o.value = r.id; o.selected = r.id === (n.recipe || 'run-study'); selRecipe.appendChild(o); } selRecipe.addEventListener('change', () => act.setPlan(id, 'recipe', selRecipe.value)); const rc = recipeOf(n.recipe || 'run-study'); f.appendChild(field('Recipe', selRecipe, rc ? rc.path + (rc.config ? ' · ' + rc.config : '') : ''));
    const selData = h('select'); for (const r of LAB.project.data) { if (r.state === 'missing') continue; const o = h('option', null, r.label); o.value = r.id; o.selected = r.id === (n.data || 'water-capture'); selData.appendChild(o); } selData.addEventListener('change', () => act.setPlan(id, 'data', selData.value)); f.appendChild(field('Data', selData));
    const rr = h('div', 'radio'); for (const r of LAB.runtimes || []) { const l = h('label'); const i = h('input'); i.type = 'radio'; i.name = 'rt-' + id; i.checked = (n.runtime || (rc && rc.runtime)) === r.id; i.addEventListener('change', () => act.setPlan(id, 'runtime', r.id)); l.appendChild(i); l.appendChild(document.createTextNode(r.label)); rr.appendChild(l); } f.appendChild(field('Runtime', rr));
    const two = h('div', 'two'); const upd = h('input'); upd.type = 'number'; upd.min = 1; upd.value = n.updates || p.updates || 1600; upd.addEventListener('change', () => act.setPlan(id, 'updates', +upd.value)); two.appendChild(field('Updates', upd)); const lr = h('input'); lr.type = 'text'; lr.value = n.lr || p.lr || '1e-5'; lr.addEventListener('change', () => act.setPlan(id, 'lr', lr.value)); two.appendChild(field('Learning rate', lr)); f.appendChild(two);
    const two2 = h('div', 'two'); const att = h('input'); att.type = 'number'; att.min = 1; att.value = n.attempts || 2; att.addEventListener('change', () => act.setPlan(id, 'attempts', +att.value)); two2.appendChild(field('Attempts', att)); const wall = h('input'); wall.type = 'number'; wall.min = 1; wall.value = n.wall || 90; wall.addEventListener('change', () => act.setPlan(id, 'wall', +wall.value)); two2.appendChild(field('Wall minutes', wall)); f.appendChild(two2);
    const two3 = h('div', 'two'); const tm = h('select'); for (const a of ACC) { const o = h('option', null, a.label); o.value = a.id; o.selected = (n.target || ACC[0].id) === a.id; tm.appendChild(o); } tm.addEventListener('change', () => act.setPlan(id, 'target', tm.value)); two3.appendChild(field('Target', tm)); const th = h('input'); th.type = 'text'; th.value = n.threshold || ''; th.placeholder = p.worstP ? 'below ' + Tree.fmtSci(p.worstP) : ''; th.addEventListener('change', () => act.setPlan(id, 'threshold', th.value)); two3.appendChild(field('Threshold', th)); f.appendChild(two3);
    const ch = h('textarea'); ch.rows = 2; ch.value = n.change || ''; ch.placeholder = 'What this model changes'; ch.addEventListener('change', () => act.setPlan(id, 'change', ch.value)); f.appendChild(field('Intended change', ch));
    ins.appendChild(f);
    const steps = h('ol', 'steps');
    for (const [t, done] of [['Prepared', !!n.prepared], ['Reviewed', false], ['Approved', false], ['Started', false]]) { const li = h('li', done ? 'done' : 'todo'); li.appendChild(stateEl(done ? 'good' : 'neutral', '')); li.appendChild(h('span', 'title', t)); steps.appendChild(li); }
    ins.appendChild(steps);
    const acts = h('div', 'actions');
    if (!n.prepared) { const b = h('button', 'btn primary', 'Prepare trial'); b.type = 'button'; b.addEventListener('click', () => act.setPlan(id, 'prepared', true)); acts.appendChild(b); }
    else { const b = h('button', 'btn primary', 'Open in Train'); b.type = 'button'; b.addEventListener('click', () => act.go('train', id)); acts.appendChild(b); }
    const d = h('button', 'btn ghost', 'Discard'); d.type = 'button'; d.addEventListener('click', () => act.discardPlan(id)); acts.appendChild(d);
    ins.appendChild(acts);
    aside.appendChild(ins);
  }

  function inspectorModel(aside, id, act, { compact = false } = {}) {
    aside.textContent = '';
    const m = byId.get(id); if (!m) return;
    const ins = h('div', 'inspector');
    const hd = h('header'); hd.appendChild(h('span', 'kicker', (m.ck ? m.ck + ' · ' : '') + m.groupLabel)); hd.appendChild(h('h2', null, m.short));
    const meta = h('div', 'ins-meta'); meta.appendChild(h('span', 'chip ' + m.kind, Tree.kindLabel(m.kind))); meta.appendChild(stateEl('good', 'source reviewed'));
    if (m.alias && m.alias !== m.ck) meta.appendChild(h('span', 'small faint', m.alias)); hd.appendChild(meta); ins.appendChild(hd);
    const lin = h('div', 'actions');
    if (m.parent) { const p = byId.get(m.parent); const b = h('button', 'btn sm ghost'); b.type = 'button'; b.appendChild(icon('branch')); b.appendChild(document.createTextNode(' From ' + (p.ck || p.short))); b.addEventListener('click', () => act.select(p.id)); lin.appendChild(b); }
    else lin.appendChild(h('span', 'small faint', 'No recorded ancestry'));
    const kids = graph.families.find(f => f.parent === m.id); if (kids) { const b = h('button', 'btn sm ghost', `${kids.children.length} fits branch here`); b.type = 'button'; b.addEventListener('click', () => act.select(kids.children[0])); lin.appendChild(b); }
    ins.appendChild(lin);
    const dl = h('dl', 'metrics');
    for (const a of ACC) dl.appendChild(cell(a.label, m[a.id] == null ? '—' : Tree.fmtSci(m[a.id])));
    dl.appendChild(cell(TIME.label, m[TIME.id] == null ? '—' : m[TIME.id].toFixed(2), m[TIME.id] == null ? '' : TIME.unit));
    dl.appendChild(cell('Parameters', m.params == null ? '—' : m.params.toLocaleString('en-GB')));
    ins.appendChild(dl);
    ins.appendChild(h('p', 'note', MET.population));
    if (!compact) for (const [k, v] of [['Purpose', m.purpose], ['Outcome', m.outcome], ['Lesson', m.lesson]]) { if (!v) continue; const d = h('div'); d.appendChild(h('h3', null, k)); d.appendChild(h('p', null, v + (v.length >= 200 ? '…' : ''))); ins.appendChild(d); }
    const cmp = Tree.comparisons(graph, m.id);
    if (cmp.length) { const d = h('div'); d.appendChild(h('h3', null, 'Compared with')); const ul = h('ul', 'links'); for (const c of cmp) { const o = byId.get(c.other); const li = h('li'); const b = h('button'); b.type = 'button'; b.appendChild(document.createTextNode((o.ck ? o.ck + ' · ' : '') + o.short)); if (!compact) b.appendChild(h('span', 'why', c.excerpt.slice(0, 140) + (c.excerpt.length > 140 ? '…' : ''))); b.addEventListener('click', () => act.select(o.id)); li.appendChild(b); ul.appendChild(li); } d.appendChild(ul); ins.appendChild(d); }
    const ac = h('div', 'actions');
    const b1 = h('button', 'btn primary'); b1.type = 'button'; b1.appendChild(icon('branch')); b1.appendChild(document.createTextNode(' Branch from here')); b1.addEventListener('click', () => act.branch(m.id)); ac.appendChild(b1);
    const b2 = h('button', 'btn', 'Benchmark'); b2.type = 'button'; b2.addEventListener('click', () => act.go('benchmarks', m.id)); ac.appendChild(b2);
    const b3 = h('button', 'btn ghost', 'Card'); b3.type = 'button'; ac.appendChild(b3);
    ins.appendChild(ac);
    aside.appendChild(ins);
  }

  // ---- Train: planned models, every training run, then the budgeted studies --
  function train(main, aside, state, act) {
    main.textContent = ''; aside.textContent = '';
    const sel = state.sel.train, studies = LAB.project.studies, planned = (state.planned || []);
    if (planned.length) {
      main.appendChild(sect('Planned', String(planned.length)));
      const pl = h('ul', 'rows');
      for (const pn of planned) { const m = byId.get(pn.id), p = byId.get(pn.parent); if (!m) continue; const li = h('li'); const b = h('button', 'row study'); b.type = 'button'; b.setAttribute('aria-pressed', String(pn.id === sel)); b.appendChild(stateEl(pn.setup.started ? 'pending' : pn.setup.prepared ? 'pending' : 'neutral', pn.setup.started ? 'running' : pn.setup.prepared ? 'prepared' : 'planned')); const t = h('span'); t.appendChild(h('span', 'title', m.label)); t.appendChild(h('span', 'sub', pn.setup.change || 'not configured')); b.appendChild(t); b.appendChild(h('span', 'sub mono', p ? (p.ck || p.short) : '')); b.appendChild(h('span', 'sub num', 'attempts 0 of ' + (pn.setup.attempts || 2))); b.appendChild(h('span', 'sub num', 'today')); b.addEventListener('click', () => act.select(pn.id)); li.appendChild(b); pl.appendChild(li); }
      main.appendChild(pl);
    }
    const bar = h('div', 'filters'); if (planned.length) bar.style.marginTop = '20px';
    const q = h('input'); q.type = 'search'; q.placeholder = 'Find a run'; q.value = state.query || ''; q.setAttribute('aria-label', 'Find a run'); q.addEventListener('input', () => act.setQuery(q.value)); bar.appendChild(q);
    const grp = h('div', 'grp'); for (const k of KINDS) { const b = h('button', 'btn sm chip ' + k, Tree.kindLabel(k)); b.type = 'button'; b.setAttribute('aria-pressed', String(!state.kinds || state.kinds.has(k))); b.addEventListener('click', () => act.toggleKind(k)); grp.appendChild(b); } bar.appendChild(grp);
    if (!planned.length) { const hint = h('span', 'pop'); hint.appendChild(document.createTextNode('To train a new model, branch from a fit on the ')); const a = h('a', null, 'map'); a.href = '#models'; hint.appendChild(a); bar.appendChild(hint); }
    main.appendChild(bar);
    const runs = graph.nodes.filter(m => !m.planned && (!state.kinds || state.kinds.has(m.kind)) && (!state.query || Tree.matches(m, state.query)));
    main.appendChild(sect('Runs', `${runs.length} of ${LAB.models.length}`));
    const ul = h('ul', 'rows'); let lastGroup = null;
    for (const m of runs) {
      if (m.group !== lastGroup) { lastGroup = m.group; const gh = h('li'); const hh = h('div', 'tsect'); hh.style.gridTemplateColumns = '1fr auto'; hh.appendChild(h('h3', null, m.groupLabel)); gh.appendChild(hh); ul.appendChild(gh); }
      const st = runStudy(m), li = h('li'); const b = h('button', 'row run'); b.type = 'button'; b.setAttribute('aria-pressed', String(m.id === sel));
      b.appendChild(h('span', 'ck', m.ck || '—'));
      const t = h('span'); t.appendChild(h('span', 'title', m.short)); t.appendChild(h('span', 'sub', [m.updates && m.updates.toLocaleString('en-GB') + ' updates', m.lr && 'lr ' + m.lr, m.seed && 'seed ' + m.seed, st && st.label].filter(Boolean).join(' · ') || 'recorded in the card')); b.appendChild(t);
      b.appendChild(h('span', 'chip ' + m.kind, Tree.kindLabel(m.kind)));
      b.appendChild(h('span', 'sub num', m.loss == null ? '' : 'loss ' + Tree.fmtSci(m.loss)));
      b.appendChild(h('span', 'sub', m.device || ''));
      b.appendChild(stateEl('good', 'completed'));
      b.addEventListener('click', () => act.select(m.id)); li.appendChild(b); ul.appendChild(li);
    }
    main.appendChild(ul);
    const sh = sect('Studies', String(studies.length)); sh.style.marginTop = '28px'; main.appendChild(sh);
    const sul = h('ul', 'rows');
    for (const s of studies) {
      const li = h('li'); const b = h('button', 'row study'); b.type = 'button'; b.setAttribute('aria-pressed', String(s.id === sel));
      b.appendChild(stateEl(studyState(s), s.state === 'closed' ? 'waiting' : s.state));
      const t = h('span'); t.appendChild(h('span', 'title', s.label)); t.appendChild(h('span', 'sub', s.decision)); b.appendChild(t);
      const mm = s.model && byId.get(s.model); b.appendChild(h('span', 'sub mono', mm ? (mm.ck || mm.short) : ''));
      b.appendChild(h('span', 'sub num', 'attempts ' + s.attempts)); b.appendChild(h('span', 'sub num', fmtDate(s.updated)));
      b.addEventListener('click', () => act.select(s.id)); li.appendChild(b); sul.appendChild(li);
    }
    main.appendChild(sul);
    const pn = planned.find(x => x.id === sel);
    if (pn) return inspectorPlannedRun(aside, pn, act);
    const run = sel && byId.get(sel);
    if (run && !run.planned) return inspectorRun(aside, run, act);
    const s = studies.find(x => x.id === sel);
    if (!s) {
      const used = studies.reduce((a, x) => { const m = /^(\d+) of (\d+)/.exec(x.attempts); if (m) { a[0] += +m[1]; a[1] += +m[2]; } return a; }, [0, 0]);
      const ins = h('div', 'inspector'); const dl = h('dl', 'metrics');
      dl.appendChild(cell('Runs', String(LAB.models.length))); dl.appendChild(cell('On CUDA', String(LAB.models.filter(m => m.device === 'CUDA').length))); dl.appendChild(cell('Waiting', String(studies.filter(x => x.state === 'closed').length + planned.filter(x => x.setup.prepared && !x.setup.started).length))); dl.appendChild(cell('Live', String(planned.filter(x => x.setup.started).length)));
      ins.appendChild(dl);
      const rl = h('div'); rl.appendChild(h('h3', null, 'Recipes')); const rul = h('ul', 'links');
      for (const r of LAB.recipes || []) { const li = h('li'); const sp = h('button'); sp.type = 'button'; sp.appendChild(document.createTextNode(r.label)); sp.appendChild(h('span', 'why', r.path + ' · ' + (runtimeOf(r.runtime) || {}).label + ' · ' + r.kind)); li.appendChild(sp); rul.appendChild(li); }
      rl.appendChild(rul); ins.appendChild(rl);
      aside.appendChild(ins); return false;
    }
    return inspectorStudy(aside, s, act);
  }
  function inspectorRun(aside, m, act) {
    const ins = h('div', 'inspector'), st = runStudy(m), p = m.parent && byId.get(m.parent);
    const hd = h('header'); hd.appendChild(h('span', 'kicker', (m.ck ? m.ck + ' · ' : '') + m.groupLabel)); hd.appendChild(h('h2', null, m.short)); const meta = h('div', 'ins-meta'); meta.appendChild(h('span', 'chip ' + m.kind, Tree.kindLabel(m.kind))); meta.appendChild(stateEl('good', 'completed')); hd.appendChild(meta); ins.appendChild(hd);
    const su = h('dl', 'setup'); const put = (k, node) => { su.appendChild(h('dt', null, k)); const dd = h('dd'); if (typeof node === 'string') dd.textContent = node; else dd.appendChild(node); su.appendChild(dd); };
    if (p) { const b = h('button', 'btn sm ghost', 'From ' + (p.ck || p.short)); b.type = 'button'; b.addEventListener('click', () => act.go('models', p.id)); put('Start', b); } else put('Start', 'no recorded ancestry');
    put('Updates', m.updates ? m.updates.toLocaleString('en-GB') : '—'); put('Learning rate', m.lr ? String(m.lr) : '—'); put('Seed', m.seed ? String(m.seed) : '—');
    put('Device', m.device || '—'); put('Final loss', m.loss == null ? '—' : Tree.fmtSci(m.loss)); put('Parameters', m.params == null ? '—' : m.params.toLocaleString('en-GB'));
    if (st) { const b = h('button', 'btn sm ghost', st.label); b.type = 'button'; b.addEventListener('click', () => act.select(st.id)); put('Study', b); }
    ins.appendChild(su);
    if (m.experiment) { const d = h('div'); d.appendChild(h('h3', null, 'As recorded')); d.appendChild(h('p', null, m.experiment + (m.experiment.length >= 300 ? '…' : ''))); ins.appendChild(d); }
    const acts = h('div', 'actions'); const b1 = h('button', 'btn primary'); b1.type = 'button'; b1.appendChild(icon('branch')); b1.appendChild(document.createTextNode(' Branch from here')); b1.addEventListener('click', () => act.branch(m.id)); acts.appendChild(b1); const b2 = h('button', 'btn', 'On the map'); b2.type = 'button'; b2.addEventListener('click', () => act.go('models', m.id)); acts.appendChild(b2); const b3 = h('button', 'btn ghost', 'Benchmark'); b3.type = 'button'; b3.addEventListener('click', () => act.go('benchmarks', m.id)); acts.appendChild(b3); ins.appendChild(acts);
    aside.appendChild(ins); return true;
  }
  function inspectorPlannedRun(aside, pn, act) {
    const m = byId.get(pn.id), p = byId.get(pn.parent), n = pn.setup, rc = recipeOf(n.recipe || 'run-study'), rt = runtimeOf(n.runtime || (rc && rc.runtime)), ds = datasetOf(n.data || 'water-capture');
    const ins = h('div', 'inspector');
    const hd = h('header'); hd.appendChild(h('span', 'kicker', 'planned · from ' + (p.ck || p.short))); hd.appendChild(h('h2', null, m.label)); const meta = h('div', 'ins-meta'); meta.appendChild(stateEl(n.started ? 'pending' : n.prepared ? 'pending' : 'neutral', n.started ? 'running' : n.prepared ? 'prepared, waiting for review' : 'not prepared')); hd.appendChild(meta); ins.appendChild(hd);
    const su = h('dl', 'setup'); const put = (k, node) => { su.appendChild(h('dt', null, k)); const dd = h('dd'); if (typeof node === 'string') dd.textContent = node; else dd.appendChild(node); su.appendChild(dd); };
    const pb = h('button', 'btn sm ghost', modelName(p)); pb.type = 'button'; pb.addEventListener('click', () => act.go('models', p.id)); put('From', pb);
    if (rc) { const sp = h('span'); sp.appendChild(document.createTextNode(rc.label + ' · ')); sp.appendChild(fileLink(rc.path, rc.path)); put('Recipe', sp); }
    if (rt) put('Runtime', rt.label); if (ds) put('Data', ds.label);
    put('Training', `${(n.updates || p.updates || 1600).toLocaleString('en-GB')} updates · lr ${n.lr || p.lr || '1e-5'}`);
    put('Budget', `${n.attempts || 2} attempts · ${n.wall || 90} min wall`);
    if (n.change) put('Intended change', n.change);
    ins.appendChild(su);
    const steps = h('ol', 'steps'); for (const [t, done] of [['Prepared', !!n.prepared], ['Reviewed', !!n.reviewed], ['Approved', !!n.approved], ['Started', !!n.started]]) { const li = h('li', done ? 'done' : 'todo'); li.appendChild(stateEl(done ? 'good' : 'pending', '')); li.appendChild(h('span', 'title', t)); steps.appendChild(li); } ins.appendChild(steps);
    const acts = h('div', 'actions');
    if (!n.prepared) { const b = h('button', 'btn primary', 'Configure on the map'); b.type = 'button'; b.addEventListener('click', () => act.go('models', pn.id)); acts.appendChild(b); }
    else if (!n.reviewed) { const b = h('button', 'btn primary', 'Review material'); b.type = 'button'; b.addEventListener('click', () => act.setPlan(pn.id, 'reviewed', true)); acts.appendChild(b); }
    else if (!n.approved) { const b = h('button', 'btn primary', 'Approve'); b.type = 'button'; b.addEventListener('click', () => act.setPlan(pn.id, 'approved', true)); acts.appendChild(b); const b2 = h('button', 'btn', 'Start training'); b2.type = 'button'; b2.disabled = true; acts.appendChild(b2); }
    else if (!n.started) { const b = h('button', 'btn primary', 'Start training'); b.type = 'button'; b.addEventListener('click', () => act.setPlan(pn.id, 'started', true)); acts.appendChild(b); }
    else acts.appendChild(stateEl('good', 'running · attempt 1 of ' + (n.attempts || 2)));
    const d = h('button', 'btn ghost', 'Discard'); d.type = 'button'; d.addEventListener('click', () => act.discardPlan(pn.id)); acts.appendChild(d);
    ins.appendChild(acts); aside.appendChild(ins); return true;
  }
  function inspectorStudy(aside, s, act) {
    const ins = h('div', 'inspector');
    const hd = h('header'); hd.appendChild(h('span', 'kicker', 'study · ' + s.id)); hd.appendChild(h('h2', null, s.label)); const meta = h('div', 'ins-meta'); meta.appendChild(stateEl(studyState(s), s.state === 'closed' ? 'waiting for approval' : s.state + ' · ' + s.decision)); hd.appendChild(meta); ins.appendChild(hd);
    const mm = s.model && byId.get(s.model), rc = recipeOf(s.recipe), rt = runtimeOf(s.runtime), ds = datasetOf(s.data);
    const su = h('dl', 'setup'); const put = (k, node) => { su.appendChild(h('dt', null, k)); const dd = h('dd'); if (typeof node === 'string') dd.textContent = node; else dd.appendChild(node); su.appendChild(dd); };
    if (mm) { const b = h('button', 'btn sm ghost', modelName(mm)); b.type = 'button'; b.addEventListener('click', () => act.go('models', mm.id)); put('Baseline', b); }
    if (rc) { const sp = h('span'); sp.appendChild(document.createTextNode(rc.label + ' · ')); sp.appendChild(fileLink(rc.path, rc.path)); if (rc.config) { sp.appendChild(document.createTextNode(' · ')); sp.appendChild(fileLink(rc.config, rc.config)); } put('Recipe', sp); }
    if (rt) put('Runtime', rt.label);
    if (ds) { const b = h('button', 'btn sm ghost', ds.label); b.type = 'button'; b.addEventListener('click', () => act.go('data', ds.id)); put('Data', b); }
    put('Budget', `${s.attempts} attempts · ${s.wall || '—'} wall`);
    if (s.change) put('Intended change', s.change);
    ins.appendChild(su);
    const trials = (LAB.project.trials || {})[s.id] || Array.from({ length: s.trials }, (_, i) => ({ id: 't' + (i + 1), label: 'trial ' + (i + 1), state: s.state === 'completed' ? 'completed' : 'prepared' }));
    if (trials.length) { const d = h('div'); d.appendChild(h('h3', null, 'Runs in this study')); const tl = h('ul', 'trials'); for (const t of trials) { const li = h('li'); li.appendChild(stateEl(t.state === 'completed' ? 'good' : t.state === 'failed' ? 'serious' : 'pending', '')); li.appendChild(h('span', null, t.label + ' · ' + t.state)); const r = t.run && LAB.models.find(m => m.ck === t.run); if (r) { const b = h('button', 'btn sm ghost', r.ck); b.type = 'button'; b.addEventListener('click', () => act.select(r.id)); li.appendChild(b); } else li.appendChild(h('span')); tl.appendChild(li); } d.appendChild(tl); ins.appendChild(d); }
    const pending = s.state === 'closed';
    const steps = h('ol', 'steps'); for (const [t, done] of [['Prepared', true], ['Reviewed', true], ['Approved', !pending], ['Started', !pending]]) { const li = h('li', done ? 'done' : 'todo'); li.appendChild(stateEl(done ? 'good' : 'pending', '')); li.appendChild(h('span', 'title', t)); steps.appendChild(li); } ins.appendChild(steps);
    const acts = h('div', 'actions');
    if (pending) { const b = h('button', 'btn primary', 'Approve'); b.type = 'button'; acts.appendChild(b); const b2 = h('button', 'btn', 'Start training'); b2.type = 'button'; b2.disabled = true; b2.title = 'Approve first'; acts.appendChild(b2); }
    else if (mm) { const b = h('button', 'btn primary'); b.type = 'button'; b.appendChild(icon('branch')); b.appendChild(document.createTextNode(' Branch from ' + (mm.ck || mm.short))); b.addEventListener('click', () => act.branch(mm.id)); acts.appendChild(b); const b2 = h('button', 'btn ghost', 'Results'); b2.type = 'button'; b2.addEventListener('click', () => act.go('benchmarks', s.model)); acts.appendChild(b2); }
    ins.appendChild(acts);
    const docs = docsOf(s.label); if (docs.length) { const dd = h('div'); dd.appendChild(h('h3', null, 'Documents')); dd.appendChild(docChips(s.label, null, id => act.go('analysis', id))); ins.appendChild(dd); }
    aside.appendChild(ins); return true;
  }

  // ---- Benchmarks ----------------------------------------------------------
  function benchmarks(main, aside, state, act) {
    main.textContent = ''; aside.textContent = '';
    const sel = state.sel.benchmarks, metric = state.metric || ACC[0].id, pop = popOf(state), cmp = state.cmp || new Set();
    const popModels = LAB.models.filter(m => inPop(m, pop));
    const bar = h('div', 'filters');
    const ps = h('select'); ps.setAttribute('aria-label', 'Population'); for (const pp of MET.populations || []) { const o = h('option', null, pp.label); o.value = pp.id; o.selected = pp.id === pop.id; ps.appendChild(o); } ps.addEventListener('change', () => act.setPop(ps.value)); bar.appendChild(ps);
    const grp = h('div', 'grp'); grp.setAttribute('role', 'group'); grp.setAttribute('aria-label', 'Kind of change');
    for (const k of KINDS) { const b = h('button', 'btn sm chip ' + k, Tree.kindLabel(k)); b.type = 'button'; b.setAttribute('aria-pressed', String(!state.kinds || state.kinds.has(k))); b.addEventListener('click', () => act.toggleKind(k)); grp.appendChild(b); }
    bar.appendChild(grp);
    const ms = h('select'); ms.setAttribute('aria-label', 'Metric'); for (const a of ACC) { const o = h('option', null, a.label); o.value = a.id; o.selected = metric === a.id; ms.appendChild(o); } ms.addEventListener('change', () => act.setMetric(ms.value)); bar.appendChild(ms);
    const fb = h('button', 'btn sm', 'Frontier only'); fb.type = 'button'; fb.setAttribute('aria-pressed', String(!!state.frontierOnly)); fb.addEventListener('click', () => act.toggleFrontier()); bar.appendChild(fb);
    const bo = h('button', 'btn sm', 'Benchmarked only'); bo.type = 'button'; bo.setAttribute('aria-pressed', String(!!state.benchOnly)); bo.addEventListener('click', () => act.setUI('benchOnly', !state.ui.benchOnly)); bar.appendChild(bo);
    const q = h('input'); q.type = 'search'; q.placeholder = 'Find a fit'; q.value = state.query || ''; q.setAttribute('aria-label', 'Find a fit'); q.addEventListener('input', () => act.setQuery(q.value)); bar.appendChild(q);
    main.appendChild(bar);
    { const both = popModels.filter(m => benchState(m) === 'accuracy and time').length, ao = popModels.filter(m => benchState(m) === 'accuracy only').length, to = popModels.filter(m => benchState(m) === 'time only').length, none = popModels.filter(m => benchState(m) === 'none retained').length, gb = popModels.filter(m => benchState(m) === 'generator benchmark').length;
      const cov = h('div', 'coverage'); const add = (n, t) => { const sp = h('span'); sp.appendChild(h('b', null, String(n))); sp.appendChild(document.createTextNode(' ' + t)); cov.appendChild(sp); };
      add(popModels.length, 'fits'); if (gb) add(gb, 'with the generator benchmark'); if (both) add(both, 'with accuracy and time'); if (ao) add(ao, 'accuracy only'); if (to) add(to, 'time only'); if (none) add(none, 'no retained benchmark'); main.appendChild(cov); }

    const s1 = h('section'); const h1 = sect('Accuracy against time'); s1.appendChild(h1); const c1 = h('div'); s1.appendChild(c1); main.appendChild(s1);
    const xMax = Math.max(10, ...popModels.filter(m => m[TIME.id] != null).map(m => Math.ceil(m[TIME.id])));
    const r = Charts.pareto(c1, popModels, { selected: sel, onSelect: id => act.select(id), kinds: state.kinds, frontierOnly: state.frontierOnly, metric, yLabel: accLabel(metric), xLabel: TIME.axis, unit: TIME.unit, xMax: pop.only ? xMax : 10 });
    h1.appendChild(h('span', 'sum', `${r.count} of ${r.total} · ${r.frontier.length} on the frontier · ${pop.note || ''}`));
    if (!pop.only) { const s2 = h('section'); s2.style.marginTop = '28px'; s2.appendChild(sect('Along the checkpoint sequence', accLabel(ACC[0].id))); const c2 = h('div'); s2.appendChild(c2); main.appendChild(s2); Charts.curve(c2, LAB.models, { selected: sel, onSelect: id => act.select(id), metric: ACC[0].id, sections: CURVE_SECTIONS, yLabel: accLabel(ACC[0].id), secondary: ACC[1] || null }); }

    if (cmp.size) {
      const sc = h('section'); sc.style.marginTop = '28px'; const hc = sect('Compare', `${cmp.size} of 3`); sc.appendChild(hc);
      const chips = h('div', 'cmp-chips'); const list = [...cmp].map(id => byId.get(id)).filter(Boolean);
      list.forEach((m, i) => { const c = h('span', 'c s' + (i + 1)); c.appendChild(h('i')); c.appendChild(document.createTextNode(modelName(m))); const x = h('button', null, '×'); x.type = 'button'; x.setAttribute('aria-label', 'Remove ' + modelName(m)); x.addEventListener('click', () => act.toggleCompare(m.id)); c.appendChild(x); chips.appendChild(c); });
      const clr = h('button', 'btn sm ghost', 'Clear'); clr.type = 'button'; clr.addEventListener('click', () => act.clearCompare()); chips.appendChild(clr); sc.appendChild(chips);
      const tb = h('table', 'tv cmpt'); tb.style.marginTop = '12px'; const thead = h('thead'); const tr = h('tr'); tr.appendChild(h('th', null, '')); list.forEach(m => tr.appendChild(h('th', 'n', modelName(m)))); thead.appendChild(tr); tb.appendChild(thead);
      const tbody = h('tbody'); const base = list[0];
      const rowsDef = [...ACC.map(a => [a.label, a.id, 'lower']), [TIME.label + ' (' + TIME.unit + ')', TIME.id, 'lower'], ['Parameters', 'params', null], ['Updates', 'updates', null], ['Learning rate', 'lr', null]];
      for (const [label, key, better] of rowsDef) { const row = h('tr'); row.appendChild(h('td', null, label)); list.forEach((m, i) => { const v = m[key]; const td = h('td', 'n'); td.textContent = v == null ? '—' : (key === 'params' || key === 'updates') ? v.toLocaleString('en-GB') : key === 'lr' ? String(v) : key === TIME.id ? v.toFixed(2) : Tree.fmtSci(v); if (i > 0 && better && v != null && base[key] != null) { const d = (v - base[key]) / base[key]; const sp = h('span', 'd ' + (d < 0 ? 'better' : d > 0 ? 'worse' : ''), ' ' + (d > 0 ? '+' : '') + (d * 100).toFixed(1) + '%'); td.appendChild(sp); } row.appendChild(td); }); tbody.appendChild(row); }
      tb.appendChild(tbody); sc.appendChild(tb);
      const cc = h('div'); cc.style.marginTop = '14px'; sc.appendChild(cc);
      Charts.lines(cc, list.map((m, i) => ({ id: m.id, label: modelName(m), slot: i + 1, points: curveFor(m) })), { yLabel: 'Training loss', xLabel: 'updates', logY: true });
      main.appendChild(sc);
    }

    const st = h('section'); st.style.marginTop = '28px';
    const vis = popModels.filter(m => (!state.kinds || state.kinds.has(m.kind)) && (!state.query || Tree.matches(m, state.query)) && (!state.ui.benchOnly || benchState(m) === 'accuracy and time' || benchState(m) === 'generator benchmark'));
    const sort = state.sort || { key: 'n', dir: 1 };
    const cols = [['', 'cmp'], ['', 'ck'], ['Fit', 'short'], ['Kind', 'kind'], ['Group', 'groupLabel'], ...ACC.map(a => [a.label, a.id]), [TIME.label, TIME.id], ['Parameters', 'params'], ['Benchmark', 'bench']];
    vis.sort((a, b) => { const ka = a[sort.key], kb = b[sort.key]; if (ka == null && kb == null) return 0; if (ka == null) return 1; if (kb == null) return -1; return (typeof ka === 'number' ? ka - kb : String(ka).localeCompare(String(kb))) * sort.dir; });
    st.appendChild(sect('All fits', `${vis.length} of ${popModels.length}`));
    const tb = h('table', 'tv'); const thead = h('thead'); const tr = h('tr');
    for (const [label, key] of cols) { const th = h('th', ['ck', 'short', 'kind', 'groupLabel', 'cmp', 'bench'].includes(key) ? '' : 'n'); if (label && key !== 'bench') { const b = h('button', null, label); b.type = 'button'; if (sort.key === key) b.setAttribute('aria-sort', sort.dir > 0 ? 'ascending' : 'descending'); b.addEventListener('click', () => act.setSort(key)); th.appendChild(b); } else th.textContent = label; tr.appendChild(th); }
    thead.appendChild(tr); tb.appendChild(thead);
    const tbody = h('tbody');
    for (const m of vis) {
      const row = h('tr', 'rowbtn' + (m.id === sel ? ' is-sel' : '')); row.addEventListener('click', () => act.select(m.id));
      const tdc = h('td'); const cb = h('input'); cb.type = 'checkbox'; cb.checked = cmp.has(m.id); cb.disabled = !cmp.has(m.id) && cmp.size >= 3; cb.setAttribute('aria-label', 'Compare ' + modelName(m)); cb.addEventListener('click', ev => { ev.stopPropagation(); act.toggleCompare(m.id); }); tdc.appendChild(cb); row.appendChild(tdc);
      row.appendChild(h('td', 'ck', m.ck || '')); row.appendChild(h('td', null, m.short)); const kt = h('td'); kt.appendChild(h('span', 'chip ' + m.kind, Tree.kindLabel(m.kind))); row.appendChild(kt); row.appendChild(h('td', 'small faint nowrap', m.groupLabel.replace(/^C\d+[–-]C\d+\s*·\s*/, '')));
      for (const a of ACC) row.appendChild(h('td', 'n', m[a.id] == null ? '' : Tree.fmtSci(m[a.id])));
      row.appendChild(h('td', 'n', m[TIME.id] == null ? '' : m[TIME.id].toFixed(2))); row.appendChild(h('td', 'n', m.params == null ? '' : m.params.toLocaleString('en-GB'))); row.appendChild(h('td', 'small faint nowrap', benchState(m)));
      tbody.appendChild(row);
    }
    tb.appendChild(tbody); st.appendChild(tb); main.appendChild(st);

    const decisions = LAB.project.decisions || [];
    if (decisions.length) {
      const sd = h('section'); sd.style.marginTop = '28px'; sd.appendChild(sect('Study results', String(decisions.length)));
      const dt = h('table', 'tv'); const dh = h('thead'); const dtr = h('tr'); for (const [t, c] of [['Study', ''], ['Decision', ''], ['Reference', 'n'], ['Candidate', 'n'], ['Change', 'n']]) dtr.appendChild(h('th', c, t)); dh.appendChild(dtr); dt.appendChild(dh);
      const db = h('tbody'); for (const d of decisions) { const row = h('tr', 'rowbtn'); const stu = LAB.project.studies.find(x => x.label === d.plan); if (stu) row.addEventListener('click', () => act.go('train', stu.id)); row.appendChild(h('td', null, d.plan)); const td = h('td'); td.appendChild(stateEl(d.decision.includes('failed') ? 'serious' : d.decision.includes('pass') ? 'good' : 'neutral', d.decision)); if (d.note) td.appendChild(h('span', 'small faint', ' · ' + d.note)); row.appendChild(td); const isAcc = ACC.some(a => a.id === d.metric); row.appendChild(h('td', 'n', d.ref == null ? '—' : isAcc ? Tree.fmtSci(d.ref) : String(d.ref))); row.appendChild(h('td', 'n', d.cand == null ? '—' : isAcc ? Tree.fmtSci(d.cand) : String(d.cand))); const ch = h('td', 'n'); if (d.ref != null && d.cand != null && isAcc) { const dd = (d.cand - d.ref) / d.ref; ch.appendChild(h('span', 'd ' + (dd < 0 ? 'better' : 'worse'), (dd > 0 ? '+' : '') + (Math.abs(dd) > 9 ? (dd * 100).toFixed(0) : (dd * 100).toFixed(1)) + '%')); } row.appendChild(ch); db.appendChild(row); }
      dt.appendChild(db); sd.appendChild(dt); main.appendChild(sd);
    }

    if (sel) { inspectorModel(aside, sel, act, { compact: true }); const bs = benchState(byId.get(sel)); if (bs === 'none retained' || bs === 'accuracy only' || bs === 'time only') { const ev = (LAB.recipes || []).find(r => r.kind === 'evaluation'); const nb = h('p', 'note', 'No comparable benchmark retained for this fit' + (bs === 'none retained' ? '' : ' (' + bs + ')') + '.'); aside.querySelector('.inspector').insertBefore(nb, aside.querySelector('.actions')); if (ev) { const rb = h('button', 'btn', 'Run ' + ev.label.toLowerCase()); rb.type = 'button'; rb.title = ev.path; aside.querySelector('.actions').appendChild(rb); } } const acts = aside.querySelector('.actions:last-child'); const b = h('button', 'btn', cmp.has(sel) ? 'Remove from compare' : 'Compare'); b.type = 'button'; b.disabled = !cmp.has(sel) && cmp.size >= 3; b.addEventListener('click', () => act.toggleCompare(sel)); acts.insertBefore(b, acts.firstChild); const b2 = h('button', 'btn ghost', 'In Models'); b2.type = 'button'; b2.addEventListener('click', () => act.go('models', sel)); acts.appendChild(b2); return true; }
    const ins = h('div', 'inspector'); const hd = h('header'); hd.appendChild(h('h2', null, 'Frontier')); hd.appendChild(h('span', 'small muted', 'fastest first')); ins.appendChild(hd);
    const ul = h('ul', 'links');
    for (const m of r.frontier) { const li = h('li'); const b = h('button'); b.type = 'button'; b.appendChild(document.createTextNode(modelName(m))); b.appendChild(h('span', 'why', `${Tree.fmtSci(m[metric])} · ${m[TIME.id].toFixed(2)} ${TIME.unit} · ${Tree.kindLabel(m.kind).toLowerCase()}`)); b.addEventListener('click', () => act.select(m.id)); li.appendChild(b); ul.appendChild(li); }
    ins.appendChild(ul); aside.appendChild(ins);
    return false;
  }

  // ---- Analysis: field comparison per case, and the reports -----------------
  function drawField(canvas, fn) {
    const ctx = canvas.getContext('2d'), W = canvas.width = 240, Hh = canvas.height = 240, n = 32;
    const dark = getComputedStyle(document.documentElement).colorScheme === 'dark';
    const mid = dark ? [56, 56, 53] : [240, 239, 236], neg = dark ? [79, 138, 224] : [46, 111, 207], pos = dark ? [217, 111, 60] : [210, 101, 47];
    for (let j = 0; j < n; j++) for (let i = 0; i < n; i++) { const val = fn(i / n, j / n); const c = val < 0 ? neg : pos, t = Math.min(1, Math.abs(val)); const rgb = mid.map((m, k) => Math.round(m + (c[k] - m) * t)); ctx.fillStyle = `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`; ctx.fillRect(i * W / n, j * Hh / n, W / n + 1, Hh / n + 1); }
  }
  const caseErr = (m, c) => { const rnd = seeded(m.id + ':' + c); const base = m.worstP || 0.01; return base * (0.35 + 0.65 * Math.pow(rnd(), 2.2)); };
  function analysis(main, aside, state, act) {
    main.textContent = ''; aside.textContent = '';
    const sel = state.sel.analysis, cases = LAB.cases || { count: 0 }, ds = datasetOf(cases.dataset);
    const cands = LAB.models.filter(m => m.worstP != null && m.group !== MET.excludedGroup);
    const fit = byId.get(state.fit) || byId.get('fit-9a6432c54d9f9434') || cands[0];
    const cn = state.caseN || 1, z = state.slice || Math.round((cases.slices || 16) / 2);
    const vs = h('section'); vs.appendChild(sect('Field comparison', ds ? ds.label : ''));
    const vb = h('div', 'viewer-bar');
    const fsel = h('select'); fsel.setAttribute('aria-label', 'Fit'); for (const m of cands) { const o = h('option', null, modelName(m)); o.value = m.id; o.selected = m.id === fit.id; fsel.appendChild(o); } fsel.addEventListener('change', () => act.setFit(fsel.value)); vb.appendChild(fsel);
    const cl = h('label'); cl.appendChild(document.createTextNode('Case')); const ci = h('input'); ci.type = 'number'; ci.min = 1; ci.max = cases.count; ci.value = cn; ci.style.width = '64px'; ci.addEventListener('change', () => act.setCase(+ci.value)); cl.appendChild(ci); cl.appendChild(document.createTextNode('of ' + cases.count)); vb.appendChild(cl);
    const zl = h('label'); zl.appendChild(document.createTextNode('Slice z')); const zi = h('input'); zi.type = 'range'; zi.min = 1; zi.max = cases.slices || 16; zi.value = z; zi.addEventListener('change', () => act.setSlice(+zi.value)); zl.appendChild(zi); zl.appendChild(h('span', 'num', String(z))); vb.appendChild(zl);
    const fl = h('label'); fl.appendChild(document.createTextNode('Field')); const fs = h('select'); for (const f of cases.fields || ['pressure']) fs.appendChild(h('option', null, f)); fl.appendChild(fs); vb.appendChild(fl);
    vs.appendChild(vb);
    const tri = h('div', 'tri'); const err = caseErr(fit, cn), eqv = fit.eq ? fit.eq * (err / (fit.worstP || err)) : null;
    const seed = cn * 0.37 + z * 0.11;
    const native = (u, v) => Math.sin(6.3 * u + seed) * Math.cos(4.7 * v - seed * 0.5) * 0.7 + Math.sin(12 * u * v + seed) * 0.3;
    const amp = Math.min(0.9, Math.sqrt(err) * 6), pred = (u, v) => native(u, v) + amp * 0.5 * Math.sin(17 * u + 3 * seed) * Math.cos(13 * v + seed);
    const canvases = [];
    for (const [title, fn, cap] of [['Native', native, 'reference solve'], ['Predicted', pred, modelName(fit)], ['Signed error', (u, v) => (pred(u, v) - native(u, v)) / Math.max(amp, 0.05), 'rel. L2 ' + Tree.fmtSci(err)]]) { const fg = h('figure'); const cv = h('canvas'); cv.setAttribute('role', 'img'); cv.setAttribute('aria-label', title + ' field, case ' + cn + ', slice ' + z); fg.appendChild(cv); drawField(cv, fn); const fc = h('figcaption'); fc.appendChild(h('b', null, title)); fc.appendChild(h('span', null, cap)); fg.appendChild(fc); tri.appendChild(fg); canvases.push([cv, title]); }
    const redraw = zz => { const sd = cn * 0.37 + zz * 0.11; const nat = (u, v) => Math.sin(6.3 * u + sd) * Math.cos(4.7 * v - sd * 0.5) * 0.7 + Math.sin(12 * u * v + sd) * 0.3, pr = (u, v) => nat(u, v) + amp * 0.5 * Math.sin(17 * u + 3 * sd) * Math.cos(13 * v + sd); drawField(canvases[0][0], nat); drawField(canvases[1][0], pr); drawField(canvases[2][0], (u, v) => (pr(u, v) - nat(u, v)) / Math.max(amp, 0.05)); };
    zi.addEventListener('input', () => { redraw(+zi.value); zl.querySelector('.num').textContent = zi.value; });
    vs.appendChild(tri);
    const sc = h('div', 'scale'); sc.appendChild(document.createTextNode('−')); sc.appendChild(h('i')); sc.appendChild(document.createTextNode('+ · case ' + cn + ' · z ' + z + ' · ' + accLabel(ACC[0].id) + ' ' + Tree.fmtSci(err) + (eqv ? ' · ' + accLabel(ACC[1].id) + ' ' + Tree.fmtSci(eqv) : ''))); vs.appendChild(sc);
    const pc = h('div', 'cases'); const ph = sect('Per case', accLabel(ACC[0].id) + ' · ' + modelName(fit)); ph.style.marginTop = '16px'; pc.appendChild(ph);
    const Wc = 760, Hc = 64, errs = Array.from({ length: cases.count }, (_, i) => caseErr(fit, i + 1)), emax = Math.max(...errs);
    const svg = document.createElementNS(svgNS, 'svg'); svg.setAttribute('viewBox', `0 0 ${Wc} ${Hc}`); svg.setAttribute('role', 'img'); svg.setAttribute('aria-label', 'Error per case; the selected case is highlighted');
    const bw = Math.max(2, Wc / cases.count - 2);
    errs.forEach((e, i) => { const rect = document.createElementNS(svgNS, 'rect'); rect.setAttribute('x', i * Wc / cases.count); rect.setAttribute('y', Hc - 8 - (e / emax) * (Hc - 12)); rect.setAttribute('width', bw); rect.setAttribute('height', (e / emax) * (Hc - 12)); rect.setAttribute('rx', 1.5); rect.setAttribute('class', 'b' + (i + 1 === cn ? ' sel' : '')); const t = document.createElementNS(svgNS, 'title'); t.textContent = 'case ' + (i + 1) + ' · ' + Tree.fmtSci(e); rect.appendChild(t); rect.addEventListener('click', () => act.setCase(i + 1)); svg.appendChild(rect); });
    const base = document.createElementNS(svgNS, 'line'); base.setAttribute('x1', 0); base.setAttribute('x2', Wc); base.setAttribute('y1', Hc - 8); base.setAttribute('y2', Hc - 8); base.setAttribute('class', 'base'); svg.appendChild(base);
    pc.appendChild(svg); vs.appendChild(pc); main.appendChild(vs);

    const rp = h('section'); rp.style.marginTop = '28px'; const plans = LAB.project.evidence.map(g => g.plan); rp.appendChild(sect('Reports', String(plans.length)));
    const tb = h('table', 'tv'); const thead = h('thead'); const tr = h('tr'); for (const t of ['Plan', 'Outcome', 'Documents']) tr.appendChild(h('th', null, t)); thead.appendChild(tr); tb.appendChild(thead);
    const tbody = h('tbody');
    for (const plan of plans) { const stu = LAB.project.studies.find(x => x.label === plan); const row = h('tr'); row.appendChild(h('td', null, plan)); const od = h('td'); if (stu) od.appendChild(stateEl(studyState(stu), stu.decision)); else od.appendChild(h('span', 'faint', '—')); row.appendChild(od); const dd = h('td'); dd.appendChild(docChips(plan, sel, id => act.select(id))); row.appendChild(dd); tbody.appendChild(row); }
    tb.appendChild(tbody); rp.appendChild(tb); main.appendChild(rp);

    const ins = h('div', 'inspector');
    if (sel) {
      const item = LAB.project.evidence.flatMap(g => g.items.map(i => [g.plan, ...i])).find(x => x[1] === sel);
      const hd = h('header'); hd.appendChild(h('span', 'kicker', item ? item[0] : sel)); hd.appendChild(h('h2', null, item ? (DOC_ROLE(item[3]) || item[2]) : sel)); ins.appendChild(hd);
      if (item) { const pa = h('p', 'note'); pa.appendChild(fileLink(item[3], item[3])); ins.appendChild(pa); }
      ins.appendChild(h('pre', 'evtext', item ? `(text of ${item[3].split('/').pop()}, first 64 KiB)\n\nsha256: measured on open` : ''));
      aside.appendChild(ins); return true;
    }
    const hd = h('header'); hd.appendChild(h('span', 'kicker', 'case ' + cn)); hd.appendChild(h('h2', null, modelName(fit))); ins.appendChild(hd);
    const dl = h('dl', 'metrics'); dl.appendChild(cell(accLabel(ACC[0].id), Tree.fmtSci(err))); if (eqv) dl.appendChild(cell(accLabel(ACC[1].id), Tree.fmtSci(eqv))); dl.appendChild(cell('Worst of ' + cases.count, Tree.fmtSci(Math.max(...errs)))); dl.appendChild(cell('Median', Tree.fmtSci(errs.slice().sort((a, b) => a - b)[Math.floor(errs.length / 2)]))); ins.appendChild(dl);
    const acts = h('div', 'actions'); const b1 = h('button', 'btn', 'Open fit'); b1.type = 'button'; b1.addEventListener('click', () => act.go('models', fit.id)); acts.appendChild(b1); const b2 = h('button', 'btn ghost', 'Benchmark'); b2.type = 'button'; b2.addEventListener('click', () => act.go('benchmarks', fit.id)); acts.appendChild(b2); ins.appendChild(acts);
    if (ds) { const pa = h('p', 'note'); pa.appendChild(fileLink(ds.path, ds.path)); ins.appendChild(pa); }
    aside.appendChild(ins); return false;
  }

  // ---- Layout switcher: the three pages are proposals for the same screen.
  const LAYOUTS = [['a-stages.html', 'A', 'Stages'], ['b-map.html', 'B', 'Map'], ['c-ledger.html', 'C', 'Ledger']];
  function layoutSwitch(container, current) {
    const nav = h('nav', 'layouts'); nav.setAttribute('aria-label', 'Layout proposal'); nav.appendChild(h('span', 'lbl', 'Layout'));
    const links = LAYOUTS.map(([file, k, label]) => { const a = h('a'); a.href = file; a.textContent = k + ' ' + label; if (file === current) a.setAttribute('aria-current', 'page'); nav.appendChild(a); return [a, file]; });
    const cmp = h('a', 'cmp', 'All three'); cmp.href = 'index.html'; nav.appendChild(cmp);
    const update = () => { const r = (window.mockRoute && window.mockRoute()) || {}; const screen = r.screen || 'overview'; for (const [a, file] of links) a.href = file + (file === 'c-ledger.html' ? '#s-' + screen : '#' + screen + (r.id ? '/' + encodeURIComponent(r.id) : '')); };
    container.textContent = ''; container.appendChild(nav); update(); window.addEventListener('hashchange', update); return { update };
  }

  // ---- Theme toggle --------------------------------------------------------
  const theme = {
    init(btn) {
      let cur = 'auto'; try { cur = localStorage.getItem('tuldok-mock-theme') || 'auto'; } catch (e) {}
      const q = new URLSearchParams(location.search).get('theme'); if (q === 'light' || q === 'dark') cur = q;
      const apply = () => { if (cur === 'auto') document.documentElement.removeAttribute('data-theme'); else document.documentElement.setAttribute('data-theme', cur); btn.textContent = ''; btn.appendChild(icon('theme')); btn.appendChild(document.createTextNode(' ' + { auto: 'System', light: 'Light', dark: 'Dark' }[cur])); btn.setAttribute('aria-label', 'Theme: ' + cur); };
      btn.addEventListener('click', () => { cur = { auto: 'light', light: 'dark', dark: 'auto' }[cur]; try { localStorage.setItem('tuldok-mock-theme', cur); } catch (e) {} apply(); });
      apply();
    }
  };
  window.addEventListener('error', e => { const b = document.createElement('div'); b.setAttribute('role', 'alert'); b.style.cssText = 'position:fixed;left:8px;bottom:8px;z-index:99;padding:8px 12px;background:#fff;border:2px solid #b7452b;color:#1b2330;font:13px monospace;max-width:80vw'; b.textContent = 'Mockup script error: ' + e.message + ' (' + (e.filename || '').split('/').pop() + ':' + e.lineno + ')'; document.body.appendChild(b); });

  return { overview, data, annotate, models, train, benchmarks, analysis, inspectorModel, setPlanned, statusLine, stageSummaries, icon, stateEl, theme, layoutSwitch, graph, KINDS, kindLabel: Tree.kindLabel };
})();
