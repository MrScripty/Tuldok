# Study drain deadline after the fixture repair candidate

The [plan](../plan.md) owns current status. This report preserves the second
complete-candidate CI outcome and the narrow deciding repair.

## Exact failed subject

Feature head `591eb24de3ae9ccd219d0fc12bda6c34663a13d5`, based on main
`133d53c0e2985a6559ba9cebd7d4a9f530051f06`, ran lifecycle `39884356869`,
job `120188935444`. The decoded root checkout confirms merge
`455c08cef97e21afea0382281fff01b49a782c9f`; feature and merge share Git tree
`94deb443164152f279e95f1b314b2bd899ef38ec`. Coding-Standards remains
`5bce3110fc64d61ff8b4f79468184bd6295855d5`; remote source and standards were
rechecked unchanged during this campaign.

Full discovery ran 2,332 cases in 3,288.197 seconds: one failure, zero errors,
107 optional/intentional skips. All eight prior failures are absent. M1 interface
`39884356864`, extension catalog `39884356930` and captured CPU `39884356868`
succeeded. Named real gates separately passed without skips:

| Gate | Cases | Seconds |
| --- | ---: | ---: |
| Native Run/fork/Study/accounting | 3 | 913.214 |
| Native SDK/CLI/MCP | 1 | 44.171 |
| Note deletion/cold-fork transports | 1 | 19.799 |

Project browsers 45–50 and observation browser 72 were skipped, not accepted.
Artifact `12475845576` uploaded successfully; no download was attempted, and
its manifest remains uninspected. No previously denied retrieval route was
retried. Available checkout logs and independent Git trees identify the subject.

## Sole remaining failure and limits of observation

`ProjectStudyCustodyTests.test_cold_study_spent_budget_lineage_and_approval_remain_inert_while_fresh_attempt_is_current`
stopped at `tests/test_project_study_execution.py:426`: the inherited
`ProjectRunCustodyTests.await_drained` defaulted to 30 seconds. The last observed
fresh Run `5d790f16af4f4e13b3df5bbff817c057` was `running/go_intent`, with no error,
11.051 seconds measured queue and 6.514 seconds launch verification. That snapshot
does **not** prove delivered GO, final completion, settlement or the later
accounting/lineage assertions. No load, concurrency or product regression cause
is inferred from elapsed time.

The actual neutral recipe declares 10 seconds execution. Its existing Pipeline
admission reserves 10 READY + 2 setup + 60 owner GO wait + 0 post-GO verification
+ 15 cleanup seconds: 97 total. The fixture's 30-second observation deadline is
below that supported budget.

The one-case repair derives `drain_timeout` from its actual immutable composition
envelope's `admitted_wall_seconds`, plus twice the existing 60-second catalog-local
timeout for terminal publication and observation: 217 seconds here. Both Runs in
this same cold-Study case use the finite bound explicitly. The shared 30-second
helper, every other case and all product limits remain unchanged. Completed state,
zero active workers, exact spent/settled envelope, lineage, fresh approval and
absence of historical runtime authority remain required.

Independent read-only review cleared that contract before execution at test-file
SHA256 `183f8a3e8e15231e4ea3584b309be18318befe82cac158eb42a0f52e1a89a33c`.
Only the failed real PostgreSQL case is selected locally, using two generic
neutral script Runs, no native training or model fit. No identical full local
suite or same-head CI rerun is used to replace the failure.

## Retained evidence

Under `/workspace/scratch/tuldok-save-load-qa/artifacts/`:

| File | SHA256 |
| --- | --- |
| `lifecycle-39884356869-591eb24.log` | `272280e4bb2d08e00f9291b4258fa164d7719b0cc302a4cf07b6d4c8b13f892b` |
| `exact-candidate-ci-591eb24-39884356869.json` | `628a3e99d39b8df08d3786a7bc09ec4021aaae892c3e73334e76bd42c19fe215` |

## Targeted deciding result

The one selected real PostgreSQL case passed in 121.259 seconds, zero failures,
errors or skips. Existing database preflight passed; all 122 recorded production
and fixture source hashes stayed unchanged. Both generic neutral Runs completed.
All original assertions passed: exact twice-spent envelope, settlement, lineage,
cold zero operational tables, historical replay denial, fresh grant/Run identity,
one current SQL Run and reservation, and absence of the historical SQL Run.
This new case result does not establish the prior CI Run's unknown final outcome.

Evidence beneath `artifacts/ci-neutral-study-591eb24/`:

| File | SHA256 |
| --- | --- |
| `actual.log` | `42049d43f6e2ee8e71de0015203c9185897ca387bec4671e396b4544b7860e2a` |
| `receipt.json` | `4a0e529fd0de47a2a6f887454998e9694792cbae4411bfcd04e328ed1109b60c` |
| `subject.json` | `de2273208541e6d0671339ad5059c648addbce4afc0c8609759797bb0b77366b` |

Independent rereview inspected the actual receipt/log, verified the released
test hash against the pre-execution subject and cleared the repair. No product
finding remains. One changed candidate proceeds to CI; complete acceptance still
requires successful exact-candidate CI and the unrun browsers.
