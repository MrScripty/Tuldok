'use strict';
// Controlled transport proves presentation lifecycle only. Actual training is covered by browser_model_development.cjs.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../static/workspace-service.js'),'utf8');
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no});return {promise,resolve,reject};};
const entry=(epoch,sha)=>({checkpoint:{sha256:sha,name:'checkpoint-'+epoch+'.json'},clocks:{epoch},selected:epoch===2,state:'retained'});
const value=(sha='b')=>({state:'verified',manifest:{producer:{run_id:'run'}},checkpoint_index:{entries:[entry(1,'a'),entry(2,'b')]},probe:{members:[{ordinal:0,frozen_reference:{id:'example',revision:3,source_revision:1}}]},observations:[{checkpoint_sha256:sha,metric_id:'accuracy',value:0,state:'observed'}],checkpoint:{clocks:{epoch:sha==='a'?1:2,optimizer_update:2,wall_elapsed_ms:50},weights:{name:'weights-'+sha+'.pt'}},predictions:{rows:[{ordinal:0,truth_index:0,predicted_index:1,probabilities:[0.2,0.8]}]}});
function fixture(){
  const calls=[],notes=[],opened=[];let handler,view='runs',intent=0,actor={kind:'owner',actor_id:'owner',credential_id:'one'};
  const nodes={},buttons=[{dataset:{modelCheckpoint:'a'}},{dataset:{modelCheckpoint:'b'}}];
  const node=id=>nodes[id]||(nodes[id]={value:'example',addEventListener(type,fn){this[type]=fn;}});
  const root={querySelector:node,querySelectorAll:selector=>selector==='[data-model-checkpoint]'?buttons:[]};
  const window={workspaceEscape:value=>String(value??'').replaceAll('<','&lt;'),TuldokAuth:{identity:()=>actor}};
  const context={window,history:{state:{},replaceState(value){this.state=value;}},structuredClone,crypto:globalThis.crypto,CSS:{escape:String},document:{activeElement:null}};
  vm.runInNewContext(source,context);
  const ui=window.WorkspaceModel({api:async(route,body)=>{calls.push({route,body});return handler(route,body);},announce:text=>notes.push(text),openRun:()=>{},openRecord:value=>opened.push(value),getView:()=>view,getIntent:()=>intent});
  const run={id:'run',state:'completed',graph:{recipe:'image_classification_model_v2'},metrics:{class_vocabulary:[{label:'circle'},{label:'square'}]}};
  let rendered='';const render=()=>{rendered=ui.html(run);ui.bind(root,run,[],render,()=>view==='runs');};
  return {ui,run,calls,notes,opened,nodes,buttons,history:context.history,render,html:()=>rendered,handler:fn=>handler=fn,navigate(){view='pipeline';intent++;ui.invalidate();},session(){actor=null;ui.invalidate();ui.sessionChanged();}};
}
(async()=>{
  const candidate={ref:{id:'candidate'},candidate:{study_id:'study',limitations:['Diagnostic only']},checkpoint:{sha256:'b'}};
  function saved(r,prepared=false){
    r.run.study_membership={study_id:'study',trial_id:'trial'};r.history.state.modelCandidates={run:{actor:'owner',id:'candidate'}};
    r.history.state.modelExports={candidate:{actor:'owner',candidate_id:'candidate',study_id:'study',mode:'package',body:{request_key:'stable-original-key'},...(prepared?{prepared:{trial:{id:'trial',material:{sha256:'material'}}},approval:{id:'approval'}}:{})}};
  }
  for(const uncertain of [false,true]){
    const r=fixture();saved(r);let attempts=0;
    r.handler(async(route,body)=>{
      if(route==='candidates/candidate')return candidate;
      if(route.endsWith('/package-state'))return {state:'selected',packages:[],verifications:[]};
      if(route==='project-snapshots')return {roots:['root']};
      if(route.endsWith('/prepare-package')){attempts++;if(uncertain&&attempts===1)throw Error('Lost response after possible commit');throw Object.assign(Error('Permission denied'),{status:403,code:'forbidden'});}
      return value(body?.checkpoint_sha256||'b');
    });
    await r.ui.load(r.run,()=>true);r.render();await r.nodes['#model-export-setup'].click();
    await r.nodes['#model-export-resume'].click();if(uncertain)await r.nodes['#model-export-resume'].click();
    assert.equal(r.html().includes('id="model-export-revise"'),!uncertain,'Only a definite initial refusal can offer revised inputs');
    r.nodes['#model-export-revise'].click();
    assert.equal(!!r.history.state.modelExports.candidate,uncertain,'Response loss followed by denial preserves the original uncertain request');
    if(uncertain)assert.equal(r.history.state.modelExports.candidate.body.request_key,'stable-original-key');
  }
  const stale=fixture();saved(stale,true);stale.handler(async(route,body)=>{
    if(route==='candidates/candidate')return candidate;
    if(route.endsWith('/package-state'))return {state:'selected',packages:[],verifications:[]};
    if(route==='project-snapshots')return {roots:['root']};
    if(route==='studies/study')return {study:{revision:stale.calls.filter(call=>call.route==='studies/study').length,admission_epoch:0,open:true}};
    if(route.endsWith('/admit'))throw Object.assign(Error('Study changed'),{status:409,code:'stale'});
    return value(body?.checkpoint_sha256||'b');
  });
  await stale.ui.load(stale.run,()=>true);stale.render();await stale.nodes['#model-export-setup'].click();
  await stale.nodes['#model-export-start'].click();await stale.nodes['#model-export-start'].click();
  assert.equal(stale.calls.filter(call=>call.route==='studies/study').length,2,'Known rejected admission re-reads current Study revision');
  const admissions=stale.calls.filter(call=>call.route.endsWith('/admit'));assert.notEqual(admissions[0].body.request_key,admissions[1].body.request_key);assert.equal(stale.history.state.modelExports.candidate.admission,null);
  const unavailable=fixture();saved(unavailable);unavailable.history.state.modelExports.candidate.preparationUnknown=true;
  unavailable.handler(async(route,body)=>{
    if(route==='candidates/candidate')return candidate;
    if(route.endsWith('/package-state'))throw Error('State read failed');
    if(route==='project-snapshots')return {roots:['root']};
    if(route.endsWith('/prepare-package'))throw Error('Still unresolved');
    return value(body?.checkpoint_sha256||'b');
  });
  await unavailable.ui.load(unavailable.run,()=>true);unavailable.render();await unavailable.nodes['#model-export-setup'].click();
  assert.doesNotMatch(unavailable.html(),/id="model-export-form"/,'A failed package-state query cannot hide the durable uncertain operation');
  assert.match(unavailable.html(),/Reconcile operation preparation/);
  await unavailable.nodes['#model-export-resume'].click();assert.equal(unavailable.calls.find(call=>call.route.endsWith('/prepare-package')).body.request_key,'stable-original-key');
  const noRoot=fixture();saved(noRoot);delete noRoot.history.state.modelExports.candidate;
  noRoot.handler(async(route,body)=>route==='candidates/candidate'?candidate:route.endsWith('/package-state')?{state:'selected',packages:[],verifications:[]}:route==='project-snapshots'?{roots:[]}:value(body?.checkpoint_sha256||'b'));
  await noRoot.ui.load(noRoot.run,()=>true);noRoot.render();await noRoot.nodes['#model-export-setup'].click();
  assert.match(noRoot.html(),/No project root is configured/);assert.doesNotMatch(noRoot.html(),/id="model-export-form"/);
  console.log('PASS candidate UI: known admission rejection refreshes intent; response loss and later denial or package-state failure preserve actor-bound original preparation. Controlled transport only.');
})().catch(error=>{console.error(error);process.exitCode=1;});
