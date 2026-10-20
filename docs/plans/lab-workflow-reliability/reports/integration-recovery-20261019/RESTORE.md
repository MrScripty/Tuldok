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

Main is c1fc60dbf2d96d3cb0ac0739a6822c6b3301f0ad after PR108. P1-P6 and E1-E4
were integrated earlier; PR89/90 and PR92-101 are also merged. The latest accepted
serial integrations are PR102,103,107,104,105,106,109,110,108. Each actual merged tree
was verified equal to its qualified source tree, with exact parents and main
readback. Do not replay completed merge operations or restart design work.

The remaining order is 111 ->112. Recheck exact GitHub heads, check contexts
and actual merge state before any operation. Newest required contexts must pass;
older green duplicates cannot replace newer pending contexts. Known same-head
failures require disposition. Source/tree equality does not relabel the tested
history as a literal later-main checkout. Use tuldok-pending-111-112-activation.json.

| PR | Published head | Base | Remaining qualification |
| --- | --- | --- | --- |
|111|29011daea37f101ee30be9bc10aab702a16c830a|main c1fc60db|Fresh lifecycle/CPU/catalog/UI gates pending|
|112|0dedbc953902ac89389dca0693006aaa02a0a87c|111head29011dae|Fresh lifecycle; both local repairs/reviews clear|

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

Latest04:18+update: PR1110ba4 lifecycle39360310903/job118424712559 failed
scientific-fields first Open project dialog wait atstep44. This differs from
the caption modal race. Fullfailurelogs/metadata and independent diagnosis are
retained. Both exact0ba4 captured-CPU jobs passed13/13 with independentreview;
that does not override failed/pending lifecycle. Minimal actualinitializer
readiness reproduction/repair is assigned separately before111/112republication.
PR108 late lifecycle remains independently separate.

Authoritative04:33+update: PR108passed172/172steps,1744tests/72skips andalllate
actualgates, independentlyreviewed; mergedtreef245dcc8 exactlyequalsqualifiedsource.
OptionalbrowserartifactZIP wasproxy403blocked anditscontentswerenotclaimedverified.
PR111twoold0ba4lifecyclesfailedsamefirstscientific Openproject59:77/64 wait.
AcontrolledrealPG/Chromium held-module reproductionprovesenabledcontrol/nullhandler
lostpointerclick; hosteventtraceitselfisabsent. Reviewedtwo-lineownerreadinessfix
29011dae passeddefaultentrypointwithnewstartupandall5originalscientificchecks.
Fouractualtestedfilehashesmatchthepublishedcommit;3exacttaskedschemasqueriedabsent.
Latebrowsercachecleanupisexplicitlydocumented,notanall-descendantguarantee.
Rootfast-forwarded111to29011daeandnormallymergeditinto1120dedbc95,verifiedboth
priorqualificationsfilehashesandfocusedregressions,andatomicallypublishedboth.
BothPRsaredrafts. FreshcurrentheadCIisrequired; oldCPU0ba4passesarenotnewheadpasses.
Old112abba lifecycle39364911305 isterminallycancelled; originaltwofailed111jobs
werenevercancelledormarkedsuccess. Allcorrectedcurrent-headjobsremainintact.
TenPR108repairQAfiles566599Barearchivedpendingrecoveryverification/precheck;
its2acceptedaliasesarestillretaineduntilsafecleanupcompletes.
