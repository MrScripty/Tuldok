# Reviewed plain-text corpus releases

## Scope and source

Add `text_corpus_v1` for the unchanged **published Chapter 11 byte-transformer
consumer**, starting from public Tuldok PR 27 commit
`a8217d22d21fae23940ec47f0e6aa5c9654c9137` (local base tree
`5a0a1006dc4962dfe63f88c6402a05c585cc757c`). This is a narrow workbench/release/UI
extension. Detection import, Pumas providers, mesh/Rheon contracts and frozen
main are outside its scope. No publication occurs before independent review.

The named book is `bc-ai-ecosystem/training-your-own-models`, pinned at
`fb895e1a3e08fac86738106e6122bdcafb124e65`. Its authoritative executable examples
are in the published companion ZIP, not repository source blobs or chapter
snippets. The retained 806,494-byte `training-models-companion.zip` matches the
[published checksum page](https://github.com/bc-ai-ecosystem/training-your-own-models/blob/fb895e1a3e08fac86738106e6122bdcafb124e65/docs/downloads/checksums.json):
`e924589b152f68bb15d89b8f95e3b52005bbe4a9f7770f2d0550b5422d3a11d6`.

Three unchanged fixture files are retained from
`training-models-companion/examples/tiny-transformer/` in that ZIP:

- `train.py`: `8d2b908007dabbbd609312f1a22a697b40534b6c5ab07e3d540fd5833295e47d`
- `model.py`: `d304e951615f3bcb9cd5f4158b7348c5ecfd68731d8a5d62bd0d98e837dd1784`
- `use_model.py`: `34b94d2be0a870fc470d27e61738e7ff193b586122b72724f7a33f2688099957`

They are attributed to *Training Your Own Models on One 24 GB GPU*, Vibe Authored
by Dr.Puma. This retention does not grant a new blanket license. The upstream
repository's reuse and evidence boundaries still apply.

## Explicit review authority

Text import continues to create a draft in its existing workflow. A user must
choose the new `text_corpus` task, enter a nonempty review note (up to 4,000
Unicode code points), and explicitly save as `human_reviewed`. The task stores
exactly `{"note": "..."}`. A trusted verifier cannot grant corpus approval.
Classification/entity review, instruction-answer approval and preference
judgments are not silently reused. As with other workbench tasks, changing a
record's current task replaces its current target and keeps prior revisions in
history. Corpus task changes and note edits reset the editor to draft.

## Byte contract

`text_corpus_export.py` owns this consumer-specific projection:

1. Sort selected record IDs deterministically within each allocated split.
2. Encode the existing canonical NFC/LF text as UTF-8. Never trim it, normalize
   it again, split it, truncate it, or remove existing trailing newlines.
3. Append **exactly two LF bytes** after each document, including the final one.
4. Emit `train.txt`, `validation.txt`, and `test.txt` at the archive root.
5. Emit `documents.jsonl` mapping every document to its file, zero-based
   half-open `byte_start`/`byte_end`, separate half-open
   `separator_start`/`separator_end`, stable record ID, exact record/source
   revisions, canonical/original-source hashes and connected-family ID.
6. Retain duplicated canonical `assets/ID.txt` bytes and a frozen manifest with
   accepted task/review note, review state, provenance/rights notes, revisions,
   source hashes, exact family evidence, consumer pin and per-file byte hashes.
   This is not a backup of pre-normalization original text.

The unchanged reader converts **raw bytes** into integer tensor IDs, with a
256-value vocabulary and targets shifted by one byte. Sampled windows may cross
both document boundaries and UTF-8 character boundaries. Separators are ordinary
training bytes; they are **not EOS tokens or attention resets**. No masking,
packing boundary, tokenizer or model behavior is added or implied.

## Splits and bounded publication

The existing complete connected-family graph remains the sole split owner.
Protected groups, parents/lineage, decoded-content duplicates, retained deleted
source evidence and unselected bridges participate. Existing fixed source splits
are preserved. Conflicting fixed assignments and unavailable historical lineage
block. Whole connected families are indivisible.

Allocation still weights **record counts**, never byte counts. Requested
percentages remain targets, not exact quotas. Preview reports document bytes,
separator bytes, total consumer bytes, document counts and selected family counts
separately for each split. The three splits must be nonempty. For the reference
context of 128, `train.txt` must contain **more than 128 bytes**. Validation and
test must each contain at least **2 bytes** for the actual evaluator. Larger
custom contexts may require more train bytes. An undersized split blocks; the
adapter never splits a document, moves a fixed family or manipulates quotas to
make the consumer run. Add reviewed independent documents or change split
settings deliberately.

Every publication requires a fresh preview fingerprint binding exact revisions,
settings, full related-family snapshots and consumer/byte contract. Preview is
read-only. The existing 5,000-record limit applies. A single deterministic entry
producer sizes and writes the **complete logical archive**, bounded to 40 MiB,
including duplicated assets, consumer files, manifest, mapping and README.
Publication checks the bound and content hashes again, removes partial files on
failure, then atomically installs a deterministic content-addressed ZIP. Later
record/source edits cannot alter an existing release.

## UI

The existing text editor exposes a corpus review-note control. The collection
can filter `text_corpus`, and the existing release selector names the Chapter 11
target. Help and preview disclose byte semantics, thresholds and distinct
byte/document/family counts. Existing editor and selected-revision owners retain
control: format/ratio changes revoke previews; export reads saved revisions;
dirty notes are preserved; repeated requests are fenced. Text rendering uses
`textContent`.

## Verification

Run from the repository root:

```sh
python -m unittest discover -s tests
node tests/test_text_corpus_export_controller.cjs
node tests/browser_text_corpus_export.cjs
TEXT_CORPUS_CONSUMER_PYTHON=/path/to/torch-2.8-cpu/bin/python node tests/check_text_corpus_consumer.cjs
```

The consumer gate needs Pillow (the application's dependency) and Torch 2.8.0.
No tokenizer, remote model, dataset download or GPU is used. It checks pinned
source hashes, actual `read_bytes` output against independently constructed raw
byte tensors, 512 independently constructed shifted windows, cross-document and
UTF-8-boundary samples, the actual training/evaluation minimums, a two-step CPU
train with reference context 128 and a tiny width-16/layer-1 model, checkpoint
reload, and unchanged `use_model.py` held-out evaluation. Authored fixtures
qualify transport/reader compatibility only; their loss is not model quality.

Backend regression coverage includes exact Unicode mapping, retained trailing
newlines, deterministic ZIP/hash identity, read-only preview, frozen reopen,
wrong tasks/review states/notes, stale tokens/revisions/family membership,
undersized/empty splits, fixed-family/duplicate leakage, unselected bridges,
retained deleted sources, missing lineage, logical archive sizing and failed
publication cleanup. Real HTTP coverage imports, reviews, previews, freezes and
reopens frozen bytes. The deterministic controller gate covers dirty-note and
fixed-selection preservation, stale-format responses, repeated preview/freeze
requests and blocker fencing.

The native Chromium gate performs actual UI import, review, preview, freeze and
immutable download/reopen, along with dirty-note Cancel/discard, repeated clicks,
stale revisions and 390-pixel layout. It writes JPEG quality 85 evidence. Browser
startup restrictions are reported separately; an authored gate or HTTP/controller
pass is never represented as a passed rendered-browser check.

All generated ZIPs, checkpoints, logs and images belong outside Git or in ignored
build/output directories. Dataset `.txt` files are necessary training data.
Documentation remains Markdown/PDF. The aggregate workflow registers backend,
controller, real-browser and actual-consumer gates.
