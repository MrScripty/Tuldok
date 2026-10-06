# Structured bulk import of real assets

Status: Local admission foundation verified; parser/API/UI remains pending the source-file contract choice. Approved feature objective, candidate encoding is provisional. Acceptance: pending; no bulk capability is advertised or published.

## Objective and binding scope

Import a practical local corpus of real text/image records, report each rejected row without discarding successful rows, retain source and provenance, and require separate annotation/human review. Keep the UI provisional and all existing acquisition, annotation, release and provider workflows intact. Local authored fixtures only; no dataset download, provider call or model installation.

The existing research synthesis and [canonical dataset workflow plan](../dataset-workflows/plan.md) establish the lifecycle and source owners, but choose no bulk file encoding, external column mapping, asset-reference syntax or annotation-ingestion contract. The original research books are not present in this workspace; this proposal relies on the checked-in research synthesis and decisions, not unseen source claims.

Dataset owns image originals, EXIF-oriented RGB PNGs, image IDs and exact-original-byte deduplication. Workbench owns canonical NFC/LF text, original text, generic annotation/review/history, protected groups/parents and canonical-text deduplication. Reuse `Workbench.import_asset` → `Dataset.add`, including the current browser image-batch acquisition boundary; do not create another normalizer, image store or generic job queue. Imports remain drafts. Caller-supplied review/verification/source-hash claims cannot establish approval or overwrite derived source facts.

## Material choice to resolve

Recommended candidate: **native JSONL asset rows plus explicitly selected local image files; annotate afterward**. One row carries the existing `kind`, `name`, `groups`, `parents`, `rights` and either `text` or an image-file reference. A matched file supplies bytes through the existing image acquisition owner. No arbitrary server path, URL fetch, archive extraction, column-mapping framework or universal dataset format.

Alternative: a **specific existing annotated corpus format**. This needs actual row fields, asset-reference convention, annotation tasks/coordinates and normalization basis. In particular, text-entity offsets before NFC/LF normalization and image boxes before EXIF orientation cannot be silently interpreted against canonical assets. Imported targets would still be drafts; an input field cannot grant human or programmatic review.

This choice changes the parser, asset binding, pre-admission validation, target-normalization contract and user error recovery. Resolve it before adding a file decoder, persistence schema, bulk API or UI. The proposed native format is not implementation authority merely because it is written here.

## Candidate behavior independent of a universal format

- Validate row shape and metadata before admission; report source row number, bounded field/error information and created record ID when applicable. Continue after validation/missing-file/duplicate failures; stop on an unexpected storage/system failure rather than disguising it as bad user data.
- Preserve original image bytes and original text, derived hashes/geometry, groups/parents/rights and any specifically admitted source identity under its own provenance owner. Untrusted declared metadata stays distinguishable from verified acquisition facts. No supplied target becomes a caption from a generation prompt.
- Keep duplicate semantics from their owners: repeated canonical text/exact original image is rejected with a useful row result; existing records, review, groups and provenance remain unchanged. A retry must not be reported as a new creation or silently merge conflicting metadata. Do not add an idempotency registry unless a supported request-retry contract actually requires one.
- Prefer sequential bounded per-row work over uploading all image bytes in one request or introducing durable jobs. Cancellation stops scheduling new rows; disclose that an already admitted row may complete and remains in the collection. An aborted HTTP response is not proof of rollback. Reconcile ambiguous outcomes against stored acquisition identity before retrying.
- Bind image references to the explicitly selected local file set. Missing or ambiguous matches are row errors; never fall back to a server filesystem path or unrelated file. Current per-image 25 MiB / 40 megapixel and text 200,000-code-point limits remain; choose manifest/result bounds from the admitted format before implementation.

## Isolation and ownership

Task branch `feature/bulk-real-import-20261006`, isolated worktree `/workspace/Tuldok-bulk-import`. On resumed authorization it fast-forwarded locally from PR4 `c88c3819207333b620e0cd8f391d11843d393757` to local compatibility follow-on `801d598a1400afdc2360128a1657896b89da10c4`, retaining all history and existing bulk discovery/tests. Published PR4 remains `a3f3cbead4137110dfa8af81c94178e6d53aa036`; the new queued-API rejection commit is local pending restored publication access. Main and PR1–3 are unchanged. Parent owns integration, review and eventual UI adoption. Retain this local branch/worktree; do not delete it or publish an incomplete feature draft.

## Composed-design review: applicable

