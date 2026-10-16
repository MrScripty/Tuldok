# Independent B: actual captured CPU qualification

The independent B package completed one public SDK admission and source Run on
2026-10-16. SDK conformance passed, and separate recovery 02 verified all 26
retained artifacts against the original SDK, current HTTP and cold HTTP downloads.
The frozen stdlib numerical oracle reports `valid` for actual checkpoints 32/64.
This report establishes this B package-seam execution, retained identity and
numerical reconstruction; it makes no physical diffusion or generalization claim.
The [hashed evidence inventory](independent-b-50502-qualification.json) retains the
exact identities, 26 artifact hashes, receipt hashes and linked evidence snapshots.

## Frozen source and one admission

The source package is `example.scalar-b-independent@1.0.0`, authored at commit
`db5ce541feb78ca371dc3b6607f27c5725c16518`. All 18 files still match the
[initial review freeze](examples/independent-b-02/author-review-freeze.json);
reviewed inventory SHA256 is
`de73d348bd34a1be19a37c419ab834f520fb008a84b15096d536a17852a6b859`.
The mathematical producer, independent oracle, fixture and oracle-freeze bytes
were unchanged before admission, during both verification recoveries and at this
report's offline hash check. The source branch remains intact; this report changes
documentation only.

The application-owner source was frozen at
`e5d1d7980fb7d806fc5dba937d9a6f8ca465f62c` for the B source attempt.
The [149-file freeze manifest](examples/independent-b-02/application-owner-freeze.json)
hashes to `7ff4b102389f488fcca66fdc8b3329a3931417563841c091e787f3493e59b3da`.
Root's retained [complete postcheck](examples/independent-b-02/application-owner-postcheck.json),
SHA256 `512cb5f1ef79b26d64de384734a3dd8f0258e37247e9ad13355e18dda9acdc0b`,
records all 149 expected/actual hashes matching on integration commit
`d5e01e354ecde403f776f1c7fb4efd635494b722`. This source-byte check belongs to root;
the author and P6 verified receipt identities without rereading application source.

The normal owner workflow prepared a finite one-slot Study, published the exact
Model/material and granted that material to the agent. The author then invoked
the supplied public SDK command exactly once, with the pinned trusted CLI and
agent-only credentials. The SDK exited 0; its
[original result](examples/independent-b-02/sdk-result.json) reports `state: passed`,
`contract.state: passed`, and `numerical: not_evaluated`. No owner credential, new
grant, re-admission, local execution fallback or SDK retry was used by the author.
The exact [prepared receipt](examples/independent-b-02/prepared.json) is retained.

| Identity | Exact value |
| --- | --- |
| Run | `3ceea12b26754accb2c65f3a0aa5038f` |
| Study | `f6c70cb21c45449488a89cc97ea62d7b` |
| Trial | `11a355fbc67f49c3a9cdf42087f09baa` |
| Recipe SHA256 | `7d089b3fe85191e5dbb3c222899e8b9629f4889708a10b854c533b73b0796416` |
| Provider SHA256 | `1f8cf0e8d7e9ec4e9c1a053087a923d6a338e926c77d5281558eaba2c5ea164f` |
| Full recipe source-closure digest | `e3b54b4af4ef1e41fd258ee0e4ed00b015dee20e3a4e420a7213810e812081e2` |
| Prepared material SHA256 | `6d19d4d06efabbdff713fd4148c38d5f9171773c01fba85b00e3156ee094e9e4` |
| Model material SHA256 | `9f631c81de088351b582609c8d9059911d1383606e5b2594081595fed1aba673` |
| Captured CPU snapshot | `50502c0ba923f3134073188efd55c20b0468c008b1bdfbdc87fd72ea830ffe3d` |
| Runtime reference SHA256 | `f74c644751dc1c038a85009a72da416118af1bb570f3e77b2c6aae52b3a6c3f2` |

The actual runtime reports Python 3.12 and NumPy 2.5.4. Its snapshot was explicitly
prepared; no runtime fallback was used. Snapshot identity and the catalog runtime
reference above have separate meanings.

## Preserved failures, settlement and successful recovery

