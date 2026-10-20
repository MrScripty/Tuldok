/* Host-owned renderer for one pinned Altair recipe. No dynamic chart plugins. */
(() => {
  'use strict';
  window.WorkspaceRetainedContracts = Object.freeze({
    'runs.retained_analysis/1': '8ec28793a0603b206cb720d0ece573793c474fed901fb8ce99133d0154526cd5',
    'runs.export_retained_analysis/1': '0994932e96aab5d9561a63e3447bb8ec1f6345607e247ddb5a9cadaccffc57fb'
  });
  const SPEC_PATH = '/static/retained-checkpoint-curve.vl.json';
  const SPEC_SHA256 = '6603c860ce76a434a11e6c96cf7418246ce2dd5da3d7a56a5f2448a0537ec183';
  const HASH = /^[a-f0-9]{64}$/;
  const MAX_BYTES = 256 * 1024;
  const fields = ['example_id', 'truth_index', 'predicted_index', 'confidence', 'error'];
  const types = ['string', 'integer', 'integer', 'number', 'boolean'];
  const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
  const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
  const integer = value => Number.isSafeInteger(value) && value >= 0;
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const fail = () => { throw Error('Retained analysis response is invalid or exceeds its budget.'); };
  function validate(value, request) {
    if (!object(value) || new TextEncoder().encode(JSON.stringify(value)).length > MAX_BYTES) fail();
    const keys = ['state', 'query_id', 'query_version', 'mode', 'provenance', 'metric', 'curve', 'columns', 'examples', 'sampling', 'selection_sha256'];
    if (Object.keys(value).length !== keys.length || keys.some(key => !own(value, key))) fail();
    if (value.state !== 'verified' || value.query_id !== 'retained_checkpoint_examples' || value.query_version !== 1 || value.mode !== 'frozen') fail();
    const p = value.provenance;
    if (!object(p) || ['evaluation_sha256', 'checkpoint_sha256', 'metric_definition_sha256'].some(key => p[key] !== request[key] || !HASH.test(p[key])) || p.run_id !== request.run_id) fail();
    if (typeof p.catalog_id !== 'string' || p.catalog_id.length > 64 || ['population_sha256', 'probe_sha256', 'data_sha256'].some(key => typeof p[key] !== 'string' || !HASH.test(p[key]))) fail();
    if (!object(p.producer) || p.producer.catalog_id !== p.catalog_id || p.producer.run_id !== p.run_id || ['material_sha256', 'adapter_sha256'].some(key => typeof p.producer[key] !== 'string' || !HASH.test(p.producer[key]))) fail();
    if (!object(value.metric) || value.metric.id !== request.metric_id || typeof value.metric.units !== 'string' || value.metric.units.length > 64 || !integer(value.metric.support) || value.metric.support > 10000) fail();
    if (!object(value.metric.definition) || value.metric.definition.id !== value.metric.id || value.metric.definition.split !== 'validation' || value.metric.definition.units !== value.metric.units || value.metric.definition.population_sha256 !== p.population_sha256) fail();
    if (!Array.isArray(value.curve) || value.curve.length < 1 || value.curve.length > 128) fail();
    const checkpoints = new Set();
    let previous = 0;
    for (const point of value.curve) {
      if (!object(point) || typeof point.checkpoint_sha256 !== 'string' || !HASH.test(point.checkpoint_sha256) || checkpoints.has(point.checkpoint_sha256) || !integer(point.epoch) || point.epoch <= previous || !finite(point.value) || point.support !== value.metric.support) fail();
      checkpoints.add(point.checkpoint_sha256); previous = point.epoch;
    }
    if (!checkpoints.has(request.checkpoint_sha256) || !HASH.test(value.selection_sha256)) fail();
    const e = value.examples;
    if (!object(e) || !Array.isArray(e.rows) || !integer(e.limit) || e.limit < 1 || e.limit > 100 || e.rows.length > e.limit || !integer(e.offset) || e.offset > 10000 || !integer(e.population_support) || e.population_support > 10000 || !integer(e.filtered_support) || e.filtered_support > e.population_support) fail();
    if (!object(e.filters) || e.filters.errors_only !== (request.errors_only ?? false) || e.offset !== (request.offset ?? 0) || e.limit !== (request.limit ?? 50) || e.population_support !== value.metric.support) fail();
    if (!e.filters.errors_only && e.filtered_support !== e.population_support) fail();
    if (e.rows.length > Math.max(0, e.filtered_support - e.offset)) fail();
    const next = e.offset + e.rows.length < e.filtered_support ? e.offset + e.rows.length : null;
    if (e.next_offset !== next || (next !== null && e.rows.length === 0)) fail();
    if (!Array.isArray(value.columns) || value.columns.length > fields.length || value.columns.length < 1) fail();
    const selected = request.fields ?? fields;
    if (value.columns.length !== selected.length || value.columns.some((column, index) => !object(column) || column.field !== selected[index] || !fields.includes(column.field) || column.type !== types[fields.indexOf(column.field)] || column.units !== (column.field === 'confidence' ? 'dimensionless' : null))) fail();
    const seen = new Set();
    let ordinal = -1;
    for (const row of e.rows) {
      if (!object(row) || typeof row.example_id !== 'string' || row.example_id.length > 200 || seen.has(row.example_id) || !integer(row.ordinal) || row.ordinal >= e.population_support || row.ordinal <= ordinal || !object(row.frozen_reference) || row.frozen_reference.id !== row.example_id) fail();
      if (own(row, 'confidence') && (!finite(row.confidence) || row.confidence < 0 || row.confidence > 1)) fail();
      if (own(row, 'truth_index') && !integer(row.truth_index) || own(row, 'predicted_index') && !integer(row.predicted_index) || own(row, 'error') && typeof row.error !== 'boolean') fail();
      if (selected.some(field => !own(row, field))) fail();
      if (e.filters.errors_only && own(row, 'error') && !row.error) fail();
      seen.add(row.example_id); ordinal = row.ordinal;
    }
    if (!object(value.sampling) || value.sampling.method !== 'none' || value.sampling.population !== 'frozen_validation_probe') fail();
    return value;
  }
  function node(tag, text, attributes = {}) {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, value);
    return element;
  }
  async function specification(signal) {
    const reply = await fetch(SPEC_PATH, {signal, credentials: 'same-origin', cache: 'no-cache'});
    if (!reply.ok) throw Error('Retained chart specification is unavailable.');
    const reader = reply.body.getReader();
    let raw = new Uint8Array(0);
    while (true) {
      const {value, done} = await reader.read();
      if (done) break;
      if (raw.byteLength + value.byteLength > 16384) {
        await reader.cancel();
        throw Error('Retained chart specification exceeds its budget.');
      }
      const next = new Uint8Array(raw.byteLength + value.byteLength);
      next.set(raw); next.set(value, raw.byteLength); raw = next;
    }
    const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', raw))].map(byte => byte.toString(16).padStart(2, '0')).join('');
    if (hash !== SPEC_SHA256) throw Error('Retained chart specification identity differs.');
    return JSON.parse(new TextDecoder().decode(raw));
  }
  function mount(root, {load, onSelection = () => {}}) {
    let disposed = false, generation = 0, pending, view, observer, current;
    function clear() {
      view?.finalize(); view = undefined;
      observer?.disconnect(); observer = undefined;
      current = undefined;
      root.replaceChildren();
    }
    async function update(body, authorityKey) {
      if (disposed) return;
      const request = structuredClone(body), ticket = ++generation;
      pending?.abort(); pending = new AbortController();
      const signal = pending.signal;
      clear(); root.setAttribute('aria-busy', 'true');
      root.append(node('p', 'Loading exact retained result…', {role: 'status'}));
      const active = () => !disposed && ticket === generation && !signal.aborted;
      try {
        const [received, base] = await Promise.all([load(request, {signal, authorityKey, export: false}), specification(signal)]);
        if (!active()) return;
        const data = validate(received, request);
        clear();
        const heading = node('h3', 'Retained checkpoint analysis', {tabindex: '-1'});
        const status = node('p', `Frozen validation probe · ${data.metric.support} examples · ${data.metric.units}`, {role: 'status'});
        const chart = node('div', undefined, {role: 'img', 'aria-label': 'Checkpoint curve; exact values and keyboard selection follow.'});
        const buttons = node('div', undefined, {'aria-label': 'Select retained epoch'});
        const choose = sha => {
          if (!active() || sha === request.checkpoint_sha256) return;
          onSelection({checkpoint_sha256: sha});
          void update({...request, checkpoint_sha256: sha, offset: 0}, authorityKey).then(() => root.querySelector('h3')?.focus());
        };
        for (const point of data.curve) {
          const button = node('button', `Epoch ${point.epoch}: ${point.value} · support ${point.support}`, {type: 'button', 'aria-pressed': String(point.checkpoint_sha256 === request.checkpoint_sha256)});
          button.addEventListener('click', () => choose(point.checkpoint_sha256));
          buttons.append(button);
        }
        const filterLabel = node('label', ' Show only errors ');
        const filter = node('input', undefined, {type: 'checkbox'});
        filter.checked = request.errors_only ?? false;
        filter.addEventListener('change', () => void update({...request, errors_only: filter.checked, offset: 0}, authorityKey).then(() => root.querySelector('input')?.focus()));
        filterLabel.prepend(filter);
        const support = node('p', `${data.examples.filtered_support} matching examples of ${data.examples.population_support}; curve statistics retain the full probe population.`);
        const table = node('table');
        table.append(node('caption', 'Frozen examples at the selected checkpoint'));
        const headers = node('tr');
        for (const column of data.columns) headers.append(node('th', column.field, {scope: 'col'}));
        const head = node('thead'); head.append(headers); table.append(head);
        const rows = node('tbody');
        for (const row of data.examples.rows) {
          const tr = node('tr');
          for (const column of data.columns) tr.append(node('td', String(row[column.field])));
          rows.append(tr);
        }
        table.append(rows);
        const navigation = node('div');
        for (const [label, offset] of [['Previous examples', Math.max(0, data.examples.offset - data.examples.limit)], ['Next examples', data.examples.next_offset]]) {
          const button = node('button', label, {type: 'button'});
          button.disabled = offset === null || offset === data.examples.offset;
          button.addEventListener('click', () => void update({...request, offset}, authorityKey)); navigation.append(button);
        }
        const exportButton = node('button', 'Export this page', {type: 'button'});
        exportButton.addEventListener('click', async () => {
          exportButton.disabled = true;
          try {
            const fresh = validate(await load(request, {signal, authorityKey, export: true}), request);
            if (!active()) return;
            const url = URL.createObjectURL(new Blob([JSON.stringify(fresh)], {type: 'application/json'}));
            const link = node('a', undefined, {href: url, download: 'retained-analysis-page.json'});
            root.append(link); link.click(); link.remove(); URL.revokeObjectURL(url);
          } catch (error) {
            if (active()) { clear(); root.append(node('p', 'Retained result access or export failed. Refresh with current access.', {role: 'alert'})); }
          } finally { if (active()) exportButton.disabled = false; }
        });
        const details = node('details'); details.append(node('summary', 'Exact retained provenance'), node('pre', JSON.stringify(data.provenance, null, 2)));
        root.append(heading, status, chart, buttons, filterLabel, support, table, navigation, exportButton, details);
        if (typeof window.vegaEmbed !== 'function' || typeof window.vega?.expressionInterpreter !== 'object') throw Error('Pinned chart assets are unavailable.');
        base.datasets = {curve: data.curve.map(point => ({...point, selected: point.checkpoint_sha256 === request.checkpoint_sha256}))};
        // Data, images and links cannot leave the controlled inline dataset.
        const deny = () => Promise.reject(Error('Chart URL loading is disabled.'));
        const embedded = await window.vegaEmbed(chart, base, {actions: false, defaultStyle: false, tooltip: false, mode: 'vega-lite', renderer: 'svg', ast: true, expr: window.vega.expressionInterpreter, loader: {load: deny, sanitize: deny}});
        if (!active()) { embedded.finalize(); return; }
        view = embedded.view;
        view.addSignalListener('checkpoint_select', (_name, value) => {
          const sha = value?.checkpoint_sha256?.[0];
          if (data.curve.some(point => point.checkpoint_sha256 === sha)) choose(sha);
        });
        observer = new ResizeObserver(() => {
          if (active()) void view?.resize().runAsync().catch(() => { if (active()) { clear(); root.append(node('p', 'Retained chart resize failed.', {role: 'alert'})); } });
        });
        observer.observe(chart);
        current = {request, authorityKey};
      } catch (error) {
        if (active()) {
          clear(); root.append(node('p', String(error.message || 'Retained analysis unavailable.'), {role: 'alert'}));
          root.setAttribute('aria-busy', 'false'); pending.abort();
        }
      } finally { if (active()) root.setAttribute('aria-busy', 'false'); }
    }
    return {
      update,
      resize() { return view?.resize().runAsync(); },
      selection() { return current ? structuredClone(current.request) : null; },
      dispose() { disposed = true; ++generation; pending?.abort(); clear(); root.removeAttribute('aria-busy'); }
    };
  }
  window.WorkspaceRetainedAnalysis = Object.freeze({mount});
})();
