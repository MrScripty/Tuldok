# Synthetic publication semantic recovery qualification

The final qualification passed in 164.443 seconds on base `6cc5943`. It retained
27 artifacts after one real synthetic child completed/drained, then recovered
the original interrupted Run. Counts stayed at one Run, grant, consumption and
reservation. The temporary catalog/runtime and PostgreSQL schema were removed.
See `qualification.json`, `qualification.log` and the file hashes in `validation.json`.

This opt-in qualification exercises the real captured CPU runtime, Model/Study
publication and admission, context, custodian, frozen publication source, cold
same-Run recovery, and extension semantic verifier. The child only serializes
explicitly synthetic protocol states. It never imports the example's numerical
producer, fits a model, optimizes weights, or invokes an independent numerical
oracle. Fixture counters and constant metrics are labels, not training results.

Run from the reviewed worktree with an explicitly supplied disposable PostgreSQL
DSN in `TULDOK_DATABASE_URL`:

```sh
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=.:tests \
  /workspace/tuldok-runtime/bin/python tests/qualify_publication_synthetic.py \
  --runtime-config /workspace/p5-qualification/runtime-config.json \
  --expected-runtime-sha256 50502c0ba923f3134073188efd55c20b0468c008b1bdfbdc87fd72ea830ffe3d \
  --reserve-bytes 805306368 \
  --report docs/plans/lab-workflow-reliability/reports/m1-publication-synthetic/qualification.json
```

The existing `RuntimeSnapshots.inspect/create` owner captures the exact nominated
runtime into a fresh temporary catalog. The explicit 768 MiB operator reserve is
local to this capture; production defaults and the runtime config stay unchanged.
The driver records free/required bytes and refuses insufficient space or a changed
runtime inventory. This reserve includes the existing 512 MiB publication floor
and bounded fixture headroom. The runtime is about 897 MB; fixture output is
bounded at 1 MiB. Only this qualification's own catalog, runtime copy and database
schema are removed by cleanup. Existing qualification catalogs are never opened.

The only execution fault is an injected output-copy error after the real child
has completed and drained. Recovery wraps, rather than replaces, the real
extension verifier and checks its source/destination/reader calls. It prohibits
another process launch, preserves the original state/events and exact settled
Study reservation/charge, and checks that legacy failed readers and candidate
promotion still refuse. No numerical, real-lab, CUDA, new transport, segmented
collection, or full M1 acceptance is established.

`qualification.json` binds the tested driver and producer hashes to the outcome.
The initial failed attempt is retained separately: its final harness check
incorrectly expected a returned legacy evidence state instead of the correct
typed unavailable refusal. That attempt is not counted as a passing qualification.
