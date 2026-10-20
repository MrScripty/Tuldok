# Task recovery checkpoint

Clone the existing authorized repository branch:

```sh
git clone --single-branch --branch checkpoint/lab-integration-20261019 https://github.com/MrScripty/Tuldok.git Tuldok-recovery
cd Tuldok-recovery
git fetch origin docs/lab-workflow-reliability-plan
```

Use normal configured GitHub authentication. This checkpoint contains no credentials.
Verify every evidence file against `manifest.json` using SHA-256 before use.
The checkpoint originally branched from the historical PR89/90 dependency tree
`76d3c6a2ec46f36bb5dee5f2d40d1ddf4d017114`. That is historical recovery context,
not the current implementation base. PR89/90 and PR92–101 are now merged.
Main after PR101 is `8c9c0b07d90fd78657539cdcbcd23fbf289c4f95`; its tree exactly
matches the qualified PR101 source. Fetch current main and inspect the latest
`tuldok-updates-integration-acceptance-20261019.json` and source-specific receipts
before resuming. Continue the published pending implementation stack; do not
restart completed design or implementation from the historical source parent.
The independent PR91 plan remains at
`b446d9a19dbd553b80bf9f3af574b8b34ddbd5cb` on its own remote branch.

Remote PR and CI state may have advanced: recheck exact heads, results and merge
status before any publication or integration. Old failed or skipped gates are
not acceptance. Retain all unrelated branches/worktrees; their inventory here
is preservation evidence, not authority to modify or delete them.

## Restore the separately published M1 implementation

The manifest records the exact later implementation head and branch. Fetch the
recorded branch from the same repository, verify that the recorded commit is
present, and create the recovery worktree from that exact SHA. If the feature
branch was safely deleted after a merge, fetch main and establish the recorded
commit's ancestry there before using it. Do not substitute the latest tree for
the recorded source without reviewing its changes. This checkpoint and the
implementation/plan branches remain separate; fetching is not product merge
or acceptance. Check fresh CI and independent-review disposition after restore.

PR92–101 feature refs and their ten clean task worktrees were safely retired
after dependent PRs were retargeted. Their exact accepted commits remain on main;
`tuldok-task-merged-cleanup-terminal.json` records the heads, retained ref and
terminal disposition. Original refs/worktrees and unrelated aliases are protected.
PR102–111 remain active pending source-qualified CI and serial integration.
The latest ledger records the published browser-teardown correction at PR102
`aa7115a4`, whole-stack PR108 `de5a3a8c`, and retained-analysis PR111 `beead92d`.
Only five task browser cleanup fixtures changed; existing product behavior is
unchanged relative to each prior head. Local actual browser witnesses passed;
fresh hosted CI remains required. The real-runtime byte-integrity observation
passed with independent exact cleanup proof; it is not full T5 performance acceptance.
The original lab failure bytes and an owned scientific criterion/compatible lab
pair are still missing inputs; synthetic diagnostics do not satisfy those claims.
