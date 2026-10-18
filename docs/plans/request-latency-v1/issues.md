# Findings

PERF-1 (high, owner Runs, fix-now): constant full-history validation under the
catalog lock in _loop and queue-capacity checks. Real minimal HTTP read plus
unchanged queue-scan profile and targeted regressions identify it. Selected-state
routing and idle event waiting are implemented and live qualification passed.
Resolved in eed2b84; no claim that all preparation latency is removed.

ENV-1 (qualification limitation, owner legacy image adapter): the pinned CPU
training runtime is absent from this application environment. One existing
RealCPURunTests check fails identically on the unchanged base. Record unavailable,
not passed; use actual Pumas CPU restore plus existing neutral real-custodian tests
for this pressure-workflow qualification. Revisit if supporting that old adapter's
numerical training environment becomes part of the requested work.

Public list/input-candidate and startup recovery still intentionally perform full
selected disclosure/recovery integrity. No performance change is claimed there.
Revisit only if representative after-fix measurements still identify them as a
limiting user workflow. No skipped artifact, authorization or dispatch checks.


RES-1 (existing resilience limitation, owner Runs, deferred separate repair): a
catalog advisory-lock timeout can terminate _loop; _start does not recreate an
already assigned dead thread. Observed after the long read-only queue profile.
The latency repair removes that repeated long history scan but does not claim to
repair arbitrary coordinator exceptions. Do not treat an exited coordinator as
healthy idle performance. Scope a separate bounded recovery/liveness change with
failure tests rather than hiding arbitrary errors or dispatch retries here.
