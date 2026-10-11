# M1 / PostgreSQL controlled integration preparation

## Subsequent admission

The later parent handoff explicitly qualified and admitted exact MB commit
`9e94d69484218e64a3ee1bddcf4c61d8aa93df16`: hosted run38175261609 passed all
93 steps with no skips, including 32 browser workflows, typed-Pumas and consumer
gates; the clean local TCP run passed 458 tests. The pending-worker condition in
the historical preparation below is satisfied. Controlled integration now
proceeds on this branch, followed by combined application qualification before
one real M2 image-classification workflow. No personal-data migration, main
merge or deployment is authorized.

The actual merge retains all runtime owners and resolves only the three shared
plan records. MB's historical I11 is integrated I12; the separate UI I11 stays
distinct. Both existing lifecycle and M1 workflows register the integration
branch, and the M1 job gains its own isolated PostgreSQL service. Combined
qualification is pending; neither the previous UI nor MB run substitutes for it.

Current combined launch requires the MB runbook setup with a **fresh catalog**:

```sh
python3 -m pip install -r requirements.txt
python3 scripts/local_postgres.py init --directory /tmp/tuldok-integration-postgres
eval "$(python3 scripts/local_postgres.py env --directory /tmp/tuldok-integration-postgres)"
python3 app.py --port 8092 --data /tmp/tuldok-integration-catalog
# Open http://127.0.0.1:8092/workspaces
```

The paths above must be newly selected disposable paths, not an existing SQLite
catalog or initialized service. For reopen, use `start` and `env` rather than
`init`. Normal development should choose a persistent owned service directory.

## Status and exact inputs

**Preparation only; MB is not admitted or qualified here.** The delegated
2026-10-11 follow-up authorizes a separate integration branch, interface
inspection and integration preparation. It requires the database worker's final
qualified commit before MB is treated as satisfied. Main merge, deployment,
personal-data migration and M2 expansion remain outside this work.

