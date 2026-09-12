// Native browser smoke test. No npm dependencies.
const assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {spawn}=require('node:child_process');
const root=path.resolve(__dirname,'..'),temporary=fs.mkdtempSync(path.join(os.tmpdir(),'tuldok-test-')),children=[];
let ws;
const pause=ms=>new Promise(resolve=>setTimeout(resolve,ms));
async function until(fn){for(let i=0;i<150;i++){const value=await fn();if(value)return value;await pause(100);}throw Error('Timed out');}
function launch(command,args,options={}){const child=spawn(command,args,options);children.push(child);return child;}
(async()=>{
  const server=launch('python3',['-u','tests/browser_server.py','--port','0','--data',path.join(temporary,'data')],{cwd:root,stdio:['ignore','pipe','pipe']});
  let output='',stderr='';server.stdout.on('data',data=>output+=data);server.stderr.on('data',data=>stderr+=data);
  const port=await until(()=>output.match(/127\.0\.0\.1:(\d+)/)?.[1]);
  launch(process.env.BROWSER||'/opt/brave.com/brave/brave',['--headless','--no-sandbox','--disable-gpu','--no-first-run','--no-default-browser-check','--remote-debugging-port=0','--window-size=1400,950','--user-data-dir='+path.join(temporary,'browser'),'about:blank'],{stdio:'ignore'});
  const active=path.join(temporary,'browser','DevToolsActivePort');
  const debugPort=await until(()=>fs.existsSync(active)&&fs.readFileSync(active,'utf8').split('\n')[0]);
  const tabs=await(await fetch('http://127.0.0.1:'+debugPort+'/json')).json();
  ws=new WebSocket(tabs[0].webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject;});
  let id=0;const pending=new Map(),errors=[];
  ws.onmessage=event=>{const message=JSON.parse(event.data);if(message.id){const task=pending.get(message.id);pending.delete(message.id);message.error?task.reject(message.error):task.resolve(message.result);}if(message.method==='Runtime.exceptionThrown')errors.push(message.params.exceptionDetails);};
  const send=(method,params={})=>new Promise((resolve,reject)=>{pending.set(++id,{resolve,reject});ws.send(JSON.stringify({id,method,params}));});
  const evaluate=async expression=>{const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value;};
  const click=id=>evaluate('document.getElementById('+JSON.stringify(id)+').click()');
  const fill=(id,value)=>evaluate('(()=>{const e=document.getElementById('+JSON.stringify(id)+');e.value='+JSON.stringify(value)+';e.dispatchEvent(new Event("input",{bubbles:true}));e.dispatchEvent(new Event("change",{bubbles:true}));})()');
  await send('Page.enable');await send('Runtime.enable');
  await send('Page.addScriptToEvaluateOnNewDocument',{source:`
    window.fixture=document.createElement('canvas');fixture.width=960;fixture.height=640;
    window.paint=(color='beige')=>{const c=fixture.getContext('2d');c.fillStyle='#4f6661';c.fillRect(0,0,960,640);c.fillStyle=color;c.fillRect(140,90,680,460);c.fillStyle='#424439';c.font='38px Georgia';c.fillText('A book for better data',250,220);c.font='19px Georgia';for(let y=300;y<500;y+=32)c.fillText('Four corners. A little patience. A useful dataset.',210,y);};paint();
    navigator.mediaDevices.getUserMedia=async()=>{const stream=fixture.captureStream(10);setInterval(()=>fixture.getContext('2d').drawImage(fixture,0,0),100);return stream;};
    navigator.mediaDevices.enumerateDevices=async()=>[];
    window.confirm=()=>true;
  `});
  await send('Page.navigate',{url:'http://127.0.0.1:'+port});
  await until(()=>evaluate('!!document.getElementById("capture-session")?.value'));
  await fill('capture-book','atlas-01');await fill('capture-session','desk-daylight');
  await click('start-camera');await until(()=>evaluate('!document.getElementById("capture").disabled'));
  assert.ok(await evaluate('(()=>{const v=document.getElementById("video").getBoundingClientRect(),r=document.getElementById("viewer").getBoundingClientRect();return v.width>0&&v.top>=r.top&&v.bottom<=r.bottom+1&&document.documentElement.scrollHeight<=innerHeight+1;})()'));
  await click('timer');await until(()=>evaluate('!document.getElementById("countdown").hidden'));await click('timer');
  assert.equal(await evaluate('document.getElementById("countdown").hidden'),true);
  await click('capture');await until(()=>evaluate('!document.getElementById("label-form").hidden&&!document.getElementById("save").disabled'));
  assert.equal(await evaluate('document.querySelectorAll("#overlay circle.unplaced").length'),4);
  await click('save');await until(()=>evaluate('document.getElementById("notice").textContent.includes("Place every visible")'));await click('notice');
  // Every unplaced marker can be selected directly, and release stops movement.
  for(let i=0;i<4;i++){
    const point=await evaluate('(()=>{const r=document.querySelectorAll("#overlay circle")['+i+'].getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2};})()');
    for(const type of ['mousePressed','mouseReleased'])await send('Input.dispatchMouseEvent',{type,...point,button:'left',clickCount:1});
    assert.equal(await evaluate('document.querySelectorAll("#overlay circle")['+i+'].classList.contains("unplaced")'),false,'Direct click places marker '+(i+1));
  }
  const before=await evaluate('document.getElementById("overlay").innerHTML');
  const blank=await evaluate('(()=>{const r=document.getElementById("overlay").getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2};})()');
  await send('Input.dispatchMouseEvent',{type:'mouseMoved',...blank,buttons:0});
  for(const type of ['mousePressed','mouseReleased'])await send('Input.dispatchMouseEvent',{type,...blank,button:'left',clickCount:1});
  assert.equal(await evaluate('document.getElementById("overlay").innerHTML'),before,'Released pins do not follow the cursor or unrelated clicks');
  await click('reset-points');
  await evaluate('document.querySelector("#corners button").click()');
  // Place book top-left directly over the bottom-right ghost marker.
  const ghost=await evaluate('(()=>{const r=document.querySelectorAll("#overlay circle")[2].getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2};})()');
  for(const type of ['mousePressed','mouseReleased'])await send('Input.dispatchMouseEvent',{type,...ghost,button:'left',clickCount:1});
  assert.equal(await evaluate('document.querySelectorAll("#overlay circle")[0].classList.contains("unplaced")'),false,'Selected book top-left must be placed over bottom-right placeholder');
  await click('reset-points');
  for(let i=0;i<4;i++)await evaluate('document.querySelectorAll("#overlay circle")['+i+'].dispatchEvent(new KeyboardEvent("keydown",{key:"ArrowRight",bubbles:true}))');
  const bounds=await evaluate('(()=>{const r=document.getElementById("overlay").getBoundingClientRect();return {x:r.left+r.width*.151,y:r.top+r.height*.15,toX:r.left+r.width*.18,toY:r.top+r.height*.18};})()');
  for(const [type,x,y] of [['mousePressed',bounds.x,bounds.y],['mouseMoved',bounds.toX,bounds.toY],['mouseReleased',bounds.toX,bounds.toY]])await send('Input.dispatchMouseEvent',{type,x,y,button:'left',buttons:type==='mouseMoved'?1:undefined,clickCount:1});
  await fill('split','train');await click('save');await until(()=>evaluate('document.getElementById("save-status").textContent==="Saved"&&!document.getElementById("save").disabled'));
  const records=await(await fetch('http://127.0.0.1:'+port+'/api/samples')).json();
  assert.equal(records.length,1);assert.equal(records[0].annotation.book_present,true);assert.equal(records[0].split,'train');
  assert.ok(Math.abs(records[0].annotation.corners[0].x-.18)<.01);
  assert.equal(await evaluate('document.getElementById("corner-reference").value'),'book');
  await fill('corner-reference','image');
  for(const [i,x,y] of [[0,.85,.85],[1,.15,.85],[2,.15,.15],[3,.85,.15]]){
    const position=await evaluate('(()=>{const circle=document.querySelectorAll("#overlay circle")['+i+'].getBoundingClientRect(),r=document.getElementById("overlay").getBoundingClientRect();return {x:circle.left+circle.width/2,y:circle.top+circle.height/2,toX:r.left+r.width*'+x+',toY:r.top+r.height*'+y+'};})()');
    for(const [type,px,py] of [['mousePressed',position.x,position.y],['mouseMoved',position.toX,position.toY],['mouseReleased',position.toX,position.toY]])await send('Input.dispatchMouseEvent',{type,x:px,y:py,button:'left',buttons:type==='mouseMoved'?1:undefined,clickCount:1});
  }
  await click('save');await until(()=>evaluate('document.getElementById("save-status").textContent==="Saved"&&!document.getElementById("save").disabled'));
  const rotated=await(await fetch('http://127.0.0.1:'+port+'/api/samples')).json();
  assert.equal(rotated[0].annotation.corner_reference,'book');
  assert.ok(rotated[0].annotation.corners[0].x>.8&&rotated[0].annotation.corners[0].y>.8,'Book top-left can be at screen bottom-right');
  const savedRecords=async()=>await(await fetch('http://127.0.0.1:'+port+'/api/samples')).json();
  const suggest=async()=>{await click('suggest');await until(()=>evaluate('document.getElementById("save-status").textContent==="AI suggestion · unsaved"&&!document.getElementById("suggest").disabled'));};
  const saveAI=async()=>{await click('save');await until(()=>evaluate('document.getElementById("save-status").textContent==="Saved"&&!document.getElementById("save").disabled'));};
  await suggest();
  assert.ok((await savedRecords())[0].annotation.corners[0].x>.8,'Suggestion is not automatically saved');
  await saveAI();assert.equal((await savedRecords())[0].annotation.suggested_by.provider,'codex');
  await evaluate('document.getElementById("ai-settings").open=true');
  await fill('ai-provider','openrouter');await fill('ai-key','fixture-secret');await click('ai-refresh');
  await until(()=>evaluate('document.getElementById("ai-model").value==="corners-test"&&!document.getElementById("ai-refresh").disabled'));
  assert.equal(await evaluate('document.querySelectorAll("#ai-models option").length'),1);
  await suggest();await saveAI();assert.equal((await savedRecords())[0].annotation.suggested_by.provider,'openrouter');
  assert.ok(!(await evaluate('localStorage.getItem("tuldok-ai")')).includes('fixture-secret'));
  await fill('ai-provider','llamacpp');await fill('ai-url','http://127.0.0.1:'+output.match(/FIXTURE_LLM_PORT=(\d+)/)[1]);
  await fill('ai-model','invalid-corners');await click('suggest');
  await until(()=>evaluate('!document.getElementById("notice").hidden&&!document.getElementById("suggest").disabled'));
  assert.equal((await savedRecords())[0].annotation.suggested_by.provider,'openrouter');
  await click('notice');await fill('ai-model','corners-test');await suggest();await saveAI();
  assert.equal((await savedRecords())[0].annotation.suggested_by.provider,'llamacpp');
  await evaluate('document.getElementById("ai-settings").open=false');
  const screenshot=await send('Page.captureScreenshot',{format:'png'});fs.writeFileSync('/tmp/tuldok-desktop.png',Buffer.from(screenshot.data,'base64'));
  await click('camera-view');await evaluate('paint("#d5b2a1")');await pause(200);
  await click('timer');await until(()=>evaluate('!document.getElementById("label-form").hidden&&!document.getElementById("save").disabled'));
  await click('present-no');await fill('book-id','');await click('save-next');
  await until(()=>evaluate('document.getElementById("label-form").hidden'));
  const labeled=await(await fetch('http://127.0.0.1:'+port+'/api/samples')).json();
  assert.equal(labeled.length,2);assert.equal(labeled[1].annotation.book_present,false);assert.deepEqual(labeled[1].annotation.corners,[]);
  const exported=await fetch('http://127.0.0.1:'+port+'/api/export');assert.equal(exported.status,200);assert.equal(Buffer.from(await exported.arrayBuffer()).subarray(0,2).toString(),'PK');
  await evaluate('paint("#a1c1d5")');
  const data=await evaluate('fixture.toDataURL("image/png").split(",")[1]'),file=path.join(temporary,'import.png');fs.writeFileSync(file,Buffer.from(data,'base64'));
  const doc=await send('DOM.getDocument'),node=await send('DOM.querySelector',{nodeId:doc.root.nodeId,selector:'#import'});
  await send('DOM.setFileInputFiles',{nodeId:node.nodeId,files:[file]});
  await until(()=>evaluate('document.getElementById("view-title").textContent==="import.png"'));
  await send('Emulation.setDeviceMetricsOverride',{width:500,height:800,deviceScaleFactor:1,mobile:false});
  await pause(200);
  assert.ok(await evaluate('(()=>{const v=document.getElementById("image-stage").getBoundingClientRect(),r=document.getElementById("viewer").getBoundingClientRect();return v.width>0&&v.left>=r.left&&v.right<=r.right+1&&v.height<=r.height;})()'),'The image fits a narrow display');
  assert.equal(errors.length,0,JSON.stringify(errors));assert.equal(stderr,'',stderr);
  console.log('PASS: camera, timer, labels, validation, corner dragging, split metadata, negatives, export, import, responsive layout, all three AI providers and unsaved suggestions');
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(()=>{ws?.close();for(const child of children)child.kill('SIGTERM');setTimeout(()=>fs.rmSync(temporary,{recursive:true,force:true}),500);});
