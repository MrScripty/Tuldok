# Workspace image training adapter v1

`image_training.py` owns the closed `tinycnn_cpu` version 1 adapter. The graph
and run owners import its parameter decoder and frozen-release inspector; they
do not import Torch. The adapter produces private files for the run supervisor
to verify and publish. It never owns queues, database state, process cancellation,
release creation, annotation review, or publication.

This is the first bounded real image workflow admitted by
[the workspace plan](../plans/dataset-centered-workspaces/plan.md). It trains a
small convolutional classifier from scratch on CPU. There is no pretrained
variant, arbitrary command, plugin, downloaded model, automatic package install,
or alternate backend. It leaves the historical
`tests/fixtures/train_image_classifier.py` and its pinned source hash unchanged.
Tiny authored fixtures establish transport and execution correctness, never
useful model quality or generalization.

## Optional runtime

The application runtime remains separate. Install the approved optional Linux
CPU environment explicitly, then select its Python executable in the run owner:

```bash
python3 -m venv .venv-training
.venv-training/bin/python -m pip install -r requirements-training.txt
.venv-training/bin/python image_training.py --probe
export TULDOK_TRAINING_PYTHON="$PWD/.venv-training/bin/python"
```

The requirements pin `torch==2.8.0+cpu`, `torchvision==0.23.0+cpu`, and
`scikit-learn==1.7.2`. CPU wheels come from PyTorch's CPU package index; other
dependencies resolve through the package manager. Pillow uses the application's
supported `>=10.2,<13` range. This is a direct dependency/version contract, not a
hash-locked transitive environment. The runtime receipt records the actual
Python and pinned package versions. Package distribution retains the upstream
packages' license files; this repository does not vendor their source or wheels.

`--probe` emits one JSON object with `schema_version:1`, `available`,
`adapter:{name:"tinycnn_cpu",version:1}`, `runtime`, and `problems:[{code,message}]`.
It checks exact installed CPU versions and loads the actual dependencies. Exit
0 means available; exit 2 means unavailable/unsupported. Missing dependencies
never trigger installation or a weaker runtime. Linux is the currently qualified
process-supervision platform. Other platforms return unsupported.

## Trusted job boundary

The run owner writes a bounded local job file, then executes a structured argv:

```text
<selected-python> image_training.py --job <server-owned-job.json>
```

The exact version 1 JSON fields are:

| Field | Contract |
| --- | --- |
| `schema_version` | Integer `1` |
| `dataset_id`, `run_id` | Canonical lowercase 32-hex identifiers |
| `graph_sha256` | Frozen executable graph SHA-256 |
| `release_id`, `release_sha256` | Equal lowercase SHA-256 of the exact frozen ZIP |
| `release_path` | Absolute existing immutable release path, supplied by the run owner |
| `output_dir` | Absolute existing empty private directory, supplied by the run owner |
| `parent_pid` | Positive PID of the owning supervisor process |
| `parameters` | Exactly the four fields below |

Jobs are at most 16 KiB. Unknown or duplicate fields, nonfinite numbers, Boolean
numbers, malformed identifiers and mismatching release identity are refused.
Paths are an internal server-owned authority, never values accepted from browser
jobs. The run owner controls the release/output roots and excludes concurrent
untrusted filesystem writers. The adapter refuses an output symlink/nonempty
directory and creates only its fixed artifact names. It cannot make an arbitrary
caller-supplied path safe or authenticate a user.

`PARAMETER_BOUNDS` and `validate_parameters` are the canonical parameter
authority used by the graph and worker:

| Parameter | Inclusive range | Suggested UI default |
| --- | --- | --- |
| `epochs` | Integer 1–5 | 1 |
| `batch_size` | Integer 1–16 | 8 |
| `learning_rate` | Finite number 0.00001–0.01 | 0.001 |
| `seed` | Integer 0–4,294,967,295 | 42 |

The worker requires explicit values; defaults are presentation guidance.

## Frozen release decoding and execution

`inspect_release(path, expected_sha256)` validates an
`image_classification_v1` release without importing Torch, returning its preserved
manifest. Its domain exception is `TrainingError(outcome, message)` with
`outcome`/`code` in `invalid`, `unsupported`, `unavailable` or `failed`.
The adapter reads and hashes one bounded ZIP byte snapshot, then validates and
extracts exactly those checked bytes. It never reads current annotations.

