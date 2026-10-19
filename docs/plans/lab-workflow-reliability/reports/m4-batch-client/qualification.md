# Explicit batch consumer qualification

Source implementation `61a34c9`, composed with canonical transport `92546d7` and
final M5 `40d7f61` at `a4ff908`. This report owns the SDK/CLI consumer only.
The service source and its paired performance qualification remain separately
owned by M4. Neither low-level benchmark timings nor segment hashes establish
consumer whole-artifact verification or a scientific result.

`WorkflowClient.collect_batch` and `collect-batch` select one existing collection
manifest, at most20 whole artifacts and at most8MiB aggregate requested bounds.
They negotiate the exact batch operation, recheck inventory, decode ordered
source/selector-correlated items and verify complete length/EOF/whole SHA256
before private fsync/atomic no-clobber publication. They never fall back or retry.
Partial results retain typed per-item outcomes using the existing collection
receipt. Only explicit ordinary collect resume reauthorizes/rehashes successes
and restarts incomplete artifacts. All pre-existing WorkflowClient methods are
AST-identical to final M5; the shared private publisher extraction preserves
ordinary download behavior. CLI signal handling delegates to the canonical read
budget/Event and never requests compute cancellation.

The initial39 controlled and existing workflow/CLI/download tests passed in
103.853seconds. The composed22 focused checks passed in1.700seconds. Exact logs,
hashes, source identity and the approximately15second overlap with the first
unavailable zero-history M4 paired control are retained in `validation.json`.
No positive measurement cell overlaps that initial suite.

Actual HTTP/clean CLI qualification is pending the M4 quiet-window release.
Its eight test cases are authored against actual neutral20-artifact custody and
an actual attached publication Ref: clean collection and ordinary resume, typed
item failure, delivery-time revocation, post-delivery whole-hash/identity faults,
held-read Event cancellation, existing/racing destinations and exact recovered
Ref preservation. No fake runtime acceptance, training, numerical improvement
or scientific criterion is claimed. Independent publisher/CLI review is pending.

The change uses the repository's Core/Router, Implementation, Verification,
Commit, Documentation, Contracts/Security/Resilience and Library/Launcher/IPC/
Persistence guidance. It adds no dependency, registry operation, server behavior,
database migration or automatic recovery policy. Root owns final CI composition
and remote publication. Ordinary discovery includes the new focused test files;
the actual boundary tests require the existing disposable PostgreSQL DSN.
