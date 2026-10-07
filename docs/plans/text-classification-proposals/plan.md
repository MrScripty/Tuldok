# Text classification proposals

This new development slice starts at published PR #17 head
`07ec464ba050cd532a2508ce86570a1ce9bcd394` on local branch
`feature/text-classification-proposals`. Main remains frozen at
`2fc4a46f12d73a0fa467d5482f68edb83d6df6af`; image-caption development remains
`c43a110c4b6ee1a85c932fa206b43091c0db7f3a`. PR #17 is unchanged. No publication,
real inference, model downloads, dependency provisioning or credential changes
are included. Repository-local attribution is MrScripty.

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
that ID without another inference. Cancellation fences late output, and restart
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

Publication is a later parent decision: review the qualified commits, then publish
the separate feature branch and a new PR without modifying PR #17 or frozen main.
The new PR should use the PR #17 head as its review base until integration is
explicitly authorized. Real-provider compatibility and model quality require a
separately authorized qualification stage.
