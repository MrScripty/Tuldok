# Dataset ownership and frozen releases

Dataset owns original image bytes, normalized image identity and legacy corners. Workbench references existing image samples and owns independently revisioned image/text targets, text sources, sequence/mesh/pointcloud records, reviews and lineage. Immutable sequence and mesh asset stores use the same Dataset lock/transaction boundary for source, record and initial history publication. There is no competing image BLOB authority.

Different targets have explicit contracts: corner geometry, detection boxes, class labels, captions, Unicode spans, corpus notes, independent instruction answers, preference judgments and human sequence ranges are not automatic conversions of one another. Numerical simulation evidence remains separate from human labels. Technical verification and a foreign review declaration never grant local human approval.

Preview binds current exact revisions/source identities and protected relationships. The allocator keeps whole connected families together, including unselected bridges and retained deleted-source lineage; unavailable historical lineage blocks validation. Fixed source splits remain authoritative. Exact hashes do not establish semantic independence, authenticated authorship or scientific/model quality.

Publication captures the reviewed source/target snapshot, stages complete bytes, and atomically publishes a content-addressed ZIP. Later live edits do not change frozen releases. Deletion retains authoritative relationship tombstones without creating another live source authority. Current target changes preserve committed history and require separate review.

This is a trusted local data-directory application. Back up the complete directory with the app stopped. Distributed identity, multi-reviewer adjudication, broad semantic deduplication and reusable project taxonomies need separate ownership contracts. UI remains provisional.
