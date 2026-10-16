# Project inspection v1

Owner: `projects.py:Projects`; PostgreSQL schema5 owns immutable registration
snapshots. HTTP and the workspace UI project the same owner. Opening inspects references without importing records. A separate explicit action may import a conforming scientific field bundle; recipe references remain non-executable and external evidence is not a Tuldok Run.

## Opening and reference schema

Configure selected directories locally when starting the application:

```sh
python app.py --data ./catalog --project-root research=/absolute/research
```

Then choose **Open project** in `/workspaces`, select `research` and enter the
manifest's relative path. Root aliases use 1–64 letters/digits/dot/dash/underscore
and start with a letter or digit. The server does not accept browser-supplied
absolute root paths. Project endpoints require loopback client addresses and
loopback Host names; existing broader application authentication is unchanged.
Only expose directories whose referenced files local application clients may
read. Project opening grants no actor/execution authority.

An external manifest can live beside an existing source checkout, so opening
does not require adding files to that checkout. All file references are relative
to the configured root, **not** the manifest's directory:

```json
{
  "schema_version": 1,
  "id": "8bd3793c538d4a0bba1d1e0c675a86d3",
  "name": "Pressure experiment",
  "data": [{"id": "capture", "label": "Trajectory capture", "path": "lab/runs/capture.npz"}],
  "recipes": [{"id": "driver", "label": "Experiment driver", "path": "lab/scripts/trajectory_experiment.py"}],
  "evidence": [{"id": "freeze", "label": "Frozen protocol", "path": "lab/experiments/trajectory-v2/freeze.json"}],
  "requirements": [{"id": "torch", "label": "Compatible PyTorch environment"}]
}
```

Every top-level field shown is required; unknown fields/versions are refused.
Use a new 32-character lowercase hex ID per independent project snapshot.
Names are at most120 characters. Each section has at most64 entries with unique
IDs (same alias syntax) within that section and labels of at most160 characters.
Data/recipe/evidence entries require `id,label,path` and optionally a lowercase
64-character `sha256`. Requirements require `id,label` and optionally `path`.
Requirements are declarations: file presence does not establish interpreter,
package, device, version or scientific compatibility. No subprocess probe,
module import, checkpoint deserialization or dependency installation occurs.

Manifest input is at most64KiB of strict UTF-8 JSON. Duplicate keys, nonfinite
numbers, lone surrogates, unsupported fields and unsafe paths fail before
registration. Paths are at most512 characters and16 components; absolute paths,
backslashes, empty/dot/parent components and control characters are refused.
The registered snapshot includes the parsed manifest and SHA256 of its original
bytes, selected root alias and root device/inode identity. Reopening identical
input returns that registration. A changed manifest or root for the same ID
returns409; there is no replacement/delete/edit operation in this stage.

## Filesystem and evidence boundary

Startup pins open directory handles for configured roots. Inspection walks
directory descriptors with no-follow flags, refusing symlinks at every component,
including final files. Only regular files are read; FIFOs/devices/directories
cannot block the file reader. Root selection itself is a trusted local startup
action and resolves the configured directory. All project access is read-only;
opening writes only Tuldok's catalog registration.

Inspection hashes at most40MiB per data reference,8MiB per other referenced file and64MiB total per detail
request. Larger regular files are reported present with unverified contents.
Bounded reads check size and modification identity before/after and refuse
observed changes. Presence, measured byte hash, equality to a declared hash and
scientific verification are distinct. `verified` means only equality to the
manifest's declared SHA256, not source authenticity or scientific correctness.

Text evidence previews permit only `.json`, `.txt` and `.md`, at most64KiB of
UTF-8 without binary control characters. The response is JSON text, never active
HTML/Markdown. An expected hash mismatch refuses preview. Other files may be
listed/hashed but cannot be parsed or downloaded through this first-stage API.

## HTTP operations and observation

- `GET /api/workspace/projects` returns configured alias names and registered
  snapshot summaries. No absolute root path or credential is returned.
- `POST /api/workspace/projects` accepts exactly `{root,manifest_path}` and
  registers a valid immutable snapshot, returning detail. A lost reply can be
  reconciled by listing; repeating identical opening is idempotent.
- `GET /api/workspace/projects/ID` inspects the saved references. It reports
  manifest `unchanged`, `changed`, `missing` or `unavailable`; a changed source
  never replaces the saved references implicitly.
- `GET /api/workspace/projects/ID/evidence/REFERENCE_ID` returns bounded external
  text plus its hash and `scientific_verification: not_performed`.

Detail is always `mode: inspection`, `execution: unsupported`. Referenced file
states are `available`, `missing`, `unavailable`, with separate integrity
`verified`, `mismatch`, `unverified`. Requirements may be `present_unqualified`,
`missing`, `unavailable`, `unverified`. Paths with missing files leave the rest
of the project usable. Removing/rebinding a configured root leaves the snapshot
visible but unavailable; matching alias alone cannot silently redirect reads.

Browser source selection remembers `project:ID` and Data/Pipeline/Runs navigation
without selecting the current catalog as that project's data. Switching projects
does not move catalog records or alter existing dirty editors. External project
mode cannot submit training. Its three panels show file references, recipe
references and external evidence respectively.

## Persistence and compatibility

Schema5 adds `workspace_projects(id TEXT PRIMARY KEY, document TEXT NOT NULL)`.
Schema1–4 definitions and stored bytes are retained exactly; use the explicit
quiesced [upgrade/backup procedure](workspace-storage.md). Complete backup
preserves registration rows, but does not copy external project roots. Back up
external research files separately. Restoring on a different filesystem leaves
root identity unavailable; explicit rebinding/migration is future work, not a
silent reassignment. Existing catalog-only startup requires no project roots.

Schema version, project manifest version and later scientific/recipe versions
have independent owners. Runtime requirements are declared file references in
v1; later qualified execution must use its own admitted runtime/permission
contract rather than treating presence as capability.

## Explicit scientific data import

POST `/api/workspace/projects/{id}/import-data/{reference_id}` selects only a saved data reference. Body requires `expected_sha256` from the displayed inspection; optional `name`, `rights`, `groups`, `parents` describe the new catalog record. The same root binding and no-follow file walk apply. Both the selected observed hash and any manifest-declared hash must match captured bytes before publication; stale selections return409. The generic project owner captures bytes and source identity; the [scientific data owner](scientific-fields.md) validates their format and owns immutable catalog custody. Opening/getting never imports automatically. Import leaves source files and project registration unchanged.

## Explicit project v2 extension inspection

Project v1 and its legacy HTTP/agent operations remain closed and unchanged.
[Extensions](extensions.md) defines project v2's exact immutable `extensions`
references and the unselected owner-only `/api/workspace/project-snapshots`
browser/HTTP projection. The separately negotiated `project_snapshots.list/get/open`
contracts admit current scoped agents, with bounded pagination and explicit
schema-version inspection. Legacy list omits v2; legacy open/get refuses it before
new effects. The [agent contract](agent-operations.md#negotiated-project-snapshots-and-bound-authoring)
owns these new projections and selected static-authoring versions. V2 discovery
is inert and never treats a package declaration as runtime/admission authority.

There is no metadata DDL change or old-binary refusal gate. An old binary may
silently project saved v2 as v1. Stop all writers and retain a complete verified
pre-v2 backup before first v2 use; pair post-v2 stores only with the new binary.
Rollback requires restoration of that pre-v2 state into a new database/schema and
destination. See the extension contract's cutover procedure and executable test.
