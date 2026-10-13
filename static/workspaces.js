"use strict";
window.workspaceEscape = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
(() => {
  const $ = (id) => document.getElementById(id),
    esc = window.workspaceEscape,
    service = WorkspaceService;
  let storage;
  try {
    storage = localStorage;
  } catch (error) {
    storage = {
      getItem() {
        throw error;
      },
      setItem() {
        throw error;
      },
      removeItem() {
        throw error;
      },
    };
  }
  let store = null,
    pipeline = null,
    runs = null;
  let catalogImportIntent=0;
  let workspaceIntent = 0, fragmentIntent = null, realCorrection = null;
  function invalidateCorrection(navigation=true) {
    workspaceIntent++;if(navigation)catalogImportIntent++;
    $("catalog-frame").contentWindow?.TuldokWorkspaceData?.cancelRecordOpen?.();
  }
  function renderCorrection(record = catalogContext?.record) {
    const banner = $("real-correction-context");
    banner.hidden = source !== "catalog" || !realCorrection || record?.id !== realCorrection.id;
    if (banner.hidden) return;
    const p = realCorrection;
    banner.textContent = `Correction from ${p.split} run ${p.run_id.slice(0, 12)}. Frozen target: ${p.truth_label}; source r${p.source_revision}, annotation r${p.revision}. Current annotation r${record.revision}. Save and review deliberately, then select current revisions and freeze a new release. The old result stays unchanged.`;
  }
  const real = WorkspaceReal({
    pipelineRoot: $("real-pipeline-root"),
    runsRoot: $("real-runs-root"),
    announce,
    openRun: () => { location.hash = "runs"; },
    openRecord: async (prediction) => {
      const bridge = $("catalog-frame").contentWindow?.TuldokWorkspaceData;
      if (!bridge) { announce("Open Data once to load the current catalog editor.", true); return; }
      const intent = ++workspaceIntent;
      try {
        const result = await bridge.openCurrentRecord(prediction.id);
        if (intent !== workspaceIntent || source !== "catalog" || currentView !== "runs") return;
        if (result.kind !== "available") { announce(result.message, true); return; }
        realCorrection = { ...prediction };
        renderCorrection(result.record);
        location.hash = "data";
      } catch (error) { announce(error.message, true); }
    },
  });
  $("dataset").disabled = true;
  let fixtures = null,
    active = "fixture-image",
    selected = new Set(),
    draftDirty = false,
    draftLabel = null,
    source = "fixtures",
    loadEpoch = 0,
    lastFocus = {},
    currentView = null,
    pendingSource = null,
    catalogContext = null,
    correction = null;
  // Navigation memory is scoped to this browser history entry, not a durable
  // dataset identity. Live references are re-read and revision-checked on reload.
  const remembered = history.state?.workspace;
  if (remembered?.version === 1) {
    if (["fixtures", "catalog"].includes(remembered.source) || (typeof remembered.source === "string" && remembered.source.startsWith("project:") && remembered.source.length > 8))
      source = remembered.source;
    if (typeof remembered.active === "string") active = remembered.active;
    if (Array.isArray(remembered.selected))
      selected = new Set(
        remembered.selected.filter((id) => typeof id === "string"),
      );
    catalogContext = remembered.catalog || null;
  }
  if (source.startsWith("project:")) {
    const option=document.createElement("option");option.value=source;option.textContent="Remembered project";$("dataset").append(option);$("dataset").value=source;
  }
  const projects = WorkspaceProjects({select:$("dataset"),
    roots:{data:$("project-data-root"),pipeline:$("project-pipeline-root"),runs:$("project-runs-root")},
    announce,switchSource,contextChanged:context,openCatalogRecord});
  async function openCatalogRecord(id) {
    try {
    switchSource("catalog");
    location.hash="#data";
    await new Promise(resolve=>setTimeout(resolve,0));
    const importIntent=catalogImportIntent,deadline=Date.now()+10000;
    while(importIntent===catalogImportIntent&&source==="catalog" && Date.now()<deadline) {
      const bridge=$("catalog-frame").contentWindow?.TuldokWorkspaceData;
      if(bridge&&catalogReady&&!restoringCatalog&&currentView==="data") {
        const intent=workspaceIntent;
        const result=await bridge.openImportedRecord(id);
        if(intent!==workspaceIntent||source!=="catalog")return;
        catalogRestoreNotice=null;
        $("catalog-status").textContent=result.kind==="available"?"Imported scientific fields ready.":`Imported ${id}. ${result.message}`;
        return;
      }
      await new Promise(resolve=>setTimeout(resolve,50));
    }
    announce(`Imported ${id}. Open it from the current catalog.`);
    } catch(error) {
      const message=`Imported ${id}. Catalog opening failed: ${error.message}`;
      $("catalog-status").textContent=message;announce(message);
    }
  }
  let restoringCatalog = false,
    catalogRestoreNotice = null;
  function remember() {
    // Keep context writes out of a pending fragment navigation.
    if (fragmentIntent !== null && location.hash !== fragmentIntent) return;
    history.replaceState(
      {
        ...history.state,
        workspace: {
          ...history.state?.workspace,
          version: 1,
          source,
          active,
          selected: [...selected],
          catalog: catalogContext,
        },
      },
      "",
    );
  }
  function announce(message, error = false) {
    $("workspace-status").textContent = message;
    $("workspace-status").style.color = error ? "#a02d26" : "";
  }
  function fixtureDirty() {
    return draftDirty || pipeline?.isDirty();
  }
  function catalogDirty() {
    return (
      $("catalog-frame").contentWindow?.TuldokWorkspaceData?.snapshot().dirty ||
      false
    );
  }
  function context() {
    renderCorrection();
    if (!restoringCatalog) remember();
    if (source === "fixtures")
      $("context").textContent =
        `fixture-dataset-v1 · ${selected.size} selected · ${draftDirty ? "unsaved fixture draft" : "authored CC0 examples"} · release fixture-release-v1`;
    else if (source.startsWith("project:"))
      $("context").textContent = projects.label() + " · inspection only · external references";
    else
      $("context").textContent = catalogContext
        ? `${catalogContext.selection.length} exact revisions selected · ${catalogContext.record?.name || "No active record"} · ${catalogContext.dirty ? "unsaved edits" : "saved state"}${real.identity() ? " · catalog " + real.identity().slice(0, 12) : " · current catalog handle"}`
        : "Current catalog handle · loading existing Data owner";
  }
  function visual(record) {
    if (record.kind === "image")
      return '<svg viewBox="0 0 300 200" role="img" aria-label="Authored blue square on a pale background"><defs><pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse"><path d="M 20 0 L 0 0 0 20" fill="none" stroke="#e1e7ee"/></pattern></defs><rect width="300" height="200" fill="url(#grid)"/><rect x="80" y="30" width="140" height="140" rx="3" fill="#5c80e6"/><path d="M80 22h140M72 30v140" stroke="#aebbd4"/><text x="150" y="193" text-anchor="middle" fill="#687991" font-size="11">128 × 128 · authored representation</text></svg>';
    if (record.kind === "text")
      return `<blockquote>${esc(record.representation.text)}</blockquote>`;
    if (record.kind === "audio")
      return '<div><svg viewBox="0 0 300 160" role="img" aria-label="Illustration of two synthetic audio pulses, not a playable waveform"><path d="M0 50h40l3-30 3 60 3-40 3 20 3-10h90l3-30 3 60 3-40 3 20 3-10h140M0 110h80l3-25 3 50 3-35 3 20 3-10h90l3-25 3 50 3-35 3 20 3-10h100" fill="none" stroke="#6079c9" stroke-width="2"/></svg><p class="muted">Synthetic pulse illustration · playback unavailable</p></div>';
    if (record.kind === "mesh" || record.kind === "point_cloud")
      return `<svg viewBox="0 0 300 200" role="img" aria-label="${record.kind === "mesh" ? "Tetrahedron" : "Four points"} fixture projection">${record.kind === "mesh" ? '<path d="M150 25L55 145 235 160zM150 25L150 115 55 145M150 115L235 160" fill="#7898e833" stroke="#526fba" stroke-width="2"/>' : ""}${[
        [150, 25],
        [55, 145],
        [235, 160],
        [150, 115],
      ]
        .map(([x, y]) => `<circle cx="${x}" cy="${y}" r="5" fill="#526fba"/>`)
        .join(
          "",
        )}<text x="150" y="190" text-anchor="middle" fill="#687991" font-size="11">Authored projection · right-handed XYZ · metres</text></svg>`;
    if (record.kind === "volume")
      return '<svg viewBox="0 0 300 200" role="img" aria-label="Two by two authored volume slice"><rect x="70" y="10" width="160" height="160" fill="#dce5f5"/><path d="M150 10h80v80h-80zM70 90h80v80H70z" fill="#7594d5"/><text x="150" y="195" text-anchor="middle" fill="#687991" font-size="11">Illustrative slice · grid 2 × 2 × 2 · 1/2/3 mm</text></svg>';
    return '<div class="numeric">t = 0.0 s   ●────────────\nt = 0.5 s   ──────●──────\nt = 1.0 s   ────────────●<br>Whole trajectory · three authored frames</div>';
  }
  function renderData() {
    $("fixture-data").hidden = source !== "fixtures";
    $("catalog-data").hidden = source !== "catalog";
    context();
    if (source === "catalog") {
      if (!$("catalog-frame").getAttribute("src"))
        $("catalog-frame").src = "/workbench?workspace=1";
      return;
    }
    if (source.startsWith("project:")) return;
    if (!fixtures || !store) return;
    const record = fixtures.records.find((r) => r.id === active);
    if (!record) {
      $("fixture-data").textContent =
        "Source unavailable. Choose another fixture explicitly.";
      return;
    }
    const capability = service.capabilities[record.kind],
      stored = store.read(),
      draft = stored.kind === "fixture" ? stored.value.drafts[record.id] : null;
    const label =
      draftDirty && draftLabel !== null
        ? draftLabel
        : draft?.label || record.representation.class || "";
    $("fixture-data").innerHTML =
      `<p class="callout"><strong>Authored fixtures · isolated from your catalog.</strong> These seven tiny examples show contracts and capability states. Choose “Current local catalog” above to import, annotate, review and freeze real data.</p><div class="grid-data"><aside class="panel"><div class="panel-title"><h2>Records</h2><span class="badge">7 fixtures</span></div><div class="record-list">${fixtures.records.map((r) => `<div class="record-row"><input type="checkbox" data-select="${r.id}" aria-label="Select ${esc(r.name)}" ${selected.has(r.id) ? "checked" : ""}><button data-record="${r.id}" aria-current="${r.id === active}"><span class="record-symbol">${{ image: "▧", text: "T", audio: "≋", mesh: "◇", point_cloud: "∴", volume: "▦", sequence: "↝" }[r.kind]}</span><span>${esc(r.name)}<small>${esc(r.kind.replace("_", " "))} · fixture</small></span></button></div>`).join("")}</div><div class="collection-foot">${selected.size} selected · source and annotation r1<br>Fixture selection never freezes a real release.</div></aside><article class="panel"><div class="panel-title"><h2>${esc(record.name)}</h2><span class="badge amber">Fixture</span></div><div class="source-preview">${visual(record)}</div><div class="panel-pad"><div class="meta-row"><span class="badge">${esc(record.schema)}</span><span class="badge">Saved: draft · r${draft?.revision || 1}</span></div>${correction && record.id === correction.record_id ? `<p class="callout">Correction from a fixture validation error. Frozen annotation r${correction.annotation_revision}; current draft r${draft?.revision || 1}. Saving a correction leaves historical results unchanged.</p>` : ""}<dl class="metadata"><dt>Source identity</dt><dd>${esc(record.id)} · source r1</dd><dt>Rights note</dt><dd>${esc(record.rights_note)}</dd><dt>Review</dt><dd>Authored draft. No human review or release admission is implied.</dd></dl><details><summary>Representation, hash and source provenance</summary><pre>${esc(JSON.stringify(record, null, 2))}</pre></details></div></article><aside class="panel panel-pad inspector"><div><span class="eyebrow">ANNOTATION</span><h2>${record.kind === "image" ? "Class draft" : "Representation contract"}</h2>${record.kind === "image" ? `<form id="fixture-annotation"><label>Class label<input id="fixture-label" value="${esc(label)}" maxlength="120" required></label><span id="fixture-dirty" class="badge ${draftDirty ? "amber" : ""}">${draftDirty ? "Unsaved fixture draft" : "Saved fixture draft"}</span><div class="actions"><button class="primary">Save fixture draft</button></div></form><p class="footnote">Saves a new browser-local draft revision. It does not create review evidence or a frozen release.</p>` : `<pre>${esc(JSON.stringify(record.representation, null, 2))}</pre><p class="footnote">Read-only fixture. Use the qualified current catalog editor where available.</p>`}</div><div><span class="eyebrow">CURRENT CATALOG CAPABILITY</span><div class="capability"><strong>${capability.state === "available" ? "Available in bounded scope" : "Unavailable"}</strong><small>${esc(capability.reason)}</small></div><div class="capability"><strong>Next qualification</strong><small>${esc(capability.gate)}</small></div><button id="open-catalog">Open current catalog →</button></div></aside></div>`;
    $("fixture-data")
      .querySelectorAll("[data-record]")
      .forEach(
        (b) =>
          (b.onclick = () => {
            if (
              draftDirty &&
              !confirm("Discard unsaved fixture annotation edits?")
            )
              return;
            draftDirty = false;
            draftLabel = null;
            active = b.dataset.record;
            renderData();
            $("fixture-data")
              .querySelector(`[data-record="${active}"]`)
              .focus();
          }),
      );
    $("fixture-data")
      .querySelectorAll("[data-select]")
      .forEach(
        (b) =>
          (b.onchange = () => {
            b.checked
              ? selected.add(b.dataset.select)
              : selected.delete(b.dataset.select);
            context();
            $("fixture-data").querySelector(
              ".collection-foot",
            ).firstChild.textContent =
              selected.size + " selected · source and annotation r1";
          }),
      );
    $("fixture-label")?.addEventListener("input", (e) => {
      draftDirty = true;
      draftLabel = e.target.value;
      $("fixture-dirty").textContent = "Unsaved fixture draft";
      $("fixture-dirty").className = "badge amber";
      context();
    });
    $("fixture-annotation")?.addEventListener("submit", (e) => {
      e.preventDefault();
      const result = store.saveDraft(record.id, $("fixture-label").value);
      if (result.kind === "fixture") {
        draftDirty = false;
        draftLabel = null;
        renderData();
        $("fixture-label").focus();
      }
      announce(result.message, result.kind !== "fixture");
    });
    $("open-catalog").onclick = () => switchSource("catalog");
  }
  function switchSource(next) {
    if (next === source) return;
    if (source === "fixtures" && fixtureDirty()) {
      pendingSource = next;
      $("dataset").value = source;
      $("leave-dialog").showModal();
      $("keep-editing").focus();
      return;
    }
    invalidateCorrection();
    source = next;
    if (source.startsWith("project:")) $("dataset").disabled = false;
    $("dataset").value = next;
    renderData();
    showView();
  }
  $("dataset").onchange = (e) => switchSource(e.target.value);
  $("keep-editing").onclick = () => {
    $("leave-dialog").close();
    pendingSource = null;
    $("dataset").focus();
  };
  $("discard-editing").onclick = () => {
    draftDirty = false;
    draftLabel = null;
    pipeline.discard();
    $("leave-dialog").close();
    const next = pendingSource;
    pendingSource = null;
    switchSource(next);
    $("dataset").focus();
  };
  $("leave-dialog").addEventListener("cancel", (event) => {
    event.preventDefault();
    pendingSource = null;
    $("leave-dialog").close();
    $("dataset").focus();
  });
  function showView() {
    const next = ["data", "pipeline", "runs"].includes(location.hash.slice(1))
      ? location.hash.slice(1)
      : "data";
    // Navigation links are outside the view and must never become its focus return target.
    for (const name of ["data", "pipeline", "runs"]) {
      $("view-" + name).hidden = name !== next;
      $("nav-" + name).toggleAttribute("aria-current", name === next);
      if (name === next) $("nav-" + name).setAttribute("aria-current", "page");
    }
    currentView = next;
    $("pipeline-root").hidden = source !== "fixtures";
    $("runs-root").hidden = source !== "fixtures";
    $("real-pipeline-root").hidden = source !== "catalog";
    $("real-runs-root").hidden = source !== "catalog";
    real.show(source === "catalog" ? next : null);
    projects.show(source, next);
    if (next === "runs" && source === "fixtures") runs?.render();
    if (source.startsWith("project:"))
      announce("Project inspection · " + next + ". Execution is unsupported.");
    else if (next !== "data" && source === "catalog")
      announce("Current catalog · real " + next + ". Source edits remain mounted in Data.");
    else
      announce(
        next === "data"
          ? source === "fixtures"
            ? "Fixture workspace ready."
            : "Current catalog · existing Data workflow."
          : "Fixture " + next + " · browser-local examples only.",
      );
    context();
    $(lastFocus[next] || next + "-heading")?.focus({ preventScroll: true });
  }
  document.addEventListener("focusin", (event) => {
    if (
      currentView &&
      event.target.id &&
      $("view-" + currentView).contains(event.target)
    )
      lastFocus[currentView] = event.target.id;
  });
  window.addEventListener("hashchange", () => {
    fragmentIntent = null;
    invalidateCorrection();
    showView();
    window.scrollTo(0, 0);
  });
  document.addEventListener("click", (event) => {
    const anchor = event.target.closest?.('a[href^="#"]');
    if (!anchor || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    fragmentIntent = anchor.getAttribute("href");
    invalidateCorrection();
  }, true);
  window.addEventListener("storage", (event) => {
    if (event.key === service.STORE_KEY)
      announce(
        "Fixture storage changed in another tab. Reload before saving; current drafts are retained.",
        true,
      );
  });
  window.addEventListener("beforeunload", (event) => {
    if (fixtureDirty() || catalogDirty() || real.isDirty()) {
      event.preventDefault();
      event.returnValue = "";
    }
  });
  // Same-origin iframe bridge exposes a read-only snapshot, never SQL or cloned owners.
  window.addEventListener("message", (event) => {
    if (
      event.origin !== location.origin ||
      event.source !== $("catalog-frame").contentWindow ||
      event.data?.type !== "tuldok-data-context"
    )
      return;
    if (restoringCatalog) return;
    if (JSON.stringify(catalogContext) === JSON.stringify(event.data.context)) return;
    if (JSON.stringify(catalogContext) !== JSON.stringify(event.data.context))
      catalogRestoreNotice = null;
    catalogContext = event.data.context;
    renderCorrection();
    remember();
    $("catalog-status").textContent =
      catalogRestoreNotice ||
      (catalogContext.dirty
        ? "Unsaved Data edits retained."
        : "Current Data owner ready.");
    if (source === "catalog" && currentView === "data") context();
  });
  let catalogLoadEpoch = 0, catalogReady = false;
  $("catalog-frame").addEventListener("load", async () => {
    invalidateCorrection(false);
    catalogReady=false;
    const epoch = ++catalogLoadEpoch;
    const bridge = $("catalog-frame").contentWindow?.TuldokWorkspaceData;
    if (!bridge) {
      $("catalog-status").textContent =
        "Data bridge unavailable. Open the classic workbench to continue.";
      return;
    }
    const saved = remembered?.catalog;
    if (saved) {
      restoringCatalog = true;
      try {
        const result = await bridge.restoreContext(saved);
        if (epoch !== catalogLoadEpoch) return;
        catalogRestoreNotice = result.message;
        $("catalog-status").textContent = catalogRestoreNotice;
      } catch (error) {
        if (epoch !== catalogLoadEpoch) return;
        catalogRestoreNotice =
          "Catalog context restore failed. Your current work is retained; refresh the catalog to retry.";
        $("catalog-status").textContent = catalogRestoreNotice;
      } finally {
        if (epoch === catalogLoadEpoch) {
          restoringCatalog = false;
          catalogContext = bridge.snapshot();
          context();
        }
      }
    }
    if(epoch===catalogLoadEpoch)catalogReady=true;
  });
  async function load() {
    const epoch = ++loadEpoch;
    $("workspace-status").textContent = "Loading authored fixtures…";
    $("retry-load").hidden = true;
    $("workspace-error").hidden = true;
    try {
      const response = await fetch("/workspace-fixtures.json");
      if (!response.ok)
        throw Error("Fixture request failed (" + response.status + ").");
      const data = await response.json();
      if (epoch !== loadEpoch) return;
      if (
        data.version !== 1 ||
        data.mode !== "fixture" ||
        !Array.isArray(data.records) ||
        data.records.length !== 7 ||
        new Set(data.records.map((record) => record?.id)).size !== 7 ||
        data.records.some((r) => service.validateRecord(r))
      )
        throw Error("Fixture contract is invalid or unsupported.");
      fixtures = data;
      if (!store) {
        store = service.createStore(
          storage,
          fixtures.records.find((r) => r.id === "fixture-image"),
        );
        pipeline = PipelineEditor(
          $("pipeline-root"),
          service,
          store,
          (run) => {
            runs.render(run.id);
            location.hash = "runs";
            announce("Fixture run recorded. No worker was started.");
          },
          announce,
        );
        runs = RunsView(
          $("runs-root"),
          service,
          store,
          (prediction) => {
            active = prediction.record_id;
            correction = prediction;
            source = "fixtures";
            $("dataset").value = source;
            renderData();
            location.hash = "data";
          },
          announce,
        );
      }
      $("dataset").disabled = false;
      $("dataset").value = source;
      const status = store.read();
      if (status.kind !== "fixture") {
        $("workspace-error").textContent = status.message;
        $("workspace-error").hidden = false;
        const reset = document.createElement("button");
        reset.textContent = "Reset isolated fixture store";
        reset.onclick = () => {
          if (confirm("Remove only browser-local fixture drafts and runs?")) {
            const result = store.reset();
            if (result.kind === "fixture") load();
            else announce(result.message, true);
          }
        };
        $("workspace-error").append(reset);
      }
      pipeline.load();
      renderData();
      showView();
    } catch (error) {
      if (epoch !== loadEpoch) return;
      $("workspace-error").textContent = error.message;
      $("workspace-error").hidden = false;
      $("retry-load").hidden = false;
      if (source.startsWith("project:")) { $("dataset").disabled=false;renderData();showView(); }
      announce(
        "Workspace fixture loading failed. The classic workbench remains available.",
        true,
      );
    }
  }
  $("retry-load").onclick = load;
  projects.initialize();
  load();
})();
