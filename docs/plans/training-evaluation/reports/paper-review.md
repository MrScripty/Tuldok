# Review: Evaluating and Visually Understanding Model Training Runs

Reviewed 2026-10-14 against paper commit
`281d77c8f5009a80599bef69db83ed340529235f`, available on `origin/main`. Local
application checkout: `6695668e`. The initial filename/content search missed the
paper because local `main` had not advanced to the remote-tracking branch. This
review reads committed source without merging unrelated changes.

Sources: [chapter](https://github.com/MrScripty/Tuldok/blob/281d77c8f5009a80599bef69db83ed340529235f/docs/research/training-evaluation/evaluating-and-visually-understanding-training-runs.md),
[source-to-claim bibliography](https://github.com/MrScripty/Tuldok/blob/281d77c8f5009a80599bef69db83ed340529235f/docs/research/training-evaluation/bibliography.md),
[illustration data](https://github.com/MrScripty/Tuldok/blob/281d77c8f5009a80599bef69db83ed340529235f/docs/research/training-evaluation/illustrations-data.json).
The full 832-line chapter was read, including its fluid case and decision guide.
This is a research synthesis/tutorial with 43 research citations and one pinned
project report, not a new empirical evaluation of a training or UI method. Its
literature date is 15 October; its commit timestamp is 14 October in Pacific time.

## Assessment

The chapter is a strong basis for Tuldok's evaluation design. Its central
contribution to this project is a connected workflow: verify example meaning,
observe real parameter learning, compare fixed validation cases across
checkpoints, evaluate independent families and domain outcomes, then assess
complete-system cost. It consistently qualifies which evidence supports each
claim. Adopt that workflow as product requirements, while treating tool choices
and implementation priorities as engineering decisions requiring their own
verification. The chapter does not establish which dashboard interactions help
users most, universal numerical thresholds, or improved model performance.

## Most useful findings for Tuldok

| Chapter | Product implication | Current gap |
| --- | --- | --- |
| §§1.2, 5.3 | Distinguish optimizer updates, data exposure, physical time and wall time. Compare checkpoints at the same physical state/time. | Built-in classification has epoch history; generic progress has a stage counter but no universal clock semantics. A latest progress event is insufficient history. |
| §§3, 5 | Show exact transformed inputs/targets and fixed probe predictions, with provenance, model mode and reconstruction identity. | Current result cards link frozen references to current Data. They do not supply transformed-input inspection or per-example checkpoint histories. |
| §§7–8 | Separate online fitting loss from fixed-set evaluation; show component loss, learning rate, gradients and actual parameter updates when recorded. | Image history exists, but only selected-checkpoint predictions are retained. Text/audio have a single fit event. Generic training metrics need explicit schemas. |
| §9 | Lock compared scales, units, coordinates, plane/camera and physical time; expose values, signed/absolute error and clipping. | Scientific inspection currently autoscales a single slice. Independent autoscaling can conceal amplitude failure. |
| §§10–12 | Distinguish raw surrogate output, corrected output, fallback, native residual, gauge, boundary behavior and free rollout. | Retained Rheon evidence can support views, but generic physical acceptance is project-owned. One model's success cannot transfer to another. |
| §§4, 13, 15 | Preserve families, exposure, paired outcomes, slice support and uncertainty assumptions. | Classification already has useful exposure gates; generic project summaries do not automatically enforce the same holdout semantics. |
| §§14–15 | Use separate acceptance constraints and score components; include correction/fallback and startup in costs. Human ratings are evaluation until a learning method consumes them. | Generic summary cards contain reported scalars; they are not a typed acceptance policy or human-evaluation protocol. |

## The chapter's local numerical example matters

Section 10.2 accurately summarizes the repository's [managed CNN
report](../../generic-neural-execution/reports/managed-cnn.md): eight fitting cases,
200 Adam updates, normalized training MSE approximately 1.600599 → 0.0584414,
fresh restoration, and **zero of 16 cases qualified** under the native
pressure/divergence criterion. The test family had previously been exposed.
The report's values and limitations agree with the chapter; the experiment was
not rerun for this review.

This should guide the first scientific evaluation screen. It must be possible to
display a successful/drained execution and falling training loss beside an
explicitly failed numerical scorecard. Reproduced weights and artifact hashes
answer custody/reproducibility questions. They do not turn a failed raw pressure
prediction into an accepted physical solution. Neither the chapter nor the
report proves why the CNN failed; a receptive-field change remains a hypothesis
requiring a controlled experiment.

## What needs specifying before implementation

1. **Artifact contracts and retention.** The tutorial lists evidence to preserve,
   but not Tuldok's exact schema, bounds, index layout or migration policy. The
   built-in classifier's strict inventory cannot accept arbitrary extra probe
   files. Generic project outputs need a versioned reader/descriptor. Preserve
   old results; introduce new capture capabilities explicitly.
2. **Capture versus replay.** Current curves cannot recover old checkpoint
   predictions. Decide capture cadence and space budget before training. A
   replay requires a retained checkpoint, exact inputs and recipe, and its own
   admitted Run; unavailable history must remain visibly unavailable.
3. **Metric definitions and independent checks.** Specify denominators, units,
   aggregation, valid masks, zero-reference behavior and undefined cases. Use
   project-owned native operators for pressure, with checked compatibility.
   Generic core can verify declared inputs and bytes without claiming it has
   independently verified a physical equation.
4. **Selection and exposure policy.** Persist why probes were chosen, what
   evidence influenced interventions, and which criterion selected a candidate.
   A discovered failure is a regression case; its frequency is not a population
   estimate. Generalize holdout serving gates before offering generic test views.
5. **UI evidence.** The chapter supplies principles and teaching diagrams, not
   measured usability results. Verify that actual users can find a deliberately
   wrong scale, inspect a regressed example, and distinguish raw from corrected
   quality. Keep exact numeric tables and keyboard access alongside plots.
6. **Optional diagnostics.** Uncertainty, residuals, gradient norms, activations
   and per-layer updates must come from declared measurements. A deterministic
   field or class probability vector does not provide every uncertainty event
   described in the chapter. Do not fabricate unavailable telemetry.

## Recommended product sequence

Begin with existing-artifact learning curves and richer classification error
inspection. Then deliver the core **fixed probe × checkpoint** comparison, with
shared-scale reference/prediction/difference views for one opted-in scientific
project. Add project-owned residual/boundary/rollout and raw/corrected/fallback
scorecards before presenting scientific acceptance or speedup. Expand calibration,
repeated seeds and blind human review as separate capabilities with explicit
evidence contracts.

The [updated plan](../plan.md) includes the concrete data requirements and
acceptance boundaries. The [methodology review](paper-methodology-review.md)
records checks of high-impact external claims; the [supporting research
note](primary-sources.md) supplies additional primary sources. No application
code, branch state, data, training run or original paper bytes were changed.

## Review verification

Recomputed the committed illustration's tenfold amplitude relationship, both
checkpoint-selection examples (updates 2000 and 4000 under their respective
criteria), alternating-pressure residual RMS of 40 under the displayed stencil,
fallback timing examples of 4 ms and 11 ms, and the managed report's loss ratio
of approximately 0.0365122. Each agrees with the chapter. The local managed CNN
report is unchanged from the paper's pinned project revision. These are source
and arithmetic checks; no trained checkpoint, native trajectory or user study
was rerun.
