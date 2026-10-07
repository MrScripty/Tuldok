'use strict';
// Responses and their exact selections are independent of generic record targets.
let responseDirty=false, responseBusy=false, responseParent=null, responseEditor=null;
let responseListBusy=false;
let responseEditEpoch=0, responseLoadEpoch=0, responseEntryFormat='text', responseRows=[];
const responseSelected=new Map();
let responseSelectionEpoch=0;
let responsePreview=null, responseReleaseBusy=false, responseReleaseEpoch=0;
const responsePair=(answer,parent)=>({id:answer.id,revision:answer.revision,prompt_id:answer.prompt_id,parent_revision:parent.revision,source_revision:parent.source_revision});
function responseButtons(){
  $('response-save').disabled=responseBusy;$('response-new').disabled=responseBusy;
  $('response-preview').disabled=responseReleaseBusy||!responseSelected.size;
  $('response-freeze').disabled=responseReleaseBusy||!responsePreview?.eligible;
}
function invalidateResponsePreview(){
  ++responseReleaseEpoch;responsePreview=null;
  $('response-preview-output').textContent='';$('response-release-result').replaceChildren();
  $('response-preview-status').textContent='Preview the fixed answer revisions before exporting.';responseButtons();
}
function responseSelectionChanged(){
  ++responseSelectionEpoch;
  $('response-selection-download').hidden=true;
  invalidateResponsePreview();
  $('response-selection-count').textContent=responseSelected.size+' fixed answers selected';
  $('response-selected-list').replaceChildren();
  for(const pair of responseSelected.values()){
    const row=document.createElement('li');row.textContent=`Answer ${pair.id.slice(0,8)} · revision ${pair.revision} · prompt ${pair.prompt_id.slice(0,8)} at ${pair.parent_revision}/${pair.source_revision}`;
    const remove=document.createElement('button');remove.type='button';remove.textContent='Remove';
    remove.onclick=()=>{responseSelected.delete(pair.id);responseSelectionChanged();renderResponses();};row.append(remove);$('response-selected-list').append(row);
  }
}
function responseCompletion(format=responseEntryFormat){
  const value=$('response-completion').value;
  if(format==='text')return value;
  let decoded;try{decoded=JSON.parse(value);}catch{throw Error('Enter a JSON string in double quotes.');}
  if(typeof decoded!=='string')throw Error('Completion must be a JSON string.');return decoded;
}
function editResponse(answer=null){
  if(responseBusy)return;
  if(responseDirty&&!confirm('Discard unsaved answer edits?'))return;
  ++responseEditEpoch;responseDirty=false;
  responseEditor=answer?structuredClone(answer):{id:crypto.randomUUID().replaceAll('-',''),prompt_id:responseParent.id,revision:0,completion:'',review:'draft'};
  responseEntryFormat=/\r/.test(responseEditor.completion)?'json':'text';
  $('response-entry-format').value=responseEntryFormat;
  $('response-completion').value=responseEntryFormat==='json'?JSON.stringify(responseEditor.completion):responseEditor.completion;
  $('response-review').value=responseEditor.review;$('response-form').hidden=false;$('response-history-output').hidden=true;
  $('response-editor-status').textContent=responseEditor.revision?'Answer revision '+responseEditor.revision:'New independent answer';responseButtons();
}
function renderResponses(){
  $('response-list').replaceChildren();
  for(const answer of responseRows){
    const row=document.createElement('div');row.className='record';
    const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.checked=responseSelected.has(answer.id);checkbox.setAttribute('aria-label','Select answer '+answer.id);
    checkbox.onchange=()=>{
      if(checkbox.checked){if(responseSelected.size>=5000){checkbox.checked=false;notice('Select at most 5,000 answers.',true);return;}responseSelected.set(answer.id,responsePair(answer,responseParent));}
      else responseSelected.delete(answer.id);responseSelectionChanged();
    };
    const edit=document.createElement('button');edit.type='button';edit.dataset.responseId=answer.id;
    const fixed=responseSelected.get(answer.id);
    edit.textContent=`${answer.completion.slice(0,100)} · ${answer.review.replaceAll('_',' ')} · revision ${answer.revision}${fixed?' · selected '+fixed.revision:''}`;
    edit.onclick=()=>editResponse(answer);row.append(checkbox,edit);$('response-list').append(row);
  }
}
async function loadResponses(parent){
  const epoch=++responseLoadEpoch;responseListBusy=true;$('response-status').textContent='Loading answers…';
  const owner={id:parent.id,revision:parent.revision,source_revision:parent.source_revision};
  const matchesOwner=record=>record?.id===owner.id&&record.revision===owner.revision&&record.source_revision===owner.source_revision;
  try{
    const result=await api('records/'+parent.id+'/responses');
    if(epoch!==responseLoadEpoch||!matchesOwner(responseParent)||!matchesOwner(current))return;
    if(!matchesOwner(result.parent)){
      invalidateResponsePreview();$('response-status').textContent='Parent revisions changed. Reload the record before using current answers; your draft and fixed selections are retained.';return;
    }
    // Only explicit record adoption owns the answer parent; a list read cannot rebase a draft.
    responseRows=result.responses;
    for(const pair of responseSelected.values())if(pair.prompt_id===parent.id){
      const answer=responseRows.find(row=>row.id===pair.id);
      if(!answer||JSON.stringify(responsePair(answer,responseParent))!==JSON.stringify(pair))invalidateResponsePreview();
    }
    renderResponses();$('response-status').textContent=responseRows.length+' independent answers';
  }catch(error){if(epoch===responseLoadEpoch)$('response-status').textContent=error.message;}
  finally{if(epoch===responseLoadEpoch)responseListBusy=false;}
}
function showResponses(parent){
  ++responseEditEpoch;++responseLoadEpoch;responseListBusy=false;responseDirty=false;responseEditor=null;responseParent=parent;responseRows=[];
  $('response-form').hidden=true;$('responses-panel').hidden=parent.kind!=='text';$('response-list').replaceChildren();
  if(parent.kind==='text')loadResponses(parent);
}
$('response-new').addEventListener('click',()=>{if(!dirty)editResponse();else notice('Save or discard the annotation edit before authoring an answer.',true);});
$('response-refresh').addEventListener('click',()=>{
  if(responseBusy)return;
  if(responseDirty&&!confirm('Discard unsaved answer edits and refresh?'))return;
  ++responseEditEpoch;responseDirty=false;responseEditor=null;$('response-form').hidden=true;loadResponses(responseParent);
});
$('response-cancel').addEventListener('click',()=>{if(responseBusy)return;++responseEditEpoch;responseDirty=false;responseEditor=null;$('response-form').hidden=true;});
$('response-completion').addEventListener('input',()=>{responseDirty=true;++responseEditEpoch;$('response-review').value='draft';});
$('response-review').addEventListener('change',()=>{responseDirty=true;++responseEditEpoch;});
$('response-entry-format').addEventListener('change',()=>{
  try{
    const value=responseCompletion();const next=$('response-entry-format').value;
    if(next==='text'&&/\r/.test(value))throw Error('Keep JSON entry to preserve carriage returns.');
    $('response-completion').value=next==='json'?JSON.stringify(value):value;responseEntryFormat=next;
  }catch(error){$('response-entry-format').value=responseEntryFormat;notice(error.message,true);}
});
$('response-form').addEventListener('submit',async event=>{
  event.preventDefault();if(responseBusy||!responseEditor)return;
  if(typeof preferenceDirty !== 'undefined' && (preferenceDirty || preferenceBusy)){notice('Save or cancel the judgment edit before saving an answer.',true);return;}
  if(dirty){notice('Save or discard the annotation edit before saving an answer.',true);return;}
  if(typeof rightsDirty !== 'undefined' && (rightsDirty || rightsBusy)){notice('Save or cancel the rights-note edit before saving an answer.',true);return;}
  const epoch=responseEditEpoch,editor=structuredClone(responseEditor),parent=responseParent;
  let completion;try{completion=responseCompletion();}catch(error){notice(error.message,true);return;}
  responseBusy=true;responseButtons();
  try{
    const saved=await api('responses',{id:editor.id,prompt_id:editor.prompt_id,revision:editor.revision,parent_revision:parent.revision,source_revision:parent.source_revision,completion,review:$('response-review').value});
    if(saved.changed&&responseSelected.has(editor.id))invalidateResponsePreview();
    if(responseEditor?.id===editor.id&&responseParent?.id===parent.id){
      responseEditor=saved.response;
      if(epoch===responseEditEpoch){responseDirty=false;$('response-editor-status').textContent='Saved answer revision '+saved.response.revision;}
      else $('response-editor-status').textContent='Earlier answer saved; later edits remain unsaved.';
      await loadResponses(parent);
    }
  }catch(error){
    if(responseSelected.has(editor.id))invalidateResponsePreview();
    $('response-editor-status').textContent=error.message+' Your draft is retained. Refresh answers to inspect an uncertain result; the same creation ID cannot create duplicates.';
  }finally{responseBusy=false;responseButtons();}
});
$('response-history').addEventListener('click',async()=>{
  const editor=responseEditor,epoch=responseEditEpoch;if(!editor?.revision)return;
  try{const result=await api('response-history/'+editor.id);if(responseEditor?.id===editor.id&&responseEditEpoch===epoch){$('response-history-output').textContent=JSON.stringify(result.history,null,2);$('response-history-output').hidden=false;}}
  catch(error){notice(error.message,true);}
});
function responseReleaseBody(){return {format:'text_instruction_v1',items:[...responseSelected.values()].sort((a,b)=>a.id.localeCompare(b.id)),ratios:{train:Number($('response-train').value),validation:Number($('response-validation').value),test:Number($('response-test').value)},seed:Number($('response-seed').value)};}
$('response-clear').addEventListener('click',()=>{responseSelected.clear();responseSelectionChanged();renderResponses();});
for(const id of ['response-train','response-validation','response-test','response-seed'])$(id).addEventListener('input',invalidateResponsePreview);
$('response-preview').addEventListener('click',async()=>{
  if(responseReleaseBusy)return;const epoch=++responseReleaseEpoch,body=responseReleaseBody();responseReleaseBusy=true;responseButtons();
  try{const result=await api('releases/preview',body);if(epoch!==responseReleaseEpoch)return;responsePreview=result;
    $('response-preview-output').textContent=[`${result.example_count} answers · ${result.unique_prompt_count} unique prompts`,`${result.lineage.length} whole protected families`,...Object.entries(result.split_report?.actual_counts||{}).map(([split,count])=>`${split}: ${count} examples (${result.split_report.actual_unique_prompt_counts[split]||0} prompts)`),...(result.warnings||[])].join('\n');$('response-preview-status').textContent=result.eligible?`${result.example_count} examples from ${result.unique_prompt_count} unique prompts. Exact selection eligible.`:result.blockers.map(item=>item.message).join(' ');
  }catch(error){if(epoch===responseReleaseEpoch){invalidateResponsePreview();$('response-preview-status').textContent=error.message;}}
  finally{responseReleaseBusy=false;responseButtons();}
});
$('response-release-form').addEventListener('submit',async event=>{
  event.preventDefault();if(responseReleaseBusy||!responsePreview?.eligible)return;
  const epoch=responseReleaseEpoch,body={...responseReleaseBody(),preview_token:responsePreview.preview_token};responseReleaseBusy=true;responseButtons();
  try{const result=await api('releases',body);if(epoch!==responseReleaseEpoch)return;
    const link=document.createElement('a');link.href=result.url;link.download=result.id+'.zip';link.textContent=`Download ${result.example_count} frozen answers`; $('response-release-result').replaceChildren(link);
  }catch(error){if(epoch===responseReleaseEpoch){invalidateResponsePreview();$('response-preview-status').textContent=error.message;}}
  finally{responseReleaseBusy=false;responseButtons();}
});
let responseSelectionURL=null,responseSelectionLoadEpoch=0;
$('response-selection-save').addEventListener('click',()=>{
  if(responseSelectionURL)URL.revokeObjectURL(responseSelectionURL);
  const envelope={schema_version:1,format:'text_instruction_selection_v1',items:responseReleaseBody().items};
  responseSelectionURL=URL.createObjectURL(new Blob([JSON.stringify(envelope,null,2)+'\n'],{type:'application/json'}));
  const link=$('response-selection-download');link.href=responseSelectionURL;link.hidden=false;link.click();
});
$('response-selection-file').addEventListener('change',async()=>{
  const epoch=++responseSelectionLoadEpoch,file=$('response-selection-file').files[0];if(!file)return;
  // A later selection action owns the intent even if file reading is delayed.
  const intent=responseSelectionEpoch;
  try{
    if(file.size>40*1024*1024)throw Error('Selection file exceeds 40 MiB.');
    const value=JSON.parse(await file.text());if(epoch!==responseSelectionLoadEpoch||responseSelectionEpoch!==intent)return;
    if(!value||Array.isArray(value)||Object.keys(value).sort().join(',')!=='format,items,schema_version'||value.schema_version!==1||value.format!=='text_instruction_selection_v1'||!Array.isArray(value.items)||value.items.length>5000)throw Error('Choose a fixed answer selection file.');
    const next=new Map();for(const pair of value.items){
      if(!pair||Array.isArray(pair)||Object.keys(pair).sort().join(',')!=='id,parent_revision,prompt_id,revision,source_revision'||!['id','prompt_id'].every(key=>typeof pair[key]==='string'&&/^[a-f0-9]{32}$/.test(pair[key]))||!['revision','parent_revision','source_revision'].every(key=>Number.isSafeInteger(pair[key])&&pair[key]>0)||next.has(pair.id))throw Error('Invalid or repeated fixed answer pair.');next.set(pair.id,pair);
    }
    responseSelected.clear();for(const [id,pair]of next)responseSelected.set(id,pair);responseSelectionChanged();renderResponses();$('response-selection-status').textContent='Opened exact stored pairs. Preview checks current evidence; revisions are not refreshed.';
  }catch(error){if(epoch===responseSelectionLoadEpoch)$('response-selection-status').textContent=error.message;}
});
responseButtons();
