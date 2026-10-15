# D2: Contracts, evidence and retained state

Date: 2026-10-15. Proposed product contracts, not implemented APIs, migrations,
telemetry collection or model qualification. D1 decisions remain authoritative
in the [plan](../plan.md). This report owns D2's concrete semantic/boundary design;
D3 measures defaults and demonstrates interaction, and D4 names implementation
slices and exact migration DDL. New wire names below are **proposed**.

## Baseline, notation and authority

D2 continues PR62 from D1 `0f8ccfe`; fetched application main remains
`f58880df84d701ef66ffe21615ae787d80ce8a5e`. No applicable AGENTS.md or live Coding
Standards MCP is exposed. Retained routing and adopted `dcc56f26` source guidance
apply with the same limits as D1. [Observations](design-observations.md) distinguish
current source/decoder results, previous measured receipts and authored examples.

All new records below are closed objects: listed fields required unless marked
`?`; unknown keys/versions, duplicate keys, nonfinite values, bool-as-integer,
NUL/surrogates, inconsistent references and excess limits fail before use.
`Id` is a catalog-scoped 32-lowercase-hex identifier; `Sha` is 64 lowercase hex;
`Nat` is an actual integer 0..2^53−1, `Pos` 1..2^53−1, `Text(n)` UTF-8 text with
at most n Unicode scalars and no controls. Enum spelling is exact. No scalar
coercion. References never grant access. Current legacy decoders keep their
actual narrower/different rules; no silent upgrade of their accepted grammar.

`Blob = {name:Text(120), sha256:Sha, bytes:Nat, media_type:Text(80)}` names one
flat declared owner-managed blob, never a client path/URL. The enclosing record
fixes the owner/store (model/Pipeline capture or Runs); bytes must match that
owner's verified inventory. Existing nested import/source paths stay in the
captured recipe/source index, not in a public filesystem resolver. Model source
closure includes a captured import-path→blob mapping and entrypoint; a list of
anonymous source hashes alone is insufficient. Internal captures reuse existing
source/input custody. Immutable public reference variants are closed:

| Ref.kind | Exact remaining fields (all include catalog_id:Id) |
| --- | --- |
| task, trainer, profile, selection_policy | `{kind, id:Text(64), revision:Pos, sha256:Sha}`; stable definition ID/version and exact body hash; adapter owns task/trainer/profile, Experiment owns selection_policy. |
| model | `{kind, id:Id, revision:Pos, sha256:Sha}`; published model revision. |
| release, runtime, recipe_material | `{kind, id:Sha, sha256:Sha}`; id equals content hash, no edit revision. |
| evidence | `{kind, id:Id, sha256:Sha}`; id is producer Run ID, hash is evidence manifest. |
| candidate, trial | `{kind, id:Id, sha256:Sha}`; immutable decision/membership record. |

`SourceSelector = {project_id:Id, recipe_id:Text(64), expected_sha256:Sha}`
selects the declared source/import closure of an existing captured Project recipe
through Projects inspection/capture. It is inert and carries no arbitrary path.
`ArtifactRef = {catalog_id:Id, run_id:Id, name:Text(120), sha256:Sha, bytes:Nat}`
selects one Runs-verified artifact (including an inference-package manifest).
It confers no access and is not an evaluation snapshot Ref.

No other kind, extra/missing revision, cross-catalog resolution or alternative
ID spelling is accepted. Unqualified project data use existing typed captured
input receipts inside recipe material, not a fake release Ref. Query snapshot is
an evidence Ref. Publication/query verify cross-owner references and full semantic
closure, not only these syntactic domains.

For content identities use the existing owner canonical JSON encoder (sorted
keys, compact separators, UTF-8, finite values, no Unicode normalization) and
SHA-256; input lists remain ordered. Exact-byte blob hashes hash original bytes,
not decoded/reencoded content. The identity of a record hashes its versioned
body excluding its own ID/hash and viewer projections. D2 uses no new generic
canonicalization/hash service. Existing retained byte spelling stays intact.

| Meaning | Owner / retained representation / invalidation |
| --- | --- |
| Task | Adapter-owned immutable task contract: input/target/output meaning, supported metrics/losses, transforms, clocks and profile schemas. Task semantic version is separate from source and artifact format version. |
| Model | Model owner publishes `{format:model_material_v1, task:Ref, specification:Blob, source_closure:[Blob], preprocessing_policy:Blob, output_policy:Blob}`. Definition is inert and immutable. Fitted statistics and weights are attempt artifacts, never editable definition values. Source/shape/policy change creates new identity. |
| Recipe snapshot | Pipeline owns `{format:recipe_material_v1, catalog_id, recipe_id, recipe_revision, recipe_document:Blob, executable_sha256, model:Ref, data:[Ref], trainer:Ref, evaluation_profile:Ref, resolved_profile:Blob, runtime:Ref, captures:[Blob], resource_envelope:Budget}`. Complete resolved composition, not a promise that mutable graph revisions remain stored. New dependencies change identity; layout/name are not executable inputs. |
| Study and trial | Experiment owns checked study revisions containing exact immutable trial IDs, budget/policy and selection intent. Trial `{format:trial_v1, id, study_id, material:Ref, replicate:Nat}` binds one Pipeline snapshot; seed is in recipe material. Same material/replicate is unique per study; intentional independent replication increments replicate. No editable parameter overrides. |
| Attempt | Runs owns attempt/Run ID, parent attempt, actor, request digest, admission and custody. Reconciliation returns the same attempt; retry creates a new ID/receipt and consumes budget/authorization again. A trial may have multiple failed attempts; none are overwritten. |
| Checkpoint | Producer defines exact weight/state blob and clock, inference/fitted-transform references; Runs owns bytes. Checkpoint key is `(run_id, checkpoint_sha256)`, where the SHA hashes the clock/model-bound descriptor, not raw weight bytes. Same weights at distinct clocks/attempts do not merge checkpoint identities. |
| Probe | Evaluation profile resolves immutable ordered validation membership, frozen references, transform/input hashes and target authority; `probe_sha256` hashes the whole manifest. Checkpoint predictions reference it exactly. Probe sampling is not a split definition. |
| Evaluation | Task evaluator owns meaning and protocol; Runs publishes immutable evidence manifest and payloads. Evaluation identity is `(run_id, manifest_sha256)`. Custody verification, semantic validation, numeric acceptance and permission-to-view remain distinct. |
| Candidate | Experiment owns immutable selection `{format:candidate_v1, id, study_id, trial_id, run_id, checkpoint_sha256, evaluation_sha256, policy:Ref, decision:qualified\|diagnostic, limitations:[Text(500)]}`. Package and fresh inference verification are separate artifact/Run references; rejected quality cannot be relabelled by export. |

