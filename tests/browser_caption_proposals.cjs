// Native browser smoke test. No npm dependencies.
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process');
const root=process.env.TULDOK_SOURCE_ROOT||path.resolve(__dirname,'..'),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-caption-proposals-browser-')),children=[];
let ws, inspect;
const errors=[];
const {pageLoadTracker}=require('./browser_page_load.cjs');const pageLoads=pageLoadTracker();
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn){for(let i=0;i<150;i++){const value=await fn();if(value)return value;await pause(100);}throw Error('Timed out');}
function launch(command,args,options={}){const child=spawn(command,args,options);children.push(child);return child;}
(async()=>{
  const outputRoot=path.join(root,'test-results/caption-proposals');fs.mkdirSync(outputRoot,{recursive:true});
  const report=fs.mkdtempSync(path.join(outputRoot,'run-'));
  console.log('Caption proposal evidence: '+report);
  const server=launch('python3',['-u','tests/browser_caption_proposals_server.py','--port','0','--data',path.join(temporary,'data')],{cwd:root,stdio:['ignore','pipe','pipe']});
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
  async function image(name,color) {
    const bytes=await evaluate(`(()=>{const c=document.createElement('canvas');c.width=200;c.height=100;const x=c.getContext('2d');x.fillStyle=${JSON.stringify(color)};x.fillRect(0,0,200,100);return c.toDataURL('image/png').split(',')[1];})()`);
    const row=await request('import',{kind:'image',name,image:bytes,groups:[name],rights:'Authored local fixture'});
    return request('records/'+row.id,{...row,task:'image_caption',annotation:{caption:'Earlier '+name},review:'human_reviewed'});
  }
  const rows=[await image('Blue source','blue'),await image('Red source','red'),await image('Green source','green')];
  const saved=await request('selections',{name:'Fixed caption set',items:rows.map(ref)});
  const modelPort=output.match(/CAPTION_MODEL_PORT=(\d+)/)[1];
  await send('Page.enable');await send('Runtime.enable');await send('Page.setLifecycleEventsEnabled',{enabled:true});
  await send('Page.navigate',{url:base+'/workbench'});await until(()=>evaluate('document.getElementById("notice")?.textContent === "Collection ready."'));
  await evaluate('refreshSavedSets('+JSON.stringify(saved.id)+')');await click('load-selection');await until(()=>evaluate('!savedLoadBusy && selected.size===3'));
  const fixed=await evaluate('releaseBody().items');
  const open=async id=>{await evaluate('openRecord('+JSON.stringify(id)+')');await until(()=>evaluate('current?.id==='+JSON.stringify(id)));};
  await open(rows[0].id);
  await evaluate('document.getElementById("caption-proposal-panel").open=true');
  await fill('caption-proposal-url','http://127.0.0.1:'+modelPort);await click('caption-proposal-models');
  await until(()=>evaluate('document.getElementById("caption-proposal-model").options.length===2'));
  assert.ok((await evaluate('document.getElementById("caption-proposal-status").textContent')).includes('does not establish vision'));
  await fill('caption-proposal-model','caption-fixture');
  const clickAction=async id=>{await click(id);await until(()=>evaluate('!document.getElementById('+JSON.stringify(id)+').dataset.busy'));};
  const start=async guidance=>{
    await fill('caption-proposal-guidance',guidance);
    await evaluate('document.getElementById("caption-proposal-form").requestSubmit();document.getElementById("caption-proposal-form").requestSubmit();');
    await until(()=>evaluate('!captionProposalBusy'));
  };
  const refresh=async()=>{await click('caption-proposal-refresh');await until(()=>evaluate('!document.getElementById("caption-proposal-refresh").dataset.busy'));};
  const jobButton=async label=>{
    await evaluate('(()=>{const button=[...document.querySelectorAll("#caption-proposal-jobs button")].find(b=>b.textContent==='+JSON.stringify(label)+');if(!button)throw Error("Missing caption action");button.click();button.click();})()');
    await until(()=>evaluate('!captionProposalBusy'));
  };
  // A served text-only entry is not promoted to a vision capability.
  await fill('caption-proposal-model','text-only');await start('Describe visible pixels');
  await until(()=>evaluate('captionProposalJobs.some(j=>j.status==="failed")'));assert.equal((await request('records/'+rows[0].id)).revision,rows[0].revision);
  await fill('caption-proposal-model','caption-fixture');
  // Hold admission, refresh through a real exact-ID 404, then lose the persisted acknowledgement.
  await evaluate('window.captionNativeFetch=window.fetch;window.captionLostStart=true;window.captionHoldStart=true;window.captionStartHeld=false;window.captionPostedIds=[];window.fetch=async(...args)=>{const start=args[0]==="/api/workbench/caption-proposals" && args[1]?.method==="POST";if(start){captionPostedIds.push(JSON.parse(args[1].body).request_id);if(captionHoldStart){captionHoldStart=false;captionStartHeld=true;await new Promise(resolve=>window.captionStartRelease=resolve);}}const r=await captionNativeFetch(...args);if(captionLostStart && start){captionLostStart=false;throw Error("Controlled lost start acknowledgement");}return r;};');
  const beforeStart=(await request('caption-proposals')).jobs.length;
  const requestCount=async()=> (await(await fetch('http://127.0.0.1:'+modelPort+'/test/request-count')).json()).requests;
  const beforeInference=await requestCount();await fill('caption-proposal-guidance','Describe the visible rectangle');
  await evaluate('document.getElementById("caption-proposal-form").requestSubmit();document.getElementById("caption-proposal-form").requestSubmit()');await until(()=>evaluate('captionStartHeld'));
  const recoveryId=await evaluate('captionProposalPendingRequest.request_id');await refresh();
  assert.equal(await evaluate('captionProposalPendingRequest?.request_id'),recoveryId,'Early real 404 must retain admission identity');
  assert.equal(await requestCount(),beforeInference,'Held admission must not start inference');
  await evaluate('captionStartRelease()');await until(()=>evaluate('!captionProposalBusy'));assert.equal(await evaluate('captionProposalPendingRequest?.request_id'),recoveryId);
  const beforeReloadPostedIds=await evaluate('captionPostedIds');
  await until(async()=> (await request('caption-proposals/'+recoveryId)).status==='completed');
  // A full new document restores sessionStorage before its first held reconciliation.
  const reloadHook=await send('Page.addScriptToEvaluateOnNewDocument',{source:'window.captionNativeFetch=window.fetch;window.captionHoldReconcile=true;window.captionReconcileHeld=false;window.captionPostedIds=[];window.fetch=async(...args)=>{if(args[0]==="/api/workbench/caption-proposals" && args[1]?.method!=="POST" && captionHoldReconcile){captionHoldReconcile=false;captionReconcileHeld=true;await new Promise(resolve=>window.captionReconcileRelease=resolve);}if(args[0]==="/api/workbench/caption-proposals" && args[1]?.method==="POST")captionPostedIds.push(JSON.parse(args[1].body).request_id);return captionNativeFetch(...args);};'});
  const previousFrame=(await send('Page.getFrameTree')).frameTree.frame;
  await send('Page.reload');await until(()=>pageLoads.reloaded(previousFrame));
  await until(()=>evaluate('document.getElementById("notice")?.textContent==="Collection ready."'));await open(rows[0].id);
  await until(()=>evaluate('captionReconcileHeld'));
  assert.equal(await evaluate('captionProposalPendingRequest?.request_id'),recoveryId,'A full reload must synchronously restore the unresolved ID');
  assert.equal(await evaluate('document.getElementById("caption-proposal-guidance").value'),'Describe the visible rectangle','Exact original retry guidance must restore');
  await start('Changed guidance during held reload reconciliation');
  assert.deepEqual(await evaluate('captionPostedIds'),[],'Changed intent must never reach POST before reconciliation');
  assert.equal(await requestCount(),beforeInference+1);
  await start('Describe the visible rectangle');const recoveryPostedIds=[...beforeReloadPostedIds,...await evaluate('captionPostedIds')];assert.deepEqual(recoveryPostedIds,[recoveryId,recoveryId],'Explicit repeat after reload must reuse the exact admission ID');
  await evaluate('captionReconcileRelease()');await send('Page.removeScriptToEvaluateOnNewDocument',{identifier:reloadHook.identifier});
  await refresh();await until(()=>evaluate('captionProposalJobs.some(j=>j.status==="completed")'));
  assert.equal((await request('caption-proposals')).jobs.length,beforeStart+1);assert.equal(await evaluate('captionProposalPendingRequest'),null);
  assert.equal(await requestCount(),beforeInference+1,'Lost-start recovery must run the image backend exactly once');
  const job=(await request('caption-proposals')).jobs.find(j=>j.status==='completed');
  const evidence=await request('caption-proposals/'+job.id);
  const crypto=require('node:crypto'),digest=bytes=>crypto.createHash('sha256').update(bytes).digest('hex');
  assert.equal(digest(Buffer.from(evidence.input_image_base64,'base64')),evidence.input_image.sha256);
  assert.equal(digest(Buffer.from(evidence.raw_response_base64,'base64')),evidence.response_sha256);
  assert.deepEqual(ref(await request('records/'+rows[0].id)),ref(rows[0]),'A completed proposal cannot save a target');
  await jobButton('Inspect request evidence');assert.ok(await evaluate('document.querySelector("#caption-proposal-jobs pre").textContent.includes("canonical_request_sha256")'));
  // Lose a real apply acknowledgement. The target commits once; refresh exposes its receipt.
  await evaluate('window.captionLostApply=true;window.fetch=async(...args)=>{const r=await captionNativeFetch(...args);if(captionLostApply && String(args[0]).includes("caption-proposals/decide/") && args[1]?.method==="POST"){captionLostApply=false;throw Error("Controlled lost apply acknowledgement");}return r;};');
  await jobButton('Apply as draft');
  const applied=await request('records/'+rows[0].id);assert.equal(applied.revision,rows[0].revision+1);assert.equal(applied.review,'draft');
  assert.equal(applied.target_proposal.job_id,job.id);assert.deepEqual(applied.provenance,rows[0].provenance);
  assert.deepEqual(await evaluate('releaseBody().items'),fixed,'Application must retain fixed pairs');
  assert.ok((await evaluate('document.getElementById("caption-proposal-status").textContent')).includes('acknowledgement'));
  await refresh();assert.equal((await request('caption-proposals/'+job.id)).status,'applied');
  const repeated=await request('caption-proposals/decide/'+job.id,{revision:job.revision,decision:'apply_draft'});assert.equal(repeated.changed,false);assert.equal(repeated.record.revision,applied.revision);
  await jobButton('Open applied caption');assert.equal(await evaluate('current.review'),'draft');assert.equal(await evaluate('document.getElementById("record-review").value'),'draft');
  assert.equal((await request('selections/'+saved.id)).members.find(m=>m.item.id===rows[0].id).status,'stale');
  // Current draft blocks the caption format; explicit review remains a separate action.
  await fill('release-format','image_caption_v1');await evaluate('refresh()');await clickAction('clear-selection');await clickAction('select-page');await click('preview-release');
  await until(()=>evaluate('!releaseBusy && !!releasePreview'));
  assert.equal(await evaluate('releasePreview.eligible'),false);
  await fill('record-review','human_reviewed');await evaluate('document.getElementById("editor").requestSubmit()');
  await until(()=>evaluate('!document.getElementById("editor").dataset.busy && current.review==="human_reviewed"'));
  await clickAction('clear-selection');await clickAction('select-page');await fill('train',34);await fill('validation',33);await fill('test',33);await click('preview-release');await until(()=>evaluate('!document.getElementById("freeze-release").disabled'));
  await evaluate('document.getElementById("release-form").requestSubmit()');await until(()=>evaluate('!!document.querySelector("#release-result a")'));
  const archiveURL=await evaluate('document.querySelector("#release-result a").href');const archive=await fetch(archiveURL);assert.equal(archive.status,200);
  const zipPath=path.join(report,'caption-proposals-downloaded.zip');fs.writeFileSync(zipPath,Buffer.from(await archive.arrayBuffer()));
  const {execFileSync}=require('node:child_process'),expanded=path.join(temporary,'expanded');
  execFileSync('python3',['-c','import sys,zipfile;zipfile.ZipFile(sys.argv[1]).extractall(sys.argv[2])',zipPath,expanded]);
  const consumer=execFileSync('python3',['tests/fixtures/diffusion_check_image_data.py',expanded],{cwd:root,encoding:'utf8'});assert.ok(consumer.includes('PASS: 3 records'));
  const manifest=JSON.parse(fs.readFileSync(path.join(expanded,'manifest.json')));assert.equal(manifest.records.find(r=>r.id===rows[0].id).target_proposal.job_id,job.id);
  fs.writeFileSync(path.join(report,'consumer.log'),consumer);
  // Rejection has no target effect. An active request survives editor navigation until explicit cancel.
  await start('Describe visible pixels');await until(()=>evaluate('captionProposalJobs.some(j=>j.status==="completed")'));
  let reviewed=await request('records/'+rows[0].id);
  // Hold a real committed annotation-save acknowledgement; Reject cannot revoke its editor ownership.
  await evaluate('window.captionHoldSave=true;window.captionSaveHeld=false;window.fetch=async(...args)=>{const r=await captionNativeFetch(...args);if(captionHoldSave && args[0]==='+JSON.stringify('/api/workbench/records/'+rows[0].id)+' && args[1]?.method==="POST"){captionHoldSave=false;captionSaveHeld=true;await new Promise(resolve=>window.captionSaveRelease=resolve);}return r;};');
  await fill('record-review','human_reviewed');await evaluate('document.getElementById("editor").requestSubmit()');await until(()=>evaluate('captionSaveHeld'));
  const committedSave=await request('records/'+rows[0].id);assert.equal(committedSave.revision,reviewed.revision+1);
  await jobButton('Reject caption proposal');assert.deepEqual(await request('records/'+rows[0].id),committedSave,'Reject cannot change the saved annotation');
  await evaluate('captionSaveRelease()');await until(()=>evaluate('!document.getElementById("editor").dataset.busy'));
  assert.equal(await evaluate('current.revision'),committedSave.revision,'Held save acknowledgement must retain editor ownership');assert.equal(await evaluate('dirty'),false);
  await fill('record-review','human_reviewed');await evaluate('document.getElementById("editor").requestSubmit()');await until(()=>evaluate('!document.getElementById("editor").dataset.busy'));
  reviewed=await request('records/'+rows[0].id);assert.equal(reviewed.revision,committedSave.revision+1,'Subsequent real annotation save must use the accepted revision');assert.equal(await evaluate('current.revision'),reviewed.revision);assert.equal(await evaluate('dirty'),false);
  await start('slow');await until(()=>evaluate('captionProposalJobs.some(j=>j.status==="generating")'));
  await open(rows[1].id);assert.equal(await evaluate('document.getElementById("caption-proposal-jobs").textContent'),'');
  await open(rows[0].id);await until(()=>evaluate('document.getElementById("caption-proposal-jobs").textContent.includes("generating")'));
  await jobButton('Cancel caption request');await until(async()=>{await refresh();return evaluate('captionProposalJobs.some(j=>j.status==="cancelled")');});
  assert.deepEqual(await request('records/'+rows[0].id),reviewed);
  const cancelled=(await request('caption-proposals')).jobs.find(j=>j.status==='cancelled');
  await start('Fresh intent after explicit cancellation');await until(()=>evaluate('captionProposalJobs.some(j=>j.status==="completed" && j.config.instruction==="Fresh intent after explicit cancellation")'));
  const fresh=(await request('caption-proposals')).jobs.find(j=>j.config.instruction==='Fresh intent after explicit cancellation');assert.notEqual(fresh.id,cancelled.id);assert.deepEqual(await request('records/'+rows[0].id),reviewed);
  const count=(await request('caption-proposals')).jobs.length;
  await send('Page.navigate',{url:base+'/'});await until(()=>evaluate('location.pathname==="/" && document.readyState==="complete"'));
  const history=await send('Page.getNavigationHistory');await send('Page.navigateToHistoryEntry',{entryId:history.entries[history.currentIndex-1].id});
  await until(()=>evaluate('location.pathname==="/workbench" && document.getElementById("notice")?.textContent==="Collection ready."'));
  await open(rows[0].id);await refresh();assert.equal((await request('caption-proposals')).jobs.length,count,'Browser navigation must not restart inference');
  await send('Page.reload');await until(()=>evaluate('document.getElementById("notice")?.textContent==="Collection ready."'));await open(rows[0].id);await refresh();
  assert.equal((await request('caption-proposals')).jobs.length,count);assert.equal(await evaluate('current.target_proposal.job_id'),job.id);
  await evaluate('document.getElementById("caption-proposal-panel").open=true;document.getElementById("caption-proposal-panel").scrollIntoView();');
  const desktop=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});fs.writeFileSync(path.join(report,'caption-proposals-desktop.png'),Buffer.from(desktop.data,'base64'));
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
  assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'),'Narrow proposal layout must not overflow');
  await evaluate('document.getElementById("caption-proposal-panel").scrollIntoView();');
  const narrow=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});fs.writeFileSync(path.join(report,'caption-proposals-narrow.png'),Buffer.from(narrow.data,'base64'));
  // Keyboard controls remain real native form controls.
  await evaluate('document.getElementById("caption-proposal-guidance").focus();document.getElementById("caption-proposal-guidance").select()');await send('Input.insertText',{text:'Describe the actual visible image.'});
  assert.equal(await evaluate('document.getElementById("caption-proposal-guidance").value'),'Describe the actual visible image.');
  // A storage write failure refuses admission before any network/model side effect.
  await fill('caption-proposal-url','http://127.0.0.1:'+modelPort);await click('caption-proposal-models');
  await until(()=>evaluate('document.getElementById("caption-proposal-model").options.length===2'));await fill('caption-proposal-model','caption-fixture');
  const beforeStorageFailure=await requestCount(),jobsBeforeStorageFailure=(await request('caption-proposals')).jobs.length;
  await evaluate('window.captionStorageSet=Storage.prototype.setItem;Storage.prototype.setItem=function(key,value){if(key===captionProposalRecoveryKey)throw Error("Controlled storage quota failure");return captionStorageSet.call(this,key,value);};');
  await start('Storage unavailable');
  assert.equal(await requestCount(),beforeStorageFailure);assert.equal((await request('caption-proposals')).jobs.length,jobsBeforeStorageFailure);
  assert.equal(await evaluate('document.getElementById("caption-proposal-submit").disabled'),true);
  await evaluate('Storage.prototype.setItem=captionStorageSet');
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(report,'session.json'),JSON.stringify({source_head:require('node:child_process').execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),model:'controlled local HTTP fixture',fixed,job_id:job.id,application_revision:applied.revision,recovery_id:recoveryId,recovery_post_ids:recoveryPostedIds,recovery_backend_requests:1,reload_changed_intent_posts:0,storage_failure_posts:0,reject_save_revision:committedSave.revision,subsequent_save_revision:reviewed.revision,cancelled_id:cancelled.id,fresh_intent_id:fresh.id,downloaded_zip_sha256:digest(fs.readFileSync(zipPath)),consumer:'unchanged pinned diffusion_check_image_data.py',real_model_quality:false,tests:'held admission/early real 404/lost start acknowledgement/full new-document reload/held reconciliation/changed-intent refusal/exact-ID repeat runs backend once/storage-write failure before POST, held annotation-save/reject/acknowledgement/subsequent save, explicit cancelled/new intent, request/apply double clicks, exact image evidence, unsupported vision, lost apply acknowledgement, idempotency, fixed stale selection, draft block, human review, ZIP consumption, navigation/reload, keyboard and narrow layout'},null,2));
  console.log('Caption proposal real HTTP/Chromium controlled lifecycle, lost-response recovery, draft review separation, navigation and pinned consumer passed.');
})().catch(async error=>{console.error(error);console.error('Runtime errors:',JSON.stringify(errors));if(inspect)try{console.error('Page diagnostics:',await inspect());}catch(diagnostic){console.error('Diagnostics failed:',diagnostic);}process.exitCode=1;}).finally(async()=>{if(ws)ws.close();for(const child of children)child.kill();await pause(200);fs.rmSync(temporary,{recursive:true,force:true});});
