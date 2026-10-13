# P3b verification

Status: local integration and full regression verified; published exact-head CI remains pending. Independent final
backend and UI re-review found no remaining blockers. P4 implementation remains gated on P3b
hosted lifecycle and UI success. No merge or deployment.

## Delivered behavior

Explicit project recipe definitions now produce editable input → execute → output
graphs. Preflight binds source/input/runtime/host/parameter identities; owner
approval and scoped agent consumption are atomic with the existing Run admission.
Schema8 retains old schema/backup identities. The sole queue uses a pinned Linux
subreaper helper, durable GO intent and independent controller deadline. Missing
drainage after possible execution stays unknown and fences external work.
Declared output bytes and custody receipts survive restart and are checked on
read. The public runtime is the explicitly trusted system Python installation;
filesystem/network authority is disclosed, not described as isolated.

## Completed evidence

- Full stable-source Python suite: **749 tests pass in856.353s**, with two optional-reader skips independently covered by20 passing spatial reader tests. All176 Python runtime/test files remained unchanged (aggregate `0a01e023016dc17405966eeb900e90edeb1ceb84725309676f33d8381459792e`).

- Access/schema/storage: 50 tests, including approval races, rollback, committed
  but unacknowledged consumption, exact schema7 and schema8 restore.
- Host/Projects/Pipeline: 28 tests; final five host tests rerun after cold material
  validation, with spec/material tampering and no-execution checks.
- Helper: 11 real lifecycle/fault tests, including READY/GO, controller loss,
  setsid/double-fork descendants, ignored TERM, bounded output, helper death,
  receipt failure, repeated cancellation and late BrokenPipe.
- Composed Runs/HTTP: final15 tests pass in56.182s. They exercise owner grants,
  wrong actors, revoked grants, drift, transaction rollback, active-queue lost
  acknowledgement fencing, GO-commit loss without execution, Unicode arguments,
  real cancellation, exact output/download/restart, altered artifacts and actual
  SIGSTOP helper deadline followed by independently verified cleanup.
- Actual native helper checkpoint: 237-byte Rheon READY response, STOP, exit0,
  `ECHILD` and durable drainage. See [native report](p3b-native-probe.md) and
  [receipt](p3b-native-probe-receipt.json). Zero simulation frames generated.
- Browser: keyboard graph creation/edit, exact review, stale-byte refusal before
  admission, actual descendant work, exact output bytes, separately authenticated
  agent using an owner grant, cloned cancellation and restart. Desktop1440 and
  narrow390 captures are retained in [p3b](p3b/receipt.json).
- Independent spatial readers:20 tests pass without skips.
- Existing project and recovery browser regressions pass. Thirty-one existing JS
  checks pass, with the browser-backed rights artifact check rerun in the proper
  PostgreSQL/Chromium environment after an initial missing-environment timeout.
  The new external controller test covers uncertain request custody and late
  response/session fences.
- Adopted standards plan-contract validation, Python/JS syntax and whitespace
  checks pass. No static type-checker or Standards Engine certificate is claimed.

## Independent review and corrections

Separate owners reviewed Access/admission, host capture, process lifecycle and UI.
Review fixed double staging creation, exact approved-spec projection, imported
helper identity, retained output bounds, directory durability, unknown-commit
queue eligibility, Unicode spec canonicalization, an independent parent deadline
and cancellation-channel closure. UI review preserved an actor-bound unresolved
key after permission failure and fenced asynchronous adoption/navigation.

The initial focused13 integration run passed12 and exposed one test fixture that
needed complete custody identity. The following14 run found a real late-cancel
channel race, fixed in the helper and covered by deterministic and repeated real
cancel tests. Final15 passes above supersede those failures. Mocks only inject
specific faults; neutral completion and drainage use actual processes.

## Boundaries

No scientific/model/GPU acceptance is claimed. P4 generation, P5 fitting and
rollout evaluation, P6 agent transport and P7 full scientific workflow remain
open. ASR and general 3D training remain outside this concrete recipe acceptance.
A killed custodian can leave descendants alive; the observed same-boot unknown
fence is deliberate and cannot be dismissed with an acknowledgement. This is
trusted-code lifecycle custody, not hostile-code confinement or aggregate
resource enforcement.
