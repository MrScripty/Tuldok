// Real manifest files, HTTP admission, cancellation, persistence and Chromium.
'use strict';
const {qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn,spawnSync}=require('node:child_process'),crypto=require('node:crypto');
const {pageLoadTracker}=require('./browser_page_load.cjs');
const root=path.resolve(__dirname,'..'),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-bulk-browser-')),children=[];
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
  ws.onmessage=event=>{const message=JSON.parse(event.data);tracker.observe(message);if(message.id){const task=pending.get(message.id);pending.delete(message.id);message.error?task.reject(message.error):task.resolve(message.result);}if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails);};
  const send=(method,params={})=>new Promise((resolve,reject)=>{pending.set(++id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
  const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  inspect=()=>evaluate('JSON.stringify({url:location.href,notice:document.getElementById("notice")?.textContent,status:document.getElementById("bulk-status")?.textContent,results:document.getElementById("bulk-results")?.textContent,body:document.body?.innerText.slice(0,1800)})');
  const click=id=>evaluate('document.getElementById('+JSON.stringify(id)+').click()');
  const choose=(lines,images=[],name='assets.jsonl')=>evaluate(`(()=>{const manifest=new DataTransfer();manifest.items.add(new File([${JSON.stringify(lines)}],${JSON.stringify(name)},{type:'application/x-ndjson'}));document.getElementById('bulk-manifest').files=manifest.files;const selected=new DataTransfer();for(const image of ${JSON.stringify(images)}){const bytes=Uint8Array.from(atob(image.data),c=>c.charCodeAt(0));selected.items.add(new File([bytes],image.name,{type:'image/png'}));}document.getElementById('bulk-images').files=selected.files;})()`);
  const row=(text,name)=>JSON.stringify({kind:'text',name,text,groups:['document-source'],rights:'Authored'});
  const importNow=()=>evaluate('document.getElementById("bulk-form").requestSubmit()');
  const idle=()=>until(()=>evaluate('!document.getElementById("bulk-start").disabled'));
  await send('Page.enable');await send('Page.setLifecycleEventsEnabled',{enabled:true});await send('Runtime.enable');
  console.log('Bulk browser targets:',JSON.stringify(tabs.map(tab=>({type:tab.type,url:tab.url}))));
  console.log('Bulk browser version:',JSON.stringify(await send('Browser.getVersion')));
  assert.ok(!(await send('Page.navigate',{url:base+'/workbench'})).errorText);
  await until(()=>evaluate('document.getElementById("notice")?.textContent==="Collection ready."'));
  await evaluate('openRecord('+JSON.stringify(seed.id)+')');
  await evaluate('document.getElementById("label").value="keep my edit";document.getElementById("label").dispatchEvent(new Event("input",{bubbles:true}));document.querySelector(".record input").click()');
  await evaluate(`(()=>{const original=window.fetch;window.bulkPosts=[];window.bulkChecks=0;window.holdNextRow=false;window.releaseBulkResponse=null;window.loseNextRow=false;window.fetch=async(...args)=>{const url=String(args[0]);if(url.includes('/import-result/'))window.bulkChecks++;if(url.endsWith('/import-row')&&args[1]?.method==='POST'){window.bulkPosts.push(JSON.parse(args[1].body));const response=await original(...args);if(window.loseNextRow){window.loseNextRow=false;throw Error('controlled response loss after actual admission');}if(window.holdNextRow){window.holdNextRow=false;await new Promise(resolve=>window.releaseBulkResponse=resolve);}return response;}return original(...args);};})()`);
  const sourceLines=[row('cafe\u0301\r\n','Real note'),'{broken',JSON.stringify({kind:'image',file:'missing.png',groups:['shoot-source']}),
    JSON.stringify({kind:'image',file:'same.png',groups:['shoot-source']}),JSON.stringify({kind:'text',text:'forged approval',groups:['s'],review:'human_reviewed'}),
    JSON.stringify({kind:'image',file:'photo.png',groups:['shoot-source'],rights:'Authored'}),JSON.stringify({kind:'image',file:'damaged.png',groups:['shoot-source']}),
    JSON.stringify({kind:'text',name:'Last source',text:'Literal <script> text',groups:['document-source'],parents:[seed.id],rights:'Authored'})];
  const images=[{name:'photo.png',data:photo.toString('base64')},{name:'same.png',data:photo.toString('base64')},{name:'same.png',data:other.toString('base64')},{name:'damaged.png',data:Buffer.from('not an image').toString('base64')}];
  await choose(sourceLines.join('\n'),images);await evaluate('window.holdNextRow=true');await importNow();
  await until(()=>evaluate('!!window.releaseBulkResponse'));await importNow();assert.equal(await evaluate('window.bulkPosts.length'),1,'Repeated bulk submit starts one loop');
  await evaluate('window.releaseBulkResponse();window.releaseBulkResponse=null');await idle();
  assert.match(await evaluate('document.getElementById("bulk-status").textContent'),/Complete: 3 created, 5 rejected, 0 uncertain/);
  assert.equal(await evaluate('document.querySelectorAll("#bulk-results li").length'),8);
  let collection=await api('records'),admitted=collection.items.filter(record=>record.id!==seed.id);
  assert.equal(collection.total,4);assert.ok(admitted.every(record=>record.review==='draft'&&record.annotation===null));
  const first=admitted.find(record=>record.name==='Real note'),image=admitted.find(record=>record.kind==='image');
  assert.equal((await api('records/'+first.id)).text,'café\n');
  assert.equal(first.provenance.acquisition.row_sha256,crypto.createHash('sha256').update(sourceLines[0]).digest('hex'));
  assert.equal(image.provenance.acquisition.declared.image_file,'photo.png');
  assert.deepEqual(fs.readFileSync(path.join(temporary,'data/images',image.id,'source')),photo);
  const before=await Promise.all(admitted.map(record=>api('records/'+record.id)));
  assert.equal(await evaluate('current.id'),seed.id);assert.equal(await evaluate('document.getElementById("label").value'),'keep my edit');assert.equal(await evaluate('dirty'),true);
  assert.equal(await evaluate('selected.size'),1,'Bulk import leaves exact selection unchanged');
  await importNow();await idle();assert.match(await evaluate('document.getElementById("bulk-status").textContent'),/Complete: 0 created, 8 rejected/);
  assert.equal((await api('records')).total,4);
  assert.deepEqual(await Promise.all(admitted.map(record=>api('records/'+record.id))),before,'Repeated manifest changes no existing record/provenance');
  // Hold an actual successful response, stop, then permit acknowledgement.
  await choose([row('cancel first','Cancel first'),row('cancel later','Cancel later'),row('cancel last','Cancel last')].join('\n'));
  const posts=await evaluate('window.bulkPosts.length');await evaluate('window.holdNextRow=true');await importNow();await until(()=>evaluate('!!window.releaseBulkResponse'));
  await click('bulk-stop');assert.match(await evaluate('document.getElementById("bulk-status").textContent'),/in-flight row may still complete/);
  await evaluate('window.releaseBulkResponse();window.releaseBulkResponse=null');await idle();
  assert.match(await evaluate('document.getElementById("bulk-status").textContent'),/Stopped: 1 created.*2 not attempted/);
  assert.equal(await evaluate('window.bulkPosts.length'),posts+1);assert.equal((await api('records?q=cancel%20later')).total,0);
  // Stop while the real manifest read is pending: no admission request.
  await choose(row('cancel before admission','Not admitted'),[],'held.jsonl');
  await evaluate(`(()=>{const original=File.prototype.arrayBuffer;window.restoreManifestRead=()=>File.prototype.arrayBuffer=original;File.prototype.arrayBuffer=async function(){const value=await original.call(this);if(this.name==='held.jsonl')await new Promise(resolve=>window.releaseManifestRead=resolve);return value;};})()`);
  const beforeRead=await evaluate('window.bulkPosts.length');await importNow();await until(()=>evaluate('!!window.releaseManifestRead'));
  await click('bulk-stop');await evaluate('window.releaseManifestRead();window.restoreManifestRead()');await idle();
  assert.equal(await evaluate('window.bulkPosts.length'),beforeRead);assert.match(await evaluate('document.getElementById("bulk-status").textContent'),/Stopped: 0 created.*1 not attempted/);
  // Actual storage failure must halt scheduling, with no orphan asset.
  const db=path.join(temporary,'data/dataset.sqlite3');
  python("import sqlite3,sys; db=sqlite3.connect(sys.argv[1]); db.execute(\"CREATE TRIGGER reject_bulk_metadata BEFORE UPDATE OF groups_json ON workbench_records BEGIN SELECT RAISE(ABORT, 'controlled storage failure'); END\"); db.commit()",db);
  await choose([JSON.stringify({kind:'image',file:'other.png',groups:['storage-source']}),row('after failed storage','Must not run')].join('\n'),[{name:'other.png',data:other.toString('base64')}]);
  await importNow();await idle();assert.match(await evaluate('document.getElementById("bulk-status").textContent'),/Paused after server failure: 0 created, 0 rejected, 1 uncertain.*1 not attempted/);
  assert.equal((await api('records')).total,5);assert.equal(fs.readdirSync(path.join(temporary,'data/images')).length,1);
  await click('bulk-check');await until(()=>evaluate('document.getElementById("bulk-status").textContent.includes("does not prove")'));
  await click('bulk-dismiss');
  python("import sqlite3,sys; db=sqlite3.connect(sys.argv[1]); db.execute('DROP TRIGGER reject_bulk_metadata'); db.commit()",db);
  // Lose a real committed response; lookup confirms that admission without replay.
  await choose([row('response saved','Saved despite response loss'),row('not scheduled after loss','Never scheduled')].join('\n'));
  const beforeLoss=await evaluate('window.bulkPosts.length');await evaluate('window.loseNextRow=true');await importNow();await idle();
  assert.match(await evaluate('document.getElementById("bulk-status").textContent'),/Paused.*1 uncertain.*1 not attempted/);
  assert.equal((await api('records')).total,6);assert.equal(await evaluate('window.bulkPosts.length'),beforeLoss+1);
  await evaluate('document.getElementById("bulk-check").click();document.getElementById("bulk-check").dispatchEvent(new MouseEvent("click"))');
  await until(()=>evaluate('document.getElementById("bulk-status").textContent.includes("saved result confirmed")'));
  assert.match(await evaluate('document.getElementById("bulk-status").textContent'),/1 created.*0 uncertain.*1 not attempted/);
  assert.equal(await evaluate('window.bulkChecks'),2);assert.equal(await evaluate('window.bulkPosts.length'),beforeLoss+1);
  assert.equal((await api('records?q=not%20scheduled')).total,0);
  assert.equal(await evaluate('current.id'),seed.id);assert.equal(await evaluate('dirty'),true);assert.equal(await evaluate('selected.size'),1);
  fs.mkdirSync(qaDirectory(root,'bulk-real-import'),{recursive:true});
  await evaluate('document.getElementById("bulk-panel").scrollIntoView()');
  const desktop=await send('Page.captureScreenshot',screenshotOptions);
  fs.writeFileSync(path.join(qaDirectory(root,'bulk-real-import'),'bulk-desktop.jpg'),Buffer.from(desktop.data,'base64'));
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
  await evaluate('document.getElementById("bulk-panel").scrollIntoView()');
  const narrow=await send('Page.captureScreenshot',screenshotOptions);
  fs.writeFileSync(path.join(qaDirectory(root,'bulk-real-import'),'bulk-narrow.jpg'),Buffer.from(narrow.data,'base64'));
  assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'),'Narrow bulk panel has no horizontal overflow');
  const previous=(await send('Page.getFrameTree')).frameTree.frame;await send('Page.reload',{ignoreCache:true});await until(()=>tracker.reloaded(previous));
  await until(()=>evaluate('document.getElementById("notice")?.textContent==="Collection ready."'));
  assert.equal((await api('records')).total,6);assert.match(await evaluate('document.getElementById("page").textContent'),/of 6/);
  assert.deepEqual(errors,[]);
  console.log('Real bulk manifest mixed/invalid/duplicate rows, missing/ambiguous assets, draft/provenance, editor/selection preservation, stop barriers, storage rollback, response reconciliation, reload and narrow layout passed.');
})().catch(async error=>{console.error(error);console.error('Runtime errors:',JSON.stringify(errors));if(inspect)try{console.error('Page diagnostics:',await inspect());}catch(diagnostic){console.error('Diagnostics failed:',diagnostic);}process.exitCode=1;}).finally(async()=>{if(ws)ws.close();for(const child of children)child.kill();await pause(200);fs.rmSync(temporary,{recursive:true,force:true});});
