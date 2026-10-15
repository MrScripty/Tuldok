# Bounded text classification recipe v1

The separately selected `text_classification_model_v2` recipe uses the
[one-fit evidence contract](one-fit-evidence.md), typed model publication and
finite owner-authorized Study/Run execution. The version-1 contract below
retains its original inventory/history.

`text_classification_export.py` owns the frozen projection;
`text_training.py` owns its checked reader, train-only transform, estimator and
JSON model reader. The existing Releases, Pipelines and Runs owners retain
selection, publication, editing, admission, supervision and exposure authority.
No PostgreSQL schema change is required.

## Frozen input

Choose **Text classification · local TF-IDF / Naive Bayes** in Data. Every
selected record must be available text with a human-reviewed single class.
Preview uses the existing connected-family allocator, including unselected
bridges and retained deleted sources. Freeze requires the current preview token.
The new `text_classification_v1` format leaves `canonical_v1` and all existing
image/text exports unchanged. General canonical exports omit complete frozen
family snapshots, so they cannot certify this trainer's split contract.

The ZIP contains `manifest.json`, `README.txt`, exact UTF-8 `assets/<id>.txt`
files and `train/records.jsonl`, `validation/records.jsonl`,
`test/records.jsonl`. Each JSONL row equals its manifest record. The manifest
freezes exact labels and class indices, record/annotation/source revisions,
original source SHA-256, canonical content/asset SHA-256, rights/provenance,
whole protected-component snapshots and split membership. Class indices are
sorted exact labels; no label is used as a filename or silently normalized.

Canonical asset text retains Workbench's NFC/LF transformation. Original source
hashes identify the original imported text; those original bytes are not in this
export and cannot be reconstructed from normalized text. The trainer does not
trim, rewrite or replace frozen assets. Model lowercasing and tokenization are
separately identified transforms.

Eligibility is 6–512 records, 2–8 labels and every label present in each split.
Texts are at most 16 KiB UTF-8 each; complete logical payloads are at most 7 MiB,
ZIPs 8 MiB and expanded reads 16 MiB. Unknown review/source lineage, unsafe or
duplicate members, altered bytes, conflicting class/JSONL references, and
cross-split protected families/exact content are refused. Hidden deleted members
with known retained lineage remain valid evidence. Selected texts must be
available. No examples are dropped or reassigned to satisfy coverage. These
checks cannot prove near-duplicate absence, semantic independence or quality.

## Saved graph and runtime

The saved graph explicitly sets `recipe: "text_classification"`,
`recipe_version: 1`, and definition version 1 for its five fixed stages:
release → validate → train → evaluate → publish. `text_export` connects validate
to train. The existing absent-recipe image document and its executable digest
remain unchanged. Unknown recipes, mismatched release types and arbitrary nodes
cannot execute. The browser offers the existing keyboard forms, typed connection
editing, undo/redo, revision save, clone and server validation.

The train parameters are exactly `max_features` (integer 64–4096, default 1024)
and `alpha` (number 0.01–10, default 1). The optional local
`TULDOK_TRAINING_PYTHON` environment uses the existing scikit-learn 1.7.2 package;
NumPy/SciPy/Pillow and Python versions are recorded. No dependency or model is
installed automatically. Missing/mismatched runtime returns `unavailable`.
Linux parent-death/process-group supervision and the existing 600-second bound
apply. OMP, MKL, OpenBLAS, BLIS, vecLib and NumExpr environment limits are set to
one; the text probe observes loaded native pools and refuses a wider pool.

Pinned source identity includes `text_training.py`,
`text_classification_export.py`, `image_training.py` (its existing bounded
JSON/event/parent-guard primitives only) and `workbench.py`. These exact files are
copied to each private staging directory before execution. Importing text
contracts in the app never imports scikit-learn or Torch.

## Fitting and results

One deterministic fit trains scikit-learn `TfidfVectorizer` and `MultinomialNB`
on the frozen training records. Word tokens use `(?u)\b\w\w+\b`, lowercase,
unigrams, L2 normalization, smoothed IDF and no sublinear TF. Vocabulary,
feature selection, document frequencies and IDF use training records only.
Validation and test only transform through those frozen fitted statistics.
Empty training vocabulary is an actionable failure, not a substitute tokenizer.

There is one fit pass and no validation-driven hyperparameter search or model
selection. The shared v1 progress/history envelope records that single pass as
`epoch: 1`, `best_epoch: 1`; this does not claim iterative NB training. Validation
metrics are default; test metrics and predictions require a durable exposure
reason before access.

Five payloads plus the artifact manifest are published:

- `metrics.json`: validation metrics, one-pass history, parameters, transform,
  vocabulary, runtime versions, elapsed seconds and peak RSS;
- `predictions-validation.json`: probabilities and exact frozen text references;
- `test-metrics.json` and `predictions-test.json`: separately gated test evidence;
- `model.json`: plain JSON vocabulary, IDF, class log priors and feature log
  probabilities, with source identity and parameters;
- `artifact-manifest.json`: exact hashes, sizes, media types and split roles.

The JSON reader validates bounded arrays/indices and never loads pickle or
executable checkpoint code. The worker cold-reads the saved JSON and checks its
training probabilities against the actual fitted estimator before evaluating.
Runs independently checks publication shape, hashes, source references, finite
metrics, class mappings and prediction/confusion-matrix consistency.
Text predictions use `content_sha256`; image-only pixel fields are absent.

Exposure matches record ID or canonical text content hash. Original source
hashes, normalized content hashes and model features remain distinct concepts.
A result links to the current editable Data record while retaining its frozen
source and annotation revisions. Correction creates a new revision/release;
old results and test-exposure history do not change.

## Compatibility and limits

Current code reads retained M2 image graph/run documents and artifacts without
rewriting them. Existing image digests remain unchanged. New text documents
require this recipe-aware application; older application versions are not a
supported reader of a catalog after text graphs/runs have been admitted.
Downgrade uses a quiesced pre-M3 catalog/filesystem backup. Do not delete new
records or alter schema metadata to force an older application to open them.

This is a small CPU classification baseline, not a language-model trainer,
synthetic-data quality endorsement or general graph executor. Other existing
text tasks retain their Data/review/export paths. Audio/3D execution and ASR are
outside this recipe.

Evidence: `tests/test_text_training.py`, `tests/browser_workspace_text.cjs`, and
[the M3 report](../plans/dataset-centered-workspaces/reports/m3-text.md).
