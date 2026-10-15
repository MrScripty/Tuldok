'use strict';
const fixtureAuth = require('./auth_helpers.cjs').authenticatedFixture();
const fetch = fixtureAuth.fetch;
// Real read-only project UI. Synthetic lifecycle fixture or copies of actual lab files;
// neither mode executes project code or qualifies externally recorded science/training.
'use strict';
const assert=require('node:assert/strict'), fs=require('node:fs'), os=require('node:os'), path=require('node:path'), crypto=require('node:crypto');
const {spawn,execFileSync}=require('node:child_process');
const {pageLoadTracker}=require('./browser_page_load.cjs');
const {waitForDebugger}=require('./browser_startup.cjs');
const {qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const scenarioIndex=process.argv.indexOf('--scenario');
assert.equal(process.argv[scenarioIndex+1],'catalog','Use --scenario catalog');
const root=path.resolve(__dirname,'..'), labIndex=-1;
assert.ok(labIndex<0||process.argv[labIndex+1],'--lab-root requires an existing checkout');
const labRoot=labIndex<0?null:path.resolve(process.argv[labIndex+1]);
const report=qaDirectory(root,'workspace-extensions-catalog');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-project-browser-')),projectRoot=path.join(temporary,'projects');
fs.mkdirSync(projectRoot);
const sha=raw=>crypto.createHash('sha256').update(raw).digest('hex');
const sourceHashes={},captures=[],checks=[],requests=[],errors=[],children=[],tracker=pageLoadTracker();
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
let ws,send,evaluate,serverErrors='',browserErrors='',phase='prepare';
async function until(fn,message='Timed out'){for(let i=0;i<600;i++){const value=await fn();if(value)return value;await pause(100);}throw Error(message);}
function launch(command,args,options){const child=spawn(command,args,options);children.push(child);return child;}
function write(relative,raw){const destination=path.join(projectRoot,relative);fs.mkdirSync(path.dirname(destination),{recursive:true});fs.writeFileSync(destination,raw);return relative;}
function reference(id,label,relative){return {id,label,path:relative,sha256:sha(fs.readFileSync(path.join(projectRoot,relative)))};}
function copied(relative){const raw=fs.readFileSync(path.join(labRoot,relative));sourceHashes[relative]=sha(raw);return write('copied/'+relative,raw);}
function snapshot(directory){const result={};function walk(current){for(const entry of fs.readdirSync(current,{withFileTypes:true})){const next=path.join(current,entry.name);if(entry.isDirectory())walk(next);else{assert.ok(entry.isFile(),'Fixture has no symlinks/special files');result[path.relative(directory,next)]=sha(fs.readFileSync(next));}}}walk(directory);return result;}
const fixture=path.join(root,'tests/fixtures/extensions/catalog');
for(const name of fs.readdirSync(fixture))fs.copyFileSync(path.join(fixture,name),path.join(projectRoot,name));
const first=JSON.parse(fs.readFileSync(path.join(projectRoot,'project.json'),'utf8'));
first.extensions[1].label='<img src=x onerror="window.extensionExecuted=true"> malformed sibling';
const second={...first,id:'b'.repeat(32),name:'Extensions disabled in this snapshot',extensions:[]};
write('alpha.project.json',JSON.stringify(first,null,2));write('beta.project.json',JSON.stringify(second,null,2));
const before=snapshot(projectRoot);
const serverArgs=port=>['-u','app.py','--port',String(port),'--data',path.join(temporary,'data'),'--project-root','sample='+projectRoot];
(async()=>{
  phase='start-server';
  let server=launch('python3',serverArgs(0),{cwd:root,stdio:['ignore','pipe','pipe']});
  let output='';server.stdout.on('data',chunk=>output+=chunk);server.stderr.on('data',chunk=>serverErrors+=chunk);
  const port=await until(()=>{if(server.exitCode!==null)throw Error('Project server exited: '+serverErrors);return output.match(/127\.0\.0\.1:(\d+)/)?.[1];});
  const base='http://127.0.0.1:'+port;
  await fixtureAuth.register('http://127.0.0.1:'+port,path.join(temporary,'data'),root);
  phase='start-browser';
  const browser=launch(process.env.BROWSER||'/usr/bin/chromium',['--headless','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--window-size=1440,900','--user-data-dir='+path.join(temporary,'browser'),'about:blank'],{stdio:['ignore','ignore','pipe'],env:{...process.env,XDG_CONFIG_HOME:temporary,XDG_CACHE_HOME:temporary}});
  browser.stderr.on('data',chunk=>browserErrors=(browserErrors+chunk).slice(-16384));
  const debugPort=await waitForDebugger(browser,path.join(temporary,'browser','DevToolsActivePort'));
  const tabs=await(await fetch('http://127.0.0.1:'+debugPort+'/json')).json(),target=tabs.find(tab=>tab.type==='page'&&tab.url==='about:blank');assert.ok(target);
  ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  let next=0,initializationRequest;const pending=new Map();
  send=(method,params={})=>new Promise((resolve,reject)=>{const id=++next,timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method));},20000);pending.set(id,{resolve:value=>{clearTimeout(timer);resolve(value);},reject:error=>{clearTimeout(timer);reject(error);}});ws.send(JSON.stringify({id,method,params}));});
  ws.onmessage=event=>{const message=JSON.parse(event.data);tracker.observe(message);if(message.id){const task=pending.get(message.id);pending.delete(message.id);if(task)message.error?task.reject(message.error):task.resolve(message.result);}if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails);if(message.method==='Network.requestWillBeSent')requests.push({url:message.params.request.url,method:message.params.request.method});if(message.method==='Fetch.requestPaused')initializationRequest=message.params.requestId;};
  evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  const element=selector=>`document.querySelector(${JSON.stringify(selector)})`,text=selector=>evaluate(`${element(selector)}?.textContent`);
  async function click(selector){const box=await until(()=>evaluate(`(async()=>{const e=${element(selector)};if(!e||e.disabled||!e.getClientRects().length)return null;e.scrollIntoView({block:'center'});await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));const b=e.getBoundingClientRect(),x=b.x+b.width/2,y=b.y+b.height/2,hit=document.elementFromPoint(x,y);return hit&&(hit===e||e.contains(hit))?{x,y}:null})()`),'Click target unavailable '+selector);for(const type of ['mousePressed','mouseReleased'])await send('Input.dispatchMouseEvent',{type,button:'left',clickCount:1,...box});}
  async function key(key,code=key,modifiers=0){for(const type of ['keyDown','keyUp'])await send('Input.dispatchKeyEvent',{type,key,code,modifiers,windowsVirtualKeyCode:{Enter:13,Escape:27,Tab:9,a:65}[key]||0,...(type==='keyDown'&&key==='Enter'?{text:'\r',unmodifiedText:'\r'}:{})});}
  async function fill(selector,value){await click(selector);await key('a','KeyA',2);await send('Input.insertText',{text:value});}
  const select=(selector,value)=>evaluate(`(()=>{const e=${element(selector)};e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  async function nav(view){await evaluate(`document.getElementById('nav-${view}').focus()`);await key('Enter');await until(()=>evaluate(`!document.getElementById('view-${view}').hidden && !document.getElementById('project-${view}-root').hidden`));await until(()=>text(`#project-${view}-root`).then(value=>value?.includes('PROJECT · INSPECTION ONLY')));}
  async function capture(name,width,selector){await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});await evaluate(`${element(selector)}.scrollIntoView({block:'start'})`);await pause(80);assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'Project viewport overflow '+name);const file=name+'.jpg';fs.writeFileSync(path.join(report,file),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));captures.push({file,width,height:900,selector,qualification:labRoot?'Copied actual source inspection only; no execution or scientific verification':'Synthetic project UI/lifecycle fixture only'});}
  const check=value=>{checks.push(value);console.log('PASS',value);};
  async function reload(){const previous=(await send('Page.getFrameTree')).frameTree.frame;await send('Page.reload');await until(()=>tracker.reloaded(previous),'Main document reload not observed');}
  async function openProject(manifest,name,id){await click('#open-project');await until(()=>evaluate('document.getElementById("project-open-dialog").open && !document.getElementById("project-open-submit").disabled'));await select('#project-root','sample');await fill('#project-manifest',manifest);await evaluate('document.getElementById("project-open-submit").focus()');await key('Enter');await until(()=>evaluate('document.getElementById("dataset").value==='+JSON.stringify('project:'+id)));await nav('data');assert.match(await text('#project-data-root'),new RegExp(name.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')));}
  await send('Page.enable');await send('Page.setLifecycleEventsEnabled',{enabled:true});await send('Runtime.enable');await send('Network.enable');
  const offlineCanary=process.env.LD_PRELOAD?JSON.parse(execFileSync('python3',['-c',"import sys;sys.path.insert(0,'tests');from test_workspace_offline import CANARY;exec(CANARY)"],{cwd:root,encoding:'utf8'})):null;
  await fixtureAuth.browser(send,'http://127.0.0.1:'+port);
  phase='open-workspaces';
  await send('Fetch.enable',{patterns:[{urlPattern:base+'/workspaces.js',requestStage:'Request'}]});
  await send('Page.navigate',{url:base+'/workspaces'});
  await until(()=>initializationRequest&&evaluate('!!document.getElementById("open-project")'),'Workspace initialization script was not intercepted');
  assert.equal(await evaluate('document.getElementById("open-project").onclick'),null);
  await send('Fetch.continueRequest',{requestId:initializationRequest});await send('Fetch.disable');
  // The parser creates the enabled button before the bottom scripts bind it.
  // Wait for the real handlers before issuing the single user click.
  await until(()=>evaluate('typeof document.getElementById("open-project")?.onclick === "function" && typeof document.getElementById("project-open-form")?.onsubmit === "function"'),'Project controls are not initialized');
  check('Parser-created controls are not treated as ready before the real workspace handlers bind');
  phase='open-alpha';
  await openProject('alpha.project.json',first.name,first.id);
  phase='inspect-catalog';
  const details=await(await fetch(base+'/api/workspace/project-snapshots/'+first.id)).json();
  assert.equal(details.execution,'unsupported');assert.equal(details.schema_version,2);
  assert.deepEqual(details.extensions.packages.map(item=>item.state),['valid','invalid','unavailable']);
  assert.equal(details.extensions.packages[0].host.state,'compatible');
  assert.equal(details.extensions.packages[0].runtime.state,'unavailable');
  assert.equal(details.extensions.packages[0].permission.state,'unavailable');
  assert.match(await text('#project-data-root .project-extensions'),/Example field declarations/);
  assert.match(await text('#project-data-root .project-extensions'),/Malformed sibling|malformed sibling/);
  assert.match(await text('#project-data-root .project-extensions'),/Absent package/);
  assert.equal(await evaluate('!!window.extensionExecuted'),false);
  assert.equal(await evaluate('document.querySelector(".project-extensions img")'),null);
  phase='capture-catalog';
  await capture('extensions-catalog-1440',1440,'#project-data-root .project-extensions');
  await capture('extensions-catalog-390',390,'#project-data-root .project-extensions');
  check('Real owner HTTP/browser shows independent validity, integrity, host, runtime and permission without executing fixture source or active labels');
  const summary='#project-data-root .project-extensions details summary';
  await evaluate(`${element(summary)}.focus()`);await key('Enter');
  assert.equal(await evaluate('document.querySelector("#project-data-root .project-extensions details").open'),true);
  assert.match(await text('#project-data-root .project-extensions details'),/example.field:model/);
  await capture('extensions-identity-390',390,'#project-data-root .project-extensions');
  await nav('pipeline');assert.equal(await evaluate('document.querySelectorAll("#project-pipeline-root [data-project-recipe]").length'),0);
  await nav('runs');assert.equal(await evaluate('document.querySelectorAll("#project-runs-root [data-project-evidence]").length'),0);
  check('Keyboard expands exact package/contribution identity; v2 exposes inspection-only actions on all three panels');
  phase='switch-beta';
  await openProject('beta.project.json',second.name,second.id);
  assert.match(await text('#project-data-root .project-extensions'),/No extensions enabled/);
  assert.doesNotMatch(await text('#project-data-root .project-extensions'),/Example field declarations/);
  // Deliberately let a superseded fetch finish after the newer selection.
  await evaluate(`(()=>{const original=TuldokAuth.fetch;window.restoreExtensionFetch=()=>TuldokAuth.fetch=original;TuldokAuth.fetch=async (...args)=>{const response=await original(...args);if(String(args[0]).endsWith('/${first.id}'))await new Promise(resolve=>setTimeout(resolve,350));return response;};})()`);
  phase='late-catalog';
  await select('#dataset','project:'+first.id);await pause(60);await select('#dataset','project:'+second.id);
  await until(()=>text('#project-data-root').then(value=>value?.includes(second.name)));await pause(450);
  assert.match(await text('#project-data-root .project-extensions'),/No extensions enabled/);
  await evaluate('window.restoreExtensionFetch()');
  check('Context-local disablement retains old snapshot; a delayed old catalog cannot replace current project');
  await select('#dataset','project:'+first.id);await until(()=>text('#project-data-root .project-extensions').then(value=>value?.includes('Example field declarations')));
  phase='reload';
  await reload();await until(()=>text('#project-data-root .project-extensions').then(value=>value?.includes('Example field declarations')));
  assert.deepEqual(await(await fetch(base+'/api/workspace/runs')).json(),[]);
  assert.deepEqual(snapshot(projectRoot),before);
  assert.ok(!fs.existsSync(path.join(projectRoot,'EXECUTED')));
  assert.ok(!requests.some(item=>item.method==='POST'&&/\/api\/workspace\/(runs|graphs)|\/api\/workbench\//.test(item.url)));
  assert.ok(!requests.some(item=>/^https?:/.test(item.url)&&!item.url.startsWith(base+'/')),'No external browser network requests');
  assert.deepEqual(errors,[]);assert.ok(!serverErrors.includes('Traceback'),serverErrors);
  check('Cold browser reload preserves catalog identity; no Run/grant/action, source mutation or external browser request occurs');
  fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify({source_commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),dirty:!!execFileSync('git',['status','--porcelain'],{cwd:root,encoding:'utf8'}).trim(),command:'node tests/browser_workspace_extensions.cjs --scenario catalog',qualification:labRoot?'Inspection of exact copies of actual lab files only; no new training, execution or scientific verification':'Generic synthetic project UI/lifecycle only',actual_lab_source:labRoot?{commit:execFileSync('git',['rev-parse','HEAD'],{cwd:labRoot,encoding:'utf8'}).trim(),files:sourceHashes}:null,project_file_hashes:before,checks,captures,offline_canary:offlineCanary,execution_submitted:false,source_mutation:false,browser:(await send('Browser.getVersion')).product},null,2));
  console.log('PASS inert extension catalog browser:',report);
})().catch(async error=>{fs.writeFileSync(path.join(report,'failure.json'),JSON.stringify({phase,error:String(error),stack:error.stack,checks,captures,server_stderr:serverErrors.slice(-16384),browser_stderr:browserErrors},null,2));console.error('Extension catalog failure phase:',phase);console.error(error);console.error('Application stderr:',serverErrors);console.error('Browser stderr:',browserErrors);if(evaluate)try{console.error(await evaluate('JSON.stringify({url:location.href,body:document.body.innerText.slice(-9000)})'));}catch{}process.exitCode=1;}).finally(()=>{ws?.close();for(const child of children.reverse())child.kill('SIGTERM');});
