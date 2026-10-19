# Model definitions and finite studies

Pipeline owns editable execution configuration and immutable compositions. Model
Definitions owns architecture/source and preprocessing/output policies. Runs owns
attempts, fitted state, process custody and published bytes. Experiments owns
finite membership, limits, selection intent and [experiment lineage](experiment-lineage.md); it never spawns a worker.

This implementation supports inert captured external source, exact finite external
attempts and the separately versioned model-aware TinyCNN classifier described
below. Scientific interpretation and candidate package/fresh-inference claims
require their separate qualification. An opaque external result does not become a
checkpoint, scientific observation or numerical acceptance by attaching model
metadata. Built-in training remains owner-only; legacy image outputs keep their
original closed contract.

## Model and material custody

`models.create/get/list/save/publish/material` use bounded strict JSON and current
inspect/edit authority. Save requires exact revision CAS. Publish retains original
source and recipe-definition bytes (at most64 files/8MiB including the definition),
separate policy JSON, catalog/model/revision identity and an immutable SHA256 body.
It never imports project source, loads weights or runs a process. Fitted weights
and statistics belong to Run artifacts, not a definition's editable policy.

Pipeline prepares the exact saved external graph against a published model's
same source selector and byte inventory. Its immutable `recipe_material_v1`
contains the complete saved recipe/preflight, captured inputs/source, model Ref,
trainer/profile/runtime identities and conservative resource envelope. Project
inputs retain their existing typed receipts; `data:[]` means no frozen release
Ref and does not invent one. The initial profile is explicitly opaque outputs,
with automatic checkpoints and numerical evidence unsupported. No live default
or mutable latest pointer determines a retained trial.

Stage/hashing runs outside the final catalog transaction. Trial attachment,
material publication, immutable membership and required audit share one outer
transaction. Files are private, synced and renamed into owner custody; ordinary
rollback removes only new unreferenced files. Unknown commit retains them. Reads
bind actual rows and exact inventories, reject duplicate/nonfinite JSON, symlinks,
hardlinks, special files, changed stat identity, sizes and byte hashes. Restore
preserves historical absolute execution paths as evidence and never replays them.

A repeated unchanged preparation key returns the same trial before re-reading
new drafts/source. Other inputs conflict. If an ambiguous publication left bytes
without a row, an owner may explicitly set `reconcile_capture:true`; the owner
compares every byte/inventory outside the transaction and rechecks directory
identity before attachment. Ordinary retries cannot adopt an orphan or delete it.
There is no automatic material garbage collection.

## Finite authority and accounting

Study creation/save and continuation require the current owner. A study starts
closed, draft, epoch0 and empty immutable membership. Initial/next continuation
is an explicit receipt operation, increments epoch and launches nothing. Trial
preparation can use current inspect/edit delegation. Selection policy is immutable
intent; it cannot qualify an unknown metric/task or weaken a task evaluator.

`studies.admit` accepts one exact member trial, current study revision/epoch,
stable request key and optional exact external approval/retry parent. It rechecks
current inspect+execute credentials and exact one-use actor/material approval.
A study, policy, trial or capability is never execution permission. The shared
Runs queue remains8 with one child; a study admits at most one live child. There
is no adaptive grant, second queue, scheduler, automatic retry or resume.

Admission uses one outer catalog transaction: reconcile original actor/key/body
and operation-contract identity; check study, child cessation, queue and limits;
insert conservative reservation; consume grant; insert Run and bounded continuation;
link trial; update revision; write required audit. Any ordinary failure rolls back
all of these and new staging. The request hash includes the actual selected
`studies.admit/1` contract SHA256; another meaning cannot reuse its receipt.
Reconciliation reads an existing receipt before capturing new bytes or charging.

Only normally acknowledged outer commit may wake Runs. psycopg's COMMITTED enum
alone is insufficient: it is set before its COMMIT generator finishes. An actual
committed-but-unacknowledged admission retains reservation, consumed grant and
files, with no speculative wake. A later delivery failure after acknowledged
commit may follow an already dispatched bounded effect. Inspect the durable
receipt; never automatically repeat a mutation.

