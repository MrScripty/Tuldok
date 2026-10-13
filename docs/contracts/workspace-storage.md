# Workspace metadata and explicit schema upgrade

Workspace graphs, runs and exposure evidence use the existing PostgreSQL
catalog and its persistent dataset identity. `metadata.py` owns their physical
tables and schema version. Pipeline/run owners validate the versioned JSON
documents, references, graph revisions, request meaning and lifecycle; storage
keeps those documents as exact `text`. Large run artifacts belong in the managed
dataset directory and therefore remain part of complete catalog backups.

Schema 2 adds exactly these tables to the qualified 19-table schema 1:

| Table | Columns and durable constraints |
| --- | --- |
| `workspace_graphs` | `id TEXT PRIMARY KEY`, `revision INTEGER NOT NULL`, `document TEXT NOT NULL` |
| `workspace_runs` | `id TEXT PRIMARY KEY`, `request_key TEXT UNIQUE NOT NULL`, `request_sha256 TEXT NOT NULL`, `document TEXT NOT NULL` |
| `workspace_exposures` | `id TEXT PRIMARY KEY`; required text `record_id`, `source_hash`, `reason`, `run_id`, `release_id`, `created_at` |

The run owner binds a unique request key to the request hash and saved result;
the graph owner performs revision-conditional writes. References remain domain
owner obligations. No second catalog or production browser store is introduced.
Schema 3 changes only `workbench_records_kind_check`, widening the admitted kinds
from `image`, `text`, `sequence`, `mesh` to include `audio`. It adds no tables or
columns. The audio owner validates source metadata in `provenance_json` and timed
annotations in the existing annotation/history contract; original WAV bytes live
under the managed dataset's `audio/` directory. Storage preserves these values
without claiming to validate WAV or annotation semantics.

Schema 4 admits `pointcloud` and `volume` record kinds and adds
`workbench_pointcloud_assets` and `workbench_volume_assets`. Each has an `id`
primary key, original `bundle BYTEA`, `metadata_json TEXT` and positive
`bundle_bytes INTEGER`. ImmutableAssets owns atomic bundle/record/history
publication; subtype parsers own native interpretation. Whole-asset inspection
uses `pointcloud_geometry` and `volume_grid` tasks with human review notes.
Original ordered PLY and uint8 NPY files and sidecars remain exact bundle bytes.
The upgrade changes no existing graph/run/release documents or artifacts.

Existing domain rows, other constraints, indexes, sequence high-water marks,
stored JSON spelling, manifest identity and artifact bytes are unchanged by
upgrade.

## Upgrade an existing catalog

Fresh catalogs use schema 5. Ordinary application startup **does not migrate**
an existing schema-1 through schema-4 catalog. It refuses with instructions to run the
explicit upgrade. Stop every application, provider/training worker and artifact writer;
keep them stopped throughout backup, upgrade and verification. The catalog
advisory lock coordinates cooperating commands, but cannot fence an old binary
that remains alive and resumes writing after the upgrade.

Use the same local `TULDOK_DATABASE_URL` configuration as the application:

```sh
python backup_metadata.py backup ./dataset ./dataset-before-spatial --quiesced
python upgrade_metadata.py ./dataset --quiesced
python app.py --data ./dataset
```

The backup destination must be new. Keep the complete backup and its receipt.
The accepted transitions have stable identities `workspace-metadata-1-to-2`,
`audio-metadata-2-to-3`, `spatial-metadata-3-to-4` and `project-metadata-4-to-5`. The command applies the ordered steps needed by the
recognized source, with the complete chain in one transaction. It verifies:

1. The manifest, catalog identity, version ledger and exact retained definition.
   Schema 1 has hash `859a04c5ee618faae689885bee79054d5e92098e746d058fd2bcb599da4c80db`;
   schema 2 has hash `ac4d969f8794004dc11942d8fdb53181e453240c489ddf2605ea32606f911274`;
   schema 3 has hash `54fade5b56207edf7c9a33bfa9187f85b3e42ea779869314e7ab0fa8bdc242a4`.
2. The actual schema against a separate reference schema created from the pinned
   accepted DDL on the same PostgreSQL server. That reference lives only within
   an always-rolled-back transaction. An edited schema cannot be accepted merely
   by refreshing its stored signature.
3. Each resulting schema against the independently derived target structure,
   before updating the version, definition and structure signatures.

All DDL and version ledger updates commit in one transaction under the existing
dataset advisory lock. A failed second step rolls back the first step as well;
the old kind constraint is never authoritatively absent. Only the known version-1,
version-2, version-3 or version-4 definitions are eligible. Unknown versions, altered constraints,
indexes, tables or triggers, malformed ledgers, missing catalogs and contradictory
identities fail closed. No command
refreshes a signature to bless unsupported drift. The manifest remains version 1;
manifest and SQL schema versions are different contracts.

