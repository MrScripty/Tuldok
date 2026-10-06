# Execution ledger

## 2026-10-06 — bounded discovery and independent admission checks

Inspected checked-in research synthesis, canonical/historical workflow plans and actual source/HTTP/browser acquisition owners. Created `feature/bulk-real-import-20261006` in `/workspace/Tuldok-bulk-import`, pinned to reviewed PR4 head `c88c3819207333b620e0cd8f391d11843d393757`, without editing PR4 or main.

Recommended native raw-asset JSONL plus explicitly selected local images. Existing plans do not choose an external format or annotated import normalization/binding. Asked for that specific design-changing choice; no parser, new API, persistence/job schema or bulk UI was invented.

Began independently supported verification of the existing admission authority: importer-supplied human/programmatic review and forged source-provenance fields cannot upgrade a new asset; repeated exact image/canonical-text import cannot overwrite existing reviewed target/groups/source facts. Full bulk row-error/missing-asset/cancellation/browser acceptance remains pending and is specified in the plan.

## 2026-10-06 — resumed local foundations after PR4 compatibility repairs

Completed the separately assigned PR4 queued-API rejection first as local commit `801d598a1400afdc2360128a1657896b89da10c4` (132 Python tests and six real browsers passed). Fast-forwarded this isolated bulk branch to that local head without rewriting history or touching remote refs; preserved all bulk discovery/tests. No GitHub authentication calls were retried.

Revisited the unresolved raw-versus-annotated source contract with one asynchronous input question; parser/API/UI decisions remain pending. Continued format-independent admission work. A real SQLite trigger rejecting image source-metadata enrollment reproduces a committed sample with original files despite import failure. Fixed the concrete boundary by passing validated initial enrollment through Dataset.add's existing lock/transaction and file cleanup, analogous to its generation-output linkage. Workbench retains groups, parents, rights, provenance and initial history ownership; no new normalizer/image store/schema is introduced. A second trigger rejects initial history after metadata update and proves the same complete rollback. Existing review-authority and repeated-admission tests remain.

Shared integration boundaries for the parallel saved-selections worker: this slice changes only `Dataset.add`'s keyword-only `enrollment` argument and Workbench's image `import_asset`/new private `_enroll_import` transaction hook, plus its own tests/plan. It does not change selection maps, collection query/filter/analysis, saved selection storage, release freshness, static UI, route names or annotation/review semantics. Future bulk UI/route edits must be coordinated separately before overlapping selection-controller work. Parent owns integration.

Full local qualification passed: 136 Python tests in 34.846 seconds, both controller/page-load gates, all six registered real Chromium suites, JavaScript syntax, Python compilation and diff checks. Preserve the admission foundation as a local commit on this separate branch. Source-contract input is still pending, so no manifest parser, batch route, bulk UI, file binding or cancellation capability is claimed. Remote publication and exact new-head hosted qualification remain blocked by the existing connection's previous HTTP 401, with no authentication retry.
