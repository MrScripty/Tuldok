// Explicit real-model acceptance: PUMAS_GATEWAY, PUMAS_MODEL and TULDOK_EVIDENCE_DIR are required.
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn}=require('node:child_process');
const root=path.resolve(__dirname,'..'),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-images-')),children=[];
const evidence=process.env.TULDOK_EVIDENCE_DIR; if(evidence)fs.mkdirSync(evidence,{recursive:true});
const gateway=process.env.PUMAS_GATEWAY,model=process.env.PUMAS_MODEL;
assert(gateway&&model&&evidence,'Set PUMAS_GATEWAY, PUMAS_MODEL and TULDOK_EVIDENCE_DIR');
let ws;
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn,attempts=200){for(let i=0;i<attempts;i++){const value=await fn();if(value)return value;await pause(100);}throw Error('Timed out');}
function launch(command,args,options={}){const child=spawn(command,args,options);children.push(child);return child;}
(async()=>{
  const server=launch('python3',['-u','app.py','--port','0','--data',path.join(temporary,'data')],{cwd:root,stdio:['ignore','pipe','pipe']});
  let output='',stderr='';server.stdout.on('data',data=>output+=data);server.stderr.on('data',data=>stderr+=data);
  const port=await until(()=>output.match(/Tuldok: http:\/\/127\.0\.0\.1:(\d+)/)?.[1]);
  launch(process.env.BROWSER||'/opt/brave.com/brave/brave',['--headless','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--window-size=1400,950','--user-data-dir='+path.join(temporary,'browser'),'about:blank'],{stdio:'ignore'});
  const active=path.join(temporary,'browser','DevToolsActivePort');
  const debugPort=await until(()=>fs.existsSync(active)&&fs.readFileSync(active,'utf8').split('\n')[0]);
  const tabs=await(await fetch('http://127.0.0.1:'+debugPort+'/json')).json();
  ws=new WebSocket(tabs[0].webSocketDebuggerUrl);await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  let id=0;const pending=new Map(),errors=[];
  ws.onmessage=event=>{const message=JSON.parse(event.data);if(message.id){const task=pending.get(message.id);pending.delete(message.id);message.error?task.reject(message.error):task.resolve(message.result);}if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails);};
  const send=(method,params={})=>new Promise((resolve,reject)=>{pending.set(++id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
  const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  const click=id=>evaluate('document.getElementById('+JSON.stringify(id)+').click()');
  const fill=(id,value)=>evaluate('(()=>{const e=document.getElementById('+JSON.stringify(id)+');e.value='+JSON.stringify(value)+';e.dispatchEvent(new Event("input",{bubbles:true}));e.dispatchEvent(new Event("change",{bubbles:true}));})()');
  await send('Page.enable');await send('Runtime.enable');
  const downloads=path.join(temporary,'downloads');fs.mkdirSync(downloads);
  await send('Browser.setDownloadBehavior',{behavior:'allow',downloadPath:downloads});
  await send('Page.navigate',{url:'http://127.0.0.1:'+port});
  await until(()=>evaluate('!!document.getElementById("capture-session")?.value&&!document.getElementById("generation-view").disabled'));
  await click('generation-view');
  await fill('generation-url',gateway);await click('generation-refresh');
  await until(()=>evaluate('[...document.getElementById("generation-model").options].some(option=>option.value==='+JSON.stringify(model)+')'));
  await fill('generation-model',model);
  assert.equal(await evaluate('document.getElementById("generation-model").value'),model,'Selected real served image model');
  const prompt=process.env.PUMAS_PROMPT||'A red ceramic teapot beside a yellow lemon on a blue table, soft daylight, detailed still life photograph';
  await fill('generation-size','512x512');await fill('generation-seed','42');await fill('generation-prompt',prompt);
  await send('Network.enable');let responseId;
  const onMessage=ws.onmessage;ws.onmessage=event=>{const message=JSON.parse(event.data);if(message.method==='Network.responseReceived'&&message.params.response.url.endsWith('/api/generation/generate'))responseId=message.params.requestId;onMessage(event);};
  const started=Date.now();await click('generate');
  await until(async()=>{
    const status=await evaluate('({status:document.getElementById("generation-status").textContent,busy:document.getElementById("generate").disabled})');
    if(!status.busy&&status.status!=='Image ready')throw Error(status.status);
    return status.status==='Image ready'&&!status.busy;
  },6500);
  const response=JSON.parse((await send('Network.getResponseBody',{requestId:responseId})).body);
  const durationSeconds=(Date.now()-started)/1000;
  const png=Buffer.from((await evaluate('document.getElementById("generated-image").src')).split(',')[1],'base64');
  assert.equal(await evaluate('document.getElementById("generated-image").naturalWidth'),512);
  await click('generation-download');await until(()=>fs.existsSync(path.join(downloads,'pumas-42.png')));
  assert.deepEqual(fs.readFileSync(path.join(downloads,'pumas-42.png')),png,'Saved PNG equals displayed response');
  if(evidence){fs.writeFileSync(path.join(evidence,'display.png'),Buffer.from((await send('Page.captureScreenshot',{format:'png'})).data,'base64'));fs.writeFileSync(path.join(evidence,'saved.png'),png);}
  await click('generation-add');await until(()=>evaluate('!document.getElementById("label-form").hidden&&!document.getElementById("save").disabled'));
  const rows=await(await fetch('http://127.0.0.1:'+port+'/api/samples')).json();
  assert.equal(rows.length,1);assert.deepEqual(fs.readFileSync(path.join(temporary,'data','images',rows[0].id,'source')),png,'Collection preserves exact generated source bytes');
  assert.equal(await evaluate('document.getElementById("ai-settings").hidden'),false,'VLM controls remain available for generated sample');
  assert.deepEqual(errors,[],'No browser runtime exceptions');
  const result={fixture:false,gateway,model,prompt,seed:42,size:'512x512',duration_seconds:durationSeconds,metadata:response.metadata,displayed_width:512,saved_sha256:crypto.createHash('sha256').update(png).digest('hex'),collection_source_matches:true};
  if(evidence)fs.writeFileSync(path.join(evidence,'result.json'),JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify(result));
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(()=>{if(ws)ws.close();for(const child of children.reverse())child.kill('SIGTERM');setTimeout(()=>fs.rmSync(temporary,{recursive:true,force:true}),300);});
