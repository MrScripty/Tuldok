# Rheon producer-v2 consumer qualification

**Plan status:** `Verifying`

**Current phase:** Implemented adapter and fixture workflows under verification; actual-packet acceptance remains blocked.

**Next slice:** Finish published regression/CI qualification and recover the recorded actual packet through supported access before actual-packet acceptance.

**Acceptance status:** `pending`

**Execution ledger:** [execution-ledger.md](execution-ledger.md)

**Issues:** [issues.md](issues.md)

## Objective and admission

Allow the existing completed Rheon producer-v2 fixed-case trajectory to pass through Tuldok Data → editable validation/export Pipeline → durable Runs without losing its original accepted-interval controls or confusing authored data with actual producer evidence. This is the next finite development milestone under the user's persistent all-remaining-work goal and follow-up instruction to prepare it. The subsequent parent instruction explicitly admits implementation under the persistent development goal. This slice implements the versioned adapter and labelled-fixture gates; it cannot qualify a new physics run or claim actual-packet acceptance.

The accepted M1–M5 workspace snapshot remains valid for its bounded contracts. It is not proof that every historical plan, proposed adapter, or future integration is complete. [The corrected audit](reports/readiness-20261013.md) distinguishes exclusions, conditional reuse and later work.

## Objective acceptance

| ID | Observable criterion | Kind | Environment | Mode | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| V1 | Original v1 imports, stored bundles, releases and completed Runs retain their exact identities and downloads | integration | representative | automated | pending | Existing retained-run/browser gates plus explicit v1 regression |
| V2 | Three original files from the recorded actual packet pass the pinned upstream v2 validator and the Tuldok adapter; origin remains producer-emitted | contract | representative | automated | pending | Packet hashes and native provenance receipt; no synthetic substitution |
| V3 | Hash, length, key/type, interval/frame/stamp/unit/sign and bound violations refuse before persistence; producer-v2 cannot silently downgrade to authored-v1 | contract | not-applicable | automated | pending | Upstream reader and focused negative fixtures |
| V4 | Actual packet import, inspect controls, review, freeze, edited graph, execute, download and restart preserve all three files and whole-trajectory family protection | user-workflow | representative | automated | pending | Offline desktop/narrow/keyboard browser and independent cold reader |
| V5 | PostgreSQL backup/restore retains actual v2 bytes and v1 history; independent standards review and final relevant CI pass | system | representative | automated | pending | Existing persistence and CI owners |

## Scope and constraints

In scope: only the existing 16×8×4, nine-frame/eight-interval, 0.5-second producer-v2 contract. Keep the two-file v1 route and add explicit three-file v2 dispatch. Preserve raw bytes, frame ordering, decimal stamps, units and accepted control semantics. Review is human; technical validation is not review or authenticity certification.

Out of scope: new simulation campaigns, generated substitute packets, PR53 session integration, new physics/fields/geometry, model training, ASR, native Pantograph, personal-data migration, merges and deployment. No producer rerun is necessary merely because a transfer failed. PR32 records that producer execution was paused; do not infer authority to resume it from this consumer plan.

PostgreSQL remains the metadata authority; existing immutable bundle and local artifact owners remain authoritative. No second scheduler or database. No inferred producer family wire member: retain Tuldok whole-trajectory and initial-condition family protection. The producer does not certify independent train/test trajectories.

## Binding decisions and early observations

| Decision | Owner | Evidence | Supersedes |
| --- | --- | --- | --- |
| Reuse the completed PR32 output, not arbitrary SimulationSession output | Sequence integration owner | PR32 exact packet handoff; PR53 API explicitly retains exporter ownership | Generic assertion that no producer packet exists |
| V1 and v2 remain distinct supported contracts | Rheon adapter owner | Current exact two-file admission and pinned v1 reader; producer v2 reader | No silent upgrade/downgrade |
| Retrieve and independently verify actual bytes before V2/V4 acceptance | Integration owner | Library result resolves exact 73,722-byte archive; supported transfer failed | Missing local evidence is not missing producer implementation |
| Preserve accepted PR38–41 | Root | New dependent branch from cafe533; no writes to their branch refs | None |

Smallest deciding observation: materialize the recorded archive, verify its SHA256 and all three file lengths/hashes, then run the source-pinned upstream reader without executing physics. Current missing local bytes and exact transfer failure are recorded in the audit. Adapter preparation and labelled negative fixtures can proceed independently; actual-packet acceptance cannot.

## Evidence and oracle plan

Use Rheon's existing `tools/import_dense3d_controls.py` as the independent producer contract oracle, with its unchanged v1 numerical reader. Pin exact source and hashes before copying/adapting any consumer code. Verify source provenance against the recorded 020437fa source rather than current main. Raw hash equality establishes custody, not authenticity or model/scientific quality. Preserve and inspect the recorded native execution receipt separately.

Use existing strict sequence release, database, graph/run and offline browser harnesses. Add no competing general validation framework. Authored malformed fixtures prove refusal behavior only. Actual packet cold-read and exact download comparisons decide positive cross-project compatibility.

## Simplicity and ownership review

**Applicability:** `applicable`

