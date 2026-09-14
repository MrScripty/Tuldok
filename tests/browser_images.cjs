// Real browser and Tuldok HTTP workflow against a controlled image gateway.
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),crypto=require('node:crypto');
const {spawn}=require('node:child_process');
const root=path.resolve(__dirname,'..'),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-images-')),children=[];
const evidence=process.env.TULDOK_EVIDENCE_DIR; if(evidence)fs.mkdirSync(evidence,{recursive:true});
let ws;
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn){for(let i=0;i<200;i++){const value=await fn();if(value)return value;await pause(100);}throw Error('Timed out');}
function launch(command,args,options={}){const child=spawn(command,args,options);children.push(child);return child;}
(async()=>{
  const server=launch('python3',['-u','tests/browser_images_server.py','--port','0','--data',path.join(temporary,'data')],{cwd:root,stdio:['ignore','pipe','pipe']});
  let output='',stderr='';server.stdout.on('data',data=>output+=data);server.stderr.on('data',data=>stderr+=data);
  const port=await until(()=>output.match(/Tuldok: http:\/\/127\.0\.0\.1:(\d+)/)?.[1]);
  const gateway=await until(()=>output.match(/FIXTURE_IMAGE_URL=(\S+)/)?.[1]);
  launch(process.env.BROWSER||'/opt/brave.com/brave/brave',['--headless','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--window-size=1400,950','--user-data-dir='+path.join(temporary,'browser'),'about:blank'],{stdio:'ignore'});
  const active=path.join(temporary,'browser','DevToolsActivePort');
  const debugPort=await until(()=>fs.existsSync(active)&&fs.readFileSync(active,'utf8').split('\n')[0]);
  const tabs=await(await fetch('http://127.0.0.1:'+debugPort+'/json')).json();
  ws=new WebSocket(tabs[0].webSocketDebuggerUrl);await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  let id=0,loads=0;const pending=new Map(),errors=[];
  ws.onmessage=event=>{const message=JSON.parse(event.data);if(message.id){const task=pending.get(message.id);pending.delete(message.id);message.error?task.reject(message.error):task.resolve(message.result);}if(message.method==='Page.loadEventFired')loads++;if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails);};
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
  // Keep real backend discovery, then present a deterministic extra idle instance.
  // The only gateway with image models should be selected without a second click.
  await evaluate('window.originalFetch=window.fetch;window.fetch=async (...args)=>{const response=await window.originalFetch(...args);if(args[0]!=="/api/generation/scan")return response;const result=await response.json();const gateway=result.gateways.find(item=>item.server_url==='+JSON.stringify(gateway)+');if(!gateway)throw Error("Fixture gateway was not discovered");return new Response(JSON.stringify({gateways:[{server_url:"http://127.0.0.1:1",models:0,image_models:0},gateway],message:""}),{status:200,headers:{"Content-Type":"application/json"}});}');
  await click('generation-scan');
  await until(()=>evaluate('[...document.getElementById("gateway-results").options].some(option=>option.value==='+JSON.stringify(gateway)+')&&!document.getElementById("generation-scan").disabled'));
  assert.equal(await evaluate('document.getElementById("generation-url").value'),gateway,'An idle instance must not prevent selecting the only image gateway');
  assert.equal(await evaluate('document.getElementById("gateway-results").value'),gateway);
  await evaluate('window.fetch=window.originalFetch');
  await until(()=>evaluate('document.getElementById("generation-url").value==='+JSON.stringify(gateway)+'&&!document.getElementById("generation-scan").disabled'));

  await until(()=>evaluate('document.getElementById("generation-model").value==="image-test"'));
  assert.equal(await evaluate('document.getElementById("generation-model").options.length'),1,'Text/VLM model excluded from image selector');
  await fill('generation-size','512x512');await fill('generation-seed','20');await fill('generation-count','12');
  await click('prompt-refresh');await until(()=>evaluate('document.getElementById("prompt-model").value==="vision-only"&&!document.getElementById("prompt-refresh").disabled'));
  await fill('generation-prompt','photorealistic open books');await click('generate');
  await until(()=>evaluate('document.getElementById("generation-status").textContent.includes("12 / 12 images · completed")'));
  let rows=await(await fetch('http://127.0.0.1:'+port+'/api/samples')).json();
  assert.equal(rows.length,12);
  assert.equal(await evaluate('document.querySelectorAll(".sample").length'),12,'Prompts become image entries without duplicate cards');
  assert.equal(new Set(rows.map(row=>row.generation.prompt)).size,12);
  await evaluate('document.querySelector(".sample").click()');
  await until(()=>evaluate('!document.getElementById("label-form").hidden&&!document.getElementById("save").disabled'));
  assert.equal(await evaluate('document.getElementById("ai-settings").hidden'),false);
  await until(()=>evaluate('document.getElementById("source").naturalWidth===512'));
  await click('suggest');await until(()=>evaluate('document.getElementById("save-status").textContent.includes("suggestion")&&!document.getElementById("save").disabled'));
  await fill('book-id','synthetic-book');await click('save');
  await until(()=>evaluate('document.getElementById("save-status").textContent==="Saved"&&!document.getElementById("save").disabled'));
  await click('generation-view');await fill('generation-strategy','repeat');await fill('generation-prompt','slow');await fill('generation-count','500');await click('generate');
  await until(()=>evaluate('document.querySelectorAll(".prompt-entry").length===1'));
  const entryId=await evaluate('document.querySelector(".prompt-entry").dataset.id');
  const beforeReload=loads;await send('Page.reload');await until(()=>loads>beforeReload);
  await until(()=>evaluate('document.querySelectorAll(".prompt-entry").length===1'));
  assert.equal(await evaluate('document.querySelector(".prompt-entry").dataset.id'),entryId,'Pending gallery entry survives reload');
  await click('generation-view');await click('generation-cancel');
  await until(()=>evaluate('document.getElementById("generation-status").textContent.includes("cancelled")'));
  assert.equal(await evaluate('document.querySelectorAll(".prompt-entry").length'),1,'Repeat mode does not pre-create 500 entries');
  await until(async()=>{const requests=await(await fetch(gateway+'/requests')).json();return requests.some(item=>item.body.prompt==='slow'&&item.cancelled);});
  if(evidence)fs.writeFileSync(path.join(evidence,'fixture-display.png'),Buffer.from((await send('Page.captureScreenshot',{format:'png'})).data,'base64'));
  assert.deepEqual(errors,[],'No browser runtime exceptions');
  const result={fixture:true,generated_images:12,unique_prompts:12,ai_label_saved:true,queue_survives_reload:true,repeat_pending_entries:1,cancelled_backend_request:true};
  if(evidence)fs.writeFileSync(path.join(evidence,'result.json'),JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify(result));
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(()=>{if(ws)ws.close();for(const child of children.reverse())child.kill('SIGTERM');setTimeout(()=>fs.rmSync(temporary,{recursive:true,force:true}),300);});
