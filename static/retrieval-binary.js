'use strict';
const retrievalBinaryStates=['relevant','not_relevant','unjudged'];
let retrievalBinaryRows=[],retrievalBinaryGeneration=0,retrievalBinaryTask='';
const retrievalBinaryReads=new Map();
const retrievalBinaryImports={query:{busy:false,epoch:0,departed:false},native:{busy:false,epoch:0,departed:false}};
function retrievalBinaryStrip(text) {
  return text.replace(/^[\u0009-\u000D\u001C-\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]+|[\u0009-\u000D\u001C-\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]+$/gu,'');
}
function retrievalBinaryReference(value) {
  if(!value||Array.isArray(value)||typeof value!=='object'||Object.keys(value).sort().join()!=='id,revision,source_revision'||
     typeof value.id!=='string'||!/^[a-f0-9]{32}$/.test(value.id)||!Number.isSafeInteger(value.revision)||value.revision<1||
     !Number.isSafeInteger(value.source_revision)||value.source_revision<1) throw Error('Use an exact document ID and positive safe-integer record/source revisions.');
  return {id:value.id,revision:value.revision,source_revision:value.source_revision};
}
function retrievalBinaryJudgments(value) {
  if(!Array.isArray(value)||value.length<1||value.length>30) throw Error('Provide 1–30 explicit document judgments.');
  const seen=new Set();
  return value.map(row=>{
    if(!row||Array.isArray(row)||typeof row!=='object'||Object.keys(row).sort().join()!=='document,relevance'||!retrievalBinaryStates.includes(row.relevance)) throw Error('Each judgment requires an exact document reference and relevant, not_relevant or unjudged.');
    const document=retrievalBinaryReference(row.document);
    if(seen.has(document.id)) throw Error('A document may have only one explicit judgment.');
    seen.add(document.id);return {document,relevance:row.relevance};
  });
}
function retrievalBinaryCancelReads() {
  const pending=retrievalBinaryReads.size>0;
  ++retrievalBinaryGeneration;for(const controller of retrievalBinaryReads.values())controller.abort();retrievalBinaryReads.clear();
  if(pending){$('retrieval-binary-status').textContent='Earlier reference inspection canceled; later editor intent is retained.';retrievalBinaryRenderRows();}
}
function retrievalBinaryEditable() {
  return current?.kind==='text'&&$('task').value==='text_retrieval_binary'&&!$('editor').dataset.busy&&!(typeof rightsBusy!=='undefined'&&rightsBusy);
}
function retrievalBinaryChanged() {retrievalBinaryCancelReads();markDirty();}
function retrievalBinaryControls(task) {
  if(task!==retrievalBinaryTask){retrievalBinaryCancelReads();retrievalBinaryTask=task;}
  $('retrieval-binary-controls').hidden=task!=='text_retrieval_binary';
  $('retrieval-binary-judgments-control').hidden=$('retrieval-binary-role').value!=='query';
}
function retrievalBinaryShown(record) {
  retrievalBinaryCancelReads();
  const annotation=record.task==='text_retrieval_binary'?record.annotation:null;
  const declared=record.provenance?.acquisition?.format==='text_retrieval_binary_query_v2'?record.provenance.acquisition.declared_judgments:null;
  const rows=annotation?.role==='query'?annotation.judgments:declared;
  retrievalBinaryRows=rows?retrievalBinaryJudgments(rows):[];
  $('retrieval-binary-role').value=annotation?.role||(declared?'query':'document');
  $('retrieval-binary-note').value=annotation?.note||'';
  $('retrieval-binary-current-ref').textContent=JSON.stringify({id:record.id,revision:record.revision,source_revision:record.source_revision});
  $('retrieval-binary-status').textContent='Explicit judgments are separate from review. Omitted relationships remain UNJUDGED. Refresh references deliberately after document edits.';
  retrievalBinaryRenderRows();retrievalBinaryControls(record.task);
}
function retrievalBinaryRenderRows() {
  const holder=$('retrieval-binary-judgments');holder.replaceChildren();
  for(const row of retrievalBinaryRows) {
    const item=document.createElement('li'),reference=document.createElement('code'),select=document.createElement('select');
    reference.textContent=JSON.stringify(row.document);select.setAttribute('aria-label','Relevance for document '+row.document.id);
    for(const value of retrievalBinaryStates){const option=document.createElement('option');option.value=value;option.textContent=value.replaceAll('_',' ');select.append(option);}
    select.value=row.relevance;
    select.addEventListener('change',()=>{if(!retrievalBinaryEditable())return;row.relevance=select.value;retrievalBinaryChanged();retrievalBinaryRenderRows();});
    const remove=document.createElement('button');remove.type='button';remove.textContent='Remove';remove.setAttribute('aria-label','Remove judgment '+row.document.id);
    remove.addEventListener('click',()=>{if(!retrievalBinaryEditable())return;retrievalBinaryRows=retrievalBinaryRows.filter(value=>value!==row);retrievalBinaryChanged();retrievalBinaryRenderRows();});
    const refresh=document.createElement('button');refresh.type='button';refresh.textContent='Refresh exact reference';refresh.setAttribute('aria-label','Refresh document reference '+row.document.id);refresh.disabled=retrievalBinaryReads.has(row);
    refresh.addEventListener('click',()=>retrievalBinaryRefresh(row));item.append(reference,select,remove,refresh);holder.append(item);
  }
}
async function retrievalBinaryRefresh(row) {
  if(!retrievalBinaryEditable()||$('retrieval-binary-role').value!=='query'||!retrievalBinaryRows.includes(row)||retrievalBinaryReads.has(row))return;
  const record=current,generation=retrievalBinaryGeneration,epoch=++editorEpoch,old=JSON.stringify(row.document),controller=new AbortController();
  retrievalBinaryReads.set(row,controller);retrievalBinaryRenderRows();
  const owns=()=>generation===retrievalBinaryGeneration&&editorEpoch===epoch&&current===record&&$('task').value==='text_retrieval_binary'&&$('retrieval-binary-role').value==='query'&&retrievalBinaryRows.includes(row)&&JSON.stringify(row.document)===old;
  $('retrieval-binary-status').textContent='Reading the current separately reviewed document reference…';
  try {
    const response=await fetch('/api/workbench/records/'+row.document.id,{signal:controller.signal}),result=await response.json();
    if(!owns())return;
    if(!response.ok)throw Error(result.error||'Document reference unavailable.');
    const reference=retrievalBinaryReference({id:result.id,revision:result.revision,source_revision:result.source_revision});
    if(reference.id!==row.document.id||result.kind!=='text'||result.task!=='text_retrieval_binary'||result.annotation?.role!=='document'||result.review!=='human_reviewed'||result.source_available!==true||result.source_lineage_known!==true)throw Error('Reference must identify an available, separately human-reviewed binary document with known source lineage.');
    row.document=reference;retrievalBinaryChanged();retrievalBinaryRenderRows();
    $('retrieval-binary-status').textContent='Exact document reference refreshed as a draft edit. Save, reopen and separately review the query; judgments were not changed.';
  } catch(error) {if(owns()&&error.name!=='AbortError')$('retrieval-binary-status').textContent=error.message;}
  finally {if(retrievalBinaryReads.get(row)===controller)retrievalBinaryReads.delete(row);if(current===record&&retrievalBinaryRows.includes(row))retrievalBinaryRenderRows();}
}
function retrievalBinaryAnnotation() {
  if(retrievalBinaryReads.size)throw Error('Finish or cancel reference inspection before saving.');
  const role=$('retrieval-binary-role').value,note=retrievalBinaryStrip($('retrieval-binary-note').value);
  if(!['document','query'].includes(role)||!note||Array.from(note).length>4000)throw Error('Choose document/query and provide a nonempty inspection note, at most 4,000 Unicode codepoints.');
  return role==='document'?{role,note}:{role,note,judgments:retrievalBinaryJudgments(retrievalBinaryRows)};
}
$('retrieval-binary-role').addEventListener('change',()=>{retrievalBinaryChanged();retrievalBinaryControls($('task').value);retrievalBinaryRenderRows();});
$('retrieval-binary-note').addEventListener('input',()=>retrievalBinaryCancelReads());
$('retrieval-binary-add').addEventListener('click',()=>{
  if(!retrievalBinaryEditable()||$('retrieval-binary-role').value!=='query')return;
  try {
    const document=retrievalBinaryReference(JSON.parse($('retrieval-binary-document-ref').value)),relevance=$('retrieval-binary-relevance').value;
    retrievalBinaryRows=retrievalBinaryJudgments([...retrievalBinaryRows,{document,relevance}]);retrievalBinaryChanged();retrievalBinaryRenderRows();
    $('retrieval-binary-status').textContent='Explicit judgment added to the draft. Save checks the current document revision and immutable parent association.';
  } catch(error) {$('retrieval-binary-status').textContent=error.message;}
});
function retrievalBinaryImportControls(type) {return [...$('retrieval-binary-'+(type==='query'?'query':'native')+'-form').querySelectorAll('input,textarea,select,button')];}
async function retrievalBinaryHash(raw) {
  const hash=await crypto.subtle.digest('SHA-256',raw);return [...new Uint8Array(hash)].map(value=>value.toString(16).padStart(2,'0')).join('');
}
function retrievalBinaryDraft(record) {
  return record&&record.kind==='text'&&typeof record.id==='string'&&/^[a-f0-9]{32}$/.test(record.id)&&record.review==='draft'&&record.revision===1&&record.source_revision===1&&record.source_available===true&&record.source_lineage_known===true&&record.provenance?.rights==='unknown';
}
window.addEventListener('pagehide',()=>{retrievalBinaryCancelReads();for(const state of Object.values(retrievalBinaryImports)){++state.epoch;state.departed=true;}});
window.addEventListener('pageshow',()=>{for(const [type,state] of Object.entries(retrievalBinaryImports)){
  if(state.busy)$('retrieval-binary-'+type+'-status').textContent='Earlier admission may have completed. Inspect the collection before repeating it; no request was replayed.';
  ++state.epoch;state.departed=false;state.busy=false;retrievalBinaryImportControls(type).forEach(control=>control.disabled=false);
}});
async function retrievalBinaryImport(type,prepare,validate) {
  const state=retrievalBinaryImports[type];if(state.busy||state.departed)return;
  const epoch=++state.epoch,live=()=>epoch===state.epoch&&!state.departed,controls=retrievalBinaryImportControls(type),status=$('retrieval-binary-'+type+'-status');
  state.busy=true;controls.forEach(control=>control.disabled=true);
  try {
    const captured=prepare();status.textContent='Preparing bounded binary relevance draft admission…';
    const prepared=await captured;if(!live())return;
    const raw=JSON.stringify(prepared.body);if(new TextEncoder().encode(raw).length>prepared.maximum)throw Error('Binary relevance request exceeds its bounded profile.');
    const response=await fetch(prepared.route,{method:'POST',headers:{'Content-Type':'application/json'},body:raw});if(!live())return;
    const result=await response.json();if(!live())return;
    if(!response.ok)throw Error(result.error||'Binary relevance import failed.');
    validate(result,prepared);status.textContent='Draft admission confirmed. Inspect the new sources in the collection; review documents before deliberately repairing and reviewing query references. All omitted relationships remain UNJUDGED.';
    if(type==='native')$('retrieval-binary-native-evidence').textContent=JSON.stringify(result,null,2);
    await refresh(live);
  } catch(error) {if(live())status.textContent=error.message+' Inspect the collection before repeating a request with an uncertain outcome. Requests are not replayed.';}
  finally {if(live()){state.busy=false;controls.forEach(control=>control.disabled=false);}}
}
$('retrieval-binary-query-form').addEventListener('submit',event=>{
  event.preventDefault();retrievalBinaryImport('query',async()=>{
    const body={name:$('retrieval-binary-query-name').value,text:$('retrieval-binary-query-text').value,groups:[retrievalBinaryStrip($('retrieval-binary-query-group').value)],rights:$('retrieval-binary-query-rights').value||'unknown',judgments:retrievalBinaryJudgments(JSON.parse($('retrieval-binary-query-judgments').value))};
    const canonical=body.text.replace(/\r\n?/g,'\n').normalize('NFC');
    const [contentHash,sourceHash]=await Promise.all([retrievalBinaryHash(new TextEncoder().encode(canonical)),retrievalBinaryHash(new TextEncoder().encode(body.text))]);
    return {body,canonical,contentHash,sourceHash,maximum:1048576,route:'/api/workbench/retrieval-binary-query'};
  },(result,prepared)=>{
    const body=prepared.body;
    if(!result||result.kind!=='text'||typeof result.id!=='string'||!/^[a-f0-9]{32}$/.test(result.id)||result.task!=='text_classification'||result.annotation!==null||result.review!=='draft'||result.revision!==1||result.source_revision!==1||result.source_available!==true||result.text!==prepared.canonical||result.content_hash!==prepared.contentHash||result.source_sha256!==prepared.sourceHash||result.name!==retrievalBinaryStrip(body.name)||JSON.stringify(result.groups)!==JSON.stringify(body.groups)||result.provenance?.rights!==retrievalBinaryStrip(body.rights)||JSON.stringify(result.parents)!==JSON.stringify(body.judgments.map(row=>row.document.id))||result.provenance?.acquisition?.format!=='text_retrieval_binary_query_v2'||JSON.stringify(retrievalBinaryJudgments(result.provenance.acquisition.declared_judgments))!==JSON.stringify(body.judgments))throw Error('Uncertain binary query import response.');
  });
});
$('retrieval-binary-native-form').addEventListener('submit',event=>{
  event.preventDefault();retrievalBinaryImport('native',async()=>{
    const file=$('retrieval-binary-native-archive').files[0];
    if(!file||!file.size||file.size>9437184)throw Error('Choose a complete stored binary relevance ZIP, at most 9 MiB.');
    const raw=new Uint8Array(await file.arrayBuffer());if(raw.length!==file.size||!raw.length||raw.length>9437184)throw Error('Binary relevance ZIP byte count changed.');
    const digest=await retrievalBinaryHash(raw);let text='';for(let offset=0;offset<raw.length;offset+=32768)text+=String.fromCharCode(...raw.subarray(offset,offset+32768));
    return {body:{archive:btoa(text),sha256:digest},maximum:13631488,route:'/api/workbench/retrieval-binary-import'};
  },(result,prepared)=>{
    if(!result||result.release_sha256!==prepared.body.sha256||!Array.isArray(result.records)||!result.records.length||result.records.length>128||!result.id_map||Array.isArray(result.id_map)||typeof result.id_map!=='object'||Object.keys(result.id_map).length!==result.records.length)throw Error('Uncertain binary release import response.');
    const localIDs=new Set(result.records.map(record=>record.id)),values=Object.values(result.id_map);
    if(localIDs.size!==result.records.length||new Set(values).size!==values.length||Object.entries(result.id_map).some(([oldID,newID])=>!/^[a-f0-9]{32}$/.test(oldID)||typeof newID!=='string'||!/^[a-f0-9]{32}$/.test(newID)||oldID===newID||!localIDs.has(newID)))throw Error('Uncertain binary release ID mapping.');
    for(const record of result.records){
      if(!retrievalBinaryDraft(record)||record.task!=='text_retrieval_binary'||!record.annotation||!['document','query'].includes(record.annotation.role)||typeof record.annotation.note!=='string'||!retrievalBinaryStrip(record.annotation.note)||!Array.isArray(record.parents)||record.parents.some(id=>!localIDs.has(id)))throw Error('Uncertain binary release draft response.');
      const acquisition=record.provenance.acquisition,upstream=acquisition?.upstream_record;
      if(acquisition?.format!=='native_retrieval_binary_v2'||acquisition.release_sha256!==prepared.body.sha256||!upstream||result.id_map[upstream.id]!==record.id||
         typeof acquisition.source_family!=='string'||!acquisition.source_family||!['train','validation','test'].includes(acquisition.source_split)||record.source_split!==acquisition.source_split||
         record.text!==upstream.text||record.name!==upstream.name||record.content_hash!==upstream.content_hash||record.source_sha256!==record.content_hash||
         record.annotation.role!==upstream.annotation?.role||record.annotation.note!==upstream.annotation?.note||!Array.isArray(upstream.parents)||
         JSON.stringify(record.parents)!==JSON.stringify(upstream.parents.filter(id=>Object.hasOwn(result.id_map,id)).map(id=>result.id_map[id])))throw Error('Uncertain binary release source evidence.');
      if(record.annotation.role==='query'){
        const expected=retrievalBinaryJudgments(upstream.annotation.judgments).map(row=>({document:{id:result.id_map[row.document.id],revision:1,source_revision:1},relevance:row.relevance}));
        if(JSON.stringify(retrievalBinaryJudgments(record.annotation.judgments))!==JSON.stringify(expected))throw Error('Uncertain binary release judgment mapping.');
      }
      if(record.annotation.role==='query')for(const row of retrievalBinaryJudgments(record.annotation.judgments)){
        const target=result.records.find(value=>value.id===row.document.id);
        if(!target||target.annotation?.role!=='document'||row.document.revision!==target.revision||row.document.source_revision!==target.source_revision||!record.parents.includes(target.id))throw Error('Uncertain binary release document association.');
      }
    }
  });
});
