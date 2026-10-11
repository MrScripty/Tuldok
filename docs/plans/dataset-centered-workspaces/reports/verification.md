# Planning verification

Scope: `README.md` (one discoverability paragraph) and `docs/plans/dataset-centered-workspaces/`. This is documentation acceptance, not product acceptance or a standards certification.

## Standards authority and actual checks

The repository's [existing plan](../../dataset-workflows/plan.md) adopts [Coding-Standards dcc56f26](https://github.com/MrScripty/Coding-Standards/tree/dcc56f26e884ade260770beceba2501d3746200d). Fresh standards main was `188beda1fa477d21d576c233dd8c7f4c4c267d23`. Direct Git comparison shows Core, Router, the [plan template](https://github.com/MrScripty/Coding-Standards/blob/dcc56f26e884ade260770beceba2501d3746200d/templates/PLAN-TEMPLATE.md), planning, architecture, verification, documentation, commit and the plan validator unchanged between these revisions. This task does not upgrade Tuldok's standards pin.

Actual source-based routing: Core/Router; Planning and Discovery for the roadmap; Implementation and Development Proportionality as Planning prerequisites; Verification for claims/evidence; Documentation for durable knowledge; Commit for branch/staged publication; Architecture for new-owner composition. The plan records affected future frontend/accessibility, contracts/persistence, concurrency/lifecycle, security, dependencies/licensing and consumer verification gates. No language profile is selected for this docs-only patch. Future implementation must route its actual selected technologies, including TypeScript/Rust if adopted; old prose saying no language profile exists is not reused as a current routing result.

Tuldok contains no `AGENTS.md`, `.agents/skills`, `.mcp.json` or Standards Engine configuration in this snapshot; `/workspace/.agents` and `/workspace/.codex` are empty and executor skill discovery returned no skills. Tool metadata search found no standards route/read/validation MCP. Source-based review proceeds, but Engine routing/validation is **unavailable and was not performed**. The fetched `.agents/skills/standards-engine/SKILL.md` is authoring-only and explicitly excludes ordinary application agents; no standards mutation was attempted.

The real structural check is `standards_verifier.checks.plan_contract.validate_plan`, not a homemade standards checklist. Reproduce using the read-only Coding-Standards checkout at either identical validator revision:

```sh
PYTHONPATH=/workspace/research-coding-standards:/workspace/research-coding-standards/tools/standards_verifier python3 - <<'PY'
from pathlib import Path
from standards_verifier.checks.plan_contract import validate_plan
error = validate_plan(Path('docs/plans/dataset-centered-workspaces/plan.md').read_text())
print(error or 'PASS')
raise SystemExit(bool(error))
PY
```

This validates plan fields/headings, lifecycle/acceptance values and the complete named design probe structure. It cannot establish semantic simplicity, research accuracy or product behavior; independent content review supplies that planning evidence.

## Check results

| Check | Result and limit |
| --- | --- |
| Actual upstream `plan_contract.validate_plan` | PASS after matching the real template's named design probes; validates structure, not semantic compliance alone |
| Adopted/current standards comparison | `git diff --exit-code dcc56f26..188beda1 --` the named Core/Router, planning/discovery, implementation/proportionality, architecture, verification, documentation, commit, template and validator files: PASS, no differences |
| Local Markdown links and pinned GitHub source references | PASS: each relative destination exists; each pinned repository/source path resolves through `git cat-file -e` in the corresponding exact clone. Markdown code fences balanced. Primary product pages were opened and checked directly |
| `git diff --check` | PASS; repeated for the staged candidate before commit |
| Independent material review | PASS with all findings resolved; [review record](independent-review.md) pins the reviewed plan bytes and scope |
| Changed-path/README review | Only the new plan directory and one README paragraph; no runtime, fixture, CI, prior-plan or unrelated feature edits |
| Fresh remote preservation check | Main `1bb2c3a`, PR32 `83b2df9`, PR33 `581fa5c` and mesh branch `dd7661d` remained unchanged before publication |

No application tests, training-bearing aggregate, browser screenshots of an implemented new UI, or native integration are claimed. The current task creates the plan, so screenshots are executable future milestone gates. The existing CI's new-docs-branch push exclusion and PR training commands are scope constraints, not passing CI evidence. Full application/required CI remains a future merge gate.

The request supplies the product direction; this task performs bounded source feasibility work and records remaining spikes. No separate interactive HTML discovery process is claimed. The plan's diagram is a review aid derived from its canonical decisions.

## Publication boundary

Commit and push only the planning branch; verify its remote SHA and retain it for review. No draft PR is opened in this task: the unrestricted `pull_request` workflow executes the actual trainer consumer and installs its runtime, which conflicts with the explicit no-training task boundary. Opening a PR is conditional in the request and is not necessary to publish the plan. No PR approval rejection occurred and no alternative route was used to bypass one. The branch can be opened for review later with authorization for its CI effects.

## Source-review clarification checks

The narrow follow-up was checked against pinned Pantograph `docs/headless-workflow.md` (the UniFFI attribution store and publication lifecycle). The actual upstream plan validator, affected relative/pinned-source links, Markdown fences, staged write-set and whitespace checks were repeated successfully. The original independent review remains bound to its recorded original plan digest; the follow-up implements the separately supplied source-review findings. No application or CI tests were run.

## Local-first PostgreSQL amendment checks

- Re-read the pinned Dataset/Workbench/ImmutableAssets/Releases owners and SQLite-specific callers; independently reproduced 145 `execute` calls across 16 production modules, 64 connection-context scopes, and direct `.db` access in 30 of 37 Python test modules. The separate audit's 21 SQLite-specific test modules remain attributed to that reviewer. Counts establish coupling, not migration duration or runtime success.
- Checked primary PostgreSQL/Psycopg/SQLite documentation for transaction/connection lifetime, Read Committed snapshots, text NUL and JSON representation, binary data and backup scope. The [storage audit](storage-audit.md) links those sources and states concrete executable gates. Exact supported server/driver versions remain a future qualification decision.
- Repeated the actual upstream `plan_contract.validate_plan`: PASS. Checked all seven plan Markdown files, eight unique relative destinations, 33 exact pinned GitHub objects, balanced code fences and the README link: PASS. Whitespace and staged-scope checks are repeated before the amendment commit.
- Fresh read-only remote lookup still shows main `1bb2c3a`, PR32 `83b2df9`, PR33 `581fa5c` and the bounded-mesh branch `dd7661d`; their heads are unchanged, and both PRs still report lifecycle failures. No failed-log retrieval was retried.
- The amendment records intended local PostgreSQL with ordinary files, an independently deliverable M1, and MB before M2 persistence. Source review is not proof of migration, offline execution, concurrency or recovery. No DB install, migration, application/training test, PR, CI run or implementation was performed.
- Independent narrow amendment review: PASS after resolving snapshot-to-cutover quiescence and the omitted native-text transaction owner; the [review record](independent-review.md) pins the final reviewed plan digest. The reviewer also independently reproduced the source counts and passed the actual validator and whitespace check.
