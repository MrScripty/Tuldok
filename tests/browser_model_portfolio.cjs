'use strict';
// Real Chromium interaction/layout and controlled read-lifecycle evidence.
// This isolated static fixture does not claim native project persistence.
const fs=require('node:fs'),path=require('node:path'),http=require('node:http'),crypto=require('node:crypto');
const {spawn}=require('node:child_process');
const {waitForDebugger}=require('./browser_startup.cjs'),{cdpSession}=require('./browser_cdp_session.cjs');
const output=path.resolve(process.argv[2]||''),engine=process.env.TULDOK_BROWSER_EXECUTABLE;
if(!process.argv[2]||!engine||fs.existsSync(output))throw Error('Explicit fresh output directory and browser executable required');
fs.mkdirSync(output,{recursive:true,mode:0o700});
const fixture=structuredClone(require('./model_portfolio_fixture.cjs'));
const hash=value=>crypto.createHash('sha256').update(value).digest('hex');
const first=fixture.document.models[0];
const oldMethod=first.summary.method;first.summary.method+=' '+('A physical pressure field with explicit case and work scope. '.repeat(60));
first.label='First model <img src=x onerror="window.injected=true">';
fixture.cards[0].version.text=fixture.cards[0].version.text.replace(oldMethod,first.summary.method);
fixture.cards[0].version.sha256=first.card.sha256=hash(fixture.cards[0].version.text);
fixture.cards[0].version.bytes=Buffer.byteLength(fixture.cards[0].version.text);
for(let index=0;index<20;index++){
  const model=structuredClone(fixture.document.models[1]);model.id='extra-'+index;model.label='Extra model '+index;model.aliases=[];
  model.card.path='notes/extra-'+index+'.md';model.card.file_id=hash(fixture.project+'\0note\0'+model.card.path);
  fixture.document.models.push(model);fixture.cards.push({...structuredClone(fixture.cards[1]),id:model.card.file_id,path:model.card.path});
}
fixture.guide.version.text=JSON.stringify(fixture.document);
fixture.guide.version.sha256=fixture.inspection.expected_sha256=fixture.inspection.observed_sha256=hash(fixture.guide.version.text);
fixture.guide.version.bytes=fixture.inspection.expected_bytes=fixture.inspection.observed_bytes=Buffer.byteLength(fixture.guide.version.text);
const inline=JSON.stringify(fixture).replaceAll('<','\\u003c');
const html=`<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Authored organization fixture</title><link rel="stylesheet" href="/project-files.css"><link rel="stylesheet" href="/experiment-lineage.css"><script src="/experiment-graph.js"></script><script src="/project-model-portfolio.js"></script><body><main><button id="outside">Project status</button><section id="root"></section></main><script>
window.fixtureData=${inline};window.readCalls=[];window.holdNext=false;window.failNext=false;window.injected=false;window.focusRestored=0;
window.fixtureUI=ProjectModelPortfolio({root:document.querySelector('#root'),onContextFocusLost(){window.focusRestored++;document.querySelector('#outside').focus();},async read(action,args,signal){
  readCalls.push({action,args});
  if(action==='files_inspect')return {items:args.offset===0?[structuredClone(fixtureData.inspection)]:[],offset:args.offset,limit:40,total:1};
  if(action!=='file_get')throw Error('Unexpected fixture read');
  if(args.file_id===fixtureData.guide.id)return structuredClone(fixtureData.guide);
  const card=fixtureData.cards.find(card=>card.id===args.file_id);if(!card)throw Object.assign(Error('Missing retained card.'),{code:'unavailable'});
  if(window.holdNext){window.holdNext=false;return new Promise(resolve=>{window.releaseHeld=()=>resolve(structuredClone(card));window.heldSignal=signal;});}
  if(window.failNext){window.failNext=false;throw Object.assign(Error('Retained card unavailable.'),{code:'unavailable'});}
  if(window.corruptNext){window.corruptNext=false;const changed=structuredClone(card);changed.version.revision++;return changed;}
  return structuredClone(card);
}});fixtureUI.setContext({key:'one',project_id:fixtureData.project,enabled:true});
</script></body></html>`;
const staticRoot=path.join(__dirname,'../static'),allowed=new Map([
  ['/project-files.css',['project-files.css','text/css']],['/experiment-lineage.css',['experiment-lineage.css','text/css']],
  ['/experiment-graph.js',['experiment-graph.js','text/javascript']],['/project-model-portfolio.js',['project-model-portfolio.js','text/javascript']]]);
const server=http.createServer((request,response)=>{
  if(request.url==='/'){response.writeHead(200,{'Content-Type':'text/html; charset=utf-8'});response.end(html);return;}
  const asset=allowed.get(request.url);if(!asset){response.writeHead(404);response.end();return;}
  response.writeHead(200,{'Content-Type':asset[1]});response.end(fs.readFileSync(path.join(staticRoot,asset[0])));
});
let child,session;
const report={status:'starting',engine,verification_only:true,native_persistence_claim:false,graphics:'Headless Chromium with GPU disabled; no model or rendering speed claim.',checks:[],errors:[],browser_stopped:false};
const sourceFiles=['app.py','static/project-files.css','static/project-files.html','static/project-files.js','static/project-model-portfolio.js',
  'docs/contracts/project-model-portfolio.md','tests/model_portfolio_fixture.cjs','tests/test_project_model_portfolio.cjs',
  'tests/browser_model_portfolio.cjs','tests/test_project_model_portfolio_http.py','tests/test_workspace_project_files.cjs','tests/test_workspace_project_files_m4.cjs'];