Integration branch: `integration/workspaces-postgres-20261011`, created from
published UI `f41daed74a94e04d31babc43ec59b6fab3d59f8a`. Its product/test source
is the independently reviewed M1 checkpoint
`f8e8ea4e7718bc139e36ffea4002f77c5187cf82`. The UI branch retains the six
[published documentation screenshots](m1/implementation.md#published-documentation-images).

Inspected MB candidate:
`9e94d69484218e64a3ee1bddcf4c61d8aa93df16` on
`feature/local-postgres-metadata-20261011`. It follows implementation
`ac83d2c4d82165960e204eb39a72d542bc4a98ed` and documentation
`0d4d69d5fac0348d7f4e7eadfbf5f01dd79ca376`. The latest change preserves original
validated credentials in the independent-reader test helper; it does not change
the runtime or assertions. At initial inspection, its
[hosted run 38175261609](https://github.com/MrScripty/Tuldok/actions/runs/38175261609)
was still in progress; a later check during this preparation confirmed
**completed/success at exact head `9e94d69`**. The earlier failed hosted runs
remain historical failures. No final qualification handoff from the database
worker has been received, so hosted success alone does not admit MB here.

The screenshot publication's own
[M1 CI run 38175849991](https://github.com/MrScripty/Tuldok/actions/runs/38175849991)
passed at `f41daed74a94e04d31babc43ec59b6fab3d59f8a`.

This preparation branch contains **UI source and integration documentation
only**. No MB commit has been merged, cherry-picked or copied into its runtime.
It remains runnable with the M1 launch command. PostgreSQL launch/qualification
instructions below describe the future combined candidate, not current behavior.

## Merge preview and conflict resolution

Common product ancestor is
`1bb2c3ae9d08432c53ddf9d4bf77fa5f62ad318c`. A non-checkout preview used:

```sh
git merge-tree --write-tree \
  f41daed74a94e04d31babc43ec59b6fab3d59f8a \
  9e94d69484218e64a3ee1bddcf4c61d8aa93df16
```

It returned conflict exit status 1 and preview tree
`bc96cb15da7a462dccad37c57f29f6d38e0dcde5`. No index/worktree merge was started.
An earlier preview using symbolic refs produced `ce0de1e5...`; its conflict
marker labels differed. The full-SHA command above is the reproducible record;
the runtime files in both preview trees are identical.
Exactly three files have add/add conflicts because the independently published
branches each introduce the plan records relative to product main:

| File under `docs/plans/dataset-centered-workspaces/` | Required resolution |
| --- | --- |
| `plan.md` | Retain both M1 and MB authorizations, per-milestone evidence and remaining gates; do not restore MB's historical statement that M1 is merely planned, or mark MB accepted from M1 evidence |
| `execution-ledger.md` | Preserve both branches' dated provenance, corrections and exact-source receipts, then append the actual integration result |
| `issues.md` | Preserve both different I11 records: M1's missing pinned consumer environment and MB's hosted credential/qualification issue. Reserve integrated I12 for the latter with an explicit branch-ID mapping; close only with actual worker evidence |

`app.py` and README merged automatically in this preview. Independent content
checks confirmed all nine new workspace routes, all eleven UI-changed static
files byte-for-byte, and unchanged MB `metadata.py`, `migrate_sqlite.py`,
`backup_metadata.py`, `workbench.py`, `dataset_releases.py` and requirements.
The combined `app.py` passed Python AST parsing. This establishes only a bounded
source compatibility observation; the preview was not executed or qualified.
Repeat all comparisons against the final admitted MB SHA because it may change.

The read-only independent reviewer verified the six screenshot hashes, sizes,
source bytes and total; eleven UI static files, six MB owners, nine routes,
Python AST and three add/add conflicts. Review found the symbolic-ref versus
full-SHA preview hash mismatch documented above. The owner reran the exact
displayed command and corrected the recorded tree before publication. Review
found no additional scope or CI-qualification issue; no combined execution was
performed by either reviewer or owner.

## Required integration adjustments

| Surface | Concrete adjustment and owner boundary |
| --- | --- |
| `.github/workflows/workspaces-m1.yml` | Provision an ephemeral local PostgreSQL service and `TULDOK_DATABASE_URL` for this job after MB integration. A service in the separate lifecycle job is not shared. Retain contracts, the actual browser gate and screenshot upload; add this integration branch to its push filter |
| `.github/workflows/tests.yml` | Retain the database worker's service, authentication fix and every existing gate. Register the integration branch only when ready to run the complete combined candidate; do not replace full lifecycle qualification with the smaller M1 job |
| `tests/browser_workspaces.cjs` | Retain real current-catalog import/save/review and zero-POST assertions for fixture actions. It starts the app normally and inherits the environment, with no SQLite/SQL fixture setup to port. Qualify startup/error diagnostics and the complete walkthrough against the disposable PostgreSQL service |
| README and M1 launch instructions | Publish a separate combined-candidate launch using the qualified local-service helper and a fresh catalog directory. Existing `/tmp/tuldok-m1-demo` may contain SQLite and must never be silently reopened as PostgreSQL or automatically migrated |
| Shared plan records | Resolve the three conflicts as above; preserve the published M1 screenshots as source-bound historical evidence and add new combined-candidate captures with their own source identity |

The reviewed MB service contract retains `Dataset(path, *, dsn=None)`,
`make_handler(dataset)`, successful HTTP response shapes and revision conflicts.
Its storage outage and uncertain-commit cases use explicit HTTP503 codes
`storage` and `commit_unknown`. M1's Data adapter continues to call existing
HTTP/controller owners and must not automatically replay an uncertain write.
No new SQL, schema, fixture-to-real import or storage abstraction is needed in
the UI service. Native source, annotation, review and release distinctions stay
with the existing owners.

Use a disposable PostgreSQL service for combined browser qualification; its
catalog schemas are unique per fresh data directory. The test service's whole
lifecycle belongs to the harness/job. Do not assume deleting a temporary data
directory drops database schemas or apply cleanup to a user database. Real
migration, quiesced backup and restore continue to use the database worker's
qualified runbook and fixtures.

## Admission and verification sequence

1. Receive the database worker's final exact qualified commit, source-bound
   review and terminal hosted results. Fetch that commit and confirm its remote
   identity. A newer branch tip alone is not an admission signal.
2. Merge that exact commit into this integration branch without rewriting either
   feature branch. Resolve only the documented shared records and inspect all
   runtime auto-merges. Recheck the nine routes, unchanged UI/controller assets,
   MB-owned runtime and retained real Data behavior.
3. Add the isolated PostgreSQL service and integration-branch CI registration,
   preserving every pre-existing gate. Install only the already qualified app
   dependencies and use the database worker's disposable local service setup.
4. Run the workspace service/contracts and full M1 browser gate against
   PostgreSQL, then existing Workbench, corner, import/review/release, mesh and
   sequence regressions plus the complete required Python/controller/consumer
   gates in the pinned integration environment. Reuse worker qualification only
   where source/environment identity permits; do not infer success for the
   changed combined application.
5. Exercise reopen and stale revisions on the combined real Data path, and
   verify outage/uncertain-write behavior retains work without implicit replay.
   Inspect desktop/tablet/narrow captures, native 200% zoom and keyboard/repeated
   actions. Retain exact source, fixture/real labels and provenance in receipts.
6. Obtain independent review and inspect terminal hosted results on the combined
   exact SHA. Report integration readiness separately from maintainer product
   acceptance. Do not merge main or deploy.

## Design boundaries before M2

No M2 design is broadened by this preparation. The fixture graph/run store stays
isolated and real execution remains disabled. The current catalog navigation
handle is not promoted to a durable dataset identity just because MB creates an
opaque ID; a later owned domain/API boundary must expose that identity before
real graph/run references are persisted.

The existing S1 decision still needs an explicit result before M2: qualify a
Pantograph host boundary, or deliberately choose the bounded local DAG. M2 also
needs separately admitted graph/run persistence, execution ownership and the
real image trainer/artifact lifecycle. Report those choices to the parent before
implementation; this branch makes none of them implicitly. No training metrics,
checkpoint or production audio/3D capability is created by combining UI and MB.
