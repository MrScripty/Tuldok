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
 const outcomes=[];
 for(const [name,invalid] of [['ASCII',{instruction:'a'.repeat(2001)}],['non-BMP',{instruction:'😀'.repeat(2001)}],['mixed',{instruction:'a'.repeat(1999)+'😀😀'}],['credential URL',{server_url:'http://secret:token@localhost:8765'}]]) {
   const store=storage(),form=page(store);form.intent({...body,...invalid});await form.submit();
   assert.equal(form.requests.length,0);assert.equal(store.data.size,0);assert.equal(form.run('captionProposalStorageError'),'');assert.equal(form.run('captionProposalPendingRequest'),null);assert.equal(form.$('caption-proposal-submit').disabled,false);
   form.intent({...body,instruction:'😀'.repeat(2000)});const refresh=form.refresh();form.take('caption-proposals').resolve({jobs:[]});await refresh;
   const corrected=form.submit(),post=form.take('caption-proposals',true);assert.equal([...post.body.instruction].length,2000);assert.equal(post.body.instruction.length,4000);assert.equal(JSON.parse(store.data.get(key)).instruction,post.body.instruction);
   post.reject(Object.assign(Error('Definite refusal'),{status:409}));await corrected;
   outcomes.push({name,invalid_prevented_post_and_write:true,no_storage_latch:true,correction_after_refresh_without_reload:true,exact_2000_non_bmp_preserved:true});
 }
 const bad=storage(),invalidStored=JSON.stringify({...body,instruction:'😀'.repeat(2001)});bad.data.set(key,invalidStored);const form=page(bad);form.intent({...body,instruction:'Corrected live form'});await form.submit();assert.equal(form.requests.length,0);assert.equal(bad.data.get(key),invalidStored);assert.ok(form.run('captionProposalStorageError'));assert.equal(form.$('caption-proposal-submit').disabled,true);
 console.log(JSON.stringify({fresh_cases:outcomes,invalid_stored_evidence_retained:true,invalid_stored_guidance_failclosed:true},null,2));
})().catch(error=>{console.error(error);process.exitCode=1;});
