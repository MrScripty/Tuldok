# Frozen static-mesh validation

`mesh_release.py RELEASE.zip` reads a local mesh-only `canonical_v1` export and
prints a JSON integrity report. The application exposes the same read-only
operation at GET `/api/workbench/mesh-release-validation/<release_sha256>` and
an explicit **Validate mesh release** button beside a successful canonical
release download. The route binds the bytes to the named SHA256. A validation
error leaves the download intact. No record, review, release or database changes.

The reader supports 1–64 whole `tuldok_mesh_v1` meshes, 64 MiB physical/logical
release bytes, 40 MiB selected original bundles, 8 MiB per metadata member,
256 KiB per JSONL row and 64 JSON nesting levels. Only stored, unencrypted ZIP
members with exact canonical paths are accepted; no extraction or client-supplied
server paths. The original mesh profile's bounds apply independently. Files are
read once into bounded immutable bytes. The existing application environment is
required, with no additional numerical, renderer or training dependencies.

Validation checks unique record and asset identities, available human-reviewed
snapshots, exact bundle/PLY/sidecar associations, preserved metadata and protected
groups, current native mesh parser semantics, ordered split JSONL agreement,
mesh-only COCO projections and selected connected-family consistency. Source
bytes, native property types, vertex/triangle order, units, coordinate frame,
provenance and record revisions are retained. No conversion or sampling feeds
the validator. A spatial screen preview remains a separate first-512-triangle
display, while this operation parses every original vertex and face.

Report schema 1 has discriminator `validation: mesh_release_integrity`, complete
release SHA256, counts, frozen split counts, bounded per-mesh summaries and
`family_scope: selected_records_only`. Canonical v1 does not carry all omitted
ancestors or bridges. The report cannot prove complete split independence and
does not replay the full-catalog allocator from incomplete evidence. Review,
rights and source declarations are retained claims, not authentication or new
local human review. Scientific correctness, watertightness, normal correctness,
physics and training suitability are not certified.

Malformed archives/metadata or inconsistent associations return Workbench
`invalid`; valid unhandled release versions/formats and mixed modalities return
`unsupported`; missing local files return `unavailable`. The CLI exits 1 with
a JSON diagnostic on stderr. Publication/clear events from the existing release
owner fence late UI replies, prevent duplicate active validation and preserve
the authoritative release download. No automatic retries.

The unmerged native-mesh candidate documents third-party ASCII float32
double-rounding differences. This reader reuses the accepted exact native parser
and independent authored numeric/bit oracles. It makes no generic `plyfile`
compatibility claim and does not introduce the candidate's binary derivative,
new schema or complete-family snapshot format.
