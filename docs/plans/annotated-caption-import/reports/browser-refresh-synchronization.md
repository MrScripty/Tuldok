# Native caption browser synchronization repair

The failed PR3 browser check read SQLite before its ordinary collection refresh
had enrolled the retained corner-studio image. This is a test synchronization
defect, not a duplicate-admission or persistence defect.

## Exact failure and retained evidence

[PR run 37548531463](https://github.com/MrScripty/Tuldok/actions/runs/37548531463),
attempt 1, job `112558254483`, failed step 26 at the final legacy-enrollment
assertion in `tests/browser_caption_import.cjs`. It checked head
`3eb64667997701f98f27befa70669f9ae8405265` through synthetic merge
`36402881a6238d11f45b31642fb2cf33003e196d`; both have exact tree
`84254d196c5a2e20f8884c290c923849e0c4dbca`. Python, syntax, controllers and all
preceding browser gates passed. Three later browser suites were skipped. The
green development push `37548526998` is separate evidence; it does not replace
the failed PR check.

Supported job-log and artifact downloads succeeded. Original run/attempt and
artifact `11451453158` remain unchanged; no blind rerun was requested. The ZIP's
SHA-256 is `01b93d9018d39f2c199ccf49a0964a16be5bece249f38278086c74436662e741`.
Its 33 entries include 18 fresh or uncommitted test outputs and 15 byte-identical
historical combined-caption images/receipt. The skipped combined suite did not
create new combined-caption evidence. Browser logs identify Chrome154.0.8037.57
and no page runtime exceptions. The downloaded four-record caption ZIP had
already passed the unchanged pinned consumer before the final assertion failed.

## Concrete cause and focused proof

The caption controller's `finally` first sets `captionRunning=false` and
re-enables Start, then awaits `bulkRefresh()`. The browser test's `idle()` checks
only Start's disabled state. It therefore cannot establish that the independent
collection request has reached the server, enrolled the retained original or
rendered its row. The failed counts were one source sample and zero workbench
records/history; the test prematurely expected one of each.

A baseline test copy with only the real collection request held before dispatch
reproduces the same final assertion and exact SQL counts. Admission still
returns HTTP409 for identical pixels, rolls its lazy enrollment back and creates
no second source directory. This controlled latency reproducer uses the actual
application, HTTP, SQLite, PNG bytes and Chromium, rather than a replacement DOM.

The revised test keeps that pre-dispatch hold as a deterministic regression.
After caption controls become idle it proves metadata/history are still absent.
It then releases the one real collection refresh and waits for the retained
sample ID and its rendered row before the original final SQLite assertion.
No extra metadata query forces enrollment. All original duplicate, rollback,
stop, draft, export and persistence assertions remain intact. The original
150 polls at 100 ms remain unchanged; no sleep or timeout extension is added.
The focused revised browser test passes with the refresh deliberately held.

## Review boundary

This candidate is based directly on development merge `3eb6466` in isolated
branch `fix/caption-browser-sync-20261006`. Executable changes are confined to
the existing browser test. Application/controller, schema, import, source,
release, selection and generation contracts remain unchanged. Curation and
rights-correction successor branches are not incorporated. Main and development
branches stay preserved; no merge/adoption or CodeRabbit request is authorized
by this test-only candidate. Full local and new candidate CI results are reported
separately, with exact source identity. All data/providers remain controlled,
locally authored fixtures; no real-model qualification is claimed.

## Local candidate qualification

All 24 registered workflow gates passed: 180 Python tests in 50.222 seconds,
four static syntax gates, six controller/page-load gates and all 13 real Chromium
suites. The changed browser test also passes `node --check`; it passed once in
focused verification and again in the full suite with the refresh deliberately
held. The baseline controlled copy fails the exact old final SQL assertion.

Test SHA-256: `43a38a488f4998350a91fb20775aca9b25b0017508435ae2e7dc9c49c03ecac3`.
All 77 other tracked executable/configuration files match the development base.
The original 48 assertions remain; one additional assertion checks the held
refresh boundary. Existing committed fixture and screenshot evidence is retained.
Generated local captures and terminal logs are preserved outside the repository.
Environment: Python3.12.14, Node24.19.0, Chromium151.0.7922.173. New candidate
hosted qualification is separate from the original failed PR3 run.
