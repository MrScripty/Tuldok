# Native text-classification import

Status: implemented and locally qualified; owner-authorized isolated candidate, no merge.
Base: `feature/image-caption-exports` at `3eb64667997701f98f27befa70669f9ae8405265`.
Branch: `feature/labeled-text-import-20261007`; main and PR13 are protected.

## Source contract and provenance boundary

Use the existing `canonical_v1` ZIP produced by `dataset_releases.py`, not a new JSONL format. A locally generated release at the exact base has manifest schema_version 1, manifest records, train/validation/test records.jsonl and assets/<32-hex-id>.txt. The fixture ZIP SHA-256 is `0947057f8e395b9c03608cb3a25e5bfaa0110c7cbdd50c390c112db5f650b5c2`. Its classification row includes text, annotation.label, groups, provenance and declared original hash. The JSONL row equals the manifest row and the asset equals UTF-8 text. All three omit the upstream pre-normalization original.

Owner explicitly admitted consuming exported canonical text as the NEW import input, preserving it exactly, with canonical normalization owned by Workbench. Upstream original reconstruction is unsupported. Never use incoming source_sha256 as the new measured input hash. The existing provenance JSON owner needs no schema expansion: measured archive/manifest/metadata/row/asset/input hashes live in acquisition; incoming origin identity, review, rights and provenance live only under acquisition.declared.upstream with original_status=unavailable. Local rights start unknown; foreign review never grants approval.

Preparation reads one explicitly chosen native ZIP, measures archive bytes, verifies exact native manifest fields/schema and exact physical JSONL-row/manifest/asset bindings. No ZIP extraction or server paths. Unsupported task/kind, malformed rows, missing assets, hash/binding conflicts are individual rejections; valid rows remain admissible. Broken manifest, ambiguous ZIP names, unsupported version and transport bounds reject preparation without writes. Limits: 8 MiB ZIP, 16 MiB aggregate expanded bytes, 1,000 manifest records and combined physical metadata lines, 3 MiB per row, at most 2,000 outcomes including unmatched manifest records, existing text and group limits. Stored ZIP entries only, matching this native producer; no third-party archive compatibility.

Process-local signed envelopes carry validated row input and measured context without a job table or source cache. Restart invalidates preparation; committed receipts persist and remain discoverable. Admission uses the existing lock/transaction and _insert_text(annotation=...), creates new ID/revision 1/draft/history atomically and rejects existing canonical text or request markers without overwrites. Imported groups retain exact native groups plus stable origin-ID/parent links to preserve declared family connections; foreign IDs are not local parents. Reject group overflow, never truncate. Active source splits remain unassigned.

## Write set and concurrent integration

New native_text_import.py, static/native_text_import.js and focused tests; narrow app.py composition/routes/static mapping; one dedicated native-text-* panel in static/workbench.html; README, this plan/reports and CI registration. No instruction task/validator/editor/export changes; no synthetic.py/image_generation.py, release owner or saved-selection changes. Shared touchpoints are app.py, workbench.html and tests.yml; instruction worker owns a separate module/panel/routes. Parent coordinates integration; no main mutation, merges or manual CodeRabbit requests.

## Acceptance

Real native export fixture -> HTTP prepare -> row admission -> restart -> explicit human review -> exact saved selection -> preflight -> frozen ZIP, inspecting actual text/label/groups/provenance and draft barriers. Verify strict source/version bindings, malformed/unsupported rows and duplicates with later success, per-record rollback, repeated markers and response loss reconciled read-only without replay. Controller and real Chromium qualify Stop during source read/preparation/in-flight response, repeated clicks, file snapshot, filters/dirty editor/exact membership, delayed refresh and browser reload/navigation. All 27 local gates passed; see reports/qualification.md. Run candidate CI against current development; preserve PR13 head and report any pre-existing base gate failure without changing its repair.

## Independent review repair: declared metadata row errors

PR15 review reproduced whole-request HTTP 400 at source `3cc85d40b88934148e72b53aa380b787d9a0c48e` for a bound classification row containing an escaped lone surrogate or exponent-overflow (`1e999`) in historical provenance. A first metadata line with a 5,000-digit integer also escaped the decoder's expected-error conversion. Later valid rows were consequently lost despite zero preparation writes.

Keep the existing strict JSON/Unicode owners. Convert expected serializer Unicode/finite-value failures into WorkbenchError inside _seal, and expected decoder ValueError (including Python's existing integer limit) into WorkbenchError inside decode, preserving existing domain errors. The caller still owns scope: metadata failures are individual row outcomes; manifest/ZIP/version integrity failures remain fatal. No catch-all, value repair, permissive JSON encoding or changed runtime limits. No admission, provenance, UI, signature or review policy change.

Actual-HTTP regressions start from exporter-generated three-row archives, prove the three failures on the prior source, verify rejected rows have no tokens and later rows do, compare the unchanged database before admission, and commit only valid rows as new drafts/history. The integer case leaves manifest and assets byte-identical; a separate manifest integer-limit case retains archive-fatal rejection. Qualification: reports/provenance-row-errors.md.
