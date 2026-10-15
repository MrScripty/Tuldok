# Extension contribution and material design

This report specifies the selected detailed design for the [canonical plan](../plan.md).
It is a proposed implementation contract to freeze against actual consumers in E1,
not an implemented ABI. The plan owns authority, sequencing and acceptance.

## Contribution And Manifest Contract To Freeze In E1

The proposed format discriminator is `tuldok_extension_v1`. The manifest names
package ID/version, license/notice references, exact source/definition inventory,
required locally known host contract IDs/versions, runtime/profile requirements,
requested effects/resources, contributions and declarative view descriptors.
References carry relative path plus expected SHA-256; qualified runtime identities
remain separate. Entrypoints are data until selected exact material is admitted.

Use strict UTF-8/JSON, duplicate-key/nonfinite/surrogate rejection and existing
Projects no-follow, descriptor-relative root access. Start with the current
64 KiB manifest bound and 64 reference ceiling, at most 64 contributions per
package, bounded nesting 16 and finite stage lists at most 16. These are proposed
parser/authoring ceilings owned by the extension contract, not performance claims.
E1 must check aggregate catalog cost, encode count/byte bounds at each referenced
definition, and retain existing source/capture limits. Reject recursive/cyclic or
remote schema references and active text/HTML. Parameter schemas use a documented
closed subset of the existing Draft 2020-12 validator, not executable validators,
coercion or a new home-grown schema engine. E1 documents every supported keyword
and rejects unsupported keywords instead of partially interpreting them. Canonical
data-only schemas live in `extension_schemas/extension-v1.json`,
`contribution-v1.json` and `parameter-v1.json`. The host's extension decoder adds
owned cross-reference/bound/provenance checks; SDK schemas are exact source-captured
copies verified by content identity and shared corpus. Existing optional
jsonschema4.26.0/locked transitives are explicitly provisioned for validation,
never on open/startup. Missing validator returns unavailable rather than a partial
proof; ordinary inert inspection still shows the reason.

Contributions have namespaced IDs and exact semantic versions/content identities.
One package may supply several kinds, but no kind receives an application object:

| Kind | Owns | May reference / must not own |
| --- | --- | --- |
| Task | Input/target/output meaning, units/axes/clocks, permitted metric/comparison definitions | Frozen datasets and evaluator; no review/admission/physical-validity authority |
| Reader/derivation | Exact format-to-task mapping and declared transforms | Captured input/output artifacts; executes as an ordinary Run, never on open |
| Model | Typed computation options, source/import closure, preprocessing/reconstruction/output policy | Task; weights/fitted statistics stay Run outputs, trainer controls stay Pipeline |
| Trainer | Closed training parameters, compatible tuples, finite stages and capture obligations | Model/runtime/evaluator; no queues, hidden installs or grant consumption |
| Evaluator | Named metric/reduction/direction/tolerance, stage/population compatibility and numerical acceptance meaning | Exact retained weights/probes/fields; no claim that byte integrity establishes quality |
| View descriptor | Bounded host-known controls, query selectors, labels and primitive renderer bindings | Evidence; no code/DOM/database/filesystem bridge or execution on inspection |

Declarative model validation checks structure and known cross-reference/shape
constraints without running model code. Code-dependent compatibility not provable
statically stays unavailable until a separately admitted smoke/qualification Run.
Unknown semantic types may remain opaque verified artifacts; discovery cannot
make them renderable, comparable or numerically accepted.

The catalog is a bounded in-memory projection of selected immutable project
snapshots. Opening a new project v2 snapshot enables exactly its listed packages;
changing enablement creates a new snapshot ID. Switching to one without a package
is context-local disablement, not revocation of independently addressable old
snapshots/grants/continuations. No installation-wide kill switch is selected.
No editable package catalog or
global registry is persisted. Duplicate contribution identities with conflicting
content are invalid; a disabled/malformed extension does not remove unrelated
valid entries. Required invalid dependencies make only dependent contributions
unavailable. There is no install-order or provider-order fallback.

