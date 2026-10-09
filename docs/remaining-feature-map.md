# Dataset feature inventory and remaining capabilities

This inventory describes source capability, not publication, merge, scientific accuracy or trained-model quality. UI remains provisional. Existing [ownership boundaries](decisions/dataset-workbench.md), [release contracts](contracts/dataset-releases.md) and fixture provenance remain authoritative.

| Capability | Implemented bounded behavior | Remaining input or substantive gap |
| --- | --- | --- |
| Image/text targets | Original/normalized images and canonical text; corners, boxes, simple polygon instances, classes, captions, Unicode spans, corpus notes, retrieval document/query positive-only and binary judgments; raw/procedural acquisition, review/rights/history | Real-user/platform/keyboard qualification, authenticated reviewer identity, shared taxonomy/adjudication. |
| Collection/releases | Metadata filters, named dynamic searches, exact fixed sets, confirmed bulk-result selection, lineage/duplicate diagnostics, fresh preview and immutable releases | Exact grouping does not establish semantic independence or benchmark decontamination. |
| Native import | Caption folder, text-classification ZIP, detection/polygon canonical ZIP, whole Rheon v1/v2 pairs/triples, bounded meshes and vertex-only point clouds | Foreign review is not local approval; upstream originals/arbitrary adapters unsupported. |
| Simulation authoring | Named staggered fields/index/time/plane/trace inspection, human inclusive ranges, explicit save/reopen/review/history and whole-family export | Scientific target truth, free-surface/two-phase physics and physical diversity are not supplied. |
| Native numerical consumer | NumPy whole trajectories/explicit windows and whole point clouds, separate TXYZ or native XYZ/normals/RGB properties/dtypes/anchors/human coverage, atomic pickle-free NPZ, sequence-only and point-only declared family proof | Actual objective/trainer/taxonomy and meaningful independent initial/configuration or scanned families remain required inputs; mesh reader compatibility remains separate. |
| Specialized releases | Canonical COCO/typed rows, caption, Chapter8 classification, Chapter11 corpus, instruction/preference, positive-only retrieval v1 and binary retrieval v2 projections | General multi-category/multi-object COCO and the bounded Chapter9 reader projection are qualified; positive-only retrieval now uses exact fixed selections, whole-family export and unchanged JSONL reading/pure helpers; reviewed binary v2 now transports relevant/not relevant/explicit unjudged with native second-owner drafts and exact refs; graded relevance and trainer/objective remain unqualified. |
| Assisted drafts | Capability-gated caption/classification/grounded rewrite proposals, typed model/profile selection and existing-owner observation | Human-composed multi-source instructions now retain exact passage provenance and independent answer review; semantic grounding quality and joint native SDK/typed serving are separate. |
| Spatial/video | Corners/boxes, bounded human-authored simple polygon COCO with native roundtrip and actual mask reading, stills, bounded static meshes/point clouds and preserved simulation time | Holes/multipart instances, crowds/RLE, semantic masks and general video recording/extraction/deduplication/tracking remain absent. |

## Next unblocked feature

The existing canonical multi-category/multi-object COCO workflow is now qualified through fractional/subpixel authoring, explicit review, exact saved selections, immutable export, real COCO/torchvision reads and a second owner's native roundtrip. Sorted category IDs are stable within a release, not a shared persistent taxonomy. Original native categories remain separate source evidence. Authored fixtures qualify reader compatibility and rendered controls only. The narrower Chapter9 projection remains single-label/single-integer-box.

The bounded retained retrieval integration now supports separate draft/reopen/review, exact document references, positive-only relevance and immutable three-file export. Every omitted relation remains unjudged; qualification does not fit, rank, compute metrics or train. Source-grounded multi-context instruction now has bounded local authoring, deliberate source reinspection, human answer review and existing prompt/completion export with pinned JSON reading. Bounded polygon authoring/native import/canonical export now has actual pinned COCO mask and image consumers, continuous-versus-raster inspection and existing rights/review/family boundaries. Semantic target quality, broader segmentation profiles and video need separate observed contracts. Shared persistent taxonomy and adjudication remain separate product gaps.

For simulation, select an actual downstream objective before defining physical targets; coordinate a versioned producer contract and authentic independent inputs before extending geometry/duration/configuration. Do not weaken validators or perturb constructor values to fabricate independence. Synthetic-controls compatibility does not grant original producer-packet acceptance. Publication, real model/producer operations and training remain separately authorized stages.

Binary retrieval v2 preserves relevant/not relevant/explicit unjudged, exact document revisions and protected whole-family splits. Native transfer creates new local drafts/rights/history and deliberately refreshed refs after document review. Released ir_measures0.4.3 qrels parser definitions are source-loaded unchanged for reading only; no ranking/metrics/training/model quality. Bounds and transfer qualifications are in [binary relevance contract](contracts/retrieval-binary.md).

Reusable [native point-cloud consumption](contracts/native-pointcloud-consumer.md)
adds whole-cloud named arrays and bounded atomic pickle-free NPZ from existing
reviewed point-only canonical releases. Modern complete declared family proof
is mandatory; old proofless bytes remain unchanged and are refused by this
consumer. It preserves native dtypes/attributes and has no target/taxonomy or
trainer. Mesh's demonstrated external-reader float32 mismatch remains a separate
compatibility decision before adding a general mesh numerical consumer.
