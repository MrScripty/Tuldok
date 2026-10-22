# External project files

The [external project plan](../plans/external-project-save-load/plan.md) owns current
milestone acceptance. This contract covers text, retained scientific history,
artifacts and non-executing metadata operations. Live execution, independent
Save As and mixed-catalog extraction require their later lifecycle milestones.
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
receipts. Canonical JSON is UTF-8, sorted keys, two-space indentation, LF ending,
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
the binding. Worker-capable domains stay unavailable until execution ownership
is integrated. Open/New replacement
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
is performed. Built-in recipe preparation returns unavailable before a native
runtime probe while that execution lifecycle remains fenced.

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
and the selected root/directory to reopen. In that state only explicit Open of
the selected directory is admitted, guarded by the current binding and last
checkpoint. Successful recovery validates current canonical bytes, builds a fresh
inert SQL projection, and rotates the binding. A failed recovery keeps the prior
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
inconsistent inventory fail. Automatic semantic merge, editable script adoption
and independent Save As are M4 capabilities and remain unavailable until admitted.
