# E2 host context contract, source proposal

This is the lead-allocated explicit recipe/spec variant (PR73 comments6202648109,
6202721183 and6202835326). It does not activate E2 from structural fixtures.
The original external_recipe_v1 definition, material and argument domain stay
closed. The source proposal separately changes recipe_process.py to verify the
one new captured context file; the existing custody protocol remains authoritative.
Canonical field_evidence.py is owned by P4 and is not copied into this change.

Pipeline resolves `extension_field_policy_v1` only for schema2
`external_model_evidence_recipe_v1`, against the actual published Model and actual
captured input receipts. Runs supplies the assigned attempt and request after
ordinary full-composition admission. The canonical context is at most65536 bytes,
contains no self hash and uses exactly one explicit argv token. Spec2 captures its
exact name/hash/bytes at `runtime-bootstrap/model-evidence-context.json`. The
prepared template has no context and cannot launch. The final file is host-owned,
read-only, held/checked by the same custodian before execution and after drainage.
Publication and cold reads must rederive the context from immutable retained
composition/model/profile and apply current transitive input permission guards.

The new pure decoder validates D2 documents, all required capabilities, exact
clock/profile/probe/source/Run/model/task bindings and actual declared native
field payload hashes. It does not load weights, import project code or implement
training, inference or error metrics. Its `verified` outcome means structural and
identity closure; numerical acceptance is a separate independent consumer result.
Scientific test access is unsupported. Query selectors are a closed object:

- `{}` returns manifest, checkpoint_index, probe, metric_definitions, observations,
  model_definition, fields and checkpoint descriptors, plus state/validation.
- `{checkpoint_sha256: SHA}` adds that exact checkpoint descriptor.
- `{checkpoint_sha256: SHA, member_ordinal: INT, field_id: TEXT,
  axis: "x"|"y"|"z", index: INT}` also returns the exact native orthogonal field
  slice: prediction/reference arrays, shape_zyx/grid/stage/units/dtype/centering,
  row_axis/column_axis, physical_origin/physical_row_step/physical_column_step.
- `split:"validation"` may accompany these; test and unknown populations refuse.

There is no private array byte payload in the public projection. No numerical
error operator or UI callback is part of this extension boundary. Main owns the
selected HTTP/API/UI output union and rendering after actual Run qualification.

## A source and independent consumer freeze

New authored A fixture v2 retains all v1 numerical values; it newly declares zero
origin/identity orientation/metre spacing/identity gauge before execution. SHA256:
`3c25603d4d95cd904b0d09582daadf000c0977af7bcdcea39ef2c6deffe86e5f`.

Independently reviewed, standard-library-only cold consumer SHA256, frozen before
any actual v2 producer Run:
`ccfbe3bc92badf265ea882382d392e05daca091f5694f528f268ec3d6e38764b`.
Its synthetic closed-form review is not a producer/training execution. It uses
one retained context read through a held nofollow directory descriptor and checks
actual retained weights/predictions against an independent64-update trajectory.

Contract tests16 passed independently. Existing recipe tests8, CPU recipe tests4
(actual disposable PostgreSQL), and Linux custody tests27 passed, with no skips.
The structural synthetic fixture explicitly fails the numerical oracle; none of
these results substitute for a fresh captured CPU Run, actual host publication,
cold owner/HTTP query, common UI or E2 acceptance.

## P5/E4 author contract handoff

Task ID `example.scalar-a:task`, revision2; profile ID
`example.scalar-a.fixed-validation`, revision1 (exact authored recipe.json is the
source of truth). Weights are data-only little-endian float64 NPY `[scale,offset]`;
transform.npy is train-only float64 `[mean,std]`. Checkpoint descriptors separately
bind clocks and opaque weights; never use the weights hash as checkpoint identity.

Retained input is `input-initial.npy`, reference `reference.npy`;
checkpoint prediction/weights names are declared explicitly in recipe.json's
field_outputs and outputs. Field stage ID `raw`, output field `prediction`, is standalone cell float64,
4x4x4, dimensionless, identity gauge, post_train_mapping stage; no physical-time or
protected task population is declared. Original fixture membership remains2train,
1validation. Actual16/32/48/64 cadence is required. The model specification owns
architecture and field names only; learning_rate and fixed64 updates are typed
recipe parameters. Last-checkpoint selection is diagnostic until a separate
accepted Study selection policy says otherwise.

Published captured Model source mapping must include exactly the five recipe
sources: producer.py, evidence_writer.py, task.json, extension.json and NOTICE.txt,
with their exact import paths/Blob hashes. The independent oracle is deliberately
outside producer capture. No A inference-entry/package reconstruction module is
yet frozen. P5 must not invent an executable hook or treat this proposal as E4
acceptance; reconstruction and its independent tolerances will be frozen before
any fresh package consumer. B is not yet authored. Rights are private QA only.
