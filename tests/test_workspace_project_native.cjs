'use strict';
// Controlled transport/controller assertions; actual native runtime is qualified separately.
const assert=require('node:assert/strict');
const {mount,state,records,bound,response,tick,B,P,C,NEXT,capabilities,versionPins}=require('./test_workspace_project_files_m4.cjs');
const G='1'.repeat(32),RUN='2'.repeat(32),PHASE='3'.repeat(32),graph={id:G,name:'Saved model Ω',recipe:'torch_image_classifier_v1',revision:2};
const validation=()=>({status:'valid',valid:true,errors:[],validation_token:C,graph_revision:2,execution_sha256:NEXT,release:{id:C},runtime:{available:true}});
const admission=()=>({format:'project_run_admission_v1',origin_catalog_id:P,run_id:RUN,request_sha256:NEXT});
const phase=()=>({format:'project_native_phase_v1',origin_catalog_id:P,phase_id:PHASE,phase:'probe',run_id:null,state:'failed',spec_sha256:C,receipt_sha256:NEXT});
function confirm(h,id){const el=h.nodes.get(id);el.checked=true;el.listeners.get('change')({target:el});}
async function load(h){h.answers.push(response(bound({items:[graph,{...graph,id:'4'.repeat(32),recipe:'external_recipe'}],total:2,offset:0,limit:40})));await h.click('project-native-graphs');assert.equal(h.nodes.get('project-native-graph').children.length,1);}
(async()=>{
  {
    const h=mount();await tick();const start=h.requests.length;await load(h);assert.equal(h.requests.length,start+1);assert.ok(h.requests.at(-1).url.includes('/graphs?'));assert.equal(h.nodes.get('project-native-submit-fields').disabled,true);
    const count=h.requests.length;await h.submit('project-native-preflight-form');assert.equal(h.requests.length,count,'Unconfirmed probe never dispatches');confirm(h,'project-native-probe-confirm');
    h.answers.push(({options})=>{const body=JSON.parse(options.body);assert.deepEqual(Object.keys(body).sort(),['binding','expected_checkpoint','request_key','graph_id','revision'].sort());assert.equal(body.graph_id,G);assert.equal(body.revision,2);return response(bound(validation(),NEXT));});await h.submit('project-native-preflight-form');assert.equal(h.nodes.get('project-files-error').textContent,'');assert.equal(h.nodes.get('project-native-submit-fields').disabled,false);assert.match(h.nodes.get('project-files-status').textContent,/separate explicit action/);
    const before=h.requests.length;await h.submit('project-native-submit-form');assert.equal(h.requests.length,before);confirm(h,'project-native-submit-confirm');h.answers.push(({options})=>{const body=JSON.parse(options.body);assert.equal(body.validation_token,C);assert.equal(body.graph_revision,2);assert.ok(!Object.hasOwn(body,'approval_id'));return response(bound(admission(),NEXT));});await h.submit('project-native-submit-form');assert.equal(h.nodes.get('project-files-error').textContent,'');assert.equal(h.nodes.get('project-native-run-id').value,RUN);assert.equal(h.nodes.get('project-native-submit-fields').disabled,true);
    confirm(h,'project-native-retry-confirm');h.answers.push(({url,options})=>{assert.ok(url.endsWith('/'+RUN+'/retry'));assert.deepEqual(Object.keys(JSON.parse(options.body)).sort(),['binding','expected_checkpoint','request_key'].sort());return response(bound({...admission(),run_id:'5'.repeat(32)},NEXT));});await h.submit('project-native-retry-form');assert.equal(h.nodes.get('project-files-error').textContent,'');assert.equal(h.nodes.get('project-native-run-id').value,'5'.repeat(32));assert.equal(h.nodes.get('project-files-error').textContent,'');
  }
  {
    const h=mount();await tick();await load(h);confirm(h,'project-native-probe-confirm');h.answers.push(()=>Promise.reject(Error('lost ACK')));await h.submit('project-native-preflight-form');const original=JSON.parse(h.requests.at(-1).options.body);assert.match(h.nodes.get('project-native-pending').textContent,new RegExp(original.request_key));
    h.answers.push(response(state(B,NEXT)),response(records(B,NEXT)));await h.click('project-files-refresh');const count=h.requests.length;await tick();assert.equal(h.requests.length,count,'No automatic probe or retry');assert.equal(h.nodes.get('project-native-pending-retry').disabled,false);
    h.answers.push(({options})=>{assert.deepEqual(JSON.parse(options.body),original);return response(bound(validation(),NEXT));});await h.click('project-native-pending-retry');assert.equal(h.nodes.get('project-files-error').textContent,'');assert.equal(h.nodes.get('project-native-pending-retry').disabled,true);
  }
  {
    const h=mount();await tick();const recovery={...state(),state:'recovery_required',available_actions:['open'],recovery:{action:'open',root:'fixture',directory:'alpha',reason:'projection_unavailable',request_key:'original-phase-request'}};h.answers.push(response(recovery));await h.click('project-files-refresh');assert.equal(h.nodes.get('project-native-reconcile-fields').disabled,false);h.input('project-native-phase-id',PHASE);
    h.answers.push(({options,url})=>{const body=JSON.parse(options.body);assert.deepEqual(body,{binding:B,expected_checkpoint:C});assert.ok(url.endsWith('/'+PHASE+'/reconcile'));return response(bound(phase(),NEXT));});await h.submit('project-native-reconcile-form');assert.equal(h.nodes.get('project-files-error').textContent,'');assert.match(h.nodes.get('project-files-status').textContent,/does not start or resume/);
  }
  {
    const h=mount();await tick();await load(h);confirm(h,'project-native-probe-confirm');h.answers.push(response(bound({...validation(),graph_revision:3},NEXT)));await h.submit('project-native-preflight-form');assert.match(h.nodes.get('project-files-error').textContent,/differs from the selected saved graph/);assert.equal(h.nodes.get('project-native-submit-fields').disabled,true);
    const count=h.requests.length;await tick();assert.equal(h.requests.length,count);
  }
  {
    const caps=JSON.parse(JSON.stringify(capabilities)),op=caps.operations.find(item=>item.id==='project_files.execution_health');op.contracts.push({...op.contracts[0],version:2,sha256:versionPins[op.id]['2']});
    const h=mount(caps);await tick();const recovery={...state(),state:'recovery_required',available_actions:['open'],recovery:{action:'open',root:'fixture',directory:'alpha',reason:'projection_unavailable',request_key:'original-probe-key'}};h.answers.push(response(recovery));await h.click('project-files-refresh');assert.equal(h.nodes.get('project-execution-health').disabled,false);const health={format:'project_execution_health_v1',active_run_ids:[],active_count:0,offset:0,limit:40,local_owner_active:false,available:false,drain_required:true,native_phases:{items:Array.from({length:40},(_,i)=>({...phase(),phase_id:(i+1).toString(16).padStart(32,'0')})),offset:0,limit:40,total:41}};
    h.answers.push(({options})=>{assert.match(options.headers['Tuldok-Operation-Contract'],/execution_health\/2\//);return response(bound(health));});await h.click('project-execution-health');assert.equal(h.nodes.get('project-files-error').textContent,'');
    assert.equal(h.nodes.get('project-native-phases').querySelectorAll('button').length,40);assert.equal(h.nodes.get('project-execution-health-more').hidden,false);
    await h.row('project-native-phases');assert.equal(h.nodes.get('project-native-phase-id').value,'1'.padStart(32,'0'));const count=h.requests.length;await tick();assert.equal(h.requests.length,count,'Selecting a current phase does not execute reconciliation');
    h.answers.push(({url})=>{assert.ok(url.includes('offset=40'));return response(bound({...health,offset:40,native_phases:{items:[{...phase(),phase_id:'4'.repeat(32)}],offset:40,limit:40,total:41}}));});await h.click('project-execution-health-more');assert.equal(h.nodes.get('project-files-error').textContent,'');assert.equal(h.nodes.get('project-native-phases').querySelectorAll('button').length,41);
  }
  console.log('Native controller: 5 selected groups PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
