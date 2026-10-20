# Indexed diagnostics v1

`extension_field_policy_indexed_v1` is an explicit opt-in policy variant for the
existing noncanonical `external_model_evidence_recipe_v1` and bound
`external_model_evidence_recipe_v2` recipe families. It adds one required
`diagnostic_capture` member. Canonical field policies are outside this variant.
Legacy policies remain closed and cannot gain this member. An arbitrary legacy
artifact named `diagnostics.json` or using a diagnostic role gains no index
semantics.

The existing `model_evidence_v1` envelope, profile capability lists, profile Ref
meaning and public evidence projections are unchanged. The complete admitted
policy and recipe/material/context bind the addon; its `capture_sha256` is the
canonical hash of `diagnostic_capture`. A profile Ref alone does not identify
the addon. Only opted-in execution material adds the shared SDK contract modules
to its recorded host closure. Retained legacy host-name sets remain unchanged.

## Declaration and admission

`diagnostic_capture` is closed over these fields:

| Field | Contract |
| --- | --- |
| `format` | `diagnostic_capture_v1` |
| `payload_schema` | `diagnostic_json_object_v1`: bounded finite JSON object, with no inferred numerical meaning |
| `index` | `{name, max_bytes}` matching a required declared output with role `diagnostic_index_v1` |
| `shards` | Ordered, unique `{name, max_bytes}` entries matching optional declared outputs with role `diagnostic_shard_v1` |
| `phases` | Unique flat names, at most the selected recipe's output count |
| `coverage` | Ordered scopes `{case_id, checkpoint_point, phase, required_count, optional_count}` |
| `records_per_shard` | Positive exact integer; each shard must fit that many maximum-size records plus its JSON envelope |
| `max_record_bytes` | Maximum canonical UTF-8 bytes of one complete record |

Case IDs must belong to the fixed admitted validation probe. Checkpoint points
must belong to the complete admitted capture cadence. Phases refer to the
explicit declared phase list. Scopes sort by admitted probe order, checkpoint
point, then declared phase order, without repeated scopes. Within each scope,
required records precede optional records. Contiguous global ordinals identify
the complete declared population.

The population must fit `len(shards) × records_per_shard`. Shards retain the
existing selected per-file ceiling, at most 8 MiB. The recipe's existing output
file-count and aggregate caps remain authoritative. This opt-in variant reserves
the sum of **all declared output maxima** inside the profile aggregate budget;
legacy policies keep their existing aggregate semantics. Admission also reserves
an index large enough for all shard descriptors and uncompressed optional
omission ranges. Impossible record identity, shard, index, population or aggregate
reservations refuse before execution admission and grant consumption. Scientific
array minimum-size checks still apply independently.

Diagnostic names must be distinct from all common scientific documents and
bound probe/prediction/reference files. They cannot replace scientific evidence.

## SDK producer

Use the supported `tuldok_extension_sdk.evidence.Evidence` writer to finish the
complete scientific envelope, then call `writer.diagnostics(records, omitted)`.
The writer checks the full record population, all ranges and serialized byte
bounds before writing diagnostics. It never samples or truncates required data.
`writer.inventory()` includes the exact bytes it wrote; this is construction
metadata, not collection permission.

Each record is closed over `{ordinal, case_id, checkpoint_point,
checkpoint_sha256, phase, payload}`. Its checkpoint SHA-256 must equal the actual
retained checkpoint descriptor at that admitted point. `payload` is a finite
JSON object under the existing SDK JSON depth/node/string bounds. Its content
does not establish a metric, physical operator or acceptance criterion.

`omitted` is an explicit sorted nonoverlapping list of `{start, count, reason}`
ranges. Each range stays inside one scope's optional population. Reasons are
`capture_budget`, `not_available` or `not_requested`. Required ordinals cannot be
omitted. Every remaining ordinal must occur exactly once, in order.

## Retained index and shards

The index is `application/json`, schema `diagnostic_index_v1`, closed over
`{format, payload_schema, run_id, material_sha256, capture_sha256, shards,
total_shard_bytes, coverage}`. It binds the current Run and exact composition
material. Each ordered shard entry is `{blob, record_count, first_ordinal,
last_ordinal}`. `blob` is `{name, bytes, sha256, media_type}` with media type
`application/json`. Shards are consumed in the declaration's order; all except
the final retained shard contain exactly `records_per_shard` records. Unused
declared optional shard files must be absent.

Each shard is closed over `{format, run_id, capture_sha256, records}` with format
`diagnostic_shard_v1`. Every file has its exact size/hash, record count and ordinal
range checked. `total_shard_bytes` equals the sum of retained shard sizes.
Coverage is closed over `{total_count, required_count, optional_count,
retained_required_count, retained_optional_count, omitted_count, omitted}`;
counts must agree with the admitted population, retained records and omissions.
Complete mandatory coverage and omitted optional detail remain distinct.

Runs' existing outer artifact inventory retains its generic
`application/octet-stream` transport media type. The addon specifies JSON's
semantic media type within that unchanged byte transport.

## Host verification and publication

The existing evidence owner first verifies the complete scientific envelope and
all current artifact bytes against Runs' retained inventory. Only then does the
shared diagnostic contract verify those already retained bytes. The proof is
private `_diagnostics`; existing query/publication evidence projections strip
private members and retain their closed public grammar.

Publication continuation, custody, permission, accounting, recovery and result
Refs remain owned by Runs. Consumers inspect or collect the declared index and
its named shards through the existing exact inventory and whole-hash artifact
readers. No arbitrary path, glob, alternate store or new export authority exists.
Recovery reruns the same host verifier. An invalid original scientific output
still fails; an index cannot repair it or confer numerical acceptance.

Focused executable witnesses are `tests/test_indexed_diagnostics.py` and
`tests/test_indexed_diagnostics_publication.py`. The latter explicitly uses a
tiny `/usr/bin/true` metadata runtime and harness serialization before the
actual no-op child. It qualifies real custody, interrupted-copy recovery, exact
readers and unchanged accounting; it proves no captured Python producer,
training, CUDA, numerical or lab-failure classification result.
