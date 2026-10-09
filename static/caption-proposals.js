'use strict';
let captionProposalJobs = [], captionProposalEpoch = 0, captionProposalModelEpoch = 0;
let captionProposalTimer = null, captionProposalPaused = false, captionProposalBusy = false;
let captionProposalPendingRequest = null, captionProposalAdmissionRequest = null, captionProposalRendered = '';
const captionProposalRecoveryKey = 'tuldok.caption-proposal-recovery.v1';
let captionProposalStorageError = '';
function captionProposalIntent(body) {
  return {source_id:body.source_id,revision:body.revision,source_revision:body.source_revision,
    server_url:body.server_url,model:body.model,instruction:body.instruction,seed:body.seed};
}
// Match Python's strip/isspace set; JS trim differs for U+0085, U+001C–1F and FEFF.
const captionProposalWhitespace = /[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]/u;
function captionProposalStrip(value) {
  return value.replace(/^[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+|[\u0009-\u000d\u001c-\u0020\u0085\u00a0\u1680\u2000-\u200a\u2028\u2029\u202f\u205f\u3000]+$/gu,'');
}
function captionProposalText(value,name,maximum,controls=false) {
  if(typeof value!=='string' || [...value].length>maximum || !captionProposalStrip(value) ||
     [...value].some(c=>c.codePointAt(0)>=0xd800 && c.codePointAt(0)<=0xdfff) ||
     (controls && /[\u0000-\u001f]/u.test(value)))
    throw Error(`${name} must be nonempty valid Unicode text, at most ${maximum.toLocaleString('en-US')} Unicode code points${controls?', without control characters':''}.`);
}
function captionProposalServerURL(value) {
  if(typeof value!=='string')throw Error('Enter the local model server URL.');
  const stripped=captionProposalStrip(value);
  if(!stripped || [...stripped].some(c=>captionProposalWhitespace.test(c) || c.codePointAt(0)<32 ||
     (c.codePointAt(0)>=0xd800 && c.codePointAt(0)<=0xdfff)))
    throw Error('Enter a server URL without internal whitespace, control characters or invalid Unicode.');
  // Check the original authority before WHATWG URL can repair missing slashes/hosts.
  const parts=/^(https?):\/\/([^/?#]+)([^?#]*)(?:\?([^#]*))?(?:#(.*))?$/iu.exec(stripped);
  if(!parts || parts[2].includes('@') || parts[4] || parts[5])
    throw Error('Use an HTTP or HTTPS server URL with a hostname, without credentials, query or fragment.');
  const authority=parts[2];
  const normalizedAuthority=authority.replace(/[@:#?]/gu,'').normalize('NFKC');
  if(/[/?#@:]/u.test(normalizedAuthority))throw Error('Use a hostname without characters that normalize to URL delimiters.');
  // Backslashes can be reinterpreted by WHATWG as path separators; urlsplit does not.
  if(authority.includes('\\'))throw Error('Use a server hostname without backslashes.');
  let url;try {url=new URL(stripped);}catch {throw Error('Enter a valid HTTP or HTTPS server URL.');}
  const port=authority.startsWith('[')?authority.slice(authority.indexOf(']')+1):authority.slice(authority.indexOf(':')<0?authority.length:authority.indexOf(':'));
  if(!url.hostname || (port && !/^:(?:[0-9]*)$/u.test(port)) || (port.length>1 && (Number(port.slice(1))===0 || Number(port.slice(1))>65535)))
    throw Error('Use a valid server hostname and port from 1 to 65535.');
  // The backend bounds its normalized URL, before any percent encoding by WHATWG.
  let path=parts[3].replace(/\/+$/u,'');if(path.endsWith('/v1'))path=path.slice(0,-3);
  captionProposalText(parts[1].toLowerCase()+'://'+authority+path,'Server URL',2048);
}
function captionProposalRecoveryBody(body) {
  const fields=['source_id','revision','source_revision','server_url','model','instruction','seed','request_id'];
  if(!body || typeof body!=='object' || Object.keys(body).length!==fields.length || fields.some(field=>!Object.hasOwn(body,field)) ||
     typeof body.request_id!=='string' || typeof body.source_id!=='string' || body.request_id.length!==32 || body.source_id.length!==32 || !/^[a-f0-9]{32}$/.test(body.request_id) || !/^[a-f0-9]{32}$/.test(body.source_id) ||
     !Number.isSafeInteger(body.revision) || body.revision<1 || !Number.isSafeInteger(body.source_revision) || body.source_revision<1 ||
     !Number.isInteger(body.seed) || body.seed<0 || body.seed>4294967295)
    throw Error('Invalid request identifiers, revisions or seed.');
  captionProposalServerURL(body.server_url);
  captionProposalText(body.model,'Model ID',200,true);
  captionProposalText(body.instruction,'Caption guidance',2000);
  // Validate without rewriting the exact body used for the backend intent hash.
  const intent={...captionProposalIntent(body),request_id:body.request_id};
  if(JSON.stringify(intent).length>32768)throw Error('Exact request exceeds this tab’s recovery bound. Shorten the server URL and submit again.');
  return intent;
}
function captionProposalStoredRequest() {
  const data=sessionStorage.getItem(captionProposalRecoveryKey);
  if(data===null)return null;
  if(data.length>32768)throw Error('Recovery intent exceeds its bound.');
  return captionProposalRecoveryBody(JSON.parse(data));
}
function captionProposalSameRequest(a,b) {return JSON.stringify(a)===JSON.stringify(b);}
function captionProposalSyncRecovery(restoreForm=false) {
  try {
    const stored=captionProposalStoredRequest();
    if(!captionProposalSameRequest(stored,captionProposalPendingRequest))captionProposalPendingRequest=stored;
    if(restoreForm && stored) {
      $('caption-proposal-url').value=stored.server_url;
      $('caption-proposal-guidance').value=stored.instruction;
      $('caption-proposal-seed').value=stored.seed;
      const option=document.createElement('option');option.value=stored.model;option.textContent=option.value+' (recovered request)';
      $('caption-proposal-model').replaceChildren(option);$('caption-proposal-model').value=option.value;
    }
    return true;
  } catch {
    captionProposalStorageError='Caption recovery storage is unavailable or invalid. Restore this tab’s storage and reload before submitting.';
    $('caption-proposal-submit').disabled=true;captionProposalStatus(captionProposalStorageError);return false;
  }
}
function captionProposalStore(body) {
  try {
    // A history-restored document may no longer own this tab's current entry.
    const stored=captionProposalStoredRequest();
    if(!captionProposalSameRequest(stored,captionProposalPendingRequest)) {
      captionProposalPendingRequest=stored;throw Error('Recovery ownership changed.');
    }
    if(body) {
      const data=JSON.stringify(captionProposalRecoveryBody(body));
      if(data.length>32768)throw Error('Recovery intent exceeds its bound.');
      sessionStorage.setItem(captionProposalRecoveryKey,data);
      if(sessionStorage.getItem(captionProposalRecoveryKey)!==data)throw Error('Recovery storage did not retain the request.');
    } else {
      sessionStorage.removeItem(captionProposalRecoveryKey);
      if(sessionStorage.getItem(captionProposalRecoveryKey)!==null)throw Error('Recovery storage did not clear the request.');
    }
    captionProposalStorageError='';return true;
  } catch {
    captionProposalStorageError='Caption recovery storage is unavailable or invalid. New submissions are blocked. Restore this tab’s storage and reload before submitting.';
    return false;
  }
}
// Read before registering submission: a held initial GET must not open a new intent.
captionProposalSyncRecovery(true);
$('caption-proposal-submit').disabled=!!captionProposalStorageError;
if(captionProposalStorageError) $('caption-proposal-status').textContent=captionProposalStorageError;
else if(captionProposalPendingRequest) $('caption-proposal-status').textContent='Unresolved caption request restored. Refresh to inspect its outcome, or explicitly repeat the unchanged intent with the same ID. No inference was replayed.';
const captionProposalActive = job => ['preparing','generating','stopping'].includes(job.status);
function captionProposalStatus(message) { $('caption-proposal-status').textContent = message; }
function captionProposalsShown(record) {
  ++captionProposalEpoch; clearTimeout(captionProposalTimer); captionProposalRendered = '';
  $('caption-proposal-panel').hidden = record.kind !== 'image';
  renderCaptionProposals();
  if(record.kind === 'image') refreshCaptionProposals().catch(error=>captionProposalStatus(error.message));
}
function captionProposalButton(label, fn) {
  const button=document.createElement('button');button.type='button';button.textContent=label;
  button.addEventListener('click',async()=>{
    if(captionProposalBusy)return;captionProposalBusy=true;button.disabled=true;
    try { await fn(); } catch(error) { captionProposalStatus(error.message); }
    finally { captionProposalBusy=false;button.disabled=false; }
  });return button;
}
function renderCaptionProposals() {
  const jobs=captionProposalJobs.filter(job=>job.source.id===current?.id);
  const signature=JSON.stringify([current?.id,jobs]);if(signature===captionProposalRendered)return;
  captionProposalRendered=signature;$('caption-proposal-jobs').replaceChildren();
  for(const job of jobs) {
    const section=document.createElement('section');section.className='proposal';
    const summary=document.createElement('p');summary.textContent=`${job.config.model} · ${job.status} · captured record ${job.source.revision} / source ${job.source.source_revision} · ${job.error || 'Caption shape checks do not establish accuracy.'}`;
    section.append(summary);
    if(job.annotation) { const caption=document.createElement('p');caption.textContent=job.annotation.caption;section.append(caption); }
    if(captionProposalActive(job)) section.append(captionProposalButton('Cancel caption request',async()=>{
      await api('caption-proposals/cancel',{job_id:job.id});await refreshCaptionProposals();
    }));
    if(job.status==='completed') {
      section.append(captionProposalButton('Apply as draft',()=>decideCaptionProposal(job,'apply_draft')),
        captionProposalButton('Reject caption proposal',()=>decideCaptionProposal(job,'reject')));
    }
    if(job.status==='applied')section.append(captionProposalButton('Open applied caption',()=>openRecord(job.source.id)));
    section.append(captionProposalButton('Inspect request evidence',async()=>{
      const epoch=captionProposalEpoch,id=current?.id;const detail=await api('caption-proposals/'+job.id);
      if(epoch!==captionProposalEpoch||id!==current?.id||captionProposalPaused)return;
      const display={...detail};delete display.input_image_base64;delete display.raw_response_base64;
      const evidence=document.createElement('pre');evidence.textContent=JSON.stringify(display,null,2);section.append(evidence);
    }));
    $('caption-proposal-jobs').append(section);
  }
}
async function refreshCaptionProposals() {
  if(captionProposalPaused)return;
  if(!captionProposalSyncRecovery())return;
  clearTimeout(captionProposalTimer);const epoch=++captionProposalEpoch;
  const result=await api('caption-proposals');if(epoch!==captionProposalEpoch||captionProposalPaused)return;
  if(!captionProposalSyncRecovery())return;
  captionProposalJobs=result.jobs;
  if(captionProposalPendingRequest && !captionProposalJobs.some(job=>job.id===captionProposalPendingRequest.request_id)) {
    const pending=captionProposalPendingRequest;
    try {
      const exact=await api('caption-proposals/'+pending.request_id);
      if(epoch!==captionProposalEpoch||captionProposalPaused)return;
      if(!captionProposalSyncRecovery())return;
      captionProposalJobs.unshift(exact);
    } catch(error) {
      if(epoch!==captionProposalEpoch||captionProposalPaused)return;
      if(!captionProposalSyncRecovery())return;
      if(error.status===404 && captionProposalPendingRequest===pending) {
        captionProposalStatus('The request ID is not visible yet. Its admission or acknowledgement may still arrive; an explicit unchanged repeat keeps this ID.');
      } else throw error;
    }
  }
  if(captionProposalPendingRequest && captionProposalAdmissionRequest!==captionProposalPendingRequest && captionProposalJobs.some(job=>job.id===captionProposalPendingRequest.request_id)) {
    if(captionProposalStore(null)) {
      captionProposalPendingRequest=null;$('caption-proposal-submit').disabled=false;
      captionProposalStatus('Persisted request recovered. Inspect its status; no inference was retried.');
    } else { $('caption-proposal-submit').disabled=true;captionProposalStatus(captionProposalStorageError); }
  }
  renderCaptionProposals();
  if(captionProposalJobs.some(captionProposalActive))captionProposalTimer=setTimeout(()=>refreshCaptionProposals().catch(error=>captionProposalStatus(error.message)),1000);
}
async function decideCaptionProposal(job, decision) {
  const record=current;
  if(decision==='apply_draft' && (record?.id!==job.source.id || hasUnsavedEdits() || $('editor').dataset.busy))
    throw Error('Save or discard edits and open the captured image before applying a draft.');
  const epoch=decision==='apply_draft'?++editorEpoch:editorEpoch,responseEpoch=responseIntentEpoch();
  let result;
  try { result=await api('caption-proposals/decide/'+job.id,{revision:job.revision,decision}); }
  catch(error) {
    if(decision==='apply_draft') { invalidateRelease();if(typeof invalidateResponsePreview==='function')invalidateResponsePreview(); }
    throw Error(error.message+' Refresh requests and inspect the record before retrying; an application acknowledgement may have been lost.');
  }
  if(result.record) {
    invalidateRelease();if(typeof invalidateResponsePreview==='function')invalidateResponsePreview();
    if(!captionProposalPaused && epoch===editorEpoch && responseEpoch===responseIntentEpoch() && current?.id===record.id && !hasUnsavedEdits())showRecord(result.record);
    captionProposalStatus('Caption applied as draft. Fixed selections retain their old revisions; explicitly review and reselect before export. Later edits are retained if the editor changed.');
    if(!captionProposalPaused)await refresh();
  } else captionProposalStatus('Caption rejected. The request evidence is retained; no annotation changed.');
  await refreshCaptionProposals();
}
$('caption-proposal-url').addEventListener('input',()=>{++captionProposalModelEpoch;$('caption-proposal-model').replaceChildren();});
action('caption-proposal-models',async()=>{
  const epoch=++captionProposalModelEpoch,url=$('caption-proposal-url').value;
  const result=await api('/api/generation/prompt-models',{server_url:url});
  if(epoch!==captionProposalModelEpoch||url!==$('caption-proposal-url').value||captionProposalPaused)return;
  $('caption-proposal-model').replaceChildren();for(const model of result.models) {
    const option=document.createElement('option');option.value=model.id;option.textContent=model.name;$('caption-proposal-model').append(option);
  }
  captionProposalStatus('Listed non-image served models. Listing does not establish vision or JSON compatibility; incompatible requests fail without fallback.');
});
$('caption-proposal-form').addEventListener('submit',async event=>{
  event.preventDefault();if(captionProposalBusy)return;
  if(!captionProposalSyncRecovery())return;
  if(captionProposalStorageError) {captionProposalStatus(captionProposalStorageError);return;}
  if(current?.kind!=='image'||hasUnsavedEdits()||$('editor').dataset.busy) {captionProposalStatus('Select an image and save or discard edits before requesting a caption.');return;}
  const intent={source_id:current.id,revision:current.revision,source_revision:current.source_revision,
    server_url:$('caption-proposal-url').value,model:$('caption-proposal-model').value,
    instruction:$('caption-proposal-guidance').value,seed:Number($('caption-proposal-seed').value)};
  const previous=captionProposalPendingRequest;
  if(previous && JSON.stringify(captionProposalIntent(previous))!==JSON.stringify(intent)) {
    captionProposalStatus('An earlier request has an unknown acknowledgement. Refresh requests before changing its intent.');return;
  }
  const body=previous || {...intent,request_id:crypto.randomUUID().replaceAll('-','')};
  // Invalid fresh settings are correctable form errors, not lost recovery storage.
  try { captionProposalRecoveryBody(body); }
  catch(error) {captionProposalStatus(error.message+' Correct the request settings and submit again.');return;}
  if(!captionProposalStore(body)) {captionProposalStatus(captionProposalStorageError);$('caption-proposal-submit').disabled=true;return;}
  captionProposalPendingRequest=body;
  captionProposalAdmissionRequest=body;captionProposalBusy=true;$('caption-proposal-submit').disabled=true;
  let acknowledged=false;
  try { await api('caption-proposals',body);acknowledged=true;if(captionProposalAdmissionRequest===body)captionProposalAdmissionRequest=null;captionProposalStatus('Caption requested. Current annotations remain unchanged.');await refreshCaptionProposals(); }
  catch(error) {if(!acknowledged && !previous && error.status>=400 && error.status<500 && captionProposalPendingRequest===body && captionProposalStore(null))captionProposalPendingRequest=null;captionProposalStatus(captionProposalStorageError || error.message+' Refresh requests to reconcile. An explicit repeat of this unchanged request uses the same ID; no automatic retry.');}
  finally {if(captionProposalAdmissionRequest===body)captionProposalAdmissionRequest=null;captionProposalBusy=false;$('caption-proposal-submit').disabled=!!captionProposalStorageError;}
});
action('caption-proposal-refresh',refreshCaptionProposals);
window.addEventListener('pagehide',()=>{captionProposalPaused=true;++captionProposalEpoch;++captionProposalModelEpoch;clearTimeout(captionProposalTimer);});
window.addEventListener('pageshow',()=>{if(captionProposalPaused){captionProposalPaused=false;if(captionProposalSyncRecovery(true))refreshCaptionProposals().catch(error=>captionProposalStatus(error.message));}});
