# D4: Implementation handoff

Status: selected architecture-design handoff, not authorization to implement the
application. User authorized completion/publication of the **design** plan.
Production slices below need their own concrete implementation operation. PR62
remains unmerged. Baseline application main is f58880df (catalog schema8); D1/D2
are 0f8ccfe/e407cb1. Recheck implementation main before allocating a migration.

The [D1 recommendation](architecture-design.md), [D2 contracts](evidence-contract-design.md),
[D3 workflow/procedures](workflow-design.md) and [observations](design-observations.md)
are inputs to this handoff. The [local prototype](prototypes/model-development.html)
is runnable now; future commands below are explicitly acceptance entrypoints to
be authored in their named slices, not scripts already present or tests run here.

## Selected first delivery and non-goals

Deliver the **classifier vertical first**, with Pipeline-owned recipe/model
configuration, immutable trial material, current owner-only built-in launch,
automatic real checkpoint/probe evidence, compact inspection, correction/new
release and candidate package/fresh inference. In the same implementation wave,
exercise the generic custody/query boundary with an independently owned scientific
adapter contract; do not hard-code its fields, gauge or numerical operators into
Tuldok. Its captured standalone field inputs/outputs/stages may change only via
explicit task/model/adapter versions. No seven-service/module target.

The optional pressure adapter is a co-test and later integration, not a dependency
of classifier/data/Run operation. A missing qualified field adapter may remain
unsupported while the classifier is useful. Existing negative CNN physics result
remains diagnostic. No new GPU installer, hosted worker, remote execution,
adaptive-study grant, arbitrary-code auto-instrumentation, universal graph editor,
training-resume guarantee or production deployment is selected.

The Torch-less design environment cannot qualify a numerical capture default.
The chosen model-aware classifier profile is **unavailable until its actual
producer gate passes**. That conditional capability does not weaken existing v1
training or turn mock values into measured evidence. See the exact future gate
below. This is the plan-permitted bounded unsupported/deferred disposition for
A4, not a claim that all later production tests pass.

## Runtime and finite scheduling

- Reuse existing local Linux CPU Runs supervisor, queue limit8 and one active
  child. Admission uses D2's narrow transactional Runs seam and outer-commit wake;
  experiment coordination never spawns or supervises a process.
- Use stable FIFO by admitted creation instant then Run ID. Experiment proposals
  are not queue entries or execution rights. Admit only explicitly requested exact
  finite trials/replicates; each attempt gets its own receipt, reservation and
  grant where required. No prefetch/admission of future adaptive configurations.
- Initial study controller admits one requested child at a time through the same
  queue; unrelated standalone Runs keep their existing admission rights and share
  FIFO. No per-study priority/fairness broker. Queue-full/stopped/unknown refusal
  leaves grant and ledger unchanged. Future distributed fairness is out of scope.
- Grant expiry/revocation and credential authority are rechecked under the owned
  lock, including after grant row lock. A study budget, membership or capability
  never permits execution. Built-ins stay owner-only; external source has the
  existing exact actor/material one-use grant and trusted-local permissions.
- Before opening a new epoch or admitting a next attempt, reconcile the original
  receipts read-only, current material/runtime, known child cessation and budgets.
  Stop commits closed epoch first and cancels all admitted children. Unknown child
  or commit fences admission and retains reservation. Restart does not replay
  queued proposals, refund consumed authority or signal remembered foreign PIDs.
- Scheduling, cancellation and mandatory audit work remain under existing catalog/
  Runs/Access locks and process custody. Do not hold DB locks during model inference,
  hashing large artifacts or blocking process waits. Reuse metadata rollback/
  on-commit hooks; caller-supplied transaction does not authorize a nested submit
  to wake before final commit.
