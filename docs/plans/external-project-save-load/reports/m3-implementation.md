# M3 integration evidence (in progress)

This is scoped supporting evidence. Current milestone status and the next action
remain authoritative in [the plan](../plan.md). M3 is not accepted and the draft
implementation PR is not ready to merge.

The integration baseline is M2 commit
`c22e9d02c87938514a7a1c9b3b0532158008ca0d`; main remains
`133d53c0e2985a6559ba9cebd7d4a9f530051f06` and the standards reference remains
`5bce3110fc64d61ff8b4f79468184bd6295855d5`. Work is isolated on
`feat/external-project-save-load-20261022`. No local lab was inspected or migrated.

The shared boundary now captures named owner changes before the actual outer
PostgreSQL commit, with canonical facts selected before acknowledgement or a
worker wake. Foreground capture composes fixed additional Run/Study/producer
facts without a second publication. Background capture requires a current local
authority callback and an owned transaction. SQL rollback after canonical
selection, lost SQL acknowledgement, and unknown checkpoint fsync all fence the
projection. Imported operation facts do not supply a current grant or admission.
The lock facade acquires host authorization, project session and actual
projection CatalogLock in that order, retaining PostgreSQL advisory ownership.

Performed shared-boundary checks, using disposable PostgreSQL 17:

- `test_project_session.py`: ten tests passed in 4.105 seconds. The additional
  cases exercise nested hook ordering, capture refusal without wake, canonical
  observation retention on an actual deferred SQL constraint failure, complete
  foreground capture and background lock entry. Existing publication, stale
  authorization and replay tests also passed.
- Two targeted tests passed in 1.518 seconds after adding actual checkpoint
  replacement/fsync uncertainty and simplifying the wake test to use the public
  hook installation API. The former verifies SQL rollback, fenced availability
  and retained canonical facts after reopening; the latter starts a second real
  transaction in an acknowledged commit callback. These are the changed cases,
  not an identical repeat of the earlier campaign.
- Existing `test_metadata_transactions.py`: fifteen tests passed in 6.515 seconds,
  covering nested rollback, independent connections, file cleanup, lost commit
  acknowledgement, exact retained text and PostgreSQL configuration failures.
- Existing `test_project_workspace.py`: eleven tests passed in 9.254 seconds after
  the initial current-custody guards and inert execution attachment. Later
  producer/Study/file composition and shutdown attachment were not present in
  that subject; final integrated lifecycle checks remain pending.

The shared production files used by these checks have SHA256:

```text
metadata.py         7bb728cab2068a415eb071191b61241dc2886a765044d9588487f4e8b8d11d86
project_session.py  9f694d1c38dbf7c5780c94a516f0fe4b014740bd4962df40c136520c0bcfe95a
project_locks.py    d2c3493339f934ab63d582ac091ef31fbf11710ffb66ba24dffffaae48c26297
```

These fingerprints identify the shared boundary, not a frozen complete M3
candidate. Other disjoint owners were still being integrated. Test output is
retained in the execution transcript; this report does not invent raw log files.

Early independent source review found and resolved lazy Run construction before
request rejection, commit callbacks observing a completed transaction as open,
and background canonical uncertainty failing to fence. The third repair also
requires execution to fence existing dispatch whenever Session is unavailable,
regardless of the SQL outcome label. Full independent review and the required
stable-source real process, public HTTP/browser and custody fault gates remain
pending. Producer and Study worker evidence is collected separately before
final integration; source compilation alone is not runtime qualification.

M3 public capability advertisement remains disabled until its production gates
are ready. M4 pure constructors and working-file helpers are independent work in
progress, not accepted Save As. Native execution, candidate external publication,
runtime capture and mixed-catalog extraction must retain explicit unavailable
guards until their admitted paths are concrete and qualified.

## First frozen execution subject

The first complete execution candidate had 232 product files, with retained
[source manifest](m3-first-execution-source-manifest.json) file SHA256
`d31893bd6c6562869c0a1fd63942eba17a8931ea5c07c9012eecf77ca023624b`.
All listed hashes matched before and after these required-real checks:

- Four actual custodian cases passed in 49.647 seconds, with no skip: canonical
  admission/GO and terminal payload ordering; cold history without Run owners or
  imported authority; SQL acknowledgement loss after actual GO-intent commit
  without sending GO; and filesystem checkpoint replacement uncertainty with
  exact same-host handle drainage/reconciliation. Raw log and hash receipt:
  `/workspace/scratch/tuldok-save-load-qa/m3-run-custody-first.log` and
  `m3-run-custody-first-receipt.json` in that directory.
