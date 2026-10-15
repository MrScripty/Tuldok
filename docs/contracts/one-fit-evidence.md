# One-fit classifier evidence (adapter version 2)

`text_training.py` and `audio_training.py` own task semantics and data-only
inference. `one_fit_evidence.py` owns their shared D2 capture format. Runs owns
admission, captured sources, supervision, inventory integrity, access and atomic
publication. `text_classification_model_v2` and
`audio_classification_model_v2` expose typed templates, immutable preparation,
owner-authorized finite Study/Run execution and the shared evidence query.
Real HTTP/CPU qualification is recorded in the [P4 report](../plans/end-to-end-model-development/reports/p4-one-fit.md).
The separate scientific adapter and generic text/audio inference package remain
unsupported until their own qualification; this does not qualify them.

## Selection and compatibility

Existing schema-1 jobs, adapter-version-1 model documents and five-payload
inventories retain their behavior. They receive no invented checkpoint history.
A schema-2 job adds exactly `adapter` and `evidence` to existing fields. Adapter
name is unchanged and version is integer `2`; unknown versions fail before fit.

`evidence` has exactly `catalog_id`, `material_sha256`, `adapter_sha256`, `model_sha256`, `task`,
`profile_sha256`, `selection_policy_sha256` and `output_policy_sha256`. Task
is a D2 reference with `kind`, `catalog_id`, `id`, `revision`, `sha256`, revision
`2` and ID `text_classification` or `audio_classification`. These are selected
immutable owner identities, never inferred from live drafts. Pipeline pins
this helper and the shared `model_evidence.py` bounded decoder in its source
closure and resolves all output caps before launch.
Negotiated graph-create/save contract **3** adds these recipes. Contracts 1 and
2 keep their exact existing schemas and digests. New one-fit graph variants
require contract 3; older or absent selections fail before mutation. Ordinary five-stage graph
documents retain recipe version 1; the distinct recipe/adapter IDs select new
semantics without rewriting retained graphs.

## Captured result

The actual estimator fit produces one checkpoint: `fit_pass=1`,
`optimizer_update=null`, `epoch=null`, `physical_time=null`. Monotonic
`wall_elapsed_ms` is measured at fit completion, including release/runtime/
preprocessing work since adapter start. The existing bounded progress wire uses
historical `epoch` keys; Runs presents those task events as fit passes. Those
wire keys create no epoch observation or curve in version-2 evidence.

The five existing payload names remain with version-2 adapter identity.
`metrics.json` has `clocks`, with no `history` or `best_epoch`. Additional files:

- `model-evidence.json`: closed D2 `model_evidence_v1` manifest;
- `checkpoints.json`, `checkpoint-fit-0001.json`: one selected retained D2 index
  entry and its exact `checkpoint_state_v1` descriptor;
- `probe.json`, `probes-fit-0001.json`: full ordered validation membership and
  probabilities/targets/first-argmax predictions bound to checkpoint/probe hashes;
- `observations.json`, `metric-definitions.json`: full-validation loss,
  accuracy and macro F1 with explicit task definitions;
- `fitted-transform.json`: ordered train references and fitted vocabulary/IDF
  or audio mean/population scale;
- `model-definition.json`: selected specification, parameters, preprocessing
  and frozen-vocabulary output policy;
- `profile.json`, `output-policy.json`: the resolved full-validation one-fit
  profile and frozen-vocabulary output policy;
- `probe-inputs.json`: canonical text strings or exact source-channel interval
  feature measurements, bound to the probe hash for cold reconstruction.

The descriptor binds exact `model.json` weights and fitted-transform digest.
Manifest observations reference both scalar and classifier shards. The outer
artifact manifest binds all seventeen payloads. Test metrics/predictions keep
separate test roles; new probes and observations contain validation only.
Model/training-statistic access retains transitive data permissions; capture
confers no private-data export right. No new dependency is selected.

## Verification and limits

Both adapters expose `verify_evidence(directory, job)` and `--verify-evidence`:
reopen the exact frozen release and reconstruct from JSON. Runs launches this
only in a supervised captured-source CPU subprocess before publication.
`one_fit_evidence.verify` supplies inert publication/query checks of identities,
membership, arrays and independently tallied metrics; it imports no numerical
runtime and runs no reconstruction. No pickle or evidence-specified code
executes. The caller first verifies drained private Run custody, inventory,
byte caps and authority, then publishes atomically after all checks. Required
missing or inconsistent evidence fails publication.

`tests/test_one_fit_evidence.py` uses real child-process fits, authored frozen
releases, PostgreSQL and the pinned sklearn 1.7.2 CPU runtime. Fresh interpreters
reproduce probabilities; independent IDF arithmetic and audio population
statistics check train-only fitting. Clock/weight/input mutations fail. These
are producer/task-contract checks. `tests/test_one_fit_studies.py` separately
proves real HTTP model publication, finite Study admission, Run capture, query
and cold reopen. `tests/qualify_model_development.py --task text|audio --fixture
tests/fixtures/model_development --output /tmp/new-one-fit-qa` retains a receipt
and independent isolated inference using only copied JSON, a test oracle and
the compatible runtime. It does not import the adapters or original checkout.
UI and scientific physics acceptance remain separate.
