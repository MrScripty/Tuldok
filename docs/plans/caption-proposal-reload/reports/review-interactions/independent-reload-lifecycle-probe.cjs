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

const trace=[];
(async()=>{
 const s=storage();let p=page(s);p.intent();const start=p.submit(),post=p.take('caption-proposals',true),original=JSON.parse(JSON.stringify(post.body));
 assert.deepEqual(JSON.parse(s.data.get(key)),original);post.reject(Error('Independent lost ACK'));await start;
 p=page(s);assert.equal(p.requests.length,0,'Reload must send no automatic request');assert.deepEqual(JSON.parse(p.run('JSON.stringify(captionProposalPendingRequest)')),original);
 const lookup=p.refresh(),held=p.take('caption-proposals');p.intent({...original,instruction:'Changed while held'});await p.submit();assert.equal(p.requests.length,0,'Changed intent must remain blocked');
 p.intent(original);const explicit=p.submit(),repeat=p.take('caption-proposals',true);assert.deepEqual(JSON.parse(JSON.stringify(repeat.body)),original);
 held.resolve({jobs:[persisted(original.request_id)]});await lookup;
 assert.ok(s.data.has(key),'Persisted GET cannot remove storage while repeat POST is in flight');assert.equal(p.run('captionProposalPendingRequest.request_id'),original.request_id);
 repeat.reject(Object.assign(Error('Unresolved repeat refusal'),{status:409}));await explicit;assert.ok(s.data.has(key));trace.push({phase:'held_GET_with_explicit_repeat',same_body_and_id:true,inflight_GET_keeps_storage:true,refused_repeat_keeps_storage:true});
 p=page(s);const late=p.refresh(),lateGET=p.take('caption-proposals');p.listeners.pagehide();lateGET.resolve({jobs:[persisted(original.request_id)]});await late;
 assert.ok(s.data.has(key),'A stale pagehide GET cannot erase unresolved recovery');assert.equal(p.run('captionProposalPendingRequest.request_id'),original.request_id);
 p.listeners.pageshow();p.take('caption-proposals').resolve({jobs:[persisted(original.request_id,'cancelled')]});await flush();assert.equal(s.data.has(key),false);assert.equal(p.run('captionProposalPendingRequest'),null);assert.equal(p.requests.length,0);
 trace.push({phase:'page_lifecycle',pagehide_GET_retains_identity:true,pageshow_cancelled_reconciliation_releases:true,automatic_POSTs:0});
 const silentWrite=storage();silentWrite.setItem=()=>{};p=page(silentWrite);p.intent();await p.submit();assert.equal(p.requests.length,0);assert.equal(p.$('caption-proposal-submit').disabled,true);assert.equal(silentWrite.data.has(key),false);
 const silentRemove=storage();silentRemove.data.set(key,JSON.stringify(original));silentRemove.removeItem=()=>{};p=page(silentRemove);const attemptedClear=p.refresh();p.take('caption-proposals').resolve({jobs:[persisted(original.request_id)]});await attemptedClear;assert.ok(silentRemove.data.has(key));assert.equal(p.run('captionProposalPendingRequest.request_id'),original.request_id);await p.submit();assert.equal(p.requests.length,0);assert.equal(p.$('caption-proposal-submit').disabled,true);
 const readAfterWrite=storage();const setter=readAfterWrite.setItem;readAfterWrite.setItem=function(k,v){setter.call(this,k,v);this.fail='read';};p=page(readAfterWrite);p.intent();await p.submit();assert.equal(p.requests.length,0);assert.ok(readAfterWrite.data.has(key));assert.equal(p.$('caption-proposal-submit').disabled,true);
 trace.push({phase:'storage_readback',silent_write_blocks_POST:true,silent_remove_retains_ID_and_blocks_POST:true,read_after_write_failure_blocks_POST:true});
 console.log(JSON.stringify({result:'PASS',trace}));
})().catch(error=>{console.error(error);process.exitCode=1;});
