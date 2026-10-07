# Read-only curation diagnostics

Base: verified combined workbench e33144a389e611dfb9e95a83f248e7bf87d7a3aa. Separate feature branch; integration, component branches and main stay unchanged.

Scope: existing exact decoded-content duplicate, annotation-none, deleted source record and projected unknown-rights facts. Workbench owns filter validation and analysis; Dataset owns sources. No inference, permission decisions, review grants, membership replacement or saved reports. Current metadata is inspected for applied criteria or exact selected IDs; stale/missing references stay explicit. Empty boxes/spans are labeled negatives. No filesystem-integrity claim for the metadata source-availability fact.

Read boundaries: shared lock and rollback-only savepoint include existing lazy enrollment. SHA256 current-fact token fences pagination. UI request epochs fence scope/category/filter/selection changes and delayed responses. Explicit current-record inspection uses editor dirty guard and revision check; selected revision pairs never refresh implicitly.

Gates: real HTTP + SQLite persistence checks; contributing membership and exact AND filters before pagination; stale/deleted/missing references; rollback on failures; deterministic delayed controller checks; actual Chromium controls with fixed selections and dirty inspection, downloaded release, desktop/narrow screenshots; complete registered Python/JS/browser suite. Do not weaken existing gates.

Positive real-model check: blocked in this environment. Bounded local inventory found no model files/process; reachable model catalogs match controlled repository fixtures. No setup/download/auth changes. Evidence: [committed runtime inventory](reports/runtime-inventory.json).

Validated review repair: selected diagnostics retrieve only requested IDs, including scoped rollback-only legacy enrollment. Freshness hashes stream the exact existing canonical facts and preserve token bytes. Contributor predicates, full filtered-scope analysis, read-only savepoints and human-review separation are unchanged. See [scaling repair evidence](reports/review-scaling-repair.md).
