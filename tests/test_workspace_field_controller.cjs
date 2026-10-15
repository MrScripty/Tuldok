'use strict';
// Controlled transport and declarative arrays only. This is not an external producer or scientific qualification.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../static/workspace-service.js'),'utf8');
const sha=letter=>letter.repeat(64),deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no;});return {promise,resolve,reject};};
function index(run='run') {
  const checkpoints=[16,32].map((update,i)=>({checkpoint:{sha256:sha(i?'b':'a')},clocks:{optimizer_update:update,epoch:null,fit_pass:null,physical_time:null,wall_elapsed_ms:update},selected:i===1}));
  return {state:'verified',validation:'structural_and_identity_closure; numerical_acceptance_is_separate',manifest:{producer:{run_id:run}},checkpoint_index:{entries:checkpoints},checkpoints:checkpoints.map(item=>({clocks:item.clocks})),probe:{split:'validation',members:[0,1].map(ordinal=>({ordinal,frozen_reference:{member_id:'source-'+ordinal,input:'authored-input',split:'validation'},input_sha256:sha('c'),target_sha256:sha('d')}))},metric_definitions:[{id:'authored_quantity',units:'declared-unit',direction:'minimize'}],observations:checkpoints.map((entry,i)=>({checkpoint_sha256:entry.checkpoint.sha256,metric_id:'authored_quantity',state:i?'undefined':'observed',value:0,reason:'declared_undefined_rule'})),model_definition:{opaque_authored_definition:'No architecture interpreted by host'},fields:checkpoints.flatMap(entry=>[0,1].flatMap(member_ordinal=>[['alien_one','first_stage'],['alien_three','first_stage'],['alien_two','different_stage']].map(([field_id,stage])=>({checkpoint_sha256:entry.checkpoint.sha256,member_ordinal,field_id,stage,shape_zyx:[2,3,4],units:'declared-unit'}))))};
}
function projected(body,run='run') {
  const value=index(run),record=value.fields.find(item=>item.checkpoint_sha256===body.checkpoint_sha256&&item.member_ordinal===body.member_ordinal&&item.field_id===body.field_id);
  const [row_axis,column_axis]={x:['z','y'],y:['z','x'],z:['y','x']}[body.axis],dimensions={x:4,y:3,z:2};
  const prediction=Array.from({length:dimensions[row_axis]},(_,row)=>Array.from({length:dimensions[column_axis]},(_,column)=>(body.checkpoint_sha256===sha('a')?100000:0)+({z:0,y:100,x:200}[body.axis])+body.index*10000+body.member_ordinal*1000+(body.field_id==='alien_one'?0:500)+row*10+column));
  const reference=prediction.map(row=>row.map(number=>number+100));
  return {...value,field:{...body,shape_zyx:record.shape_zyx,stage:record.stage,units:record.units,dtype:'<f8',centering:'cell',gauge_policy_sha256:sha('e'),gauge_policy:{mode:'authored_gauge',declared_value:0},time_units:'not_applicable',grid:{units:'m'},row_axis,column_axis,physical_origin:[2,3,5],physical_row_step:[0,3,0],physical_column_step:[2,0,0],prediction,reference}};
}
function fixture({canvas=false,resize=false}={}){
  const calls=[],nodes={},observers=[];let handler,active=true,html='';
  const root={querySelectorAll:()=>[nodes['#field-prediction']?.parentElement,nodes['#field-reference']?.parentElement].filter(Boolean),querySelector(selector){const node=nodes[selector]||(nodes[selector]={id:selector.slice(1),style:{},textContent:'',addEventListener(kind,fn){this[kind]=fn;},focus(){},setAttribute(){}});if(canvas&&['#field-prediction','#field-reference'].includes(selector)){node.parentElement={clientWidth:300,clientHeight:200};node.getContext=()=>({createImageData:(columns,rows)=>({data:new Uint8ClampedArray(columns*rows*4)}),putImageData(){node.draws=(node.draws||0)+1;}});}return node;}};
  const window={workspaceEscape:value=>String(value??'').replaceAll('<','&lt;')};
  vm.runInNewContext(source,{window,history:{state:{}},document:{activeElement:null},CSS:{escape:String},structuredClone,...(resize?{ResizeObserver:class{constructor(callback){this.callback=callback;observers.push(this);}observe(){}disconnect(){this.disconnected=true;}}}:{})});
  const ui=window.WorkspaceFieldEvidence({api:async(route,body,version)=>{calls.push({route,body,version});return handler(route,body);},announce:()=>{}}),run={id:'run',state:'completed',graph:{recipe:'external_recipe'}};
  const render=()=>{html=ui.html(run);ui.bind(root,run,render,()=>active);};
  return {ui,run,calls,nodes,observers,render,html:()=>html,handler:value=>handler=value,stop(){active=false;ui.invalidate();}};
}
(async()=>{
  const f=fixture();f.handler(async(route,body)=>body.field_id?projected(body):index());await f.ui.load(f.run,()=>true);f.render();
  assert.match(f.html(),/Linked field evidence/);assert.match(f.html(),/Time units: <strong>not_applicable/);assert.match(f.html(),/Gauge policy SHA256 e{64}/);assert.match(f.html(),/authored_gauge/);assert.match(f.html(),/declared_value/);assert.match(f.html(),/Update 16/);assert.match(f.html(),/Update 32/);assert.match(f.html(),/>0<\/td>/);assert.match(f.html(),/Undefined: declared_undefined_rule/);
  assert.match(f.html(),/alien_one/);assert.match(f.html(),/different_stage/);assert.doesNotMatch(f.html(),/simulation frame<select|field-frame/);
  assert.match(f.html(),/Difference unavailable/);assert.match(f.html(),/Scientific test access is unsupported/);assert.match(f.html(),/Physical acceptance is not established/);
  assert.ok(f.calls.every(call=>call.version===2));assert.deepEqual(JSON.parse(JSON.stringify(f.calls[1].body)),{checkpoint_sha256:sha('b'),member_ordinal:0,field_id:'alien_one',axis:'z',index:0,split:'validation'});
  assert.match(f.nodes['#field-scale'].textContent,/Shared display grayscale range 0 to 123/);
  f.nodes['#field-probe-row'].input({target:{value:'1'}});f.nodes['#field-probe-column'].input({target:{value:'2'}});
  assert.match(f.nodes['#field-probe-result'].innerHTML,/prediction <strong>12<\/strong>; reference <strong>112<\/strong>/);
  assert.match(f.nodes['#field-probe-result'].innerHTML,/Display coordinates \(6, 6, 5\) m/);
  f.nodes['#field-axis'].change({target:{value:'x'}});await new Promise(setImmediate);assert.equal(f.calls.at(-1).body.axis,'x');assert.equal(f.calls.at(-1).body.index,0);assert.match(f.html(),/id="field-probe-row"[^>]*value="1"/);assert.match(f.html(),/id="field-probe-column"[^>]*value="2"/);
  f.nodes['#field-stage'].change({target:{value:'different_stage'}});await new Promise(setImmediate);assert.equal(f.calls.at(-1).body.field_id,'alien_two');
  const before=f.calls.length;f.nodes['#field-index'].change({target:{value:'999'}});await new Promise(setImmediate);assert.equal(f.calls.length,before);assert.match(f.html(),/Choose an integer slice index/);assert.doesNotMatch(f.html(),/id="field-prediction"/);
  for(const selector of ['field-checkpoint','field-member','field-stage','field-id','field-axis','field-index']){
    const r=fixture(),first=deferred(),second=deferred();let pending=0;
    r.handler(async(route,body)=>body.field_id?projected(body):index());await r.ui.load(r.run,()=>true);r.render();
    r.handler((route,body)=>++pending===1?first.promise:second.promise);
    r.nodes['#field-index'].change({target:{value:'1'}});
    assert.doesNotMatch(r.html(),/id="field-prediction"/,'Pending query removes earlier arrays');
    const chosen={'field-checkpoint':sha('a'),'field-member':'1','field-stage':'different_stage','field-id':'alien_three','field-axis':'x','field-index':'0'}[selector];
    r.nodes['#'+selector].change({target:{value:chosen}});
    const old=r.calls.at(-2).body,latest=r.calls.at(-1).body;
    if(selector==='field-checkpoint'){first.resolve(projected(old));await new Promise(setImmediate);assert.doesNotMatch(r.html(),/id="field-prediction"/);assert.match(r.html(),/id="field-load" disabled/);second.resolve(projected(latest));await new Promise(setImmediate);}
    else{second.resolve(projected(latest));await new Promise(setImmediate);first.resolve(projected(old));await new Promise(setImmediate);}
    assert.match(r.html(),/id="field-prediction"/);assert.doesNotMatch(r.html(),/id="field-load" disabled/);
    assert.ok(r.html().includes(`value="${latest.checkpoint_sha256}" selected`));
    assert.match(r.html(),new RegExp('prediction <strong>'+projected(latest).field.prediction[0][0]+'<'));
    assert.ok(r.html().includes('Standalone slice '+latest.axis.toUpperCase()+' '+latest.index));
  }
  const late=fixture(),held=deferred();late.handler(()=>held.promise);const loading=late.ui.load(late.run,()=>true);late.stop();held.resolve(index());await loading;assert.equal(late.ui.html(late.run),'');
  const denied=fixture({canvas:true,resize:true});denied.handler(async(route,body)=>body.field_id?projected(body):index());await denied.ui.load(denied.run,()=>true);denied.render();
  const deniedObserver=denied.observers.at(-1);denied.handler(async()=>{throw Object.assign(Error('Evidence read revoked'),{status:403});});denied.nodes['#field-axis'].change({target:{value:'y'}});await new Promise(setImmediate);
  assert.equal(deniedObserver.disconnected,true,'Denied rerender releases detached field viewports');assert.match(denied.html(),/Evidence read revoked/);assert.doesNotMatch(denied.html(),/id="field-prediction"|authored_quantity|field-checkpoint/,'Denied read clears cached arrays and scalar values');
  const bad=fixture();bad.handler(async(route,body)=>body.field_id?{...projected(body),field:{...projected(body).field,checkpoint_sha256:sha('c')}}:index());await bad.ui.load(bad.run,()=>true);bad.render();assert.match(bad.html(),/does not match the exact/);assert.doesNotMatch(bad.html(),/id="field-prediction"/);
  const time=fixture();time.handler(async()=>{const value=index();value.checkpoints[0].clocks.physical_time=1;return value;});await time.ui.load(time.run,()=>true);time.render();assert.match(time.html(),/no physical timeline is qualified/);
  const unsupported=fixture();unsupported.handler(async()=>({state:'unsupported',reason:'No retained field evidence from this legacy external recipe.'}));await unsupported.ui.load(unsupported.run,()=>true);unsupported.render();assert.match(unsupported.html(),/legacy external recipe/);assert.doesNotMatch(unsupported.html(),/field-selectors|field-prediction/);
  const fit=fixture({canvas:true,resize:true});fit.handler(async(route,body)=>body.field_id?projected(body):index());await fit.ui.load(fit.run,()=>true);fit.render();
  for(const key of ['prediction','reference']){const style=fit.nodes['#field-'+key].style;assert.ok(parseFloat(style.width)<=300&&parseFloat(style.height)<=200);assert.ok(Math.abs(parseFloat(style.width)/parseFloat(style.height)-(4/3)*(2/3))<1e-12);}
  const previousObserver=fit.observers.at(-1);fit.nodes['#field-axis'].change({target:{value:'x'}});await new Promise(setImmediate);
  const draws=fit.nodes['#field-prediction'].draws;previousObserver.callback();assert.equal(fit.nodes['#field-prediction'].draws,draws,'Detached observer cannot redraw a new slice');assert.equal(previousObserver.disconnected,true);
  const currentObserver=fit.observers.at(-1);fit.stop();currentObserver.callback();assert.equal(fit.nodes['#field-prediction'].draws,draws,'Invalidated observer cannot draw');assert.equal(currentObserver.disconnected,true);
  const thin=fixture({canvas:true});thin.handler(async(route,body)=>{if(!body.field_id)return index();const value=projected(body);value.field.physical_row_step=[0,1e12,0];value.field.physical_column_step=[1,0,0];return value;});await thin.ui.load(thin.run,()=>true);thin.render();
  assert.equal(thin.nodes['#field-prediction'].hidden,true);assert.match(thin.nodes['[data-field-display="prediction"]'].textContent,/cannot be represented at this viewport resolution/);assert.match(thin.html(),/id="field-probe-row"/,'Unrepresentable aspect preserves exact numeric probe');
  for(const change of [field=>delete field.gauge_policy,field=>field.gauge_policy={},field=>field.gauge_policy=[],field=>field.gauge_policy={nested:{not_finite:Infinity}},field=>field.gauge_policy={nested:[NaN]},field=>field.gauge_policy_sha256='not-a-digest',field=>delete field.time_units,field=>field.time_units='s']){
    const invalid=fixture();invalid.handler(async(route,body)=>{if(!body.field_id)return index();const value=projected(body);change(value.field);return value;});await invalid.ui.load(invalid.run,()=>true);invalid.render();assert.match(invalid.html(),/gauge policy or standalone time units/);assert.doesNotMatch(invalid.html(),/id="field-prediction"|id="field-gauge-policy"/,'No invented gauge/time default after invalid projection');
  }
  console.log('PASS external field UI: exact declared selectors, shared display range, exact numeric probes, stale selector/navigation exclusion, revoked-value clearing and unsupported legacy/physical time. Controlled transport only.');
})().catch(error=>{console.error(error);process.exitCode=1;});
