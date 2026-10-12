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
Existing domain rows, constraints, indexes, sequence high-water marks, stored
JSON spelling, manifest identity and artifact bytes are unchanged by upgrade.

## Upgrade an existing catalog

Fresh catalogs use schema 2. Ordinary application startup **does not migrate**
an existing schema-1 catalog. It refuses with instructions to run the explicit
upgrade. Stop every application, provider/training worker and artifact writer;
keep them stopped throughout backup, upgrade and verification. The catalog
advisory lock coordinates cooperating commands, but cannot fence an old binary
that remains alive and resumes writing after the upgrade.

Use the same local `TULDOK_DATABASE_URL` configuration as the application:

```sh
python backup_metadata.py backup ./dataset ./dataset-before-workspaces --quiesced
python upgrade_metadata.py ./dataset --quiesced
python app.py --data ./dataset
```

The backup destination must be new. Keep the complete backup and its receipt.
The explicit upgrade has stable identity `workspace-metadata-1-to-2` and verifies:

1. The manifest, catalog identity, version ledger and retained schema-1 definition
   hash `859a04c5ee618faae689885bee79054d5e92098e746d058fd2bcb599da4c80db`.
2. The actual schema against a separate reference schema created from the pinned
   accepted DDL on the same PostgreSQL server. That reference lives only within
   an always-rolled-back transaction. An edited schema cannot be accepted merely
   by refreshing its stored signature.
3. The resulting schema against the independently derived schema-2 structure,
   before publishing the new version, definition and structure signatures.

The three new tables and version ledger update commit in one transaction under
the existing dataset advisory lock. Only the known version-1 definition is
eligible. Unknown versions, altered constraints/indexes/tables/triggers, malformed
ledgers, missing catalogs and contradictory identities fail closed. No command
refreshes a signature to bless unsupported drift. The manifest remains version 1;
manifest and SQL schema versions are different contracts.

The command prints the dataset identity, migration name, final schema version,
definition/structure hashes and `upgraded` or `already_current`. A repeat on a
known schema-2 catalog verifies its structure and leaves rows/files unchanged.
Run one upgrade/transfer command at a time. A command failure rolls back its
transaction. A lost commit acknowledgement is explicitly an unknown outcome:
keep writers stopped, reopen, and rerun this same command to verify whether the
catalog is still known schema 1 or already known schema 2. Never manually change
the ledger, delete a table or replay a training request to resolve it.

## Backup, restore and legacy imports

The backup container remains `format_version: 1` and explicitly records
`schema_version: 1` or `2`. `backup_metadata.py` accepts either recognized schema.
Restore recreates **the exact backed-up schema version**, identity, rows,
sequence states and ordinary files in an absent catalog/new directory. A retained
schema-1 backup remains restorable; upgrade that restored copy explicitly before
opening it in the new application. Schema-2 backups include every graph, run and
exposure row. Restore retries reject later writes and schema evolution instead
of overwriting them. Required privileges and full-file preservation remain as
specified in [local storage and recovery](local-storage.md).

`Metadata(..., schema_version=1)` and `schema_version=None` are tooling entry
points for exact old-version restoration and recognized-version inspection.
Normal Dataset and Workbench callers omit that argument and require schema 2.
Version selection never authorizes an unsupported definition or structural drift.

Legacy SQLite preflight still recognizes only the original 19 owner tables.
A new import creates schema 2 and leaves the three workspace tables empty.
A retained schema-1 migration receipt remains byte-for-byte authoritative:
an interrupted import continues at schema 1, and a completed import can be
reconciled after an explicit upgrade only while its original rows/files still
match and all newly added tables remain empty. Existing migration receipts are
never rewritten to imply that later workspace writes belonged to the old import.

There is no automatic downgrade. Before any new writes, retain and restore the
complete pre-upgrade backup to a separate destination/database if returning to
the older binary is necessary. After new writes, retain the schema-2 catalog and
artifacts and reconcile/export them under an explicit recovery decision; an old
backup cannot represent those later writes.

## Evidence and scope

`tests/test_workspace_metadata.py` exercises real PostgreSQL upgrade/reopen,
historical Workbench rows/history/selections/searches, exact identity and file
preservation, unknown and re-signed schema refusal, partial-DDL/postcondition
rollback, lost commit acknowledgement, real CLI re-entry, unique request keys,
schema-1 restore and schema-2 graph/run/exposure backup/restore. Existing metadata
migration/transaction/worker/filter tests remain required regressions. The local
qualification server is PostgreSQL 17.11; this does not claim independent
qualification on every supported server major or operating system.
