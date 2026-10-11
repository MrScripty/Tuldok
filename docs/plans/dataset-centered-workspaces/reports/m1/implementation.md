# M1 implementation evidence

## Admission and isolation

The 2026-10-11 delegated user instruction admits **M1 start** against
`docs/plans/dataset-centered-workspaces/plan.md` at approved plan commit
`4d8a237e9221d8cc327a547df1abb846460ed1a3`. This feature branch,
`ui/dataset-workspaces-m1-20261011`, starts at that plan commit; its product base
is main `1bb2c3ae9d08432c53ddf9d4bf77fa5f62ad318c`. The UI worker owns this
branch. Parent/integration owner serializes integration with the separate MB
storage worker. No main merge or deployment is authorized.

The precise write set extends M1's named static files with
`workspace-service.js`, `workspace-fixtures.json`, `workspaces-data.js` and
`workspaces-data.css`, plus a Node service contract test. These are the fixture
boundary and opt-in presentation adapter, not new backend owners. `app.py` adds
only explicit static routes. No SQL, schema, migration, real run service, model,
weights or production training changes are included.

PR33 at `581fa5ca471186ed641ec4bf6d134ee1ba807d22` was inspected. Its compact
drawer/retained-control approach informed this design; no commit or file from
that branch was merged or copied. Its failing lifecycle CI is not waived.
The opt-in bridge leaves standalone `/workbench` styling and controllers intact.

## Runnable checkpoint

```sh
python3 -m pip install -r requirements.txt
python3 -u app.py --port 8092 --data /tmp/tuldok-m1-demo
# Open http://127.0.0.1:8092/workspaces
node tests/test_workspace_service.cjs
python3 -m unittest discover -s tests -p 'test_workspace_contracts.py'
```

Data defaults to clearly labelled, authored CC0 fixtures for image, text, audio,
mesh, point cloud, volume and sequence. Choose **Current local catalog** for
existing real import/edit/review/release controls. Its same-origin editor remains
mounted when moving between workspaces. The bridge exposes a small read-only
context snapshot; existing controllers own record selection, drafts, review,
rights, requests and release admission.

Pipeline owns a disposable browser-local graph draft with bounded nodes, typed
connections, parameters, history, save/reload and stale validation. Runs are
explicitly authored scenarios. Completed metrics are not measured, checkpoints
are absent, and JSON exports identify fixture mode. Frozen predictions bind to
the original authored release. Current fixture corrections create only new
unreviewed drafts and do not modify prior runs. Real execution is unavailable
until MB/M2 qualification. This does not qualify A2, production modalities or
Pantograph integration.

## Early evidence

The initial browser walkthrough used real Chromium with the Python application,
Playwright only as an installed local capture driver, and no remote model calls.
JPEG quality 85 captures are in ignored `build/qa/workspaces/early/`:
`data-1440.jpg`, `pipeline-1440.jpg`, `runs-1440.jpg`, `data-390.jpg`.
Viewports: 1440×900 and 390×844. These represent the initial uncommitted shell,
not final acceptance. The images were manually inspected; later captures will
retain exact source revision and viewport metadata. Pipeline/Runs initial
captures revealed scroll position needing correction; viewport capture at the
top is included in the final browser gate.

Passed at this checkpoint: JS syntax, service contracts (valid/invalid modality
fixtures, malformed graph, incompatible ports, cycle, missing inputs,
unavailable ASR, bounded parameters, stale validation, immutable run snapshot,
reopen, cancel/unknown, cross-tab conflict, unsupported store version and failed
storage write), two independent Python fixture checks, and whitespace check.
Comprehensive browser/legacy verification and independent review are in progress.

## Standards and remaining evidence

Adopted Coding-Standards authority remains
`dcc56f26e884ade260770beceba2501d3746200d`. Local application has no `AGENTS.md`
or `.agents/skills`; the fetched standards skill is authoring-only and does not
apply. No Standards Engine MCP is available; no Engine route/certificate is
claimed. Source review routes Core/Router, Implementation, Proportionality,
Verification, Commit, Frontend, Accessibility, Contracts, Concurrency,
Persistence for disposable fixture storage, and Documentation. Plain JS/Python
and no framework build are retained. Source-based review does not claim an
engine-backed compliance result.

Next slice: complete actual browser interaction, responsive/keyboard/error
coverage, screenshot review and independent exact-source review, then report
CI/integration readiness separately. The branch is retained for parent review;
no task-created worktree or external dependency is removed.
