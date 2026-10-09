'use strict';
// QA-only replay against unmodified production sources and isolated local databases.
const assert=require('node:assert/strict'), fs=require('node:fs'), path=require('node:path'), os=require('node:os');
const {spawn,spawnSync}=require('node:child_process'), crypto=require('node:crypto');
const report=__dirname, root=path.resolve(report,'../../..'), legacy=process.env.TULDOK_LEGACY_ROOT||'/workspace/Tuldok';
const temp=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-ui-walkthrough-')), children=[], errors=[], requests=[];
const session={candidate:{},legacy:{},fixtures:{},screenshots:[],steps:[],runtime:{temporary:temp}};
const source='e33144a389e611dfb9e95a83f248e7bf87d7a3aa';
const pause=ms=>new Promise(r=>setTimeout(r,ms)), hash=b=>crypto.createHash('sha256').update(b).digest('hex');
let ws,evaluate,send;
function git(cwd,arg){const r=spawnSync('git',['rev-parse',arg],{cwd,encoding:'utf8'});assert.equal(r.status,0,r.stderr);return r.stdout.trim();}
async function until(fn,label='state'){for(let i=0;i<200;i++){if(await fn())return;await pause(100);}throw Error('Timed out: '+label);}
function launch(cmd,args,options){const c=spawn(cmd,args,options);children.push(c);return c;}
async function app(cwd,name){let output='';const c=launch('python3',['-u','app.py','--port','0','--data',path.join(temp,name)],{cwd,stdio:['ignore','pipe','pipe']});c.stdout.on('data',b=>output+=b);c.stderr.on('data',b=>fs.appendFileSync(path.join(temp,name+'-server.log'),b));await until(()=>output.match(/127\.0\.0\.1:(\d+)/),'server '+name);return 'http://127.0.0.1:'+output.match(/127\.0\.0\.1:(\d+)/)[1];}
async function api(base,route){const response=await fetch(base+route);assert.ok(response.ok,route);return response.json();}
async function shot(name,selector=null,narrow=false){
  await send('Emulation.setDeviceMetricsOverride',{width:narrow?390:1400,height:narrow?844:1000,deviceScaleFactor:1,mobile:false});
  await pause(150);
  await evaluate(selector?'document.querySelector('+JSON.stringify(selector)+').scrollIntoView({block:"start"})':'window.scrollTo(0,0)');
  await pause(100);
  const layout=await evaluate('({width:innerWidth,height:innerHeight,scrollWidth:document.documentElement.scrollWidth,scrollY,recordsY:document.getElementById("records")?.getBoundingClientRect().top+scrollY,editorY:document.querySelector(".editor")?.getBoundingClientRect().top+scrollY})');
  assert.ok(layout.scrollWidth<=layout.width,'Horizontal overflow: '+name);
  // Use ordinary viewport captures. Offscreen CDP clips can move form content
  // during capture, so the report retains the actual surrounding page and scroll.
  const image=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false}),file=name+(narrow?'-narrow':'-desktop')+'.png',output=path.join(report,'screenshots',file);fs.writeFileSync(output,Buffer.from(image.data,'base64'));
  session.screenshots.push({file,selector,viewport:{width:layout.width,height:layout.height},layout,method:'native viewport capture',sha256:hash(fs.readFileSync(output))});
}
async function both(name,selector=null){await shot(name,selector);await shot(name,selector,true);await send('Emulation.setDeviceMetricsOverride',{width:1400,height:1000,deviceScaleFactor:1,mobile:false});}
async function fill(id,value){await evaluate('(()=>{const e=document.getElementById('+JSON.stringify(id)+');e.value='+JSON.stringify(value)+';e.dispatchEvent(new Event("input",{bubbles:true}));e.dispatchEvent(new Event("change",{bubbles:true}));})()');}
async function click(id){await evaluate('document.getElementById('+JSON.stringify(id)+').click()');}
async function submit(id){await evaluate('document.getElementById('+JSON.stringify(id)+').requestSubmit()');await until(()=>evaluate('!document.getElementById('+JSON.stringify(id)+').dataset.busy'),id);}
async function inputFile(id,files){const {root:dom}=await send('DOM.getDocument');const {nodeId}=await send('DOM.querySelector',{nodeId:dom.nodeId,selector:'#'+id});await send('DOM.setFileInputFiles',{nodeId,files});}
async function record(id){await evaluate('openRecord('+JSON.stringify(id)+')');}
async function preview(){await click('preview-release');await until(()=>evaluate('!releaseBusy && !!releasePreview'),'preview');return evaluate('releasePreview');}
(async()=>{
  const audit=spawnSync('git',['diff','--quiet',source,'--','.',':(exclude)docs/plans/workbench-ui-qualification'],{cwd:root,encoding:'utf8'});assert.equal(audit.status,0,'Production sources must match reviewed candidate');
  session.qa={head:git(root,'HEAD'),root};session.candidate={head:source,tree:git(root,source+'^{tree}'),root};session.legacy={head:git(legacy,'HEAD'),tree:git(legacy,'HEAD^{tree}'),root:legacy};
  assert.equal(session.legacy.head,'2fc4a46f12d73a0fa467d5482f68edb83d6df6af');
  for(const filename of ['blue-book-qa.png','assets.jsonl']){const b=fs.readFileSync(path.join(report,'fixtures',filename));session.fixtures[filename]={bytes:b.length,sha256:hash(b)};}
  const candidate=await app(root,'candidate-data'), frozen=await app(legacy,'legacy-data');session.runtime.candidate=candidate;session.runtime.legacy=frozen;
  launch(process.env.BROWSER||'/usr/bin/chromium',['--headless','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--window-size=1400,1000','--user-data-dir='+path.join(temp,'browser'),'about:blank'],{stdio:['ignore','ignore','pipe'],env:{...process.env,XDG_CONFIG_HOME:temp,XDG_CACHE_HOME:temp}});
  const active=path.join(temp,'browser','DevToolsActivePort');await until(()=>fs.existsSync(active),'CDP');const port=fs.readFileSync(active,'utf8').split('\n')[0];
  const tabs=await(await fetch('http://127.0.0.1:'+port+'/json')).json(),tab=tabs.find(t=>t.type==='page');ws=new WebSocket(tab.webSocketDebuggerUrl);await new Promise((r,j)=>{ws.onopen=r;ws.onerror=j;});
  let id=0;const pending=new Map();ws.onmessage=e=>{const m=JSON.parse(e.data);if(m.id){const p=pending.get(m.id);pending.delete(m.id);if(p)m.error?p.reject(m.error):p.resolve(m.result);}if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails);if(m.method==='Network.requestWillBeSent')requests.push(m.params.request.url);};
  send=(method,params={})=>new Promise((resolve,reject)=>{const request=++id,timer=setTimeout(()=>{pending.delete(request);reject(Error('CDP timeout '+method));},20000);pending.set(request,{resolve:v=>{clearTimeout(timer);resolve(v);},reject:e=>{clearTimeout(timer);reject(e);}});ws.send(JSON.stringify({id:request,method,params}));});
  evaluate=async expression=>{const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(r.exceptionDetails)throw Error(JSON.stringify(r.exceptionDetails));return r.result.value;};
  await send('Page.enable');await send('Runtime.enable');await send('Network.enable');session.browser=await send('Browser.getVersion');
  await send('Page.navigate',{url:candidate+'/workbench'});await until(()=>evaluate('document.getElementById("notice")?.textContent==="Collection ready."'),'workbench ready');
  await inputFile('bulk-manifest',[path.join(report,'fixtures/assets.jsonl')]);await inputFile('bulk-images',[path.join(report,'fixtures/blue-book-qa.png')]);await submit('bulk-form');await until(()=>evaluate('document.getElementById("bulk-status").textContent.startsWith("Complete:") && page.total===3'),'bulk complete');
  const raw=(await api(candidate,'/api/workbench/records')).items;assert.equal(raw.length,3);assert.ok(raw.every(r=>r.review==='draft'&&r.annotation===null));const image=raw.find(r=>r.kind==='image'),note=raw.find(r=>r.name==='Source note');
  session.steps.push({stage:'raw-import',status:await evaluate('document.getElementById("bulk-status").textContent'),records:raw});console.log('PASS raw import: three drafts, one forged-review row rejected');
  await both('01-import-overview');await both('01-import-panel','#bulk-panel');
  await record(image.id);await fill('task','image_classification');await fill('label','blue-book');await submit('editor');assert.equal((await api(candidate,'/api/workbench/records/'+image.id)).review,'draft');await both('02-annotation-draft','.editor');
  await fill('record-review','human_reviewed');await submit('editor');await both('03-reviewed-image','.editor');await both('03-review-controls','#record-review');
  await record(note.id);await fill('label','source-note');await fill('record-review','human_reviewed');await submit('editor');
  await fill('rights-filter','unknown');await submit('filters');assert.equal(await evaluate('page.total'),2);assert.equal(await evaluate('page.items.filter(r=>r.review==="draft").length'),1);
  session.steps.push({stage:'unknown-rights-filter',items:await evaluate('page.items'),selected:await evaluate('releaseBody().items')});await both('04-unknown-rights','.collection');console.log('PASS unknown-rights exact filter: two records, one still draft');
  await fill('rights-filter','');await fill('review-filter','human_reviewed');await submit('filters');assert.equal(await evaluate('page.total'),2);await click('select-page');await fill('selection-name','Book + note — fixed');await submit('save-selection-form');
  const summary=(await api(candidate,'/api/workbench/selections')).selections[0],saved=(await api(candidate,'/api/workbench/selections/'+summary.id)).selection;
  await click('clear-selection');await fill('saved-selection',saved.id);await click('load-selection');await until(()=>evaluate('!savedLoadBusy && selected.size===2'),'fixed open');const fixed=await evaluate('releaseBody().items');assert.deepEqual(fixed,saved.items.map(({id,revision,source_revision})=>({id,revision,source_revision})));
  session.steps.push({stage:'fixed-open',selection:saved,pairs:fixed});await both('05-fixed-set','#saved-selection-panel');
  await fill('review-filter','');await fill('rights-filter','unknown');await submit('filters');assert.equal(await evaluate('page.total'),2);assert.deepEqual(await evaluate('releaseBody().items'),fixed);
  await send('Page.navigate',{url:candidate+'/workbench#selection='+saved.id});await until(()=>evaluate('typeof savedLoadBusy!=="undefined" && !savedLoadBusy && selected.size===2'),'navigation fixed reopen');assert.deepEqual(await evaluate('releaseBody().items'),fixed);
  await record(note.id);await fill('label','source-note-updated');await fill('record-review','human_reviewed');await submit('editor');await click('load-selection');await until(()=>evaluate('!savedLoadBusy'),'stale fixed open');assert.deepEqual(await evaluate('releaseBody().items'),fixed);
  await fill('train','100');await fill('validation','0');await fill('test','0');const stale=await preview();assert.equal(stale.eligible,false);assert.equal(await evaluate('document.getElementById("freeze-release").disabled'),true);
  const resolution=await api(candidate,'/api/workbench/selections/'+saved.id);assert.equal(resolution.members.find(m=>m.item.id===note.id).status,'stale');session.steps.push({stage:'stale-open',resolution,preview:stale});await both('06-stale-fixed-set','#saved-selection-panel');await both('06-stale-release','#release-form');console.log('PASS fixed reopen/navigation/filter isolation and stale release blocking');
  await fill('rights-filter','');await fill('review-filter','human_reviewed');await submit('filters');assert.equal(await evaluate('page.total'),2);await click('clear-selection');await click('select-page');const current=await evaluate('releaseBody().items');assert.equal(current.length,2);assert.notDeepEqual(current,fixed);const eligible=await preview();assert.equal(eligible.eligible,true);await both('07-eligible-preview','#release-form');
  await evaluate('document.getElementById("release-form").requestSubmit()');await until(()=>evaluate('!releaseBusy && !!document.querySelector("#release-result a")'),'release freeze');const link=await evaluate('document.querySelector("#release-result a").href'),response=await fetch(link);assert.equal(response.status,200);const zip=Buffer.from(await response.arrayBuffer());fs.writeFileSync(path.join(report,'fixtures/candidate-release.zip'),zip);
  const extracted=spawnSync('python3',['-c','import json,zipfile,sys; z=zipfile.ZipFile(sys.argv[1]); print(json.dumps(json.loads(z.read("manifest.json"))))',path.join(report,'fixtures/candidate-release.zip')],{encoding:'utf8'});assert.equal(extracted.status,0,extracted.stderr);const manifest=JSON.parse(extracted.stdout);
  assert.deepEqual(manifest.records.map(({id,revision,source_revision})=>({id,revision,source_revision})),current);assert.ok(manifest.records.every(r=>r.review==='human_reviewed'));assert.equal(manifest.records.length,2);
  session.steps.push({stage:'current-explicit-release',pairs:current,preview:eligible,url:link,manifest,zip:{bytes:zip.length,sha256:hash(zip)}});await both('08-frozen-release','#release-form');await both('08-download','#release-result');await both('08-final-overview');console.log('PASS explicit current selection, preview, frozen ZIP and exact manifest pairs');
  await send('Page.navigate',{url:frozen+'/'});await until(()=>evaluate('document.getElementById("counts")?.textContent.includes("0")'),'legacy ready');await fill('capture-book','local-blue-book');await fill('capture-session','qa-session');await inputFile('import',[path.join(report,'fixtures/blue-book-qa.png')]);await evaluate('document.getElementById("import").dispatchEvent(new Event("change",{bubbles:true}))');
  await until(()=>evaluate('document.getElementById("view-title").textContent==="blue-book-qa.png" && document.getElementById("source").complete && !document.getElementById("save").disabled'),'legacy image');
  await both('09-legacy-import');await send('Emulation.setDeviceMetricsOverride',{width:1400,height:1000,deviceScaleFactor:1,mobile:false});await pause(200);
  for(const [i,xy] of [[.25,.2],[.75,.2],[.75,5/6],[.25,5/6]].entries()){
    await evaluate('document.querySelectorAll("#corners button")['+i+'].click()');const p=await evaluate('(()=>{const r=document.getElementById("overlay").getBoundingClientRect();return {x:r.left+r.width*'+xy[0]+',y:r.top+r.height*'+xy[1]+'};})()');
    await send('Input.dispatchMouseEvent',{type:'mousePressed',...p,button:'left',clickCount:1});await send('Input.dispatchMouseEvent',{type:'mouseReleased',...p,button:'left',clickCount:1});
  }
  await fill('split','train');await click('save');await until(()=>evaluate('document.getElementById("save-status").textContent==="Saved" && !document.getElementById("save").disabled'),'legacy save');const samples=await api(frozen,'/api/samples');assert.equal(samples.length,1);assert.ok(samples[0].annotation.corners.every(c=>Number.isFinite(c.x)&&Number.isFinite(c.y)));
  const oldzip=await fetch(frozen+'/api/export');assert.equal(oldzip.status,200);const oldbytes=Buffer.from(await oldzip.arrayBuffer());fs.writeFileSync(path.join(report,'fixtures/legacy-labeled.zip'),oldbytes);
  session.steps.push({stage:'legacy-corners-export',samples,zip:{bytes:oldbytes.length,sha256:hash(oldbytes)}});await both('10-legacy-labeled');await both('10-legacy-inspector','.inspector');console.log('PASS retained legacy import, four manual corners, labeled ZIP');
  assert.deepEqual(errors,[]);assert.ok(requests.every(url=>new URL(url).hostname==='127.0.0.1'),'Unexpected external browser request');session.requests=[...new Set(requests)];session.errors=errors;session.result='PASS';session.completed=new Date().toISOString();
})().catch(async e=>{console.error(e);session.result='FAIL';session.error=String(e);if(evaluate)try{console.error(await evaluate('document.body.innerText.slice(0,3000)'));}catch{}process.exitCode=1;}).finally(async()=>{session.errors=errors;fs.writeFileSync(path.join(report,'session.json'),JSON.stringify(session,null,2)+'\n');if(ws)ws.close();for(const c of children)c.kill();await pause(200);console.log('Isolated fixture databases retained:',temp);});
