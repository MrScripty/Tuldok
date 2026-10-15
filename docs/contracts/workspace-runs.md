# Workspace runs v1

Owner: `runs.py:Runs`. The Dataset shares its PostgreSQL connection, catalog lock
and transactions. `metadata.claim_runtime('workspace_runs')` gives one supervisor
per catalog across application instances and local paths. Construction performs
recovery without loading Torch or scikit-learn or starting a worker thread. Real work starts only
after explicit durable admission. Another application may observe and cancel
through the shared store, but cannot submit through a non-owner supervisor.

## Admission and observation

`submit({request_key, graph_id, graph_revision, validation_token})` first looks up
the idempotency key and exact request digest. A matching prior receipt is returned
before current graph validation, so a lost acknowledgment remains reconcilable
after the graph changes. Reusing a key with different content is a conflict.
Keys contain 8–128 letters, digits or `._:-`. A database unique constraint and
catalog transaction serialize competing admissions.

A committed queued receipt whose acknowledgment was lost wakes the existing
owned, unblocked queue when the caller explicitly reconciles the same request.
It never creates a second run. Restarted catalogs do not replay old queue entries.
There are at most eight active admitted attempts and one active training child.

`list()` and `get(id)` return real mode, dataset/run IDs, saved graph snapshot,
graph and release SHA, graph revision, adapter/runtime/parameters, attempt and
parent IDs, timestamps, events, progress, node attempts, artifacts, metrics,
errors and exposure evidence. `quality_claim` is false: actual execution proves
the result was computed, not that the corpus/model is fit for a real use.
Progress totals are null until actual bounded fit-pass events establish them.
Image epochs retain their existing meaning; text has one non-iterative fit pass.
Audio records one bounded logistic fit as epoch 1, not one optimizer iteration.

The state vocabulary is `queued`, `running`, `cancelling`, `completed`, `failed`,
`cancelled`, `interrupted`, `unknown`. `completed` requires a drained successful
worker plus verified, published output files. A cancel request is not a
cancellation result. `cancel(id)` is repeatable; queued attempts cancel before
process creation, while running attempts remain cancelling until cessation.

## Worker and restart lifecycle

The supervisor copies the selected closed image/text/audio adapter and its pinned local source dependencies
into a private `.staging-<run_id>` directory, writes the closed trusted job, and
launches the configured interpreter in a new Linux process group. It performs
probes, training and waits outside database locks. The adapter arms Linux parent
death protection before importing the numerical runtime. Image DataLoaders use
no child workers; text/audio fitting also creates no child workers. Native math thread
environment settings are bounded to one, including inherited OpenBLAS settings.

Process identity is PID, Linux boot ID and `/proc` start ticks. The owner signals
only its currently owned live `Popen` process after checking that identity.
Cancellation sends TERM, then KILL after three seconds if needed, waits, and
checks that the process group is absent. Unconfirmed cessation becomes unknown
and fences both new submissions **and already queued work**. No recovered PID is
ever signaled. Execution has a ten-minute bound.

Durable process phases distinguish pre-spawn validation (`not_started`), the
spawn/PID-receipt window (`starting`), and a recorded worker (`started`). Recovery
interrupts proven pre-spawn work. A recorded worker that still exists or cannot
be observed is unknown; observed cessation permits interrupted, never success.

For an ambiguous spawn without a PID receipt, recovery first requires the exact
original supervisor identity to have ceased. It then performs a read-only
same-user `/proc` scan for that attempt's exact private adapter and job argv.
A matching or unreadable candidate stays unknown. Proven absence permits
interrupted under this closed, parent-guarded, no-child-worker contract. Stop
the old application and reopen the catalog to repeat this bounded reconciliation;
recovery never starts training. This is Linux-specific, not a portable process
discovery or termination API.

Database loss does not prevent draining the owned child or joining the supervisor
on shutdown. A failed durable update is not reported as successful cancellation;
the remaining active row is reconciled on reopen. No worker may outlive a
successful local shutdown. The application must retain metadata if a supervisor
cannot drain within the shutdown bound.

The only accepted stdout messages are the adapter's bounded, closed JSON started,
epoch, completed and failure events. At most 64 KiB and 32 retained events are
accepted. Epoch metrics must be validation metrics with the frozen example count.
No arbitrary stdout, stderr or test metrics are published as logs.

## Artifact publication and reuse

An admitted `input_artifacts` entry links `release.zip` immediately, including
while queued/running. Its accessor revalidates the exact frozen archive and hashes
the returned bytes. This is the completed validate/export checkpoint. Reuse is
only that verified immutable export; no partial training checkpoint is resumed.

Private output must contain exactly five payloads plus `artifact-manifest.json`:

- `metrics.json`: validation metrics, training history, transforms and runtime;
- `predictions-validation.json`: exact validation example references;
- `test-metrics.json` and `predictions-test.json`: separately gated test results;
- Image `checkpoint.pt`: actual selected model weights and frozen execution metadata;
- Text substitutes `model.json`: checked plain JSON TF-IDF vocabulary/IDF and
  MultinomialNB coefficients; no pickle loader or arbitrary estimator is exposed.
- Audio substitutes `model.json`: checked scaling statistics and logistic
  coefficients/intercepts for its eight fixed source-interval features.

