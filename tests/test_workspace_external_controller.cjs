'use strict';
// Controlled transport proof only; real execution is qualified by the browser gate.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),crypto=require('node:crypto');
const source=fs.readFileSync(require('node:path').join(__dirname,'../static/workspace-external.js'),'utf8');
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject};};
function fixture(){
  let dirty=false;const fields={};
  let actor={actor_id:'owner',credential_id:'session1',kind:'owner',scopes:['approve-execution','edit']},intent=0,runId='run1',handler;
  const history={state:{},replaceState(value){this.state=value;}},listeners={},nodes={},calls=[],adopted=[],opened=[],imported=[],notices=[];
  const graph={id:'g',revision:1,name:'neutral',recipe:'external_recipe',nodes:[{type:'input',parameters:{project_id:'p',recipe_id:'r',expected_sha256:'a'.repeat(64),inputs:{sample:{reference_id:'source',expected_sha256:'b'.repeat(64)}}}},{type:'execute',parameters:{mode:'complete'}},{type:'output',parameters:{}}]};
  const node=id=>nodes[id]||(nodes[id]={value:'owner',addEventListener(type,fn){this[type]=fn;}});
  const root={innerHTML:'',querySelector:node,querySelectorAll:selector=>fields[selector]||[]};
  const window={workspaceEscape:value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('\"','&quot;'),TuldokAuth:{identity:()=>actor},addEventListener:(name,fn)=>listeners[name]=fn};
  const context={window,history,crypto,structuredClone,confirm:()=>true};vm.runInNewContext(source,context);
  const api=async(route,body)=>{calls.push({route,body:structuredClone(body)});if(route.endsWith('preflight-external'))return {valid:true,graph_revision:1,material_sha256:'a'.repeat(64),parameter_definitions:{},material:{},outputs:[],runtime:{}};return handler(route,body);};
  let latest;
  const ui=window.WorkspaceExternal({api,action:fn=>latest=fn(),status:value=>notices.push(value),getGraph:()=>graph,getIntent:()=>intent,getRunId:()=>runId,isDirty:()=>dirty,replaceGraph:value=>adopted.push(value),changeGraph:fn=>{fn();dirty=true;ui.invalidate();ui.dirtyChanged(root);},render:()=>{},refresh:()=>{},onRun:value=>opened.push(value),onImported:async id=>imported.push(id)});
  const render=()=>ui.renderPipeline(root,{graph,graphs:[graph],busy:false,choose:()=>{}});
  render();
  return {history,nodes,calls,adopted,opened,imported,notices,root,render,ui,window,graph,fields,setHandler:value=>handler=value,
    navigate(){intent++;},selectRun(){runId='run2';},revokeEdit(){actor={...actor,scopes:[]};},session(){actor={...actor,credential_id:'session2'};listeners['tuldok-session']();},other(){actor={...actor,actor_id:'other'};listeners['tuldok-session']();},
    async review(){await node('#external-preflight').onclick();node('#external-reviewed').change({target:{checked:true}});},
    click(id){node(id).onclick?.();return latest;},event(id){node(id).click();return latest;}};
}
(async()=>{
  const f=fixture();await f.review();f.setHandler(async()=>{throw Object.assign(Error('lost acknowledgement'),{status:503,code:'commit_unknown'});});
  await assert.rejects(f.click('#external-submit'),/lost/);const original=structuredClone(f.history.state.externalSubmission);
  assert.equal(original.actor_id,'owner');assert.ok(original.body.request_key);
  f.session();f.setHandler(async()=>{throw Object.assign(Error('scope changed'),{status:403,code:'forbidden'});});
  await assert.rejects(f.click('#external-submit'),/scope/);assert.deepEqual(structuredClone(f.history.state.externalSubmission),original);
  assert.deepEqual(f.calls.filter(call=>call.route==='runs/submit-external').map(call=>call.body.request_key),[original.body.request_key,original.body.request_key]);
  f.setHandler(async()=>{throw Object.assign(Error('current material unavailable'),{status:409,code:'unavailable'});});await assert.rejects(f.click('#external-submit'),/unavailable/);assert.deepEqual(structuredClone(f.history.state.externalSubmission),original);
  f.other();const count=f.calls.length;await assert.rejects(f.click('#external-submit'),/another actor/);assert.equal(f.calls.length,count);assert.deepEqual(structuredClone(f.history.state.externalSubmission),original);
  for(const [control,event] of [['#external-save',false],['#external-reload',false],['#external-clone',false],['#external-grant',true],['#external-submit',false]]){
    for(const change of ['navigate','session']){
      const g=fixture();await g.review();const held=deferred();g.setHandler(()=>held.promise);
      const result=event?g.event(control):g.click(control);g[change]();held.resolve({id:'durable',revision:2});await result;
      assert.equal(g.adopted.length,0,control+' must not adopt after '+change);assert.equal(g.opened.length,0,control+' must not navigate after '+change);
      g.render();assert.ok(!g.root.innerHTML.includes('data-approval-id="durable"'),control+' must not install stale grant');
      if(control==='#external-submit'){assert.equal(g.history.state.externalSubmission,null);assert.ok(g.notices.some(value=>value.includes('durable')));}
    }
  }
  const h=fixture();await h.review();h.setHandler(async()=>{throw Object.assign(Error('input changed before admission'),{status:409,code:'stale'});});await assert.rejects(h.click('#external-submit'));assert.equal(h.history.state.externalSubmission,null);
  const artifact={name:'fields.zip',role:'scientific_fields',sha256:'b'.repeat(64)},run={id:'run1',state:'completed',graph:{recipe:'external_recipe'}};
  const imported=fixture();imported.setHandler(async()=>({id:'draft1'}));assert.match(imported.ui.artifactActionHTML(run,artifact),/Import into Data/);
  await imported.ui.importArtifact(run,artifact);assert.deepEqual(imported.imported,['draft1']);assert.deepEqual(imported.calls[0],{route:'runs/run1/import-data/fields.zip',body:{expected_sha256:artifact.sha256}});
  for(const change of ['navigate','session','selectRun']){
    const f=fixture(),held=deferred();f.setHandler(()=>held.promise);const result=f.ui.importArtifact(run,artifact);f[change]();held.resolve({id:'saved-draft'});await result;assert.deepEqual(f.imported,[]);assert.ok(f.notices.some(value=>value.includes('saved-draft')));
  }
  const blocked=fixture();blocked.setHandler(()=>{throw Error('Must not call');});
  for(const state of ['running','cancelled','unknown']){assert.equal(blocked.ui.artifactActionHTML({...run,state},artifact),'');await assert.rejects(blocked.ui.importArtifact({...run,state},artifact));}
  assert.equal(blocked.ui.artifactActionHTML({...run,artifact_status:{status:'unavailable'}},artifact),'');assert.equal(blocked.ui.artifactActionHTML(run,{...artifact,role:'result'}),'');
  blocked.revokeEdit();assert.match(blocked.ui.artifactActionHTML(run,artifact),/disabled/);await assert.rejects(blocked.ui.importArtifact(run,artifact),/permission/);assert.equal(blocked.calls.length,0);
  const uncertain=fixture();uncertain.setHandler(async()=>{throw Error('acknowledgement lost');});await assert.rejects(uncertain.ui.importArtifact(run,artifact),/inspect Data/);assert.equal(uncertain.calls.length,1);assert.deepEqual(uncertain.imported,[]);
  const bindingUI=fixture(),helpers=bindingUI.window.WorkspaceExternalInputs;
  const candidate={release_id:'c'.repeat(64),sha256:'c'.repeat(64),bytes:20,status:'available'},project={data:[{id:'source',label:'Source',status:'available',integrity:'verified',observed_sha256:'b'.repeat(64),bytes:10}]};
  const choices=helpers.choices(project,[candidate,{...candidate,release_id:'d'.repeat(64),status:'unavailable',reason:'Missing archive'}]);
  assert.deepEqual(structuredClone(helpers.binding('project_reference',choices.project_reference[0])),{reference_id:'source',expected_sha256:'b'.repeat(64)});
  assert.deepEqual(structuredClone(helpers.binding('frozen_release',choices.frozen_release[0])),{kind:'frozen_release',release_id:candidate.release_id,expected_sha256:candidate.sha256});
  assert.throws(()=>helpers.binding('frozen_release',choices.frozen_release[1]),/available/);
  assert.match(helpers.html({sample:{reference_id:'missing',expected_sha256:'e'.repeat(64)}},{sample:{max_bytes:100}},choices),/Saved missing.*exact binding retained/);
  assert.match(helpers.html({},{sample:{max_bytes:5}},choices),/disabled.*exceeds slot limit/);
  await bindingUI.review();
  bindingUI.window.TuldokAuth.fetch=async()=>({ok:true,json:async()=>({releases:[candidate]})});
  bindingUI.setHandler(async route=>route==='projects/p'?project:route.includes('/recipes/')?{inputs:{sample:{max_bytes:100}}}:({id:'g',revision:2}));
  await bindingUI.click('#external-input-choices');
  const kind={value:'project_reference',getAttribute:()=> 'sample'},select={value:'source',getAttribute:()=> 'sample'},hint={getAttribute:()=> 'sample'};
  bindingUI.fields['[data-external-input-kind]']=[kind];bindingUI.fields['[data-external-input]']=[select];bindingUI.fields['[data-external-input-hash]']=[hint];bindingUI.render();
  kind.value='frozen_release';kind.onchange();assert.equal(bindingUI.graph.nodes[0].parameters.inputs.sample,undefined);
  select.value=candidate.release_id;select.onchange();
  assert.deepEqual(structuredClone(bindingUI.graph.nodes[0].parameters.inputs.sample),{kind:'frozen_release',release_id:candidate.release_id,expected_sha256:candidate.sha256});
  assert.equal(bindingUI.nodes['#external-preflight'].disabled,true);assert.equal(bindingUI.nodes['#external-reviewed'].checked,false);
  await assert.rejects(bindingUI.click('#external-submit'),/Save and preflight/);
  await bindingUI.click('#external-save');const save=bindingUI.calls.find(call=>call.route==='graphs/g');assert.equal(save.body.document.nodes[0].parameters.inputs.sample.kind,'frozen_release');
  assert.match(helpers.html(save.body.document.nodes[0].parameters.inputs,{sample:{max_bytes:100}},choices),/value="frozen_release" selected/);
  for(const change of ['navigate','session']){
    const late=fixture(),held=deferred();late.window.TuldokAuth.fetch=async()=>({ok:true,json:async()=>({releases:[candidate]})});late.setHandler(()=>held.promise);
    const request=late.click('#external-input-choices');late[change]();held.resolve({data:project.data,inputs:{sample:{max_bytes:100}}});await request;late.render();assert.doesNotMatch(late.root.innerHTML,/data-external-input-kind/);
  }
  const sourceRun='1'.repeat(32),otherRun='2'.repeat(32),artifactChoice={artifact_name:'model.pt',role:'checkpoint',bytes:50,sha256:'e'.repeat(64),status:'receipt_verified'};
  const runCandidates=[{run_id:sourceRun,state:'completed',status:'receipt_verified',reason:null,artifacts:[artifactChoice]},
    {run_id:otherRun,state:'completed',status:'receipt_verified',reason:null,artifacts:[{...artifactChoice,sha256:'f'.repeat(64)}]},
    {run_id:'3'.repeat(32),state:'completed',status:'unavailable',reason:'<missing>',artifacts:[]},
    {run_id:'4'.repeat(32),state:'failed',status:'receipt_verified',reason:null,artifacts:[artifactChoice]}];
  const runChoices=helpers.choices(project,[candidate],runCandidates);
  assert.equal(runChoices.run_artifact.length,2);assert.equal(runChoices.runs.length,3);
  const exactBinding={kind:'run_artifact',run_id:sourceRun,artifact_name:'model.pt',expected_sha256:artifactChoice.sha256};
  assert.deepEqual(structuredClone(helpers.binding('run_artifact',runChoices.run_artifact[0])),exactBinding);
  assert.match(helpers.html({sample:exactBinding},{sample:{max_bytes:100}},runChoices),/value="run_artifact" selected/);
  assert.match(helpers.html({sample:exactBinding},{sample:{max_bytes:100}},runChoices),/value="model.pt" selected/);
  assert.match(helpers.html({sample:exactBinding},{sample:{max_bytes:100}},runChoices),/&lt;missing&gt;/);
  assert.match(helpers.html({sample:exactBinding},{sample:{max_bytes:100}},helpers.choices(project,[],[])),/exact binding retained/);
  bindingUI.window.TuldokAuth.fetch=async url=>({ok:true,json:async()=>url.endsWith('run-artifact-inputs')?{runs:runCandidates}:{releases:[candidate]}});
  await bindingUI.click('#external-input-choices');
  const runSelector={value:'',getAttribute:()=> 'sample'},runGroup={getAttribute:()=> 'sample'};
  bindingUI.fields['[data-external-input-run]']=[runSelector];bindingUI.fields['[data-external-input-run-group]']=[runGroup];bindingUI.render();
  kind.value='run_artifact';kind.onchange();assert.equal(runGroup.hidden,false);assert.equal(runSelector.required,true);
  runSelector.value=sourceRun;runSelector.onchange();select.value='model.pt';select.onchange();
  assert.deepEqual(structuredClone(bindingUI.graph.nodes[0].parameters.inputs.sample),exactBinding);
  assert.equal(bindingUI.nodes['#external-preflight'].disabled,true);assert.equal(bindingUI.nodes['#external-reviewed'].checked,false);
  await bindingUI.click('#external-save');assert.deepEqual(bindingUI.calls.filter(call=>call.route==='graphs/g').at(-1).body.document.nodes[0].parameters.inputs.sample,exactBinding);
  runSelector.value=otherRun;runSelector.onchange();assert.equal(bindingUI.graph.nodes[0].parameters.inputs.sample,undefined);
  select.value='model.pt';select.onchange();assert.equal(bindingUI.graph.nodes[0].parameters.inputs.sample.expected_sha256,'f'.repeat(64));assert.equal(bindingUI.graph.nodes[0].parameters.inputs.sample.run_id,otherRun);
  select.value='../../unlisted';select.onchange();assert.equal(bindingUI.graph.nodes[0].parameters.inputs.sample,undefined);
  kind.value='project_reference';kind.onchange();assert.equal(runGroup.hidden,true);assert.equal(runSelector.disabled,true);select.value='source';select.onchange();assert.deepEqual(structuredClone(bindingUI.graph.nodes[0].parameters.inputs.sample),{reference_id:'source',expected_sha256:'b'.repeat(64)});
  bindingUI.window.TuldokAuth.fetch=async url=>{if(url.endsWith('run-artifact-inputs'))throw Error('Candidate service unavailable');return {ok:true,json:async()=>({releases:[candidate]})};};
  const partial=await helpers.catalogs();assert.equal(partial.releases.length,1);assert.equal(partial.runs.length,0);assert.match(partial.errors[0],/Run artifacts/);
  const progressUI=fixture().ui,completed={id:'r',state:'completed',artifacts:[{name:'model.pt',role:'checkpoint'}]};
  const progress={run_id:'r',evidence:'live_unverified',streams:{stdout:{available_bytes:12,start_byte:4,text:'<script>unsafe</script>',truncated:true},stderr:null},progress:{format:'tuldok_progress_v1',stage:'loading',completed:1,total:2,metrics:{actual:4}},result:null};
  let html=progressUI.progressHTML({...completed,state:'running'},progress);assert.match(html,/Live output · unverified/);assert.match(html,/1 \/ 2/);assert.match(html,/&lt;script&gt;/);assert.doesNotMatch(html,/<script>|<details[^>]* open/);
  const result={status:'hash_verified',sha256:'f'.repeat(64),summary:{format:'tuldok_result_summary_v1',title:'Reported result',metrics:[{name:'value',value:2,unit:'m'}],scope:['Previously exposed material'],checkpoint:'model.pt'}};
  html=progressUI.progressHTML(completed,{...progress,evidence:'unavailable',progress:null,result});assert.match(html,/Hash-verified result artifact/);assert.match(html,/Download checkpoint/);assert.match(html,/recipe-reported values, not scientific qualification/);
  assert.doesNotMatch(progressUI.progressHTML({...completed,state:'cancelled'},{...progress,result}),/Reported result|Download checkpoint/);
  assert.doesNotMatch(progressUI.progressHTML({...completed,artifacts:[{name:'model.pt',role:'result'}]},{...progress,result}),/Download checkpoint/);
  assert.doesNotMatch(progressUI.progressHTML(completed,{...progress,run_id:'other',result}),/Reported result|loading/);
  assert.match(progressUI.progressHTML(completed,{...progress,result:{status:'unavailable'}}),/Result summary unavailable/);
  // Exercise the actual polling composition with held progress responses.
  for(const change of ['view','session','none','receipt']){
    const held=deferred(),requested=deferred(),listeners={};let actor={actor_id:'owner',credential_id:'one',kind:'owner',scopes:[]};
    const root=()=>({innerHTML:'',contains:()=>false,querySelectorAll:()=>[],querySelector:()=>({addEventListener(){},classList:{toggle(){}},setAttribute(){}})});
    const pipelineRoot=root(),runsRoot=root(),record={id:'poll',state:'completed',graph:{recipe:'external_recipe',name:'Polling fixture'},artifacts:[],node_attempts:[],events:[],progress:{}};
    if(change==='receipt')record.artifact_status={status:'receipt_verified',payloads:'not_checked'};
    const auth={identity:()=>actor,fetch:async url=>({ok:true,json:async()=>{
      if(url.endsWith('/runs'))return [record];if(url.endsWith('/progress')){requested.resolve();return held.promise;}return record;
    }})};
    const window={workspaceEscape:String,TuldokAuth:auth,addEventListener:(name,fn)=>(listeners[name]||=[]).push(fn)};
    const context={window,TuldokAuth:auth,history:{state:{},replaceState(){}},structuredClone,crypto,clearTimeout,setTimeout,document:{activeElement:null},CSS:{escape:String}};
    vm.runInNewContext(source,context);context.WorkspaceExternal=window.WorkspaceExternal;
    vm.runInNewContext(fs.readFileSync(require('node:path').join(__dirname,'../static/workspace-service.js'),'utf8'),context);context.WorkspaceModel=window.WorkspaceModel;
    vm.runInNewContext(fs.readFileSync(require('node:path').join(__dirname,'../static/experiment-lineage.js'),'utf8'),context);
    vm.runInNewContext(fs.readFileSync(require('node:path').join(__dirname,'../static/workspace-real.js'),'utf8'),context);
    const workspace=window.WorkspaceReal({pipelineRoot,runsRoot,announce(){}}),loading=workspace.show('runs');await requested.promise;
    if(change==='view')await workspace.show(null);
    if(change==='session'){actor=null;for(const fn of listeners['tuldok-session'])fn();}
    held.resolve({run_id:'poll',evidence:'custody_verified',streams:{},progress:{format:'tuldok_progress_v1',stage:'HELD_PROGRESS',completed:1,total:1,metrics:{}},result:null});await loading;
    if(change==='none'||change==='receipt'){
      if(change==='receipt'){assert.match(runsRoot.innerHTML,/Recorded outputs; verified on download/);assert.doesNotMatch(runsRoot.innerHTML,/<h3>Verified artifacts<\/h3>/);}
      assert.match(runsRoot.innerHTML,/HELD_PROGRESS/);assert.doesNotMatch(runsRoot.innerHTML,/<h3>Stage evidence<\/h3>/);assert.match(runsRoot.innerHTML,/Run lifecycle events/);assert.match(runsRoot.innerHTML,/Trusted local execution/);assert.match(runsRoot.innerHTML,/<details id="external-custody-details" data-external-disclosure><summary>Custody and approved material<\/summary>/);actor=null;for(const fn of listeners['tuldok-session'])fn();assert.doesNotMatch(runsRoot.innerHTML,/HELD_PROGRESS/);
    }else assert.doesNotMatch(runsRoot.innerHTML,/HELD_PROGRESS/);
  }
  console.log('PASS project/frozen/Run-artifact binding and generic progress controllers: exact old/new union, unavailable and oversized refusal, dirty approval invalidation, save/reopen projection, stale/session choice fences, escaped logs, truthful evidence, restored verified summaries, held polling view/session fences and session cache clearing. Mock transport only.');
  console.log('PASS scientific artifact import controller: exact hash/route, draft navigation, session/view/run-selection fences, non-completed/unavailable role refusal, edit permission and no replay after uncertain acknowledgement. Mock transport only.');
  console.log('PASS external controller: actor-bound unresolved key survives ambiguous→403; no cross-actor request; late save/reload/clone/grant/submit preserve navigation/session; initial authoritative rejection clears key. Mock transport only.');
})().catch(error=>{console.error(error);process.exitCode=1;});
