'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
class Element{
 constructor(id=''){this.id=id;this.value='';this.hidden=false;this.disabled=false;this.children=[];this.listeners={};this.dataset={};this.files=[];this.classList={toggle(){}};}
 addEventListener(name,fn){(this.listeners[name]??=[]).push(fn);}setAttribute(){}append(...children){this.children.push(...children);}replaceChildren(...children){this.children=children;}
 matches(selector){return selector==='form'&&['editor','import-form','filters'].includes(this.id);}querySelectorAll(){return [];}
 async dispatch(name){for(const fn of this.listeners[name]||[])await fn({preventDefault(){},currentTarget:this});if(this['on'+name])return this['on'+name]();}
 click(){return this.dispatch('click');}
}
const elements=new Map(),get=id=>{if(!elements.has(id))elements.set(id,new Element(id));return elements.get(id);};
const requests=[],context=vm.createContext({console,document:{createElement:()=>new Element()},$:get,crypto:{randomUUID:()=> 'c'.repeat(32)},structuredClone,confirm:()=>true,dirty:false,responseDirty:false,responseBusy:false,current:null,notice:message=>get('notice').textContent=message,
 api:(url,body)=>new Promise((resolve,reject)=>requests.push({url,body,resolve,reject}))});
const run=expression=>vm.runInContext(expression,context),json=expression=>JSON.parse(JSON.stringify(run(expression))),flush=()=>new Promise(resolve=>setImmediate(resolve));
function resolve(url,value){const index=requests.findIndex(request=>request.url===url);assert.notEqual(index,-1,'Expected '+url);requests.splice(index,1)[0].resolve(value);}
const parent={id:'1'.repeat(32),revision:3,source_revision:1,kind:'text'},a={id:'a'.repeat(32),prompt_id:parent.id,revision:1,completion:' left\r\ne\u0301 ',review:'human_reviewed'},b={...a,id:'b'.repeat(32),completion:'right',review:'draft'};
const judgment={id:'d'.repeat(32),revision:1,prompt_id:parent.id,parent_revision:2,source_revision:1,left_id:a.id,left_revision:1,right_id:b.id,right_revision:1,outcome:'right',rationale:'First review',review:'human_reviewed',deleted:false,stale_warning:'Stale prompt'};
context.fixture={parent,a,b,judgment};context.current=parent;
for(const [id,value]of [['preference-train',100],['preference-validation',0],['preference-test',0],['preference-seed',42]])get(id).value=String(value);
vm.runInContext(fs.readFileSync('static/preferences.js','utf8'),context);
async function load(){run('showPreferences(fixture.parent)');resolve('records/'+parent.id+'/preferences',{parent,judgments:[judgment],responses:[a,b]});await flush();}
async function parentLoadRaces(){
 const nodes=new Map(),element=id=>{if(!nodes.has(id))nodes.set(id,new Element(id));return nodes.get(id);};
 const pending=[],record={...parent,name:'Prompt',text:'Prompt text',task:'text_classification',annotation:{label:'class'},groups:['family'],review:'human_reviewed',provenance:{method:'import'}};
 const other={...record,id:'2'.repeat(32),name:'Other prompt',revision:4};
 const page={items:[],total:0,analysis:{records:0,unlabeled:0,protected_groups:0,duplicate_content_records:0,unknown_rights:0,labels:{}}};
 let confirms=0,answers=[a,b],judgments=[{...judgment,parent_revision:record.revision,stale_warning:null}];
 const response=data=>({ok:true,json:async()=>data});
 const env=vm.createContext({console,URLSearchParams,structuredClone,setTimeout,clearTimeout,Blob,URL,crypto:{randomUUID:()=> 'e'.repeat(32)},
  confirm:()=>{++confirms;return true;},fixture:{record,other,a,b,judgment:{...judgment,parent_revision:record.revision,stale_warning:null}},window:{addEventListener(){}},
  document:{getElementById:element,querySelectorAll:()=>[],createElement:()=>new Element(),createElementNS:()=>new Element()},
  fetch:(url,options)=>url.endsWith('/grounded/jobs')?Promise.resolve(response({jobs:[]})):url.includes('/records?')?Promise.resolve(response(page)):url.endsWith('/responses')&&!options?.method?Promise.resolve(response({parent:record,responses:answers})):url.endsWith('/preferences')&&!options?.method?Promise.resolve(response({parent:record,responses:answers,judgments})):new Promise(resolve=>pending.push({url,options,resolve}))});
 const evaluate=code=>vm.runInContext(code,env);
 for(const script of ['workbench','instruction-responses','preferences','rights-note'])vm.runInContext(fs.readFileSync('static/'+script+'.js','utf8'),env);
 await flush();
 for(const operation of ['navigation','reload','annotation-save','import','rights-save'])for(const intent of ['left','right','outcome','rationale','review']){
  evaluate('showRecord(fixture.record)');await flush();evaluate('editPreference(fixture.judgment)');confirms=0;
  element('import-text').value='Imported prompt';element('rights-note-value').value='Authored';
  const loading=operation==='navigation'?evaluate('openRecord(fixture.other.id)'):element(operation==='reload'?'reload':operation==='import'?'import-form':operation==='rights-save'?'rights-note-form':'editor').dispatch(operation==='reload'?'click':'submit');
  assert.equal(pending.length,1,operation+' starts held parent operation');
  const annotationEpoch=evaluate('editorEpoch'),responseEpoch=evaluate('responseEditEpoch'),editor=evaluate('preferenceEditor');
  element('preference-'+intent).value=intent==='rationale'?'Later unsaved rationale':intent==='review'?'draft':intent==='outcome'?'tie':intent==='left'?b.id:a.id;
  await element('preference-'+intent).dispatch(intent==='rationale'?'input':'change');
  const text=element('preference-rationale').value,review=element('preference-review').value;
  assert.equal(evaluate('editorEpoch'),annotationEpoch);assert.equal(evaluate('responseEditEpoch'),responseEpoch,'Judgment retains its own intent epoch');
  const saved=operation==='rights-save'?{record:{...record,revision:4},changed:true}:operation==='navigation'||operation==='import'?other:{...record,revision:4};
  pending.shift().resolve(response(saved));await loading;await flush();
  assert.equal(evaluate('current.id'),record.id);assert.equal(evaluate('current.revision'),record.revision);
  assert.equal(evaluate('preferenceEditor'),editor);assert.equal(evaluate('preferenceDirty'),true);assert.equal(element('preference-rationale').value,text);assert.equal(element('preference-review').value,review);assert.equal(confirms,0);assert.equal(pending.length,0);
 }
 const held=evaluate('preferenceEditor');element('rights-note-value').value='Changed note';await element('rights-note-form').dispatch('submit');assert.equal(pending.length,0,'Rights save cannot discard an existing dirty judgment');assert.equal(evaluate('preferenceEditor'),held);assert.equal(evaluate('preferenceDirty'),true);assert.match(element('rights-note-status').textContent,/judgment edit/);
 // Actual save owners invalidate proof for relevant local mutations, retaining later intent.
 evaluate('showRecord(fixture.record)');await flush();
 evaluate('preferenceSelected.set(fixture.judgment.id,preferencePair(fixture.judgment));preferencePreview={eligible:true};preferenceButtons()');
 const fixed=JSON.stringify(evaluate('preferenceReleaseBody().items'));
 const peer={...env.fixture.judgment,id:'f'.repeat(32),left_id:b.id,right_id:a.id,outcome:'right',review:'draft'};env.fixture.peer=peer;
 evaluate('editPreference(fixture.peer)');element('preference-review').value='human_reviewed';await element('preference-review').dispatch('change');
 const saving=evaluate('mutatePreference()');assert.equal(pending.length,1);
 element('preference-rationale').value='Later comparative draft';await element('preference-rationale').dispatch('input');
 const reviewed={...peer,revision:2,review:'human_reviewed'};judgments=[env.fixture.judgment,reviewed];pending.shift().resolve(response({changed:true,judgment:reviewed}));await saving;await flush();
 assert.equal(evaluate('preferencePreview'),null,'Unselected opposing review invalidates proof');assert.equal(element('preference-freeze').disabled,true);
 assert.equal(evaluate('preferenceDirty'),true);assert.equal(element('preference-rationale').value,'Later comparative draft');assert.equal(element('preference-review').value,'draft');
 assert.equal(JSON.stringify(evaluate('preferenceReleaseBody().items')),fixed);
 evaluate('showRecord(fixture.record)');await flush();evaluate('preferencePreview={eligible:true};preferenceButtons();editResponse(fixture.a)');
 element('response-completion').value=JSON.stringify(a.completion+' changed');await element('response-completion').dispatch('input');
 const answerSaving=element('response-form').dispatch('submit');assert.equal(pending.length,1);
 evaluate('editPreference(fixture.judgment)');element('preference-rationale').value='Draft during answer acknowledgment';await element('preference-rationale').dispatch('input');
 const updated={...a,revision:2,completion:a.completion+' changed',review:'draft'};answers=[updated,b];pending.shift().resolve(response({changed:true,response:updated,parent:record}));await answerSaving;await flush();
 assert.equal(evaluate('preferencePreview'),null,'Actual bound-answer save invalidates proof');assert.equal(element('preference-freeze').disabled,true);
 assert.equal(evaluate('preferenceDirty'),true);assert.equal(element('preference-rationale').value,'Draft during answer acknowledgment');assert.equal(evaluate('preferenceBody().left_revision'),1,'Later draft retains its opened answer revision');
 assert.equal(JSON.stringify(evaluate('preferenceReleaseBody().items')),fixed);
 evaluate('preferencePreview={eligible:true};preferenceResponseSaved({id:"unrelated"})');assert.equal(evaluate('preferencePreview.eligible'),true);
 for(const field of ['prompt_id','parent_revision','source_revision','left_revision','right_revision']){
  env.fixture.unrelated={...peer,[field]:field==='prompt_id'?'9'.repeat(32):2};assert.equal(evaluate('preferenceJudgmentAffectsSelection(fixture.unrelated)'),false,'Different '+field+' preserves proof');
 }
 // A no-op answer acknowledgment cannot revoke a proof.
 await element('preference-cancel').dispatch('click');const noOp=element('response-form').dispatch('submit');assert.equal(pending.length,1);
 pending.shift().resolve(response({changed:false,response:updated,parent:record}));await noOp;assert.equal(evaluate('preferencePreview.eligible'),true);

}
(async()=>{
 await load();run('editPreference(fixture.judgment)');assert.equal(get('preference-review').value,'draft','Stale judgment requires fresh review');
 let checkbox=get('preference-list').children[0].children[0];checkbox.checked=true;await checkbox.dispatch('change');const fixed=json('preferenceReleaseBody().items');assert.equal(fixed[0].parent_revision,2,'Selection uses stored bindings, never refreshed parent');
 get('preference-outcome').value='left';await get('preference-outcome').dispatch('change');get('preference-review').value='human_reviewed';await get('preference-review').dispatch('change');
 run('mutatePreference()');run('mutatePreference()');assert.equal(requests.length,1,'Repeated save issues one mutation');assert.equal(requests[0].body.parent_revision,3,'Only deliberate rejudgment binds current parent');
 get('preference-rationale').value='Later local intent';await get('preference-rationale').dispatch('input');const saved={...judgment,revision:2,parent_revision:3,outcome:'left',rationale:'First review',stale_warning:null};resolve('preferences',{judgment:saved,changed:true});await flush();resolve('records/'+parent.id+'/preferences',{parent,judgments:[saved],responses:[a,b]});await flush();
 assert.equal(run('preferenceDirty'),true);assert.equal(get('preference-rationale').value,'Later local intent');assert.equal(get('preference-review').value,'draft');assert.equal(run('preferenceEditor.revision'),2);assert.deepEqual(json('preferenceReleaseBody().items'),fixed);
 await get('preference-cancel').dispatch('click');run('editPreference(fixture.judgment)');
 const loading=run('loadPreferences(fixture.parent)');get('preference-rationale').value='Typed during list read';await get('preference-rationale').dispatch('input');resolve('records/'+parent.id+'/preferences',{parent,judgments:[saved],responses:[{...a,revision:2},b]});await loading;assert.equal(get('preference-rationale').value,'Typed during list read');assert.equal(run('preferenceEditor.parent_revision'),2,'List read never rebases editor');assert.equal(run('preferenceBody().left_revision'),1,'Retained editor never binds an unseen newer answer from a list refresh');
 // Selection invalidation rejects held proof and freezes repeated exports once.
 const preview=get('preference-preview').dispatch('click');await get('preference-preview').dispatch('click');assert.equal(requests.length,1);run('preferenceSelectionChanged()');resolve('releases/preview',{eligible:true,preview_token:'1'.repeat(64)});await preview;assert.equal(run('preferencePreview'),null);
 let pending=get('preference-preview').dispatch('click');resolve('releases/preview',{eligible:true,preview_token:'2'.repeat(64)});await pending;
 const freezing=get('preference-release-form').dispatch('submit');await get('preference-release-form').dispatch('submit');assert.equal(requests.length,1);requests.shift().reject(Error('Stale judgment'));await freezing;assert.equal(run('preferencePreview'),null);assert.equal(get('preference-freeze').disabled,true);assert.match(get('preference-preview-output').textContent,/Stale/);
 assert.equal(requests.length,0);
 run('preferenceRows=[{...fixture.judgment,deleted:true}];renderPreferences()');const deletedHistory=get('preference-list').children[0].children[1].onclick();
 run('showPreferences(fixture.parent)');resolve('records/'+parent.id+'/preferences',{parent,judgments:[],responses:[a,b]});await flush();resolve('preference-history/'+judgment.id,{history:[judgment]});await deletedHistory;assert.equal(get('preference-history-output').hidden,true,'Late deleted history cannot paint a replaced editor');
 await parentLoadRaces();console.log('PASS judgment controller stored binding, review reset, repeated saves, later intent, list/preview races and every parent-adopter ownership interleaving, relevant local saves/no-op and dirty-draft preservation.');
})().catch(error=>{console.error(error);process.exitCode=1;});
