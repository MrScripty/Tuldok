# Independent composition review

Reviewed source `be8c1b77c2b1743f4e68fa48cdd168249eca8a13`, tree
`57f7ba92c9fd2f7f329dfe85eb1daf78b596d2d8`, against base
`ae094770cfebc68b73d91bc163a0043a4ab117dc` in
`/workspace/Tuldok-caption-proposals-local`. Worktree remained clean after checks.
Read plan, source/diff, existing transport and persistence owners, Core/Router,
implementation/verification, persistence/IPC, architecture/contracts/concurrency,
and independent-oracle standards. No repository source/report modifications,
remote calls, browsers/full-suite execution, model downloads or dependencies.

## Findings

1. **P2: bind preparation to the bytes verified for the selected source**
   `caption_proposals.py:149` verifies canonical source bytes; `:181` later opens
   the path again. An external replacement between these operations can supply
   a different image, then restore the original before the worker's source check.
   `probes.py` injects only this timing: the selected source and captured/current
   hash are blue, the exact submitted JPEG's center is red `[254,0,0]`, and the
   job nevertheless completes and applies successfully. The receipt then links
   a proposal from different pixels to the original canonical image identity.
   Prepare from the same verified bytes/opened descriptor, and qualify this
   interleaving. Exact input-image evidence must match the selected source.

2. **P2: terminalize a failed thread launch and retain safe shutdown ownership**
   `caption_proposals.py:204-205` persists the preparing attempt before invoking
   `Thread.start`, with no failure disposition for the launch. Injecting the
   supported operational failure (`RuntimeError: cannot start thread`) leaves
   the attempt preparing and a nonstarted worker. Starting another attempt can
   complete, but the old attempt remains preparing and cancellation returns
   false. Immediate `Dataset.close` reaches `caption_proposals.py:286` and
   raises `cannot join thread before it is started`, preventing normal downstream
   resource cleanup. Terminalize the persisted attempt on launch failure,
   clear runtime active ownership, and make close join only started work. Add
   focused launch-failure/recovery/shutdown assertions.

## Evidence and limits

Executed all 15 existing caption proposal Python tests from `/tmp`, using
`PYTHONDONTWRITEBYTECODE=1` and explicit source/test import paths; all passed in
8.923 seconds (`focused-tests.log`). The cases use independent temporary SQLite
stores and local synthetic HTTP fixtures. Additional `probes.py` and
`shutdown-probe.py` are outside the repository; their exact observed outcomes
are `probes.json` and `shutdown-probe.json`. `git diff --check` passed. Review
confirmed same-lock/transaction application, revision and current-byte checks,
request-ID/apply idempotency, human review separation and separate target
evidence; no further concrete findings identified in those paths.

This review does not establish real-model caption quality, provider capability,
browser UX or aggregate qualification. Parent's independent interaction reviewer
and concurrently running aggregate suite own those evidence boundaries.
