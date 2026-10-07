'use strict';
// This form owns native classification batch intent, never editor or selection.
let nativeTextRunning=false, nativeTextStopped=false, nativeTextPending=null;
function nativeTextControls(){
  for(const id of ['native-text-archive','native-text-start'])$(id).disabled=nativeTextRunning;
  $('native-text-stop').disabled=!nativeTextRunning || nativeTextStopped;
  for(const id of ['native-text-check','native-text-dismiss'])$(id).disabled=nativeTextRunning || !nativeTextPending;
}
function nativeTextSummary(counts,state){
  $('native-text-status').textContent=`${state}: ${counts.created} created, ${counts.rejected} rejected, ${counts.unknown} uncertain; ${counts.total-counts.attempted} not attempted. New classification drafts use exported text; upstream original text is unavailable. Human review is required.`;
}
function nativeTextRow(row,state,message){
  const item=document.createElement('li');item.textContent=`${row.metadata_path} · row ${row.row_number ?? 'missing'} · ${state}: ${String(message).slice(0,500)}`;
  $('native-text-results').append(item);return item;
}
async function nativeTextArchive(file){
  if(!file || !file.size || file.size>8*1024*1024)throw Error('Choose one native release ZIP of at most 8 MiB.');
  const buffer=await file.arrayBuffer();
  if(buffer.byteLength!==file.size)throw Error('Archive size changed during reading.');
  const bytes=new Uint8Array(buffer),parts=[];
  for(let start=0;start<bytes.length;start+=16384)parts.push(String.fromCharCode(...bytes.subarray(start,start+16384)));
  return {source_name:file.name,archive:btoa(parts.join(''))};
}
$('native-text-stop').addEventListener('click',()=>{
  nativeTextStopped=true;nativeTextControls();$('native-text-status').textContent='Stopping before the next classification admission. An in-flight record may still complete.';
});
$('native-text-form').addEventListener('submit',async event=>{
  event.preventDefault();if(nativeTextRunning)return;
  if(nativeTextPending){notice('Check or dismiss the uncertain classification row before starting again.',true);return;}
  const file=$('native-text-archive').files[0];nativeTextRunning=true;nativeTextStopped=false;nativeTextControls();$('native-text-results').replaceChildren();
  const counts={created:0,rejected:0,unknown:0,total:0,attempted:0};let state='Complete';
  try{
    const source=await nativeTextArchive(file);
    if(nativeTextStopped){nativeTextSummary(counts,'Stopped before preparation');return;}
    const response=await fetch('/api/workbench/native-text-import/prepare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(source)});
    const prepared=await response.json();
    if(!response.ok)throw Error(prepared.error||'Native release preparation failed.');
    if(prepared.format!=='canonical_v1' || prepared.schema_version!==1 || prepared.input_basis!=='consumed_exported_text' || prepared.upstream_original!=='unavailable' || !/^[a-f0-9]{64}$/.test(prepared.archive_sha256) || !Array.isArray(prepared.rows) || !prepared.rows.length || prepared.rows.length>2000)throw Error('Invalid native classification preparation receipt.');
    counts.total=prepared.rows.length;
    for(const row of prepared.rows){
      if(nativeTextStopped){state='Stopped';break;}
      if(row.error){counts.attempted++;counts.rejected++;nativeTextRow(row,'rejected',row.error);continue;}
      if(!/^(train|validation|test)\/records\.jsonl$/.test(row.metadata_path) || !Number.isInteger(row.row_number) || row.row_number<1 || row.row_number>1000 || !/^[a-f0-9]{64}$/.test(row.row_sha256) || typeof row.token!=='string')throw Error('Invalid prepared classification row.');
      const body={token:row.token,request_id:crypto.randomUUID().replaceAll('-','')};
      const proof={request_id:body.request_id,row_number:row.row_number,row_sha256:row.row_sha256};
      counts.attempted++;
      try{
        const admission=await fetch('/api/workbench/native-text-import/row',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),receipt=await admission.json();
        if(!admission.ok && [400,409].includes(admission.status)){
          counts.rejected++;nativeTextRow(row,'rejected',receipt.error||'Classification admission failed.');
        }else{
          if(!admission.ok)throw Error(receipt.error||'Server failure.');
          if(!bulkReceipt(receipt,proof) || receipt.kind!=='text' || receipt.review!=='draft')throw Error('Invalid classification admission receipt.');
          counts.created++;nativeTextRow(row,'created',receipt.record_id+' · draft · exported text; upstream original unavailable');
        }
      }catch(error){
        counts.unknown++;state='Paused after uncertain response';
        const item=nativeTextRow(row,'uncertain','Creation was not confirmed. Check the saved result before retrying.');
        nativeTextPending={...proof,row,counts,item};break;
      }
      nativeTextSummary(counts,'Importing');
    }
    if(nativeTextStopped && state==='Complete')state='Stopped';nativeTextSummary(counts,state);
  }catch(error){$('native-text-status').textContent=error.message;notice(error.message,true);}
  finally{await bulkRefresh();nativeTextRunning=false;nativeTextControls();}
});
$('native-text-check').addEventListener('click',async()=>{
  if(nativeTextRunning || !nativeTextPending)return;
  const pending=nativeTextPending;nativeTextRunning=true;nativeTextControls();
  try{
    const response=await fetch('/api/workbench/import-result/'+pending.request_id),receipt=await response.json();
    if(!response.ok)throw Error(receipt.error||'Saved result lookup failed.');
    if(!receipt.found){$('native-text-status').textContent='No saved result is visible yet. This does not prove the in-flight record stopped. Inspect the collection before retrying.';return;}
    if(!bulkReceipt(receipt,pending) || receipt.kind!=='text')throw Error('Saved result does not match the pending classification row.');
    pending.item.textContent=`${pending.row.metadata_path} · row ${pending.row_number} · created (saved result confirmed): ${receipt.record_id} · exported text; upstream original unavailable`;
    pending.counts.unknown--;pending.counts.created++;nativeTextSummary(pending.counts,'Paused; saved result confirmed');nativeTextPending=null;
  }catch(error){notice(error.message,true);}
  finally{await bulkRefresh();nativeTextRunning=false;nativeTextControls();}
});
$('native-text-dismiss').addEventListener('click',()=>{
  if(nativeTextRunning || !nativeTextPending)return;
  nativeTextPending=null;nativeTextControls();$('native-text-status').textContent='Pending check dismissed; no rollback is implied. Inspect the collection before retrying.';
});
nativeTextControls();
