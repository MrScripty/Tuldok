'use strict';
// External graph projection only. The existing Pipeline and Runs owners admit all work.
window.WorkspaceExternal=function({api,action,status,getGraph,getIntent,isDirty,replaceGraph,changeGraph,render,refresh,onRun}){
  const esc=window.workspaceEscape,enc=encodeURIComponent,copy=value=>structuredClone(value);
  const isGraph=graph=>graph?.recipe==='external_recipe';
  let epoch=0,preflight=null,definitions={},reviewed=false,grant='',recipient='',grantReceipt=null;
  let pending=history.state?.externalSubmission||null;
  const snapshot=()=>({epoch,graph:getGraph(),intent:getIntent(),actor:identity()?.actor_id,credential:identity()?.credential_id});
  const current=value=>value.epoch===epoch&&value.graph===getGraph()&&value.intent===getIntent()&&value.actor===identity()?.actor_id&&value.credential===identity()?.credential_id;
  const actorPending=()=>!pending||pending.actor_id===identity()?.actor_id;
  const remember=()=>history.replaceState({...history.state,externalSubmission:pending},'');
  const identity=()=>window.TuldokAuth?.identity();
  const owner=()=>identity()?.kind==='owner'&&identity().scopes.includes('approve-execution');
  const permissions='Trusted local code runs with the service user’s filesystem and network access. This is not a sandbox. Limits do not guarantee aggregate resource isolation.';
  function invalidate(reset=false){epoch++;if(reset)definitions={};preflight=null;reviewed=false;grant='';grantReceipt=null;}
  function fieldsHTML(values,defs,prefix){
    return Object.entries(values).map(([name,value])=>{
      const spec=defs[name]||{type:typeof value==='boolean'?'boolean':typeof value==='number'?'number':'string'},id=prefix+name;
      const attrs=`id="${esc(id)}" data-external-param="${esc(name)}"`;
      const control=spec.enum?`<select ${attrs}>${spec.enum.map(item=>`<option value="${esc(item)}" ${item===value?'selected':''}>${esc(item)}</option>`).join('')}</select>`:spec.type==='boolean'?`<input ${attrs} type="checkbox" ${value?'checked':''}>`:`<input ${attrs} type="${['integer','number'].includes(spec.type)?'number':'text'}" value="${esc(value)}" ${spec.min!==undefined?`min="${esc(spec.min)}"`:''} ${spec.max!==undefined?`max="${esc(spec.max)}"`:''} ${spec.max_length?`maxlength="${esc(spec.max_length)}"`:''} step="${spec.type==='integer'?'1':'any'}">`;
      return `<label>${esc(name)}${control}<small>${esc(spec.type)}${spec.min!==undefined?' · min '+esc(spec.min):''}${spec.max!==undefined?' · max '+esc(spec.max):''}</small></label>`;
    }).join('');
  }
  function readValue(input,spec){return spec?.type==='boolean'||input.type==='checkbox'?input.checked:['integer','number'].includes(spec?.type)||input.type==='number'?(input.value===''?null:Number(input.value)):input.value;}
  function bindParameters(root,defs,changed){for(const input of root.querySelectorAll('[data-external-param]'))input.oninput=()=>changed(input.dataset.externalParam,readValue(input,defs[input.dataset.externalParam]));}
  async function submit(){
    const origin=snapshot();
    const previouslyAmbiguous=!!pending;
    if(!pending){
      const graph=getGraph();if(isDirty()||!preflight||preflight.graph_revision!==graph.revision)throw Error('Save and preflight this exact revision first.');
      if(owner()&&!reviewed)throw Error('Review the exact material before owner submission.');
      if(!owner()&&!grant.trim())throw Error('An owner-issued approval ID is required.');
      pending={actor_id:identity()?.actor_id,body:{request_key:crypto.randomUUID(),graph_id:graph.id,graph_revision:graph.revision,expected_digest:preflight.material_sha256,...(!owner()?{approval_id:grant.trim()}:{})}};remember();
    }
    if(!actorPending())throw Error('This unresolved request belongs to another actor. Restore the originating actor to reconcile it.');
    let result;
    try{result=await api('runs/submit-external',pending.body);}
    catch(error){
      // A prior ambiguous send may already have committed. Later authorization or
      // material failures cannot prove that it did not: preserve its exact key.
      if(!previouslyAmbiguous&&[400,404,409].includes(error.status)&&['invalid','stale','unsupported','unavailable'].includes(error.code)){pending=null;invalidate();remember();}
      throw error;
    }
    pending=null;remember();
    if(current(origin))onRun(result);
    else status('External attempt '+result.id+' was admitted. Current navigation is retained; inspect saved Runs.');
  }
  function renderPipeline(root,{graph,graphs,busy,choose}){
    const execute=graph.nodes.find(node=>node.type==='execute'),input=graph.nodes.find(node=>node.type==='input').parameters;
    root.innerHTML=`<p class="real-status" role="status"></p><div class="panel panel-pad real-library"><h2>Saved recipes</h2><label>Recipe<select id="real-graph-select">${graphs.map(item=>`<option value="${esc(item.id)}" ${item.id===graph.id?'selected':''}>${esc(item.name)} · r${item.revision}</option>`).join('')}</select></label><button id="real-refresh">Refresh catalog</button></div><section class="panel panel-pad"><div class="panel-title"><h2>External recipe</h2><span id="external-dirty" class="badge">${isDirty()?'Unsaved changes':'Saved r'+graph.revision}</span></div><div class="external-stages" aria-label="Recipe stages"><span>1 · Project inputs</span><span>2 · Execute captured recipe</span><span>3 · Verify outputs</span></div><label>Name<input id="external-name" maxlength="120" value="${esc(graph.name)}"></label><div class="external-fields">${fieldsHTML(execute.parameters,definitions,'external-param-')}</div><details><summary>Exact project and input references</summary><pre>${esc(JSON.stringify(input,null,2))}</pre></details><div class="actions"><button id="external-save" ${!isDirty()?'disabled':''}>Save revision</button><button id="external-reload">Reload saved</button><button id="external-clone">Clone saved</button><button id="external-preflight" ${isDirty()?'disabled':''}>Preflight exact revision</button></div></section><section class="panel panel-pad"><h2>Execution approval</h2><p class="callout">${permissions}</p><div id="external-material">${preflight?`<p>Material SHA256 <code class="project-path">${esc(preflight.material_sha256)}</code></p><p>Graph r${esc(preflight.graph_revision)} · runtime ${esc(preflight.runtime?.profile||preflight.runtime?.id||'declared runtime')}</p><details><summary>Captured sources, inputs, runtime and limits</summary><pre>${esc(JSON.stringify(preflight.material,null,2))}</pre></details><details><summary>Declared output roles</summary><pre>${esc(JSON.stringify(preflight.outputs,null,2))}</pre></details>`:'<p>Preflight checks identity without executing project code.</p>'}</div>${owner()?`<label class="check-row"><input id="external-reviewed" type="checkbox" ${reviewed?'checked':''} ${!preflight||isDirty()?'disabled':''}>I reviewed this exact material and its effective permissions.</label><details><summary>Grant this material to an actor</summary><label>Consuming actor ID<input id="external-recipient" value="${esc(recipient||identity()?.actor_id||'')}"></label><button id="external-grant" ${!preflight||!reviewed||isDirty()?'disabled':''}>Create one-use approval</button>${grantReceipt?`<p id="external-grant-receipt" data-approval-id="${esc(grantReceipt.id||grantReceipt.approval_id)}">Approval ${esc(grantReceipt.id||grantReceipt.approval_id)} · actor ${esc(grantReceipt.consumer_actor_id||recipient)}</p><button id="external-revoke">Revoke approval</button>`:''}</details>`:`<label>Owner-issued approval ID<input id="external-approval-id" value="${esc(grant)}" autocomplete="off"></label><p class="muted">The grant must bind your actor, this graph revision and this exact material digest.</p>`}<button id="external-submit" class="primary" ${!actorPending()||(!pending&&(!preflight||isDirty()||(owner()?!reviewed:!grant.trim())))?'disabled':''}>${pending?'Check submitted request':'Submit exact approved material'}</button>${pending?`<p class="callout">Request ${esc((pending.body||pending).request_key)} for graph ${esc((pending.body||pending).graph_id)} r${esc((pending.body||pending).graph_revision)} has an unresolved acknowledgement. Originating actor ${esc(pending.actor_id||'unknown')}. Reconcile this same request before starting another.</p>`:''}<p class="footnote">Execution receipts establish process and artifact custody, not scientific correctness.</p></section>`;
    const $=id=>root.querySelector('#'+id);
    $('real-graph-select').onchange=event=>choose(event.target.value);$('real-refresh').onclick=refresh;
    $('external-name').oninput=event=>changeGraph(()=>graph.name=event.target.value,false);
    bindParameters(root,definitions,(name,value)=>changeGraph(()=>execute.parameters[name]=value,false));
    $('external-save').onclick=()=>action(async()=>{const origin=snapshot(),value=await api('graphs/'+enc(graph.id),{revision:graph.revision,document:copy(graph)});if(current(origin)){replaceGraph(value);status('Saved revision. Preflight and review again.');}else status('Graph revision saved. Current navigation and edits retained.');});
    $('external-reload').onclick=()=>{if(isDirty()&&!confirm('Discard unsaved external recipe edits?'))return;action(async()=>{const origin=snapshot(),value=await api('graphs/'+enc(graph.id));if(current(origin))replaceGraph(value);});};
    $('external-clone').onclick=()=>{if(isDirty()&&!confirm('Clone saved revision and discard unsaved edits?'))return;action(async()=>{const origin=snapshot(),value=await api('graphs/'+enc(graph.id)+'/clone',{name:graph.name.slice(0,112)+' copy'});if(current(origin))replaceGraph(value);else status('Graph '+value.id+' cloned. Current navigation and edits retained.');});};
    $('external-preflight').onclick=()=>action(async()=>{const origin=snapshot();const value=await api('graphs/'+enc(graph.id)+'/preflight-external',{revision:graph.revision});if(!current(origin))throw Error('Selection or session changed during preflight. Review again.');if(value.valid!==true||value.graph_revision!==graph.revision||!/^[a-f0-9]{64}$/.test(value.material_sha256))throw Error('Unsupported external preflight response.');preflight=value;definitions=value.parameter_definitions;reviewed=false;grant='';grantReceipt=null;status('Preflight captured exact material. Review before submission.');});
    $('external-reviewed')?.addEventListener('change',event=>{reviewed=event.target.checked;render();});
    $('external-recipient')?.addEventListener('input',event=>{recipient=event.target.value;});
    $('external-approval-id')?.addEventListener('input',event=>{grant=event.target.value;$('external-submit').disabled=!actorPending()||!pending&&(!preflight||isDirty()||!grant.trim());});
    $('external-grant')?.addEventListener('click',()=>action(async()=>{if(!reviewed||!preflight||isDirty())throw Error('Review this exact material first.');const origin=snapshot();recipient=$('external-recipient').value;const value=await api('runs/approve-external',{graph_id:graph.id,graph_revision:graph.revision,expected_digest:preflight.material_sha256,consumer_actor_id:recipient});if(current(origin)){grantReceipt=value;status('Created one-use exact-material approval.');}else status('Approval '+value.id+' created. Current selection retained.');}));
    $('external-revoke')?.addEventListener('click',()=>action(async()=>{const origin=snapshot();const response=await (window.TuldokAuth?.fetch||fetch)('/api/access/execution-grants/'+enc(grantReceipt.id||grantReceipt.approval_id)+'/revoke',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});const value=await response.json();if(!response.ok)throw Error(value.error||'Revocation failed.');if(current(origin))grantReceipt=null;status('Approval revoked.');}));
    $('external-submit').onclick=()=>action(submit);
    if(busy)root.querySelectorAll('button,input,select').forEach(node=>node.disabled=true);
  }
  function dirtyChanged(root){
    root.querySelector('#external-dirty').textContent='Unsaved changes';root.querySelector('#external-save').disabled=false;root.querySelector('#external-preflight').disabled=true;root.querySelector('#external-submit').disabled=!actorPending()||!pending;
    root.querySelector('#external-material').textContent='Save this revision, then preflight and review its exact material.';
    const review=root.querySelector('#external-reviewed');if(review){review.checked=false;review.disabled=true;}
    const button=root.querySelector('#external-grant');if(button)button.disabled=true;
  }
  function runHTML(run){return `<section class="external-run-custody"><h3>External execution custody</h3><p>${esc(run.custody_phase||'No confirmed custody phase')}</p><p>Approval ${esc(run.approval_id)} · actor ${esc(run.actor_id)}</p><p class="project-path">Material SHA256 ${esc(run.material_sha256)}</p>${run.state==='unknown'?'<p class="error-panel">Process cessation is unconfirmed. Same-boot execution may remain fenced; acknowledgement alone cannot clear custody.</p>':''}<p class="muted">${permissions} Completion is not scientific qualification.</p><details><summary>Approved material</summary><pre>${esc(JSON.stringify(run.material,null,2))}</pre></details></section>`;}
  window.addEventListener('tuldok-session',()=>{invalidate();if(isGraph(getGraph()))render();});
  return {isGraph,invalidate,renderPipeline,dirtyChanged,runHTML};
};

