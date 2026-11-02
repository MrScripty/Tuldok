/* Native scalar selection/inspection. The host owns current access and reads. */
(() => {
  'use strict';
  const STATES = ['measured', 'failed', 'unsupported', 'unavailable'];
  const hash = value => typeof value === 'string' && /^[a-f0-9]{64}$/.test(value);
  const identity = value => typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(value);
  const natural = value => Number.isSafeInteger(value) && value >= 0;
  const finite = value => typeof value === 'number' && Number.isFinite(value);
  const display = value => value === null ? 'Unknown' : Object.is(value, -0) ? '-0' : String(value);
  const node = (tag, text) => { const value = document.createElement(tag); if (text !== undefined) value.textContent = text; return value; };
  const button = (text, invoke) => { const value = node('button', text); value.type = 'button'; value.onclick = invoke; return value; };
  const sourceKey = source => source.origin_catalog_id + '.' + source.id;
  const spec = {path: '/static/retained-measurement-maxima.vl.json', sha256: 'c9440bbe90d215afb15d47a5f12c5aefcb20dc1d3ddba19d72fe5ba3adb1cd92'};
  function page(value, offset, limit, items) {
    if (!value || value.offset !== offset || value.limit !== limit || !natural(value.total) || !Array.isArray(items)
        || items.length !== Math.min(limit, Math.max(0, value.total - offset))) throw Error('Measurement page differs from the selected continuation.');
  }
  function jsonDetails(title, value, open = false) {
    const details = node('details'); details.open = open;
    details.append(node('summary', title), node('pre', JSON.stringify(value, null, 2))); return details;
  }
  window.ProjectMeasurements = function({root, read, onContextFocusLost = () => {}}) {
    root.innerHTML = '<h2>Retained measurements</h2><p>Compare exact saved scalars and inspect their original cases. Maxima use every matching case; failed and unavailable observations remain counted.</p><div class="actions"><button type="button" id="project-measurements-sources">Load measurement sources</button><button type="button" id="project-measurements-sources-prev" hidden>Previous sources</button><button type="button" id="project-measurements-sources-next" hidden>Next sources</button></div><p id="project-measurements-source-page"></p><form id="project-measurements-source-form"><label>Measurement source<select id="project-measurements-source"></select></label><button id="project-measurements-load">Load source</button></form><p id="project-measurements-status" role="status" aria-live="polite"></p><div id="project-measurements-context"></div><form id="project-measurements-form" hidden><label>Metric<select id="project-measurements-metric"></select></label><label>Select subjects on this page<select id="project-measurements-subjects" multiple size="4"></select></label><p id="project-measurements-subject-page"></p><div class="actions"><button type="button" id="project-measurements-subjects-prev" hidden>Previous subjects</button><button type="button" id="project-measurements-subjects-next" hidden>Next subjects</button></div><details><summary>Filter declared attributes</summary><p>Grid density and domain cell counts are separate attributes. Filters use exact recorded values; unknown values must be selected explicitly.</p><div id="project-measurements-filters"></div></details><button id="project-measurements-compare">Compare metric</button></form><section id="project-measurements-results" hidden aria-label="Measurement comparison"><h3 id="project-measurements-heading" tabindex="-1"></h3><p id="project-measurements-counts"></p><div id="project-measurements-chart" role="img" aria-label="Maximum retained value per selected subject; exact values and keyboard inspection follow"></div><div id="project-measurements-maxima"></div><div id="project-measurements-rows"></div><div class="actions"><button type="button" id="project-measurements-prev">Previous observations</button><button type="button" id="project-measurements-next">Next observations</button></div></section><section id="project-measurements-inspection" hidden aria-label="Exact observation and original source"></section>';
    const $ = name => root.querySelector('#project-measurements-' + name);
    let context = null, generation = 0, plotGeneration = 0, pending, busy = false, pendingFocus = false;
    let sources = [], sourceOffset = 0, sourceTotal = 0, selected = null, descriptor = null, metadata = null;
    let subjects = [], subjectOffset = 0, subjectTotal = 0, filters = new Map(), applied = null, query = null;
    const renderer = window.RetainedChart.mount($('chart'), spec, {onError: error => {
      const ownsFocus = root.contains(document.activeElement); clearResults(); $('status').textContent = error.message; controls();
      if (ownsFocus) $('compare').focus();
    }});
    function clearInspection() { $('inspection').replaceChildren(); $('inspection').hidden = true; }
    function clearResults() {
      ++plotGeneration; renderer.clear(); query = null; applied = null;
      $('results').hidden = true; $('maxima').replaceChildren(); $('rows').replaceChildren(); clearInspection();
    }
    function controls() {
      for (const control of root.querySelectorAll('input,select,button')) control.disabled = !context?.enabled || busy;
      $('sources-prev').hidden = sourceOffset === 0; $('sources-next').hidden = sourceOffset + sources.length >= sourceTotal;
      $('source').disabled ||= !sources.length; $('load').disabled ||= !$('source').value;
      $('subjects-prev').hidden = subjectOffset === 0; $('subjects-next').hidden = subjectOffset + subjects.length >= subjectTotal;
      $('compare').disabled ||= !metadata || !$('subjects').selectedOptions.length;
      $('prev').disabled ||= !query || query.offset === 0;
      $('next').disabled ||= !query || query.offset + query.rows.length >= query.total;
      root.setAttribute('aria-busy', String(busy));
    }
    function clearSource() {
      selected = descriptor = metadata = null; subjects = []; subjectOffset = subjectTotal = 0; filters.clear();
      $('form').hidden = true; $('context').replaceChildren(); $('filters').replaceChildren();
      $('metric').replaceChildren(); $('subjects').replaceChildren(); clearResults();
    }
    function reset() {
      ++generation; pending?.abort(); pending = undefined; busy = false; pendingFocus = false;
      clearSource(); sources = []; sourceOffset = sourceTotal = 0;
      $('source').replaceChildren(); $('source-page').textContent = ''; $('status').textContent = ''; controls();
    }
    const ownsFocus = () => root.contains(document.activeElement)
      || busy && pendingFocus && document.activeElement === document.body;
    async function perform(work) {
      if (!context?.enabled || busy) return;
      const ticket = ++generation, authority = context.key;
      pending = new AbortController(); const signal = pending.signal;
      const active = () => ticket === generation && context?.key === authority && context.enabled && !signal.aborted;
      pendingFocus = root.contains(document.activeElement); busy = true; controls();
      let focus;
      try { focus = await work(active, signal, authority); }
      catch (error) {
        if (active()) {
          const ownedFocus = ownsFocus(); reset(); $('status').textContent = error.message;
          if (ownedFocus) $('sources').focus();
        }
      } finally { if (active()) { busy = false; pending = undefined; pendingFocus = false; controls(); focus?.focus(); } }
    }
    async function loadSources(offset = 0) {
      clearSource();
      return perform(async(active, signal) => {
        const value = await read('measurement_sources', {offset, limit: 40}, signal); if (!active()) return;
        page(value, offset, 40, value.items);
        const seen = new Set();
        for (const item of value.items) {
          const key = sourceKey(item);
          if (!hash(item.id) || !/^[a-f0-9]{32}$/.test(item.origin_catalog_id) || seen.has(key)
              || item.blob?.sha256 !== item.id || typeof item.title !== 'string') throw Error('Invalid retained measurement source.');
          seen.add(key);
        }
        sources = value.items; sourceOffset = offset; sourceTotal = value.total; $('source').replaceChildren();
        for (const item of sources) {
          const option = node('option', item.title + ' · ' + item.id.slice(0, 12) + (item.availability?.state === 'missing' ? ' · missing packet' : ''));
          option.value = sourceKey(item); $('source').append(option);
        }
        $('source-page').textContent = `${sources.length ? offset + 1 : 0}–${offset + sources.length} of ${sourceTotal} sources`;
        $('status').textContent = sources.length ? 'Choose a source and load its exact retained metadata.' : 'No retained measurement sources in this project.';
        return $('source');
      });
    }
    function checkRead(value, source = selected) {
      if (!value || value.source?.origin_catalog_id !== source?.origin_catalog_id || value.source?.id !== source?.id
          || value.source.blob?.sha256 !== source.id || value.source.source?.measured_sha256 !== source.id
          || descriptor && (value.source.blob.bytes !== descriptor.blob.bytes || value.source.title !== descriptor.title)
          || new TextEncoder().encode(JSON.stringify(value)).length > 256 * 1024) throw Error('Measurement reply differs from the selected packet.');
      return value.value;
    }
    const selection = () => ({origin_catalog_id: selected.origin_catalog_id, packet_sha256: selected.id});
    async function subjectPage(offset, active, signal) {
      const value = checkRead(await read('measurement_subjects', {...selection(), offset, limit: 40}, signal)); if (!active()) return;
      page(value, offset, 40, value.items);
      if (value.total !== metadata.subject_count) throw Error('Subject page differs from the retained packet population.');
      if (value.items.some(item => !identity(item.id) || typeof item.label !== 'string')
          || new Set(value.items.map(item => item.id)).size !== value.items.length) throw Error('Invalid retained subjects.');
      subjects = value.items; subjectOffset = offset; subjectTotal = value.total; $('subjects').replaceChildren();
      for (const item of subjects) { const option = node('option', item.label + ' · ' + item.id); option.value = item.id; option.selected = true; $('subjects').append(option); }
      $('subject-page').textContent = `Subjects ${subjects.length ? offset + 1 : 0}–${offset + subjects.length} of ${subjectTotal}. Only explicitly selected subjects on this page will be compared.`;
      return $('subjects');
    }
    function dimensions() {
      filters.clear(); $('filters').replaceChildren();
      for (const [index, dimension] of metadata.dimensions.entries()) {
        const field = node('fieldset'), legend = node('legend', `${dimension.label}${dimension.units ? ' · ' + dimension.units : ''} (${dimension.scope})`);
        const mode = node('select'); mode.id = 'project-measurements-filter-mode-' + index;
        for (const [value, label] of [['any','Any recorded value'],['value','Exact value'],['unknown','Unknown only']]) { const option = node('option', label); option.value = value; mode.append(option); }
        const label = node('label', 'Match'); label.htmlFor = mode.id; label.append(mode);
        let input;
        if (dimension.type === 'boolean') { input = node('select'); for (const value of ['true','false']) { const option = node('option', value); option.value = value; input.append(option); } }
        else { input = node('input'); input.type = dimension.type === 'string' ? 'text' : 'number'; input.maxLength = 256; input.step = dimension.type === 'integer' ? '1' : 'any'; }
        input.id = 'project-measurements-filter-value-' + index;
        const valueLabel = node('label', 'Exact recorded value'); valueLabel.htmlFor = input.id; valueLabel.append(input);
        field.append(legend, label, valueLabel); $('filters').append(field); filters.set(dimension.id, {dimension, mode, input});
        mode.onchange = invalidate; input.oninput = invalidate;
      }
    }
    function filterValues() {
      const values = {};
      for (const [id, {dimension, mode, input}] of filters) {
        if (mode.value === 'any') continue;
        if (mode.value === 'unknown') { values[id] = null; continue; }
        if (mode.value !== 'value' || !input.value.length) throw Error('Enter an exact filter value or choose Any recorded value.');
        const value = dimension.type === 'boolean' ? input.value === 'true' : dimension.type === 'string' ? input.value : Number(input.value);
        if ((dimension.type === 'number' && !finite(value)) || (dimension.type === 'integer' && !Number.isSafeInteger(value))) throw Error('Filter values must match the declared numeric type.');
        values[id] = value;
      }
      return values;
    }
    function invalidate() {
      ++generation; pending?.abort(); pending = undefined; busy = false; clearResults();
      $('status').textContent = 'Selection edited. Compare metric to apply it.'; controls();
    }
    function attributes(title, values) {
      const details = node('details'); details.append(node('summary', title));
      const list = node('dl');
      for (const [key, value] of Object.entries(values)) {
        const dimension = metadata.dimensions.find(item => item.id === key);
        list.append(node('dt', dimension?.label ?? key), node('dd', display(value) + (dimension?.units ? ' ' + dimension.units : '')));
      }
      details.append(list); return details;
    }
    function table(caption, headings) {
      const result = node('table'), row = node('tr'), head = node('thead'), body = node('tbody');
      for (const text of headings) { const cell = node('th', text); cell.scope = 'col'; row.append(cell); }
      head.append(row); result.append(node('caption', caption), head, body); return {result, body};
    }
    async function inspect(observation_id) {
      clearInspection();
      return perform(async(active, signal) => {
        const value = checkRead(await read('measurement_inspect', {...selection(), observation_id}, signal)); if (!active()) return;
        if (value.packet_sha256 !== selected.id || value.observation?.id !== observation_id
            || value.observation.metric_id !== applied?.metric_id || !applied.subject_ids.includes(value.observation.subject_id)) throw Error('Observation differs from the selected comparison.');
        const heading = node('h3', value.subject.label + ' · ' + value.case.id); heading.tabIndex = -1;
        const observation = value.observation;
        $('inspection').append(heading, node('p', `${value.metric.label} · ${value.metric.units} · ${observation.state} · ${observation.value === null ? observation.reason : display(observation.value)}`),
          attributes('Case attributes, including grid density and domain cell counts', value.case.dimensions),
          attributes('Subject execution attributes', value.subject.dimensions), attributes('Observation work attributes', observation.dimensions),
          jsonDetails('Original case evidence', value.case_evidence, true), jsonDetails('Original scalar evidence', value.scalar_evidence, true),
          jsonDetails('Exact observation, metric, source and scope', value));
        $('inspection').hidden = false; heading.focus(); $('status').textContent = 'Exact retained observation and original source evidence.';
      });
    }
    async function showQuery(value, request, active, signal, authority) {
      if (value.packet_sha256 !== selected.id || value.metric?.id !== request.metric_id
          || JSON.stringify(value.subject_ids) !== JSON.stringify(request.subject_ids)
          || !value.filters || Object.keys(value.filters).length !== Object.keys(request.filters).length
          || Object.entries(request.filters).some(([key, wanted]) => !Object.hasOwn(value.filters, key) || value.filters[key] !== wanted)
          || !Array.isArray(value.summary) || value.summary.length !== request.subject_ids.length || value.sampling !== 'none') throw Error('Measurement comparison differs from its requested selection.');
      page(value, request.offset, request.limit, value.rows);
      const maxima = table('Maximum over all matching cases, including every observation status', ['Subject / execution attributes','Maximum','Measured','Failed','Unsupported','Unavailable']);
      const points = [];
      for (const [index, summary] of value.summary.entries()) {
        if (summary.subject_id !== request.subject_ids[index] || !natural(summary.count) || STATES.some(state => !natural(summary.states?.[state]))
            || STATES.reduce((sum, state) => sum + summary.states[state], 0) !== summary.count
            || (summary.maximum === null) !== (summary.states.measured === 0)) throw Error('Invalid complete measurement summary.');
        const subject = subjects.find(item => item.id === summary.subject_id); if (!subject) throw Error('Subject is outside the selected page.');
        const row = node('tr'), label = node('td'); label.append(node('strong', subject.label), attributes('Execution attributes', subject.dimensions));
        const maximum = node('td');
        if (summary.maximum === null) maximum.textContent = 'No measured value';
        else {
          const point = summary.maximum;
          if (!finite(point.value) || !identity(point.id) || !identity(point.case_id)) throw Error('Invalid retained maximum.');
          maximum.append(button(display(point.value) + ' · inspect maximum for ' + subject.label, () => void inspect(point.id)));
          points.push({subject_id:subject.id, value:point.value, observation_id:point.id});
        }
        row.append(label, maximum, ...STATES.map(state => node('td', String(summary.states[state])))); maxima.body.append(row);
      }
      const observations = table('Exact observations on this page', ['Subject','Case','Value / status','Inspection']);
      for (const observation of value.rows) {
        if (!request.subject_ids.includes(observation.subject_id) || observation.metric_id !== request.metric_id || !identity(observation.id)
            || !STATES.includes(observation.state) || (observation.state === 'measured' ? !finite(observation.value) : observation.value !== null)) throw Error('Invalid retained observation row.');
        const subject = subjects.find(item => item.id === observation.subject_id), row = node('tr'), detail = node('td');
        detail.append(button('Inspect ' + observation.id, () => void inspect(observation.id)), attributes('Case and execution attributes', observation.dimensions));
        row.append(node('td', subject.label), node('td', observation.case_id), node('td', observation.value === null ? observation.state + ': ' + observation.reason : display(observation.value)), detail); observations.body.append(row);
      }
      query = value; applied = structuredClone(request); $('results').hidden = false;
      $('heading').textContent = value.metric.label + ' · ' + value.metric.units;
      $('counts').textContent = `${request.subject_ids.length} selected subjects of ${subjectTotal}; ${value.total} matching observations. Showing ${value.rows.length ? value.offset + 1 : 0}–${value.offset + value.rows.length}. Maxima use every matching case, independent of this page.`;
      $('maxima').replaceChildren(maxima.result); $('rows').replaceChildren(observations.result);
      const plotTicket = ++plotGeneration;
      if (points.length) await renderer.render({maxima:points}, {signal,
        isCurrent: () => context?.enabled && context.key === authority && plotTicket === plotGeneration,
        onSignal:{measurement_select: selection => { const id = selection?.observation_id?.[0]; if (points.some(point => point.observation_id === id)) void inspect(id); }}});
      else { renderer.clear(); $('chart').append(node('p', 'No measured values for this selection. Missing and failed observations remain counted below.')); }
      if (active()) { $('heading').focus(); $('status').textContent = 'Exact retained comparison. Metric and scope definitions are available above.'; }
    }
    function compare(offset = 0, saved = null) {
      return perform(async(active, signal, authority) => {
        const request = saved ? {...saved, offset} : {metric_id:$('metric').value,
          subject_ids:[...$('subjects').selectedOptions].map(option => option.value), filters:filterValues(), offset, limit:50};
        if (!request.subject_ids.length) throw Error('Choose at least one subject.');
        clearResults();
        const value = checkRead(await read('measurement_query', {...selection(), ...request}, signal)); if (!active()) return;
        await showQuery(value, request, active, signal, authority);
      });
    }
    $('sources').onclick = () => void loadSources();
    $('sources-prev').onclick = () => void loadSources(Math.max(0, sourceOffset - 40));
    $('sources-next').onclick = () => void loadSources(sourceOffset + 40);
    $('source').onchange = () => { invalidate(); clearSource(); controls(); };
    $('source-form').onsubmit = event => {
      event.preventDefault();
      void perform(async(active, signal) => {
        const chosen = sources.find(source => sourceKey(source) === $('source').value); clearSource(); selected = chosen;
        if (!selected) throw Error('Choose a retained measurement source.');
        const response = await read('measurement_metadata', selection(), signal); if (!active()) return;
        metadata = checkRead(response); descriptor = response.source;
        if (metadata.packet_sha256 !== selected.id || metadata.title !== selected.title || !Array.isArray(metadata.metrics) || metadata.metrics.length > 32
            || !Array.isArray(metadata.dimensions) || metadata.dimensions.length > 32) throw Error('Invalid exact measurement metadata.');
        $('context').append(node('h3', metadata.title), node('p', metadata.scope.label + ' · population: ' + metadata.scope.population),
          node('p', typeof metadata.scope_definition.task === 'string' ? metadata.scope_definition.task : 'Interpret results using the retained scope definition.'),
          jsonDetails('Exact scope, metric definitions and packet source', {metadata, source:descriptor}));
        for (const metric of metadata.metrics) { const option = node('option', metric.label + ' · ' + metric.units); option.value = metric.id; $('metric').append(option); }
        dimensions(); await subjectPage(0, active, signal); if (!active()) return;
        $('form').hidden = false; $('status').textContent = 'Choose a metric, subjects and optional exact attribute filters.'; return $('metric');
      });
    };
    $('metric').onchange = invalidate; $('subjects').onchange = invalidate;
    for (const [name, direction] of [['subjects-prev',-1],['subjects-next',1]]) $(name).onclick = () => {
      clearResults(); void perform((active, signal) => subjectPage(subjectOffset + direction * 40, active, signal));
    };
    $('form').onsubmit = event => { event.preventDefault(); void compare(); };
    $('prev').onclick = () => void compare(Math.max(0, query.offset - query.limit), applied);
    $('next').onclick = () => void compare(query.offset + query.limit, applied);
    controls();
    return {setContext(value) {
      if (value.key !== context?.key || context?.enabled && !value.enabled) { const ownedFocus = ownsFocus(); context = value; reset(); if (ownedFocus) onContextFocusLost(); }
      else context = value;
      root.hidden = !value.enabled; controls();
    }, clear() { context = null; reset(); root.hidden = true; }};
  };
})();
