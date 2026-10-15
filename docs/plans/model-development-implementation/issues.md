# Implementation issues

| ID | Owner / evidence | Disposition and verification |
| --- | --- | --- |
| I1 | Agent transport; old8MiB segment expands beyond draft8MiB response ceiling | Select16MiB negotiated limit consistent with actual existing receive bound; preserve frozen legacy metadata, test maximum declared segment behavior. |
| I2 | Full server selected-request validation; jsonschema previously agent-only optional | Reuse existing pinned4.26.0 lazily in base requirements, keep imports/discovery stdlib and headerless behavior unchanged; verify actual server rejection before owner/grant. |
| I3 | Environment lacks psycopg/PostgreSQL/Torch | Provision private test environments; no skipped/absent runtime claim. GPU/physics separately unqualified. |
| I4 | Cross-thread messenger absent | Shared GitHub handoff and parent relay; serial shared-file owner, extension worker isolated scope. |
| I5 | Independent P1 review: original Run receipts bind actor/body but not selected contract identity | P1 keeps one submit meaning. Before any submit v2/new meaning, P2+ must bind semantic operation identity in durable admission/reconciliation; no cross-version replay claim. |
| I6 | Independent P1 review found legacy shared-route blocking and insufficient unknown-schema validation | Preserve headerless legacy dispatch; new shared branches explicitly require their selected ID. Validate every advertised fragment/bounds through existing validator. Regression tests and re-review required. |
| I7 | Inherited test environment has MCP1.29, while adopted lock pins1.30 | Initial MCP receipts are supporting1.29 observations only. Provision fresh private base+hash-locked optional environment; rerun acceptance under1.30 before merge. |
