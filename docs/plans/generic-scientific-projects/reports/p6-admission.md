# P6 admission: typed operations through existing HTTP owners

Admitted for isolated source preparation on 2026-10-13 by the task integration
owner. Canonical plan: `docs/plans/generic-scientific-projects/plan.md`.
Worktree `/workspace/Tuldok-p6`, branch `feature/scoped-agent-operations-20261013`,
base PR52 source checkpoint `d191e681011756d7d3204604a410fe5619b5c559`.
Main was freshly fetched and remains `c522bf6b5eaf94d89811578c9e73aecfdba4ef9e`;
PR32/33 and PR38–52 remain unmerged drafts. No merge or deployment is admitted.

P5c's original evaluation continues against frozen `/workspace/Tuldok-p5c`.
This sequencing amendment admits independent P6 source preparation only: no
edits to that worktree's runtime/UI/adapter sources, no package installation or
competing tests during its benchmark. Dependent actual P6 workflow qualification
waits for P5c actual gates and final regression/CI; any owning fixes propagate
before acceptance. Root preserves both worktrees and publishes separate drafts.
The active integration slice remains P5c qualification until those gates close.

Current checkpoint: implementation and focused checks are recorded in
[p6-verification.md](p6-verification.md); final acceptance remains pending.
The initial source-only restriction below is retained as sequencing history;
focused tests began only after the P5c benchmark completed and drained.

The named matrix below, including scoped `runs.expose_test`, is admitted.
The stateless segment contract explicitly does not verify whole-file hashes.
Use explicit underscore MCP tool names mapped one-to-one to dotted operation IDs.
Registry version and deterministic digest identify the transport contract only;
the bridge checks the authenticated server discovery before mutations. Domain
identity, validation, authorization and lifecycle retain their existing owners.

Dependency selection: adopt optional official `mcp==1.30.0` low-level server
(Python >=3.10, MIT, supports protocol 2025-06-18) and `jsonschema==4.26.0`
Draft202012Validator. The independent review compared a local stdio
implementation: it would own version negotiation, request lifecycle, typed
protocol models and schema semantics indefinitely, with no independent corpus
already present here. The maintained SDK delegates those standardized semantics;
Tuldok still owns strict bounded framing, fixed loopback HTTP, scopes and errors.
Do not create a custom JSON Schema evaluator. Record the exact jsonschema pin,
resolution provenance and remaining SDK controls in the dependency review before
protocol implementation. App/discovery imports must remain usable without these
optional packages; no automatic installation or training-runtime mutation.

Exact ownership: root owns app.py discovery/segment route, README, plan/reports
and public end-to-end qualification. Root also owns `.github/workflows/tests.yml`
for an explicit isolated optional-SDK gate; base app tests retain their original
dependencies. Registry/client owner owns agent_api.py,
its contract and focused tests; protocol owner owns mcp_stdio.py, optional pinned
requirements and protocol tests; Runs owner owns runs.py segment method and
focused artifact-segment tests. Canonical data owners remain unchanged unless a
concrete defect is separately admitted. Shared app/routes have one root owner.
All focused and full verification remains required, with no source-only
completion claim. No new scheduler, catalog, credential issuer or grant authority.

## Boundary and protocol

Add a tools-only local stdio MCP adapter pinned to protocol 2025-06-18. It is a
client of one explicitly configured existing loopback Tuldok HTTP server. It never
constructs Dataset, opens the catalog, imports a domain owner, starts a worker,
creates a scheduler, discovers hosts, or runs shell commands. Owner approval,
human review, credential issuance and revocation remain existing authenticated
HTTP/UI authority; documentation covers their explicit setup. Agent tools cannot
mint credentials, approve grants, or claim human review. A credential with execute
scope can use only the already admitted external-submit exception, consuming an
exact owner grant. Existing ordinary execute guards stay owner-only.

Use one versioned operation registry in agent_api.py: operation name, exact JSON
input/output envelope schema, required scope, owner restriction, side effects,
approval/idempotency/revision behavior, fixed method/path/query/body projection,
and response kind. No arbitrary URL/method/headers/body forwarding tool. Publish
that same registry at authenticated GET /api/agent/operations, and project its
tool definitions into MCP tools/list. Existing HTTP route/domain validation stays
canonical. Registry schema checking covers transport shape and bounds; do not
reimplement scientific validation or silently accept arbitrary body objects.
Registry does not imply every legacy provider/network/admin endpoint is exposed.
Publish an explicit supported-operation matrix and list owner-only exclusions.

