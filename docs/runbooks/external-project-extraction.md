# Extracting a legacy project into a portable directory

This runbook describes the M5 extraction contract under implementation. It is
not an instruction to migrate a personal catalog before the extraction gate is
accepted. Work on a disposable representative fixture first. Do not inspect or
migrate a user's local lab as a product acceptance test.

An extraction keeps the original stopped source and creates a new, independent
project. It is neither a database migration nor a generic SQL export. Historical
materials, Runs, Trials, source observations and their hashes retain their
original namespace. Editable copies receive destination identities through
their domain owners. No credentials, live grants, admissions, process control or
resumable operation authority enter the destination.

## Preview first

Preview uses a read-only, repeatable-read PostgreSQL view and pinned filesystem
capabilities. It does not construct `Metadata`, `Dataset`, Jobs or Runs; the
legacy `Metadata` constructor can append `.metadata-init.lock`, even with
`create=False`. Preview does not repair schema, enroll images, execute scripts,
install dependencies, contact producers, or regenerate missing bytes.

Select one exact registered project snapshot and explicit roots from the finite
families: data records, responses, preferences, saved selections and searches,
graphs, recipe drafts, model definitions, Studies, Runs, producer histories and
working files. A registration snapshot identifies captured external files; it
does not establish ownership of otherwise global data, Studies or Runs.

Review the report's required dependency closure, shared dependencies, unassigned
global records, ambiguities, missing payloads and unsupported source facts.
Parent/baseline lineage can require another Study as historical provenance. That
expansion is visible in the report and must not be presented as inferred
ownership. A required dependency cannot be excluded while claiming a complete
extraction. A saved search preserves entered criteria; its current search
results are not implicitly selected membership.

The report binds the exact selection, source schema and snapshot, backup and
external inventory. Extraction requires the same report digest and selection.
An unresolved or incomplete report is not successful empty-project creation.

## Stop through the existing owner

The explicit stop operation belongs to the currently opened legacy controller.
It first fences new requests and drains existing request handlers. It verifies
that this instance owns all five known runtime claims, drains the four producer
workers and standalone image requests, and asks the existing Run owner to prove
local worker and external custodian drainage. A peer's runtime ownership,
unconfirmed descendant cessation, failed drain, unknown outcome or lost lock
prevents a stopped-source capability from being issued.

An old backup receipt, `quiesced=True`, a process ID, an idle activity message or
a stored terminal state is not this proof. A newly opened application without
the original live owners can still preview, but reports
`cessation_proof_unavailable` until a trusted owner performs stop and capture.

The controller issues an opaque, local stopped-source lease only after confirmed
drainage, peer exclusion, read-only snapshot pinning, a verified backup and an
external payload inventory. The lease owns its connection and directory
capabilities. It cannot be reconstructed from JSON or imported project facts.

Stopping can legitimately persist cancellations or interruptions through the
existing runtime owners. The source-unchanged baseline is recorded **after**
that explicit stop and verified backup. Extraction itself must preserve that
baseline exactly.

## Preserve original evidence

Verify required unique payload bytes, including native BYTEA bundles, original
images/audio/scientific sources, release ZIPs, execution inputs and outputs,
runtime manifests and captured scripts. Resolve files only through current
explicit capabilities; historical absolute paths are inert evidence.

Missing original bytes cannot be replaced by running a producer, re-exporting a
release, recreating a manifest's formatting or remeasuring a result. Declared
regenerable dependencies retain visible availability. Missing required unique
bytes block a complete extraction.

Legacy storage has genuine history gaps. Saved selections/searches retain only
their current row, and image source revisions are not a complete source event
stream. A report must identify absent historical revisions, timestamps or
bindings. It must not invent earlier names, source revisions, audit events or
complete-history claims. An observed-history representation requires explicit
domain support; otherwise extraction remains blocked for that case.

## Publish and verify the destination

