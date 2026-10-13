# Frozen mesh integrity runs

`mesh_validate_export`, recipe version 1, is a closed real recipe with exactly
`release → validate → publish`. Ports are `frozen_release` and
`validated_release`. Only the release node accepts a parameter (`release_id`).
Graph edits, layout, cloning, revision checks and execution digests use the
existing Pipeline owner. Retained classification graphs, digests and results
keep their existing contract.

Selection recognizes mesh-only canonical releases by bounded manifest record
kinds, then delegates full captured-byte verification to `mesh_release`.
Canonical manifests have no format tag. Mixed canonical archives and other
canonical subtypes are not admitted by this recipe. Existing Data downloads
remain unchanged. The reader enforces 64 MiB releases, at most 64 meshes and
40 MiB of bundled mesh bytes, with its existing metadata and native limits.

Release summaries include `recipe: mesh_validate_export`, `format: canonical_v1`,
`result_kind: release_validation`, record and split counts and
`validation_summary`. The summary retains selected-record-only family scope,
units/frame declarations and the reader's limitations. Validation proves
integrity, not simulation suitability, rights certification or model quality.

## Admission and lifecycle

The existing Runs owner freezes graph, release identity, summary and definition
identity, persists idempotent submission receipts and queues the attempt. No
training interpreter, GPU, downloaded model or training subprocess is required.
The integrity adapter pins the transitive local Python import closure; Python
version and execution mode are part of its runtime fingerprint. Admission rejects
disk definitions that differ from the application import snapshot; restart is
required after changing implementation files.

The sole supervisor thread rechecks definition identity, revalidates the exact
release hash and compares the report with admitted evidence. It checks
cancellation before validation and before publication. Native parsing is bounded
but not preempted mid-operation; cancellation waits for it to return. Shutdown
keeps metadata open until supervisor drain. This recipe spawns no child process
and leaves `process_phase: not_started`; after process death the existing
recovery owner marks running attempts interrupted and never replays them.
A new explicit retry receives a new run identity.

Publication uses the existing staging directory, fsync, rename and durable
receipt pattern. A successful report has three completed node attempts,
`metrics: null`, `parameters: {}` and `quality_claim: false`.

## Artifact custody

`validation-report.json` is a closed object with `schema_version: 1`,
`source_identity`, `adapter` and `validation_summary`. Source identity includes
dataset, run, graph and release hashes. `artifact-manifest.json` contains the
same identity and adapter plus the exact one-payload inventory. Every completed
run/detail and artifact read verifies regular files, size bounds, report
identity/evidence and inventory hashes. The unchanged `release.zip` is served
through the existing verified input-artifact route. A broken result directory
is unavailable, and list responses remove the summary when custody fails.

These runs do not create test-model exposure events and do not provide model
predictions or test metrics. The existing empty exposure envelope is retained
for transport compatibility; the UI must not interpret it as holdout evidence.

Evidence: `tests/test_mesh_runs.py` exercises real PostgreSQL admission,
completion, frozen downloads, reopen, stale input/definition, cancellation,
retry, interruption and report tampering. Browser evidence is owned by
`tests/browser_workspace_mesh_run.cjs`; synthetic geometry proves workflow and
native integrity only.
