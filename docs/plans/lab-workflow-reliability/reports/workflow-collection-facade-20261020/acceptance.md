# Current collection facade: paired cost and integrity

Frozen source `00d32f85229954aed93b333d4fbf89494631e7b5` completed the admitted
matrix with **36 pairs / 72 arms / 12 fresh processes**, with no failed or omitted
measurement. Production remains the exact `cd420c44` composition; the intervening
commits add only the stopped-transfer witness and this benchmark/admission.
The [evidence manifest](evidence-manifest.json) seals every raw sample, both pilot
and final matrices, environment/bookends, logs and derived cells. Every ratio,
including the one-item regressions, is retained.

The measured boundary is an actual `WorkflowClient.collect` or explicit
`collect_batch` call against authenticated local HTTP. It includes current complete
inventory correlation, transport/contract checks, whole-byte SHA256 verification,
private output write/fsync and atomic no-clobber publication. Each arm receives
the same exported exact manifest and a fresh destination. Imports, cold catalog
reopen, bootstrap and manifest export have separate setup observations. Fresh
directory creation, the independent local whole-byte oracle reread and directory
cleanup are outside each timed call. No producer or production policy changed.

## Paired results and scoped decision

Each cell has three fresh processes, with one first pair and two warm pairs per
process. The first-pair second arm follows its peer in the same process after
bootstrap/manifest export; neither arm claims OS/PG cache coldness. Ratios are
batch wall time divided by ordinary wall time **within each pair**. They are not
ratios of marginal medians.

| Exact source / inventory | History | First paired median, n=3 | Warm paired median, n=6 | All nine paired ratio range |
| --- | ---: | ---: | ---: | --- |
| Run, twenty 16 KiB files | 8 | 0.791959 | 0.806177 | 0.771067–0.838938 |
| Run, twenty 16 KiB files | 55 | 0.800143 | 0.804662 | 0.745422–0.841675 |
| Attached result Ref, twenty 16 KiB files | 56 | 0.796211 | 0.788530 | 0.763881–0.816569 |
| Run, one 320 KiB file | 8 | 2.166093 | 1.975566 | 1.719977–2.295047 |

All 27 twenty-item pairs had lower observed batch elapsed time; all 9 one-item
controls had higher batch elapsed time. This supports retaining the existing
**explicit** batch facade for the measured twenty-small-file selection. Ordinary
collection remains the default. No automatic item threshold, policy change or
claim for 2–19 items follows. These results advance this facade boundary's T5
evidence; they do not complete T5 or establish generic workflow/lab speedup.
Final acceptance remains subject to independent evidence review and lead integration.

Nine pairs per cell yield five ordinary-first and four batch-first pairs; first
pairs are two ordinary-first/one batch-first and warm pairs are three/three.
[derived-cells.json](derived-cells.json) retains every order/condition ratio and
its count. Both order strata retain the same observed direction in all four
cells. No sample or outlier was excluded, and no confidence or broad causal
claim is inferred from these small groups.

## Resources and request boundary

The marginal wall medians across all nine arms per method were 628.541/505.874 ms
ordinary/batch for Run history 8, 622.592/493.100 ms at history 55, and
1271.303/989.485 ms for the attached Ref. Their CPU medians were 584.682/476.058,
571.450/465.862 and 1200.137/922.978 ms respectively. These are descriptive marginal
medians; the paired table owns the comparison. One-item wall medians were
106.878/214.259 ms and CPU 103.650/205.873 ms.

Twenty-item facade calls use 21 versus 2 HTTP requests, including one current
inventory read in both arms; one-item calls use 2 in both. Canonical per-item
owner work remains: Run inventory/segment observations are 21/20 in each arm,
with Run loads 21 ordinary versus 23 batch. Attached Ref result/segment calls
are 21/20 in each arm, with Run loads 62/64. One-item Run loads are 2/4. No
authority check or per-item verification is removed by this test. Raw rows retain
every owner count/inclusive span, HTTP method/selected operation/status/body size,
wall, process CPU, RSS/HWM and `/proc`/resource I/O observation.

The Linux x86_64 environment has a 4-CPU cgroup quota and 16 GiB memory limit,
Python 3.12.14 and actual PostgreSQL 17.11. Start/end affinity/load/free-space and
source hashes are retained in both environment files. The quiet window had no
concurrent tests, PostgreSQL qualification, runtime installation or heavy local
qualification; the lead continued light source/prose/Git work and remote CI
metadata polling. This was not an exclusive host or zero-activity window.
CPU excludes PostgreSQL backend CPU; RSS/HWM are snapshots/lifetime readings,
I/O includes observer overhead and inclusive owner spans cannot be added into
independent phase totals. A per-process no-op calibration is retained.

## Integrity, preservation and remaining limits

All twelve worker receipts assert original Run document/events and admission/
grant/consumption/reservation counts unchanged, exact ordinary/batch/manifest
whole hashes and mode 0600 outputs, and zero compute-launch calls. The attached
Ref comes from one real neutral attempt with an original copy fault and explicit
same-Run publication recovery outside the measured read arms. The reused negative
tail retains expected changed-input/runtime-inventory/corrupt-payload/revocation
refusals; temporary input changes are restored. Installed runtime bytes are never
mutated, and this expected-inventory refusal is not actual installed-runtime
mutation proof.

The pilot contains two first pairs at histories 1/2 and four arms, both
ordinary-first. It passed integrity and cleanup before final-matrix admission;
its small samples are archived separately and are not pooled into final results.
Both final exact schemas and temporary directories were removed; pilot cleanup
is separately recorded. External start/finish namespace queries are empty and
the measured worktree is clean at the same head with identical named hashes.

No actual lab workload, training, CUDA, numerical validity, larger/remote payload,
other item count, preparation gain, cache or end-to-end improvement is qualified.
PUB-1 still lacks its original failure/custody/profile/output inventory; SCI-1
still lacks the real comparison pair, criterion authority and environment.

The same follow-up preserves two separate acceptance receipts without relabeling
them as performance evidence: [independent stopped-transfer review/run](../integrated-retention-restore-20261020/independent/review.json)
at source `322482d` (one test 16.994s), and [root current neutral HTTP/CLI qualification](../m5-workflow-client/current-integration-20261020/qualification.json)
at exact `cd420c44` (12 tests 97.352s unittest / 97.360587636s wrapper, zero skips).
The classifier case is explicitly excluded locally because no qualified Torch
runtime was selected; its hosted qualification remains separately lead-owned.
