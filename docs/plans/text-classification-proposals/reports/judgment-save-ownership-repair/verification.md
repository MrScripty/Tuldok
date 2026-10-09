# Clean stale-judgment ownership repair

Qualified source `f2b61ce3ebcae8380dcbea9c384c124e803083be`, tree
`39491c6e3b8ff1582c5dfe870f199f4304605e35`, parent published PR18
`6aba384a90246aa2c9d344997561154710178586`. Repository-local MrScripty attribution.
The following evidence successor changes only this report tree and plan/ledger
status; all 127 qualified source hashes remain identical.

Parent review found a state absent from the previous qualification: opening a
stale judgment resets review to draft but leaves `preferenceDirty=false`. Its
explicit Save rebinds current evidence and is meaningful author intent. Apply
could replace its parent and clear that editor while Save was held, then Save's
409 falsely claimed the draft was retained. Independent published-code probes
and real Chromium reproduced both Save-first and Apply-first orderings. Earlier
signed claims and all prior evidence remain unchanged as historical checkpoints.

The production repair changes only two sites. Classification Apply refuses
dispatch while a judgment save/delete is busy, before claiming an editor epoch
or sending a decision POST. A validated judgment Save/Delete advances its existing
edit epoch. The existing shared parent-adoption fence therefore preserves later
save intent both while it is pending and after it settles with success or failure.
Invalid/refused operations, cancelled Delete and repeated busy clicks do not
advance that epoch or send extra POSTs. No queue, automatic retry or new storage
schema is introduced. Preference persistence, backend CAS, classification
admission recovery, frozen labels/configuration and draft-only Apply are unchanged.

The initial preflight plus live-busy adoption guard passed eight native cases,
but independent probes showed it still lost the editor when Save settled before
the held Apply acknowledgement. Those source snapshots, passing focus run and
negative traces are preserved. The final epoch repair supersedes that uncommitted
approach. An already committed classification remains a draft and invalidates
preference proof; its older reply cannot silently replace the later judgment
editor or its old parent binding. Author inspection and fresh explicit action
remain necessary to reconcile stale evidence.

All **50 registered aggregate checks** passed on the exact committed source,
including **285 Python tests**, in **442.975 seconds**. Every gate retained the
same head and 127-file source snapshot; the non-report diff was empty. Aggregate
source SHA-256 is
`352aa0c4a5379d28249ec2c35e1250022177b629fd0b881245124c70e2308d73`.
[Summary](qualification/gates/summary.json), [all results](qualification/gates/results.json),
[qualification and preservation](qualification/qualification-and-preservation.json).

The final real Chromium fixture preserves the original five combined cases and
adds five clean stale-judgment orderings: Save-first conflict and success release;
Apply-first with Save still held; and Save conflict/success fully settled before
the older Apply reply. Actual judgment HTTP statuses are 409/200/409/409/200.
Both busy-first Apply attempts send zero decision POSTs. The exact editor, form,
review, request bindings, fixed selections, recovery state and displayed parent
survive the tested late replies. Success before Apply uses a transport hold before
backend admission; success against an already changed parent would correctly
conflict. Backend Apply can commit while the display retains the later author's
editor; no acquired provenance or human review is changed.
Qualified native artifacts are under
`qualification/component-artifacts/node-tests-browser_classification_preferences_integration.cjs/test-results/classification-preferences/run-NnNsjB/`.
[Ten-case focused receipt](focused-native/focused-ten-case-receipt.json) links both
published negative traces and the preserved eight-case intermediate focus.

Independent backend review verifies seven byte-matching focused cases and
unchanged backend/schema/admission code. Independent interaction review reruns
thirteen composed cases on this exact commit, including both published loss
states, settled-success/conflict lifetime, Save/Delete epoch boundaries, later
inputs, repeated/invalid/refused operations, Reject ownership and unchanged
admission generation recovery. Their setup-only diagnostic failures and all raw
negative/positive probes remain preserved. Final aggregate/artifact reviews are
stored separately from earlier focused signoffs.
[Exact backend signoff](independent-review/backend/review_f2b61ce.md),
[final backend aggregate review](independent-review/backend-final/review_final_f2b61ce.md),
[final interaction review](independent-review/interactions/aggregate-audit-f2b61/review-aggregate-f2b61.md),
[UI artifact audit](independent-review/ui-artifact-audit/frozen-artifact-audit.json).
Both final reviews verify all 50 gates, 92 component hashes and the frozen
146-entry qualification manifest, with no remaining scoped findings.

All **3,559 existing reports** remain byte-identical: 3,551 tracked and eight
preexisting ignored/untracked. Every byte also matches the external backup
`/tmp/tuldok-judgment-busy-preflight-history-5vbi6pji`.
[Prior hash map](prior-evidence-hashes.json). Fresh outputs are captured before
restoring inherited report bytes; the final artifact manifest covers only this
new evidence tree. Raw stdout retains its original whitespace.

Existing preference DPO, instruction consumer and classification/caption native
workflows pass using the already provisioned pinned environment and offline
flags. No real inference, model-weight download, dependency/credential change or
training-quality claim is included. Only a normal push to the same draft PR18
branch and exact hosted CI verification are authorized next. Main `2fc4a46…`,
development `321f710…` and the owner's review state remain untouched. PR18 remains
unmerged, with no CodeRabbit request. Publication receipts stay outside this
frozen tree; real-provider quality remains unqualified.
