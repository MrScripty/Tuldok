'use strict';
let curationEpoch = 0, curationBusy = false, curationReport = null, curationKey = '', curationQueryPending = false;
function curationScope() {
  return $('curation-scope').value === 'selected'
    ? {scope:'selected', items:releaseBody().items}
    : {scope:'filtered', filters:page?.criteria || {}};
}
function curationScopeKey() { return JSON.stringify(curationScope()); }
function curationControls() {
  $('curation-refresh').disabled = curationBusy || curationQueryPending || !page;
  $('curation-previous').disabled = curationBusy || !curationReport || curationReport.offset === 0;
  $('curation-next').disabled = curationBusy || !curationReport || curationReport.offset + curationReport.items.length >= curationReport.total;
}
function curationInvalidate(message = 'Scope changed. Refresh diagnostics.', pendingQuery = false) {
  if(pendingQuery) curationQueryPending = true;
  ++curationEpoch; curationBusy = false; curationReport = null;
  curationKey = curationScopeKey();
  $('curation-results').replaceChildren(); $('curation-counts').textContent = ''; $('curation-page').textContent = '';
  $('curation-status').textContent = message; curationControls();
}
function curationQueryFinished() { curationQueryPending = false; curationControls(); }
function curationChanged() {
  if(curationKey !== curationScopeKey()) curationInvalidate();
}
async function curationInspect(record, epoch) {
  if(epoch !== curationEpoch || $('editor').dataset.busy || !mayDiscard()) return;
  const editorRequest = ++editorEpoch, responseEpoch = responseIntentEpoch();
  try {
    const latest = await api('records/' + record.id);
    if(epoch !== curationEpoch || editorRequest !== editorEpoch || responseEpoch !== responseIntentEpoch()) return;
    if(latest.revision !== record.revision || latest.source_revision !== record.source_revision) {
      curationInvalidate('Record changed since this report. Refresh diagnostics.'); return;
    }
    showRecord(latest);
  } catch(error) {
    if(epoch === curationEpoch) curationInvalidate(error.message + ' Refresh diagnostics.');
  }
}
function curationRender(epoch) {
  const result = curationReport, a = result.analysis, refs = result.reference_counts;
  const scope = result.scope === 'selected'
    ? `Exact selected IDs: ${result.requested} requested, ${a.records} resolved. Current facts; saved revision pairs retained.`
    : `All ${a.records} records matching applied collection criteria: ${JSON.stringify(result.filters)}.`;
  $('curation-status').textContent = scope;
  $('curation-counts').textContent = `${a.duplicate_content_records} exact duplicate members · ${a.unlabeled} unlabeled · ${a.missing_sources} missing source records · ${a.unknown_rights} unknown rights notes. Selected references: ${refs.stale} stale · ${refs.source_deleted} deleted sources · ${refs.missing_record} missing records. Duplicate membership is limited to this scope; empty reviewed boxes/spans are labeled negatives.`;
  $('curation-results').replaceChildren();
  for(const record of result.items) {
    const row = document.createElement('li'), description = document.createElement('p');
    description.textContent = `${record.name} · ID ${record.id}`;
    if(record.revision !== undefined) description.textContent += ` · revision ${record.revision} / source ${record.source_revision ?? 'deleted'} · ${record.task} · ${record.review} · rights note: ${record.rights_note} · groups: ${record.groups.join(', ')}`;
    if(record.duplicate_hash) description.textContent += ` · decoded-content hash ${record.duplicate_hash} · ${record.duplicate_members} members in scope`;
    if(record.reference) description.textContent += ` · requested ${record.reference.requested.revision} / ${record.reference.requested.source_revision ?? 'deleted'} · ${record.reference.issues.join(', ') || 'current'}`;
    const inspect = document.createElement('button'); inspect.type = 'button'; inspect.textContent = 'Inspect current record';
    inspect.disabled = record.revision === undefined;
    inspect.onclick = () => curationInspect(record, epoch);
    row.append(description, inspect); $('curation-results').append(row);
  }
  $('curation-page').textContent = result.total ? `${result.offset+1}–${Math.min(result.offset+result.limit,result.total)} of ${result.total} contributors` : 'No contributors';
}
async function curationLoad(offset = 0, fresh = false) {
  if(curationBusy || curationQueryPending || !page) return;
  const epoch = ++curationEpoch, key = curationScopeKey();
  curationKey = key; curationBusy = true; curationControls();
  $('curation-status').textContent = 'Reading current diagnostic metadata…';
  const body = {...curationScope(), category:$('curation-category').value, offset, limit:40};
  if(!fresh && curationReport) body.view_token = curationReport.view_token;
  try {
    const result = await api('curation', body);
    if(epoch !== curationEpoch || key !== curationScopeKey()) return;
    curationReport = result; curationRender(epoch);
  } catch(error) {
    if(epoch === curationEpoch) curationInvalidate(error.message);
  } finally {
    if(epoch === curationEpoch) { curationBusy = false; curationControls(); }
  }
}
for(const id of ['curation-scope','curation-category']) $(id).addEventListener('change', () => curationInvalidate());
$('curation-refresh').addEventListener('click', () => curationLoad(0,true));
$('curation-previous').addEventListener('click', () => curationLoad(Math.max(0,curationReport.offset-40)));
$('curation-next').addEventListener('click', () => curationLoad(curationReport.offset+40));
curationControls();
