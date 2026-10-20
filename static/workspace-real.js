"use strict";
window.WorkspaceCoordinatorContracts = {
  'runs.coordinator_health/1': 'a5d87e0cf67706641dc361c2d783fdb1557dd2c1198f0db2506726a132b8cae9',
  'runs.recover_coordinator/1': 'd31aee53400b2f00adedb958feb054f636b9efd7e2e1a0afad0fd55a9fd46b19'
};
window.WorkspaceCoordinator = function ({api, render, identity=()=>window.TuldokAuth?.identity(),
  getStorage=()=>window.sessionStorage}) {
  const esc=window.workspaceEscape, documents=window.WorkspacePublicationDocuments;
  let epoch=0, readEpoch=0, health=null, message='', busy=false, storageError='', current=()=>false,
    activeRead=null, activeWrite=null;
  const session=()=>JSON.stringify([identity()?.catalog_id,identity()?.actor_id,identity()?.credential_id]);
  const owner=()=>identity()?.kind==='owner'&&['inspect','approve-execution'].every(scope=>identity()?.scopes?.includes(scope));
  const closed=(value,keys)=>value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).sort().join(',')===[...keys].sort().join(',');
  const id=value=>typeof value==='string'&&/^[a-f0-9]{32}$/.test(value);
  const key=value=>typeof value==='string'&&/^[A-Za-z0-9][A-Za-z0-9_.:-]{7,127}$/.test(value);
  const generation=value=>Number.isInteger(value)&&value>=1&&value<2**31;
  const storeKey='tuldok.coordinator.requests.v1';
  const requestFields=['actor_id','request_key','request_sha256','expected_generation','completed_generation'];
  function invalidate(){epoch++;readEpoch++;activeRead?.abort();activeWrite?.abort();activeRead=null;activeWrite=null;health=null;message='';busy=false;storageError='';current=()=>false;}
  function snapshot(){const own=epoch, credential=session();return ()=>own===epoch&&credential===session()&&current();}
  async function check(value){
    if(!closed(value,['format','catalog_id','generation','state','updated_at','fault','admission_ready','recovery_request'])||value.format!=='run_coordinator_health_v1'||!id(value.catalog_id)||value.catalog_id!==identity()?.catalog_id||!generation(value.generation)||!['healthy','idle','blocked','recovering','stopped','faulted'].includes(value.state)||typeof value.updated_at!=='string'||!value.updated_at||value.updated_at.length>64||typeof value.admission_ready!=='boolean'||value.admission_ready&&!['healthy','idle'].includes(value.state))throw Error('Coordinator health identity or readiness differs.');
    if(value.fault!==null&&(!closed(value.fault,['category','at'])||!(/^[a-z_]{1,80}$/.test(value.fault.category||''))||typeof value.fault.at!=='string'||!value.fault.at||value.fault.at.length>64))throw Error('Coordinator fault receipt is invalid.');
    const request=value.recovery_request;
    if(request!==null){
      if(!closed(request,requestFields)||!id(request.actor_id)||!key(request.request_key)||!generation(request.expected_generation)||request.expected_generation>value.generation||request.completed_generation!==null&&(!generation(request.completed_generation)||request.completed_generation<=request.expected_generation||request.completed_generation>value.generation))throw Error('Coordinator recovery receipt is invalid.');
      const body={expected_generation:request.expected_generation,request_key:request.request_key};
      if(request.request_sha256!==await documents.digest({catalog_id:value.catalog_id,operation:'runs.recover_coordinator',actor_id:request.actor_id,body}))throw Error('Coordinator request hash differs from its actor and body.');
    }
    return value;
  }
  function requests(){
    const raw=getStorage().getItem(storeKey);
    if(raw&&raw.length>128*1024)throw Error('Coordinator request storage exceeds its bound.');
    const values=raw?JSON.parse(raw):{};
    if(!values||typeof values!=='object'||Array.isArray(values)||Object.keys(values).length>128)throw Error('Coordinator request storage is invalid.');
    return values;
  }
  const scope=()=>identity().catalog_id+':'+identity().actor_id;
  function pending(){
    try{
      const value=requests()[scope()]||null;
      if(value&&(!closed(value,['expected_generation','request_key'])||!generation(value.expected_generation)||!key(value.request_key)))throw Error('Coordinator request identity is invalid.');
      storageError='';return value;
    }catch{storageError='Tab request storage is unavailable. Restore it before recovery; refresh health to inspect saved state.';return null;}
  }
  function retain(body){
    const values={...requests(),[scope()]:body},raw=JSON.stringify(values);
    if(raw.length>128*1024||Object.keys(values).length>128)throw Error('Coordinator request storage exceeds its bound.');
    getStorage().setItem(storeKey,raw);
  }
  function body(){
    const retained=pending(), request=health.recovery_request;
    if(storageError)throw Error(storageError);
    if(retained&&request&&(request.actor_id!==identity().actor_id||request.request_key!==retained.request_key||request.expected_generation!==retained.expected_generation)){
      // The new request may never have reached the owner. An older completed
      // receipt does not consume this exact pending current-generation key.
      if(request.completed_generation!==null&&request.completed_generation<=retained.expected_generation&&retained.expected_generation===health.generation)return retained;
      throw Error('Saved request and current receipt differ. Inspect the original recovery request before starting another.');
    }
    // A completed acknowledgement stays complete even if another fault occurs.
    // A new explicit action then names the current generation with a fresh key.
    if(request?.completed_generation!==null&&request?.completed_generation!==undefined){
      return {expected_generation:health.generation,request_key:crypto.randomUUID()};
    }
    if(retained){
      if(!request&&retained.expected_generation!==health.generation)throw Error('Saved recovery generation changed without an acknowledgement. Inspect the saved request first.');
      return retained;
    }
    if(request?.actor_id===identity().actor_id)return {expected_generation:request.expected_generation,request_key:request.request_key};
    return {expected_generation:health.generation,request_key:crypto.randomUUID()};
  }
  async function refresh(isCurrent=snapshot()){
    pending();
    activeRead?.abort();const controller=new AbortController();activeRead=controller;
    const read=++readEpoch, selected=()=>isCurrent()&&read===readEpoch;
    try{const value=await api('coordinator',undefined,1,10000,controller.signal);if(!selected())return;const checked=await check(value);if(!selected())return;health=checked;message='';}
    catch(error){if(selected()){health=null;message=error.message;}}
    finally{if(activeRead===controller)activeRead=null;if(selected())render();}
  }
  async function load(isCurrent){invalidate();current=isCurrent;pending();await refresh(snapshot());}
  async function recover(){
    const isCurrent=snapshot();if(!isCurrent()||busy||!owner()||!health||health.admission_ready||!['faulted','blocked'].includes(health.state))return;
    let request;
    try{request=body();retain(request);}catch(error){message=error.message;render();return;}
    readEpoch++;activeRead?.abort();const controller=new AbortController();activeWrite=controller;busy=true;message='Waiting for owned attempts to drain and reconciling the queue…';render();
    try{const value=await api('coordinator/recover',request,1,75000,controller.signal);if(!isCurrent())return;const checked=await check(value);if(!isCurrent())return;
      if(!checked.recovery_request||checked.recovery_request.actor_id!==identity().actor_id||checked.recovery_request.request_key!==request.request_key||checked.recovery_request.expected_generation!==request.expected_generation)throw Error('Recovery acknowledgement identifies another request.');
      message='Recovery response received. Checking current saved health…';
    }catch(error){if(isCurrent())message=error.message+' The exact request is retained. Refresh health before reconciling it.';}
    finally{if(activeWrite===controller)activeWrite=null;if(isCurrent()){busy=false;const previous=message;await refresh(isCurrent);if(isCurrent()){const receipt=health?.recovery_request;
      message=health?.admission_ready&&receipt?.actor_id===identity().actor_id&&receipt.request_key===request.request_key&&receipt.expected_generation===request.expected_generation&&receipt.completed_generation!==null?'Saved recovery receipt confirmed. The queue may resume.':previous;render();}}}
  }
  function html(){
    const request=health?.recovery_request, canRecover=!storageError&&owner()&&health&&!health.admission_ready&&['faulted','blocked'].includes(health.state);
    return `<section id="coordinator-panel" aria-labelledby="coordinator-title"><h3 id="coordinator-title">Run coordinator</h3><p id="coordinator-message" role="status">${esc(message||storageError)}</p>${health?`<p id="coordinator-health"><strong>${esc(health.state)}</strong> · generation ${health.generation} · ${health.admission_ready?'ready for new work':'new work is fenced'}</p><p>Updated ${esc(health.updated_at)}${health.fault?` · retained fault: ${esc(health.fault.category)}`:''}</p>`:'<p>Current coordinator health is unavailable.</p>'}<div class="actions"><button id="coordinator-refresh">Refresh coordinator health</button>${canRecover?`<button id="coordinator-recover" ${busy?'disabled':''}>${request?.completed_generation===null&&request.actor_id===identity()?.actor_id?'Reconcile same recovery request':'Recover current coordinator'}</button>`:''}</div>${canRecover?'<p>Recovery reconciles existing custody before resuming the original queue.</p>':''}${!owner()?'<p>A current owner with execution approval can recover a fenced coordinator.</p>':''}${request?`<details><summary>Saved recovery receipt</summary><pre>${esc(JSON.stringify(request,null,2))}</pre></details>`:''}</section>`;
  }
  function bind(root){root.querySelector('#coordinator-refresh')?.addEventListener('click',()=>refresh());root.querySelector('#coordinator-recover')?.addEventListener('click',recover);}
  return {load,invalidate,html,bind};
};
// Real HTTP boundary. Fixture state is never read or submitted by this module.
// Server-owned graph definitions and validation determine execution eligibility.
(() => {
  const esc = (s) => window.workspaceEscape(s),
    copy = (v) => structuredClone(v),
    short = (s) => String(s || "").slice(0, 12),
    encoded = encodeURIComponent,
    terminal = new Set(["completed", "failed", "cancelled", "interrupted", "unknown"]);
  async function api(route, body, selectedVersion, timeout=75000, requestSignal) {
    const headers = {"Content-Type": "application/json"};
    const path = route.split('?')[0].split('/');
    const modelRecipe=body?.recipe||body?.document?.recipe;
    const modelGraph=['image_classification_model_v2','text_classification_model_v2','audio_classification_model_v2'].includes(modelRecipe);
    const operation = path[0]==='scientific-comparison'?'runs.compare_scientific_evidence':path[0]==='experiment-lineage' ? (path.length===1?(body===undefined?'studies.lineage':'studies.record_lineage'):path[1]==='branch'?'studies.branch_trial':'studies.lineage_trial') : path[0]==='graphs'&&modelGraph ? (path.length===1?'graphs.create':'graphs.save') : path[0] === 'models' ? (path.length === 1 ? (body === undefined ? 'models.list' : 'models.create') : path[2] === 'publish' ? 'models.publish' : body === undefined ? 'models.get' : 'models.save') :
      path[0] === 'studies' ? (path.length === 1 ? (body === undefined ? 'studies.list' : 'studies.create') : path[2] ? ({'prepare-branch':'studies.prepare_branch','prepare-trial':'studies.prepare_trial',continue:'studies.continue',admit:'studies.admit',reconcile:'studies.reconcile',approve:'studies.approve','prepare-package':'studies.prepare_package','prepare-verifier':'studies.prepare_verifier','select-candidate':'studies.select_candidate'})[path[2]] : body === undefined ? 'studies.get' : 'studies.save') :
      path[0] === 'candidates' ? (path[2]==='package-state'?'studies.package_state':'studies.candidate') : path[0] === 'runs' && path[2] === 'candidates' ? 'studies.candidates' : path[0] === 'runs' && path[2] === 'model-evidence' ? 'runs.model_evidence' : path[0] === 'runs' && path[2] === 'compare-model-evidence' ? 'runs.compare_model_evidence' : null;
    const publicationOperation=path[0]==='publication-results'?(path.length===1?'runs.publication_result':path[1]==='model-evidence'?'runs.publication_model_evidence':path[1]==='artifact-segment'?'runs.publication_artifact_chunk':null):path[0]==='runs'?({'publication':'runs.publication_status','recover-publication':'runs.recover_publication','cancel-publication':'runs.cancel_publication'})[path[2]]:null;
    const coordinatorOperation=path[0]==='coordinator'?(path.length===1?'runs.coordinator_health':path[1]==='recover'?'runs.recover_coordinator':null):null;
    const phaseOperation=path[0]==='runs'&&path[2]==='phase-timings'?'runs.phase_timings':path[0]==='graphs'&&path[2]==='preparation-timings'?'graphs.preparation_timings':null;
    if(operation==='runs.compare_scientific_evidence'){
      const pin=window.WorkspaceScientificContracts?.[operation+'/1'];
      if(selectedVersion!==1||!pin)throw Error('The exact scientific comparison contract is unavailable.');
      headers['Tuldok-Operation-Contract']=operation+'/1/'+pin;
    } else if(phaseOperation){
      const pin=window.WorkspacePhaseContracts?.[phaseOperation+'/1'];
      if(selectedVersion!==1||!pin)throw Error('The exact timing operation contract is unavailable.');
      headers['Tuldok-Operation-Contract']=phaseOperation+'/1/'+pin;
    } else if(coordinatorOperation){
      const pin=window.WorkspaceCoordinatorContracts?.[coordinatorOperation+'/1'];
      if(selectedVersion!==1||!pin)throw Error('The exact coordinator operation contract is unavailable.');
      headers['Tuldok-Operation-Contract']=coordinatorOperation+'/1/'+pin;
    } else if(publicationOperation){
      const version=publicationOperation==='runs.publication_status'?2:1;
      const pin=window.WorkspacePublicationContracts?.[publicationOperation+'/'+version];
      if(selectedVersion!==version||!pin)throw Error('The exact publication operation contract is unavailable.');
      headers['Tuldok-Operation-Contract']=publicationOperation+'/'+version+'/'+pin;
    } else if(path[0]==='projects'&&path[2]==='recipes'&&path.length===4&&body===undefined){
      const sha=window.WorkspaceExtensionAuthorContracts?.['recipes.inspect/4'];
      if(selectedVersion!==4||!sha)throw Error('Current recipe inspection is unavailable.');
      headers['Tuldok-Operation-Contract']='recipes.inspect/4/'+sha;
    } else if(path[0]==='project-snapshots'&&path.length===2&&body===undefined){
      const sha=window.WorkspaceExtensionAuthorContracts?.['project_snapshots.get/2'];
      if(selectedVersion!==2||!sha)throw Error('Current project inspection is unavailable.');
      headers['Tuldok-Operation-Contract']='project_snapshots.get/2/'+sha;
    } else if (operation) {
      const version=operation==='runs.model_evidence'&&selectedVersion===2?2:operation==='runs.compare_model_evidence'?2:operation.startsWith('graphs.')?(modelRecipe==='image_classification_model_v2'?2:3):1;
      const sha = window.WorkspaceModelContracts?.[version===3||operation==='runs.model_evidence'&&version===2?operation+'/'+version:operation];
      if (!sha) throw Error('This model operation has no supported local contract: ' + operation);
      headers['Tuldok-Operation-Contract'] = operation + '/' + version + '/' + sha;
    }
    const controller=publicationOperation||coordinatorOperation||phaseOperation||operation==='runs.compare_scientific_evidence'?new AbortController():null;
    const deadline=controller?setTimeout(()=>controller.abort(),Math.min(75000,Math.max(1,timeout))):null;
    const abort=()=>controller?.abort();
    if(requestSignal?.aborted)abort();else requestSignal?.addEventListener('abort',abort,{once:true});
    try {
    const response = await (globalThis.TuldokAuth?.fetch || fetch)("/api/workspace/" + route, {
      ...(body === undefined ? {} : {method: "POST", body: JSON.stringify(body)}), headers, ...(controller?{signal:controller.signal}:{}),
    });
    if(publicationOperation||coordinatorOperation||phaseOperation||operation==='runs.compare_scientific_evidence'){
      const length=response.headers.get('Content-Length');
      if(!/^\d+$/.test(length||'')||Number(length)>(operation==='runs.compare_scientific_evidence'?2*1024**2:phaseOperation?48*1024:coordinatorOperation?16*1024:16*1024**2))throw Error('Selected response has no supported bounded length.');
    }
    const value = await response.json();
    if (!response.ok) {
      const error = Error(value.error || "Workspace request failed.");
      error.code = value.code; error.status = response.status; throw error;
    }
    return value;
    } finally {if(deadline!==null)clearTimeout(deadline);requestSignal?.removeEventListener('abort',abort);}
  }
  window.WorkspaceReal = function ({ pipelineRoot, runsRoot, announce, openRecord, openRun, openImportedRecord }) {
    let definitions, releases = [], graphs = [], graph = null, saved = "", selectedNode = "train",
      validation = null, busy = false, loadGeneration = 0, undo = [], redo = [],
      view = null, timer = null, runs = [], run = null, runGeneration = 0, notice = "", noticeError = false,
      runProgress = null, predictions = null, predictionError = null, split = "validation", selectedCell = null, context = null;
    const memory = history.state?.realWorkspace || {};
    let graphId = memory.graphId || null, runId = memory.runId || null,
      pendingSubmission = memory.pendingSubmission || null;
    const external = WorkspaceExternal({api,action,status,getGraph:()=>graph,getIntent:()=>loadGeneration,getRunId:()=>runId,isDirty:()=>dirty(),
      replaceGraph:document=>{if(!graphs.some(item=>item.id===document.id))graphs.push(document);adopt(document);},
      changeGraph:change,render:renderPipeline,refresh:loadPipeline,
      onImported:openImportedRecord,observePreparation:restart=>observePreparation(restart),
      onRun:result=>{run=result;runId=result.id;predictions=null;predictionError=null;remember();status("External attempt admitted with exact material approval.");openRun();}});
    const model = WorkspaceModel({api, announce, openRecord, getIntent:()=>loadGeneration, getView:()=>view,
      openRun:result=>{run=result;runId=result.id;remember();if(view==='runs')loadRuns(runId);else openRun();}});
    const publication = window.WorkspacePublication({api,render:()=>{if(view==='runs')renderRuns();}});
    const coordinator = window.WorkspaceCoordinator({api,render:renderCoordinator});
    const phases = window.WorkspacePhaseTimings({api,render:renderPhases});
    const preparation = window.WorkspacePhaseTimings({api,render:renderPreparation});
    const scientific = window.WorkspaceScientificComparison({api,announce});
    const fieldEvidence = window.WorkspaceFieldEvidence({api,announce});
    const candidatePackages = window.WorkspaceCandidatePackageEvidence({api});
    const lineage = window.WorkspaceExperimentLineage({api,announce,getIntent:()=>loadGeneration,getView:()=>view,getGraph:()=>graph,isDirty:()=>dirty(),
      openRecipe:async(id,current)=>{if(await openGraph(id,current)){if(!graphs.some(item=>item.id===graph.id))graphs.push(copy(graph));if(current())renderPipeline();}},openRun:async(id,current)=>{if(await openRunById(id,current))openRun();},
      compare:async(id,baseline,current)=>{if(await openRunById(id,current)){if(run?.graph?.recipe==='external_recipe'){if(!await openRunById(baseline,current))return;scientific.queueComparison(baseline,id);}else model.queueComparison(id,baseline);openRun();}}});
    function mountModel() {
      const container=document.createElement('div');container.id='real-model-root';pipelineRoot.prepend(container);
      model.configure({definitions,releases,context});model.mount(container);
      const lineageRoot=document.createElement('div');lineageRoot.id='real-lineage-root';pipelineRoot.prepend(lineageRoot);lineage.mount(lineageRoot,context);
    }
    function remember() {
      history.replaceState({ ...history.state, realWorkspace: { version: 1, graphId, runId, pendingSubmission } }, "");
    }
    const dirty = () => !!graph && JSON.stringify(graph) !== saved;
    function status(text, error = false) {
      notice = text; noticeError = error;
      announce(text, error);
      const target = (view === "runs" ? runsRoot : pipelineRoot).querySelector(".real-status");
      if (target) { target.textContent = text; target.classList.toggle("error-panel", error); }
    }
    function retainFocus(root, render) {
      const focused = root.contains(document.activeElement) ? document.activeElement.id : null;
      const phaseScroll=Array.from(root.querySelectorAll('.phase-timing-table[id]')).map(node=>[node.id,node.scrollLeft]);
      render();
      for(const [id,left] of phaseScroll){const node=root.querySelector('#'+CSS.escape(id));if(node)node.scrollLeft=left;}
      if (focused) root.querySelector("#" + CSS.escape(focused))?.focus({ preventScroll: true });
    }
    function adopt(document) {
      preparation.invalidate();graph = document; graphId = graph.id; saved = JSON.stringify(graph);
      graphs = graphs.map(item => item.id === graph.id ? copy(graph) : item);
      validation = null; external.invalidate(true); undo = []; redo = []; remember();
    }
    function change(fn, render = true) {
      undo.push(copy(graph)); if (undo.length > 40) undo.shift(); redo = [];
      fn(); validation = null;preparation.invalidate();renderPreparation();
      if(external.isGraph(graph)){external.invalidate();if(render)renderPipeline();else external.dirtyChanged(pipelineRoot);return;}
      if (render) renderPipeline(); else {
        pipelineRoot.querySelector("#real-dirty").textContent = "Unsaved changes";
        pipelineRoot.querySelector("#real-validate").disabled = true;
        pipelineRoot.querySelector("#real-submit").disabled = !pendingSubmission;
        pipelineRoot.querySelector("#real-undo").disabled = false;
        pipelineRoot.querySelector("#real-redo").disabled = true;
        pipelineRoot.querySelector("#real-validation").textContent = "Save this revision, then validate it.";
        pipelineRoot.querySelector("#real-differences").innerHTML = differencesHTML();
      }
    }
    async function action(fn) {
      if (busy) return;
      const actionView = view, actionIntent = loadGeneration;
      const actionRoot = view === "pipeline" ? pipelineRoot : view === "runs" ? runsRoot : null;
      const focusedId = actionRoot?.contains(document.activeElement) ? document.activeElement.id : null;
      busy = true;
      for (const root of [pipelineRoot, runsRoot]) root.querySelectorAll("button,input,select").forEach(e => e.disabled = true);
      try { await fn(); } catch (error) {
        status(error.message + (error.code === "commit_unknown" ? " The acknowledgement was lost. Reload saved state before another write." : ""), true);
      } finally {
        busy = false;
        const restore = focusedId && view === actionView && loadGeneration === actionIntent && document.activeElement === document.body;
        // Keep the error/status outside the replaced panels.
        if (view === "pipeline") renderPipeline();
        else if (view === "runs") renderRuns();
        if (restore && document.activeElement === document.body)
          actionRoot.querySelector("#" + CSS.escape(focusedId))?.focus({ preventScroll: true });
      }
    }
    async function loadPipeline() {
      const generation = ++loadGeneration;
      pipelineRoot.innerHTML = '<p class="real-status" role="status">Loading saved recipes and frozen releases…</p>';
      try {
        const values = await Promise.all([api("definitions"), api("releases"), api("graphs"), api("context")]);
        if (generation !== loadGeneration || view !== "pipeline") return;
        [definitions, releases, graphs, context] = values;
        if (!graph) {
          const chosen = graphs.find(g => g.id === graphId) || graphs[0];
          if (chosen) adopt(chosen);
        }
        await model.refresh(()=>generation===loadGeneration&&view==='pipeline');
        if(generation!==loadGeneration||view!=='pipeline')return;
        renderPipeline();
      } catch (error) {
        if (generation !== loadGeneration || view !== "pipeline") return;
        pipelineRoot.innerHTML = `<div class="error-panel" role="alert">${esc(error.message)}<p>Your current draft is retained.</p><button id="real-load-retry">Retry loading</button></div>`;
        pipelineRoot.querySelector("button").onclick = loadPipeline;
      }
    }
    function recipeDefinition(document = graph) {
      return definitions?.recipes?.find(item => item.id === (document?.recipe || "image_classification")) || definitions;
    }
    function expectedEdges() {
      if (!graph || !definitions) return [];
      const definition = recipeDefinition();
      return definition.recipe.slice(0, -1).flatMap((type, i) => {
        const from = graph.nodes.find(n => n.type === type), to = graph.nodes.find(n => n.type === definition.recipe[i + 1]);
        if (!from || !to) return [];
        return [{ from: from.id, output: definition.nodes.find(n => n.type === type).output,
          to: to.id, input: definition.nodes.find(n => n.type === to.type).input }];
      });
    }
    const edgeKey = e => [e.from, e.output, e.to, e.input].join(":");
    const titles = { release: "Frozen release", validate: "Validate / export", train: "Train TinyCNN", evaluate: "Evaluate", publish: "Publish artifacts" };
    const explanations = {
      release: "Exact, reviewed source revisions and class mapping from an immutable classification release.",
      validate: "Verify frozen bytes, class coverage, resource bounds and protected families.",
      train: "Train from scratch on the training split. CPU only; no pretrained weights or downloads.",
      evaluate: "Measure validation and test splits separately. Test results stay gated until deliberately exposed.",
      publish: "Publish the checkpoint, predictions, metrics and hashes only after successful verification.",
    };
    const integrityKinds = {image_validate_export: {name: "Image export", unit: "images", source: "classification records", classification: true},
      text_validate_export: {name: "Text export", unit: "texts", source: "classification records", classification: true},
      audio_validate_export: {name: "Audio export", unit: "WAV intervals", source: "classification records", classification: true},
      mesh_validate_export: {name: "Mesh", unit: "meshes", source: "native geometry"},
      sequence_validate_export: {name: "Sequence", unit: "sequences", source: "native accepted-state frames"},
      pointcloud_validate_export: {name: "Point cloud", unit: "point clouds", source: "native point order and properties"},
      volume_validate_export: {name: "Volume", unit: "volumes", source: "native voxel arrays and declared affine"}};
    const integrityKind = document => integrityKinds[document?.recipe];
    const audioRecipe = document => document?.recipe?.startsWith("audio_classification");
    const sourceUnit = recipe => integrityKinds[recipe] ? integrityKinds[recipe].unit : recipe?.startsWith("audio_classification") ? "WAV intervals" : recipe?.startsWith("text_classification") ? "texts" : "images";
    const trainingTitle = document => audioRecipe(document) ? "Fit audio features + logistic regression" : document?.recipe?.startsWith("text_classification") ? "Fit TF-IDF + Naive Bayes" : titles.train;
    function differencesHTML() {
      if (!graph) return "";
      const original = JSON.parse(saved), installed = definitions.recipes?.find(item => item.id === (graph.recipe || "image_classification")), changes = [];
      if (graph.name !== original.name) changes.push(`Name: ${original.name} → ${graph.name}`);
      for (const node of graph.nodes) {
        const previous = original.nodes.find(item => item.id === node.id);
        if (JSON.stringify(previous?.parameters) !== JSON.stringify(node.parameters))
          changes.push(`${node.type}: ${JSON.stringify(previous?.parameters || {})} → ${JSON.stringify(node.parameters)}`);
      }
      if (JSON.stringify(graph.edges) !== JSON.stringify(original.edges)) changes.push("Typed connections changed.");
      const versions = graph.nodes.map(node => {
        const current = installed?.nodes?.find(item => item.type === node.type);
        return `${node.type}: saved v${original.nodes.find(item => item.id === node.id)?.definition_version ?? "unavailable"}, draft v${node.definition_version}, installed ${current ? "v" + current.definition_version : "unavailable"}`;
      });
      return `<p>${changes.length ? changes.map(esc).join("<br>") : "No changes from the saved recipe."}</p><p>Recipe: saved v${esc(original.recipe_version)}, draft v${esc(graph.recipe_version)}, installed ${installed?.recipe_version ? "v" + esc(installed.recipe_version) : "unavailable"}.</p><ul>${versions.map(item => `<li>${esc(item)}</li>`).join("")}</ul><p class="muted">No automatic upgrade. Unsupported definitions remain blocked by validation.</p>`;
    }
    function recipeChoices(release) {
      return (release?.allowed_recipes || (release?.recipe ? [release.recipe] : [])).map(id =>
        `<option value="${esc(id)}">${esc(integrityKinds[id] ? "Validate and export · " + integrityKinds[id].unit : "Train and evaluate · " + sourceUnit(id))}</option>`).join("");
    }
    function renderPhases(){const target=runsRoot.querySelector('#real-phase-root');if(target){retainFocus(target,()=>{target.innerHTML=phases.html();});phases.bind(target);}}
    function renderPreparation(){const target=pipelineRoot.querySelector('#preparation-phase-root');if(target){retainFocus(target,()=>{target.innerHTML=preparation.html();});preparation.bind(target);}}
    function observePreparation(restart=false){
      if(!external.isGraph(graph)||dirty()||view!=='pipeline'){preparation.invalidate();return;}
      const selected=graph,generation=loadGeneration;
      preparation.select({kind:'preparation',id:graph.id,revision:graph.revision},()=>view==='pipeline'&&graph===selected&&!dirty()&&generation===loadGeneration,restart);
    }
    function renderPipeline() {
      if (!definitions) return;
      if(external.isGraph(graph)){
        retainFocus(pipelineRoot, () => external.renderPipeline(pipelineRoot,{graph,graphs,busy,choose:id=>{if(dirty()&&!confirm("Discard unsaved recipe changes?")){renderPipeline();return;}action(async()=>adopt(await api("graphs/"+encoded(id))));}}));
        if(notice){const target=pipelineRoot.querySelector('.real-status');target.textContent=notice;target.classList.toggle('error-panel',noticeError);}const phaseRoot=document.createElement('div');phaseRoot.id='preparation-phase-root';pipelineRoot.append(phaseRoot);observePreparation();renderPreparation();mountModel();return;
      }
      const integrity = integrityKind(graph);
      const title = {...titles, train: trainingTitle(graph), ...(integrity ? {validate: `Validate ${integrity.name.toLowerCase()} integrity`, publish: "Publish integrity report"} : {})};
      const eligible = releases.filter(r => r.status === "available"),
        node = graph?.nodes.find(n => n.id === selectedNode) || graph?.nodes[0];
      if (node) selectedNode = node.id;
      const releaseOptions = (selected) => releases.map(r => `<option value="${esc(r.id)}" ${r.id === selected ? "selected" : ""} ${r.status !== "available" ? "disabled" : ""}>${short(r.id)} · ${r.status === "available" ? r.records + " " + sourceUnit(r.recipe) : r.status}</option>`).join("");
      retainFocus(pipelineRoot, () => {
        pipelineRoot.innerHTML = `<p class="callout"><strong>Real local workflows.</strong> Image, text and WAV classification; mesh, sequence, point cloud and volume integrity validation/export. Choose training or validation/export from a frozen release. ASR and 3D training are unavailable.</p>
        <p class="real-status" role="status"></p>
        <div class="panel panel-pad real-library"><div><span class="eyebrow">SAVED RECIPES</span><h2>Saved recipes</h2><small>Catalog ${esc(short(context?.dataset_id))}</small></div>
        <label>Recipe<select id="real-graph-select"><option value="">Choose a recipe</option>${graphs.map(g => `<option value="${g.id}" ${g.id === graphId ? "selected" : ""}>${esc(g.name)} · r${g.revision}</option>`).join("")}</select></label>
        <button id="real-refresh">Refresh catalog</button></div>
        <details class="panel panel-pad" ${graph ? "" : "open"}><summary>Create a recipe from a frozen release</summary><form id="real-create-form" class="real-create"><label>Name<input id="real-create-name" maxlength="120" required value="Local workflow"></label><label>Frozen release<select id="real-create-release" required>${eligible.length ? releaseOptions() : '<option value="">No eligible frozen release</option>'}</select></label><label>Operation<select id="real-create-recipe" required>${recipeChoices(eligible[0])}</select></label><button class="primary" ${eligible.length ? "" : "disabled"}>Create recipe</button></form>${!eligible.length ? '<p>In Data, review and select records, then freeze a supported classification release or a single-subtype spatial canonical release. Then refresh here.</p><a href="#data">Open Data →</a>' : ""}${releases.filter(r => r.status !== "available").map(r => `<p class="muted">${esc(short(r.id))}: ${esc(r.message || r.status)}</p>`).join("")}</details>
        ${graph ? `<div class="panel"><div class="panel-title"><div><span class="eyebrow">EDITABLE RECIPE · V${esc(graph.recipe_version)}</span><h2>${esc(graph.name)}</h2></div><span class="badge ${dirty() ? "amber" : "green"}" id="real-dirty">${dirty() ? "Unsaved changes" : "Saved r" + graph.revision}</span></div>
        <div class="real-graph-layout"><div class="panel-pad"><div class="real-nodes" aria-label="Recipe nodes">${graph.nodes.map((n, i) => `<button id="real-node-${esc(n.id)}" data-node="${esc(n.id)}" aria-pressed="${n.id === selectedNode}"><span class="node-index">${i + 1}</span><span><strong>${esc(title[n.type] || n.type)}</strong><small>Definition v${n.definition_version}</small></span>${i < graph.nodes.length - 1 ? '<span aria-hidden="true">↓</span>' : ""}</button>`).join("")}</div>
        <details class="real-connections"><summary>Edit typed connections</summary>${expectedEdges().map((edge, i) => `<label><input type="checkbox" data-edge="${i}" ${graph.edges.some(e => edgeKey(e) === edgeKey(edge)) ? "checked" : ""}>${esc(edge.from)} → ${esc(edge.to)}<small>${esc(edge.output)}</small></label>`).join("")}<p class="muted">Disconnecting a stage creates an invalid draft. Save and validate to inspect server errors.</p></details></div>
        <section class="panel-pad real-inspector"><span class="eyebrow">NODE INSPECTOR</span><h2>${esc(title[node.type] || node.type)}</h2><p>${esc(node.type === "train" && audioRecipe(graph) ? "Measure eight fixed features of the exact source channel and interval, then fit training-only scaling and logistic regression. Original WAVs stay unchanged. No ASR, resampling or downmix." : node.type === "train" && graph.recipe?.startsWith("text_classification") ? "Fit vocabulary, IDF and Naive Bayes once on training text only. No pretrained model or downloads. Validation and test use that frozen transform." : (integrity ? {release: `Exact reviewed ${integrity.unit} from an immutable ${integrity.classification ? "classification" : "canonical"} release.`, validate: integrity.classification ? `Verify ${integrity.source}, hashes and protected-family scope. No training or model-quality qualification.` : `Verify ${integrity.source}, hashes, units and selected-record family scope. No training or physics certification.`, publish: "Publish the integrity report and hashes; retain the unchanged frozen release."}[node.type] : explanations[node.type]) || "Unsupported node definition.")}</p>
        <label>Recipe name<input id="real-name" value="${esc(graph.name)}" maxlength="120"></label>
        ${node.type === "train" ? Object.entries(node.parameters).filter(([key])=>!["widths","input_size","head"].includes(key)).map(([key, value]) => `<label>${esc(key.replaceAll("_", " "))}<input id="real-param-${esc(key)}" data-param="${esc(key)}" type="number" step="${recipeDefinition().parameter_bounds[key]?.type === "number" ? "any" : "1"}" min="${recipeDefinition().parameter_bounds[key]?.minimum ?? ""}" max="${recipeDefinition().parameter_bounds[key]?.maximum ?? ""}" value="${esc(value)}"></label>`).join("") : ""}
        ${node.type === "release" ? `<label>Frozen release<select id="real-release">${releaseOptions(node.parameters.release_id)}</select></label><p class="muted">${esc(node.parameters.release_id)}</p>` : ""}
        <p class="footnote">Changing a draft never changes an existing run. Recipe limits and release eligibility are checked by the server.</p></section></div>
        <details class="panel-pad"><summary>Recipe changes and definitions</summary><div id="real-differences">${differencesHTML()}</div></details>
        <div class="panel-pad real-actions"><button id="real-undo" ${undo.length ? "" : "disabled"}>Undo</button><button id="real-redo" ${redo.length ? "" : "disabled"}>Redo</button><button id="real-reload">Reload saved</button><button id="real-clone">Clone saved recipe</button><button id="real-save">Save revision</button><button id="real-validate" ${dirty() ? "disabled" : ""}>Validate</button><button id="real-submit" class="primary" ${pendingSubmission || (!dirty() && validation?.valid) ? "" : "disabled"}>${pendingSubmission ? "Reconcile pending submission" : (integrity ? `Validate and export ${integrity.unit}` : "Run on local CPU")}</button></div>
        <div class="panel-pad" id="real-validation">${validation ? validationHTML() : 'Save this revision, then validate it.'}</div></div>` : ""}`;
      });
      if (notice && notice !== "Validation blocked. Inspect the errors below.") { const target = pipelineRoot.querySelector('.real-status'); target.textContent = notice; target.classList.toggle('error-panel', noticeError); }
      pipelineRoot.querySelector("#real-refresh").onclick = loadPipeline;
      pipelineRoot.querySelector("#real-graph-select").onchange = event => {
        if (dirty() && !confirm("Discard unsaved recipe edits and open another saved recipe?")) { event.target.value = graphId; return; }
        const chosen = graphs.find(g => g.id === event.target.value); if (chosen) { adopt(copy(chosen)); renderPipeline(); }
      };
      pipelineRoot.querySelector("#real-create-release").onchange = event => {
        pipelineRoot.querySelector("#real-create-recipe").innerHTML = recipeChoices(releases.find(item => item.id === event.target.value));
      };
      pipelineRoot.querySelector("#real-create-form").onsubmit = event => {
        event.preventDefault();
        if (dirty() && !confirm("Discard unsaved recipe edits and create another recipe?")) return;
        const release_id = pipelineRoot.querySelector("#real-create-release").value;
        const body = { name: pipelineRoot.querySelector("#real-create-name").value, release_id, recipe: pipelineRoot.querySelector("#real-create-recipe").value };
        action(async () => { const result = await api("graphs", body); graphs.push(result); adopt(result); status("Recipe created. Inspect parameters, then validate."); });
      };
      if (!graph) {mountModel();return;}
      pipelineRoot.querySelectorAll("[data-node]").forEach(button => button.onclick = () => { selectedNode = button.dataset.node; renderPipeline(); pipelineRoot.querySelector("#real-node-" + CSS.escape(selectedNode)).focus(); });
      pipelineRoot.querySelector("#real-name").oninput = event => change(() => graph.name = event.target.value, false);
      pipelineRoot.querySelectorAll("[data-param]").forEach(input => input.oninput = () => change(() => node.parameters[input.dataset.param] = input.value === "" ? null : Number(input.value), false));
      pipelineRoot.querySelector("#real-release")?.addEventListener("change", event => change(() => node.parameters.release_id = event.target.value));
      pipelineRoot.querySelectorAll("[data-edge]").forEach(input => input.onchange = () => {
        const edge = expectedEdges()[Number(input.dataset.edge)];
        change(() => { graph.edges = graph.edges.filter(e => edgeKey(e) !== edgeKey(edge)); if (input.checked) graph.edges.push(edge); });
      });
      pipelineRoot.querySelector("#real-undo").onclick = () => { redo.push(copy(graph)); graph = undo.pop(); validation = null; renderPipeline(); };
      pipelineRoot.querySelector("#real-redo").onclick = () => { undo.push(copy(graph)); graph = redo.pop(); validation = null; renderPipeline(); };
      pipelineRoot.querySelector("#real-reload").onclick = () => {
        if (dirty() && !confirm("Discard unsaved recipe changes and reload the saved revision?")) return;
        action(async () => { adopt(await api("graphs/" + encoded(graphId))); status("Loaded current saved revision."); });
      };
      pipelineRoot.querySelector("#real-clone").onclick = () => action(async () => {
        if (dirty() && !confirm("Clone the saved revision and discard these unsaved edits?")) return;
        const result = await api("graphs/" + encoded(graphId) + "/clone", { name: graph.name.slice(0, 112) + " copy" });
        graphs.push(result); adopt(result); status("Cloned the saved revision. Unsaved edits are excluded.");
      });
      pipelineRoot.querySelector("#real-save").onclick = () => action(async () => {
        const result = await api("graphs/" + encoded(graphId), { revision: graph.revision, document: copy(graph) });
        graphs = graphs.map(g => g.id === result.id ? result : g); adopt(result); status("Saved revision " + result.revision + ". Validate before running.");
      });
      pipelineRoot.querySelector("#real-validate").onclick = () => action(async () => {
        validation = await api("graphs/" + encoded(graphId) + "/validate", { revision: graph.revision });
        status(validation.valid ? (integrity ? `${integrity.name} release and graph are ready for integrity validation.` : "Release, graph and local CPU runtime are ready.") : "Validation blocked. Inspect the errors below.", !validation.valid);
      });
      pipelineRoot.querySelector("#real-submit").onclick = () => action(async () => {
        if (!pendingSubmission) {
          if (dirty() || !validation?.valid) throw Error("Save and validate the current recipe before submitting.");
          pendingSubmission = { request_key: crypto.randomUUID(), graph_id: graph.id, graph_revision: graph.revision, validation_token: validation.validation_token };
          remember();
        }
        let result;
        try { result = await api("runs", pendingSubmission); }
        catch (error) {
          // These service outcomes prove this exact request was rejected before
          // admission. Transport/storage uncertainty retains the original key.
          if ([400,404,409].includes(error.status) && ["invalid","stale","unsupported","unavailable"].includes(error.code)) {
            pendingSubmission = null; validation = null; remember();
            error.message += " No run was admitted. Reload the saved recipe if it changed, then validate again.";
          }
          throw error;
        }
        pendingSubmission = null; runId = result.id; run = result;
        split = "validation"; selectedCell = null; predictions = null; predictionError = null; remember();
        status("Durable run admitted. Its graph and release are frozen."); openRun();
      });
      mountModel();
      if (busy) pipelineRoot.querySelectorAll("button,input,select").forEach(e => e.disabled = true);
    }
    function meshSummaryHTML(summary) {
      if (!summary) return "";
      return `<section class="real-mesh-summary"><h3>Mesh integrity</h3><p>${esc(summary.mesh_count)} meshes · ${esc(summary.vertex_count)} vertices · ${esc(summary.triangle_count)} triangles</p><p>Family scope: ${esc(summary.family_scope)}</p><p>Declared units: ${esc([...new Set((summary.meshes || []).map(mesh => mesh.units))].join(", "))}</p><details><summary>Validation scope and limitations</summary><ul>${(summary.limitations || []).map(item => `<li>${esc(item)}</li>`).join("")}</ul><pre>${esc(JSON.stringify(summary.meshes, null, 2))}</pre></details></section>`;
    }
    function integritySummaryHTML(document, summary) {
      if (!summary) return "";
      if (integrityKind(document)?.classification) return `<section class="real-export-summary"><h3>Classification export integrity</h3><p>${esc(summary.record_count)} ${esc(sourceUnit(document.recipe))} · ${esc(JSON.stringify(summary.split_counts))}</p><p>${esc(summary.scope)}</p><details><summary>Frozen classes and format</summary><p>${esc(summary.format)}</p><pre>${esc(JSON.stringify(summary.class_vocabulary, null, 2))}</pre></details></section>`;
      if (document.recipe === "mesh_validate_export") return meshSummaryHTML(summary);
      if (document.recipe === "pointcloud_validate_export" || document.recipe === "volume_validate_export") {
        const points = document.recipe === "pointcloud_validate_export", rows = points ? summary.pointclouds : summary.volumes;
        return `<section class="real-spatial-summary"><h3>${points ? "Point cloud" : "Volume"} integrity</h3><p>${esc(points ? summary.pointcloud_count : summary.volume_count)} whole sources · ${esc(points ? summary.point_count : summary.voxel_count)} ${points ? "points" : "voxels"}</p><p>Family scope: ${esc(summary.family_scope)}</p>${rows.map(row => `<p>${esc(row.name)} · ${esc(row.units)} · ${points ? esc(row.coordinate_system.frame) : esc(row.shape.join(" × ")) + " [z,y,x] · uint8"}</p>`).join("")}<details><summary>Native coordinates, scope and limitations</summary><ul>${summary.limitations.map(item => `<li>${esc(item)}</li>`).join("")}</ul><pre>${esc(JSON.stringify(rows, null, 2))}</pre></details></section>`;
      }
      return `<section class="real-sequence-summary"><h3>Sequence integrity</h3><p>${esc(summary.sequence_count)} sequences · ${esc(summary.frame_count)} accepted frames</p><p>Family scope: ${esc(summary.family_scope)}</p>${(summary.sequences || []).map(sequence => `<p>${esc(sequence.name)} · ${esc(sequence.geometry.counts.join(" × "))} cells<br>Time: ${esc(sequence.frame_index[0].time_s)}–${esc(sequence.frame_index.at(-1).time_s)} ${esc(sequence.units.time)} · spacing ${esc(sequence.geometry.spacing_m.join(" × "))} m</p>`).join("")}<details><summary>Native units, validation scope and limitations</summary><ul>${(summary.limitations || []).map(item => `<li>${esc(item)}</li>`).join("")}</ul>${(summary.sequences || []).map(sequence => `<h4>${esc(sequence.name)}</h4><p>Declared units: ${esc(JSON.stringify(sequence.units))}</p><pre>${esc(JSON.stringify({geometry: sequence.geometry, field_types: sequence.field_types, pressure_semantics: sequence.pressure_semantics, technical_validation: sequence.technical_validation, provenance: sequence.provenance}, null, 2))}</pre>`).join("")}</details></section>`;
    }
    function validationHTML() {
      const v = validation;
      return `<span class="badge ${v.valid ? "green" : "amber"}">${esc(v.status)}</span>${(v.errors || []).map(e => `<p class="error-panel"><strong>${esc(e.path)}</strong> · ${esc(e.message)}</p>`).join("")}${v.release ? `<div class="real-preview"><h3>Verified frozen input</h3><p>${v.release.records} ${sourceUnit(v.release.recipe)} · ${esc(JSON.stringify(v.release.split_counts))}</p>${v.release.audio_summary ? `<p>${esc(v.release.audio_summary.coordinate_contract)}</p><p class="muted">${v.release.audio_summary.analyzed_frames.toLocaleString()} analyzed source frames · ${esc(v.release.audio_summary.sample_rates_hz.join(", "))} Hz</p>` : ""}<p class="muted">Release ${esc(v.release.id)}</p>${integrityKind(v.release) ? integritySummaryHTML(v.release, v.release.validation_summary) : `<p class="${v.release.prior_test_exposure?.exposed ? "error-panel" : "muted"}">${v.release.prior_test_exposure?.exposed ? "Previously exposed/reused test material. This is not fresh holdout evidence." : "No prior test-exposure event recorded for these records or canonical content."}</p>`}<a href="/api/workbench/releases/${encoded(v.release.id)}" download>Download verified release ZIP</a></div>` : ""}${v.runtime ? `<details><summary>Installed runtime and adapter identity</summary><pre>${esc(JSON.stringify(v.runtime, null, 2))}</pre></details>` : ""}`;
    }
    function artifactURL(name) { return `/api/workspace/runs/${encoded(run.id)}/artifacts/${encoded(name)}`; }
    function renderCoordinator(){
      if(view!=='runs')return;
      const root=runsRoot.querySelector('#real-coordinator-root');
      if(root){retainFocus(root,()=>{root.innerHTML=coordinator.html();});coordinator.bind(root);}
    }
    async function loadRuns(chosen = runId, quiet = false) {
      const generation = ++runGeneration,session=window.TuldokAuth?.identity()?.credential_id;
      candidatePackages.invalidate();publication.invalidate();coordinator.invalidate();scientific.invalidate();
      const current=()=>generation===runGeneration&&view==='runs'&&session===window.TuldokAuth?.identity()?.credential_id;
      const coordinatorRead=coordinator.load(current);
      if (!quiet) runsRoot.innerHTML = '<p class="real-status" role="status">Loading durable run receipts…</p>';
      try {
        const list = await api("runs");
        const id = list.some(r => r.id === chosen) ? chosen : list[0]?.id;
        let detail = null, rows = null, rowsError = null, progress = null;
        if (id) {
          try { detail = await api("runs/" + encoded(id)); }
          catch (error) {
            // The list's durable receipt remains useful when verifying its
            // artifacts fails. Keep other runs reachable; never trust cached
            // metrics or offer artifacts from the failed detail read.
            detail = { ...list.find(r => r.id === id), metrics: null, artifacts: [],
              artifact_status: {status: "unavailable", message: error.message} };
            rowsError = error.message;
          }
        }
        if(detail&&external.isGraph(detail.graph)&&detail.artifact_status?.status!=='unavailable'){
          try{progress=await api('runs/'+encoded(id)+'/progress');}
          catch{progress=null;}
        }
        if (detail?.state === "completed" && !integrityKind(detail.graph) && !external.isGraph(detail.graph) && !detail.artifact_status) {
          try { rows = await api("runs/" + encoded(id) + "/predictions?split=" + split); }
          catch (error) { rowsError = error.message; }
        }
        if (!current()) return;
        await model.load(detail,current);
        if (!current()) return;
        await fieldEvidence.load(detail,current);
        if (!current()) return;
        await scientific.load(detail,current);
        if (!current()) return;
        await publication.load(detail,current);
        if (!current()) return;
        if(detail)phases.select({kind:'run',id:detail.id},current);else phases.invalidate();
        const packageRead=candidatePackages.load(detail&&external.isGraph(detail.graph)?detail:null,current);
        runs = list; run = detail; runProgress = progress; runId = id || null; predictions = rows; predictionError = rowsError; remember(); renderRuns();
        packageRead.then(()=>{if(current())renderRuns();});
        coordinatorRead.then(()=>{if(current())renderCoordinator();});
      } catch (error) {
        if (!current()) return;
        if ([401,403].includes(error.status)) {run=null;runs=[];predictions=null;model.invalidate();fieldEvidence.invalidate();scientific.invalidate();candidatePackages.invalidate();publication.invalidate();coordinator.invalidate();phases.invalidate();preparation.invalidate();renderRuns();status(error.message,true);return;}
        if (!quiet) {runsRoot.innerHTML = `<div id="real-coordinator-root">${coordinator.html()}</div><div class="error-panel" role="alert">${esc(error.message)}<p>No work has been resubmitted.</p><button id="real-runs-retry">Refresh saved runs</button></div>`;coordinator.bind(runsRoot);coordinatorRead.then(()=>{if(current())renderCoordinator();});}
        else status("Run refresh failed: " + error.message + " Saved results are retained; use Refresh to retry.", true);
        runsRoot.querySelector("#real-runs-retry")?.addEventListener("click", () => loadRuns(chosen));
      } finally {
        if(current())clearTimeout(timer);
        if (current() && run && !terminal.has(run.state)) timer = setTimeout(() => loadRuns(runId, true), 1800);
      }
    }
    function renderRuns() {
      const integrity = integrityKind(run?.graph), externalRun=external.isGraph(run?.graph), metrics = integrity||externalRun ? null : run?.metrics?.validation;
      const openStreams=Array.from(runsRoot.querySelectorAll('details[data-external-stream][open]')).map(node=>node.dataset.externalStream);
      const openDisclosures=Array.from(runsRoot.querySelectorAll('details[data-external-disclosure][open]')).map(node=>node.id);
      retainFocus(runsRoot, () => {
        runsRoot.innerHTML = `<p class="callout"><strong>Real local runs.</strong> Results retain their saved graph and exact admitted inputs. Classification, integrity and external execution receipts retain their own scope and limitations.</p><p class="real-status" role="status"></p><div class="actions"><button id="real-runs-refresh">Refresh saved runs</button><a class="button" href="#pipeline">Open Pipeline</a></div><div id="real-coordinator-root">${coordinator.html()}</div>${!run ? '<div class="panel empty"><h2>No real runs yet</h2><p>Save and validate a recipe in Pipeline, then run it on the local CPU.</p></div>' : `<div class="runs-layout"><aside class="panel"><div class="panel-title"><h2>Runs</h2><span class="badge">${runs.length}</span></div><div class="run-list">${runs.map(r => `<button id="real-run-${r.id}" data-real-run="${r.id}" class="run-item" aria-current="${r.id === runId}"><span class="badge ${r.state === "completed" ? "green" : "amber"}">${esc(r.state)}</span><strong>${esc(r.graph.name)}</strong><small>Graph r${r.graph_revision} · attempt ${r.attempt}</small><small>${esc(r.created_at)}</small></button>`).join("")}</div></aside>
        <article class="panel panel-pad"><div class="meta-row"><span id="real-run-state" class="badge ${run.state === "completed" ? "green" : "amber"}">${esc(run.state)}</span><span class="badge">${externalRun ? "Trusted local executable" : integrity ? `${integrity.name} integrity · no training` : "Real · CPU"}</span><span class="badge">${esc(short(run.id))}</span></div><h2 style="margin-top:14px">${esc(run.graph.name)}</h2><p class="muted">Frozen graph r${run.graph_revision} · attempt ${run.attempt}${externalRun ? "" : " · release " + esc(short(run.release_id))}</p><div class="actions">${(run.input_artifacts || []).map(a => `<a class="button" href="${artifactURL(a.name)}" download>Download verified frozen export</a>`).join("")}</div>
        ${run.error ? `<p class="error-panel" role="alert">${esc(run.error.code)}: ${esc(run.error.message)}</p>` : ""}
        ${run.artifact_status?.status === "unavailable" ? `<p class="error-panel" role="alert">Published artifacts unavailable: ${esc(run.artifact_status.message)}. Saved run identity is retained.</p>` : ""}
        ${!terminal.has(run.state) ? `<div class="real-running"><span class="running-dot" aria-hidden="true"></span><div><strong>${esc(run.progress.stage || run.state)}</strong><p>${externalRun?"Recipe-reported progress appears below when available. Remaining duration is unknown.":"Total work and remaining duration are unknown."} Cancellation completes only after the worker has stopped.</p></div></div><button id="real-cancel" ${run.state === "cancelling" ? "disabled" : ""}>${run.state === "cancelling" ? "Waiting for worker to stop" : "Cancel run"}</button>` : ""}
        ${!externalRun && !run.study_membership && ["failed", "cancelled", "interrupted"].includes(run.state) ? `<button id="real-retry-run">Start a fresh ${integrity ? "validation" : "training"} attempt</button><p class="muted">Reuses verified frozen input.${integrity ? "" : " Partial checkpoints are never resumed."}</p>` : ""}
        ${run.study_membership&&["failed","cancelled","interrupted"].includes(run.state)?'<p>This finite-study attempt has stopped. Prepare another exact trial in <a href="#pipeline">Pipeline</a> before starting new training.</p>':""}
        ${run.state === "unknown" ? '<p class="error-panel">Execution outcome is unresolved. Automatic retry is unavailable; reconcile process and storage state first.</p>' : ""}
        ${!externalRun && !integrity && (run.current_test_exposure?.exposed || run.prior_test_exposure?.exposed) ? '<p class="error-panel">This release contains previously exposed/reused test material. Results cannot be presented as fresh holdout evidence.</p>' : ""}
        <div id="real-phase-root">${phases.html()}</div>${externalRun ? external.runHTML(run,runProgress)+publication.html(run) : integrity ? integritySummaryHTML(run.graph, run.validation_summary) : ""}
        ${!externalRun&&!integrity?model.html(run,predictions):""}${externalRun?candidatePackages.html(run)+fieldEvidence.html(run)+scientific.html(run,runs):""}
        ${metrics ? `<div class="metric-grid"><div class="metric"><strong>${(metrics.accuracy * 100).toFixed(1)}%</strong><span>Validation accuracy</span></div><div class="metric"><strong>${metrics.examples}</strong><span>Validation examples</span></div><div class="metric"><strong>${metrics.macro_f1.toFixed(3)}</strong><span>Validation macro F1</span></div></div>` : ""}
        <div class="${externalRun?'':'run-columns'}">${!externalRun?`<section><h3>Stage evidence</h3>${(run.node_attempts || []).map((stage, i) => `<div class="attempt"><span class="node-index">${i + 1}</span><span>${esc(stage.type === "train" ? trainingTitle(run.graph) : (integrity ? {release: "Frozen release", validate: `Validate ${integrity.name.toLowerCase()} integrity`, publish: "Publish integrity report"}[stage.type] : titles[stage.type]) || stage.type)}</span><small>${esc(stage.state)}</small></div>`).join("")}<details><summary>Bounded progress log</summary><pre>${esc((run.events || []).map(e => `${e.at} [${e.state}] ${e.message}`).join("\n"))}</pre></details></section>`:`<details id="external-lifecycle-events" data-external-disclosure><summary>Run lifecycle events</summary><pre>${esc((run.events || []).map(e => `${e.at} [${e.state}] ${e.message}`).join("\n"))}</pre></details>`}<section><h3>${run.artifact_status?.status==='receipt_verified'?'Recorded outputs; verified on download':'Verified artifacts'}</h3>${run.artifacts.length ? `<ul class="real-artifacts">${run.artifacts.map(a => `<li>${a.locked ? `<span>${esc(a.name)} · test access locked</span>` : `<a href="${artifactURL(a.name)}" download>${esc(a.name)}</a>`}<small>${a.role ? esc(a.role) + " · " : ""}${a.bytes.toLocaleString()} bytes · SHA ${esc(short(a.sha256))}</small>${external.artifactActionHTML(run,a)}</li>`).join("")}</ul>` : '<p class="muted">No published artifacts yet.</p>'}<p class="footnote">${run.artifact_status?.status==='receipt_verified'?'Output receipt verified. Payload bytes are checked individually when requested.':'Every artifact read verifies its frozen hash.'}</p></section></div>
        ${run.state === "completed" && !externalRun && !integrity ? `<section class="real-predictions"><div class="panel-title"><h3>Per-example predictions</h3><span class="badge ${split === "test" ? "amber" : ""}">${esc(split)}${split === "test" ? " · exposed" : ""}</span></div><div class="actions"><button id="real-validation-predictions" ${split === "validation" ? "disabled" : ""}>Validation examples</button><button id="real-test-predictions">${run.test_exposure?.exposed ? "Open exposed test results" : "Expose test results…"}</button></div>${predictionsHTML()}</section>` : ""}
        <details><summary>Frozen identity, source provenance and parameters</summary><pre>${esc(JSON.stringify({ dataset_id: run.dataset_id, run_id: run.id, release_sha256: run.release_sha256, graph_sha256: run.graph_sha256, graph: run.graph, adapter: run.adapter, runtime: run.runtime, parameters: run.parameters, prior_test_exposure: run.prior_test_exposure, current_test_exposure: run.current_test_exposure, test_exposure: run.test_exposure }, null, 2))}</pre></details></article></div>`}`;
      });
      if (notice) { const target = runsRoot.querySelector('.real-status'); target.textContent = notice; target.classList.toggle('error-panel', noticeError); }
      runsRoot.querySelector("#real-runs-refresh").onclick = () => loadRuns();
      coordinator.bind(runsRoot);
      const scientificGeneration=runGeneration,scientificRunId=run?.id;
      scientific.bind(runsRoot,run,runs,renderRuns,()=>view==='runs'&&scientificGeneration===runGeneration&&runId===scientificRunId,id=>loadRuns(id));
      runsRoot.querySelectorAll("[data-real-run]").forEach(button => button.onclick = () => { split = "validation"; selectedCell = null; loadRuns(button.dataset.realRun); });
      for(const button of runsRoot.querySelectorAll('[data-import-run-artifact]'))button.onclick=()=>{
        const selected=run,artifact=selected.artifacts.find(item=>item.name===button.dataset.importRunArtifact);
        action(()=>external.importArtifact(selected,artifact));
      };
      runsRoot.querySelector("#real-cancel")?.addEventListener("click", () => action(async () => {
        run = await api("runs/" + encoded(run.id) + "/cancel", {}); status("Cancellation requested. Waiting for confirmed worker cessation."); await loadRuns(run.id, true);
      }));
      for(const name of openStreams)runsRoot.querySelector('details[data-external-stream="'+name+'"]')?.setAttribute('open','');
      for(const id of openDisclosures)runsRoot.querySelector('#'+CSS.escape(id))?.setAttribute('open','');
      runsRoot.querySelector("#real-retry-run")?.addEventListener("click", () => action(async () => {
        const receiptKey = "retry:" + run.id;
        const state = history.state?.realRetries || {};
        const request_key = state[receiptKey] || crypto.randomUUID();
        history.replaceState({ ...history.state, realRetries: { ...state, [receiptKey]: request_key } }, "");
        const result = await api("runs/" + encoded(run.id) + "/retry", { request_key });
        runId = result.id; split = "validation"; selectedCell = null; remember(); await loadRuns(runId, true);
      }));
      runsRoot.querySelector("#real-validation-predictions")?.addEventListener("click", () => { split = "validation"; selectedCell = null; loadRuns(runId, true); });
      runsRoot.querySelector("#real-test-predictions")?.addEventListener("click", () => {
        if (!run.test_exposure?.exposed) {
          const reason = prompt("Viewing test results creates a durable exposure record. Reusing these records or canonical content must be labelled exposed, not fresh holdout evidence. Enter the reason for inspection:");
          if (!reason?.trim()) return;
          action(async () => { await api("runs/" + encoded(run.id) + "/expose-test", { reason: reason.trim() }); split = "test"; selectedCell = null; await loadRuns(runId, true); });
        } else { split = "test"; selectedCell = null; loadRuns(runId, true); }
      });
      runsRoot.querySelectorAll("[data-real-cell]").forEach(button => button.onclick = () => { selectedCell = button.dataset.realCell; renderRuns(); runsRoot.querySelector("#real-examples-heading")?.focus(); });
      runsRoot.querySelectorAll("[data-correct-record]").forEach(button => button.onclick = () => {
        const prediction = predictions.rows.find(p => p.id === button.dataset.correctRecord);
        openRecord({ ...prediction, run_id: run.id, release_id: run.release_id });
      });
      const displayedRun=runId,displayedGeneration=runGeneration,credential=window.TuldokAuth?.identity()?.credential_id;
      publication.bind(runsRoot);phases.bind(runsRoot);
      fieldEvidence.bind(runsRoot,run,renderRuns,()=>view==='runs'&&runId===displayedRun&&runGeneration===displayedGeneration&&credential===window.TuldokAuth?.identity()?.credential_id);
      model.bind(runsRoot,run,runs,renderRuns,()=>view==='runs'&&runId===displayedRun&&runGeneration===displayedGeneration&&credential===window.TuldokAuth?.identity()?.credential_id);
      candidatePackages.bind(runsRoot,run,renderRuns,()=>view==='runs'&&runId===displayedRun&&runGeneration===displayedGeneration&&credential===window.TuldokAuth?.identity()?.credential_id,id=>loadRuns(id));
      if (busy) runsRoot.querySelectorAll("button,input,select").forEach(e => e.disabled = true);
    }
    function predictionsHTML() {
      if (predictionError) return `<p class="error-panel" role="alert">Predictions unavailable: ${esc(predictionError)}. Refresh saved runs to retry.</p>`;
      if (!predictions) return '<p class="muted">Predictions unavailable.</p>';
      const vocabulary = predictions.class_vocabulary,
        rows = predictions.rows,
        counts = vocabulary.map((_, a) => vocabulary.map((__, b) => rows.filter(r => r.truth_index === a && r.predicted_index === b).length)),
        filtered = selectedCell ? rows.filter(r => `${r.truth_index}:${r.predicted_index}` === selectedCell) : rows;
      return `<p class="muted">Rows are frozen targets; columns are model predictions. Select a count to inspect exact examples.</p><div class="real-table-wrap"><table class="real-matrix"><thead><tr><th scope="col">Target / prediction</th>${vocabulary.map(v => `<th scope="col">${esc(v.label)}</th>`).join("")}</tr></thead><tbody>${vocabulary.map((v, a) => `<tr><th scope="row">${esc(v.label)}</th>${vocabulary.map((w, b) => `<td><button data-real-cell="${a}:${b}" aria-label="${esc(v.label)} predicted ${esc(w.label)}: ${counts[a][b]} examples" ${a !== b && counts[a][b] ? 'class="error-cell"' : ""}>${counts[a][b]}</button></td>`).join("")}</tr>`).join("")}</tbody></table></div><h3 id="real-examples-heading" tabindex="-1">${selectedCell ? "Selected cell" : "All " + split + " examples"} · ${filtered.length}</h3>${!filtered.length ? '<p>No examples in this cell.</p>' : filtered.map(p => `<div class="prediction"><strong>${esc(p.truth_label)} → ${esc(p.predicted_label)}</strong><p>${esc(short(p.id))} · source r${p.source_revision} · frozen annotation r${p.revision}</p>${p.start_frame !== undefined ? `<p class="audio-result-reference">Source channel ${p.channel + 1} (index ${p.channel}) · frames [${p.start_frame}, ${p.end_frame}) · ${p.sample_rate_hz} Hz<br><span class="muted">Original WAV ${esc(short(p.source_sha256))} · PCM ${esc(short(p.pcm_sha256))}</span></p>` : ""}<p class="muted">${p.current_record?.revision ? `Current annotation r${p.current_record.revision}${p.current_record.changed ? " · changed since this run" : ""}` : "Current record unavailable"}</p><button data-correct-record="${esc(p.id)}" ${p.current_record?.revision ? "" : "disabled"}>Open current record in Data →</button><p class="footnote">Editing creates a new current revision. This prediction and its frozen target remain unchanged.</p></div>`).join("")}`;
    }
    async function openGraph(id,isCurrent=()=>true){
        if(dirty()&&!confirm("Discard unsaved recipe changes to open this graph?"))return false;
        if(busy)throw Error("Finish the current Pipeline action before opening another graph.");
        const previous=graph,previousState=JSON.stringify(graph);
        const document=await api("graphs/"+encoded(id));
        if(!isCurrent()||graph!==previous||JSON.stringify(graph)!==previousState)return false;
        adopt(document);return true;
    }
    async function openRunById(id,isCurrent=()=>true){
        const credential=window.TuldokAuth?.identity()?.credential_id,selected=await api('runs/'+encoded(id));
        if(!isCurrent()||credential!==window.TuldokAuth?.identity()?.credential_id)return false;
        if(selected.id!==id)throw Error('The admitted Run could not be identified.');
        ++runGeneration;coordinator.invalidate();publication.invalidate();phases.invalidate();preparation.invalidate();model.invalidate();fieldEvidence.invalidate();scientific.invalidate();candidatePackages.invalidate();run=selected;runId=id;predictions=null;predictionError=null;remember();return true;
    }
    window.addEventListener('tuldok-session',()=>{
      ++runGeneration;++loadGeneration;clearTimeout(timer);coordinator.invalidate();publication.invalidate();phases.invalidate();preparation.invalidate();lineage.sessionChanged();runProgress=null;model.invalidate();fieldEvidence.invalidate();scientific.invalidate();candidatePackages.invalidate();model.sessionChanged();
      if(view==='pipeline'){definitions=null;graph=null;graphs=[];releases=[];pipelineRoot.innerHTML='<p>Session changed. Refreshing current catalog…</p>';if(window.TuldokAuth?.identity())loadPipeline();}
      if(view==='runs'){run=null;runs=[];renderRuns();if(window.TuldokAuth?.identity())loadRuns();}
    });
    return {
      isDirty: dirty,
      openGraph,openRunById,
      identity: () => context?.dataset_id,
      async show(next) {
        view = next; ++loadGeneration; ++runGeneration; clearTimeout(timer);coordinator.invalidate();publication.invalidate();phases.invalidate();preparation.invalidate();lineage.invalidate();model.invalidate(next==='runs');fieldEvidence.invalidate();scientific.invalidate();candidatePackages.invalidate();
        if (next === "pipeline") {
          if (definitions && graph) renderPipeline(); else await loadPipeline();
        } else if (next === "runs") await loadRuns();
      },
    };
  };
})();
