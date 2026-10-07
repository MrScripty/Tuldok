'use strict';
// Independent bounded VM probe: real composed production controllers, synthetic fetch only.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),crypto=require('node:crypto');
class Element {
 constructor(id=''){this.id=id;this.value='';this.dataset={};this.listeners={};this.children=[];this.classList={toggle(){}};}
 addEventListener(event,fn){(this.listeners[event]||=[]).push(fn);}replaceChildren(...children){this.children=children;}append(...children){this.children.push(...children);}setAttribute(){}matches(){return false;}querySelectorAll(){return [];}
 async dispatch(event){for(const fn of this.listeners[event]||[])await fn({preventDefault(){},currentTarget:this,target:this});}
}
const row={id:'a'.repeat(32),name:'Synthetic source',kind:'text',task:'text_classification',review:'draft',revision:1,source_revision:1,groups:['g'],annotation:null,text:'An exact synthetic prompt\r\ne\u0301 😀',content_hash:'frozen-content-hash',source_sha256:'frozen-source-hash',provenance:{rights:'Authored'}};
const other={...row,id:'b'.repeat(32),name:'Other'};
const after={...row,revision:2,annotation:{label:'keep'},review:'draft'};
const job={id:'c'.repeat(32),revision:3,status:'completed',source:row,annotation:{label:'keep'},config:{server_url:'http://127.0.0.1:23456',model:'fixture',instruction:'Exact synthetic fixture',seed:42,labels:['keep','cancel']},error:''};
const page={items:[],total:0,analysis:{records:0,unlabeled:0,protected_groups:0,duplicate_content_records:0,unknown_rights:0,labels:{}}};
const flush=()=>new Promise(resolve=>setImmediate(resolve));
async function harness(){
 const elements=new Map(),element=id=>{if(!elements.has(id))elements.set(id,new Element(id));return elements.get(id);};
 const requests=[],timers=new Map(),listeners={};let nextTimer=0;
 const reply=(data,status=200)=>({ok:status<400,status,json:async()=>data});
 const context=vm.createContext({console,URLSearchParams,structuredClone,crypto:{randomUUID:crypto.randomUUID},confirm:()=>false,
  setTimeout:fn=>{timers.set(++nextTimer,fn);return nextTimer;},clearTimeout:id=>timers.delete(id),
  document:{getElementById:element,createElement:()=>new Element(),createElementNS:()=>new Element()},
  window:{addEventListener(event,fn){(listeners[event]||=[]).push(fn);}},
  fetch:(url,options)=>url.includes('/records?')?Promise.resolve(reply(page)):url.endsWith('/grounded/jobs')?Promise.resolve(reply({jobs:[]})):new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}))});
 const root=process.env.TULDOK_SOURCE_ROOT||path.resolve(__dirname,'../../../../../..');
 for(const file of ['workbench.js','instruction-responses.js','text-classification-proposals.js'])vm.runInContext(fs.readFileSync(path.join(root,'static',file),'utf8'),context,{filename:file});
 const run=code=>vm.runInContext(code,context);Object.assign(context,{row,other,after,job});
 const take=suffix=>{const i=requests.findIndex(r=>r.url.endsWith(suffix));assert.notEqual(i,-1,`Pending request ${suffix}`);return requests.splice(i,1)[0];};
 const resolve=(suffix,data,status=200)=>take(suffix).resolve(reply(data,status));
 const button=label=>element('text-classification-proposal-jobs').children.flatMap(s=>s.children).find(e=>e.textContent===label);
 const settleShown=async(jobs=[job],parent=row)=>{resolve('/text-classification-proposals',{jobs});resolve('/responses',{parent,responses:[]});await flush();};
 for(const [key,value] of Object.entries(job.config))element('text-classification-proposal-'+({server_url:'url',instruction:'guidance'}[key]||key)).value=key==='labels'?JSON.stringify(value):String(value);
 await flush();run('showRecord(row)');await settleShown();
 return {element,requests,timers,listeners,run,take,resolve,reply,button,settleShown};
}
async function summaryProjectionAllowsApply(){
 const h=await harness();const summary={...job,source:{...row}};delete summary.source.text;const polling=h.run('refreshTextClassificationProposals()');h.resolve('/text-classification-proposals',{jobs:[summary]});await polling;
 const applying=h.button('Apply as draft').dispatch('click');const held=h.take('/text-classification-proposals/decide/'+job.id);
 held.resolve(h.reply({record:after,job:{...job,status:'applied'},changed:true}));await flush();await h.settleShown([{...job,status:'applied'}],after);h.resolve('/text-classification-proposals',{jobs:[{...job,status:'applied'}]});await applying;assert.equal(h.run('current.revision'),2);assert.equal(h.run('current.review'),'draft');
}
async function requestedGatewayNormalizationKeepsApply(){
 const h=await harness();const summary={...job,source:{...row},config:{...job.config,requested_server_url:job.config.server_url+'/v1/'}};delete summary.source.text;h.element('text-classification-proposal-url').value=summary.config.requested_server_url;
 const polling=h.run('refreshTextClassificationProposals()');h.resolve('/text-classification-proposals',{jobs:[summary]});await polling;const applying=h.button('Apply as draft').dispatch('click');const held=h.take('/text-classification-proposals/decide/'+job.id);
 held.resolve(h.reply({record:after,job:{...summary,status:'applied'},changed:true}));await flush();await h.settleShown([{...summary,status:'applied'}],after);h.resolve('/text-classification-proposals',{jobs:[{...summary,status:'applied'}]});await applying;
 assert.equal(h.run('current.revision'),2);assert.equal(h.element('text-classification-proposal-url').value,summary.config.requested_server_url);
}
async function frozenChoiceAndSourceFences(){
 const h=await harness();
 for(const labels of ['["cancel","keep"]','["keep","invented"]','{"label":"keep"}','["keep","keep"]','[" keep "]']){
  h.element('text-classification-proposal-labels').value=labels;await h.element('text-classification-proposal-labels').dispatch('input');await h.button('Apply as draft').dispatch('click');assert.equal(h.requests.length,0,'Changed or malformed choices cannot POST Apply');
 }
 h.element('text-classification-proposal-labels').value=JSON.stringify(job.config.labels);
 for(const code of ["current={...row,revision:2}","current={...row,source_revision:2}","current={...row,content_hash:'changed'}","current={...row,source_sha256:'changed'}","current={...row,annotation:{label:'manual'}}"]){
  h.run(code);await h.button('Apply as draft').dispatch('click');assert.equal(h.requests.length,0,'Changed source/annotation cannot POST Apply');
 }
}
async function admissionUnknownRetainsIdentity(){
 const h=await harness();const starting=h.element('text-classification-proposal-form').dispatch('submit');const start=h.take('/text-classification-proposals'),body=JSON.parse(start.options.body);
 const polling=h.run('refreshTextClassificationProposals()');h.resolve('/text-classification-proposals',{jobs:[]});await flush();h.resolve('/text-classification-proposals/'+body.request_id,{error:'Not persisted yet'},404);await polling;
 assert.equal(h.run('textClassificationProposalPendingRequest.request_id'),body.request_id);start.reject(Error('Lost acknowledgement'));await starting;
 const repeating=h.element('text-classification-proposal-form').dispatch('submit');const repeat=h.take('/text-classification-proposals');assert.deepEqual(JSON.parse(repeat.options.body),body);repeat.resolve(h.reply({error:'Earlier admission unknown'},409));await repeating;
 assert.equal(h.run('textClassificationProposalPendingRequest.request_id'),body.request_id);h.element('text-classification-proposal-labels').value='["other"]';await h.element('text-classification-proposal-form').dispatch('submit');assert.equal(h.requests.length,0,'Changed intent cannot escape unknown admission');
}
async function formChangeFencesApplyAcknowledgement(){
 const h=await harness();const applying=h.button('Apply as draft').dispatch('click');const held=h.take('/text-classification-proposals/decide/'+job.id);h.element('text-classification-proposal-labels').value='["new"]';await h.element('text-classification-proposal-labels').dispatch('input');
 held.resolve(h.reply({record:after,job:{...job,status:'applied'},changed:true}));await flush();h.resolve('/text-classification-proposals',{jobs:[{...job,status:'applied'}]});await applying;assert.equal(h.run('current.revision'),1);assert.equal(h.element('text-classification-proposal-labels').value,'["new"]');
}
async function lateResponseDraftFencesApply(){
 const h=await harness();h.run("selected.set(row.id,row);responseSelected.set('d'.repeat(32),{id:'d'.repeat(32),revision:1,prompt_id:row.id,parent_revision:1,source_revision:1});releasePreview={eligible:true};responsePreview={eligible:true}");
 const pairs=h.run('JSON.stringify({records:[...selected.values()],answers:[...responseSelected.values()]})');
 const applying=h.button('Apply as draft').dispatch('click');const held=h.take('/text-classification-proposals/decide/'+job.id);
 h.run('editResponse()');h.element('response-completion').value='A later exact answer\r\ne\u0301 😀';await h.element('response-completion').dispatch('input');
 const owner=h.run('({id:responseEditor.id,epoch:responseEditEpoch})');held.resolve(h.reply({record:after,job:{...job,status:'applied'},changed:true}));await flush();h.resolve('/text-classification-proposals',{jobs:[{...job,status:'applied'}]});await applying;
 assert.equal(h.run('current.revision'),1);assert.equal(h.run('responseParent.revision'),1);assert.equal(h.run('responseDirty'),true);assert.equal(h.run('responseEditor.id'),owner.id);assert.equal(h.run('responseEditEpoch'),owner.epoch);assert.equal(h.element('response-completion').value,'A later exact answer\r\ne\u0301 😀');
 assert.equal(h.run('releasePreview'),null);assert.equal(h.run('responsePreview'),null);assert.equal(h.run('JSON.stringify({records:[...selected.values()],answers:[...responseSelected.values()]})'),pairs);
}
async function rejectCannotAcquireEitherEditor(){
 const h=await harness();h.element('label').value='Human saved';await h.element('editor').dispatch('input');const saving=h.element('editor').dispatch('submit');const held=h.take('/records/'+row.id);const epoch=h.run('editorEpoch');
 const rejecting=h.button('Reject classification proposal').dispatch('click');h.resolve('/text-classification-proposals/decide/'+job.id,{job:{...job,status:'rejected'}});await flush();h.resolve('/text-classification-proposals',{jobs:[{...job,status:'rejected'}]});await rejecting;
 assert.equal(h.run('editorEpoch'),epoch);held.resolve(h.reply({...after,annotation:{label:'Human saved'}}));await flush();await h.settleShown([{...job,status:'rejected'}],after);await saving;assert.equal(h.run('current.revision'),2);assert.equal(h.run('dirty'),false);assert.equal(h.element('label').value,'Human saved');
}
async function answerSaveDuringApplyKeepsExactParent(){
 const h=await harness();const applying=h.button('Apply as draft').dispatch('click');const held=h.take('/text-classification-proposals/decide/'+job.id);
 h.run('editResponse()');h.element('response-completion').value='Independent answer';await h.element('response-completion').dispatch('input');const saving=h.element('response-form').dispatch('submit');const saved=h.take('/api/workbench/responses');const body=JSON.parse(saved.options.body);
 assert.equal(body.parent_revision,1);held.resolve(h.reply({record:after,job:{...job,status:'applied'},changed:true}));await flush();h.resolve('/text-classification-proposals',{jobs:[{...job,status:'applied'}]});await applying;
 assert.equal(h.run('current.revision'),1);assert.equal(h.run('responseParent.revision'),1);saved.resolve(h.reply({error:'Parent revision changed. Reload the prompt.'},409));await saving;assert.equal(h.run('responseDirty'),true);assert.equal(h.element('response-completion').value,'Independent answer');
}
async function navigationAndLateEvidence(){
 const h=await harness();const inspecting=h.button('Inspect request evidence').dispatch('click');const evidence=h.take('/text-classification-proposals/'+job.id);
 const opening=h.run('openRecord(other.id)');h.resolve('/records/'+other.id,other);await opening;await h.settleShown([job],other);
 evidence.resolve(h.reply({...job,source:{...row,text:'private prior source'}}));await inspecting;assert.equal(h.run('current.id'),other.id);assert.equal(h.element('text-classification-proposal-jobs').children.length,0);
}
async function terminalAbstentionNeverOffersApply(){
 const h=await harness();const polling=h.run('refreshTextClassificationProposals()');h.resolve('/text-classification-proposals',{jobs:[{...job,status:'abstained',annotation:null,abstained:true}]});await polling;
 assert.equal(h.button('Apply as draft'),undefined);assert.ok(h.button('Reject classification proposal'));assert.equal(h.timers.size,0);
}
(async()=>{let failed=0;for(const test of [summaryProjectionAllowsApply,requestedGatewayNormalizationKeepsApply,frozenChoiceAndSourceFences,admissionUnknownRetainsIdentity,formChangeFencesApplyAcknowledgement,lateResponseDraftFencesApply,rejectCannotAcquireEitherEditor,answerSaveDuringApplyKeepsExactParent,navigationAndLateEvidence,terminalAbstentionNeverOffersApply]){try{await test();console.log(test.name+' passed');}catch(error){failed++;console.error(test.name+': '+error.stack);}}if(failed)process.exitCode=1;})().catch(error=>{console.error(error);process.exitCode=1;});