No model/task/viewer/candidate service registry is added. Metadata owns physical
catalog tables/signatures; these domain owners validate their documents. Current
[metadata schema is 8](../../../contracts/workspace-storage.md), not the older
schema-2 baseline wording in some historical reports. New catalog migration
number is allocated against implementation main in D4, not preemptively claimed.

New model-aware recipe drafts use a closed `recipe_draft_v2` variant in Pipeline:
`{format, id, revision, name:Text(120), task:Ref, data:[Ref], model:Ref,
trainer:Ref, parameters:object, evaluation_profile:Ref, runtime:Ref,
layout:object}`. Parameters obey the selected trainer's closed schema; model
architecture remains only in the model definition. Layout is bounded numeric
presentation and cannot affect execution. The existing closed workflow stages
are derived from the selected trainer integration, not editable layer nodes.
New negotiated `recipes.save/get` owns this variant; old `graphs.*` cannot edit
or admit it. Pipeline preparation binds it to retained material and rechecks all
semantic dependencies. No old recipe is rewritten to v2 on open.

## Immutable preparation, pinning and persistence

Use existing catalog transaction, advisory/thread lock and file rollback hooks.
Pipeline preparation first stages verified immutable source/input/model/profile
bytes privately, without code import, model load, training or permission grants.
A final short transaction rechecks graph revision, source/capture identities and
current access; inserts immutable material and exact blob inventory; and attaches
the requested trial/study revision in the **same catalog transaction**. Domain
methods receive the shared transaction; nested owners use existing savepoints.
No network work, runtime probing or large hashing occurs while holding that lock.

Proposed physical obligations (DDL/migration remains D4): immutable model and
Pipeline material rows keyed by catalog/hash, blob inventory references; study
row `(id, revision, document)` with CAS; immutable trial row unique on
`(study_id, material_sha256, replicate)`; immutable membership revisions;
attempt/reservation link unique on `(study_id, request_key)` and Run ID. Restrict
parent deletion while referenced. Store exact versioned documents as `text`,
consistent with current metadata; do not invent a second JSON database.

Publication uses a private staging directory followed by owner-controlled
immutable publication before transaction acknowledgement. On ordinary rollback
remove only newly created unreferenced bytes. On unknown commit preserve staging
and inventory; do not dispatch. Reconcile a catalog-scoped `(actor_id, request_key,
request_sha256)` receipt before re-preparing or attaching. A repeated identical
prepare returns the prior snapshot/trial even if a later draft differs; changed
body/actor conflicts. If no receipt is proven, repeat the same prepare under
owner reconciliation after checking orphan custody. Never turn missing state
into a new grant or delete bytes on a timeout.

Retain pinned material with the trial, admitted Run and candidates. Explicit
owner discard of an unattached preparation releases its references transactionally;
only proven unreferenced, non-ambiguous task-created blobs may then be removed.
No idle-time automatic garbage collection is selected. Study removal cannot
remove Runs, audits, exposure or referenced material. Backups include all new
rows, blobs, inventories, reservation states and current identities under the
existing stopped-writer complete-backup discipline. Restore never launches work
or refunds grants; interrupted/unknown reservations remain fenced. Old schema-8
backup readers must reject new schema; new reader restores old schema exactly,
then explicit upgrade. Downgrade uses a complete stopped pre-upgrade backup, not
field/table deletion. No migration or restore was executed in D2.

## Default profile resolution

The adapter owns immutable profile definitions. Resolve an explicitly requested
supported profile revision first; otherwise choose the **single** declared default
for the exact task/trainer/model compatibility tuple. Zero matches is unsupported;
multiple matches is invalid registration, never first-in-list. No project-wide,
UI, agent or environment default silently overrides that selection. Resolve all
numeric settings and capability states before material hashing/approval. D3
chooses measured numeric allocations; unresolved required settings prevent preflight,
not a live “automatic” profile that fills in later.

Resolved profile is closed
`{format:resolved_profile_v1, definition:Ref, task_sha256:Sha,
trainer_sha256:Sha, model_sha256:Sha,
probe_selection:{role:validation, algorithm:sha256_rank_v1,
namespace:Text(64), seed:Nat, count:Pos},
capture:{clock:epoch|optimizer_update|fit_pass, interval:Pos,
retain_selected:true, max_snapshots:Pos},
required_capabilities:[Text(64)], optional_capabilities:[Text(64)],
limits:{manifest_bytes:Pos, shard_bytes:Pos, total_output_bytes:Pos}}`.
Count must fit eligible validation membership and task bounds; no test replacement
or duplicate probes when insufficient. Rank each eligible frozen input by SHA-256
of canonical `[namespace, data_sha256, frozen_reference, seed]`, with canonical
reference as tie-break; retain first count, then freeze ordered membership.
Profile seed is independent of training seed so repeated-seed trials retain the
same probes. Targets/transforms are bound before publication; record exact
selection algorithm/version instead of reranking on reopen.

