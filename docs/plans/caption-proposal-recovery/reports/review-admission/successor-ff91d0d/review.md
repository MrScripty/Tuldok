# Final caption recovery admission review

Reviewed exact head `ff91d0d920a57df6585ee84bcbfa204910b13438`, tree
`01741c7c219d64c0490e264252dc9dca5a0aedc8`, against published base
`4dc9c71f7e758bece5115361e57fa4e4ed866275` and the exact repair delta from
`300d1ebf84e53c739f856fb7115671cfaac057b9`. No findings remain in this
bounded admission/controller review. Original 300 finding and probes are retained
unchanged in the parent directory.

The catch now releases pending identity on a first-attempt definite4xx refusal,
while retaining an older unresolved identity after a failed repeat. Independent
probe passed original ambiguous admission -> same-body/ID repeat409 -> changed
intent refusal -> same-body/ID successful repeat/release. It also passed fresh
first-attempt409 -> released identity -> changed intent with a fresh ID. This
proves the two proof scopes remain distinct and no inference is automatically
replayed. Existing early404, in-flight persistence, recovered cancellation,
Reject/save/editor ownership and navigation/timer assertions remain intact.

Executed start-only, reject-only and combined controller cases; all passed.
The exact final start case failed 300 at the repeated409 identity assertion and
failed published4dc at the early404 assertion. These failures reach each intended
boundary independently. Git diff --check passed; worktree remained exact and
clean. Source hashes and actual probe observations are in receipt.json.

No tracked edits, browser/full suite execution, remote calls, models/downloads
or inference. Reproduction uses bounded VM/fetch schedules rather than delayed
real HTTP; parent owns concurrent aggregate and browser qualifications.
Real-model capability/quality remain outside these checks.
