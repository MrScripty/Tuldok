'use strict';
// Real named runtime controls; offline byte capture, explicit recovery, inert cold Open.
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn,execFileSync}=require('node:child_process'),{once}=require('node:events');
const {authenticatedFixture}=require('./auth_helpers.cjs'),{waitForDebugger}=require('./browser_startup.cjs'),{cdpSession}=require('./browser_cdp_session.cjs'),{qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const root=path.resolve(__dirname,'..'),hash=raw=>crypto.createHash('sha256').update(raw).digest('hex');
assert.ok(process.env.TULDOK_DATABASE_URL&&process.env.TULDOK_PROJECT_FILES_COLD_DATABASE_URL,'Disposable source and cold PostgreSQL configurations required');
assert.ok(process.env.TULDOK_M3_FREEZE_MANIFEST,'Lead must freeze and qualify isolated M3 before actual browser acceptance');
const freeze=JSON.parse(fs.readFileSync(process.env.TULDOK_M3_FREEZE_MANIFEST,'utf8'));
const material={manifest_sha256:hash(fs.readFileSync(process.env.TULDOK_M3_FREEZE_MANIFEST)),files:freeze.files};
function verifySource(){for(const [file,expected] of Object.entries(material.files))assert.equal(hash(fs.readFileSync(path.join(root,file))),expected,'Frozen source changed: '+file);}
verifySource();
const testSha=hash(fs.readFileSync(__filename)),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-m3-browser-')),report=qaDirectory(root,'project-files-m3');
const sourceDsn=process.env.TULDOK_DATABASE_URL,coldDsn=process.env.TULDOK_PROJECT_FILES_COLD_DATABASE_URL;
assert.notEqual(sourceDsn,coldDsn);
const external=path.join(temporary,'external');fs.mkdirSync(external);
const children=[],catalogs=[],checks=[],errors=[],httpErrors=[],bounds=[],requests=[];
const sentinel=path.join(temporary,'EXECUTED'),audit=path.join(temporary,'process-audit.jsonl'),auditDir=path.join(temporary,'audit');fs.mkdirSync(auditDir);
fs.writeFileSync(path.join(auditDir,'sitecustomize.py'),`import sys,os,json
with open(os.environ['QA_AUDIT_INSTALLED'],'w') as f:f.write('installed')
def guard(event,args):
 if event in ('subprocess.Popen','os.system','os.exec','os.posix_spawn'):
  with open(os.environ['QA_PROCESS_AUDIT'],'a') as f:f.write(json.dumps({'event':event})+'\\n')
  raise AssertionError('No process execution is allowed during this capture fixture')
sys.addaudithook(guard)
`);
const configFile=path.join(temporary,'runtime.json');
const gitEnv={...process.env,GIT_CONFIG_NOSYSTEM:'1',GIT_CONFIG_GLOBAL:'/dev/null',GIT_TERMINAL_PROMPT:'0'};
const routes=JSON.parse(execFileSync('python3',['-c',"import json,agent_api;names=agent_api.ProjectFilesOwnerClient.OPERATIONS;print(json.dumps({n.split('.')[1]:{**{k:agent_api.operation(n)[k] for k in ('path','method','query','side_effects')},'header':agent_api.selected_header(n)} for n in names}))"],{cwd:root,encoding:'utf8'}));
let server,origin,auth,socket,session,send,evaluate,serverErrors='',isolation;
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn,label){for(let i=0;i<200;i++){const result=await fn();if(result)return result;await pause(100);}throw Error('Timed out: '+label);}
function launch(command,args,options={}){const child=spawn(command,args,options);children.push(child);return child;}
async function stop(child){if(!child||child.exitCode!==null||child.signalCode!==null)return;const exited=once(child,'exit');child.kill('SIGTERM');await exited;}
async function start(control,directory,dsn,configured=false){
  process.env.TULDOK_DATABASE_URL=dsn;serverErrors='';let output='';
  server=launch('python3',['-u','app.py','--port','0','--data',control,'--project-files-root','fixture='+directory,...(configured?['--project-runtime-source','inert-fixture='+configFile]:[])],{cwd:root,env:{...process.env,TULDOK_DATABASE_URL:dsn,QA_PROCESS_AUDIT:audit,QA_AUDIT_INSTALLED:path.join(temporary,'audit-installed-'+catalogs.length),PYTHONPATH:auditDir+path.delimiter+(process.env.PYTHONPATH||'')},stdio:['ignore','pipe','pipe']});
  server.stdout.on('data',chunk=>output+=chunk);server.stderr.on('data',chunk=>serverErrors+=chunk);
  const port=await until(()=>{if(server.exitCode!==null)throw Error('Server exited: '+serverErrors);return output.match(/127\.0\.0\.1:(\d+)/)?.[1];},'actual server startup');
  assert.ok(fs.existsSync(path.join(temporary,'audit-installed-'+catalogs.length)),'App audit assertion installed');origin='http://127.0.0.1:'+port;catalogs.push({control,dsn});auth=authenticatedFixture();await auth.register(origin,control,root);
}
async function state(){const response=await auth.fetch(origin+routes.status.path,{headers:{'Tuldok-Operation-Contract':routes.status.header}});const value=await response.json();assert.equal(response.status,200,JSON.stringify(value));return value;}
async function key(key,code=key,modifiers=0){for(const type of ['keyDown','keyUp'])await send('Input.dispatchKeyEvent',{type,key,code,modifiers,windowsVirtualKeyCode:{Enter:13,Tab:9,a:65,' ':32}[key]||0,...(type==='keyDown'&&key==='Enter'?{text:'\r',unmodifiedText:'\r'}:{})});}
async function focus(selector){await until(()=>evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});if(!e||e.disabled||!e.getClientRects().length)return false;e.scrollIntoView({block:'center'});e.focus();return document.activeElement===e;})()`),'focus '+selector);}
async function fill(selector,value){await focus(selector);await key('a','KeyA',2);await send('Input.insertText',{text:value});}
async function activate(selector){await focus(selector);await key('Enter');}
async function choose(selector,value){await focus(selector);await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});if(!Array.from(e.options).some(o=>o.value===${JSON.stringify(value)}))throw Error('Missing option');e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('change',{bubbles:true}));e.dispatchEvent(new Event('input',{bubbles:true}));})()`);}
async function settled(){await until(async()=>{const failure=await evaluate('document.getElementById("project-files-error").textContent');if(failure)throw Error('UI error: '+failure);return evaluate('!document.getElementById("project-files-save").disabled');},'acknowledged UI state');}
async function navigate(){await auth.browser(send,origin);await send('Page.navigate',{url:origin+'/project-files'});await until(()=>evaluate('!!document.querySelector("#project-files-root option")&&!document.getElementById("project-files-new").disabled'),'negotiated UI startup');}
async function capture(width){
  await send('Emulation.setDeviceMetricsOverride',{width,height:950,deviceScaleFactor:1,mobile:false});await evaluate('document.getElementById("project-runtime-title").scrollIntoView({block:"start"})');
  await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
  const value=await evaluate('({viewport:innerWidth,width:document.documentElement.scrollWidth,client:document.documentElement.clientWidth,offenders:Array.from(document.querySelectorAll("body *")).filter(e=>e.getClientRects().length&&e.getBoundingClientRect().right>innerWidth+1).map(e=>({tag:e.tagName,id:e.id,width:e.getBoundingClientRect().width,right:e.getBoundingClientRect().right,text:e.textContent.slice(0,100)})).slice(-20)})');
  bounds.push(value);fs.writeFileSync(path.join(report,'bounds-'+width+'.json'),JSON.stringify(value,null,2)+'\n');fs.writeFileSync(path.join(report,'m3-runtime-'+width+'.jpg'),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));
  assert.ok(value.width<=value.viewport+1,'Responsive overflow: '+JSON.stringify(value));
}
function snapshot(directory){const files={};function walk(at){for(const item of fs.readdirSync(at,{withFileTypes:true})){if(['.git','.tuldok-local'].includes(item.name))continue;const next=path.join(at,item.name);if(item.isDirectory())walk(next);else if(item.isFile())files[path.relative(directory,next)]=hash(fs.readFileSync(next));else throw Error('Unexpected special fixture file');}}walk(directory);return files;}
function check(value){checks.push(value);console.log('PASS '+value);}
(async()=>{
  isolation=JSON.parse(execFileSync('python3',['-c',"import json,os,psycopg;from psycopg.conninfo import conninfo_to_dict;s=conninfo_to_dict(os.environ['TULDOK_DATABASE_URL']);c=psycopg.connect(os.environ['TULDOK_PROJECT_FILES_COLD_DATABASE_URL']);row=c.execute('SELECT current_database(),current_user,has_database_privilege(current_user,%s,%s)',(s['dbname'],'CONNECT')).fetchone();assert row[0]!=s['dbname'] and not row[2];print(json.dumps(dict(database=row[0],role=row[1],source_connect=row[2])));c.close()"],{cwd:root,encoding:'utf8'}));
  execFileSync('python3',['-c',`import json,pathlib,shutil,sys
p=pathlib.Path(sys.argv[1]);python=p/'explicit-python';site=p/'explicit-packages'
(python/'bin').mkdir(parents=True);(python/'lib/python3.12/lib-dynload').mkdir(parents=True)
shutil.copyfile('/usr/bin/true',python/'bin/python3.12')
for i in range(45):(python/'lib/python3.12/lib-dynload'/('fixture-%03d.txt'%i)).write_text('Owned inert runtime bytes Ω '+str(i))
packages=[]
for name in ('torch','numpy'):
 (site/name).mkdir(parents=True);(site/name/'__init__.py').write_text('from pathlib import Path'+chr(10)+'Path('+repr(sys.argv[2])+').write_text("executed")'+chr(10)+'raise AssertionError("Never import fixture")'+chr(10))
 info=site/(name+'-0.0.dist-info');info.mkdir();(info/'METADATA').write_text('Name: '+name+chr(10)+'Version: 0.0'+chr(10));(info/'LICENSE').write_text('Owned fixture');packages.extend([name,info.name])
(p/'runtime.json').write_text(json.dumps(dict(schema_version=1,python_root=str(python),python_version='3.12',site_packages=str(site),packages=packages)))`,temporary,sentinel],{cwd:root});
  await start(path.join(temporary,'control'),external,sourceDsn,true);
  const browser=launch(process.env.BROWSER||'/usr/bin/chromium',['--headless','--no-sandbox','--disable-gpu','--no-first-run','--remote-debugging-port=0','--window-size=1440,950','--user-data-dir='+path.join(temporary,'browser'),'about:blank'],{stdio:'ignore',env:{...process.env,XDG_CONFIG_HOME:temporary,XDG_CACHE_HOME:temporary}});
  const port=await waitForDebugger(browser,path.join(temporary,'browser','DevToolsActivePort')),tabs=await(await fetch('http://127.0.0.1:'+port+'/json')).json(),target=tabs.find(tab=>tab.type==='page'&&tab.url==='about:blank');assert.ok(target);
  socket=new WebSocket(target.webSocketDebuggerUrl);await once(socket,'open');session=cdpSession(socket,{onEvent:event=>{if(event.method==='Runtime.exceptionThrown')errors.push(event.params.exceptionDetails);if(event.method==='Network.requestWillBeSent')requests.push({url:event.params.request.url,method:event.params.request.method,body:event.params.request.postData});if(event.method==='Network.responseReceived'&&event.params.response.status>=400)httpErrors.push({url:event.params.response.url,status:event.params.response.status});}});send=session.send;
  evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  await send('Page.enable');await send('Runtime.enable');await send('Network.enable');await navigate();
  await fill('#project-files-directory','alpha');await fill('#project-files-name','M3 offline runtime browser Ω');await activate('#project-files-new');await settled();
  const initial=await state(),project=initial.project.project_id;
  const automatic=()=>requests.filter(r=>r.url.includes('/runtime/'));
  assert.equal(automatic().length,0,'New does not automatically inspect or capture runtime');
  await activate('#project-runtime-sources');await settled();assert.equal(await evaluate('document.querySelectorAll("#project-runtime-source option").length'),1);
  await activate('#project-runtime-inspect');await settled();assert.equal(await evaluate('document.querySelectorAll("#project-runtime-files li").length'),40);
  await activate('#project-runtime-files-more');await settled();assert.ok(await evaluate('document.querySelectorAll("#project-runtime-files li").length>40'));
  const summary=await evaluate('document.getElementById("project-runtime-summary").textContent'),inventory=summary.match(/[a-f0-9]{64}/)[0];
  assert.match(await evaluate('document.getElementById("project-runtime-layout").textContent'),/torch/);assert.equal(automatic().filter(r=>r.method==='POST').length,0);
  check('Keyboard loads configured alias and bounded paged inventory without capture or executing package imports');
  await fill('#project-runtime-reserve','9007199254740991');await focus('#project-runtime-confirm');await key(' ','Space');
  await activate('#project-runtime-capture');
  await until(()=>evaluate('document.getElementById("project-files-error").textContent'),'expected real insufficient-reserve error');
  const failedCapture=automatic().find(r=>r.method==='POST'&&r.url.endsWith('/runtime/capture'));assert.ok(failedCapture);const failedBody=JSON.parse(failedCapture.body);
  assert.match(await evaluate('document.getElementById("project-files-error").textContent'),/disk|reserve/i);
  await activate('#project-files-refresh');
  await until(()=>evaluate('!document.getElementById("project-runtime-abandon-fields").disabled'),'current original capture recovery control');
  const pending=await state();assert.ok(['open','recovery_required'].includes(pending.state));
  await fill('#project-runtime-abandon-key',failedBody.request_key);await fill('#project-runtime-abandon-reason','Explicitly abandon impossible reserve; preserve original inventory and intent Ω');await activate('#project-runtime-abandon');
  await until(()=>evaluate('document.getElementById("project-files-status").textContent.includes("partial bytes and scientific intent remain")'),'canonical abandonment ACK');
  await activate('#project-files-refresh');await settled();
  await fill('#project-runtime-status-key',failedBody.request_key);await activate('#project-runtime-status-form button');await settled();
  const abandoned=JSON.parse(await evaluate('document.getElementById("project-runtime-status").textContent'));assert.equal(abandoned.state,'abandoned');assert.equal(abandoned.intent.manifest_sha256,inventory);assert.equal(abandoned.abandonment.capture_key,failedBody.request_key);assert.equal(abandoned.result,null);
  check('Real reserve failure retains durable intent; named current-owner abandonment records exact key/reason and historical abandoned outcome');
  await activate('#project-runtime-sources');await settled();await activate('#project-runtime-inspect');await settled();await fill('#project-runtime-reserve','0');await focus('#project-runtime-confirm');await key(' ','Space');await activate('#project-runtime-capture');await settled();
  const captured=JSON.parse(await evaluate('document.getElementById("project-runtime-status").textContent'));assert.equal(captured.format,'project_runtime_capture_v1');assert.equal(captured.project_id,project);assert.equal(captured.manifest_sha256,inventory);assert.notEqual(captured.request_key,failedBody.request_key);
  await activate('#project-runtime-status-form button');await settled();const historical=JSON.parse(await evaluate('document.getElementById("project-runtime-status").textContent'));assert.equal(historical.state,'captured');assert.deepEqual(historical.result,captured);
  assert.ok(!fs.existsSync(sentinel));assert.ok(!fs.existsSync(audit),'Application never attempted subprocess/exec/install');
  check('Fresh explicit confirmed capture copies offline bytes and retains intent/result; no child process or package import executes');
  await activate('#project-files-close');await until(async()=>(await state()).state==='no_project_open','close captured project');await stop(server);
  const source=path.join(external,'alpha'),coldRoot=path.join(temporary,'cold-external');fs.mkdirSync(coldRoot);const clone=path.join(coldRoot,'clone'),canonical=snapshot(source);
  const git=(...args)=>execFileSync('git',args,{env:gitEnv,stdio:['ignore','pipe','pipe']});git('init','-q','--template=',source);git('-C',source,'add','.');git('-C',source,'-c','user.name=Disposable M3 QA','-c','user.email=qa@example.invalid','-c','commit.gpgsign=false','-c','core.hooksPath=/dev/null','commit','-qm','Inert canonical runtime facts');git('-c','core.hooksPath=/dev/null','clone','-q','--no-hardlinks','--template=',source,clone);if(fs.existsSync(path.join(source,'artifacts')))fs.cpSync(path.join(source,'artifacts'),path.join(clone,'artifacts'),{recursive:true});assert.deepEqual(snapshot(clone),canonical);
  // Remove the original configured source before cold Open. Canonical metadata cannot restore it.
  fs.rmSync(path.join(temporary,'explicit-python'),{recursive:true});fs.rmSync(path.join(temporary,'explicit-packages'),{recursive:true});fs.unlinkSync(configFile);
  const beforeCold=automatic().length;await start(path.join(temporary,'cold-control'),coldRoot,coldDsn);await navigate();await fill('#project-files-directory','clone');await activate('#project-files-open');await settled();assert.equal((await state()).project.project_id,project);assert.equal(automatic().length,beforeCold,'Cold Open does not auto inspect/capture/status');
  await activate('#project-runtime-sources');await settled();assert.equal(await evaluate('document.querySelectorAll("#project-runtime-source option").length'),0);
  await fill('#project-runtime-status-key',captured.request_key);await activate('#project-runtime-status-form button');await settled();assert.deepEqual(JSON.parse(await evaluate('document.getElementById("project-runtime-status").textContent')),historical);
  await fill('#project-runtime-status-key',failedBody.request_key);await activate('#project-runtime-status-form button');await settled();assert.deepEqual(JSON.parse(await evaluate('document.getElementById("project-runtime-status").textContent')),abandoned);
  const cached=execFileSync('python3',['-c',"from pathlib import Path;import sys;print(len(list(Path(sys.argv[1]).rglob('runtime-snapshots'))))",path.join(temporary,'cold-control')],{encoding:'utf8'}).trim();assert.equal(cached,'0');
  await capture(390);await capture(1440);assert.deepEqual(snapshot(clone),canonical);assert.ok(!fs.existsSync(sentinel));assert.ok(!fs.existsSync(audit));assert.deepEqual(errors,[]);
  assert.equal(httpErrors.length,1,JSON.stringify(httpErrors));assert.ok(httpErrors[0].url.endsWith('/runtime/capture'));verifySource();assert.equal(hash(fs.readFileSync(__filename)),testSha);
  check('Cold keyboard UI on distinct role denied source CONNECT reconstructs exact captured/abandoned facts with no source alias/cache or automatic regeneration; 390/1440 responsive');
  fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify({status:'pass',source_stable:true,checks,material,test_sha256:testSha,isolation,bounds,project_id:project,captured,abandoned,browser_runtime_errors:errors,expected_http_errors:httpErrors,runtime_requests:automatic(),fixture:'M3 enabled only in derived immutable source. Actual app CLI/PG/Chromium; offline true ELF plus inert never-import packages; app-only audit hook rejects child execution; real impossible-reserve failure and explicit current-marker abandonment; Git canonical clone with explicit artifact transfer; source removed before cold Open. No scientific execution or runtime preflight.'},null,2)+'\n');console.log('Report '+path.join(report,'receipt.json'));
})().catch(async error=>{
  fs.writeFileSync(path.join(report,'failure-receipt.json'),JSON.stringify({status:'failed',error:error.message,checks,material,test_sha256:testSha,isolation,bounds,browser_runtime_errors:errors,http_errors:httpErrors,runtime_requests:requests.filter(r=>r.url.includes("/runtime/"))},null,2)+'\n');console.error(error);console.error('Server:',serverErrors);if(evaluate)try{console.error('UI:',await evaluate('document.body.innerText'));}catch(_){}process.exitCode=1;
}).finally(async()=>{
  session?.close();socket?.close();for(const child of children.reverse())await stop(child);
  for(const {control,dsn} of catalogs)try{execFileSync('python3',['-c',"import json,pathlib,os,psycopg;from psycopg import sql;root=pathlib.Path(os.environ['QA_CONTROL']);c=psycopg.connect(os.environ['TULDOK_DATABASE_URL'],autocommit=True);[(c.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier('projection_'+v['projection_id'] if v['version']==2 else 'catalog_'+v['dataset_id'])))) for p in root.rglob('.tuldok.json') for v in [json.loads(p.read_text())]];c.close()"],{cwd:root,env:{...process.env,TULDOK_DATABASE_URL:dsn,QA_CONTROL:control},stdio:['ignore','pipe','pipe']});}catch(error){console.error('Owned cleanup failed:',error.message);process.exitCode=1;}
  process.env.TULDOK_DATABASE_URL=sourceDsn;fs.rmSync(temporary,{recursive:true,force:true});
});
