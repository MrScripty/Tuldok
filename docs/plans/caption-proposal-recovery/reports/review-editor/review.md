# Independent annotation editor recovery review

Exact source `300d1ebf84e53c739f856fb7115671cfaac057b9`, tree `3b512dfac2fe6a5ce2f5014ad04a02688a1f21e1`, against PR17 `4dc9c71f7e758bece5115361e57fa4e4ed866275`.

No actionable findings. `static/caption-proposals.js:75` acquires annotation ownership only for Apply; Reject leaves a pending legitimate annotation acknowledgement eligible for adoption. `tests/test_caption_proposals_controller.cjs:88` exercises held save, Reject, acknowledgement and next save; lines 100–105 retain later actual input fencing. Existing Apply/navigation/fixed selection and page lifecycle cases remain in the same executed test.

The full isolated controller passed. Its reject-specific regression fails extracted base source at the expected ownership assertion. A separate externally saved probe observes committed revision 3 adopted after Reject, dirty cleared, next save submitting parent revision 3, and both acknowledgement orders preserved. The same probe on extracted base source observes revision 2 and dirty true after the successful annotation acknowledgement, then fails the specific adoption assertion.

Companion admission delta retains uncertain ID across 404 and in-flight POST/persisted GET overlap; the executed controller also checks exact-body repeats and explicitly cancelled/fresh intent. Python backend, Workbench, API routing, CI registration, exporter and pinned consumer files are unchanged. No browser or aggregate execution, real inference, remote access, publication or candidate writes occurred. These controlled VM observations do not claim real HTTP/DOM behavior; the parent owns that concurrent qualification.
