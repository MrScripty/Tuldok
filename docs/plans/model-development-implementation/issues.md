# Implementation issues

## Current dispositions after implementation qualification

P1–P6 and their named actual gates are accepted and merged. PR78 composed head
`29f535b5b8d43a5945d3cbd43017bdd8a33be36b` passed all five checks and the lead
merged it as `63b277ebe3a1d4403ef1c64e307b7ef4d7c490a2` at `2026-10-16T06:18:08Z`.
The [implementation plan](plan.md) and
[product record](../end-to-end-model-development/reports/product-implementation-status.md) bind exact source/merge identities and reports.
These current dispositions supersede the historical finding text below.

| Findings | Current disposition and retained verification |
| --- | --- |
| I1, I2, I5, I6 | Resolved by negotiated bounds, lazy complete selected-request validation, exact operation/material receipt binding and unchanged legacy dispatch. [P1](reports/p1-verification.md) and [P2](reports/p2-verification.md) retain source-specific negatives; later full CI and merges are in product status. |
| I3 | Actual isolated PostgreSQL/CPU and pinned optional MCP environments were provisioned for qualification. P3/P4/P5 actual producers and independent consumers passed. GPU/physics remain explicitly unqualified; fixture presence alone is never runtime proof. |
| I4 | Parent relay/shared handoff and one serial integration owner resolved coordination; cross-thread messenger availability is not a product execution requirement. Historical relay observations below are unchanged. |
| I7 | P1 acceptance reran under the pinned MCP1.30 closure. Earlier MCP1.29 observations retain their supporting-only status. |
| I8–I12 | Resolved P2 postcommit custody, bounded documents/pages, anchored orphan inventory, Study-scoped receipt keys and full-composition approval. Actual PostgreSQL rollback/race/unknown/cold checks and merge `8fa4915` are recorded in P2 verification/product status. |
| I13 | Kept production spec/material refusal and corrected only the complete capacity fixture. The failed predecessor remains recorded; later checked source `351f55b` and merged P2 qualification close the then-pending CI gate. |

No known selected implementation issue remains open at these accepted sources.
Future semantic, runtime, access or custody changes require new qualification.
This closeout does not edit any raw failure or claim physics, hard quotas or
hostile-code isolation.

## Historical findings and original dispositions

| ID | Owner / evidence | Disposition and verification |
| --- | --- | --- |
| I1 | Agent transport; old8MiB segment expands beyond draft8MiB response ceiling | Select16MiB negotiated limit consistent with actual existing receive bound; preserve frozen legacy metadata, test maximum declared segment behavior. |
| I2 | Full server selected-request validation; jsonschema previously agent-only optional | Reuse existing pinned4.26.0 lazily in base requirements, keep imports/discovery stdlib and headerless behavior unchanged; verify actual server rejection before owner/grant. |
| I3 | Environment lacks psycopg/PostgreSQL/Torch | Provision private test environments; no skipped/absent runtime claim. GPU/physics separately unqualified. |
| I4 | Cross-thread messenger absent | Shared GitHub handoff and parent relay; serial shared-file owner, extension worker isolated scope. |
| I5 | Independent P1 review: original Run receipts bind actor/body but not selected contract identity | P1 keeps one submit meaning. Before any submit v2/new meaning, P2+ must bind semantic operation identity in durable admission/reconciliation; no cross-version replay claim. |
| I6 | Independent P1 review found legacy shared-route blocking and insufficient unknown-schema validation | Preserve headerless legacy dispatch; new shared branches explicitly require their selected ID. Validate every advertised fragment/bounds through existing validator. Regression tests and re-review required. |
| I7 | Inherited test environment has MCP1.29, while adopted lock pins1.30 | Initial MCP receipts are supporting1.29 observations only. Provision fresh private base+hash-locked optional environment; rerun acceptance under1.30 before merge. |
| I8 | Independent P2 review: acknowledged admission followed by response/callback failure deleted capture | Transfer cleanup ownership to Metadata rollback immediately; postcommit errors retain durable custody. Real PostgreSQL regressions for reply-read and wake failures. |
| I9 | P2 membership and collection writer/reader limits | Explicit1MiB Study/membership/receipt documents checked before commit, tested with7501 valid actual trial rows; bounded model/draft/Study pages and revision-checked reservation pages. |
| I10 | P2 orphan verification checked only parent directory identity | Retain handle-derived file identities after hashing; compare exact anchored inventory and recheck per-file stats under final lock. Real in-place child rewrite leaves parent unchanged and refuses adoption. |
| I11 | Study-scoped keys collided with catalog-global Runs keys | Derive a deterministic Study+actor+originalkey Runs key; retain original semantic key. Two actual studies sharing one key admit independent Runs/grants. |
| I12 | Full composed approval was not bound by legacy executable grant | Dedicated owner studies.approve verifies exact immutable composition/current executable; existing grant binds full RecipeMaterial SHA. Runs retains executable and composed approval identities separately; old-preflight and changed-policy substitution refusal regressions. |
| I13 | CI capacity fixture changed only spec to large CPU while approved material still declared ordinary system Python | Preserve production validate_spec refusal. Build a complete valid declared CPU large capture with the existing authored static descriptor fixture, inject only low disk, preserve no-grant/no-Run/cleanup and legacy reconciliation checks. Actual six-case artifact suite passes0skip; new committed-head CI remains required. |
