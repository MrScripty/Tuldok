// Independent review reproductions: real production controllers, deterministic transport order.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const sourceRoot=path.resolve(process.env.TULDOK_SOURCE_ROOT||path.join(__dirname,'..'));
class Element {
  constructor(id=''){this.id=id;this.value='';this.dataset={};this.listeners={};this.children=[];this.files=[];this.classList={toggle(){}};}
  addEventListener(event,fn){(this.listeners[event] ||= []).push(fn);}
  replaceChildren(...children){this.children=children;}
  append(...children){this.children.push(...children);}
  setAttribute(){}
  matches(selector){return selector==='form'&&['editor','filters'].includes(this.id);}
  querySelectorAll(){return [];}
  async dispatch(event){for(const fn of this.listeners[event]||[])await fn({preventDefault(){},currentTarget:this});}
}
const response=data=>({ok:true,json:async()=>data});
const emptyPage={items:[],total:0,analysis:{records:0,unlabeled:0,protected_groups:0,duplicate_content_records:0,unknown_rights:0,labels:{}}};
const record=(id,revision=1)=>({id,revision,source_revision:1,name:id,kind:'text',text:'Source '+id,
  task:'text_classification',annotation:{label:'target'},groups:['group-'+id],review:'human_reviewed',provenance:{rights:'owned'}});
