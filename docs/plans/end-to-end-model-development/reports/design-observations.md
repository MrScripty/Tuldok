# Design observations and limits: D2

Date: 2026-10-15. Scope: representation/compatibility questions that can change
D2. Current main remains f58880df; PR62 D1 head was 0f8ccfe. No user catalog was
opened, model/trainer executed, dependency installed, data migrated or recorder
enabled. Coding Standards MCP remains unavailable; these are local source/
decoder observations, not Engine certification. Primary agent owns this record.

## Smallest adequate observations

| Question / deciding value | Actual procedure and result | Limits / disposition |
| --- | --- | --- |
| What strict compatibility profile is actually installed? | `python -B` import of `agent_api`, call `discovery()` only. Version1, 56 operations, digest `cb070a69ebd35b48e4f95a57ca01647c75bd7567521429e49efc3a3a1daebae8`. Source SHA-256 `820ec62f22d49aa5834c05858d865bcf109529689a54bdc06ebc3e186c955dd2`. Returned limits 1 MiB requests, 16 MiB HTTP, 32 MiB MCP, 512 KiB inline decoded and 8 MiB segments. | Actual stdlib-only discovery, no HTTP or agent credential used. Establishes the bounded legacy projection identity, not new-client compatibility or live Access. |
| Can an external adapter declare the proposed evidence role without widening generic recipe grammar? | Pass an inert authored `external_recipe_v1` definition to current `recipe_contract.decode_definition`: one required flat `evidence.json`, role `model_evidence_v1`, cap1 MiB, no parameters/inputs, source text would raise if executed. Accepted; duplicate output filename rejected. No source entrypoint was imported/executed. | Actual production decoder on authored metadata only. Role is a declaration, not semantic evidence or a training integration. New task index/verifier still required. Current 32/96-file and byte ceilings remain governing. |
| Do existing scientific field decoders preserve explicit time and endian constraints? | Use existing `tests/qualify_scientific_fields.neutral_bundle()` authored fixture in memory and current `scientific_fields.parse_bundle`. 5958 bytes, 2 frames/4 fields, SHA-256 `32d79d5e4c8881fcfd6c858b70e485c61a636ac1e8ea7d4dbd6c52c7bdc47ed7`. Equal frame times and big-endian field variant rejected. | Actual parser, authored rotated/noncubic native-width arrays, not model/native pressure output. Shows representation constraints and why standalone CNN fields must not acquire invented physical frames. Does not prove any physics/array interpretation of a model. |
| Are model/evidence assumptions consistent with recorded prior pressure work? | Read existing [managed CNN receipt](../../generic-neural-execution/reports/managed-cnn-evidence.json) and [qualification](../../generic-neural-execution/reports/managed-cnn.md). Each prior training/restore stage has six artifacts, selected/final weights and transform/splits/predictions/receipt/summary; no indexed recurring checkpoints/probes. | Previous measured work, not rerun or rehashed original artifact bytes here. Reported 200 Adam updates, exact prior restore and 0/16 native qualification remain their original claims. Current scalar history cannot recreate checkpoint fields. |
| Can the proposed examples distinguish checkpoint binding, amplitude/denominator, authority and budget mistakes? | Seven explicitly [authored cases](examples/d2-contract-cases.json), checked with a disposable stdlib script. Re-tallied confusion/accuracy, rejected checkpoint/clock mismatch, relative-L2([0,10,20],[0,1,2])=9, zero-reference undefined, train-fit membership mismatch, serialized 6+5 against10 admission, exact contract intersection, mixed-artifact policy and retained-vs-live reference distinctions. Passed. | Design arithmetic/rules only. The script is not a production validator, PostgreSQL race proof, access test or full exported package. No new permanent verifier. Expected values are independently simple arithmetic/source-owned invariants, not fitted model outputs. |
| Can current public submit safely be nested inside a study transaction? | Read [Runs submit/retry](../../../../runs.py#L944), [external submit](../../../../runs.py#L322) and [Metadata callbacks](../../../../metadata.py#L314). Public methods call `_start` after their local transaction, which can be only a savepoint under an outer caller. | Source-backed mismatch, no process launched to prove a known code path. D2 requires a narrow Runs admission seam with outer-commit wake. A mock queue test would not improve that architectural decision. |
| Do existing external artifact reads enforce classifier holdout disclosure? | Read [capture/segments/whole reads](../../../../runs.py#L1555) against [classifier exposure](../../../../runs.py#L1694). External paths verify integrity/inspect access, but do not apply classifier test-disclosure semantics to mixed payloads. | Source-backed gap. New generic protected evidence must inherit whole-artifact population protection across all accessors or split outputs. Until qualified, protected scientific test mode is unsupported. |

Reproduction uses existing imports only (`python -B`, repository root plus `tests`
on `sys.path` for the authored fixture helper), JSON/hashlib/copy/zipfile and
current decoders. No Dataset constructor, database, subprocess trainer, runtime
probe, native executable or observer store was used. Temporary scripts stay in
`/tmp`; the only retained example is explicitly authored JSON under the allowed
D2 examples directory.

## Dispositions and stopping conditions

- **A2 representation/design:** concrete owner/version/boundary/consumer contracts
  and valid/invalid/cold-read examples can be reviewed from source and these
  bounded observations. New formats remain proposed, not producer-qualified.
- **A4 interpretation/capture:** partial. Existing field decoder observations
  distinguish real format restrictions, but no current model producer emits the
  proposed checkpoint index. D3 must inspect actual weights/probe arrays and
  measure cadence/storage/time/memory for supported producer integration. Do not
  train user data or launch a new campaign to manufacture a D2 claim.
- **Scientific bridge:** unavailable implementation, bounded scope valid. Current
  captured pressure path remains optional; new canonical-release derivation,
  recurring probes and protected test handling must be independently qualified.
  Common custody/query envelope can be designed now; universal field/operator
  interfaces and physical acceptance are not admitted by authored fixtures.
- **Resource claims:** aggregate reservation is admission/accounting; current code
  provides no hard aggregate CPU/GPU/RSS/filesystem quota. Required hard-limit
  requests remain unsupported. D3 measurements select usable allocations; D4
  runtime design must state enforceable versus advisory limits.
- **A3/A6/A7:** document rendering is a supporting check only. D3 must specify
  linked human/headless-agent and unchanged-client observation-failure procedures;
  D4 supplies implementation slices, migrations and overhead/retention handoff.
- Stop D2 investigation once contract/ownership alternatives are discriminated.
  No source/data/runtime experiment is needed to reconfirm a visible missing
  producer or known unimplemented admission seam. Required later proof stays
  explicit rather than expanding this design stage into implementation.

## D2 independent review and documentation checks

Independent read-only **GPT-6.1 Sol** review (`d2_independent_review`, separate
context) checked all eight D2 documents plus source contracts. Initial findings
and final dispositions:

| Finding | Correction / recheck |
| --- | --- |
| Positive-only settlement could not release staging/empty output to zero | Separate positive Budget from Nat-valued Charge; cumulative slots/wall versus retained/staging occupancy explicit. Zero-charge authored case passes. |
| Study pagination returned an unusable cursor | `studies.get` accepts cursor/limit/expected revision, stable trial/Run ordering, mutation/settlement revision conflict; stop continuation uses get. |
| Multi-checkpoint compare did not identify the observation | Each side binds snapshot and exact checkpoint plus metric definition hash; no implicit best/last/mean. Two-checkpoint deltas −0.1/−0.3 checked. |
| Retained study/create/edit/continue was underspecified | Closed study/policy documents, initial draft/epoch0, owner-only budget/policy edits and explicit current-authority continuation; CAS/receipts/no launch or grant. |
| Source/package Ref call sites had no legal variant | Explicit Projects SourceSelector and Runs ArtifactRef; release/runtime/content IDs and revision variants are distinct. |
| Identical weight bytes could collapse checkpoint identity | Clock/model-bound checkpoint descriptor hash; weight Blob may be shared at distinct actual clocks. Query/candidate/package binding and authored example updated. |
| Packaging preflight/admission needed an explicit path | Package request pins prepared trial/material/revision/epoch/exact grant and shared study/Run admission; package/verification attempts charged. No latest binding or automatic grant. |

Reviewer also checked deterministic default-profile precedence/probe ranking and
reserved selected-checkpoint capacity; D3 numeric allocations block future preflight
until resolved. Reviewer rechecked all corrections and arithmetic and reports **no remaining
blocking D2 findings**. No application files changed by the reviewer. A2 is
satisfied for contract design; the report does not certify implementation.

Supporting checks passed:

- Exact adopted upstream `validate_plan` using unchanged AST/helpers from
  Coding Standards dcc56f26, source SHA-256
  `c7266c0564b9ee02944fc4eb12d66cc20d604fd4ddb7f051ed77d01e9fe4466e`.
- 210 local links and 116 heading/source-line anchors across 12 Markdown files, Markdown table/fence structure,
  unique HTML IDs/nesting/self-contained assets, authored JSON parsing and exact
  eight-file D2 write set. Disposable stdlib checks; no new permanent validator.
- Seven authored arithmetic/reference cases, including independent review of
  checkpoint deltas, unchanged weights and zero settlement.
- Chromium/Playwright over loopback static HTTP at 1440×1000 and 390×1000: no
  script error/body overflow, working Tab/Enter skip link, four disclosures.
  Document rendering only, not A3's future linked-evidence walkthrough.
- `git diff --check`, full-file whitespace checks for new reports/JSON and staged
  scope/history review. Application suite/training not run: no behavior changed.

**Acceptance:** A0/A1/A2 satisfied for their design/evidence scopes. Overall plan
Active/partial; A3–A7 pending, including A4's actual model-producer/physical
interpretation/capture-cost proof. D2 Accepted; next slice D3. No live Coding
Standards MCP certification, generic inference package, scientific protected-test
mode, telemetry-v2 deployment or production acceptance is claimed.

## D3 bounded resource and scientific-meaning observations

Date: 2026-10-15. Source checkout HEAD at observation:
`e407cb17a6ee17f6f17771f9c54fcb6699fc4d5e`, branch
`docs/model-development-d1`; application source remains main `f58880df`.
This section appends to, and does not upgrade, the historical D2 observations.
The only repository write in this investigation is this report. Disposable
scripts/stores used `/tmp`; no catalog, user dataset, lab/Rheon checkout, agent
service, training campaign, runtime installation or installed observer recording
was opened/started. Operator-approved diagnostic scope permits the private
synthetic observer store below, not deployment activation.

### Runtime finding and exact scope of the disposition

Actual `image_training.probe_runtime()` returned `available:false`:
Torch `2.8.0+cpu` and torchvision `0.23.0+cpu` are absent; installed scikit-learn
is `1.8.0`, whereas this adapter requires `1.7.2`. Default Python is CPython
3.12.14, NumPy 2.3.5, psutil 7.2.2, Pillow 12.3.0, x86_64 Linux
6.18.44/glibc 2.41, with five CPUs in the process affinity set. The repository's
only `.venv` has no Torch or NumPy either. Bounded directory-name search under
`/opt`, `/usr/local` and `/tmp` found no Torch installation. `build/` is absent;
tracked `checkpoint.pt`, `weights.npz` and `predictions.npz` search found no
payloads. The [managed CNN receipt](../../generic-neural-execution/reports/managed-cnn-evidence.json)
is retained evidence, **not currently available/rehashed checkpoint bytes**.

Consequently no actual TinyCNN forward, Torch serialization, recurring capture,
capture/training time ratio or trainer peak-RSS measurement is claimed. A NumPy
reimplementation or authored checkpoint sequence would not close that gap.
The new automatic TinyCNN checkpoint/probe profile remains **unavailable** for
preflight until the real-producer gate below passes. The existing legacy
selected-checkpoint-only contract remains supported on separately provisioned
qualified runtimes; this machine cannot execute it. The optional new pressure
bridge/recurring capture likewise stays unavailable. This is a bounded
unsupported/deferred disposition for A4 under the plan, preserving the custody,
query and visualization design; it is not real-integration or product acceptance.

### Source-derived workload and unqualified profile candidates

[Actual image producer](../../../../image_training.py#L334) resizes RGB to 96×96,
uses convolution widths 16/32/64, two 2× pools, adaptive average pool and a
64→class head. It runs one CPU thread; current admission caps are 128 images,
2–8 classes, 1–5 epochs, batch 1–16, 40 MiB release ZIP and 64 MiB expanded
release. Every epoch already evaluates full validation without retaining rows;
only best weights and selected validation/test rows survive. Therefore a future
adapter can capture fixed-probe probabilities from that same evaluation pass;
an extra full validation pass per checkpoint is unnecessary, but this must be
verified in the producer rather than assumed from a prototype.

| Quantity | Exact arithmetic or measured encoding | Meaning and limit |
| --- | --- | --- |
| TinyCNN parameter count | `448 + 4640 + 18496 + 65*C = 23584+65*C`: 23,714 at C=2; 24,104 at C=8 | Source arithmetic, not an executed model. |
| Float32 weight tensor payload | 94,856–96,416 bytes | Excludes Torch archive/envelope, optimizer/resume state and temporary copies. Actual checkpoint file size is unmeasured. |
| Sixteen RGB96 float32 inputs | 1,769,472 bytes | First convolution output alone is 9,437,184 bytes at batch16. Neither is a peak-RSS bound; runtime, activations, backward state and allocator costs are missing. |
| Authored 16×8 probability rows | Compact JSON 1,872 bytes; float32 probabilities alone 512 bytes | Uniform authored probabilities, not model output; no input thumbnails copied. |
| Conservative row-shape allocation | With an explicitly bounded ≤32-byte probability token, ≤3-digit ordinal and one-digit class indices, closed `rows` body ≤5,354 bytes for16, ≤42,762 for128 | Proposed serializer restriction/byte admission, not a claim about arbitrary JSON or actual Torch output. Check references/envelope separately. A 64 KiB per-checkpoint row shard leaves room for bounded references and worst admitted full validation rows. |

**Candidate to qualify, not an admitted default:** resolve
`probe_count=min(16, eligible_validation_count)` before material hashing, freeze
the actual count and ordered D2 SHA-ranked members; use all available validation
members when fewer than16. Never substitute test members or duplicate inputs.
Capture end-of-every-epoch (interval1), retaining every actual checkpoint for
the existing 1–5 epoch scope: `max_snapshots=epochs` (≤5). The selected best
epoch is already in that set, so no duplicate/final-clock snapshot or extra slot
is needed. Retain weights for each checkpoint claimed queryable. Keep scalar
metrics over full validation and label fixed probes as diagnostic examples.
This count allows more examples than the maximum eight classes without claiming
class coverage or statistical representativeness; frozen SHA rank is not stratification.

The candidate publication envelope is ≤4 MiB/≤32 flat files: at most five
weight files with provisional 256 KiB per-file caps, five row shards of64 KiB,
and bounded descriptor/probe/metric/index/scalar material within the remainder.
The 256 KiB cap is an explicit **unqualified allocation**, not observed Torch
archive size: qualify or revise it before registration. It exceeds the largest
raw weight payload, while five such allocations plus five row shards consume
1,638,400 bytes, leaving 2,555,904 bytes for metadata within4 MiB. Whole manifest
still ≤1 MiB, individual shard ≤8 MiB and reference count≤1024 under D2; the
smaller profile caps govern first. No copy of input assets or resumable optimizer
state is included. If those become required, qualify a separate profile. A
private output plus publication copy requires at least8 MiB output staging in
this candidate, **in addition** to release extraction, runtime/worker scratch,
temporary checkpoint files and retained inputs. Account exact source/input
captures separately; do not call8 MiB the total staging reservation.

No numeric trainer memory or capture compute allocation is admitted from raw
tensor size. Current aggregate budget is accounting, not a hard RSS/CPU/GPU or
filesystem quota. D4 must leave unsupported requested hard limits that the
runtime cannot enforce. The new profile refuses preflight while its required
time/RSS/serialized-checkpoint allocation is unresolved; it cannot silently use
these candidate numbers as measured defaults or trim required checkpoints.

### Standalone pressure semantics and measured encoding only

The [source-backed D2 contract](evidence-contract-design.md#scientific-data-bridge-and-bounded-support)
limits the captured CNN to standalone (6,7,8) cell-centered little-endian
float64 cases, four RHS/x/y/z channels, 108 features/16 hidden units and
cell-zero pressure gauge. Exact orientation/origin/spacing, mask semantics,
stage, unit and target authority must come from the lab-owned reader; array
shape supplies none of them. There is no physical frame/time sequence.
Unknown units are `native_unspecified`. Current `scientific_field_sequence_v1`
requires actual strictly increasing frame times, so wrapping these cases in
authored times is invalid. The proposed pair reader is not implemented.

Thirty actual NumPy save/hash/load/reduction repetitions used explicitly
**authored diagnostic arrays**, `r=arange(336).reshape(6,7,8)`, `p=10*r`, with
cell0 already zero and only the last cell masked out. No native pressure
prediction, native geometry or numerical quality is inferred. Valid-cell
relative-L2 is `sqrt(sum((p-r)^2)/sum(r^2))`; empty mask and zero reference norm
are undefined states. Masked values do not contribute to either sum or display
range. No generic re-gauging, independent amplitude normalization or automatic
resampling is permitted. Prediction/reference share one valid-cell range;
signed error uses a separate range. The measured values discriminate a display
that preserves tenfold amplitude from one that normalizes it away:

```json
{"authored":true,"shape_zyx":[6,7,8],"dtype":"<f8","valid_cells":335,
 "physical_time":null,"units":"native_unspecified","gauge":"cell_zero",
 "numerator":1010534535,"denominator":12475735,"relative_l2":9,
 "shared_prediction_reference_range":[0,3340],"signed_error_range":[0,3006],
 "raw_bytes_prediction_reference_mask":[2688,2688,336],
 "npy_bytes_prediction_reference_mask":[2816,2816,464],
 "encode_and_hash_ms":{"n":30,"median":0.041212,"p95":0.092446,"max":0.254457},
 "decode_and_reduce_ms":{"n":30,"median":0.144297,"p95":0.241369,"max":0.757791}}
```

Prediction/reference/mask NPY SHA-256 respectively:
`bc39193131929f431a52e6f73f71f5cb51f8c78fd80ab4a41897f8123ea86483`,
`f03fe96f2ff435b2abe2cf943ee4e21275ba798a40731bbcd6f8af04dcdc4597`,
`c54b25bcbd082c487ce7e6ebf66ad3111dad44db4a839c94a1153c108eb55248`.
One pair+mask occupies6,096 encoded bytes/5,712 expanded array bytes. Four
such cases occupy24,384/22,848 bytes respectively; thus a bounded four-case
inspection may decode one case at a time and keep the expanded array allowance
at64 KiB, with JS/object/render-buffer overhead separately bounded by its future
consumer. This does not certify consumer RSS, NPY pair parsing or image rendering.
Payload length/shape/dtype must be validated before allocation; compressed
size is never the expanded-memory limit. Retain exact values/hashes; display
downsampling, if introduced, is a labelled projection and cannot feed metrics.

Historical receipt only: pressure weights14,830 bytes, predictions36,614 bytes,
200 actual Adam updates, fit0.737034s/wall-after-import0.754533s; restore
wall-after-import0.009147s. These prior receipts contain no capture-only time,
peak RSS or recurring checkpoint arrays. They cannot establish per-checkpoint
overhead. Its step0/50/100/150/200 scalar history is not a checkpoint index.
The earlier0/16 native qualification remains negative.

A future pressure qualification may test four immutable validation cases,
post-update interval50 for a200-update recipe, reserving four regular plus one
selected-checkpoint slot (selected may be outside cadence). That is an
unqualified candidate only, and no historical arrays/weights are reconstructed.
Keep this optional integration unavailable until actual producer arrays and
domain-owned gauge/mask/geometry are inspected alongside capture time/RSS;
neither these authored arrays nor receipt timings admit the integration.

### Actual optional-observer diagnostic and retention

Used the existing `InteractionRecorder` directly in new mode0700 `/tmp`
directories, SQLite mode0600, `max_calls=16`, default age7days/max32 MiB.
Forty fixed synthetic `context_get` request envelopes per case did **not**
dispatch context/domain/MCP operations. The inert function returned identical
bytes in disabled, healthy, unavailable, locked and full cases; response
SHA-256 `f05ff00761efb63a1199544014dc176a1fc36c1c56a1cf1585178137885c4142`.
Healthy instrumentation exercised begin plus all five phases with real SQLite
transactions and `synchronous=FULL`. Times include wrapper/response hashing;
they are single-environment samples, not a service SLA or representative agent
latency percentile. p95 is sorted sample index `floor(.95*n)-1`.

| Mode | Startup / operation measurement | Actual state and bytes |
| --- | --- | --- |
| Disabled | call median0.002424ms, p950.003232ms, n40 | No recorder/store. |
| Healthy | startup3.353465ms; call median0.388519ms, p950.567829ms, max1.462217ms, n40 | 40starts/40terminals;24pruned; reopen retains16starts/16terminals,0unfinished; database61,440bytes. |
| Missing private parent | startup0.267028ms; call median0.006139ms, p950.010887ms, n40 | `storage-unavailable`,0starts, no database created. |
| Actual `BEGIN IMMEDIATE` lock | first call20.582364ms; subsequent median0.005894ms, p950.006444ms, n40 | `storage-locked`; connection released, recording remains degraded.20ms configured busy timeout is visible. |
| Actual SQLite page exhaustion | forced page-cap transaction0.134026ms; subsequent median0.006118ms, p950.007193ms, n40 | Real `SQLITE_FULL` through `_transaction`, `storage-full`; database45,056bytes; reopen has1unfinished and0terminal, never fabricates success. |

The full case follows the existing test's bounded technique: insert an active
structural row, fill its shape column to3950bytes, set `max_page_count` to
current pages, then attempt a larger update. This corrupts no installed store;
it is an explicitly authored failure injection into a disposable diagnostic DB.
No age wait, raw values, credentials or sensitive IDs are retained. Stores were
removed on exit. Peak rollback-journal/temp bytes were **not** measured; SQLite
max-page policy is not a whole-directory quota. Whole probe process peak-RSS
was33,234,944bytes by `getrusage`; end RSS33,361,920bytes by psutil. They have
different accounting/sampling and include NumPy/imports/all diagnostic cases;
neither is observer-only memory overhead or trainer RSS.

**Disposition:** reuse the existing optional observer and its closed structural
allowlist, bounded active count and explicit degraded/unfinished states. Keep
operator opt-in and storage policy; do not add per-agent instrumentation. Measured
cost does not justify a new recorder. An installation requiring tighter latency
than the observed20.6ms one-time lock path must leave recording disabled until
deployment-specific healthy/lock/full/retention measurements satisfy its own
latency/storage policy; do not promise zero overhead. Complete unchanged-client
SDK/HTTP/CLI, cancellation/restart and privacy/lifecycle comparisons remain
future implementation verification. This fixture establishes local recorder
cost/failure/retention behavior only, not A7 product integration acceptance.

### Reproduction, identity and stopping conditions

Executed with `PYTHONDONTWRITEBYTECODE=1 OPENBLAS_NUM_THREADS=1 python3 -B
/tmp/tuldok_d3_resource_probe.py`, source SHA-256
`83d17956d782ce5df182c05ba40a44c35c463a6c89bb9363021903b5a46ccd0d`.
The complete disposable JSON is `/tmp/tuldok_d3_resource_receipt.json` for this
session; the decisive small receipts above are the durable record. No new
production verifier was created. Reconstruct the array procedure exactly as:

```python
import io, hashlib, time, numpy as np
r = np.arange(336, dtype='<f8').reshape(6, 7, 8); p = 10*r
m = np.ones(r.shape, dtype=np.bool_); m.flat[-1] = False
for repeat in range(30):
    start = time.perf_counter(); payloads = []
    for a in (p, r, m):
        stream = io.BytesIO(); np.save(stream, a, allow_pickle=False)
        payloads.append(stream.getvalue())
    hashes = [hashlib.sha256(b).hexdigest() for b in payloads]
    encode_ms = 1000*(time.perf_counter()-start)
    start = time.perf_counter()
    pred, ref, mask = [np.load(io.BytesIO(b), allow_pickle=False) for b in payloads]
    numerator = float(np.sum((pred[mask]-ref[mask])**2))
    denominator = float(np.sum(ref[mask]**2))
    value = np.sqrt(numerator/denominator) if denominator else None
    decode_ms = 1000*(time.perf_counter()-start)
    assert value == 9
```

For the recorder, import only `agent_api.discovery` and `mcp_observer` from the
repository root. Create a `TemporaryDirectory`, chmod0700; construct
`InteractionRecorder(RecorderConfig(path,max_calls=16),discovery(),diagnostics=io.StringIO())`.
Use the closed request `{"jsonrpc":"2.0","id":1,"method":"tools/call",
"params":{"name":"context_get","arguments":{}}}` (93compact bytes).
For40iterations time `begin`, stages `admitted/validated/dispatch`, then
`returned/terminal` with success/HTTP200 and terminal delivery written. Close,
call `check_store` and stat the DB. Repeat with no recorder and a missing
parent path. For lock/full use the precise technique above, then time40calls
after degradation. Hash the same inert response in every mode. This reproduces
the measured mechanism without starting an agent or accessing a catalog.

Observed source SHA-256:

| Source | SHA-256 |
| --- | --- |
| `image_training.py` | `5a7807f8834f96bf17e1c020357fdb96a7eb1ac94b54a440db80559d9923f99c` |
| `mcp_observer.py` | `b4630f48db0365ab7bf724d9dc81e9dfa781dc8aad6314573ac172c0e6fd845d` |
| `mcp_stdio.py` | `7a87261212474b06dad85ab7f8ab8693c20cd0fec90ded0ba034f2adf0ced344` |
| `agent_api.py` | `820ec62f22d49aa5834c05858d865bcf109529689a54bdc06ebc3e186c955dd2` |
| `scientific_fields.py` | `19b63cf1c65335b55a907c84312f0f9be70de1aa79522d96ec38d4862fa55338` |
| Managed CNN receipt | `390dd78d482c1745f9697d57adb5c4387252d29593ed4a472a4f6a0b361839da` |

Existing installed package metadata was read locally, without installation or
dependency adoption: NumPy2.3.5 declares BSD redistribution terms plus bundled
component notices (including OpenBLAS BSD-3-Clause and GCC runtime/quadmath
notices); psutil7.2.2 declares BSD-3-Clause; Pillow12.3.0 declares MIT-CMU.
Their METADATA SHA-256 respectively:
`6002f29765e5bc1a3be4a1b92ed56b64968a0fecba73e7f81cd536d0c40f4fa3`,
`525f8ba78523cf7bc3759d62a105e7c57fd679ea702402b9449fb0746aa0217f`,
`8fc07146cab33ef7582361dab6eac596d340b03ec648f18217da7894f73838c8`.
This identifies the diagnostic environment, not a complete future runtime
redistribution/license audit or a dependency selection. Absent Torch has no
installed metadata to inspect here.

**Stop here:** no further fixture/NumPy experiment can settle Torch producer
capture or pressure physical meaning. Future adapter/runtime owner, on an
already authorized/provisioned pinned CPU runtime, first runs
`<qualified-python> -B image_training.py --probe`. Before registering the new
profile, run a bounded disposable synthetic RGB96 workload through the actual
model and proposed producer seam: identical fixed validation membership,
1and5end-epoch captures, batch1and16, C=2and8, selected checkpoint reload and
same-probe inference. Measure cold/warm capture-only versus training+evaluation
wall time, actual serialized weight/row/scalar/manifest bytes, all staging/copy/
temporary bytes, expanded arrays and isolated worker peak RSS; verify every
checkpoint→probe binding and exact selected-clock retention after cold reopen.
Stop as soon as the above candidate count/cadence/caps are accepted or replaced
within the actual recipe wall/storage/operator memory allowance. Record the
resulting allocation and runtime identity before material hashing; if required
cost exceeds that allowance, qualify a different explicit profile or refuse.
No universal percent-overhead threshold is invented here. Pressure additionally
requires real emitted pairs and independent lab-owned geometry/gauge/mask and
native-evaluator disposition. Missing runtime/producer/semantics keeps only that
integration unavailable; it cannot be closed by authored fields or old receipts.
