'use strict';
const $ = id => document.getElementById(id);
const selected = new Map();
let releasePreview = null, releaseKey = '', releaseEpoch = 0, releaseBusy = false;
let selectionEpoch = 0;
let page = null, offset = 0, current = null, targets = [], dirty = false, queryEpoch = 0, editorEpoch = 0;
function notice(message, error = false) { $('notice').textContent = message; $('notice').classList.toggle('error', error); }
async function api(path, body) {
  const response = await fetch(path.startsWith('/') ? path : '/api/workbench/' + path, body === undefined ? {} : {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});
  const result = await response.json();
  if (!response.ok) { const error=Error(result.error || 'Request failed.');error.status=response.status;throw error; }
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
function selection(intent = false) { if(intent) ++selectionEpoch; $('selection').textContent = selected.size + ' selected'; syncReleaseSelection(); if(typeof savedSelectionChanged === 'function') savedSelectionChanged(intent); if(typeof curationChanged === 'function') curationChanged(); }
function pagination() { $('previous').disabled = offset === 0; $('next').disabled = offset + page.items.length >= page.total; }
const exactFilters = [['label','Target label',80], ['group','Protected source/group',120], ['rights','Rights note',1000]];
let exactFilterFormat = 'text';
function exactFilterValue(key, name, format = $('exact-filter-format').value) {
  const value = $(key + '-filter').value;
  let decoded = value;
  if (format === 'json' && value.trim() !== '') {
    try { decoded = JSON.parse(value); } catch { decoded = null; }
    if(typeof decoded !== 'string') throw Error(`${name}: enter a JSON string in double quotes, or leave blank for any.`);
  }
  // Unicode-mode matching sees valid pairs as one codepoint, leaving only lone surrogates.
  if(/[\uD800-\uDFFF]/u.test(decoded)) throw Error(`${name}: unpaired surrogate characters are invalid Unicode.`);
  return decoded;
}
$('exact-filter-format').addEventListener('change', () => {
  const format = $('exact-filter-format').value;
  try {
    const values = exactFilters.map(([key,name]) => exactFilterValue(key,name,exactFilterFormat));
    if(format === 'text' && values.some(value => /[\r\n]/.test(value)))
      throw Error('Keep JSON string entry for values containing line breaks; plain inputs would lose them.');
    exactFilters.forEach(([key,,limit],i) => {
      const input = $(key + '-filter');
      input.maxLength = format === 'json' ? limit * 12 + 2 : limit * 2;
      input.value = format === 'json' && values[i] !== '' ? JSON.stringify(values[i]) : values[i];
    });
    exactFilterFormat = format;
  } catch(error) { $('exact-filter-format').value = exactFilterFormat; notice(error.message,true); }
});
async function refresh(isCurrent = () => true) {
  const params = new URLSearchParams({q:$('query').value, kind:$('kind').value, review:$('review-filter').value, sort:$('sort').value, task:$('task-filter').value,
    ...Object.fromEntries(exactFilters.map(([key,name]) => [key,exactFilterValue(key,name)])), offset, limit:40});
  const epoch = ++queryEpoch;
  if(typeof curationInvalidate === 'function') curationInvalidate('Collection query pending. Refresh diagnostics after it completes.', true);
  let result;
  try { result = await api('records?' + params); }
  finally { if(epoch === queryEpoch && typeof curationQueryFinished === 'function') curationQueryFinished(); }
  if (epoch !== queryEpoch || !isCurrent()) return;
  page = result;
  $('records').replaceChildren();
  for (const record of page.items) {
    const row = document.createElement('div'); row.className = 'record';
    const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.checked = selected.has(record.id); checkbox.setAttribute('aria-label','Select ' + record.name);
    checkbox.onchange = () => { checkbox.checked ? selected.set(record.id, record) : selected.delete(record.id); selection(true); };
    const button = document.createElement('button'); button.textContent = record.name;
    const detail = document.createElement('small'); detail.textContent = `${record.task.replaceAll('_',' ')} · ${record.review.replaceAll('_',' ')} · revision ${record.revision}`; button.append(detail);
    const metadata = document.createElement('small'); metadata.textContent = `Groups: ${record.groups.join(', ')} · Rights note: ${record.rights_note ?? 'unknown'}`; button.append(metadata);
    button.onclick = () => openRecord(record.id).catch(error => notice(error.message, true));
    row.append(checkbox, button); $('records').append(row);
  }
  const a = page.analysis;
  $('analysis').textContent = `${a.records} records · ${a.unlabeled} unlabeled · ${a.protected_groups} protected groups · ${a.duplicate_content_records} exact duplicates · ${a.unknown_rights} unknown rights. Labels: ${Object.entries(a.labels).map(([k,v])=>`${k} (${v})`).join(', ') || 'none'}. Exact matching only; balance is not coverage.`;
  $('page').textContent = page.total ? `${offset + 1}–${Math.min(offset + 40,page.total)} of ${page.total}` : 'No records';
  pagination(); selection();
}
function markDirty(resetReview = true) { dirty = true; ++editorEpoch; if(resetReview) $('record-review').value = 'draft'; }
function hasUnsavedEdits() { return dirty || (typeof rightsDirty !== 'undefined' && rightsDirty) || (typeof responseDirty !== 'undefined' && responseDirty) || (typeof preferenceDirty !== 'undefined' && preferenceDirty); }
function mayDiscard() { return !hasUnsavedEdits() || confirm('Discard unsaved annotation, rights-note, response or judgment edits?'); }
function responseIntentEpoch() { return `${typeof responseEditEpoch === 'undefined' ? '' : responseEditEpoch}/${typeof preferenceEditEpoch === 'undefined' ? '' : preferenceEditEpoch}`; }
async function openRecord(id, force = false) {
  if (!force && ($('editor').dataset.busy || !mayDiscard())) return;
  const epoch = ++editorEpoch, responseEpoch = responseIntentEpoch();
  const record = await api('records/' + id);
  // Parent replacement discards both editors; each owner must still match the request.
  if (epoch !== editorEpoch || responseEpoch !== responseIntentEpoch()) return;
  showRecord(record);
}
function showRecord(record) {
  current = record; dirty = false; drag = null;
  $('editor').hidden = false; $('empty-editor').hidden = true; $('record-name').textContent = record.name;
  $('asset-image').hidden = record.kind !== 'image'; $('asset-text').hidden = record.kind !== 'text';
  if(record.kind === 'image') $('asset-image').src = '/api/workbench/asset/' + record.id + '?revision=' + record.source_revision;
  $('asset-text').textContent = record.text || '';
  $('task').replaceChildren();
  for(const task of record.kind === 'image' ? ['image_detection','image_classification','image_caption'] : record.kind === 'sequence' ? ['sequence_transport'] : record.kind === 'mesh' ? ['mesh_geometry'] : ['text_classification','text_entities']) {
    const option = document.createElement('option'); option.value = task; option.textContent = task.replaceAll('_',' '); $('task').append(option);
  }
  $('task').value = record.task; $('caption').value = record.annotation?.caption || ''; $('label').value = record.annotation?.label || 'object';
  if(typeof sequenceShown === 'function') sequenceShown(record);
  if(typeof meshShown === 'function') meshShown(record);
  targets = structuredClone(record.annotation?.boxes || record.annotation?.spans || []);
  $('groups').value = record.groups.join('\n'); $('record-review').value = record.review === 'human_reviewed' ? 'human_reviewed' : 'draft';
  $('record-provenance').textContent = `Saved evidence: ${record.review.replaceAll('_',' ')}. Source: ${JSON.stringify(record.provenance)}. Saving an edit requires a new review decision.`;
  $('history-output').hidden = true; renderTargets();
  if(typeof rightsRecordShown === 'function') rightsRecordShown(record);
  if(typeof captionProposalsShown === 'function') captionProposalsShown(record);
  if(typeof textClassificationProposalsShown === 'function') textClassificationProposalsShown(record);
  if(typeof showResponses === 'function') showResponses(record);
  if(typeof showPreferences === 'function') showPreferences(record);
  notice('Record loaded.');
}
function renderTargets() {
  const task = $('task').value;
  $('caption-controls').hidden = task !== 'image_caption'; $('label-control').hidden = task === 'image_caption' || task === 'sequence_transport' || task === 'mesh_geometry';
  $('classification-help').hidden = !task.endsWith('_classification'); $('detection-controls').hidden = task !== 'image_detection'; $('entity-controls').hidden = task !== 'text_entities';
  $('targets').replaceChildren();
  $('box-overlay').replaceChildren();
  if(current?.kind === 'image' && task === 'image_detection'){
    $('box-overlay').setAttribute('viewBox',`0 0 ${current.width} ${current.height}`);
    for(const box of targets){const rect=document.createElementNS('http://www.w3.org/2000/svg','rect');for(const key of ['x','y','width','height'])rect.setAttribute(key,box[key]);$('box-overlay').append(rect);}
  }
  if(task.endsWith('_classification') || task === 'image_caption') return;
  targets.forEach((target,index)=>{
    const li = document.createElement('li'); li.textContent = JSON.stringify(target);
    const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = 'Remove'; remove.setAttribute('aria-label','Remove target ' + (index+1));
    remove.onclick = () => { targets.splice(index,1); markDirty(); renderTargets(); };
    li.append(remove); $('targets').append(li);
  });
}
$('editor').addEventListener('input',event=>markDirty(event.target?.id !== 'record-review'));
$('task').addEventListener('change',()=>{targets=[];markDirty();renderTargets();});
action('filters',async()=>{offset=0;await refresh();notice('Collection updated.');},'submit');
action('previous',async()=>{offset=Math.max(0,offset-40);await refresh();});
action('next',async()=>{offset+=40;await refresh();});
action('select-page',()=>{for(const row of page.items) selected.set(row.id,row); selection(true); return refresh();});
action('clear-selection',()=>{selected.clear();selection(true);return refresh();});
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
  if(typeof rightsDirty !== 'undefined' && rightsDirty) throw Error('Save or cancel the rights-note edit before saving an annotation.');
  if(typeof responseDirty !== 'undefined' && (responseDirty || responseBusy)) throw Error('Save or cancel the response edit before saving the annotation.');
  if(typeof captionProposalBusy !== 'undefined' && captionProposalBusy) throw Error('Wait for the caption action to finish before saving an annotation.');
  if(typeof textClassificationProposalBusy !== 'undefined' && textClassificationProposalBusy) throw Error('Wait for the classification action to finish before saving an annotation.');
  if(typeof preferenceDirty !== 'undefined' && (preferenceDirty || preferenceBusy)) throw Error('Save or cancel the judgment edit before saving the annotation.');
  const record=current, task=$('task').value, epoch=++editorEpoch, responseEpoch=responseIntentEpoch();
  const selectionAtSave=selectionEpoch, pairAtSave=selected.get(record.id);
  const annotation=task === 'mesh_geometry' ? {note:$('mesh-note').value} : task === 'sequence_transport' ? {note:$('sequence-note').value} : task === 'image_caption' ? {caption:$('caption').value} : task.endsWith('_classification')?{label:$('label').value}:{[task==='image_detection'?'boxes':'spans']:targets};
  const saved=await api('records/'+record.id,{revision:record.revision,source_revision:record.source_revision,task,annotation,groups:$('groups').value.split('\n').map(x=>x.trim()).filter(Boolean),review:$('record-review').value});
  // A later fixed-set open/reselection owns membership, even when IDs are unchanged.
  if(selectionAtSave===selectionEpoch && pairAtSave && selected.get(saved.id)===pairAtSave &&
     pairAtSave.revision===record.revision && pairAtSave.source_revision===record.source_revision) {
    selected.set(saved.id,saved);selection();
  }
  // A successful older save can prove retained fixed pairs stale without owning them.
  const selectedPair=selected.get(saved.id);
  if(selectedPair && (selectedPair.revision<saved.revision || selectedPair.source_revision<saved.source_revision)) invalidateRelease();
  if(epoch===editorEpoch && responseEpoch===responseIntentEpoch())showRecord(saved);
  await refresh();notice('Annotation saved.');
},'submit');
async function readImportImage(file) {
  if(file.size>25*1024*1024)throw Error('Choose an image at most 25 MiB.');
  return new Promise((resolve,reject)=>{
    const reader=new FileReader();
    reader.onload=()=>resolve(reader.result.split(',')[1]);
    reader.onerror=()=>reject(Error('Image could not be read.'));
    reader.readAsDataURL(file);
  });
}
action('import-form',async()=>{
  if(!mayDiscard())return;
  const epoch=++editorEpoch, responseEpoch=responseIntentEpoch();
  const file=$('import-image').files[0], text=$('import-text').value;
  if(file && text.trim())throw Error('Import an image or text, one at a time.');
  const body={kind:file?'image':'text',name:file?file.name:$('import-name').value,groups:[$('import-group').value],rights:$('rights').value,text};
  if(file)body.image=await readImportImage(file);
  const record=await api('import',body);await refresh();
  if(epoch===editorEpoch && responseEpoch===responseIntentEpoch())showRecord(record);
  notice('Record imported.');
},'submit');
action('generate-form',async()=>{
  const result=await api('generate',{recipe:$('recipe').value,seed:Number($('seed').value),count:Number($('count').value)});
  await refresh();notice(`${result.created.length} candidates created; ${result.rejected.length} rejected. Programmatic verification is not human review.`);
},'submit');
function releaseBody() {
  return {format:$('release-format').value || 'canonical_v1',
    items:[...selected.values()].map(({id,revision,source_revision})=>({id,revision,source_revision})).sort((a,b)=>a.id.localeCompare(b.id)),
    ratios:{train:Number($('train').value),validation:Number($('validation').value),test:Number($('test').value)},
    seed:Number($('split-seed').value)};
}
function releaseButtons() {
  const opening = typeof savedLoadBusy !== 'undefined' && savedLoadBusy;
  $('preview-release').disabled = releaseBusy || opening || !selected.size;
  $('freeze-release').disabled = releaseBusy || opening || !releasePreview?.eligible;
}
function invalidateRelease() {
  ++releaseEpoch; releasePreview = null;
  $('release-preview').replaceChildren();
  $('release-preview-status').textContent = selected.size ? 'Preview the saved selected revisions before exporting.' : 'Select records to preview a release.';
  $('release-result').replaceChildren(); releaseButtons();
}
function syncReleaseSelection() {
  const key = JSON.stringify(releaseBody());
  if(key !== releaseKey) { releaseKey = key; invalidateRelease(); }
  else releaseButtons();
}
function previewLine(parent, text) { const p=document.createElement('p');p.textContent=text;parent.append(p); }
function renderReleasePreview(result) {
  const root=$('release-preview');root.replaceChildren();
  $('release-preview-status').textContent = result.eligible ? `${result.selected_count} selected records are eligible for this format.` : 'Release blocked. Resolve the issues below, then preview again.';
  if(result.analysis) {
    const a=result.analysis, counts=(values,pretty=false)=>Object.entries(values).map(([key,value])=>`${pretty ? key.replaceAll('_',' ') : key}: ${value}`).join(' · ') || 'none';
    previewLine(root, 'Selected tasks: '+counts(a.tasks,true));
    previewLine(root, 'Selected review states: '+counts(a.reviews,true));
    previewLine(root, 'Selected class / target label counts: '+counts(a.labels));
    previewLine(root, `${a.unlabeled} unlabeled · ${a.empty_targets} empty targets · ${a.duplicate_content_records} exact duplicate records · ${a.unknown_rights} unknown rights`);
  }
  if(result.class_coverage) {
    for(const item of result.class_coverage) previewLine(root, `${JSON.stringify(item.label)} → ${item.folder} (index ${item.index}): `+Object.entries(item.counts).map(([split,count])=>`${split}: ${count}`).join(' · '));
  }
  for(const item of result.blockers) previewLine(root, (item.record_id ? item.record_id+': ' : '')+item.message);
  const report=result.split_report;
  if(report) {
    for(const split of ['train','validation','test']) {
      const count=report.actual_counts[split] || 0, percent=result.selected_count ? (100*count/result.selected_count).toFixed(1) : '0.0';
      previewLine(root, `${split}: requested ${report.requested_percentages[split]}%; achievable ${count} records (${percent}%).`);
    }
    previewLine(root, report.note);
  } else previewLine(root, 'No valid split allocation is available for these settings.');
  const families=document.createElement('details'), summary=document.createElement('summary');
  summary.textContent=`${result.lineage.length} connected lineage groups in this selection`;families.append(summary);
  for(const family of result.lineage) {
    previewLine(families, `${family.selected_ids.length} selected / ${family.member_ids.length} related records · ${family.deleted_ids.length} deleted sources · fixed splits: ${family.fixed_splits.join(', ') || 'none'}`);
    previewLine(families, 'Family '+family.id+' · members: '+family.member_ids.join(', '));
  }
  root.append(families);
  for(const warning of result.warnings) previewLine(root, 'Warning: '+warning);
  releaseButtons();
}
for(const id of ['release-format','train','validation','test','split-seed']) {
  for(const event of ['input','change']) $(id).addEventListener(event, syncReleaseSelection);
}
$('release-format').addEventListener('change',()=>{$('caption-export-help').hidden = $('release-format').value !== 'image_caption_v1';$('classification-export-help').hidden = $('release-format').value !== 'image_classification_v1';});
$('preview-release').addEventListener('click', async event=>{
  event.preventDefault(); if(releaseBusy) return;
  syncReleaseSelection();
  const body=releaseBody(), key=releaseKey, epoch=++releaseEpoch;
  releasePreview=null; releaseBusy=true; releaseButtons();
  $('release-preview').replaceChildren();$('release-result').replaceChildren();
  $('release-preview-status').textContent='Checking saved selection, source bytes and connected lineage…';
  try {
    const result=await api('releases/preview',body);
    if(epoch!==releaseEpoch || key!==JSON.stringify(releaseBody())) return;
    if(result.eligible && (typeof result.preview_token !== 'string' || !/^[a-f0-9]{64}$/.test(result.preview_token))) throw Error('Release preview proof is unavailable. Preview again.');
    renderReleasePreview(result);releasePreview=result;
  } catch(error) {
    if(epoch===releaseEpoch && key===JSON.stringify(releaseBody())) $('release-preview-status').textContent=error.message;
  } finally { releaseBusy=false;syncReleaseSelection(); }
});
$('release-form').addEventListener('submit',async event=>{
  event.preventDefault();if(releaseBusy)return;
  syncReleaseSelection();
  if(!releasePreview?.eligible) { $('release-preview-status').textContent='Preview an eligible selection before exporting.';return; }
  const body={...releaseBody(),preview_token:releasePreview.preview_token ?? null}, key=releaseKey, epoch=releaseEpoch;
  releaseBusy=true;releaseButtons();$('release-result').replaceChildren();
  try {
    const result=await api('releases',body);
    if(epoch!==releaseEpoch || key!==JSON.stringify(releaseBody())) return;
    const link=document.createElement('a');link.href=result.url;link.textContent=`Download ${result.records}-record frozen release`;link.download='';$('release-result').replaceChildren(link);
    notice('Release frozen. '+JSON.stringify(result.split_report.actual_counts)+(result.warnings?.length ? ' '+result.warnings.length+(result.format==='image_classification_v1'?' export warnings; inspect manifest.json.':' small-image warnings; inspect manifest.json.') : ''));
  } catch(error) {
    if(epoch===releaseEpoch && key===JSON.stringify(releaseBody())) {invalidateRelease();$('release-preview-status').textContent=error.message;notice(error.message,true);}
  } finally { releaseBusy=false;syncReleaseSelection(); }
});
window.addEventListener('beforeunload',event=>{if(hasUnsavedEdits()){event.preventDefault();event.returnValue='';}});
refresh().then(()=>notice('Collection ready.')).catch(error=>notice(error.message,true));

