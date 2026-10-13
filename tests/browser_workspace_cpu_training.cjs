'use strict';
// Actual frozen-input CPU fitting and QA-authored source preparation; explicit qualified catalog/runtime required.
const fixtureAuth=require('./auth_helpers.cjs').authenticatedFixture(),fetch=fixtureAuth.fetch;
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn,execFileSync}=require('node:child_process');
const {pageLoadTracker}=require('./browser_page_load.cjs');
const {waitForDebugger}=require('./browser_startup.cjs');
const {qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const root=path.resolve(__dirname,'..'),report=qaDirectory(root,'workspace-cpu-training');
function option(name,environment){const index=process.argv.indexOf(name);return index<0?process.env[environment]:process.argv[index+1];}
const catalog=option('--catalog','TULDOK_CPU_CATALOG'),projectRoot=option('--project','TULDOK_CPU_PROJECT'),snapshot=option('--snapshot','TULDOK_CPU_SNAPSHOT');
assert.ok(catalog&&projectRoot&&/^[a-f0-9]{64}$/.test(snapshot||''),'Explicit precreated --catalog, --project and --snapshot required');
assert.ok(process.argv.includes('--runtime-qualified'),'Pass --runtime-qualified only after the captured runtime qualification passes');
const generatorRoot=option('--generator-project','TULDOK_TRAINING_GENERATOR'),preparedInputs=option('--prepared-inputs','TULDOK_TRAINING_INPUTS');
const inspectRun=option('--inspect-run','TULDOK_INSPECT_TRAINING_RUN');
assert.ok(generatorRoot||preparedInputs||inspectRun,'Supply generator project or existing prepared-inputs receipt');
const numpy=process.env.TULDOK_TRAINING_PYTHON||'/workspace/Tuldok/.venv-training/bin/python';
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-cpu-training-browser-'));
const project=JSON.parse(fs.readFileSync(path.join(projectRoot,'project.json')));
const sha=raw=>crypto.createHash('sha256').update(raw).digest('hex');
const originalFiles=Object.fromEntries(fs.readdirSync(projectRoot).filter(name=>fs.statSync(path.join(projectRoot,name)).isFile()).map(name=>[name,sha(fs.readFileSync(path.join(projectRoot,name)))]));
const inspections=[],captures=[],checks=[],requests=[],errors=[],children=[],tracker=pageLoadTracker();const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));let ws,send,evaluate,serverErrors='';
async function until(fn,message='Timed out',seconds=60){for(let i=0;i<seconds*10;i++){const value=await fn();if(value)return value;await pause(100);}throw Error(message);}
function launch(command,args,options){const child=spawn(command,args,options);children.push(child);return child;}
const serverArgs=port=>['-u','app.py','--port',String(port),'--data',catalog,'--project-root','sample='+projectRoot,...(generatorRoot?['--project-root','generator='+generatorRoot]:[])];
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
  async function captureWorkspace(name,width,selector){await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});await evaluate(`${element(selector)}.scrollIntoView({block:'start'})`);await pause(100);assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'));const file=name+'.jpg';fs.writeFileSync(path.join(report,file),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));captures.push({file,width,height:900,qualification:'Actual frozen-input CPU fit; QA-authored review, no GPU or autonomous evaluation acceptance'});}
  async function api(route,body){const response=await fetch(base+route,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const value=await response.json();assert.ok(response.ok,JSON.stringify({route,status:response.status,value}));return value;}
  async function artifact(run,name){const item=run.artifacts.find(item=>item.name===name);assert.ok(item,name);const response=await fetch(base+item.url);assert.equal(response.status,200);const bytes=Buffer.from(await response.arrayBuffer());assert.equal(sha(bytes),item.sha256);return bytes;}
  async function completed(id){let logged=0;return until(async()=>{const run=await api('/api/workspace/runs/'+id);assert.ok(!['failed','unknown','cancelled','interrupted'].includes(run.state),JSON.stringify({state:run.state,error:run.error,events:run.events}));if(Date.now()-logged>30000){console.log('CPU run',run.id,run.state,run.custody_phase);logged=Date.now();}return run.state==='completed'?run:null;},'Actual approved execution did not complete',900);}
  if(inspectRun){
    assert.match(inspectRun,/^[a-f0-9]{32}$/);const before=(await api('/api/workspace/runs')).map(item=>item.id).sort(),run=await api('/api/workspace/runs/'+inspectRun);assert.equal(run.state,'completed');
    await until(()=>evaluate('typeof document.getElementById("dataset")?.onchange==="function"'));await select('#dataset','catalog');await evaluate('document.getElementById("nav-runs").focus()');await key('Enter');
    await click('#real-run-'+inspectRun);await until(()=>evaluate('!!document.getElementById("external-checkpoint-download")'));
    const progress=await api('/api/workspace/runs/'+inspectRun+'/progress');assert.equal(progress.result.status,'hash_verified');assert.equal(progress.evidence,'custody_verified');
    assert.ok(!(await text('#real-runs-root')).includes('Stage evidence'));assert.ok(!(await text('#real-runs-root')).includes('input\npending'));
    const downloadURL=await evaluate('document.getElementById("external-checkpoint-download").getAttribute("href")');const item=run.artifacts.find(item=>item.name==='model.pt');assert.equal(downloadURL,item.url);
    const checkpoint=await artifact(run,'model.pt');fs.writeFileSync(path.join(report,'inspected-model.pt'),checkpoint);
    await captureWorkspace('inspection-results-1440',1440,'#external-result-summary');await captureWorkspace('inspection-results-390',390,'#external-result-summary');
    for(const capture of captures)capture.qualification='Read-only inspection of a previously completed actual training Run; no new execution';
    assert.deepEqual((await api('/api/workspace/runs')).map(item=>item.id).sort(),before);assert.deepEqual(errors,[]);
    fs.writeFileSync(path.join(report,'inspection-receipt.json'),JSON.stringify({qualification:'Read-only final UI and verified checkpoint download; no retraining',source_commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),dirty:!!execFileSync('git',['status','--porcelain'],{cwd:root,encoding:'utf8'}).trim(),run_id:inspectRun,run_ids_unchanged:before,checkpoint_sha256:sha(checkpoint),checkpoint_bytes:checkpoint.length,progress,captures,offline_canary:offlineCanary,browser:(await send('Browser.getVersion')).product},null,2));console.log('PASS completed training inspection:',report);return;
  }
  let prepared;
  if(preparedInputs){
    prepared=JSON.parse(fs.readFileSync(preparedInputs));assert.equal(path.resolve(prepared.catalog),path.resolve(catalog));
    assert.equal(prepared.releases.length,6);assert.equal(prepared.records.length,12);
    for(const record of prepared.records){const current=await api('/api/workbench/records/'+record.id);assert.equal(current.content_hash,record.content_hash);assert.equal(current.review,'human_reviewed');}
    for(const release of prepared.releases){const response=await fetch(base+release.url);assert.equal(response.status,200);const raw=Buffer.from(await response.arrayBuffer());assert.equal(sha(raw),release.id);}
  }else{
    const generator=JSON.parse(fs.readFileSync(path.join(generatorRoot,'project.json')));
    await api('/api/workspace/projects',{root:'generator',manifest_path:'project.json'});
    let graph=await api('/api/workspace/graphs/external',{name:'QA native training trajectories',project_id:generator.id,recipe_id:'generate',expected_sha256:generator.recipes[0].sha256,inputs:{build_receipt:{reference_id:'build_receipt',expected_sha256:generator.data[0].sha256}},parameters:{grid:32,frames:8,seed:100}});
    prepared={qualification:'Actual native trajectories, QA-authored owner inspection/review and six immutable pair releases; no end-user review or fitting acceptance implied',catalog:path.resolve(catalog),records:[],releases:[],source_commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim()};
    const generations=path.join(report,'generation');fs.mkdirSync(generations);
    for(let seed=100;seed<=111;seed++){
      if(seed!==100){graph=await api('/api/workspace/graphs/'+graph.id+'/clone',{name:'QA native seed '+seed});graph.nodes.find(node=>node.type==='execute').parameters={grid:32,frames:8,seed};graph=await api('/api/workspace/graphs/'+graph.id,{revision:graph.revision,document:graph});}
      const preflight=await api('/api/workspace/graphs/'+graph.id+'/preflight-external',{revision:graph.revision});
      const submitted=await api('/api/workspace/runs/submit-external',{request_key:'training-source-'+crypto.randomUUID(),graph_id:graph.id,graph_revision:graph.revision,expected_digest:preflight.material_sha256});
      const generated=await completed(submitted.id),directory=path.join(generations,String(seed));fs.mkdirSync(directory);
      for(const name of ['fields.zip','wire.bin','producer-receipt.json','native-diagnostics.txt'])fs.writeFileSync(path.join(directory,name),await artifact(generated,name));
      const cold=JSON.parse(execFileSync(numpy,['tests/qualify_native_generation.py','--bundle',path.join(directory,'fields.zip'),'--wire',path.join(directory,'wire.bin'),'--seed',String(seed),'--frames','8','--report',path.join(directory,'cold.json')],{cwd:root,encoding:'utf8'}));assert.equal(cold.arrays.length,48);
      const fields=generated.artifacts.find(item=>item.name==='fields.zip');let record=await api('/api/workspace/runs/'+generated.id+'/import-data/fields.zip',{expected_sha256:fields.sha256,name:'QA training trajectory seed '+seed,rights:'Locally generated bounded native data; QA-authored evidence'});
      assert.equal(record.review,'draft');assert.equal(record.field_sequence.frame_count,8);
      // Deliberate owner review after all six arrays/wire and bounded diagnostics passed.
      record=await api('/api/workbench/records/'+record.id,{...record,review:'human_reviewed',annotation:{note:'QA owner inspected all 48 arrays against exact native wire, stages, geometry and bounded diagnostics. Whole seed '+seed+' trajectory for training; this is authored qualification evidence, not independent end-user scientific review.'}});
      prepared.records.push({seed,run_id:generated.id,id:record.id,revision:record.revision,source_revision:record.source_revision,content_hash:record.content_hash,groups:record.groups,cold_path:path.join(directory,'cold.json')});
      fs.writeFileSync(path.join(report,'prepared-inputs.partial.json'),JSON.stringify(prepared,null,2));console.log('PASS native eight-frame trajectory + QA review seed',seed);
    }
    for(let pair=0;pair<6;pair++){
      const rows=prepared.records.slice(pair*2,pair*2+2),request={items:rows.map(({id,revision,source_revision})=>({id,revision,source_revision})),ratios:{train:100,validation:0,test:0},seed:9};
      const preview=await api('/api/workbench/releases/preview',request);assert.equal(preview.eligible,true,JSON.stringify(preview.blockers));
      const release=await api('/api/workbench/releases',{...request,preview_token:preview.preview_token}),response=await fetch(base+release.url);assert.equal(response.status,200);const raw=Buffer.from(await response.arrayBuffer());assert.equal(sha(raw),release.id);assert.ok(raw.length<=40*1024*1024);
      const file=path.join(report,'training-pair-'+pair+'.zip');fs.writeFileSync(file,raw);prepared.releases.push({id:release.id,url:release.url,bytes:raw.length,path:file,seeds:rows.map(row=>row.seed)});
    }
    fs.writeFileSync(path.join(report,'prepared-inputs.json'),JSON.stringify(prepared,null,2));check('Twelve whole native trajectories reviewed by authenticated QA owner and frozen in six measured train-only releases');
  }
  assert.ok(prepared.releases.reduce((total,item)=>total+item.bytes,0)<=256*1024*1024);
  fs.writeFileSync(path.join(report,'prepared-inputs.json'),JSON.stringify(prepared,null,2));
  if(process.argv.includes('--prepare-only')){console.log('PASS training inputs prepared:',report);return;}
  await openProject('project.json',project.name,project.id);await nav('pipeline');
  await click('[data-project-recipe="train"]');await until(()=>evaluate('!!document.querySelector("[data-external-input=training_1]")'));
  for(let index=1;index<=6;index++){await select('[data-external-input-kind="training_'+index+'"]','frozen_release');await select('[data-external-input="training_'+index+'"]',prepared.releases[index-1].id);}
  await select('[data-external-input="build_receipt"]','build_receipt');await fill('#external-create-name','QA frozen-input CPU fit · 96 observations');
  await evaluate('document.getElementById("external-create-submit").focus()');await key('Enter');await until(()=>evaluate('!!document.getElementById("external-preflight")'));
  await fill('#external-param-threads','8');await click('#external-save');await until(()=>text('#external-dirty').then(value=>value?.startsWith('Saved')));
  await click('#external-preflight');await until(()=>evaluate('!document.getElementById("external-reviewed").disabled'),'Training preflight',120);
  await captureWorkspace('training-pipeline-1440',1440,'#external-material');await captureWorkspace('training-pipeline-390',390,'#external-material');
  const previousRunIds=new Set((await api('/api/workspace/runs')).map(run=>run.id));await click('#external-reviewed');await evaluate('document.getElementById("external-submit").focus()');await key('Enter');
  const submitted=await until(async()=>{const runs=await api('/api/workspace/runs');return runs.find(run=>run.execution_kind==='external_recipe'&&!previousRunIds.has(run.id));});
  fs.writeFileSync(path.join(report,'submitted-run.json'),JSON.stringify(submitted,null,2));
  const progressHistory=[];let lastProgress=0,liveCaptured=false;
  const run=await until(async()=>{const current=await api('/api/workspace/runs/'+submitted.id);if(['failed','unknown','cancelled','interrupted'].includes(current.state)){fs.writeFileSync(path.join(report,'failed-run.json'),JSON.stringify(current,null,2));throw Error(JSON.stringify({id:current.id,state:current.state,custody_phase:current.custody_phase,error:current.error,events:current.events}));}if(Date.now()-lastProgress>1800){lastProgress=Date.now();const progress=await api('/api/workspace/runs/'+current.id+'/progress');progressHistory.push(progress);fs.writeFileSync(path.join(report,'progress-observations.json'),JSON.stringify(progressHistory,null,2));if(progress.progress?.stage==='validation'&&!liveCaptured){await until(()=>text('#external-progress').then(value=>value?.includes('validation')));await captureWorkspace('training-live-1440',1440,'#external-progress');await captureWorkspace('training-live-390',390,'#external-progress');liveCaptured=true;}console.log('CPU training',current.state,current.custody_phase,progress.progress?.stage,progress.progress?.completed);}return current.state==='completed'?current:null;},'Actual frozen-input training did not complete',900);
  fs.writeFileSync(path.join(report,'completed-run.json'),JSON.stringify(run,null,2));assert.ok(JSON.stringify(run.material).includes(snapshot));
  const finalProgress=await api('/api/workspace/runs/'+run.id+'/progress');assert.equal(finalProgress.result.status,'hash_verified');assert.equal(finalProgress.evidence,'custody_verified');fs.writeFileSync(path.join(report,'completed-progress.json'),JSON.stringify(finalProgress,null,2));
  await until(()=>text('#real-run-state').then(value=>value==='completed'));await until(()=>evaluate('!!document.getElementById("external-checkpoint-download")'));
  await captureWorkspace('training-results-390',390,'#external-result-summary');await captureWorkspace('training-results-1440',1440,'#external-result-summary');
  check('Actual six-release approved CPU fit reports real closed-form/validation progress and hash-verified checkpoint metrics');
  const artifactDirectory=path.join(report,'artifacts');fs.mkdirSync(artifactDirectory);const downloaded={};
  for(const item of run.artifacts){downloaded[item.name]=await artifact(run,item.name);fs.writeFileSync(path.join(artifactDirectory,item.name),downloaded[item.name]);}
  const oracle=JSON.parse(execFileSync(numpy,['tests/qualify_cpu_training.py','--artifacts',artifactDirectory,'--prepared-inputs',path.join(report,'prepared-inputs.json'),'--report',path.join(report,'cold-report.json')],{cwd:root,encoding:'utf8',maxBuffer:8*1024*1024}));assert.equal(oracle.observations,96);
  check('Independent NumPy replay verifies exact frozen inputs, NPZ observations, full-spectrum fitted gains and checkpoint custody');
  server.kill('SIGINT');await until(()=>server.exitCode!==null);server=launch('python3',serverArgs(port),{cwd:root,stdio:['ignore','pipe','pipe']});let reopened='';server.stdout.on('data',chunk=>reopened+=chunk);server.stderr.on('data',chunk=>serverErrors+=chunk);await until(()=>reopened.includes('Tuldok:'));await reload();
  const retained=await api('/api/workspace/runs/'+run.id);assert.equal(retained.state,'completed');assert.equal(retained.material_sha256,run.material_sha256);
  for(const name of Object.keys(downloaded))assert.deepEqual(await artifact(retained,name),downloaded[name]);
  const retainedProgress=await api('/api/workspace/runs/'+run.id+'/progress');assert.deepEqual(retainedProgress.result,finalProgress.result);assert.equal(retainedProgress.evidence,'custody_verified');
  for(const [name,hash] of Object.entries(originalFiles))assert.equal(sha(fs.readFileSync(path.join(projectRoot,name))),hash);
  assert.deepEqual(errors,[]);assert.ok(!serverErrors.includes('Traceback'),serverErrors);check('Cold restart retains trained checkpoint, exact input identities, custody-verified diagnostics and result summary');
  fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify({source_commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),dirty:!!execFileSync('git',['status','--porcelain'],{cwd:root,encoding:'utf8'}).trim(),qualification:'Actual fresh CPU closed-form fit using96 observations from12 whole native trajectories and6 QA-reviewed frozen releases',autonomous_evaluation_acceptance:false,gpu_acceptance:false,independent_end_user_review:false,checks,captures,run_id:run.id,material_sha256:run.material_sha256,runtime_snapshot_sha256:snapshot,cold:oracle,offline_canary:offlineCanary,browser:(await send('Browser.getVersion')).product},null,2));console.log('PASS frozen-input CPU training browser:',report);
})().catch(async error=>{console.error(error);console.error('Application stderr:',serverErrors);if(evaluate)try{console.error(await evaluate('JSON.stringify({url:location.href,body:document.body.innerText.slice(-6000)})'));}catch{}process.exitCode=1;}).finally(()=>{ws?.close();for(const child of children.reverse())child.kill('SIGTERM');});
