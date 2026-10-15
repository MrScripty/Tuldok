# P2 verification: immutable composition and finite-study admission

Status: local implementation/review verified; committed-head CI and merge remain
pending. I2 is not closed by these local receipts. Initial P2 implementation is911da9c on merged P1 main8673509.
E1 main91c5e96 is composed by merge0100712; the two app.py route conflicts retain
the exact union of Model/Study guards and E1 snapshot/auth/strict JSON behavior.
Accepted inert SDK main1a5c596 is composed by merge06d397b. Its15 additions and
ledger union leave P2 application owners unchanged. Independent review verifies
canonical/copied SDK schema bytes, source and test owners match accepted main.
No user catalog was migrated, training campaign launched or telemetry activated.

## Behavior and ownership

Captured Model Definitions retain inert source and policy bytes. Pipeline owns
v2 draft CRUD and immutable external composition. Study owns finite intent,
checked membership and conservative reservations; Runs/Access keep their existing
queue, supervisor, exact one-use grants and mandatory audit. No second process
owner, automatic retry or prospective grant was introduced.

The full composed RecipeMaterial SHA is owner-approved via studies.approve.
Executable preflight SHA stays independently bound to the full composition, actual
Run and durable grant/Trial association; legacy standalone approval is unchanged.
Namespaced Runs keys preserve independent Study-scoped request keys. Public
models/recipe drafts/Study reads are bounded and later reservation pages reject
changed revisions. The shipped project_cli call command and MCP consume the same
selected registry and current authorization. Frozen f588 discovery remains exactly
56 operations and digest `cb070a69ebd35b48e4f95a57ca01647c75bd7567521429e49efc3a3a1daebae8`.
The new capability manifest is 78 operations / 217,230 bytes, below 1 MiB.

The implemented external profile explicitly has opaque outputs, unsupported
numerical evidence and unsupported automatic checkpoints. Model-aware classifier
compilation/evidence is unavailable until P3. Draft syntax is not an executable
qualification. Candidate selection, package closure/fresh inference and scientific
acceptance remain P4/P5 gates. No absent GPU/physics capability is counted as passed.

## Actual local qualification

Disposable PostgreSQL17.11, private Unix socket/no TCP. Python3.12.14 isolated
base+hash-locked optional agent environment: psycopg3.3.6, MCP1.30.0,
jsonschema4.26.0, pydantic2.14.1 and anyio4.15.1. Agent holdout parity explicitly
selected the separately installed actual Torch2.8.0+cpu/vision0.23.0/sklearn1.7.2
runtime. External neutral executions use the qualified system Python3.13 contract;
they do not assert a model result. No skipped test below is counted as passing.

Commands use the private test DSN and
`/tmp/tuldok-model-dev-agent-pinned/bin/python -m unittest discover -s tests -p PATTERN -v`.
Agent regression additionally sets TULDOK_TRAINING_PYTHON to the private CPU runtime.

| Pattern / actual boundary | Passed | Skipped | Elapsed seconds |
| --- | ---: | ---: | ---: |
| test_experiments.py |32|0|98.962|
| test_model_definitions.py |7|0|6.965|
| test_study_admission.py |5|0|15.797|
| test_external_runs.py |11|0|66.641|
| test_agent_*.py |53|0|309.902|
| test_mcp_stdio.py |17|0|38.970|
| test_workspace_metadata.py |38|0|79.572|
| test_execution_approvals.py |9|0|5.981|
| test_access.py |10|0|8.734|
| test_runtime_snapshots.py |12|0|6.948|
| test_spatial_storage.py |9|0|12.841|
| test_metadata_migration.py |18|0|22.074|
| **Distinct cases** |**221**|**0**|Not a sequential benchmark|

Key proofs use actual owners and PostgreSQL, not injected completion rows:

- Two connections compete for one Study revision; one Run/grant/reservation wins.
  Separate peer credential/grant revocation and stop-before-admit leave no attempt
  or consumed grant. Stop commits its epoch before actual queued cancellation.
- True PostgreSQL COMMIT executes before injected lost acknowledgement: a fresh
  connection sees durable Study/Run/grant, capture persists and no wake occurs.
  Confirmed commit followed by response-read/wake failure also retains custody.
- Exact retry consumes a new grant/slot, retains material and parent linkage.
  Configured runtime-policy drift refuses a retry without a new charge. Source
  drift refuses admission. This does not claim an actual installed runtime wheel
  was changed or any optional hardware was exercised.
