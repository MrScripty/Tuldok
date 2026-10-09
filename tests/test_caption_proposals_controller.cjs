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
  URL,sessionStorage:{data:new Map(),getItem(key){return this.data.get(key)??null;},setItem(key,value){this.data.set(key,value);},removeItem(key){this.data.delete(key);}},
  setTimeout:fn=>{timers.set(++timerId,fn);return timerId;},clearTimeout:id=>timers.delete(id),
  document:{getElementById:element,createElement:()=>new Element(),createElementNS:()=>new Element()},
  window:{addEventListener(name,fn){(listeners[name]||=[]).push(fn);}},
  fetch:(url,options)=>url.includes('/records?')?Promise.resolve(response(empty)):url.endsWith('/grounded/jobs')?Promise.resolve(response({jobs:[]})):new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}))});
const root=process.env.TULDOK_SOURCE_ROOT||path.resolve(__dirname,'..');
for(const file of ['workbench.js','caption-proposals.js'])vm.runInContext(fs.readFileSync(path.join(root,'static',file),'utf8'),context);
const run=code=>vm.runInContext(code,context),flush=()=>new Promise(resolve=>setImmediate(resolve));
const take=suffix=>{const index=requests.findIndex(r=>r.url.endsWith(suffix));assert.notEqual(index,-1,suffix);return requests.splice(index,1)[0];};
const resolve=(suffix,data)=>take(suffix).resolve(response(data));
const row={id:'a'.repeat(32),name:'Image A',kind:'image',task:'image_caption',annotation:{caption:'Earlier'},review:'human_reviewed',revision:2,source_revision:1,groups:['g'],provenance:{rights:'Authored'}};
const other={...row,id:'b'.repeat(32),name:'Image B'};
const after={...row,revision:3,annotation:{caption:'Proposed'},review:'draft'};
let job={id:'c'.repeat(32),revision:3,status:'completed',source:row,annotation:{caption:'Proposed'},config:{model:'fixture'},error:''};
context.row=row;context.other=other;context.after=after;
const button=label=>element('caption-proposal-jobs').children.flatMap(section=>section.children).find(child=>child.textContent===label);
(async()=>{
  await flush();run('showRecord(row);selected.set(row.id,row);selection(true)');resolve('/caption-proposals',{jobs:[job]});await flush();
  assert.equal(button('Apply as draft').type,'button');const pairs=run('JSON.stringify(releaseBody().items)');
  // URL changes revoke a pending catalog response.
  element('caption-proposal-url').value='http://127.0.0.1:1000';const models=element('caption-proposal-models').dispatch('click');
  element('caption-proposal-url').value='http://127.0.0.1:2000';await element('caption-proposal-url').dispatch('input');resolve('/api/generation/prompt-models',{models:[{id:'old',name:'Old'}]});await models;
  assert.equal(element('caption-proposal-model').children.length,0);
  if(process.env.CAPTION_RECOVERY_CASE!=='reject') {
    // A list and exact-ID 404 can precede admission of a held start POST.
    element('caption-proposal-model').value='fixture';element('caption-proposal-guidance').value='Held admission';element('caption-proposal-seed').value='42';
    const heldStart=element('caption-proposal-form').dispatch('submit'),heldPost=take('/caption-proposals'),heldBody=JSON.parse(heldPost.options.body);
    const early=element('caption-proposal-refresh').dispatch('click');resolve('/caption-proposals',{jobs:[job]});await flush();
    take('/caption-proposals/'+heldBody.request_id).resolve(response({error:'Not persisted yet'},false,404));await early;
    assert.equal(run('captionProposalPendingRequest?.request_id'),heldBody.request_id,'Early absence must retain the in-flight admission identity');
    heldPost.reject(Error('Lost acknowledgement after held admission'));await heldStart;
    const absentAgain=element('caption-proposal-refresh').dispatch('click');resolve('/caption-proposals',{jobs:[job]});await flush();
    take('/caption-proposals/'+heldBody.request_id).resolve(response({error:'Admission may still arrive'},false,404));await absentAgain;
    assert.equal(run('captionProposalPendingRequest?.request_id'),heldBody.request_id,'Ambiguous absence cannot authorize a new ID');
    element('caption-proposal-guidance').value='Changed intent';await element('caption-proposal-form').dispatch('submit');assert.equal(requests.length,0);
    assert.ok(element('caption-proposal-status').textContent.includes('unknown acknowledgement'));
    // A refusal of a repeat does not establish what happened to its earlier admission.
    element('caption-proposal-guidance').value='Held admission';const refusedRepeat=element('caption-proposal-form').dispatch('submit'),refusedPost=take('/caption-proposals');
    assert.deepEqual(JSON.parse(refusedPost.options.body),heldBody);
    refusedPost.resolve(response({error:'Busy; earlier admission still unresolved'},false,409));await refusedRepeat;
    assert.equal(run('captionProposalPendingRequest?.request_id'),heldBody.request_id,'A repeated-request 409 must retain the original ambiguous admission identity');
    element('caption-proposal-guidance').value='Changed after repeat refusal';await element('caption-proposal-form').dispatch('submit');assert.equal(requests.length,0);
    element('caption-proposal-guidance').value='Held admission';const retry=element('caption-proposal-form').dispatch('submit'),retryPost=take('/caption-proposals');
    assert.deepEqual(JSON.parse(retryPost.options.body),heldBody,'Explicit unchanged repeat must reuse the exact admission ID/body');
    const persistedWhilePosting=element('caption-proposal-refresh').dispatch('click');resolve('/caption-proposals',{jobs:[{...job,id:heldBody.request_id}]});await persistedWhilePosting;
    assert.equal(run('captionProposalPendingRequest?.request_id'),heldBody.request_id,'Even a persisted GET cannot revoke an in-flight POST identity');
    retryPost.resolve(response({...job,id:heldBody.request_id}));await flush();resolve('/caption-proposals',{jobs:[{...job,id:heldBody.request_id}]});await retry;
    assert.equal(run('captionProposalPendingRequest'),null);
    // A recovered explicitly cancelled attempt releases the old intent for a fresh request.
    const cancelledStart=element('caption-proposal-form').dispatch('submit'),cancelledPost=take('/caption-proposals'),cancelledBody=JSON.parse(cancelledPost.options.body);
    assert.notEqual(cancelledBody.request_id,heldBody.request_id);cancelledPost.reject(Error('Lost start acknowledgement'));await cancelledStart;
    const cancelledLookup=element('caption-proposal-refresh').dispatch('click');resolve('/caption-proposals',{jobs:[{...job,id:cancelledBody.request_id,status:'cancelled'}]});await cancelledLookup;
    assert.equal(run('captionProposalPendingRequest'),null);
    element('caption-proposal-guidance').value='New intent after cancellation';const fresh=element('caption-proposal-form').dispatch('submit'),freshPost=take('/caption-proposals'),freshBody=JSON.parse(freshPost.options.body);
    assert.notEqual(freshBody.request_id,cancelledBody.request_id);assert.equal(freshBody.instruction,'New intent after cancellation');
    freshPost.resolve(response({...job,id:freshBody.request_id}));await flush();resolve('/caption-proposals',{jobs:[{...job,id:freshBody.request_id}]});await fresh;
  }
  if(process.env.CAPTION_RECOVERY_CASE!=='reject') {
    // A first-attempt definite refusal has no older unknown admission to preserve.
    const refusedStart=element('caption-proposal-form').dispatch('submit'),refusedPost=take('/caption-proposals'),refusedBody=JSON.parse(refusedPost.options.body);
    refusedPost.resolve(response({error:'Busy before admission'},false,409));await refusedStart;assert.equal(run('captionProposalPendingRequest'),null);
    element('caption-proposal-guidance').value='New intent after definite refusal';const accepted=element('caption-proposal-form').dispatch('submit'),acceptedPost=take('/caption-proposals'),acceptedBody=JSON.parse(acceptedPost.options.body);
    assert.notEqual(acceptedBody.request_id,refusedBody.request_id);acceptedPost.resolve(response({...job,id:acceptedBody.request_id}));await flush();resolve('/caption-proposals',{jobs:[{...job,id:acceptedBody.request_id}]});await accepted;
  }
  // Two starts share one pending action; a lost start is reconciled by GET only.
  element('caption-proposal-model').value='fixture';element('caption-proposal-guidance').value='Visible pixels';element('caption-proposal-seed').value='42';
  const start=element('caption-proposal-form').dispatch('submit');await element('caption-proposal-form').dispatch('submit');
  assert.equal(requests.length,1);const request=take('/caption-proposals'),body=JSON.parse(request.options.body);request.reject(Error('Lost start acknowledgement'));await start;
  assert.equal(run('captionProposalPendingRequest.request_id'),body.request_id);
  const reconcile=element('caption-proposal-refresh').dispatch('click');resolve('/caption-proposals',{jobs:[{...job,id:body.request_id,status:'generating'}]});await reconcile;
  assert.equal(run('captionProposalPendingRequest'),null);assert.equal(requests.length,0);assert.equal(timers.size,1);
  const completed=element('caption-proposal-refresh').dispatch('click');resolve('/caption-proposals',{jobs:[job]});await completed;assert.equal(timers.size,0);
  // Application acknowledgement cannot discard newer local editor input or replace fixed pairs.
  run('releasePreview={eligible:true,preview_token:"old"}');const apply=button('Apply as draft').dispatch('click');await button('Apply as draft').dispatch('click');
  assert.equal(requests.length,1);element('caption').value='Later local edit';await element('editor').dispatch('input');
  resolve('/caption-proposals/decide/'+job.id,{record:after,job:{...job,status:'applied'},changed:true});await flush();resolve('/caption-proposals',{jobs:[{...job,status:'applied'}]});await apply;
  assert.equal(run('current.revision'),2);assert.equal(run('dirty'),true);assert.equal(element('caption').value,'Later local edit');assert.equal(run('releasePreview'),null);assert.equal(run('JSON.stringify(releaseBody().items)'),pairs);
  // Apply is blocked while there are unsaved edits.
  run('captionProposalJobs=[];captionProposalRendered="";dirty=false;showRecord(row)');resolve('/caption-proposals',{jobs:[job]});await flush();run('dirty=true');await button('Apply as draft').dispatch('click');assert.equal(requests.length,0);run('dirty=false');
  // Navigating to another image owns the editor when an earlier application finishes.
  const navigationApply=button('Apply as draft').dispatch('click');run('showRecord(other)');const heldRefresh=take('/caption-proposals');
  resolve('/caption-proposals/decide/'+job.id,{record:after,job:{...job,status:'applied'},changed:true});await flush();heldRefresh.resolve(response({jobs:[job]}));await flush();resolve('/caption-proposals',{jobs:[{...job,status:'applied'}]});await navigationApply;
  assert.equal(run('current.id'),other.id);assert.equal(run('current.annotation.caption'),'Earlier');
  // A lost application is never replayed automatically. Refresh exposes the persisted receipt.
  run('showRecord(row)');resolve('/caption-proposals',{jobs:[job]});await flush();const lost=button('Apply as draft').dispatch('click');take('/caption-proposals/decide/'+job.id).reject(Error('Lost application acknowledgement'));await lost;
  assert.equal(requests.length,0);assert.ok(element('caption-proposal-status').textContent.includes('acknowledgement'));
  const receipt=element('caption-proposal-refresh').dispatch('click');resolve('/caption-proposals',{jobs:[{...job,status:'applied',application:{revision:3}}]});await receipt;assert.equal(button('Apply as draft'),undefined);assert.ok(button('Open applied caption'));
  if(process.env.CAPTION_RECOVERY_CASE!=='start') {
    // Reject changes no record and cannot revoke an already submitted annotation save.
    run('showRecord(row)');resolve('/caption-proposals',{jobs:[job]});await flush();
    element('caption').value='Human caption saved during reject';await element('editor').dispatch('input');
    const save=element('editor').dispatch('submit'),savePost=take('/records/'+row.id),saveEpoch=run('editorEpoch');
    const reject=button('Reject caption proposal').dispatch('click');resolve('/caption-proposals/decide/'+job.id,{job:{...job,status:'rejected'}});await flush();resolve('/caption-proposals',{jobs:[{...job,status:'rejected'}]});await reject;
    assert.equal(run('editorEpoch'),saveEpoch,'Reject must not acquire annotation editor ownership');
    const humanSaved={...row,revision:3,annotation:{caption:'Human caption saved during reject'},review:'draft'};savePost.resolve(response(humanSaved));await flush();resolve('/caption-proposals',{jobs:[{...job,status:'rejected'}]});await save;
    assert.equal(run('current.revision'),3);assert.equal(run('dirty'),false);assert.equal(element('caption').value,humanSaved.annotation.caption);
    element('caption').value='Next human save';await element('editor').dispatch('input');const nextSave=element('editor').dispatch('submit'),nextPost=take('/records/'+row.id);
    assert.equal(JSON.parse(nextPost.options.body).revision,3,'Next save must use the accepted parent revision');
    nextPost.resolve(response({...humanSaved,revision:4,annotation:{caption:'Next human save'}}));await flush();resolve('/caption-proposals',{jobs:[{...job,status:'rejected'}]});await nextSave;
    assert.equal(run('current.revision'),4);assert.equal(run('dirty'),false);
    // Later actual editor input still fences an earlier annotation acknowledgement.
    run('showRecord(row)');resolve('/caption-proposals',{jobs:[job]});await flush();
    element('caption').value='Submitted caption';await element('editor').dispatch('input');const olderSave=element('editor').dispatch('submit'),olderPost=take('/records/'+row.id);
    element('caption').value='Later unsaved caption';await element('editor').dispatch('input');
    const laterReject=button('Reject caption proposal').dispatch('click');resolve('/caption-proposals/decide/'+job.id,{job:{...job,status:'rejected'}});await flush();resolve('/caption-proposals',{jobs:[{...job,status:'rejected'}]});await laterReject;
    olderPost.resolve(response(humanSaved));await olderSave;assert.equal(element('caption').value,'Later unsaved caption');assert.equal(run('dirty'),true);assert.equal(run('current.revision'),2);
    run('dirty=false;showRecord(row)');resolve('/caption-proposals',{jobs:[{...job,status:'applied'}]});await flush();
  }
  // Page exit fences late polling and model responses, and removes the poll timer.
  const pendingPoll=element('caption-proposal-refresh').dispatch('click');for(const fn of listeners.pagehide||[])fn();resolve('/caption-proposals',{jobs:[{...job,status:'generating'}]});await pendingPoll;
  assert.equal(timers.size,0);assert.equal(run('captionProposalJobs[0].status'),'applied');
  // Exact typed intent survives recovery; profile/protocol changes cannot become a retry.
  const typedBody={request_id:'d'.repeat(32),source_id:row.id,revision:2,source_revision:1,server_url:'http://127.0.0.1:39019',
    model:'controlled-vision',instruction:'Describe pixels.',seed:null,protocol:'pumas_typed_v1',profile:'vision-cpu'};
  context.typedBody=typedBody;
  assert.deepEqual(JSON.parse(run('JSON.stringify(captionProposalRecoveryBody(typedBody))')),typedBody);
  assert.throws(()=>run('captionProposalRecoveryBody({...typedBody,seed:42})'));
  assert.throws(()=>run('captionProposalRecoveryBody({...typedBody,profile:"bad/profile"})'));
  assert.notEqual(run('JSON.stringify(captionProposalIntent(typedBody))'),run('JSON.stringify(captionProposalIntent({...typedBody,profile:"other"}))'));
  for(const fn of listeners.pageshow||[])fn();resolve('/caption-proposals',{jobs:[{...job,status:'generating'}]});await flush();assert.equal(timers.size,1);
  for(const fn of listeners.pagehide||[])fn();assert.equal(timers.size,0);assert.equal(requests.length,0);
  console.log('Caption controller held admission/early 404/lost acknowledgement/exact-ID repeat, cancelled/new intent, held annotation-save/reject/subsequent save, later-input/apply ownership and polling lifecycle passed.');
  require('node:child_process').execFileSync(process.execPath,[path.join(__dirname,'test_caption_reload_controller.cjs')],{stdio:'inherit'});
})().catch(error=>{console.error(error);process.exitCode=1;});