report.source_sha256=Object.fromEntries(sourceFiles.map(name=>[name,hash(fs.readFileSync(path.join(__dirname,'..',name)))]));
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function main(){
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  const origin='http://127.0.0.1:'+server.address().port;
  try{
    const flags=['--headless','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--window-size=1440,1000','--user-data-dir='+path.join(output,'profile'),'about:blank'];
    report.flags=flags;report.origin=origin;
    const log=fs.openSync(path.join(output,'browser.log'),'w');child=spawn(engine,flags,{stdio:['ignore',log,log]});fs.closeSync(log);
    const port=await waitForDebugger(child,path.join(output,'profile/DevToolsActivePort'));
    const targets=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json(),target=targets.find(target=>target.type==='page');
    const socket=new WebSocket(target.webSocketDebuggerUrl);await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
    session=cdpSession(socket,{onEvent:event=>{if(event.method==='Runtime.exceptionThrown')report.errors.push(event.params.exceptionDetails.text);}});
    const send=session.send;
    await send('Page.enable');await send('Runtime.enable');
    async function evaluate(expression){const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw Error(result.exceptionDetails.exception?.description||result.exceptionDetails.text);return result.result.value;}
    async function until(expression){const end=Date.now()+15000;while(Date.now()<end){if(await evaluate(expression))return;await pause(50);}throw Error('Fixture wait expired: '+expression);}
    async function check(expression,label){if(!await evaluate(expression))throw Error(label);report.checks.push(label);}
    async function keyClick(selector){await evaluate(`(()=>{const element=document.querySelector(${JSON.stringify(selector)});if(!element||element.disabled)throw Error('Unavailable fixture control');element.scrollIntoView({block:'center'});element.focus();})()`);
      await send('Input.dispatchKeyEvent',{type:'keyDown',key:'Enter',code:'Enter',windowsVirtualKeyCode:13,text:'\r'});await send('Input.dispatchKeyEvent',{type:'keyUp',key:'Enter',code:'Enter',windowsVirtualKeyCode:13});}
    async function fill(selector,value){await evaluate(`(()=>{const element=document.querySelector(${JSON.stringify(selector)});element.value=${JSON.stringify(value)};element.dispatchEvent(new Event('input',{bubbles:true}));element.dispatchEvent(new Event('change',{bubbles:true}));})()`);}
    async function screenshot(name){const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});fs.writeFileSync(path.join(output,name),Buffer.from(shot.data,'base64'));}
    async function load(){await keyClick('#project-portfolio-notes');await until("document.querySelector('#project-portfolio-note').options.length===1");await keyClick('#project-portfolio-load');await until("document.querySelector('#project-portfolio-status').textContent==='Loaded retained authored model organization.'");}
    async function selectFirst(){await keyClick('[data-lineage-node="model/fit-first"]');await until("document.querySelector('#project-portfolio-status').textContent==='Exact retained model summary and captured evidence.'");}
    await send('Page.navigate',{url:origin+'/'});await until("!!window.fixtureUI");
    await load();await check('readCalls.length===2','Guide loading reads no model card or payload');
    await check("document.querySelector('#project-portfolio-count').textContent.includes('22 models in this guide; 1 source reviewed')",'Exact complete and reviewed guide counts');
    const point=await evaluate("(()=>{const element=document.querySelector('[data-lineage-node=\"group/pressure\"]');element.scrollIntoView({block:'center'});const box=element.getBoundingClientRect();return {x:box.x+box.width/2,y:box.y+box.height/2};})()");
    await send('Input.dispatchMouseEvent',{type:'mousePressed',button:'left',clickCount:1,...point});await send('Input.dispatchMouseEvent',{type:'mouseReleased',button:'left',clickCount:1,...point});
    await check("document.querySelector('#project-portfolio-group').value==='pressure'&&document.activeElement.dataset.lineageNode==='group/pressure'",'Pointer group activation applies the group and retains visible keyboard focus');
    await check("!document.querySelector('#root img')&&!window.injected",'Authored graph labels remain inert text');
    await keyClick('#project-portfolio-next');await check("document.querySelector('#project-portfolio-count').textContent.includes('Showing 21–22.')",'Bounded model paging uses the full population');
    await keyClick('#project-portfolio-prev');await selectFirst();
    await check("document.activeElement.id==='project-portfolio-model-heading'",'Keyboard selection moves focus to selected summary');
    await check("document.querySelector('#project-portfolio-detail').innerText.includes(fixtureData.document.models[0].summary.method)",'Complete long method paragraph is readable retained text');
    await check("document.querySelector('#project-portfolio-detail').scrollWidth<=document.querySelector('#project-portfolio-detail').clientWidth",'Desktop detail wraps without horizontal overflow');
    await evaluate("document.querySelector('#project-portfolio-model-heading').scrollIntoView({block:'start'})");await screenshot('desktop-summary.png');
    await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
    await check("document.querySelector('#project-portfolio-detail').scrollWidth<=document.querySelector('#project-portfolio-detail').clientWidth",'Mobile detail wraps without horizontal overflow');
    await evaluate("document.querySelector('#project-portfolio-model-heading').scrollIntoView({block:'start'})");await screenshot('mobile-summary.png');
    await send('Emulation.clearDeviceMetricsOverride');
    await fill('#project-portfolio-search','C107');await keyClick('#project-portfolio-filter-form button');
    await check("document.querySelector('#project-portfolio-count').textContent.includes('1 match the applied filters')&&document.querySelector('#project-portfolio-next').disabled",'Alias filtering has exact counts and paging');
    await selectFirst();await keyClick('#project-portfolio-detail button');await until("document.querySelector('#project-portfolio-model-heading')?.textContent==='Second model'");
    await check("document.querySelector('#project-portfolio-detail').innerText.includes('A source-reviewed interpretation has not been recorded')",'Pending review does not invent a method summary');
    await check("document.querySelector('[data-lineage-node=\"model/fit-second\"]').getAttribute('aria-pressed')==='true'",'Off-filter relationship navigation brings selected model into the graph window');
    await selectFirst();await evaluate('window.failNext=true');await keyClick('#project-portfolio-detail button');
    await until("document.querySelector('#project-portfolio-status').textContent==='unavailable: Retained card unavailable.'");
    await check("document.querySelector('#project-portfolio-detail').children.length===0",'Unavailable card clears the previous model detail');
    await evaluate('window.corruptNext=true');await keyClick('[data-lineage-node="model/fit-first"]');
    await until("document.querySelector('#project-portfolio-status').textContent==='invalid: Model card differs from its exact retained organization reference.'");
    await check("document.querySelector('#project-portfolio-detail').children.length===0",'Foreign card revision is refused without stale detail');
    await evaluate('window.holdNext=true');await keyClick('[data-lineage-node="model/fit-first"]');await until('!!window.releaseHeld');
    await evaluate("fixtureUI.setContext({key:'two',project_id:fixtureData.project,enabled:true});window.releaseHeld()");
    await check("window.heldSignal.aborted&&document.querySelector('#project-portfolio-content').hidden",'Context replacement aborts and clears pending view');
    await load();await check("document.querySelector('#project-portfolio-detail').children.length===0",'Reload after supersession starts without old detail');
    await selectFirst();await evaluate("fixtureUI.setContext({key:'two',project_id:fixtureData.project,enabled:false})");
    await check("document.querySelector('#root').hidden&&document.querySelector('#project-portfolio-detail').children.length===0&&document.activeElement.id==='outside'",'Permission loss clears private view and restores host focus');
    await evaluate("fixtureUI.setContext({key:'three',project_id:fixtureData.project,enabled:true})");await load();
    await fill('#project-portfolio-search','No match');await keyClick('#project-portfolio-filter-form button');
    await check("document.querySelector('#project-portfolio-count').textContent.includes('0 match the applied filters. Showing 0–0.')",'Empty filter result retains exact zero denominator');
    await check('readCalls.every(call=>[\'files_inspect\',\'file_get\'].includes(call.action))','All interactions use read-only project-file actions');
    if(report.errors.length)throw Error('Browser runtime exception');report.status='passed_authored_portfolio_real_browser_component';
  }catch(error){report.status='failed_authored_portfolio_real_browser_component';report.error=String(error);
    if(session){try{const state=await session.send('Runtime.evaluate',{expression:'document.body.innerText',returnByValue:true});report.failure_page=state.result?.value;
      const shot=await session.send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});fs.writeFileSync(path.join(output,'failed-page.png'),Buffer.from(shot.data,'base64'));}catch(captureError){report.failure_capture_error=String(captureError);}}
    throw error;}
  finally{session?.close();if(child&&child.exitCode===null&&child.signalCode===null){child.kill('SIGTERM');for(let i=0;i<100&&child.exitCode===null&&child.signalCode===null;i++)await pause(50);if(child.exitCode===null&&child.signalCode===null)child.kill('SIGKILL');}
    report.browser_stopped=!child||child.exitCode!==null||child.signalCode!==null;await new Promise(resolve=>server.close(resolve));
    report.end_source_sha256=Object.fromEntries(sourceFiles.map(name=>[name,hash(fs.readFileSync(path.join(__dirname,'..',name)))]));
    report.source_stable_through_tests=JSON.stringify(report.source_sha256)===JSON.stringify(report.end_source_sha256);
    if(!report.source_stable_through_tests){report.status='failed_authored_portfolio_real_browser_component';report.errors.push('Source changed during browser qualification');process.exitCode=1;}
    report.producer_sha256=hash(fs.readFileSync(__filename));fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2)+'\n');}
  console.log(report.status,report.checks.length,'checks');
}
main().catch(error=>{console.error(String(error));process.exitCode=1;});
