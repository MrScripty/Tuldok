# Full-suite CI diagnosis and bounded repair

The [plan](../plan.md) owns current status and acceptance. This report preserves
candidate-specific outcomes; a passing subgate does not accept the whole feature.

## Failed subject and verified results

Feature head `5704965d1a441946aacf3548e0b9f57dc4312d35` ran in PR 119 against
main `133d53c0e2985a6559ba9cebd7d4a9f530051f06`. The root checkout log confirms
GitHub test merge `28a49775c42564972db64cb5503c3200476a9f0a`; both commits have
Git tree `31d69890b0f019349a5106e53337d19c9f2fbfe6`. The separate pinned legacy
checkout is not confused with this product checkout. Current standards remain
`5bce3110fc64d61ff8b4f79468184bd6295855d5`.

Lifecycle run `39874125909`, job `120155445651`, failed at full discovery:
2,332 tests in 2,179.457 seconds, 6 failures, 2 errors, 107 optional/intentional
skips. M1 interface `39874125884`, extension catalog `39874126119` and candidate
CPU `39874125893` succeeded. Decoded lifecycle logs separately establish:

- Native Run/fork/Study/accounting: 3 cases, 525.522 seconds, OK, no skips.
- Native SDK/CLI/MCP: 1 case, 22.140 seconds, OK, no skips.
- Note deletion/independent cold fork transports: 1 case, 10.541 seconds, OK,
  no skips.
- Later browser gates 45–50 and the previous observation-fixture repair at 72
  were skipped, not accepted on this candidate.

The earlier apt/ffmpeg provisioning delay resolved without source changes,
cancellation or another run. No supported cause was inferred from elapsed time.

Raw decoded log:
`/workspace/scratch/tuldok-save-load-qa/artifacts/lifecycle-39874125909-5704965.log`,
SHA256 `5dcef7b25ac80f9d8efb0f1c556f40796a6d748f8cdd213a84f7de19896435d4`.
Compact receipt:
`/workspace/scratch/tuldok-save-load-qa/artifacts/exact-candidate-ci-5704965-39874125909.json`,
SHA256 `025258dc14cf7a62c5c4a3f3d186c3653ec0d64d2abcfb8bdd145d13935a944f`.

Artifact upload succeeded as `12471242268`. The connector returned a reusable
ZIP reference, but the first local retrieval was denied by the proxy with HTTP
403 before receiving bytes. That operation stopped with no retry or alternate
route. Artifact manifest bytes remain uninspected; checkout identity and counts
above are established by the available log and independent Git data instead.

## Eight fixture failures and repair boundaries

Independent source triage found no demonstrated product regression. Repairs are
confined to the seven affected test files and their shared HTTP fixture helper;
production checks and protocol policy stay intact.

| Failed case | Cause and bounded repair |
| --- | --- |
| `test_project_dispatch.Dispatch.test_explicit_preparation_keeps_runtime_and_sequence_semantics_with_owners` | Opaque `pipelines.get` Mock cannot pass the finite saved-graph classifier. Author the intended valid external-recipe graph and keep the owner/runtime/sequence assertions. |
| `test_project_files_material_http.ProjectFilesMaterialHTTP.test_fresh_neutral_material_preparation_and_cold_refs_are_nonexecuting` | Replacing the entire `app.Dataset` class with a Mock breaks a real `isinstance` check. Keep the actual type and place the no-construction tripwire on `Dataset.__init__`. |
| `test_managed_model_workflow.ManagedModelWorkflowTests.test_trial_runtime_identity_and_budget_include_measured_managed_verification` | Expected budget omitted the separate bounded READY-to-GO owner wait. Include `recipe_process.GO_WAIT_SECONDS` in the independently derived expression; do not change admission policy or old historical charges. |
| `test_project_files_clients.Consumers.test_cli_named_lifecycle_and_json_text_commands_use_registry` | Latest negotiated get is v2. Retain explicit legacy-v1 fallback coverage. |
| `test_project_files_clients.Contracts.test_additive_negotiation_preserves_installed_legacy_and_mcp_contracts` | Latest get/annotate legitimately negotiate v2; original v1 contracts remain exact. |
| `test_project_files_fork_contracts.ForkTextContracts.test_old_pins_stay_exact_and_only_v2_accepts_closed_fork_origins` | Exact version inventory must include native execution-health v2 while freezing its v1 hash and original fork rejection checks. |
| `test_project_projection.ProjectProjectionTests.test_unknown_receipt_is_rejected_before_invoke_and_sql_or_checkpoint_changes` | The forged v2 envelope omitted project identity/namespaced ID, reaching structural invalidity before unknown-operation rejection. Use a structurally valid v2 envelope and preserve no-invoke/no-SQL/no-checkpoint effects. |
| `test_project_runtime.RuntimeCaptureTests.test_sigkill_after_native_publication_retains_exact_private_intent_without_final_ack` | Child `python -c` could not import the test helper. Supply its root/tests search path explicitly; retain actual SIGKILL -9, exact private intent and no final acknowledgement assertions. |

