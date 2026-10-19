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
implied; client integration is separately owned and remains pending here.

Reads are sequential, buffered and share a 60-second owner deadline. Existing
catalog command ownership and SQL deadlines are reused. Optional domain
cancellation and owned shutdown are checked between items and through canonical
copy/semantic checkpoints. There is no persistent cancellation request, mutation
retry or new compute authority. The request rechecks current inspection and
transitive authority for every item, then every successful source before domain
return. HTTP repeats the delivery fence after output-schema validation and
serialization. Current credential loss, delivery authority loss, shutdown,
cancellation or exhausted budget discards all buffered bytes. Individual
ordinary readers retain their previous defaults; optional private checkpoints
only support this new operation.

Initial qualification passed eight tests in 47.251 seconds with zero skips:
real disposable PostgreSQL and neutral custody for mixed completed Run/recovered
Ref collection, whole hashes, typed partial errors, legacy gate, headerless
refusal, unchanged accounting/events, actual credential revocation after
serialization and injected current transitive denial at delivery; pure caps,
correlation, shutdown/cancellation/deadline and full prior-contract equality.
The initial missing-method red witness is retained. This checkpoint does not
claim independent clearance, hosted acceptance, broader regression completion
or a performance improvement. Paired same-candidate-head/catalog/inventory
individual/batch measurements with alternating order remain pending.

Current pin: `510198cf8617f297b45b5b5100692e76aa3de5f865019730843b18d1d8ee7e39`.

The separately committed paired harness alternates individual/batch calls on
the same candidate head, catalog and exact inventory. Each eligible cell uses
three fresh application processes and two warm pairs per process (n=3 first
pairs and n=6 warm pairs). Empty history has no eligible artifact and is recorded
unavailable. Normal completed histories are 8 and 55; additional attached-Ref
pairs use the same inventory after one real copy fault/recovery, so total history
includes that original interrupted Run. Bootstrap is measured separately and
excluded from both arms. Failed/corrupt/partial replies cannot count as improved
samples. Same-head whole hashes, events and admission/accounting counts must
match, and no compute can run during paired reads. Final costs remain pending.

The measurement checkout normally composes root92546d7, including the canonical
AgentClient request-aware decoder/configured-publication-catalog checks and the
M6 operation. Both arms use that same composed client. The harness avoids a
second redundant request-aware decode, retains explicit whole SHA256 equality,
and records delegating inclusive `_load`/inventory/segment/result owner counters.
A composed one-artifact pilot passed both normal and attached-Ref first/warm pairs
with alternating order and own-schema cleanup. Eleven relevant pure/correlation
cases passed. Exact final source/harness hashes are recorded at measurement start;
these composed measurements are not attributed to production007 alone.
