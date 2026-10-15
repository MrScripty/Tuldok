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

## Disjoint source and model output purposes

The new canonical mode also assigns finite recipe output roles. Native source
NPYs use `field_source`; model predictions use `field_prediction`; checkpoint
JSON uses `model_checkpoint`; opaque weights/transform state use `model_state`;
the separate exact derivation uses `field_derivation`. Existing common JSON
keeps `model_evidence` and the context keeps `model_context`. These are required
purpose declarations only for this explicit new input mode; old recipes keep
their original roles and bytes.

The complete derivation native names must equal the recipe's source-role names.
Policy prediction/reference/probe bindings must agree with their roles, and no
source can become a prediction by renaming/re-hashing the receipt. After the
normal decoder has verified the closed authoritative payload inventory, the
helper additionally checks checkpoint descriptor/state and transform-state
references against their declared distinct roles. No source-native proof can
also serve opaque model state, checkpoint JSON or common evidence. This uses
policy/recipe roles and generic D2 references, with no A filename convention.

The shared schema3 `field_targets` repair is independently owned by p2. A
canonical common-policy parser must preserve that explicit bound-only key while
checking the additional canonical declaration; never project it away to force
old authored grammar. Its composite target identity must remain distinct from
the old schema2 direct payload identity. The canonical author compiler will
align to the accepted schema3 map before new material capture.
