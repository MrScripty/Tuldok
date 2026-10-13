"use strict";
(() => {
  window.RunsView = function (root, service, store, openRecord, announce) {
    let selected = history.state?.workspace?.runId || null,
      selectedCell = null;
    const esc = window.workspaceEscape;
    function render(id) {
      if (id) {
        selected = id;
        selectedCell = null;
      }
      const result = store.read();
      if (result.kind !== "fixture") {
        root.innerHTML = '<p class="error-panel">Fixture runs unavailable.</p>';
        return;
      }
      const runs = result.value.runs;
      const run = runs.find((r) => r.id === selected) || runs[0];
      selected = run?.id;
      history.replaceState(
        {
          ...history.state,
          workspace: { ...history.state?.workspace, runId: selected },
        },
        "",
      );
      root.innerHTML = `<p class="callout"><strong>Fixture results.</strong> Metrics and predictions below are authored interface examples. No training ran, no real checkpoint exists, and these values make no quality claim.</p>${!runs.length ? '<div class="panel empty"><h2>No fixture runs yet</h2><p>Validate a graph in Pipeline, then record a fixture scenario.</p><a class="button primary" href="#pipeline">Open Pipeline →</a></div>' : `<div class="runs-layout"><aside class="panel"><div class="panel-title"><h2>Fixture runs</h2><span class="badge">${runs.length}</span></div><div class="run-list">${runs.map((r, i) => `<button class="run-item" data-run="${esc(r.id)}" aria-current="${r.id === selected}"><span class="badge ${r.state === "completed" ? "green" : "amber"}">${esc(r.state)} · fixture</span><small>${esc(r.graph.name)}</small>Revision ${r.graph.revision} <small>${esc(new Date(r.created_at).toLocaleString())}</small></button>`).join("")}</div></aside><article class="panel panel-pad"><div class="meta-row"><span class="badge ${run.state === "completed" ? "green" : "amber"}">${esc(run.state)} · fixture</span><span class="badge">validation split</span></div><h2 style="margin-top:14px">${esc(run.graph.name)}</h2><p class="muted">Frozen graph revision ${run.graph.revision} · ${esc(run.graph.release_id)} · schema v1</p>${details(run)}<details style="margin-top:18px"><summary>Frozen graph, source reference and provenance</summary><pre>${esc(JSON.stringify({ mode: "fixture", id: run.id, graph: run.graph, prediction: run.prediction, source: "Authored Tuldok M1 interface fixture; CC0-1.0" }, null, 2))}</pre></details></article></div>`}`;
      root.querySelectorAll("[data-run]").forEach(
        (b) =>
          (b.onclick = () => {
            render(b.dataset.run);
            root.querySelector(`[data-run="${selected}"]`)?.focus();
          }),
      );
      root.querySelectorAll("[data-cell]").forEach(
        (b) =>
          (b.onclick = () => {
            selectedCell = b.dataset.cell;
            render();
            root.querySelector("#prediction-heading")?.focus();
          }),
      );
      root
        .querySelector("#open-correction")
        ?.addEventListener("click", () => openRecord(run.prediction));
      root.querySelector("#cancel-fixture")?.addEventListener("click", () => {
        const result = store.cancelRun(run.id);
        announce(result.message, result.kind !== "fixture");
        render();
      });
      root.querySelector("#download-fixture")?.addEventListener("click", () => {
        const blob = new Blob(
            [
              JSON.stringify(
                {
                  version: 1,
                  mode: "fixture",
                  quality_claim: false,
                  run_id: run.id,
                  release_id: run.graph.release_id,
                  graph: run.graph,
                  prediction: run.prediction,
                  metrics: { accuracy: 0.75, examples: 4 },
                  checkpoint: null,
                },
                null,
                2,
              ),
            ],
            { type: "application/json" },
          ),
          url = URL.createObjectURL(blob),
          a = document.createElement("a");
        a.href = url;
        a.download = run.id + ".json";
        a.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
      });
    }
    function details(run) {
      if (run.state === "running")
        return '<div class="empty"><h2>Running scenario · fixture</h2><p>Total work and remaining duration are unknown. This static scenario starts no worker and will not advance by itself.</p><button id="cancel-fixture">Cancel fixture scenario</button></div>';
      if (run.state === "failed")
        return '<div class="error-panel"><strong>Example failure: image export rejected</strong><p>Authored class-coverage error: one class is missing from the validation split. No worker started. Real errors will link to actual offending records after M2.</p></div>';
      if (run.state === "cancelled")
        return '<div class="empty"><h2>Fixture scenario cancelled</h2><p>No artifacts were published. This demonstrates a terminal state; it does not prove process cessation.</p></div>';
      if (run.state === "unknown")
        return '<div class="error-panel"><h2>Completion unknown · fixture</h2><p>Example lost acknowledgement. Reconciliation is required before another real attempt. M1 has no worker to reconcile.</p><button disabled>Retry unavailable</button></div>';
      return `<div class="metric-grid"><div class="metric"><strong>75%</strong><span>Authored accuracy · fixture</span></div><div class="metric"><strong>4</strong><span>Authored examples</span></div><div class="metric"><strong>1</strong><span>Illustrated error</span></div></div><div class="run-columns"><section><h3>Confusion matrix · fixture</h3><p class="muted">Rows: targets. Columns: predictions. Select a cell to inspect validation examples.</p><div class="matrix"><span></span><span>square</span><span>circle</span><span>square</span><button data-cell="correct-square" aria-label="Square predicted square: 2 fixture examples">2</button><button data-cell="error" class="error-cell" aria-label="Square predicted circle: 1 fixture error">1</button><span>circle</span><button data-cell="none" aria-label="Circle predicted square: 0 fixture examples">0</button><button data-cell="correct-circle" aria-label="Circle predicted circle: 1 fixture example">1</button></div>${selectedCell === "error" ? `<div class="prediction"><h3 id="prediction-heading" tabindex="-1">Authored error example</h3><p>Blue square · validation<br>Target: ${esc(run.prediction.target)} → predicted: ${esc(run.prediction.predicted)}</p><p>Frozen source r${run.prediction.source_revision}, annotation r${run.prediction.annotation_revision}. Current fixture annotation r${store.read().value.drafts["fixture-image"]?.revision || 1}.</p><button id="open-correction">Open current fixture in Data →</button><p class="muted">Editing creates a new fixture draft. This result stays unchanged.</p></div>` : selectedCell ? `<div class="prediction"><h3 id="prediction-heading" tabindex="-1">${selectedCell === "none" ? "No examples in this cell" : "Aggregate fixture cell"}</h3><p>${selectedCell === "none" ? "The authored count is zero." : "Only the single error row is materialized in M1. This aggregate cell has no per-example records to open."}</p></div>` : ""}</section><section><h3>Node attempts · authored</h3>${run.graph.nodes.map((n, i) => `<div class="attempt"><span class="node-index">${i + 1}</span><span>${esc(service.definitions[n.definition].title)}</span><small>fixture</small></div>`).join("")}<div class="actions"><button id="download-fixture">Download fixture JSON</button></div><p class="muted">Manifest, graph and prediction example. Checkpoint unavailable.</p></section></div><details style="margin-top:16px"><summary>Bounded example log · 3 lines</summary><pre>[fixture] release fixture-release-v1\n[fixture] no process started\n[fixture] authored metrics displayed</pre></details>`;
    }
    return { render };
  };
})();
