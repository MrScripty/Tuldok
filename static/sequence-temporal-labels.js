'use strict';
// Draft human targets only. Source arrays/provenance, save/review and split owners remain separate.
const sequenceTemporalSemantics='inclusive native accepted-state frame indices; constructor 0 has no preceding accepted interval';
let sequenceTemporalOwner=null,sequenceTemporalRanges=[],sequenceTemporalUsed=false,sequenceTemporalPending=false;
let sequenceTemporalEditing=null,sequenceTemporalEpoch=0,sequenceTemporalDeparted=false;
function sequenceTemporalText(value,name,maximum,empty=false){
  if(typeof value!=='string'||/[\uD800-\uDFFF]/u.test(value)||[...value].length>maximum)throw Error(`${name}: valid Unicode, at most ${maximum} code points required.`);
  // Exact Python str.strip whitespace; no NFC/case folding or JS-only BOM trimming.
  const stripped=value.replace(/^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+|[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$/gu,'');
  if(!empty&&!stripped)throw Error(`${name}: nonempty text required.`);return stripped;
}
function sequenceTemporalCurrent(){return !sequenceTemporalDeparted&&sequenceTemporalOwner&&current?.kind==='sequence'&&current.task==='sequence_transport'&&$('task').value==='sequence_transport'&&['id','revision','source_revision','content_hash'].every(key=>current[key]===sequenceTemporalOwner[key]);}
function sequenceTemporalGuard(epoch=sequenceTemporalEpoch,saving=false){
  if(epoch!==sequenceTemporalEpoch||!sequenceTemporalCurrent())throw Error('Temporal draft belongs to a different record or revision. Reload deliberately.');
  if((!saving&&$('editor').dataset.busy)||(typeof rightsBusy!=='undefined'&&rightsBusy)||(typeof responseBusy!=='undefined'&&responseBusy)||(typeof preferenceBusy!=='undefined'&&preferenceBusy)||(typeof captionProposalBusy!=='undefined'&&captionProposalBusy)||(typeof textClassificationProposalBusy!=='undefined'&&textClassificationProposalBusy))throw Error('Wait for the current editor action before changing temporal targets.');
}
function sequenceTemporalAnchor(record,k){
  const frame=record.sequence?.frame_index?.[k];if(!frame||frame.frame!==k||!Number.isFinite(frame.time_s)||typeof frame.sha256!=='string'||!/^[a-f0-9]{64}$/.test(frame.sha256))throw Error('Complete native endpoint metadata required.');
  for(const [key,id] of [['carrier_stamp','43'],['liquid_stamp','41']]){const stamp=frame[key];if(!stamp||Object.keys(stamp).length!==2||stamp.id!==id||stamp.version!==String(k))throw Error('Native endpoint stamp association changed.');}
  return structuredClone({frame:k,time_s:frame.time_s,sha256:frame.sha256,carrier_stamp:frame.carrier_stamp,liquid_stamp:frame.liquid_stamp});
}
function sequenceTemporalEqual(a,b){
  if(typeof a!==typeof b||a===null||b===null)return a===b;
  if(typeof a==='number')return Number.isFinite(a)&&a===b;
  if(typeof a!=='object')return a===b;
  if(Array.isArray(a)!==Array.isArray(b))return false;
  const keys=Object.keys(a);return keys.length===Object.keys(b).length&&keys.every(key=>Object.hasOwn(b,key)&&sequenceTemporalEqual(a[key],b[key]));
}
function sequenceTemporalEnvelope(record,ranges){
  const source={content_hash:record.content_hash,run_sha256:record.sequence.run_sha256,frames_sha256:record.sequence.manifest.frames_sha256};
  if(Object.values(source).some(value=>typeof value!=='string'||!/^[a-f0-9]{64}$/.test(value)))throw Error('Whole trajectory source hashes required.');
  if(!Array.isArray(ranges)||ranges.length>16)throw Error('At most 16 temporal ranges are allowed.');
  const seen=new Set();const entries=ranges.map(entry=>{
    if(!entry||Array.isArray(entry)||Object.keys(entry).length!==6||!['label','note','start_frame','end_frame','start','end'].every(key=>Object.hasOwn(entry,key)))throw Error('Closed temporal range fields required.');
    const label=sequenceTemporalText(entry.label,'Human label',80),note=sequenceTemporalText(entry.note,'Human rationale',500),a=entry.start_frame,b=entry.end_frame;
    if(!Number.isInteger(a)||!Number.isInteger(b)||a<0||a>b||b>8)throw Error('Use inclusive native frames 0 ≤ first ≤ last ≤ 8.');
    const key=JSON.stringify([label,a,b]);if(seen.has(key))throw Error('Duplicate normalized label and frame range.');seen.add(key);
    const start=sequenceTemporalAnchor(record,a),end=sequenceTemporalAnchor(record,b);
    if(!sequenceTemporalEqual(entry.start,start)||!sequenceTemporalEqual(entry.end,end))throw Error('Temporal endpoint time/hash/stamp association changed.');
    return {label,note,start_frame:a,end_frame:b,start,end};
  });
  return {version:1,origin:'human_defined_annotation',frame_semantics:sequenceTemporalSemantics,source,ranges:entries};
}
function sequenceTemporalPayload(record,note,ranges){
  const annotation={note:sequenceTemporalText(note,'Sequence review note',4000,true),temporal_labels:sequenceTemporalEnvelope(record,ranges)};
  // Python emits .0 for canonical integer-valued float times. Account for that
  // conservative wire difference before publishing local drafts; server owns exact cap.
  const overhead=annotation.temporal_labels.ranges.reduce((n,r)=>n+[r.start.time_s,r.end.time_s].reduce((bytes,value)=>bytes+(Number.isInteger(value)?(Object.is(value,-0)?3:2):0),0),0);
  if(new TextEncoder().encode(JSON.stringify(annotation)).length+overhead>65536)throw Error('Complete temporal annotation exceeds 64 KiB UTF-8. Nothing changed.');
  return annotation;
}
function sequenceTemporalAnnotation(record,note){
  sequenceTemporalGuard(sequenceTemporalEpoch,true);
  if(sequenceTemporalPending)throw Error('Add or Update the pending temporal range, or Cancel it, before saving the record.');
  return sequenceTemporalUsed?sequenceTemporalPayload(record,note,sequenceTemporalRanges):{note};
}
function sequenceTemporalResetControls(){
  $('sequence-temporal-first').value='0';$('sequence-temporal-last').value='0';$('sequence-temporal-label').value='';$('sequence-temporal-rationale').value='';
  sequenceTemporalPending=false;sequenceTemporalEditing=null;
}
function sequenceTemporalControls(){
  const departed=sequenceTemporalDeparted||!sequenceTemporalCurrent();
  for(const name of ['first','last','label','rationale','add','cancel'])$('sequence-temporal-'+name).disabled=departed;
  $('sequence-temporal-cancel').disabled=departed||!sequenceTemporalPending;
  $('sequence-temporal-add').textContent=sequenceTemporalEditing===null?'Add draft range':'Update draft range';
  $('sequence-temporal-clear').disabled=departed||sequenceTemporalPending||!sequenceTemporalRanges.length;
  for(const button of $('sequence-temporal-list').querySelectorAll('button'))button.disabled=departed||sequenceTemporalPending;
}
function sequenceTemporalRender(){
  const list=$('sequence-temporal-list');list.replaceChildren();const epoch=sequenceTemporalEpoch;
  sequenceTemporalRanges.forEach((range,index)=>{
    const row=document.createElement('li'),title=document.createElement('p'),rationale=document.createElement('p'),details=document.createElement('details'),summary=document.createElement('summary'),evidence=document.createElement('pre');
    title.textContent=`${range.label} · inclusive frames ${range.start_frame}–${range.end_frame} · ${range.start.time_s} … ${range.end.time_s} s`;
    rationale.textContent=range.note;summary.textContent='Source endpoint evidence (human label stays separate)';evidence.textContent=JSON.stringify({start:range.start,end:range.end},null,2);details.append(summary,evidence);
    const edit=document.createElement('button');edit.type='button';edit.textContent='Edit range';edit.onclick=()=>sequenceTemporalAction(()=>{
      sequenceTemporalGuard(epoch);if(sequenceTemporalPending)throw Error('Add/Update or Cancel the pending range first.');
      sequenceTemporalEditing=index;sequenceTemporalPending=true;$('sequence-temporal-first').value=String(range.start_frame);$('sequence-temporal-last').value=String(range.end_frame);$('sequence-temporal-label').value=range.label;$('sequence-temporal-rationale').value=range.note;
      $('sequence-temporal-status').textContent='Editing a staged range. Explicitly Update or Cancel before saving.';sequenceTemporalControls();$('sequence-temporal-label').focus();
    });
    const remove=document.createElement('button');remove.type='button';remove.textContent='Remove range';remove.onclick=()=>sequenceTemporalAction(()=>{
      sequenceTemporalGuard(epoch);if(sequenceTemporalPending)throw Error('Add/Update or Cancel the pending range first.');
      const next=sequenceTemporalRanges.filter((_,j)=>j!==index);sequenceTemporalPayload(sequenceTemporalOwner,$('sequence-note').value,next);
      sequenceTemporalRanges=next;sequenceTemporalUsed=true;++sequenceTemporalEpoch;markDirty();sequenceTemporalRender();$('sequence-temporal-status').textContent='Range removed from draft. Save and human review remain separate.';
    });
    row.append(title,rationale,edit,remove,details);list.append(row);
  });
  $('sequence-temporal-count').textContent=`${sequenceTemporalRanges.length} staged human-defined ranges. Empty ranges mean no authored temporal labels, not a physical negative.`;
  sequenceTemporalControls();
}
function sequenceTemporalAction(fn){try{fn();}catch(error){$('sequence-temporal-status').textContent=error.message;}}
function sequenceTemporalShown(record){
  ++sequenceTemporalEpoch;sequenceTemporalOwner=record.kind==='sequence'?structuredClone(record):null;sequenceTemporalRanges=[];sequenceTemporalUsed=false;sequenceTemporalResetControls();
  $('sequence-temporal').hidden=!sequenceTemporalOwner;$('sequence-temporal-status').textContent='Human labels are author judgments; source fields/provenance remain immutable.';
  if(sequenceTemporalOwner&&record.annotation&&Object.hasOwn(record.annotation,'temporal_labels')){
    try{
      const saved=record.annotation.temporal_labels;
      if(!saved||typeof saved!=='object'||Array.isArray(saved))throw Error('Saved temporal envelope is malformed.');
      const canonical=sequenceTemporalEnvelope(record,saved.ranges);
      if(!sequenceTemporalEqual(saved,canonical))throw Error('Saved temporal envelope is malformed or associated with a different source.');
      sequenceTemporalRanges=canonical.ranges;sequenceTemporalUsed=true;
    }catch(error){sequenceTemporalOwner=null;$('sequence-temporal-status').textContent=error.message+' Existing targets have not been replaced. Inspect history and recover deliberately.';}
  }
  sequenceTemporalRender();
}
for(const name of ['first','last','label','rationale'])for(const event of ['input','change'])$('sequence-temporal-'+name).addEventListener(event,()=>{
  if(!sequenceTemporalCurrent())return;sequenceTemporalPending=true;sequenceTemporalControls();
});
$('sequence-temporal-add').addEventListener('click',()=>sequenceTemporalAction(()=>{
  sequenceTemporalGuard();const frames=['first','last'].map(name=>{const raw=$('sequence-temporal-'+name).value;if(!/^[0-8]$/.test(raw))throw Error('Choose native endpoint frames 0 through 8.');return Number(raw);});
  const [a,b]=frames;if(a>b)throw Error('The first frame must not follow the last frame.');
  const label=sequenceTemporalText($('sequence-temporal-label').value,'Human label',80),note=sequenceTemporalText($('sequence-temporal-rationale').value,'Human rationale',500);
  const entry={label,note,start_frame:a,end_frame:b,start:sequenceTemporalAnchor(sequenceTemporalOwner,a),end:sequenceTemporalAnchor(sequenceTemporalOwner,b)},next=structuredClone(sequenceTemporalRanges);
  if(sequenceTemporalEditing===null)next.push(entry);else next[sequenceTemporalEditing]=entry;
  const checked=sequenceTemporalPayload(sequenceTemporalOwner,$('sequence-note').value,next);
  sequenceTemporalRanges=checked.temporal_labels.ranges;sequenceTemporalUsed=true;++sequenceTemporalEpoch;sequenceTemporalResetControls();markDirty();sequenceTemporalRender();$('sequence-temporal-status').textContent='Human range staged in the draft. Save and human review remain separate explicit actions.';
}));
$('sequence-temporal-cancel').addEventListener('click',()=>sequenceTemporalAction(()=>{
  sequenceTemporalGuard();++sequenceTemporalEpoch;sequenceTemporalResetControls();sequenceTemporalRender();$('sequence-temporal-status').textContent='Pending range canceled. Staged targets and other draft edits retained; review choice unchanged.';
}));
$('sequence-temporal-clear').addEventListener('click',()=>sequenceTemporalAction(()=>{
  sequenceTemporalGuard();if(sequenceTemporalPending)throw Error('Add/Update or Cancel the pending range first.');
  sequenceTemporalPayload(sequenceTemporalOwner,$('sequence-note').value,[]);sequenceTemporalRanges=[];sequenceTemporalUsed=true;++sequenceTemporalEpoch;markDirty();sequenceTemporalRender();$('sequence-temporal-status').textContent='All temporal ranges cleared in the draft. This is no physical negative or approval.';
}));
window.addEventListener('pagehide',()=>{sequenceTemporalDeparted=true;++sequenceTemporalEpoch;if(sequenceTemporalOwner&&current?.id===sequenceTemporalOwner.id)++editorEpoch;sequenceTemporalControls();});
window.addEventListener('pageshow',event=>{if(!event.persisted)return;sequenceTemporalDeparted=false;++sequenceTemporalEpoch;
  if(!sequenceTemporalCurrent()){$('sequence-temporal-status').textContent='Restored temporal draft has a different record/revision. Reload deliberately; no targets copied.';sequenceTemporalControls();return;}
  sequenceTemporalRender();$('sequence-temporal-status').textContent='Restored staged ranges and pending draft controls. Save still checks the exact source/annotation revisions.';
});