Server capabilities exactly {tools:{}}; no resources/prompts/roots/sampling,
subscriptions, logging notifications, or tool-list change capability. Parse one
UTF-8 JSON-RPC object per newline, reject duplicate keys/nonfinite values/batches,
cap input line at 1MiB and JSON depth, and write only protocol responses to stdout.
Initialize before tools; await notifications/initialized. Support ping, tools/list
and tools/call; reject duplicate initialize and out-of-state requests. Ignore
unknown notifications without a response; reject unknown request methods. Offer
only 2025-06-18 when another version is requested (standard negotiation); client
must decide compatibility. EOF exits without cancelling durable Runs. Sequential
bounded calls are sufficient initially; document that cancellation of a durable
Run is its explicit run.cancel operation, not termination of this bridge.

Official primary references verified 2026-10-13 (pinned version, not latest alias):
- https://modelcontextprotocol.io/specification/2025-06-18/basic/lifecycle
- https://modelcontextprotocol.io/specification/2025-06-18/basic/transports
- https://modelcontextprotocol.io/specification/2025-06-18/server/tools

## HTTP transport and credentials

Configure fixed http://127.0.0.1:PORT or http://[::1]:PORT, no hostname/DNS,
userinfo, query, fragment, base-path or non-loopback address. Construct paths
from registry plus individually encoded validated segments. Use direct
http.client connections, no proxy environment or redirects; reject any3xx.
Use finite connect/read and absolute call deadlines, response length limits,
identity encoding only, and reject malformed/truncated HTTP framing. A private
configuration file may name the endpoint and expected catalog identity. Read
bearer credential from an explicitly supplied inherited private descriptor or
owner-only nofollow regular token file, bounded4KiB; never command-line token,
stdout/stderr token echo, generic environment dump or request-header logs.
Validate the identity against /api/access/session and catalog against workspace
context; require agent kind for the initial adapter to avoid accidentally giving
an agent session owner powers. Revocation is still rechecked by every HTTP call.
Neither startup inspection nor cached tool metadata grants later authorization.

Existing app.py credential boundary is shared: GET requires inspect;
POST binds bearer and domain guards enforce scopes. Mixed cookie/bearer is403,
missing/malformed bearer401. Domain errors retain {error,code} and status;
commit_unknown/storage are503 and must never trigger automatic mutation retry.
A lost response to submit is resolved by explicit same request_key/body retry
against existing idempotency receipts, not a newly generated request key.

## Admitted operation matrix

Source inspected: /workspace/Tuldok-p5c/app.py GET/POST workspace and workbench
routes, projects.py, workbench.py, dataset_releases.py, pipeline.py, runs.py and
native asset owners. These are admitted operation names. Implementation and focused checks are now
recorded in the verification report; final qualification remains pending.
Prefix paths below with /api. IDs and fixed route segments are encoded separately.
Every row becomes named tools with closed schemas; no generic HTTP dispatch tool.
Scope column is the domain minimum in addition to inspect required for bootstrap.

