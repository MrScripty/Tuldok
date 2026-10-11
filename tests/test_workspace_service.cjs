"use strict";
const assert = require("node:assert/strict"),
  fs = require("node:fs"),
  path = require("node:path");
const S = require("../static/workspace-service.js"),
  fixture = JSON.parse(
    fs.readFileSync(path.join(__dirname, "../static/workspace-fixtures.json")),
  ),
  image = fixture.records.find((r) => r.kind === "image");
const invalid = JSON.parse(
  fs.readFileSync(path.join(__dirname, "fixtures/workspaces/invalid.json")),
);
function memory() {
  const data = new Map();
  return {
    getItem: (k) => data.get(k) ?? null,
    setItem: (k, v) => data.set(k, v),
    removeItem: (k) => data.delete(k),
  };
}
for (const record of fixture.records)
  assert.equal(S.validateRecord(record), null, record.kind);
for (const row of invalid) {
  const record = structuredClone(
    fixture.records.find((r) => r.id === row.record_id),
  );
  record.representation[row.field] = row.value;
  assert.equal(S.validateRecord(record), row.expected);
}
for (const record of fixture.records) {
  assert.equal(
    S.validateRecord({ ...record, schema: "future_v99" }),
    "schema_version",
  );
}
assert.equal(
  S.validateRecord({ ...image, representation: { width: 128, height: 128 } }),
  "image_class",
);
const sequence = structuredClone(
  fixture.records.find((r) => r.kind === "sequence"),
);
sequence.representation.positions = ["bad", null, []];
assert.equal(S.validateRecord(sequence), "sequence_entities");
const storage = memory(),
  store = S.createStore(storage, image),
  graph = S.defaultGraph();
assert.equal(S.validateGraph(graph).kind, "fixture");
const wrong = structuredClone(graph);
wrong.edges[0].to = "node-3";
assert.equal(S.validateGraph(wrong).kind, "invalid");
const cycle = structuredClone(graph);
cycle.edges.push({ from: "node-5", to: "node-1" });
assert.match(S.validateGraph(cycle).message, /Cycles/);
const missing = structuredClone(graph);
missing.edges.pop();
assert.match(S.validateGraph(missing).message, /connect exactly one/);
const unavailable = structuredClone(graph);
unavailable.nodes.push({
  id: "node-audio",
  definition: "audio",
  version: 1,
  parameters: {},
});
assert.match(S.validateGraph(unavailable).message, /Unavailable/);
const badParameters = structuredClone(graph);
badParameters.nodes[2].parameters.epochs = 11;
assert.equal(S.validateGraph(badParameters).kind, "invalid");
assert.equal(store.createRun(graph, "completed", 0).kind, "invalid");
assert.equal(store.read().value.runs.length, 0);
assert.equal(store.saveGraph(graph).kind, "fixture");
assert.equal(store.saveDraft(image.id, "triangle").kind, "fixture");
const run = store.createRun(graph, "completed", graph.revision).value;
assert.equal(run.prediction.target, "square");
assert.equal(run.prediction.annotation_revision, 1);
assert.equal(run.prediction.content_hash, image.content_hash);
graph.nodes[2].parameters.epochs = 8;
assert.equal(store.read().value.runs[0].graph.nodes[2].parameters.epochs, 2);
const reopened = S.createStore(storage, image);
assert.equal(reopened.read().value.drafts[image.id].label, "triangle");
assert.equal(reopened.read().value.runs[0].prediction.target, "square");
assert.equal(
  reopened.createRun(S.defaultGraph(), "unknown", 1).value.state,
  "unknown",
);
assert.equal(reopened.cancelRun(run.id).kind, "invalid");
const running = reopened.createRun(S.defaultGraph(), "running", 1).value;
assert.equal(reopened.cancelRun(running.id).kind, "fixture");
assert.equal(reopened.cancelRun(running.id).kind, "invalid");
assert.equal(
  store.saveGraph(graph).kind,
  "invalid",
  "stale tab cannot overwrite runs from other tab",
);
const malformed = JSON.parse(storage.getItem(S.STORE_KEY));
for (const mutate of [
  (value) => (value.runs[0].graph.edges = []),
  (value) => (value.runs[0].id = 'malformed"selector'),
  (value) => value.runs.push(structuredClone(value.runs[0])),
  (value) => (value.runs[0].prediction.annotation_revision = -1),
  (value) => (value.runs[0].graph.nodes[0].parameters = []),
]) {
  const copy = structuredClone(malformed);
  mutate(copy);
  storage.setItem(S.STORE_KEY, JSON.stringify(copy));
  assert.equal(S.createStore(storage, image).read().kind, "invalid");
}
malformed.runs[0].prediction.split = "test";
storage.setItem(S.STORE_KEY, JSON.stringify(malformed));
assert.equal(S.createStore(storage, image).read().kind, "invalid");
storage.setItem(S.STORE_KEY, JSON.stringify({ version: 99 }));
const unknown = S.createStore(storage, image);
assert.equal(unknown.read().kind, "unsupported");
assert.equal(unknown.saveGraph(graph).kind, "unsupported");
assert.equal(JSON.parse(storage.getItem(S.STORE_KEY)).version, 99);
assert.equal(unknown.reset().kind, "fixture");
assert.equal(unknown.read().value.runs.length, 0);
const failing = S.createStore(
  {
    getItem: () => null,
    setItem: () => {
      throw Error("quota");
    },
  },
  image,
);
assert.equal(failing.saveGraph(graph).kind, "unavailable");
assert.equal(failing.read().value.graph.nodes[2].parameters.epochs, 2);
console.log(
  "PASS workspace fixture contracts, graph errors, snapshot isolation, stale validation, storage conflicts and recovery",
);
