// Deterministic transport ordering; real rendering is covered by browser_saved_selections.cjs.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
class Element {
  constructor(id='') {this.id=id;this.value='';this.dataset={};this.listeners={};this.children=[];this.files=[];this.classList={toggle(){}};}
  addEventListener(event,fn){(this.listeners[event] ||= []).push(fn);}
  replaceChildren(...children){this.children=children;}
  append(...children){this.children.push(...children);}
  setAttribute(){}
  matches(selector){return selector==='form'&&this.id.endsWith('form');}
  querySelectorAll(){return [];}
  async dispatch(event){for(const fn of this.listeners[event]||[])await fn({preventDefault(){},currentTarget:this});}
}
const elements=new Map(),element=id=>{if(!elements.has(id))elements.set(id,new Element(id));return elements.get(id);};
const requests=[],windowEvents={},historyEntries=[],location={hash:''};
const response=data=>({ok:true,json:async()=>data});
const page={items:[],total:0,analysis:{records:0,unlabeled:0,protected_groups:0,duplicate_content_records:0,unknown_rights:0,labels:{}}};
let list=[],allowDelete=true;
const context=vm.createContext({console,URLSearchParams,structuredClone,setTimeout,clearTimeout,location,
  history:{pushState(_state,_title,hash){historyEntries.push(hash);location.hash=hash;}},confirm:()=>allowDelete,
  document:{getElementById:element,createElement:()=>new Element(),createElementNS:()=>new Element()},
  window:{addEventListener(event,fn){(windowEvents[event] ||= []).push(fn);}},
  fetch:(url,options)=>url.endsWith('/grounded/jobs')&&!options?.method?Promise.resolve(response({jobs:[]})):
    url.includes('/records?')?Promise.resolve(response(page)):
    url.endsWith('/selections')&&!options?.method?Promise.resolve(response({selections:list})):
    new Promise(resolve=>requests.push({url,options,resolve}))
});
for(const file of ['workbench.js','saved-selections.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../static',file),'utf8'),context);
const run=code=>vm.runInContext(code,context);
const resolve=(suffix,data,ok=true)=>{const i=requests.findIndex(r=>r.url.endsWith(suffix));assert.notEqual(i,-1,'Pending '+suffix);requests.splice(i,1)[0].resolve({...response(data),ok});};
const record=id=>({id,revision:1,source_revision:1,name:id,kind:'text'});
const set=(id,item)=>({id,name:id,revision:1,member_count:1,items:[record(item)],mode:'fixed'});
const load=set=>({selection:set,members:[{item:set.items[0],status:'ok'}],current:true});
const flush=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
  await flush();element('train').value='100';element('validation').value='0';element('test').value='0';element('split-seed').value='7';
  const first=set('first','a'),second=set('second','b');list=[first,second];await run('refreshSavedSets()');
  context.fixture=record('chosen');run('selected.set(fixture.id,fixture);selection()');
  element('selection-name').value='saved while pending';
  const saving=element('save-selection-form').dispatch('submit');
  await element('save-selection-form').dispatch('submit');assert.equal(requests.length,1,'Repeated save is suppressed');
  const body=JSON.parse(requests[0].options.body);assert.deepEqual(body.items,[{id:'chosen',revision:1,source_revision:1}]);
  run('selected.clear();selection()');resolve('/selections',first);await saving;
  assert.equal(run('selected.size'),0,'Save never restores older membership');
  assert.equal(run('releasePreview'),null,'Save grants no export proof');
  // A cancelled open can be retried immediately; its late response has no authority.
  const opening=run('openSavedSelection("first")');
  await run('openSavedSelection("first")');assert.equal(requests.length,1,'Repeated open is suppressed');
  await element('cancel-selection-load').dispatch('click');assert.equal(run('savedLoadBusy'),false);
  const newer=run('openSavedSelection("second")');
  resolve('/second',load(second));await newer;resolve('/first',load(first));await opening;
  assert.equal(run('[...selected.keys()].join()'),'b');assert.equal(location.hash,'#selection=second');
  assert.equal(run('releasePreview'),null);assert.equal(element('freeze-release').disabled,true);
  // Selection changes revoke a pending open even when a refresh finishes later.
  const pending=run('openSavedSelection("first")');
  context.fixture=record('manual');run('selected.clear();selected.set(fixture.id,fixture);selection()');
  resolve('/first',load(first));await pending;assert.equal(run('[...selected.keys()].join()'),'manual');
  // Filters are independent of membership and do not revoke a legitimate open.
  const filtering=run('openSavedSelection("first")');element('query').value='new filter';await run('refresh()');
  resolve('/first',{...load(first),current:false,members:[{item:first.items[0],status:'stale',message:'Changed.'}]});await filtering;
  assert.equal(element('query').value,'new filter');assert.equal(run('selected.get("a").revision'),1);
  assert.ok(element('saved-selection-issues').children[0].textContent.includes('stale'));
  assert.equal(element('freeze-release').disabled,true);
  // Navigation away fences an outstanding response, without clearing annotation edits.
  const leaving=run('openSavedSelection("second")');run('dirty=true');
  for(const fn of windowEvents.pagehide)fn({});resolve('/second',load(second));await leaving;
  assert.equal(run('[...selected.keys()].join()'),'a');assert.equal(run('dirty'),true);
  location.hash='';for(const fn of windowEvents.popstate)fn({});await flush();assert.equal(run('selected.size'),0);
  location.hash='#selection=second';for(const fn of windowEvents.popstate)fn({});await flush();
  resolve('/second',load(second));await flush();assert.equal(run('[...selected.keys()].join()'),'b');
  // Cancellation before delete has no HTTP effects; a conflict preserves the set.
  element('saved-selection').value='second';allowDelete=false;await element('delete-selection').dispatch('click');assert.equal(requests.length,0);
  allowDelete=true;const deleting=element('delete-selection').dispatch('click');
  resolve('/second/delete',{error:'Saved selection changed.'},false);await deleting;
  assert.equal(run('savedSets.has("second")'),true);assert.equal(run('[...selected.keys()].join()'),'b');
  assert.ok(element('notice').textContent.includes('Saved selection changed'));
  // Returning from the back/forward cache without a saved URL preserves manual membership.
  location.hash='';for(const fn of windowEvents.pageshow)fn({persisted:true});await flush();
  assert.equal(run('[...selected.keys()].join()'),'b');assert.equal(run('releasePreview'),null);
  assert.equal(requests.length,0);
  console.log('Fixed save/open, repeated actions, cancellation, delayed selection fencing, filters, page navigation and deletion conflicts passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
