'use strict';
// External graph projection only. The existing Pipeline and Runs owners admit all work.
// Binding shapes remain byte-compatible: project references never gain a kind key.
window.WorkspaceExternalInputs=(()=>{
  const esc=value=>window.workspaceEscape(value),hash=value=>/^[a-f0-9]{64}$/.test(value||'');
  function choices(project,releases,runs=[]){return {
    project_reference:(project.data||[]).filter(item=>item.status==='available'&&item.integrity!=='mismatch'&&hash(item.observed_sha256)).map(item=>({id:item.id,label:item.label,bytes:item.bytes,sha256:item.observed_sha256})),
    frozen_release:releases.map(item=>({id:item.release_id,label:item.release_id,bytes:item.bytes,sha256:item.sha256,unavailable:item.status!=='available'||!hash(item.sha256),reason:item.reason||item.status})),
    runs:runs.filter(run=>run.state==='completed'),
    run_artifact:runs.filter(run=>run.state==='completed'&&run.status==='receipt_verified').flatMap(run=>run.artifacts.map(item=>({id:item.artifact_name,run_id:run.run_id,label:item.artifact_name+' · '+item.role,bytes:item.bytes,sha256:item.sha256,unavailable:item.status!=='receipt_verified'||!hash(item.sha256)})))
  };}
  function kind(binding){return ['frozen_release','run_artifact'].includes(binding?.kind)?binding.kind:'project_reference';}
  function binding(type,item){
    if(!item||item.unavailable||!hash(item.sha256))throw Error('Choose an available input with an observed hash.');
    if(type==='run_artifact')return {kind:'run_artifact',run_id:item.run_id,artifact_name:item.id,expected_sha256:item.sha256};
    return type==='frozen_release'?{kind:'frozen_release',release_id:item.id,expected_sha256:item.sha256}:{reference_id:item.id,expected_sha256:item.sha256};
  }
  function options(type,value,list,max,runId=''){
    const id=value?.artifact_name||value?.release_id||value?.reference_id||'',items=(list[type]||[]).filter(item=>type!=='run_artifact'||item.run_id===runId);
    const retained=id&&!items.some(item=>item.id===id&&item.sha256===value.expected_sha256);
    return `<option value="">Choose ${type==='run_artifact'?'recorded artifact':type==='frozen_release'?'frozen release':'observed project data'}</option>${retained?`<option value="" data-input-retained selected>Saved ${esc(id)} · exact binding retained</option>`:''}${items.map(item=>`<option value="${esc(item.id)}" ${item.id===id&&item.sha256===value?.expected_sha256?'selected':''} ${item.unavailable||item.bytes>max?'disabled':''}>${esc(item.label)} · ${esc(item.bytes)} bytes${item.unavailable?' · '+esc(item.reason||'unavailable'):item.bytes>max?' · exceeds slot limit':''}</option>`).join('')}`;
  }
  function runOptions(value,list){
    const id=value?.run_id||'',runs=list.runs||[];
    return `<option value="">Choose completed Run</option>${id&&!runs.some(run=>run.run_id===id)?`<option value="${esc(id)}" selected>Saved ${esc(id)} · unavailable in candidate list</option>`:''}${runs.map(run=>`<option value="${esc(run.run_id)}" ${run.run_id===id?'selected':''} ${run.status!=='receipt_verified'||!run.artifacts.length?'disabled':''}>${esc(run.run_id)}${run.status!=='receipt_verified'?' · '+esc(run.reason||'unavailable'):!run.artifacts.length?' · no eligible input artifacts':''}</option>`).join('')}`;
  }
  function html(inputs,specs,list){return Object.keys(specs).map(name=>{
    const value=inputs[name],type=kind(value),max=specs[name].max_bytes;
    return `<fieldset style="min-width:0"><legend>Input · ${esc(name)}</legend><label>Source kind<select data-external-input-kind="${esc(name)}"><option value="project_reference" ${type==='project_reference'?'selected':''}>Project reference</option><option value="frozen_release" ${type==='frozen_release'?'selected':''}>Frozen release</option><option value="run_artifact" ${type==='run_artifact'?'selected':''}>Completed Run artifact</option></select></label><label data-external-input-run-group="${esc(name)}" ${type==='run_artifact'?'':'hidden'}>Source Run<select data-external-input-run="${esc(name)}" ${type==='run_artifact'?'required':'disabled'}>${runOptions(value,list)}</select><small>Recorded outputs; selected bytes verified during preflight and capture.</small></label><label>Exact input<select data-external-input="${esc(name)}" required>${options(type,value,list,max,value?.run_id)}</select></label><small>Maximum ${esc(max)} bytes</small><p class="project-path" data-external-input-hash="${esc(name)}">${esc(value?.expected_sha256||'Choose an input to bind its exact SHA256.')}</p></fieldset>`;
  }).join('');}
  function bind(root,inputs,specs,list,changed){
    const find=(attribute,name)=>Array.from(root.querySelectorAll('['+attribute+']')).find(node=>node.getAttribute(attribute)===name);
    for(const selector of root.querySelectorAll('[data-external-input-kind]')){
      const name=selector.getAttribute('data-external-input-kind'),target=find('data-external-input',name),hint=find('data-external-input-hash',name),run=find('data-external-input-run',name),group=find('data-external-input-run-group',name);
      const clear=()=>{target.innerHTML=options(selector.value,null,list,specs[name].max_bytes,run?.value);hint.textContent='Choose an input to bind its exact SHA256.';changed(name,null);};
      selector.onchange=()=>{if(run){run.value='';run.disabled=selector.value!=='run_artifact';run.required=!run.disabled;group.hidden=run.disabled;}clear();};
      if(run)run.onchange=clear;
      target.onchange=()=>{if(target.selectedOptions?.[0]?.hasAttribute('data-input-retained'))return;const item=list[selector.value]?.find(item=>item.id===target.value&&(selector.value!=='run_artifact'||item.run_id===run?.value));if(target.value===''||!item||item.unavailable||item.bytes>specs[name].max_bytes){changed(name,null);return;}const value=binding(selector.value,item);hint.textContent=value.expected_sha256;changed(name,value);};
    }
  }
  async function candidates(route='/api/workbench/releases/input-candidates',key='releases'){
    const response=await (window.TuldokAuth?.fetch||fetch)(route),value=await response.json();
    if(!response.ok||!Array.isArray(value[key]))throw Error(value.error||'Input choices unavailable.');return value[key];
  }
  async function catalogs(){
    const results=await Promise.allSettled([candidates(),candidates('/api/workspace/run-artifact-inputs','runs')]);
    return {releases:results[0].status==='fulfilled'?results[0].value:[],runs:results[1].status==='fulfilled'?results[1].value:[],errors:results.flatMap((item,index)=>item.status==='rejected'?[(index?'Run artifacts: ':'Frozen releases: ')+item.reason.message]:[])};
  }
  return {choices,binding,html,bind,candidates,catalogs};
})();

