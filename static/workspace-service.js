"use strict";
/* M1 presentation service. This is a disposable fixture store, not a run engine.
 * No catalog writes, backend SQL, network inference or process execution here.
 * M2 replaces this boundary only after MB qualification and engine admission. */
(() => {
  /** @typedef {'fixture'|'available'|'unavailable'} CapabilityState */
  /** @typedef {{state: CapabilityState, reason: string, gate: string}} Capability */
  /** @typedef {{dataset_id:string, id:string, source_revision:number, annotation_revision:number, content_hash:string}} AssetRef */
  /** @typedef {{id:string, definition:string, version:1, parameters:Object}} FixtureNode */
  /** @typedef {{version:1, mode:'fixture', id:string, revision:number, name:string, release_id:string, nodes:FixtureNode[], edges:{from:string,to:string}[]}} GraphDocument */
  /** @typedef {{mode:'fixture', id:string, graph:GraphDocument, state:'completed'|'failed'|'cancelled'|'unknown'|'running', created_at:string, prediction:Object}} FixtureRun */
  const STORE_KEY = "tuldok.workspace.fixture.v1";
  // Keep the namespace so older checkpoint data is detected and left intact.
  // Envelope v2 pins predictions to the immutable authored source reference.
  const STORE_VERSION = 2;
  const definitions = Object.freeze({
    release: {
      title: "Frozen release",
      input: null,
      output: "image_release_v1",
      help: "Exact authored fixture release; no live selection is captured.",
    },
    validate: {
      title: "Validate image export",
      input: "image_release_v1",
      output: "image_export_v1",
      help: "Fixture preview of class coverage and protected family checks.",
    },
    train: {
      title: "Train TinyCNN",
      input: "image_export_v1",
      output: "classifier_v1",
      help: "Fixture only. No model, training process or checkpoint is created.",
    },
    evaluate: {
      title: "Evaluate",
      input: "classifier_v1",
      output: "evaluation_v1",
      help: "Authored validation metrics, not measured model performance.",
    },
    publish: {
      title: "Publish artifacts",
      input: "evaluation_v1",
      output: null,
      help: "Exports labelled fixture JSON only; never publishes a real release.",
    },
    audio: {
      title: "Transcribe audio",
      input: "audio_pcm_v1",
      output: "transcript_v1",
      help: "Unavailable: production ASR has not been qualified.",
      unavailable: true,
    },
  });
  const capabilities = Object.freeze({
    image: {
      state: "available",
      reason:
        "Class, caption, detection and corner editors in the current catalog. Reviewed image releases support the bounded TinyCNN CPU recipe.",
      gate: "Other image tasks need their own qualified training recipes",
    },
    text: {
      state: "available",
      reason:
        "Text class, entities, corpus, responses and preferences in Data. Reviewed text classification releases support a train-only TF-IDF / Naive Bayes CPU recipe.",
      gate: "Other text tasks retain their existing reviewed exports; no general language-model trainer",
    },
    audio: {
      state: "available",
      reason:
        "Bounded PCM16 WAV import, playback, timed human review and frozen export in the current catalog. One reviewed labelled interval per record supports a real local CPU feature/logistic classifier with frozen source-frame results. ASR is unavailable.",
      gate: "PCM interval classification only; no ASR, resampling or downmix",
    },
    mesh: {
      state: "available",
      reason:
        "Current catalog accepts bounded ASCII PLY triangle meshes. Inspection does not qualify physics or training.",
      gate: "M5a expansion",
    },
    point_cloud: {
      state: "unavailable",
      reason:
        "Indexed point fixture only. The unmerged acquisition branch is not enabled.",
      gate: "M5a",
    },
    volume: {
      state: "unavailable",
      reason:
        "Grid metadata fixture only. Import and volume reader are not implemented.",
      gate: "M5b",
    },
    sequence: {
      state: "available",
      reason:
        "Current catalog inspects bounded whole Rheon trajectories (16×8×4, nine frames), not arbitrary animation.",
      gate: "M5c expansion",
    },
  });
  const copy = (value) => structuredClone(value);
  const outcome = (kind, message, value) => ({
    kind,
    message,
    ...(value === undefined ? {} : { value }),
  });
  const finite = (value) => typeof value === "number" && Number.isFinite(value);
  const positive = (value) => Number.isSafeInteger(value) && value > 0;
  const schemas = {
    image: "image_classification_v1",
    text: "text_entities_v1",
    audio: "audio_pcm_v1",
    mesh: "mesh_ascii_ply_v1",
    point_cloud: "point_cloud_fixture_v1",
    volume: "volume_fixture_v1",
    sequence: "sequence_fixture_v1",
  };
  const vector = (value) =>
    Array.isArray(value) && value.length === 3 && value.every(finite);
  function validateRecord(record) {
    if (
      !record ||
      record.mode !== "fixture" ||
      record.dataset_id !== "fixture-dataset-v1" ||
      !Object.hasOwn(capabilities, record.kind) ||
      record.id !== "fixture-" + record.kind ||
      !/^[a-f0-9]{64}$/.test(record.content_hash || "") ||
      !positive(record.source_revision) ||
      !positive(record.annotation_revision)
    )
      return "asset_reference";
    if (record.schema !== schemas[record.kind]) return "schema_version";
    const r = record.representation;
    if (!r || typeof r !== "object") return "representation";
    switch (record.kind) {
      case "image":
        if (!positive(r.width) || !positive(r.height))
          return "image_dimensions";
        if (
          typeof r.class !== "string" ||
          !r.class.trim() ||
          r.class.length > 120
        )
          return "image_class";
        break;
      case "text":
        if (
          typeof r.text !== "string" ||
          !Array.isArray(r.spans) ||
          r.spans.some(
            (s) =>
              !s ||
              !Number.isInteger(s.start) ||
              !Number.isInteger(s.end) ||
              s.start < 0 ||
              s.end <= s.start ||
              s.end > Array.from(r.text).length,
          )
        )
          return "text_span";
        break;
      case "audio":
        if (
          !positive(r.sample_rate) ||
          !positive(r.channels) ||
          !positive(r.frame_count)
        )
          return "audio_format";
        if (
          !Array.isArray(r.interval) ||
          r.interval.length !== 2 ||
          !r.interval.every(Number.isInteger) ||
          r.interval[0] < 0 ||
          r.interval[1] <= r.interval[0] ||
          r.interval[1] > r.frame_count
        )
          return "audio_interval";
        if (
          !Number.isInteger(r.channel) ||
          r.channel < 0 ||
          r.channel >= r.channels
        )
          return "audio_channel";
        break;
      case "mesh":
        if (
          !Array.isArray(r.vertices) ||
          !r.vertices.length ||
          !r.vertices.every(vector)
        )
          return "mesh_vertices";
        if (
          !Array.isArray(r.faces) ||
          !r.faces.length ||
          r.faces.some(
            (f) =>
              !Array.isArray(f) ||
              f.length !== 3 ||
              f.some(
                (i) => !Number.isInteger(i) || i < 0 || i >= r.vertices.length,
              ),
          )
        )
          return "mesh_index";
        break;
      case "point_cloud":
        if (
          !positive(r.point_count) ||
          !Array.isArray(r.points) ||
          r.points.length !== r.point_count ||
          !r.points.every(vector)
        )
          return "point_count";
        break;
      case "volume":
        if (
          !Array.isArray(r.shape) ||
          r.shape.length !== 3 ||
          !r.shape.every(positive) ||
          !Array.isArray(r.values) ||
          r.shape.reduce((a, b) => a * b, 1) !== r.values.length ||
          !r.values.every(finite)
        )
          return "volume_shape";
        if (
          !Array.isArray(r.affine) ||
          r.affine.length !== 4 ||
          r.affine.some(
            (row) =>
              !Array.isArray(row) || row.length !== 4 || !row.every(finite),
          ) ||
          JSON.stringify(r.affine[3]) !== "[0,0,0,1]" ||
          !vector(r.spacing) ||
          r.spacing.some((x) => x <= 0)
        )
          return "volume_affine";
        break;
      case "sequence":
        if (
          !Array.isArray(r.times) ||
          !r.times.length ||
          r.times.some(
            (t, i) => !finite(t) || (i > 0 && t <= r.times[i - 1]),
          ) ||
          !Array.isArray(r.positions) ||
          r.positions.length !== r.times.length
        )
          return "sequence_times";
        if (
          !Array.isArray(r.entity_ids) ||
          !r.entity_ids.length ||
          !r.entity_ids.every(
            (id) => typeof id === "string" && id.length > 0,
          ) ||
          new Set(r.entity_ids).size !== r.entity_ids.length ||
          r.positions.some(
            (frame) =>
              !Array.isArray(frame) ||
              frame.length !== r.entity_ids.length ||
              !frame.every(vector),
          )
        )
          return "sequence_entities";
        break;
    }
    return null;
  }
  function graphShape(g) {
    return (
      g &&
      g.version === 1 &&
      g.mode === "fixture" &&
      /^fixture-graph-[a-z0-9-]{1,80}$/.test(g.id || "") &&
      typeof g.name === "string" &&
      g.name.length <= 100 &&
      positive(g.revision) &&
      g.release_id === "fixture-release-v1" &&
      Array.isArray(g.nodes) &&
      g.nodes.length <= 20 &&
      g.nodes.every(
        (n) =>
          n &&
          /^node-[a-z0-9-]{1,80}$/.test(n.id || "") &&
          Object.hasOwn(definitions, n.definition) &&
          n.version === 1 &&
          n.parameters &&
          typeof n.parameters === "object" &&
          !Array.isArray(n.parameters) &&
          Object.keys(n.parameters).every(
            (key) =>
              n.definition === "train" && ["epochs", "seed"].includes(key),
          ) &&
          (n.definition !== "train" ||
            Object.values(n.parameters).every(finite)),
      ) &&
      new Set(g.nodes.map((n) => n.id)).size === g.nodes.length &&
      Array.isArray(g.edges) &&
      g.edges.length <= 40 &&
      g.edges.every(
        (e) => e && typeof e.from === "string" && typeof e.to === "string",
      )
    );
  }
  function defaultGraph() {
    return {
      version: 1,
      mode: "fixture",
      id: "fixture-graph-1",
      revision: 1,
      name: "Image classification · starter",
      release_id: "fixture-release-v1",
      nodes: ["release", "validate", "train", "evaluate", "publish"].map(
        (definition, i) => ({
          id: "node-" + (i + 1),
          definition,
          version: 1,
          parameters: definition === "train" ? { epochs: 2, seed: 42 } : {},
        }),
      ),
      edges: [1, 2, 3, 4].map((i) => ({
        from: "node-" + i,
        to: "node-" + (i + 1),
      })),
    };
  }
  function validateGraph(graph) {
    if (!graphShape(graph))
      return outcome("invalid", "Unsupported or malformed fixture graph.");
    const errors = [],
      nodes = new Map(graph.nodes.map((n) => [n.id, n]));
    if (!graph.nodes.length) errors.push("Add nodes to the empty graph.");
    for (const node of graph.nodes) {
      const d = definitions[node.definition];
      if (d.unavailable) errors.push(d.help);
      if (
        node.definition === "train" &&
        (!positive(node.parameters.epochs) ||
          node.parameters.epochs > 10 ||
          !Number.isInteger(node.parameters.seed) ||
          node.parameters.seed < 0 ||
          node.parameters.seed > 4294967295)
      )
        errors.push(
          "TinyCNN fixture: epochs must be 1–10 and seed 0–4294967295.",
        );
      const incoming = graph.edges.filter((e) => e.to === node.id);
      if (d.input && incoming.length !== 1)
        errors.push(d.title + ": connect exactly one " + d.input + " input.");
      if (!d.input && incoming.length)
        errors.push(d.title + ": source node has no input.");
    }
    const pairs = new Set();
    for (const edge of graph.edges) {
      const a = nodes.get(edge.from),
        b = nodes.get(edge.to),
        key = edge.from + "/" + edge.to;
      if (!a || !b) errors.push("Connection references a missing node.");
      else if (
        !definitions[a.definition].output ||
        definitions[a.definition].output !== definitions[b.definition].input
      )
        errors.push(
          "Incompatible ports: " +
            definitions[a.definition].title +
            " → " +
            definitions[b.definition].title +
            ".",
        );
      if (pairs.has(key)) errors.push("Duplicate connection.");
      pairs.add(key);
    }
    const visiting = new Set(),
      visited = new Set();
    function visit(id) {
      if (visiting.has(id)) return true;
      if (visited.has(id)) return false;
      visiting.add(id);
      for (const e of graph.edges.filter((e) => e.from === id))
        if (visit(e.to)) return true;
      visiting.delete(id);
      visited.add(id);
      return false;
    }
    if (graph.nodes.some((n) => visit(n.id)))
      errors.push(
        "Cycles are not allowed; corrections return to Data as a new revision.",
      );
    if (!graph.nodes.some((n) => n.definition === "release"))
      errors.push("A frozen release source is required.");
    return errors.length
      ? outcome("invalid", errors.join("\n"), errors)
      : outcome(
          "fixture",
          "Fixture graph is valid. Real execution remains unavailable.",
        );
  }
  function createStore(storage, releasedRecord) {
    if (
      validateRecord(releasedRecord) !== null ||
      releasedRecord.kind !== "image"
    )
      throw Error("A validated image fixture release is required.");
    const frozenPrediction = {
      dataset_id: releasedRecord.dataset_id,
      record_id: releasedRecord.id,
      content_hash: releasedRecord.content_hash,
      source_revision: releasedRecord.source_revision,
      annotation_revision: releasedRecord.annotation_revision,
      target: releasedRecord.representation.class,
      predicted: "circle",
      split: "validation",
    };
    const predictionValid = (p) =>
      p &&
      Object.keys(frozenPrediction).every(
        (key) => p[key] === frozenPrediction[key],
      );
    let savedRaw = null;
    let state = {
        version: STORE_VERSION,
        mode: "fixture",
        graph: defaultGraph(),
        runs: [],
        drafts: {},
      },
      blocked = null;
    try {
      const raw = storage.getItem(STORE_KEY);
      savedRaw = raw;
      if (raw) {
        const parsed = JSON.parse(raw);
        if (parsed.version !== STORE_VERSION)
          blocked = outcome(
            "unsupported",
            "Saved fixture store version is unsupported. Nothing was overwritten.",
          );
        else if (
          parsed.mode !== "fixture" ||
          !graphShape(parsed.graph) ||
          !Array.isArray(parsed.runs) ||
          parsed.runs.length > 30 ||
          parsed.runs.some(
            (r) =>
              !r ||
              r.mode !== "fixture" ||
              !/^fixture-run-[a-f0-9-]{36}$/.test(r.id || "") ||
              typeof r.created_at !== "string" ||
              r.created_at.length > 40 ||
              !Number.isFinite(Date.parse(r.created_at)) ||
              ![
                "completed",
                "failed",
                "cancelled",
                "unknown",
                "running",
              ].includes(r.state) ||
              validateGraph(r.graph).kind !== "fixture" ||
              !predictionValid(r.prediction),
          ) ||
          new Set(parsed.runs.map((r) => r.id)).size !== parsed.runs.length ||
          !parsed.drafts ||
          typeof parsed.drafts !== "object" ||
          Array.isArray(parsed.drafts) ||
          Object.keys(parsed.drafts).some((id) => id !== "fixture-image") ||
          Object.values(parsed.drafts).some(
            (d) =>
              !d ||
              typeof d.label !== "string" ||
              !d.label.trim() ||
              d.label.length > 120 ||
              d.review !== "draft" ||
              !positive(d.revision),
          )
        )
          blocked = outcome(
            "invalid",
            "Saved fixture store is malformed. Nothing was overwritten.",
          );
        else state = parsed;
      }
    } catch (error) {
      blocked = outcome(
        "unavailable",
        "Cannot read fixture storage: " + error.message,
      );
    }
    function write(next) {
      if (blocked) return blocked;
      try {
        if (storage.getItem(STORE_KEY) !== savedRaw)
          return outcome(
            "invalid",
            "Fixture storage changed in another tab. Reload before saving; your draft is retained.",
          );
        const raw = JSON.stringify(next);
        storage.setItem(STORE_KEY, raw);
        savedRaw = raw;
        state = next;
        return outcome("fixture", "Saved in this browser only.");
      } catch (error) {
        return outcome(
          "unavailable",
          "Cannot save fixture storage: " + error.message,
        );
      }
    }
    return {
      read: () =>
        blocked ||
        outcome("fixture", "Browser-local fixture store.", copy(state)),
      saveGraph(graph) {
        if (!graphShape(graph))
          return outcome("invalid", "Malformed fixture graph; nothing saved.");
        return write({ ...state, graph: copy(graph) });
      },
      saveDraft(id, label) {
        if (
          id !== "fixture-image" ||
          typeof label !== "string" ||
          !label.trim() ||
          label.length > 120
        )
          return outcome(
            "invalid",
            "A fixture label of 1–120 characters is required.",
          );
        return write({
          ...state,
          drafts: {
            ...state.drafts,
            [id]: {
              label,
              revision: (state.drafts[id]?.revision || 1) + 1,
              review: "draft",
            },
          },
        });
      },
      createRun(graph, scenario, validationRevision) {
        if (blocked) return blocked;
        if (validationRevision !== graph.revision)
          return outcome(
            "invalid",
            "Validation is stale. Validate this graph revision again.",
          );
        const check = validateGraph(graph);
        if (check.kind !== "fixture") return check;
        if (
          !["release", "validate", "train", "evaluate", "publish"].every(
            (type) =>
              graph.nodes.filter((n) => n.definition === type).length === 1,
          )
        )
          return outcome(
            "invalid",
            "Authored run scenarios require each of the five starter definitions exactly once. Partial graph previews remain editable.",
          );
        if (
          !["completed", "failed", "cancelled", "unknown", "running"].includes(
            scenario,
          )
        )
          return outcome("invalid", "Unknown fixture scenario.");
        if (state.runs.length >= 30)
          return outcome(
            "invalid",
            "Fixture run limit (30) reached. Reset demo storage to start again.",
          );
        const run = {
          mode: "fixture",
          id: "fixture-run-" + crypto.randomUUID(),
          graph: copy(graph),
          state: scenario,
          created_at: new Date().toISOString(),
          prediction: copy(frozenPrediction),
        };
        const result = write({ ...state, runs: [run, ...state.runs] });
        return result.kind === "fixture"
          ? outcome(
              "fixture",
              "Authored fixture scenario recorded. No worker was started.",
              copy(run),
            )
          : result;
      },
      cancelRun(id) {
        const run = state.runs.find((r) => r.id === id);
        if (!run || run.state !== "running")
          return outcome(
            "invalid",
            "Only the running fixture can be cancelled.",
          );
        return write({
          ...state,
          runs: state.runs.map((r) =>
            r.id === id ? { ...r, state: "cancelled" } : r,
          ),
        });
      },
      reset() {
        try {
          storage.removeItem(STORE_KEY);
          savedRaw = null;
          state = {
            version: STORE_VERSION,
            mode: "fixture",
            graph: defaultGraph(),
            runs: [],
            drafts: {},
          };
          blocked = null;
          return outcome(
            "fixture",
            "Fixture store reset. Real catalog unchanged.",
          );
        } catch (error) {
          return outcome(
            "unavailable",
            "Cannot reset fixture storage: " + error.message,
          );
        }
      },
    };
  }
  const service = {
    STORE_KEY,
    definitions,
    capabilities,
    validateRecord,
    validateGraph,
    graphShape,
    defaultGraph,
    createStore,
  };
  if (typeof module !== "undefined") module.exports = service;
  else window.WorkspaceService = service;
})();

