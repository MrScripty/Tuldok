# Issues and decisions requiring follow-up

| ID | Severity/evidence | Relationship and owner | Disposition and required verification | Revisit trigger |
| --- | --- | --- | --- | --- |
| I1 | Medium: PR33 lifecycle failure at `581fa5c`; prior typed-Pumas detail, current failed check verified | UI integration owner; compact layout overlap | Defer fix outside docs scope. Inspect current head and successful affected/CI gates before reuse; do not retry inaccessible logs | M1 integration |
| I2 | Medium: PR32 lifecycle failure at `83b2df9` | Documentation/UI owner; existing screenshot work | Preserve branch. Reconcile README link on integration; old screenshots do not satisfy new UI gates | PR32 review/merge under separate authority |
| I3 | High: bounded mesh branch `dd7661d` contains a broad unmerged stack | 3D and integration owners; baseline/contract uncertainty | Defer branch adoption. Review actual current diff and native reader/browser evidence by subtype | Before M5a |
| I4 | Medium: no Standards Engine MCP or Tuldok local agent skill/config available | Planning author; tooling evidence | Complete source/template/structural/manual review now; explicitly report unavailable Engine routing, no certification claim | A configured application-purpose Engine becomes available |
| I5 | High: Pantograph host packaging/transport unqualified for Tuldok | Integration owner | S1 bounded real no-model embedding probe; adopt only demonstrated surface or retain small local DAG | Before M2 graph-engine admission |
| I6 | High: Pumas audio is experimental, production unavailable | Audio/inference owner | Local audio data work proceeds; keep ASR disabled until producer/runtime qualification and consumer tests pass | A supported production contract/runtime is available |
| I7 | Medium: trainer fixture is not app lifecycle and omits per-example output | Run owner | M2 dedicated adapter, environment limits, prediction mapping, process/cancel/restart and artifact evidence | M2 admission |
| I8 | Medium: no current volume format/consumer selected | 3D owner | S4 bounded format choice with affine/grid reader proof; no generic 3D claim | Before M5b |
| I9 | Medium: new docs branch is outside push CI allowlist; PR CI invokes training-bearing checks | Planning author/integration owner | Docs-only source checks are the planning gate. Do not open a PR that starts excluded training in this task; no workflow changes to evade scope | Separate PR/CI authorization or future implementation |
| I10 | High: distributed SQLite coupling; PostgreSQL lifecycle/migration not qualified | Storage/integration owner; MB before M2 persistence | Preserve all owners/bytes/history/rights/receipts through new-database migration; qualify explicit transactions, two independent connections, local lifecycle and metadata+artifact restore. Stop on lossy conversion or unsupported values; no silent second production backend | S6/MB admission and before cutover |
| I11 | Medium: M1 environment lacks pinned TRL/datasets/transformers/Torch/accelerate/tokenizers for the full training-bearing consumer aggregate; prerequisite receipt `build/qa/qualification/run-z24othta/gates/summary.json` is blocked | Parent/integration owner; full merge qualification | M1 contracts/browser, 417 Python tests, 43 existing controller/static gates, legacy browsers, independent review and focused hosted CI passed. Run the remaining registered consumer gates in the qualified integration environment; do not infer aggregate success or acquire large runtimes/models in this UI task | Combined candidate qualification before merge |
| I12 | High: initial hosted runs38173918147 and38174382414 failed Python discovery; log download returned HTTP403 | Storage/integration owner; MB qualification | Clean TCP reproduction identified credential loss in the independent-reader fixture; corrected to use validated Metadata.dsn without changing assertions. Both authentication styles pass. Qualified by parent handoff at 9e94d69484218e64a3ee1bddcf4c61d8aa93df16 and successful run38175261609; preserve no guessed attribution to earlier Pumas failures or denied-log retry | Exact-head hosted result for the helper correction |

These rows retain the original bounded planning findings. The plan's ownership
review prevents introducing duplicate data/graph authority. Their current
M1/MB/M2 resolution is recorded below; later modality claims remain pending.


Integrated I12 retains MB branch issue I11; integrated I11 remains the UI consumer-environment finding. Parent has admitted the exact qualified MB commit; combined-app qualification remains separate.

## M1/MB/M2 resolution

- I1/I2: PR33 was inspected but never merged/copied; existing screenshot work was preserved. The separately implemented workspace passed its own combined gates. Neither external branch's failing check was waived.
- I5: S1 selected the permitted small fixed DAG after pinned Pantograph source inspection. Native Pantograph remains deferred and unqualified.
- I7: The dedicated bounded CPU adapter, durable runs, actual per-example results and lifecycle/recovery gates passed. The original trainer fixture remains an independent unchanged oracle.
- I9: Later explicit M1/M2 implementation and CI admission superseded the planning-only restriction for these feature branches. No main merge or deployment was admitted.
- I10/I11/I12: Parent accepted exact MB9e94d69; combined907da2f passed 93 lifecycle steps. The final image checkpoint acac0d3 passed all 98 steps without skips, including 507 Python tests and the pinned consumers. Earlier failures remain in the evidence history.
- The later inherited Pumas browser readiness failure was reproduced, repaired only in the test, independently reviewed and closed by complete successor CI38180720462; see [M2 verification](reports/m2/verification.md).
- I3/I4/I6/I8 remain their stated bounded follow-ups: unreconciled 3D branch, unavailable Engine MCP, unqualified production ASR and unselected volume consumer. They do not turn the delivered bounded image workflow into an unqualified native/modality claim.