Show independent facets: discovered/valid/enabled, compatible host contracts,
runtime qualification and current permission. `Available` never means admitted.
An attempt's queued/running/terminal state belongs only to Runs.

## Material, Versions And Stage Rules

The resolved extension binding is part of PR62's model/recipe material, not a
second editable recipe. It pins original manifest/definition bytes and hashes,
chosen contribution contracts, code/import closure, all resolved defaults,
input/release/probe references, model config, training parameters, exact stage
sequence, evaluator/transform policy, runtime, limits and reviewed effects.
Compilation to the supported external recipe execution shape is deterministic
and inert. Any generated execution-config file is captured and hashed like other
material; no mutable filesystem lookup or late plugin default supplies meaning.

Preserve independent version roles:

- Project/manifest versions discriminate readable formats.
- Contribution/task/model/evaluator contracts govern semantic compatibility.
- Package/source/runtime hashes identify exact content and closure.
- Operation contract IDs/digests govern actual HTTP/CLI/MCP consumer overlap.
- Metadata schema version governs only admitted persistence migration.
- Editable revisions provide CAS/freshness, not compatibility or execution rights.

Changing executable code, ports, stage order, units/gauge/tokenizer/class order,
normalization, parameters, profile/defaults, runtime or inputs requires new exact
material and current preflight/approval. A package label alone does not prove
compatibility. Name/layout edits remain presentation-only under Pipeline's rules;
saved-revision freshness still applies. No selected provider follows `latest`.

Each stage names its exact ID/version, inputs/outputs, applicable clock and failure
policy. Its outputs bind producing stage and input lineage. One admitted worker
may execute prepare → fit → infer → evaluate inside one reviewed envelope. A stage
needing another runtime, permission, input closure or resource envelope becomes a
separately prepared/admitted Run; no child-attempt callbacks or implicit admission.
The first UI offers finite trainer-qualified options and read-only stage order.

## Model, Evidence And Multimodal Meaning

Reuse PR62 model/evidence ownership and envelope, never build a parallel plugin
results system. Checkpoints bind actual retained weights, model, fitted-transform
identity and producing clock; identical weight bytes at different clocks are
different checkpoint descriptors. Retain required observations automatically for
a qualified trainer. Omitted optional evidence has a typed reason; missing/failed/
not-applicable/undefined/skipped are not zero. One-fit tasks keep actual fit-pass
clocks; physical time and optimizer progress remain distinct.

Port descriptors bind an exact semantic contract and artifact/encoding identity,
plus declared shape/dtype/axes, coordinate/time and mask/validity information where
applicable. Structural schema agreement alone does not prove semantic compatibility.
First compatibility uses exact supported intersections, without inferred conversions.
Explicit derivations create separately captured provenance and admission as needed.

- Image keeps color/channel/alpha/range and transform identity.
- Text keeps raw/token distinction, tokenizer/vocabulary, normalization, masks,
  sequence boundaries, truncation and offset convention.
- Audio keeps sample rate/channels/amplitude/timebase and any explicit resampling.
- Mesh/points keep topology or stable IDs where relevant, attachment domain,
  coordinate frame/units and transforms.
- Fields keep grid/centering/axis order/units/mask/boundary/stage/gauge/time meaning.

Reuse only scalar curves, tables/classifier rows and scientific orthogonal slices
qualified in the actual implementation baseline or accepted PR62 P3/P4. Their
design files alone do not establish availability. Extension declarations select
primitives only for acknowledged representations. Unknown formats show a truthful
metadata/download fallback under current authority. No checkpoint deserialization
or custom semantic code runs in the application or browser to draw a view.
Evaluators execute under an admitted operation and emit bounded data-only evidence;
the host checks structure, exact provenance/cross-file binding and allowed scope.
Numerical claims still require the evaluator's qualification/oracle, not its label.

All paired comparisons pin both checkpoints, exact metric/reduction and compatible
population/targets/transforms/stage/grid/mask/units/gauge/time as applicable.
Return incompatible with bounded reason and labeled side-by-side values otherwise.
Run completion, evidence integrity, numerical acceptance and candidate selection
remain separate. A physical-quality test may fail while inference reconstructs.
