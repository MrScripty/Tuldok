'use strict';
// Controlled transport proof only; real execution is qualified by the browser gate.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),crypto=require('node:crypto');
const source=fs.readFileSync(require('node:path').join(__dirname,'../static/workspace-external.js'),'utf8');
const deferred=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return {promise,resolve,reject};};
function fixture(){
  let actor={actor_id:'owner',credential_id:'session1',kind:'owner',scopes:['approve-execution','edit']},intent=0,runId='run1',handler;
  const history={state:{},replaceState(value){this.state=value;}},listeners={},nodes={},calls=[],adopted=[],opened=[],imported=[],notices=[];
  const graph={id:'g',revision:1,name:'neutral',recipe:'external_recipe',nodes:[{type:'input',parameters:{}},{type:'execute',parameters:{mode:'complete'}},{type:'output',parameters:{}}]};
  const node=id=>nodes[id]||(nodes[id]={value:'owner',addEventListener(type,fn){this[type]=fn;}});
  const root={innerHTML:'',querySelector:node,querySelectorAll:()=>[]};
  const window={workspaceEscape:String,TuldokAuth:{identity:()=>actor},addEventListener:(name,fn)=>listeners[name]=fn};
  const context={window,history,crypto,structuredClone,confirm:()=>true};vm.runInNewContext(source,context);
  const api=async(route,body)=>{calls.push({route,body:structuredClone(body)});if(route.endsWith('preflight-external'))return {valid:true,graph_revision:1,material_sha256:'a'.repeat(64),parameter_definitions:{},material:{},outputs:[],runtime:{}};return handler(route,body);};
  let latest;
  const ui=window.WorkspaceExternal({api,action:fn=>latest=fn(),status:value=>notices.push(value),getGraph:()=>graph,getIntent:()=>intent,getRunId:()=>runId,isDirty:()=>false,replaceGraph:value=>adopted.push(value),changeGraph:()=>{},render:()=>{},refresh:()=>{},onRun:value=>opened.push(value),onImported:async id=>imported.push(id)});
  const render=()=>ui.renderPipeline(root,{graph,graphs:[graph],busy:false,choose:()=>{}});
  render();
  return {history,nodes,calls,adopted,opened,imported,notices,root,render,ui,setHandler:value=>handler=value,
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
  console.log('PASS scientific artifact import controller: exact hash/route, draft navigation, session/view/run-selection fences, non-completed/unavailable role refusal, edit permission and no replay after uncertain acknowledgement. Mock transport only.');
  console.log('PASS external controller: actor-bound unresolved key survives ambiguous→403; no cross-actor request; late save/reload/clone/grant/submit preserve navigation/session; initial authoritative rejection clears key. Mock transport only.');
})().catch(error=>{console.error(error);process.exitCode=1;});