| Exact proposed operations | Existing method/path and canonical owner | Scope / bounded support |
| --- | --- | --- |
| context.get; identity.get | GET workspace/context; GET access/session | inspect; omit secrets, require same configured catalog and agent kind |
| projects.list; projects.get; projects.open | GET workspace/projects; GET workspace/projects/:id; POST workspace/projects | inspect/edit; open exactly {root,manifest_path}, root must already be owner-configured |
| projects.evidence | GET workspace/projects/:id/evidence/:ref | inspect; Projects.evidence bounded declared text/Markdown/JSON |
| recipes.list; recipes.inspect | GET workspace/definitions; GET workspace/projects/:id/recipes/:ref?expected_sha256= | inspect; Pipelines.definitions/inspect_external_recipe, no native probe or execution |
| data.query; data.get; data.history | GET workbench/records; records/:id; history/:id | inspect; Workbench.query/get/history; query offset>=0, limit1..100 and q/kind/review/sort/task/label/group/rights only |
| data.audio; data.mesh; data.pointcloud | GET workbench/audio-inspection/:id; mesh-inspection/:id; pointcloud-inspection/:id | inspect; respective immutable asset inspect owner |
| data.volume; data.scientific | GET workbench/volume-inspection/:id?axis=&index=; records/:id/scientific?frame=&field=&axis=&index= | inspect; bounded owner slice, no full array expansion |
| data.responses; data.preferences | GET workbench/records/:id/responses; records/:id/preferences | inspect; Workbench.responses/Preferences.list |
| data.import_image; data.import_text | POST workbench/import | edit; Workbench.import_asset; closed kind-specific union, image base64/text plus name/rights/groups/parents |
| data.import_audio; data.import_mesh; data.import_sequence; data.import_pointcloud; data.import_volume | POST workbench/audio-import; mesh-import; sequence-import; pointcloud-import; volume-import | edit; existing native parser owner; exact wav or files envelope with name/rights/groups/parents, no invented bundle shape |
| data.import_project_scientific; data.import_run_scientific | POST workspace/projects/:id/import-data/:ref; workspace/runs/:id/import-data/:artifact | edit+inspect; ScientificFields.admit/admit_run_artifact through Projects/Runs custody, expected_sha256 required, optional name/rights/groups/parents |
| data.save_draft | POST workbench/records/:id | edit; Workbench.save; exact revision/source_revision/task/annotation/groups and review constrained to draft, subtype-specific annotation schema |
| responses.save_draft | POST workbench/responses | edit; save_response existing id/prompt_id/revision/parent_revision/source_revision/completion/review envelope, review=draft |
| proposals.caption_list; proposals.caption_get; proposals.caption_decide | GET workbench/caption-proposals[/id]; POST workbench/caption-proposals/decide/:id | inspect/edit; completed owner-started proposals only, decision reject or apply_draft with exact revision |
| proposals.classification_list; proposals.classification_get; proposals.classification_decide | GET workbench/text-classification-proposals[/id]; POST workbench/text-classification-proposals/decide/:id | inspect/edit; reject or apply_draft; latter binds exact frozen labels and revision |
| releases.list; releases.inputs; releases.preview; releases.freeze | GET workspace/releases; GET workbench/releases/input-candidates; POST workbench/releases/preview; POST workbench/releases | inspect/freeze; initial advertised format canonical_v1 only, exact selected revisions/items/ratios/seed and required preview_token for freeze; same family/review validation |
| graphs.list; graphs.get; graphs.create; graphs.create_external; graphs.save; graphs.clone | GET workspace/graphs[/id]; POST workspace/graphs[/external]; POST workspace/graphs/:id[/clone] | inspect/edit; Pipelines methods; closed graph variants, CAS save revision+document, existing recipe/node limits |
| graphs.validate; graphs.preflight_external | POST workspace/graphs/:id/validate; /preflight-external | inspect; exact revision, existing owner; native preflight execute guard can deny agent, never bypass it |
| run_inputs.list | GET workspace/run-artifact-inputs | inspect; Runs.input_candidates, receipt-only status preserved, max100 completed candidates as existing owner |
| runs.list; runs.get; runs.progress; runs.predictions | GET workspace/runs[/id]; runs/:id/progress; runs/:id/predictions?split= | inspect; Runs existing owners, progress/summary is current bounded projection, held-out denial preserved |
| runs.submit_external | POST workspace/runs/submit-external | inspect+execute and exact existing actor/material owner grant; request_key/graph_id/graph_revision/expected_digest/approval_id ALL required by agent schema |
| runs.cancel | POST workspace/runs/:id/cancel {} | cancel; same Runs cancellation/drain state, no helper or process access |
| runs.expose_test | POST workspace/runs/:id/expose-test {reason} | expose-holdout; exact existing Runs.expose_test disclosure and audit, no owner-only or new grant requirement |
| runs.artifact_chunk | proposed POST workspace/runs/:id/artifact-segment/:name | inspect; NEW narrow Runs read owner described below; no arbitrary filename/path or bridge file write |

