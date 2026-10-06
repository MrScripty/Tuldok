# Structured bulk import of real assets

Status: Native raw-asset bulk import locally verified; hosted qualification/review/publication pending. Owner selected raw text/images plus the plan's recommended structured manifest; annotated corpus ingestion is a later feature. UI remains provisional.

## Objective and binding scope

Import a practical local corpus of real text/image records, report each rejected row without discarding successful rows, retain source and provenance, and require separate annotation/human review. Keep the UI provisional and all existing acquisition, annotation, release and provider workflows intact. Local authored fixtures only; no dataset download, provider call or model installation.

The existing research synthesis and [canonical dataset workflow plan](../dataset-workflows/plan.md) establish the lifecycle and source owners, but choose no bulk file encoding, external column mapping, asset-reference syntax or annotation-ingestion contract. The original research books are not present in this workspace; this proposal relies on the checked-in research synthesis and decisions, not unseen source claims.

Dataset owns image originals, EXIF-oriented RGB PNGs, image IDs and exact-original-byte deduplication. Workbench owns canonical NFC/LF text, original text, generic annotation/review/history, protected groups/parents and canonical-text deduplication. Reuse `Workbench.import_asset` → `Dataset.add`, including the current browser image-batch acquisition boundary; do not create another normalizer, image store or generic job queue. Imports remain drafts. Caller-supplied review/verification/source-hash claims cannot establish approval or overwrite derived source facts.

## Admitted first source contract

Owner explicitly selected **native JSONL asset rows plus explicitly selected local image files; annotate afterward** on resumption. This matches the earlier recommendation and existing owner/review decisions; no contradictory repository plan was found. `kind`, nonempty `groups` and matching `text` or `file` are required. Optional `name`, `parents` and `rights` retain existing validation/defaults. Image `file` is an exact flat filename matching one selected file, with no directory/URL/server lookup. Duplicate JSON fields, supplied annotations/task/review/provenance and other unknown fields are rejected. Blank lines keep physical numbering but are skipped. LF/CRLF and strict UTF-8 are supported.

Subsequent feature: a **specific existing annotated corpus format**, requiring actual row fields, asset references, annotation tasks/coordinates and normalization basis. Pre-normalization text offsets and pre-EXIF image boxes cannot be silently interpreted against canonical assets. Input fields cannot grant review. This useful later stage does not block the chosen raw-asset slice.

Bounds: 8 MiB per manifest, 1,000 physical lines, 3 MiB per UTF-8 JSON row, existing text/image limits. `bulk_import.py` owns strict row decoding, request-marker lookup and minimal outcomes. Workbench receives a trusted internal acquisition context: row SHA-256 computed from consumed UTF-8 row text, format and request marker; manifest filename/physical row/image label remain explicitly declared context. Original source text/bytes and derived hashes remain with their owners. The full manifest is not stored or independently authenticated.

`POST /api/workbench/import-row` admits one bounded row through the atomic source owner and returns a minimal receipt. `GET /api/workbench/import-result/<request_id>` is read-only and can confirm a committed row after response loss. Markers are stored in existing provenance, not a new job/idempotency table; repeated markers/content never overwrite records. Missing lookup is not proof of stopped work. Storage errors are HTTP 500 and halt the client; invalid/duplicate rows are HTTP 400/409 and permit later rows.

The separate bulk controller schedules rows sequentially, snapshots the chosen manifest/file set, fences repeated controls, does not abort in-flight work on Stop and pauses on an uncertain response without replay. A matching saved result can reconcile creation; dismissal makes no rollback claim. Results remain visible with IDs and physical row numbers. It refreshes the collection without opening/discarding editor state or changing selection.

## Candidate behavior independent of a universal format

- Validate row shape and metadata before admission; report source row number, bounded field/error information and created record ID when applicable. Continue after validation/missing-file/duplicate failures; stop on an unexpected storage/system failure rather than disguising it as bad user data.
- Preserve original image bytes and original text, derived hashes/geometry, groups/parents/rights and any specifically admitted source identity under its own provenance owner. Untrusted declared metadata stays distinguishable from verified acquisition facts. No supplied target becomes a caption from a generation prompt.
- Keep duplicate semantics from their owners: repeated canonical text/exact original image is rejected with a useful row result; existing records, review, groups and provenance remain unchanged. A retry must not be reported as a new creation or silently merge conflicting metadata. Do not add an idempotency registry unless a supported request-retry contract actually requires one.
- Prefer sequential bounded per-row work over uploading all image bytes in one request or introducing durable jobs. Cancellation stops scheduling new rows; disclose that an already admitted row may complete and remains in the collection. An aborted HTTP response is not proof of rollback. Reconcile ambiguous outcomes against stored acquisition identity before retrying.
- Bind image references to the explicitly selected local file set. Missing or ambiguous matches are row errors; never fall back to a server filesystem path or unrelated file. Current per-image 25 MiB / 40 megapixel and text 200,000-code-point limits remain; choose manifest/result bounds from the admitted format before implementation.

