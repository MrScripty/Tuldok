'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
class Element{
 constructor(value=''){this.value=value;this.listeners={};this.disabled=false;this.hidden=false;}
 addEventListener(name,fn){(this.listeners[name]??=[]).push(fn);}
 dispatchEvent(event){for(const fn of this.listeners[event.type]||[])fn(event);}
 async fire(type){for(const fn of this.listeners[type]||[])await fn({type});}
 replaceChildren(...children){this.children=children;this.value=children[0]?.value||'';}
}
const root=process.env.TULDOK_SOURCE_ROOT||path.resolve(__dirname,'..');
const ids=[...fs.readFileSync(path.join(root,'static/workbench.html'),'utf8').matchAll(/id="([^"]+)"/g)].map(m=>m[1]);
const elements=new Map(ids.map(id=>[id,new Element()])), $=id=>elements.get(id)||null;
const requests=[],events={};
const context=vm.createContext({console,$,URL,document:{getElementById:$},current:{id:"source",revision:1},editorEpoch:0,dirty:false,textClassificationProposalModelEpoch:0,textClassificationProposalFormEpoch:0,captionProposalModelEpoch:0,modelEpoch:0,pumasTypedEpoch:{},
 Option:class{constructor(text,value){this.textContent=text;this.value=value;}},Event:class{constructor(type){this.type=type;}},
 window:{addEventListener:(name,fn)=>{const old=events[name];events[name]=()=>{if(old)old();fn();};}},api:(url,body)=>new Promise((resolve,reject)=>requests.push({url,body,resolve,reject}))});