The source Run and SDK conformance succeeded before the original operator
verification failed. The operator had copied the reviewed oracle and fixture into
its snapshot but omitted the required `oracle-freeze.json` dependency. The frozen
oracle raised `FileNotFoundError` when reading that snapshot file. The
[original failure](examples/independent-b-02/original-failure.json) and
[exact traceback](examples/independent-b-02/original-oracle-stderr.txt) are retained.
This was a verifier snapshot failure, not evidence of a failed source Run, and it
was not erased or replaced by a successful receipt.

One separate owner `studies.reconcile` settled the already completed B
reservation. The [accounting extract](examples/independent-b-02/settlement-extract.json)
binds the original full receipt by hash. It records `reserved → settled`,
`additional_charge: false` and `no_admission_or_sdk: true`. The retained charge is
one attempt slot, 197 admitted wall seconds, 4,366,403 retained bytes and 5,995,018
peak staging bytes. These are conservative admitted accounting values, not a
measurement of training duration or resource consumption. Shared catalog counts
for Runs, Studies, Trials, reservations, grants and consumptions were all 2 before
and after settlement: one A and one B source attempt.

Verification recovery 01 supplied the original reviewed dependency triplet and
obtained a valid numerical oracle result. It then stopped before HTTP dispatch:
its verification-only guard refused `POST models.material` at
`/api/workspace/model-material`, an existing read-only material operation omitted
from its route allowlist. The
[exact diagnostic](examples/independent-b-02/recovery-01-diagnostic.json) records
`verification_incomplete_no_admission`; its
[failure receipt](examples/independent-b-02/recovery-01-failure.json) is preserved.
This was an exact read-only guard refusal, not an authorization to retry admission.

Recovery 02 used the corrected verification-only helper at
`3affe90bc258c1327fde49faf57bceb852cc2759` to inspect the same completed Run. Its
[summary](examples/independent-b-02/recovery-summary.json) and
[successful receipt](examples/independent-b-02/recovery-02-receipt.json) record no
admission or SDK retry, a valid frozen oracle, current and cold whole-artifact
verification, and identical domain counts before/after. These helper fixes are
identified separately from the frozen application and mathematical package.

## Numerical and retained-byte result

B requires initial, source and binary boundary-mask arrays. The raw reference is
`0.5 * initial + 0.25 + 0.2 * source`; `boundary_enforcement` produces
`corrected = where(boundary_mask, 0, raw)`. Inputs, raw/corrected references,
train-only means/stds, three weights and both output stages were retained as
little-endian float64 native arrays. The two actual checkpoint clocks are 32/64
optimizer updates; these standalone dimensionless 4³ cell fields have no physical
timeline.

The [frozen stdlib oracle result](examples/independent-b-02/oracle.json) independently
checks gradient state and reconstructs each output from retained weights,
transform and inputs with `1e-10 + 1e-10 * abs(expected)` tolerance. Maximum gradient
state error is `4.996003610813204e-16`; maximum reconstruction error is
`2.220446049250313e-16`. Reference-target error is a separately retallied diagnostic:

| Optimizer update | Field/stage | Reference-target MSE | Maximum reconstruction error |
| --- | --- | --- | --- |
| 32 | raw / `raw_inference` | `1.4472054366887254e-6` | `2.220446049250313e-16` |
| 32 | corrected / `boundary_enforcement` | `1.7336691075130304e-7` | `2.220446049250313e-16` |
| 64 | raw / `raw_inference` | `7.329544376552364e-12` | `2.220446049250313e-16` |
| 64 | corrected / `boundary_enforcement` | `8.736419045724307e-13` | `5.551115123125783e-17` |

The documentation author independently checked all 26 artifact sizes and SHA256s
in three retained download sets: original SDK, current HTTP and cold HTTP
(78 whole-file comparisons). All 18 author files match the original review;
all summary-linked receipt hashes/lengths and the frozen oracle dependency hashes
also match. This report used offline file/receipt reads and started no host, SDK,
or numerical process. P6 separately verified these retained bytes, accounting
counts and oracle dependencies; its
[sanitized review receipt](examples/independent-b-02/p6-independent-review.json)
is included and explicitly excludes an independent 149-file application reread.

SDK `numerical: not_evaluated` and independent oracle `state: valid` remain separate
results. The oracle explicitly retains `product_conformance: not_established` and
`physical_qualification: not_established`; it does not qualify diffusion physics,
generalization, or the remaining E3 lifecycle/browser matrix. No credentials,
private agent configuration or runtime installation are included in this report.
