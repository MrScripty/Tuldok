# D3: Automatic evidence interaction and acceptance design

Status: proposed interaction design with a separately labelled runnable prototype.
The [plan](../plan.md) owns acceptance. [D2 contracts](evidence-contract-design.md)
own identities, permissions and meaning; this report does not create a new data
or execution authority. Resource observations are retained separately in
[design-observations.md](design-observations.md).

## Compact interaction

The local [walkthrough](prototypes/model-development.html) is a self-contained,
dark, authored design fixture. It has no application/catalog connection and no
training, permission grant, disclosure or export effect. Persistent labels identify
simulated values/actions. This is a demonstration of proposed controls and failure
states, not a trained model or a production acceptance result.

Use one task-aware workspace with a small top toolbar and a contextual detail
panel. Show the selected task, trial/Run, evidence state and active checkpoint;
place long provenance and resolved defaults behind explicit inspect actions.
Keep primary controls next to the evidence they affect. Do not build seven
permanent navigation modules, a universal graph editor or a page of expanded
explanatory lists. Copy describes the current decision in a few words.

| Context | Primary controls / retained selection | Required consequence |
| --- | --- | --- |
| Classifier inspection | Checkpoint/curve point, validation example, class probabilities/confusion/error rows; native select/numeric alternatives. | Changing checkpoint keeps the same probe example and class order, and visibly changes predictions. Frozen targets stay immutable; selection identifies producing weights/descriptor, actual epoch and live/verified state. |
| Standalone field model | Input/output field, stage, checkpoint/update, plane and numeric slice. | Physical-time control is not applicable for the captured pressure CNN. Input/output/stage edits require a new versioned task/model/adapter compatibility decision, even with unchanged tensor shape. No Rheon operator knowledge in generic UI. |
| Trajectory evidence | Explicitly declared physical frame/time, field/stage, plane/index; same controls share selection across checkpoint/reference/prediction/error. | The separate authored trajectory demonstrates time controls. Frame identity/time comes from retained evidence, not optimizer or wall clock. Never add fictitious simulation times to standalone cases. |
| Scales and error | Shared prediction/reference range; separate error range; numeric extrema/selected values. | Amplitude differences remain visible. Auto-range uses permitted values only and does not silently reset on checkpoint change; an explicit reset changes the display, never evidence. |
| Model authoring | Supported input/output fields/stages and architecture/config/source revision in a contextual editor. | Validate against exact task/adapter version; incompatible shape/gauge/preprocessing/stage changes cannot reuse an old material/grant. Computation summary is distinct from execution workflow. No code executes on edit/inspect. |
| Correction | Frozen example/target beside current record revision; edit current draft and request review. | Simulated correction creates a new draft/review gate/release/trial, never rewrites old evidence. Changed validation membership disables paired deltas; labelled side-by-side comparison remains possible. |
| Next trial | Proposed exact variant, resolved capture budget and current authority requirement. | Proposal is not execution. Owner-only built-in start remains a gate; external start needs matching exact actor/material grant. Budget/stop/unknown states remain visible. |
| Candidate | Exact selected checkpoint/evaluation, diagnostic/qualified decision and package/verification state. | Missing required evidence or failed required numerical criteria cannot become qualified through export. Package-complete and fresh-consumer-verified remain separate. |

Test controls default to validation and reveal no hidden test-derived value,
count, color scale, preview, thumbnail or cached field before permission/disclosure.
Classifier test requires the existing expose-holdout scope and committed durable
exposure. The prototype may simulate this owner action, clearly labelled. New
scientific protected-test mode remains unsupported until D2's all-accessor
protection is implemented; a simulated grant cannot claim the missing cutover.

## Capability-to-view resolution

The supported task adapter declares capabilities; the evidence query returns
which were selected, scheduled, observed, verified and currently accessible.
The browser and headless agent consume the same structured semantics. Never
infer capability from an arbitrary filename, stdout string, model class name or
a final scalar. Missing renderer support affects that view only; bounded numeric
queries remain useful when supported. No per-run chart/logger/callback setup.

