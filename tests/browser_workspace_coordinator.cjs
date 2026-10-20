'use strict';
// Real coordinator lock fault, lost recovery reply and first neutral custody dispatch.
// No model training or scientific acceptance is exercised.
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn,execFileSync}=require('node:child_process');
const {authenticatedFixture}=require('./auth_helpers.cjs'),{waitForDebugger}=require('./browser_startup.cjs');
const {pageLoadTracker}=require('./browser_page_load.cjs');
const {stopOwnedChildren}=require('./browser_owned_cleanup.cjs');
const tracker=pageLoadTracker();
const {qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const root=path.resolve(__dirname,'..'),report=qaDirectory(root,'workspace-coordinator'),temp=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-coordinator-browser-'));
const auth=authenticatedFixture(),children=[],errors=[],requests=[],checks=[];
let ws,evaluate,send,stderr='';const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn,label){for(let i=0;i<750;i++){const value=await fn();if(value)return value;await pause(100);}throw Error(label||'Timed out');}
function launch(command,args,options={}){const child=spawn(command,args,{cwd:root,...options});children.push(child);return child;}
(async()=>{
  const fixture=launch(process.env.PYTHON||'python3',['-u','tests/coordinator_browser_fixture.py',path.join(report,'domain-receipt.json')],{env:{...process.env,PYTHONPATH:'.:tests',PYTHONDONTWRITEBYTECODE:'1'},stdio:['pipe','pipe','pipe']});
  let output='';fixture.stdout.on('data',chunk=>output+=chunk);fixture.stderr.on('data',chunk=>stderr+=chunk);
  const info=await until(()=>{if(fixture.exitCode!==null)throw Error('Fixture exited '+stderr);try{return JSON.parse(output.split('\n')[0]);}catch{return null;}},'Neutral coordinator fixture unavailable');
  const base='http://127.0.0.1:'+info.port;await auth.register(base,info.data,root);
  const browser=launch(process.env.BROWSER||'/usr/bin/chromium',['--headless','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--window-size=1440,900','--user-data-dir='+path.join(temp,'browser'),'about:blank'],{stdio:'ignore',env:{...process.env,XDG_CONFIG_HOME:temp,XDG_CACHE_HOME:temp}});
  const debug=await waitForDebugger(browser,path.join(temp,'browser','DevToolsActivePort'));
  const target=(await(await fetch('http://127.0.0.1:'+debug+'/json')).json()).find(tab=>tab.type==='page');
  ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  let next=0;const pending=new Map();
  send=(method,params={})=>new Promise((resolve,reject)=>{const id=++next,timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method));},25000);pending.set(id,{resolve:value=>{clearTimeout(timer);resolve(value);},reject});ws.send(JSON.stringify({id,method,params}));});
  ws.onmessage=event=>{const message=JSON.parse(event.data);tracker.observe(message);if(message.id){const task=pending.get(message.id);pending.delete(message.id);if(task)message.error?task.reject(message.error):task.resolve(message.result);}if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails);if(message.method==='Network.requestWillBeSent')requests.push({url:message.params.request.url,method:message.params.request.method,headers:message.params.request.headers,body:message.params.request.postData});};
  evaluate=async expression=>{const value=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(value.exceptionDetails)throw Error(JSON.stringify(value.exceptionDetails));return value.result.value;};
  const text=selector=>evaluate(`document.querySelector(${JSON.stringify(selector)})?.textContent`);
  async function activate(selector,keyboard=false){
    await until(()=>evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});if(!e||e.disabled||!e.getClientRects().length)return false;e.scrollIntoView({block:'center'});return true;})()`),'Control unavailable '+selector);
    if(keyboard){await evaluate(`document.querySelector(${JSON.stringify(selector)}).focus()`);for(const type of ['keyDown','keyUp'])await send('Input.dispatchKeyEvent',{type,key:'Enter',code:'Enter',windowsVirtualKeyCode:13,...(type==='keyDown'?{text:'\r'}:{})});}
    else{const box=await evaluate(`(()=>{const r=document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()`);for(const type of ['mousePressed','mouseReleased'])await send('Input.dispatchMouseEvent',{type,button:'left',clickCount:1,...box});}
  }
  await send('Page.enable');await send('Page.setLifecycleEventsEnabled',{enabled:true});await send('Runtime.enable');await send('Network.enable');await auth.browser(send,base);
  await send('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:path.join(temp,'downloads')});
  await send('Page.navigate',{url:base+'/workspaces#runs'});
  await until(()=>evaluate('!!document.getElementById("dataset") && !document.getElementById("dataset").disabled && typeof document.getElementById("dataset").onchange==="function"'));
  await evaluate('(()=>{const select=document.getElementById("dataset");select.value="catalog";select.dispatchEvent(new Event("change",{bubbles:true}));})()');
  await until(()=>text('#coordinator-health').then(value=>value?.includes('generation 1')),'Real faulted coordinator health missing');
  assert.match(await text('#coordinator-health'),/faulted/);
  assert.equal(await text('#real-run-state'),'queued');
  await activate('#coordinator-recover',true);
  await until(()=>text('#coordinator-health').then(value=>value?.includes('generation 2')&&value.includes('ready for new work')),'Saved receipt did not reconcile the deliberately lost reply');
  await until(()=>text('#real-run-state').then(value=>value==='completed'),'Preserved original queue did not execute its first neutral GO');
  assert.equal(requests.filter(request=>request.url.endsWith('/coordinator/recover')).length,1,'Unknown reply must not cause another mutation dispatch');
  assert.equal(await evaluate('!!document.getElementById("coordinator-recover")'),false);
  const receipt=JSON.parse(await text('#coordinator-panel details pre'));
  assert.equal(receipt.expected_generation,1);assert.equal(receipt.completed_generation,2);
  const sent=JSON.parse(requests.find(request=>request.url.endsWith('/coordinator/recover')).body);
  assert.equal(receipt.request_key,sent.request_key);
  const before=(await send('Page.getFrameTree')).frameTree.frame;
  await send('Page.reload');await until(()=>tracker.reloaded(before),'Fresh coordinator document did not reload');
  await until(()=>text('#coordinator-health').then(value=>value?.includes('generation 2')),'Reopened coordinator receipt missing');
  assert.equal(requests.filter(request=>request.url.endsWith('/coordinator/recover')).length,1);
  await activate('#coordinator-refresh');
  assert.deepEqual(JSON.parse(await text('#coordinator-panel details pre')),receipt);
  assert.ok(requests.filter(request=>request.url.includes('/api/workspace/coordinator')).every(request=>request.headers['Tuldok-Operation-Contract']?.startsWith(request.method==='POST'?'runs.recover_coordinator/1/':'runs.coordinator_health/1/')));
  assert.ok(!requests.some(request=>request.url.includes('/retry')||request.url.includes('/submit-external')||request.url.includes('select-candidate')));
  assert.deepEqual(errors,[]);
  for(const width of [1440,390]){await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});await evaluate('document.getElementById("coordinator-panel").scrollIntoView({block:"start"})');await pause(80);assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'Viewport overflow');fs.writeFileSync(path.join(report,'coordinator-'+width+'.jpg'),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));}
  checks.push('Real separate PostgreSQL advisory lock causes coordinator timeout/fault',
    'Keyboard explicit owner recovery names original generation and stable request',
    'Deliberately lost HTTP acknowledgement reconciles through saved read without another mutation',
    'Original queued neutral attempt executes first GO and completes with same admission identities',
    'Fresh reload and mouse refresh preserve exact completed receipt',
    'All coordinator operations pinned;1440/390 layouts without overflow');
  fixture.stdin.end('finish\n');await until(()=>fixture.exitCode!==null,'Owned coordinator fixture cleanup did not finish');assert.equal(fixture.exitCode,0,stderr);
  const domain=JSON.parse(fs.readFileSync(path.join(report,'domain-receipt.json'),'utf8'));assert.equal(domain.go_sends,1);assert.equal(domain.health.generation,2);assert.equal(domain.dropped_reply,true);
  fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify({source_head:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),scope:'Neutral coordinator UI/process custody; no training or science claim',checks,browser:(await send('Browser.getVersion')).product,run_id:info.run_id},null,2)+'\n');
  console.log('PASS coordinator browser:',report);
})().catch(async error=>{console.error(error);console.error('Fixture stderr:',stderr);if(evaluate)try{console.error(await evaluate('document.body.innerText.slice(-9000)'));}catch{}process.exitCode=1;}).finally(async()=>{ws?.close();await stopOwnedChildren([...children].reverse());fs.rmSync(temp,{recursive:true,force:true,maxRetries:5,retryDelay:100});});
