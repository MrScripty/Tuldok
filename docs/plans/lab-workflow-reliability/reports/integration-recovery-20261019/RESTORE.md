# Task recovery checkpoint

Clone the authorized repository checkpoint with normal configured GitHub authentication:

```sh
git clone --single-branch --branch checkpoint/lab-integration-20261019 https://github.com/MrScripty/Tuldok.git Tuldok-recovery
cd Tuldok-recovery
git fetch origin main docs/lab-workflow-reliability-plan
```

Verify every evidence file's size and SHA-256 against manifest.json before use.
This branch contains task-owned source and evidence, never credentials or catalogs.
Its historical parent76d3c6a is recovery history, not the current product base.
Read tuldok-updates-integration-acceptance-20261019.json and the latest receipts;
older pending snapshots and failed attempts remain preserved as history.

## Current integration state

Main is63f689ecace7bac2f20114efde53a9c6bc05a9ed after PR110. P1-P6 and E1-E4
were integrated earlier; PR89/90 and PR92-101 are also merged. The latest accepted
serial integrations are PR102,103,107,104,105,106,109,110. Each actual merged tree
was verified equal to its qualified source tree, with exact parents and main
readback. Do not replay completed merge operations or restart design work.

The remaining order is108 ->111 ->112. Recheck exact GitHub heads, check contexts
and actual merge state before any operation. Newest required contexts must pass;
older green duplicates cannot replace newer pending contexts. Known same-head
failures require disposition. Source/tree equality does not relabel the tested
history as a literal later-main checkout. Use tuldok-pending-108-111-112-activation.json.

| PR | Published head | Base | Remaining qualification |
| --- | --- | --- | --- |
|108|9f08427029d8b48c8f9b50927a1c835afb573276|main63f689ec|Fresh lifecycle; catalog/static-kit passed in snapshot|
|111|0ba4db01f04a77c262eb4b397f88849e9688b5ab|108head9f084270|Fresh lifecycle and captured-CPU gates|
|112|abbae728434fa0670478e12216a1d94603a97daf|111head0ba4db01|Fresh lifecycle; local caption qualification/review clear|

PR108's repair preserves the frozen canonical source authority and verifies its
pinned SDK paths instead of comparing them to evolving live SDK files. PR111's
repair checks the real denial status owner and cleared private DOM before an
explicit refresh. Original failures, narrow actual checks and independent reviews
are archived. Those checks do not replace fresh hosted runtime qualification.

PR112 fixes an observed caption-test dialog timing race using event-owned exact
confirm waits, bounded CDP/diagnostics and owned-child cleanup. The existing CI
entrypoint includes the deterministic regression. Its complete PostgreSQL/Chromium
journey passed with matching implementation-file hashes and exact fixture cleanup;
no product/workflow/assertion relaxation occurred. The receipt's source_commit is
the pre-commit base HEAD; exact modified-file hashes establish tested source and
match publishedabbae728. See caption-ci-repair-source/evidence/raw and the root and
independent reviews. Original hosted late-modal diagnosis remains a hypothesis.

Obsolete PR105 duplicate39349523584 is terminally cancelled. Its modal error and
full raw/decoded logs are retained; it is never counted as success. Newer same-head
primary39349557067 completed all170steps and remains its reviewed acceptance gate.
All current108/111 runtime jobs were preserved. No uncertain publication is pending.

## Restore and retire safely

Fetch each recorded feature branch, verify its exact recorded commit, then create
an isolated worktree. If already safely merged/deleted, fetch main and establish
recorded commit ancestry first. Do not substitute a later tree for an old source
receipt. After each predecessor merge, prove the old qualified base tree equals
current main and the prospective merge tree equals the reviewed source tree;
retarget the dependent before retiring the merged predecessor's task branch.
Keep111 until112 is retargeted. Preserve unmerged repair aliases and unrelated work.

Eighteen accepted task branches/worktrees were retired in three verified groups:
PR92-101,102/103/107,104/105/106/109/110. Terminal and independent postchecks record
exact removals. All other immediate pre-state records and original82protectedrefs,
96originalworktree records and91originalcommits remain preserved. All non-cache QA
bytes were remotely archived and recovery-verified before removal. The latest five
retirement postcheck's94localheads/108worktrees is a historical snapshot; PR112's
new task branch/worktree was created afterward. Do not delete original worktrees.
README67 and independent plan91 remain separate/unmerged. Plan91 remainsb446d9a
on docs/lab-workflow-reliability-plan. PR71 is historical documentation only.

## Evidence limits and missing inputs

The actual CPU classifier/correction/checkpoint/probe and fresh captured inference
gates are source-specific. Pending fresh gates remain pending. Scientific reader
fixtures use explicitly authored terminal arrays, never qualified physics.
PUB-1 still needs the original failed diagnostic bytes/path/profile/caps/receipt;
SCI-1 needs an owned qualified criterion and compatible real lab pair. Keep missing
criteria and measurements unknown. The actual runtime-byte-integrity observation
passed with cleanup proof; it establishes no full T5/preparation/performance gain.
No CUDA, live-model quality or scientific acceptance is inferred from these records.
