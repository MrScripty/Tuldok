// Native browser smoke test. No npm dependencies.
const {qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process');
const root=process.env.TULDOK_SOURCE_ROOT||path.resolve(__dirname,'..');
const report=qaDirectory(root,'pumas-model-selection');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-text-classification-proposals-browser-')),children=[];
let ws, inspect;
const extraSockets=[];
const errors=[];
const {pageLoadTracker}=require('./browser_page_load.cjs');const pageLoads=pageLoadTracker();
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn){for(let i=0;i<150;i++){const value=await fn();if(value)return value;await pause(100);}throw Error('Timed out');}
function launch(command,args,options={}){const child=spawn(command,args,options);children.push(child);return child;}
(async()=>{
  console.log('Typed Pumas evidence: '+report);
  const server=launch('python3',['-u','tests/browser_pumas_model_selection_server.py','--port','0','--data',path.join(temporary,'data')],{cwd:root,stdio:['ignore','pipe','pipe'],env:{...process.env,TULDOK_PUMAS_SELECTION_READ_LOG:path.join(report,'transport-read-calls.jsonl')}});
  let output='',stderr='';server.stdout.on('data',data=>output+=data);server.stderr.on('data',data=>stderr+=data);
  const port=await until(()=>output.match(/Tuldok: http:\/\/127\.0\.0\.1:(\d+)/)?.[1]);
  launch(process.env.BROWSER||'/usr/bin/chromium',['--headless','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--window-size=1400,950','--user-data-dir='+path.join(temporary,'browser'),'about:blank'],{stdio:['ignore','ignore','ignore'],env:{...process.env,HOME:temporary,XDG_CONFIG_HOME:temporary,XDG_CACHE_HOME:temporary}});
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

  const gateway=output.match(/TYPED_GATEWAY=(.+)/)[1],origin=output.match(/TYPED_ORIGIN=(.+)/)[1];
  const source=await makeText('Selected typed text','Human authors this source.');
  const before=await request('records/'+source.id),observations=[];
  await send('Page.enable');await send('Runtime.enable');await send('Page.navigate',{url:base+'/workbench'});
  await until(()=>evaluate('document.getElementById("notice")?.textContent === "Collection ready."'));
  await evaluate('openRecord('+JSON.stringify(source.id)+')');
  for(const p of ['text-classification-proposal','grounded']){
    await fill(p+'-protocol','pumas_typed_v1');await fill(p+'-url',gateway);await click(p+'-models');
    await until(()=>evaluate('Array.from(document.getElementById('+JSON.stringify(p+'-model')+').options).some(o=>o.value==="controlled-text")'));
    await fill(p+'-model','controlled-text');await fill(p+'-profile','');await click(p+'-selection-inspect');
    await until(()=>evaluate('!document.getElementById('+JSON.stringify(p+'-selection-use')+').disabled'));
    const observation=JSON.parse(await evaluate('document.getElementById('+JSON.stringify(p+'-capability-metadata')+').textContent'));observations.push(observation);
    assert.equal(observation.profile,'controlled-text-cpu');assert.equal(observation.owner_authenticated,false);assert.equal(observation.inference_admitted,false);
    assert.equal(await evaluate('document.getElementById('+JSON.stringify(p+'-profile')+').value'),'');
    await click(p+'-selection-use');await until(()=>evaluate('document.getElementById('+JSON.stringify(p+'-capability-metadata')+').textContent.includes("configuration_applied")'));
    assert.equal(await evaluate('document.getElementById('+JSON.stringify(p+'-profile')+').value'),'controlled-text-cpu');
    // A real HTTP response held after completion must not apply after an edit.
    await fill(p+'-profile','');await click(p+'-selection-inspect');await until(()=>evaluate('!document.getElementById('+JSON.stringify(p+'-selection-use')+').disabled'));
    await evaluate('window.originalSelectionFetch=fetch;window.selectionRelease=null;window.fetch=async(...args)=>{const r=await originalSelectionFetch(...args);if(args[0]==="/api/generation/typed-selection")await new Promise(resolve=>selectionRelease=resolve);return r;};');
    await click(p+'-selection-use');await until(()=>evaluate('!!selectionRelease'));await fill(p+'-profile','no-event-edit');
    await evaluate('selectionRelease();window.fetch=originalSelectionFetch');await pause(100);
    assert.equal(await evaluate('document.getElementById('+JSON.stringify(p+'-profile')+').value'),'no-event-edit');
    assert.equal(await evaluate('document.getElementById('+JSON.stringify(p+'-selection-use')+').disabled'),true);
  }
  assert.deepEqual(await request('records/'+source.id),before);
  assert.deepEqual((await request('text-classification-proposals')).jobs,[]);assert.deepEqual((await request('grounded/jobs')).jobs,[]);
  assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'));
  const shot=await send('Page.captureScreenshot',screenshotOptions);fs.writeFileSync(path.join(report,'selected-text-model.jpg'),Buffer.from(shot.data,'base64'));
  const transportCalls=fs.readFileSync(path.join(report,'transport-read-calls.jsonl'),'utf8').trim().split('\n').map(JSON.parse);
  assert.ok(transportCalls.length>=12);assert.ok(transportCalls.every(r=>r.method==='GET'&&r.completed&&r.response_sha256.length===64));
  fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify({origin,gateway,observations,preserved_record:before,proposal_jobs_started:0,transportCalls,errors},null,2));
  assert.deepEqual(errors,[]);console.log('Exact-profile Inspect/Use for both text purposes, held edit refusals, preserved record and zero proposals passed: '+origin);
})().catch(async error=>{console.error(error);console.error('Runtime errors:',JSON.stringify(errors));if(inspect)try{console.error('Page diagnostics:',await inspect());}catch(diagnostic){console.error('Diagnostics failed:',diagnostic);}process.exitCode=1;}).finally(async()=>{if(ws)ws.close();for(const child of children)child.kill();await pause(200);fs.rmSync(temporary,{recursive:true,force:true});});
