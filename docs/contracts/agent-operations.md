# Generic scoped local agent operations

This independently admitted component preserves PR53's generic operations and
optional SDK transport. Sequence import supports main's two-file v1 only. The
original three-file variant and its assertions remain on the original PR43/53
branches; whole original P6/G7 acceptance remains pending. This component is not
full original P6 acceptance.

`agent_api.discovery()` is the frozen f588 v1 compatibility projection. Its deterministic
SHA256 binds schemas, route projections, scope descriptions and limits. The
application exposes it at authenticated `GET /api/agent/operations` without
importing optional packages. New clients negotiate per-operation contracts below. MCP uses fixed underscore
names; dotted operation IDs remain stable registry identifiers. These schemas
bound transport input; current HTTP/domain owners decide source custody,
permissions, revisions, family independence and execution eligibility.

## Configuration and authority

The optional bridge reads `--config /absolute/private/config.json`. The closed
configuration has `endpoint`, `catalog_id`, `token_file`, and optional `timeout`.
Endpoint must be explicit `http://127.0.0.1:PORT` or `http://[::1]:PORT`.
Configuration and token files must be owned regular files, private to the current
user, without symlinks or hard links. Token path is absolute; credential contents
are never CLI arguments or logs. Bootstrap requires a live agent credential and
matching catalog, then negotiates compatible operations. Legacy-mode mutations
recheck exact authenticated discovery. Its HTTP authorization failures keep
the original validated status/code/message; registry_mismatch is reserved for a
successful discovery response whose registry differs. No
redirects, proxies, host discovery, arbitrary URLs, shell, catalog connection,
scheduler, credential issuance or automatic mutation retries exist in the bridge.

An owner prepares credentials, human reviews and exact execution grants through
existing HTTP/UI. Agent draft tools cannot claim human/programmatic review.
External submit requires the exact approval ID, graph revision, material digest
and request key. Identical-key receipt reconciliation is distinct from a new
attempt. Ordinary submit/retry remains owner-only and unexposed. Explicit test
exposure is supported with `expose-holdout`, not an owner-only fiction: it records
irreversible disclosure through the existing owner, has no preview/grant field,
and is not idempotent. A lost acknowledgement requires state inspection.

## Supported matrix

The registry is the machine-readable exact field/schema inventory:

| Operations | Existing domain surface |
| --- | --- |
| context.get, identity.get | workspace context and authenticated identity |
| projects.list/get/open/evidence | configured project roots and bounded declared evidence |
| project_snapshots.list/get/open | selected bounded v1/v2 snapshot inspection and registration; projects list/get/open stay v1-only; evidence and import accept current v2 |
| recipes.list/inspect | recipe declarations, exact expected recipe SHA |
| data.query/get/history/responses/preferences | all eight record kinds, existing metadata/history |
| data.audio/mesh/pointcloud/volume/scientific | existing bounded typed inspections/slices |
| data.import_image/text/audio/mesh/sequence/pointcloud/volume | bounded exact native imports |
| data.import_project_scientific/import_run_scientific | hash-bound existing owner reference capture |
| data.save_draft, responses.save_draft | CAS draft targets; all twelve annotation tasks |
| proposals.caption_list/get/decide, proposals.classification_list/get/decide | existing owner-started proposal reads and reject/apply_draft |
| releases.list/inputs/preview/freeze | canonical_v1 selection/family/review authority |
| graphs.list/get/create/create_external/save/clone/validate/preflight_external | known graph variants; disconnected drafts allowed, preflight canonical |
| run_inputs.list, runs.list/get/progress/predictions | current Run custody/progress/result projections |
| runs.submit_external/cancel/expose_test | exact granted execution, scoped cancellation/disclosure |
| runs.artifact_chunk | bounded stateless segment of a completed external Run artifact |