window.WorkspaceExternal=function({api,action,status,getGraph,getIntent,getRunId,isDirty,replaceGraph,changeGraph,render,refresh,onRun,onImported}){
  const esc=window.workspaceEscape,enc=encodeURIComponent,copy=value=>structuredClone(value);
  const isGraph=graph=>graph?.recipe==='external_recipe';
  let inputChoices=null,inputSpecs={};
  let epoch=0,preflight=null,definitions={},reviewed=false,grant='',recipient='',grantReceipt=null;
  let pending=history.state?.externalSubmission||null;
  const snapshot=()=>({epoch,graph:getGraph(),intent:getIntent(),actor:identity()?.actor_id,credential:identity()?.credential_id});
  const current=value=>value.epoch===epoch&&value.graph===getGraph()&&value.intent===getIntent()&&value.actor===identity()?.actor_id&&value.credential===identity()?.credential_id;
  const actorPending=()=>!pending||pending.actor_id===identity()?.actor_id;
  const remember=()=>history.replaceState({...history.state,externalSubmission:pending},'');
  const identity=()=>window.TuldokAuth?.identity();
  const owner=()=>identity()?.kind==='owner'&&identity().scopes.includes('approve-execution');
  const permissions='Trusted local code runs with the service user’s filesystem and network access. This is not a sandbox. Limits do not guarantee aggregate resource isolation.';
  function invalidate(reset=false){epoch++;if(reset){definitions={};inputChoices=null;inputSpecs={};}preflight=null;reviewed=false;grant='';grantReceipt=null;}
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
    root.innerHTML=`<p class="real-status" role="status"></p><div class="panel panel-pad real-library"><h2>Saved recipes</h2><label>Recipe<select id="real-graph-select">${graphs.map(item=>`<option value="${esc(item.id)}" ${item.id===graph.id?'selected':''}>${esc(item.name)} · r${item.revision}</option>`).join('')}</select></label><button id="real-refresh">Refresh catalog</button></div><section class="panel panel-pad"><div class="panel-title"><h2>External recipe</h2><span id="external-dirty" class="badge">${isDirty()?'Unsaved changes':'Saved r'+graph.revision}</span></div><div class="external-stages" aria-label="Recipe stages"><span>1 · Exact inputs</span><span>2 · Execute captured recipe</span><span>3 · Verify outputs</span></div><label>Name<input id="external-name" maxlength="120" value="${esc(graph.name)}"></label><div class="external-fields">${fieldsHTML(execute.parameters,definitions,'external-param-')}</div><section><h3>Input bindings</h3><button id="external-input-choices" type="button">Load input choices</button>${inputChoices?window.WorkspaceExternalInputs.html(input.inputs||{},inputSpecs,inputChoices):'<p class="muted">Load project data, frozen releases and completed Run artifacts to edit exact bindings.</p>'}</section><details><summary>Exact project and input references</summary><pre id="external-input-references">${esc(JSON.stringify(input,null,2))}</pre></details><div class="actions"><button id="external-save" ${!isDirty()?'disabled':''}>Save revision</button><button id="external-reload">Reload saved</button><button id="external-clone">Clone saved</button><button id="external-preflight" ${isDirty()?'disabled':''}>Preflight exact revision</button></div></section><section class="panel panel-pad"><h2>Execution approval</h2><p class="callout">${permissions}</p><div id="external-material">${preflight?`<p>Material SHA256 <code class="project-path">${esc(preflight.material_sha256)}</code></p><p>Graph r${esc(preflight.graph_revision)} · runtime ${esc(preflight.material?.recipe?.runtime||preflight.runtime?.profile||preflight.runtime?.id||'declared runtime')}</p><details><summary>Captured sources, inputs, runtime and limits</summary><pre>${esc(JSON.stringify(preflight.material,null,2))}</pre></details><details><summary>Declared output roles</summary><pre>${esc(JSON.stringify(preflight.outputs,null,2))}</pre></details>`:'<p>Preflight checks identity without executing project code.</p>'}</div>${owner()?`<label class="check-row"><input id="external-reviewed" type="checkbox" ${reviewed?'checked':''} ${!preflight||isDirty()?'disabled':''}>I reviewed this exact material and its effective permissions.</label><details><summary>Grant this material to an actor</summary><label>Consuming actor ID<input id="external-recipient" value="${esc(recipient||identity()?.actor_id||'')}"></label><button id="external-grant" ${!preflight||!reviewed||isDirty()?'disabled':''}>Create one-use approval</button>${grantReceipt?`<p id="external-grant-receipt" data-approval-id="${esc(grantReceipt.id||grantReceipt.approval_id)}">Approval ${esc(grantReceipt.id||grantReceipt.approval_id)} · actor ${esc(grantReceipt.consumer_actor_id||recipient)}</p><button id="external-revoke">Revoke approval</button>`:''}</details>`:`<label>Owner-issued approval ID<input id="external-approval-id" value="${esc(grant)}" autocomplete="off"></label><p class="muted">The grant must bind your actor, this graph revision and this exact material digest.</p>`}<button id="external-submit" class="primary" ${!actorPending()||(!pending&&(!preflight||isDirty()||(owner()?!reviewed:!grant.trim())))?'disabled':''}>${pending?'Check submitted request':'Submit exact approved material'}</button>${pending?`<p class="callout">Request ${esc((pending.body||pending).request_key)} for graph ${esc((pending.body||pending).graph_id)} r${esc((pending.body||pending).graph_revision)} has an unresolved acknowledgement. Originating actor ${esc(pending.actor_id||'unknown')}. Reconcile this same request before starting another.</p>`:''}<p class="footnote">Execution receipts establish process and artifact custody, not scientific correctness.</p></section>`;
    const $=id=>root.querySelector('#'+id);
    $('real-graph-select').onchange=event=>choose(event.target.value);$('real-refresh').onclick=refresh;
    $('external-name').oninput=event=>changeGraph(()=>graph.name=event.target.value,false);
    $('external-input-choices').onclick=()=>action(async()=>{
      const origin=snapshot();
      const [project,definition,catalog]=await Promise.all([api('project-snapshots/'+enc(input.project_id),undefined,2),api('projects/'+enc(input.project_id)+'/recipes/'+enc(input.recipe_id)+'?expected_sha256='+enc(input.expected_sha256),undefined,4),window.WorkspaceExternalInputs.catalogs()]);
      if(!current(origin))return;
      inputChoices=window.WorkspaceExternalInputs.choices(project,catalog.releases,catalog.runs);inputSpecs=definition.inputs;status(catalog.errors.length?catalog.errors.join(' ')+' Saved bindings remain unchanged.':'Loaded input choices. Changing a binding requires saving and a new preflight.');
    });
    if(inputChoices)window.WorkspaceExternalInputs.bind(root,input.inputs||{},inputSpecs,inputChoices,(name,value)=>changeGraph(()=>{if(value)input.inputs[name]=value;else delete input.inputs[name];},false));
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
    root.querySelector('#external-input-references').textContent=JSON.stringify(getGraph().nodes.find(node=>node.type==='input').parameters,null,2);
    const review=root.querySelector('#external-reviewed');if(review){review.checked=false;review.disabled=true;}
    const button=root.querySelector('#external-grant');if(button)button.disabled=true;
  }
  function importable(run,artifact){return isGraph(run?.graph)&&run.state==='completed'&&run.artifact_status?.status!=='unavailable'&&artifact?.role==='scientific_fields'&&typeof artifact.name==='string'&&!artifact.locked&&/^[a-f0-9]{64}$/.test(artifact.sha256||'');}
  function artifactActionHTML(run,artifact){
    if(!importable(run,artifact))return '';
    return `<button type="button" data-import-run-artifact="${esc(artifact.name)}" ${identity()?.scopes.includes('edit')?'':'disabled'}>Import into Data</button><small>Creates a draft. Review and freeze separately.</small>`;
  }
  async function importArtifact(run,artifact){
    if(!importable(run,artifact))throw Error('Only scientific-field outputs from a completed external run can be imported; the server verifies selected bytes.');
    if(!identity()?.scopes.includes('edit'))throw Error('Editing permission is required to import a draft.');
    const origin=snapshot(),runId=run.id,name=artifact.name,expected=artifact.sha256;
    let record;
    try{record=await api('runs/'+enc(runId)+'/import-data/'+enc(name),{expected_sha256:expected});}
    catch(error){throw Error(error.message+' If acknowledgement was lost, inspect Data for the existing content before retrying. This action never reruns the recipe.');}
    if(!record||typeof record.id!=='string')throw Error('Import response unavailable. Inspect Data before retrying.');
    if(current(origin)&&getRunId()===runId){
      status('Imported draft '+record.id+'. Review and freeze remain separate.');
      try{await onImported(record.id);}catch(error){status('Draft '+record.id+' was imported. '+error.message+' Open it from Data.');}
    }else status('Draft '+record.id+' was imported. Current navigation and edits are retained; open it from Data.');
  }
  function progressHTML(run,value){
    if(!value||value.run_id!==run.id)return '<section id="external-progress"><h3>Recipe progress</h3><p>Progress evidence unavailable. Run state remains authoritative.</p></section>';
    const verified=value.evidence==='custody_verified',live=value.evidence==='live_unverified';
    const label=verified?'Custody-verified log bytes':live?'Live output · unverified':value.evidence==='pending'?'Awaiting output':'Output unavailable';
    const progress=(verified||live)&&value.progress?.format==='tuldok_progress_v1'?value.progress:null;
    const result=run.state==='completed'&&value.result?.status==='hash_verified'?value.result:null;
    const summary=result?.summary?.format==='tuldok_result_summary_v1'?result.summary:null;
    const checkpoint=summary?.checkpoint&&(run.artifacts||[]).find(item=>item.name===summary.checkpoint&&item.role==='checkpoint'&&!item.locked);
    return `<section id="external-progress"><h3>Recipe progress</h3><p class="badge">${esc(label)}</p>${progress?`<p><strong>${esc(progress.stage)}</strong> · ${esc(progress.completed)} / ${esc(progress.total)}</p><progress max="${esc(progress.total||1)}" value="${esc(progress.completed)}" aria-label="Recipe-reported work"></progress><dl>${Object.entries(progress.metrics||{}).map(([name,value])=>`<dt>${esc(name)}</dt><dd>${esc(value)}</dd>`).join('')}</dl>`:'<p>No structured recipe progress reported. Work total and remaining duration are unknown.</p>'}${summary?`<section id="external-result-summary"><h3>${esc(summary.title)}</h3><p class="muted">Hash-verified result artifact · recipe-reported values, not scientific qualification.</p><dl>${summary.metrics.map(item=>`<dt>${esc(item.name)}</dt><dd>${esc(item.value)} ${esc(item.unit)}</dd>`).join('')}</dl><ul>${summary.scope.map(item=>`<li>${esc(item)}</li>`).join('')}</ul><p class="project-path">SHA256 ${esc(result.sha256)}</p>${checkpoint?`<a class="button" id="external-checkpoint-download" href="/api/workspace/runs/${enc(run.id)}/artifacts/${enc(checkpoint.name)}" download>Download checkpoint</a>`:''}</section>`:value.result?.status==='unavailable'?'<p class="callout">Result summary unavailable. Inspect recorded outputs for retained evidence.</p>':''}${['stdout','stderr'].map(name=>{const stream=(verified||live)&&value.streams?.[name];return `<details data-external-stream="${name}"><summary>${name} · ${stream?esc(stream.available_bytes)+' bytes'+(stream.truncated?' · bounded tail':''):'unavailable'}</summary>${stream?`<p class="muted">${esc(label)} · starts at byte ${esc(stream.start_byte)}</p><pre>${esc(stream.text)}</pre>`:'<p>No readable stream evidence.</p>'}</details>`;}).join('')}</section>`;
  }
  function runHTML(run,progress){return `<section class="external-run-custody">${progressHTML(run,progress)}<p><span class="badge">Trusted local execution</span> · Custody: <strong>${esc(run.custody_phase||'unconfirmed')}</strong></p>${run.state==='unknown'?'<p class="error-panel">Process cessation is unconfirmed. Same-boot execution may remain fenced; acknowledgement alone cannot clear custody.</p>':''}<details id="external-custody-details" data-external-disclosure><summary>Custody and approved material</summary><p>Approval ${esc(run.approval_id)} · actor ${esc(run.actor_id)}</p><p class="project-path">Material SHA256 ${esc(run.material_sha256)}</p><p class="muted">${permissions} Completion is not scientific qualification.</p><pre>${esc(JSON.stringify(run.material,null,2))}</pre></details></section>`;}
  window.addEventListener('tuldok-session',()=>{invalidate(true);if(isGraph(getGraph()))render();});
  return {isGraph,invalidate,renderPipeline,dirtyChanged,runHTML,progressHTML,artifactActionHTML,importArtifact};
};

