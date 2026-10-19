# Refined bounded collection measurements — 9838022

Explicit batch collection is faster in all 27 measured twenty-artifact pairs. Median paired batch/individual wall ratios are 0.700 for a completed Run at history 8, 0.695 at history 55 and 0.710 for an attached recovered-publication Ref at total history 56. All one-artifact cells regress. These data support retaining the bounded operation for explicit twenty-item collection in this neutral small-output fixture; they do not justify automatic selection, an assumed threshold for 2–19 items, cross-call caches or a general workflow/science speedup.

Exact measured source: `98380228a7edb8eefb4715cba27ca76722756cf9`. It normally composes whole root source 0e7b3cb/current M5/M6 ancestry and the independently reviewed Runs refinement 9a6e853. Both arms use the same canonical request-aware AgentClient. This measures the collection boundary; the separately owned WorkflowClient batch facade and end-to-end workflows are not the measured arms. The historical raw `production_base` field records admission ancestry 2d8b7d7, not equality with that base or producer 007. Start/end eight-owner and both harness fingerprints match.

The complete fixed matrix exited 0: 24 fresh application processes, six unavailable empty-history controls, 18 eligible processes, 54 pairs and 108 collection arms. Each eligible cell has three first pairs and six warm pairs. Histories 8/55 contain genuine completed neutral byte-copy Runs. Attached-Ref history 56 contains55 completed plus the original interrupted Run. Each arm collects 327,680 raw bytes in one or twenty artifacts, with exact inventory/whole-hash equality within each layout. Deterministic contents differ between layouts. Order alternates (five individual-first/four batch-first per cell); a first pair's second arm follows the first in that process.

Bootstrap, population, retained proof and actual same-Run copy recovery are separate observations, excluded from collection pairs. All counts of Runs/grants/consumptions/reservations and original events remain unchanged during paired reads. A launch tripwire prohibits compute during reads. Both exact fresh schema/temporary-directory cleanup checks passed. Negative tails retain changed-input/expected-inventory, changed-payload, partial-selection and revoked-inspection refusals; installed-runtime mutation remains unavailable, with expected-inventory mismatch the narrower witness. No samples or outliers were filtered.

## Paired wall distributions

Delta is batch minus individual. Ratios are computed within each pair before summarizing, not by dividing independent medians. P90 is nearest rank. Full pooled and arm-order strata are also retained in `qualified-pairs.json`.

| Source | Items | Total history | Condition | n | Faster pairs | Ratio min / median / p90 / max | Delta ms min / median / p90 / max |
|---|---:|---:|---|---:|---:|---|---|
| publication | 1 | 56 | first_pair_fresh_process | 3 | 0 | 1.536 / 1.657 / 2.389 / 2.389 | 171.543 / 226.144 / 438.606 / 438.606 |
| publication | 1 | 56 | warm_pair_same_process | 6 | 0 | 1.771 / 2.138 / 2.314 / 2.314 | 227.345 / 252.559 / 413.193 / 413.193 |
| publication | 20 | 56 | first_pair_fresh_process | 3 | 3 | 0.674 / 0.710 / 0.742 / 0.742 | -983.359 / -861.958 / -800.560 / -800.560 |
| publication | 20 | 56 | warm_pair_same_process | 6 | 6 | 0.683 / 0.712 / 0.820 / 0.820 | -930.129 / -836.054 / -618.507 / -618.507 |
| run | 1 | 8 | first_pair_fresh_process | 3 | 0 | 2.315 / 2.667 / 3.036 / 3.036 | 240.695 / 337.075 / 343.689 / 343.689 |
| run | 1 | 8 | warm_pair_same_process | 6 | 0 | 2.310 / 2.843 / 3.512 / 3.512 | 222.297 / 282.473 / 425.830 / 425.830 |
| run | 1 | 55 | first_pair_fresh_process | 3 | 0 | 1.939 / 2.016 / 2.855 / 2.855 | 188.440 / 199.864 / 395.602 / 395.602 |
| run | 1 | 55 | warm_pair_same_process | 6 | 0 | 2.293 / 2.612 / 2.951 / 2.951 | 222.656 / 234.971 / 401.296 / 401.296 |
| run | 20 | 8 | first_pair_fresh_process | 3 | 3 | 0.700 / 0.714 / 0.731 / 0.731 | -507.589 / -416.073 / -389.441 / -389.441 |
| run | 20 | 8 | warm_pair_same_process | 6 | 6 | 0.498 / 0.662 / 0.821 / 0.821 | -1207.534 / -491.289 / -257.655 / -257.655 |
| run | 20 | 55 | first_pair_fresh_process | 3 | 3 | 0.656 / 0.700 / 0.703 / 0.703 | -526.399 / -508.008 / -452.873 / -452.873 |
| run | 20 | 55 | warm_pair_same_process | 6 | 6 | 0.575 / 0.649 / 0.736 / 0.736 | -694.918 / -518.005 / -346.616 / -346.616 |

