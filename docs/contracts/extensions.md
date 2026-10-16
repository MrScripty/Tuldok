# Inert project extensions

E1 implements static inspection only. Nothing here admits extension execution,
imports a numerical package, builds/installs dependencies, deserializes a model,
probes a runtime, creates a grant or submits a Run. Existing Projects owns root
selection and immutable snapshots. `extension_contract.py` owns declaration
validation/catalog derivation; Access, Pipeline, Runs and RuntimeSnapshots retain
their authority. PR62 P1–P4 must be accepted before executable E2 bindings.

## Selected project and HTTP version

Project manifest v1 remains closed and unchanged. Project v2 has all its fields
plus required `extensions`: at most 64 `{id,label,path,sha256}` references. IDs
are unique within this section. Paths and exact SHA256s are mandatory. Every
extension/source/notice/definition path is relative to the **configured project
root**, including when the manifest lives in a subdirectory. Projects uses its
existing descriptor-relative no-follow regular-file reader and pinned root
identity. Discovery never enumerates installed distributions or searches paths.

The owner browser uses these explicit HTTP operations:

- `GET /api/workspace/project-snapshots`: configured aliases and snapshot summaries.
- `POST /api/workspace/project-snapshots`: exactly `{root,manifest_path}`; registers
  a structurally valid v1/v2 immutable snapshot and returns current inspection.
- `GET /api/workspace/project-snapshots/ID`: saved references plus current catalog.

