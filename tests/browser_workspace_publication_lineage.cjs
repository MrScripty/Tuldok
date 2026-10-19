'use strict';
// Real neutral Study/Trial/custody fault and publication links in existing lineage.
// No model training or scientific acceptance is exercised.
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn,execFileSync}=require('node:child_process');
const {authenticatedFixture}=require('./auth_helpers.cjs'),{waitForDebugger}=require('./browser_startup.cjs');
const {pageLoadTracker}=require('./browser_page_load.cjs');
const tracker=pageLoadTracker();
const {qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const root=path.resolve(__dirname,'..'),report=qaDirectory(root,'workspace-publication-lineage'),temp=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-publication-lineage-browser-'));
const auth=authenticatedFixture(),children=[],errors=[],requests=[],checks=[];
let ws,evaluate,send,stderr='';const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn,label){for(let i=0;i<750;i++){const value=await fn();if(value)return value;await pause(100);}throw Error(label||'Timed out');}
function launch(command,args,options={}){const child=spawn(command,args,{cwd:root,...options});children.push(child);return child;}
(async()=>{
  const fixture=launch(process.env.PYTHON||'python3',['-u','tests/publication_lineage_browser_fixture.py',path.join(report,'domain-receipt.json')],{env:{...process.env,PYTHONPATH:'.:tests',PYTHONDONTWRITEBYTECODE:'1'},stdio:['pipe','pipe','pipe']});
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
  await send('Page.navigate',{url:base+'/workspaces#pipeline'});
  await until(()=>evaluate('!!document.getElementById("dataset") && !document.getElementById("dataset").disabled'));
  await evaluate('(()=>{const select=document.getElementById("dataset");select.value="catalog";select.dispatchEvent(new Event("change",{bubbles:true}));})()');
  await until(()=>evaluate(`!!document.querySelector('[data-lineage-node="${info.trial_id}"]')`),'Actual Study Trial missing from lineage');
  await activate('[data-lineage-node="'+info.trial_id+'"]',true);
  assert.ok(!requests.some(request=>request.url.endsWith('/publication')),'Lineage never fans out publication status automatically');
  await activate('[data-lineage-publication="'+info.run_id+'"]',true);
  await until(()=>text('.lineage-publication').then(value=>value?.includes('requires_verification')),'Saved eligible metadata missing');
  assert.match(await text('.lineage-publication'),/Original Run: interrupted/);
  assert.match(await text('.lineage-publication'),/publication: not recorded/);
  assert.equal(await evaluate('!!document.querySelector("#lineage-detail #publication-recover")'),false);
  await activate('[data-lineage-run="'+info.run_id+'"]');
  await until(()=>evaluate('!!document.getElementById("publication-recover")'),'Original Run recovery controls unavailable');
  assert.equal(await text('#real-run-state'),'interrupted');
  await activate('#publication-recover',true);
  await until(()=>text('#publication-attempt-status').then(value=>value?.includes('published')),'Original Run publication failed');
  const ref=JSON.parse(await text('#publication-result-ref pre'));
  await activate('#nav-pipeline');
  await until(()=>evaluate(`!!document.querySelector('[data-lineage-node="${info.trial_id}"]')`));
  await activate('[data-lineage-node="'+info.trial_id+'"]');
  assert.ok(!(await text('#lineage-detail')).includes('Exact recovered publication Ref'),'Prior publication metadata must be cleared after navigation');
  await activate('[data-lineage-publication="'+info.run_id+'"]');
  await until(()=>text('.lineage-publication').then(value=>value?.includes('Exact recovered publication Ref')),'Fresh published Ref missing from lineage');
  assert.match(await text('.lineage-publication'),/Original Run: interrupted/);
  assert.match(await text('.lineage-publication'),/publication: published/);
  assert.deepEqual(JSON.parse(await text('.lineage-publication details pre')),ref);
  for(const width of [1440,390]){await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});await evaluate('document.querySelector(".lineage-attempt").scrollIntoView({block:"start"})');await pause(80);assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'Viewport overflow');fs.writeFileSync(path.join(report,'publication-lineage-'+width+'.jpg'),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));}
  await activate('[data-lineage-publication-run="'+info.run_id+'"]',true);
  await until(()=>text('#publication-attempt-status').then(value=>value?.includes('published')),'Exact Ref link did not reopen original Run');
  assert.deepEqual(JSON.parse(await text('#publication-result-ref pre')),ref);
  assert.equal(await text('#real-run-state'),'interrupted');
  await activate('#publication-inspect',true);
  await until(()=>evaluate('!!document.getElementById("publication-inspected")'),'Linked exact result did not verify');
  assert.equal(requests.filter(request=>request.url.endsWith('/recover-publication')).length,1);
  assert.ok(requests.filter(request=>request.url.endsWith('/publication')).every(request=>request.headers['Tuldok-Operation-Contract']?.startsWith('runs.publication_status/2/')));
  assert.ok(!requests.some(request=>request.url.includes('/retry')||request.url.includes('/submit-external')||request.url.includes('select-candidate')||request.url.includes('/branch')));
  assert.deepEqual(errors,[]);
  checks.push('Real neutral Model/Study/Trial/admission and custody publication fault',
    'Explicit pinned lineage metadata inspection with no status fanout or recovery control',
    'Original interrupted outcome preserved beside separate published state and exact Ref',
    'Navigation drops old metadata; explicit refresh observes attached publication',
    'Keyboard exact Ref link reopens original Run and its real byte verifier',
    '1440px/390px existing lineage detail without horizontal overflow');
  fixture.stdin.end('finish\n');await until(()=>fixture.exitCode!==null,'Fixture cleanup did not finish');assert.equal(fixture.exitCode,0,stderr);
  const domain=JSON.parse(fs.readFileSync(path.join(report,'domain-receipt.json'),'utf8'));assert.deepEqual(domain.result_ref,ref);assert.equal(domain.original_run_state,'interrupted');assert.equal(domain.reservation_unchanged,true);assert.equal(domain.lineage_projection_unchanged,true);
  fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify({source_head:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),scope:'Real neutral Study/Trial/custody publication lineage; no scientific/training claim',checks,browser:(await send('Browser.getVersion')).product,result_ref:ref,trial_id:info.trial_id,run_id:info.run_id},null,2)+'\n');
  console.log('PASS publication lineage browser:',report);
})().catch(async error=>{console.error(error);console.error('Fixture stderr:',stderr);if(evaluate)try{console.error(await evaluate('document.body.innerText.slice(-9000)'));}catch{}process.exitCode=1;}).finally(()=>{ws?.close();for(const child of children.reverse())if(child.exitCode===null)child.kill('SIGTERM');fs.rmSync(temp,{recursive:true,force:true});});
