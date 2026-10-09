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
 const durable=new Map();const context=vm.createContext({console,URL,URLSearchParams,localStorage:{getItem:key=>durable.get(key)??null,setItem:(key,value)=>durable.set(key,value),removeItem:key=>durable.delete(key)},sessionStorage:{getItem:key=>durable.get('session:'+key)??null,setItem:(key,value)=>durable.set('session:'+key,value),removeItem:key=>durable.delete('session:'+key)},navigator:{locks:{request:async(_name,_options,fn)=>fn()}},structuredClone,crypto:{randomUUID:crypto.randomUUID},confirm:()=>false,
  setTimeout:fn=>{timers.set(++nextTimer,fn);return nextTimer;},clearTimeout:id=>timers.delete(id),
  document:{getElementById:element,createElement:()=>new Element(),createElementNS:()=>new Element()},
  window:{addEventListener(event,fn){(listeners[event]||=[]).push(fn);}},
  fetch:(url,options)=>url.includes('/records?')?Promise.resolve(reply(page)):url.endsWith('/grounded/jobs')?Promise.resolve(reply({jobs:[]})):new Promise((resolve,reject)=>requests.push({url,options,resolve,reject}))});
 const root=process.env.TULDOK_SOURCE_ROOT||path.resolve(__dirname,'../../../../../..');
 for(const file of ['workbench.js','instruction-responses.js','caption-proposals.js','text-classification-proposals.js'])vm.runInContext(fs.readFileSync(path.join(root,'static',file),'utf8'),context,{filename:file});
 const run=code=>vm.runInContext(code,context);Object.assign(context,{row,other,after,job,image,imageAfter,capJob});
 const take=suffix=>{const i=requests.findIndex(r=>r.url.endsWith(suffix));assert.notEqual(i,-1,`Pending request ${suffix}`);return requests.splice(i,1)[0];};
 const resolve=(suffix,data,status=200)=>take(suffix).resolve(reply(data,status));
 const button=label=>element('text-classification-proposal-jobs').children.flatMap(s=>s.children).find(e=>e.textContent===label);
 const settleShown=async(jobs=[job],parent=row)=>{resolve('/text-classification-proposals',{jobs});resolve('/responses',{parent,responses:[]});await flush();};
 for(const [key,value] of Object.entries(job.config))element('text-classification-proposal-'+({server_url:'url',instruction:'guidance'}[key]||key)).value=key==='labels'?JSON.stringify(value):String(value);
 await flush();run('showRecord(row)');await settleShown();
 return {element,requests,timers,listeners,run,take,resolve,reply,button,settleShown,context,durable};
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
 const h=await harness();const starting=h.element('text-classification-proposal-form').dispatch('submit');await flush();const start=h.take('/text-classification-proposals'),body=JSON.parse(start.options.body);
 const polling=h.run('refreshTextClassificationProposals()');h.resolve('/text-classification-proposals',{jobs:[]});await flush();h.resolve('/text-classification-proposals/'+body.request_id,{error:'Not persisted yet'},404);await polling;
 assert.equal(h.run('textClassificationProposalPendingRequest.request_id'),body.request_id);start.reject(Error('Lost acknowledgement'));await starting;
 const repeating=h.element('text-classification-proposal-form').dispatch('submit');await flush();const repeat=h.take('/text-classification-proposals');assert.deepEqual(JSON.parse(repeat.options.body),body);repeat.resolve(h.reply({error:'Earlier admission unknown'},409));await repeating;
 assert.equal(h.run('textClassificationProposalPendingRequest.request_id'),body.request_id);h.element('text-classification-proposal-labels').value='["other"]';await h.element('text-classification-proposal-form').dispatch('submit');assert.equal(h.requests.length,0,'Changed intent cannot escape unknown admission');
}
async function formChangeFencesApplyAcknowledgement(){
 const h=await harness();const applying=h.button('Apply as draft').dispatch('click');const held=h.take('/text-classification-proposals/decide/'+job.id);h.element('text-classification-proposal-labels').value='["new"]';await h.element('text-classification-proposal-labels').dispatch('input');
 held.resolve(h.reply({record:after,job:{...job,status:'applied'},changed:true}));await flush();h.resolve('/text-classification-proposals',{jobs:[{...job,status:'applied'}]});await applying;assert.equal(h.run('current.revision'),1);assert.equal(h.element('text-classification-proposal-labels').value,'["new"]');
}
async function recoveryControlsPreserveEditorsAndFenceLoads(){
 const h=await harness();h.context.pending={source_id:row.id,revision:row.revision,source_revision:row.source_revision,...job.config,request_id:'e'.repeat(32)};
 h.run('localStorage.setItem(textClassificationProposalStorageKey,JSON.stringify({schema_version:1,body:pending}));textClassificationProposalRestoreStorage();syncTextClassificationProposalRecovery();editResponse()');h.element('response-completion').value='Keep exact later answer\r\ne\u0301 😀';await h.element('response-completion').dispatch('input');const owner=h.run('({editor:editorEpoch,response:responseEditEpoch,id:responseEditor.id})');
 await h.element('text-classification-proposal-restore').dispatch('click');assert.equal(h.run('editorEpoch'),owner.editor);assert.equal(h.run('responseEditEpoch'),owner.response);assert.equal(h.run('responseEditor.id'),owner.id);assert.equal(h.run('responseDirty'),true);assert.equal(h.element('response-completion').value,'Keep exact later answer\r\ne\u0301 😀');assert.equal(h.requests.length,0);
 await h.element('text-classification-proposal-open-pending').dispatch('click');assert.equal(h.requests.length,0,'Discard refusal does not send source navigation');h.run('responseDirty=false');const opening=h.element('text-classification-proposal-open-pending').dispatch('click');const held=h.take('/records/'+row.id);h.run('editResponse()');h.element('response-completion').value='Later answer while source load held';await h.element('response-completion').dispatch('input');held.resolve(h.reply(row));await opening;assert.equal(h.run('responseDirty'),true);assert.equal(h.element('response-completion').value,'Later answer while source load held');
 const catalog=h.element('text-classification-proposal-models').dispatch('click');const models=h.take('/api/generation/prompt-models');await h.element('text-classification-proposal-restore').dispatch('click');models.resolve(h.reply({models:[{id:'stale-model',name:'Stale'}]}));await catalog;assert.equal(h.element('text-classification-proposal-model').value,'fixture');assert.equal(h.element('text-classification-proposal-model').children[0].value,'fixture');assert.equal(h.requests.length,0);
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
const image={...other,kind:'image',task:'image_caption',text:undefined,width:100,height:50};
const imageAfter={...image,revision:2,annotation:{caption:'Draft model caption'},review:'draft'};
const capJob={id:'f'.repeat(32),revision:3,status:'completed',source:image,annotation:{caption:'Draft model caption'},config:{server_url:'http://127.0.0.1:23457',model:'caption-fixture',instruction:'Exact visible pixel guidance',seed:41},error:''};
const capButton=(h,label)=>h.element('caption-proposal-jobs').children.flatMap(s=>s.children).find(e=>e.textContent===label);
async function showImage(h,jobs=[capJob]){Object.assign(h.context,{image,imageAfter,capJob});h.run('showRecord(image)');h.resolve('/caption-proposals',{jobs});await flush();}
function fillCaption(h){for(const [field,value] of Object.entries({url:capJob.config.server_url,model:capJob.config.model,guidance:capJob.config.instruction,seed:String(capJob.config.seed)}))h.element('caption-proposal-'+field).value=value;}
async function typedFormsAndPanelsRemainDisjoint(){
 const h=await harness();fillCaption(h);await h.element('caption-proposal-form').dispatch('submit');assert.equal(h.requests.length,0);assert.equal(h.element('caption-proposal-panel').hidden,true);assert.equal(h.element('text-classification-proposal-panel').hidden,false);
 await showImage(h);await h.element('text-classification-proposal-form').dispatch('submit');assert.equal(h.requests.length,0);assert.equal(h.element('caption-proposal-panel').hidden,false);assert.equal(h.element('text-classification-proposal-panel').hidden,true);
 assert.equal(h.run('captionProposalRecoveryKey===textClassificationProposalStorageKey'),false);
}
async function simultaneousPendingNamespacesAndIndependentRecovery(){
 const h=await harness();const classification=h.element('text-classification-proposal-form').dispatch('submit');await flush();const classPost=h.take('/text-classification-proposals');const classBody=JSON.parse(classPost.options.body);classPost.reject(Error('Synthetic lost classification acknowledgement'));await classification;
 await showImage(h);fillCaption(h);const caption=h.element('caption-proposal-form').dispatch('submit');const capPost=h.take('/caption-proposals');const capBody=JSON.parse(capPost.options.body);capPost.reject(Error('Synthetic lost caption acknowledgement'));await caption;
 assert.equal(h.durable.size,2);assert.notEqual(capBody.request_id,classBody.request_id);const classRaw=h.durable.get('tuldok.text-classification-proposals.admission.v1');
 const recovery=h.run('refreshCaptionProposals()');h.resolve('/caption-proposals',{jobs:[{...capJob,id:capBody.request_id}]});await recovery;assert.equal(h.run('captionProposalPendingRequest'),null);assert.equal(h.durable.get('tuldok.text-classification-proposals.admission.v1'),classRaw);
 const uncertain=h.run('refreshTextClassificationProposals()');h.resolve('/text-classification-proposals',{jobs:[]});await flush();h.resolve('/text-classification-proposals/'+classBody.request_id,{error:'Early404'},404);await uncertain;
 assert.equal(h.run('textClassificationProposalPendingRequest.request_id'),classBody.request_id);assert.equal(h.element('text-classification-proposal-panel').hidden,false);assert.equal(h.run('current.id'),image.id);assert.equal(h.requests.length,0);
}
async function captionApplyAcknowledgementCannotReplaceLaterTextAnswer(){
 const h=await harness();await showImage(h);const applying=capButton(h,'Apply as draft').dispatch('click');const held=h.take('/caption-proposals/decide/'+capJob.id);
 const opening=h.run('openRecord(row.id)');h.resolve('/records/'+row.id,row);await opening;await h.settleShown();h.run('editResponse()');h.element('response-completion').value='Later exact answer\r\n😀';await h.element('response-completion').dispatch('input');const owner=h.run('responseIntentEpoch()');
 held.resolve(h.reply({record:imageAfter,job:{...capJob,status:'applied'},changed:true}));await flush();h.resolve('/caption-proposals',{jobs:[{...capJob,status:'applied'}]});await applying;
 assert.equal(h.run('current.id'),row.id);assert.equal(h.run('responseIntentEpoch()'),owner);assert.equal(h.run('responseDirty'),true);assert.equal(h.element('response-completion').value,'Later exact answer\r\n😀');assert.equal(h.element('caption-proposal-panel').hidden,true);
}
async function classificationApplyAcknowledgementCannotReplaceLaterImageEdits(){
 const h=await harness();const applying=h.button('Apply as draft').dispatch('click');const held=h.take('/text-classification-proposals/decide/'+job.id);
 const opening=h.run('openRecord(image.id)');h.resolve('/records/'+image.id,image);await opening;h.resolve('/caption-proposals',{jobs:[capJob]});await flush();h.element('caption').value='Later human caption 😀';await h.element('editor').dispatch('input');const epoch=h.run('editorEpoch');
 held.resolve(h.reply({record:after,job:{...job,status:'applied'},changed:true}));await flush();h.resolve('/text-classification-proposals',{jobs:[{...job,status:'applied'}]});await applying;
 assert.equal(h.run('current.id'),image.id);assert.equal(h.run('editorEpoch'),epoch);assert.equal(h.run('dirty'),true);assert.equal(h.element('caption').value,'Later human caption 😀');assert.equal(h.element('caption-proposal-panel').hidden,false);
}
async function captionRejectCannotStealIndependentAnnotationSave(){
 const h=await harness();await showImage(h);h.element('caption').value='Explicit human saved caption';await h.element('editor').dispatch('input');const saving=h.element('editor').dispatch('submit');const save=h.take('/records/'+image.id),epoch=h.run('editorEpoch');
 const rejecting=capButton(h,'Reject caption proposal').dispatch('click');const held=h.take('/caption-proposals/decide/'+capJob.id);held.resolve(h.reply({record:null,job:{...capJob,status:'rejected'}}));await flush();h.resolve('/caption-proposals',{jobs:[{...capJob,status:'rejected'}]});await rejecting;assert.equal(h.run('editorEpoch'),epoch);
 save.resolve(h.reply({...imageAfter,annotation:{caption:'Explicit human saved caption'}}));await flush();h.resolve('/caption-proposals',{jobs:[{...capJob,status:'rejected'}]});await saving;assert.equal(h.run('current.id'),image.id);assert.equal(h.element('caption').value,'Explicit human saved caption');assert.equal(h.run('dirty'),false);
}
(async()=>{let failed=0;for(const test of [typedFormsAndPanelsRemainDisjoint,simultaneousPendingNamespacesAndIndependentRecovery,captionApplyAcknowledgementCannotReplaceLaterTextAnswer,classificationApplyAcknowledgementCannotReplaceLaterImageEdits,captionRejectCannotStealIndependentAnnotationSave,recoveryControlsPreserveEditorsAndFenceLoads,summaryProjectionAllowsApply,requestedGatewayNormalizationKeepsApply,frozenChoiceAndSourceFences,admissionUnknownRetainsIdentity,formChangeFencesApplyAcknowledgement,lateResponseDraftFencesApply,rejectCannotAcquireEitherEditor,answerSaveDuringApplyKeepsExactParent,navigationAndLateEvidence,terminalAbstentionNeverOffersApply]){try{await test();console.log(test.name+' passed');}catch(error){failed++;console.error(test.name+': '+error.stack);}}if(failed)process.exitCode=1;})().catch(error=>{console.error(error.stack);process.exitCode=1});
