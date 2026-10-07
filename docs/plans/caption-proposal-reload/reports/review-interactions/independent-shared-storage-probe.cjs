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
async function replaced(){
 const s=storage();s.data.set(key,JSON.stringify(body));const a=page(s);a.listeners.pagehide();
 const b=page(s);const first=b.refresh();b.take('caption-proposals').resolve({jobs:[persisted(body.request_id)]});await first;
 b.intent({...body,instruction:'New document pending ID2'});const admission=b.submit(),post=b.take('caption-proposals',true),second=JSON.parse(JSON.stringify(post.body));post.reject(Error('ID2 acknowledgement lost'));await admission;b.listeners.pagehide();
 assert.notEqual(second.request_id,body.request_id);assert.equal(JSON.parse(s.data.get(key)).request_id,second.request_id);
 return {s,a,second};
}
(async()=>{
 const removal=await replaced();removal.a.listeners.pageshow();removal.a.take('caption-proposals').resolve({jobs:[persisted(body.request_id)]});await flush();
 trace.push({case:'stale_remove',old_memory_id:body.request_id,newer_pending_id:removal.second.request_id,entry_after_old_GET:removal.s.data.get(key)??null});
 assert.equal(removal.s.data.has(key),false,'Regression probe expects reproduced stale removal');
 const c=page(removal.s);c.run("crypto.randomUUID=()=> '2'.repeat(32)");c.intent({...body,instruction:'Changed ID3 after lost ID2'});const third=c.submit(),thirdPost=c.take('caption-proposals',true);
 trace.push({case:'changed_after_corrupted_recovery',changed_POST_id:thirdPost.body.request_id,lost_ID2:removal.second.request_id});assert.notEqual(thirdPost.body.request_id,removal.second.request_id);thirdPost.reject(Error('Probe cleanup'));await third;
 const overwrite=await replaced();overwrite.a.listeners.pageshow();const held=overwrite.a.take('caption-proposals');overwrite.a.intent(body);const repeat=overwrite.a.submit(),repeatPost=overwrite.a.take('caption-proposals',true);
 trace.push({case:'stale_overwrite',newer_pending_id:overwrite.second.request_id,entry_after_old_explicit_repeat:JSON.parse(overwrite.s.data.get(key)).request_id});assert.equal(JSON.parse(overwrite.s.data.get(key)).request_id,body.request_id);
 repeatPost.reject(Error('Probe cleanup'));await repeat;held.resolve({jobs:[]});await flush();overwrite.a.take('caption-proposals/'+body.request_id).reject(Object.assign(Error('Not visible'),{status:404}));await flush();
 console.log(JSON.stringify({result:'REPRODUCED',trace}));
})().catch(error=>{console.error(error);process.exitCode=1;});