Registry restrictions narrower than HTTP are explicit: canonical freeze requires
preview_token; draft annotations only; graph edits describe known node parameter
variants rather than arbitrary future types; inline import bytes are at most
512 KiB aggregate and request at most1 MiB. Larger scientific references use
existing Project/Run capture limits, not client filesystem access. Sequence v1
requires run.json/frames.jsonl. For an exact three-file request containing
controls.json, the Python AgentClient raises `AgentAPIError` with code
`unsupported` and status400 before HTTP dispatch. Official-SDK stdio performs
argument prevalidation and reports JSON-RPC `-32602` (Invalid tool arguments)
before client dispatch. Both paths reject the request without an HTTP side
effect or reinterpretation as two-file input. All file payloads, including image,
are original raw base64 (not image data URLs); no scientific conversion occurs in the transport.

Unexposed: owner review/grant/admin operations, providers/model execution,
ordinary run submit/retry, backup/restore/runtime snapshots, bulk native import workflows,
saved-search/selection mutations, alternate export formats and general binary
asset/release downloads. Project evidence DOES have its existing HTTP route;
`projects.evidence` invokes it. Metadata parity does not promise binary rendering.

## Limits and errors

Schema validation uses the base pinned jsonschema4.26.0
Draft202012Validator, with no custom type checker or external schema retrieval.
Standard integer schemas reject bool but admit integral floats. Existing domain
owners may require actual Python integers and reject those floats; the bridge
forwards the original value without conversion. Schema validity is not domain
acceptance. App registry imports remain stdlib-only.
Strict JSON rejects duplicate fields, nonfinite numbers, surrogates/NUL and depth
above64. No trimming/coercion occurs during forwarding; owners retain semantics.

Default absolute HTTP deadline is120 seconds (configuration maximum300). Connect
is at most5 seconds. Header wait may use the remaining absolute deadline because
preflight can take longer than5 seconds before replying; a separate deadline
socket shutdown prevents header trickle extending the call. Payload blocks use
at most5 seconds or remaining deadline. This deliberately supersedes any draft
claim of a5-second complete header phase. Every call closes its own socket/timer.

HTTP receive bound16 MiB and MCP encoded response bound32 MiB are client limits,
with the HTTP bound also enforced for selected-contract responses, not existing
global headerless server caps. Large list/detail responses can exceed them and
are explicitly refused. Framing requires one Content-Length, JSON identity
encoding, no compression, chunked encoding or redirects. Execution errors retain
bounded safe HTTP status/code/message, returned as `{status,result}`. Unknown tools and registry argument-schema errors return JSON-RPC -32602
before SDK dispatch. Actual HTTP/domain or transport execution failures return
tool isError with the typed envelope; protocol failures are not tool failures.
Unknown commit is never retried automatically. MCP output schemas describe this
stable envelope; domain result semantics remain with their existing owners.

## Artifact byte parity

`runs.artifact_chunk` takes run_id/name/expected_sha256/offset/max_bytes (1..8 MiB).
The existing Runs segment owner verifies receipt/inventory and reads only the
selected interval, returning its hash and explicit whole-hash-unverified status.
Reassemble ordered offsets, verify each segment and verify the final complete
SHA256 against expected_sha256 BEFORE treating bytes as verified evidence or a
checkpoint. Same-size mutation outside the segment is not detected by that read.
No bridge cache, arbitrary output file, fake full verification or Library exists.
The unchanged full HTTP download uses the existing verified anonymous spool.

An8 MiB chunk encodes to11,184,812 base64 characters; duplicating structuredContent
in compatibility text uses22,369,624 characters plus bounded metadata, within32 MiB.
Other JSON can expand more: the protocol owner checks final encoded response size.
Tests must establish exact multichunk reconstruction and linear payload reads,
revocation and mutation failures, alongside legacy full-download behavior.

Historical full PR53 HTTP/MCP, benchmark and scientific evidence belongs to its
original source scope. Fresh generic-component tests, official-SDK retained
scientific cold reads and final composition CI are separate acceptance gates
owned by the scientific-integration plan.

## Per-operation capability negotiation

Authenticated `GET /api/agent/capabilities` returns a closed
`agent_capabilities_v1` envelope: `envelope_version:1`, current `catalog_id`,
`operations`, and `limits`. The manifest is at most1MiB, at most256 operations,
and at most4 locally implemented contracts per operation. Each operation has
`id`, `availability` (`available`, `unsupported`, `unavailable`) and `contracts`.
Each contract has `version`, `sha256`, `input_schema`, `output_schema`, `scopes`,
`authority`, `effects`, `retry` and `bounds`. Bounds name request/response bytes,
inline decoded bytes and JSON depth as positive safe integers. Schema fragments
must validate as closed locally interpreted Draft202012 schemas without references;
even ignored unknown operations must have valid bounded declarations. Discovery
does not confer permission or claim an installed model/runtime capability.

