# Independent implementation-plan review

Reviewer: independent GPT-6.1 Sol High review worker. Date: 2026-10-19.
Disposition: **clear for documentation publication and a later explicitly
authorized implementation handoff; no remaining blocking plan finding**.
This is not implementation, product acceptance, integration approval or a
Standards Engine certification.

## Exact reviewed subject

The subject is the uncommitted draft in the separate
`docs/lab-workflow-reliability-plan` worktree, based on main
`300f12df6f48e028fd9379911703f7c89337952a`. The final binding material has these
SHA256 identities:

| File, relative to this plan directory | SHA256 |
| --- | --- |
| `plan.md` | `62d33606c5829d7bb26562985fdc8d13e8f8f3e7380ab5ef9e31fabd96752af3` |
| `reports/contracts-and-acceptance.md` | `815dc87cfb438b83563c3671e0c91ab8ae51fc5b035cf030a7544eb8dfe257c5` |
| `reports/baseline-and-standards.md` | `60a887e2169ad9966242dc70c6edb133df115d9f809debb4549cb131ff12f4a4` |

Also read the current issues, execution ledger and validation report. Their
subsequent recording of this review or final validation does not change the
binding subject above. Material semantic changes require affected re-review;
recording unchanged evidence does not impose a new commit-topology requirement.

Inspected adopted Coding Standards at
`dcc56f26e884ade260770beceba2501d3746200d`: Core, Router, canonical Planning,
Architecture and Development Proportionality, with relevant Implementation,
Verification, contract/proof-lifetime/evolution, resilience, security and
performance guidance. Read the accepted D1 architecture/evidence design and
the existing Run, external-recipe, Model/Study, lineage, storage and agent/client
contracts and affected source. Read the exact PR90 objects at
`429d0c4ff44dba16bc95313d2a0980169dbc9b9f`, including RES-1 and coordinator
startup/loop/shutdown. PR89/90 remain proposed dependencies in this plan;
reviewing their objects does not establish a merge or current CI success.

## Findings and dispositions

### R1 — Recovered evidence needed an explicit supported consumer contract

**Originally blocking; resolved in the reviewed revision.** Keeping a legacy
Run failed while merely publishing recovered bytes did not define how actual
completed-state-gated artifact/evidence readers or candidate selection would
consume those bytes. Existing `runs.py` readers and
`Experiments.select_candidate` cannot acquire that meaning through a UI label.

C2 now owns an exact versioned attached publication-result Ref binding catalog,
Run, material, inventory, custody receipt and result identity. New negotiated
artifact/evidence/compare readers, collection, Run presentation and lineage
links consume that Ref through the supported verifier. Legacy failed projections
remain failed/unavailable. Candidate/package promotion and new recovered-result
input bindings are explicitly unsupported in this initial scope. M1's consumer
and write-set inventory and T2/T7 now cover new and old readers, cold/rootless
access, Ref mismatches and promotion refusal. This makes recovery useful without
silently weakening legacy completion or selection contracts.

### R2 — Distinguish scientific per-case criteria from training passes

**Recommendation; resolved.** C6 and T7 now bind an owned criterion Ref,
threshold, direction, units and scope; show per-case pass/fail/unknown; and keep
diagnostic checks distinct from qualified acceptance. Missing criteria stay
unknown. This is separate from the actual training iteration/pass-count axis;
neither UI arithmetic nor synthetic fixtures invent scientific thresholds.

### R3 — Bound publication recovery independently from compute admission

**Recommendation; resolved.** C2 now specifies a named finite initial wall
budget, serialized catalog/Run recovery, inventory-derived verification/copy
I/O, one reserved temporary copy and bounded detailed history. Exhaustion pauses
with a limit outcome. Original/final proofs and mandatory audits remain retained;
owner policy cannot enlarge the original settled resource envelope. T2 exercises
these limits and unchanged compute charges. These are proposed operational
bounds to verify during implementation, not measured throughput claims.

## Review conclusions

- C1 binds preflight to exact submission material and required checks while
  preserving current admission/dispatch authorization, storage, capacity and
  mutable runtime/device rechecks. It promises no prediction of arbitrary
  output success or future resource availability.
- C2 preserves the original attempt, fault and successful-drain proof, uses
  explicit owner recovery and stable reconciliation identity, and forbids new
  GO, training, grants, reservations or compute charges. Invalid/oversize
  required evidence cannot be repaired by relabelling or silent truncation.
- C3 addresses actual RES-1 inside Runs: unhealthy readiness fences, owned
  futures/custodians, bounded joins, serialized replacement and durable custody
  reconciliation precede readiness. Unknown GO/custody and final shutdown are
  not cleared by a live thread, dead PID or automatic restart.
- Phase spans distinguish elapsed time from cumulative/overlapping work, retain
  clock domains and uncertainty, cover preparation before admission, and expose
  stale/open/unknown intervals. Producer timing is not workflow timing.
- M4 measures before retaining machinery. C4 does not cache grants, access,
  capacity or mutable installed-runtime proof. C5 preserves per-item authority,
  inventory/hash identity, partial outcomes, segment bounds and complete-hash
  local publication within a bounded batch.
- The SDK/CLI remain thin negotiated clients with stable mutation identities,
  explicit unknown outcomes, finite monitoring and cancel-versus-drained
  semantics. They acquire no scheduler, installer, owner budget or grant role.
- Scientific comparison binds compatible data/splits/cases/metrics/units and
  exact evidence operands, preserves missing values and measurement scope, and
  distinguishes external observations from managed custody. Lineage intent
  does not establish quality or trigger compute.
- The six milestones are proportionate dependency-ordered vertical outcomes,
  with named owners, write sets, acceptance paths and re-plan triggers. M1 uses
  existing HTTP/AgentClient consumers rather than depending on the future M5
  facade. Supported public/persisted versions, stopped migration/restore,
  interrupted commits and backup/forward-repair rollback remain explicit.

## Checks actually performed and limits

Rehashed the three binding documents and independently ran the unchanged
`validate_plan` AST/constants/helpers from the adopted local checker. Result:
**PASS**, returning `None`. Checker source SHA256:
`c7266c0564b9ee02944fc4eb12d66cc20d604fd4ddb7f051ed77d01e9fe4466e`.
This proves that checker's selected structural rules, not semantic completeness
or application behavior. Final directory-wide link/whitespace/scope validation
is recorded separately by the plan author.

Only this allocated review report was written by this reviewer. No product,
shared branch, PR89/90 source, catalog, hardware/runtime, producer or application
test was changed or executed. No benchmark, scientific or CUDA result was
established. All required source and standards reads succeeded; no environment
access limitation affected this review. A1–A8 and T1–T8 remain future
implementation acceptance. Execution
still requires the later explicit plan instruction, lead disposition of
PR89/90/current baseline, actual required-environment tests, independent review
and applicable release gates. Missing lab receipts, compatible scientific pairs
and hardware remain visible dependent evidence needs.
