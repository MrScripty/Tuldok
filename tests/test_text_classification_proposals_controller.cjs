'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),crypto=require('node:crypto');
class Element {
  constructor(id=''){this.id=id;this.value='';this.dataset={};this.listeners={};this.children=[];this.classList={toggle(){}};}
  addEventListener(event,fn){(this.listeners[event]||=[]).push(fn);}replaceChildren(...children){this.children=children;}append(...children){this.children.push(...children);}setAttribute(){}
  matches(selector){return selector==='form'&&['editor','filters'].includes(this.id);}querySelectorAll(){return [];}
  async dispatch(event){for(const fn of this.listeners[event]||[])await fn({preventDefault(){},currentTarget:this});}
}
const elements=new Map(),element=id=>{if(!elements.has(id))elements.set(id,new Element(id));return elements.get(id);};
const listeners={},requests=[],timers=new Map();let timerId=0;
const response=(data,ok=true,status=200)=>({ok,status,json:async()=>data});
const empty={items:[],total:0,analysis:{records:0,unlabeled:0,protected_groups:0,duplicate_content_records:0,unknown_rights:0,labels:{}}};
const admissionStorage=new Map(),localStorage={getItem:key=>admissionStorage.get(key)??null,setItem:(key,value)=>admissionStorage.set(key,String(value)),removeItem:key=>admissionStorage.delete(key)};
const context=vm.createContext({console,URL,URLSearchParams,structuredClone,crypto,localStorage,navigator:{locks:{request:async(key,options,fn)=>fn()}},confirm:()=>false,location:{hash:''},history:{pushState(){}},
  setTimeout:fn=>{timers.set(++timerId,fn);return timerId;},clearTimeout:id=>timers.delete(id),
  document:{getElementById:element,createElement:()=>new Element(),createElementNS:()=>new Element()},
  window:{addEventListener(name,fn){(listeners[name]||=[]).push(fn);}},
  fetch:(url,options)=>url.includes('/records?')?Promise.resolve(response(empty)):url.endsWith('/grounded/jobs')?Promise.resolve(response({jobs:[]})):new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}))});
const root=process.env.TULDOK_SOURCE_ROOT||path.resolve(__dirname,'..');
for(const file of ['workbench.js','text-classification-proposals.js'])vm.runInContext(fs.readFileSync(path.join(root,'static',file),'utf8'),context);
const run=code=>vm.runInContext(code,context),flush=()=>new Promise(resolve=>setImmediate(resolve));
const take=suffix=>{const index=requests.findIndex(r=>r.url.endsWith(suffix));assert.notEqual(index,-1,suffix);return requests.splice(index,1)[0];};
const resolve=(suffix,data)=>take(suffix).resolve(response(data));
const row={id:'a'.repeat(32),name:'Text A',kind:'text',task:'text_classification',text:'Please schedule a meeting.',content_hash:'source-content',source_sha256:'original-source',annotation:null,review:'draft',revision:2,source_revision:1,groups:['g'],provenance:{rights:'Authored'}};
const other={...row,id:'b'.repeat(32),name:'Text B'};
const after={...row,revision:3,annotation:{label:'schedule'},review:'draft'};
let job={id:'c'.repeat(32),revision:3,status:'completed',source:row,annotation:{label:'schedule'},config:{requested_server_url:'http://127.0.0.1:2000',server_url:'http://127.0.0.1:2000',requested_model:'fixture',model:'fixture',instruction:'Visible text',seed:42,labels:['schedule','cancel']},error:''};
// Summary polling projects exact text out; explicit evidence GET retains it.
delete (job.source={...row}).text;
context.row=row;context.other=other;context.after=after;
const button=label=>element('text-classification-proposal-jobs').children.flatMap(section=>section.children).find(child=>child.textContent===label);
const admitted=(body,extra={})=>({...job,id:body.request_id,source:{...job.source,id:body.source_id,revision:body.revision,source_revision:body.source_revision},config:{...job.config,requested_server_url:body.server_url,requested_model:body.model,instruction:body.instruction,seed:body.seed,labels:body.labels},...extra});

