# P7 admission: preserve runtime permissions and qualify restore

Root admits isolated source preparation on 2026-10-13 in branch
`feature/scientific-restore-qualification-20261013`, based on P6 checkpoint
`b02004a` (draft PR53). P5c actual evaluation has passed; its remaining final
checks and P6 full acceptance are separately gated. This sequencing amendment
allows only the bounded existing backup-owner fix and focused tests in this
isolated worktree. Do not alter frozen P5c/P6 sources or the qualified catalog.
The later resume instruction admits P7 inventory, complete backup and separate-DB
SQL probe preparation while the isolated P6 test-only correction finishes.
P6 actual scientific MCP read already passed; P7 product acceptance remains
gated on final P6 checks and measured transfer evidence. No deletion is admitted
by this document. Restore waits for a concrete verified recovery plan.

The observed defect is that copy_tree drops file permissions: a byte-exact
restore can make captured 0500 executables and 0400 data fail runtime verification.
Admit mode preservation in existing backup_metadata.copy_tree, source identity
and mode consistency checks, matching modes for resumed/completed restore,
and directories applied after children. Preserve byte manifest/receipt format;
old byte-only backups do not prove original modes. Refuse changed evidence;
never repair source or historical snapshot manifests. Safe retry behavior for
read-only staging must be explicit and tested, with no generic chmod bypass.

Owner write set: backup_metadata.py; tests/test_workspace_metadata.py;
tests/test_runtime_snapshots.py; docs/contracts/local-storage.md,
docs/contracts/captured-cpu-runtime.md and docs/contracts/workspace-storage.md.
A focused tests/qualify_scientific_restore.py may compose existing owners.
Root owns plan/ledger/reports. Independent review and focused/full tests precede
acceptance and publication. No new backup framework, schema migration or model
execution is admitted.

# P7 proposed backup/restore qualification

2026-10-13. Planning only during active P5c evaluation. No source changes, deletion, backup, restore, model execution or heavy tests. Actual P5c numerical/lifecycle gates must finish first. QA owner review/auth flows are already authorized; this plan adds no generic approval ceremony. Destructive removal, if needed, still requires the parent to approve exact task-owned paths and verified recovery evidence. No deletion is authorized here.

## Existing owners and prerequisite fix

`backup_metadata.py backup CATALOG BACKUP --quiesced` creates a new separate/nonnested backup. It packs every SQL table losslessly, retains opaque JSON text, per-row/table hashes and identity sequence high-water marks, copies the complete ordinary-file tree, compares source before/after and backup bytes, then publishes metadata.json/backup-receipt.json/catalog. Symlinks and special files are refused. On failure only the newly owned partial backup is cleaned. Quiesced is an assertion, not a process stopper.

`backup_metadata.py restore BACKUP DESTINATION` preserves the dataset UUID and original schema version. The target directory must be new and the target PostgreSQL catalog schema absent. It validates backup bytes/metadata, creates marker-bound staging, reconciles/inserts rows, copies files and publishes by rename. Failure can leave DB rows and staging; same-target retry reconciles the exact marker/rows rather than merging/replaying. A repeated completed restore accepts only an unchanged destination and refuses later writes.

`upgrade_metadata.py CATALOG --quiesced` explicitly upgrades schemas1–7 to8, retaining the known TABLES_V1..V7 identities. Real current schema8 restore needs no upgrade. Older small fixture restores prove old-state parity before explicitly upgrading.

**Concrete prerequisite:** `backup_metadata.tree_manifest` records bytes/hash, not modes; `copy_tree` currently writes temporary files with default umask and never restores mode. CPU snapshot verification requires exact0500 ELF/0400 data modes (`recipe_process._cpu_stream_file`). Byte-perfect backup/restore alone cannot qualify a usable runtime.

Parent-selected fix: preserve source file modes in existing `copy_tree`, applying directory modes last after children are copied, with cold runtime verification. Keep existing backup manifest/receipt byte format and supported old readers unchanged. Source permissions must be checked consistently while copying, before final publication; do not repair them later with an undocumented chmod script or rewrite a runtime manifest. Existing old byte-only backups cannot guarantee runtime usability; disclose this, do not claim they were previously qualified. New backups copy canonical source permissions into their own files and restore preserves those permissions. Test restrictive writable/read-only modes, directories, copied file ownership/link count, and exact runtime manifest expectations without model execution.

