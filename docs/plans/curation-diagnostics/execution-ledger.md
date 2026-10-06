# Execution ledger

Owner authorization: development/publication on one isolated feature branch from verified combined e33144a; preserve pending caption repair and every integration/component/main ref. Parent owns PR metadata and hosted CI. Repo-local author and committer remain MrScripty <TheEnvironmentGuy@protonmail.com>.

Implemented POST /api/workbench/curation, no new database schema. Shared Workbench current filters and diagnostic contributor predicates drive both analysis counts and member lists. Rollback-only savepoint covers legacy synchronization. Freshness token hashes current scoped facts and requested exact references; altered facts require explicit refresh before paging. New UI keeps applied-filter criteria separate from typed input, fixed selected pairs separate from current diagnostics, request epochs separate from editor intent, and inspection separate from saving/reviewing.

Declared write set: app.py, workbench.py, curation.py, static/workbench.{js,html,css}, static/curation.js; workflow additions that retain all prior gates; four curation test files; this plan/ledger and curation report artifacts only. Regenerated preexisting suite screenshots are supporting local evidence, excluded from the commit.

Qualification covers all registered suites and actual screenshots as detailed in reports/verification.md and reports/evidence.json. No endpoint/provider setup was attempted after the brief real-runtime inventory blocked that optional qualification. No models, authentication or network policy changed.

Review boundary: read-only diagnostics and present-record inspection only. No dynamic saved-set mode, corpus import duplication, rights correction, segmentation, inference, quality scoring, batching registry or broad UI cleanup. Integration and pending caption branches are not composed here.
