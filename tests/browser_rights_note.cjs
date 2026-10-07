// Native browser smoke test. No npm dependencies.
const {qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process');
const root=process.env.TULDOK_SOURCE_ROOT||path.resolve(__dirname,'..'),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-rights-browser-')),children=[];
let ws, inspect;
const errors=[];
const {pageLoadTracker}=require('./browser_page_load.cjs');const pageLoads=pageLoadTracker();
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn){for(let i=0;i<150;i++){const value=await fn();if(value)return value;await pause(100);}throw Error('Timed out');}
function launch(command,args,options={}){const child=spawn(command,args,options);children.push(child);return child;}
(async()=>{
  const reports=qaDirectory(root,'rights-note');
  const server=launch('python3',['-u','app.py','--port','0','--data',path.join(temporary,'data')],{cwd:root,stdio:['ignore','pipe','pipe']});
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
  ws.onmessage=event=>{const message=JSON.parse(event.data);pageLoads.observe(message);if(message.id){const task=pending.get(message.id);pending.delete(message.id);message.error?task.reject(message.error):task.resolve(message.result);}if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails);};
  const send=(method,params={})=>new Promise((resolve,reject)=>{pending.set(++id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
  const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  inspect=()=>evaluate('JSON.stringify({url:location.href,ready:document.readyState,notice:document.getElementById("notice")?.textContent,body:document.body?.innerText.slice(0,1500),viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,overflow:[...document.querySelectorAll("body *")].filter(e=>e.getBoundingClientRect().right>innerWidth || e.scrollWidth>e.clientWidth+1).map(e=>({tag:e.tagName,id:e.id,class:e.className,right:e.getBoundingClientRect().right,width:e.getBoundingClientRect().width})).slice(0,30)})');
  const click=id=>evaluate('document.getElementById('+JSON.stringify(id)+').click()');
  const fill=(id,value)=>evaluate('(()=>{const e=document.getElementById('+JSON.stringify(id)+');e.value='+JSON.stringify(value)+';e.dispatchEvent(new Event("input",{bubbles:true}));e.dispatchEvent(new Event("change",{bubbles:true}));})()');
  const base='http://127.0.0.1:'+port,ref=row=>({id:row.id,revision:row.revision,source_revision:row.source_revision});
  const request=async(path,body)=>{const r=await fetch(base+'/api/workbench/'+path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const data=await r.json();assert.ok(r.ok,JSON.stringify(data));return data;};
  async function text(name,label,groups,rights,task='text_classification') {
    const row=await request('import',{kind:'text',name,text:'Local source for '+name,groups,rights});
    return request('records/'+row.id,{...row,task,review:'human_reviewed',annotation:task==='text_entities'?{spans:[{label,start:0,end:5}]}:{label}});
  }
  async function image(name,color,task,annotation,groups,rights) {
    const bytes=await evaluate(`(()=>{const canvas=document.createElement('canvas');canvas.width=16;canvas.height=16;const c=canvas.getContext('2d');c.fillStyle=${JSON.stringify(color)};c.fillRect(0,0,16,16);return canvas.toDataURL('image/png').split(',')[1];})()`);
    const row=await request('import',{kind:'image',name,image:bytes,groups,rights});
    return request('records/'+row.id,{...row,task,annotation,review:'human_reviewed'});
  }
  const origin='Declared café\r\nSecond line\rThird line\n😀';
  let row=await text('Rights reviewed source','intent',['rights-family'],origin);
  const draft=await request('import',{kind:'text',name:'Draft source',text:'Fictional unreviewed draft',groups:['draft'],rights:'unknown'});
  const sibling=await request('import',{kind:'text',name:'Related context',text:'Fictional related context',groups:['rights-family'],rights:'unknown'});
  const saved=await request('selections',{name:'Fixed rights set',items:[ref(row)]});
  await send('Page.enable');await send('Runtime.enable');await send('Page.setLifecycleEventsEnabled',{enabled:true});
  await send('Page.navigate',{url:base+'/workbench'});await until(()=>evaluate('document.getElementById("notice")?.textContent === "Collection ready."'));
  await evaluate('refreshSavedSets('+JSON.stringify(saved.id)+')');await click('load-selection');await until(()=>evaluate('!savedLoadBusy && selected.size===1'));
  const fixed=await evaluate('releaseBody().items');
  const unloading=()=>evaluate('(()=>{const event=new Event("beforeunload",{cancelable:true});window.dispatchEvent(event);return event.defaultPrevented;})()');
  await evaluate('openRecord('+JSON.stringify(row.id)+')');
  assert.equal(await evaluate('document.getElementById("rights-note-format").value'),'json');assert.equal(await evaluate('rightsValue()'),origin);assert.equal(await unloading(),false,'unchanged note is clean');
  const snapshot=()=>{const {spawnSync}=require('node:child_process');const result=spawnSync('python3',['-c',`import sqlite3,json;db=sqlite3.connect(${JSON.stringify(path.join(temporary,'data','dataset.sqlite3'))});print(json.dumps({t:db.execute('SELECT * FROM '+t+' ORDER BY rowid').fetchall() for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}))`],{encoding:'utf8'});assert.equal(result.status,0,result.stderr);return result.stdout;};
  const submit=async()=>{await evaluate('document.getElementById("rights-note-form").requestSubmit()');await until(()=>evaluate('!rightsBusy'));};
  const feff=await request('import',{kind:'text',name:'FEFF note',text:'Fictional FEFF boundary source',groups:['boundary'],rights:'\ufeffowner\ufeff'});
  await evaluate('openRecord('+JSON.stringify(feff.id)+')');assert.equal(await evaluate('document.getElementById("rights-note-value").value'),'\ufeffowner\ufeff');
  const feffBefore=snapshot();await submit();assert.equal(snapshot(),feffBefore);assert.equal(await evaluate('current.revision'),1);assert.equal((await request('records/'+feff.id)).provenance.rights,'\ufeffowner\ufeff');assert.equal(await unloading(),false);
  const pythonOnly=await request('import',{kind:'text',name:'Python boundary note',text:'Fictional Python-only whitespace source',groups:['boundary'],rights:'owner'});
  const {spawnSync}=require('node:child_process'),rawNote='\u0085owner\u001c\u001f';
  const patchOrigin=spawnSync('python3',['-c','import sqlite3,json,sys;db=sqlite3.connect(sys.argv[1]);p=json.loads(db.execute("SELECT provenance_json FROM workbench_records WHERE id=?",(sys.argv[2],)).fetchone()[0]);p["rights"]=sys.argv[3];db.execute("UPDATE workbench_records SET provenance_json=? WHERE id=?",(json.dumps(p),sys.argv[2]));db.commit()',path.join(temporary,'data','dataset.sqlite3'),pythonOnly.id,rawNote],{encoding:'utf8'});assert.equal(patchOrigin.status,0,patchOrigin.stderr);
  await evaluate('openRecord('+JSON.stringify(pythonOnly.id)+')');assert.equal(await evaluate('document.getElementById("rights-note-value").value'),'owner');
  const pythonBefore=snapshot();await submit();assert.equal(snapshot(),pythonBefore);assert.equal(await evaluate('current.revision'),1);
  await fill('rights-note-value',rawNote);assert.equal(await evaluate('rightsDirty'),false);assert.equal(await unloading(),false);await submit();assert.equal(snapshot(),pythonBefore);assert.equal((await request('records/'+pythonOnly.id)).provenance.rights,rawNote);
  await evaluate('openRecord('+JSON.stringify(row.id)+')');
  await fill('train',100);await fill('validation',0);await fill('test',0);await click('preview-release');await until(()=>evaluate('!!releasePreview?.eligible'));
  const token=await evaluate('releasePreview.preview_token'),before=snapshot();
  await fill('rights-note-value',JSON.stringify('Canceled fictional correction'));assert.equal(await evaluate('rightsDirty'),true);assert.equal(await evaluate('dirty'),false);assert.equal(await unloading(),true,'rights-only draft beforeunload');
  await evaluate('window.confirm=()=>false;openRecord('+JSON.stringify(draft.id)+')');assert.equal(await evaluate('current.id'),row.id);
  await click('rights-note-cancel');assert.equal(await unloading(),false,'canceled rights draft is clean');assert.equal(snapshot(),before);assert.equal(await evaluate('releasePreview.preview_token'),token);
  await submit();assert.equal(await unloading(),false,'saved unchanged note is clean');assert.equal(snapshot(),before);assert.ok((await evaluate('document.getElementById("rights-note-status").textContent')).includes('unchanged'));assert.equal(await evaluate('releasePreview.preview_token'),token);
  // Actual JSON controls retain internal CR/CRLF, Unicode and composed/decomposed spelling.
  const note='Corrected café e\u0301 😀\nAnother line\rCarriage return\r\nLast line';
  await fill('rights-note-value',JSON.stringify(note));
  await fill('rights-note-format','text');assert.equal(await evaluate('document.getElementById("rights-note-format").value'),'json');
  await evaluate(`window.originalFetch=window.fetch;window.rightsHeld=[];window.rightsCount=0;window.fetch=async(...args)=>{const response=await originalFetch(...args);if(String(args[0]).includes('/rights/')){++rightsCount;await new Promise(resolve=>rightsHeld.push(resolve));}return response;};`);
  await evaluate('document.getElementById("rights-note-form").requestSubmit()');await until(()=>evaluate('rightsHeld.length===1'));
  await evaluate('document.getElementById("rights-note-form").requestSubmit()');assert.equal(await evaluate('rightsCount'),1);
  await evaluate('rightsHeld[0]()');await until(()=>evaluate('!rightsBusy && current.revision===3'));
  assert.equal(await unloading(),false,'changed note saved cleanly');row=await request('records/'+row.id);assert.equal(row.provenance.rights,note===origin?note:origin);assert.equal(row.provenance.rights_note_correction.note,note);assert.equal(row.review,'human_reviewed');
  assert.equal(await evaluate('releasePreview'),null);assert.equal(await evaluate('document.getElementById("freeze-release").disabled'),true);
  assert.deepEqual(await evaluate('releaseBody().items'),fixed);assert.deepEqual((await request('selections/'+saved.id)).selection.items,saved.items);
  assert.ok((await evaluate('document.getElementById("saved-selection-issues").textContent')).includes('stale'));
  // Reopening proves staleness but never replaces the original pair.
  await click('load-selection');await until(()=>evaluate('!savedLoadBusy'));assert.deepEqual(await evaluate('releaseBody().items'),fixed);
  assert.ok((await evaluate('document.getElementById("saved-selection-issues").textContent')).includes('stale'));
  await evaluate('window.fetch=originalFetch');
  // A concurrent external correction makes a stale editor's note fail; draft is retained.
  const external=await request('rights/'+row.id,{revision:row.revision,source_revision:row.source_revision,note:'Concurrent note'});
  await fill('rights-note-value',JSON.stringify('Retained local draft'));await submit();assert.equal(await evaluate('current.revision'),3);assert.equal(await evaluate('document.getElementById("rights-note-value").value'),JSON.stringify('Retained local draft'));
  assert.ok((await evaluate('document.getElementById("rights-note-status").textContent')).includes('changed'));
  await evaluate('window.confirm=()=>true');await click('reload');await until(()=>evaluate('current.revision===4 && !document.getElementById("reload").dataset.busy'));
  // Annotation and rights drafts cannot erase each other or grant review.
  await fill('label','unsaved annotation');await evaluate('document.getElementById("label").dispatchEvent(new Event("input",{bubbles:true}))');
  assert.equal(await unloading(),true,'annotation-only draft is guarded');await fill('rights-note-value','Blocked until annotation resolved');const noWrite=snapshot();await submit();assert.equal(snapshot(),noWrite);
  await click('reload');await until(()=>evaluate('!dirty && !document.getElementById("reload").dataset.busy'));
  // An older note completion cannot overwrite a later annotation edit.
  await evaluate(`window.rightsHeld=[];window.fetch=async(...args)=>{const response=await originalFetch(...args);if(String(args[0]).includes('/rights/'))await new Promise(resolve=>rightsHeld.push(resolve));return response;};`);
  await fill('rights-note-value','Delayed correction');await evaluate('document.getElementById("rights-note-form").requestSubmit()');await until(()=>evaluate('rightsHeld.length===1'));
  await fill('label','Later annotation edit');await evaluate('document.getElementById("label").dispatchEvent(new Event("input",{bubbles:true}));rightsHeld[0]()');await until(()=>evaluate('!rightsBusy'));
  assert.equal(await evaluate('current.revision'),4);assert.equal(await evaluate('document.getElementById("label").value'),'Later annotation edit');assert.equal(await evaluate('dirty'),true);assert.deepEqual(await evaluate('releaseBody().items'),fixed);
  await evaluate('window.fetch=originalFetch');await click('reload');await until(()=>evaluate('current.revision===5 && !dirty && !document.getElementById("reload").dataset.busy'));
  // Note text alone grants no annotation/review on an unreviewed source.
  await evaluate('openRecord('+JSON.stringify(draft.id)+')');await fill('rights-note-value','Permission claimed in an arbitrary note');await submit();const draftAfter=await request('records/'+draft.id);assert.equal(draftAfter.review,'draft');assert.equal(draftAfter.annotation,null);
  // Explicit reselection obtains current revisions; native preview/export still owns freshness.
  await evaluate('selected.clear();selection(true)');await fill('query','Rights reviewed source');await evaluate('document.getElementById("filters").requestSubmit()');await until(()=>evaluate('page.total===1 && !document.getElementById("filters").dataset.busy'));
  await click('select-page');await until(()=>evaluate('selected.size===1 && !document.getElementById("select-page").dataset.busy'));await click('preview-release');await until(()=>evaluate('releasePreview?.eligible'));
  const freshToken=await evaluate('releasePreview.preview_token');assert.notEqual(freshToken,token);
  // Unselected related-source correction changes lineage-bound preview; old token cannot export.
  const changedSibling=await request('rights/'+sibling.id,{revision:sibling.revision,source_revision:sibling.source_revision,note:'Related owner note'});assert.equal(changedSibling.changed,true);
  // Hold the actual stale HTTP response to reproduce the hosted timing race deterministically.
  await evaluate(`window.staleBaseFetch=window.fetch;window.staleExportRelease=null;window.staleHoldOnce=true;window.staleStatus=null;window.staleError=null;window.freshPreviewRequests=0;window.freshPreviewTokens=[];window.fetch=async(...args)=>{const route=String(args[0]);if(route.endsWith('/releases/preview'))++freshPreviewRequests;const response=await staleBaseFetch(...args);if(route.endsWith('/releases')&&staleHoldOnce){staleHoldOnce=false;staleStatus=response.status;staleError=(await response.clone().json()).error;await new Promise(resolve=>staleExportRelease=resolve);}if(route.endsWith('/releases/preview')&&response.ok)freshPreviewTokens.push((await response.clone().json()).preview_token);return response;};`);
  await evaluate('document.getElementById("release-form").requestSubmit()');await until(()=>evaluate('!!staleExportRelease'));
  assert.equal(await evaluate('staleStatus'),409);assert.match(await evaluate('staleError'),/Release preview changed/);
  assert.equal(await evaluate('releaseBusy'),true);assert.equal(await evaluate('releasePreview.preview_token'),freshToken);
  assert.equal(await evaluate('!!document.getElementById("release-form").dataset.busy'),false,'The former form-dataset wait can pass while the export is still pending');
  assert.equal(await evaluate('document.getElementById("preview-release").disabled'),true);
  await click('preview-release');assert.equal(await evaluate('freshPreviewRequests'),0,'Clicking disabled Preview cannot schedule a new request');
  await evaluate('staleExportRelease();staleExportRelease=null');
  await until(()=>evaluate('!releaseBusy && releasePreview===null && document.getElementById("release-preview-status").textContent.includes("Release preview changed")'));
  assert.equal(await evaluate('document.getElementById("freeze-release").disabled'),true);
  assert.equal(await evaluate('document.getElementById("preview-release").disabled'),false);
  await click('preview-release');
  await until(()=>evaluate('!releaseBusy && freshPreviewRequests===1 && freshPreviewTokens.length===1 && releasePreview?.eligible && releasePreview.preview_token===freshPreviewTokens[0]'));
  const refreshedToken=await evaluate('releasePreview.preview_token');assert.match(refreshedToken,/^[a-f0-9]{64}$/);assert.notEqual(refreshedToken,freshToken,'A newly returned lineage-bound proof replaces the stale token');
  await evaluate('window.fetch=staleBaseFetch');
  await evaluate('document.getElementById("release-form").requestSubmit()');await until(()=>evaluate('!!document.querySelector("#release-result a")'));
  const zip=await fetch(await evaluate('document.querySelector("#release-result a").href'));assert.equal(zip.status,200);assert.ok((await zip.arrayBuffer()).byteLength>500);
  await evaluate('openRecord('+JSON.stringify(row.id)+')');await click('history');await until(()=>evaluate('!document.getElementById("history-output").hidden'));
  assert.ok((await evaluate('document.getElementById("history-output").textContent')).includes('rights_note_correction'));
  await evaluate('document.getElementById("rights-note-panel").scrollIntoView()');let shot=await send('Page.captureScreenshot',screenshotOptions);fs.writeFileSync(path.join(reports,'rights-desktop.jpg'),Buffer.from(shot.data,'base64'));
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});await evaluate('document.getElementById("rights-note-panel").scrollIntoView()');shot=await send('Page.captureScreenshot',screenshotOptions);fs.writeFileSync(path.join(reports,'rights-narrow.jpg'),Buffer.from(shot.data,'base64'));
  assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'),'390px note form stays within viewport');assert.deepEqual(errors,[]);
  console.log('Rights-note screenshots:',reports);
  console.log('Actual Chromium beforeunload rights-only/unchanged/saved/canceled/annotation states, rights-note cancel/no-op, JSON CR/LF/Unicode, repeated and delayed edits, concurrent stale conflict, annotation separation, fixed saved sets/issues, review preservation, lineage freshness with held stale response/releaseBusy completion/new preview token, explicit reselection, ZIP/history and desktop/narrow passed.');
})().catch(async error=>{console.error(error);console.error('Runtime errors:',JSON.stringify(errors));if(inspect)try{console.error('Page diagnostics:',await inspect());}catch(diagnostic){console.error('Diagnostics failed:',diagnostic);}process.exitCode=1;}).finally(async()=>{if(ws)ws.close();for(const child of children)child.kill();await pause(200);fs.rmSync(temporary,{recursive:true,force:true});});
