'use strict';
const fixtureAuth = require('./auth_helpers.cjs').authenticatedFixture();
const fetch = fixtureAuth.fetch;
// Real Chromium regression for saved external-graph keyboard focus.
// Opens an inert private Project and creates graph metadata only; no recipe
// preflight, execution, Study, grant or scientific qualification is performed.
const assert=require('node:assert/strict'), fs=require('node:fs'), os=require('node:os'), path=require('node:path'), crypto=require('node:crypto');
const {spawn,execFileSync}=require('node:child_process');
const {waitForDebugger}=require('./browser_startup.cjs');
const {qaDirectory}=require('./qa_artifacts.cjs');
const root=path.resolve(__dirname,'..'),report=qaDirectory(root,'workspace-graph-focus');
const temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-graph-focus-browser-')),projectRoot=path.join(temporary,'project');fs.mkdirSync(projectRoot);
const sha=raw=>crypto.createHash('sha256').update(raw).digest('hex');
const errors=[],children=[],inspectionRequests=[];
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
let ws,send,evaluate,serverErrors='',paused=null;
async function until(fn,message='Timed out'){for(let i=0;i<600;i++){const value=await fn();if(value)return value;await pause(100);}throw Error(message);}
function launch(command,args,options){const child=spawn(command,args,options);children.push(child);return child;}
const input=Buffer.concat([Buffer.from('Neutral browser input λ\n'),Buffer.from([0,255])]);
const source=fs.readFileSync(path.join(root,'tests/fixtures/external_recipe.py'));
const definition={schema_version:1,format:'external_recipe_v1',id:'neutral',name:'Neutral execution',version:1,runtime:'system_python',sources:[{path:'recipe.py',sha256:sha(source)}],entrypoint:'recipe.py',arguments:[{parameter:'mode'},{input:'sample'},{output_dir:true}],parameters:{mode:{type:'string',default:'complete',enum:['complete','sleep','nonzero'],max_length:16}},inputs:{sample:{max_bytes:4096}},outputs:[{path:'result.txt',role:'result',max_bytes:4096,required:true}],environment:{},resources:{wall_seconds:10,max_output_bytes:16384}};
const recipe=Buffer.from(JSON.stringify(definition));
const project={schema_version:1,id:crypto.randomBytes(16).toString('hex'),name:'Neutral process fixture',data:[{id:'sample',label:'Exact bytes',path:'input.bin',sha256:sha(input)}],recipes:[{id:'neutral',label:'Neutral executable',path:'recipe.json',sha256:sha(recipe)}],evidence:[],requirements:[]};
for(const [name,bytes] of Object.entries({'recipe.py':source,'recipe.json':recipe,'input.bin':input,'project.json':JSON.stringify(project)}))fs.writeFileSync(path.join(projectRoot,name),bytes);
const serverArgs=port=>['-u','app.py','--port',String(port),'--data',path.join(temporary,'data'),'--project-root','sample='+projectRoot];
(async()=>{
  let server=launch('python3',serverArgs(0),{cwd:root,stdio:['ignore','pipe','pipe']});
  let output='';server.stdout.on('data',chunk=>output+=chunk);server.stderr.on('data',chunk=>serverErrors+=chunk);
  const port=await until(()=>{if(server.exitCode!==null)throw Error('Project server exited: '+serverErrors);return output.match(/127\.0\.0\.1:(\d+)/)?.[1];});
  const base='http://127.0.0.1:'+port;
  await fixtureAuth.register('http://127.0.0.1:'+port,path.join(temporary,'data'),root);
  const browser=launch(process.env.BROWSER||'/usr/bin/chromium',['--headless','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--window-size=1440,900','--user-data-dir='+path.join(temporary,'browser'),'about:blank'],{stdio:['ignore','ignore','ignore'],env:{...process.env,XDG_CONFIG_HOME:temporary,XDG_CACHE_HOME:temporary}});
  const debugPort=await waitForDebugger(browser,path.join(temporary,'browser','DevToolsActivePort'));
  const tabs=await(await fetch('http://127.0.0.1:'+debugPort+'/json')).json(),target=tabs.find(tab=>tab.type==='page'&&tab.url==='about:blank');assert.ok(target);
  ws=new WebSocket(target.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  let next=0;const pending=new Map();
  send=(method,params={})=>new Promise((resolve,reject)=>{const id=++next,timer=setTimeout(()=>{pending.delete(id);reject(Error('CDP timeout '+method));},20000);pending.set(id,{resolve:value=>{clearTimeout(timer);resolve(value);},reject:error=>{clearTimeout(timer);reject(error);}});ws.send(JSON.stringify({id,method,params}));});
  ws.onmessage=event=>{const message=JSON.parse(event.data);if(message.method==='Fetch.requestPaused')paused=message.params;if(message.id){const task=pending.get(message.id);pending.delete(message.id);if(task)message.error?task.reject(message.error):task.resolve(message.result);}if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails);if(message.method==='Network.requestWillBeSent'){const request=message.params.request;if(request.url.includes('/project-snapshots/')||request.url.includes('/recipes/'))inspectionRequests.push({url:request.url,contract:Object.entries(request.headers).find(([name])=>name.toLowerCase()==='tuldok-operation-contract')?.[1]});}};
  evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  const element=selector=>`document.querySelector(${JSON.stringify(selector)})`,text=selector=>evaluate(`${element(selector)}?.textContent`);
  async function click(selector){const box=await until(()=>evaluate(`(async()=>{const e=${element(selector)};if(!e||e.disabled||!e.getClientRects().length)return null;e.scrollIntoView({block:'center'});await new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r)));const b=e.getBoundingClientRect(),x=b.x+b.width/2,y=b.y+b.height/2,hit=document.elementFromPoint(x,y);return hit&&(hit===e||e.contains(hit))?{x,y}:null})()`),'Click target unavailable '+selector);for(const type of ['mousePressed','mouseReleased'])await send('Input.dispatchMouseEvent',{type,button:'left',clickCount:1,...box});}
  async function key(key,code=key,modifiers=0){for(const type of ['keyDown','keyUp'])await send('Input.dispatchKeyEvent',{type,key,code,modifiers,windowsVirtualKeyCode:{Enter:13,Escape:27,Tab:9,a:65}[key]||0,...(type==='keyDown'&&key==='Enter'?{text:'\r',unmodifiedText:'\r'}:{})});}
  async function fill(selector,value){await click(selector);await key('a','KeyA',2);await send('Input.insertText',{text:value});}
  const select=(selector,value)=>evaluate(`(()=>{const e=${element(selector)};e.value=${JSON.stringify(value)};e.dispatchEvent(new Event('change',{bubbles:true}));})()`);
  async function nav(view){await click('#nav-'+view);await until(()=>evaluate(`!document.getElementById('view-${view}').hidden && !document.getElementById('project-${view}-root').hidden`));await until(()=>text(`#project-${view}-root`).then(value=>value?.includes('PROJECT · SAVED SNAPSHOT')));}
  async function openProject(manifest,name,id){await click('#open-project');await until(()=>evaluate('document.getElementById("project-open-dialog").open && !document.getElementById("project-open-submit").disabled'));await select('#project-root','sample');await fill('#project-manifest',manifest);await evaluate('document.getElementById("project-open-submit").focus()');await key('Enter');await until(()=>evaluate('document.getElementById("dataset").value==='+JSON.stringify('project:'+id)));await nav('data');assert.match(await text('#project-data-root'),new RegExp(name.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')));}
  await send('Page.enable');await send('Page.setLifecycleEventsEnabled',{enabled:true});await send('Runtime.enable');await send('Network.enable');
  await fixtureAuth.browser(send,'http://127.0.0.1:'+port);
  await send('Page.navigate',{url:base+'/workspaces'});await until(()=>evaluate('typeof document.getElementById("open-project")?.onclick==="function"'),'Project controls are not bound');
  await openProject('project.json',project.name,project.id);await nav('pipeline');
  await click('[data-project-recipe="neutral"]');await until(()=>evaluate('!!document.querySelector("[data-external-input=sample]")'));
  await select('[data-external-input="sample"]','sample');await fill('#external-create-name','Neutral exact bytes');
  await evaluate('document.getElementById("external-create-submit").focus()');await key('Enter');
  await until(()=>evaluate('!!document.getElementById("external-preflight")'));
  const beforeChoices=inspectionRequests.length;await click('#external-input-choices');
  await until(()=>evaluate('(()=>{const input=document.querySelector("#real-pipeline-root [data-external-input-kind=sample]");return !!input&&!input.disabled;})()'));
  assert.equal(await evaluate('document.querySelector("#real-pipeline-root [data-external-input=sample]").value'),'sample','Current snapshot choices retain the exact saved binding');
  const choiceRequests=inspectionRequests.slice(beforeChoices);
  assert.ok(choiceRequests.some(item=>item.url===base+'/api/workspace/project-snapshots/'+project.id&&item.contract==='project_snapshots.get/2/770e999697f069af13e9cf0d48daaf930ee26db4d7415169edecb414f68bdd01'),'Saved graph choices select the scoped current snapshot contract');
  assert.ok(choiceRequests.some(item=>item.url.includes('/recipes/neutral?')&&item.contract==='recipes.inspect/4/0080ae0e39bf758b9c96c3208ef1614a9335f257731cfde935a23d8b486dedb1'),'Saved graph choices select the current recipe contract');

  await click('#external-clone');await until(()=>text('#external-name').then(()=>evaluate('document.getElementById("external-name").value.endsWith("copy")')));
  await click('#external-clone');await until(()=>text('#external-name').then(()=>evaluate('document.getElementById("external-name").value.endsWith("copy copy")')));
  await until(()=>evaluate('document.getElementById("real-graph-select").options.length>=3'));
  const values=await evaluate('Array.from(document.getElementById("real-graph-select").options,o=>o.value)');
  await select('#real-graph-select',values.at(-1));await until(()=>evaluate('document.getElementById("real-graph-select").value==='+JSON.stringify(values.at(-1))+'&&!document.getElementById("real-graph-select").disabled'));
  await evaluate('document.getElementById("real-graph-select").focus()');assert.equal(await evaluate('document.activeElement===document.getElementById("real-graph-select")'),true,'Initial native select focus');
  const observed=[];
  for(const name of ['Home','ArrowDown','ArrowDown']){
    assert.equal(await evaluate('document.activeElement===document.getElementById("real-graph-select")'),true,'Native keyboard focus before each key');
    for(const type of ['keyDown','keyUp'])await send('Input.dispatchKeyEvent',{type,key:name,code:name,windowsVirtualKeyCode:name==='Home'?36:40});
    await until(()=>evaluate('!document.getElementById("real-graph-select").disabled'));await pause(20);
    observed.push(await evaluate('({focus:document.activeElement===document.getElementById("real-graph-select"),value:document.getElementById("real-graph-select").value,active:document.activeElement.tagName})'));
  }
  console.log('OBSERVED',JSON.stringify({values,observed}));
  assert.deepEqual(observed.map(x=>x.focus),[true,true,true],'Every settled graph change retains native keyboard focus');
  assert.deepEqual(observed.map(x=>x.value),values.slice(0,3),'Continuous native keys reach successive saved graphs');

  const negativeChecks=[];
  {
    async function hold(value,name){paused=null;await send('Fetch.enable',{patterns:[{urlPattern:base+'/api/workspace/graphs/'+value,requestStage:'Request'}]});await evaluate('document.getElementById("real-graph-select").focus()');for(const type of ['keyDown','keyUp'])await send('Input.dispatchKeyEvent',{type,key:name,code:name,windowsVirtualKeyCode:name==='Home'?36:40});await until(()=>paused,'Expected held graph read');assert.equal(paused.request.method,'GET');}
    await hold(values[0],'Home');await evaluate('document.getElementById("dataset").focus()');assert.equal(await evaluate('document.activeElement.id'),'dataset');await send('Fetch.continueRequest',{requestId:paused.requestId});await send('Fetch.disable');await until(()=>evaluate('!document.getElementById("real-graph-select").disabled&&document.getElementById("real-graph-select").value==='+JSON.stringify(values[0])));assert.equal(await evaluate('document.activeElement.id'),'dataset');negativeChecks.push('held graph read preserves separately moved focus');
    await hold(values[1],'ArrowDown');await click('#nav-runs');await until(()=>evaluate('!document.getElementById("view-runs").hidden'));await send('Fetch.continueRequest',{requestId:paused.requestId});await send('Fetch.disable');await until(()=>evaluate('!!document.getElementById("real-runs-refresh")&&!document.getElementById("real-runs-refresh").disabled'),'Runs action did not settle');assert.equal(await evaluate('!document.getElementById("view-runs").hidden&&document.activeElement.id!=="real-graph-select"'),true);negativeChecks.push('held graph read does not restore hidden Pipeline focus after navigation');
  }
  assert.deepEqual(await(await fetch(base+'/api/workspace/runs')).json(),[],'Graph-focus regression never executes a recipe');
  assert.deepEqual(errors,[]);assert.ok(!serverErrors.includes('Traceback'),serverErrors);
  const result={state:'passed',scope:'Inert private Project graph metadata only; no recipe execution or scientific qualification',source_commit:execFileSync('git',['rev-parse','HEAD'],{cwd:root,encoding:'utf8'}).trim(),workspace_real_sha256:sha(fs.readFileSync(path.join(root,'static/workspace-real.js'))),harness_sha256:sha(fs.readFileSync(__filename)),native_keys:['Home','ArrowDown','ArrowDown'],programmatic_focus_calls_in_journey:1,values,observed,negativeChecks,recipe_runs:0,browser:(await send('Browser.getVersion')).product};
  fs.writeFileSync(path.join(report,'receipt.json'),JSON.stringify(result,null,2));console.log('PASS graph focus regression',JSON.stringify(result));console.log('Receipt',path.join(report,'receipt.json'));
})().catch(async error=>{console.error(error);console.error('Application stderr:',serverErrors);if(evaluate)try{console.error(await evaluate('JSON.stringify({url:location.href,body:document.body.innerText.slice(-9000)})'));}catch{}process.exitCode=1;}).finally(()=>{ws?.close();for(const child of children.reverse())child.kill('SIGTERM');});
