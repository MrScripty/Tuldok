'use strict';
const fixtureAuth = require('./auth_helpers.cjs').authenticatedFixture();
const fetch = fixtureAuth.fetch;
// Authored PCM WAV through the real Data UI, PostgreSQL metadata and frozen export.
'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn,execFileSync}=require('node:child_process');
const {qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const {waitForDebugger}=require('./browser_startup.cjs');
const {pageLoadTracker}=require('./browser_page_load.cjs');
const root=path.resolve(__dirname,'..'),report=qaDirectory(root,'workspace-audio'),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-audio-'));
const children=[],errors=[],checks=[],captures=[],tracker=pageLoadTracker();let ws,evaluate,serverErrors='';
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn,message='Timed out'){for(let i=0;i<300;i++){const value=await fn();if(value)return value;await pause(100);}throw Error(message);}
function launch(command,args,options){const child=spawn(command,args,options);children.push(child);return child;}
(async()=>{
  const fixture=path.join(root,'tests/fixtures/workspaces/audio/stereo-impulses.wav');
  const server=launch('python3',['-u','app.py','--port','0','--data',path.join(temporary,'data')],{cwd:root,stdio:['ignore','pipe','pipe']});
  let output='';server.stdout.on('data',chunk=>output+=chunk);server.stderr.on('data',chunk=>serverErrors+=chunk);
  const port=await until(()=>output.match(/127\.0\.0\.1:(\d+)/)?.[1]),base='http://127.0.0.1:'+port;
  await fixtureAuth.register('http://127.0.0.1:'+port,path.join(temporary,'data'),root);
  const api=async(route,body)=>{const response=await fetch(base+'/api/workbench/'+route,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const value=await response.json();assert.ok(response.ok,JSON.stringify(value));return value;};
  const browser=launch(process.env.BROWSER||'/usr/bin/chromium',[...(process.env.TULDOK_NATIVE_ZOOM?[]:['--headless']),'--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--autoplay-policy=no-user-gesture-required','--remote-debugging-port=0','--window-size=1440,1000','--user-data-dir='+path.join(temporary,'browser'),'about:blank'],{stdio:['ignore','ignore','ignore'],env:{...process.env,XDG_CONFIG_HOME:temporary,XDG_CACHE_HOME:temporary}});
  const debugPort=await waitForDebugger(browser,path.join(temporary,'browser','DevToolsActivePort'));
  const target=(await(await fetch('http://127.0.0.1:'+debugPort+'/json')).json()).find(tab=>tab.type==='page'&&tab.url==='about:blank');
  ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  let id=0;const pending=new Map();
  const send=(method,params={})=>new Promise((resolve,reject)=>{const key=++id,timer=setTimeout(()=>{pending.delete(key);reject(Error('CDP timeout '+method));},20000);pending.set(key,{resolve:value=>{clearTimeout(timer);resolve(value);},reject:error=>{clearTimeout(timer);reject(error);}});ws.send(JSON.stringify({id:key,method,params}));});
  ws.onmessage=event=>{const m=JSON.parse(event.data);tracker.observe(m);if(m.id){const p=pending.get(m.id);if(p){pending.delete(m.id);m.error?p.reject(m.error):p.resolve(m.result);}}if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails);if(m.method==='Page.javascriptDialogOpening')send('Page.handleJavaScriptDialog',{accept:true}).catch(error=>errors.push(String(error)));};
  evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true,userGesture:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  const frame=expression=>evaluate(`document.getElementById('catalog-frame').contentWindow.eval(${JSON.stringify(expression)})`);
  const fill=(id,value)=>frame(`(()=>{const el=document.getElementById(${JSON.stringify(id)});el.value=${JSON.stringify(value)};el.dispatchEvent(new Event('input',{bubbles:true}));el.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  const key=async(value,code=value)=>{const common={key:value,code,windowsVirtualKeyCode:value==='Enter'?13:value==='Tab'?9:0};await send('Input.dispatchKeyEvent',{type:'keyDown',...common,...(value==='Enter'?{text:'\r',unmodifiedText:'\r'}:{})});await send('Input.dispatchKeyEvent',{type:'keyUp',...common});};
  const click=id=>frame(`document.getElementById(${JSON.stringify(id)}).click()`);
  // Collection data can finish before the later workspace adapter attaches its controls.
  const toolsReady=()=>evaluate(`(()=>{
    const host=document.getElementById('catalog-frame'),doc=host?.contentDocument;
    const button=doc?.querySelector('.embed-toolbar button'),drawer=doc?.getElementById('embed-tools');
    return Boolean(!document.getElementById('catalog-data')?.hidden && doc?.readyState==='complete' &&
      button?.isConnected && !button.disabled && button.getClientRects().length && drawer?.isConnected &&
      typeof host?.contentWindow?.TuldokWorkspaceData?.snapshot==='function');
  })()`);
  const tools=async()=>{await until(toolsReady,'Embedded catalog tools did not become ready');await frame('document.querySelector(".embed-toolbar button").click()');await until(()=>frame('document.getElementById("embed-tools").open'));};
  const closeTools=()=>frame('document.querySelector("#embed-tools>button").click()');
  async function capture(name,width,height){await send('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});await frame('document.getElementById("audio-inspection").scrollIntoView({block:"start"})');await evaluate('new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))');assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth'),'workspace fits viewport');assert.ok(await frame('document.documentElement.scrollWidth<=innerWidth'),'audio editor fits viewport');const filename=name+'.jpg';fs.writeFileSync(path.join(report,filename),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));captures.push(filename);}
  await send('Page.enable');await send('Runtime.enable');await send('Page.setLifecycleEventsEnabled',{enabled:true});
  await fixtureAuth.browser(send,'http://127.0.0.1:'+port);
  await send('Page.navigate',{url:base+'/workspaces'});await until(()=>evaluate('!!document.getElementById("fixture-label")'));
  await evaluate('document.getElementById("dataset").value="catalog";document.getElementById("dataset").dispatchEvent(new Event("change",{bubbles:true}))');
  await until(()=>evaluate('document.getElementById("catalog-frame")?.contentDocument?.getElementById("notice")?.textContent==="Collection ready."'));
  assert.match(await frame('document.getElementById("empty-editor").textContent'),/Open a record/);checks.push('Empty real catalog renders honestly');
  await tools();await frame('document.getElementById("audio-import-panel").open=true');
  const object=await send('Runtime.evaluate',{expression:'document.getElementById("catalog-frame").contentDocument.getElementById("audio-file")'});
  await send('DOM.setFileInputFiles',{files:[fixture],objectId:object.result.objectId});await fill('audio-group','authored-session');await fill('audio-rights','Authored mathematical fixture');
  await frame(`(()=>{const original=fetch;window.audioPosts=0;window.holdAudio=true;window.fetch=async(...args)=>{if(String(args[0]).endsWith('/audio-import')){window.audioPosts++;const response=await original(...args);if(window.holdAudio){window.holdAudio=false;await new Promise(resolve=>window.releaseAudio=resolve);}return response;}return original(...args);};})()`);
  await frame('document.getElementById("audio-import-form").requestSubmit()');await until(()=>frame('!!window.releaseAudio'));
  assert.match(await frame('document.getElementById("audio-import-status").textContent'),/Reading and validating/);
  await frame('document.getElementById("audio-import-form").requestSubmit()');assert.equal(await frame('audioPosts'),1);
  await frame('releaseAudio()');await until(()=>frame('!document.getElementById("audio-import-form").dataset.busy'));
  assert.match(await frame('document.getElementById("audio-import-status").textContent'),/Imported.*unreviewed/);
  const row=(await api('records?kind=audio')).items[0];assert.equal(row.review,'draft');checks.push('Real file input imports once despite repeated submit and lost-ack delay');
  // Identical repeated import is a domain conflict with no duplicate record.
  await frame('document.getElementById("audio-import-form").requestSubmit()');await until(()=>frame('!document.getElementById("audio-import-form").dataset.busy'));
  assert.match(await frame('document.getElementById("audio-import-status").textContent'),/already exists/);assert.equal((await api('records?kind=audio')).total,1);await closeTools();
  await frame('document.querySelector(".record button").click()');await until(()=>frame('!!audioInspection && document.getElementById("audio-player").readyState>=1'));
  assert.equal(await frame('document.getElementById("audio-player").duration'),2);assert.equal(await frame('document.getElementById("audio-segments").children.length'),0);
  const decoded=await frame(`(async()=>{const context=new OfflineAudioContext(2,16000,8000),response=await fetch('/api/workbench/asset/'+current.id),buffer=await context.decodeAudioData(await response.arrayBuffer());return {rate:buffer.sampleRate,frames:buffer.length,channels:buffer.numberOfChannels,samples:[buffer.getChannelData(0)[0],buffer.getChannelData(1)[4000],buffer.getChannelData(0)[8000],buffer.getChannelData(1)[15999]]};})()`);
  assert.deepEqual([decoded.rate,decoded.frames,decoded.channels],[8000,16000,2]);
  // Browser float PCM normalization may divide positive samples by 32767. One source LSB bounds it.
  for(const [index,expected] of [0.5,0.75,-0.5,-0.25].entries()) assert.ok(Math.abs(decoded.samples[index]-expected)<1/32767,'authored PCM impulse amplitude within one source LSB');checks.push('Browser independently decodes exact stereo source samples and duration');
  await capture('audio-data-first-1440',1440,1000);
  await fill('audio-start',4000);await fill('audio-end',8001);await fill('audio-channel',1);
  await frame('document.getElementById("audio-transcript").focus()');await send('Input.insertText',{text:'Human-annotated impulse'});
  await fill('audio-label','impulse');await fill('audio-speaker','authored-channel');
  // Keyboard reaches adjacent action and commits interval fields.
  await frame('document.getElementById("audio-add").focus()');await key('Enter');await until(()=>frame('audioSegments.length===1&&!audioPending'));
  await fill('audio-start',4000);await fill('audio-end',8001);await fill('audio-channel',1);
  await click('audio-play-interval');await until(()=>frame('!!audioSource'));assert.equal(await frame('audioSource.buffer.length'),4001);assert.ok(Math.abs(await frame('audioSource.buffer.getChannelData(0)[0]')-0.75)<1/32767);
  await click('audio-stop');assert.equal(await frame('audioSource'),null);await click('audio-clear-fields');checks.push('Keyboard creates source-frame transcript; chosen channel playback has exactly 4001 frames');
  await fill('record-review','human_reviewed');await frame('document.querySelector("#editor button:not([type=button])").focus()');await key('Enter');
  await until(()=>frame('current.revision===2&&current.review==="human_reviewed"&&!dirty&&!document.getElementById("editor").dataset.busy'));
  const saved=await api('records/'+row.id);assert.equal(saved.annotation.segments[0].end_frame,8001);assert.equal(saved.annotation.segments[0].channel,1);checks.push('Keyboard explicit human review persists exact typed interval and history');
  await frame('document.querySelector(".record input").click()');await tools();await frame('document.getElementById("release-form").closest("details").open=true');await fill('train',100);await fill('validation',0);await fill('test',0);
  await click('preview-release');await until(()=>frame('!document.getElementById("freeze-release").disabled'));
  assert.match(await frame('document.getElementById("release-preview").textContent'),/PCM WAV originals/);
  await frame('document.getElementById("release-form").requestSubmit()');await until(()=>frame('!!document.querySelector("#release-result a")'));
  const releaseURL=await frame('document.querySelector("#release-result a").href'),archive=path.join(report,'audio-release.zip');fs.writeFileSync(archive,Buffer.from(await(await fetch(releaseURL)).arrayBuffer()));
  const inspected=JSON.parse(execFileSync('python3',['-c',`import hashlib,json,sys,zipfile; z=zipfile.ZipFile(sys.argv[1]); m=json.loads(z.read('manifest.json')); r=m['records'][0]; print(json.dumps({'record':r,'sha256':hashlib.sha256(z.read(r['asset'])).hexdigest(),'jsonl':json.loads(z.read('train/records.jsonl'))}))`,archive],{encoding:'utf8'}));
  assert.equal(inspected.sha256,row.content_hash);assert.deepEqual(inspected.record,inspected.jsonl);assert.equal(inspected.record.audio_target_schema_version,1);checks.push('Frozen release contains byte-identical WAV and reviewed JSONL with exact provenance');await closeTools();
  // Fresh server revision makes the visible editor stale, never a silent overwrite.
  await api('records/'+row.id,{revision:2,source_revision:1,task:'audio_timed',annotation:saved.annotation,groups:saved.groups,review:'human_reviewed'});
  await frame('document.getElementById("editor").requestSubmit()');await until(()=>frame('!document.getElementById("editor").dataset.busy'));assert.match(await frame('document.getElementById("notice").textContent'),/changed.*Reload/);
  await click('reload');await until(()=>frame('current.revision===3&&!!audioInspection'));checks.push('Stale edit is refused; explicit reload restores current revision');
  await frame('document.getElementById("filters").requestSubmit()');await until(()=>frame('!document.getElementById("filters").dataset.busy'));
  await click('clear-selection');await click('select-page');await until(()=>frame('selected.get(current.id)?.revision===3'));
  await capture('audio-reviewed-1440',1440,1000);await capture('audio-reviewed-390',390,844);
  // Reload through the workspace restores the catalog record, then proves timing survived.
  const previous=(await send('Page.getFrameTree')).frameTree.frame;
  await send('Page.reload');await until(()=>tracker.reloaded(previous),'fresh main document did not reload');await until(()=>evaluate('document.getElementById("catalog-frame")?.contentDocument?.getElementById("audio-inspection")?.hidden===false'));
  await until(()=>frame('!!audioInspection'));assert.equal(await frame('current.annotation.segments[0].transcript'),'Human-annotated impulse');assert.equal(await frame('current.review'),'human_reviewed');checks.push('Workspace reload retains durable reviewed record and exact timing');
  const textRecord=await api('import',{kind:'text',text:'Existing text editor remains available after invalid audio input.',name:'Text regression',groups:['text-independent'],rights:'Authored'});
  await fill('audio-end',16001);await frame('openRecord('+JSON.stringify(textRecord.id)+')');await until(()=>frame('current?.id==='+JSON.stringify(textRecord.id)));
  assert.equal(await frame('document.getElementById("audio-inspection").hidden'),true);assert.equal(await frame('document.getElementById("editor").checkValidity()'),true);
  await fill('label','retained text class');await frame('document.getElementById("editor").requestSubmit()');await until(()=>frame('current.revision===2&&!document.getElementById("editor").dataset.busy'));
  assert.equal(await frame('document.getElementById("editor").checkValidity()'),true);assert.equal((await api('records/'+textRecord.id)).annotation.label,'retained text class');checks.push('Discarding out-of-range audio input does not block existing text save, including after form re-enable');
  await frame('openRecord('+JSON.stringify(row.id)+')');await until(()=>frame('!!audioInspection'));
  await frame(`(()=>{const original=fetch;window.holdPlayback=true;window.fetch=async(...args)=>{if(window.holdPlayback&&String(args[0]).includes('/asset/')){window.holdPlayback=false;const response=await original(...args);await new Promise(resolve=>window.releasePlayback=resolve);return response;}return original(...args);};})()`);
  await click('audio-play-interval');await until(()=>frame('!!window.releasePlayback'));await click('audio-stop');await frame('releasePlayback()');await until(()=>frame('!document.getElementById("audio-play-interval").dataset.busy'));
  assert.equal(await frame('audioSource'),null);checks.push('Pause during delayed interval preparation cannot resume playback');
  await frame(`(()=>{const original=fetch;window.failPlayback=true;window.fetch=(...args)=>{if(window.failPlayback&&String(args[0]).includes('/asset/')){window.failPlayback=false;return new Promise((resolve,reject)=>window.rejectPlayback=()=>reject(Error('authored late source failure')));}return original(...args);};})()`);
  await click('audio-play-interval');await until(()=>frame('!!window.rejectPlayback'));
  await frame('openRecord('+JSON.stringify(textRecord.id)+')');await until(()=>frame('current?.id==='+JSON.stringify(textRecord.id)));
  const noticeBefore=await frame('document.getElementById("notice").textContent');await frame('rejectPlayback()');await until(()=>frame('!document.getElementById("audio-play-interval").dataset.busy'));
  assert.equal(await frame('document.getElementById("notice").textContent'),noticeBefore);checks.push('Failed late audio request cannot overwrite a newer editor notice');
  await frame('openRecord('+JSON.stringify(row.id)+')');await until(()=>frame('!!audioInspection'));
  const capability=await evaluate('WorkspaceService.capabilities.audio');
  assert.equal(capability.state,'available');
  assert.match(capability.reason,/Bounded PCM16 WAV import, playback, timed human review and frozen export/);
  assert.match(capability.reason,/One reviewed labelled interval per record supports a real local CPU feature\/logistic classifier with frozen source-frame results/);
  assert.match(capability.reason,/ASR is unavailable/);
  assert.equal(capability.gate,'PCM interval classification only; no ASR, resampling or downmix');
  checks.push('Catalog capability states bounded WAV Data and reviewed-interval CPU classification; ASR remains unavailable');
  if(process.env.TULDOK_NATIVE_ZOOM){
    await send('Emulation.clearDeviceMetricsOverride');
    const xdotool=process.env.TULDOK_XDOTOOL||'xdotool';
    const windows=execFileSync(xdotool,['search','--onlyvisible','--all','--pid',String(browser.pid),'--class','Chromium'],{encoding:'utf8'}).trim().split('\n');
    assert.equal(windows.length,1,'one owned visible Chromium window');
    execFileSync(xdotool,['windowfocus','--sync',windows[0]]);execFileSync(xdotool,['key','--clearmodifiers','ctrl+0']);
    const unzoomed=await evaluate('({width:innerWidth,ratio:devicePixelRatio})');
    for(let i=0;i<5;i++)execFileSync(xdotool,['key','--clearmodifiers','ctrl+plus']);
    await until(()=>evaluate('devicePixelRatio').then(r=>Math.abs(r/unzoomed.ratio-2)<.01));
    const zoomed=await evaluate('({width:innerWidth,ratio:devicePixelRatio})');assert.ok(Math.abs(zoomed.width*2-unzoomed.width)<20);
    await frame('document.getElementById("audio-segments").scrollIntoView({block:"center"});document.getElementById("audio-start").focus()');await key('Tab');
    assert.equal(await frame('document.activeElement.id'),'audio-end');
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'));assert.ok(await frame('document.documentElement.scrollWidth<=innerWidth+1'));
    const filename='audio-native-200.jpg';fs.writeFileSync(path.join(report,filename),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));captures.push(filename);
    checks.push('Native 200% Chromium zoom doubles pixel ratio/halves viewport; keyboard interval controls and layout remain usable');
    execFileSync(xdotool,['key','--clearmodifiers','ctrl+0']);
  }
  assert.deepEqual(errors,[]);assert.ok(!serverErrors.includes('Traceback'),serverErrors);
  const receipt={source_sha:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),dirty:!!execFileSync('git',['status','--porcelain'],{cwd:root,encoding:'utf8'}).trim(),checks,captures,record_id:row.id,release_url:releaseURL.replace(base,''),fixture_sha256:require('node:crypto').createHash('sha256').update(fs.readFileSync(fixture)).digest('hex')};
  fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify(receipt,null,2)+'\n');console.log('Audio workspace: '+checks.length+' checks passed. Evidence: '+report);
})().catch(async error=>{console.error(error);console.error(serverErrors.slice(-6000));console.error(JSON.stringify(errors));if(evaluate)try{console.error(await evaluate('({body:document.body.innerText.slice(-2500),frame:document.getElementById("catalog-frame")?.contentDocument?.body.innerText.slice(-6000)})'));}catch{}process.exitCode=1;}).finally(async()=>{ws?.close();for(const child of children)child.kill();await pause(250);for(const child of children)if(child.exitCode===null&&child.signalCode===null)child.kill('SIGKILL');fs.rmSync(temporary,{recursive:true,force:true});});
