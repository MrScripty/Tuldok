'use strict';
// This controller owns only the native-caption form. Existing helpers own image
// reads, receipt matching, hashes and collection refresh; editor/selection stay put.
let captionRunning=false, captionStopped=false, captionPending=null;
function captionControls(){
  for(const id of ['caption-folder','caption-start'])$(id).disabled=captionRunning;
  $('caption-stop').disabled=!captionRunning || captionStopped;
  for(const id of ['caption-check','caption-dismiss'])$(id).disabled=captionRunning || !captionPending;
}
function captionSummary(counts,state){
  $('caption-status').textContent=`${state}: ${counts.created} created, ${counts.rejected} rejected, ${counts.unknown} uncertain; ${counts.total-counts.attempted} not attempted. Imported captions require human review; original split assignments are retained.`;
}
function captionRow(row,state,message){
  const item=document.createElement('li');item.textContent=`${row.asset} · row ${row.row_number} · ${state}: ${String(message).slice(0,500)}`;
  $('caption-results').append(item);return item;
}
function captionFiles(files){
  if(!files.length || files.length>1100)throw Error('Choose one expanded native caption release folder with at most 1,100 files.');
  const roots=new Set(),paths=new Map();
  for(const file of files){
    const parts=(file.webkitRelativePath||'').split('/');
    if(parts.length<2 || parts.some(part=>!part || part==='.' || part==='..' || part.includes('\\')))throw Error('Folder files require exact safe relative paths.');
    roots.add(parts.shift());const relative=parts.join('/'),matches=paths.get(relative)||[];matches.push(file);paths.set(relative,matches);
  }
  if(roots.size!==1)throw Error('Choose files from exactly one source folder.');
  return paths;
}
async function captionSources(paths){
  const names=['manifest.json','train/metadata.jsonl','val/metadata.jsonl','test/metadata.jsonl'];
  const files=names.map(name=>{const matches=paths.get(name)||[];if(matches.length!==1)throw Error(`Required source ${name} is missing or ambiguous.`);return matches[0];});
  if(files.reduce((sum,file)=>sum+file.size,0)>8*1024*1024)throw Error('Combined manifest and metadata must be at most 8 MiB.');
  const texts=[];
  for(const file of files){
    const bytes=await file.arrayBuffer();
    if(bytes.byteLength!==file.size)throw Error('Source file size changed during reading.');
    try{texts.push(new TextDecoder('utf-8',{fatal:true,ignoreBOM:true}).decode(bytes));}catch{throw Error('Source files must be valid UTF-8.');}
  }
  return {manifest:texts[0],metadata:{train:texts[1],val:texts[2],test:texts[3]}};
}
$('caption-stop').addEventListener('click',()=>{captionStopped=true;captionControls();$('caption-status').textContent='Stopping before the next caption admission. An in-flight row may still complete.';});
$('caption-form').addEventListener('submit',async event=>{
  event.preventDefault();if(captionRunning)return;
  if(captionPending){notice('Check or dismiss the uncertain caption row before importing again.',true);return;}
  const files=[...$('caption-folder').files];captionRunning=true;captionStopped=false;captionControls();$('caption-results').replaceChildren();
  const counts={created:0,rejected:0,unknown:0,total:0,attempted:0};let state='Complete';
  try{
    const paths=captionFiles(files),source=await captionSources(paths);
    if(captionStopped){captionSummary(counts,'Stopped before preparation');return;}
    const prepared=await fetch('/api/workbench/caption-import/prepare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(source)});
    const contract=await prepared.json();
    if(!prepared.ok)throw Error(contract.error||'Native caption preparation failed.');
    if(contract.format!=='image_caption_v1' || !Array.isArray(contract.rows) || !contract.rows.length || contract.rows.length>1000)throw Error('Invalid native preparation receipt.');
    counts.total=contract.rows.length;
    for(const row of contract.rows){
      if(captionStopped){state='Stopped';break;}
      let body,proof;
      try{
        if(!/^(train|val|test)\/[a-f0-9]{32}\.png$/.test(row.asset) || !Number.isInteger(row.row_number) || row.row_number<1 || row.row_number>1000 || !/^[a-f0-9]{64}$/.test(row.row_sha256) || typeof row.token!=='string')throw Error('Invalid prepared caption row.');
        const matches=paths.get(row.asset)||[];
        if(matches.length!==1)throw Error(matches.length?'Image path is ambiguous in the selected folder.':'Referenced image is missing from the selected folder.');
        body={asset:row.asset,token:row.token,image:await readImportImage(matches[0]),request_id:crypto.randomUUID().replaceAll('-','')};
        proof={request_id:body.request_id,row_number:row.row_number,row_sha256:row.row_sha256};
      }catch(error){counts.attempted++;counts.rejected++;captionRow(row,'rejected',error.message);continue;}
      if(captionStopped){state='Stopped';break;}
      counts.attempted++;
      try{
        const response=await fetch('/api/workbench/caption-import/row',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}),receipt=await response.json();
        if(!response.ok && [400,409].includes(response.status)){
          counts.rejected++;captionRow(row,'rejected',receipt.error||'Caption admission failed.');
        }else{
          if(!response.ok)throw Error(receipt.error||'Server failure.');
          if(!bulkReceipt(receipt,proof) || receipt.kind!=='image' || receipt.review!=='draft')throw Error('Invalid caption admission receipt.');
          counts.created++;captionRow(row,'created',receipt.record_id+' · draft caption');
        }
      }catch(error){
        counts.unknown++;state='Paused after uncertain response';
        const item=captionRow(row,'uncertain','Creation was not confirmed. Check the saved result before retrying.');
        captionPending={...proof,row,counts,item};break;
      }
      captionSummary(counts,'Importing');
    }
    if(captionStopped && state==='Complete')state='Stopped';captionSummary(counts,state);
  }catch(error){$('caption-status').textContent=error.message;notice(error.message,true);}
  finally{captionRunning=false;captionControls();await bulkRefresh();}
});
$('caption-check').addEventListener('click',async()=>{
  if(captionRunning || !captionPending)return;
  const pending=captionPending;captionRunning=true;captionControls();
  try{
    const response=await fetch('/api/workbench/import-result/'+pending.request_id),receipt=await response.json();
    if(!response.ok)throw Error(receipt.error||'Saved result lookup failed.');
    if(!receipt.found){$('caption-status').textContent='No saved result is visible yet. This does not prove the in-flight row stopped. Inspect the collection before retrying.';return;}
    if(!bulkReceipt(receipt,pending) || receipt.kind!=='image')throw Error('Saved result does not match the pending caption row.');
    pending.item.textContent=`${pending.row.asset} · created (saved result confirmed): ${receipt.record_id}`;
    pending.counts.unknown--;pending.counts.created++;captionSummary(pending.counts,'Paused; saved result confirmed');captionPending=null;
  }catch(error){notice(error.message,true);}
  finally{captionRunning=false;captionControls();await bulkRefresh();}
});
$('caption-dismiss').addEventListener('click',()=>{
  if(captionRunning || !captionPending)return;captionPending=null;captionControls();
  $('caption-status').textContent='Pending check dismissed; no rollback is implied. Inspect the collection before retrying. Batch progress is kept only in this page.';
});
captionControls();