All resource/revision counters use exact integers0..2^53−1 (positive where
required). Admission requires charged+open+requested<=limit in all dimensions:

- Every admitted attempt, including failed/cancelled/retry, consumes one slot.
- Wall charge retains the declared process ceiling plus READY allowances and15s
  supervisor/drainage margin; captured CPU and managed Torch include their
  separate runtime-verification phase, selected by the same custody-owner
  `preparation_seconds` and `verification_seconds` functions as actual execution.
- Retained bytes conservatively include captured source/input/model/profile,
  declared outputs, two bounded stdout/stderr streams and custody/manifest margin.
- Staging reserves capture duplication and output publication duplication. Shared
  provisioned runtime installation bytes are separate existing capacity.

Settlement keeps the full admitted charge, including staging while its directory
is retained. This initial implementation performs no automatic cleanup/refund;
limits may be increased only by a checked owner edit and never below obligations.
Unknown children keep full reservation and fence admission/continuation. These
are admission accounting bounds, not OS CPU/GPU/RSS/disk quotas or a sandbox.
Trusted same-user source may write outside declared directories; hard aggregate
resource guarantees remain unsupported.

Stop first commits closed admission and incremented epoch, then calls the existing
Runs cancellation owner. Its durable receipt binds the exact children at that
stop, so repeating an old stop cannot cancel children of a later reopened epoch.
The study remains stopping until known cessation, unknown if custody is uncertain.
`studies.get/list/trial` are inert reads. Explicit `studies.reconcile` updates only
owned derived accounting/lifecycle from Run custody; it never wakes or replays work.

## Public compatibility and storage

New operations live in the existing `agent_api.py` registry and require exact
selected contract headers before domain entry. New output bodies are typed in
that registry. Owner-only operations advertise `authority:owner`; access remains
checked by the owner. The existing AgentClient/MCP still requires an agent
credential. Owner actions use the authenticated selected HTTP projection; adding
owner operations does not widen the agent credential's authority. Existing actual
56-operation legacy discovery bytes/digest stay frozen. Unrelated compatible
operations remain available.

Metadata schema9 adds separately owned draft/material/policy/study/trial/
membership/reservation/candidate/receipt rows. Schema1–8 definitions remain exact.
Ordinary startup never migrates. Stop all writers, retain complete schema8 backup,
then run `python upgrade_metadata.py CATALOG --quiesced`. New domain tables start
empty; old rows/files/grants/results are not rewritten or backfilled. Complete
backup/restore includes all new rows and byte custody, using Metadata's DDL order
for foreign-key insertion. Restore targets a new absent schema/directory. An old
schema backup restores exactly, then requires explicit upgrade; downgrade uses
the complete stopped backup.

Passive observation remains optional and separate from mandatory transactional
Access audit and task-owned training/evaluation evidence. No per-agent logging
or telemetry configuration is required for this workflow.

The public `recipes.create/get/save/list_drafts` operations retain the closed
Pipeline `recipe_draft_v2` format separately from legacy graphs. Draft storage
checks syntax, identity, bounded layout and revision CAS. The generic
`recipe_draft_v2` execution compiler remains unavailable; the qualified classifier uses the explicitly selected `image_classification_model_v2` closed
graph contract. Saving a generic draft never asserts it is executable. Existing
external graphs can prepare exact captured-source trials through the qualified
external execution contract described above.

The shipped `project_cli.py ... call --operation ... --arguments ...` command
inspects these registered model/material/study operations through the same client.
Study/membership/operation-receipt documents share an explicit1MiB owner bound,
large enough for the declared10000-trial membership, checked before publication.

