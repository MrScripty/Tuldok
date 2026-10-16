# Six inert modality descriptor fixtures

These tiny image, text, audio, mesh, point and volume examples exercise the
canonical extension declaration/catalog and SDK manifest seams. Each has a Task
descriptor with bounded example values in `parameters`/`defaults`, an inventoried
Reader source sentinel, and a `metadata` View declaration. The current schema is
unchanged. There are no trainers, numerical adapters, actual Runs or catalog writes.

| Family | Explicit descriptor assumptions |
| --- | --- |
| Image | 2×2 RGB integer code values, HWC axes and channel order |
| Text | Ragged token lists, exact tokenizer digest and ordered class vocabulary; no padding |
| Audio | Mono amplitudes, 16,000 Hz and sample-index clock; no resampling |
| Mesh | Bounded indexed triangles, explicit vertex/face ports, right-handed lab frame and meters |
| Points | Ragged point records and explicit offsets, left-handed sensor frame and millimeters |
| Volume | Bounded dense cell values, C-order ZYX, standalone world frame and unit spacing in meters |

`corpus.json` freezes every fixture file SHA256, the exact Task ID/version/hash,
the raw configuration SHA256 and its canonical JSON digest. `config.json` is an
opaque source-inventory file; the fixture check separately confirms that its
value equals the Task's explicit defaults. The declaration validator checks
those defaults against the authored closed parameter schema. It does not parse
standalone source files as configuration or invent a new payload decoder.

All manifest/source/definition paths are relative to this corpus root, including
when selecting a manifest in a modality subdirectory. For example:

```sh
python -m tuldok_extension_sdk validate tests/fixtures/extensions/modalities \
  --manifest text/extension.json
python -m unittest discover -s tests -p test_extension_modalities.py -v
```

Provision `requirements-extensions.lock` separately. The dedicated SDK CI job
runs these tests with its installed validator. Each Reader source deliberately
writes `EXECUTED` and raises if imported; validation tests forbid its import,
application/numerical imports and `Popen`, and verify the entire fixture tree is
unchanged. No fixture source is executed to obtain the expected result.

The focused tests compare complete canonical and SDK catalog projections, reject
malformed/duplicate/nonfinite declarations, closed-object additions, wrong payload
types and authored array bounds, and preserve exact dependency refusal. Valid
new tokenizer/clock/frame/unit policies or port identities are accepted as opaque
new declarations with different byte hashes; dependents pinned to the old hash
remain unavailable. The generic host does not decide whether either scientific
meaning is correct, convert units, resize images, pad tokens, resample audio,
infer connectivity or voxelize points. Mesh cross-index consistency, ragged
point-offset consistency and geometry/physical correctness are not qualified by
the parameter subset.

The views use the existing `metadata` primitive with author-owned opaque query
identities. Their static shape is valid; no new query handler or renderer is
claimed. Runtime and permission remain `unavailable`, and execution remains
`unsupported`. The corpus also checks six unrelated descriptors alongside a
missing, malformed, incompatible or removed field provider in the canonical
catalog and checks each through the SDK, without launching a workflow.

This is the descriptor-envelope part of E3's explicit modality fixture task
(plan lines 550–551 and acceptance procedure case 12). Existing actual classifier
and spatial workflows own their separate execution evidence; this corpus does
not replace those workflows or establish the full E3 acceptance matrix.
