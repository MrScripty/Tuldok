# P5b admission proposal: reviewed scientific inputs to unchanged ModalPressure.fit

**Status: ADMITTED for isolated source preparation; real fitting not yet qualified.** Reviewed 2026-10-13. P5a actual runtime, model comparison, restart and no-adapter gates passed and were published as draft PR50 at05ea66e. Full regression and hosted CI are running against that unchanged checkout. Within the same active P5 stage, source preparation may proceed in the separate feature/scientific-frozen-training-20261013 worktree. Dependent real generation/model qualification, acceptance and branch promotion wait for P5a regression/CI success; any P5a fix must be propagated first. This is an explicit sequencing amendment, within the user's already authorized milestone scope. No additional user permission gate is introduced. This is a fresh CPU fit from frozen reviewed records, not historical CUDA reproduction or new holdout qualification.


## Standards disposition and current integration facts

This report supports [the active parent plan](../plan.md); it does not replace its G4/G8 acceptance or current next slice. Reviewed adopted Coding-Standards revision `dcc56f26e884ade260770beceba2501d3746200d`: Core, Router, Planning, Implementation, Verification, Development Proportionality, Documentation, Code Design and Contract Evolution. Apply ownership through existing Releases/Pipeline/Runs, compatibility through retained binding bytes, and required-real verification through actual consumed arrays and lifecycle/UI results. No Standards Engine certificate is claimed. The smallest next implementation is the generic frozen-input union plus captured cold reader, followed by the optional training adapter and real workflow; no second scheduler, graph engine, parser or new database schema is justified.

Verified current entry points (all paths relative to repository root):

- `pipeline.py`: `Pipelines.create_external(body)`, `save(graph_id, body)`, `preflight_external(graph_id, revision)`, `capture_external(graph_id, revision, expected_digest, staging)` and `validate_graph(graph)`. All three current `recipe_contract.prepare(...)` call sites must receive the new release owner; graph save continues `{revision, document}` optimistic concurrency.
- `recipe_contract.py`: `graph_parameters(graph)`, `prepare(projects, graph, execution_sha256, profile=None)` and `validate_material(material)` own binding decoding and captured identity. `projects.py:Projects.read_data_reference(project_id, reference_id, expected_sha256, limit)` remains the original project-input branch unchanged.
- `dataset_releases.py:Releases.locate(release_id)` returns a managed archive path; `create(body)` owns freeze. Add the proposed bounded `capture_input` here, not a caller-supplied path reader in Runs.
- `runs.py:Runs.approve_external(body)` and `submit_external(body)` already own digest-bound grants, consuming actor, same-key reconciliation and admission. The input change flows through those methods; it does not add an execution endpoint or loosen permissions.
- `static/workspace-external.js` owns both `WorkspaceExternal` saved editing and `WorkspaceExternalProject` graph creation. Creation currently only lists `project.data`; saved editing shows input JSON but cannot change it. This is the primary UI write owner. `static/workspace-projects.js` already delegates creation to it; do not modify that file unless a concrete interface change requires it.
- Existing HTTP routes: `/api/workspace/graphs/external`, `/api/workspace/graphs/{id}`, `/api/workspace/graphs/{id}/preflight-external`, `/api/workspace/runs/approve-external`, `/api/workspace/runs/submit-external`. Reuse these bodies/routes. Data freeze remains `POST /api/workbench/releases` and preview its `/preview` suffix.
- Existing `GET /api/workspace/releases` calls `Pipelines.releases()` and `inspect_release()`, which select built-in training/integrity recipes and currently do not admit scientific fields. Do not pretend this list already supplies scientific choices or add a Rheon branch. Proposed generic `Releases.input_candidates()` returns bounded managed archive identities `{release_id, sha256, bytes}` only, through new `GET /api/workbench/releases/input-candidates`. It lists at most the existing 100-release UI budget, accepts no user path, and reports unavailable/oversize files explicitly; the capture method rechecks bytes. The optional consumer remains responsible for scientific validity. Reuse an equivalent existing generic owner if one lands before integration; do not maintain two candidate catalogs.

Dependency order and runnable checkpoints:

