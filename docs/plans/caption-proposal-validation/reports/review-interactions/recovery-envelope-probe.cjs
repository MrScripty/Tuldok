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
 const longURL='http://127.0.0.1:8765'+'/'.repeat(33000);
 const s=storage(),form=page(s);form.intent({...body,server_url:longURL});
 form.run('globalThis.probe='+JSON.stringify({...body,server_url:longURL}));
 assert.doesNotThrow(()=>form.run('captionProposalRecoveryBody(probe)'));
 await form.submit();
 assert.equal(form.requests.length,0);assert.equal(s.data.size,0);
 assert.ok(form.run('captionProposalStorageError'));assert.equal(form.$('caption-proposal-submit').disabled,true);
 form.intent();await form.submit();
 assert.equal(form.requests.length,0);assert.equal(s.data.size,0);
 assert.ok(form.run('captionProposalStorageError'));assert.equal(form.$('caption-proposal-submit').disabled,true);
 console.log(JSON.stringify({source_head:'e89cf7636e3b6790179a0de3f4aeb9c433217bed',url_length:longURL.length,recovery_json_length:JSON.stringify({...body,server_url:longURL}).length,validator_accepted:true,fresh_submit_posts:0,recovery_entries:0,storage_error_latched:true,corrected_fresh_input_still_blocked:true}));
})().catch(error=>{console.error(error);process.exitCode=1;});
