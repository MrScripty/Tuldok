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
 const b=page(s),first=b.refresh();b.take('caption-proposals').resolve({jobs:[persisted(body.request_id)]});await first;
 b.intent({...body,instruction:'New document pending ID2'});const start=b.submit(),post=b.take('caption-proposals',true),second=JSON.parse(JSON.stringify(post.body));post.reject(Error('ID2 acknowledgement lost'));await start;b.listeners.pagehide();return {s,a,second};
}
(async()=>{
 const removal=await replaced();removal.a.listeners.pageshow();assert.equal(removal.a.run('captionProposalPendingRequest.request_id'),removal.second.request_id);assert.equal(removal.a.$('caption-proposal-guidance').value,removal.second.instruction);
 removal.a.take('caption-proposals').resolve({jobs:[persisted(body.request_id)]});await flush();removal.a.take('caption-proposals/'+removal.second.request_id).reject(Object.assign(Error('ID2 not visible'),{status:404}));await flush();
 assert.deepEqual(JSON.parse(removal.s.data.get(key)),removal.second);
 const c=page(removal.s);c.intent({...body,instruction:'Changed ID3 after lost ID2'});await c.submit();assert.equal(c.requests.length,0);
 trace.push({case:'stale_remove_fixed',pageshow_adopts_ID2_and_exact_form:true,newer_entry_preserved:true,full_reload_changed_POSTs:0});
 const overwrite=await replaced();overwrite.a.listeners.pageshow();const held=overwrite.a.take('caption-proposals');overwrite.a.intent(body);await overwrite.a.submit();assert.equal(overwrite.a.requests.length,0);assert.deepEqual(JSON.parse(overwrite.s.data.get(key)),overwrite.second);
 held.resolve({jobs:[persisted(body.request_id)]});await flush();overwrite.a.take('caption-proposals/'+overwrite.second.request_id).reject(Object.assign(Error('ID2 not visible'),{status:404}));await flush();
 trace.push({case:'stale_overwrite_fixed',stale_ID1_POSTs:0,newer_entry_preserved:true});
 const s=storage(),a=page(s);a.intent();const old=a.submit(),oldPost=a.take('caption-proposals',true),first=JSON.parse(JSON.stringify(oldPost.body));a.listeners.pagehide();
 const b=page(s),known=b.refresh();b.take('caption-proposals').resolve({jobs:[persisted(first.request_id)]});await known;b.run("crypto.randomUUID=()=> '2'.repeat(32)");b.intent({...body,instruction:'Newer unknown ID2'});const newer=b.submit(),newPost=b.take('caption-proposals',true),second=JSON.parse(JSON.stringify(newPost.body));newPost.reject(Error('Newer ACK lost'));await newer;
 oldPost.reject(Object.assign(Error('Late old first 409'),{status:409}));await old;assert.deepEqual(JSON.parse(s.data.get(key)),second);assert.equal(a.run('captionProposalPendingRequest.request_id'),second.request_id);
 trace.push({case:'late_first_refusal_fixed',newer_entry_preserved:true,old_document_adopts_live_ID:true});
 // Live replacement while the old GET is held, without pagehide fencing it.
 const shared=storage();shared.data.set(key,JSON.stringify(body));const liveA=page(shared),pendingLookup=liveA.refresh(),oldList=liveA.take('caption-proposals');const liveB=page(shared),resolveOld=liveB.refresh();liveB.take('caption-proposals').resolve({jobs:[persisted(body.request_id)]});await resolveOld;
 liveB.intent({...body,instruction:'New active-document ID2'});const liveStart=liveB.submit(),livePost=liveB.take('caption-proposals',true),liveBody=JSON.parse(JSON.stringify(livePost.body));livePost.reject(Error('New ACK lost'));await liveStart;
 oldList.resolve({jobs:[persisted(body.request_id)]});await flush();liveA.take('caption-proposals/'+liveBody.request_id).reject(Object.assign(Error('ID2 absent'),{status:404}));await pendingLookup;assert.deepEqual(JSON.parse(shared.data.get(key)),liveBody);
 trace.push({case:'replacement_during_live_GET',latest_pending_ID:liveA.run('captionProposalPendingRequest.request_id'),entry_preserved:true});
 console.log(JSON.stringify({result:'PASS',trace}));
})().catch(error=>{console.error(error);process.exitCode=1;});
