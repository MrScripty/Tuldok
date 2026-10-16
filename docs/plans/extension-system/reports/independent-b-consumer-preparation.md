# Independent B consumer preparation

This is test-only preparation for E3. No actual B producer, SDK admission,
retained Run, numerical acceptance or physical qualification is claimed here.

The analytic kernel and its nine unit witnesses were frozen at `81c0c5d` before
inspecting B's producer. The later artifact adapter uses the declared README,
recipe and fixture protocol. Neither implementation imports the author's
producer or cold oracle, trains a model, or uses NumPy, Torch, the application or
the database. The kernel remains byte-exact to that freeze.

The consumer checks the operator-selected Run/Model/Task/composition/context
identities, all required initial/source/mask inputs, the complete ordered
raw/corrected target map, clocks 32/64, native payload identities, exact source
geometry and gauge, and fixed validation membership. It independently recomputes
train-only means and population standard deviations, derives the two correlated
feature modes in closed form, checks retained weights, reconstructs with the
**retained** transform, and retallies each stage's reference MSE. Reference quality
is reported as a diagnostic. There is no scientific or physics acceptance claim.

Synthetic witnesses exercise full analytic replay, zero-state rejection,
coherently rehashed source/geometry/stage-target mutations and retained-transform
replay. These witnesses never substitute for an actual admitted Run. Independent
review caught and corrected semantic and bounded-read gaps before this freeze.
The CLI streams directory names and checks its 64-file and 16 MiB aggregate limits
before reading excess bytes. It refuses symlinks and reports inside the retained
artifact directory.

For the actual gate, freeze the application's reviewed host and author inventory,
perform the normal finite owner-granted SDK workflow, and download all artifacts
through their public whole-hash receipts. Supply an identity JSON with exactly
`catalog_id`, `run_id`, `model_sha256`, `task_sha256`, `material_sha256` and
`context_sha256`. Derive those from separately fetched authoritative Run,
Model/composition and custody receipts. The context hash must come from the
Run's unique `execution-context.json` artifact receipt, not from the artifact
being tested. The fixture hash must come from the author inventory reviewed
before admission.

```sh
python3 -I tests/extension_b_cold_consumer.py \
  --artifacts /absolute/path/to/whole-hash-downloads \
  --projection /absolute/path/to/public-model-evidence.json \
  --identity /absolute/path/to/independently-selected-identities.json \
  --fixture /absolute/path/to/reviewed-fixture.json \
  --fixture-sha256 REVIEWED_FIXTURE_SHA256 \
  --report /absolute/path/outside-downloads/absent-consumer-report.json
```

The report destination must be absent. A successful report applies only to the
supplied retained bytes and source identities. The main integration lead owns
the actual B admission and A/B shared retention/package qualification.
