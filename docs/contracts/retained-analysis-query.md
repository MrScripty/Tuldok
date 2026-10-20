# Retained checkpoint examples query v1

Status: implemented and qualified in the verified native classifier Runs view.
Python entry point: `retained_analysis.query(runs, body)`. HTTP consumers select
`runs.retained_analysis/1` or `runs.export_retained_analysis/1` explicitly with
its published capability hash. POST routes are
`/api/workspace/runs/<run_id>/retained-analysis` and its `/export` sibling.
HTTP bodies omit run_id: the selected decoder rejects duplicate body IDs and
the handler injects the validated URL ID. The Python example below includes it
because the direct query entry point receives the full exact request.

```json
{
  "query_id": "retained_checkpoint_examples",
  "query_version": 1,
  "run_id": "<exact authorized native Run ID>",
  "evaluation_sha256": "<model-evidence.json exact artifact hash>",
  "checkpoint_sha256": "<exact retained checkpoint descriptor hash>",
  "metric_id": "accuracy",
  "metric_definition_sha256": "<exact metric definition hash>",
  "fields": ["example_id", "truth_index", "predicted_index", "confidence", "error"],
  "errors_only": false,
  "limit": 50,
  "offset": 0
}
```

Closed object; last four fields optional with shown defaults. Metrics allow
accuracy/loss/macro_f1 only. Fields must be unique and include example_id.
Integer booleans are rejected; limit 1–100, offset 0–10000. One exact completed
native `model_evidence_v1` Run, validation split only. Scientific field and
one-fit formats require their own later query variants. All hashes lowercase
64-character SHA256; a valid hash from another result/checkpoint is rejected.

Access: inspect checked before evidence and again after the SQL read snapshot,
including exports. No cache, training, inference, new analysis, checkpoint
deserialization or holdout exposure. Existing Runs verification re-tallies
retained metric evidence; it does not publish a new computed result.
`export=True` is a host-owned keyword, never caller metadata; it runs the same
bounded query under `runs.export_retained_analysis`. Each exported page is a
fresh authorized query; no unbounded export endpoint or persistent URL.

Runs verifies immutable bytes and graph/task compatibility. Query selects the
exact PostgreSQL workspace_runs row and checks artifact identity. Curve SQL
reads catalog metric history and joins verified checkpoint epochs. Every value,
epoch and support must equal retained observations. Bounded verified per-example
scalars are passed to PostgreSQL as a parameterized disposable recordset for
error filtering and stable ordinal pagination. This is an initial projection,
not a new persisted statistics schema. Original text and hash-bound bytes are
unchanged; JSONB casts never define evidence identity.

Budgets: 128 checkpoints, 10000 fixed-probe examples, 2 MiB scalar projection,
16 MiB existing Run document, 256 KiB response, 100-row pages; SQL statement and
lock timeouts 2000ms scoped to the read transaction, two-second ownership wait.
Existing Runs verification/artifact budgets still apply before SQL; the SQL
timeout is not a hard wall deadline on artifact verification. These initial
limits are explicit admission bounds, not measured performance targets. An
outer transaction is refused; a standalone read owns Repeatable Read and READ
ONLY. These settings are consistency controls, not an untrusted-SQL sandbox.
All query structure/relations/functions are server-owned; credentials remain
server-side. No new roles, privileges, DDL or production migrations.

Response: state verified; query ID/version; frozen mode; provenance including
catalog/Run/evaluation/checkpoint/metric-definition/population/probe/data hashes
and retained producer identity. Metric includes its original definition/units
and unfiltered support. Curve rows carry checkpoint hash, epoch, exact value,
support. Table columns carry type/units; rows always include stable example_id,
ordinal and complete frozen_reference. Confidence is the retained predicted
class probability. Errors mean truth_index != predicted_index. Population
support, filtered support, page offset/limit/next_offset and visible filters
remain distinct. Error filtering never recomputes curve statistics or changes
their population. No display sampling is used: the population is explicitly
the frozen validation probe, not an implied full dataset. selection_sha256
identifies canonical query settings and is not a new computed-result identity.

Failures use WorkbenchError: invalid request 400; unsupported query/task 409;
stale evaluation/metric 409; foreign checkpoint/not-found Run 404; limit 413;
unavailable standalone/read state 503 where applicable. Existing Access and
storage errors propagate with their established boundaries. A failed or revoked
request clears the renderer, cancel obsolete requests, and exclude
late replies. Already returned bytes cannot be recalled.

The renderer consumes an immutable base spec/result and transient allowlisted
selections. Persisted revisioned display overrides remain a later milestone.
Changed analysis creates a new result;
series/color/range/display filters cannot silently redefine metric meaning.
No renderer or spec is accepted merely because it is JSON.


Qualification: 27 query/contract/actual PostgreSQL/authenticated HTTP tests pass
without skips; the actual Runs browser uses the normal app, retained native Run,
real session revocations and a fresh application process. See
[acceptance evidence](../plans/retained-analysis/reports/m4-integrated/acceptance.md).
The two-epoch six-image fixture proves custody, transport and numeric behavior;
it makes no model-quality or production-scale claim.
