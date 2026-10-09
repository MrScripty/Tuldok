# Correctable caption input composition review

Exact reviewed source `10bc3f35d7a4b875eceaebb82c8d5b2085a81285`, tree
`4b3c03ea133854066d968d347f04f33cab6d7e69`, against published base
`4ed5466fd764e938999cca1d535e9a33379271a0`. No findings in this narrow
fresh-input/recovery-storage separation review.

The P2 is repaired: complete fresh body validation now executes before Store's
storage failure latch. Oversized guidance returns a clear 2,000 Unicode-codepoint
message, with no request admission, pending identity, stored entry or disabled
submit control. Correction followed by refresh can submit without reload. The
same reader still rejects corrupt persisted guidance through the distinct
fail-closed recovery path; submission checks that storage failure first. The
production delta leaves exact intent comparison, identity/body ownership,
reconciliation, ACK/history fencing and Python/provider/review behavior unchanged.
Non-BMP guidance is counted by code points, preserved exactly, not truncated.

Executed input-only controller and combined controller with all prior reload,
storage and shared-document cases; passed. Exact new input test on published-base
source fails at the intended durable-storage latch assertion. Independent probe
adds ASCII/non-BMP/mixed2001 guidance plus a credential URL: all prevent POST/
write without latching storage failure, then corrected2000emoji guidance posts
with exact stored/wire content after refresh in the same document. Previously
stored oversized non-BMP guidance remains unchanged and blocks submission.
JavaScript syntax and git diff --check passed; source/tree stayed exact and clean.

No tracked edits, aggregate/browser execution, remote/bot actions, models,
downloads, inference or unrelated work. Controller probes are VM simulations;
native browser textarea validity and actual workflow qualification remain
parent-owned. No real-model quality or performance claim.
