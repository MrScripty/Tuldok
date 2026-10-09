# Saved fixed dataset selections

Status: Verifying, 2026-10-06. Canonical bounded follow-on to the dataset-workflows
plan; operation `start`, admitted by the delegated owner-authorized cloud task.
The parent coordinates review/integration. Main remains frozen; no merge is authorized.

## Outcome and scope

Persist named, user-chosen record membership and exact source/annotation revisions.
Reopen the same references, report stale/missing/deleted/changed sources, and pass
those exact pairs into the existing release preview. Save/open never grants review.
Rename/delete are revision-checked. Filters remain independent; browser reload and
Back/Forward reopen via a saved-set URL. Cancellation and delayed results cannot
replace a newer selection or discard editor changes.

Current source plans define exact revision-pair selection and read-only preflight;
none calls for persisted dynamic search expressions. Fixed sets meet the delegated
request without inventing a query contract. The UI/API explicitly say `fixed`.
Dynamic saved searches remain unimplemented; they must be a separate explicit mode
if admitted later. Saving new membership creates a new set, avoiding silent refresh
or replacement of saved source semantics. Duplicate names are allowed; IDs identify sets.

## Base, ownership and write set

Verified Git fetch/ls-remote and PR4 metadata agree on
`feature/selected-release-preview-20261006` at
`a3f3cbead4137110dfa8af81c94178e6d53aa036` (PR4 draft). Main is
`2fc4a46f12d73a0fa467d5482f68edb83d6df6af`.
Separate branch `feature/saved-dataset-selections-20261006`, worktree
`/workspace/Tuldok-saved-selections`, draft target the verified PR4 branch.
This worktree is retained-protected for parent review and further UI iteration;
the parent owns its next integration/retirement disposition. No old branch or history changes.

Write set: `saved_selections.py`, `static/saved-selections.js`, narrow composition/routes
in `app.py`, the selection callback and opening-state button guard in `static/workbench.js`,
saved-set panel in `static/workbench.html`, small wrapping rules in `static/workbench.css`,
`tests/test_saved_selections.py`, `tests/test_saved_selections_controller.cjs`,
`tests/browser_saved_selections.cjs`, `.github/workflows/tests.yml`, README and this directory.
Shared touchpoints were reported before implementation. The other worker owns bulk real
import and generation compatibility: `synthetic.py`, `image_generation.py`, and its
branch remain untouched. Workbench and Releases contracts are consumed unchanged.

## Persistence and composition

SavedSelections owns one additive SQLite table and name/revision/membership lifecycle.
Dataset composes it with the existing Workbench lock/connection. Save validates the
whole selection and source availability/identity before one transactional insertion.
Rename/delete check revision while holding that same lock. No provider/background
work or second image store is introduced. The persisted table supports the initial
fixed schema only; immutable membership is stored as canonical JSON with source
hashes, not annotations or historical asset bytes. Listing returns metadata only.

Load reads each saved reference and observes the current source, reporting per-member
currency; it does not refresh saved revisions. Existing lazy image enrollment may
run, with existing ownership, but review/annotation/history never changes. Releases
still performs final revision/byte/lineage checks. A saved set is neither a release
snapshot nor authority to export. Missing records stay in returned membership.

The separate UI script consumes typed routes and existing selection/preview hooks.
Selection generation, cancellation and page-lifecycle fences revoke an older open's
ability to mutate the map. Save completion refreshes the set list without restoring
old membership. Load changes no editor state. Browser history is a reference to the
persisted set, not a copy in browser storage; no credentials enter these artifacts.

Standards source: MrScripty/Coding-Standards pinned
`dcc56f26e884ade260770beceba2501d3746200d`, Core/Router and applicable implementation,
verification/oracles/GUI, commit, documentation/tooling, frontend/accessibility,
persistence, contracts/evolution/protocols, concurrency, architecture/replay/code-design,
security and proportionality guidance. No AGENTS.md or .agents skill exists in Tuldok's
verified tree or workspace. The standards repository's authoring skill explicitly
excludes ordinary source edits; it was inspected and not invoked. Pinned source
guidance was read locally without mutating the standards repository.

## Required evidence and remaining work

- Real SQLite/reopen and HTTP contracts: repeated save/load, no approval/history
  mutation, fixed membership across filters/new records, stale record/source pairs,
  missing/deleted/tampered sources, atomic rejection, rename/delete conflicts and
  exact loaded release preview/export consumption.
- Controller transport ordering: repeated operations, cancellation/retry, late
  responses versus manual selection/filter changes, pagehide/popstate and delete conflict.
- Real Chromium workflow: save/open/export, reload and Back/Forward with dirty editor,
  stale/deleted sources, rename/delete/cancel, desktop/narrow screenshots and overflow.
- Complete existing Python/controller and all six existing real browser suites,
  plus new suites and syntax/diff checks. Controlled local providers only.
- Exact published head/base verification and hosted CI, when existing authorized
  access works. No credential repair, denied-call bypass, CodeRabbit request, merge,
  external model/dataset, network setting change or ONNX download.

Exactly one next slice: finish qualification, publish this isolated proposal as a
draft against PR4, report exact identities/evidence and remaining UI/review limits.
Independent review and final UI acceptance remain parent-owned.

[Execution ledger](execution-ledger.md) · [Verification](reports/verification.md)
