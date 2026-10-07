'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto');
process.env.TULDOK_SOURCE_ROOT='/workspace/Tuldok';
const {atomicIndexedDB,serializedLocks,faultStorage}=require('/workspace/scratch/tuldok-classification-preference-integration/review-interactions/candidate-c0de883159025491d5283c52514c7c762f53c4cc/qualified-atomic-helpers.cjs');
const files=['workbench.js','rights-note.js','instruction-responses.js','preferences.js','caption-proposals.js','text-classification-proposals.js'];
class Element{constructor(id=''){this.id=id;this.value='';this.dataset={};this.listeners={};this.children=[];this.classList={toggle(){}};}addEventListener(e,f){(this.listeners[e]||=[]).push(f);}append(...x){this.children.push(...x);}replaceChildren(...x){this.children=x;}setAttribute(){}matches(s){return s==='form'&&['editor','filters'].includes(this.id);}querySelectorAll(){return [];}async dispatch(e){for(const f of this.listeners[e]||[])await f({preventDefault(){},currentTarget:this});}}
const response=(data,ok=true,status=200)=>({ok,status,json:async()=>data}),flush=()=>new Promise(r=>setImmediate(r));
const row={id:'a'.repeat(32),name:'Prompt',kind:'text',task:'text_classification',text:'Exact fictional prompt.',content_hash:'text-hash',source_sha256:'original-source-hash',annotation:null,review:'human_reviewed',revision:1,source_revision:1,groups:['g'],provenance:{rights:'Authored'}};
const answers=[{id:'b'.repeat(32),revision:1,prompt_id:row.id,completion:'Answer B',review:'human_reviewed'},{id:'c'.repeat(32),revision:1,prompt_id:row.id,completion:'Answer C',review:'human_reviewed'}];
const judgment={id:'d'.repeat(32),revision:1,prompt_id:row.id,parent_revision:1,source_revision:1,left_id:answers[0].id,left_revision:1,right_id:answers[1].id,right_revision:1,outcome:'left',rationale:'Exact judged preference',review:'human_reviewed',stale_warning:null};
const config={server_url:'http://127.0.0.1:2000',model:'fixture',instruction:'Classify the exact text',seed:42,labels:['schedule','cancel']};
const job={id:'e'.repeat(32),revision:3,status:'completed',source:{...row},annotation:{label:'schedule'},config:{...config,requested_server_url:config.server_url,requested_model:config.model},error:''};delete job.source.text;
const page={items:[],total:0,criteria:{},analysis:{records:0,unlabeled:0,protected_groups:0,duplicate_content_records:0,unknown_rights:0,labels:{}}};
async function harness(shared={}){
 const dom=new Map(),get=id=>{if(!dom.has(id))dom.set(id,new Element(id));return dom.get(id);},queued=[],holds=new Set(),storage=shared.storage||faultStorage(),session=faultStorage(),database=shared.database||atomicIndexedDB(),locks=shared.locks||serializedLocks();
 let server={...row},serverAnswers=structuredClone(answers),serverJudgments=[structuredClone(judgment)];
 const context=vm.createContext({console,URL,URLSearchParams,structuredClone,crypto,localStorage:storage,sessionStorage:session,indexedDB:database,navigator:{locks},confirm:()=>true,location:{hash:''},history:{pushState(){}},setTimeout:()=>1,clearTimeout(){},document:{getElementById:get,createElement:()=>new Element(),createElementNS:()=>new Element()},window:{addEventListener(){}},fetch:(url,options={})=>{
  if(!options.method&&!holds.has(url)){
   if(url.includes('/records?'))return Promise.resolve(response(page));
   if(url.endsWith('/grounded/jobs')||url.endsWith('/caption-proposals'))return Promise.resolve(response({jobs:[]}));
   if(url.endsWith('/text-classification-proposals'))return Promise.resolve(response({jobs:[job]}));
   if(url.endsWith('/responses'))return Promise.resolve(response({parent:server,responses:serverAnswers}));
   if(url.endsWith('/preferences'))return Promise.resolve(response({parent:server,judgments:serverJudgments,responses:serverAnswers}));
  }
  return new Promise((resolve,reject)=>queued.push({url,options,resolve,reject}));
 }});
 for(const file of files)vm.runInContext(fs.readFileSync('/workspace/Tuldok/static/'+file,'utf8'),context);
 const run=code=>vm.runInContext(code,context);context.fixture={row,answers,judgment,job};run('showRecord(fixture.row)');await flush();
 for(const [key,field] of [['server_url','url'],['model','model'],['instruction','guidance'],['seed','seed'],['labels','labels']])get('text-classification-proposal-'+field).value=key==='labels'?JSON.stringify(config.labels):String(config[key]);
 assert.equal(run('textClassificationProposalAuthorityReady'),true);assert.equal(run('preferenceListBusy'),false);
 run('selected.set(fixture.row.id,{id:fixture.row.id,revision:1,source_revision:1});responseSelected.set(fixture.answers[0].id,responsePair(fixture.answers[0],fixture.row));preferenceSelected.set(fixture.judgment.id,preferencePair(fixture.judgment));preferencePreview={eligible:true,preview_token:"initial"};responsePreview={eligible:true};preferenceButtons();textClassificationProposalJobs=[fixture.job];renderTextClassificationProposals()');
 const fixed=run('JSON.stringify({records:[...selected.values()],answers:[...responseSelected.values()],judgments:[...preferenceSelected.values()]})');
 const take=suffix=>{const i=queued.findIndex(x=>x.url.endsWith(suffix));assert.notEqual(i,-1,suffix);return queued.splice(i,1)[0];};
 const button=label=>get('text-classification-proposal-jobs').children.flatMap(s=>s.children).find(b=>b.textContent===label);
 const apply=()=>button('Apply as draft').dispatch('click'),reject=()=>button('Reject classification proposal').dispatch('click');
 const mutate=(deleting=false)=>run('mutatePreference('+deleting+')');
 const adopt=()=>{server={...row,revision:2,annotation:{label:'schedule'},review:'draft'};return {record:server,job:{...job,status:'applied_draft'}};};
 return {get,context,run,queued,holds,storage,database,locks,fixed,take,apply,reject,mutate,adopt,setJudgments:x=>serverJudgments=x,setAnswers:x=>serverAnswers=x,assertFixed(){assert.equal(run('JSON.stringify({records:[...selected.values()],answers:[...responseSelected.values()],judgments:[...preferenceSelected.values()]})'),fixed);}};
}

