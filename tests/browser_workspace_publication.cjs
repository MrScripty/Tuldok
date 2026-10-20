'use strict';
// Real neutral process/copy fault, owner panel, pause/resume, exact Ref and download.
// No model training or scientific acceptance is exercised.
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn,execFileSync}=require('node:child_process');
const {authenticatedFixture}=require('./auth_helpers.cjs'),{waitForDebugger}=require('./browser_startup.cjs');
const {pageLoadTracker}=require('./browser_page_load.cjs');
const {stopOwnedChildren}=require('./browser_owned_cleanup.cjs');
const tracker=pageLoadTracker();
const {qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const root=path.resolve(__dirname,'..'),report=qaDirectory(root,'workspace-publication'),temp=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-publication-browser-'));
const auth=authenticatedFixture(),children=[],errors=[],requests=[],checks=[];
let ws,evaluate,send,stderr='';const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn,label){for(let i=0;i<750;i++){const value=await fn();if(value)return value;await pause(100);}throw Error(label||'Timed out');}
function launch(command,args,options={}){const child=spawn(command,args,{cwd:root,...options});children.push(child);return child;}
(async()=>{
  const fixture=launch(process.env.PYTHON||'python3',['-u','tests/publication_browser_fixture.py',path.join(report,'domain-receipt.json')],{env:{...process.env,PYTHONPATH:'.:tests',PYTHONDONTWRITEBYTECODE:'1'},stdio:['pipe','pipe','pipe']});
  let output='';fixture.stdout.on('data',chunk=>output+=chunk);fixture.stderr.on('data',chunk=>stderr+=chunk);
  const info=await until(()=>{if(fixture.exitCode!==null)throw Error('Fixture exited '+stderr);try{return JSON.parse(output.split('\n')[0]);}catch{return null;}},'Neutral failed-publication fixture unavailable');
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
  await until(()=>evaluate('!!document.getElementById("dataset") && !document.getElementById("dataset").disabled'));
  await evaluate('(()=>{const select=document.getElementById("dataset");select.value="catalog";select.dispatchEvent(new Event("change",{bubbles:true}));})()');
  await until(()=>text('#publication-eligibility').then(value=>value?.includes('requires_verification')),'Saved publication eligibility missing');
  assert.equal(await text('#real-run-state'),'interrupted');assert.match(await text('#publication-fault'),/unavailable/);
  assert.match(await text('#publication-panel'),/Current bytes still require verification/);
  await activate('#publication-recover',true);
  await until(()=>evaluate('!!document.getElementById("publication-cancel")'),'Pause control missing while recovery active');
  await activate('#publication-cancel');
  await until(()=>text('#publication-attempt-status').then(value=>value?.includes('paused')),'Cancellation did not become paused');
  await until(()=>evaluate('!!document.getElementById("publication-recover") && !document.getElementById("publication-recover").disabled'));
  const previous=(await send('Page.getFrameTree')).frameTree.frame;
  await send('Page.reload');await until(()=>tracker.reloaded(previous),'Fresh Run-panel document did not reload');
  await until(()=>text('#publication-attempt-status').then(value=>value?.includes('paused')),'Saved paused continuation did not reopen');
  await activate('#publication-recover',true);
  await until(()=>text('#publication-attempt-status').then(value=>value?.includes('published')),'Publication did not resume with original request');
  assert.equal(await text('#real-run-state'),'interrupted');assert.match(await text('#publication-attempt-status'),/attempt 2 of 20/);
  await activate('#publication-inspect');await until(()=>evaluate('!!document.getElementById("publication-inspected")'),'Exact result inspection missing');
  await activate('[data-publication-download="result.txt"]',true);
  const download=path.join(temp,'downloads','result.txt');await until(()=>fs.existsSync(download),'Verified browser download missing');
  const measured=crypto.createHash('sha256').update(fs.readFileSync(download)).digest('hex');
  await until(()=>text('#publication-message').then(value=>value?.includes('whole SHA256 verification')));
  await activate('#publication-evidence');await until(()=>text('#publication-message').then(value=>/no supported extension|unsupported/i.test(value||'')),'Neutral evidence refusal missing');
  const writes=requests.filter(r=>r.url.endsWith('/recover-publication'));assert.equal(writes.length,2);assert.equal(JSON.parse(writes[0].body).request_key,JSON.parse(writes[1].body).request_key);
  assert.ok(requests.some(r=>r.url.endsWith('/publication')&&r.headers['Tuldok-Operation-Contract']?.startsWith('runs.publication_status/2/')));
  assert.ok(requests.filter(r=>/publication-results|\/publication$|recover-publication|cancel-publication/.test(r.url)).every(r=>r.headers['Tuldok-Operation-Contract']),'Every publication request is explicitly selected');
  assert.ok(!requests.some(r=>r.url.includes('/retry')||r.url.includes('/submit-external')||r.url.includes('select-candidate')));
  assert.deepEqual(errors,[]);
  for(const width of [1440,390]){await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});await evaluate('document.getElementById("publication-panel").scrollIntoView({block:"start"})');await pause(80);assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'Viewport overflow');fs.writeFileSync(path.join(report,'publication-'+width+'.jpg'),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));}
  checks.push('Real neutral custody fault retains original interrupted Run','Keyboard owner recovery and mouse pause reach real cancellation boundary','Fresh document reload retains exact request and resumes to published attempt2','Exact result inspection and segmented whole-hash browser download','Neutral field evidence remains unsupported','All publication operations pinned; no compute retry/promotion/submission','1440px and390px panel without horizontal overflow');
  fixture.stdin.end('finish\n');await until(()=>fixture.exitCode!==null,'Fixture cleanup did not finish');assert.equal(fixture.exitCode,0,stderr);
  const domain=JSON.parse(fs.readFileSync(path.join(report,'domain-receipt.json'),'utf8'));assert.equal(domain.input_sha256,measured);assert.equal(domain.original_run_state,'interrupted');assert.equal(domain.attempt_count,2);
  fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify({source_head:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),scope:'Neutral publication UI and custody; no scientific/training claim',checks,browser:(await send('Browser.getVersion')).product,download_sha256:measured,run_id:info.run_id},null,2)+'\n');
  console.log('PASS publication browser:',report);
})().catch(async error=>{console.error(error);console.error('Fixture stderr:',stderr);if(evaluate)try{console.error(await evaluate('document.body.innerText.slice(-9000)'));}catch{}process.exitCode=1;}).finally(async()=>{ws?.close();await stopOwnedChildren([...children].reverse());fs.rmSync(temp,{recursive:true,force:true,maxRetries:5,retryDelay:100});});