vm.runInContext(fs.readFileSync(path.join(root,'static/pumas-owner-reuse.js'),'utf8'),context);
vm.runInContext(fs.readFileSync(path.join(root,'static/pumas-model-selection.js'),'utf8'),context);
const run=code=>vm.runInContext(code,context),copy=v=>JSON.parse(JSON.stringify(v));
const source='ab9890fe3248ed7c435b958cded0b131b0700a35',selected={id:'explicit-library',root:'/owned/fixture'};
const library={...selected,name:'Fixture',version:null};
const listed={registered_libraries:[library],local_models:[{registry_library_id:selected.id,library_root:selected.root,observation:'unavailable'}],producer_commit:source,producer_status:'PR48 draft',registry_context:'ctx',scope:'index only'};
const receipt={observation:{producer_commit:source,selected,registry_context:'ctx',service:{service_generation:'HTTP',instance:{generation:'core'}}},server_url:'http://127.0.0.1:32123',proof:'hmac',observation_sha256:'sha'};
function next(){assert.ok(requests.length);return requests.shift();}
async function list(){const task=$('pumas-owner-list').fire('click');next().resolve(copy(listed));await task;$('pumas-owner-library').value=selected.id;await $('pumas-owner-library').fire('change');}
async function observe(){const task=$('pumas-owner-observe').fire('click');const request=next();assert.equal(request.url,'/api/generation/local-pumas/observe');assert.deepEqual(copy(request.body),{selected});request.resolve(copy(receipt));await task;}
(async()=>{
 $('pumas-owner-target').value='classification';
 for(const prefix of ['caption-proposal','text-classification-proposal','grounded']){
  if($(prefix+'-protocol'))$(prefix+'-protocol').value='legacy';$(prefix+'-url').value='retain';$(prefix+'-model').value='model';if($(prefix+'-profile'))$(prefix+'-profile').value='';
 }
 const listing=$('pumas-owner-list').fire('click');await $('pumas-owner-list').fire('click');assert.equal(requests.length,1);next().resolve(copy(listed));await listing;
 assert.equal($('pumas-owner-library').value,'');assert.equal($('pumas-owner-use').disabled,true,'No implicit selection/authentication');
 $('pumas-owner-library').value=selected.id;await $('pumas-owner-library').fire('change');await observe();
 assert.equal($('text-classification-proposal-url').value,'retain','Observation starts no proposal or URL mutation');
 for(const [purpose,prefix] of [['classification','text-classification-proposal'],['caption','caption-proposal'],['rewrite','grounded']]){
  $('pumas-owner-target').value=purpose;await $('pumas-owner-target').fire('change');
  for(const name of ['url','model','protocol','profile'].filter(name=>$(prefix+'-'+name))){
   const held=$('pumas-owner-use').fire('click'),request=next();$(prefix+'-'+name).value='new-'+name;await $(prefix+'-'+name).fire('input');request.resolve(copy(receipt));await held;
   if(name!=='url')assert.notEqual($(prefix+'-url').value,receipt.server_url,'Later configuration fences copy');
   if($(prefix+'-protocol'))$(prefix+'-protocol').value='legacy';$(prefix+'-url').value='retain';
  }
  const restore=$('pumas-owner-use').fire('click'),restored=next();$(prefix+($(prefix+'-profile')?'-profile':'-model')).value='no-event-restored';restored.resolve(copy(receipt));await restore;assert.equal($(prefix+'-url').value,'retain');
  const epoch=$('pumas-owner-use').fire('click'),epochRequest=next();
  run(prefix==='text-classification-proposal'?'++textClassificationProposalFormEpoch':prefix==='caption-proposal'?'++captionProposalModelEpoch':'++modelEpoch');
  epochRequest.resolve(copy(receipt));await epoch;assert.equal($(prefix+'-url').value,'retain','Same-value Restore epoch owns configuration');
  const typed=$('pumas-owner-use').fire('click'),typedRequest=next();run(`pumasTypedEpoch[${JSON.stringify(prefix)}]=(pumasTypedEpoch[${JSON.stringify(prefix)}]||0)+1`);typedRequest.resolve(copy(receipt));await typed;assert.equal($(prefix+'-url').value,'retain');
  if($(prefix+'-protocol')){$(prefix+'-protocol').value='pumas_typed_v1';await $('pumas-owner-use').fire('click');assert.equal(requests.length,0);assert.match($('pumas-owner-status').textContent,/separate producer stacks/);$(prefix+'-protocol').value='legacy';}
  let changes=0;$(prefix+'-url').addEventListener('input',()=>changes++);
  const using=$('pumas-owner-use').fire('click');await $('pumas-owner-use').fire('click');assert.equal(requests.length,1);
  const request=next();assert.equal(request.url,'/api/generation/local-pumas/use');assert.equal(request.body.protocol,'legacy');request.resolve(copy(receipt));await using;
  assert.equal($(prefix+'-url').value,receipt.server_url);assert.equal(changes,1);$(prefix+'-url').value='retain';
 }
 const changed=$('pumas-owner-use').fire('click'),changeRequest=next(),different=copy(receipt);different.observation.service.service_generation='successor';changeRequest.resolve(different);await changed;
 assert.equal($('pumas-owner-use').disabled,true);assert.match($('pumas-owner-status').textContent,/changed/);await observe();
 const selection=$('pumas-owner-use').fire('click'),selectionRequest=next();$('pumas-owner-library').value='';await $('pumas-owner-library').fire('change');selectionRequest.resolve(copy(receipt));await selection;assert.equal($('grounded-url').value,'retain');
 await list();await observe();const purpose=$('pumas-owner-use').fire('click'),purposeRequest=next();$('pumas-owner-target').value='caption';await $('pumas-owner-target').fire('change');purposeRequest.resolve(copy(receipt));await purpose;assert.equal($('grounded-url').value,'retain');
 $('pumas-owner-target').value='classification';await $('pumas-owner-target').fire('change');
 const typedSource='40c5cbfed67a6f0e862a1197bb5105363d67bdb1';
 function inspection(capability){return {receipt:copy(receipt),kind:capability?'capability':'catalog',discovery_contract_source:source,typed_contract_source:typedSource,inference_admitted:false,configuration_apply_supported:false,joint_producer_qualified:false,inspection:capability?{server_url:receipt.server_url,model:'served-alias',profile:'text-profile',purpose:'classification',protocol:'pumas_typed_v1',producer_contract_source:typedSource,owner_authenticated:false,inference_admitted:false,capability_observation:{observed_sha256:'a'.repeat(64),capabilities:{model:'served-alias',profile:'text-profile'}}}:{models:[{id:'served-alias'}],producer_contract_source:typedSource}};}
 for(const capability of [false,true]){
  $('pumas-owner-model').value='served-alias';$('pumas-owner-profile').value='text-profile';
  const button=capability?'pumas-owner-capability':'pumas-owner-models';
  for(const change of ['kind','discovery-source','typed-source','selected','endpoint','context','generation',...(capability?['alias','profile','purpose']:['catalog-source'])]){
   const task=$(button).fire('click'),req=next(),bad=inspection(capability);
   if(change==='kind')bad.kind='mixed';if(change==='discovery-source')bad.discovery_contract_source='other';if(change==='typed-source')bad.typed_contract_source='other';
   if(change==='selected')bad.receipt.observation.selected.id='other';if(change==='endpoint')bad.receipt.server_url='http://127.0.0.1:39090';if(change==='context')bad.receipt.observation.registry_context='other';if(change==='generation')bad.receipt.observation.service.service_generation='other';
   if(change==='alias')bad.inspection.model='wrong';if(change==='profile')bad.inspection.profile='wrong';if(change==='purpose')bad.inspection.purpose='rewrite';if(change==='catalog-source')bad.inspection.producer_contract_source='other';
   req.resolve(bad);await task;assert.match($('pumas-owner-status').textContent,/association changed/,change);assert.equal(run('pumasOwnerTypedInspection'),null);
  }
  const held=$(button).fire('click'),req=next();run('++editorEpoch');req.resolve(inspection(capability));await held;assert.equal(run('pumasOwnerTypedInspection'),null);
  const good=$(button).fire('click'),goodReq=next();assert.equal(goodReq.url,'/api/generation/local-pumas/'+(capability?'typed_selection':'typed_models'));goodReq.resolve(inspection(capability));await good;
  assert.equal(run('pumasOwnerTypedInspection.configuration_apply_supported'),false);assert.equal($('text-classification-proposal-url').value,'retain');
  if(!capability){assert.equal($('pumas-owner-model').value,'');$('pumas-owner-model').value='served-alias';}
 }
 const departure=$('pumas-owner-use').fire('click'),oldRequest=next();events.pagehide();events.pageshow();
 const fresh=$('pumas-owner-list').fire('click'),newRequest=next();oldRequest.resolve(copy(receipt));await departure;assert.equal($('pumas-owner-list').disabled,true,'Old finalizer cannot release new operation');newRequest.resolve(copy(listed));await fresh;
 $('pumas-owner-library').value=selected.id;await $('pumas-owner-library').fire('change');const failure=$('pumas-owner-observe').fire('click');next().reject(Error('Attachment unresolved; no fallback'));await failure;assert.match($('pumas-owner-status').textContent,/unresolved/);assert.equal($('pumas-owner-use').disabled,true);assert.equal(requests.length,0);
 console.log('Explicit SDK chooser: no selection/acquisition/inference, full config+Restore epochs, all destinations, typed refusal, complete service drift, selection/purpose/departure, late-finalizer and no fallback verified.');
})().catch(error=>{console.error(error);process.exitCode=1;});
