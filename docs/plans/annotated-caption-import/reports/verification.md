# Native caption import qualification

Base: exact published bulk `7c43e9b8fe6ff23d3e75d356361fe616c8365d9c` / tree `b3c57889a9f9e6f685a87431cc8297cb3df5feab`. Separate branch `feature/annotated-caption-import-20261006`. No main, PR4/bulk head or saved-selection worker branch changes. Parent supplied raw-import review/hosted disposition; this report claims the new slice's **local** evidence only. Hosted new-head CI/draft/review belong to parent.

## Actual registered qualification

- `python -m unittest discover -s tests`: **160 tests passed in 48.679 seconds**, including **15 native-import HTTP/SQLite/filesystem tests**. Full stdout/stderr: `/workspace/scratch/tuldok-retry/caption-pixel-transaction-repair-python.log`.
- Four JavaScript gates passed: page-load tracker, workbench controller, raw bulk controller and native caption controller. Log: `caption-pixel-repair-static-and-controller.log` in the same scratch directory.
- **Eight real Chromium suites passed**: workbench, grounded, captions, exact release preview, raw bulk import, native caption import, corner studio and image providers/queued jobs. Existing suites use controlled providers, with no real model/dataset/ONNX download. Logs `caption-pixel-repair-browser-*.log`; includes actual later corner acquisition, native duplicate HTTP409 and rolled-back lazy enrollment/history.
- All `static/*.js` and `tests/*.cjs` passed Node syntax checking; affected Python modules/tests/design fixture script compiled; `git diff --check` passed.

Runtime: Linux x86_64, Python 3.12.14, Node 24.19.0, Pillow 12.3.0, headless Chromium **151.0.7922.173**. Fixtures attach the launched `page/about:blank`; the new fixture logs exact Chrome version/targets, retains HOME and isolates its profile/XDG paths. Two old legacy fixtures default to a missing Brave binary; initial launch returned `ENOENT`. They passed with `BROWSER=/usr/bin/chromium`, without changing gates or fixture source.

## What traversed real owners

HTTP tests consume the committed authored native release, exercise strict metadata/manifest correspondence, finite/unique-field JSON, Unicode/caption bounds, paths, source/hash/snapshot/geometry/family validation, declared review versus local draft state, preparation tampering (including non-ASCII signature), actual PNG/mode/EXIF/damage rejection, duplicate concurrent markers/pixels, conflict with existing related fixed splits, and no reassignment of existing unassigned sources. Real SQL triggers fail caption update and initial history: neither source/target/history nor an image directory survives pre-commit failure. An injected failure **after actual commit** returns 500 but preserves one complete draft/history; read-only marker lookup proves that result without replay. Actual Dataset reopen invalidates old process envelopes while retaining records and lookup evidence.

Imported IDs are new; received PNG bytes become current original source bytes with their actual SHA-256. Unavailable original acquisition SHA and prior native review/provenance remain declared. Caption task, annotation, draft and initial history share the source owner's transaction. Source rights remain unknown. Deleted/unselected image members and an independently produced native release with an unselected text ancestor preserve declared family links without foreign IDs as local parents. Re-exported native origin tokens survive preparation verbatim, within the existing 30-group bound. Separate acquisition sessions prevent legacy session split propagation from editing older unassigned assets.

Drafts were blocked by the actual release endpoint; explicit test-state review allowed actual download/re-export consumed by the unchanged SHA-pinned CLI. Pixels, captions and train/validation/test assignments matched the source release. IDs, ZIP hashes and original acquisition hashes differ; no original-provider or original-archive authenticity is claimed.

## Actual browser workflow and screenshots

The browser builds actual `File`/`DataTransfer` objects from committed local fixture bytes; controlled `webkitRelativePath` properties represent the selected folder tree. This tests file reading/relative binding, not the operating-system picker dialog. Actual HTTP admits rows and actual SQLite triggers/records are inspected. Missing, duplicate-path and damaged files yield three attributed failures and one retained success; a valid subsequent folder fills remaining rows without overwriting duplicates.

Coverage: Stop during source reading, delayed read-only preparation and actual in-flight admission; repeated submission; file-set snapshots; actual storage rollback; lost actual committed response with repeated-control-fenced lookup; unchanged editor/unsaved input/exact selection; four imported drafts with retained splits/origin evidence; duplicate immutability; blocked draft release; explicit per-record editor review; eligible preview; and an **actual browser ZIP download** to a temporary directory. The downloaded ZIP passed the byte-pinned consumer with four records, 2/1/1 splits, no exact pixel duplicates or cross-split group leakage. Fresh-document reload retained five records and reset page-only batch/proof state; it does not establish restart-safe batch recovery.

Local screenshots inspected at desktop **1400 × 807** and narrow **390 × 844** show readable split-qualified row outcomes and explicit draft-review/split consequences. Browser asserts no horizontal overflow. PNGs are untracked runtime evidence, not source fixtures or hosted artifacts:

| Screenshot | Bytes | SHA-256 |
| --- | ---: | --- |
| `caption-import-desktop.png` | 99,058 | `a04d404a4c2e4dde79a762d85dc627b7258523aa1ce1bd95fdd339e8fbc2f19a` |
| `caption-import-narrow.png` | 78,619 | `ce348b7ef04b5dd25c4395c9260e25535c15172977bd56b40ec9513fc607d570` |

Workflow registers the new branch/controller/browser and screenshot paths. Hosted screenshots were not retrieved or inspected for this head. No denied gh inspection call, credential/grant or network setting was retried/changed.

## Limits and disposition

Exactly native image-caption v1 expanded trees are supported. Foreign declarations are unauthenticated; conservative grouping cannot prove semantic independence/rights/quality. Native source annotations require fresh human acceptance. Whole metadata mismatch fails preparation before admission; missing/damaged assets produce per-row partial outcomes. Components/evidence over stated bounds fail closed. Expanded trees cannot recover original ZIP bytes/hash. Process restart expires preparation; known pending markers can be looked up, but batch state has no restart-safe recovery promise. Parent-coordinated exact-head hosted qualification and independent review remain required before integration. No merge or manual CodeRabbit request was performed by this worker.

Independent-review follow-up repaired actual original-head legacy pixel bypass and pending lazy-enrollment transaction after split-conflict rejection. Exact original/repair connection-local versus durable observations and four new regressions are recorded in [admission review repair](duplicate-pixel-review.md). Original a481c3d qualification had 156 tests; current qualification above includes the review regressions and replaces that source acceptance.
