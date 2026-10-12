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
        "Bounded PCM16 WAV import, playback, timed human review and frozen export in the current catalog. One reviewed labelled interval per record can freeze an audio classification release and edit a real graph. Audio execution and ASR are unavailable in this checkpoint.",
      gate: "M4 Data qualified; audio execution qualification pending; ASR unavailable",
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
