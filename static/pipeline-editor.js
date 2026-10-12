"use strict";
(() => {
  // The fixture editor owns drafts/history. Validation is presentation-only.
  window.PipelineEditor = function (root, service, store, onRun, announce) {
    let graph = service.defaultGraph(),
      saved = JSON.stringify(graph),
      selected = graph.nodes[0].id,
      undo = [],
      redo = [],
      validation = null,
      busy = false,
      graphObserver = null,
      connectionsOpen = false;
    const esc = window.workspaceEscape;
    function load() {
      const result = store.read();
      if (result.kind !== "fixture") {
        announce(result.message, true);
        return;
      }
      graph = result.value.graph;
      saved = JSON.stringify(graph);
      selected = graph.nodes[0]?.id;
      undo = [];
      redo = [];
      validation = null;
      render();
    }
    function change(fn, redraw = true) {
      undo.push(structuredClone(graph));
      if (undo.length > 40) undo.shift();
      redo = [];
      fn();
      graph.revision++;
      validation = null;
      if (redraw) render();
      else {
        root.querySelector("#graph-dirty").textContent = "Unsaved changes";
        root.querySelector("#graph-dirty").className = "badge amber";
        root.querySelector("#graph-revision").textContent =
          "v1 · revision " + graph.revision;
        root.querySelector("#graph-validation").textContent =
          "Validation stale. Validate the changed graph.";
        if (root.querySelector("#preview-status"))
          root.querySelector("#preview-status").textContent =
            graph.release_id + " · sample preview stale / unvalidated";
        root.querySelector("#fixture-run").disabled = true;
        root.querySelector("#graph-undo").disabled = false;
        root.querySelector("#graph-redo").disabled = true;
      }
      announce(
        "Fixture graph changed. Validate this revision before recording a run.",
      );
    }
    function button(id, fn) {
      root.querySelector("#" + id)?.addEventListener("click", fn);
    }
    function render() {
      connectionsOpen =
        root.querySelector("#graph-connections")?.open ?? connectionsOpen;
      const dirty = JSON.stringify(graph) !== saved,
        node = graph.nodes.find((n) => n.id === selected),
        definition = node && service.definitions[node.definition];
      const options = graph.nodes
        .map(
          (n) =>
            `<option value="${esc(n.id)}">${esc(service.definitions[n.definition].title)} · ${esc(n.id)}</option>`,
        )
        .join("");
      root.innerHTML = `<p class="callout"><strong>Fixture pipeline.</strong> Graphs save only in this browser. All outputs are authored examples. Real execution is unavailable until PostgreSQL migration and M2 qualification pass.</p>
      <div class="toolbar"><label class="sr-only" for="graph-name">Recipe name</label><input id="graph-name" value="${esc(graph.name)}" maxlength="100"><span id="graph-revision" class="badge">v1 · revision ${graph.revision}</span><span id="graph-dirty" class="badge ${dirty ? "amber" : ""}">${dirty ? "Unsaved changes" : "Saved fixture"}</span><span class="spacer"></span><button id="graph-undo" ${undo.length ? "" : "disabled"}>Undo</button><button id="graph-redo" ${redo.length ? "" : "disabled"}>Redo</button><button id="graph-clone">Clone recipe</button><button id="graph-save">Save draft</button></div>
      <div class="pipeline-layout"><div class="panel"><div class="panel-title"><h2>Graph · keyboard-operable node list</h2><span class="badge">${graph.nodes.length} nodes</span></div><div class="graph-board" aria-label="Graph nodes">${graph.nodes.map((n, i) => `<button class="graph-node" data-node="${esc(n.id)}" aria-pressed="${n.id === selected}"><span class="node-index">${String(i + 1).padStart(2, "0")} / ${esc(n.id)}</span>${esc(service.definitions[n.definition].title)}<small>${service.definitions[n.definition].unavailable ? "Unavailable" : "Fixture · definition v1"}</small></button>`).join("") || "<p>No nodes. Add a definition below.</p>"}</div>
      <div class="connections"><div class="toolbar"><label class="inline-label">Add node<select id="node-definition">${Object.entries(
        service.definitions,
      )
        .map(
          ([key, d]) =>
            `<option value="${key}">${d.title}${d.unavailable ? " · unavailable" : ""}</option>`,
        )
        .join(
          "",
        )}</select></label><button id="node-add">Add</button></div><details id="graph-connections" ${connectionsOpen ? "open" : ""}><summary>Typed connections · ${graph.edges.length} edges</summary><p class="muted">Remove an edge, then connect its replacement. All graph actions work without dragging.</p><div>${graph.edges.map((e, i) => `<div class="connection-row"><span>${esc(service.definitions[graph.nodes.find((n) => n.id === e.from)?.definition]?.title || e.from)} → ${esc(service.definitions[graph.nodes.find((n) => n.id === e.to)?.definition]?.title || e.to)}</span><button data-edge="${i}" aria-label="Remove connection ${i + 1}">Remove</button></div>`).join("") || "<p>No connections.</p>"}</div><form class="connection-form" id="connect-form"><label>Output node<select id="edge-from">${options}</select></label><label>Input node<select id="edge-to">${options}</select></label><button ${graph.nodes.length ? "" : "disabled"}>Connect</button></form></details></div>
      <div class="validation"><div class="actions"><button id="graph-validate" class="primary">Validate fixture graph</button><button disabled title="MB and M2 qualification required">Run real pipeline · unavailable</button></div><p id="graph-validation" role="status">${validation ? esc(validation.message) : "Validation stale or not run. Changes invalidate the previous result."}</p><label class="inline-label">Fixture outcome<select id="run-scenario"><option value="completed">Completed · authored metrics</option><option value="running">Running · unknown progress</option><option value="failed">Failed · example error</option><option value="cancelled">Cancelled</option><option value="unknown">Unknown · reconciliation needed</option></select></label><button id="fixture-run" ${validation?.kind === "fixture" ? "" : "disabled"}>Record fixture run →</button></div></div>
      <aside class="panel panel-pad node-settings"><span class="eyebrow">NODE INSPECTOR</span><h2>${definition ? esc(definition.title) : "Select a node"}</h2>${node ? `<p class="muted">${esc(definition.help)}</p><dl class="metadata"><dt>Definition</dt><dd>${esc(node.definition)} / v${node.version}</dd><dt>Input port</dt><dd>${esc(definition.input || "None — source")}</dd><dt>Output port</dt><dd>${esc(definition.output || "None — terminal")}</dd></dl>${node.definition === "train" ? `<form id="node-settings"><label>Epochs · fixture only<input id="train-epochs" type="number" min="1" max="10" value="${esc(node.parameters.epochs)}" required></label><label>Seed<input id="train-seed" type="number" min="0" max="4294967295" value="${esc(node.parameters.seed)}" required></label><p class="muted">Changes update the graph draft. Save before reloading.</p></form>` : ""}<button id="node-remove" class="danger">Remove selected node</button><hr><h3>Output preview</h3><span class="badge amber">Fixture · sample 1 of 1</span><p id="preview-status" class="muted">${esc(graph.release_id)} · no truncation · ${validation?.kind === "fixture" ? "current validation" : "stale / unvalidated"}</p><pre class="preview-json">${esc(JSON.stringify({ mode: "fixture", node: node.definition, definition_version: 1, release: graph.release_id, sample: node.definition === "train" ? { checkpoint: null, reason: "No training executed" } : { type: definition.output, value: "Authored preview only" } }, null, 2))}</pre>` : ""}</aside></div>`;
      drawConnections();
      root.querySelectorAll("[data-node]").forEach(
        (b) =>
          (b.onclick = () => {
            selected = b.dataset.node;
            render();
            root.querySelector(`[data-node="${selected}"]`)?.focus();
          }),
      );
      root.querySelector("#graph-name").oninput = (e) =>
        change(() => (graph.name = e.target.value), false);
      button("node-add", () => {
        if (graph.nodes.length >= 20)
          return announce("Fixture graph limit: 20 nodes.", true);
        const type = root.querySelector("#node-definition").value;
        change(() => {
          selected = "node-" + crypto.randomUUID();
          graph.nodes.push({
            id: selected,
            definition: type,
            version: 1,
            parameters: type === "train" ? { epochs: 2, seed: 42 } : {},
          });
        });
        root.querySelector(`[data-node="${selected}"]`)?.focus();
      });
      button("node-remove", () => {
        change(() => {
          graph.nodes = graph.nodes.filter((n) => n.id !== selected);
          graph.edges = graph.edges.filter(
            (e) => e.from !== selected && e.to !== selected,
          );
          selected = graph.nodes[0]?.id;
        });
        root.querySelector("#node-add").focus();
      });
      root.querySelectorAll("[data-edge]").forEach(
        (b) =>
          (b.onclick = () => {
            change(() => graph.edges.splice(Number(b.dataset.edge), 1));
            root.querySelector("#edge-from").focus();
          }),
      );
      root.querySelector("#connect-form").onsubmit = (e) => {
        e.preventDefault();
        const from = root.querySelector("#edge-from").value,
          to = root.querySelector("#edge-to").value;
        const a = graph.nodes.find((n) => n.id === from),
          b = graph.nodes.find((n) => n.id === to);
        if (
          from === to ||
          !service.definitions[a.definition].output ||
          service.definitions[a.definition].output !==
            service.definitions[b.definition].input
        )
          return announce(
            "Connection refused: incompatible ports or self-cycle.",
            true,
          );
        if (graph.edges.some((x) => x.to === to))
          return announce(
            "Input already connected. Remove its edge before reconnecting.",
            true,
          );
        if (graph.edges.length >= 40)
          return announce("Fixture edge limit reached.", true);
        change(() => graph.edges.push({ from, to }));
        root.querySelector("#edge-from").focus();
      };
      root
        .querySelector("#node-settings")
        ?.addEventListener("submit", (e) => e.preventDefault());
      for (const id of ["train-epochs", "train-seed"])
        root.querySelector("#" + id)?.addEventListener("input", () => {
          const epochs = Number(root.querySelector("#train-epochs").value),
            seed = Number(root.querySelector("#train-seed").value);
          change(() => (node.parameters = { epochs, seed }), false);
        });
      button("graph-undo", () => {
        redo.push(structuredClone(graph));
        const revision = graph.revision + 1;
        graph = undo.pop();
        graph.revision = revision;
        validation = null;
        render();
        root.querySelector("#graph-redo").focus();
      });
      button("graph-redo", () => {
        undo.push(structuredClone(graph));
        const revision = graph.revision + 1;
        graph = redo.pop();
        graph.revision = revision;
        validation = null;
        render();
        root.querySelector("#graph-undo").focus();
      });
      button("graph-clone", () =>
        change(() => {
          graph.id = "fixture-graph-" + crypto.randomUUID();
          graph.name = (graph.name + " · copy").slice(0, 100);
        }),
      );
      button("graph-save", () => {
        const result = store.saveGraph(graph);
        if (result.kind === "fixture") {
          saved = JSON.stringify(graph);
          render();
          root.querySelector("#graph-save").focus();
        }
        announce(result.message, result.kind !== "fixture");
      });
      button("graph-validate", () => {
        validation = service.validateGraph(graph);
        render();
        root.querySelector("#graph-validate").focus();
        announce(validation.message, validation.kind !== "fixture");
      });
      button("fixture-run", () => {
        if (busy) return;
        busy = true;
        const result = store.createRun(
          graph,
          root.querySelector("#run-scenario").value,
          validation?.kind === "fixture" ? graph.revision : null,
        );
        if (result.kind === "fixture") onRun(result.value);
        else announce(result.message, true);
        queueMicrotask(() => (busy = false));
      });
    }
    function drawConnections() {
      graphObserver?.disconnect();
      const board = root.querySelector(".graph-board"),
        ns = "http://www.w3.org/2000/svg";
      const svg = document.createElementNS(ns, "svg");
      svg.classList.add("graph-edges");
      svg.setAttribute("aria-hidden", "true");
      board.prepend(svg);
      function paint() {
        const rect = board.getBoundingClientRect();
        if (!rect.width) return;
        svg.setAttribute("viewBox", `0 0 ${rect.width} ${rect.height}`);
        svg.innerHTML =
          '<defs><marker id="edge-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto"><path d="M0 0L10 5L0 10z" fill="#7389ad"/></marker></defs>';
        for (const edge of graph.edges) {
          const from = board.querySelector(`[data-node="${edge.from}"]`),
            to = board.querySelector(`[data-node="${edge.to}"]`);
          if (!from || !to) continue;
          const a = from.getBoundingClientRect(),
            b = to.getBoundingClientRect();
          const sameRow =
            Math.abs(a.top + a.height / 2 - (b.top + b.height / 2)) < 5;
          const x1 = (sameRow ? a.right : a.left + a.width / 2) - rect.left,
            y1 = (sameRow ? a.top + a.height / 2 : a.bottom) - rect.top;
          const x2 = (sameRow ? b.left : b.left + b.width / 2) - rect.left,
            y2 = (sameRow ? b.top + b.height / 2 : b.top) - rect.top;
          const line = document.createElementNS(ns, "path");
          line.setAttribute(
            "d",
            sameRow
              ? `M${x1} ${y1}L${x2 - 2} ${y2}`
              : `M${x1} ${y1}C${x1} ${y1 + 12} ${x2} ${y2 - 12} ${x2} ${y2 - 2}`,
          );
          line.setAttribute("fill", "none");
          line.setAttribute("stroke", "#7389ad");
          line.setAttribute("stroke-width", "1.5");
          line.setAttribute("marker-end", "url(#edge-arrow)");
          svg.append(line);
        }
      }
      graphObserver = new ResizeObserver(paint);
      graphObserver.observe(board);
      paint();
    }
    window.addEventListener("pagehide", (event) => {
      if (!event.persisted) graphObserver?.disconnect();
    });
    return {
      load,
      render,
      isDirty: () => JSON.stringify(graph) !== saved,
      discard: load,
    };
  };
})();
