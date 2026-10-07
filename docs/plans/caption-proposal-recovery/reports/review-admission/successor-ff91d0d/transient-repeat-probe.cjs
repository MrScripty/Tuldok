'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),crypto=require('node:crypto');
class Element {
  constructor(id=''){this.id=id;this.value='';this.dataset={};this.listeners={};this.children=[];this.classList={toggle(){}};}
  addEventListener(event,fn){(this.listeners[event]||=[]).push(fn);}replaceChildren(...children){this.children=children;}append(...children){this.children.push(...children);}setAttribute(){}
  matches(selector){return selector==='form'&&['editor','filters'].includes(this.id);}querySelectorAll(){return [];}
  async dispatch(event){for(const fn of this.listeners[event]||[])await fn({preventDefault(){},currentTarget:this});}
}
const elements=new Map(),element=id=>{if(!elements.has(id))elements.set(id,new Element(id));return elements.get(id);};
const listeners={},requests=[],timers=new Map();let timerId=0;
const response=(data,ok=true,status=200)=>({ok,status,json:async()=>data});
const empty={items:[],total:0,analysis:{records:0,unlabeled:0,protected_groups:0,duplicate_content_records:0,unknown_rights:0,labels:{}}};
const context=vm.createContext({console,URLSearchParams,structuredClone,crypto,confirm:()=>false,location:{hash:''},history:{pushState(){}},
  setTimeout:fn=>{timers.set(++timerId,fn);return timerId;},clearTimeout:id=>timers.delete(id),
  document:{getElementById:element,createElement:()=>new Element(),createElementNS:()=>new Element()},
  window:{addEventListener(name,fn){(listeners[name]||=[]).push(fn);}},
  fetch:(url,options)=>url.includes('/records?')?Promise.resolve(response(empty)):url.endsWith('/grounded/jobs')?Promise.resolve(response({jobs:[]})):new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}))});
const root=process.env.TULDOK_SOURCE_ROOT||path.resolve(__dirname,'..');
for(const file of ['workbench.js','caption-proposals.js'])vm.runInContext(fs.readFileSync(path.join(root,'static',file),'utf8'),context);
const run=code=>vm.runInContext(code,context),flush=()=>new Promise(resolve=>setImmediate(resolve));
const take=suffix=>{const index=requests.findIndex(r=>r.url.endsWith(suffix));assert.notEqual(index,-1,suffix);return requests.splice(index,1)[0];};
const resolve=(suffix,data)=>take(suffix).resolve(response(data));
const row={id:'a'.repeat(32),name:'Image A',kind:'image',task:'image_caption',annotation:{caption:'Earlier'},review:'human_reviewed',revision:2,source_revision:1,groups:['g'],provenance:{rights:'Authored'}};
const other={...row,id:'b'.repeat(32),name:'Image B'};
const after={...row,revision:3,annotation:{caption:'Proposed'},review:'draft'};
let job={id:'c'.repeat(32),revision:3,status:'completed',source:row,annotation:{caption:'Proposed'},config:{model:'fixture'},error:''};
context.row=row;context.other=other;context.after=after;
const button=label=>element('caption-proposal-jobs').children.flatMap(section=>section.children).find(child=>child.textContent===label);
(async()=>{
  await flush();run('showRecord(row)');resolve('/caption-proposals',{jobs:[]});await flush();
  element('caption-proposal-url').value='http://127.0.0.1:1000';element('caption-proposal-model').value='fixture';element('caption-proposal-guidance').value='Original intent';element('caption-proposal-seed').value='42';
  const original=element('caption-proposal-form').dispatch('submit'),originalPost=take('/caption-proposals'),originalBody=JSON.parse(originalPost.options.body);
  originalPost.reject(Error('Original admission acknowledgement lost'));await original;
  const repeat=element('caption-proposal-form').dispatch('submit'),repeatPost=take('/caption-proposals');assert.deepEqual(JSON.parse(repeatPost.options.body),originalBody);
  repeatPost.resolve(response({error:'A different caption worker is active; original delayed POST may still arrive later'},false,409));await repeat;
  assert.equal(run('captionProposalPendingRequest.request_id'),originalBody.request_id);
  element('caption-proposal-guidance').value='Changed intent';await element('caption-proposal-form').dispatch('submit');assert.equal(requests.length,0);
  element('caption-proposal-guidance').value='Original intent';const success=element('caption-proposal-form').dispatch('submit'),successPost=take('/caption-proposals');assert.deepEqual(JSON.parse(successPost.options.body),originalBody);
  successPost.resolve(response({...job,id:originalBody.request_id}));await flush();resolve('/caption-proposals',{jobs:[{...job,id:originalBody.request_id}]});await success;assert.equal(run('captionProposalPendingRequest'),null);
  const firstRefusal=element('caption-proposal-form').dispatch('submit'),firstRefusalPost=take('/caption-proposals'),refusedBody=JSON.parse(firstRefusalPost.options.body);firstRefusalPost.resolve(response({error:'Fresh request definitely refused'},false,409));await firstRefusal;
  assert.equal(run('captionProposalPendingRequest'),null);
  element('caption-proposal-guidance').value='Changed after definite refusal';const changed=element('caption-proposal-form').dispatch('submit'),changedPost=take('/caption-proposals'),changedBody=JSON.parse(changedPost.options.body);assert.notEqual(changedBody.request_id,refusedBody.request_id);
  changedPost.resolve(response({...job,id:changedBody.request_id}));await flush();resolve('/caption-proposals',{jobs:[]});await changed;
  console.log(JSON.stringify({original_id:originalBody.request_id,repeat_409_retained_identity:true,changed_intent_refused:true,successful_repeat_same_body:true,successful_repeat_released_identity:true,fresh_409_released_identity:true,fresh_changed_intent_accepted:true,fresh_new_id_differs:true},null,2));
})().catch(error=>{console.error(error);process.exitCode=1;});
