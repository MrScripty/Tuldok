'use strict';
// Read-only restored-catalog UI and authenticated artifact-byte qualification.
// Opens existing records/graphs/Runs; never imports, reviews, edits, or executes models.
// Run only after raw restore parity is recorded; owner login appends access audit rows.
const fixtureAuth=require('./auth_helpers.cjs').authenticatedFixture(),fetch=fixtureAuth.fetch;
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn,execFileSync}=require('node:child_process');
const {waitForDebugger}=require('./browser_startup.cjs');
const {qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const root=path.resolve(__dirname,'..');
function option(name){const index=process.argv.indexOf(name);return index<0?undefined:process.argv[index+1];}
const catalog=option('--catalog'),projectRoot=option('--project'),evidence=option('--evidence');
assert.ok(catalog&&projectRoot&&evidence,'Explicit --catalog restored path, --project root and --evidence prior qualification directory required');
assert.ok(process.argv.includes('--restore-qualified'),'Run only after root confirms completed raw restore verification and private restore DSN');
const prior=JSON.parse(fs.readFileSync(path.join(evidence,'receipt.json')));
const expectedInventory=JSON.parse(fs.readFileSync(path.join(evidence,'completed-http-inventory.json')));
assert.match(prior.run_id||'',/^[a-f0-9]{32}$/);assert.match(prior.record_id||'',/^[a-f0-9]{32}$/);
assert.equal(expectedInventory.length,89);
const explicitReport=option('--report');
if(explicitReport)fs.mkdirSync(explicitReport,{recursive:false});
const report=explicitReport||qaDirectory(root,'workspace-scientific-restore');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-restored-scientific-browser-'));
const captures=[],errors=[],children=[];const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));let ws,send,evaluate,base,authRegistered=false,serverErrors='';
async function until(fn,message='Timed out',seconds=60){for(let i=0;i<seconds*10;i++){const value=await fn();if(value)return value;await pause(100);}throw Error(message);}
function launch(command,args,options){const child=spawn(command,args,options);children.push(child);return child;}
const serverArgs=port=>['-u','app.py','--port',String(port),'--data',catalog,'--project-root','sample='+projectRoot];
(async()=>{
  const serverEnv={...process.env,PGAPPNAME:'tuldok-p7-restore-browser-'+process.pid};
  const server=launch('python3',serverArgs(0),{cwd:root,env:serverEnv,stdio:['ignore','pipe','pipe']});
  let output='';server.stdout.on('data',chunk=>output+=chunk);server.stderr.on('data',chunk=>serverErrors+=chunk);
  const port=await until(()=>{if(server.exitCode!==null)throw Error('Project server exited: '+serverErrors);return output.match(/127\.0\.0\.1:(\d+)/)?.[1];});
  base='http://127.0.0.1:'+port;
  const scopeCode=`import os,sys,json
from pathlib import Path
import psycopg
from metadata import Metadata
from backup_metadata import digest
def identity(connection):
    info=connection.info
    return digest({'host':info.host,'port':info.port,'dbname':info.dbname})
metadata=Metadata(sys.argv[1],dsn=os.environ['TULDOK_DATABASE_URL'],create=False,schema_version=None)
try:
    with psycopg.connect(os.environ['TULDOK_RESTORE_DATABASE_URL'],autocommit=True) as expected:
        assert identity(metadata.connection)==identity(expected), 'Effective browser DSN differs from admitted restore DSN'
        sessions=expected.execute('SELECT datname,count(*) FROM pg_stat_activity WHERE application_name=%s AND pid<>pg_backend_pid() AND pid<>%s GROUP BY datname',(os.environ['PGAPPNAME'],metadata.connection.info.backend_pid)).fetchall()
        assert sessions and all(row[0]==expected.info.dbname for row in sessions), 'Actual browser app sessions differ from admitted restore database'
        print(json.dumps({'catalog':str(Path(sys.argv[1]).resolve()),'dataset_id':metadata.dataset_id,'schema_version':metadata.schema_version,'database_identity_sha256':identity(expected),'actual_app_sessions':sum(row[1] for row in sessions),'actual_app_sessions_exclusively_restore_database':True,'verified_before_owner_login':True}))
finally:
    metadata.close()
`;
  const scope=JSON.parse(execFileSync('python3',['-c',scopeCode,catalog],{cwd:root,env:serverEnv,encoding:'utf8'}));
  assert.match(scope.dataset_id,/^[a-f0-9]{32}$/);assert.equal(scope.catalog,path.resolve(catalog));
  fs.writeFileSync(path.join(report,'server-database-scope.json'),JSON.stringify(scope,null,2));
  await fixtureAuth.register('http://127.0.0.1:'+port,catalog,root);
  authRegistered=true;
  const browser=launch(process.env.BROWSER||'/usr/bin/chromium',['--headless','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--window-size=1440,900','--user-data-dir='+path.join(temporary,'browser'),'about:blank'],{stdio:['ignore','ignore','ignore'],env:{...process.env,XDG_CONFIG_HOME:temporary,XDG_CACHE_HOME:temporary}});
  const debugPort=await waitForDebugger(browser,path.join(temporary,'browser','DevToolsActivePort'));
  const tabs=await(await fetch('http://127.0.0.1:'+debugPort+'/json')).json(),target=tabs.find(tab=>tab.type==='page'&&tab.url==='about:blank');assert.ok(target);
  ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  let next=0;const pending=new Map();
  send=(method,params={})=>new Promise((resolve,reject)=>{const id=++next,timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method));},20000);pending.set(id,{resolve:value=>{clearTimeout(timer);resolve(value);},reject:error=>{clearTimeout(timer);reject(error);}});ws.send(JSON.stringify({id,method,params}));});
  ws.onmessage=event=>{const message=JSON.parse(event.data);if(message.id){const task=pending.get(message.id);pending.delete(message.id);if(task)message.error?task.reject(message.error):task.resolve(message.result);}if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails);};
  evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  const doc=frame=>frame?'document.getElementById("catalog-frame").contentDocument':'document';
  const element=(selector,frame=false)=>`${doc(frame)}.querySelector(${JSON.stringify(selector)})`,text=(selector,frame=false)=>evaluate(`${element(selector,frame)}?.textContent`);
  async function click(selector,frame=false){
    const box=await until(()=>evaluate(`(async()=>{const e=${element(selector,frame)};if(!e||e.disabled||!e.getClientRects().length)return null;${frame?'document.getElementById("catalog-frame").scrollIntoView({block:"start"});':''}e.scrollIntoView({block:'center'});await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));const b=e.getBoundingClientRect(),x=b.x+b.width/2,y=b.y+b.height/2,hit=${doc(frame)}.elementFromPoint(x,y),f=${frame?'document.getElementById("catalog-frame").getBoundingClientRect()':'{x:0,y:0}'};return hit&&(hit===e||e.contains(hit))?{x:x+f.x,y:y+f.y}:null})()`),'Click target unavailable '+selector);
    for(const type of ['mousePressed','mouseReleased'])await send('Input.dispatchMouseEvent',{type,button:'left',clickCount:1,...box});
  }
  async function key(key,code=key,modifiers=0){for(const type of ['keyDown','keyUp'])await send('Input.dispatchKeyEvent',{type,key,code,modifiers,windowsVirtualKeyCode:{Enter:13,Escape:27,Tab:9,a:65}[key]||0,...(type==='keyDown'&&key==='Enter'?{text:'\r',unmodifiedText:'\r'}:{})});}
  const select=(selector,value,frame=false)=>evaluate(`(()=>{const e=${element(selector,frame)};e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  await send('Page.enable');await send('Page.setLifecycleEventsEnabled',{enabled:true});await send('Runtime.enable');await send('Network.enable');
  const offlineCanary=process.env.LD_PRELOAD?JSON.parse(execFileSync('python3',['-c',"import sys;sys.path.insert(0,'tests');from test_workspace_offline import CANARY;exec(CANARY)"],{cwd:root,encoding:'utf8'})):null;
  await fixtureAuth.browser(send,'http://127.0.0.1:'+port);
  await send('Page.navigate',{url:base+'/workspaces'});await until(()=>evaluate('!!document.getElementById("open-project")'));
  async function captureWorkspace(name,width,selector){await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});await evaluate(`${element(selector)}.scrollIntoView({block:'start'})`);await pause(100);assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'));const file=name+'.jpg';fs.writeFileSync(path.join(report,file),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));captures.push({file,width,height:900,qualification:'Read-only restored catalog; no new execution or scientific acceptance'});}
  async function api(route){const response=await fetch(base+route);const value=await response.json();assert.ok(response.ok,JSON.stringify({route,status:response.status,value}));return value;}

  const runId=prior.run_id,recordId=prior.record_id;
  const beforeRuns=(await api('/api/workspace/runs')).map(x=>x.id).sort(),beforeRecords=(await api('/api/workbench/records')).items.map(x=>x.id).sort();
  const beforeGraphs=await api('/api/workspace/graphs');
  const beforeRecord=await api('/api/workbench/records/'+recordId),run=await api('/api/workspace/runs/'+runId);assert.equal(run.state,'completed');assert.equal(beforeRecord.review,'human_reviewed');
  await until(()=>evaluate('typeof document.getElementById("dataset")?.onchange==="function"'));await select('#dataset','catalog');
  await evaluate('document.getElementById("nav-pipeline").focus()');await key('Enter');
  await until(()=>evaluate('!!document.getElementById("real-graph-select")'));
  await select('#real-graph-select',run.graph.id);
  await until(()=>evaluate('!!document.getElementById("external-preflight")'));
  await captureWorkspace('restored-pipeline-1440',1440,'#real-pipeline-root');await captureWorkspace('restored-pipeline-390',390,'#real-pipeline-root');
  await evaluate('document.getElementById("nav-runs").focus()');await key('Enter');
  await click('#real-run-'+runId);await until(()=>evaluate('!!document.getElementById("external-result-summary")'));
  await captureWorkspace('inspection-summary-1440',1440,'#external-result-summary');await captureWorkspace('inspection-summary-390',390,'#external-result-summary');
  await evaluate('document.getElementById("nav-data").focus()');await key('Enter');
  await until(()=>evaluate('!!document.getElementById("catalog-frame")?.contentWindow.TuldokWorkspaceData'));
  await until(async()=>{const value=await evaluate(`document.getElementById('catalog-frame').contentWindow.TuldokWorkspaceData.openCurrentRecord('${recordId}')`);if(value.kind!=='available')console.log('Read-only initial record navigation deferred:',value.message);return value.kind==='available';},'Existing reviewed record could not be opened');
  await select('#scientific-field','pressure',true);await select('#scientific-axis','z',true);
  const ready=()=>evaluate(`(()=>{const d=${doc(true)},c=d.getElementById('scientific-canvas');return c&&!c.hidden&&c.width===32&&c.height===32&&d.getElementById('scientific-status').textContent.includes('Producer-declared stage: solved pressure')&&d.getElementById('record-review').value==='human_reviewed'})()`);
  await until(ready,'Reviewed exact pressure slice never became ready');
  for(const width of [1440,390]){
    await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});await until(ready);
    await evaluate(`(async()=>{const f=document.getElementById('catalog-frame');f.scrollIntoView({block:'start'});f.contentDocument.getElementById('scientific-canvas').scrollIntoView({block:'center'});await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));window.scrollBy(0,f.getBoundingClientRect().top)})()`);
    assert.ok(await ready());assert.ok(!(await text('#scientific-status',true)).includes('Loading'));
    const file='inspection-loaded-data-'+width+'.jpg';fs.writeFileSync(path.join(report,file),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));captures.push({file,width,height:900,status:await text('#scientific-status',true),coordinates:await text('#scientific-coordinates',true),review:'human_reviewed'});
  }

  const inventory=[];assert.equal(run.artifacts.length,89);
  for(const item of run.artifacts){
    const response=await fetch(base+item.url);assert.equal(response.status,200);assert.equal(Number(response.headers.get('content-length')),item.bytes);
    let bytes=0;const hash=crypto.createHash('sha256');for await(const chunk of response.body){bytes+=chunk.length;hash.update(chunk);}
    const digest=hash.digest('hex');assert.equal(bytes,item.bytes);assert.equal(digest,item.sha256);inventory.push({name:item.name,bytes,sha256:digest});
    if(inventory.length%8===0)console.log('Restored verified HTTP artifacts',inventory.length,'/89');
  }
  const sorted=value=>[...value].sort((a,b)=>a.name.localeCompare(b.name));assert.deepEqual(sorted(inventory),sorted(expectedInventory));
  fs.writeFileSync(path.join(report,'restored-http-inventory.json'),JSON.stringify(inventory,null,2));
  assert.deepEqual(await api('/api/workspace/graphs'),beforeGraphs);
  assert.deepEqual((await api('/api/workspace/runs')).map(x=>x.id).sort(),beforeRuns);assert.deepEqual((await api('/api/workbench/records')).items.map(x=>x.id).sort(),beforeRecords);assert.deepEqual(await api('/api/workbench/records/'+recordId),beforeRecord);assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify({qualification:'Actual relocated restored catalog: read-only Data/Pipeline/Run UI and all89 authenticated HTTP artifact hashes; no model/import/review/graph mutation',source_commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),restored_catalog:path.resolve(catalog),prior_evidence:path.resolve(evidence),graphs_exactly_unchanged:true,http_artifacts:inventory.length,http_bytes:inventory.reduce((sum,item)=>sum+item.bytes,0),prior_http_inventory_exact_match:true,run_id:runId,record_id:recordId,run_ids_unchanged:beforeRuns,record_ids_unchanged:beforeRecords,record_exactly_unchanged:true,captures,offline_canary:offlineCanary},null,2));console.log('PASS restored scientific UI and HTTP qualification:',report);
})().catch(async error=>{console.error(error);console.error('Application stderr:',serverErrors);process.exitCode=1;}).finally(async()=>{
  const logout={attempted:authRegistered,verified:false};
  if(authRegistered){
    try{
      const response=await fetch(base+'/api/access/logout',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',signal:AbortSignal.timeout(10000)});
      logout.http_status=response.status;await response.arrayBuffer();assert.ok(response.ok,'Restored owner session logout refused');
      logout.verified=true;console.log('Restored owner session logout verified');
    }catch(error){logout.failure_type=error.name;console.error('Restored owner session logout failed:',error.name);process.exitCode=1;}
  }
  try{
    fs.writeFileSync(path.join(report,'logout.json'),JSON.stringify(logout,null,2));
    const receiptPath=path.join(report,'receipt.json');
    if(fs.existsSync(receiptPath)){const receipt=JSON.parse(fs.readFileSync(receiptPath));receipt.owner_session_logout_verified=logout.verified;fs.writeFileSync(receiptPath,JSON.stringify(receipt,null,2));}
  }finally{
    try{ws?.close();}finally{for(const child of children.reverse())child.kill('SIGTERM');}
  }
});
