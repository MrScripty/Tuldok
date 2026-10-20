# Same-head bounded collection measurements — 99741e5

All six eligible cells have a median paired batch/individual wall ratio above 1. The current batch path reduces twenty collection requests to one but does not demonstrate a latency improvement. These results are retained as a negative candidate result; no automatic selection, cache or speedup is justified.

Exact measured source: `99741e5807e4260c58b53badafc5b6c549421645`, normally composed with root92546d7. Both arms use the same canonical request-aware client. The raw `production_base` field is the historical branch admission base2d8b7d7; it does not claim current source equality with that base or producer007. Start/end source8 and both harness hashes match. Raw receipts and `qualified-pairs.json` retain every sample and owner/resource observation.

The fixed matrix completed with exit0: 24 fresh application processes, six empty-history controls without an eligible target, 18 eligible processes, 54 pairs and108 collection arms. Each eligible cell has three first pairs and six warm pairs. Normal histories contain8/55 genuinely completed neutral byte-copy Runs. Attached-publication cells contain55 completed plus one original interrupted Run (56 total). Each arm reads327680 raw bytes in one or twenty artifacts; exact inventory/whole hashes match within each layout. The deterministic contents differ between layouts. Arm order alternates; the second arm in a first pair already follows the first arm in that process.

Client bootstrap, source population and actual same-Run copy recovery are measured separately and excluded from collection pairs. Reads launch no compute. All paired Run/grant/consumption/reservation counts and original events remain unchanged. Both exact fresh schema and temporary-directory cleanup checks passed. The negative tail retains changed-input/expected-inventory, changed-payload and revoked-inspection refusals plus same-Run no-replay evidence. Earlier separate producer tests qualify typed partial/hash errors and cancellation; those are not additional performance samples. Installed-runtime mutation was unavailable under the installation restriction; expected-inventory mismatch is the narrower witness.

## Paired wall distributions

Delta is batch minus individual; positive values are regressions. Ratio is computed per pair before summarizing, rather than dividing independent medians. `p90` is nearest rank. No pair or outlier was excluded.

| Source | Items | Total history | Condition | n | Ratio min / median / p90 / max | Delta ms min / median / p90 / max |
|---|---:|---:|---|---:|---|---|
| publication | 1 | 56 | first_pair_fresh_process | 3 | 1.686 / 2.327 / 2.744 / 2.744 | 181.979 / 282.542 / 506.915 / 506.915 |
| publication | 1 | 56 | warm_pair_same_process | 6 | 1.296 / 1.877 / 3.061 / 3.061 | 107.259 / 225.501 / 555.228 / 555.228 |
| publication | 20 | 56 | first_pair_fresh_process | 3 | 1.009 / 1.056 / 1.087 / 1.087 | 32.188 / 177.381 / 266.559 / 266.559 |
| publication | 20 | 56 | warm_pair_same_process | 6 | 0.736 / 1.003 / 1.181 / 1.181 | -1075.302 / 3.662 / 535.115 / 535.115 |
| run | 1 | 8 | first_pair_fresh_process | 3 | 2.000 / 2.222 / 2.319 / 2.319 | 237.710 / 247.643 / 666.547 / 666.547 |
| run | 1 | 8 | warm_pair_same_process | 6 | 2.693 / 2.918 / 10.036 / 10.036 | 270.774 / 312.148 / 1628.862 / 1628.862 |
| run | 1 | 55 | first_pair_fresh_process | 3 | 2.181 / 2.355 / 2.969 / 2.969 | 221.511 / 276.593 / 284.646 / 284.646 |
| run | 1 | 55 | warm_pair_same_process | 6 | 2.782 / 2.921 / 3.307 / 3.307 | 270.057 / 290.995 / 353.314 / 353.314 |
| run | 20 | 8 | first_pair_fresh_process | 3 | 1.415 / 1.807 / 1.912 / 1.912 | 765.444 / 1377.133 / 1586.163 / 1586.163 |
| run | 20 | 8 | warm_pair_same_process | 6 | 1.362 / 1.998 / 3.174 / 3.174 | 782.130 / 1709.873 / 4114.870 / 4114.870 |
| run | 20 | 55 | first_pair_fresh_process | 3 | 1.677 / 1.874 / 2.825 / 2.825 | 1086.310 / 1491.561 / 6208.147 / 6208.147 |
| run | 20 | 55 | warm_pair_same_process | 6 | 1.419 / 2.044 / 6.170 / 6.170 | 817.311 / 1968.688 / 8594.904 / 8594.904 |

