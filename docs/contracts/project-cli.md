# Project execution CLI

`project_cli.py` uses the existing authenticated agent operations. Saved graphs,
execution grants, Run custody, progress, cancellation and artifacts keep their
existing owners and remain visible in `/workspaces` → Current local catalog →
Pipeline / Runs. The CLI opens no catalog and owns no model or scheduler.

Install base requirements, including the pinned JSON Schema validator; no MCP
package or connection is needed for the CLI. The optional agent environment is
also supported. Reuse the [agent client's private config](agent-operations.md)
with `endpoint`, `catalog_id`, `token_file` and optional `timeout`. Endpoint must
be numeric loopback HTTP with an explicit port. Config/token files must be owned
private regular files. Start the server with the desired project root alias.

Commands negotiate exact per-operation contracts. Additive server operations do
not disable compatible CLI calls; an incompatible requested operation is refused.
Definite old-server route absence permits exact frozen legacy fallback. Ordinary
auth/server/malformed discovery failures never trigger fallback. Contract selection
is internal to the client; there are no schema, telemetry or retry flags to manage.

An owner issues an agent credential with `inspect,edit,execute` and optional
`cancel` scopes. The CLI cannot approve execution. In Pipeline the owner reviews
the exact graph preflight, expands **Grant this material to an actor**, selects
that agent's actor ID and creates a one-use grant. Scope alone grants no execution.
Keep credentials out of shell arguments, recipes and version control.

## Explicit sequence

```sh
PYTHON=/path/to/agent-environment/bin/python
CONFIG=/private/tuldok-agent.json
$PYTHON project_cli.py --config "$CONFIG" open --root research --manifest project.json
$PYTHON project_cli.py --config "$CONFIG" inspect --project-id PROJECT_ID
$PYTHON project_cli.py --config "$CONFIG" recipe --project-id PROJECT_ID \
  --reference-id train --expected-sha256 RECIPE_SHA256
$PYTHON project_cli.py --config "$CONFIG" prepare --arguments graph-inputs.json
$PYTHON project_cli.py --config "$CONFIG" preflight --graph-id GRAPH_ID --revision 1
# Owner reviews this exact material in Pipeline and issues its one-use grant.
$PYTHON project_cli.py --config "$CONFIG" submit --arguments submission.json
$PYTHON project_cli.py --config "$CONFIG" status --run-id RUN_ID --progress
$PYTHON project_cli.py --config "$CONFIG" status --run-id RUN_ID
$PYTHON project_cli.py --config "$CONFIG" download --run-id RUN_ID \
  --name weights.npz --expected-sha256 ARTIFACT_SHA256 --out ./new-weights.npz
$PYTHON project_cli.py --config "$CONFIG" cancel --run-id RUN_ID
```

Uppercase identifiers stand for actual returned values. Commands emit existing
domain JSON and return1 with a bounded JSON diagnostic on failure. They do not
poll/retry or infer successful completion. `status --progress` reads bounded
streams and the compact result. `cancel` requires that credential scope.

`graph-inputs.json` contains the existing `graphs.create_external` arguments:

```json
{
  "name": "Captured model training",
  "project_id": "ACTUAL_32_HEX_PROJECT_ID",
  "recipe_id": "train",
  "expected_sha256": "ACTUAL_64_HEX_RECIPE_SHA256",
  "inputs": {
    "dataset": {"reference_id": "dataset", "expected_sha256": "ACTUAL_DATA_SHA256"}
  },
  "parameters": {"steps": 100}
}
```

Inputs also support existing `frozen_release` and `run_artifact` bindings. Keep
the selected split file in captured recipe inputs. The CLI never allocates or
reinterprets model splits. Root paths remain local server configuration.

`submission.json` contains the exact `runs.submit_external` arguments:

```json
{
  "request_key": "captured-training-attempt-001",
  "graph_id": "ACTUAL_32_HEX_GRAPH_ID",
  "graph_revision": 1,
  "expected_digest": "ACTUAL_64_HEX_PREFLIGHT_MATERIAL_SHA256",
  "approval_id": "ACTUAL_32_HEX_OWNER_GRANT_ID"
}
```

A stable request key belongs to exactly this actor/body. Explicit unchanged
`submit` reconciles uncertain admission through the existing server contract.
Inspect saved state before retrying; never create another key because a reply was
lost. `prepare` creates a graph separately from preflight so its returned identity
is visible before another operation. Lost graph creation acknowledgements require
inspecting saved Pipeline graphs. Graph/source/input/runtime drift requires fresh
preflight and owner approval.

Downloads use the existing segmented reader and check the complete SHA256 before
publishing a new mode0600 file. They refuse existing files, directories and dangling
symlinks, including concurrent destination creation. Corruption or refusal removes
provisional bytes. An explicit lab restore recipe must validate downloaded weights
before interpreting their schema/model compatibility.

## Minimum training adapter contract

The [project](projects.md), [external recipe](external-recipes.md) and
[captured CPU runtime](captured-cpu-runtime.md) contracts are unchanged. Numerical
implementation and physics-specific manifests belong to the opened lab project.
The suitable existing lab `scripts/train_cpu.py` implementation is a NumPy
volumetric CNN with gradients and Adam. `trajectory_model.ModalPressure.fit`
reports closed-form fitting and zero optimizer steps; it cannot establish neural
optimization. The existing CNN's radius-one receptive field also limits global
pressure reproduction; loss reduction alone cannot establish pressure quality.

The lab recipe declares an exact reader/model/wrapper source closure, selects
a qualified CPU runtime snapshot, accepts captured dataset/persisted split
references and writes flat bounded outputs. Opening/preflight never loads a
model. Captured datasets train without a native producer; generation and physics
evaluation are independently optional recipes.

| Output | Existing role | Lab-owned evidence |
| --- | --- | --- |
| `weights.npz` | `checkpoint` | Real trained arrays, schema/shape/dtype and hash |
| `splits.json` | `training_splits` | Persisted train/validation/test IDs and grouping policy |
| `receipt.json` | `training_result` | Input/split/source identities, train-only preprocessing, seed, optimizer steps, timings and weight hashes |
| `summary.json` | `result_summary` | `tuldok_result_summary_v1` metrics/scope/checkpoint |

Progress uses existing `tuldok_progress_v1` stdout events. Compact summaries have
`format,title,metrics,scope` and optional `checkpoint`; metrics have `name,value,unit`.
The checkpoint must name an output with role `checkpoint`. Runs verifies custody
and bytes; numerical acceptance stays lab-owned.

A separate restore/evaluate recipe binds checkpoint/dataset/split artifacts by
exact hashes, starts a fresh process, refuses shape/dtype/source/normalization or
split mismatches, and reports reproduced predictions and actual metrics. It must
never refit on holdout or silently regenerate splits. Generic process fixtures
do not establish neural optimization, pressure quality, native physics acceptance,
GPU use or remote execution.

## Registered model-development calls

`python project_cli.py --config PRIVATE_CONFIG call --operation models.get --arguments model.json`
uses the same installed registry, exact capability selection and bounded JSON
argument reader. For example, `model.json` contains `{"model_id":"OPAQUE_ID"}`.
`recipes.material` accepts `{"ref":RETAINED_MATERIAL_REF}` and `studies.get`
accepts `{"study_id":"OPAQUE_ID"}`. All print the same domain result available
through selected HTTP and structured MCP. No project code executes on inspection.
Only locally registered operations are callable; this is not an arbitrary URL or
route dispatcher. Existing AgentClient requires an active agent credential, and
owner-only study control still requires authenticated owner HTTP actions.

## Optional operator observations

Ordinary commands require no telemetry arguments or setup. The operator may
explicitly select a fresh private v2 store with `--observe-v2-database` before
the subcommand. Retention/configuration, independent health inspection, private
storage and failure semantics are owned by the [shared observation contract](mcp-observer.md#shared-interface-observation-v2).
Collection defaults off. Recording failure does not alter command results,
consume another grant or authorize a retry. A written output terminal proves
only local stdout/stderr acceptance; partial delivery remains unknown.
