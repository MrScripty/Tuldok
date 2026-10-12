# Audio runs increment — implementation evidence

Admission: `audio-mesh-admission-20261012.md`, canonical plan blob
`d7c0b894219da0d229eee960b9a11616805276a5`, operation `continue`.
Branch `feature/workspace-audio-runs-20261012` starts at d4a5b196 and includes
root's narrow HTML selector commit 2faae824. Main and older worktrees remain
unchanged. No schema migration or new runtime dependency is introduced.

First runnable checkpoint implements real authored WAV admission/review,
classification preview/freeze, checked complete-family reader and editable
audio graph. A missing trainer produces `unavailable` and admits no run.

Evidence before source checkpoint:

- Five real PostgreSQL audio release/graph tests passed in 3.441 seconds.
- All fourteen existing text reader/trainer/run cases passed in 13.804 seconds
  after shared-family extraction, including a real CPU run and reopen.
- All ten existing audio parser/custody/backup cases passed in 2.969 seconds
  after the custody-only lazy import.
- Actual Chromium release/graph walkthrough passed four checks: keyboard empty
  Runs navigation, authored source admission, UI freeze/download, edited graph
  and honest unavailable validation. Desktop 1440 and narrow 390 captures have
  no document horizontal overflow. This checkpoint uses fixture setup through
  ordinary HTTP import/review followed by actual Data/Pipeline UI actions.

The first candidate captures and receipt are in
`build/qa/workspace-audio-run/run-b9U4dz`; they truthfully record a dirty working
tree. Clean source-bound captures follow the source commit. Root/independent
review and final CPU, cancellation/restart, correction/exposure, offline and
hosted gates remain pending; this is not final audio execution acceptance.

Launch from the feature worktree with the configured local PostgreSQL service:

```sh
TULDOK_TRAINING_PYTHON=/path/to/optional-cpu-python python app.py --data /path/to/catalog --port 8099
```

Set `TULDOK_DATABASE_URL` using the existing local PostgreSQL runbook. Existing
catalog migration/backup requirements remain unchanged. No personal catalog was
opened. The local browser command is `node tests/browser_workspace_audio_run.cjs`
with app Python on PATH and the same test-service environment.
