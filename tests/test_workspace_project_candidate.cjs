'use strict';
const assert=require('node:assert/strict');
const {mount,state,response,bound,tick,P,ACTOR,C,NEXT}=require('./test_workspace_project_files_m4.cjs');
const STUDY='a'.repeat(32),CANDIDATE='e'.repeat(32);
const prepared=()=>({state:'prepared',candidate_id:CANDIDATE,trial:{format:'trial_v1',id:'1'.repeat(32),study_id:STUDY,material:{kind:'recipe_material',catalog_id:P,id:C,sha256:C},replicate:0},graph:{id:'2'.repeat(32),revision:1,nodes:[],edges:[]},model:{kind:'model',catalog_id:P,id:ACTOR,revision:1,sha256:C},runtime_snapshot_sha256:C});
const recovery=()=>({...state(),state:'recovery_required',available_actions:['open'],recovery:{action:'open',root:'fixture',directory:'alpha',reason:'projection_unavailable',request_key:'pending-preparation-key'}});
(async()=>{
  {
    const h=mount();await tick();for(const [id,value] of Object.entries({'project-candidate-study':STUDY,'project-candidate-id':CANDIDATE,'project-candidate-revision':'1','project-candidate-directory':'package','project-candidate-runtime':C}))h.input(id,value);h.nodes.get('project-candidate-kind').value='package';
    h.answers.push(({options})=>{const body=JSON.parse(options.body);assert.equal(body.study_id,undefined);assert.equal(body.expected_checkpoint,C);assert.equal(body.runtime_snapshot_sha256,C);assert.equal(body.candidate_id,CANDIDATE);assert.ok(!Object.hasOwn(body,'approval_id'));assert.equal(h.nodes.get('project-candidate-recovery-key').value,body.request_key);return response(bound(prepared(),NEXT));});await h.submit('project-candidate-prepare-form');assert.equal(h.nodes.get('project-files-error').textContent,'');assert.match(h.nodes.get('project-files-status').textContent,/No Run was launched/);
  }
  {
    const h=mount();await tick();h.answers.push(response(recovery()));await h.click('project-files-refresh');
    assert.equal(h.nodes.get('project-candidate-prepare-fields').disabled,true);assert.equal(h.nodes.get('project-candidate-reconcile').disabled,false);assert.equal(h.nodes.get('project-candidate-abandon').disabled,false);
    h.input('project-candidate-recovery-study',STUDY);h.input('project-candidate-recovery-key','pending-preparation-key');
    h.answers.push(({options})=>{const body=JSON.parse(options.body);assert.deepEqual(Object.keys(body).sort(),['binding','expected_checkpoint','preparation_key'].sort());assert.equal(body.preparation_key,'pending-preparation-key');return response(bound(prepared(),NEXT));});await h.click('project-candidate-reconcile');assert.equal(h.nodes.get('project-files-error').textContent,'');assert.match(h.nodes.get('project-files-status').textContent,/no writer was replayed/);
  }
  {
    const h=mount();await tick();h.answers.push(response(recovery()));await h.click('project-files-refresh');h.input('project-candidate-recovery-study',STUDY);h.input('project-candidate-recovery-key','pending-preparation-key');
    const before=h.requests.length;await h.click('project-candidate-abandon');assert.equal(h.requests.length,before);assert.match(h.nodes.get('project-files-error').textContent,/explicit reason/);
    h.input('project-candidate-abandon-reason','Scientist explicitly abandons stopped partial writer Ω');
    h.answers.push(({options})=>{const body=JSON.parse(options.body);assert.notEqual(body.request_key,body.preparation_key);return response(bound({format:'project_candidate_preparation_abandon_v1',origin_catalog_id:P,study_id:STUDY,preparation_key:body.preparation_key,preparation_operation:'study_execution.prepare_package',input_sha256:C,candidate:{kind:'candidate',catalog_id:P,id:CANDIDATE,sha256:NEXT},actor_id:ACTOR,reason:body.reason,observed_checkpoint:C,occurred_at:'2026-10-22T12:00:00+00:00',state:'abandoned'},NEXT));});await h.click('project-candidate-abandon');assert.equal(h.nodes.get('project-files-error').textContent,'');assert.match(h.nodes.get('project-files-status').textContent,/original staging and scientific facts remain/);
  }
  console.log('Candidate controller: 3 selected groups PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
