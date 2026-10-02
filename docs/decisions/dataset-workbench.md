# Dataset workbench: shared assets, explicit targets, frozen releases

Status: selected for reversible development-branch implementation, 2026-10-02.

Tuldok already has useful local image acquisition and corner annotation. Expanding that editor's label object into every possible modality would mingle unrelated target semantics. A separate image BLOB database would duplicate acquisition/provenance and load large objects unnecessarily. Replacing the entire app would bind an unsettled UI before proving the data lifecycle.

Add a workbench which references current image samples and preserves the existing editor. The workbench owns generic image/text annotation revisions and text records; Dataset continues to own image bytes and corners. Publication captures exact state and streams complete ZIPs to an immutable content-addressed release directory. This contains the required consistency boundary without an event system or distributed store.

The design applies the supplied methods-first Dataset Production research: annotation units precede drawing tools; exact/decoded duplicates are distinct from semantic similarity; protected relationships form connected split components; synthetic pixels and labels come from shared structured state; verification and human review remain distinct. Cooking the Cat supplies the decision procedure: define the action possible after success, compare meaningful alternatives under the same failure cases, expose consequences, and keep reversible production work proportionate.

The first exports are COCO-compatible detection JSON and explicit Unicode-span/classification JSONL. Existing corner schema v2 is unchanged. No inferred segmentation mask, DPO target, or training-success claim is added. Consumers must choose the applicable task; common packaging does not make different supervision interchangeable.

Consequences: users can use existing images without reimport. Generic and corner labels coexist as distinct tasks, not automatic conversions. Frozen releases retain copies of canonical asset bytes and require disk space/backups. The user must choose meaningful protected groups; exact grouping cannot discover semantic dependence. Deterministic examples validate a production mechanism, while broader model-assisted/source-grounded production remains a separate acceptance milestone.

Reconsider after practical scale evidence, actual consumer contracts, or UI feedback invalidates these boundaries. Main remains untouched.

Deletion retains the final authoritative legacy book/session/split relationships in an immutable source tombstone, committed with source deletion. This retains split protection for descendants without retaining deleted bytes or introducing a second live image authority. Missing historical lineage cannot be inferred; connected unknown deletions fail release validation.