1. Capture and cold-reader closure with compatibility/boundary tests. Add source-only generic binding editing and save/reopen UI; preflight remains fail-closed until all six inputs are bound and reader qualification succeeds.
2. Optional release-consuming CPU training recipe with strict array/wire/family checks and unchanged fit/validation algorithms. Keep G4 pending until real model evidence exists.
3. Generate the twelve actual reference trajectories, import, perform authored QA owner inspection/review and freeze six bounded releases. Measure archives and finalize the approved input material before executing the fit.
4. Run real CPU fit and validation, then original autonomous evaluation on the resulting checkpoint (120 frames, seeds 900–903, previously exposed). A follow-on evaluation wrapper must accept the newly measured checkpoint/freeze identity without altering P5a's historical pins. Fit alone does not complete G4. Verify full-field comparisons, physics diagnostics, restart/restore and desktop/narrow/keyboard monitor/results.
5. Record exact source/runtime/input/output hashes, test results and browser evidence in the parent ledger. Parent owns status updates, commit/push/draft PR and independent review. No merge/deployment change is authorized here.

## Measured source facts and size budget

Pinned original lab scripts are under /workspace/scratch/tuldok-science-probe/lab/scripts. trajectory_experiment.train generates seeds 100..111, eight frames each (historical freeze), stacks full RHS and pressure as float64 [96,32768], calls unchanged ModalPressure.fit, writes training.npz and model.pt, validates seeds 500/501 for 60 frames, and checks rejection of unit-gain ablation. Its train entry point cannot consume frozen releases: it regenerates inputs and calls live Git provenance(). Therefore add optional adapter orchestration invoking unchanged fit/compare/rollout, not a claim that original train itself runs unchanged. Do not patch the originals or fake Git provenance.

The fit is the original excited-mode positive finite closed-form least-squares fit; no new optimizer, inverse, reduced modes, resampling, downcasting or analytic initialization. Keep all 96 observations in ascending seed then frame order.

At n=32, each frame contains RHS/pressure 524288 bytes, face velocities 405504 bytes, tracer 131072 bytes: 1060864 numerical bytes. 96 frames total 101842944 bytes. Preserving exact native wire plus all six NPY arrays doubles that payload to 203685888 bytes (194.25 MiB), before headers, reports and receipts. This explains the approximately 205 MB estimate; it is not a measured finished release size. Actual archives must be measured before approval.

Original training.npz numerical payload is 50331648 bytes (48 MiB), plus small uncompressed ZIP/NPY headers. The source writes np.savez, not compressed output. Model checkpoint is approximately 272 KB historically; new exact size/hash must be measured. Fresh freeze, input receipt and validation diagnostics should keep total training outputs within current 64 MiB output limit. Do not publish full validation field arrays in this recipe: 2 seeds x 60 frames x 3 methods would exceed that budget. Training evidence includes actual consumed-array hashes and retained inputs, not invented historical NPZ byte equality (ZIP metadata can differ).

Existing bounds: scientific bundle 40 MiB; combined selected scientific assets 40 MiB; cold canonical release archive bound 64 MiB; each recipe input 40 MiB; current aggregate capture 64 MiB; source file 8 MiB; captured files 128. Preserve scientific and per-input bounds. Freeze six releases, each containing two complete eight-frame seed records (~34 MB), and bind all six inputs. Twelve single-seed releases are a fallback if actual metadata makes a pair exceed 40 MiB. No splitting a trajectory into records to evade family checks.

CPU profile only: proposed aggregate input bound 256 MiB and total captured source+input+generated policy/bootstrap bound 320 MiB. Keep legacy system profile at 64 MiB and outputs at 64 MiB. Enforce in prepare, retained validate_material, and recipe_process.validate_spec (which separately hardcodes the 64 MiB captured closure). Profile must be validated before selecting its bound; arbitrary descriptor presence must not enable larger legacy limits. Runtime snapshot bytes remain separately bounded/measured, not counted as input capture. Memory can exceed disk bytes due to ZIP expansion/stacks/transforms; these byte bounds do not promise 320 MiB RSS. Observe actual peak RSS and leave original scientific memory gates unchanged.

## Generic binding API and compatibility

Retain exact old binding shape {reference_id, expected_sha256}, receipt shape, graph serialization and identities. Treat that existing shape as project_reference; do not inject a default kind into saved old graphs. New union variant is {kind: "frozen_release", release_id: <64hex>, expected_sha256: <64hex>}. Unknown/mixed fields fail. No domain names in generic core.

