'use strict';
let binaryMeshImportBusy=false,binaryMeshToken=null,binaryMeshCancelRequested=false,binaryMeshGeneration=0,binaryMeshDeparted=false;
const binaryMeshRequest=(action,body)=>api('mesh-binary/'+action,body);
function binaryMeshChunk(raw){let text='';for(let i=0;i<raw.length;i+=16384)text+=String.fromCharCode(...raw.subarray(i,i+16384));return btoa(text);}
$('binary-mesh-cancel').addEventListener('click',()=>{binaryMeshCancelRequested=true;$('binary-mesh-status').textContent='Cancelling upload…';});
$('binary-mesh-form').addEventListener('submit',async event=>{
  event.preventDefault();if(binaryMeshImportBusy)return;
  binaryMeshImportBusy=true;binaryMeshCancelRequested=false;
  let token=null;
  const generation=++binaryMeshGeneration,status=$('binary-mesh-status'),controls=[...$('binary-mesh-form').querySelectorAll('input,button')];
  controls.forEach(item=>item.disabled=true);$('binary-mesh-cancel').disabled=false;
  const owns=()=>generation===binaryMeshGeneration;
  try{
    const file=$('binary-mesh-archive').files[0];
    if(!file||!file.size||file.size>12582912)throw Error('Choose a complete source-bound ZIP, at most12MiB.');
    const name=$('binary-mesh-name').value,group=$('binary-mesh-group').value.trim(),rights=$('binary-mesh-rights').value||'unknown';
    status.textContent='Checking the bounded file hash…';
    // At most one12MiB hashing buffer; transport then reads only64KiB slices.
    const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',await file.arrayBuffer()))].map(x=>x.toString(16).padStart(2,'0')).join('');
    if(binaryMeshCancelRequested||!owns())throw Error('Upload cancelled.');
    const started=await binaryMeshRequest('start',{bytes:file.size,sha256:hash,name,groups:group?[group]:[],rights});
    if(typeof started.token!=='string'||started.chunk_bytes!==65536||started.offset!==0)throw Error('Invalid upload acknowledgement.');
    token=started.token;
    if(!owns())throw Error('Upload cancelled.');
    binaryMeshToken=token;
    for(let offset=0;offset<file.size;){
      if(binaryMeshCancelRequested||!owns())throw Error('Upload cancelled.');
      const raw=new Uint8Array(await file.slice(offset,offset+65536).arrayBuffer());
      const result=await binaryMeshRequest('chunk',{token,offset,data:binaryMeshChunk(raw)});
      if(result.token!==token||result.offset!==offset+raw.length)throw Error('Invalid chunk acknowledgement.');
      offset=result.offset;if(owns())status.textContent=`Uploaded ${offset} of ${file.size} bytes. Source validation follows.`;
    }
    if(binaryMeshCancelRequested||!owns())throw Error('Upload cancelled.');
    $('binary-mesh-cancel').disabled=true;status.textContent='Validating the complete source and native geometry…';
    const record=await binaryMeshRequest('finish',{token});
    if(binaryMeshToken===token)binaryMeshToken=null;token=null;
    if(owns())status.textContent=`Imported ${record.name}: ${record.mesh.vertex_count} vertices, ${record.mesh.triangle_count} triangles, unreviewed. Open it to inspect and review.`;
    if(owns())await refresh(owns);
  }catch(error){if(owns())status.textContent=error.message+' Check the collection before repeating a request whose response was lost.';}
  finally{
    if(binaryMeshToken===token)binaryMeshToken=null;
    if(token)try{await binaryMeshRequest('cancel',{token});}catch(_){/* Lost finish may already have published; never retry it. */}
    if(owns()){binaryMeshImportBusy=false;controls.forEach(item=>item.disabled=false);$('binary-mesh-cancel').disabled=true;}
  }
});
window.addEventListener('pagehide',()=>{
  binaryMeshDeparted=binaryMeshImportBusy;++binaryMeshGeneration;binaryMeshCancelRequested=true;
  const token=binaryMeshToken;binaryMeshToken=null;
  if(token)fetch('/api/workbench/mesh-binary/cancel',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({token}),keepalive:true}).catch(()=>{});
});
window.addEventListener('pageshow',()=>{
  if(!binaryMeshDeparted)return;
  binaryMeshDeparted=false;binaryMeshImportBusy=false;binaryMeshCancelRequested=false;
  [...$('binary-mesh-form').querySelectorAll('input,button')].forEach(item=>item.disabled=false);
  $('binary-mesh-cancel').disabled=true;
  $('binary-mesh-status').textContent='Upload interrupted by navigation. Check the collection before deliberately starting another upload; a lost finish may already have published.';
});
