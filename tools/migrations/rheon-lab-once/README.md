# Frozen one-time Rheon lab converter

This is an offline migration tool, outside the application import root. It is
never an application reader, HTTP operation, startup migration, runner or new
history catalog. It publishes through existing Metadata transactions and current
Projects registration/inspection. Its only source Project decoding is the local
`activity_path` field. No production conversion has been performed by its fixtures.

Stop every app, Run child and artifact writer first. An `unknown` Run or
undrained external custody blocks conversion; reconcile with its original owner.
One narrow original-owner terminal representation is archive-only: an external
Run already `interrupted` in `prepared`, with explicit null worker and custody
identity, a finished timestamp and a final interrupted event. The original
owner can record this before GO. Its exact phase remains historical evidence;
conversion does not relabel it drained or assert current execution custody.
Other non-drained phases, including GO intent, remain blocked.
The command's `--quiesced` is the operator's attestation, not a process-killing
facility or a fence against an uncooperative writer. Keep submissions closed
through independent post-publication inspection. Never try this against the live
store to discover its contents.

Create and independently verify a complete schema-8 backup using
`backup_metadata.py`. Rehearse its restore into an absent catalog on a distinct
PostgreSQL service/database, then use `upgrade_metadata.py --quiesced` to perform
only schema 8→9→10. Do not start Dataset or a service on the restored old domain
records before conversion. This converter accepts exactly that unchanged
schema-only upgrade, not an arbitrary current database. The exact retained
`restore_catalog` receipt for that verified archive is validated separately;
no wildcard file exclusion or unknown staging marker is accepted. Its bytes stay
in the target publication/re-entry inventory.

Supply an independently reviewed JSON spec with these fields:

```json
{
  "dataset_id": "<exact original 32-hex dataset ID>",
  "archive_receipt_sha256": "<SHA256 of original backup-receipt.json bytes>",
  "target_schema_version": 10,
  "target_definition_sha256": "<metadata.definition_hash()>",
  "target_connection_sha256": "<convert.target_identity(open Metadata)>",
  "target_application_sha256": "<convert.application_identity()>",
  "roots": {
    "lab": {
      "path": "/absolute/stopped/project/root",
      "files": {"<selected-relative-file>": {"kind": "file", "bytes": 123, "sha256": "<exact SHA256>"}},
      "unavailable": {"<missing-relative-file>": {"status": "pre-existing-unavailable", "reason": "FileNotFoundError"}},
      "selection_sha256": "<digest of files plus unavailable observation>"
    }
  }
}
```

The target connection digest includes catalog directory, PostgreSQL socket/host,
port, database and user; it contains no passwords. It prevents treating a restored
catalog's shared dataset ID as proof of a different destination. The application
digest binds every top-level application Python file; the prepared receipt also
binds the converter's source bytes. Freeze the candidate before preparing.
Use mode `inventory` with the original archive and initial spec containing root
paths to produce the reviewed `files`, `unavailable` and `selection_sha256` fields.
The bounded union contains saved Project manifests, explicit group/activity
references and recipe-declared source/native-source files. It never walks or
copies a whole root alias, `.git`, unrelated generated outputs or nested staging.
An alias may bind the complete lab repository, and staging may live inside that
root safely because only declared selected paths are read.

Roots must cover every original Project; alias `historical` is reserved. Each
root's current device/inode must match the saved Project. Unavailable/moved roots
require a separately justified mapping implementation and qualification; the
converter does not guess their identity. Selected files use anchored no-symlink
reads and streaming copies. Unreferenced symlinks do not enter the selection.
Take sufficient space: staging retains the complete independent original archive
and bounded selected source files.

Pre-existing unavailable or changed snapshots become archived-visible exact
original rows with explicit source observations, rather than invented current
Projects. Every missing selected reference has readable evidence stating it was
unavailable before conversion. This preserves the actual stopped source state;
it does not claim recovery of original file bytes already absent before migration.
Fresh active lab Projects can be registered separately under current contracts.

Optional root `recoveries` entries provide `original_path`, pinned old `sha256`
and a `source`: either `{kind:"file",root:"/isolated/lineage",path:"relative"}` or
`{kind:"git",repository:"/repo",revision:"<40-hex>",path:"relative"}`. A recovery
must match a hash explicitly bound by an original Project reference or manifest;
similar current files are never substituted. Recovered bytes are archived with
their actual source/revision provenance, separately from observations that the
live reference was already missing. They do not silently make an old snapshot
current. Git lookup is bounded to the reviewed path and revision.

Run from candidate Tuldok with private, explicitly isolated PostgreSQL
configuration and the qualified Python environment:

```sh
python -B tools/migrations/rheon-lab-once/convert.py prepare \
  --catalog /isolated/restored-catalog --archive /verified/original-backup \
  --stage /private/absent-migration-stage --spec /reviewed/spec.json --quiesced
```

Preparation is read-only for PostgreSQL. Review `stage/prepared.json`, including
every `source_keys` entry, accounting disposition, old/new identifiers, hashes,
root selections, removed active rows and current Project manifests. The returned
`prepared_sha256` binds this entire result and the staged-file inventory. No
source row, original archive or external source directory is changed. A failed
preparation leaves private staging for inspection; use another absent stage only
after resolving the failure. Preparation refuses to overwrite an existing stage.

