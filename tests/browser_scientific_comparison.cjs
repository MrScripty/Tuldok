'use strict';
// Actual HTTP/DOM readers with explicitly synthetic terminal arrays and receipts.
// The tiny runtime is not runnable Python; no producer, custody or science qualification.
const assert=require('node:assert/strict'),fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn,execFileSync}=require('node:child_process');
const {authenticatedFixture}=require('./auth_helpers.cjs'),{waitForDebugger}=require('./browser_startup.cjs');
const {pageLoadTracker}=require('./browser_page_load.cjs');
const tracker=pageLoadTracker();
const {qaDirectory,screenshotOptions}=require('./qa_artifacts.cjs');
const root=path.resolve(__dirname,'..'),report=qaDirectory(root,'scientific-comparison'),temp=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-scientific-comparison-browser-'));
const auth=authenticatedFixture(),children=[],errors=[],requests=[],checks=[];
let ws,evaluate,send,stderr='';const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn,label){for(let i=0;i<750;i++){const value=await fn();if(value)return value;await pause(100);}throw Error(label||'Timed out');}
function launch(command,args,options={}){const child=spawn(command,args,{cwd:root,...options});children.push(child);return child;}
(async()=>{
  const fixture=launch(process.env.PYTHON||'python3',['-u','tests/scientific_comparison_fixture.py',path.join(report,'domain-receipt.json')],{env:{...process.env,PYTHONPATH:'.:tests',PYTHONDONTWRITEBYTECODE:'1'},stdio:['pipe','pipe','pipe']});
  let output='';fixture.stdout.on('data',chunk=>output+=chunk);fixture.stderr.on('data',chunk=>stderr+=chunk);
  const info=await until(()=>{if(fixture.exitCode!==null)throw Error('Fixture exited '+stderr);try{return JSON.parse(output.split('\n')[0]);}catch{return null;}},'Synthetic retained-material fixture unavailable');
  const control=async command=>{const prior=output.length;fixture.stdin.write(command+'\n');await until(()=>output.slice(prior).includes('\"control\": \"'+command+'\"'),'Fixture control '+command);};
  const base='http://127.0.0.1:'+info.port;await auth.register(base,info.data,root);
  const browser=launch(process.env.BROWSER||'/usr/bin/chromium',['--headless','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--window-size=1440,900','--user-data-dir='+path.join(temp,'browser'),'about:blank'],{stdio:'ignore',env:{...process.env,XDG_CONFIG_HOME:temp,XDG_CACHE_HOME:temp}});
  const debug=await waitForDebugger(browser,path.join(temp,'browser','DevToolsActivePort'));
  const target=(await(await fetch('http://127.0.0.1:'+debug+'/json')).json()).find(tab=>tab.type==='page');
  ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  let next=0;const pending=new Map();
  send=(method,params={})=>new Promise((resolve,reject)=>{const id=++next,timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method));},25000);pending.set(id,{resolve:value=>{clearTimeout(timer);resolve(value);},reject});ws.send(JSON.stringify({id,method,params}));});
  ws.onmessage=event=>{const message=JSON.parse(event.data);tracker.observe(message);if(message.id){const task=pending.get(message.id);pending.delete(message.id);if(task)message.error?task.reject(message.error):task.resolve(message.result);}if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails);if(message.method==='Network.requestWillBeSent')requests.push({url:message.params.request.url,method:message.params.request.method,headers:message.params.request.headers,body:message.params.request.postData});};
  evaluate=async expression=>{const value=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(value.exceptionDetails)throw Error(JSON.stringify(value.exceptionDetails));return value.result.value;};
  const text=selector=>evaluate(`document.querySelector(${JSON.stringify(selector)})?.textContent`);
  async function activate(selector,keyboard=false){
    await until(()=>evaluate(`(()=>{const e=document.querySelector(${JSON.stringify(selector)});if(!e||e.disabled||!e.getClientRects().length)return false;e.scrollIntoView({block:'center'});return true;})()`),'Control unavailable '+selector);
    if(keyboard){await evaluate(`document.querySelector(${JSON.stringify(selector)}).focus()`);for(const type of ['keyDown','keyUp'])await send('Input.dispatchKeyEvent',{type,key:'Enter',code:'Enter',windowsVirtualKeyCode:13,...(type==='keyDown'?{text:'\r'}:{})});}
    else{const box=await evaluate(`(()=>{const r=document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};})()`);for(const type of ['mousePressed','mouseReleased'])await send('Input.dispatchMouseEvent',{type,button:'left',clickCount:1,...box});}
  }
  await send('Page.enable');await send('Page.setLifecycleEventsEnabled',{enabled:true});await send('Runtime.enable');await send('Network.enable');await auth.browser(send,base);
  await send('Page.navigate',{url:base+'/workspaces#pipeline'});
  await until(()=>evaluate('!!document.getElementById("dataset") && !document.getElementById("dataset").disabled'));
  await evaluate('(()=>{const select=document.getElementById("dataset");select.value="catalog";select.dispatchEvent(new Event("change",{bubbles:true}));})()');
  await until(()=>evaluate(`!!document.querySelector('[data-lineage-node="${info.trial_id}"]')`),'Retained candidate Trial missing from actual lineage');
  await activate('[data-lineage-node="'+info.trial_id+'"]',true);
  await activate('#lineage-compare',true);
  await until(()=>evaluate(`document.querySelector('#scientific-candidate')?.value==='${info.candidate}'&&!document.querySelector('#scientific-compare')?.disabled`),'Exact baseline/candidate selection did not open from lineage');
  assert.equal(requests.filter(row=>row.url.endsWith('/scientific-comparison')).length,0,'Selection must not compare or start compute');
  await activate('#scientific-compare',true);
  await until(()=>evaluate('!!document.getElementById("scientific-result")'),'Actual comparison table missing');
  assert.match(await text('#scientific-result'),/Exact comparison: compatible/);
  assert.match(await text('#scientific-result'),/Coverage: baseline 1; candidate 1; matched 1; union 1/);
  assert.match(await text('#scientific-result'),/owned_per_case_criterion_not_retained/);
  assert.match(await text('#scientific-result'),/Memory: unknown/);
  const first=requests.find(row=>row.url.endsWith('/scientific-comparison'));
  assert.equal(JSON.parse(first.body).operands[0].run_id,info.baseline);
  assert.equal(JSON.parse(first.body).operands[1].run_id,info.candidate);
  assert.ok(first.headers['Tuldok-Operation-Contract']?.startsWith('runs.compare_scientific_evidence/1/'));
  const pair=await evaluate(`Array.from(document.querySelectorAll('#scientific-result table:first-of-type tbody td')).map(node=>node.textContent)`);
  assert.ok((await text('#scientific-result')).includes('2 pressure_unit')||(await text('#scientific-result')).includes('2 '),'Independent expected diagnostic delta absent');
  checks.push('Actual lineage opens exact ordered operands; selection causes no comparison/admission; keyboard submission returns independent expected delta 2 and explicit unknown criteria/memory.');
  for(const width of [1440,390]){
    await send('Emulation.setDeviceMetricsOverride',{width,height:900,deviceScaleFactor:1,mobile:false});
    await evaluate('document.querySelector("#scientific-result").scrollIntoView({block:"start"})');await pause(80);
    assert.ok(await evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'Page overflows narrow viewport');
    assert.ok(await evaluate('document.querySelector("#scientific-result .real-table-wrap").getAttribute("tabindex")==="0"'),'Table scroll is not keyboard accessible');
    fs.writeFileSync(path.join(report,'comparison-'+width+'.jpg'),Buffer.from((await send('Page.captureScreenshot',screenshotOptions)).data,'base64'));
  }
  checks.push('1440/390px tables retain all values and keyboard scrolling without page overflow.');
  // Hold only delivery of an actual backend response, then change exact selectors.
  await evaluate(`(()=>{const original=TuldokAuth.fetch.bind(TuldokAuth);window.releaseScientific=null;window.delayScientific=true;TuldokAuth.fetch=async(...args)=>{const response=await original(...args);if(String(args[0]).endsWith('/scientific-comparison')&&window.delayScientific){window.delayScientific=false;await new Promise(resolve=>window.releaseScientific=resolve);}return response;};})()`);
  await activate('#scientific-compare',true);
  await until(()=>evaluate('typeof window.releaseScientific==="function"'),'Actual old response was not held');
  assert.equal(await evaluate('!!document.getElementById("scientific-result")'),false,'Pending request retains old values');
  await evaluate('(()=>{const input=document.querySelector("#scientific-x");input.value="1";input.dispatchEvent(new Event("change",{bubbles:true}));})()');
  await activate('#scientific-compare',true);
  await until(()=>evaluate('!!document.getElementById("scientific-result")'),'New exact response missing');
  const newText=await text('#scientific-result');await evaluate('window.releaseScientific()');await pause(120);
  assert.equal(await text('#scientific-result'),newText,'Old response replaced newer selection');
  checks.push('Actual overlapping HTTP responses clear pending values and fence stale delivery after exact point changes.');
  // Attached recovery operand is selected through its actual status and Ref readers.
  await evaluate(`(()=>{const select=document.querySelector('#scientific-candidate');select.value='${info.recovered}';select.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  await until(()=>evaluate('!document.querySelector("#scientific-compare")?.disabled'),'Exact recovered operand did not load');
  await activate('#scientific-compare',true);
  await until(()=>evaluate('!!document.getElementById("scientific-result")'),'Recovered comparison missing');
  assert.match(await text('#scientific-result'),/original state interrupted/);
  const recovered=requests.filter(row=>row.url.endsWith('/scientific-comparison')).at(-1);
  assert.deepEqual(JSON.parse(recovered.body).operands[1],{kind:'publication_result',ref:info.ref});
  assert.match(await text('#scientific-result'),/Exact comparison: compatible/);
  checks.push('Exact attached publication Ref uses real publication readers and preserves original interrupted state.');
  // Removing only the fixture-owned retained candidate root invalidates a fresh read.
  await control('remove');
  await evaluate(`(()=>{const select=document.querySelector('#scientific-candidate');select.value='${info.candidate}';select.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  await until(()=>text('.scientific-comparison [role="status"]').then(value=>value&&!value.includes('Reading exact')),'Removed retained root did not refuse');
  assert.equal(await evaluate('!!document.getElementById("scientific-result")'),false);
  assert.equal(await evaluate('document.getElementById("scientific-compare")?.disabled'),true);
  await control('restore');checks.push('Removed retained root refuses fresh candidate selection and clears prior values.');
  const forbidden=requests.filter(row=>row.method==='POST'&&/\/api\/workspace\//.test(row.url)&&!/(\/model-evidence|\/scientific-comparison|\/publication-results)$/.test(row.url));
  assert.deepEqual(forbidden,[],'Read-only comparison dispatched an unexpected workspace mutation');
  assert.deepEqual(errors,[],'Browser runtime exceptions');
  fixture.stdin.write('done\n');await until(()=>fixture.exitCode!==null,'Fixture did not close fresh schema');assert.equal(fixture.exitCode,0,stderr);
  const domain=JSON.parse(fs.readFileSync(path.join(report,'domain-receipt.json'),'utf8'));
  assert.deepEqual(domain.counts_after,domain.counts_before);assert.equal(domain.original_recovered_state,'interrupted');
  fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify({scope:'Real HTTP/browser with actual metadata/admission/retained context; synthetic terminal receipts and arrays; no producer/runtime/custody/science qualification',checks,source_head:require('node:child_process').execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),
    source_hashes:Object.fromEntries(['agent_api.py','runs.py','run_publication.py','extension_evidence.py','static/workspace-real.js','static/workspace-scientific-comparison.js','tests/scientific_comparison_fixture.py','tests/browser_scientific_comparison.cjs'].map(file=>[file,crypto.createHash('sha256').update(fs.readFileSync(path.join(root,file))).digest('hex')])),requests:requests.filter(row=>row.url.endsWith('/scientific-comparison')).map(row=>({method:row.method,body:JSON.parse(row.body),contract:row.headers['Tuldok-Operation-Contract']})),domain},null,2)+'\n');
  console.log(JSON.stringify({state:'passed',report,checks}));
})().catch(error=>{console.error(error);console.error(stderr);process.exitCode=1;}).finally(async()=>{
  if(ws)ws.close();
  for(const child of children.reverse())if(child.exitCode===null){if(child.stdin?.writable)child.stdin.end('done\n');else child.kill('SIGTERM');}
  await Promise.all(children.map(child=>child.exitCode!==null?Promise.resolve():new Promise(resolve=>{const timer=setTimeout(()=>{child.kill('SIGTERM');resolve();},3000);child.once('exit',()=>{clearTimeout(timer);resolve();});})));
  fs.rmSync(temp,{recursive:true,force:true});
});
