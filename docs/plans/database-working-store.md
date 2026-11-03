# Database working store for external projects

Status: stages 1–2 implemented; stage 3 revised (2026-11-02). Owner decision recorded with the user.

## Decision

The local PostgreSQL database is the persistent **working copy** of an opened
project and is kept across sessions. The external project folder
(`.tuldok/project.json` plus content-addressed `records/`, tracked in Git) is
only:

- an **import source**, read when its files changed since Tuldok last imported
  or exported them, or when the project is not yet in this workspace; and
- an **export target**, written only by an explicit Save.

Edits during a session are committed to the database and stay there. Closing a
project does not write the external folder. Complete domain validation runs
only when the record set changes (import of a changed folder, or a commit).

There is exactly one durable copy of the record set (the database) and no
complete in-memory copy: owners read the record families or records they need.

## Why

Opening the 54k-record, 1.77 GB Rheon portfolio rebuilt a fresh SQL projection
from every JSON file on each Open (9+ minutes, 17–21 GB RAM: the Store, the
Session and owner copies each held the whole record set). JSON exists only so
the project can be tracked in Git.

## Identity and integrity

- Checkpoint identity is unchanged: the working copy keeps the same manifest
  (inventory of `family/id/format/bytes/sha256`, roots, receipts) and the same
  checkpoint digest as the file format, so Save writes byte-identical files and
  existing receipts, validation markers and custody records stay meaningful.
- Each record is stored once as its exact canonical bytes (not `jsonb`, which
  would change number spelling such as `-0.0`) with its SHA256.
- Import verifies `project.json`, then only reads, SHA256-checks and
  canonical-checks records whose digest the working copy does not already hold.
- Save re-checks that the external `project.json` is still the one last
  imported/exported (refusing to overwrite external changes), writes only
  missing record files, then publishes `project.json` atomically.

## Open

1. Read external `project.json` (one file) and its SHA256.
2. Working copy exists and its last imported/exported manifest hash matches:
   attach. No record file is read; the SQL projection is reused.
3. External folder changed, working copy has no unsaved changes: incremental
   import, validate (cached per checkpoint), rebuild projection tables.
4. External folder changed **and** working copy has unsaved changes: refuse with
   an explicit conflict (keep working copy and overwrite on Save, or discard and
   re-import). Never merge silently.

## Stages

1. **Working store — done.** `WorkingProjectStore` (project_working_store.py)
   with the ProjectStore interface, incremental import, commits joined to the
   projection's open SQL transaction, Save as the only folder write. Workspace
   keeps a private folder→working-copy registry.
2. **No whole-project memory copy — done.** Sessions over a working copy bind
   checkpoint metadata only; family/record/identity reads come from
   PostgreSQL, commit hooks never materialize the record set, Study authoring
   restores from Study/Trial documents and Run history loads per Run.
3. **Projection reuse — revised.** Reusing the SQL projection across sessions
   would carry live execution state (runs, admissions, execution grants) into
   a later session, which a cold open deliberately starts without. Instead the
   projection is still reconstructed fresh, from cheap family-scoped reads.
4. **Edit-scoped validation — done.** `project_validation_delta` declares each
   validation component's input families (from a per-component audit); an
   edit re-runs only components whose inputs it changed and only the old
   receipts bound to changed records or sharing a key space. Identity, claim,
   fork and receipt-identity checks always run; unclassified operations are
   always validated. `TULDOK_VALIDATION_CROSSCHECK=1` runs complete validation
   alongside and fails on disagreement (the project suite passes in that mode).
   A text import on the portfolio: 161 s → ~31 s; validation itself 1–3 s. The
   remainder is the receipt digest over every record's bytes (format-defined)
   and the full record read for owner captures, both dominated by stage 5.
5. **Smaller project files — open.** Store each captured runtime file listing
   once and reference it from Runs (format migration with exact round trip).

## Measured on the Rheon portfolio (54k records, 1.77 GB metadata)

| | before | reopen now |
|---|---|---|
| Open | ~9 min (CPU) | ~11 s |
| Peak memory | 21.7 GB | 0.76 GB |
| First history/progression read | ~100 s | 0.5 s |

First import into a new workspace takes ~50 s plus one complete validation
(~2.5 min) per checkpoint and validator version.

Payload blobs (`artifacts/sha256/*`, 16 GB for the portfolio) remain
content-addressed files under the project folder in stages 1–4.
