# Local classification proposal verification

Qualified runtime candidate `7b1938e3ef9b7ba499bafde1fa02e44fb90e8dc7`, tree
`a3b21243a9a990c0709f2f524085ee71cc4a9636`, starts directly at PR #17 head
`07ec464ba050cd532a2508ce86570a1ce9bcd394` on separate local branch
`feature/text-classification-proposals`. The following evidence commit adds
reports/documentation and corrects the README panel title; runtime, fixtures,
tests, CI and the aggregate runner remain identical to the qualified candidate.

All 46 aggregate commands are recorded: **44 passed, zero failed, two blocked**.
Python discovery passed **271 tests**, including **16 classification tests**.
All 43 inherited commands were retained, with new classification syntax,
controller and real Chromium gates appended. The aggregate took 243.136 seconds.
Every command binds the same candidate commit and unchanged code digest
`b52482aad290393c2b15dd07fdd5a1dda808dd03869ed828c4bba3bc70be627b`.
See [results](gates/results.json), [source and preservation summary](gates/summary.json)
and the adjacent raw command logs. The aggregate exits nonzero to report its two
blocked gates; this is not a full-green inherited consumer qualification.

The blocked commands are `node tests/browser_instruction_responses.cjs` and
`node tests/browser_combined_workbench.cjs`. Their unchanged pinned instruction
consumer requires absent TRL 0.23.1, Datasets 4.1.1, Transformers 4.56.2, CPU Torch
2.8.0+cpu, Accelerate 1.10.1 and Tokenizers 0.22.1. No consumer environment was
provisioned during this bounded classification stage. The classification browser,
canonical export assertions, combined controller and all other gates passed.
Rerun these two inherited browser gates in the existing pinned consumer environment
before claiming full inherited instruction-export qualification.

The new real HTTP/Chromium gate sends actual frozen text and exact label choices
to a bounded local synthetic provider. It covers a held admission with an early
404, a lost admission acknowledgement, unchanged explicit replay with one backend
request, changed labels and dirty editor blocking Apply, a lost Apply reply with
one draft write and idempotent receipt, retained fixed revisions and stale saved
sets, blocked draft export, separate explicit review, and an actual downloaded
canonical ZIP binding exact text, label, target evidence and acquisition provenance.
It also covers explicit abstention without Apply, rejection during a held unrelated
save and a subsequent save, cancellation/navigation/fresh intent, reload without
inference replay, keyboard entry, narrow layout and no browser runtime exceptions.
Final [session](component-artifacts/node-tests-browser_text_classification_proposals.cjs/test-results/text-classification-proposals/run-PfehWu/session.json),
screenshots and the reviewed synthetic ZIP are retained beside it.

Python HTTP/lifecycle tests additionally cover malformed/unknown/partial/oversized
output, exact Unicode labels without normalization, wrong/absent models, annotated
and stale source rejection, same-revision source/hash/original-text changes,
deletion and target changes, inflight source changes, atomic rollback/concurrent
Apply, catalog/body cancellation and late-output fencing, persisted restart
interruption without retry, and bounded 50-row SQL projection before Python decoding.
Exact source and response evidence remain available on individual request reads.

Independent backend review passed **12 additional probes** and independently reran
all 16 focused tests; [review](independent-review/backend_review.md) and
[receipt](independent-review/backend_receipt.json) report no findings. Independent
interaction review passed **10 ownership/lifecycle probes**, a synthetic provider
URL test, three controller suites and another actual Chromium run;
[review](independent-review/interactions/review.md) and
[receipt](independent-review/interactions/receipt.json) report no remaining findings.
Both reviews identify this exact candidate and hash their source/evidence. Earlier
composition observations and provisional output remain preserved, with corrected
candidate evidence distinguished from initial development runs.

All **959 historical tracked reports remain byte-identical**. The aggregate copies
inherited fixtures' new outputs into `component-artifacts` before restoring their
old destinations. Base hashes are in [base-and-preservation.json](base-and-preservation.json);
qualified changed-file hashes are in [candidate-source.json](candidate-source.json).
`initial-checkpoint` preserves the provisional run, including a corrected test-only
JSONL assertion failure. `focused-fixtures` preserves earlier synthetic runs.
An artifact manifest hashes this task's retained reports and archives.

Main remains `2fc4a46f12d73a0fa467d5482f68edb83d6df6af`; image-caption development
remains `c43a110c4b6ee1a85c932fa206b43091c0db7f3a`; published PR #17 remains
`07ec464ba050cd532a2508ce86570a1ce9bcd394`. Only repository-local MrScripty Git
attribution was used. No public writes, real inference, model downloads, credential
changes, new runtime dependencies or global Git changes occurred.

Limits: this is one existing unannotated text record per request, with 1–30 exact
labels of at most 80 code points and a bounded complete response of 256 KiB.
Surrounding label whitespace is rejected to match current annotation semantics.
Catalog/JSON validity does not prove provider compatibility or semantic quality.
Transport cancellation and late-output fencing do not establish when remote
backend compute stops. Invalid transport may lack a complete response payload.

Next publication step requires parent disposition: push only this new feature
branch and open a new stacked PR against `feature/caption-proposals-local-20261007`.
Keep PR #17 and main untouched. See [publication target](publication-target.json).
Integration and any real-provider/model-quality qualification are separate steps.