Suggested narrow Releases.capture_input(release_id, expected_sha256, max_bytes) -> (raw_bytes, receipt), inspect-authorized, under Workbench lock, regular immutable managed file only, exact size/hash checked. Receipt closed fields: kind="frozen_release", catalog_id, release_id, measured_sha256, bytes. release_id is content identity today; enforce equality to measured/expected digest. No filesystem path supplied by caller. No live-record revalidation or revision substitution: the frozen archive is authority. Generic owner captures bytes; optional adapter performs scientific semantics.

Extend recipe_contract.prepare(projects, graph, execution_sha256, profile=None, *, releases=None) compatibly; release binding requires explicit releases owner from Pipeline/Runs. Old project binding and receipt representations, retained graph digests and stored material remain byte-identical. Newly created material naturally records the changed execution-host source hashes; do not claim that a new host yields the old approval digest. Material input receipt union preserves old project receipt exactly; frozen receipt catalog must equal material.catalog_id; captures input/name hash/length must equal receipt and declared max. Preserve exact approval/material digest and same-key reconciliation: editing any binding/config invalidates preflight and approval; post-preflight modified/missing release refuses before GO.

Existing external graph input node becomes a real named-input mapping to the six archives actually read by fit. No unused Data node. Save/reopen/definition differences show frozen IDs and hashes. Typed parameter controls can expose threads and approved bounded runtime configuration; n32/training seeds/8frames/validation60 are fixed acceptance invariants, not tempting unconstrained knobs.

## Scientific consumer and source closure

Reuse scientific_release.validate_bytes(raw, expected_sha256), scientific_fields.parse_bundle and current canonical receipt validators. Do not create a weaker second release reader. After validation, traverse only exact validated record asset paths and complete manifest-listed arrays; np.load(BytesIO(...), allow_pickle=False), preserve dtype/order/shape. Fit consumes only RHS/pressure but verifies all six fields and exact native wire/provenance as evidence.

Static top-level local import closure currently has 17 files, 270607 bytes: access.py, audio_assets.py, audio_classification_export.py, audio_export.py, bulk_import.py, canonical_release.py, caption_import.py, dataset_releases.py, image_classification_export.py, immutable_assets.py, meshes.py, native_text_import.py, scientific_fields.py, scientific_release.py, text_classification_export.py, text_corpus_export.py, workbench.py. Run-origin provenance additionally lazy-imports recipe_process.py. This count is source inspection, not an executed import qualification. Top-level external non-stdlib dependencies include PIL and psycopg, so copying scientific_release.py alone or assuming NumPy/Torch-only closure is wrong.

Preferred bounded change: move strictly server-only PIL/psycopg imports to their use sites in existing owners, provided cold reader has no executed dependency on those functions, then capture the exact local source closure (including recipe_process). Independent fresh isolated reader import/positive run-source validation must prove closure. If some dependency is actually needed, stop and revise admission/runtime snapshot rather than install silently or duplicate algorithms. No broad parser refactor just to shorten source count. Preserve old release bytes and existing import behavior tests. Capture unchanged original model/experiment/numerical helper sources, optional training wrapper, native transport/policy, exact binary/build receipt, cold reader closure and CPU runtime descriptor. No live checkout imports; path layout must match originals. All adapter provenance must describe measured captured identities rather than call historical provenance() with nonexistent live Git state.

## Acceptance and leakage checks

Before fit, require available human-reviewed field_sequence releases, all selected rows train, exactly seeds 100..111 and eight consecutive frames each, n32 consistent axis/centering/dtype/geometry/time, exact producer report stages (pressure/RHS projection and post-step velocities/tracer), complete all-six-field+wire inventory and accepted finite native diagnostics. Revalidate wire-to-NPY equality using existing optional decoder. Seed names alone are insufficient: bind request/build/policy/source receipts and family identity. Generate fresh training data through existing approved native Runs, import actual artifacts into Data, review and freeze; QA executes review transitions through a named authenticated owner using production Access/Workbench interfaces and explicit QA-authored inspection notes. This proves the owner review flow, not independent end-user scientific acceptance. No direct database review writes, actor bypass or fabricated human acceptance.

Across all six releases reject repeated record IDs, repeated asset/source digests, duplicate first-observed state and conflicting protected families/splits. Run connected-components checks on the combined frozen snapshots/groups, not just each archive separately. Require distinct expected trajectory families for the twelve seeds. Selected-family evidence remains declared/selected scope, not proof about omitted ancestors. Reject validation/test rows from fitting. Validation 500/501 uses original comparison without weight updates; tests 900..903 are previously exposed and must remain labelled so. Fit/validation do not establish fresh holdout quality.

