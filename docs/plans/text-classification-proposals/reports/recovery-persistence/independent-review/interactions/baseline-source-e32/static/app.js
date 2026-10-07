const $=id=>document.getElementById(id);
const names=['top_left','top_right','bottom_right','bottom_left'];
const titles=['Top left','Top right','Bottom right','Bottom left'];
const defaults=[[.15,.15],[.85,.15],[.85,.85],[.15,.85]];
let samples=[],selected=null,annotation=null,active=0,dirty=false,busy=false,stream=null,timer=null,remaining=0,drag=null;
let placementArmed=false;
let dimensions=[4,3],mode='camera',noticeTimer;
let generationCatalog=[],generationPreferred='',generationState={jobs:[],entries:[]};
let promptCatalog=[],promptPreferred='',pollingGeneration=false,generationEpoch=0;
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
  for(const id of ['save','save-next','delete-image'])$(id).disabled=!selected||busy;
  $('export').disabled=busy||!samples.some(s=>s.annotation);
  $('camera-view').disabled=busy;
  $('generation-view').disabled=busy;
  const generating=generationState.jobs.some(job=>['preparing','generating','stopping'].includes(job.status));
  $('generate').disabled=busy||generating||!generationCatalog.some(item=>item.id===$('generation-model').value)||!$('generation-prompt').value.trim()||!$('generation-count').checkValidity()||($('generation-strategy').value==='varied'&&!$('prompt-model').value);
  document.querySelectorAll('#generation-jobs button').forEach(button=>button.disabled=busy||generating);
  $('generation-cancel').hidden=!generating;
  $('generation-cancel').disabled=busy||generationState.jobs.some(job=>job.status==='stopping');
  document.querySelectorAll('#generation-settings input, #generation-settings select, #generation-settings button, #generation-stage input, #generation-stage select, #generation-stage textarea').forEach(element=>element.disabled=busy||generating);
  $('generation-model').disabled=busy||generating||!generationCatalog.length;
  $('prompt-model').disabled=busy||generating||!promptCatalog.length;
  $('prompt-model-settings').hidden=$('generation-strategy').value!=='varied';
  $('import').disabled=busy;
  $('suggest').disabled=busy||!selected||!$('ai-model').value.trim();
  document.querySelectorAll('#ai-settings input, #ai-settings select, #ai-settings button').forEach(element=>element.disabled=busy);
  $('ai-model').disabled=busy||!aiCatalog.length;
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
  const queuedSamples=new Set(generationState.entries.map(entry=>entry.sample_id).filter(Boolean));
  const samplesById=new Map(samples.map(sample=>[sample.id,sample]));
  const entriesBySample=new Map(generationState.entries.map(entry=>[entry.sample_id,entry]));
  const gallery=[...samples.filter(sample=>!queuedSamples.has(sample.id)),...generationState.entries.filter(entry=>entry.status!=='deleted').map(entry=>samplesById.get(entry.sample_id)||entry)];
  for(const sample of gallery.filter(s=>filter==='all'||(filter==='labeled')===!!s.annotation)){
    if(!sample.filename){renderPromptEntry(sample);continue;}
    const button=document.createElement('button');button.className='sample'+(sample.annotation?' labeled':'')+(selected?.id===sample.id?' active':'');
    const entry=entriesBySample.get(sample.id);
    button.dataset.id=entry?.id||sample.id;button.dataset.sampleId=sample.id;button.title=entry?.prompt||sample.filename;
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
  if(mode==='generation')return;
  const scale=Math.min(width/dimensions[0],height/dimensions[1]);
  const stage=$(mode==='camera'?'camera-stage':mode==='generation'?'generation-stage':'image-stage');
  stage.style.width=Math.max(1,dimensions[0]*scale)+'px';stage.style.height=Math.max(1,dimensions[1]*scale)+'px';
  if(mode==='label'&&annotation)renderOverlay();
}
new ResizeObserver(fit).observe($('viewer'));
function setMode(next){
  mode=next;cancelTimer();
  $('camera-view').setAttribute('aria-pressed',String(next==='camera'));
  $('generation-view').setAttribute('aria-pressed',String(next==='generation'));
  $('camera-stage').hidden=next!=='camera';$('image-stage').hidden=next!=='label';
  $('capture-actions').hidden=next!=='camera';$('label-actions').hidden=next!=='label';
  $('label-form').hidden=next!=='label';
  $('generation-stage').hidden=next!=='generation';$('generation-actions').hidden=next!=='generation';
  $('generation-settings').hidden=next!=='generation';$('ai-settings').hidden=next==='generation';$('labels-heading').hidden=next==='generation';
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
  renderZoom();if(!annotation?.book_present){svg.replaceChildren();return;}
  // Keep pointer targets mounted so a drag cannot lose capture during redraw.
  for(const node of [...svg.children])if(node.tagName!=='circle')node.remove();
  for(const node of svg.querySelectorAll('circle'))if(annotation.corners[Number(node.dataset.corner)].visibility!=='visible')node.remove();
  if(annotation.corners.every(c=>c.visibility==='visible'&&c.x!==null)){
    svg.prepend(svgElement('polygon',{points:annotation.corners.map(c=>c.x*1000+','+c.y*svgHeight).join(' ')}));
  }
  annotation.corners.forEach((corner,i)=>{
    if(corner.visibility!=='visible')return;
    const x=(corner.x??defaults[i][0])*1000,y=(corner.y??defaults[i][1])*svgHeight;
    let target=svg.querySelector('[data-corner="'+i+'"]');
    if(!target){target=svgElement('circle',{});svg.append(target);}
    const attributes={cx:x,cy:y,r:radius,tabindex:0,role:'button','aria-label':titles[i]+' corner','data-corner':i,class:(active===i?'selected ':'')+(corner.x===null?'unplaced':'')};
    for(const [name,value] of Object.entries(attributes))target.setAttribute(name,value);
    const arm=radius*.75,gap=radius*.15;
    const cross=svgElement('path',{d:`M ${x-arm} ${y} H ${x-gap} M ${x+gap} ${y} H ${x+arm} M ${x} ${y-arm} V ${y-gap} M ${x} ${y+gap} V ${y+arm}`,class:'crosshair'+(active===i?' selected':'')+(corner.x===null?' unplaced':'')});
    svg.append(cross.cloneNode(),cross);cross.classList.add('ink');
    const text=svgElement('text',{x:x+radius,y:y-radius});text.style.fontSize=radius*1.2+'px';text.textContent=i+1;svg.append(text);
  });
}
// Magnify original pixels, never the scaled image or its annotation overlay.
function renderZoom(){
  const canvas=$('corner-zoom'),source=$('source'),corner=annotation?.corners[drag];
  if(drag===null||!annotation?.book_present||!corner||!source.complete||!source.naturalWidth){canvas.hidden=true;return;}
  const {width,height}=$('image-stage').getBoundingClientRect();
  const x=corner.x??defaults[drag][0],y=corner.y??defaults[drag][1];
  const distances={left:x*width,right:(1-x)*width,top:y*height,bottom:(1-y)*height};
  // Keep the panel stable unless the marker enters its third of the image.
  let side=canvas.dataset.side;
  if(canvas.hidden||!side||({left:x<1/3,right:x>2/3,top:y<1/3,bottom:y>2/3})[side]){
    side=Object.keys(distances).reduce((a,b)=>distances[a]>distances[b]?a:b);
  }
  canvas.dataset.side=side;canvas.hidden=false;
  const vertical=side==='left'||side==='right',w=vertical?width/3:width,h=vertical?height:height/3;
  const ratio=window.devicePixelRatio||1;
  canvas.width=Math.max(1,Math.round(w*ratio));canvas.height=Math.max(1,Math.round(h*ratio));
  const ctx=canvas.getContext('2d');ctx.setTransform(ratio,0,0,ratio,0,0);
  ctx.fillStyle='#303b35';ctx.fillRect(0,0,w,h);ctx.imageSmoothingEnabled=false;
  const scale=6;
  ctx.drawImage(source,w/2-(x*(source.naturalWidth-1)+.5)*scale,h/2-(y*(source.naturalHeight-1)+.5)*scale,source.naturalWidth*scale,source.naturalHeight*scale);
  ctx.beginPath();ctx.moveTo(w/2-18,h/2);ctx.lineTo(w/2-3,h/2);ctx.moveTo(w/2+3,h/2);ctx.lineTo(w/2+18,h/2);
  ctx.moveTo(w/2,h/2-18);ctx.lineTo(w/2,h/2-3);ctx.moveTo(w/2,h/2+3);ctx.lineTo(w/2,h/2+18);
  ctx.strokeStyle='#302a20';ctx.lineWidth=4;ctx.stroke();ctx.strokeStyle='#ffe4a0';ctx.lineWidth=2;ctx.stroke();
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
  if(event.buttons===0){endDrag();return;}
  if(drag!==null)place(drag,...pointerPosition(event));
};
function endDrag(){drag=null;$('corner-zoom').hidden=true;}
$('overlay').onpointerup=endDrag;
$('overlay').onpointercancel=endDrag;
$('overlay').onlostpointercapture=endDrag;
window.addEventListener('blur',endDrag);
window.addEventListener('keydown',event=>{if(event.key==='Escape')endDrag();});
$('overlay').onkeydown=event=>{
  const i=Number(event.target.dataset.corner),delta={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[event.key];
  if(busy||!delta||!Number.isInteger(i))return;
  event.preventDefault();active=i;
  const c=annotation.corners[i],step=event.shiftKey?10:1;
  place(i,(c.x??defaults[i][0])+delta[0]*step/Math.max(1,dimensions[0]-1),(c.y??defaults[i][1])+delta[1]*step/Math.max(1,dimensions[1]-1));
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
$('delete-image').onclick=()=>run(async()=>{
  if(!selected)return;
  const deleting=selected,index=samples.findIndex(sample=>sample.id===deleting.id);
  if(!confirm('Permanently delete "'+deleting.filename+'" from the dataset? Its original image, thumbnail, saved label, and any unsaved edits will be removed.'))return;
  const result=await api('/api/samples/delete/'+deleting.id,{revision:deleting.revision});
  generationEpoch++;samples=result.samples;generationState={jobs:result.jobs,entries:result.entries};
  selected=null;annotation=null;dirty=false;drag=null;$('source').removeAttribute('src');$('corner-zoom').hidden=true;
  const next=samples[Math.min(index,samples.length-1)];
  if(next)await select(next);else if(deleting.generation)showGeneration();else showCamera();
  renderList();renderJobs();notice(result.warning||'Image deleted from the dataset.');
});
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
    ...(['llamacpp','pumas'].includes(provider)?{server_url:$('ai-url').value.trim()}:{}),
    ...(provider==='openrouter'?{api_key:$('ai-key').value}:{})};
}
function rememberAI(){
  const body=aiBody();
  aiPreferences[body.provider]={model:body.model||aiPreferences[body.provider]?.model||'',effort:body.effort,server_url:body.server_url};
  localStorage.setItem('tuldok-ai',JSON.stringify({provider:body.provider,providers:aiPreferences}));
  controls();
}
function renderEfforts(){
  const model=aiCatalog.find(item=>item.id===$('ai-model').value),old=$('ai-effort').value;
  const levels=model?.efforts||['low','medium','high','xhigh','max','ultra'];
  $('ai-effort').replaceChildren(...levels.map(level=>{const option=document.createElement('option');option.value=level;option.textContent=level;return option;}));
  $('ai-effort').value=levels.includes(old)?old:levels[0];
}
function renderModels(items,preferred=$('ai-model').value||aiPreferences[$('ai-provider').value]?.model){
  aiCatalog=items;
  const options=items.map(item=>{const option=document.createElement('option');option.value=item.id;option.textContent=item.name||item.id;return option;});
  if(!options.length){const option=document.createElement('option');option.value='';option.textContent='Refresh models to choose a model';options.push(option);}
  $('ai-model').replaceChildren(...options);
  $('ai-model').value=items.some(item=>item.id===preferred)?preferred:items[0]?.id||'';
  renderEfforts();
}
function chooseProvider(){
  const provider=$('ai-provider').value,prefs=aiPreferences[provider]||{};
  $('ai-url-row').hidden=!['llamacpp','pumas'].includes(provider);$('ai-pumas-row').hidden=provider!=='pumas';$('ai-key-row').hidden=provider!=='openrouter';$('ai-effort-row').hidden=provider!=='codex';
  $('ai-url-row').firstChild.textContent=provider==='pumas'?'Vision endpoint URL':'Server URL';
  $('ai-url').value=prefs.server_url||(provider==='pumas'?'':'http://127.0.0.1:8080');
  renderModels(provider==='codex'?aiConfig.models||[]:[],prefs.model||(provider==='codex'?aiConfig.default:''));
  if(prefs.effort&&[...$('ai-effort').options].some(option=>option.value===prefs.effort))$('ai-effort').value=prefs.effort;
  rememberAI();
}
async function initializeAI(){
  aiConfig=await api('/api/ai/config');
  try{
    const stored=JSON.parse(localStorage.getItem('tuldok-ai')||'{}');
    aiPreferences=stored.providers||{};
    if(['codex','openrouter','llamacpp','pumas'].includes(stored.provider))$('ai-provider').value=stored.provider;
  }catch{}
  $('ai-key').placeholder=aiConfig.openrouter_key_configured?'Configured on server':'API key or OPENROUTER_API_KEY on server';
  chooseProvider();
}
$('ai-provider').onchange=chooseProvider;
$('ai-model').onchange=()=>{renderEfforts();rememberAI();};
$('ai-effort').onchange=rememberAI;$('ai-url').onchange=()=>{renderModels([]);rememberAI();};
async function refreshAIModels(){
  const result=await api('/api/ai/models',aiBody());
  renderModels(result.models);
  renderEfforts();rememberAI();
  if(!result.models.length)notice('No compatible models found. Check the provider and server URL, then refresh models.');
}
$('ai-refresh').onclick=()=>run(refreshAIModels);
$('ai-scan').onclick=()=>run(async()=>{
  $('ai-scan-status').textContent='Scanning local ports…';$('ai-gateway-row').hidden=true;
  try{
    const result=await api('/api/ai/scan',{});
    $('ai-gateways').replaceChildren(new Option('Choose an endpoint',''),...result.endpoints.map(endpoint=>new Option(endpoint.server_url+' · '+endpoint.kind+' · '+endpoint.models+' models',endpoint.server_url)));
    $('ai-gateway-row').hidden=!result.endpoints.length;
    const current=result.endpoints.find(endpoint=>endpoint.server_url===$('ai-url').value.trim().replace(/\/v1\/?$|\/$/g,''));
    const focused=result.endpoints.filter(endpoint=>endpoint.kind==='model server'&&endpoint.models===1);
    const chosen=current||(focused.length===1?focused[0]:result.endpoints.length===1?result.endpoints[0]:null);
    $('ai-scan-status').textContent=result.message||(result.endpoints.length+' vision endpoint'+(result.endpoints.length===1?' found':'s found')+(chosen?' — selecting '+chosen.server_url:'. Choose an endpoint below.'));
    if(chosen){$('ai-gateways').value=chosen.server_url;await useAIGateway();}
  }catch(error){$('ai-scan-status').textContent=error.message;throw error;}
});
async function useAIGateway(){
  if(!$('ai-gateways').value)return;
  $('ai-url').value=$('ai-gateways').value;$('ai-url').onchange();
  await refreshAIModels();
}
$('ai-gateways').onchange=()=>run(useAIGateway);
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

