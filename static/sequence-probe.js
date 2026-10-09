'use strict';
let sequenceProbeEpoch = 0, sequenceProbeRecord = null, sequenceProbeAbort = null;
function sequenceProbeInvalidate() {
  sequenceProbeEpoch++;
  sequenceProbeAbort?.abort(); sequenceProbeAbort = null;
  $('sequence-probe-output').textContent = '';
  $('sequence-probe-status').textContent = '';
}
function sequenceProbeShown(record) {
  sequenceProbeInvalidate();
  sequenceProbeRecord = record.kind === 'sequence' ? {id:record.id,revision:record.revision,source_revision:record.source_revision,content_hash:record.content_hash} : null;
  $('sequence-probe').hidden = !sequenceProbeRecord;
  $('sequence-probe-controls').value = '';
}
for(const id of ['frame','field','i','j','k','controls']) {
  for(const event of ['input','change']) $('sequence-probe-'+id).addEventListener(event, sequenceProbeInvalidate);
}
window.addEventListener('pagehide', () => { sequenceProbeInvalidate(); sequenceProbeRecord = null; });
$('sequence-probe-read').addEventListener('click', async () => {
  sequenceProbeInvalidate();
  if(!sequenceProbeRecord) return;
  const epoch = sequenceProbeEpoch, record = {...sequenceProbeRecord};
  const controller = new AbortController(); sequenceProbeAbort = controller;
  const body = {...record,frame:Number($('sequence-probe-frame').value),field:$('sequence-probe-field').value,
    index:['i','j','k'].map(axis=>Number($('sequence-probe-'+axis).value))};
  delete body.id;
  delete body.content_hash;
  const file = $('sequence-probe-controls').files[0];
  const live = () => epoch === sequenceProbeEpoch && sequenceProbeRecord?.id === record.id;
  $('sequence-probe-status').textContent = 'Checking original native bundle…';
  try {
    for(const id of ['frame','i','j','k']) {
      if(!/^(0|[1-9][0-9]*)$/.test($('sequence-probe-'+id).value)) throw Error('Choose nonnegative integer native frame and indices.');
    }
    if(file) {
      if(!file.size || file.size>65536) throw Error('Authored controls file must be at most 65536 bytes.');
      const raw = new Uint8Array(await file.arrayBuffer());
      if(!live()) return;
      if(raw.length!==file.size) throw Error('Controls file size changed.');
      let binary=''; for(let i=0;i<raw.length;i+=32768) binary+=String.fromCharCode(...raw.subarray(i,i+32768));
      body.controls=btoa(binary);
    }
    if(!live()) return;
    const response=await fetch('/api/workbench/sequence-inspection/'+encodeURIComponent(record.id),{
      method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:controller.signal});
    const result=await response.json();
    if(!live()) return;
    if(!response.ok) throw Error(result.error||'Sequence inspection failed.');
    if(result.id!==record.id || result.revision!==record.revision || result.source_revision!==record.source_revision || result.content_hash!==record.content_hash) throw Error('Invalid sequence inspection identity.');
    $('sequence-probe-output').textContent=JSON.stringify(result,null,2);
    $('sequence-probe-status').textContent=result.interval_controls_emitted?.scope==='producer_controls_validated'
      ? 'Native value inspected. Declared producer-v2 controls validated; origin authenticity and review unchanged.'
      : 'Native value inspected. Producer interval controls unavailable; review state unchanged.';
  } catch(error) {
    if(live()) $('sequence-probe-status').textContent=error.message;
  } finally { if(live()) sequenceProbeAbort=null; }
});
