'use strict';
const $ = id => document.getElementById(id);
const selected = new Map();
let page = null, offset = 0, current = null, targets = [], dirty = false, queryEpoch = 0, editorEpoch = 0;
function notice(message, error = false) { $('notice').textContent = message; $('notice').classList.toggle('error', error); }
async function api(path, body) {
  const response = await fetch('/api/workbench/' + path, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  const result = await response.json();
  if (!response.ok) throw Error(result.error || 'Request failed.');
  return result;
}
function action(id, fn, event = 'click') {
  $(id).addEventListener(event, async e => {
    e.preventDefault();
    const control = e.currentTarget, buttons = control.matches('form') ? [...control.querySelectorAll('button,input,select,textarea')] : [control];
    if (control.dataset.busy) return;
    control.dataset.busy = 'true'; buttons.forEach(b => b.disabled = true);
    try { await fn(e); } catch (error) { notice(error.message, true); }
    finally { delete control.dataset.busy; buttons.forEach(b => b.disabled = false); if(page) pagination(); }
  });
}
function selection() { $('selection').textContent = selected.size + ' selected'; }
function pagination() { $('previous').disabled = offset === 0; $('next').disabled = offset + page.items.length >= page.total; }
async function refresh() {
  const epoch = ++queryEpoch;
  const params = new URLSearchParams({q:$('query').value, kind:$('kind').value, review:$('review-filter').value, sort:$('sort').value, offset, limit:40});
  const result = await api('records?' + params);
  if (epoch !== queryEpoch) return;
  page = result;
  $('records').replaceChildren();
  for (const record of page.items) {
    const row = document.createElement('div'); row.className = 'record';
    const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.checked = selected.has(record.id); checkbox.setAttribute('aria-label','Select ' + record.name);
    checkbox.onchange = () => { checkbox.checked ? selected.set(record.id, record) : selected.delete(record.id); selection(); };
    const button = document.createElement('button'); button.textContent = record.name;
    const detail = document.createElement('small'); detail.textContent = `${record.kind} · ${record.review.replaceAll('_',' ')} · revision ${record.revision}`; button.append(detail);
    button.onclick = () => openRecord(record.id).catch(error => notice(error.message, true));
    row.append(checkbox, button); $('records').append(row);
  }
  const a = page.analysis;
  $('analysis').textContent = `${a.records} records · ${a.unlabeled} unlabeled · ${a.protected_groups} protected groups · ${a.duplicate_content_records} exact duplicates · ${a.unknown_rights} unknown rights. Labels: ${Object.entries(a.labels).map(([k,v])=>`${k} (${v})`).join(', ') || 'none'}. Exact matching only; balance is not coverage.`;
  $('page').textContent = page.total ? `${offset + 1}–${Math.min(offset + 40,page.total)} of ${page.total}` : 'No records';
  pagination(); selection();
}
function markDirty() { dirty = true; ++editorEpoch; }
function mayDiscard() { return !dirty || confirm('Discard unsaved annotation edits?'); }
async function openRecord(id, force = false) {
  if (!force && ($('editor').dataset.busy || !mayDiscard())) return;
  const epoch = ++editorEpoch;
  const record = await api('records/' + id);
  if (epoch !== editorEpoch) return;
  showRecord(record);
}
function showRecord(record) {
  current = record; dirty = false; drag = null;
  $('editor').hidden = false; $('empty-editor').hidden = true; $('record-name').textContent = record.name;
  $('asset-image').hidden = record.kind !== 'image'; $('asset-text').hidden = record.kind !== 'text';
  if(record.kind === 'image') $('asset-image').src = '/api/workbench/asset/' + record.id + '?revision=' + record.source_revision;
  $('asset-text').textContent = record.text || '';
  $('task').replaceChildren();
  for(const task of record.kind === 'image' ? ['image_detection','image_classification'] : ['text_classification','text_entities']) {
    const option = document.createElement('option'); option.value = task; option.textContent = task.replaceAll('_',' '); $('task').append(option);
  }
  $('task').value = record.task; $('label').value = record.annotation?.label || 'object';
  targets = structuredClone(record.annotation?.boxes || record.annotation?.spans || []);
  $('groups').value = record.groups.join('\n'); $('record-review').value = record.review === 'human_reviewed' ? 'human_reviewed' : 'draft';
  $('record-provenance').textContent = `Saved evidence: ${record.review.replaceAll('_',' ')}. Source: ${JSON.stringify(record.provenance)}. Saving an edit requires a new review decision.`;
  $('history-output').hidden = true; renderTargets(); notice('Record loaded.');
}
function renderTargets() {
  const task = $('task').value;
  $('classification-help').hidden = !task.endsWith('_classification'); $('detection-controls').hidden = task !== 'image_detection'; $('entity-controls').hidden = task !== 'text_entities';
  $('targets').replaceChildren();
  $('box-overlay').replaceChildren();
  if(current?.kind === 'image' && task === 'image_detection'){
    $('box-overlay').setAttribute('viewBox',`0 0 ${current.width} ${current.height}`);
    for(const box of targets){const rect=document.createElementNS('http://www.w3.org/2000/svg','rect');for(const key of ['x','y','width','height'])rect.setAttribute(key,box[key]);$('box-overlay').append(rect);}
  }
  if(task.endsWith('_classification')) return;
  targets.forEach((target,index)=>{
    const li = document.createElement('li'); li.textContent = JSON.stringify(target);
    const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = 'Remove'; remove.setAttribute('aria-label','Remove target ' + (index+1));
    remove.onclick = () => { targets.splice(index,1); markDirty(); renderTargets(); };
    li.append(remove); $('targets').append(li);
  });
}
$('editor').addEventListener('input',()=>markDirty());
$('task').addEventListener('change',()=>{targets=[];markDirty();renderTargets();});
action('filters',async()=>{offset=0;await refresh();notice('Collection updated.');},'submit');
action('previous',async()=>{offset=Math.max(0,offset-40);await refresh();});
action('next',async()=>{offset+=40;await refresh();});
action('select-page',()=>{for(const row of page.items) selected.set(row.id,row); return refresh();});
action('clear-selection',()=>{selected.clear();return refresh();});
action('reload',async()=>{if(current && mayDiscard()) await openRecord(current.id,true);});
action('history',async()=>{const epoch=editorEpoch;const history=await api('history/'+current.id);if(epoch!==editorEpoch)return;$('history-output').textContent=JSON.stringify(history,null,2);$('history-output').hidden=false;});
action('add-box',()=>{targets.push({label:$('label').value,x:Number($('box-x').value),y:Number($('box-y').value),width:Number($('box-width').value),height:Number($('box-height').value)});markDirty();renderTargets();});
function addSpan(start,end) { if(!Number.isInteger(start)||!Number.isInteger(end)||start<0||end<=start||end>Array.from(current.text).length) throw Error('Choose a nonempty span inside the text.'); targets.push({label:$('label').value,start,end});markDirty();renderTargets(); }
action('add-offset-span',()=>addSpan(Number($('span-start').value),Number($('span-end').value)));
action('add-span',()=>{
  const selection = window.getSelection();
  if(!selection.rangeCount || !selection.toString()) throw Error('Select text in the source first.');
  const range = selection.getRangeAt(0), source = $('asset-text');
  if(!source.contains(range.startContainer)||!source.contains(range.endContainer)) throw Error('Select only source text.');
  const before = document.createRange(); before.selectNodeContents(source); before.setEnd(range.startContainer,range.startOffset);
  const start = Array.from(before.toString()).length; addSpan(start,start+Array.from(range.toString()).length);
});
let drag = null;
$('asset-image').addEventListener('pointerdown',event=>{
  if($('task').value!=='image_detection')return;
  const r=event.currentTarget.getBoundingClientRect();
  drag={x:(event.clientX-r.left)*current.width/r.width,y:(event.clientY-r.top)*current.height/r.height};event.currentTarget.setPointerCapture(event.pointerId);event.preventDefault();
});
$('asset-image').addEventListener('pointerup',event=>{
  if(!drag)return; const r=event.currentTarget.getBoundingClientRect();
  const x=Math.max(0,Math.min(current.width,(event.clientX-r.left)*current.width/r.width)),y=Math.max(0,Math.min(current.height,(event.clientY-r.top)*current.height/r.height));
  $('box-x').value=Math.floor(Math.min(drag.x,x));$('box-y').value=Math.floor(Math.min(drag.y,y));$('box-width').value=Math.ceil(Math.max(drag.x,x)) - Number($('box-x').value);$('box-height').value=Math.ceil(Math.max(drag.y,y)) - Number($('box-y').value);drag=null;
  markDirty();
  notice('Box coordinates captured. Choose its label and add the box.');
});
$('asset-image').addEventListener('pointercancel',()=>drag=null);
action('editor',async()=>{
  const record=current, task=$('task').value, epoch=++editorEpoch;
  const annotation=task.endsWith('_classification')?{label:$('label').value}:{[task==='image_detection'?'boxes':'spans']:targets};
  const saved=await api('records/'+record.id,{revision:record.revision,source_revision:record.source_revision,task,annotation,groups:$('groups').value.split('\n').map(x=>x.trim()).filter(Boolean),review:$('record-review').value});
  if(selected.has(saved.id))selected.set(saved.id,saved);
  if(epoch===editorEpoch)showRecord(saved);
  await refresh();notice('Annotation saved.');
},'submit');
action('import-form',async()=>{
  if(!mayDiscard())return;
  const epoch=++editorEpoch;
  const file=$('import-image').files[0], text=$('import-text').value;
  if(file && text.trim())throw Error('Import an image or text, one at a time.');
  const body={kind:file?'image':'text',name:file?file.name:$('import-name').value,groups:[$('import-group').value],rights:$('rights').value,text};
  if(file){if(file.size>25*1024*1024)throw Error('Choose an image smaller than 25 MB.');body.image=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(Error('Image could not be read.'));reader.readAsDataURL(file);});}
  const record=await api('import',body);await refresh();
  if(epoch===editorEpoch)showRecord(record);
  notice('Record imported.');
},'submit');
action('generate-form',async()=>{
  const result=await api('generate',{recipe:$('recipe').value,seed:Number($('seed').value),count:Number($('count').value)});
  await refresh();notice(`${result.created.length} candidates created; ${result.rejected.length} rejected. Programmatic verification is not human review.`);
},'submit');
action('release-form',async()=>{
  const result=await api('releases',{items:[...selected.values()].map(({id,revision,source_revision})=>({id,revision,source_revision})),ratios:{train:Number($('train').value),validation:Number($('validation').value),test:Number($('test').value)},seed:Number($('split-seed').value)});
  const link=document.createElement('a');link.href=result.url;link.textContent=`Download ${result.records}-record frozen release`;link.download='';$('release-result').replaceChildren(link);
  notice('Release frozen. '+JSON.stringify(result.split_report.actual_counts));
},'submit');
window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
refresh().then(()=>notice('Collection ready.')).catch(error=>notice(error.message,true));
