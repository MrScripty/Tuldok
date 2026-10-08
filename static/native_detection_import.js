'use strict';
// This form owns bounded batch intent. It never adopts record/editor selections.
let detectionRunning=false,detectionStopped=false,detectionPending=null;
let detectionEpoch=0,detectionFlight=null,detectionCounts=null;
function detectionControls(){
  $('native-detection-archive').disabled=detectionRunning;
  $('native-detection-start').disabled=detectionRunning || !!detectionPending;
  $('native-detection-stop').disabled=!detectionRunning || detectionStopped;
  for(const id of ['native-detection-check','native-detection-dismiss'])$(id).disabled=detectionRunning || !detectionPending;
}
function detectionSummary(counts,state){
  $('native-detection-status').textContent=`${state}: ${counts.created} created, ${counts.rejected} rejected, ${counts.unknown} uncertain; ${counts.total-counts.attempted} not attempted. New detection records require human review.`;
}
function detectionRow(number,state,message){
  const item=document.createElement('li');item.textContent=`Manifest record ${number} · ${state}: ${String(message).slice(0,500)}`;
  $('native-detection-results').append(item);return item;
}
function detectionReceipt(value,proof){
  return value && value.kind==='image' && typeof value.record_id==='string' && /^[a-f0-9]{32}$/.test(value.record_id)
    && typeof value.name==='string' && ['request_id','row_number','row_sha256'].every(key=>value[key]===proof[key]);
}
async function detectionRefresh(epoch){
  if(epoch!==detectionEpoch)return;
  try{await refresh(()=>epoch===detectionEpoch);}catch(error){if(epoch===detectionEpoch)notice('Imported records remain retained; collection refresh failed: '+error.message,true);}
}
$('native-detection-stop').addEventListener('click',()=>{
  if(!detectionRunning)return;
  detectionStopped=true;detectionControls();$('native-detection-status').textContent='Stopping before the next record. An in-flight admission may still complete.';
});
window.addEventListener('pagehide',()=>{
  detectionEpoch++;detectionStopped=true;detectionRunning=false;
  if(detectionFlight){
    detectionPending=detectionFlight;detectionFlight=null;detectionPending.counts.unknown++;
    detectionPending.item.textContent=`Manifest record ${detectionPending.row_number} · uncertain after page departure; check saved result. In-flight work may complete.`;
    detectionSummary(detectionPending.counts,'Paused after page departure');
  }else if(detectionPending)$('native-detection-status').textContent='Pending admission remains uncertain after page departure. Check its saved result or inspect the collection.';
  else if(detectionCounts)detectionSummary(detectionCounts,'Stopped after page departure');
  detectionControls();
});
$('native-detection-form').addEventListener('submit',async event=>{
  event.preventDefault();if(detectionRunning)return;
  if(detectionPending){notice('Check or dismiss the uncertain record before starting again.',true);return;}
  const file=$('native-detection-archive').files[0],epoch=++detectionEpoch;
  const counts={created:0,rejected:0,unknown:0,total:0,attempted:0};
  detectionCounts=counts;detectionRunning=true;detectionStopped=false;detectionControls();$('native-detection-results').replaceChildren();
  let state='Complete';
  try{
    if(!file || !Number.isSafeInteger(file.size) || file.size<=0 || file.size>8*1024*1024)throw Error('Choose one native detection ZIP of at most 8 MiB.');
    // Snapshot the selected File and its declared size before the first await.
    const size=file.size,name=file.name,buffer=await file.arrayBuffer();
    if(epoch!==detectionEpoch)return;
    if(detectionStopped){detectionSummary(counts,'Stopped before preparation');return;}
    if(buffer.byteLength!==size)throw Error('Selected archive size changed during reading.');
    const bytes=new Uint8Array(buffer),parts=[];
    for(let offset=0;offset<bytes.length;offset+=16384)parts.push(String.fromCharCode(...bytes.subarray(offset,offset+16384)));
    const response=await fetch('/api/workbench/native-detection-import/prepare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source_name:name,archive:btoa(parts.join(''))})});
    if(epoch!==detectionEpoch)return;
    const prepared=await response.json();
    if(epoch!==detectionEpoch)return;
    if(!response.ok)throw Error(prepared.error||'Native detection preparation failed.');
    if(prepared.format!=='canonical_v1' || prepared.schema_version!==1 || prepared.input_basis!=='consumed_exported_png'
      || prepared.upstream_original!=='unavailable' || prepared.upstream_graph!=='selected_declared_links_only'
      || !/^[a-f0-9]{64}$/.test(prepared.archive_sha256) || !Array.isArray(prepared.rows) || !prepared.rows.length || prepared.rows.length>100)throw Error('Invalid native detection preparation receipt.');
    let tokenBytes=0;
    if(!prepared.rows.every((row,index)=>row && row.metadata_path==='manifest.json' && row.row_number===index+1
      && typeof row.row_sha256==='string' && /^[a-f0-9]{64}$/.test(row.row_sha256)
      && typeof row.token==='string' && row.token.length>0 && row.token.length<=4*1024*1024+65
      && (tokenBytes+=row.token.length)<=16*1024*1024))throw Error('Invalid or oversized prepared detection rows.');
    counts.total=prepared.rows.length;
    for(const [index,row] of prepared.rows.entries()){
      if(epoch!==detectionEpoch)return;
      if(detectionStopped){state='Stopped';break;}
      const body={token:row.token,request_id:crypto.randomUUID().replaceAll('-','')};
      const proof={request_id:body.request_id,row_number:row.row_number,row_sha256:row.row_sha256};
      counts.attempted++;const item=detectionRow(row.row_number,'importing','Validating native image and initial boxes…');
      detectionFlight={...proof,counts,item};
      try{
        const admission=await fetch('/api/workbench/native-detection-import/row',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        if(epoch!==detectionEpoch)return;
        const receipt=await admission.json();if(epoch!==detectionEpoch)return;
        if(!admission.ok){
          if(![400,409].includes(admission.status))throw Error(receipt.error||'Server failure');
          counts.rejected++;item.textContent=`Manifest record ${row.row_number} · rejected: ${String(receipt.error||'Admission failed.').slice(0,500)}`;
        }else{
          if(!detectionReceipt(receipt,proof) || receipt.review!=='draft')throw Error('Invalid detection admission receipt.');
          counts.created++;item.textContent=`Manifest record ${row.row_number} · created: ${receipt.record_id} · draft`;
        }
        detectionFlight=null;
      }catch(error){
        if(epoch!==detectionEpoch)return;
        counts.unknown++;state='Paused after uncertain response';detectionPending=detectionFlight;detectionFlight=null;
        item.textContent=`Manifest record ${row.row_number} · uncertain: creation was not confirmed. Check its saved result before retrying.`;break;
      }
      detectionSummary(counts,'Importing');
    }
    if(detectionStopped && state==='Complete')state='Stopped';detectionSummary(counts,state);
  }catch(error){if(epoch===detectionEpoch){$('native-detection-status').textContent=error.message;notice(error.message,true);}}
  finally{if(epoch===detectionEpoch){await detectionRefresh(epoch);if(epoch===detectionEpoch){detectionRunning=false;detectionControls();}}}
});
$('native-detection-check').addEventListener('click',async()=>{
  if(detectionRunning || !detectionPending)return;
  const pending=detectionPending,epoch=++detectionEpoch;detectionRunning=true;detectionControls();
  try{
    const response=await fetch('/api/workbench/import-result/'+pending.request_id);
    if(epoch!==detectionEpoch)return;
    const receipt=await response.json();if(epoch!==detectionEpoch)return;
    if(!response.ok)throw Error(receipt.error||'Saved result lookup failed.');
    if(typeof receipt.found!=='boolean')throw Error('Invalid saved-result observation.');
    if(!receipt.found){$('native-detection-status').textContent='No saved result is visible yet. This does not prove the in-flight record stopped. Inspect the collection before retrying.';return;}
    if(!detectionReceipt(receipt,pending))throw Error('Saved result does not match the uncertain record.');
    pending.item.textContent=`Manifest record ${pending.row_number} · created (saved admission confirmed): ${receipt.record_id}. Current bytes and review are separate.`;
    pending.counts.unknown--;pending.counts.created++;detectionSummary(pending.counts,'Paused; saved admission confirmed');detectionPending=null;
  }catch(error){if(epoch===detectionEpoch)notice(error.message,true);}
  finally{if(epoch===detectionEpoch){await detectionRefresh(epoch);if(epoch===detectionEpoch){detectionRunning=false;detectionControls();}}}
});
$('native-detection-dismiss').addEventListener('click',()=>{
  if(detectionRunning || !detectionPending)return;
  detectionPending=null;detectionControls();$('native-detection-status').textContent='Pending check dismissed; no rollback is implied. Inspect the collection before retrying.';
});
detectionControls();
