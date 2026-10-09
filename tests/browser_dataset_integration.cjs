// Real manifest files, HTTP admission, cancellation, persistence and Chromium.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn,spawnSync}=require('node:child_process'),crypto=require('node:crypto');
const {pageLoadTracker}=require('./browser_page_load.cjs');
const root=path.resolve(__dirname,'..'),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-integration-browser-')),children=[];
const errors=[],tracker=pageLoadTracker(),pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
let ws,inspect;
async function until(fn){for(let i=0;i<150;i++){const value=await fn();if(value)return value;await pause(100);}throw Error('Timed out');}
function launch(command,args,options={}){const child=spawn(command,args,options);children.push(child);return child;}
function python(code,...args){const result=spawnSync('python3',['-c',code,...args],{cwd:root,encoding:'utf8'});assert.equal(result.status,0,result.stderr);return result.stdout;}
(async()=>{
  python("from PIL import Image; import sys; from pathlib import Path; p=Path(sys.argv[1]); Image.new('RGB',(80,60),'#467e9a').save(p/'photo.png'); Image.new('RGB',(80,60),'#be5467').save(p/'other.png')",temporary);
  const photo=fs.readFileSync(path.join(temporary,'photo.png')),other=fs.readFileSync(path.join(temporary,'other.png'));
  const server=launch('python3',['-u','app.py','--port','0','--data',path.join(temporary,'data')],{cwd:root,stdio:['ignore','pipe','pipe']});
  let output='';server.stdout.on('data',data=>output+=data);server.stderr.on('data',data=>{if(process.env.BULK_BROWSER_DEBUG)process.stderr.write(data);});
  const port=await until(()=>output.match(/127\.0\.0\.1:(\d+)/)?.[1]),base='http://127.0.0.1:'+port;
  const api=async(route,body)=>{const response=await fetch(base+'/api/workbench/'+route,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const result=await response.json();assert.ok(response.ok,JSON.stringify(result));return result;};
  const seed=await api('import',{kind:'text',text:'Keep this editor intact.',name:'Existing editor',groups:['existing-source'],rights:'Authored'});
  launch(process.env.BROWSER||'/usr/bin/chromium',['--headless','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--window-size=1400,950','--user-data-dir='+path.join(temporary,'browser'),'about:blank'],{stdio:['ignore','ignore','inherit'],env:{...process.env,XDG_CONFIG_HOME:temporary,XDG_CACHE_HOME:temporary}});
  const active=path.join(temporary,'browser','DevToolsActivePort');
  const debugPort=await until(()=>fs.existsSync(active)&&fs.readFileSync(active,'utf8').split('\n')[0]);
  const tabs=await(await fetch('http://127.0.0.1:'+debugPort+'/json')).json(),target=tabs.find(tab=>tab.type==='page'&&tab.url==='about:blank');
  assert.ok(target,'Expected explicitly launched page');ws=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  let id=0;const pending=new Map();
  ws.onmessage=event=>{const message=JSON.parse(event.data);tracker.observe(message);if(message.id){const task=pending.get(message.id);pending.delete(message.id);if(task)message.error?task.reject(message.error):task.resolve(message.result);}if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails);};
  const send=(method,params={})=>new Promise((resolve,reject)=>{const request=++id;const timer=setTimeout(()=>{pending.delete(request);reject(Error('CDP timeout: '+method));},20000);pending.set(request,{resolve:value=>{clearTimeout(timer);resolve(value);},reject:error=>{clearTimeout(timer);reject(error);}});ws.send(JSON.stringify({id:request,method,params}));});
  const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  inspect=()=>evaluate('JSON.stringify({url:location.href,notice:document.getElementById("notice")?.textContent,status:document.getElementById("bulk-status")?.textContent,release:document.getElementById("release-preview-status")?.textContent,releaseBusy,preview:releasePreview?.eligible,results:document.getElementById("bulk-results")?.textContent,body:document.body?.innerText.slice(0,1800)})');
  const click=id=>evaluate('document.getElementById('+JSON.stringify(id)+').click()');
  const choose=(lines,images=[],name='assets.jsonl')=>evaluate(`(()=>{const manifest=new DataTransfer();manifest.items.add(new File([${JSON.stringify(lines)}],${JSON.stringify(name)},{type:'application/x-ndjson'}));document.getElementById('bulk-manifest').files=manifest.files;const selected=new DataTransfer();for(const image of ${JSON.stringify(images)}){const bytes=Uint8Array.from(atob(image.data),c=>c.charCodeAt(0));selected.items.add(new File([bytes],image.name,{type:'image/png'}));}document.getElementById('bulk-images').files=selected.files;})()`);
  const row=(text,name)=>JSON.stringify({kind:'text',name,text,groups:['document-source'],rights:'Authored'});
  const importNow=()=>evaluate('document.getElementById("bulk-form").requestSubmit()');
  const idle=()=>until(()=>evaluate('!document.getElementById("bulk-start").disabled'));
  await send('Page.enable');await send('Page.setLifecycleEventsEnabled',{enabled:true});await send('Runtime.enable');
  console.log('Integration browser targets:',JSON.stringify(tabs.map(tab=>({type:tab.type,url:tab.url}))));
  console.log('Integration browser version:',JSON.stringify(await send('Browser.getVersion')));
  assert.ok(!(await send('Page.navigate',{url:base+'/workbench'})).errorText);
  await until(()=>evaluate('document.getElementById("notice")?.textContent==="Collection ready."'));
  const fill=(id,value)=>evaluate('(()=>{const e=document.getElementById('+JSON.stringify(id)+');e.value='+JSON.stringify(value)+';e.dispatchEvent(new Event("input",{bubbles:true}));e.dispatchEvent(new Event("change",{bubbles:true}));})()');
  const submit=async id=>{await evaluate('document.getElementById('+JSON.stringify(id)+').requestSubmit()');await until(()=>evaluate('!document.getElementById('+JSON.stringify(id)+').dataset.busy'));};
  const filter=()=>submit('filters');
  const ref=r=>({id:r.id,revision:r.revision,source_revision:r.source_revision});
  const pairs=()=>evaluate('releaseBody().items');
  const note='Recorded source\r\nPermission still unverified';
  const native=[{kind:'text',name:'Corpus text',text:'A retained local text source.',groups:['corpus'],rights:note},
    {kind:'image',name:'Corpus image',file:'photo.png',groups:['corpus'],rights:note},
    {kind:'text',name:'Forged review',text:'Should be rejected.',groups:['corpus'],rights:note,review:'human_reviewed'}];
  await choose(native.map(r=>JSON.stringify(r)).join('\n'),[{name:'photo.png',data:photo.toString('base64')}]);
  await importNow();await idle();assert.match(await evaluate('document.getElementById("bulk-status").textContent'),/Complete: 2 created, 1 rejected/);
  const initial=(await api('records')).items.filter(r=>r.groups.includes('corpus'));
  assert.equal(initial.length,2);assert.ok(initial.every(r=>r.review==='draft'&&r.annotation===null));
  const text=initial.find(r=>r.kind==='text'),image=initial.find(r=>r.kind==='image');
  assert.deepEqual(fs.readFileSync(path.join(temporary,'data/images',image.id,'source')),photo);
  await fill('exact-filter-format','json');await fill('group-filter',JSON.stringify('corpus'));await fill('rights-filter',JSON.stringify(note));await filter();
  assert.equal(await evaluate('page.total'),2);assert.equal(await evaluate('page.items.every(r=>r.rights_note.includes("\\r\\n"))'),true);
  await click('select-page');await fill('selection-name','Imported drafts');await submit('save-selection-form');
  const draftSet=(await api('selections')).selections.find(s=>s.name==='Imported drafts');assert.ok(draftSet);
  await fill('train','100');await fill('validation','0');await fill('test','0');await click('preview-release');
  await until(()=>evaluate('!releaseBusy'));assert.equal(await evaluate('releasePreview.eligible'),false,'Saving imported drafts grants no review');
  assert.equal(await evaluate('document.getElementById("freeze-release").disabled'),true);
  await click('clear-selection');
  for(const record of [text,image]) {
    await evaluate('openRecord('+JSON.stringify(record.id)+')');
    if(record.kind==='image')await fill('task','image_classification');
    await fill('label','integration');await fill('record-review','human_reviewed');await submit('editor');
  }
  await fill('label-filter',JSON.stringify('integration'));await filter();assert.equal(await evaluate('page.total'),2);
  await click('select-page');await fill('selection-name','Reviewed corpus fixed');await submit('save-selection-form');
  const summary=(await api('selections')).selections.find(s=>s.name==='Reviewed corpus fixed');assert.ok(summary);
  const saved=(await api('selections/'+summary.id)).selection;
  await click('clear-selection');await fill('saved-selection',saved.id);await click('load-selection');await until(()=>evaluate('!savedLoadBusy && selected.size===2'));
  const fixed=await pairs();assert.deepEqual(fixed,saved.items.map(ref));
  await click('preview-release');await until(()=>evaluate('!releaseBusy && !!releasePreview'));
  assert.equal(await evaluate('releasePreview.eligible'),true);const token=await evaluate('releasePreview.preview_token');
  assert.equal(await evaluate('document.getElementById("freeze-release").disabled'),false);
  // Dynamic raw rows match note criteria without joining the fixed set or its lineage.
  await fill('label-filter','');await fill('group-filter','');await filter();
  await choose(JSON.stringify({kind:'text',name:'Additional raw',text:'Another distinct retained source.',groups:['additional'],rights:note}));
  await importNow();await idle();await until(()=>evaluate('page.total===3'));assert.equal(await evaluate('page.total'),3);
  assert.deepEqual(await pairs(),fixed);assert.equal(await evaluate('releasePreview.preview_token'),token);
  // Hold real responses after the server has returned/committed. Only acknowledgment is delayed.
  await evaluate(`(()=>{const original=window.fetch;window.holdQuery=false;window.holdImport=false;window.holdEditor=false;window.releaseQuery=null;window.releaseImport=null;window.releaseEditor=null;window.fetch=async(url,options)=>{const response=await original(url,options);let slot=null;if(window.holdQuery&&String(url).startsWith('/api/workbench/records?')){window.holdQuery=false;slot='releaseQuery';}else if(window.holdImport&&String(url).endsWith('/import-row')){window.holdImport=false;slot='releaseImport';}else if(window.holdEditor&&options?.method==='POST'&&String(url).includes('/records/')){window.holdEditor=false;slot='releaseEditor';}if(slot)await new Promise(resolve=>window[slot]=resolve);return response;};})()`);
  await evaluate('window.holdQuery=true;window.oldQuery=refresh();void 0');await until(()=>evaluate('!!window.releaseQuery'));
  await fill('rights-filter',JSON.stringify('No matching note'));await filter();assert.equal(await evaluate('page.total'),0);
  await evaluate('window.releaseQuery();window.releaseQuery=null;window.oldQuery');assert.equal(await evaluate('page.total'),0,'Late prior filters cannot repaint');
  assert.deepEqual(await pairs(),fixed);assert.equal(await evaluate('releasePreview.preview_token'),token);
  await fill('rights-filter',JSON.stringify(note));await filter();
  await choose([{kind:'text',name:'Delayed raw',text:'Retained despite late acknowledgment.',groups:['delayed'],rights:note},
    {kind:'text',name:'Not scheduled',text:'Should never be admitted.',groups:['never'],rights:note}].map(r=>JSON.stringify(r)).join('\n'));
  await evaluate('window.holdImport=true');await importNow();await until(()=>evaluate('!!window.releaseImport'));
  await click('bulk-stop');await fill('rights-filter',JSON.stringify('No matching note'));await filter();
  await evaluate('window.releaseImport();window.releaseImport=null');await idle();
  assert.match(await evaluate('document.getElementById("bulk-status").textContent'),/Stopped: 1 created.*1 not attempted/);
  assert.equal(await evaluate('page.total'),0,'Late bulk refresh uses current criteria');
  assert.deepEqual(await pairs(),fixed);assert.equal(await evaluate('releasePreview.preview_token'),token);
  assert.equal((await api('records?q=Not%20scheduled')).total,0);
  await fill('rights-filter',JSON.stringify(note));await filter();assert.equal(await evaluate('page.total'),4);
  assert.deepEqual((await api('selections/'+saved.id)).selection.items,saved.items);
  await evaluate('document.getElementById("release-form").requestSubmit()');await until(()=>evaluate('!releaseBusy && !!document.querySelector("#release-result a")'));const href=await evaluate('document.querySelector("#release-result a").href');
  const zip=await fetch(href);assert.equal(zip.status,200);assert.ok((await zip.arrayBuffer()).byteLength>1000);
  // A completed editor commit acknowledged after fixed open must retain its old pairs.
  await evaluate('openRecord('+JSON.stringify(text.id)+')');await fill('label','integration later');await fill('record-review','human_reviewed');
  await evaluate('window.holdEditor=true;document.getElementById("editor").requestSubmit()');await until(()=>evaluate('!!window.releaseEditor'));
  await click('load-selection');await until(()=>evaluate('!savedLoadBusy'));
  assert.deepEqual(await pairs(),fixed);
  await evaluate('window.releaseEditor();window.releaseEditor=null');await until(()=>evaluate('!document.getElementById("editor").dataset.busy'));
  assert.deepEqual(await pairs(),fixed,'Later fixed intent survives earlier editor completion');
  const loaded=await api('selections/'+saved.id);assert.equal(loaded.members.find(m=>m.item.id===text.id).status,'stale');
  assert.deepEqual(loaded.selection.items,saved.items);
  const staleBody=await evaluate('releaseBody()');assert.equal((await api('releases/preview',staleBody)).eligible,false);
  await click('preview-release');await until(()=>evaluate('!releaseBusy'));
  assert.equal(await evaluate('releasePreview.eligible'),false);assert.equal(await evaluate('document.getElementById("freeze-release").disabled'),true);
  assert.equal((await api('records/'+text.id)).provenance.rights,note);
  await fill('group-filter',JSON.stringify('corpus'));await filter();assert.equal(await evaluate('page.total'),2);
  await click('select-page');await click('preview-release');await until(()=>evaluate('!releaseBusy'));
  assert.equal(await evaluate('releasePreview.eligible'),true,'Explicit reselection adopts current reviewed revisions');
  assert.notEqual(await evaluate('releasePreview.preview_token'),token);
  await evaluate('document.getElementById("release-form").requestSubmit()');await until(()=>evaluate('!releaseBusy && !!document.querySelector("#release-result a")'));const newer=await fetch(await evaluate('document.querySelector("#release-result a").href'));assert.equal(newer.status,200);
  const reports=path.join(root,'docs/plans/dataset-integration/reports');fs.mkdirSync(reports,{recursive:true});
  await evaluate('document.getElementById("filters").scrollIntoView()');
  const desktop=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});fs.writeFileSync(path.join(reports,'integration-desktop.png'),Buffer.from(desktop.data,'base64'));
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
  await evaluate('document.getElementById("filters").scrollIntoView()');
  const narrow=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});fs.writeFileSync(path.join(reports,'integration-narrow.png'),Buffer.from(narrow.data,'base64'));
  assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'));assert.deepEqual(errors,[]);
  console.log('Combined real JSONL text/image import, draft gate, lossless CRLF filter, explicit review, fixed set, exact preview/export, dynamic rows, late query/import/editor responses, stop and stale-pair blocking/adoption passed.');
})().catch(async error=>{console.error(error);console.error('Runtime errors:',JSON.stringify(errors));if(inspect)try{console.error('Page diagnostics:',await inspect());}catch(diagnostic){console.error('Diagnostics failed:',diagnostic);}process.exitCode=1;}).finally(async()=>{if(ws)ws.close();for(const child of children)child.kill();await pause(200);fs.rmSync(temporary,{recursive:true,force:true});});
