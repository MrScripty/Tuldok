# Plan: Retained checkpoint curve and linked examples

**Plan status:** `Accepted`

**Current phase:** M4 complete; independently reviewed; lead-owned integration

**Next slice:** Lead review and serial integration of the completed dependent PR.

**Acceptance status:** `accepted for this bounded slice`

**Execution ledger:** [execution-ledger.md](execution-ledger.md)

**Issues:** [issues.md](issues.md)

## Objective

Open an exact retained classifier result in Runs, inspect its metric curve,
select an exact checkpoint and page its frozen examples/errors, with current
access, numeric, lifecycle and provenance guarantees. View opening is inert.

## Objective Acceptance

| ID | Observable criterion | Kind | Environment | Mode | Status | Evidence |
| --- | --- | --- | --- | --- | --- | --- |
| A1 | Closed named query rejects malformed identities, unknown fields and unbounded requests before reads; exact substitutions fail before result return | contract | not-applicable | automated | passed | [focused tests](reports/m1/focused-tests.log) |
| A2 | Exact metric values, stable examples, pagination/support and frozen identity agree with retained bytes and actual PostgreSQL | integration | required-real | automated | passed | [actual retained query tests](reports/m3-actual/retained-query-tests.log) |
| A3 | Actual Runs browser supports keyboard, linked selections, narrow layout, stale replies, revocation, malformed/large specs, offline assets and cold reopen | user-workflow | required-real | automated | passed | [actual Runs browser](reports/m4-integrated/browser.json), [strict isolated renderer](reports/m4-integrated/renderer.json); complementary scopes documented |
| A4 | Query/export reauthorize every retrieval, no cache authority, no computation or mutation on opening | integration | required-real | automated | passed | [query/HTTP tests](reports/m4-integrated/query-http-tests.log), [real Run revocation/export/cold reopen](reports/m4-integrated/browser.json) |

## Scope

### In Scope

First recipe: existing native `model_evidence_v1` classifier checkpoints,
validation metrics and retained fixed-probe examples. One result/run per request;
exact result and metric-definition hashes. Server-owned parameterized SQL over
the existing PostgreSQL Run document and a bounded verified example projection.
No schema change, role/credential change, or production migration.

### Out Of Scope

Scientific field queries, arbitrary SQL/Python/JS, benchmark execution, extra
plot libraries, generic EAV/schema engines, computed-on-open analyses and saved
view persistence. Revisioned overrides follow the completed immutable slice.

## Binding Decisions

| Decision | Owner | Evidence | Supersedes |
| --- | --- | --- | --- |
| Runs owns retained verification; query owner only projects verified results | Runs | `runs.py:2331`, `model_evidence.py:381` at main 8c9c0b0 | none |
| `retained_checkpoint_examples` v1 selects explicit run, evaluation, metric definition and checkpoint hashes | retained_analysis | [contract](../../contracts/retained-analysis-query.md) | none |
| Existing text Run document remains authoritative; JSONB casts are disposable query projections | Metadata/Runs | schema v10; raw artifact hashes retained | none |
| Vega-Lite/vega-embed with interpreter and self-hosted pinned assets | renderer | official upstream docs; later asset/browser qualification required | none |
| Lead alone merges; shared hooks approved after composing reliability83a1e128 | repository lead | parent relay 2026-10-20; explicit approved hunks | initial pending coordination |

## Design Observations And Remaining Evidence

No AGENTS.md exists in workspace/repository. Applied Core/Router and selected
implementation, verification/oracles/GUI, planning, commit, documentation,
architecture/replay/code-design, contracts/protocol/evolution, persistence/IPC,
security/delegation, concurrency/resilience, performance, dependencies/licensing,
accessibility/frontend guidance from Coding-Standards dcc56f26. No callable
Standards Engine is exposed; this is source-guided routing, not certification.
Brief `libfile_e94877d6735c8191a6e5d78c82d1151b` read in full (five pages).

Initial source environment lacked PostgreSQL/configuration and a qualified CPU
runtime. The parent clarified that a disposable local test database and ordinary
official dependency setup are within scope. Task-owned PostgreSQL 17.11 now runs
under `/tmp`, using the existing local_postgres helper; pinned CPU packages are
provisioned in a separate test runtime. Six actual retained-query tests and all
13 original query tests pass. Initial skipped evidence remains unchanged.
No production catalog, credential, role or system-service change is involved.

## Simplicity And Ownership Review

**Applicability:** `applicable`

- Independent concepts and dimensions: frozen analysis identity; mutable view
  selection; current access; transport lifecycle; chart rendering.
