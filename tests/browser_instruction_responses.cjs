// Real manifest files, HTTP admission, cancellation, persistence and Chromium.
'use strict';
const {qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn,spawnSync}=require('node:child_process'),crypto=require('node:crypto');
const {pageLoadTracker}=require('./browser_page_load.cjs');
const root=path.resolve(__dirname,'..'),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-instruction-browser-')),children=[];
const errors=[],tracker=pageLoadTracker(),pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
let ws,inspect;
async function until(fn){for(let i=0;i<150;i++){const value=await fn();if(value)return value;await pause(100);}throw Error('Timed out');}
function launch(command,args,options={}){const child=spawn(command,args,options);children.push(child);return child;}
function python(code,...args){const result=spawnSync('python3',['-c',code,...args],{cwd:root,encoding:'utf8'});assert.equal(result.status,0,result.stderr);return result.stdout;}
(async()=>{
  const server=launch('python3',['-u','app.py','--port','0','--data',path.join(temporary,'data')],{cwd:root,stdio:['ignore','pipe','pipe']});
  let output='';server.stdout.on('data',data=>output+=data);server.stderr.on('data',data=>{if(process.env.BULK_BROWSER_DEBUG)process.stderr.write(data);});
  const port=await until(()=>output.match(/127\.0\.0\.1:(\d+)/)?.[1]),base='http://127.0.0.1:'+port;
  const api=async(route,body)=>{const response=await fetch(base+'/api/workbench/'+route,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const result=await response.json();assert.ok(response.ok,JSON.stringify(result));return result;};
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
  inspect=()=>evaluate('JSON.stringify({url:location.href,notice:document.getElementById("notice")?.textContent,responseStatus:document.getElementById("response-status")?.textContent,responseBusy,responseListBusy,responseDirty,responsePreview:responsePreview?.eligible,responseSelected:[...responseSelected.values()],release:document.getElementById("release-preview-status")?.textContent,releaseBusy,preview:releasePreview?.eligible,results:document.getElementById("caption-results")?.textContent,body:document.body?.innerText.slice(0,1800)})');
  const click=id=>evaluate('document.getElementById('+JSON.stringify(id)+').click()');
  await send('Page.enable');await send('Page.setLifecycleEventsEnabled',{enabled:true});await send('Runtime.enable');
  console.log('Instruction browser targets:',JSON.stringify(tabs.map(tab=>({type:tab.type,url:tab.url}))));
  console.log('Instruction browser version:',JSON.stringify(await send('Browser.getVersion')));
  assert.ok(!(await send('Page.navigate',{url:base+'/workbench'})).errorText);
  await until(()=>evaluate('document.getElementById("notice")?.textContent==="Collection ready."'));
  const fill=(id,value)=>evaluate('(()=>{const e=document.getElementById('+JSON.stringify(id)+');e.value='+JSON.stringify(value)+';e.dispatchEvent(new Event("input",{bubbles:true}));e.dispatchEvent(new Event("change",{bubbles:true}));})()');
  const submit=async id=>{await evaluate('document.getElementById('+JSON.stringify(id)+').requestSubmit()');await until(()=>evaluate('!document.getElementById('+JSON.stringify(id)+').dataset.busy'));};
  const filter=()=>submit('filters');
  const reports=qaDirectory(root,'instruction-responses');fs.mkdirSync(reports,{recursive:true});
  const identity=spawnSync('git',['rev-parse','HEAD','HEAD^{tree}'],{cwd:root,encoding:'utf8'}).stdout.trim().split('\n');
  const diff=spawnSync('git',['diff','HEAD','--','workbench.py','dataset_releases.py','app.py','static','tests'],{cwd:root,encoding:'utf8'}).stdout;
  const evidence={source_head:identity[0],source_tree:identity[1],source_state:diff?'working_tree':'committed',source_diff_sha256:crypto.createHash('sha256').update(diff).digest('hex'),browser:await send('Browser.getVersion'),screenshots:[],steps:[]};
  const ref=(parent,answer)=>({id:answer.id,revision:answer.revision,prompt_id:parent.id,parent_revision:parent.revision,source_revision:parent.source_revision});
  const pairs=()=>evaluate('responseReleaseBody().items');
  async function open(parent){await evaluate('openRecord('+JSON.stringify(parent.id)+')');await until(()=>evaluate('current?.id==='+JSON.stringify(parent.id)+' && !responseListBusy && responseParent?.id==='+JSON.stringify(parent.id)));}
  async function saveAnswer(content){await click('response-new');await fill('response-entry-format','json');await fill('response-completion',JSON.stringify(content));assert.equal(await evaluate('document.getElementById("response-review").value'),'draft');await fill('response-review','human_reviewed');await evaluate('document.getElementById("response-form").requestSubmit()');await until(()=>evaluate('!responseBusy && !responseListBusy && !responseDirty'));}
  async function preview(){await click('response-preview');await until(()=>evaluate('!responseReleaseBusy && !!responsePreview'));return evaluate('responsePreview');}
  async function capture(name,selector){for(const narrow of [false,true]){
    const viewport={width:narrow?390:1400,height:narrow?844:1000};await send('Emulation.setDeviceMetricsOverride',{...viewport,deviceScaleFactor:1,mobile:false});await evaluate('document.querySelector('+JSON.stringify(selector)+').scrollIntoView({block:"start"})');await pause(100);assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'),'Horizontal overflow');
    const shot=Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'),file='instruction-'+name+(narrow?'-narrow':'-desktop')+'.jpg';fs.writeFileSync(path.join(reports,file),shot);evidence.screenshots.push({file,viewport,selector,sha256:crypto.createHash('sha256').update(shot).digest('hex')});
  }await send('Emulation.setDeviceMetricsOverride',{width:1400,height:1000,deviceScaleFactor:1,mobile:false});}
  const imported=[];for(const name of ['primary','second','third'])imported.push(await api('import',{kind:'text',name,text:' prompt '+name+'\r\ne\u0301 😀 ',groups:['instruction-'+name],rights:'Authored QA fixture'}));
  let primary=await api('records/'+imported[0].id,{...imported[0],task:'text_entities',annotation:{spans:[{label:'prompt',start:1,end:7}]},review:'human_reviewed'});
  const bridge=await api('import',{kind:'text',name:'Unselected bridge',text:'Unselected family context.',groups:['bridge'],parents:[primary.id],rights:'Authored QA fixture'});
  await open(primary);await click('response-new');await fill('response-entry-format','json');const exact='\ufeff e\u0301\r\n😀 '+ 'x'.repeat(1100)+'  ';await fill('response-completion',JSON.stringify(exact));await fill('response-review','human_reviewed');
  await evaluate(`window.answerBaseFetch=window.fetch;window.answerRelease=null;window.answerHoldOnce=true;window.answerSaves=0;window.fetch=async(...args)=>{if(String(args[0]).endsWith('/responses')&&args[1]?.method==='POST')++answerSaves;const response=await answerBaseFetch(...args);if(String(args[0]).endsWith('/responses')&&args[1]?.method==='POST'&&answerHoldOnce){answerHoldOnce=false;await new Promise(resolve=>answerRelease=resolve);}return response;};`);
  await evaluate('document.getElementById("response-form").requestSubmit();document.getElementById("response-form").requestSubmit()');await until(()=>evaluate('!!answerRelease'));assert.equal(await evaluate('answerSaves'),1);
  assert.equal((await api('records/'+primary.id+'/responses')).responses.length,1);
  await fill('response-completion',JSON.stringify('Later unsaved answer 😀 '));await evaluate('window.confirm=()=>false');await evaluate('openRecord('+JSON.stringify(imported[1].id)+')');assert.equal(await evaluate('current.id'),primary.id);
  const unload=await evaluate('(()=>{const event=new Event("beforeunload",{cancelable:true});window.dispatchEvent(event);return event.defaultPrevented;})()');assert.equal(unload,true);
  await evaluate('answerRelease();answerRelease=null');await until(()=>evaluate('!responseBusy && !responseListBusy'));assert.equal(await evaluate('responseDirty'),true);assert.equal(await evaluate('responseCompletion()'),'Later unsaved answer 😀 ');assert.equal(await evaluate('document.getElementById("response-review").value'),'draft');
  await click('response-cancel');await evaluate('window.fetch=answerBaseFetch;window.confirm=()=>true');await saveAnswer(' another accepted answer \ufeff ');
  let rows=(await api('records/'+primary.id+'/responses')).responses;assert.equal(rows.length,2);const first=rows.find(row=>row.completion===exact),second=rows.find(row=>row.id!==first.id);assert.ok(first);assert.deepEqual(await api('records/'+primary.id),primary);
  // Hold actual parent GET acknowledgments after navigation/reload begins, then edit the still-visible answer.
  await evaluate('refresh()');const heldParentLoads=[];
  for(const operation of ['navigation','reload'])for(const intent of ['completion','review']){
    await evaluate('document.querySelector('+JSON.stringify('#response-list button[data-response-id="'+first.id+'"]')+').click()');
    const targetID=operation==='reload'?primary.id:imported[1].id;
    await evaluate(`window.parentRaceFetch=window.fetch;window.parentRaceRelease=null;window.parentRaceDone=false;window.parentRaceConfirms=0;window.confirm=()=>{++parentRaceConfirms;return true;};window.fetch=async(...args)=>{const response=await parentRaceFetch(...args);if(String(args[0])==='/api/workbench/records/${targetID}'&&!args[1]?.method)await new Promise(resolve=>parentRaceRelease=resolve);return response;};`);
    if(operation==='reload')await click('reload');
    else await evaluate(`window.parentRaceTask=[...document.querySelectorAll('#records button')].find(button=>button.textContent.startsWith('second')).onclick();parentRaceTask.then(()=>parentRaceDone=true);void 0;`);
    await until(()=>evaluate('!!parentRaceRelease'));
    if(intent==='completion')await fill('response-completion',JSON.stringify('Later held parent-load edit\r\n😀 '));
    else await fill('response-review','draft');
    const draft=await evaluate('JSON.stringify({completion:responseCompletion(),review:document.getElementById("response-review").value,editor:responseEditor})');
    assert.equal(await evaluate('responseDirty'),true);assert.equal(await evaluate('dirty'),false);
    await evaluate('parentRaceRelease();parentRaceRelease=null');
    await until(()=>evaluate(operation==='reload'?'!document.getElementById("reload").dataset.busy':'parentRaceDone'));
    assert.equal(await evaluate('current.id'),primary.id,operation+' cannot adopt a parent over newer answer '+intent);
    assert.equal(await evaluate('responseParent.id'),primary.id);assert.equal(await evaluate('responseDirty'),true);
    assert.equal(await evaluate('document.getElementById("response-form").hidden'),false);
    assert.equal(await evaluate('JSON.stringify({completion:responseCompletion(),review:document.getElementById("response-review").value,editor:responseEditor})'),draft);
    assert.equal(await evaluate('parentRaceConfirms'),0,'Starting a clean load grants no discard of later edits');
    await evaluate('window.fetch=parentRaceFetch');await click('response-cancel');heldParentLoads.push({operation,intent,newer_draft_retained:true});
  }
  evidence.steps.push({stage:'held-parent-record-loads',cases:heldParentLoads});
  await evaluate('document.querySelectorAll("#response-list input[type=checkbox]").forEach(e=>e.click())');assert.equal(await evaluate('responseSelected.size'),2);assert.equal(await evaluate('selected.size'),0);
  await evaluate('document.querySelector('+JSON.stringify('#response-list button[data-response-id="'+first.id+'"]')+').click()');assert.equal(await evaluate('responseCompletion()'),exact);assert.equal(await evaluate('document.getElementById("response-entry-format").value'),'json');await fill('response-entry-format','text');assert.equal(await evaluate('document.getElementById("response-entry-format").value'),'json');assert.equal(await evaluate('responseDirty'),false);
  await capture('01-independent-answers','#responses-panel');const fixed=await pairs();let proof=await preview();assert.equal(proof.eligible,true);assert.equal(proof.example_count,2);assert.equal(proof.unique_prompt_count,1);
  await fill('rights-filter','No matching note');await filter();assert.equal(await evaluate('page.total'),0);assert.deepEqual(await pairs(),fixed);assert.equal(await evaluate('selected.size'),0);
  const unselected=await api('responses',{id:crypto.randomUUID().replaceAll('-',''),prompt_id:primary.id,revision:0,parent_revision:primary.revision,source_revision:primary.source_revision,completion:'Unselected draft',review:'draft'});await click('response-refresh');await until(()=>evaluate('!responseListBusy&&responseRows.length===3'));assert.deepEqual(await pairs(),fixed);assert.equal(await evaluate('responsePreview.preview_token'),proof.preview_token);
  let changed=await api('responses',{...ref(primary,first),completion:exact+' changed',review:'draft'});
  await evaluate(`window.staleBaseFetch=window.fetch;window.staleRelease=null;window.staleOnce=true;window.staleStatus=null;window.refreshProofs=0;window.fetch=async(...args)=>{if(String(args[0]).endsWith('/releases/preview'))++refreshProofs;const response=await staleBaseFetch(...args);if(String(args[0]).endsWith('/releases')&&staleOnce){staleOnce=false;staleStatus=response.status;await new Promise(resolve=>staleRelease=resolve);}return response;};`);
  await evaluate('document.getElementById("response-release-form").requestSubmit()');await until(()=>evaluate('!!staleRelease'));assert.equal(await evaluate('staleStatus'),409);assert.equal(await evaluate('responseReleaseBusy'),true);await click('response-preview');assert.equal(await evaluate('refreshProofs'),0);
  await evaluate('staleRelease();staleRelease=null');await until(()=>evaluate('!responseReleaseBusy&&responsePreview===null'));assert.equal(await evaluate('document.getElementById("response-freeze").disabled'),true);await evaluate('window.fetch=staleBaseFetch');proof=await preview();assert.equal(proof.eligible,false);assert.deepEqual(await pairs(),fixed);await capture('02-stale-fixed-selection','#response-release-panel');
  await click('response-refresh');await until(()=>evaluate('!responseListBusy'));await evaluate('document.querySelector('+JSON.stringify('#response-list button[data-response-id="'+first.id+'"]')+').click()');await fill('response-review','human_reviewed');await evaluate('document.getElementById("response-form").requestSubmit()');await until(()=>evaluate('!responseBusy&&!responseListBusy&&!responseDirty'));assert.deepEqual(await pairs(),fixed);
  await evaluate('document.querySelectorAll("#response-list input[type=checkbox]").forEach(e=>{if(e.checked){e.click();e.click();}})');assert.notDeepEqual(await pairs(),fixed);proof=await preview();assert.equal(proof.eligible,true);
  await api('records/'+bridge.id,{...bridge,task:'text_classification',annotation:{label:'changed lineage'},review:'draft'});
  await evaluate('document.getElementById("response-release-form").requestSubmit()');await until(()=>evaluate('!responseReleaseBusy&&responsePreview===null'));assert.match(await evaluate('document.getElementById("response-preview-status").textContent'),/Release preview changed/);
  // A parent target edit is independent but supersedes the fixed parent pair.
  primary=await api('records/'+primary.id,{...primary,task:'text_entities',annotation:primary.annotation,review:'human_reviewed'});proof=await preview();assert.equal(proof.eligible,false);
  await open(primary);await evaluate('document.querySelectorAll("#response-list input[type=checkbox]").forEach(e=>{if(e.checked){e.click();e.click();}})');
  for(const parent of imported.slice(1)){await open(parent);await saveAnswer('Reviewed answer for '+parent.name);await evaluate('document.querySelector("#response-list input[type=checkbox]").click()');}
  assert.equal(await evaluate('responseSelected.size'),4);await fill('response-train','50');await fill('response-validation','25');await fill('response-test','25');proof=await preview();assert.equal(proof.eligible,true);assert.deepEqual(proof.split_report.actual_counts,{train:2,validation:1,test:1});assert.equal(proof.unique_prompt_count,3);
  const finalPairs=await pairs();await capture('03-weighted-preview','#response-release-panel');
  const downloads=path.join(temporary,'downloads');fs.mkdirSync(downloads);await send('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:downloads,eventsEnabled:true});await click('response-selection-save');await until(()=>fs.readdirSync(downloads).some(name=>name.endsWith('.json')));const selectionFile=path.join(downloads,fs.readdirSync(downloads).find(name=>name.endsWith('.json')));const selection=JSON.parse(fs.readFileSync(selectionFile,'utf8'));assert.deepEqual(selection.items,finalPairs);
  await send('Page.navigate',{url:base+'/workbench'});await until(()=>evaluate('document.getElementById("notice")?.textContent==="Collection ready."'));assert.equal(await evaluate('responseSelected.size'),0);
  const selectionBytes=fs.readFileSync(selectionFile).toString('base64');await evaluate(`(()=>{const data=new DataTransfer();data.items.add(new File([Uint8Array.from(atob(${JSON.stringify(selectionBytes)}),c=>c.charCodeAt(0))],'fixed-answers.json',{type:'application/json'}));const input=document.getElementById('response-selection-file');input.files=data.files;input.dispatchEvent(new Event('change'));})()`);await until(()=>evaluate('responseSelected.size===4'));assert.deepEqual(await pairs(),finalPairs);
  await fill('rights-filter','No matching note');await filter();assert.equal(await evaluate('page.total'),0);assert.deepEqual(await pairs(),finalPairs);
  await fill('response-train','50');await fill('response-validation','25');await fill('response-test','25');const reopened=await preview();assert.equal(reopened.preview_token,proof.preview_token);
  await evaluate('document.getElementById("response-release-form").requestSubmit();document.getElementById("response-release-form").requestSubmit()');await until(()=>evaluate('!responseReleaseBusy&&!!document.querySelector("#response-release-result a")'));await evaluate('document.querySelector("#response-release-result a").click()');await until(()=>fs.readdirSync(downloads).some(name=>name.endsWith('.zip')));const archive=path.join(downloads,fs.readdirSync(downloads).find(name=>name.endsWith('.zip')));
  const consumerRun=spawnSync(process.env.INSTRUCTION_CONSUMER_PYTHON||'python3',['tests/check_instruction_consumer.py',archive],{cwd:root,encoding:'utf8',timeout:120000});assert.equal(consumerRun.status,0,consumerRun.stdout+'\n'+consumerRun.stderr);const consumer=JSON.parse(consumerRun.stdout.trim().split('\n').at(-1));assert.equal(consumer.result,'PASS');assert.equal(consumer.examples,4);assert.equal(consumer.over_default_1024_tokens,true);
  const bytes=fs.readFileSync(archive);assert.equal(consumer.zip_sha256,crypto.createHash('sha256').update(bytes).digest('hex'));fs.writeFileSync(path.join(reports,'instruction-downloaded.zip'),bytes);
  evidence.steps.push({stage:'held-real-create-acknowledgment',single_request:true,later_editor_intent_retained:true,parent_annotation_preserved:true},{stage:'exact-selection-staleness',original_pairs:fixed,final_pairs:finalPairs,selected_response_and_parent_and_unselected_lineage_rejected:true,unselected_sibling_does_not_expand_selection:true},{stage:'actual-download-and-consumer',selection,preview:reopened,consumer,zip_bytes:bytes.length});await capture('04-download','#response-release-panel');
  assert.deepEqual(errors,[]);evidence.errors=errors;evidence.result='PASS';fs.writeFileSync(path.join(reports,'instruction-session.json'),JSON.stringify(evidence,null,2)+'\n');console.log('PASS actual Chromium two independent answers + retained entity annotation, held create and parent navigation/reload/repeated controls/later edits, exact Unicode/review, response/parent/bridge freshness, fixed file reopen/filter separation, weighted families, actual ZIP download and unchanged pinned consumer; desktop/narrow.');
})().catch(async error=>{console.error(error);console.error('Runtime errors:',JSON.stringify(errors));if(inspect)try{console.error('Page diagnostics:',await inspect());}catch(diagnostic){console.error('Diagnostics failed:',diagnostic);}process.exitCode=1;}).finally(async()=>{if(ws)ws.close();for(const child of children)child.kill();await pause(200);fs.rmSync(temporary,{recursive:true,force:true});});
