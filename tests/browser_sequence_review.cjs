// Recorded actual producer bytes. Never invokes an exporter or a simulation.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn,spawnSync}=require('node:child_process');
const {pageLoadTracker}=require('./browser_page_load.cjs');
const {qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const root=path.resolve(process.env.TULDOK_SOURCE_ROOT||path.join(__dirname,'..')),source=path.join(root,'tests/fixtures/rheon_actual_fee7b4a');
const report=qaDirectory(root,'native-trajectory-review',process.env.TULDOK_TRAJECTORY_REVIEW_REPORT_ROOT||process.env.TULDOK_QA_OUTPUT_ROOT);
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-trajectory-review-browser-')),children=[],errors=[],tracker=pageLoadTracker();
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms)),sha=raw=>crypto.createHash('sha256').update(raw).digest('hex');
let ws,inspect;
async function until(fn){for(let i=0;i<150;i++){const result=await fn();if(result)return result;await pause(100);}throw Error('Timed out');}
function launch(command,args,options={}){const child=spawn(command,args,options);children.push(child);return child;}
function python(code,...args){const result=spawnSync('python3',['-c',code,...args],{cwd:root,encoding:'utf8',timeout:30000});assert.equal(result.status,0,result.stderr);return result.stdout;}
(async()=>{
  const run=fs.readFileSync(path.join(source,'run.json')),frames=fs.readFileSync(path.join(source,'frames.jsonl'));
  const manifest=JSON.parse(run),receipt=JSON.parse(fs.readFileSync(path.join(source,'producer-receipt.json')));
  assert.equal(sha(run),receipt.run_sha256);assert.equal(sha(frames),receipt.frames_sha256);
  assert.equal(manifest.provenance.source_commit,'fee7b4a139574f87b259796b1ba8698a41d31ac1');assert.equal(manifest.provenance.source_dirty,false);
  assert.equal(manifest.provenance.base_commit,'9cd4587a54befa61bdfddc8e35014bd3c34f02fb');
  assert.deepEqual(manifest.provenance.build_command,['cargo','build','--locked','--no-default-features','--example','dense3d_sequence']);
  assert.equal(manifest.frames_bytes,frames.length);assert.equal(manifest.frames_sha256,sha(frames));
  assert.equal(manifest.frame_count,9);assert.match(receipt.basis,/actual producer execution/);
  const evidence={basis:'recorded actual one-shot capped producer output; no exporter/simulation invoked by browser test',producer_receipt:receipt,manifest,run_sha256:sha(run),frames_sha256:sha(frames),checks:[]};
  // Source-derived comparison remains explicitly synthetic, with its placeholders.
  python("import sys,json; from pathlib import Path; sys.path.insert(0,'tests'); from test_sequences import fixture; p=Path(sys.argv[1]); run,frames=fixture(); (p/'synthetic-run.json').write_bytes(run); (p/'synthetic-frames.jsonl').write_bytes(frames)",temporary);
  const server=launch('python3',['-u','app.py','--port','0','--data',path.join(temporary,'data')],{cwd:root,stdio:['ignore','pipe','pipe']});
  let output='';server.stdout.on('data',chunk=>output+=chunk);
  const port=await until(()=>output.match(/127\.0\.0\.1:(\d+)/)?.[1]),base='http://127.0.0.1:'+port;
  const request=async(route,body)=>{const response=await fetch(base+'/api/workbench/'+route,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});return {status:response.status,result:await response.json()};};
  const api=async(route,body)=>{const response=await request(route,body);assert.ok(response.status<300,JSON.stringify(response));return response.result;};
  launch(process.env.BROWSER||'/usr/bin/chromium',['--headless','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--window-size=1400,950','--user-data-dir='+path.join(temporary,'browser'),'about:blank'],{stdio:['ignore','ignore','ignore'],env:{...process.env,XDG_CONFIG_HOME:temporary,XDG_CACHE_HOME:temporary}});
  const active=path.join(temporary,'browser','DevToolsActivePort'),debugPort=await until(()=>fs.existsSync(active)&&fs.readFileSync(active,'utf8').split('\n')[0]);
  const tabs=await(await fetch('http://127.0.0.1:'+debugPort+'/json')).json(),target=tabs.find(tab=>tab.type==='page'&&tab.url==='about:blank');assert.ok(target);
  ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  let id=0;const pending=new Map();const send=(method,params={})=>new Promise((resolve,reject)=>{pending.set(++id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
  ws.onmessage=event=>{const message=JSON.parse(event.data);tracker.observe(message);if(message.id){const task=pending.get(message.id);pending.delete(message.id);message.error?task.reject(message.error):task.resolve(message.result);}if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails);if(message.method==='Page.javascriptDialogOpening')send('Page.handleJavaScriptDialog',{accept:true}).catch(error=>errors.push(error));};
  const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  inspect=()=>evaluate('JSON.stringify({notice:document.getElementById("notice")?.textContent,status:document.getElementById("sequence-import-status")?.textContent,current:current?.id,dirty,selected:selected.size,preview:releasePreview})');
  const fill=(id,value)=>evaluate(`(()=>{const e=document.getElementById(${JSON.stringify(id)});e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  const choose=(id,name,contents)=>evaluate(`(()=>{const raw=Uint8Array.from(atob(${JSON.stringify(contents.toString('base64'))}),c=>c.charCodeAt(0)),dt=new DataTransfer();dt.items.add(new File([raw],${JSON.stringify(name)}));document.getElementById(${JSON.stringify(id)}).files=dt.files;})()`);
  await send('Page.enable');await send('Page.setLifecycleEventsEnabled',{enabled:true});await send('Runtime.enable');
  await send('Page.navigate',{url:base+'/workbench'});await until(()=>evaluate('document.getElementById("notice")?.textContent==="Collection ready."'));
  const actual=await api('sequence-import',{files:{'run.json':run.toString('base64'),'frames.jsonl':frames.toString('base64')},name:'Recorded actual native trajectory'});
  const decoded=frames.toString('utf8').trimEnd().split('\n').map(JSON.parse);
  const items=row=>[{id:row.id,revision:row.revision,source_revision:row.source_revision}],ratios={train:100,validation:0,test:0};
  assert.equal((await api('releases/preview',{items:items(actual),ratios,seed:42})).eligible,false);
  await evaluate(`openRecord(${JSON.stringify(actual.id)})`);
  assert.equal(await evaluate('document.getElementById("sequence-review").closest("form")'),null,'Viewer is outside annotation form');
  await evaluate('window.nativeReads=0;window.originalReviewFetch=window.fetch;window.fetch=(...args)=>{if(String(args[0]).includes("/sequence-review/"))nativeReads++;return originalReviewFetch(...args)}');
  const owner=()=>evaluate('JSON.stringify({dirty,editorEpoch,note:document.getElementById("sequence-note").value,review:document.getElementById("record-review").value,selected:[...selected],query:document.getElementById("query").value,filter:document.getElementById("kind").value})');
  await fill('sequence-note','Retain 🦋 independent human draft');await fill('query','native');await fill('kind','sequence');
  await evaluate('selected.set(current.id,current);selection(true)');const dirtyOwner=await owner();
  await fill('sequence-review-field','velocity_y');await fill('sequence-review-j','1');
  const load=async()=>{await evaluate('document.getElementById("sequence-review-load").click()');await until(()=>evaluate('sequenceReviewRequest===null'));assert.equal(await evaluate('document.getElementById("sequence-review-view").hidden'),false,await inspect());};
  await load();assert.equal(await owner(),dirtyOwner);assert.equal(await evaluate('nativeReads'),1);
  const data=await evaluate('sequenceReviewData');assert.equal(data.frames.length,9);assert.deepEqual(data.field.shape,[16,9,4]);
  for(let k=0;k<9;k++){
    await fill('sequence-review-frame',k);assert.match(await evaluate('document.getElementById("sequence-review-label").textContent'),new RegExp('Frame '+k));
    assert.equal(data.frames[k].value,Math.fround(decoded[k].fields.velocity_y[16]));
    assert.equal(await evaluate('document.querySelectorAll("#sequence-review-slice circle").length'),145);
  }
  assert.equal(await owner(),dirtyOwner);assert.equal(await evaluate('nativeReads'),1);assert.deepEqual(await api('records/'+actual.id),actual);assert.equal((await api('history/'+actual.id)).length,1);
  await fill('sequence-review-frame',0);await evaluate('document.getElementById("sequence-review-play").click()');await until(()=>evaluate('sequenceReviewFrame===8&&sequenceReviewTimer===null'));
  assert.equal(await evaluate('nativeReads'),1);assert.equal(await owner(),dirtyOwner);evidence.checks.push('real HTTP verified native f32 trace/144 sample plane; all nine frames and automatic terminal playback local; dirty note/editorEpoch/review/selection/query/filter/database/history retained');
  await evaluate('document.getElementById("sequence-review-append").click()');const appended=await evaluate('document.getElementById("sequence-note").value');assert.match(appended,/Retain 🦋 independent human draft\nNative inspection: velocity_y/);assert.match(appended,/frame 8/);assert.ok(appended.includes(actual.sequence.frame_index[8].sha256));assert.equal(await evaluate('dirty'),true);assert.equal(await evaluate('document.getElementById("record-review").value'),'draft');
  const appendEpoch=await evaluate('editorEpoch');await evaluate('document.getElementById("sequence-review-append").click()');assert.equal(await evaluate('editorEpoch'),appendEpoch);
  await evaluate('document.getElementById("editor").requestSubmit()');await until(()=>evaluate('!dirty&&current.revision===2'));
  const drafted=await api('records/'+actual.id);assert.equal(drafted.review,'draft');assert.equal(drafted.annotation.note,appended);assert.equal((await api('releases/preview',{items:items(drafted),ratios,seed:42})).eligible,false);
  await evaluate(`openRecord(${JSON.stringify(actual.id)})`);assert.equal(await evaluate('document.getElementById("sequence-note").value'),appended);assert.equal(await evaluate('sequenceReviewData'),null);
  await load();await fill('sequence-review-field','pressure');await fill('sequence-review-i','15');await load();await fill('sequence-review-frame',8);assert.match(await evaluate('document.getElementById("sequence-review-details").textContent'),/last accepted interval/);
  await fill('record-review','human_reviewed');await evaluate('document.getElementById("editor").requestSubmit()');await until(()=>evaluate('!dirty&&current.revision===3&&current.review==="human_reviewed"'));
  const reviewed=await api('records/'+actual.id);assert.deepEqual(reviewed.sequence,actual.sequence);assert.equal((await api('history/'+actual.id)).length,3);evidence.checks.push('explicit reference append preserves draft, duplicate no-op; draft save/reopen/export block, separate human review/history, pressure semantics retained');
  // Retained synthetic comparison shares constructor family. It is never actual producer evidence.
  const synthetic=await api('sequence-import',{files:{'run.json':fs.readFileSync(path.join(temporary,'synthetic-run.json')).toString('base64'),'frames.jsonl':fs.readFileSync(path.join(temporary,'synthetic-frames.jsonl')).toString('base64')},name:'Synthetic constructor-family comparison'});
  assert.equal(actual.groups[1],synthetic.groups[1]);
  const syntheticReviewed=await api('records/'+synthetic.id,{revision:1,source_revision:1,task:'sequence_transport',annotation:{note:'Synthetic grouping control only'},groups:synthetic.groups,review:'human_reviewed'});
  const split=await api('releases/preview',{items:[...items(reviewed),...items(syntheticReviewed)],ratios:{train:50,validation:50,test:0},seed:42});assert.equal(split.eligible,false);assert.ok(split.blockers.some(b=>/Too few independent/.test(b.message)));
  const single=await api('releases/preview',{items:items(reviewed),ratios,seed:42});assert.equal(single.eligible,true);
  assert.deepEqual(new Set(single.lineage[0].member_ids),new Set([actual.id,synthetic.id]));
  evidence.family_split_preview=split;evidence.single_selection_preview=single;evidence.checks.push('same initial-state family cannot split; unselected relative remains in existing preview closure');
  // Use the existing UI release owner for exact whole-bundle export.
  await fill('query','');await fill('kind','sequence');await evaluate('refresh()');await until(()=>evaluate('page.total===2'));
  await evaluate('document.getElementById("clear-selection").click()');await until(()=>evaluate('!document.getElementById("clear-selection").dataset.busy'));
  await evaluate('document.querySelector('+JSON.stringify('input[aria-label="Select '+actual.name+'"]')+').click()');await fill('train',100);await fill('validation',0);await fill('test',0);
  await evaluate('document.getElementById("preview-release").click()');await until(()=>evaluate('!document.getElementById("freeze-release").disabled'));await evaluate('document.getElementById("release-form").requestSubmit()');await until(()=>evaluate('!!document.querySelector("#release-result a")'));
  const frozen=Buffer.from(await(await fetch(await evaluate('document.querySelector("#release-result a").href'))).arrayBuffer());fs.writeFileSync(path.join(report,'whole-trajectory-release.zip'),frozen);
  const checked=JSON.parse(python("import sys,json,zipfile,hashlib,io; from pathlib import Path; z=zipfile.ZipFile(sys.argv[1]); m=json.loads(z.read('manifest.json')); assert len(m['records'])==1; r=m['records'][0]; assert r['kind']=='sequence' and r['split']=='train' and r['review']=='human_reviewed'; b=z.read(r['asset']); assert hashlib.sha256(b).hexdigest()==r['content_hash']==r['asset_sha256']; inner=zipfile.ZipFile(io.BytesIO(b)); p=Path(sys.argv[2]); assert inner.namelist()==['run.json','frames.jsonl']; assert inner.read('run.json')==(p/'run.json').read_bytes(); assert inner.read('frames.jsonl')==(p/'frames.jsonl').read_bytes(); assert len(r['sequence']['frame_index'])==9; assert m['split_report']['independent_components']==1; print(json.dumps(dict(result='PASS',byte_exact_whole_trajectory=True,independent_components=1,bundle_sha256=hashlib.sha256(b).hexdigest())))",path.join(report,'whole-trajectory-release.zip'),source));
  evidence.frozen_check=checked;evidence.release_sha256=sha(frozen);evidence.checks.push('existing selected UI preview/freeze/download: byte-exact original bundle, all nine frames, one independent split component; unselected constructor family closure separately proven in preview');
  await load();await fill('sequence-note','Dirty survives viewer lifecycle and failures');const laterOwner=await owner();
  // Real response held before client admission: invalidation and cancel must refuse publication.
  await evaluate('window.fetch=async(...args)=>{const r=await originalReviewFetch(...args);if(String(args[0]).includes("/sequence-review/")){nativeReads++;await new Promise(resolve=>window.releaseReviewRead=resolve)}return r};document.getElementById("sequence-review-load").click()');await until(()=>evaluate('typeof releaseReviewRead==="function"'));
  await fill('sequence-review-field','fraction');await evaluate('releaseReviewRead();delete window.releaseReviewRead');await pause(100);assert.equal(await evaluate('sequenceReviewData'),null);assert.equal(await owner(),laterOwner);
  await evaluate('document.getElementById("sequence-review-load").click()');await until(()=>evaluate('typeof releaseReviewRead==="function"'));await evaluate('document.getElementById("sequence-review-cancel").click();releaseReviewRead();delete window.releaseReviewRead');await pause(100);assert.equal(await evaluate('sequenceReviewData'),null);assert.equal(await owner(),laterOwner);
  await evaluate('window.fetch=(...args)=>String(args[0]).includes("/sequence-review/")?Promise.resolve(new Response(JSON.stringify({error:"Controlled HTTP refusal"}),{status:409})):originalReviewFetch(...args);document.getElementById("sequence-review-load").click()');await until(()=>evaluate('sequenceReviewRequest===null'));assert.match(await evaluate('document.getElementById("sequence-review-status").textContent'),/Controlled HTTP refusal/);assert.equal(await owner(),laterOwner);
  await evaluate('window.fetch=originalReviewFetch');await load();await evaluate('document.getElementById("sequence-review-play").click();window.dispatchEvent(new PageTransitionEvent("pagehide"));window.dispatchEvent(new PageTransitionEvent("pageshow",{persisted:true}))');assert.equal(await evaluate('sequenceReviewData'),null);assert.equal(await evaluate('sequenceReviewTimer'),null);
  // The shared save epoch retires old responses on owned-sequence departure.
  // Every draft/review/selection/filter owner remains otherwise unchanged.
  const departedOwner=JSON.parse(laterOwner);assert.deepEqual(JSON.parse(await owner()),{...departedOwner,editorEpoch:departedOwner.editorEpoch+1});await load();
  evidence.checks.push('actual held HTTP response fenced by input change/cancel; controlled HTTP refusal explicit retry; dispatched departure/restore events clear playback/projection, retire exactly one shared save epoch and retain every other draft owner; fresh explicit load');
  await evaluate('document.getElementById("sequence-review").scrollIntoView()');fs.writeFileSync(path.join(report,'trajectory-desktop.jpg'),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});await evaluate('document.getElementById("sequence-review-view").scrollIntoView()');assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'));fs.writeFileSync(path.join(report,'trajectory-narrow.jpg'),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));
  await fill('sequence-note',appended);await evaluate('document.getElementById("reload").click()');await until(()=>evaluate('!dirty'));
  const previous=(await send('Page.getFrameTree')).frameTree.frame;await send('Page.reload');await until(()=>tracker.reloaded(previous));await until(()=>evaluate('document.getElementById("notice")?.textContent==="Collection ready."'));await evaluate(`openRecord(${JSON.stringify(actual.id)})`);assert.equal(await evaluate('current.review'),'human_reviewed');assert.equal(await evaluate('sequenceReviewData'),null);await load();
  // Original synthetic-v2 eight controls in the real viewer; not an actual v2 packet.
  const v2files=JSON.parse(python("import sys,json,base64;sys.path.insert(0,'tests');from fixtures.rheon_synthetic_v2 import fixture;print(json.dumps({n:base64.b64encode(raw).decode() for n,raw in zip(('run.json','frames.jsonl','controls.json'),fixture())}))"));
  const v2row=await api('sequence-import',{files:v2files,name:'Explicit synthetic v2 controls'});await evaluate(`openRecord(${JSON.stringify(v2row.id)})`);await load();assert.equal(await evaluate('sequenceReviewData.frames[0].emitted_control'),null);await fill('sequence-review-frame',8);assert.equal(await evaluate('sequenceReviewData.frames[8].emitted_control.end_frame'),8);assert.match(await evaluate('document.getElementById("sequence-review-details").textContent'),/does not authenticate/);
  assert.equal(await evaluate('current.review'),'draft');assert.deepEqual(errors,[]);evidence.actual_record=reviewed;evidence.synthetic_v2_record=v2row;evidence.errors=errors;evidence.result='PASS';evidence.checks.push('390px no overflow; real CDP reload barrier, human review persists and viewer explicitly reloads; synthetic v2 constructor None/eight original controls/declared origin shown, no approval');
  fs.writeFileSync(path.join(report,'native-review-response.json'),JSON.stringify(data,null,2)+'\n');fs.writeFileSync(path.join(report,'session.json'),JSON.stringify(evidence,null,2)+'\n');
  console.log('Native trajectory Chromium PASS: actual HTTP/recorded native slices and trace, nine local frames/playback, draft append/save/reopen and separate human review, byte-exact family-safe whole release, input/cancel/error/restore/reload ownership, narrow display; separate synthetic v2 controls. No producer or training execution.');
})().catch(async error=>{console.error(error);if(inspect)try{console.error(await inspect());}catch{}process.exitCode=1;}).finally(async()=>{if(ws)ws.close();for(const child of children)child.kill();await pause(200);fs.rmSync(temporary,{recursive:true,force:true});});
