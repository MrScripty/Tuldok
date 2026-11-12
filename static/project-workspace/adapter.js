'use strict';
// The page's one way to the project. It calls the project's operations
// (POST /api/project/<name>) with the contract the server publishes at
// /api/agent/capabilities (never pinned here), keeps each answer until it is
// read again, and shapes what the screens read: the map's sections, models
// and lines, the sentence of where the project stands, and what needs the
// person. It reads on its own; an operation that changes the project is
// called only by a control the person pressed (actions.js), after which every
// kept answer is forgotten. A refusal is thrown as an Error carrying the
// server's code, problems, references and files.
window.TuldokProject = (() => {
  // Kinds of change, by the project format's names, with the brief's labels.
  const KINDS = [
    { id: 'training-policy', label: 'Training policy' },
    { id: 'architecture', label: 'Architecture' },
    { id: 'refinement', label: 'Refinement' },
    { id: 'component', label: 'Component' }
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

  // Answers are kept by operation and arguments until forgotten.
  const kept = new Map();
  function read(name, args = {}) {
    const key = name + ' ' + JSON.stringify(args);
    if (!kept.has(key)) kept.set(key, call(name, args).catch(error => { kept.delete(key); throw error; }));
    return kept.get(key);
  }
  function forget(names) { for (const key of [...kept.keys()]) if (names.includes(key.split(' ')[0])) kept.delete(key); }
  function forgetAll() { kept.clear(); }

  // ---- The map ------------------------------------------------------------
  /**
   * What the Map tab and the drawer read, from the answer of `map`:
   * sections (one per group that has models, the group tree read depth
   * first in authored order, then one section "Not in a group" when a model
   * names no group), models in section order and, within a section, in the
   * map's order (training date, then those without one), inputs as lines,
   * comparisons and the track with its scale.
   */
  function shapeMap(raw) {
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
      value: m.value, count: m.count, benchmarks: m.benchmarks
    }));
    const byId = new Map(models.map(m => [m.id, m]));
    for (const m of models) if (m.parent && !byId.has(m.parent)) m.parent = null;
    const sections = [];
    for (const { group, up } of order) {
      const list = models.filter(m => m.group === group.id);
      if (list.length) sections.push({ id: group.id, title: group.title, up, description: group.description, models: list });
    }
    const loose = models.filter(m => m.group === null);
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
  let mapRaw = null, mapShaped = null;
  async function map() {
    const raw = await read('map');
    if (raw !== mapRaw) { mapRaw = raw; mapShaped = shapeMap(raw); }
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
    const count = s => shaped.models.filter(m => s.includes(m.state)).length;
    const built = count(['built']), toBuild = count(['not-built', 'out-of-date', 'failed']), cannot = count(['cannot-rebuild']), work = count(['needs-work']);
    const parts = [(built ? built : 'none') + ' built', toBuild + ' to build', cannot + ' cannot be rebuilt'];
    if (work) parts.push(work + (work === 1 ? ' needs' : ' need') + ' work');
    let text = plural(shaped.models.length, 'model', 'models') + ': ' + parts.join(', ') + '.';
    const running = (runs || []).filter(r => r.state === 'running'), queued = (requests || []).filter(r => r.state === 'queued' || r.state === 'running');
    let tone = 'good', word = 'Idle';
    if (running.length) { tone = 'pending'; word = 'Building'; text += ' Running ' + running.map(r => titleOf(shaped, r.reference) + (r.subject ? ' (' + r.subject + ')' : '')).join(', ') + '.'; }
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
    if (status.removed.length) out.push({ kind: 'changed', key: 'removed', save: true, references: status.removed.map(String), text: plural(status.removed.length, 'definition is', 'definitions are') + ' marked removed and not yet saved: ' + listed(status.removed.map(String)) + '.' });
    const disk = [].concat(status.added, status.changed, status.missing).map(String);
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

  return { KINDS, UNSET, kindLabel, stateWord, call, read, forget, forgetAll, map, trackName, better, units, standing, needs, titleOf, day };
})();
