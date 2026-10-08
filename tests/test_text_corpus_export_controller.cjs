// Deterministic controller checks complement, but do not replace, browser QA.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
class Element {
  constructor(id=''){this.id=id;this.value='';this.dataset={};this.listeners={};this.children=[];this.files=[];this.classList={toggle(){}};}
  addEventListener(event,fn){(this.listeners[event]||=[]).push(fn);}
  replaceChildren(...children){this.children=children;}
  append(...children){this.children.push(...children);}
  setAttribute(){}
  matches(selector){return selector==='form'&&['editor','import-form','filters','generate-form','release-form'].includes(this.id);}
  querySelectorAll(){return [];}
  async dispatch(event){for(const fn of this.listeners[event]||[])await fn({preventDefault(){},currentTarget:this});}
}
const elements=new Map(),element=id=>{if(!elements.has(id))elements.set(id,new Element(id));return elements.get(id);};
const requests=[],response=data=>({ok:true,json:async()=>data});
const page={items:[],total:0,analysis:{records:0,unlabeled:0,protected_groups:0,duplicate_content_records:0,unknown_rights:0,labels:{}}};
const context=vm.createContext({console,URLSearchParams,structuredClone,setTimeout,clearTimeout,confirm:()=>false,
  document:{querySelectorAll:()=>[],getElementById:element,createElement:()=>new Element(),createElementNS:()=>new Element()},window:{addEventListener(){}},
  fetch:(url,options)=>url.endsWith('/grounded/jobs')&&!options?.method?Promise.resolve(response({jobs:[]})):url.includes('/records?')?Promise.resolve(response(page)):new Promise(resolve=>requests.push({url,options,resolve}))});
vm.runInContext(fs.readFileSync(path.join(process.env.TULDOK_SOURCE_ROOT||path.resolve(__dirname,'..'),'static/workbench.js'),'utf8'),context);
const run=code=>vm.runInContext(code,context);
const resolve=data=>requests.shift().resolve(response(data));
(async()=>{
  await Promise.resolve();
  context.record={id:'a'.repeat(32),kind:'text',name:'source.txt',revision:2,source_revision:1,text:'Stored corpus text',annotation:{note:'stored'},task:'text_corpus',groups:['source'],review:'human_reviewed',provenance:{method:'import'}};
  // A previously reviewed class is not itself a corpus review decision.
  context.oldRecord={...context.record,task:'text_classification',annotation:{label:'approved class'}};
  run('showRecord(oldRecord)');
  element('task').value='text_corpus';await element('task').dispatch('change');
  assert.equal(element('record-review').value,'draft');
  assert.equal(element('corpus-note').value,'');
  assert.equal(element('corpus-controls').hidden,false);
  element('corpus-note').value='Explicit new corpus review';element('record-review').value='human_reviewed';
  const save=element('editor').dispatch('submit');
  assert.equal(requests.length,1);
  const savedBody=JSON.parse(requests[0].options.body);
  assert.equal(savedBody.task,'text_corpus');assert.deepEqual(savedBody.annotation,{note:'Explicit new corpus review'});
  assert.equal(savedBody.review,'human_reviewed');
  resolve({...context.record,revision:3,annotation:savedBody.annotation});await save;
  assert.equal(element('corpus-note').value,'Explicit new corpus review');
  run('showRecord(record);selected.set(record.id,record);selection()');
  element('corpus-note').value='keep unsaved';await element('editor').dispatch('input');
  const pairs=run('JSON.stringify([...selected.values()])');
  element('release-format').value='text_corpus_v1';await element('release-format').dispatch('change');
  assert.equal(element('corpus-export-help').hidden,false);assert.equal(element('caption-export-help').hidden,true);
  assert.equal(run('dirty'),true);assert.equal(element('corpus-note').value,'keep unsaved');assert.equal(element('record-review').value,'draft');
  assert.equal(run('JSON.stringify([...selected.values()])'),pairs);
  element('train').value='34';element('validation').value='33';element('test').value='33';element('split-seed').value='42';
  const result={format:'text_corpus_v1',eligible:true,selected_count:6,preview_token:'1'.repeat(64),
    blockers:[],warnings:['Repeated examples retained.'],lineage:[],split_report:null,
    corpus_counts:{train:{bytes:151,document_bytes:149,separator_bytes:2,documents:1,families:1}},artifact_bytes:12000};
  let preview=element('preview-release').dispatch('click');await element('preview-release').dispatch('click');
  assert.equal(requests.length,1);
  assert.equal(JSON.parse(requests[0].options.body).format,'text_corpus_v1');
  element('release-format').value='canonical_v1';await element('release-format').dispatch('change');
  resolve(result);await preview;
  assert.equal(run('releasePreview'),null);assert.equal(element('freeze-release').disabled,true);
  assert.equal(element('release-preview').children.length,0,'Stale corpus preview cannot repaint another format');
  element('release-format').value='text_corpus_v1';await element('release-format').dispatch('change');
  preview=element('preview-release').dispatch('click');resolve(result);await preview;
  assert.equal(element('freeze-release').disabled,false);
  const coverage=element('release-preview').children.find(row=>row.textContent?.includes('train.txt'));
  assert.ok(coverage.textContent.includes('151 bytes · 1 documents · 1 connected families'));assert.equal(coverage.innerHTML,undefined);
  assert.ok(coverage.textContent.includes('149 document bytes + 2 separator bytes'));
  const freeze=element('release-form').dispatch('submit');await element('release-form').dispatch('submit');assert.equal(requests.length,1);
  assert.equal(JSON.parse(requests[0].options.body).preview_token,result.preview_token);
  resolve({format:'text_corpus_v1',url:'/fixture.zip',records:6,split_report:{actual_counts:{train:2,validation:2,test:2}},warnings:['Repeated examples retained.']});await freeze;
  assert.ok(element('notice').textContent.includes('export warnings'));assert.ok(!element('notice').textContent.includes('small-image'));
  assert.equal(element('corpus-note').value,'keep unsaved');assert.equal(run('JSON.stringify([...selected.values()])'),pairs);
  preview=element('preview-release').dispatch('click');resolve({...result,eligible:false,preview_token:null,blockers:[{message:'train.txt requires more than 128 bytes'}]});await preview;
  assert.equal(element('freeze-release').disabled,true);
  await element('release-form').dispatch('submit');assert.equal(requests.length,0);
  console.log('Corpus controller: byte/document/family counts, exact format/token transport, dirty editor/fixed selection preservation, stale preview, repeated submit and blocker fencing passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
