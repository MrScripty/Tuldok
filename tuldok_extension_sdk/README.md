# Private extension authoring kit

The source-capturable SDK has two separate commands. `validate` inspects inert
package declarations. `conformance` admits one explicitly selected, already
prepared and externally granted trial through the existing public CLI/API.
Neither command grants itself permission, installs dependencies or starts a
local training fallback. Public SDK/package distribution is outside this scope.

## Inert validation

Explicitly provision `requirements-extensions.lock`, then run:

```sh
python -m pip install --require-hashes -r requirements-extensions.lock
python -m tuldok_extension_sdk validate examples/extensions/template
python -m tuldok_extension_sdk validate PROJECT_ROOT --manifest nested/extension.json
```

Paths are relative to the selected local root. The existing held, no-follow
reader and canonical `extension_contract.py` own declaration validation. No
package code, model, subprocess, network client, app, database or Torch starts.
The included `contracts/` bytes must match canonical `extension_schemas/` exactly;
the SDK defines no additional schema language. Missing optional validation is
unavailable and never causes installation. Linux file-boundary qualification
is not a hostile-code sandbox or a supported execution platform claim.

Output remains the exact canonical catalog projection. Validity, integrity,
host support, runtime qualification and permission are separate. Exit 0 means
the selected declaration validates statically; runtime/permission remain
unavailable. Exit 1 means an included package/contribution is invalid,
unsupported or unavailable. Exit 2 means the root/manifest/schema cannot establish
a catalog. Dependencies outside the selected package remain unavailable.

A standalone validation kit contains `tuldok_extension_sdk/`, canonical
`extension_contract.py`, `extension_schemas/`, the separately provisioned optional
validator closure and selected package. It needs no app, database or numerical
runtime. Tests retain the canonical negative corpus and fresh copied-kit check.

## Evidence construction helpers

`evidence.py` uses only the standard library and the current explicit
`extension_evidence_context_v1` host projection. It is source-capturable without
`manifest.py`, canonical schemas or application modules. Capture both
`tuldok_extension_sdk/__init__.py` and `tuldok_extension_sdk/evidence.py` at those
exact import paths in the producer's new explicit source closure:

```python
from tuldok_extension_sdk.evidence import Evidence, progress

writer = Evidence(output_directory, exact_canonical_host_context_bytes)
# The adapter writes its own real state, arrays and numerical metric values.
writer.transform('transform.npy')
writer.checkpoint(actual_update, actual_clocks, weights_filename, actual_metrics)
writer.finish()
writer.write('diagnostics.json', adapter_owned_diagnostics)
print(progress('fit', actual_completed, declared_total, actual_metrics), flush=True)
```

The methods preserve A's existing writer interface and exact D2 document bytes.
They enforce bounded finite JSON, common catalog/model/task/profile identities,
explicit cadence/clocks, flat names, bounded stable regular Blob files and
exclusive writes. They construct `checkpoint_state_v1`, `checkpoint_index_v1`,
observations, field-pair inventories and `model_evidence_v1` from the admitted
policy. `finish` seals checkpoint capture; an author can still add a separately
declared diagnostic output afterward. `inventory()` reports only files consumed
or written by the helper, including declared probe inputs. The host owns the
complete output-rule inventory, transitive access, custody and publication.

No helper loads an array/weight, fits a transform, computes a metric or evaluates
physics/quality. `load_context(raw)` checks bounded common identities, not the
host's complete policy/grant/source proof. `progress(...)` returns one existing
`tuldok_progress_v1` JSON line using supplied counts; it infers no progress or
clock. `validate_projection(public, context_raw, whole_bytes_by_name)` checks the
current public verified D2 identities and whole-Blob closure without numerical
reconstruction. Its result explicitly says `numerical: not_evaluated`.

A/B must capture and consume the helper in a new source/material identity. Do
not replace the frozen five-source A version or reinterpret its historical
artifacts. Unknown context versions fail unsupported; canonical input-mode and
new semantic policy changes remain host/adapter-owned contract work.

## Explicit authorized conformance

For native field producers, follow the exact
[probe input and per-field target identity rules](../docs/contracts/extension-field-identities.md).
The bound multi-output recipe uses native payload hashes and ordered target
identities; complete NPY file hashes belong to artifact Blobs instead.

First use the existing owner workflow to create/open the finite Study, prepare
its trial, review the exact composition and runtime, and issue an execution grant
to the intended agent. The agent needs current `inspect,execute` scopes. Scope
alone is not a grant. The SDK never creates a Study/trial/graph, continues a Study,
approves material, issues a grant, exposes test data or retries admission.

Select a trusted, provisioned `project_cli.py` and pin its source hash. Its
installation, import closure and agent requirements are caller-owned; selecting
this executable is explicit execution of trusted CLI code, not execution of the
untrusted package during validation. SDK conformance uses the SDK interpreter,
fixed argv, isolated Python, no shell and a sealed snapshot of the checked CLI
entry bytes. Linux `memfd` sealing prevents replacement or in-place modification
of the selected entry file from changing executed bytes. The explicitly trusted
CLI directory still owns its separate import/dependency closure; this SDK does
not claim to capture or sandbox that installation. The CLI owns AgentClient
credential checks, exact operation negotiation, current permissions and complete
segmented-artifact hash verification. No AgentClient/app module is imported into
the SDK process. No endpoint or credential is guessed or copied into argv.

