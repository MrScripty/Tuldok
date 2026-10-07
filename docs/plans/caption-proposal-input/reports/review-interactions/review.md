# Correctable fresh caption input review

Exact source `10bc3f35d7a4b875eceaebb82c8d5b2085a81285`, tree `4b3c03ea133854066d968d347f04f33cab6d7e69`, base `4ed5466fd764e938999cca1d535e9a33379271a0`.

No actionable findings. The fresh body is validated before captionProposalStore, so invalid guidance remains a correctable form error instead of entering the durable-storage failure latch. The same validator reading stored recovery still preserves invalid evidence and blocks admission. Existing sync/store ownership, GET/reconciliation, Apply/Reject and editor functions are byte-identical; backend, CI, release owner and consumer files are unchanged.

The registered controller gate passed all existing lifecycle tests and new 2000/2001 ASCII/nonBMP/mixed boundaries. Its new input regression fails preserved base source at the expected latch assertion. A separate probe confirms 2001 ASCII creates no storage/pending/POST, then correction plus refresh admits exact combining/nonBMP 2000-codepoint guidance without reload. It also confirms invalid edits cannot discard an unknown prior ACK/404 identity, fresh invalid URL/fractional seed can be corrected, and oversized stored evidence remains fail closed even after correcting the form.

No candidate/report writes, browser/full-suite rerun, real inference, remote actions or publication occurred. Controlled VM proofs establish the examined correction/recovery contract; parent owns aggregate and actual Chromium qualification.