window.WorkspaceExternalProject=function({onCreated,announce}){
  const esc=window.workspaceEscape,enc=encodeURIComponent;
  let generation=0,busy=false,project=null,reference=null,definition=null,inputChoices=null,bindings={},choicesError="";
  const dialog=document.createElement('dialog');dialog.id='external-create-dialog';dialog.setAttribute('aria-labelledby','external-create-title');document.body.append(dialog);
  async function api(route,body,selectedVersion){
    const headers={'Content-Type':'application/json'};
    if(selectedVersion!==undefined){
      const pin=window.WorkspaceExtensionAuthorContracts?.['recipes.inspect/4'];
      if(selectedVersion!==4||!pin)throw Error('Current recipe inspection is unavailable.');
      headers['Tuldok-Operation-Contract']='recipes.inspect/4/'+pin;
    }
    const response=await (window.TuldokAuth?.fetch||fetch)('/api/workspace/'+route,{headers,...(body===undefined?{}:{method:'POST',body:JSON.stringify(body)})});
    const value=await response.json();if(!response.ok)throw Error(value.error||'External recipe unavailable.');return value;
  }
  function cancel(){generation++;if(dialog.open)dialog.close();if(busy)announce('Graph creation may still complete. Inspect saved recipes before repeating it.');}
  window.addEventListener('tuldok-session',cancel);
  dialog.addEventListener('cancel',()=>{generation++;if(busy)announce('Graph creation may still complete. Inspect saved recipes before repeating it.');});
  function render(){
    dialog.innerHTML=`<div class="panel-title"><h2 id="external-create-title">Create external recipe</h2><button id="external-create-close" type="button">Close</button></div><p>${esc(reference.label)} · ${esc(reference.path)}</p><p class="project-path">SHA256 ${esc(reference.observed_sha256)}</p><p>Creating a graph does not execute project code.</p><form id="external-create-form"><label>Name<input id="external-create-name" maxlength="120" value="${esc(definition.definition.name)}" required></label>${choicesError?`<p class="callout">${esc(choicesError)}</p>`:''}${window.WorkspaceExternalInputs.html(bindings,definition.inputs,inputChoices)}<div class="external-fields">${Object.entries(definition.parameter_definitions).map(([name,spec])=>`<label>${esc(name)}${spec.enum?`<select data-create-param="${esc(name)}">${spec.enum.map(value=>`<option value="${esc(value)}" ${value===spec.default?'selected':''}>${esc(value)}</option>`).join('')}</select>`:spec.type==='boolean'?`<input type="checkbox" data-create-param="${esc(name)}" ${spec.default?'checked':''}>`:`<input data-create-param="${esc(name)}" type="${['integer','number'].includes(spec.type)?'number':'text'}" value="${esc(spec.default)}" ${spec.min!==undefined?`min="${esc(spec.min)}"`:''} ${spec.max!==undefined?`max="${esc(spec.max)}"`:''} ${spec.max_length?`maxlength="${esc(spec.max_length)}"`:''} step="${spec.type==='integer'?'1':'any'}">`}</label>`).join('')}</div><details><summary>Runtime, sources, outputs and limits</summary><pre>${esc(JSON.stringify(definition.definition,null,2))}</pre></details><button id="external-create-submit" class="primary">Create saved graph</button></form><p id="external-create-status" role="status"></p>`;
    window.WorkspaceExternalInputs.bind(dialog,bindings,definition.inputs,inputChoices,(name,value)=>{if(value)bindings[name]=value;else delete bindings[name];});
    dialog.querySelector('#external-create-close').onclick=cancel;
    dialog.querySelector('#external-create-form').onsubmit=async event=>{
      event.preventDefault();if(busy)return;const epoch=generation;
      const inputs=copy(bindings),parameters={};
      if(Object.keys(definition.inputs).some(name=>!inputs[name]))return;
      for(const input of dialog.querySelectorAll('[data-create-param]')){const spec=definition.parameter_definitions[input.dataset.createParam];parameters[input.dataset.createParam]=spec.type==='boolean'?input.checked:['integer','number'].includes(spec.type)?Number(input.value):input.value;}
      const body={name:dialog.querySelector('#external-create-name').value,project_id:project.id,recipe_id:reference.id,expected_sha256:reference.observed_sha256,inputs,parameters};
      busy=true;dialog.querySelectorAll('input,select,button:not(#external-create-close)').forEach(item=>item.disabled=true);dialog.querySelector('#external-create-status').textContent='Saving exact recipe references…';
      try{const graph=await api('graphs/external',body);if(epoch!==generation||!dialog.open)return;busy=false;dialog.close();try{await onCreated(graph.id);}catch(error){announce('Saved graph '+graph.id+'. '+error.message);}}
      catch(error){if(epoch===generation)dialog.querySelector('#external-create-status').textContent=error.message+' Inspect saved recipes before repeating a request whose acknowledgement was lost.';}
      finally{busy=false;if(epoch===generation)dialog.querySelectorAll('input,select,button').forEach(item=>item.disabled=false);}
    };
  }
  return {cancel,async open(detail,item){
    if(busy)return;const epoch=++generation;project=copy(detail);reference=copy(item);definition=null;bindings={};choicesError='';inputChoices=null;
    dialog.innerHTML='<h2 id="external-create-title">Inspecting recipe definition…</h2><p role="status">Reading declared fields. No project code is executed.</p><button id="external-create-close">Close</button>';dialog.querySelector('button').onclick=cancel;dialog.showModal();
    try{const value=await api('projects/'+enc(detail.id)+'/recipes/'+enc(item.id)+'?expected_sha256='+enc(item.observed_sha256),undefined,4);if(epoch!==generation||!dialog.open)return;if(!value.definition||!value.inputs||!value.parameter_definitions)throw Error('Unsupported external recipe definition.');definition=value;const catalog=await window.WorkspaceExternalInputs.catalogs();choicesError=catalog.errors.join(' ');if(epoch!==generation||!dialog.open)return;inputChoices=window.WorkspaceExternalInputs.choices(project,catalog.releases,catalog.runs);render();dialog.querySelector('#external-create-name').focus();}
    catch(error){if(epoch===generation&&dialog.open){dialog.querySelector('p').textContent=error.message;}}
  }};
  function copy(value){return structuredClone(value);}
};
