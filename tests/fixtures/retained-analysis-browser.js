'use strict';
window.fixtureRequests = [];
window.fixtureMode = 'normal';
window.fixturePending = [];
window.fixtureSelections = [];
window.fixtureCsp = [];
window.fixtureSpecMode = 'normal';
const originalFetch = window.fetch.bind(window);
window.fetch = (url, options) => {
  if (url === '/static/retained-checkpoint-curve.vl.json' && window.fixtureSpecMode !== 'normal') {
    return Promise.resolve(new Response(window.fixtureSpecMode === 'oversized' ? ' '.repeat(16385) : '{"data":{"url":"https://example.invalid/private"}}'));
  }
  return originalFetch(url, options);
};
document.addEventListener('securitypolicyviolation', event => window.fixtureCsp.push(event.violatedDirective));
const cp = ['b'.repeat(64), 'c'.repeat(64)];
window.fixtureRequest = {query_id: 'retained_checkpoint_examples', query_version: 1, run_id: 'a'.repeat(32), evaluation_sha256: 'd'.repeat(64), checkpoint_sha256: cp[0], metric_id: 'accuracy', metric_definition_sha256: 'e'.repeat(64), limit: 1, offset: 0};
function response(request) {
  const ordinal = request.errors_only ? 1 : (request.offset ?? 0);
  const count = request.errors_only ? 1 : 2;
  const row = {example_id: (request.checkpoint_sha256 === cp[0] ? 'frozen-example-first' : 'frozen-example-second') + '-' + ordinal, ordinal, truth_index: ordinal, predicted_index: 0, confidence: ordinal === 0 ? .875 : .75, error: ordinal !== 0};
  row.frozen_reference = {id: row.example_id, revision: 3};
  return {state: 'verified', query_id: 'retained_checkpoint_examples', query_version: 1, mode: 'frozen', provenance: {catalog_id: 'renderer-fixture', run_id: request.run_id, evaluation_sha256: request.evaluation_sha256, checkpoint_sha256: request.checkpoint_sha256, metric_definition_sha256: request.metric_definition_sha256, population_sha256: '1'.repeat(64), probe_sha256: '2'.repeat(64), data_sha256: '3'.repeat(64), producer: {catalog_id: 'renderer-fixture', run_id: request.run_id, material_sha256: '4'.repeat(64), adapter_sha256: '5'.repeat(64)}}, metric: {id: 'accuracy', units: 'dimensionless', support: 2, definition: {id: 'accuracy', split: 'validation', units: 'dimensionless', population_sha256: '1'.repeat(64)}}, curve: [{checkpoint_sha256: cp[0], epoch: 1, value: .125, support: 2}, {checkpoint_sha256: cp[1], epoch: 2, value: .375, support: 2}], columns: ['example_id', 'truth_index', 'predicted_index', 'confidence', 'error'].map((field, index) => ({field, type: ['string', 'integer', 'integer', 'number', 'boolean'][index], units: field === 'confidence' ? 'dimensionless' : null})), examples: {rows: request.offset >= count ? [] : [row], population_support: 2, filtered_support: count, offset: request.offset ?? 0, limit: request.limit ?? 50, next_offset: (request.offset ?? 0) + 1 < count ? (request.offset ?? 0) + 1 : null, filters: {errors_only: request.errors_only ?? false}}, sampling: {method: 'none', population: 'frozen_validation_probe'}, selection_sha256: 'f'.repeat(64)};
}
async function load(request, options) {
  window.fixtureRequests.push({request, exported: options.export, aborted: () => options.signal.aborted});
  if (window.fixtureMode === 'revoked') throw Error('Credential is unavailable, expired or revoked.');
  if (window.fixtureMode === 'stale') return new Promise(resolve => window.fixturePending.push(() => resolve(response(request))));
  const result = response(request);
  if (window.fixtureMode === 'malformed') result.spec = {data: {url: 'https://example.invalid/private'}};
  if (window.fixtureMode === 'oversized') result.curve = Array(129).fill(result.curve[0]);
  if (window.fixtureMode === 'support-mismatch') result.curve[0].support = 999;
  if (window.fixtureMode === 'ordinal-mismatch') result.examples.rows[0].ordinal = 999;
  if (window.fixtureMode === 'count-mismatch') result.examples.filtered_support = 0;
  if (window.fixtureMode === 'missing-provenance') delete result.provenance.probe_sha256;
  if (window.fixtureMode === 'missing-definition') delete result.metric.definition;
  if (window.fixtureMode === 'missing-column-type') delete result.columns[0].type;
  return result;
}
window.fixtureAdapter = window.WorkspaceRetainedAnalysis.mount(document.querySelector('#analysis'), {load, onSelection: value => window.fixtureSelections.push(value)});
window.fixtureStart = () => window.fixtureAdapter.update(window.fixtureRequest, 'authority-1');
void window.fixtureStart();