`AgentClient` selects the highest exact locally implemented ID/version/contract
intersection. A valid unknown addition is ignored. A mismatched known operation
is unavailable independently; compatible operations remain usable. Malformed
envelopes, duplicate IDs/versions, external references and catalog/authentication
failures refuse bootstrap. No schema-subsumption solver or remote route/code load
exists. The digest binds schemas, method/path/query/injected fields, binary
projection, MCP name, scopes, effects, retry and bounds; schema documentation
prose is excluded. A changed semantic meaning requires a new operation version.

Selected HTTP calls carry one internal header:
`Tuldok-Operation-Contract: operation_id/version/sha256`. The server checks
method/path/header identity, strict JSON, complete selected schema, query fields,
injected fields and canonical projection before domain entry. Duplicate headers,
query keys, JSON fields, unsupported framing or a discovery/dispatch contract
race refuse without a domain mutation or execution-grant consumption. Current
credentials, scopes, CAS, exact grants and exposure policy remain owner checks.
Selected JSON response schema and actual encoded16MiB size are checked before
delivery. `contract_output`502 after a mutation can leave a committed result;
inspect durable state and reconcile its receipt before another attempt.

New-only registered routes require selection. Retained headerless routes keep
their existing wider HTTP grammar. A new branch sharing any retained route
template (including static paths overlapping an old placeholder) must call
`require_selection(selection, new_operation_id)` before its domain owner; a
legacy operation's header cannot authorize the new variant. P1 advertises no new
product operation. Later operation additions must test this dispatch obligation.

Only a definite missing negotiation route/method permits fallback:404 with
`route_not_found`, the exact old404 `Not found.` response without a code, or405
with `method_not_allowed`. Fallback then requires exact frozen v1 discovery.
Authentication/server errors, ambiguous404 or malformed capabilities never
trigger fallback. The frozen56-operation digest is
`cb070a69ebd35b48e4f95a57ca01647c75bd7567521429e49efc3a3a1daebae8`.
Legacy HTTP16MiB/MCP32MiB limits and grammar remain unchanged; negotiated manifest
and request caps are1MiB and response cap16MiB. The16MiB choice preserves an
existing8MiB artifact segment's11,184,812 base64 characters. Retire the projection
only through an explicit supported-installation inventory and owned cutover.

MCP lists and validates only the selected contracts via
`AgentClient.selected_contracts()`/`tool_definitions()`; CLI calls use the same
client. Neither retries automatically. Receipt reconciliation uses the original
actor, exact body and request key. Before a future submit version changes meaning,
its durable receipt must bind that selected semantic contract; P1 supports only
the original submit meaning and claims no cross-version replay.

The actual retained f588 client and HTTP-handler source fixtures are tested
against both old and new peers. New CLI/MCP lost-ack tests execute a neutral
byte-copy Run through actual PostgreSQL, Access and custody owners. These tests
qualify transport/reconciliation, not model training or scientific correctness.

Output schemas check each operation's success top-level kind and identity fields,
and distinguish HTTP error envelopes from successful results. Nested scientific
or runtime documents are preserved as owner evidence, not independently certified
by these schemas. Artifact segment output alone is fully closed and bounded;
client correlation checks echoed Run/name/hash/offset, decoded size and segment
SHA. `verify_artifact` provides bounded whole-file reassembly verification with
an optional caller callback. Callback bytes are provisional until successful
return and must be discarded on error; it never opens a filesystem path.

Response errors without a legacy code map to `http_error`; malformed/non-string/
secret-bearing code fields are transport failures. HTTP output objects posing as
success (`200` with only an error body) fail the operation output schema. Raw
tracebacks or arbitrary response formats are not accepted as authoritative errors.

## Negotiated project snapshots and bound authoring

Ordinary agents use three additive snapshot operations through the same selected
HTTP, CLI and MCP registry. List remains version1; get/open support versions1
and2 with exact per-version output schemas:

