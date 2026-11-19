'use strict';
// The page's one way to the project. It calls the project's operations
// (POST /api/project/<name>) with the contract the server publishes at
// /api/agent/capabilities (never pinned here), keeps each answer until it is
// read again, and shapes what the screens read: the map's sections, models
// and lines, the sentence of where the project stands, and what needs the
// person. It reads on its own; an operation that changes the project is
// called only by a control the person pressed (actions.js). Reading again
// (again()) compares each answer's text with the kept one, so the page can
// leave alone what did not change; what is not watched is forgotten when
// something changed (forgetBut()). A refusal is thrown as an Error carrying
// the server's code, problems, references and files.
window.TuldokProject = (() => {
  // Kinds of change, by the project format's names, with the brief's labels.
  const KINDS = [
    { id: 'training-policy', label: 'Training policy' },
    { id: 'architecture', label: 'Architecture' },
    { id: 'refinement', label: 'Refinement' },
    { id: 'component', label: 'Component' },
    { id: 'sweep-trial', label: 'Sweep trial' }   // a trial a sweep made (spec-t7)
  ];
  const UNSET = 'unset';   // the class and filter key of a model without a kind of change
  const kindLabel = id => (KINDS.find(k => k.id === id) || { label: 'Kind not set' }).label;
  // A model's state, as a word and the tone of its mark.
  const STATES = {
    built: ['built', 'good'], running: ['running', 'pending'], 'out-of-date': ['out of date', 'warn'],
    failed: ['failed', 'serious'], 'not-built': ['not built', 'neutral'], 'needs-work': ['needs work', 'warn'],
    'cannot-rebuild': ['cannot be rebuilt', 'neutral'], none: ['nothing to build', 'neutral'],
    ready: ['ready', 'good'], failing: ['failing', 'serious'], 'not-set-up': ['not set up', 'warn']
  };
  const stateWord = s => (STATES[s] || [s || 'unknown', 'neutral']);
  const ENDED_BADLY = { failed: 'failed', 'timed-out': 'ran out of time', 'over-disk': 'went over its disk budget', unknown: 'ended in an unknown state' };

  // ---- Calls --------------------------------------------------------------
  let contracts = null;
  async function json(response) {
    let value;
    try { value = await response.json(); } catch (e) { throw Error('The server answered ' + response.status + ' without JSON.'); }
    if (!response.ok) throw Object.assign(Error(value.error || 'The request was refused.'), { code: value.code, status: response.status,
      problems: Array.isArray(value.problems) ? value.problems : [], references: Array.isArray(value.references) ? value.references : [], files: Array.isArray(value.files) ? value.files : [] });
    return value;
  }
  async function selection(name) {
    if (!contracts) {
      const manifest = await json(await window.TuldokAuth.fetch('/api/agent/capabilities', { cache: 'no-store' }));
      contracts = new Map(manifest.operations.map(operation => {
        const newest = operation.contracts.reduce((a, b) => (b.version > a.version ? b : a));
        return [operation.id, operation.id + '/' + newest.version + '/' + newest.sha256];
      }));
    }
    if (!contracts.has(name)) throw Error('This Tuldok does not offer ' + name + '.');
    return contracts.get(name);
  }
  async function call(name, body = {}) {
    try {
      const response = await window.TuldokAuth.fetch('/api/project/' + name, {
        method: 'POST', cache: 'no-store',
        headers: { 'Content-Type': 'application/json', 'Tuldok-Operation-Contract': await selection('project.' + name) },
        body: JSON.stringify(body)
      });
      return await json(response);
    } catch (error) { contracts = null; throw error; }
  }

  // Answers are kept by operation and arguments until forgotten, each with its text, so a reading
  // again can tell an answer that changed from one that did not.
  const kept = new Map();   // key -> { answer: promise, text: the answer as JSON once it came }
  const keyOf = (name, args) => name + ' ' + JSON.stringify(args);
  function read(name, args = {}) {
    const key = keyOf(name, args);
    if (!kept.has(key)) {
      const entry = { text: null };
      entry.answer = call(name, args).then(value => { entry.text = JSON.stringify(value); entry.value = value; return value; }, error => { if (kept.get(key) === entry) kept.delete(key); throw error; });
      kept.set(key, entry);
    }
    return kept.get(key).answer;
  }
  /**
   * Asks again for the kept answer of each named operation (no arguments),
   * asking for the first time when none is kept, and resolves to the names
   * whose answer differs from the kept one; for those the kept answer is
   * replaced, and an equal answer leaves the kept object as it is. When any
   * of them is refused or does not arrive, the error is thrown and nothing
   * kept is replaced: a reading that failed changes nothing.
   */
  async function again(names) {
    const got = await Promise.all(names.map(async name => {
      const key = keyOf(name, {}), had = kept.get(key);
      const before = had ? await had.answer.then(() => had.text, () => null) : null;
      const value = await call(name, {});
      return { name, key, had, before, value, text: JSON.stringify(value) };
    }));
    const changed = [];
    for (const g of got) {
      if (g.before !== null && g.text === g.before && kept.get(g.key) === g.had) continue;
      kept.set(g.key, { answer: Promise.resolve(g.value), text: g.text }); changed.push(g.name);
    }
    return changed;
  }
  /** The kept answer of a read when it has arrived, else undefined; asks nothing (the Benchmarks tab's intervals, spec-t3 section 5.2). */
  function peek(name, args = {}) { const entry = kept.get(keyOf(name, args)); return entry && entry.text !== null ? (entry.value !== undefined ? entry.value : JSON.parse(entry.text)) : undefined; }
  function forget(names) { for (const key of [...kept.keys()]) if (names.includes(key.split(' ')[0])) kept.delete(key); }
  /** Forgets every kept answer whose operation is not named. */
  function forgetBut(names) { for (const key of [...kept.keys()]) if (!names.includes(key.split(' ')[0])) kept.delete(key); }
  function forgetAll() { kept.clear(); }
  // What the page watches: asked again on every reading ('map' on some, app.js), kept across a change.
  const WATCHED = ['summary', 'status', 'build_requests', 'environments', 'runs', 'map'];

  // ---- Looking inside a product (spec-d1.md, inside.js) -----------------------------
  // The five reads of a finished run's product. Their answers are kept like any other until a reading
  // finds something changed (they are not watched, so forgetBut() drops them); the slice the viewer draws
  // as a slider moves is asked for each time and not kept, so the kept answers do not grow with every move.
  const defined = o => Object.fromEntries(Object.entries(o).filter(([, v]) => v !== undefined && v !== null));
  const product = {
    records: (run, { offset, limit, kind, split } = {}) => read('records', defined({ run, offset, limit, kind, split })),
    record: (run, id) => read('record', { run, id }),
    /** Any file of the product, or a member of an archive in it, read as a record by its address. */
    recordAt: (run, path) => read('record', { run, path }),
    inside: (run, { path, offset, limit } = {}) => read('inside', defined({ run, path: path || null, offset, limit })),
    /** A slice; kept unless fresh (the viewer's slider). */
    slice: (run, { path, array, axes, index, most }, fresh = false) => (fresh ? call : read)('array_slice', defined({ run, path, array, axes, index, most })),
    summary: (run, { path, array, bins }) => read('array_summary', defined({ run, path, array, bins })),
    // A model's weights (spec-d2.md, weights.js): its weights files, a comparison of two, and tiles of a tensor
    // of three or more axes (asked for each time the person moves through them unless kept).
    weights: run => read('weights', { run }),
    compare: (run, path, otherRun, otherPath) => read('weights_compare', { run, path, other_run: otherRun, other_path: otherPath }),
    tiles: (run, { path, array, across, axes, index, first, most }, fresh = false) => (fresh ? call : read)('array_tiles', defined({ run, path, array, across, axes, index, first, most })),
    // The fields a run kept (spec-d6.md, fields.js): its cases, and one slice of a case's native field, prediction
    // and signed error with the error's figures (asked for each time the person moves through it unless kept).
    fields: run => read('fields', { run }),
    fieldCompare: (run, { entry, case: one, axis, index, mean_free }, fresh = false) => (fresh ? call : read)('field_compare', defined({ run, entry, case: one, axis, index, mean_free })),
    // A model's structure (spec-t2.md, structure.js): its graph folded by the person's choices, a number per module
    // and operation, and the matching of two graphs' modules. Kept like the rest until a reading finds a change.
    graph: (run, { depth, open, close } = {}) => read('model_graph', defined({ run, depth, open: open && open.length ? open : null, close: close && close.length ? close : null })),
    graphOverlay: (run, { kind, against, other_run, path, other_path }) => read('model_graph_overlay', defined({ run, kind, against, other_run, path, other_path })),
    graphCompare: (run, otherRun) => read('model_graph_compare', { run, other_run: otherRun }),
    /** The address of an image's or a sound's bytes (GET /api/project/file), as the record operation gives it. */
    fileUrl: (run, path) => '/api/project/file?run=' + encodeURIComponent(run) + '&path=' + encodeURIComponent(path)
  };

  // ---- Annotating (spec-d4.md, annotate.js) --------------------------------------------------
  // The three reads of annotations, kept like any other answer until a reading finds something changed (they are
  // not watched, so forgetBut() drops them). The two changes (set_annotation, revert_annotations) are called by
  // controls (actions.js) by their names.
  const annotations = {
    tasks: () => read('annotation_tasks'),
    /** A page of a task's records with their annotations; state one of the counts' names, or none for all. */
    records: (task, { state, kind, offset, limit } = {}) => read('annotated_records', defined({ task, state, kind, offset, limit })),
    one: (task, record) => read('annotation', { task, record })
  };
  /** How many records have an unsaved annotation, in all, from a status answer. */
  const annotationsUnsaved = status => ((status && status.annotations_unsaved) || []).reduce((n, t) => n + t.records, 0);

  // ---- The map ------------------------------------------------------------
  /**
   * What the Map tab and the drawer read, from the answer of `map`:
   * sections (one per group that has models, the group tree read depth
   * first in authored order, then one section "Not in a group" when a model
   * names no group), models in section order and, within a section, in the
   * map's order (training date, then those without one) except that one
   * without a date naming a parent comes right after it (placed()), inputs
   * as lines, comparisons and the track with its scale. The page's drafts
   * (editor.js) are models too, marked draft.
   */
  function shapeMap(raw, drafts = []) {
    const groups = new Map(raw.groups.map(g => [g.id, g]));
    const children = new Map(), roots = [];
    for (const g of raw.groups) {
      if (g.parent && groups.has(g.parent)) { if (!children.has(g.parent)) children.set(g.parent, []); children.get(g.parent).push(g); }
      else roots.push(g);
    }
    const order = [], seen = new Set();
    const visit = (g, up) => { if (seen.has(g.id)) return; seen.add(g.id); order.push({ group: g, up }); for (const c of children.get(g.id) || []) visit(c, up.concat([g.title])); };
    roots.forEach(g => visit(g, []));
    const kinds = new Set(KINDS.map(k => k.id));
    const models = raw.models.map(m => ({
      id: m.reference, title: m.title, short: m.short, description: m.description || '',
      group: groups.has(m.group) ? m.group : null, kind: kinds.has(m.change) ? m.change : UNSET,
      parent: m.derived_from || null, trainedAt: m.trained_at, state: m.state, adopted: m.adopted, card: m.card,
      value: m.value, count: m.count, benchmarks: m.benchmarks, unsaved: !!m.unsaved,
      // Never built: drawn hollow and dashed (spec-w3 section 3.2).
      planned: m.state === 'not-built' && !m.adopted && !m.trained_at
    }));
    // A draft (editor.js) is a model of the page only, after its parent's models.
    for (const d of drafts) models.push({
      id: d.reference, title: d.title, short: d.short || null, description: d.description || '',
      group: groups.has(d.group) ? d.group : null, kind: kinds.has(d.change) ? d.change : UNSET,
      parent: d.parent, trainedAt: null, state: 'draft', adopted: false, card: null,
      value: null, count: null, benchmarks: 0, unsaved: false, planned: true, draft: true
    });
    const byId = new Map(models.map(m => [m.id, m]));
    for (const m of models) if (m.parent && !byId.has(m.parent)) m.parent = null;
    const sections = [];
    for (const { group, up } of order) {
      const list = placed(models.filter(m => m.group === group.id));
      if (list.length) sections.push({ id: group.id, title: group.title, up, description: group.description, models: list });
    }
    const loose = placed(models.filter(m => m.group === null));
    if (loose.length) sections.push({ id: null, title: 'Not in a group', up: [], loose: true, models: loose });
    for (const s of sections) for (const m of s.models) m.groupTitle = s.title;
    const derived = new Set(raw.edges.filter(e => e.kind === 'derived').map(e => e.from + ' ' + e.to));
    const inputs = raw.edges.filter(e => e.kind === 'input' && !derived.has(e.from + ' ' + e.to) && byId.has(e.from) && byId.has(e.to))
      .map(e => ({ from: e.to, to: e.from }));   // drawn from the input to the model that uses it
    const comparisons = raw.comparisons.filter(c => byId.has(c.from) && byId.has(c.to));
    const track = raw.track;
    const trackScale = track ? window.LabCharts.scale(models.map(m => m.value), track.metric.better) : null;
    return { sections, models: sections.flatMap(s => s.models), byId, inputs, comparisons, track, trackScale, groups: raw.groups };
  }
  /**
   * One section's models in the map's order, except that a model without a
   * date naming a parent in the same section comes right after that parent,
   * after the parent's earlier such children (spec-w3 section 3.2). Linear.
   */
  function placed(list) {
    const here = new Set(list.map(m => m.id)), after = new Map(), moved = new Set();
    for (const m of list) if (!m.trainedAt && m.parent && m.parent !== m.id && here.has(m.parent)) {
      if (!after.has(m.parent)) after.set(m.parent, []);
      after.get(m.parent).push(m); moved.add(m.id);
    }
    if (!moved.size) return list;
    const out = [], seen = new Set();
    const emit = m => { if (seen.has(m.id)) return; seen.add(m.id); out.push(m); for (const c of after.get(m.id) || []) emit(c); };
    for (const m of list) if (!moved.has(m.id)) emit(m);
    for (const m of list) emit(m);   // a loop of parents without dates (never stored): kept, in the map's order
    return out;
  }
  // The drafts of the page (editor.js): drawn on the map, never sent anywhere. A draft
  // whose parent is gone, or whose reference the project now has, is dropped
  // (onDrop tells editor.js); a session that may not edit draws none.
  let drafts = [], draftsVersion = 0, onDrop = () => {};
  function setDrafts(list, dropped) { drafts = list.slice(); draftsVersion++; if (dropped) onDrop = dropped; }
  let mapRaw = null, mapShaped = null, mapKey = '';
  async function map() {
    const raw = await read('map');
    const editing = !!(window.LabActions && window.LabActions.may('edit')), key = draftsVersion + ' ' + editing;
    if (raw !== mapRaw || key !== mapKey) {
      const refs = new Set(raw.models.map(m => m.reference));
      const gone = drafts.filter(d => !refs.has(d.parent) || refs.has(d.reference));
      const shown = editing ? drafts.filter(d => !gone.includes(d)) : [];
      mapRaw = raw; mapKey = key; mapShaped = shapeMap(raw, shown);
      if (gone.length) onDrop(gone);
    }
    return mapShaped;
  }
  const trackName = track => track ? track.metric.title + ' · ' + track.statistic : '';
  const better = track => track && track.metric.better === 'higher' ? 'higher is better' : 'lower is better';
  const units = track => track && track.metric.units && track.metric.units !== '1' ? ' ' + track.metric.units : '';

  // ---- Where the project stands -------------------------------------------
  const plural = (n, one, many) => n + ' ' + (n === 1 ? one : many);
  function titleOf(shaped, reference) { const m = shaped && shaped.byId.get(reference); return m ? (m.short ? m.short + ' · ' : '') + m.title : reference; }
  /**
   * {tone, word, text}: the one sentence of the status strip. Reads the map's
   * model states and, once read, the runs and build requests.
   */
  function standing(shaped, runs, requests) {
    const models = shaped.models.filter(m => !m.draft), count = s => models.filter(m => s.includes(m.state)).length;
    const built = count(['built']), toBuild = count(['not-built', 'out-of-date', 'failed']), cannot = count(['cannot-rebuild']), work = count(['needs-work']);
    const parts = [(built ? built : 'none') + ' built', toBuild + ' to build', cannot + ' cannot be rebuilt'];
    if (work) parts.push(work + (work === 1 ? ' needs' : ' need') + ' work');
    let text = plural(models.length, 'model', 'models') + ': ' + parts.join(', ') + '.';
    const running = (runs || []).filter(r => r.state === 'running'), queued = (requests || []).filter(r => r.state === 'queued' || r.state === 'running');
    let tone = 'good', word = 'Idle';
    if (running.length) { tone = 'pending'; word = 'Building'; text += ' Running ' + running.map(r => titleOf(shaped, r.reference) + (r.subject ? ' (' + r.subject + ')' : '')).join(', ') + '.'; }
    else if (queued.some(r => r.state === 'running')) { tone = 'pending'; word = 'Building'; text += ' A build is between two of its steps.'; }   // a request runs, none of its runs does at this moment
    else if (queued.length) { tone = 'pending'; word = 'Queued'; text += ' ' + plural(queued.length, 'build request is', 'build requests are') + ' queued.'; }
    else if (runs && requests) text += ' Nothing is running.';
    return { tone, word, text };
  }

  const day = iso => iso ? new Date(iso).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) : '';
  const listed = (items, most = 3) => items.slice(0, most).join(', ') + (items.length > most ? ' and ' + (items.length - most) + ' more' : '');
  /**
   * What needs the person, each a sentence with a kind ('approval', 'changed'
   * or 'missing', which sets its mark): build requests awaiting approval,
   * unsaved edits and files changed on disk, environments not ready, the
   * definitions whose last run ended badly, a build worker stopped or elsewhere.
   */
  function needs({ summary, status, requests, environments, runs, shaped }) {
    const out = [];
    for (const r of requests) if (r.state === 'awaiting-approval') {
      const who = r.requested_by && (r.requested_by.label || r.requested_by.kind) || 'someone';
      out.push({ kind: 'approval', key: 'request:' + r.id, request: r, text: 'A build of ' + (r.every ? 'everything buildable' : listed(r.targets || [])) + ', asked by ' + who + ' on ' + day(r.requested_at) + ', awaits your approval.' });
    }
    if (status.unsaved.length) out.push({ kind: 'changed', key: 'unsaved', save: true, references: status.unsaved.map(String), text: plural(status.unsaved.length, 'definition has', 'definitions have') + ' unsaved edits: ' + listed(status.unsaved.map(String)) + '.' });
    const typed = annotationsUnsaved(status);
    if (typed) out.push({ kind: 'changed', key: 'annotations-unsaved', save: true, references: status.annotations_unsaved.map(t => t.task), text: plural(typed, 'annotation is', 'annotations are') + ' unsaved: ' + listed(status.annotations_unsaved.map(t => t.task + ' (' + t.records + ')')) + '.' });
    if (status.removed.length) out.push({ kind: 'changed', key: 'removed', save: true, references: status.removed.map(String), text: plural(status.removed.length, 'definition is', 'definitions are') + ' marked removed and not yet saved: ' + listed(status.removed.map(String)) + '.' });
    const disk = [].concat(status.added, status.changed, status.missing, status.annotations_changed || []).map(String);
    if (disk.length) out.push({ kind: 'changed', text: plural(disk.length, 'file changed', 'files changed') + ' on disk since the project was last read: ' + listed(disk) + '.' });
    if (status.irregular.length) out.push({ kind: 'missing', text: plural(status.irregular.length, 'file is', 'files are') + ' not regular files and are not read: ' + listed(status.irregular.map(String)) + '.' });
    const results = [].concat(status.results_unsaved, status.results_changed).map(String);
    if (results.length) out.push({ kind: 'changed', text: 'Results differ from their files: ' + listed(results) + '.' });
    for (const e of environments) if (e.state !== 'ready') out.push({ kind: e.state === 'failing' ? 'missing' : 'changed', key: 'env:' + e.reference, environment: e, text: 'The environment ' + e.title + (e.state === 'failing' ? ' failed its last check.' : ' is not set up on this machine.') });
    const last = new Map();
    for (const r of runs) if (!last.has(r.reference)) last.set(r.reference, r);   // runs come newest first
    for (const [reference, r] of last) if (ENDED_BADLY[r.state]) out.push({ kind: 'missing', key: 'run:' + r.id, run: r, reference, text: 'The last run of ' + titleOf(shaped, reference) + ' ' + ENDED_BADLY[r.state] + (r.finished_at ? ' on ' + day(r.finished_at) : '') + '.' });
    if (summary.worker === 'stopped') out.push({ kind: 'changed', text: 'The build worker is stopped: queued builds will not start.' });
    if (summary.worker === 'elsewhere') out.push({ kind: 'changed', text: 'Another Tuldok process runs the builds of this project.' });
    return out;
  }

  return { KINDS, UNSET, WATCHED, kindLabel, stateWord, call, read, peek, again, forget, forgetBut, forgetAll, map, setDrafts, trackName, better, units, standing, needs, titleOf, day, product, annotations, annotationsUnsaved };
})();
