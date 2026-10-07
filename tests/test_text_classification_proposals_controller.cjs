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
const context=vm.createContext({console,URLSearchParams,structuredClone,crypto,confirm:()=>false,location:{hash:''},history:{pushState(){}},
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
    const heldStart=element('text-classification-proposal-form').dispatch('submit'),heldPost=take('/text-classification-proposals'),heldBody=JSON.parse(heldPost.options.body);
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
    element('text-classification-proposal-guidance').value='Held admission';const refusedRepeat=element('text-classification-proposal-form').dispatch('submit'),refusedPost=take('/text-classification-proposals');
    assert.deepEqual(JSON.parse(refusedPost.options.body),heldBody);
    refusedPost.resolve(response({error:'Busy; earlier admission still unresolved'},false,409));await refusedRepeat;
    assert.equal(run('textClassificationProposalPendingRequest?.request_id'),heldBody.request_id,'A repeated-request 409 must retain the original ambiguous admission identity');
    element('text-classification-proposal-guidance').value='Changed after repeat refusal';await element('text-classification-proposal-form').dispatch('submit');assert.equal(requests.length,0);
    element('text-classification-proposal-guidance').value='Held admission';const retry=element('text-classification-proposal-form').dispatch('submit'),retryPost=take('/text-classification-proposals');
    assert.deepEqual(JSON.parse(retryPost.options.body),heldBody,'Explicit unchanged repeat must reuse the exact admission ID/body');
    const persistedWhilePosting=element('text-classification-proposal-refresh').dispatch('click');resolve('/text-classification-proposals',{jobs:[{...job,id:heldBody.request_id}]});await persistedWhilePosting;
    assert.equal(run('textClassificationProposalPendingRequest?.request_id'),heldBody.request_id,'Even a persisted GET cannot revoke an in-flight POST identity');
    retryPost.resolve(response({...job,id:heldBody.request_id}));await flush();resolve('/text-classification-proposals',{jobs:[{...job,id:heldBody.request_id}]});await retry;
    assert.equal(run('textClassificationProposalPendingRequest'),null);
    // A recovered explicitly cancelled attempt releases the old intent for a fresh request.
    const cancelledStart=element('text-classification-proposal-form').dispatch('submit'),cancelledPost=take('/text-classification-proposals'),cancelledBody=JSON.parse(cancelledPost.options.body);
    assert.notEqual(cancelledBody.request_id,heldBody.request_id);cancelledPost.reject(Error('Lost start acknowledgement'));await cancelledStart;
    const cancelledLookup=element('text-classification-proposal-refresh').dispatch('click');resolve('/text-classification-proposals',{jobs:[{...job,id:cancelledBody.request_id,status:'cancelled'}]});await cancelledLookup;
    assert.equal(run('textClassificationProposalPendingRequest'),null);
    element('text-classification-proposal-guidance').value='New intent after cancellation';const fresh=element('text-classification-proposal-form').dispatch('submit'),freshPost=take('/text-classification-proposals'),freshBody=JSON.parse(freshPost.options.body);
    assert.notEqual(freshBody.request_id,cancelledBody.request_id);assert.equal(freshBody.instruction,'New intent after cancellation');
    freshPost.resolve(response({...job,id:freshBody.request_id}));await flush();resolve('/text-classification-proposals',{jobs:[job]});await fresh;
  }
  if(process.env.CLASSIFICATION_RECOVERY_CASE!=='reject') {
    // A first-attempt definite refusal has no older unknown admission to preserve.
    const refusedStart=element('text-classification-proposal-form').dispatch('submit'),refusedPost=take('/text-classification-proposals'),refusedBody=JSON.parse(refusedPost.options.body);
    refusedPost.resolve(response({error:'Busy before admission'},false,409));await refusedStart;assert.equal(run('textClassificationProposalPendingRequest'),null);
    element('text-classification-proposal-guidance').value='New intent after definite refusal';const accepted=element('text-classification-proposal-form').dispatch('submit'),acceptedPost=take('/text-classification-proposals'),acceptedBody=JSON.parse(acceptedPost.options.body);
    assert.notEqual(acceptedBody.request_id,refusedBody.request_id);acceptedPost.resolve(response({...job,id:acceptedBody.request_id}));await flush();resolve('/text-classification-proposals',{jobs:[job]});await accepted;
  }
  // Two starts share one pending action; a lost start is reconciled by GET only.
  element('text-classification-proposal-model').value='fixture';element('text-classification-proposal-guidance').value='Visible text';element('text-classification-proposal-seed').value='42';
  const start=element('text-classification-proposal-form').dispatch('submit');await element('text-classification-proposal-form').dispatch('submit');
  assert.equal(requests.length,1);const request=take('/text-classification-proposals'),body=JSON.parse(request.options.body);request.reject(Error('Lost start acknowledgement'));await start;
  assert.equal(run('textClassificationProposalPendingRequest.request_id'),body.request_id);
  const reconcile=element('text-classification-proposal-refresh').dispatch('click');resolve('/text-classification-proposals',{jobs:[{...job,id:body.request_id,status:'generating'}]});await reconcile;
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
  console.log('Text classification controller projected summaries, exact labels/config/source fences, abstention, held admission/early 404/lost acknowledgement/exact-ID repeat, cancelled/new intent, annotation-save/reject ownership, later-input/form/apply ownership and polling lifecycle passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
