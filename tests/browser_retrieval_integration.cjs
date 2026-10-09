// Actual rendered positive-only authoring and pure serialized readers; no fitting.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn,execFileSync}=require('node:child_process');
const {qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const {waitForDebugger}=require('./browser_startup.cjs'),{pageLoadTracker}=require('./browser_page_load.cjs');
const root=path.resolve(process.env.TULDOK_SOURCE_ROOT||path.join(__dirname,'..'));
const output=qaDirectory(root,'retrieval-integration');
const scratch=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-retrieval-ui-')),children=[],errors=[],network=new Map(),tracker=pageLoadTracker();
const python=process.env.INSTRUCTION_CONSUMER_PYTHON||'python3',sha=raw=>crypto.createHash('sha256').update(raw).digest('hex');
const pair=row=>({id:row.id,revision:row.revision,source_revision:row.source_revision});
const sortedPairs=rows=>rows.map(pair).sort((a,b)=>a.id.localeCompare(b.id));
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
let ws,evaluate,uiAction='initial document';
async function until(fn){for(let i=0;i<200;i++){if(await fn())return;await pause(75);}throw Error('Timed out during '+uiAction);}
function launch(command,args,options){const child=spawn(command,args,options);children.push(child);return child;}
(async()=>{
 const server=launch(python,['-u','app.py','--port','0','--data',path.join(scratch,'data')],{cwd:root,stdio:['ignore','pipe','pipe']});
 let stdout='',stderr='';server.stdout.on('data',v=>stdout+=v);server.stderr.on('data',v=>stderr+=v);
 await until(()=>{if(server.exitCode!==null)throw Error(stderr);return /127\.0\.0\.1:(\d+)/.test(stdout);});
 const base='http://127.0.0.1:'+stdout.match(/127\.0\.0\.1:(\d+)/)[1];
 const get=async route=>{const response=await fetch(base+'/api/workbench/'+route);assert.equal(response.status,200);return response.json();};
 const browser=launch(process.env.BROWSER||'/usr/bin/chromium',['--headless','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--window-size=1400,950','--user-data-dir='+path.join(scratch,'browser'),'about:blank'],{stdio:['ignore','ignore','pipe'],env:{...process.env,XDG_CONFIG_HOME:scratch,XDG_CACHE_HOME:scratch}});
 const port=await waitForDebugger(browser,path.join(scratch,'browser','DevToolsActivePort'));
 const tabs=await(await fetch('http://127.0.0.1:'+port+'/json')).json();
 ws=new WebSocket(tabs.find(t=>t.type==='page'&&t.url==='about:blank').webSocketDebuggerUrl);
 await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
 let id=0;const pending=new Map();
 ws.onmessage=event=>{
  const message=JSON.parse(event.data);tracker.observe(message);
  if(message.id){const item=pending.get(message.id);pending.delete(message.id);message.error?item.reject(message.error):item.resolve(message.result);}
  if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails);
  if(message.method==='Network.requestWillBeSent'){const request=message.params.request,url=new URL(request.url);if(url.hostname==='127.0.0.1')network.set(message.params.requestId,{request_id:message.params.requestId,owner:'retrieval-workbench',method:request.method,path:url.pathname,ui_action:uiAction,role:request.method==='POST'&&!url.pathname.endsWith('/preview')?'mutation':'observation',body_bytes:request.postData?Buffer.byteLength(request.postData):0,body_sha256:request.postData?sha(request.postData):null,status:null});}
  if(message.method==='Network.responseReceived'){const item=network.get(message.params.requestId);if(item)item.status=message.params.response.status;}
 };
 const send=(method,params={})=>new Promise((resolve,reject)=>{const request=++id,timeout=setTimeout(()=>{pending.delete(request);reject(Error('CDP timeout '+method));},15000);pending.set(request,{resolve:value=>{clearTimeout(timeout);resolve(value);},reject:error=>{clearTimeout(timeout);reject(error);}});ws.send(JSON.stringify({id:request,method,params}));});
 evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
 const click=id=>{uiAction='rendered click '+id;return evaluate('document.getElementById('+JSON.stringify(id)+').click()');};
 const submit=id=>{uiAction='rendered submit '+id;return evaluate('document.getElementById('+JSON.stringify(id)+').requestSubmit()');};
 const fill=(id,value)=>evaluate('(()=>{const e=document.getElementById('+JSON.stringify(id)+');e.value='+JSON.stringify(value)+';e.dispatchEvent(new Event("input",{bubbles:true}));e.dispatchEvent(new Event("change",{bubbles:true}));})()');
 const pairs=()=>evaluate('([...selected.values()].map(({id,revision,source_revision})=>({id,revision,source_revision}))).sort((a,b)=>a.id.localeCompare(b.id))');
 const rowExpression=row=>'[...document.querySelectorAll("#records .record")].find(r=>r.querySelector("input")?.getAttribute("aria-label")==='+JSON.stringify('Select '+row.name)+')';
 const open=async row=>{uiAction='rendered collection Open '+row.id;await evaluate('window.qaPreviousCurrent=current');await evaluate('(()=>{const r='+rowExpression(row)+';if(!r)throw Error("Row not rendered");r.querySelector("button").click();})()');await until(()=>evaluate('current!==window.qaPreviousCurrent&&current?.id==='+JSON.stringify(row.id)+'&&!dirty&&!document.getElementById("editor").dataset.busy'));};
 const reloadRecord=async row=>{await evaluate('window.qaPreviousCurrent=current');await click('reload');await until(()=>evaluate('current!==window.qaPreviousCurrent&&current?.id==='+JSON.stringify(row.id)+'&&current.revision==='+row.revision+'&&!dirty&&!document.getElementById("reload").dataset.busy&&!document.getElementById("editor").dataset.busy'));};
 const discardReload=async row=>{await evaluate('window.qaPreviousCurrent=current');const discard=click('reload');await pause(100);await send('Page.handleJavaScriptDialog',{accept:true});await discard;await until(()=>evaluate('current!==window.qaPreviousCurrent&&current?.id==='+JSON.stringify(row.id)+'&&!dirty&&!document.getElementById("reload").dataset.busy&&!document.getElementById("editor").dataset.busy'));};
 const save=async(row,review)=>{await submit('editor');await until(()=>evaluate('current?.id==='+JSON.stringify(row.id)+'&&current.revision>'+row.revision+'&&current.review==='+JSON.stringify(review)+'&&!dirty&&!document.getElementById("editor").dataset.busy'));return get('records/'+row.id);};
 const finishReview=async(row,annotation)=>{
  assert.equal(await evaluate('document.getElementById("record-review").value'),'draft');
  row=await save(row,'draft');assert.deepEqual(row.annotation,annotation);await reloadRecord(row);
  assert.equal(await evaluate('current.review'),'draft');assert.equal(await evaluate('document.getElementById("retrieval-role").value'),annotation.role);assert.equal(await evaluate('document.getElementById("retrieval-note").value'),annotation.note);
  if(annotation.role==='query')assert.deepEqual(JSON.parse(await evaluate('document.getElementById("retrieval-refs").value')),annotation.positive_refs);
  await fill('record-review','human_reviewed');row=await save(row,'human_reviewed');assert.deepEqual(row.annotation,annotation);return row;
 };
 const setFormat=async()=>{await fill('release-format','text_retrieval_v1');await fill('train',34);await fill('validation',33);await fill('test',33);};
 const preview=async()=>{await click('preview-release');await until(()=>evaluate('!releaseBusy'));return evaluate('releasePreview');};
 const clearSelection=async()=>{await click('clear-selection');await until(()=>evaluate('!document.getElementById("clear-selection").dataset.busy&&selected.size===0&&document.querySelectorAll("#records input:checked").length===0'));};
 const selectRows=async rows=>{await submit('filters');await until(()=>evaluate('!document.getElementById("filters").dataset.busy'));await clearSelection();uiAction='rendered exact record checkboxes';for(const row of rows)await evaluate('('+rowExpression(row)+').querySelector("input").click()');assert.deepEqual(await pairs(),sortedPairs(rows));};
 const namedSelection=async(name,rows)=>{
  const expected=sortedPairs(rows);assert.deepEqual(await pairs(),expected);await fill('selection-name',name);await submit('save-selection-form');
  await until(()=>evaluate('!document.getElementById("save-selection-form").dataset.busy&&document.getElementById("saved-selection-status").textContent.startsWith("Saved “")'));
  const setId=await evaluate('document.getElementById("saved-selection").value');await clearSelection();await click('load-selection');await until(()=>evaluate('!savedLoadBusy&&selected.size==='+rows.length));assert.deepEqual(await pairs(),expected);
  const old=(await send('Page.getFrameTree')).frameTree.frame;await send('Page.reload');await until(()=>tracker.reloaded(old));await until(()=>evaluate('document.readyState==="complete"&&!savedLoadBusy&&selected.size==='+rows.length+'&&document.getElementById("saved-selection-status").textContent.startsWith("Opened “")'));
  assert.deepEqual(await pairs(),expected);assert.equal(await evaluate('releasePreview'),null);assert.equal(await evaluate('document.getElementById("freeze-release").disabled'),true);
  const saved=await get('selections/'+setId);assert.equal(saved.current,true);assert.deepEqual(sortedPairs(saved.selection.items),expected);return {id:setId,pairs:expected,saved};
 };
 const rawQuery=async(name,text,doc)=>{
  await fill('retrieval-import-name',name);await fill('retrieval-import-text',text);await fill('retrieval-import-group',doc.groups[0]);await fill('retrieval-import-rights','unknown');await fill('retrieval-import-refs',JSON.stringify([pair(doc)]));await submit('retrieval-import-form');
  await until(()=>evaluate('!retrievalImportBusy'));assert.match(await evaluate('document.getElementById("retrieval-import-status").textContent'),/Imported raw draft/);
  const row=(await get('records?kind=text')).items.find(r=>r.name===name);assert.ok(row);assert.equal(row.review,'draft');assert.equal(row.annotation,null);assert.equal(row.rights_note,'unknown');assert.deepEqual(row.parents,[doc.id]);assert.deepEqual(row.provenance.acquisition.declared_positive_refs,[pair(doc)]);return row;
 };
 await send('Page.enable');await send('Runtime.enable');await send('Network.enable');await send('Page.setLifecycleEventsEnabled',{enabled:true});
 const blank=(await send('Page.getFrameTree')).frameTree.frame;await send('Page.navigate',{url:base+'/workbench'});await until(()=>tracker.reloaded(blank));await until(()=>evaluate('document.readyState==="complete"&&document.getElementById("notice")?.textContent==="Collection ready."'));
 const documents=[],queries=[],rawSources=[],specs=[];
 for(const group of ['orchard','garden','river'])for(let i=0;i<2;i++)specs.push({group,name:group+' corpus '+i,text:' '+group+' source '+i+': café β, water and sunlight.\n'});
 specs.push({group:'orchard',name:'Unused corpus · UNJUDGED',text:' Unused café <img src=x onerror=alert(1)> source: no relevance judgment.\n'});
 for(const spec of specs){
  await fill('import-name',spec.name);await fill('import-text',spec.text);await fill('import-group',spec.group);await fill('rights','unknown');await submit('import-form');
  await until(()=>evaluate('!document.getElementById("import-form").dataset.busy&&current?.name==='+JSON.stringify(spec.name)+'&&!dirty'));
  let row=await get('records/'+await evaluate('current.id'));rawSources.push(row);assert.equal(row.text,spec.text);assert.equal(row.review,'draft');assert.equal(row.annotation,null);await open(row);
  await fill('task','text_retrieval');await fill('retrieval-role','document');const annotation={role:'document',note:'Explicit authored document review · β <img src=x onerror=alert(1)>'};await fill('retrieval-note',annotation.note);documents.push(await finishReview(row,annotation));
 }
 assert.equal(await evaluate('current.id'),documents[6].id);assert.ok((await evaluate('document.getElementById("asset-text").textContent')).includes('<img src=x onerror=alert(1)>'));
 assert.equal(await evaluate('document.querySelectorAll("#asset-text img,#asset-text script").length'),0);assert.ok((await evaluate('document.getElementById("retrieval-note").value')).includes('β <img src=x onerror=alert(1)>'));
 for(let i=0;i<6;i++){
  const doc=documents[i];await open(doc);if(i===0){uiAction='rendered preserve selected document';await evaluate('('+rowExpression(doc)+').querySelector("input").click()');}
  const dirtyNote='Unrelated dirty document note retained during raw query admission';await fill('retrieval-note',dirtyNote);
  const owner=await evaluate('({id:current.id,dirty,editorEpoch,pairs:[...selected.values()].map(({id,revision,source_revision})=>({id,revision,source_revision}))})');
  let row=await rawQuery('Query '+doc.name,' How to '+doc.groups[0]+' source '+(i%2)+'? café β\n',doc);
  assert.deepEqual(await evaluate('({id:current.id,dirty,editorEpoch,pairs:[...selected.values()].map(({id,revision,source_revision})=>({id,revision,source_revision}))})'),owner);assert.equal(await evaluate('document.getElementById("retrieval-note").value'),dirtyNote);
  await discardReload(doc);await open(row);await fill('task','text_retrieval');assert.equal(await evaluate('document.getElementById("retrieval-role").value'),'query');
  const annotation={role:'query',note:'Explicit authored positive relevance · '+i,positive_refs:[pair(doc)]};await fill('retrieval-note',annotation.note);
  if(i===0){await evaluate('document.getElementById("retrieval-controls").scrollIntoView()');fs.writeFileSync(path.join(output,'retrieval-authoring.jpg'),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));}
  queries.push(await finishReview(row,annotation));
 }
 await open(documents[0]);await fill('retrieval-note','Unselected dirty owner stays unchanged');const unselected=await rawQuery('Unselected raw query · UNJUDGED','Unselected café query remains unreviewed.\n',documents[0]);await discardReload(documents[0]);
 let rows=[...documents,...queries];await selectRows(rows);const firstSet=await namedSelection('Retrieval QA · original exact reviewed pairs',rows);fs.writeFileSync(path.join(output,'original-fixed-selection.json'),JSON.stringify(firstSet.saved,null,2)+'\n');
 await setFormat();const initial=await preview();assert.equal(initial.eligible,true);assert.equal(await evaluate('document.getElementById("retrieval-export-help").hidden'),false);assert.match(await evaluate('document.getElementById("retrieval-export-help").textContent'),/unjudged/i);
 // Exact positive refs never auto-follow a later document review.
 const originalPositiveRefs=queries[0].annotation.positive_refs.map(r=>({...r}));
 await open(documents[0]);await fill('retrieval-note','Deliberately revised document · new positive revision');documents[0]=await finishReview(documents[0],{role:'document',note:'Deliberately revised document · new positive revision'});
 const stalePositive=await preview();assert.equal(stalePositive.eligible,false);assert.ok(stalePositive.blockers.some(item=>item.status===409&&/Positive document changed/.test(item.message)));
 await open(queries[0]);await fill('retrieval-note','Attempting stale positive must preserve stored query');await submit('editor');
 await until(()=>evaluate('!document.getElementById("editor").dataset.busy&&document.getElementById("notice").textContent.includes("Positive document changed")'));assert.equal((await get('records/'+queries[0].id)).revision,queries[0].revision);assert.equal(await evaluate('dirty'),true);
 await fill('retrieval-refs',JSON.stringify([pair(documents[0])]));const repaired={role:'query',note:'Deliberately reviewed updated positive document revision',positive_refs:[pair(documents[0])]};await fill('retrieval-note',repaired.note);queries[0]=await finishReview(queries[0],repaired);
 await click('history');await until(()=>evaluate('!document.getElementById("history-output").hidden'));const queryHistory=JSON.parse(await evaluate('document.getElementById("history-output").textContent')).sort((a,b)=>a.revision-b.revision);
 assert.equal(queryHistory.length,5);assert.equal(queryHistory[0].annotation,null);assert.equal(queryHistory[0].review,'draft');assert.deepEqual(queryHistory.slice(1).map(r=>r.review),['draft','human_reviewed','draft','human_reviewed']);
 assert.deepEqual(queryHistory[2].annotation.positive_refs,originalPositiveRefs);assert.deepEqual(queryHistory[4].annotation.positive_refs,repaired.positive_refs);
 rows=[...documents,...queries];await selectRows(rows);const fixed=await namedSelection('Retrieval QA · repaired exact reviewed pairs',rows);fs.writeFileSync(path.join(output,'frozen-fixed-selection.json'),JSON.stringify(fixed.saved,null,2)+'\n');await setFormat();
 const ready=await preview();assert.equal(ready.eligible,true);assert.match(await evaluate('document.getElementById("release-preview").textContent'),/distinct positives/);assert.equal(await evaluate('document.querySelectorAll("#release-preview img,#release-preview script").length'),0);
 await submit('release-form');await until(()=>evaluate('!releaseBusy&&!!document.querySelector("#release-result a")'));const url=await evaluate('document.querySelector("#release-result a").href');const response=await fetch(url);assert.equal(response.status,200);
 const zip=Buffer.from(await response.arrayBuffer()),archive=path.join(output,'frozen-retrieval.zip');fs.writeFileSync(archive,zip);assert.ok(url.includes(sha(zip)));const expected=path.join(output,'expected-records.json');fs.writeFileSync(expected,JSON.stringify(rows,null,2)+'\n');
 execFileSync(python,['tests/check_retrieval_reader.py','--archive',archive,'--expected',expected,'--output',path.join(output,'reader')],{cwd:root,timeout:90000,stdio:'inherit'});const reader=JSON.parse(fs.readFileSync(path.join(output,'reader','report.json')));assert.equal(reader.status,'passed');
 assert.equal(reader.documents,7);assert.equal(reader.queries,6);assert.equal(reader.train_pairs,2);assert.equal(reader.archive.sha256,sha(zip));assert.deepEqual(reader.unjudged_document_ids,[documents[6].id]);
 for(const key of ['fitting_executed','ranking_executed','metrics_executed','training_executed','model_loading','downloads','negatives_inferred'])assert.equal(reader[key],false,key);
 await evaluate('document.getElementById("release-form").scrollIntoView()');await until(()=>evaluate('document.getElementById("release-format").getBoundingClientRect().top>=0&&document.getElementById("release-format").getBoundingClientRect().bottom<innerHeight'));fs.writeFileSync(path.join(output,'retrieval-desktop.jpg'),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));
 await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});await evaluate('document.getElementById("release-preview").scrollIntoView()');assert.equal(await evaluate('document.documentElement.scrollWidth<=innerWidth'),true);fs.writeFileSync(path.join(output,'retrieval-narrow.jpg'),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));
 // Live Save updates its pair; a named set deliberately restores the old exact pairs.
 await open(queries[1]);await fill('retrieval-note','Post-freeze draft edit');const edited=await save(queries[1],'draft');assert.equal(edited.review,'draft');assert.equal((await get('selections/'+fixed.id)).current,false);
 await clearSelection();await click('load-selection');await until(()=>evaluate('!savedLoadBusy&&selected.size===13'));assert.deepEqual(await pairs(),fixed.pairs);const refused=await preview();assert.equal(refused.eligible,false);assert.equal(await evaluate('document.getElementById("freeze-release").disabled'),true);
 const staleSaved=await get('selections/'+fixed.id);assert.equal(staleSaved.current,false);fs.writeFileSync(path.join(output,'stale-fixed-selection.json'),JSON.stringify(staleSaved,null,2)+'\n');assert.deepEqual(Buffer.from(await(await fetch(url)).arrayBuffer()),zip);
 const untouched=await get('records/'+unselected.id);assert.equal(untouched.review,'draft');assert.equal(untouched.annotation,null);assert.equal(untouched.provenance.rights,'unknown');assert.deepEqual(errors,[]);
 const snapshot=JSON.parse(execFileSync(python,['-c','import json;from scripts.qualify_text_classification_local import source_snapshot;print(json.dumps(source_snapshot()))'],{cwd:root,encoding:'utf8'}));const ledger=[...network.values()];
 assert.equal(ledger.filter(item=>item.path==='/api/workbench/releases'&&item.status===201).length,1);assert.ok(ledger.some(item=>item.path==='/api/workbench/records/'+queries[0].id&&item.status===409));
 fs.writeFileSync(path.join(output,'session.json'),JSON.stringify({result:'PASS',candidate_head:snapshot.head,candidate_tree:execFileSync('git',['write-tree'],{cwd:root,encoding:'utf8'}).trim(),source_snapshot_sha256:snapshot.sha256,source_snapshot_files:Object.keys(snapshot.files).length,basis:'Authored tiny texts, QA groups and simulated review actions; no genuine human benchmark or semantic independence.',frozen_url:url,release_sha256:sha(zip),selected_pairs:fixed.pairs,original_fixed_set:firstSet.id,frozen_fixed_set:fixed.id,records_at_freeze:rows,query_review_history:queryHistory,raw_sources:rawSources,unused_corpus_document_id:documents[6].id,unselected_query:{id:untouched.id,review:untouched.review,annotation:untouched.annotation,rights_note:untouched.provenance.rights},positive_only:true,omitted_relations:'UNJUDGED; never authored negative targets',checks:['rendered raw document and query imports','separate draft Save/reopen then simulated human review','raw query import preserves dirty editor epoch and exact selected pair','stable IDs/exact source refs/immutable parent provenance','named exact set Save/Open/full-document reload','stale positive preview and actual query Save HTTP409 without mutation','deliberate draft exact-ref repair/reopen/separate review','family-safe fresh preview/freeze/hash download','unchanged pure serialized reader on actual ZIP; no fits/ranks/metrics','post-freeze old named set exact pairs/current=false/refusal','immutable old ZIP after target edit','desktop/narrow and safe literal text'],network:ledger,network_scope:'Browser CDP mutations and observations; Node inspections/archive downloads are separate read-only checks.',mutating_requests:ledger.filter(item=>item.role==='mutation').length,errors,reader,fitting_executed:false,ranking_executed:false,evaluation_executed:false,training_executed:false,model_downloads:false,UI_provisional:true},null,2)+'\n');
 console.log('Retrieval integration browser passed: explicit positive-only draft/review, exact named sets, stale refs, immutable export and actual serialized reader; no fitting/ranking/training.');
})().catch(async error=>{console.error(error);if(evaluate)try{console.error(await evaluate('document.body.innerText.slice(-7000)'));}catch{}process.exitCode=1;}).finally(async()=>{ws?.close();for(const child of children)child.kill();await pause(200);fs.rmSync(scratch,{recursive:true,force:true});});
