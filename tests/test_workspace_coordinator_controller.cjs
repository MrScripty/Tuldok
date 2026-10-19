'use strict';
// Controlled delivery/identity/storage faults; actual process/browser evidence is separate.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto');
const catalog='c'.repeat(32),owner='a'.repeat(32),ordered=v=>Array.isArray(v)?v.map(ordered):v&&typeof v==='object'?Object.fromEntries(Object.keys(v).sort().map(k=>[k,ordered(v[k])])):v;
const digest=v=>crypto.createHash('sha256').update(JSON.stringify(ordered(v))).digest('hex');
const health=(generation=1,request=null,ready=false)=>({format:'run_coordinator_health_v1',catalog_id:catalog,generation,state:ready?'idle':'faulted',updated_at:'2026-10-19T21:00:00Z',fault:{category:'catalog_lock_timeout',at:'2026-10-19T21:00:00Z'},admission_ready:ready,recovery_request:request});
const receipt=body=>({actor_id:owner,...body,request_sha256:digest({catalog_id:catalog,operation:'runs.recover_coordinator',actor_id:owner,body}),completed_generation:2});
const deferred=()=>{let resolve;return {promise:new Promise(r=>resolve=r),resolve};};
function fixture(){
  let actor={catalog_id:catalog,actor_id:owner,credential_id:'b'.repeat(32),kind:'owner',scopes:['inspect','approve-execution']},view=true,handler=async()=>health();
  const values=new Map(),calls=[],storage={getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v)},window={workspaceEscape:s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;')};
  const context={window,crypto:crypto.webcrypto,TextEncoder,structuredClone,Set,Map,AbortController};
  for(const file of ['workspace-external.js','workspace-real.js'])vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../static',file),'utf8'),context);
  const elements=new Map(),root={querySelector(selector){if(!ui.html().includes('id="'+selector.slice(1)+'"'))return null;if(!elements.has(selector))elements.set(selector,{addEventListener:(name,fn)=>elements.get(selector)[name]=fn});return elements.get(selector);}};
  const ui=window.WorkspaceCoordinator({api:async(route,body,version,timeout,signal)=>{calls.push({route,body:structuredClone(body),version,timeout,signal});return handler(route,body);},identity:()=>actor,getStorage:()=>storage,render(){elements.clear();ui.bind(root);}});
  return {ui,calls,values,storage,html:()=>ui.html(),handler:fn=>handler=fn,async load(){view=true;await ui.load(()=>view);ui.bind(root);},click:selector=>{ui.bind(root);assert.ok(root.querySelector(selector),selector);return root.querySelector(selector).click();},navigate(){view=false;ui.invalidate();},session(){actor={...actor,credential_id:'d'.repeat(32)};ui.invalidate();},agent(){actor={...actor,kind:'agent',scopes:['inspect']};ui.invalidate();}};
}
(async()=>{
  const good=fixture();await good.load();let written;
  good.handler(async(route,body)=>{if(body)written=body;return written?health(2,receipt(written),true):health();});
  await good.click('#coordinator-recover');assert.match(good.html(),/generation 2/);assert.match(good.html(),/Saved recovery receipt confirmed/);assert.equal(good.calls.filter(c=>c.body).length,1);assert.ok(good.calls.every(c=>c.version===1));assert.doesNotMatch(good.html(),/id="coordinator-recover"/);
  const unknown=fixture();await unknown.load();unknown.handler(async(route,body)=>{if(body)throw Error('lost acknowledgement');return health();});await unknown.click('#coordinator-recover');await unknown.load();await unknown.click('#coordinator-recover');const writes=unknown.calls.filter(c=>c.body);assert.equal(writes.length,2);assert.deepEqual(writes[0].body,writes[1].body);
  for(const change of ['navigate','session']){const f=fixture();await f.load();const held=deferred();f.handler((route,body)=>body?held.promise:Promise.resolve(health()));const pending=f.click('#coordinator-recover');f[change]();assert.equal(f.calls.find(c=>c.body).signal.aborted,true);held.resolve(health(2,receipt(f.calls.find(c=>c.body).body),true));await pending;assert.doesNotMatch(f.html(),/generation 2/);assert.equal(f.calls.filter(c=>c.body).length,1);}
  const stale=fixture();await stale.load();const old=deferred();let reads=0,body;
  stale.handler(async(route,request)=>{if(request){body=request;return health(2,receipt(body),true);}if(++reads===1)return old.promise;return health(2,receipt(body),true);});
  const prior=stale.click('#coordinator-refresh');await stale.click('#coordinator-recover');old.resolve(health());await prior;assert.match(stale.html(),/generation 2/);assert.doesNotMatch(stale.html(),/id="coordinator-recover"/);
  const forged=fixture();forged.handler(async()=>{const body={expected_generation:1,request_key:'retained-recovery-0001'},value=health(2,receipt(body),false);value.recovery_request.request_key='forged-recovery-0001';return value;});await forged.load();assert.match(forged.html(),/hash differs/);assert.doesNotMatch(forged.html(),/id="coordinator-recover"/);
  const noStore=fixture();noStore.storage.getItem=()=>{throw Error('Storage unavailable');};await noStore.load();assert.doesNotMatch(noStore.html(),/id="coordinator-recover"/);
  const agent=fixture();agent.agent();await agent.load();assert.doesNotMatch(agent.html(),/id="coordinator-recover"/);
  const later=fixture(),previous={expected_generation:1,request_key:'completed-recovery-0001'};later.handler(async()=>health(2,receipt(previous),false));await later.load();later.handler(async(route,body)=>{if(body){assert.equal(body.expected_generation,2);assert.notEqual(body.request_key,previous.request_key);return health(3,{...receipt(body),completed_generation:3},true);}const written=later.calls.find(c=>c.body)?.body;return written?health(3,{...receipt(written),completed_generation:3},true):health(2,receipt(previous),false);});await later.click('#coordinator-recover');assert.match(later.html(),/generation 3/);
  const undelivered=fixture();let delivered=false,attempts=0,newBody;
  undelivered.handler(async(route,body)=>{if(body){newBody=body;if(++attempts===1)throw Error('Request delivery unknown before durable record');delivered=true;}return delivered?health(3,{...receipt(newBody),completed_generation:3},true):health(2,receipt(previous),false);});
  await undelivered.load();await undelivered.click('#coordinator-recover');await undelivered.click('#coordinator-recover');
  const retried=undelivered.calls.filter(c=>c.body);assert.equal(retried.length,2,'A pending current-generation request must reconcile against the older completed receipt');assert.deepEqual(retried[0].body,retried[1].body);assert.notEqual(retried[0].body.request_key,previous.request_key);assert.match(undelivered.html(),/generation 3/);
  const conflicting=fixture();conflicting.handler(async(route,body)=>{if(body)throw Error('Delivery unknown');return health(2,receipt(previous),false);});await conflicting.load();await conflicting.click('#coordinator-recover');
  const foreignBody={expected_generation:2,request_key:'different-pending-0001'},foreignActor='f'.repeat(32),foreign={actor_id:foreignActor,...foreignBody,completed_generation:null,request_sha256:digest({catalog_id:catalog,operation:'runs.recover_coordinator',actor_id:foreignActor,body:foreignBody})};
  conflicting.handler(async()=>health(2,foreign,false));await conflicting.click('#coordinator-refresh');await conflicting.click('#coordinator-recover');assert.equal(conflicting.calls.filter(c=>c.body).length,1);assert.match(conflicting.html(),/Saved request and current receipt differ/);
  console.log('PASS coordinator owner controls, exact generation/request identity, immutable completion, unknown-ack retention, stale read/write/session fences and storage refusal');
})().catch(error=>{console.error(error);process.exitCode=1;});
