'use strict';
// Acquisition never changes selection. Only the explicit confirmed-import
// action below adds revision pairs; source owners retain normalization/review.
let bulkRunning = false, bulkStopped = false, bulkPending = null;
const bulkConfirmed = new Map();
function bulkControls() {
  for(const id of ['bulk-manifest','bulk-images','bulk-start'])$(id).disabled=bulkRunning;
  $('bulk-stop').disabled=!bulkRunning || bulkStopped;
  $('bulk-check').disabled=bulkRunning || !bulkPending;
  $('bulk-dismiss').disabled=bulkRunning || !bulkPending;
  $('bulk-select').disabled=bulkRunning || !bulkConfirmed.size;
}
function bulkSummary(counts, state) {
  $('bulk-status').textContent=`${state}: ${counts.created} created, ${counts.rejected} rejected, ${counts.unknown} uncertain; ${counts.total-counts.attempted} not attempted. All new records start as drafts.`;
}
function bulkRow(number, state, message) {
  const item=document.createElement('li');
  item.textContent=`Row ${number} · ${state}: ${String(message).slice(0,500)}`;
  $('bulk-results').append(item);return item;
}
function bulkManifest(buffer) {
  if(buffer.byteLength>8*1024*1024)throw Error('Choose a manifest at most 8 MiB.');
  let text;
  try{text=new TextDecoder('utf-8',{fatal:true}).decode(buffer);}catch{throw Error('Manifest must be valid UTF-8.');}
  const lines=text.split('\n');
  if(lines.at(-1)==='')lines.pop();
  if(lines.length>1000)throw Error('A manifest may contain at most 1,000 physical lines.');
  const rows=lines.map((line,index)=>({line,number:index+1})).filter(row=>row.line.trim());
  if(!rows.length)throw Error('Manifest contains no asset rows.');
  return rows;
}
function bulkReceipt(value, pending) {
  return value && /^[a-f0-9]{32}$/.test(value.record_id) && value.request_id===pending.request_id
    && value.row_number===pending.row_number && value.row_sha256===pending.row_sha256
    && ['text','image'].includes(value.kind) && typeof value.name==='string';
}
function bulkConfirmedReceipt(value, proof) {
  return bulkReceipt(value,proof) && typeof value.record_id==='string'
    && !bulkConfirmed.has(value.record_id)
    && value.kind===proof.kind && Number.isSafeInteger(value.revision) && value.revision>0
    && Number.isSafeInteger(value.source_revision) && value.source_revision>0;
}
function bulkRemember(value) {
  bulkConfirmed.set(value.record_id,{id:value.record_id,name:value.name,kind:value.kind,
    revision:value.revision,source_revision:value.source_revision});
}
async function bulkHash(line) {
  const hash=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(line));
  return [...new Uint8Array(hash)].map(byte=>byte.toString(16).padStart(2,'0')).join('');
}
async function bulkRefresh() {
  try{await refresh();}catch(error){notice('Imports are retained, but collection refresh failed: '+error.message,true);}
}
$('bulk-stop').addEventListener('click',()=>{
  bulkStopped=true;bulkControls();
  $('bulk-status').textContent='Stopping before the next admission. An in-flight row may still complete and remains in the collection.';
});
$('bulk-select').addEventListener('click',()=>{
  if(bulkRunning || !bulkConfirmed.size)return;
  const additions=[...bulkConfirmed.values()].filter(pair=>!selected.has(pair.id));
  if(selected.size+additions.length>5000){
    $('bulk-selection-status').textContent='Selection would exceed 5,000 records. Clear or reduce the current selection before adding this batch.';
    return;
  }
  for(const pair of additions)selected.set(pair.id,{...pair});
  selection(true);invalidateRelease();
  $('bulk-selection-status').textContent=`Added ${additions.length} confirmed imports; ${bulkConfirmed.size-additions.length} already selected pairs retained. Save selected records as a new fixed set when ready. Review states are unchanged.`;
  void bulkRefresh();
});
$('bulk-form').addEventListener('submit',async event=>{
  event.preventDefault();if(bulkRunning)return;
  if(bulkPending){notice('Check or dismiss the uncertain row before starting another batch.',true);return;}
  const manifest=$('bulk-manifest').files[0], files=[...$('bulk-images').files];
  bulkRunning=true;bulkStopped=false;bulkConfirmed.clear();bulkControls();$('bulk-results').replaceChildren();$('bulk-selection-status').textContent='';
  const counts={created:0,rejected:0,unknown:0,attempted:0,total:0};
  let state='Complete';
  try{
    if(!manifest)throw Error('Choose a JSONL manifest.');
    if(manifest.size>8*1024*1024)throw Error('Choose a manifest at most 8 MiB.');
    const rows=bulkManifest(await manifest.arrayBuffer());counts.total=rows.length;
    const images=new Map();
    for(const file of files){const matches=images.get(file.name)||[];matches.push(file);images.set(file.name,matches);}
    for(const row of rows){
      if(bulkStopped){state='Stopped';break;}
      let body, proof;
      try{
        if(new TextEncoder().encode(row.line).length>3*1024*1024)throw Error('Source row exceeds 3 MiB.');
        const parsed=JSON.parse(row.line);
        if(!parsed || Array.isArray(parsed) || typeof parsed!=='object')throw Error('Source row must be a JSON object.');
        body={source_name:manifest.name,row_number:row.number,line:row.line,request_id:crypto.randomUUID().replaceAll('-','')};
        if(parsed.kind==='image'){
          const matches=images.get(parsed.file)||[];
          if(matches.length!==1)throw Error(matches.length?'Image filename is ambiguous in the selected files.':'Referenced image was not selected.');
          body.image_name=matches[0].name;body.image=await readImportImage(matches[0]);
        }
        proof={request_id:body.request_id,row_number:row.number,row_sha256:await bulkHash(row.line),kind:parsed.kind};
      }catch(error){counts.attempted++;counts.rejected++;bulkRow(row.number,'rejected',error.message);bulkSummary(counts,'Importing');continue;}
      if(bulkStopped){state='Stopped';break;}
      counts.attempted++;
      try{
        const response=await fetch('/api/workbench/import-row',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        const result=await response.json();
        if(!response.ok){
          if([400,409].includes(response.status)){
            counts.rejected++;bulkRow(row.number,'rejected',result.error||'Row admission failed.');
          }else{
            counts.unknown++;state='Paused after server failure';
            const item=bulkRow(row.number,'uncertain',(result.error||'Server failed.')+' Creation was not confirmed. Check the saved result before retrying.');
            bulkPending={...proof,counts,item};break;
          }
        }else{
          if(!bulkConfirmedReceipt(result,proof))throw Error('Invalid admission receipt.');
          bulkRemember(result);
          counts.created++;bulkRow(row.number,'created',`${result.name} · ${result.record_id}`);
        }
      }catch(error){
        counts.unknown++;state='Paused after uncertain response';
        const item=bulkRow(row.number,'uncertain','Response lost or invalid. This row may have been admitted. Check its saved result before retrying.');
        bulkPending={...proof,counts,item};break;
      }
      bulkSummary(counts,'Importing');
    }
    if(bulkStopped && state==='Complete')state='Stopped';
    bulkSummary(counts,state);
  }catch(error){$('bulk-status').textContent=error.message;notice(error.message,true);}
  finally{bulkRunning=false;bulkControls();await bulkRefresh();}
});
$('bulk-check').addEventListener('click',async()=>{
  if(bulkRunning || !bulkPending)return;
  const pending=bulkPending;bulkRunning=true;bulkControls();
  try{
    const response=await fetch('/api/workbench/import-result/'+pending.request_id);
    const result=await response.json();
    if(!response.ok)throw Error(result.error||'Result check failed.');
    if(result.found===false){$('bulk-status').textContent='No saved result is visible yet. This does not prove the in-flight row stopped. Inspect the collection before retrying.';return;}
    if(result.found!==true || !bulkConfirmedReceipt(result,pending))throw Error('Saved result does not match the pending row.');
    bulkRemember(result);
    pending.item.textContent=`Row ${pending.row_number} · created (saved result confirmed): ${result.name} · ${result.record_id}`;
    pending.counts.unknown--;pending.counts.created++;bulkSummary(pending.counts,'Paused; saved result confirmed');bulkPending=null;
  }catch(error){notice(error.message,true);}
  finally{bulkRunning=false;bulkControls();await bulkRefresh();}
});
$('bulk-dismiss').addEventListener('click',()=>{
  if(bulkRunning || !bulkPending)return;
  bulkPending=null;bulkControls();
  $('bulk-status').textContent='Pending check dismissed; no rollback is implied. Inspect the collection before retrying. Existing records are rejected without changes.';
});
bulkControls();