Use a new destination under an authorized root. Source, stopped backup,
destination and task-owned staging must not overlap. Existing destinations are
not overwritten or merged. Stage validated domain records and immutable payloads
without writable hard links, then publish atomically through the project store.
Project-owned scripts and notes remain ordinary inert UTF-8 files; copying them
does not execute them.

The extraction receipt binds the source, selection/report, request identity,
destination project/checkpoint, identity mappings, artifact completeness and
independent cold reconstruction. The deciding test opens the new project with a
fresh physical PostgreSQL projection and checks retained identities, hashes,
history, closure and source preservation. Current permissions come from the new
installation, never the imported source's access tables.

## Use the process-local transfer controller

The transfer controller takes the already running legacy Dataset and a separate,
inert control workspace. Configure publication root aliases for the verified
backup and destination; the destination alias must also be a root of the control
workspace. Root paths are pinned directory capabilities, and backup and project
names are single relative directory names. Symlink roots, publication roots
inside the source catalog, overlapping targets and existing backup targets are
refused before Stop.

The five fixed controller actions are `project_transfer.status`, `preview`,
`report_page`, `stop` and `extract`. These are controller methods; the application
transport exposes only its corresponding validated routes. An ordinary Open or
preview cannot stop a source or create a stopped-source lease.

1. Authenticate as the current legacy owner with administration permission. Read
   Status and submit the explicit snapshot, root selection and decisions to
   Preview with that process binding. Preview remains read only. Its summary
   gives the report digest and counts; Report Page exposes one of `included`,
   `required`, `unassigned`, `excluded`, `blockers`, `warnings`, `artifacts` or
   `working_files` in pages of at most 40 items. Keep the same report digest while
   reviewing pages.
2. Request Stop with the reviewed live report digest, backup root/directory and
   proposed destination root/directory. Stop validates both target locations,
   drains the actual source owner and creates the private verified backup. A
   successful Stop rotates the process binding and clears the live report.
3. Sign in explicitly using credentials issued independently by the control
   workspace. Source credentials are not copied, rebound or accepted as control
   credentials. The stopped source's authentication database may already be
   closed. Refresh Status and Preview the same explicit selection again; the
   stopped-source report now binds the verified backup and cessation capability.
4. Extract using that exact stopped report digest, configured destination,
   display name and a stable request key. Publication first produces a durable
   independent project. The controller then attempts an ordinary inert Open in
   the control workspace. Inspect the separate `selection.selected` result;
   committed publication is preserved if workspace selection fails.

The controller binding is an opaque process-local correlation value. Neither a
request nor a stored report contains the stopped-source capability. Restarting
the process does not reconstruct that capability from JSON. A failed stop after
the native source fence keeps the source fenced and exposes the failure through
independently authenticated control Status. If existing handlers have not yet
drained, the application delays its ordinary-route authentication handoff until
they finish. A native authorization denial before installation of that fence
leaves the source phase live and requires a refreshed report.

The bounded public receipt gives publication identity, source/report/input
digests, copied/missing artifact counts and independent verification. Artifact
declarations remain available through report pages. Its checkpoint and
verification describe the **current verified destination head** on an exact-key
retry, including legitimate later destination edits. The source, selection,
report and input digests remain immutable birth facts; retry does not extract
again. A changed body with the same key conflicts.

Keep the exact key after a lost publication acknowledgement. A typed unknown
outcome may already carry `committed: true` and `selected: false`; controller
Status retains that partial receipt. Retry reconciles the actual destination.
If publication failed before rename, preserve the reported staging directory for
inspection. Do not substitute a new key or assume the destination is absent.

On retry, reconcile the exact request key and input digest before attempting
another publication. Keep a published destination. If publication is uncertain,
retain task-owned staging and receipts until its outcome is checked; do not
delete a destination to make a retry appear clean. Report the exact known or
uncertain outcome and preserve the original stopped source.

## Current owner API