Provide an existing authenticated owner credential token (normally a local
owner session, transported as a Bearer credential) in the private environment
variable `TULDOK_MIGRATION_OWNER_TOKEN`; it is not printed or a CLI argument.
Do not mint an admin bearer: Access forbids that authority. Use the existing
local owner login/exchange workflow. The session credential must already exist
before taking the stopped original backup,
because target inventory checks admit no extra owner/credential mutations.

```sh
python -B tools/migrations/rheon-lab-once/convert.py publish \
  --catalog /isolated/restored-catalog --stage /private/absent-migration-stage \
  --prepared-sha256 <reviewed-prepare-result> --quiesced
```

One transaction replaces affected Project rows, removes archived-only Runs,
source external/obsolete graphs and historical execution grants/consumptions,
registers current snapshots through
Projects, verifies their current inspection results and saves the exact receipt
through Access audit. It does not admit any execution. Historical native/current
Runs remain byte-for-byte only if the current Runs owner validates their retained
envelope; that reader is allocated without constructing its recovery/worker.
No old Run timestamps, results, failures, weights, normalization, host descriptors
or custody facts are rewritten. No new execution material, approval, acceptance
or lineage is invented.

Each original row has exactly one disposition: `already-current`,
`converted-current` or `archived-visible`. Every original ordinary file and
directory also appears in accounting. Exact SQL values, including opaque original
JSON document text, remain in independent original backup and paginated ordinary
Project evidence files. Original row wrappers are exposed completely as labelled
ASCII fragments of at most 60 KiB, within the existing evidence preview limit;
no result text is truncated. Original files have bounded readable descriptor
evidence plus ordinary data references for current byte capture. Binary artifacts
are never presented as text. Scientific file bytes are copied and verified exactly;
there is no numerical decoding/re-encoding. Historical source files and Run rows
are visibly labelled imported evidence. The mapping is ordinary evidence and
JSON receipt, not a second history framework.

Project manifests become schema 2; `activity_path` becomes evidence reference ID
`activity`, without a pinned hash because it is mutable external observation.
Only definitions admitted by the current Project recipe contract, with a current
format for their exact referenced managed-runtime registry descriptor, stay recipes.
Unbound captured-CPU recipes and valid generic templates pinned to an obsolete
runtime descriptor become `historical-*` evidence references with explicit reasons.
This is an archival policy for historical templates, not a claim that all their
recipe declarations are malformed. Opaque trainer inputs remain exact source
bytes. Never repin old recipes or add an obsolete runtime reader. Current-format
validation does not assert installed asset availability or execution qualification;
fresh material and approval remain required. Every retained recipe is additionally
inspected through the current recipe owner before publication and reconciliation. Fresh managed recipes/materials require their
own actual current source/runtime qualification and new approval. Source graphs
that bind old Project IDs/recipe hashes remain archived evidence; the
converter never leaves those source external graphs runnable with dangling
references. Current nonexternal graphs remain only when their current owner
validates them. Current Project IDs/root bindings/manifests have actual new
identities. Configure the service's
project roots from `prepared.json` and configure current live producers to write
their activity to those selected roots. Original root handles are never silently
rebound. Staged roots become retained current files after successful publication.

A failure before commit rolls back active row publication. A lost commit
acknowledgment is **unknown**, so keep writers stopped, reopen Metadata and run
the same command with mode `reconcile` instead of `publish`, retaining the exact
stage/hash. It either verifies the saved
receipt, complete domain/audit inventories, sequences, original catalog files and
current Project reads without writes, proves the exact original inventory is
unpublished without performing publication, or refuses. Reconciliation never
replays conversion or resubmits a Run. Any inventory drift, missing/corrupt archive/input, source application change,
wrong destination, conflicting reference or duplicate/missing disposition blocks
publication. A confirmed rollback can retry the same unchanged stage.

After publication independently compare accounting to original receipt and
current rows/files; back up/restore the completed current catalog using existing
backup tooling and separately preserve the retained external staged roots.
Perform fresh-process current Project inspection with original inputs and this
converter unavailable. The fixtures cover small actual PostgreSQL records,
scientific bytes, archive failures, transactional rollback, duplicate/re-entry,
lost acknowledgment and backup/restore/cold inspection. They do not establish
production 120-Project/160-Run completeness, real CUDA execution, browser acceptance
or physical model parity. No complete catalog rehearsal or cutover is claimed.

The frozen fixtures have been retired from ongoing application CI after verified
cutover. Retain and invoke both archival test modules explicitly from the candidate
Tuldok root against a disposable isolated PostgreSQL database only:

```sh
PYTHONDONTWRITEBYTECODE=1 python -B -m unittest discover \
  -s tools/migrations/rheon-lab-once/fixtures -p 'test_*.py' -v
```

The migration fixture moved from `tests/test_rheon_lab_migration.py` into this
`fixtures/` evidence directory. The dependent historical result inspection moved
from `tests/test_migration_independent_review.py` to
`fixtures/test_scientific_result_inspection.py`, preserving its exact scientific
marker assertion. The installed runtime alias regression stays in ordinary CI as
`tests/test_installed_runtime_alias.py`; it imports no converter or offline fixture.
The ordinary `python -m unittest discover -s tests` command cannot discover the
archival modules, and no workflow invokes this offline directory. **Keep this
whole directory excluded from deployed artifacts and ongoing CI.** Original
qualification receipts retain their pre-retirement commands and hashes; retirement
changes test placement/import roots and this explicit invocation, never converter
behavior. Retain the frozen converter, fixtures and receipts as migration evidence only. Current
application imports and startup must remain independent of this directory. Do
not add obsolete-record validators or source-format loaders to normal owners to
make a failed conversion succeed.
