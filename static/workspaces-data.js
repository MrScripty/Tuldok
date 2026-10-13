"use strict";
// Opt-in presentation adapter. Existing Workbench functions remain the owners.
(() => {
  if (
    window.parent === window ||
    new URLSearchParams(location.search).get("workspace") !== "1"
  )
    return;
  const stylesheet = document.createElement("link");
  stylesheet.rel = "stylesheet";
  stylesheet.href = "/workspaces-data.css";
  document.head.append(stylesheet);
  document.documentElement.classList.add("workspace-embedded");
  const snapshot = () => ({
    record: current
      ? {
          id: current.id,
          name: current.name,
          revision: current.revision,
          source_revision: current.source_revision,
        }
      : null,
    selection: [...selected.values()].map(
      ({ id, revision, source_revision }) => ({
        id,
        revision,
        source_revision,
      }),
    ),
    dirty: hasUnsavedEdits(),
  });
  let restoreGeneration = 0;
  async function restoreContext(context) {
    const generation = ++restoreGeneration;
    if (
      !context ||
      !Array.isArray(context.selection) ||
      context.selection.length > 5000
    )
      return {
        kind: "invalid",
        message: "Remembered catalog context is invalid.",
      };
    if (hasUnsavedEdits())
      return {
        kind: "invalid",
        message: "Save current edits before restoring a remembered selection.",
      };
    const editorAtStart = editorEpoch,
      selectionAtStart = selectionEpoch,
      responseAtStart = responseIntentEpoch();
    const refs = [
        ...context.selection,
        ...(context.record ? [context.record] : []),
      ],
      records = new Map();
    for (const ref of refs) {
      if (
        !ref ||
        typeof ref.id !== "string" ||
        !Number.isSafeInteger(ref.revision) ||
        !Number.isSafeInteger(ref.source_revision)
      )
        return {
          kind: "invalid",
          message: "Remembered source reference is invalid.",
        };
      if (records.has(ref.id)) {
        const existing = records.get(ref.id);
        if (
          existing.revision !== ref.revision ||
          existing.source_revision !== ref.source_revision
        )
          return {
            kind: "invalid",
            message:
              "Remembered record and selection revisions disagree. Select current revisions explicitly.",
          };
        continue;
      }
      try {
        const record = await api("records/" + encodeURIComponent(ref.id));
        if (
          record.revision !== ref.revision ||
          record.source_revision !== ref.source_revision
        )
          return {
            kind: "invalid",
            message:
              "Remembered source changed. Open the record and select its current revision explicitly.",
          };
        records.set(ref.id, record);
      } catch (error) {
        return {
          kind: "unavailable",
          message:
            "Remembered source unavailable. Open a record explicitly from the current catalog.",
        };
      }
    }
    // No selection/current record changes until every exact reference is checked.
    if (
      generation !== restoreGeneration ||
      editorEpoch !== editorAtStart ||
      selectionEpoch !== selectionAtStart ||
      responseIntentEpoch() !== responseAtStart ||
      hasUnsavedEdits()
    )
      return {
        kind: "invalid",
        message:
          "Catalog context changed during restore. Your current work is retained.",
      };
    selected.clear();
    for (const ref of context.selection)
      selected.set(ref.id, records.get(ref.id));
    selection();
    if (context.record) showRecord(records.get(context.record.id));
    try {
      await refresh();
    } catch (error) {
      publish();
      return {
        kind: "unavailable",
        message:
          "Exact source restored, but collection refresh failed. Refresh the current catalog to retry.",
      };
    }
    publish();
    return {
      kind: "available",
      message:
        "Restored exact saved catalog context; unsaved edits are never replayed.",
    };
  }
  let correctionGeneration = 0;
  async function openCurrentRecord(id) {
    if (hasUnsavedEdits()) return { kind: "invalid", message: "Save or discard current Data edits before opening a result correction." };
    const generation = ++correctionGeneration, editor = editorEpoch,
      selectionIntent = selectionEpoch, responseIntent = responseIntentEpoch();
    const record = await api("records/" + encodeURIComponent(id));
    if (generation !== correctionGeneration || editor !== editorEpoch ||
        selectionIntent !== selectionEpoch || responseIntent !== responseIntentEpoch() || hasUnsavedEdits())
      return { kind: "invalid", message: "Data changed while the record loaded. Your current work is retained." };
    showRecord(record);
    publish();
    return { kind: "available", record: { id: record.id, revision: record.revision, source_revision: record.source_revision } };
  }
  window.TuldokWorkspaceData = { snapshot, restoreContext, openCurrentRecord,
    cancelRecordOpen: () => { correctionGeneration++; } };
  const publish = () =>
    window.parent.postMessage(
      { type: "tuldok-data-context", context: snapshot() },
      location.origin,
    );
  const toolbar = document.createElement("div");
  toolbar.className = "embed-toolbar";
  const drawer = document.createElement("dialog");
  drawer.id = "embed-tools";
  const heading = document.createElement("h2");
  heading.textContent = "Import, generate and release";
  const close = document.createElement("button");
  close.textContent = "Close tools";
  close.type = "button";
  const aside = document.querySelector("main>aside");
  drawer.append(heading, close, aside);
  document.body.append(drawer);
  const open = document.createElement("button");
  open.textContent = "Import / generate / release";
  open.type = "button";
  toolbar.append(open);
  document.querySelector("main").before(toolbar);
  open.onclick = () => {
    drawer.showModal();
    close.focus();
  };
  close.onclick = () => drawer.close();
  drawer.addEventListener("close", () => open.focus());
  aside.querySelectorAll("details").forEach((d) => (d.open = false));
  for (const id of ["saved-selection-panel", "curation-panel"])
    document.getElementById(id).open = false;
  const filterDetails = document.createElement("details"),
    filterSummary = document.createElement("summary");
  filterSummary.textContent = "Filter collection";
  filterDetails.append(filterSummary);
  const filters = document.getElementById("filters");
  filters.before(filterDetails);
  filterDetails.append(filters);
  document
    .querySelectorAll("main>.editor>details")
    .forEach((panel) => (panel.open = false));
  const evidence = document.getElementById("record-provenance"),
    evidenceDetails = document.createElement("details"),
    evidenceSummary = document.createElement("summary");
  evidenceSummary.textContent = "Saved source and review evidence";
  evidenceDetails.append(evidenceSummary);
  evidence.before(evidenceDetails);
  evidenceDetails.append(evidence);

  // Import and release controls keep their original DOM identity and handlers.
  const status = document.createElement("p");
  status.setAttribute("role", "status");
  heading.after(status);
  const observer = new MutationObserver(() => {
    status.textContent = document.getElementById("notice").textContent;
    publish();
  });
  // Independent editors settle asynchronously without changing the main notice.
  // Observe their outcome surfaces, then read the owners' actual dirty state;
  // a saved earlier revision can still have a newer unsaved draft.
  for (const id of ["notice", "selection", "response-editor-status",
    "preference-editor-status", "rights-note-status"]) {
    observer.observe(document.getElementById(id), { childList: true, subtree: true });
  }
  document.addEventListener("input", () => queueMicrotask(publish));
  document.addEventListener("change", () => queueMicrotask(publish));
  document.addEventListener(
    "invalid",
    (event) => {
      for (let p = event.target.parentElement; p; p = p.parentElement)
        if (p.tagName === "DETAILS") p.open = true;
    },
    true,
  );
  document.addEventListener("click", () => queueMicrotask(publish));
  window.addEventListener("pagehide", (event) => {
    if (!event.persisted) observer.disconnect();
  });
  window.addEventListener("pageshow", publish);
  publish();
})();
