# Frozen neutral workflow baseline results

Production: `96c2adebc3a46b9fe92b179097474e08474689c3`. Measurement/harness commit: `83d7e8f52df92d10d3ff85709da6eff3231a0b06`. No candidate or optimization was implemented. The final matrix exited 0; all eight recorded fresh schemas and owned temporary directories were removed. Initial failed pilot 01 may retain an unknown small schema; it was not guessed or deleted.

The matrix contains 18 fresh sequential application processes, 3 cycles each (54 preparation/capture cycles), 6 history/layout cells, and 6 separately fresh-catalog workflows. First-call cells have n=3; warm cells have n=6. The six fresh-catalog workflows have n=3 per layout. Aggregate output is 327,680 bytes in each layout; each layout has distinct deterministic input bytes/recipe declaration and its own material identity. Exact identity is required within each layout/process/history, not across layouts.

All table wall times are milliseconds, shown as median [min, max]. The full 281 groups, every n, min/median/nearest-rank p90/max, CPU/RSS/I/O/request/body summaries are in [qualified-distributions.json](qualified-distributions.json); individual observations and inclusive owner counters/spans remain in [frozen raw cells](frozen-83d7e8f/raw). Small samples are descriptive, without confidence or latency-budget claims.

The raw built-in summary is preserved unchanged. Qualified reporting mechanically prefixes each condition with its filename-defined cohort, preventing the initial population workflow from being pooled with the three fresh-catalog workflows. No outcome-based filtering is applied.

## Preparation and capture

Empty-history samples isolate repeated preparation from growing terminal history. Runtime identity is freshly checked every time; warm means full same-process reverification. The held-prepared helper column excludes the prerequisite preparation and current admission/launch checks; it is no cross-call cache or end-to-end improvement.

| Artifacts | Condition | n | Prepare | Full capture | Held-prepared capture | Prepare CPU ms | Prepare logical read chars | Physical read bytes |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | first call | 3 | 446.0 [369.5, 471.3] | 414.3 [400.1, 512.9] | 13.5 [13.3, 21.3] | 441.3 | 64656835 | 0 |
| 1 | warm reverification | 6 | 428.6 [343.8, 833.5] | 551.1 [387.2, 638.0] | 20.2 [14.6, 26.1] | 426.2 | 64656840 | 0 |
| 20 | first call | 3 | 418.3 [401.0, 455.7] | 429.2 [381.5, 440.2] | 14.3 [14.0, 15.7] | 408.8 | 64658241 | 0 |
| 20 | warm reverification | 6 | 412.7 [360.8, 520.6] | 467.2 [375.2, 612.1] | 17.5 [12.0, 30.2] | 409.9 | 64658246 | 0 |

All 54 preparations hash a current 1,315-file/64,063,492-byte system-Python runtime closure. Total `recipe_contract.file_digest` input is 64,728,371 bytes in the one-artifact layout and the same in the twenty-artifact layout; both are recorded per observation; these counters cover that helper, not every hashing/read operation. Runtime identity occupies a median 93.6% of inclusive preparation wall time across 54 observations. The retained source-proof metadata reader is much smaller: n=36, median 0.402 ms; it does not verify all payload bytes.

## Terminal-history reads

Every history entry is a real completed neutral Run. No active or queued workload is present in these cells. HTTP includes serialization/transport/client contract validation; the difference from the direct owner call is not attributed to a specific subcomponent without profiling.

| Artifacts | Completed history | Owner list first | HTTP list first | HTTP list warm | HTTP first CPU ms | Body bytes | HTTP RSS after KiB |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 0 | 1.5 [1.0, 1.6] | 20.2 [18.8, 26.1] | 20.4 [19.6, 44.5] | 15.8 | 2 | 68972 |
| 1 | 8 | 297.6 [292.2, 327.3] | 665.3 [662.2, 665.6] | 652.1 [637.7, 699.1] | 647.1 | 1584113 | 88712 |
| 1 | 55 | 1963.0 [1799.0, 2013.4] | 4391.9 [4352.2, 4572.2] | 4319.0 [4145.8, 4723.5] | 4285.8 | 10890771 | 186940 |
| 20 | 0 | 1.4 [1.1, 2.0] | 29.5 [21.4, 38.9] | 23.6 [17.9, 28.5] | 19.6 | 2 | 69104 |
| 20 | 8 | 299.5 [286.9, 336.5] | 660.5 [655.3, 741.0] | 644.5 [619.7, 702.1] | 638.2 | 1636265 | 89092 |
| 20 | 55 | 2566.0 [2537.6, 2632.0] | 5371.7 [5367.1, 6429.2] | 4785.3 [4612.7, 5286.0] | 5236.2 | 11249316 | 190284 |

## Individual collection at 55 completed Runs

Both modes finish by verifying each complete artifact SHA256. Default mode permits 8 MiB per segment; the deliberately small mode permits 16 KiB. For twenty 16 KiB artifacts both modes naturally issue twenty requests. Body bytes exclude headers. These layouts are baseline topology comparisons, not paired candidate runs.

