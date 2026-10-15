# Model definitions and finite studies

Pipeline owns editable execution configuration and immutable compositions. Model
Definitions owns architecture/source and preprocessing/output policies. Runs owns
attempts, fitted state, process custody and published bytes. Experiments owns
finite membership, limits and selection intent; it never spawns a worker.

This first implementation supports inert captured external source and exact
finite external attempts. A model-aware classifier template, automatic evidence,
scientific interpretation, candidate selection/package and fresh inference remain
unavailable until their P3–P5 qualification. An opaque external result does not
become a checkpoint, scientific observation or numerical acceptance by attaching
model metadata. Existing built-in training remains owner-only and unchanged.

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
  supervisor/drainage margin; captured CPU includes its second verification phase.
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
checks syntax, identity, bounded layout and revision CAS. Trainer/model/task
semantic qualification and v2 execution compilation remain unavailable until P3's
actual producer gate; saving a draft never asserts it is executable. Existing
external graphs can prepare exact captured-source trials through the qualified
external execution contract described above.

The shipped `project_cli.py ... call --operation ... --arguments ...` command
inspects these registered model/material/study operations through the same client.
Study/membership/operation-receipt documents share an explicit1MiB owner bound,
large enough for the declared10000-trial membership, checked before publication.

Study execution uses the dedicated owner `studies.approve` action. It verifies
an exact member trial's complete retained composition and current executable,
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