| Capability / evidence state | Display / action |
| --- | --- |
| Required, scheduled, not yet produced | Pending marker with known cadence; no zero point or empty successful result. |
| Verified checkpoint/probe index | Linked history/example controls, immutable snapshot and producing checkpoint. |
| Optional budget-skipped | Explicit skipped badge and resolved budget reason; no suggestion evidence can be recovered without separately authorized replay. |
| Not applicable (one fit, standalone time) | Show one fit result; disable irrelevant clock/time control with its short reason. No fake curve. |
| Unsupported or historical unsupported | Current v1 selected-only predictions stay viewable; history says unavailable. Do not synthesize checkpoints from loss history. |
| Live-unverified or partial/interrupted | Show bounded provisional status separately. Staged arrays are not a verified snapshot, candidate or complete comparison. |
| Missing/corrupt required evidence | Actionable integrity/incomplete state; refuse selection/export, preserve diagnostics and original Run meaning. |
| Incompatible comparison | Show the exact mismatch (population/target/unit/gauge/stage/profile), no paired delta; offer permitted side-by-side values. |
| Denied or protected | Authorization error without existence/count/scale leakage. Current access is checked on every read/page/window/export/cache. |

A renderer never converts `undefined` arithmetic to zero, or successful execution
into accepted numerical quality. Use a textual status and numeric value in
addition to color. Selected control identity is scoped to catalog/Run/snapshot;
ignore stale asynchronous responses after that context changes. The production
implementation must reauthorize caches and update derived views atomically.

## Capture and resource decision

The measurement record owns actual environment/input/source hashes and results.
The present design environment has no Torch runtime; this limits which capture
claims can be made. Candidate numeric settings below are a **bounded proposed
profile**, not a qualified default or measured TinyCNN performance result.
The new profile must advertise unavailable until the future actual producer
qualification succeeds. Existing v1 training/selected evidence remains unchanged.

| Profile | Proposed resolved settings / admission consequence |
| --- | --- |
| New bounded TinyCNN evidence | Rank validation probes deterministically with profile seed0, choose count=min(16, eligible validation examples) and freeze that resolved count. End-of-epoch cadence interval1 for existing 1–5 epoch scope, retain all sampled descriptors/weights plus selected marker; selected already sampled. At most five sampled checkpoints, at most sixteen probes per sample. No test probes. |
| One-fit text/audio | Single fit-pass observation with existing frozen text/audio transform identities; no optimizer trajectory. Retained model JSON, full validation predictions and bounded fixed probes; optional unsupported diagnostics explicit. |
| Captured pressure-model adapter | Proposed checkpoints at declared optimizer-update cadence only after adapter qualification; selected source currently exposes steps, not free channel/width/seed changes. No default capture/physics claim from a missing producer. Standalone arrays/time remain explicit. Canonical-release bridge and protected-test mode unavailable until independently qualified. |
| Trajectory/other field adapters | Adapter-owned field/stage/time/geometry/mask/gauge/unit contract plus declared bounded windows. Generic core supplies custody/query/view projection, not a physical operator or implicit alignment. Unsupported extensions return typed outcomes. |

The min(16,N) rule resolves a new immutable count before hashing material, so it
does not violate D2's refusal of a resolved count larger than membership. Sixteen
is a conservative initial usability/count cap, not an empirically optimal sample.
Probe count is independent of training seed and says nothing about statistical
coverage. A task needing other coverage must declare another explicit profile.

Retain the existing classifier 64 MiB aggregate result bound and 600-second Run
watchdog as initial outer admission ceilings, without claiming existing v1 can
accept new files. New-version producer/manifest/verifier must account for all
weights, probe/full prediction payloads, indexes, metadata and publication copies.
Preflight rejects a resolved profile whose worst-case output bound does not fit;
never truncate required evidence or raise the resource profile automatically.
The resource report's smaller **unqualified** candidate caps are4 MiB/32 flat
files for the new result, 256 KiB per weight file and64 KiB per checkpoint row
shard. These apply only to the inspected16/32/64 architecture and bounded128-image,
2–8-class workload; changed width/input/head requires its own profile qualification.
The whole new result includes full validation/test predictions and all descriptor/
index/manifest metadata, not just probe extras. The4 MiB cap is stricter than the
existing64 MiB outer ceiling; preflight must prove the actual selected result fits
both, or revise the candidate before activation. No claim of successful Torch
serialization or memory performance is made. The observed four-case standalone
array allocation suggests a64 KiB expanded pair-inspection candidate, not a bound
on browser/worker RSS. Actual renderer buffers and object overhead need their own
qualified consumer gate.

