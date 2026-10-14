# Generic scoped local agent operations v1

This independently admitted component preserves PR53's generic operations and
optional SDK transport. Sequence import supports main's two-file v1 only. The
original three-file variant and its assertions remain on the original PR43/53
branches; whole original P6/G7 acceptance remains pending. This component is not
full original P6 acceptance.

`agent_api.discovery()` is the versioned operation registry. Its deterministic
SHA256 binds schemas, route projections, scope descriptions and limits. The
application exposes it at authenticated `GET /api/agent/operations` without
importing optional packages. MCP uses the same definitions with fixed underscore
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
matching catalog and registry. Mutations recheck authenticated discovery. Its HTTP authorization failures keep
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
ordinary run submit/retry, backup/restore/snapshots, bulk native import workflows,
saved-search/selection mutations, alternate export formats and general binary
asset/release downloads. Project evidence DOES have its existing HTTP route;
`projects.evidence` invokes it. Metadata parity does not promise binary rendering.

## Limits and errors

Optional schema validation uses the standard pinned jsonschema
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
not existing global server caps. Large list/detail responses can exceed them and
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