Cadence uses actual declared clocks and post-update/end-epoch convention; one-fit
profiles have clock=fit_pass/interval1 and one observation, not fabricated epochs.
Capture may include the final selected checkpoint outside regular cadence only
when `max_snapshots` reserves that additional slot and output budget upfront.
Its descriptor uses the original producing clock, not final wall time presented
as a new optimizer step. If already retained, selection marks the same descriptor.
No required checkpoint/probe omission can be reclassified as optional to fit
budget. Resolve a different supported profile or refuse preflight. Missing optional
capability is explicitly unsupported/not-applicable/budget-skipped, never a promise
that a generic stdout parser will discover it. This entire resolved body is part
of Pipeline material and exact execution approval; viewing needs no extra setup.

## Evidence envelope and proof at each boundary

Keep the current worker protocol and closed v1 classifier output reader for old
recipes. Admit new model-aware classifier recipes with a distinct recipe/adapter
version and `model_evidence_v1` output contract. External recipes retain
`external_recipe_v1`: an integrated adapter declares the additional evidence
manifest/shards/checkpoints among its exact bounded flat outputs. Ordinary external
output roles do not establish task semantics; a registered task evaluator must
validate the inner contract. Do not add undeclared files to a v1 inventory.

For new evidence, `checkpoint:Blob` is a JSON descriptor with exact body
`{format:checkpoint_state_v1, run_id:Id, model_sha256:Sha, weights:Blob,
fitted_transform_sha256:Sha, clocks:Clocks}`. `checkpoint_sha256` everywhere in
new queries/candidates/observations hashes that descriptor. Its weight Blob is
separately in the same Runs inventory and may be shared by multiple descriptors.
Actual clock/model changes create distinct descriptor hashes even when weights
are byte-identical; do not invent updates to force different weight hashes.
Index summary fields must equal descriptor fields exactly. No fitted statistics
uses a declared canonical empty transform manifest, not an ambient default.
Existing v1 checkpoint bytes are untouched; new evidence does not relabel their
raw digest as a new descriptor hash or manufacture historical sampling points.

New immutable evidence manifest body, exact keys:

```text
{format:"model_evidence_v1", schema_version:1,
 producer:{catalog_id:Id, run_id:Id, material_sha256:Sha, adapter_sha256:Sha},
 task:Ref, model_sha256:Sha, data_sha256:Sha, profile_sha256:Sha,
 probe:Blob, metric_definitions:Blob, checkpoints:Blob,
 observations:[Blob], field_index:Blob|null,
 coverage:{required:[Text(64)], optional:[Text(64)], omitted:[Omission]},
 inference:{mode:"eval_no_grad", fitted_transforms:[Blob], output_policy_sha256:Sha}}
Omission = {capability:Text(64), reason:"not_applicable"|"budget_skipped"|"unsupported",
            required:false}
```

Manifest at most 1 MiB/1024 blob references; shard at most 8 MiB; overall count,
expanded bytes and checkpoints are bounded by the **resolved** profile/resource
envelope and current recipe output limits (32 ordinary, 96 large-output files).
These are proposed transport/format ceilings, not measured capture defaults.
D3 selects affordable cadence/probe/checkpoint counts within those ceilings.
A run requiring more must select an explicitly supported different profile or
fail preflight; no automatic truncation, hidden large-profile promotion or extra
files. Checkpoint blobs obey their declared role/size caps; a manifest never
self-hashes. The existing outer artifact manifest verifies the inner manifest.
All referenced artifacts must be declared in the same verified Run inventory,
except explicitly typed immutable owner inputs already captured in material.

Producer writes temporary files, flushes and closes, then sends existing bounded
progress events. Live progress may contain only adapter-allowed validation
summaries, never evidence of persisted checkpoint completeness. No new unbounded
stdout stream, arbitrary JSON event or output watched mid-write is selected.
After child drainage, Runs verifies exact inventory/bytes/hashes/source/custody;
evaluation validates inner task/model/probe/schema/cross-file meaning; only then
publishes evidence atomically. For new supported recipes, missing or inconsistent
**required** evidence prevents completed evidence publication and yields the
existing failed-attempt outcome with bounded reason. Optional omissions are
explicit; optional telemetry cannot change completion. Partial staged files
remain private diagnostic custody, never a candidate/export source.

Outer binary integrity alone is insufficient: verify outgoing query/manifest
variants, finite numeric domains, complete membership, dimensions and canonical
references as well as inbound requests. No arbitrary model checkpoint is
deserialized by a query/viewer. Schema validation can use established JSON/schema
libraries; this report does not authorize installing a new framework.