Numeric array windows remain ≤262144 values/8 MiB response per D2, with dtype/
shape/mask expansion counted before allocation. Do not claim process RSS, hard
aggregate CPU/GPU or a filesystem sandbox from these ledger/format ceilings.

Source-owned raw-weight/input/output bounds and permitted disposable encoding/
observer observations inform these ceilings; they do not establish actual Torch
latency or peak RSS. Production activation gate: actual supported Torch/torchvision
CPU runtime, original classifier producer on a bounded non-user-data reviewed
fixture, ≥2 real sampled checkpoints, same fixed probes, measured capture+write/
publication bytes, elapsed training/evaluation time and peak RSS; then cold query
and independent fixed-probe inference. Record runtime/source/material/fixture pins,
compare against the declared envelope and revise the profile or leave unavailable.
No successful product acceptance is claimed until that procedure runs in its
required-real environment. This bounded unsupported disposition preserves selected
owners/contracts and makes deployment failure explicit rather than inventing costs.

Cancellation first closes study admission epoch and asks Runs to stop every child.
No capture continues under a new actor/grant after stop; partial temporary outputs
stay private. After confirmed cessation account full conservative wall/slot charge
and actual verified retained/storage cleanup as D2 permits. Unknown cessation or
commit retains reservation and fences admission. Capture and inference do not
create a second supervisor or silently replay after reopen.

## Human product acceptance procedures (future implementation)

These are executable acceptance recipes for later production slices; the local
prototype is separate evidence. Use isolated non-user-data fixtures, real owner/
agent credentials and actual PostgreSQL/HTTP/worker boundaries. No acceptance
procedure is permission to execute a campaign or migrate user data now.

| Procedure | Actual start → observation → deciding result / negative |
| --- | --- |
| H1 automatic image evidence | Owner prepares reviewed fixture/frozen release, compatible model and three epochs; start ordinary supported training with no logging/chart setup. Confirm ≥2 actual checkpoint descriptors/weights and identical validation probe membership/probabilities from real producer. Reopen service, select the same example across checkpoints, independently infer fixed probes and compare retained probabilities. Wrong descriptor/class order/transform refuses publication or inference; old v1 Run has honest absent history. |
| H2 one-fit modes | Use existing text/audio task fixtures and one fit. Confirm single actual fit-pass, no invented optimizer/epoch curve, exact text vocabulary/IDF or WAV rate/channel/frame features and train-fitted values. Unsupported diagnostics clearly not applicable. |
| H3 scientific field semantics | Use qualified optional captured adapter with pinned data/operator contract, not a universal core solver. Compare reference/prediction/error on exact same field/stage/grid/mask/gauge/time (time only where present). Read raw array windows independently; tenfold amplitude produces correct relative error and shared-scale difference. Reject incompatible centering/gauge/time and zero denominator as undefined. Record native units/negative acceptance honestly. |
| H4 correction/new release | Inspect frozen prediction, change current draft, human review and freeze new release. Confirm prior evidence unchanged and current revision visible. Compare only proven identical validation populations with paired deltas; changed memberships get labelled side by side. Exposure survives content/family reimport. |
| H5 access and missing evidence | Revoke read permission during paging; try stale response/cache and all whole/segment/import/capture/export accessors. Deny without hidden test values/count/scales. Kill worker before publication; required absent checkpoint/index cannot become complete or selectable. |
| H6 custom model/stage changes | Import new source closure or change declared input/output field/stage semantics. Inert validation identifies new task/model/adapter compatibility or unsupported integration. Existing material/grant cannot start changed code; generic Run alone does not promise automatic views. |
| H7 candidate package | Select eligible verified validation checkpoint; diagnostic-only result stays diagnostic. Package through exact prepared trial/authority/budget. Verify inventory, source/transform/runtime/license closure. Fresh consumer with no live checkout/cache reproduces fixed probes under owned tolerances. Missing/wrong transform or runtime fails; package bytes alone cannot close inference or physics acceptance. |

Keyboard/narrow acceptance uses real browser focus traversal, labels, native
select/range/number controls, visible focus, zoom and screen widths1440/390.
No evidence/control is available only by pointer/hover/color. Physical-time/plane
controls have numeric alternatives. Task, snapshot, selected example/time/plane
and comparison state survive valid checkpoint switches; changed context excludes
stale responses. Product acceptance requires actual data/API paths and current
policy, not only this prototype's successful DOM checks.

