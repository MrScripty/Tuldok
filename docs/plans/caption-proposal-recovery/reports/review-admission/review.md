# Caption recovery admission review

Exact source `300d1ebf84e53c739f856fb7115671cfaac057b9`, tree
`3b512dfac2fe6a5ce2f5014ad04a02688a1f21e1`, against published base
`4dc9c71f7e758bece5115361e57fa4e4ed866275`. Read plan and complete narrow
production/test delta, existing API/controller and backend admission contract.

## P2: retain earlier ambiguous admission through failed explicit repeats

At `static/caption-proposals.js:113`, every 4xx POST response clears pending
identity, including a repeat of an earlier unresolved POST. An acknowledgement
lost while the original request can still arrive leaves pending identity. An
explicit repeat correctly uses that same ID, but its transient409 rejection
(e.g. another active worker, as supported by `CaptionProposals.start`) does not
prove the original delayed request will never be admitted. The catch currently
clears the ID and allows a changed intent with a fresh ID. This defeats the
repair's stated ambiguous-admission ownership rule and can produce a later
original job plus the newly admitted job/inference.

`transient-repeat-probe.cjs` independently exercises this sequence against exact
repair source. Its recorded JSON reports identity cleared, changed intent
accepted and different fresh ID. Retain the earlier unresolved ID through a
failed repeat, or obtain an explicit terminal protocol fact. A fresh request's
definite rejection and rejection of a repeat of an unresolved request have
different proof scope. Add a bounded controller case for this interleaving.

## Verified repairs and evidence limits

Start-only, reject-only and combined controller cases passed independently.
The new controller start case against extracted exact published-base scripts
fails the early404 identity assertion, proving sensitivity to the original
finding. The repair retains identity through early404/list absence and GET
persistence while a POST is in flight; same-intent repeats reuse the body/ID;
changed intent is blocked while pending; recovered cancellation permits a fresh
ID. Reject no longer increments the annotation editor epoch, and the held-save,
subsequent-save, later-input and Apply/navigation checks pass. Python production,
CI commands and dependencies remain unchanged; test fixture request count is
local/read-only. Git diff --check passed and worktree stayed exact and clean.

No tracked source/report changes, browser/full suite execution, remote calls,
models/downloads or inference. The additional failure reproduction is a
controlled VM/fetch schedule; it does not itself execute delayed real HTTP
admission. Aggregate/browser qualification is separately owned by the parent.
Real-model capability and caption quality remain unqualified.
