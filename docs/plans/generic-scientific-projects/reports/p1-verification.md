# P1 project opening verification

## Delivered behavior

Projects can be opened from explicitly configured local roots and inspected in
Data/Pipeline/Runs. Saved manifests are immutable PostgreSQL snapshots. Referenced
data, recipe files, external evidence and missing requirements remain distinct
from imported records, executable graphs and completed Tuldok Runs. No project
code, dependency probe or checkpoint deserializer is invoked.

The implementation adds schema5 with an explicit quiesced upgrade. Schema1–4
definition hashes remain exact. External roots are read-only, descriptor-bound
and local-client-only; every path component refuses symlinks, unsafe traversal
and special files. Hash inspection and text previews have explicit bounds.
Opening the same ID with different source/root returns a conflict. Removing a
root leaves the durable snapshot visible but unavailable.

## Verification scope

- 11 real PostgreSQL/HTTP project tests pass, independently rerun by the source
  reviewer. They cover registration/reopen, unchanged source bytes/no execution,
  immutable conflicts, changed manifests, absent/rebound roots, unsafe paths,
  symlinks/FIFOs, malformed/deep/duplicate JSON, invalid Unicode, file/hash
  budgets, evidence refusal and hostile Host rejection.
- 71 affected schema, migration, rollback, storage and worker tests pass.
  The actual retained schema3 completed mesh Run survives explicit upgrade and
  backup/restore with exact graph/run/report/release bytes. See the
  [retained-run receipt](p1/retained-runs.json).
- Existing workspace browser regression passes all18 checks, retaining fixture
  dirty guards, catalog editing/review, context restoration and responsive focus.
- New [generic browser receipt](p1/generic/receipt.json) passes its four workflow
  checks. The [actual-lab inspection receipt](p1/actual-lab/receipt.json) passes
  five, using exact copies of five actual files from lab revision
  `e8a90bfef6b2955c502008ccc62443e29dd9f2ec`. Both verify two-project isolation,
  browser/server restart, no graph/run/record submissions, and unchanged files.
  Both run with the existing loopback-only transport injection and twelve
  external-denial/local-roundtrip canaries. This proves the named ordinary libc
  transport boundary, not an OS sandbox or denial of arbitrary syscall code.
- Python compilation, JavaScript syntax and scoped whitespace checks pass.
  The repository uses runtime contract checks and these existing static checks;
  no new language type-checking framework or certification is claimed.
- Adopted plan-contract validation passes. Source-based standards review covers
  ownership/contracts, persistence/migration, filesystem security, lifecycle and
  browser accessibility. Standards Engine is unavailable; no Engine certificate.

Final local discovery passed649 tests in412.564s, with two optional independent-reader skips. Both reader suites then passed separately under the installed qualification interpreter:11 point-cloud and9 volume tests, zero skips. Hosted CI is pending publication; local results do not imply hosted success.
Local browser receipts identify the precommit tree as dirty honestly; the
[implementation file hashes](p1/source-files.json) bind their reviewed material
content. Documentation/publication changes do not imply those receipts came
from a clean committed checkout.

## Visual and independent review

The source reviewer `/root/mesh_review` found no remaining blocker after correcting
file-size/hash consistency, invalid Unicode handling and misleading changed-
manifest wording. It independently ran the11 project tests. Root reviewed the
desktop and narrow screenshots; project reference cards, status labels and
external text remain readable without horizontal overflow. Browser checks use
keyboard form submission and navigation; external markup is rendered as text.

- [Actual source Data desktop](p1/actual-lab/project-data-1440.jpg)
- [Actual source Data narrow](p1/actual-lab/project-data-390.jpg)
- [Recipe references narrow](p1/actual-lab/project-pipeline-390.jpg)
- [External evidence desktop](p1/actual-lab/project-evidence-1440.jpg)
- [External evidence narrow](p1/actual-lab/project-evidence-390.jpg)

## Limits and next prerequisite

This qualifies project inspection, not execution or scientific data import. The
lab's checkpoint is only byte-inspected; its large result file is hashed but its
oversize text preview is honestly refused. Existing published scientific results
are external evidence, not reverified results. No new training or simulation was
performed. Runtime requirements remain declared/unqualified.

P2 requires representative actual lab field captures before fixing the scientific
schema. Tracked model weights, freeze/results JSON and synthetic UI fixtures do
not supply those arrays. Later permissions/external recipes remain P3–P6 work;
this stage's local filesystem gate does not pretend to implement actor roles.
