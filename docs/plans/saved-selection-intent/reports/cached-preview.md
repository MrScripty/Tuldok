# Known-stale cached preview repair

Original PR6 head `2311f7cd0eaaf6c6a89e259ddf5c340f3a9ca887` remains preserved.
Parent relayed independently reproduced CodeRabbit finding: eligible preview,
pending editor save, explicit Select page reselecting the same fixed pair, then
earlier editor response. Pair fencing works, but the identical selection key leaves
cached eligibility and Freeze enabled after the newer editor revision is known.

Deterministic regression fails against unchanged original production source:
`/tmp/tuldok-cached-preview-controller-before.log`. Real Chromium against archived
original source `/tmp/tuldok-pr6-2311f7c` reproduces actual state:

    selectedRevision=2, editorRevision=3, cachedEligible=true, freezeDisabled=false

Server preview rejects the old pair, accepts the current reviewed pair and rejects
stale export with HTTP 409. Thus the existing server boundary remains correct;
cached UI proof still needs immediate invalidation. Before browser evidence:
`/tmp/tuldok-cached-preview-browser-before.log`.

Successful editor completion now invalidates release proof if a retained selected
pair's record/source revision is older than the returned saved record. It does not
substitute that pair or assume ownership of later selection intent. A completion
older than a newer selected pair does not prove staleness and retains its proof.
No persistence, release validation, approval, API or Python production changes.

After repair real browser state is:

    selectedRevision=2, editorRevision=3, cachedEligible=null, freezeDisabled=true

Exact stale preview/export rejection and current-pair eligibility still pass.
Log: `/tmp/tuldok-cached-preview-browser-after.log`. All eight deterministic cases
pass, including the exact same-pair ordering and newer-proof positive control;
`/tmp/tuldok-cached-preview-controller-after.log`. Original six cases remain.

Full local qualification on Linux x86_64 / Python 3.12.14 / Node 24.19.0 / Pillow
12.3.0 / Chromium 151.0.7922.173: **141 Python tests in 33.228s**, all page-load and
controller checks, JS syntax/diff checks and all **eight real Chromium suites**:
workbench, grounded, captions, release preview, saved sets, saved-selection intent,
corner studio and controlled image generation. Logs:
`/tmp/tuldok-cached-preview-python.log`, `/tmp/tuldok-cached-preview-*.cjs.log`.
Only the extra deterministic positive control was added after full qualification;
all eight controller cases were then rerun. Production source is unchanged.

Repair appends on existing PR6 branch `fix/saved-selection-intent-20261006`; no new
repair PR, merge into main or history rewrite. Existing worktrees/component refs
remain protected except this authorized PR6 advance. Published head/tree and hosted
run/job receipts are recorded in the PR6 body. Parent owns review-thread disposition
and integration. The preserved provisional integration worktree will compose this
corrected head and the subsequent PR7 surrogate repair before full requalification.
No manual CodeRabbit request, credential/settings change, external model/dataset,
ONNX download or denied-log transfer retry/alternate route.
