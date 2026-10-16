'use strict';
const fixtureAuth = require('./auth_helpers.cjs').authenticatedFixture();
const fetch = fixtureAuth.fetch;
// Real trusted-local neutral recipe execution and artifact custody.
// This authored process fixture does not qualify a scientific result or model.
const assert=require('node:assert/strict'), fs=require('node:fs'), os=require('node:os'), path=require('node:path'), crypto=require('node:crypto');
const {spawn,execFileSync}=require('node:child_process');
const {pageLoadTracker}=require('./browser_page_load.cjs');
const {waitForDebugger}=require('./browser_startup.cjs');
const {qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const root=path.resolve(__dirname,'..'),report=qaDirectory(root,'workspace-external');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-external-browser-')),projectRoot=path.join(temporary,'project');fs.mkdirSync(projectRoot);
const sha=raw=>crypto.createHash('sha256').update(raw).digest('hex');
const captures=[],checks=[],requests=[],errors=[],children=[],tracker=pageLoadTracker();
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
let ws,send,evaluate,serverErrors='';
async function until(fn,message='Timed out'){for(let i=0;i<600;i++){const value=await fn();if(value)return value;await pause(100);}throw Error(message);}
function launch(command,args,options){const child=spawn(command,args,options);children.push(child);return child;}
const input=Buffer.concat([Buffer.from('Neutral browser input λ\n'),Buffer.from([0,255])]);
const source=fs.readFileSync(path.join(root,'tests/fixtures/external_recipe.py'));
const definition={schema_version:1,format:'external_recipe_v1',id:'neutral',name:'Neutral execution',version:1,runtime:'system_python',sources:[{path:'recipe.py',sha256:sha(source)}],entrypoint:'recipe.py',arguments:[{parameter:'mode'},{input:'sample'},{output_dir:true}],parameters:{mode:{type:'string',default:'complete',enum:['complete','sleep','nonzero'],max_length:16}},inputs:{sample:{max_bytes:4096}},outputs:[{path:'result.txt',role:'result',max_bytes:4096,required:true}],environment:{},resources:{wall_seconds:10,max_output_bytes:16384}};
const recipe=Buffer.from(JSON.stringify(definition));
const project={schema_version:1,id:crypto.randomBytes(16).toString('hex'),name:'Neutral process fixture',data:[{id:'sample',label:'Exact bytes',path:'input.bin',sha256:sha(input)}],recipes:[{id:'neutral',label:'Neutral executable',path:'recipe.json',sha256:sha(recipe)}],evidence:[],requirements:[]};
for(const [name,bytes] of Object.entries({'recipe.py':source,'recipe.json':recipe,'input.bin':input,'project.json':JSON.stringify(project)}))fs.writeFileSync(path.join(projectRoot,name),bytes);
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
  async function nav(view){await click('#nav-'+view);await until(()=>evaluate(`!document.getElementById('view-${view}').hidden && !document.getElementById('project-${view}-root').hidden`));await until(()=>text(`#project-${view}-root`).then(value=>value?.includes('PROJECT · SAVED SNAPSHOT')));}
  async function capture(name,width,selector){await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});await evaluate(`${element(selector)}.scrollIntoView({block:'start'})`);await pause(80);assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'Project viewport overflow '+name);const file=name+'.jpg';fs.writeFileSync(path.join(report,file),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));captures.push({file,width,height:900,selector,qualification:'Neutral process execution only; no scientific qualification'});}
  const check=value=>{checks.push(value);console.log('PASS',value);};
  async function reload(){const previous=(await send('Page.getFrameTree')).frameTree.frame;await send('Page.reload');await until(()=>tracker.reloaded(previous),'Main document reload not observed');}
  async function openProject(manifest,name,id){await click('#open-project');await until(()=>evaluate('document.getElementById("project-open-dialog").open && !document.getElementById("project-open-submit").disabled'));await select('#project-root','sample');await fill('#project-manifest',manifest);await evaluate('document.getElementById("project-open-submit").focus()');await key('Enter');await until(()=>evaluate('document.getElementById("dataset").value==='+JSON.stringify('project:'+id)));await nav('data');assert.match(await text('#project-data-root'),new RegExp(name.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')));}
  await send('Page.enable');await send('Page.setLifecycleEventsEnabled',{enabled:true});await send('Runtime.enable');await send('Network.enable');
  const offlineCanary=process.env.LD_PRELOAD?JSON.parse(execFileSync('python3',['-c',"import sys;sys.path.insert(0,'tests');from test_workspace_offline import CANARY;exec(CANARY)"],{cwd:root,encoding:'utf8'})):null;
  await fixtureAuth.browser(send,'http://127.0.0.1:'+port);
  await send('Page.navigate',{url:base+'/workspaces'});await until(()=>evaluate('typeof document.getElementById("open-project")?.onclick==="function"'),'Project controls are not bound');
  await openProject('project.json',project.name,project.id);await nav('pipeline');
  await click('[data-project-recipe="neutral"]');await until(()=>evaluate('!!document.querySelector("[data-external-input=sample]")'));
  await select('[data-external-input="sample"]','sample');await fill('#external-create-name','Neutral exact bytes');
  await evaluate('document.getElementById("external-create-submit").focus()');await key('Enter');
  await until(()=>evaluate('!!document.getElementById("external-preflight")'));
  await fill('#external-name','Edited neutral execution');await click('#external-save');await until(()=>text('#external-dirty').then(value=>value?.startsWith('Saved')));
  await click('#external-preflight');await until(()=>evaluate('!document.getElementById("external-reviewed").disabled'));
  assert.match(await text('#external-material'),/Material SHA256/);assert.match(await text('#real-pipeline-root'),/not a sandbox/);
  await capture('external-pipeline-1440',1440,'#external-material');await capture('external-pipeline-390',390,'#external-material');
  fs.writeFileSync(path.join(projectRoot,'input.bin'),'changed after exact review');
  await click('#external-reviewed');await click('#external-submit');
  await until(()=>text('#real-pipeline-root .real-status').then(value=>value&&/changed|hash|stale|match/i.test(value)),'Stale input refusal missing');
  assert.deepEqual(await(await fetch(base+'/api/workspace/runs')).json(),[]);
  fs.writeFileSync(path.join(projectRoot,'input.bin'),input);
  await click('#external-preflight');await until(()=>evaluate('!document.getElementById("external-reviewed").disabled'));
  await click('#external-reviewed');await click('#external-submit');
  await until(()=>text('#real-run-state').then(value=>value==='completed'),'Neutral execution did not complete');
  const completed=(await(await fetch(base+'/api/workspace/runs')).json())[0];
  const detail=await(await fetch(base+'/api/workspace/runs/'+completed.id)).json();
  assert.equal(detail.quality_claim,false);assert.equal(detail.execution_kind,'external_recipe');
  const artifact=detail.artifacts.find(item=>item.name==='result.txt');assert.ok(artifact);assert.equal(artifact.sha256,sha(input));
  assert.deepEqual(Buffer.from(await(await fetch(base+artifact.url)).arrayBuffer()),input);
  assert.doesNotMatch(await text('#real-runs-root'),/Validation accuracy|Fresh holdout|Prediction examples/);
  await capture('external-runs-390',390,'.external-run-custody');await capture('external-runs-1440',1440,'.external-run-custody');
  check('Real keyboard-created edited graph, exact review, stale-byte refusal, descendant execution and exact artifact custody');
  await click('#nav-pipeline');await until(()=>evaluate('!!document.getElementById("external-preflight")'));
  const issued=await(await fetch(base+'/api/access/credentials',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({label:'Browser approved executor',scopes:['inspect','execute','cancel']})})).json();assert.ok(issued.token);
  await click('#external-preflight');await until(()=>evaluate('!document.getElementById("external-reviewed").disabled'));await click('#external-reviewed');
  await click('details:has(#external-recipient) summary');await fill('#external-recipient',issued.identity.actor_id);await click('#external-grant');await until(()=>evaluate('!!document.getElementById("external-grant-receipt")'));
  const approval=await evaluate('document.getElementById("external-grant-receipt").dataset.approvalId');assert.match(approval,/^[a-f0-9]{32}$/);
  await send('Network.setCookie',{name:'tuldok_session',value:issued.token,url:base+'/',httpOnly:true,sameSite:'Strict',path:'/'});await reload();
  await until(()=>evaluate('!!document.getElementById("external-approval-id")'));
  assert.equal(await evaluate('!!document.getElementById("external-reviewed")'),false);
  await click('#external-preflight');await until(()=>text('#external-material').then(value=>value?.includes('Material SHA256')));await fill('#external-approval-id',approval);await click('#external-submit');
  await until(()=>text('#real-run-state').then(value=>value==='completed'));
  const agentRun=(await(await fetch(base+'/api/workspace/runs')).json()).find(item=>item.actor_id===issued.identity.actor_id);assert.ok(agentRun);assert.equal(agentRun.approval_id,approval);
  check('Owner creates an exact-material one-use grant; separately authenticated agent executes it without owner review controls');
  await fixtureAuth.browser(send,base);await reload();
  await click('#nav-pipeline');await until(()=>evaluate('!!document.getElementById("external-clone")'));await click('#external-clone');
  await until(()=>text('#external-name').then(()=>evaluate('document.getElementById("external-name").value.endsWith("copy")')));
  await fill('#external-param-mode','sleep');await click('#external-save');await until(()=>text('#external-dirty').then(value=>value?.startsWith('Saved')));
  await click('#external-preflight');await until(()=>evaluate('!document.getElementById("external-reviewed").disabled'));await click('#external-reviewed');await click('#external-submit');
  await until(()=>evaluate('!!document.getElementById("real-cancel")'));await click('#real-cancel');await until(()=>text('#real-run-state').then(value=>value==='cancelled'),'Cancel did not confirm cessation');
  check('Cloned graph cancellation waits for confirmed custody termination');
  server.kill('SIGINT');await until(()=>server.exitCode!==null);server=launch('python3',serverArgs(port),{cwd:root,stdio:['ignore','pipe','pipe']});let reopened='';server.stdout.on('data',chunk=>reopened+=chunk);server.stderr.on('data',chunk=>serverErrors+=chunk);await until(()=>reopened.includes('Tuldok:'));
  await reload();await until(()=>evaluate('!!document.getElementById("real-run-'+completed.id+'")'));await click('#real-run-'+completed.id);await until(()=>text('#real-run-state').then(value=>value==='completed'));
  assert.deepEqual(Buffer.from(await(await fetch(base+artifact.url)).arrayBuffer()),input);assert.deepEqual(errors,[]);assert.ok(!serverErrors.includes('Traceback'),serverErrors);
  check('Server restart retains exact completed run and downloadable original output');
  fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify({source_commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),qualification:'Neutral real process/descendant and artifact custody only; no scientific/model acceptance',checks,captures,run_id:completed.id,input_sha256:sha(input),browser:(await send('Browser.getVersion')).product},null,2));
  console.log('PASS external recipe browser:',report);
})().catch(async error=>{console.error(error);console.error('Application stderr:',serverErrors);if(evaluate)try{console.error(await evaluate('JSON.stringify({url:location.href,body:document.body.innerText.slice(-9000)})'));}catch{}process.exitCode=1;}).finally(()=>{ws?.close();for(const child of children.reverse())child.kill('SIGTERM');});
