# Saved-selection intent verification

Source before: PR5 `991a22beb5a69272571dd3731cfb8392154725f7`, verified published
head, unchanged while the independent reviewer runs. Repair branch:
`fix/saved-selection-intent-20261006`. Linux x86_64, Python 3.12.14, Node 24.19.0,
Pillow 12.3.0, Chromium 151.0.7922.173; controlled local providers and temporary data.

## Reproduction against unchanged production source

`TULDOK_SOURCE_ROOT=/workspace/Tuldok-saved-selections node
tests/test_saved_selection_intent.cjs` loads the exact original production scripts,
without editing that worktree. Five cases fail: delayed initial list overriding
manual membership; initial URL open overriding explicit empty clear; earlier editor
completion replacing a later fixed revision; a later editor save adopting an
already-stale selected pair; and empty clear failing to cancel an active open.
The ordinary editor-save positive control passes. Log:
`/tmp/tuldok-intent-controller-before.log`.

`TULDOK_SOURCE_ROOT=/workspace/Tuldok-saved-selections node
tests/browser_saved_selection_intent.cjs` launches the original real server/static
source with real Chromium and actual SQLite. Both independent review cases fail.
For the pending-save case, the actual endpoint returns:

    storedFixed: false, currentPair: true, actualSelected: true

These are release eligibility results, not merely displayed revision differences.
The source override is test-only; it chooses the existing local checkout and makes
no credential, provider, dataset-download or network-setting changes. Original
source and screenshots remain unchanged. Log: `/tmp/tuldok-intent-browser-before.log`.

## Repair evidence

- All six deterministic cases pass against repaired production scripts. Log:
  `/tmp/tuldok-intent-controller-after.log`. Positive control preserves ordinary
  save behavior; explicit Select page can adopt current revisions after a fixed open.
- Real Chromium passes both reported workflows. The successful annotation still
  persists and becomes visible in the editor. Stored saved membership is unchanged;
  the actual selected request keeps its old pair and receives:

      storedFixed: false, currentPair: true, actualSelected: false

  The actual UI preview displays a revision conflict and leaves Freeze disabled.
  Explicitly selecting current page records then enables eligible preview.
  [Blocked preview screenshot](intent-blocked.png) was captured and visually inspected.
  No runtime exceptions. Log: `/tmp/tuldok-intent-browser_saved_selection_intent.cjs.log`.
- Full Python suite: **141 tests passed in 33.586s**. No Python production or
  persistence module changes. Log: `/tmp/tuldok-intent-python.log`.
- Existing workbench and saved-set controllers and CDP fresh-document barrier pass.
  Production JavaScript syntax and branch `git diff --check` pass.
- All **eight real Chromium suites** pass: workbench, grounded candidates, captions,
  release preview, saved selections, new saved-selection intent, legacy corner studio
  and controlled image generation. Each owns its temporary SQLite/provider/browser
  resources; three independent suites ran concurrently. Logs:
  `/tmp/tuldok-intent-*.cjs.log`. Existing saved/preview narrow-layout assertions pass.

Existing-suite generated screenshots were preserved under
`/tmp/tuldok-intent-existing-suite-screenshots`; inherited committed screenshot bytes
were restored only in this task's clean-at-start repair worktree, keeping the diff
scoped. The original PR5 worktree and separate metadata-filter changes were untouched.

## Delivery and limits

Parent review/integration and final UI choice remain pending. This is a scoped
successor draft against unchanged PR5, not a merge or PR5 head replacement.
The metadata-filter worktree remains paused; its eight focused Python contracts and
controller transport checks passed before the repair steering. It is not published
as part of this fix and has no new schema or permission taxonomy.

Hosted qualification must identify the exact candidate via authorized run/job
metadata and each registered step. Earlier redirected hosted-log transfers returned
Forbidden; no log transfer retries, alternate route, credential repair or network
setting changes are made. Local logs and inspected local screenshots provide detailed
workflow evidence. No external model/dataset, ONNX download or manual CodeRabbit request.
