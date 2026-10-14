# Remaining-work audit and actual producer-v2 readiness

## Completion correction

PR38–41 satisfy the named bounded workspace M1/MB/M2/M3/M4/M5 and A1–A12 claims. They do **not** establish that the broader persistent all-remaining-Tuldok goal is complete. In particular, [dataset-workflows](../../dataset-workflows/plan.md) explicitly keeps its overall objective open until A8, model-assisted image/text candidates and grounded transformations. Its old storage/browser/publication wording is partly historical and must be reconciled against current source rather than copied as fresh blockers.

The independent read-only milestone auditor confirmed these dispositions:

| Item | Exact rationale | Remaining work / trigger |
| --- | --- | --- |
| ASR | Original main c522bf6 workspace plan M4 explicitly says audio works without ASR; its task paragraph requires a later production Pumas contract and actual runtime. The recorded source pin ad31e391 advertised experimental audio with `production_available:false`. | A later adapter, not an unmet required M4 claim. Re-inventory current Pumas capability and installed permitted model before admission. This audit does not assert the old production flag is still current. |
| General 3D training | Original main workspace plan Out Of Scope explicitly excludes it. M5 is import/inspect/review/export per subtype, not a general trainer. | Product/task/consumer, target labels, family allocation and evaluation contract need selection before an implementation milestone. Not merely missing hardware. |
| Native Pantograph | Original S1 is conditional and expressly permits a small Tuldok-owned fixed DAG. [Graph-choice evidence](../../dataset-centered-workspaces/reports/m2/graph-choice.md) rejects embedding for that bounded slice. Pinned source exposed Rust/C#/BEAM hosts, not demonstrated Python/headless REST; native build/packaging and lifecycle were unqualified. | Reassess only with a concrete supported host and useful replacement outcome. Missing Rust in the old environment was evidence of an unperformed spike, not permanent impossibility. Current graph already fulfills the admitted fallback. |
| Real grounded rewrite success | [Actual Qwen smoke](../../grounded-text-candidates/reports/real-pumas-smoke.md) exercised a real installed local model, but it returned invalid placeholder/class/quote output; Tuldok correctly rejected it. | Positive real-model draft admission → explicit review → release remains unqualified. Current model/runtime availability must be re-inventoried; do not claim no model was ever available. |
| Real caption success | [Caption plan](../../caption-proposals/plan.md) explicitly qualifies controlled-provider lifecycle but not actual valid model output. | Qualify the existing positive image-model path with a supported currently available runtime. Mock success is insufficient. |
| Other grounded transformations / masks / retrieval | Grounded M2a explicitly excludes Q&A/instruction generation, multiple contexts, entity rewrites and image suggestions. Broader annotation M3 is deferred to actual consumers and UI feedback. | Reconcile delivered caption/instruction data support; choose concrete remaining consumer semantics before implementing new generation or segmentation. |

No new model download, paid service, producer simulation or speculative training scope is authorized by this audit. Existing development authority covers bounded adapters, tests, preparation and review. Keep overall completion open until required remaining evidence is satisfied or explicitly dispositioned by its owner.

## Current upstream facts

- Tuldok remote main: `c522bf6b5eaf94d89811578c9e73aecfdba4ef9e`; PR41 base for this plan: `cafe533a3289df773f1f5e4a8b21c65dc212e3b2`.
- Rheon remote main: `2209012bc5f902693d0f695ec1c2d854126af317`.
- [Rheon PR32](https://github.com/MrScripty/Rheon/pull/32) merged 2026-10-09, merge `4c6e7f3d888c074f921d6a9a7a716212620c1dcf`, final head `2497f3eacbfc227b9b6acd5b669e1daf7fe44751`.
- Actual recorded native packet source is earlier `020437fa638ad56823b544ba1f9207ceef065f12`, tree `3cf138c626564853f05b8b3114cc77b8ebe152d8`. Subsequent PR32 integration retained that historical packet rather than rerunning physics.
- [PR53](https://github.com/MrScripty/Rheon/pull/53) is open at `99bd03905a5e4f670328abf12f2fae3a0ee3ab20`, stacked on PR48. Its SimulationSession, MaterialSession and PressureSession APIs do not replace completed-dataset publication. `tools/export_dense3d_sequence.py`, `tools/import_dense3d_controls.py` and `docs/implementation/dense3d-producer-controls.md` have no diff from main to PR53. The simulation API explicitly says it does not publish a complete manifest or capture controls and points to the existing `--producer-controls-v2` exporter.

## Exact packet and local missing evidence

PR32 includes an actual-packet handoff, not just authored fixtures. Library exact-name search resolved `Rheon-PR32-actual-producer-v2-020437fa-compact-packet.zip`, Library ID `libfile_880a2f02d3248191a41d79d5684be891`, file ID `file_0000000037d8822f96576517bb0ee9b5`, 73,722 bytes. The PR records archive SHA256 `66a0f6d4e993b4be19df51ac39944bdb8b937078aa058218a849fef9bc6ddb2e` and version 0; current Library search did not expose a version. Archive contains `packet/` with all three files and handoff record. Metadata discovery is not byte materialization.

| File | Bytes | Recorded raw SHA256 | Current local evidence |
| --- | ---: | --- | --- |
| run.json | 7596 | `3aa73803dff2fa8ef374a98ed0528fbfa4c11fe97dcc6298b8a2105ed4220408` | Exact PR JSON block plus final LF recovered; length/hash verified |
| controls.json | 10434 | `be1f0f07a26099e45d81a08d77d7eccba3d14cee05181b46881503019adcb7a4` | Exact PR JSON block plus final LF recovered; length/hash verified |
| frames.jsonl | 518951 | `1f0cb462f6d145cdaca62a11d180c1bbcb0da6f8a7dae5369faf0be8f2dcdd28` | Original bytes not materialized locally |

The manifest identifies original executable SHA256 `dae9bc63e77f293aeb55e6876d6d1de6290bf56e00bc5072f944fc97856870ec`, Rust/Cargo 1.92.0, actual command and tracked source hashes. These are recorded provenance, not an independently replayed execution in this audit. Full source/receipt verification remains part of qualification.

The current Library skill's supported download helper was invoked for the exact resolved archive. It failed with `library download request failed: hosted apps tools/list request failed: network` before materialization. No alternative credential, signed-URL workaround, transfer bypass, guessed content or simulation rerun was used. This is a concrete transfer failure, not an authorization rejection and not evidence that the producer bundle does not exist.

Therefore the old generic “needs a completed producer bundle” statement is superseded: the bundle is recorded and discoverable; original frame bytes and the packet handoff receipt still need successful supported retrieval and verification locally. No physics or PR53 work is required to establish that first observation.

## Current consumer gap and next finite action

`rheon_sequences.admit` currently accepts exactly `run.json` and `frames.jsonl`; `prepare` calls the source-pinned v1 validator and emits a two-file immutable bundle. `SequenceAssets` captures run/frame origin hashes and its bound excludes a third controls payload. The reader, release validators, import UI/batch path and controls preview therefore need coordinated explicit v2 support. Retaining a manifest that happens to mention controls is insufficient.

The [new finite plan](../plan.md) proceeds with pinned validator/adapter preparation and labelled negative fixtures without waiting for packet transfer. Actual V2 user acceptance remains blocked only where original evidence is necessary. Separately, reconcile dataset-workflows A8 and inventory available real Pumas text/vision capabilities before selecting the next actual positive-path qualification. Do not close the persistent goal using the workspace plan's narrower acceptance.
