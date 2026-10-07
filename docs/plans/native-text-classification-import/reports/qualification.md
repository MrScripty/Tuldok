# Native classification import qualification

Native source/implementation base: `3eb64667997701f98f27befa70669f9ae8405265`, tree `84254d196c5a2e20f8884c290c923849e0c4dbca`. Independent worktree/branch: `feature/labeled-text-import-20261007`. Native canonical_v1 fixture uses actual exporter output with decomposed Unicode/CRLF original, demonstrating omitted upstream original and distinct measured new input hash. Producer schema/record/asset bindings are documented in ../plan.md.

All 27 local workflow gates passed: 190 Python tests, five JavaScript syntax checks, seven controller/page-load gates and fourteen real Chromium suites. No model/dataset download, dependency/network configuration change or external provider was used. The new Python tests traverse HTTP/SQLite/native ZIP production and inspect restart, per-record transaction rollback, connection closed AFTER commit, read-only reconciliation, malformed/unsupported rows with later valid admission, missing assets/metadata, exact row/asset binding, duplicates, foreign parent links, preparation expiry and explicit review -> saved selection -> preview -> frozen ZIP contents.

The new controller test observes source-read, preparation, in-flight admission and collection-refresh barriers; repeated submit/check, source snapshot, partial 400/409 outcomes, uncertain 500/network outcomes and missing/successful receipt lookup without replay. Real Chromium imports actual generated ZIP bytes, holds actual admitted responses and collection refresh, preserves dirty editor/exact selection across changed filters, verifies repeated archive rejection without updates, stops before later rows, reconciles an actually committed lost response, reviews via the editor, saves/reopens exact membership, downloads/inspects the frozen ZIP, and qualifies reload plus Back/Forward navigation and 390px layout.

Initial browser-development runs exposed test synchronization/selector/history assumptions: completion of editor state can precede collection rendering, and Back returns to the earlier no-selection URL before Forward restores the set. Final checks wait for rendered current revisions and assert those existing navigation semantics. These observations did not change the application editor, saved-set or release owners. Browser confirmation dialogs are accepted explicitly when ending the dirty-editor fixture. Unrelated regenerated baseline screenshots were restored rather than added to the feature.

While testing, the parent merged PR13: development advanced to `b5c4247a7dffba744f4295e6b8650e1f6ccece16`, while PR13 head remained `c765587a229e8daa78963dc21bd87e4c2a9b9dcf`. This branch remains based on the instructed 3eb6466. Its original caption gate passed locally without importing the PR13 patch; final draft CI must qualify the current target combination. Main remains `2fc4a46f12d73a0fa467d5482f68edb83d6df6af`. No merge or CodeRabbit request was performed by this worker.

## Tested feature source SHA-256

- `native_text_import.py`: `3fedb1f80b7d97d431f3d23397adc865443ea14cd25e761fa3d727592f7c9db3`
- `static/native_text_import.js`: `96b8798779eb6c9a5dadf0523d13b9eeebe2f466dcb15dfb59b5364f22a2c62d`
- `tests/test_native_text_import.py`: `0b4edf5d05759183fe91caabe8d79dc44c83e312f07cf066a87fc6fe44d697bd`
- `tests/test_native_text_import_controller.cjs`: `98e550c365133b1954537114cab78dcec4ba03ba395e622c591f13f4ba8e2742`
- `tests/browser_native_text_import.cjs`: `13f3058dc49be20b7570511a6a716c50e898403a8b25e5b95b82847e52e52f29`

## Scope limits

Only native canonical_v1 version-1 stored ZIP entries and text_classification rows are supported. Archive/manifest/metadata/row/asset/input identities are measured from consumed bytes; identity is not source authenticity. Upstream record/hash/rights/review/provenance are declared history with unavailable original; none becomes local approval or the new input hash. Original reconstruction, split restoration, entities/instruction/preferences, local foreign-parent restoration and arbitrary corpus adapters remain unsupported. Foreign relationships become stable protected-group links, with overflow rejected rather than truncated. Preparation is process-local; committed records/receipts persist. Provider quality, rights permission and semantic source independence require their existing human decisions.