Exact proposed owner/write set: storage owner `backup_metadata.py`, `tests/test_workspace_metadata.py`, `tests/test_runtime_snapshots.py`; actual restore evidence may add one focused `tests/qualify_scientific_restore.py` procedure reusing these owners. Documentation owner updates `docs/contracts/local-storage.md`, `docs/contracts/captured-cpu-runtime.md`, `docs/contracts/workspace-storage.md` and parent plan/ledger/reports. No current source edits during evaluation. Root admits and independently reviews this bounded prerequisite first; no alternative backup framework or schema migration.

## Identity and database constraints

.tuldok.json fixes dataset_id and PostgreSQL schema `catalog_<dataset_id>`. Removing its filesystem tree does NOT remove that schema. Prefer an explicitly configured separate restore database, leaving the stopped original DB/schema intact. Provision it through the authorized fixture/service owner. Do not print DSNs/passwords. If a separate DB cannot be provisioned, report the blocker; do not improvise DROP SCHEMA to force restore to pass.

Runtime manifest, saved graph/Run/material/spec/request/grant and custody receipt bytes remain exact. Historical spec.cwd/output_dir and cpu_snapshot.root are evidence, not current destinations. Completed Run artifact reads use the restored catalog's owned paths. Dispatch refuses a historical staging-root mismatch; no historical attempt is resumed. `RuntimeSnapshots.get(sha,verify=True)` creates a fresh inspection descriptor pointing to the current snapshot root from its unchanged manifest. New preflight would create new material/approval identity; never rewrite old paths/hashes.

External project files are outside full catalog backup. Project rows preserve immutable manifest snapshots/root aliases, but restored app inspection requires explicit authorized root bindings. Missing external files remain missing. Captured per-Run inputs/sources and snapshot bytes inside the catalog must be backed up. Backup credentials are digests, but live sessions/grants may remain effective until expiry: protect full backups like the source and do not publish their rows/tokens.

## Phase 1: finish, inventory, quiesce

1. Finish actual evaluation and independent all-output/full-field verification. Large-profile `receipt_verified/payloads:not_checked` list/get is NOT all-payload verification. Preserve exact checkpoint/freeze/training receipts, numerical results, original NPZ/viewport, scientific chunks and native-wire evidence. Record failures honestly.
2. Obtain exact catalog path, UUID, source commit, Python executable, actual Run IDs and private source/restore DB aliases from parent. The shared qualified scientific catalog is the intended source; do not guess a scratch path for destructive work.
3. Stop app and workers via lifecycle owners and confirm drained terminal states across Runs/generation/proposals. No queued/running/cancelling/unknown work for this snapshot. Unknown cessation is a blocker; directory deletion or a second Dataset cannot resolve it. Never signal remembered PIDs.
4. Keep all writers stopped. Capture raw `Metadata(create=False,schema_version=None)` table summaries via `read_catalog`, sequence high-water marks via `read_sequences`, manifest bytes, file digests/sizes/modes and actual free space. Do this BEFORE Dataset/login/runtime CLI; those can append audit/recovery rows. Record checks outside the catalog to avoid perturbing its tree.

## Phase 2: prefer narrowly approved staging duplicate cleanup

After confirmed successful publication, `.external-<RunID>/output` contains a duplicate of durable `workspace-runs/<RunID>/<artifact>`. Propose cleanup only if each exact target is parent-approved after evidence:

- Completed Run, drained successful custody; every declared source output matches published size+SHA; published manifest and receipt independently verify.
- Target is the task-owned canonical directory beneath the confirmed catalog, with no symlinks/undeclared files. No active reader/writer depends on it. Capture path/count/byte/digest inventory and retained counterpart in a cleanup receipt.
- Current artifact/capture/scientific-import owners use durable published paths; historical spec output paths are not operational dependencies.

If approved, delete ONLY that output subtree, keeping `.external-<RunID>/custody` logs/receipt, captured sources/inputs/bootstrap, runtime snapshots and durable artifacts. Do not remove the entire staging tree or any failed/interrupted/unknown attempt evidence. Do not rewrite historical spec.output_dir. Verify all published artifacts, progress custody and typed input capture again. Record the intentional before/after tree delta. No such deletion occurred in this planning task.

## Phase 3: measured space and two-copy fallback