function serializedLocks() {
  let tail=Promise.resolve();
  return {request(key,options,fn){const result=tail.then(fn);tail=result.catch(()=>{});return result;}};
}
function recoveryHarness(storage,locks=serializedLocks(),extra={}) {
  const dom=new Map(),queued=[],events={},get=id=>{if(!dom.has(id))dom.set(id,new Element(id));return dom.get(id);};
  const sandbox=vm.createContext({console,URL,URLSearchParams,structuredClone,crypto,localStorage:storage,navigator:locks?{locks}:{},location:{hash:''},history:{pushState(){}},confirm:()=>false,
    setTimeout:()=>1,clearTimeout(){},document:{getElementById:get,createElement:()=>new Element(),createElementNS:()=>new Element()},window:{addEventListener(name,fn){(events[name]||=[]).push(fn);}},
    fetch:(url,options)=>url.includes('/records?')?Promise.resolve(response(empty)):url.endsWith('/grounded/jobs')?Promise.resolve(response({jobs:[]})):new Promise((resolve,reject)=>queued.push({url,options,resolve,reject})),...extra});
  for(const file of ['workbench.js','text-classification-proposals.js'])vm.runInContext(fs.readFileSync(path.join(root,'static',file),'utf8'),sandbox);
  const execute=code=>vm.runInContext(code,sandbox);
  return {sandbox,get,queued,run:execute,posts:()=>queued.filter(r=>r.options?.method==='POST'),take(suffix,method){const index=queued.findIndex(r=>r.url.endsWith(suffix)&&(!method||r.options?.method===method));assert.notEqual(index,-1,suffix);return queued.splice(index,1)[0];},
    configure(body){sandbox.fixture=row;execute('showRecord(fixture)');for(const [key,id] of [['server_url','url'],['model','model'],['instruction','guidance'],['seed','seed'],['labels','labels']])get('text-classification-proposal-'+id).value=key==='labels'?JSON.stringify(body.labels):String(body[key]);},
    resolveLists(jobs=[]){for(const request of [...queued])if(request.url.endsWith('/text-classification-proposals')&&!request.options?.method){queued.splice(queued.indexOf(request),1);request.resolve(response({jobs}));}}};
}
function faultStorage(initial) {
  const data=new Map(initial?[['tuldok.text-classification-proposals.admission.v1',initial]]:[]),fault={get:false,set:false,remove:false};
  return {data,fault,getItem(key){if(fault.get)throw Error('Synthetic get failure');return data.get(key)??null;},setItem(key,value){if(fault.set)throw Error('Synthetic set failure');data.set(key,String(value));},removeItem(key){if(fault.remove)throw Error('Synthetic remove failure');data.delete(key);}};
}
async function freshClassificationValidationCases() {
  const key='tuldok.text-classification-proposals.admission.v1',gateway='http://127.0.0.1:2000/',valid={source_id:row.id,revision:row.revision,source_revision:row.source_revision,server_url:gateway,model:'fixture',instruction:'🧪'.repeat(2000),seed:42,labels:['offered']};
  const ascii2048=gateway+'a'.repeat(2048-Array.from(gateway).length),astral2048=gateway+'🧪'.repeat(2048-Array.from(gateway).length);
  async function corrected(name,field,bad,good) {
    const storage=faultStorage(),page=recoveryHarness(storage);page.configure(valid);page.resolveLists();await flush();page.get('text-classification-proposal-'+field).value=bad;
    await page.get('text-classification-proposal-form').dispatch('submit');assert.equal(page.posts().length,0,name);assert.equal(storage.data.size,0,name);assert.equal(page.run('textClassificationProposalPendingRequest'),null,name);assert.equal(page.run('textClassificationProposalAdmissionRequest'),null,name);assert.equal(page.run('textClassificationProposalRecoveryId'),null,name);assert.equal(page.run('textClassificationProposalStorageBlocked'),'',name);assert.equal(page.run('textClassificationProposalStorageMalformed'),false,name);assert.equal(page.run('textClassificationProposalBusy'),false,name);
    page.get('text-classification-proposal-'+field).value=good;const start=page.get('text-classification-proposal-form').dispatch('submit');await flush();assert.equal(page.posts().length,1,name+' corrected explicit submission');
    const post=page.take('/text-classification-proposals','POST'),body=JSON.parse(post.options.body);assert.deepEqual(JSON.parse(storage.getItem(key)),{schema_version:1,body});assert.equal(body.server_url,field==='url'?good:valid.server_url,name+' exact raw gateway preservation');assert.equal(Array.from(body.instruction).length,2000,name+' exact Unicode guidance boundary');
    post.resolve(response(admitted(body,{annotation:{label:body.labels[0]}})));await flush();page.resolveLists();await start;assert.equal(storage.data.size,0,name+' matching receipt clears admission');assert.equal(page.run('textClassificationProposalPendingRequest'),null,name);assert.equal(page.run('textClassificationProposalStorageBlocked'),'',name);
  }
  const baseline=[
    ['guidance 2001 Unicode code points','guidance','🧪'.repeat(2001),valid.instruction],['blank guidance','guidance','',valid.instruction],['Unicode whitespace-only guidance','guidance','\u0085\u2003',valid.instruction],['surrogate guidance','guidance','bad\ud800',valid.instruction],
    ['blank model','model','',valid.model],['201-codepoint model','model','漢'.repeat(201),valid.model],['surrogate model','model','bad\ud800',valid.model],['control-character model','model','bad\nmodel',valid.model],
    ['blank gateway','url','',gateway],['malformed gateway','url','not a URL',gateway],['non-HTTP gateway','url','file:///tmp/synthetic',gateway],['gateway credentials','url','http://synthetic:fixture@127.0.0.1:2000',gateway],['gateway query','url',gateway+'?synthetic=1',gateway],['gateway fragment','url',gateway+'#synthetic',gateway],['gateway port zero','url','http://127.0.0.1:0',gateway],
    ['negative seed','seed','-1','42'],['fractional seed','seed','42.5','42'],['seed overflow','seed','4294967296','42'],['nonnumeric seed','seed','NaN','42'],
    ['blank labels','labels','','["offered"]'],['empty labels','labels','[]','["offered"]'],['surrogate labels','labels','["\\ud800"]','["offered"]'],['duplicate labels','labels','["offered","offered"]','["offered"]']
  ];
  for(const test of baseline)await corrected(...test);
  const invalidGateways=[
    ['ASCII gateway 2049→2048',ascii2048+'a',ascii2048],['astral gateway 2049→2048',astral2048+'🧪',astral2048],['surrogate gateway',gateway+'\ud800',gateway],['leading BOM gateway','\ufeff'+gateway,gateway],['internal NEL gateway',gateway+'inside\u0085space',gateway],
    ['missing authority slashes','http:127.0.0.1:2000',gateway],['single authority slash','http:/127.0.0.1:2000',gateway],['backslash authority','http:\\\\127.0.0.1:2000',gateway],['backslash inside authority','http://127.0.0.1:2000\\other',gateway],['empty userinfo','http://@127.0.0.1:2000/',gateway],['empty password userinfo','http://:@127.0.0.1:2000/',gateway],['empty authority repaired by JS URL','http:///127.0.0.1:2000/',gateway]
  ];
  for(const [name,bad,good] of invalidGateways)await corrected(name,'url',bad,good);
  // Python edge stripping accepts NEL and information separators, and a BOM
  // inside a path remains a literal non-whitespace character. Do not mutate raw.
  for(const spelling of ['\u0085'+gateway+'\u0085','\u001c'+gateway+'\u001f',gateway+'inside\ufeffpath',gateway+'path\\segment',ascii2048,astral2048]) {
    const storage=faultStorage(),page=recoveryHarness(storage);page.configure({...valid,server_url:spelling});page.resolveLists();await flush();const start=page.get('text-classification-proposal-form').dispatch('submit');await flush();assert.equal(page.posts().length,1,'Accepted backend spelling must reach explicit transport');const post=page.take('/text-classification-proposals','POST'),body=JSON.parse(post.options.body);assert.equal(body.server_url,spelling);assert.equal(JSON.parse(storage.getItem(key)).body.server_url,spelling);post.resolve(response(admitted(body,{annotation:{label:body.labels[0]}})));await flush();page.resolveLists();await start;
  }
  // A newly stricter URL validator cannot discard a previously stored unknown
  // admission. Correcting the visible controls is never authoritative recovery.
  for(const [name,bad] of invalidGateways) {
    const pending={...valid,server_url:bad,request_id:'f'.repeat(32)},frame=JSON.stringify({schema_version:1,body:pending}),storage=faultStorage(frame),page=recoveryHarness(storage);page.configure(valid);page.resolveLists();await flush();await page.get('text-classification-proposal-form').dispatch('submit');assert.equal(page.posts().length,0,name+' stored unknown cannot be repaired by a new intent');assert.equal(storage.getItem(key),frame);assert.ok(page.run('textClassificationProposalStorageBlocked'));const lookup=page.take('/text-classification-proposals/'+pending.request_id);lookup.resolve(response({error:'Admission acknowledgement remains unknown'},false,404));await flush();assert.equal(storage.getItem(key),frame,name+' early 404 retains stored bytes');
  }
  // Accepted long raw spelling remains exact after a lost acknowledgement and
  // an explicit same-ID/body retry; no fallback or normalization creates intent.
  const storage=faultStorage(),page=recoveryHarness(storage);page.configure({...valid,server_url:astral2048});page.resolveLists();await flush();const lost=page.get('text-classification-proposal-form').dispatch('submit');await flush();const lostPost=page.take('/text-classification-proposals','POST'),original=JSON.parse(lostPost.options.body);lostPost.reject(Error('Synthetic lost admission acknowledgement'));await lost;assert.equal(JSON.parse(storage.getItem(key)).body.server_url,astral2048);
  page.get('text-classification-proposal-url').value=gateway;await page.get('text-classification-proposal-form').dispatch('submit');assert.equal(page.posts().length,0);assert.equal(page.run('textClassificationProposalPendingRequest.request_id'),original.request_id);await page.get('text-classification-proposal-restore').dispatch('click');assert.equal(page.get('text-classification-proposal-url').value,astral2048);
  const retry=page.get('text-classification-proposal-form').dispatch('submit');await flush();const retryPost=page.take('/text-classification-proposals','POST');assert.deepEqual(JSON.parse(retryPost.options.body),original);retryPost.resolve(response(admitted(original,{annotation:{label:original.labels[0]}})));await flush();page.resolveLists();await retry;
  console.log('Classification fresh correction: 23 baseline cases, 12 gateway rejection/correction cases, six exact accepted spellings, 12 stored-unknown URL cases, and long raw same-ID recovery passed.');
}
async function durableRecoveryCases() {
  const key='tuldok.text-classification-proposals.admission.v1',frozen={source_id:row.id,revision:row.revision,source_revision:row.source_revision,server_url:'http://127.0.0.1:2000/v1/',model:'fixture',instruction:'Exact\r\n guidance 👩‍💻',seed:42,labels:['schedule','cancel'],request_id:'d'.repeat(32)};
  const frame=JSON.stringify({schema_version:1,body:frozen});
  // A fresh VM models full reload: restore is synchronous despite held startup GETs.
  const storage=faultStorage(frame),reload=recoveryHarness(storage);assert.deepEqual(JSON.parse(reload.run('JSON.stringify(textClassificationProposalPendingRequest)')),frozen);
  reload.configure({...frozen,instruction:'Changed during startup'});const changed=reload.get('text-classification-proposal-form').dispatch('submit');await changed;assert.equal(reload.posts().length,0);assert.equal(storage.getItem(key),frame);
  assert.equal(reload.get('text-classification-proposal-pending-evidence').hidden,false);assert.deepEqual(JSON.parse(reload.get('text-classification-proposal-pending-evidence').textContent),frozen);
  await reload.get('text-classification-proposal-restore').dispatch('click');assert.equal(reload.posts().length,0);assert.equal(reload.get('text-classification-proposal-url').value,frozen.server_url);assert.equal(reload.get('text-classification-proposal-guidance').value,frozen.instruction);assert.equal(reload.get('text-classification-proposal-model').value,frozen.model);
  const retry=reload.get('text-classification-proposal-form').dispatch('submit');await flush();const repeat=reload.take('/text-classification-proposals','POST');
  assert.deepEqual(JSON.parse(repeat.options.body),frozen,'Full reload permits only an explicit exact same-ID/body repeat');
  repeat.resolve(response(admitted(frozen,{status:'cancelled'})));await flush();reload.resolveLists([admitted(frozen,{status:'cancelled'})]);await retry;
  assert.equal(reload.run('textClassificationProposalPendingRequest'),null);assert.equal(storage.getItem(key),null);
  reload.get('text-classification-proposal-guidance').value='Fresh after receipt';const fresh=reload.get('text-classification-proposal-form').dispatch('submit');await flush();const freshPost=reload.take('/text-classification-proposals','POST'),freshBody=JSON.parse(freshPost.options.body);assert.notEqual(freshBody.request_id,frozen.request_id);
  freshPost.resolve(response(admitted(freshBody)));await flush();reload.resolveLists();await fresh;
  // Terminal persisted recovery without a retry clears only after the matching GET.
  const terminalStore=faultStorage(frame),terminal=recoveryHarness(terminalStore);terminal.configure(frozen);terminal.resolveLists([admitted(frozen,{status:'cancelled'})]);await flush();assert.equal(terminal.run('textClassificationProposalPendingRequest'),null);assert.equal(terminalStore.getItem(key),null);
  // Read failure hides a real pending identity; no new POST is allowed.
  const unreadable=faultStorage(frame);unreadable.fault.get=true;const readFailure=recoveryHarness(unreadable);readFailure.configure({...frozen,instruction:'Unsafe read-failure intent'});await readFailure.get('text-classification-proposal-form').dispatch('submit');assert.equal(readFailure.posts().length,0);assert.ok(readFailure.run('textClassificationProposalStorageBlocked'));
  unreadable.fault.get=false;await readFailure.get('text-classification-proposal-form').dispatch('submit');assert.equal(readFailure.posts().length,0);assert.equal(readFailure.run('textClassificationProposalPendingRequest.request_id'),frozen.request_id);
  // Write failure prevents transport, keeps the exact in-memory intent, then an
  // explicit unchanged repeat may proceed only once persistence succeeds.
  const unwritable=faultStorage(),writeFailure=recoveryHarness(unwritable);writeFailure.configure(frozen);writeFailure.resolveLists();await flush();unwritable.fault.set=true;
  await writeFailure.get('text-classification-proposal-form').dispatch('submit');assert.equal(writeFailure.posts().length,0);assert.equal(unwritable.getItem(key),null);const held=JSON.parse(writeFailure.run('JSON.stringify(textClassificationProposalPendingRequest)'));
  unwritable.fault.set=false;const savedRetry=writeFailure.get('text-classification-proposal-form').dispatch('submit');await flush();const savedPost=writeFailure.take('/text-classification-proposals','POST');assert.deepEqual(JSON.parse(savedPost.options.body),held);savedPost.reject(Error('Synthetic lost admission acknowledgement'));await savedRetry;assert.deepEqual(JSON.parse(unwritable.getItem(key)).body,held);
  // Removal failure retains the durable admission through another full reload.
  const unremovable=faultStorage(),removeFailure=recoveryHarness(unremovable);removeFailure.configure(frozen);removeFailure.resolveLists();await flush();const removeStart=removeFailure.get('text-classification-proposal-form').dispatch('submit');await flush();const removePost=removeFailure.take('/text-classification-proposals','POST'),removeBody=JSON.parse(removePost.options.body);unremovable.fault.remove=true;removePost.resolve(response(admitted(removeBody)));await removeStart;assert.equal(removeFailure.run('textClassificationProposalPendingRequest.request_id'),removeBody.request_id);assert.ok(unremovable.getItem(key));
  const afterRemoveReload=recoveryHarness(unremovable);afterRemoveReload.configure({...removeBody,instruction:'Blocked until remove succeeds'});await afterRemoveReload.get('text-classification-proposal-form').dispatch('submit');assert.equal(afterRemoveReload.posts().length,0);unremovable.fault.remove=false;afterRemoveReload.resolveLists([admitted(removeBody)]);await flush();assert.equal(unremovable.getItem(key),null);
  // Malformed and oversized records are never discarded based on absence/age.
  const invalid=faultStorage('{corrupt'),corrupt=recoveryHarness(invalid);corrupt.configure(frozen);corrupt.resolveLists();await flush();await corrupt.get('text-classification-proposal-form').dispatch('submit');assert.equal(corrupt.posts().length,0);assert.equal(invalid.getItem(key),'{corrupt');
  let parseCalls=0;const oversized=faultStorage(' '.repeat(64001)),oversizedPage=recoveryHarness(oversized,serializedLocks(),{JSON:{stringify:JSON.stringify,parse(value){++parseCalls;return JSON.parse(value);}}});assert.equal(parseCalls,0,'Oversized frames must fail before JSON decoding');assert.ok(oversizedPage.run('textClassificationProposalStorageBlocked'));
  const duplicateRaw=frame.replace('"request_id":"'+frozen.request_id+'"','"request_id":"'+'e'.repeat(32)+'","request_id":"'+frozen.request_id+'"'),duplicateStore=faultStorage(duplicateRaw),duplicatePage=recoveryHarness(duplicateStore);assert.equal(duplicatePage.run('textClassificationProposalPendingRequest'),null);assert.equal(duplicatePage.run('textClassificationProposalRecoveryId'),null);duplicatePage.configure(frozen);duplicatePage.resolveLists([admitted(frozen)]);await flush();await duplicatePage.get('text-classification-proposal-form').dispatch('submit');assert.equal(duplicatePage.posts().length,0);assert.equal(duplicateStore.getItem(key),duplicateRaw,'Ambiguous duplicate IDs cannot be arbitrarily salvaged or discarded');
  const partial=faultStorage(JSON.stringify({schema_version:0,body:{request_id:frozen.request_id}})),salvage=recoveryHarness(partial);salvage.resolveLists([admitted(frozen)]);await flush();const exact=salvage.take('/text-classification-proposals/'+frozen.request_id);exact.resolve(response(admitted(frozen)));await flush();assert.equal(partial.getItem(key),null,'Malformed salvage requires an authoritative exact-ID GET');
  // Unsupported locking cannot admit inference or overwrite a pending record.
  const noLocksStore=faultStorage(),noLocks=recoveryHarness(noLocksStore,null);noLocks.configure(frozen);await noLocks.get('text-classification-proposal-form').dispatch('submit');assert.equal(noLocks.posts().length,0);assert.equal(noLocksStore.getItem(key),null);assert.ok(noLocks.run('textClassificationProposalStorageBlocked.includes("Web Locks")'));
  // Two same-origin pages loaded while storage was empty must serialize the
  // pre-POST read/write, and a late receipt cannot remove a different identity.
  const shared=faultStorage(),locks=serializedLocks(),left=recoveryHarness(shared,locks),right=recoveryHarness(shared,locks);left.configure(frozen);right.configure({...frozen,instruction:'Other page intent'});left.resolveLists();right.resolveLists();await flush();const leftSubmit=left.get('text-classification-proposal-form').dispatch('submit'),rightSubmit=right.get('text-classification-proposal-form').dispatch('submit');await flush();await rightSubmit;assert.equal(left.posts().length,1);assert.equal(right.posts().length,0);
  const original=left.take('/text-classification-proposals','POST'),originalBody=JSON.parse(original.options.body),successor={...frozen,request_id:'e'.repeat(32),instruction:'Successor persisted elsewhere'};shared.setItem(key,JSON.stringify({schema_version:1,body:successor}));original.resolve(response(admitted(originalBody)));await leftSubmit;assert.deepEqual(JSON.parse(shared.getItem(key)).body,successor,'A stale authoritative receipt must not erase another admission');
  console.log('Durable classification recovery full reload/delayed reconciliation/exact-ID repeat, authoritative terminal recovery, get/set/remove failures, corrupt/oversized records, missing locks, and two-page admission/CAS passed.');
}

