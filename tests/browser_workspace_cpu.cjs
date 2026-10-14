'use strict';
// Actual frozen-checkpoint CPU comparison; requires a qualified, caller-owned catalog/runtime snapshot.
const fixtureAuth=require('./auth_helpers.cjs').authenticatedFixture(),fetch=fixtureAuth.fetch;
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn,execFileSync}=require('node:child_process');
const {pageLoadTracker}=require('./browser_page_load.cjs');
const {waitForDebugger}=require('./browser_startup.cjs');
const {qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const root=path.resolve(__dirname,'..'),report=qaDirectory(root,'workspace-cpu-comparison');
function option(name,environment){const index=process.argv.indexOf(name);return index<0?process.env[environment]:process.argv[index+1];}
const catalog=option('--catalog','TULDOK_CPU_CATALOG'),projectRoot=option('--project','TULDOK_CPU_PROJECT'),snapshot=option('--snapshot','TULDOK_CPU_SNAPSHOT');
assert.ok(catalog&&projectRoot&&/^[a-f0-9]{64}$/.test(snapshot||''),'Explicit precreated --catalog, --project and --snapshot required');
assert.ok(process.argv.includes('--runtime-qualified'),'Pass --runtime-qualified only after the captured runtime qualification passes');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-cpu-browser-'));
const project=JSON.parse(fs.readFileSync(path.join(projectRoot,'project.json')));
const sha=raw=>crypto.createHash('sha256').update(raw).digest('hex');
const originalFiles=Object.fromEntries(fs.readdirSync(projectRoot).filter(name=>fs.statSync(path.join(projectRoot,name)).isFile()).map(name=>[name,sha(fs.readFileSync(path.join(projectRoot,name)))]));
const inspections=[],captures=[],checks=[],requests=[],errors=[],children=[],tracker=pageLoadTracker();const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));let ws,send,evaluate,serverErrors='';
async function until(fn,message='Timed out',seconds=60){for(let i=0;i<seconds*10;i++){const value=await fn();if(value)return value;await pause(100);}throw Error(message);}
function launch(command,args,options){const child=spawn(command,args,options);children.push(child);return child;}
const serverArgs=port=>['-u','app.py','--port',String(port),'--data',catalog,'--project-root','sample='+projectRoot];
(async()=>{
  let server=launch('python3',serverArgs(0),{cwd:root,stdio:['ignore','pipe','pipe']});
  let output='';server.stdout.on('data',chunk=>output+=chunk);server.stderr.on('data',chunk=>serverErrors+=chunk);
  const port=await until(()=>{if(server.exitCode!==null)throw Error('Project server exited: '+serverErrors);return output.match(/127\.0\.0\.1:(\d+)/)?.[1];});
  const base='http://127.0.0.1:'+port;
  await fixtureAuth.register('http://127.0.0.1:'+port,catalog,root);
  const browser=launch(process.env.BROWSER||'/usr/bin/chromium',['--headless','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--window-size=1440,900','--user-data-dir='+path.join(temporary,'browser'),'about:blank'],{stdio:['ignore','ignore','ignore'],env:{...process.env,XDG_CONFIG_HOME:temporary,XDG_CACHE_HOME:temporary}});
  const debugPort=await waitForDebugger(browser,path.join(temporary,'browser','DevToolsActivePort'));
  const tabs=await(await fetch('http://127.0.0.1:'+debugPort+'/json')).json(),target=tabs.find(tab=>tab.type==='page'&&tab.url==='about:blank');assert.ok(target);
  ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  let next=0;const pending=new Map();
  send=(method,params={})=>new Promise((resolve,reject)=>{const id=++next,timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method));},20000);pending.set(id,{resolve:value=>{clearTimeout(timer);resolve(value);},reject:error=>{clearTimeout(timer);reject(error);}});ws.send(JSON.stringify({id,method,params}));});
  ws.onmessage=event=>{const message=JSON.parse(event.data);tracker.observe(message);if(message.id){const task=pending.get(message.id);pending.delete(message.id);if(task)message.error?task.reject(message.error):task.resolve(message.result);}if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails);if(message.method==='Network.requestWillBeSent')requests.push({url:message.params.request.url,method:message.params.request.method});};
  evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  const doc=frame=>frame?'document.getElementById("catalog-frame").contentDocument':'document';
  const element=(selector,frame=false)=>`${doc(frame)}.querySelector(${JSON.stringify(selector)})`,text=(selector,frame=false)=>evaluate(`${element(selector,frame)}?.textContent`);
  async function click(selector,frame=false){
    const box=await until(()=>evaluate(`(async()=>{const e=${element(selector,frame)};if(!e||e.disabled||!e.getClientRects().length)return null;${frame?'document.getElementById("catalog-frame").scrollIntoView({block:"start"});':''}e.scrollIntoView({block:'center'});await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));const b=e.getBoundingClientRect(),x=b.x+b.width/2,y=b.y+b.height/2,hit=${doc(frame)}.elementFromPoint(x,y),f=${frame?'document.getElementById("catalog-frame").getBoundingClientRect()':'{x:0,y:0}'};return hit&&(hit===e||e.contains(hit))?{x:x+f.x,y:y+f.y}:null})()`),'Click target unavailable '+selector);
    for(const type of ['mousePressed','mouseReleased'])await send('Input.dispatchMouseEvent',{type,button:'left',clickCount:1,...box});
  }
  async function key(key,code=key,modifiers=0){for(const type of ['keyDown','keyUp'])await send('Input.dispatchKeyEvent',{type,key,code,modifiers,windowsVirtualKeyCode:{Enter:13,Escape:27,Tab:9,a:65}[key]||0,...(type==='keyDown'&&key==='Enter'?{text:'\r',unmodifiedText:'\r'}:{})});}
  async function fill(selector,value,frame=false){await click(selector,frame);await key('a','KeyA',2);await send('Input.insertText',{text:value});}
  const select=(selector,value,frame=false)=>evaluate(`(()=>{const e=${element(selector,frame)};e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  async function nav(view){await evaluate(`document.getElementById('nav-${view}').focus()`);await key('Enter');await until(()=>evaluate(`!document.getElementById('view-${view}').hidden && !document.getElementById('project-${view}-root').hidden`));await until(()=>text(`#project-${view}-root`).then(value=>value?.includes('PROJECT · INSPECTION ONLY')));}
  const check=value=>{checks.push(value);console.log('PASS',value);};
  async function reload(){const previous=(await send('Page.getFrameTree')).frameTree.frame;await send('Page.reload');await until(()=>tracker.reloaded(previous),'Main document reload not observed');}
  async function openProject(manifest,name,id){await until(()=>evaluate('typeof document.getElementById("open-project")?.onclick==="function"'));await click('#open-project');await until(()=>evaluate('document.getElementById("project-open-dialog").open && !document.getElementById("project-open-submit").disabled'));await select('#project-root','sample');await fill('#project-manifest',manifest);await evaluate('document.getElementById("project-open-submit").focus()');await key('Enter');await until(()=>evaluate('document.getElementById("dataset").value==='+JSON.stringify('project:'+id)));await nav('data');assert.match(await text('#project-data-root'),new RegExp(name.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')));}
  await send('Page.enable');await send('Page.setLifecycleEventsEnabled',{enabled:true});await send('Runtime.enable');await send('Network.enable');
  const offlineCanary=process.env.LD_PRELOAD?JSON.parse(execFileSync('python3',['-c',"import sys;sys.path.insert(0,'tests');from test_workspace_offline import CANARY;exec(CANARY)"],{cwd:root,encoding:'utf8'})):null;
  await fixtureAuth.browser(send,'http://127.0.0.1:'+port);
  await send('Page.navigate',{url:base+'/workspaces'});await until(()=>evaluate('!!document.getElementById("open-project")'));
  async function captureWorkspace(name,width,selector){await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});await evaluate(`${element(selector)}.scrollIntoView({block:'start'})`);await pause(100);assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'));const file=name+'.jpg';fs.writeFileSync(path.join(report,file),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));captures.push({file,width,height:900,qualification:'Actual frozen-checkpoint CPU comparison; exposed seeds, no retraining/GPU acceptance'});}
  async function api(route,body){const response=await fetch(base+route,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const value=await response.json();assert.ok(response.ok,JSON.stringify({route,status:response.status,value}));return value;}
  async function artifact(run,name){const item=run.artifacts.find(item=>item.name===name);assert.ok(item,name);const response=await fetch(base+item.url);assert.equal(response.status,200);const bytes=Buffer.from(await response.arrayBuffer());assert.equal(sha(bytes),item.sha256);return bytes;}
  async function completed(id){let logged=0;return until(async()=>{const run=await api('/api/workspace/runs/'+id);assert.ok(!['failed','unknown','cancelled','interrupted'].includes(run.state),JSON.stringify({state:run.state,error:run.error,events:run.events}));if(Date.now()-logged>30000){console.log('CPU run',run.id,run.state,run.custody_phase);logged=Date.now();}return run.state==='completed'?run:null;},'Actual CPU comparison did not complete',750);}
  await openProject('project.json',project.name,project.id);await nav('pipeline');
  await click('[data-project-recipe="compare"]');await until(()=>evaluate('!!document.querySelector("[data-external-input=checkpoint]")'));
  for(const input of ['checkpoint','freeze','build_receipt'])await select('[data-external-input="'+input+'"]',input);
  await fill('#external-create-name','CPU comparison · exposed seeds 900–903');
  await evaluate('document.getElementById("external-create-submit").focus()');await key('Enter');await until(()=>evaluate('!!document.getElementById("external-preflight")'));
  await fill('#external-param-threads','8');await fill('#external-param-repetitions','1');await click('#external-save');await until(()=>text('#external-dirty').then(value=>value?.startsWith('Saved')));
  await click('#external-preflight');await until(()=>evaluate('!document.getElementById("external-reviewed").disabled'), 'CPU preflight did not become approvable',120);
  assert.match(await text('#external-material'),/Material SHA256/);
  await captureWorkspace('cpu-pipeline-1440',1440,'#external-material');await captureWorkspace('cpu-pipeline-390',390,'#external-material');
  const previousRunIds=new Set((await api('/api/workspace/runs')).map(run=>run.id));
  await click('#external-reviewed');await evaluate('document.getElementById("external-submit").focus()');await key('Enter');
  const submitted=await until(async()=>{const runs=await api('/api/workspace/runs');return runs.find(run=>run.execution_kind==='external_recipe'&&!previousRunIds.has(run.id));},'CPU Run was not submitted');
  fs.writeFileSync(path.join(report,'submitted-run.json'),JSON.stringify(submitted,null,2));
  const run=await completed(submitted.id);
  fs.writeFileSync(path.join(report,'completed-run.json'),JSON.stringify(run,null,2));
  assert.equal(run.execution_kind,'external_recipe');assert.equal(run.material.parameters.threads,8);assert.equal(run.material.parameters.repetitions,1);
  assert.ok(JSON.stringify(run.material).includes(snapshot),'Run material does not bind caller-qualified snapshot');
  await until(()=>text('#real-run-state').then(value=>value==='completed'));
  await captureWorkspace('cpu-runs-390',390,'.external-run-custody');await captureWorkspace('cpu-runs-1440',1440,'.external-run-custody');
  check('Actual approved CPU graph completes all original methods, frames and exposed seeds');
  const artifactDirectory=path.join(report,'artifacts');fs.mkdirSync(artifactDirectory);
  const names=['comparison-freeze.json','timing.json','result.json','input-model.pt','input-freeze.json','comparison-receipt.json'];
  const downloaded={};for(const name of names){downloaded[name]=await artifact(run,name);fs.writeFileSync(path.join(artifactDirectory,name),downloaded[name]);}
  // Explicit owner-local QA observation, not an HTTP artifact or agent API acceptance claim.
  const localEvidence=path.join(report,'owner-local-custody');fs.mkdirSync(localEvidence);
  const published=path.join(catalog,'workspace-runs',run.id),custody=path.join(catalog,'workspace-runs','.external-'+run.id,'custody');
  const readLocal=(directory,name)=>{const raw=fs.readFileSync(path.join(directory,name));fs.writeFileSync(path.join(localEvidence,name),raw);return raw;};
  const manifest=JSON.parse(readLocal(published,'artifact-manifest.json'));
  assert.equal(manifest.run_id,run.id);assert.equal(manifest.material_sha256,run.material_sha256);
  assert.deepEqual(manifest.artifacts,run.artifacts.map(({url,locked,...item})=>item));
  const custodyRaw=readLocal(published,'custody-receipt.json'),custodyReceipt=JSON.parse(custodyRaw);
  assert.equal(sha(custodyRaw),manifest.custody_receipt_sha256);assert.equal(custodyReceipt.attempt_id,run.id);assert.equal(custodyReceipt.request_sha256,manifest.request_sha256);
  assert.equal(custodyReceipt.outcome,'completed');for(const flag of ['go_received','spawn_closed','drained','echild'])assert.equal(custodyReceipt[flag],true);
  const liveReceipt=fs.readFileSync(path.join(custody,'receipt.json'));assert.deepEqual(JSON.parse(liveReceipt),custodyReceipt);
  const streams={};for(const name of ['stdout','stderr']){streams[name]=readLocal(custody,name+'.log');assert.equal(streams[name].length,custodyReceipt.streams[name].bytes);assert.equal(sha(streams[name]),custodyReceipt.streams[name].sha256);}
  const runtimeLines=streams.stdout.toString('utf8').split('\n').filter(line=>line.startsWith('{')&&line.includes('"tuldok_cpu_runtime"')).map(line=>JSON.parse(line));
  assert.equal(runtimeLines.length,1);const runtimeProof=runtimeLines[0].tuldok_cpu_runtime;assert.equal(runtimeProof.snapshot_sha256,snapshot);assert.ok(runtimeProof.packages.numpy&&runtimeProof.packages.torch&&runtimeProof.mappings&&runtimeProof.module_paths);
  fs.writeFileSync(path.join(localEvidence,'runtime-proof.json'),JSON.stringify({source:'Explicit owner-local QA read of hash-bound custodian stdout; not HTTP download or agent API parity',...runtimeLines[0]},null,2));
  check('Owner-local QA custody logs retain exact hash-bound CPU bootstrap module and mapping evidence');
  const oracle=JSON.parse(execFileSync('python3',['tests/qualify_cpu_comparison.py','--artifacts',artifactDirectory,'--project',projectRoot,'--report',path.join(report,'cold-report.json')],{cwd:root,encoding:'utf8'}));
  assert.equal(oracle.timed_frames,1440);assert.equal(oracle.native_launches,24);
  check('Independent cold audit verifies original checkpoint/source bytes, complete reports, medians and strict accuracy thresholds');
  server.kill('SIGINT');await until(()=>server.exitCode!==null);server=launch('python3',serverArgs(port),{cwd:root,stdio:['ignore','pipe','pipe']});let reopened='';server.stdout.on('data',chunk=>reopened+=chunk);server.stderr.on('data',chunk=>serverErrors+=chunk);await until(()=>reopened.includes('Tuldok:'));await reload();
  const retained=await api('/api/workspace/runs/'+run.id);fs.writeFileSync(path.join(report,'reopened-run.json'),JSON.stringify(retained,null,2));assert.equal(retained.state,'completed');assert.equal(retained.material_sha256,run.material_sha256);
  for(const name of names)assert.deepEqual(await artifact(retained,name),downloaded[name]);
  for(const [name,hash] of Object.entries(originalFiles))assert.equal(sha(fs.readFileSync(path.join(projectRoot,name))),hash);
  assert.deepEqual(errors,[]);assert.ok(!serverErrors.includes('Traceback'),serverErrors);
  check('Server restart preserves exact completed comparison artifacts and caller-owned project inputs');
  fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify({source_commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),dirty:!!execFileSync('git',['status','--porcelain'],{cwd:root,encoding:'utf8'}).trim(),qualification:'Fresh frozen-checkpoint CPU correctness/backend comparison through actual approved Run',previously_exposed_seeds:[900,901,902,903],fresh_training_acceptance:false,gpu_acceptance:false,full_accuracy_fields_retained:false,checks,captures,run_id:run.id,material_sha256:run.material_sha256,runtime_snapshot_sha256:snapshot,local_qa_evidence:{directory:'owner-local-custody',custody_receipt_sha256:sha(custodyRaw),http_download_acceptance:false},cold:oracle,offline_canary:offlineCanary,browser:(await send('Browser.getVersion')).product},null,2));console.log('PASS CPU comparison browser:',report);
})().catch(async error=>{console.error(error);console.error('Application stderr:',serverErrors);if(evaluate)try{console.error(await evaluate('JSON.stringify({url:location.href,body:document.body.innerText.slice(-6000)})'));}catch{}process.exitCode=1;}).finally(()=>{ws?.close();for(const child of children.reverse())child.kill('SIGTERM');});
