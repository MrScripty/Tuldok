# Required source fixtures and provenance

Fixtures are retained inputs/authored generators, not approved targets, additional physical families or runtime QA results. Existing bytes remain unchanged; generated outputs belong in ignored build/output. No new producer execution or large producer packet is needed.

| Input | Origin and required role |
| --- | --- |
| `tests/fixtures/rheon_actual_fee7b4a` | Retained actual16×8×4 constructor plus8 accepted steps at exact `fee7b4a139574f87b259796b1ba8698a41d31ac1`, tree `7a8809b5609610337a40429f3540232aebb89125`. Four files529,032bytes, raw pair526,264, frames518,951; already in public base. Required actual native-bit/axis/time/stamp/HTTP/browser checks. Existing receipt/README bind raw hashes and transport scope. Historical command paths are immutable provenance, never commands or import paths. |
| `rheon_source_derived.py`, `rheon_synthetic_v2.py`, `rheon_authored_controls.py` | Explicit synthetic field/control factories and authored v1 assertions, separately named. Same constructor/provenance variants/windows do not establish physical diversity. |
| `meshes/*.ply` and sidecars | Tiny tetrahedron/open-surface topology/units/frame/hash contract inputs, not screenshots or segmentation labels. |
| `native-caption-release`, `workbench-ui` | Eleven retained lossless manifest/metadata/PNG/asset-JSONL inputs. Exact sizes/hashes/original locators remain in `qa/historical-artifacts.json`; only required input records survive that index. |
| `diffusion_check_image_data.py` | Unchanged hash-pinned chapter26 validator, not a model or generated output. |
| `train_image_classifier.py`, `tiny_transformer/*.py` | Unchanged published book-consumer source, pinned hashes/attribution; miniature input generators remain separate. No checkpoints/companion ZIP added. Trainer execution excluded from current no-training QA; upstream reuse/evidence boundaries remain, without new blanket license. |
| `pumas-http-pr51`, `pumas-typed-v1`, `pumas-owner-reuse` | Source-derived advertisements, controlled native capability captures and authored HTTP/Rust harnesses. Existing manifests label exact independent pins/controlled origin; no learned model included. |
| QA registry and instruction/preference consumer pins | Exact gate/package/source identities, never prior runtime results. |

See [simulation pins](contracts/simulation-sequences.md) and attribution beside retained book sources. Optional dependencies/harnesses require separate provisioning/authorization. Fixtures never request a producer/provider rerun.

`native_pointcloud_fixture.py` uses the retained authored actual colored/XYZ PLY
pairs, one sidecar-only provenance variant and an unselected known deleted text
parent. The three clouds form two declared fixed-split families; the bridge is
graph QA rather than a scanned source. Whole raw pairs and separate native
properties are checked through actual pinned plyfile/NumPy and pickle-free NPZ,
including a second owner's new draft IDs/review. No scanner samples, physical
independence, semantic labels or training corpus are claimed.

The detection reader retains two unchanged published Chapter 9 files with hashes and attribution in [detection-reader-source.json](../tests/fixtures/detection-reader-source.json). Its six retained authored image fixtures and test-only annotations simulate workflow review; they are not a human-labelled corpus or meaningful physical diversity. Only the reader/helper are invoked; no trainer, predictor, model, checkpoint or download.

`general_coco_fixture.py` reuses those same six authored lossless PNGs with test-only multi-object targets: exact-case labels, repeated categories, overlap, fractional/subpixel edges and reviewed empty-box negatives. Its paired split families exercise ownership boundaries; they do not establish real-world independence. `coco-consumer-pins.json` binds the actual pycocotools2.0.11 and torchvision0.23.0 readers. Programmatic and rendered review actions are QA simulation, not authenticated human annotation.


`polygon_fixture.py` reuses those same six authored16×12 RGB images, with manually authored rectangle, fractional concave L, triangle and tiny positive simple rings. Independent explicit bitmap expectations contain16,20,6 and0 pixels respectively, while continuous areas are16,14.25,8 and0.015625. The tiny ring uses15.25..15.375 x and11.25..11.375 y; observed pinned decoding corrected a preimplementation assumption that a larger0.0625-area ring would be empty. Fixture correction did not weaken geometry or decoding. Three reviewed empty records are separate negatives; a positive ring decoding to zero pixels remains a positive instance. `polygon-consumer-pins.json` separately pins actual mask.py and the retained compiled wheel extension, with platform/build provenance limits. Automated draft/reopen/rights/review actions remain QA simulation, not authenticated human annotation or semantic truth.