- `project_snapshots.list` accepts optional `cursor` and `limit` (1–20, default20).
  Its closed page contains `mode:inspection`, configured root aliases, immutable
  v1/v2 project summaries, `limit` and nullable `next_cursor`. Pagination uses
  project ID order. Summaries explicitly identify `schema_version`.
- `project_snapshots.get` accepts exactly `project_id`. Its closed result
  reports saved declarations and current bounded inspection; project schema v2
  adds the inert extension catalog. Contract version2 adds an optional external `activity` observation from
  ordinary evidence id `activity`, with measured hash and explicit external
  authority; unavailable activity preserves the rest of inspection. It does not
  return captured source blobs. Version1 retains its installed closed result
  without `activity`, even when that evidence reference exists.
- `project_snapshots.open` accepts exactly `root` and `manifest_path` and requires
  inspect plus edit. It registers immutable metadata and returns inspection.
  Root is a configured alias; callers cannot nominate an absolute root.

List/get require current inspect authority. Readers retain pinned root identity,
descriptor-relative no-follow access, aggregate byte bounds and exact manifest
and source integrity checks. Cached capabilities convey no authority after
credential revocation. Package declaration, host compatibility, runtime evidence
and execution permission remain distinct facets. Inspection never imports source,
probes a runtime or executes a process. Unselected owner-browser snapshot routes
and the separate upstream v1 discovery documents retain their existing shapes
and owner gates. Existing `projects.evidence` and `data.import_project_scientific`
operations accept current project v2 through the same bounded evidence and
strict source-capture owners; no snapshot alias or historical decoder is added.

The following explicit new versions permit static authoring from project-v2
source for ordinary scoped agents: `recipes.inspect/3` and `/4`,
`graphs.create_external/2`, `graphs.preflight_external/2`, `models.publish/2`
and `studies.prepare_trial/2`. The trusted selected contract header controls this
boundary; request-body flags cannot opt into it. Earlier selected versions retain
their owner-only project-v2 fresh inspection/capture behavior and exact contract
hashes. Verified prior Model publications and exact actor/key/body Trial receipts
retain their existing current-authorized replay semantics, without new capture.
Legacy `graphs.validate/1` and `runs.submit_external/1` retain owner-only fresh
project-v2 source access; new authoring uses preflight/2 and unchanged Study
admission instead. Project-v1 behavior is unchanged.
Source capture reconciliation and orphan adoption remain
owner-only even with the new publication version.

Recipe inspection v4 adds `managed_torch_python_v1` to the declared recipe and
provider runtime variants. Versions2/3 retain their published CPU schemas and
exact hashes; older selected inspection versions return `unsupported` for a
managed Torch recipe. Inspection is inert and conveys no runtime availability
or execution authority.

An agent may inspect declared parameters, create/publish a captured Model, create
and preflight a bound graph, and prepare a Trial in an owner-created Study.
Study creation, policy/budget changes, continuation and approval remain owner
actions. These authoring calls do not open an epoch, create an execution grant,
reserve an attempt or submit a Run. `studies.admit/1` is unchanged: ordinary
execution still requires the owner's exact finite budget, open epoch and grant.
Static source inspection and Trial preparation establish no runtime, numerical
or hardware acceptance.

## Optional interface observations

HTTP, CLI and MCP boundary observations remain operator opt-in and separate from
operation contracts and required transactional audit. New boundaries require an
explicit fresh private v2 store; existing MCP v1 stores are preserved. No headers,
operation arguments, schemas or domain results gain telemetry requirements.
The [shared observation contract](mcp-observer.md#shared-interface-observation-v2)
owns the closed projection, independent health reader, private retention and
actual delivery semantics. Passive records cannot establish a domain commit,
Run completion, client receipt or permission to retry.


Current bound recipe inspection projects `managed_torch_python_v1` in both the
recipe runtime and selected provider declaration, alongside the existing captured
CPU profile. The exact negotiated output contract changes with that current
vocabulary. Source inspection remains inert; declaration does not prove runtime
availability, grant permission or numerical acceptance. The current Project v2
reader also accepts an ordinary managed recipe, preserving exact manifest/source
capture and the current operation scope gate.
