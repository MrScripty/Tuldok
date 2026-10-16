'use strict';
// Controlled read transport only. Actual retained A package/Run qualification is separate.
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../static/workspace-service.js'),'utf8');
const A='a'.repeat(32),B='b'.repeat(32),C='c'.repeat(32),D='d'.repeat(32),E='e'.repeat(32),F='f'.repeat(32),sha='1'.repeat(64);
const ref=id=>({kind:'candidate',catalog_id:C,id,sha256:sha});
const state=(candidate=D,run=A,phase='fresh_verified')=>({candidate:{ref:ref(candidate),run_id:run,checkpoint:{sha256:sha},candidate:{id:candidate,run_id:run,limitations:['Diagnostic only; no physical acceptance.']}},state:phase,
  packages:phase==='selected'?[]:[{run_id:E,sha256:sha,bytes:269170,artifact_name:'package.zip',url:'/ignored-untrusted-url'}],
  verifications:phase==='fresh_verified'?[{run_id:F,receipt:{verified:true,package_sha256:sha}}]:[]});
const deferred=()=>{let resolve,reject;const promise=new Promise((yes,no)=>{resolve=yes;reject=no});return {promise,resolve,reject};};
function fixture(){
  let handler,active=true,credential='owner-session',html='',run={id:A,dataset_id:C,state:'completed'},nodes={};const calls=[];
  const window={workspaceEscape:value=>String(value??'').replaceAll('<','&lt;'),TuldokAuth:{identity:()=>({credential_id:credential})}};
  vm.runInNewContext(source,{window,structuredClone});
  const ui=window.WorkspaceCandidatePackageEvidence({api:async(route,body)=>{calls.push({route,body});return handler(route,body);}});
  const root={querySelector(selector){if(!html.includes('id="'+selector.slice(1)+'"'))return null;return nodes[selector]||(nodes[selector]={addEventListener(event,fn){this[event]=fn;}});},querySelectorAll(){return [];}};
  const current=()=>active,render=()=>{html=ui.html(run);ui.bind(root,run,render,current,()=>{});};
  return {ui,calls,nodes,current,render,html:()=>html,run:()=>run,handler:fn=>handler=fn,select(value){ui.invalidate();run={id:value,dataset_id:C,state:'completed'};},navigate(){active=false;ui.invalidate();render();},session(){credential='other';ui.invalidate();render();}};
}
(async()=>{
  const ready=fixture();ready.handler(route=>route.includes('/candidates?')?{run_id:A,candidates:[ref(D)],next_cursor:null,limit:20}:state());
  await ready.ui.load(ready.run(),ready.current);ready.render();assert.match(ready.html(),/Package: complete/);assert.match(ready.html(),/Fresh inference: verified in a separate consumer Run/);
  assert.ok(ready.html().includes(E)&&ready.html().includes(F));assert.ok(ready.html().includes('/runs/'+E+'/artifacts/package.zip'));assert.ok(!ready.html().includes('/ignored-untrusted-url'));
  assert.doesNotMatch(ready.html(),/id="model-export-(prepare|approve|start|setup)|select-candidate|<form/);
  ready.handler(()=>{throw Object.assign(Error('Current read denied'),{status:403});});await ready.nodes['#external-package-refresh'].click();
  assert.match(ready.html(),/Current read denied/);assert.doesNotMatch(ready.html(),/Package: complete|Fresh inference: verified|download>/);

  const pending=fixture();pending.handler(route=>route.includes('/candidates?')?{run_id:A,candidates:[ref(D)],next_cursor:null,limit:20}:state(D,A,'package_complete'));
  await pending.ui.load(pending.run(),pending.current);pending.render();assert.match(pending.html(),/Package: complete/);assert.match(pending.html(),/Fresh inference: not verified/);assert.ok(!pending.html().includes(F));
  pending.select(B);pending.handler(()=>({run_id:B,candidates:[],next_cursor:null,limit:20}));await pending.ui.load(pending.run(),pending.current);pending.render();
  assert.match(pending.html(),/No retained candidate package evidence/);assert.doesNotMatch(pending.html(),/Package: complete|Download verified package/);

  const stale=fixture(),late=deferred();stale.handler(route=>route.includes('/candidates?')?{run_id:A,candidates:[ref(D)],next_cursor:null,limit:20}:late.promise);
  const old=stale.ui.load(stale.run(),stale.current);await new Promise(setImmediate);stale.select(B);stale.handler(()=>({run_id:B,candidates:[],next_cursor:null,limit:20}));await stale.ui.load(stale.run(),stale.current);late.resolve(state());await old;stale.render();assert.match(stale.html(),/No retained candidate/);assert.doesNotMatch(stale.html(),/Package: complete/);

  const foreign=fixture();foreign.handler(route=>route.includes('/candidates?')?{run_id:A,candidates:[ref(D)],next_cursor:null,limit:20}:state(D,B));await foreign.ui.load(foreign.run(),foreign.current);foreign.render();assert.match(foreign.html(),/does not belong/);assert.doesNotMatch(foreign.html(),/Package: complete/);
  const multiple=fixture();multiple.handler(route=>route.includes('/candidates?')?{run_id:A,candidates:[ref(D),ref(E)],next_cursor:null,limit:20}:route.includes('/'+D+'/')?state(D,A,'selected'):state(E,A,'package_complete'));
  await multiple.ui.load(multiple.run(),multiple.current);multiple.render();assert.match(multiple.html(),/Package: complete/);assert.ok(multiple.html().includes('value="'+E+'" selected'));
  multiple.navigate();assert.equal(multiple.html(),'');
  for(const item of [ready,pending,stale,foreign,multiple])assert.ok(item.calls.every(call=>call.body===undefined),'Passive package view must never POST');
  console.log('PASS controlled external package view: owned discovery, pending versus fresh state, source identity, denial/stale clearing and passive-only reads.');
})().catch(error=>{console.error(error);process.exitCode=1;});
