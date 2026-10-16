# Independent B: second frozen consumer on actual retained evidence

The separately authored consumer at `311431ecd45fc8331cb5ca9361e318ff42c16f44`
passes on the 26 cold whole-hash downloads from actual B Run
`3ceea12b26754accb2c65f3a0aa5038f`. Its analytic kernel is byte-identical to
`81c0c5d6711c07ac94ee06d6e28bd674f8134c3f`, frozen before B producer inspection.
Neither the producer nor the author's numerical oracle was imported. This is
additional offline retained-evidence verification, with no SDK invocation,
catalog opening, admission, training or optimizer execution.

The [machine receipt](examples/independent-b-actual-cold-consumer.json), SHA256
`73fc61e5a94810e66d760100873a3539279cad707c184a71bda4c2a3409bd4a5`,
records every code hash, selected identity, public receipt hash, all 26 artifact
hashes and the unmodified consumer result. The source host is `e5d1d79` and the
current/cold download verifier is `3affe90`; their execution and recovery history
belongs to the separate B qualification report.

Expected Run/catalog, Model/Task and composition identities came from separately
retained public Run, Model material and recipe material responses. The context
SHA256 `1233354af8146f2c9d70a4fddd5232f78161110a6de70dd4cfc650a3bbbbdc6b`
was selected from the unique public Run artifact receipt, rather than obtained by
hashing the context under test as its own expectation. Fixture SHA256
`5ab71e1f6a24caf039df419d60d1d39a3592bf25079a7a6f9503779069dc16fe`
comes from the initial pre-admission review inventory. The held fixture and all
26 cold files match those independently selected whole-file identities.

The Run's execution material SHA `97de63fe...` and its approved composition SHA
`6d19d4d0...` remain distinct. The former equals the public composition's
`executable_sha256`; the latter equals its immutable reference and the Run's
approval material identity. The consumer selects the composition identity required
by the evidence context, with no substitution between those two hashes.

Under CPython with `-I -S -B`, the unchanged consumer checks the exact initial,
source and boundary-mask inputs, two ordered output stages, source geometry and
gauge, complete validation membership, native payload/target identities and
checkpoint clocks 32/64. It independently computes train-only population means
and standard deviations. A closed-form calculation of the two correlated affine
feature modes and intercept checks the retained weights without running gradient
updates. Reconstruction uses the retained fitted transform and weights; separate
raw and boundary-enforced reference MSE values are retallied.

| Actual check | Maximum absolute difference |
| --- | --- |
| Train-only normalization | `1.096345236817342e-15` |
| Closed-form weights, updates 32/64 | `4.996003610813204e-16` |
| Retained replay, both stages and checkpoints | `2.220446049250313e-16` |
| Retallied reference MSE | `2.117582368135751e-22` |

All comparisons use the independently frozen absolute and relative tolerances
`1e-10`. The 23 focused numerical-kernel, evidence-contract and consumer tests
also pass with zero skips in 0.966 seconds. These include bounded reads,
coherently rehashed identity/field/source mutations, train-only membership,
stage-specific target refusal and rejection of a structurally valid zero state.

No semantic mismatch was found for this actual B protocol. This result establishes
only the named retained-byte identity, affine trajectory/replay and diagnostic
MSE checks. It does not establish current authority, physical validity,
generalization, product conformance, stopped restore or browser qualification.
The public SDK's numerical result remains `not_evaluated`.
