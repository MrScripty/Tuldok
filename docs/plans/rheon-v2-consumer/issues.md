# Issues

| ID | Finding | Owner | Disposition / revisit |
| --- | --- | --- | --- |
| V2-1 | Actual packet exists but original frames and handoff receipt are not materialized locally | Integration / Library transfer owner | Supported helper failed `hosted apps tools/list request failed: network`; retry only the supported route when available. Do not reconstruct frames or relabel authored fixtures. Blocks actual-packet acceptance, not bounded adapter preparation. |
| V2-2 | Earlier final report inferred a missing producer packet from absence in Git | Root | Corrected by PR32 handoff and exact Library metadata; historical PR38–41 left stable. |
| V2-3 | Current Tuldok only admits two files and v1; three-file reader/storage/release/UI paths remain unimplemented | Sequence owner | Complete V1–V5 under this plan; not a PR53 dependency. |
| V2-4 | Historical plans may retain stale or genuinely pending claims beyond the workspace snapshot | Root / plan owners | Keep overall persistent goal open; audit other plan claims individually, without converting model mocks or environment gaps into acceptance. |
