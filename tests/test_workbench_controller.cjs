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
vm.runInContext(fs.readFileSync(path.join(process.env.TULDOK_SOURCE_ROOT||path.resolve(__dirname,'..'),'static/workbench.js'),'utf8'),context);
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
  assert.equal(run('releaseBusy'),true);
  assert.equal(element('release-form').dataset.busy,undefined,'The release handler does not use generic form dataset state');
  assert.equal(element('preview-release').disabled,true);
  await element('preview-release').dispatch('click');assert.equal(requests.length,1,'Pending stale export fences an early preview request');
  assert.equal(run('releasePreview.preview_token'),'a'.repeat(64),'Old eligibility persists until the stale response is handled');
  resolve('/releases',{error:'Release preview changed.',code:'conflict'},false);await failing;
  assert.equal(run('releaseBusy'),false);assert.equal(run('releasePreview'),null);assert.equal(element('freeze-release').disabled,true);
  assert.equal(element('release-preview-status').textContent,'Release preview changed.');
  assert.equal(element('preview-release').disabled,false);
  const refreshed=element('preview-release').dispatch('click');assert.equal(requests.length,1);assert.ok(requests[0].url.endsWith('/releases/preview'));
  resolve('/releases/preview',{...eligible,preview_token:'b'.repeat(64)});await refreshed;
  assert.equal(run('releaseBusy'),false);assert.equal(run('releasePreview.preview_token'),'b'.repeat(64));assert.equal(element('freeze-release').disabled,false);
  const finalExport=element('release-form').dispatch('submit');assert.equal(JSON.parse(requests[0].options.body).preview_token,'b'.repeat(64));
  resolve('/releases',{url:'/current.zip',records:2,split_report:{actual_counts:{train:2}}});await finalExport;
  assert.equal(element('release-result').children[0].href,'/current.zip');
  run('selected.clear();selection()');assert.equal(element('preview-release').disabled,true);assert.equal(element('release-result').children.length,0);
  assert.equal(requests.length,0);
  // Explicit metadata criteria travel independently of exact selected pairs and proof.
  const queries=[];context.fetch=(url,options)=>new Promise(resolve=>queries.push({url,options,resolve}));
  element('label-filter').value='cat & café +😀';element('group-filter').value='source &😀';element('rights-filter').value='unknown';
  context.fixture=record('fixed');context.proof=eligible;
  run('selected.set(fixture.id,fixture);selection();releasePreview=proof;releaseKey=JSON.stringify(releaseBody())');
  const olderFilter=run('refresh()');
  const criteria=new URL(queries[0].url,'http://localhost').searchParams;
  assert.equal(criteria.get('label'),'cat & café +😀');assert.equal(criteria.get('group'),'source &😀');assert.equal(criteria.get('rights'),'unknown');
  element('label-filter').value='new criterion';const newerFilter=run('refresh()');
  queries[1].resolve(response({...page,total:1,items:[{...record('visible-new'),rights_note:'unknown'}]}));await newerFilter;
  queries[0].resolve(response({...page,total:99,items:[{...record('obsolete-row'),rights_note:'old note'}]}));await olderFilter;
  assert.equal(run('page.total'),1,'Delayed obsolete criteria cannot replace newer results');
  assert.equal(element('label-filter').value,'new criterion');
  assert.equal(run('[...selected.keys()].join()'),'fixed');assert.equal(run('selected.get("fixed").revision'),1);
  assert.equal(run('releasePreview===proof'),true,'Filtering grants no proof and preserves an existing exact proof');
  assert.ok(element('records').children[0].children[1].children[1].textContent.includes('Rights note: unknown'));
  element('exact-filter-format').value='json';
  for(const value of ['ordinary', 'left\nright', 'left\rright', 'left\r\nright', 'literal\\n and "quotes"', 'valid 😀 pair']) {
    for(const key of ['label','group','rights']) element(key+'-filter').value=JSON.stringify(value);
    const filtering=run('refresh()'), query=queries.at(-1);
    const sent=new URL(query.url,'http://localhost').searchParams;
    for(const key of ['label','group','rights'])assert.equal(sent.get(key),value,'Exact '+key+' codepoints survive JSON entry');
    query.resolve(response(page));await filtering;
    assert.equal(run('[...selected.keys()].join()'),'fixed');assert.equal(run('releasePreview===proof'),true);
  }
  const count=queries.length;
  for(const invalid of ['not JSON', 'null', '5', '[]', '"raw\nnewline"', '"unterminated']) {
    element('rights-filter').value=invalid;
    await assert.rejects(run('refresh()'),/Rights note.*JSON string/);
    assert.equal(queries.length,count,'Invalid JSON never dispatches a query');
    assert.equal(run('releasePreview===proof'),true);
  }
  for(const key of ['label','group','rights']) {
    for(const field of ['label','group','rights'])element(field+'-filter').value='';
    for(const invalid of ['\ud800','\udfff','a\ud800b','\ud800\ud800','\udc00\ud800']) {
      element(key+'-filter').value=JSON.stringify(invalid);
      const filtering=run('refresh()');
      if(queries.length!==count)queries.at(-1).resolve(response(page));
      await assert.rejects(filtering,/unpaired surrogate/);
      assert.equal(queries.length,count,'Malformed Unicode is rejected before URLSearchParams can replace it');
      assert.equal(run('[...selected.keys()].join()'),'fixed');assert.equal(run('releasePreview===proof'),true);
    }
  }
  element('exact-filter-format').value='text';
  for(const key of ['label','group','rights']) {
    for(const field of ['label','group','rights'])element(field+'-filter').value='';
    element(key+'-filter').value='\ud800';await assert.rejects(run('refresh()'),/unpaired surrogate/);
    assert.equal(queries.length,count,'Plain malformed Unicode is rejected too');
  }
  console.log('Controller navigation, exact-release fencing and explicit metadata filter transport/ordering passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
