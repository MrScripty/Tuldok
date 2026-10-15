# Native field probe identities

This is the author contract for the implemented field-evidence decoder. It is
data identity, not numerical or physical acceptance. Validate native dtype,
shape, C order, finite values, geometry, stage and gauge before using its bytes.
The SDK's `digest` uses the host's UTF-8 canonical JSON with sorted keys, compact
separators and unescaped Unicode. `payload_sha256` hashes native scalar payload
bytes **without the NPY header**. Artifact Blobs separately hash the complete NPY
file. These hashes have different meanings and cannot be substituted.

For each frozen validation member, `input_sha256` is the digest of an ordered
list of objects with exactly `field_id` and `payload_sha256`. Its order is
`model_evidence.fields[0].contract.inputs`. Every required Task input, including
a source field or boundary mask, must be represented in that contract and its
matching `probe_inputs` artifact inventory. All declared output fields use that
same explicit input contract and geometry.

```python
from hashlib import sha256
from tuldok_extension_sdk.evidence import digest

# These are validated native scalar bytes, not the complete NPY files.
input_identities = [
    {"field_id": "initial", "payload_sha256": sha256(initial_payload).hexdigest()},
    {"field_id": "source", "payload_sha256": sha256(source_payload).hexdigest()},
    {"field_id": "boundary_mask", "payload_sha256": sha256(mask_payload).hexdigest()},
]
candidate_input_sha256 = digest(input_identities)
```

The explicit bound recipe (`schema_version: 3`,
`format: external_model_evidence_recipe_v2`) requires
`model_evidence.field_targets`. Its rows have exactly `member_id`, `field_id` and
`payload_sha256`, ordered first by authored `probe.candidates`, then by declared
`fields`. `member_id` is the candidate's `frozen_reference.member_id`; `field_id`
is the declared output field's `id`. There must be exactly one row per pair.
Missing, extra, repeated, unknown or reordered rows are refused before admission.

For each candidate, `target_sha256` is the digest of its ordered field identities,
even when only one field exists. A raw and a corrected reference may therefore
have different payload hashes while belonging to the same fixed probe.

```python
target_identities = [
    {"field_id": "raw", "payload_sha256": sha256(raw_reference_payload).hexdigest()},
    {"field_id": "corrected", "payload_sha256": sha256(corrected_reference_payload).hexdigest()},
]
candidate_target_sha256 = digest(target_identities)
field_targets = [dict(member_id="validation-case", **item)
                 for item in target_identities]
```

Place these exact candidate identities in `probe.candidates`, and place the
complete ordered `field_targets` list in the policy. For every checkpoint,
`field_outputs` separately maps `(clock, field_id, member_id)` to the declared
prediction and reference artifact names. Each field's actual reference payload
must match its own `field_targets` row. Its stage, grid, units and gauge must
also match the exact declared field contract. An aggregate target hash cannot
authorize swapping raw/corrected references or relabeling their stages.

The adapter identity is the digest of the **complete declared recipe source
inventory**, sorted by `path`. Use each exact `{path, sha256}` entry from
`recipe.sources`; do not add file sizes, the recipe itself, or the automatic
Model binding inventory. This same closure digest is required in
`model_evidence.adapter_sha256`, every field contract's `source_sha256`, and
every metric's `evaluator_sha256`. Hashing only the numerical producer does not
identify the captured evaluator/source closure. Keep the recipe outside its own
source inventory to avoid a self-hash cycle.

```python
adapter_sha256 = digest(sorted(recipe["sources"], key=lambda item: item["path"]))
```

The SDK writer emits field groups in checkpoint order, then policy `fields`
order; each group's cases follow the resolved probe members. The field's exact
contract and `field_outputs` binding identify each group. Do not add an
undeclared top-level `field_id` to the closed field-index format.

Historical authored recipes (`schema_version: 2`,
`format: external_model_evidence_recipe_v1`) retain their original direct
reference-payload `target_sha256` and reject the new `field_targets` key. Their
old source, Task, Model, material and grants are never reinterpreted as a bound
multi-target recipe. New source/port/stage/target meaning requires new exact
declarations, publication, material review and grant.

These rules describe the common identity envelope. Normal admission, captured
runtime, current authority, custody and independent numerical evaluation remain
separate requirements. A local hash or SDK validation is not an executed Run.
