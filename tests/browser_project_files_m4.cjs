'use strict';
// Real keyboard-driven named M4 controls, followed by a cold metadata clone.
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn,execFileSync}=require('node:child_process'),{once}=require('node:events');
const {authenticatedFixture}=require('./auth_helpers.cjs'),{waitForDebugger}=require('./browser_startup.cjs'),{cdpSession}=require('./browser_cdp_session.cjs'),{qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const root=path.resolve(__dirname,'..'),hash=raw=>crypto.createHash('sha256').update(raw).digest('hex');
assert.ok(process.env.TULDOK_DATABASE_URL&&process.env.TULDOK_PROJECT_FILES_COLD_DATABASE_URL,'Disposable source and cold PostgreSQL configurations required');
assert.ok(process.env.TULDOK_M4_FREEZE_MANIFEST,'Lead must freeze and enable M4 before actual browser acceptance');
const freeze=JSON.parse(fs.readFileSync(process.env.TULDOK_M4_FREEZE_MANIFEST,'utf8'));
const material={manifest_sha256:hash(fs.readFileSync(process.env.TULDOK_M4_FREEZE_MANIFEST)),files:freeze.files};
function verifySource(){for(const [file,expected] of Object.entries(material.files))assert.equal(hash(fs.readFileSync(path.join(root,file))),expected,'Frozen source changed: '+file);}
verifySource();
const testSha=hash(fs.readFileSync(__filename)),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-m4-browser-')),report=qaDirectory(root,'project-files-m4');
const sourceDsn=process.env.TULDOK_DATABASE_URL,coldDsn=process.env.TULDOK_PROJECT_FILES_COLD_DATABASE_URL;
assert.notEqual(sourceDsn,coldDsn);
const external=path.join(temporary,'external');fs.mkdirSync(external);
const children=[],catalogs=[],checks=[],errors=[],httpErrors=[],bounds=[];
const gitEnv={...process.env,GIT_CONFIG_NOSYSTEM:'1',GIT_CONFIG_GLOBAL:'/dev/null',GIT_TERMINAL_PROMPT:'0'};
const routes=JSON.parse(execFileSync('python3',['-c',"import json,agent_api;names=agent_api.ProjectFilesOwnerClient.OPERATIONS;print(json.dumps({n.split('.')[1]:{**{k:agent_api.operation(n)[k] for k in ('path','method','query','side_effects')},'header':agent_api.selected_header(n)} for n in names}))"],{cwd:root,encoding:'utf8'}));
let server,origin,auth,socket,session,send,evaluate,serverErrors='',isolation;
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn,label){for(let i=0;i<200;i++){const result=await fn();if(result)return result;await pause(100);}throw Error('Timed out: '+label);}
function launch(command,args,options={}){const child=spawn(command,args,options);children.push(child);return child;}
async function stop(child){if(!child||child.exitCode!==null||child.signalCode!==null)return;const exited=once(child,'exit');child.kill('SIGTERM');await exited;}
async function start(control,directory,dsn){
  process.env.TULDOK_DATABASE_URL=dsn;serverErrors='';let output='';
  server=launch('python3',['-u','app.py','--port','0','--data',control,'--project-files-root','fixture='+directory],{cwd:root,env:{...process.env,TULDOK_DATABASE_URL:dsn},stdio:['ignore','pipe','pipe']});
  server.stdout.on('data',chunk=>output+=chunk);server.stderr.on('data',chunk=>serverErrors+=chunk);
  const port=await until(()=>{if(server.exitCode!==null)throw Error('Server exited: '+serverErrors);return output.match(/127\.0\.0\.1:(\d+)/)?.[1];},'actual server startup');
  origin='http://127.0.0.1:'+port;catalogs.push({control,dsn});auth=authenticatedFixture();await auth.register(origin,control,root);
}
async function state(){const response=await auth.fetch(origin+routes.status.path,{headers:{'Tuldok-Operation-Contract':routes.status.header}});const value=await response.json();assert.equal(response.status,200,JSON.stringify(value));return value;}
async function call(action,fields={}){
  const current=await state(),definition=routes[action],arguments_={binding:current.binding,[definition.side_effects?'expected_checkpoint':'checkpoint']:current.project.checkpoint,...(definition.side_effects?{request_key:crypto.randomUUID().replaceAll('-','')} :{}),...fields};
  let target=definition.path;for(const [key,value] of Object.entries(arguments_))target=target.replace('{'+key+'}',encodeURIComponent(value));
  const query=new URLSearchParams(Object.entries(arguments_).filter(([key])=>definition.query.includes(key)));if(query.size)target+='?'+query;
  const body=Object.fromEntries(Object.entries(arguments_).filter(([key])=>!definition.query.includes(key)&&!definition.path.includes('{'+key+'}')));
  const response=await auth.fetch(origin+target,{method:definition.method,headers:{'Content-Type':'application/json','Tuldok-Operation-Contract':definition.header},...(definition.method==='POST'?{body:JSON.stringify(body)}:{})});
  const value=await response.json();assert.equal(response.status,200,JSON.stringify(value));return value.value;
}
async function key(key,code=key,modifiers=0){for(const type of ['keyDown','keyUp'])await send('Input.dispatchKeyEvent',{type,key,code,modifiers,windowsVirtualKeyCode:{Enter:13,Tab:9,a:65}[key]||0,...(type==='keyDown'&&key==='Enter'?{text:'\r',unmodifiedText:'\r'}:{})});}
async function focus(selector){await until(()=>evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});if(!e||e.disabled||!e.getClientRects().length)return false;e.scrollIntoView({block:'center'});e.focus();return document.activeElement===e;})()`),'focus '+selector);}
async function fill(selector,value){await focus(selector);await key('a','KeyA',2);await send('Input.insertText',{text:value});}
async function activate(selector){await focus(selector);await key('Enter');}
async function choose(selector,value){await focus(selector);await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});if(!Array.from(e.options).some(o=>o.value===${JSON.stringify(value)}))throw Error('Missing option');e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('change',{bubbles:true}));e.dispatchEvent(new Event('input',{bubbles:true}));})()`);}
async function settled(){await until(async()=>{const failure=await evaluate('document.getElementById("project-files-error").textContent');if(failure)throw Error('UI error: '+failure);return evaluate('!document.getElementById("project-files-save").disabled');},'acknowledged UI state');}
async function navigate(){await auth.browser(send,origin);await send('Page.navigate',{url:origin+'/project-files'});await until(()=>evaluate('!!document.querySelector("#project-files-root option")&&!document.getElementById("project-files-new").disabled'),'negotiated UI startup');}
async function working(kind,file,raw,revision=0){
  await choose('#project-working-kind',kind);await fill('#project-working-path',file);await fill('#project-working-revision',String(revision));await fill('#project-working-sha',hash(raw));
  await activate('#project-working-adopt-form button[type="submit"]');await settled();
  assert.equal(await evaluate('document.getElementById("project-working-text").value'),raw.toString());
}
async function inspectFile(file){
  await activate('#project-working-load');await settled();
  await evaluate(`(()=>{const b=Array.from(document.querySelectorAll('#project-working-list button')).find(e=>e.textContent.startsWith(${JSON.stringify(file+' ·')}));if(!b)throw Error('Missing working file');b.dataset.qaSelected='yes';})()`);
  await activate('#project-working-list button[data-qa-selected="yes"]');await settled();
}
async function capture(width){
  await send('Emulation.setDeviceMetricsOverride',{width,height:950,deviceScaleFactor:1,mobile:false});await evaluate('document.getElementById("project-intent-title").scrollIntoView({block:"start"})');
  await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');
  const value=await evaluate('({viewport:innerWidth,width:document.documentElement.scrollWidth,client:document.documentElement.clientWidth,offenders:Array.from(document.querySelectorAll("body *")).filter(e=>e.getClientRects().length&&e.getBoundingClientRect().right>innerWidth+1).map(e=>({tag:e.tagName,id:e.id,width:e.getBoundingClientRect().width,right:e.getBoundingClientRect().right,text:e.textContent.slice(0,100)})).slice(-20)})');
  bounds.push(value);fs.writeFileSync(path.join(report,'bounds-'+width+'.json'),JSON.stringify(value,null,2)+'\n');fs.writeFileSync(path.join(report,'m4-cold-'+width+'.jpg'),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));
  assert.ok(value.width<=value.viewport+1,'Responsive overflow: '+JSON.stringify(value));
}
function snapshot(directory){const files={};function walk(at){for(const item of fs.readdirSync(at,{withFileTypes:true})){if(['.git','.tuldok-local'].includes(item.name))continue;const next=path.join(at,item.name);if(item.isDirectory())walk(next);else if(item.isFile())files[path.relative(directory,next)]=hash(fs.readFileSync(next));else throw Error('Unexpected special fixture file');}}walk(directory);return files;}
function check(value){checks.push(value);console.log('PASS '+value);}
async function inspectIntent(){
  await activate('#project-intents-load');await settled();await until(()=>evaluate('document.querySelectorAll("#project-intents-list button").length===1'),'one unresolved recipe');
  await activate('#project-intents-list button');await settled();
  return JSON.parse(await evaluate('document.getElementById("project-intent-detail").textContent'));
}
(async()=>{
  isolation=JSON.parse(execFileSync('python3',['-c',"import json,os,psycopg;from psycopg.conninfo import conninfo_to_dict;s=conninfo_to_dict(os.environ['TULDOK_DATABASE_URL']);c=psycopg.connect(os.environ['TULDOK_PROJECT_FILES_COLD_DATABASE_URL']);row=c.execute('SELECT current_database(),current_user,has_database_privilege(current_user,%s,%s)',(s['dbname'],'CONNECT')).fetchone();assert row[0]!=s['dbname'] and not row[2];print(json.dumps(dict(database=row[0],role=row[1],source_connect=row[2])));c.close()"],{cwd:root,encoding:'utf8'}));
  await start(path.join(temporary,'control'),external,sourceDsn);
  const browser=launch(process.env.BROWSER||'/usr/bin/chromium',['--headless','--no-sandbox','--disable-gpu','--no-first-run','--remote-debugging-port=0','--window-size=1440,950','--user-data-dir='+path.join(temporary,'browser'),'about:blank'],{stdio:'ignore',env:{...process.env,XDG_CONFIG_HOME:temporary,XDG_CACHE_HOME:temporary}});
  const port=await waitForDebugger(browser,path.join(temporary,'browser','DevToolsActivePort')),tabs=await(await fetch('http://127.0.0.1:'+port+'/json')).json(),target=tabs.find(tab=>tab.type==='page'&&tab.url==='about:blank');assert.ok(target);
  socket=new WebSocket(target.webSocketDebuggerUrl);await once(socket,'open');session=cdpSession(socket,{onEvent:event=>{if(event.method==='Runtime.exceptionThrown')errors.push(event.params.exceptionDetails);if(event.method==='Network.responseReceived'&&event.params.response.status>=400)httpErrors.push({url:event.params.response.url,status:event.params.response.status});}});send=session.send;
  evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  await send('Page.enable');await send('Runtime.enable');await send('Network.enable');await navigate();
  await fill('#project-files-directory','alpha');await fill('#project-files-name','M4 original browser Ω');await activate('#project-files-new');await settled();
  const originalState=await state(),originalProject=originalState.project.project_id,source=path.join(external,'alpha'),sentinel=path.join(temporary,'EXECUTED');
  fs.mkdirSync(path.join(source,'scripts'));fs.mkdirSync(path.join(source,'notes'));
  const first=Buffer.from('from pathlib import Path\nPath('+JSON.stringify(sentinel)+').write_text("executed")\n# authored Ω 山\n'),second=Buffer.concat([first,Buffer.from('# exact second decision 🌸\n')]);
  fs.writeFileSync(path.join(source,'scripts/inert.py'),first);fs.writeFileSync(path.join(source,'notes/empty.md'),'');
  await working('script','scripts/inert.py',first);await working('note','notes/empty.md',Buffer.alloc(0));
  fs.writeFileSync(path.join(source,'scripts/inert.py'),second);await inspectFile('scripts/inert.py');
  assert.equal(await evaluate('document.getElementById("project-working-text").value'),first.toString());assert.equal(await evaluate('document.getElementById("project-working-sha").value'),hash(second));
  await activate('#project-working-adopt-form button[type="submit"]');await settled();assert.equal(await evaluate('document.getElementById("project-working-text").value'),second.toString());
  await activate('#project-working-history');await settled();assert.equal(await evaluate('document.querySelectorAll("#project-working-history-list button").length'),2);
  await activate('#project-working-history-list button');await settled();assert.equal(await evaluate('document.getElementById("project-working-text").value'),first.toString());assert.ok(!fs.existsSync(sentinel));
  check('Actual keyboard controls adopt script and empty note, review current changed digest and select exact older captured revision without execution');
  const draft=JSON.parse(execFileSync('python3',['-c',"import json,sys;sys.path.insert(0,'tests');from test_project_material_fork import recipe;v=recipe(sys.argv[1]);print(json.dumps({k:x for k,x in v.items() if k not in ('format','id','revision')}))",originalProject],{cwd:root,encoding:'utf8'}));
  const retainedRecipe=await call('recipe_create',draft);await activate('#project-files-refresh');await settled();
  const sourceBefore=snapshot(source),sourceCheckpoint=(await state()).project.checkpoint;
  await fill('#project-save-as-directory','independent');await fill('#project-save-as-name','M4 independent browser Ω');await activate('#project-files-save-as');await settled();
  const forkState=await state();assert.notEqual(forkState.project.project_id,originalProject);assert.notEqual(forkState.binding,originalState.binding);assert.deepEqual(snapshot(source),sourceBefore);
  await activate('#project-fork-load');await settled();assert.match(await evaluate('document.getElementById("project-fork-summary").textContent'),new RegExp(sourceCheckpoint));
  const intent=await inspectIntent();assert.deepEqual(intent.current.definition,retainedRecipe);assert.equal(intent.fork_origin.project_id,originalProject);assert.equal(intent.current.definition.runtime.catalog_id,originalProject);assert.ok(intent.current.required_reselection.includes('runtime'));
  await activate('#project-intent-capabilities');await settled();assert.match(await evaluate('document.getElementById("project-intents-list").textContent'),/Reselect/);assert.ok(!fs.existsSync(sentinel));
  check('Actual named Save As selects new identity; fork mapping and selected readonly original binding intent retain source parameters and require reselection');
  const fork=path.join(external,'independent');await activate('#project-files-close');await until(async()=>(await state()).state==='no_project_open','close before cold copy');await stop(server);
  const coldRoot=path.join(temporary,'cold-external');fs.mkdirSync(coldRoot);const clone=path.join(coldRoot,'clone'),canonical=snapshot(fork);
  const git=(...args)=>execFileSync('git',args,{env:gitEnv,stdio:['ignore','pipe','pipe']});git('init','-q','--template=',fork);git('-C',fork,'add','.');git('-C',fork,'-c','user.name=Disposable M4 QA','-c','user.email=qa@example.invalid','-c','commit.gpgsign=false','-c','core.hooksPath=/dev/null','commit','-qm','Exact independent M4 project');git('-c','core.hooksPath=/dev/null','clone','-q','--no-hardlinks','--template=',fork,clone);if(fs.existsSync(path.join(fork,'artifacts')))fs.cpSync(path.join(fork,'artifacts'),path.join(clone,'artifacts'),{recursive:true});assert.deepEqual(snapshot(clone),canonical);
  await start(path.join(temporary,'cold-control'),coldRoot,coldDsn);await navigate();await fill('#project-files-directory','clone');await activate('#project-files-open');await settled();assert.deepEqual((await state()).project,forkState.project);
  await inspectFile('scripts/inert.py');assert.equal(await evaluate('document.getElementById("project-working-text").value'),second.toString());await activate('#project-working-history');await settled();await activate('#project-working-history-list button');await settled();assert.equal(await evaluate('document.getElementById("project-working-text").value'),first.toString());
  assert.deepEqual(await inspectIntent(),intent);await capture(390);await capture(1440);assert.deepEqual(snapshot(clone),canonical);assert.ok(!fs.existsSync(sentinel));assert.deepEqual(errors,[]);assert.deepEqual(httpErrors,[]);verifySource();assert.equal(hash(fs.readFileSync(__filename)),testSha);
  check('Cold UI on distinct role denied source CONNECT reconstructs exact fork, working-file history and unresolved intent; 390/1440 responsive and sentinel inert');
  fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify({status:'pass',checks,material,test_sha256:testSha,isolation,bounds,project:forkState.project,source_project:originalProject,browser_runtime_errors:errors,http_errors:httpErrors,canonical_sha256:canonical,fixture:'Real named keyboard UI; explicitly authored inert recipe references; local Git metadata clone plus explicit untracked payload transfer; no runtime/preflight'},null,2)+'\n');console.log('Report '+path.join(report,'receipt.json'));
})().catch(async error=>{
  fs.writeFileSync(path.join(report,'failure-receipt.json'),JSON.stringify({status:'failed',error:error.message,checks,material,test_sha256:testSha,isolation,bounds,browser_runtime_errors:errors,http_errors:httpErrors},null,2)+'\n');console.error(error);console.error('Server:',serverErrors);if(evaluate)try{console.error('UI:',await evaluate('document.body.innerText'));}catch(_){}process.exitCode=1;
}).finally(async()=>{
  session?.close();socket?.close();for(const child of children.reverse())await stop(child);
  for(const {control,dsn} of catalogs)try{execFileSync('python3',['-c',"import json,pathlib,os,psycopg;from psycopg import sql;root=pathlib.Path(os.environ['QA_CONTROL']);c=psycopg.connect(os.environ['TULDOK_DATABASE_URL'],autocommit=True);[(c.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier('projection_'+v['projection_id'] if v['version']==2 else 'catalog_'+v['dataset_id'])))) for p in root.rglob('.tuldok.json') for v in [json.loads(p.read_text())]];c.close()"],{cwd:root,env:{...process.env,TULDOK_DATABASE_URL:dsn,QA_CONTROL:control},stdio:['ignore','pipe','pipe']});}catch(error){console.error('Owned cleanup failed:',error.message);process.exitCode=1;}
  process.env.TULDOK_DATABASE_URL=sourceDsn;fs.rmSync(temporary,{recursive:true,force:true});
});
