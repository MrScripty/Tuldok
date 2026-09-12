const $=id=>document.getElementById(id);
const names=['top_left','top_right','bottom_right','bottom_left'];
const titles=['Top left','Top right','Bottom right','Bottom left'];
const defaults=[[.15,.15],[.85,.15],[.85,.85],[.15,.85]];
let samples=[],selected=null,annotation=null,active=0,dirty=false,busy=false,stream=null,timer=null,remaining=0,drag=null;
let placementArmed=false;
let dimensions=[4,3],mode='camera',noticeTimer;
const clone=value=>JSON.parse(JSON.stringify(value));
function notice(message){clearTimeout(noticeTimer);$('notice').textContent=message;$('notice').hidden=!message;if(message)noticeTimer=setTimeout(()=>notice(''),12000);}
$('notice').onclick=()=>notice('');
async function api(path,body){
  const response=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const value=await response.json();if(!response.ok)throw Error(value.error||'Request failed.');return value;
}
async function run(action){
  if(busy)return;busy=true;controls();
  try{return await action();}catch(error){notice(error.message);}finally{busy=false;controls();}
}
function controls(){
  $('capture').disabled=!stream||busy||remaining>0;
  $('timer').disabled=!stream||busy;
  $('start-camera').disabled=busy;
  for(const id of ['save','save-next'])$(id).disabled=!selected||busy;
  $('export').disabled=busy||!samples.some(s=>s.annotation);
  $('camera-view').disabled=busy;
  $('import').disabled=busy;
  $('suggest').disabled=busy||!selected||!$('ai-model').value.trim();
  document.querySelectorAll('#ai-settings input, #ai-settings select, #ai-settings button').forEach(element=>element.disabled=busy);
  document.querySelectorAll('#label-form input, #label-form select, #label-form button').forEach(element=>element.disabled=busy);
  if(annotation)$('suitable').disabled=busy||!annotation.book_present;
}
function remember(){localStorage.setItem('tuldok-capture',JSON.stringify({book_id:$('capture-book').value,session_id:$('capture-session').value}));}
try{const settings=JSON.parse(localStorage.getItem('tuldok-capture')||'{}');$('capture-book').value=settings.book_id||'';$('capture-session').value=settings.session_id||new Date().toISOString().slice(0,10)+'-desk';}catch{$('capture-session').value=new Date().toISOString().slice(0,10)+'-desk';}
$('capture-book').onchange=remember;$('capture-session').onchange=remember;
function captureMeta(){return {book_id:$('capture-book').value.trim(),session_id:$('capture-session').value.trim(),split:'unassigned'};}
async function reload(){samples=await api('/api/samples');renderList();controls();}
function renderList(){
  const labeled=samples.filter(s=>s.annotation).length;
  $('counts').textContent=labeled+' labeled · '+(samples.length-labeled)+' remaining';
  $('samples').replaceChildren();
  const filter=$('filter').value;
  for(const sample of samples.filter(s=>filter==='all'||(filter==='labeled')===!!s.annotation)){
    const button=document.createElement('button');button.className='sample'+(sample.annotation?' labeled':'')+(selected?.id===sample.id?' active':'');
    button.dataset.id=sample.id;button.title=sample.filename;
    const image=document.createElement('img');image.src='/api/thumb/'+sample.id;image.alt='';image.loading='lazy';
    const copy=document.createElement('span');copy.className='sample-copy';
    const strong=document.createElement('strong');strong.textContent=sample.book_id||'No book ID';
    const small=document.createElement('small');small.textContent=(sample.annotation?(sample.annotation.book_present?'Labeled':'No book'):'Needs labels')+' · '+sample.filename;
    copy.append(strong,small);const dot=document.createElement('span');dot.className='dot';
    button.append(image,copy,dot);button.onclick=()=>{if(!busy)run(()=>select(sample));};$('samples').append(button);
  }
}
$('filter').onchange=renderList;
function canLeave(){return !dirty||confirm('Discard the unsaved changes to this label?');}
function fit(){
  const viewer=$('viewer'),style=getComputedStyle(viewer),width=viewer.clientWidth-parseFloat(style.paddingLeft)-parseFloat(style.paddingRight),height=viewer.clientHeight-parseFloat(style.paddingTop)-parseFloat(style.paddingBottom);
  const scale=Math.min(width/dimensions[0],height/dimensions[1]);
  const stage=$(mode==='camera'?'camera-stage':'image-stage');
  stage.style.width=Math.max(1,dimensions[0]*scale)+'px';stage.style.height=Math.max(1,dimensions[1]*scale)+'px';
  if(mode==='label'&&annotation)renderOverlay();
}
new ResizeObserver(fit).observe($('viewer'));
function setMode(next){
  mode=next;cancelTimer();
  $('camera-stage').hidden=next!=='camera';$('image-stage').hidden=next!=='label';
  $('capture-actions').hidden=next!=='camera';$('label-actions').hidden=next!=='label';
  $('label-form').hidden=next!=='label';
  fit();controls();
}
function showCamera(){
  if(!canLeave())return;
  selected=null;dirty=false;dimensions=[$('video').videoWidth||4,$('video').videoHeight||3];
  $('view-title').textContent='Camera';$('dimensions').textContent='';
  setMode('camera');renderList();
}
$('camera-view').onclick=showCamera;
function emptyAnnotation(){return {book_present:true,crop_suitable:true,corner_reference:'book',corners:names.map(name=>({name,visibility:'visible',x:null,y:null}))};}
async function select(sample){
  if(!canLeave())return;
  selected=sample;dirty=false;active=0;placementArmed=false;drag=null;annotation=clone(sample.annotation||emptyAnnotation());
  if(!annotation.book_present)annotation.corners=emptyAnnotation().corners;
  $('book-id').value=sample.book_id;$('session-id').value=sample.session_id;$('split').value=sample.split;
  $('view-title').textContent=sample.filename;$('dimensions').textContent=sample.width+' × '+sample.height;
  $('save-status').textContent=sample.annotation?'Saved':'Not labeled';
  dimensions=[sample.width,sample.height];$('source').src='/api/image/'+sample.id;
  setMode('label');renderAnnotation();renderList();
}
function changed(){dirty=true;$('save-status').textContent='Unsaved changes';}
for(const id of ['book-id','session-id','split'])$(id).oninput=changed;
$('label-form').onsubmit=e=>e.preventDefault();
function renderAnnotation(){
  $('corner-reference').value=annotation.corner_reference;
  $('present-yes').setAttribute('aria-pressed',String(annotation.book_present));
  $('present-no').setAttribute('aria-pressed',String(!annotation.book_present));
  $('suitable').checked=annotation.crop_suitable;$('suitable').disabled=!annotation.book_present;
  $('corners').hidden=!annotation.book_present;$('reset-points').hidden=!annotation.book_present;
  renderCorners();renderOverlay();
}
function renderCorners(){
  $('corners').replaceChildren();
  annotation.corners.forEach((corner,i)=>{
    const row=document.createElement('div');row.className='corner-row'+(active===i?' active':'');
    const button=document.createElement('button');button.type='button';button.textContent=i+1;button.setAttribute('aria-label','Select '+titles[i].toLowerCase()+' corner');
    button.onclick=()=>{active=i;placementArmed=true;renderCorners();renderOverlay();};
    const label=document.createElement('label');label.textContent=titles[i];
    const select=document.createElement('select');select.setAttribute('aria-label',titles[i]+' visibility');
    for(const [value,text] of [['visible','Visible'],['occluded','Hidden by a hand or object'],['out_of_frame','Outside the frame']]){
      const option=document.createElement('option');option.value=value;option.textContent=text;select.append(option);
    }
    select.value=corner.visibility;
    select.onchange=()=>{
      corner.visibility=select.value;corner.x=null;corner.y=null;
      if(select.value!=='visible')annotation.crop_suitable=false;
      changed();renderAnnotation();
    };
    const coordinates=document.createElement('small');
    coordinates.textContent=corner.visibility!=='visible'?'No coordinates recorded':corner.x===null?'Click to place':(corner.x*100).toFixed(1)+'%, '+(corner.y*100).toFixed(1)+'%';
    label.append(select,coordinates);row.append(button,label);$('corners').append(row);
  });
}
function svgElement(tag,attributes){
  const element=document.createElementNS('http://www.w3.org/2000/svg',tag);
  for(const [key,value] of Object.entries(attributes))element.setAttribute(key,value);
  return element;
}
function renderOverlay(){
  const svg=$('overlay'),svgHeight=1000*dimensions[1]/dimensions[0];
  svg.setAttribute('viewBox','0 0 1000 '+svgHeight);
  const radius=Math.max(16,12000/($('image-stage').getBoundingClientRect().width||500));
  svg.replaceChildren();if(!annotation?.book_present)return;
  if(annotation.corners.every(c=>c.visibility==='visible'&&c.x!==null)){
    svg.append(svgElement('polygon',{points:annotation.corners.map(c=>c.x*1000+','+c.y*svgHeight).join(' ')}));
  }
  annotation.corners.forEach((corner,i)=>{
    if(corner.visibility!=='visible')return;
    const x=(corner.x??defaults[i][0])*1000,y=(corner.y??defaults[i][1])*svgHeight;
    svg.append(svgElement('circle',{cx:x,cy:y,r:radius,tabindex:0,role:'button','aria-label':titles[i]+' corner','data-corner':i,class:(active===i?'selected ':'')+(corner.x===null?'unplaced':'')}));
    const text=svgElement('text',{x,y});text.style.fontSize=radius*1.2+'px';text.textContent=i+1;svg.append(text);
  });
}
function place(i,x,y){
  const corner=annotation.corners[i];if(corner.visibility!=='visible')return;
  annotation.corner_reference='book';$('corner-reference').value='book';
  corner.x=Math.min(1,Math.max(0,x));corner.y=Math.min(1,Math.max(0,y));changed();renderCorners();renderOverlay();
}
function pointerPosition(event){
  const rect=$('overlay').getBoundingClientRect();return [(event.clientX-rect.left)/rect.width,(event.clientY-rect.top)/rect.height];
}
$('overlay').onpointerdown=event=>{
  if(busy||!annotation?.book_present)return;
  event.preventDefault();
  const index=event.target.dataset.corner;
  if(!placementArmed){
    if(index===undefined)return;
    active=Number(index);
  }
  placementArmed=false;
  if(annotation.corners[active].visibility!=='visible')return;
  drag=active;$('overlay').setPointerCapture(event.pointerId);place(active,...pointerPosition(event));
};
$('overlay').onpointermove=event=>{
  if(event.buttons===0){drag=null;return;}
  if(drag!==null)place(drag,...pointerPosition(event));
};
$('overlay').onpointerup=()=>{drag=null;};
$('overlay').onpointercancel=()=>{drag=null;};
$('overlay').onlostpointercapture=()=>{drag=null;};
$('overlay').onkeydown=event=>{
  const i=Number(event.target.dataset.corner),delta={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[event.key];
  if(busy||!delta||!Number.isInteger(i))return;
  event.preventDefault();active=i;
  const c=annotation.corners[i],step=event.shiftKey?.01:.001;
  place(i,(c.x??defaults[i][0])+delta[0]*step,(c.y??defaults[i][1])+delta[1]*step);
  $('overlay').querySelector('[data-corner="'+i+'"]')?.focus();
};
$('present-yes').onclick=()=>{annotation.book_present=true;changed();renderAnnotation();};
$('present-no').onclick=()=>{annotation.book_present=false;annotation.crop_suitable=false;changed();renderAnnotation();};
$('suitable').onchange=()=>{
  annotation.crop_suitable=$('suitable').checked;
  if(annotation.crop_suitable&&annotation.corners.some(c=>c.visibility!=='visible')){
    annotation.crop_suitable=false;notice('Mark all four corners visible before choosing a full crop.');
  }
  changed();renderAnnotation();
};
$('corner-reference').onchange=()=>{annotation.corner_reference=$('corner-reference').value;changed();};
$('reset-points').onclick=()=>{annotation.corner_reference='book';annotation.corners=emptyAnnotation().corners;active=0;placementArmed=false;drag=null;changed();renderAnnotation();};
async function save(next=false){
  if(!selected)return;
  const payload={book_id:$('book-id').value,session_id:$('session-id').value,split:$('split').value,revision:selected.revision,
    annotation:{...annotation,corners:annotation.book_present?annotation.corners:[]}};
  const saved=await api('/api/labels/'+selected.id,payload);
  dirty=false;selected=saved;$('save-status').textContent='Saved';await reload();
  if(next){
    const remaining=samples.find(s=>!s.annotation&&s.id!==saved.id);
    if(remaining)await select(remaining);else showCamera();
  }
}
$('save').onclick=()=>run(()=>save());
$('save-next').onclick=()=>run(()=>save(true));
function navigate(direction){const index=samples.findIndex(s=>s.id===selected?.id),sample=samples[index+direction];if(sample)run(()=>select(sample));}
$('previous').onclick=()=>navigate(-1);$('next').onclick=()=>navigate(1);
async function startCamera(){
  if(stream){stopCamera();return;}
  if(!navigator.mediaDevices?.getUserMedia)throw Error('Camera access needs localhost or an HTTPS address. You can still import images.');
  let next;
  const preferred={width:{ideal:1920},height:{ideal:1080}};
  try{next=await navigator.mediaDevices.getUserMedia({video:$('devices').value?{...preferred,deviceId:{exact:$('devices').value}}:preferred,audio:false});}
  catch(error){
    if(!['OverconstrainedError','NotFoundError'].includes(error.name))throw error;
    next=await navigator.mediaDevices.getUserMedia({video:true,audio:false});
  }
  stream=next;
  try{
    $('video').srcObject=stream;await $('video').play();
    dimensions=[$('video').videoWidth,$('video').videoHeight];$('camera-empty').hidden=true;$('start-camera').textContent='Stop camera';
    const current=stream.getVideoTracks()[0].getSettings().deviceId;
    const devices=(await navigator.mediaDevices.enumerateDevices()).filter(d=>d.kind==='videoinput');
    $('devices').replaceChildren();
    devices.forEach(d=>{const option=document.createElement('option');option.value=d.deviceId;option.textContent=d.label||'Camera';$('devices').append(option);});
    $('devices').value=current;$('devices').hidden=devices.length<2;fit();
  }catch(error){stopCamera();throw error;}
}
function stopCamera(){
  cancelTimer();stream?.getTracks().forEach(track=>track.stop());stream=null;$('video').srcObject=null;
  $('camera-empty').hidden=false;$('start-camera').textContent='Start camera';controls();
}
$('start-camera').onclick=()=>run(startCamera);
$('devices').onchange=()=>run(async()=>{stopCamera();await startCamera();});
function cancelTimer(){clearInterval(timer);timer=null;remaining=0;$('countdown').hidden=true;$('timer').textContent='7s timer';controls();}
async function capture(){
  if(!stream||!$('video').videoWidth)throw Error('Start the camera first.');
  cancelTimer();const meta=captureMeta();
  if(!meta.session_id)throw Error('Enter a recording session ID first.');
  const canvas=document.createElement('canvas');canvas.width=$('video').videoWidth;canvas.height=$('video').videoHeight;
  canvas.getContext('2d').drawImage($('video'),0,0);
  const sample=await api('/api/samples',{...meta,filename:'capture-'+new Date().toISOString().replaceAll(':','-')+'.jpg',image:canvas.toDataURL('image/jpeg',.95).split(',')[1]});
  remember();await reload();await select(sample);
}
$('capture').onclick=()=>run(capture);
$('timer').onclick=()=>{
  if(remaining){cancelTimer();return;}
  if(!stream||busy)return;
  if(!captureMeta().session_id){notice('Enter a recording session ID first.');return;}
  const deadline=Date.now()+7000;remaining=7;$('countdown').textContent=remaining;$('countdown').hidden=false;$('timer').textContent='Cancel timer';controls();
  timer=setInterval(()=>{
    remaining=Math.max(0,Math.ceil((deadline-Date.now())/1000));$('countdown').textContent=remaining;
    if(!remaining){cancelTimer();run(capture);}
  },100);
};
function readFile(file){return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(Error('Could not read '+file.name));reader.readAsDataURL(file);});}
$('import').onchange=()=>run(async()=>{
  if(!canLeave()){$('import').value='';return;}
  const files=[...$('import').files],meta=captureMeta();let last,success=0,failures=[];
  if(!meta.session_id)throw Error('Enter a recording session ID first.');
  for(const file of files){
    try{
      if(file.size>25*1024*1024)throw Error('Larger than 25 MB.');
      last=await api('/api/samples',{...meta,filename:file.name,image:await readFile(file)});success++;
    }catch(error){failures.push(file.name+': '+error.message);}
  }
  $('import').value='';remember();dirty=false;await reload();if(last)await select(last);
  if(failures.length)notice(success+' imported. '+failures.join(' · '));
});
$('export').onclick=()=>run(async()=>{
  const response=await fetch('/api/export');
  if(!response.ok)throw Error((await response.json()).error);
  const url=URL.createObjectURL(await response.blob()),a=document.createElement('a');a.href=url;a.download='tuldok-dataset.zip';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
window.addEventListener('pagehide',stopCamera);
window.addEventListener('keydown',event=>{
  if(event.key==='Escape'){cancelTimer();return;}
  if(['INPUT','SELECT','TEXTAREA','BUTTON'].includes(document.activeElement?.tagName))return;
  if(event.code==='Space'&&mode==='camera'&&stream&&!busy&&!remaining){event.preventDefault();run(capture);}
  if(mode==='label'&&/^[1-4]$/.test(event.key)){active=Number(event.key)-1;placementArmed=true;renderCorners();renderOverlay();}
});

// Provider credentials stay in this page's password field, never browser storage.
let aiCatalog=[],aiConfig={},aiPreferences={};
function aiBody(){
  const provider=$('ai-provider').value;
  return {provider,model:$('ai-model').value.trim(),
    ...(provider==='codex'?{effort:$('ai-effort').value}:{}),
    ...(provider==='llamacpp'?{server_url:$('ai-url').value.trim()}:{}),
    ...(provider==='openrouter'?{api_key:$('ai-key').value}:{})};
}
function rememberAI(){
  const body=aiBody();
  aiPreferences[body.provider]={model:body.model,effort:body.effort,server_url:body.server_url};
  localStorage.setItem('tuldok-ai',JSON.stringify({provider:body.provider,providers:aiPreferences}));
  controls();
}
function renderEfforts(){
  const model=aiCatalog.find(item=>item.id===$('ai-model').value),old=$('ai-effort').value;
  const levels=model?.efforts||['low','medium','high','xhigh','max','ultra'];
  $('ai-effort').replaceChildren(...levels.map(level=>{const option=document.createElement('option');option.value=level;option.textContent=level;return option;}));
  $('ai-effort').value=levels.includes(old)?old:levels[0];
}
function renderModels(items){
  aiCatalog=items;$('ai-models').replaceChildren(...items.map(item=>{const option=document.createElement('option');option.value=item.id;option.label=item.name||item.id;return option;}));
  renderEfforts();
}
function chooseProvider(){
  const provider=$('ai-provider').value,prefs=aiPreferences[provider]||{};
  $('ai-url-row').hidden=provider!=='llamacpp';$('ai-key-row').hidden=provider!=='openrouter';$('ai-effort-row').hidden=provider!=='codex';
  $('ai-model').value=prefs.model||(provider==='codex'?aiConfig.default||'':'');
  $('ai-url').value=prefs.server_url||'http://127.0.0.1:8080';
  renderModels(provider==='codex'?aiConfig.models||[]:[]);
  if(prefs.effort&&[...$('ai-effort').options].some(option=>option.value===prefs.effort))$('ai-effort').value=prefs.effort;
  rememberAI();
}
async function initializeAI(){
  aiConfig=await api('/api/ai/config');
  try{
    const stored=JSON.parse(localStorage.getItem('tuldok-ai')||'{}');
    aiPreferences=stored.providers||{};
    if(['codex','openrouter','llamacpp'].includes(stored.provider))$('ai-provider').value=stored.provider;
  }catch{}
  $('ai-key').placeholder=aiConfig.openrouter_key_configured?'Configured on server':'API key or OPENROUTER_API_KEY on server';
  chooseProvider();
}
$('ai-provider').onchange=chooseProvider;
$('ai-model').oninput=()=>{renderEfforts();rememberAI();};
$('ai-effort').onchange=rememberAI;$('ai-url').onchange=rememberAI;
$('ai-refresh').onclick=()=>run(async()=>{
  const result=await api('/api/ai/models',aiBody());
  renderModels(result.models);
  if(!$('ai-model').value&&result.models.length)$('ai-model').value=result.models[0].id;
  renderEfforts();rememberAI();
  if(!result.models.length)notice('No compatible models found. Enter a vision model ID directly.');
});
$('suggest').onclick=()=>run(async()=>{
  const imageId=selected.id,revision=selected.revision,previousStatus=$('save-status').textContent;
  $('suggest').textContent='Suggesting…';$('save-status').textContent='Finding corners…';
  try{
    const result=await api('/api/ai/suggest',{...aiBody(),sample_id:imageId,revision});
    if(selected?.id!==imageId||selected.revision!==result.revision)return;
    annotation=result.annotation;
    if(!annotation.book_present)annotation.corners=emptyAnnotation().corners;
    active=0;changed();renderAnnotation();$('save-status').textContent='AI suggestion · unsaved';
  }catch(error){$('save-status').textContent=previousStatus;throw error;}
  finally{$('suggest').textContent='Suggest corners';}
});

await run(async()=>{await reload();await initializeAI();});fit();
