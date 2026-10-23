'use strict';
// Controlled HTTP/controller proof. Native filesystem capture has separate real
// PG/ELF evidence; this fixture never claims an executable Python environment.
const assert=require('node:assert/strict');
const {mount,state,records,bound,response,tick,B,P,ACTOR,C,NEXT}=require('./test_workspace_project_files_m4.cjs');
const inventory=()=>({format:'project_runtime_inspection_v1',source:'configured-cpu',inventory_sha256:C,profile:'captured_cpu_python_v1',python_version:'3.12',file_count:1,total_bytes:1,manifest_bytes:400,free_bytes:1000,packages:[{name:'numpy',version:'0.0'},{name:'torch',version:'0.0'}],launch:{python:'python/bin/python3.12',loader:'system/lib/ld.so',home:'python',stdlib:'python/lib/python3.12',dynload:'python/lib/python3.12/lib-dynload',packages:'packages',library_dirs:['system/lib']},files:{items:[{path:'python/bin/python3.12',bytes:1,sha256:C,mode:320,kind:'elf'}],offset:0,limit:40,total:1}});
function summary(key,complete=false){return {format:complete?'project_runtime_capture_v1':'project_runtime_capture_intent_v1',project_id:P,manifest_sha256:C,file_count:1,total_bytes:1,actor_id:ACTOR,observed_at:'2026-10-22T12:00:00+00:00',request_key:key,...(complete?{runtime_ref:{kind:'runtime',catalog_id:P,id:NEXT,sha256:NEXT}}:{})};}
async function inspect(h,checkpoint=C){h.answers.push(response(bound({items:[{source:'configured-cpu'}],total:1,offset:0,limit:40},checkpoint)));await h.click('project-runtime-sources');h.answers.push(response(bound(inventory(),checkpoint)));await h.click('project-runtime-inspect');}
function confirm(h){const checkbox=h.nodes.get('project-runtime-confirm');checkbox.checked=true;checkbox.listeners.get('change')({target:checkbox});}
(async()=>{
  {
    const h=mount();await tick();const initial=h.requests.length;assert.equal(h.nodes.get('project-runtime-capture').disabled,true);
    await inspect(h);assert.equal(h.requests.length,initial+2);assert.equal(h.requests.at(-1).options.method,'GET');assert.ok(h.requests.at(-1).url.includes('source=configured-cpu'));assert.equal(h.nodes.get('project-runtime-files').children.length,1);assert.match(h.nodes.get('project-runtime-layout').textContent,/"numpy"/);assert.equal(h.nodes.get('project-runtime-capture').disabled,true);
    h.input('project-runtime-reserve','0');confirm(h);assert.equal(h.nodes.get('project-runtime-capture').disabled,false);
    h.answers.push(({options})=>{const body=JSON.parse(options.body);assert.deepEqual(Object.keys(body).sort(),['binding','expected_checkpoint','expected_inventory_sha256','request_key','reserve_bytes','source'].sort());assert.equal(body.source,'configured-cpu');assert.equal(body.expected_inventory_sha256,C);assert.equal(body.reserve_bytes,0);return response(bound(summary(body.request_key,true),NEXT));});
    await h.submit('project-runtime-capture-form');assert.equal(h.nodes.get('project-files-error').textContent,'');assert.equal(h.nodes.get('project-runtime-confirm').checked,false);assert.match(h.nodes.get('project-files-status').textContent,/No project execution started/);
    const key=h.nodes.get('project-runtime-status-key').value;h.answers.push(response(bound({state:'captured',intent:summary(key),result:summary(key,true)},NEXT)));await h.submit('project-runtime-status-form');assert.match(h.nodes.get('project-files-status').textContent,/Current local readiness was not inspected/);
  }
  {
    const h=mount();await tick();await inspect(h);h.input('project-runtime-reserve','0');confirm(h);
    h.answers.push(()=>Promise.reject(Error('lost acknowledgement')));await h.submit('project-runtime-capture-form');const original=JSON.parse(h.requests.at(-1).options.body);
    assert.equal(h.nodes.get('project-runtime-status-key').value,original.request_key);assert.match(h.nodes.get('project-runtime-pending').textContent,new RegExp(original.request_key));
    h.answers.push(response(state(B,NEXT)),response(records(B,NEXT)));await h.click('project-files-refresh');await inspect(h,NEXT);confirm(h);
    h.answers.push(({options})=>{assert.deepEqual(JSON.parse(options.body),original);return response(bound(summary(original.request_key,true),NEXT));});await h.submit('project-runtime-capture-form');assert.equal(h.nodes.get('project-files-error').textContent,'');
  }
  {
    const h=mount();await tick();await inspect(h);h.input('project-runtime-status-key','capture-request-0001');
    h.answers.push(response(bound({state:'captured',intent:null,result:summary('capture-request-0001',true)})));await h.submit('project-runtime-status-form');assert.match(h.nodes.get('project-files-error').textContent,/Retained runtime status differs/);assert.equal(h.nodes.get('project-runtime-status').textContent,'');
  }
  {
    const h=mount();await tick();await inspect(h);h.input('project-runtime-reserve','0');confirm(h);
    h.answers.push(()=>Promise.reject(Error('lost acknowledgement')));await h.submit('project-runtime-capture-form');const original=JSON.parse(h.requests.at(-1).options.body);
    const recovery={...state(B,NEXT),state:'recovery_required',available_actions:['open'],recovery:{action:'open',root:'fixture',directory:'alpha',reason:'projection_unavailable',request_key:original.request_key}};
    h.answers.push(response(recovery));await h.click('project-files-refresh');assert.equal(h.nodes.get('project-runtime-capture-fields').disabled,true);assert.equal(h.nodes.get('project-runtime-retry').disabled,false);
    const count=h.requests.length;await tick();assert.equal(h.requests.length,count,'No automatic retry or inspection');
    h.answers.push(({options})=>{assert.deepEqual(JSON.parse(options.body),original);return response(bound(summary(original.request_key,true),NEXT));});await h.click('project-runtime-retry');assert.equal(h.nodes.get('project-files-error').textContent,'');assert.equal(h.nodes.get('project-runtime-retry').disabled,true);
  }
  {
    const h=mount();await tick();const key='stopped-capture-key',recovery={...state(),state:'recovery_required',available_actions:['open'],recovery:{action:'open',root:'fixture',directory:'alpha',reason:'projection_unavailable',request_key:key}};
    h.answers.push(response(recovery));await h.click('project-files-refresh');assert.equal(h.nodes.get('project-runtime-abandon-fields').disabled,false);h.input('project-runtime-abandon-key',key);
    const count=h.requests.length;await h.submit('project-runtime-abandon-form');assert.equal(h.requests.length,count);h.input('project-runtime-abandon-reason','Original source is gone; preserve partial bytes Ω');
    let abandoned;
    h.answers.push(({options})=>{const body=JSON.parse(options.body);assert.notEqual(body.request_key,key);assert.equal(body.capture_key,key);abandoned={format:'project_runtime_capture_abandon_v1',project_id:P,capture_key:key,input_sha256:NEXT,manifest_sha256:C,actor_id:ACTOR,reason:body.reason,observed_checkpoint:C,observed_at:'2026-10-22T12:00:00+00:00'};return response(bound(abandoned,NEXT));});await h.submit('project-runtime-abandon-form');assert.equal(h.nodes.get('project-files-error').textContent,'');assert.match(h.nodes.get('project-files-status').textContent,/partial bytes and scientific intent remain/);
    h.answers.push(response(bound({state:'abandoned',intent:summary(key),result:null,abandonment:abandoned},NEXT)));await h.submit('project-runtime-status-form');assert.equal(h.nodes.get('project-files-error').textContent,'');assert.match(h.nodes.get('project-files-status').textContent,/Current local readiness was not inspected/);
  }
  console.log('Runtime controller: 5 selected groups PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