- The one selected actual Study case failed in 7.519 seconds before SQL
  acknowledgement or GO. Reservation validation called a host-authorized
  material reader under a logical project reconciliation context. Its raw log,
  `/workspace/scratch/tuldok-save-load-qa/m3-study-one-frozen.log`, has SHA256
  `f55cb6b2135653e951eb58b74d53ef9c3a4c645861189300e7ca04d9559a0764`.
  The owner now uses the same pure retained-material codec on that path, keeping
  legacy behavior intact; the targeted regression passed. The actual Study
  rerun remains pending a new stable execution subject.

Independent review of that exact subject found four additional justified issues:
approved agents were rejected by ordinary execute guards; producer-only recovery
could release its writer before custody checks; normal reconciliation skipped
checkpoint CAS; and producer cancellation signals preceded canonical commitment.
The source fixes are integrated or owned, with current transport policy checked
before replay and cancellation split into preparation and post-acknowledgement
signalling. Actual PostgreSQL/HTTP cancellation faults passed without premature
signals. Two actual workspace cases passed in 3.457 seconds, proving an active
and then unknown producer retains its original store, root descriptor and real
flock during recovery, and a stale reconciliation request cannot drain it.
Relevant scratch logs are `m3-producer-cancel-journal-final.log` and
`m3-workspace-custody-first.log`. Approved-agent positive HTTP acceptance and
targeted independent re-review remain pending.

Subsequent implementation adds an ignored original-host custody index and
restart reconciliation, fixed runtime/package writer guards, independent fork
receipt namespaces (`project_operation_v2`, with exact v1 reading), and explicit
legacy extraction. These are later source changes: the first frozen execution
results are not presented as their validation. Current-source tests and review
must qualify their own effects before milestone acceptance. No duplicate full
campaign was started and no incomplete feature was merged.

## Later isolated qualification and recovery checkpoint

Three original-host crash cases passed in 66.118 seconds with no skips. The
2,422-file immutable qualification manifest has SHA256
`5f82530d0b86610e4e3aa645f4359d45f8c5d0b844341d356d73264fd31e4694`.
All hashes matched before/after. Actual subprocess termination followed admission
ACK, GO-intent ACK before GO, and actual recipe start. Fresh Open constructed no
Run owner or process; reconciliation used exact original physical SQL/journal
and observed drain receipts without GO replay. Logs and receipt are
`/workspace/scratch/tuldok-save-load-qa/m3-originalhost-crash-three-first.log`
and its adjacent `-receipt.json`.

The subsequent Study case exposed distinct real defects: background capture
called a decorated policy reader outside its internal settlement scope, and
explicit cold approval lacked reconstruction of exact canonical material bytes
into the new private cache. Both were corrected without restoring live authority
or changing Open. A fixture then needed explicit current-supervisor drainage
before Close. The original 10-second helper preparation deadline also covered
durable pre-GO acknowledgements. A separate bounded 60-second READY-to-GO phase
now permits that required publication, rejects late GO, and is reserved in new
material resource envelopes; historic envelopes are not rewritten. Seven real
custodian cases passed in 13.030 seconds, including delay beyond the old limit,
expiry without execution, EOF/cancel, streams and source drift. Evidence is
`m3-go-wait-protocol.log` and its receipt in the scratch directory above.

The complete actual Study case subsequently passed in 110.146 seconds, selected
one/no skips. All 2,441 files matched immutable manifest
`b1dbf055f7abc5888bc30079316032d687910343d557237664b3e547d6907449`
before/after. Both generic Runs completed; cold reconstruction preserved spent
budget and lineage while old Run/grant/admission/reservation SQL remained empty.
Fresh Continue/current approval and exact private-cache reconstruction were
required, and missing canonical bytes could not issue a grant or change the
checkpoint. Log `m3-study-current-go60.log` has SHA256
`ec0a79d6d1db6687525eedd9e11f9bb3320c7389d4564627d9d2cd1c0964ef63`.
Earlier failed logs remain retained rather than overwritten.

Candidate verifier preparation passed actual PostgreSQL/filesystem/canonical
publication checks without launching captured binaries or constructing Runs.
The extended positive/cold case passed in 64.254 seconds. Its selected-candidate
return was explicitly authored controlled fixture data; package, source, input,
disclosure, material and canonical receipt validators remained real. It makes
no scientific/model-quality claim. A separate actual original-journal recovery
case passed in 153.990 seconds: partial source/graph/model commits and directory
bytes survived a native failure; explicit abandonment cleared only the qualified
local marker after canonical ACK; final-journal ACK loss reconciled the existing
receipt without rerunning the writer; cold imported facts supplied no marker or
grants. Log `m3-candidate-native-recovery.log` has SHA256
`92e3f9d27f30c63b0ceff6390ebe9aeb0623c45f7f561185ff308c8f82d66a9c`.
That case preceded the later read-only journal-refresh strengthening; five
targeted PostgreSQL/filesystem guard/refresh cases passed in 2.206 seconds for
that later boundary.

