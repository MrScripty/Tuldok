'use strict';
// Projects project server-owned references. Opening never admits an execution.
window.WorkspaceProjects = function ({select, roots, announce, switchSource, contextChanged, openCatalogRecord, openExternalGraph}) {
  const $=id=>document.getElementById(id), esc=value=>window.workspaceEscape(value);
  let active=null, view=null, detail=null, generation=0, controller=null, evidenceController=null;
  let importTarget=null, importing=false, importGeneration=0;
  let entries=[], aliases=[], listGeneration=0, opening=false, openGeneration=0;
  const externalCreator=WorkspaceExternalProject({onCreated:openExternalGraph,announce});
  const currentSource=()=>select.value;
  async function api(path, options={}) {
    const response=await (globalThis.TuldokAuth?.fetch || fetch)('/api/workspace/projects'+path,options), value=await response.json();
    if(!response.ok)throw Error(value.error||'Project inspection unavailable.');
    return value;
  }
  function populate() {
    const selected=currentSource();
    for(const option of [...select.options])if(option.value.startsWith('project:'))option.remove();
    for(const entry of entries){const option=document.createElement('option');option.value='project:'+entry.id;option.textContent=entry.name+' · project';select.append(option);}
    if(selected.startsWith('project:')&&!entries.some(entry=>'project:'+entry.id===selected)){
      const option=document.createElement('option');option.value=selected;option.textContent='Remembered project';select.append(option);
    }
    select.value=selected;
    const previous=$('project-root').value;$('project-root').replaceChildren();
    for(const alias of aliases){const option=document.createElement('option');option.value=alias;option.textContent=alias;$('project-root').append(option);}
    if(aliases.includes(previous))$('project-root').value=previous;
    $('project-open-submit').disabled=opening||!aliases.length;
    contextChanged();
  }
  async function refreshList() {
    const epoch=++listGeneration;
    try {
      const value=await api('');if(epoch!==listGeneration)return;
      if(value.mode!=='inspection'||!Array.isArray(value.roots)||!value.roots.every(alias=>typeof alias==='string')||!Array.isArray(value.projects))throw Error('Unsupported project catalog.');
      aliases=value.roots;entries=value.projects;populate();
      $('project-open-status').textContent=aliases.length?'Choose a configured root and its relative manifest path.':'No project roots configured by this local server.';
    }catch(error){if(epoch===listGeneration)$('project-open-status').textContent=error.message;}
  }
  function reference(item, category) {
    return `<li class="project-reference"><div><strong>${esc(item.label)}</strong><span class="badge ${item.status==='available'&&item.integrity==='verified'?'':'amber'}">${esc(item.status)} · ${esc(item.integrity)}</span></div><p class="project-path">${esc(item.path)}</p>${item.reason?`<p>${esc(item.reason)}</p>`:''}${item.bytes!==undefined?`<small>${esc(item.bytes)} bytes</small>`:''}${category==='data'?`<button type="button" data-project-import="${esc(item.id)}" ${item.status!=='available'||item.integrity==='mismatch'||!(/^[a-f0-9]{64}$/.test(item.observed_sha256||''))?'disabled':''}>Import fields</button>`:''}${category==='pipeline'?`<button type="button" data-project-recipe="${esc(item.id)}" ${item.status!=='available'||item.integrity==='mismatch'||!(/^[a-f0-9]{64}$/.test(item.observed_sha256||''))?'disabled':''}>Create execution graph</button>`:''}${category==='evidence'&&item.status==='available'?`<button type="button" data-project-evidence="${esc(item.id)}">Inspect external evidence</button>`:''}<details><summary>Reference identity</summary><pre>${esc(JSON.stringify({id:item.id,expected_sha256:item.sha256,observed_sha256:item.observed_sha256},null,2))}</pre></details></li>`;
  }
  function render() {
    if(!active||!view)return;
    const root=roots[view];
    if(!detail){root.innerHTML='<p role="status">Loading project references…</p>';return;}
    const changed=detail.manifest_status!=='unchanged';
    const items=view==='data'?detail.data:view==='pipeline'?detail.recipes:detail.evidence;
    const title=view==='data'?'Referenced data':view==='pipeline'?'Referenced recipes':'External evidence';
    const note=view==='data'?'Import supported scientific fields explicitly into the catalog. Saved project references remain unchanged.':view==='pipeline'?'Referenced files are not executable here. Inspect a declared recipe and explicitly create a saved execution graph. Preflight and material approval are required before execution.':'External evidence is not a Tuldok-completed run or scientific qualification.';
    root.innerHTML=`<div class="panel panel-pad project-header"><div><span class="eyebrow">PROJECT · INSPECTION ONLY</span><h2>${esc(detail.name)}</h2><p>${esc(detail.root)} / ${esc(detail.manifest_path)}</p></div><button type="button" class="project-refresh">Refresh references</button></div>${changed?`<p class="callout" role="status">Manifest ${esc(detail.manifest_status)}. Saved references remain unchanged; a different manifest requires a new project ID.</p>`:''}<section class="panel panel-pad"><h2>${title}</h2><p>${note}</p>${items.length?`<ul class="project-references">${items.map(item=>reference(item,view==='runs'?'evidence':view)).join('')}</ul>`:`<p class="muted">No ${title.toLowerCase()} declared.</p>`}</section>${view==='data'?`<section class="panel panel-pad"><h2>Runtime requirements</h2><p class="muted">Presence does not qualify a runtime.</p>${detail.requirements.length?`<ul class="project-references">${detail.requirements.map(item=>`<li><strong>${esc(item.label)}</strong><span class="badge amber">${esc(item.status)}</span>${item.path?`<p class="project-path">${esc(item.path)}</p>`:''}${item.reason?`<p>${esc(item.reason)}</p>`:''}</li>`).join('')}</ul>`:'<p class="muted">No requirements declared.</p>'}</section>`:''}<div class="project-evidence-output" aria-live="polite"></div><details class="project-identity"><summary>Saved manifest identity</summary><p class="project-path">${esc(detail.manifest_sha256)}</p><p>Execution: unsupported</p></details>`;
    root.querySelector('.project-refresh').onclick=()=>loadDetail(active,true);
    for(const button of root.querySelectorAll('[data-project-evidence]'))button.onclick=()=>loadEvidence(button.dataset.projectEvidence);
    for(const button of root.querySelectorAll('[data-project-recipe]'))button.onclick=()=>externalCreator.open(detail,detail.recipes.find(item=>item.id===button.dataset.projectRecipe));
    for(const button of root.querySelectorAll('[data-project-import]'))button.onclick=()=>openImport(button.dataset.projectImport);
    contextChanged();
  }
  async function loadDetail(id, refresh=false) {
    const epoch=++generation;controller?.abort();evidenceController?.abort();evidenceController=null;
    const request=new AbortController();controller=request;
    if(refresh)detail=null;render();
    try {
      const value=await api('/'+encodeURIComponent(id),{signal:request.signal});
      if(epoch!==generation||id!==active)return;
      if(value.id!==id||value.mode!=='inspection'||value.execution!=='unsupported'||!['data','recipes','evidence','requirements'].every(key=>Array.isArray(value[key])))throw Error('Unsupported project inspection response.');
      detail=value;render();
    }catch(error){
      if(epoch===generation&&id===active&&error.name!=='AbortError'){
        roots[view].innerHTML=`<div class="error-panel" role="alert">${esc(error.message)}<p>Project inspection is unavailable.</p><button type="button" class="project-retry">Retry inspection</button></div>`;
        roots[view].querySelector('button').onclick=()=>loadDetail(id,true);
      }
    }finally{if(controller===request)controller=null;}
  }
  async function loadEvidence(id) {
    evidenceController?.abort();const request=new AbortController();evidenceController=request;
    const project=active,epoch=generation,root=roots[view],output=root.querySelector('.project-evidence-output');
    output.textContent='Loading external evidence…';
    try{
      const value=await api('/'+encodeURIComponent(project)+'/evidence/'+encodeURIComponent(id),{signal:request.signal});
      if(evidenceController!==request||epoch!==generation||project!==active||view!=='runs')return;
      if(value.id!==id||value.external!==true||typeof value.text!=='string')throw Error('Unsupported external evidence response.');
      output.innerHTML=`<section class="panel panel-pad"><h3 tabindex="-1">${esc(value.label)} · external evidence</h3><p class="muted">Referenced source text; not a Tuldok run or scientific validation.</p><p class="project-path">SHA256 ${esc(value.sha256)}</p><pre>${esc(value.text)}</pre></section>`;
      output.querySelector('h3').focus({preventScroll:true});
    }catch(error){if(evidenceController===request&&epoch===generation&&error.name!=='AbortError')output.textContent=error.message;}
    finally{if(evidenceController===request)evidenceController=null;}
  }
  function openImport(id) {
    const item=detail?.data.find(ref=>ref.id===id);
    if(importing||!item||item.status!=='available'||item.integrity==='mismatch'||!(/^[a-f0-9]{64}$/.test(item.observed_sha256||'')))return;
    importTarget={project:active,ref:id,sha256:item.observed_sha256};importGeneration++;
    $('project-import-name').value=item.label;$('project-import-rights').value='unknown';$('project-import-group').value='';
    $('project-import-identity').textContent=item.path+' · SHA256 '+item.observed_sha256;
    $('project-import-status').textContent='Import original field bytes as a new catalog record. Source identity is checked again before import.';
    $('project-import-dialog').showModal();$('project-import-name').focus();
  }
  $('project-import-close').onclick=()=>{importGeneration++;$('project-import-dialog').close();if(importing)announce('Import may still complete. Inspect the catalog before repeating it.');};
  $('project-import-dialog').addEventListener('cancel',()=>{importGeneration++;if(importing)announce('Import may still complete. Inspect the catalog before repeating it.');});
  $('project-import-form').onsubmit=async event=>{
    event.preventDefault();if(importing||!importTarget)return;
    const target={...importTarget},epoch=++importGeneration,owner=generation;
    const group=$('project-import-group').value.trim();
    const body={name:$('project-import-name').value,rights:$('project-import-rights').value,groups:group?[group]:[],parents:[],expected_sha256:target.sha256};
    importing=true;$('project-import-submit').disabled=true;$('project-import-status').textContent='Checking source identity and importing…';
    try{
      const record=await api('/'+encodeURIComponent(target.project)+'/import-data/'+encodeURIComponent(target.ref),{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
      if(epoch!==importGeneration||owner!==generation||active!==target.project||!$('project-import-dialog').open)return;
      if(typeof record.id!=='string'||record.kind!=='field_sequence')throw Error('Unsupported imported field record response.');
      $('project-import-dialog').close();await openCatalogRecord(record.id);
    }catch(error){if(epoch===importGeneration)$('project-import-status').textContent=error.message+' If a reply was lost, inspect the catalog before repeating the import.';}
    finally{importing=false;$('project-import-submit').disabled=false;}
  };
  $('open-project').onclick=()=>{$('project-open-dialog').showModal();$('project-manifest').focus();refreshList();};
  $('project-open-close').onclick=()=>{openGeneration++;$('project-open-dialog').close();$('open-project').focus();};
  $('project-open-dialog').addEventListener('cancel',()=>{openGeneration++;});
  $('project-roots-refresh').onclick=refreshList;
  $('project-open-form').onsubmit=async event=>{
    event.preventDefault();if(opening)return;
    const root=$('project-root').value,manifest_path=$('project-manifest').value;
    if(!aliases.includes(root))return;
    const epoch=++openGeneration;opening=true;$('project-open-submit').disabled=true;$('project-open-status').textContent='Inspecting project manifest…';
    try{
      const value=await api('',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({root,manifest_path})});
      if(epoch!==openGeneration||!$('project-open-dialog').open)return;
      if(typeof value.id!=='string'||value.mode!=='inspection')throw Error('Unsupported opened project response.');
      listGeneration++;entries=entries.filter(entry=>entry.id!==value.id);entries.push(value);populate();
      $('project-open-dialog').close();switchSource('project:'+value.id);
    }catch(error){if(epoch===openGeneration)$('project-open-status').textContent=error.message+' Refresh saved projects before repeating an opening whose reply was lost.';}
    finally{opening=false;$('project-open-submit').disabled=!aliases.length;}
  };
  window.addEventListener('pagehide',()=>{generation++;listGeneration++;openGeneration++;importGeneration++;controller?.abort();evidenceController?.abort();});
  return {
    initialize:refreshList,
    label:()=>detail?.name||entries.find(entry=>'project:'+entry.id===currentSource())?.name||'Project',
    show(source,next){
      const id=source.startsWith('project:')?source.slice(8):null;
      for(const [name,root] of Object.entries(roots))root.hidden=!id||name!==next;
      if(id===active&&next===view)return;
      externalCreator.cancel();importGeneration++;$('project-import-dialog').close();
      const changed=id!==active;active=id;view=next;generation++;controller?.abort();evidenceController?.abort();controller=null;evidenceController=null;
      if(changed)detail=null;
      if(!id)return;
      if(detail)render();else loadDetail(id);
    },
  };
};
