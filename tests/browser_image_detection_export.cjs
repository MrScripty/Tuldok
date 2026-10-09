// Native Chromium gate: real local HTTP service, immutable download, no inference.
'use strict';
const crypto=require('node:crypto');
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn,execFileSync}=require('node:child_process');
const {qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const {waitForDebugger}=require('./browser_startup.cjs');
const {pageLoadTracker}=require('./browser_page_load.cjs');
const root=path.resolve(process.env.TULDOK_SOURCE_ROOT||path.join(__dirname,'..'));
const output=qaDirectory(root,'image-detection-export');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-detector-browser-')),children=[],errors=[];
const tracker=pageLoadTracker();
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn){for(let i=0;i<200;i++){if(await fn())return;await pause(75);}throw Error('Timed out');}
function launch(command,args,options={}){const child=spawn(command,args,options);children.push(child);return child;}
let ws,evaluate;
const network=new Map();let uiAction='initial load';
const recordNetwork=message=>{
  if(message.method==='Network.requestWillBeSent'){const q=message.params.request;const u=new URL(q.url);if(u.hostname!=='127.0.0.1')return;
    const mutating=q.method==='POST'&&!u.pathname.endsWith('/preview')&&!u.pathname.endsWith('/prepare');
    network.set(message.params.requestId,{request_id:message.params.requestId,method:q.method,path:u.pathname,role:mutating?'mutation':'observation',ui_action:uiAction,body_bytes:q.postData?Buffer.byteLength(q.postData):0,body_sha256:q.postData?crypto.createHash('sha256').update(q.postData).digest('hex'):null,status:null});
  }
  if(message.method==='Network.responseReceived'){const row=network.get(message.params.requestId);if(row)row.status=message.params.response.status;}
};
(async()=>{
  const server=launch('python3',['-u','tests/browser_image_detection_server.py','--port','0','--data',path.join(temporary,'data')],{cwd:root,stdio:['ignore','pipe','pipe']});
  let stdout='',stderr='';server.stdout.on('data',data=>stdout+=data);server.stderr.on('data',data=>stderr+=data);
  await until(()=>{if(server.exitCode!==null)throw Error(stderr);return /127\.0\.0\.1:(\d+)/.test(stdout);});
  const url='http://127.0.0.1:'+stdout.match(/127\.0\.0\.1:(\d+)/)[1];
  const browser=launch(process.env.BROWSER||'/usr/bin/chromium',['--headless','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--window-size=1400,950','--user-data-dir='+path.join(temporary,'browser'),'about:blank'],{stdio:['ignore','ignore','pipe'],env:{...process.env,XDG_CONFIG_HOME:temporary,XDG_CACHE_HOME:temporary}});
  let browserStderr='';browser.stderr.on('data',data=>browserStderr+=data);
  const port=await waitForDebugger(browser,path.join(temporary,'browser','DevToolsActivePort')).catch(error=>{throw Error(error.message+'\n'+browserStderr);});
  const tabs=await(await fetch('http://127.0.0.1:'+port+'/json')).json();
  ws=new WebSocket(tabs.find(tab=>tab.type==='page'&&tab.url==='about:blank').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  const pending=new Map();let id=0;
  ws.onmessage=event=>{const message=JSON.parse(event.data);tracker.observe(message);recordNetwork(message);if(message.id){const task=pending.get(message.id);pending.delete(message.id);message.error?task.reject(message.error):task.resolve(message.result);}if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails);};
  const send=(method,params={})=>new Promise((resolve,reject)=>{const request=++id;const timer=setTimeout(()=>{pending.delete(request);reject(Error('CDP timeout: '+method));},15000);pending.set(request,{resolve:value=>{clearTimeout(timer);resolve(value);},reject:error=>{clearTimeout(timer);reject(error);}});ws.send(JSON.stringify({id:request,method,params}));});
  evaluate=async expression=>{if(process.env.DETECTION_BROWSER_DEBUG)console.log(expression.slice(0,150));const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  const click=id=>{uiAction='rendered click '+id;return evaluate('document.getElementById('+JSON.stringify(id)+').click()');};
  const fill=(id,value)=>evaluate('(()=>{const e=document.getElementById('+JSON.stringify(id)+');e.value='+JSON.stringify(value)+';e.dispatchEvent(new Event("input",{bubbles:true}));e.dispatchEvent(new Event("change",{bubbles:true}));})()');
  const preview=async()=>{await click('preview-release');await until(()=>evaluate('!releaseBusy'));};
  await send('Page.enable');await send('Runtime.enable');await send('Network.enable');await send('Page.setLifecycleEventsEnabled',{enabled:true});
  await send('Page.navigate',{url:url+'/workbench'});
  await until(()=>evaluate('document.getElementById("notice")?.textContent==="Collection ready."'));
  // Ordinary native ZIP acquisition produces drafts with preserved fixed families.
  uiAction='rendered open unrelated record';await evaluate('document.querySelector("#records .record button").click()');
  await until(()=>evaluate('!document.getElementById("editor").hidden'));
  await fill('label','Unrelated dirty edit survives native import');
  const raw=fs.readFileSync(path.join(temporary,'native.zip')).toString('base64');
  uiAction='rendered native file-input submit';
  await evaluate(`(()=>{const dt=new DataTransfer();dt.items.add(new File([Uint8Array.from(atob(${JSON.stringify(raw)}),c=>c.charCodeAt(0))],'native.zip',{type:'application/zip'}));document.getElementById('native-detection-archive').files=dt.files;document.getElementById('native-detection-form').requestSubmit();})()`);
  await until(()=>evaluate('!detectionRunning && document.getElementById("native-detection-status").textContent.includes("6 created")'));
  assert.equal(await evaluate('document.getElementById("label").value'),'Unrelated dirty edit survives native import');
  const imported=(await(await fetch(url+'/api/workbench/records?')).json()).items.filter(r=>r.kind==='image');
  assert.equal(imported.length,6);assert.ok(imported.every(r=>r.review==='draft'&&r.rights_note==='unknown'));
  const foreground=imported.find(r=>r.annotation.boxes.some(b=>!Number.isInteger(b.x))).annotation.boxes[0].label;
  const chosen=imported.filter(r=>r.annotation.boxes.every(b=>b.label===foreground));assert.equal(chosen.length,5);
  const selectionExpression=`for(const row of page.items.filter(r=>r.kind==='image'&&r.annotation.boxes.every(b=>b.label===${JSON.stringify(foreground)})))document.querySelector('input[aria-label="Select '+row.name+'"]')?.click()`;
  const openRendered=async row=>{uiAction='rendered open '+row.id;await evaluate(`(()=>{const e=[...document.querySelectorAll('#records .record')].find(e=>e.querySelector('input')?.getAttribute('aria-label')===${JSON.stringify('Select '+row.name)});if(!e)throw Error('Rendered record absent');e.querySelector('button').click();})()`);await until(()=>evaluate('current?.id==='+JSON.stringify(row.id)));};
  // Explicitly discard the unrelated edit before entering human review.
  const discardImport=click('reload');await pause(100);await send('Page.handleJavaScriptDialog',{accept:true});await discardImport;await until(()=>evaluate('!dirty && !document.getElementById("editor").dataset.busy'));
  for(const row of chosen){
    await openRendered(row);
    await until(()=>evaluate('current?.id==='+JSON.stringify(row.id)));
    await fill('record-review','human_reviewed');uiAction='rendered explicit review/save '+row.id;await evaluate('document.getElementById("editor").requestSubmit()');
    await until(()=>evaluate('!dirty && current.review==="human_reviewed" && !document.getElementById("editor").dataset.busy'));
  }
  await evaluate('document.getElementById("filters").requestSubmit()');await until(()=>evaluate('!document.getElementById("filters").dataset.busy'));
  await evaluate(selectionExpression);
  assert.equal(await evaluate('selected.size'),5);
  await fill('release-format','image_detection_v1');await preview();
  assert.ok((await evaluate('document.getElementById("release-preview").textContent')).includes('integer pixel edges'));
  assert.equal(await evaluate('document.getElementById("freeze-release").disabled'),true);
  const fractional=imported.find(r=>r.annotation.boxes.some(b=>!Number.isInteger(b.x)));
  await openRendered(fractional);await until(()=>evaluate('current?.id==='+JSON.stringify(fractional.id)));
  await evaluate('document.querySelector("#targets button").click()');
  await fill('label',fractional.annotation.boxes[0].label);
  for(const [id,value] of Object.entries({'box-x':15,'box-y':11,'box-width':1,'box-height':1}))await fill(id,value);
  await click('add-box');
  assert.equal(await evaluate('document.getElementById("record-review").value'),'draft','Editing geometry resets review');
  await fill('record-review','human_reviewed');uiAction='rendered explicit geometry correction review/save';await evaluate('document.getElementById("editor").requestSubmit()');
  await until(()=>evaluate('!dirty && current.review==="human_reviewed" && !document.getElementById("editor").dataset.busy'));
  await click('clear-selection');await until(()=>evaluate('!document.getElementById("clear-selection").disabled'));
  await evaluate(selectionExpression);
  assert.equal(await evaluate('document.getElementById("selection").textContent'),'5 selected');
  const pair=row=>({id:row.id,revision:row.revision,source_revision:row.source_revision});
  const pairs=()=>evaluate('([...selected.values()].map(({id,revision,source_revision})=>({id,revision,source_revision}))).sort((a,b)=>a.id.localeCompare(b.id))');
  const selectedPairs=await pairs();
  await fill('selection-name','Detection QA · exact reviewed revisions');uiAction='rendered save fixed selection';
  await evaluate('document.getElementById("save-selection-form").requestSubmit()');
  await until(()=>evaluate('!document.getElementById("save-selection-form").dataset.busy&&document.getElementById("saved-selection-status").textContent.startsWith("Saved “")'));
  const savedId=await evaluate('document.getElementById("saved-selection").value');assert.match(savedId,/^[a-f0-9]{32}$/);
  const saved=await(await fetch(url+'/api/workbench/selections/'+savedId)).json();assert.equal(saved.current,true);
  assert.deepEqual(saved.selection.items.map(pair).sort((a,b)=>a.id.localeCompare(b.id)),selectedPairs);
  fs.writeFileSync(path.join(output,'saved-fixed-selection.json'),JSON.stringify(saved,null,2)+'\n');
  assert.equal(await evaluate('releasePreview'),null);
  await click('clear-selection');await until(()=>evaluate('selected.size===0'));
  await click('load-selection');await until(()=>evaluate('!savedLoadBusy&&selected.size===5&&document.getElementById("saved-selection-status").textContent.startsWith("Opened “")'));
  assert.deepEqual(await pairs(),selectedPairs);
  const beforeFixedReload=(await send('Page.getFrameTree')).frameTree.frame;
  await send('Page.reload');await until(()=>tracker.reloaded(beforeFixedReload));
  await until(()=>evaluate('document.readyState==="complete"&&!savedLoadBusy&&selected.size===5&&document.getElementById("saved-selection-status").textContent.startsWith("Opened “")'));
  assert.deepEqual(await pairs(),selectedPairs);assert.equal(await evaluate('releasePreview'),null);
  assert.equal(await evaluate('document.getElementById("freeze-release").disabled'),true);
  await openRendered(fractional);
  const provenanceText=await evaluate('document.getElementById("record-provenance").textContent');
  const currentRow=(await(await fetch(url+'/api/workbench/records/'+fractional.id)).json());
  const upstream=currentRow.provenance.acquisition.declared.upstream;
  assert.equal(upstream.category_table[1].id,2);assert.equal(upstream.category_table[1].name,foreground);
  assert.deepEqual(upstream.annotation_category_ids,[2]);
  assert.ok(provenanceText.includes(JSON.stringify(upstream.category_table)));
  const acquisition=currentRow.provenance.acquisition;
  const sourceArchiveSha256=crypto.createHash('sha256').update(Buffer.from(raw,'base64')).digest('hex');
  assert.equal(acquisition.archive_sha256,sourceArchiveSha256);
  for(const digest of [acquisition.archive_sha256,acquisition.manifest_sha256,...Object.values(acquisition.coco_sha256)]){assert.match(digest,/^[a-f0-9]{64}$/);assert.ok(provenanceText.includes(digest));}

  await until(()=>evaluate('!document.getElementById("editor").hidden'));
  const savedLabel=await evaluate('document.getElementById("label").value');
  await fill('label','Unsaved annotation must survive');
  await fill('release-format','image_detection_v1');
  assert.equal(await evaluate('document.getElementById("detection-export-help").hidden'),false);
  assert.equal(await evaluate('document.getElementById("caption-export-help").hidden'),true);
  await preview();
  assert.equal(await evaluate('document.getElementById("freeze-release").disabled'),false);
  assert.equal(await evaluate('document.getElementById("label").value'),'Unsaved annotation must survive');
  assert.equal(await evaluate('document.getElementById("record-review").value'),'draft');
  const coverage=await evaluate('document.getElementById("release-preview").textContent');
  assert.ok(coverage.includes('<img src=x onerror=alert(1)>'));
  assert.ok(coverage.includes('train: 1 positive · 1 negative images'));
  assert.ok(coverage.includes('class index 0; positive presence 1'));
  assert.ok(coverage.includes('5 retained · 0 unavailable'));
  assert.ok(coverage.includes('not segmentation ground truth'));
  assert.equal(await evaluate('document.querySelectorAll("#release-preview img, #release-preview script").length'),0);
  // Format changes immediately revoke a preview and never change fixed selection/editor state.
  await fill('release-format','canonical_v1');
  assert.equal(await evaluate('document.getElementById("freeze-release").disabled'),true);
  await fill('release-format','image_detection_v1');
  const cancelled=click('reload');await pause(100);await send('Page.handleJavaScriptDialog',{accept:false});await cancelled;
  assert.equal(await evaluate('document.getElementById("label").value'),'Unsaved annotation must survive');
  const discard=click('reload');await pause(100);await send('Page.handleJavaScriptDialog',{accept:true});await discard;
  await until(()=>evaluate('document.getElementById("label").value==='+JSON.stringify(savedLabel)));
  await preview();
  // Repeated submits are fenced; the frozen selection is complete and hash-addressed.
  await evaluate('window.exportPosts=0;window.actualFetch=window.fetch;window.fetch=(u,o)=>{if(String(u).endsWith("/releases")&&o?.method==="POST")window.exportPosts++;return window.actualFetch(u,o);};document.getElementById("release-form").requestSubmit();document.getElementById("release-form").requestSubmit();');
  await until(()=>evaluate('!!document.querySelector("#release-result a")'));
  assert.equal(await evaluate('window.exportPosts'),1);
  assert.ok((await evaluate('document.getElementById("notice").textContent')).includes('export warnings'));
  const download=await evaluate('document.querySelector("#release-result a").href');
  const archive=await fetch(download);assert.equal(archive.status,200);
  const zipPath=path.join(output,'detection.zip');fs.writeFileSync(zipPath,Buffer.from(await archive.arrayBuffer()));
  const readerPython=process.env.INSTRUCTION_CONSUMER_PYTHON||'python3';
  const expectedPairs=path.join(temporary,'expected-pairs.json');fs.writeFileSync(expectedPairs,JSON.stringify(selectedPairs));
  const frozenSha256=crypto.createHash('sha256').update(fs.readFileSync(zipPath)).digest('hex');
  execFileSync(readerPython,['-c',`import json,zipfile; z=zipfile.ZipFile(${JSON.stringify(zipPath)}); m=json.loads(z.read('manifest.json')); assert sorted([{k:r[k] for k in ('id','revision','source_revision')} for r in m['records']],key=lambda r:r['id'])==json.load(open(${JSON.stringify(expectedPairs)})); assert len(m['records'])==5; assert m['native_category_evidence']=={'retained':5,'unavailable':0,'not_native':0}
for r in m['records']:
 u=r['provenance']['acquisition']['declared']['upstream']; assert u['category_table'][1]['id']==2; assert u['category_table'][1]['name']==m['foreground_label']; assert u['annotation_category_ids']==([2] if r['annotation']['boxes'] else []); assert r['split']==r['source_split']
`],{cwd:root,timeout:30000});
  execFileSync(readerPython,['tests/check_image_detection_reader.py','--archive',zipPath,'--output',path.join(output,'reader')],{cwd:root,timeout:60000,stdio:'inherit'});
  const readerReport=JSON.parse(fs.readFileSync(path.join(output,'reader','reader-report.json')));assert.equal(readerReport.reader_records,5);assert.equal(readerReport.training_executed,false);assert.equal(readerReport.release_sha256,frozenSha256);assert.ok(download.includes(frozenSha256));
  // A later source revision invalidates an otherwise unchanged preview at publication.
  const row=(await(await fetch(url+'/api/workbench/records?')).json()).items.find(r=>r.id===fractional.id);
  uiAction='test-only external stale revision mutation (not rendered human review)';
  const changed=await fetch(url+'/api/workbench/records/'+row.id,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:row.revision,source_revision:row.source_revision,task:row.task,annotation:row.annotation,groups:row.groups,review:'human_reviewed'})});
  assert.equal(changed.status,200);
  await evaluate('document.getElementById("release-form").requestSubmit()');
  await until(()=>evaluate('document.getElementById("release-preview-status").textContent.includes("Selection changed")'));
  assert.equal(await evaluate('document.getElementById("freeze-release").disabled'),true);
  // Re-selecting current rows is explicit; a filter alone does not refresh selected revisions.
  await evaluate('document.getElementById("filters").requestSubmit()');await until(()=>evaluate('!document.getElementById("filters").dataset.busy'));
  await click('clear-selection');await until(()=>evaluate('!document.getElementById("clear-selection").disabled')); await evaluate(selectionExpression);await preview();
  assert.equal(await evaluate('document.getElementById("freeze-release").disabled'),false);
  await evaluate('document.getElementById("release-form").scrollIntoView()');
  await until(()=>evaluate('document.getElementById("release-format").getBoundingClientRect().top>=0&&document.getElementById("release-format").getBoundingClientRect().bottom<innerHeight'));
  fs.writeFileSync(path.join(output,'detection-desktop.jpg'),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
  await evaluate('document.getElementById("release-form").scrollIntoView()');
  await until(()=>evaluate('document.getElementById("release-format").getBoundingClientRect().top>=0&&document.getElementById("release-format").getBoundingClientRect().bottom<innerHeight'));
  assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth'),true);
  fs.writeFileSync(path.join(output,'detection-narrow.jpg'),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));
  await click('load-selection');await until(()=>evaluate('!savedLoadBusy&&document.getElementById("saved-selection-issues").children.length>0'));
  assert.deepEqual(await pairs(),selectedPairs);await preview();
  assert.equal(await evaluate('releasePreview.eligible'),false);
  const old=(await send('Page.getFrameTree')).frameTree.frame;
  await send('Page.reload');await until(()=>tracker.reloaded(old));
  await until(()=>evaluate('document.readyState==="complete"&&!savedLoadBusy&&selected.size===5&&document.getElementById("saved-selection-issues").children.length>0'));
  assert.deepEqual(await pairs(),selectedPairs);
  assert.equal(await evaluate('document.getElementById("selection").textContent'),'5 selected');
  assert.equal(await evaluate('document.getElementById("freeze-release").disabled'),true);
  assert.equal(await evaluate('document.getElementById("release-format").value'),'canonical_v1');
  const again=await fetch(download);assert.deepEqual(Buffer.from(await again.arrayBuffer()),fs.readFileSync(zipPath),'Old release remains immutable after live edits/reload');
  assert.deepEqual(errors,[]);
  const finalRows=(await(await fetch(url+'/api/workbench/records?')).json()).items;
  const unselected=finalRows.find(r=>imported.some(before=>before.id===r.id)&&!chosen.some(before=>before.id===r.id));
  assert.equal(unselected.review,'draft');assert.equal(unselected.rights_note,'unknown');
  const sourceSnapshot=JSON.parse(execFileSync(readerPython,['-c','import json;from scripts.qualify_text_classification_local import source_snapshot;print(json.dumps(source_snapshot()))'],{cwd:root,encoding:'utf8'}));
  const ledger=[...network.values()];assert.ok(ledger.some(r=>r.path==='/api/workbench/releases'&&r.status===201));
  fs.writeFileSync(path.join(output,'session.json'),JSON.stringify({candidate_head:sourceSnapshot.head,candidate_tree:execFileSync('git',['write-tree'],{cwd:root,encoding:'utf8'}).trim(),source_snapshot_sha256:sourceSnapshot.sha256,source_snapshot_files:Object.keys(sourceSnapshot.files).length,frozen_url:download,release_sha256:frozenSha256,selected_pairs:selectedPairs,saved_selection_id:savedId,saved_selection_pairs:saved.selection.items.map(pair).sort((a,b)=>a.id.localeCompare(b.id)),unselected_draft_unknown_rights:{id:unselected.id,review:unselected.review,rights_note:unselected.rights_note},rendered_original_category_evidence:upstream,source_archive_sha256:sourceArchiveSha256,rendered_acquisition_hashes:{archive:acquisition.archive_sha256,manifest:acquisition.manifest_sha256,coco:acquisition.coco_sha256},basis:'Authored compatibility images/annotations; actual production HTTP and rendered controls. Automated review-state actions are not genuine human labels.',checks:['native original category2 retained independently of reader class0/presence1','imported drafts then explicit rendered review/save','fractional geometry refused then explicit correction','saved fixed set open/reload retains all five exact selected revision/source pairs, frozen manifest matches; stale saved pairs held and refused; unselected row draft/unknown rights','fresh proof/immutable hash download/dirty state/stale revisions/narrow/reload','actual pinned reader only'],network:ledger,network_scope:'Browser CDP requests only; Node archive reads are separate. One test-only external mutation exercises stale revisions.',external_test_mutations:[{path:'/api/workbench/records/'+row.id,status:changed.status,role:'test-only stale revision mutation, not rendered human review'}],mutating_requests:ledger.filter(r=>r.role==='mutation').length,errors,reader:readerReport,training_executed:false,UI_provisional:true},null,2)+'\n');
  console.log('Detection browser: exact coverage, safe labels, dirty-editor/cancel preservation, stale revisions, repeated submit, frozen download/reload and narrow layout passed.');
})().catch(async error=>{console.error(error);if(evaluate)try{console.error(await evaluate('document.body.innerText.slice(-12000)'));}catch{}process.exitCode=1;}).finally(async()=>{if(ws)ws.close();for(const child of children)child.kill();await pause(200);fs.rmSync(temporary,{recursive:true,force:true});});