These are internal owner interfaces. They do not add a public HTTP, SDK, MCP or
CLI capability until those consumers have been qualified against the same
selection, completeness and outcome contracts.

```python
# Use the already opened legacy controller and its authenticated current actor.
# parent_fd is a caller-owned directory capability outside the source catalog.
from project_transfer import ProjectTransfer, preview_source

selection = {
    'project_snapshot': {'id': registered_id, 'manifest_sha256': manifest_hash},
    'roots': {'records': [chosen_record_id], 'studies': [chosen_study_id]},
    'decisions': [],
}
with preview_source(existing_dataset) as view:
    review = ProjectTransfer(view).preview(selection)
# This first report can inspect closure but cannot claim cessation proof.

with existing_dataset.stop_for_project_extraction(parent_fd, 'stopped-backup') as source:
    transfer = ProjectTransfer(source)
    report = transfer.preview(selection)
    # Review can_extract/blockers, required dependencies and unassigned inventory.
    receipt = transfer.extract(selection, report['report_sha256'], parent_fd,
                               'new-project', 'New independent project',
                               'caller-owned-extraction-key')
```

The selection accepts only the finite root arrays `records`, `responses`,
`preferences`, `selections`, `searches`, `graphs`, `recipe_drafts`,
`model_definitions`, `studies`, `runs`, `releases`, `exposures`, `model_materials`,
`recipe_materials`, `runtime_materials`, `producer_jobs` and `working_files`.
Omitted arrays are empty. Producer roots identify one known kind and job ID;
working files identify `script`/`note` plus an exact `scripts/...`/`notes/...`
path. Explicit decisions identify a known family and exact canonical ID, an
include/exclude choice and the entered reason. They do not authorize omitting a
required dependency.

The stopped backup is private legacy custody and includes the original access
rows. Portable domain records exclude those rows. The canonical extraction
manifest retains only non-secret source digests, the normalized selection,
actual first-adoption observations for selected working files, fixed-family
population counts and copied/missing-regenerable artifact identities.

A successful receipt has `committed: true` and `selected: false`: publication
creates a project without changing the application's selection. A lost final
acknowledgement returns an `unknown` error carrying its known committed identity
when that identity can be proven. Inspect that destination and repeat the exact
key/input. Before publication, failure retains `staging_directory`; it does not
claim the destination exists. A missing unique payload, absent legacy history,
unknown cessation, unsupported schema or required exclusion stays a blocker.

Current focused evidence uses disposable PostgreSQL 17 fixtures and private
filesystem roots. It covers ordinary cold Open under a different installation,
current scoped inspection and revocation, actual handler drainage, peer
exclusion, exact source/archive preservation, malformed or missing source facts,
required closure, failed publication and lost-reply reconciliation. Historical
fixture custody is not a claim that an imported process was executed again or
that an old scientific result was remeasured.

The extraction-only closer has a bounded deadline. If an existing owner does not
finish closing, the controller returns `source_busy`, keeps new requests fenced
and issues no stopped-source lease. Its single owned closer may finish later;
that does not turn a timed-out request into a successful extraction or revive
ordinary requests. A closure failure or unconfirmed descendant remains unknown.
The ordinary application's `close()` semantics are unchanged.

The focused owner gate is:

```sh
# Run from the repository root with a disposable PostgreSQL fixture DSN only.
PYTHONPATH="tests:.:${PYTHONPATH:-}" python -m unittest test_project_transfer -v
```

The current owner checkpoint passed **20 tests in 17.495 seconds** on the private
PostgreSQL 17.11 fixture. The cross-Study case retains two Studies, two Trials,
parent and baseline lineage, a settled reservation, a candidate, native Run
artifacts, model and recipe materials, a frozen release and shared source bytes.
A separate ordinary Open uses a different current installation and fresh
physical SQL projection, while constructor tripwires verify that Jobs and Runs
do not start. The historical case establishes custody and reconstruction only;
current-host preflight and actual execution have their own gates.