| Payload | Exact semantic fields / proof |
| --- | --- |
| Probe manifest | `{format:probe_v1, task_sha256, data_sha256, split:validation, selection_policy_sha256, members:[{ordinal:Nat, frozen_reference:object, input_sha256:Sha, target_sha256:Sha}]}`. Ordinals contiguous, members unique, exact source/annotation/asset identities validated by selected task reader; all belong to validation and the same captured release/split. Classifier reference keys stay those of current image/text/audio adapters; scientific case references bind release/member/frame/field/gauge target, not mutable display name. |
| Checkpoint index | `{format:checkpoint_index_v1, run_id, entries:[{checkpoint:Blob, model_sha256, fitted_transform_sha256, clocks:Clocks, selected:bool, state:"retained"}]}`. Unique descriptor hashes/clock coordinates; repeated raw weight hashes are permitted; selected weights match selection result. Every observation references an actual entry and exact probe. Retained predictions may exist after a nonselected weight is deliberately omitted only under a different explicit prediction-only capability; this initial profile retains weights for every claimed checkpoint. |
| Clocks | `{optimizer_update:Nat\|null, epoch:Pos\|null, fit_pass:Pos\|null, physical_time:Text(64)\|null, wall_elapsed_ms:Nat}`. At least the task's applicable progress clock; physical decimal has explicit units in field/task metadata. Post-update/end-epoch is declared in protocol. Image epochs may also record actual update count; never infer unknown counts. Text/audio fit_pass=1, optimizer_update/epoch=null. Modal fit optimizer_update=0, fit_pass=1; pressure CNN update is actual Adam update; its standalone cases have physical_time=null, not invented simulation frames. Wall time is not an ETA or physical time. |
| Scalar observation | `{run_id, checkpoint_sha256, probe_sha256, metric_id:Text(64), split:validation, clocks:Clocks, state:"observed", value:number, sample_count:Pos}` or same reference fields with `{state:"undefined", reason:Text(64)}` and no value/count. Metric definition owns domain/range/units/reduction/direction. Zero is only observed zero. Missing/failed/skipped is not undefined arithmetic. |
| Classifier probe rows | `{run_id, checkpoint_sha256, probe_sha256, rows:[{ordinal:Nat, truth_index:Nat, predicted_index:Nat, probabilities:[number]}]}`. Same class vocabulary/order and transform as material; exactly the probe membership once. Probabilities finite in [0,1], sum tolerance 1e−4 (existing classifier rule), predicted index first argmax; truth equals frozen target. Re-tally full validation predictions for full confusion/accuracy; probe counts cannot impersonate the full split. |
| Scientific fields | Index binds `{run_id, checkpoint_sha256, probe_sha256, cases:[{member_ordinal, predicted:Blob, reference:Blob, mask:Blob\|null, geometry_sha256, time_units, gauge_policy_sha256}]}` to bounded `pressure_field_pair_v1` standalone NPY pairs for the captured CNN, or explicitly supported `scientific_field_sequence_v1` archives for trajectory adapters. The pressure pair has exact keys `{geometry:object, dtype:"<f8", shape_zyx:[Pos,Pos,Pos], centering:"cell", stage:Text(160), units:Text(80), gauge_policy_sha256:Sha, prediction:Blob, reference:Blob, mask:Blob\|null}`; there is no invented frame/time. Exact grid/orientation/origin/spacing, dtype/centering/field stage, actual frame time when present, unit and mask meaning are validated by domain evaluator. Each array payload hash survives decoding. No generic resampling, re-gauging, unit conversion or stage alignment. |

## Metric meaning and comparison admission

Definitions are frozen with evaluator/source identity and input/output transforms:
`{id, semantic_version, split, units, direction:minimize|maximize|none,
reduction, population_sha256, domain, undefined_rule, evaluator_sha256}`.
Metric names alone never establish comparability. Task adapters own mathematical
meaning; core enforces declared compatibility and bounds.

- Image validation loss is mean per-example cross entropy on logits, accuracy
  is diagonal/total of the full validation confusion matrix, macro-F1 averages
  declared vocabulary labels with zero-division=0 as current code. Units are
  dimensionless; class order/population and preprocessing are bound. Probe
  probabilities are diagnostics, not another full-split metric estimate.
- Pressure training `normalized_mse` averages squared normalized pressure errors
  on **train** cells under train-fitted pressure RMS and cell-zero gauge; it is
  explicitly training-only and cannot rank validation quality. Validation
  pressure relative-L2 uses the declared aligned/gauged arrays and valid mask:
  sqrt(sum((p−r)^2)/sum(r^2)). Empty mask or zero denominator returns `undefined`,
  not 0/NaN. Unknown physical units remain `native_unspecified`. Physical
  residual/divergence/acceptance require a named native evaluator/operator,
  grid/BC/stage and thresholds; a relative-error calculation proves none of them.
- Shared prediction/reference display range comes from both permitted arrays;
  error has a separate range. Scales are view projections over exact values;
  tenfold prediction amplitude must remain visible/numerically nonzero. Changing
  only display colors does not change evidence identity or require retraining.

Comparison request binds both evaluation snapshots, exact checkpoint hashes,
metric-definition hash/ID and mode `paired|side_by_side`. There is no implicit
last/best/average checkpoint. If either side has multiple matching observations
under those exact references, reject ambiguity; aggregation is a separately
frozen policy, not a hidden default. Paired deltas require same metric definition/reduction,
validation population/probe, target meaning, transform semantics, geometry/time/
mask/gauge/unit and compatible evaluator contract. Different model/weight identities
are expected. A changed release can pair only if evaluator proves exact unchanged
validation membership/targets; otherwise return `incompatible` with bounded reason
and offer labelled side-by-side values. No normalization to conceal incompatible
units, no averages over failed/undefined trials, no zero-filled missing checkpoints.
Ranking excludes train-only metrics, exposed test evidence and incomplete required
coverage; tie-breaking and replicate aggregation are explicit study policy.

## Scientific data bridge and bounded support

Choose a lossless adapter-owned **input derivation artifact**, not a generic core
converter: an explicitly approved preparation Run consumes canonical scientific
release ZIPs plus immutable train/validation/test membership, and emits the NPZ,
splits, case-map and input receipt required by the captured pressure trainer.
Its manifest binds every release/member/array hash, whole scene/seed/family group,
exact field/stage/time/geometry/gauge/dtype, split role and output bytes. Its
source is a pinned lab-owned reader/packager closure. Core captures it through
existing `frozen_release` inputs; training consumes verified completed-Run outputs.
The preparation launch has its own exact grant, receipt and study budget charge.
No conversion occurs on data inspection or a client copying NPZ paths.