Limits are 40 MiB compressed/input bytes, 64 MiB expanded bytes, a 1 MiB manifest,
6–128 images, 2–8 classes, and one single-frame PNG per image. Each image is at
most 4,194,304 pixels and 8,192 pixels on either dimension. Every class must occur
in train, validation and test, matching the existing ImageFolder consumer.
There is no dropping, resplitting or class renumbering to make a run start.

The decoder checks ZIP member names/counts, traversal, duplicates, symlinks,
special files, encryption, undeclared entries, exact consumer/split mapping,
class vocabulary/index mapping, positive frozen revisions, human review,
source/asset/pixel hashes, decoded pixel dimensions, and protected-component
membership. It rejects a protected component or duplicate pixels crossing splits.
The existing Releases owner remains authoritative for full family allocation,
rights and lineage policy. Retained release fields that are not adapter inputs
remain unchanged in the returned manifest; they do not introduce executable
options. User-authored Unicode labels remain data and never become paths.

The actual `torchvision.datasets.ImageFolder` reads the private checked image
tree. Its class indices and membership must match the manifest. Preprocessing is
deterministic RGB loading, `Resize((96,96))`, then `ToTensor()`, with no fitted
statistics or augmentation. The classifier uses convolution widths 16/32/64,
ReLU, pooling, global average pooling, and a linear class head. AdamW uses the
requested learning rate and fixed weight decay 0.0001. Training and interop each
use one CPU thread; DataLoader has zero worker processes. Torch deterministic
algorithms and the explicit seed govern data order and initialization within the
recorded runtime. Reproducibility across different runtime/platform versions is
not asserted.

Validation loss selects the best checkpoint. Test evaluation happens once after
that selection and cannot change it. No test scores or per-example predictions
enter progress logs, default metrics, or the checkpoint. The run owner must
record durable test exposure before serving either held-out file; generating
private test artifacts is distinct from displaying them to the user.

## Artifacts and observation

All JSON artifacts carry `schema_version:1`, the adapter identity, and
`source_identity:{dataset_id,run_id,graph_sha256,release_id,release_sha256}`.

| File | Contents |
| --- | --- |
| `metrics.json` | Parameters, transform, exact class vocabulary/map, validation metrics, epoch history, best epoch and runtime receipt |
| `test-metrics.json` | `split:"test"` and held-out metrics |
| `predictions-validation.json` | Validation rows and exact class vocabulary/map |
| `predictions-test.json` | Held-out rows and exact class vocabulary/map |
| `checkpoint.pt` | Restricted-loadable Torch state dictionary with identity, class mapping, parameters, transform and selected epoch; no optimizer/resume promise |
| `artifact-manifest.json` | Written last; SHA-256, byte count, media type and split for exactly the five payload files |

Metrics contain `split`, `examples`, `loss`, `accuracy`, `macro_f1` and a confusion
matrix whose row/column indices follow the frozen class vocabulary. History
contains `epoch`, `training_loss`, and `validation`. Runtime contains Python,
Torch, torchvision and scikit-learn versions, CPU device/thread count, measured
elapsed seconds and Linux process peak RSS bytes. The timing includes release
validation/runtime loading, training and evaluation up to metrics generation.

Each prediction row carries exact `id`, `revision`, `source_revision`,
`source_sha256`, `asset_sha256`, `exported_pixel_sha256`, `split`, `truth_label`,
`truth_index`, `predicted_label`, `predicted_index`, and class-index-ordered
`probabilities`. These are computed model outputs, never fixture replacements.
Opening a prediction in Data does not rewrite its frozen target or metrics.

Stdout is a bounded sequence of JSON events: `started`, one `epoch` event per
epoch (validation metrics only), and `completed`, or `failed` with typed outcome
and a bounded non-sensitive message. Events use schema version 1. Successful
exit alone does not prove publication: the supervisor must verify all six files,
their identity, content contracts and manifest hashes before accepting results.

## Lifetime and failure

