# Text classification proposals

## Clean stale-judgment save ownership repair

Parent review of published `6aba384a90246aa2c9d344997561154710178586`
confirmed an ownership state missing from the earlier combined qualification:
opening a stale judgment resets its review to draft while `preferenceDirty`
remains false. Explicit Save still owns a meaningful rejudgment request. Apply
could replace the parent and clear that editor while the request was held, and
the later 409 incorrectly claimed its draft was retained. The reverse ordering,
Apply first and Save before its acknowledgement, has the same loss.

The minimal classification repair refuses Apply dispatch while `preferenceBusy`.
Validated judgment Save/Delete dispatch advances its existing intent epoch, so
the existing shared adoption fence protects a later save even after it settles. An
already committed classification remains a draft; preference proof is revoked
while the exact pending judgment editor and old parent binding remain available
for inspection after a conflict. No automatic operation is discarded or replayed.
Busy release permits a fresh explicit author action. Preference persistence,
review rules and classification admission recovery are unchanged. Repeated or
invalid save attempts do not acquire a new operation epoch.

Actual stale-judgment native fixtures cover both orderings and successful/failed
save release, including Save settling before the earlier Apply acknowledgement.
New qualification belongs in `reports/judgment-save-ownership-repair`;
all 3,559 current prior report files remain immutable. Run all 50 registered
checks and independent exact-source review before a normal PR18 branch push.
PR18 remains draft/unmerged; main/development and the owner's review state remain
untouched. No CodeRabbit request is authorized. Earlier combined reports below
remain historical evidence, superseded only for this missing ownership state.

## Preference development integration

Exact integration source `c0de883159025491d5283c52514c7c762f53c4cc` passed all
50 registered checks and 285 Python tests. Every 127-file source snapshot stayed
stable and all 3,339 prior reports retained their exact bytes. Both independent
reviews found no scoped issues. [Integration evidence](reports/preference-integration/verification.md).

Owner-authorized integration merges development
`321f710a9b185bf6e9eac518579c083079a6d751` into the existing PR18 branch from
`7ec7e47a090467fa37b68d33a7e81438828eea9d`. Five shared-file conflicts retain
both feature panels, script routes, editor guards, documentation and CI evidence.
Classification Apply synchronously revokes preference preview proof on success
or uncertain acknowledgement, while fixed judgment selections retain their
captured revisions. Combined answer/judgment intent epochs fence late adoption.

A new bounded Chromium fixture checks the actual combined controllers with
synthetic HTTP, including late judgment edits, rejection during judgment save,
preview invalidation and unresolved classification admission. The aggregate runner
now discovers all registered executable workflow checks without installing
dependencies; every original PR17 and classification gate remains required.
Qualification and independent review belong in a fresh
`reports/preference-integration` directory. The 3,339 prior local report files
are preservation-hashed before qualification. Only a normal push to the same PR18
branch is authorized after passing checks; PR18 still requires owner review.
Protected main/development writes, PR merge and CodeRabbit requests are excluded.

## Qualified review successor: cross-tab dispatch ownership

Exact repair source `824e3ee1181184e2284875e5a08ebd1406318bfc` passed all
46 aggregate gates and 273 Python tests. All 119 runtime/test source hashes stayed
stable. Independent native backend, interaction and final artifact audits found
no remaining scoped findings. [Repair evidence](reports/dispatch-ownership-repair/verification.md)
supersedes the older cross-tab cleanup claim; parent acceptance of PR18 remains open.

Parent review of published PR #18 head
`b1d0a453ea24653fa40f08c08f41e56375663521` reproduced a delayed initial
4xx clearing the shared recovery reservation while another explicit same-ID
POST was unresolved. The earlier qualification below does not qualify this
interleaving. Preserve its source, reports and failed probes unchanged.

The bounded repair commits a positive, safe-integer attempt generation with
the exact pending envelope in the existing IndexedDB transaction before every
explicit POST. An initial refusal may retire only the exact ID/body and its
unchanged captured generation. A later explicit retry advances that generation;
the older refusal leaves pending authority, mirror and local recovery intact.
Legacy or crash-restored pending evidence is never assumed to be a sole attempt.
Matching durable admission receipts may reconcile the whole ID. Failed commits,
malformed generation evidence, overflow and ambiguous 404s block inference rather
than discard evidence. No timer expiry, automatic retry or queued inference is added.
A known matching receipt may retire a malformed counter only when its recognizable
versioned attempt frame names that exact pending body. Foreign, opaque, orphaned
or unknown-version attempt evidence remains blocked; it cannot be discarded using
another request's receipt. This exception never supplies a dispatch generation.

Write set: the classification controller, its controller/native browser fixtures,
the synthetic fixture server, README and this plan/ledger. Backend admission and
other feature sources remain unchanged. Verify delayed 400/409/422, success,
lost acknowledgement, crash/reload, generation commit failure and terminal cleanup
ownership; then run all 46 aggregate gates and independent exact-source reviews.
Only PR #18's branch may be committed/pushed after qualification. No merge or
CodeRabbit request. New evidence belongs in a fresh dispatch-ownership-repair
directory; all 2,939 existing report files are protected by an immutable baseline.

