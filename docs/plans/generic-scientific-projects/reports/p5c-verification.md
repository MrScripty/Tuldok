# P5c autonomous CPU evaluation verification

Status: actual CPU scientific, custody, HTTP and restart gates passed; final
local regression remains in progress; refreshed loaded-slice screenshots passed.
Source checkpoint is draft [PR52](https://github.com/MrScripty/Tuldok/pull/52),
`d191e681011756d7d3204604a410fe5619b5c559`. P5c remains verifying until its final gates close.

## Actual execution

Run `e731c9569b7d41f9a8f6cde438dcf9ac` uses project
`a32555aabdee479ab94a9cb4159f5a73`, recipe digest
`777fccef814adfeb7afcf599cb56e31faf361b4c6afbd3e80b5b899c87ce271b`, and
the fresh checkpoint from completed P5b Run `11fc2be1aada490f9b67c11c190728f6`.
The checkpoint SHA256 is
`e08e85d991d2734383d14501d6dcfdaccb45dfd53370d883c26b44e84255f5f8`.
Four typed completed-Run inputs bind checkpoint, freeze, training observations
and training result to their retained custody. No manual checkpoint-copy bridge
is part of this workflow.

The unchanged scientific protocol evaluates four previously exposed seeds
900–903 at 32³ for 120 frames, then benchmarks five repetitions of all four seeds
and three original methods with eight CPU threads. The optional adapter retains
all six scientific arrays, exact native stdout, original compressed NPZ results,
viewport and original metrics. Sixty-four bounded scientific bundles permit
ordinary Data import without a new array-storage system. There are 89 declared
outputs with a 3,500,000,000-byte aggregate bound and a 2,400-second child limit.

Actual admission measured 8,266,240,000 free bytes against the
8,073,741,824-byte staging/publication guard. Source remained frozen throughout
the actual Run. Executor transport loss was separately observed; reconnection
confirmed the original browser/server and Run continued. No replacement Run or
blind admission retry was performed.

## Actual acceptance evidence

- Run completed and drained in 1,601.241886 seconds, with no stderr and no
  replacement admission after transport interruption.
- All 89 outputs total 3,086,837,711 bytes. Each authenticated HTTP stream matched
  its declared SHA256/length, then every stream matched again after cold restart.
- Independent cold comparison covered all 960 accuracy frames, 5,760 arrays and
  eight complete wire trajectories, including learned pre-report RHS bytes and
  overlapping original NPZ/viewport values. Maximum relative velocity-or-tracer
  error was 8.885705993537438e-8; maximum independently recomputed MAC divergence
  was 1.430511474609375e-6.
- All 60 original benchmark trajectories and 7,200 frames passed original
  diagnostic gates and arithmetic checks. Median 120-frame walls were
  36,691.010262 ms Jacobi, 26,321.438251 ms SGS and 4,756.986147 ms learned on this
  measured CPU environment. These are local observations, not historical hardware
  reproduction or unexposed-test claims.
- Independent arithmetic covers numerical errors, MAC divergence and tracer
  integral. Residual/Courant evidence checks producer reports against original
  thresholds; it is not independent solver reconstruction.
- Representative record `9df813a605d746709eb0c245f16f4033` was imported from a
  complete retained chunk, inspected and explicitly reviewed by the QA owner;
  its identity/review survived restart. Root found the first narrow screenshot
  still displayed loading. A separate read-only inspection then captured loaded
  pressure canvases at 390 and 1440 pixels, preserving the exact record and all
  Run/record IDs. Root visually reviewed the refreshed loaded slice and summary.
  [Inspection receipt](p5c/loaded-inspection.json),
  [loaded narrow slice](p5c/inspection-loaded-data-390.jpg),
  [desktop results](p5c/inspection-summary-1440.jpg).
- Hosted checkpoint UI run 38462526672 and lifecycle run 38462526507 succeeded.
  Root's independent review owner verified the terminal lifecycle log through
  final workspace breadth and artifact upload; the job-step API lagged that log.
  The hosted base suite ran 860 tests with 12 optional skips; dedicated native
  and adapter gates ran separately, with actual source-assembly availability
  explicitly skipped on hosted runners. Local real evaluation provides the
  required model evidence. Final local base regression passed 860 tests in 1,226.890 seconds with six optional skips. Dedicated point-cloud (11), volume (9), training (12) and evaluation (9) suites passed with zero skips against the qualified native assembly. All 56 CI-listed JavaScript/syntax commands passed. All 327 inventoried source files remained unchanged; see [source receipt](p5c/regression-source-files.json).

Evidence: [cold oracle](p5c/cold-report.json), [actual browser receipt](p5c/browser-receipt.json),
[first HTTP inventory](p5c/completed-http-inventory.json),
[restart HTTP inventory](p5c/reopened-http-inventory.json).

The browser evidence directory is
`build/qa/workspace-rheon-evaluation/run-hWVrH7`; owner-local oracle reads are
matched to every HTTP artifact hash and do not claim agent-interface parity.
Large Run listing verifies inventory/custody and explicitly leaves payload bytes
unchecked until selected download or full audit. The HTTP download owner verifies
the complete selected artifact before sending success.

## Scope

This is CPU qualification of the original modal surrogate and exact captured
runtime. It does not qualify CUDA, general 3D training, new holdout performance,
historical speedups, runtime sandboxing, or P6/P7. The test seeds were already
exposed and remain labelled accordingly. P5b fitting, CPU runtime verification,
native source/build identity and its final regression evidence remain separately
owned by [P5b verification](p5b-verification.md) and the P5a reports.

## Retained artifact storage

After completed/drained custody and matching published hashes were independently
checked, the exact 89 staging-output duplicates were removed. All 89 authoritative
published artifacts were rehashed afterwards; their Run document and protected
trees were unchanged. No failed staging, inputs, custody, snapshot or published
artifact was removed. The cleanup reclaimed 3,087,097,856 allocated bytes.
[Exact inventory](p5c/evaluation-duplicate-inventory.json),
[cleanup receipt](p5c/evaluation-duplicate-cleanup-receipt.json), and
[measured capacity](p5c/postcleanup-capacity.json) retain the scope and proof.
This does not qualify P7 backup/restore.

## Hosted browser follow-up

The evidence-only head1c0cb6f lifecycle38474813909 passed full Python discovery
but later failed browser_captions.cjs with CDP `Inspected target navigated or
closed`; diagnostics still showed the new document loading. The script read DOM
state immediately after navigation acknowledgement. It now uses the existing
pageLoadTracker's changed-main-loader/load barrier for initial navigation and
reload, preserving assertions and time bounds. Full native Chromium caption
workflow and existing load/startup/auth regressions pass. A real Chromium timing
trace measured six pre-load reads before the fix and zero afterward; the exact
hosted error was not reproduced locally. This changes QA ordering only. The
actual scientific runtime, algorithms and qualified artifacts are unchanged.
Fresh hosted lifecycle acceptance remains required for the updated head.
