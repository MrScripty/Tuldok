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
