# Classification admission recovery across tabs

Exact source `824e3ee1181184e2284875e5a08ebd1406318bfc`, tree
`45bbb665da96a719d5e9ae900ce6439bcd2e1f70`, passed all 46 aggregate gates
and 273 Python tests in 311.037 seconds. Independent backend and interaction
reviews report no outstanding findings. The final native artifact audit checks
the actual downloaded ZIP, source/proposal evidence, screenshots and cross-tab
transport observations. PR18 remains draft and requires parent acceptance.

## Problem and repair

Parent review of published `b1d0a453ea24653fa40f08c08f41e56375663521`
found a P2 cleanup race. Two tabs explicitly POSTed the same reserved ID/body.
The first tab's delayed initial 4xx removed IndexedDB pending authority and its
recovery mirror while the second dispatch remained unresolved. Changed intent
could then obtain a fresh ID. Independent pre-fix probes preserve four
400/409/422 and lost-acknowledgement reproductions in `reproduction/`.

Every explicit dispatch now atomically commits a versioned attempt generation
bound to the exact pending envelope before transport. The initial-refusal cleanup
transaction compares exact ID/body and the captured generation. A later explicit
retry advances the generation, so an older refusal leaves authority, mirror and
local recovery untouched. A generation write/commit failure sends no POST.
Counters are positive safe integers, with no wraparound or expiry.

Legacy or crash-restored pending evidence remains unknown; initializing its
counter does not make it a sole attempt. Explicit unchanged retries retain the
same ID/body. Reload, page closure, lost acknowledgement and GET404 do not infer
or retire a request. A matching persisted admission receipt may reconcile the
whole ID because backend admission is idempotent on its exact request hash.
Old receipts still compare exact identity and cannot erase a newer admission.

A matching positive receipt may recover a corrupted counter only in a
recognizable version-1 attempt frame naming the exact valid pending envelope.
POST and refusal cleanup remain strict. Foreign, opaque, unknown-version and
orphan evidence remains preserved and blocked; normal atomic claim/retirement
cannot create an orphan. No automatic inference, fallback label or retry queue
was added. The earlier live dispatch-mutex proposal was superseded.

Production changes are confined to `static/text-classification-proposals.js`.
Backend, app composition, Workbench, release projection and caption sources are
unchanged from b1. Existing frozen-label validation, abstention, cancellation,
summary polling, draft-only atomic Apply, provenance and editor ownership remain
covered by all inherited gates. Documentation and classification controller/native
fixtures are the remaining changes.

## Evidence and limits

- `qualification/gates/` records all 46 commands, exact start/end source identities
  and logs. All 119 runtime/test files retain aggregate SHA-256
  `e720c4d86a085c051f4bc65ffe46265189747c54ea49adb5eb274e3ca6fc80f7`.
  Every source diff is empty; 77 component artifact hashes are verified.
- Backend review covers 16 native IndexedDB boundaries, including cancelled
  ConstraintError defaults, transaction abort, exhaustion, stale generation CAS,
  positive counter recovery and successor protection. Real loopback HTTP proves
  busy409, GET404, later identical-ID202 admission, delayed409 delivery and one
  synthetic provider request; replay after a source edit adds no inference.
- Interaction review covers 11 cases, including the original overlapping
  dispatches, stale refusals, lost replies, full-context reload/404, explicit
  generation-3 retry, canonical recovery and foreign evidence preservation.
- Final native `run-YIRFBf` retains nine artifacts. Four actual cross-tab cases
  check exact bodies, generation1→2, pending/mirror retention after delayed409,
  changed-intent POST0, success/lost-ACK/crash recovery and old-receipt cleanup.
  Provider deltas are 1/1/2/1; retries do not replay accepted inference.
- All 2,993 pre-run report files remain byte-identical, including 2,990 tracked
  files and all 2,939 original published report files. Focused dirty-source runs
  are explicitly labeled and are not final exact-source qualification. Failed
  fixture initialization/barrier runs and the corrected timing-probe status
  assertion remain preserved alongside the passing evidence.

All providers are bounded synthetic fixtures. Real-provider compatibility,
semantic label quality and training quality remain unqualified. Available origin
storage and Web Locks remain required. No model downloads, credential changes,
merge, CodeRabbit request or writes to another branch were performed for this
repair. The previously published caption CI navigation failure and its bounded
passing retry remain preserved outside this frozen evidence tree.

The evidence-only successor must retain all 119 qualified runtime/test hashes.
The authorized next step updates only PR18's branch and description, then checks
both exact-head hosted CI runs. Parent review remains the acceptance step; main
stays `2fc4a46f12d73a0fa467d5482f68edb83d6df6af` and development remains
`2f1d68ee29ec98a524bdf0f14d20b6024a25364c`.
