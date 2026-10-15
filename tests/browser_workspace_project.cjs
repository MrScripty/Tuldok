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
const root=path.resolve(__dirname,'..'), labIndex=process.argv.indexOf('--lab-root');
assert.ok(labIndex<0||process.argv[labIndex+1],'--lab-root requires an existing checkout');
const labRoot=labIndex<0?null:path.resolve(process.argv[labIndex+1]);
const report=qaDirectory(root,labRoot?'workspace-project-lab':'workspace-project');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-project-browser-')),projectRoot=path.join(temporary,'projects');
fs.mkdirSync(projectRoot);
const sha=raw=>crypto.createHash('sha256').update(raw).digest('hex');
const sourceHashes={},captures=[],checks=[],requests=[],errors=[],children=[],tracker=pageLoadTracker();
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
let ws,send,evaluate,serverErrors='';
async function until(fn,message='Timed out'){for(let i=0;i<600;i++){const value=await fn();if(value)return value;await pause(100);}throw Error(message);}
function launch(command,args,options){const child=spawn(command,args,options);children.push(child);return child;}
function write(relative,raw){const destination=path.join(projectRoot,relative);fs.mkdirSync(path.dirname(destination),{recursive:true});fs.writeFileSync(destination,raw);return relative;}
function reference(id,label,relative){return {id,label,path:relative,sha256:sha(fs.readFileSync(path.join(projectRoot,relative)))};}
function copied(relative){const raw=fs.readFileSync(path.join(labRoot,relative));sourceHashes[relative]=sha(raw);return write('copied/'+relative,raw);}
function snapshot(directory){const result={};function walk(current){for(const entry of fs.readdirSync(current,{withFileTypes:true})){const next=path.join(current,entry.name);if(entry.isDirectory())walk(next);else{assert.ok(entry.isFile(),'Fixture has no symlinks/special files');result[path.relative(directory,next)]=sha(fs.readFileSync(next));}}}walk(directory);return result;}
const first={schema_version:1,id:'a'.repeat(32),name:labRoot?'Copied actual lab · inspection only':'Authored project Alpha',data:[],recipes:[],evidence:[],requirements:[]};
if(labRoot){
  first.data.push(reference('freeze','Copied actual trajectory freeze',copied('experiments/trajectory-v2/freeze.json')));
  first.data.push(reference('checkpoint','Copied external checkpoint · not loaded',copied('experiments/trajectory-v2/model.pt')));
  first.recipes.push(reference('recipe','Copied actual recipe · not executable',copied('scripts/trajectory_experiment.py')));
  first.evidence.push(reference('report','Copied actual README · external evidence',copied('README.md')));
  first.evidence.push(reference('large-result','Copied actual result · bounded preview',copied('experiments/trajectory-v2/result.json')));
}else{
  first.data.push(reference('sample','Authored sample data',write('alpha/data.json',JSON.stringify({source:'synthetic project fixture',values:[1,2,3]}))));
  first.recipes.push(reference('recipe','Authored recipe · execution trap',write('alpha/recipe.py',"from pathlib import Path\nPath(__file__).with_name('EXECUTED').write_text('must never run')\n")));
  first.evidence.push(reference('report','Alpha external evidence',write('alpha/report.md','# External Alpha evidence\nAuthored UI fixture, not a completed Tuldok run.\n<script>window.projectExecuted=true</script>\nCafé 😀 山\n')));
}
first.data.push({id:'missing-data',label:'Unavailable external dataset',path:'not-installed/data.json'});
first.requirements=[{id:'present',label:'Recipe file present; runtime unqualified',path:first.recipes[0].path},
  {id:'missing',label:'Missing optional runtime',path:'not-installed/python'},
  {id:'declared',label:'Unprobed GPU requirement'}];
