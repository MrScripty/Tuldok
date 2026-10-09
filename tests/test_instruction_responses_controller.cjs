'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
 constructor(id=''){this.id=id;this.value='';this.hidden=false;this.disabled=false;this.children=[];this.listeners={};this.dataset={};this.files=[];this.classList={toggle(){}};}
 addEventListener(name,fn){(this.listeners[name]??=[]).push(fn);}setAttribute(){}append(...children){this.children.push(...children);}replaceChildren(...children){this.children=children;}
 matches(selector){return selector==='form'&&['editor','import-form','filters'].includes(this.id);}querySelectorAll(){return [];}
 async dispatch(name){for(const fn of this.listeners[name]||[])await fn({preventDefault(){},currentTarget:this});if(this['on'+name])return this['on'+name]();}
 click(){return this.dispatch('click');}
}
const elements=new Map(),get=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
const requests=[],context=vm.createContext({console,document:{createElement:()=>new Element()},$:get,crypto:{randomUUID:()=> 'c'.repeat(32)},structuredClone,Blob,URL:{createObjectURL:()=>'/blob',revokeObjectURL(){}},confirm:()=>true,dirty:false,current:null,notice:message=>get('notice').textContent=message,
 api:(url,body)=>new Promise((resolve,reject)=>requests.push({url,body,resolve,reject}))});
