'use strict';
let sequenceImportBusy = false;
function sequenceShown(record) {
  const panel = $('sequence-inspection'); panel.hidden = record.kind !== 'sequence';
  if(record.kind !== 'sequence') return;
  $('sequence-note').value = record.annotation?.note || '';
  $('sequence-metadata').textContent = JSON.stringify(record.sequence, null, 2);
  $('sequence-download').href = '/api/workbench/asset/' + record.id;
  $('sequence-download').download = record.id + '.zip';
}
async function sequenceFile(file, maximum, name) {
  if(!file || file.name !== name || !file.size || file.size > maximum) throw Error(`Choose ${name}, at most ${maximum} bytes.`);
  const raw = new Uint8Array(await file.arrayBuffer());
  let binary = '';
  for(let start=0; start<raw.length; start+=32768) binary += String.fromCharCode(...raw.subarray(start,start+32768));
  return btoa(binary);
}
$('sequence-import-form').addEventListener('submit', async event => {
  event.preventDefault(); if(sequenceImportBusy) return;
  sequenceImportBusy = true;
  const controls = [...$('sequence-import-form').querySelectorAll('input,button')];
  controls.forEach(control => control.disabled = true);
  const status = $('sequence-import-status');
  try {
    const run = $('sequence-run').files[0], frames = $('sequence-frames').files[0];
    const name = $('sequence-name').value, group = $('sequence-group').value.trim(), rights = $('sequence-rights').value || 'unknown';
    status.textContent = 'Reading and validating the complete bounded trajectory…';
    const files = {'run.json':await sequenceFile(run,65536,'run.json'), 'frames.jsonl':await sequenceFile(frames,2097152,'frames.jsonl')};
    const record = await api('sequence-import', {files,name,groups:group?[group]:[],rights});
    status.textContent = `Imported ${record.name}: 9 frames, unreviewed. Open it in the collection to inspect and review.`;
    // Collection refresh retains the independent editor and selection owners.
    await refresh();
  } catch(error) { status.textContent = error.message + ' Check the collection before repeating a request whose response was lost.'; }
  finally { sequenceImportBusy = false; controls.forEach(control => control.disabled = false); }
});
