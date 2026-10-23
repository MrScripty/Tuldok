# External project files

The [external project plan](../plans/external-project-save-load/plan.md) owns current
milestone acceptance. This contract covers the external-directory format and
its finite owner operations. Execution/recovery, independent Save As and
extraction have separate acceptance evidence; an unavailable capability must
refuse before effects. An in-progress draft is not final feature acceptance.
The [authority decision](../decisions/external-project-authority.md) explains the
canonical boundary.

Start an explicit project-file service with a separate installation control
directory and one or more existing trusted root directories:

```sh
python app.py --data /private/tuldok-control \
  --project-files-root research=/home/me/research
```

Use the service's normal local owner bootstrap, then visit `/project-files`.
New creates a previously absent relative directory under a configured alias.
Open chooses an existing project directory. Root aliases and credentials stay
local. Historical snapshots may retain inert root identities or runtime path
strings as evidence; they never establish a current filesystem binding. Tokens,
token hashes and live credential records are excluded. This mode cannot be
combined with legacy `--project-root`.

## Canonical format

`.tuldok/project.json` has format `tuldok_project_v1`. It is the sole current
checkpoint: project UUID, display name, membership roots, sorted record inventory,
request receipts and a SHA256 checkpoint. Its digest covers canonical bytes of
the document with `checkpoint` omitted. The store supports only its declared
format and family; malformed and future versions fail before projection writes.

Each inventory entry identifies a rooted immutable file
`.tuldok/records/<family>/<record-id>/<sha256>.json`, its format, namespace,
byte count and SHA256. Original `workbench_text_v1` preserves original source, current
Workbench record, every annotation revision, non-secret audit facts and operation
receipts. New operation receipts use `project_operation_v2`, whose identity
includes the current project UUID. Old v1 receipts remain exact historical
facts; a fork cannot reactivate their request authority. Canonical JSON is
UTF-8, sorted keys, two-space indentation, LF ending,
finite bounded values, and no duplicate keys. The namespace equals the logical
project UUID. Historical domain catalog IDs, record identities and hash inputs
remain exact within those envelopes. No generic recursive ID rewriting is permitted.

The finite additional families cover Workbench data/source/annotation/response/
preference histories and tombstones; saved selections/searches; frozen releases
and exposures; model/graph/recipe revisions and immutable materials; project and
runtime snapshots; Study/Trial/Run/candidate/lineage facts; and four producer
history families. Owner decoders validate their complete reference closure.
Unknown families, future formats and unclassified authority-bearing fields fail
before reconstruction. Older text is not silently upgraded on Open.

New stages and fsyncs a complete project in a sibling directory, then publishes
it with atomic no-replace rename. An edit publishes and fsyncs new immutable
records before atomic replacement of the checkpoint. Unreferenced staged records
are not current authority. A failure with uncertain checkpoint publication fences
further use until explicit recovery. No cleanup deletes published history.

Save verifies/fsyncs the full selected closure and returns a durability barrier.
A no-op Save leaves canonical bytes unchanged. Close drains synchronous project
requests, performs the barrier, releases the projection and file lock, and rotates
the binding. Active or unknown local Run, producer, runtime-copy and package
writers block Close, replacement and fork. A drained thread alone does not prove
that an external provider has ceased. Open/New replacement
validates an incoming inert projection before releasing healthy current custody.

The generated `.gitignore` excludes `/artifacts/`, `/.tuldok-local/`, `/.venv/`,
`/__pycache__/`, `/PGDATA/` and `/output/`. New does not initialize Git. Authored
records and the checkpoint are suitable for Git; database binaries, model weights,
caches and large generated data stay outside tracked content. Intrinsic
`project_artifact_v1` records contain SHA256 and byte count; domain edges classify
role, media type, unique/regenerable preservation and required operations.
Present bytes live at `artifacts/sha256/<sha256>` or an explicitly supplied local
resolution. Git transports canonical text and manifests; an independent payload
transfer supplies untracked bytes. Missing payloads remain visible. Consumers
verify exact captured bytes before use; they never regenerate historical evidence.

## Consumers and outcomes

The shared operation registry owns `project_files.*` contracts and exact contract
hashes. Browser, SDK, CLI and MCP negotiate those contracts. Lifecycle selection
requires current owner authority. Scoped agents may inspect data and submit draft
annotations; human review still requires the owner. Every project action is bound
to an opaque workspace generation and its expected canonical checkpoint.