## Pooled descriptive owner/resource costs

Each row pools nine arms for a compact resource description; first/warm and arm-order distributions remain in JSON. Do not add inclusive owner spans. CPU includes app/HTTP/client and waited children, excluding PostgreSQL backend CPU. Actual SQL-command counts were not instrumented; Run-load counts are owner observations, not SQL-count claims.

| Source | Items | History | Arm | Median wall ms | Median CPU ms | Requests | Response body bytes | Run loads | RSS after KiB | Logical read chars | Physical read bytes |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| publication | 1 | 56 | batch | 522.3 | 504.6 | 1 | 438441 | 5 | 66008 | 332817 | 0 |
| publication | 1 | 56 | individual | 294.9 | 281.8 | 1 | 437835 | 3 | 66004 | 332817 | 0 |
| publication | 20 | 56 | batch | 2033.7 | 1911.7 | 1 | 466753 | 62 | 66816 | 584792 | 0 |
| publication | 20 | 56 | individual | 2966.1 | 2763.4 | 20 | 455440 | 60 | 66264 | 584792 | 0 |
| run | 1 | 8 | batch | 455.4 | 437.2 | 1 | 437478 | 3 | 66088 | 330128 | 0 |
| run | 1 | 8 | individual | 168.8 | 161.5 | 1 | 437332 | 1 | 66088 | 330128 | 0 |
| run | 1 | 55 | batch | 394.8 | 380.6 | 1 | 437478 | 3 | 65964 | 330128 | 0 |
| run | 1 | 55 | individual | 196.6 | 193.2 | 1 | 437332 | 1 | 65964 | 330128 | 0 |
| run | 20 | 8 | batch | 1038.0 | 973.8 | 1 | 447493 | 22 | 64804 | 417052 | 0 |
| run | 20 | 8 | individual | 1454.0 | 1351.9 | 20 | 445380 | 20 | 64912 | 417052 | 0 |
| run | 20 | 55 | batch | 968.2 | 909.6 | 1 | 447493 | 22 | 66096 | 417053 | 0 |
| run | 20 | 55 | individual | 1531.6 | 1412.0 | 20 | 445380 | 20 | 65556 | 417053 | 0 |

For this simple ordinary source, twenty items retain 20 initial canonical reads/inventory checks. Loads are 20 individual versus 22 batch (N+2U, U=1); requests are 20 versus 1. Publication canonical readers retain their original subloads: 60 individual versus 62 batch in this fixture. Every item still has its initial canonical authorization/retained proof. Domain and HTTP final stages independently reload current exact-source authority/attachment in last-occurrence order. No proof/loaded Run survives between stages or calls. The prior99741e5 full matrix is preserved separately as a negative result; cross-head comparisons are not a controlled estimate of refinement contribution.

## Qualification and limits

The independent source reviewer passed all 10 current pure cases, including 122 prior full contracts. The expanded16-case module ran 41.111s with 15 passes and one new test-harness error after shutdown already returned HTTP 409 with no items. Only its assertion was corrected to the established top-level error code; the affected actual case then passed 1/6.439s with no production change. Both logs remain under `../refinement/`. Actual cases cover N+2U load trace, A/B/A source loss at domain and post-serialization delivery, duplicate late revocation/shutdown, mixed exact Ref/Run partial errors, unchanged events/accounting and legacy failure gates. No hosted acceptance is claimed.

Python 3.12.14, task-owned PostgreSQL 17.6, cgroup 4 CPU-equivalents / 16 GiB. All known heavy gates reported complete before this coordinated window; small pure checks were permitted, and this is not an exclusive host. Per-arm UTC starts were not recorded. No OS/PostgreSQL cache flush; RSS and lifetime HWM are snapshots rather than phase peaks. `/proc` I/O includes observers. HTTP byte counts cover declared bodies rather than headers. Raw process CPU/RSS/I/O, owner counters/times, request/body counts and source/environment receipts are retained.

These n=3 first / n=6 warm distributions are descriptive, without confidence intervals or latency-budget acceptance. Performance for 2–19 items, other byte sizes, transitive Run graphs, scientific outputs, network deployments and CUDA is unmeasured here. No cache, automatic fallback, replay, import, promotion or numerical/scientific claim follows. The baseline/runtime/history costs remain separate; this scoped result does not complete all T5 or M4 acceptance.

The parent independently queried both exact matrix schemas after cleanup and found them absent. `parent-cleanup-independent.json` retains those two `m4_refined` rows plus two separately scoped `indexed` rows, which are outside this matrix.
