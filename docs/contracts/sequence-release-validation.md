# Frozen sequence release validation

`sequence_release.validate_bytes(raw, expected_sha256=None)` and
`validate_release(path, expected_sha256=None)` are read-only consumers of
sequence-only canonical v1 releases. `python sequence_release.py RELEASE.zip`
prints the report as JSON or exits 1 with an error/code object on stderr.
`validate_release` captures at most 64 MiB plus one overflow-detection byte.
The expected hash, when supplied, must match the complete captured ZIP.

The existing Releases owner produces the archive. `canonical_release.py` owns
its shared envelope, projection and selected-family validation; the sequence
reader owns subtype rows and calls unchanged `rheon_sequences.prepare` and
`rheon_sequence_contract.verify` for the complete pinned native contract. It
never writes the catalog or release and never executes producer provenance
commands. Native validation uses temporary server-owned files which are removed
on success or failure; no archive-controlled path is extracted.

## Accepted input and proof

Accept 1–64 whole human-reviewed sequence records, with exact canonical manifest
fields, valid snapshot revisions, rights declarations, selected-family split
consistency, matching split JSONL and empty detection projections. The stored ZIP
must have unique exact member names, no compression/encryption, no preamble,
comment or trailing bytes. Metadata is bounded to 8 MiB per member, JSONL rows to
256 KiB and selected raw bundles to 40 MiB. Check every member's CRC.

Each raw nested bundle contains exactly `run.json` and `frames.jsonl`, bounded by
the existing 64 KiB and 2 MiB native limits. Frozen asset/source hashes must equal
the bundle hash. Recompute all source metadata, frame indexes and protected
trajectory/initial-family identifiers and compare with the frozen record.

The native reader enforces the existing fixed 16×8×4 dense3D pilot: nine accepted
states, native staggered MAC fields, exact shape/type/unit/axis contracts,
provenance schema, stamps, times/intervals, finite native values, declared field
hashes and the existing independent numerical transport assertions. This is
transport integrity, not general simulation or model qualification.

## Output and limits

Schema version 1 reports `validation: sequence_release_integrity`, release hash,
sequence/frame counts, split counts, `family_scope: selected_records_only`,
limitations and a `sequences` list. Each sequence reports exact identity/revisions,
source hashes, native geometry/field types/units, frame index, technical validation,
pressure semantics, producer provenance and frozen review/rights declarations.
No per-voxel field arrays or model metrics are emitted.

Canonical v1 does not contain every omitted ancestor/bridge. The report proves
selected-family consistency only; review, rights and source provenance remain
declarations. Retained actual producer fixtures are not newly executed producer
runs. Unknown formats or mixed modalities return `unsupported`, malformed or
inconsistent evidence returns `invalid`, and an unreadable path returns
`unavailable`. Existing released bytes need no migration. The reader does not
create reviews, normalize data, rewrite releases, or change current records.

Focused proof lives in `tests/test_sequence_release.py`: actual retained producer
bytes through real review/export, independent packed native-bit comparison,
physical/time results, catalogue immutability, cold optimized-Python reading,
selected-family conflicts and rehashed native corruption. Existing mesh reader
and sequence tests cover the shared boundary and native owner regressions.
Pipeline/Runs/UI qualification belongs to the milestone integration owner; this
reader alone does not close M5c.
