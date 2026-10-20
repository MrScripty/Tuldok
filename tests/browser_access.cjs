// Actual CLI bootstrap, HttpOnly browser login, denied writes, and preserved drafts.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {spawn,execFileSync}=require('node:child_process');
const {authenticatedFixture}=require('./auth_helpers.cjs');
const {waitForDebugger}=require('./browser_startup.cjs');
const {accessSession}=require('./browser_access_session.cjs');
const {stopOwnedChildren}=require('./browser_owned_cleanup.cjs');
const {qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const root=path.resolve(__dirname,'..'),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-access-browser-')),data=path.join(temporary,'data');
const report=qaDirectory(root,'access'),children=[],errors=[],checks=[],fixture=authenticatedFixture();
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));let ws,session,send,evaluate,phase='startup';
function setPhase(value){phase=value;session?.setPhase(value);}
async function until(fn){for(let n=0;n<200;n++){const value=await fn();if(value)return value;await pause(100);}throw Error('Access browser wait timed out');}
function launch(command,args,options){const child=spawn(command,args,options);children.push(child);return child;}
function code(){const file=path.join(temporary,'login-'+Date.now());execFileSync('python3',['access.py','login','--data',data,'--out',file],{cwd:root});const value=fs.readFileSync(file,'utf8').trim();fs.unlinkSync(file);return value;}
(async()=>{
  await require('./test_browser_access_navigation.cjs').verifyAccessNavigation();
  setPhase('application-startup');
  const server=launch('python3',['-u','app.py','--port','0','--data',data],{cwd:root,stdio:['ignore','pipe','pipe']});let output='',serverErrors='';server.stdout.on('data',chunk=>output+=chunk);server.stderr.on('data',chunk=>serverErrors+=chunk);
  const port=await until(()=>output.match(/127\.0\.0\.1:(\d+)/)?.[1]),base='http://127.0.0.1:'+port;
  assert.equal((await fetch(base+'/api/workbench/records')).status,401);
  assert.equal((await fetch(base+'/api/samples',{method:'POST',headers:{'Content-Type':'application/json',Origin:base},body:'{}'})).status,401);
  await fixture.register(base,data,root);
  const response=await fixture.fetch(base+'/api/workbench/import',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({kind:'text',name:'Retained owner draft',text:'Original immutable source',groups:['auth-fixture'],rights:'Authored test fixture'})});assert.equal(response.status,201);const record=await response.json();
  const browser=launch(process.env.BROWSER||'/usr/bin/chromium',['--headless','--no-sandbox','--disable-gpu','--no-first-run','--remote-debugging-port=0','--window-size=1280,900','--user-data-dir='+path.join(temporary,'browser'),'about:blank'],{stdio:'ignore'});
  const debug=await waitForDebugger(browser,path.join(temporary,'browser','DevToolsActivePort')),tabs=await(await fetch('http://127.0.0.1:'+debug+'/json')).json();
  const target=tabs.find(tab=>tab.type==='page'&&tab.url==='about:blank');assert.ok(target,'Expected the explicitly launched blank page');
  ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error('Access CDP connection timed out')),10000);ws.onopen=()=>{clearTimeout(timer);resolve();};ws.onerror=()=>{clearTimeout(timer);reject(Error('Access CDP connection failed'));};});
  session=accessSession(ws,{onEvent:value=>{if(value.method==='Runtime.exceptionThrown')errors.push(value.params.exceptionDetails.text);}});session.setPhase(phase);send=session.send;
  evaluate=async expression=>{const value=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(value.exceptionDetails)throw Error(JSON.stringify(value.exceptionDetails));return value.result.value;};
  async function click(selector){const box=await evaluate(`(()=>{const el=document.querySelector(${JSON.stringify(selector)});el.scrollIntoView({block:'center'});const r=el.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}})()`);await send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...box});await send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...box});}
  async function fill(selector,value){await click(selector);await evaluate(`document.querySelector(${JSON.stringify(selector)}).select()`);await send('Input.insertText',{text:value});}
  async function login(){const token=code();await fill('#session-token',token);await click('#session-submit');await until(()=>evaluate('!document.getElementById("session-dialog").open'));assert.equal(await evaluate('document.getElementById("session-token").value'),'');assert.equal(await evaluate('document.cookie.includes("tuldok_session")'),false);return token;}
  await send('Page.enable');await send('Page.setLifecycleEventsEnabled',{enabled:true});await send('Runtime.enable');await send('Network.enable');
  // No fixture cookie is installed: this suite exercises actual interactive login.
  setPhase('initial-navigation');await session.navigate('Page.navigate',{url:base+'/workbench'});await until(()=>evaluate('document.getElementById("session-dialog")?.open'));
  setPhase('one-time-owner-login');
  const oneTime=await login();await until(()=>evaluate('document.getElementById("notice").textContent==="Collection ready."'));
  assert.equal((await fetch(base+'/api/access/session',{method:'POST',headers:{Origin:base,'Content-Type':'application/json'},body:JSON.stringify({token:oneTime})})).status,401);
  checks.push('Anonymous legacy/current APIs denied; real one-time login consumed; cookie is HttpOnly and code cleared');
  setPhase('draft-and-reauthentication');
  await click('#records .record button');await until(()=>evaluate('!document.getElementById("editor").hidden'));await fill('#label','retained-draft');
  const before=(await(await fixture.fetch(base+'/api/workbench/records/'+record.id)).json()).revision;
  await click('#session-logout');await until(()=>evaluate('document.getElementById("session-dialog").open'));await click('#session-close');
  await evaluate('window.deniedWrites=0;const original=window.fetch;window.fetch=async(...args)=>{if(args[0]==="/api/workbench/records/'+record.id+'"&&args[1]?.method==="POST")window.deniedWrites++;return original(...args)}');
  await click('#save');await until(()=>evaluate('document.getElementById("session-dialog").open'));
  assert.equal(await evaluate('document.getElementById("label").value'),'retained-draft');await login();await pause(150);
  assert.equal((await(await fixture.fetch(base+'/api/workbench/records/'+record.id)).json()).revision,before);
  assert.equal(await evaluate('document.getElementById("label").value'),'retained-draft');
  await click('#save');await until(async()=>((await(await fixture.fetch(base+'/api/workbench/records/'+record.id)).json()).revision)>before);
  checks.push('Sign out and rejected mutation preserve draft; reauthentication does not replay mutation; deliberate retry commits');
  setPhase('session-layout-captures');
  for(const [width,height] of [[1280,900],[390,844]]){await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});await click('#session-open');await pause(100);const shot=await send('Page.captureScreenshot',screenshotOptions);fs.writeFileSync(path.join(report,'session-'+width+'.jpg'),Buffer.from(shot.data,'base64'));await click('#session-close');}
  const issued=await fixture.fetch(base+'/api/access/credentials',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({label:'Scoped browser agent',scopes:['inspect','edit']})});assert.equal(issued.status,201);const agent=await issued.json();
  const cookies=await send('Network.getCookies',{urls:[base]});const sessionCookie=cookies.cookies.find(cookie=>cookie.httpOnly&&cookie.name==='tuldok_session');assert.ok(sessionCookie);
  await send('Network.setCookie',{name:sessionCookie.name,value:agent.token,url:base+'/',httpOnly:true,sameSite:'Strict',path:'/'});
  setPhase('scoped-agent-reload');await session.navigate('Page.reload');await until(()=>evaluate('document.getElementById("session-identity")?.textContent.includes("Scoped browser agent")'));await until(()=>evaluate('document.getElementById("notice").textContent==="Collection ready."'));await click('#records .record button');await until(()=>evaluate('!document.getElementById("editor").hidden'));
  assert.equal(await evaluate('document.getElementById("record-review").disabled'),true);
  checks.push('Real scoped agent identity cannot use owner human-review controls');
  assert.deepEqual(errors,[]);assert.equal(serverErrors,'');fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify({checks,anonymous_denied:true,real_cli_login:true,no_mutation_replay:true,source_commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),source_sha256:Object.fromEntries(['tests/browser_access.cjs','tests/browser_access_session.cjs','tests/test_browser_access_navigation.cjs'].map(file=>[file,require('node:crypto').createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex')])),navigation:session.snapshot()},null,2));console.log('PASS access browser '+report);
})().catch(error=>{
  console.error('Primary access failure:',error);process.exitCode=1;
  const failure={phase,protocol:session?.snapshot(),error:{name:error.name,message:error.message,code:error.code}};
  console.error('Access failure context:',JSON.stringify(failure));
  fs.writeFileSync(path.join(report,'failure.json'),JSON.stringify(failure,null,2)+'\n');
}).finally(async()=>{
  if(session)session.close();else ws?.close();
  await stopOwnedChildren(children);
  fs.rmSync(temporary,{recursive:true,force:true,maxRetries:10,retryDelay:100});
  fs.writeFileSync(path.join(report,'cleanup.json'),JSON.stringify({temporary,removed:!fs.existsSync(temporary),children:children.map(child=>({pid:child.pid,exit_code:child.exitCode,signal:child.signalCode})),scope:'Supplied test-owned main handles exited before bounded profile removal'},null,2)+'\n');
}).catch(error=>{console.error('Secondary access cleanup failure:',error);process.exitCode=1;});
