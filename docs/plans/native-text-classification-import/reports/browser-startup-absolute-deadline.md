# Absolute startup deadline repair

The timer-only helper published at `060343f6a6da5528c57883163b16a80e78e06e66` allowed an overdue polling callback to accept readiness before the overdue timeout callback ran. Independent review identified this boundary; the parent authorized a test-bootstrap-only successor on PR15.

The regression uses a real Node child with an IPC handshake confirming its 80 ms write timer is armed. The parent starts a 50 ms startup allowance with 10 ms polls and deliberately holds its event loop for 200 ms. It verifies that the independent child supplied the port file during the hold, then requires budget rejection and detached startup listeners. On the unchanged 060343f helper this failed with `Missing expected rejection`, proving late readiness was accepted. The red output is retained outside the repository at `/workspace/tuldok-owner-review/labeled-text-contract/absolute-deadline/red-baseline.log`.

The helper now computes `performance.now() + budgetMs` once, checks that monotonic absolute deadline at poll entry and immediately before success, and keeps the existing timeout to wake the waiter. No deadline extension, retry or product change. The maximum and default remain 60,000 ms. Existing controlled delayed readiness, budget exhaustion, exit/spawn failure, stale-file rejection and listener cleanup cases remain. Controlled readiness is only startup-policy evidence; full real browser suites establish browser behavior.

Only the startup helper and its controlled test changed among executable files. The browser caller, its diagnostics/cleanup and all eight product assertions are unchanged from 060343f. Native row-error repair and its fourteen HTTP tests are unchanged. The workflow still registers the same 28 gates, including fourteen real browser suites.

Source SHA-256 identities:

| File | SHA-256 |
| --- | --- |
| `tests/browser_startup.cjs` | `ba7e6c8817489ec6d41b994e57a4f01029e986d2475162fe3b5cc971e6ccf634` |
| `tests/test_browser_startup.cjs` | `7d2be37ce682f593407a890013b25268fc595f8cb80c42dd6edc9e2e97373e52` |
| `tests/browser_workbench.cjs` | `38157f073988581ac092eba3b0de430699efacd95269aa25f2ad797656a69192` |
| `native_text_import.py` | `a4a4f7daf1a8e31faef1a02f5b52d6b83c8839614c1949b9fb0851998f8a071d` |
| `tests/test_native_text_import.py` | `f25882491db9bded14e0752009deb0862411832cc2039ecddb3ad5dfe0f95bfb` |

The previous budget report and all historical CI runs remain source-bound evidence for their original commits. Current successor qualification and hosted checkout identities are recorded in PR15 and the external publication record after the full gates finish. No merge, main change, history rewrite or manual CodeRabbit request is authorized by this repair.

All 28 local workflow gates passed on these source blobs: 194 Python tests, five JavaScript syntax checks, eight controller/page-load/startup gates and fourteen complete real Chromium suites. The controlled fixture observed delayed readiness at 20,565 ms under the unchanged 60-second default; held-loop expiration, process failure, exhaustion, stale-file and listener-cleanup checks passed. Workbench lifecycle and native classification import/review/export/navigation passed in actual Chromium. Complete logs and generated screenshots are retained in the external `absolute-deadline/gates` and `absolute-deadline/artifacts` evidence directories.
