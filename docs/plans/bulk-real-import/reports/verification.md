# Native raw-asset bulk import verification

2026-10-06. Locally qualified; hosted qualification, independent review and separate draft publication pending. UI is provisional; main remains frozen.

Owner chose the plan's recommended native UTF-8 JSONL plus explicitly selected images, with annotation/review afterward. No contradictory repository plan was found. This is a fixed raw-asset contract, not a universal annotated dataset mapping.

## Contract and evidence

Strict text/image rows are bounded at 8 MiB/1,000 physical manifest lines and 3 MiB per consumed UTF-8 row, with existing text/image limits. Unknown/annotation/review/provenance fields and duplicate JSON keys are rejected. Exact flat filenames bind only one selected image; missing/ambiguous/damaged/duplicate assets are row errors. No server paths, URL fetches, archives or second source store.

Existing atomic Dataset/Workbench admission retains originals, normalized pixels/text, hashes, groups/parents/rights and history. All new records are unlabeled drafts. Server-derived row SHA-256 is separate from declared manifest name/physical row/image label; the full manifest is not copied or independently authenticated. Original acquisition/normalization remain owner-derived.

Sequential per-row HTTP admission shows IDs/errors and preserves successful rows. Stop prevents the next admission, including after pending file reads; in-flight work can complete. Repeated controls are fenced. Lost/malformed/unexpected responses pause without replay; read-only saved-marker lookup verifies a matching row proof before crediting creation. Missing lookup does not prove stopped work and dismissal implies no rollback. A real injected SQL read failure after image admission commits returns HTTP 500 with a valid saved record, proving why server errors remain uncertain. Editor edits and exact selection survive refresh.

Final full Python suite: **145 tests in 40.019 seconds, OK**. Includes nine actual HTTP/SQLite/filesystem bulk tests, four admission foundation cases, two queued-API regressions and five legacy-job restart/resume cases. Bulk coverage includes real text/image originals and EXIF orientation, reopen/provenance, partial/malformed/unknown/duplicate rows and fields, missing/damaged/mismatched files, bounds, reviewed-record preservation, storage rollback, post-commit read uncertainty and read-only result lookup. Faults are injected at SQLite metadata/read boundaries; admission/normalization/storage/HTTP remain real.

Three JS gates passed: page-load tracker, existing workbench controller and new bulk controller. New cases cover sequential/repeated scheduling, cancel during manifest/image reads and after pending acknowledgement, selected-file ambiguity, uncertain server/network responses, wrong proof, matching lookup without replay, changed controls and manifest bounds. Controller checks are separate from rendering evidence.

All seven registered real Chromium suites passed: workbench, grounded, captions, exact-selection release preview, bulk import, legacy corner studio and image generation. Bulk uses actual File/DataTransfer objects, local manifest/original image bytes and actual app HTTP/storage. Response withholding/loss happens after real requests/commits. It checks three successes plus five invalid rows; unchanged records on repeated manifest; selection/unsaved-editor preservation; Stop before admission and after in-flight success; actual SQLite rollback without orphan files; matching lookup; fresh-document reload; desktop and 390px overflow. Existing preview/export formats/splits/stale lineage/delayed/repeated controls/download gates remain green. No existing deadline/assertion is removed or relaxed.

All JS syntax, Python compilation and diff checks passed. No new dependency, credential/grant/network setting, model or ONNX download.

Runtime: Linux x86_64, Python 3.12.14, Node 24.19.0, Pillow 12.3.0 and actual Chrome/151.0.7922.173 at `/usr/bin/chromium`; native headless `--no-sandbox --disable-gpu`, isolated temporary data/profile/XDG directories and controlled local providers. Browser target/version diagnostics are retained. Desktop screenshot: 1400×807; narrow: 390×844. Both visually inspected for panel/outcomes/controls/wrapping. This does not qualify live models, non-Linux platforms or larger corpora.

## Retained evidence and integration

Task logs at `/workspace/scratch/tuldok-retry/`: `bulk-feature-qualified-python.log` (145), `bulk-feature-api-qualified.log` (9 focused), `bulk-feature-final-page-load.log`, `bulk-feature-final-workbench-controller.log`, `bulk-feature-final-controller.log`, seven `bulk-feature-final-browser-*.log`, `bulk-feature-browser-qualified-final.log` (final fixture/version check), `bulk-feature-final-full-gates.log`. Desktop/narrow PNGs remain local in this report directory and are registered for future CI artifact upload; they are not Git source files.

Queued repair remains its own local PR4 commit 801d598. Bulk foundation is a16bba4; native bulk is its subsequent separate feature commit. This feature does not edit the PR4 worktree, main or PR1–3. Shared paths: app route/static composition, Workbench import/enrollment context, shared original-image read helper and static shell. Selection storage/query/filter/analysis, release validation and saved-selections implementation are unchanged. Parent coordinates integration/review/UI adoption.

Precise retained errors: `gh pr view 4 --json headRefOid,headRefName,baseRefName,isDraft,url --jq .` returned HTTP 401 `Bad credentials` at `https://api.github.com/graphql`; `gh api repos/MrScripty/Tuldok/actions/runs/37531676070/artifacts ...` returned HTTP 401 at that REST artifact metadata endpoint. Only inspection reads failed. Earlier authenticated push at a3f3cbe succeeded; no post-error Git push or alternative publication route was attempted. Publication is held locally by instruction, not proven denied through every route. No denied call or credential/settings repair is retried. Previous hosted CI at a3f3cbe does not qualify these newer local commits; hosted/review results remain pending.