// Real model/trial presentation. No fixture state or local inference is consumed.
(() => {
  if(typeof window==='undefined')return;
  const esc = value => window.workspaceEscape(value), enc = encodeURIComponent;
  const metric = value => Number.isFinite(value) ? value.toFixed(4) : typeof value==='string'?esc(value):'Unavailable';
  const recipe = 'image_classification_model_v2';
  const evidenceRecipes=new Set([recipe,'text_classification_model_v2','audio_classification_model_v2']);
  // Generated from the operation registry; coordinated updates fail closed on drift.
  const contracts = /* MODEL_CONTRACTS_START */ {
  "models.create": "693d1514f44e92bb6c6635427db822acfc079a6e438d5d721630087157d1b8d5",
  "models.publish": "bb84c1fd72b3617135a8246353db797bba270430121fbae6f9d46cdbfdd26235",
  "models.list": "7a58a4f7e429c06f0c0488b8ca8a07b2901a864c7c24e1187bbd679ad0ac089a",
  "models.get": "79b0ac2317f62ea368e8540f63c093eea2d99dd7833109037e2e3e8fa577962a",
  "models.save": "093806e289da9fe7df57b021cd6eb4efb2e574a687bd7337656ddd6276367c25",
  "studies.create": "8c4b35bbd1c2b7c6825787b40e40b2b3d22f58118ccaf1ef5f0d9bc12edb38f1",
  "studies.get": "12080dea124eb9e763ec495e070211b60a219c47cab9488218383a7d3919533d",
  "studies.list": "77c21d405c0e556341ea4212fbab927a6298be114c202a43e1cdcc409a32c48a",
  "studies.prepare_trial": "516f89e4a03cafee9d50ac3910d1906fb34d51d3b21e8271a4be45075ea3778a",
  "studies.continue": "44237f86e49135203613b40a7bf6fe0960581ed7c3f128150b9576a07b491008",
  "studies.admit": "9c80abdfc50d56de88ada0141ba6c3b503cc07a395b0ceb930fa29169bd182ed",
  "studies.reconcile": "a209efd79a85bdb9ff5f42c469413cff9ebcc56c55ab16aa76227427670565af",
  "studies.save": "c5a0eee9a12d91f88b3e7dda4ee3c013c263f20897006ca50aed5f703d6c3d74",
  "runs.model_evidence/2": "48c1b942f8e7a102a83bf63806fb425576690f4bfbca841203d54edbca4a59f9",
  "runs.model_evidence": "50c054fc7ce64c08f8a229faed6dfdcd9069c1b84ee8985bfce8736bc2c9aadb",
  "runs.compare_model_evidence": "0c89402e1749b5bca7c09c66bc5bfc13cd33b3be6e15c69826074583fc0e13c5",
  "graphs.create": "a4c0ec40212ce85ad67c5f279fa90fe4564048d4ab41b6769670cbcf21bbb615",
  "graphs.save": "da60657d6c3298db8b9bbdfc6d30577125c8a6310573cee5c2feefa3a67e3564",
  "studies.select_candidate": "940d670ae6e4630572d1c5cdeda1cc658a7b73587bedd277af137b77dac3e582",
  "studies.candidate": "d02dda330ac41ef05a1ff4e4d4f9ed04d5a60b24a444a28f1af9904791977799",
  "studies.candidates": "84eacef1aacffdfcba18ce037f013034ac959f23a617c8b443247c72f89fcfd2",
  "studies.approve": "5ed2d9db58231f14c164a76f1c64157260902d2cd86f5e86433f29fc00f4f408",
  "studies.prepare_package": "6eea96340355a085a4709c180f3ae61bed063a344c3e4ad8b876c53f36ff6f14",
  "studies.prepare_verifier": "cde685bd4e93bb749055bb291501c67520f97dc514b2a4e4c3ba2cd1a10a6528",
  "studies.package_state": "4ad0fd6c580c794ed01a8f94fc9f0ee1e07b09578be940bc02be3581f44449bd"
} /* MODEL_CONTRACTS_END */;
  window.WorkspaceModelContracts = contracts;
  // Shared read-only projection. Only the owner response establishes package state.
  window.WorkspacePackageStateHTML = function (state) {
    if(!state)return '<p>Package state has not been loaded.</p>';
    const packages=state.packages||[],verified=state.state==='fresh_verified';
    return `<div class="package-state-summary"><p><strong>Package: ${packages.length?'complete':'not exported'}.</strong> Fresh inference: ${verified?'verified in a separate consumer Run':'not verified'}.</p>${packages.map(item=>`<p><a href="/api/workspace/runs/${enc(item.run_id)}/artifacts/package.zip" download>Download verified package</a> · ${esc(item.bytes.toLocaleString())} bytes · <span class="field-hash">SHA256 ${esc(item.sha256)}</span><br>Completed package Run <span class="field-hash">${esc(item.run_id)}</span></p>`).join('')}${verified?'<p>Fresh inference reproduced the retained fixed probes. The candidate remains diagnostic.</p>':''}${(state.verifications||[]).map(item=>`<p>Separate fresh verifier Run <span class="field-hash">${esc(item.run_id)}</span> · package <span class="field-hash">${esc(item.receipt.package_sha256)}</span></p>`).join('')}${state.verifications?.length?`<details><summary>Fresh consumer verification receipts</summary><pre>${esc(JSON.stringify(state.verifications,null,2))}</pre></details>`:''}</div>`;
  };
  window.WorkspaceModel = function ({api:transport, announce, openRun, openRecord, getIntent, getView, onAccessFailure=()=>{}}) {
    let definition = null, releases = [], studies = [], root = null, busy = false,
      message = '', failed = false, evidence = null, evidenceError = '', comparison = null,
      checkpoint = null, probe = null, compareId = '', generation = 0, queryIntent = 0, detailPredictions = null, studyDetail = null, candidate = null, candidateBusy = false, candidateError = '', foreignPending = false, compareTarget = null, compareTargetRun = null, compareCheckpoint = '', compareMetric = '', compareMode = 'paired', compareBusy = false, compareIntent = 0, compareTargetIntent = 0, checkpointBusy = false, checkpointIntent = 0, packageState = null, packageError = '', exportSetup = null, exportJob = null, exportBusy = false, exportDraft = {mode:'package',root:'',directory:'',runtime:'',packageRun:''};
    let pendingComparison=null;
    let retainedView=null,activeRun=null;
    let config = {name: 'TinyCNN experiment', release: '', widths: [16,32,64], input_size: 96, epochs: 3, seed: 17};
    let journal = history.state?.modelTrial || null;
    const identity = () => window.TuldokAuth?.identity();
    const owner = () => identity()?.kind === 'owner';
    // Denials must reach the Runs owner before local presentation catches can
    // absorb them, including after auth.js clears a revoked session identity.
    async function api(...args){
      const runId=activeRun,credential=identity()?.credential_id,version=generation;
      try{return await transport(...args);}
      catch(error){
        if(runId&&activeRun===runId&&version===generation&&!args[4]?.aborted&&[401,403].includes(error.status))onAccessFailure(error,runId,credential);
        throw error;
      }
    }
    function disposeRetained(){retainedView?.dispose();retainedView=null;}
    function retainedHTML(run){
      return run?.graph?.recipe===recipe&&run.state==='completed'&&evidence?.state==='verified'&&
        evidence.metric_definition_hashes?.accuracy&&run.artifacts?.some(item=>item.name==='model-evidence.json')?
        '<section class="retained-analysis" data-retained-analysis aria-label="Retained checkpoint analysis"></section>':'';
    }
    function bindRetained(node,run,current){
      disposeRetained();
      const target=node.querySelector('[data-retained-analysis]');
      if(!target||!current()||!retainedHTML(run))return;
      if(!window.WorkspaceRetainedAnalysis){target.textContent='Retained chart assets are unavailable. Refresh to retry.';return;}
      const artifact=run.artifacts.find(item=>item.name==='model-evidence.json');
      const selected=evidence.checkpoint_index.entries.find(item=>item.checkpoint.sha256===checkpoint)||evidence.checkpoint_index.entries[0];
      const authority=JSON.stringify([identity()?.catalog_id,identity()?.actor_id,identity()?.credential_id]);
      const valid=()=>current()&&authority===JSON.stringify([identity()?.catalog_id,identity()?.actor_id,identity()?.credential_id]);
      retainedView=window.WorkspaceRetainedAnalysis.mount(target,{load:async(request,options)=>{
        if(!valid())throw Error('Retained result authority changed.');
        const {run_id,...body}=request;
        const value=await api('runs/'+enc(run_id)+'/retained-analysis'+(options.export?'/export':''),body,1,10000,options.signal);
        if(!valid())throw Error('Retained result authority changed.');
        return value;
      }});
      void retainedView.update({query_id:'retained_checkpoint_examples',query_version:1,run_id:run.id,
        evaluation_sha256:artifact.sha256,checkpoint_sha256:selected.checkpoint.sha256,
        metric_id:'accuracy',metric_definition_sha256:evidence.metric_definition_hashes.accuracy,limit:1,offset:0},authority);
    }
    const remember = () => history.replaceState({...history.state, modelTrial: journal}, '');
    function notice(text, error = false) { message = text; failed = error; announce(text,error); }
    function scope() {
      const intent = getIntent(), credential = identity()?.credential_id, version = generation;
      return () => intent === getIntent() && credential === identity()?.credential_id && version === generation && getView() === 'pipeline';
    }
    async function write(route, body, current) {
      const result = await api(route,body);
      if (!current()) throw Error('Saved state may have changed after navigation or session change. Refresh the catalog to inspect it.');
      return result;
    }
    async function perform(fn) {
      if (busy) return;
      const previousFocus=document.activeElement?.id;
      busy = true; render();
      try { await fn(scope()); } catch (error) { notice(error.message,true); }
      finally { busy = false; if(getView()==='pipeline'){render();const focus=root?.querySelector(journal?.trial?'#model-start':'#'+CSS.escape(previousFocus||'model-prepare'));focus?.focus({preventScroll:true});} }
    }
    function render() {
      if (!root || getView() !== 'pipeline') return;
      const focus = root.contains(document.activeElement) ? document.activeElement.id : null;
      const eligible = releases.filter(item => item.status === 'available' &&
        (item.allowed_recipes || [item.recipe]).includes(recipe));
      const ready = !!journal?.trial;
      root.innerHTML = `<section class="panel panel-pad model-workspace" aria-labelledby="model-heading"><div class="model-heading"><div><span class="eyebrow">MODEL DEVELOPMENT · REAL CPU</span><h2 id="model-heading">Configure → train → inspect</h2></div><a href="#runs">Inspect runs →</a></div>
      <p>Typed TinyCNN configuration, a frozen image release and one finite trial. Each epoch records its actual checkpoint, validation metrics and fixed probes automatically.</p>
      <p class="model-status ${failed?'error-panel':''}" role="status">${esc(message)}</p>
      ${!definition ? '<p>Model-aware image training is unavailable in the installed recipe definitions. Existing saved workflows remain available below.</p>' : `<form id="model-form"><fieldset ${busy||journal?'disabled':''}><legend>Model and training inputs</legend><div class="model-fields"><label>Name<input id="model-name" required maxlength="120" value="${esc(config.name)}"></label><label>Frozen image release<select id="model-release" required><option value="">Choose a release</option>${eligible.map(item=>`<option value="${esc(item.id)}" ${config.release===item.id?'selected':''}>${esc(item.id.slice(0,12))} · ${esc(item.records)} images</option>`).join('')}</select></label>
      ${config.widths.map((value,i)=>`<label>Block ${i+1} width<input id="model-width-${i}" type="number" min="4" max="64" step="1" required value="${value}"></label>`).join('')}
      <label>Input size<select id="model-size">${[32,64,96].map(value=>`<option ${value===config.input_size?'selected':''} value="${value}">${value} × ${value} RGB</option>`).join('')}</select></label><label>Head<select id="model-head"><option value="linear">Linear class head</option></select></label><label>Epochs<input id="model-epochs" type="number" min="2" max="${definition.parameter_bounds?.epochs?.maximum||10}" step="1" value="${config.epochs}" required></label><label>Seed<input id="model-seed" type="number" min="${definition.parameter_bounds?.seed?.minimum??0}" max="${definition.parameter_bounds?.seed?.maximum??2147483647}" step="1" value="${config.seed}" required></label></div><p class="footnote">Widths are integers from 4–64. RGB resize has no fitted statistics or augmentation. The release fixes class order. Preparing saves immutable material; training starts only with Start finite trial.</p></fieldset><button class="primary" id="model-prepare" ${busy||ready||journal?.uncertain||foreignPending||!eligible.length||!owner()?'disabled':''}>${journal?'Continue preparation':'Prepare finite trial'}</button></form>
      ${foreignPending?'<p class="error-panel">Another actor has an unresolved trial admission. Return to that session to reconcile it before preparing another trial.</p>':''}
      ${!eligible.length?'<p>No eligible frozen image release. Review records and freeze a release in <a href="#data">Data</a>, then refresh Pipeline.</p>':''}
      ${!owner()?'<p>Starting built-in training requires the current owner session.</p>':''}
      ${journal?`<div class="model-trial"><h3>${ready?'Prepared finite trial':'Preparation progress'}</h3><p>${esc(journal.config?.name)} · ${esc(journal.config?.epochs)} epochs · widths ${esc(journal.config?.widths?.join(' / '))}</p><dl>${[['Model',journal.model?.id],['Frozen material',journal.material?.ref?.sha256],['Recipe',journal.graph?.id],['Study',journal.study?.id],['Trial',journal.trial?.id],['Run',journal.run?.id]].filter(([,value])=>value).map(([name,value])=>`<div><dt>${name}</dt><dd>${esc(value)}</dd></div>`).join('')}</dl>${journal.uncertain?`<p class="error-panel">${esc(journal.uncertain)} Inspect saved state before preparing again.</p>`:''}<div class="actions">${ready&&!journal.run?`<button id="model-start" class="primary" ${busy||!owner()?'disabled':''}>${journal.admission?'Reconcile finite admission':'Start finite trial'}</button>`:''}${journal.run?'<button id="model-open-run">Inspect admitted run →</button>':''}<button id="model-new" ${busy||journal.admission||journal.uncertain?'disabled':''}>Configure another trial</button></div><p class="footnote">One requested training attempt. Finite budget: three attempt slots for training, export and verification; 10,800 admitted wall seconds, 1 GiB retained and 2 GiB staging. Admission rechecks current authority, material and runtime.</p></div>`:''}
      <details><summary>Saved studies · ${studies.length}</summary>${studies.map(study=>`<button class="model-study" data-model-study="${esc(study.id)}">${esc(study.name)} · ${esc(study.state)}</button>`).join('')||'<p>No saved studies.</p>'}<div id="model-study-detail">${studyDetail?`<p>Membership r${esc(studyDetail.study.membership_revision)}: ${esc(studyDetail.study.trial_ids.length)} trials. ${esc(studyDetail.charged.attempt_slots)} charged attempts.</p>${studyDetail.reservations.map(row=>`<button data-model-saved-run="${esc(row.run_id)}">Open run ${esc(row.run_id.slice(0,12))}</button>`).join('')}`:''}</div></details>`}</section>`;
      root.querySelector('#model-form')?.addEventListener('submit',event=>{
        event.preventDefault(); if(!journal)readConfig(); perform(prepare);
      });
      for (const element of root.querySelectorAll('#model-form input,#model-form select')) element.addEventListener('change',readConfig);
      root.querySelector('#model-start')?.addEventListener('click',()=>perform(start));
      root.querySelector('#model-open-run')?.addEventListener('click',()=>openRun(journal.run));
      root.querySelector('#model-new')?.addEventListener('click',()=>{journal=null;remember();message='Choose the new release and configuration, then prepare another finite trial.';render();});
      for (const button of root.querySelectorAll('[data-model-study]')) button.onclick=()=>perform(async current=>{
        const detail = await api('studies/'+enc(button.dataset.modelStudy)); if(!current())return;
        studyDetail=detail;
      });
      for(const button of root.querySelectorAll('[data-model-saved-run]'))button.onclick=()=>openRun({id:button.dataset.modelSavedRun});
      if(focus) root.querySelector('#'+CSS.escape(focus))?.focus({preventScroll:true});
    }
    function readConfig() {
      const value = id => root.querySelector('#'+id)?.value;
      config = {name:value('model-name'),release:value('model-release'),widths:[0,1,2].map(i=>Number(value('model-width-'+i))),input_size:Number(value('model-size')),epochs:Number(value('model-epochs')),seed:Number(value('model-seed'))};
    }
    async function prepare(current) {
      if(!owner())throw Error('An owner session is required.');
      if(foreignPending)throw Error('Reconcile the unresolved admission with its original actor.');
      if(journal?.uncertain)throw Error(journal.uncertain);
      if(!journal){journal={actor:identity()?.actor_id,config:structuredClone(config)};remember();}
      if(journal.actor!==identity()?.actor_id)throw Error('This preparation belongs to another actor.');
      const c=journal.config;
      if(!journal.model){
        const body=structuredClone(definition.model_template); body.name=c.name; body.specification={template:'tinycnn_v2',widths:c.widths,input_size:c.input_size,head:'linear'};body.preprocessing_policy.size=[c.input_size,c.input_size];
        try {journal.model=await write('models',body,current);remember();}
        catch(error){if([400,401,403,404,409].includes(error.status))throw error;journal.uncertain='Model creation acknowledgement is unresolved. Inspect the saved models before another creation.';remember();throw error;}
      }
      if(!journal.material){journal.material=await write('models/'+enc(journal.model.id)+'/publish',{revision:journal.model.revision},current);remember();}
      if(!journal.graph){
        try{journal.graph=await write('graphs',{name:c.name,release_id:c.release,recipe},current);remember();}
        catch(error){if([400,401,403,404,409].includes(error.status))throw error;journal.uncertain='Recipe creation acknowledgement is unresolved. Inspect saved recipes before another creation.';remember();throw error;}
      }
      if(!journal.configured){
        const document=structuredClone(journal.graph),train=document.nodes.find(node=>node.type==='train');
        Object.assign(train.parameters,{widths:c.widths,input_size:c.input_size,head:'linear',epochs:c.epochs,seed:c.seed});
        journal.graph=await write('graphs/'+enc(document.id),{revision:document.revision,document},current);journal.configured=true;remember();
      }
      if(!journal.validation){journal.validation=await write('graphs/'+enc(journal.graph.id)+'/validate',{revision:journal.graph.revision},current);remember();if(!journal.validation.valid||!journal.validation.selection_policy){journal.validation=null;remember();throw Error('Model recipe validation did not produce an exact frozen selection policy. Inspect its release and runtime.');}}
      if(!journal.study){
        try{journal.study=await write('studies',{name:c.name,limits:{attempt_slots:3,admitted_wall_seconds:10800,retained_bytes:1073741824,peak_staging_bytes:2147483648},policy:journal.validation.selection_policy},current);remember();}
        catch(error){if([400,401,403,404,409].includes(error.status))throw error;journal.uncertain='Study creation acknowledgement is unresolved. Inspect saved studies before another creation.';remember();throw error;}
      }
      if(!journal.prepare){journal.prepare={request_key:crypto.randomUUID(),revision:journal.study.revision,graph_id:journal.graph.id,graph_revision:journal.graph.revision,model:journal.material.ref,replicate:0};remember();}
      journal.trial=await write('studies/'+enc(journal.study.id)+'/prepare-trial',journal.prepare,current);remember();
      notice('Finite trial prepared. Its model, data and recipe material are frozen. Start it explicitly when ready.');
    }
    async function start(current) {
      if(!owner()||journal.actor!==identity()?.actor_id)throw Error('The preparing owner must start this trial.');
      if(!journal.admission){
        let state=await api('studies/'+enc(journal.study.id));if(!current())return;
        if(!state.study.open){
          if(!journal.continue){journal.continue={request_key:crypto.randomUUID(),revision:state.study.revision,admission_epoch:state.study.admission_epoch};remember();}
          await write('studies/'+enc(journal.study.id)+'/continue',journal.continue,current);
          state=await api('studies/'+enc(journal.study.id));if(!current())return;
        }
        journal.admission={request_key:crypto.randomUUID(),revision:state.study.revision,admission_epoch:state.study.admission_epoch,trial_id:journal.trial.id};remember();
      }
      let result;
      try{result=await write('studies/'+enc(journal.study.id)+'/admit',journal.admission,current);}
      catch(error){if([400,404,409].includes(error.status)&&['invalid','stale','unsupported','unavailable'].includes(error.code)){journal.admission=null;journal.continue=null;remember();}throw error;}
      journal.run=result.run;journal.admission=null;remember();notice('Durable finite attempt admitted. Epoch evidence appears after verified publication.');openRun(result.run);
    }
    return {
      queueComparison(runId,id){pendingComparison={runId,id,credential:identity()?.credential_id};},
      configure(value) {definition=value.definitions?.recipes?.find(item=>item.id===recipe);releases=value.releases;const saved=history.state?.modelTrial;if(!journal&&saved?.actor===identity()?.actor_id){journal=saved;foreignPending=false;}},
      sessionChanged() {pendingComparison=null;studies=[];studyDetail=null;message='';exportDraft={mode:'package',root:'',directory:'',runtime:'',packageRun:''};config={name:'TinyCNN experiment',release:'',widths:[16,32,64],input_size:96,epochs:3,seed:17};const saved=history.state?.modelTrial;foreignPending=!!(saved&&saved.actor!==identity()?.actor_id&&(saved.admission||saved.uncertain));if(journal?.actor!==identity()?.actor_id)journal=null;},
      mount(node) {root=node;render();},
      async refresh(current) {try{const result=await api('studies');if(current())studies=result.studies;}catch(error){if(current())notice('Saved studies unavailable: '+error.message,true);}},
      invalidate(preserveComparison=false) {activeRun=null;disposeRetained();if(!preserveComparison)pendingComparison=null;generation++;queryIntent++;compareIntent++;compareTargetIntent++;checkpointIntent++;checkpointBusy=false;evidence=null;comparison=null;checkpoint=null;probe=null;evidenceError='';detailPredictions=null;candidate=null;candidateError='';compareTarget=null;compareTargetRun=null;compareCheckpoint='';compareBusy=false;packageState=null;packageError='';exportSetup=null;exportJob=null;},
      async load(run,current) {
        disposeRetained();activeRun=run?.id||null;
        if(pendingComparison&&(pendingComparison.runId!==run?.id||pendingComparison.credential!==identity()?.credential_id))pendingComparison=null;
        const intent=++queryIntent;compareIntent++;compareTargetIntent++;checkpointIntent++;checkpointBusy=false;
        evidence=null;comparison=null;evidenceError='';candidate=null;candidateError='';packageState=null;packageError='';exportJob=null;compareTarget=null;compareTargetRun=null;compareCheckpoint='';compareId='';compareBusy=false;
        if(!evidenceRecipes.has(run?.graph?.recipe)||run.state!=='completed')return;
        try{
          let value=await api('runs/'+enc(run.id)+'/model-evidence',{});if(!current()||intent!==queryIntent)return;
          if(value.state==='verified'){
            const entry=value.checkpoint_index.entries.find(item=>item.checkpoint.sha256===checkpoint)||value.checkpoint_index.entries.find(item=>item.selected)||value.checkpoint_index.entries[0];
            if(entry){value=await api('runs/'+enc(run.id)+'/model-evidence',{checkpoint_sha256:entry.checkpoint.sha256});if(!current()||intent!==queryIntent)return;checkpoint=entry.checkpoint.sha256;}
          }
          evidence=value;
          const savedCandidate=history.state?.modelCandidates?.[run.id];
          if(savedCandidate?.actor===identity()?.actor_id){try{const saved=await api('candidates/'+enc(savedCandidate.id));if(current()&&intent===queryIntent){candidate=saved;await loadPackage(saved,current,intent);}}catch(error){if([401,403].includes(error.status))throw error;if(current()&&intent===queryIntent)candidateError=error.message;}}
        }catch(error){if([401,403].includes(error.status))throw error;if(current()&&intent===queryIntent)evidenceError=error.message;}
      },
      html(run,predictions) {
        detailPredictions=predictions;
        if(!evidenceRecipes.has(run?.graph?.recipe))return '<p class="muted model-history">Epoch checkpoint and probe history was not captured for this legacy workflow.</p>';
        if(evidenceError)return `<section class="model-evidence"><h3>Model evidence unavailable</h3><p class="error-panel" role="alert">${esc(evidenceError)}</p><p>No cached checkpoint or probe values are shown. Refresh saved runs to retry.</p></section>`;
        if(!evidence)return '<p>Model evidence has not been published yet.</p>';
        if(evidence.state==='unsupported')return `<p class="muted model-history">${esc(evidence.reason)}</p>`;
        return evidenceHTML(evidence,run)+retainedHTML(run);
      },
      bind(node,run,runs,rerender,current) {bindEvidence(node,run,runs,rerender,current);bindRetained(node,run,current);},
    };
    function evidenceHTML(value,run) {
      // Index and checkpoint/probe projections are supplied by the same Runs query.
      const points=value.checkpoint_index.entries.map(entry=>({checkpoint_sha256:entry.checkpoint.sha256,epoch:entry.clocks.epoch,progress:entry.clocks.epoch?('Epoch '+entry.clocks.epoch):('Fit pass '+entry.clocks.fit_pass),selected:entry.selected,
        metrics:Object.fromEntries(value.observations.filter(item=>item.checkpoint_sha256===entry.checkpoint.sha256).map(item=>[item.metric_id,item.state==='observed'?item.value:item.state==='undefined'?'Undefined: '+item.reason:'Unavailable']))}));
      const selected=points.find(item=>item.checkpoint_sha256===checkpoint)||points.find(item=>item.selected);
      checkpoint=selected?.checkpoint_sha256||null;
      const rows=probeRows(value,run),chosen=rows.find(item=>item.id===probe)||rows[0];probe=chosen?.id||null;
      return `<section class="model-evidence" aria-labelledby="model-evidence-heading"><h3 id="model-evidence-heading">${run.graph.recipe===recipe?'Linked epoch evidence':'Linked fit evidence'}</h3><p>Run ${esc(run.id.slice(0,12))} · fixed validation membership. Select a checkpoint to inspect its actual fitted state, metrics and probes.</p><div class="real-table-wrap" tabindex="0" aria-label="Epoch checkpoints"><table><caption>Checkpoints and validation metrics</caption><thead><tr><th scope="col">Progress</th><th scope="col">Accuracy</th><th scope="col">Loss</th><th scope="col">Checkpoint</th></tr></thead><tbody>${points.map(item=>`<tr ${item.checkpoint_sha256===checkpoint?'class="model-selected"':''}><th scope="row"><button id="model-checkpoint-${esc(item.checkpoint_sha256)}" data-model-checkpoint="${esc(item.checkpoint_sha256)}" aria-pressed="${item.checkpoint_sha256===checkpoint}">${esc(item.progress)}${item.selected?'<br><small>selected</small>':''}</button></th><td>${metric(item.metrics?.accuracy)}</td><td>${metric(item.metrics?.loss)}</td><td>${esc(item.checkpoint_sha256?.slice(0,12))}</td></tr>`).join('')}</tbody></table></div>${value.checkpoint?`<p>${value.checkpoint.clocks.epoch?`Epoch ${esc(value.checkpoint.clocks.epoch)} · ${esc(value.checkpoint.clocks.optimizer_update)} updates`:`Fit pass ${esc(value.checkpoint.clocks.fit_pass)}`} · ${(value.checkpoint.clocks.wall_elapsed_ms/1000).toFixed(2)} elapsed seconds</p><div class="actions"><a href="/api/workspace/runs/${enc(run.id)}/artifacts/${enc(value.checkpoint.weights.name)}" download>Download exact fitted state</a><a href="/api/workspace/runs/${enc(run.id)}/artifacts/${enc(value.checkpoint_index.entries.find(item=>item.checkpoint.sha256===checkpoint)?.checkpoint.name)}" download>Checkpoint descriptor</a></div>`:''}<div class="model-probes"><label>Fixed validation example<select id="model-probe">${rows.map(row=>`<option value="${esc(row.id)}" ${row.id===probe?'selected':''}>${esc(row.id.slice(0,12))} · ${esc(row.truth_label||row.target?.label||'frozen target')}</option>`).join('')}</select></label>${chosen?`<p>Frozen target: ${esc(chosen.truth_label||chosen.target?.label)} · prediction: ${esc(chosen.predicted_label||'See probabilities')}</p><div class="real-table-wrap"><table><caption>Frozen class probabilities</caption><thead><tr><th scope="col">Class</th><th scope="col">Probability</th></tr></thead><tbody>${chosen.probabilities.map((value,index)=>`<tr><th scope="row">${esc((run.metrics?.class_vocabulary||detailPredictions?.class_vocabulary||[])[index]?.label||String(index))}</th><td>${Number.isFinite(value)?value.toFixed(6):'Unavailable'}</td></tr>`).join('')}</tbody></table></div><p>${chosen.current_record?.revision?`Current annotation r${esc(chosen.current_record.revision)}${chosen.current_record.changed?' · changed since this run':''}`:'Current record availability is checked when opened.'}</p><button id="model-correct">Open current record in Data →</button><p class="footnote">Save and review the correction, then freeze a new release and prepare a new trial. These frozen targets stay unchanged.</p>`:'<p>No disclosed validation probes in this checkpoint.</p>'}</div>${comparisonHTML(run)}${candidateHTML(run,selected)}<details><summary>Verified evidence identity</summary><pre>${esc(JSON.stringify({manifest:value.manifest,checkpoint_index:value.checkpoint_index},null,2))}</pre></details></section>`;
    }
    function comparisonHTML(run) {
      const options=(evidence.metric_definitions||[]).map(item=>`<option value="${esc(item.id)}" ${item.id===compareMetric?'selected':''}>${esc(item.id)} · ${esc(item.units)} · ${esc(item.direction)}</option>`).join('');
      const entries=compareTarget?.checkpoint_index?.entries||[];
      return `<form id="model-compare-form" class="model-comparison"><h4>Compare exact validation evidence</h4><p>Current checkpoint ${esc(checkpoint?.slice(0,12))}. Choose the other run, its checkpoint and the metric. A paired delta requires compatible frozen populations and meaning.</p><div class="model-fields"><label>Other run<select id="model-compare-run"><option value="">Choose another completed model run</option></select></label><label>Other checkpoint<select id="model-compare-checkpoint" required ${!entries.length?'disabled':''}><option value="">Choose a checkpoint</option>${entries.map(item=>`<option value="${esc(item.checkpoint.sha256)}" ${item.checkpoint.sha256===compareCheckpoint?'selected':''}>${item.clocks.epoch?'Epoch '+esc(item.clocks.epoch):'Fit pass '+esc(item.clocks.fit_pass)}${item.selected?' · selected':''} · ${esc(item.checkpoint.sha256.slice(0,12))}</option>`).join('')}</select></label><label>Metric<select id="model-compare-metric" required><option value="">Choose a metric</option>${options}</select></label><label>Comparison<select id="model-compare-mode"><option value="paired" ${compareMode==='paired'?'selected':''}>Paired delta</option><option value="side_by_side" ${compareMode==='side_by_side'?'selected':''}>Side by side</option></select></label></div><button id="model-compare" ${compareBusy||checkpointBusy||!entries.length?'disabled':''}>${compareBusy?'Loading evidence…':'Compare'}</button></form>${comparison?comparisonResultHTML(comparison):''}`;
    }
    function comparisonResultHTML(value) {
      if(!value.sides)return `<p class="error-panel" role="alert">${esc(value.reasons.join(' '))}</p>`;
      const compatible=value.state==='compatible';
      return `<section class="model-comparison-result"><p class="${compatible||value.mode==='side_by_side'?'callout':'error-panel'}" role="status">${value.mode==='side_by_side'?'Side-by-side values are shown without a paired delta.':compatible?'Identical compatible validation membership. Exact paired comparison is available.':'Validation populations or metric definitions differ; paired delta is unavailable.'}</p><div class="real-table-wrap"><table><caption>Exact comparison selectors and observed values</caption><thead><tr><th scope="col">Evidence</th><th scope="col">Current run</th><th scope="col">Other run</th></tr></thead><tbody>${[['Run',...value.sides.map(item=>item.run_id.slice(0,12))],['Checkpoint',...value.sides.map(item=>item.checkpoint_sha256.slice(0,12))],['Metric',...value.sides.map(item=>item.metric_id)],['Value',...value.sides.map(item=>item.result.state==='observed'?metric(item.result.value):'Undefined: '+item.result.reason)],['Examples',...value.sides.map(item=>item.result.state==='observed'?item.result.sample_count:'Undefined')]].map(row=>`<tr><th scope="row">${esc(row[0])}</th><td>${esc(row[1])}</td><td>${esc(row[2])}</td></tr>`).join('')}</tbody></table></div>${value.delta?`<p>Paired delta: ${value.delta.state==='observed'?metric(value.delta.value)+' '+esc(value.delta.units):'Undefined: '+esc(value.delta.reason)}</p>`:''}${value.reasons.length?`<p>${esc(value.reasons.join(' '))}</p>`:''}<details><summary>Exact evaluation, checkpoint and metric identities</summary><pre>${esc(JSON.stringify(value,null,2))}</pre></details></section>`;
    }
    function candidateHTML(run,selected) {
      if(!run.study_membership)return '<p class="footnote">This run has no finite-study membership for candidate selection.</p>';
      return `<section class="model-candidate"><h4 id="model-candidate-heading" tabindex="-1">Candidate and export</h4>${candidate?`<p><strong>Diagnostic candidate retained</strong> · ${esc(candidate.ref.id.slice(0,12))}</p><p>${esc(candidate.candidate.limitations.join(' '))}</p><p>Candidate checkpoint ${esc(candidate.checkpoint.sha256.slice(0,12))}</p>`:`<p>The study selects its validation-selected checkpoint. Candidate selection records a diagnostic decision; it does not establish model quality.</p><button id="model-select-candidate" ${candidateBusy||checkpointBusy||!selected?.selected?'disabled':''}>${candidateBusy?'Selecting candidate…':'Retain selected checkpoint candidate'}</button>${!selected?.selected?'<p>Select the checkpoint marked selected to retain its candidate.</p>':''}`}${candidateError?`<p class="error-panel" role="alert">${esc(candidateError)}</p>`:''}${candidate?exportHTML():'<p class="footnote">Package: not exported. Fresh inference: not verified. Export and verification are separate outcomes from candidate selection.</p>'}</section>`;
    }
    async function loadPackage(value,current,intent) {
      packageState=null;packageError='';
      const saved=history.state?.modelExports?.[value.ref.id];exportJob=saved?.actor===identity()?.actor_id?saved:null;
      if(!contracts['studies.package_state'])return;
      try{const state=await api('candidates/'+enc(value.ref.id)+'/package-state');if(!current()||intent!==queryIntent)return;packageState=state;}
      catch(error){if([401,403].includes(error.status))throw error;if(current()&&intent===queryIntent)packageError=error.message;}
    }
    function exportHTML() {
      if(!contracts['studies.package_state'])return '<p>Package preparation is unavailable in this installed interface. No package or fresh verification is claimed.</p>';
      const packages=packageState?.packages||[];
      return `<section class="model-export"><h4>Package and fresh inference</h4>${packageError?`<p class="error-panel" role="alert">Export state unavailable: ${esc(packageError)}</p>`:window.WorkspacePackageStateHTML(packageState)}
      <button id="model-export-refresh" ${exportBusy?'disabled':''}>Refresh export state</button>
      ${!owner()?'<p>Preparing and approving these local operations requires the owner session.</p>':!exportSetup?`<button id="model-export-setup" ${exportBusy?'disabled':''}>Load export setup</button>`:!exportSetup.roots.length?'<p>No project root is configured for this local server. Configure an allowed project root before preparing export.</p>':!exportJob?`<form id="model-export-form"><fieldset ${exportBusy?'disabled':''}><legend>Prepare one finite operation</legend><div class="model-fields"><label>Operation<select id="model-export-mode"><option value="package" ${exportDraft.mode==='package'?'selected':''}>Export package</option><option value="verifier" ${exportDraft.mode==='verifier'?'selected':''} ${!packages.length?'disabled':''}>Verify fresh inference</option></select></label><label>Configured root<select id="model-export-root">${exportSetup.roots.map(alias=>`<option value="${esc(alias)}" ${exportDraft.root===alias?'selected':''}>${esc(alias)}</option>`).join('')}</select></label><label>New directory<input id="model-export-directory" required maxlength="120" pattern="[A-Za-z0-9][A-Za-z0-9_.-]{0,119}" value="${esc(exportDraft.directory)}"></label><label>Exact CPU runtime snapshot SHA256<input id="model-export-runtime" required minlength="64" maxlength="64" pattern="[a-f0-9]{64}" value="${esc(exportDraft.runtime)}"></label>${packages.length?`<label>Package for fresh verification<select id="model-export-package">${packages.map(item=>`<option value="${esc(item.run_id)}" ${item.run_id===exportDraft.packageRun?'selected':''}>${esc(item.sha256.slice(0,12))} · Run ${esc(item.run_id.slice(0,12))}</option>`).join('')}</select></label>`:''}</div><p class="footnote">Use an existing captured CPU runtime. Preparation writes a new operation project and immutable trial; approval and execution remain separate actions.</p><button id="model-export-prepare">Prepare operation</button></fieldset></form>`:`<div class="model-export-prepared"><h5>${exportJob.mode==='package'?'Package':'Fresh verifier'} operation</h5>${exportJob.prepared?`<p>Prepared trial ${esc(exportJob.prepared.trial.id.slice(0,12))}</p><p class="model-hash">Exact material SHA256 ${esc(exportJob.prepared.trial.material.sha256)}</p><details><summary>Inspect prepared operation</summary><pre>${esc(JSON.stringify(exportJob.prepared,null,2))}</pre></details>${exportJob.run?`<p>Admitted Run ${esc(exportJob.run.id.slice(0,12))}</p><button id="model-export-open">Inspect operation Run →</button><button id="model-export-next" ${exportBusy?'disabled':''}>Prepare another operation</button>`:exportJob.approval?`<p>Exact one-use approval ${esc(exportJob.approval.id.slice(0,12))}</p><button id="model-export-start" class="primary" ${exportBusy?'disabled':''}>${exportJob.admission?'Reconcile exact admission':'Start approved operation'}</button>`:`<button id="model-export-approve" ${exportBusy||exportJob.approvalUnknown?'disabled':''}>Approve this exact operation</button>${exportJob.approvalUnknown?'<p class="error-panel">Approval acknowledgement is unresolved. Inspect execution grants before issuing another approval.</p>':''}`}`:`${exportJob.preparationUnknown?'<p>The original preparation acknowledgement is unresolved. Reconcile the same request before changing inputs.</p>':''}<button id="model-export-resume" ${exportBusy?'disabled':''}>Reconcile operation preparation</button>${exportJob.failureKnown&&!exportJob.preparationUnknown?'<button id="model-export-revise">Revise preparation inputs</button>':''}`}</div>`}
      </section>`;
    }
    function saveExport(job) {history.replaceState({...history.state,modelExports:{...history.state?.modelExports,[job.candidate_id]:job}},'');}
    function bindExport(node,run,rerender,current) {
      if(!candidate)return;
      async function action(fn){if(exportBusy)return;exportBusy=true;packageError='';const intent=++queryIntent;rerender();try{await fn(()=>current()&&intent===queryIntent);}catch(error){if(current()&&intent===queryIntent)packageError=error.message;}finally{exportBusy=false;if(current())rerender();}}
      node.querySelector('#model-export-refresh')?.addEventListener('click',()=>action(valid=>loadPackage(candidate,valid,queryIntent)));
      node.querySelector('#model-export-setup')?.addEventListener('click',()=>action(async valid=>{
        const setup=await api('project-snapshots');if(!valid())return;exportSetup=setup;exportDraft.root=setup.roots[0]||'';exportDraft.directory='candidate-'+candidate.ref.id.slice(0,12)+'-package';
      }));
      function read(){const value=id=>node.querySelector('#'+id)?.value;exportDraft={mode:value('model-export-mode'),root:value('model-export-root'),directory:value('model-export-directory'),runtime:value('model-export-runtime'),packageRun:value('model-export-package')||''};}
      for(const field of node.querySelectorAll('#model-export-form input,#model-export-form select'))field.addEventListener('change',read);
      async function prepare(valid){
        let job=exportJob;
        if(!job){read();const state=await api('studies/'+enc(candidate.candidate.study_id));if(!valid())return;
          const body={request_key:crypto.randomUUID(),revision:state.study.revision,candidate_id:candidate.ref.id,root:exportDraft.root,directory:exportDraft.directory,runtime_snapshot_sha256:exportDraft.runtime};
          if(exportDraft.mode==='verifier'){const item=packageState.packages.find(item=>item.run_id===exportDraft.packageRun);if(!item)throw Error('Choose a verified package.');Object.assign(body,{package_run_id:item.run_id,package_sha256:item.sha256});}
          job={actor:identity()?.actor_id,candidate_id:candidate.ref.id,study_id:candidate.candidate.study_id,mode:exportDraft.mode,body};saveExport(job);exportJob=job;
        }
        if(job.actor!==identity()?.actor_id)throw Error('This operation belongs to another actor.');
        try{job.prepared=await api('studies/'+enc(job.study_id)+'/prepare-'+job.mode,job.body);job.preparationUnknown=false;job.failureKnown=false;saveExport(job);if(valid())exportJob=job;}
        catch(error){if([400,401,403,404,409].includes(error.status)){job.failureKnown=!job.preparationUnknown;}else{job.preparationUnknown=true;job.failureKnown=false;}saveExport(job);throw error;}
      }
      node.querySelector('#model-export-form')?.addEventListener('submit',event=>{event.preventDefault();read();action(prepare);});
      node.querySelector('#model-export-resume')?.addEventListener('click',()=>action(prepare));
      node.querySelector('#model-export-revise')?.addEventListener('click',()=>{if(!exportJob?.failureKnown||exportJob.preparationUnknown)return;const saved={...history.state?.modelExports};delete saved[candidate.ref.id];history.replaceState({...history.state,modelExports:saved},'');exportJob=null;rerender();});
      node.querySelector('#model-export-approve')?.addEventListener('click',()=>action(async valid=>{
        const job=exportJob;if(!valid())return;if(job.actor!==identity()?.actor_id)throw Error('This operation belongs to another actor.');
        try{job.approval=await api('studies/'+enc(job.study_id)+'/approve',{trial_id:job.prepared.trial.id,expected_material_sha256:job.prepared.trial.material.sha256,consumer_actor_id:job.actor});saveExport(job);if(valid())exportJob=job;}
        catch(error){if(![400,401,403,404,409].includes(error.status)){job.approvalUnknown=true;saveExport(job);}throw error;}
      }));
      node.querySelector('#model-export-start')?.addEventListener('click',()=>action(async valid=>{
        const job=exportJob;if(!valid())return;if(job.actor!==identity()?.actor_id)throw Error('This operation belongs to another actor.');
        if(!job.admission){let state=await api('studies/'+enc(job.study_id));if(!valid())return;
          if(!state.study.open){if(!job.continue){job.continue={request_key:crypto.randomUUID(),revision:state.study.revision,admission_epoch:state.study.admission_epoch};saveExport(job);}await api('studies/'+enc(job.study_id)+'/continue',job.continue);if(!valid())return;state=await api('studies/'+enc(job.study_id));if(!valid())return;}
          job.admission={request_key:crypto.randomUUID(),revision:state.study.revision,admission_epoch:state.study.admission_epoch,trial_id:job.prepared.trial.id,approval_id:job.approval.id};saveExport(job);
        }
        let result;try{result=await api('studies/'+enc(job.study_id)+'/admit',job.admission);}
        catch(error){if([400,404,409].includes(error.status)&&['invalid','stale','unsupported','unavailable'].includes(error.code)){job.admission=null;job.continue=null;saveExport(job);}throw error;}job.run=result.run;saveExport(job);if(!valid())return;exportJob=job;openRun(result.run);
      }));
      node.querySelector('#model-export-open')?.addEventListener('click',()=>openRun(exportJob.run));
      node.querySelector('#model-export-next')?.addEventListener('click',()=>{
        const remaining={...history.state?.modelExports};delete remaining[candidate.ref.id];history.replaceState({...history.state,modelExports:remaining},'');exportDraft.runtime=exportJob.body.runtime_snapshot_sha256;exportDraft.root=exportJob.body.root;exportJob=null;exportDraft.mode=packageState?.packages?.length?'verifier':'package';exportDraft.directory='candidate-'+candidate.ref.id.slice(0,12)+'-'+exportDraft.mode;rerender();
      });
    }
    function probeRows(value,run) {
      const vocabulary=run.metrics?.class_vocabulary||detailPredictions?.class_vocabulary||[];
      return (value.predictions?.rows||[]).map(row=>{
        const member=value.probe.members.find(item=>item.ordinal===row.ordinal),reference=member.frozen_reference;
        const current=detailPredictions?.rows.find(item=>item.id===reference.id)?.current_record;
        return {...reference,...row,truth_label:vocabulary[row.truth_index]?.label||String(row.truth_index),predicted_label:vocabulary[row.predicted_index]?.label||String(row.predicted_index),current_record:current};
      });
    }
    function clearComparison() {
      compareIntent++;comparison=null;
      if(compareBusy?.kind==='comparison')compareBusy=false;
    }
    function bindEvidence(node,run,runs,rerender,current) {
      if(!evidence||!evidenceRecipes.has(run?.graph?.recipe))return;
      for(const button of node.querySelectorAll('[data-model-checkpoint]'))button.onclick=async()=>{
        if(candidateBusy)return;const sha=button.dataset.modelCheckpoint,intent=++checkpointIntent;clearComparison();checkpointBusy=true;rerender();
        try{const value=await api('runs/'+enc(run.id)+'/model-evidence',{checkpoint_sha256:sha});if(!current()||intent!==checkpointIntent)return;evidence=value;checkpoint=sha;rerender();}
        catch(error){if(current()&&intent===checkpointIntent){evidence=null;evidenceError=error.message;rerender();}}
        finally{if(current()&&intent===checkpointIntent){checkpointBusy=false;rerender();}}
      };
      node.querySelector('#model-select-candidate')?.addEventListener('click',async()=>{
        if(candidateBusy||checkpointBusy)return;candidateBusy=true;candidateError='';const intent=++queryIntent;rerender();
        try{
          const member=run.study_membership;if(!member)throw Error('This run has no finite-study membership.');
          const state=await api('studies/'+enc(member.study_id));if(!current()||intent!==queryIntent)return;
          const requests=history.state?.modelCandidateRequests||{};let request=requests[run.id];
          if(request&&request.actor!==identity()?.actor_id)throw Error('An unresolved candidate request belongs to another actor.');
          if(!request){request={actor:identity()?.actor_id,body:{request_key:crypto.randomUUID(),revision:state.study.revision,trial_id:member.trial_id,run_id:run.id,checkpoint_sha256:checkpoint}};history.replaceState({...history.state,modelCandidateRequests:{...requests,[run.id]:request}},'');}
          const result=await api('studies/'+enc(member.study_id)+'/select-candidate',request.body);
          const remaining={...history.state?.modelCandidateRequests};delete remaining[run.id];
          history.replaceState({...history.state,modelCandidateRequests:remaining,modelCandidates:{...history.state?.modelCandidates,[run.id]:{actor:request.actor,id:result.ref.id}}},'');
          if(!current()||intent!==queryIntent)return;candidate=result;await loadPackage(result,current,intent);announce('Diagnostic candidate retained. Export and fresh inference verification remain separate.');
        }catch(error){if(current()&&intent===queryIntent){candidateError=error.message;if([400,404,409].includes(error.status)&&['invalid','stale','unsupported','unavailable'].includes(error.code)){const requests={...history.state?.modelCandidateRequests};delete requests[run.id];history.replaceState({...history.state,modelCandidateRequests:requests},'');}}}
        finally{candidateBusy=false;if(current()){rerender();if(candidate&&intent===queryIntent)node.querySelector('#model-candidate-heading')?.focus();}}
      });
      node.querySelector('#model-probe')?.addEventListener('change',event=>{probe=event.target.value;rerender();});
      node.querySelector('#model-correct')?.addEventListener('click',()=>{
        const row=probeRows(evidence,run).find(item=>item.id===probe);
        if(row)openRecord({...row,run_id:run.id,release_id:run.release_id,split:'validation'});
      });
      bindExport(node,run,rerender,current);
      const select=node.querySelector('#model-compare-run');
      if(select)select.innerHTML='<option value="">Choose another completed model run</option>'+runs.filter(item=>item.id!==run.id&&item.state==='completed'&&evidenceRecipes.has(item.graph?.recipe)).map(item=>`<option value="${esc(item.id)}" ${item.id===compareId?'selected':''}>${esc(item.graph.name)} · ${esc(item.id.slice(0,12))}</option>`).join('');
      select?.addEventListener('change',async()=>{
        compareId=select.value;compareTarget=null;compareTargetRun=null;compareCheckpoint='';clearComparison();const intent=++compareTargetIntent;
        const token={kind:'target'};compareBusy=compareId?token:false;
        if(!compareId){rerender();return;}rerender();
        try{const [detail,value]=await Promise.all([api('runs/'+enc(compareId)),api('runs/'+enc(compareId)+'/model-evidence',{})]);if(!current()||intent!==compareTargetIntent)return;if(value.state!=='verified')throw Error('The other run has no verified model evidence.');compareTarget=value;compareTargetRun=detail;}
        catch(error){if(current()&&intent===compareTargetIntent)comparison={reasons:[error.message]};}
        finally{if(compareBusy===token){compareBusy=false;if(current())rerender();}}
      });
      if(pendingComparison?.runId===run.id&&pendingComparison.credential===identity()?.credential_id&&select&&[...select.options].some(option=>option.value===pendingComparison.id)){select.value=pendingComparison.id;pendingComparison=null;select.dispatchEvent(new Event('change'));}
      for(const [id,update] of [['model-compare-checkpoint',value=>compareCheckpoint=value],['model-compare-metric',value=>compareMetric=value],['model-compare-mode',value=>compareMode=value]])node.querySelector('#'+id)?.addEventListener('change',event=>{update(event.target.value);clearComparison();rerender();});
      node.querySelector('#model-compare-form')?.addEventListener('submit',async event=>{
        event.preventDefault();if(compareBusy||checkpointBusy||!compareId||!compareTarget||!compareCheckpoint||!compareMetric)return;const intent=++compareIntent,token={kind:'comparison'};compareBusy=token;rerender();
        try{
          const evaluation=run.artifacts.find(item=>item.name==='model-evidence.json'),otherEvaluation=compareTargetRun.artifacts.find(item=>item.name==='model-evidence.json');
          const leftMetric=evidence.metric_definition_hashes?.[compareMetric],rightMetric=compareTarget.metric_definition_hashes?.[compareMetric];
          if(!evaluation||!otherEvaluation||!leftMetric||!rightMetric)throw Error('The exact evaluation or metric definition identity is unavailable.');
          const value=await api('runs/'+enc(run.id)+'/compare-model-evidence',{other_run_id:compareId,checkpoint_sha256:checkpoint,other_checkpoint_sha256:compareCheckpoint,evaluation_sha256:evaluation.sha256,other_evaluation_sha256:otherEvaluation.sha256,metric_id:compareMetric,metric_definition_sha256:leftMetric,other_metric_definition_sha256:rightMetric,mode:compareMode});
          if(!current()||intent!==compareIntent)return;comparison=value;announce(value.mode==='side_by_side'?'Exact side-by-side values are shown.':value.state==='compatible'?'Compatible validation membership. Exact paired comparison is shown.':'Paired delta is unavailable for these exact evidence selectors.');
        }catch(error){if(current()&&intent===compareIntent)comparison={reasons:[error.message]};}
        finally{if(compareBusy===token){compareBusy=false;if(current())rerender();}}
      });
    }
  };

  // Passive external evidence inspection shares the existing package-state owner.
  // Candidate discovery is an authorized Run-scoped query, never artifact inference.
  window.WorkspaceCandidatePackageEvidence = function ({api}) {
    let generation=0,intent=0,runId=null,busy=false,error='',refs=[],states=new Map(),selected='',next=null;
    const identity=()=>window.TuldokAuth?.identity()?.credential_id;
    const id=value=>typeof value==='string'&&/^[a-f0-9]{32}$/.test(value);
    function clear(){refs=[];states=new Map();selected='';next=null;error='';}
    function validState(value,ref,run){
      return value&&['selected','package_complete','fresh_verified'].includes(value.state)&&
        value.candidate?.ref?.id===ref.id&&value.candidate.ref.sha256===ref.sha256&&
        value.candidate.ref.catalog_id===ref.catalog_id&&value.candidate.run_id===run.id&&
        value.candidate.candidate?.run_id===run.id&&value.candidate.candidate.id===ref.id&&
        Array.isArray(value.packages)&&value.packages.length<=100&&Array.isArray(value.verifications)&&value.verifications.length<=100;
    }
    async function load(run,current,append=false){
      if(!current())return;
      const own=++intent,version=generation,credential=identity();runId=run?.id||null;
      const valid=()=>current()&&own===intent&&version===generation&&credential===identity()&&runId===run?.id;
      const cursor=append?next:null;
      if(!append)clear();busy=true;
      if(!run||run.state!=='completed'){busy=false;return;}
      try{
        const page=await api('runs/'+enc(run.id)+'/candidates?limit=20'+(cursor?'&cursor='+enc(cursor):''));if(!valid())return;
        if(page.run_id!==run.id||!Array.isArray(page.candidates)||page.candidates.length>20||
          page.candidates.some(ref=>ref.kind!=='candidate'||!id(ref.id)||!id(ref.catalog_id)||typeof ref.sha256!=='string'||!/^[a-f0-9]{64}$/.test(ref.sha256)||run.dataset_id&&ref.catalog_id!==run.dataset_id)||
          page.next_cursor!==null&&!id(page.next_cursor))throw Error('The retained candidate index does not match this Run.');
        if(refs.length+page.candidates.length>100)throw Error('Inspect at most 100 retained candidates in this view.');
        for(const ref of page.candidates){
          if(refs.some(item=>item.id===ref.id))throw Error('The retained candidate index repeated an identity.');
          const value=await api('candidates/'+enc(ref.id)+'/package-state');if(!valid())return;
          if(!validState(value,ref,run))throw Error('Package evidence does not belong to this exact source Run and candidate.');
          refs.push(ref);states.set(ref.id,value);
        }
        next=page.next_cursor;
        const rank={selected:0,package_complete:1,fresh_verified:2};
        if(!states.has(selected))selected=[...refs].sort((a,b)=>rank[states.get(b.id).state]-rank[states.get(a.id).state]||a.id.localeCompare(b.id))[0]?.id||'';
      }catch(problem){if(valid()){clear();error=problem.message;}}
      finally{if(valid())busy=false;}
    }
    return {
      invalidate(){generation++;intent++;runId=null;busy=false;clear();},
      load,
      html(run){
        if(!run||run.id!==runId)return '';
        const state=states.get(selected),candidate=state?.candidate;
        return `<section class="model-evidence external-package-evidence" aria-labelledby="external-package-heading"><h3 id="external-package-heading">Retained candidate and inference evidence</h3><p>Current authorized records for this source Run. Package completeness and fresh inference verification are separate from field interpretation and candidate diagnostics.</p>${busy?'<p role="status">Loading exact retained candidate and package receipts…</p>':error?`<p class="error-panel" role="alert">Package evidence unavailable: ${esc(error)}</p><p>No cached package or verifier result is shown.</p>`:!candidate?'<p class="external-package-empty">No retained candidate package evidence is available for this Run. Package: not established. Fresh inference: not verified. Field plots do not establish export support.</p>':`<label>Retained candidate<select id="external-package-candidate">${refs.map(ref=>`<option value="${esc(ref.id)}" ${ref.id===selected?'selected':''}>${esc(ref.id.slice(0,12))} · ${esc(states.get(ref.id).state)}</option>`).join('')}</select></label><p>Diagnostic candidate <span class="field-hash">${esc(candidate.ref.id)}</span><br>Source Run <span class="field-hash">${esc(candidate.run_id)}</span><br>Checkpoint <span class="field-hash">${esc(candidate.checkpoint.sha256)}</span></p><p>${esc(candidate.candidate.limitations.join(' '))}</p>${window.WorkspacePackageStateHTML(state)}<div class="actions">${state.packages.map(item=>`<button type="button" data-package-open-run="${esc(item.run_id)}">Open package Run</button>`).join('')}${state.verifications.map(item=>`<button type="button" data-package-open-run="${esc(item.run_id)}">Open fresh verifier Run</button>`).join('')}</div>`}<div class="actions"><button id="external-package-refresh" type="button" aria-disabled="${busy}" aria-busy="${busy}">Refresh retained package evidence</button>${next?`<button id="external-package-more" type="button" aria-disabled="${busy}">Load more retained candidates</button>`:''}</div><p class="footnote">Inspection only. This panel cannot build a package, approve material or admit a Run. No model-quality or physical acceptance is inferred.</p></section>`;
      },
      bind(root,run,rerender,current,openRun){
        async function refresh(append){if(busy||!current()||run?.id!==runId)return;const task=load(run,current,append);rerender();await task;if(current())rerender();}
        root.querySelector('#external-package-refresh')?.addEventListener('click',()=>refresh(false));
        root.querySelector('#external-package-more')?.addEventListener('click',()=>refresh(true));
        root.querySelector('#external-package-candidate')?.addEventListener('change',event=>{if(busy||!current()||!states.has(event.target.value))return;selected=event.target.value;rerender();});
        for(const button of root.querySelectorAll('[data-package-open-run]'))button.addEventListener('click',()=>{if(current()&&!busy)openRun(button.dataset.packageOpenRun);});
      },
    };
  };
})();

