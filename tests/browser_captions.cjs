'use strict';
const fixtureAuth = require('./auth_helpers.cjs').authenticatedFixture();
const fetch = fixtureAuth.fetch;
// Native browser smoke test. No npm dependencies.
const {qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn,execFileSync}=require('node:child_process');
const {cdpSession}=require('./browser_cdp_session.cjs');
const {stopOwnedChildren}=require('./browser_owned_cleanup.cjs');
const {waitForDebugger}=require('./browser_startup.cjs');
const {pageLoadTracker}=require('./browser_page_load.cjs');
const loads=pageLoadTracker();
const root=path.resolve(__dirname,'..'),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-caption-browser-')),children=[];
const report=qaDirectory(root,'image-caption-exports');
const sourceHashes=Object.fromEntries(['tests/browser_captions.cjs','tests/browser_cdp_session.cjs','tests/test_browser_cdp_session.cjs','tests/browser_owned_cleanup.cjs','static/workbench.js'].map(file=>[file,require('node:crypto').createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex')]));
let ws, session, inspect;
const dialogChecks=[];
const errors=[];
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn){const deadline=performance.now()+15000;while(performance.now()<deadline){const value=await fn();if(value)return value;await pause(100);}throw Error('Timed out');}
function launch(command,args,options={}){const child=spawn(command,args,options);children.push(child);return child;}
(async()=>{
  await require('./test_browser_cdp_session.cjs').verifyCDPSession();
  const server=launch('python3',['-u','tests/browser_server.py','--port','0','--data',path.join(temporary,'data')],{cwd:root,stdio:['ignore','pipe','pipe']});
  let output='',stderr='';server.stdout.on('data',data=>output+=data);server.stderr.on('data',data=>stderr+=data);
  const port=await until(()=>output.match(/127\.0\.0\.1:(\d+)/)?.[1]);
  await fixtureAuth.register('http://127.0.0.1:'+port,path.join(temporary,'data'),root);
  const browser=launch(process.env.BROWSER||'/usr/bin/chromium',['--headless','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--window-size=1400,950','--user-data-dir='+path.join(temporary,'browser'),'about:blank'],{stdio:['ignore','ignore','inherit'],env:{...process.env,XDG_CONFIG_HOME:temporary,XDG_CACHE_HOME:temporary}});
  const active=path.join(temporary,'browser','DevToolsActivePort');
  const debugPort=await waitForDebugger(browser,active);
  const tabs=await(await fetch('http://127.0.0.1:'+debugPort+'/json',{signal:AbortSignal.timeout(10000)})).json();
  const target=tabs.find(tab=>tab.type==='page' && tab.url==='about:blank');
  assert.ok(target,'Expected the explicitly launched blank page target');
  ws=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{
    const timer=setTimeout(()=>reject(Error('CDP connection timed out')),10000);
    ws.onopen=()=>{clearTimeout(timer);resolve();};ws.onerror=()=>{clearTimeout(timer);reject(Error('CDP connection failed'));};
  });
  session=cdpSession(ws,{onEvent:message=>{loads.observe(message);if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails);}});
  const {send}=session;
  const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  inspect=()=>send('Runtime.evaluate',{expression:'JSON.stringify({url:location.href,ready:document.readyState,notice:document.getElementById("notice")?.textContent,body:document.body?.innerText.slice(0,1500),viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,overflow:[...document.querySelectorAll("body *")].filter(e=>e.getBoundingClientRect().right>innerWidth || e.scrollWidth>e.clientWidth+1).map(e=>({tag:e.tagName,id:e.id,class:e.className,right:e.getBoundingClientRect().right,width:e.getBoundingClientRect().width})).slice(0,30)})',awaitPromise:true,returnByValue:true},1000).then(value=>value.result?.value);
  const click=id=>evaluate('document.getElementById('+JSON.stringify(id)+').click()');
  const fill=(id,value)=>evaluate('(()=>{const e=document.getElementById('+JSON.stringify(id)+');e.value='+JSON.stringify(value)+';e.dispatchEvent(new Event("input",{bubbles:true}));e.dispatchEvent(new Event("change",{bubbles:true}));})()');
  await send('Page.enable');await send('Page.setLifecycleEventsEnabled',{enabled:true});await send('Runtime.enable');
  await fixtureAuth.browser(send,'http://127.0.0.1:'+port);
  const initial=(await send('Page.getFrameTree')).frameTree.frame;
  assert.ok(initial.loaderId,'Initial navigation needs the blank document loader identity');
  const navigation=await send('Page.navigate',{url:'http://127.0.0.1:'+port+'/workbench'});
  assert.ok(!navigation.errorText,navigation.errorText);
  // Navigation acknowledgement precedes document replacement; read only the loaded new document.
  await until(()=>loads.reloaded(initial));
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
  const previous=(await send('Page.getFrameTree')).frameTree.frame;
  assert.ok(previous.loaderId,'The reopen check needs the old document loader identity');
  await send('Page.reload');await until(()=>loads.reloaded(previous));
  await until(()=>evaluate('document.getElementById("notice")?.textContent === "Collection ready."'));
  await openName(names[0]);
  assert.equal(await evaluate('document.getElementById("task").value'),'image_caption');
  assert.equal(await evaluate('document.getElementById("caption").value'),'A dark canvas in a procedural rectangle test scene.');
  // Unsaved caption changes survive cancellation of a navigation prompt.
  await fill('caption','Keep this unsaved caption');
  const discardMessage='Discard unsaved annotation, rights-note, response or judgment edits?';
  const answerDiscard=async accept=>{
    const event=await session.withDialog(()=>click('reload'),{accept,message:discardMessage});
    dialogChecks.push({type:event.type,message:event.message,accept});
  };
  await answerDiscard(false);
  assert.equal(await evaluate('document.getElementById("caption").value'),'Keep this unsaved caption');
  await answerDiscard(true);
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
  await answerDiscard(true);
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
  execFileSync('python3',['-c',`import json,zipfile;z=zipfile.ZipFile(${JSON.stringify(zipPath)});m=json.loads(z.read('manifest.json'));assert m['format']=='image_caption_v1';assert len(m['records'])==4;assert len(m['warnings'])==4;assert all(w.startswith('Small image:') for w in m['warnings']);assert set(m['split_mapping'].values())=={'train','val','test'};[(lambda rows: (len(rows)>0 or (_ for _ in ()).throw(AssertionError('Empty split'))))([json.loads(x) for x in z.read(s+'/metadata.jsonl').splitlines()]) for s in ('train','val','test')]`]);
  assert.ok((await evaluate('document.getElementById("notice").textContent')).includes('4 export warnings; inspect manifest.json.'));
  const desktop=await send('Page.captureScreenshot',screenshotOptions);
  fs.writeFileSync(path.join(report,'captions-desktop.jpg'),Buffer.from(desktop.data,'base64'));
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
  const shot=await send('Page.captureScreenshot',screenshotOptions);
  fs.writeFileSync(path.join(report,'captions-narrow.jpg'),Buffer.from(shot.data,'base64'));
  assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'), 'Narrow caption layout must not overflow');
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify({status:'passed',command:'node tests/browser_captions.cjs',source_commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),source_sha256:sourceHashes,browser:(await send('Browser.getVersion')).product,catalog_id:JSON.parse(fs.readFileSync(path.join(temporary,'data','.tuldok.json'),'utf8')).dataset_id,dialog_checks:dialogChecks,exported_records:4,zip_sha256:require('node:crypto').createHash('sha256').update(fs.readFileSync(zipPath)).digest('hex'),checks:['cancel preserves unsaved caption','discard restores saved caption','keyboard edit resets review; discard restores human review','draft exclusion and exact caption ZIP','reopen, filters, repeated submit and390px layout'],scope:'Actual app/PostgreSQL/Chromium caption journey with existing controlled generation provider; no model-quality claim'},null,2)+'\n');
  console.log('Caption Chromium edit/draft/review/reopen/filter/export, keyboard review reset, discard, repeated-submit and narrow layout passed.',report);
})().catch(async error=>{
  console.error(error);console.error('Runtime errors:',JSON.stringify(errors));
  if(session?.hasDialog())console.error('Page diagnostics skipped: JavaScript dialog is open.');
  else if(inspect)try{console.error('Page diagnostics:',await inspect());}catch(diagnostic){console.error('Diagnostics failed:',diagnostic);}
  process.exitCode=1;
}).finally(async()=>{
  if(session)session.close();else if(ws)ws.close();
  await stopOwnedChildren(children);
  fs.rmSync(temporary,{recursive:true,force:true,maxRetries:10,retryDelay:100});
  fs.writeFileSync(path.join(report,'cleanup.json'),JSON.stringify({temporary,removed:!fs.existsSync(temporary),children:children.map(child=>({pid:child.pid,exit_code:child.exitCode,signal:child.signalCode})),scope:'Only test-owned child handles; all exited before temporary removal'},null,2)+'\n');
}).catch(error=>{console.error('Owned caption fixture cleanup failed:',error);process.exitCode=1;});
