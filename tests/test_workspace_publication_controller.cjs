'use strict';
// Controlled transport/lifecycle evidence; actual custody and browser are separate.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto');
const source=fs.readFileSync(path.join(__dirname,'../static/workspace-external.js'),'utf8');
const catalog='c'.repeat(32),runId='a'.repeat(32),actorId='b'.repeat(32),sha='d'.repeat(64);
const run={id:runId,dataset_id:catalog,state:'interrupted',graph:{recipe:'external_recipe'}};
const sourceRef={kind:'external_publication_source',schema_version:1,catalog_id:catalog,run_id:runId,sha256:sha};
const ordered=v=>Array.isArray(v)?v.map(ordered):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,ordered(v[k])])):v;
const digest=v=>crypto.createHash('sha256').update(JSON.stringify(ordered(v))).digest('hex');
function status(state=null,key='retained-key',actor=actorId){
  const value={run_id:runId,original_run_state:'interrupted',verification:'saved_metadata_only',eligibility:'requires_verification',source_ref:sourceRef,original_fault:{format:'external_publication_fault_v1',code:'unavailable',message:'Original copy fault',source_sha256:sha,recorded_at:'2026-10-19T20:00:00Z'},continuation:null,continuation_request:null,limits:{max_attempts:20,wall_seconds:60,copy_bytes:4096}};
  if(state){value.continuation={run_id:runId,original_run_state:'interrupted',state,attempt_count:1,cancel_requested:false,result_ref:null};value.continuation_request={actor_id:actor,request_key:key,request_sha256:digest({actor_id:actor,operation:'runs.recover_publication',body:{run_id:runId,source_ref:sourceRef,request_key:key}})};}
  return value;
}
function deferred(){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject};}
const tick=()=>new Promise(resolve=>setTimeout(resolve,10));
function fixture(){
  let identity={catalog_id:catalog,actor_id:actorId,credential_id:'credential',kind:'owner',scopes:['inspect','approve-execution','cancel']},active=true,html='',handler=async()=>status();
  const stored=new Map(),storage={getItem:key=>stored.get(key)||null,setItem:(key,value)=>stored.set(key,value)};
  const calls=[],nodes={},timers=new Map(),history={state:{},replaceState(value){this.state=structuredClone(value);}};let next=0;
  const window={workspaceEscape:v=>String(v??'').replaceAll('<','&lt;').replaceAll('"','&quot;'),TuldokAuth:{identity:()=>identity}};
  vm.runInNewContext(source,{window,history,structuredClone,crypto:crypto.webcrypto,TextEncoder,setTimeout,clearTimeout});
  const root={querySelector(selector){return html.includes('id="'+selector.slice(1)+'"')?(nodes[selector]||=( {addEventListener(type,fn){this[type]=fn;}})):null;},querySelectorAll(){return [];}};
  const render=()=>{html=ui.html(run);ui.bind(root);};
  const ui=window.WorkspacePublication({getStorage:()=>storage,api:async(route,body,version)=>{calls.push({route,body:structuredClone(body),version});return handler(route,body,version);},render,schedule:fn=>{timers.set(++next,fn);return next;},unschedule:id=>timers.delete(id)});
  return {ui,calls,history,timers,storage,html:()=>html,setHandler:fn=>handler=fn,render,load:async()=>{await ui.load(run,()=>active);render();},click:selector=>{assert.ok(root.querySelector(selector),selector);return nodes[selector].click();},session(){identity={...identity,credential_id:'new'};ui.invalidate();render();},other(){identity={...identity,actor_id:'e'.repeat(32),credential_id:'new'};ui.invalidate();render();},agent(){identity={...identity,kind:'agent'};},navigate(){active=false;ui.invalidate();render();}};
}
(async()=>{
  const initial=fixture();await initial.load();assert.match(initial.html(),/requires_verification/);assert.match(initial.html(),/Original copy fault/);assert.match(initial.html(),/publication-recover/);assert.equal(initial.calls[0].version,2);
  const unavailable=fixture();unavailable.setHandler(async()=>({...status(),eligibility:'unavailable'}));await unavailable.load();assert.doesNotMatch(unavailable.html(),/id="publication-recover"/);
  const agent=fixture();agent.agent();await agent.load();assert.doesNotMatch(agent.html(),/id="publication-recover"|id="publication-cancel"/);
  for(const change of ['navigate','session','other']){
    const f=fixture(),held=deferred();f.setHandler(()=>held.promise);const loading=f.load();f[change]();held.resolve(status());await loading;assert.equal(f.html(),'');assert.equal(f.timers.size,0);
    const w=fixture();await w.load();const ack=deferred();w.setHandler(route=>route.endsWith('recover-publication')?ack.promise:Promise.resolve(status()));const write=w.click('#publication-recover');const pending=structuredClone(w.history.state);w[change]();ack.resolve({run_id:runId,state:'published'});await write;assert.equal(w.html(),'');assert.deepEqual(w.history.state,pending);assert.equal(w.timers.size,0);
  }
  const uncertain=fixture();await uncertain.load();uncertain.setHandler(async route=>{if(route.endsWith('recover-publication'))throw Error('lost acknowledgement');return status();});await uncertain.click('#publication-recover');const retained=structuredClone(uncertain.history.state);uncertain.history.state={};await uncertain.load();await uncertain.click('#publication-recover');const writes=uncertain.calls.filter(c=>c.route.endsWith('recover-publication'));assert.equal(writes.length,2);assert.deepEqual(writes[0].body,writes[1].body);assert.deepEqual(uncertain.history.state.publicationRequests,retained.publicationRequests);assert.match(uncertain.html(),/exact request is retained/);
  const noStore=fixture();noStore.storage.getItem=()=>{throw Error('Storage denied');};await noStore.load();assert.doesNotMatch(noStore.html(),/id="publication-recover"/);assert.match(noStore.html(),/storage is unavailable/);
  const existing=fixture();existing.setHandler(async route=>route.endsWith('recover-publication')?{run_id:runId}:status('paused'));await existing.load();await existing.click('#publication-recover');assert.equal(existing.calls.find(c=>c.route.endsWith('recover-publication')).body.request_key,'retained-key');
  const foreign=fixture();foreign.setHandler(async()=>status('recovering','external-key','e'.repeat(32)));await foreign.load();assert.doesNotMatch(foreign.html(),/id="publication-recover"/);assert.match(foreign.html(),/id="publication-cancel"/);await foreign.click('#publication-cancel');assert.equal(foreign.calls.find(c=>c.route.endsWith('cancel-publication')).body.request_key,'external-key');foreign.navigate();assert.equal(foreign.timers.size,0);
  const forged=fixture();forged.setHandler(async()=>{const value=status('paused');value.continuation_request.request_key='forged-key';return value;});await forged.load();assert.match(forged.html(),/hash differs/);assert.doesNotMatch(forged.html(),/id="publication-recover"/);
  const drift=fixture();drift.setHandler(async()=>({...status(),run_id:'f'.repeat(32)}));await drift.load();assert.match(drift.html(),/differs from this exact Run/);assert.doesNotMatch(drift.html(),/id="publication-recover"/);
  const document={format:'recovered_publication_result_v1',schema_version:1,catalog_id:catalog,run_id:runId,source_ref:sourceRef,original_run_state:'interrupted',original_fault:{code:'unavailable'},artifacts:[]};
  const resultRef={kind:'recovered_publication_result',schema_version:1,catalog_id:catalog,run_id:runId,sha256:digest(document),inventory_sha256:sha,material_sha256:sha,custody_receipt_sha256:sha};
  const published=()=>{const value=status('published');value.continuation.result_ref=resultRef;return value;};
  const inspected=fixture();inspected.setHandler(async route=>route==='publication-results'?{...document,result_ref:resultRef}:route.endsWith('/model-evidence')?{result_ref:resultRef,evidence:{state:'verified',manifest:{producer:{run_id:runId,catalog_id:catalog}},validation:'structural_and_identity_closure; numerical_acceptance_is_separate'}}:published());await inspected.load();await inspected.click('#publication-inspect');assert.match(inspected.html(),/publication-inspected/);await inspected.click('#publication-evidence');assert.match(inspected.html(),/publication-evidence-result/);
  const badResult=fixture();badResult.setHandler(async route=>route==='publication-results'?{...document,result_ref:resultRef,original_fault:{code:'changed'}}:published());await badResult.load();await badResult.click('#publication-inspect');assert.match(badResult.html(),/content differs/);assert.doesNotMatch(badResult.html(),/id="publication-inspected"/);
  const polling=fixture();polling.setHandler(async()=>status('recovering'));await polling.load();assert.equal(polling.timers.size,1);polling.setHandler(async()=>status('paused'));await polling.click('#publication-refresh');assert.equal(polling.timers.size,0);polling.navigate();assert.equal(polling.timers.size,0);
  console.log('PASS publication metadata, pinned status2, owner/actor controls, unknown-ack stable request, source/hash identity, stale reads/writes and polling cleanup');
})().catch(error=>{console.error(error);process.exitCode=1;});