Let C be measured source file bytes after any approved cleanup, M metadata/receipt overhead, and R at least512MiB operational reserve plus actual DB/WAL growth. Parent forecast is approximately2.2GB before evaluation +3.3GB canonical evaluation ≈5.5GB; unremoved staging duplicates add another~3.3GB. These are estimates, not permission to start transfer. Recompute on the actual filesystem after evaluation.

`copy_tree` copies a file into an adjacent temporary and renames it into its final staging location. That temporary becomes part of the final destination C: it does not add a whole extra largest file beyond the complete C budget. Account separately for filesystem overhead, metadata, DB/WAL and concurrent user writes. No compression/dedup/reflink is promised. Measure /tmp separately; do not assume it shares /workspace's capacity or persistence.

Preferred no-source-deletion protocol: source+backup+restore coexist, approximately3C+M plus databases/reserve. If this fits after approved duplicate cleanup, use it and retain original DB/source stopped.

If only two copies fit: source→complete verified backup; independently verify backup and SQL readability; parent approves removal of ONLY the exact task-owned original catalog tree (resolved path, UUID, full digest, backup path and receipt hash); remove original filesystem tree while preserving original stopped DB; restore to another path and a separate DB. Peak backup+restore≈2C+M plus databases/reserve. No DB schema, source checkout, backup or other catalog deletion. Full backup must exist and be independently verified BEFORE original removal. No completed duplicate cleanup or whole-catalog removal is assumed done.

Before source deletion, prove SQL backup readability without a second full artifact copy: validate metadata.json SHA, every packed value/table columns/count/row digest/sequence and dataset/schema definition; exercise existing `populate_catalog` in a separate disposable probe DB and rollback transaction if needed. This proves types/permissions, not complete restore. Keep actual restore target schema absent. No ad hoc DB cleanup outside exact disposable ownership.

## Phase 4: existing commands (planned, not executed)

Use frozen source and task-specific reviewed absolute paths, with new separate/nonnested backup and restore destinations. DSNs are supplied through private environment files; never echo them.

```
source "$TULDOK_QA_SOURCE_ENV"
"$TULDOK_QA_PYTHON" backup_metadata.py backup \
  "$TULDOK_QA_CATALOG" "$TULDOK_QA_BACKUP" --quiesced
# Independently verify full backup; parent owns any exact approved removal.
source "$TULDOK_QA_RESTORE_ENV"
"$TULDOK_QA_PYTHON" backup_metadata.py restore \
  "$TULDOK_QA_BACKUP" "$TULDOK_QA_RESTORED"
```

Only genuinely old small fixture catalogs then use:
```
"$TULDOK_QA_PYTHON" upgrade_metadata.py "$TULDOK_QA_OLD_RESTORED" --quiesced
```

## Phase 5: raw parity, then restored workflows

Before auth/app startup, compare actual restored schema/version/definition, UUID, all table columns/counts/row hashes/table digests and sequences to backup. Compare full restored tree excluding only `.restore-receipt-<receipt-digest>.json`. Verify the prerequisite's permission invariants and unchanged full backup tree. Historical graph/Run documents, IDs, material/spec/receipt bytes stay exact. No path normalization in opaque JSON.

Then open Dataset using explicit restore DSN/root bindings. Record expected new auth/audit/reconciliation events separately. Verify completed actual Runs remain completed with no replay. Use production local owner login into an exclusive0600 file only after raw parity; no token output. Runtime verification also creates/logout credentials and audit entries:
```
"$TULDOK_QA_PYTHON" runtime_snapshots.py verify \
  --data "$TULDOK_QA_RESTORED" --manifest-sha256 "$TULDOK_QA_RUNTIME_SHA"
```

This must cold-verify the ACTUAL qualified snapshot at its new root without loading a model. Public owners must read exact completed checkpoint/results/summary and all scientific artifacts from restored paths; stream/hash full evaluation output once, preserving roles and evidence. Inspect representative scientific slice geometry, review/history and immutable release bytes. In the two-copy case the old source is absent, proving no fallback to historical paths. New preflight may prove current runtime root with a newly computed material digest; no model submission is needed. Any later neutral dispatch uses a fresh approval, never a replay of a historical attempt.

## Actual-history and retained-fixture matrix