Data query/get cover all eight kinds: image, text, audio, mesh, sequence, pointcloud,
volume, field_sequence. Image/text/sequence inspection is the actual record's
metadata/annotation and existing declared source metadata; there is no invented
sequence-frame HTTP view. Mesh/point/volume/audio/scientific typed views retain the
existing owner limits. This does not promise a full image/audio binary rendering
tool. All twelve existing TASKS must have exact draft annotation schemas before
claiming draft-edit parity: image_detection/image_classification/image_caption,
text_classification/text_entities/text_corpus, sequence_transport/mesh_geometry,
audio_timed/pointcloud_geometry/volume_grid/field_sequence_fields. No scientific
schema copies: registry describes request shapes, owners validate semantics.

Initial stdio request cap stays1MiB. Inline imports are explicitly limited to
512KiB aggregate decoded original bytes (including all files) and total request
under1MiB; this is useful for bounded native fixtures, not parity for arbitrary
large uploads. Large scientific input uses existing manifest-declared Project or
completed Run references and server-side hash verification, with existing40MiB
per-input cap. No tool accepts local filesystem paths except the already-owned
project root alias/manifest relative reference. Refusal must name the supported
bound and route the user to existing HTTP/UI; never claim all HTTP upload sizes.

Native file union must come directly from current parsers: mesh.ply+mesh.json;
points.ply+points.json; volume.npy+volume.json; sequence run.json+frames.jsonl forv1 and additionally controls.json forv2
(the prepare_files closed variants), and
wav for audio. No multipart protocol or generic source-reading endpoint. Tests must cover both
sequence variants without weakening the native contract or exceeding inline caps.

Explicit HTTP/UI-only exclusions: owner human review, preference approval,
execution-grant creation/revocation, credential administration/bootstrap,
provider discovery/configuration, proposal-start/native model execution,
ordinary runs.submit/retry, backup/restore/runtime snapshot maintenance,
procedural generation, native text/detection/caption bulk import workflows,
saved search/selection mutations and alternate export projections. Holdout
exposure is supported ONLY through its separately issued expose-holdout scope;
test predictions remain denied until the existing disclosure owner permits them. These exclusions must appear in the
published registry contract. No tools named approve/review pretending agent draft
application is human acceptance. Owner review and exact grant setup are exercised
through authenticated UI/HTTP in QA, never delegated through MCP.

Project evidence has the existing GET /api/workspace/projects/:id/evidence/:ref
route, owned by Projects.evidence. The admitted projects.evidence operation
exposes that bounded declared text/Markdown/JSON read; no arbitrary file read is added. Release ZIP downloads and record-source binary
HTTP endpoints remain existing HTTP-only initially; P6 artifact-byte acceptance
is explicitly completed external Run artifacts, not every binary endpoint.

## Artifact decision: owner segments with client whole-file verification

CHOSEN proposal: add one bounded, authenticated, stateless Runs.artifact_segment
owner and matching HTTP operation. Preserve existing full download route and
Runs.open_artifact verified anonymous spool completely unchanged. Do not implement
a bridge cache, managed download file, opaque path token, second artifact store,
or Library integration. No arbitrary output path is accepted or returned.

Request exactly {expected_sha256,offset,max_bytes}; name/run_id are path params.
Require SHA256 lowercase64hex, offset integer0..artifactbytes, max_bytes1..8MiB.
Initial support only completed external recipes and declared payload names.
Whole artifact cap is the admitted output rule (currently512MiB for large,
64MiB for old); aggregate Run output may be4GiB. No generic Range interpretation.
This is a JSON operation, not a falsely advertised HTTP206 implementation.

The Runs owner checks catalog access, completed record/material/spec, approved
output declaration, retained manifest/custody and current exact inventory using
existing _external_inventory. Bind expected_sha256 to the authoritative declared
whole SHA. Open selected file nofollow, require currentuid/regular/nlink1/exact
size, pread only requested bounded region, compare fstat before/after plus named
inode identity. Return bytes encoded once by HTTP or bridge; choose one encoding
layer in implementation. Closed response:
{run_id,name,expected_sha256,total_bytes,media_type,offset,bytes,next_offset,eof,
 segment_sha256,data_base64,verification:"segment_read_whole_hash_unverified"}.
Segment SHA hashes the returned bytes only. No claim that a range read proves the
whole payload still matches the retained receipt. A same-size changed segment
can be returned with its actual segment hash; final whole-file client hashing
MUST fail against expected_sha256. This limitation is deliberate and visible.

