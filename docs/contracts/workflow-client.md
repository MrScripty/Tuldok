# Consumer workflow client

`tuldok_client.WorkflowClient` is a small synchronous consumer facade over the
existing negotiated `AgentClient`. It opens no catalog and imports only the
standard library; JSON Schema is loaded lazily by operation validation. Use the
[existing private configuration](agent-operations.md) and provisioned validator.
Each facade exclusively owns its AgentClient during a workflow; do not share one
instance concurrently. No extra routine client dependency is required.

The facade exports plain, deterministic JSON documents. They contain catalog,
operation, exact arguments and SHA256, never credentials. A checksum detects
changed identity; it is not a signature, grant or scientific approval. Inspect
and retain exported manifests before an effect. Grant issuance, Study budgets,
runtime installation, scheduling and scientific acceptance remain server-owned.

```python
from tuldok_client import WorkflowClient

workflow = WorkflowClient.from_config('/private/agent.json')
manifest = workflow.submission_manifest(graph_id, revision,
    approval_id=existing_grant_id, request_key='lab-attempt-0001')
# Inspect/export manifest, then explicitly submit.
submission = workflow.submit(manifest)
```

`submission_manifest` reads the selected exact external preflight and verifies its
material digest/catalog/revision. The existing owner grant still has to authorize
that exact material at admission. `trial_submission_manifest(trial_id, ...)`
reads the retained Trial and current Study revision/admission epoch and exports
`studies.admit` with that Trial, grant and stable key. Optional `parent_run_id`
uses the existing explicit attempt relationship. Neither builder changes state.

`submit` dispatches once. It returns `workflow_submission_receipt_v1` with the
unchanged manifest and `acknowledged` plus the server status/result envelope,
`refused` plus a definite server refusal envelope, or `unknown` plus a bounded
client/server error. Server 5xx and `commit_unknown` remain uncertain. A later
authorization/refusal during explicit reconciliation is retained as a bounded
`reconciliation` observation on the original unknown receipt, because it cannot
prove the earlier admission had no effect. Only an exact positive acknowledgement
resolves this facade's unknown outcome. A transport/decoding failure after
dispatch is uncertain even when the
server may already have committed. There is no automatic retry. Retain the
receipt and explicitly call `reconcile(unknown_receipt)` with exactly the same
catalog, operation and body. This invokes the existing same-key receipt owner;
it never creates a key or adopts an alternate dispatch path. Conflicting bodies
remain conflicts. A bootstrap/negotiation failure before dispatch raises
`AgentAPIError` and performs no submission.

`monitor(run_id, timeout=60, cancelled=event)` polls only `runs.get`, with a finite
positive overall budget (at most one day), exponential delay capped at five
seconds by default (configurable up to 60 seconds), and one AgentClient read
budget shared across initial registry validation, all
bootstrap requests and each subsequent read. Held sockets are interrupted by the
canonical request watchdog on deadline or cancellation, and that watchdog is joined
before return. Registry validation checks the budget around each local schema pair;
first validator import and a schema pair are cooperative CPU boundaries, not hard
real-time preemption. The selected Run contract has no retry-after
field; server/authorization/decoding errors propagate without retry. The result
is `terminal`, `deadline` or `stopped`, includes the latest Run if observed, and
always reports `compute_cancel_requested: false`. Terminal `unknown` is preserved
as the owner's uncertainty. Stopping a monitor does not cancel compute. Event
cancellation is observed during held socket reads and between bounded local steps
and waits. The read budget refuses mutation dispatch and does not change normal
low-level calls outside its context.

`cancel(run_id)` is a separate explicit server mutation. Its result distinguishes
`requested`, `drained`, and `cancelled_before_start`. The last means the owner
cancelled a prepared queue item without starting a process; it is not a drainage
receipt. A transport failure is not evidence of a cancellation outcome. No cancel
retry or automatic cancel-on-deadline is performed.

## Exact bounded collection

```python
manifest = workflow.collection_manifest(run_id=run_id,
    names=['weights.npz', 'receipt.json'])
receipt = workflow.collect(manifest, '/private/existing-results')
# For an interrupted/partial receipt, an explicit later call resumes:
receipt = workflow.collect(manifest, '/private/existing-results', resume=receipt)
```

