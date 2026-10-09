// Native browser smoke test. No npm dependencies.
const {qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process');
const root=path.resolve(process.env.TULDOK_SOURCE_ROOT||path.join(__dirname,'..'));
const report=qaDirectory(root,'saved-searches');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-search-browser-')),children=[];
let ws, inspect, allowDialog=true;
const errors=[];
const {pageLoadTracker}=require('./browser_page_load.cjs');const pageLoads=pageLoadTracker();
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn){for(let i=0;i<150;i++){const value=await fn();if(value)return value;await pause(100);}throw Error('Timed out');}
function launch(command,args,options={}){const child=spawn(command,args,options);children.push(child);return child;}
(async()=>{
  const server=launch('python3',['-u','tests/browser_server.py','--port','0','--data',path.join(temporary,'data')],{cwd:root,stdio:['ignore','pipe','pipe']});
  let output='',stderr='';server.stdout.on('data',data=>output+=data);server.stderr.on('data',data=>stderr+=data);
  const port=await until(()=>output.match(/127\.0\.0\.1:(\d+)/)?.[1]);
  launch(process.env.BROWSER||'/usr/bin/chromium',['--headless','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--window-size=1400,950','--user-data-dir='+path.join(temporary,'browser'),'about:blank'],{stdio:['ignore','ignore','inherit'],env:{...process.env,XDG_CONFIG_HOME:temporary,XDG_CACHE_HOME:temporary}});
  const active=path.join(temporary,'browser','DevToolsActivePort');
  const debugPort=await until(()=>fs.existsSync(active)&&fs.readFileSync(active,'utf8').split('\n')[0]);
  const tabs=await(await fetch('http://127.0.0.1:'+debugPort+'/json')).json();
  const target=tabs.find(tab=>tab.type==='page' && tab.url==='about:blank');
  assert.ok(target,'Expected the explicitly launched blank page target');
  ws=new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  let id=0;const pending=new Map();
  ws.onmessage=event=>{const message=JSON.parse(event.data);pageLoads.observe(message);if(message.id){const task=pending.get(message.id);pending.delete(message.id);message.error?task.reject(message.error):task.resolve(message.result);}if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails);if(message.method==='Page.javascriptDialogOpening')send('Page.handleJavaScriptDialog',{accept:allowDialog}).catch(error=>errors.push(error));};
  const send=(method,params={})=>new Promise((resolve,reject)=>{pending.set(++id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
  const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  inspect=()=>evaluate('JSON.stringify({url:location.href,ready:document.readyState,notice:document.getElementById("notice")?.textContent,body:document.body?.innerText.slice(0,1500),viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,overflow:[...document.querySelectorAll("body *")].filter(e=>e.getBoundingClientRect().right>innerWidth || e.scrollWidth>e.clientWidth+1).map(e=>({tag:e.tagName,id:e.id,class:e.className,right:e.getBoundingClientRect().right,width:e.getBoundingClientRect().width})).slice(0,30)})');
  const click=id=>evaluate('document.getElementById('+JSON.stringify(id)+').click()');
  const fill=(id,value)=>evaluate('(()=>{const e=document.getElementById('+JSON.stringify(id)+');e.value='+JSON.stringify(value)+';e.dispatchEvent(new Event("input",{bubbles:true}));e.dispatchEvent(new Event("change",{bubbles:true}));})()');
  await send('Page.enable');await send('Runtime.enable');await send('Page.setLifecycleEventsEnabled',{enabled:true});
  await send('Page.navigate',{url:'http://127.0.0.1:'+port+'/workbench'});
  await until(()=>evaluate('document.getElementById("notice")?.textContent === "Collection ready."'));
  const base='http://127.0.0.1:'+port;
  const api=async(route,body)=>{const response=await fetch(base+'/api/workbench/'+route,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const result=await response.json();assert.ok(response.ok,JSON.stringify(result));return result;};
  const submit=id=>evaluate('document.getElementById('+JSON.stringify(id)+').requestSubmit()');
  const label='exact\r\nlabel',group='group\rvalue',rights='rights\nvalue';
  async function source(name,matching=true){const row=await api('import',{kind:'text',name,text:'Actual authored '+name,groups:[matching?group:name],rights:matching?rights:'owned'});return api('records/'+row.id,{...row,annotation:{label:matching?label:'other'},review:'human_reviewed'});}
  const first=await source('Alpha1'),other=await source('Beta',false),ref=row=>({id:row.id,revision:row.revision,source_revision:row.source_revision});
  await evaluate('refresh()');await evaluate('document.querySelector('+JSON.stringify('input[aria-label="Select Alpha1"]')+').click()');
  await fill('train',100);await fill('validation',0);await fill('test',0);await fill('selection-name','Fixed before dynamic');await submit('save-selection-form');
  await until(()=>evaluate('document.getElementById("saved-selection-status").textContent.startsWith("Saved “Fixed before dynamic”")'));
  const fixedId=await evaluate('document.getElementById("saved-selection").value');await click('load-selection');await until(()=>evaluate('!savedLoadBusy&&location.hash.startsWith("#selection=")'));
  await click('preview-release');await until(()=>evaluate('releasePreview?.eligible'));const proof=await evaluate('JSON.stringify(releasePreview)'),pairs=await evaluate('releaseBody().items'),hash=await evaluate('location.hash');
  await evaluate('openRecord('+JSON.stringify(first.id)+')');await fill('label','Retain this unsaved target');
  const editor=await evaluate('JSON.stringify({current:current.id,revision:current.revision,label:document.getElementById("label").value,dirty})');
  const before=[await api('records/'+first.id),await api('history/'+first.id),await api('records/'+other.id),await api('history/'+other.id)];
  await evaluate('document.getElementById("saved-search-panel").open=true');await fill('query','Alpha');await fill('kind','text');await fill('exact-filter-format','json');
  await fill('label-filter',JSON.stringify(label));await fill('group-filter',JSON.stringify(group));await fill('rights-filter',JSON.stringify(rights));await fill('search-name','Matching authored sources');
  assert.equal(await evaluate('page.total'),2,'Save entered filters before applying them');await submit('save-search-form');
  await until(()=>evaluate('document.getElementById("saved-search-status").textContent.startsWith("Saved “Matching authored sources”")&&!searchWriting'));
  const searchId=await evaluate('document.getElementById("saved-search").value'),saved=await api('searches/'+searchId);assert.equal(saved.mode,'dynamic');assert.equal(saved.criteria.label,label);assert.equal(saved.criteria.group,group);assert.equal(saved.criteria.rights,rights);
  await fill('query','Beta');await fill('label-filter','');await fill('group-filter','');await fill('rights-filter','');await click('open-search');await until(()=>evaluate('!searchOpening&&page.total===1&&document.getElementById("query").value==="Alpha"'));
  async function retained(){assert.deepEqual(await evaluate('releaseBody().items'),pairs);assert.equal(await evaluate('location.hash'),hash);assert.equal(await evaluate('JSON.stringify({current:current.id,revision:current.revision,label:document.getElementById("label").value,dirty})'),editor);}
  await retained();assert.equal(await evaluate('JSON.stringify(releasePreview)'),proof);
  assert.deepEqual([await api('records/'+first.id),await api('history/'+first.id),await api('records/'+other.id),await api('history/'+other.id)],before);
  const second=await source('Alpha2');await click('open-search');await until(()=>evaluate('!searchOpening&&page.total===2'));await retained();assert.equal(await evaluate('JSON.stringify(releasePreview)'),proof);
  assert.equal((await api('selections/'+fixedId)).selection.items.length,1);
  // Release remains the one explicitly selected revision, despite two dynamic matches.
  // Adding an unselected family member changes server preview evidence; explicitly re-preview.
  await click('preview-release');await until(()=>evaluate('releasePreview?.eligible&&!document.getElementById("freeze-release").disabled'));
  await submit('release-form');await until(()=>evaluate('!!document.querySelector("#release-result a")'));const zip=await fetch(await evaluate('document.querySelector("#release-result a").href'));assert.equal(zip.status,200);fs.writeFileSync(path.join(report,'fixed-release.zip'),Buffer.from(await zip.arrayBuffer()));
  const checked=JSON.parse(require('node:child_process').execFileSync('python3',['-c','import json,sys,zipfile;z=zipfile.ZipFile(sys.argv[1]);m=json.loads(z.read("manifest.json"));assert len(m["records"])==1;r=m["records"][0];assert r["id"]==sys.argv[2] and r["review"]=="human_reviewed" and r["annotation"]["label"]=="exact\\r\\nlabel";print(json.dumps({"records":1,"id":r["id"],"result":"PASS"}))',path.join(report,'fixed-release.zip'),first.id],{cwd:root,encoding:'utf8'}));
  // A held actual read cannot replace a no-event programmatic filter edit.
  await evaluate(`window.searchOriginalFetch=fetch;window.searchHeld=false;window.fetch=async(...args)=>{const response=await searchOriginalFetch(...args);if(args[0]===${JSON.stringify('/api/workbench/searches/'+searchId)}&&!args[1]?.method){searchHeld=true;await new Promise(resolve=>window.searchRelease=resolve);}return response;};`);
  await click('open-search');await until(()=>evaluate('searchHeld'));await evaluate('document.getElementById("query").value="Manual after held read"');await evaluate('searchRelease()');await until(()=>evaluate('!searchOpening'));assert.equal(await evaluate('document.getElementById("query").value'),'Manual after held read');await retained();await evaluate('window.fetch=searchOriginalFetch');
  // Current source edits do not advance fixed pairs or an unsaved editor via query reads.
  const changed=await api('records/'+first.id,{...first,annotation:{label:'different'},review:'draft'});assert.equal(changed.revision,3);await click('open-search');await until(()=>evaluate('!searchOpening&&page.total===1'));await retained();const stale=await api('selections/'+fixedId);assert.equal(stale.current,false);assert.equal(stale.selection.items[0].revision,2);
  await click('preview-release');await until(()=>evaluate('releasePreview?.eligible===false'));assert.equal(await evaluate('document.getElementById("freeze-release").disabled'),true);assert.match(await evaluate('JSON.stringify(releasePreview.blockers)'),/Selection changed/);
  await fill('search-rename','Renamed current search');await submit('rename-search-form');await until(()=>evaluate('!searchWriting&&document.getElementById("saved-search-status").textContent.startsWith("Renamed")'));const renamed=await api('searches/'+searchId);assert.equal(renamed.revision,2);assert.deepEqual(renamed.criteria,saved.criteria);
  await evaluate('document.getElementById("saved-search-panel").scrollIntoView()');fs.writeFileSync(path.join(report,'desktop.jpg'),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});await evaluate('document.getElementById("saved-search-panel").scrollIntoView()');assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'));fs.writeFileSync(path.join(report,'narrow.jpg'),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));
  const previous=(await send('Page.getFrameTree')).frameTree.frame;await send('Page.reload');await until(()=>pageLoads.reloaded(previous));await until(()=>evaluate('page?.total===3&&!savedLoadBusy&&savedSearches.size===1'));
  assert.equal(await evaluate('document.getElementById("query").value'),'','Reload lists searches without automatically applying any');assert.deepEqual(await evaluate('releaseBody().items'),pairs);assert.equal(await evaluate('location.hash'),hash);
  await fill('saved-search',searchId);allowDialog=false;await click('delete-search');await until(()=>evaluate('!searchWriting'));assert.equal((await api('searches')).searches.length,1);
  allowDialog=true;await click('delete-search');await until(()=>evaluate('!searchWriting&&savedSearches.size===0'));assert.deepEqual(await evaluate('releaseBody().items'),pairs);assert.equal((await api('records?')).total,3);assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(report,'session.json'),JSON.stringify({source_head:require('node:child_process').execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),result:'PASS',saved,renamed,first:ref(first),new_match:ref(second),fixed:pairs,stale_saved:stale,release:checked,checks:['entered filters saved independently of applied page','exact LF/CR/CRLF metadata restored losslessly','dynamic matches grow; dirty editor, fixed pairs, proof and URL retained','actual ZIP contains only original fixed reviewed revision','held real read fenced by no-event filter edit','stale fixed pairs block release','CAS rename; cancel/delete; reload lists only; desktop390px; no runtime errors']},null,2));
  console.log('Real Chromium saved dynamic criteria, growing results, fixed selection/release/editor isolation, stale blockers, held read, persistence/CRUD and390px passed.');
})().catch(async error=>{console.error(error);console.error('Runtime errors:',JSON.stringify(errors));if(inspect)try{console.error('Page diagnostics:',await inspect());}catch{}process.exitCode=1;}).finally(()=>{if(ws)ws.close();for(const child of children.reverse())child.kill('SIGTERM');fs.rmSync(temporary,{recursive:true,force:true});});