Client reassembles in exact offsets with stable identity/total, verifies each
segment hash, then verifies final whole SHA before treating the artifact as
verified or usable as checkpoint/evidence. Provide a bounded test client example
that streams hashes; it need not write a file. MCP host itself does not silently
assemble/download arbitrary paths. If downstream clients cannot honor this
contract they must use the existing full verified HTTP download instead. Tests
must demonstrate mutation/revocation between chunks cannot yield final accepted
whole content. Empty file and offset==EOF yield zero bytes/eof with emptysegment
SHA. Reject offset>EOF, malformed ints/bools, growth/truncation, nonregular paths.

Complexity is linear total payload reads plus O(chunks*smallinventory), with no
O(chunks*payload) whole-file hash.8MiB keeps a200MiB artifact to25 calls; base64 is
~11.2MB per maximum response. Set explicit16MiB HTTP JSON envelope cap and32MiB
MCP response cap because compatibility text serialization duplicates the same
structuredContent object, including base64. Both are finite and distinct from
1MiB request cap. Exact deadline and response limits must be published; no silent
truncation. Existing tools returning HTTP JSON exceeding16MiB fail explicitly;
they are not claimed unbounded parity. Avoid accidental unbounded third copies.

Rejected alternatives: fetching the existing full verified spool per8MiB chunk
would read/hash200MiB25times (~5GiB), plus server spool writes;1MiB would cost
~40GiB. A bridge-owned temporary file amortizes this but adds lifecycle/credential
revocation/cache custody and disk ownership absent from current plan. A single
full artifact base64 tool exceeds honest bounded response limits. New stateless
segments are the smallest explicit tradeoff while the full verified HTTP route
remains available.

## Errors and tests

JSON-RPC parse/envelope/method/schema failures use protocol errors. Valid tool
calls rejected by HTTP return isError:true and structuredContent with original
HTTP status/code/error; include equivalent text content for client compatibility.
Successful structuredContent uses a stable object envelope {status,result} even
if HTTP result is a list. Do not put raw server HTML, credentials or Python
tracebacks in errors; bound message sizes. No automatic replay of mutations.

Tests required before G5 complete:
1. Real subprocess stdio lifecycle, negotiation, ping, list schema, call; malformed,
   duplicate/nonfinite/deep/oversized JSON, unknown methods/tools, notifications,
   EOF, stdout cleanliness and no secrets in errors/logs.
2. Real authenticated loopback HTTP plus same domain catalog: every registry
   operation schema has a tested route projection; tool list equals HTTP discovery.
   End-to-end project/data/draft-review-by-owner/freeze/graph/preflight/owner grant/
   agent submit/status/artifact/import workflow; compare domain digests/evidence,
   not actor-specific IDs/timestamps. No second scheduler or Dataset in adapter.
3. Different agent scopes, revoked/expired/wrong-catalog credentials; forged human
   review/owner identity; approval wrong actor/material/stale revision/reuse; stale
   graph save; owner-only setup excluded. Assert no DB write or native spawn.
4. Lost acknowledgement/commit_unknown: same-key replay returns same durable Run;
   different body same key conflicts; unknown custody stays fenced. Durable Run
   survives MCP disconnect. Explicit cancellation uses sole Runs owner.
5. Artifact binary/empty/multichunk exact reassembly including >8MiB authored payload,
   incorrect expected digest, mutated/truncated content, final whole-SHA rejection,
   response overflow, chunk bounds, denied/nonexternal routes, revoked credential
   between chunks, no HTTP Range assumption. Count actual bytes read to prove
   linear payload reads; old full verified downloads and old-profile guards unchanged.
6. Mock hostile transport redirection/proxy env/non-loopback URL/header injection,
   response-size/deadline/framing failures, source config mode/symlink rejection.

Proposed write set after admission: agent_api.py (registry + bounded HTTP client),
mcp_stdio.py (stdio protocol only), docs/contracts/agent-operations.md, versioned
schema artifact if not generated directly, tests/test_agent_api.py,
tests/test_mcp_stdio.py, app.py authenticated discovery and fixed segment route, runs.py narrow segment owner
with tests/test_artifact_segments.py, README local setup,
P6 plan/report. Existing owner fixes only if tests reveal a concrete parity gap;
no new database tables, runtime profile changes, executor, package installation,
or network/provider discovery. The admitted supported-operation matrix bounds this implementation; one
scientific checkpoint does not establish all legacy surface parity.