1. Acquisition remains Dataset-owned, records/targets Workbench-owned, and the proposed importer owns only decoding, row scheduling/outcomes and admitted source context. UI owns selection and cancellation controls.
2. Original bytes/text, hashes and asset IDs are stable; annotations/review/revisions remain separately mutable. Partial batch completion changes only admitted rows.
3. Caller knows file/row identity and typed results, not arbitrary storage paths or SQL. Parsing must not duplicate normalization or target validation.
4. A supported new external format changes only its decoder and conformance fixtures; changed acquisition semantics remain with Dataset. No generic adapter registry is required by the first slice.
5. Existing record and source IDs/revisions remain values. Shared lock/SQLite ownership is reused; do not keep that lock across user file reads or asynchronous UI waits.
6. Admission tests exercise the actual SQLite/filesystem owner; row parsing tests use the chosen external contract; browser evidence must traverse actual HTTP import, cancellation and collection refresh.
7. Deleting bulk orchestration removes only multi-row scheduling/results; single-asset acquisition and review remain usable. No competing lifecycle/state machine or image store is retained.
8. Necessary complexity is bounded row decoding, asset binding, partial outcomes, cancellation semantics and source evidence. Keep it within the current owners; no queues/framework migration/provider integration.

## One bounded implementation slice, after contract resolution

Goal: chosen local manifest/file set → row-level validation/admission → visible partial results → draft records → separate manual annotation/review. State: active format-independent admission repair; parser/API/UI remains pending the actual row contract. A real SQLite enrollment failure revealed that image bytes/sample insertion could commit before Workbench metadata/history. Move initial enrollment into Dataset's existing acquisition transaction/file-cleanup owner before any bulk loop depends on row atomicity.

Expected write set: `workbench.py`, `app.py` (composition/routes and only an evidenced acquisition-boundary adjustment), `static/workbench.html`, `static/workbench.js`, `static/workbench.css`, focused `tests/test_bulk_import.py`, `tests/test_real_import_foundation.py`, `tests/test_workbench_controller.cjs`, `tests/browser_bulk_import.cjs`, `.github/workflows/tests.yml`, `README.md`, and this plan directory. Add a separate importer module only if admitted decoding/scheduling needs a distinct owner; no unrelated provider/release edits.

Gate: focused row/source tests, complete registered Python/controller/browser suites, syntax/compile/diff checks, real desktop/narrow browser import/cancel/retry/error results, exact new-head push/PR CI and parent-coordinated review. Publish a separate draft only after its own complete verification; never merge.

## Acceptance claims

| ID | Observable criterion | Evidence / environment / mode | Status |
| --- | --- | --- | --- |
| B1 | Mixed real text/images admitted through existing owners; originals/canonical forms and source metadata survive reopen | contract / real SQLite/filesystem / automated | pending; existing-boundary checks started |
| B2 | Isolated malformed/partial invalid rows yield correctly attributed errors while valid rows succeed, without orphan files/partial record metadata | integration / real HTTP/SQLite/filesystem / automated | blocked on row contract |
| B3 | Duplicate/repeated submissions create no duplicate assets or implicit provenance/review changes; ambiguous response is reconciled honestly | contract / real persistence/HTTP / automated | pending; repeated single-asset owner checks started |
| B4 | Missing/ambiguous assets cannot bind unrelated bytes; unknown/forged fields cannot grant human review or verification | contract / real file/row binding / automated | blocked on binding; existing draft/provenance checks started |
| B5 | Cancel before admission and between rows stops future scheduling; in-flight completion and retry remain visible and correct | user-workflow + integration / representative browser/HTTP / automated | blocked on chosen scheduling contract |
| B6 | Actual bulk import, per-row recovery, repeated controls, editor fencing, progress/cancellation and narrow layout work through real Chromium | user-workflow / representative Chromium / automated and local screenshot inspection | pending |
| B7 | Full registered regression suites and exact new-head hosted CI pass; separate draft and bounded review preserve main/PR1–4 | integration / local and GitHub / automated/review | pending; no feature draft created |

## Exactly one next slice and re-plan triggers

The format-independent image enrollment repair is locally verified: 136 Python tests and all six registered browser suites passed, including source/review/duplicate and injected metadata/history rollback checks. Exactly one next slice: resolve the pending raw-assets-versus-annotated-corpus source contract, then admit precise fields, asset binding, normalization/provenance and cancellation/result bounds and implement the vertical slice. Do not convert unresolved annotations or invent a universal format. Replan for measured scale beyond sequential bounded imports, required annotation coordinates, restart-safe receipts or a stack-base change. Remote writes and new hosted qualification are blocked by the last observed HTTP 401; do not retry denied authentication, change credentials or settings.

[Discovery](reports/discovery.md) · [Admission evidence](reports/admission-boundary.md) · [Ledger](execution-ledger.md) · [Issues](issues.md) · [Existing architecture decision](../../decisions/dataset-workbench.md)