Use `ProjectFilesOwnerClient` only for the narrow owner project-file operations.
`ProjectFilesClient` wraps a negotiated client. CLI domain `file-*` commands take
`--arguments` JSON files; lifecycle commands use explicit flags and select
`--owner-project-files` with a
private owner configuration. Generic AgentClient remains agent-only. Keep request
keys across lost replies; the same key with changed input conflicts. Canonical
receipts survive SQL loss and return the originally committed domain result.
Current permissions and any stronger owner/disclosure requirement are checked
before replay. SQL failure after canonical publication returns a durable receipt
and fences the projection until explicit recovery.

M2 domain operations return `{binding, project_id, checkpoint, value}`. Ordinary
list pages use offset/limit (default 40, maximum 40); heavy data-history pages
default to one and permit at most four. The original M1 text paging below stays
compatible. Historical Study metadata separates membership/reservation pages
from complete charge totals. Run summaries omit frozen source content. Exact
Run documents use digest-bound bounded byte segments, with current explicit
disclosure required before protected document bytes or evidence are read.
Imported disclosures remain historical observations and grant no current access.

Explicit source registration captures the original manifest and establishes a
current installation-local rooted binding. Open restores no such binding. A
fresh explicit registration may renew a moved, unchanged manifest. Reference
inspection is bounded and reports observed SHA256 separately from a declared
expected digest. An unpinned reference is labeled unverified; a declared mismatch
is refused. Scientific import requires the selected exact observed bytes and the
existing scientific owner interprets them. Project scripts provide integrations;
opening or registering a manifest does not execute them.

Owner-only artifact resolution selects an existing file relative to a configured
root. It verifies and durably copies the exact declared bytes. The receipt is a
past resolution observation; `artifact_status` reports current availability.
No network fetch, runtime installation, dependency activation or regeneration
is performed. For supported built-in graphs, explicit recipe preparation performs
a guarded current native probe before retaining the immutable material. Reading
retained native materials or historical evidence does not launch that probe.

## Explicit execution and recovery

Generic project scripts own domain integrations. Current external-script Run and
Study approval/admission use current local policy and grants. Admission and GO
intent are canonical before worker acknowledgement or GO. Measured terminal
evidence, spent budget and lineage remain project facts. Imported history supplies
no approval, admission epoch, cancellation right or resumable process. Producer
requests and candidate preparation follow the same intent-before-effects rule.

For supported native graphs, the current owner explicitly calls
`project_files.native_preflight` with the saved graph ID and revision. A valid
result binds its validation token to that exact graph and measured runtime.
`native_submit` takes the graph ID, graph revision and token; admission rechecks
current inputs and authority before launching a native Run. `native_retry`
requires an actual current local Run and creates a new attempt. These actions
require current owner execute permission, the workspace binding, expected
checkpoint and a request key. `native_reconcile` instead selects an original
current local phase with the binding and expected checkpoint, requires current
owner cancel permission, and never sends GO. Its phase ID is available through
the current native-phase page of execution health v2; imported phases are history,
not current custody.

Native execution uses the current operator's `TULDOK_TRAINING_PYTHON`, or the
service interpreter when unset. Its installed packages remain an operator trust
assumption; a runtime observation does not prove a complete dependency closure or
model quality. Open and ordinary inspection do not probe, install, train, resume
or activate a runtime. Retained validation, admission and phase facts do not grant
execution authority after a cold Open.

An optional current operator binding selects runtime sources:

```sh
python app.py --data /private/tuldok-control \
  --project-files-root research=/home/me/research \
  --project-runtime-source cpu=/private/cpu-runtime.json
```

The configuration uses the existing runtime-snapshot configuration schema.
`runtime_sources` lists aliases. Explicit Inspect measures that selected source;
Capture requires the exact inspected inventory and a stable request key, records
an intent, and copies bytes without launching them. Status distinguishes absent,
intent recorded, captured and abandoned. A cold Open has no configured alias or
cache merely because a historical descriptor contains a path.

Recovery preserves the last acknowledged binding/checkpoint. Generic Run/producer
reconciliation requires exact original local custody and proof of drain. Runtime
retry and package reconciliation additionally require the exact original physical
writer journal and canonical intent; imported intent alone is insufficient.
Explicit abandonment records the owner reason with a separate key and retains
partial bytes and scientific facts. A completed package is reconciled rather than
silently rewritten. Recovery never sends GO or executes project code.