Inventory exact real IDs; do not claim the scientific QA catalog contains every old modality. Required real history if present: P5a checkpoint comparison, P4/native generation, P5b reviewed training records/six releases/fit-validation-checkpoint, P5c evaluated checkpoint/full fields/custody, editable graphs/projects/runtime, actors/audit/admissions/grants/consumptions and imported/reviewed evaluation chunk. Mark any absent item explicitly.

Qualify all legacy modalities using separate small fixtures rather than merging or multiplying multi-GB catalogs: `tests/test_workspace_metadata.py` (retained schemas/upgrade/rollback/restore), `tests/test_spatial_storage.py`, `tests/test_scientific_release.py` (neutral project+Run provenance restore), sequence v1/v2 `tests/test_sequences_v2.py`, `tests/test_sequence_runs.py`, `tests/test_sequence_v2_runs.py`, plus owned image/text/audio regressions. Existing `tests/qualify_spatial_retained_runs.py --legacy-root <exact clean qualified historical checkout> --report <new report>` proves actual retained spatial Runs; its checker decides the required historical source, not a guessed current checkout. Retain release bytes, source bytes, reviews/revisions/history/families/splits and classification test-exposure refusal. Synthetic compatibility fixtures never qualify actual model acceptance.

Schedule tests after evaluation under root ownership; no concurrent heavy suite now. Capture source hashes before/after authoritative verification.

## Failure/recovery and authority switch

- Backup failure: source DB/tree stay stopped and authoritative. Never delete source based on a partial transfer. Existing owner cleans only its private partial backup.
- No approval to remove original: retain it and report exact space requirement.
- Restore failure after approved source removal: preserve full backup, original DB and marker-bound staging/target DB. Same-target restore reconciles; no new import/merge/replay or ad hoc DROP SCHEMA. Unsupported crash reconciliation is a blocker, not apparent success.
- Commit acknowledgement unknown: preserve rows/files and inspect exact receipt/marker. No blind retry mutation or deletion. Restored destination with later writes cannot be overwritten.
- Unknown custody: restore does not stop processes. Do not edit state/boot IDs, clear fences or signal old PIDs. Same-boot active/unknown source blocks full quiesced qualification. Authored interrupted/queued restore cases belong to small lifecycle tests and must prove no spawned replay, not fictional successful cancellation.
- Runtime mode/hash mismatch: fail runtime acceptance; byte-readable completed artifacts are narrower evidence only. No posthoc chmod/recapture changing identities to force green.
- Finish with complete verified backup and restored catalog/evidence. Parent explicitly selects live DB/catalog and keeps old writers stopped. No further deletion follows automatically.

## Final evidence

Bounded report: source commit/tool versions, safe absolute paths and UUID (no secrets), actual disk phases, permission-preservation fix revision, table/sequence/file digest summaries, backup receipt SHA, optional cleanup receipt, cold actual runtime verification, completed Run/release/checkpoint/full-field digests, restored UI/read results and exact compatibility receipts/blockers. Store long inventories privately with hashes/counts; do not dump credentials or raw DB rows into chat. This plan writes only this /tmp document.

## Fresh catalog permission initialization refinement

Final review observed that Metadata creates `.tuldok.json` and
`.metadata-init.lock` before transfer. A private source manifest or a different
creation umask can therefore contradict the exact-mode transfer guard in a
valid new restore. Root admits a minimal owner change in `metadata.py`,
`backup_metadata.py` and `tests/test_workspace_metadata.py` to apply validated
source modes only to files exclusively created by this invocation. A resumed
marker-bound staging directory may initialize an absent manifest after Metadata
validates its existing pending reservation, identity and schema. Its existing
lock and all existing file modes remain untouched.
Creation identity must come from the creating owner; inspecting an existing
name after construction does not prove ownership. Refuse preexisting fresh marker/lock files and never chmod a substituted
file, hardlink or symlink. Keep the existing atomic manifest publication
behavior; this refinement adds no stronger same-owner publication guarantee.
Resumed staging and completed
restores retain strict mode contradiction refusal. A leftover exclusive
manifest temporary is refused; no general cleanup or overwrite is admitted
to turn ambiguous partial state into apparent success. No receipt, schema or
historical mode claim changes, and no actual restored catalog edits are
admitted. Qualify private 0400/0600 manifests, 077-to-022 umask changes,
interruption/retry and replaced-file refusal, then independent review.
