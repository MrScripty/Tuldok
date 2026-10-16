'use strict';
const fixtureAuth = require('./auth_helpers.cjs').authenticatedFixture();
const fetch = fixtureAuth.fetch;
// Real project import and scientific inspection/review/freeze, with independent NumPy cold custody.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn,execFileSync}=require('node:child_process');
const {pageLoadTracker}=require('./browser_page_load.cjs');
const {waitForDebugger}=require('./browser_startup.cjs');
const {qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const root=path.resolve(__dirname,'..'),captureIndex=process.argv.indexOf('--capture-root');
assert.ok(captureIndex<0||process.argv[captureIndex+1],'--capture-root needs a directory');
const captureRoot=captureIndex<0?null:path.resolve(process.argv[captureIndex+1]);
const report=qaDirectory(root,captureRoot?'scientific-fields-native':'scientific-fields-neutral');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-fields-browser-')),projectRoot=path.join(temporary,'projects');fs.mkdirSync(projectRoot);
const sha=raw=>crypto.createHash('sha256').update(raw).digest('hex');
const bundlePath=path.join(projectRoot,'fields.zip');
const fixtureArgs=['tests/qualify_scientific_fields.py','--output',bundlePath,'--build-only',...(captureRoot?['--capture-root',captureRoot]:[])];
execFileSync('python3',fixtureArgs,{cwd:root});const source=fs.readFileSync(bundlePath),sourceHash=sha(source);
const first={schema_version:1,id:'c'.repeat(32),name:captureRoot?'Native capture transport only':'Rotated noncubic authored fields',data:[{id:'fields',label:'Generic scientific bundle',path:'fields.zip'}],recipes:[],evidence:[],requirements:[]};
const manifestRaw=JSON.stringify(first);fs.writeFileSync(path.join(projectRoot,'tuldok.project.json'),manifestRaw);
const inspections=[],captures=[],checks=[],requests=[],errors=[],children=[],tracker=pageLoadTracker();const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));let ws,send,evaluate,serverErrors='';
async function until(fn,message='Timed out'){for(let i=0;i<600;i++){const value=await fn();if(value)return value;await pause(100);}throw Error(message);}
function launch(command,args,options){const child=spawn(command,args,options);children.push(child);return child;}
const serverArgs=port=>['-u','app.py','--port',String(port),'--data',path.join(temporary,'data'),'--project-root','sample='+projectRoot];
(async()=>{
  let server=launch('python3',serverArgs(0),{cwd:root,stdio:['ignore','pipe','pipe']});
  let output='';server.stdout.on('data',chunk=>output+=chunk);server.stderr.on('data',chunk=>serverErrors+=chunk);
  const port=await until(()=>{if(server.exitCode!==null)throw Error('Project server exited: '+serverErrors);return output.match(/127\.0\.0\.1:(\d+)/)?.[1];});
  const base='http://127.0.0.1:'+port;
  await fixtureAuth.register('http://127.0.0.1:'+port,path.join(temporary,'data'),root);
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
  async function nav(view){await evaluate(`document.getElementById('nav-${view}').focus()`);await key('Enter');await until(()=>evaluate(`!document.getElementById('view-${view}').hidden && !document.getElementById('project-${view}-root').hidden`));await until(()=>text(`#project-${view}-root`).then(value=>value?.includes('PROJECT · SAVED SNAPSHOT')));}
  async function capture(name,width){
    await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});
    await evaluate(`(async()=>{const iframe=document.getElementById('catalog-frame');iframe.scrollIntoView({block:'start'});iframe.contentDocument.getElementById('scientific-inspection').scrollIntoView({block:'start'});await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));window.scrollBy(0,iframe.getBoundingClientRect().top);})()`);
    await pause(100);assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'Outer overflow');
    assert.ok(await evaluate(`${doc(true)}.documentElement.scrollWidth<=${doc(true)}.defaultView.innerWidth+1`),'Inspector overflow');
    const file=name+'.jpg';fs.writeFileSync(path.join(report,file),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));captures.push({file,width,height:900,qualification:'Transport, inspection and custody only; no physics or model qualification'});
  }
  const check=value=>{checks.push(value);console.log('PASS',value);};
  async function reload(){const previous=(await send('Page.getFrameTree')).frameTree.frame;await send('Page.reload');await until(()=>tracker.reloaded(previous),'Main document reload not observed');}
  async function openProject(manifest,name,id){await click('#open-project');await until(()=>evaluate('document.getElementById("project-open-dialog").open && !document.getElementById("project-open-submit").disabled'));await select('#project-root','sample');await fill('#project-manifest',manifest);await evaluate('document.getElementById("project-open-submit").focus()');await key('Enter');await until(()=>evaluate('document.getElementById("dataset").value==='+JSON.stringify('project:'+id)));await nav('data');assert.match(await text('#project-data-root'),new RegExp(name.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')));}
  await send('Page.enable');await send('Page.setLifecycleEventsEnabled',{enabled:true});await send('Runtime.enable');await send('Network.enable');
  const offlineCanary=process.env.LD_PRELOAD?JSON.parse(execFileSync('python3',['-c',"import sys;sys.path.insert(0,'tests');from test_workspace_offline import CANARY;exec(CANARY)"],{cwd:root,encoding:'utf8'})):null;
  await fixtureAuth.browser(send,'http://127.0.0.1:'+port);
  await send('Page.navigate',{url:base+'/workspaces'});await until(()=>evaluate('!!document.getElementById("open-project")'));
  await openProject('tuldok.project.json',first.name,first.id);
  assert.equal((await(await fetch(base+'/api/workbench/records')).json()).items.length,0,'Opening does not import');
  await click('[data-project-import="fields"]');
  await until(()=>evaluate('document.getElementById("project-import-dialog").open'));
  assert.match(await text('#project-import-identity'),new RegExp(sourceHash));
  await fill('#project-import-name','Whole generic field sequence');
  await fill('#project-import-rights','Test qualification custody only; no science acceptance');
  // Alter only our disposable copy after UI observation; saved references omit a declared hash.
  fs.writeFileSync(bundlePath,Buffer.concat([source,Buffer.from('changed')]));
  await click('#project-import-submit');await until(()=>text('#project-import-status').then(value=>/changed|hash|stale/i.test(value)));
  assert.equal((await(await fetch(base+'/api/workbench/records')).json()).items.length,0,'Stale displayed observation creates no record');
  fs.writeFileSync(bundlePath,source);
  await click('#project-import-submit');
  await until(()=>evaluate(`${doc(true)}?.getElementById('scientific-inspection')?.hidden===false`));
  await until(()=>text('#scientific-status',true).then(value=>value?.includes('Producer-declared stage:')));
  const records=(await(await fetch(base+'/api/workbench/records')).json()).items;assert.equal(records.length,1);const row=records[0];
  assert.equal(row.kind,'field_sequence');assert.equal(row.content_hash,sourceHash);assert.equal(row.review,'draft');
  const original=Buffer.from(await(await fetch(base+'/api/workbench/asset/'+row.id)).arrayBuffer());assert.deepEqual(original,source);
  check('Opening remains read-only; explicit import refuses stale observed hash before catalog writes, then imports exact bytes');
  const manifest=row.field_sequence.manifest;
  for(const field of manifest.fields){
    await select('#scientific-field',field.id,true);await select('#scientific-frame','1',true);
    for(const axis of ['x','y','z']){
      await select('#scientific-axis',axis,true);
      await until(()=>text('#scientific-status',true).then(value=>value?.includes(field.stage)&&value.includes(manifest.frames[1].time)));
      await until(()=>text('#scientific-coordinates',true).then(value=>value?.startsWith(axis.toUpperCase()+' index')));
      const rawSlice=await(await fetch(base+'/api/workbench/records/'+row.id+'/scientific?'+new URLSearchParams({frame:1,field:field.id,axis,index:0}))).text(),actual=JSON.parse(rawSlice);
      inspections.push(rawSlice);assert.equal(actual.time,manifest.frames[1].time);assert.equal(actual.stage,field.stage);assert.equal(actual.dtype,field.dtype);
      assert.equal(actual.values.length,{x:manifest.grid.shape_xyz[2]+Number(field.centering==='face_z'),y:manifest.grid.shape_xyz[2]+Number(field.centering==='face_z'),z:manifest.grid.shape_xyz[1]+Number(field.centering==='face_y')}[axis]);
      assert.match(await text('#scientific-probe',true),new RegExp('physical'));
    }
  }
  await select('#scientific-field',manifest.fields[0].id,true);await select('#scientific-frame','0',true);await select('#scientific-axis','z',true);
  await until(()=>text('#scientific-status',true).then(value=>value?.includes(manifest.frames[0].time)&&value.includes(manifest.fields[0].stage)));
  if(!captureRoot){assert.match(await text('#scientific-probe',true),/-0 K/);assert.match(await text('#scientific-coordinates',true),/9, -3.75, 8.5/);}
  await capture('scientific-inspector-1440',1440);await capture('scientific-inspector-390',390);
  check(captureRoot?'All native fields and X/Y/Z planes retain time, stage, dtype and declared geometry':'All authored fields and X/Y/Z planes retain exact time/stage/dtype; rotated noncubic origin and signed zero inspected');
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:900,deviceScaleFactor:1,mobile:false});
  await fill('#scientific-note','Whole-asset transport inspection. No physical validity, model or training acceptance.',true);
  await select('#record-review','human_reviewed',true);
  await evaluate(`${element('#editor button:not([type="button"])',true)}.focus()`);await key('Enter');
  await until(async()=>{const value=await(await fetch(base+'/api/workbench/records/'+row.id)).json();return value.review==='human_reviewed';});
  await until(()=>evaluate(`${doc(true)}.defaultView.TuldokWorkspaceData?.snapshot().record?.revision===2`));
  await until(()=>text('#records',true).then(value=>value?.includes('revision 2')));
  await click('#select-page',true);await click('.embed-toolbar button',true);
  await evaluate(`${element('#release-form',true)}.closest('details').open=true`);
  await fill('#train','100',true);await fill('#validation','0',true);await fill('#test','0',true);
  await click('#preview-release',true);await until(()=>evaluate(`${element('#freeze-release',true)}?.disabled===false`));
  await click('#freeze-release',true);await until(()=>evaluate(`!!${doc(true)}.querySelector('#release-result a')`));
  const download=await evaluate(`${doc(true)}.querySelector('#release-result a').href`),releasePath=path.join(report,'scientific-release.zip');
  const response=await fetch(download);assert.equal(response.status,200);const frozen=Buffer.from(await response.arrayBuffer());fs.writeFileSync(releasePath,frozen);
  const recoveredPath=path.join(report,'recovered-source.zip');
  const frozenSummary=JSON.parse(execFileSync('python3',['-c',"import json,sys,zipfile;from pathlib import Path;from scientific_release import validate_release;p=Path(sys.argv[1]);r=validate_release(p);z=zipfile.ZipFile(p);m=json.loads(z.read('manifest.json'));assert len(m['records'])==1;row=m['records'][0];assert row['review']=='human_reviewed';Path(sys.argv[2]).write_bytes(z.read(row['asset']));print(json.dumps(r))",releasePath,recoveredPath],{cwd:root,encoding:'utf8'}));
  assert.deepEqual(fs.readFileSync(recoveredPath),source);
  const inspectionsPath=path.join(report,'inspection-slices.json');fs.writeFileSync(inspectionsPath,'['+inspections.join(',')+']');
  const cold=JSON.parse(execFileSync(process.env.TULDOK_TRAINING_PYTHON||process.env.NUMPY_PYTHON||'/workspace/Tuldok/.venv-training/bin/python',['tests/qualify_scientific_fields.py','--output',recoveredPath,'--read-existing','--inspections',inspectionsPath,...(captureRoot?['--capture-root',captureRoot]:[])],{cwd:root,encoding:'utf8'}));
  assert.equal(cold.model_or_training_acceptance,false);assert.equal(cold.physics_acceptance,false);
  check('Wholeasset human inspection freezes canonical release; separate NumPy reader verifies exact recovered original payload and opaque sources');
  server.kill('SIGINT');await until(()=>server.exitCode!==null);server=launch('python3',serverArgs(port),{cwd:root,stdio:['ignore','pipe','pipe']});let reopened='';server.stdout.on('data',chunk=>reopened+=chunk);server.stderr.on('data',chunk=>serverErrors+=chunk);await until(()=>reopened.includes('Tuldok:'));
  await reload();await until(()=>text('#scientific-status',true).then(value=>value?.includes('Producer-declared stage:')));
  assert.deepEqual(Buffer.from(await(await fetch(download)).arrayBuffer()),frozen);assert.deepEqual(fs.readFileSync(bundlePath),source);assert.equal(fs.readFileSync(path.join(projectRoot,'tuldok.project.json'),'utf8'),manifestRaw);
  // A second actual import holds its collection reply while the user explicitly
  // chooses an existing clean record. Imported-record navigation must lose intent.
  const secondPath=path.join(temporary,'second.zip');
  execFileSync('python3',['-c',"import io,json,sys,zipfile;from pathlib import Path;z=zipfile.ZipFile(sys.argv[1]);m=json.loads(z.read('manifest.json'));m['provenance']['source_id']+='-race-fixture';o=io.BytesIO();w=zipfile.ZipFile(o,'w',zipfile.ZIP_STORED);w.writestr('manifest.json',json.dumps(m));[w.writestr(n,z.read(n)) for n in z.namelist() if n!='manifest.json'];w.close();Path(sys.argv[2]).write_bytes(o.getvalue())",bundlePath,secondPath],{cwd:root});
  fs.copyFileSync(secondPath,bundlePath);
  await select('#dataset','project:'+first.id);await until(()=>text('#project-data-root').then(value=>value?.includes(first.name)));
  await click('#project-data-root .project-refresh');
  await until(()=>evaluate(`document.querySelector('#project-data-root [data-project-import="fields"]')&&!document.querySelector('#project-data-root [data-project-import="fields"]').disabled`));
  await evaluate(`(()=>{const w=${doc(true)}.defaultView,original=w.fetch.bind(w);w.scientificHeld=false;w.fetch=async(...args)=>{const response=await original(...args);if(new URL(String(args[0]),w.location.href).pathname==='/api/workbench/records'&&!w.scientificHeld){w.scientificHeld=true;await new Promise(resolve=>{w.releaseScientific=resolve});w.fetch=original;}return response;};})()`);
  await click('[data-project-import="fields"]');await until(()=>evaluate('document.getElementById("project-import-dialog").open'));
  await fill('#project-import-name','Second field sequence for selection race');await click('#project-import-submit');
  await until(()=>evaluate(`${doc(true)}.defaultView.scientificHeld===true`));
  await click('#records .record button',true);
  await until(()=>evaluate(`${doc(true)}.defaultView.TuldokWorkspaceData.snapshot().record?.id===${JSON.stringify(row.id)}`));
  await evaluate(`${doc(true)}.defaultView.releaseScientific()`);
  await until(()=>text('#catalog-status').then(value=>value?.includes('Data changed while the imported record loaded')));
  assert.equal(await evaluate(`${doc(true)}.defaultView.TuldokWorkspaceData.snapshot().record.id`),row.id);
  assert.equal((await(await fetch(base+'/api/workbench/records')).json()).items.length,2);
  fs.writeFileSync(bundlePath,source);assert.deepEqual(fs.readFileSync(bundlePath),source);
  check('Held import refresh preserves a newer explicit clean-record selection instead of opening the newly imported record');
  assert.deepEqual(await(await fetch(base+'/api/workspace/runs')).json(),[]);assert.deepEqual(errors,[]);assert.ok(!serverErrors.includes('Traceback'),serverErrors);
  check('Restart retains reviewed field record and exact release; original project bytes unchanged and no execution submitted');
  fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify({source_commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),dirty:!!execFileSync('git',['status','--porcelain'],{cwd:root,encoding:'utf8'}).trim(),command:'node tests/browser_scientific_fields.cjs'+(captureRoot?' --capture-root <saved-native-capture>':''),capture_receipt_sha256:captureRoot?sha(fs.readFileSync(path.join(captureRoot,'receipt.json'))):null,qualification:captureRoot?'Actual saved native capture converted without element conversion; transport/UI/custody only':'Producer-neutral authored rotated noncubic fields; transport/UI/custody only',physics_acceptance:false,model_or_training_acceptance:false,checks,captures,source_sha256:sourceHash,cold,frozenSummary,offline_canary:offlineCanary,browser:(await send('Browser.getVersion')).product},null,2));
  console.log('PASS scientific field browser:',report);
})().catch(async error=>{console.error(error);console.error('Application stderr:',serverErrors);if(evaluate)try{console.error(await evaluate('JSON.stringify({url:location.href,body:document.body.innerText.slice(-9000),frame:document.getElementById("catalog-frame")?.contentDocument?.body.innerText.slice(-5000)})'));}catch{}process.exitCode=1;}).finally(()=>{ws?.close();for(const child of children.reverse())child.kill('SIGTERM');});