## Pooled descriptive owner/resource costs

Each row below pools all nine pairs only for a compact description; the first/warm distributions above and full machine-readable distributions remain authoritative. Inclusive owner timings overlap and must not be added.

| Source | Items | History | Arm | Wall ms median | CPU ms median | Requests | Response body bytes | Run loads | RSS after KiB median | Logical read chars median | Physical read bytes median |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| publication | 1 | 56 | batch | 495.4 | 478.7 | 1 | 438441 | 5 | 65956 | 332817 | 0 |
| publication | 1 | 56 | individual | 271.4 | 265.2 | 1 | 437835 | 3 | 65956 | 332817 | 0 |
| publication | 20 | 56 | batch | 3317.9 | 3091.7 | 1 | 466753 | 100 | 66984 | 584793 | 0 |
| publication | 20 | 56 | individual | 3160.3 | 2985.6 | 20 | 455440 | 60 | 66420 | 584793 | 0 |
| run | 1 | 8 | batch | 471.3 | 438.1 | 1 | 437478 | 4 | 66048 | 330128 | 0 |
| run | 1 | 8 | individual | 180.3 | 171.0 | 1 | 437332 | 1 | 66048 | 330128 | 0 |
| run | 1 | 55 | batch | 447.0 | 434.4 | 1 | 437478 | 4 | 66036 | 330128 | 0 |
| run | 1 | 55 | individual | 153.2 | 150.8 | 1 | 437332 | 1 | 66036 | 330128 | 0 |
| run | 20 | 8 | batch | 3083.6 | 2739.6 | 1 | 447493 | 80 | 66776 | 417053 | 0 |
| run | 20 | 8 | individual | 1762.6 | 1650.7 | 20 | 445380 | 20 | 67052 | 417052 | 0 |
| run | 20 | 55 | batch | 3199.0 | 2968.6 | 1 | 447493 | 80 | 66372 | 417052 | 0 |
| run | 20 | 55 | individual | 1721.2 | 1593.3 | 20 | 445380 | 20 | 66280 | 417053 | 0 |

The simple ordinary Run path performs N loads in individual mode versus4N in current batch mode: outer eligibility, canonical initial reader and two final-stage reloads. For twenty artifacts this is20 versus80. Every initial inventory/segment read remains present. The independent refinement review permits removing the outer duplicate via an external-only private canonical flag and deduplicating exact sources separately at each final stage in last-occurrence order; that proposed source was not present in this measurement. No cross-call proof cache is admitted.

## Attribution and limits

Python3.12.14 / task-owned PostgreSQL17.6, cgroup4 CPU-equivalents and16GiB memory. CPU includes application/HTTP/client and waited child usage; PostgreSQL backend CPU is excluded. RSS/current and lifetime-HWM snapshots are not phase peaks. `/proc` I/O includes observers. HTTP byte counts cover declared bodies, excluding headers. The complete resource distributions, before/after observations, inclusive owner times, exact source hashes and environment are in the JSON receipts.

Host activity was not exclusive. Environment-start file time was22:34:48.507661 UTC; another agent's pure/oldCLI group ended22:35:03.649626, about15 seconds later. Available progress and the first positive receipt support control-only overlap, but per-arm UTC start times were not recorded. No sample was discarded or relabelled. Small pure checks were allowed throughout the shared quiet period. No OS/PostgreSQL cache flush, confidence interval, latency-budget acceptance, CUDA/training or scientific claim is made.

The complete matrix source remained frozen. A later refined candidate must receive independent correctness review and a separately attributed paired matrix; this negative matrix remains immutable.
