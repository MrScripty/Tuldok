# Scalar A inference-only contract v1

This is a separate private QA adapter version, frozen before any qualified fresh
consumer Run. It does not modify the five-source A training closure, task or
recipe. The source authority is `057c8abf571d62331486dc56ef43064e72f9d03a`:
`example.scalar-a:task` revision **2** and
`example.scalar-a.fixed-validation` profile revision **2**. Exact authority and
policy hashes are recorded in `contract.json`.

The only formula is the published model's retained-state reconstruction:

```text
prediction = scale * ((initial - train_mean) / train_population_std) + offset
```

No training step, fitting, analytic training trajectory, target equation, MSE,
quality threshold or physical acceptance operator is implemented. The independent
oracle remains outside this source closure and is neither imported nor copied.

## Interface

`infer.py` imports only the ten standard-library modules explicitly listed in the
contract. The complete executable source closure is `infer.py`; its complete
adapter notice is `NOTICE.txt`. `contract.json` pins their exact bytes/hashes and
does not contain a hash of itself. A package owner must pin the whole contract
separately. Neither this adapter nor its contract replaces the original captured
model/source/notices, selected checkpoint, fitted-transform or package owners.

```python
predict(initial_npy: bytes, weights_npy: bytes,
        transform_npy: bytes, request: dict) -> bytes
```

The function reads no files and returns a native NPY v1 prediction. All input
arrays must be finite, non-pickled, little-endian float64, C-order NPY v1 or v2:

| Input | Shape/order | Meaning |
| --- | --- | --- |
| `initial_npy` | `[4,4,4]`, ZYX | One permitted `initial` probe field |
| `weights_npy` | `[2]` | `[scale,offset]` from the selected checkpoint |
| `transform_npy` | `[2]` | `[train_mean,train_population_std]`; std must be positive |
| Returned bytes | `[4,4,4]`, ZYX | `prediction`, native float64 C-order NPY v1 |

`request` is a closed data-only object:

```json
{
  "format": "scalar_affine_inference_request_v1",
  "policy": "REPLACE WITH THE EXACT contract.json policy OBJECT",
  "sha256": {
    "initial": "SHA256 OF THE EXACT INITIAL NPY FILE BYTES",
    "weights": "SHA256 OF THE EXACT SELECTED WEIGHTS NPY FILE BYTES",
    "transform": "SHA256 OF THE EXACT FITTED TRANSFORM NPY FILE BYTES"
  }
}
```

The strings above illustrate required bindings; they are not valid requests. No
role/hash may be omitted. The policy is fixed to dimensionless cell fields on a
4³ grid, metre coordinates, zero origin, unit spacing, identity orientation and
identity gauge. It binds input stage `input`, output stage `post_train_mapping`,
the source-owned `raw` field contract's output `prediction`, train-only population
standardization and exact task/profile definitions. Changes require another
adapter contract version, without interpreting older material as the new policy.

The CLI is exact, writes an absent output exclusively and never overwrites:

```sh
python -I -S -B infer.py --contract contract.json --request request.json \
  --input input-initial.npy --weights weights-selected.npy \
  --transform transform.npy --output prediction.npy
```

Success exits 0 and reports `{state:"written",bytes,sha256}` on stdout. Invalid or
unavailable input/state/contract/output exits 2 with bounded `{state:"invalid",
reason}` on stderr. Source/notice checks and declared CPython 3.12 compatibility
run before CLI inference. The pure function also rejects another runtime version.
No site packages, runtime installation, training fixture, provider, cache or
ambient project directory is used. Input files must be bounded, stable,
single-link regular files; symlinks and special files are refused.

## Caller and package ownership

P5 must derive request hashes from an already authorized immutable selection:

1. Verify the selected **checkpoint descriptor SHA**, independently of its weight
   hash. Bind `weights` to the descriptor's exact weights Blob.
2. Follow its fitted-transform SHA to the exact `fitted-transform.json` and bind
   `transform` to that document's `state` Blob. Preserve training member lineage.
3. Bind `initial` to the exact permitted input NPY artifact, after its native
   field payload has been checked against the admitted probe. A D2
   `probe.input_sha256` is a field-payload identity and is **not** the raw NPY file
   hash required by this request.
4. Retain current transitive permissions, source/notices, exact policy/contract
   and explicitly selected compatible runtime. CPython version checking here is
   not captured-runtime authorization or custody qualification.

The request cannot authenticate itself. Replacing both bytes and caller-supplied
hashes would describe another input/state; the package owner must bind them to its
verified selection. This adapter deliberately does not duplicate host admission,
checkpoint selection, authority or source-family derivation.

The independent frozen oracle SHA is
`ccfbe3bc92badf265ea882382d392e05daca091f5694f528f268ec3d6e38764b`.
Its pre-existing acceptance rule for finite reconstructed probe values is
`abs(actual-expected) <= 1e-10 + 1e-10*abs(expected)`. Compare decoded array values;
independent valid NPY encoders can produce different header bytes. This tolerance
is a fixed reconstruction diagnostic and grants no model-quality or physics pass.

## Authored checks and remaining gates

`PYTHONPATH=tests python -m unittest test_extension_inference_contract -v` covers
an independently authored exact affine case, isolated CLI consumption, missing or
wrong bound state, dtype/order/shape/gauge/geometry/stage/profile changes,
nonfinite arithmetic, runtime mismatch, links and exclusive output behavior.
These synthetic contract/unit inputs are not producer checkpoints or fabricated
completed Runs. Actual producer-state comparison and separately admitted fresh
package consumption remain pending worker artifacts and P5 integration.

The original authored Project fixture is not a canonical Release or a global
family/split derivation proof. This module supplies no such proof. Rights remain
private QA only; complete runtime and training-package notices/redistribution
rights remain separately owned.