Require fit finite positive gains/excitation, unchanged full-field validation gates and ablation outcome. Do not reuse P5a pinned historical-checkpoint validator to validate a new checkpoint: define a new optional result schema binding exact new model.pt, training.npz, all six release hashes, ordered record/frame/array hashes, fit metrics, native/runtime identities, validation and ablation. Check checkpoint schema and full state_dict shapes/finite values via weights_only load in qualified runtime. Independent replay of frozen input arrays establishes actual use; tampered RHS must fail receipt or alter consumed-array hash/result, never pass as unused input.

## Write ownership proposal and runnable checkpoints

1. Root: recipe_contract.py, pipeline.py, runs.py, dataset_releases.py, app.py and relevant generic contracts/tests. Generic union, owner capture, exact digest/approval semantics, bounded retained validation. Existing project-only graph golden identities first.
2. Runtime owner: recipe_process.py and focused process tests for CPU-only 320 MiB capture and legacy64 MiB refusal. No global output-limit increase.
3. Cold-reader owner: scientific_release.py only if a small combined-input API is genuinely needed; otherwise existing public API unchanged. Coordinate narrowly approved lazy-import edits in workbench/caption_import/native_text_import/bulk_import/dataset_releases as required by dependency inventory. Focused independent cold/old-release/restore tests.
4. Optional-adapter owner: new adapters/rheon/cpu_train.py and cpu_training_project.py plus contract/tests; unchanged upstream scripts copied and pinned. Consume all declared archive inputs, unchanged fit and validation, real result gates.
5. UI owner: static/workspace-external.js and minimal static/workspace-real.js integration; input-kind selector and frozen-release picker per named slot, typed configuration, approval digest, saved input hashes, live bounded log/status/cancel, verified result downloads. Reuse existing graph and Runs lifecycle. No explanatory wall or hardcoded Rheon behavior in generic UI.
6. Independent evidence owner: actual generation/import/review/freeze, real HTTP/browser edited binding/config -> preflight -> approval -> run -> monitor/result -> reopen and relocated restore. Use explicit authenticated QA owner review/approval through production operations; already authorized QA work does not require another user confirmation. Do not claim actual acceptance from neutral fixtures.

Tests: retained old project binding/material byte equality; new release capture hash mismatch/missing/oversize/cross-catalog; aggregate CPU bounds and legacy rejection; changed config/binding stale approvals; release family leakage across archives; draft/nonhuman/test/duplicate/missing frame/changed dtype/stage/wire refusals; cold source closure without live repo/PIL/psycopg; direct fit input array equality to original oracle; actual fit/validation/ablation and checkpoint reopen; cancellation/cleanup/retry with new exact approval; backup restore and result/download byte identity. Runtime/model qualification follows successful P5a gate, never mocked acceptance.

Open before implementation: actual archive byte inventory; cold-import dependency isolation; exact intended CPU fit/validation resource window (current P5a600 seconds may not be suitable); recorded QA owner review of the twelve generated records through production interfaces, clearly distinguished from real end-user scientific acceptance. This proposal changes only this report; runtime source remains frozen during the active P5a browser/model qualification.

## Proposed exact verification/documentation write set

Alongside the runtime/UI owners above, update existing `tests/test_external_runs.py`, `tests/test_external_http.py`, `tests/test_recipe_process.py` and `tests/browser_workspace_external.cjs` only for affected generic contracts. New optional acceptance tests belong in `tests/test_rheon_cpu_training.py` and `tests/browser_workspace_cpu_training.cjs`; fixture-only positives are explicitly synthetic. Cold closure changes use `tests/test_scientific_release.py` and existing retained-reader coverage. Extend the existing `tests/test_workspace_external_controller.cjs` for stale binding/picker/session responses. Reuse existing browser helpers in the new real-training workflow. Durable input semantics belong in the existing `docs/contracts/external-recipes.md`; CPU limits in `docs/contracts/captured-cpu-runtime.md`; optional numerical scope in new `docs/contracts/rheon-cpu-training.md`. Update the parent `plan.md`, `execution-ledger.md` and `issues.md` only as evidence changes. This planning task writes only this report.

## Compact in-app progress and metrics (proposed)

### Existing authority and gap