External Study execution uses the dedicated owner `studies.approve` action. It
verifies an exact member trial's complete retained composition and current executable,
then issues the existing one-use actor grant for the **RecipeMaterial SHA256**.
A legacy executable-only grant cannot authorize Study admission. A changed model,
policy, task/profile or captured dependency requires its own composed approval.
The Runs seam separately preserves executable/custody material identity and
`approval_material_sha256`; cold reads bind the retained grant and immutable
Study/Trial association. Standalone external approval behavior stays unchanged.
The original Study-scoped request key is retained in its reservation; Runs receives
a deterministic namespaced key to satisfy its existing catalog-wide uniqueness.

Collection reads are bounded: models and recipe drafts return up to20 documents
with an ID cursor; Study lists return up to20 summaries. Study details return up
to100 reservations with explicit offset, next offset and Study revision. Every
later reservation page must provide the same revision; changed state returns
stale instead of combining pages from different accounting states. Totals cover
the whole ledger independently of page contents. Stop receipts retain only the
exact current unceased/unknown children, so historical attempts cannot make stop
unbounded. Settled charges remain equal to the original conservative envelope;
cold receipt/accounting reads reject altered row/Run/material or lowered charges.

For external compositions, `RecipeMaterial.executable_sha256` hashes the complete
compiled external preflight material, including runtime/source/input/parameter
identities. It is distinct from the graph execution digest retained inside that
preflight and the Run. Snapshot validation closes graph→preflight→composition;
Runs checks the same exact preflight SHA at admission and cold reopen. An internally
consistent replacement runtime/spec cannot ride an earlier composition approval.

## Automatic classifier vertical (P3)

`image_classification_model_v2` adds the qualified TinyCNN template and automatic
D2 evidence without changing the legacy image recipe. Pipeline definitions expose
an inert `model_template` creation body. After saving typed architecture parameters,
`graphs.validate` resolves the exact frozen release, source/runtime and
`selection_policy`: its MetricDefinition digest binds validation membership,
class order, evaluator and preprocessing. A release-independent placeholder digest
cannot select a candidate. Model publication remains inert and template sources
are captured by the same Model Definitions custody owner.

`studies.prepare_trial` selects built-in or external preparation from the exact
saved graph. Built-in material retains model, frozen data release, resolved profile,
runtime and adapter sources with its conservative envelope. Study admission and
reservation remain one transaction and wake the existing Runs owner only after a
normally acknowledged commit. Built-in execution retains current owner-only
authority; delegated inspect/edit access and external source grants do not widen it.
Studies never create a second runner, implicit retry or scheduler.

Automatic classifier evidence is task-owned and published only after complete
artifact verification and actual per-checkpoint CPU inference reconstruction.
The common manifest/index/clock/checkpoint/probe grammar follows
[evidence-contract-design.md](../plans/end-to-end-model-development/reports/evidence-contract-design.md).
Structured model evidence and comparison queries expose the same verified bytes
to humans and agents. A v1 Run reports unavailable historical evidence honestly.
Candidate packaging/fresh-consumer qualification remains a separate P5 gate.

`studies.select_candidate` retains an immutable `candidate_v1` from an actual
Study reservation, a verified checkpoint, the exact emitted metric definition
and the captured selection policy. Concurrent identical request keys reconcile
one receipt. Candidate reads recheck current authority, task evidence and policy.
The current classifier evaluator supplies diagnostics only: a successful fit is
not a model-quality threshold. Required numerical acceptance and mean-replicate
selection remain unsupported; export cannot upgrade that decision.

## Built-in artifact input provenance

Qualified `image_classification_model_v2` publications may become exact captured
recipe inputs through `Runs.capture_artifact`. This operation verifies the
completed Run's full published artifact inventory and applies the ordinary
artifact permission/holdout guard before returning bytes. Whole mixed releases
are excluded. This is a byte-publication proof and does not grant execution,
transfer distribution rights, or assert that a historical permission is current.

The distinct source schema2, kind `builtin_classifier_publication_v1`, records
catalog/Run/request/material/graph/release/adapter identities, exact artifact
name/role/size/hash, population, and the actual verified `artifact-manifest.json`
bytes in canonical base64 plus their SHA256. The retained decoder checks source
identity, qualified adapter version, selected manifest item, and measured input
bytes. It does not fabricate an external custodian or drainage receipt. Existing
schema1 external Run source receipts retain their exact custody contract.