Three disjoint test owners and an independent read-only reviewer handle these
repairs. Only failed cases and necessary distinct controls run locally. No full
suite or native fit is repeated locally, and no same-head CI rerun is requested.
A changed candidate receives one exact-head campaign after targeted checks and
review. Qualification is not inferred for skipped browser stages.

## Targeted repair evidence

The public contract owner ran six selected checks in 7.530 seconds, all passing
without skips. These include the three failed assertions and distinct legacy
fallback/pin controls; all 238 original pins remain exact. Log SHA256
`3bcd9956ccdd3057c0706c4260122c38e36ac13885c0a38b89684695108528e5`
is retained at `public-contract-ci-repair.log` beneath the QA root.

The projection/runtime owner ran both failed cases in 4.215 seconds, passing
without skips. A separate clean-child-path control passed in 2.054 seconds
without an inherited tests search path. The actual child still received SIGKILL
(-9), and private intent/no-final-ack assertions remain. Logs beneath
`artifacts/` are `ci-39874125909-projection-runtime-fixture-repair.log`
(SHA256 `e7936287176118153282f72b3c1bd191a3dd1b57047942447df3011a0d6bbee6`)
and `ci-39874125909-runtime-clean-child-path.log`
(`f34e6e7f913076dc37c45f34ecea961f3b41c016fe5d78485689e31c50b94824`).

The domain owner's first selected three-case check passed Dispatch and managed
budget, but advanced the HTTP fixture to a second stale expectation: cold Open
now legitimately reconstructs authored Study/Trial metadata. The corrected
assertions require their exact IDs and counts while current epochs, Runs,
credentials, grants, reservations and execution authority remain absent. This
does not relax the no-execution or no-live-authority boundary.

The next HTTP-only check timed out at the helper's 15-second client deadline
before observing those assertions. Its server outcome is unknown: cleanup
removed the disposable schemas, and available logs show neither a server error
nor a supported lock/concurrency cause. Both failures remain evidence. A finite
fixture-only deadline now allows the existing 60-second catalog-local wait plus
the existing 15-second transport/reply allowance; all other fixtures retain
their 15-second default. No product latency SLA is inferred or changed.

The final HTTP-only check passed one selected case in 23.480 seconds, zero
failures/errors/skips. Disposable source/cold PostgreSQL preflight passed; 20
actual domain operations, separate-role source CONNECT denial, exact metadata
and closure, canonical-byte preservation and all no-execution tripwires passed.
No production file changed. Dispatch and managed-budget passes are retained
from the initial three-case check, whose overall result remains FAIL because
the HTTP tail stopped there. No already-passing case was repeated.

Domain logs beneath `artifacts/ci-domain-fixtures-39874125909/`:

| Evidence | SHA256 |
| --- | --- |
| `initial-3.log` (two passes, HTTP authoring assertion FAIL) | `fad0cd54239ce9b81fcdd2d6b1cfc932a40a63696ea25cff4d181725b7a9e058` |
| `corrected-http-only.log` (client deadline ERROR, outcome unknown) | `93dc4679aeee91cfa4bc4e7b7889d08e5b86efa9066dfde06e8e821ec3daa0b7` |
| `final-http.log` (one complete PASS) | `d65121ced653b50b7ede1362b636fd75f0c22e9a98201aeb1fa1966235bb9140` |
| `final-http-receipt.json` | `fb92bc6684ceb092f3c52373a96165c485d23b915829daac3e7785f69c1f1452` |

All eight original failed cases now have scoped passing evidence. Full-suite
and later browser acceptance still require the changed candidate's CI, rather
than inference from these local repairs.

The independent reviewer cleared all eight test files at exact subject SHA256
`9472f124392cf9e2c6cb36cadcd2ddf76ae33f2c279619e5222976b93b0b1688`
(SHA256 of compact sorted UTF-8 JSON mapping relative paths to file SHA256,
without a trailing newline). Review retained all old contract pins, legacy
fallback, no-effect/no-authority assertions and real SIGKILL; no product finding
remains. Documentation finalization is reviewed separately before commit.
