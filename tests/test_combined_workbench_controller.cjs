// Actual composed controllers: independent answer drafts across other owners.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),crypto=require('node:crypto');
class Element {
 constructor(){this.value='';this.dataset={};this.listeners={};this.children=[];this.classList={toggle(){}};}
 addEventListener(event,fn){(this.listeners[event]||=[]).push(fn);}
 replaceChildren(...children){this.children=children;}append(...children){this.children.push(...children);}setAttribute(){}matches(){return false;}querySelectorAll(){return [];}
 async dispatch(event){for(const fn of this.listeners[event]||[])await fn({preventDefault(){},currentTarget:this});}
}
const row={id:'a'.repeat(32),name:'Prompt',kind:'text',task:'text_classification',review:'draft',revision:1,source_revision:1,groups:['g'],annotation:null,text:'fictional',provenance:{rights:'unknown'}};
const page={items:[],total:0,criteria:{},analysis:{records:0,unlabeled:0,protected_groups:0,duplicate_content_records:0,unknown_rights:0,labels:{}}};
const flush=()=>new Promise(resolve=>setImmediate(resolve));
async function harness(){
 const elements=new Map(),element=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);},requests=[];
 const response=(data,ok=true)=>({ok,json:async()=>data});
 const context=vm.createContext({console,URLSearchParams,structuredClone,setTimeout,clearTimeout,crypto:{randomUUID:crypto.randomUUID},confirm:()=>false,
  document:{getElementById:element,createElement:()=>new Element(),createElementNS:()=>new Element()},window:{addEventListener(){}},
  fetch:(url,options)=>url.endsWith('/grounded/jobs')?Promise.resolve(response({jobs:[]})):new Promise(resolve=>requests.push({url,options,resolve}))});
 const root=process.env.TULDOK_SOURCE_ROOT||path.resolve(__dirname,'..');
 for(const file of ['workbench.js','curation.js','rights-note.js','instruction-responses.js'])vm.runInContext(fs.readFileSync(path.join(root,'static',file),'utf8'),context);
 const run=code=>vm.runInContext(code,context);
 function resolve(suffix,data,ok=true){const i=requests.findIndex(r=>r.url.endsWith(suffix)||suffix==='/records?'&&r.url.includes(suffix));assert.notEqual(i,-1,suffix);requests.splice(i,1)[0].resolve(response(data,ok));}
 resolve('/records?',page);await flush();context.row=row;run('showRecord(row)');resolve('/responses',{parent:row,responses:[]});await flush();
 async function type(text){element('response-completion').value=text;await element('response-completion').dispatch('input');}
 return {run,context,element,requests,resolve,type};
}
async function curationLaterEdit(){
 const h=await harness();h.run('editResponse()');
 const request=h.run('curationInspect(row,curationEpoch)');await h.type('Later exact answer\r\n😀');
 const before=h.run('({id:responseEditor.id,epoch:responseEditEpoch,review:document.getElementById("response-review").value})');
 h.resolve('/records/'+row.id,row);await request;
 assert.equal(h.run('responseDirty'),true,'Diagnostic inspection must retain later response intent');
 assert.equal(h.run('responseEditor.id'),before.id);assert.equal(h.run('responseEditEpoch'),before.epoch);
 assert.equal(h.element('response-completion').value,'Later exact answer\r\n😀');assert.equal(h.element('response-review').value,before.review);
 await h.run('curationInspect(row,curationEpoch)');assert.equal(h.requests.length,0,'Discard refusal sends no inspection');
}
async function rightsLaterEdit(){
 const h=await harness();h.run('editResponse()');
 h.element('rights-note-value').value='Fixture note';await h.element('rights-note-value').dispatch('input');
 const request=h.element('rights-note-form').dispatch('submit');await h.type('Later answer during held rights save');
 const id=h.run('responseEditor.id');const corrected={...row,revision:2,provenance:{rights:'unknown',rights_note_correction:{note:'Fixture note',revision:2}}};
 h.resolve('/rights/'+row.id,{record:corrected,changed:true});await flush();h.resolve('/records?',page);await request;
 assert.equal(h.run('responseDirty'),true,'Rights acknowledgement must retain later response intent');
 assert.equal(h.run('responseEditor.id'),id);assert.equal(h.run('current.revision'),1,'No unsafe parent adoption');
 assert.equal(h.element('response-completion').value,'Later answer during held rights save');
}
async function rightsRejectsExistingDraft(){
 const h=await harness();h.run('editResponse()');await h.type('Existing unsaved answer');
 const request=h.element('rights-note-form').dispatch('submit');await flush();
 assert.equal(h.requests.length,0,'Rights correction must not discard an existing response draft');
 await request;
 assert.equal(h.run('responseDirty'),true);
}
async function rightsInvalidatesResponseProofBeforeRefresh(){
 const h=await harness();
 h.run("responseSelected.set('b'.repeat(32),{id:'b'.repeat(32),revision:1,prompt_id:row.id,parent_revision:1,source_revision:1});responsePreview={eligible:true};responseButtons()");
 const pairs=h.run('JSON.stringify([...responseSelected.values()])');
 h.element('rights-note-value').value='Fixture note';await h.element('rights-note-value').dispatch('input');
 const request=h.element('rights-note-form').dispatch('submit');
 const corrected={...row,revision:2,provenance:{rights:'unknown',rights_note_correction:{note:'Fixture note',revision:2}}};
 h.resolve('/rights/'+row.id,{record:corrected,changed:true});await flush();
 assert.equal(h.run('responsePreview'),null,'Known rights change must invalidate answer proof before the held list refresh');
 assert.equal(h.run('JSON.stringify([...responseSelected.values()])'),pairs,'Answer pairs stay fixed');
 h.resolve('/responses',{parent:corrected,responses:[]});h.resolve('/records?',page);await request;
}
async function answerSaveRejectsRightsEdit(){
 const h=await harness();h.run('editResponse()');await h.type('Keep this answer');
 h.element('rights-note-value').value='Keep this note';await h.element('rights-note-value').dispatch('input');
 await h.element('response-form').dispatch('submit');
 assert.equal(h.requests.length,0,'Answer save must not overwrite an active rights-note owner');
 assert.equal(h.run('responseDirty'),true);assert.equal(h.run('rightsDirty'),true);
 assert.equal(h.element('response-completion').value,'Keep this answer');
 assert.equal(h.element('rights-note-value').value,'Keep this note');
}
async function heldAnswerListRetainsParentUntilExplicitReload(){
 const h=await harness(),text='Later answer bound to displayed parent\r\ne\u0301 😀\ufeff';
 h.run("selected.set(row.id,{id:row.id,revision:1,source_revision:1});responseSelected.set('b'.repeat(32),{id:'b'.repeat(32),revision:1,prompt_id:row.id,parent_revision:1,source_revision:1})");
 const pairs=h.run('JSON.stringify({records:[...selected.values()],answers:[...responseSelected.values()]})');
 const loading=h.run('loadResponses(current)');h.run('editResponse()');
 h.element('rights-note-value').value='New note';await h.element('rights-note-value').dispatch('input');
 const correcting=h.element('rights-note-form').dispatch('submit');
 h.element('response-entry-format').value='json';await h.element('response-entry-format').dispatch('change');
 await h.type(JSON.stringify(text));h.element('response-review').value='human_reviewed';await h.element('response-review').dispatch('change');
 const draft=h.run('({id:responseEditor.id,epoch:responseEditEpoch})'),corrected={...row,revision:2,provenance:{rights:'unknown',rights_note_correction:{note:'New note',revision:2}}};
 h.resolve('/rights/'+row.id,{record:corrected,changed:true});await flush();h.resolve('/records?',page);await correcting;
 h.resolve('/responses',{parent:corrected,responses:[]});await loading;
 assert.equal(h.run('current.revision'),1);assert.equal(h.run('responseParent.revision'),1,'A late answer-list result must not silently rebase the draft parent');
 assert.equal(h.run('responseParent.source_revision'),1);assert.equal(h.run('responseDirty'),true);assert.equal(h.run('responseEditor.id'),draft.id);assert.equal(h.run('responseEditEpoch'),draft.epoch);
 assert.equal(h.run('responseCompletion()'),text);assert.equal(h.element('response-review').value,'human_reviewed');assert.match(h.element('response-status').textContent,/Reload/);
 await h.element('rights-note-cancel').dispatch('click');const saving=h.element('response-form').dispatch('submit');
 const body=JSON.parse(h.requests.find(request=>request.url.endsWith('/api/workbench/responses')).options.body);
 assert.equal(body.parent_revision,1,'Cancelling rights does not authorize adopting revision 2');assert.equal(body.source_revision,1);assert.equal(body.completion,text);
 h.resolve('/api/workbench/responses',{error:'Parent revision changed. Reload the prompt.'},false);await saving;
 assert.equal(h.run('responseDirty'),true);assert.equal(h.run('responseEditor.id'),draft.id);assert.equal(h.run('responseCompletion()'),text);
 await h.element('reload').dispatch('click');assert.equal(h.requests.length,0,'Discard refusal retains the draft and sends no reload');
 h.context.confirm=()=>true;
 const reload=h.element('reload').dispatch('click');h.resolve('/records/'+row.id,corrected);await reload;h.resolve('/responses',{parent:corrected,responses:[]});await flush();
 assert.equal(h.run('current.revision'),2);assert.equal(h.run('responseParent.revision'),2);assert.equal(h.run('responseDirty'),false);assert.equal(h.run('responseEditor'),null);
 h.run('editResponse()');h.element('response-entry-format').value='json';await h.element('response-entry-format').dispatch('change');await h.type(JSON.stringify(text));
 assert.equal(h.element('response-review').value,'draft','Reload never grants answer review');
 const retry=h.element('response-form').dispatch('submit'),retryBody=JSON.parse(h.requests.find(request=>request.url.endsWith('/api/workbench/responses')).options.body);
 assert.equal(retryBody.parent_revision,2);assert.equal(retryBody.source_revision,1);assert.equal(retryBody.completion,text);assert.equal(retryBody.review,'draft');
 h.resolve('/api/workbench/responses',{changed:true,response:{...retryBody,revision:1}});await flush();h.resolve('/responses',{parent:corrected,responses:[]});await retry;
 assert.equal(h.run('responseDirty'),false);assert.equal(h.run('JSON.stringify({records:[...selected.values()],answers:[...responseSelected.values()]})'),pairs,'Every save/load/retry keeps fixed pairs');
}
async function answerListRequiresExactSourceOwner(){
 const h=await harness();h.run('editResponse()');await h.type('Keep this source owner');
 h.run('responsePreview={eligible:true}');const loading=h.run('loadResponses(current)');
 h.resolve('/responses',{parent:{...row,source_revision:2},responses:[]});await loading;
 assert.equal(h.run('responseParent.source_revision'),1,'A source-only mismatch cannot rebase the draft');assert.equal(h.run('responseDirty'),true);
 assert.equal(h.run('responsePreview'),null);assert.equal(h.element('response-completion').value,'Keep this source owner');
 const matching=h.run('loadResponses(current)');h.resolve('/responses',{parent:row,responses:[]});await matching;
 assert.equal(h.run('responseDirty'),true,'An exact-owner list refresh can finish without adopting later draft intent');assert.equal(h.run('responseParent.source_revision'),1);
}
(async()=>{
 const failures=[];
 for(const test of [curationLaterEdit,rightsLaterEdit,rightsRejectsExistingDraft,rightsInvalidatesResponseProofBeforeRefresh,answerSaveRejectsRightsEdit,heldAnswerListRetainsParentUntilExplicitReload,answerListRequiresExactSourceOwner]){
  try{await test();console.log(test.name+' passed');}catch(error){failures.push(error);console.error(test.name+': '+error.message);}
 }
 if(failures.length)throw new AggregateError(failures,'Combined ownership failures');
 console.log('Combined controller ownership: delayed inspection/rights acknowledgement, discard refusal, response draft guard and fixed proof invalidation passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