const second={schema_version:1,id:'b'.repeat(32),name:'Authored project Beta',data:[reference('beta','Only Beta data',write('beta/data.txt','Private-to-Beta synthetic fixture data\n'))],recipes:[],evidence:[reference('report','Beta external evidence',write('beta/report.md','Beta evidence belongs only to the second project.\n'))],requirements:[]};
write('alpha.project.json',JSON.stringify(first,null,2));write('beta.project.json',JSON.stringify(second,null,2));
const before=snapshot(projectRoot), expectedEvidence=fs.readFileSync(path.join(projectRoot,first.evidence[0].path),'utf8');
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
  const element=selector=>`document.querySelector(${JSON.stringify(selector)})`,text=selector=>evaluate(`${element(selector)}?.textContent`);
  async function click(selector){const box=await until(()=>evaluate(`(async()=>{const e=${element(selector)};if(!e||e.disabled||!e.getClientRects().length)return null;e.scrollIntoView({block:'center'});await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));const b=e.getBoundingClientRect(),x=b.x+b.width/2,y=b.y+b.height/2,hit=document.elementFromPoint(x,y);return hit&&(hit===e||e.contains(hit))?{x,y}:null})()`),'Click target unavailable '+selector);for(const type of ['mousePressed','mouseReleased'])await send('Input.dispatchMouseEvent',{type,button:'left',clickCount:1,...box});}
  async function key(key,code=key,modifiers=0){for(const type of ['keyDown','keyUp'])await send('Input.dispatchKeyEvent',{type,key,code,modifiers,windowsVirtualKeyCode:{Enter:13,Escape:27,Tab:9,a:65}[key]||0,...(type==='keyDown'&&key==='Enter'?{text:'\r',unmodifiedText:'\r'}:{})});}
  async function fill(selector,value){await click(selector);await key('a','KeyA',2);await send('Input.insertText',{text:value});}
  const select=(selector,value)=>evaluate(`(()=>{const e=${element(selector)};e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  async function nav(view){await evaluate(`document.getElementById('nav-${view}').focus()`);await key('Enter');await until(()=>evaluate(`!document.getElementById('view-${view}').hidden && !document.getElementById('project-${view}-root').hidden`));await until(()=>text(`#project-${view}-root`).then(value=>value?.includes('PROJECT · SAVED SNAPSHOT')));}
  async function capture(name,width,selector){await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});await evaluate(`${element(selector)}.scrollIntoView({block:'start'})`);await pause(80);assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'Project viewport overflow '+name);const file=name+'.jpg';fs.writeFileSync(path.join(report,file),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));captures.push({file,width,height:900,selector,qualification:labRoot?'Copied actual source inspection only; no execution or scientific verification':'Synthetic project UI/lifecycle fixture only'});}
  const check=value=>{checks.push(value);console.log('PASS',value);};
  async function reload(){const previous=(await send('Page.getFrameTree')).frameTree.frame;await send('Page.reload');await until(()=>tracker.reloaded(previous),'Main document reload not observed');}
  async function openProject(manifest,name,id){await click('#open-project');await until(()=>evaluate('document.getElementById("project-open-dialog").open && !document.getElementById("project-open-submit").disabled'));await select('#project-root','sample');await fill('#project-manifest',manifest);await evaluate('document.getElementById("project-open-submit").focus()');await key('Enter');await until(()=>evaluate('document.getElementById("dataset").value==='+JSON.stringify('project:'+id)));await nav('data');assert.match(await text('#project-data-root'),new RegExp(name.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')));}
  await send('Page.enable');await send('Page.setLifecycleEventsEnabled',{enabled:true});await send('Runtime.enable');await send('Network.enable');
  const offlineCanary=process.env.LD_PRELOAD?JSON.parse(execFileSync('python3',['-c',"import sys;sys.path.insert(0,'tests');from test_workspace_offline import CANARY;exec(CANARY)"],{cwd:root,encoding:'utf8'})):null;
  await fixtureAuth.browser(send,'http://127.0.0.1:'+port);
  await send('Page.navigate',{url:base+'/workspaces'});await until(()=>evaluate('!!document.getElementById("open-project")'));
  await openProject('alpha.project.json',first.name,first.id);
  const details=await(await fetch(base+'/api/workspace/projects/'+first.id)).json();assert.equal(details.execution,'unsupported');assert.equal(details.manifest_status,'unchanged');
  assert.equal(details.data.find(item=>item.id==='missing-data').status,'missing');assert.equal(details.requirements.find(item=>item.id==='present').status,'present_unqualified');assert.equal(details.requirements.find(item=>item.id==='missing').status,'missing');assert.equal(details.requirements.find(item=>item.id==='declared').status,'unverified');
  assert.match(await text('#project-data-root'),/present_unqualified/);assert.match(await text('#project-data-root'),/Missing optional runtime/);
  assert.ok(details.data.filter(item=>item.id!=='missing-data').every(item=>item.integrity==='verified'));
  await capture('project-data-1440',1440,'#project-data-root');await capture('project-data-390',390,'#project-data-root');
  check('Project opens through keyboard form; data hashes and missing/present-unqualified/unprobed requirements remain distinct');
  await nav('pipeline');assert.match(await text('#project-pipeline-root'),/not executable/);assert.equal(await evaluate('document.querySelectorAll("#project-pipeline-root form").length'),0);
  await capture('project-pipeline-390',390,'#project-pipeline-root');
  await nav('runs');assert.match(await text('#project-runs-root'),/not a Tuldok-completed run or scientific qualification/);
  await click('#project-runs-root [data-project-evidence="report"]');await until(()=>evaluate('!!document.querySelector("#project-runs-root .project-evidence-output pre")'));
  assert.equal(await text('#project-runs-root .project-evidence-output pre'),expectedEvidence);assert.equal(await evaluate('window.projectExecuted===true'),false);
  assert.match(await text('#project-runs-root .project-evidence-output'),/not a Tuldok run or scientific validation/);
  await capture('project-evidence-1440',1440,'#project-runs-root .project-evidence-output');await capture('project-evidence-390',390,'#project-runs-root .project-evidence-output');
  if(labRoot){await click('#project-runs-root [data-project-evidence="large-result"]');await until(()=>text('#project-runs-root .project-evidence-output').then(value=>value?.includes('inspection limit')));check('Actual copied 4MiB result is hash-inspected but bounded text preview is refused honestly');}
  check('Pipeline exposes nonexecutable references; Runs renders exact external evidence as text without a completion claim');
  await openProject('beta.project.json',second.name,second.id);assert.match(await text('#project-data-root'),/Only Beta data/);assert.doesNotMatch(await text('#project-data-root'),/Unavailable external dataset|Copied actual trajectory freeze|Authored sample data/);
  await nav('runs');await click('#project-runs-root [data-project-evidence="report"]');await until(()=>text('#project-runs-root .project-evidence-output pre').then(value=>value?.startsWith('Beta evidence')));
  await select('#dataset','project:'+first.id);await until(()=>text('#project-runs-root').then(value=>value?.includes(first.name)));assert.equal(await evaluate('document.querySelector("#project-runs-root .project-evidence-output pre")'),null);assert.doesNotMatch(await text('#project-runs-root'),/Beta evidence belongs/);
  await click('#project-runs-root [data-project-evidence="report"]');await until(()=>text('#project-runs-root .project-evidence-output pre').then(value=>value===expectedEvidence));
  check('Two projects with shared reference ID stay isolated; switching clears previous external evidence');
  await reload();await until(()=>evaluate('document.getElementById("dataset")?.value==='+JSON.stringify('project:'+first.id)));await until(()=>text('#project-runs-root').then(value=>value?.includes(first.name)));assert.equal(await evaluate('document.getElementById("view-runs").hidden'),false);
  server.kill('SIGINT');await until(()=>server.exitCode!==null,'Project server did not drain');server=launch('python3',serverArgs(port),{cwd:root,stdio:['ignore','pipe','pipe']});let reopened='';server.stdout.on('data',chunk=>reopened+=chunk);server.stderr.on('data',chunk=>serverErrors+=chunk);await until(()=>reopened.includes('Tuldok:'));
  await reload();await until(()=>text('#project-runs-root').then(value=>value?.includes(first.name)));await click('#project-runs-root [data-project-evidence="report"]');await until(()=>text('#project-runs-root .project-evidence-output pre').then(value=>value===expectedEvidence));
  assert.equal((await(await fetch(base+'/api/workspace/projects')).json()).projects.length,2);assert.deepEqual(await(await fetch(base+'/api/workspace/runs')).json(),[]);
  assert.deepEqual(snapshot(projectRoot),before);if(labRoot)for(const [relative,digest] of Object.entries(sourceHashes))assert.equal(sha(fs.readFileSync(path.join(labRoot,relative))),digest);
  assert.ok(!requests.some(item=>item.method==='POST'&&/\/api\/workspace\/(runs|graphs)|\/api\/workbench\//.test(item.url)),'Project browsing must not submit run, graph or record writes');
  assert.deepEqual(errors,[]);assert.ok(!serverErrors.includes('Traceback'),serverErrors);
  check('Browser reload and server restart retain project selection/catalog; all source/copy bytes unchanged and no execution submitted');
  fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify({source_commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),dirty:!!execFileSync('git',['status','--porcelain'],{cwd:root,encoding:'utf8'}).trim(),command:'node tests/browser_workspace_project.cjs'+(labRoot?' --lab-root <actual-checkout>':''),qualification:labRoot?'Inspection of exact copies of actual lab files only; no new training, execution or scientific verification':'Generic synthetic project UI/lifecycle only',actual_lab_source:labRoot?{commit:execFileSync('git',['rev-parse','HEAD'],{cwd:labRoot,encoding:'utf8'}).trim(),files:sourceHashes}:null,project_file_hashes:before,checks,captures,offline_canary:offlineCanary,execution_submitted:false,source_mutation:false,browser:(await send('Browser.getVersion')).product},null,2));
  console.log('PASS read-only project browser:',report);
})().catch(async error=>{console.error(error);console.error('Application stderr:',serverErrors);if(evaluate)try{console.error(await evaluate('JSON.stringify({url:location.href,body:document.body.innerText.slice(-9000)})'));}catch{}process.exitCode=1;}).finally(()=>{ws?.close();for(const child of children.reverse())child.kill('SIGTERM');});
