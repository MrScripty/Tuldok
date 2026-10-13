# Frozen sequence integrity runs

`sequence_validate_export`, recipe version 1, admits exactly
`release → validate → publish` using `frozen_release` and `validated_release`
ports. The release node alone accepts `release_id`. It shares Pipeline's graph
revision/token checks and Runs' queue, idempotency, cancellation, retry,
interruption and immutable publication owners with the mesh integrity recipe.
No database migration, second supervisor or training worker is introduced.

Selection requires a sequence-only canonical v1 archive and then invokes
`sequence_release` for full immutable-byte validation. Canonical v1 has no
format tag. Mesh/sequence mixtures, other canonical kinds and a sequence release
bound to a mesh recipe are rejected. Native interpretation remains with the
existing Rheon reader; `canonical_release` owns shared archive/projection/family
custody. Existing classification and mesh graph/result identities are retained.

The admitted reader covers the pinned nine-frame dense3D transport pilot, not
arbitrary trajectories, volumes, simulation acceptance or general 3D training.
Whole trajectories remain indivisible. Selected-record-only family scope and
all reader limitations remain visible in the report.

## API and results

Release and run responses use `result_kind: release_validation`. The release
summary exposes `recipe: sequence_validate_export`, `format: canonical_v1`,
record/split counts and `validation_summary`. The report contains sequence and
frame counts plus each trajectory's exact asset/run/frame hashes, native grid,
field types, units, source frame/time index, technical validation, pressure
semantics and provenance. Original source files are never rewritten.

`validation-report.json` contains the shared schema-1 identity envelope and
`adapter: {id: sequence_validate_export, version: 1}`. Its exact summary must
match admitted evidence; report and artifact-manifest custody are verified on
completed detail/artifact reads. `release.zip` downloads unchanged frozen bytes.
There are no predictions, metrics, test-model exposure events or quality claims.

In-process execution pins the transitive local import closure including both
native readers and shared canonical owner. Admission refuses disk definitions
that differ from the application import snapshot. Runtime checks bracket native
validation; cancellation is observed before validation and before publication.
The existing mesh lifecycle guarantees and bounded, non-preemptive reader
limitation apply equally here. Retained completed mesh reports do not acquire
sequence identity or require retraining after this extension.

Evidence is owned by `tests/test_sequence_runs.py`, the dedicated frozen reader
suite and `tests/browser_workspace_sequence_run.cjs`. The run suite exercises
actual retained producer bytes through PostgreSQL admission, report publication,
byte-identical nested source downloads, grid/time/unit checks, restart,
cancellation/retry, malformed graph/token rejection and artifact corruption.

## Producer controls v2

The same recipe accepts explicitly validated v2 three-file bundles and retains
controls metadata in its integrity report. No training or simulator runs. V1
retains its original hashes, protected identities and report shape; v2 adds
control custody and compact interval/provenance inspection. Fixture-based
integration is distinct from still-blocked actual PR32 packet acceptance.
