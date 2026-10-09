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
  context.record={id:'a'.repeat(32),kind:'image',name:'source.png',revision:2,source_revision:1,annotation:{label:'stored'},task:'image_classification',groups:['source'],review:'human_reviewed',provenance:{method:'import'}};
  run('showRecord(record);selected.set(record.id,record);selection()');
  element('label').value='keep unsaved';await element('editor').dispatch('input');
  const pairs=run('JSON.stringify([...selected.values()])');
  element('release-format').value='image_classification_v1';await element('release-format').dispatch('change');
  assert.equal(element('classification-export-help').hidden,false);assert.equal(element('caption-export-help').hidden,true);
  assert.equal(run('dirty'),true);assert.equal(element('label').value,'keep unsaved');assert.equal(element('record-review').value,'draft');
  assert.equal(run('JSON.stringify([...selected.values()])'),pairs);
  element('train').value='34';element('validation').value='33';element('test').value='33';element('split-seed').value='42';
  const result={format:'image_classification_v1',eligible:true,selected_count:6,preview_token:'1'.repeat(64),
    blockers:[],warnings:['Repeated examples retained.'],lineage:[],split_report:null,
    class_coverage:[{label:'<img src=x onerror=alert(1)>',folder:'class_000000',index:0,counts:{train:1,validation:1,test:1}}]};
  let preview=element('preview-release').dispatch('click');await element('preview-release').dispatch('click');
  assert.equal(requests.length,1);
  assert.equal(JSON.parse(requests[0].options.body).format,'image_classification_v1');
  element('release-format').value='canonical_v1';await element('release-format').dispatch('change');
  resolve(result);await preview;
  assert.equal(run('releasePreview'),null);assert.equal(element('freeze-release').disabled,true);
  assert.equal(element('release-preview').children.length,0,'Stale classifier preview cannot repaint another format');
  element('release-format').value='image_classification_v1';await element('release-format').dispatch('change');
  preview=element('preview-release').dispatch('click');resolve(result);await preview;
  assert.equal(element('freeze-release').disabled,false);
  const coverage=element('release-preview').children.find(row=>row.textContent?.includes('class_000000'));
  assert.ok(coverage.textContent.includes('<img src=x onerror=alert(1)>'));assert.equal(coverage.innerHTML,undefined);
  assert.ok(coverage.textContent.includes('train: 1 · validation: 1 · test: 1'));
  const freeze=element('release-form').dispatch('submit');await element('release-form').dispatch('submit');assert.equal(requests.length,1);
  assert.equal(JSON.parse(requests[0].options.body).preview_token,result.preview_token);
  resolve({format:'image_classification_v1',url:'/fixture.zip',records:6,split_report:{actual_counts:{train:2,validation:2,test:2}},warnings:['Repeated examples retained.']});await freeze;
  assert.ok(element('notice').textContent.includes('export warnings'));assert.ok(!element('notice').textContent.includes('small-image'));
  assert.equal(element('label').value,'keep unsaved');assert.equal(run('JSON.stringify([...selected.values()])'),pairs);
  preview=element('preview-release').dispatch('click');resolve({...result,eligible:false,preview_token:null,blockers:[{message:'Missing coverage: test/class_000000'}]});await preview;
  assert.equal(element('freeze-release').disabled,true);
  await element('release-form').dispatch('submit');assert.equal(requests.length,0);
  console.log('Classifier controller: safe coverage text, exact format/token transport, dirty editor/fixed selection preservation, stale preview, repeated submit and blocker fencing passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
