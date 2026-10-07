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
const report=path.dirname(__filename),sourceStart={head:execFileSync('git',['rev-parse','HEAD'],{cwd:'/workspace/Tuldok',encoding:'utf8'}).trim(),sha256:crypto.createHash('sha256').update(fs.readFileSync('/workspace/Tuldok/static/text-classification-proposals.js')).digest('hex')};
(async()=>{
 const h=await harness();h.run('editPreference({...fixture.judgment,review:"draft"})');const original=JSON.parse(h.run('JSON.stringify(preferenceEditor)'));
 const applying=h.apply(),applyRequest=h.take('/text-classification-proposals/decide/'+job.id);const applied=h.adopt();
 const saving=h.mutate(),saveRequest=h.take('/preferences');saveRequest.resolve(response({error:'Backend applied classification first; exact old parent revision is stale.'},false,409));await saving;
 const beforeACK=JSON.parse(h.run('JSON.stringify({current,editor:preferenceEditor,busy:preferenceBusy,dirty:preferenceDirty,epoch:preferenceEditEpoch,status:document.getElementById("preference-editor-status").textContent})'));
 assert.equal(beforeACK.busy,false);assert.deepEqual(beforeACK.editor,original);assert.equal(beforeACK.current.revision,1);
 applyRequest.resolve(response(applied));await applying;
 const afterACK=JSON.parse(h.run('JSON.stringify({current,editor:preferenceEditor,busy:preferenceBusy,dirty:preferenceDirty,epoch:preferenceEditEpoch,status:document.getElementById("preference-editor-status").textContent})'));
 const result={sourceStart,original,beforeACK,afterACK,failedEditorRetained:afterACK.editor?.id===original.id,fixAdvice:'Advance preferenceEditEpoch at every explicit validated save/delete dispatch; Apply already captures shared responseIntentEpoch. Keep preflight busy guard.',findings:afterACK.editor?.id===original.id?[]:['Late Apply acknowledgement clears failed clean judgment editor after its409 settles busyfalse']};fs.writeFileSync(path.join(report,'settled409_before_applyACK_receipt.json'),JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify({sourceStart,failedEditorRetained:result.failedEditorRetained,beforeBusy:beforeACK.busy,afterEditor:afterACK.editor,findings:result.findings},null,2));
 assert.equal(result.failedEditorRetained,true,'A failed explicit judgment save is newer editor ownership even after its request settles');
})().catch(e=>{console.error(e.stack);process.exitCode=1;});