const fixed=row=>({id:'fixed-set',name:'fixed set',revision:1,member_count:1,items:[row],mode:'fixed'});
const loaded=set=>({selection:set,members:[{item:set.items[0],status:'ok'}],current:true});
const flush=()=>new Promise(resolve=>setImmediate(resolve));
function setup(hash='') {
  const elements=new Map(),requests=[];
  const element=id=>{if(!elements.has(id))elements.set(id,new Element(id));return elements.get(id);};
  const context=vm.createContext({console,URLSearchParams,structuredClone,setTimeout,clearTimeout,location:{hash},
    history:{pushState(){}},confirm:()=>true,
    document:{getElementById:element,createElement:()=>new Element(),createElementNS:()=>new Element()},window:{addEventListener(){}},
    fetch:(url,options)=>url.includes('/records?')?Promise.resolve(response(emptyPage)):
      url.endsWith('/grounded/jobs')?Promise.resolve(response({jobs:[]})):
      new Promise(resolve=>requests.push({url,options,resolve}))
  });
  for(const file of ['workbench.js','saved-selections.js'])vm.runInContext(fs.readFileSync(path.join(sourceRoot,'static',file),'utf8'),context);
  const run=code=>vm.runInContext(code,context);
  const resolve=(suffix,data)=>{const i=requests.findIndex(r=>r.url.endsWith(suffix));assert.notEqual(i,-1,'Pending '+suffix);requests.splice(i,1)[0].resolve(response(data));};
  return {context,element,requests,run,resolve};
}
async function delayedInitialListing() {
  const f=setup('#selection=fixed-set');f.context.manual=record('manual');f.context.saved=fixed(record('stored'));
  f.run('selected.set(manual.id,manual);selection()');
  f.resolve('/selections',{selections:[f.context.saved]});await flush();
  if(f.requests.some(r=>r.url.endsWith('/fixed-set'))) {f.resolve('/fixed-set',loaded(f.context.saved));await flush();}
  assert.equal(f.run('[...selected.keys()].join()'),'manual','A delayed initial list must not reopen over newer manual membership');
  assert.equal(f.requests.length,0);
}
async function delayedInitialListingAfterClear() {
  const f=setup('#selection=fixed-set');const saved=fixed(record('stored'));
  await f.element('clear-selection').dispatch('click');
  f.resolve('/selections',{selections:[saved]});await flush();
  if(f.requests.some(r=>r.url.endsWith('/fixed-set'))) {f.resolve('/fixed-set',loaded(saved));await flush();}
  assert.equal(f.run('selected.size'),0,'Explicit clear revokes URL auto-open even when membership was already empty');
}
async function pendingEditorSaveAfterFixedOpen() {
  const f=setup(),original=record('member');f.context.original=original;
  f.resolve('/selections',{selections:[fixed(original)]});await flush();
  f.run('selected.set(original.id,original);selection();showRecord(original)');
  f.element('label').value='new target';f.element('record-review').value='human_reviewed';
  const saving=f.element('editor').dispatch('submit');
  const opening=f.run('openSavedSelection("fixed-set")');f.resolve('/fixed-set',loaded(fixed(original)));await opening;
  f.resolve('/records/member',{...original,revision:2,annotation:{label:'new target'}});await saving;
  assert.equal(f.run('selected.get("member").revision'),1,'Earlier save completion must retain fixed revision 1');
  assert.equal(f.run('releaseBody().items[0].revision'),1,'Final release body must keep the stale fixed pair, not the eligible current pair');
  assert.equal(f.run('current.revision'),2,'Annotation save can still succeed independently of release selection');
  assert.equal(f.requests.length,0);
  // Explicit Select page is the existing user action for adopting current pairs.
  f.context.latest={...original,revision:2};f.run('page.items=[latest]');await f.element('select-page').dispatch('click');
  assert.equal(f.run('releaseBody().items[0].revision'),2,'Explicit reselection can adopt the saved revision');
}
async function ordinaryEditorSaveKeepsCurrentIntent() {
  const f=setup(),original=record('member');f.context.original=original;
  f.resolve('/selections',{selections:[]});await flush();
  f.run('selected.set(original.id,original);selection();showRecord(original)');
  f.element('record-review').value='human_reviewed';const saving=f.element('editor').dispatch('submit');
  f.resolve('/records/member',{...original,revision:2});await saving;
  assert.equal(f.run('releaseBody().items[0].revision'),2,'A save still owns the exact current pair it observed without intervening selection intent');
}
async function laterSaveCannotAdoptAlreadyStalePair() {
  const f=setup(),original=record('member');f.context.original=original;f.context.newer=record('member',2);
  f.resolve('/selections',{selections:[]});await flush();
  f.run('selected.set(original.id,original);selection();showRecord(newer)');
  const saving=f.element('editor').dispatch('submit');f.resolve('/records/member',record('member',3));await saving;
  assert.equal(f.run('releaseBody().items[0].revision'),1,'Saving a newer editor record does not imply adoption by an already stale fixed pair');
}
async function explicitClearCancelsPendingEmptyOpen() {
  const f=setup();f.resolve('/selections',{selections:[]});await flush();
  const opening=f.run('openSavedSelection("fixed-set")');await f.element('clear-selection').dispatch('click');
  assert.equal(f.run('savedLoadBusy'),false,'Explicit clear cancels an open even when the map stays empty');
  f.resolve('/fixed-set',loaded(fixed(record('stored'))));await opening;assert.equal(f.run('selected.size'),0);
}
async function samePairReselectionInvalidatesKnownStalePreview() {
  const f=setup(),original=record('member');f.context.original=original;
  f.resolve('/selections',{selections:[]});await flush();
  f.run('selected.set(original.id,original);selection();showRecord(original);releasePreview={eligible:true,preview_token:"a".repeat(64)};releaseKey=JSON.stringify(releaseBody());releaseButtons()');
  assert.equal(f.element('freeze-release').disabled,false);
  f.element('label').value='new target';f.element('record-review').value='human_reviewed';
  const saving=f.element('editor').dispatch('submit');
  f.run('page.items=[original]');await f.element('select-page').dispatch('click');
  assert.equal(f.run('selected.get("member").revision'),1);
  assert.equal(f.run('releasePreview.eligible'),true,'Same pair stays cached until newer revision is known');
  f.resolve('/records/member',{...original,revision:2,annotation:{label:'new target'}});await saving;
  assert.equal(f.run('current.revision'),2);
  assert.equal(f.run('releaseBody().items[0].revision'),1,'Earlier save does not substitute the reselected fixed pair');
  assert.equal(f.run('releasePreview'),null,'Known stale selected pair invalidates cached proof');
  assert.equal(f.element('freeze-release').disabled,true,'Known staleness disables Freeze immediately');
}
async function olderSaveCannotInvalidateNewerSelectedProof() {
  const f=setup(),original=record('member');f.context.original=original;f.context.newer=record('member',3);
  f.resolve('/selections',{selections:[]});await flush();
  f.run('selected.set(original.id,original);selection();showRecord(original)');
  const saving=f.element('editor').dispatch('submit');
  f.run('selected.set(newer.id,newer);selection(true);releasePreview={eligible:true,preview_token:"b".repeat(64)};releaseKey=JSON.stringify(releaseBody());releaseButtons()');
  f.resolve('/records/member',record('member',2));await saving;
  assert.equal(f.run('releaseBody().items[0].revision'),3);
  assert.equal(f.run('releasePreview.eligible'),true,'An older completion does not prove a newer selected pair stale');
  assert.equal(f.element('freeze-release').disabled,false);
}
(async()=>{
  let failed=false;
  for(const test of [delayedInitialListing,delayedInitialListingAfterClear,pendingEditorSaveAfterFixedOpen,ordinaryEditorSaveKeepsCurrentIntent,laterSaveCannotAdoptAlreadyStalePair,explicitClearCancelsPendingEmptyOpen,samePairReselectionInvalidatesKnownStalePreview,olderSaveCannotInvalidateNewerSelectedProof]) {
    try{await test();console.log('PASS',test.name);}catch(error){failed=true;console.error('FAIL',test.name,error.message);}
  }
  if(failed)process.exitCode=1;
})().catch(error=>{console.error(error);process.exitCode=1;});
