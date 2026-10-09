// Real Chromium + production HTTP/actor. Native positive proof requires explicit SDK fixtures.
'use strict';
const assert=require('node:assert/strict'),crypto=require('node:crypto'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process'),{qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs'),{pageLoadTracker}=require('./browser_page_load.cjs');
const root=process.env.TULDOK_SOURCE_ROOT||path.resolve(__dirname,'..'),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-owner-browser-'));
const report=qaDirectory(root,'pumas-owner-reuse'),children=[],errors=[],loads=pageLoadTracker(),pause=ms=>new Promise(r=>setTimeout(r,ms));
const sha=raw=>crypto.createHash('sha256').update(raw).digest('hex');let ws,server,ownerRoot;
async function until(fn){for(let i=0;i<200;i++){const v=await fn();if(v)return v;await pause(100);}throw Error('Timed out');}
function launch(command,args,options){const child=spawn(command,args,options);children.push(child);return child;}
(async()=>{
 server=launch('python3',['-u','tests/browser_pumas_owner_reuse_server.py','--port','0','--data',path.join(temporary,'data')],{cwd:root,stdio:['ignore','pipe','pipe']});
 let output='',stderr='';server.stdout.on('data',b=>output+=b);server.stderr.on('data',b=>stderr+=b);
 const port=await until(()=>{if(server.exitCode!==null)throw Error(stderr);return output.match(/Tuldok: http:\/\/127\.0\.0\.1:(\d+)/)?.[1];}),base='http://127.0.0.1:'+port;
 ownerRoot=output.match(/OWNER_FIXTURE=(.+)/)?.[1];const native=!!ownerRoot,scope=output.match(/OWNER_SCOPE=(.+)/)[1];
 const selected=native?JSON.parse(output.match(/OWNER_SELECTED=(.+)/)[1]):null,endpoint=output.match(/OWNER_ENDPOINT=(.+)/)?.[1];
 launch(process.env.BROWSER||'/usr/bin/chromium',['--headless','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--window-size=1400,950','--user-data-dir='+path.join(temporary,'chromium'),'about:blank'],{stdio:['ignore','ignore','ignore'],env:{...process.env,XDG_CONFIG_HOME:temporary,XDG_CACHE_HOME:temporary}});
 const active=path.join(temporary,'chromium/DevToolsActivePort'),debugPort=await until(()=>fs.existsSync(active)&&fs.readFileSync(active,'utf8').split('\n')[0]);
 const tabs=await(await fetch('http://127.0.0.1:'+debugPort+'/json')).json(),target=tabs.find(t=>t.type==='page'&&t.url==='about:blank');assert.ok(target);
 ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
 let id=0;const pending=new Map(),send=(method,params={})=>new Promise((resolve,reject)=>{pending.set(++id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
 ws.onmessage=e=>{const m=JSON.parse(e.data);loads.observe(m);if(m.id){const p=pending.get(m.id);pending.delete(m.id);m.error?p.reject(m.error):p.resolve(m.result);}if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails);};
 const evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;};
 const click=id=>evaluate(`document.getElementById(${JSON.stringify(id)}).click()`);
 const fill=(id,value)=>evaluate(`(()=>{const e=document.getElementById(${JSON.stringify(id)});e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));})()`);
 const api=async(route,body)=>{const r=await fetch(base+'/api/workbench/'+route,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const d=await r.json();assert.ok(r.ok,JSON.stringify(d));return d;};
 const source=await api('import',{kind:'text',name:'Preserved owned source',text:'Human authors this record.',groups:['source-family'],rights:'Authored'});
 await send('Page.enable');await send('Page.setLifecycleEventsEnabled',{enabled:true});await send('Runtime.enable');await send('Page.navigate',{url:base+'/workbench'});await until(()=>evaluate('document.getElementById("notice")?.textContent==="Collection ready."'));
 await evaluate('openRecord('+JSON.stringify(source.id)+')');await fill('label','retain dirty target');
 await evaluate('document.querySelector(".record input").click();document.getElementById("pumas-owner-panel").open=true');
 const selection=await evaluate('releaseBody().items'),before=await api('records/'+source.id);
 await fill('text-classification-proposal-url','http://127.0.0.1:31000');await click('pumas-owner-list');await until(()=>evaluate('!pumasOwnerOperation'));
 let observation=null,libraries=null;
 if(!native){assert.match(await evaluate('document.getElementById("pumas-owner-status").textContent'),/No trusted local Pumas bridge/);}
 else{
  libraries=await evaluate('pumasOwnerLibraries');assert.equal(libraries.registered_libraries.length,3);assert.equal(await evaluate('document.getElementById("pumas-owner-library").value'),'');
  await fill('pumas-owner-library',selected.id);assert.equal(await evaluate('document.getElementById("pumas-owner-observe").disabled'),false,'selected observe enabled');await click('pumas-owner-observe');await until(async()=>{const state=await evaluate('({busy:!!pumasOwnerOperation,receipt:!!pumasOwnerReceipt,status:document.getElementById("pumas-owner-status").textContent})');if(!state.busy&&!state.receipt)throw Error(state.status+" exceptions="+JSON.stringify(errors));return !state.busy&&state.receipt;});
  observation=await evaluate('pumasOwnerReceipt');assert.equal(observation.observation.selected.root,selected.root);assert.equal(await evaluate('document.getElementById("text-classification-proposal-url").value'),'http://127.0.0.1:31000');
  // Original SDK identity is real; this authored descriptor responder has no
  // serving/typed routes. This refusal is NOT a native PR48 RPC-router claim.
  await click('pumas-owner-models');await until(()=>evaluate('!pumasOwnerOperation'));
  assert.match(await evaluate('document.getElementById("pumas-owner-status").textContent'),/Owner-bound typed use unavailable; no fallback/);
  assert.equal(await evaluate('pumasOwnerTypedInspection'),null);assert.equal(await evaluate('document.getElementById("text-classification-proposal-url").value'),'http://127.0.0.1:31000');
  await fill('text-classification-proposal-protocol','pumas_typed_v1');await click('pumas-owner-use');assert.match(await evaluate('document.getElementById("pumas-owner-status").textContent'),/separate producer stacks/);
  await fill('text-classification-proposal-protocol','legacy');
  // Hold decoded HTTP response without changing original SDK outcome; later edits own configuration.
  await evaluate('window.savedOwnerFetch=fetch;window.ownerHeld=null;window.fetch=async(...a)=>{const r=await savedOwnerFetch(...a);if(a[0]==="/api/generation/local-pumas/use")await new Promise(resolve=>ownerHeld=resolve);return r;};');
  await click('pumas-owner-use');await until(()=>evaluate('!!ownerHeld'));await fill('text-classification-proposal-profile','later-profile');await evaluate('ownerHeld();window.fetch=savedOwnerFetch');await until(()=>evaluate('!pumasOwnerOperation'));
  assert.equal(await evaluate('document.getElementById("text-classification-proposal-url").value'),'http://127.0.0.1:31000');
  await click('pumas-owner-use');await until(()=>evaluate('!pumasOwnerOperation'));assert.equal(await evaluate('document.getElementById("text-classification-proposal-url").value'),endpoint);
  fs.writeFileSync(path.join(ownerRoot,'mode'),'wrong-service');await click('pumas-owner-use');await until(()=>evaluate('!pumasOwnerOperation'));assert.equal(await evaluate('pumasOwnerReceipt'),null);assert.match(await evaluate('document.getElementById("pumas-owner-status").textContent'),/could not be observed\/authenticated/);fs.writeFileSync(path.join(ownerRoot,'mode'),'');
  await click('pumas-owner-observe');await until(async()=>{const state=await evaluate('({busy:!!pumasOwnerOperation,receipt:!!pumasOwnerReceipt,status:document.getElementById("pumas-owner-status").textContent})');if(!state.busy&&!state.receipt)throw Error(state.status+" exceptions="+JSON.stringify(errors));return !state.busy&&state.receipt;});
  await evaluate('window.ownerHeld=null;window.fetch=async(...a)=>{const r=await savedOwnerFetch(...a);if(a[0]==="/api/generation/local-pumas/use")await new Promise(resolve=>ownerHeld=resolve);return r;};');
  await click('pumas-owner-use');await until(()=>evaluate('!!ownerHeld'));
  await evaluate('window.dispatchEvent(new PageTransitionEvent("pagehide",{persisted:true}));window.dispatchEvent(new PageTransitionEvent("pageshow",{persisted:true}));ownerHeld();window.fetch=savedOwnerFetch');
  await click('pumas-owner-list');await until(()=>evaluate('!pumasOwnerOperation&&!!pumasOwnerLibraries'));assert.equal(await evaluate('pumasOwnerReceipt'),null);
  assert.equal(await evaluate('document.getElementById("label").value'),'retain dirty target');assert.deepEqual(await evaluate('releaseBody().items'),selection);assert.deepEqual(await api('records/'+source.id),before);
  const old=(await send('Page.getFrameTree')).frameTree.frame;await send('Page.reload',{ignoreCache:true});await until(()=>loads.reloaded(old));await until(()=>evaluate('document.getElementById("notice")?.textContent==="Collection ready."'));
  assert.equal(await evaluate('pumasOwnerReceipt'),null,'Reload cannot restore/authenticate a saved observation');
  await evaluate('document.getElementById("pumas-owner-panel").open=true');await click('pumas-owner-list');await until(()=>evaluate('!pumasOwnerOperation&&!!pumasOwnerLibraries'));await fill('pumas-owner-library',selected.id);await click('pumas-owner-observe');await until(async()=>{const state=await evaluate('({busy:!!pumasOwnerOperation,receipt:!!pumasOwnerReceipt,status:document.getElementById("pumas-owner-status").textContent})');if(!state.busy&&!state.receipt)throw Error(state.status+" exceptions="+JSON.stringify(errors));return !state.busy&&state.receipt;});observation=await evaluate('pumasOwnerReceipt');
 }
 await evaluate('document.getElementById("pumas-owner-panel").scrollIntoView({block:"start"})');
 const desktop=await send('Page.captureScreenshot',screenshotOptions);fs.writeFileSync(path.join(report,'owner-reuse-desktop.jpg'),Buffer.from(desktop.data,'base64'));
 await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});await evaluate('document.getElementById("pumas-owner-panel").scrollIntoView({block:"start"})');
 const narrow=await send('Page.captureScreenshot',screenshotOptions);fs.writeFileSync(path.join(report,'owner-reuse-narrow.jpg'),Buffer.from(narrow.data,'base64'));
 let requests=[];
 if(native){
  requests=fs.readFileSync(path.join(ownerRoot,'requests.jsonl'),'utf8').trim().split('\n').map(line=>JSON.parse(line).request);assert.ok(requests.every(r=>r.startsWith('GET /.well-known/pumas HTTP/')||r.startsWith('GET /v1/models HTTP/')));
  fs.writeFileSync(path.join(report,'libraries.json'),JSON.stringify(libraries,null,2));fs.writeFileSync(path.join(report,'authenticated-observation.json'),JSON.stringify(observation,null,2));
 }
 assert.deepEqual(errors,[]);ws.close();ws=null;
 server.kill('SIGTERM');await until(()=>server.exitCode!==null);assert.equal(server.exitCode,0,stderr);
 let shutdown=null;if(native){shutdown=JSON.parse(fs.readFileSync(path.join(ownerRoot,'shutdown.json')));assert.equal(shutdown.remaining_instances,0);fs.writeFileSync(path.join(report,'ordered-shutdown.json'),JSON.stringify(shutdown,null,2));}
 const files=fs.readdirSync(report);const hashes=Object.fromEntries(files.map(n=>[n,sha(fs.readFileSync(path.join(report,n)))]));
 fs.writeFileSync(path.join(report,'session.json'),JSON.stringify({result:'PASS',native_original_SDK_fixture:native,scope,producer_head:'ab9890fe3248ed7c435b958cded0b131b0700a35',source_record:source.id,
  receipt_preserved_on_reload:false,fresh_document_verified:native,consumer_owner_startups:0,model_operation_or_acquisition_requests:0,serving_catalog_reads:requests.filter(r=>r.startsWith('GET /v1/models HTTP/')).length,typed_route_refusal_scope:'Original SDK core identity with authored HTTP responder lacking serving routes; production PR48 absence is source-confirmed separately',HTTP_requests:requests,artifact_hashes:hashes,ordered_shutdown:shutdown,original_packet_acceptance:false,errors},null,2));
 console.log('PASS original SDK observation/owned native fixture='+native+' '+report);
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{if(ws)ws.close();for(const child of children)if(child.exitCode===null)child.kill('SIGTERM');if(server&&server.exitCode===null){for(let i=0;i<200&&server.exitCode===null;i++)await pause(100);}fs.rmSync(temporary,{recursive:true,force:true});});
