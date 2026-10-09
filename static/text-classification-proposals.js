'use strict';
let textClassificationProposalJobs = [], textClassificationProposalEpoch = 0, textClassificationProposalModelEpoch = 0;
let textClassificationProposalTimer = null, textClassificationProposalPaused = false, textClassificationProposalBusy = false;
let textClassificationProposalPendingRequest = null, textClassificationProposalAdmissionRequest = null, textClassificationProposalRendered = '';
let textClassificationProposalFormEpoch = 0;
const textClassificationProposalStorageKey = 'tuldok.text-classification-proposals.admission.v1';
const textClassificationProposalStorageLimit = 64000;
let textClassificationProposalStorageBlocked = '', textClassificationProposalRecoveryId = null, textClassificationProposalStorageMalformed = false;
const textClassificationProposalDatabaseName='tuldok.text-classification-proposals.admission.v1';
const textClassificationProposalStoreName='recovery';
let textClassificationProposalDatabase=null,textClassificationProposalDatabaseOpening=null,textClassificationProposalAuthorityReady=false;
let textClassificationProposalAdmissionPreparing=false;
let textClassificationProposalRecoveryBody=null;
const textClassificationProposalActive = job => ['preparing','generating','stopping'].includes(job.status);
function textClassificationProposalStatus(message) { $('text-classification-proposal-status').textContent = message;syncTextClassificationProposalRecovery(); }
function syncTextClassificationProposalRecovery() {
  const body=textClassificationProposalPendingRequest,evidence=$('text-classification-proposal-pending-evidence');
  evidence.hidden=!body;evidence.textContent=body?JSON.stringify(body,null,2):'';
  if(body||textClassificationProposalStorageBlocked)$('text-classification-proposal-panel').hidden=false;
}
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
function validateTextClassificationProposalGateway(value) {
  if(typeof value!=='string' || Array.from(value).length>2048 || /[\uD800-\uDFFF]/u.test(value))
    throw Error('Classification gateway URL must have 1–2048 Unicode code points and no unpaired surrogates.');
  // Python str.strip includes NEL and information separators, but not a BOM.
  // Inspect a stripped copy; the original spelling stays in admission evidence.
  const inspected=value.replace(/^[\u0009-\u000D\u001C-\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]+|[\u0009-\u000D\u001C-\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]+$/gu,'');
  const authority=/^https?:\/\/([^/?#]+)/i.exec(inspected)?.[1];
  if(!authority || /[@\\]/u.test(authority) || /[\u0000-\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]/u.test(inspected))
    throw Error('Use an HTTP or HTTPS classification gateway with an explicit authority and no credentials or internal whitespace.');
  // Match urlsplit's NFKC authority guard before WHATWG host repair.
  if(/[/?#@:]/u.test(authority.replace(/[@:#?]/gu,'').normalize('NFKC')))
    throw Error('Use a classification hostname without characters that normalize to URL delimiters.');
  let url;
  try { url=new URL(inspected); } catch { throw Error('Enter a valid classification gateway URL.'); }
  if(!['http:','https:'].includes(url.protocol) || !url.hostname || url.username || url.password || url.search || url.hash || url.port==='0')
    throw Error('Use a classification gateway URL without credentials, query or fragment.');
}
function validateTextClassificationProposalBody(body) {
  const mode=body?.protocol==='pumas_typed_v1';
  const keys=['request_id','source_id','revision','source_revision','server_url','model','instruction','seed','labels',...(mode?['protocol','profile']:[])];
  if(!body || typeof body!=='object' || Array.isArray(body) || Object.keys(body).length!==keys.length || keys.some(key=>!Object.hasOwn(body,key)) ||
     typeof body.request_id!=='string' || body.request_id.length!==32 || !/^[a-f0-9]{32}$/.test(body.request_id) || typeof body.source_id!=='string' || body.source_id.length!==32 || !/^[a-f0-9]{32}$/.test(body.source_id) ||
     !['revision','source_revision'].every(key=>Number.isSafeInteger(body[key]) && body[key]>0) ||
     (mode?body.seed!==null || !(body.profile===null || typeof body.profile==='string' && /^[A-Za-z0-9_.-]{1,128}$/.test(body.profile)):!Number.isInteger(body.seed) || body.seed<0 || body.seed>4294967295))
    throw Error('Invalid classification recovery identity or revision evidence.');
  const validText=(value,max)=>typeof value==='string' && /[^\u0009-\u000D\u001C-\u0020\u0085\u00A0\u1680\u2000-\u200A\u2028\u2029\u202F\u205F\u3000]/u.test(value) && Array.from(value).length<=max && !/[\uD800-\uDFFF]/u.test(value);
  if(!validText(body.instruction,2000) || !validText(body.model,mode?256:200) || /[\u0000-\u001F]/u.test(body.model))
    throw Error('Invalid bounded classification recovery settings.');
  validateTextClassificationProposalGateway(body.server_url);
  if(mode && (new TextEncoder().encode(body.model).length>256 || body.model!==body.model.trim() || /[\u0000-\u001F\u007F]/u.test(body.model)))throw Error('Invalid exact typed serving alias.');
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
  try { const parsed=JSON.parse(raw),id=parsed?.body?.request_id;return JSON.stringify(parsed)===raw && typeof id==='string' && id.length===32 && /^[a-f0-9]{32}$/.test(id)?id:null; } catch { return null; }
}
function textClassificationProposalMirror() {
  let raw;
  try {raw=localStorage.getItem(textClassificationProposalStorageKey);} catch {throw Error('Classification recovery storage cannot be read. Requests are blocked; restore storage access and refresh requests.');}
  if(raw===null)return {raw,body:null};
  try {return {raw,body:textClassificationProposalStored(raw)};} catch {return {raw,body:null};}
}
function textClassificationProposalBlocker(raw) {
  return {schema_version:1,raw:raw.length<=textClassificationProposalStorageLimit?raw:null,length:raw.length,recovery_id:textClassificationProposalStoredId(raw)};
}
function textClassificationProposalValidBlocker(value) {
  return value && !Array.isArray(value) && value.schema_version===1 && Object.keys(value).length===4 && Number.isSafeInteger(value.length) && value.length>=0 &&
    (value.raw===null?value.length>textClassificationProposalStorageLimit:typeof value.raw==='string' && value.raw.length===value.length && value.length<=textClassificationProposalStorageLimit) &&
    (value.raw===null?value.recovery_id===null:value.recovery_id===textClassificationProposalStoredId(value.raw));
}
function textClassificationProposalAddBlocker(values,store,raw) {
  const candidate=textClassificationProposalBlocker(raw),entries=values.legacy_blocker||[];
  if(!entries.some(entry=>JSON.stringify(entry)===JSON.stringify(candidate))) {
    // Bound retained conflicting frames. Overflow is an opaque, non-clearable
    // blocker; the originating mirror bytes are left intact.
    if(entries.length<16)entries.push(candidate);
    else if(entries.length===16)entries.push(textClassificationProposalBlocker(' '.repeat(textClassificationProposalStorageLimit+1)));
    values.legacy_blocker=entries;store.put(entries,'legacy_blocker');
  }
}
async function textClassificationProposalOpenDatabase() {
  if(textClassificationProposalDatabase)return textClassificationProposalDatabase;
  if(textClassificationProposalDatabaseOpening)return textClassificationProposalDatabaseOpening;
  textClassificationProposalDatabaseOpening=new Promise((resolve,reject)=>{
    let request,settled=false;
    const failed=()=>{if(!settled){settled=true;reject(Error('Classification IndexedDB authority cannot be opened. Requests are blocked; restore access and refresh requests.'));}};
    try {
      if(typeof indexedDB==='undefined')throw Error('IndexedDB unavailable');
      request=indexedDB.open(textClassificationProposalDatabaseName,1);
      request.onupgradeneeded=()=>{if(!request.result.objectStoreNames.contains(textClassificationProposalStoreName))request.result.createObjectStore(textClassificationProposalStoreName);};
      request.onerror=failed;request.onblocked=failed;
      request.onsuccess=()=>{
        if(settled){request.result.close();return;}
        settled=true;textClassificationProposalDatabase=request.result;
        textClassificationProposalDatabase.onversionchange=()=>{textClassificationProposalDatabase.close();textClassificationProposalDatabase=null;textClassificationProposalAuthorityReady=false;};
        resolve(textClassificationProposalDatabase);
      };
    } catch {failed();}
  });
  try {return await textClassificationProposalDatabaseOpening;} finally {textClassificationProposalDatabaseOpening=null;}
}
async function textClassificationProposalAuthorityTransaction(fn) {
  const database=await textClassificationProposalOpenDatabase();
  return new Promise((resolve,reject)=>{
    let transaction,result,failure,remaining=4;const values={};
    const failed=()=>reject(failure||Error('Classification IndexedDB authority transaction failed. Requests are blocked; refresh before an explicit unchanged repeat.'));
    try {
      transaction=database.transaction(textClassificationProposalStoreName,'readwrite',{durability:'strict'});
      transaction.oncomplete=()=>failure?failed():resolve(result);transaction.onabort=failed;transaction.onerror=event=>{
        event.preventDefault();failure=failure||Error('Classification IndexedDB authority mutation failed. Requests remain blocked.');
        try {transaction.abort();} catch {failed();}
      };
      const store=transaction.objectStore(textClassificationProposalStoreName);
      for(const key of ['pending','initialized','legacy_blocker','attempt']) {
        const request=store.get(key);
        request.onerror=event=>{event.preventDefault();failure=Error('Classification IndexedDB authority cannot be read. Requests remain blocked.');transaction.abort();};
        request.onsuccess=()=>{
          values[key]=request.result;
          if(--remaining===0)try {result=fn(values,store);} catch(error) {failure=error;transaction.abort();}
        };
      }
    } catch(error) {failure=error;if(transaction)try {transaction.abort();} catch {failed();} else failed();}
  });
}
function textClassificationProposalObserveAuthority(values,store,mirror,knownReceiptRaw) {
  const initialized=values.initialized;
  if(initialized!==undefined && (!initialized || Array.isArray(initialized) || initialized.schema_version!==1 || Object.keys(initialized).length!==2 || !(initialized.resolved_raw===null || (typeof initialized.resolved_raw==='string' && initialized.resolved_raw.length<=textClassificationProposalStorageLimit && textClassificationProposalStoredId(initialized.resolved_raw)!==null))))
    throw Error('Classification IndexedDB initialization evidence is malformed. Requests remain blocked.');
  if(values.legacy_blocker!==undefined && (!Array.isArray(values.legacy_blocker) || !values.legacy_blocker.length || values.legacy_blocker.length>17 || values.legacy_blocker.some(entry=>!textClassificationProposalValidBlocker(entry))))throw Error('Classification IndexedDB blocker evidence is malformed. Requests remain blocked.');
  if(initialized===undefined) {
    store.put({schema_version:1,resolved_raw:null},'initialized');
    if(values.pending===undefined && values.legacy_blocker===undefined && mirror.raw!==null) {
      if(mirror.body){store.put(mirror.raw,'pending');values.pending=mirror.raw;}
      else textClassificationProposalAddBlocker(values,store,mirror.raw);
    }
  }
  const retired=mirror.raw!==null && initialized?.resolved_raw===mirror.raw;
  if(mirror.raw!==null && mirror.raw!==values.pending && !retired && (values.pending!==undefined || initialized!==undefined))textClassificationProposalAddBlocker(values,store,mirror.raw);
  let body=null;
  if(values.pending!==undefined)try {body=textClassificationProposalStored(values.pending);} catch {throw Error('Classification IndexedDB pending evidence is malformed. Requests remain blocked; it was not discarded.');}
  // This generation is durable evidence of every explicitly requested attempt,
  // including retries in other pages. Legacy pending frames have unknown history.
  const attempt=values.attempt;
  if(attempt!==undefined && (!attempt || Array.isArray(attempt) || Object.keys(attempt).length!==3 || !['schema_version','raw','generation'].every(key=>Object.hasOwn(attempt,key)) || attempt.schema_version!==1 ||
     typeof attempt.raw!=='string' || attempt.raw!==values.pending || !body ||
     ((!Number.isSafeInteger(attempt.generation) || attempt.generation<1) && knownReceiptRaw!==values.pending)))
    throw Error('Classification admission attempt evidence is malformed or does not match its pending request. Requests remain blocked.');
  return {raw:values.pending??null,body,blockers:values.legacy_blocker||[],retired,resolvedRaw:initialized?.resolved_raw??null,attemptGeneration:attempt?.generation??null};
}
function textClassificationProposalUseAuthority(state,mirror) {
  textClassificationProposalAuthorityReady=true;
  if(state.blockers.length) {
    textClassificationProposalStorageMalformed=true;
    if(!textClassificationProposalPendingRequest && state.body)textClassificationProposalPendingRequest=state.body;
    const blocker=state.blockers.find(entry=>entry.recovery_id);
    textClassificationProposalRecoveryId=blocker?.recovery_id||textClassificationProposalPendingRequest?.request_id||null;
    textClassificationProposalRecoveryBody=null;
    if(blocker?.raw)try {textClassificationProposalRecoveryBody=textClassificationProposalStored(blocker.raw);} catch {}
    textClassificationProposalStorageBlocked='Classification IndexedDB authority retains unresolved legacy recovery evidence. Requests remain blocked until an exact admission receipt reconciles it; it was not discarded.';
    throw Error(textClassificationProposalStorageBlocked);
  }
  if(textClassificationProposalPendingRequest && JSON.stringify({schema_version:1,body:textClassificationProposalPendingRequest})===state.resolvedRaw)textClassificationProposalPendingRequest=null;
  if(state.body) {
    if(textClassificationProposalPendingRequest && JSON.stringify(textClassificationProposalPendingRequest)!==JSON.stringify(state.body))throw Error('Another classification admission occupies IndexedDB authority. The earlier local intent is retained; requests remain blocked.');
    if(!textClassificationProposalPendingRequest)textClassificationProposalPendingRequest=state.body;
    textClassificationProposalRecoveryId=state.body.request_id;
    try {if(mirror.raw!==state.raw)localStorage.setItem(textClassificationProposalStorageKey,state.raw);} catch {throw Error('Classification recovery storage cannot mirror IndexedDB authority. Requests remain blocked.');}
  } else if(state.retired) {
    try {localStorage.removeItem(textClassificationProposalStorageKey);} catch {throw Error('Classification recovery storage could not clear a retired admission. Requests remain blocked.');}
  }
  textClassificationProposalStorageMalformed=false;textClassificationProposalStorageBlocked='';
  return state;
}
async function textClassificationProposalLoadAuthority() {
  try {
    const mirror=textClassificationProposalMirror();
    const state=await textClassificationProposalAuthorityTransaction((values,store)=>textClassificationProposalObserveAuthority(values,store,mirror));
    return textClassificationProposalUseAuthority(state,mirror);
  } catch(error) {textClassificationProposalStorageBlocked=error.message;throw error;}
  finally {syncTextClassificationProposalRecovery();$('text-classification-proposal-submit').disabled=textClassificationProposalBusy||!textClassificationProposalAuthorityReady;}
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
    job.config?.requested_server_url===body.server_url && job.config.requested_model===body.model && job.config.instruction===body.instruction && job.config.seed===body.seed && (job.config.protocol||null)===(body.protocol||null) && (job.config.profile||null)===(body.profile||null) && JSON.stringify(job.config.labels)===JSON.stringify(body.labels);
}
async function textClassificationProposalStorageLock(fn) {
  if(typeof navigator==='undefined' || !navigator.locks?.request) {
    textClassificationProposalStorageBlocked='This browser lacks Web Locks. Classification requests are blocked because admission recovery cannot be coordinated across pages.';
    throw Error(textClassificationProposalStorageBlocked);
  }
  return navigator.locks.request(textClassificationProposalStorageKey,{mode:'exclusive'},fn);
}
async function textClassificationProposalClearStorage(id, body, refusalGeneration) {
  return textClassificationProposalStorageLock(async()=>{
    try {
      const mirror=textClassificationProposalMirror();
      const state=await textClassificationProposalAuthorityTransaction((values,store)=>{
        // A matching admission receipt can retire its own corrupted counter.
        // This exception never supplies a generation for POST or refusal CAS.
        let knownReceiptRaw;
        if(refusalGeneration===undefined && body && values.pending===JSON.stringify({schema_version:1,body})) {
          try {if(textClassificationProposalStored(values.pending).request_id===id)knownReceiptRaw=values.pending;} catch {}
        }
        const observed=textClassificationProposalObserveAuthority(values,store,mirror,knownReceiptRaw);
        const raw=values.pending,blockers=values.legacy_blocker||[];
        const matchesPending=raw!==undefined && textClassificationProposalStoredId(raw)===id && (!body || raw===JSON.stringify({schema_version:1,body}));
        // A refusal only settles the captured attempt. Another page's committed
        // retry makes it stale even when the admission ID/body is identical.
        if(refusalGeneration!==undefined && (!Number.isSafeInteger(refusalGeneration) || refusalGeneration<1 || !body || !matchesPending || values.attempt?.generation!==refusalGeneration))
          return {...observed,retirementDenied:true};
        const matchesBlocker=entry=>entry.recovery_id===id && (!body || entry.raw===JSON.stringify({schema_version:1,body}));
        if(matchesPending) {
          store.delete('pending');values.pending=undefined;
          store.delete('attempt');values.attempt=undefined;
          values.initialized={schema_version:1,resolved_raw:raw};store.put(values.initialized,'initialized');
        }
        if(blockers.some(matchesBlocker)) {
          const resolved=blockers.find(matchesBlocker);values.legacy_blocker=blockers.filter(entry=>!matchesBlocker(entry));
          if(values.legacy_blocker.length)store.put(values.legacy_blocker,'legacy_blocker');else {store.delete('legacy_blocker');values.legacy_blocker=undefined;}
          values.initialized={schema_version:1,resolved_raw:resolved.raw};store.put(values.initialized,'initialized');
        }
        return textClassificationProposalObserveAuthority(values,store,{raw:null,body:null});
      });
      if(state.retirementDenied)throw Error('A later classification attempt retains this admission. The earlier refusal did not clear its request ID or exact intent.');
      if(mirror.raw!==null) {
        const mirrorId=textClassificationProposalStoredId(mirror.raw);
        if(mirrorId!==id || (body && mirror.raw!==JSON.stringify({schema_version:1,body}))) {
          textClassificationProposalStorageBlocked='Classification recovery mirror changed. This receipt cannot erase another admission.';return false;
        }
        try {localStorage.removeItem(textClassificationProposalStorageKey);} catch {throw Error('Classification recovery storage could not be cleared after an authoritative receipt. Requests remain blocked; refresh to reconcile it again.');}
      }
      if(textClassificationProposalPendingRequest?.request_id===id)textClassificationProposalPendingRequest=null;
      textClassificationProposalRecoveryId=null;textClassificationProposalStorageMalformed=false;
      textClassificationProposalUseAuthority(state,{raw:null,body:null});
      if(state.body){textClassificationProposalStorageBlocked='Another classification admission remains in IndexedDB authority. This older receipt did not erase it.';return false;}
      return true;
    } catch(error) {textClassificationProposalStorageBlocked=error.message;return false;}
  });
}
async function textClassificationProposalClaim(intent) {
  return textClassificationProposalStorageLock(async()=>{
    if(textClassificationProposalPaused)throw Error('The page was hidden before admission. No request was sent.');
    await textClassificationProposalLoadAuthority();
    const previous=textClassificationProposalPendingRequest;
    if(previous && JSON.stringify({...previous,request_id:undefined})!==JSON.stringify(intent))throw Error('An earlier request has an unknown acknowledgement. Refresh requests before changing its intent.');
    const captured=previous || {...intent,request_id:crypto.randomUUID().replaceAll('-','')};
    validateTextClassificationProposalBody(captured);
    const mirror=textClassificationProposalMirror();
    let result;
    try {result=await textClassificationProposalAuthorityTransaction((values,store)=>{
      const state=textClassificationProposalObserveAuthority(values,store,mirror);
      if(state.blockers.length)return {state,previous:state.body||previous,body:null};
      if(state.body && JSON.stringify({...state.body,request_id:undefined})!==JSON.stringify(intent))return {state,previous:state.body,body:null};
      const body=state.body?(previous && JSON.stringify(previous)===JSON.stringify(state.body)?previous:state.body):captured;
      const raw=JSON.stringify({schema_version:1,body});
      textClassificationProposalPendingRequest=body;textClassificationProposalRecoveryId=body.request_id;
      const generation=(state.attemptGeneration??0)+1;
      if(!Number.isSafeInteger(generation))throw Error('Classification admission attempt generation is exhausted. Requests remain blocked; the evidence was retained.');
      if(state.raw!==raw)store.put(raw,'pending');
      store.put({schema_version:1,raw,generation},'attempt');
      return {state:{...state,raw,body,attemptGeneration:generation},previous:state.body||previous,body,generation};
    });} catch(error) {textClassificationProposalStorageBlocked=error.message;throw error;}
    // A request-success event is not a commit. Mirror only committed authority,
    // so a transaction abort cannot leave an unresolvable fresh legacy hint.
    if(result.body)try {localStorage.setItem(textClassificationProposalStorageKey,result.state.raw);} catch {
      textClassificationProposalStorageBlocked='Classification recovery storage could not mirror the committed exact request. Inference is blocked; restore storage and explicitly repeat this unchanged request.';
      throw Error(textClassificationProposalStorageBlocked);
    }
    textClassificationProposalUseAuthority(result.state,result.body?{raw:result.state.raw,body:result.state.body}:mirror);
    if(!result.body)throw Error('An earlier request has an unknown acknowledgement in IndexedDB authority. Refresh requests before changing its intent.');
    return result;
  });
}
// Storage is already scoped to the page's origin. Restore before submit listeners
// or any asynchronous list fetch can authorize a new admission identity.
$('text-classification-proposal-submit').disabled=true;
textClassificationProposalRestoreStorage();
syncTextClassificationProposalRecovery();
textClassificationProposalLoadAuthority().catch(error=>textClassificationProposalStatus(error.message));
if(textClassificationProposalStorageBlocked)textClassificationProposalStatus(textClassificationProposalStorageBlocked);
function textClassificationProposalConfig() {
  return {server_url:$('text-classification-proposal-url').value,model:$('text-classification-proposal-model').value,
    instruction:$('text-classification-proposal-guidance').value,seed:$('text-classification-proposal-protocol').value==='pumas_typed_v1'?null:Number($('text-classification-proposal-seed').value),labels:textClassificationProposalLabels(),
    ...(typeof pumasTypedSettings==='function'?pumasTypedSettings('text-classification-proposal'):{})};
}
function textClassificationProposalsShown(record) {
  ++textClassificationProposalEpoch; clearTimeout(textClassificationProposalTimer); textClassificationProposalRendered = '';
  $('text-classification-proposal-panel').hidden = record.kind !== 'text' && !textClassificationProposalPendingRequest && !textClassificationProposalStorageBlocked;
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
  const summary=api('text-classification-proposals');
  await textClassificationProposalLoadAuthority().catch(error=>textClassificationProposalStatus(error.message));
  const recoveryId=(textClassificationProposalStorageMalformed?textClassificationProposalRecoveryId:null)||textClassificationProposalPendingRequest?.request_id||textClassificationProposalRecoveryId;
  const pending=textClassificationProposalPendingRequest?.request_id===recoveryId?textClassificationProposalPendingRequest:textClassificationProposalRecoveryBody?.request_id===recoveryId?textClassificationProposalRecoveryBody:null;
  const result=await summary;if(epoch!==textClassificationProposalEpoch||textClassificationProposalPaused)return;
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
  if(recovered && (!pending || ((pending===textClassificationProposalPendingRequest || pending===textClassificationProposalRecoveryBody) && textClassificationProposalAdmissionRequest!==pending && !textClassificationProposalAdmissionPreparing))) {
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
    if(typeof preferenceBusy!=='undefined' && preferenceBusy)
      throw Error('Wait for the judgment save to finish before applying a classification draft.');
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
    if(decision==='apply_draft') { invalidateRelease();if(typeof invalidateResponsePreview==='function')invalidateResponsePreview();if(typeof invalidatePreferencePreview==='function')invalidatePreferencePreview(); }
    throw Error(error.message+' Refresh requests and inspect the record before retrying; an application acknowledgement may have been lost.');
  }
  if(result.record) {
    invalidateRelease();if(typeof invalidateResponsePreview==='function')invalidateResponsePreview();if(typeof invalidatePreferencePreview==='function')invalidatePreferencePreview();
    if(!textClassificationProposalPaused && epoch===editorEpoch && responseEpoch===responseIntentEpoch() && formEpoch===textClassificationProposalFormEpoch && current?.id===record.id && !hasUnsavedEdits())showRecord(result.record);
    textClassificationProposalStatus('Classification applied as draft. Fixed selections retain their old revisions; explicitly review and reselect before export. Later edits are retained if the editor changed.');
    if(!textClassificationProposalPaused)await refresh();
  } else textClassificationProposalStatus('Classification rejected. The request evidence is retained; no annotation changed.');
  await refreshTextClassificationProposals();
}
$('text-classification-proposal-url').addEventListener('input',()=>{++textClassificationProposalModelEpoch;$('text-classification-proposal-model').replaceChildren();});
for(const id of ['url','model','guidance','seed','labels','protocol','profile']) {
  const input=$('text-classification-proposal-'+id);
  for(const event of ['input','change'])input.addEventListener(event,()=>{++textClassificationProposalFormEpoch;});
}
action('text-classification-proposal-models',async()=>{
  const epoch=++textClassificationProposalModelEpoch,url=$('text-classification-proposal-url').value,formEpoch=textClassificationProposalFormEpoch;
  const result=await api($('text-classification-proposal-protocol').value==='pumas_typed_v1'?'/api/generation/typed-models':'/api/generation/prompt-models',{server_url:url});
  if(formEpoch!==textClassificationProposalFormEpoch)return;
  if(epoch!==textClassificationProposalModelEpoch||url!==$('text-classification-proposal-url').value||textClassificationProposalPaused)return;
  ++textClassificationProposalFormEpoch;
  $('text-classification-proposal-model').replaceChildren();for(const model of result.models) {
    const option=document.createElement('option');option.value=model.id;option.textContent=model.name;$('text-classification-proposal-model').append(option);
  }
  textClassificationProposalStatus($('text-classification-proposal-protocol').value==='pumas_typed_v1'?'Listed serving aliases. Selected-model capabilities govern admission; listing does not establish classification or JSON compatibility.':'Listed served text models. Listing does not establish classification or JSON compatibility; incompatible requests fail without fallback.');
});
$('text-classification-proposal-form').addEventListener('submit',async event=>{
  event.preventDefault();if(textClassificationProposalBusy||textClassificationProposalPaused)return;
  if(current?.kind!=='text'||current.annotation!=null||hasUnsavedEdits()||$('editor').dataset.busy) {textClassificationProposalStatus('Select an existing unannotated text and save or discard edits before requesting a classification.');return;}
  let config;
  try { config=textClassificationProposalConfig(); } catch(error) {textClassificationProposalStatus(error.message);return;}
  const intent={source_id:current.id,revision:current.revision,source_revision:current.source_revision,
    ...config};
  let previous,body,generation,posted=false;
  textClassificationProposalBusy=true;textClassificationProposalAdmissionPreparing=true;$('text-classification-proposal-submit').disabled=true;
  try {
    const claimed=await textClassificationProposalClaim(intent);body=claimed.body;previous=claimed.previous;generation=claimed.generation;
    textClassificationProposalAdmissionRequest=body;
    if(textClassificationProposalPaused)throw Error('The page was hidden before transport. The stored request ID is retained for an explicit unchanged repeat; no request was sent.');
    posted=true;
    const receipt=await api('text-classification-proposals',body);
    if(!textClassificationProposalJobMatches(receipt,body))throw Error('The classification acknowledgement does not match the exact stored admission intent.');
    if(!await textClassificationProposalClearStorage(body.request_id,body))throw Error(textClassificationProposalStorageBlocked);
    textClassificationProposalStatus('Classification requested. Current annotations remain unchanged.');await refreshTextClassificationProposals();
  }
  catch(error) {
    if(posted && !previous && error.status>=400 && error.status<500 && textClassificationProposalPendingRequest===body)await textClassificationProposalClearStorage(body.request_id,body,generation);
    textClassificationProposalStatus((textClassificationProposalStorageBlocked||error.message)+' Refresh requests to reconcile. An explicit repeat of this unchanged request uses the same ID; no automatic retry.');
  }
  finally {textClassificationProposalAdmissionRequest=null;textClassificationProposalAdmissionPreparing=false;textClassificationProposalBusy=false;$('text-classification-proposal-submit').disabled=!textClassificationProposalAuthorityReady;}
});
action('text-classification-proposal-refresh',refreshTextClassificationProposals);
action('text-classification-proposal-restore',()=>{
  if(!textClassificationProposalRestoreStorage())throw Error(textClassificationProposalStorageBlocked);
  const body=textClassificationProposalPendingRequest;
  if(!body)throw Error('No unresolved classification admission is stored.');
  ++textClassificationProposalModelEpoch;++textClassificationProposalFormEpoch;
  $('text-classification-proposal-url').value=body.server_url;
  $('text-classification-proposal-protocol').value=body.protocol||'legacy';$('text-classification-proposal-profile').value=body.profile||'';
  if(typeof pumasTypedRender==='function')pumasTypedRender('text-classification-proposal');
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
