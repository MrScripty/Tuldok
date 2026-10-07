// Native browser smoke test. No npm dependencies.
const {qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process');
const root=process.env.TULDOK_SOURCE_ROOT||path.resolve(__dirname,'..'),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-curation-browser-')),children=[];
let ws, inspect;
const errors=[];
const {pageLoadTracker}=require('./browser_page_load.cjs');const pageLoads=pageLoadTracker();
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn){for(let i=0;i<150;i++){const value=await fn();if(value)return value;await pause(100);}throw Error('Timed out');}
function launch(command,args,options={}){const child=spawn(command,args,options);children.push(child);return child;}
(async()=>{
  const server=launch('python3',['-u','tests/browser_curation_server.py','--port','0','--data',path.join(temporary,'data')],{cwd:root,stdio:['ignore','pipe','pipe']});
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
  async function text(name,label,groups,rights,task='text_classification') {
    const row=await request('import',{kind:'text',name,text:'Local source for '+name,groups,rights});
    return request('records/'+row.id,{...row,task,review:'human_reviewed',annotation:task==='text_entities'?{spans:[{label,start:0,end:5}]}:{label}});
  }
  async function image(name,color,task,annotation,groups,rights) {
    const bytes=await evaluate(`(()=>{const canvas=document.createElement('canvas');canvas.width=16;canvas.height=16;const c=canvas.getContext('2d');c.fillStyle=${JSON.stringify(color)};c.fillRect(0,0,16,16);return canvas.toDataURL('image/png').split(',')[1];})()`);
    const row=await request('import',{kind:'image',name,image:bytes,groups,rights});
    return request('records/'+row.id,{...row,task,annotation,review:'human_reviewed'});
  }
  await send('Page.enable');await send('Runtime.enable');await send('Page.setLifecycleEventsEnabled',{enabled:true});
  await send('Page.navigate',{url:base+'/workbench'});await until(()=>evaluate('document.getElementById("notice")?.textContent === "Collection ready."'));
  const all=(await request('records?limit=100')).items,find=name=>all.find(r=>r.name===name);
  const first=find('Fictional 00'),second=find('Fictional 01'),a=find('Duplicate A'),b=find('Duplicate B'),deleted=all.find(r=>!r.source_available);
  assert.equal(all.length,45);
  const saved=await request('selections',{name:'Fixed diagnostic set',items:[ref(first),ref(a)]});
  await evaluate('refreshSavedSets('+JSON.stringify(saved.id)+')');await click('load-selection');await until(()=>evaluate('!savedLoadBusy && selected.size===2'));
  const pairs=await evaluate('releaseBody().items');
  const snapshot=()=>{const {spawnSync}=require('node:child_process');const result=spawnSync('python3',['-c',`import sqlite3,json;db=sqlite3.connect(${JSON.stringify(path.join(temporary,'data','dataset.sqlite3'))});print(json.dumps({t:db.execute('SELECT * FROM '+t+' ORDER BY rowid').fetchall() for (t,) in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")}))`],{encoding:'utf8'});assert.equal(result.status,0,result.stderr);return result.stdout;};
  const before=snapshot();
  const diagnostic=async(category,scope='filtered')=>{await fill('curation-category',category);await fill('curation-scope',scope);await click('curation-refresh');await until(()=>evaluate('!!curationReport && !curationBusy'));return evaluate('curationReport');};
  let report=await diagnostic('unlabeled');assert.equal(report.total,44);assert.equal(report.items.length,40);
  assert.equal(await evaluate('page.items.length'),40);assert.equal(report.analysis.records,45,'analysis covers full criteria');
  await click('curation-next');await until(()=>evaluate('curationReport?.offset===40 && !curationBusy'));
  assert.equal(await evaluate('curationReport.items.length'),4);await click('curation-previous');await until(()=>evaluate('curationReport?.offset===0 && !curationBusy'));
  report=await diagnostic('duplicates');assert.deepEqual(report.items.map(r=>r.id).sort(),[a.id,b.id].sort());assert.ok(report.items.every(r=>r.duplicate_members===2));
  report=await diagnostic('missing_sources');assert.deepEqual(report.items.map(r=>r.id),[deleted.id]);
  report=await diagnostic('unknown_rights');assert.equal(report.total,44);assert.equal(snapshot(),before,'all diagnostics leave SQL/history/fixed sets unchanged');
  assert.deepEqual(await evaluate('releaseBody().items'),pairs);
  // A typed but unapplied criterion cannot mislabel the report scope.
  await fill('group-filter','images');report=await diagnostic('duplicates');assert.equal(report.analysis.records,45);assert.equal(report.filters.group,'');
  await evaluate('document.getElementById("filters").requestSubmit()');await until(()=>evaluate('page.total===3 && !document.getElementById("filters").dataset.busy'));
  report=await diagnostic('duplicates');assert.equal(report.analysis.records,3);assert.equal(report.filters.group,'images');
  await fill('query','Duplicate A');await evaluate('document.getElementById("filters").requestSubmit()');await until(()=>evaluate('page.total===1 && !document.getElementById("filters").dataset.busy'));
  report=await diagnostic('duplicates');assert.equal(report.total,0,'outside-scope duplicate does not contribute');
  report=await diagnostic('unlabeled','selected');assert.equal(report.analysis.records,2);assert.deepEqual(report.items.map(r=>r.id).sort(),pairs.map(r=>r.id).sort());
  // Real editor dirty cancellation and successful explicit inspection leave exact pairs alone.
  await evaluate('openRecord('+JSON.stringify(second.id)+')');await fill('label','unsaved');
  await evaluate('document.getElementById("label").dispatchEvent(new Event("input",{bubbles:true}));window.confirm=()=>false;document.querySelector("#curation-results button").click()');
  assert.equal(await evaluate('current.id'),second.id);assert.equal(await evaluate('dirty'),true);
  await evaluate('window.confirm=()=>true;document.querySelector("#curation-results button").click()');await until(()=>evaluate('!dirty && current.id!=='+JSON.stringify(second.id)));
  assert.deepEqual(await evaluate('releaseBody().items'),pairs);
  const changed=await request('records/'+first.id,{...first,annotation:{label:'fictional'},review:'human_reviewed'});
  report=await diagnostic('references','selected');assert.equal(report.reference_counts.stale,1);assert.equal(report.items[0].reference.requested.revision,first.revision);assert.equal(report.items[0].revision,changed.revision);
  assert.deepEqual(await evaluate('releaseBody().items'),pairs);assert.deepEqual((await request('selections/'+saved.id)).selection.items,saved.items);
  // Missing selected IDs are explicit; no inferred annotation/rights facts for absent records.
  await evaluate('selected.set("ffffffffffffffffffffffffffffffff",{id:"ffffffffffffffffffffffffffffffff",revision:1,source_revision:1});selection(true)');
  report=await diagnostic('references','selected');assert.equal(report.reference_counts.missing_record,1);
  assert.ok(await evaluate('[...document.querySelectorAll("#curation-results li")].some(li=>li.textContent.includes("Missing record")&&li.querySelector("button").disabled)'));
  await evaluate('selected.delete("ffffffffffffffffffffffffffffffff");selection(true)');
  // Delayed actual HTTP responses and repeat controls cannot paint an obsolete category/scope.
  await evaluate(`window.originalFetch=window.fetch;window.diagHeld=[];window.fetch=async(...args)=>{const response=await originalFetch(...args);if(String(args[0]).endsWith('/curation'))await new Promise(resolve=>diagHeld.push(resolve));return response;};`);
  await click('curation-refresh');await until(()=>evaluate('diagHeld.length===1'));await click('curation-refresh');assert.equal(await evaluate('diagHeld.length'),1);
  await fill('curation-category','unknown_rights');await click('curation-refresh');await until(()=>evaluate('diagHeld.length===2'));
  await evaluate('diagHeld[1]()');await until(()=>evaluate('curationReport?.category==="unknown_rights" && !curationBusy'));
  await evaluate('diagHeld[0]()');await pause(150);assert.equal(await evaluate('curationReport.category'),'unknown_rights');
  await click('curation-refresh');await until(()=>evaluate('diagHeld.length===3'));
  await fill('curation-scope','filtered');await evaluate('diagHeld[2]()');await pause(150);assert.equal(await evaluate('curationReport'),null);
  await evaluate('window.fetch=originalFetch');
  // Actual delayed collection HTTP blocks diagnostic requests until applied scope is known.
  await evaluate(`window.queryHeld=[];window.diagStarts=0;window.fetch=async(...args)=>{if(String(args[0]).endsWith('/curation'))++diagStarts;const response=await originalFetch(...args);if(String(args[0]).includes('/records?'))await new Promise(resolve=>queryHeld.push(resolve));return response;};`);
  await fill('query','Fictional');await fill('group-filter','');
  await evaluate('document.getElementById("filters").requestSubmit()');await until(()=>evaluate('queryHeld.length===1'));
  assert.equal(await evaluate('document.getElementById("curation-refresh").disabled'),true);
  await evaluate('curationLoad(0,true)');assert.equal(await evaluate('diagStarts'),0);
  await evaluate('queryHeld[0]()');await until(()=>evaluate('page.total===42 && !document.getElementById("filters").dataset.busy'));
  assert.equal(await evaluate('curationReport'),null);assert.equal(await evaluate('page.criteria.q'),'fictional');
  await evaluate('window.fetch=originalFetch');
  // Freshness-bound paging through actual server: current annotations change while page is held.
  await fill('query','');await fill('group-filter','');await evaluate('document.getElementById("filters").requestSubmit()');await until(()=>evaluate('page.total===45 && !document.getElementById("filters").dataset.busy'));
  report=await diagnostic('unlabeled');await request('records/'+second.id,{...second,annotation:{label:'fictional'},review:'human_reviewed'});
  await click('curation-next');await until(()=>evaluate('!curationBusy && !curationReport'));
  assert.ok((await evaluate('document.getElementById("curation-status").textContent')).includes('facts changed'));
  report=await diagnostic('unlabeled');assert.equal(report.total,42);
  // Deleted selected source retains requested source revision and fails freshness rather than adopting it.
  const deletion=await fetch(base+'/api/samples/delete/'+a.id,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision:a.source_revision})});assert.ok(deletion.ok,await deletion.text());
  report=await diagnostic('references','selected');assert.equal(report.reference_counts.source_deleted,1);assert.equal(report.reference_counts.stale,2);
  assert.deepEqual(await evaluate('releaseBody().items'),pairs);
  // Existing export owner still produces a downloadable ZIP for a reviewed target.
  const negative=find('Reviewed negative'),releaseBody={items:[ref(negative)],format:'canonical_v1',ratios:{train:100,validation:0,test:0},seed:42};
  const preview=await request('releases/preview',releaseBody);assert.equal(preview.eligible,true);
  const release=await request('releases',{...releaseBody,preview_token:preview.preview_token});
  const zip=await fetch(base+release.url);assert.equal(zip.status,200);assert.ok((await zip.arrayBuffer()).byteLength>500);
  assert.deepEqual(await evaluate('releaseBody().items'),pairs);
  const reports=qaDirectory(root,'curation-diagnostics');fs.mkdirSync(reports,{recursive:true});
  await evaluate('document.getElementById("curation-panel").scrollIntoView()');
  const desktop=await send('Page.captureScreenshot',screenshotOptions);fs.writeFileSync(path.join(reports,'curation-desktop.jpg'),Buffer.from(desktop.data,'base64'));
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
  await evaluate('document.getElementById("curation-panel").scrollIntoView()');const narrow=await send('Page.captureScreenshot',screenshotOptions);fs.writeFileSync(path.join(reports,'curation-narrow.jpg'),Buffer.from(narrow.data,'base64'));
  assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'),'390px diagnostic controls and IDs do not overflow');
  await evaluate('document.getElementById("curation-results").scrollIntoView()');
  const membersNarrow=await send('Page.captureScreenshot',screenshotOptions);fs.writeFileSync(path.join(reports,'curation-members-narrow.jpg'),Buffer.from(membersNarrow.data,'base64'));
  await send('Emulation.clearDeviceMetricsOverride');await evaluate('document.getElementById("curation-results").scrollIntoView()');
  const membersDesktop=await send('Page.captureScreenshot',screenshotOptions);fs.writeFileSync(path.join(reports,'curation-members-desktop.jpg'),Buffer.from(membersDesktop.data,'base64'));
  assert.deepEqual(errors,[]);
  console.log('Actual Chromium: full filtered contributors/paging, exact scoped duplicates, deleted sources, unknown notes, unchanged SQL/fixed pairs, dirty inspection, stale/missing IDs, delayed/repeated controls, freshness409, release ZIP and desktop/narrow screenshots passed.');
})().catch(async error=>{console.error(error);console.error('Runtime errors:',JSON.stringify(errors));if(inspect)try{console.error('Page diagnostics:',await inspect());}catch(diagnostic){console.error('Diagnostics failed:',diagnostic);}process.exitCode=1;}).finally(async()=>{if(ws)ws.close();for(const child of children)child.kill();await pause(200);fs.rmSync(temporary,{recursive:true,force:true});});