// Declarative external field inspection. It displays retained numbers and never runs an adapter.
(() => {
  if (typeof window === 'undefined') return;
  const esc = value => window.workspaceEscape(value), enc = encodeURIComponent;
  const numeric = value => Object.is(value, -0) ? '-0' : String(value);
  const vector = value => Array.isArray(value) && value.length === 3 && value.every(Number.isFinite);
  const finiteJSON = (value,depth=0) => depth<=64 && (value===null || typeof value==='string' || typeof value==='boolean' || (typeof value==='number' && Number.isFinite(value)) || (Array.isArray(value) ? value.every(item=>finiteJSON(item,depth+1)) : typeof value==='object' && Object.prototype.toString.call(value)==='[object Object]' && Object.values(value).every(item=>finiteJSON(item,depth+1))));
  const clock = value => ['optimizer_update', 'epoch', 'fit_pass'].filter(key => value?.[key] !== null && value?.[key] !== undefined).map(key => ({optimizer_update:'Update',epoch:'Epoch',fit_pass:'Fit pass'}[key])+' '+value[key]).join(' · ');
  window.WorkspaceFieldEvidence = function ({api, announce}) {
    let generation = 0, query = 0, catalog = null, slice = null, error = '', busy = false, layoutObserver = null, layoutIntent = 0;
    let selection = {checkpoint:'',member:'',stage:'',field:'',axis:'z',index:0}, sample = {row:0,column:0};
    const eligible = run => run?.graph?.recipe === 'external_recipe' && run.state === 'completed';
    const records = () => (catalog?.fields || []).filter(item => item.checkpoint_sha256 === selection.checkpoint && item.member_ordinal === Number(selection.member));
    const selectedRecord = () => records().find(item => item.field_id === selection.field && item.stage === selection.stage);
    const stages = () => [...new Set(records().map(item => item.stage))];
    function choose(reset = false) {
      const entries = catalog?.checkpoint_index?.entries || [], members = catalog?.probe?.members || [];
      if (!entries.some(item => item.checkpoint.sha256 === selection.checkpoint)) selection.checkpoint = (entries.find(item => item.selected) || entries[0])?.checkpoint.sha256 || '';
      if (!members.some(item => String(item.ordinal) === selection.member)) selection.member = String(members[0]?.ordinal ?? '');
      const choices = stages();
      if (!choices.includes(selection.stage)) selection.stage = choices[0] || '';
      const fields = records().filter(item => item.stage === selection.stage);
      if (!fields.some(item => item.field_id === selection.field)) selection.field = fields[0]?.field_id || '';
      const record = selectedRecord(), maximum = record?.shape_zyx?.['zyx'.indexOf(selection.axis)] - 1;
      if (reset || !Number.isInteger(selection.index) || selection.index < 0 || selection.index > maximum) selection.index = 0;
    }
    function request() {
      return {checkpoint_sha256:selection.checkpoint,member_ordinal:Number(selection.member),field_id:selection.field,axis:selection.axis,index:selection.index,split:'validation'};
    }
    function validIndex() {
      const record = selectedRecord(), maximum = record?.shape_zyx?.['zyx'.indexOf(selection.axis)] - 1;
      return !!record && Number.isInteger(selection.index) && selection.index >= 0 && selection.index <= maximum;
    }
    function validateIndex(value,run) {
      if(value?.state==='unsupported')return;
      if(value?.state!=='verified'||!Array.isArray(value.fields)||!Array.isArray(value.checkpoints)||value.manifest?.producer?.run_id!==run.id||!Array.isArray(value.checkpoint_index?.entries)||!Array.isArray(value.probe?.members)||!Array.isArray(value.metric_definitions)||!Array.isArray(value.observations))throw Error('The retained field evidence index is unavailable or belongs to another Run.');
      if(value.probe.split!=='validation'||value.checkpoint_index.entries.some(item=>item.clocks?.physical_time!==null)||value.checkpoints.some(item=>item.clocks?.physical_time!==null))throw Error('Only standalone validation field evidence is supported; no physical timeline is qualified.');
    }
    function validateSlice(value,run,expected) {
      validateIndex(value,run);
      const field=value.field,record=(value.fields||[]).find(item=>item.checkpoint_sha256===expected.checkpoint_sha256&&item.member_ordinal===expected.member_ordinal&&item.field_id===expected.field_id);
      if(!field||!record||Object.entries(expected).some(([key,v])=>key!=='split'&&field[key]!==v)||field.stage!==record.stage||field.units!==record.units||!Array.isArray(field.shape_zyx)||!field.shape_zyx.every((n,i)=>n===record.shape_zyx[i])||!vector(field.physical_origin)||!vector(field.physical_row_step)||!vector(field.physical_column_step))throw Error('The returned field does not match the exact checkpoint, member, stage and slice selectors.');
      if(field.time_units!=='not_applicable'||!(/^[a-f0-9]{64}$/).test(field.gauge_policy_sha256)||!field.gauge_policy||typeof field.gauge_policy!=='object'||Array.isArray(field.gauge_policy)||!Object.keys(field.gauge_policy).length||!finiteJSON(field.gauge_policy))throw Error('The retained gauge policy or standalone time units are unavailable or invalid.');
      const [row,column]={z:['y','x'],y:['z','x'],x:['z','y']}[expected.axis],dimensions={z:record.shape_zyx[0],y:record.shape_zyx[1],x:record.shape_zyx[2]};
      if(field.row_axis!==row||field.column_axis!==column||!field.grid||typeof field.grid.units!=='string'||!['prediction','reference'].every(key=>Array.isArray(field[key])&&field[key].length===dimensions[row]&&field[key].every(values=>Array.isArray(values)&&values.length===dimensions[column]&&values.every(Number.isFinite))))throw Error('The field slice has invalid numeric arrays or physical axes.');
      return field;
    }
    async function fetchSlice(run,current) {
      const own=++query,version=generation,expected=request();slice=null;error='';busy=true;
      try {
        if(!validIndex())throw Error('Choose an integer slice index within the declared field shape.');
        const value=await api('runs/'+enc(run.id)+'/model-evidence',expected,2);
        if(!current()||version!==generation||own!==query)return;
        slice=validateSlice(value,run,expected);
        if(!Number.isInteger(sample.row)||sample.row<0||sample.row>=slice.prediction.length)sample.row=0;
        if(!Number.isInteger(sample.column)||sample.column<0||sample.column>=slice.prediction[0].length)sample.column=0;
      }catch(problem){if(current()&&version===generation&&own===query){slice=null;error=problem.message;if([401,403].includes(problem.status))catalog=null;}}
      finally{if(version===generation&&own===query)busy=false;}
    }
    function metricValue(row) {
      return !row?'Unavailable':row.state==='observed'?numeric(row.value):'Undefined: '+row.reason;
    }
    function indexHTML() {
      const definitions=catalog.metric_definitions;
      return `<div class="real-table-wrap" tabindex="0" aria-label="Retained field checkpoints and scalar observations"><table><caption>Retained checkpoints and declared validation observations</caption><thead><tr><th scope="col">Progress</th><th scope="col">Checkpoint</th>${definitions.map(item=>`<th scope="col">${esc(item.id)}<br><small>${esc(item.units)} · ${esc(item.direction)}</small></th>`).join('')}</tr></thead><tbody>${catalog.checkpoint_index.entries.map(entry=>`<tr ${entry.checkpoint.sha256===selection.checkpoint?'class="model-selected"':''}><th scope="row">${esc(clock(entry.clocks))}${entry.selected?' · selected':''}</th><td>${esc(entry.checkpoint.sha256.slice(0,12))}</td>${definitions.map(definition=>`<td>${esc(metricValue(catalog.observations.find(row=>row.checkpoint_sha256===entry.checkpoint.sha256&&row.metric_id===definition.id)))}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
    }
    function probeHTML() {
      if(!slice)return '';
      const {row,column}=sample,valid=Number.isInteger(row)&&Number.isInteger(column)&&row>=0&&column>=0&&row<slice.prediction.length&&column<slice.prediction[0].length;
      if(!valid)return '<p id="field-probe-value" role="status">Choose an in-bounds integer row and column.</p>';
      const physical=slice.physical_origin.map((value,i)=>value+row*slice.physical_row_step[i]+column*slice.physical_column_step[i]);
      return `<p id="field-probe-value" role="status">Row ${row}, column ${column}: prediction <strong>${esc(numeric(slice.prediction[row][column]))}</strong>; reference <strong>${esc(numeric(slice.reference[row][column]))}</strong> ${esc(slice.units)}. Display coordinates (${physical.map(value=>esc(numeric(value))).join(', ')}) ${esc(slice.grid.units)}.</p>`;
    }
    function sliceHTML() {
      if(!slice)return '';
      return `<div class="field-pair" aria-label="Prediction and reference share physical and display scales">${['prediction','reference'].map(key=>`<figure><figcaption>${key==='prediction'?'Prediction':'Reference'} · ${esc(slice.stage)} · ${esc(slice.units)}</figcaption><div class="field-slice-viewport"><canvas id="field-${key}" role="img" aria-label="${key} field slice; exact values available in the numeric probe"></canvas></div><p class="field-display-warning" data-field-display="${key}" hidden></p></figure>`).join('')}</div><p id="field-scale" class="footnote"></p><p>Standalone slice ${esc(slice.axis.toUpperCase())} ${slice.index}; rows +${esc(slice.row_axis)}, columns +${esc(slice.column_axis)}. ${esc(slice.centering)} · ${esc(slice.dtype)} · shape Z/Y/X ${slice.shape_zyx.join(' / ')}.</p><p class="field-coordinates">Physical sample origin (${slice.physical_origin.map(numeric).map(esc).join(', ')}) ${esc(slice.grid.units)}; row step (${slice.physical_row_step.map(numeric).map(esc).join(', ')}); column step (${slice.physical_column_step.map(numeric).map(esc).join(', ')}).</p><div class="field-metadata"><p>Time units: <strong>${esc(slice.time_units)}</strong> · standalone physical time is not declared.</p><p class="field-hash">Gauge policy SHA256 ${esc(slice.gauge_policy_sha256)}</p><details><summary>Declared gauge policy</summary><pre id="field-gauge-policy">${esc(JSON.stringify(slice.gauge_policy,null,2))}</pre></details></div><div class="model-fields field-probe-controls"><label>Probe row<input id="field-probe-row" type="number" min="0" max="${slice.prediction.length-1}" step="1" required value="${sample.row}"></label><label>Probe column<input id="field-probe-column" type="number" min="0" max="${slice.prediction[0].length-1}" step="1" required value="${sample.column}"></label></div><div id="field-probe-result">${probeHTML()}</div><p class="callout">Difference unavailable: this pair contains no retained difference array. Choose a declared field/stage to inspect it; no residual or error operator runs in the interface.</p>`;
    }
    function draw(root) {
      if(!slice)return;
      let low=Infinity,high=-Infinity;
      for(const key of ['prediction','reference'])for(const row of slice[key])for(const value of row){low=Math.min(low,value);high=Math.max(high,value);}
      const magnitude=Math.max(Math.abs(low),Math.abs(high)),range=magnitude?high/magnitude-low/magnitude:0;
      const rows=slice.prediction.length,columns=slice.prediction[0].length;
      const rowLength=Math.hypot(...slice.physical_row_step),columnLength=Math.hypot(...slice.physical_column_step);
      // Normalize first to keep the display-only aspect calculation bounded.
      const physicalAspect=(columns/rows)*(columnLength/rowLength);
      const label=`Shared display grayscale range ${numeric(low)} to ${numeric(high)} ${slice.units}. Both views use identical physical axis scales; original float values remain unchanged.`;
      const legend=root.querySelector('#field-scale');if(legend)legend.textContent=label;
      for(const key of ['prediction','reference']){
        const canvas=root.querySelector('#field-'+key);if(!canvas?.getContext)continue;
        canvas.width=columns;canvas.height=rows;
        const viewport=canvas.parentElement,width=viewport.clientWidth,height=viewport.clientHeight;
        const fitWidth=Math.min(width,height*physicalAspect),fitHeight=fitWidth/physicalAspect;
        const representable=Number.isFinite(physicalAspect)&&physicalAspect>0&&Number.isFinite(fitWidth)&&Number.isFinite(fitHeight)&&fitWidth>=1&&fitHeight>=1;
        const warning=root.querySelector('[data-field-display="'+key+'"]');
        if(warning){warning.hidden=representable;warning.textContent='The declared physical aspect cannot be represented at this viewport resolution. Exact numeric probes and coordinates remain available.';}
        canvas.hidden=!representable;if(!representable)continue;
        canvas.style.width=fitWidth+'px';canvas.style.height=fitHeight+'px';
        canvas.setAttribute('aria-label',`${key}; ${slice.axis} slice ${slice.index}, rows +${slice.row_axis}, columns +${slice.column_axis}. ${label}`);
        const context=canvas.getContext('2d'),pixels=context.createImageData(columns,rows);
        for(let row=0;row<rows;row++)for(let column=0;column<columns;column++){
          const number=slice[key][row][column],gray=range?Math.round(255*(number/magnitude-low/magnitude)/range):128;
          pixels.data.set([gray,gray,gray,255],(row*columns+column)*4);
        }
        context.putImageData(pixels,0,0);
      }
    }
    return {
      invalidate(){generation++;query++;catalog=null;slice=null;error='';busy=false;layoutIntent++;layoutObserver?.disconnect();layoutObserver=null;},
      async load(run,current){
        const version=++generation;query++;catalog=null;slice=null;error='';busy=false;layoutIntent++;layoutObserver?.disconnect();layoutObserver=null;
        if(!eligible(run))return;
        try{
          const value=await api('runs/'+enc(run.id)+'/model-evidence',{},2);if(!current()||version!==generation)return;
          validateIndex(value,run);catalog=value;if(value.state==='unsupported')return;
          choose();if(selectedRecord())await fetchSlice(run,()=>current()&&version===generation);
        }catch(problem){if(current()&&version===generation){catalog=null;slice=null;error=problem.message;}}
      },
      html(run){
        if(!eligible(run))return '';
        if(error&&!catalog)return `<section class="model-evidence field-evidence"><h3>Field evidence unavailable</h3><p class="error-panel" role="alert">${esc(error)}</p><p>No cached field values are shown. Refresh saved runs to retry.</p></section>`;
        if(!catalog)return '';
        if(catalog.state==='unsupported')return `<section class="field-evidence"><h3>Field evidence</h3><p class="muted">${esc(catalog.reason)}</p></section>`;
        const member=catalog.probe.members.find(item=>String(item.ordinal)===selection.member),record=selectedRecord(),maximum=record?.shape_zyx?.['zyx'.indexOf(selection.axis)]-1;
        const position=catalog.checkpoint_index.entries.findIndex(item=>item.checkpoint.sha256===selection.checkpoint),entry=catalog.checkpoint_index.entries[position],descriptor=catalog.checkpoints[position];
        return `<section class="model-evidence field-evidence" aria-labelledby="field-evidence-heading"><h3 id="field-evidence-heading">Linked field evidence</h3><p>Retained standalone validation fields. Structural and identity closure is verified; numerical or physical acceptance requires separate task evidence.</p>${indexHTML()}<form id="field-selectors"><div class="model-fields"><label>Exact checkpoint<select id="field-checkpoint">${catalog.checkpoint_index.entries.map(item=>`<option value="${esc(item.checkpoint.sha256)}" ${item.checkpoint.sha256===selection.checkpoint?'selected':''}>${esc(clock(item.clocks))}${item.selected?' · selected':''} · ${esc(item.checkpoint.sha256.slice(0,12))}</option>`).join('')}</select></label><label>Fixed validation member<select id="field-member">${catalog.probe.members.map(item=>`<option value="${item.ordinal}" ${String(item.ordinal)===selection.member?'selected':''}>${item.ordinal} · ${esc(item.frozen_reference.member_id)}</option>`).join('')}</select></label><label>Declared stage<select id="field-stage">${stages().map(stage=>`<option ${stage===selection.stage?'selected':''} value="${esc(stage)}">${esc(stage)}</option>`).join('')}</select></label><label>Declared field<select id="field-id">${records().filter(item=>item.stage===selection.stage).map(item=>`<option value="${esc(item.field_id)}" ${item.field_id===selection.field?'selected':''}>${esc(item.field_id)} · ${esc(item.units)}</option>`).join('')}</select></label><label>Orthogonal axis<select id="field-axis">${['x','y','z'].map(axis=>`<option value="${axis}" ${axis===selection.axis?'selected':''}>${axis.toUpperCase()}</option>`).join('')}</select></label><label>Slice index<input id="field-index" type="number" min="0" max="${maximum}" step="1" required value="${selection.index}"></label></div><button id="field-load" ${busy||!record?'disabled':''}>${busy?'Loading exact retained slice…':'Reload exact slice'}</button></form>${descriptor?.weights?.name?`<div class="actions"><a href="/api/workspace/runs/${enc(run.id)}/artifacts/${enc(descriptor.weights.name)}" download>Download exact retained fitted state</a>${entry.checkpoint.name?`<a href="/api/workspace/runs/${enc(run.id)}/artifacts/${enc(entry.checkpoint.name)}" download>Checkpoint descriptor</a>`:''}</div>`:''}<p class="field-status" role="status">${busy?'Loading the exact selected checkpoint, member and slice. No earlier array values are shown.':error?esc(error):''}</p>${member?`<p>Frozen input ${esc(member.frozen_reference.input)} · member ${esc(member.frozen_reference.member_id)} · validation. Input SHA256 <span class="field-hash">${esc(member.input_sha256)}</span>; target SHA256 <span class="field-hash">${esc(member.target_sha256)}</span>.</p>`:''}${sliceHTML()}<p class="footnote">Scientific test access is unsupported. No simulation frame or physical timeline is declared. Physical acceptance is not established by these plots.</p><details><summary>Retained field index, model and evidence identities</summary><pre>${esc(JSON.stringify({validation:catalog.validation,fields:catalog.fields,probe:catalog.probe,checkpoint_index:catalog.checkpoint_index,checkpoints:catalog.checkpoints,model_definition:catalog.model_definition,manifest:catalog.manifest,selected_field_metadata:slice?{grid:slice.grid,gauge_policy_sha256:slice.gauge_policy_sha256,gauge_policy:slice.gauge_policy,time_units:slice.time_units}:undefined},null,2))}</pre></details></section>`;
      },
      bind(root,run,rerender,current){
        layoutIntent++;layoutObserver?.disconnect();layoutObserver=null;
        if(!eligible(run)||catalog?.state!=='verified')return;
        draw(root);
        if(slice&&typeof ResizeObserver!=='undefined'){const layoutVersion=layoutIntent;layoutObserver=new ResizeObserver(()=>{if(current()&&layoutVersion===layoutIntent&&root.isConnected!==false)draw(root);});for(const viewport of root.querySelectorAll('.field-slice-viewport'))layoutObserver.observe(viewport);}
        const show=()=>{const focus=document.activeElement?.id;rerender();if(focus)root.querySelector('#'+CSS.escape(focus))?.focus({preventScroll:true});};
        const load=async()=>{const pending=fetchSlice(run,current);show();await pending;if(current())show();};
        for(const [id,key] of [['field-checkpoint','checkpoint'],['field-member','member'],['field-stage','stage'],['field-id','field'],['field-axis','axis'],['field-index','index']])root.querySelector('#'+id)?.addEventListener('change',event=>{
          selection[key]=key==='index'?(event.target.value.trim()===''?NaN:Number(event.target.value)):event.target.value;if(key!=='index')choose(key==='axis'||key==='field'||key==='stage');load();
        });
        root.querySelector('#field-selectors')?.addEventListener('submit',event=>{event.preventDefault();load();});
        for(const [id,key] of [['field-probe-row','row'],['field-probe-column','column']])root.querySelector('#'+id)?.addEventListener('input',event=>{
          sample[key]=event.target.value.trim()===''?NaN:Number(event.target.value);const result=root.querySelector('#field-probe-result');if(result)result.innerHTML=probeHTML();
        });
      },
    };
  };
})();

// Bounded native controls for an inert contribution's declared parameter schema.
(() => {
  if(typeof window==='undefined')return;
  const esc=value=>window.workspaceEscape(value);
  window.WorkspaceTypedParameters=function({schema,value,prefix}){
    let state=structuredClone(value),bindings=[],actions=[],count=0;
    const own=(value,key)=>value!==null&&typeof value==='object'&&Object.hasOwn(value,key);
    const at=path=>path.reduce((value,key)=>own(value,key)?value[key]:undefined,state);
    function set(path,value){if(!path.length){state=value;return;}let parent=state;for(const key of path.slice(0,-1))parent=parent[key];parent[path.at(-1)]=value;}
    function remove(path){let parent=state;for(const key of path.slice(0,-1))parent=parent[key];delete parent[path.at(-1)];}
    function blank(rule){if(rule.type==='object')return Object.fromEntries((rule.required||[]).map(key=>[key,blank(rule.properties[key])]));if(rule.type==='array')return Array.from({length:rule.minItems||0},()=>blank(rule.items));return undefined;}
    function validate(rule,value,label,depth=0){
      if(depth>8)throw Error('This configuration exceeds the native editor depth bound.');
      if(rule.enum&&!rule.enum.some(item=>item===value))throw Error('Choose '+label+'.');
      if(rule.type==='object'){
        if(!value||typeof value!=='object'||Array.isArray(value)||rule.additionalProperties!==false||!rule.properties)throw Error(label+' requires a closed object.');
        if(Object.keys(value).some(key=>!own(rule.properties,key)))throw Error(label+' contains undeclared fields.');
        for(const key of rule.required||[])if(!own(value,key))throw Error('Complete '+label+' · '+key+'.');
        for(const key of Object.keys(value))validate(rule.properties[key],value[key],label+' · '+key,depth+1);
      }else if(rule.type==='array'){
        if(!Array.isArray(value)||!Number.isInteger(rule.maxItems)||rule.maxItems>64||value.length<(rule.minItems||0)||value.length>rule.maxItems)throw Error(label+' has an invalid item count.');
        value.forEach((item,index)=>validate(rule.items,item,label+' '+(index+1),depth+1));
      }else if(rule.type==='number'||rule.type==='integer'){
        if(!Number.isFinite(value)||(rule.type==='integer'&&!Number.isSafeInteger(value))||(rule.minimum!==undefined&&value<rule.minimum)||(rule.maximum!==undefined&&value>rule.maximum))throw Error('Enter a valid '+label+'.');
      }else if(rule.type==='string'){
        if(typeof value!=='string'||value.length<(rule.minLength||0)||value.length>(rule.maxLength??4096))throw Error('Enter a valid '+label+'.');
      }else if(rule.type==='boolean'){if(typeof value!=='boolean')throw Error('Choose '+label+'.');}
      else throw Error('This parameter type is unavailable in the native editor.');
    }
    function node(rule,path,label,depth=0){
      if(depth>8||++count>256)throw Error('This configuration exceeds the native editor size bound.');
      const current=at(path),title=rule.title||label,hint=rule.description?`<small>${esc(rule.description)}</small>`:'';
      if(rule.type==='object'){
        if(rule.additionalProperties!==false||!rule.properties||Object.keys(rule.properties).length>64)throw Error('Only bounded closed parameter objects are supported.');
        return `<fieldset class="author-parameters"><legend>${esc(title)}</legend>${hint}${Object.entries(rule.properties).map(([key,child])=>{
          if(!/^[a-z][a-z0-9_.-]{0,63}$/.test(key))throw Error('Unsupported declared parameter name.');
          const childPath=[...path,key],required=(rule.required||[]).includes(key);
          if(required)return node(child,childPath,key.replaceAll('_',' '),depth+1);
          const id=prefix+'-optional-'+bindings.length;bindings.push({id,kind:'optional',path:childPath,rule:child});
          return `<div><label class="check-row"><input id="${id}" type="checkbox" ${own(current,key)?'checked':''}>Include ${esc(child.title||key)}</label>${own(current,key)?node(child,childPath,key.replaceAll('_',' '),depth+1):''}</div>`;
        }).join('')}</fieldset>`;
      }
      if(rule.type==='array'){
        if(!Number.isInteger(rule.maxItems)||rule.maxItems>64||rule.maxItems<0||!rule.items)throw Error('Only explicitly bounded parameter arrays are supported.');
        const items=Array.isArray(current)?current:[],group=prefix+'-array-'+actions.length;
        const add=group+'-add';actions.push({id:add,run:()=>set(path,[...at(path),blank(rule.items)])});
        return `<fieldset class="author-parameters"><legend>${esc(title)}</legend>${hint}${items.map((item,index)=>{
          const id=group+'-remove-'+index;actions.push({id,run:()=>set(path,at(path).filter((value,i)=>i!==index))});
          return `<div class="author-array-item">${node(rule.items,[...path,index],title+' '+(index+1),depth+1)}<button id="${id}" type="button" ${items.length<=(rule.minItems||0)?'disabled':''}>Remove ${esc(title)} ${index+1}</button></div>`;
        }).join('')}<button id="${add}" type="button" ${items.length>=rule.maxItems?'disabled':''}>Add ${esc(title)} item</button><small>${rule.minItems||0}–${rule.maxItems} items.</small></fieldset>`;
      }
      const id=prefix+'-value-'+bindings.length;bindings.push({id,kind:'value',path,rule,label:title});
      let control;
      if(rule.enum){control=`<select id="${id}" required><option value="">Choose ${esc(title)}</option>${rule.enum.map((item,index)=>`<option value="${index}" ${item===current?'selected':''}>${esc(item)}</option>`).join('')}</select>`;}
      else if(rule.type==='boolean')control=`<input id="${id}" type="checkbox" ${current===true?'checked':''}>`;
      else if(['integer','number','string'].includes(rule.type))control=`<input id="${id}" type="${rule.type==='string'?'text':'number'}" required value="${esc(current??'')}" ${rule.minimum!==undefined?`min="${esc(rule.minimum)}"`:''} ${rule.maximum!==undefined?`max="${esc(rule.maximum)}"`:''} ${rule.type==='string'?`minlength="${rule.minLength||0}" maxlength="${rule.maxLength??4096}"`:`step="${rule.type==='integer'?'1':'any'}"`}>`;
      else throw Error('This declared parameter type is unavailable in the native editor.');
      return `<label class="${rule.type==='boolean'?'check-row':''}">${esc(title)}${control}${hint}</label>`;
    }
    function read(root,check=true){
      if(root)for(const binding of bindings){
        if(binding.kind!=='value')continue;
        const input=root.querySelector('#'+binding.id);if(!input)throw Error('Configuration control is unavailable.');
        const raw=input.value;let value;
        if(binding.rule.enum){if(raw===''&&check)throw Error('Choose '+binding.label+'.');value=raw===''?undefined:binding.rule.enum[Number(raw)];}
        else if(binding.rule.type==='boolean')value=input.checked;
        else if(binding.rule.type==='string')value=raw;
        else value=raw.trim()===''?undefined:Number(raw);
        set(binding.path,value);
      }
      if(check)validate(schema,state,'configuration');return structuredClone(state);
    }
    return {
      html(label){bindings=[];actions=[];count=0;return node(schema,[],label);},
      read,
      bind(root,rerender,onError){
        for(const action of actions)root.querySelector('#'+action.id)?.addEventListener('click',()=>{try{read(root,false);action.run();rerender();}catch(error){onError(error.message);}});
        for(const binding of bindings.filter(item=>item.kind==='optional'))root.querySelector('#'+binding.id)?.addEventListener('change',event=>{
          try{read(root,false);if(event.target.checked)set(binding.path,blank(binding.rule));else remove(binding.path);rerender();}catch(error){onError(error.message);}
        });
      },
    };
  };
})();

// Human preparation of the explicitly bound model recipe variant. No project code is loaded here.
(() => {
  if(typeof window==='undefined')return;
  const pins=/* AUTHOR_CONTRACTS_START */ {
    "recipes.inspect/2":"be0cfb596b3ae741e2903be57413684bac28e9fa3c59987086fde49e514284ea",
    "recipes.inspect/3":"5b5c6a4eefe84df8da4c31d779a468c7bdbacf4296c294076010fbbaed167458",
    "recipes.inspect/4":"0080ae0e39bf758b9c96c3208ef1614a9335f257731cfde935a23d8b486dedb1",
    "project_snapshots.get/2":"770e999697f069af13e9cf0d48daaf930ee26db4d7415169edecb414f68bdd01",
    "models.create":"693d1514f44e92bb6c6635427db822acfc079a6e438d5d721630087157d1b8d5",
    "models.publish":"bb84c1fd72b3617135a8246353db797bba270430121fbae6f9d46cdbfdd26235",
    "graphs.create_external":"219f3c28bcb73e6d5445bdbd9b97e563bde3bd90487796b4680f36e02d338ffa",
    "graphs.preflight_external":"81515fd903aefd3ab717a8a9b7cfb937726a312b1fa4808bec8a06ae03094125",
    "studies.create":"8c4b35bbd1c2b7c6825787b40e40b2b3d22f58118ccaf1ef5f0d9bc12edb38f1",
    "studies.prepare_trial":"516f89e4a03cafee9d50ac3910d1906fb34d51d3b21e8271a4be45075ea3778a",
    "recipes.material":"d3ded92c05a1e3d7d88392355e4c61b480b63e55cf763774e2823462774c2870",
    "studies.get":"12080dea124eb9e763ec495e070211b60a219c47cab9488218383a7d3919533d",
    "studies.continue":"44237f86e49135203613b40a7bf6fe0960581ed7c3f128150b9576a07b491008",
    "studies.approve":"5ed2d9db58231f14c164a76f1c64157260902d2cd86f5e86433f29fc00f4f408",
    "studies.admit":"9c80abdfc50d56de88ada0141ba6c3b503cc07a395b0ceb930fa29169bd182ed"
  } /* AUTHOR_CONTRACTS_END */;
  window.WorkspaceExtensionAuthorContracts=pins;
  const esc=value=>window.workspaceEscape(value),enc=encodeURIComponent,copy=value=>structuredClone(value);
  const exactRef=(left,right)=>!!left&&!!right&&['kind','catalog_id','id','sha256'].every(key=>left[key]===right[key]);
  const rejected=error=>[400,404,409].includes(error.status)&&['invalid','stale','unsupported','unavailable'].includes(error.code);
  const uncertain=error=>!error.status||error.status>=500||['commit_outcome_unknown','commit_unknown','outcome_unknown','unknown'].includes(error.code);
  const identity=()=>window.TuldokAuth?.identity(),owner=()=>identity()?.kind==='owner';
  const numericSources=new WeakMap();
  function exactJSON(raw){
    if(typeof JSON.rawJSON!=='function')throw Error('This browser does not support exact inspected policy transport. Use a current browser before preparing a trial.');
    return JSON.parse(raw,function(key,value,context){
      if(typeof value==='number'){
        if(typeof context?.source!=='string')throw Error('This browser cannot retain inspected numeric policy identity.');
        let leaves=numericSources.get(this);if(!leaves){leaves=new Map();numericSources.set(this,leaves);}
        leaves.set(key,{value,source:context.source});
      }
      return value;
    });
  }
  function exactBody(value){
    return JSON.stringify(value,function(key,item){
      const recorded=numericSources.get(this)?.get(key);
      return typeof item==='number'&&recorded&&Object.is(item,recorded.value)?JSON.rawJSON(recorded.source):item;
    });
  }
  function configuredSpecification(policy,configuration){
    const value={...policy,configuration:copy(configuration)},leaves=numericSources.get(policy);
    if(leaves)numericSources.set(value,leaves);
    return value;
  }
  async function request(operation,route,body,version=1){
    const pin=pins[version===1?operation:operation+'/'+version];if(!pin)throw Error('This preparation operation is unavailable.');
    const response=await (window.TuldokAuth?.fetch||fetch)('/api/workspace/'+route,{headers:{'Content-Type':'application/json','Tuldok-Operation-Contract':operation+'/'+version+'/'+pin},...(body===undefined?{}:{method:'POST',body:exactBody(body)})});
    const value=exactJSON(await response.text());if(!response.ok){const error=Error(value.error||'Bound recipe operation unavailable.');error.status=response.status;error.code=value.code;throw error;}return value;
  }
  window.WorkspaceExtensionModelAuthor=function({announce,onRun,send=request}){
    let generation=0,busy=null,project=null,reference=null,inspected=null,roles=null,job=null,foreign=false,key='',status='',failed=false,reviewed=false,modelEditor=null,trainerEditor=null,draft=null;
    const dialog=document.createElement('dialog');dialog.id='extension-model-dialog';dialog.setAttribute('aria-labelledby','extension-model-title');document.body.append(dialog);
    const save=value=>{history.replaceState({...history.state,extensionModelTrials:{...history.state?.extensionModelTrials,[value.key]:value}},'');};
    const currentScope=()=>{const epoch=generation,credential=identity()?.credential_id;return ()=>epoch===generation&&credential===identity()?.credential_id&&dialog.open;};
    const note=(text,error=false)=>{status=text;failed=error;if(dialog.open)render();announce(text,error);};
    function cancel(){generation++;if(dialog.open)dialog.close();if(busy&&!job?.run)announce('An exact preparation or admission may still finish. Reopen this recipe with the original owner to inspect its saved request.');}
    window.addEventListener('tuldok-session',()=>{cancel();job=null;inspected=null;roles=null;reviewed=false;});
    dialog.addEventListener('cancel',cancel);
    function binding(value){
      const definition=value.definition,bound=value.extension_binding,selection=definition?.extension_selection?.selections;
      if(project.schema_version!==2||definition?.schema_version!==3||definition?.format!=='external_model_evidence_recipe_v2'||bound?.format!=='tuldok_extension_binding_v1'||bound.project?.id!==project.id||bound.project.manifest_sha256!==project.manifest_sha256||!selection||!value.model_task||!value.selection_policy)throw Error('Only the explicitly bound model recipe is supported here. This project recipe remains inspection-only.');
      const result={};
      for(const role of ['task','model','trainer','evaluator','view']){
        const selected=selection[role],matches=bound.contributions.filter(item=>item.kind===role&&['id','version','sha256'].every(name=>item[name]===selected?.[name]));
        if(matches.length!==1||!bound.selections.some(item=>['id','version','sha256'].every(name=>item[name]===selected?.[name])))throw Error('The exact '+role+' contribution is unavailable.');
        result[role]=matches[0];
      }
      if(!definition.model_evidence?.model_specification?.configuration||typeof definition.model_evidence.model_specification.configuration!=='object'||Array.isArray(definition.model_evidence.model_specification.configuration))throw Error('The bound model has no explicit configuration object.');
      return result;
    }
    function trainerSchema(){
      const properties={};
      for(const [name,rule] of Object.entries(inspected.parameter_definitions)){
        const declared=roles.trainer.definition.parameters?.properties?.[name]||{};
        const value={...declared,type:rule.type,title:declared.title||name.replaceAll('_',' ')};
        if(rule.min!==undefined)value.minimum=Math.max(rule.min,value.minimum??-Infinity);
        if(rule.max!==undefined)value.maximum=Math.min(rule.max,value.maximum??Infinity);
        if(rule.max_length!==undefined)value.maxLength=Math.min(rule.max_length,value.maxLength??4096);
        if(rule.enum)value.enum=rule.enum.filter(item=>!declared.enum||declared.enum.includes(item));
        properties[name]=value;
      }
      return {type:'object',properties,required:Object.keys(properties),additionalProperties:false};
    }
    function captureDraft(){
      if(job||!draft)return;
      const name=dialog.querySelector('#extension-model-name');if(!name)return;draft.name=name.value;
      for(const node of dialog.querySelectorAll('[data-author-input]'))draft.inputs[node.dataset.authorInput]=node.value;
      for(const id of ['attempts','wall','retained','staging'])draft.budget[id]=dialog.querySelector('#extension-budget-'+id).value;
    }
    function providerDeclaration(provider){
      const runtime=provider?.runtime,resources=provider?.resources,definition=inspected?.definition;
      if(!Array.isArray(provider?.effects)||!['captured_cpu_python_v1','managed_torch_python_v1'].includes(runtime?.profile)||runtime.profile!==inspected?.runtime||!resources)return null;
      const snapshot=definition?.runtime_snapshot_sha256;
      if(!/^[a-f0-9]{64}$/.test(snapshot||'')||(runtime.snapshot_sha256!==undefined&&runtime.snapshot_sha256!==snapshot))return null;
      if(!['wall_seconds','source_bytes','output_bytes'].every(key=>Number.isSafeInteger(resources[key])&&resources[key]>0)||resources.wall_seconds<definition.resources.wall_seconds||resources.output_bytes<definition.resources.max_output_bytes)return null;
      return provider;
    }
    function hasReview(j){return Object.values(roles||{}).every(item=>providerDeclaration(item.provider))&& j?.preflight?.valid===true&&typeof j.preflight.material?.permissions?.filesystem==='string'&&typeof j.preflight.material.permissions.network==='string'&&!!j?.composition&&exactRef(j.composition.ref,j.trial?.material)&&exactRef(j.composition.material?.model,j.material?.ref)&&j.composition.material.recipe_id===j.graph?.id&&j.composition.material.recipe_revision===j.graph?.revision&&!!j.composition.material.resource_envelope;}
    function makeEditors(){
      const config=job?.configuration||inspected.definition.model_evidence.model_specification.configuration;
      modelEditor=roles.model.definition.parameters?window.WorkspaceTypedParameters({schema:roles.model.definition.parameters,value:config,prefix:'extension-model'}):null;
      if(!modelEditor&&Object.keys(config).length)throw Error('This model does not declare editable configuration parameters.');
      trainerEditor=window.WorkspaceTypedParameters({schema:trainerSchema(),value:job?.parameters||Object.fromEntries(Object.entries(inspected.parameter_definitions).map(([name,rule])=>[name,rule.default])),prefix:'extension-trainer'});
    }
    function inputChoices(name){
      const policy=inspected.definition.model_evidence,required=new Set([...policy.fit_members,...policy.probe.candidates.map(item=>item.frozen_reference)].filter(item=>item.input===name).map(item=>item.sha256));
      return project.data.filter(item=>item.status==='available'&&item.integrity!=='mismatch'&&/^[a-f0-9]{64}$/.test(item.observed_sha256||'')&&(!required.size||required.has(item.observed_sha256))&&item.bytes<=inspected.inputs[name].max_bytes);
    }
    function contributionsHTML(){
      return `<ul class="author-contributions">${Object.entries(roles).map(([role,item])=>`<li><strong>${esc(role)} · ${esc(item.definition.label)}</strong><p>${esc(item.id)} @ ${esc(item.version)} · ${esc(item.provider?.id||item.provider?.reference_id)}</p><small class="field-hash">${esc(item.sha256)}</small></li>`).join('')}</ul>`;
    }
    function providersHTML(){
      const providers=[...new Map(Object.values(roles).map(item=>[item.provider.reference_id,item.provider])).values()];
      return `<section><h3>Provider declarations</h3><p>These are hash-bound provider declarations. Effective process permissions are shown separately below.</p><ul>${providers.map(provider=>{
        const item=providerDeclaration(provider);
        return `<li><strong>${esc(provider.id)} @ ${esc(provider.version)}</strong>${item?`<p>Declared effects: ${esc(item.effects.join(', ')||'none')}. Declared runtime: ${esc(item.runtime.profile)} · <span class="field-hash">${esc(item.runtime.snapshot_sha256??'Snapshot hash not declared')}</span></p><p>Declared limits: ${item.resources.wall_seconds} wall seconds; ${item.resources.source_bytes} source bytes; ${item.resources.output_bytes} output bytes.</p>`:'<p>Declared effects, runtime and limits are unavailable in this bound inspection. Reinspect the recipe before approval.</p>'}</li>`;
      }).join('')}</ul></section>`;
    }
    function reviewHTML(){
      if(!hasReview(job))return '<p class="callout">The exact trial composition must be loaded before approval.</p><button id="extension-review-reconcile" type="button" '+(busy||!owner()?'disabled':'')+'>Load exact trial review</button>';
      const material=job.composition.material,policy=inspected.definition.model_evidence;
      return `<section class="author-review">${providersHTML()}<h3 id="extension-review-heading" tabindex="-1">Review this exact finite trial</h3><p>Trial ${esc(job.trial.id)} · composition SHA256 <span class="field-hash">${esc(job.trial.material.sha256)}</span></p><p>Model material ${esc(job.material.ref.sha256)} · recipe r${esc(job.graph.revision)}. The Study retains a diagnostic last-checkpoint policy; no numerical or physical acceptance threshold is qualified.</p><dl><div><dt>Runtime</dt><dd>${esc(inspected.runtime)} · <span class="field-hash">${esc(inspected.definition.runtime_snapshot_sha256||material?.runtime?.sha256)}</span></dd></div><div><dt>Finite requested budget</dt><dd>${job.limits.attempt_slots} attempts · ${job.limits.admitted_wall_seconds} wall seconds · ${job.limits.retained_bytes} retained bytes · ${job.limits.peak_staging_bytes} staging bytes</dd></div><div><dt>Effective process permissions</dt><dd>Filesystem: ${esc(job.preflight?.material?.permissions?.filesystem)} · network: ${esc(job.preflight?.material?.permissions?.network)}</dd></div><div><dt>Exact input membership</dt><dd>${policy.fit_members.length} training members; ${policy.probe.candidates.length} fixed validation members. Test and a physical timeline are unsupported.</dd></div></dl><p class="callout">Trusted local code runs with the service user’s filesystem and network access. This is not a sandbox. Limits do not guarantee aggregate resource isolation. Approval authorizes this exact material for the current owner. Process completion and retained diagnostics do not establish scientific correctness.</p><details><summary>Captured sources, data and declared limits</summary><ul>${inspected.extension_binding.inventory.map(item=>`<li>${esc(item.path)} · ${item.bytes} bytes · <span class="field-hash">${esc(item.sha256)}</span></li>`).join('')}</ul><pre>${esc(JSON.stringify({inputs:job.inputs,captured_sources:job.preflight?.material?.captures,resources:inspected.definition.resources,fit_members:policy.fit_members,validation_members:policy.probe.candidates,field_targets:policy.field_targets,resource_envelope:material?.resource_envelope},null,2))}</pre></details>${job.run?`<p>Admitted Run ${esc(job.run.id)}</p><button id="extension-open-run" type="button">Inspect admitted Run →</button>`:job.approval?`<p>Exact one-use approval ${esc(job.approval.id)}</p><button id="extension-admit" class="primary" type="button" ${busy||!owner()?'disabled':''}>${job.admission?'Reconcile exact Study admission':'Start approved finite trial'}</button>`:`<label class="check-row"><input id="extension-reviewed" type="checkbox" ${reviewed?'checked':''} ${busy||!owner()||job.approvalUnknown?'disabled':''}>I reviewed this exact model, input membership, runtime, sources, permissions and finite budget.</label><button id="extension-approve" type="button" ${busy||!owner()||!reviewed||job.approvalUnknown?'disabled':''}>Approve this exact Study trial</button>${job.approvalUnknown?'<p class="error-panel">Approval acknowledgement is unresolved. Inspect execution grants before issuing another approval; this interface will not create a replacement grant.</p>':''}`}</section>`;
    }
    function render(){
      if(!dialog.open)return;
      const focus=dialog.contains(document.activeElement)?document.activeElement.id:null;
      let form='';
      if(inspected&&roles){
        try{
          form=`${contributionsHTML()}<p>Project snapshot ${esc(inspected.extension_binding.project.manifest_sha256)}. Opening and inspection run no contribution code.</p><form id="extension-model-form"><fieldset ${busy||job||foreign||!owner()?'disabled':''}><legend>Model and training configuration</legend><label>Name<input id="extension-model-name" maxlength="120" required value="${esc(job?.name??draft.name)}"></label>${modelEditor?modelEditor.html('Model configuration'):'<p>No editable model configuration parameters are declared.</p>'}${trainerEditor.html('Trainer controls')}<fieldset class="author-parameters"><legend>Exact authored project inputs</legend>${Object.keys(inspected.inputs).map(name=>`<label>${esc(name)}<select data-author-input="${esc(name)}" required><option value="">Choose a matching captured input</option>${inputChoices(name).map(item=>`<option value="${esc(item.id)}" ${(job?.inputs?.[name]?.reference_id??draft.inputs[name])===item.id?'selected':''}>${esc(item.label)} · ${esc(item.observed_sha256.slice(0,12))}</option>`).join('')}</select></label>`).join('')}</fieldset><fieldset class="author-parameters"><legend>Finite Study budget</legend><div class="model-fields">${[['attempts','Attempt slots',3],['wall','Admitted wall seconds',10800],['retained','Retained MiB',1024],['staging','Peak staging MiB',2048]].map(([id,label,value])=>`<label>${label}<input id="extension-budget-${id}" type="number" min="1" step="1" max="${id==='retained'||id==='staging'?Math.floor(Number.MAX_SAFE_INTEGER/1048576):Number.MAX_SAFE_INTEGER}" required value="${job?(id==='attempts'?job.limits.attempt_slots:id==='wall'?job.limits.admitted_wall_seconds:id==='retained'?job.limits.retained_bytes/1048576:job.limits.peak_staging_bytes/1048576):draft.budget[id]}"></label>`).join('')}</div></fieldset></fieldset>${foreign?'<p class="error-panel">Another actor has unresolved preparation for this recipe. Reconcile it in that actor’s session before creating a replacement.</p>':!owner()?'<p>The current owner session is required to prepare and approve a local model trial.</p>':!job?.trial?`<button id="extension-prepare" class="primary" ${busy||job?.creationUnknown?'disabled':''}>${job?'Reconcile exact preparation':'Prepare immutable finite trial'}</button>`:''}</form><details><summary>Declared ordered stages</summary><ol>${(roles.trainer.definition.stages||roles.task.definition.stages||[]).map(stage=>`<li>${esc(stage.id)} @ ${esc(stage.version)} · ${esc(stage.clock||'declared stage')}</li>`).join('')}</ol><p>The declared stages and native field view are fixed by this recipe.</p></details>${job?.creationUnknown?`<p class="error-panel">${esc(job.creationUnknown)} creation acknowledgement is unresolved. Inspect saved ${esc(job.creationUnknown)} records before another creation; the original preparation remains retained.</p>`:''}${job?.trial?reviewHTML():''}`;
        }catch(error){form=`<p class="error-panel">${esc(error.message)} No configuration is submitted.</p>`;}
      }
      dialog.innerHTML=`<div class="panel-title"><h2 id="extension-model-title">Prepare a bound model trial</h2><button id="extension-model-close" type="button">Close</button></div><p>${esc(reference?.label)} · ${esc(project?.name)}</p><p class="author-status ${failed?'error-panel':''}" role="status">${esc(status)}</p>${form}`;
      dialog.querySelector('#extension-model-close').onclick=cancel;
      const rerender=()=>{captureDraft();render();};modelEditor?.bind(dialog,rerender,text=>note(text,true));trainerEditor?.bind(dialog,rerender,text=>note(text,true));
      dialog.querySelector('#extension-model-form')?.addEventListener('submit',event=>{event.preventDefault();return perform(prepare);});
      dialog.querySelector('#extension-reviewed')?.addEventListener('change',event=>{reviewed=event.target.checked;const button=dialog.querySelector('#extension-approve');if(button)button.disabled=!reviewed||!!busy||!owner();});
      dialog.querySelector('#extension-review-reconcile')?.addEventListener('click',()=>perform(loadReview));
      dialog.querySelector('#extension-approve')?.addEventListener('click',()=>perform(approve));
      dialog.querySelector('#extension-admit')?.addEventListener('click',()=>perform(admit));
      dialog.querySelector('#extension-open-run')?.addEventListener('click',()=>onRun(job.run.id));
      if(focus)dialog.querySelector('#'+CSS.escape(focus))?.focus({preventScroll:true});
    }
    async function perform(action){
      if(busy||!owner()||foreign)return;
      captureDraft();const valid=currentScope(),token={};busy=token;status='Checking exact immutable material…';failed=false;
      try{await action(valid);}catch(error){if(valid()){status=error.message;failed=true;}}
      finally{if(busy===token){busy=null;if(valid()){render();if(job?.trial)dialog.querySelector('#extension-review-heading')?.focus({preventScroll:true});}}}
    }
    function checked(valid){if(!valid())throw Error('Selection or session changed. Reopen this recipe to inspect the retained operation.');}
    async function create(j,field,operation,route,body,valid){
      if(j[field])return;
      if(j.creationUnknown)throw Error('An earlier '+j.creationUnknown+' creation is unresolved. Inspect saved records before another creation.');
      try{const value=await send(operation,route,body);j[field]=value;save(j);checked(valid);}
      catch(error){if(!j[field]&&uncertain(error)){j.creationUnknown=field;save(j);}throw error;}
    }
    async function prepare(valid){
      checked(valid);
      let j=job;
      if(!j){
        const configuration=modelEditor?modelEditor.read(dialog):{},parameters=trainerEditor.read(dialog),inputs={};
        for(const select of dialog.querySelectorAll('[data-author-input]')){
          const name=select.dataset.authorInput,item=inputChoices(name).find(item=>item.id===select.value);if(!item)throw Error('Choose the exact captured input for '+name+'.');inputs[name]={reference_id:item.id,expected_sha256:item.observed_sha256};
        }
        const number=id=>Number(dialog.querySelector('#extension-budget-'+id).value),limits={attempt_slots:number('attempts'),admitted_wall_seconds:number('wall'),retained_bytes:number('retained')*1048576,peak_staging_bytes:number('staging')*1048576};
        if(Object.values(limits).some(value=>!Number.isSafeInteger(value)||value<1))throw Error('Use positive finite integer budget values.');
        if(!draft.name.trim()||draft.name.length>120)throw Error('Enter a model trial name of at most 120 characters.');
        j={key,actor:identity().actor_id,name:draft.name,configuration,parameters,inputs,limits};job=j;save(j);
      }
      if(j.actor!==identity()?.actor_id)throw Error('The preparing owner must reconcile this trial.');
      render();checked(valid);
      const policy=inspected.definition.model_evidence,specification=configuredSpecification(policy.model_specification,j.configuration);
      const source_selector={project_id:project.id,recipe_id:reference.id,expected_sha256:reference.observed_sha256};
      await create(j,'model','models.create','models',{name:j.name,task:inspected.model_task,kind:'captured_source',specification,source_selector,preprocessing_policy:policy.preprocessing_policy,output_policy:policy.output_policy},valid);
      if(!j.material){j.material=await send('models.publish','models/'+enc(j.model.id)+'/publish',{revision:j.model.revision,reconcile_capture:true});save(j);checked(valid);}
      await create(j,'graph','graphs.create_external','graphs/external',{name:j.name,...source_selector,inputs:j.inputs,parameters:j.parameters},valid);
      if(!j.preflight){j.preflight=await send('graphs.preflight_external','graphs/'+enc(j.graph.id)+'/preflight-external',{revision:j.graph.revision});save(j);checked(valid);}
      if(j.preflight.valid!==true)throw Error('The exact bound graph did not pass preflight.');
      await create(j,'study','studies.create','studies',{name:j.name,limits:j.limits,policy:inspected.selection_policy},valid);
      if(!j.preparation){const state=await send('studies.get','studies/'+enc(j.study.id));checked(valid);j.study=state.study;j.preparation={request_key:crypto.randomUUID(),revision:j.study.revision,graph_id:j.graph.id,graph_revision:j.graph.revision,model:j.material.ref,replicate:0,reconcile_capture:true};save(j);}
      if(!j.trial){try{j.trial=await send('studies.prepare_trial','studies/'+enc(j.study.id)+'/prepare-trial',j.preparation);save(j);checked(valid);}
        catch(error){if(!j.preparationUnknown&&rejected(error)){j.preparation=null;save(j);}else if(uncertain(error)){j.preparationUnknown=true;save(j);}throw error;}}
      await loadReview(valid);status='Immutable trial prepared. Review its full material before a separate exact approval and explicit admission.';
    }
    async function loadReview(valid){const j=job;checked(valid);render();if(j.actor!==identity()?.actor_id)throw Error('The preparing owner must review this trial.');if(!Object.values(roles).every(item=>providerDeclaration(item.provider)))throw Error('Reinspect the recipe to review exact provider effects, runtime and limits before approval.');const result=await send('recipes.material','recipe-material',{ref:j.trial.material});j.composition=result;save(j);checked(valid);if(!hasReview(j))throw Error('The returned composition does not match this exact trial and Model.');}
    async function approve(valid){
      const j=job;if(!reviewed||!hasReview(j)||j.actor!==identity()?.actor_id||j.approvalUnknown)throw Error('Review the prepared exact trial before approval.');checked(valid);render();
      try{j.approval=await send('studies.approve','studies/'+enc(j.study.id)+'/approve',{trial_id:j.trial.id,expected_material_sha256:j.trial.material.sha256,consumer_actor_id:identity().actor_id});save(j);checked(valid);status='One-use full-composition approval retained. Start this finite Study trial explicitly.';}
      catch(error){if(!j.approval&&uncertain(error)){j.approvalUnknown=true;save(j);}throw error;}
    }
    async function admit(valid){
      const j=job;checked(valid);render();if(!hasReview(j)||!j?.approval||j.actor!==identity()?.actor_id)throw Error('The preparing owner and exact approval are required.');
      if(!j.admission){let state=await send('studies.get','studies/'+enc(j.study.id));checked(valid);
        if(!state.study.open){if(!j.continuation){j.continuation={request_key:crypto.randomUUID(),revision:state.study.revision,admission_epoch:state.study.admission_epoch};save(j);}try{await send('studies.continue','studies/'+enc(j.study.id)+'/continue',j.continuation);}catch(error){if(!j.continuationUnknown&&rejected(error)){j.continuation=null;save(j);}else if(uncertain(error)){j.continuationUnknown=true;save(j);}throw error;}checked(valid);state=await send('studies.get','studies/'+enc(j.study.id));checked(valid);}
        j.admission={request_key:crypto.randomUUID(),revision:state.study.revision,admission_epoch:state.study.admission_epoch,trial_id:j.trial.id,approval_id:j.approval.id};save(j);
      }
      let result;try{result=await send('studies.admit','studies/'+enc(j.study.id)+'/admit',j.admission);}
      catch(error){if(!j.admissionUnknown&&rejected(error)){j.admission=null;j.continuation=null;save(j);}else if(uncertain(error)){j.admissionUnknown=true;save(j);}throw error;}
      j.run=result.run;j.admission=null;save(j);checked(valid);status='Durable Study attempt admitted.';await onRun(result.run.id);
    }
    return {cancel,observeProject(detail){
      if(!dialog.open||!project||!reference)return;
      const current=detail.recipes.find(item=>item.id===reference.id);
      if(detail.id!==project.id||detail.manifest_sha256!==project.manifest_sha256||detail.manifest_status!=='unchanged'||current?.observed_sha256!==reference.observed_sha256||current?.status!=='available'||current.integrity==='mismatch'){
        const pending=!!busy&&!job?.run;cancel();
        if(!pending)announce('The selected project or recipe identity changed. Reinspect the recipe before preparing a trial.',true);
      }
    },async open(detail,item){
      if(busy){announce('Finish or reconcile the current preparation before opening another recipe.');return;}
      const validEpoch=++generation;project=copy(detail);reference=copy(item);key=project.id+':'+reference.id+':'+reference.observed_sha256;inspected=null;roles=null;reviewed=false;modelEditor=null;trainerEditor=null;draft=null;
      const saved=history.state?.extensionModelTrials?.[key];foreign=!!(saved&&saved.actor!==identity()?.actor_id&&!saved.run);job=saved?.actor===identity()?.actor_id?{...saved,key}:null;
      status='Inspecting the exact bound contributions. No project code is executed.';failed=false;dialog.showModal();render();const credential=identity()?.credential_id;
      try{const value=await send('recipes.inspect','projects/'+enc(project.id)+'/recipes/'+enc(reference.id)+'?expected_sha256='+enc(reference.observed_sha256),undefined,4);if(validEpoch!==generation||credential!==identity()?.credential_id||!dialog.open)return;roles=binding(value);inspected=value;draft={name:value.definition.name,inputs:{},budget:{attempts:3,wall:10800,retained:1024,staging:2048}};makeEditors();status='Configure the declared model separately from trainer controls. Preparation does not execute a Run.';render();dialog.querySelector('#extension-model-name')?.focus();}
      catch(error){if(validEpoch===generation&&credential===identity()?.credential_id&&dialog.open){status=error.message;failed=true;render();}}
    }};
  };
})();