## Prior qualification

Exact integrated source `97144cb85b274cf68e20e0952907787b28b3026a` passed
all 46 aggregate gates and 273 Python tests. IndexedDB admission recovery,
source/label fences, explicit abstention, atomic draft Apply and both proposal
ownership contracts passed independent backend, interaction and native artifact
review. [Current qualification](reports/admission-authority-repair/verification.md).

The final caption head `12690a58d9b2a781efd081f1a3e796313d5235c1` and landed
development merge `2f1d68ee29ec98a524bdf0f14d20b6024a25364c` are retained through
normal merges. Both panels remain intact; caption source/tests match development.
This branch began at requested PR #17 head
`07ec464ba050cd532a2508ce86570a1ce9bcd394`. Main remains
`2fc4a46f12d73a0fa467d5482f68edb83d6df6af`. Development was independently
advanced by the parent; this feature writes only its own branch and PR #18.
Repository-local attribution is MrScripty, with no global Git changes.

Draft PR #18 was previously published at
`12b174f7a7b2fd6aa36d71da450ad657a5443114`. Authorized publication updates
only this classification branch, retargets the draft to development and verifies
exact hosted CI. No merge or CodeRabbit request is authorized here.

All earlier qualification, negative race proofs, caption integration evidence and
the initial 45/46 retirement-fixture run remain immutable. All 2,801 pre-final
report files were preserved byte-for-byte. [Initial evidence](reports/verification.md),
[earlier recovery qualification](reports/recovery-persistence/verification.md) and
[preserved integration blockers](reports/final-caption-integration/verification.md)
are historical checkpoints. The former cross-tab Web Locks finding is repaired by
transactional origin authority; the stale memory assertion now checks actual
committed retirement evidence. Pinned test-only dependencies were provisioned in
an isolated environment with later authorization. No real inference, model weights
downloads or credential changes are included.

An author selects one existing unannotated text record, defines an exact bounded
list of label choices, selects a served model and explicitly requests a proposal.
The existing text is the model input; the model does not rewrite or import text.
This differs from grounded candidates, which rewrite an already classified source
and preserve its existing label. A proposal may select exactly one offered label
or explicitly abstain. Unknown labels, malformed JSON and partial output fail
without fallback. Structural validity does not establish semantic correctness.

The attempt freezes source text, source and target revisions/hashes, exact offered
labels, guidance, system prompt/version, provider configuration, seed and canonical
request hash. Complete bounded response bytes and hashes remain inspectable.
Polling projects summaries before Python decoding; exact evidence uses individual
attempt reads. One classification request runs at a time. Client admission IDs
reconcile lost acknowledgements and early 404s; explicit unchanged repeats reuse
that ID without another inference. Before POST, the client commits its bounded exact ID/body in an origin-wide
IndexedDB transaction, then writes the recovery mirror. Submission waits for
loaded authority after reload; Web Locks provide additional coordination. Changed intent is refused until an authoritative matching outcome;
summary absence and ambiguous 404s never release it. Visible author controls
restore the pending source/settings, followed by explicit same-ID retry. Storage
or lock failures and unrecoverable corrupt records fail closed. Cancellation fences late output, and restart
marks active attempts interrupted without resuming them.

Only explicit **Apply as draft** can atomically save the exact selected label and
its proposal receipt. Apply rechecks source identity, both revisions, absence of
an annotation, and offered labels. Repeated Apply reconciles its receipt without
another target/history write. Abstention never supplies a target. The editor also
guards unsaved changes, navigation, saves and changed request controls. Reject
changes only the attempt and must not claim ownership of an unrelated editor save.

Acquisition provenance, source bytes, rights, protected groups and parents remain
unchanged. Proposal evidence belongs to the target, persists through explicit
human review and canonical export, and remains in history after a target change.
Fixed selections retain captured revisions and become stale after Apply. Drafts
are ineligible for training releases; the author must review and explicitly
reselect current revisions.

Acceptance uses bounded local synthetic HTTP providers, Python lifecycle tests,
controller tests and real Chromium fixtures. Required cases include exact Unicode
labels, malformed/unknown labels, abstention, source/label changes, deletion,
cancel/restart, early 404 and lost admission/application acknowledgements,
rejection during an unrelated save, atomic rollback/idempotence, stale exports
and explicit human review. Run inherited aggregate gates with all historical
report bytes preserved and new outputs captured separately. Independent reviewers
check backend/composition and interactions against the exact local commit.

Subsequent authorization permits publishing this separate branch and a new draft
PR, without merging or requesting CodeRabbit. Its review base is PR #17's branch.
The final caption successor and its landed development merge are integrated
normally. PR #18 is authorized to target feature/image-caption-exports after
qualification and remains a draft awaiting review. No merge or CodeRabbit request
is authorized here. Real-provider compatibility and model quality require a
separately authorized stage.
