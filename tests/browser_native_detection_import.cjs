// Real manifest files, HTTP admission, cancellation, persistence and Chromium.
'use strict';
const {qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn,spawnSync}=require('node:child_process'),crypto=require('node:crypto');
const {pageLoadTracker}=require('./browser_page_load.cjs');
const root=path.resolve(process.env.TULDOK_SOURCE_ROOT||path.resolve(__dirname,'..')),report=qaDirectory(root,'native-detection-import'),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-native-detection-browser-')),children=[];
const errors=[],tracker=pageLoadTracker(),pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
let ws,inspect;
async function until(fn){for(let i=0;i<150;i++){const value=await fn();if(value)return value;await pause(100);}throw Error('Timed out');}
function launch(command,args,options={}){const child=spawn(command,args,options);children.push(child);return child;}
function python(code,...args){const result=spawnSync('python3',['-c',code,...args],{cwd:root,encoding:'utf8'});assert.equal(result.status,0,result.stderr);return result.stdout;}
(async()=>{
  python("import sys; from pathlib import Path; sys.path.insert(0,'tests'); from test_native_detection_import import native_fixture,rewrite; p=Path(sys.argv[1]); (p/'source.zip').write_bytes(native_fixture(p/'native-source')); (p/'stop.zip').write_bytes(native_fixture(p/'native-stop',count=2,name_prefix='Stop')); (p/'lost.zip').write_bytes(native_fixture(p/'native-lost',count=2,name_prefix='Lost'))",temporary);
  python("import sys,json,io,zipfile; from pathlib import Path; sys.path.insert(0,'tests'); from test_native_detection_import import native_fixture; p=Path(sys.argv[1]); raw=native_fixture(p/'native-linked',count=1,name_prefix='Linked family'); (p/'linked.zip').write_bytes(raw); z=zipfile.ZipFile(io.BytesIO(raw)); (p/'linked-origin.json').write_text(json.dumps(json.loads(z.read('manifest.json'))['records'][0]))",temporary);
  const server=launch('python3',['-u','app.py','--port','0','--data',path.join(temporary,'data')],{cwd:root,stdio:['ignore','pipe','pipe']});
  let output='';server.stdout.on('data',data=>output+=data);server.stderr.on('data',data=>{if(process.env.NATIVE_DETECTION_BROWSER_DEBUG)process.stderr.write(data);});
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
  ws.onmessage=event=>{const message=JSON.parse(event.data);tracker.observe(message);if(message.id){const task=pending.get(message.id);pending.delete(message.id);message.error?task.reject(message.error):task.resolve(message.result);}if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails);if(message.method==='Page.javascriptDialogOpening')send('Page.handleJavaScriptDialog',{accept:true}).catch(error=>errors.push(error));};
  const send=(method,params={})=>new Promise((resolve,reject)=>{pending.set(++id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
  const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  inspect=()=>evaluate('JSON.stringify({url:location.href,notice:document.getElementById("notice")?.textContent,status:document.getElementById("native-detection-status")?.textContent,results:document.getElementById("native-detection-results")?.textContent,body:document.body?.innerText.slice(0,1800)})');
  const click=id=>evaluate('document.getElementById('+JSON.stringify(id)+').click()');
  const fill=(id,value)=>evaluate(`(()=>{const e=document.getElementById(${JSON.stringify(id)});e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  const choose=name=>evaluate(`(()=>{const dt=new DataTransfer(),raw=Uint8Array.from(atob(${JSON.stringify(fs.readFileSync(path.join(temporary,name)).toString('base64'))}),c=>c.charCodeAt(0));dt.items.add(new File([raw],${JSON.stringify(name)},{type:'application/zip'}));document.getElementById('native-detection-archive').files=dt.files;})()`);
  const submit=()=>evaluate('document.getElementById("native-detection-form").requestSubmit()');
  const idle=()=>until(()=>evaluate('!detectionRunning'));
  await send('Page.enable');await send('Page.setLifecycleEventsEnabled',{enabled:true});await send('Runtime.enable');
  console.log('Native browser stage: navigation');
  await send('Page.navigate',{url:base+'/workbench'});
  await until(()=>evaluate('document.getElementById("notice")?.textContent==="Collection ready."'));
  await evaluate('document.getElementById("native-detection-import-panel").open=true');
  await evaluate('openRecord('+JSON.stringify(seed.id)+')');await fill('label','keep this unsaved target');
  await evaluate('document.querySelector(".record input").click()');
  await evaluate(`(()=>{const original=window.fetch;window.nativePosts=[];window.holdNative=false;window.loseNative=false;window.holdPreparation=false;window.holdNativeRefresh=false;window.fetch=async(...args)=>{const url=String(args[0]);if(url.endsWith('/native-detection-import/row')){window.nativePosts.push(JSON.parse(args[1].body));const response=await original(...args);if(window.loseNative){window.loseNative=false;throw Error('controlled lost acknowledgement after actual commit');}if(window.holdNative){window.holdNative=false;await new Promise(resolve=>window.releaseNative=resolve);}return response;}if(url.endsWith('/native-detection-import/prepare')&&window.holdPreparation){window.holdPreparation=false;const response=await original(...args);await new Promise(resolve=>window.releasePreparation=resolve);return response;}if(url.includes('/api/workbench/records?')&&window.holdNativeRefresh){window.holdNativeRefresh=false;const response=await original(...args);await new Promise(resolve=>window.releaseNativeRefresh=resolve);return response;}return original(...args);};})()`);
  console.log('Native browser stage: initial import');
  await choose('source.zip');await evaluate('window.holdNative=true');await submit();
  await until(()=>evaluate('!!window.releaseNative'));await submit();
  assert.equal(await evaluate('window.nativePosts.length'),1);
  await evaluate('document.getElementById("native-detection-archive").files=new DataTransfer().files;window.releaseNative();window.releaseNative=null');await idle();
  assert.match(await evaluate('document.getElementById("native-detection-status").textContent'),/Complete: 3 created, 0 rejected/);
  const imported=(await api('records')).items.filter(row=>row.id!==seed.id);
  assert.equal(imported.length,3);assert.ok(imported.every(row=>row.review==='draft'&&Array.isArray(row.annotation.boxes)&&row.width===8&&row.height===12));
  assert.equal(await evaluate('current.id'),seed.id);assert.equal(await evaluate('dirty'),true);
  assert.equal(await evaluate('document.getElementById("label").value'),'keep this unsaved target');assert.equal(await evaluate('selected.size'),1);
  await fill('query','nothing matches');await evaluate('document.getElementById("filters").requestSubmit()');
  await until(()=>evaluate('page.total===0'));assert.equal(await evaluate('selected.size'),1);
  console.log('Native browser stage: duplicates');
  await choose('source.zip');await submit();await idle();
  assert.match(await evaluate('document.getElementById("native-detection-status").textContent'),/Complete: 0 created, 3 rejected/);
  assert.deepEqual((await api('records')).items.filter(row=>row.id!==seed.id),imported);
  // Stop after the real commit; controls remain disabled through a held refresh.
  console.log('Native browser stage: stop');
  await choose('stop.zip');await evaluate('window.holdNative=true');await submit();await until(()=>evaluate('!!window.releaseNative'));
  const postsBeforeStop=await evaluate('window.nativePosts.length');await click('native-detection-stop');
  await evaluate('window.holdNativeRefresh=true;window.releaseNative();window.releaseNative=null');
  await until(()=>evaluate('!!window.releaseNativeRefresh'));
  assert.equal(await evaluate('document.getElementById("native-detection-start").disabled'),true);
  await submit();assert.equal(await evaluate('window.nativePosts.length'),postsBeforeStop);
  await evaluate('window.releaseNativeRefresh();window.releaseNativeRefresh=null');await idle();
  assert.match(await evaluate('document.getElementById("native-detection-status").textContent'),/Stopped: 1 created.*1 not attempted/);
  assert.equal((await api('records')).total,5);
  // Stop during read-only preparation admits nothing.
  console.log('Native browser stage: preparation stop');
  await choose('lost.zip');await evaluate('window.holdPreparation=true');await submit();await until(()=>evaluate('!!window.releasePreparation'));
  await click('native-detection-stop');await evaluate('window.releasePreparation();window.releasePreparation=null');await idle();
  assert.equal((await api('records')).total,5);
  // A real admitted row with a lost response is confirmed without replay.
  console.log('Native browser stage: response loss');
  await choose('lost.zip');await evaluate('window.loseNative=true');await submit();await idle();
  assert.match(await evaluate('document.getElementById("native-detection-status").textContent'),/Paused.*1 uncertain.*1 not attempted/);
  const uncertainPosts=await evaluate('window.nativePosts.length');await submit();assert.equal(await evaluate('window.nativePosts.length'),uncertainPosts);
  await click('native-detection-check');await idle();
  assert.match(await evaluate('document.getElementById("native-detection-status").textContent'),/saved admission confirmed: 1 created.*0 uncertain/);
  assert.equal((await api('records')).total,6);
  assert.equal(await evaluate('window.nativePosts.length'),uncertainPosts);
  // Explicitly end the unsaved-edit fixture before exercising human review.
  console.log('Native browser stage: review');
  await click('reload');await until(()=>evaluate('!dirty'));
  await fill('query','');await evaluate('document.getElementById("filters").requestSubmit()');await until(()=>evaluate('page.total===6'));
  await click('clear-selection');
  for(const row of imported){
    await evaluate('openRecord('+JSON.stringify(row.id)+')');
    await fill('record-review','human_reviewed');await evaluate('document.getElementById("editor").requestSubmit()');
    await until(()=>evaluate('current.review==="human_reviewed" && !dirty && page.items.find(row=>row.id===current.id)?.revision===current.revision'));
    const selector='input[aria-label='+JSON.stringify('Select '+row.name)+']';
    await evaluate('document.querySelector('+JSON.stringify(selector)+').click()');
  }
  assert.equal(await evaluate('selected.size'),3,'Use rendered selection controls');
  console.log('Native browser stage: selection');
  await fill('train',100);await fill('validation',0);await fill('test',0);
  await fill('selection-name','Native imported detection');await evaluate('document.getElementById("save-selection-form").requestSubmit()');
  await until(()=>evaluate('document.getElementById("saved-selection-status").textContent.startsWith("Saved “Native imported detection”")'));
  const savedId=await evaluate('document.getElementById("saved-selection").value');
  await click('clear-selection');await click('load-selection');await until(()=>evaluate('selected.size===3'));
  await click('preview-release');await until(()=>evaluate('!document.getElementById("freeze-release").disabled'));
  await evaluate('document.getElementById("release-form").requestSubmit()');await until(()=>evaluate('!!document.querySelector("#release-result a")'));
  const releaseUrl=await evaluate('document.querySelector("#release-result a").href'),release=await fetch(releaseUrl);
  assert.equal(release.status,200);fs.writeFileSync(path.join(temporary,'frozen.zip'),Buffer.from(await release.arrayBuffer()));
  python("import json,sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); m=json.loads(z.read('manifest.json')); assert len(m['records'])==3; assert all(r['task']=='image_detection' and r['review']=='human_reviewed' and r['annotation']==r['provenance']['acquisition']['declared']['upstream']['record']['annotation'] and (r['width'],r['height'])==(8,12) and r['provenance']['acquisition']['declared']['upstream']['original_status']=='unavailable' for r in m['records'])",path.join(temporary,'frozen.zip'));
  console.log('Native browser stage: reload/back');
  const previousFrame=(await send('Page.getFrameTree')).frameTree.frame;
  await send('Page.reload');await until(()=>tracker.reloaded(previousFrame));
  await until(()=>evaluate(`document.getElementById('saved-selection').value===${JSON.stringify(savedId)} && selected.size===3 && !savedLoadBusy`));
  assert.equal((await api('records')).total,6,'Reload must not replay imports');
  await evaluate('history.back()');await until(()=>evaluate('selected.size===0'));
  await evaluate('history.forward()');await until(()=>evaluate('selected.size===3 && !savedLoadBusy'));
  const nativeSelectedPairs=await evaluate('releaseBody().items');
  // Actual detection admission changes the corpus family proof, while saved
  // document revisions, dirty review note and fixed selection remain intact.
  console.log('Native browser stage: combined corpus family');
  const origin=JSON.parse(fs.readFileSync(path.join(temporary,'linked-origin.json'))),link='native-text-origin:'+crypto.createHash('sha256').update(origin.id).digest('hex'),documents=[];
  for(let index=0;index<3;index++){
    const row=await api('import',{kind:'text',name:'Combined corpus '+index,text:(`Combined document ${index}: café 🙂 山. Preserve source text and final newlines.\n`).repeat(4)+'\n',groups:[index===0?link:'combined-corpus-'+index],rights:'Authored compatibility fixture'});
    documents.push(await api('records/'+row.id,{...row,task:'text_corpus',annotation:{note:'Reviewed authored compatibility document.'},review:'human_reviewed'}));
  }
  await fill('task-filter','text_corpus');await evaluate('document.getElementById("filters").requestSubmit()');await until(()=>evaluate('page.total===3 && !document.getElementById("filters").dataset.busy'));
  await click('clear-selection');await click('select-page');assert.equal(await evaluate('selected.size'),3);
  await evaluate('openRecord('+JSON.stringify(documents[0].id)+')');
  await fill('corpus-note','Unsaved corpus note retained through detection import');
  await fill('release-format','text_corpus_v1');await fill('train',34);await fill('validation',33);await fill('test',33);
  await click('preview-release');await until(()=>evaluate('!releaseBusy && releasePreview?.eligible'));
  const corpusBody=await evaluate('releaseBody()'),oldProof=await evaluate('releasePreview.preview_token');
  await choose('linked.zip');await submit();await idle();
  assert.match(await evaluate('document.getElementById("native-detection-status").textContent'),/Complete: 1 created, 0 rejected/);
  assert.equal(await evaluate('current.id'),documents[0].id);assert.equal(await evaluate('dirty'),true);
  assert.equal(await evaluate('document.getElementById("corpus-note").value'),'Unsaved corpus note retained through detection import');
  assert.deepEqual(await evaluate('releaseBody().items'),corpusBody.items);
  const linked=(await api('records?task=image_detection')).items.find(row=>row.name===origin.id+'.png');assert.ok(linked);
  assert.equal(linked.review,'draft');assert.equal(linked.provenance.rights,'unknown');assert.equal(linked.source_split,'train');
  const stale=await fetch(base+'/api/workbench/releases',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...corpusBody,preview_token:oldProof})});
  assert.equal(stale.status,409);assert.match((await stale.json()).error,/Release preview changed/);
  if(await evaluate('!!releasePreview?.eligible')){
    await evaluate('document.getElementById("release-form").requestSubmit()');
    await until(()=>evaluate('!releaseBusy && document.getElementById("freeze-release").disabled'));
    assert.match(await evaluate('document.getElementById("release-preview-status").textContent'),/Release preview changed/);
  }
  await click('preview-release');await until(()=>evaluate('!releaseBusy && releasePreview?.eligible'));
  const freshProof=await evaluate('releasePreview.preview_token');assert.notEqual(freshProof,oldProof);
  assert.equal(await evaluate('releasePreview.assignments['+JSON.stringify(documents[0].id)+']'),'train');
  await evaluate('document.getElementById("release-form").requestSubmit()');await until(()=>evaluate('!releaseBusy && !!document.querySelector("#release-result a")'));
  const corpusUrl=await evaluate('document.querySelector("#release-result a").href'),corpusResponse=await fetch(corpusUrl);assert.equal(corpusResponse.status,200);
  fs.writeFileSync(path.join(report,'combined-corpus.zip'),Buffer.from(await corpusResponse.arrayBuffer()));
  fs.writeFileSync(path.join(temporary,'combined-documents.json'),JSON.stringify(documents));
  python("import sys,json,zipfile; from pathlib import Path; z=zipfile.ZipFile(sys.argv[1]); docs=json.loads(Path(sys.argv[2]).read_text()); m=json.loads(z.read('manifest.json')); assert m['format']=='text_corpus_v1' and len(m['records'])==3; assert sys.argv[3] in [r['id'] for family in m['protected_components'].values() for r in family]; assignment={r['id']:r['split'] for r in m['records']}; assert assignment[docs[0]['id']]=='train'; expected=lambda s: b''.join(r['text'].encode()+b'\\n\\n' for r in sorted(docs,key=lambda r:r['id']) if assignment[r['id']]==s); assert all(z.read(s+'.txt')==expected(s) for s in ('train','validation','test'))",path.join(report,'combined-corpus.zip'),path.join(temporary,'combined-documents.json'),linked.id);
  const originalRelease=await fetch(releaseUrl);assert.deepEqual(Buffer.from(await originalRelease.arrayBuffer()),fs.readFileSync(path.join(temporary,'frozen.zip')));
  const crossFeature={old_preview_status:stale.status,old_proof:oldProof,fresh_proof:freshProof,linked_detection_id:linked.id,corpus_selected_pairs:corpusBody.items,dirty_note_retained:true,raw_corpus_bytes_verified:true,old_native_release_unchanged:true};
  fs.copyFileSync(path.join(temporary,'linked.zip'),path.join(report,'linked-exporter-source.zip'));
  fs.copyFileSync(path.join(temporary,'frozen.zip'),path.join(report,'frozen.zip'));fs.copyFileSync(path.join(temporary,'source.zip'),path.join(report,'actual-exporter-source.zip'));
  await evaluate('document.getElementById("native-detection-import-panel").open=true;document.getElementById("native-detection-import-panel").scrollIntoView()');
  fs.writeFileSync(path.join(report,'native-detection-desktop.jpg'),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
  await evaluate('document.getElementById("native-detection-import-panel").scrollIntoView({block:"start"})');
  await until(()=>evaluate('document.getElementById("native-detection-import-panel").getBoundingClientRect().top<innerHeight && document.getElementById("native-detection-import-panel").getBoundingClientRect().bottom>0'));
  fs.writeFileSync(path.join(report,'native-detection-narrow.jpg'),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));
  assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'),'Native import panel must fit narrow layout');
  assert.deepEqual(errors,[]);
  const head=spawnSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'});assert.equal(head.status,0,head.stderr);
  const hash=file=>crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
  fs.writeFileSync(path.join(report,'session.json'),JSON.stringify({passed:true,source_head:head.stdout.trim(),fixture:'actual existing exporter',records:3,geometry:[8,12],initialReview:'draft',explicitReviewControl:'automated exercise, no semantic quality claim',reviewAndExport:true,sourceOriginal:'unavailable',runtimeErrors:errors,release_url:releaseUrl,archive_sha256:hash(path.join(report,'frozen.zip')),source_archive_sha256:hash(path.join(report,'actual-exporter-source.zip')),selected_pairs:nativeSelectedPairs,saved_selection_id:savedId,cross_feature:crossFeature},null,2));

  console.log('Native detection Chromium: actual ZIP imports, review/export roundtrip, duplicate preservation, Stop, delayed refresh, lost-response lookup, dirty editor/filter/selection preservation, reload/back and narrow layout passed.');
})().catch(async error=>{console.error(error);console.error('Runtime errors:',JSON.stringify(errors));if(inspect)try{console.error('Page diagnostics:',await inspect());}catch(diagnostic){console.error('Diagnostics failed:',diagnostic);}process.exitCode=1;}).finally(async()=>{if(ws)ws.close();for(const child of children)child.kill();await pause(200);fs.rmSync(temporary,{recursive:true,force:true});});