Transitive current permissions and protected-population disclosure are checked
again on derived access; a captured source receipt alone cannot authorize a
package export, import, query, segment read, or derivative summary.

## Candidate package and fresh inference (P5)

`candidate_packages.py` implements the exact `inference_package_v1` body from D2.
The checkpoint descriptor includes its exact weights Blob. Its immutable candidate
bytes bind the selected Run, checkpoint and evaluation; the retained published
ModelMaterial binds every source import and each specification/preprocessing/output
policy. An inventory entry alone cannot replace those cross-file identities.
Candidate, runtime and published model catalog identities must agree. Expected
probe truth indexes are exact integers in the frozen class range and hash to the
retained fixed probe targets; copied source artifacts retain their lineage hashes.

The classifier package includes only explicitly selected validation PNG probes,
expected probabilities, fixed probe membership, fitted transform, model and task
contracts, source closure, runtime contract, decision/evaluation/lineage and rights
inventory. Training and holdout records remain permissioned references. Unknown
or mixed protected populations are unsupported for this profile. Every included
material has an explicit rights disposition. Unknown rights allow the owner's
local/private workflow and deny redistribution; no permissive license is inferred.

Preparation selects an existing configured Projects root and a new flat directory.
The owner helpers prepare a declared packaging or captured CPU verifier graph,
its captured operation model and an exact member Trial. Preparation returns the
proposed Trial/material without granting execution or starting a process. Repeated
actor/request keys return the same durable receipt. Existing `studies.approve`
and `studies.admit` provide exact material approval, conservative budget charging,
Run custody, reconciliation and cancellation. No second runner or implicit retry
is added. Package source Run inputs remain explicit captured bindings so every
current derived accessor can reauthorize their transitive populations.
These helpers reject an existing caller metadata transaction before capture or
directory creation. Trial publication and the helper receipt share the final short
transaction. Rollback owns cleanup after publication begins; a failure returning
an already committed result preserves the retained project for exact replay.

The verifier requires an existing approved `captured_cpu_python_v1` snapshot.
Its runtime contract uses the RuntimeSnapshots owner, including exact Python,
packages, transitive native files and notices. The fresh consumer reconstructs
the declared TinyCNN topology independently, applies PIL bilinear RGB resize and
CHW float32 division by255, loads weights-only state with strict keys and compares
fixed probabilities under evaluator-owned `atol=1e-6`, `rtol=1e-5`. It imports no
training adapter, live checkout, model cache or torchvision implementation. It
independently recounts confusion, accuracy and macro F1. Physical validity and
training resume remain separate unsupported claims.

Candidate decision, `package_complete` and `fresh_verified` are distinct states.
Construction reports `verification_pending`; only a separately completed admitted
verifier Run supplies fresh verification. Inspection and state queries decode
bounded data and never execute captured code. State collection is scoped to the
candidate and bounded; unsupported collection size returns a typed outcome.

The standalone checkpoint is:

```
python tests/qualify_candidate_package.py --package /tmp/export/package.zip \
  --runtime /catalog/runtime-snapshots/SHA/python/bin/python3.12 \
  --expected-sha256 PUBLISHED_PACKAGE_SHA --mask-path /original/checkout \
  --mask-path /original/model-cache --output /tmp/fresh-inference-qa
```

The qualifier first verifies the entire downloaded artifact against the published
SHA, then starts the approved runtime through its captured bootstrap in a private
working directory. `--mask-path` requires bubblewrap and separately verifies the
named original directories are empty in the consumer filesystem. A sibling
`package-result.json` may provide the expected published SHA when the explicit
argument is omitted. The qualifier does not reinterpret public redistribution
rights or a diagnostic candidate as a quality qualification.

For the actual producer-to-consumer qualification, explicitly provision a
disposable catalog and captured snapshot, then run:

```
TULDOK_TRAINING_PYTHON=/qualified/training/python python tests/qualify_candidate_package.py \
  --production-catalog /disposable/catalog --snapshot-descriptor /tmp/runtime-descriptor.json \
  --output /tmp/charged-package-qa
```

This driver performs actual two-epoch training, immutable candidate selection,
normal package and verifier preparation/approval/admission in one finite Study,
HTTP download and whole-hash verification. It records three charged attempts and
observes that expensive external capture runs outside a metadata transaction.
The authored RGB fixture qualifies the execution/evidence contract rather than
classifier generalization. `test_candidate_packages.py` separately exercises
real PostgreSQL publication-callback failure and rollback; its optional actual
CPU case requires explicit qualification catalog/snapshot/output/runtime settings.

The separate `Candidate package captured CPU` CI job provisions its supported
Python/Torch CPU environment explicitly before running any qualification. After
the actual model browser gate stops, `tests/prepare_candidate_runtime.py` runs in
that environment and writes a closed RuntimeSnapshots config, the complete
reviewable inventory, exact package versions/source hashes and `runtime.env`.
The helper installs nothing and does not capture a snapshot. The existing
`browser_candidate_package.cjs` passes that config and exact inventory SHA to
`runtime_snapshots.py create --quiesced`, then exercises preparation, approval,
charging, download and fresh inference through the ordinary UI.

This fixture selects the qualified Torch/NumPy/Pillow inference subset and its
upstream metadata/notices. It excludes the unused torchvision distribution,
functorch native extension, Torch native tests/test data and optional tkinter
extension. Those explicit exclusions precede inspection; an unsupported ELF or
missing dependency fails the job instead of triggering further exclusions.
It preserves the existing CPU profile, loader checks and rights disposition.
Its locally measured manifest may differ on a separately provisioned CI host;
each run freezes its own full inventory before ordinary capture and inference.

## Explicit scientific A package profile

`package_scalar_a_task_v1` is a separate, explicitly frozen package task inside
the unchanged `inference_package_v1` envelope. It accepts only the nominated
`example.scalar-a:task` revision2 / fixed-validation profile revision2, source
authority057c8ab, author inference source `cdfdf92c...95d98eb` and whole contract
`468e3e15...78717fe`. A second literal nomination accepts adapter revision2,
contract `9588ee26...02f7dd8`, source `b77face4...49acc2c` and recipe
`4cebb6b2...d233508` only with captured runtime `50502c0b...0ffe3d` and the
separate author-owned `inference-v2-private-qa` source directory. The original
nomination stays intact. Other field tasks, source variants, gauges and adapter
entrypoints remain unsupported. The classifier task and its v1 receipt retain
their existing contracts.

The scientific candidate evaluation is the actual retained `model-evidence.json`,
not a host-created metrics file. Its selected checkpoint descriptor, four retained
16/32/48/64 descriptor/field pairs, exact little-endian float64 weights, training
transform state and fit member identities, permitted initial/reference arrays,
task/profile/policies/geometry/gauge, published material, six owner-captured
source imports (five author sources plus recipe definition), frozen inference
source/contract/notice, captured CPU runtime and permissioned artifact lineage
are retained. Private training fixture values stay outside the package. Private
QA rights deny redistribution; no license is inferred.

Cold inspection decodes bounded JSON and native NPY data without importing the
author adapter. The approved consumer derives its three raw-file request hashes
from the selected descriptor weights, fitted-transform state and permitted input
Blob. It separately binds the input's field-payload identity and reference target
to the fixed probe. The D2 input identity is not a raw NPY file hash.

After ordinary exact admission in the existing captured CPU profile, the consumer
imports only the exact pinned author inference source and compares native output
values using the frozen author/oracle `1e-10 +1e-10*abs(expected)` rule. The host
implements no scientific model, fitting, MSE or physical acceptance operator.
`fresh_field_inference_verification_v1` reports this reconstruction separately
from independent numerical/physical acceptance and training resume. No generic
untrusted executable hook or implicit runtime compatibility fallback is added.