// Jobs live on the server, so labeling and page reloads do not interrupt a dataset.
function rememberGeneration(){
  localStorage.setItem('tuldok-generation',JSON.stringify({server_url:$('generation-url').value.trim(),model:$('generation-model').value||generationPreferred,width:$('generation-width').value,height:$('generation-height').value,seed:$('generation-seed').value,prompt_url:$('prompt-url').value,prompt_model:$('prompt-model').value||promptPreferred,prompt:$('generation-prompt').value,count:$('generation-count').value,strategy:$('generation-strategy').value}));
}
try{
  const settings=JSON.parse(localStorage.getItem('tuldok-generation')||'{}');
  $('generation-url').value=settings.server_url||'';generationPreferred=settings.model||'';
  $('generation-width').value=settings.width??1280;$('generation-height').value=settings.height??720;
  $('generation-seed').value=settings.seed??'';$('prompt-url').value=settings.prompt_url||'';promptPreferred=settings.prompt_model||'';
  $('generation-prompt').value=settings.prompt||'';$('generation-count').value=settings.count||500;$('generation-strategy').value=settings.strategy||'varied';
}catch{}
function showGeneration(){
  if(!canLeave())return false;
  selected=null;dirty=false;stopCamera();
  $('view-title').textContent='';$('dimensions').textContent='';
  setMode('generation');renderList();return true;
}
$('generation-view').onclick=()=>{if(showGeneration())$('generation-entry-prompt').hidden=true;};
function renderPromptEntry(entry){
  const button=document.createElement('button');button.className='sample prompt-entry';button.dataset.id=entry.id;button.title=entry.prompt;
  const copy=document.createElement('span');copy.className='sample-copy';
  const strong=document.createElement('strong');strong.textContent=entry.prompt;
  const small=document.createElement('small');small.textContent='Image '+(entry.ordinal+1)+' · '+entry.status+(entry.error?' · '+entry.error:'');
  copy.append(strong,small);button.append(copy);
  button.onclick=()=>{if(!busy&&showGeneration()){$('generation-entry-prompt').textContent=entry.prompt;$('generation-entry-prompt').hidden=false;}};
  $('samples').append(button);
}
function renderJobs(){
  $('generation-jobs').replaceChildren();
  const active=generationState.jobs.find(job=>['preparing','generating','stopping'].includes(job.status));
  const shown=active??(generationState.jobs.length?generationState.jobs.at(-1):null);
  $('generation-status').textContent=shown?jobText(shown)+(shown.error?' · '+shown.error:''):'';
  for(const job of generationState.jobs){
    const row=document.createElement('div');row.className='generation-job';
    const text=document.createElement('p');text.textContent=jobText(job)+(job.error?' · '+job.error:'');row.append(text);
    if(['failed','cancelled','interrupted'].includes(job.status)){
      const resume=document.createElement('button');resume.textContent='Resume remaining images';resume.disabled=!!active||busy;
      resume.onclick=()=>run(async()=>{await api('/api/generation/jobs/resume',{job_id:job.id});await refreshGeneration();});row.append(resume);
    }
    $('generation-jobs').append(row);
  }
}
function jobText(job){
  const prepared=generationState.entries.filter(entry=>entry.job_id===job.id).length;
  const deleted=generationState.entries.filter(entry=>entry.job_id===job.id&&entry.status==='deleted').length;
  return job.completed+' / '+job.config.count+' images'+(deleted?' ('+deleted+' deleted)':'')+' · '+(job.status==='preparing'?prepared+' prompts prepared':job.status);
}
async function refreshGeneration(){
  if(pollingGeneration)return;
  pollingGeneration=true;const epoch=generationEpoch;
  try{
    const {samples:updatedSamples,...state}=await api('/api/generation/jobs');
    if(epoch!==generationEpoch)return;
    // Queue entries and saved images come from one consistent server snapshot.
    if(JSON.stringify(state)!==JSON.stringify(generationState)){
      samples=updatedSamples;generationState=state;renderList();renderJobs();controls();
    }
  }finally{pollingGeneration=false;}
}
function clearPromptCatalog(){promptCatalog=[];$('prompt-model').replaceChildren(new Option('Refresh models to choose',''));}
$('generation-url').onchange=()=>{
  generationCatalog=[];$('generation-model').replaceChildren(new Option('Refresh models to choose',''));if(!$('prompt-url').value.trim())clearPromptCatalog();rememberGeneration();controls();
};
$('prompt-url').onchange=()=>{clearPromptCatalog();rememberGeneration();controls();};
for(const id of ['generation-width','generation-height','generation-seed','generation-model','generation-count','generation-strategy','prompt-model'])$(id).onchange=()=>{rememberGeneration();controls();};
$('generation-count').oninput=controls;
$('generation-prompt').oninput=()=>{rememberGeneration();controls();};
$('generation-scan').onclick=()=>run(async()=>{
  $('gateway-scan-status').textContent='Scanning local ports…';$('gateway-results-row').hidden=true;
  try{
    const result=await api('/api/generation/scan',{});
    $('gateway-results').replaceChildren(new Option('Choose a gateway',''),...result.gateways.map(gateway=>new Option(gateway.server_url+' · '+gateway.image_models+' image models · '+gateway.models+' models total',gateway.server_url)));
    $('gateway-results-row').hidden=!result.gateways.length;
    const ready=result.gateways.filter(gateway=>gateway.image_models>0);
    const current=ready.find(gateway=>gateway.server_url===$('generation-url').value.trim().replace(/\/v1\/?$|\/$/g,''));
    const chosen=current||(ready.length===1?ready[0]:result.gateways.length===1?result.gateways[0]:null);
    const found=result.gateways.length+' Pumas gateway'+(result.gateways.length===1?' found':'s found');
    $('gateway-scan-status').textContent=result.message||found+(chosen?' — selecting '+chosen.server_url:'. Choose a gateway below.');
    if(chosen){
      $('gateway-results').value=chosen.server_url;await useDiscoveredGateway();
      $('gateway-scan-status').textContent=found+' — selected '+chosen.server_url+(chosen.image_models?' ('+chosen.image_models+' image models ready).':'. Load an image model in Pumas, then refresh models.');
    }
  }catch(error){$('gateway-scan-status').textContent=error.message;throw error;}
});
async function useDiscoveredGateway(){
  if(!$('gateway-results').value)return;
  $('generation-url').value=$('gateway-results').value;$('generation-url').onchange();
  await refreshImageModels();
  if(!$('prompt-url').value.trim())await refreshPromptModels();
}
$('gateway-results').onchange=()=>run(useDiscoveredGateway);
async function refreshImageModels(){
  const result=await api('/api/generation/models',{server_url:$('generation-url').value.trim()});generationCatalog=result.models;
  $('generation-model').replaceChildren(...result.models.map(item=>new Option(item.name,item.id)));
  if(result.models.some(item=>item.id===generationPreferred))$('generation-model').value=generationPreferred;
  if(!result.models.length)$('generation-model').append(new Option('No ready image models',''));
  $('generation-status').textContent=result.message||result.models.length+' image models ready';rememberGeneration();
}
$('generation-refresh').onclick=()=>run(refreshImageModels);
async function refreshPromptModels(){
  const result=await api('/api/generation/prompt-models',{server_url:$('prompt-url').value.trim()||$('generation-url').value.trim()});promptCatalog=result.models;
  $('prompt-model').replaceChildren(...result.models.map(item=>new Option(item.name,item.id)));
  if(result.models.some(item=>item.id===promptPreferred))$('prompt-model').value=promptPreferred;
  if(!result.models.length)$('prompt-model').append(new Option('No text models available',''));
  rememberGeneration();
}
$('prompt-refresh').onclick=()=>run(refreshPromptModels);
$('generate').onclick=()=>run(async()=>{
  const seed=$('generation-seed').value;
  await api('/api/generation/jobs',{...captureMeta(),server_url:$('generation-url').value.trim(),model:$('generation-model').value,
    prompt:$('generation-prompt').value,count:Number($('generation-count').value),strategy:$('generation-strategy').value,
    prompt_url:$('prompt-url').value.trim(),prompt_model:$('prompt-model').value,width:Number($('generation-width').value),height:Number($('generation-height').value),...(seed===''?{}:{seed:Number(seed)})});
  rememberGeneration();await refreshGeneration();
});
$('generation-cancel').onclick=()=>run(async()=>{
  const job=generationState.jobs.find(job=>['preparing','generating','stopping'].includes(job.status));
  if(job)await api('/api/generation/jobs/cancel',{job_id:job.id});await refreshGeneration();
});
await run(async()=>{await reload();await initializeAI();await refreshGeneration();});fit();
setInterval(()=>refreshGeneration().catch(error=>{$('generation-status').textContent='Could not refresh generation: '+error.message;}),1000);