## 2026-10-12 bounded text/audio follow-through

- Independent review accepted the new text, WAV and explicit schema3 sources and their combined integration. Demonstrated defects in thread limits, archive failures, unknown lineage, hidden audio form validity, late playback and nested rollback custody were fixed with regressions before acceptance.
- The combined audio/text family boundary preserves unselected bridges without enabling audio training. A real old image result passed complete-backup/explicit-upgrade/reopen preservation checks. See [combined evidence](reports/combined-20261012.md).
- PR34 qualifies the preserved image base; the new stacked draft requires its own automatic hosted pass. Existing PR32/33 checks remain separate and unwaived. Audio Pipeline/Runs, production ASR, additional 3D and native Pantograph remain pending under their original bounds.

## 2026-10-12 next bounded admission

- PR35's exact corrected head passed every hosted gate and independent review; separate explicit user approval merged PR34/35. Their previous pending state above is historical. New feature branches still require their own evidence and later merge approval.
- I3: Reconciled acquisition dd7661d, native mesh b4f89fa and point-cloud97b8f5a. The 392-file stack is not adopted; no exact acquisition-head PR/Actions qualification was returned. Current-profile inspection and validation proceed independently. Revisit candidate adoption only with a separately scoped need and review.
- I13, high, audio/release owner: frame/channel targets and complete protected families must survive freezing and CPU execution. One labelled interval per record bounds the new recipe; whole-WAV families and PCM exposure prevent interval-based leakage. Verify independent decode, train-only fitting, cancellation/restart and retained old results before A11 acceptance.
- I14, medium, mesh/reviewer: canonical_v1 lacks omitted-ancestor family proof; a third-party ASCII float32 reader also has a documented double-rounding mismatch. New validation must declare selected-record scope, preserve exact accepted native values and distinguish internal integrity from generic external-reader compatibility. Verify authored numeric/bit/topology oracles and negative archives before A12 acceptance.
- I4/I6/I8 remain: no Engine certification, no production ASR and no admitted volumes. Existing PostgreSQL migration/backup rules remain binding; this slice does not migrate personal data or add a schema version.


## 2026-10-12 — bounded implementation review dispositions

- I13: Real one-interval CPU execution, exact source frames/channels, complete family evidence, whole-PCM exposure and cancellation/restart pass source/numeric/browser review. A validated-path replacement defect was reproduced with actual training and repaired by consuming one owned verified byte capture. Old image/text results remain exact. Final hosted qualification is pending; broader audio and ASR remain excluded.
- I14: The bounded validator explicitly reports selected-record-only family checks and retains original native coordinates/properties. Valid empty human notes and supplementary Unicode producer values now pass with regression coverage. The omitted-ancestor and generic external ASCII-reader limits remain real limits, not certified capabilities.
- Integration qualification: Mesh CI's saved-selection VM event primitive omission and the old WAV execution-unavailable expectation were independently repaired in tests without runtime fallbacks or weaker assertions. Corrected normal PR checkpoints must pass terminal automatic CI before bounded acceptance. [Evidence](reports/audio-mesh-20261012.md).


Terminal disposition: both corrected feature heads passed their full103-step
lifecycle and focused interface jobs, independently verified. Bounded I13/A11
and I14/A12 gates are qualified in [the combined report](reports/audio-mesh-20261012.md).
The declared ASR, broader 3D and omitted-ancestor/reader limits remain unchanged;
they are outside this accepted increment. No task-local acceptance blocker remains.


## 2026-10-13 — final bounded dispositions

I8 is resolved for admitted uint8 NPY1 volumes by native NumPy/affine, real Data/Pipeline/Runs and migration/restore evidence. M3/M4/M5 and A5/A7/A8 are accepted in [final qualification](reports/final-20261013.md). I1/I2 remain separate owner PRs, not dependencies. I3 candidate stack is not adopted; current bounded subtypes are independently implemented/reviewed. I4 remains an unavailable Engine, with source-based review completed and no certification claim. I5/I6 native Pantograph/ASR are optional integration-owner follow-ups, triggered by separately admitted supported host/runtime evidence. I14 omitted-ancestor/generic-reader limits remain declared contract limits. Rheon producer-v2 remains unsupported; the sequence integration owner must obtain a real completed controls-bound bundle and producer receipt before admitting/qualifying a distinct adapter. No remaining blocker exists for the accepted bounded milestone scope.
