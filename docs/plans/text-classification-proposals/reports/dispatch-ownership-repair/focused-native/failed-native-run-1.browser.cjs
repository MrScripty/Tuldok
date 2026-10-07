// Native browser smoke test. No npm dependencies.
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process');
const root=process.env.TULDOK_SOURCE_ROOT||path.resolve(__dirname,'..'),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-text-classification-proposals-browser-')),children=[];
let ws, inspect;
const extraSockets=[];
const errors=[];
const {pageLoadTracker}=require('./browser_page_load.cjs');const pageLoads=pageLoadTracker();
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn){for(let i=0;i<150;i++){const value=await fn();if(value)return value;await pause(100);}throw Error('Timed out');}
function launch(command,args,options={}){const child=spawn(command,args,options);children.push(child);return child;}
(async()=>{
  const outputRoot=process.env.TULDOK_CLASSIFICATION_REPORT_ROOT||path.join(root,'test-results/text-classification-proposals');fs.mkdirSync(outputRoot,{recursive:true});
  const report=fs.mkdtempSync(path.join(outputRoot,'run-'));
  console.log('Text classification proposal evidence: '+report);
  const server=launch('python3',['-u','tests/browser_text_classification_proposals_server.py','--port','0','--data',path.join(temporary,'data')],{cwd:root,stdio:['ignore','pipe','pipe']});
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
  inspect=()=>evaluate('JSON.stringify({url:location.href,ready:document.readyState,notice:document.getElementById("notice")?.textContent,classificationStatus:document.getElementById("text-classification-proposal-status")?.textContent,classificationModels:document.getElementById("text-classification-proposal-model")?.options.length,scriptType:typeof refreshTextClassificationProposals,body:document.body?.innerText.slice(0,1500),viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,overflow:[...document.querySelectorAll("body *")].filter(e=>e.getBoundingClientRect().right>innerWidth || e.scrollWidth>e.clientWidth+1).map(e=>({tag:e.tagName,id:e.id,class:e.className,right:e.getBoundingClientRect().right,width:e.getBoundingClientRect().width})).slice(0,30)})');
  const click=id=>evaluate('document.getElementById('+JSON.stringify(id)+').click()');
  const fill=(id,value)=>evaluate('(()=>{const e=document.getElementById('+JSON.stringify(id)+');e.value='+JSON.stringify(value)+';e.dispatchEvent(new Event("input",{bubbles:true}));e.dispatchEvent(new Event("change",{bubbles:true}));})()');
  const base='http://127.0.0.1:'+port,ref=row=>({id:row.id,revision:row.revision,source_revision:row.source_revision});
  const request=async(path,body)=>{const r=await fetch(base+'/api/workbench/'+path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const data=await r.json();assert.ok(r.ok,JSON.stringify(data));return data;};
  const makeText=async(name,text)=>request('import',{kind:'text',name,text,groups:[name],rights:'Authored synthetic fixture'});
  const rows=[await makeText('Cancel source','Please cancel the café meeting 😀.\nExact source.'),await makeText('Other source','Please keep the appointment.')];
  const saved=await request('selections',{name:'Fixed text set',items:rows.map(ref)});
  const modelPort=output.match(/CLASSIFICATION_MODEL_PORT=(\d+)/)[1],labels=['cancel','keep','café 😀'];
  const prefix='text-classification-proposal-',v='textClassificationProposal';
  await send('Page.enable');await send('Runtime.enable');await send('Page.setLifecycleEventsEnabled',{enabled:true});
  await send('Page.navigate',{url:base+'/workbench'});await until(()=>evaluate('document.getElementById("notice")?.textContent === "Collection ready."'));
  await evaluate('refreshSavedSets('+JSON.stringify(saved.id)+')');await click('load-selection');await until(()=>evaluate('!savedLoadBusy && selected.size===2'));
  const fixed=await evaluate('releaseBody().items');
  const open=async id=>{await evaluate('openRecord('+JSON.stringify(id)+')');await until(()=>evaluate('current?.id==='+JSON.stringify(id)));};
  await open(rows[0].id);await evaluate('document.getElementById('+JSON.stringify(prefix+'panel')+').open=true');
  await fill(prefix+'url','http://127.0.0.1:'+modelPort+'/v1/');await click(prefix+'models');await until(()=>evaluate('document.getElementById('+JSON.stringify(prefix+'model')+').options.length===1'));
  await fill(prefix+'model','classification-fixture');await fill(prefix+'labels',JSON.stringify(labels));
  const start=async guidance=>{await fill(prefix+'guidance',guidance);await evaluate('document.getElementById('+JSON.stringify(prefix+'form')+').requestSubmit();document.getElementById('+JSON.stringify(prefix+'form')+').requestSubmit()');await until(()=>evaluate('!'+v+'Busy'));};
  const refresh=async()=>{await click(prefix+'refresh');await until(()=>evaluate('!document.getElementById('+JSON.stringify(prefix+'refresh')+').dataset.busy'));};
  const jobButton=async label=>{await evaluate('(()=>{const b=[...document.querySelectorAll('+JSON.stringify('#'+prefix+'jobs button')+')].find(b=>b.textContent==='+JSON.stringify(label)+');if(!b)throw Error("Missing classification action: "+'+JSON.stringify(label)+');b.click();b.click();})()');await until(()=>evaluate('!'+v+'Busy'));};
  const count=async()=> (await(await fetch('http://127.0.0.1:'+modelPort+'/test/request-count')).json()).requests;
  // A lost admitted POST must retain its exact identity across a full renderer reload,
  // synchronously before a delayed initial status GET can reconcile it.
  const persistedSource=await makeText('Reload recovery','Exact source for reload recovery.');await open(persistedSource.id);
  await evaluate('window.reloadNativeFetch=window.fetch;window.reloadLostAck=true;window.fetch=async(...args)=>{const r=await reloadNativeFetch(...args);if(reloadLostAck&&args[0]==="/api/workbench/text-classification-proposals"&&args[1]?.method==="POST"){reloadLostAck=false;throw Error("Synthetic full-reload lost admission acknowledgement");}return r;};');
  await start('Frozen reload recovery');const persistentBody=await evaluate(v+'PendingRequest');assert.ok(persistentBody?.request_id);
  await until(async()=> (await request('text-classification-proposals/'+persistentBody.request_id)).status==='completed');
  const storedAdmission=await evaluate('JSON.parse(localStorage.getItem("tuldok.text-classification-proposals.admission.v1"))');assert.deepEqual(storedAdmission,{schema_version:1,body:persistentBody},'Durable recovery retains the exact versioned frozen request body');
  const beforeRecoveryInference=await count();
  const recoveryHook=await send('Page.addScriptToEvaluateOnNewDocument',{source:'window.recoveryOriginalFetch=window.fetch;window.recoveryGetReleases=[];window.recoveryPostedBodies=[];window.fetch=async(...args)=>{const path=String(args[0]);if(path.startsWith("/api/workbench/text-classification-proposals")&&(!args[1]?.method||args[1].method==="GET"))await new Promise(resolve=>recoveryGetReleases.push(resolve));if(path==="/api/workbench/text-classification-proposals"&&args[1]?.method==="POST")recoveryPostedBodies.push(JSON.parse(args[1].body));return recoveryOriginalFetch(...args);};'});
  await send('Page.reload');await until(()=>evaluate('document.getElementById("notice")?.textContent==="Collection ready."'));
  assert.equal(await evaluate('current'),null,'Recovery controls must work before a record is opened');
  assert.equal(await evaluate('document.getElementById('+JSON.stringify(prefix+'panel')+').hidden'),false,'Pending recovery must be visible without an editor');
  await evaluate('document.getElementById('+JSON.stringify(prefix+'panel')+').querySelector("summary").click()');
  assert.deepEqual(JSON.parse(await evaluate('document.getElementById('+JSON.stringify(prefix+'pending-evidence')+').textContent')),persistentBody,'Visible recovery evidence retains the exact frozen request');
  await click(prefix+'open-pending');await until(()=>evaluate('current?.id==='+JSON.stringify(persistedSource.id)));
  await click(prefix+'restore');
  const restoredControls=await evaluate('({server_url:document.getElementById("text-classification-proposal-url").value,model:document.getElementById("text-classification-proposal-model").value,instruction:document.getElementById("text-classification-proposal-guidance").value,seed:Number(document.getElementById("text-classification-proposal-seed").value),labels:JSON.parse(document.getElementById("text-classification-proposal-labels").value)})');
  assert.deepEqual(restoredControls,{server_url:persistentBody.server_url,model:persistentBody.model,instruction:persistentBody.instruction,seed:persistentBody.seed,labels:persistentBody.labels});
  assert.equal((await evaluate('recoveryPostedBodies')).length,0,'Opening source and restoring visible settings cannot submit a model request');assert.equal(await count(),beforeRecoveryInference);
  const restoredBeforeSubmit=await evaluate(v+'PendingRequest');
  await fill(prefix+'guidance','Changed intent before initial reconciliation');await evaluate('document.getElementById('+JSON.stringify(prefix+'form')+').requestSubmit()');await until(()=>evaluate('recoveryPostedBodies.length>0 || !'+v+'Busy'));
  fs.writeFileSync(path.join(report,'reload-recovery-observation.json'),JSON.stringify({expected_id:persistentBody.request_id,restored_controls:restoredControls,restored_before_submit:restoredBeforeSubmit,restored_pending:await evaluate(v+'PendingRequest'),posted_bodies:await evaluate('recoveryPostedBodies'),before_inference:beforeRecoveryInference,after_inference:await count()},null,2));
  assert.equal((await evaluate('recoveryPostedBodies')).length,0,'Full reload must restore pending admission synchronously and block changed intent before delayed reconciliation');
  assert.deepEqual(await evaluate(v+'PendingRequest'),persistentBody,'Full reload must retain the exact bounded request body');
  await click(prefix+'restore');await click(prefix+'submit');await until(()=>evaluate('recoveryPostedBodies.length===1'));assert.deepEqual(await evaluate('recoveryPostedBodies'),[persistentBody]);assert.equal(await count(),beforeRecoveryInference,'Explicit same-ID retry after reload must not repeat inference');
  await evaluate('recoveryGetReleases.splice(0).forEach(resolve=>resolve());window.fetch=recoveryOriginalFetch');await send('Page.removeScriptToEvaluateOnNewDocument',{identifier:recoveryHook.identifier});await until(()=>evaluate('!'+v+'Busy'));await refresh();
  await until(()=>evaluate(v+'PendingRequest===null'));await start('Fresh intent after authoritative recovery');await until(()=>evaluate(v+'Jobs.some(j=>j.config.instruction==="Fresh intent after authoritative recovery"&&j.status==="completed")'));
  assert.equal(await count(),beforeRecoveryInference+1);
  // Reload an admission held before HTTP delivery: the real exact-ID GET returns
  // 404, and visible recovery controls must still recover the unchanged body.
  await evaluate('window.earlyReloadNativeFetch=window.fetch;window.earlyReloadHeld=false;window.fetch=async(...args)=>{if(args[0]==="/api/workbench/text-classification-proposals"&&args[1]?.method==="POST"){earlyReloadHeld=true;await new Promise(()=>{});}return earlyReloadNativeFetch(...args);};');
  await fill(prefix+'guidance','Reload recovery after real early 404');await click(prefix+'submit');await until(()=>evaluate('earlyReloadHeld'));const earlyReloadBody=await evaluate(v+'PendingRequest'),beforeEarlyReloadInference=await count();
  await send('Page.reload');await until(()=>evaluate('document.getElementById("notice")?.textContent==="Collection ready."'));await until(()=>evaluate('document.getElementById("text-classification-proposal-status").textContent.includes("not visible yet")'));
  assert.deepEqual(await evaluate(v+'PendingRequest'),earlyReloadBody,'Real early404 after reload retains the exact stored admission');assert.equal(await count(),beforeEarlyReloadInference);
  await evaluate('document.getElementById('+JSON.stringify(prefix+'panel')+').querySelector("summary").click()');await click(prefix+'open-pending');await until(()=>evaluate('current?.id==='+JSON.stringify(persistedSource.id)));await click(prefix+'restore');
  assert.equal(await evaluate('document.getElementById('+JSON.stringify(prefix+'guidance')+').value'),earlyReloadBody.instruction);assert.equal(await count(),beforeEarlyReloadInference,'Restoring after a real early404 cannot start inference');
  await click(prefix+'submit');await until(()=>evaluate('!'+v+'Busy'));await until(async()=> (await request('text-classification-proposals/'+earlyReloadBody.request_id)).status==='completed');assert.equal(await count(),beforeEarlyReloadInference+1,'Explicit sameID submission after real early404 makes exactly one first inference');
  fs.writeFileSync(path.join(report,'early404-reload-observation.json'),JSON.stringify({body:earlyReloadBody,before_inference:beforeEarlyReloadInference,after_inference:await count(),real_exact_get_status:404,restored_via_visible_buttons:true},null,2));
  const beforeMainInference=await count();
  await open(rows[0].id);await fill(prefix+'guidance','Classify exact request');
  // Hold the real admission; an exact-ID early 404 must preserve the ID, then lose the POST acknowledgement.
  await evaluate('window.nativeClassificationFetch=window.fetch;window.lostStart=true;window.holdStart=true;window.startHeld=false;window.postedIds=[];window.fetch=async(...args)=>{const start=args[0]==="/api/workbench/text-classification-proposals"&&args[1]?.method==="POST";if(start){postedIds.push(JSON.parse(args[1].body).request_id);if(holdStart){holdStart=false;startHeld=true;await new Promise(resolve=>window.releaseStart=resolve);}}const r=await nativeClassificationFetch(...args);if(lostStart&&start){lostStart=false;throw Error("Synthetic lost admission acknowledgement");}return r;};');
  await fill(prefix+'guidance','Classify exact request');await evaluate('document.getElementById('+JSON.stringify(prefix+'form')+').requestSubmit()');await until(()=>evaluate('startHeld'));
  const recoveryId=await evaluate(v+'PendingRequest.request_id');await refresh();assert.equal(await evaluate(v+'PendingRequest?.request_id'),recoveryId);assert.equal(await count(),beforeMainInference);
  await evaluate('releaseStart()');await until(()=>evaluate('!'+v+'Busy'));assert.equal(await evaluate(v+'PendingRequest?.request_id'),recoveryId);
  await start('Classify exact request');assert.deepEqual(await evaluate('postedIds'),[recoveryId,recoveryId]);await refresh();await until(()=>evaluate(v+'Jobs.some(j=>j.status==="completed")'));
  assert.equal(await count(),beforeMainInference+1);assert.equal(await evaluate(v+'PendingRequest'),null);
  const job=(await request('text-classification-proposals')).jobs.find(j=>j.status==='completed'&&j.source.id===rows[0].id),detail=await request('text-classification-proposals/'+job.id);
  const crypto=require('node:crypto'),digest=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
  assert.equal(detail.source.text,rows[0].text);assert.deepEqual(detail.config.labels,labels);assert.equal(detail.config.instruction,'Classify exact request');assert.equal(detail.config.requested_server_url,'http://127.0.0.1:'+modelPort+'/v1/');assert.equal(detail.config.server_url,'http://127.0.0.1:'+modelPort);
  assert.equal(digest(Buffer.from(detail.raw_response_base64,'base64')),detail.response_sha256);assert.deepEqual(await request('records/'+rows[0].id),rows[0]);
  await jobButton('Inspect request evidence');assert.ok(await evaluate('document.querySelector('+JSON.stringify('#'+prefix+'jobs pre')+').textContent.includes("canonical_request_sha256")'));
  // Changed label choices and dirty editor both fence Apply without committing a target.
  await fill(prefix+'labels',JSON.stringify(['keep','cancel']));await jobButton('Apply as draft');assert.deepEqual(await request('records/'+rows[0].id),rows[0]);
  assert.ok((await evaluate('document.getElementById('+JSON.stringify(prefix+'status')+').textContent')).includes('frozen'));
  await fill(prefix+'labels',JSON.stringify(labels));await fill('label','unsaved author label');await jobButton('Apply as draft');assert.deepEqual(await request('records/'+rows[0].id),rows[0]);
  await evaluate('window.confirm=()=>true');await open(rows[0].id);
  // Lose a committed Apply acknowledgement; it commits one draft and keeps fixed selection revisions.
  await evaluate('window.lostApply=true;window.fetch=async(...args)=>{const r=await nativeClassificationFetch(...args);if(lostApply&&String(args[0]).includes("text-classification-proposals/decide/")&&args[1]?.method==="POST"){lostApply=false;throw Error("Synthetic lost Apply acknowledgement");}return r;};');
  await jobButton('Apply as draft');const applied=await request('records/'+rows[0].id);assert.equal(applied.revision,rows[0].revision+1);assert.equal(applied.review,'draft');assert.deepEqual(applied.annotation,{label:'cancel'});assert.deepEqual(applied.provenance,rows[0].provenance);assert.equal(applied.target_proposal.job_id,job.id);
  assert.deepEqual(await evaluate('releaseBody().items'),fixed);await refresh();
  const again=await request('text-classification-proposals/decide/'+job.id,{revision:job.revision,decision:'apply_draft',labels});assert.equal(again.changed,false);assert.equal(again.record.revision,applied.revision);
  await jobButton('Open applied classification');assert.equal(await evaluate('current.review'),'draft');assert.equal((await request('selections/'+saved.id)).members.find(m=>m.item.id===rows[0].id).status,'stale');
  await click('clear-selection');await until(()=>evaluate('selected.size===0'));await evaluate('selected.set(current.id,{id:current.id,revision:current.revision,source_revision:current.source_revision});selection(true);');
  await fill('train',100);await fill('validation',0);await fill('test',0);await click('preview-release');await until(()=>evaluate('!releaseBusy && !!releasePreview'));assert.equal(await evaluate('releasePreview.eligible'),false);
  await fill('record-review','human_reviewed');await evaluate('document.getElementById("editor").requestSubmit()');await until(()=>evaluate('!document.getElementById("editor").dataset.busy&&current.review==="human_reviewed"'));
  const reviewed=await request('records/'+rows[0].id);assert.equal(reviewed.target_proposal.job_id,job.id);
  await evaluate('selected.clear();selected.set(current.id,{id:current.id,revision:current.revision,source_revision:current.source_revision});selection(true);');
  await click('preview-release');await until(()=>evaluate('!document.getElementById("freeze-release").disabled'));
  await evaluate('document.getElementById("release-form").requestSubmit()');await until(()=>evaluate('!!document.querySelector("#release-result a")'));
  const archiveURL=await evaluate('document.querySelector("#release-result a").href');const archiveResponse=await fetch(archiveURL);assert.equal(archiveResponse.status,200);
  const zipPath=path.join(report,'classification-reviewed.zip');fs.writeFileSync(zipPath,Buffer.from(await archiveResponse.arrayBuffer()));
  const {execFileSync}=require('node:child_process');const archiveEvidence=JSON.parse(execFileSync('python3',['-c','import json,sys,zipfile;z=zipfile.ZipFile(sys.argv[1]);m=json.loads(z.read("manifest.json"));r=json.loads(z.read("train/records.jsonl"));print(json.dumps({"record":r,"manifest":m}))',zipPath],{encoding:'utf8'}));
  assert.equal(archiveEvidence.record.text,rows[0].text);assert.deepEqual(archiveEvidence.record.annotation,{label:'cancel'});assert.equal(archiveEvidence.record.review,'human_reviewed');assert.equal(archiveEvidence.record.target_proposal.job_id,job.id);assert.deepEqual(archiveEvidence.record.provenance,rows[0].provenance);
  // New unannotated source: abstention presents no Apply, and rejection cannot revoke unrelated save ownership.
  await open(rows[1].id);await start('abstain');await until(()=>evaluate(v+'Jobs.some(j=>j.status==="abstained")'));
  assert.equal(await evaluate('[...document.querySelectorAll('+JSON.stringify('#'+prefix+'jobs button')+')].some(b=>b.textContent==="Apply as draft")'),false);assert.deepEqual(await request('records/'+rows[1].id),rows[1]);
  await evaluate('window.holdSave=true;window.saveHeld=false;window.fetch=async(...args)=>{const r=await nativeClassificationFetch(...args);if(holdSave&&args[0]==='+JSON.stringify('/api/workbench/records/'+rows[1].id)+'&&args[1]?.method==="POST"){holdSave=false;saveHeld=true;await new Promise(resolve=>window.releaseSave=resolve);}return r;};');
  await fill('label','keep');await fill('record-review','draft');await evaluate('document.getElementById("editor").requestSubmit()');await until(()=>evaluate('saveHeld'));const committedSave=await request('records/'+rows[1].id);
  await jobButton('Reject classification proposal');assert.deepEqual(await request('records/'+rows[1].id),committedSave);
  await evaluate('releaseSave()');await until(()=>evaluate('!document.getElementById("editor").dataset.busy'));assert.equal(await evaluate('current.revision'),committedSave.revision);assert.equal(await evaluate('dirty'),false);
  await evaluate('document.getElementById("editor").requestSubmit()');await until(()=>evaluate('!document.getElementById("editor").dataset.busy'));assert.equal((await request('records/'+rows[1].id)).revision,committedSave.revision+1);
  // Cancellation follows the captured source across navigation; fresh author intent gets a fresh ID.
  const third=await makeText('Cancel lifecycle','Third unannotated source.');await open(third.id);await start('slow');await until(()=>evaluate(v+'Jobs.some(j=>j.source.id==='+JSON.stringify(third.id)+'&&j.status==="generating")'));
  await open(rows[0].id);assert.ok(!(await evaluate('document.getElementById('+JSON.stringify(prefix+'jobs')+').textContent')).includes('generating'));await open(third.id);await jobButton('Cancel classification request');
  await until(async()=>{await refresh();return evaluate(v+'Jobs.some(j=>j.source.id==='+JSON.stringify(third.id)+'&&j.status==="cancelled")');});
  const cancelled=(await request('text-classification-proposals')).jobs.find(j=>j.source.id===third.id&&j.status==='cancelled');await start('Fresh author intent');await until(()=>evaluate(v+'Jobs.some(j=>j.status==="completed"&&j.config.instruction==="Fresh author intent")'));
  const fresh=(await request('text-classification-proposals')).jobs.find(j=>j.config.instruction==='Fresh author intent');assert.notEqual(fresh.id,cancelled.id);assert.deepEqual(await request('records/'+third.id),third);
  const beforeReload=await count();await send('Page.reload');await until(()=>evaluate('document.getElementById("notice")?.textContent==="Collection ready."'));await open(third.id);await refresh();assert.equal(await count(),beforeReload);
  // Storage failures must fail closed before a POST or before forgetting an admitted body.
  const storageKey='tuldok.text-classification-proposals.admission.v1',beforeStorageInference=await count();
  const getFailureHook=await send('Page.addScriptToEvaluateOnNewDocument',{source:'window.storageOriginalGet=Storage.prototype.getItem;window.storageOriginalFetch=window.fetch;window.storagePostedBodies=[];Storage.prototype.getItem=function(key){if(key==="tuldok.text-classification-proposals.admission.v1")throw Error("Synthetic getItem failure");return storageOriginalGet.call(this,key);};window.fetch=async(...args)=>{if(args[0]==="/api/workbench/text-classification-proposals"&&args[1]?.method==="POST")storagePostedBodies.push(JSON.parse(args[1].body));return storageOriginalFetch(...args);};'});
  await send('Page.reload');await until(()=>evaluate('document.getElementById("notice")?.textContent==="Collection ready."'));await open(third.id);
  await fill(prefix+'url','http://127.0.0.1:'+modelPort+'/v1/');await click(prefix+'models');await until(()=>evaluate('document.getElementById('+JSON.stringify(prefix+'model')+').options.length===1'));await fill(prefix+'model','classification-fixture');await fill(prefix+'labels',JSON.stringify(labels));
  await start('Must block getItem failure');assert.equal((await evaluate('storagePostedBodies')).length,0);assert.equal(await count(),beforeStorageInference);
  assert.ok(await evaluate('Boolean(textClassificationProposalStorageBlocked)'));
  await evaluate('Storage.prototype.getItem=storageOriginalGet');await send('Page.removeScriptToEvaluateOnNewDocument',{identifier:getFailureHook.identifier});await refresh();
  await evaluate('window.storageOriginalSet=Storage.prototype.setItem;Storage.prototype.setItem=function(key,value){if(key==="tuldok.text-classification-proposals.admission.v1")throw Error("Synthetic setItem failure");return storageOriginalSet.call(this,key,value);};');
  await start('Must block setItem failure');assert.equal((await evaluate('storagePostedBodies')).length,0);assert.equal(await count(),beforeStorageInference);assert.ok(await evaluate('Boolean(textClassificationProposalStorageBlocked)'));
  await evaluate('Storage.prototype.setItem=storageOriginalSet');await refresh();await start('Must block setItem failure');await until(()=>evaluate(v+'Jobs.some(j=>j.config.instruction==="Must block setItem failure"&&j.status==="completed")'));assert.equal((await evaluate('storagePostedBodies')).length,1);assert.equal(await count(),beforeStorageInference+1);
  await evaluate('window.storageOriginalRemove=Storage.prototype.removeItem;Storage.prototype.removeItem=function(key){if(key==="tuldok.text-classification-proposals.admission.v1")throw Error("Synthetic removeItem failure");return storageOriginalRemove.call(this,key);};');
  await start('Admitted removal failure');const removalBody=await evaluate(v+'PendingRequest');assert.ok(removalBody?.request_id);await until(async()=> (await request('text-classification-proposals/'+removalBody.request_id)).status==='completed');
  assert.ok(await evaluate('localStorage.getItem('+JSON.stringify(storageKey)+')!==null'));assert.equal((await evaluate('storagePostedBodies')).length,2);
  await refresh();await start('Must block removeItem failure');assert.equal((await evaluate('storagePostedBodies')).length,2);assert.equal(await evaluate(v+'PendingRequest'),null,'An exact receipt retires the authoritative pending admission before mirror cleanup');assert.equal(await count(),beforeStorageInference+2);
  const canonicalRemovalFrame=JSON.stringify({schema_version:1,body:removalBody});
  assert.equal(await evaluate('localStorage.getItem('+JSON.stringify(storageKey)+')'),canonicalRemovalFrame,'Failed mirror removal must retain the exact retired admission frame');assert.ok(await evaluate('Boolean(textClassificationProposalStorageBlocked)'));
  const retiredAuthority=await evaluate('new Promise((resolve,reject)=>{const request=indexedDB.open("tuldok.text-classification-proposals.admission.v1",1);request.onerror=()=>reject(request.error);request.onsuccess=()=>{const database=request.result,transaction=database.transaction("recovery","readonly"),store=transaction.objectStore("recovery"),values={};transaction.onabort=()=>{database.close();reject(transaction.error);};transaction.oncomplete=()=>{database.close();resolve({has_pending:values.pending!==undefined,initialized:values.initialized});};for(const key of ["pending","initialized"]){const read=store.get(key);read.onsuccess=()=>values[key]=read.result;}};})');
  assert.equal(retiredAuthority.has_pending,false,'The admitted request must be retired in real IndexedDB authority');assert.deepEqual(retiredAuthority.initialized,{schema_version:1,resolved_raw:canonicalRemovalFrame},'Retirement proof must retain the exact authoritative receipt frame');
  await evaluate('Storage.prototype.removeItem=storageOriginalRemove');await refresh();assert.equal(await evaluate(v+'PendingRequest'),null);assert.equal(await evaluate('localStorage.getItem('+JSON.stringify(storageKey)+')'),null);
  await start('Fresh intent after storage recovers');await until(()=>evaluate(v+'Jobs.some(j=>j.config.instruction==="Fresh intent after storage recovers"&&j.status==="completed")'));assert.equal((await evaluate('storagePostedBodies')).length,3);assert.equal(await count(),beforeStorageInference+3);assert.notEqual((await evaluate('storagePostedBodies'))[2].request_id,removalBody.request_id,'Fresh author intent must use a different admission ID after exact retirement');assert.equal(await evaluate('localStorage.getItem('+JSON.stringify(storageKey)+')'),null,'Retired mirror must be cleared after access recovers');
  fs.writeFileSync(path.join(report,'storage-failure-observation.json'),JSON.stringify({get_failure_posts:0,set_failure_posts:0,remove_failure_blocked_posts:2,removal_body:removalBody,retired_authority:retiredAuthority,canonical_retired_mirror:canonicalRemovalFrame,final_posts:await evaluate('storagePostedBodies'),baseline_inference:beforeStorageInference,final_inference:await count()},null,2));
  // Native controls admit a syntactically valid long URL and 2001 ASCII guidance
  // characters. Client bounds must reject both before durable state or HTTP POST.
  const validationSource=await makeText('Fresh validation source','Unannotated text for bounded native form validation.');await open(validationSource.id);
  const shortValidationURL='http://127.0.0.1:'+modelPort+'/v1/',urlAuthority='http://127.0.0.1:'+modelPort+'/',longValidationURL=urlAuthority+'x'.repeat(2072-urlAuthority.length),beforeValidationInference=await count();
  await evaluate('window.validationNativeFetch=window.fetch;window.validationPostedBodies=[];window.fetch=async(...args)=>{if(args[0]==="/api/workbench/text-classification-proposals"&&args[1]?.method==="POST")validationPostedBodies.push(JSON.parse(args[1].body));return validationNativeFetch(...args);};');
  await fill(prefix+'url',longValidationURL);
  // The synthetic catalog is intentionally available only at /v1/models. Offer
  // its known fixture model in the native select without contacting the long path.
  await evaluate('document.getElementById("text-classification-proposal-model").replaceChildren(new Option("classification-fixture","classification-fixture"))');
  await fill(prefix+'labels',JSON.stringify(labels));await fill(prefix+'guidance','Reject oversized gateway before admission');
  assert.equal(Array.from(longValidationURL).length,2072);assert.equal(await evaluate('document.getElementById("text-classification-proposal-form").checkValidity()'),true,'The 2072-character URL is valid in the native form');
  await start('Reject oversized gateway before admission');
  const rejectedLongURL=await evaluate('({posts:validationPostedBodies.length,pending:textClassificationProposalPendingRequest,stored:localStorage.getItem("tuldok.text-classification-proposals.admission.v1"),blocked:textClassificationProposalStorageBlocked,recoveryId:textClassificationProposalRecoveryId,status:document.getElementById("text-classification-proposal-status").textContent})');
  assert.equal(rejectedLongURL.posts,0);assert.equal(rejectedLongURL.pending,null);assert.equal(rejectedLongURL.stored,null);assert.equal(rejectedLongURL.blocked,'');assert.equal(rejectedLongURL.recoveryId,null);assert.equal(await count(),beforeValidationInference);
  await fill(prefix+'url',shortValidationURL);await click(prefix+'models');await until(()=>evaluate('document.getElementById('+JSON.stringify(prefix+'model')+').options.length===1'));await fill(prefix+'model','classification-fixture');
  await start('Reject oversized gateway before admission');await until(()=>evaluate(v+'Jobs.some(j=>j.source.id==='+JSON.stringify(validationSource.id)+'&&j.status==="completed")'));
  assert.equal((await evaluate('validationPostedBodies')).length,1);assert.equal(await count(),beforeValidationInference+1,'Correcting an invalid URL on the same page makes one explicit request');
  const longGuidance='g'.repeat(2001),exactGuidance='g'.repeat(2000);await fill(prefix+'guidance',longGuidance);assert.equal(await evaluate('document.getElementById("text-classification-proposal-form").checkValidity()'),true,'ASCII guidance2001 fits native maxlength4000');
  await start(longGuidance);
  const rejectedLongGuidance=await evaluate('({posts:validationPostedBodies.length,pending:textClassificationProposalPendingRequest,stored:localStorage.getItem("tuldok.text-classification-proposals.admission.v1"),blocked:textClassificationProposalStorageBlocked,recoveryId:textClassificationProposalRecoveryId,status:document.getElementById("text-classification-proposal-status").textContent})');
  assert.equal(rejectedLongGuidance.posts,1);assert.equal(rejectedLongGuidance.pending,null);assert.equal(rejectedLongGuidance.stored,null);assert.equal(rejectedLongGuidance.blocked,'');assert.equal(rejectedLongGuidance.recoveryId,null);assert.equal(await count(),beforeValidationInference+1);
  await start(exactGuidance);await until(()=>evaluate(v+'Jobs.some(j=>j.source.id==='+JSON.stringify(validationSource.id)+'&&j.config.instruction.length===2000&&j.status==="completed")'));
  assert.equal((await evaluate('validationPostedBodies')).length,2);assert.equal(await count(),beforeValidationInference+2);assert.equal((await evaluate('validationPostedBodies'))[1].instruction,exactGuidance,'Valid 2000-character guidance is preserved exactly');
  fs.writeFileSync(path.join(report,'native-validation-observation.json'),JSON.stringify({url_code_points:2072,rejected_url:rejectedLongURL,rejected_guidance:rejectedLongGuidance,accepted_url:shortValidationURL,accepted_guidance_code_points:2000,accepted_guidance_sha256:digest(Buffer.from(exactGuidance)),explicit_posts:await evaluate('validationPostedBodies'),before_inference:beforeValidationInference,after_inference:await count()},null,2));
  await evaluate('document.getElementById('+JSON.stringify(prefix+'panel')+').open=true;document.getElementById('+JSON.stringify(prefix+'panel')+').scrollIntoView()');
  let shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});fs.writeFileSync(path.join(report,'classification-desktop.png'),Buffer.from(shot.data,'base64'));
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'),'Narrow classification layout must not overflow');
  await evaluate('document.getElementById('+JSON.stringify(prefix+'panel')+').scrollIntoView()');shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});fs.writeFileSync(path.join(report,'classification-narrow.png'),Buffer.from(shot.data,'base64'));
  await evaluate('document.getElementById('+JSON.stringify(prefix+'labels')+').focus();document.getElementById('+JSON.stringify(prefix+'labels')+').select()');await send('Input.insertText',{text:JSON.stringify(labels)});assert.equal(await evaluate('document.getElementById('+JSON.stringify(prefix+'labels')+').value'),JSON.stringify(labels));assert.deepEqual(errors,[]);
  // Shared-origin, real-IDB dispatch races. All ordering comes from fetch
  // barriers and completed handlers, rather than a sleep chosen to win a race.
  // The previous page has finished its UI checks; remove its polling realm.
  await send('Page.navigate',{url:'about:blank'});
  const dispatchHook=String.raw`
    window.dispatchNativeFetch=window.fetch;
    window.dispatchPosts=[];window.dispatchResponses=[];window.dispatchGetHeld=[];
    window.dispatchHoldMode='';window.dispatchHoldGets=false;window.dispatchDropAck=false;
    window.fetch=async(...args)=>{
      const url=String(args[0]),isPost=url==='/api/workbench/text-classification-proposals'&&args[1]?.method==='POST';
      const isGet=url.startsWith('/api/workbench/text-classification-proposals')&&!args[1]?.method;
      if(isPost){
        dispatchPosts.push(JSON.parse(args[1].body));
        if(dispatchHoldMode==='before'){dispatchBarrier='before';await new Promise(resolve=>window.dispatchRelease=resolve);}
      }
      const response=await dispatchNativeFetch(...args);
      if(isPost){
        dispatchResponses.push({status:response.status,body:await response.clone().json()});
        if(dispatchHoldMode==='after'){dispatchBarrier='after';await new Promise(resolve=>window.dispatchRelease=resolve);}
        if(dispatchDropAck){dispatchDropAck=false;throw Error('Synthetic cross-tab lost admission acknowledgement');}
      }
      if(isGet&&dispatchHoldGets)await new Promise(resolve=>dispatchGetHeld.push({url,status:response.status,resolve}));
      return response;
    };
    window.dispatchReleaseGets=()=>{dispatchHoldGets=false;for(const held of dispatchGetHeld.splice(0))held.resolve();};
  `;
  const nativeTab=async(holdGets=false)=>{
    const target=await(await fetch('http://127.0.0.1:'+debugPort+'/json/new?about:blank',{method:'PUT'})).json();
    const socket=new WebSocket(target.webSocketDebuggerUrl);extraSockets.push(socket);
    await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
    let sequence=0;const requests=new Map(),loads=pageLoadTracker();
    socket.onmessage=event=>{const message=JSON.parse(event.data);loads.observe(message);if(message.id){const pending=requests.get(message.id);requests.delete(message.id);message.error?pending.reject(message.error):pending.resolve(message.result);}if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails);};
    const command=(method,params={})=>new Promise((resolve,reject)=>{requests.set(++sequence,{resolve,reject});socket.send(JSON.stringify({id:sequence,method,params}));});
    const run=async expression=>{const result=await command('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
    await command('Page.enable');await command('Runtime.enable');await command('Page.setLifecycleEventsEnabled',{enabled:true});
    await command('Page.addScriptToEvaluateOnNewDocument',{source:dispatchHook+(holdGets?'dispatchHoldGets=true;':'')});
    await command('Page.navigate',{url:base+'/workbench'});await until(()=>run('document.getElementById("notice")?.textContent==="Collection ready."'));
    const tab={id:target.id,command,run,
      click:id=>run('document.getElementById('+JSON.stringify(id)+').click()'),
      fill:(id,value)=>run('(()=>{const input=document.getElementById('+JSON.stringify(id)+');input.value='+JSON.stringify(value)+';input.dispatchEvent(new Event("input",{bubbles:true}));input.dispatchEvent(new Event("change",{bubbles:true}));})()'),
      submit:()=>run('document.getElementById("text-classification-proposal-form").requestSubmit()'),
      idle:()=>until(()=>run('!textClassificationProposalBusy')),
      close:()=>send('Target.closeTarget',{targetId:target.id}),
      reload:async()=>{const previous=(await command('Page.getFrameTree')).frameTree.frame;await command('Page.reload');await until(()=>loads.reloaded(previous));await until(()=>run('document.getElementById("notice")?.textContent==="Collection ready."'));}
    };
    tab.open=async source=>{await run('openRecord('+JSON.stringify(source.id)+')');await until(()=>run('current?.id==='+JSON.stringify(source.id)));};
    tab.configure=async(source,guidance)=>{await tab.open(source);await tab.fill(prefix+'url','http://127.0.0.1:'+modelPort+'/v1/');await tab.click(prefix+'models');await until(()=>run('document.getElementById("text-classification-proposal-model").options.length===1'));await tab.fill(prefix+'model','classification-fixture');await tab.fill(prefix+'labels',JSON.stringify(labels));await tab.fill(prefix+'guidance',guidance);};
    tab.restore=async()=>{await tab.click(prefix+'open-pending');await until(()=>run('current?.id===textClassificationProposalPendingRequest?.source_id'));await tab.click(prefix+'restore');};
    tab.snapshot=()=>run('new Promise((resolve,reject)=>{const request=indexedDB.open("tuldok.text-classification-proposals.admission.v1");request.onerror=()=>reject(request.error);request.onsuccess=()=>{const database=request.result,tx=database.transaction("recovery","readonly"),store=tx.objectStore("recovery");let keys,values;store.getAllKeys().onsuccess=e=>keys=e.target.result;store.getAll().onsuccess=e=>values=e.target.result;tx.onabort=()=>{database.close();reject(tx.error);};tx.oncomplete=()=>{database.close();resolve({entries:Object.fromEntries(keys.map((key,index)=>[key,values[index]])),mirror:localStorage.getItem("tuldok.text-classification-proposals.admission.v1"),memory:textClassificationProposalPendingRequest,blocked:textClassificationProposalStorageBlocked});};};})');
    return tab;
  };
  const dispatchEvidence=[];
  const writeDispatch=()=>fs.writeFileSync(path.join(report,'cross-tab-dispatch-observation.json'),JSON.stringify({source_head:require('node:child_process').execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),runtime_sha256:digest(fs.readFileSync(path.join(root,'static/text-classification-proposals.js'))),cases:dispatchEvidence},null,2));
  const ledger=async()=> (await(await fetch(base+'/test/classification-dispatch')).json()).admissions;
  for(const outcome of ['success','lost-ack']){
    const source=await makeText('Cross-tab '+outcome,'Exact cross-tab source '+outcome+'.'),baseline=await count();
    const a=await nativeTab();await a.configure(source,'dispatch-refusal-'+outcome);await a.run('dispatchHoldMode="after"');await a.submit();await until(()=>a.run('dispatchBarrier==="after"'));
    const body=(await a.run('dispatchPosts'))[0],frame=JSON.stringify({schema_version:1,body});
    const first=await a.snapshot();
    const b=await nativeTab();await b.restore();await b.run('dispatchHoldMode="before"');await b.submit();await until(()=>b.run('dispatchBarrier==="before"'));
    assert.deepEqual(await b.run('dispatchPosts'),[body],'Both tabs explicitly dispatch the identical ID/body');
    const second=await b.snapshot();
    await a.run('dispatchHoldMode="";dispatchRelease()');await a.idle();
    const afterOldRefusal=await a.snapshot();
    const observation={outcome,body,first,second,after_old_refusal:afterOldRefusal,before_inference:baseline,backend_before_release:(await ledger()).filter(entry=>entry.body.request_id===body.request_id)};
    dispatchEvidence.push(observation);writeDispatch();
    assert.equal(afterOldRefusal.entries.pending,frame,'An older409 cannot retire an identical request with a newer committed dispatch');
    assert.equal(afterOldRefusal.mirror,frame,'An older409 cannot erase the durable mirror');
    assert.deepEqual(first.entries.attempt,{schema_version:1,raw:frame,generation:1});
    assert.deepEqual(second.entries.attempt,{schema_version:1,raw:frame,generation:2});
    assert.deepEqual(afterOldRefusal.entries.attempt,second.entries.attempt);
    assert.equal(await count(),baseline,'Neither the first refusal nor a held transport runs inference');
    await a.fill(prefix+'guidance','Changed intent while second dispatch is unknown');await a.submit();await a.idle();
    assert.equal((await a.run('dispatchPosts')).length,1,'Changed intent must not issue a third POST');
    assert.equal((await b.run('dispatchPosts')).length,1);
    const early=await fetch(base+'/api/workbench/text-classification-proposals/'+body.request_id);assert.equal(early.status,404,'The second transport is held before actual admission');
    observation.early_exact_get_status=early.status;observation.changed_intent_posts=0;
    await a.run('dispatchHoldGets=true');await b.run('dispatchHoldGets=true;dispatchHoldMode="";dispatchDropAck='+JSON.stringify(outcome==='lost-ack')+';dispatchRelease()');await b.idle();
    await until(async()=> (await request('text-classification-proposals/'+body.request_id)).status==='completed');
    assert.equal(await count(),baseline+1);
    observation.after_second_transport=await b.snapshot();observation.backend_after_release=(await ledger()).filter(entry=>entry.body.request_id===body.request_id);
    if(outcome==='lost-ack'){
      assert.equal(observation.after_second_transport.entries.pending,frame,'Lost acknowledgment retains exact ID/body until canonical reconciliation');
      await b.command('Page.addScriptToEvaluateOnNewDocument',{source:'dispatchHoldGets=true;'});await b.reload();
      await until(()=>b.run('dispatchGetHeld.length>0'));
      assert.deepEqual(await b.run('textClassificationProposalPendingRequest'),body,'Reload restores exact recovery body before held canonical GET');
      assert.equal((await b.run('dispatchPosts')).length,0,'Reload does not automatically retry inference');
      await b.restore();await b.submit();await b.idle();assert.deepEqual(await b.run('dispatchPosts'),[body]);assert.equal(await count(),baseline+1,'Explicit same-ID retry after lostACK/reload is idempotent');
      observation.reload_explicit_posts=await b.run('dispatchPosts');
    }
    const retired=await b.snapshot();assert.equal(retired.entries.pending,undefined);assert.equal(retired.entries.attempt,undefined);assert.equal(retired.mirror,null);
    observation.canonical_retirement=retired;observation.after_inference=await count();writeDispatch();
    await a.close();await b.close();
  }
  // A terminal canonical GET can retire a whole admitted ID, but a delayed
  // receipt for that ID cannot erase a subsequently committed new admission.
  const terminalSource=await makeText('Terminal receipt CAS','Exact source for terminal receipt CAS.'),terminalBaseline=await count();
  const owner=await nativeTab();await owner.configure(terminalSource,'Terminal canonical receipt');await owner.run('dispatchDropAck=true;dispatchHoldGets=true');await owner.submit();await owner.idle();
  const terminalBody=(await owner.run('dispatchPosts'))[0];await until(async()=> (await request('text-classification-proposals/'+terminalBody.request_id)).status==='completed');
  const observer=await nativeTab(true);await until(()=>observer.run('dispatchGetHeld.some(held=>held.status===200)'));
  await owner.run('dispatchReleaseGets()');await owner.click(prefix+'refresh');await until(async()=> (await owner.snapshot()).entries.pending===undefined);
  const freshSource=await makeText('Fresh after terminal receipt','New exact source.'),freshTab=await nativeTab();await freshTab.configure(freshSource,'Fresh after terminal receipt');await freshTab.run('dispatchHoldMode="before"');await freshTab.submit();await until(()=>freshTab.run('dispatchBarrier==="before"'));
  const freshBody=(await freshTab.run('dispatchPosts'))[0],freshFrame=JSON.stringify({schema_version:1,body:freshBody});assert.notEqual(freshBody.request_id,terminalBody.request_id);
  await observer.run('dispatchReleaseGets()');await until(()=>observer.run('textClassificationProposalStorageBlocked.includes("another admission")'));
  const afterOldCanonical=await observer.snapshot();
  assert.equal(afterOldCanonical.entries.pending,freshFrame,'An old canonical receipt cannot erase a newer admission');assert.equal(afterOldCanonical.mirror,freshFrame);assert.equal(afterOldCanonical.entries.attempt.raw,freshFrame);
  await freshTab.run('dispatchHoldMode="";dispatchRelease()');await freshTab.idle();await until(async()=> (await request('text-classification-proposals/'+freshBody.request_id)).status==='completed');assert.equal(await count(),terminalBaseline+2);
  dispatchEvidence.push({outcome:'terminal-receipt-CAS',terminal_body:terminalBody,fresh_body:freshBody,after_old_canonical:afterOldCanonical,before_inference:terminalBaseline,after_inference:await count()});writeDispatch();await owner.close();await observer.close();await freshTab.close();
  // Closing a realm releases live ownership; durable admission intent remains.
  const crashSource=await makeText('Crash before delivery','Exact crash/reload source.'),crashBaseline=await count();
  const crashed=await nativeTab();await crashed.configure(crashSource,'Crash before delivery');await crashed.run('dispatchHoldMode="before"');await crashed.submit();await until(()=>crashed.run('dispatchBarrier==="before"'));
  const crashBody=(await crashed.run('dispatchPosts'))[0];await crashed.close();
  const recovered=await nativeTab();await until(()=>recovered.run('document.getElementById("text-classification-proposal-status").textContent.includes("not visible yet")'));
  assert.deepEqual(await recovered.run('textClassificationProposalPendingRequest'),crashBody);assert.equal((await recovered.run('dispatchPosts')).length,0);assert.equal(await count(),crashBaseline);
  await recovered.restore();await recovered.submit();await recovered.idle();assert.deepEqual(await recovered.run('dispatchPosts'),[crashBody]);await until(async()=> (await request('text-classification-proposals/'+crashBody.request_id)).status==='completed');assert.equal(await count(),crashBaseline+1);
  const crashRetired=await recovered.snapshot();assert.equal(crashRetired.entries.pending,undefined);assert.equal(crashRetired.entries.attempt,undefined);
  dispatchEvidence.push({outcome:'crash-before-delivery',body:crashBody,early_exact_get_status:404,explicit_recovered_posts:await recovered.run('dispatchPosts'),retired:crashRetired,before_inference:crashBaseline,after_inference:await count()});writeDispatch();await recovered.close();assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(report,'session.json'),JSON.stringify({source_head:require('node:child_process').execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),model:'bounded synthetic HTTP fixture',job_id:job.id,labels,early404_reload_id:earlyReloadBody.request_id,persistent_recovery_id:persistentBody.request_id,persistent_recovery_body:persistentBody,recovery_id:recoveryId,recovery_post_ids:[recoveryId,recoveryId],recovery_backend_requests:1,application_revision:applied.revision,downloaded_zip_sha256:digest(fs.readFileSync(zipPath)),fixed,reject_save_revision:committedSave.revision,cancelled_id:cancelled.id,fresh_intent_id:fresh.id,real_model_quality:false,tests:'native URL2072 and guidance2001 reject before POST/storage/pending/error latch, same-page validURL and exactguidance2000 explicit correction each once, visible pending evidence/open-source/restore-settings buttons recover form without developer tools or automatic POST, fullreload lostACK restored before delayed reconciliation unchanged exact-ID repeat and fresh intent, storage get/set/remove failures closed, early404 lost admission exact-ID recovery, frozen source/prompt/provider/labels evidence, malformed UI changes and dirty editor fences, lost Apply draft/idempotency/provenance, stale fixed selection, draft export blocked separate human review, abstention unappliable, reject during held unrelated save and subsequent save, cancellation navigation fresh intent, reload no inference, keyboard/narrow layout'},null,2));
  console.log('Text classification proposals real HTTP/Chromium bounded synthetic contracts passed.');
})().catch(async error=>{console.error(error);console.error('Runtime errors:',JSON.stringify(errors));if(inspect)try{console.error('Page diagnostics:',await inspect());}catch(diagnostic){console.error('Diagnostics failed:',diagnostic);}process.exitCode=1;}).finally(async()=>{if(ws)ws.close();for(const socket of extraSockets)socket.close();for(const child of children)child.kill();await pause(200);fs.rmSync(temporary,{recursive:true,force:true});});