The status endpoint is available before any project is open. It reports current
binding, local root aliases, project identity/checkpoint when selected, and
available actions. A stale binding or checkpoint is a conflict. Corrupt canonical
bytes cannot be blessed by Save. Missing unsupported families are never silently
omitted or auto-generated.

Query returns summaries sorted by ID, with `limit` (1–100, default 40), exclusive
`after_id`, and `next_after_id`. Get returns the current full record and newest
history first, with `history_limit` (1–4, default 1), exclusive `before_revision`,
and `next_history_before_revision`. The same checkpoint binds all pages. Mutation
results include their committed revision and its first history page; replay never
mixes that historical result with newer revisions. The UI exposes explicit controls
to load more records and older history.

Status may report `recovery_required`, its last acknowledged project identity,
and the selected root/directory to reopen. Explicit Open of the selected
directory is guarded by the current binding and last checkpoint. Ordinary
recovery validates canonical bytes, builds a fresh inert SQL projection and
rotates the binding. If original local custody remains, the named execution/file
recovery action must settle it first. That same-selection recovery preserves the
binding so its reply remains correlated with the caller. A failed recovery keeps the prior
custody and the recovery action available. A creation that committed but could not
be selected reports `selected:false` with the destination identity and request
receipt. Exact New retry reconciles that receipt without overwriting a different
existing destination.

Errors distinguish invalid/unsupported format, stale selection,
writer contention, unavailable projection and unknown publication. A definite
canonical commit followed by projection failure returns its durable receipt.
Inspect/reconcile that receipt instead of minting another request key. Recovery
reopens the selected directory and reconstructs the projection without scripts.

When changing Git revisions, close the project first. Open revalidates the complete
checkpoint; edits to canonical immutable files, unresolved conflict text and
inconsistent inventory fail. A changed checkout fences an already-open projection;
explicit reload reconstructs it without scripts. Git conflict resolution is manual.

## Working files and independent Save As

Adopt explicitly captures the exact UTF-8 bytes of a selected script or note,
including its history and measured hash. Merely editing a working file does not
replace an immutable scientific capture. Open never executes, repairs or restores
working files. Save As refuses an adopted file that is missing or changed until
its intended current bytes or an eligible note deletion are explicitly adopted.
A missing script remains protected: note-deletion adoption cannot remove its
captured script or make a missing script eligible for Save As.

`project_files.file_adopt_deletion` is
`POST /api/workspace/project-files/files/adopt-deletion`. It requires current edit
permission and the usual `binding`, `expected_checkpoint` and `request_key`, plus
`path`, `expected_revision` and `expected_sha256`. The path must identify an
already adopted note that is safely absent. The revision and digest must match
its current positive captured revision; an existing file, changed canonical
revision/digest or unsafe path is refused. This action records absence; it never
deletes a filesystem entry. Inspection and Open never adopt a deletion.

The first adopted deletion changes that note's document to `project_file_v2`.
All earlier positive revisions retain their exact original fields and text. A
closed deletion revision adds `deleted:true` and contains `revision`,
`sha256:null`, `bytes:0`, `text:null`, `adopted_at` and `actor_id`. This is distinct
from an empty positive file, whose text is `""` and whose SHA256 is the empty-byte
digest. `file_get` can select either revision; paged `file_history` returns
metadata, including the deletion marker, without embedding full texts. Current
inspection reports `deleted` only while that note remains safely absent, with
null expected/observed digests and zero expected bytes.

Save As retains the complete note history and deletion marker and leaves its
current note path absent in the new destination. If a note is later recreated,
inspection reports its changed current bytes. Explicit `file_adopt` with the
tombstone's expected revision and the recreated file's measured SHA256 appends a
positive revision; it preserves the deletion and earlier text in history. Open
does not recreate the note or adopt its restoration.

Save As publishes into a new absent directory, creates a new logical project and
editable identities, retains original hashed envelopes and records origin maps.
It copies required unique payloads and materializes captured working files only
into that new destination. Historical catalog IDs and material hashes remain
exact; unresolved bound drafts become explicit re-selection intents. Known
regenerable runtime binaries may remain missing with an explicit inventory;
missing unique evidence blocks a complete fork. Source bytes are unchanged.
Publication followed by selection failure reports `committed:true, selected:false`;
retry the exact request to select the already-published destination.

The [extraction runbook](../runbooks/external-project-extraction.md) covers explicit
legacy selection, stopped backup, independent control credentials and the five
transfer operations. A whole-catalog backup is private recovery custody, not this
portable project format.