The run owner verifies regular files, no symlinks, a 64 MiB aggregate bound,
manifest hashes/sizes/media/split roles, closed JSON envelopes, source identity,
runtime, class vocabulary, finite metrics, history and exact prediction references.
Prediction probabilities, labels and indices must agree; independently tallied
predictions must match confusion matrices and their reported accuracies. The
owner does not deserialize arbitrary checkpoint pickle data. The text model
reader additionally checks bounded numeric arrays, exact class/feature indices,
recipe and source identity. The audio reader additionally checks bounded scaler
and binary/multiclass coefficient shapes; predictions bind integer source
rate/channel/frame coordinates and original/PCM identities. The retained image
payload contract is unchanged.

Files and directory are fsynced, then output is renamed atomically to the run ID
directory. Only afterward is the completed receipt committed. A crash or failed
commit may leave orphan published bytes, but never exposes them as successful
results. Staging and failed evidence are retained; there is no automatic cleanup
that could erase investigation evidence. Artifact reads check hashes again and
fail closed on loss or modification. Run lists suppress unavailable metrics if
artifact integrity no longer holds; detail/download returns a typed error.

`retry(id, {request_key})` is permitted only for failed, cancelled or interrupted
attempts. It creates a new run with immutable parent link and the parent's frozen
graph/release, revalidates availability and runtime, and trains from scratch.
Completed or unknown attempts cannot be restarted through this operation.

## Holdout exposure and correction

Default metrics and predictions are validation-only. `expose_test(id, {reason})`
requires completed verified output and an explicit nonempty reason, then commits
append-only exposure rows for every frozen test record ID and its image pixel SHA or canonical text
content SHA, or the complete decoded-PCM/rate/channel family SHA for audio.
Changing an audio interval or RIFF metadata does not erase exposure. Original
source hashes remain separate provenance.
Only after this durable event may test metrics/predictions be downloaded.
Exposures never change frozen releases, metrics or predictions.

`prior_test_exposure` is the immutable admission snapshot;
`execution_test_exposure` records the final pre-spawn check;
`current_test_exposure` refreshes on every observation. Later inspection of an
older run therefore cannot leave a newer run visually marked as fresh.

`predictions(id, split='validation')` adds `frozen_reference` and `current_record`
to each row. Current revision differences and unavailable records are explicit.
A correction uses the existing Workbench save/review owner and creates a new
draft; it cannot edit the historical truth/prediction. A new release/run is a new
evaluation, with prior exposure/reuse still visible.

All public domain errors are `WorkbenchError`. `artifact(id,name)` returns
`(verified_bytes, media_type)`; callers never receive a filesystem path.

Evidence: `tests/test_runs.py` uses actual PostgreSQL, real processes and a real
TinyCNN CPU result. Failure-only sleeping/exiting workers isolate cancellation
and recovery proofs; they are never presented as trained results. Actual offline
network-denial/browser qualification is owned by the integration gate, not proved
merely by these local unit tests.

The [text](workspace-text-training.md) and [audio](workspace-audio-training.md)
recipe contracts define their versioned release/adapter/model meanings. No SQL/schema migration or second run supervisor
is introduced. Retained M2 image receipts, artifacts and exposure remain readable.

## Automatic model evidence

`model_evidence(run_id, {checkpoint_sha256?})` is an inert inspect operation over
verified published bytes. Its result contains the common manifest, checkpoint
index, probe membership, metric definitions, scalar observations and model
specification. An exact descriptor hash additionally selects its checkpoint and
prediction shard; a foreign hash is rejected. Old adapters return explicit
`unsupported` instead of inventing historical checkpoints. There is no test split
selector; existing holdout exposure controls remain authoritative.

`compare_model_evidence(run_id, other_run_id)` admits comparison only with equal
task meaning, input/output policy, class vocabulary/order, exact frozen validation
membership and metric definitions. A corrected training annotation can produce a
new immutable release while preserving compatible validation membership. Changed
validation targets, source revision, class order or preprocessing are incompatible
and produce reasons without comparative metric values. Current record editing
continues through Workbench; retained inputs and prior evidence stay immutable.

Built-in model-aware trials use the same owner-only Runs admission, finite Study
reservation transaction, eight-attempt queue and one worker. A membership/budget
or external execution grant cannot launch a built-in trainer as an agent. The
supervisor captures and checks the new evidence automatically; users configure
neither logging nor manual artifact imports. Runtime installation is separate
existing capacity. Conservative Study accounting reserves750 seconds per attempt
and the full64MiB output envelope plus capture/publication duplication; it is an
admission limit, not an OS sandbox or hard aggregate resource quota.

The selected version2 comparison contract requires both evaluation manifest byte
hashes, both checkpoint descriptor hashes, metric ID, each exact metric-definition
hash and `paired|side_by_side` mode. Its labelled sides preserve observed versus
undefined values and their reasons. Paired differences are returned only for
compatible semantics and observed values; undefined arithmetic remains explicit.
Incompatible or side-by-side comparisons return no paired difference. The earlier
version1 comparison remains the explicitly narrow selected-result summary.
`model_evidence` supplies authoritative `metric_definition_hashes` so interfaces
can select exact definitions without implementing canonical hashing.

Qualified model-aware classifier publications support the existing bounded
artifact-segment transport for agent downloads of retained fitted state. Each
call checks current authority, the exact published inventory and test exposure;
the client verifies the complete downloaded SHA256 before publishing a file.
The original standalone classifier recipes retain their previous transport
contract. This does not grant test access or promise training resumption.
