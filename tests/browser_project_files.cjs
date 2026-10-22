'use strict';
// Real browser authoring, keyboard actions and a cold process on another database.
// Inputs and runtime roots are disposable; project scripts are inert sentinels.
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn,execFileSync}=require('node:child_process');
const {once}=require('node:events');
const {authenticatedFixture}=require('./auth_helpers.cjs');
const {waitForDebugger}=require('./browser_startup.cjs');
const {cdpSession}=require('./browser_cdp_session.cjs');
const {qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const root=path.resolve(__dirname,'..');
assert.ok(process.env.TULDOK_DATABASE_URL,'Use a disposable PostgreSQL TULDOK_DATABASE_URL');
assert.ok(process.env.TULDOK_PROJECT_FILES_COLD_DATABASE_URL,'Cold proof requires a separate disposable database URL');
const sourceDsn=process.env.TULDOK_DATABASE_URL,coldDsn=process.env.TULDOK_PROJECT_FILES_COLD_DATABASE_URL;
const gitOptions={env:{...process.env,GIT_CONFIG_NOSYSTEM:'1',GIT_CONFIG_GLOBAL:'/dev/null',GIT_TERMINAL_PROMPT:'0'}};
assert.notEqual(sourceDsn,coldDsn,'Source and cold connection configuration must differ');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-project-files-browser-'));
const report=qaDirectory(root,'project-files');
const external=path.join(temporary,'external');fs.mkdirSync(external);
const sourceControl=path.join(temporary,'control'),coldControl=path.join(temporary,'cold-control');
const TEXT='Café 山 🧪 — browser-authored source\nThe scientist’s unique rationale stays exact.\n';
const name='Browser source 山',label='positive 山',corpusNote='Earlier corpus note café 山 — preserve this scientific rationale.';
const checks=[],errors=[],httpErrors=[],children=[],catalogs=[];
const observationHeaders=JSON.parse(execFileSync('python3',['-c',"import json,agent_api;print(json.dumps({name:agent_api.selected_header('project_files.'+name) for name in ('status','query','get')}))"],{cwd:root,encoding:'utf8'}));
const material={head:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8',...gitOptions}).trim(),files:Object.fromEntries(['app.py','metadata.py','access.py','workbench.py','agent_api.py','project_store.py','project_text.py','project_workspace.py','static/project-files.html','static/project-files.js','static/project-files.css','tests/browser_project_files.cjs'].map(file=>[file,fs.existsSync(path.join(root,file))?crypto.createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex'):null]))};
let socket,session,server,serverErrors='',origin,fixtureAuth,send,evaluate;
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn,message='Timed out'){
  for(let i=0;i<200;i++){const value=await fn();if(value)return value;await pause(100);}
  throw Error(message);
}
function launch(command,args,options={}){const child=spawn(command,args,options);children.push(child);return child;}
function snapshot(directory){
  const values={};
  function walk(current){for(const entry of fs.readdirSync(current,{withFileTypes:true})){
    if(['.git','.tuldok-local'].includes(entry.name))continue;
    const next=path.join(current,entry.name);
    if(entry.isDirectory())walk(next);
    else if(entry.isFile())values[path.relative(directory,next)]=crypto.createHash('sha256').update(fs.readFileSync(next)).digest('hex');
    else throw Error('Unexpected project special file '+entry.name);
  }}walk(directory);return values;
}
async function stop(child){
  if(!child||child.exitCode!==null||child.signalCode!==null)return;
  const exited=once(child,'exit');child.kill('SIGTERM');await exited;
}
async function start(control,configuredRoot,dsn){
  process.env.TULDOK_DATABASE_URL=dsn;
  serverErrors='';
  server=launch('python3',['-u','app.py','--port','0','--data',control,'--project-files-root','fixture='+configuredRoot],{cwd:root,stdio:['ignore','pipe','pipe'],env:{...process.env,TULDOK_DATABASE_URL:dsn}});
  let output='';server.stdout.on('data',chunk=>output+=chunk);server.stderr.on('data',chunk=>serverErrors+=chunk);
  const port=await until(()=>{if(server.exitCode!==null)throw Error('Server exited: '+serverErrors);return output.match(/127\.0\.0\.1:(\d+)/)?.[1];},'Project-files server readiness: '+serverErrors);
  origin='http://127.0.0.1:'+port;
  catalogs.push({control,dsn});
  fixtureAuth=authenticatedFixture();
  await fixtureAuth.register(origin,control,root);
  return origin;
}
async function jsonApi(relative){
  const route=relative.split('?')[0],operation=route.endsWith('/records')?'query':route.includes('/records/')?'get':'status';
  const response=await fixtureAuth.fetch(origin+relative,{headers:{'Tuldok-Operation-Contract':observationHeaders[operation]}});
  const value=await response.json();assert.equal(response.status,200,JSON.stringify(value));return value;
}
async function state(){return jsonApi('/api/workspace/project-files');}
async function detail(recordId){
  const current=await state();
  return jsonApi('/api/workspace/project-files/records/'+recordId+'?'+new URLSearchParams({binding:current.binding,checkpoint:current.project.checkpoint,history_limit:'4'}));
}
async function key(key,code=key,modifiers=0){
  for(const type of ['keyDown','keyUp'])await send('Input.dispatchKeyEvent',{type,key,code,modifiers,windowsVirtualKeyCode:{Enter:13,Tab:9,Escape:27,a:65}[key]||0,...(type==='keyDown'&&key==='Enter'?{text:'\r',unmodifiedText:'\r'}:{})});
}
async function focus(selector){
  await until(()=>evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});if(!e||e.disabled||!e.getClientRects().length)return false;e.scrollIntoView({block:'center'});e.focus();return document.activeElement===e;})()`),'Focusable control '+selector);
}
async function fill(selector,value){await focus(selector);await key('a','KeyA',2);await send('Input.insertText',{text:value});}
async function activate(selector){await focus(selector);await key('Enter');}
async function choose(selector,value){
  await focus(selector);
  await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});if(!Array.from(e.options).some(o=>o.value===${JSON.stringify(value)}))throw Error('Missing rendered option');e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('change',{bubbles:true}));})()`);
}
async function ready(){await until(()=>evaluate('!!document.querySelector("#project-files-root option")&&!document.getElementById("project-files-new").disabled'),'Project files UI ready');}
async function navigate(){await fixtureAuth.browser(send,origin);await send('Page.navigate',{url:origin+'/project-files'});await ready();}
async function capture(filename,width,selector='#record-heading'){
  await send('Emulation.setDeviceMetricsOverride',{width,height:950,deviceScaleFactor:1,mobile:false});
  await evaluate(`document.querySelector(${JSON.stringify(selector)}).scrollIntoView({block:'start'})`);
  await pause(80);
  assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'No horizontal overflow at '+width);
  fs.writeFileSync(path.join(report,filename),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));
}
function check(message){checks.push(message);console.log('PASS '+message);}
(async()=>{
  // Cold runtime role must genuinely lack CONNECT to the source database.
  const isolation=JSON.parse(execFileSync('python3',['-c',
    "import json,os,psycopg;from psycopg.conninfo import conninfo_to_dict;source=conninfo_to_dict(os.environ['TULDOK_DATABASE_URL']);cold=conninfo_to_dict(os.environ['TULDOK_PROJECT_FILES_COLD_DATABASE_URL']);assert source['dbname']!=cold['dbname'];c=psycopg.connect(os.environ['TULDOK_PROJECT_FILES_COLD_DATABASE_URL']);row=c.execute('SELECT current_database(), current_user, has_database_privilege(current_user,%s,%s)',(source['dbname'],'CONNECT')).fetchone();assert not row[2], 'Cold role must not connect to source database';print(json.dumps({'database':row[0],'role':row[1],'source_connect':row[2]}));c.close()"
  ],{cwd:root,encoding:'utf8'}));
  await start(sourceControl,external,sourceDsn);
  const browser=launch(process.env.BROWSER||'/usr/bin/chromium',['--headless','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--window-size=1440,950','--user-data-dir='+path.join(temporary,'browser'),'about:blank'],{stdio:'ignore',env:{...process.env,XDG_CONFIG_HOME:temporary,XDG_CACHE_HOME:temporary}});
  const port=await waitForDebugger(browser,path.join(temporary,'browser','DevToolsActivePort'));
  const tabs=await(await fetch('http://127.0.0.1:'+port+'/json')).json();
  const target=tabs.find(tab=>tab.type==='page'&&tab.url==='about:blank');assert.ok(target);
  socket=new WebSocket(target.webSocketDebuggerUrl);await once(socket,'open');
  session=cdpSession(socket,{onEvent:event=>{
    if(event.method==='Runtime.exceptionThrown')errors.push(event.params.exceptionDetails);
    if(event.method==='Network.responseReceived'&&event.params.response.status>=400)httpErrors.push({url:event.params.response.url,status:event.params.response.status});
  }});send=session.send;
  evaluate=async expression=>{const value=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(value.exceptionDetails)throw Error(JSON.stringify(value.exceptionDetails));return value.result.value;};
  await send('Page.enable');await send('Runtime.enable');await send('Network.enable');
  await navigate();
  const initial=await state();assert.equal(initial.state,'no_project_open');
  await choose('#project-files-root','fixture');await fill('#project-files-directory','alpha');await fill('#project-files-name','Browser café 🧪');
  await activate('#project-files-new');
  await until(async()=>((await state()).state==='open'),'New via keyboard opens project');
  await until(()=>evaluate('!document.getElementById("import-text").disabled'));
  await fill('#text-name',name);await fill('#text-content',TEXT);await fill('#text-groups','source-fixture');await fill('#text-rights','Owned synthetic browser input');
  await activate('#import-text');
  await until(()=>evaluate('document.querySelectorAll("#records-list [data-record-id]").length===1'),'Import appears in actual UI');
  const recordId=await evaluate('document.querySelector("#records-list [data-record-id]").dataset.recordId');
  await activate('#records-list [data-record-id]');
  await until(()=>evaluate('document.getElementById("record-text").value==='+JSON.stringify(TEXT)),'Imported source shown exact');
  await choose('#annotation-task','text_corpus');await fill('#annotation-value',corpusNote);await choose('#record-review','human_reviewed');
  await activate('#annotation-save');
  await until(()=>evaluate('document.getElementById("record-summary").textContent.includes("Revision 2")&&!document.getElementById("annotation-save").disabled'),'Corpus note acknowledged in actual editor');
  await choose('#annotation-task','text_classification');
  await fill('#annotation-value',label);await fill('#annotation-groups','source-fixture,review-fixture');await choose('#record-review','human_reviewed');
  await activate('#annotation-save');
  await until(()=>evaluate('document.getElementById("record-summary").textContent.includes("Revision 3")&&!document.getElementById("annotation-save").disabled'),'Annotation acknowledged in actual editor');
  const expected=await detail(recordId);
  assert.equal(expected.record.text,TEXT);assert.equal(expected.record.name,name);assert.equal(expected.record.review,'human_reviewed');assert.equal(expected.history.length,3);assert.ok(expected.history.some(item=>item.annotation?.note===corpusNote));
  await activate('#record-history-more');
  await until(()=>evaluate('document.getElementById("record-history").textContent.includes('+JSON.stringify(corpusNote)+')'),'Prior corpus note is inspectable through older-history UI');
  check('Keyboard New, Unicode import, historical corpus note and human-reviewed classification commit through real UI controls');
  await activate('#project-files-save');
  await until(()=>evaluate('!document.getElementById("project-files-save").disabled'));
  const beforeClose=await state();
  await capture('authored-1440.jpg',1440);await capture('authored-390.jpg',390);
  await activate('#project-files-close');await until(async()=>((await state()).state==='no_project_open'));
  await until(()=>evaluate('document.querySelectorAll("#records-list [data-record-id]").length===0'),'Close clears record panel');
  await stop(server);
  const source=path.join(external,'alpha');fs.mkdirSync(path.join(source,'scripts'),{recursive:true});
  fs.writeFileSync(path.join(source,'scripts','must-not-run.py'),"from pathlib import Path\nPath(__file__).with_name('EXECUTED').write_text('must never run')\n");
  const before=snapshot(source);
  const coldExternal=path.join(temporary,'cold-external');fs.mkdirSync(coldExternal);
  const clone=path.join(coldExternal,'clone');
  // Use an actual Git commit/clone; canonical source files are plain text.
  execFileSync('git',['init','-q','--template=',source],gitOptions);
  execFileSync('git',['-C',source,'add','.'],gitOptions);
  execFileSync('git',['-C',source,'-c','user.name=Disposable Project QA','-c','user.email=project-qa@example.invalid','-c','commit.gpgsign=false','-c','core.hooksPath=/dev/null','commit','-qm','Synthetic external project fixture'],gitOptions);
  execFileSync('git',['-c','core.hooksPath=/dev/null','clone','-q','--no-hardlinks','--template=',source,clone],gitOptions);
  assert.deepEqual(snapshot(clone),before,'Git clone retained exact canonical authored bytes');
  await start(coldControl,coldExternal,coldDsn);
  await navigate();
  assert.equal((await state()).state,'no_project_open');
  await choose('#project-files-root','fixture');await fill('#project-files-directory','clone');await activate('#project-files-open');
  await until(async()=>((await state()).state==='open'),'Cold process Open through keyboard');
  await until(()=>evaluate('document.querySelectorAll("#records-list [data-record-id]").length===1'));
  await activate('#records-list [data-record-id]');
  await until(()=>evaluate('document.getElementById("record-text").value==='+JSON.stringify(TEXT)));
  await until(()=>evaluate('document.getElementById("annotation-value").value==='+JSON.stringify(label)));
  const cold=await state(),actual=await detail(recordId);
  assert.deepEqual(cold.project,beforeClose.project);
  assert.deepEqual(actual.record,expected.record);assert.deepEqual(actual.history,expected.history);
  assert.equal(await evaluate('document.getElementById("record-review").value'),'human_reviewed');
  await activate('#project-files-save');await until(()=>evaluate('!document.getElementById("project-files-save").disabled'));
  assert.deepEqual(snapshot(clone),before,'Cold no-op Save has no semantic or byte changes');
  assert.ok(!fs.existsSync(path.join(clone,'scripts','EXECUTED')));
  check('Fresh application process and distinct PostgreSQL role/database reconstruct exact IDs, text, review and history from Git clone; source DB access denied');
  await activate('#record-history-more');
  await until(()=>evaluate('document.getElementById("record-history").textContent.includes('+JSON.stringify(corpusNote)+')'),'Cold Open retained corpus note is inspectable through older-history UI');
  await capture('cold-open-1440.jpg',1440);await capture('cold-open-390.jpg',390);await capture('cold-history-390.jpg',390,'#record-history');
  await activate('#project-files-close');await until(async()=>((await state()).state==='no_project_open'));
  assert.deepEqual(errors,[],'No browser runtime errors');assert.deepEqual(httpErrors,[],'No failed browser requests');
  for(const [file,digest] of Object.entries(material.files))assert.equal(crypto.createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex'),digest,'Material source changed during campaign: '+file);
  fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify({status:'pass',checks,isolation,material,project:beforeClose.project,record_id:recordId,history_count:expected.history.length,canonical_sha256:before,screenshots:['authored-1440.jpg','authored-390.jpg','cold-open-1440.jpg','cold-open-390.jpg','cold-history-390.jpg'],browser_runtime_errors:errors,http_errors:httpErrors,fixture:'Synthetic project only; no lab/scientific execution claim'},null,2)+'\n');
  console.log('Report '+path.join(report,'receipt.json'));
})().catch(async error=>{console.error(error);console.error('Server diagnostics:',serverErrors);console.error('Browser runtime errors:',JSON.stringify(errors));console.error('HTTP errors:',JSON.stringify(httpErrors));if(evaluate)try{console.error('UI diagnostics:',await evaluate('document.body.innerText'));}catch(diagnostic){console.error('UI diagnostics unavailable:',diagnostic.message);}process.exitCode=1;}).finally(async()=>{
  session?.close();socket?.close();
  for(const child of children.reverse())await stop(child);
  // Drop only UUID catalog schemas whose manifests live under this owned root.
  for(const {control,dsn} of catalogs){
    try{execFileSync('python3',['-c',
      "import json,pathlib,os,psycopg;from psycopg import sql;root=pathlib.Path(os.environ['QA_CONTROL']);c=psycopg.connect(os.environ['TULDOK_DATABASE_URL'],autocommit=True);[(c.execute(sql.SQL('DROP SCHEMA IF EXISTS {} CASCADE').format(sql.Identifier(('projection_'+v['projection_id']) if v['version']==2 else ('catalog_'+v['dataset_id']))))) for p in root.rglob('.tuldok.json') for v in [json.loads(p.read_text())]];c.close()"
    ],{cwd:root,env:{...process.env,TULDOK_DATABASE_URL:dsn,QA_CONTROL:control},stdio:['ignore','pipe','pipe']});}catch(error){console.error('Owned schema cleanup failed:',error.message);process.exitCode=1;}
  }
  process.env.TULDOK_DATABASE_URL=sourceDsn;
  fs.rmSync(temporary,{recursive:true,force:true});
});
