'use strict';
// Only complete trajectories are scheduled. Record/review/selection owners stay separate.
let sequenceBatchRunning=false, sequenceBatchStopped=false, sequenceBatchPending=null;
let sequenceBatchEpoch=0, sequenceBatchFlight=null, sequenceBatchCounts=null;
function sequenceBatchControls() {
  for(const id of ['sequence-batch-folder','sequence-batch-group','sequence-batch-rights'])$(id).disabled=sequenceBatchRunning;
  $('sequence-batch-start').disabled=sequenceBatchRunning || !!sequenceBatchPending;
  $('sequence-batch-stop').disabled=!sequenceBatchRunning || sequenceBatchStopped;
  for(const id of ['sequence-batch-check','sequence-batch-dismiss'])$(id).disabled=sequenceBatchRunning || !sequenceBatchPending;
}
function sequenceBatchSummary(counts,state) {
  $('sequence-batch-status').textContent=`${state}: ${counts.created} created, ${counts.rejected} rejected, ${counts.unknown} uncertain; ${counts.total-counts.attempted} not attempted. New records require human review.`;
}
function sequenceBatchItem(index,name,state,message) {
  const item=document.createElement('li');
  item.textContent=`Trajectory ${index} (${name}) · ${state}: ${String(message).slice(0,500)}`;
  $('sequence-batch-results').append(item);return item;
}
function sequenceBatchLabel(value) {
  if(typeof value!=='string' || !value || value.length>200 || !value.isWellFormed() || value.trim()!==value || ['.','..'].includes(value) || /[\x00-\x1f/\\]/.test(value))throw Error('Use flat folder labels of at most 200 characters, without paths or surrounding whitespace.');
  return value;
}
function sequenceBatchPairs(files) {
  if(!files.length || files.length>96)throw Error('Choose a folder containing 1–32 complete trajectories (at most 96 files).');
  const pairs=new Map();let root=null,total=0;
  for(const file of files) {
    const parts=(file.webkitRelativePath||'').split('/');
    if(parts.length!==3 || !['run.json','frames.jsonl','controls.json'].includes(parts[2]) || file.name!==parts[2])throw Error('Select only folder/trajectory/run.json, frames.jsonl and optional producer-v2 controls.json.');
    const batch_name=sequenceBatchLabel(parts[0]),item_name=sequenceBatchLabel(parts[1]);
    if(root!==null && root!==batch_name)throw Error('All selected pairs must share one folder.');
    root=batch_name;
    if(!Number.isSafeInteger(file.size) || file.size<=0)throw Error('Selected files must be nonempty with bounded sizes.');
    if(file.size>(file.name==='frames.jsonl'?2097152:65536))throw Error('Each run.json/controls.json must be at most 64 KiB and frames.jsonl at most 2 MiB.');
    total+=file.size;
    if(total>40*1024*1024)throw Error('Selected raw trajectory files exceed 40 MiB.');
    const pair=pairs.get(item_name)||{batch_name,item_name,files:{}};
    if(pair.files[file.name])throw Error('A selected trajectory filename is ambiguous.');
    pair.files[file.name]=file;pairs.set(item_name,pair);
  }
  const result=[...pairs.values()].sort((a,b)=>a.item_name<b.item_name?-1:a.item_name>b.item_name?1:0);
  if(result.length>32 || result.some(pair=>!pair.files['run.json'] || !pair.files['frames.jsonl']))throw Error('Every trajectory folder must contain exactly one complete run/frame pair.');
  return result;
}
async function sequenceBatchHash(encoded) {
  // Hash the exact transmitted bytes, without rereading the selected File.
  const raw=Uint8Array.from(atob(encoded),character=>character.charCodeAt(0));
  const digest=await crypto.subtle.digest('SHA-256',raw);
  return [...new Uint8Array(digest)].map(byte=>byte.toString(16).padStart(2,'0')).join('');
}
function sequenceBatchReceipt(value,proof) {
  const hasControls=Object.hasOwn(proof,'controls_sha256');
  return value && value.format===(hasControls?'tuldok_rheon_batch_v2':'tuldok_rheon_batch_v1') && value.kind==='sequence'
    && typeof value.record_id==='string' && /^[a-f0-9]{32}$/.test(value.record_id) && typeof value.name==='string'
    && ['request_id','batch_name','item_name','item_index','run_sha256','frames_sha256'].every(key=>value[key]===proof[key])
    && (hasControls ? value.sequence_version===2 && value.controls_sha256===proof.controls_sha256
      : !Object.hasOwn(value,'sequence_version') && !Object.hasOwn(value,'controls_sha256'));
}
async function sequenceBatchRefresh(epoch) {
  if(epoch!==sequenceBatchEpoch)return;
  try{await refresh(()=>epoch===sequenceBatchEpoch);}catch(error){if(epoch===sequenceBatchEpoch)notice('Imported records remain retained; collection refresh failed: '+error.message,true);}
}
$('sequence-batch-stop').addEventListener('click',()=>{
  if(!sequenceBatchRunning)return;
  sequenceBatchStopped=true;sequenceBatchControls();
  $('sequence-batch-status').textContent='Stopping before the next trajectory. An in-flight admission may still complete.';
});
window.addEventListener('pagehide',()=>{
  sequenceBatchEpoch++;sequenceBatchStopped=true;sequenceBatchRunning=false;
  if(sequenceBatchFlight) {
    sequenceBatchPending=sequenceBatchFlight;sequenceBatchFlight=null;
    sequenceBatchPending.counts.unknown++;
    sequenceBatchPending.item.textContent=`Trajectory ${sequenceBatchPending.item_index} (${sequenceBatchPending.item_name}) · uncertain after page departure; check saved result. In-flight work may complete.`;
    sequenceBatchSummary(sequenceBatchPending.counts,'Paused after page departure');
  } else if(sequenceBatchPending) {
    $('sequence-batch-status').textContent='Pending admission remains uncertain after page departure. Check its saved result or inspect the collection.';
  } else if(sequenceBatchCounts)sequenceBatchSummary(sequenceBatchCounts,'Stopped after page departure');
  sequenceBatchControls();
});
$('sequence-batch-form').addEventListener('submit',async event=>{
  event.preventDefault();if(sequenceBatchRunning)return;
  if(sequenceBatchPending){notice('Check or dismiss the uncertain trajectory before starting another batch.',true);return;}
  const files=[...$('sequence-batch-folder').files],group=$('sequence-batch-group').value.trim(),rights=$('sequence-batch-rights').value || 'unknown';
  const epoch=++sequenceBatchEpoch,counts={created:0,rejected:0,unknown:0,attempted:0,total:0};
  sequenceBatchCounts=counts;sequenceBatchRunning=true;sequenceBatchStopped=false;
  sequenceBatchControls();$('sequence-batch-results').replaceChildren();
  let state='Complete';
  try {
    const pairs=sequenceBatchPairs(files);counts.total=pairs.length;
    for(const [offset,pair] of pairs.entries()) {
      if(epoch!==sequenceBatchEpoch)return;
      if(sequenceBatchStopped){state='Stopped';break;}
      let body,proof;
      try {
        const run=await sequenceFile(pair.files['run.json'],65536,'run.json');
        if(epoch!==sequenceBatchEpoch)return;
        if(sequenceBatchStopped){state='Stopped';break;}
        const frames=await sequenceFile(pair.files['frames.jsonl'],2097152,'frames.jsonl');
        if(epoch!==sequenceBatchEpoch)return;
        if(sequenceBatchStopped){state='Stopped';break;}
        const files={'run.json':run,'frames.jsonl':frames};
        if(pair.files['controls.json']) {
          files['controls.json']=await sequenceFile(pair.files['controls.json'],65536,'controls.json');
          if(epoch!==sequenceBatchEpoch)return;
          if(sequenceBatchStopped){state='Stopped';break;}
        }
        proof={request_id:crypto.randomUUID().replaceAll('-',''),batch_name:pair.batch_name,item_name:pair.item_name,item_index:offset+1};
        for(const [name,value] of Object.entries(files)) {
          const key={'run.json':'run_sha256','frames.jsonl':'frames_sha256','controls.json':'controls_sha256'}[name];
          proof[key]=await sequenceBatchHash(value);
          if(epoch!==sequenceBatchEpoch)return;
          if(sequenceBatchStopped)break;
        }
        body={request_id:proof.request_id,batch_name:proof.batch_name,item_name:proof.item_name,item_index:proof.item_index,
          files,name:pair.item_name,groups:group?[group]:[],rights};
      } catch(error) {
        if(epoch!==sequenceBatchEpoch)return;
        if(sequenceBatchStopped){state='Stopped';break;}
        counts.attempted++;counts.rejected++;sequenceBatchItem(offset+1,pair.item_name,'rejected',error.message);continue;
      }
      if(epoch!==sequenceBatchEpoch)return;
      if(sequenceBatchStopped){state='Stopped';break;}
      counts.attempted++;
      const item=sequenceBatchItem(offset+1,pair.item_name,'importing','Validating the whole bounded trajectory…');
      sequenceBatchFlight={...proof,counts,item};
      try {
        const response=await fetch('/api/workbench/sequence-import-item',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        if(epoch!==sequenceBatchEpoch)return;
        const result=await response.json();
        if(epoch!==sequenceBatchEpoch)return;
        if(!response.ok) {
          if(![400,409].includes(response.status))throw Error(result.error||'Server failure');
          counts.rejected++;item.textContent=`Trajectory ${offset+1} (${pair.item_name}) · rejected: ${String(result.error||'Admission failed.').slice(0,500)}`;
        } else {
          if(!sequenceBatchReceipt(result,proof))throw Error('Invalid admission receipt');
          counts.created++;item.textContent=`Trajectory ${offset+1} (${pair.item_name}) · created: ${result.name} · ${result.record_id} · imported as unreviewed`;
        }
        sequenceBatchFlight=null;
      } catch(error) {
        if(epoch!==sequenceBatchEpoch)return;
        counts.unknown++;state='Paused after uncertain response';sequenceBatchPending=sequenceBatchFlight;sequenceBatchFlight=null;
        item.textContent=`Trajectory ${offset+1} (${pair.item_name}) · uncertain: response lost, invalid or server failed. The trajectory may have been admitted. Check its saved result before retrying.`;
        break;
      }
      sequenceBatchSummary(counts,'Importing');
    }
    if(sequenceBatchStopped && state==='Complete')state='Stopped';
    sequenceBatchSummary(counts,state);
  } catch(error) {
    if(epoch===sequenceBatchEpoch){$('sequence-batch-status').textContent=error.message;notice(error.message,true);}
  } finally {
    if(epoch===sequenceBatchEpoch){sequenceBatchRunning=false;sequenceBatchControls();await sequenceBatchRefresh(epoch);}
  }
});
$('sequence-batch-check').addEventListener('click',async()=>{
  if(sequenceBatchRunning || !sequenceBatchPending)return;
  const pending=sequenceBatchPending,epoch=++sequenceBatchEpoch;
  sequenceBatchRunning=true;sequenceBatchControls();
  try {
    const response=await fetch('/api/workbench/sequence-import-result/'+pending.request_id);
    if(epoch!==sequenceBatchEpoch)return;
    const result=await response.json();
    if(epoch!==sequenceBatchEpoch)return;
    if(!response.ok)throw Error(result.error||'Result check failed.');
    if(typeof result.found!=='boolean')throw Error('Invalid saved-result observation.');
    if(!result.found){$('sequence-batch-status').textContent='No saved result is visible yet. This does not prove the in-flight trajectory stopped. Inspect the collection before retrying.';return;}
    if(!sequenceBatchReceipt(result,pending))throw Error('Saved result does not match the pending trajectory.');
    pending.item.textContent=`Trajectory ${pending.item_index} (${pending.item_name}) · created (saved admission confirmed): ${result.name} · ${result.record_id}. Current bytes and review are separate.`;
    pending.counts.unknown--;pending.counts.created++;sequenceBatchSummary(pending.counts,'Paused; saved admission confirmed');sequenceBatchPending=null;
  } catch(error) {if(epoch===sequenceBatchEpoch)notice(error.message,true);}
  finally {if(epoch===sequenceBatchEpoch){sequenceBatchRunning=false;sequenceBatchControls();await sequenceBatchRefresh(epoch);}}
});
$('sequence-batch-dismiss').addEventListener('click',()=>{
  if(sequenceBatchRunning || !sequenceBatchPending)return;
  sequenceBatchPending=null;sequenceBatchControls();
  $('sequence-batch-status').textContent='Pending check dismissed; no rollback is implied. Inspect the collection before retrying. Existing bundles are rejected without changes.';
});
sequenceBatchControls();
