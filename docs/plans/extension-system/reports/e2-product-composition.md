# E2: accepted product composition

Feature composition `0509900c349239d66a18126eb83697297eb14a0b` includes published
product `f994228cdc7495d0ee29d1527fbe975acc62be5d` after the frozen 0b A-only
retention witness finished. It preserves the actual source/cold host `4b68c51`,
masked consumer host `f01f896` and retention host `0572ad9` as historical execution
provenance. Their receipts are not relabeled as executions of the composed head.

The only difference from that product is `tests/qualify_extension_fields.py`:
complete canonical root-map preservation, canonical bound wrong-Task publication
refusal and accurate canonical source-mode reporting. All other 1,385 tracked
product files match, including the accepted stronger SDK parser, author
verification recovery, all 149 application files and the independent B consumer.
The legacy wrong-Task branch is AST-identical.

Post-composition checks ran in a separate PostgreSQL database. The six affected
modules ran 61 cases: 59 passed and two explicit actual-receipt-only A/B checks
skipped because their main-only private recovery/selection inputs are absent
here. The checks cover author recovery, A/B retention driver contracts,
cross-material refusal, SDK conformance, canonical driver guards and canonical
P5 profile. All 23 independent B kernel/contract/consumer synthetic cases also
passed in the validator-only environment. These tests performed no new source
Run admission or numerical training. The [test receipt](examples/e2-product-composition-tests.json)
records the exact composed host and modules; it contains no database credentials.

The [independent read-only review](examples/e2-product-composition-independent-review.json),
SHA `2614bc811bb6d09688c694cdd9c714dfb6c844d16b5dc386faf783d2cb413eca`,
verified the complete product comparison, exact SDK/recovery preservation,
frozen A/B hashes and root-map/legacy-branch invariants. It opened no catalog,
database or Run. Main's separately retained actual B consumer execution remains
distinct from the frozen independent consumer authorship here.

Exact-head GitHub CI and the integration lead's serial PR acceptance remain
merge gates. No PR was merged and no dependent branch was deleted by this worker.
