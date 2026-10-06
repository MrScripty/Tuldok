// Deterministic controller concurrency tests; this is not browser/rendering QA.
'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
class Element {
  constructor(id='') { this.id=id; this.value=''; this.dataset={}; this.listeners={}; this.children=[]; this.files=[]; this.classList={toggle(){}}; }
  addEventListener(event,fn) { (this.listeners[event] ||= []).push(fn); }
  replaceChildren(...children) { this.children=children; }
  append(...children) { this.children.push(...children); }
  setAttribute() {}
  matches(selector) { return selector==='form' && ['editor','import-form','filters','generate-form','release-form'].includes(this.id); }
  querySelectorAll() { return []; }
  async dispatch(event) { for(const fn of this.listeners[event] || []) await fn({preventDefault(){},currentTarget:this}); }
}
const elements=new Map();
const element=id=>{if(!elements.has(id)) elements.set(id,new Element(id));return elements.get(id);};
const requests=[];
const response=data=>({ok:true,json:async()=>data});
const page={items:[],total:0,analysis:{records:0,unlabeled:0,protected_groups:0,duplicate_content_records:0,unknown_rights:0,labels:{}}};
const context=vm.createContext({console,URLSearchParams,structuredClone,setTimeout,clearTimeout,confirm:()=>true,
  document:{querySelectorAll:()=>[],getElementById:element,createElement:()=>new Element(),createElementNS:()=>new Element()},
  window:{addEventListener(){}},
  fetch:(url,options)=>url.endsWith('/grounded/jobs')&&!options?.method?Promise.resolve(response({jobs:[]})):url.includes('/records?')?Promise.resolve(response(page)):new Promise(resolve=>requests.push({url,options,resolve}))
});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/workbench.js'),'utf8'),context);
const run=code=>vm.runInContext(code,context);
const record=id=>({id,name:id,kind:'text',text:'Source '+id,task:'text_classification',annotation:{label:'original'},groups:[id],review:'draft',revision:1,source_revision:1,provenance:{method:'import'}});
const resolve=(suffix,data,ok=true)=>{const index=requests.findIndex(request=>request.url.endsWith(suffix));assert.notEqual(index,-1,'Expected pending '+suffix);requests.splice(index,1)[0].resolve({...response(data),ok});};
async function startAt(id) { context.fixture=record(id);run('showRecord(fixture)'); }
(async()=>{
  await Promise.resolve();
  await startAt('a');
  const navigation=run('openRecord("b")');
  element('label').value='unsaved edit';await element('editor').dispatch('input');
  resolve('/records/b',record('b'));await navigation;
  assert.equal(run('current.id'),'a');assert.equal(element('label').value,'unsaved edit');assert.equal(run('dirty'),true);
  // A later navigation owns the editor even when an older fetch finishes last.
  const older=run('openRecord("b")'), newer=run('openRecord("c")');
  resolve('/records/c',record('c'));await newer;resolve('/records/b',record('b'));await older;
  assert.equal(run('current.id'),'c');
  // Import may succeed in the collection without displacing later navigation/editing.
  element('import-text').value='new asset';element('import-group').value='import';element('rights').value='owned';
  const importing=element('import-form').dispatch('submit');
  const next=run('openRecord("d")');resolve('/records/d',record('d'));await next;
  element('label').value='keep this';await element('editor').dispatch('input');
  resolve('/import',record('imported'));await importing;
  assert.equal(run('current.id'),'d');assert.equal(element('label').value,'keep this');assert.equal(run('dirty'),true);
  // Edits alone, without a new navigation, invalidate an import's auto-open.
  const secondImport=element('import-form').dispatch('submit');
  element('label').value='newest edit';await element('editor').dispatch('input');
  resolve('/import',record('imported-again'));await secondImport;
  assert.equal(run('current.id'),'d');assert.equal(element('label').value,'newest edit');assert.equal(run('dirty'),true);
  // History is likewise scoped to the editor that requested it.
  const history=element('history').dispatch('click');
  const move=run('openRecord("e")');resolve('/records/e',record('e'));await move;
  resolve('/history/d',[record('d')]);await history;
  assert.equal(element('history-output').hidden,true);
  assert.equal(requests.length,0);
  // Release proof belongs to the exact saved selection and controls that requested it.
  element('train').value='100';element('validation').value='0';element('test').value='0';element('split-seed').value='7';
  context.fixture=record('selected');run('selected.set(fixture.id,fixture);selection()');
  await element('release-form').dispatch('submit');assert.equal(requests.length,0);
  const eligible={eligible:true,selected_count:1,format:'canonical_v1',preview_token:'a'.repeat(64),
    analysis:{tasks:{text_classification:1},reviews:{human_reviewed:1},labels:{one:1},unlabeled:0,empty_targets:0,duplicate_content_records:0,unknown_rights:0},
    blockers:[],warnings:['fixture warning'],lineage:[{id:'family',selected_ids:['selected'],member_ids:['selected'],deleted_ids:[],fixed_splits:[]}],
    split_report:{requested_percentages:{train:100,validation:0,test:0},actual_counts:{train:1},note:'Whole groups stay together.'}};
  const preview=element('preview-release').dispatch('click');
  await element('preview-release').dispatch('click');assert.equal(requests.length,1,'Repeated preview clicks issue one request');
  element('split-seed').value='8';await element('split-seed').dispatch('input');
  resolve('/releases/preview',eligible);await preview;
  assert.equal(run('releasePreview'),null);assert.equal(element('freeze-release').disabled,true);
  assert.equal(element('release-preview').children.length,0,'A delayed obsolete proof cannot repaint');
  const blocked=element('preview-release').dispatch('click');
  resolve('/releases/preview',{...eligible,eligible:false,preview_token:null,blockers:[{code:'conflict',message:'Selection changed.'}]});await blocked;
  assert.equal(element('freeze-release').disabled,true);
  const incomplete=element('preview-release').dispatch('click');
  resolve('/releases/preview',{...eligible,preview_token:undefined});await incomplete;
  assert.equal(element('freeze-release').disabled,true);assert.equal(run('releasePreview'),null);
  const approve=async()=>{const task=element('preview-release').dispatch('click');resolve('/releases/preview',eligible);await task;assert.equal(element('freeze-release').disabled,false);};
  await approve();await run('refresh()');assert.equal(element('freeze-release').disabled,false,'Filtering is not selection');
  context.fixture=record('new-selection');run('selected.set(fixture.id,fixture);selection()');
  assert.equal(element('freeze-release').disabled,true,'A selection change invalidates proof');
  await approve();
  element('split-seed').value='9'; // Also fence programmatic changes without an input event.
  await element('release-form').dispatch('submit');assert.equal(requests.length,0);assert.equal(element('freeze-release').disabled,true);
  await approve();
  const exporting=element('release-form').dispatch('submit');await element('release-form').dispatch('submit');
  assert.equal(requests.length,1,'Repeated export submits issue one request');
  assert.equal(JSON.parse(requests[0].options.body).preview_token,'a'.repeat(64));
  element('train').value='90';await element('train').dispatch('change');
  resolve('/releases',{url:'/old.zip',records:1,split_report:{actual_counts:{train:1}}});await exporting;
  assert.equal(element('release-result').children.length,0,'A delayed obsolete export does not claim current settings');
  assert.equal(element('freeze-release').disabled,true);
  await approve();const failing=element('release-form').dispatch('submit');
  resolve('/releases',{error:'Release preview changed.',code:'conflict'},false);await failing;
  assert.equal(run('releasePreview'),null);assert.equal(element('freeze-release').disabled,true);
  assert.equal(element('release-preview-status').textContent,'Release preview changed.');
  await approve();const finalExport=element('release-form').dispatch('submit');
  resolve('/releases',{url:'/current.zip',records:2,split_report:{actual_counts:{train:2}}});await finalExport;
  assert.equal(element('release-result').children[0].href,'/current.zip');
  run('selected.clear();selection()');assert.equal(element('preview-release').disabled,true);assert.equal(element('release-result').children.length,0);
  assert.equal(requests.length,0);
  console.log('Controller navigation/edit fencing and release preview/export freshness, changed controls and repeated actions passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
