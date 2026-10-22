# Project execution CLI

The separate `file-*` commands operate on the explicit external text-project
mode. See [project files](project-files.md) for its canonical authority, owner
selection, checkpoint binding and current milestone limits. Registration `open`
below keeps its existing meaning.

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

When negotiated graph preflight v4 returns a classified preparation refusal,
`preflight` exits nonzero and stderr JSON includes its validated
`preflight_report` beside the original code, message and status. Unknown material,
runtime readiness and execution remain explicit. Ordinary early errors and older
contracts keep their existing projection. A refusal does not create a submission
manifest, grant, reservation or retry. See the
[report contract](run-preflight-publication.md#selected-v4-refusal-reports).

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
$PYTHON project_cli.py --config "$CONFIG" evidence --project-id PROJECT_ID --reference-id activity
$PYTHON project_cli.py --config "$CONFIG" import-data --project-id PROJECT_ID \
  --reference-id capture --expected-sha256 DATA_SHA256
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
For a fresh, inert external retained-material check, write
`{"ref":RETAINED_MATERIAL_REF}` from `studies.trial.material` to a regular JSON
file and call `--operation recipes.preflight_material --arguments FILE` through
the existing `call` command. It returns the selected v3 bounded report or retains
the validated typed refusal report in stderr JSON with a nonzero exit status.
Builtin native probes are unsupported; no execution or Study reservation occurs.
See the [exact material contract](run-preflight-publication.md#exact-retained-study-material-preflight).

`recipes.material` accepts `{"ref":RETAINED_MATERIAL_REF}` and `studies.get`
accepts `{"study_id":"OPAQUE_ID"}`. All print the same domain result available
through selected HTTP and structured MCP. No project code executes on inspection.
Only locally registered operations are callable; this is not an arbitrary URL or
route dispatcher. Existing AgentClient requires an active agent credential, and
owner-only study control still requires authenticated owner HTTP actions.

Snapshot discovery and registration use the same generic command, for example:

```sh
python project_cli.py --config PRIVATE_CONFIG call --operation project_snapshots.list --arguments page.json
python project_cli.py --config PRIVATE_CONFIG call --operation project_snapshots.open --arguments opening.json
python project_cli.py --config PRIVATE_CONFIG call --operation project_snapshots.get --arguments project.json
```

Here `page.json` is `{"limit":20}`, `opening.json` is
`{"root":"research","manifest_path":"project.json"}` and `project.json` is
`{"project_id":"OPAQUE_ID"}`. Files contain arguments only; credentials stay in
the private client configuration. These operations select their highest exact
available contracts. The dedicated `open` and `inspect` commands select the current
snapshot operation when an exact available contract was negotiated, including
project v2. If that operation is unavailable and the corresponding published
`projects.open`/`projects.get` contract is available, the command selects that
legacy project-v1 operation before dispatch. Authentication or malformed
capabilities refuse selection, and an operation failure never triggers a second
call. Snapshot get/open v2 adds the optional activity projection while their
installed v1 contracts retain their exact closed output without activity.
`inspect` with snapshot v2 includes bounded external
activity when the manifest declares evidence id `activity`. `evidence` previews
one ordinary evidence reference; `import-data` explicitly captures and imports
a selected scientific data reference by its observed hash. Both work with
current v2 projects through existing API owners. Failed/stale observations remain
external evidence and cannot become execution or scientific acceptance.
The recipe inspection command negotiates `recipes.inspect/4`, which adds
managed Torch runtime variants. Installed inspection v2/v3 contracts retain
their exact CPU output and return typed `unsupported` for managed Torch.
Generic calls also negotiate `models.publish/2`, `graphs.create_external/2`,
`graphs.preflight_external/2` and `studies.prepare_trial/2` when supported.
These versions authorize static source authoring with current inspect/edit
scopes. They do not authorize owner Study control or execution; see the
[snapshot and authoring boundary](agent-operations.md#negotiated-project-snapshots-and-bound-authoring).
An owner credential cannot be substituted into AgentClient bootstrap.

## Optional operator observations

Ordinary commands require no telemetry arguments or setup. The operator may
explicitly select a fresh private v2 store with `--observe-v2-database` before
the subcommand. Retention/configuration, independent health inspection, private
storage and failure semantics are owned by the [shared observation contract](mcp-observer.md#shared-interface-observation-v2).
Collection defaults off. Recording failure does not alter command results,
consume another grant or authorize a retry. A written output terminal proves
only local stdout/stderr acceptance; partial delivery remains unknown.

Configured observation preserves a single JSON stderr failure diagnostic exactly.
It emits no operator-health lines into that command channel, including when
observer configuration/storage fails. Invoke the independent operator reader
separately to inspect store health; CLI health emission is quiet by default.

## Consumer workflow commands

The [small Python consumer facade](workflow-client.md) also backs these explicit
convenience commands. Existing `submit`, `status`, `cancel`, `download`, `call`
and owner recovery commands keep their existing JSON and exit contracts.

```sh
$PYTHON project_cli.py --config "$CONFIG" submission-manifest \
  --graph-id GRAPH_ID --revision 1 --approval-id EXISTING_GRANT_ID \
  --request-key lab-attempt-0001 > submission-manifest.json
$PYTHON project_cli.py --config "$CONFIG" submit-workflow --manifest submission-manifest.json
$PYTHON project_cli.py --config "$CONFIG" monitor --run-id RUN_ID --timeout 60
$PYTHON project_cli.py --config "$CONFIG" cancel-workflow --run-id RUN_ID
$PYTHON project_cli.py --config "$CONFIG" collection-manifest --run-id RUN_ID \
  --name weights.npz --name receipt.json > collection-manifest.json
$PYTHON project_cli.py --config "$CONFIG" collect --manifest collection-manifest.json \
  --directory /private/existing-results > collection-receipt.json
$PYTHON project_cli.py --config "$CONFIG" collect --manifest collection-manifest.json \
  --directory /private/existing-results --resume collection-receipt.json
```

Redirect JSON only to newly selected files. For Trial admission use
`submission-manifest --trial-id TRIAL_ID --approval-id EXISTING_GRANT_ID
--request-key STABLE_KEY`; its Study revision/epoch come from selected results.
A lost reply returns `unknown` and the unchanged manifest. Save that receipt,
then explicitly use `reconcile-submission --manifest UNKNOWN_RECEIPT.json`.
No command invents an owner grant, request key, scheduler or retry. `monitor`
has a finite overall budget; Ctrl-C stops monitoring only. `cancel-workflow`
explicitly shows requested, drained or cancelled-before-start, separately.

Collection may select `--ref EXACT_PUBLICATION_REF.json` instead of `--run-id`.
A partial/stopped receipt preserves successes and outstanding/refused items;
resume rechecks exact inventory/current access/local whole hashes and restarts
incomplete artifacts at offset0. Ctrl-C discards provisional bytes. Use a new
receipt output path when explicitly resuming; never overwrite the receipt being
read through shell redirection.

`collect-batch --manifest COLLECTION_MANIFEST.json --directory /private/existing-results`
explicitly selects whole-artifact batching through `runs.artifact_segments/1`.
It accepts the same single-source manifest with at most20 selected artifacts and
at most8MiB aggregate requested bounds (`max(1, bytes)` per artifact). Larger
selections refuse before dispatch; ordinary `collect` remains the segmented
path. A complete batch exits0; a partial/stopped batch exits1 with the same
collection receipt JSON on stdout. Service/authority/transport/decoding errors
retain the existing stderr diagnostic and exit1. No error triggers fallback or
retry. The command has no `--resume`; explicitly use ordinary `collect --resume`
with the saved batch receipt to recheck successes and restart incomplete items.
Ctrl-C interrupts reads or stops before the next output publication, preserves
earlier verified outputs and requests no compute cancellation.

`comparison-manifest --run-id BASELINE --other-run-id CANDIDATE
--checkpoint-sha256 BASELINE_CHECKPOINT --other-checkpoint-sha256 CANDIDATE_CHECKPOINT
--metric-id METRIC_ID [--mode paired|side_by_side]` exports selected exact operands.
Both `--ref` and `--other-ref` may select supported attached publication results.
Then `compare --manifest COMPARISON_MANIFEST.json` returns the existing owner's
status/result envelope, including typed incompatibility. It calculates no metrics
and chooses no scientific winner.

New commands return0 for an acknowledged submission, complete collection, observed
terminal monitor or successful comparison operation. Unknown/refused submission,
partial/stopped collection, stopped/deadline monitor and refused comparison exit1
with their structured workflow JSON on stdout. Argument/bootstrap/local errors
retain the existing one JSON diagnostic on stderr and exit1. A terminal failed or
unknown Run remains explicitly so in monitor JSON; exit0 means observation reached
its terminal state, not that computation succeeded. There is no implicit compute
cancel, admission retry or alternate transport.
