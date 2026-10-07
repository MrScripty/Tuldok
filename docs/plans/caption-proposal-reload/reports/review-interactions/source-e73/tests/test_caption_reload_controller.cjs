'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(process.env.TULDOK_SOURCE_ROOT||path.resolve(__dirname,'..'),'static/caption-proposals.js'),'utf8');
const key='tuldok.caption-proposal-recovery.v1',row={id:'a'.repeat(32),kind:'image',revision:2,source_revision:1};
const body={source_id:row.id,revision:2,source_revision:1,server_url:'http://127.0.0.1:8765',model:'fixture',instruction:'Original exact guidance',seed:42,request_id:'0'.repeat(31)+'1'};
const flush=()=>new Promise(resolve=>setImmediate(resolve));
function storage() {return {data:new Map(),fail:'',getItem(k){if(this.fail==='read')throw Error('SecurityError');return this.data.get(k)??null;},setItem(k,v){if(this.fail==='write')throw Error('QuotaExceeded');this.data.set(k,v);},removeItem(k){if(this.fail==='remove')throw Error('SecurityError');this.data.delete(k);}};}
function page(store) {
  const elements=new Map(),requests=[],listeners={};
  class Element {
    constructor(){this.value='';this.children=[];this.dataset={};this.listeners={};}
    addEventListener(e,fn){(this.listeners[e]||=[]).push(fn);}append(...v){this.children.push(...v);}replaceChildren(...v){this.children=v;}
    async dispatch(e){for(const fn of this.listeners[e]||[])await fn({preventDefault(){},currentTarget:this});}
  }
  const $=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
  const context=vm.createContext({URL,sessionStorage:store,crypto:{randomUUID:()=> '1'.repeat(32)},current:row,editorEpoch:0,
    $,document:{createElement:()=>new Element()},window:{addEventListener(e,fn){listeners[e]=fn;}},
    hasUnsavedEdits:()=>false,responseIntentEpoch:()=>0,clearTimeout(){},setTimeout:()=>1,
    action:(id,fn)=>$(id).addEventListener('click',fn),
    api:(url,request)=>new Promise((resolve,reject)=>requests.push({url,body:request,resolve,reject}))});
  vm.runInContext(source,context);const run=code=>vm.runInContext(code,context);
  function intent(value=body){for(const [id,v] of [['url',value.server_url],['model',value.model],['guidance',value.instruction],['seed',value.seed]])$('caption-proposal-'+id).value=v;}
  function take(url,post=false){const i=requests.findIndex(r=>r.url===url && (r.body!==undefined)===post);assert.notEqual(i,-1,url);return requests.splice(i,1)[0];}
  const submit=()=>$('caption-proposal-form').dispatch('submit'),refresh=()=>$('caption-proposal-refresh').dispatch('click');
  return {$,run,requests,intent,take,submit,refresh,listeners};
}
const persisted=(id,status='completed')=>({id,status,source:row,config:{model:'fixture'},annotation:{caption:'Fixture'},error:''});
(async()=>{
  if(process.env.CAPTION_RELOAD_CASE==='restore') {
    const prior=storage();prior.data.set(key,JSON.stringify(body));const restored=page(prior);
    const reconciliation=restored.refresh(),held=restored.take('caption-proposals');
    restored.intent({...body,instruction:'Changed while reload GET is held'});const changed=restored.submit();
    assert.equal(restored.requests.length,0,'A full reload must refuse a changed POST while initial reconciliation is held');await changed;
    assert.equal(restored.run('captionProposalPendingRequest?.request_id'),body.request_id);
    held.resolve({jobs:[persisted(body.request_id)]});await reconciliation;console.log('Full-reload held-reconciliation negative/positive probe passed.');return;
  }
  const store=storage();let p=page(store);p.intent();const initial=p.submit(),post=p.take('caption-proposals',true);
  assert.equal(JSON.parse(store.data.get(key)).request_id,post.body.request_id,'Exact retry evidence must commit before POST');
  const original=JSON.parse(JSON.stringify(post.body));post.reject(Error('Lost acknowledgement'));await initial;
  // A new JS document, sharing only the real tab storage, restores before held GET.
  p=page(store);assert.deepEqual(JSON.parse(p.run('JSON.stringify(captionProposalPendingRequest)')),original);
  const lookup=p.refresh(),held=p.take('caption-proposals');p.intent({...body,instruction:'Changed after reload'});await p.submit();
  assert.equal(p.requests.length,0,'Held initial reconciliation cannot permit a changed POST');
  held.resolve({jobs:[]});await flush();p.take('caption-proposals/'+original.request_id).reject(Object.assign(Error('Not visible'),{status:404}));await lookup;
  await p.submit();assert.equal(p.requests.length,0);assert.ok(store.data.has(key),'Ambiguous 404 must retain storage');
  // Explicit unchanged repeat only; refused repeats survive another full reload.
  p.intent(original);const refused=p.submit(),repeat=p.take('caption-proposals',true);
  assert.deepEqual(JSON.parse(JSON.stringify(repeat.body)),original);repeat.reject(Object.assign(Error('Busy'),{status:409}));await refused;
  p=page(store);p.intent(original);const retry=p.submit(),retryPost=p.take('caption-proposals',true);
  assert.deepEqual(JSON.parse(JSON.stringify(retryPost.body)),original);
  retryPost.resolve(persisted(original.request_id));await flush();p.take('caption-proposals').resolve({jobs:[persisted(original.request_id)]});await retry;
  assert.equal(store.data.has(key),false);assert.equal(p.run('captionProposalPendingRequest'),null);
  for(const status of ['cancelled','completed','failed','interrupted','generating']) {
    store.data.set(key,JSON.stringify(body));p=page(store);p.intent({...body,instruction:'Later intent'});
    const reconciliation=p.refresh();p.take('caption-proposals').resolve({jobs:[persisted(body.request_id,status)]});await reconciliation;
    assert.equal(store.data.has(key),false);const fresh=p.submit(),next=p.take('caption-proposals',true);
    assert.notEqual(next.body.request_id,body.request_id);assert.equal(next.body.instruction,'Later intent');
    next.resolve(persisted(next.body.request_id));await flush();p.take('caption-proposals').resolve({jobs:[persisted(next.body.request_id)]});await fresh;
  }
  // Acknowledged POST + failing GET does not become a definite start refusal.
  p=page(store);p.intent();const accepted=p.submit(),acceptedPost=p.take('caption-proposals',true);
  acceptedPost.resolve(persisted(acceptedPost.body.request_id));await flush();p.take('caption-proposals').reject(Object.assign(Error('GET denied'),{status:403}));await accepted;
  assert.ok(store.data.has(key));store.data.clear();
  for(const failure of ['read','write']) {
    const bad=storage();bad.fail=failure;p=page(bad);p.intent();await p.submit();assert.equal(p.requests.length,0,failure+' failure must prevent any POST');assert.equal(p.$('caption-proposal-submit').disabled,true);
  }
  // A failed removal retains the ID even after authoritative GET; retry clearing is safe.
  store.data.set(key,JSON.stringify(body));p=page(store);store.fail='remove';const failedClear=p.refresh();p.take('caption-proposals').resolve({jobs:[persisted(body.request_id)]});await failedClear;
  assert.equal(p.run('captionProposalPendingRequest.request_id'),body.request_id);assert.ok(store.data.has(key));p.intent();await p.submit();assert.equal(p.requests.length,0);
  store.fail='';const clear=p.refresh();p.take('caption-proposals').resolve({jobs:[persisted(body.request_id)]});await clear;assert.equal(store.data.has(key),false);
  for(const value of ['{broken',JSON.stringify({...body,credentials:'forbidden'}),'x'.repeat(32769),JSON.stringify({...body,server_url:'http://secret:token@localhost:8765'})]) {
    const bad=storage();bad.data.set(key,value);p=page(bad);p.intent();await p.submit();assert.equal(p.requests.length,0);assert.equal(bad.data.get(key),value,'Invalid recovery evidence must not be silently discarded');
  }
  const privateStore=storage();p=page(privateStore);p.intent({...body,server_url:'http://secret:token@localhost:8765'});await p.submit();assert.equal(p.requests.length,0);assert.equal(privateStore.data.size,0);
  console.log('Caption reload: durable before POST, synchronous restore/held GET, changed-intent refusal, 404/refused repeat retention, exact retry, terminal/active reconciliation, storage read/write/remove/corruption bounds and credential exclusion passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
