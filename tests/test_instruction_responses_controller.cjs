'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
 constructor(){this.value='';this.hidden=false;this.disabled=false;this.children=[];this.listeners={};this.dataset={};this.files=[];}
 addEventListener(name,fn){(this.listeners[name]??=[]).push(fn);}setAttribute(){}append(...children){this.children.push(...children);}replaceChildren(...children){this.children=children;}
 async dispatch(name){for(const fn of this.listeners[name]||[])await fn({preventDefault(){}});if(this['on'+name])return this['on'+name]();}
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
 assert.deepEqual(requests,[]);console.log('Response controller exact Unicode, review reset, repeated mutations, late edits, fixed-pair ownership, delayed file ABA intent and stale-proof invalidation passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