## Isolation and ownership

Task branch `feature/bulk-real-import-20261006`, isolated worktree `/workspace/Tuldok-bulk-import`, inherits the separate local queued-API repair `801d598a1400afdc2360128a1657896b89da10c4` and admission foundation `a16bba4b6473fdde88f97ab295f8563e0793cf5a`. PR4's branch stays at 801d598 locally; its last published head is a3f3cbe. No queued/provider or saved-selections implementation is duplicated here. Main/PR1–3 are unchanged by this worker. Parent owns integration/review/publication and provisional UI acceptance.

Exact retained authentication failures were `gh pr view 4 --json headRefOid,headRefName,baseRefName,isDraft,url --jq .` against `https://api.github.com/graphql`, and `gh api repos/MrScripty/Tuldok/actions/runs/37531676070/artifacts ...` against that REST endpoint; both HTTP 401 `Bad credentials`. These were inspection reads. Ordinary authenticated Git push succeeded earlier at a3f3cbe; no post-error push was attempted. Publication is held locally by instruction, not proven denied through every route. No denied call, credential repair or network change is retried.

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

Goal: native local manifest/file set → strict row decoding/file binding → atomic admission → visible partial results → draft records → separate annotation/review. Implemented and locally verified. Initial image enrollment already moved into Dataset's transaction/file-cleanup owner in its own foundation commit; bulk context shares that boundary.

Feature write set: `bulk_import.py`, `workbench.py`, `app.py` (composition/routes), `static/bulk_import.js`, `static/workbench.html`, `static/workbench.js` (shared original-image read helper only), `static/workbench.css`, `tests/test_bulk_import.py`, `tests/test_bulk_import_controller.cjs`, `tests/browser_bulk_import.cjs`, `.github/workflows/tests.yml`, `README.md`, this plan directory. Foundation's four tests/source remain in the prior commit. No existing selection/release/controller validator is changed; no unrelated provider work.

Gate: focused row/source tests, complete registered Python/controller/browser suites, syntax/compile/diff checks, real desktop/narrow browser import/cancel/retry/error results, exact new-head push/PR CI and parent-coordinated review. Publish a separate draft only after its own complete verification; never merge.

## Acceptance claims

| ID | Observable criterion | Evidence / environment / mode | Status |
| --- | --- | --- | --- |
| B1 | Mixed real text/images admitted through existing owners; originals/canonical forms and source metadata survive reopen | contract / real SQLite/filesystem / automated | passed locally: HTTP restart/originals and Chromium reload |
| B2 | Isolated malformed/partial invalid rows yield correctly attributed errors while valid rows succeed, without orphan files/partial record metadata | integration / real HTTP/SQLite/filesystem / automated | passed locally: invalid/partial rows and injected metadata/history/storage rollback |
| B3 | Duplicate/repeated submissions create no duplicate assets or implicit provenance/review changes; ambiguous response is reconciled honestly | contract / real persistence/HTTP / automated | passed locally: marker/content repeats, unchanged reviewed records, lost actual response + lookup without replay |
| B4 | Missing/ambiguous assets cannot bind unrelated bytes; unknown/forged fields cannot grant human review or verification | contract / real file/row binding / automated | passed locally: exact selected files, ambiguity/missing/damage, strict fields and draft state |
| B5 | Cancel before admission and between rows stops future scheduling; in-flight completion and retry remain visible and correct | user-workflow + integration / representative browser/HTTP / automated | passed locally: manifest/file-read barriers and actual in-flight acknowledgement |
| B6 | Actual bulk import, per-row recovery, repeated controls, editor fencing, progress/cancellation and narrow layout work through real Chromium | user-workflow / representative Chromium / automated and local screenshot inspection | passed locally: actual browser suite, desktop/390px screenshots inspected |
| B7 | Full registered regression suites and exact new-head hosted CI pass; separate draft and bounded review preserve main/PR1–4 | integration / local and GitHub / automated/review | local passed: 145 Python tests, three JS gates, seven browsers; hosted/review/draft pending |

## Exactly one next slice and re-plan triggers

The selected raw-asset slice is locally verified. Exactly one next slice: parent-coordinate review/integration/publication and exact new-head hosted qualification while preserving the separate queued repair and saved-selection work. Do not claim all publication routes were denied; only gh inspection returned 401. No denied authentication call or settings change is retried. Annotated corpus ingestion remains a later separately mapped feature. Replan for measured scale beyond bounded sequential imports, new annotation/coordinate contracts, durable restart-safe batch receipts or a stack-base change.

[Discovery](reports/discovery.md) · [Admission evidence](reports/admission-boundary.md) · [Ledger](execution-ledger.md) · [Issues](issues.md) · [Existing architecture decision](../../decisions/dataset-workbench.md)
