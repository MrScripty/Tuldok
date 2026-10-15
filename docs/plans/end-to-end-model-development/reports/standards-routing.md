# Coding Standards MCP authority and design-plan application

Recorded 2026-10-15. The user's request explicitly selected the Coding Standards
MCP for this plan. The running server is Standards Engine interface **47**,
implementation **0.2.0**, purpose **authoring**, installation state **current**.
Only read-only discovery, routing and content retrieval operations were used.
No standards proposal, review, apply or publication operation was requested or run.

Exact routing facts, selected policy IDs, canonical source paths and content
SHA-256 values are retained in [standards-routing.json](standards-routing.json).
The snapshot was
`snapshot:v1:5d59fde2-6756-42e9-a6d3-fba30457128c`.
The catalog digest was
`sha256:8a9f84b8c07f364eb36aa7e0b6d96832bc70957e82d709a12c110bb74292242e`.
Runtime/tool identity is evidence of what was read, not approval of this plan.

## Routing facts

- Activities: planning, documentation, uncertainty reduction and verification of
  the resulting design-plan artifact. Production implementation is outside this task.
- Affected design forms: frontend interactions, launcher/CLI projection and
  reusable model/trainer interfaces.
- Interfaces: persisted definitions/evidence and process messages. Language
  bindings and generated executable schemas have not been selected as mechanisms.
- Topics: architecture, contracts, concurrency, security, resilience, performance,
  diagnostics, accessibility, dependencies and licensing.
- Details: discovery, code design, immutable results/replay, contract schemas/
  protocols/evolution and GUI/oracle/platform evidence.
- Registered language/framework selections: empty. This catalog has no Python
  or plain-JavaScript profile; Rust/TypeScript/Godot were not inferred from neighbors.
- Concurrent-plan-integration profile: not selected. Research reports have
  disjoint writers and one serial plan owner; no competing mutable-plan proposals
  were prepared for integration.

The route returned **complete**, **31 selected standards**, **zero unresolved
routing questions** and **zero unresolved policies**. All four content pages
were retrieved from the same snapshot. Core, Router and the selected prerequisite
closure were read; the actual `templates/PLAN-TEMPLATE.md` was retrieved through
`read` after the navigation index identified its canonical path. The template
is a structural aid; the returned exposure was `needs-review`, not an application
or architecture qualification certificate.

## Requirements that changed this plan

| MCP policy | Concrete design-plan consequence |
| --- | --- |
| `workflow.planning`, `workflow.planning.discovery` | Scope is a plan for designing the architecture. D1–D4 have goals, write sets, gates and lifecycle states; only D1 is next. Candidate design choices are distinguishable from user requirements. |
| `topic.architecture`, `topic.code-design` | Evaluate actual concern ownership, caller obligations, representative change paths, independent evolution and deletion. The seven-part conversational sketch is not a required module count. |
| `topic.architecture` authority-scope admission | Experiment composition references independently owned data/model/evidence/runtime/access policies; packaging information together does not transfer their authority. I1 resolves experiment/Pipeline configuration ownership. |
| `workflow.planning.discovery` substantial discovery | Bounded source and evidence investigations ran independently while a separate writer maintained local HTML/CSS. The main agent alone integrates decisions; the visual remains provisional. |
| `topic.contracts`, `.schemas`, `.protocols`, `.evolution` | D2 names canonical semantic owners, full boundary proof, actual consumers, version roles, invalidation and compatibility. New probe artifacts cannot be silently inserted into closed v1 inventories. |
| `topic.architecture.replay`, `profile.boundary.persistence` | Cold evidence binds its complete retained authority; current authorization is checked separately. Historical inspection, captured observations, replay and training resume have distinct promises. Migrations and backup/restore need explicit design. |
| `topic.concurrency`, `topic.resilience`, `profile.boundary.ipc` | Tuning uses one execution owner and specifies idempotency, child cancellation, partial evidence, unknown outcomes and restart. Worker events do not authorize completed publication. |
| `topic.security`, launcher profile | Automatic dashboard setup does not authorize new code, grants, installations or test disclosure. Current scopes and exact-material execution rules remain until an owned replacement is designed. |
| `topic.performance`, `topic.diagnostics` | Capture cadence, retained data and telemetry need declared cost/lifecycle/meaning. Missing measurements stay distinct from zero; physical time and optimizer progress remain distinct. |
| `topic.dependencies`, `topic.licensing`, library profile | Software precedents support alternatives. Select a dependency only for a concrete interface requirement with maintenance/license/runtime evidence; do not create a public SDK or plugin system solely for convenience. |
| Frontend/accessibility and GUI verification | D3 specifies linked selection, stale-result exclusion, current viewer permissions, keyboard/numeric access and real-browser design evidence. A local diagram does not prove the future app workflow. |
| `workflow.verification` and oracle/platform details | A0–A5 distinguish evidence kinds, environments and modes. Source inspection, structural validation, design prototypes, actual producer observations and product acceptance prove different claims. |
| `workflow.development-proportionality` | Each proposed investigation names a decision, smallest adequate method and stop condition. No training campaign, new verifier or dependency installation is added merely to create a plan. |
| `workflow.documentation`, implementation prerequisite | One canonical plan owns sequencing; ledger, issues and reports have distinct roles. The earlier evaluation proposal is retained as historical research with a link. |

## Authority scope

The repository's historical plans adopt Coding Standards `dcc56f26`. This task
uses the explicitly requested live MCP guidance for the new design plan while
preserving those historical records and existing application contracts. It
does not change the repository-wide adoption pin or claim a standards upgrade.

The available local standards checkout at `188beda1` supplies the existing
`validate_plan` structural check. Its result is a supporting structure check,
recorded separately from manual review against the current MCP content. Neither
routing completeness nor a passing structural validator certifies the product
architecture or closes pending design acceptance claims.