const run=expression=>vm.runInContext(expression,context),json=expression=>JSON.parse(JSON.stringify(run(expression))),flush=()=>new Promise(resolve=>setImmediate(resolve));
function resolve(url,value){const index=requests.findIndex(request=>request.url===url);assert.notEqual(index,-1,'Expected '+url);requests.splice(index,1)[0].resolve(value);}
const parent={id:'1'.repeat(32),revision:3,source_revision:1,kind:'text'},a={id:'a'.repeat(32),prompt_id:parent.id,revision:1,completion:'\ufeff exact\r\ne\u0301  ',review:'human_reviewed'},b={...a,id:'b'.repeat(32),completion:'Sibling'};
context.fixture={parent,a,b};context.current=parent;
for(const [id,value]of [['response-train',100],['response-validation',0],['response-test',0],['response-seed',42]])get(id).value=String(value);
vm.runInContext(fs.readFileSync('static/instruction-responses.js','utf8'),context);
async function parentLoadRaces(){
 // Exercise the real parent controller and response owner together, with held HTTP results.
 const nodes=new Map(),element=id=>{if(!nodes.has(id))nodes.set(id,new Element(id));return nodes.get(id);};
 const pending=[],record={...parent,name:'Prompt',text:'Prompt text',task:'text_entities',annotation:{spans:[{label:'entity',start:0,end:6}]},groups:['family'],review:'human_reviewed',provenance:{method:'import'}};
 const other={...record,id:'2'.repeat(32),name:'Other prompt',revision:4};
 const page={items:[],total:0,analysis:{records:0,unlabeled:0,protected_groups:0,duplicate_content_records:0,unknown_rights:0,labels:{}}};
 let confirms=0,acceptDiscard=true;
 const response=data=>({ok:true,json:async()=>data});
 const env=vm.createContext({console,URLSearchParams,structuredClone,setTimeout,clearTimeout,Blob,URL,crypto:{randomUUID:()=> 'd'.repeat(32)},
  confirm:()=>{++confirms;return acceptDiscard;},fixture:{record,other,a},window:{addEventListener(){}},
  document:{getElementById:element,querySelectorAll:()=>[],createElement:()=>new Element(),createElementNS:()=>new Element()},
  fetch:(url,options)=>url.endsWith('/grounded/jobs')?Promise.resolve(response({jobs:[]})):url.includes('/records?')?Promise.resolve(response(page)):url.endsWith('/responses')?Promise.resolve(response({parent:record,responses:[a]})):new Promise(resolve=>pending.push({url,options,resolve}))});
 const evaluate=code=>vm.runInContext(code,env);
 for(const script of ['workbench','instruction-responses'])vm.runInContext(fs.readFileSync('static/'+script+'.js','utf8'),env);
 await flush();
 for(const operation of ['navigation','reload','annotation-save','import'])for(const intent of ['completion','review']){
  evaluate('showRecord(fixture.record)');await flush();evaluate('editResponse(fixture.a)');confirms=0;
  element('import-text').value='Imported prompt';
  const loading=operation==='navigation'?evaluate('openRecord(fixture.other.id)'):element(operation==='reload'?'reload':operation==='import'?'import-form':'editor').dispatch(operation==='reload'?'click':'submit');
  assert.equal(pending.length,1,operation+' starts one held parent result');
  const annotationEpoch=evaluate('editorEpoch'),editor=evaluate('responseEditor');
  if(intent==='completion'){element('response-completion').value=JSON.stringify('Later unsaved\r\n😀 ');await element('response-completion').dispatch('input');}
  else{element('response-review').value='draft';await element('response-review').dispatch('change');}
  const text=element('response-completion').value,review=element('response-review').value;
  assert.equal(evaluate('editorEpoch'),annotationEpoch,'Answer intent retains its own epoch');
  pending.shift().resolve(response(operation==='navigation'||operation==='import'?other:{...record,revision:4}));await loading;await flush();
  assert.equal(evaluate('current.id'),record.id,operation+' cannot replace a newer answer '+intent);
  assert.equal(evaluate('current.revision'),record.revision);assert.equal(evaluate('responseParent.revision'),record.revision);
  assert.equal(evaluate('responseEditor'),editor);assert.equal(evaluate('responseDirty'),true);assert.equal(evaluate('dirty'),false);
  assert.equal(element('response-form').hidden,false);assert.equal(element('response-completion').value,text);assert.equal(element('response-review').value,review);
  assert.equal(confirms,0,'A clean editor did not pre-authorize discarding later intent');assert.equal(pending.length,0);
 }
 // A discard decision applies only to the draft seen at request time, even for review ABA.
 evaluate('showRecord(fixture.record)');await flush();evaluate('editResponse(fixture.a)');
 element('response-review').value='draft';await element('response-review').dispatch('change');confirms=0;
 const approved=element('reload').dispatch('click');assert.equal(confirms,1);
 element('response-review').value='human_reviewed';await element('response-review').dispatch('change');
 element('response-review').value='draft';await element('response-review').dispatch('change');
 pending.shift().resolve(response({...record,revision:4}));await approved;
 assert.equal(evaluate('current.revision'),3);assert.equal(evaluate('responseDirty'),true);assert.equal(confirms,1,'No implicit second discard decision');
 acceptDiscard=false;await evaluate('openRecord(fixture.other.id)');assert.equal(pending.length,0);assert.equal(evaluate('current.id'),record.id);
 // Explicit retry/discard without newer edits still opens and resets the intended editor.
 acceptDiscard=true;const retry=evaluate('openRecord(fixture.record.id)');pending.shift().resolve(response({...record,revision:4}));await retry;await flush();
 assert.equal(evaluate('current.revision'),4);assert.equal(evaluate('responseDirty'),false);assert.equal(element('response-form').hidden,true);
 console.log('Held navigation, reload, annotation-save and import preserve newer answer typing/review; separate owners, review ABA, discard refusal and explicit retry passed.');
}
(async()=>{
 run('showResponses(fixture.parent)');resolve('records/'+parent.id+'/responses',{parent,responses:[a,b]});await flush();
 run('editResponse(fixture.a)');assert.equal(get('response-entry-format').value,'json');assert.equal(run('responseCompletion()'),a.completion);
 get('response-entry-format').value='text';await get('response-entry-format').dispatch('change');assert.equal(get('response-entry-format').value,'json');assert.equal(run('responseCompletion()'),a.completion);
 let checkbox=get('response-list').children[0].children[0];checkbox.checked=true;await checkbox.dispatch('change');const fixed=json('responseReleaseBody().items');assert.equal(fixed[0].revision,1);
 const preview=get('response-preview').dispatch('click');await get('response-preview').dispatch('click');assert.equal(requests.length,1,'Repeated preview remains fenced');
 run('responseSelected.set(fixture.b.id,responsePair(fixture.b,fixture.parent));responseSelectionChanged()');resolve('releases/preview',{eligible:true,lineage:[],warnings:[],split_report:{actual_counts:{train:1},actual_unique_prompt_counts:{train:1}},preview_token:'1'.repeat(64),example_count:1,unique_prompt_count:1});await preview;assert.equal(run('responsePreview'),null,'Obsolete selected membership cannot adopt proof');
 run('responseSelected.delete(fixture.b.id);responseSelectionChanged()');let pending=get('response-preview').dispatch('click');resolve('releases/preview',{eligible:true,lineage:[],warnings:[],split_report:{actual_counts:{train:1},actual_unique_prompt_counts:{train:1}},preview_token:'2'.repeat(64),example_count:1,unique_prompt_count:1});await pending;
 get('response-completion').value=JSON.stringify('Saved exact\r\n');await get('response-completion').dispatch('input');assert.equal(get('response-review').value,'draft');get('response-review').value='human_reviewed';await get('response-review').dispatch('change');
 const saving=get('response-form').dispatch('submit');await get('response-form').dispatch('submit');assert.equal(requests.length,1,'Repeated save cannot issue another mutation');assert.equal(requests[0].body.completion,'Saved exact\r\n');assert.equal(requests[0].body.parent_revision,3);
 get('response-completion').value=JSON.stringify('Later unsaved 😀 ');await get('response-completion').dispatch('input');const changed={...a,revision:2,completion:'Saved exact\r\n'};resolve('responses',{response:changed,parent,changed:true});await flush();resolve('records/'+parent.id+'/responses',{parent,responses:[changed,b]});await saving;
 assert.equal(run('responseCompletion()'),'Later unsaved 😀 ');assert.equal(run('responseDirty'),true);assert.equal(run('responseEditor.revision'),2);assert.equal(get('response-review').value,'draft');assert.deepEqual(json('responseReleaseBody().items'),fixed,'Saved response never silently refreshes fixed pairs');assert.equal(run('responsePreview'),null);
 await get('response-cancel').dispatch('click');assert.equal(run('responseDirty'),false);run('editResponse(fixture.b)');
 pending=get('response-preview').dispatch('click');resolve('releases/preview',{eligible:true,lineage:[],warnings:[],split_report:{actual_counts:{train:1},actual_unique_prompt_counts:{train:1}},preview_token:'3'.repeat(64),example_count:1,unique_prompt_count:1});await pending;
 get('response-completion').value='Updated sibling';await get('response-completion').dispatch('input');const siblingSave=get('response-form').dispatch('submit');resolve('responses',{response:{...b,revision:2,completion:'Updated sibling',review:'draft'},parent,changed:true});await flush();
 // The server re-read also finds the selected A pair stale and must invalidate it.
 resolve('records/'+parent.id+'/responses',{parent,responses:[changed,{...b,revision:2,completion:'Updated sibling',review:'draft'}]});await siblingSave;assert.equal(run('responsePreview'),null);
 await get('response-clear').dispatch('click');checkbox=get('response-list').children[0].children[0];checkbox.checked=true;await checkbox.dispatch('change');const currentPairs=json('responseReleaseBody().items');
 let releaseFile;get('response-selection-file').files=[{size:100,text:()=>new Promise(resolve=>releaseFile=resolve)}];const opening=get('response-selection-file').dispatch('change');await get('response-clear').dispatch('click');checkbox.checked=true;await checkbox.dispatch('change');assert.deepEqual(json('responseReleaseBody().items'),currentPairs);
 releaseFile(JSON.stringify({schema_version:1,format:'text_instruction_selection_v1',items:[{...currentPairs[0],id:b.id}]}));await opening;assert.deepEqual(json('responseReleaseBody().items'),currentPairs,'Later same-pair selection intent owns delayed file results');
 pending=get('response-preview').dispatch('click');resolve('releases/preview',{eligible:true,lineage:[],warnings:[],split_report:{actual_counts:{train:1},actual_unique_prompt_counts:{train:1}},preview_token:'4'.repeat(64),example_count:1,unique_prompt_count:1});await pending;
 const freezing=get('response-release-form').dispatch('submit');await get('response-release-form').dispatch('submit');assert.equal(requests.length,1);assert.equal(requests[0].body.preview_token,'4'.repeat(64));requests.shift().reject(Error('Release preview changed.'));await freezing;
 assert.equal(run('responseReleaseBusy'),false);assert.equal(run('responsePreview'),null);assert.equal(get('response-freeze').disabled,true);assert.equal(get('response-preview-status').textContent,'Release preview changed.');
 assert.deepEqual(requests,[]);await parentLoadRaces();console.log('Response controller exact Unicode, review reset, repeated mutations, late edits, fixed-pair ownership, delayed file ABA intent and stale-proof invalidation passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