- Independent concepts: producer manifest/version and interval controls; Tuldok asset/review/family; immutable release; existing graph/run lifecycle.
- State, identity, value, time and policy: upstream owns accepted interval clocks/stamps/units; the adapter validates original bytes; immutable assets own storage; review owns approval; Runs owns execution. V1 identities stay unchanged. V2 identity binds all three files, including controls. Missing or changed controls invalidate v2 import/freeze, not old v1 state.
- Compatibility: retained v1 remains two files; v2 is exactly three. Unknown versions and mixtures refuse. Persisted metadata must identify the actual validator/version. Determine whether any schema evolution is needed from current storage limits; do not change schema signatures implicitly.
- Caller/composition knowledge: HTTP and UI submit bounded files and present server outcomes. They must not recreate interval semantics, family hashes or scheduling rules.
- Representative changes: producer contract changes reach only the versioned adapter/validator and its fixtures; storage limits reach the immutable sequence owner; graph/run integration consumes the existing validated release contract.
- Stable interfaces versus hidden knowledge: one prepared bundle plus metadata crosses into storage; raw provenance and controls are inspected through existing server-owned summaries. Hide producer parsing and fixed-case semantics within the adapter.
- Independent evolution/testing/failure/replacement: keep pinned v1 qualification intact; exercise v2 independently against producer reader and actual packet; reject unsupported data before persistence. Adapter removal must not delete retained bytes or reinterpret saved releases.
- Necessary complexity: one explicit version dispatch and bounded v2 reader; original-file custody and version-aware release checks are required by independent persisted consumers.
- Deletion/cumulative machinery: reuse immutable assets, family allocation, canonical archive and the sole Runs supervisor; no plugin system, new transport or simulator integration.

## Milestone V2: Completed producer controls through the existing workspace

**Status:** `Implemented`

**Goal:** Satisfy V1–V5 for the recorded packet.

**Allowed write set:** `app.py` (both sequence routes share strict bounded JSON decoding), `rheon_sequences.py`, `rheon_sequence_contract.py` (preserve v1 semantics), `rheon_controls_contract.py` and `rheon_controls_sequence_contract.py` pinned from Rheon main, `sequence_assets.py`, `sequence_batch_import.py`, sequence release reader/metadata paths in their existing owners, `static/sequences.js`, `static/sequence-batch.js`, `static/workbench.html`, `static/workspace-real.js`, existing sequence graph/run summary paths, `tests/test_sequences_v2.py`, `tests/test_sequence_v2_runs.py`, `tests/fixtures/rheon_controls_authored.py`, sequence controller tests, `tests/browser_workspace_sequence_run.cjs`, `.github/workflows/tests.yml`, `README.md`, sequence contracts/source attribution and `docs/licenses/rheon-APACHE-2.0.txt`, and this plan. Expand exact adjacent filenames after tracing their existing owners, before editing; no unrelated changes.

**Tasks:** Recover/pin evidence; implement explicit version dispatch and three-file custody; retain whole-trajectory families; add compact controls inspection; connect existing validation/export recipe; prove v1 retention and v2 actual workflow; independent review; push separate draft implementation PR with ordinary checks.

**Gate:** V1–V5 all satisfied. Partial unit tests or authored fixtures do not close the milestone.

## Blockers and re-plan triggers

Implementation and fixture preparation are complete; see [checkpoint evidence](reports/implementation-20261013.md). Actual-packet V2/V4 acceptance is blocked on supported retrieval of the original frames and handoff receipt; exact evidence is in issues. No model/GPU requirement applies.

Replan if recovered hashes differ, native receipt is incomplete, producer validator rejects the packet, retained storage requires a migration, source-family semantics change, or new geometry/API/training scope is requested. Keep ordinary adapter repairs inside this slice.

## Repository isolation and review

Root owns `/workspace/Tuldok-v2-readiness`, branch `plan/rheon-v2-readiness-20261013`, based on PR41 cafe533a3289df773f1f5e4a8b21c65dc212e3b2. Implementation uses the separately owned `/workspace/Tuldok-v2`, branch `feature/rheon-v2-consumer-20261013`, from PR42 ef4a56f. Root integrates docs/CI/source attribution; backend agent owns adapters, assets, batch/release readers and focused Python fixture/tests; UI agent owns sequence scripts/markup/controllers; integration-test agent owns v2 run tests and the existing browser harness. No overlapping writers. Independent reviewers are read-only. Retain both worktrees under root/integration ownership for draft review. Preserve PR38–41 refs and owner work. Retain this worktree for plan review under integration ownership; later disposition requires reachability verification. Independent auditor reviews scope/source findings and this plan without editing shared files.

## Final acceptance

- Acceptance status: pending; actual-packet claims remain blocked on recorded bytes.
- Deferred follow-ups: ASR production adapter, general 3D training product definition and native Pantograph adoption retain the distinct dispositions in the audit.
- Final status: Verifying; actual-packet acceptance blocked.

The v2 producer numerical reader differs from the historical Tuldok v1 reader only in accepting the exporter’s appended Cargo message-format argument. Pin its exact version separately for v2 rather than silently broadening retained v1. This bounded duplication preserves two independently supported public versions; no competing runtime validation authority is added.
