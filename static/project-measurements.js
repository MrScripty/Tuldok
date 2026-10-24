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
    root.innerHTML = '<h2>Retained measurements</h2><p>Compare exact saved scalars and inspect their original cases. Maxima use every matching case; failed and unavailable observations remain counted.</p><div class="actions"><button type="button" id="project-measurements-sources">Load measurement sources</button><button type="button" id="project-measurements-sources-prev" hidden>Previous sources</button><button type="button" id="project-measurements-sources-next" hidden>Next sources</button></div><p id="project-measurements-source-page"></p><form id="project-measurements-source-form"><label>Measurement sources (choose 1–16)<select id="project-measurements-source" multiple size="4"></select></label><button type="button" id="project-measurements-source-all">Select all listed sources</button><button id="project-measurements-load">Load selected sources</button></form><p id="project-measurements-status" role="status" aria-live="polite"></p><div id="project-measurements-context"></div><form id="project-measurements-form" hidden><label>Metric<select id="project-measurements-metric"></select></label><label>Select subjects on this page<select id="project-measurements-subjects" multiple size="4"></select></label><p id="project-measurements-subject-page"></p><div class="actions"><button type="button" id="project-measurements-subjects-all">Select all subjects</button><button type="button" id="project-measurements-subjects-clear">Clear subject selection</button></div><div class="actions"><button type="button" id="project-measurements-subjects-prev" hidden>Previous subjects</button><button type="button" id="project-measurements-subjects-next" hidden>Next subjects</button></div><details><summary>Filter declared attributes</summary><p>Grid density and domain cell counts are separate attributes. Filters use exact recorded values; unknown values must be selected explicitly.</p><div id="project-measurements-filters"></div></details><button id="project-measurements-compare">Compare metric</button></form><section id="project-measurements-results" hidden aria-label="Measurement comparison"><h3 id="project-measurements-heading" tabindex="-1"></h3><p id="project-measurements-counts"></p><div id="project-measurements-chart" role="img" aria-label="Maximum retained value per selected subject; exact values and keyboard inspection follow"></div><div id="project-measurements-maxima"></div><div id="project-measurements-rows"></div><div class="actions"><button type="button" id="project-measurements-prev">Previous observations</button><button type="button" id="project-measurements-next">Next observations</button></div></section><section id="project-measurements-inspection" hidden aria-label="Exact observation and original source"></section>';
    const $ = name => root.querySelector('#project-measurements-' + name);
    let context = null, generation = 0, plotGeneration = 0, pending, busy = false, pendingFocus = false;
    let sources = [], sourceOffset = 0, sourceTotal = 0, selected = null, descriptors = null, metadata = null;
    let subjects = [], subjectOffset = 0, subjectTotal = 0, filters = new Map(), applied = null, query = null, selectedSubjects = new Set();
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
      $('source').disabled ||= !sources.length; $('source-all').disabled ||= !sources.length || sources.length > 16;
      $('load').disabled ||= !$('source').selectedOptions.length || $('source').selectedOptions.length > 16;
      $('subjects-prev').hidden = subjectOffset === 0; $('subjects-next').hidden = subjectOffset + 40 >= subjectTotal;
      $('compare').disabled ||= !metadata || !selectedSubjects.size;
      $('subjects-all').disabled ||= !metadata; $('subjects-clear').disabled ||= !metadata;
      $('prev').disabled ||= !query || query.offset === 0;
      $('next').disabled ||= !query || query.offset + query.rows.length >= query.total;
      root.setAttribute('aria-busy', String(busy));
    }
    function clearSource() {
      selected = descriptors = metadata = null; subjects = []; selectedSubjects.clear(); subjectOffset = subjectTotal = 0; filters.clear();
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
        for (const [index, item] of sources.entries()) {
          const option = node('option', item.title + ' · ' + item.id.slice(0, 12) + (item.availability?.state === 'missing' ? ' · missing packet' : ''));
          option.value = sourceKey(item); option.selected = index === 0; $('source').append(option);
        }
        $('source-page').textContent = `${sources.length ? offset + 1 : 0}–${offset + sources.length} of ${sourceTotal} sources`;
        $('status').textContent = sources.length ? 'Choose compatible sources and load their exact retained metadata.' : 'No retained measurement sources in this project.';
        return $('source');
      });
    }
    const same = (left, right) => {
      if (Object.is(left, right)) return true;
      if (!left || !right || typeof left !== 'object' || typeof right !== 'object' || Array.isArray(left) !== Array.isArray(right)) return false;
      const keys = Object.keys(left);
      return keys.length === Object.keys(right).length && keys.every(key => Object.hasOwn(right, key) && same(left[key], right[key]));
    };
    const locatorKey = value => value.origin_catalog_id + '.' + value.packet_sha256;
    const selection = () => ({sources:selected.map(item => ({origin_catalog_id:item.origin_catalog_id, packet_sha256:item.id}))});
    function checkComparison(response) {
      if (!response || !Array.isArray(response.sources) || response.sources.length !== selected.length
          || new TextEncoder().encode(JSON.stringify(response)).length > 256 * 1024) throw Error('Comparison differs from selected sources.');
      for (const [index, source] of response.sources.entries()) {
        const expected = selected[index];
        if (source.origin_catalog_id !== expected.origin_catalog_id || source.id !== expected.id
            || source.title !== expected.title || source.blob?.sha256 !== source.id || source.blob.bytes !== expected.blob.bytes
            || source.source?.measured_sha256 !== source.id) throw Error('Comparison source identity changed.');
      }
      if (descriptors && !same(descriptors, response.sources)) throw Error('Original comparison capture facts changed.');
      const value = response.value, keys = selected.map(sourceKey);
      if (value?.format !== 'retained_measurement_comparison_v1' || !hash(value.case_population_sha256)
          || !Array.isArray(value.subjects) || !value.subjects.length || value.subjects.length > 256
          || !natural(value.case_count) || !value.case_count || !natural(value.observation_count)
          || !Array.isArray(value.metrics) || !value.metrics.length || value.metrics.length > 32
          || !Array.isArray(value.dimensions) || value.dimensions.length > 32
          || value.observation_count !== value.subjects.length * value.case_count * value.metrics.length
          || locatorKey(value.definition_source) !== keys[0]
          || value.subjects.some(item => !identity(item.id) || typeof item.label !== 'string' || !keys.includes(locatorKey(item.source)))
          || new Set(value.subjects.map(item => item.id)).size !== value.subjects.length) throw Error('Invalid comparison metadata.');
      if (metadata && ['scope','scope_definition','dimensions','metrics','definition_source','case_population_sha256','case_count','observation_count','subjects'].some(key => !same(value[key], metadata[key]))) throw Error('Comparison population changed.');
      return value;
    }
    function checkRead(response, source) {
      const original = descriptors.find(item => sourceKey(item) === locatorKey(source));
      if (!original || response?.source?.origin_catalog_id !== source.origin_catalog_id || response.source.id !== source.packet_sha256
          || response.source.blob?.sha256 !== source.packet_sha256 || !same(response.source, original)
          || new TextEncoder().encode(JSON.stringify(response)).length > 256 * 1024) throw Error('Observation differs from its original packet.');
      return response.value;
    }
    function subjectPage(offset) {
      if (!metadata || !natural(offset) || offset > subjectTotal) throw Error('Invalid comparison subject page.');
      subjectOffset = offset; $('subjects').replaceChildren();
      const items = subjects.slice(offset, offset + 40);
      for (const item of items) {
        const option = node('option', item.label + ' · ' + item.id); option.value = item.id;
        option.selected = selectedSubjects.has(item.id); $('subjects').append(option);
      }
      subjectSelectionStatus();
      return $('subjects');
    }
    function subjectSelectionStatus() {
      const count = Math.min(40, subjectTotal - subjectOffset);
      $('subject-page').textContent = `Subjects ${count ? subjectOffset + 1 : 0}–${subjectOffset + count} of ${subjectTotal}. ${selectedSubjects.size} selected across all pages; selection is retained when paging.`;
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
    async function inspect(observation_id, source) {
      clearInspection();
      return perform(async(active, signal) => {
        const value = checkRead(await read('measurement_inspect', {...source, observation_id}, signal), source); if (!active()) return;
        if (value.packet_sha256 !== source.packet_sha256 || value.observation?.id !== observation_id
            || value.observation.metric_id !== applied?.metric_id || !applied.subject_ids.includes(value.observation.subject_id)
            || !same(subjects.find(item => item.id === value.observation.subject_id)?.source, source)) throw Error('Observation differs from the selected comparison.');
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
      if (!value || value.metric?.id !== request.metric_id
          || !same(value.metric, metadata.metrics.find(metric => metric.id === request.metric_id))
          || JSON.stringify(value.subject_ids) !== JSON.stringify(request.subject_ids)
          || !value.filters || Object.keys(value.filters).length !== Object.keys(request.filters).length
          || Object.entries(request.filters).some(([key, wanted]) => !Object.hasOwn(value.filters, key) || value.filters[key] !== wanted)
          || !Array.isArray(value.summary) || value.summary.length !== request.subject_ids.length || value.sampling !== 'none') throw Error('Measurement comparison differs from its requested selection.');
      page(value, request.offset, request.limit, value.rows);
      if (value.summary.reduce((count, summary) => count + summary.count, 0) !== value.total) throw Error('Comparison denominator differs from its complete summaries.');
      const maxima = table('Maximum over all matching cases, including every observation status', ['Subject / execution attributes','Maximum','Measured','Failed','Unsupported','Unavailable']);
      const points = [], inspections = new Map();
      for (const [index, summary] of value.summary.entries()) {
        if (summary.subject_id !== request.subject_ids[index] || !natural(summary.count) || STATES.some(state => !natural(summary.states?.[state]))
            || STATES.reduce((sum, state) => sum + summary.states[state], 0) !== summary.count
            || (summary.maximum === null) !== (summary.states.measured === 0)) throw Error('Invalid complete measurement summary.');
        const subject = subjects.find(item => item.id === summary.subject_id); if (!subject || !same(subject.source, summary.source)) throw Error('Subject differs from its original comparison packet.');
        const row = node('tr'), label = node('td'); label.append(node('strong', subject.label), attributes('Execution attributes', subject.dimensions));
        const maximum = node('td');
        if (summary.maximum === null) maximum.textContent = 'No measured value';
        else {
          const point = summary.maximum;
          if (!finite(point.value) || !identity(point.id) || !identity(point.case_id)) throw Error('Invalid retained maximum.');
          maximum.append(button(display(point.value) + ' · inspect maximum for ' + subject.label, () => void inspect(point.id, summary.source)));
          const token = JSON.stringify([summary.source.origin_catalog_id, summary.source.packet_sha256, point.id]);
          inspections.set(token, {id:point.id, source:summary.source});
          points.push({subject_id:subject.id, value:point.value, observation_id:token});
        }
        row.append(label, maximum, ...STATES.map(state => node('td', String(summary.states[state])))); maxima.body.append(row);
      }
      const observations = table('Exact observations on this page', ['Subject','Case','Value / status','Inspection']);
      for (const observation of value.rows) {
        if (!request.subject_ids.includes(observation.subject_id) || observation.metric_id !== request.metric_id || !identity(observation.id)
            || !STATES.includes(observation.state) || (observation.state === 'measured' ? !finite(observation.value) : observation.value !== null)) throw Error('Invalid retained observation row.');
        const subject = subjects.find(item => item.id === observation.subject_id), row = node('tr'), detail = node('td');
        if (!subject || !same(subject.source, observation.source)) throw Error('Observation belongs to another packet.');
        detail.append(button('Inspect ' + observation.id, () => void inspect(observation.id, observation.source)), attributes('Case and execution attributes', observation.dimensions));
        row.append(node('td', subject.label), node('td', observation.case_id), node('td', observation.value === null ? observation.state + ': ' + observation.reason : display(observation.value)), detail); observations.body.append(row);
      }
      query = value; applied = structuredClone(request); $('results').hidden = false;
      $('heading').textContent = value.metric.label + ' · ' + value.metric.units;
      $('counts').textContent = `${request.subject_ids.length} selected subjects of ${subjectTotal}; ${value.total} matching observations. Showing ${value.rows.length ? value.offset + 1 : 0}–${value.offset + value.rows.length}. Maxima use every matching case, independent of this page.`;
      $('maxima').replaceChildren(maxima.result); $('rows').replaceChildren(observations.result);
      const plotTicket = ++plotGeneration;
      if (points.length) await renderer.render({maxima:points}, {signal,
        isCurrent: () => context?.enabled && context.key === authority && plotTicket === plotGeneration,
        onSignal:{measurement_select: selection => { const id = selection?.observation_id?.[0]; const original = inspections.get(id); if (original) void inspect(original.id, original.source); }}});
      else { renderer.clear(); $('chart').append(node('p', 'No measured values for this selection. Missing and failed observations remain counted below.')); }
      if (active()) { $('heading').focus(); $('status').textContent = 'Exact retained comparison. Metric and scope definitions are available above.'; }
    }
    function compare(offset = 0, saved = null) {
      return perform(async(active, signal, authority) => {
        const request = saved ? {...saved, offset} : {metric_id:$('metric').value,
          subject_ids:subjects.filter(item => selectedSubjects.has(item.id)).map(item => item.id), filters:filterValues(), offset, limit:50};
        if (!request.subject_ids.length) throw Error('Choose at least one subject.');
        clearResults();
        const value = checkComparison(await read('measurement_compare', {...selection(), ...request}, signal)).query; if (!active()) return;
        await showQuery(value, request, active, signal, authority);
      });
    }
    $('sources').onclick = () => void loadSources();
    $('sources-prev').onclick = () => void loadSources(Math.max(0, sourceOffset - 40));
    $('sources-next').onclick = () => void loadSources(sourceOffset + 40);
    $('source').onchange = () => { invalidate(); clearSource(); $('status').textContent = 'Load the selected compatible sources.'; controls(); };
    $('source-form').onsubmit = event => {
      event.preventDefault();
      void perform(async(active, signal) => {
        const chosen = [...$('source').selectedOptions].map(option => sources.find(item => sourceKey(item) === option.value));
        clearSource(); selected = chosen;
        if (!selected.length || selected.length > 16 || selected.some(item => !item)) throw Error('Choose 1 through 16 retained sources.');
        const response = await read('measurement_compare', selection(), signal); if (!active()) return;
        metadata = checkComparison(response); descriptors = response.sources;
        if (metadata.query !== null) throw Error('Metadata reply unexpectedly contains a query.');
        subjects = metadata.subjects; subjectTotal = subjects.length; selectedSubjects = new Set(subjects.map(item => item.id));
        $('context').append(node('h3', `Comparison of ${selected.length} retained sources`), node('p', metadata.scope.label + ' · population: ' + metadata.scope.population),
          node('p', typeof metadata.scope_definition.task === 'string' ? metadata.scope_definition.task : 'Interpret results using the retained scope definition.'),
          jsonDetails('Exact compatible scope, metric definitions and original packet sources', {metadata, sources:descriptors}));
        for (const metric of metadata.metrics) { const option = node('option', metric.label + ' · ' + metric.units); option.value = metric.id; $('metric').append(option); }
        dimensions(); subjectPage(0); if (!active()) return;
        $('form').hidden = false; $('status').textContent = 'Choose a metric, subjects and optional exact attribute filters.'; return $('metric');
      });
    };
    $('source-all').onclick = () => {
      for (const option of $('source').options) option.selected = true;
      $('source').onchange();
    };
    $('metric').onchange = invalidate;
    $('subjects').onchange = () => {
      for (const option of $('subjects').options) {
        if (option.selected) selectedSubjects.add(option.value); else selectedSubjects.delete(option.value);
      }
      invalidate(); subjectSelectionStatus(); controls();
    };
    for (const [name, all] of [['subjects-all',true],['subjects-clear',false]]) $(name).onclick = () => {
      selectedSubjects = new Set(all ? subjects.map(item => item.id) : []);
      invalidate(); subjectPage(subjectOffset); controls();
    };
    for (const [name, direction] of [['subjects-prev',-1],['subjects-next',1]]) $(name).onclick = () => {
      clearResults(); void perform(() => subjectPage(subjectOffset + direction * 40));
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
