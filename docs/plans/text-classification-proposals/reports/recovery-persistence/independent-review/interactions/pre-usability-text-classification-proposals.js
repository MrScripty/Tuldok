'use strict';
let textClassificationProposalJobs = [], textClassificationProposalEpoch = 0, textClassificationProposalModelEpoch = 0;
let textClassificationProposalTimer = null, textClassificationProposalPaused = false, textClassificationProposalBusy = false;
let textClassificationProposalPendingRequest = null, textClassificationProposalAdmissionRequest = null, textClassificationProposalRendered = '';
let textClassificationProposalFormEpoch = 0;
const textClassificationProposalStorageKey = 'tuldok.text-classification-proposals.admission.v1';
const textClassificationProposalStorageLimit = 64000;
let textClassificationProposalStorageBlocked = '', textClassificationProposalRecoveryId = null, textClassificationProposalStorageMalformed = false;
const textClassificationProposalActive = job => ['preparing','generating','stopping'].includes(job.status);
function textClassificationProposalStatus(message) { $('text-classification-proposal-status').textContent = message; }
function validateTextClassificationProposalLabels(labels) {
  // Match the annotation contract's Python str.strip whitespace, including NEL
  // and the information separators; a BOM remains an exact label character.
  const edgeWhitespace=/^[\u0009-\u000D\u001C-\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]|[\u0009-\u000D\u001C-\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]$/u;
  if(!Array.isArray(labels) || labels.length<1 || labels.length>30 || labels.some(label=>typeof label!=='string' || !label || edgeWhitespace.test(label) || Array.from(label).length>80 || /[\uD800-\uDFFF]/u.test(label)) || new Set(labels).size!==labels.length)
    throw Error('Offer 1–30 unique exact labels, each 1–80 Unicode code points with no leading or trailing whitespace. No labels are trimmed or repaired.');
  return labels;
}
function textClassificationProposalLabels() {
  let labels;
  try { labels=JSON.parse($('text-classification-proposal-labels').value); } catch { throw Error('Enter label choices as a JSON array of exact strings.'); }
  return validateTextClassificationProposalLabels(labels);
}
function validateTextClassificationProposalBody(body) {
  const keys=['request_id','source_id','revision','source_revision','server_url','model','instruction','seed','labels'];
  if(!body || typeof body!=='object' || Array.isArray(body) || Object.keys(body).length!==keys.length || keys.some(key=>!Object.hasOwn(body,key)) ||
     typeof body.request_id!=='string' || !/^[a-f0-9]{32}$/.test(body.request_id) || typeof body.source_id!=='string' || !/^[a-f0-9]{32}$/.test(body.source_id) ||
     !['revision','source_revision'].every(key=>Number.isSafeInteger(body[key]) && body[key]>0) ||
     !Number.isInteger(body.seed) || body.seed<0 || body.seed>4294967295)
    throw Error('Invalid classification recovery identity or revision evidence.');
  const validText=(value,max)=>typeof value==='string' && /[^\u0009-\u000D\u001C-\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]/u.test(value) && Array.from(value).length<=max && !/[\uD800-\uDFFF]/u.test(value);
  if(!validText(body.instruction,2000) || !validText(body.model,200) || /[\u0000-\u001F]/u.test(body.model) || typeof body.server_url!=='string' || body.server_url.length>4096)
    throw Error('Invalid bounded classification recovery settings.');
  let url;
  try { url=new URL(body.server_url.trim()); } catch { throw Error('Enter a valid classification gateway URL.'); }
  if(!['http:','https:'].includes(url.protocol) || !url.hostname || url.username || url.password || url.search || url.hash || url.port==='0' || /\s|[\u0000-\u001F]/u.test(body.server_url.trim()))
    throw Error('Use a classification gateway URL without credentials, query or fragment.');
  validateTextClassificationProposalLabels(body.labels);
  if(JSON.stringify(body).length>textClassificationProposalStorageLimit-100)
    throw Error('Classification recovery settings exceed the bounded storage limit.');
  return body;
}
function textClassificationProposalStored(raw) {
  if(typeof raw!=='string' || raw.length>textClassificationProposalStorageLimit) throw Error('Oversized recovery record.');
  const envelope=JSON.parse(raw);
  if(JSON.stringify(envelope)!==raw)throw Error('Noncanonical or ambiguous recovery record.');
  if(!envelope || envelope.schema_version!==1 || Object.keys(envelope).length!==2 || !Object.hasOwn(envelope,'body')) throw Error('Malformed recovery record.');
  return validateTextClassificationProposalBody(envelope.body);
}
function textClassificationProposalStoredId(raw) {
  if(typeof raw!=='string' || raw.length>textClassificationProposalStorageLimit)return null;
  try { const parsed=JSON.parse(raw),id=parsed?.body?.request_id;return JSON.stringify(parsed)===raw && typeof id==='string' && /^[a-f0-9]{32}$/.test(id)?id:null; } catch { return null; }
}
function textClassificationProposalRestoreStorage() {
  let raw;
  try { raw=localStorage.getItem(textClassificationProposalStorageKey); }
  catch { textClassificationProposalStorageBlocked='Classification recovery storage cannot be read. Requests are blocked; restore storage access and refresh requests.';return false; }
  if(raw===null) {
    if(textClassificationProposalStorageMalformed) return false;
    textClassificationProposalStorageBlocked='';return true;
  }
  let body;
  try { body=textClassificationProposalStored(raw); }
  catch {
    textClassificationProposalStorageMalformed=true;
    const id=textClassificationProposalStoredId(raw);if(id)textClassificationProposalRecoveryId=id;
    textClassificationProposalStorageBlocked='Classification recovery storage is malformed or stale. Requests are blocked until its exact admission is authoritatively reconciled; it was not discarded.';return false;
  }
  if(textClassificationProposalPendingRequest && JSON.stringify(body)!==JSON.stringify(textClassificationProposalPendingRequest)) {
    textClassificationProposalStorageBlocked='Another classification admission occupies recovery storage. Requests are blocked; an older acknowledgement cannot erase its identity.';return false;
  }
  if(!textClassificationProposalPendingRequest)textClassificationProposalPendingRequest=body;
  textClassificationProposalRecoveryId=body.request_id;
  if(!textClassificationProposalStorageMalformed)textClassificationProposalStorageBlocked='';
  return !textClassificationProposalStorageBlocked;
}
function textClassificationProposalJobMatches(job, body) {
  return job?.id===body.request_id && job.source?.id===body.source_id && job.source.revision===body.revision && job.source.source_revision===body.source_revision &&
    job.config?.requested_server_url===body.server_url && job.config.requested_model===body.model && job.config.instruction===body.instruction && job.config.seed===body.seed && JSON.stringify(job.config.labels)===JSON.stringify(body.labels);
}
async function textClassificationProposalStorageLock(fn) {
  if(typeof navigator==='undefined' || !navigator.locks?.request) {
    textClassificationProposalStorageBlocked='This browser lacks Web Locks. Classification requests are blocked because admission recovery cannot be coordinated across pages.';
    throw Error(textClassificationProposalStorageBlocked);
  }
  return navigator.locks.request(textClassificationProposalStorageKey,{mode:'exclusive'},fn);
}
async function textClassificationProposalClearStorage(id, body) {
  return textClassificationProposalStorageLock(()=>{
    let raw;
    try { raw=localStorage.getItem(textClassificationProposalStorageKey); }
    catch { textClassificationProposalStorageBlocked='Classification recovery storage cannot be read. Requests remain blocked.';return false; }
    if(raw!==null) {
      let stored,storedId;
      try { stored=textClassificationProposalStored(raw);storedId=stored.request_id; }
      catch { storedId=textClassificationProposalStoredId(raw); }
      if(storedId!==id || (stored && body && JSON.stringify(stored)!==JSON.stringify(body))) {
        textClassificationProposalStorageBlocked='Classification recovery storage changed. Requests remain blocked; this receipt cannot erase another admission.';return false;
      }
      try { localStorage.removeItem(textClassificationProposalStorageKey); }
      catch { textClassificationProposalStorageBlocked='Classification recovery storage could not be cleared after an authoritative receipt. Requests remain blocked; refresh to reconcile it again.';return false; }
    }
    if(!body || textClassificationProposalPendingRequest===body)textClassificationProposalPendingRequest=null;
    textClassificationProposalRecoveryId=null;textClassificationProposalStorageMalformed=false;textClassificationProposalStorageBlocked='';return true;
  });
}
// Storage is already scoped to the page's origin. Restore before submit listeners
// or any asynchronous list fetch can authorize a new admission identity.
$('text-classification-proposal-submit').disabled=true;
textClassificationProposalRestoreStorage();
$('text-classification-proposal-submit').disabled=false;
if(textClassificationProposalStorageBlocked)textClassificationProposalStatus(textClassificationProposalStorageBlocked);
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
  textClassificationProposalRestoreStorage();
  clearTimeout(textClassificationProposalTimer);const epoch=++textClassificationProposalEpoch;
  const pending=textClassificationProposalPendingRequest,recoveryId=pending?.request_id||textClassificationProposalRecoveryId;
  const result=await api('text-classification-proposals');if(epoch!==textClassificationProposalEpoch||textClassificationProposalPaused)return;
  textClassificationProposalJobs=result.jobs;
  if(recoveryId && (!pending || !textClassificationProposalJobs.some(job=>job.id===recoveryId))) {
    try {
      const exact=await api('text-classification-proposals/'+recoveryId);
      if(epoch!==textClassificationProposalEpoch||textClassificationProposalPaused)return;
      if(exact.id!==recoveryId)throw Error('The exact classification recovery receipt has a different identity.');
      textClassificationProposalJobs=textClassificationProposalJobs.filter(job=>job.id!==recoveryId);textClassificationProposalJobs.unshift(exact);
    } catch(error) {
      if(epoch!==textClassificationProposalEpoch||textClassificationProposalPaused)return;
      if(error.status===404) {
        textClassificationProposalStatus('The request ID is not visible yet. Its admission or acknowledgement may still arrive; an explicit unchanged repeat keeps this ID.');
      } else throw error;
    }
  }
  const recovered=textClassificationProposalJobs.find(job=>job.id===recoveryId);
  if(recovered && (!pending || (pending===textClassificationProposalPendingRequest && textClassificationProposalAdmissionRequest!==pending))) {
    if(pending && !textClassificationProposalJobMatches(recovered,pending)) {
      textClassificationProposalStorageMalformed=true;textClassificationProposalStorageBlocked='The persisted classification receipt does not match the exact stored intent. Requests remain blocked; no identity was discarded.';
    } else if(await textClassificationProposalClearStorage(recoveryId,pending)) {
      if(epoch!==textClassificationProposalEpoch||textClassificationProposalPaused)return;
      textClassificationProposalStatus('Persisted request recovered. Inspect its status; no inference was retried.');
    }
  }
  if(textClassificationProposalStorageBlocked)textClassificationProposalStatus(textClassificationProposalStorageBlocked);
  renderTextClassificationProposals();
  if(textClassificationProposalJobs.some(textClassificationProposalActive)||textClassificationProposalPendingRequest||textClassificationProposalRecoveryId)textClassificationProposalTimer=setTimeout(()=>refreshTextClassificationProposals().catch(error=>textClassificationProposalStatus(error.message)),1000);
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
  let previous,body,posted=false;
  textClassificationProposalBusy=true;$('text-classification-proposal-submit').disabled=true;
  try {
    body=await textClassificationProposalStorageLock(()=>{
      if(!textClassificationProposalRestoreStorage())throw Error(textClassificationProposalStorageBlocked);
      previous=textClassificationProposalPendingRequest;
      if(previous && JSON.stringify({...previous,request_id:undefined})!==JSON.stringify(intent))
        throw Error('An earlier request has an unknown acknowledgement. Refresh requests before changing its intent.');
      const captured=previous || {...intent,request_id:crypto.randomUUID().replaceAll('-','')};
      validateTextClassificationProposalBody(captured);
      textClassificationProposalPendingRequest=captured;textClassificationProposalRecoveryId=captured.request_id;
      try { localStorage.setItem(textClassificationProposalStorageKey,JSON.stringify({schema_version:1,body:captured})); }
      catch {textClassificationProposalStorageBlocked='Classification recovery storage could not persist the exact request. Inference is blocked; refresh storage and explicitly repeat this unchanged request.';throw Error(textClassificationProposalStorageBlocked);}
      textClassificationProposalAdmissionRequest=captured;return captured;
    });
    posted=true;
    const receipt=await api('text-classification-proposals',body);
    if(!textClassificationProposalJobMatches(receipt,body))throw Error('The classification acknowledgement does not match the exact stored admission intent.');
    if(!await textClassificationProposalClearStorage(body.request_id,body))throw Error(textClassificationProposalStorageBlocked);
    textClassificationProposalStatus('Classification requested. Current annotations remain unchanged.');await refreshTextClassificationProposals();
  }
  catch(error) {
    if(posted && !previous && error.status>=400 && error.status<500 && textClassificationProposalPendingRequest===body)await textClassificationProposalClearStorage(body.request_id,body);
    textClassificationProposalStatus((textClassificationProposalStorageBlocked||error.message)+' Refresh requests to reconcile. An explicit repeat of this unchanged request uses the same ID; no automatic retry.');
  }
  finally {if(textClassificationProposalAdmissionRequest===body)textClassificationProposalAdmissionRequest=null;textClassificationProposalBusy=false;$('text-classification-proposal-submit').disabled=false;}
});
action('text-classification-proposal-refresh',refreshTextClassificationProposals);
action('text-classification-proposal-restore',()=>{
  if(!textClassificationProposalRestoreStorage())throw Error(textClassificationProposalStorageBlocked);
  const body=textClassificationProposalPendingRequest;
  if(!body)throw Error('No unresolved classification admission is stored.');
  ++textClassificationProposalModelEpoch;++textClassificationProposalFormEpoch;
  $('text-classification-proposal-url').value=body.server_url;
  const option=document.createElement('option');option.value=body.model;option.textContent=body.model;
  $('text-classification-proposal-model').replaceChildren(option);$('text-classification-proposal-model').value=body.model;
  $('text-classification-proposal-guidance').value=body.instruction;$('text-classification-proposal-seed').value=body.seed;
  $('text-classification-proposal-labels').value=JSON.stringify(body.labels);
  $('text-classification-proposal-pending-evidence').textContent=JSON.stringify(body,null,2);$('text-classification-proposal-pending-evidence').hidden=false;
  textClassificationProposalStatus(`Frozen request settings restored for record ${body.source_id}, record revision ${body.revision} / source ${body.source_revision}. Open that exact unannotated source and explicitly submit to repeat the same admission ID. No request was sent.`);
});
action('text-classification-proposal-open-pending',()=>{
  if(!textClassificationProposalRestoreStorage())throw Error(textClassificationProposalStorageBlocked);
  if(!textClassificationProposalPendingRequest)throw Error('No unresolved classification admission is stored.');
  return openRecord(textClassificationProposalPendingRequest.source_id);
});
window.addEventListener('pagehide',()=>{textClassificationProposalPaused=true;++textClassificationProposalEpoch;++textClassificationProposalModelEpoch;clearTimeout(textClassificationProposalTimer);});
window.addEventListener('pageshow',()=>{if(textClassificationProposalPaused){textClassificationProposalPaused=false;refreshTextClassificationProposals().catch(error=>textClassificationProposalStatus(error.message));}});
if(textClassificationProposalPendingRequest||textClassificationProposalStorageBlocked)refreshTextClassificationProposals().catch(error=>textClassificationProposalStatus(error.message));