| Artifacts | Mode | Condition | n | Wall ms | CPU ms | Requests | Body bytes |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| 1 | default whole verification | first call | 3 | 172.1 [142.4, 173.2] | 167.0 | 1 | 437332 |
| 1 | default whole verification | warm | 6 | 169.5 [147.5, 216.7] | 166.1 | 1 | 437332 |
| 1 | 16KiB segments | first call | 3 | 1492.6 [1475.3, 1567.1] | 1411.3 | 20 | 445522 |
| 1 | 16KiB segments | warm | 6 | 1590.2 [1487.5, 1847.3] | 1475.0 | 20 | 445522 |
| 20 | default whole verification | first call | 3 | 1715.3 [1630.8, 1880.8] | 1579.0 | 20 | 445380 |
| 20 | default whole verification | warm | 6 | 1713.1 [1529.1, 1855.0] | 1553.8 | 20 | 445380 |
| 20 | 16KiB segments | first call | 3 | 2158.2 [1595.2, 2638.1] | 2015.8 | 20 | 445380 |
| 20 | 16KiB segments | warm | 6 | 1739.5 [1457.5, 2629.7] | 1609.0 | 20 | 445380 |

## Fresh process and supported workflow boundaries

Fresh-process imports/reopen/bootstrap are measured separately. Bootstrap always uses 3 requests and 555,015 response body bytes. Fresh-process does not mean OS/PG cache cold.

| Artifacts | History | n | Imports | Catalog reopen | Agent bootstrap |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 0 | 3 | 932.2 [836.7, 940.7] | 138.9 [137.3, 152.3] | 6724.0 [5794.0, 7064.5] |
| 1 | 8 | 3 | 919.0 [907.6, 1178.8] | 391.5 [356.5, 601.5] | 6648.7 [6160.3, 6891.9] |
| 1 | 55 | 3 | 995.0 [868.0, 1017.8] | 1637.5 [1632.0, 2102.3] | 6662.4 [5884.9, 6757.8] |
| 20 | 0 | 3 | 891.6 [872.5, 1001.7] | 146.1 [141.0, 148.7] | 6997.9 [6226.4, 7022.1] |
| 20 | 8 | 3 | 1000.2 [825.0, 1158.9] | 413.7 [381.1, 437.5] | 7252.5 [6173.6, 7277.3] |
| 20 | 55 | 3 | 1090.2 [1013.4, 1807.4] | 2017.3 [1977.2, 2225.7] | 8439.3 [7957.3, 10004.7] |

The following routine workflow begins after explicit Project/Graph setup and client bootstrap. It covers actual preflight, owner grant, agent submit, real queue completion and whole-hash individual collection. Each sample uses a newly created catalog, already warm application imports and zero starting history; setup/bootstrap are excluded and separately retained. Polling cadence is 50 ms. The real recipe only copies bytes; no numerical training is performed.

| Artifacts | n | Workflow wall ms | CPU ms | HTTP requests median | Body bytes median |
| --- | ---: | ---: | ---: | ---: | ---: |
| 1 | 3 | 4304.9 [4267.1, 5154.2] | 4302.1 | 12 | 2805596 |
| 20 | 3 | 6591.2 [5580.6, 9175.9] | 6373.9 | 29 | 2438020 |

## Integrity, resource limits and decision

All 18 read workers preserve Run/grant/consumption/reservation counts and original states; launch is forbidden during those reads/preparation/capture measurements. Captured bytes and unique path/bytes/SHA inventories match. Each layout has one exact material identity across process/history/reverification. Empty history has no published target and therefore no collection/proof sample; this is unavailable, not an artifact pass.

Both separate integrity/recovery tails passed changed-input refusal, expected-runtime-inventory mismatch, corrupted payload whole-hash refusal, restored exact collection and revoked-credential refusal. The twenty-artifact layout also verifies a first successful item before a second-item failure. Actual successful-compute/copy faults retain drained proofs; exact owner recovery on the same Run and repeated result/idempotence reads preserve original interrupted state/events/accounting, with a launch tripwire. These recovery timings have only one initial fault/recovery per layout; no general recovery-performance claim follows.

The environment is Linux, Intel Xeon Platinum 8573C, 4 CPU equivalent cgroup quota / 16 GiB memory limit, PostgreSQL 17.6 and the package versions in [tooling.json](tooling.json). Start/end load/free-space/affinity/source hashes are in the frozen receipt. CPU includes the co-resident app/HTTP/client and waited children, excluding PostgreSQL backend CPU. RSS/HWM are snapshots/lifetime values, not phase peaks. `/proc` I/O includes observer reads. Owner spans are inclusive and cannot be summed. Hash counters instrument named owner helpers only. Observer overhead has a per-process no-op calibration. Optional heavy peer tests were deferred during the matrix; this is not an exclusive OS benchmark host.

Retain this baseline and investigate a bounded sequential collection request owner next: the one-artifact default and 16 KiB forms show higher cost with twenty requests while transferred bytes are close. A candidate must preserve current per-item/transitive authorization, exact expected SHA/Run or result Ref, bounded request/item/aggregate bytes, finite cancellation/deadline, partial typed outcomes and final whole-hash verification. This is a proposed next scope, not implementation admission or a speedup claim.

Do not add a proof/publication cache based on submillisecond metadata proof reads. Repeated runtime verification is a demonstrated preparation owner cost; existing invocation-local held preparation may be a future bounded candidate, but current mutable installed bytes/graph/auth/resource/GO checks cannot be cached away. Cross-call runtime reuse requires a separately qualified immutable owner proof. No cache or domain behavior is changed here.

T5 candidate alternation/improvement and actual installed-runtime mutation are pending. Managed Torch/lab workloads, CUDA/science, shared-host variance and higher payload/history bounds are not qualified. The twenty-artifact fresh workflow spans 5.6–9.2 seconds even with n=3, so this baseline supports a bounded investigation rather than an invented latency threshold.