(async()=>{
  await flush();run('showRecord(row);selected.set(row.id,row);selection(true)');resolve('/text-classification-proposals',{jobs:[job]});await flush();
  assert.equal(button('Apply as draft').type,'button');const pairs=run('JSON.stringify(releaseBody().items)');
  // URL changes revoke a pending catalog response.
  element('text-classification-proposal-url').value='http://127.0.0.1:1000';const models=element('text-classification-proposal-models').dispatch('click');
  element('text-classification-proposal-url').value='http://127.0.0.1:2000';await element('text-classification-proposal-url').dispatch('input');resolve('/api/generation/prompt-models',{models:[{id:'old',name:'Old'}]});await models;
  assert.equal(element('text-classification-proposal-model').children.length,0);
  element('text-classification-proposal-labels').value=JSON.stringify(job.config.labels);
  if(process.env.CLASSIFICATION_RECOVERY_CASE!=='reject') {
    // A list and exact-ID 404 can precede admission of a held start POST.
    element('text-classification-proposal-model').value='fixture';element('text-classification-proposal-guidance').value='Held admission';element('text-classification-proposal-seed').value='42';
    const heldStart=element('text-classification-proposal-form').dispatch('submit');await flush();const heldPost=take('/text-classification-proposals'),heldBody=JSON.parse(heldPost.options.body);
    assert.deepEqual(heldBody.labels,job.config.labels,'Admission freezes the exact authored label array');
    const early=element('text-classification-proposal-refresh').dispatch('click');resolve('/text-classification-proposals',{jobs:[job]});await flush();
    take('/text-classification-proposals/'+heldBody.request_id).resolve(response({error:'Not persisted yet'},false,404));await early;
    assert.equal(run('textClassificationProposalPendingRequest?.request_id'),heldBody.request_id,'Early absence must retain the in-flight admission identity');
    heldPost.reject(Error('Lost acknowledgement after held admission'));await heldStart;
    const absentAgain=element('text-classification-proposal-refresh').dispatch('click');resolve('/text-classification-proposals',{jobs:[job]});await flush();
    take('/text-classification-proposals/'+heldBody.request_id).resolve(response({error:'Admission may still arrive'},false,404));await absentAgain;
    assert.equal(run('textClassificationProposalPendingRequest?.request_id'),heldBody.request_id,'Ambiguous absence cannot authorize a new ID');
    element('text-classification-proposal-guidance').value='Changed intent';await element('text-classification-proposal-form').dispatch('submit');assert.equal(requests.length,0);
    assert.ok(element('text-classification-proposal-status').textContent.includes('unknown acknowledgement'));
    // A refusal of a repeat does not establish what happened to its earlier admission.
    element('text-classification-proposal-guidance').value='Held admission';const refusedRepeat=element('text-classification-proposal-form').dispatch('submit');await flush();const refusedPost=take('/text-classification-proposals');
    assert.deepEqual(JSON.parse(refusedPost.options.body),heldBody);
    refusedPost.resolve(response({error:'Busy; earlier admission still unresolved'},false,409));await refusedRepeat;
    assert.equal(run('textClassificationProposalPendingRequest?.request_id'),heldBody.request_id,'A repeated-request 409 must retain the original ambiguous admission identity');
    element('text-classification-proposal-guidance').value='Changed after repeat refusal';await element('text-classification-proposal-form').dispatch('submit');assert.equal(requests.length,0);
    element('text-classification-proposal-guidance').value='Held admission';const retry=element('text-classification-proposal-form').dispatch('submit');await flush();const retryPost=take('/text-classification-proposals');
    assert.deepEqual(JSON.parse(retryPost.options.body),heldBody,'Explicit unchanged repeat must reuse the exact admission ID/body');
    const persistedWhilePosting=element('text-classification-proposal-refresh').dispatch('click');resolve('/text-classification-proposals',{jobs:[admitted(heldBody)]});await persistedWhilePosting;
    assert.equal(run('textClassificationProposalPendingRequest?.request_id'),heldBody.request_id,'Even a persisted GET cannot revoke an in-flight POST identity');
    retryPost.resolve(response(admitted(heldBody)));await flush();resolve('/text-classification-proposals',{jobs:[admitted(heldBody)]});await retry;
    assert.equal(run('textClassificationProposalPendingRequest'),null);assert.equal(admissionStorage.size,0);
    // A recovered explicitly cancelled attempt releases the old intent for a fresh request.
    const cancelledStart=element('text-classification-proposal-form').dispatch('submit');await flush();const cancelledPost=take('/text-classification-proposals'),cancelledBody=JSON.parse(cancelledPost.options.body);
    assert.notEqual(cancelledBody.request_id,heldBody.request_id);cancelledPost.reject(Error('Lost start acknowledgement'));await cancelledStart;
    const cancelledLookup=element('text-classification-proposal-refresh').dispatch('click');resolve('/text-classification-proposals',{jobs:[admitted(cancelledBody,{status:'cancelled'})]});await cancelledLookup;
    assert.equal(run('textClassificationProposalPendingRequest'),null);
    element('text-classification-proposal-guidance').value='New intent after cancellation';const fresh=element('text-classification-proposal-form').dispatch('submit');await flush();const freshPost=take('/text-classification-proposals'),freshBody=JSON.parse(freshPost.options.body);
    assert.notEqual(freshBody.request_id,cancelledBody.request_id);assert.equal(freshBody.instruction,'New intent after cancellation');
    freshPost.resolve(response(admitted(freshBody)));await flush();resolve('/text-classification-proposals',{jobs:[job]});await fresh;
  }
  if(process.env.CLASSIFICATION_RECOVERY_CASE!=='reject') {
    // A first-attempt definite refusal has no older unknown admission to preserve.
    const refusedStart=element('text-classification-proposal-form').dispatch('submit');await flush();const refusedPost=take('/text-classification-proposals'),refusedBody=JSON.parse(refusedPost.options.body);
    refusedPost.resolve(response({error:'Busy before admission'},false,409));await refusedStart;assert.equal(run('textClassificationProposalPendingRequest'),null);
    element('text-classification-proposal-guidance').value='New intent after definite refusal';const accepted=element('text-classification-proposal-form').dispatch('submit');await flush();const acceptedPost=take('/text-classification-proposals'),acceptedBody=JSON.parse(acceptedPost.options.body);
    assert.notEqual(acceptedBody.request_id,refusedBody.request_id);acceptedPost.resolve(response(admitted(acceptedBody)));await flush();resolve('/text-classification-proposals',{jobs:[job]});await accepted;
  }
  // Two starts share one pending action; a lost start is reconciled by GET only.
  element('text-classification-proposal-model').value='fixture';element('text-classification-proposal-guidance').value='Visible text';element('text-classification-proposal-seed').value='42';
  const start=element('text-classification-proposal-form').dispatch('submit');await element('text-classification-proposal-form').dispatch('submit');
  assert.equal(requests.length,1);const request=take('/text-classification-proposals'),body=JSON.parse(request.options.body);request.reject(Error('Lost start acknowledgement'));await start;
  assert.equal(run('textClassificationProposalPendingRequest.request_id'),body.request_id);
  const reconcile=element('text-classification-proposal-refresh').dispatch('click');resolve('/text-classification-proposals',{jobs:[admitted(body,{status:'generating'})]});await reconcile;
  assert.equal(run('textClassificationProposalPendingRequest'),null);assert.equal(requests.length,0);assert.equal(timers.size,1);
  const completed=element('text-classification-proposal-refresh').dispatch('click');resolve('/text-classification-proposals',{jobs:[job]});await completed;assert.equal(timers.size,0);
  // Local labels are exact, never repaired or guessed, and altered choices block Apply.
  for(const invalid of ['not JSON','[]','["schedule","schedule"]','[" schedule"]','[17]','["\\ud800"]']) {
    element('text-classification-proposal-labels').value=invalid;
    await element('text-classification-proposal-form').dispatch('submit');assert.equal(requests.length,0,invalid);
  }
  const resetConfig=()=>{for(const [key,id] of [['requested_server_url','url'],['requested_model','model'],['instruction','guidance'],['seed','seed'],['labels','labels']])element('text-classification-proposal-'+id).value=key==='labels'?JSON.stringify(job.config.labels):String(job.config[key]);};
  for(const exact of ['👩‍💻\nline','\ufeffexact']) { element('text-classification-proposal-labels').value=JSON.stringify([exact]);assert.deepEqual(JSON.parse(run('JSON.stringify(textClassificationProposalLabels())')),[exact]); }
  for(const edge of ['\u0085label','label\u001c']) { element('text-classification-proposal-labels').value=JSON.stringify([edge]);await element('text-classification-proposal-form').dispatch('submit');assert.equal(requests.length,0); }
  resetConfig();
  assert.deepEqual(JSON.parse(run('JSON.stringify(textClassificationProposalLabels())')),job.config.labels);
  for(const [id,value] of [['labels','["cancel","schedule"]'],['url','http://127.0.0.1:3000'],['model','different-model'],['guidance','New guidance'],['seed','43']]) {
    element('text-classification-proposal-'+id).value=value;await button('Apply as draft').dispatch('click');
    assert.equal(requests.length,0,id+' changes must require the frozen request intent');resetConfig();
  }
  // Saved source or annotation changes fence a completed summary-backed proposal.
  for(const changes of [{revision:3},{source_revision:2},{content_hash:'changed-source'},{source_sha256:'changed-original'},{annotation:{label:'human'}}]) {
    context.changed={...row,...changes};run('current=changed');await button('Apply as draft').dispatch('click');assert.equal(requests.length,0);
  }
  run('current=row');
  const malformed=element('text-classification-proposal-refresh').dispatch('click');resolve('/text-classification-proposals',{jobs:[{...job,annotation:{label:'unknown'}}]});await malformed;
  await button('Apply as draft').dispatch('click');assert.equal(requests.length,0,'Unknown label cannot receive a fallback');
  const abstain=element('text-classification-proposal-refresh').dispatch('click');resolve('/text-classification-proposals',{jobs:[{...job,status:'abstained',annotation:null}]});await abstain;
  assert.equal(button('Apply as draft'),undefined);assert.ok(button('Reject classification proposal'));
  const rejectAbstain=button('Reject classification proposal').dispatch('click');resolve('/text-classification-proposals/decide/'+job.id,{job:{...job,status:'rejected',annotation:null}});await flush();resolve('/text-classification-proposals',{jobs:[job]});await rejectAbstain;
  assert.equal(run('current.annotation'),null,'Abstention cannot annotate the source');
  // Exact request evidence is fetched explicitly; large source text is absent in polling.
  const inspect=button('Inspect request evidence').dispatch('click');resolve('/text-classification-proposals/'+job.id,{...job,source:row,system_prompt:'fixture system',raw_response_base64:'excluded'});await inspect;
  const evidence=element('text-classification-proposal-jobs').children[0].children.find(child=>child.textContent?.startsWith('{'));
  assert.ok(evidence.textContent.includes(row.text));assert.ok(!evidence.textContent.includes('raw_response_base64'));
  // Accepted gateway spelling is frozen separately from its normalized transport URL.
  const originalURL=job.config.requested_server_url;job.config.requested_server_url=originalURL+'/v1/';resetConfig();
  const normalized=element('text-classification-proposal-refresh').dispatch('click');resolve('/text-classification-proposals',{jobs:[job]});await normalized;
  const normalizedApply=button('Apply as draft').dispatch('click'),normalizedPost=take('/text-classification-proposals/decide/'+job.id);
  normalizedPost.reject(Error('Controlled pre-commit failure'));await normalizedApply;
  assert.equal(element('text-classification-proposal-url').value,originalURL+'/v1/');
  job.config.requested_server_url=originalURL;resetConfig();
  const original=element('text-classification-proposal-refresh').dispatch('click');resolve('/text-classification-proposals',{jobs:[job]});await original;
  // Application acknowledgement cannot discard newer local editor input or replace fixed pairs.
  run('releasePreview={eligible:true,preview_token:"old"}');const apply=button('Apply as draft').dispatch('click');await button('Apply as draft').dispatch('click');
  assert.equal(requests.length,1);element('label').value='Later local edit';await element('editor').dispatch('input');
  resolve('/text-classification-proposals/decide/'+job.id,{record:after,job:{...job,status:'applied'},changed:true});await flush();resolve('/text-classification-proposals',{jobs:[{...job,status:'applied'}]});await apply;
  assert.equal(run('current.revision'),2);assert.equal(run('dirty'),true);assert.equal(element('label').value,'Later local edit');assert.equal(run('releasePreview'),null);assert.equal(run('JSON.stringify(releaseBody().items)'),pairs);
  // Apply is blocked while there are unsaved edits.
  run('textClassificationProposalJobs=[];textClassificationProposalRendered="";dirty=false;showRecord(row)');resolve('/text-classification-proposals',{jobs:[job]});await flush();run('dirty=true');await button('Apply as draft').dispatch('click');assert.equal(requests.length,0);run('dirty=false');
  // A later label-list edit cannot be overwritten by an older Apply acknowledgement.
  const changedFormApply=button('Apply as draft').dispatch('click'),changedFormPost=take('/text-classification-proposals/decide/'+job.id);
  assert.deepEqual(JSON.parse(changedFormPost.options.body).labels,job.config.labels);
  element('text-classification-proposal-labels').value='["new label"]';await element('text-classification-proposal-labels').dispatch('input');
  changedFormPost.resolve(response({record:after,job:{...job,status:'applied'},changed:true}));await flush();resolve('/text-classification-proposals',{jobs:[job]});await changedFormApply;
  assert.equal(run('current.revision'),2);assert.equal(element('text-classification-proposal-labels').value,'["new label"]');resetConfig();
  // Navigating to another text owns the editor when an earlier application finishes.
  const navigationApply=button('Apply as draft').dispatch('click');run('showRecord(other)');const heldRefresh=take('/text-classification-proposals');
  resolve('/text-classification-proposals/decide/'+job.id,{record:after,job:{...job,status:'applied'},changed:true});await flush();heldRefresh.resolve(response({jobs:[job]}));await flush();resolve('/text-classification-proposals',{jobs:[{...job,status:'applied'}]});await navigationApply;
  assert.equal(run('current.id'),other.id);assert.equal(run('current.annotation'),null);
  // A lost application is never replayed automatically. Refresh exposes the persisted receipt.
  run('showRecord(row)');resolve('/text-classification-proposals',{jobs:[job]});await flush();const lost=button('Apply as draft').dispatch('click');take('/text-classification-proposals/decide/'+job.id).reject(Error('Lost application acknowledgement'));await lost;
  assert.equal(requests.length,0);assert.ok(element('text-classification-proposal-status').textContent.includes('acknowledgement'));
  const receipt=element('text-classification-proposal-refresh').dispatch('click');resolve('/text-classification-proposals',{jobs:[{...job,status:'applied',application:{revision:3}}]});await receipt;assert.equal(button('Apply as draft'),undefined);assert.ok(button('Open applied classification'));
  if(process.env.CLASSIFICATION_RECOVERY_CASE!=='start') {
    // Reject changes no record and cannot revoke an already submitted annotation save.
    run('showRecord(row)');resolve('/text-classification-proposals',{jobs:[job]});await flush();
    element('label').value='Human label saved during reject';await element('editor').dispatch('input');
    const save=element('editor').dispatch('submit'),savePost=take('/records/'+row.id),saveEpoch=run('editorEpoch');
    const reject=button('Reject classification proposal').dispatch('click');resolve('/text-classification-proposals/decide/'+job.id,{job:{...job,status:'rejected'}});await flush();resolve('/text-classification-proposals',{jobs:[{...job,status:'rejected'}]});await reject;
    assert.equal(run('editorEpoch'),saveEpoch,'Reject must not acquire annotation editor ownership');
    const humanSaved={...row,revision:3,annotation:{label:'Human label saved during reject'},review:'draft'};savePost.resolve(response(humanSaved));await flush();resolve('/text-classification-proposals',{jobs:[{...job,status:'rejected'}]});await save;
    assert.equal(run('current.revision'),3);assert.equal(run('dirty'),false);assert.equal(element('label').value,humanSaved.annotation.label);
    element('label').value='Next human save';await element('editor').dispatch('input');const nextSave=element('editor').dispatch('submit'),nextPost=take('/records/'+row.id);
    assert.equal(JSON.parse(nextPost.options.body).revision,3,'Next save must use the accepted parent revision');
    nextPost.resolve(response({...humanSaved,revision:4,annotation:{label:'Next human save'}}));await flush();resolve('/text-classification-proposals',{jobs:[{...job,status:'rejected'}]});await nextSave;
    assert.equal(run('current.revision'),4);assert.equal(run('dirty'),false);
    // Later actual editor input still fences an earlier annotation acknowledgement.
    run('showRecord(row)');resolve('/text-classification-proposals',{jobs:[job]});await flush();
    element('label').value='Submitted label';await element('editor').dispatch('input');const olderSave=element('editor').dispatch('submit'),olderPost=take('/records/'+row.id);
    element('label').value='Later unsaved label';await element('editor').dispatch('input');
    const laterReject=button('Reject classification proposal').dispatch('click');resolve('/text-classification-proposals/decide/'+job.id,{job:{...job,status:'rejected'}});await flush();resolve('/text-classification-proposals',{jobs:[{...job,status:'rejected'}]});await laterReject;
    olderPost.resolve(response(humanSaved));await olderSave;assert.equal(element('label').value,'Later unsaved label');assert.equal(run('dirty'),true);assert.equal(run('current.revision'),2);
    run('dirty=false;showRecord(row)');resolve('/text-classification-proposals',{jobs:[{...job,status:'applied'}]});await flush();
  }
  // Cancellation remains an explicit action and clears summary polling when terminal.
  const active=element('text-classification-proposal-refresh').dispatch('click');resolve('/text-classification-proposals',{jobs:[{...job,status:'generating',annotation:null}]});await active;assert.equal(timers.size,1);
  const cancel=button('Cancel classification request').dispatch('click'),cancelPost=take('/text-classification-proposals/cancel');
  assert.deepEqual(JSON.parse(cancelPost.options.body),{job_id:job.id});cancelPost.resolve(response({...job,status:'cancelled'}));await flush();resolve('/text-classification-proposals',{jobs:[{...job,status:'cancelled'}]});await cancel;assert.equal(timers.size,0);
  const appliedAgain=element('text-classification-proposal-refresh').dispatch('click');resolve('/text-classification-proposals',{jobs:[{...job,status:'applied'}]});await appliedAgain;
  // Page exit fences late polling and model responses, and removes the poll timer.
  const pendingPoll=element('text-classification-proposal-refresh').dispatch('click');for(const fn of listeners.pagehide||[])fn();resolve('/text-classification-proposals',{jobs:[{...job,status:'generating'}]});await pendingPoll;
  assert.equal(timers.size,0);assert.equal(run('textClassificationProposalJobs[0].status'),'applied');
  for(const fn of listeners.pageshow||[])fn();resolve('/text-classification-proposals',{jobs:[{...job,status:'generating'}]});await flush();assert.equal(timers.size,1);
  for(const fn of listeners.pagehide||[])fn();assert.equal(timers.size,0);assert.equal(requests.length,0);
  await freshClassificationValidationCases();
  await durableRecoveryCases();
  console.log('Text classification controller projected summaries, exact labels/config/source fences, abstention, held admission/early 404/lost acknowledgement/exact-ID repeat, cancelled/new intent, annotation-save/reject ownership, later-input/form/apply ownership and polling lifecycle passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
