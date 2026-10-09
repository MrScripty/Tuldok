'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{constructor(){this.value='';this.disabled=false;this.hidden=true;this.listeners={};}addEventListener(t,f){(this.listeners[t]??=[]).push(f);}dispatchEvent(e){for(const f of this.listeners[e.type]||[])f(e);}async fire(t){for(const f of this.listeners[t]||[])await f({type:t});}replaceChildren(...c){this.value=c[0]?.value||'';}}
const ids=[...fs.readFileSync('static/workbench.html','utf8').matchAll(/id="([^"]+)"/g)].map(m=>m[1]);const el=new Map(ids.map(x=>[x,new Element()])),events={},requests=[];
const context=vm.createContext({document:{getElementById:id=>el.get(id)||null},window:{addEventListener:(t,f)=>(events[t]??=[]).push(f)},console,JSON,Error,URL,
 Option:class{constructor(text,value){this.textContent=text;this.value=value;}},Event:class{constructor(type){this.type=type;}},
 api:(url,body)=>new Promise((resolve,reject)=>requests.push({url,body,resolve,reject})),
 current:{id:'source',revision:1,source_revision:1},editorEpoch:0,dirty:false,hasUnsavedEdits:()=>false,modelEpoch:0,textClassificationProposalModelEpoch:0,textClassificationProposalFormEpoch:0});
vm.runInContext(fs.readFileSync('static/pumas-typed.js','utf8'),context);vm.runInContext(fs.readFileSync('static/pumas-model-selection.js','utf8'),context);
const run=s=>vm.runInContext(s,context),get=id=>el.get(id),tick=()=>new Promise(r=>setImmediate(r));events.DOMContentLoaded.forEach(f=>f());
function reply(prefix){return {server_url:'http://127.0.0.1:39019',model:'controlled-text',profile:'controlled-text-cpu',purpose:prefix==='grounded'?'rewrite':'classification',protocol:'pumas_typed_v1',producer_contract_source:'40c5cbfed67a6f0e862a1197bb5105363d67bdb1',owner_authenticated:false,inference_admitted:false,capability_observation:{observed_sha256:'a'.repeat(64),capabilities:{model:'controlled-text',profile:'controlled-text-cpu'}}};}
function configure(p){get(p+'-url').value='http://127.0.0.1:39019';get(p+'-model').value='controlled-text';get(p+'-profile').value='';get(p+'-protocol').value='pumas_typed_v1';run('pumasTypedRender('+JSON.stringify(p)+')');}
async function inspect(p){const task=get(p+'-selection-inspect').fire('click');const req=requests.shift();assert.equal(req.url,'/api/generation/typed-selection');req.resolve(reply(p));await task;assert.equal(get(p+'-selection-use').disabled,false);}
(async()=>{
 for(const change of ['endpoint','source','requested-profile','profile-syntax','manifest-model','manifest-profile','hash']){
  const p='grounded';configure(p);if(change==='requested-profile')get(p+'-profile').value='requested-profile';
  const task=get(p+'-selection-inspect').fire('click'),req=requests.shift(),bad=reply(p);
  if(change==='endpoint')bad.server_url='http://127.0.0.1:39100';if(change==='source')bad.producer_contract_source='other';
  if(change==='profile-syntax')bad.profile='bad profile';if(change==='manifest-model')bad.capability_observation.capabilities.model='other';
  if(change==='manifest-profile')bad.capability_observation.capabilities.profile='other';if(change==='hash')bad.capability_observation.observed_sha256='bad';
  req.resolve(bad);await task;assert.equal(get(p+'-selection-use').disabled,true,change);assert.match(get(p+'-capability-metadata').textContent,/association changed/);
 }
 for(const p of ['text-classification-proposal','grounded']){
  configure(p);await inspect(p);assert.equal(get(p+'-profile').value,'');
  for(const change of ['model','profile','epoch','navigation','dirty','departure']){
   const task=get(p+'-selection-use').fire('click'),req=requests.shift();assert.equal(req.body.profile,'controlled-text-cpu');
   if(change==='model')get(p+'-model').value='different';
   if(change==='profile')get(p+'-profile').value='no-event-restore';
   if(change==='epoch')run(p==='grounded'?'++modelEpoch':'++textClassificationProposalFormEpoch');
   if(change==='navigation')run('++editorEpoch;current.id="another"');
   if(change==='dirty')run('dirty=true');
   if(change==='departure'){events.pagehide.forEach(f=>f());events.pageshow.forEach(f=>f());}
   req.resolve(reply(p));await task;assert.notEqual(get(p+'-profile').value,'controlled-text-cpu');run('dirty=false;current.id="source"');configure(p);await inspect(p);
  }
  const drift=get(p+'-selection-use').fire('click'),req=requests.shift(),bad=reply(p);bad.capability_observation.observed_sha256='changed';req.resolve(bad);await drift;assert.equal(get(p+'-selection-use').disabled,true);await inspect(p);
  let changes=0;get(p+'-model').addEventListener('change',()=>changes++);
  const use=get(p+'-selection-use').fire('click');await get(p+'-selection-use').fire('click');assert.equal(requests.length,1);requests.shift().resolve(reply(p));await use;
  assert.equal(get(p+'-profile').value,'controlled-text-cpu');assert.equal(get(p+'-model').value,'controlled-text');assert.equal(changes,1);assert.equal(requests.length,0);
 }
 const p='text-classification-proposal';configure(p);const old=get(p+'-selection-inspect').fire('click'),oldReq=requests.shift();events.pagehide.forEach(f=>f());events.pageshow.forEach(f=>f());const fresh=get(p+'-selection-inspect').fire('click'),freshReq=requests.shift();oldReq.resolve(reply(p));await old;assert.ok(run('!!pumasModelSelectionOperations["'+p+'"]'));freshReq.resolve(reply(p));await fresh;assert.equal(get(p+'-selection-use').disabled,false);
 console.log('Standalone typed exact profile, fresh Use, all text purposes, ordinary events, capability drift, config/Restore/navigation/dirty/lifecycle and late-finalizer fences passed; no proposal or owner claim.');
})().catch(e=>{console.error(e);process.exitCode=1;});