The current CNN reader accepts finite little-endian float64 cases with shape
(6,7,8), four RHS/x/y/z channels, 108 features, 16 hidden units and cell-zero
pressure. Reject other shapes, dtype, missing/unaligned RHS/pressure, family
leakage or changed gauge as unsupported/invalid before training. Output mapping
must be invertible to source case/geometry without inferred coordinates. Train
normalization records exact fit-case IDs; held-out changes cannot change it.
A code/source revision is required for 27-feature input or hidden width 32 until
an adapter qualifies typed options and restore changes. Current wrapper exposes
steps only; no invented learning-rate/seed option.

This bridge and recurring pressure checkpoints are **not implemented or qualified**.
The existing captured NPZ path remains supported only under its existing project
contract. New model-aware canonical-release pressure support stays unavailable
until its separate adapter producer/consumer qualification. D2 freezes the common
reference, custody and query envelope for the two worked semantics; it does not
freeze a universal scientific tensor/operator API. D3 may keep that integration
unsupported without invalidating classifier support, but cannot claim full
scientific automatic-evidence acceptance from authored arrays.

## Finite-study authority, budgets and cancellation

Retained study document is closed:
`{format:study_v1, id:Id, revision:Pos, name:Text(120), admission_epoch:Nat,
open:bool, state:draft|open|stopping|stopped|unknown, limits:Budget,
policy:Ref, membership_revision:Pos, trial_ids:[Id], stop_receipt_id:Id|null}`.
Membership is bounded to 10000 trials and persisted separately/atomically with
immutable trial rows. Study create starts draft, open=false, epoch=0, revision=1,
empty membership. Current reserved/charged totals are authoritative projections
of the same owner's reservation ledger, not independently editable study fields.
Every membership, reservation/settlement, policy, limit or lifecycle mutation
increments study revision under its lock, so paged reads can reject mixed states.

Selection policy is immutable
`{format:selection_policy_v1, metric_definition_sha256:Sha,
checkpoint_rule:selected|last|explicit, replicate_reduce:individual|mean,
required_capabilities:[Text(64)], numerical_acceptance:required|diagnostic,
tie_break:trial_id}`. Metric direction comes from its bound definition; mean
requires all explicitly declared comparable replicates defined/complete, never
drops failures/undefined trials. Explicit checkpoint selection is recorded in
candidate references, never chosen by response ordering. Numerical thresholds
remain task-evaluator owned; a study policy cannot weaken native acceptance.
A changed policy creates a new policy Ref and checked study revision without
rewriting earlier trial/candidate decisions.

Create/edit (`studies.save`) is owner-only inspect+edit for initial budget/policy
control; trial preparation may still be delegated to an inspect/edit agent.
Limits cannot fall below cumulative settled slots/wall/retained bytes plus open
obligations; peak-staging must cover currently open staging reservations.
Edit does not reopen a stopped epoch. Explicit owner `studies.continue` requires
inspect+execute, exact study revision/current epoch, confirmed cessation, no
unknown reservation, valid remaining budget/capacity and current policy. It
increments epoch, sets open=true/state=open and stores an idempotent receipt;
it launches nothing and grants no child execution. Initial draft uses the same
continue operation. Stop closes open=false immediately, then reports stopping
or stopped once all children drain; unknown children set state=unknown and fence
continue. Final settled charges use Nat values including zero released staging/
empty retained output; slots and conservative admitted wall stay cumulative and
never reset on continue. Peak-staging is occupancy, not a lifetime cumulative sum.

Initial supported execution remains local CPU with one Runs supervisor, one
active child and existing queue limit eight. No prospective/adaptive execution
grant is created. Study edits/selection use inspect+edit, start uses current
inspect+execute **and** owner-only authority for built-in Runs or an exact one-use
actor/material grant for external Runs, cancellation uses inspect+cancel, freeze
uses inspect+freeze, human review/approval remains owner-only. An agent can
prepare/propose/observe the built-in trial and request an owner action; no new
built-in execution delegation is silently selected.

Proposed immutable budget body:

```text
Budget = {attempt_slots:Pos, admitted_wall_seconds:Pos,
          retained_bytes:Pos, peak_staging_bytes:Pos}
Reservation = {id:Id, study_id:Id, admission_epoch:Nat, request_key:Text(128),
 actor_id:Id, trial_id:Id, parent_run_id:Id|null, run_id:Id,
 request_sha256:Sha, material_sha256:Sha, envelope:Budget,
 state:"reserved"|"running"|"settled"|"unknown", settled:Charge|null}
Charge = {attempt_slots:Nat, admitted_wall_seconds:Nat,
          retained_bytes:Nat, peak_staging_bytes:Nat}
```

`attempt_slots` counts every actual admitted training, derivation, evaluation, packaging or inference-verification
attempt, including failed/cancelled/retry attempts; reconciliation is not another
slot. Wall budget is the sum of admitted worst-case wall ceilings, including
automatic probe evaluation and drainage allowance; it is **not CPU/GPU time**.
Retained-byte envelope includes all outputs/evidence plus input/model/profile
captures charged conservatively for this attempt. Peak staging includes private
capture, worker scratch and publication duplication; shared runtime installation
bytes are existing provisioned capacity, explicitly reported separately. A
trusted-local recipe can allocate outside declared directories: this ledger is
an **admission/accounting bound**, not a kernel filesystem, memory, CPU/GPU quota
or sandbox. Current source has no enforceable aggregate CPU/GPU/RSS limits;
requests requiring such hard guarantees are unsupported. D3 measures selected
costs/capture defaults; D4 implements the declared bounded process/output controls.

