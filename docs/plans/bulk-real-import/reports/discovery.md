# Existing source boundaries and unresolved format

Inspected the current workflow/workbench plans and issues, discovery research synthesis, shared-asset ADR, README and Dataset/Workbench/browser source at PR4 `c88c3819207333b620e0cd8f391d11843d393757`.

- `Dataset.add`: base64 decoding and existing image bounds; Pillow EXIF orientation/RGB normalization; original `source`, normalized `image.png`, thumbnail; unique raw SHA-256 and folder cleanup when its owned insertion fails.
- `static/app.js` image batch acquisition: sequential selected files, same sample-admission route, per-file errors and partial success. This is an existing boundary to reuse, not a parallel image implementation. It currently lacks a batch stop control.
- `Workbench.import_asset`: groups/rights/parent checks, calls Dataset for image bytes and uses the same asset ID; text original/canonical preservation, canonical-content deduplication; initial records/annotation history remain draft and unlabeled.
- `static/workbench.js`: one real text/image record per submit, editor-epoch fencing; no manifest parsing, multi-file row binding or bulk cancellation/progress contract.
- Existing plans prioritize real image/text workflows and provenance, keep the UI provisional and reject a universal modality/schema or second image store. They do not choose CSV/JSONL columns, import annotated targets, filesystem paths or restart-safe bulk job semantics.

The material design question is the source contract, not whether Tuldok can normalize images or store text. A native JSONL raw-asset manifest is the smallest candidate consistent with existing operations. An existing annotated corpus needs its real fields and coordinate/normalization contract before admission. No source-file decoder or target conversion is inferred from the book demonstrations.

The original focused tests exercised existing single-row admission only: supplied review/verification provenance cannot upgrade import, and repeated asset admission cannot overwrite an already reviewed record's groups/source metadata. They did not prove a bulk workflow, cancellation, missing-file binding, external-format compatibility or corpus-scale performance.

Later owner disposition: proceed with the recommended native raw-asset manifest first, then map a concrete annotated corpus separately. No existing plan contradicts it. The implemented local slice and actual bulk HTTP/browser evidence are recorded in verification.md. Scale beyond bounded manifest/row/file limits and existing annotated formats remain unqualified.
