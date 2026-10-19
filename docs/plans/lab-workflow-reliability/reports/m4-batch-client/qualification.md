# Explicit batch consumer qualification

Source implementation `61a34c9`, composed with canonical transport `92546d7` and
final M5 `5634968`; exact qualified source is
`fd42361f043c201290c5b6297a384652320044ed`. This report owns the SDK/CLI consumer only.
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
AST-identical to final M5 `5634968`; the shared private publisher extraction preserves
ordinary download behavior. CLI signal handling delegates to the canonical read
budget/Event and never requests compute cancellation.

The initial39 controlled and existing workflow/CLI/download tests passed in
103.853seconds. The composed22 focused checks passed in1.700seconds. Exact logs,
hashes, source identity and the approximately15second overlap with the first
unavailable zero-history M4 paired control are retained in `validation.json`.
No positive measurement cell overlaps that initial suite.

All eight actual HTTP/clean CLI tests passed on the first attempt in145.991seconds
after the M4 quiet-window release. They use actual authorized neutral20-artifact
custody and an actual attached publication Ref: SDK and clean CLI whole collection,
ordinary resume, typed item failure, delivery-time revocation, post-delivery
whole-hash/identity faults, held-read SDK Event and clean CLI real SIGINT
cancellation, existing/racing destinations and exact recovered Ref preservation.
Each selected output is independently compared with the deterministic producer
bytes and SHA256, private mode is checked, and collection changes neither Run
events nor admission/consumption counts. The two exact fresh schemas were closed
and dropped, then independently queried absent. Their identities and proofs are
retained with source hashes and the full test log in `actual-attempt-01/`.
No fake runtime acceptance, training, numerical improvement, benchmark speedup
or scientific criterion is claimed.

The independent M5 author cleared the frozen `a4ff908` source/default CLI review,
including ordinary method equality, publisher cleanup and atomic no-clobber,
caps, exact inventory/ref/hash validation, failure behavior and explicit ordinary
resume. This is independent source review, not a claim of separate test execution;
its receipt is owned by the M5 report directory. Final exact-source evidence audit
is pending receipt publication by that reviewer. Root CI/serial integration and
the independently owned M4 service usefulness disposition remain pending.

The change uses the repository's Core/Router, Implementation, Verification,
Commit, Documentation, Contracts/Security/Resilience and Library/Launcher/IPC/
Persistence guidance. It adds no dependency, registry operation, server behavior,
database migration or automatic recovery policy. Root owns final CI composition
and remote publication. Ordinary discovery includes the new focused test files;
the actual boundary tests require the existing disposable PostgreSQL DSN.
