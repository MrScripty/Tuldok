// Real-browser layout interactions; supported server, synthetic sample data, JPEG85.
'use strict';
const fixtureAuth = require('./auth_helpers.cjs').authenticatedFixture();
const fetch = fixtureAuth.fetch;
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn,execFileSync}=require('node:child_process');
const {qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const {pageLoadTracker}=require('./browser_page_load.cjs');
const {waitForDebugger}=require('./browser_startup.cjs');
const root=path.resolve(process.env.TULDOK_SOURCE_ROOT||path.join(__dirname,'..')),report=qaDirectory(root,'workbench-layout'),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-layout-')),children=[];
const errors=[],tracker=pageLoadTracker(),pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));let ws;
async function until(fn){for(let i=0;i<150;i++){const result=await fn();if(result)return result;await pause(100);}throw Error('Timed out');}
function launch(command,args,options={}){const child=spawn(command,args,options);children.push(child);return child;}
(async()=>{
  const fixture=path.join(root,'tests/fixtures/meshes');
  const ply=fs.readFileSync(path.join(fixture,'tetrahedron.ply')),sidecar=fs.readFileSync(path.join(fixture,'tetrahedron.json'));
  const server=launch('python3',['-u','app.py','--port','0','--data',path.join(temporary,'data')],{cwd:root,stdio:['ignore','pipe','pipe']});
  let output='',serverErrors='';server.stdout.on('data',chunk=>output+=chunk);server.stderr.on('data',chunk=>serverErrors+=chunk);
  const port=await until(()=>output.match(/127\.0\.0\.1:(\d+)/)?.[1]),base='http://127.0.0.1:'+port;
  await fixtureAuth.register(base,path.join(temporary,'data'),root);
  const api=async(route,body)=>{const response=await fetch(base+'/api/workbench/'+route,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const result=await response.json();assert.ok(response.ok,JSON.stringify(result));return result;};

  const browser=launch(process.env.BROWSER||'/usr/bin/chromium',['--headless','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--window-size=1400,950','--user-data-dir='+path.join(temporary,'browser'),'about:blank'],{stdio:['ignore','ignore','ignore'],env:{...process.env,XDG_CONFIG_HOME:temporary,XDG_CACHE_HOME:temporary}});
  const debugPort=await waitForDebugger(browser,path.join(temporary,'browser','DevToolsActivePort'));
  const tabs=await(await fetch('http://127.0.0.1:'+debugPort+'/json')).json(),target=tabs.find(tab=>tab.type==='page'&&tab.url==='about:blank');
  assert.ok(target);ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  let id=0;const pending=new Map();
  const send=(method,params={})=>new Promise((resolve,reject)=>{const key=++id,timer=setTimeout(()=>{pending.delete(key);reject(Error('CDP timeout '+method));},20000);pending.set(key,{resolve:value=>{clearTimeout(timer);resolve(value);},reject:error=>{clearTimeout(timer);reject(error);}});ws.send(JSON.stringify({id:key,method,params}));});
  ws.onmessage=event=>{const message=JSON.parse(event.data);tracker.observe(message);if(message.id){const task=pending.get(message.id);if(!task)return;pending.delete(message.id);message.error?task.reject(message.error):task.resolve(message.result);}if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails);if(message.method==='Page.javascriptDialogOpening')send('Page.handleJavaScriptDialog',{accept:true}).catch(error=>errors.push(String(error)));};
  const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  const fill=(id,value)=>evaluate(`(()=>{const e=document.getElementById(${JSON.stringify(id)});e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  const choose=(id,name,raw)=>evaluate(`(()=>{const raw=Uint8Array.from(atob(${JSON.stringify(raw.toString('base64'))}),c=>c.charCodeAt(0)),dt=new DataTransfer();dt.items.add(new File([raw],${JSON.stringify(name)}));document.getElementById(${JSON.stringify(id)}).files=dt.files;})()`);
  await send('Page.enable');await send('Page.setLifecycleEventsEnabled',{enabled:true});await send('Runtime.enable');
  await fixtureAuth.browser(send,base);
  await send('Page.navigate',{url:base+'/workbench'});await until(()=>evaluate('document.getElementById("notice")?.textContent==="Collection ready."'));
  await send('Emulation.setDeviceMetricsOverride',{width:1600,height:1100,deviceScaleFactor:1,mobile:false});
  const click=async selector=>{
    const point=await evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});if(!e)throw Error('Missing control');e.scrollIntoView({block:'nearest'});const r=e.getBoundingClientRect();if(!r.width||!r.height)throw Error('Control is not visible');return {x:r.x+r.width/2,y:r.y+r.height/2};})()`);
    await send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...point});
    await send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...point});
  };
  const escape=async()=>{await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});};
  const shot=async name=>{await pause(150);fs.writeFileSync(path.join(report,name+'.jpg'),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));};
  assert.equal(await evaluate('document.querySelectorAll("[id]").length === new Set([...document.querySelectorAll("[id]")].map(e=>e.id)).size'),true,'Unique control IDs');
  // The served markup remains authoritative for every current modality and
  // native validation constraint; layout must preserve those actual controls.
  assert.deepEqual(await evaluate(`(async()=>{
    const raw=new DOMParser().parseFromString(await(await fetch('/workbench')).text(),'text/html'), failures=[];
    for(const original of raw.querySelectorAll('[id]')) {
      const live=document.getElementById(original.id);
      if(!live){failures.push('Missing '+original.id);continue;}
      for(const name of ['required','min','max','maxlength','pattern','accept','multiple','webkitdirectory'])
        if(original.getAttribute(name)!==live.getAttribute(name)) failures.push(original.id+': '+name);
    }
    for(const id of ['kind','task-filter','release-format']) {
      const options=node=>[...node.options].map(option=>[option.value,option.textContent]);
      if(JSON.stringify(options(raw.getElementById(id)))!==JSON.stringify(options(document.getElementById(id)))) failures.push(id+': options');
    }
    const scripts=doc=>[...doc.querySelectorAll('script[src]')].map(node=>node.getAttribute('src'));
    if(JSON.stringify(scripts(raw))!==JSON.stringify(scripts(document))) failures.push('controller scripts');
    return failures;
  })()`),[],'All current controls, validation, kinds/tasks/export formats and controller scripts retained');
  for(const id of ['audio-inspection','pointcloud-inspection','volume-inspection','scientific-inspection'])
    assert.equal(await evaluate(`document.getElementById(${JSON.stringify(id)}).parentElement.className`),'source-pane');
  assert.equal(await evaluate('document.getElementById("workspace-tools").open'),false);
  assert.ok(await evaluate('[...document.getElementById("kind").options].some(o=>o.value==="image")'),'Image filter remains available');
  await click('[data-workspace-panel="import"]');
  assert.equal(await evaluate('document.getElementById("workspace-tools").open'),true);
  assert.equal(await evaluate('document.getElementById("workspace-tools").getAttribute("aria-labelledby")'),'workspace-tools-title');
  // Keyboard traversal stays inside the native modal, then Escape restores the
  // toolbar trigger. No manually implemented focus trap replaces the browser.
  await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Tab',code:'Tab',windowsVirtualKeyCode:9,modifiers:8});
  await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Tab',code:'Tab',windowsVirtualKeyCode:9,modifiers:8});
  assert.ok(await evaluate('document.getElementById("workspace-tools").contains(document.activeElement)'),'Shift+Tab contained by native modal');
  await fill('import-name','SAMPLE · Layout workshop request');await fill('import-group','sample-layout');await fill('rights','Authored non-sensitive sample');
  await fill('import-text','SAMPLE DATA — authored for layout verification. Please schedule a dataset annotation workshop for next Tuesday.');
  // Closing never clears partially entered import forms.
  await escape();await until(()=>evaluate('!document.getElementById("workspace-tools").open'));
  assert.equal(await evaluate('document.activeElement.dataset.workspacePanel'),'import');
  await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,text:'\r'});
  await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
  assert.equal(await evaluate('document.getElementById("workspace-tools").open'),true,'Native Enter reopens the focused drawer trigger');
  assert.equal(await evaluate('document.getElementById("import-group").value'),'sample-layout');
  await click('#import-form button');await until(()=>evaluate('document.getElementById("notice").textContent==="Record imported."'));
  const imported=await evaluate('current.id');
  assert.equal(await evaluate('document.querySelector(".record button[aria-current=true]").dataset.recordId'),imported);
  assert.match(await evaluate('document.getElementById("record-state").textContent'),/Saved: draft · revision 1/);
  assert.equal(await evaluate('document.getElementById("workspace-tools-status").textContent'),'Record imported.');
  await click('#workspace-tools-close');await until(()=>evaluate('!document.getElementById("workspace-tools").open'));
  await fill('label','scheduling');
  // Tool panels can be revisited repeatedly without replacing draft/selection owners.
  await click('.record input');
  for(let repeat=0;repeat<2;repeat++)for(const panel of ['import','generate','export','collection']){
    await click('[data-workspace-panel="'+panel+'"]');
    assert.equal(await evaluate('document.querySelectorAll(".workspace-panel:not([hidden])").length'),1);
    assert.equal(await evaluate('document.activeElement.id'),'workspace-tools-close');
    await escape();await until(()=>evaluate('!document.getElementById("workspace-tools").open'));
    assert.equal(await evaluate('document.activeElement.dataset.workspacePanel'),panel);
    assert.equal(await evaluate('document.getElementById("label").value'),'scheduling');assert.equal(await evaluate('dirty'),true);assert.equal(await evaluate('selected.size'),1);
  }
  // Native validation opens the collapsed source controls without bypassing required groups.
  await fill('groups','');await click('#save');
  assert.equal(await evaluate('document.getElementById("record-evidence").open'),true);
  assert.equal(await evaluate('document.getElementById("groups").validity.valueMissing'),true);
  assert.equal((await api('records/'+imported)).revision,1);
  await fill('groups','sample-layout');await fill('record-review','human_reviewed');await click('#save');
  await until(()=>evaluate('document.getElementById("notice").textContent==="Annotation saved."'));
  assert.equal((await api('records/'+imported)).annotation.label,'scheduling');
  await click('#record-evidence > summary');
  await evaluate('document.querySelector("#advanced-filters > summary").focus()');
  await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,text:'\r'});
  await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
  assert.equal(await evaluate('document.getElementById("advanced-filters").open'),true,'Native keyboard disclosure exposes exact criteria');
  await fill('label-filter','scheduling');
  await evaluate('document.getElementById("label-filter").focus()');
  await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,text:'\r'});
  await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
  await until(()=>evaluate('document.getElementById("notice").textContent==="Collection updated."'));
  assert.equal(await evaluate('page.total'),1);assert.equal(await evaluate('selected.size'),1);
  await fill('label-filter','');await click('#filters > button');await until(()=>evaluate('!document.getElementById("filters").dataset.busy'));
  await click('#advanced-filters > summary');
  await shot('text-desktop');
  await click('[data-workspace-panel="export"]');await fill('train',100);await fill('validation',0);await fill('test',0);
  await click('#preview-release');await until(()=>evaluate('!document.getElementById("freeze-release").disabled'));
  await click('#freeze-release');await until(()=>evaluate('!!document.querySelector("#release-result a")'));
  const link=await evaluate('document.querySelector("#release-result a").href');assert.equal((await fetch(link)).status,200);
  await shot('export-desktop');await click('#workspace-tools-close');
  await click('[data-workspace-panel="generate"]');await fill('count',2);await click('#generate-form button');
  await until(()=>evaluate('document.getElementById("notice").textContent.includes("2 candidates created")'));
  await click('#workspace-tools-close');
  const image=(await api('records?kind=image')).items[0];
  await click('button[data-record-id="'+image.id+'"]');await until(()=>evaluate('document.getElementById("asset-image").complete && document.getElementById("asset-image").naturalWidth===128'));
  const sizes=await evaluate('({source:document.querySelector(".source-pane").getBoundingClientRect().width,collection:document.querySelector(".collection").getBoundingClientRect().width,image:document.getElementById("asset-image").getBoundingClientRect().width})');
  assert.ok(sizes.source>700&&sizes.image>600,'Canvas gets usable desktop width');assert.ok(sizes.collection<=310);
  // Display scaling retains correct original-image coordinate mapping.
  const box=await evaluate('(()=>{const r=document.getElementById("asset-image").getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height};})()');
  await send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,x:box.x+box.width/8,y:box.y+box.height/8});
  await send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,x:box.x+box.width/4,y:box.y+box.height/4});
  assert.ok(Math.abs(Number(await evaluate('document.getElementById("box-x").value'))-16)<=1);
  assert.ok(Math.abs(Number(await evaluate('document.getElementById("box-width").value'))-16)<=1);
  await fill('label','manual-sample');await click('#add-box');assert.ok(await evaluate('targets.some(t=>t.label==="manual-sample")'));
  await click('#save');await until(()=>evaluate('!dirty'));
  await shot('image-desktop');
  await click('[data-workspace-panel="import"]');await click('#mesh-import-panel > summary');
  await choose('mesh-ply','mesh.ply',ply);await choose('mesh-manifest','mesh.json',sidecar);await fill('mesh-name','SAMPLE · Analytic tetrahedron');await fill('mesh-group','sample-mesh');await fill('mesh-rights','Project-authored analytic fixture');
  await click('#mesh-import-form button');await until(()=>evaluate('document.getElementById("mesh-import-status").textContent.includes("4 vertices, 4 triangles")'));
  await click('#workspace-tools-close');const mesh=(await api('records?kind=mesh')).items[0];
  await click('button[data-record-id="'+mesh.id+'"]');await until(()=>evaluate('document.querySelectorAll("#mesh-projections polygon").length===12'));
  await shot('mesh-desktop');
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
  await evaluate('document.querySelector(".editor").scrollIntoView()');await shot('mesh-narrow');
  assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'),'No horizontal document overflow at 390px');
  await evaluate('scrollTo(0,0)');await click('[data-workspace-panel="import"]');
  assert.ok(await evaluate('document.getElementById("workspace-tools").scrollWidth<=innerWidth'),'Drawer fits narrow viewport');
  await shot('import-narrow');await escape();await until(()=>evaluate('!document.getElementById("workspace-tools").open'));
  await click('button[data-record-id="'+imported+'"]');await evaluate('document.querySelector(".editor").scrollIntoView()');await shot('text-narrow');
  assert.deepEqual(errors,[]);assert.ok(!serverErrors.includes('Traceback'),serverErrors);
  const sourceHashes={};
  for(const file of ['app.py','static/workbench.html','static/workbench.css','static/workbench.js','static/workbench-layout.js','static/workbench-layout.css','static/workspaces-data.js','static/workspaces-data.css','tests/auth_helpers.cjs','tests/browser_workbench_layout.cjs'])
    sourceHashes[file]=require('node:crypto').createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex');
  fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify({
    result:'PASS',source_head:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),
    dirty:!!execFileSync('git',['status','--porcelain'],{cwd:root,encoding:'utf8'}).trim(),source_hashes:sourceHashes,
    command:'node tests/browser_workbench_layout.cjs',browser:(await send('Browser.getVersion')).product,
    environment:{mode:'headless',graphics:'--disable-gpu software rendering',sandbox:'--no-sandbox verification only',isolation:'task-owned temporary browser profile and authored dataset',process_lifecycle:'tracked server/browser killed in finally; debugger startup bounded at 60 seconds'},
    viewports:[{width:1600,height:1100},{width:390,height:844}],
    checks:['current controls/native constraints/kinds/tasks/export options/scripts retained','current audio/pointcloud/volume/scientific source surfaces retained','explicit authenticated owner fixture for browser and API calls','native Shift+Tab modal containment and Escape/focus restoration','repeated dialogs preserve draft/selection','status mirrored inside modal','collapsed invalid groups revealed without save','explicit review/save/release download','exact metadata Enter filter','saved state/current record markers','original-pixel image coordinates after scaling','mesh native import/projections','desktop and narrow content fit','no runtime errors'],
    captures:['text-desktop.jpg','export-desktop.jpg','image-desktop.jpg','mesh-desktop.jpg','mesh-narrow.jpg','import-narrow.jpg','text-narrow.jpg'],
    qualification:'Standalone authenticated composed UI with authored fixtures and current scientific controls; no inference, training, scientific quality, assistive-technology or cross-browser conformance claim'
  },null,2)+'\n');
  console.log('Compact workbench: native drawer clicks/Escape/focus, preserved draft and selection, import, hidden required-field validation, save, release download, offline generation, scaled image coordinates, mesh import/projections and desktop/narrow pixels passed. '+report);
})().catch(error=>{console.error(error);console.error('Runtime errors:',JSON.stringify(errors));process.exitCode=1;}).finally(async()=>{if(ws)ws.close();for(const child of children)child.kill();await pause(200);fs.rmSync(temporary,{recursive:true,force:true});});
