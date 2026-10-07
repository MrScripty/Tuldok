# Selected lookup and streamed freshness repair

Validated findings: [CodeRabbit review 5436648695](https://github.com/MrScripty/Tuldok/pull/11#pullrequestreview-5436648695), source `f081f6174c19ba8256bc9915b59553a420da15b9`. Selected diagnostics called `_all()` under the shared Dataset lock; even one selected ID decoded every record and enrolled unrelated legacy images temporarily. Freshness hashing used `encode(facts).encode()`, materializing a JSON string and UTF-8 bytes for the complete scoped collection before SHA-256. Pagination did not bound this work. The plan's inventory reference pointed into the author's workspace.

Selected scope now resolves each validated requested ID directly. The existing `_sync_images` owner accepts an optional single-ID restriction; all existing unscoped callers retain their original behavior. Selected legacy enrollment and history remain inside the rollback-only diagnostic savepoint. Only the existing unavailable/404 record error becomes an explicit missing reference. Stale/deleted/missing reporting, contributor semantics and human-review separation remain unchanged.

Freshness hashing consumes `JSONEncoder.iterencode` chunks using the same Unicode, sorted-key, compact-separator and strict finite-number settings as `workbench.encode`. It hashes the same scope, normalized filters, ID-sorted requested references, ID-sorted full current rows and reference diagnostics. Category/page size/offset remain outside the token as before. Tokens match the previous canonical JSON bytes exactly. The largest serialized scalar still determines a chunk's size; filtered scope still reads its matching rows for complete analysis and contributor membership before pagination. This repair removes combined JSON serialization allocations; it does not claim constant memory for the entire report or move shared reads outside their lock.

Two new regressions failed on the unchanged reviewed source: unrelated selected-scope record decoding, and full 36-row freshness JSON serialization. All nine focused curation HTTP/SQL tests now pass. Instrumentation verifies selected legacy enrollment only, unchanged SQL/history/membership after success and exception, canonical filtered hash with Unicode, bounded individual hash writes, stale/missing selected canonical reference facts, reordered selection stability and unchanged token across category/page changes. No wall-time or peak-memory pass threshold, cache or new schema framework.

An independent controlled probe used the same 36 locally authored approximately 100k-character Unicode text records for old and new inspection:

| Observation | Reviewed source | Repair |
| --- | ---: | ---: |
| `_get` calls for one selected ID | 36 | 1 |
| Unrelated `_get` calls | 35 | 0 |
| Complete freshness JSON characters materialized | 3,626,591 | none |
| Largest hash input write (bytes) | 3,626,735 | 100,002 |
| Total hash input (bytes) | 3,626,735 | 3,626,735 |
| SHA-256 token | `e31b8b22bd95fe28d8f33b6d74f3cd9021a9435361ef405715e3cb4543aad0bf` | identical |

Traced peaks in this Unicode probe were 43,538,635 and 15,370,243 bytes respectively; these are informational observations, not acceptance thresholds. The parent's independent reproduction used a different fixture and reported 3,628,149 JSON characters and approximately 10.98 MB peak on the old source. Those values are separate evidence, not claimed as this probe's output.

Source SHA-256 identities:

| File | SHA-256 |
| --- | --- |
| `curation.py` | `fdb7e74574349674c4d5baeb5be68a72fcea72f80c240d7ae165408e5c18f5b5` |
| `workbench.py` | `f9b8481b5500827e626333b0ed078aa79efdd29383619685b49a28251e85892c` |
| `tests/test_curation.py` | `7a2746e0ef1198ebd0f3d61ea49dd49742295bfe8d676c263325eeb1f0d320e3` |

The plan links [the committed runtime inventory](runtime-inventory.json). No new model/runtime qualification is claimed. External evidence is retained under `/workspace/tuldok-owner-review/curation-scaling/`: red-baseline.log, focused.log, scaling-probe.json and full gate logs. Final source, hosted checkout identities and qualification are recorded in PR11 and publication.json after current gates finish. PR15 bootstrap work remains separate and preserved; main is frozen, with no merges or manual CodeRabbit requests.

All 27 registered current-target gates passed: 189 Python tests, five syntax checks, seven controller/page-load suites and fourteen complete real Chromium suites, including curation, caption import and the combined dataset-caption workflow. Existing production/UI/routes, workflow registration and caption/browser owners remain unchanged from f081f617. Regenerated artifacts are retained as external evidence and excluded from the successor commit.