- Budget slots and admitted wall ceiling are cumulative conservative charges;
  retained bytes count while referenced, staging occupancy releases only after
  proven cleanup. Admission accounting is not an OS CPU/GPU/RSS/filesystem quota.
  Required hard quota modes are unsupported. Filesystem free-space checks and
  watchdog/output caps remain operational admission/termination mechanisms.
- Runtime/source/profile drift on retry changes exact material: refuse study
  retry under the old trial and prepare a new trial/material/grant. Existing v1
  retry behavior remains its legacy contract, not proof of exact study replay.

Runtime provisioning is separate and inert discovery reports missing capabilities.
Retain supported requirements-training CPU pins (Torch2.8.0+cpu,
torchvision0.23.0+cpu, scikit-learn1.7.2 and allowed Pillow range). No installation
on open/preflight/worker start. External captured CPU projects keep their exact
RuntimeSnapshots and NumPy/source requirements. Managed CUDA branch d3514c6 is
not current-main qualification; GPU requires a separately admitted runtime profile,
loader/custody and hardware evidence before any capability is advertised.

## Package and fresh-consumer responsibilities

Experiment owns selection/diagnostic status; model/evaluator owns reconstruction,
meaning and expected-output tolerance; Pipeline pins packaging/verifier material;
Access owns current authority/disclosure; Runs owns both execution and bytes.
Package, verifier and optional physical evaluator are ordinary charged attempts.
No new candidate registry, deserialization service or execution exception.

A package contains the checkpoint descriptor **and exact weights**, model/source
import/entrypoint closure, preprocessing and fitted statistics, input/output/task/
stage/shape/dtype/unit/gauge policies, runtime contract, selection/evaluation/
lineage, licenses and inventory. Private training data stays permissioned lineage
unless explicitly authorized for export. Acceptance probes/expected values are
included when permitted or named explicit authorized inputs. No live checkout,
model cache, mutable default or undeclared download is allowed. Optimizer/resume
state is optional and separately contracted; weights alone do not promise resume.

Packaging must verify permission to every transitive blob and preserve whole-
artifact population protection. Unknown/mixed scientific test content cannot be
exported merely because a generic artifact route exists. Whole/segment/capture/
import/query/summary/cache/export access must agree or the mode stays unsupported.

Fresh-consumer acceptance exports through actual interfaces, verifies full bytes,
then launches a fresh separately authorized consumer process with only package,
explicit compatible runtime and permitted fixed probes. Compare output values
against evaluator-owned exactness/tolerances, pin all identities and retain the
new verification receipt. Wrong weights/class order/fit statistics/gauge/runtime
or missing dependency fails. No retraining, telemetry setup or live Rheon is
needed for captured inference. Physical validity is a separate optional evaluator
criterion and may still fail after exact inference reconstruction.

## Dependency and license disposition

No new package/framework/server is selected. Keep existing owner mechanisms and
numerical libraries. The handwritten supported adapter should capture evidence
at its lifecycle seam rather than adopt Lightning just for callbacks; no MLflow,
Label Studio, dashboard server or generic schema-subsumption engine displaces
existing ownership. Revisit only a concrete required capability with measured
maintenance/runtime cost and an owner.

