"use strict";
// Real HTTP boundary. Fixture state is never read or submitted by this module.
// Server-owned graph definitions and validation determine execution eligibility.
(() => {
  const esc = (s) => window.workspaceEscape(s),
    copy = (v) => structuredClone(v),
    short = (s) => String(s || "").slice(0, 12),
    encoded = encodeURIComponent,
    terminal = new Set(["completed", "failed", "cancelled", "interrupted", "unknown"]);
  async function api(route, body, selectedVersion) {
    const headers = {"Content-Type": "application/json"};
    const path = route.split('?')[0].split('/');
    const modelRecipe=body?.recipe||body?.document?.recipe;
    const modelGraph=['image_classification_model_v2','text_classification_model_v2','audio_classification_model_v2'].includes(modelRecipe);
    const operation = path[0]==='graphs'&&modelGraph ? (path.length===1?'graphs.create':'graphs.save') : path[0] === 'models' ? (path.length === 1 ? (body === undefined ? 'models.list' : 'models.create') : path[2] === 'publish' ? 'models.publish' : body === undefined ? 'models.get' : 'models.save') :
      path[0] === 'studies' ? (path.length === 1 ? (body === undefined ? 'studies.list' : 'studies.create') : path[2] ? ({'prepare-trial':'studies.prepare_trial',continue:'studies.continue',admit:'studies.admit',reconcile:'studies.reconcile',approve:'studies.approve','prepare-package':'studies.prepare_package','prepare-verifier':'studies.prepare_verifier','select-candidate':'studies.select_candidate'})[path[2]] : body === undefined ? 'studies.get' : 'studies.save') :
      path[0] === 'candidates' ? (path[2]==='package-state'?'studies.package_state':'studies.candidate') : path[0] === 'runs' && path[2] === 'candidates' ? 'studies.candidates' : path[0] === 'runs' && path[2] === 'model-evidence' ? 'runs.model_evidence' : path[0] === 'runs' && path[2] === 'compare-model-evidence' ? 'runs.compare_model_evidence' : null;
    if (operation) {
      const version=operation==='runs.model_evidence'&&selectedVersion===2?2:operation==='runs.compare_model_evidence'?2:operation.startsWith('graphs.')?(modelRecipe==='image_classification_model_v2'?2:3):1;
      const sha = window.WorkspaceModelContracts?.[version===3||operation==='runs.model_evidence'&&version===2?operation+'/'+version:operation];
      if (!sha) throw Error('This model operation has no supported local contract: ' + operation);
      headers['Tuldok-Operation-Contract'] = operation + '/' + version + '/' + sha;
    }
    const response = await (globalThis.TuldokAuth?.fetch || fetch)("/api/workspace/" + route, {
      ...(body === undefined ? {} : {method: "POST", body: JSON.stringify(body)}), headers,
    });
    const value = await response.json();
    if (!response.ok) {
      const error = Error(value.error || "Workspace request failed.");
      error.code = value.code; error.status = response.status; throw error;
    }
    return value;
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
      onImported:openImportedRecord,
      onRun:result=>{run=result;runId=result.id;predictions=null;predictionError=null;remember();status("External attempt admitted with exact material approval.");openRun();}});
    const model = WorkspaceModel({api, announce, openRecord, getIntent:()=>loadGeneration, getView:()=>view,
      openRun:result=>{run=result;runId=result.id;remember();if(view==='runs')loadRuns(runId);else openRun();}});
    const fieldEvidence = window.WorkspaceFieldEvidence({api,announce});
    const candidatePackages = window.WorkspaceCandidatePackageEvidence({api});
    function mountModel() {
      const container=document.createElement('div');container.id='real-model-root';pipelineRoot.prepend(container);
      model.configure({definitions,releases,context});model.mount(container);
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
      render();
      if (focused) root.querySelector("#" + CSS.escape(focused))?.focus({ preventScroll: true });
    }
    function adopt(document) {
      graph = document; graphId = graph.id; saved = JSON.stringify(graph);
      graphs = graphs.map(item => item.id === graph.id ? copy(graph) : item);
      validation = null; external.invalidate(true); undo = []; redo = []; remember();
    }
    function change(fn, render = true) {
      undo.push(copy(graph)); if (undo.length > 40) undo.shift(); redo = [];
      fn(); validation = null;
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
    function renderPipeline() {
      if (!definitions) return;
      if(external.isGraph(graph)){
        retainFocus(pipelineRoot, () => external.renderPipeline(pipelineRoot,{graph,graphs,busy,choose:id=>{if(dirty()&&!confirm("Discard unsaved recipe changes?")){renderPipeline();return;}action(async()=>adopt(await api("graphs/"+encoded(id))));}}));
        if(notice){const target=pipelineRoot.querySelector('.real-status');target.textContent=notice;target.classList.toggle('error-panel',noticeError);}mountModel();return;
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
    async function loadRuns(chosen = runId, quiet = false) {
      const generation = ++runGeneration,session=window.TuldokAuth?.identity()?.credential_id;
      candidatePackages.invalidate();
      const current=()=>generation===runGeneration&&view==='runs'&&session===window.TuldokAuth?.identity()?.credential_id;
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
        const packageRead=candidatePackages.load(detail&&external.isGraph(detail.graph)?detail:null,current);
        runs = list; run = detail; runProgress = progress; runId = id || null; predictions = rows; predictionError = rowsError; remember(); renderRuns();
        packageRead.then(()=>{if(current())renderRuns();});
      } catch (error) {
        if (!current()) return;
        if ([401,403].includes(error.status)) {run=null;runs=[];predictions=null;model.invalidate();fieldEvidence.invalidate();candidatePackages.invalidate();renderRuns();status(error.message,true);return;}
        if (!quiet) runsRoot.innerHTML = `<div class="error-panel" role="alert">${esc(error.message)}<p>No work has been resubmitted.</p><button id="real-runs-retry">Refresh saved runs</button></div>`;
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
        runsRoot.innerHTML = `<p class="callout"><strong>Real local runs.</strong> Results retain their saved graph and exact admitted inputs. Classification, integrity and external execution receipts retain their own scope and limitations.</p><p class="real-status" role="status"></p><div class="actions"><button id="real-runs-refresh">Refresh saved runs</button><a class="button" href="#pipeline">Open Pipeline</a></div>${!run ? '<div class="panel empty"><h2>No real runs yet</h2><p>Save and validate a recipe in Pipeline, then run it on the local CPU.</p></div>' : `<div class="runs-layout"><aside class="panel"><div class="panel-title"><h2>Runs</h2><span class="badge">${runs.length}</span></div><div class="run-list">${runs.map(r => `<button id="real-run-${r.id}" data-real-run="${r.id}" class="run-item" aria-current="${r.id === runId}"><span class="badge ${r.state === "completed" ? "green" : "amber"}">${esc(r.state)}</span><strong>${esc(r.graph.name)}</strong><small>Graph r${r.graph_revision} · attempt ${r.attempt}</small><small>${esc(r.created_at)}</small></button>`).join("")}</div></aside>
        <article class="panel panel-pad"><div class="meta-row"><span id="real-run-state" class="badge ${run.state === "completed" ? "green" : "amber"}">${esc(run.state)}</span><span class="badge">${externalRun ? "Trusted local executable" : integrity ? `${integrity.name} integrity · no training` : "Real · CPU"}</span><span class="badge">${esc(short(run.id))}</span></div><h2 style="margin-top:14px">${esc(run.graph.name)}</h2><p class="muted">Frozen graph r${run.graph_revision} · attempt ${run.attempt}${externalRun ? "" : " · release " + esc(short(run.release_id))}</p><div class="actions">${(run.input_artifacts || []).map(a => `<a class="button" href="${artifactURL(a.name)}" download>Download verified frozen export</a>`).join("")}</div>
        ${run.error ? `<p class="error-panel" role="alert">${esc(run.error.code)}: ${esc(run.error.message)}</p>` : ""}
        ${run.artifact_status?.status === "unavailable" ? `<p class="error-panel" role="alert">Published artifacts unavailable: ${esc(run.artifact_status.message)}. Saved run identity is retained.</p>` : ""}
        ${!terminal.has(run.state) ? `<div class="real-running"><span class="running-dot" aria-hidden="true"></span><div><strong>${esc(run.progress.stage || run.state)}</strong><p>${externalRun?"Recipe-reported progress appears below when available. Remaining duration is unknown.":"Total work and remaining duration are unknown."} Cancellation completes only after the worker has stopped.</p></div></div><button id="real-cancel" ${run.state === "cancelling" ? "disabled" : ""}>${run.state === "cancelling" ? "Waiting for worker to stop" : "Cancel run"}</button>` : ""}
        ${!externalRun && !run.study_membership && ["failed", "cancelled", "interrupted"].includes(run.state) ? `<button id="real-retry-run">Start a fresh ${integrity ? "validation" : "training"} attempt</button><p class="muted">Reuses verified frozen input.${integrity ? "" : " Partial checkpoints are never resumed."}</p>` : ""}
        ${run.study_membership&&["failed","cancelled","interrupted"].includes(run.state)?'<p>This finite-study attempt has stopped. Prepare another exact trial in <a href="#pipeline">Pipeline</a> before starting new training.</p>':""}
        ${run.state === "unknown" ? '<p class="error-panel">Execution outcome is unresolved. Automatic retry is unavailable; reconcile process and storage state first.</p>' : ""}
        ${!externalRun && !integrity && (run.current_test_exposure?.exposed || run.prior_test_exposure?.exposed) ? '<p class="error-panel">This release contains previously exposed/reused test material. Results cannot be presented as fresh holdout evidence.</p>' : ""}
        ${externalRun ? external.runHTML(run,runProgress) : integrity ? integritySummaryHTML(run.graph, run.validation_summary) : ""}
        ${!externalRun&&!integrity?model.html(run,predictions):""}${externalRun?candidatePackages.html(run)+fieldEvidence.html(run):""}
        ${metrics ? `<div class="metric-grid"><div class="metric"><strong>${(metrics.accuracy * 100).toFixed(1)}%</strong><span>Validation accuracy</span></div><div class="metric"><strong>${metrics.examples}</strong><span>Validation examples</span></div><div class="metric"><strong>${metrics.macro_f1.toFixed(3)}</strong><span>Validation macro F1</span></div></div>` : ""}
        <div class="${externalRun?'':'run-columns'}">${!externalRun?`<section><h3>Stage evidence</h3>${(run.node_attempts || []).map((stage, i) => `<div class="attempt"><span class="node-index">${i + 1}</span><span>${esc(stage.type === "train" ? trainingTitle(run.graph) : (integrity ? {release: "Frozen release", validate: `Validate ${integrity.name.toLowerCase()} integrity`, publish: "Publish integrity report"}[stage.type] : titles[stage.type]) || stage.type)}</span><small>${esc(stage.state)}</small></div>`).join("")}<details><summary>Bounded progress log</summary><pre>${esc((run.events || []).map(e => `${e.at} [${e.state}] ${e.message}`).join("\n"))}</pre></details></section>`:`<details id="external-lifecycle-events" data-external-disclosure><summary>Run lifecycle events</summary><pre>${esc((run.events || []).map(e => `${e.at} [${e.state}] ${e.message}`).join("\n"))}</pre></details>`}<section><h3>${run.artifact_status?.status==='receipt_verified'?'Recorded outputs; verified on download':'Verified artifacts'}</h3>${run.artifacts.length ? `<ul class="real-artifacts">${run.artifacts.map(a => `<li>${a.locked ? `<span>${esc(a.name)} · test access locked</span>` : `<a href="${artifactURL(a.name)}" download>${esc(a.name)}</a>`}<small>${a.role ? esc(a.role) + " · " : ""}${a.bytes.toLocaleString()} bytes · SHA ${esc(short(a.sha256))}</small>${external.artifactActionHTML(run,a)}</li>`).join("")}</ul>` : '<p class="muted">No published artifacts yet.</p>'}<p class="footnote">${run.artifact_status?.status==='receipt_verified'?'Output receipt verified. Payload bytes are checked individually when requested.':'Every artifact read verifies its frozen hash.'}</p></section></div>
        ${run.state === "completed" && !externalRun && !integrity ? `<section class="real-predictions"><div class="panel-title"><h3>Per-example predictions</h3><span class="badge ${split === "test" ? "amber" : ""}">${esc(split)}${split === "test" ? " · exposed" : ""}</span></div><div class="actions"><button id="real-validation-predictions" ${split === "validation" ? "disabled" : ""}>Validation examples</button><button id="real-test-predictions">${run.test_exposure?.exposed ? "Open exposed test results" : "Expose test results…"}</button></div>${predictionsHTML()}</section>` : ""}
        <details><summary>Frozen identity, source provenance and parameters</summary><pre>${esc(JSON.stringify({ dataset_id: run.dataset_id, run_id: run.id, release_sha256: run.release_sha256, graph_sha256: run.graph_sha256, graph: run.graph, adapter: run.adapter, runtime: run.runtime, parameters: run.parameters, prior_test_exposure: run.prior_test_exposure, current_test_exposure: run.current_test_exposure, test_exposure: run.test_exposure }, null, 2))}</pre></details></article></div>`}`;
      });
      if (notice) { const target = runsRoot.querySelector('.real-status'); target.textContent = notice; target.classList.toggle('error-panel', noticeError); }
      runsRoot.querySelector("#real-runs-refresh").onclick = () => loadRuns();
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
    window.addEventListener('tuldok-session',()=>{
      ++runGeneration;++loadGeneration;clearTimeout(timer);runProgress=null;model.invalidate();fieldEvidence.invalidate();candidatePackages.invalidate();model.sessionChanged();
      if(view==='pipeline'){definitions=null;graph=null;graphs=[];releases=[];pipelineRoot.innerHTML='<p>Session changed. Refreshing current catalog…</p>';if(window.TuldokAuth?.identity())loadPipeline();}
      if(view==='runs'){run=null;runs=[];renderRuns();if(window.TuldokAuth?.identity())loadRuns();}
    });
    return {
      isDirty: dirty,
      async openGraph(id,isCurrent=()=>true){
        if(dirty()&&!confirm("Discard unsaved recipe changes to open this graph?"))return false;
        if(busy)throw Error("Finish the current Pipeline action before opening another graph.");
        const previous=graph,previousState=JSON.stringify(graph);
        const document=await api("graphs/"+encoded(id));
        if(!isCurrent()||graph!==previous||JSON.stringify(graph)!==previousState)return false;
        adopt(document);return true;
      },
      async openRunById(id,isCurrent=()=>true){
        const credential=window.TuldokAuth?.identity()?.credential_id,selected=await api('runs/'+encoded(id));
        if(!isCurrent()||credential!==window.TuldokAuth?.identity()?.credential_id)return false;
        if(selected.id!==id)throw Error('The admitted Run could not be identified.');
        ++runGeneration;model.invalidate();fieldEvidence.invalidate();candidatePackages.invalidate();run=selected;runId=id;predictions=null;predictionError=null;remember();return true;
      },
      identity: () => context?.dataset_id,
      async show(next) {
        view = next; ++loadGeneration; ++runGeneration; clearTimeout(timer);model.invalidate();fieldEvidence.invalidate();candidatePackages.invalidate();
        if (next === "pipeline") {
          if (definitions && graph) renderPipeline(); else await loadPipeline();
        } else if (next === "runs") await loadRuns();
      },
    };
  };
})();
