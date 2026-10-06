# Import native frozen caption releases

Status: Locally verified; parent-coordinated hosted qualification/review pending. Base: bulk-import `7c43e9b8fe6ff23d3e75d356361fe616c8365d9c`, tree `b3c57889a9f9e6f685a87431cc8297cb3df5feab`. Separate local branch `feature/annotated-caption-import-20261006`; published PR4/bulk heads remain stable. Parent reported independent raw-import ACK and both exact-head hosted checks passing, and authorized this next bounded slice on 2026-10-06.

## Objective, authority and scope

Import an explicitly selected, expanded **Tuldok `image_caption_v1` frozen release** into the existing collection, retain actual image/caption/protected-family/split relationships, inspect imported captions and explicitly accept them before re-export. Support exactly the native manifest plus `train/val/test/metadata.jsonl` and referenced PNGs. This is already produced and consumed by the repository; no universal schema, arbitrary imagefolder variant, external corpus/model download, archive extraction or task-coordinate conversion is introduced. Folder selection includes the relative paths and is provisional UI.

The source contract is `dataset_releases.py::_create_captions`, its contract tests, and the unchanged chapter-26 CLI at SHA-256 `6a4394308a4cc69b4ca965aca7f8459d7711ac9d51ce70492562c6ec6d806f94`. Existing research synthesis and [shared-owner decision](../../decisions/dataset-workbench.md) require independent source/target identity, review distinct from verification, and protected connected families. The original research books are unavailable locally; no additional source claim depends on them.

Binding owner decisions: raw import review cleared according to parent; next slice permitted if concrete existing format has no unresolved product choice; all imported targets remain drafts; main/published heads/saved-selection worker branches remain unchanged; parent owns draft metadata/CI/manual review. Numeric generation contracts are untouched. Standards remain Coding-Standards `dcc56f26e884ade260770beceba2501d3746200d` (core/router, planning/discovery, implementation, persistence/contracts, security, oracles/GUI, commit).

Split disposition follows the selected frozen-release contract: **preserve exported assignments as active source splits**, with `val` mapped to `validation`. Treating them only as contextual notes would silently change evaluation partitions on re-export. This consequence was stated before implementation; no product answer is required to preserve the existing contract. Foreign review/rights/provenance remain declarations; they cannot establish present human acceptance or image-provider identity.

## Mapping and identity

| Input | Canonical/local meaning |
| --- | --- |
| `file_name` | Exact `<32-hex source id>.png` beside split metadata; directory/URL/absolute/backslash references rejected |
| `text` | Validate with existing `image_caption` validator; caption preserved according to that owner's trim/4,000-code-point contract; never a generation prompt |
| `group` | Must match manifest `export_group` and complete protected snapshot; keep conservative family links |
| PNG bytes | Existing Dataset original, normalization and hash owners; normalized RGB PNG/orientation/geometry/hash/pixel hash must agree with manifest |
| source `id`, revisions, hashes, provenance, review, rights, parents | Bounded **declared origin evidence** under acquisition, not local ID/revision/verifier/rights/parent authority |
| imported ID/revisions/source SHA/pixel hash | Newly allocated/derived by current owners; imported source SHA hashes received PNG, not unavailable original acquisition bytes |
| split folder | Active `train` / `validation` / `test`, preserving whole-family assignment |
| imported task/review | `image_caption` + validated target + `draft` in the same admission transaction/initial history |

Full component snapshots include unselected and deleted members. Each new row gets the same deduplicated protected tokens for every declared snapshot member ID, parent ID, group and retained legacy book/session link. Tokens are `caption-origin:` plus SHA-256 of the typed link; they exclude archive/manifest hashes so overlapping frozen families remain conservatively connected across imports. Existing `caption-origin:` tokens survive subsequent native round-trips verbatim rather than being hashed again. They are declared grouping evidence, not authenticated identity. Existing pixel identity remains a separately derived graph link. Foreign parent IDs are retained in origin evidence and never installed as dangling local parents. Cap the resulting groups at the existing 30-group limit; reject larger components rather than truncate them. Native cross-split components, conflicting retained splits, unknown lineage, missing snapshots or incomplete/different selected snapshots fail before admission. Dataset/source identities cannot prove semantic independence, rights or authorship.

Duplicate source IDs in the package, duplicate assets/pixels, conflicting metadata/manifest captions/groups/splits/hash claims and ambiguous paths are rejected. Existing local source-ID collisions or actual byte/pixel duplicates conflict without editing existing targets/provenance/review. Imports of the same native release into a fresh collection allocate new IDs and preserve pixels, captions, family membership and partitions; ZIP/release hashes, source acquisition hashes and IDs are not promised identical.

## Acquisition composition, bounds and failures

`caption_import.py` validates the complete metadata/manifest once in a read-only preparation request, reusing the existing connected-component graph and target validators. It returns bounded per-row integrity envelopes signed with an ephemeral process key; this is not authentication, a permission grant, a job store or a new credential. No prepared corpus/registry is persisted. The signed row freezes the validated source declaration without sending the full manifest beside every image or trusting browser-only shape checks. Restart invalidates envelopes; choose the files again. A row checks actual bytes/pixels before mutation, then duplicates and current related split state under the source lock. Separate acquisition sessions keep legacy split propagation from updating older unassigned assets.

