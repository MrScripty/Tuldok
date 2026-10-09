'use strict';
let rightsDirty = false, rightsBusy = false, rightsEpoch = 0, rightsFormat = 'text', rightsSetEpoch = 0;
const rightsKnownRevisions = new Map();
// Match Python str.strip() in the pinned Python3.12 server, including C0/0085 and excluding FEFF.
function rightsStrip(value) {
  return value.replace(/^[\u0009-\u000D\u001C-\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]+|[\u0009-\u000D\u001C-\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]+$/gu, '');
}
function currentRights(record) { const correction = record.provenance.rights_note_correction; const note = typeof correction?.note === 'string' ? correction.note : record.provenance.rights; return typeof note === 'string' && rightsStrip(note) ? rightsStrip(note) : 'unknown'; }
function rightsValue(format = $('rights-note-format').value) {
  let note = $('rights-note-value').value;
  if(format === 'json') { try { note = JSON.parse(note); } catch { note = null; } }
  if(typeof note !== 'string') throw Error('Enter a rights note as text or a JSON string.');
  if(/[\uD800-\uDFFF]/u.test(note)) throw Error('Rights note contains invalid Unicode.');
  if(Array.from(note).length > 1000) throw Error('Rights note must be at most 1,000 Unicode code points.');
  return rightsStrip(note) || 'unknown';
}
function rightsRecordShown(record) {
  ++rightsEpoch; rightsDirty = false;
  let note = currentRights(record); note = typeof note === 'string' && rightsStrip(note) ? rightsStrip(note) : 'unknown';
  rightsFormat = /\r/.test(note) ? 'json' : 'text'; $('rights-note-format').value = rightsFormat;
  $('rights-note-value').maxLength = rightsFormat === 'json' ? 12002 : 2000;
  $('rights-note-value').value = rightsFormat === 'json' ? JSON.stringify(note) : note;
  $('rights-note-panel').hidden = false;
  $('rights-note-status').textContent = `Record revision ${record.revision} / source ${record.source_revision ?? 'deleted'}. Original rights evidence remains in source provenance and history.`;
}
function rightsValidateSavedResult(result) {
  for(const member of result.members) {
    if(['ok','stale'].includes(member.status) && (rightsKnownRevisions.get(member.item.id) || 0) > member.item.revision) {
      member.status = 'stale'; member.message = 'Rights note changed the record revision; saved revisions are retained.';
    }
  }
  result.current = result.members.every(member=>member.status==='ok');
}
async function rightsRefreshSavedIssues() {
  if(typeof savedSets === 'undefined') return;
  const id = $('saved-selection').value; if(!id) return;
  const epoch = ++rightsSetEpoch, intent = selectionEpoch, load = savedLoadEpoch, key = JSON.stringify(releaseBody().items);
  try {
    const result = await api('selections/'+id);
    if(epoch !== rightsSetEpoch || intent !== selectionEpoch || load !== savedLoadEpoch || id !== $('saved-selection').value || key !== JSON.stringify(releaseBody().items)) return;
    rightsValidateSavedResult(result);
    $('saved-selection-issues').replaceChildren();
    for(const member of result.members.filter(member=>member.status!=='ok')) {
      const li = document.createElement('li');li.textContent = `${member.item.name} (${member.item.id}) · ${member.status}: ${member.message}`;
      $('saved-selection-issues').append(li);
    }
    savedStatus(result.current ? 'Saved revisions are current. Preview again before exporting.' : 'Rights note changed. Saved revisions are retained; explicitly reselect current records for a new release.');
  } catch(error) { if(epoch === rightsSetEpoch && intent === selectionEpoch && load === savedLoadEpoch && id === $('saved-selection').value && key === JSON.stringify(releaseBody().items)) $('rights-note-status').textContent += ' Saved-set check failed: '+error.message; }
}
$('rights-note-value').addEventListener('input',()=>{
  ++rightsEpoch; ++editorEpoch;
  try { rightsDirty = rightsValue() !== (rightsStrip(String(currentRights(current) ?? '')) || 'unknown'); }
  catch { rightsDirty = true; }
});
$('rights-note-format').addEventListener('change',()=>{
  try {
    const value = rightsValue(rightsFormat), format = $('rights-note-format').value;
    if(format === 'text' && /\r/.test(value)) throw Error('Keep JSON string entry to preserve carriage returns.');
    $('rights-note-value').maxLength = format === 'json' ? 12002 : 2000;
    $('rights-note-value').value = format === 'json' ? JSON.stringify(value) : value; rightsFormat = format;
  } catch(error) { $('rights-note-format').value = rightsFormat; $('rights-note-status').textContent = error.message; }
});
$('rights-note-cancel').addEventListener('click',()=>{
  if(rightsBusy || !current) return; ++editorEpoch; rightsRecordShown(current); $('rights-note-status').textContent = 'Note edit canceled. No revision changed.';
});
$('rights-note-form').addEventListener('submit',async event=>{
  event.preventDefault();if(rightsBusy || !current) return;
  if(typeof polygonPointer !== 'undefined' && polygonPointer) { $('rights-note-status').textContent = 'Finish or cancel polygon capture before correcting the rights note.'; return; }
  if(dirty || $('editor').dataset.busy) { $('rights-note-status').textContent = 'Save or discard annotation edits before correcting the rights note.'; return; }
  if(typeof responseDirty !== 'undefined' && (responseDirty || responseBusy)) { $('rights-note-status').textContent = 'Save or cancel the response edit before correcting the rights note.'; return; }
  let note;try { note = rightsValue(); } catch(error) { $('rights-note-status').textContent = error.message; return; }
  if(typeof preferenceDirty !== 'undefined' && (preferenceDirty || preferenceBusy)) { $('rights-note-status').textContent = 'Save or cancel the judgment edit before saving a rights note.'; return; }
  const record = current, epoch = ++editorEpoch, noteEpoch = rightsEpoch, responseEpoch = responseIntentEpoch();
  rightsBusy = true;const controls=[...$('rights-note-form').querySelectorAll('button,select,textarea')];controls.forEach(control=>control.disabled=true);
  try {
    const result = await api('rights/'+record.id,{revision:record.revision,source_revision:record.source_revision,note});
    if(result.changed) {
      rightsKnownRevisions.set(record.id,result.record.revision);
      // Unselected lineage can also bind a preview; conservatively discard every cached proof.
      invalidateRelease();$('release-preview-status').textContent = 'Rights note changed. Saved revision pairs remain fixed; reselect current records and preview again.';
      if(typeof invalidateResponsePreview === 'function') invalidateResponsePreview();
      if(typeof invalidatePreferencePreview === 'function') invalidatePreferencePreview();
      await rightsRefreshSavedIssues();
    }
    if(epoch === editorEpoch && noteEpoch === rightsEpoch && responseEpoch === responseIntentEpoch() && current?.id === record.id) {
      showRecord(result.record);$('rights-note-status').textContent = result.changed ? 'Rights note saved. Record revision changed; annotation review and source evidence are unchanged.' : 'Note unchanged. No revision or history changed.';
    } else if(current?.id === record.id) {
      $('rights-note-status').textContent = 'Earlier note saved; later edits are retained. Reload before using current record revisions.';
    }
    await refresh();
  } catch(error) {
    invalidateRelease();
    if(typeof invalidateResponsePreview === 'function') invalidateResponsePreview();
    if(typeof invalidatePreferencePreview === 'function') invalidatePreferencePreview();
    if(current?.id === record.id && noteEpoch === rightsEpoch) $('rights-note-status').textContent = error.message+' Your note edit is retained; reload the record to use current revisions.';
  }
  finally { rightsBusy = false;controls.forEach(control=>control.disabled=false); }
});
