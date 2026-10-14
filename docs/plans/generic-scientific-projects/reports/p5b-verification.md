# P5b: fresh CPU training from frozen scientific releases

## Qualification

Actual Run `11fc2be1aada490f9b67c11c190728f6` completed with drained custody.
It consumed six verified, QA-owner-reviewed immutable releases containing twelve
whole native trajectories, seeds 100–111, eight frames each. Independent byte
checks cover all 576 field arrays. All 96 ordered float64 RHS/pressure observations
match the published training NPZ exactly. The original pinned modal fitting and
validation algorithms are unchanged; orchestration consumes frozen Data inputs.

The fresh checkpoint contains 32,767 fitted gains, with zero optimizer steps.
Independent NumPy replay agrees to a maximum relative gain difference of
2.002450423477542e-14. The actual fitting call took 0.215544621 seconds; the whole
Run took 64.748344 seconds including capture/runtime loading, validation and
publication. Measured Python peak RSS was 615,874,560 bytes. These timings are
observations on this CPU, not historical speedup or hardware reproduction claims.

Both 60-frame validation trajectories (seeds 500 and 501) passed. Maximum relative
velocity error was 7.66891475e-8, tracer error 3.49280828e-8 and learned divergence
1.311302185e-6. Native residual, Courant and zero learned-iteration gates passed.
The unit-gain ablation produced the exact native physics rejection, verified by
exit status, bounded diagnostic bytes/hash and threshold.

Checkpoint SHA-256: `e08e85d991d2734383d14501d6dcfdaccb45dfd53370d883c26b44e84255f5f8`.
Training NPZ SHA-256: `3ca87734e4ebe41320328b130908dc88b85967dcc745f80f8c207cf29b539184`.
Freeze SHA-256: `020ac431def0540edca65b6009ee77ebf8a5eff414efd9cf7da38532ef711792`.
The qualified captured runtime remains `cc54ef199fc192b70f702e85dda70bfc8697bf3220373ae9f031afd8b237f0a7`.

## Public workflow and durability

The browser selected six frozen releases, saved the graph, preflighted the exact
material, granted owner approval and submitted through the existing Runs owner.
Actual loading/validation progress and verified checkpoint metrics appeared in
the compact UI. Six HTTP artifact downloads were hash-checked; after a cold
server restart, all artifact bytes and result/progress evidence remained equal.
The twelve loopback-only offline canary checks passed. Desktop (1440 px) and
narrow (390 px) screenshots capture Pipeline, live validation and completed
results. Final UI inspection hides the unrelated pending-stage table for external Runs
and collapses raw custody identifiers while keeping actual status, metrics and
checkpoint prominent. A separate read-only browser recheck passed at both widths,
verified the checkpoint download, and confirmed all 20 Run IDs stayed unchanged.
It did not rerun or requalify model fitting. See the [inspection receipt](p5b/inspection-receipt.json).

## Retained failed attempt

Earlier Run `ece8abe0a4024d1483048d91b7980cf0` failed and drained after fitting and
validation because the adapter expected the wrong native diagnostic prefix.
The fix recognizes only the exact pinned `trajectory probe: ` prefix and retains
all physics/hash checks. Regression coverage uses the observed native line and
rejects unrelated diagnostics, wrong thresholds, signal exits and hash mismatch.
The failed Run/project remain retained; success uses a fresh captured project
and approval. No unknown attempt was automatically retried.

## Verification status

Independent source review found no blocker. Focused generic contract/progress
tests passed (26); producer tests passed (10, including real native eight-frame
generation); training adapter checks passed (12 with the pinned assembly/runtime
inputs); helper/import regressions passed (61). Plan validation and diff checks
passed. Final regression passed: 838 Python tests in 1,155.485 seconds, with five optional
skips covered by 32 qualified reader/training tests (zero skips). All 56 CI-listed
JavaScript syntax/controller checks passed. The 196 Python source files remained
unchanged throughout; after the authorized compact UI/harness changes settled,
all 123 final JavaScript files remained unchanged during their checks.

Both hosted workflows passed at exact PR51 head
`28c666f115ca8fac7daf29096e91493ff7b0cc10`: interface run38460254846 and
lifecycle run38460254594. Source inventories are retained alongside this report.
P5b is qualified; P5c and P7 remain separate gates.

## Evidence and limits

- [Actual browser receipt](p5b/receipt.json), [independent cold oracle](p5b/cold-report.json), [Run summary](p5b/run-summary.json).
- [Frozen input inventory](p5b/prepared-inputs.json), [input consumption receipt](p5b/input-receipt.json), [training freeze](p5b/freeze.json), [actual result](p5b/result.json).
- [Verified progress/result projection](p5b/completed-progress.json); twelve generation cold reports and six screenshots are retained in `p5b/`.

Full payloads remain in the local catalog and QA directory, not Git. QA-authored
owner review is not independent end-user scientific certification. Training
validation fields were compared in memory and are not retained by this bounded
recipe. Autonomous evaluation with durable full fields is P5c, still pending.
There is no GPU, new holdout, general 3D training, ASR or historical timing claim.
P7 backup/restore remains pending.
