# Integration readiness review — 12 October 2026

## Decision and source boundary

**Ready for a draft integration PR for the completed M1/MB/M2 image slice.**
This review found no demonstrated P1/P2 blocker in that slice. It does not approve
a main merge, deployment, personal-data migration, new modality, or arbitrary
graph execution. Future text/audio proposals require their own evidence and a
fresh review of their combined changes.

Reviewed source: `feature/workspace-image-runs-20261011`,
`6d939359d3cef2464c2aff990dd58d50c4f8d791`. Remote `main` remains
`1bb2c3ae9d08432c53ddf9d4bf77fa5f62ad318c`; the feature is 19 commits ahead
and contains the main baseline. These refs and the two open draft PRs were
independently read through the authorized GitHub connector on 2026-10-12.
The feature has not been merged. See the compact
[remote evidence](integration-20261012-evidence.json).

This worker owns only this report and its evidence JSON, on
`review/workspace-integration-20261012`, admitted from the reviewed source.
The coordinating agent owns shared code/contracts, plan state, serial integration
and PR creation. No runtime/test file, existing PR, CI run, main ref or deployment
was changed by this review.

## Exact qualification evidence

| Claim | Exact evidence | Result |
| --- | --- | --- |
| Final feature lifecycle | [CI38181666802](https://github.com/MrScripty/Tuldok/actions/runs/38181666802), [job114595349909](https://github.com/MrScripty/Tuldok/actions/runs/38181666802/job/114595349909), head `6d939359d3cef2464c2aff990dd58d50c4f8d791` | Completed successfully 2026-10-11 22:56:30 UTC; 98 successful steps, zero skipped/failed |
| Python contracts/lifecycle | Same job's authorized log | 507 tests in 265.886 seconds; successful aggregate step |
| Real image browser path | Same job's authorized log | Real workflow gate passed; receipt path `build/qa/workspace-image-run/run-tOQxgm` |
| Caption readiness and recovery | Same job's authorized log | Repaired typed Pumas browser and all three workspace recovery cases passed; Pumas is a source-derived HTTP fixture, not native model inference |
| Focused M1 interface | [CI38181666836](https://github.com/MrScripty/Tuldok/actions/runs/38181666836), [job114595349921](https://github.com/MrScripty/Tuldok/actions/runs/38181666836/job/114595349921), same head | 14 successful steps, zero skipped/failed |
| Published screenshot provenance | [M2 manifest](../../../images/workspaces-m2/manifest.json) and [gallery](../../../images/workspaces-m2/README.md) | All 12 local files match their SHA-256; receipt says clean source and 14 browser checks |
| Source/capture equivalence | `git diff f725bd1806bfe5e27635eb817a403b602a14591a..6d939359d3cef2464c2aff990dd58d50c4f8d791 -- '*.py' static requirements.txt requirements-training.txt` | No runtime, static UI or dependency changes since captured/reviewed source |

These are existing completed runs, independently inspected; this review did not
restart or duplicate them. The earlier independent source review is useful
supporting evidence, but is not substituted for the final-head job result:
[M2 review](m2/independent-review.md), [verification](m2/verification.md).

## What the slice actually delivers

The opt-in `/workspaces` interface retains Data, editable Pipeline and Runs
context. The classic workbench and corner studio remain reachable. Explicitly
labelled browser fixtures cover modality states without representing execution.

For the current local catalog, the real path imports images, saves human labels
and reviews, previews/fixes family-aware splits, freezes an
`image_classification_v1` release, saves and validates a bounded graph, and
executes one scratch CPU TinyCNN. Runs provide validation metrics, per-record
predictions, verified export/checkpoint/artifact downloads, durable test-exposure
records, and correction links back to current Data. Corrections and later releases
do not rewrite old release bytes, saved graph snapshots or results.

Source inspection covered graph revision/token freshness; idempotency lookup
before replay; committed admission before child dispatch; process-group ownership,
cancellation and restart fencing; verified publication/download; and separate
validation/test visibility. The trainer chooses a checkpoint using validation,
evaluates test once afterward, and keeps test results outside default metrics.
It downloads neither weights nor packages. Its one-thread, 128-image/eight-class,
1–5-epoch bounds are a useful runnable baseline, not a quality or scale claim.

The executable graph remains the five-stage
release → validate → train → evaluate → publish recipe. Editable invalid drafts
can be saved, but disconnected/unsupported graphs cannot execute. Pantograph,
arbitrary nodes, user shell commands and generalized modality training are absent.

## PostgreSQL and recovery

The feature includes admitted MB `9e94d69484218e64a3ee1bddcf4c61d8aa93df16`
and the subsequently qualified combined M1/MB checkpoint
`907da2f3df974802f167dd4ce1905159bf50126a`. Main still uses SQLite.

Runtime metadata is local PostgreSQL; assets and large artifacts stay in the
dataset directory. A private local service and catalog manifest replace implicit
SQLite startup. Linux/WSL2 is the published platform; PostgreSQL 17.11 is the
qualified server, while the implementation accepts majors 16–18. Other majors
and native Windows/macOS are not implied to have independent qualification.

The [storage contract](../../../contracts/local-storage.md) owns explicit,
stopped-writer SQLite import into a new destination with a complete retained
source backup and exact row/file reconciliation. Unknown schema drift, malformed
types and actual NUL text fail closed. It does not repair arbitrary legacy data,
perform online migration or dual-write stores.

The [workspace upgrade contract](../../../contracts/workspace-storage.md) owns
schema 1 → 2. Source inspection confirms an explicit `--quiesced` gate, actual
catalog comparison with reference DDL, one transaction for three new workspace
tables and ledger update, repeatable verification, and no automatic startup
upgrade. Backup/restore uses the selected schema's table set, preserves identity
sequences and ordinary files, and restores into an absent catalog. Schema 1 and
2 restoration and migration boundaries are exercised in the completed suite.

Operators must stop every writer, back up the entire catalog, then explicitly
migrate/upgrade and select the new authority. Returning to an old SQLite or
schema-1 backup after new writes loses those writes; no reverse migration or
delta merge is promised. No personal dataset was migrated in this work.

## Reconciliation of older drafts

| Draft | Head and failure | Overlap and disposition |
| --- | --- | --- |
| [PR #32: workbench screenshots](https://github.com/MrScripty/Tuldok/pull/32) | `83b2df92d16acb80a03d1a5d19370489b464501a`; [CI38164151958](https://github.com/MrScripty/Tuldok/actions/runs/38164151958) has 88 successful, two skipped and one failed step | Only README, image provenance and three original-workbench screenshots. Retain separately; useful historical/classic screenshots, not evidence for M2. Root README overlap requires deliberate reconciliation if later accepted. |
| [PR #33: compact classic workbench](https://github.com/MrScripty/Tuldok/pull/33) | `581fa5ca471186ed641ec4bf6d134ee1ba807d22`; [CI38166806302](https://github.com/MrScripty/Tuldok/actions/runs/38166806302) has 90 successful, two skipped and one failed step | Changes classic HTML/CSS/JS, a layout controller, browser navigation helpers and tests. Retain as a separate competing layout proposal. Do not merge/copy it to claim compact M2 completion. |

The authorized PR #32 job log fails `browser_pumas_typed.cjs:122:20`; PR #33
fails `:124:20`. Both point to the same semantic wait for a failed second
caption job after programmatic `requestSubmit()`. PR #32's entire Pumas test
matches main exactly. PR #33 adds only a navigation-helper import and a reveal
call before an earlier classification screenshot; those two lines shift this
wait. The caption controller is unchanged by either PR.

The completed workspace repair at `acac0d32e89b67fa5d9b351ea058152adbe196e3`
changes only that test plus evidence documents. It deliberately holds the real
Apply response after backend commit, proves that the saved revision can be
visible while Apply is still busy, and proves that the old submission then
admits zero requests. It releases the acknowledgement, waits for complete action
readiness, physically clicks the enabled visible control, and asserts exactly
one new admission with the correct unknown-outcome request identity. The
two-provider-request/no-replay assertions remain. No timeout extension or
product change hides the failure. Current test SHA-256 is
`2280074da9ae31710ec79fe3bd498b6d44827e6aaf0a10b9f11f560603da600d`.

**Causal limit:** the historical PR logs lack the busy/admission diagnostics
needed to prove their exact timing. A shared unguarded readiness hazard and
matching semantic failure are demonstrated; that the hazard caused both
historical failures is a strong inference, not direct observation. PR #33 also
changes visibility, so its whole layout must pass fresh browser qualification
if later accepted. Neither draft becomes green merely because the newer
workspace branch passes.

No features from either draft appear in the reviewed branch. Its classic
`workbench.html` delta is two added/two removed lines for opt-in integration;
classic `workbench.css` and `workbench.js` are unchanged from main. Workspace
layout and embedded Data adaptation have separate files. Blindly adopting the
PR #33 moved-control/dialog model would create competing navigation ownership.

## Limits and small documentation findings

- **IR-01, P3; coordinating documentation owner:** the complete-backup paragraph
  in `docs/contracts/local-storage.md` still says `metadata.json` contains
  “all 19 tables.” That is schema 1's count; schema 2 has 22. The linked workspace
  storage contract and actual backup code correctly include all three workspace
  tables. Clarify the count during central integration; this is not evidence of
  missing backed-up rows.
- **IR-02, P3; coordinating documentation owner:** M2 verification describes the
  temporary `8094` demo as “currently” running. It is a dated observation of the
  earlier execution environment, not a portable launch or availability promise.
  Date-bound that statement while preserving the historical recovery evidence.
- Screenshot hashes and two representative narrow/desktop captures were checked
  anew. The reviewed gallery includes 390/1024/1440 layouts and genuine native
  200% zoom; static images do not replace the keyboard/navigation checks. New
  text/audio UI needs new screenshots and its own interaction evidence.
- Offline evidence denies ordinary libc outbound transports and permits local
  traffic. It is not a direct-syscall security sandbox or proof of every future
  integration. The full roadmap's A5/A7/A8 remain pending.
- Audio acquisition/playback/timed annotation, text training through all three
  workspaces, general 3D/volume training and real ASR are not implemented by this
  accepted image slice. Existing bounded mesh/sequence and text Data/export
  capability must not be renamed as completed generalized training.
- Local environment access was confirmed at this review's start. This reviewer
  did not launch the application or repeat training; the coordinating agent owns
  environment restoration and new feature execution.

## Handoff and review integrity

The coordinating agent can prepare an integration draft for the completed slice
with exact final-head CI links, explicit PostgreSQL migration instructions,
screenshot gallery and these bounds. Keep new text/audio changes in their
respective feature branches until each bounded workflow is independently
qualified. Recheck current target/source refs before serial integration; this
report accepts only the exact image source named above.

Applied the repository-adopted Coding-Standards
`dcc56f26e884ade260770beceba2501d3746200d`: Core, Router, Implementation
(required by Commit), Commit, Documentation, Verification and GUI evidence.
This non-authorizing report does not mutate shared plan authority; concurrent
proposal admission and lifecycle remain the coordinating owner's responsibility.
No language/framework change or standards upgrade is included.

Review verification consists of source/contract sampling, exact remote CI/log
inspection, PR file/test comparison, screenshot hash/visual inspection, report
link checks, JSON parse and staged-diff review. No runtime rerun is required for
these documentation-only findings. The review worktree
`/workspace/Tuldok-review-20261012` remains protected on its published review
branch for the coordinating agent's acceptance; that owner will record
integration/rejection and perform any authorized final cleanup. No branch
history was rewritten.
