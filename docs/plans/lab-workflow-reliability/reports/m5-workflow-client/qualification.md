# M5 consumer workflow implementation and qualification

Status: implemented; actual HTTP qualification pending, independent review and
root serial publication/integration pending. This report is supporting evidence
for the admitted `docs/plans/lab-workflow-reliability/plan.md` M5/C6/T6 work;
it does not accept the whole plan or replace shared plan/ledger authority.

Source starts at published whole UI `3217ef9` (PR104), in task-owned branch
`feature/lab-workflow-client-20261019`. Root retains all remote publication,
independent review and normal merge composition. No old catalogs or unrelated
branches/worktrees are opened or altered. No package installation or runtime
capture is performed. The original unmerged plan-author PR91 remains separate.

The delivered source is `tuldok_client.py`, matching new convenience commands in
`project_cli.py`, exact client/CLI documentation and one README entrypoint
paragraph. The existing download helper is moved intact in mechanism to the
client and re-exported from the CLI. Focused tests are in
`tests/test_workflow_client.py` and actual HTTP qualification in
`tests/test_workflow_client_http.py`. No server operation/registry/schema,
scientific policy, budget, runtime installer, dispatch or scheduler is added.

Root explicitly extended the initial write set to the `AgentClient` imports,
class/request owner and an optional `validate_registry(checkpoint=None)` hook.
A shared thread-local read budget constrains initial registry validation,
identity/context/capability bootstrap and polling to one absolute deadline.
The canonical request owner interrupts a held socket on deadline/current event
and joins its watchdog. Read-budget mutation dispatch refuses. Local validator
import and one schema pair remain cooperative CPU boundaries, not hard real-time
preemption. Outside-context low-level calls keep their existing contract.

Submission exports exact selected material or Trial/Study arguments with an
existing grant and caller-owned stable key. One explicit dispatch acknowledges,
definitely refuses or stays unknown. Server5xx/commit_unknown remain unknown;
later revoked/expired/conflicting reconciliation cannot prove the earlier
admission had no effect. Positive acknowledgements must correlate to the exact
request. Root's early review caught UTF-8 material canonicalization and these
mutation uncertainty distinctions before actual qualification; focused regression
witnesses now cover them.

Collection uses existing single-artifact reads because the installed registry
has no batching operation. It pins exact catalog/Run or attached publication Ref,
complete name/hash/byte inventory identity and at most20 selected items/512MiB
aggregate bytes. Failure stops subsequent requests. Whole SHA and byte count,
private mode0600 provisional bytes, fsync and atomic no-clobber publication remain
required. Explicit resume reauthorizes and rehashes verified successes; incomplete
artifacts restart at segment offset0. There is no retained/unverified-prefix
reuse or invented collection route. Comparison exports exact operands and delegates
all compatibility/evaluation/statistics to the existing owner.

## Evidence recorded before actual HTTP qualification

- `focused.log`: 12 focused tests passed on the implemented source before the
  actual HTTP gate. Covers stdlib-only clean `python -S` import/startup tripwires,
  stable-key unknown reconciliation, 5xx/negative reconciliation uncertainty,
  Unicode canonical material hashing, no compatible operation/no dispatch,
  read-budget mutation refusal/context cleanup, monitor deadline/stop, requested
  cancellation, interrupted/resumed segments, partial typed outcomes, malformed
  segments, whole hash, no-clobber race, changed inventory/local success refusal.
- Existing CLI selection/download tests: 9 passed (`test_agent_project_cli`'s
  `CommandSelectionTests` and `PublicationTests`) before the later deadline adapter;
  rerun with affected transport/compatibility tests is required on final source.
- `python -m py_compile` passed for changed source/tests; `git diff --check` passed.
- Actual HTTP/custodian tests deliberately deferred during M4's controlled cost
  matrix, after coordination with its owner. These focused tests make no cost,
  speed, model training, CUDA or scientific acceptance claim.

## Failed attempts and corrections retained

The first focused import-tripwire attempt ran8 tests with one failure. The test
replaced `socket.socket` with a function before stdlib `http.client` imported
`ssl`; `ssl.SSLSocket(socket)` then failed with `TypeError: function() argument
'code' must be code, not str`. The guard was corrected to subclass `socket.socket`
and reject construction. The product import path was not weakened. The original
failure was reported to root; subsequent focused receipts show the corrected
tripwire passes. This was a test-harness failure on uncommitted M5 source, not a
runtime or application startup failure.

Actual HTTP tests and final source/commit attribution will be appended after
the benchmark owner's quiet window and focused qualification. Missing or failing
acceptance stays visible; no CI or full-plan acceptance is claimed here.
