# Extension-system planning baseline and inputs

Recorded 2026-10-15. This is source inspection and planning provenance, not
extension implementation or runtime qualification. The canonical
[plan](../plan.md) owns decisions and sequencing.

## Repository baseline

The local documentation branch `docs/extension-system-plan` starts at PR62 head
`f99182c03da1e070081718ef6829eaeac3c82640`. Its application baseline is
`f58880df84d701ef66ffe21615ae787d80ce8a5e`. PR62 is architecture design, not
implemented model-development functionality. This task neither changes that
branch nor assumes its proposed APIs exist.

| Current owner / source | Established behavior | Extension planning consequence |
| --- | --- | --- |
| [Projects](../../../../projects.py), [project contract](../../../contracts/projects.md) | Closed schema1; immutable saved manifest/root identity; bounded descriptor-relative no-follow reads. Open/get does not import Python, install, probe or execute. Same ID with changed snapshot conflicts. | Preserve inert opening and old registrations. New declarations require explicit versioning, not extra ignored fields or replacement of saved snapshots. |
| [Recipe contract](../../../../recipe_contract.py), [external recipes](../../../contracts/external-recipes.md) | Closed external_recipe_v1; exact sources/inputs/runtime/material; typed argv, flat bounded outputs; current graph input→execute→output. | New contributions and stage meaning require owned contracts. Keep old formats/limits readable; do not mutate their meaning to make an extension appear compatible. |
| [Pipeline](../../../../pipeline.py) | Editable recipe authority and exact preflight/capture composition. | Extension references/configuration become Pipeline material, not a second mutable training configuration. |
| [RuntimeSnapshots](../../../../runtime_snapshots.py), [CPU contract](../../../contracts/captured-cpu-runtime.md) | Explicit offline runtime capture/verification; finite qualified profiles and immutable identity. No arbitrary interpreter path or startup installation. | Discovery can report missing runtime. A dependency declaration or lockfile cannot establish available execution. |
| [Runs](../../../../runs.py), [custody helper](../../../../recipe_process.py) | One supervisor, Linux subreaper/READY–GO, exact bounded continuation, verified drainage and publication; unknown cessation fences execution. | Numerical extensions execute through existing custody; no loader callback, stdout success or second scheduler can admit/complete work. |
| [Access](../../../../access.py), [actor contract](../../../contracts/actors.md) | Live current authority; owner-only built-ins; exact actor/material one-use external grants; required transactional audit. Already admitted bounded continuation may finish after credential revocation. | Enablement/compatibility never grants execution. New work after revocation is denied; cancellation controls an admitted Run. |
| [Agent registry/client](../../../../agent_api.py), [agent contract](../../../contracts/agent-operations.md) | Current client `_check_discovery` uses whole-registry equality. PR62 selects future per-operation compatibility, but does not implement it. | Sequence actual negotiation/cutover before claiming additive independent capability compatibility. Preserve fail-closed incompatible mutations and live Access. |
| [Scientific fields](../../../contracts/scientific-fields.md), [PR62 evidence design](../../end-to-end-model-development/reports/evidence-contract-design.md) | Byte integrity, semantic interpretation and numerical acceptance differ. Current generic artifact access lacks the proposed transitive scientific protected-test gate. | Host owns structural readers, custody and current access. Extension evaluators execute only as admitted work; unsupported semantics stay opaque and protected modes remain unavailable until every accessor is covered. |

## Reviewed research supplied by the parent

Both reports were retrieved successfully through ChatGPT Library `read`, including
all continuation windows. They are research inputs, not executed conformance:

| Library identity | Supplied name / size | Use |
| --- | --- | --- |
| `libfile_4f69c599d8f081918b849c2c40c8cf39` | `report(1).md`,40,780bytes,410lines | Main manifest/contribution/semantic/UI/SDK recommendation and independently packaged A/B field extension. |
| `libfile_b3cefad07b08819183f3bce0a8cd1619` | `runtime-boundaries.md`,31,459bytes,150lines | Existing runtime/Access/custody limits, CPU files/mmap, GPU ownership, transport distinctions and fault acceptance. |

The parent reported independent acceptance of both research inputs. This task
adds its own independent review of the resulting repository plan; it does not
claim to have repeated the research review or its proposed experiments.

Preserve the supplied distinctions: static discovery before activation; exact
protocol versus semantic versions versus content identities; declared/observed/
granted capability; host structural/query authority versus admitted numerical
evaluation; provisional scalar progress versus committed evidence; CPU file/mmap
first; GPU within trainer only after separate qualification. DLPack is not a
cross-process protocol. Same-user Python is trusted-local execution, not an
adversarial security sandbox. No new framework or transport dependency follows
merely from a useful precedent.

The individual draft transfers (before integration edits) were:

| Destination | Library identity | Reconstructed bytes |
| --- | --- | --- |
| `plan.md` | `libfile_9a298e9668988191914e7730abef7a69` | 71289 |
| `execution-ledger.md` | `libfile_b27a18385620819199e3306075dc184f` | 1820 |
| `issues.md` | `libfile_1afd4cacdee48191a0c54244c6752e23` | 2334 |
| `reports/standards-application.md` | `libfile_e41a785e4644819190b3af694ea91a90` | 4416 |
| `reports/plan-verification.md` | `libfile_d611600b9e988191bcbd2121a6dedecf` | 1772 |

The ZIP `libfile_d0802802f88881918a4b268bca9995d8` was resolved but failed
helper download. Direct Library text reads resolved the transfer blocker; no
binary artifact or package was installed. These repository copies are local
planning derivatives, not replacements or edits to the source Library items.

## Standards and task authority

No applicable `AGENTS.md` exists in repository/workspace ancestors or repository
paths inspected. No callable Coding Standards MCP is exposed in this task.
[PR62 routing](../../end-to-end-model-development/reports/standards-routing.md)
and its JSON receipt are historical evidence; no fresh MCP consultation or Engine
certification is claimed.

Read adopted Coding Standards `dcc56f26e884ade260770beceba2501d3746200d`
planning/discovery, documentation, development proportionality, contracts,
security and immutable-authority guidance from the retained source checkout.
Use its original `validate_plan` structural function, with source SHA-256
`c7266c0564b9ee02944fc4eb12d66cc20d604fd4ddb7f051ed77d01e9fe4466e`,
as supporting structure evidence only. A fresh read-only GitHub retrieval in this
integration confirms the original13,132-byte checker and blob
`5eea8ad6d912dc2e710dfaac71a67c9b61ca9698`; the template is7,610bytes,
SHA-256 `c12c0365bb558c8ef973647fc74af9678cd1c35f54d17b104afdd3ed373f4f50`. The resulting plan must separately resolve
owners, actual consumers, version/migration boundaries, exact milestone write
sets, real acceptance procedures and all eight composed-design probes.

Authorization is local documentation planning, independent GPT-6.1 Sol review,
validation and local commit on the dedicated branch. No push, PR, implementation,
training, installation or user-data change is authorized by this task. The parent supplied the native draft as individually readable Markdown after ZIP
transfer failed. All five reconstructed texts match their Library byte sizes;
research copies also match the previously read size/hash. Integration changes
lifecycle/clarity and resolves source-backed review findings; it does not redo the
reviewed external research.