window.WorkspaceExternalProject=function({onCreated,announce}){
  const esc=window.workspaceEscape,enc=encodeURIComponent;
  let generation=0,busy=false,project=null,reference=null,definition=null;
  const dialog=document.createElement('dialog');dialog.id='external-create-dialog';dialog.setAttribute('aria-labelledby','external-create-title');document.body.append(dialog);
  async function api(route,body){const response=await (window.TuldokAuth?.fetch||fetch)('/api/workspace/'+route,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});const value=await response.json();if(!response.ok)throw Error(value.error||'External recipe unavailable.');return value;}
  function cancel(){generation++;if(dialog.open)dialog.close();if(busy)announce('Graph creation may still complete. Inspect saved recipes before repeating it.');}
  window.addEventListener('tuldok-session',cancel);
  dialog.addEventListener('cancel',()=>{generation++;if(busy)announce('Graph creation may still complete. Inspect saved recipes before repeating it.');});
  function render(){
    const refs=project.data.filter(item=>item.status==='available'&&item.integrity!=='mismatch'&&/^[a-f0-9]{64}$/.test(item.observed_sha256||''));
    dialog.innerHTML=`<div class="panel-title"><h2 id="external-create-title">Create external recipe</h2><button id="external-create-close" type="button">Close</button></div><p>${esc(reference.label)} · ${esc(reference.path)}</p><p class="project-path">SHA256 ${esc(reference.observed_sha256)}</p><p>Creating a graph does not execute project code.</p><form id="external-create-form"><label>Name<input id="external-create-name" maxlength="120" value="${esc(definition.definition.name)}" required></label>${Object.entries(definition.inputs).map(([name,spec])=>`<label>Input · ${esc(name)}<select data-external-input="${esc(name)}" required><option value="">Choose observed project data</option>${refs.map(item=>`<option value="${esc(item.id)}">${esc(item.label)} · ${esc(item.bytes)} bytes</option>`).join('')}</select><small>Maximum ${esc(spec.max_bytes)} bytes</small></label>`).join('')}<div class="external-fields">${Object.entries(definition.parameter_definitions).map(([name,spec])=>`<label>${esc(name)}${spec.enum?`<select data-create-param="${esc(name)}">${spec.enum.map(value=>`<option value="${esc(value)}" ${value===spec.default?'selected':''}>${esc(value)}</option>`).join('')}</select>`:spec.type==='boolean'?`<input type="checkbox" data-create-param="${esc(name)}" ${spec.default?'checked':''}>`:`<input data-create-param="${esc(name)}" type="${['integer','number'].includes(spec.type)?'number':'text'}" value="${esc(spec.default)}" ${spec.min!==undefined?`min="${esc(spec.min)}"`:''} ${spec.max!==undefined?`max="${esc(spec.max)}"`:''} ${spec.max_length?`maxlength="${esc(spec.max_length)}"`:''} step="${spec.type==='integer'?'1':'any'}">`}</label>`).join('')}</div><details><summary>Runtime, sources, outputs and limits</summary><pre>${esc(JSON.stringify(definition.definition,null,2))}</pre></details><button id="external-create-submit" class="primary">Create saved graph</button></form><p id="external-create-status" role="status"></p>`;
    dialog.querySelector('#external-create-close').onclick=cancel;
    dialog.querySelector('#external-create-form').onsubmit=async event=>{
      event.preventDefault();if(busy)return;const epoch=generation;
      const inputs={},parameters={};
      for(const input of dialog.querySelectorAll('[data-external-input]')){const item=refs.find(ref=>ref.id===input.value);if(!item)return;inputs[input.dataset.externalInput]={reference_id:item.id,expected_sha256:item.observed_sha256};}
      for(const input of dialog.querySelectorAll('[data-create-param]')){const spec=definition.parameter_definitions[input.dataset.createParam];parameters[input.dataset.createParam]=spec.type==='boolean'?input.checked:['integer','number'].includes(spec.type)?Number(input.value):input.value;}
      const body={name:dialog.querySelector('#external-create-name').value,project_id:project.id,recipe_id:reference.id,expected_sha256:reference.observed_sha256,inputs,parameters};
      busy=true;dialog.querySelectorAll('input,select,button:not(#external-create-close)').forEach(item=>item.disabled=true);dialog.querySelector('#external-create-status').textContent='Saving exact recipe references…';
      try{const graph=await api('graphs/external',body);if(epoch!==generation||!dialog.open)return;busy=false;dialog.close();try{await onCreated(graph.id);}catch(error){announce('Saved graph '+graph.id+'. '+error.message);}}
      catch(error){if(epoch===generation)dialog.querySelector('#external-create-status').textContent=error.message+' Inspect saved recipes before repeating a request whose acknowledgement was lost.';}
      finally{busy=false;if(epoch===generation)dialog.querySelectorAll('input,select,button').forEach(item=>item.disabled=false);}
    };
  }
  return {cancel,async open(detail,item){
    if(busy)return;const epoch=++generation;project=copy(detail);reference=copy(item);definition=null;
    dialog.innerHTML='<h2 id="external-create-title">Inspecting recipe definition…</h2><p role="status">Reading declared fields. No project code is executed.</p><button id="external-create-close">Close</button>';dialog.querySelector('button').onclick=cancel;dialog.showModal();
    try{const value=await api('projects/'+enc(detail.id)+'/recipes/'+enc(item.id)+'?expected_sha256='+enc(item.observed_sha256));if(epoch!==generation||!dialog.open)return;if(!value.definition||!value.inputs||!value.parameter_definitions)throw Error('Unsupported external recipe definition.');definition=value;render();dialog.querySelector('#external-create-name').focus();}
    catch(error){if(epoch===generation&&dialog.open){dialog.querySelector('p').textContent=error.message;}}
  }};
  function copy(value){return structuredClone(value);}
};
