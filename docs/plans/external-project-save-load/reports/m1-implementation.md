# M1 implementation evidence

This dated record concerns the external text-project vertical. The [plan](../plan.md)
alone owns current status, next slice and acceptance. Later scientific families,
execution, independent Save As and extraction need M2–M5 gates.

## Source and environment

- Tuldok main: [`133d53c0e2985a6559ba9cebd7d4a9f530051f06`](https://github.com/MrScripty/Tuldok/tree/133d53c0e2985a6559ba9cebd7d4a9f530051f06).
- Local reviewed plan: `2c9c9b098c9f1c4c2557c58818574ebdbc1e7d41`.
- Standards: [`5bce3110fc64d61ff8b4f79468184bd6295855d5`](https://github.com/MrScripty/Coding-Standards/tree/5bce3110fc64d61ff8b4f79468184bd6295855d5).
  Core, implementation, verification/oracles/GUI/platforms, persistence,
  contracts/evolution, ownership, concurrency, security, diagnostics and commit
  guidance applied; the [baseline report](baseline-and-standards.md) gives the
  original routing/source context. The Standards Engine authoring skill is
  explicitly inapplicable to ordinary application edits; no application Engine
  connection is available and no automated standards certification is claimed.
- Disposable PostgreSQL 17.11 over a private Unix socket; Python 3.12.14;
  Node 24.19.0; Chromium 151.0.7922.173; Linux overlayfs. Source and cold roles
  are non-superuser fixture roles, and the cold role is denied source DB access.
  No user database, project or lab is an input.

## Deciding evidence

| Boundary | Performed evidence | Practical limit |
| --- | --- | --- |
| Filesystem publication | `tests/test_project_store.py`: real files/processes, contention, process kills, canonical closure, no-clobber New, fsync faults, malformed/future/path cases | Supports named local Linux filesystem; no destructive power-loss or network/Windows promise |
| Canonical before SQL acknowledgement | `tests/test_project_text.py`: 18 real PostgreSQL tests passed, including a deferrable COMMIT failure after file publication and fresh reconstruction | Text/annotation family only |
| Current local authority | Text tests include scoped agent drafts/read, human review refusal, inspect-only mutation refusal and revocation ordering | No imported current credentials, grants or resumable authority |
| Workspace recovery/retry/pages | `tests/test_project_workspace.py`: nine real-PG tests, then two targeted persistent-fsync tests after barrier repair passed | Later worker/run lifecycle remains fenced |
| Legacy affected behavior | `test_metadata_transactions.py` 15 passed; three selected Workbench tests passed | No full-suite or unrelated D1 requalification claimed |
| HTTP, real clients and browser | Changed-subject cold reconstruction, stale requests, actual SQL COMMIT fault/recovery, real SDK/CLI/MCP and Chromium workflow passed; exact receipts in [M1 QA](m1-qa.json) | Text scope; original failed MCP initialization retained separately |

The final HTTP campaign selected four nonzero methods. Three passed immediately;
the actual-adapter method failed MCP initialization at its 20-second deadline.
An isolated production probe measured 20.431 seconds, with CPU work dominating.
`main()` already performed full registry validation in bootstrap, and `serve()`
repeated it before reading initialization. After independent consequence review,
only the redundant `serve()` validation was removed. Bootstrap admission and
per-call input/output checks remain. A focused main-order test passed and proves
bootstrap failure prevents serving. Only the failed real-adapter method reran:
1 passed, no skips, stable source, 103.987 seconds overall. Actual MCP initialized
in 10.955 seconds under the unchanged 20-second initialization deadline.

That real adapter method used an actual ProjectWorkspace HTTP server, owner SDK
New, ordinary agent SDK drafts/read and owner-review denial, private-config CLI
Save/Close/Open subprocesses, and the official MCP SDK against production stdio
and actual HTTP. It verified retained historical notes and revocation 401 without
canonical effects. It did not substitute the controlled HTTP client fixtures.
The focused client suite separately passed 16 tests without skips, including
maximum Unicode sizing, exact pins, page/receipt/recovery contracts and controlled
consumer faults. The affected preexisting Agent API suite passed 17 tests.

The final changed Chromium subject passed with matching start/end file hashes:
keyboard New/import, retained corpus note followed by human-reviewed classification,
Save/Close, real local Git commit and clone, fresh process/control catalog with
the cold role denied source DB access, exact identity/text/history of three
revisions, older-note UI pagination, no-op Save byte identity and inert script
sentinel. Runtime and HTTP error lists were empty; desktop/mobile screenshots
had no horizontal overflow. The later MCP-only startup edit does not affect the
browser's owners and did not justify another identical browser campaign.

The three legacy Workbench methods were
`test_normalized_unicode_revisions_and_reopen`,
`test_intent_recipe_labels_and_template_lineage`, and
`test_http_static_export_and_errors` (3 passed, 2.232 seconds).

Commands use the qualified fixture environment, then standard nonzero unittest
discovery/explicit method selection and `node tests/browser_project_files.cjs`.
The fixture environment is `/workspace/scratch/tuldok-save-load-qa/env.sh`;
raw logs and browser receipts are retained in that task-owned scratch directory.
Tests clean only their owned schemas/processes/profiles. PostgreSQL remains owned
by the task while dependent milestone checks need it.

## Review findings and repairs

The independent source reviewer requested seven concrete fixes: recoverable
unknown publication/committed outcome delivery; bounded list/history responses;
receipt-correlated historical revision; New creation without selection; stale
lifecycle replay; legacy capability truth; and bootstrap against the real project
server. They were closed together at the affected owners. Text authority
correction was independently re-reviewed at SHA256
`adf90ee6e53b8dc1e8b68287269e907a4da1112704489db4eee1efddf0b65e5b`
and cleared. Final targeted source re-review cleared every collected finding;
the reviewer performed no runtime tests. The reviewed product files include
workspace `2b0dbace8e2840e4f60997985ac7f52618c0fe15ed32cf6ca548c3832e9b8c54`,
text `adf90ee6e53b8dc1e8b68287269e907a4da1112704489db4eee1efddf0b65e5b`
and UI `5bb198e00191c1b39b74998b0c54c14129aa7470f8dba1bd71819cab81c2874b`.
The app, registry, SDK, CLI, contract and authority decision were also inspected
on their frozen final subjects. Final affected transport checks remain distinct
from that source-review verdict. The additional MCP startup change was independently
cleared at final SHA256
`a37cf211ded719242499a90772ccf377c2ba52a895621c1ed618c37ed065deeb`.
No source-review finding remains. The lead accepted the M1 text milestone after
the named real checks; final A1–A9 feature acceptance remains governed by the plan.

Failed checks are retained with their causes: missing exact contract headers,
incorrect static routes, a misplaced HTTP guard, test quoting/fixture name errors,
and a browser observation racing the acknowledged edit. The team corrected the
specific defect and selected the affected rerun; it did not repeat unchanged
campaigns or use test-count targets.
