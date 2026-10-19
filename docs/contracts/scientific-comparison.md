# Exact scientific evidence comparison

`runs.compare_scientific_evidence/1` is a read-only, separately negotiated
operation at `POST /api/workspace/scientific-comparison`. Existing
`runs.compare_model_evidence/1,/2` and recovered comparison contracts retain their
identities and closed outputs. Selection never admits or starts compute.

The request contains exactly two ordered `operands` (baseline, candidate), an
exact scalar `selection`, and `point: {field_id,x,y,z}`. A completed operand is
`{kind:completed_run,catalog_id,run_id}`. A recovered operand is
`{kind:publication_result,ref}` with the complete attached publication-result Ref.
Both forms may be mixed. Stopped Runs cannot use the completed operand form.
The operation does not promote their outcome or establish candidate eligibility.

The scalar selection retains the existing exact checkpoint/evaluation/metric
selection grammar: checkpoint/evaluation/metric-definition SHA256 values for
both sides, `metric_id`, and `mode` (`paired` or `side_by_side`). The evaluation
identity is the retained `model-evidence.json` artifact hash. Frozen case
correspondence uses the entire declared frozen-reference value, independent of
array ordering and probe ordinals. Both per-side ordinals remain explicit.
No filename, cohort label or array shape establishes correspondence.

Runs and publication-result readers revalidate each operand's actual material,
current inspect authority, transitive inputs, inventory and retained payloads.
`extension_evidence.compare` owns scalar and authoritative field policy checks;
the new owner also requires exact evaluation-data, profile, split and case
selection-policy identities. Task, normalization/preprocessing, output, metric
population/units/direction/evaluator, frozen membership/target, geometry and
gauge mismatches suppress all paired deltas and preserve precise reasons.
No unit conversion, normalization fitting, checkpoint inference or holdout read
is supported. Missing cases are a union of exact identities with explicit
`case_not_retained`; absent selected fields use `field_not_retained`.

The bounded current profile retains scalar observations and fixed validation
field arrays. Its per-case output is the original prediction and reference at
the exact declared field point, plus a candidate-minus-baseline **prediction
point diagnostic** when compatible and paired. This subtraction is not a
reference error operator, regression judgment or physical acceptance rule.
Out-of-bounds coordinates, unknown selectors and ambiguous identities refuse.
Non-finite deltas refuse rather than entering JSON.

The profile has no per-case metric or owned criterion Ref. `criterion` and each
case's `acceptance` therefore return `unknown` with their explicit reason. An
Experiment target is authored intent and cannot supply scientific authority.
Qualified per-case pass/fail, diagnostic-versus-qualified criterion selection,
and lab-specific scientific improvement remain unsupported until an admitted
producer/profile contract retains that authority. No threshold is invented.

`operands` in the response bind exact Model/material and finite Study/Trial
references, original outcome, retained model configuration, owner phase timings,
artifact identities and managed-Run custody. Checkpoint clocks are retained
coordinates; absent epoch/fit-pass/time remains null. The current profile retains
no memory measurements, so memory is explicitly unknown. Owner timing records
keep their scope and missing granularity; they are not summed or substituted
for checkpoint wall clocks. External Project activity remains external activity.

The existing Runs page selects exact baseline/candidate/checkpoints and renders
all cases and scalar clocks as keyboard-accessible tables, including at narrow
widths. It clears old values while reads are pending, validates response identity,
fences overlapping reads/session changes and clears on authority failure.
Immutable lineage remains owned by Experiment progression; comparison does not
write relationships or reinterpret target intent as acceptance.

`tests/test_scientific_comparison.py`, `tests/scientific_comparison_fixture.py`
and `tests/browser_scientific_comparison.cjs` describe the verification boundary.
Tiny-runtime fixtures use the actual metadata/material/grant/Study admission
owners, then explicitly author synthetic terminal arrays/receipts without
launching a producer. Production cold context, inventory, publication-result,
array, authorization and HTTP readers remain unchanged. These fixtures establish
contract and UI behavior, not runtime execution, process custody, training,
physical correctness or the lab's unavailable scientific acceptance pair.
