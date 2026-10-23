'use strict';
// Actual current native probe and zero-GO acknowledgement recovery; no model fit.
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn,execFileSync}=require('node:child_process'),{once}=require('node:events'),readline=require('node:readline');
const {authenticatedFixture}=require('./auth_helpers.cjs'),{waitForDebugger}=require('./browser_startup.cjs'),{cdpSession}=require('./browser_cdp_session.cjs'),{qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const root=path.resolve(__dirname,'..'),hash=raw=>crypto.createHash('sha256').update(raw).digest('hex');
assert.equal(process.env.TULDOK_NATIVE_PROJECT_GO,'1','Explicit native qualification GO required');
assert.ok(process.env.TULDOK_DATABASE_URL&&process.env.TULDOK_PROJECT_FILES_COLD_DATABASE_URL,'Disposable source and cold PostgreSQL configurations required');
assert.ok(process.env.TULDOK_NATIVE_PUBLIC_FREEZE_MANIFEST,'Lead must freeze and qualify isolated M3 before actual browser acceptance');
const freeze=JSON.parse(fs.readFileSync(process.env.TULDOK_NATIVE_PUBLIC_FREEZE_MANIFEST,'utf8'));
const material={manifest_sha256:hash(fs.readFileSync(process.env.TULDOK_NATIVE_PUBLIC_FREEZE_MANIFEST)),files:freeze.files};
function verifySource(){for(const [file,expected] of Object.entries(material.files))assert.equal(hash(fs.readFileSync(path.join(root,file))),expected,'Frozen source changed: '+file);}
verifySource();
const testSha=hash(fs.readFileSync(__filename)),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-native-browser-')),report=qaDirectory(root,'project-native');
const sourceDsn=process.env.TULDOK_DATABASE_URL,coldDsn=process.env.TULDOK_PROJECT_FILES_COLD_DATABASE_URL;
assert.notEqual(sourceDsn,coldDsn);
const children=[],catalogs=[],checks=[],errors=[],httpErrors=[],bounds=[],requests=[];
const gitEnv={...process.env,GIT_CONFIG_NOSYSTEM:'1',GIT_CONFIG_GLOBAL:'/dev/null',GIT_TERMINAL_PROMPT:'0'};
const routes=JSON.parse(execFileSync('python3',['-c',"import json,agent_api;names=agent_api.ProjectFilesOwnerClient.OPERATIONS;print(json.dumps({n.split('.')[1]:{**{k:agent_api.operation(n)[k] for k in ('path','method','query','side_effects')},'header':agent_api.selected_header(n)} for n in names}))"],{cwd:root,encoding:'utf8'}));
let server,origin,auth,socket,session,send,evaluate,serverErrors='',isolation,fixture,sourceFacts,coldFacts;const fixtures=[];
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn,label){for(let i=0;i<600;i++){const result=await fn();if(result)return result;await pause(100);}throw Error('Timed out: '+label);}
function launch(command,args,options={}){const child=spawn(command,args,options);children.push(child);return child;}
async function stop(child){if(!child||child.exitCode!==null||child.signalCode!==null)return;const exited=once(child,'exit');child.kill('SIGTERM');await exited;}
async function start(directory,dsn,cold=false){
  process.env.TULDOK_DATABASE_URL=dsn;serverErrors='';let ready;
  server=launch('python3',['-u','tests/test_project_native_clients_http.py','--serve','--root',directory,...(cold?['--cold']:[])],{cwd:root,env:{...process.env,TULDOK_DATABASE_URL:dsn},stdio:['pipe','pipe','pipe']});
  const pending=new Map(),lines=readline.createInterface({input:server.stdout});
  lines.on('line',line=>{let value;try{value=JSON.parse(line);}catch(_){serverErrors+='\nUnexpected stdout: '+line;return;}if(value.origin){ready=value;return;}const wait=pending.get(value.id);if(wait){pending.delete(value.id);value.error?wait.reject(Error(value.error)):wait.resolve(value.result);}});
  server.stderr.on('data',chunk=>serverErrors+=chunk);
  await until(()=>{if(server.exitCode!==null)throw Error('Fixture app exited: '+serverErrors);return ready;},'actual fixture app startup');
  const process_=server;
  const host={process:process_,ready,async command(action){const id=crypto.randomUUID();return new Promise((resolve,reject)=>{const timeout=setTimeout(()=>{pending.delete(id);reject(Error('Fixture command timed out: '+action));},30000);pending.set(id,{resolve:value=>{clearTimeout(timeout);resolve(value);},reject:error=>{clearTimeout(timeout);reject(error);}});process_.stdin.write(JSON.stringify({id,action})+'\n');});},async stop(){if(process_.exitCode!==null)return;const exited=once(process_,'exit');await host.command('stop');const [code]=await exited;assert.equal(code,0,'Fixture cleanup exit: '+serverErrors);}};
  fixtures.push(host);fixture=host;origin=ready.origin;auth=authenticatedFixture();await auth.register(origin,ready.control,root);return host;
}
async function state(){const response=await auth.fetch(origin+routes.status.path,{headers:{'Tuldok-Operation-Contract':routes.status.header}});const value=await response.json();assert.equal(response.status,200,JSON.stringify(value));return value;}
async function key(key,code=key,modifiers=0){for(const type of ['keyDown','keyUp'])await send('Input.dispatchKeyEvent',{type,key,code,modifiers,windowsVirtualKeyCode:{Enter:13,Tab:9,a:65,' ':32}[key]||0,...(type==='keyDown'&&key==='Enter'?{text:'\r',unmodifiedText:'\r'}:{})});}
async function focus(selector){await until(()=>evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});if(!e||e.disabled||!e.getClientRects().length)return false;e.scrollIntoView({block:'center'});e.focus();return document.activeElement===e;})()`),'focus '+selector);}
async function fill(selector,value){await focus(selector);await key('a','KeyA',2);await send('Input.insertText',{text:value});}
async function activate(selector){await focus(selector);await key('Enter');}
async function choose(selector,value){await focus(selector);await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});if(!Array.from(e.options).some(o=>o.value===${JSON.stringify(value)}))throw Error('Missing option');e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('change',{bubbles:true}));e.dispatchEvent(new Event('input',{bubbles:true}));})()`);}
async function settled(){await until(async()=>{const failure=await evaluate('document.getElementById("project-files-error").textContent');if(failure)throw Error('UI error: '+failure);return evaluate('!document.getElementById("project-files-save").disabled');},'acknowledged UI state');}
async function navigate(){await auth.browser(send,origin);await send('Page.navigate',{url:origin+'/project-files'});await until(()=>evaluate('!!document.querySelector("#project-files-root option")&&!document.getElementById("project-files-new").disabled'),'negotiated UI startup');}
async function capture(width,label){
  await send('Emulation.setDeviceMetricsOverride',{width,height:950,deviceScaleFactor:1,mobile:false});await evaluate('document.getElementById("project-native-title").scrollIntoView({block:"start"})');
  await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
  const value=await evaluate('({viewport:innerWidth,width:document.documentElement.scrollWidth,client:document.documentElement.clientWidth,offenders:Array.from(document.querySelectorAll("body *")).filter(e=>e.getClientRects().length&&e.getBoundingClientRect().right>innerWidth+1).map(e=>({tag:e.tagName,id:e.id,width:e.getBoundingClientRect().width,right:e.getBoundingClientRect().right,text:e.textContent.slice(0,100)})).slice(-20)})');
  bounds.push(value);fs.writeFileSync(path.join(report,label+'-bounds-'+width+'.json'),JSON.stringify(value,null,2)+'\n');fs.writeFileSync(path.join(report,label+'-'+width+'.jpg'),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));
  assert.ok(value.width<=value.viewport+1,'Responsive overflow: '+JSON.stringify(value));
}
function snapshot(directory){const files={};function walk(at){for(const item of fs.readdirSync(at,{withFileTypes:true})){if(['.git','.tuldok-local'].includes(item.name))continue;const next=path.join(at,item.name);if(item.isDirectory())walk(next);else if(item.isFile())files[path.relative(directory,next)]=hash(fs.readFileSync(next));else throw Error('Unexpected special fixture file');}}walk(directory);return files;}
function check(value){checks.push(value);console.log('PASS '+value);}
(async()=>{
  assert.ok(process.env.TULDOK_TRAINING_PYTHON,'Current explicitly qualified native interpreter required');
  isolation=JSON.parse(execFileSync('python3',['-c',"import json,os,psycopg;from psycopg.conninfo import conninfo_to_dict;s=conninfo_to_dict(os.environ['TULDOK_DATABASE_URL']);c=psycopg.connect(os.environ['TULDOK_PROJECT_FILES_COLD_DATABASE_URL']);row=c.execute('SELECT current_database(),current_user,has_database_privilege(current_user,%s,%s)',(s['dbname'],'CONNECT')).fetchone();assert row[0]!=s['dbname'] and not row[2];print(json.dumps(dict(database=row[0],role=row[1],source_connect=row[2])));c.close()"],{cwd:root,encoding:'utf8'}));
  const sourceHost=await start(path.join(temporary,'source-host'),sourceDsn);
  const browser=launch(process.env.BROWSER||'/usr/bin/chromium',['--headless','--no-sandbox','--disable-gpu','--no-first-run','--remote-debugging-port=0','--window-size=1440,950','--user-data-dir='+path.join(temporary,'browser'),'about:blank'],{stdio:'ignore',env:{...process.env,XDG_CONFIG_HOME:temporary,XDG_CACHE_HOME:temporary}});
  const port=await waitForDebugger(browser,path.join(temporary,'browser','DevToolsActivePort')),tabs=await(await fetch('http://127.0.0.1:'+port+'/json')).json(),target=tabs.find(tab=>tab.type==='page'&&tab.url==='about:blank');assert.ok(target);
  socket=new WebSocket(target.webSocketDebuggerUrl);await once(socket,'open');session=cdpSession(socket,{onEvent:event=>{if(event.method==='Runtime.exceptionThrown')errors.push(event.params.exceptionDetails);if(event.method==='Network.requestWillBeSent')requests.push({url:event.params.request.url,method:event.params.request.method,body:event.params.request.postData});if(event.method==='Network.responseReceived'&&event.params.response.status>=400)httpErrors.push({url:event.params.response.url,status:event.params.response.status});}});send=session.send;
  evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  await send('Page.enable');await send('Runtime.enable');await send('Network.enable');await navigate();
  await fill('#project-files-directory','alpha');await fill('#project-files-name','Native keyboard CPU fixture Ω');await activate('#project-files-new');await settled();
  const project=(await state()).project.project_id,graph=await fixture.command('seed');assert.equal(graph.records,6);await activate('#project-files-refresh');await settled();
  const nativeRequests=()=>requests.filter(value=>value.url.includes('/execution/native/'));
  assert.equal(nativeRequests().length,0);assert.equal((await fixture.command('facts')).go_events.length,0);
  await activate('#project-native-graphs');await settled();assert.equal(await evaluate('document.querySelectorAll("#project-native-graph option").length'),1);assert.equal(nativeRequests().length,0);
  await focus('#project-native-probe-confirm');await key(' ','Space');await activate('#project-native-preflight');
  await until(()=>evaluate('document.getElementById("project-files-status").textContent.includes("Native validation succeeded")'),'actual current CPU probe acknowledgement');await settled();
  let facts=await fixture.command('facts');assert.equal(facts.go_events.length,1);assert.equal(facts.workspace_runs,0);assert.ok(facts.go_events.every(event=>!event.in_transaction));
  assert.equal(await evaluate('document.getElementById("project-native-submit-fields").disabled'),false);
  const before=nativeRequests().length;await activate('#project-native-submit');await evaluate('new Promise(resolve=>requestAnimationFrame(resolve))');assert.equal(nativeRequests().length,before,'Unchecked separate Start consent prevents dispatch');
  await capture(390,'validated');await capture(1440,'validated');
  check('Actual keyboard native preflight runs one current CPU probe; saved metadata loading and unchecked separate Start never dispatch a training Run');
  await fill('#project-native-run-id','9'.repeat(32));await focus('#project-native-retry-confirm');await key(' ','Space');await activate('#project-native-retry');
  await until(()=>evaluate('document.getElementById("project-files-error").textContent'),'typed current-only retry refusal');assert.match(await evaluate('document.getElementById("project-files-error").textContent'),/current local Run|current native Run/i);
  facts=await fixture.command('facts');assert.equal(facts.go_events.length,1);assert.equal(facts.workspace_runs,0);
  await activate('#project-files-discard');await activate('#project-files-refresh');await settled();await activate('#project-native-graphs');await settled();
  await fixture.command('install_fault');await focus('#project-native-probe-confirm');await key(' ','Space');await activate('#project-native-preflight');
  await until(()=>evaluate('document.getElementById("project-files-error").textContent'),'actual canonical/SQL acknowledgement fault');facts=await fixture.command('facts');assert.deepEqual(facts.fired,[true]);assert.equal(facts.go_events.length,1,'Failed GO intent SQL acknowledgement must send no second GO');
  await fixture.command('clear_fault');await activate('#project-files-refresh');await until(()=>evaluate('!document.getElementById("project-execution-health").disabled'),'recovery health current phase control');await activate('#project-execution-health');
  await until(()=>evaluate('document.querySelectorAll("#project-native-phases button").length===1'),'one original unresolved current phase ID');
  await evaluate(`(()=>{const button=Array.from(document.querySelectorAll('#project-native-phases button')).find(value=>/ · (ready|go_intent|unknown)$/.test(value.textContent));if(!button)throw Error('Missing original unresolved phase');button.dataset.qaSelected='yes';})()`);
  await activate('#project-native-phases button[data-qa-selected="yes"]');const selectedPhase=await evaluate('document.getElementById("project-native-phase-id").value');assert.match(selectedPhase,/^[a-f0-9]{32}$/);
  await activate('#project-native-reconcile');await until(()=>evaluate('document.getElementById("project-files-status").textContent.includes("does not start or resume")'),'original current phase receipt reconciliation');
  facts=await fixture.command('facts');assert.equal(facts.go_events.length,1);assert.equal(facts.pending,false);assert.equal(facts.available,true);assert.equal(facts.workspace_runs,0);
  await activate('#project-files-discard');await activate('#project-files-refresh');await settled();sourceFacts=await fixture.command('facts');
  check('Named retry refuses absent current Run; real deferrable SQL fault after canonical GO intent sends zero GO, then keyboard health phase selection and explicit reconciliation restore availability without execution');
  const source=path.join(sourceHost.ready.external,'alpha'),canonical=snapshot(source),saved=(await state()).project;
  await activate('#project-files-close');await until(async()=>(await state()).state==='no_project_open','close before cold clone');await sourceHost.stop();
  const coldHostRoot=path.join(temporary,'cold-host'),external=path.join(coldHostRoot,'external');fs.mkdirSync(external,{recursive:true});const clone=path.join(external,'clone');
  const git=(...args)=>execFileSync('git',args,{env:gitEnv,stdio:['ignore','pipe','pipe']});git('init','-q','--template=',source);git('-C',source,'add','.');git('-C',source,'-c','user.name=Disposable native QA','-c','user.email=qa@example.invalid','-c','commit.gpgsign=false','-c','core.hooksPath=/dev/null','commit','-qm','Inert native probe science and exact failed phase');git('-c','core.hooksPath=/dev/null','clone','-q','--no-hardlinks','--template=',source,clone);if(fs.existsSync(path.join(source,'artifacts')))fs.cpSync(path.join(source,'artifacts'),path.join(clone,'artifacts'),{recursive:true});assert.deepEqual(snapshot(clone),canonical);
  fs.rmSync(path.join(temporary,'source-host'),{recursive:true,force:true});
  const beforeCold=nativeRequests().length;await start(coldHostRoot,coldDsn,true);await navigate();await fill('#project-files-directory','clone');await activate('#project-files-open');await settled();assert.deepEqual((await state()).project,saved);assert.equal(nativeRequests().length,beforeCold);
  await activate('#project-execution-health');await until(()=>evaluate('document.getElementById("project-execution-summary").textContent.includes("0 original current native phases")'),'cold phases remain historical');assert.equal(await evaluate('document.querySelectorAll("#project-native-phases button").length'),0);
  await activate('#project-native-graphs');await settled();assert.equal(await evaluate('document.querySelectorAll("#project-native-graph option").length'),1);coldFacts=await fixture.command('facts');assert.equal(coldFacts.portable_phase_count,sourceFacts.portable_phase_count);assert.ok(coldFacts.portable_phase_count>=2);assert.deepEqual(coldFacts.go_events,[]);assert.deepEqual(coldFacts.forbidden,[]);assert.equal(coldFacts.workspace_runs,0);assert.deepEqual(snapshot(clone),canonical);
  await capture(390,'cold');await capture(1440,'cold');assert.deepEqual(errors,[]);assert.equal(httpErrors.length,2,JSON.stringify(httpErrors));assert.ok(httpErrors.some(value=>value.status===409&&value.url.endsWith('/retry')));assert.ok(httpErrors.some(value=>value.status===503&&value.url.endsWith('/preflight')));verifySource();assert.equal(hash(fs.readFileSync(__filename)),testSha);
  check('Cold keyboard Open on distinct role denied source CONNECT preserves canonical native facts but no local phases/Run owner; removed original host is not followed and 390/1440 layouts fit');
  fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify({status:'pass',source_stable:true,checks,material,test_sha256:testSha,isolation,bounds,project_id:project,source_facts:sourceFacts,cold_facts:coldFacts,browser_runtime_errors:errors,expected_http_errors:httpErrors,native_requests:nativeRequests(),fixture:'Actual app handler/PG/Chromium and explicit qualified CPU interpreter; real source/release, one native probe, real deferred SQL ACK fault and no second GO; no model fit or training Run. Test-only stdin fixture commands seed authored data and wrap the actual before_commit hook; native owners unmocked. Cold host forbids process preparation/Runs construction as assertions.'},null,2)+'\n');console.log('Report '+path.join(report,'receipt.json'));
})().catch(async error=>{
  fs.writeFileSync(path.join(report,'failure-receipt.json'),JSON.stringify({status:'failed',error:error.message,checks,material,test_sha256:testSha,isolation,bounds,source_facts:sourceFacts,cold_facts:coldFacts,browser_runtime_errors:errors,http_errors:httpErrors,native_requests:requests.filter(value=>value.url.includes('/execution/native/'))},null,2)+'\n');console.error(error);console.error('Server:',serverErrors);if(evaluate)try{console.error('UI:',await evaluate('document.body.innerText'));}catch(_){}process.exitCode=1;
}).finally(async()=>{
  session?.close();socket?.close();for(const host of fixtures.reverse())try{await host.stop();}catch(error){console.error('Fixture cleanup failed:',error.message);process.exitCode=1;}for(const child of children.reverse())await stop(child);process.env.TULDOK_DATABASE_URL=sourceDsn;fs.rmSync(temporary,{recursive:true,force:true});
});
