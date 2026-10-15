# Reference admission

Parent authorizes local adaptation from Coding-Standards branch
`feat/issue3-mcp-observability`, exact head
`4887b7aff0ba84acd257da081135b7849cc9c79f`, base
`188beda1fa477d21d576c233dd8c7f4c4c267d23`. Read full verification.md and
independent-review.md at that head plus actual recorder, MCP integration, tests,
operating contract and CC0-1.0 license. Separate extracted read-only source at
`/workspace/issue59-qualified-reference`; adopted standards remain dcc56f26.

Reference qualification is local:40 focused tests,39 observer-v3 tests,73 verifier
suites; Engine635/636 with one fixture failure reproduced on baseline. Independent
GPT-6.1 Sol High review satisfied, including R1–R7. Parent reports pushed branch;
the evidence report predates that publication and names its then-auth blocker.
Hosted CI is pending. Do not describe it as merged or fully CI-qualified.

Reuse/adapt the CC0 recorder's schema-owned value-free input projection, bounded
synchronous SQLite transactions/20ms busy timeout, guarded fixed-code health,
zero-length-only v0 admission, exact DDL/application identity under writer lock,
separate starts/terminal evidence, count/age/page retention, secure deletion,
retention eviction handling and no fabricated restart completions. No new runtime
dependency: stdlib SQLite is mandated by the issue and satisfies local transactions.
No Engine APIs/catalogs/qualification harness or reporting/analytics are copied.

Tuldok-specific differences: no deployment label or catalog manifests containing
unneeded metadata; public registry and exact per-operation schema fingerprints,
source identity digest over only loaded bridge/registry/observer code; generated
session/interaction IDs; up to two live correlations for pending SDK request and
admission refusal; bounded validation/admission/dispatch/returned/terminal stages;
HTTP status, protocol class and actual bytes written; no stored client IDs,
continuations, free-form error codes or payload-derived hashes. Valid notifications
are excluded; malformed notifications that receive protocol replies are observed.
Input shapes use exact top-level declared parameters only; sensitive body/annotation/
recipe/file subtrees are redacted without traversal. This deliberately stricter
projection loses nested diagnostics to avoid Tuldok content/paths.

All shared-store writers must use the same persisted retention policy, enforced at
open. Health only verifies schema/integrity and persistence counts; it is not
reporting. Offline retention requires exclusive process lock; rotation stops all
writers, verifies and moves the standalone DELETE-journal store as documented.
No automatic rebuild, retry, remote telemetry, queue or background task. Synchronous
filesystem and stderr I/O cannot promise a latency bound under a stuck filesystem;
20ms bounds SQLite lock contention only. These limits remain in the operator contract.
