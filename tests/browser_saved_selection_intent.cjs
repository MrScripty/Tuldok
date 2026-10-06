// Native browser smoke test. No npm dependencies.
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process');
const root=path.resolve(process.env.TULDOK_SOURCE_ROOT||path.join(__dirname,'..')),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-intent-browser-')),children=[];
let ws, inspect;
const errors=[];
const {pageLoadTracker}=require('./browser_page_load.cjs');const pageLoads=pageLoadTracker();
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn){for(let i=0;i<150;i++){const value=await fn();if(value)return value;await pause(100);}throw Error('Timed out');}
function launch(command,args,options={}){const child=spawn(command,args,options);children.push(child);return child;}
(async()=>{
  const server=launch('python3',['-u','tests/browser_server.py','--port','0','--data',path.join(temporary,'data')],{cwd:root,stdio:['ignore','pipe','pipe']});
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
  const base='http://127.0.0.1:'+port;
  const request=async(path,body)=>{const response=await fetch(base+'/api/workbench/'+path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const result=await response.json();assert.ok(response.ok,JSON.stringify(result));return result;};
  async function seed(name) {
    const row=await request('import',{kind:'text',name,text:'Source text for '+name,groups:[name],rights:'owned fixture'});
    return request('records/'+row.id,{...row,annotation:{label:'accepted'},review:'human_reviewed'});
  }
  const member=await seed('Fixed member'),manual=await seed('Manual choice');
  const ref=row=>({id:row.id,revision:row.revision,source_revision:row.source_revision});
  const saved=await request('selections',{name:'Fixed set',items:[ref(member)]});
  const failures=[];
  async function verify(name,fn){try{await fn();console.log('PASS',name);}catch(error){failures.push({name,error:error.message});console.error('FAIL',name,error.message);}}
  await send('Page.enable');await send('Runtime.enable');await send('Page.setLifecycleEventsEnabled',{enabled:true});
  const injected=await send('Page.addScriptToEvaluateOnNewDocument',{source:`(()=>{
    const original=window.fetch;window.transportPending=0;window.fixedOpenCalls=0;window.releaseInitialListing=null;
    let firstList=true;window.fetch=async(...args)=>{const url=String(args[0]);const initial=firstList && url.endsWith('/selections') && !args[1]?.method;
      if(initial)firstList=false;if(url.includes('/selections/'))window.fixedOpenCalls++;window.transportPending++;
      try{const response=await original(...args);if(initial)await new Promise(resolve=>window.releaseInitialListing=resolve);return response;}
      finally{window.transportPending--;}};
  })()`});
  await send('Page.navigate',{url:base+'/workbench#selection='+saved.id});
  await until(()=>evaluate('document.getElementById("notice")?.textContent === "Collection ready." && typeof window.releaseInitialListing === "function"'));
  await verify('initial list cannot override newer manual selection',async()=>{
    await evaluate('document.querySelectorAll(".record")[Array.from(document.querySelectorAll(".record button")).findIndex(b=>b.textContent.includes("Manual choice"))].querySelector("input").click()');
    assert.deepEqual(await evaluate('[...selected.keys()]'),[manual.id]);
    await evaluate('window.releaseInitialListing()');
    await until(()=>evaluate('savedSets.size===1 && !savedLoadBusy && window.transportPending===0'));
    assert.deepEqual(await evaluate('[...selected.keys()]'),[manual.id]);
    assert.equal(await evaluate('window.fixedOpenCalls'),0,'Obsolete URL intent issues no record-set load');
  });
  await send('Page.removeScriptToEvaluateOnNewDocument',{identifier:injected.identifier});
  // Editor persistence succeeds at the real server, while only its response delivery is delayed.
  await verify('pending editor response cannot make stale fixed pairs release-eligible',async()=>{
    await evaluate('history.replaceState(null,"","/workbench");selected.clear();selection();');
    await evaluate('openRecord('+JSON.stringify(member.id)+')');
    await evaluate('selected.set(current.id,current);selection()');
    await fill('label','Changed annotation');await fill('record-review','human_reviewed');
    await evaluate(`(()=>{const original=window.fetch;window.resumeEditor=null;
      window.fetch=async(...args)=>{const response=await original(...args);if(String(args[0]).endsWith('/records/${member.id}') && args[1]?.method==='POST')await new Promise(resolve=>window.resumeEditor=resolve);return response;};})()`);
    await evaluate('document.getElementById("editor").requestSubmit()');
    await until(()=>evaluate('typeof window.resumeEditor === "function"'));
    await evaluate('document.getElementById("saved-selection").value='+JSON.stringify(saved.id));
    await click('load-selection');
    await until(()=>evaluate('!savedLoadBusy && document.getElementById("saved-selection-status").textContent.startsWith("Opened")'));
    assert.equal(await evaluate('selected.get('+JSON.stringify(member.id)+').revision'),member.revision);
    await evaluate('window.resumeEditor()');
    await until(()=>evaluate('!document.getElementById("editor").dataset.busy'));
    const after=await request('records/'+member.id);
    assert.equal(after.revision,member.revision+1);assert.equal(after.review,'human_reviewed');
    assert.equal(await evaluate('current.revision'),after.revision,'Successful editor state remains independently visible');
    const controls={ratios:{train:100,validation:0,test:0},seed:7};
    const fixedPreview=await request('releases/preview',{...controls,items:[ref(member)]});
    assert.equal(fixedPreview.eligible,false);assert.ok(fixedPreview.blockers.some(b=>b.code==='conflict'));
    const newerPreview=await request('releases/preview',{...controls,items:[ref(after)]});
    assert.equal(newerPreview.eligible,true,'The newer reviewed pair would be eligible if silently substituted');
    const selectedBody=await evaluate('releaseBody().items');
    const actualPreview=await request('releases/preview',{...controls,items:selectedBody});
    console.log('Release eligibility:',JSON.stringify({storedFixed:fixedPreview.eligible,currentPair:newerPreview.eligible,actualSelected:actualPreview.eligible}));
    assert.equal(actualPreview.eligible,false,'Actual selected request must stay blocked; adopting a newer eligible pair requires reselection');
    assert.deepEqual(selectedBody,[ref(member)]);
    await fill('train',100);await fill('validation',0);await fill('test',0);await click('preview-release');
    await until(()=>evaluate('document.getElementById("release-preview").textContent.includes("Selection changed")'));
    assert.equal(await evaluate('document.getElementById("freeze-release").disabled'),true,'The actual selected preview remains blocked');
    const reopened=await request('selections/'+saved.id);assert.deepEqual(reopened.selection.items,saved.items);
    await evaluate('document.getElementById("release-preview-status").scrollIntoView()');
    if(!process.env.TULDOK_SOURCE_ROOT){const reports=path.join(root,'docs/plans/saved-selection-intent/reports');fs.mkdirSync(reports,{recursive:true});
      const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});fs.writeFileSync(path.join(reports,'intent-blocked.png'),Buffer.from(shot.data,'base64'));}
    // Adoption is still possible through an explicit current-record selection action.
    await fill('query','Fixed member');await evaluate('document.getElementById("filters").requestSubmit()');
    await until(()=>evaluate('page.total===1 && !document.getElementById("filters").dataset.busy'));
    await click('select-page');await until(()=>evaluate('!document.getElementById("select-page").dataset.busy'));
    assert.deepEqual(await evaluate('releaseBody().items'),[ref(after)]);
    await click('preview-release');await until(()=>evaluate('!document.getElementById("freeze-release").disabled'));
  });
  await verify('same-pair reselection drops preview after earlier editor proves staleness',async()=>{
    const original=await seed('Cached same pair');
    await evaluate('selected.clear();selection(true)');
    await fill('query','Cached same pair');await evaluate('document.getElementById("filters").requestSubmit()');
    await until(()=>evaluate('page.total===1 && !document.getElementById("filters").dataset.busy'));
    await click('select-page');await until(()=>evaluate('!document.getElementById("select-page").dataset.busy'));
    await evaluate('openRecord('+JSON.stringify(original.id)+')');
    await click('preview-release');await until(()=>evaluate('!document.getElementById("freeze-release").disabled'));
    const body=await evaluate('releaseBody()'),proof=await evaluate('releasePreview.preview_token');
    await fill('label','Newer reviewed annotation');await fill('record-review','human_reviewed');
    await evaluate(`(()=>{const original=window.fetch;window.resumeCachedEditor=null;window.fetch=async(...args)=>{const response=await original(...args);if(String(args[0]).endsWith('/records/${original.id}')&&args[1]?.method==='POST')await new Promise(resolve=>window.resumeCachedEditor=resolve);return response;};})()`);
    await evaluate('document.getElementById("editor").requestSubmit()');await until(()=>evaluate('!!window.resumeCachedEditor'));
    await click('select-page');await until(()=>evaluate('!document.getElementById("select-page").dataset.busy'));
    assert.deepEqual(await evaluate('releaseBody().items'),[ref(original)]);
    assert.equal(await evaluate('releasePreview.preview_token'),proof,'Same pair remains cached before acknowledgment');
    await evaluate('window.resumeCachedEditor()');await until(()=>evaluate('!document.getElementById("editor").dataset.busy'));
    const newest=await request('records/'+original.id);
    assert.equal(await evaluate('current.revision'),newest.revision);assert.equal(newest.revision,original.revision+1);
    assert.deepEqual(await evaluate('releaseBody().items'),[ref(original)]);
    const stale=await request('releases/preview',body);assert.equal(stale.eligible,false);
    const current=await request('releases/preview',{...body,items:[ref(newest)]});assert.equal(current.eligible,true);
    const response=await fetch(base+'/api/workbench/releases',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...body,preview_token:proof})});
    assert.equal(response.status,409,'Server continues rejecting stale export');
    console.log('Cached same-pair completion:',JSON.stringify(await evaluate('({selectedRevision:releaseBody().items[0].revision,editorRevision:current.revision,cachedEligible:releasePreview?.eligible??null,freezeDisabled:document.getElementById("freeze-release").disabled})')));
    assert.equal(await evaluate('releasePreview'),null,'Known stale cached eligibility is discarded');
    assert.equal(await evaluate('document.getElementById("freeze-release").disabled'),true);
  });
  assert.deepEqual(errors,[]);assert.deepEqual(failures,[]);
  console.log('Real Chromium initial-list/manual-intent ordering and pending-editor fixed-pair release blocker/adoption passed.');
})().catch(async error=>{console.error(error);console.error('Runtime errors:',JSON.stringify(errors));if(inspect)try{console.error('Page diagnostics:',await inspect());}catch(diagnostic){console.error('Diagnostics failed:',diagnostic);}process.exitCode=1;}).finally(async()=>{if(ws)ws.close();for(const child of children)child.kill();await pause(200);fs.rmSync(temporary,{recursive:true,force:true});});
