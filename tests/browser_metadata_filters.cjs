// Native browser smoke test. No npm dependencies.
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process');
const root=process.env.TULDOK_SOURCE_ROOT||path.resolve(__dirname,'..'),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-filters-browser-')),children=[];
let ws, inspect;
const errors=[];
const {pageLoadTracker}=require('./browser_page_load.cjs');const pageLoads=pageLoadTracker();
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn){for(let i=0;i<150;i++){const value=await fn();if(value)return value;await pause(100);}throw Error('Timed out');}
function launch(command,args,options={}){const child=spawn(command,args,options);children.push(child);return child;}
(async()=>{
  const server=launch('python3',['-u','tests/browser_metadata_server.py','--port','0','--data',path.join(temporary,'data')],{cwd:root,stdio:['ignore','pipe','pipe']});
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
  const label='vehicle & café',note='Owner note: unverified & café';
  const alpha=await text('Alpha source',label,['source-a','shared'],note);
  const beta=await text('Beta source',label,['source-b'],'unknown','text_entities');
  await text('Label substring','vehicle & cafés',['source-a'],'unknown');
  const saved=await request('selections',{name:'Fixed target set',items:[ref(alpha),ref(beta)]});
  const exactValues=['ordinary note', 'left\nright', 'left\rright', 'left\r\nright', 'literal\\n and "quotes"'];
  const endingRows=[];
  for(let i=0;i<exactValues.length;i++)endingRows.push(await text('Exact ending '+i,exactValues[i],[exactValues[i]],exactValues[i]));
  await send('Page.enable');await send('Runtime.enable');await send('Page.setLifecycleEventsEnabled',{enabled:true});
  await send('Page.navigate',{url:base+'/workbench'});await until(()=>evaluate('document.getElementById("notice")?.textContent === "Collection ready."'));
  const detection=await image('Detection source','red','image_detection',{boxes:[{label,x:0,y:0,width:4,height:4}]},['source-a-extra'],'UNKNOWN');
  await image('Caption source','blue','image_caption',{caption:'A vehicle & café in a caption.'},['caption'],'unknown');
  await evaluate('refresh()');
  const submit=async()=>{await evaluate('document.getElementById("filters").requestSubmit()');await until(()=>evaluate('!document.getElementById("filters").dataset.busy'));};
  const ids=()=>evaluate('page.items.map(r=>r.id).sort()');
  const chosen=()=>evaluate('releaseBody().items');
  // Keyboard Enter submits the exact label criterion, rather than broad source-word matching.
  await fill('label-filter',label);await evaluate('document.getElementById("label-filter").focus()');
  await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,text:'\r'});
  await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});
  await until(()=>evaluate('page.total===3 && !document.getElementById("filters").dataset.busy'));
  assert.deepEqual(await ids(),[alpha.id,beta.id,detection.id].sort());
  await fill('group-filter','source-a');await submit();assert.deepEqual(await ids(),[alpha.id]);
  await fill('rights-filter',note);await fill('kind','text');await fill('task-filter','text_classification');await fill('review-filter','human_reviewed');await fill('sort','name');await submit();
  assert.deepEqual(await ids(),[alpha.id]);assert.equal(await evaluate('page.analysis.labels["vehicle & café"]'),1);
  assert.ok((await evaluate('document.getElementById("records").textContent')).includes('Rights note: '+note));
  await fill('rights-filter',note.toLowerCase());await submit();assert.equal(await evaluate('page.total'),0,'Notes are exact case-sensitive metadata');
  for(const id of ['label-filter','group-filter','rights-filter','kind','task-filter','review-filter'])await fill(id,'');
  await fill('rights-filter','unknown');await submit();
  assert.equal(await evaluate('page.total'),5);assert.equal(await evaluate('page.analysis.unknown_rights'),5);
  assert.ok((await evaluate('document.getElementById("records").textContent')).includes('legacy-missing-note'));
  assert.ok((await evaluate('document.getElementById("records").textContent')).includes('legacy-null-note'));
  assert.equal(await evaluate('page.items.every(r=>r.rights_note==="unknown")'),true);
  assert.equal(await evaluate('page.items.filter(r=>r.name.startsWith("legacy-")).every(r=>r.review==="draft")'),true,'Unknown notes grant no review');
  await fill('rights-filter','UNKNOWN');await submit();assert.deepEqual(await ids(),[detection.id],'Uppercase text is retained as an arbitrary note');
  await fill('rights-filter','');await fill('group-filter','source-a-extra');await submit();assert.deepEqual(await ids(),[detection.id]);
  await fill('group-filter','SOURCE-A-EXTRA');await submit();assert.equal(await evaluate('page.total'),0);
  await fill('group-filter','');
  const unicode=await text('Unicode maximum','😀'.repeat(80),['😀'.repeat(120)],'😀'.repeat(1000));
  const replacement=await text('Literal replacement character','\ufffd',['\ufffd'],'\ufffd');
  await fill('label-filter','😀'.repeat(80));await fill('group-filter','😀'.repeat(120));await fill('rights-filter','😀'.repeat(1000));await submit();
  assert.deepEqual(await ids(),[unicode.id],'All valid Unicode code-point lengths can be filtered');
  // Exact criteria are applied before pagination and full-result analysis.
  for(let i=0;i<41;i++)await text('Page '+String(i).padStart(2,'0'),'paged',['paged-source'],'Unverified fixture note');
  await fill('label-filter','paged');await fill('group-filter','paged-source');await fill('rights-filter','Unverified fixture note');await submit();
  assert.equal(await evaluate('page.total'),41);assert.equal(await evaluate('page.items.length'),40);assert.equal(await evaluate('page.analysis.labels.paged'),41);
  await click('next');await until(()=>evaluate('offset===40 && !document.getElementById("next").dataset.busy'));
  assert.equal(await evaluate('page.items.length'),1);assert.equal(await evaluate('page.total'),41);
  assert.equal(await evaluate('page.items.every(r=>r.rights_note==="Unverified fixture note" && r.groups.includes("paged-source"))'),true);
  await click('previous');await until(()=>evaluate('offset===0 && !document.getElementById("previous").dataset.busy'));
  // Dynamic filtered results can change without changing loaded fixed membership or proof.
  await evaluate('refreshSavedSets('+JSON.stringify(saved.id)+')');await click('load-selection');await until(()=>evaluate('!savedLoadBusy && selected.size===2'));
  const fixedPairs=await chosen();assert.deepEqual(fixedPairs,[ref(alpha),ref(beta)].sort((a,b)=>a.id.localeCompare(b.id)));
  await fill('train',100);await fill('validation',0);await fill('test',0);await click('preview-release');await until(()=>evaluate('!document.getElementById("freeze-release").disabled'));
  const token=await evaluate('releasePreview.preview_token');
  // Real single-line inputs sanitize CR/LF; backend values and exact queries retain them.
  const probe=[];
  for(let i=1;i<=3;i++) {
    const value=exactValues[i];await fill('rights-filter',value);
    const entered=await evaluate('document.getElementById("rights-filter").value');
    assert.equal(entered,'leftright');
    const exact=await request('records?'+new URLSearchParams({label:value,group:value,rights:value}));
    const sanitized=await request('records?'+new URLSearchParams({label:value,group:value,rights:entered}));
    assert.deepEqual(exact.items.map(r=>r.id),[endingRows[i].id]);assert.equal(sanitized.total,0);
    probe.push({stored:[...value].map(c=>c.codePointAt(0)),input:[...entered].map(c=>c.codePointAt(0)),exact:exact.total,sanitized:sanitized.total});
  }
  console.log('Original single-line defect, API positive controls:',JSON.stringify(probe));
  assert.equal(await evaluate('!!document.getElementById("exact-filter-format")'),true,'Lossless criterion entry is available');
  // Capture actual production fetch URLs to assert submitted codepoints, not only visible values.
  await evaluate('window.exactQueries=[];window.originalFetch=window.fetch;window.fetch=(url,options)=>{if(String(url).startsWith("/api/workbench/records?")){const q=new URL(url,location.href).searchParams;exactQueries.push(Object.fromEntries(["label","group","rights"].map(k=>[k,q.get(k)])));}return originalFetch(url,options);}');
  await fill('exact-filter-format','json');
  assert.equal(await evaluate('document.getElementById("rights-filter").value'),JSON.stringify('leftright'),'Format conversion preserves ordinary entry');
  for(let i=0;i<exactValues.length;i++) {
    const value=exactValues[i];
    for(const field of ['label','group','rights'])await fill(field+'-filter',JSON.stringify(value));
    await submit();assert.deepEqual(await ids(),[endingRows[i].id]);
    assert.deepEqual(await evaluate('exactQueries.at(-1)'),{label:value,group:value,rights:value},'Actual submitted values preserve exact codepoints');
    assert.deepEqual(await chosen(),fixedPairs);assert.equal(await evaluate('releasePreview.preview_token'),token);
    const row=await request('records/'+endingRows[i].id);
    assert.equal(row.annotation.label,value);assert.deepEqual(row.groups,[value]);assert.equal(row.provenance.rights,value);
    assert.deepEqual(row,endingRows[i],'Exact filtering never rewrites stored metadata or revisions');
  }
  // The longest legal values also fit when every supplementary codepoint is escaped.
  for(const [field,length] of [['label',80],['group',120],['rights',1000]])
    await fill(field+'-filter','"'+'\\ud83d\\ude00'.repeat(length)+'"');
  await submit();assert.deepEqual(await ids(),[unicode.id]);
  assert.deepEqual(await evaluate('exactQueries.at(-1)'),{label:'😀'.repeat(80),group:'😀'.repeat(120),rights:'😀'.repeat(1000)});
  assert.deepEqual(await chosen(),fixedPairs);assert.equal(await evaluate('releasePreview.preview_token'),token);
  // Valid U+FFFD metadata must never be matched by silently replacing malformed UTF-16.
  for(const field of ['label','group','rights']) {
    for(const key of ['label','group','rights'])await fill(key+'-filter','');
    for(const value of ['\ud800','\udfff','a\ud800b','\ud800\ud800','\udc00\ud800']) {
      const beforeQueries=await evaluate('exactQueries.length');
      await fill(field+'-filter',JSON.stringify(value));await submit();
      const submitted=await evaluate('exactQueries.slice('+beforeQueries+')');
      console.log('Surrogate entry:',JSON.stringify({field,codeUnits:Array.from({length:value.length},(_,i)=>value.charCodeAt(i)),submitted,total:await evaluate('page.total')}));
      assert.equal(submitted.length,0,'Reject unpaired surrogate before URL encoding; no replacement-character alias query');
      assert.ok((await evaluate('document.getElementById("notice").textContent')).includes('unpaired surrogate'));
      assert.deepEqual(await chosen(),fixedPairs);assert.equal(await evaluate('releasePreview.preview_token'),token);
    }
  }
  for(const field of ['label','group','rights'])await fill(field+'-filter',JSON.stringify('\ufffd'));
  await submit();assert.deepEqual(await ids(),[replacement.id],'A deliberately entered replacement character remains valid');
  for(const field of ['label','group','rights'])await fill(field+'-filter','');
  await fill('exact-filter-format','text');
  for(const field of ['label','group','rights']) {
    for(const key of ['label','group','rights'])await fill(key+'-filter','');
    const beforeQueries=await evaluate('exactQueries.length');await fill(field+'-filter','\ud800');await submit();
    assert.equal(await evaluate('exactQueries.length'),beforeQueries,'Plain lone surrogates are also rejected');
  }
  for(const field of ['label','group','rights'])await fill(field+'-filter','');
  await fill('exact-filter-format','json');
  // A switch to plain entry cannot silently drop internal CR/LF.
  for(const field of ['label','group','rights'])await fill(field+'-filter',JSON.stringify(exactValues[3]));
  await fill('exact-filter-format','text');
  assert.equal(await evaluate('document.getElementById("exact-filter-format").value'),'json');
  assert.equal(await evaluate('document.getElementById("rights-filter").value'),JSON.stringify(exactValues[3]));
  assert.ok((await evaluate('document.getElementById("notice").textContent')).includes('line breaks'));
  const queryCount=await evaluate('exactQueries.length');
  await fill('rights-filter','null');await submit();
  assert.equal(await evaluate('exactQueries.length'),queryCount,'Non-string JSON never reaches the API');
  assert.ok((await evaluate('document.getElementById("notice").textContent')).includes('JSON string'));
  assert.deepEqual(await chosen(),fixedPairs);assert.equal(await evaluate('releasePreview.preview_token'),token);
  for(const [field,value] of [['label','paged'],['group','paged-source'],['rights','Unverified fixture note']])await fill(field+'-filter',JSON.stringify(value));
  await fill('exact-filter-format','text');
  assert.equal(await evaluate('document.getElementById("rights-filter").value'),'Unverified fixture note');
  assert.equal(await evaluate('document.getElementById("exact-filter-format").value'),'text');
  await text('Page 41','paged',['paged-source'],'Unverified fixture note');await submit();
  assert.equal(await evaluate('page.total'),42);assert.deepEqual(await chosen(),fixedPairs);
  assert.equal(await evaluate('releasePreview.preview_token'),token,'Unrelated filter-result changes cannot replace exact proof');
  assert.equal(await evaluate('document.getElementById("freeze-release").disabled'),false);
  assert.deepEqual((await request('selections/'+saved.id)).selection.items,saved.items);
  const before=await request('records/'+alpha.id);assert.equal(before.review,'human_reviewed');
  // Invalid criteria show an API error and recover without changing selected pairs.
  await fill('label-filter','x'.repeat(81));await submit();
  assert.ok((await evaluate('document.getElementById("notice").textContent')).includes('Label filter'));
  assert.deepEqual(await chosen(),fixedPairs);
  await fill('label-filter','paged');await submit();assert.equal(await evaluate('page.total'),42);
  await evaluate('document.getElementById("release-form").requestSubmit()');await until(()=>evaluate('!!document.querySelector("#release-result a")'));
  const zip=await fetch(await evaluate('document.querySelector("#release-result a").href'));assert.equal(zip.status,200);assert.ok((await zip.arrayBuffer()).byteLength>1000);
  const reports=path.join(__dirname,'../docs/plans/explicit-metadata-filters/reports');fs.mkdirSync(reports,{recursive:true});
  await evaluate('document.getElementById("filters").scrollIntoView()');const desktop=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});fs.writeFileSync(path.join(reports,'filters-desktop.png'),Buffer.from(desktop.data,'base64'));
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:false});
  await evaluate('document.getElementById("filters").scrollIntoView()');const narrow=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});fs.writeFileSync(path.join(reports,'filters-narrow.png'),Buffer.from(narrow.data,'base64'));
  assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'),'Exact filter controls and metadata do not overflow at 390px');
  assert.deepEqual(await request('records/'+alpha.id),before,'Filtering never changes target/review metadata');
  assert.deepEqual(errors,[]);
  console.log('Exact label/group/rights filters, lossless LF/CR/CRLF JSON entry and submitted codepoints, unknown retained notes, keyboard search, combined criteria, pagination, dynamic results/fixed pairs, preview/export, error recovery and narrow layout passed.');
})().catch(async error=>{console.error(error);console.error('Runtime errors:',JSON.stringify(errors));if(inspect)try{console.error('Page diagnostics:',await inspect());}catch(diagnostic){console.error('Diagnostics failed:',diagnostic);}process.exitCode=1;}).finally(async()=>{if(ws)ws.close();for(const child of children)child.kill();await pause(200);fs.rmSync(temporary,{recursive:true,force:true});});
