// Real manifest files, HTTP admission, cancellation, persistence and Chromium.
'use strict';
const {qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn,spawnSync}=require('node:child_process'),crypto=require('node:crypto');
const {pageLoadTracker}=require('./browser_page_load.cjs');
const root=path.resolve(__dirname,'..'),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-grounded-instruction-browser-')),children=[];
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
  const reports=qaDirectory(root,'grounded-instructions');fs.mkdirSync(reports,{recursive:true});
  const identity=spawnSync('git',['rev-parse','HEAD','HEAD^{tree}'],{cwd:root,encoding:'utf8'}).stdout.trim().split('\n');
  const diff=spawnSync('git',['diff','HEAD','--','workbench.py','dataset_releases.py','app.py','static','tests'],{cwd:root,encoding:'utf8'}).stdout;
  const evidence={source_head:identity[0],source_tree:identity[1],source_state:diff?'working_tree':'committed',source_diff_sha256:crypto.createHash('sha256').update(diff).digest('hex'),browser:await send('Browser.getVersion'),screenshots:[],steps:[]};
  const ref=(parent,answer)=>({id:answer.id,revision:answer.revision,prompt_id:parent.id,parent_revision:parent.revision,source_revision:parent.source_revision});
  const pairs=()=>evaluate('responseReleaseBody().items');
  async function open(parent){await fill('query',parent.name);await filter();await until(()=>evaluate('!![...document.querySelectorAll("#records button")].find(b=>b.textContent.startsWith('+JSON.stringify(parent.name)+'))'));await evaluate('(()=>{const b=[...document.querySelectorAll("#records button")].find(b=>b.textContent.startsWith('+JSON.stringify(parent.name)+'));const handler=b.onclick;let task;b.onclick=function(...args){task=handler.apply(this,args);return task;};b.click();b.onclick=handler;return task;})()');await until(()=>evaluate('current?.id==='+JSON.stringify(parent.id)+' && !responseListBusy && responseParent?.id==='+JSON.stringify(parent.id)));}
  async function saveAnswer(content){await click('response-new');await fill('response-entry-format','json');await fill('response-completion',JSON.stringify(content));assert.equal(await evaluate('document.getElementById("response-review").value'),'draft');await fill('response-review','human_reviewed');await evaluate('document.getElementById("response-form").requestSubmit()');await until(()=>evaluate('!responseBusy && !responseListBusy && !responseDirty'));}
  async function preview(){await click('response-preview');await until(()=>evaluate('!responseReleaseBusy && !!responsePreview'));return evaluate('responsePreview');}
  async function capture(name,selector){for(const narrow of [false,true]){
    const viewport={width:narrow?390:1400,height:narrow?844:1000};await send('Emulation.setDeviceMetricsOverride',{...viewport,deviceScaleFactor:1,mobile:false});await evaluate('document.querySelector('+JSON.stringify(selector)+').scrollIntoView({block:"start"})');await pause(100);assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'),'Horizontal overflow');
    const shot=Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'),file='instruction-'+name+(narrow?'-narrow':'-desktop')+'.jpg';fs.writeFileSync(path.join(reports,file),shot);evidence.screenshots.push({file,viewport,selector,sha256:crypto.createHash('sha256').update(shot).digest('hex')});
  }await send('Emulation.setDeviceMetricsOverride',{width:1400,height:1000,deviceScaleFactor:1,mobile:false});}
  const sources=[];
  for(const [name,text] of [['North QA','Header 😀\r\nNorth holds 7 e\u0301 cups.\nFooter'],['South QA','South holds 5 cups.\nQuestion\n<script>window.fixtureInjected=1</script>\nFooter']])sources.push(await api('import',{kind:'text',name,text,groups:[name],rights:'Authored local consumer fixture'}));
  await open(sources[0]);
  // Actual DOM selection uses UTF-16; capture converts to Unicode codepoints.
  await evaluate(`(()=>{const text=document.getElementById('asset-text').firstChild;const range=document.createRange();range.setStart(text,7);range.setEnd(text,text.textContent.indexOf('Footer'));const s=window.getSelection();s.removeAllRanges();s.addRange(range);})()`);
  await click('grounded-capture-selection');
  assert.equal(await evaluate('groundedContexts[0].start'),7);assert.equal(await evaluate('groundedContexts[0].quote.startsWith("😀")'),true);
  await open(sources[1]);await fill('grounded-start','0');await fill('grounded-end',String([...sources[1].text].length-6));await click('grounded-capture');
  assert.equal(await evaluate('groundedContexts.length'),2);await fill('grounded-name','Two-source cups QA');await fill('grounded-question',' How many cups together? ');
  await capture('01-passages','#grounded-composer');
  // Commit the real request then lose its acknowledgment; repeated retry recovers one identity.
  await evaluate(`window.composeBaseFetch=window.fetch;window.composeLoseOnce=true;window.composeRequests=[];window.fetch=async(...args)=>{const response=await composeBaseFetch(...args);if(String(args[0]).endsWith('/instruction-compose')){composeRequests.push(JSON.parse(args[1].body));if(composeLoseOnce){composeLoseOnce=false;window.lostComposition=await response.clone().json();throw Error('Fixture lost acknowledgment');}}return response;};`);
  await submit('grounded-compose-form');await until(()=>evaluate('!groundedBusy'));assert.equal(await evaluate('groundedDirty'),true);
  const lost=await evaluate('lostComposition.record');assert.equal(lost.review,'draft');assert.equal((await api('records/'+lost.id+'/responses')).responses.length,0);
  await submit('grounded-compose-form');await until(()=>evaluate('!groundedBusy&&current.id===lostComposition.record.id&&!responseListBusy'));
  assert.equal(await evaluate('composeRequests.length'),2);assert.deepEqual(await evaluate('composeRequests[0]'),await evaluate('composeRequests[1]'));
  assert.equal((await api('records?q=Two-source%20cups%20QA')).total,1);const compositionRequestID=await evaluate('composeRequests[0].request_id');
  await evaluate('window.fetch=composeBaseFetch');let parent=await api('records/'+lost.id);
  assert.equal(await evaluate('typeof window.fixtureInjected'),'undefined');assert.equal(parent.parents.length,2);assert.equal(parent.text,await evaluate('document.getElementById("grounded-prompt-preview").textContent'));
  // Answer is authored separately, persisted draft, reopened, then explicitly reviewed.
  await click('response-new');await fill('response-entry-format','json');const answerText=' 12 cups.\r\n😀 e\u0301 ';await fill('response-completion',JSON.stringify(answerText));
  assert.equal(await evaluate('document.getElementById("response-review").value'),'draft');
  await evaluate(`window.answerLostFetch=window.fetch;window.answerLoseOnce=true;window.fetch=async(...args)=>{const response=await answerLostFetch(...args);if(String(args[0]).endsWith('/responses')&&args[1]?.method==='POST'&&answerLoseOnce){answerLoseOnce=false;throw Error('Fixture lost answer acknowledgment');}return response;};`);
  await submit('response-form');await until(()=>evaluate('!responseBusy'));assert.equal(await evaluate('responseDirty'),true);const uncertainAnswerID=await evaluate('responseEditor.id');
  await submit('response-form');await until(()=>evaluate('!responseBusy'));assert.equal((await api('records/'+parent.id+'/responses')).responses.length,1);assert.equal(await evaluate('responseEditor.id'),uncertainAnswerID);
  await evaluate('window.fetch=answerLostFetch;window.confirm=()=>true');await click('response-refresh');await until(()=>evaluate('!responseListBusy&&responseRows.length===1'));await evaluate('document.querySelector("#response-list button").click()');assert.equal(await evaluate('responseEditor.id'),uncertainAnswerID);await submit('response-form');await until(()=>evaluate('!responseBusy&&!responseListBusy&&!responseDirty'));
  let answer=(await api('records/'+parent.id+'/responses')).responses[0];assert.equal(answer.review,'draft');const creationAnswer=answer.provenance;
  await open(sources[0]);await open(parent);await evaluate('document.querySelector("#response-list button").click()');assert.equal(await evaluate('responseCompletion()'),answerText);
  await fill('response-review','human_reviewed');
  await evaluate(`window.answerGroundFetch=window.fetch;window.answerGroundRelease=null;window.answerGroundRequests=0;window.fetch=async(...args)=>{const response=await answerGroundFetch(...args);if(String(args[0]).endsWith('/responses')&&args[1]?.method==='POST'){++answerGroundRequests;await new Promise(resolve=>answerGroundRelease=resolve);}return response;};`);
  await evaluate('document.getElementById("response-form").requestSubmit();document.getElementById("response-form").requestSubmit()');await until(()=>evaluate('!!answerGroundRelease'));assert.equal(await evaluate('answerGroundRequests'),1);
  await fill('response-completion',JSON.stringify('Later unsaved answer'));await evaluate('answerGroundRelease();answerGroundRelease=null');await until(()=>evaluate('!responseBusy&&!responseListBusy'));
  assert.equal(await evaluate('responseDirty'),true);assert.equal(await evaluate('responseCompletion()'),'Later unsaved answer');assert.equal(await evaluate('document.getElementById("response-review").value'),'draft');
  await evaluate('window.fetch=answerGroundFetch');await click('response-cancel');answer=(await api('records/'+parent.id+'/responses')).responses[0];assert.equal(answer.review,'human_reviewed');assert.equal(answer.completion,answerText);
  await evaluate('document.querySelector("#response-list input[type=checkbox]").click()');const originalFixed=await pairs();let proof=await preview();assert.equal(proof.eligible,true);assert.equal(proof.lineage.length,1);
  const downloads=path.join(temporary,'downloads');fs.mkdirSync(downloads);await send('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:downloads,eventsEnabled:true});
  await evaluate('document.getElementById("response-release-form").requestSubmit();document.getElementById("response-release-form").requestSubmit()');await until(()=>evaluate('!responseReleaseBusy&&!!document.querySelector("#response-release-result a")'));
  await evaluate('document.querySelector("#response-release-result a").click()');await until(()=>fs.readdirSync(downloads).some(name=>name.endsWith('.zip')));
  const archive=path.join(downloads,fs.readdirSync(downloads).find(name=>name.endsWith('.zip'))),frozenBytes=fs.readFileSync(archive),frozenSHA=crypto.createHash('sha256').update(frozenBytes).digest('hex');
  const consumerRun=spawnSync(process.env.INSTRUCTION_CONSUMER_PYTHON||'python3',['tests/check_instruction_consumer.py',archive,'--reader-only'],{cwd:root,encoding:'utf8',timeout:120000});assert.equal(consumerRun.status,0,consumerRun.stdout+'\n'+consumerRun.stderr);
  const consumer=JSON.parse(consumerRun.stdout.trim().split('\n').at(-1));assert.equal(consumer.result,'PASS');assert.equal(consumer.context_sources,2);assert.equal(consumer.models_or_trainers_constructed,false);assert.equal(consumer.zip_sha256,frozenSHA);
  fs.writeFileSync(path.join(reports,'grounded-downloaded.zip'),frozenBytes);
  await click('response-selection-save');await until(()=>fs.readdirSync(downloads).some(name=>name.endsWith('.json')));
  const selectionFile=path.join(downloads,fs.readdirSync(downloads).find(name=>name.endsWith('.json'))),selection=JSON.parse(fs.readFileSync(selectionFile,'utf8'));assert.deepEqual(selection.items,originalFixed);
  await send('Page.navigate',{url:base+'/workbench'});await until(()=>evaluate('document.getElementById("notice")?.textContent==="Collection ready."'));assert.equal(await evaluate('responseSelected.size'),0);
  const selectionBytes=fs.readFileSync(selectionFile).toString('base64');await evaluate(`(()=>{const data=new DataTransfer();data.items.add(new File([Uint8Array.from(atob(${JSON.stringify(selectionBytes)}),c=>c.charCodeAt(0))],'fixed-answers.json',{type:'application/json'}));const input=document.getElementById('response-selection-file');input.files=data.files;input.dispatchEvent(new Event('change'));})()`);await until(()=>evaluate('responseSelected.size===1'));assert.deepEqual(await pairs(),originalFixed);
  // Edit a contributing source's rights via the real existing editor, while fixed answer selection stays exact.
  await open(sources[0]);await fill('rights-note-value','Updated permission statement QA');await submit('rights-note-form');await until(()=>evaluate('!rightsBusy'));sources[0]=await api('records/'+sources[0].id);
  await open(parent);proof=await preview();assert.equal(proof.eligible,false);assert.deepEqual(await pairs(),originalFixed);
  await click('grounded-inspect');await until(()=>evaluate('!groundedInspectBusy&&!!groundedInspection'));assert.equal(await evaluate('groundedInspection.current'),false);assert.equal(await evaluate('document.getElementById("grounded-reinspect").disabled'),false);
  await capture('02-source-change','#grounded-context-inspection');
  await evaluate(`window.reinspectFetch=window.fetch;window.reinspectRelease=null;window.fetch=async(...args)=>{const response=await reinspectFetch(...args);if(String(args[0]).includes('/instruction-reinspect/'))await new Promise(resolve=>reinspectRelease=resolve);return response;};`);
  await click('grounded-reinspect');await until(()=>evaluate('!!reinspectRelease'));await click('response-new');await fill('response-completion','Later draft during reinspect');
  await evaluate('reinspectRelease();reinspectRelease=null');await until(()=>evaluate('!groundedInspectBusy'));assert.equal(await evaluate('current.revision'),1);assert.equal(await evaluate('responseDirty'),true);assert.equal(await evaluate('responseCompletion()'),'Later draft during reinspect');
  await evaluate('window.fetch=reinspectFetch');await click('response-cancel');await open(parent);await until(()=>evaluate('!responseListBusy&&current.revision===2'));
  parent=await api('records/'+parent.id);answer=(await api('records/'+parent.id+'/responses')).responses[0];assert.equal(answer.review,'draft');assert.deepEqual(answer.provenance,creationAnswer);
  assert.deepEqual(parent.provenance,lost.provenance);assert.deepEqual(await pairs(),originalFixed);
  await evaluate('document.querySelector("#response-list button").click()');assert.equal(await evaluate('document.getElementById("response-review").value'),'draft');await submit('response-form');await until(()=>evaluate('!responseBusy&&!responseListBusy&&!responseDirty'));
  await open(sources[0]);await open(parent);await evaluate('document.querySelector("#response-list button").click()');assert.equal(await evaluate('responseCompletion()'),answerText);
  await fill('response-review','human_reviewed');await submit('response-form');await until(()=>evaluate('!responseBusy&&!responseListBusy&&!responseDirty'));
  proof=await preview();assert.equal(proof.eligible,false,'Review does not silently replace fixed selections');
  await evaluate('document.querySelector("#response-list input[type=checkbox]").click();document.querySelector("#response-list input[type=checkbox]").click()');proof=await preview();assert.equal(proof.eligible,true);assert.notDeepEqual(await pairs(),originalFixed);
  for(const source of sources){await open(source);await fill('grounded-start',String(source.id===sources[0].id?7:0));await fill('grounded-end',String([...source.text].length-6));await click('grounded-capture');}await open(parent);
  // A held composition acknowledgment retains later question and answer intent without replacing parent.
  await fill('grounded-question','What do the two sources hold?');await fill('grounded-name','Held composition QA');
  // Re-capture changed source explicitly, preserving the same exact original span.
  await evaluate('[...document.querySelectorAll("#grounded-passages li")].find(li=>li.textContent.includes('+JSON.stringify(sources[0].id)+')).querySelector("button").click()');await open(sources[0]);await fill('grounded-start','7');await fill('grounded-end',String([...sources[0].text].length-6));await click('grounded-capture');await open(parent);
  await evaluate(`window.composeHeldFetch=window.fetch;window.composeHeldRelease=null;window.composeHeldRequests=0;window.fetch=async(...args)=>{const response=await composeHeldFetch(...args);if(String(args[0]).endsWith('/instruction-compose')){++composeHeldRequests;window.heldComposition=await response.clone().json();await new Promise(resolve=>composeHeldRelease=resolve);}return response;};`);
  await evaluate('document.getElementById("grounded-compose-form").requestSubmit();document.getElementById("grounded-compose-form").requestSubmit()');await until(()=>evaluate('!!composeHeldRelease'));
  await fill('grounded-question','Later unsaved question');await click('response-new');await fill('response-completion','Later unsaved answer during compose');
  await evaluate('composeHeldRelease();composeHeldRelease=null');await until(()=>evaluate('!groundedBusy'));assert.equal(await evaluate('composeHeldRequests'),1);assert.equal(await evaluate('current.id'),parent.id);
  assert.equal(await evaluate('document.getElementById("grounded-question").value'),'Later unsaved question');assert.equal(await evaluate('responseCompletion()'),'Later unsaved answer during compose');assert.equal(await evaluate('responseDirty'),true);assert.equal(await evaluate('groundedDirty'),true);
  const unload=await evaluate('(()=>{const event=new Event("beforeunload",{cancelable:true});window.dispatchEvent(event);return event.defaultPrevented;})()');assert.equal(unload,true);
  await evaluate('window.fetch=composeHeldFetch');await click('response-cancel');await evaluate('window.confirm=()=>true');await click('grounded-compose-reset');
  // Isolated owner intents: each clean late compose acknowledgment must respect its owner.
  const isolated=[];
  for(const intent of ['answer','rights','navigation','clean-answer-save']){
    for(const source of sources){await open(source);await fill('grounded-start','0');await fill('grounded-end',String(Math.min(20,[...source.text].length)));await click('grounded-capture');}
    await fill('grounded-name','Isolated composer '+intent);await fill('grounded-question','QA race '+intent);await open(parent);
    await evaluate(`window.isolatedFetch=window.fetch;window.isolatedComposeRelease=null;window.isolatedAnswerRelease=null;window.fetch=async(...args)=>{const response=await isolatedFetch(...args);if(String(args[0]).endsWith('/instruction-compose'))await new Promise(resolve=>isolatedComposeRelease=resolve);if(String(args[0]).endsWith('/responses')&&args[1]?.method==='POST')await new Promise(resolve=>isolatedAnswerRelease=resolve);return response;};`);
    if(intent==='clean-answer-save'){await evaluate('document.querySelector("#response-list button").click()');assert.equal(await evaluate('responseDirty'),false);await evaluate('document.getElementById("response-form").requestSubmit()');await until(()=>evaluate('!!isolatedAnswerRelease'));}
    await evaluate('document.getElementById("grounded-compose-form").requestSubmit()');await until(()=>evaluate('!!isolatedComposeRelease'));
    if(intent==='answer'){await click('response-new');await fill('response-completion','Only later answer intent');}
    if(intent==='rights')await fill('rights-note-value','Only later rights intent');
    if(intent==='navigation')await open(sources[0]);
    const owner=await evaluate('current.id');await evaluate('isolatedComposeRelease();isolatedComposeRelease=null');await until(()=>evaluate('!groundedBusy'));
    assert.equal(await evaluate('current.id'),owner,'Later '+intent+' owns the record');
    if(intent==='answer'){assert.equal(await evaluate('responseCompletion()'),'Only later answer intent');assert.equal(await evaluate('responseDirty'),true);await click('response-cancel');}
    if(intent==='rights'){assert.equal(await evaluate('rightsDirty'),true);assert.equal(await evaluate('document.getElementById("rights-note-value").value'),'Only later rights intent');await click('rights-note-cancel');}
    if(intent==='clean-answer-save'){assert.equal(await evaluate('responseBusy'),true);await evaluate('isolatedAnswerRelease();isolatedAnswerRelease=null');await until(()=>evaluate('!responseBusy&&!responseListBusy'));await click('response-cancel');}
    await evaluate('window.fetch=isolatedFetch');await click('grounded-compose-reset');isolated.push(intent);
  }
  // An inspection result cannot attach old source evidence after rendered navigation.
  await open(parent);await evaluate(`window.inspectHeldFetch=window.fetch;window.inspectHeldRelease=null;window.fetch=async(...args)=>{const response=await inspectHeldFetch(...args);if(String(args[0]).includes('/instruction-contexts/'))await new Promise(resolve=>inspectHeldRelease=resolve);return response;};`);
  await click('grounded-inspect');await until(()=>evaluate('!!inspectHeldRelease'));await open(sources[0]);await evaluate('inspectHeldRelease();inspectHeldRelease=null');await until(()=>evaluate('!groundedInspectBusy'));assert.equal(await evaluate('groundedInspection'),null);assert.equal(await evaluate('document.getElementById("grounded-context-evidence").textContent'),'');await evaluate('window.fetch=inspectHeldFetch');
  // Delete second source using rendered control, with a held acknowledgement and later rights draft.
  // Tombstone and family links survive; source asset refuses.
  await open(sources[1]);await evaluate(`window.deleteHeldFetch=window.fetch;window.deleteHeldRelease=null;window.fetch=async(...args)=>{const response=await deleteHeldFetch(...args);if(String(args[0]).includes('/text-delete/'))await new Promise(resolve=>deleteHeldRelease=resolve);return response;};`);
  await click('text-source-delete');await until(()=>evaluate('!!deleteHeldRelease'));await fill('rights-note-value','Later draft during delete');await evaluate('deleteHeldRelease();deleteHeldRelease=null');await until(()=>evaluate('!groundedInspectBusy'));assert.equal(await evaluate('rightsDirty'),true);assert.equal(await evaluate('document.getElementById("rights-note-value").value'),'Later draft during delete');
  await evaluate('window.fetch=deleteHeldFetch');await click('rights-note-cancel');await open(sources[1]);assert.equal(await evaluate('current.source_available'),false);
  const deleted=await api('records/'+sources[1].id);assert.equal(deleted.source_available,false);assert.equal(deleted.source_lineage_known,true);assert.deepEqual(deleted.groups,sources[1].groups);
  const assetResponse=await fetch(base+'/api/workbench/asset/'+deleted.id);assert.equal(assetResponse.status,404);
  await open(parent);await click('grounded-inspect');await until(()=>evaluate('!groundedInspectBusy&&!!groundedInspection'));assert.equal(await evaluate('document.getElementById("grounded-reinspect").disabled'),true);
  proof=await preview();assert.equal(proof.eligible,false);assert.match(proof.blockers[0].message,/deleted/);assert.equal(crypto.createHash('sha256').update(fs.readFileSync(archive)).digest('hex'),frozenSHA);
  await capture('03-deleted-context','#grounded-context-inspection');
  assert.deepEqual(errors,[]);evidence.result='PASS';evidence.errors=errors;evidence.steps.push({stage:'authored_unicode_dom_passages',offsets:'Unicode codepoints',sources:sources.map(s=>s.id)},{stage:'lost_ack_and_repeated_compose',request_id:compositionRequestID,single_prompt:lost.id},{stage:'independent_draft_reopen_review_held_save',creation_provenance_unchanged:true,later_editor_retained:true,fixed_selection_save_and_document_reload:true,repair_draft_save_reopen_review:true},{stage:'source_edit_reinspect_and_stale_selection',old_selection:originalFixed,current_selection:await pairs(),all_answers_reset_draft:true},{stage:'held_compose_later_intent',single_request:true,question_and_answer_retained:true,isolated_owner_cases:isolated,held_reinspect_answer_and_delete_rights_retained:true,held_inspection_navigation_retained:true},{stage:'source_tombstone',deleted_id:deleted.id,asset_status:assetResponse.status,blocked_preview:proof},{stage:'actual_immutable_download_and_pinned_consumer',consumer,zip_bytes:frozenBytes.length,sha256:frozenSHA});
  fs.writeFileSync(path.join(reports,'grounded-instruction-session.json'),JSON.stringify(evidence,null,2)+'\n');console.log('PASS actual Chromium Unicode passage capture, lost/held/repeated composition, independent draft/reopen/human review, held answer save, rights edit/deliberate reset/rereview, stale selection, source deletion, immutable actual ZIP and pinned reader-only Datasets; desktop/narrow; no model/trainer.');
})().catch(async error=>{console.error(error);console.error('Runtime errors:',JSON.stringify(errors));if(inspect)try{console.error('Page diagnostics:',await inspect());}catch(diagnostic){console.error('Diagnostics failed:',diagnostic);}process.exitCode=1;}).finally(async()=>{if(ws)ws.close();for(const child of children)child.kill();await pause(200);fs.rmSync(temporary,{recursive:true,force:true});});
