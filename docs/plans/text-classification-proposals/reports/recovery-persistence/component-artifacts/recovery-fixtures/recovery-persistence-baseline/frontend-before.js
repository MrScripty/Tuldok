'use strict';
let textClassificationProposalJobs = [], textClassificationProposalEpoch = 0, textClassificationProposalModelEpoch = 0;
let textClassificationProposalTimer = null, textClassificationProposalPaused = false, textClassificationProposalBusy = false;
let textClassificationProposalPendingRequest = null, textClassificationProposalAdmissionRequest = null, textClassificationProposalRendered = '';
let textClassificationProposalFormEpoch = 0;
const textClassificationProposalActive = job => ['preparing','generating','stopping'].includes(job.status);
function textClassificationProposalStatus(message) { $('text-classification-proposal-status').textContent = message; }
function textClassificationProposalLabels() {
  let labels;
  try { labels=JSON.parse($('text-classification-proposal-labels').value); } catch { throw Error('Enter label choices as a JSON array of exact strings.'); }
  // Match the annotation contract's Python str.strip whitespace, including NEL
  // and the information separators; a BOM remains an exact label character.
  const edgeWhitespace=/^[\u0009-\u000D\u001C-\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]|[\u0009-\u000D\u001C-\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]$/u;
  if(!Array.isArray(labels) || labels.length<1 || labels.length>30 || labels.some(label=>typeof label!=='string' || !label || edgeWhitespace.test(label) || Array.from(label).length>80 || /[\uD800-\uDFFF]/u.test(label)) || new Set(labels).size!==labels.length)
    throw Error('Offer 1–30 unique exact labels, each 1–80 Unicode code points with no leading or trailing whitespace. No labels are trimmed or repaired.');
  return labels;
}
function textClassificationProposalConfig() {
  return {server_url:$('text-classification-proposal-url').value,model:$('text-classification-proposal-model').value,
    instruction:$('text-classification-proposal-guidance').value,seed:Number($('text-classification-proposal-seed').value),labels:textClassificationProposalLabels()};
}
function textClassificationProposalsShown(record) {
  ++textClassificationProposalEpoch; clearTimeout(textClassificationProposalTimer); textClassificationProposalRendered = '';
  $('text-classification-proposal-panel').hidden = record.kind !== 'text';
  renderTextClassificationProposals();
  if(record.kind === 'text') refreshTextClassificationProposals().catch(error=>textClassificationProposalStatus(error.message));
}
function textClassificationProposalButton(label, fn) {
  const button=document.createElement('button');button.type='button';button.textContent=label;
  button.addEventListener('click',async()=>{
    if(textClassificationProposalBusy)return;textClassificationProposalBusy=true;button.disabled=true;
    try { await fn(); } catch(error) { textClassificationProposalStatus(error.message); }
    finally { textClassificationProposalBusy=false;button.disabled=false; }
  });return button;
}
function renderTextClassificationProposals() {
  const jobs=textClassificationProposalJobs.filter(job=>job.source.id===current?.id);
  const signature=JSON.stringify([current?.id,jobs]);if(signature===textClassificationProposalRendered)return;
  textClassificationProposalRendered=signature;$('text-classification-proposal-jobs').replaceChildren();
  for(const job of jobs) {
    const section=document.createElement('section');section.className='proposal';
    const summary=document.createElement('p');summary.textContent=`${job.config.model} · ${job.status} · captured record ${job.source.revision} / source ${job.source.source_revision} · ${job.error || 'Label shape checks do not establish correctness.'}`;
    section.append(summary);
    if(job.annotation) { const label=document.createElement('p');label.textContent='Proposed exact label: '+JSON.stringify(job.annotation.label);section.append(label); }
    if(job.status==='abstained') { const note=document.createElement('p');note.textContent='The model explicitly abstained. No label or draft can be applied.';section.append(note); }
    if(textClassificationProposalActive(job)) section.append(textClassificationProposalButton('Cancel classification request',async()=>{
      await api('text-classification-proposals/cancel',{job_id:job.id});await refreshTextClassificationProposals();
    }));
    if(job.status==='completed') section.append(textClassificationProposalButton('Apply as draft',()=>decideTextClassificationProposal(job,'apply_draft')));
    if(['completed','abstained'].includes(job.status)) section.append(textClassificationProposalButton('Reject classification proposal',()=>decideTextClassificationProposal(job,'reject')));
    if(job.status==='applied')section.append(textClassificationProposalButton('Open applied classification',()=>openRecord(job.source.id)));
    section.append(textClassificationProposalButton('Inspect request evidence',async()=>{
      const epoch=textClassificationProposalEpoch,id=current?.id;const detail=await api('text-classification-proposals/'+job.id);
      if(epoch!==textClassificationProposalEpoch||id!==current?.id||textClassificationProposalPaused)return;
      const display={...detail};delete display.raw_response_base64;
      const evidence=document.createElement('pre');evidence.textContent=JSON.stringify(display,null,2);section.append(evidence);
    }));
    $('text-classification-proposal-jobs').append(section);
  }
}
async function refreshTextClassificationProposals() {
  if(textClassificationProposalPaused)return;
  clearTimeout(textClassificationProposalTimer);const epoch=++textClassificationProposalEpoch;
  const result=await api('text-classification-proposals');if(epoch!==textClassificationProposalEpoch||textClassificationProposalPaused)return;
  textClassificationProposalJobs=result.jobs;
  if(textClassificationProposalPendingRequest && !textClassificationProposalJobs.some(job=>job.id===textClassificationProposalPendingRequest.request_id)) {
    const pending=textClassificationProposalPendingRequest;
    try {
      const exact=await api('text-classification-proposals/'+pending.request_id);
      if(epoch!==textClassificationProposalEpoch||textClassificationProposalPaused)return;
      textClassificationProposalJobs.unshift(exact);
    } catch(error) {
      if(epoch!==textClassificationProposalEpoch||textClassificationProposalPaused)return;
      if(error.status===404 && textClassificationProposalPendingRequest===pending) {
        textClassificationProposalStatus('The request ID is not visible yet. Its admission or acknowledgement may still arrive; an explicit unchanged repeat keeps this ID.');
      } else throw error;
    }
  }
  if(textClassificationProposalPendingRequest && textClassificationProposalAdmissionRequest!==textClassificationProposalPendingRequest && textClassificationProposalJobs.some(job=>job.id===textClassificationProposalPendingRequest.request_id)) {
    textClassificationProposalPendingRequest=null;textClassificationProposalStatus('Persisted request recovered. Inspect its status; no inference was retried.');
  }
  renderTextClassificationProposals();
  if(textClassificationProposalJobs.some(textClassificationProposalActive))textClassificationProposalTimer=setTimeout(()=>refreshTextClassificationProposals().catch(error=>textClassificationProposalStatus(error.message)),1000);
}
async function decideTextClassificationProposal(job, decision) {
  const record=current;
  let labels;
  if(decision==='apply_draft') {
    if(record?.id!==job.source.id || record.kind!=='text' || record.annotation!=null || record.revision!==job.source.revision || record.source_revision!==job.source.source_revision || record.content_hash!==job.source.content_hash || record.source_sha256!==job.source.source_sha256 || hasUnsavedEdits() || $('editor').dataset.busy)
      throw Error('Open the exact captured unannotated text and save or discard edits before applying a draft. A changed source requires a new request.');
    const config=textClassificationProposalConfig();labels=config.labels;
    if(Object.entries(config).some(([key,value])=>JSON.stringify(value)!==JSON.stringify(key==='server_url'?(job.config.requested_server_url??job.config.server_url):key==='model'?(job.config.requested_model??job.config.model):job.config[key])))
      throw Error('Restore the exact frozen label choices, gateway, model, guidance and seed before applying this proposal. Inspect its request evidence; changed choices require a new request.');
    if(job.status!=='completed' || !job.annotation || !labels.includes(job.annotation.label))
      throw Error('Only a completed proposal with an exact offered label can be applied. Abstention and malformed labels never receive a fallback.');
  }
  const epoch=decision==='apply_draft'?++editorEpoch:editorEpoch,responseEpoch=responseIntentEpoch(),formEpoch=textClassificationProposalFormEpoch;
  let result;
  try { result=await api('text-classification-proposals/decide/'+job.id,{revision:job.revision,decision,...(labels?{labels}:{})}); }
  catch(error) {
    if(decision==='apply_draft') { invalidateRelease();if(typeof invalidateResponsePreview==='function')invalidateResponsePreview(); }
    throw Error(error.message+' Refresh requests and inspect the record before retrying; an application acknowledgement may have been lost.');
  }
  if(result.record) {
    invalidateRelease();if(typeof invalidateResponsePreview==='function')invalidateResponsePreview();
    if(!textClassificationProposalPaused && epoch===editorEpoch && responseEpoch===responseIntentEpoch() && formEpoch===textClassificationProposalFormEpoch && current?.id===record.id && !hasUnsavedEdits())showRecord(result.record);
    textClassificationProposalStatus('Classification applied as draft. Fixed selections retain their old revisions; explicitly review and reselect before export. Later edits are retained if the editor changed.');
    if(!textClassificationProposalPaused)await refresh();
  } else textClassificationProposalStatus('Classification rejected. The request evidence is retained; no annotation changed.');
  await refreshTextClassificationProposals();
}
$('text-classification-proposal-url').addEventListener('input',()=>{++textClassificationProposalModelEpoch;$('text-classification-proposal-model').replaceChildren();});
for(const id of ['url','model','guidance','seed','labels']) {
  const input=$('text-classification-proposal-'+id);
  for(const event of ['input','change'])input.addEventListener(event,()=>{++textClassificationProposalFormEpoch;});
}
action('text-classification-proposal-models',async()=>{
  const epoch=++textClassificationProposalModelEpoch,url=$('text-classification-proposal-url').value;
  const result=await api('/api/generation/prompt-models',{server_url:url});
  if(epoch!==textClassificationProposalModelEpoch||url!==$('text-classification-proposal-url').value||textClassificationProposalPaused)return;
  ++textClassificationProposalFormEpoch;
  $('text-classification-proposal-model').replaceChildren();for(const model of result.models) {
    const option=document.createElement('option');option.value=model.id;option.textContent=model.name;$('text-classification-proposal-model').append(option);
  }
  textClassificationProposalStatus('Listed served text models. Listing does not establish classification or JSON compatibility; incompatible requests fail without fallback.');
});
$('text-classification-proposal-form').addEventListener('submit',async event=>{
  event.preventDefault();if(textClassificationProposalBusy)return;
  if(current?.kind!=='text'||current.annotation!=null||hasUnsavedEdits()||$('editor').dataset.busy) {textClassificationProposalStatus('Select an existing unannotated text and save or discard edits before requesting a classification.');return;}
  let config;
  try { config=textClassificationProposalConfig(); } catch(error) {textClassificationProposalStatus(error.message);return;}
  const intent={source_id:current.id,revision:current.revision,source_revision:current.source_revision,
    ...config};
  const previous=textClassificationProposalPendingRequest;
  if(previous && JSON.stringify({...previous,request_id:undefined})!==JSON.stringify(intent)) {
    textClassificationProposalStatus('An earlier request has an unknown acknowledgement. Refresh requests before changing its intent.');return;
  }
  const body=previous || {...intent,request_id:crypto.randomUUID().replaceAll('-','')};textClassificationProposalPendingRequest=body;
  textClassificationProposalAdmissionRequest=body;textClassificationProposalBusy=true;$('text-classification-proposal-submit').disabled=true;
  try { await api('text-classification-proposals',body);if(textClassificationProposalPendingRequest===body)textClassificationProposalPendingRequest=null;textClassificationProposalStatus('Classification requested. Current annotations remain unchanged.');await refreshTextClassificationProposals(); }
  catch(error) {if(!previous && error.status>=400 && error.status<500 && textClassificationProposalPendingRequest===body)textClassificationProposalPendingRequest=null;textClassificationProposalStatus(error.message+' Refresh requests to reconcile. An explicit repeat of this unchanged request uses the same ID; no automatic retry.');}
  finally {if(textClassificationProposalAdmissionRequest===body)textClassificationProposalAdmissionRequest=null;textClassificationProposalBusy=false;$('text-classification-proposal-submit').disabled=false;}
});
action('text-classification-proposal-refresh',refreshTextClassificationProposals);
window.addEventListener('pagehide',()=>{textClassificationProposalPaused=true;++textClassificationProposalEpoch;++textClassificationProposalModelEpoch;clearTimeout(textClassificationProposalTimer);});
window.addEventListener('pageshow',()=>{if(textClassificationProposalPaused){textClassificationProposalPaused=false;refreshTextClassificationProposals().catch(error=>textClassificationProposalStatus(error.message));}});
