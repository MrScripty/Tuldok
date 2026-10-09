// Recorded actual v1 fee7b4a + explicitly SYNTHETIC producer-v2 fixtures; real HTTP and Chromium.
'use strict';
const crypto=require('node:crypto');const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn,spawnSync}=require('node:child_process');
const {pageLoadTracker}=require('./browser_page_load.cjs');
const {qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const root=path.resolve(process.env.TULDOK_SOURCE_ROOT||path.join(__dirname,'..')),report=qaDirectory(root,'mixed-sequence-batch');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-sequence-browser-')),children=[];
const errors=[],tracker=pageLoadTracker(),pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
let ws;
async function until(fn){for(let i=0;i<150;i++){const result=await fn();if(result)return result;await pause(100);}throw Error('Timed out');}
function launch(command,args,options={}){const child=spawn(command,args,options);children.push(child);return child;}
(async()=>{
  const seeded=spawnSync('python3',['-c',"import sys; from pathlib import Path; sys.path.insert(0,'tests'); from fixtures.rheon_synthetic_v2 import fixture; p=Path(sys.argv[1]); run,frames,controls=fixture(); (p/'run.json').write_bytes(run); (p/'frames.jsonl').write_bytes(frames);(p/'controls.json').write_bytes(controls)",temporary],{cwd:root,encoding:'utf8'});
  assert.equal(seeded.status,0,seeded.stderr);
  const server=launch('python3',['-u','app.py','--port','0','--data',path.join(temporary,'data')],{cwd:root,stdio:['ignore','pipe','pipe']});
  let output='';server.stdout.on('data',chunk=>output+=chunk);
  const port=await until(()=>output.match(/127\.0\.0\.1:(\d+)/)?.[1]),base='http://127.0.0.1:'+port;
  const api=async(route,body)=>{const response=await fetch(base+'/api/workbench/'+route,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const result=await response.json();assert.ok(response.ok,JSON.stringify(result));return result;};
  const seed=await api('import',{kind:'text',text:'Independent editor stays intact.',name:'Existing editor',groups:['existing-source'],rights:'Authored'});
  launch(process.env.BROWSER||'/usr/bin/chromium',['--headless','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--window-size=1400,950','--user-data-dir='+path.join(temporary,'browser'),'about:blank'],{stdio:['ignore','ignore','ignore'],env:{...process.env,XDG_CONFIG_HOME:temporary,XDG_CACHE_HOME:temporary}});
  const active=path.join(temporary,'browser','DevToolsActivePort'),debugPort=await until(()=>fs.existsSync(active)&&fs.readFileSync(active,'utf8').split('\n')[0]);
  const tabs=await(await fetch('http://127.0.0.1:'+debugPort+'/json')).json(),target=tabs.find(tab=>tab.type==='page'&&tab.url==='about:blank');
  assert.ok(target);ws=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  let id=0;const pending=new Map();
  const send=(method,params={})=>new Promise((resolve,reject)=>{pending.set(++id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
  ws.onmessage=event=>{const message=JSON.parse(event.data);tracker.observe(message);if(message.id){const task=pending.get(message.id);pending.delete(message.id);message.error?task.reject(message.error):task.resolve(message.result);}if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails);if(message.method==='Page.javascriptDialogOpening')send('Page.handleJavaScriptDialog',{accept:true}).catch(error=>errors.push(error));};
  const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  const fill=(id,value)=>evaluate(`(()=>{const e=document.getElementById(${JSON.stringify(id)});e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  const choose=(id,name,contents)=>evaluate(`(()=>{const raw=Uint8Array.from(atob(${JSON.stringify((contents||fs.readFileSync(path.join(temporary,name))).toString('base64'))}),c=>c.charCodeAt(0)),dt=new DataTransfer();dt.items.add(new File([raw],${JSON.stringify(name)}));document.getElementById(${JSON.stringify(id)}).files=dt.files;})()`);
  await send('Page.enable');await send('Page.setLifecycleEventsEnabled',{enabled:true});await send('Runtime.enable');
  const blank=(await send('Page.getFrameTree')).frameTree.frame;await send('Page.navigate',{url:base+'/workbench'});await until(()=>tracker.reloaded(blank));await until(()=>evaluate('document.getElementById("notice")?.textContent==="Collection ready."'));
  const actual=path.join(root,'tests/fixtures/rheon_actual_fee7b4a');
  const source=(label,origin=temporary,changes={})=>{
    let run=fs.readFileSync(path.join(origin,'run.json')),value=JSON.parse(run);
    let controls=value.version===2?fs.readFileSync(path.join(origin,'controls.json')):null;
    if(changes.variant){if(controls){const c=JSON.parse(controls);const note=c.provenance.source_note;controls=Buffer.from(controls.toString('utf8').replace(JSON.stringify(note),JSON.stringify(note+' explicit synthetic variant '+changes.variant)));value.controls_bytes=controls.length;value.controls_sha256=sha(controls);}else value.provenance.command.push('explicit-synthetic-source-derived-'+changes.variant);run=Buffer.from(JSON.stringify(value)+'\n');}
    const entries=[{relative:`corpus/${label}/run.json`,data:run.toString('base64')},
      {relative:`corpus/${label}/frames.jsonl`,data:(changes.bad?Buffer.from('truncated\n'):fs.readFileSync(path.join(origin,'frames.jsonl'))).toString('base64')}];
    if(controls)entries.push({relative:`corpus/${label}/controls.json`,data:controls.toString('base64')});return entries;
  };
  const chooseFolder=entries=>evaluate(`(()=>{const selected=new DataTransfer();for(const entry of ${JSON.stringify(entries)}){const file=new File([Uint8Array.from(atob(entry.data),c=>c.charCodeAt(0))],entry.relative.split('/').at(-1));Object.defineProperty(file,'webkitRelativePath',{value:entry.relative});selected.items.add(file);}document.getElementById('sequence-batch-folder').files=selected.files;})()`);
  const submit=()=>evaluate('document.getElementById("sequence-batch-form").requestSubmit()');
  const idle=()=>until(()=>evaluate('!sequenceBatchRunning'));
  const selectedPairs=()=>evaluate('[...selected.values()].map(row=>[row.id,row.revision,row.source_revision]).sort((a,b)=>a[0].localeCompare(b[0]))');
  await evaluate('openRecord('+JSON.stringify(seed.id)+')');await fill('label','retain unsaved target');
  await evaluate('document.querySelector(".record input").click();document.getElementById("sequence-batch-panel").open=true');
  const fixedBefore=await selectedPairs();
  // Hold actual committed POST/GET/collection responses, without replacing admission.
  await evaluate(`(()=>{const original=window.fetch;window.batchPosts=0;window.batchChecks=0;window.holdBatch=false;window.dropBatch=false;window.holdBatchCheck=false;window.holdRecords=false;
    window.fetch=async(...args)=>{const url=String(args[0]);const response=await original(...args);
      if(url.endsWith('/sequence-import-item')){window.batchPosts++;if(window.holdBatch){window.holdBatch=false;await new Promise(resolve=>window.releaseBatch=resolve);}if(window.dropBatch){window.dropBatch=false;throw Error('Owned committed response lost');}}
      if(url.includes('/sequence-import-result/')){window.batchChecks++;if(window.holdBatchCheck){window.holdBatchCheck=false;await new Promise(resolve=>window.releaseBatchCheck=resolve);}}
      if(url.includes('/records?')&&window.holdRecords){window.holdRecords=false;await new Promise(resolve=>window.releaseRecords=resolve);}
      return response;};})()`);
  await chooseFolder([...source('a-actual',actual),...source('b-malformed',temporary,{bad:true}),...source('c-source-derived')]);
  await evaluate('window.holdBatch=true');await submit();await until(()=>evaluate('!!window.releaseBatch'));
  assert.equal((await api('records?kind=sequence')).total,1,'Held response belongs to real committed acquisition');
  await submit();assert.equal(await evaluate('batchPosts'),1,'Repeated controls cannot start another POST');
  await fill('sequence-batch-rights','changed disabled controls');await chooseFolder(source('changed-input'));
  await evaluate('window.releaseBatch();window.releaseBatch=null');await idle();
  assert.match(await evaluate('document.getElementById("sequence-batch-status").textContent'),/Complete: 2 created, 1 rejected, 0 uncertain/);
  assert.equal(await evaluate('batchPosts'),3);
  assert.equal(await evaluate('current.id'),seed.id);assert.equal(await evaluate('dirty'),true);
  assert.equal(await evaluate('document.getElementById("label").value'),'retain unsaved target');
  assert.deepEqual(await selectedPairs(),fixedBefore,'Exact selected revision pairs survive batch refresh');
  const imported=(await api('records?kind=sequence')).items;
  assert.equal(imported.length,2);
  for(const row of imported){assert.equal(row.review,'draft');assert.equal(row.annotation,null);assert.equal(row.provenance.rights,'unknown');assert.equal(row.sequence.frame_index.length,9);}
  const actualRow=imported.find(row=>row.name==='a-actual'),syntheticRow=imported.find(row=>row.name==='c-source-derived');
  assert.ok(actualRow&&syntheticRow);assert.equal(actualRow.provenance.sequence_acquisition.format,'tuldok_rheon_batch_v1');assert.equal(syntheticRow.provenance.sequence_acquisition.format,'tuldok_rheon_batch_v2');assert.equal(syntheticRow.provenance.sequence_acquisition.sequence_version,2);assert.equal(syntheticRow.provenance.sequence_acquisition.controls_sha256,sha(fs.readFileSync(path.join(temporary,'controls.json'))));assert.equal(actualRow.provenance.sequence_acquisition.item_index,1);assert.equal(syntheticRow.provenance.sequence_acquisition.item_index,3);
  assert.equal(actualRow.groups.find(group=>group.startsWith('initial-family:')),syntheticRow.groups.find(group=>group.startsWith('initial-family:')));
  const fixtureProof={};for(const name of ['run.json','frames.jsonl','controls.json']){const raw=fs.readFileSync(path.join(temporary,name));fs.writeFileSync(path.join(report,'synthetic-'+name),raw);fixtureProof[name]={bytes:raw.length,sha256:sha(raw)};}
  const bundles={};for(const row of [actualRow,syntheticRow]){const response=await fetch(base+'/api/workbench/asset/'+row.id);assert.equal(response.status,200);const raw=Buffer.from(await response.arrayBuffer());fs.writeFileSync(path.join(report,row.name+'-bundle.zip'),raw);bundles[row.id]={name:row.name,sha256:sha(raw)};}
  // A lost real committed response pauses. Its GET confirmation never replays/resumes.
  await fill('sequence-batch-rights','unknown');
  await chooseFolder([...source('d-lost',temporary,{variant:'lost'}),...source('e-not-attempted',temporary,{variant:'later'})]);
  await evaluate('window.dropBatch=true');await submit();await idle();
  assert.equal((await api('records?kind=sequence')).total,3);assert.equal(await evaluate('batchPosts'),4);
  assert.match(await evaluate('document.getElementById("sequence-batch-status").textContent'),/1 uncertain.*1 not attempted/);
  await submit();assert.equal(await evaluate('batchPosts'),4);
  await evaluate('document.getElementById("sequence-batch-check").click()');await until(()=>evaluate('!sequenceBatchRunning&&!sequenceBatchPending'));
  assert.equal(await evaluate('batchChecks'),1);assert.equal(await evaluate('batchPosts'),4);
  // Departure retains the in-flight marker, fences held POST and GET continuations.
  await chooseFolder([...source('f-departed',temporary,{variant:'departure'}),...source('g-not-attempted',temporary,{variant:'departure-later'})]);
  await evaluate('window.holdBatch=true');await submit();await until(()=>evaluate('!!window.releaseBatch'));
  await evaluate('window.dispatchEvent(new PageTransitionEvent("pagehide"));window.releaseBatch();window.releaseBatch=null');await pause(150);
  assert.equal(await evaluate('!!sequenceBatchPending'),true);assert.equal(await evaluate('batchPosts'),5);
  assert.equal((await api('records?kind=sequence')).total,4);
  await evaluate('window.holdBatchCheck=true;document.getElementById("sequence-batch-check").click()');await until(()=>evaluate('!!window.releaseBatchCheck'));
  await evaluate('window.dispatchEvent(new PageTransitionEvent("pagehide"));window.releaseBatchCheck();window.releaseBatchCheck=null');await pause(150);
  assert.equal(await evaluate('!!sequenceBatchPending'),true,'Departed saved-result check cannot confirm creation');
  await evaluate('document.getElementById("sequence-batch-check").click()');await until(()=>evaluate('!sequenceBatchRunning&&!sequenceBatchPending'));
  assert.equal(await evaluate('batchPosts'),5,'Departure/checks cannot schedule the later pair');
  // Actual shared collection refresh cannot publish after its batch departs.
  await chooseFolder(source('h-refresh',temporary,{variant:'refresh'}));
  await evaluate('window.holdRecords=true');await submit();await until(()=>evaluate('!!window.releaseRecords'));
  await evaluate('window.dispatchEvent(new PageTransitionEvent("pagehide"));document.getElementById("records").textContent="Departed refresh sentinel";window.releaseRecords();window.releaseRecords=null');await pause(150);
  assert.equal(await evaluate('document.getElementById("records").textContent'),'Departed refresh sentinel');
  assert.equal(await evaluate('curationQueryPending'),false,'Completed departed refresh retires diagnostics ownership');
  assert.equal(await evaluate('!!sequenceBatchPending'),false,'Known committed receipt is not uncertain because refresh departed');
  assert.equal((await api('records?kind=sequence')).total,5);
  // Resume the simulated departed page before human editor actions. A hidden
  // sequence editor deliberately refuses saves until its pageshow lifecycle.
  await evaluate('window.dispatchEvent(new PageTransitionEvent("pageshow",{persisted:true}));refresh()');
  // Existing human review, fixed selections and whole-trajectory export are reused.
  await evaluate('dirty=false');
  for(const row of [actualRow,syntheticRow]) {
    await evaluate('openRecord('+JSON.stringify(row.id)+')');
    assert.equal(await evaluate('current.id'),row.id,'Settled editor opens the requested trajectory');
    await fill('sequence-note','Inspected native MAC fields, time index and transport-only scope.');
    await fill('record-review','human_reviewed');await evaluate('document.getElementById("editor").requestSubmit()');
    // showRecord(saved) precedes the awaited collection refresh and finally.
    await until(()=>evaluate('current.id==='+JSON.stringify(row.id)+'&&current.review==="human_reviewed"&&!dirty&&current.revision===2&&!document.getElementById("editor").dataset.busy'));
  }
  await evaluate('document.getElementById("clear-selection").click()');await until(()=>evaluate('selected.size===0'));
  await evaluate('refresh()');
  for(const row of [actualRow,syntheticRow])await evaluate('document.querySelector('+JSON.stringify('input[aria-label="Select '+row.name+'"]')+').click()');
  const reviewedPairs=await selectedPairs();assert.equal(reviewedPairs.length,2);
  await fill('selection-name','Whole imported trajectories');await evaluate('document.getElementById("save-selection-form").requestSubmit()');
  await until(()=>evaluate('document.getElementById("saved-selection-status").textContent.startsWith("Saved “Whole imported trajectories”")'));
  const savedId=await evaluate('document.getElementById("saved-selection").value');assert.match(savedId,/^[a-f0-9]{32}$/);
  await evaluate('document.getElementById("clear-selection").click()');await until(()=>evaluate('selected.size===0'));
  await evaluate('document.getElementById("load-selection").click()');await until(()=>evaluate('selected.size===2'));
  assert.deepEqual(await selectedPairs(),reviewedPairs);
  await fill('train',100);await fill('validation',0);await fill('test',0);
  await evaluate('document.getElementById("preview-release").click()');await until(()=>evaluate('!document.getElementById("freeze-release").disabled'));
  await evaluate('document.getElementById("release-form").requestSubmit()');await until(()=>evaluate('!!document.querySelector("#release-result a")'));
  const frozen=await fetch(await evaluate('document.querySelector("#release-result a").href'));assert.equal(frozen.status,200);
  const frozenUrl=frozen.url,frozenBytes=Buffer.from(await frozen.arrayBuffer());fs.writeFileSync(path.join(temporary,'release.zip'),frozenBytes);fs.writeFileSync(path.join(report,'mixed-frozen-release.zip'),frozenBytes);
  const check=spawnSync('python3',['-c',"import sys,zipfile,json; from pathlib import Path; p=Path(sys.argv[1]); actual=Path(sys.argv[2]); z=zipfile.ZipFile(p/'release.zip'); m=json.loads(z.read('manifest.json')); assert len(m['records'])==2; rows=[json.loads(line) for line in z.read('train/records.jsonl').splitlines()]; assert len(rows)==2; a=next(row for row in m['records'] if row['name']=='a-actual'); import io; b=zipfile.ZipFile(io.BytesIO(z.read(a['asset']))); assert b.read('run.json')==(actual/'run.json').read_bytes(); assert b.read('frames.jsonl')==(actual/'frames.jsonl').read_bytes(); assert all(len(row['sequence']['frame_index'])==9 for row in m['records'])",temporary,actual],{cwd:root,encoding:'utf8'});
  assert.equal(check.status,0,check.stderr);
  const nested=spawnSync('python3',['-c',"import sys,json,zipfile,io;from pathlib import Path;p=Path(sys.argv[1]);z=zipfile.ZipFile(p/'mixed-frozen-release.zip');m=json.loads(z.read('manifest.json'));assert len(m['records'])==2;assert all(z.read(row['asset'])==(p/(row['name']+'-bundle.zip')).read_bytes() for row in m['records']);r=next(row for row in m['records'] if row['name']=='c-source-derived');b=zipfile.ZipFile(io.BytesIO(z.read(r['asset'])));assert len(b.namelist())==3;assert all(b.read(n)==(p/('synthetic-'+n)).read_bytes() for n in b.namelist())",report],{cwd:root,encoding:'utf8'});assert.equal(nested.status,0,nested.stderr);
  await evaluate('document.getElementById("sequence-batch-panel").scrollIntoView()');
  fs.writeFileSync(path.join(report,'sequence-batch-desktop.jpg'),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
  await evaluate('document.getElementById("sequence-batch-panel").scrollIntoView()');
  assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'),'Batch results fit 390px viewport');
  fs.writeFileSync(path.join(report,'sequence-batch-narrow.jpg'),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));
  const previous=(await send('Page.getFrameTree')).frameTree.frame;
  await send('Page.reload');await until(()=>tracker.reloaded(previous));
  await until(()=>evaluate('document.getElementById("notice")?.textContent==="Collection ready."'));
  assert.equal((await api('records?kind=sequence')).total,5);
  assert.equal(await evaluate('sequenceBatchPending'),null,'Reload has no durable batch recovery claim');
  assert.equal((await api('selections/'+savedId)).current,true);
  await evaluate('openRecord('+JSON.stringify(syntheticRow.id)+')');assert.equal(await evaluate('current.review'),'human_reviewed');
  await fill('sequence-probe-frame','8');await fill('sequence-probe-i','16');await fill('sequence-probe-j','7');await fill('sequence-probe-k','3');await evaluate('document.getElementById("sequence-probe-read").click()');await until(()=>evaluate('document.getElementById("sequence-probe-status").textContent.includes("Declared producer-v2 controls validated")'));
  const probe=JSON.parse(await evaluate('document.getElementById("sequence-probe-output").textContent'));assert.equal(probe.interval_controls_emitted.selected_interval.start_frame,7);assert.deepEqual(probe.field.shape,[17,8,4]);assert.equal(probe.field.dtype,'f32');
  const repeat=Buffer.from(await(await fetch(frozenUrl)).arrayBuffer());assert.equal(sha(repeat),sha(frozenBytes));
  fs.writeFileSync(path.join(report,'session.json'),JSON.stringify({result:'PASS',scope:'actual recorded v1 fee7b4a regression plus explicit synthetic v2 folder compatibility; no actual-v2 producer acceptance',fixtureProof,bundles,frozen_sha256:sha(frozenBytes),fresh_document_verified:tracker.reloaded(previous),probe,errors},null,2));
  assert.deepEqual(errors,[]);
  console.log('Mixed v1/synthetic-v2 folder Chromium: actual/source-derived pairs, partial malformed rejection, frozen controls, dirty editor/exact selection, committed lost-response GET recovery, departure/held POST/check/refresh fences, human review/fixed set/native release, reload and narrow JPEG85 layout passed.');
})().catch(error=>{console.error(error);console.error('Runtime errors:',JSON.stringify(errors));process.exitCode=1;}).finally(async()=>{if(ws)ws.close();for(const child of children)child.kill();await pause(200);fs.rmSync(temporary,{recursive:true,force:true});});
