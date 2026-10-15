# Frozen independent A producer oracle

Status: ready before the first A producer execution. This is independent numerical
review preparation, not E2 acceptance, a host model/evidence ABI, E3 authoring
acceptance, a qualified execution profile or a physical/generalization claim.

The oracle author read the canonical
[A specification](acceptance-procedures.md#concrete-ab-extension-specification)
and the frozen fixture only. The author did not read, import or execute producer
worker source. No production numerical work was run while freezing this oracle.

## Frozen inputs and independent equations

- Fixture: `examples/extensions/field-surrogate/v1/fixture.json`.
- Fixture SHA256:
  `0074fd7a67701a94babd9abf9e166d3435427bb032ba9b49c9d63636b397f2f3`.
- Oracle: `tests/qualify_extension_producer.py`.
- Oracle SHA256:
  `0f6128d76ab7da277448449ea90534b111d8190893c38ef75fa1b2889d5528a7`.
- Exact fit members: `train-0`, `train-1`, both split `train`. The sole probe is
  `validation-0`, split `validation`; no validation point enters fitted statistics.
- Each member has 64 dimensionless field values in C-order ZYX, shape `(4,4,4)`,
  cell-centered, meter coordinates with unit spacing and no physical timeline.
- The independently checked target equation is `y = 0.5*x + 0.25` for every
  training and validation point.

For the 128 explicitly selected training values, derive population mean
`mu = math.fsum(x)/128` and standard deviation
`sigma = sqrt(math.fsum((x-mu)**2)/128)`. This gives `mu = 0.734375` and
`sigma = 0.946441732556738`. Use `z = (x-mu)/sigma`.

The affine optimum for this authored equation is
`a_star = 0.5*sigma`, `b_star = 0.5*mu + 0.25`. On this population,
`mean(z)=0` and `mean(z*z)=1`. Full-batch mean squared error therefore has
gradients `2*(a-a_star)` and `2*(b-b_star)`. Starting with `a_0=b_0=0`, learning
rate `0.1` gives, independently of the producer implementation:

```
a_t = 0.5*sigma*(1 - 0.8**t)
b_t = (0.5*mu + 0.25)*(1 - 0.8**t)
```

Freeze observations at actual optimizer-update clocks `t=16` and `t=64`, after
64 total updates. The consumer compares retained weights against these analytic
values. It independently reconstructs every validation point from the retained
weights and retained transform, and also checks the direct analytic trajectory
`prediction_t = (0.5*x + 0.25)*(1 - 0.8**t)`. It independently retallies reference
MSE with `math.fsum((prediction-(0.5*x+0.25))**2)/64` and compares the reported MSE.
The output report records this retallied value even when it is very small.

The frozen comparison rule for numeric checks is exactly
`abs(actual-expected) <= 1e-10 + 1e-10*abs(expected)`. It is an agreement tolerance,
not an optimizer-quality cutoff, convergence promise or scientific acceptance
threshold. Matching two retained observations establishes agreement with the
selected trajectory at those clocks; it cannot independently prove the worker's
internal execution history or authenticity.

## Retained-output boundary

The artifact directory must contain exactly these six flat files, with no extra
files, directories, links or special files:

| File | Selected representation |
| --- | --- |
| `transform.npy` | C-order `<f8`, shape `(2,)`, `[mu,sigma]` |
| `weights-16.npy`, `weights-64.npy` | C-order `<f8`, shape `(2,)`, `[a,b]` |
| `prediction-16.npy`, `prediction-64.npy` | C-order `<f8`, shape `(4,4,4)` |
| `diagnostics.json` | Strict bounded JSON with the closed fields below |

Diagnostics contain exactly `fixture_sha256`, `fit_member_ids`,
`probe_member_id`, `learning_rate` (0.1), `updates` (64), `observations` and
`scope` (`producer-preparation-only`). The two observations are ordered 16,64
and contain exactly `update`, `weights_sha256`, `prediction_sha256` and
`reference_mse`. Clocks must be integers without boolean coercion; populations,
fixture identity and both hashes must match the actual retained bytes. The
consumer records SHA256 for every artifact, including transform and diagnostics.
These are content identities, not authenticity or numerical-quality proofs.

The independent parser uses only stdlib `ast`, `struct`, JSON and ordinary file
operations. It never imports NumPy, Torch, app, database code or worker source.
Files are held through no-follow regular-file descriptors and stable bounded
reads. JSON is limited to 64 KiB and 16 nesting levels; duplicate fields,
nonfinite values, coercions and unexpected fields are rejected. NPY files are
limited to 8192 bytes, with headers at most 4096 bytes; only versions 1.0/2.0,
literal closed headers, explicit `<f8`, exact shapes and C-order are accepted.
Object/pickled/native/big-endian types, Fortran order, unsupported expressions,
nonfinite payloads, truncation, trailing bytes and oversized data are rejected.
The artifact directory's exact inventory is checked before and after reading.

Invoke the consumer after producer outputs are closed and retained:

```sh
python tests/qualify_extension_producer.py \
  --fixture examples/extensions/field-surrogate/v1/fixture.json \
  --expected-fixture-sha256 0074fd7a67701a94babd9abf9e166d3435427bb032ba9b49c9d63636b397f2f3 \
  --artifacts /path/to/retained-artifacts \
  --report /path/outside-artifacts/new-oracle-report.json
```

The report must be a new file outside the retained artifact directory; existing
files are never overwritten. Exit0 means the cold independent numerical checks
passed; exit1 is rejected retained material; exit2 is an unusable report
destination. All reports retain scope `producer-preparation-only` and
`product_acceptance:not_established`. A fresh Python process needs stdlib only.

## Preparation evidence and limits

Fixture hash and member/equation/statistic derivation were checked independently
before execution. Python compilation succeeded. A stdlib-only synthetic
oracle-consumer harness passed NPY v1/v2 and fresh-process CLI positives, nineteen
malformed-array/lineage/hash/inventory negatives, and rejection of a report inside
the retained directory without modifying that directory. This harness authored
expected retained bytes directly; it did not execute a producer or optimizer.
The oracle source hash above remained unchanged through these checks. Synthetic
oracle-consumer checks are separate from any producer execution; no
synthetic artifact is evidence of an actual optimizer, admitted Run, custody,
publication, stage service, protected-population enforcement or E2/E3 gate.
The parent owns subsequent real producer execution and its separately retained
receipts. Oracle or fixture changes require a new explicitly frozen hash before
the affected producer execution; existing evidence keeps its original identities.