`recipe_process._helper` already owns stdout/stderr capture in `custody/stdout.log` and `custody/stderr.log`, with a 1 MiB limit per stream, truncation causing `stream_limit` cancellation, and exact retained stream byte counts/SHA256 in its custody receipt. Runs owns launch, cancellation, drain and publication. `Runs._public` currently exposes lifecycle events/progress/custody phase but no external stream text or scientific metrics; `WorkspaceExternal.runHTML` shows custody only. `static/workspace-real.js:loadRuns` already refreshes the selected active Run every 1800 ms and stops polling terminal Runs. Reuse that loop; no telemetry daemon, WebSocket service, database event mirror or second scheduler.

The existing internal training `_drain` parser explicitly excludes raw worker text; do not relax it. Add a separate read-only external diagnostic projection in the same Runs owner. Diagnostic text is project-authored and untrusted, never a state transition, permission, scientific verdict or reason to mark a Run completed.

### Proposed bounded read API

Add inspect-authorized `Runs.external_progress(run_id)` and `GET /api/workspace/runs/{id}/progress`. It accepts only a validated Run ID, never a path, stream name, arbitrary artifact name or caller offset. Load and validate the external Run; resolve only the current catalog's `_external_directory(run)/custody`, not retained historical absolute `spec.cwd`. Open owned directory components without symlink traversal and fixed stdout/stderr regular files with no-follow/nonblocking semantics. Reject changed inode/path ownership, FIFOs, symlinks and sizes over the existing 1 MiB stream limit. Missing logs before launch yield an explicit pending status; missing retained diagnostics yield unavailable, not an empty successful log.

Read at most the last 8 KiB of each stream per response. Return closed fields `schema_version`, `run_id`, `state`, `custody_phase`, `evidence`, `streams`, `progress`, `result`; stream entries contain `available_bytes`, `start_byte`, `text`, `truncated`. UTF-8 replacement decoding is display-only; hashes always cover raw bytes. Drop a partial leading line before structured-event parsing, replace display controls except newline/tab, and render text only (escape HTML; never hyperlink or execute output). Bound parsed lines to 4096 bytes and the response to 192 KiB after the same JSON encoding used by HTTP, including escaping. Enforce the encoded limit explicitly; summary fields are semantically bounded below, and diagnostic tails may be reduced with truthful truncation metadata if needed. A growing active file is a valid bounded observation, so do not use `_read_regular`'s unchanged-size requirement unchanged for live tails; use bounded descriptor reads and report observed bytes rather than pretending an atomic entire-stream snapshot.

`evidence` is one of `pending`, `live_unverified`, `custody_verified`, `unavailable`. Active/unknown Runs always use `live_unverified`, with label “Live process output — unverified.” For drained terminal diagnostics, verify the entire stream (still at most 1 MiB) against the exact identity-validated custody receipt's size/hash before saying “Custody-verified process output.” Failed/cancelled output can have verified custody but is never a successful result. Completed Runs additionally bind the published custody receipt hash through the existing Runs record. Source files missing after restore remain visibly unavailable; never follow the old absolute location. Do not persist diagnostic tails or inferred stages as another mutable truth.

### Actual stages and numeric progress

The optional training adapter flushes small JSON lines on existing stdout with closed protocol `{format:"tuldok_progress_v1", stage, completed, total, metrics}`. Stages are bounded identifier strings supplied by the reviewed recipe; generic core knows no Rheon names. Integers satisfy `0 <= completed <= total <= 1000000`; metrics are at most eight bounded named finite numeric values. Recognize only complete valid lines; malformed/unrelated text remains diagnostic text and cannot abort or alter the Run. Keep the latest valid event from the bounded tail; if none is present show “No structured progress available,” never infer progress from wall time. This is a projection of the existing stream, not an independently durable event channel.

For this adapter emit actual `loading` counts for 12 verified trajectories/96 frames, `fit` start 0/1 and finish 1/1 around the real unchanged `ModalPressure.fit` call, `validation` counts 0..2 for seeds 500/501 after each completed 60-frame comparison, then `publishing` before the wrapper writes its final results. Each scientific metric is a number actually returned/recomputed, such as fit relative pressure error, fit wall seconds, validation relative velocity/tracer error and divergence maximum; use the original script's actual field names where possible. The fit is closed-form with **zero optimizer steps**: no epochs, fabricated loss curve, per-step updates, fabricated ETA or apparent continuously increasing fit percentage. Native comparison frame-level progress is shown only if the unchanged execution actually provides it; otherwise retain the completed-seed count.

