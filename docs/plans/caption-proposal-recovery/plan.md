# Caption proposal recovery and rejection ownership repair

Status: locally qualified and independently reviewed; all 43 inherited gates passed
on source `ff91d0d920a57df6585ee84bcbfa204910b13438`, tree
`01741c7c219d64c0490e264252dc9dca5a0aedc8`. Both focused successor reviews report
no remaining findings. Publication is held for the parent. See `reports/verification.md`
and the hash manifest for exact source/tests, negative regressions and retained outputs.

Base: published PR17 `4dc9c71f7e758bece5115361e57fa4e4ed866275`, tree
`6bf88609588dbbfe51c0afc3aff1809db4120370`, retaining PR16 `ae094770` ancestry.
Isolated branch `fix/caption-proposal-recovery-local-20261007`, worktree
`/workspace/Tuldok-caption-recovery-local`. Main, PR16, PR17 and all retained worktrees
stay unchanged; no remote publication or inference with real assets is authorized.

Parent independent review reproduced two P2 controller gaps after PR17 qualification:

1. A start POST can be held before admission while a refresh obtains list absence
   and exact-ID 404. Clearing recovery identity then loses the same-ID guarantee
   when admission succeeds but its acknowledgement is lost. The backend already
   provides exact-request idempotency; the controller must retain the ID.
2. Reject increments annotation editor ownership despite changing no record. When
   an annotation-save acknowledgement is held, Reject revokes its ownership and
   leaves the editor dirty at the stale revision, causing the next save to conflict.

The controller retains unresolved identity across early and ambiguous absence.
An in-flight start keeps that identity even when a concurrent GET finds persistence.
A successful POST, a definite refusal of the first attempt, or an explicit later
persisted-state reconciliation releases it. A failed repeat, including a transient
409, cannot establish whether an older unknown admission persisted and retains its ID. Unknown outcomes block changed intent; unchanged explicit repeat keeps
the original ID. A recovered explicitly cancelled attempt permits a fresh request
with a new ID. There is no automatic inference replay. No new abandonment action
guesses that an unresolved request was cancelled.

Reject observes editor state without acquiring or revoking its epoch. Apply still
acquires ownership and fences later input/navigation. A legitimate held annotation
save adopts its successful acknowledgement through concurrent Reject; a later real
editor input still owns the unsaved draft. Backend persistence, human review,
rights/acquisition evidence and fixed selections are unchanged.

Narrow write set: caption controller, existing controller/browser regressions,
read-only request counter in the synthetic HTTP fixture, this plan and fresh repair
reports. CI commands, dependencies and all Python production modules stay unchanged.

Validation: independently failing old-source controller cases; held admission →
early 404 → lost acknowledgement → exact-ID repeat; changed intent while unknown; refused repeat retains an ambiguous ID while a
first-attempt definite refusal permits a fresh ID;
persisted lookup during in-flight start; explicit cancelled/new intent; held annotation
save → Reject → successful acknowledgement → next save; later-input/Apply fences.
Real Chromium/HTTP reproduces both races, verifies only one image-backend invocation
for the repeated request, and keeps the existing actual ZIP/consumer lifecycle.
Run all 43 inherited commands on one immutable repair source; preserve all 668 prior
tracked report files after every gate and retain regenerated artifacts separately.
Independent review must recheck both repairs and the bounded source/evidence scope.

The separate read-only Pumas compatibility audit lives outside this worktree at
`/workspace/tuldok-owner-review/caption-proposals-local/compatibility-audit/`.
It is not part of the controller repair and launches no runtime or inference.