The adapter arms Linux `PR_SET_PDEATHSIG` with `SIGKILL` before importing Torch
and checks the expected parent PID after arming to close the parent-exit race.
The supervisor retains ownership of the exact subprocess/process group, bounded
logs, deadline, cancellation, wait/reap, and terminal state. The adapter creates
no child processes. A cancelled/killed worker can leave partial private files;
they must never appear as succeeded artifacts. Retrying starts new training from
scratch in a new empty directory and does not overwrite a previous run.

The closed implementation makes no network or model-download calls. Network
isolation is a separate execution-environment qualification claim, not a sandbox
guarantee made by this adapter. The runtime must already be installed locally.

## Verification

`tests/test_image_training.py` builds real releases using Dataset/Workbench and
the existing Releases preview/freeze methods. It covers malformed contracts,
hash/pixel/class identity, review/revision requirements, bounds, ZIP traversal
and duplicate members, and missing runtime behavior. With
`TULDOK_TRAINING_PYTHON` set to the pinned runtime, it trains one real epoch after
editing current annotations, checks every artifact hash/reference, and uses an
independent Torch/ImageFolder reader to reproduce checkpoint predictions and
verify weights changed from initialization. Without that optional runtime the
one-epoch test is explicitly skipped; such a run cannot qualify real M2 training.
The parent run-service/browser gates own cancellation, application restart,
test exposure, publication, and the complete user workflow.

## Model-aware TinyCNN v2

The distinct `image_classification_model_v2` recipe selects `tinycnn_cpu` adapter
version2 and job schema2. Historical image recipes, job schema1 and their closed
five-payload artifact inventory retain their original meaning. V2 accepts the
existing four optimizer parameters plus exactly three integer channel `widths`
(each4–64), `input_size`32/64/96 and `head:"linear"`. It initializes from scratch,
uses the frozen class vocabulary and retains every actual end-of-epoch state.
There is no arbitrary topology, pretrained download, GPU or resume capability.

The template `tinycnn_v2` is inert Model Definitions material. Its specification,
RGB resize/tensor policy and frozen-vocabulary probability output policy must
match the saved recipe. Publication captures the actual adapter import closure;
preparation refuses changed source, model policies or runtime. The resolved
`tinycnn_epoch_full_validation_v1` profile captures each admitted epoch, retains
the selected state within the existing snapshot budget and ranks the complete
validation membership using `sha256_rank_v1`, seed0 independent of training seed.
No test example is a probe. The largest five-epoch inventory is30 files including
the outer manifest, within the32-file/64MiB result profile.

V2 automatically emits the D2 `model_evidence_v1` envelope, fixed probe manifest,
checkpoint index, exact `checkpoint_state_v1` descriptors, fitted-transform
manifest, metric definitions, scalar observations and each epoch's weights and
probe predictions. A descriptor hashes the run/model/weights/transform/actual
clock binding; equal weight bytes at distinct clocks remain distinct checkpoints.
Optimizer updates are counted at the actual `optimizer.step()` call; epoch,
physical time and wall elapsed time keep their separate meanings. Transform
statistics are an explicit empty manifest because preprocessing is not fitted.

After training child drainage, the owner verifies exact inventory, byte hashes,
source/model/profile bindings, full frozen validation coverage, finite probability
vectors, actual clock increments and validation-loss checkpoint selection. An
additional pinned CPU subprocess reconstructs every retained checkpoint against
its exact frozen validation inputs. Only successful reconstruction and confirmed
process cessation permit atomic publication. Queries never deserialize weights.

Run the actual owner/HTTP/study/Run qualification with the separately provisioned
CPU interpreter:

```bash
TULDOK_TRAINING_PYTHON=/qualified/cpu/python python tests/qualify_model_development.py \
  --task image --fixture tests/fixtures/model_development --output /tmp/new-model-qa
```

The output directory must be absent. The driver records actual two-epoch training,
checkpoint/probe custody, bytes, elapsed time/RSS, cold reopen, independent fixed
inference and a correction→new-release→new-trial comparison. Authored RGB patterns
prove bounded workflow mechanics; they do not establish useful model quality.
The1440/390 keyboard browser checkpoint is separately reported, never inferred
from backend qualification.