- State, identity, value, time, policy, mechanism: Runs/artifacts own evidence,
  Access owns current scopes, Metadata owns transaction/lock, this module owns
  one closed read query. Query version does not revise metric meaning. Result
  hash changes invalidate selections; colors never change result identity.
- Caller/composition knowledge: caller sends exact identities and bounded page;
  query invokes the established verifier. Browser needs no artifact paths/SQL.
- Representative changes: adding a second recipe changes the query registry;
  replacing renderer leaves result query intact; new metric meaning creates a
  new retained result instead of mutating this query.
- Stable interfaces: explicit response fields, units, support and unavailable
  errors. Internal evidence path knowledge stays in Runs.
- Independent evolution/failure: query can be tested without shared UI edits;
  missing data is typed unsupported/unavailable, never substituted.
- Necessary complexity: strict decoding, evidence closure, bounded SQL and
  post-read authorization protect separate reachable failures.
- Deletion result: removing renderer leaves current Runs fully functional;
  removing query leaves no persisted second authority or migration.

## Milestones

### M1: Authorized bounded retained query

**Allowed write set:** `retained_analysis.py`, `tests/test_retained_analysis.py`,
`tests/retained_analysis_actual_fixture.py`, `tests/test_retained_analysis_actual.py`,
`tests/test_retained_analysis_http.py`, `tests/browser_retained_analysis_actual.cjs`,
`docs/contracts/retained-analysis-query.md`, `docs/plans/retained-analysis/**`.

Implement closed validation, exact retained identity, owned bounded SQL,
typed columns/units/support/provenance and final access check. Review through a
separate GPT-6.1 Sol High instance. Gate A1; A2/A4 remain blocked without actual DB.

### M2: Embedded curve and linked table

Allowed additive files: `static/retained-analysis.js`,
`static/retained-checkpoint-curve.vl.json`, `static/vendor/retained-analysis/**`,
`examples/analysis/retained_checkpoint_curve.py`,
`examples/analysis/requirements.txt`, `tests/browser_retained_analysis.cjs`,
`tests/retained_analysis_browser_fixture.py`,
`tests/fixtures/retained-analysis-browser.js`,
`tests/fixtures/retained-analysis-browser.css`,
`docs/contracts/retained-analysis-renderer.md`.
Shared integration candidates `app.py`,
`agent_api.py`, `static/workspace-real.js`, `static/workspaces.html`,
`static/workspaces.css`, CI; exact hooks must be agreed with lead before edit.
Define mount/resize/update/selection/export/dispose; deny external loaders/editor,
use interpreter under strict CSP. Gate A3 plus actual A2/A4.

### M4: Authenticated integration, approved through parent

Composed dependency: `83a1e1289f3f7e4f8c3e697c1748a862a69d0897`, reliability
PR108 branch (including its composed PR102–110 history). Local composition merge
`252a68c5b90afdd8660f652cfa0094233ef9f64f`; no conflict resolution or reliability
rewrites. The PR must declare this dependency until the lead integrates it.

Allowed shared hunks: `agent_api.py` two new inspect contracts; `app.py` POST
handlers and exact static asset mappings; `static/workspace-real.js` bounded
authenticated transport; `static/workspace-service.js` verified native classifier
mount/disposal; `static/workspaces.html` (scoped CSP before assets; initially disabled selector), scoped CSS and additive CI commands.
Normal Run read catches propagate access denials to generation/session-aware
private-content cleanup; no non-auth reliability fallback changes.
New `retained_analysis_schema.py` owns the narrow schema. Preserve all existing
coordinator/phase/publication/batch/scientific-comparison behavior and old
operation identities. HTTP bodies omit run_id; validated path ID is injected.
Execute actual SQL, authenticated HTTP, Runs browser, real revocation/export and
cold-reopen acceptance, then independent review before publication readiness.

## Blockers

- `none` for implementation or local acceptance. Lead-owned integration remains; no new user permission is needed.

## Re-Plan Triggers

Real data exceeds declared query budgets; incompatible artifact formats;
shared hook ownership changes; actual CSP/interpreter incompatibility; measured
need for indexed relational facts requiring a separately gated schema migration.

## Repository Isolation

Path `/workspace/Tuldok`; branch `feature/retained-analysis-query-20261019` from
main `8c9c0b0`. Preserve all README and reliability branches. Lead owns merge;
retain source/evidence and branch for its review. No worktree deletion planned.

## Final Acceptance

- Acceptance status: `accepted for this bounded slice`
- Evidence: [M4 acceptance](reports/m4-integrated/acceptance.md)
- Deferred follow-ups: general query recipes, persisted revisioned view overrides,
  benchmark manifests and later scientific workflows; outside this first slice
- Final status: `Accepted` for the implemented slice; lead alone owns merge
