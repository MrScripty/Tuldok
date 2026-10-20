'use strict';
// Controlled transport proves presentation lifecycle only. Actual training is covered by browser_model_development.cjs.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../static/workspace-service.js'),'utf8');
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no});return {promise,resolve,reject};};
const entry=(epoch,sha)=>({checkpoint:{sha256:sha,name:'checkpoint-'+epoch+'.json'},clocks:{epoch},selected:epoch===2,state:'retained'});
const value=(sha='b')=>({state:'verified',manifest:{producer:{run_id:'run'}},checkpoint_index:{entries:[entry(1,'a'),entry(2,'b')]},probe:{members:[{ordinal:0,frozen_reference:{id:'example',revision:3,source_revision:1}}]},observations:[{checkpoint_sha256:sha,metric_id:'accuracy',value:0,state:'observed'}],checkpoint:{clocks:{epoch:sha==='a'?1:2,optimizer_update:2,wall_elapsed_ms:50},weights:{name:'weights-'+sha+'.pt'}},predictions:{rows:[{ordinal:0,truth_index:0,predicted_index:1,probabilities:[0.2,0.8]}]}});
function fixture(){
  const calls=[],notes=[],opened=[],failures=[];let handler,view='runs',intent=0,actor={kind:'owner',actor_id:'owner',credential_id:'one'};
  const nodes={},buttons=[{dataset:{modelCheckpoint:'a'}},{dataset:{modelCheckpoint:'b'}}];
  const node=id=>nodes[id]||(nodes[id]={value:'example',addEventListener(type,fn){this[type]=fn;}});
  const root={querySelector:node,querySelectorAll:selector=>selector==='[data-model-checkpoint]'?buttons:[]};
  const window={workspaceEscape:value=>String(value??'').replaceAll('<','&lt;'),TuldokAuth:{identity:()=>actor}};
  const context={window,history:{state:{},replaceState(value){this.state=value;}},structuredClone,crypto:globalThis.crypto,CSS:{escape:String},document:{activeElement:null}};
  vm.runInNewContext(source,context);
  const ui=window.WorkspaceModel({api:async(route,body)=>{calls.push({route,body});return handler(route,body);},announce:text=>notes.push(text),openRun:()=>{},openRecord:value=>opened.push(value),getView:()=>view,getIntent:()=>intent,onAccessFailure:(...args)=>failures.push(args)});
  const run={id:'run',state:'completed',graph:{recipe:'image_classification_model_v2'},metrics:{class_vocabulary:[{label:'circle'},{label:'square'}]}};
  let rendered='';const render=()=>{rendered=ui.html(run);ui.bind(root,run,[],render,()=>view==='runs');};
  return {ui,run,calls,notes,opened,failures,nodes,buttons,expired(){actor=null;},history:context.history,render,html:()=>rendered,handler:fn=>handler=fn,navigate(){view='pipeline';intent++;ui.invalidate();},session(){actor=null;ui.invalidate();ui.sessionChanged();}};
}
(async()=>{
  for(const status of [401,403]){
    const denied=fixture(),failure=Object.assign(Error('Current access denied'),{status});
    denied.handler(async()=>{throw failure;});
    await assert.rejects(denied.ui.load(denied.run,()=>true),error=>error===failure,
      'Model evidence denial must reach the Runs owner before detail/predictions can commit');
    assert.doesNotMatch(denied.ui.html(denied.run),/Linked epoch evidence/);
  }
  for(const change of ['expired','navigate','session']){
    const late=fixture();late.handler(async(route,body)=>value(body.checkpoint_sha256||'b'));await late.ui.load(late.run,()=>true);late.render();
    const held=deferred();late.handler(()=>held.promise);const loading=late.buttons[0].onclick();late[change]();
    held.reject(Object.assign(Error('Denied checkpoint'),{status:401}));await loading;
    assert.equal(late.failures.length,change==='expired'?1:0,'Only a current model generation reports denial after '+change);
    if(change==='expired'){assert.equal(late.failures[0][1],'run');assert.equal(late.failures[0][2],'one');}
  }
  const f=fixture();f.handler(async(route,body)=>value(body.checkpoint_sha256||'b'));await f.ui.load(f.run,()=>true);f.render();
  assert.match(f.html(),/Linked epoch evidence/);assert.match(f.html(),/circle/);assert.match(f.html(),/square/);assert.match(f.html(),/>0\.0000<\/td>/,'Observed zero remains zero');
  assert.match(f.ui.html({graph:{recipe:'image_classification'}}),/was not captured/);
  f.render();f.nodes['#model-correct'].click();assert.equal(f.opened[0].id,'example');assert.equal(f.opened[0].truth_label,'circle');assert.equal(f.opened[0].revision,3);
  for(const change of ['navigate','session']){
    const g=fixture(),held=deferred();g.handler(()=>held.promise);const loading=g.ui.load(g.run,()=>true);g[change]();held.resolve(value());await loading;
    assert.doesNotMatch(g.ui.html(g.run),/Linked epoch evidence/,'Late evidence after '+change);
  }
  const g=fixture();g.handler(async(route,body)=>value(body.checkpoint_sha256||'b'));await g.ui.load(g.run,()=>true);g.render();
  const first=deferred(),second=deferred();g.handler((route,body)=>body.checkpoint_sha256==='a'?first.promise:second.promise);
  const earlier=g.buttons[0].onclick(),later=g.buttons[1].onclick();second.resolve(value('b'));await later;first.resolve(value('a'));await earlier;
  assert.match(g.html(),/weights-b.pt/);assert.doesNotMatch(g.html(),/weights-a.pt/);
  g.handler(async()=>{throw Error('Read permission revoked');});await g.buttons[0].onclick();assert.match(g.html(),/Read permission revoked/);assert.doesNotMatch(g.html(),/data-model-checkpoint|model-probe/);
  const u=fixture();u.handler(async()=>{const result=value();result.observations[0]={checkpoint_sha256:'b',metric_id:'accuracy',state:'undefined',reason:'empty_population'};return result;});await u.ui.load(u.run,()=>true);assert.match(u.ui.html(u.run),/Undefined: empty_population/);
  const c=fixture(),memberRun={...c.run,study_membership:{study_id:'study',trial_id:'trial'}};
  c.history.state.modelCandidates={run:{actor:'owner',id:'candidate-a'}};
  c.handler(async(route,body)=>route.startsWith('candidates/')?{ref:{id:'candidate-a'},candidate:{limitations:['Diagnostic only']},checkpoint:{sha256:'a'}}:value(body.checkpoint_sha256||'b'));
  await c.ui.load(memberRun,()=>true);assert.match(c.ui.html(memberRun),/Diagnostic candidate retained/);
  const another={...memberRun,id:'another'};await c.ui.load(another,()=>true);assert.doesNotMatch(c.ui.html(another),/Diagnostic candidate retained/,'Candidate from the previous Run must not appear on another Run');
  // Comparison generations belong to their exact selector set, independently of target metadata reads.
  for(const selector of ['metric','checkpoint','mode','left-checkpoint']){
    const r=fixture(),held=deferred(),newer=deferred();let comparisons=0;
    r.run.artifacts=[{name:'model-evidence.json',sha256:'left-evaluation'}];
    const rich=(sha='b')=>({...value(sha),metric_definitions:[{id:'loss',units:'loss',direction:'minimize'},{id:'accuracy',units:'fraction',direction:'maximize'}],metric_definition_hashes:{loss:'loss-definition',accuracy:'accuracy-definition'}});
    const result=(metric='loss')=>({state:'compatible',mode:'paired',sides:['run','other'].map(run_id=>({run_id,checkpoint_sha256:'b',metric_id:metric,result:{state:'observed',value:1,sample_count:1}})),reasons:[],delta:null});
    r.handler(async(route,body)=>route==='runs/other'?{...r.run,id:'other',artifacts:[{name:'model-evidence.json',sha256:'right-evaluation'}]}:route.endsWith('/compare-model-evidence')?(++comparisons===1?held.promise:newer.promise):rich(body?.checkpoint_sha256||'b'));
    await r.ui.load(r.run,()=>true);r.render();r.nodes['#model-compare-run'].value='other';await r.nodes['#model-compare-run'].change();
    r.nodes['#model-compare-checkpoint'].change({target:{value:'b'}});r.nodes['#model-compare-metric'].change({target:{value:'loss'}});
    const pending=r.nodes['#model-compare-form'].submit({preventDefault(){}});
    if(selector==='left-checkpoint')await r.buttons[0].onclick();
    else r.nodes['#model-compare-'+selector].change({target:{value:selector==='metric'?'accuracy':selector==='checkpoint'?'a':'side_by_side'}});
    const fresh=r.nodes['#model-compare-form'].submit({preventDefault(){}});
    held.resolve(result());await pending;
    assert.doesNotMatch(r.html(),/class="model-comparison-result"/,'Selector '+selector+' excludes pending old comparison');
    assert.match(r.html(),/id="model-compare" disabled/,'Old request finalizer cannot enable a newer comparison');
    newer.resolve(result(selector==='metric'?'accuracy':'loss'));await fresh;
    assert.match(r.html(),/class="model-comparison-result"/);
    await r.buttons[1].onclick();
    assert.doesNotMatch(r.html(),/class="model-comparison-result"/,'Changing main checkpoint clears a completed comparison');
  }
  const simultaneous=fixture(),checkpointReply=deferred();simultaneous.run.study_membership={study_id:'study',trial_id:'trial'};
  simultaneous.handler(async(route,body)=>body.checkpoint_sha256==='a'?checkpointReply.promise:value(body.checkpoint_sha256||'b'));
  await simultaneous.ui.load(simultaneous.run,()=>true);simultaneous.render();
  const choosing=simultaneous.buttons[0].onclick();
  assert.match(simultaneous.html(),/id="model-select-candidate" disabled/,'Candidate selection waits for the exact checkpoint query');
  await simultaneous.nodes['#model-select-candidate'].click();
  assert.equal(simultaneous.calls.some(call=>call.route.endsWith('/select-candidate')),false);
  checkpointReply.resolve(value('a'));await choosing;assert.match(simultaneous.html(),/weights-a.pt/);
  console.log('PASS model UI: exact frozen probe correction, honest legacy history, observed zero, query ordering, navigation/session exclusion and denied evidence clearing. Controlled transport only.');
})().catch(error=>{console.error(error);process.exitCode=1;});