// Proposal requests own their refresh timer; polling ends at terminal state/page exit.
let groundedEpoch=0, modelEpoch=0, groundedTimer=null, groundedPaused=false, groundedRevision='';
const proposalNotes=new Map();
function groundedButton(label, fn) {
  const button=document.createElement('button');button.type='button';button.textContent=label;
  button.onclick=async()=>{if(button.disabled)return;button.disabled=true;try{await fn();}catch(error){notice(error.message,true);}finally{button.disabled=false;}};
  return button;
}
function renderGrounded(jobs) {
  const opened=new Set([...document.querySelectorAll('.proposal-job[open]')].map(element=>element.dataset.jobId));
  const active=document.activeElement, focus=active?.id?.startsWith('proposal-note-') ? {id:active.id,start:active.selectionStart,end:active.selectionEnd} : null;
  $('grounded-jobs').replaceChildren();
  for(const job of jobs) {
    const container=document.createElement('details');container.className='proposal-job';container.dataset.jobId=job.id;container.open=opened.has(job.id)||['preparing','generating','stopping'].includes(job.status);
    const summary=document.createElement('summary');summary.textContent=`${job.source.name} · ${job.status} · ${job.candidates.length} proposals`;container.append(summary);
    const status=document.createElement('p');status.textContent=`${job.config.model} · requested seed ${job.config.seed} · source revision ${job.source.revision}. ${job.error || job.verification}`;container.append(status);
    if(job.capability_observation){const metadata=document.createElement('pre');metadata.textContent=JSON.stringify({protocol:job.config.protocol,...job.capability_observation,request:job.canonical_request,producer_contract_source:job.producer_contract_source},null,2);container.append(metadata);}
    const source=document.createElement('pre');source.textContent=`Captured source (${job.source.annotation.label}):\n${job.source.text}`;container.append(source);
    if(['preparing','generating','stopping'].includes(job.status))container.append(groundedButton('Cancel request',async()=>{await api('grounded/cancel',{job_id:job.id});await refreshGrounded();}));
    for(const candidate of job.candidates) {
      const item=document.createElement('div');item.className='proposal-candidate';
      const text=document.createElement('pre');text.textContent=candidate.text;item.append(text);
      const target=document.createElement('p');target.textContent=`Proposed class: ${candidate.label}. State: ${candidate.status}.`;item.append(target);
      const evidence=document.createElement('pre');evidence.textContent='Exact source evidence:\n'+candidate.evidence.map(span=>`[${span.start},${span.end}): ${span.quote}`).join('\n');item.append(evidence);
      if(candidate.status==='pending_review') {
        const label=document.createElement('label');label.textContent='Review / admission note';const note=document.createElement('textarea');note.id='proposal-note-'+candidate.id;note.value=proposalNotes.get(candidate.id)||'';note.maxLength=1000;note.rows=2;note.oninput=()=>proposalNotes.set(candidate.id,note.value);label.append(note);item.append(label);
        const decide=async decision=>{await api('grounded/review/'+job.id,{revision:job.revision,candidate_id:candidate.id,decision,note:note.value});proposalNotes.delete(candidate.id);await refreshGrounded();await refresh();notice(decision==='reject'?'Candidate rejected and retained for audit.':'Candidate admitted as a draft. Open it and review the annotation before release.');};
        item.append(groundedButton('Admit as draft',()=>decide('admit_draft')),groundedButton('Reject candidate',()=>decide('reject')));
      } else {
        const note=document.createElement('p');note.textContent=candidate.review_note;item.append(note);
        if(candidate.record_id)item.append(groundedButton('Open admitted draft',()=>openRecord(candidate.record_id)));
      }
      container.append(item);
    }
    $('grounded-jobs').append(container);
  }
  if(focus){const note=$(focus.id);if(note){note.focus();note.setSelectionRange(focus.start,focus.end);}}
}
async function refreshGrounded() {
  clearTimeout(groundedTimer);const epoch=++groundedEpoch;
  const result=await api('grounded/jobs');if(epoch!==groundedEpoch||groundedPaused)return;
  const revision=result.jobs.map(job=>job.id+':'+job.revision).join(',');
  if(revision!==groundedRevision){renderGrounded(result.jobs);groundedRevision=revision;}
  if(result.jobs.some(job=>['preparing','generating','stopping'].includes(job.status)))groundedTimer=setTimeout(()=>refreshGrounded().catch(error=>notice(error.message,true)),1000);
}
$('grounded-url').addEventListener('input',()=>{++modelEpoch;$('grounded-model').replaceChildren();});
for(const id of ['grounded-protocol','grounded-profile'])for(const event of ['input','change'])$(id).addEventListener(event,()=>{++modelEpoch;});
action('grounded-models',async()=>{
  const epoch=++modelEpoch,url=$('grounded-url').value,settings=JSON.stringify([$('grounded-protocol').value,$('grounded-profile').value]);const result=await api($('grounded-protocol').value==='pumas_typed_v1'?'/api/generation/typed-models':'/api/generation/prompt-models',{server_url:url});
  if(settings!==JSON.stringify([$('grounded-protocol').value,$('grounded-profile').value]))return;
  if(epoch!==modelEpoch||url!==$('grounded-url').value)return;
  $('grounded-model').replaceChildren();for(const model of result.models){const option=document.createElement('option');option.value=model.id;option.textContent=model.name;$('grounded-model').append(option);}
  notice(result.models.length?result.qualification:'No listed non-image models. Load a text model in Pumas.');
});
action('grounded-form',async()=>{
  if(!current||dirty||current.kind!=='text'||current.task!=='text_classification'||current.review!=='human_reviewed')throw Error('Open and save a human-reviewed text-classification source first.');
  await api('grounded/jobs',{source_id:current.id,revision:current.revision,source_revision:current.source_revision,server_url:$('grounded-url').value,model:$('grounded-model').value,instruction:$('grounded-instruction').value,count:Number($('grounded-count').value),seed:$('grounded-protocol').value==='pumas_typed_v1'?null:Number($('grounded-seed').value),...(typeof pumasTypedSettings==='function'?pumasTypedSettings('grounded'):{})});
  await refreshGrounded();notice('Proposal request started. Outputs remain unreviewed candidates.');
},'submit');
action('grounded-refresh',refreshGrounded);
window.addEventListener('pagehide',()=>{groundedPaused=true;++groundedEpoch;clearTimeout(groundedTimer);});
window.addEventListener('pageshow',()=>{if(groundedPaused){groundedPaused=false;refreshGrounded().catch(error=>notice(error.message,true));}});
refreshGrounded().catch(error=>notice(error.message,true));
