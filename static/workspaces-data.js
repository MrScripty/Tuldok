'use strict';
// Opt-in presentation adapter. Existing Workbench functions remain the owners.
(() => {
  if(window.parent===window || new URLSearchParams(location.search).get('workspace')!=='1')return;
  const stylesheet=document.createElement('link');stylesheet.rel='stylesheet';stylesheet.href='/workspaces-data.css';document.head.append(stylesheet);
  document.documentElement.classList.add('workspace-embedded');
  const snapshot=()=>({record:current?{id:current.id,name:current.name,revision:current.revision,source_revision:current.source_revision}:null,selection:[...selected.values()].map(({id,revision,source_revision})=>({id,revision,source_revision})),dirty:hasUnsavedEdits()});
  window.TuldokWorkspaceData={snapshot};
  const publish=()=>window.parent.postMessage({type:'tuldok-data-context',context:snapshot()},location.origin);
  const toolbar=document.createElement('div');toolbar.className='embed-toolbar';
  const drawer=document.createElement('dialog');drawer.id='embed-tools';
  const heading=document.createElement('h2');heading.textContent='Import, generate and release';
  const close=document.createElement('button');close.textContent='Close tools';close.type='button';
  const aside=document.querySelector('main>aside');drawer.append(heading,close,aside);document.body.append(drawer);
  const open=document.createElement('button');open.textContent='Import / generate / release';open.type='button';toolbar.append(open);document.querySelector('main').before(toolbar);
  open.onclick=()=>{drawer.showModal();close.focus();};close.onclick=()=>drawer.close();drawer.addEventListener('close',()=>open.focus());
  aside.querySelectorAll('details').forEach(d=>d.open=false);
  for(const id of ['saved-selection-panel','curation-panel'])document.getElementById(id).open=false;
  // Import and release controls keep their original DOM identity and handlers.
  const status=document.createElement('p');status.setAttribute('role','status');heading.after(status);
  const observer=new MutationObserver(()=>{status.textContent=document.getElementById('notice').textContent;publish();});observer.observe(document.getElementById('notice'),{childList:true,subtree:true});observer.observe(document.getElementById('selection'),{childList:true,subtree:true});
  document.addEventListener('input',()=>queueMicrotask(publish));document.addEventListener('change',()=>queueMicrotask(publish));
  document.addEventListener('invalid',event=>{for(let p=event.target.parentElement;p;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;},true);
  document.addEventListener('click',()=>queueMicrotask(publish));
  window.addEventListener('pagehide',()=>observer.disconnect(),{once:true});publish();
})();
