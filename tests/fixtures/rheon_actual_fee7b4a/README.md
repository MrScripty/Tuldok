# Actual capped Rheon producer fixture

`run.json` and `frames.jsonl` are unchanged bytes from one actual local execution
of MrScripty/Rheon draft PR 20 at exact clean commit
`fee7b4a139574f87b259796b1ba8698a41d31ac1`. The official Rust/Cargo 1.92.0 toolchain
built only `--locked --no-default-features --example dense3d_sequence`.
The producer orchestrator ran exactly one 16×8×4 case: constructor plus eight
accepted 0.0625 s steps. The normal producer validator completed it and published
the original manifest last. No second physics run, broad simulation or model work
occurred. Retained command paths are historical execution provenance; consumers
must not execute them or treat them as paths to import.

All 35 declared source digests and the executable digest were checked against the
clean exact checkout and independently reviewed. `producer-receipt.json` binds
the recorded raw hashes, tree, provenance and comparison to the separately labeled
source-derived synthetic fixture. `rheon_source_derived.py` remains synthetic; it
has not been replaced or relabeled as real producer output. Actual and synthetic
constructor states share the same initial-family split boundary even though later
field values and diagnostic/provenance bytes differ.

This is a frozen compatibility fixture, not human-reviewed training data. Tests
exercise explicit review controls without certifying science or permission.
Its scope remains fixed all-fluid constant-density carrier and represented-fraction
donor transport. It does not qualify free surfaces, two-phase inertia, material
calibration, multidirectional accuracy, performance or a training model.
PR 20 was still draft and unmerged when read; no merge is assumed.
