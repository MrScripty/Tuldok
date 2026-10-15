# Independent author B: source and boundary enforcement

This separate package owns only this directory. The existing A package and the
other author's `field-surrogate-b/v1` are untouched. No application-owner Python
or JavaScript, database, RuntimeSnapshots or Access source was read or edited.
Permitted inputs were the public SDK, schemas, extension/model contracts,
acceptance procedure and frozen A author example. A's policy envelope was adapted
into a new B identity; the numerical implementation and stdlib oracle are new.

`initial`, `source` and binary `boundary_mask` are required. The raw reference is
`0.5 * initial + 0.25 + 0.2 * source`; boundary value `1` enforces zero and value
`0` preserves the raw model value. Raw and corrected targets and errors are
separate. The dimensionless 4³ fields are `<f8`, C-order ZYX, cell centered on a
unit grid in meters. These standalone cases have no physical timeline or solver
qualification.

The model fits three affine weights from two independently standardized features
and a bias, using full-batch gradient descent from zero for exactly 64 updates.
Both means and population standard deviations use only `train-0` and `train-1`.
The transform is retained as a `(2,2)` NPY: means row then standard-deviations row,
feature order initial/source. Checkpoints are captured at actual updates 32/64;
weights use `(initial_scale, source_scale, offset)` order. Raw inference produces
`raw`; mandatory `boundary_enforcement` consumes `raw` and the mask to produce
`corrected`. Task and Trainer declare the same ordered stages. No A weights or
implicit adaptation are accepted.

`recipe.json` is explicit schema3 / `external_model_evidence_recipe_v2`. Its five
contribution selectors pin exact IDs, versions and bytes; the Project SHA is not
embedded in the recipe. The separate v2 Project pins the recipe and extension.
Source capture includes the exact SDK `tuldok_extension_sdk/__init__.py` and
`evidence.py`, imported by the producer, together with author source, declarations
and notice. Provider and recipe both select already prepared CPU runtime
`50502c0ba923f3134073188efd55c20b0468c008b1bdfbdc87fd72ea830ffe3d`, with no runtime
fallback. There are 26 declared outputs, within the current 32-output envelope.
Architecture and preprocessing/output policies are author exact. Only declared
configuration schema/defaults may be edited in the model workflow.

The SDK writes field groups in checkpoint order, then `policy.fields` order
(raw, corrected). Exact policy contracts, output bindings and artifact identities
bind these groups; no extra undeclared SDK field keys are introduced. Each field
contract and `probe_inputs` covers all three required Task inputs.

## Local verification, not actual Runs

```sh
python -m tuldok_extension_sdk validate examples/extensions/field-surrogate-b-independent/v1
python -m unittest discover -s examples/extensions/field-surrogate-b-independent/v1 -p test_author_numerics.py -v
```

These prove inert declaration validity and local numerical behavior. Seven tests
compare NumPy updates/replay with independent stdlib equations, demonstrate
train-only fitting and explicit boundary enforcement, reject missing/nonbinary
inputs and malformed native arrays, and check exact source closure/dataflow.
No host/context fabrication or local producer-main fallback supplies an actual
Run. Importing numerical functions for these local tests is not SDK execution
conformance.

`cold_oracle.py` imports only stdlib. `oracle-freeze.json` pins its exact source
and fixture before any actual Run. It independently computes training statistics
and the gradient recurrence, parses bounded raw NPY arrays, reconstructs both
stages from retained weights/transforms/inputs, and retallies both reference-target
errors. Reconstruction uses `abs(actual-expected) <= 1e-10 + 1e-10*abs(expected)`.
Reference quality remains a separately named diagnostic. The exact expected
canonical context SHA must come independently from retained custody, not the
artifact being tested.

```sh
python cold_oracle.py --fixture fixture.json --artifacts DOWNLOADED_ARTIFACTS \
  --expected-context-sha256 INDEPENDENT_EXPECTED_SHA --report ABSENT_REPORT.json
```

The exact native identity rules follow
`docs/contracts/extension-field-identities.md`, first published at `647cf2f`
and corrected with the reviewed SDK UTF-8 canonicalization change `8e70f1e`.
Candidate input identities hash ordered input field IDs and SHA256s of native
little-endian float64 payloads, excluding NPY headers. The policy contains exact
`field_targets` rows in candidate then field order, and candidate target identity
hashes the ordered raw/corrected field payload identities. Raw and corrected
reference payload hashes are distinct. The recipe's exact hashes and Project
reference have been updated; frozen producer/oracle/fixture bytes are unchanged.

Actual execution is pending the main owner's frozen public server/selection
harness and canonical A owner glue. The main owner
must prepare the finite Study normally, review the complete composition, grant
that exact material and provide the public CLI/agent fixture. SDK conformance
must then admit only that selected trial, download all retained artifacts and
pass the independent cold oracle. No actual Run or E3 acceptance is claimed here.

The own-package SDK evidence helper was recaptured from reviewed `8e70f1e`:
canonical JSON emits UTF-8 with unescaped Unicode. ASCII probe identities stay
unchanged. Its new exact source hash changes provider/recipe/Project identities;
producer-only adapter/evaluator/field-source hashes remain the frozen producer
SHA. Mathematical source, oracle and fixture remain unchanged. This unadmitted
package has no prior material or grant to reuse.

Exact author/source hashes, commands, constraints and pending evidence are in
`author-report.json`. Private local QA rights do not imply redistribution rights.
