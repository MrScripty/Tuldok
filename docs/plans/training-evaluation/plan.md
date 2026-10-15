# Visual training evaluation: investigation and proposed delivery

Status: historical evaluation proposal, 2026-10-14. End-to-end architecture design
sequencing is now owned by [the model-development design plan](../end-to-end-model-development/plan.md).
This document remains supporting research and does not authorize a parallel
implementation. Application source inspected at
`6695668e`. No application changes or new training runs are part of this report.
The requested paper is [Evaluating and Visually Understanding Model Training
Runs](https://github.com/MrScripty/Tuldok/blob/281d77c8f5009a80599bef69db83ed340529235f/docs/research/training-evaluation/evaluating-and-visually-understanding-training-runs.md),
added in commit `281d77c8` and present on `origin/main` (`133f420` when inspected).
Local `main` does not yet contain it; the review reads its committed bytes without
switching or merging branches. See the [paper review](reports/paper-review.md),
[methodology checks](reports/paper-methodology-review.md), and
[supporting research](reports/primary-sources.md).

The paper changes the priority of this proposal: **fixed validation probes across
checkpoints are a core capability**, alongside scalar diagnostics. A completed-run
dashboard is an immediately useful first slice, but cannot show what an earlier
checkpoint predicted when those outputs were never retained.

## What Tuldok already supports

| Existing capability | Source | Implication |
| --- | --- | --- |
| CPU image training records training loss, validation metrics per epoch, selected checkpoint epoch and runtime. Image training currently permits 1–5 epochs. | [Image contract](../../contracts/workspace-image-training.md), [worker](../../../image_training.py) | Completed-run learning curves can use existing artifacts. The retained training loss is measured during updates; label it separately from evaluation of a fixed checkpoint. |
| Text TF-IDF/Naive Bayes and audio logistic classification publish the same classification evidence envelope, including probabilities. | [Text contract](../../contracts/workspace-text-training.md), [audio contract](../../contracts/workspace-audio-training.md) | Shared prediction diagnostics are possible. Their single fit-pass history does not describe an iterative neural training curve. |
| Runs already shows accuracy, example count, macro F1, clickable confusion counts and frozen prediction references, with a link to the current editable Data record. | [Current Runs UI](../../../static/workspace-real.js) | Extend this working interaction. A confusion matrix itself is not a new feature. The current prediction cards do not display the retained probability vectors or frozen media previews. |
| Artifact publication checks hashes, source references, class mappings, finite values and prediction/confusion consistency. Test files have durable exposure gates. | [Runs contract](../../contracts/workspace-runs.md), [Runs implementation](../../../runs.py) | New classification views should consume the existing verified read paths and default to validation. |
| Generic projects can train and independently restore/evaluate using exact checkpoint, dataset and persisted split inputs. Compact results contain recipe-reported metrics; progress exposes bounded observations. | [Project CLI](../../contracts/project-cli.md), [external recipes](../../contracts/external-recipes.md) | Generic neural projects need declared evaluation artifacts for full charts. Polling the latest progress event cannot reconstruct training history. |
| Rheon CPU evaluation retains reference/learned fields, numerical errors and repeated timing evidence. Data can inspect an exact orthogonal scientific field slice. | [Rheon evaluation](../../contracts/rheon-evaluation.md), [field contract](../../contracts/scientific-fields.md), [slice UI](../../../static/scientific-fields.js) | Build comparison on retained evidence. The current viewer is a single-record inspector with per-slice automatic grayscale ranges. |

## Recommended first delivery

Extend **Runs** with a validation evaluation view for the existing image, text
and audio classifiers. Keep the existing Runs owner, immutable artifacts and
Data correction flow. This first delivery needs no new trainer, model download,
execution engine or wider training limits.

1. **Training history.** Plot image training loss and validation loss on a loss
   chart, and validation accuracy/macro F1 on a separate chart. Mark the selected
   epoch, show exact values in an accessible table, and show a single point for
   one-epoch runs. Text/audio show their one-fit result explicitly. Final
   probability diagnostics refer to the selected checkpoint, not necessarily
   the last epoch. Existing live epoch events omit training loss, so the complete
   paired loss chart is initially a completed-run feature.
2. **Class and error diagnostics.** Add raw-count and row-normalized confusion
   views, per-class precision/recall/F1 and support, probability bars, and filters
   for errors and confidently wrong examples. Preserve click-through to exact
   prediction references. Empty denominators display as unavailable with support
   counts; do not silently report a perfect or zero percentage.
3. **Confidence diagnostics.** Add confidence histograms, reliability bins with
   counts, and a clearly defined multiclass Brier score computed from the retained
   probabilities. Show bin definitions and label sparse results as descriptive.
   Calibration visualization does not calibrate a model. Retain the worker's
   reported loss and its definition; do not silently replace logits-based loss
   with a differently clipped probability-based calculation.
4. **Run comparison.** Select two completed validation runs; overlay compatible
   histories and show metric deltas plus examples fixed/regressed/both wrong.
   Paired examples require identical frozen inputs, target revisions, split
   membership and class semantics. Same release hash is a simple initial
   classification admission rule. Different releases remain inspectable as
   different datasets, without a paired improvement claim. Name a baseline run
   explicitly; a new majority-class baseline chooses its class from training
   labels only and records that rule.

Proposed implementation: a small pure diagnostic calculator and a focused Runs
renderer, called by `workspace-real.js`. The calculator accepts verified metrics,
class vocabulary and prediction rows, and returns chart/table data. Keep model
loading, artifact custody, authorization and training out of that interface.
Compute bounded descriptive statistics on demand; do not add derived columns to
the authoritative run document or rewrite old artifact schemas. Scope all async
reads and cached render data to the current catalog, actor, run and split using
the existing stale-response guards.

## Core next delivery: fixed probes across checkpoints

Sections 3, 5, 7 and 9 of the paper supply the main product interaction. Create a
frozen validation probe collection before fitting, record actual predictions at
a declared cadence, then let a user select a case and compare checkpoints with
identical inference and display settings. Start with existing image classification
and one declared scientific project; reuse the same identity/selection concepts
with task-specific renderers.

The screen should have a checkpoint selector, a fixed example selector, scalar
history with the current checkpoint marked, and coordinated input/target/output/
error panes. For classification, outputs are probability vectors and the frozen
target. For fields, outputs are registered numeric arrays with aligned signed
and absolute differences. Uncertainty appears only if a declared artifact
provides it. A scientific time control is separate from optimizer progress.

Required additions:

- A versioned probe specification containing exact source/revision/content and
  family/split identities, a reproducible sampling rule, explicit ordinary/slice/
  regression-case roles, inference recipe and display protocol. A failure-selected
  regression set does not estimate general failure prevalence.
- A bounded evaluation history/index containing run and checkpoint hash, actual
  optimizer updates and exposure counts when known, evaluation wall time and
  pre/post-update semantics, probe identity, prediction artifacts, metric
  definitions, and transformation/reconstruction identity. Physical time belongs
  to each trajectory observation, not the optimizer clock.
- Training-side periodic evaluation in the declared model mode. Preserve fitted
  state and resume intended training behavior afterward. Probe predictions and
  their producing checkpoint must correspond; an evaluation checkpoint need not
  contain optimizer state or promise resumable training.
- Explicit storage/cadence/output limits. Current classification adapters publish
  a closed six-file inventory and only selected-checkpoint predictions; add an
  opt-in versioned adapter/artifact contract rather than altering historical v1
  artifacts. Generic recipes already permit bounded declared outputs, but need a
  documented evaluation descriptor and checked reader. Prefer indexed/bundled
  observations within those output limits over an unbounded file per update.
- Distinguish retained checkpoint outputs from replay. A replay is a new,
  explicitly admitted evaluation Run binding checkpoint, probe inputs and
  evaluation recipe, with a fresh receipt. Missing historical predictions are
  unavailable until such a replay; the UI never reconstructs them from curves.

Acceptance must show two actual checkpoints evaluated on identical probes,
retained bytes surviving restart, an independently reproduced prediction, and a
comparison that preserves physical values under a shared scale. A tenfold
amplitude error must remain visible. Changing the model, probe, transform or
frame must invalidate stale comparisons. No test probe is displayed through this
validation workflow.

## Follow-on capabilities

| Priority | Capability | Evidence or contract needed |
| --- | --- | --- |
| Next | Error gallery with frozen image/text/audio evidence | Read exact release assets through verified accessors. Current Data is a separate editable destination; current assets/annotations cannot substitute for frozen evidence. Audio playback binds the original rate, channel and interval. |
| Next | Saved error slices and threshold exploration | Pin slice rules and membership to frozen metadata. Show support and independent-family counts. Threshold selection uses validation and saves a separate decision-policy artifact; exploratory thresholds never rewrite original argmax metrics. |
| Next | Repeated-seed comparison and evaluation-only runs | Record model/recipe/runtime, fixed splits, preprocessing, seeds and evaluation protocol. Separate initialization variability from data-sampling uncertainty. Text/audio determinism is not evidence from independent repeated trials. Model selection remains validation-only. |
| Next | Scientific reference/prediction/difference view | Bind compatible field pairs to exact artifacts; synchronize frame/time, axis and slice. Check geometry, centering, units and computational stage. Share the reference/prediction color scale and use an explicitly labelled error scale. Do not silently interpolate or resample mismatches. |
| Next | Scientific error-over-time and resource comparison | Retain per-trajectory errors and domain checks, baseline identity, hardware/thread/runtime, timing repetitions and memory measurement scope. Aggregate at trajectory level; adjacent cells/frames are not independent test examples. Preserve already-exposed-seed labels. |
| Alongside probe capture | Neural optimization diagnostics | Version a bounded history artifact with actual step/epoch, train/validation loss definitions, learning rate, gradient norm, optimizer-step count and optional weight-update norms. Include unweighted objective components and weights, clipping/skipped-update semantics when supported. Trainer emits real observations; core never infers them from wall time. Missing telemetry remains unavailable. |
| Later | Human evaluation and acceptance scorecards | Preserve rubric version, blind/randomized paired presentation where appropriate, case selection, ties/cannot-judge, reasons and disagreement. Keep mandatory domain constraints distinct from tradeoff scores. Ratings select or evaluate candidates; a separate declared training method is needed to consume feedback. |
| Later | Detection/segmentation/retrieval/generative evaluation | Separate task schemas: box/mask overlays and task metrics, ranked relevance judgments, or fixed prompt/seed sample panels with human rubrics. Existing Data/export support alone does not qualify these training or evaluation tasks. |

For generic project results, introduce an explicit, bounded, versioned evaluation
descriptor that references declared hash-verified outputs and specifies task,
split/protocol identity, metric meaning/direction/units and evidence links.
Existing summaries remain readable. Custody verification and numerical
verification must remain visibly distinct. Generic summaries currently do not
provide the classification test-exposure enforcement; a generic holdout feature
needs its own declared identities and serving gates before claiming parity.

## Evaluation discipline

- Default every view and comparison to validation. A test-derived chart,
  thumbnail, filter count, export or cached result must pass the existing durable
  exposure gate before serving any underlying evidence. Session/catalog changes
  clear display state. Correcting Data creates a new release/run and leaves old
  evaluation evidence unchanged.
- Count protected source families as well as rows. Exact-hash and family checks
  do not prove semantic independence. New confidence intervals or resampling must
  state their estimand and sampling unit; correlated intervals, frames and cells
  cannot masquerade as independent observations.
- Show empty or tiny slices explicitly. Exploratory slice search and validation
  tuning can overfit evaluation material. A final claim needs a separately
  specified protocol and appropriate held-out evidence.
- Avoid ranking different task losses, datasets, preprocessing, or runtimes as a
  single score. Keep quality, throughput and resource measurements separate.
- Keep raw observations, calculation definitions and frozen identity available
  in exported evaluation reports. A visually plausible chart is not independent
  proof of model quality.

## Acceptance for the first delivery

- Existing completed image/text/audio artifacts remain readable unchanged.
  Independently calculated small examples verify class support, normalization,
  per-class metrics, confidence bins, Brier convention and paired deltas.
- Real browser evidence covers an image history with multiple actual epochs,
  one-fit text/audio presentation, matrix-to-row navigation and correction, and
  comparison of compatible runs. Any newly executed runs retain their actual
  artifacts; authored fixtures remain labelled fixtures.
- Test access fails before exposure, including every derived route/export/cache;
  later exposure remains visible on reused material. Tampered or missing artifacts
  cannot continue displaying apparently valid cached diagnostics.
- Narrow/desktop layouts, keyboard selection, text labels and numeric tables
  preserve access without color or hover. Switching actor/catalog/run while a
  request is pending cannot paint stale evidence.

## Delivery order and decision record

1. Expose existing verified history and classification prediction evidence with
   descriptive charts; establish safe same-release comparisons.
2. Add the versioned fixed-probe capture/index and checkpoint comparison. Bring
   aligned scientific difference views into this milestone for an opted-in
   project, using retained final fields first where intermediate captures are
   absent.
3. Add project-owned physical/rollout/route evaluation, acceptance scorecards,
   error slices and meaningful uncertainty; compare raw, corrected and fallback
   results at equal final quality and complete-system cost.
4. Expand to other tasks and repeated training only after their artifact meanings
   and evaluation protocols are explicit.

These are engineering priorities inferred from the tutorial, not a claim that
the chapter experimentally validated a Tuldok interface. Its illustrations are
authored; its cited managed CNN report supplies negative numerical evidence, not
fresh holdout success. A later implementation should retain that distinction in
the product as clearly as the chapter does.
