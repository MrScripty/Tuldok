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
const context=vm.createContext({console,URLSearchParams,structuredClone,confirm:()=>true,
  document:{getElementById:element,createElement:()=>new Element(),createElementNS:()=>new Element()},
  window:{addEventListener(){}},
  fetch:(url,options)=>url.includes('/records?')?Promise.resolve(response(page)):new Promise(resolve=>requests.push({url,options,resolve}))
});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../static/workbench.js'),'utf8'),context);
const run=code=>vm.runInContext(code,context);
const record=id=>({id,name:id,kind:'text',text:'Source '+id,task:'text_classification',annotation:{label:'original'},groups:[id],review:'draft',revision:1,source_revision:1,provenance:{method:'import'}});
const resolve=(suffix,data)=>{const index=requests.findIndex(request=>request.url.endsWith(suffix));assert.notEqual(index,-1,'Expected pending '+suffix);requests.splice(index,1)[0].resolve(response(data));};
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
  console.log('Controller delayed navigation, edits, import and history fencing passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