Bounds: at most 1,000 combined physical JSONL lines, 8 MiB combined manifest/metadata UTF-8, 256 KiB per signed row context and 16 MiB combined envelope text, current 25 MiB/40-megapixel image bounds, existing 30 protected groups and caption bounds. Strict UTF-8/finite JSON/duplicate-key rejection applies to source files. Every required file/path must be unique; selected extra files are never substituted. No server filesystem/URL lookup or ZIP extraction.

Actual bytes and hashes of consumed manifest/metadata/row/PNG are acquisition observations. Original source identity/history is explicitly declared and bounded. The expanded tree does not expose the original ZIP bytes: no computed package fingerprint claims that archive's SHA-256 or producer authentication.

Workbench owns validated target/draft/history and receives only trusted internal annotation/split/acquisition-session arguments; Dataset's existing enrollment hook commits them with source files/metadata. Pre-commit metadata/history failures roll back the image and remove its directory. A post-commit receipt failure can leave a fully admitted row: classify it uncertain and use the existing read-only request-marker lookup without automatic replay. Marker namespace is shared with raw import to prevent ambiguous duplicate receipts. Stop fences future scheduling and never claims in-flight rollback. Controls/file sets are snapshotted; repeated/delayed controls cannot schedule two loops. Batch/proof state is page memory only, with no restart-safe batch recovery claim. Collection refresh never changes the current editor or exact selection.

## Composed-design review: applicable

1. Caption importer owns this one external decoder/proof; Dataset owns originals/normalized assets/splits; Workbench owns targets/history/review/provenance; browser owns selected files and scheduling. No second store/normalizer/source graph.
2. New local source ID and original/hash remain stable. Review/revisions are separately mutable. Imported declarations are evidence; source split constrains release allocation.
3. Caller knows relative file references and row outcomes, not SQL/storage paths. Target checks and normalization stay with their owners.
4. Changing another format is outside this slice. Caption/graph changes propagate through existing validators rather than a duplicate implementation.
5. Reuse current lock/SQLite/file-cleanup enrollment. User file reads and HTTP waits never hold the source lock.
6. Real HTTP/SQLite/Pillow tests prove admission/rollback/duplicates/restart; unchanged consumer proves projection; browser proves files/controls/editor/review/export/download.
7. Removing this decoder/controller leaves raw/single import, caption authoring and frozen exports usable. No persistent queue/idempotency/schema migration is retained.
8. Necessary extra state is one bounded process integrity key plus current page loop/pending receipt. Native manifest/snapshot validation is justified by the chosen source contract.

## Milestones, write sets and acceptance

M0 design/local-fixture preparation: passed. Write set only this plan directory. Generated authored native release includes four exported rows, an unselected bridge, a deleted ancestor and EXIF-normalized original/source byte distinction. Existing-owner rehearsal preserved pixels/captions/splits; draft export was blocked; explicit fixture review then re-export passed the pinned consumer. Seven malformed probes demonstrate admission gaps in the training CLI. This proves feasibility, not an importer/UI/atomic target-admission contract.

M1 bounded importer + provisional UI: locally verified. Exact intended write set: `caption_import.py`, `workbench.py` (trusted internal admission only), `app.py` (composition/routes), `static/caption_import.js`, `static/workbench.html`, `static/workbench.css`, `tests/test_caption_import.py`, `tests/test_caption_import_controller.cjs`, `tests/browser_caption_import.cjs`, `.github/workflows/tests.yml`, `README.md`, and this plan directory. Do not write saved-selection/metadata worker modules, feature branches, release allocation/preview code, provider APIs or schema tables.

| Claim | Acceptance evidence | Current status |
| --- | --- | --- |
| C1 | Native metadata/snapshots/labels/asset references fail closed; no review grant from declarations | actual HTTP + owned validators + malformed native fixtures | passed locally |
| C2 | Original/normalized bytes, actual source hashes, declared origin, family protection and active splits survive restart | actual SQLite/filesystem/HTTP | passed locally: actual admission/reopen/hash/split evidence |
| C3 | Source + caption + draft + initial history atomic; duplicates unchanged; concurrent markers/pixels fenced; uncertainty reconciled | real SQL fault injection and HTTP concurrency | passed locally |
| C4 | Drafts cannot export; explicit acceptance gives pinned-consumer-compatible round-trip without ID/hash impersonation | actual release/download + unchanged consumer | passed locally: actual HTTP and browser ZIP consumption |
| C5 | Folder/file binding, mixed outcomes, stop/read/in-flight/repeated controls, response loss/reload, editor/selection fencing, narrow layout | actual Chromium/HTTP + controller fixtures + inspected screenshots | passed locally |
| C6 | Complete registered tests/syntax/compile and exact new-head hosted CI/review, separate draft, stable existing heads | local gates + parent GitHub coordination | local gates passed; hosted/draft/review pending with parent |

Current phase: M1 locally verified, awaiting M2 hosted qualification/review. Exactly one next slice: publish only the new verified branch and hand exact branch/head/tree and evidence to parent for hosted qualification and review. Keep denied gh inspection reads paused. No merge/public-main change.

Re-plan for a requested non-native/other-task format, component evidence over existing bounds, actual consumer-contract change, unsupported coordinates, source-identity ambiguity requiring authenticated namespace, a stack-base change or material shared-owner review findings. No unresolved product choice currently blocks this selected native contract.

[Ledger](execution-ledger.md) · [Issues](issues.md) · [Fixture preparation](reports/prepare_fixtures.py) · [Verification](reports/verification.md)
