# P4 one-fit and generic scientific co-test implementation

The text/audio model-aware recipes now use normal model publication, captured
recipe material, finite Study admission and Runs. Each performs one actual fit,
retains one descriptor/weight/transform/probe closure and exposes the shared D2
evidence query. There is no fabricated epoch, optimizer-update count, physical
time or curve. Legacy recipes retain their closed original results. This is
the implementation follow-up authorized after the design-only handoff.

The [retained measured receipts](p4-one-fit-qualification.json) were produced
with `tests/qualify_model_development.py --task text|audio --fixture
tests/fixtures/model_development --output <fresh-directory>` using the
separately provisioned sklearn 1.7.2 CPU runtime and disposable PostgreSQL.
The driver uses actual authenticated HTTP operations, published source/model
material and real child processes. It does not inject completed rows or
artifacts. Readiness is scoped to these task/runtime contracts.

| Actual task | Checkpoints | Validation probes | Retained bytes | CPU peak RSS | Qualification elapsed | Independent inference maximum error |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Text | 1 | 5 | 28,346 | 118,145,024 bytes | 35.74 seconds | 0 |
| Audio | 1 | 5 | 32,604 | 127,709,184 bytes | 35.31 seconds | 1.39e-17 |

Each driver cold-reopened the catalog and compared its evidence, then copied
only `model.json`, validation inputs and the independent test oracle into a
separate directory. An isolated interpreter imported no adapter or checkout
module and reproduced the fixed probabilities within 1e-12. This verifies
frozen inference; it does not promise a general inference package or transfer
training-data distribution rights. Source fixture, source generator when
applicable, oracle and actual adapter/runtime identities are retained.

Focused evidence includes 15 one-fit producer/contract tests, 7 generic field
contract tests, 2 real HTTP Study/Run tests and the image model-evidence
regression suite. Existing text/audio suites also passed (14/13 tests). Graph
contract 3 adds the new recipe variants; exact prior contract-2 hashes and
legacy discovery remain unchanged. A missing or old selection fails before
new graph creation. Queries never launch a model or expose test predictions.

Scientific `field_evidence.py` validates a domain-owned versioned field/stage/
gauge/input/output contract, exact canonical-release NPY derivation receipts,
whole selected member/frame accounting and ordered train fit IDs. The generic
fixtures prove representation/custody only. They preserve independent failed
physical results after successful inference and cannot qualify physical
accuracy. Scientific test evidence stays unsupported across the complete
accessor population pending owned permission qualification. Domain-owned NPZ
packing and actual external physical qualification remain separate; no lab or
Rheon numerical sources changed.

UI qualification and the optional scientific integration are coordinated by
their separate owners. This report claims the text/audio authenticated
HTTP/Study/Run and cold-inference path, not their browser workflow, optional
physics, generic packaging or public redistribution.

Independent review reproduced a self-consistent wrong-fit snapshot that the
initial reconstruction-only check accepted. The worker verifier now recomputes
train-only text vocabulary/IDF and audio mean/population scale from exact source
inputs, without fitting another classifier. Bit-exact checks use the pinned
numerical primitives, including vocabulary frequency ties and near-constant
scaler features. Rebuilt wrong-stat snapshots, boolean clocks, non-integer Blob
lengths and singleton boolean field shapes are rejected. The one-fit loss
definition explicitly names sklearn float64-epsilon probability clipping.