## Protocol conformance details and admission gaps

Official lifecycle confirms initialize is first, version negotiation precedes
initialized, and transport close ends stdio without a special shutdown method.
The fixed-version server responds2025-06-18 to a different requested version;
that is negotiation, not pretending it implements the client's requested one.
Official tools require tools capability, schemas and distinct protocol/tool
execution errors; structuredContent must satisfy declared outputSchema and
serialized text is recommended for compatibility. Stdio uses UTF-8 newline
framing with protocol-only stdout. The HTTP hop here is ordinary existing Tuldok
HTTP, NOT MCP StreamableHTTP; do not claim MCP HTTP/session/SSE conformance.

Tool listing is a small fixed inventory: return all supported definitions with no
nextCursor; reject nonempty unknown cursor. Tool schemas use additionalProperties
false recursively for transport-owned closed envelopes. JSON-RPC IDs permit
integer/string IDs according to pinned base spec, never bool; preserve exactID.
Protocol notifications receive no response; unknown method requests do. A tool
annotation cannot authorize a scope; HTTP domain checks remain live authority.

Root admitted this named matrix and segment semantics above. The detailed
dependency review fixes SDK/schema choices before their implementation. Remaining exact schemas (graph variants, annotation variants and
canonical release selections) are mechanical source-derived work, not authority
decisions. Registry-to-owner parity tests must cover each advertised subtype,
plus real agent workflow with separate owner UI review/grant. Initial bridge has
no model dependency, catalog migration, scheduler or snapshot changes. Optional
agent packages were subsequently installed only in the isolated P6 QA environment
as recorded in the dependency report. This admission itself changed no runtime
code or real evaluation; current implementation evidence is in p6-verification.md.

## Admitted canonical-plan amendment record (2026-10-13 follow-up)

The integration owner applied this amendment in the canonical plan. Original replacement wording follows for decision traceability. Replace the G5 requirement cell with:

> Agent and UI clients reach the same domain owners for the admitted operation
> matrix and receive equivalent domain evidence when exercising equivalent
> authority. Owner-only setup/review/grant actions remain separate. Explicitly
> excluded HTTP capabilities are recorded, not counted as MCP parity. Stale
> requests, forged human review, unauthorized execution, path escape and approval
> reuse fail before side effects.

Replace the P6 Goal with:

> An agent discovers and controls the qualified workflow through the admitted
> typed operation matrix, with the same domain outcomes as equivalent authorized
> HTTP/UI actions. Capability parity means shared semantics and authorization
> within that matrix, not delegation of every UI privilege or legacy endpoint.

Replace the P6 Tasks with:

> Publish the versioned supported-operation and exclusion matrix; project/data/
> recipe discovery; bounded queries and typed draft mutations; canonical release
> preview/freeze; graph editing/preflight; exact-grant idempotent external submit,
> status/progress and scoped cancellation; bound provenance and artifact segments.
> Document owner credential setup/revocation, review and exact execution grants
> through existing HTTP/UI. Include explicit test exposure through the existing
> expose-holdout scope and exact reason contract. Ordinary retry remains existing
> owner-only HTTP/UI. A transport reconnect or submit
> receipt reconciliation never creates a new attempt or approval. Tool schemas
> identify bounds, side effects and required authority. Reuse shared validation
> and errors; no direct DB or file-management convenience operations.

Replace the P6 Acceptance gate with:

> Complete G5 against the admitted matrix: equivalent authorized agent and UI
> actions produce equivalent domain evidence, and a real workflow crosses owner
> review/grant checkpoints without assigning owner identity to the agent.
> Exercise revisions, lost acknowledgements, revocation, human-review spoofing,
> approval reuse and exact artifact reassembly through public transports.
> Prove excluded capabilities remain absent from MCP; verify ordinary retry
> remains owner-only and test exposure preserves its explicit scope, irreversible
> audit and exact request semantics through both transports. No new actor-specific
> bypass.

At the public-interface architecture paragraph (current plan.md:106), append:

> This is the domain capability inventory, not a promise that every capability
> is delegated to the initial agent transport. P6's admitted matrix declares its
> supported bounded subset and exclusions. Existing HTTP operations retain their
> own scopes and owner restrictions; MCP omissions do not silently revoke them.