For each dimension before admission, `settled_charge + sum(open_reservations) +
requested_envelope <= study_limit`. Initial conservative accounting settles each
attempt at its full admitted wall/slot envelope (including cancellation) rather
than trusting worker-reported usage. Verified retained bytes can settle downward
only after Runs proves terminal cessation/publication/cleanup; ambiguous writes
retain full reservation. Staging reservation releases only after proven cleanup;
retained bytes stay charged while material/evidence is referenced. This trades
utilization for enforceability without inventing a CPU meter or refunding failed
attempts. Changing study limits requires a checked owner edit, never automatic
increase by the tuning client. Existing admitted reservations cannot be lowered
out from under attempts; fail edit when new total is below obligated amounts.

Admission algorithm, with one owner-controlled outer transaction:

1. Outside transaction, inertly capture/validate the exact immutable Pipeline
   material and current runtime/source compatibility. No drift replacement on
   retry: current built-in `Runs.retry` revalidates installed runtime/source;
   an exact-material study retry must instead reject drift and create a new
   trial/material if the original is no longer runnable. No resume is promised.
2. Under existing catalog lock/transaction, reconcile `(catalog,actor,key,digest)`
   first; if committed return the linked Run/reservation without charging or
   consuming again. Recheck live actor/credential authority, study revision,
   admission epoch/open state, trial membership/material, current grant,
   capacity/queue and budget inequalities. Reject changed body/actor/key binding.
3. Reserve budget; consume exact grant where required; insert Runs attempt,
   bounded continuation, trial association and required audit **atomically**.
   Lock order is catalog/study then exact grant, consistent across stop/admit;
   Access must retain its post-grant-row-lock credential recheck. Unknown commit
   preserves captured bytes, reservation and authority ambiguity; it dispatches
   no speculative work. Reconcile through original receipt.
4. Runs registers an outer-commit wake, not an experiment-owned worker. Do not
   wrap today's public `Runs.submit`/`submit_external` in an outer transaction:
   those methods can call `_start` after a nested savepoint but before the outer
   commit. Introduce a **narrow Runs-owned admission seam** that accepts the
   existing transaction, stores the attempt and registers dispatch with
   `Metadata.on_commit`. No caller can spawn, replay or signal workers itself.
   Commit-callback ambiguity follows existing Metadata's confirmed-COMMITTED
   behavior; durable receipt/custody governs, not a blanket claim no process ran.
5. A cancellation/stop first commits `study.open=false` and increments its
   `admission_epoch`, under the same lock as admission. It then requests every
   admitted child cancel through Runs. A later admission from the old epoch is
   refused before grant consumption. Record stop receipt plus pending children;
   repeat stop reuses it and reissues only idempotent owner cancel requests.
6. Remain `stopping` until every known child has confirmed cessation and cleanup,
   even if a cancellation response or credential was lost. Unknown child/commit
   freezes new admissions and worst-case reservation; no refund/new grant.
   Reopen reconciles receipts/custody, never auto-launches stored proposals.
   Explicit continuation creates a new epoch with current authority/material/
   capacity/budget checks. Already admitted bounded effects follow existing
   Access continuation rules after credential revocation.

Read-only reconciliation identifies durable receipts without calling today's
`_reconcile_receipt` path if it can wake queued work. Explicit authorized
continuation may request that existing Runs wake only after all study invariants
are established. A stop can cancel queued work before spawn; a race already
committed before stop remains a charged child to drain, not an untracked launch.
D4 chooses fairness/polling/runtime details; this D2 seam and transaction rule are
foundational requirements, not an implemented scheduler.

Worked race: limit wall=10, no settled charge; clients A/B request 6/5 with the
same expected study revision. A commits 6 and a Run; B serializes later and
fails budget or stale CAS, consumes no grant, creates no Run. Lost A response
reconciles exactly A; new key is a new attempt requiring another 6 and fails
budget. If stop commits before A's transaction, A's old epoch is stale. If A
commits first, stop includes that Run and retains 6 until cessation/accounting.
If A commit is unknown, both budget and grant remain reserved/ambiguous; B and
new epochs remain fenced until owned reconciliation. Authored traces in the
[examples](examples/d2-contract-cases.json) are design arithmetic, not a measured
PostgreSQL concurrency proof.

## Discovery and compatibility transition

