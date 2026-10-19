'use strict';
// Actual project controllers and Chromium focus/polling; synthetic transport only.
// No catalog, recipe execution, authoring mutation, or scientific qualification.
const assert=require('node:assert/strict'),fs=require('node:fs'),http=require('node:http'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process');
const {waitForDebugger}=require('./browser_startup.cjs');
const root=path.resolve(__dirname,'..'),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-project-observation-'));
const id='a'.repeat(32),sha='b'.repeat(64),changedSha='c'.repeat(64),roles=['task','model','trainer','evaluator','view'];
const recipeContract='recipes.inspect/4/0080ae0e39bf758b9c96c3208ef1614a9335f257731cfde935a23d8b486dedb1',recipeHeaders=[];
const reference={id:'recipe',label:'Authored recipe',path:'recipe.json',status:'available',integrity:'verified',observed_sha256:sha};
let observation={schema_version:2,id,name:'Authored observation fixture',mode:'inspection',execution:'unsupported',manifest_status:'unchanged',manifest_sha256:sha,data:[],recipes:[reference],evidence:[{id:'note',label:'Live evidence',path:'note.txt',status:'available',integrity:'unverified',observed_sha256:sha}],requirements:[],activity:{available:true,phase:'Fixture',message:'External observation',state:'running',producer:'Authored fixture',updated_at:new Date().toISOString(),progress:{completed:1,total:2}}};
const selection=Object.fromEntries(roles.map(kind=>[kind,{id:kind,version:'1',sha256:sha}]));
const inspection={definition:{schema_version:3,format:'external_model_evidence_recipe_v2',name:'Authored bound recipe',extension_selection:{selections:selection},model_evidence:{model_specification:{configuration:{}}}},extension_binding:{format:'tuldok_extension_binding_v1',project:{id,manifest_sha256:sha},selections:Object.values(selection),contributions:roles.map(kind=>({kind,...selection[kind],definition:{label:kind,parameters:{type:'object',properties:{},additionalProperties:false}},provider:{id:'provider',reference_id:'provider'}}))},model_task:'authored',selection_policy:{},parameter_definitions:{},inputs:{}};
const html=`<!doctype html><title>Project observation regression</title><body>
<select id="source"><option value="project:${id}">Authored project</option><option value="catalog">Catalog</option></select><button id="elsewhere">Other task</button>
<div id="data"></div><div id="pipeline"></div><div id="runs"></div>
<dialog id="project-import-dialog"><button id="project-import-close"></button><form id="project-import-form"></form><button id="project-import-submit"></button></dialog>
<dialog id="project-open-dialog"><button id="project-open-close"></button><button id="project-roots-refresh"></button><form id="project-open-form"></form><select id="project-root"></select><button id="project-open-submit"></button><p id="project-open-status"></p><input id="project-manifest"></dialog><button id="open-project"></button>
<script>window.workspaceEscape=value=>String(value??'').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');window.TuldokAuth={identity:()=>({kind:'owner',actor_id:'fixture-owner',credential_id:'fixture-session'}),fetch:(...args)=>fetch(...args)};</script>
<script src="/workspace-service.js"></script><script src="/workspace-external.js"></script><script src="/workspace-project-activity.js"></script><script src="/workspace-projects.js"></script>
<script>window.projectUI=WorkspaceProjects({select:document.getElementById('source'),roots:Object.fromEntries(['data','pipeline','runs'].map(name=>[name,document.getElementById(name)])),announce(){},switchSource(){},contextChanged(){},openCatalogRecord(){},openExternalGraph(){},openExternalRun(){}});window.showProject=view=>projectUI.show(document.getElementById('source').value,view);</script>`;
let snapshotReads=0,recipeReads=0,ordinaryReads=0,holdRecipe=0,heldRecipe=null,holdEvidence=false,heldEvidence=null,mutations=0;
function reply(response,value){response.setHeader('Content-Type','application/json');response.end(JSON.stringify(value));}
const server=http.createServer((request,response)=>{
  if(request.method!=='GET'){mutations++;response.writeHead(405);response.end();return;}
  if(request.url==='/'){response.setHeader('Content-Type','text/html');response.end(html);return;}
  if(['/workspace-service.js','/workspace-external.js','/workspace-project-activity.js','/workspace-projects.js'].includes(request.url)){response.setHeader('Content-Type','text/javascript');response.end(fs.readFileSync(path.join(root,'static',request.url.slice(1))));return;}
  if(request.url==='/api/workspace/project-snapshots/'+id){snapshotReads++;reply(response,observation);return;}
  if(request.url.startsWith('/api/workspace/projects/'+id+'/recipes/')){
    recipeHeaders.push(request.headers['tuldok-operation-contract']);
    if(recipeHeaders.at(-1)!==recipeContract){response.statusCode=409;reply(response,{error:'Expected current recipe inspection contract',code:'unsupported'});return;}
    if(request.url.includes('/recipes/ordinary?')){ordinaryReads++;reply(response,{definition:{schema_version:1,format:'external_recipe_v1',name:'Authored CPU restore recipe',runtime:'managed_torch_python_v1'},inputs:{},parameter_definitions:{}});return;}
    recipeReads++;if(recipeReads===holdRecipe){heldRecipe=()=>reply(response,inspection);return;}
    reply(response,inspection);return;
  }
  if(request.url==='/api/workbench/releases/input-candidates'){reply(response,{releases:[]});return;}
  if(request.url==='/api/workspace/run-artifact-inputs'){reply(response,{runs:[]});return;}
  if(request.url==='/api/workspace/projects/'+id+'/evidence/note'){
    const value={id:'note',external:true,label:'Live evidence',text:'Evidence '+observation.evidence[0].observed_sha256,sha256:observation.evidence[0].observed_sha256};
    if(holdEvidence){holdEvidence=false;heldEvidence=()=>reply(response,value);return;}
    reply(response,value);return;
  }
  response.writeHead(404);response.end();
});
let browser,ws,send,evaluate;const errors=[],checks=[],failures=[];
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn,message){for(let i=0;i<200;i++){if(await fn())return;await pause(50);}throw Error(message||'Timed out');}
function check(name,value){checks.push({name,passed:value});if(!value)failures.push(name);}
(async()=>{
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));const base='http://127.0.0.1:'+server.address().port;
  browser=spawn(process.env.BROWSER||'/usr/bin/chromium',['--headless','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--user-data-dir='+temporary,'about:blank'],{stdio:'ignore',env:{...process.env,XDG_CONFIG_HOME:temporary,XDG_CACHE_HOME:temporary}});
  const port=await waitForDebugger(browser,path.join(temporary,'DevToolsActivePort'));
  const tabs=await(await fetch('http://127.0.0.1:'+port+'/json')).json();
  ws=new WebSocket(tabs.find(tab=>tab.type==='page'&&tab.url==='about:blank').webSocketDebuggerUrl);await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  let sequence=0;const pending=new Map();
  send=(method,params={})=>new Promise((resolve,reject)=>{const key=++sequence,timer=setTimeout(()=>{pending.delete(key);reject(Error('CDP timeout: '+method));},10000);pending.set(key,{resolve:value=>{clearTimeout(timer);resolve(value);},reject:error=>{clearTimeout(timer);reject(error);}});ws.send(JSON.stringify({id:key,method,params}));});
  ws.onmessage=event=>{const value=JSON.parse(event.data);if(value.id){const task=pending.get(value.id);if(task){pending.delete(value.id);value.error?task.reject(value.error):task.resolve(value.result);}}if(value.method==='Runtime.exceptionThrown')errors.push(value.params.exceptionDetails);};
  evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  async function activate(selector){await evaluate(`document.querySelector(${JSON.stringify(selector)}).focus()`);for(const type of ['keyDown','keyUp'])await send('Input.dispatchKeyEvent',{type,key:'Enter',code:'Enter',windowsVirtualKeyCode:13,...(type==='keyDown'?{text:'\r',unmodifiedText:'\r'}:{})});}
  const text=selector=>evaluate(`document.querySelector(${JSON.stringify(selector)})?.textContent`);
  async function observe(next){const before=snapshotReads;observation=next;await until(()=>snapshotReads>before,'Project did not poll');await pause(50);}
  await send('Runtime.enable');await send('Page.navigate',{url:base});await until(()=>evaluate('typeof showProject==="function"'));
  await evaluate('showProject("runs")');await until(()=>evaluate('!!document.querySelector("[data-project-evidence]")'));
  await activate('[data-project-evidence]');await until(()=>text('#runs .project-evidence-output pre'));
  assert.equal(await evaluate('document.activeElement.tagName'),'H3');
  await observe({...observation,evidence:[{...observation.evidence[0],observed_sha256:changedSha}]});
  await until(()=>text('#runs .project-evidence-output pre').then(value=>value==='Evidence '+changedSha));
  check('Auto evidence refresh preserves focus inside the preview',await evaluate('document.activeElement===document.querySelector("#runs .project-evidence-output h3")'));
  holdEvidence=true;const before=snapshotReads;observation={...observation,evidence:[{...observation.evidence[0],observed_sha256:sha}]};await until(()=>heldEvidence&&snapshotReads>before,'Evidence refresh was not held');
  await evaluate('document.getElementById("elsewhere").focus()');heldEvidence();heldEvidence=null;
  await until(()=>text('#runs .project-evidence-output pre').then(value=>value==='Evidence '+sha));
  check('A completed background refresh does not steal separately moved focus',await evaluate('document.activeElement.id==="elsewhere"'));
  await evaluate('document.querySelector("#runs .project-evidence-output h3").focus()');
  await observe({...observation,evidence:[{...observation.evidence[0],status:'missing',observed_sha256:undefined}]});
  check('Missing selected evidence clears stale text and retains preview focus',await evaluate('!document.querySelector("#runs .project-evidence-output pre")&&document.activeElement===document.querySelector("#runs .project-evidence-output")'));
  await evaluate('showProject("pipeline")');await until(()=>evaluate('!!document.querySelector("[data-project-recipe]")'));
  async function holdInner(){holdRecipe=recipeReads+2;heldRecipe=null;await activate('[data-project-recipe]');await until(()=>heldRecipe,'Second recipe inspection was not held');}
  async function releaseInner(){heldRecipe();heldRecipe=null;await pause(100);}
  await holdInner();await observe({...observation});await releaseInner();
  check('Same-identity polling preserves the pending inner inspection',await evaluate('!!document.getElementById("extension-prepare")&&document.getElementById("extension-model-dialog").open'));
  await activate('#extension-model-close');
  for(const [name,change] of [
    ['unavailable recipe',{recipes:[{...reference,status:'unavailable'}]}],
    ['changed manifest source',{manifest_status:'changed'}],
  ]){
    await observe({...observation,manifest_status:'unchanged',recipes:[reference]});
    const before=recipeReads;holdRecipe=before+1;heldRecipe=null;
    await activate('[data-project-recipe]');await until(()=>heldRecipe,'Initial inspection was not held');
    await observe({...observation,...change});await releaseInner();
    check(name+' fences the initial inspection before opening the author',recipeReads===before+1&&await evaluate('!document.getElementById("extension-model-dialog").open'));
    if(await evaluate('document.getElementById("extension-model-dialog").open'))await activate('#extension-model-close');
  }
  for(const [name,change] of [
    ['changed recipe hash',{recipes:[{...reference,observed_sha256:changedSha}]}],
    ['declared identity mismatch',{recipes:[{...reference,integrity:'mismatch'}]}],
    ['unavailable recipe',{recipes:[{...reference,status:'unavailable'}]}],
    ['missing recipe',{recipes:[]}],
    ['changed manifest identity',{manifest_sha256:changedSha}],
    ['changed manifest source',{manifest_status:'changed'}],
  ]){
    await observe({...observation,manifest_sha256:sha,manifest_status:'unchanged',recipes:[reference]});
    await holdInner();await observe({...observation,...change});await releaseInner();
    check(name+' cancels the inner inspection before authoring',await evaluate('!document.getElementById("extension-model-dialog").open&&!document.getElementById("extension-prepare")'));
    if(await evaluate('document.getElementById("extension-model-dialog").open'))await activate('#extension-model-close');
  }
  await observe({...observation,manifest_sha256:sha,manifest_status:'unchanged',recipes:[reference]});
  await holdInner();await evaluate('document.getElementById("source").value="catalog";showProject("pipeline")');await releaseInner();
  check('Project-context changes cancel the inner inspection',await evaluate('!document.getElementById("extension-model-dialog").open'));
  const stopped=snapshotReads;await pause(1200);check('Leaving the project stops its polling lifetime',snapshotReads===stopped);
  observation={...observation,recipes:[{...reference,id:'ordinary'}]};
  await evaluate(`document.getElementById("source").value="project:${id}";showProject("pipeline")`);
  await until(()=>evaluate('!!document.querySelector("[data-project-recipe=ordinary]")'));
  await activate('[data-project-recipe=ordinary]');await until(()=>evaluate('!!document.querySelector("#external-create-form")'));
  check('Ordinary managed recipe inspection selects version 4 through both project and graph authoring',ordinaryReads===2&&await evaluate('document.getElementById("external-create-dialog").open'));
  await activate('#external-create-close');await evaluate('document.getElementById("source").value="catalog";showProject("pipeline")');
  check('Every current bound and ordinary recipe inspection uses the exact version 4 pin',recipeHeaders.length>2&&recipeHeaders.every(value=>value===recipeContract));
  assert.equal(mutations,0,'Observation regression must not submit any mutation');assert.deepEqual(errors,[]);
  console.log(JSON.stringify({scope:'Actual JavaScript/Chromium lifecycle and focus with synthetic observations; no catalog, execution or scientific qualification',browser:(await send('Browser.getVersion')).product,checks,mutations},null,2));
  assert.deepEqual(failures,[],'Project observation regressions');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{heldRecipe?.();heldEvidence?.();ws?.close();browser?.kill('SIGTERM');await new Promise(resolve=>server.close(resolve));});