| Dependency/material | Decision / responsibility / distribution gate |
| --- | --- |
| Torch/torchvision CPU | Existing supported runtime, not installed here. Retain exact qualified wheel/source identity and full notices; primary tagged [Torch license](https://github.com/pytorch/pytorch/blob/v2.8.0/LICENSE) and [vision license](https://github.com/pytorch/vision/blob/v0.23.0/LICENSE) were inspected. Do not infer a complete wheel/transitive license inventory from the top-level source notice. |
| NumPy | Existing captured scientific runtime and disposable array observations only; [tagged source license](https://github.com/numpy/numpy/blob/v2.3.5/LICENSE.txt) inspected. Exact snapshot may include BLAS/native dependencies with additional notices; capture manifest/licenses at qualification. No version substitution from the design host. |
| sklearn/Pillow/psycopg/MCP/jsonschema | Existing task/storage/optional-agent dependencies under their current pins/ranges. Domain owner records exact installed versions, metadata and transitive notices in the selected runtime/package; no new legal compatibility assertion or SDK adoption. |
| Chart/field rendering | Native HTML/SVG/canvas and existing browser service; no new visualization dependency. The prototype is self-contained. Revisit only if a concrete accessibility/performance requirement demands a library. |
| Model/project/user data | Capture does not transfer license/redistribution rights. Package manifest records source/weights/data permissions and actual included notices. Unresolved rights deny the affected distribution; never stamp a permissive license onto arbitrary captured code. |
| Tuldok distribution | README states no distribution license selected. Initial scope is the owner's local/private workflow, not public redistribution. A future public distribution requires the repository owner to select rights/notice policy; this is an explicit excluded distribution promise, not a blocker to reviewing the internal design. |

The package owner validates the actual selected closure, not a broad library-name
allowlist. A required missing/unknown notice or incompatible distribution right
returns unsupported export for that closure. D4 chooses no new license and does
not relicense Tuldok, lab, Rheon, user data or historical records.

## Migration and compatibility cutover

The next implementation schema is **9 only if main still has8**. Metadata owns
exact DDL/signatures and upgrade numbering; changed baseline re-plans migration
number/chain without weakening old states. New domain rows follow existing exact
text documents and typed indexed identifiers. Proposed table/constraint inventory:

| Owner / table | Durable columns and constraints |
| --- | --- |
| Model / `model_definition_drafts` | `id TEXT PK`, `revision BIGINT >0`, `document TEXT`; expected-revision CAS. |
| Model / `model_materials` | `(id,revision)` unique, `sha256 TEXT UNIQUE`, `document TEXT`; immutable published definition/source inventory. |
| Pipeline / `workspace_recipe_materials` | `sha256 TEXT PK`, `recipe_id TEXT`, `recipe_revision BIGINT`, `document TEXT`; immutable complete capture; no latest indirection. |
| Experiment / `model_studies` | `id TEXT PK`, `revision BIGINT`, `admission_epoch BIGINT`, `document TEXT`; bounds/closed lifecycle enforced by owner and selected DB checks. |
| Experiment / `model_trials` | `id TEXT PK`, `study_id TEXT`, `material_sha256 TEXT`, `replicate BIGINT`, `document TEXT`; unique `(study_id,material_sha256,replicate)` and retained material FK/restrict deletion. Membership revisions immutable in `model_study_memberships(study_id,revision,document)` composite PK. |
| Experiment / `model_attempt_reservations` | `id TEXT PK`, `study_id TEXT`, `actor_id TEXT`, `request_key TEXT`, `request_sha256 TEXT`, `trial_id TEXT`, `run_id TEXT UNIQUE`, `document TEXT`; unique study/request key and global attempt link. Existing Runs request-key uniqueness still governs. |
| Experiment / `model_candidates` | `id TEXT PK`, `study_id TEXT`, `trial_id TEXT`, `run_id TEXT`, `document TEXT`; immutable selection record and owned artifact/evidence references. |
| Shared operation receipts | Reuse the owning operation's durable row where sufficient; otherwise one metadata-owned `model_operation_receipts(actor_id,operation_id,request_key,request_sha256,document)` with unique `(actor_id,operation_id,request_key)`. No generic command queue or event-sourcing framework. |

Use BIGINT for Nat resource/revision values and enforce D2 safe-integer bounds;
never silently fit them into existing signed32-bit columns. Exact foreign-key
order, signatures and fixture DDL are slice deliverables, reviewed against real
PostgreSQL, not implied by this proposed table list.

1. Stop all writers/workers, preserve complete schema8 backup plus files/receipts;
   verify baseline signature and selected migration identity.
2. Apply new DDL/version/signature atomically using existing explicit upgrade;
   no ordinary startup migration. Retain exact old schema definitions/hashes and
   all old graph/Run/release/grant/exposure bytes. No backfilled fictional model/
   checkpoint/probe history. New material rows start empty.
3. Verify original and new rows/files/cold reads and backup/restore into a new
   destination. A failed migration rolls back; unknown commit preserves state,
   reopens and verifies known old/new schema, never rewrites the ledger to match.
4. Start only the selected new application. Old binaries fail unknown schema.
   Restored old backups retain their exact schema; explicitly upgrade that copy.
   Downgrade uses the quiesced pre-upgrade backup, not deleting new tables.
5. Deploy registry/client change with frozen f58880df v1 discovery projection
   and unchanged legacy grammar. New clients negotiate exact contracts and
   pre-domain selected-contract checks. Verify all four old/new combinations.
   Retire legacy projection only after supported-installation inventory/cutover;
   no absence inference from opt-in passive logs.
6. New evidence version gates new producer/verifier/query/view together. Old v1
   selected-only results remain readable as historical unsupported history.
   Unknown external roles stay opaque artifacts. Current permission/exposure is
   checked independently from historical integrity on every derived read.

## Dependency-ordered production slices and exact write sets

Paths in this section are **proposed future implementation files**. A task selecting
one slice must recheck source facts, authorize its write set and preserve unrelated
work. Do not execute missing scripts as if they were shipped. Each checkpoint has
a runnable verification entrypoint and a viewable outcome after its implementation.
No migration, app source or application test file is changed in this design PR.

### P1: Negotiated contracts without breaking existing work

Write: `agent_api.py`, `mcp_stdio.py`, `project_cli.py`, `app.py`,
`tests/test_agent_api.py`, `tests/test_mcp_stdio.py`, `tests/test_agent_project_cli.py`,
`docs/contracts/agent-operations.md`, `docs/contracts/project-cli.md`.

Keep one registry owner with exact frozen legacy projection and locally implemented
contract versions. Implement bounded capabilities endpoint, internal selected-contract
header validation before domain entry, current authority and no generic schema
subsumption. No new model/task capability advertised yet.

Checkpoint: real HTTP/CLI/MCP old/new matrix, additive operation, one incompatible
operation, revocation and discovery/dispatch race; zero mutation/grant effect on
mismatch, lost post-dispatch acknowledgement reconciles once. Run existing focused
agent/CLI tests plus their new real-interface cases. View existing Data/Pipeline/
Runs with old and upgraded clients; no new workflow setup needed.

### P2: Immutable model/recipe material and finite study admission

Write: new `model_definitions.py`, `experiments.py`; `pipeline.py`, `runs.py`,
`access.py`, `metadata.py`, `app.py`, `agent_api.py`, `upgrade_metadata.py`,
`backup_metadata.py`; new `tests/test_model_definitions.py`,
`tests/test_experiments.py`, `tests/test_study_admission.py`;
`tests/test_workspace_metadata.py`, `tests/test_execution_approvals.py`,
`tests/test_metadata_migration.py`; new `docs/contracts/model-development.md`;
`docs/contracts/workspace-storage.md`, `docs/contracts/actors.md`.

Model definitions own typed template/config/source and fitted-policy distinction;
Pipeline owns v2 draft and immutable snapshots. Experiment owns study/policy/trial/
reservation/candidate intent. Metadata alone owns physical schema9-if-current8.
Add narrow Runs admission seam, outer-commit wake and read-only receipt lookup;
retain exact actor/material grants and owner built-in gate. No second runner.

Checkpoint: run `python -m unittest discover -s tests -p test_study_admission.py -v`
after authoring it, against disposable PostgreSQL. Exercise real two-connection
reservation/stop/revoke races, rollback before/after grant, lost commit/response,
changed source/runtime retry and unknown child fencing. Back up/upgrade/restore a
stopped schema8 fixture and reopen exact material after draft overwrite. View
inert model/recipe/study details through real HTTP/CLI without launching training.

### P3: First useful automatic classifier vertical

Write: new `model_evidence.py`; `image_training.py`, `pipeline.py`, `runs.py`,
`model_definitions.py`, `experiments.py`, `app.py`, `agent_api.py`;
`static/workspace-real.js`, `static/workspace-service.js`,
`static/workspaces.css`; new `tests/test_model_evidence.py`,
`tests/qualify_model_development.py`, `tests/fixtures/model_development/`;
`tests/test_image_training.py`, `tests/test_runs.py`, `tests/test_agent_api.py`;
`docs/contracts/workspace-image-training.md`, `docs/contracts/workspace-runs.md`,
`docs/contracts/model-development.md`. The existing shared workspace stylesheet remains its owner; no new global theme
service is introduced.

Support TinyCNN template widths/input/head only under a new qualified adapter/version;
keep legacy recipe untouched. Capture real per-epoch weights/descriptors and fixed
validation probes inside supported adapter; task evaluator verifies/indexes exact
artifacts, Runs publishes atomically. Structured queries and compact view consume
the same evidence. Correct current Workbench data, freeze new release, prepare
new trial, compare only compatible validation membership. No per-run logging or
manual artifact import/chart wiring.

Checkpoint: provision the already specified supported CPU runtime separately,
then proposed command
`TULDOK_TRAINING_PYTHON=/qualified/cpu/python python tests/qualify_model_development.py --task image --fixture tests/fixtures/model_development --output /tmp/new-model-qa`.
The authored driver must use actual owner/HTTP/Run/custody and source-pinned fixture,
not injected completion rows. It records ≥2 actual checkpoints/probes, bytes/
elapsed/RSS, cold reopen, independent fixed inference and UI/headless H1/H4/H5.
Keep model-aware capability unavailable until this gate passes; change profile or
return unsupported on bound/cost failure. View real linked controls at1440/390 and
keyboard, with old v1 history absence still honest. This is the first complete
useful human/agent training-inspection-correction checkpoint, not merely a chart.

### P4: Scientific adapter co-test and one-fit task expansion

Generic writes: `model_evidence.py`, `model_definitions.py`, `recipe_contract.py`,
`recipe_process.py`, `runs.py`, `app.py`, `agent_api.py`,
`static/scientific-fields.js`, `static/workspace-real.js`;
`text_training.py`, `audio_training.py` only for explicitly selected one-fit
adapter-version capture; new `tests/test_field_evidence.py`,
`tests/test_one_fit_evidence.py`; `tests/qualify_model_development.py`;
`docs/contracts/model-development.md`, `docs/contracts/scientific-fields.md`,
`docs/contracts/workspace-text-training.md`, `docs/contracts/workspace-audio-training.md`.
Optional existing wrapper changes, if selected, are restricted to
`adapters/rheon/cpu_train.py`, `adapters/rheon/evaluate.py`,
`adapters/rheon/cpu_training_project.py`, `adapters/rheon/evaluation_project.py`,
`docs/contracts/rheon-cpu-training.md`, `docs/contracts/rheon-evaluation.md`,
`tests/test_rheon_cpu_training.py`, `tests/test_rheon_evaluation.py`. Any additional
optional qualification driver needs a separately bounded write set before selection. Lab/Rheon numerical source writes are **not**
in this Tuldok write set and require a separate owned integration task.

Define adapter-owned field/input/output/stage contract and canonical-release
derivation with lossless array/family/split receipts. Current pressure source has
fixed standalone108→16 model and selected/final weights; do not claim it already
produces probes or physical frame histories. A changed field/stage/gauge/shape
creates new semantics/version/material. The generic query/view stays agnostic to
native numerical methods. Human/agent inspection uses exact values and shared
scales; test mode stays unavailable until all-accessor protection is proved.

Checkpoint: proposed driver `--task field --adapter-project /qualified/project`
uses an actually qualified optional adapter and independent domain oracle, preserves
negative results, reopens captured evidence, checks train-only fit statistics and
H3/H6. If no qualified adapter exists, run generic contract fixtures as contract
checks only and leave this adapter unavailable. Do not substitute fixtures for
required-real physics or delay classifier usefulness. One-fit text/audio driver
checks actual single-fit clocks and frozen reconstruction, no fabricated curve.

### P5: Candidate package and fresh inference

Write: `experiments.py`, `model_definitions.py`, `model_evidence.py`, `runs.py`,
`recipe_contract.py`, `app.py`, `agent_api.py`, `project_cli.py`,
`static/workspace-real.js`; new `tests/test_candidate_packages.py`,
`tests/qualify_candidate_package.py`; `docs/contracts/model-development.md`,
`docs/contracts/agent-operations.md`.

Use normal exact prepared packaging/verifier trial and study-budget seam. Capture
full source/import/transform/weight/runtime/license/input/output closure and enforce
current transitive permissions at all accessors. No generic deserializer in UI.

Checkpoint: actual export/download→whole hash→fresh consumer command
`python tests/qualify_candidate_package.py --package /tmp/exported-package --runtime /qualified/cpu/python --output /tmp/new-inference-qa`
after this driver exists. Remove access to original checkout/cache; independently
compare fixed probes and reject missing/wrong transforms/class order/gauge/runtime/
weights. View selected/diagnostic, package-complete and separately verified states.
An optional numerical evaluator may reject physics while inference reproduces exactly.

### P6: Wider observation and final integrated qualification

Write: `mcp_observer.py`, `mcp_stdio.py`, `agent_api.py`, `app.py`, `project_cli.py`;
new `tests/test_interface_observation.py`; `tests/test_mcp_observer.py`,
`tests/test_mcp_stdio.py`; `docs/contracts/mcp-observer.md`,
`docs/contracts/agent-operations.md`, `docs/contracts/project-cli.md`.
UI/domain lifecycle projections use existing study/Run queries; do not persist
Run/actor/material IDs in passive observer storage or add a second process log.

Implement D2's versioned shared projection/sink with actual request/admission/
dispatch/return/delivery seams, opt-in policy, fresh private v2 store and separate
operator reader/health. Keep v1 stores unchanged and agent arguments/schemas free
of telemetry. Required domain audit failure remains transactional and separate.

Checkpoint: unchanged-client disabled/healthy/full/locked/unsafe/corrupt/partial-
delivery comparisons at actual HTTP/CLI/MCP boundaries plus measured overhead/
retention/private modes, shutdown and broken health sink. Current disposable v1
observer measurements do not qualify new v2 seams. New collection stays disabled
until explicit operator provisioning and boundary qualification. Run complete H1–H7,
headless agent and observation/audit procedures with exact selected implementation.
View operator permitted health separately from domain results. No census/client-
receipt/zero-latency claim or automatic collector activation.

P1 and contract tests can precede costly runtime provisioning. P2 precedes study
execution, P3 precedes classifier activation, P4 optional integration precedes its
capability, P5 precedes generic package/inference claims, P6 precedes whole-interface
observation claims. Each slice owns a useful checkpoint; no “all modules first”
construction wave. Record implementation blockers at their capability, keep the
rest usable and re-plan only material ownership/contract changes.

## Design verification versus product verification

This handoff closes design responsibilities and staged verification requirements.
It does not close H1–H7 or P1–P6 production behavior. A3 is a real-browser **design**
walkthrough; A4 is actual bounded observer/array observation plus explicit unsupported
Torch/scientific producer dispositions. A5–A7 are reviewed design/acceptance/handoff
claims, not proof those future features exist. Public distribution and GPU/adaptive/
resume promises are explicitly excluded with owners/triggers. Independent final
composed-design findings and dispositions are in [design-review.md](design-review.md).
