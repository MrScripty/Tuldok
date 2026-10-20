'use strict';
// Actual neutral owner phase observation, preparation/queue/cancel/publication lifecycle.
// No model training or scientific acceptance is exercised.
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn,execFileSync}=require('node:child_process');
const {authenticatedFixture}=require('./auth_helpers.cjs'),{waitForDebugger}=require('./browser_startup.cjs');
const {pageLoadTracker}=require('./browser_page_load.cjs');
const {stopOwnedChildren}=require('./browser_owned_cleanup.cjs');
const tracker=pageLoadTracker();
const {qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const root=path.resolve(__dirname,'..'),report=qaDirectory(root,'run-phase-timings'),temp=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-phase-browser-'));
const auth=authenticatedFixture(),children=[],errors=[],requests=[],checks=[];
let ws,evaluate,send,stderr='';const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn,label){for(let i=0;i<750;i++){const value=await fn();if(value)return value;await pause(100);}throw Error(label||'Timed out');}
function launch(command,args,options={}){const child=spawn(command,args,{cwd:root,...options});children.push(child);return child;}
(async()=>{
  const fixture=launch(process.env.PYTHON||'python3',['-u','tests/phase_timing_browser_fixture.py',path.join(report,'domain-receipt.json')],{env:{...process.env,PYTHONPATH:'.:tests',PYTHONDONTWRITEBYTECODE:'1'},stdio:['pipe','pipe','pipe']});
  let output='';fixture.stdout.on('data',chunk=>output+=chunk);fixture.stderr.on('data',chunk=>stderr+=chunk);
  const info=await until(()=>{if(fixture.exitCode!==null)throw Error('Fixture exited '+stderr);try{return JSON.parse(output.split('\n')[0]);}catch{return null;}},'Neutral phase fixture unavailable');
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
  async function command(name){fixture.stdin.write(JSON.stringify({command:name})+'\n');return until(()=>{for(const line of output.trim().split('\n').slice(1)){try{const value=JSON.parse(line);if(value.command===name)return value;}catch{}}return null;},'Fixture command '+name);}
  const phaseText=()=>text('#real-phase-root');
  await send('Page.navigate',{url:base+'/workspaces#pipeline'});
  await until(()=>evaluate('!!document.getElementById("dataset") && !document.getElementById("dataset").disabled && typeof document.getElementById("dataset").onchange==="function"'));
  await evaluate('(()=>{const select=document.getElementById("dataset");select.value="catalog";select.dispatchEvent(new Event("change",{bubbles:true}));})()');
  await until(()=>evaluate('!!document.getElementById("external-preflight") && !document.getElementById("external-preflight").disabled'));
  await activate('#external-preflight',true);
  await until(()=>text('#preparation-phase-root').then(value=>value?.includes('preparing material')&&value.includes('open')),'Live preparation-before-Run evidence missing');
  assert.match(await text('#preparation-phase-root'),/another tab can replace/);
  await command('release-preparation');
  await until(()=>evaluate('!!document.querySelector("#external-material code")'),'Real preflight did not complete');
  const queued=await command('queue');
  await evaluate('location.hash="#runs"');
  await until(()=>text('#real-run-state').then(value=>value==='queued'));
  await until(()=>phaseText().then(value=>value?.includes('capacity')),'Actual queue-capacity wait missing');
  await evaluate('document.querySelector("#phase-run-refresh").focus()');
  await pause(2300);assert.equal(await evaluate('document.activeElement.id'),'phase-run-refresh','Timing refresh must retain keyboard focus');
  await evaluate('(()=>{const region=document.querySelector("#real-phase-root .phase-timing-table");region.scrollLeft=50;window.phaseRegion={id:region.id,left:region.scrollLeft};})()');
  await pause(2300);assert.equal(await evaluate('document.getElementById(window.phaseRegion.id).scrollLeft'),await evaluate('window.phaseRegion.left'),'Live refresh must retain table scroll');
  await command('lock-wait');
  await activate('#real-phase-root [data-phase-refresh]');
  await until(()=>phaseText().then(value=>value?.includes('catalog lock wait')),'Actual catalog lock span missing');
  await command('allow');
  await until(()=>phaseText().then(value=>value?.includes('leader lifetime')&&value.includes('open')),'Live custodian leader observation missing');
  await activate('#real-cancel',true);
  await until(()=>text('#real-run-state').then(value=>value==='cancelled'));
  await activate('#real-phase-root [data-phase-refresh]');
  await until(()=>phaseText().then(value=>value?.includes('drain')&&value.includes('measured')),'Final cancellation/drain observations missing');
  const second=await command('publication');
  await activate('#real-runs-refresh');
  await until(()=>evaluate(`!!document.querySelector('[data-real-run="${second.run_id}"]')`));
  await activate(`[data-real-run="${second.run_id}"]`);
  await until(()=>text('#real-run-state').then(value=>['failed','interrupted'].includes(value)),'Original copy failure missing');
  await until(()=>phaseText().then(value=>value?.includes('publication')&&value.includes('incomplete')),'Failed publication observed prefix missing');
  await command('copy');
  await until(()=>evaluate('!!document.querySelector("#publication-recover")'));
  await activate('#publication-recover',true);
  await until(()=>text('#publication-panel').then(value=>value?.includes('published')),'Same-attempt publication continuation did not finish');
  await activate('#real-phase-root [data-phase-refresh]');
  await until(()=>phaseText().then(value=>value?.includes('recovery publication')&&value.includes('measured')),'Recovery copy observations missing');
  assert.match(await phaseText(),/Different owner clocks cannot be subtracted or added/);
  assert.ok(['failed','interrupted'].includes(await text('#real-run-state')));
  for(const width of [1440,390]){await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});await evaluate('document.querySelector("#real-phase-root").scrollIntoView({block:"start"})');await pause(80);assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'Viewport overflow');fs.writeFileSync(path.join(report,'phases-'+width+'.jpg'),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));}
  const timingRequests=()=>requests.filter(request=>/\/(phase-timings|preparation-timings)$/.test(request.url));
  assert.ok(timingRequests().length>3);assert.ok(timingRequests().every(request=>request.headers['Tuldok-Operation-Contract']?.startsWith(request.url.endsWith('/preparation-timings')?'graphs.preparation_timings/1/':'runs.phase_timings/1/')));
  await evaluate('location.hash="#data"');await pause(100);const stopped=timingRequests().length;await pause(2300);assert.equal(timingRequests().length,stopped,'Navigation must stop timing polling');
  assert.deepEqual(errors,[]);
  fixture.stdin.end(JSON.stringify({command:'finish'})+'\n');await until(()=>fixture.exitCode!==null,'Owned phase fixture cleanup did not finish');assert.equal(fixture.exitCode,0,stderr);
  const domain=JSON.parse(fs.readFileSync(path.join(report,'domain-receipt.json'),'utf8'));assert.equal(domain.go_sends,2);assert.equal(domain.counts.workspace_runs,2);assert.equal(domain.counts.access_execution_consumptions,2);
  checks.push('Live real preparation before any Run, explicitly latest actor/revision observation','Actual capacity wait and separate-thread catalog mutex observation','First neutral GO, live custodian phases, explicit UI cancellation and drainage','Second neutral original publication fault, incomplete interval and same-attempt recovery intervals','Original Run failure retained, two admissions/two GO/two consumptions','Exact selected timing operations,1440/390 layout and navigation polling cleanup');
  fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify({source_head:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),scope:'Actual neutral phase lifecycle UI; no model training/CUDA/science',checks,browser:(await send('Browser.getVersion')).product,first_run:queued.run_id,second_run:second.run_id,timing_requests:timingRequests().length},null,2)+'\n');
  console.log('PASS phase timing browser:',report);
})().catch(async error=>{console.error(error);console.error('Fixture stderr:',stderr);if(evaluate)try{console.error(await evaluate('document.body.innerText.slice(-9000)'));}catch{}process.exitCode=1;}).finally(async()=>{ws?.close();await stopOwnedChildren([...children].reverse());fs.rmSync(temp,{recursive:true,force:true,maxRetries:5,retryDelay:100});});
