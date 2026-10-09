// Native browser smoke test. No npm dependencies.
const {qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process');
const root=path.resolve(__dirname,'..'),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-caption-browser-')),children=[];
let ws, inspect;
const errors=[];
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn){for(let i=0;i<150;i++){const value=await fn();if(value)return value;await pause(100);}throw Error('Timed out');}
function launch(command,args,options={}){const child=spawn(command,args,options);children.push(child);return child;}
(async()=>{
  fs.mkdirSync(qaDirectory(root,'image-caption-exports'),{recursive:true});
  const server=launch('python3',['-u','tests/browser_server.py','--port','0','--data',path.join(temporary,'data')],{cwd:root,stdio:['ignore','pipe','pipe']});
  let output='',stderr='';server.stdout.on('data',data=>output+=data);server.stderr.on('data',data=>stderr+=data);
  const port=await until(()=>output.match(/127\.0\.0\.1:(\d+)/)?.[1]);
  launch(process.env.BROWSER||'/usr/bin/chromium',['--headless','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--window-size=1400,950','--user-data-dir='+path.join(temporary,'browser'),'about:blank'],{stdio:['ignore','ignore','inherit'],env:{...process.env,HOME:temporary,XDG_CONFIG_HOME:temporary,XDG_CACHE_HOME:temporary}});
  const active=path.join(temporary,'browser','DevToolsActivePort');
  const debugPort=await until(()=>fs.existsSync(active)&&fs.readFileSync(active,'utf8').split('\n')[0]);
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
  await fill('count',5);await evaluate('document.getElementById("generate-form").requestSubmit()');
  await until(()=>evaluate('document.getElementById("notice").textContent.includes("5 candidates created")'));
  const names=await evaluate('[...document.querySelectorAll(".record button")].map(button=>button.childNodes[0].textContent)');
  assert.equal(names.length,5);
  const openName=async name=>{await evaluate('(()=>{const name='+JSON.stringify(name)+';[...document.querySelectorAll(".record button")].find(button=>button.childNodes[0].textContent===name).click();})()');await until(()=>evaluate('document.getElementById("record-name").textContent==='+JSON.stringify(name)));};
  await openName(names[0]);
  await fill('task','image_caption');
  assert.equal(await evaluate('document.getElementById("caption").value'),'','An old detection target or generation prompt must not become a caption');
  await fill('caption','A dark canvas in a procedural rectangle test scene.');
  await evaluate('document.getElementById("editor").requestSubmit()');
  await until(()=>evaluate('!document.getElementById("editor").dataset.busy && document.getElementById("notice").textContent === "Annotation saved."'));
  assert.equal(await evaluate('document.getElementById("record-review").value'),'draft');
  await click('history');await until(()=>evaluate('!document.getElementById("history-output").hidden'));
  assert.ok((await evaluate('document.getElementById("history-output").textContent')).includes('image_caption'));
  await send('Page.reload');await until(()=>evaluate('document.getElementById("notice")?.textContent === "Collection ready."'));
  await openName(names[0]);
  assert.equal(await evaluate('document.getElementById("task").value'),'image_caption');
  assert.equal(await evaluate('document.getElementById("caption").value'),'A dark canvas in a procedural rectangle test scene.');
  // Unsaved caption changes survive cancellation of a navigation prompt.
  await fill('caption','Keep this unsaved caption');
  const blockedNavigation=click('reload');
  await pause(100);await send('Page.handleJavaScriptDialog',{accept:false});await blockedNavigation;
  assert.equal(await evaluate('document.getElementById("caption").value'),'Keep this unsaved caption');
  const reload=click('reload');await pause(100);await send('Page.handleJavaScriptDialog',{accept:true});await reload;
  await until(()=>evaluate('document.getElementById("caption").value==="A dark canvas in a procedural rectangle test scene."'));
  await fill('record-review','human_reviewed');
  await evaluate('document.getElementById("editor").requestSubmit();document.getElementById("editor").requestSubmit();');
  await until(()=>evaluate('!document.getElementById("editor").dataset.busy && document.getElementById("notice").textContent === "Annotation saved."'));
  for(const name of names.slice(1,4)) {
    await openName(name);await fill('task','image_caption');await fill('caption','A dark canvas in a procedural rectangle test scene.');
    await fill('record-review','human_reviewed');await evaluate('document.getElementById("editor").requestSubmit()');
    await until(()=>evaluate('!document.getElementById("editor").dataset.busy && document.getElementById("notice").textContent === "Annotation saved."'));
  }
  // Actual keyboard entry is enough to revoke old review evidence before saving.
  await evaluate('document.getElementById("caption").focus();document.getElementById("caption").setSelectionRange(0,0)');
  await send('Input.insertText',{text:'A test view. '});
  assert.equal(await evaluate('document.getElementById("record-review").value'),'draft');
  const discard=click('reload');await pause(100);await send('Page.handleJavaScriptDialog',{accept:true});await discard;
  await until(()=>evaluate('document.getElementById("record-review").value==="human_reviewed"'));
  // A matching draft caption is visible before review filtering and must be excluded afterward.
  await openName(names[4]);await fill('task','image_caption');await fill('caption','A dark canvas in a procedural rectangle test scene.');
  await evaluate('document.getElementById("editor").requestSubmit()');
  await until(()=>evaluate('!document.getElementById("editor").dataset.busy && document.getElementById("notice").textContent === "Annotation saved."'));
  assert.equal(await evaluate('document.querySelectorAll(".record").length'),5);
  await fill('task-filter','image_caption');await fill('review-filter','human_reviewed');await fill('query','rectangle test scene');
  await evaluate('document.getElementById("filters").requestSubmit()');await until(()=>evaluate('!document.getElementById("filters").dataset.busy && document.querySelectorAll(".record").length===4'));
  await click('select-page');await until(()=>evaluate('document.getElementById("selection").textContent === "4 selected"'));
  await fill('release-format','image_caption_v1');
  await click('preview-release');await until(()=>evaluate('!document.getElementById("freeze-release").disabled'));
  await evaluate('document.getElementById("release-form").requestSubmit()');
  await until(()=>evaluate('!!document.querySelector("#release-result a")'));
  const release=await evaluate('document.querySelector("#release-result a").href');
  const archive=await fetch(release);assert.equal(archive.status,200);
  const zipPath=path.join(temporary,'captions.zip');fs.writeFileSync(zipPath,Buffer.from(await archive.arrayBuffer()));
  const {execFileSync}=require('node:child_process');
  execFileSync('python3',['-c',`import json,zipfile;z=zipfile.ZipFile(${JSON.stringify(zipPath)});m=json.loads(z.read('manifest.json'));assert m['format']=='image_caption_v1';assert len(m['records'])==4;assert set(m['split_mapping'].values())=={'train','val','test'};[(lambda rows: (len(rows)>0 or (_ for _ in ()).throw(AssertionError('Empty split'))))([json.loads(x) for x in z.read(s+'/metadata.jsonl').splitlines()]) for s in ('train','val','test')]`]);
  assert.ok((await evaluate('document.getElementById("notice").textContent')).includes('small-image warnings'));
  const desktop=await send('Page.captureScreenshot',screenshotOptions);
  fs.writeFileSync(path.join(qaDirectory(root,'image-caption-exports'),'captions-desktop.jpg'),Buffer.from(desktop.data,'base64'));
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
  const shot=await send('Page.captureScreenshot',screenshotOptions);
  fs.writeFileSync(path.join(qaDirectory(root,'image-caption-exports'),'captions-narrow.jpg'),Buffer.from(shot.data,'base64'));
  assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'), 'Narrow caption layout must not overflow');
  assert.deepEqual(errors,[]);console.log('Caption Chromium edit/draft/review/reopen/filter/export, keyboard review reset, discard, repeated-submit and narrow layout passed.');
})().catch(async error=>{console.error(error);console.error('Runtime errors:',JSON.stringify(errors));if(inspect)try{console.error('Page diagnostics:',await inspect());}catch(diagnostic){console.error('Diagnostics failed:',diagnostic);}process.exitCode=1;}).finally(async()=>{if(ws)ws.close();for(const child of children)child.kill();await pause(200);fs.rmSync(temporary,{recursive:true,force:true});});