Current actual strict profile (read-only import observation): registry v1,
56 operations, digest
`cb070a69ebd35b48e4f95a57ca01647c75bd7567521429e49efc3a3a1daebae8`.
Current [AgentClient equality](../../../../agent_api.py#L558),
[agent contract](../../../contracts/agent-operations.md) and
[CLI](../../../../project_cli.py) bind its whole document. New negotiated clients
use authenticated proposed `GET /api/agent/capabilities`; no client code/routes
are downloaded or evaluated. Keep a single registry owner with two projections.

```text
CapabilityManifest = {format:"agent_capabilities_v1", envelope_version:1,
 catalog_id:Id, operations:[Operation], limits:{request_bytes:1048576,
 response_bytes:8388608, max_operations:256}}
Operation = {id:Text(80), contracts:[{version:Pos, sha256:Sha,
 input_schema:object, output_schema:object, scopes:[Text(40)],
 authority:"agent"|"owner", effects:"read"|"mutation",
 retry:"read"|"cas"|"receipt"|"never", bounds:object}],
 availability:"available"|"unsupported"|"unavailable"}
```

Manifest ≤1 MiB, schemas are closed Draft202012 fragments without external refs;
≤256 operations, ≤4 supported contracts each, unique IDs/versions. Each contract
hash covers canonical schemas, locally known method/path/projection, scopes,
authority/effects/retry semantics, semantic version and exact bounds, excluding
descriptive prose and current permission/availability. Version changes for changed
meaning; client selects an exact locally implemented `(id,version,hash)` intersection.
Unknown operations are ignored after bounded envelope validation. Malformed
envelope/catalog/auth/framing fails bootstrap; an incompatible operation affects
only itself. No schema-subsumption solver or global digest gate.

Selected calls carry reserved transport header `Tuldok-Operation-Contract` with
`id/version/sha256` plus normal operation args. MCP/CLI generate it internally,
not an agent telemetry argument. HTTP routes map it through the same registry
projection. Before body can enter a domain owner or consume an execution grant,
check the selected contract still supported and its exact request representation;
then run current authorization/revision/material checks. Mismatch is
`409 contract_mismatch` with no mutation/grant effect. Known compatible old contract
may continue during server additions. Output must conform to the selected
contract including failures; no response body automatically reinterpreted as another
version. Post-dispatch unknown result reconciles the original durable receipt.

**Selected bounded legacy transition:** retain `/api/agent/operations` as the exact
f58880df v1 projection/digest while supported strict MCP/CLI installations exist.
Headerless legacy calls use only those existing operations/grammars and current
Access guards. New model-aware recipe variants cannot enter old `graphs.save`
or old submit/read shapes; new operations/contracts own them. Reject missing
contract on new-only operations. Do not expose new tools through the legacy
projection or loosen it to fabricate equality. New clients fall back to that
exact legacy profile only on a definite unsupported capabilities endpoint
(404 route-not-found or 405), never 401/403/5xx/malformed response. The fallback
checks exact current legacy document/catalog and locally implemented operations.

| Actual consumer/state | Deployment / new-old disposition |
| --- | --- |
| `AgentClient`, `mcp_stdio.py`, `project_cli.py` | Independently launched installed clients; upgrade together per installation. Old/old remains exact; old/new uses frozen v1 projection; new/old uses bounded exact fallback; new/new negotiates operation contracts. Retire legacy projection only through an explicit versioned cutover after operator inventory confirms supported strict installations upgraded, with owner and release notice. Absence of passive logs is not proof of absence. |
| HTTP handlers and real browser workspace | Coordinated application bundle; new views use negotiated semantic endpoints, old deployed browser gets reload/unsupported result on a changed new contract. Retained data is not an old-browser compatibility promise. Keep legacy HTTP contracts while legacy calls are supported. |
| v1 classifier Runs, cold readers | Exact existing five payloads plus manifest; read using retained v1 decoder. No historical checkpoints/probes invented. New query maps to `historical_unsupported` with available selected predictions, never upgrades retained payload bytes. |
| New model-aware classifiers | Distinct adapter/recipe/evidence version with all producer, Runs verifier, schema/agent/UI/backup consumers updated together. Old v1 tools cannot edit/start them. Retained v1 standalone training remains usable. |
| External recipes/project roots | Preserve project schema1/external_recipe_v1 and exact capture. New evidence only as declared bounded outputs with qualified task contract; unknown evidence stays opaque downloadable artifact, never automatically accepted metric. Versioned project/recipe pins keep original source closure. |
| Scientific field/release readers | Preserve `scientific_field_sequence_v1`, dtype/geometry/time/family semantics. Bridge artifact is separate, never rewrite scientific bundles or move physical operators into core. |
| Artifact/CLI downloads | Preserve segment and whole-hash distinction. New semantic query is bounded structured data; package downloads use existing verified byte custody. Old artifacts do not become inference packages. |
| Metadata/backup/restore | New writer requires explicit new catalog migration; old binary refuses unknown schema. New reader preserves old states/cold meaning. Stop writers, complete backup, atomic upgrade, verify exact definition/signatures; D4 DDL and cutover tests required. |
| Authorization/exposure/audit | Same current Access/domain owners for every view/query/count/artifact/export/cache. Generic test input is denied pending protected-population policy below; optional recorder cannot grant access or replace required audit. |
| Observer v1 | Existing operator store/config stays opt-in and unchanged; no in-place guessed schema migration. Extended boundary observations require explicit operator v2 store selection/rotation as specified in agent requirements. |

Retirement of compatibility is an owner decision based on supported consumers,
not a timer, repo-wide latest-version preference or maintaining every historical
client forever. D4 implements/qualifies the transition atomically; D2 did not
change registry behavior.

## Lifecycle, protected evidence and package closure

New immutable published evidence survives service/catalog reopen using its
retained decoder/material/task contract, without reading live project source or
probing today's runtime. Current permission is still checked. Unknown evidence
version returns unsupported, missing/tampered artifact unavailable; neither selects
a newer file. Unsupported cold decoding is not an invitation to execute historical
source. Checkpoint inference/replay requires an explicitly authorized consumer
Run; cold inspection only decodes bounded declared data.

| Failure/window | Required state and reader behavior |
| --- | --- |
| Before admission commit | No authorized execution; ordinary rollback restores reservation/grant. Private orphan bytes follow preparation reconciliation, never public evidence. |
| Lost admission acknowledgement | Return unknown, preserve bytes; read original actor/key receipt before any retry. A proved existing Run is returned without another grant/charge. Never auto-resubmit a new key. |
| Worker running/partial output | Only bounded live-unverified progress/status; no published checkpoints from mutable staging. Cancellation keeps evidence unavailable until final state; terminal cancelled/interrupted has no complete new evidence result. |
| Successful worker, incomplete/invalid required evidence | Runs/evaluation publication fails; attempt is failed, quality false. Do not publish half a checkpoint matrix or choose a candidate from it. |
| Complete verified publication | Publish immutable manifest/index and query snapshot atomically with completed Run. Current access and artifact integrity still checked on serving. Domain numerical rejection stays a separate outcome. |
| Crash/reopen or unknown child | Use retained custody, receipt and existing supervisor recovery. No auto-launch/replay and no SIGKILL inference of success. Unknown child fences further admission and retains worst-case reservation. |
| Optional evidence/capture omission | Only if protocol marks optional and resolved budget permits it; return typed omission. Required omission cannot be hidden as optional on reopen. |
| Access revocation or hidden test | Deny new read/launch at trusted boundary; already admitted bounded effects retain current continuation rules. Cache keys include actor/catalog/access context; caches are reauthorized and cannot disclose data through counts/extrema/errors. |

**Protected populations:** preserve classifier's existing expose-holdout flow and
content/family exposure ledger. For new generic scientific profiles the initial
policy is stricter: training and automatic queries accept train/validation only;
test material is excluded from the admitted training capture and query inventory.
An explicitly separate evaluator Run may consume test only after an owner
material grant **and** expose-holdout authorization whose durable transaction
records the canonical whole protected families before returning any derivative.
Access/domain owner must extend exposure lineage to exact scientific case/family
and captured derivation inputs; no arbitrary external file is inferred safe.
Until that extension is implemented/qualified, generic protected-test evaluation,
queries, counts, scales, preview/export/cache are unsupported. Enforce transitive
protection at **all** Runs accessors: whole artifact, segment, capture-as-input,
import, semantic query, summaries and package export. A mixed NPZ/JSON/ZIP inherits
the union of protected populations; deny the entire blob until disclosure, or
require the producer to split train/validation/test artifacts. Protecting the UI
while allowing the same mixed file through `runs.artifact_chunk` is invalid.
Current external artifact access does not supply this classifier-style protection;
new protected support cannot be advertised until that cutover is qualified. Existing optional
historical recipes retain their disclosed limitations; they are not retroactively
upgraded to untouched holdouts. No legacy lab NPZ is relabelled a protected release.

Candidate package body `{format:inference_package_v1, candidate:Ref,
checkpoint:Blob, model:Blob, sources:[Blob], transforms:[Blob], task:Blob,
inference_entry:Blob, runtime:{contract:Blob, provision:"included"|"external"},
evidence:[Blob], lineage:Blob, probes:Blob|null, expected_outputs:Blob|null,
licenses:[Blob], inventory:[Blob], limitations:[Text(500)]}` must include the selected checkpoint descriptor **and its exact weight Blob**
and close every inference dependency and explicit external runtime/probe input. Inventory has no
self-hash; outer Run artifact manifest binds it. No live checkout, default class
order, fit statistics or model cache may be required. Training data may remain
protected lineage references; export cannot disclose them by accident. A package
without permitted fixed probes/expected outputs is package-complete only for
inference dependencies and explicitly `verification_pending`, never fresh-consumer
verified. Candidate permission does not authorize loading code or training. Packaging is
an ordinary declared captured recipe/trial: prepare exact candidate closure with
Pipeline, reserve the same study budget, then have the owner review and call the
existing `Access.grant_execution` semantics for that material/consumer. The
convenience package operation pins the prepared trial/material explicitly; it
does not pick latest, mint a grant or create a second admission path.

Future verification uses an authorized separate Runs consumer of the actual
exported whole-hash-verified package plus explicitly compatible runtime/probes.
Fresh process has no live catalog/project/model cache; reconstruct inference and
compare expected outputs under evaluator-owned tolerances, reject missing/wrong
transform/class order/gauge/runtime/tampered checkpoint. Store verification result
as separate evidence; optional physics evaluation is independent and can fail.
D3/D4 specify UI/procedures and exact implementation; none ran in D2.

## Worked valid/invalid cases and D2 acceptance boundary

[Authored cases](examples/d2-contract-cases.json) are small design examples with
synthetic identities/values. They exercise the following consequences, not a
production validator or training campaign:

| Valid case | Single invalid change | Required result |
| --- | --- | --- |
| Same classifier validation probe/class order at end epochs 1 and 2 | Observation references epoch-1 checkpoint while naming epoch-2 weights | `invalid checkpoint_binding`; no evidence publication or paired view. |
| Two full validation rows with probabilities [0.8,0.2], [0.4,0.6], identity truth | Change vocabulary order without target/prediction index update | `invalid class_binding`; confusion and accuracy cannot silently agree under another class order. |
| Pressure RHS/x/y/z 108×16 model with train-only fit cases | Include a validation case in normalization fit IDs | `invalid transform_population`; reject inference/evidence binding. |
| Pressure comparison same grid/stage/time/cell-zero gauge | Same-shaped prediction declares another gauge or different stage | `incompatible`; no paired error or physical acceptance. |
| Reference [0,1,2], prediction [0,10,20], same units/mask | Independent autoscale disguises amplitude; numeric relative-L2 still 9 | View procedure must expose error; a visually similar pair cannot pass numerical acceptance. |
| Metric reference includes both exact checkpoint hashes (validation loss .8→.5 versus .8→.7 yields deltas −.3 versus −.1) | Omit right checkpoint and let index order choose | `invalid ambiguous_checkpoint`; no default delta. |
| Paired pressure reference nonzero | All-zero reference denominator | `undefined zero_reference_norm`, no NaN/zero metric. |
| Exact operation digest on discovery and dispatch | Server changes requested contract after discovery | `contract_mismatch`, zero domain/grant/budget effect; unrelated compatible query works. |
| Two attempts reserve 6 and 5 against total 10 | Admit both concurrently | At most one commits; serialized reservation inequality fails the other before grant consumption. |
| Lost acknowledgement with same actor/key/body | New key or changed contract/body used to retry | Original receipt reconciliation only; changed identity conflicts or becomes a separately approved attempt. |
| Cold manifest binds original model/probe/fitted values | Live draft/source changes while catalog is closed | Original verified values unchanged; no live source lookup or synthesized history. |

D2 acceptance requires the concrete contracts, consumer dispositions, failure
examples, observation/audit policy and independent review. Real producer checkpoint
capture costs, pressure bridge/numerical interpretation qualification and browser/
agent product acceptance stay pending D3/D4 or later implementation. The design
remains valid by keeping unavailable scientific/test capabilities unadvertised;
this is not a claim of generic-interface or physical-quality qualification.