const {execFileSync}=require('node:child_process');
const report=path.dirname(__filename),root='/workspace/Tuldok';
const source=()=>({head:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),module_sha256:crypto.createHash('sha256').update(fs.readFileSync(root+'/static/text-classification-proposals.js')).digest('hex')});
const sourceStart=source(),proofs=[];
function snapshot(h){return JSON.parse(h.run('JSON.stringify({current,editor:preferenceEditor,dirty:preferenceDirty,busy:preferenceBusy,editEpoch:preferenceEditEpoch,editorEpoch,preview:preferencePreview})'));}
(async()=>{
 for(const deleting of [false,true]){
  const h=await harness();h.run('editPreference({...fixture.judgment,review:"draft"})');const before=snapshot(h);assert.equal(before.dirty,false);const save=h.mutate(deleting),request=h.take(deleting?'/preferences/delete':'/preferences');const pending=snapshot(h);assert.equal(pending.busy,true);
  await h.apply();assert.equal(h.queued.length,0,'Apply attempted while clean judgment mutation busy must not POST');assert.deepEqual(snapshot(h),pending);assert.match(h.get('text-classification-proposal-status').textContent,/judgment save/);h.assertFixed();
  request.resolve(response({error:'Controlled exact parent CAS refusal'},false,409));await save;const settled=snapshot(h);assert.deepEqual(settled.editor,before.editor);assert.equal(settled.busy,false);assert.equal(settled.dirty,false);assert.equal(settled.current.revision,1);
  proofs.push({name:(deleting?'delete':'save')+' first clean busy blocks Apply before POST',before,pending,settled});
 }
 for(const deleting of [false,true]){
  const h=await harness();h.run('editPreference({...fixture.judgment,review:"draft"})');const before=snapshot(h);const apply=h.apply(),applyRequest=h.take('/text-classification-proposals/decide/'+job.id);const save=h.mutate(deleting),request=h.take(deleting?'/preferences/delete':'/preferences');const pending=snapshot(h);assert.equal(pending.busy,true);assert.equal(pending.dirty,false);
  const applied=h.adopt();applyRequest.resolve(response(applied));await apply;const afterApply=snapshot(h);assert.equal(afterApply.current.revision,1,'Backend draft applied; UI old current stays while judgment owns editor');assert.equal(applied.record.revision,2);assert.equal(applied.record.review,'draft');assert.deepEqual(afterApply.editor,before.editor);assert.equal(afterApply.busy,true);assert.equal(afterApply.dirty,false);assert.equal(afterApply.preview,null);assert.equal(h.get('preference-freeze').disabled,true);assert.equal(afterApply.editEpoch,before.editEpoch);h.assertFixed();
  request.resolve(response({error:'Prompt changed. Exact parent revision rejected; draft retained.'},false,409));await save;const afterRefusal=snapshot(h);assert.deepEqual(afterRefusal.editor,before.editor);assert.equal(afterRefusal.current.revision,1);assert.equal(afterRefusal.busy,false);assert.match(h.get('preference-editor-status').textContent,/Draft retained/);
  if(!deleting){const retry=h.mutate(),retryRequest=h.take('/preferences');assert.deepEqual(JSON.parse(retryRequest.options.body),JSON.parse(request.options.body),'Explicit stale save preserves exact old parent/answers; backend remains authority');retryRequest.resolve(response({error:'Parent revision still stale'},false,409));await retry;assert.deepEqual(snapshot(h).editor,before.editor);}
  proofs.push({name:'Apply first late clean '+(deleting?'delete':'save')+' keeps pending judgment owner and stale binding',before,pending,afterApply,afterRefusal});
 }
 {
  const h=await harness();h.run('editPreference({...fixture.judgment,review:"draft"})');const save=h.mutate(),request=h.take('/preferences');const epoch=h.run('editorEpoch'),before=snapshot(h);const rejecting=h.reject();h.take('/text-classification-proposals/decide/'+job.id).resolve(response({job:{...job,status:'rejected'}}));await rejecting;assert.equal(h.run('editorEpoch'),epoch);assert.deepEqual(snapshot(h),before);request.resolve(response({judgment:{...judgment,review:'draft',revision:2},changed:true}));await save;assert.equal(h.run('preferenceEditor.revision'),2);assert.equal(h.run('current.revision'),1);h.assertFixed();proofs.push({name:'Reject leaves pending clean judgment save ownership unchanged',before,after:snapshot(h)});
 }
 const sourceEnd=source();assert.deepEqual(sourceEnd,sourceStart);const result={passed:proofs.length,proofs,sourceStart,sourceEnd,sourceUnchanged:true,findings:[]};fs.writeFileSync(path.join(report,'composed_busy_receipt.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify({passed:proofs.length,sourceStart,sourceEnd,sourceUnchanged:true,findings:[]},null,2));
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
