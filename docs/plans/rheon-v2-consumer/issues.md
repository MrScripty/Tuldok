# Issues

| ID | Finding | Owner | Disposition / revisit |
| --- | --- | --- | --- |
| V2-1 | Actual packet exists but original frames and handoff receipt are not materialized locally | Integration / Library transfer owner | Supported helper failed `hosted apps tools/list request failed: network`; retry only the supported route when available. Do not reconstruct frames or relabel authored fixtures. Blocks actual-packet acceptance, not bounded adapter preparation. |
| V2-2 | Earlier final report inferred a missing producer packet from absence in Git | Root | Corrected by PR32 handoff and exact Library metadata; historical PR38–41 left stable. |
| V2-3 | Three-file reader/storage/release/UI paths implemented with labelled fixtures; actual packet remains unqualified | Sequence owner | Implementation addressed; V2/V4/V5 actual-packet gates remain pending. Not a PR53 dependency. |
| V2-4 | Historical plans may retain stale or genuinely pending claims beyond the workspace snapshot | Root / plan owners | Keep overall persistent goal open; audit other plan claims individually, without converting model mocks or environment gaps into acceptance. |

| V2-5 | No legitimate real Pumas runtime/model endpoint found in current environment | Integration / runtime owner | A8 positive-path gate requires available compatible text/image capability; no model downloads or mocked acceptance. See runtime inventory. |
