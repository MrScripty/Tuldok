'use strict';
let retrievalImportBusy=false,retrievalImportEpoch=0,retrievalImportDeparted=false;
function retrievalShown(record) {
  const a=record.task==='text_retrieval'?record.annotation:null;
  const declared=record.provenance?.acquisition?.format==='text_retrieval_query_v1'?record.provenance.acquisition.declared_positive_refs:null;
  $('retrieval-role').value=a?.role||(declared?'query':'document');
  $('retrieval-note').value=a?.note||'';
  $('retrieval-refs').value=JSON.stringify(a?.positive_refs||declared||[],null,2);
  $('retrieval-current-ref').textContent=JSON.stringify({id:record.id,revision:record.revision,source_revision:record.source_revision});
}
function retrievalControls(task) {
  $('retrieval-controls').hidden=task!=='text_retrieval';
  $('retrieval-refs-control').hidden=$('retrieval-role').value!=='query';
}
function retrievalReferences(refs) {
  if(!Array.isArray(refs)||refs.length<1||refs.length>30)throw Error('Provide 1–30 exact positive document references.');
  const ids=new Set();
  for(const r of refs) {
    if(!r||Array.isArray(r)||typeof r!=='object'||Object.keys(r).sort().join(',')!=='id,revision,source_revision'||
       typeof r.id!=='string'||!/^[a-f0-9]{32}$/.test(r.id)||ids.has(r.id)||
       !Number.isSafeInteger(r.revision)||r.revision<1||!Number.isSafeInteger(r.source_revision)||r.source_revision<1)
      throw Error('Positive refs require unique canonical IDs and positive safe-integer revisions.');
    ids.add(r.id);
  }
  return refs;
}
function retrievalAnnotation() {
  const role=$('retrieval-role').value,result={role,note:$('retrieval-note').value};
  if(role==='query') result.positive_refs=retrievalReferences(JSON.parse($('retrieval-refs').value));
  return result;
}
function retrievalStrip(value) {
  return value.replace(/^[\u0009-\u000D\u001C-\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]+|[\u0009-\u000D\u001C-\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]+$/gu,'');
}
async function retrievalHash(text) {
  const raw=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text));
  return [...new Uint8Array(raw)].map(b=>b.toString(16).padStart(2,'0')).join('');
}
function retrievalImportControls() {return [...$('retrieval-import-form').querySelectorAll('input,textarea,button')];}
$('retrieval-role').addEventListener('change',()=>{markDirty();retrievalControls($('task').value);});
window.addEventListener('pagehide',()=>{retrievalImportEpoch++;retrievalImportDeparted=true;});
window.addEventListener('pageshow',()=>{
  retrievalImportEpoch++;retrievalImportDeparted=false;retrievalImportBusy=false;
  retrievalImportControls().forEach(e=>e.disabled=false);
});
$('retrieval-import-form').addEventListener('submit',async event=>{
  event.preventDefault();if(retrievalImportBusy||retrievalImportDeparted)return;
  const epoch=++retrievalImportEpoch,live=()=>epoch===retrievalImportEpoch&&!retrievalImportDeparted;
  const controls=retrievalImportControls();retrievalImportBusy=true;controls.forEach(e=>e.disabled=true);
  try {
    const body={name:$('retrieval-import-name').value,text:$('retrieval-import-text').value,
      groups:[retrievalStrip($('retrieval-import-group').value)],rights:$('retrieval-import-rights').value,
      positive_refs:retrievalReferences(JSON.parse($('retrieval-import-refs').value))};
    const raw=JSON.stringify(body);if(new TextEncoder().encode(raw).length>1048576)throw Error('Query request exceeds 1 MiB.');
    const canonical=body.text.replace(/\r\n?/g,'\n').normalize('NFC');
    const [contentHash,sourceHash]=await Promise.all([retrievalHash(canonical),retrievalHash(body.text)]);
    if(!live())return;
    $('retrieval-import-status').textContent='Importing raw draft query…';
    const response=await fetch('/api/workbench/retrieval-query',{method:'POST',headers:{'Content-Type':'application/json'},body:raw});
    if(!live())return;
    const result=await response.json();if(!live())return;
    if(!response.ok)throw Error(result.error||'Query import failed.');
    const refs=retrievalReferences(result.provenance?.acquisition?.declared_positive_refs);
    const tuples=rs=>rs.map(r=>[r.id,r.revision,r.source_revision]);
    if(result.kind!=='text'||result.task!=='text_classification'||result.review!=='draft'||result.annotation!==null||
       result.revision!==1||result.source_revision!==1||result.source_available!==true||
       typeof result.id!=='string'||!/^[a-f0-9]{32}$/.test(result.id)||result.text!==canonical||
       result.content_hash!==contentHash||result.source_sha256!==sourceHash||
       result.name!==retrievalStrip(body.name)||JSON.stringify(result.groups)!==JSON.stringify(body.groups)||
       result.provenance?.rights!==retrievalStrip(body.rights)||
       JSON.stringify(result.parents)!==JSON.stringify(body.positive_refs.map(r=>r.id))||
       result.provenance?.acquisition?.format!=='text_retrieval_query_v1'||
       JSON.stringify(tuples(refs))!==JSON.stringify(tuples(body.positive_refs)))throw Error('Uncertain query import response.');
    $('retrieval-import-status').textContent='Imported raw draft '+result.id+'. Open it in the collection and separately review the relevance judgment. All omitted relationships remain UNJUDGED.';
    await refresh(live);if(!live())return;
  } catch(error) {
    if(live())$('retrieval-import-status').textContent=error.message+' Inspect the collection before repeating any request with an uncertain outcome. Requests are not replayed.';
  } finally {
    if(live()){retrievalImportBusy=false;controls.forEach(e=>e.disabled=false);}
  }
});
