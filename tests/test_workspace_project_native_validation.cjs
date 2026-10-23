'use strict';
// Only native truth-field consistency; real process/science is owner-qualified separately.
const assert=require('node:assert/strict');
const {mount,bound,response,tick,C,NEXT}=require('./test_workspace_project_files_m4.cjs');
const G='1'.repeat(32),graph={id:G,name:'Saved native graph',recipe:'torch_image_classifier_v1',revision:2};
const valid=()=>({status:'valid',valid:true,errors:[],validation_token:C,graph_revision:2,execution_sha256:NEXT,release:{id:C},runtime:{available:true}});
const failure={status:'unavailable',valid:false,errors:[{path:'',message:'Current CPU is unavailable',code:'unavailable'}],validation_token:null,release:null,runtime:{available:false}};
function confirm(h){const el=h.nodes.get('project-native-probe-confirm');el.checked=true;el.listeners.get('change')({target:el});}
async function fixture(){const h=mount();await tick();h.answers.push(response(bound({items:[graph],total:1,offset:0,limit:40})));await h.click('project-native-graphs');confirm(h);return h;}
(async()=>{
  const invalid=[
    {status:'invalid',valid:true,errors:[7],release:null,runtime:null},
    {status:'invalid'},{errors:[{path:'runtime',message:'Unavailable',code:'unavailable'}]},
    {release:null},{runtime:null},{runtime:{available:false}},{runtime:{available:1}},
    {valid:false,status:'invalid',errors:[],validation_token:null},
    {...failure,errors:[7]},{...failure,status:'other'},{...failure,errors:[{path:'',message:'bad',code:'unavailable',extra:true}]},
    {...failure,errors:[{path:7,message:'bad',code:'unavailable'}]},
    {...failure,errors:[{path:'',message:'x'.repeat(2001),code:'unavailable'}]},
    {...failure,errors:Array.from({length:101},()=>failure.errors[0])},
    {execution_sha256:Number('7'.repeat(64))},{validation_token:Number('7'.repeat(64))},
    {execution_sha256:true},{validation_token:true},
  ];
  for(const change of invalid){const h=await fixture();h.answers.push(response(bound({...valid(),...change},NEXT)));await h.submit('project-native-preflight-form');assert.match(h.nodes.get('project-files-error').textContent,/Native validation differs/);assert.equal(h.nodes.get('project-native-submit-fields').disabled,true);const count=h.requests.length;await tick();assert.equal(h.requests.length,count,'No automatic submit after a contradictory result');}
  {
    const h=await fixture();h.answers.push(response(bound({...valid(),...failure},NEXT)));await h.submit('project-native-preflight-form');assert.equal(h.nodes.get('project-files-error').textContent,'');assert.equal(h.nodes.get('project-native-submit-fields').disabled,true);assert.match(h.nodes.get('project-files-status').textContent,/reported errors/);
  }
  {
    const h=await fixture();h.answers.push(response(bound(valid(),NEXT)));await h.submit('project-native-preflight-form');assert.equal(h.nodes.get('project-native-submit-fields').disabled,false);
    confirm(h);h.answers.push(response(bound({...valid(),errors:[7]},NEXT)));await h.submit('project-native-preflight-form');assert.match(h.nodes.get('project-files-error').textContent,/Native validation differs/);assert.equal(h.nodes.get('project-native-submit-fields').disabled,true,'A new invalid observation cannot leave the previous submit proof enabled at the same checkpoint');
  }
  console.log('Native validation consistency: 18 negative replies + typed failure + prior-proof invalidation PASS');
})().catch(error=>{console.error(error);process.exitCode=1;});