The approved-agent HTTP workflow observed both real Run and Study completion,
canonical/SQL ACK before GO with exact current actor, wrong-agent 403, revoked
credential 401, explicit drainage, and cold Open without local authority. Its
full local case is **not passed**: fixture corrections for missing origin fields
and receipt-less reconciliation were retained as failed runs; the latest case
failed because it expected only 403/409 for an old cold approval while the
correct observed response was 404 `unavailable`. The final cold Study denial
tail remains unrun. Manifest
`08041e0eb447394fd9eab4620539b455cce7e9310dab8d8c616783046b678a39`
matched all 2,441 files; log `m3-approved-agent-http-reconcile-fixed.log` records
that distinction. No pass is inferred from partial positive phases.

A temporary executor disconnect interrupted process creation and a pending
Runtime-abandonment edit. Actual subsequent shell/status checks confirmed the
workspace survived. The pending patch failed to read its target and did not
apply. The already-running candidate recovery process was inspected first and
found successful; it was not rerun. Public runtime recovery/abandonment, public
package recovery wiring, remaining transport/UI gates, full independent review
and exact-head CI remain pending at this unaccepted recovery checkpoint.

## Qualified recovery and retained observations

Four actual PostgreSQL/HTTP runtime recovery cases passed in 13.729 seconds,
with all owned source hashes unchanged. They cover a real reserve failure after
durable intent and abandonment after its source disappears; final SQL deferred
COMMIT failure followed by exact-key recovery without recopying; original-host
physical projection recovery without configured aliases/source; stale binding
and checkpoint refusal; and foreign-clone intent remaining inert. Neither Runs
nor child-process construction was permitted in this offline capture fixture.
Log: `/workspace/scratch/tuldok-save-load-qa/m3-runtime-recovery-http-first.log`.
Four affected runtime identity/replay compatibility cases also passed in 2.410
seconds; that selection did not repeat the HTTP campaign.

The named Chromium runtime workflow passed four groups on immutable derived
manifest `d008a0a729812f1d2af8436d317a0dbe6d799d76598937812b9c75d746e399ba`.
All 2,449 copied source hashes matched before/after. The sole product delta in
that isolated copy enabled M3 for qualification; the shared feature flag stayed
false. It exercised paged Inspect, an actual high-reserve 409 after durable
intent, explicit abandonment with reason/key, a fresh capture, and Git cold Open
with source/config/cache absent. App audit-hook installation was asserted and
no child-execution attempt occurred. The cold role lacked source CONNECT.
At 390/1440 viewports document widths were 375/1425, with no overflow or runtime
errors and exactly one expected 409. Receipt:
`/workspace/scratch/tuldok-save-load-qa/artifacts/project-files-m3/run-aQAOCI/receipt.json`,
SHA256 `9c83fcacc68a10d5168933755f90aa46b8e3bddf15fe002a95850fb2a124ebc1`.

Retained producer input authorization passed its actual PostgreSQL/native-writer
case in 191.000 seconds. The selected candidate remains authored fixture data;
there was no scientific training/process claim. Original producer receipts,
current disclosure and scientific closure were validated, with source writes
and exact original-journal recovery. Log `m3-retained-producer-consumer-corrected.log`
has SHA256 `f9d03b1c89b05fb25dc9e0f8ed483c3c36d99918b02f943f73169e2b8e3b5390`.
The prior attempt reached those phases but failed a fixture message assertion;
that failed 231.061-second log remains retained separately.

The candidate terminal-before-wrapper window has its own focused actual
PostgreSQL gate: one case passed in 107.490 seconds. Complete native preparation
could not be abandoned, and exact proof reconstructed only its missing wrapper
acknowledgement without rerunning the writer. Log
`m3-native-wrapper-ack-recovery.log` has SHA256
`6381d125182d6d833b6ff0da5d7fd4b7876b600e808a6a61e7da3bde559ed4eb`.

Two thirteen-case focused PostgreSQL/codec selections passed for immutable
disclosure snapshots and affected history/Study behavior, followed by one
targeted forged-foreign-artifact snapshot negative. Snapshot facts remain plain
canonical text, survive later same-name payload replacement, retain old bytes as
unique and restore no disclosure grant. The additional negative passed in 0.320
seconds; log `m3-disclosure-foreign-artifact.log` has SHA256
`0185f43bbf13daaa69b7f058eddc24fa76d3c93005b0aca435414301f69d3f89`.
Independent source re-review cleared these snapshot and acknowledgement repairs.

Full M3 acceptance is still blocked by the explicitly fenced built-in probe and
native Run execution paths. Independent review confirmed that the external-script
subset cannot replace the reviewed current-family scope. A finite native child,
admission, payload and recovery slice is being implemented under the existing
authorization; no flag or documentation change waives its required real gates.
