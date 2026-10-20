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
Main after PR107 is `18a53816a279ad56758de620c9a1c4b129ba84ce`. PR102,
PR103 and PR107 are accepted and merged; each resulting tree exactly matches
its independently reviewed source/CI tree. Fetch current main and inspect the latest
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
PR104,105,106,109,110,108,111 remain in that serial order. PR104 is retargeted
to current main; its lifecycle acceptance remains pending. The latest ledger
records PR108 `9f084270` and retained-analysis PR111 `0ba4db01`: narrowly repaired
test oracles with product code and frozen source authorities preserved. Original
failures, actual CPU browser/targeted checks, independent reviews and publication
receipts are retained. Fresh exact-head CI is required before their merge.
PR102/103/107 task refs and their three worktrees are now removed after all
dependents were retargeted. Consult the terminal and independent postcheck records;
all other immediate pre-state records and original82 refs/96 worktrees/91 original
commit reachability are preserved. All16 non-cache task QA artifacts were remotely
archived and recovery-verified before removal. The real-runtime byte-integrity observation passed with exact
cleanup proof; it is not full T5 performance acceptance.
The original lab failure bytes and an owned scientific criterion/compatible lab
pair are still missing inputs; synthetic diagnostics do not satisfy those claims.

Final serial merge preparation and exact-source reviews for104/105/106/109/110
are recorded in `tuldok-remaining-serial-merge-preparation.json`. Activate each
only after the predecessor merge, with a fresh current-main/base/tree proof.
PR104 latest lifecycle is still pending at the recorded03:05 snapshot;
the independent merge-gate review explicitly grants no clearance while pending.
Current PR descriptions have been rewritten around final behavior and evidence.

PR104/105/106/109/110 have now been accepted and merged serially. Current main
is63f689ecace7bac2f20114efde53a9c6bc05a9ed, with every actual merge tree
verified equal to its qualified source. Their final merge receipts supersede
older pending snapshots. PR108 is retargeted to main; its source remains9f084270.
PR111 remains0ba4db01 based on108. Fresh repaired-head qualification is still
pending. Do not replay completed merge operations. Five accepted worktrees
remain pending safe retirement;72 non-cache QA files are archived with exact
size/SHA inventory, requiring recovery verification and independent precheck.

Five accepted PR104/105/106/109/110 task refs and worktrees are now safely
retired after PR108 retarget, remote archive verification and independent
precheck. Terminal/postcheck records supersede older pending cleanup snapshots.
Every other local ref/worktree and original protected inventory is preserved.
Only PR108 then PR111 remain in this implementation stack, pending exact-head
hosted qualification. Their source worktrees and repair aliases are retained.

Obsolete PR105 duplicate39349523584 is terminally cancelled after independent
review; completed same-head primary39349557067 remains its acceptance gate.
Original cancelled logs and modal-error observation are retained without success
reclassification. A narrowly scoped caption-dialog CI repair is now being
implemented in its own branch AFTER111; see caption_dialog_ci_repair in the
latest ledger. Keep111branch until this new dependent is retargeted.
