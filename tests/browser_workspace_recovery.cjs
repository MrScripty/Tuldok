// Browser regression tests with explicitly mocked service transport.
// No training or backend execution evidence is claimed by this suite.
"use strict";
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),http=require('node:http'),{spawn}=require('node:child_process');
const {waitForDebugger}=require('./browser_startup.cjs');
const deadline=setTimeout(()=>{console.error('UI recovery gate exceeded 45 seconds');process.exit(1)},45000);
const dir=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-review-ui-'));let ws,browser,server;
const pause=ms=>new Promise(r=>setTimeout(r,ms));
(async()=>{
server=http.createServer((req,res)=>res.end('<div id="p"></div><div id="r"></div>'));await new Promise(r=>server.listen(0,'127.0.0.1',r));
browser=spawn(process.env.BROWSER || '/usr/bin/chromium',['--headless','--no-sandbox','--disable-gpu','--no-first-run','--remote-debugging-port=0','--user-data-dir='+dir,'about:blank'],{stdio:'ignore'});
const port=await waitForDebugger(browser,path.join(dir,'DevToolsActivePort')),tabs=await(await fetch('http://127.0.0.1:'+port+'/json')).json();ws=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);await new Promise(r=>ws.onopen=r);
let id=0;const pending=new Map();ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(m.error):p.resolve(m.result)}};
const send=(method,params={})=>new Promise((resolve,reject)=>{pending.set(++id,{resolve,reject});ws.send(JSON.stringify({id,method,params}))});
const ev=async expression=>{const x=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(x.exceptionDetails)throw Error(JSON.stringify(x.exceptionDetails));return x.result.value;};
await send('Page.enable');await send('Page.navigate',{url:'http://127.0.0.1:'+server.address().port+'/'});await pause(150);
await ev(`window.workspaceEscape=s=>String(s??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');window.calls=[];window.notes=[];const types=['release','validate','train','evaluate','publish'];
window.g={id:'a'.repeat(32),name:'Recipe',revision:1,nodes:types.map(type=>({id:type,type,definition_version:1,parameters:type==='train'?{epochs:1,batch_size:8,learning_rate:.001,seed:42}:type==='release'?{release_id:'b'.repeat(64)}:{}})),edges:[]};
window.a={id:'c'.repeat(32),state:'completed',graph:g,graph_revision:1,attempt:1,release_id:'b'.repeat(64),created_at:'now',artifacts:[],test_exposure:{exposed:true},progress:{stage:'completed'}};
window.b={...structuredClone(a),id:'d'.repeat(32),test_exposure:{exposed:false}};window.list=[a];
window.fetch=async(url,options)=>{const route=url.replace('/api/workspace/','');calls.push(route);let value,status=200;
// Match the image_training.PARAMETER_BOUNDS published by Pipelines.definitions.
if(route.startsWith('experiment-lineage?'))value={revision:'f'.repeat(64),nodes:[],related:[],next_cursor:null,limit:20,cohort:null};
else if(route==='definitions')value={recipe:types,nodes:types.map(type=>({type,input:'i',output:'o'})),parameter_bounds:{
epochs:{minimum:1,maximum:5,default:1,type:'integer'},
batch_size:{minimum:1,maximum:16,default:8,type:'integer'},
learning_rate:{minimum:0.00001,maximum:0.01,default:0.001,type:'number'},
seed:{minimum:0,maximum:4294967295,default:42,type:'integer'}}};
else if(route==='releases')value=[{id:'b'.repeat(64),status:'available',records:6}];else if(route==='graphs')value=[g];else if(route==='context')value={dataset_id:'e'.repeat(32)};
else if(route.endsWith('/validate'))value={valid:true,status:'valid',validation_token:'token'};
else if(route==='runs'&&options?.method==='POST'){list=[b,a];value=b;}else if(route==='runs')value=list;
else if(route==='runs/'+a.id)value=a;else if(route==='runs/'+b.id)value=b;
else if(route.includes('/predictions')){if(route.includes(b.id)&&route.endsWith('split=test')){status=409;value={code:'conflict',error:'Record an explicit test-set exposure first.'}}else value={class_vocabulary:[{label:'circle'}],rows:[]};}
else value={};return {ok:status===200,status,json:async()=>structuredClone(value)}};`);
await ev(fs.readFileSync(path.resolve(__dirname,'../static/workspace-external.js'),'utf8'));
await ev(fs.readFileSync(path.resolve(__dirname,'../static/workspace-service.js'),'utf8'));
await ev(fs.readFileSync(path.resolve(__dirname,'../static/experiment-lineage.js'),'utf8'));
await ev(fs.readFileSync(path.resolve(__dirname,'../static/workspace-phase-timings.js'),'utf8'));
await ev(fs.readFileSync(path.resolve(__dirname,'../static/workspace-scientific-comparison.js'),'utf8'));
await ev(fs.readFileSync(path.resolve(__dirname,'../static/workspace-real.js'),'utf8'));
await ev(`window.real=WorkspaceReal({pipelineRoot:document.getElementById('p'),runsRoot:document.getElementById('r'),announce:s=>notes.push(s),openRecord:()=>{},openRun:()=>real.show('runs')});real.show('runs')`);
if(!await ev(`!!document.getElementById('real-test-predictions')`))throw Error(await ev(`document.getElementById('r').innerText`));
await ev(`document.getElementById('real-test-predictions').click()`);await pause(100);
await ev(`real.show('pipeline')`);
const renderedPipeline=await ev(`({validateReady:!!document.getElementById('real-validate')&&!document.getElementById('real-validate').disabled,
parameters:[...document.querySelectorAll('#p [data-param]')].map(input=>[input.dataset.param,input.min,input.max,input.step,input.value]),
error:document.querySelector('#p .error-panel')?.textContent||null})`);
const expectedParameters=[
['epochs','1','5','1','1'],
['batch_size','1','16','1','8'],
['learning_rate','0.00001','0.01','any','0.001'],
['seed','0','4294967295','1','42']];
if(!renderedPipeline.validateReady||renderedPipeline.error||JSON.stringify(renderedPipeline.parameters)!==JSON.stringify(expectedParameters)){
throw Error('Image Pipeline fixture did not render its parameter contract: '+JSON.stringify({...renderedPipeline,visibleText:await ev(`document.getElementById('p').innerText`)}));
}
console.log('PASS: mocked image Pipeline renders exact parameter min/max/step/defaults and ready Validate control. '+JSON.stringify(renderedPipeline));
await ev(`document.getElementById('real-validate').onclick()`);await ev(`document.getElementById('real-submit').onclick()`);await pause(200);
const result=await ev(`({newRunPredictionRequests:calls.filter(x=>x.includes(b.id)&&x.includes('predictions')),completedControlsVisible:!!document.getElementById('real-test-predictions'),visibleText:document.getElementById('r').innerText.slice(0,180)})`);console.log(JSON.stringify(result));
if(result.newRunPredictionRequests.some(x=>x.endsWith('split=test'))||!result.completedControlsVisible)throw Error('Sticky test split still broken');
console.log('PASS: exposed test view on A → new submission B opens validation with completed controls. UI mocked transport only.');
await ev(`window.baseFetch=fetch;window.fetch=async(url,options)=>url.includes('/predictions?')?{ok:false,status:503,json:async()=>({code:'unavailable',error:'Injected prediction fetch failure'})}:baseFetch(url,options);real.show('runs')`);
const isolated=await ev(`({state:document.getElementById('real-run-state')?.textContent,hasExposeControl:!!document.getElementById('real-test-predictions'),typedErrorVisible:document.getElementById('r').innerText.includes('Predictions unavailable: Injected prediction fetch failure')})`);
console.log(JSON.stringify(isolated));if(isolated.state!=='completed'||!isolated.hasExposeControl||!isolated.typedErrorVisible)throw Error('Prediction fetch failure discarded valid run detail');
console.log('PASS: prediction-fetch failure preserves completed run details and controls with inline error.');
await ev(`b.metrics=null;b.artifact_status={status:'unavailable',message:'Injected artifact tamper'};window.fetch=async(url,options)=>url==='/api/workspace/runs/'+b.id?{ok:false,status:409,json:async()=>({code:'unavailable',error:'Injected artifact tamper'})}:baseFetch(url,options);real.show('runs')`);
const damaged=await ev(`({runButtons:document.querySelectorAll('[data-real-run]').length,artifactWarning:document.getElementById('r').innerText.includes('Published artifacts unavailable: Injected artifact tamper'),metricCards:document.querySelectorAll('.metric').length})`);console.log(JSON.stringify(damaged));if(damaged.runButtons!==2||!damaged.artifactWarning||damaged.metricCards)throw Error('Damaged run blocked navigation or exposed metrics');
await ev(`document.querySelector('[data-real-run="'+a.id+'"]').click()`);await pause(150);
if(!await ev(`document.getElementById('real-run-'+a.id).getAttribute('aria-current')==='true' && document.getElementById('real-run-state').textContent==='completed'`))throw Error('Healthy run not selectable after damaged detail');
console.log('PASS: damaged selected run retains list/warning, no metrics, and healthy run remains selectable.');
})().catch(e=>{console.error(e);process.exitCode=1}).finally(async()=>{clearTimeout(deadline);if(ws)ws.close();if(browser)browser.kill();if(server)server.close();await pause(150);fs.rmSync(dir,{recursive:true,force:true})});
