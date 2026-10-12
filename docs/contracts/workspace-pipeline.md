# Workspace pipeline v1

Owner: `pipeline.py:Pipelines`. PostgreSQL catalog version 2 owns persistence;
`app.py` translates HTTP requests. The S1 fallback admits three fixed CPU classification recipes: image TinyCNN,
text TF-IDF / MultinomialNB and reviewed WAV interval features / logistic
regression. It remains a closed graph engine; ASR, 3D execution and other
trainers are unsupported.

## Documents and editing

`create({name, release_id, recipe?})`, `get(id)`, `list()`,
`save(id, {revision, document})` and `clone(id, {name})` return graph documents:

```json
{
  "schema_version": 1,
  "mode": "real",
  "recipe_version": 1,
  "id": "32 lowercase hexadecimal characters",
  "revision": 1,
  "name": "Image baseline",
  "nodes": [
    {"id": "release", "type": "release", "definition_version": 1,
     "parameters": {"release_id": "64 lowercase hexadecimal characters"}}
  ],
  "edges": [],
  "layout": {}
}
```

The example shows a partial editable image draft. Missing `recipe` retains the
original image v1 interpretation and digest; text and audio graphs explicitly
contain `recipe: "text_classification"` or `"audio_classification"`, recipe
version 1. Unknown recipe names fail closed. New recipe documents require the
corresponding application version; downgrade requires a stopped-writer complete
pre-feature backup rather than deleting newer state.

The example shows a partial editable draft. `create` supplies all five nodes and
four edges. Drafts permit 1–10 nodes, at most 12 edges and 32 KiB of finite JSON.
Names have at most 120 characters. Layout maps existing node IDs to bounded
numeric `{x,y}` coordinates. Unknown fields, duplicate IDs, fixture documents,
malformed values and incompatible schema/recipe versions are refused.

Saving uses the Dataset catalog lock and transaction with a checked edit
revision. A successful save increments that revision. Clone makes an independent
ID at revision 1. A stale save cannot overwrite another editor. Invalid semantic
drafts, such as disconnected edges, remain saveable for correction.

The executable digest includes schema, real mode, recipe version, nodes and
edges, plus the explicit recipe when present. Name, edit revision and layout are excluded. Submission separately binds
the saved revision. A run stores the entire graph snapshot and its own digest;
later edits and clones cannot change that evidence.

## Definitions and validation

`definitions()` retains its existing image fields and adds `recipes`, each
with its version, node ports and authoritative parameter bounds. The image
sequence is:

| Type | Input | Output |
| --- | --- | --- |
| release | — | frozen_release |
| validate | frozen_release | image_export |
| train | image_export | trained_model |
| evaluate | trained_model | evaluation |
| publish | evaluation | — |

Executable graphs require exactly one of each type, definition version 1, and
exactly those four ordered connections. Cycles, disconnected graphs, duplicates,
wrong ports and unsupported nodes cannot execute. This fixed recipe is the
complete admitted image engine surface. The text recipe uses the same five
stages with `text_export` in place of `image_export`; audio uses `audio_export`.
The chosen release format must match the saved recipe.

The release node accepts only `release_id`; train accepts exactly `epochs`,
`batch_size`, `learning_rate`, `seed`; other nodes accept no parameters. The
adapter's `PARAMETER_BOUNDS`/`validate_parameters` remain their single owner:
1–5 epochs, batch size 1–16, learning rate 0.00001–0.01, unsigned 32-bit seed.
Defaults are 1, 8, 0.001 and 42 respectively. Text accepts exactly
`max_features` (64–4096, default 1024) and `alpha` (0.01–10, default 1); it
performs one fit. Audio accepts exactly `C` (0.01–100, default 1) and fits
train-only scaling plus bounded logistic regression. See the
[text](workspace-text-training.md) and [audio](workspace-audio-training.md)
contracts for exact input, numerical and model semantics.

`validate(id, {revision})` returns `status`, `valid`, `errors` (each with `path`,
`code`, `message`), `validation_token`, `graph_revision`, `execution_sha256`,
`release`, and `runtime`. Invalid, unsupported, unavailable and stale remain
distinct. No preview launches training or downloads a model.

The server reads a saved graph, validates its semantic contract, independently
verifies frozen release bytes through the selected image/text/audio adapter reader, probes
the actual configured local Python runtime, then rechecks the graph revision.
The token fingerprints the saved revision, executable digest, release SHA,
adapter definitions and runtime. It is a freshness proof, not authorization:
submission repeats all checks and compares the token before admission.

`TULDOK_TRAINING_PYTHON` selects the local isolated interpreter; absent that value,
the application interpreter is probed. Nothing installs an environment. The
probe has a 45-second bound and reports missing pinned packages honestly. Source
identity covers `image_training.py`, `image_classification_export.py` and
`workbench.py`, the worker's actual local import set. Execution copies those
hash-verified files into its private attempt staging directory. Text and audio recipes pin their own reader/export modules, shared complete-family
reader, existing JSON/process primitives and Workbench; audio additionally pins
the existing WAV parser. See their contracts. Probes and workers override inherited native math
thread settings to one. A malformed/unsupported ZIP remains an individual typed
release entry and cannot break the release listing.

## Release custody and exposure

`releases()` inspects up to 100 content-addressed release ZIPs. Each entry is
available with format, class vocabulary, split counts and exposure evidence, or
carries a typed reason it cannot serve this recipe. `inspect_release(id)` reads
the exact existing release; it does not export a new selection or mutate Data.
The original Workbench and Releases owners retain review, family and release
creation authority. Current annotation edits cannot alter a frozen export.

`prior_test_exposure` lists append-only events matching a record ID **or** its
exported image pixel SHA, canonical text content SHA or whole decoded-PCM/rate/
channel family SHA, so a new release, interval change or reimport cannot silently
present exposed content as a fresh holdout. Runs preserve admission evidence and also expose
current evidence and a fresh pre-execution snapshot.

All public errors use `WorkbenchError(message, code, status)`. Bad input is 400,
missing IDs 404, and stale/conflicting/unavailable admission is 409. Filesystem
paths, SQL and trainer process creation are not HTTP/UI responsibilities.

Focused evidence: `tests/test_pipeline.py`; the real completed workflow and
cross-owner invariants are in `tests/test_runs.py` and the browser workflow.
