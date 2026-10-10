'use strict';
const pumasTypedEpoch={};
let pumasTypedHidden=false;
window.addEventListener('pagehide',()=>{pumasTypedHidden=true;for(const prefix of Object.keys(pumasTypedEpoch))++pumasTypedEpoch[prefix];});
window.addEventListener('pageshow',()=>{pumasTypedHidden=false;});
function pumasTypedSettings(prefix) {
  const get=name=>document.getElementById(prefix+'-'+name);
  return get('protocol')?.value==='pumas_typed_v1'?{protocol:'pumas_typed_v1',profile:get('profile').value||null}:{};
}
function pumasTypedRender(prefix) {
  const seed=document.getElementById(prefix+'-seed');
  if(seed && prefix!=='generation')seed.disabled=!!pumasTypedSettings(prefix).protocol;
  const catalog=document.getElementById(prefix+(prefix==='generation'?'-refresh':'-models'));
  if(catalog)catalog.textContent=pumasTypedSettings(prefix).protocol?'List serving aliases':prefix==='generation'?'Refresh image models':prefix==='grounded'?'Refresh served models':'List served text models';
  const output=document.getElementById(prefix+'-capability-metadata');
  if(output){output.hidden=true;output.textContent='';}
  pumasTypedEpoch[prefix]=(pumasTypedEpoch[prefix]||0)+1;
}
window.addEventListener('DOMContentLoaded',()=>{
  for(const prefix of ['text-classification-proposal','grounded','generation','caption-proposal']) {
    const get=name=>document.getElementById(prefix+'-'+name);
    if(!get('protocol'))continue;
    pumasTypedRender(prefix);
    for(const name of ['url','model','profile','protocol'])for(const event of ['input','change'])get(name).addEventListener(event,()=>pumasTypedRender(prefix));
    get('capabilities').addEventListener('click',async()=>{
      const body={server_url:get('url').value,model:get('model').value,profile:get('profile').value||null};
      const epoch=++pumasTypedEpoch[prefix],snapshot=JSON.stringify([body,get('protocol').value]);
      const current=()=>!pumasTypedHidden && epoch===pumasTypedEpoch[prefix] && snapshot===JSON.stringify([{server_url:get('url').value,model:get('model').value,profile:get('profile').value||null},get('protocol').value]);
      const output=get('capability-metadata');
      output.hidden=false;output.textContent='Inspecting selected model capabilities…';
      try {
        if(get('protocol').value!=='pumas_typed_v1')throw Error('Choose Pumas typed v1 to inspect its selected-model contract.');
        const response=await fetch('/api/generation/typed-capabilities',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
        const value=await response.json();
        if(!response.ok)throw Error(value.error||'Capability observation failed.');
        if(!current())return;
        output.textContent=JSON.stringify(value,null,2);
      } catch(error) {if(current())output.textContent=error.message;}
    });
  }
});
