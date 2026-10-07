// Native browser smoke test. No npm dependencies.
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process');
const {STARTUP_BUDGET_MS,waitForDebugger}=require('./browser_startup.cjs');
const root=path.resolve(__dirname,'..'),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-test-')),children=[];
let ws, inspect;
const errors=[];
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn){for(let i=0;i<150;i++){const value=await fn();if(value)return value;await pause(100);}throw Error('Timed out');}
function launch(command,args,options={}){const child=spawn(command,args,options);children.push(child);return child;}
(async()=>{
  const server=launch('python3',['-u','tests/browser_server.py','--port','0','--data',path.join(temporary,'data')],{cwd:root,stdio:['ignore','pipe','pipe']});
  let output='',stderr='';server.stdout.on('data',data=>output+=data);server.stderr.on('data',data=>stderr+=data);
  const port=await until(()=>output.match(/127\.0\.0\.1:(\d+)/)?.[1]);
  const browserCommand=process.env.BROWSER||'/usr/bin/chromium';
  const browser=launch(browserCommand,['--headless','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--window-size=1400,950','--user-data-dir='+path.join(temporary,'browser'),'about:blank'],{stdio:['ignore','pipe','pipe'],env:{...process.env,HOME:temporary,XDG_CONFIG_HOME:temporary,XDG_CACHE_HOME:temporary}});
  // Chrome wrappers can report startup failure on stdout. Retain bounded tails
  // and process state; only debugger startup gets the 60-second allowance.
  let browserStdout='',browserStderr='',browserSpawnError;
  browser.stdout.on('data',data=>browserStdout=(browserStdout+data).slice(-8192));
  browser.stderr.on('data',data=>{browserStderr=(browserStderr+data).slice(-8192);process.stderr.write(data);});
  browser.on('error',error=>browserSpawnError=error.message);
  const active=path.join(temporary,'browser','DevToolsActivePort');
  let debugPort;
  try{
    debugPort=await waitForDebugger(browser,active);
  }catch(error){
    console.error('Browser startup diagnostics:',JSON.stringify({command:browserCommand,pid:browser.pid,exitCode:browser.exitCode,signal:browser.signalCode,spawnError:browserSpawnError,startupBudgetMs:STARTUP_BUDGET_MS,activePortFile:active,activePortFileExists:fs.existsSync(active),stdout:browserStdout,stderr:browserStderr}));
    throw error;
  }
  const tabs=await(await fetch('http://127.0.0.1:'+debugPort+'/json')).json();
  const target=tabs.find(tab=>tab.type==='page' && tab.url==='about:blank');
  assert.ok(target,'Expected the explicitly launched blank page target');
  ws=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  let id=0;const pending=new Map();
  ws.onmessage=event=>{const message=JSON.parse(event.data);if(message.id){const task=pending.get(message.id);pending.delete(message.id);message.error?task.reject(message.error):task.resolve(message.result);}if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails);};
  const send=(method,params={})=>new Promise((resolve,reject)=>{pending.set(++id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
  const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  inspect=()=>evaluate('JSON.stringify({url:location.href,ready:document.readyState,notice:document.getElementById("notice")?.textContent,body:document.body?.innerText.slice(0,1500),viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,overflow:[...document.querySelectorAll("body *")].filter(e=>e.getBoundingClientRect().right>innerWidth || e.scrollWidth>e.clientWidth+1).map(e=>({tag:e.tagName,id:e.id,class:e.className,right:e.getBoundingClientRect().right,width:e.getBoundingClientRect().width})).slice(0,30)})');
  const click=id=>evaluate('document.getElementById('+JSON.stringify(id)+').click()');
  const fill=(id,value)=>evaluate('(()=>{const e=document.getElementById('+JSON.stringify(id)+');e.value='+JSON.stringify(value)+';e.dispatchEvent(new Event("input",{bubbles:true}));e.dispatchEvent(new Event("change",{bubbles:true}));})()');
  await send('Page.enable');await send('Runtime.enable');
  await send('Page.navigate',{url:'http://127.0.0.1:'+port+'/workbench'});
  await until(()=>evaluate('document.getElementById("notice")?.textContent === "Collection ready."'));
  await fill('import-name','Unicode note');await fill('import-group','doc-one');await fill('import-text','Hello 😀 café');
  await evaluate('document.getElementById("import-form").requestSubmit()');
  await until(()=>evaluate('document.getElementById("notice").textContent === "Record imported."'));
  await fill('task','text_entities');await fill('label','emoji');await fill('span-start',6);await fill('span-end',7);await click('add-offset-span');
  assert.equal(await evaluate('document.querySelectorAll("#targets li").length'),1);
  await fill('record-review','human_reviewed');await evaluate('document.getElementById("editor").requestSubmit()');
  await until(()=>evaluate('document.getElementById("notice").textContent === "Annotation saved."'));
  await click('history');await until(()=>evaluate('!document.getElementById("history-output").hidden'));
  assert.ok((await evaluate('document.getElementById("history-output").textContent')).includes('emoji'));
  // Conflicting remote revision must retain local edits and offer an explicit reload.
  await evaluate(`(async()=>{const page=await(await fetch('/api/workbench/records')).json();const r=page.items[0];await fetch('/api/workbench/records/'+r.id,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...r,annotation:{spans:[]},review:'human_reviewed'})});})()`);
  await evaluate('document.getElementById("editor").requestSubmit()');
  await until(()=>evaluate('document.getElementById("notice").textContent.includes("Reload before saving")'));
  assert.equal(await evaluate('document.querySelectorAll("#targets li").length'),1);
  await click('reload');await until(()=>evaluate('document.querySelectorAll("#targets li").length===0'));
  await fill('count',8);await evaluate('document.getElementById("generate-form").requestSubmit()');
  await until(()=>evaluate('document.getElementById("notice").textContent.includes("8 candidates created")'));
  await fill('query','rectangles');await evaluate('document.getElementById("filters").requestSubmit()');
  await until(()=>evaluate('document.querySelectorAll(".record").length===8'));
  await evaluate('document.querySelector(".record button").click()');
  await until(()=>evaluate('document.getElementById("asset-image").complete && document.getElementById("asset-image").naturalWidth===128'));
  await fill('box-x',1);await fill('box-y',2);await fill('box-width',12);await fill('box-height',14);await fill('label','manual-box');await click('add-box');
  assert.ok(await evaluate('document.querySelectorAll("#box-overlay rect").length>0'));
  await fill('record-review','human_reviewed');await evaluate('document.getElementById("editor").requestSubmit()');
  await until(()=>evaluate('document.getElementById("notice").textContent === "Annotation saved."'));
  await click('select-page');await until(()=>evaluate('document.getElementById("selection").textContent === "8 selected"'));
  await click('preview-release');await until(()=>evaluate('!document.getElementById("freeze-release").disabled'));
  await evaluate('document.getElementById("release-form").requestSubmit()');
  await until(()=>evaluate('!!document.querySelector("#release-result a")'));
  const release=await evaluate('document.querySelector("#release-result a").href');
  const archive=await fetch(release);assert.equal(archive.status,200);assert.equal((await archive.arrayBuffer()).byteLength>1000,true);
  const desktop=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
  fs.writeFileSync(path.join(root,'docs/plans/dataset-workflows/reports/workbench-desktop.png'),Buffer.from(desktop.data,'base64'));
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
  const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
  fs.writeFileSync(path.join(root,'docs/plans/dataset-workflows/reports/workbench-narrow.png'),Buffer.from(shot.data,'base64'));
  assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'), 'Narrow layout must not overflow');
  assert.deepEqual(errors,[]);console.log('Workbench Chromium lifecycle, stale conflicts, frozen download and narrow layout passed.');
})().catch(async error=>{console.error(error);console.error('Runtime errors:',JSON.stringify(errors));if(inspect)try{console.error('Page diagnostics:',await inspect());}catch(diagnostic){console.error('Diagnostics failed:',diagnostic);}process.exitCode=1;}).finally(async()=>{if(ws)ws.close();for(const child of children)child.kill();await pause(200);fs.rmSync(temporary,{recursive:true,force:true});});