Source distinction requiring accuracy: runs.py:1011 ordinary retry has
execute+owner_only. runs.py:1621 expose_test requires expose-holdout with NO
owner_only restriction; access.py:18 permits that scope on agent credentials.
Preserve both policies. External retry means a user-requested new external submit
with a new request_key and an exact valid owner grant; the bridge has no hidden
retry/fresh-grant policy. Replaying the SAME admitted request_key/body is only
receipt reconciliation, never a new attempt.

### Exact runs.expose_test transport contract

MCP arguments closed object {run_id,reason}, both required; run_id lowercase
32hex; reason string1..500 characters, trimmed nonempty, no surrogate codepoints.
Route POST /api/workspace/runs/:run_id/expose-test; body exactly {reason}. Canonical
owner remains Runs.expose_test with @authorized('expose-holdout',...). No new
preview token, execution approval_id, revision or request_key is accepted: the
existing route has none. Do not add owner_only or synthetic approval semantics.

Existing owner loads the Run, refuses external recipes and integrity-validation
Runs, fully verifies its completed published artifacts, then transactionally
records each test source exposure plus the actor audit and Run exposure event.
Response contains id/run_id/release_id/created_at/reason and
 test_exposure:{exposed:true,event_count}. Tool description says it irreversibly
records disclosure of held-out test results and requires explicitly issued
expose-holdout scope. readOnlyHint=false, idempotentHint=false; annotate the
irreversible side effect. Calling again can create another audit/event, so NO
automatic retries after a lost acknowledgement; inspect runs.get exposure state
and audit evidence first. Semantic prediction permission remains owned by Runs.

Required tests: no scope ->403/no exposure mutation; eligible completed classifier
with scope -> persisted same domain exposure and subsequent test read; exact
reason and closed fields; external/validation/noncompleted refusal; artifact
tamper refusal; revoked credential; lost response causes no bridge replay. Owner
review/grant tools stay excluded. This restores the original accepted exposure
capability without broadening the service's authorization.

## Pinned tool names and output-size evidence

Pinned official schema inspected at:
https://raw.githubusercontent.com/modelcontextprotocol/modelcontextprotocol/2025-06-18/schema/2025-06-18/schema.ts
Tool extends BaseMetadata (lines763ff); BaseMetadata.name is string (line260),
without a regular-expression restriction. The pinned tools specification also
requires unique names, not a no-dot rule. Therefore dotted registry names are
compatible with this pinned schema. This is not a guarantee every downstream
model tool wrapper permits dots. Minimal portability choice: freeze registry
operation_id as the dotted name and mcp_name as an explicit collision-free
underscore name, e.g. runs.artifact_chunk -> runs_artifact_chunk, under local
[a-z][a-z0-9_]{0,63}. Do not dynamically sanitize caller strings; freeze and test
the one-to-one mapping. Alternatively retain dots and name the clients tested.

Current HTTP output has NO global16MiB limit: app.py:427 reply JSON-serializes
then reports its actual byte length. MAX_BODY40MiB is a request limit, not a
response limit. Runs.list/Projects.list/graph lists can grow with catalog size;
ordinary get/run documents can include substantial captured runtime metadata.
Workbench.query bounds page count1..100 but query analysis is catalog-dependent.
Typed source-owner limits constrain inputs/slices, not all serialized response
lengths. P6's proposed16MiB HTTP receive limit is an explicit client capability
bound; reject oversized responses before allocating/reading them, never claim
it is inherited from HTTP. List parity is qualified only for responses inside
that bound; paging must be an separately admitted owner change if later needed.

An8MiB raw segment is8,388,608 bytes and canonical base64 is11,184,812 characters.
Base64 alone duplicated in structuredContent and compatibility text is22,369,624
characters plus small metadata/JSON escaping.16MiB HTTP and32MiB MCP caps admit
this closed segment response. Arbitrary16MiB JSON can expand beyond32MiB when
serialized again as compatibility text; validate the final encoded MCP response
size too, returning an explicit response_too_large tool error. Do not assert all
16MiB HTTP JSON automatically fits32MiB MCP. A small fixed metadata bound makes
the segment guarantee measurable; include exact maximum envelope test.
