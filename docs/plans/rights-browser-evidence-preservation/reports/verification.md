# Rights-note browser output preservation

Qualified source `4e7ec2d08613bf74efa23ecb18c44c4b14a595b0`, tree `c961259776962788a6dece02abc88c6ffaaf70fa`. The final evidence commit changes reports only. Local branch `fix/rights-browser-evidence-local-20261007`, isolated worktree `/workspace/Tuldok-rights-evidence-local`, based on immutable published PR16 candidate `78b5b2f22bcdc1b5c36481b29f4a60d8a017fb42`, tree `24203ce68c0868905769503d123dd729cf5c2f65`.

## Narrow repair

The existing rights-note browser workflow now writes its actual desktop/narrow screenshots to a fresh `test-results/rights-note/run-<unique>/` directory per invocation. It logs that destination and retains the files after temporary browser/dataset cleanup. `/test-results/rights-note/` is ignored locally; CI's existing artifact collection additionally includes `test-results/rights-note/**`, covering the fresh PNGs and rerun receipts. Existing artifact registrations remain unchanged.

The inherited browser assertions, interactions, server behavior and screenshot content are unchanged. Only the output path and destination log differ. All production files, previous qualified source hashes and four owner lineages are unchanged. There are no new dependencies, external models/datasets, ONNX downloads, credential/network changes or global Git changes.

## Regression and qualification

`tests/test_rights_note_artifacts.cjs` snapshots every tracked report file and executes the real rights-note browser workflow twice. After each successful run it checks that all tracked bytes remain identical to its starting snapshot, requires one new output directory with actual desktop/narrow PNGs, checks ignored status, and verifies the second run preserves the first run's captures. Its receipt records source identity, actual script hashes, tracked-file count, preservation results and screenshot hashes. The oracle is the pre-invocation filesystem bytes; the browser and regression do not share an output helper.

The predecessor reproduction used a separate local shared clone at exact `78b5b2f`, never a retained worktree. Its functional browser workflow passed, then the new preservation assertion failed because exactly the two tracked historical rights PNGs changed. The raw failure and before/overwritten hashes are retained under `prior-traces/`; the disposable copy's original bytes were restored. The focused repaired regression passed both real browser runs and preserved all 420 tracked report files, retaining four PNGs. Its precommit working-source receipt is retained separately under `focused-browser/`.

Full qualification passed **40 gates** on the exact committed source: all 39 existing commands plus the new preservation gate. This includes **235 Python tests**, eight JavaScript syntax commands, twelve controller/helper commands, eighteen existing real Chromium workflows and two additional rights-note browser reruns, for **20 real Chromium invocations** in the qualification run. Dependency setup and original gate ordering are retained. The local Chromium 151 executable is `/usr/bin/chromium`; the existing private CPU consumer environment was reused without installing anything. Both independent instruction and combined workflows pass their unchanged pinned offline consumers and actual archive downloads.

`gates/source.json`, numbered raw logs and `gates/results.json` identify the source and each actual exit. `fresh-rights-output/` retains the standalone qualification run's two PNGs, the regression's four PNGs, and its committed-source receipt. The receipt proves 420 tracked files unchanged after each rerun and earlier captures retained. All fresh paths match the new CI collection prefix.

## Preservation and limits

All **420 historical report files** are byte-identical to the published candidate. This includes all **340 manifest entries across 343 files** in the earlier combined, owner-fix and projection-warning report directories, with their manifests unchanged. `source-and-preservation.json` records every historical path/hash, source hashes, owner pins and protected existing local heads.

Other inherited browser workflows still regenerate component reports in their existing destinations; changing those destinations is outside this narrow repair. Their 58 regenerated PNG/JSON/ZIP artifacts are retained separately under `full-suite/`, then original tracked paths were restored. The rerun receipt compares the bytes immediately before its own invocations; the final audit independently checks every historical file against the immutable base. Thus the new regression directly proves rights-note rerun preservation, while the final artifact audit proves complete retained history after full qualification. Raw logs preserve platform diagnostics and significant/trailing whitespace; authored source/docs pass whitespace checks.

Independent review of the frozen evidence successor is recorded with exact head/tree in the executor handoff. The branch/worktree remains protected for the parent to inspect and decide publication. No remote action, public push, PR mutation, merge, manual thread resolution or CodeRabbit request occurs. Hosted CI has not run for this local successor; CI collection is verified from the registered path and retained actual outputs.
