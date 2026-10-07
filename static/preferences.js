'use strict';
// Judgment intent and fixed selection are independent of answer/annotation owners.
let preferenceDirty=false, preferenceBusy=false, preferenceListBusy=false;
let preferenceEditEpoch=0, preferenceLoadEpoch=0, preferenceParent=null, preferenceEditor=null;
let preferenceRows=[], preferenceAnswers=[], preferenceEditorAnswers=[];
const preferenceSelected=new Map();
let preferencePreview=null, preferenceReleaseBusy=false, preferenceReleaseEpoch=0;
const preferenceKeys=['id','revision','prompt_id','parent_revision','source_revision','left_id','left_revision','right_id','right_revision'];
const preferencePair=row=>Object.fromEntries(preferenceKeys.map(key=>[key,row[key]]));
function preferenceButtons(){
  for(const id of ['preference-save','preference-new','preference-delete','preference-refresh','preference-cancel'])$(id).disabled=preferenceBusy||preferenceListBusy;
  $('preference-delete').hidden=!preferenceEditor?.revision;
  $('preference-preview').disabled=preferenceReleaseBusy||!preferenceSelected.size;
  $('preference-freeze').disabled=preferenceReleaseBusy||!preferencePreview?.eligible;
}
function invalidatePreferencePreview(){
  ++preferenceReleaseEpoch;preferencePreview=null;$('preference-release-result').replaceChildren();
  $('preference-preview-output').textContent='Preview the fixed judgment revisions.';preferenceButtons();
}
function preferenceJudgmentAffectsSelection(judgment){
  if(preferenceSelected.has(judgment.id))return true;
  const sameAnswer=(pair,side,other)=>pair[side+'_id']===judgment[other+'_id']&&pair[side+'_revision']===judgment[other+'_revision'];
  return [...preferenceSelected.values()].some(pair=>pair.prompt_id===judgment.prompt_id&&pair.parent_revision===judgment.parent_revision&&pair.source_revision===judgment.source_revision&&
    ((sameAnswer(pair,'left','left')&&sameAnswer(pair,'right','right'))||(sameAnswer(pair,'left','right')&&sameAnswer(pair,'right','left'))));
}
function preferenceResponseSaved(answer){
  if([...preferenceSelected.values()].some(pair=>pair.left_id===answer.id||pair.right_id===answer.id))invalidatePreferencePreview();
}
function preferenceSelectionChanged(){
  invalidatePreferencePreview();$('preference-selected-list').replaceChildren();
  for(const pair of preferenceSelected.values()){
    const item=document.createElement('li');item.textContent=`Judgment ${pair.id.slice(0,8)} · revision ${pair.revision} · prompt ${pair.prompt_id.slice(0,8)} · answers ${pair.left_revision}/${pair.right_revision}`;
    const remove=document.createElement('button');remove.type='button';remove.textContent='Remove';remove.onclick=()=>{preferenceSelected.delete(pair.id);preferenceSelectionChanged();renderPreferences();};
    item.append(remove);$('preference-selected-list').append(item);
  }
}
function preferenceAnswerText(){
  for(const side of ['left','right']){
    const answer=preferenceEditorAnswers.find(row=>row.id===$('preference-'+side).value);
    $('preference-'+side+'-text').textContent=answer?`${answer.completion}\n\nAnswer revision ${answer.revision} · ${answer.review}`:'Choose an answer explicitly.';
  }
}
function editPreference(row=null){
  if(preferenceBusy||preferenceListBusy)return;
  if(preferenceDirty&&!confirm('Discard unsaved judgment edits?'))return;
  ++preferenceEditEpoch;preferenceDirty=false;
  preferenceEditorAnswers=structuredClone(preferenceAnswers);
  preferenceEditor=row?structuredClone(row):{id:crypto.randomUUID().replaceAll('-',''),revision:0,prompt_id:preferenceParent.id};
  for(const side of ['left','right']){
    const select=$('preference-'+side);select.replaceChildren();
    const empty=document.createElement('option');empty.value='';empty.textContent='Choose '+side+' answer';select.append(empty);
    for(const answer of preferenceEditorAnswers){const option=document.createElement('option');option.value=answer.id;option.textContent=`${answer.id.slice(0,8)} · r${answer.revision} · ${answer.completion.slice(0,60)}`;select.append(option);}
    select.value=row?.[side+'_id']||'';
  }
  $('preference-outcome').value=row?.outcome||'';$('preference-rationale').value=row?.rationale||'';
  // Editing a stale comparison requires a fresh explicit review of current evidence.
  $('preference-review').value=row?.stale_warning?'draft':row?.review||'draft';
  $('preference-form').hidden=false;$('preference-history-output').hidden=true;
  $('preference-editor-status').textContent=row?.stale_warning||'Compare the displayed exact answers and choose an outcome.';
  preferenceAnswerText();preferenceButtons();
}
function renderPreferences(){
  $('preference-list').replaceChildren();
  for(const judgment of preferenceRows){
    const row=document.createElement('div');row.className='record';
    const check=document.createElement('input');check.type='checkbox';check.checked=preferenceSelected.has(judgment.id);check.disabled=judgment.deleted;check.setAttribute('aria-label','Select judgment '+judgment.id);
    check.onchange=()=>{if(check.checked){if(preferenceSelected.size>=5000){check.checked=false;notice('Select at most 5,000 judgments.',true);return;}preferenceSelected.set(judgment.id,preferencePair(judgment));}else preferenceSelected.delete(judgment.id);preferenceSelectionChanged();};
    const edit=document.createElement('button');edit.type='button';edit.dataset.preferenceId=judgment.id;
    edit.textContent=`${judgment.outcome} · ${judgment.review} · revision ${judgment.revision}${judgment.deleted?' · deleted':''}${judgment.stale_warning?' · stale':''}`;
    edit.onclick=async()=>{
      if(!judgment.deleted){editPreference(judgment);return;}
      const parent=preferenceParent,epoch=++preferenceEditEpoch;
      try{const result=await api('preference-history/'+judgment.id);if(preferenceParent?.id===parent.id&&preferenceEditEpoch===epoch){$('preference-history-output').textContent=JSON.stringify(result.history,null,2);$('preference-history-output').hidden=false;}}
      catch(error){if(preferenceParent?.id===parent.id&&preferenceEditEpoch===epoch)notice(error.message,true);}
    };
    row.append(check,edit);$('preference-list').append(row);
  }
}
async function loadPreferences(parent){
  const epoch=++preferenceLoadEpoch;preferenceListBusy=true;preferenceButtons();
  try{
    const result=await api('records/'+parent.id+'/preferences');
    const matches=record=>record?.id===parent.id&&record.revision===parent.revision&&record.source_revision===parent.source_revision;
    if(epoch!==preferenceLoadEpoch||!matches(preferenceParent)||!matches(current))return;
    if(!matches(result.parent)){invalidatePreferencePreview();$('preference-status').textContent='Prompt changed. Reload the record; your draft and fixed judgments are retained.';return;}
    preferenceRows=result.judgments;preferenceAnswers=result.responses;
    for(const pair of preferenceSelected.values())if(pair.prompt_id===parent.id){
      const row=preferenceRows.find(row=>row.id===pair.id);
      if(!row||row.deleted||row.stale_warning||JSON.stringify(preferencePair(row))!==JSON.stringify(pair))invalidatePreferencePreview();
    }
    renderPreferences();$('preference-status').textContent=preferenceRows.length+' judgments. Refresh after answer edits to inspect stale bindings.';
  }catch(error){if(epoch===preferenceLoadEpoch)$('preference-status').textContent=error.message;}
  finally{if(epoch===preferenceLoadEpoch)preferenceListBusy=false;preferenceButtons();}
}
function showPreferences(parent){
  ++preferenceEditEpoch;++preferenceLoadEpoch;preferenceListBusy=false;preferenceDirty=false;preferenceEditor=null;preferenceParent=parent;preferenceRows=[];preferenceAnswers=[];preferenceEditorAnswers=[];
  $('preference-form').hidden=true;$('preference-history-output').hidden=true;$('preferences-panel').hidden=parent.kind!=='text';$('preference-list').replaceChildren();
  if(parent.kind==='text')loadPreferences(parent);
}
$('preference-new').addEventListener('click',()=>editPreference());
$('preference-cancel').addEventListener('click',()=>{if(preferenceBusy)return;++preferenceEditEpoch;preferenceDirty=false;preferenceEditor=null;$('preference-form').hidden=true;preferenceButtons();});
$('preference-refresh').addEventListener('click',()=>{
  if(preferenceBusy||preferenceListBusy)return;if(preferenceDirty&&!confirm('Discard unsaved judgment edits and refresh?'))return;
  ++preferenceEditEpoch;preferenceDirty=false;preferenceEditor=null;$('preference-form').hidden=true;loadPreferences(preferenceParent);
});
for(const id of ['preference-left','preference-right','preference-outcome','preference-rationale','preference-review']){
  $(id).addEventListener(id==='preference-rationale'?'input':'change',()=>{preferenceDirty=true;++preferenceEditEpoch;if(id!=='preference-review')$('preference-review').value='draft';preferenceAnswerText();});
}
function preferenceBody(){
  const left=preferenceEditorAnswers.find(row=>row.id===$('preference-left').value),right=preferenceEditorAnswers.find(row=>row.id===$('preference-right').value);
  if(!left||!right||left.id===right.id)throw Error('Choose two distinct answers to this prompt.');
  return {id:preferenceEditor.id,revision:preferenceEditor.revision,prompt_id:preferenceParent.id,parent_revision:preferenceParent.revision,source_revision:preferenceParent.source_revision,
    left_id:left.id,left_revision:left.revision,right_id:right.id,right_revision:right.revision,outcome:$('preference-outcome').value,rationale:$('preference-rationale').value,review:$('preference-review').value};
}
async function mutatePreference(deleting=false){
  if(preferenceBusy||!preferenceEditor)return;
  if(dirty||responseDirty||responseBusy||(typeof rightsDirty!=='undefined'&&(rightsDirty||rightsBusy))){notice('Save or cancel annotation, answer and rights-note edits before saving a judgment.',true);return;}
  if(deleting&&!confirm('Delete this judgment? Its independent history and frozen exports remain.'))return;
  let body;try{body=deleting?preferencePair(preferenceEditor):preferenceBody();}catch(error){notice(error.message,true);return;}
  const epoch=++preferenceEditEpoch,parent=preferenceParent,editor=preferenceEditor;preferenceBusy=true;preferenceButtons();
  try{
    const result=await api(deleting?'preferences/delete':'preferences',body);
    if(result.changed&&(preferenceJudgmentAffectsSelection(editor)||preferenceJudgmentAffectsSelection(result.judgment)))invalidatePreferencePreview();
    if(preferenceEditor?.id===editor.id&&preferenceParent?.id===parent.id){
      preferenceEditor=result.judgment;
      if(epoch===preferenceEditEpoch){preferenceDirty=false;$('preference-editor-status').textContent=deleting?'Judgment deleted.':'Saved judgment revision '+result.judgment.revision;if(deleting)$('preference-form').hidden=true;}
      else $('preference-editor-status').textContent='Earlier judgment saved; later edits remain unsaved.';
      await loadPreferences(parent);
    }
  }catch(error){invalidatePreferencePreview();$('preference-editor-status').textContent=error.message+' Draft retained. Refresh judgments to inspect an uncertain result; IDs are never replayed automatically.';}
  finally{preferenceBusy=false;preferenceButtons();}
}
$('preference-form').addEventListener('submit',event=>{event.preventDefault();return mutatePreference();});
$('preference-delete').addEventListener('click',()=>mutatePreference(true));
$('preference-history').addEventListener('click',async()=>{
  const editor=preferenceEditor,epoch=preferenceEditEpoch;if(!editor?.revision)return;
  try{const result=await api('preference-history/'+editor.id);if(preferenceEditor?.id===editor.id&&preferenceEditEpoch===epoch){$('preference-history-output').textContent=JSON.stringify(result.history,null,2);$('preference-history-output').hidden=false;}}catch(error){notice(error.message,true);}
});
function preferenceReleaseBody(){return {format:'text_preference_v1',items:[...preferenceSelected.values()].sort((a,b)=>a.id.localeCompare(b.id)),ratios:{train:Number($('preference-train').value),validation:Number($('preference-validation').value),test:Number($('preference-test').value)},seed:Number($('preference-seed').value)};}
$('preference-clear').addEventListener('click',()=>{preferenceSelected.clear();preferenceSelectionChanged();renderPreferences();});
for(const id of ['preference-train','preference-validation','preference-test','preference-seed'])$(id).addEventListener('input',invalidatePreferencePreview);
$('preference-preview').addEventListener('click',async()=>{
  if(preferenceReleaseBusy)return;const epoch=++preferenceReleaseEpoch;preferenceReleaseBusy=true;preferenceButtons();
  try{const result=await api('releases/preview',preferenceReleaseBody());if(epoch!==preferenceReleaseEpoch)return;preferencePreview=result;
    $('preference-preview-output').textContent=JSON.stringify({eligible:result.eligible,pairs:result.example_count,prompts:result.unique_prompt_count,excluded:result.excluded,splits:result.split_report,warnings:result.warnings,blockers:result.blockers},null,2);
  }catch(error){if(epoch===preferenceReleaseEpoch){invalidatePreferencePreview();$('preference-preview-output').textContent=error.message;}}
  finally{preferenceReleaseBusy=false;preferenceButtons();}
});
$('preference-release-form').addEventListener('submit',async event=>{
  event.preventDefault();if(preferenceReleaseBusy||!preferencePreview?.eligible)return;
  const epoch=preferenceReleaseEpoch,body={...preferenceReleaseBody(),preview_token:preferencePreview.preview_token};preferenceReleaseBusy=true;preferenceButtons();
  try{const result=await api('releases',body);if(epoch!==preferenceReleaseEpoch)return;const link=document.createElement('a');link.href=result.url;link.download=result.id+'.zip';link.textContent='Download '+result.example_count+' frozen preference pairs';$('preference-release-result').replaceChildren(link);}
  catch(error){if(epoch===preferenceReleaseEpoch){invalidatePreferencePreview();$('preference-preview-output').textContent=error.message;}}
  finally{preferenceReleaseBusy=false;preferenceButtons();}
});
preferenceButtons();
