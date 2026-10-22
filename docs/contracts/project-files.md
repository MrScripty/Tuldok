# External text project files

This is the M1 text-project vertical of the [external project plan](../plans/external-project-save-load/plan.md).
Save As, non-text scientific families, execution and extraction remain unavailable
until their later milestones pass. The [authority decision](../decisions/external-project-authority.md)
explains the canonical boundary.

Start an explicit project-file service with a separate installation control
directory and one or more existing trusted root directories:

```sh
python app.py --data /private/tuldok-control \
  --project-files-root research=/home/me/research
```

Use the service's normal local owner bootstrap, then visit `/project-files`.
New creates a previously absent relative directory under a configured alias.
Open chooses an existing project directory. Root aliases and credentials stay
local; a project's canonical text never contains a root's device/inode binding
or a credential. This mode cannot be combined with legacy `--project-root`.

## Canonical format

`.tuldok/project.json` has format `tuldok_project_v1`. It is the sole current
checkpoint: project UUID, display name, membership roots, sorted record inventory,
request receipts and a SHA256 checkpoint. Its digest covers canonical bytes of
the document with `checkpoint` omitted. The store supports only its declared
format and family; malformed and future versions fail before projection writes.

Each inventory entry identifies a rooted immutable file
`.tuldok/records/workbench_text/<record-id>/<sha256>.json`, its format, namespace,
byte count and SHA256. `workbench_text_v1` preserves original source, current
Workbench record, every annotation revision, non-secret audit facts and operation
receipts. Canonical JSON is UTF-8, sorted keys, two-space indentation, LF ending,
finite bounded values, and no duplicate keys. The namespace equals the logical
project UUID. No generic recursive ID rewriting is permitted.

New stages and fsyncs a complete project in a sibling directory, then publishes
it with atomic no-replace rename. An edit publishes and fsyncs new immutable
records before atomic replacement of the checkpoint. Unreferenced staged records
are not current authority. A failure with uncertain checkpoint publication fences
further use until explicit recovery. No cleanup deletes published history.

Save verifies/fsyncs the full selected closure and returns a durability barrier.
A no-op Save leaves canonical bytes unchanged. Close drains synchronous text
requests, performs the barrier, releases the projection and file lock, and rotates
the binding. No worker-capable domain is admitted in M1. Open/New replacement
validates an incoming inert projection before releasing healthy current custody.

The generated `.gitignore` excludes `/artifacts/`, `/.tuldok-local/`, `/.venv/`,
`/__pycache__/`, `/PGDATA/` and `/output/`. New does not initialize Git. Authored
records and the checkpoint are suitable for Git; database binaries, model weights,
caches and large generated data must stay outside tracked content. M1 does not
yet provide the artifact manifests required to admit those families.

## Consumers and outcomes

The shared operation registry owns `project_files.*` contracts and exact contract
hashes. Browser, SDK, CLI and MCP negotiate those contracts. Lifecycle selection
requires current owner authority. Scoped agents may inspect text and submit draft
annotations; human review still requires the owner. Every project action is bound
to an opaque workspace generation and its expected canonical checkpoint.

Use `ProjectFilesOwnerClient` only for the narrow owner project-file operations.
`ProjectFilesClient` wraps a negotiated client. CLI text `file-*` commands take
`--arguments` JSON files; lifecycle commands use explicit flags and select
`--owner-project-files` with a
private owner configuration. Generic AgentClient remains agent-only. Keep request
keys across lost replies; the same key with changed input conflicts. Text receipts
survive SQL loss and return the originally committed revision.

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
and independent Save As are M4 capabilities and are not advertised in M1.