Progress never supersedes Runs state. A live “publishing” line is not successful publication; only Runs' existing drained/verified terminal transition enables completed artifacts. A restart, cancellation, stale response or stream limit preserves this distinction.

### Hash-verified completed result panel

Add one generic optional output role `result_summary`, explicitly declared in the approved recipe's existing output inventory. Its exact declared artifact name, role, byte cap (64 KiB), and captured recipe identity authorize rendering; neither a filename suffix nor an stdout line can nominate another file. The proposed closed JSON schema `tuldok_result_summary_v1` contains a bounded title, up to 24 finite numeric metrics `{name,value,unit}`, at most eight bounded scope labels, and optional checkpoint artifact name. Strings are bounded plain text: title 120 code points, metric name 64, unit 24, scope label 160. Summary input remains capped at 64 KiB; the encoded whole-response cap applies independently. No HTML, scripts, paths, URLs, arbitrary tables or nested executable content.

Expose the summary through an inspect-authorized Runs projection using existing `_verified_artifacts`/`artifact` authority, only for `state == completed` and exactly one declared `result_summary` output. Return this in the same `/progress` response; do not add another summary endpoint or reader. The closed response includes `result`, null until verified, then `{status:"hash_verified", artifact_name, sha256, summary}`. The referenced checkpoint must be another verified artifact in the same completed inventory with the recipe-declared `checkpoint` role. Downloads continue through the existing `/artifacts/{name}` endpoint. No server checkpoint deserialization.

Generic shape validation proves safe display and custody only. The optional adapter owns numerical qualification and must write the summary from its already validated fit/validation report, including all release hashes and measured checkpoint identity in the full result artifact. Include a visible “Hash-verified artifact; metrics are recipe-reported” caption. This preserves the difference between byte integrity and independent scientific acceptance. Invalid/tampered summary hides metrics and reports unavailable; it does not rewrite the completed Run or invent fallback metrics from its log. Historical recipes without the role retain their existing artifact list and custody view unchanged.

### UI integration and decisive evidence

Keep the Runs panel compact: lifecycle badge; current stage/count; up to four primary numeric values; checkpoint download after verified completion; one collapsed diagnostics section with separate stdout/stderr tails and evidence label. Full provenance and remaining metrics stay in details/downloads. Refresh through the existing selected-Run poll with its generation/view guards; session change, Run selection and navigation invalidate pending responses. Stop automatic polling on terminal state, retain explicit Refresh, and preserve diagnostic disclosure/focus while refreshing. Scope labels include authored QA evidence, CPU runtime and previously exposed evaluation seeds where applicable. No universal quality/accuracy badge.

Write owners: Runs/app owner adds the bounded projection and optional result-role validation; optional adapter owner emits actual stdout events and approved result summary; UI owner changes `static/workspace-external.js` and the existing `loadRuns` composition in `static/workspace-real.js`. Reuse custody logs and receipt code in `recipe_process.py`; no extra stream writer is needed. Tests cover active growth, truncated/partial/non-UTF8 text, malicious control/HTML text, missing/oversize/symlink files, receipt hash mismatch, cross-catalog access, malformed event counts/nonfinite metrics, stale/session-switched UI responses, failed/cancelled diagnostics, role-confused summaries and checkpoint references, terminal restored verification, plus actual observed loading → closed-form fit → validation → verified checkpoint in the real browser. Synthetic stage fixtures prove parsing only, never actual fitting.

Run-artifact input binding is deferred to P5c: P5b's only new input variant remains `frozen_release`. P5b produces and retains the real checkpoint and its evidence; P5c may add a separately specified generic completed-Run artifact binding for convenient follow-on evaluation. This sequencing does not remove the parent G4 autonomous-evaluation acceptance requirement or permit unused graph inputs.


## Independent admission corrections and assigned owners

Independent review identified two omissions, now admitted explicitly. The optional
producer currently supports only two frames. Extend `adapters/rheon/generate.py`
and `adapters/rheon/project.py` to at most eight whole frames, wire at most12 MiB,
fields.zip at most20 MiB and declared aggregate output40 MiB; keep the120-second
wall bound, grid32 ceiling and unchanged native source/solver. Preserve the old
one/two-frame behavior and frozen historical bytes. Update affected producer
unit/browser refusal checks (the invalid upper frame becomes9), and qualify an
actual eight-frame/all-six-array wire capture before generating training data.
No scratch-only bypass of the declared producer is allowed. The progress response
now has coherent8 KiB tails and192 KiB encoded response bounds as specified above.

