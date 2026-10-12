# M3 bounded text workflow

Status: implemented and locally verified; independent source review accepted.
The parent integration owner owns combined text/audio qualification, hosted CI,
plan acceptance and PR publication. No main merge or deployment is authorized.

## Scope and authority

The 2026-10-12 user follow-up authorized a real bounded text training/result path
beyond the original export-only M3 description. This branch is
`feature/workspace-text-runs-20261012`, based on the preserved image checkpoint
`6d939359d3cef2464c2aff990dd58d50c4f8d791`. Root admitted the fixed TF-IDF +
MultinomialNB recipe and the new `text_classification_v1` projection after
inspection showed that `canonical_v1` omits complete frozen family snapshots.
Existing exports and PostgreSQL metadata schema are unchanged.

Owned files are the text exporter/trainer/tests, narrow existing release/graph/
run/UI composition and their contract documentation. Root owns active plan/
ledger, SQL/schema, shared CI and audio integration. The isolated worktree
`/workspace/Tuldok-text-20261012` is retained for integration/review; its owner is
the M3 text worker, and root disposes of it only after accepted integration and
reachability verification. No unrelated/user changes were present or removed.

Applied standards: `/workspace/Coding-Standards` at
`dcc56f26` (Core and Router; implementation, verification, commits, frontend,
accessibility, persistence, IPC, contracts/evolution, security, concurrency,
code design and GUI/oracle evidence). The existing application owns the service
boundary. No second scheduler, database layer or arbitrary graph executor was
introduced.

## Runnable result

Data imports and explicitly reviews text class examples, previews class/family
coverage, and freezes a content-addressed text release. Pipeline chooses the
matching recipe, supports bounded parameter and typed-edge editing, save/clone,
server validation and idempotent real admission. Runs executes one local CPU
fit, verifies JSON model/metrics/predictions, gates test evidence, links errors
back to current Data and preserves frozen source/annotation references across
correction, new release and restart.

The model fits vocabulary, feature selection, IDF and NB coefficients only on
training records. No pretrained weights, network service or quality claim is
involved. `model.json` is data-only; the cold reader reproduces the fitted
estimator before publication. Existing text entities/corpora/responses/
preferences remain accessible through their existing review/export paths.

See [the text contract](../../../contracts/workspace-text-training.md),
[pipeline contract](../../../contracts/workspace-pipeline.md), and
[run contract](../../../contracts/workspace-runs.md) for bounds and compatibility.
Older applications are not supported readers after new text graphs/runs are
admitted; downgrade restores a quiesced pre-M3 backup. The current application
preserves old M2 image documents without rewriting their digests or artifacts.

## Qualification evidence

- 54 focused Python tests passed in 42.358 seconds:
  `PYTHONPATH=tests:. python -m unittest test_pipeline test_runs test_dataset_releases test_image_classification_export test_text_training -q`.
  These include 13 new text cases, actual sklearn subprocess execution,
  train-only vocabulary/IDF, parameter/resource checks, frozen byte/JSONL/index
  mapping, unknown family lineage, unselected bridge leakage, valid retained
  deleted members, explicit exposure, correction and reopen.
- Two workspace contract tests, existing workbench and image-release controller
  tests, affected JavaScript syntax checks and `git diff --check` passed.
- Early complete browser milestone: `build/qa/workspace-text-run/run-VvAVtI`.
  Follow-up `run-k1uuog` passed 13 real checks including keyboard navigation,
  empty/loading/error states, stale graph rejection, lost committed response
  reconciliation without duplicate admission, actual training, artifacts,
  correction/new release, held-out exposure and restart. Both receipts correctly
  mark the evolving source as dirty. They are milestone evidence, not exact-head
  release screenshots. Clean-head qualification is recorded below when complete.
- Independent worker `/root/text_review` found three P2 boundary defects and
  verified their fixes: inherited native thread settings, unsupported ZIP
  compression escaping typed listing failures, and unknown/unavailable source
  lineage falsely passing frozen-family validation. Four targeted independent
  checks passed in 3.226 seconds. No remaining source P1/P2 findings.
- Independent Python-stdlib TF-IDF/NB equations (no sklearn/NumPy inference)
  reproduced train-only vocabulary, smoothed IDF, class priors, normalized
  feature counts/additive smoothing, validation softmax scores and exact source
  references. Nine train/five validation examples, 17 features; maximum
  probability error `2.220446049250313e-16`.
  [Exact source/runtime receipt](m3-text-independent-math.json).

Review also corrected misleading TinyCNN stage text for text runs, stale saved
recipe revision display after peer/reload, text exposure wording and capability
copy. The new browser's physical click helper waits for enabled/connected state,
scrolls, waits for layout frames and checks hit testing; no arbitrary wait or
assertion suppression replaced a failure.

## Retained published image result

A real image run was created with the clean **old** checkout at exact
`6d939359d3cef2464c2aff990dd58d50c4f8d791`, then reopened with this text candidate.
The complete public receipt, graph snapshot/digests, frozen predictions, all six
artifact hashes, existing exposure and one-run/no-replay count were unchanged.

- Disposable authored catalog: `/tmp/tuldok-retained-image-m3-nx3h0gxb`
- Run: `e9b38263fab54d04ba79264d7317aeae`
- Graph SHA: `0c9120e8c8946b1b59e427a11342872d93df7ff25d7c063d8ab471f59d55b1f5`
- Release SHA: `6cad94481c648f609d303963191e9ffa31a4a571114800d7dfcfa018fab150bf`

`compatibility-before.json` and `compatibility-after.json` remain beside the
catalog for root's combined schema-upgrade test. All catalog writers were
closed. This proves retained M2 compatibility; it does not claim a later audio
schema upgrade, which belongs to combined integration qualification.

## Environment and launch

Local proof uses Python 3.12.14, PostgreSQL 17.11, Pillow 12.3.0, scikit-learn
1.7.2, NumPy 2.5.4, SciPy 1.18.1 and Chromium in the managed environment.
Runtime package versions and adapter source hashes are saved with each run.
No user machine, private corpus or external execution harness was used.

```sh
TULDOK_DATABASE_URL='host=/tmp/tuldok-pg/socket port=5432 dbname=tuldok user=tuldok passfile=/tmp/tuldok-pg/app.pgpass' \
TULDOK_TRAINING_PYTHON=/tmp/tuldok-training-venv/bin/python \
/tmp/tuldok-app-venv/bin/python app.py --data /tmp/tuldok-m3-text-demo --port 8096
```

Open `http://127.0.0.1:8096/workspaces` and choose **Current local catalog**.
The DSN uses a local private passfile; no credential contents are committed.
Fresh authored catalogs are disposable. Root owns migration of retained catalogs.

## Remaining integration gate

Parent owns the serial merge with the audio Data milestone, shared schema
upgrade qualification, complete lifecycle CI, and PR readiness. Audio, ASR,
3D and arbitrary graph execution are not added by this branch. This slice stops
at the complete bounded text workflow.
