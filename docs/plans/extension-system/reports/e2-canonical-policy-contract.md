# Explicit canonical policy handoff

`extension_canonical.py` is a pure, currently inactive helper for the explicit
`extension_field_policy_v2` successor. It does not reinterpret authored policy
v1 or enable discovery execution. Shared schema3 catalog capture and admission
integration remain owned by the product lead/p2 owner.

The additional `canonical` object has exactly:

- `format: canonical_field_inputs_v1`;
- `release: {input, sha256}` selecting one actual frozen Release;
- `derivation: {input, sha256, output}` selecting the exact captured lossless
  receipt and its separate required retained output with unique role
  `field_derivation`;
- `provenance: {input, sha256}` selecting the exact author compilation policy;
- `contract`, the existing `field_adapter_contract_v1` source contract;
- ordered `members: [{case_id, record_id, revision, source_revision, split}]`;
- explicit `mapping: {inputs: [{source_field_id, model_field_id}],
  target: {source_field_id}}`.

The fit/probe references keep their existing closed keys, but their `input` and
`sha256` identify this actual Release; `member_id` identifies the exact case
mapped to the canonical record/revisions above. The frozen validation probe's
`data_sha256` is the Release SHA, never the old authored fixture SHA. Source
reference-target semantics and model prediction-stage semantics remain distinct;
all native dtype/shape/centering/units/gauge and source geometry must agree.
Test populations remain unsupported.

Serial integration must call `validate_declaration(canonical, policy, recipe)`
within complete policy validation. Before any input provider/runtime capture,
call `validate_bindings(canonical, graph_inputs)`: only the named Release binding
may have `kind: frozen_release`; every other kind-tagged input, including unused
ones, refuses. Existing project input ownership checks remain authoritative.
After normal capture and before runtime/grant/Run work, call
`validate_captured(canonical, policy, recipe, execution_material, captured)` with
exact immutable `input/<name>` bytes. It validates actual scientific ZIP custody,
complete ordered record revisions/splits, all frames/families/protected groups,
native hashes, complete P4 lossless derivation and exact validation artifact
bindings. Source-specific compilation correctness belongs to the captured author
compiler and independent consumer; the host binds its exact provenance bytes.

Publication and every cold query/access must repeat that function with the
rederived immutable captured inputs plus `outputs=decoder_payloads`, the same
closed byte inventory already checked against authoritative Run artifact hashes.
The exact admitted derivation must be retained, every source native output must
be byte-identical, and native/derivation output names must be disjoint. Known
proof bytes must fit required individual and aggregate output limits before
execution. Preserve all existing Project/catalog/current-access checks and
upstream hash verification. No worker output, mutable provider or caller may
replace the captured input bytes.

The helper has not yet been wired into shared recipe/Model/Pipeline/Runs owners.
Its PostgreSQL tests use actual new import/review/freeze owners and leave zero
producer Run rows. This is source/identity contract evidence, not canonical E2
execution, SDK admission, physical quality or full product acceptance.