```sh
python -m tuldok_extension_sdk conformance \
  --config /private/existing-agent-config.json \
  --cli /trusted/source-kit/project_cli.py --cli-sha256 EXACT_CLI_FILE_SHA256 \
  --selection /private/existing-trial-selection.json \
  --output /private/absent-conformance-output --deadline-seconds 180
```

The existing AgentClient config owns numeric-loopback endpoint, catalog and
private token-file selection. Selection is a closed JSON object; placeholders
below must be replaced by exact current returned identities:

```json
{
  "format": "extension_sdk_conformance_selection_v1",
  "catalog_id": "CATALOG_32_HEX",
  "actor_id": "CURRENT_AGENT_32_HEX",
  "project_id": "PROJECT_32_HEX",
  "study_id": "STUDY_32_HEX",
  "trial_id": "PREPARED_TRIAL_32_HEX",
  "revision": 3,
  "admission_epoch": 1,
  "approval_id": "EXISTING_EXACT_OWNER_GRANT_32_HEX",
  "request_key": "explicit-conformance-attempt-001",
  "expected": {
    "graph_id": "GRAPH_32_HEX",
    "graph_revision": 1,
    "material_sha256": "FULL_COMPOSITION_64_HEX",
    "model_sha256": "PUBLISHED_MODEL_64_HEX",
    "runtime_sha256": "CAPTURED_RUNTIME_REFERENCE_64_HEX",
    "task_sha256": "TASK_DEFINITION_64_HEX",
    "profile_definition_sha256": "EVALUATION_PROFILE_DEFINITION_64_HEX"
  }
}
```

The revision/epoch are the existing Study values. Expected identities are taken
from `studies.trial`, `recipes.material`, `models.material` and the current graph.
`profile_definition_sha256` is the composition's evaluation-profile definition
hash, not the resolved profile or retained profile-file hash. Runtime hash is the
composition's runtime reference. Material hash is the full composition hash,
which differs from its executable/material child hash.

The command checks actor/scopes, Study/trial membership, exact material, project,
graph, model, Task, profile and runtime before making exactly one `studies.admit`
call with the supplied grant and request key. The server remains the authority
for stale/revoked/expired/used grants and finite budgets. It then polls that Run,
reads its common public evidence and downloads every published artifact through
the same CLI using the exact whole-artifact hashes. Local identity/Blob closure
checks do not deserialize model state or re-run numerical inference. This bounded
initial conformance path accepts at most 128 artifacts, 8 MiB each, 64 MiB total.

Exit 0 returns machine JSON `format: extension_sdk_conformance_v1`,
`state: passed`, `contract.state: passed` and `numerical: not_evaluated`, with
exact Run/material identities and downloaded inventory. It establishes the
observed authorized Run/contract workflow only. Independent actual numerical
acceptance remains a separate gate.

Exit 2 returns `invalid`, `unsupported`, `stale`, `refused`, `unavailable`, `failed`
or `unknown`, with `contract.state: not_evaluated` and no numerical pass. An
uncertain admission, timeout or interruption never triggers another request key,
reapproval, cancellation or local execution. Inspect durable Study/Run state
before an explicit retry. A read revoked after admission can fail conformance
while the exact already-admitted server Run continues. Partial downloaded files
may remain in the explicitly selected new directory; no existing output is
replaced. The deadline bounds the client workflow, not server training custody. Bounded
pipe draining stops and reaps the CLI at 8 MiB stdout or 64 KiB stderr; it does
not wait for the full deadline before enforcing those stream bounds. Sealed CLI
execution is Linux-only; inert validation keeps its separate platform scope.

Focused SDK tests use clearly labelled representative transport and synthetic
states. Those tests prove refusal/delegation and byte/schema behavior; they are
not actual E2 execution or E3 A/B acceptance. A real public CLI fixture must run
this command separately before claiming product conformance. Complete numerical,
package/runtime notices and distribution rights remain separately owned.
# Explicit recovered publication collection

`python -m tuldok_extension_sdk collect-publication --config <agent-config>
--cli <project_cli.py> --cli-sha256 <reviewed-cli-sha256> --ref <result-ref.json>
--output <new-directory>` collects one exact attached recovered result through
the explicitly selected public CLI. The Ref comes from a separate owner action;
collection never admits, recovers or replays compute. All files must pass complete
SHA256 checks before `state: collected`; numerical acceptance remains
`not_evaluated`. An existing destination refuses and a failed partial collection
is retained for inspection. The command uses the existing private CLI/config
rules, finite command deadline and a 4 GiB total collection ceiling.

`compare-publication` uses the same `--config`, `--cli`, `--cli-sha256` and
`--deadline-seconds`, plus `--ref`, `--other-ref` and `--selection` JSON files.
It selects both exact checkpoint/evaluation/metric-definition identities and
`paired` or `side_by_side` mode. The host checks current authority and semantic
compatibility; the SDK correlates both labelled sides. It performs no admission,
recovery, model loading, inference or promotion. `numerical: not_evaluated`
describes scientific acceptance independently of returned comparison arithmetic.
