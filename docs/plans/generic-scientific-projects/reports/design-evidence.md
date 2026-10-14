# Design evidence and qualification limits

## Inspected sources

Read-only review on 2026-10-13 established these source facts. No scientific execution was performed during that review or this planning assignment.

| Source | Observation and consequence |
| --- | --- |
| [Tuldok main pipeline](https://github.com/MrScripty/Tuldok/blob/c522bf6b5eaf94d89811578c9e73aecfdba4ef9e/pipeline.py) | Three closed CPU classification recipes; reusable graph ownership, not arbitrary train/evaluate execution |
| [Draft pipeline](https://github.com/MrScripty/Tuldok/blob/51bec9ea89f03357473aca0d40f2fa8251598a25/pipeline.py) | Adds integrity/export stages for spatial assets; does not train scientific models |
| [Draft Rheon import](https://github.com/MrScripty/Tuldok/blob/51bec9ea89f03357473aca0d40f2fa8251598a25/rheon_sequences.py) | Statically coupled fixed-profile v1/v2 parsing, not a generic producer interface |
| [Volume owner](https://github.com/MrScripty/Tuldok/blob/51bec9ea89f03357473aca0d40f2fa8251598a25/volume_assets.py) | Bounded uint8 NPY volumes cannot losslessly represent floating scientific fields |
| [HTTP handlers](https://github.com/MrScripty/Tuldok/blob/51bec9ea89f03357473aca0d40f2fa8251598a25/app.py) | Useful existing domain operations; localhost/same-origin guard is not authenticated human/agent identity; `--data` opens managed storage |
| [Pipeline contract](../../../contracts/workspace-pipeline.md) / [Runs contract](../../../contracts/workspace-runs.md) | Reuse revision checks, idempotent admission, process identity, artifact custody and holdout exposure; broaden only where external execution demands it |
| [Current lab experiment](https://github.com/MrScripty/rheon-surrogate-lab/blob/e8a90bfef6b2955c502008ccc62443e29dd9f2ec/experiments/trajectory-v2/README.md) | 32³ trajectory model, 12 training trajectories × 8 frames, four 120-frame test rollouts; native simulation outside learned pressure solve; CPU control and GPU results are separately recorded |
| [Modal model](https://github.com/MrScripty/rheon-surrogate-lab/blob/e8a90bfef6b2955c502008ccc62443e29dd9f2ec/scripts/trajectory_model.py) | Fits 32,767 gains by supervised modal least squares; no new architecture needed for initial integration |
| [Experiment driver](https://github.com/MrScripty/rheon-surrogate-lab/blob/e8a90bfef6b2955c502008ccc62443e29dd9f2ec/scripts/trajectory_experiment.py) | Native subprocess interaction, training, freeze, checkpoint and rollout artifacts remain lab-owned |
| [CPU control](https://github.com/MrScripty/rheon-surrogate-lab/blob/e8a90bfef6b2955c502008ccc62443e29dd9f2ec/scripts/trajectory_cpu.py) | Existing same-thread CPU evaluation path; requires actual compatible runtime and native binary, not merely Python installed |
| [Verifier](https://github.com/MrScripty/rheon-surrogate-lab/blob/e8a90bfef6b2955c502008ccc62443e29dd9f2ec/scripts/verify_trajectory_results.py) | Checks original artifacts/hashes, disjoint seeds, memory, full-field errors, physics gates and timing summaries; preserve native artifact layout for this oracle |
| [Pumas runtime launcher](https://github.com/MrScripty/rheon-surrogate-lab/blob/e8a90bfef6b2955c502008ccc62443e29dd9f2ec/scripts/pumas_trajectory.py) | Selects managed PyTorch 2.14 environment; this is a training Python environment, not Tuldok's Pumas inference API |

Repository inspection found no Tuldok MCP server/OpenAPI catalog or general project opener. HTTP APIs and documented Python domain owners are the existing integration base. This is a scoped source finding, not a promise that undocumented external integrations do not exist.

## Roadmap dispositions

The [prior readiness audit](../../rheon-v2-consumer/reports/readiness-20261013.md) already separates bounded accepted workspace work from the persistent overall goal. Preserve that distinction. This plan adds concrete scientific execution and agent authority scope; it does not reopen every historical plan, certify PR43's missing actual producer packet, or count controlled-provider tests as dataset-workflows A8 real-model success.

Legacy actual v2 qualification needs original recorded frames. The newer lab workflow uses different dimensions, trajectory lengths and artifact schemas. Neither should be passed off as the other's acceptance evidence. Missing bulk lab captures should be reported; a deliberately admitted new bounded generation run may provide new evidence, but cannot recreate a historical receipt or untouched test set.

## Environment procedure before scientific implementation

1. Inventory configured local Python/PyTorch/NumPy and Rust toolchains without installing or changing a managed runtime; identify actual device availability.
2. Resolve lab source, its required Rheon revision, native executable identity and tracked checkpoint; separately locate required ignored capture files. Missing inputs remain missing.
3. Run the smallest admitted native subprocess handshake/cancellation probe to settle process ownership before broader execution design. Record descendant and pipe behavior.
4. Inspect a real capture's arrays in a cold reader to settle schema, centering and storage bounds before P2 freezes the wire format.
5. Execute new CPU evaluation in a separate output directory using existing checkpoint and recorded protocol; preserve exposure labels and new provenance. Then qualify a new training/evaluation run.
6. Run GPU/performance qualification only if actual requested hardware/runtime exists. CPU behavior, fixture lifecycle and old published benchmarks cannot satisfy it.

## Standards basis

Read the adopted [plan template](https://github.com/MrScripty/Coding-Standards/blob/dcc56f26e884ade260770beceba2501d3746200d/templates/PLAN-TEMPLATE.md), Planning, Architecture and Verification sources, and existing repository verification records. Template and plan-validator files match the available standards checkout. Route future implementation through actual Python/JavaScript, contracts, persistence, process/concurrency, security and accessibility policies when its slice is admitted; this planning document does not certify unwritten code.

No `AGENTS.md` or `.agents/skills` was present in the inspected Tuldok worktree; workspace `.agents` and `.codex` directories were empty. No Standards Engine route/validation tool is exposed. Source-based checks are recorded in the ledger; no Engine result is fabricated.

## Scientific acceptance protocol to freeze before P5

The reviewed trajectory driver uses training seeds 100–111 (eight reference frames each), validation seeds 500–501 (60 frames), and test seeds 900–903 (120 frames). Those test seeds are historically exposed: replaying them is reproduction/correctness evidence, never a new untouched generalization claim. Do not silently choose fresh seeds to improve an acceptance score. Any new holdout protocol must be selected and frozen before inspection and is a separate scientific claim.

Retain the recorded sealed uniform 32³ box, density 1.25 kg/m³ and time step 1/60, forcing/tracer conventions and gauge. The pinned verifier checks divergence at most 1e-5, residual at most 1e-8, Courant at most 1, and zero learned pressure iterations; it recomputes full-field velocity/tracer errors using its recorded precision tolerance. Freeze the actual source-defined error tolerances and definitions from the selected driver/verifier before executing P5; this plan does not invent substitute error thresholds.

Use the existing trajectory verifier only on its matching artifact/protocol schema. Its historical workload/resource/timing expectations do not automatically apply to CPU-control output. Before P5, identify the CPU driver's native checks and any missing cold-reader verification, then add only the necessary independently justified CPU result reader in the optional integration package. CPU acceptance requires the actual field/physics correctness, full native baseline comparison, identity and lifecycle gates. It does not require historical CUDA memory or speedup values. If an unchanged verifier rejects a changed environment/protocol, report that mismatch; do not modify original frozen receipts or skip checks while claiming full verification.

## Independent review

Read-only review by `/root/mesh_review` found no blocker to presenting this planning proposal. It requested explicit protocol/seed/exposure separation and a single initial array layout with precise source-byte versus array-byte custody. The plan/report now specify both. Review did not certify runtime feasibility, source-code compliance or scientific results.
