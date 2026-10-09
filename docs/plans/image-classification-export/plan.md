# Reviewed image classification release

## Scope

Add one consumer-specific release format, `image_classification_v1`, on the
verified public development source `cdb8e241b002c5beef464df1bec36f10efb7023e`.
This is a source-only development change. Frozen main, private detection import,
simulation contracts and existing canonical/caption/text adapters stay separate.

The format produces a self-contained `train/val/test/class_000000/ID.png` tree
for the Chapter 8 image classifier from *Training Your Own Models*. Its exact
unchanged source is retained at `tests/fixtures/train_image_classifier.py`:
SHA-256 `a198463590d41660c21ae45313b47c3a5baf38889eb9bc029e4c7fe8aa741ac1`.
This closes the classification export gap identified in the dataset-production
research without adding an inference service or changing annotation authority.

## Consumer-backed choices

- The trainer uses Torch 2.8.0 and torchvision 0.23.0, constructs ImageFolder
  separately for train, val and test, checks identical `class_to_idx` and requires
  at least two classes. These are requirements of this named adapter only.
- [The pinned upstream reader](https://github.com/pytorch/vision/blob/v0.23.0/torchvision/datasets/folder.py)
  sorts directory names into indices and defaults `allow_empty` to false. Every
  class therefore needs at least one image in every exported split. Preview
  shows per-class coverage and blocks missing cells; it never drops or moves
  records to satisfy that requirement. Canonical export retains its prior rules.
- Exact labels are Unicode data, not directory names. Sorted exact labels map to
  fixed-width `class_000000` folders and zero-based indices. The manifest's
  `class_vocabulary` and `class_to_idx` retain that bijection, including Unicode,
  path-like strings and case-distinct labels. No normalization, slugification or
  case-folding silently merges classes. The index vocabulary is per release.
- Downstream predictions and the trainer's checkpoint/report use opaque folders.
  Keep the release manifest with the trained model to translate those results
  back to exact labels. This adapter does not rewrite the trainer or prediction
  utility's semantics.

## Invariants

1. Every selected record must have an available normalized image and an exact,
   single-class, human-reviewed annotation. A proposed label, draft, generated
   verifier result, multi-label object or another task cannot be relabeled by
   export. Stored malformed/noncanonical labels fail closed before analytics.
2. Selection binds exact record and source revisions. The new adapter requires
   an eligible fresh preview token before publication. Existing release-preview
   epochs prevent a delayed result from authorizing changed browser settings.
3. All protected group, parent, content/pixel-identity and legacy-source links
   participate in the existing connected-component allocator, including
   unselected bridges. Existing fixed splits are preserved; conflicts block.
4. Same-split decoded-pixel repeats remain in the archive with a visible warning.
   This includes possibly contradictory annotations needing user inspection.
   No automatic deduplication or target adjudication is performed. Cross-split
   fixed duplicates conflict through the existing component rule.
5. The image bytes are the existing normalized PNG, without resizing, cropping,
   augmenting or re-encoding. The archived stream is hashed while it is written.
   The manifest retains exact annotations, revisions, review evidence, source
   provenance, raw-source hashes, normalized hashes and connected-family state.
   This is a training view, not a complete original-byte backup.
6. Archive entry order and timestamps are deterministic. Failed publication
   removes the temporary build; later edits cannot change an existing content-
   addressed release. Generated ZIPs, checkpoints, logs and screenshots remain
   in ignored output directories or external scratch storage, never Git.

## UI

The existing release menu names the Chapter 8 target. Its help text states the
two-class and all-split coverage requirements. Preview exposes exact labels,
opaque folder/index mapping, coverage, existing blockers and duplicate warnings.
Text uses textContent; labels cannot create markup. Format changes invalidate
preview without changing editor drafts, review state or fixed selections.

## Verification

- Python tests exercise exact/deterministic projection, provenance, safe folder
  mapping, Unicode/case distinctions, stale selection and preview, unknown input
  fields, malformed/multiple labels, single-class canonical compatibility,
  incomplete coverage, retained same-split repeats, cross-split duplicates,
  unselected bridges, missing/changed bytes, partial-build cleanup and real HTTP
  preview/freeze/download.
- A deterministic controller gate covers safe coverage rendering, dirty editor
  and fixed-selection preservation, stale previews, repeated submits and blockers.
- The dedicated consumer gate imports actual pinned torchvision, compares its
  exact reader-source hash, reads all exported examples, and executes the
  unchanged tiny CPU trainer for one epoch through checkpoint reload/test.
  Actual-reader negative cases verify empty-class and single-class behavior.
- A native Chromium browser gate is registered for real UI interaction, download,
  stale revisions, cancel/discard, reload and narrow layout. Execution availability
  is reported separately; authored coverage is never reported as a passed run.
- Run the registered aggregate after installing the pinned existing instruction
  consumer dependencies plus CPU torchvision 0.23.0 and scikit-learn 1.7.2.

The six solid-color images used for consumer smoke are authored compatibility
fixtures. Their arbitrary training metrics do not establish data or model quality.

## Boundaries

This does not add native ImageFolder ingestion, persistent project-wide class
ontologies, multi-label targets, split stratification, class balancing, model
selection, synthetic-data quality validation or automatic review. Missing rare-
class coverage may require a different consumer, a larger independent corpus,
or explicitly adjusted source split decisions; canonical export remains available.
