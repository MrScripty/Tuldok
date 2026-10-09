'use strict';
let sequenceImportBusy = false, sequenceImportEpoch = 0, sequenceImportDeparted = false;
window.addEventListener('pagehide',()=>{sequenceImportEpoch++;sequenceImportDeparted=true;});
window.addEventListener('pageshow',event=>{
  if(!event.persisted)return;
  sequenceImportEpoch++;sequenceImportDeparted=false;sequenceImportBusy=false;
  [...$('sequence-import-form').querySelectorAll('input,button')].forEach(control=>control.disabled=false);
  $('sequence-import-status').textContent='Page restored. Check the collection for an earlier in-flight import before repeating it.';
});
function sequenceShown(record) {
  if(typeof sequenceTemporalShown === 'function') sequenceTemporalShown(record);
  if(typeof sequenceReviewShown === 'function') sequenceReviewShown(record);
  if(typeof sequenceProbeShown === 'function') sequenceProbeShown(record);
  const panel = $('sequence-inspection'); panel.hidden = record.kind !== 'sequence';
  if(record.kind !== 'sequence') return;
  $('sequence-note').value = record.annotation?.note || '';
  $('sequence-metadata').textContent = JSON.stringify(record.sequence, null, 2);
  $('sequence-download').href = '/api/workbench/asset/' + record.id;
  $('sequence-download').download = record.id + '.zip';
  $('sequence-download').textContent=record.sequence?.manifest?.version===2
    ? 'Download original run.json + frames.jsonl + controls.json bundle'
    : 'Download original run.json + frames.jsonl bundle';
}
async function sequenceFile(file, maximum, name) {
  if(!file || file.name !== name || !file.size || file.size > maximum) throw Error(`Choose ${name}, at most ${maximum} bytes.`);
  const raw = new Uint8Array(await file.arrayBuffer());
  if(raw.length!==file.size)throw Error('Selected sequence file size changed.');
  let binary = '';
  for(let start=0; start<raw.length; start+=32768) binary += String.fromCharCode(...raw.subarray(start,start+32768));
  return btoa(binary);
}
async function sequenceDigest(value) {
  const raw=Uint8Array.from(atob(value),c=>c.charCodeAt(0));
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256',raw))].map(n=>n.toString(16).padStart(2,'0')).join('');
}
$('sequence-import-form').addEventListener('submit', async event => {
  event.preventDefault(); if(sequenceImportBusy||sequenceImportDeparted) return;
  const epoch=++sequenceImportEpoch,live=()=>epoch===sequenceImportEpoch&&!sequenceImportDeparted;
  sequenceImportBusy = true;
  const controls = [...$('sequence-import-form').querySelectorAll('input,button')];
  controls.forEach(control => control.disabled = true);
  const status = $('sequence-import-status');
  try {
    const run = $('sequence-run').files[0], frames = $('sequence-frames').files[0], emitted=$('sequence-controls').files[0];
    const name = $('sequence-name').value, group = $('sequence-group').value.trim(), rights = $('sequence-rights').value || 'unknown';
    status.textContent = 'Reading and validating the complete bounded trajectory…';
    const files = {'run.json':await sequenceFile(run,65536,'run.json')};if(!live())return;
    files['frames.jsonl']=await sequenceFile(frames,2097152,'frames.jsonl');if(!live())return;
    if(emitted)files['controls.json']=await sequenceFile(emitted,65536,'controls.json');if(!live())return;
    const proofs={};for(const [name,value] of Object.entries(files)){proofs[name]=await sequenceDigest(value);if(!live())return;}
    const record = await api('sequence-import', {files,name,groups:group?[group]:[],rights});
    if(!live())return;
    if(record.kind!=='sequence'||record.review!=='draft'||record.annotation!==null||record.revision!==1||record.source_revision!==1||
       typeof record.id!=='string'||!/^[a-f0-9]{32}$/.test(record.id)||record.sequence?.run_sha256!==proofs['run.json']||
       record.sequence.manifest?.frames_sha256!==proofs['frames.jsonl']||record.sequence.manifest.version!==(emitted?2:1)||
       (emitted&&record.sequence.controls?.sha256!==proofs['controls.json']))throw Error('Uncertain sequence import receipt.');
    status.textContent = `Imported ${record.name}: 9 frames, unreviewed. Open it in the collection to inspect and review.`;
    // Collection refresh retains the independent editor and selection owners.
    await refresh(live);
  } catch(error) { if(live())status.textContent = error.message + ' Check the collection before repeating a request whose response was lost.'; }
  finally { if(live()){sequenceImportBusy = false;controls.forEach(control => control.disabled = false);} }
});
