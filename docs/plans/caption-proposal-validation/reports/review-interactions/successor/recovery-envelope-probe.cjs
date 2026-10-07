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
 const results=[];
 const freshOversized=['http://127.0.0.1:8765'+'/'.repeat(33000),'http://127.0.0.1:8765/v1'+'/'.repeat(33000),'\u0085'.repeat(33000)+'http://127.0.0.1:8765','http://127.0.0.1:8765'+'\u0085'.repeat(33000)];
 for(const server_url of freshOversized){
  const s=storage(),form=page(s);form.intent({...body,server_url});const rejected=form.submit();
  assert.equal(form.requests.length,0);await rejected;assert.equal(s.data.size,0);assert.equal(form.run('captionProposalStorageError'),'');assert.equal(form.$('caption-proposal-submit').disabled,false);
  assert.ok(form.$('caption-proposal-status').textContent.includes('recovery bound'));
  form.intent();const corrected=form.submit(),post=form.take('caption-proposals',true);post.reject(Object.assign(Error('Definitive first refusal'),{status:400}));await corrected;
  assert.equal(s.data.size,0);assert.equal(form.run('captionProposalStorageError'),'');assert.equal(form.$('caption-proposal-submit').disabled,false);
  const legacy=storage(),raw=JSON.stringify({...body,server_url});legacy.data.set(key,raw);const blocked=page(legacy);blocked.intent();await blocked.submit();assert.equal(blocked.requests.length,0);assert.equal(legacy.data.get(key),raw);assert.ok(blocked.run('captionProposalStorageError'));
  results.push({url_length:server_url.length,fresh_correctable:true,legacy_evidence_retained:true});
 }
 for(const length of [32767,32768,32769]){
  const exact={...body,instruction:'Control\u0000 and emoji\u{1f600}',request_id:'1'.repeat(32)};
  exact.server_url+='/'.repeat(length-JSON.stringify(exact).length);assert.equal(JSON.stringify(exact).length,length);
  const s=storage(),form=page(s);form.intent(exact);const start=form.submit();
  if(length>32768){assert.equal(form.requests.length,0);await start;assert.equal(s.data.size,0);assert.equal(form.run('captionProposalStorageError'),'');assert.equal(form.$('caption-proposal-submit').disabled,false);}
  else{
   const post=form.take('caption-proposals',true);assert.deepEqual(JSON.parse(JSON.stringify(post.body)),exact);assert.deepEqual(JSON.parse(s.data.get(key)),exact);assert.equal(s.data.get(key).length,length);
   post.reject(Error('Unknown response outcome'));await start;
   const reload=page(s),lookup=reload.refresh();reload.take('caption-proposals').resolve({jobs:[]});await flush();reload.take('caption-proposals/'+exact.request_id).reject(Object.assign(Error('Missing'),{status:404}));await lookup;
   reload.intent({...exact,instruction:'New guidance'});await reload.submit();assert.equal(reload.requests.length,0);assert.deepEqual(JSON.parse(s.data.get(key)),exact);
   reload.intent(exact);const repeat=reload.submit(),repeatPost=reload.take('caption-proposals',true);assert.deepEqual(JSON.parse(JSON.stringify(repeatPost.body)),exact);repeatPost.reject(Object.assign(Error('Refused repeat'),{status:400}));await repeat;assert.deepEqual(JSON.parse(s.data.get(key)),exact);
  }
  results.push({json_utf16_units:length,expected: length>32768?'fresh correctable refusal':'exact persistence, lost response, reload 404, changed intent refusal and repeated 400 evidence retained'});
 }
 console.log(JSON.stringify({source_head:'9483d4a2f5c1391b3f882e107cee6846aeb36a39',source_tree:'0fe33807c03e582c3a5ce9f4403be37e570e8f59',all_passed:true,results},null,2));
})().catch(error=>{console.error(error);process.exitCode=1;});
