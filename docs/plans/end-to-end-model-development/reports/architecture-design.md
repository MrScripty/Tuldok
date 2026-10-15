# D1: Workflow, ownership and model authoring

Date: 2026-10-15. Status: independently reviewed D1 recommendation; A1 satisfied for design only; no product
implementation. The [plan](../plan.md) owns acceptance and sequencing. All example
names, edits and journeys below are design examples, not newly executed training.
D2 must work the contracts and real evidence before freezing generic interfaces.

## Recommendation and product consequences

Keep **Pipeline as the sole editable execution-recipe owner**. Experiment
coordination owns comparable trial membership, total budget, selection policy and
candidate decisions; it binds exact Pipeline revisions, never a second mutable
training configuration. A single experiment screen can edit recipes through
Pipeline without making users navigate separate backend concepts.

Support **templates with bounded declarative model configuration and captured
project code** initially. A model definition owns computation, preprocessing and
output interpretation; Pipeline owns its reference and training controls. Use
read-only computation summaries where useful. Defer a general model graph editor:
width, head and input edits do not justify its operator catalog and shape rules.
The workflow graph remains a separate representation of execution stages.

Choose **finite, explicitly enumerated trials**, including repeated seeds, as the
initial tuning mode. The agent may propose the next exact trial after inspecting
validation evidence. It cannot authorize it. Existing built-in starts remain
owner-only; external starts require the existing exact one-use owner grant.
Adaptive search and prospective study grants are deferred. Move identity,
authorization, total-budget and cancellation invariants into D2; D4 retains
detailed scheduling and the implementation handoff.

Select the existing image TinyCNN and a captured pressure-CNN adapter as the two
worked journeys. The optional closed-form pressure adapter is a counterexample
to an epoch-centric interface, not a substitute for iterative training. Rheon
and the surrogate lab retain numerical ownership and are optional integrations.
No code or data there changes in this design task.

The tradeoff is deliberate: recipe variants remain concrete and reviewable, with
more explicit preparation than an open-ended optimizer. Users gain automatic
checkpoint/probe evidence on supported integrations without gaining arbitrary
code safety, universal metrics or automatic physics acceptance. No external
tracking or annotation platform becomes an additional source of truth.

## Source baseline and standards limits

- Freshly fetched `origin/main` and clean checkout both resolve to
  `f58880df84d701ef66ffe21615ae787d80ce8a5e`. D1 branch:
  `docs/model-development-d1`. The initial plan (`18af8ea`) and agent amendment
  (`5e7caf9`) are integrated. No concurrent local implementation was reported.
- The earlier [ownership report](current-ownership.md) records an older checkout.
  This section supersedes its baseline-only statements: MCP observer source and
  [contract](../../../contracts/mcp-observer.md) are now integrated on main.
  HTTP/CLI and long-running domain-lifecycle observation are still gaps. The
  existing observer remains operator opt-in; this work activates nothing.
- Managed Torch/CUDA `d3514c6` remains historical branch evidence, not a current
  main capability verified here. Existing captured CPU runtime and external Run
  custody suffice for the design recommendation. GPU feasibility stays D4.
- No `AGENTS.md` was found in the repository or workspace ancestors. No Coding
  Standards MCP tools/server were exposed in this environment. The retained
  [MCP routing record](standards-routing.md) is prior evidence, not a live D1
  consultation. D1 additionally reads adopted Coding Standards `dcc56f26` Core,
  Router and applicable architecture, contracts, planning, documentation,
  verification and commit guidance through read-only GitHub source retrieval.
  It does not upgrade the adoption pin or claim Engine certification.
- Current code/contracts are authoritative for current behavior. Older design
  reports are evidence of previous investigations. In particular, the five
  classifier payloads plus manifest form six files; neither arbitrary additional
  checkpoint files nor structured scientific histories are accepted by v1.