## Headless agent product acceptance procedure

Use one unchanged authorized AgentClient/MCP or CLI client and the real server.
This closes design coverage for A6; future implementation must run it end to end.

1. Authenticate and discover capability envelope; select exact locally supported
   operation contracts. Verify new unrelated operation leaves existing compatible
   reads/mutations usable; requested incompatible contract fails before domain/
   grant/budget mutation. Test old/old, old/new frozen legacy, new/old bounded
   fallback and new/new negotiation. Never fall back on auth/malformed/5xx.
2. Import/inspect/annotate fixture through supported typed operations. Request
   human review and wait for owner; agent cannot self-approve. Preview/freeze exact
   record/source revisions and family splits. Exercise stale CAS and changed source.
3. Save/resolve model and recipe through canonical owners. Prepare study/trials
   with immutable material/probe/profile and finite budget; inspect resolved
   defaults and unavailable capability. An input/output/stage change must produce
   new versioned task/model material or explicit unsupported, never hidden coercion.
4. Owner reviews exact material and grants an external launch, or starts the
   built-in classifier under existing owner gate. Agent receives durable receipt,
   polls actual Runs and uses bounded numeric evidence queries; no screenshots,
   opaque filename interpretation, logger calls or trace IDs.
5. Page all metrics/checkpoints/probes/errors under immutable snapshot/revision;
   query bounded field windows with masks/geometry/units/clocks/gauge. Independently
   re-tally classifier confusion and pressure error arithmetic. Reject missing
   selector, stale cursor, incompatible population/gauge and oversized expanded
   arrays. Never recover historical checkpoints from scalar history.
6. Propose correction/new release or exact next finite trial; current human review,
   grant and total-budget gates remain. Simultaneous admissions cannot overreserve;
   changed contract/material cannot consume a grant. Lost acknowledgement queries
   same actor/key/body receipt read-only before retry. Explicit replication differs
   from a new attempt; exact-material retry refuses runtime/source drift.
7. Stop study while work queued/running: commit closed epoch first; pending child
   cancellation stays visible until cessation. Revoke credential, lose response,
   restart service and reconcile unknown state without auto-replay/refund. Existing
   admitted children retain only their bounded continuation effects.
8. Select eligible candidate and package via exact prepared material/grant. Verify
   complete inventory and current permitted artifacts, then separately approve
   fresh inference verification. Wrong class order, preprocessing, gauge or weights
   fails. Record diagnostic/qualified/package/verification states separately.

The report/receipt must pin implementation, selected contracts, catalog/runtime/
fixture/source/material/evidence identities, actual process termination and results.
Fixture setup and owned human review/approval may be provided by a qualification
harness, never by forging catalog rows or granting the ordinary client admin scope.

## Unchanged-client observation and mandatory-audit procedures

A7 design acceptance includes these future comparative cases for each supported
MCP/HTTP/CLI boundary. Current MCP's bounded disposable measurements remain limited
to that existing implementation; proposed v2 seams are unimplemented.

Run the **same client and arguments** under disabled, healthy private-store and
failed observer conditions against isolated actual domain fixtures. Normalize only
declared random/timestamp/duration fields and compare selected contract/schema,
ordinary result, required audit, grant consumption, Run count and durable effects.
No additional agent tool, telemetry argument, setup step or causal ID is permitted.

| Failure/input | Passive record expectation | Domain/required audit expectation |
| --- | --- | --- |
| Invalid arguments or permission refusal | Only witnessed fixed stage/outcome and allowlisted shapes, no raw body/error/identity. | Same denial/status and rollback/audit behavior with recording on/off. |
| Unknown response after commit | Return/terminal may be missing or incomplete; no inferred no-commit/success. | One receipt/attempt/grant charge; read-only reconcile, no automatic retry. |
| Partial socket/stdout delivery or broken health sink | Only known written byte count and incomplete/unknown; kernel acceptance is not client receipt. | No substitute response, second execution or invented child completion. |
| Store full/locked/unsafe/corrupt | Bounded fixed degraded health, recorder disabled for lifetime; preserve unknown store. No raw SQL/path/context. | Same domain result; no retry or response replacement. Retention/rotation stays operator-owned. |
| Cancellation/restart/SIGKILL | Known unmatched starts remain unknown; orderly close marks incomplete if writable. | Existing Runs/study custody governs cessation/unknown/reservations; no replay from passive logs. |
| Sensitive nested input and unknown operation/fields | Redact before buffering; unknown names fixed markers; no paths/prompts/data/content hashes/Run or actor IDs. | Ordinary selected operation still validates its actual full input and current permission. |
| Required audit or exposure write fails | Optional recorder can be healthy or failed independently. | Actual owning transaction rolls back grant/admission/disclosure and returns failure. No bytes/derived values returned before committed disclosure. |

