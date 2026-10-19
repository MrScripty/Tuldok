# Concurrent local CPU and CUDA Runs

Status: Accepted; operation start. User authorized simultaneous CPU Runs alongside
one CUDA fit and continuing the pressure-model sequence. Owner: root; branch
performance/concurrent-cpu-cuda-20261017, base8af5a6a1e288e5b2f86a75b53cab93ca71222a04.
Retain this branch for review/integration; existing PR89 and its source branch
remain unchanged. No rewrite, merge or cleanup.

Objective: remove the serial queue bottleneck while preserving exact admissions,
per-attempt custody, cancellation, drainage, restart and immutable publication.
Canonical consumer contract: docs/contracts/workspace-runs.md.

Composition: Runs remains the sole catalog supervisor and owner of durable Run
state, execution futures and shutdown. The existing standard-library executor
provides bounded threading; run_capacity owns only admission budgets, CPU placement
and device classification. Custodians remain one per attempt. Authoritative
recipe resource requests are captured with material; observed placement is Run
execution metadata. No second queue, process supervisor or authority registry.
Changing a capacity budget affects run_capacity and its configuration/tests;
changing custody affects recipe_process independently. Removing capacity would
move resource accounting/placement back into Runs; removing the executor would
restore serial execution. Necessary interleaving is admission before dispatch,
and confirmed cessation/publication before lease release. All copied numerical
sources, runtime assets, model weights and scientific thresholds are unchanged.

Write set: runs.py, run_capacity.py, recipe_contract.py, affected tests,
docs/contracts/{workspace-runs,external-recipes}.md and this plan directory.
No storage schema/version change; prior rows remain retained. New resource
requests use the current recipe decoder and material hash; stale deployments
reject those fields rather than guessing them. No runtime compatibility shim.

Acceptance: focused resource/accounting tests; actual independent overlapping CPU
custodians; disjoint inherited CPU affinity; independent and queued cancellation;
CPU bypass of a blocked CUDA slot; exclusive CUDA dispatch; shutdown joins all
attempts; existing storage-loss/restart/unknown-state lifecycle tests. Actual CUDA
computation and CPU analysis overlap must be observed in the lab before deployment
is qualified for that workload. Source/Spec review and exact staged diff required.

Current phase: terminal for scheduler implementation and hardware qualification.
Next slice: none in this plan; deployment and model experiments continue in the
linked lab plan. All required process checks and both independent review axes
pass. Real CUDA pressure training overlapped managed CPU computation for1.2556s;
the one-update checkpoint restored on CPU with zero updates and CUDA uninitialized.
Exact restored weights/normalization/history and joined executor workers are
recorded in actual-device-overlap-03.json (270.023s total). The old
TinyCNN runtime is unavailable locally; its test fails at runtime preflight before
the scheduler. No package install or fallback to the lab's CUDA runtime is used.

Independent review found a late dispatch/fence race and one uncoordinated drain
fence writer. The real red startup regression, passing13-case built-in lifecycle
receipt10,14-case external/concurrency receipt09 and the final review retain both
findings and their closure. Commit correction preserves the original history.

Related scientific plan: rheon-surrogate-lab/docs/plans/pressure-throughput-feedback-v1/plan.md.
Standards route snapshot:v1:bc3877fc-df9b-41cc-9a60-ec680a5ccf55,
21 selected policies, zero unresolved routing facts. Reservations are admission
budgets, not an OS memory sandbox; other applications/catalogs do not share leases.
