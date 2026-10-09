# Reviewed dataset release contracts

`dataset_releases.py` owns exact source/target snapshots, protected-family allocation, fresh preview proof and immutable atomic publication. Source/review/rights/history remain their existing owners. Target-specific formats supplement canonical output; they do not make supervision interchangeable. Whole connected families include selected/unselected/deleted bridges and fixed source splits. Ratios weight record counts, not semantic independence. Selections are bounded5,000 units. Text and native-asset budgets are40MiB; specialized writers also enforce their documented complete logical-output budgets. Canonical image acquisition/normalization retains its own pixel/asset bounds; this statement is not a universal40MiB canonical-image archive limit.

## Canonical/native assets

Canonical manifests and split JSONL retain typed targets and canonical assets; detection is projected to COCO pixel-edge `xywh` (including fractional coordinates and multiple objects/categories; see [general COCO contract](general-coco-detection.md)), text spans use Unicode code points. Sequence/mesh raw bundles remain whole assets. New sequence-only exports add declared `protected_components` and per-record `export_group`; mixed/nonsequence key sets stay unchanged. Native consumption validates the included known graph and raw-derived groups, not omitted upstream completeness/authenticity.

## Image captions

`image_caption_v1` requires a nonempty human-reviewed caption, at most4,000 code points. Prompts/provider output remain provenance. Layout is normalized PNGs with `train/val/test/metadata.jsonl`, exact rows `file_name/text/group`; validation maps to val and all splits are nonempty. Manifests retain complete relevant families and exact source/target revisions/hashes. Unchanged chapter26 validator `tests/fixtures/diffusion_check_image_data.py` has SHA256 `6a4394308a4cc69b4ca965aca7f8459d7711ac9d51ce70492562c6ec6d806f94`. Compatibility is not caption semantics, permission or model quality.

## Image classification

`image_classification_v1` emits unchanged normalized PNGs under `train/val/test/class_000000/ID.png`. Sorted exact Unicode labels map bijectively to opaque folders/zero-based indices; labels never become paths, slugs or case-folded identities. Chapter8 ImageFolder requires at least2 classes and every class in each split; preview blocks missing coverage without dropping/moving records. Canonical has no such two-class restriction. Same-split repeated pixels remain with warnings; fixed cross-split families conflict.

`image_classification_export.py` pins the reader Torch2.8.0/torchvision0.23.0 `ImageFolder(allow_empty=False)` and unchanged fixture `train_image_classifier.py`, SHA256 `a198463590d41660c21ae45313b47c3a5baf38889eb9bc029e4c7fe8aa741ac1`. Trainer execution/quality are separate from export compatibility.

## Plain-text corpora

`text_corpus_v1` requires a separately human-reviewed corpus note; classification/entity/answer approval is not reused. Sort selected IDs within allocated splits, encode existing NFC/LF canonical text as UTF8 without trimming/re-normalizing/splitting, and add exactly2 LF bytes after every document, including the last. Emit `train.txt/validation.txt/test.txt`, `documents.jsonl` with half-open document/separator byte ranges and exact revisions/families, canonical `assets/ID.txt`, frozen metadata/per-file hashes. This is not a pre-normalization original-source backup.

Chapter11 uses256 raw-byte token IDs and one-byte-shifted targets. Windows may cross document/UTF8 boundaries; separators are ordinary bytes, not EOS or attention resets. Train must exceed128-byte context, validation/test need at least2 bytes, and all splits are nonempty. Allocation still weights records; complete duplicated assets/metadata count toward40MiB.

`text_corpus_export.py` pins book commit `fb895e1a3e08fac86738106e6122bdcafb124e65` and published companion ZIP SHA256 `e924589b152f68bb15d89b8f95e3b52005bbe4a9f7770f2d0550b5422d3a11d6`. Unchanged three-file source hashes/attribution remain in `tests/fixtures/tiny_transformer/README.md`; no companion ZIP/checkpoint is added. Trainer execution is excluded from current no-training QA.

## Independent answers and preferences

`text_instruction_v1` emits only `prompt/completion` for independently revisioned human-reviewed answers bound to exact text prompt/source revisions. Sidecars/manifests retain answer/parent evidence/families. Answers are separate judgment records, not generic annotation replacement. Empty/whitespace-only completions are rejected; stale selected bindings block, and related prompts/answers stay together. Text/answer bounds are200,000 code points,5,000 selected responses/40MiB logical output.

`text_preference_v1` requires a separately reviewed comparison of two distinct existing answers bound to one exact prompt. Directional rows contain `prompt/chosen/rejected`; ties/abstentions retain manifest evidence/exclusion reasons. Current opposing reviewed judgments of an exact unordered pair block even if unselected. Identical strings remain with a degenerate-pair warning. Answer review/order/provider scores never grant preference review. Competing evidence participates in preview and bounds; history/deletion/frozen output remain independent.

Unchanged TRL0.23.1/Datasets4.1.1 package/source hashes remain in `tests/instruction-consumer-pins.json` and `tests/preference-consumer-pins.json`. Isolated dependencies are in `tests/instruction-consumer-requirements.txt`, not app runtime. Completion masks/EOS/padding/truncation/collators are consumer settings. Export alone does not qualify a tokenizer/trainer/model; the separate neural consumer browser gates are excluded from current scoped QA.

## Single-object image detection

`image_detection_v1` adds the roadmap’s [pinned Chapter 9 reader projection](image-detection-export.md) through the existing exact-selection preview and atomic release owner. Original current boxes/label/review/provenance and whole-family splits stay intact; derived masks are transport only. Canonical COCO mapping and geometry remain unchanged.

Point-cloud assets retain unchanged points.ply/points.json, native attribute dtypes,
units/frame and immutable declared source/family/fixed-split lineage. New-owner
raw-pair imports are drafts; local reviews/rights and newly allocated splits for
unassigned inputs do not transfer. See [point-cloud v1](point-clouds.md).