The command prints the dataset identity, final migration name
(`project-metadata-4-to-5`), final schema version, definition/structure hashes and
`upgraded` or `already_current`. A repeat on a
known schema-5 catalog verifies its structure and leaves rows/files unchanged.
Run one upgrade/transfer command at a time. A command failure rolls back its
transaction. A lost commit acknowledgement is explicitly an unknown outcome:
keep writers stopped, reopen, and rerun this same command to verify whether the
catalog is still the known source version or already known schema 5. Never
manually change the ledger, delete a table or replay a training request to resolve it.

## Backup, restore and legacy imports

The backup container remains `format_version: 1` and explicitly records
`schema_version: 1`, `2`, `3`, `4` or `5`. `backup_metadata.py` accepts each recognized schema.
Restore recreates **the exact backed-up schema version**, identity, rows,
sequence states and ordinary files in an absent catalog/new directory. A retained
schema-1, schema-2 or schema-3 backup remains restorable; upgrade that restored copy explicitly
before opening it in the new application. Schema-2/3/4 backups include every graph,
run and exposure row. Schema-3 backups also preserve audio records/history and
managed WAV bytes. Schema-4 backups also preserve both spatial bundle tables,
review history and frozen spatial releases. Restore retries reject later writes and schema evolution instead
of overwriting them. Required privileges and full-file preservation remain as
specified in [local storage and recovery](local-storage.md).

`Metadata(..., schema_version=1)`, `schema_version=2`, `schema_version=3` and `schema_version=None`
are tooling entry points for exact old-version restoration and recognized-version inspection.
Normal Dataset and Workbench callers omit that argument and require schema 5.
Version selection never authorizes an unsupported definition or structural drift.

Legacy SQLite preflight still recognizes only the original 19 owner tables.
A new import creates schema 5 and leaves workspace/project tables empty.
A retained schema-1 or schema-2 migration receipt remains byte-for-byte authoritative:
an interrupted import continues at its receipt's version, and a completed import can be
reconciled after an explicit upgrade only while its original rows/files still
match and all newly added tables remain empty. Existing migration receipts are
never rewritten to imply that later workspace or audio writes belonged to the old import.

There is no automatic downgrade. Before any new writes, retain and restore the
complete pre-upgrade backup to a separate destination/database if returning to
the older binary is necessary. After new writes, retain the schema-5 catalog and
artifacts and reconcile/export them under an explicit recovery decision; an old
backup cannot represent those later writes.

## Evidence and scope

`tests/test_workspace_metadata.py` exercises real PostgreSQL upgrade/reopen,
historical Workbench rows/history/selections/searches, exact identity and file
preservation, unknown and re-signed schema refusal, partial-DDL/postcondition
rollback, lost commit acknowledgement, real CLI re-entry, unique request keys,
schema-1 restore, schema-2 graph/run/exposure backup/restore, both retained versions'
upgrade chains, schema-3 audio/history/WAV backup/restore, and retained schema-2
SQLite migration receipts. Existing metadata migration/transaction/worker/filter
tests remain required regressions. The local
qualification server is PostgreSQL 17.11; this does not claim independent
qualification on every supported server major or operating system.


`tests/test_spatial_storage.py` verifies schema3→4 preconditions and atomic
rollback, original spatial bytes/review/release custody and schema4 backup/restore.
`tests/qualify_spatial_retained_runs.py --legacy-root LEGACY_CHECKOUT` creates a
real completed mesh run using exact schema3 source
`f1ecf7888a8dfa5b67ac8b087034226d533c682e`, with no synthetic downgrade. It then
verifies unchanged graph, record, completed run, report and release bytes after
explicit upgrade, schema4 backup/restore, and schema3 backup/restore followed by
explicit upgrade. Both backup trees remain unchanged. CI checks out that exact
legacy revision and retains the qualification report with QA artifacts.

## Project registration (schema5)

Schema5 adds only `workspace_projects(id TEXT PRIMARY KEY, document TEXT NOT NULL)` for immutable project manifest snapshots. The schema4 definition remains exactly `52242c56f7b88144157b66d93b151d818cecf0b2219226d4aff5734e8a1adcef`. Schema5 backup/restore includes project rows but does not copy external project files or grant a new filesystem binding. See [project inspection](projects.md). Tests retain exact v4 backups and prove the explicit v4→5 transition, transactional rollback and restored project snapshots alongside old domain rows. The retained-run qualifier now targets schema5 while preserving its actual historical schema3 source and backup.