- Actual neutral helper/descendant completes with drained custody. Unknown-state
  fault composition keeps worst charges/closes epoch; existing actual stopped-
  helper tests qualify the underlying real unknown/drainage boundary. Dropping a
  queued owner's connection and reopening does not replay it or refund its grant.
- Complete stopped backup/restore retains exact rows/files/model/recipe/trial/
  reservation/grant before cold Run reconciliation. Retained schema8 explicitly
  upgrades to9; failed new DDL rolls back all tables/ledger and old rows/files.
  Earlier schema definition hashes remain exact. Schema9 definition SHA256 is
 `1672d984517caaabf772ce64e9b73edb96d04a1cbe2997c14350e2df63396f54`.
- 7,501 seeded valid actual trial rows exceed the old256KiB boundary and remain
  readable with an unchanged-key large continuation receipt. No campaigns were
  executed to generate this boundary fixture. Receipt/material/Run corruption and
  lowered settled charges fail closed.
- Orphan reconciliation verifies original bytes then checks per-file identities
  under the final lock. Actual in-place child rewrites keep parent directory
  identity unchanged yet are refused. Exact orphan adoption requires explicit owner.
- Legacy preflight and sibling changed-model-policy grants cannot authorize another
  composition. A correct full-material grant is consumed once; the fresh cold Run
  also refuses a different self-consistent executable preflight under that grant.
- Real selected HTTP exercises owner approval, agent403, v2 draft CAS, bounded
  collection pages/stale reservation revisions and exact receipt replay. Actual
  project_cli subprocesses inspect model, recipe material and Study. Official
  MCP1.30 client/process inspects the same retained model. No Run is created by
  those inert inspection calls.

Actual Chromium existing project/Data/Pipeline/Runs check passed desktop/narrow,
keyboard, reload and server restart. Receipt is the task-local ignored
build/qa/workspace-project/run-VABiQr/receipt.json. This is supporting precommit
browser evidence, not a claim of new P3 model-authoring/training UI.

## Independent review and corrections

Independent GPT-6.1 Sol High review, no Astra. Findings were resolved with actual
regressions: postcommit capture deletion; writer/reader size mismatch; Study/global
key collision; orphan child rewrite race; full-composition approval and executable
binding; cold receipt/charge coherence; bounded collections and stop children.
The reviewer independently ran final6 full-approval/Run/restore/public/corruption
cases0skip18.092s, plus earlier fault/race/migration/CLI/orphan checks. Final source
review reports no remaining blocker. Read-only review did not modify files.

Failed intermediate runs are diagnostic only: an incorrect SQL reservation-column
assumption was replaced by a Trial join; a corrupt-row test now restores its fixture
for cleanup; an agent run overlapped execution-host source edits and was rejected
by the existing host-identity guard. The fresh settled53-case run passed. No guard,
timeout, historical witness or optional dependency requirement was weakened.

No applicable AGENTS file or callable Coding Standards MCP was exposed. The
adopted dcc56f26 guidance and original plan structural function were used; validator
SHA256 `c7266c0564b9ee02944fc4eb12d66cc20d604fd4ddb7f051ed77d01e9fe4466e`.
The original function, changed Python AST, local documentation links/anchors and
whitespace checks pass. This is not a fresh Engine certification.

## Remaining gates and next stage

A reviewable implementation and E1 composition are committed. Post-composition
actual Study32/0skip75.789s and extension24/0skip7.935s pass. The extension backup
test now asserts current SCHEMA_VERSION while keeping its exact project-format
restoration/legacy-reader witnesses; it was not a historical schema8 fixture.
Independent merge review confirms the app.py union preserves both owners.
SDK PR65 subsequently passed all six exact-head checks and merged as1a5c596.
P2 merge06d397b is the clean union; no P2 application file changed. Actual composed
Study32/0skip88.009s and all extension33/0skip9.834s pass, including SDK static
validation and the original retained-reader witnesses. Independent review confirms
the15 SDK additions and schema/canonical/test owners exactly match accepted main.
Run exact-head CI and recheck the composition before merging. P2 stays Verifying/I2 pending until then.
Source identities are retained in [P2 fingerprints](p2-source-fingerprints.json).
P3 implements and qualifies actual classifier template edits, automatic recurrent
checkpoint/probe capture, linked inspection/correction and cold consumer behavior.
P4 co-tests generic/one-fit fields; P5 package/fresh inference and P6 wider passive
observation remain pending. Optional scientific producer drafts do not close them.