Select one exact ordinary Run or pass `result_ref=exact_attached_publication_ref`.
The closed `workflow_collection_manifest_v1` binds catalog, source, SHA256 of the
sorted complete public name/hash/byte inventory, and 1–20 unique selected items.
Each item is at most 512 MiB and selected aggregate bytes are at most 512 MiB.
There is no wildcard, archive, recursive export, filename inference or path in a
manifest. Names use the canonical flat artifact grammar. Private destination
files use the selected artifact names in an existing destination directory.

The installed registry has no batched read operation. Collection therefore uses
its existing selected single-artifact segmented reader, sequentially, with at
most 8 MiB per segment. This is capability absence, not recovery from a failed
batch call. No batching operation or route is invented, and no authentication,
transport, decoding or server error causes an alternate request. A future batch
contract requires an explicit coordinated client implementation.

Collection checks the current inventory and transitive disclosure again before
reading, including on resume. Each artifact read rechecks its owner's current
authority. The complete byte count and SHA256 must match the pinned item before
publication. Provisional files are mode0600, in the destination directory, fsynced
and linked atomically without replacing any existing path. Existing files,
directories, dangling symlinks and concurrent destination creation refuse.
Corruption/refusal/interruption removes the affected provisional file. The
existing `project_cli.download` is a re-export of this same publication helper.

A `workflow_collection_receipt_v1` retains the exact manifest and ordered
`verified`, `refused` (with original typed error) and `outstanding` items. The
whole result is `complete`, `partial` or `stopped`. A failed item stops further
requests; collection never auto-retries it. Earlier verified files remain valid
local results. Explicit resume reopens each prior verified success without
following symlinks, checks owner/private regular-file metadata and whole SHA,
and reauthorizes it through the selected reader. Refused/outstanding items are
retried only by that explicit resume. Incomplete artifacts restart at segment
offset zero; no unverified prefix is retained or reused. No missing segment is
zero-filled. A changed inventory refuses the entire stale selection. Initial
inventory or resume validation failures raise a typed error; retain the earlier
receipt for inspection. CLI output can be saved for later resume, without token
material. Event cancellation stops collection only, never compute. A pre-set
event validates the local manifest and returns stopped before bootstrap/inventory
requests or local publication. Its items are outstanding, or retain the exact
previous resume proofs; it claims no fresh authorization/verification. Later
stops/partial results also preserve unvisited prior item outcomes. A subsequent
explicit resume rechecks them before claiming collection complete.

When an event is supplied, collection uses the same canonical AgentClient read
context in cancellation-only mode: each request keeps its finite configured
request deadline, cancellation is checked during bootstrap and socket reads, and
the request watchdog is joined. No separate overall collection timeout is added.
Connection setup may take up to the configured connect bound (at most5seconds),
and local validation/hash steps remain cooperative. Without an event, ordinary
finite configured per-request timeouts remain unchanged.

## Exact comparison

`comparison_manifest(run_id, other_run_id, checkpoint_sha256=...,
other_checkpoint_sha256=..., metric_id=..., mode='paired')` reads the selected
Run inventories and evidence for both explicit checkpoints, then exports the
exact evaluation artifact and metric definition hashes returned by their owners.
Both attached publication Refs may be supplied with `result_ref` and
`other_result_ref`; mixed ordinary/recovered operands are unsupported by the
current existing comparison operations. Missing evidence is typed unsupported.

`compare(manifest)` delegates the exact operands to the existing negotiated
comparison owner and returns its complete status/result envelope. Compatibility,
metric direction/units/population, missing values, clocks, deltas and refusal
reasons stay with that owner. The facade computes no scientific statistics,
selects no winner, invents no criteria or epoch, and performs no inference. The
ordinary exact comparison needs its existing v2 contract; a v1-only server cannot
silently downgrade to the old implicit selection. Compatible/incompatible is a
comparison result, not a model-quality acceptance claim.

## CLI and compatibility

See [project CLI](project-cli.md#consumer-workflow-commands) for the matching
convenience commands. Existing commands, private configuration and exit contracts
are preserved. New workflow commands emit machine-readable JSON; unknown,
partial, stopped and deadline outcomes remain explicit and exit1. Terminal Run
failure or uncertainty remains in the returned Run; reaching terminal state
exits0 because monitoring itself completed, without claiming compute success.
