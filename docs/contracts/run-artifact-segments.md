# Bounded sequential artifact segments

`runs.artifact_segments/1` is an explicitly selected read operation at
`POST /api/workspace/artifact-segments`. Headerless calls refuse. Existing
individual Run/publication operations and all 122 prior full contracts remain
unchanged. This operation creates no Run, grant, consumption, publication,
reservation, process or cache. Segment bytes remain provisional until the caller
verifies each complete artifact SHA256; no science or import/promotion follows.

The closed request is `{items:[...]}` with 1–20 ordered items. Each item has a
unique 1–64 character key (`A–Z a–z 0–9 _ . : -`), a closed `source`, `name`,
`expected_sha256`, `offset` and `max_bytes`. Sources are either
`{kind:"run",run_id}` or `{kind:"publication",ref}` with the complete existing
attached recovered-publication Ref. Offset is 0–512 MiB. Each requested bound is
1–8 MiB and their sum must be at most 8 MiB. All item grammar and aggregate caps
are checked before artifact reads. Requests cannot select private receipt or
manifest filenames. Initial support is external Runs and attached publication
Refs; built-in Runs receive a typed `unsupported` item result.

The response is `{format:"artifact_segments_v1",items:[...]}` in request order.
Each outcome echoes `key` and exact `source`. A success has `status:200` and
`result` equal to the existing canonical Run/publication segment projection.
An item failure has a 400–599 `status` and closed `error:{code,message}`. Wrong
hashes, missing items and unavailable legacy failed-Run reads can coexist with
successful authorized items. The free consumer decoder
`agent_api.validate_artifact_segments(value,request)` checks order, exact source,
selectors, Ref, arithmetic and segment hash. Callers must still verify complete
whole hashes and discard provisional data on failure. No fallback or retry is
implied. The canonical AgentClient also checks request correlation and the
configured catalog for successful publication items.

Reads are sequential, buffered and share a 60-second owner deadline. Existing
catalog command ownership and SQL deadlines are reused. Optional domain
cancellation and owned shutdown are checked between items and through canonical
copy/semantic checkpoints. There is no persistent cancellation request, mutation
retry or new compute authority. The request rechecks current inspection and
transitive authority for every item, then every distinct exact successful source
before domain return, retaining last-occurrence order. HTTP repeats the delivery
fence after output-schema validation and serialization. Current credential loss, delivery authority loss, shutdown,
cancellation or exhausted budget discards all buffered bytes. Individual
ordinary readers retain their previous defaults; optional private checkpoints
only support this new operation.

The batch layer passes a private external-only flag, defaulting false, to the
canonical decorated Run reader. Eligibility is checked immediately after that
reader's own load, before built-in dispatch. Every item retains independent
initial authorization, retained-inventory verification and its canonical read.
Each final stage rebuilds exact-source identities in last-occurrence order
(A,B,A becomes B,A), then reloads current Run/transitive authority and exact
published attachment. No loaded Run, authority result or seen set is reused
between domain return, HTTP delivery or requests. These remain sequential
current checks, not an atomic snapshot of every source's permissions.

Current pin: `510198cf8617f297b45b5b5100692e76aa3de5f865019730843b18d1d8ee7e39`.

## Local qualification

The initial eight-case actual PostgreSQL/neutral custody and pure group passed,
as did five canonical reader regressions. The refined sixteen-case module ran
with fifteen passes and one new harness error after already proving shutdown
returned HTTP 409 with no items. Only its assertion changed to the established top-level
error code; the affected actual case then passed. Both logs are retained.
Actual qualification covers repeated canonical reads and fresh final proofs,
A/B/A authority loss at domain and post-serialization boundaries, duplicate late
credential revocation/shutdown, mixed exact Run/Ref partial outcomes, legacy
failed-Run refusal and unchanged accounting/events. Independent source review
was clear and all ten current pure cases passed, including all 122 prior full
contracts, source identity, default reader behavior, cancellation and deadlines.
This does not claim hosted acceptance or complete M4/T5 qualification.

## Measured collection cost

The full frozen `9838022` same-head/catalog/inventory matrix completed with 54
pairs/108 collection arms. Every eligible cell has three first pairs in fresh
application processes and six warm pairs. Order alternates; a first pair's
second arm already follows its first arm. Bootstrap, population and real same-Run
copy recovery are excluded from collection pairs. Each arm reads 327,680 raw bytes
in one or twenty artifacts. No OS/PostgreSQL cache flush or exclusive host is
claimed. The fixture executes neutral byte copying, with no training or science
claim. Whole hashes, counts/events, source/harness identity and both exact owned
schema/temporary-directory cleanup checks all matched.

Ratios below are batch/individual wall time computed within each pair. Values
below 1 are faster. These small descriptive samples have no confidence interval
or latency-budget acceptance.

| Source | Total terminal history | Artifacts | First median ratio (n=3) | Warm median ratio (n=6) | Faster pairs /9 |
|---|---:|---:|---:|---:|---:|
| run | 8 | 1 | 2.667 | 2.843 | 0 |
| run | 8 | 20 | 0.714 | 0.662 | 9 |
| run | 55 | 1 | 2.016 | 2.612 | 0 |
| run | 55 | 20 | 0.700 | 0.649 | 9 |
| publication | 56 | 1 | 1.657 | 2.138 | 0 |
| publication | 56 | 20 | 0.710 | 0.712 | 9 |

All 27 twenty-artifact pairs were faster; all one-artifact cells regress. For the
simple ordinary source without transitive Run loads, twenty canonical reads and
inventory checks remain, with 20 individual loads versus 22 batch loads and 20
requests versus 1. Publication readers retain all their original subloads.

Retain this operation for explicit bounded collection under the measured many
small twenty-artifact condition. Default individual collection remains unchanged.
Performance for 2–19 artifacts, different sizes, scientific outputs, remote
networks and the separately owned collection facade is not established here.
No automatic threshold/selection, fallback, cross-call cache or generic workflow
speedup follows. The first full `99741e5` candidate matrix is retained as a negative
result, without rewriting or excluding its regressions.

Full first/warm/arm-order distributions, process CPU/RSS/I/O, HTTP body counts,
inclusive owner counters/times, raw integrity receipts and exact source hashes
are in [the refined report](../plans/lab-workflow-reliability/reports/m4-bounded-collection/paired-9838022/results.md).
The [earlier negative report](../plans/lab-workflow-reliability/reports/m4-bounded-collection/paired-99741e5/results.md)
and [correctness history](../plans/lab-workflow-reliability/reports/m4-bounded-collection/refinement/qualification.json)
remain separate. PostgreSQL backend CPU and SQL command counts were not measured;
RSS/HWM values are snapshots/lifetime values rather than phase peaks, and
inclusive owner timings must not be added.