All implementation below occurs in `/workspace/Tuldok-p5b`; the P5a checkout stays
source-stable for regression. Root owns recipe_contract.py, pipeline.py,
dataset_releases.py, corresponding frozen-input tests, contracts and plan.
`milestone_audit` owns recipe_process.py capture bounds and its tests, plus narrow
server-only lazy-import edits needed by the cold reader (coordinate the
dataset_releases.py import edit with root, never edit that file concurrently).
`volume_assets` owns runs.py/app.py progress and result projection, HTTP tests,
and registration of the generic release-candidate route against root's owner API.
`mesh_ui` owns workspace-external/workspace-real JavaScript and controller tests.
`recipe_design` owns the optional training adapter/assembler and their tests.
`point_assets` owns the eight-frame producer extension and generation/browser
qualification harness. `mesh_review` performs independent integration review
after completing P5a regression. No new scheduler, database schema, parser or
scientific algorithm is introduced.

Additional reviewed integration writes: `tests/test_frozen_recipe_inputs.py` owns
frozen-byte authority, binding staleness, old material equality and CPU/legacy
bound tests. `.github/workflows/tests.yml` runs the new training adapter module
under the already provisioned training interpreter, so its three NumPy-dependent
contract tests are covered despite explicit skips in the base interpreter. No
new dependency installation is added. `native_transport.py` admits an explicit
validation seed tuple (default P5a scope unchanged) and optional bounded private
regular-file stderr evidence for the unit-gain rejection test; unrelated native
failures cannot be labeled physics rejection. Source review required closed native
policy/mapping evidence, finite training residuals, validation identity/maxima and
measured original memory-limit enforcement; all were implemented before execution.


## Real preparation admission

P5a commit05ea66e passed full807-test local regression with unchanged190-source
inventory, plus20 independent native-reader checks, and exact-head hosted
UI38456049102/lifecycle38456049347. The dependency gate is satisfied. Independent
P5b generic/UI and optional numerical reviews found no remaining blocker after
the recorded fixes;26 generic tests and12 training adapter checks pass.

Admit actual eight-frame producer qualification, then preparation-only production
Runs for seeds100..111, QA owner Data review and six pair releases. Verify each
wire/array set and measure actual archive sizes. Server/runtime/adapter source
remains frozen during Runs. The fresh fit follows a preparation evidence review
against the admitted256 MiB aggregate input and40 MiB individual limits. This is
an internal execution checkpoint within the user's existing authorization.

## Fresh fitting admission

Preparation completed with twelve native trajectories (seeds 100–111, eight
frames each), 576 independently checked field arrays and six QA-owner-reviewed
train-only pair releases. Root independently verified each downloaded archive
against its release SHA-256 and byte count. Sizes are 34,145,326; 34,145,202;
34,145,306; 34,145,280; 34,145,150; and 34,145,328 bytes, totaling 204,871,592
bytes. Every input fits the 40 MiB bound and the total fits 256 MiB.

The preparation inventory is `build/qa/workspace-cpu-training/run-OgbEYN/prepared-inputs.json`.
Actual producer qualification passed ten tests, including the extended native
eight-frame path. All 27 captured training sources and the current cold-reader
closure were rechecked before starting the browser resume. Fresh fitting through
the saved graph is admitted. This admits execution, not successful model
qualification; progress, checkpoint, independent numerical checks and restart
evidence remain required. No production deployment or merge is authorized.

## First actual fitting attempt: retained failure

Run `ece8abe0a4024d1483048d91b7980cf0` reached terminal `failed` / `drained`
after approximately 65 seconds, before browser shutdown. The actual fit and both
validation trajectories passed, but the adapter refused ablation qualification.
The pinned native program emits `trajectory probe: stored divergence … exceeds …`;
the authored classifier incorrectly expected `Error: `. The observed untrained
divergence was 0.20241660624742508 against 0.00001. This failure is preserved and
is not successful training acceptance.

Admit a narrow correction to the exact pinned diagnostic prefix and regression
coverage using the retained line. Retain exit-code, seed/method, exact diagnostic
bytes/hash, finite-value and threshold checks; unrelated failures remain rejected.
No numerical algorithm, training inputs or acceptance threshold changes. A new
captured project and fresh exact approval are required for the next attempt.
