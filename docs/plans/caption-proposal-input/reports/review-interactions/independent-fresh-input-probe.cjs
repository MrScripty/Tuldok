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
 const trace=[],s=storage(),p=page(s);p.intent({...body,instruction:'A'.repeat(2001)});await p.submit();assert.equal(p.requests.length,0);assert.equal(s.data.size,0);assert.equal(p.run('captionProposalPendingRequest'),null);assert.equal(p.run('captionProposalStorageError'),'');assert.equal(p.$('caption-proposal-submit').disabled,false);
 const exact='e\u0301'.repeat(999)+'\u{1f600}\u{1f600}';assert.equal([...exact].length,2000);p.intent({...body,instruction:exact});const refreshed=p.refresh();p.take('caption-proposals').resolve({jobs:[]});await refreshed;
 const corrected=p.submit(),post=p.take('caption-proposals',true),request=JSON.parse(JSON.stringify(post.body));assert.equal(request.instruction,exact);assert.deepEqual(JSON.parse(s.data.get(key)),request);post.reject(Error('Independent lost ACK'));await corrected;
 trace.push({case:'correct_without_reload',invalid_fresh_POSTs:0,invalid_fresh_storage_entries:0,corrected_code_points:2000,corrected_UTF16_units:exact.length,exact_combining_and_nonBMP_text:true});
 const retained=s.data.get(key);p.intent({...body,instruction:'Changed invalid '.repeat(200)});await p.submit();assert.equal(p.requests.length,0);assert.equal(s.data.get(key),retained);assert.equal(p.run('captionProposalPendingRequest.request_id'),request.request_id);
 const absent=p.refresh();p.take('caption-proposals').resolve({jobs:[]});await flush();p.take('caption-proposals/'+request.request_id).reject(Object.assign(Error('Unknown admission'),{status:404}));await absent;assert.equal(s.data.get(key),retained);
 trace.push({case:'invalid_edit_after_unknown_ACK',original_body_retained:true,changed_POSTs:0,ambiguous_404_keeps_identity:true});
 const settingsStore=storage(),settings=page(settingsStore);settings.intent({...body,server_url:'not a URL'});await settings.submit();assert.equal(settings.requests.length,0);assert.equal(settings.run('captionProposalStorageError'),'');assert.equal(settingsStore.data.size,0);
 settings.intent({...body,seed:1.5});await settings.submit();assert.equal(settings.requests.length,0);assert.equal(settings.run('captionProposalStorageError'),'');assert.equal(settingsStore.data.size,0);
 settings.intent(body);const accepted=settings.submit(),good=settings.take('caption-proposals',true);assert.equal(good.body.seed,42);good.reject(Object.assign(Error('Definite fresh refusal'),{status:409}));await accepted;assert.equal(settingsStore.data.size,0);
 trace.push({case:'other_fresh_invalid_settings',URL_and_fractional_seed_correctable:true,valid_correction_POST:true});
 const stored=storage(),bad=JSON.stringify({...body,instruction:'\u{1f600}'.repeat(2001)});stored.data.set(key,bad);const blocked=page(stored);blocked.intent(body);await blocked.submit();assert.equal(blocked.requests.length,0);assert.ok(blocked.run('captionProposalStorageError'));assert.equal(stored.data.get(key),bad);assert.equal(blocked.$('caption-proposal-submit').disabled,true);
 trace.push({case:'invalid_stored_guidance',retained_exactly:true,corrected_form_still_fail_closed:true});
 console.log(JSON.stringify({result:'PASS',trace}));
})().catch(error=>{console.error(error);process.exitCode=1;});
