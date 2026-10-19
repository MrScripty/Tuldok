# M5 consumer workflow implementation and qualification

Status: implemented and qualified in the scoped actual HTTP groups below;
root integrated-source review, CI and serial publication/integration remain
pending. This report is supporting evidence
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

## Independent review follow-up before HTTP qualification

Root reviewed source commit `d04d9be64b115d491a005ddb59fb868f3e2dea1a` and found no
new blocking client/CLI issue after its earlier hash/uncertainty/deadline fixes.
It requested prompt pre-set collection cancellation. Root explicitly approved
cancellation-only `read_budget(deadline=None, cancelled=Event)`, preserving finite
configured per-request deadlines and the same canonical watchdog/socket owner.
Collection now validates the local closed manifest and returns stopped before
bootstrap when already cancelled. An explicit resume retains earlier item proofs;
stopped/unvisited proofs make no fresh authorization/verification claim. Current
bootstrap and segment reads observe that event through the same request owner.
No request parallelism or alternate transport is introduced.

Follow-up source also retains publication-result Ref provenance on resumed local
successes and refuses destination inode replacement during local whole hashing.
`focused-followup.log` records14 focused tests, including pre-stopped/no-network
collection and the pathname replacement race. The actual HTTP test covers a
blocked artifact response, Event cancellation, provisional cleanup and explicit
resume. Existing CLI `submit/status/download` and a frozen legacy AgentClient
now read the same genuinely completed Run inside the disposable HTTP fixture.

The selected existing interpreter's installed metadata is Python3.12.14,
psycopg3.3.6, jsonschema4.26.0, NumPy2.5.4, Torch2.8.0+cpu,
torchvision0.23.0+cpu and scikit-learn1.7.2. The optional existing classifier
fixture uses the built-in runtime directly and creates no runtime snapshot/copy.

A final capability regression (`focused-comparison.log`, 15 focused tests) makes
an exact comparison against a v1-only server explicitly `operation_unsupported`
before dispatch, rather than relying on the older schema's argument rejection.
It cannot downgrade to implicit checkpoint/evaluation selection. This changes no
server operation version or wire schema.

## Actual HTTP attempt01 — failed and retained

The benchmark owner released its quiet window at22:10:55UTC after its matrix
exited0. Actual HTTP qualification then ran on normal composed source
`2d8b7d79110f210896dcdda8df08f6385cabf2d3`, which includes whole104
`1c9f01cb7e4adafd169dd56e95e02f0f5025b35d` through a normal merge. Root published
that source as draftPR105; actual qualification was explicitly pending.
`http-attempt-01-source.json` records the exact source/tree/file SHA256s, command
and installed runtime metadata. `http-attempt-01.log` is the complete failed
receipt: 12 cases in238.210s, 5 passed and7 errors. It is not overwritten.

Five actual cases passed: clean CLI neutral submit/monitor/collect and existing
CLI/frozen legacy reads; retained Trial admission with one reservation/consumption;
attached publication collection/resume and revoked access; cold monitor
import/registry deadline/cancellation; delayed bootstrap sharing one deadline and
blocked Run-read Event cancellation. These are genuine supported boundary
observations, not full T6 acceptance.

Six errors were a fixture name collision: `ExternalCase` already stores its
project manifest dictionary as `self.manifest`; the new helper method with that
name was masked, giving `TypeError: 'dict' object is not callable`. Rename it to
`submission_manifest`. The typed commit-uncertainty injection also preserves the
real handler's `_graph_guard` keyword argument so the fault occurs after the
actual admission rather than at a test adapter signature mismatch.

The classifier case exposed a product consumer bug. Built-in Runs legitimately
include public `artifact-manifest.json` metadata, while the selected segmented
reader intentionally cannot select that name. Full inventory validation had
incorrectly applied the selected reader's exclusion to every unselected metadata
item, refusing a valid retained classifier before comparison. The fix checks
bounded flat names, hashes and byte counts across the complete public inventory,
then validates only selected collection items against the exact reader grammar.
The complete inventory remains hashed, and blocked names cannot be selected.
`focused-inventory-fix.log` records16 focused passes including this regression.
Actual rerun remains required; no unsupported numerical/runtime claim is inferred.

