// Joined production UI/HTTP/SQLite journey. Retained actual + explicitly synthetic
// source bytes only; never executes a producer, model or training consumer.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn,spawnSync}=require('node:child_process');
const {pageLoadTracker}=require('./browser_page_load.cjs');
const {qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const root=path.resolve(process.env.TULDOK_SOURCE_ROOT||path.join(__dirname,'..'));
const report=qaDirectory(root,'trajectory-workflow'),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-trajectory-workflow-'));
const data=path.join(temporary,'data'),children=[],errors=[],tracker=pageLoadTracker();
const sha=raw=>crypto.createHash('sha256').update(raw).digest('hex'),pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const evidence={basis:'joined real local production UI/backend; retained actual v1 and explicitly source-derived synthetic v1, no producer/model execution',checks:[],network:[],observer_reads:[],app_lifecycle:[],scratch_data:data};
let ws,inspect,activeAction=null,base,server;
async function until(fn){for(let n=0;n<150;n++){const value=await fn();if(value)return value;await pause(100);}throw Error('Timed out');}
function launch(command,args,options={}){const child=spawn(command,args,options);children.push(child);return child;}
function python(code,...args){const result=spawnSync('python3',['-c',code,...args],{cwd:root,encoding:'utf8',timeout:30000});assert.equal(result.status,0,result.error?String(result.error):result.stderr);return result.stdout;}
function sourceLines(raw){const result=[];let first=0;for(let n=0;n<raw.length;n++)if(raw[n]===10){result.push(raw.subarray(first,n+1));first=n+1;}assert.equal(first,raw.length);return result;}
async function startApp(){
  const child=launch('python3',['-u','app.py','--port','0','--data',data],{cwd:root,stdio:['ignore','pipe','pipe']});
  let output='';child.stdout.on('data',chunk=>output+=chunk);
  const port=await until(()=>output.match(/127\.0\.0\.1:(\d+)/)?.[1]);
  evidence.app_lifecycle.push({event:'start',pid:child.pid,command:['python3','-u','app.py','--port','0','--data',data],origin:'http://127.0.0.1:'+port,data});
  return {child,origin:'http://127.0.0.1:'+port};
}
async function get(route){
  const response=await fetch(base+'/api/workbench/'+route),raw=Buffer.from(await response.arrayBuffer());
  evidence.observer_reads.push({method:'GET',route,status:response.status,bytes:raw.length,sha256:sha(raw)});
  assert.equal(response.status,200,raw.toString());return JSON.parse(raw);
}
(async()=>{
  const actualDir=path.join(root,'tests/fixtures/rheon_actual_fee7b4a');
  const actual={key:'actual',name:'Retained actual trajectory',run:fs.readFileSync(path.join(actualDir,'run.json')),frames:fs.readFileSync(path.join(actualDir,'frames.jsonl'))};
  const receipt=JSON.parse(fs.readFileSync(path.join(actualDir,'producer-receipt.json')));
  assert.equal(sha(actual.run),receipt.run_sha256);assert.equal(sha(actual.frames),receipt.frames_sha256);assert.equal(receipt.producer_commit,'fee7b4a139574f87b259796b1ba8698a41d31ac1');
  // Exactly the existing source-derived fixture; only the third run's declared
  // synthetic command gains a variant, leaving all raw frame bytes unchanged.
  python("import sys;from pathlib import Path;sys.path.insert(0,'tests');from test_sequences import fixture;p=Path(sys.argv[1]);run,frames=fixture();(p/'run.json').write_bytes(run);(p/'frames.jsonl').write_bytes(frames)",temporary);
  const synthetic={key:'synthetic',name:'Source-derived synthetic comparison',run:fs.readFileSync(path.join(temporary,'run.json')),frames:fs.readFileSync(path.join(temporary,'frames.jsonl'))};
  const variant=JSON.parse(synthetic.run);variant.provenance.command.push('synthetic-unselected-family-context');
  const relative={key:'synthetic_unselected',name:'Synthetic unselected family relative',run:Buffer.from(JSON.stringify(variant)),frames:synthetic.frames};
  const sources=[actual,synthetic,relative];
  assert.deepEqual(JSON.parse(sourceLines(actual.frames)[0]).fields,JSON.parse(sourceLines(synthetic.frames)[0]).fields);
  assert.deepEqual(JSON.parse(relative.run).config,JSON.parse(synthetic.run).config);assert.deepEqual(relative.frames,synthetic.frames);
  evidence.sources=sources.map(s=>({key:s.key,name:s.name,run_sha256:sha(s.run),frames_sha256:sha(s.frames),frames_bytes:s.frames.length,
    basis:s===actual?'retained recorded actual producer fee7b4a, not rerun':s===synthetic?'existing tests/test_sequences.py fixture() / tests/fixtures/rheon_source_derived.py, synthetic v1':'same synthetic v1 frames; manifest-only declared command variant',
    producer_commit:JSON.parse(s.run).provenance.source_commit}));
  evidence.synthetic_fixture_sha256=sha(fs.readFileSync(path.join(root,'tests/fixtures/rheon_source_derived.py')));
  evidence.actual_producer_receipt=receipt;
  ({child:server,origin:base}=await startApp());
  launch(process.env.BROWSER||'/usr/bin/chromium',['--headless','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--window-size=1400,950','--user-data-dir='+path.join(temporary,'browser'),'about:blank'],{stdio:['ignore','ignore','ignore'],env:{...process.env,XDG_CONFIG_HOME:temporary,XDG_CACHE_HOME:temporary}});
  const active=path.join(temporary,'browser','DevToolsActivePort'),debugPort=await until(()=>fs.existsSync(active)&&fs.readFileSync(active,'utf8').split('\n')[0]);
  const tabs=await(await fetch('http://127.0.0.1:'+debugPort+'/json')).json(),target=tabs.find(tab=>tab.type==='page'&&tab.url==='about:blank');assert.ok(target);
  ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  let id=0;const pending=new Map(),network=new Map();
  const send=(method,params={})=>new Promise((resolve,reject)=>{pending.set(++id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
  ws.onmessage=event=>{
    const message=JSON.parse(event.data);tracker.observe(message);
    if(message.id){const task=pending.get(message.id);pending.delete(message.id);message.error?task.reject(message.error):task.resolve(message.result);}
    if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails);
    if(message.method==='Page.javascriptDialogOpening')send('Page.handleJavaScriptDialog',{accept:true}).catch(error=>errors.push(error));
    if(message.method==='Network.requestWillBeSent'){
      const request=message.params.request,url=new URL(request.url);if(!url.pathname.startsWith('/api/'))return;
      const observation=request.method==='GET'||/^\/api\/workbench\/(?:sequence-(?:review|inspect)\/|releases\/preview$)/.test(url.pathname);
      const row={request_id:message.params.requestId,method:request.method,path:url.pathname+url.search,origin:url.origin,role:observation?'observation':'mutation',ui_action:activeAction};
      if(request.method==='POST'){row.body_bytes=Buffer.byteLength(request.postData||'');row.body_sha256=sha(Buffer.from(request.postData||''));row.body_available=typeof request.postData==='string';}
      evidence.network.push(row);network.set(row.request_id,row);
    }
    if(message.method==='Network.responseReceived'){const row=network.get(message.params.requestId);if(row)row.status=message.params.response.status;}
  };
  const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  inspect=()=>evaluate('JSON.stringify({url:location.href,notice:document.getElementById("notice")?.textContent,import:document.getElementById("sequence-import-status")?.textContent,current:current?.id,revision:current?.revision,dirty,editorBusy:document.getElementById("editor")?.dataset.busy,selected:[...selected.values()].map(({id,revision,source_revision})=>({id,revision,source_revision})),preview:releasePreview})');
  const fill=(name,value)=>evaluate(`(()=>{const e=document.getElementById(${JSON.stringify(name)});e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  const click=name=>evaluate(`document.getElementById(${JSON.stringify(name)}).click()`);
  const submit=name=>evaluate(`document.getElementById(${JSON.stringify(name)}).requestSubmit()`);
  const ui=async(name,action,settled)=>{assert.equal(activeAction,null);activeAction='UI '+name;try{await action();if(settled)await until(settled);}finally{activeAction=null;}};
  const pairs=()=>evaluate('[...selected.values()].map(({id,revision,source_revision})=>({id,revision,source_revision})).sort((a,b)=>a.id.localeCompare(b.id))');
  const pair=row=>({id:row.id,revision:row.revision,source_revision:row.source_revision});
  const idle=(row,revision)=>evaluate(`current?.id===${JSON.stringify(row.id)}&&current.revision===${revision}&&!dirty&&!document.getElementById('editor').dataset.busy`);
  const open=async row=>ui('collection open '+row.name,()=>evaluate(`document.querySelector(${JSON.stringify('input[aria-label="Select '+row.name+'"]')}).closest('.record').querySelector('button').click()`),()=>idle(row,row.revision));
  const choose=(name,filename,raw)=>evaluate(`(()=>{const dt=new DataTransfer();dt.items.add(new File([Uint8Array.from(atob(${JSON.stringify(raw.toString('base64'))}),c=>c.charCodeAt(0))],${JSON.stringify(filename)}));document.getElementById(${JSON.stringify(name)}).files=dt.files;})()`);
  const reloadDocument=async(restartURL)=>{
    const previous=(await send('Page.getFrameTree')).frameTree.frame;
    if(restartURL)await send('Page.navigate',{url:restartURL});else await send('Page.reload');
    await until(()=>tracker.reloaded(previous));await until(()=>evaluate('document.readyState==="complete"&&document.getElementById("notice")?.textContent==="Collection ready."&&!savedLoadBusy&&!curationQueryPending&&document.getElementById("saved-selection-status").textContent.startsWith("Opened “")'));
  };
  await send('Page.enable');await send('Page.setLifecycleEventsEnabled',{enabled:true});await send('Runtime.enable');await send('Network.enable',{maxPostDataSize:4*1024*1024});
  await send('Page.navigate',{url:base+'/workbench'});await until(()=>evaluate('document.readyState==="complete"&&document.getElementById("notice")?.textContent==="Collection ready."'));
  for(const source of sources){
    await choose('sequence-run','run.json',source.run);await choose('sequence-frames','frames.jsonl',source.frames);await fill('sequence-name',source.name);
    await ui('raw file import '+source.key,()=>submit('sequence-import-form'),()=>evaluate('!sequenceImportBusy&&document.getElementById("sequence-import-status").textContent.startsWith("Imported ")'));
    source.row=(await get('records?kind=sequence')).items.find(row=>row.name===source.name);assert.ok(source.row);
    assert.equal(source.row.review,'draft');assert.equal(source.row.annotation,null);assert.equal(source.row.revision,1);assert.equal(source.row.source_revision,1);assert.equal(source.row.rights_note,'unknown');
    assert.equal(source.row.sequence.run_sha256,sha(source.run));assert.equal(source.row.sequence.manifest.frames_sha256,sha(source.frames));
  }
  assert.equal(new Set(sources.map(s=>s.row.groups.find(g=>g.startsWith('initial-family:')))).size,1);assert.equal(new Set(sources.map(s=>s.row.content_hash)).size,3);
  evidence.checks.push('three complete original v1 pairs admitted through actual file-input form; draft/null targets/unknown rights; retained actual and explicitly synthetic identities, one unchanged constructor family');
  await open(actual.row);await fill('sequence-note','Human whole-trajectory QA note; source numbers and labels remain distinct.');
  const owner=()=>evaluate('JSON.stringify({id:current.id,revision:current.revision,dirty,editorEpoch,note:document.getElementById("sequence-note").value,review:document.getElementById("record-review").value,targets:sequenceTemporalRanges})');
  const beforeInspection=await owner();evidence.native_inspection=[];
  for(const field of ['velocity_x','pressure']){
    await fill('sequence-review-field',field);await fill('sequence-review-i',15);await fill('sequence-review-j',0);await fill('sequence-review-k',0);await fill('sequence-review-axis','z');
    await ui('native '+field+' inspection',()=>click('sequence-review-load'),()=>evaluate('sequenceReviewRequest===null&&sequenceReviewData!==null'));
    const native=await evaluate('sequenceReviewData'),manifest=JSON.parse(actual.run),frames=sourceLines(actual.frames);
    assert.equal(native.field.name,field);assert.deepEqual(native.field.shape,manifest.geometry.field_shapes[field]);assert.equal(native.field.dtype,manifest.field_types[field]);assert.equal(native.field.units,field==='pressure'?'Pa':'m/s');
    assert.deepEqual(native.field.location_offset,field==='pressure'?manifest.geometry.cell_offset:manifest.geometry.face_offsets.x);assert.equal(native.frames.length,9);
    for(let n=0;n<9;n++){
      const frame=JSON.parse(frames[n]);assert.equal(native.frames[n].metadata.time_s,frame.time_s);assert.equal(native.frames[n].metadata.sha256,sha(frames[n]));assert.deepEqual(native.frames[n].metadata.carrier_stamp,frame.carrier_stamp);assert.deepEqual(native.frames[n].metadata.liquid_stamp,frame.liquid_stamp);
      assert.equal(native.frames[n].value,field==='pressure'?frame.fields[field][15]:Math.fround(frame.fields[field][15]));
      assert.equal(native.frames[n].plane_values.length,manifest.geometry.field_shapes[field][0]*manifest.geometry.field_shapes[field][1]);
      if(n===0)assert.equal(native.frames[n].accepted_interval,null);else{assert.equal(native.frames[n].accepted_interval.start_frame,n-1);assert.equal(native.frames[n].accepted_interval.end_frame,n);}
    }
    evidence.native_inspection.push(native);await fill('sequence-review-frame',1);assert.equal(await owner(),beforeInspection);
  }
  assert.match(await evaluate('document.getElementById("sequence-review-details").textContent'),/last accepted interval/);
  await click('sequence-review-append');assert.match(await evaluate('document.getElementById("sequence-note").value'),/Native inspection: pressure/);
  evidence.checks.push('explicit native MAC f32 velocity and cell f64 pressure/time inspection checks all nine original anchors and interval semantics, retains dirty draft; explicit reference append remains a human draft');
  const add=async(label,first,last,rationale)=>{
    await fill('sequence-temporal-label',label);await fill('sequence-temporal-first',first);await fill('sequence-temporal-last',last);await fill('sequence-temporal-rationale',rationale);await click('sequence-temporal-add');
    assert.equal(await evaluate('sequenceTemporalPending'),false);
  };
  for(const source of [actual,synthetic]){
    if(source===synthetic){await open(source.row);await fill('sequence-note','Human review of a clearly synthetic source-derived compatibility fixture.');}
    await add('Human early '+source.key,0,1,'Human-defined early endpoint-state range; no inferred solver truth.');await add('Human late '+source.key,2,8,'Human-defined later appearance range; no interpolation or training-quality claim.');
    await ui('save draft labels '+source.key,()=>submit('editor'),()=>idle(source.row,2));source.drafted=await get('records/'+source.row.id);assert.equal(source.drafted.review,'draft');assert.equal(source.drafted.annotation.temporal_labels.origin,'human_defined_annotation');
    await ui('reopen draft labels '+source.key,()=>click('reload'),()=>idle(source.row,2));assert.deepEqual(await evaluate('sequenceTemporalRanges'),source.drafted.annotation.temporal_labels.ranges);
    await fill('record-review','human_reviewed');await ui('separate human review '+source.key,()=>submit('editor'),()=>idle(source.row,3));source.reviewed=await get('records/'+source.row.id);
    assert.equal(source.reviewed.review,'human_reviewed');assert.deepEqual(source.reviewed.sequence,source.row.sequence);assert.deepEqual(source.reviewed.provenance,source.row.provenance);assert.equal((await get('history/'+source.row.id)).length,3);
  }
  assert.equal((await get('records/'+relative.row.id)).review,'draft');
  evidence.checks.push('two source-separated trajectories: explicit range authoring → draft Save → deliberate reopen → separate human review; exact saved targets/provenance/history, unselected relative stays draft');
  await ui('checkbox exact reviewed selection',async()=>{for(const source of [actual,synthetic])await evaluate(`document.querySelector(${JSON.stringify('input[aria-label="Select '+source.name+'"]')}).click()`);});
  const selectedPairs=[pair(actual.reviewed),pair(synthetic.reviewed)].sort((a,b)=>a.id.localeCompare(b.id));assert.deepEqual(await pairs(),selectedPairs);
  await fill('selection-name','Whole trajectory QA · exact revisions');await ui('save fixed trajectory set',()=>submit('save-selection-form'),()=>evaluate('!document.getElementById("save-selection-form").dataset.busy&&document.getElementById("saved-selection-status").textContent.startsWith("Saved “")'));
  const savedId=await evaluate('document.getElementById("saved-selection").value');assert.match(savedId,/^[a-f0-9]{32}$/);
  const saved=await get('selections/'+savedId);assert.equal(saved.current,true);fs.writeFileSync(path.join(report,'saved-fixed-selection.json'),JSON.stringify(saved,null,2)+'\n');
  assert.deepEqual(saved.selection.items.map(pair).sort((a,b)=>a.id.localeCompare(b.id)),selectedPairs);assert.equal(await evaluate('releasePreview'),null);
  await fill('label-filter','Human early actual');await ui('filter collection only',()=>submit('filters'),()=>evaluate('!document.getElementById("filters").dataset.busy&&page.total===1'));
  await ui('clear transient selection',()=>click('clear-selection'),()=>evaluate('selected.size===0&&!document.getElementById("clear-selection").dataset.busy'));
  await ui('open exact set through filtered collection',()=>click('load-selection'),()=>evaluate('!savedLoadBusy&&selected.size===2&&document.getElementById("saved-selection-status").textContent.startsWith("Opened “")'));
  assert.deepEqual(await pairs(),selectedPairs);assert.equal(await evaluate('page.total'),1);assert.equal(await evaluate('document.getElementById("label-filter").value'),'Human early actual');assert.equal(await evaluate('releasePreview'),null);
  await reloadDocument();assert.deepEqual(await pairs(),selectedPairs);assert.equal(await evaluate('releasePreview'),null);assert.equal(await evaluate('document.getElementById("freeze-release").disabled'),true);
  evidence.checks.push('rendered checkbox selection/save fixed set; filtered collection hides a selected member without changing exact pairs; clear/open and real complete-document reload preserve fixed membership and retire release proof');
  await fill('release-format','canonical_v1');await fill('train',50);await fill('validation',0);await fill('test',50);
  await ui('refuse family train/test split',()=>click('preview-release'),()=>evaluate('!releaseBusy&&releasePreview!==null'));
  const blocked=await evaluate('releasePreview');assert.equal(blocked.eligible,false);assert.ok(blocked.blockers.some(b=>/Too few independent/.test(b.message)));assert.equal(await evaluate('document.getElementById("freeze-release").disabled'),true);evidence.impossible_family_preview=blocked;
  await fill('train',100);await fill('test',0);assert.equal(await evaluate('releasePreview'),null);
  await ui('fresh train-only whole-family preview',()=>click('preview-release'),()=>evaluate('!releaseBusy&&releasePreview?.eligible===true'));
  const preview=await evaluate('releasePreview');assert.equal(preview.selected_count,2);assert.equal(preview.lineage.length,1);assert.deepEqual(new Set(preview.lineage[0].member_ids),new Set(sources.map(s=>s.row.id)));assert.deepEqual(new Set(preview.lineage[0].selected_ids),new Set(selectedPairs.map(p=>p.id)));evidence.eligible_preview=preview;
  await ui('freeze reviewed whole trajectories',()=>submit('release-form'),()=>evaluate('!releaseBusy&&!!document.querySelector("#release-result a")'));
  const releaseURL=await evaluate('document.querySelector("#release-result a").href');evidence.release_notice=await evaluate('document.getElementById("notice").textContent');
  const response=await fetch(releaseURL);assert.equal(response.status,200);const frozen=Buffer.from(await response.arrayBuffer());const archive=path.join(report,'whole-family-labelled-release.zip');fs.writeFileSync(archive,frozen);evidence.release_sha256=sha(frozen);
  const originalFiles={};for(const source of [actual,synthetic]){const directory=source===actual?actualDir:temporary;originalFiles[source.row.id]={run_path:path.join(directory,'run.json'),frames_path:path.join(directory,'frames.jsonl'),record:source.reviewed};}
  const expectedFile=path.join(temporary,'expected-source-records.json');fs.writeFileSync(expectedFile,JSON.stringify(originalFiles));
  const check=JSON.parse(python("import sys,json,hashlib,zipfile,io;from pathlib import Path;z=zipfile.ZipFile(sys.argv[1]);sources=json.loads(Path(sys.argv[2]).read_text());m=json.loads(z.read('manifest.json'));rows=m['records'];assert len(rows)==2 and {r['id'] for r in rows}==set(sources);assert m['split_report']['independent_components']==1;assert [json.loads(line) for line in z.read('train/records.jsonl').splitlines()]==rows;assert not z.read('validation/records.jsonl') and not z.read('test/records.jsonl');assert all(r['kind']=='sequence' and r['split']=='train' and r['review']=='human_reviewed' for r in rows);\nfor r in rows:\n s=sources[r['id']];before=s['record'];assert all(r[k]==before[k] for k in ('revision','source_revision','annotation','sequence','provenance'));a=r['annotation']['temporal_labels'];assert a['origin']=='human_defined_annotation' and len(a['ranges'])==2;bundle=z.read(r['asset']);assert hashlib.sha256(bundle).hexdigest()==r['content_hash']==a['source']['content_hash'];b=zipfile.ZipFile(io.BytesIO(bundle));assert b.namelist()==['run.json','frames.jsonl'];run=Path(s['run_path']).read_bytes();raw=Path(s['frames_path']).read_bytes();assert b.read('run.json')==run and b.read('frames.jsonl')==raw;assert a['source']['run_sha256']==hashlib.sha256(run).hexdigest() and a['source']['frames_sha256']==hashlib.sha256(raw).hexdigest();lines=raw.splitlines(keepends=True);assert len(lines)==9;frames=[json.loads(line) for line in lines];\n for target in a['ranges']:\n  for key in ('start','end'):\n   n=target[key+'_frame'];e=target[key];f=frames[n];assert e['sha256']==hashlib.sha256(lines[n]).hexdigest() and all(e[k]==f[k] for k in ('frame','time_s','carrier_stamp','liquid_stamp'));assert e['sha256']==r['sequence']['frame_index'][n]['sha256']\n assert type(a['ranges'][0]['start']['time_s']) is float\nprint(json.dumps(dict(result='PASS',records=2,whole_frames_each=9,independent_components=1,train_only=True,raw_source_bytes_equal=True,human_targets_separate=True,source_endpoint_associations=True,constructor_time_float=True)))",archive,expectedFile));
  evidence.artifact_check=check;fs.writeFileSync(path.join(report,'artifact-check.json'),JSON.stringify(check,null,2)+'\n');
  evidence.native_consumer=JSON.parse(python("import sys,json;from pathlib import Path;sys.path.insert(0,'tests');from check_native_sequence_consumer import verify;print(json.dumps(verify(Path(sys.argv[1]),sys.argv[2],Path(sys.argv[3]),torch_probe=False)))",archive,sha(frozen),report));
  assert.equal(evidence.native_consumer.declared_family_context_members,3);
  evidence.checks.push('UI-created current release carries declared three-member family closure; actual NumPy reader compares every native field/frame byte, time/stamp and human coverage; three-frame NPZ reloads with allow_pickle=False, no model/training');
  evidence.checks.push('UI refuses train/test split of one initial family; new train-only preview includes unselected draft in three-member closure; two whole reviewed native trajectories export with exact raw files and aligned human targets, not eighteen frame examples');
  await evaluate('document.getElementById("release-preview").scrollIntoView()');fs.writeFileSync(path.join(report,'workflow-desktop.jpg'),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});await open(actual.reviewed);await evaluate('document.getElementById("sequence-temporal-list").scrollIntoView()');assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'));fs.writeFileSync(path.join(report,'workflow-narrow.jpg'),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));
  const firstOrigin=base,firstPid=server.pid,exited=new Promise(resolve=>server.once('exit',(code,signal)=>resolve({code,signal})));assert.equal(server.exitCode,null);assert.ok(server.kill('SIGTERM'));const exit=await exited;
  evidence.app_lifecycle.push({event:'exit',pid:firstPid,...exit,data});({child:server,origin:base}=await startApp());evidence.origin_changed=base!==firstOrigin;
  await reloadDocument(base+'/workbench#selection='+savedId);assert.deepEqual(await pairs(),selectedPairs);assert.equal(await evaluate('releasePreview'),null);
  for(const source of [actual,synthetic]){assert.deepEqual(await get('records/'+source.row.id),source.reviewed);assert.equal((await get('history/'+source.row.id)).length,3);}
  assert.deepEqual(await get('selections/'+savedId),saved);await open(actual.reviewed);
  await evaluate('document.querySelector("#sequence-temporal-list button").click()');await fill('sequence-temporal-label','Human revised actual after freeze');await click('sequence-temporal-add');assert.equal(await evaluate('document.getElementById("record-review").value'),'draft');
  await ui('save post-freeze human draft revision',()=>submit('editor'),()=>idle(actual.row,4));const edited=await get('records/'+actual.row.id);assert.equal(edited.review,'draft');assert.equal(edited.annotation.temporal_labels.ranges[0].label,'Human revised actual after freeze');assert.deepEqual(edited.sequence,actual.row.sequence);
  await ui('reopen original exact stale set',()=>click('load-selection'),()=>evaluate('!savedLoadBusy&&document.getElementById("saved-selection-issues").textContent.includes("stale")'));
  assert.deepEqual(await pairs(),selectedPairs);assert.equal(await evaluate('releasePreview'),null);assert.equal((await get('selections/'+savedId)).current,false);
  await ui('stale selected revision preview refusal',()=>click('preview-release'),()=>evaluate('!releaseBusy&&releasePreview!==null'));assert.equal(await evaluate('releasePreview.eligible'),false);assert.match(await evaluate('document.getElementById("release-preview").textContent'),/Selection changed/);assert.equal(await evaluate('document.getElementById("freeze-release").disabled'),true);
  const persisted=await fetch(base+new URL(releaseURL).pathname);assert.equal(persisted.status,200);assert.deepEqual(Buffer.from(await persisted.arrayBuffer()),frozen);
  evidence.reopened_reviewed_records=[actual.reviewed,synthetic.reviewed];evidence.after_freeze_draft=edited;evidence.exact_saved_pairs=selectedPairs;evidence.stale_preview=await evaluate('releasePreview');
  evidence.checks.push('owned app-only exit/restart with same scratch SQLite/source/release data and recorded origins; exact saved pairs, labels/review/history survive; later human edit creates draft4, original set retains reviewed3 and blocks fresh preview; restarted server serves identical frozen archive');
  const mutations=evidence.network.filter(row=>row.role==='mutation');assert.ok(mutations.length>0);
  for(const row of mutations){assert.equal(row.method,'POST');assert.ok(row.ui_action?.startsWith('UI '),JSON.stringify(row));assert.equal(row.body_available,true);assert.ok(row.body_bytes>0);assert.ok(row.status>=200&&row.status<300,JSON.stringify(row));assert.match(row.path,/^\/api\/workbench\/(?:sequence-import$|records\/[a-f0-9]{32}$|selections$|releases$)/);}
  assert.equal(mutations.filter(row=>row.path.endsWith('/sequence-import')).length,3);assert.equal(mutations.filter(row=>row.path.endsWith('/releases')).length,1);assert.equal(mutations.filter(row=>row.path.endsWith('/selections')).length,1);
  assert.deepEqual(errors,[]);evidence.errors=errors;evidence.mutating_requests=mutations.length;
  // Canonical transport warnings must not be misrepresented as image-size facts.
  assert.doesNotMatch(evidence.release_notice,/small-image warnings/,'All-sequence canonical release must describe its general export warnings accurately.');
  evidence.result='PASS';fs.writeFileSync(path.join(report,'session.json'),JSON.stringify(evidence,null,2)+'\n');
  console.log('Joined trajectory UI/backend PASS: original file import, native fields/time, human ranges/draft/reopen/separate review, exact saved selection/filter/CDP reload/app-only restart, family split refusal and whole raw+target export, post-freeze stale references/immutable release,390px. No producer/model/training/provider execution.');
})().catch(async error=>{console.error(error);evidence.result='FAIL';evidence.failure=String(error);evidence.errors=errors;if(inspect)try{evidence.diagnostics=await inspect();console.error(evidence.diagnostics);}catch{}fs.writeFileSync(path.join(report,'failed-session.json'),JSON.stringify(evidence,null,2)+'\n');process.exitCode=1;}).finally(async()=>{if(ws)ws.close();for(const child of children)if(child.exitCode===null&&child.signalCode===null)child.kill();await pause(200);fs.rmSync(temporary,{recursive:true,force:true});});