| Source at this baseline | Relevant fact | Consequence |
| --- | --- | --- |
| [Pipeline documents and validation](../../../contracts/workspace-pipeline.md), [pipeline.py](../../../../pipeline.py) | Checked editable revisions; layout/name excluded from executable identity; invalid semantic drafts allowed; closed task recipes. | Keep draft editing and executable-material validation in Pipeline; never interpret workflow nodes as model layers. |
| [Runs lifecycle/custody](../../../contracts/workspace-runs.md), [runs.py](../../../../runs.py) | Receipt reconciliation, sole supervisor, bounded queue, restart fencing, verified publication and protected classifier test access. | Experiments delegate attempts and artifact custody; a completed Run is not an accepted model. |
| [Actor and grant contract](../../../contracts/actors.md), [access.py](../../../../access.py) | Agents cannot approve review/execution; built-in starts owner-only; external grants bind actor and exact material once. | UI automation and capability discovery cannot confer authority; retry is not a reused grant. |
| [image_training.py](../../../../image_training.py) | Three convolution widths 16/32/64; RGB 96×96 transform; dynamic class head; only best checkpoint plus final predictions survive. | Proposed model editing and checkpoint probes need explicit new contracts; historical evidence cannot be manufactured. |
| [Managed pressure CNN evidence](../../generic-neural-execution/reports/managed-cnn.md) | Captured NumPy CNN, 200 actual Adam updates, train-only normalization, fresh restore; zero of 16 native cases qualified. | Iterative training, custody, inference reproducibility and physical quality are separate. This is prior evidence, not a new D1 run. |
| [Closed-form pressure fitting](../../../contracts/rheon-cpu-training.md), [native evaluation](../../../contracts/rheon-evaluation.md) | Zero optimizer steps for ModalPressure; native field/stage/operator meanings and acceptance remain adapter-owned. | Common evidence exposes applicable clocks/capabilities, not invented epochs or universal residuals. |
| [Agent registry](../../../../agent_api.py#L558), [operation contract](../../../contracts/agent-operations.md) | Bootstrap and each mutation currently demand whole-registry equality. Many workflow steps are excluded. | Capability negotiation requires an owned client/server cutover; adding a server operation alone cannot fix old clients. |

## Configuration authority: alternatives and selected change path

| Alternative | What is authoritative | Benefits | Cost and disposition |
| --- | --- | --- | --- |
| Experiment-owned compilation | Experiment owns release/model/training/evaluation/runtime recipe fields; Pipeline is generated immutable execution material. | Compact experiment-centric editing and compiler-controlled trial expansion. | Credible if replacing recipe editing. Existing saved graphs, UI, CLI and external recipes would need an explicit read-only/import/cutover policy. Otherwise changes can silently diverge. Rejected for the initial design because these actual independent callers still need editable recipes. |
| Pipeline-owned editable recipes | Pipeline owns release/model/protocol/runtime references and training parameters. Experiment owns membership, comparison/selection intent and budget; references exact recipes. | Preserves independent recipe editing and existing admission. One validation and invalidation path for ordinary and study Runs. | More explicit variants. Experiment UI must delegate edits and show pinned versus current revisions. Selected; historical and invalid drafts remain truthful. |

Pipeline owns **binding and executable composition**, not the semantics of the
referenced data, model, evaluator or runtime. For example, model width belongs
only in a model definition; Pipeline has `model_ref`, not a duplicate width field.
Learning rate, seed and epochs belong only in the recipe. A selected evaluation
profile is an immutable reference whose defaults resolve through its adapter;
Pipeline retains the resulting exact execution material. Experiment stores no
independently editable overrides or shadow defaults.

Worked edit sequence (logical operations, not proposed final wire schemas):

1. Create model draft `M1`; publish immutable model revision after inert validation.
   Bind release `R1`, model `M1`, training parameters and resolved profile in
   Pipeline draft `P1/r1`. Invalid drafts can be saved but cannot launch.
2. Validate `P1/r1`; obtain exact source/runtime/input/evaluation material and a
   freshness proof. Freeze that recipe revision as trial material `T1` in study
   revision `E/r1`. Existing Pipeline saves overwrite the current document, so
   D2 must specify retained immutable revision snapshots; a bare `(id, revision)`
   pointing at an overwritten draft is insufficient.
3. Changing learning rate `0.001 → 0.0003` delegates a checked edit/derive to
   Pipeline and creates `P2/r1` (or another retained revision). Study `E/r2`
   references it as `T2`. It never changes `T1`. A finite batch is a list of exact
   references, not a live search-space document or late-bound override map.
4. Concurrent stale saves conflict at Pipeline. Study membership changes use a
   checked study revision. D2 must define atomic pinning, or an exact idempotent
   prepare/attach receipt with detectable orphaned preparation; callers cannot
   synthesize success after half of a cross-owner operation commits.
5. Model width, transform, source, release, profile or runtime changes require
   new dependent material validation and matching approvals; an old unconsumed
   grant remains bound only to its original material and is never transferred. A name/layout change
   leaves executable identity stable, while a changed saved revision still needs
   its normal freshness check. No edit rewrites admitted Runs or prior candidates.
6. Opening a study shows its exact trial material and separately offers a newer
   draft. It never silently follows latest. Removing study membership stops
   prospective admission, subject to cancellation policy; it does not delete
   Run evidence, refund consumed authority or erase audit/exposure history.

Existing graphs remain standalone recipes without compulsory experiment records.
Legacy classifier recipes resolve to their historical fixed model/transform;
D2 chooses explicit versioned model references for new recipes, with old-reader
and downgrade dispositions. No bulk migration is authorized by this report.

## State owners, interfaces and composition

These are responsibilities, not a mandatory file/module count. Proposed calls
below express small semantic interfaces; D2 owns exact schemas and persistence.

| Concern: what and why | Authority, lifecycle and location | Interface and caller obligations |
| --- | --- | --- |
| Editable records and review: current data truth | Workbench and asset owners in existing catalog; checked annotation/source revisions. Human review policy in Access/domain. | Query/import/save draft; request qualified human review. Evaluation links frozen evidence to current record without editing historical targets. |
| Frozen data: stable train/validation/test input | Releases; family-connected split and immutable archives; custody survives study deletion. | Preview then freeze exact reviewed records. Caller chooses meaningful selection/ratios/seed, not splitting implementation. |
| Model definition: computation and inference meaning | New focused model-definition responsibility; immutable published revisions and editable drafts; weights remain Runs artifacts. | Create/edit/validate/publish template configuration or captured code reference. Hide shape/source closure validation; expose unsupported/task mismatch and code-execution boundary. |
| Executable recipe: exact composition | Pipeline; editable revisions, retained trial snapshots and invalidation. | Prepare/derive/validate exact inputs/model/trainer/profile/runtime. Caller sees resolved defaults, resource requirements and material digest. |
| Study/trial/candidate decision: intent across executions | Focused experiment coordination in catalog; immutable trial membership revisions, selection records and total-budget accounting. Candidate record initially belongs here. | Attach exact material, request authorized next trial, compare/select/export intent. No process control, evidence parsing or numeric thresholds invented here. |
| Attempts and bytes: execution/custody | Runs, existing supervisor and verified artifact publication. | Submit/reconcile/status/cancel and scoped reads. Request receipt is not completion; cancellation remains pending until cessation is proven. |
| Task evidence and numerical meaning | Versioned adapter declarations/evaluator plus focused evaluation query responsibility; durable bytes stay in Runs. | Resolve profile; validate checkpoint/probe/field evidence; query bounded metrics/rows/windows and comparison admission. UI/agents supply selection, never parse opaque files themselves. |
| Runtime and source capture: exact executable environment | Existing Projects, RuntimeSnapshots and recipe/process custody; provisioned independently. | Inspect/preflight/capture through current owners; missing capability is explicit. No package install or model load on draft edit/open. |
| Permissions, required audit and exposure | Access and existing domain transactions; current authority checked at every serving/admission boundary. | Inspect permissible capabilities; owner grants/review; transactional audit. References and hashes grant no permission. |
| Human and agent presentation | HTTP/browser and registered MCP/CLI projections of the same owners. | Render structured evidence and typed outcomes. No shadow recipe store, numerical algorithm or workflow truth inferred from telemetry. |
| Passive observation | Integrated MCP observer; future approved interface seams and separate operator reader. Independent opt-in store and bounded lifecycle. | Composition configures once; ordinary clients have no telemetry obligations. Recording failure degrades diagnostics alone. |

The composition root supplies existing catalog/lock/access/custody owners, the
supported model/task adapters and operator observation policy once. Adapters
register bounded capabilities with semantic versions, not a new persistent
plugin marketplace. The ordinary user supplies data, model, training goal,
finite budget and required human decisions. The coordinator hides trial
bookkeeping; it does not hide cost, missing evidence, ordering or authority.

## Model-authoring comparison using the same real edits

Both template forms and a structured editor update one typed, adapter-specific
model specification. Neither creates an independently writable graph or code
copy. Draft inspection validates declared metadata without importing/executing
model code; active smoke inference is a separately authorized Run. A captured
configuration JSON may be an ordinary adapter input rather than an expansion of
the generic recipe scalar-parameter grammar.

| Concrete requested edit | Template/form | Declarative configuration | Computation graph | Captured code and selected behavior |
| --- | --- | --- | --- | --- |
| TinyCNN widths 16/32/64 → 24/48/96 | Bounded width controls if qualified by the template. | One widths tuple; derive final head input 96. | Would edit three convolution nodes and dependent dimensions. | Current v1 is fixed in source. Requires a new qualified model/adapter version; never insert fields into v1. Select typed options in the new supported template. |
| Classifier head and input changes | Class count derives from frozen release vocabulary, not a free count. RGB → grayscale requires an explicitly supported input option. | Bind class order, transform and input channels; reject incompatible checkpoint reuse. | Shape checks still need channel/label semantics; nodes alone are insufficient. | Current RGB96×96 and class-bound head are the baseline. A changed task/head/transform gets new model material and compatible trainer; unsupported options go through captured source qualification. |
| Pressure input channels RHS+x/y/z → RHS only | Do not offer an unqualified checkbox. | Only an adapter-qualified option could derive 108 → 27 features. | Removing coordinate nodes does not automatically repair checkpoint loaders or gauge-aware gradients. | Revise captured encoder/model/restore source together. Existing kernel[108,16] cannot load a 27-feature model. Source revision is the initial path. |
| Pressure hidden width 16 → 32 | No current width control; recipe exposes steps only. | Future typed model option must qualify all fitted and restored shapes. | A graph can show tanh/head connectivity, but current restore still expects kernel[108,16], bias[16], output[16]. | Capture new initializer and loader source/shape specification; new model identity. No pretending it is an existing generic recipe scalar. |
| Pressure normalization or output gauge | A user-facing label cannot certify numerical meaning. | Declare train-only fitting policy, pressure RMS inversion and gauge policy; fitted values remain Run artifacts. | Same-shaped graph may still change pressure/reference meaning. | Source/evaluator revision required for changed gauge or fit semantics. Cell-zero subtraction participates in the current analytic gradient; outputs/evaluator must agree. |
| New residual block, architecture or external custom model | A template can select only already integrated options. | Configuration cannot invent an undeclared operator. | Editable topology is useful only with a supported operator/shape/serialization contract. | Use captured source/import closure plus task/evidence adapter. Unsupported instrumentation remains explicit; do not infer automatic probes from arbitrary output JSON. |

The pressure examples use actual source at lab
`2a49aa81a26efc8ccbfdc3f756b39ccd5019ff15`:
[encoder, normalization and gauge-aware model](https://github.com/MrScripty/rheon-surrogate-lab/blob/2a49aa81a26efc8ccbfdc3f756b39ccd5019ff15/scripts/train_cpu.py#L40),
[fixed checkpoint loader and reconstruction](https://github.com/MrScripty/rheon-surrogate-lab/blob/2a49aa81a26efc8ccbfdc3f756b39ccd5019ff15/tuldok/cnn.py#L73),
and [recipe bounds](https://github.com/MrScripty/rheon-surrogate-lab/blob/2a49aa81a26efc8ccbfdc3f756b39ccd5019ff15/tuldok/cnn_project.py#L63).
The encoder forms zero-padded 3×3×3 neighborhoods over four channels (108
features); 16 tanh hidden units produce scalar pressure with cell-zero gauge.
Training fits RHS mean/std and pressure RMS from train cases only. Inference
inverts pressure RMS. These examples establish authoring consequences, not
physical validity or a proposed edit to the lab.

**Selected initial authoring surface:** template forms plus bounded structured
configuration in Tuldok; import captured project source and provide a small
text-edit/revision surface for supported text source files when custom source
editing is needed. Import and edit use the same source-capture owner and publish
a new immutable closure after validation; no full IDE, code/graph round-trip or
execution on inspection. A source edit can leave an invalid draft; it cannot
silently widen the adapter's supported task/evidence capabilities. Source import
is the initial useful path and the lightweight editor is a reversible product
recommendation for design review, not an independently required service or a
blocker to D2. A later demonstrated topology-editing need can reopen the graph
choice with concrete operator and accessibility obligations.

Model policy owns architecture and preprocessing/reconstruction **rules**.
Training produces fitted transform **values** and weights under Runs custody.
This avoids moving fitted statistics into editable metadata or putting learning
rate in both model and recipe. Task adapters own losses, evaluator semantics and
default profile meaning; Pipeline resolves/binds their versioned references.

## Complete classifier journey

All identifiers in this journey are illustrative. “Proposed” means absent from
the current product contract and still requiring D2/D3 design verification.

| Step | Human interaction and authoritative transition | Structured-agent path, ordering and observation |
| --- | --- | --- |
| 1. Acquire and annotate | Import images through supported Data owner, inspect sources, edit labels and family metadata in Workbench. | Discover supported image import first; use `data.import_image`, `data.query`, `data.save_draft` and current revisions. Raw payloads stay outside passive logs. Import/generation modes absent from discovery stay unsupported. |
| 2. Review and freeze | Qualified human approves review; preview connected-family splits and freeze `R1`. | Agent requests review, waits for owner action, then uses `releases.preview`/`releases.freeze` with freeze scope and exact preview token. An agent cannot mark its own work human-reviewed. |
| 3. Edit model | Start from current 16/32/64 TinyCNN. In proposed configuration change widths to 24/48/96; head input follows final width, output follows frozen class vocabulary. RGB resize remains 96×96. Publish `M1`. | Proposed model operations return shape/task checks and exact model identity, not executable arbitrary code. No Run starts on validation. Existing image recipe has no such width field today. |
| 4. Prepare recipe/study | Pipeline binds `R1/M1`, three epochs, batch 8, LR 0.001, seed 42 and qualified CPU. Resolve and show default validation-only profile, fixed probes, checkpoint cadence and storage envelope; attach exact material as `T1`. | Proposed prepare returns resolved material and missing capabilities. Check exact revision, source, vocabulary, transform and required-evidence capability before admission. No agent callbacks, chart setup or logger fields. |
| 5. Admit training | Owner reviews material and starts through Runs. An owner-only built-in start is still a human gate; a future agent-enabled built-in grant path requires explicit design. | Agent can propose and monitor, but current `runs.submit_external` cannot launch a built-in classifier. D2 records this transport/authority gap. Admission/required audit commit together; passive observer cannot replace them. |
| 6. Capture automatically | Proposed supported adapter saves bounded end-of-epoch checkpoints with validation probe predictions from those exact weights in inference mode; selected checkpoint remains minimum validation loss. A one-epoch run has one observation. | Poll Runs for lifecycle; proposed evidence queries return checkpoint/probe IDs, class order/probabilities, epoch and completeness. Live values are provisional; verified retained evidence is separately published. D3 measures cadence/caps rather than declaring three epochs universally affordable. |
| 7. Inspect | UI opens history/confusion/errors and one fixed example across checkpoints; frozen target/input is visible. Test remains gated. | Query the same validation evidence, confusion rows and fixed-example predictions with bounded pages. Distinguish no evidence, missing required artifact and observed zero. Prior v1 Runs expose only best-checkpoint final predictions. |
| 8. Correct or tune | Correct a current label in Workbench, obtain human review, freeze `R2`, derive a recipe and new trial. Or keep `R1/M1` and change LR to 0.0003 in a new Pipeline recipe. | Agent links errors to record and frozen source revisions, proposes edits and an exact next trial. Dataset-changed trials are shown side by side with changed membership; only compatible fixed validation memberships receive paired deltas. Owner still authorizes each start. |
| 9. Compare/select | Compare validation criteria, failures and repeated seeds if explicitly enumerated. Human or authorized selection policy records a candidate from an exact verified checkpoint and evidence set. | Proposed candidate operation records explicit policy/actor and limitations. No test-driven tuning or selection from incomplete required evidence. Exposure requires separate scope and durable disclosure; it never becomes routine gallery input. |
| 10. Export and verify | Request proposed complete inference package; export status distinguishes selected, package-complete and fresh-consumer-verified. A later acceptance procedure restores the package and predicts the fixed probes in a fresh consumer. | Proposed export checks current access for each transitive artifact, returns a verified bounded inventory and permitted download handle. Download hashes prove bytes only. Fresh-consumer numerical acceptance is pending, not satisfied by the existing checkpoint file. |

Text TF-IDF/MultinomialNB (`max_features`, `alpha`) and audio logistic fitting
(`C`, train-only scaling and fixed WAV interval features) reuse the same
freeze/recipe/trial/inspection/selection structure. They declare one fit result,
not an epoch history. Their plain JSON models, text vocabulary/IDF, audio
rate/channel/frame identity and preprocessing stay authoritative. No fake
checkpoint trajectory, gradient trace or neural resumability is added.

## Complete scientific pressure-model journey

This exercises an existing captured pressure-CNN path and names missing generic
features. It does not require a live solver to train/infer captured data. Native
physics validation is a distinct optional integration and execution.

| Step | Human interaction and authoritative transition | Structured-agent path, ordering and observation |
| --- | --- | --- |
| 1. Acquire and review fields | Use previously captured pressure/RHS cases with source/scene/seed/family, stage/grid/time/dtype/mask metadata. New native generation, if needed, is separately approved execution. Inspect and human-review scientific assets. | `projects.open` is inert. Discover scientific import/inspection operations; import verified Run artifacts through `data.import_*_scientific` when supported. Core never generates units, gauge or solver meaning from array dimensions. |
| 2. Freeze data | Releases freeze reviewed scientific cases and connected seed/family groups. Bind train/validation/test membership before training. | Current captured CNN uses project NPZ plus persisted splits (8/4/4 in prior evidence), not a generic Releases-backed CNN reader. D2 must specify the adapter bridge from canonical frozen releases to captured model inputs, including hashes, whole-family membership and train-only normalization. Until qualified, that bridge is unsupported; do not claim the prior NPZ was human-reviewed or a Tuldok release. |
| 3. Edit model | Register lab-owned captured source as a model definition. The radius-one CNN is a concrete baseline; changing its receptive field/input channels is a code-and-shape edit, not a scalar learning-rate tweak. | Proposed model operations reference captured source/reader/preprocessing/output closure. The lab author supplies revised implementation/qualification separately; this D1 task edits neither lab nor Rheon. Core validates declared compatibility, not the physics. |
| 4. Prepare exact trial | Pipeline binds frozen inputs/splits, model/source/runtime, step count and adapter evaluation profile. Experiment attaches that exact material with finite budget and explicit numerical selection constraints. | Existing `graphs.create_external`, `graphs.save`, `graphs.preflight_external` cover captured recipes. Model/automatic-evidence bindings are proposed. No silent substitution of the closed-form ModalPressure adapter for this iterative model. |
| 5. Authorize/train | Owner reviews material and grants its consuming agent one launch; agent uses `runs.submit_external` and retains the durable receipt. | Reconcile the same request key after lost acknowledgement before proposing retry. A new attempt requires fresh authorization. The captured CNN performs Adam updates; prior evidence establishes training, not current model quality. |
| 6. Capture/check | Proposed pressure adapter emits declared checkpoints, fixed validation case predictions, train-only normalization and update-index history automatically. Pair pressure/reference fields by exact case/grid/stage/time and declared gauge convention. | Proposed bounded field queries expose actual arrays, masks, field placement, unit status and update versus physical-time clocks. No hard-coded pressure operator in generic core. Missing required checkpoint/probe evidence is incomplete/failed under the selected protocol, never fabricated from scalar loss. |
| 7. Inspect physics and errors | UI uses shared prediction/reference scale and a separate error scale; show amplitude errors, not independent autoscaling. Review task-owned relative pressure errors and declared native checks separately. | Agent queries numeric errors/windows and declared acceptance outcomes. Existing native evaluation has specific MAC/grid/stage semantics and unspecified native units; generic views must preserve those limits. A tenfold amplitude difference must remain visible and numerically detectable. Native checks require separately approved captured evaluator inputs. |
| 8. Authorize next trial | Inspect validation failures; derive exact model/recipe change (e.g. revised receptive-field source supplied by the lab author, or a supported learning-rate parameter), re-preflight, reserve total budget and obtain a new exact grant. | Agent can propose finite variants and compare validation, never loosen domain thresholds or infer a study-wide grant. No test tuning. Cancellation stops future admissions first, then requests Runs child cancellation and reconciles cessation. |
| 9. Select candidate honestly | Record an exact checkpoint plus normalized inference/output semantics and validation/domain evidence. Prior radius-one CNN remains diagnostic: reported native qualification is 0/16. | Failed physics excludes a production-qualified candidate under that policy. A permitted diagnostic candidate can retain failures and export only with explicit diagnostic status. Selection/export cannot relabel it physically accepted. |
| 10. Export and later fresh inference | Proposed package contains weights, lab inference/reader source, normalization, split/probe identities, runtime/array contract and evidence closure. Consumer inference on fixed captured probes must work without live lab checkout or Rheon. | Later fresh-consumer verification consumes only package plus separately provisioned compatible runtime and permitted probes; compare owned outputs/tolerances. Native rollout acceptance is separate and may still fail. No such generic candidate package or acceptance was implemented/run in D1. |

The optional ModalPressure adapter consumes six canonical scientific releases and
reports a closed-form fit with zero optimizer steps. Its native evaluation binds
checkpoint, freeze, training inputs and result from one completed Run. Those
real independent semantics justify task-owned evidence capability declarations;
they do not justify a universal scientific trainer or seven permanent modules.
If the canonical-release bridge or pressure checkpoint capture cannot meet D2's
contracts, keep that integration unsupported and revisit only the dependent
interface. Do not freeze a generic interface on a classifier-only example.

## Initial tuning invariants: D1 choice and D2 obligations

The selected mode permits a single next trial or a finite enumerated list with
explicit seeds. A future adaptive optimizer may propose finite next material,
but no autonomous prospective policy authority is selected.

| Invariant | Responsible owner and D2 proof obligation |
| --- | --- |
| Trial versus attempt | Experiment owns immutable trial identity for exact Pipeline material/seed/profile; Runs owns each attempt and parent/retry lineage. Repeating a seed is explicit trial membership; retrying unchanged material is a new attempt, never a new result hidden inside an old attempt. D2 decides content deduplication versus deliberate replication identity. |
| Permission is current and exact | Access/Runs preserve live actor checks and exact one-use external grants; built-in start and human review remain owner-only. Changed recipe/source/runtime/protocol material requires new preflight/authorization. Selection/export permissions do not imply execution or protected-data exposure. |
| Aggregate budget cannot multiply | Experiment owns the study ledger; Runs owns per-attempt ceilings and enforcement. Before a launch, atomically reserve worst-case admitted compute/wall/storage/capture allowance including required automatic evaluation. Do not double-charge reconciliation or refund uncertain work. Failed/retry attempts consume budget. D2 specifies conservative accounting, concurrent reservations and how existing per-Run bounds compose. D3 measures default numeric allocations. |
| Cancellation closes admission first | Experiment records stop/no-more-children before requesting cancellation of every admitted child through Runs. Cancellation is not success until known children cease. Unknown child state fences new admissions and keeps its reservation. D2 specifies crash windows and restart reconciliation; D4 chooses detailed queue scheduling. |
| No implicit replay on restart | Reopen reconciles retained receipts and unknown states; it does not launch queued study proposals or recreate consumed grants. Explicit authorized continuation rechecks current budget, permissions and material. Previously admitted bounded children retain only their existing continuation effects after credential revocation. |
| Selection uses comparable validation | Evaluation owns comparison admission; experiment policy ranks only eligible evidence and records failed/missing trials. Test evidence is excluded from tuning. Dataset-changing trials disclose changed groups and cannot masquerade as paired validation on unchanged probes. |

These are design invariants, not claims that the current application has an
aggregate study budget or atomic study/Run reservation. D2 must resolve that
transactional seam before any automatic finite-batch launch is implementable.

## Candidate package closure and future acceptance

A candidate decision is not an inference package and a complete package is not
numerical acceptance. Initially the experiment owner records selection; Runs
retains/verifies package bytes. No separate candidate registry, model-serving
service or runtime installer is justified.

Package closure must identify and retain, or explicitly declare separately
provisioned under a compatibility contract:

- Selected checkpoint bytes and format/loader restrictions; immutable model
  definition/configuration and source/import closure, with no mutable repository
  path or missing external default required for inference.
- Exact preprocessing and train-fitted statistics; image resize/channel/class
  order, text vocabulary/IDF, audio scaling/features or pressure normalization,
  field placement/gauge/output reconstruction as applicable.
- Task/input/output schemas, supported dimensions/dtypes/units/masks and inference
  mode; runtime requirements or exact qualified runtime reference and permitted
  platform constraints. A runtime hash alone does not provision that runtime.
- Dataset release/split/probe membership and source lineage; evaluation protocol,
  producing checkpoint, selection criteria, numerical results and limitations;
  access/exposure policy and permission-checked distribution inventory. Private
  training records may remain protected references; fixed acceptance probes must
  be included when permitted or explicitly supplied through an authorized owner.
- Manifest of all inference dependencies, hashes, sizes, versions and licenses;
  reconstruction entrypoint and bounded fixed-probe expected outputs/tolerances
  owned by the model/evaluator. Optimizer state and resume are optional separate
  promises, never inferred from retained weights.

Later product acceptance must export through the actual interface, download and
verify the whole inventory, then open a **fresh consumer process** with no live
catalog, original project checkout or ambient model cache. Supply only the package,
its declared compatible runtime and authorized fixed probes. Reconstruct inference
and compare class probabilities/pressure outputs to owned expected values under
declared exactness/tolerances. Reject missing preprocessing/class order/source,
wrong checkpoint, incompatible runtime, tampered bytes and unauthorized probes.
Inference must not need a new training launch, telemetry setup or native solver.
Native physics acceptance, when requested, is a separately authorized evaluator
and independent criterion. D2/D4 specify exact package schemas and procedure;
this generic export/fresh-consumer acceptance remains pending implementation.

## Reuse versus owning orchestration

Official precedents were inspected in the earlier [software comparison](../../training-evaluation/reports/software-precedents.md);
Label Studio, MLflow and Lightning primary docs were re-opened for D1. Patterns
are evidence, not dependency adoption or runtime qualification.

| Choice | Product/ownership effect | D1 disposition and revisit trigger |
| --- | --- | --- |
| Tuldok owns connected data/recipe/Run/evidence journey | Preserves family/review/freeze, exact byte custody and current access. Adds bounded model/study/evidence semantics where current owners lack them. | Selected. Maintain one coherent projection across browser and agents; no second execution queue or artifact store. |
| Label Studio for annotation integration | An external annotation owner/backend could add review integration, but identity/review/exposure mapping still needs an explicit import boundary. | No replacement/adoption selected. Revisit if a required annotation capability demonstrably exceeds Workbench. [ML backend integration](https://labelstud.io/guide/ml.html). |
| MLflow for tracking/autologging | Framework-specific autologging still needs an enabled integration; handwritten Torch loops are not covered by its Lightning-only PyTorch route. Another tracker cannot replace exact release/Run custody or infer field meaning. | No tracking server/SDK selected. Revisit a concrete external tracking consumer with one-way, access-filtered projection and an owned lifecycle. [Autologging](https://mlflow.org/docs/latest/ml/tracking/autolog/). |
| Lightning callbacks for supported Torch adapters | Reuses lifecycle hooks when an adapter already uses Lightning; switching this small handwritten trainer would add framework/runtime/checkpoint compatibility work. | Keep existing loop and design bounded adapter capture first. Reconsider only if required training capabilities make lifecycle reuse cheaper with license/runtime proof. [Callbacks 2.6.6](https://pytorch-lightning.readthedocs.io/en/2.6.6/pytorch/extensions/callbacks.html). |
| Declarative toolkits/vision platforms and error workbenches | Show useful config-driven training and metric-to-example review patterns; do not establish universal graph or scientific validity. | Reuse interaction ideas from retained precedents, with no new dependency. D4 selects a package only if it replaces required work under an explicit license/maintenance owner. |

## Change paths, invalidation and deletion review

| Concrete change | Semantically forced owners | Preserved independent behavior |
| --- | --- | --- |
| Correct image label | Workbench/review → Releases → Pipeline binding → new trial; Runs and evaluation consume new exact input. | Prior targets/probes/weights remain immutable. Family exposure survives reimport; changed membership is explicit in comparison. |
| Change CNN width/head/input transform | Model semantics/source → Pipeline compatibility/material → new trial/Run; task evaluation only if output meaning changes. | Study selection policy, observer schema and workflow graph topology need not change. Head dimension validates against vocabulary; no duplicate layer widths in recipe. |
| Add a new plot of existing evidence | Evaluation query/view descriptor → UI renderer; agent query semantics shared. | No retraining, recipe change or source material invalidation when underlying retained evidence meaning is unchanged. |
| Add recurring checkpoint probes | Adapter/profile/evidence contract → Pipeline material → Runs inventory/verification → query/view/agent projection. | Old v1 Runs remain readable with unavailable history. This is a producer/contract change, not a chart-only patch. |
| Add finite learning-rate/seed variants | Pipeline derives exact variants → experiment membership/budget → Access/Runs admission → evaluation comparison/candidate. | No second supervisor, hidden retry, generic optimizer service or test-driven selection. |
| Replace optional pressure adapter | Project/model/evaluator closure → Pipeline compatibility/material and new trials. | Generic scientific data, classifier training, Runs custody and passive observer work without Rheon. Core never imports its numerical methods. |
| Add unrelated server operation | Interface registry/discovery and appropriate owner; negotiate compatible operation subset. | Existing compatible operations stay usable on negotiated clients; an incompatible mutation alone fails closed. Legacy exact-registry clients need coordinated upgrade. |

| Proposed permanent mechanism | Deletion result and selected containment |
| --- | --- |
| Model-definition responsibility | Removing it repeats computation/shape/preprocessing/source identity across recipe UI, agents and trainers. Retain focused definitions, not a new serving registry. |
| Experiment coordination | Removing it repeats trial membership, aggregate budget, comparison policy and selection across callers. Retain as one focused owner; candidate decisions stay here initially. |
| Evaluation semantics/query seam | Removing it makes UI/agents parse artifacts and invent units/comparison rules. Retain semantic queries over Runs custody, not a viewer store. |
| Adapter capability declarations | Needed by two distinct iterative journeys plus one-fit/closed-form modes. Keep with supported adapters and negotiate schema compatibility; no discovery daemon/marketplace. |
| Retained immutable recipe snapshots | Necessary because mutable Pipeline documents cannot reconstruct older unattached trial material. Put retention in Pipeline, reuse Run snapshots when admitted; D2 bounds pre-admission retention/cleanup. |
| Checkpoint/probe evidence contract/version | Deletion makes automatic history impossible or corrupts v1 promises. Retain only required bounded evidence, with D2 explicit old/new consumers; no universal telemetry format. |
| Separate candidate registry, dashboard store, universal graph editor, study process supervisor | Deletion removes incidental machinery while existing owners can provide the requested journey. Declined. |
| New passive recorder | Existing integrated MCP observer already contains its privacy/lifecycle obligations. Reuse; add HTTP/CLI/domain seams only where justified, without domain-ID leakage or per-agent setup. |

Eight composed-design probes have concrete dispositions:

1. **Independent concerns and dimensions:** data/review/freeze, model computation,
   executable composition, study intent, attempts/custody, numerical evidence,
   access and presentation have distinct change reasons, owners and lifecycles
   in the state/interface table. Product unity does not combine authority.
2. **State/identity/value/time/policy/mechanism:** checked draft ordinals differ
   from immutable material IDs, public schema versions and database migrations.
   Optimizer updates, fit passes, physical frame time and wall time remain distinct.
   Semantic owners retain policy; Pipeline composes references. D2 classifies
   exact version overlap/consumer migration and proof on real retained examples.
3. **Caller/root knowledge:** callers choose data/model/goals/finite budget and
   act on explicit review/grant gates. Composition wires owners/capture once.
   Exact material, bounds and typed missing/unknown outcomes remain visible;
   no filename parsing, callback wiring or hidden latest-version binding.
4. **Change locality:** the seven worked paths above identify forced propagation
   and protected independent behavior, including ordinary graph editing outside
   studies and deletion of the optional pressure integration.
5. **Stable interfaces/hidden knowledge:** immutable references, bounded semantic
   queries and Run receipts carry meaning. Physical file layout, source import
   tracing, numerical operators and process identity stay behind their owners.
   Current registry equality is an exposed version coupling requiring migration.
6. **Independent evolution/failure/replacement:** inert edits can fail validation
   without launching; denied/revoked authority prevents new work; admitted children
   keep bounded continuations. Required evidence failure blocks completeness;
   optional observation failure preserves business outcomes. Partial publication,
   cancellation, unknown/restart and old-read compatibility go to explicit D2
   contracts, with no alternate authority or fabricated success.
7. **Deletion:** each retained responsibility hides necessary caller work in
   the deletion table; declined mechanisms have no independent current need.
8. **Cumulative machinery:** retain model definitions, study/candidate intent,
   semantic evaluation, bounded adapter declarations and necessary immutable
   snapshots/evidence evolution. Reuse Releases, Pipeline, Runs, access, runtime,
   transactions and integrated observer. This is a proposed composition, not a
   service count, filesystem plan or production admission.

## D1 review and verification record

An independent **GPT-6.1 Sol** reviewer (`d1_independent_review`, read-only,
separate context) reviewed all six D1 files against Pipeline, Runs, Access,
AgentClient, image training and optional scientific contracts, and the three
pinned lab sources. Result: **no blocking D1 findings**. It confirmed singular
recipe authority, both full journeys, concrete authoring choices, capability
negotiation/current authorization and the three distinct record obligations.
No findings required a design correction. Primary writer additionally clarified
that changed material cannot reuse an old grant, while the original grant stays
bound to its original material, and normalized plan lifecycle to `Active`.

| Check / procedure | Actual result and proof limit |
| --- | --- |
| Adopted upstream `validate_plan` | Passed using original AST/constants/helpers before the first checker class, standard-library-only, as in the earlier reproduction procedure. Fetched from Coding Standards `dcc56f26`, `tools/standards_verifier/standards_verifier/checks/plan_contract.py`, SHA-256 `c7266c0564b9ee02944fc4eb12d66cc20d604fd4ddb7f051ed77d01e9fe4466e`. Structure only, not architecture certification. |
| Markdown/HTML links and anchors | Disposable standard-library checker resolves local targets, Markdown heading anchors, source line bounds and HTML IDs; also checks table columns and balanced code fences. All pass across 10 Markdown files: 176 local links and 104 anchors, plus the HTML. Historical external citations are not all revalidated. |
| HTML structure and assets | Unique IDs, balanced nesting, local links and no remote script/style/image/frame dependency pass. No product prototype or automatic-training behavior is proved. |
| Actual document rendering | Chromium via existing Playwright at 1440×1000 and 390×1000: title/content present, no page script errors or body overflow, four phase disclosures present, keyboard Tab/Enter skip link reaches main. Desktop screenshot inspected. Direct file navigation was blocked by browser policy; serving the same static report directory on loopback HTTP passed. No browser/dependency install. Temporary screenshots are not committed outside D1's write set. |
| Whitespace and scope | `git diff --check` and new-report full-file `git diff --no-index --check /dev/null` pass. Exact six allowed documentation files changed; no application, lab/Rheon or user-data edits. Staged diff/history are reviewed before commit. |
| Application/product tests | Not run: no application behavior changed. No training, migration, telemetry activation or generic candidate/fresh-consumer inference acceptance was executed. |

These observations close **A1**: reviewed design ownership, journeys and authoring
choices. A0 retains its prior source/routing scope with the refreshed D1 baseline.
**A2–A7 remain pending**: exact contracts/consumer cutovers and finite-study
transactional proofs (D2), actual capture/field observations and interaction/cost
procedures (D2/D3), detailed scheduling/runtime/package and implementation handoff
(D4). A source report, checked diagram and document-rendering smoke cannot satisfy
those product or later design claims. Next stage is D2, not application coding.

D1 source-backed defaults can proceed without a required new user decision.
The proposed lightweight source editor and deferred editable topology support
remain reversible recommendations for design review. Live Coding Standards MCP
consultation was unavailable; adopted source and retained routing are supporting
guidance, not an Engine approval or new standards adoption.


## D4 reconciliation of the D1 recommendation

The D1 review/next-stage text above is historical. D2 selected concrete contracts;
D3 selected the compact contextual walkthrough and bounded unsupported runtime
disposition; D4 completes scheduling, migration and implementation ownership.
[Final composed review](design-review.md), [workflow design](workflow-design.md),
[handoff](implementation-handoff.md) and [architecture decision](../../../decisions/model-development-architecture.md)
now carry that continuation. Pipeline remains the sole editable recipe owner;
no later stage introduced another supervisor, configuration owner or universal
graph editor. Input/output fields and workflow stages evolve through explicit
adapter/model/schema versions; authored trajectory evidence supplies no inferred
pressure-model capability. Built-in owner-only launch and exact external grants
remain distinct. New model-aware capture and optional scientific integrations stay
unavailable until their actual producer/runtime/access gates pass. Design closure
does not upgrade the historical D1/D2 or authored prototype into product acceptance.