The downloaded-package qualifier can require `--expected-profile scalar_a`.
For an existing real producer candidate with an approved registered runtime,
`--production-catalog`, `--snapshot-descriptor`, `--source-study` and
`--source-candidate` prepare and admit two ordinary charged package/verifier
attempts, download the package through HTTP and retain the new receipt.
`--field-limits` names an explicit finite budget JSON when the original Study
needs two additional attempts. After confirming all children have ceased, the
qualifier uses ordinary owner stop/save, retains the original limits and actual
amendment response, opens a new epoch and obtains new exact package/verifier
grants. It never changes a budget after failed admission or reuses a source grant.
The authored `test_scalar_candidate_packages.py` states are boundary fixtures;
they are not completed Runs or E4 acceptance. Actual E4 producer/package evidence
and any separately nominated runtime/source variant remain required.


## Bound field evidence with managed Torch

The existing current bound recipe (`schema_version:3`,
`external_model_evidence_recipe_v2`) accepts `managed_torch_python_v1` with an
explicit `cuda` or `cpu` device and its exact measured manifest identity.
Managed execution retains its own descriptor/bootstrap, runtime origin checks,
finite deadlines and CUDA visibility policy. It is never relabeled as a captured
CPU snapshot. Unbound model-evidence variants and native-source combinations
remain unsupported for this managed field profile.

Project v2 can also declare ordinary `external_recipe_v1` managed Torch recipes.
Their source, recipe and Project data reads use current rooted snapshot capture,
including the unchanged manifest proof before/after capture. This permits the
same current project to hold a typed CUDA trainer and an ordinary fresh CPU
restore recipe. It adds no old-manifest decoder, alias or alternate runner.

An exact Model source selector still binds its selected recipe and provider
closure. Trial composition identifies the measured managed descriptor, rather
than the bootstrap system Python, and reserves both readiness and runtime
verification before admission. The same existing finite Study budget, owner
grant, attempt context, immutable captures and drained artifact publication apply.
The bound context remains one exact read-only argument of at most64KiB and is
reverified after child drainage. Inspection and Model/Trial preparation never
execute the trainer or load model arrays.

The pressure migration authoring helper is the lab's
`experiments/dependency-migration-v1/typed_pressure_project.py`. It assembles a
fresh current project from exact captured trainer bytes, task-owned tensor
ports and scalar physical context, the unchanged evidence SDK, and one explicitly
previously consumed validation frame. The large measured runtime manifest is an
explicit Project data reference while the managed runtime owner retains its own
exact bootstrap manifest. This keeps the provider/Model source closure within
8MiB without changing runtime identity, data custody, numerical values or bounds.
Its `assembly.json` records source-to-current paths/hashes and actual new Project
identity. Assembly and static Model publication make no optimizer, acceptance or
historical ancestry claim.

This profile keeps the existing fixed validation population and evaluator
semantics. Pa, exact float64 ZYX geometry, solved-prior lineage, the gauge, float32
network compute and pressure reconstruction are declared by the pressure task
and captured source. Structural field verification is distinct from numerical or
physical acceptance; a diagnostic Trial cannot promote a model automatically.

The fresh CPU restore stays outside the bound evidence profile. It consumes the
training Run's exact artifacts through ordinary `run_artifact` receipts and
existing transitive authorization/custody. The restore evidence explicitly links
the training Model, Trial, Run and checkpoint hashes; no extra restore Model or
validation-population capability is invented. Historical Runs keep unknown
ancestry. Bound field profiles continue to reject unsupported Run/frozen inputs,
including unused inputs. Untouched holdout access remains unsupported.

The separately negotiated [scientific comparison](scientific-comparison.md)
reads exact completed and recovered field evidence in the existing Runs and
Experiment progression UI. Per-case field-point diagnostics remain distinct
from scientific acceptance; the current profile has no owned per-case criterion.