## Actual HTTP attempt02 and independent review fixes

`http-attempt-02-source.json` attributes the explicit rerun to
`cb68bc0`; `http-attempt-02.log` records all12 cases passing in406.466s.
This includes the existing two-epoch CPU classifier's exact selected comparison,
real CLI exports/admission/monitor/collection, frozen legacy reads, same-key lost
reply and typed post-commit uncertainty, grant/credential refusals, cancellation
and drainage, blocked response cancellation, segmented interruption/resume,
whole-hash mismatch, no-clobber race, retained Trial and publication-Ref paths.
No large runtime snapshot or package installation was performed.

Independent review of the earlier source identified two additional correctness
blockers that the successful12-case gate did not cover. That pass therefore does
not establish final-source acceptance. The gate source stayed unchanged while
its CLI subprocesses were active; fixes were first exercised in an isolated
`/tmp` module, then applied after the gate exited.

1. A cancelled resume could retain an unvisited old `verified` proof and report
   whole collection complete because it tested historical item states first.
   Completion now requires every item to be freshly verified in this invocation;
   stop takes precedence. The exact controlled repro corrupts the second earlier
   success, stops after rehashing the first, and asserts stopped plus no second
   request. Prior proofs remain available for explicit later rechecking.
2. A schema-valid Study admission acknowledgement could contradict requested
   parent, configured catalog, existing grant or the owner's request SHA256.
   The client now checks these fields and exposed Run/reservation associations.
   It derives the existing `experiments.Experiments.admit/1` receipt SHA from
   operation/version/current exact contract pin/Study ID/canonical UTF-8 body
   excluding the path Study ID. This is protocol correlation, not budget policy.
   The focused oracle uses the existing Pipeline digest and real AgentClient
   selected v1 decoder; seven independently schema-valid contradictory replies
   remain unknown with the original manifest and one dispatch each.

`focused-review-fixes.log` records18 focused passes. The new actual two-artifact
resume test preserves the corrupted unvisited file, refuses it on explicit
recheck, then completes after the user explicitly moves that file aside. The
actual Trial test now injects a wrong-catalog201 only after real HTTP admission,
then explicitly reconciles the original exact identity; one Run/grant/reservation
is required throughout.

`http-review-fixes-source.json` pins the affected rerun to
`875038ade24a8a37c1431fbe0f8e4c2625e20a5e` and its exact file hashes.
`http-review-fixes.log` records all5 affected actual HTTP tests passing in82.269s:
the two-artifact cancellation/corruption repro, blocked segment Event interruption
and cleanup, segment interruption/resume/whole-hash/no-clobber, retained Trial
acknowledgement/reconciliation, and attached Ref resume/revocation. The five
fresh fixtures used the existing private Unix-socket PostgreSQL cluster and
actual authenticated loopback HTTP; each closed its catalog before dropping only
its newly created schema. This rerun contains no classifier training.

Independent M1 review rechecked the same `875038a` source: all18 focused tests
passed, the original cancelled-resume repro returned stopped, and a valid strict
AgentClient Study baseline plus eight independently schema-valid contradictory
acknowledgements (including membership) each preserved unknown, the exact manifest
and one dispatch. Its root-owned receipts remain separate from this author report.
The earlier full12 pass remains attributed to `cb68bc0`; it is not relabeled as
a full-suite pass on `875038a`.

`legacy-client-cli-contracts-source.json` pins the final compatibility gate to
the same `875038a` source and exact production/test hashes.
`legacy-client-cli-contracts.log` records all35 tests passing in203.608s:
registry/client/output/parity, exact operation negotiation and legacy refusal
behavior, plus existing CLI selection and private atomic download publication.
This group ran after the affected actual gate and before M4's next paired quiet
matrix; its owner held that matrix until the explicit CPU release. No further
heavy tests ran here after that release. Final receipt changes contain no product
source changes, so the qualified production hashes remain those in the source
receipts. `git diff --check` passed before the receipt commit.

Root owns an additional ordinary comparison-v2 response correlation guard in the
canonical AgentClient, separately from this branch's two fixes. It will be
qualified after root composition with M6. No client-side scientific comparison
math or new operation schema is introduced here. Required integrated CI and
independent review remain root-owned gates.
