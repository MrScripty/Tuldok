'use strict';
// Passage composition is local authoring. Answers retain their existing owner.
let groundedContexts=[], groundedDirty=false, groundedBusy=false, groundedEditEpoch=0;
let groundedRequest=null, groundedInspection=null, groundedInspectEpoch=0, groundedInspectBusy=false;
const groundedRef=(source,start,end)=>({id:source.id,revision:source.revision,source_revision:source.source_revision,content_hash:source.content_hash,start,end,quote:[...source.text].slice(start,end).join('')});
function groundedChanged(){++groundedEditEpoch;groundedDirty=true;groundedRequest=null;groundedRender();}
function groundedOwnersIdle(){return !responseBusy&&!rightsBusy&&!preferenceBusy&&!$('editor').dataset.busy&&!hasUnsavedEdits();}
function groundedPrompt(){return groundedContexts.map((ref,i)=>`Source ${i+1} [${ref.id}]\n${ref.quote}`).join('\n\n')+'\n\nQuestion\n'+$('grounded-question').value.replace(/\r\n?/g,'\n').normalize('NFC');}
function groundedRender(){
  $('grounded-passages').replaceChildren();
  for(const ref of groundedContexts){
    const li=document.createElement('li');const quote=document.createElement('pre');quote.textContent=ref.quote;
    const text=document.createElement('p');text.textContent=`Source ${ref.id} · revision ${ref.revision}/${ref.source_revision} · codepoints [${ref.start}, ${ref.end}) · SHA256 ${ref.content_hash}`;
    const remove=document.createElement('button');remove.type='button';remove.textContent='Remove passage';remove.disabled=groundedBusy;
    remove.onclick=()=>{groundedContexts=groundedContexts.filter(item=>item.id!==ref.id);groundedChanged();};li.append(text,quote,remove);$('grounded-passages').append(li);
  }
  $('grounded-prompt-preview').textContent=groundedPrompt();
  $('grounded-compose-save').disabled=groundedBusy||groundedContexts.length<2||groundedContexts.length>4;
  $('grounded-compose-reset').disabled=groundedBusy;
}
function groundedShown(record){
  $('grounded-capture-controls').hidden=record.kind!=='text'||!record.source_available;
  $('text-source-delete').hidden=record.kind!=='text'||!record.source_available;
  $('grounded-start').value=0;$('grounded-end').value=Math.min(10000,[...record.text||''].length);
  groundedInspection=null;++groundedInspectEpoch;
  $('grounded-context-inspection').hidden=!record.provenance.grounded_instruction;
  $('grounded-context-evidence').textContent=record.provenance.grounded_instruction?JSON.stringify({creation:record.provenance.grounded_instruction,current_binding:record.grounded_context_binding},null,2):'';
  $('grounded-reinspect').disabled=true;$('grounded-context-status').textContent='Inspect current sources before reviewing this answer.';
}
$('grounded-capture').addEventListener('click',()=>{
  if(groundedBusy||!current||current.kind!=='text'||!current.source_available)return;
  const start=Number($('grounded-start').value),end=Number($('grounded-end').value),length=[...current.text].length;
  if(!Number.isSafeInteger(start)||!Number.isSafeInteger(end)||start<0||start>=end||end>length||end-start>10000){$('grounded-compose-status').textContent='Use Unicode codepoint offsets, with 1–10,000 codepoints per passage.';return;}
  if(groundedContexts.some(ref=>ref.id===current.id)||groundedContexts.length>=4){$('grounded-compose-status').textContent='Capture 2–4 distinct sources, one passage each. Remove an old passage to capture its current revision.';return;}
  groundedContexts.push(groundedRef(current,start,end));groundedChanged();$('grounded-compose-status').textContent='Passage captured as source data. Capture another source, then inspect the composed prompt.';
});
$('grounded-capture-selection').addEventListener('click',()=>{
  const selected=window.getSelection(),text=$('asset-text');if(!selected?.rangeCount)return;
  const range=selected.getRangeAt(0);if(range.collapsed||!text.contains(range.startContainer)||!text.contains(range.endContainer)){notice('Select a passage inside the source text.',true);return;}
  const prefix=range.cloneRange();prefix.selectNodeContents(text);prefix.setEnd(range.startContainer,range.startOffset);
  $('grounded-start').value=[...prefix.toString()].length;prefix.setEnd(range.endContainer,range.endOffset);$('grounded-end').value=[...prefix.toString()].length;$('grounded-capture').click();
});
for(const id of ['grounded-name','grounded-question'])$(id).addEventListener('input',groundedChanged);
$('grounded-compose-reset').addEventListener('click',()=>{
  if(groundedBusy||groundedDirty&&!confirm('Discard this unsaved composition?'))return;
  groundedContexts=[];$('grounded-name').value='';$('grounded-question').value='';++groundedEditEpoch;groundedDirty=false;groundedRequest=null;groundedRender();$('grounded-compose-status').textContent='Composition cleared.';
});
$('grounded-compose-form').addEventListener('submit',async event=>{
  event.preventDefault();if(groundedBusy||groundedContexts.length<2)return;
  if(!groundedRequest)groundedRequest={request_id:crypto.randomUUID().replaceAll('-',''),name:$('grounded-name').value,question:$('grounded-question').value,contexts:structuredClone(groundedContexts)};
  const body=structuredClone(groundedRequest),epoch=groundedEditEpoch,parentEpoch=editorEpoch,responseEpoch=responseIntentEpoch();
  groundedBusy=true;groundedRender();
  try{
    const result=await api('instruction-compose',body);
    if(epoch===groundedEditEpoch){
      groundedDirty=false;$('grounded-compose-status').textContent=`Draft prompt saved: ${result.record.id}. Author an answer separately, then review against all sources and rights.`;
      if(parentEpoch===editorEpoch&&responseEpoch===responseIntentEpoch()&&groundedOwnersIdle())showRecord(result.record);
    }else $('grounded-compose-status').textContent=`Earlier draft saved: ${result.record.id}. Later composition edits are retained.`;
    await refresh();
  }catch(error){$('grounded-compose-status').textContent=error.message+' Draft retained. Retry unchanged to recover the same request; no duplicate prompt is created.';}
  finally{groundedBusy=false;groundedRender();}
});
$('grounded-inspect').addEventListener('click',async()=>{
  if(groundedInspectBusy||!current?.provenance.grounded_instruction)return;
  const owner=current,epoch=++groundedInspectEpoch;groundedInspectBusy=true;
  try{
    const result=await api('instruction-contexts/'+owner.id);
    if(epoch!==groundedInspectEpoch||current?.id!==owner.id||current.revision!==owner.revision)return;
    groundedInspection=result;
    $('grounded-context-evidence').textContent=JSON.stringify({creation:owner.provenance.grounded_instruction,inspection:result},null,2);
    $('grounded-context-status').textContent=result.current?'Exact context bindings are current. Exact quotes are not semantic verification; review the answer and permission yourself.':result.problems.join(' ')+' Reinspection resets every answer to draft.';
    $('grounded-reinspect').disabled=result.current||result.contexts.some(item=>!item.source.source_available||item.source.content_hash!==item.captured.ref.content_hash)||result.parent.revision!==current.revision;
  }catch(error){if(current?.id===owner.id&&epoch===groundedInspectEpoch)$('grounded-context-status').textContent=error.message;}
  finally{groundedInspectBusy=false;}
});
$('grounded-reinspect').addEventListener('click',async()=>{
  if(groundedInspectBusy||!groundedInspection||!groundedOwnersIdle()){notice('Save or cancel current edits before reinspecting sources.',true);return;}
  const owner=current,epoch=editorEpoch,responseEpoch=responseIntentEpoch();
  const contexts=groundedInspection.contexts.map(item=>groundedRef(item.source,item.captured.ref.start,item.captured.ref.end));
  groundedInspectBusy=true;$('grounded-reinspect').disabled=true;
  try{
    const result=await api('instruction-reinspect/'+owner.id,{revision:owner.revision,source_revision:owner.source_revision,contexts});
    invalidateResponsePreview();if(typeof invalidatePreferencePreview==='function')invalidatePreferencePreview();
    if(current?.id===owner.id&&epoch===editorEpoch&&responseEpoch===responseIntentEpoch()&&groundedOwnersIdle())showRecord(result.record);
    if(current?.id===owner.id)$('grounded-context-status').textContent='Current context evidence saved. All answers reset to draft; reopen, inspect and review each answer deliberately. Fixed selections remain stale.';
  }catch(error){if(current?.id===owner.id)$('grounded-context-status').textContent=error.message+' Inspect again; no automatic repair.';}
  finally{groundedInspectBusy=false;}
});
$('text-source-delete').addEventListener('click',async()=>{
  if(!current||groundedInspectBusy||!groundedOwnersIdle()){notice('Save or cancel current edits before deleting a source.',true);return;}
  if(!confirm('Delete this text source from use? Its bytes, history and family links are retained. Dependent instructions will be blocked.'))return;
  const owner=current,epoch=editorEpoch,responseEpoch=responseIntentEpoch();groundedInspectBusy=true;$('text-source-delete').disabled=true;
  try{
    const result=await api('text-delete/'+owner.id,{revision:owner.revision,source_revision:owner.source_revision});
    invalidateRelease();invalidateResponsePreview();invalidatePreferencePreview();
    if(current?.id===owner.id&&epoch===editorEpoch&&responseEpoch===responseIntentEpoch()&&groundedOwnersIdle())showRecord(result.record);
    notice('Text source deleted from use. History and family links retained.');await refresh();
  }catch(error){notice(error.message,true);}
  finally{groundedInspectBusy=false;$('text-source-delete').disabled=false;}
});
window.addEventListener('beforeunload',event=>{if(groundedDirty||groundedBusy){event.preventDefault();event.returnValue='';}});
groundedRender();
