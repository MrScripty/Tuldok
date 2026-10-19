# Baseline, sources and standards application

## Source baseline

Observed 2026-10-19 through GitHub PR reads and anonymous read-only Git refs:

| Subject | Exact revision / state | Meaning |
| --- | --- | --- |
| main | `300f12df6f48e028fd9379911703f7c89337952a` | Base of this docs-only worktree; merge of completed D1 CLI-baseline documentation. |
| [PR89](https://github.com/MrScripty/Tuldok/pull/89) | `33069a859836953960a06dfd6001cba54aba0aa0`, open/unmerged | Proposed managed Torch registration, live Project activity and compatibility repairs. No fresh CUDA/science result is claimed by integration review. |
| [PR90](https://github.com/MrScripty/Tuldok/pull/90) | `429d0c4ff44dba16bc95313d2a0980169dbc9b9f`, open/unmerged, based on PR89 | Capacity/custody/deadline/idle-history work; retains explicit RES-1. |
| Adopted Coding Standards | `dcc56f26e884ade260770beceba2501d3746200d` | Local Core/Router, canonical policies, plan template and structural validator. |

Inspected repo Git trees and local workspace instructions: no AGENTS.md or
repository-local `.agents/skills` were present in main/PR89/PR90. Workspace
`.agents`/`.codex` expose no task instructions. The standards repository's
`standards-engine` skill is specifically for authoring the standards library,
and says ordinary application agents use application tools; it is not applied
as an authoring workflow to this application documentation task.

Read current D1 architecture/evidence/handoff and existing contracts:
[Project CLI](../../../contracts/project-cli.md),
[external recipes](../../../contracts/external-recipes.md),
[model development](../../../contracts/model-development.md),
[Run lifecycle](../../../contracts/workspace-runs.md),
[lineage](../../../contracts/experiment-lineage.md),
[agent operations](../../../contracts/agent-operations.md) and
[storage](../../../contracts/workspace-storage.md).
Inspected `pipeline.py` material/preflight, `runs.py` admission/publication and
artifact readers, `extension_evidence.py`/`model_evidence.py` profile limits,
`project_cli.py`/AgentClient and existing lineage/comparison UI. Read the exact
PR90 source and request-latency findings without checking out or changing its
branch. Existing owners are sufficient; no new scheduler or runtime installer
is justified.

The following observations are not new benchmark/hardware acceptance:

- Lab feedback: 70.9 seconds training within 275.1 seconds workflow; completed
  training could not publish diagnostics exceeding evidence shard limits; custom
  HTML was needed for scientific comparison. Raw private receipt inputs are
  absent here, so classification remains an explicit M1 observation.
- PR90 retains historical same-Run 189-byte artifact reads around 7.7→0.394 seconds,
  paired preflight 15.104→14.263 seconds, and new restore reads 2.1–2.3 seconds.
  Different workloads, sampling caveats and the unhealthy-coordinator observation
  prevent a controlled whole-workflow speedup claim. See
  [the exact retained findings](https://github.com/MrScripty/Tuldok/blob/429d0c4ff44dba16bc95313d2a0980169dbc9b9f/docs/plans/request-latency-v1/issues.md).
- Fresh CUDA/scientific training was not reproduced by this plan review. Existing
  actual lab receipts retain their original source/environment scope.

## Standards route and design application

The observable task is implementation planning plus durable docs/commit/review,
not standards maintenance or product execution. Future milestones affect a
Python SDK/CLI, browser UI, persisted/public contracts, lifecycle, resources and
scientific interpretation. There is no language-specific, FFI, framework, new
third-party dependency or package-publication change in this documentation task.
No concurrent mutable-plan proposals exist; the independent reader and one
serial writer do not select concurrent-plan-integration machinery.

Selected canonical guidance and concrete application:

| Guidance | Applied decision |
| --- | --- |
| Core, Planning, Implementation, Development Proportionality | Preserve requested outcomes/owners; six useful vertical milestones, exact write sets, one next slice; classify missing inputs without repeating D1. |
| Verification + Independent Oracles + GUI/Platform evidence | A1–A8 separate evidence kind/environment/mode; T1–T8 assert exact failures and no-effect invariants; real process/store/browser evidence cannot be replaced by fixtures. |
| Documentation + Commit | One repository-native plan directory, current decision owner, separate ledger/issues/reports; isolated docs worktree; no unrelated branch changes or merge. |
| Architecture + Code Design + Immutable Authority Closure | Complete eight-probe composition review; one authority per material/custody/runtime/budget/science concern; refs and disposable caches do not acquire authority. |
| Contracts + Evolution + Protocols/Schemas + IPC/Persistence | Preserve installed closed contract identities, explicitly version changed representations, update real consumers, explicit stopped migration/reopen/rollback. |
| Concurrency + Resilience | At-most-once GO, serialized health recovery, owned futures/drain, unknown outcome reconciliation; no automatic retraining or thread restart that clears custody uncertainty. |
| Security + Cross-platform + delegated-authority detail | Current scopes and transitive disclosure; private no-follow bounded files, no credential/path leakage; trusted-local process scope and no stronger sandbox promise. |
| Diagnostics + Performance | Bounded indexed detail and accurate overlapping spans; measured cold/warm/history-size costs; no guessed budget or speed claim. |
| Library / Launcher / Frontend profiles + Accessibility | Thin client and existing CLI preserve outcomes/ownership; real browser lifecycle, keyboard/table/narrow-screen paths and stale-response cleanup. |

Requires closures follow the local Router and canonical policy metadata. Proposed
product implementation must re-route if baseline, deployment, dependencies or
publication facts change. No external source/library was adopted here.

## Tooling availability and validation boundary

No Standards Engine MCP tool is exposed in this session. The checked-in public
helper can list application operations and schema, but actual application-purpose
`route` invocation returns exit2: `Application invocation is unavailable; use the
published interface contract.` No authoring-purpose retry, direct standards
mutation, application certification or guessed successful route was substituted.
Manual routing above records current observed facts and policy application.

Use the exact local `validate_plan` function with its original constants/helpers
for structure, then independent prose/contract review and link/scope checks.
[Validation](validation.md) records the exact source hash, command and limits.
This is standards-guided planning plus structural validation, not a full Engine
checkpoint, semantic completeness certificate or product acceptance result.