These unselected operations remain owner-only. Ordinary agents use the explicit
`project_snapshots.list/get/open` negotiated contracts described in
[agent operations](agent-operations.md#negotiated-project-snapshots-and-bound-authoring).
They remain absent from legacy agent discovery. Auth, loopback Host,
same-origin JSON and strict duplicate-key request decoding remain required.
The legacy `/api/workspace/projects` collection/open/detail remains v1-only;
v2 open/get returns `unsupported` before registration/projection and legacy
list omits v2. For v1 both HTTP interfaces produce the existing exact shapes.
No legacy operation document/digest is modified.

V2 detail adds `schema_version:2` and `extensions` containing `mode:inspection`,
`execution:unsupported`, canonical `schema_sha256`, aggregate `bytes_inspected`
and `packages`. No independent enabled-package table or editable catalog exists.
Changing enablement creates a new manifest/new project ID. Older snapshots stay
addressable; selecting a snapshot without a package is context-local disablement,
not grant revocation or global deletion. V2 currently exposes static references;
its data import, recipe creation and external evidence preview are unavailable.
Existing v1 actions retain their existing routes and semantics.

## Canonical declaration vocabulary

Data-only `extension_schemas/extension-v1.json`, `contribution-v1.json` and
`parameter-v1.json` are canonical. Their `$id` URNs resolve only through the
host's fixed local registry. No package-supplied schema or remote reference is
resolved. The decoder additionally owns bounds, exact hashes, namespaces,
source closure, inventory/default relationships and dependency selection.

`tuldok_extension_v1` has these closed fields (the JSON schema defines exact
requiredness/types/ranges):

- `package:{id,version}`, `label`, `license:{id,notices}` and `sources`.
- `host_contracts:[{id,version}]`, `runtime:{profile,snapshot_sha256?}`,
  declared `effects` and `resources:{wall_seconds,source_bytes,output_bytes}`.
- `contributions:[{id,version,kind,path,sha256,bytes}]`. Contributions/manifest
  source references are exact; source and notice references have path/hash/bytes.

Package IDs are bounded lowercase dotted names; semantic versions are exact
three-component decimal versions, without ranges or `latest`. Contribution IDs
are `package-id:local-id`. One package can declare task, reader, model, trainer,
evaluator or view contributions, with no application-object bridge. An
implementation is a source-inventory path and bounded entrypoint identifier;
it remains inert data. Contribution definitions carry the closed
`tuldok_contribution_v1` shape: identity/kind/label, exact contribution requirements,
and optional parameter/default, typed-port, finite-stage, implementation or view
descriptors as allowed by the schema. Trainer declarations require finite stages
and explicit parameters/defaults; executable kinds require an inventoried source.
Views select only the schema's bounded primitive vocabulary/query contract.
None of those declarations qualifies task meaning, numerical comparability,
rendering support or a runtime. Those remain unavailable until their owners
implement and qualify the selected contracts.

Parameter schemas use the established JSON Schema Draft 2020-12 validator with
this **closed subset**: `type`, `title`, `description`, `properties`, `required`,
`additionalProperties:false`, `items`, `minimum`, `maximum`, `minLength`,
`maxLength`, `minItems`, `maxItems`, `enum`. Types are object, array, string,
number, integer and boolean. Objects require properties and closed additional
properties; arrays require items and finite maxItems. Bounds must be consistent;
keywords must apply to their declared type; required keys must be declared;
enum members must satisfy the rest of their schema. Unknown keywords at any
depth (including `$ref`, defaults, combinators, custom formats and executable
validators) are `unsupported`. Explicit resolved defaults are validated with the
same schema, without coercion, interpolation or invented defaults. JSON numeric
and boolean semantics belong to jsonschema, not Python equality.

The optional validator is `jsonschema==4.26.0` and the complete hash-pinned
closure in `requirements-extensions.lock`. Provision it explicitly with
`python -m pip install --require-hashes -r requirements-extensions.lock` in the
selected environment. Import/startup of the contract module uses stdlib only.
Missing validation preserves discovered identity/hash but returns `unavailable`;
it cannot claim partial compatibility or install automatically. No new framework
or public SDK distribution is introduced. This existing validator/closure is
reused from agent validation; upstream package licenses remain applicable.

## Bounds and outcomes

A declaration is at most 64 KiB strict UTF-8 JSON, 16 levels and 16,384 visited
nodes. Duplicate keys, nonfinite numbers (including exponent overflow), lone
surrogates/control characters and oversized strings are invalid. Each package
has at most 64 total source/notice/definition references and 64 contributions;
source/notice files are at most 8 MiB, contribution definitions 64 KiB, stages
16 and port lists 32. A selected catalog reserves at most 8 MiB for reads, including failed/raced
attempts and overflow discrimination. Successful bytes and consumed budget are
reported separately. A failed read conservatively consumes its reservation;
exhaustion leaves remaining entries unavailable. The inherited reader rejects
oversized/special/raced files. Project
reference inspection keeps its separate inherited 64 MiB budget. Resource/effect
declarations are review information and do not widen any execution profile.

A package reports independent discovered/enabled status, declaration state,
manifest integrity, host-contract support, runtime and permission facets:

- `valid`: structural and currently inspected inventory/hash proof succeeded.
- `invalid`: malformed declaration, contradictory identity, drift or failed bounds.
- `unsupported`: well-formed format or parameter vocabulary outside this reader.
- `unavailable`: missing/unsafe file, budget, validator or exact dependency.

Manifest integrity `verified` proves equality to the selected project hash only;
it does not prove authenticity, licensing, scientific quality or source/runtime
qualification. Source/definition drift never substitutes new bytes. A malformed
package does not suppress siblings; a missing/invalid definition does not suppress
its unrelated valid siblings. Duplicate package identity with different content,
or duplicate contribution ID/version with different content, is invalid. Required
contributions resolve an exact ID/version/content intersection; transitive missing
dependencies remain unavailable, without first-provider or ordering fallback.

The only acknowledged E1 host format contracts are
`tuldok:extension@1.0.0` and `tuldok:project@2.0.0`. These are independent of P1
operation contract IDs/digests. Unknown requirements show `host:unsupported`;
all runtime/permission facets stay unavailable. Available declaration bytes never
mean execution is admitted. GET re-inspects saved exact references and cannot
activate a package, follow a new manifest, migrate history or deserialize weights.

## Store cutover and rollback

There is no DDL change. New binaries decode saved v1/v2 manifests explicitly.
The pinned old binary's `_saved/get` can silently omit v2 extensions while
projecting legacy groups. **Old binary plus a store containing v2 is unsupported**;
no machine-enforced schema gate or downgrade safety is claimed.

Before the first v2 registration, stop all writers and make a complete backup:
`python backup_metadata.py backup CATALOG BACKUP --quiesced` (see that CLI's
usage and [workspace storage](workspace-storage.md)). Keep external project roots
separately. Continue using the new binary for the post-v2 store. To roll back,
stop writers, restore the verified pre-v2 backup into a new database/schema and
new destination, verify the saved project rows, and pair the old binary only
with that pre-v2 state. Never reinterpret or mutate a live post-v2 store for an
old reader. E1's real backup/restore test proves this selected procedure; complete
extension Run/package restore remains E4 and requires P5.

Focused conformance is in `tests/test_extensions.py`; real PostgreSQL/HTTP,
legacy projection/cutover and authority tests in `tests/test_extension_http.py`;
real owner browser checks at 1440/390 in
`node tests/browser_workspace_extensions.cjs --scenario catalog`.