Measure added latency distribution, peak memory, retained/temporary/journal bytes,
count/age retention, shutdown and dropped/incomplete counts using the actual
boundary/store/health reader. Check private modes and offline maintenance refuses
live writers. Stuck filesystem/stderr is outside current hard latency guarantees;
require operational storage/supervision constraints or keep collection disabled.
Future v2 collection requires fresh operator-selected store/projection qualification,
not an automatic v1 store migration. No passive record is a numerical oracle,
transactional audit substitute or complete workflow census.

## D3 prototype and review results

The stable [prototype](prototypes/model-development.html) source SHA-256 is
`5f0eec72ed49792b183216bac7b088a6df176289bd757f913440e9cac209e96b`.
Prototype author and primary integrator separately ran the same four disposable
Playwright procedures on that final source: **153 assertions pass** (91 main
workflow,12 material/clock regressions,32 review-context regressions,18 task-session
regressions), zero page script errors. This is repeated execution of one assertion
set, not two independent numerical oracles. Chromium151.0.7922.173, preinstalled
Playwright1.62.1 and Node24.19.0; loopback static HTTP, no external assets. Root's
rerun used a separate dynamic port and screenshots only under `/tmp`.

Actual checks cover checkpoint/example preservation, all six evidence states,
protected derived DOM, review/freeze and incompatible pairing, supported versus
unsupported model edits, owner-only classifier start versus exact external grant,
pressure steps-only material, authored trajectory's unavailable model/trial/package,
finite admission/package accounting, immutable admitted material, declared physical
frame arithmetic, shared field scales and numeric slices. Task switches explicitly
reset independent authored demo sessions; same-task changes cannot refund spent
budget or approval. All15 task/context combinations fit390×844 without document
horizontal overflow; desktop1440×1100, native controls and keyboard navigation pass.
These checks do not certify comprehensive assistive-technology accessibility.

The11 committed representative captures are:

- [Classifier desktop](screenshots/d3-classifier-desktop.png) and
  [narrow](screenshots/d3-classifier-narrow.png).
- [Shared-scale pressure amplitude failure](screenshots/d3-pressure-amplitude-desktop.png)
  and [separate trajectory timeline](screenshots/d3-trajectory-narrow.png).
- [Current correction/frozen evidence](screenshots/d3-correction-desktop.png),
  [versioned model/workflow edit](screenshots/d3-model-desktop.png),
  [candidate pending inference verification](screenshots/d3-candidate-desktop.png).
- [Classifier owner-only start](screenshots/d3-classifier-owner-start-desktop.png),
  [pressure steps-only external trial](screenshots/d3-pressure-trial-desktop.png),
  [pressure future package contract](screenshots/d3-pressure-candidate-desktop.png),
  [trajectory model unavailable](screenshots/d3-trajectory-model-unavailable-narrow.png).

Tooling provenance: one-shot Prettier3.6.2 was downloaded solely for formatting
through `/tmp/d3-npm-cache`. No repository package/lockfile or application/runtime
dependency was added; no formatter/download was used for final corrections.
Temporary static servers were stopped. The overview also passes actual Chromium
1440/390 rendering, keyboard skip, no overflow/errors and no external requests.

Independent GPT-6.1 Sol final review identified and rechecked the contextual
owner/parameter/trajectory/session corrections; final result **no design blockers**.
[Final review](design-review.md) records the composed design and exact proof limits.
A3 proves labelled design interaction only. A4 closes through actual named bounded
observations plus its explicitly permitted unsupported Torch/producer disposition;
no real capture/time/RSS, physical qualification or product acceptance is claimed.
H1–H7, full headless journey and unchanged-client/audit procedures remain future
implementation acceptance.
