# Text classification proposals

Draft PR #18 is published at `12b174f7a7b2fd6aa36d71da450ad657a5443114`;
its 46 hosted gates passed. Local normal merge
`71752fadd68efd092f53ee356ffb64061fa064da` integrates caption successor
`10de10b6710976570ace33b033ffb2349995edec`, preserving both panels. Local repair
`8235672a8482e10e95df7a6d5b05540325f66816` aligns fresh classification URLs
with backend validation and passes focused controller/backend/native checks.
It has not been published. [Focused evidence and blockers](reports/final-caption-integration/verification.md).

Full integrated qualification and publication are paused: the caption author is
repairing additional fresh validation gaps, and native review reproduced a
classification cross-page recovery overwrite despite Web Locks. A transactional
origin authority is being developed locally. Keep all prior reports immutable;
receive the next final caption SHA from the parent before integrating again.

Implemented and qualified at
`c5500cba5021949bccf45d2124ee5e2910dc5c92`: all 46 aggregate gates and 271
Python tests passed with exact stable source evidence. Independent backend and
interaction reviews cover durable admission recovery across reloads and pages.
[Current qualification](reports/recovery-persistence/verification.md).
The [initial qualification](reports/verification.md) remains immutable historical
evidence; its two dependency blockers were subsequently resolved in an isolated
pinned consumer environment.

This new development slice starts at published PR #17 head
`07ec464ba050cd532a2508ce86570a1ce9bcd394` on local branch
`feature/text-classification-proposals`. Main remains frozen at
`2fc4a46f12d73a0fa467d5482f68edb83d6df6af`; image-caption development remains
`c43a110c4b6ee1a85c932fa206b43091c0db7f3a`. This slice does not write those
branches or PR #17. Its author independently advanced PR #17 to
`4ed5466fd764e938999cca1d535e9a33379271a0`; integration with that successor is
pending and currently conflicts in `static/workbench.html`. Pinned test-only
dependencies were provisioned with subsequent authorization. No real inference,
model downloads or credential changes are included. Repository-local attribution
is MrScripty.

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
that ID without another inference. Before POST, the client durably stores its
bounded exact ID/body under a per-origin Web Lock and restores it synchronously
on full reload. Changed intent is refused until an authoritative matching outcome;
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
The independently advanced caption successor must be integrated and qualified
before the draft can merge; the current qualification applies to the exact
classification candidate from the requested original base. Real-provider
compatibility and model quality require a separately authorized stage.
