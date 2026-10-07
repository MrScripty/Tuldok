# Row-local declared metadata error repair

Independent PR15 review and local actual-HTTP regression confirmed these failures on `3cc85d40b88934148e72b53aa380b787d9a0c48e`:

- One otherwise bound classification record with `"\\ud800"` in nested declared provenance caused whole-request HTTP 400 from UTF-8 encoding, discarding later row results.
- The same bound provenance position with JSON number `1e999` decoded to infinity and caused whole-request HTTP 400 from strict JSON encoding, discarding later row results.
- With manifest/assets untouched, replacing only the first metadata physical line with `{"id": <5,000-digit integer>}` caused whole-request HTTP 400 from Python's unchanged 4,300-digit conversion limit, discarding later row results.

The three new actual-HTTP regressions failed on that source with the reported errors. The fix keeps strict encoding and converts expected errors at the narrow owning boundary: `_seal` reports Unicode or finite-JSON failures as WorkbenchError; `decode` reports expected decoder ValueError (including integer conversion limits) as WorkbenchError while preserving existing domain errors. Metadata callers report the bad row and retain later valid tokens. Manifest callers still reject the archive with HTTP 400. No catch-all, permissive encoder, runtime-limit changes, value substitution or admission/provenance/review-policy changes.

Four added actual-HTTP tests use real exporter-generated three-row ZIPs. The bound provenance fixtures alter only one historical value in both manifest and metadata, preserving record/asset/hash bindings. The integer metadata fixture verifies every manifest/asset byte is untouched. All prove zero database/history writes during preparation and explicit admission of only the two valid later rows as revision-1 drafts with matching measured acquisition identity. A manifest integer-limit fixture separately proves archive-fatal rejection and zero writes. The focused suite passes all 14 tests. All 27 complete local workflow gates also pass: 194 Python tests, five JavaScript syntax checks, seven controller/page-load gates and fourteen real Chromium suites.

## Tested source identities

- `native_text_import.py` SHA-256: `a4a4f7daf1a8e31faef1a02f5b52d6b83c8839614c1949b9fb0851998f8a071d`
- `tests/test_native_text_import.py` SHA-256: `f25882491db9bded14e0752009deb0862411832cc2039ecddb3ad5dfe0f95bfb`

Full lifecycle qualification and published successor identity are recorded in the PR15 description. Initial 3cc85d4 evidence remains historical in qualification.md; this repair adds four Python cases. The application/UI/signature/admission owners are otherwise unchanged. Main remains frozen and no manual CodeRabbit request is included.
