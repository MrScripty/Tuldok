# Local caption-proposal qualification

Qualified source `4267819af784f5094a5e5ac48d82f71eafbd0564`, tree `676726e711d7c980ba3a8135e076b45b5fda47b2`, base `ae094770cfebc68b73d91bc163a0043a4ab117dc`.
All 43 aggregate commands passed: all 40 inherited commands remain in order, plus
caption syntax/controller/browser gates. Python discovery passed 252 tests, including
17 caption tests. Nineteen browser workflow commands and the two additional rights
preservation reruns exercised 21 real Chromium invocations. Logs/source/results are
under `gates/`; exact source/test hashes are in `source-and-preservation.json`.

The new controlled local HTTP/Chromium flow sends actual image pixels, rejects a
listed text-only model's vision failure without fallback, recovers real lost start
and apply acknowledgements, applies one draft target with receipt, retains fixed
selection revisions and reports staleness, blocks draft caption export, then
explicitly reviews and consumes the actual downloaded ZIP with the unchanged
pinned caption validator. It also exercises reject, active cancel, editor navigation,
browser back/reload without inference replay, real keyboard entry and narrow layout.
Fresh screenshots, ZIP, consumer log and session receipt are under
`fresh-caption-output/run-sGlw1C/`. These are synthetic authored fixtures,
not a real model or external corpus. Original images/acquisition provenance stay
unchanged. Structural validation never grants review or establishes caption quality.

Focused Python tests cover atomic rollback/linkage, repeated/concurrent application,
request-ID reconciliation, malformed/truncated/oversized output, unknown/image-only/
text-only models, source deletion/missing/tampered bytes, stale source/target revisions,
inflight edits, catalog/body cancellation, late output fencing, shutdown/restart,
EXIF-normalized resize/input identity, request persistence failure and frozen target
evidence through explicit review/consumer export and later edits.

Initial source `be8c1b77` passed its 43 gates, but independent review reproduced two
P2 gaps: source path reopening and failed thread launch. Initial reviews/probes are
retained alongside successful successor probes and 17-test independent execution.
The repaired source prepares the same bounded verified canonical byte buffer;
launch failure persists a failed attempt and clears runtime ownership. UI/consumer
files are unchanged from the independently reviewed interaction source. No findings
remain on the qualified successor. Acceptance does not rely on the initial pass.

All 540 historical tracked report files remain byte-identical. Inherited
browser destinations can still write old report paths: the local gate runner copied
each changed or new artifact into `component-artifacts/gate-N/`, then restored historical
bytes after every gate. Rights-note and new caption outputs use fresh ignored paths;
their receipts/captures are retained separately. Manifests hash retained qualification
files; output path preservation is not a claim that other inherited writers changed.

No GitHub remote calls/publication, merges, manual review-thread actions, model/dataset
downloads, dependencies, credentials or network settings changed. Reused the existing
private CPU instruction-consumer environment for inherited instruction workflows;
no provisioning fallback ran. Main and all other local branch heads are preserved.
Real vision-runtime success, model semantic quality, backend compute cancellation,
final UI decisions and publication/acceptance by the parent remain outside these
local evidence claims. Full bounded complete response bytes are retained; an attempt
that fails during transport/size checking need not have a complete response payload.

Raw browser logs retain exact logger output, including trailing spaces. Source/docs
whitespace checks exclude retained raw reports; artifact hashes verify their bytes.
