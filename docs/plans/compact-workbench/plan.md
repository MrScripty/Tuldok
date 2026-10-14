# PR33 reconciliation

**Plan status:** `Accepted`

**Current phase:** Local reconciliation accepted; serial publication handed to root

**Next slice:** `none`

**Acceptance status:** `satisfied`

**Execution ledger:** [execution-ledger.md](execution-ledger.md)

**Issues:** [issues.md](issues.md)

## Objective

Reconcile owner PR33's canvas-first collection, source and annotation layout
against admitted main `f2751c3224ed0280ba285262698d15144a8fed9f`.
The user authorized reconciliation, fixes and qualified integration. The serial
integration owner admitted this base on 2026-10-14. Operation: `start` for this
plan. Preserve original owner head `581fa5ca471186ed641ec4bf6d134ee1ba807d22`
through a merge on isolated branch `reconcile/pr33-compact-workbench-20261014`
in `/workspace/Tuldok-pr33-reconcile`; no rewritten owner history.

## Objective Acceptance

| ID | Observable criterion | Kind | Environment | Mode | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | Current IDs/constraints/modalities/controllers retained; usable desktop/narrow canvas, native drawer/focus/disclosure workflows and original image coordinates | `user-workflow` | Chromium151, isolated authored fixtures, headless software graphics | `automated` | `satisfied` | [Source-bound layout receipt](reports/reconciliation-layout-receipt.json) |
| A2 | Affected domain/controller/browser and embedded Data/Pipeline/Runs gates pass without weakened assertions | `integration` | Current-main PostgreSQL and actual Chromium; pinned existing CPU consumer | `automated` | `satisfied` | [35 browser gates,15 Python tests,11 controller suites](reports/reconciliation-checks.json) |
| A3 | Independent review, focused syntax/diff and serial publication handoff preserve original owner history | `review` | Isolated original-descendant branch | `manual` | `satisfied` | [Independent review](reports/independent-review-20261014.md); root receives the named branch for final publication/CI/merge |

## Binding Decisions

- The presentation adapter moves existing standalone controls without cloning
  controls, changing validation, taking domain ownership or clearing drafts.
- Existing main HTML is authoritative for all current kinds, tasks, imports,
  exports and script registration. Keep its forms and attributes intact.
- Compact styles apply only to the standalone shell. Embedded workspace Data
  retains `workspaces-data.js`, its existing drawer and edit/context ownership.
- The admitted main has no P3 actor/session system. Do not import future auth
  machinery or invent a bypass. A later scientific integration must requalify
  its own authentication and field-sequence composition.
- Root owns serial publication, exact-head checks and merge. This branch may
  commit after focused verification; publication requires the root handoff.

## Scope

Write set: `app.py` static asset registration; `static/workbench.html` includes;
`static/workbench-layout.js`, `static/workbench-layout.css`; retained current
`static/workbench.css`; PR33 collection metadata/current-record hooks in
`static/workbench.js`; original layout browser/navigation evidence and directly
affected browser/controller tests; `.github/workflows/tests.yml`; this compact
workbench documentation. The affected embedded regression adds
`tests/browser_workspaces.cjs` to this write set; no embedded production owner
changes. No v2 or MCP ancestry, domain changes, test deletion,
owner worktree edits, auth bypass or whole old-HTML replacement.

## Constraints And Assumptions

Standards: Coding-Standards `dcc56f26e884ade260770beceba2501d3746200d`, Core,
Router, Planning/Discovery, Implementation, Verification/GUI, Commit,
Development Proportionality, Frontend, Accessibility, Code Design and
Documentation. Native dialog/disclosure behavior must retain visible keyboard
focus, cancellation, restoration and invalid-field reachability. Existing
controllers own canonical state; the layout owns presentation and its status
observer lifetime. Composed-design review: not applicable; this reconciles one
bounded presentation owner and retains existing independently owned domain and
embedded-workspace contracts. Root serializes integration; no same-plan
concurrent proposal authorizes shared mutation.

## Simplicity And Ownership Review

**Applicability:** `not-applicable`

**Reason:** One bounded presentation owner arranges existing controls; domain,
modalities and embedded-workspace ownership/interfaces remain unchanged. No new
runtime, state store, or independently deployed contract is introduced.

## Milestones

### Reconcile and qualify the standalone workbench

**Status:** `Accepted`

Goal: restore the owner's standalone canvas-first
layout while preserving all admitted-main control IDs, required/range/length
constraints, controller scripts and current modalities. Desktop collection and
source must have useful independent space; narrow content must fit. Native
drawer open/close, Escape, focus return, draft/selection preservation, status,
disclosure validation, review/save/release and original image coordinates must
pass in real Chromium with isolated authored fixtures. Existing affected
browser/controller suites and embedded workspace Data/Pipeline/Runs behavior
must pass; syntax and diff checks must pass. Screenshots support only the
observed Chromium/layout claim, not inference, scientific quality or external
accessibility conformance.

## Blockers

No current implementation/environment blockers. Isolated pinned consumer and
the supported existing native-reader interpreter resolved both observed
environment obstructions without weakening tests. Independent review passed and
root received the candidate/branch publication handoff. Hosted checks and merge
remain a separate root-owned integration decision.

## Re-Plan Triggers

- A current control/domain owner cannot be preserved.
- Embedded context, dirty state or operation ownership changes.
- Root admits a different base; requalify that composition before integration.

## Final Acceptance

- Acceptance status: `satisfied`
- Final status: `Accepted`
- Publication and integration remain root-owned.

Evidence: [ledger](execution-ledger.md), [issues](issues.md), owner
[presentation/captures](README.md), [fresh verification](reports/reconciliation-20261014.md).
Worktree outcome: `retained-protected`. Retain `/workspace/Tuldok-pr33-reconcile`
for root publication/integration; its head is `retained-ref` through
`reconcile/pr33-compact-workbench-20261014`, with commit disposition `retained`.
Root owns next disposition and records the exact final head before safe cleanup.
Existing owner worktrees are outside that scope.
