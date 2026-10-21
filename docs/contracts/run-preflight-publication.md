# Exact external preflight reporting

Pipeline remains the preparation owner. Selected
`graphs.preflight_external/3` performs the existing fresh source/input capture,
runtime inventory and current host-code verification, then rechecks the graph
before returning `external_preflight_report_v1`. Inspection never imports
Project code or starts recipe execution. Runs retains admission, process custody
and publication authority.

## Report and proof scope

The report binds catalog ID, graph ID and revision, execution SHA256 and exact
prepared material SHA256. Its own SHA256 covers every report field except
`sha256`, using sorted compact UTF-8 JSON with finite values and unescaped
Unicode, matching the material owner's canonical encoding. ASCII escaping in
the HTTP transport does not change that domain identity. Graph clones may share
execution/material identities; their report identities still bind their distinct
graph IDs/revisions. The report is outside the material and does not change its
approval digest, capture inventory or execution identity.

`state: prepared` means the existing preparation path returned successfully.
`admission: not_reserved` is explicit. This is an observation of that preparation,
not a grant, admission token, proof cache, reservation, readiness guarantee or
numerical acceptance. Changing any execution-affecting input requires normal
fresh preparation/admission; retaining the report does not extend proof lifetime.

Each check has a bounded code, owner, phase, state, evidence SHA256, named boundary
and explanation. The wire limit is 16 checks, 160 characters per boundary and 240
per explanation. The producer emits ten checks, plus the current storage
observation when the selected recipe uses the large-output resource profile:

| Checks | State | Meaning |
| --- | --- | --- |
| `source_inputs`, `runtime_inventory`, `host_closure`, `output_contract`, `capture_authority` | checked | The actual fresh preparation path verified these declarations/captured bytes/current observations. Cold structural validation alone cannot produce this report. |
| `storage_capacity` (large-output profile only) | checked | Runs observed sufficient free bytes on its destination filesystem for its existing two-output-copy plus 1 GiB envelope, adding pending captured bytes and the existing generated model-context limit before staging. The bounded explanation exposes observed available/required/pending bytes; its evidence hash binds that observation. |
| `authority_admission` | deferred | Runs must check current actor/grant/request identity and any Study budget/reservation atomically. |
| `resource_availability` | deferred | Current queue/capacity/storage and reservations remain the existing owners' checks. |
| `runtime_ready_go` | deferred | Dispatch/READY/GO must recheck mutable installation and actual selected device readiness. |
| `custody_completion` | deferred | No execution/cancellation/drainage has yet been observed. |
| `output_publication` | deferred | Actual output/evidence bytes, shapes, hashes and durable publication remain unverified. |

The fixed-array capacity checks are described in
[external recipes](external-recipes.md). Headers, variable diagnostics/context,
actual output sizes and science remain later checks. A preparation refusal keeps
its existing typed error and emits no successful report. The selected refusal
and retained-material extensions below do not complete all M1 acceptance.

### Selected v4 refusal reports

`graphs.preflight_external/4` extends this same report owner with
`external_preflight_report_v2`. Selected v1–v3 and headerless projections retain
their original contract identities. Successful v4 preparation retains the same
exact material checks, uses the v2 discriminator and has `refusal: null`.
It is still `prepared`, not an execution-readiness or scientific pass.

After authorized Pipeline entry, classified `WorkbenchError` outcomes (`invalid`,
`unsupported`, `unavailable`, `stale`, `conflict`, `too_large`, `storage`) keep their
original HTTP status, code and message. V4 adds `preflight_report` to that existing
error envelope. Invalid declarations report `invalid`, unsupported meaning reports
`unsupported`, and unavailable/stale/resource outcomes report `blocked`.
The report's `refusal` binds the original code/status. It reports only the first
observed refusal and performs no additional preparation or failure investigation.

Refused reports bind the requested catalog/graph/revision. Both execution and
material SHA256 fields are null, including after storage refusal or graph drift;
they never attest partial material. Their check evidence hashes bind request and
refusal provenance, not content verification. The generic Pipeline preparation
boundary does not guess a source/runtime/output failure family from error text.
Only the explicit Runs storage call may name `storage_capacity`/Runs provenance.
All ten other required checks remain `deferred`, meaning unknown in that refused
preparation. Device READY/GO, custody, publication and scientific acceptance stay
unobserved. The fixed eleven-row refusal fits the existing sixteen-check bound;
each boundary/detail keeps the existing 160/240-character limits. No unbounded
exception, path, traceback or producer diagnostic is copied into the report.

Authorization, selected-contract and request-schema failures before owner entry,
unclassified errors and non-Workbench storage failures remain ordinary bare typed
errors. Reporting does not perform graph reads to decorate those refusals.
It neither issues nor consumes grants, reserves a Study attempt, starts a child,
publishes a result nor retries preparation. This graph slice does not add reports
to the separate retained-recipe/Study material path or complete all C1/T1 checks.

AgentClient preserves only the selected v4 report through error normalization and
validates its closed bounds, content hash, code/status/state, exact owner/phase/
boundary layout, deferred checks and requested catalog/graph/revision. Explicit
null/malformed reports refuse; an absent report remains valid for early errors.
CLI `preflight` errors retain the validated report in stderr JSON with nonzero
exit status; WorkflowClient preparation raises the same typed error carrying
`preflight_report` and emits no submission manifest. Neither consumer retries.
Current credential content in a received refusal report is rejected without echo.

### Exact retained Study material preflight

`recipes.preflight_material/1` is the inspect-only POST operation at
`/api/workspace/recipe-material/preflight`, with closed input `{"ref": MATERIAL_REF}`.
Use the exact `material` reference from `studies.trial`; the operation does not
infer a Study, Trial membership, continuation state or budget from that reference.
It exposes Pipeline's existing `recipes.preflight_material` owner action without
changing `studies.prepare_trial` durable receipts or its replay behavior.

The successful closed result extends `recipes.material`'s `{ref, material}` with
`preflight_report: external_preflight_report_v3`. Pipeline verifies retained
composition/Model/capture bytes, revalidates the stored external graph against
current source/input/runtime/host state, then rechecks current retained disclosure
before delivery. It uses the retained recipe ID/revision, even after the editable
graph advances. It neither imports authored code nor launches a child. Builtin
materials return typed `unsupported` before native preparation/probing; the
existing internal Study approval/capture path retains its original behavior.

V3 extends the same bounded report family and preserves these distinct identities:

| Field | Meaning |
| --- | --- |
| `recipe_material_ref`, `material_sha256` | Exact outer composition reference and canonical hash of returned `material`. |
| `model_ref` | The verified Model reference in that composition. |
| `execution_material_sha256` | Inner prepared-material digest, equal to returned `material.executable_sha256`. |
| `execution_sha256` | Graph execution digest, retaining the graph report meaning. |
| `graph_id`, `graph_revision` | Stored graph in the retained recipe snapshot. |

The ten success checks reuse the actual inner preparation proofs. Their hashes
are not recomputed from the outer capture-blob list: that inventory has a different
representation. Runtime evidence is correlated with the returned runtime digest;
admission/custody evidence binds the inner material digest. Source, host, output
and graph-execution details remain owner-attested provenance in this bounded
projection. A client cannot independently reconstruct the graph execution digest
from `{ref, material}`. Report hashing establishes content consistency, not a
new scientific proof. No storage-capacity observation is added here; resource
availability, authority, READY/GO, custody and publication remain deferred.

Classified refusals preserve their typed code/status and eleven-row request-only
layout. Only `recipe_material_ref` and its catalog are established: graph identity,
Model, outer/inner material and execution digests are null, including after partial
verification. No checked proof survives a refused preparation. Malformed/foreign
references, authentication/disclosure failures, missing records and unclassified
errors remain bare typed errors. No extra investigation decorates a refusal.

AgentClient selects this additive contract, validates its closed bounds and hash,
correlates the exact requested Ref/catalog and all locally available composition
links, and rejects malformed/null reports or current credential contents in
refusal reports.
The generic CLI `call` retains validated refusal reports in stderr JSON and exits
nonzero. Neither transport retries. Existing `recipes.material` remains a cold
inspection operation; source drift can block fresh preflight while retained
inspection and old Trial receipt replay still succeed. No admission grant,
reservation, process, publication or scientific acceptance follows from this read.

The success-only/early pending statements above describe the retained v3 slice.
Publication/indexed-diagnostic implementation below has its own qualification;
this extension changes only graph preparation reporting.

## Producer and consumer boundaries

The HTTP producer validates the selected output. The Python AgentClient validates
the closed bounded report and cross-checks its SHA, material SHA, catalog,
execution and graph revision. It also correlates graph ID/revision and catalog
with the actual request/client configuration. Contradictory responses return a
typed transport error; the client makes no alternate request or implicit retry.
These checks prove consistency, not independent freshness or authorization of a
server claim. Only the fresh server preparation path owns the checked facts.

Old selected v1/v2 and headerless responses keep their existing projection and
authority. V3 is negotiated explicitly; it adds no request field or scope. The
existing CLI's `preflight` command and MCP tool consume negotiated results through
AgentClient. Older clients/servers continue selecting their exact common version.
Authentication, corrupt responses and unavailable operations never cause fallback
dispatch. No catalog schema, retained evidence format or migration changes.

## Publication recovery status

The Runs-owned continuation core below is implemented separately from preflight.
Selected HTTP/agent operations and CLI/SDK collection are implemented below;
Indexed diagnostics remain pending M1 work; the existing Run-panel and lineage
controls below have separate browser qualification.
The exact Ref evidence/comparison methods below have separate qualification.
The preflight report itself grants no recovery or publication authority.

## Retained original-attempt publication source

New external attempts retain a private `external_publication_source_v1` before
copying outputs into the published result directory. It binds catalog, Run,
request, material and execution graph identities, the validated completed/drained
custody receipt, the original measured declared-output inventory and its hash.
Its `evidence_semantics: not_verified` is explicit: structural byte verification
does not establish valid extension evidence, numerical acceptance or a result.

The existing output verifier gains an opt-in durable path. It syncs each measured
output and directory while holding anchored descriptors and checking file/root
identity, with the existing bounded reads and file/aggregate limits. The source
proof is canonical finite UTF-8 JSON, capped at 48 KiB, written owner-only and
synced before atomic no-replacement publication in the original private
`.external-<Run>` directory as `publication-source-v1.json`. Existing unequal
proof bytes refuse; a later call cannot adopt newly changed outputs. The
temporary link shares the same file bytes and is removed by its writer.

Only its versioned `external_publication_source` Ref is saved in the original
Run document. Drainage and that Ref commit in a separate acknowledged transaction
before result copying starts. Unknown commit acknowledgement starts no copying;
it does not imply retry or cleanup authority. The next transaction reloads current
Run/cancellation state. A copy fault therefore leaves the original drained proof
and receipt inspectable on reopen rather than rolling their metadata back.

The proof belongs outside the final published directory, whose exact inventory
remains unchanged. Source bytes are not a third output copy. The bounded file
and small Ref use the existing custody metadata allowance; no new attempt,
reservation, grant consumption or Study refund is introduced. Existing backup
already retains ordinary private staging files and opaque Run documents. The
new file/Ref each carry schema version 1; metadata schema versions 1–10 and old
Run/wire projections remain unchanged. No proof includes a rebased execution
path. Historical absolute execution specs remain historical evidence after restore.

## Runs-owned continuation core

`Runs.recover_publication` accepts the original Run ID, exact retained source Ref
and a stable request key. It requires a current owner with approve-execution
authority and current transitive input access. It creates no process, GO, Run,
execution grant consumption or Study reservation. The original failed/interrupted
Run state, execution events, request and settled resource envelope remain intact.
Older Run/artifact/evidence gates keep refusing that failed attempt.

Eligibility requires a recorded recoverable publication fault, completed/drained
original custody, the frozen source proof, exact captures/output membership and
unchanged approved bytes. Legacy attempts without that proof/fault refuse.
Changed outputs, incompatible evidence, foreign directory entries, unproved
ownership and sealed mismatching metadata refuse; recovery never adopts them.
Existing owned unreferenced partial payload files may be replaced within the
original destination. Intact files and matching receipts/manifests are synced
before attachment. The original output and destination copies are reused; no
third output copy is created. Remaining growth plus the existing 512 MiB reserve
must fit current destination storage.

There is one active continuation per Runs owner/catalog, a 60-second wall budget,
bounded per-chunk cancellation/deadline checks and at most 20 recorded attempts.
Each attempt retains bounded status/error information under the original Run.
Same actor/body/key requests converge on this continuation. Conflicting requests
refuse. Cancellation persists a revision before acknowledgement; copies pause at
safe checks. A committed result wins over later cancellation. Shutdown joins
owned recovery before metadata closes. No startup or reader retries compute.

After integrity and supported evidence verification, an immutable private
`recovered_publication_result_v1` document binds the original identities,
inventory, custody receipt, fault and continuation request. It is at most 48 KiB,
mode 0400, synced and linked without replacement in the original private staging
directory. Its versioned `recovered_publication_result` Ref attaches in a final
transaction that rechecks current owner/transitive authority and cancellation.
Unknown commit acknowledgement claims neither failure nor success; repeating
the same request reconciles the exact attached Ref before any copying.

`Runs.publication_status` exposes bounded saved metadata and explicitly labels
eligibility as requiring verification. `publication_result` and the bounded
`publication_artifact` reader accept the exact attached Ref, verify its proof,
published membership, receipt/manifest and artifact bytes, and reuse supported
extension semantics. Their 60-second verification budget checks shutdown and
chunk/semantic boundaries; an individual artifact response is at most 8 MiB.
Malformed or changed retained bytes return typed unavailable. Explicit selected
transport operations below expose the new result independently. Evidence queries/
comparison accept explicit Refs as described below. Candidate/package promotion
from recovered failed Runs remains unsupported; existing gates are unchanged.

No SQL migration, supported metadata version change, dependency or legacy wire
projection change is introduced. Existing stopped backup/restore retains the
private source/result documents and opaque Run continuation. Recovery resolves
current catalog-relative staging after restore while preserving original specs.
The neutral real-process/Study tests establish custody and accounting behavior;
synthetic field fixtures establish structural stop boundaries. Neither establishes
new numerical, CUDA, real-lab or full extension-result acceptance.

## Selected publication transport and collection

The additive selected-v1 operations `runs.publication_status`,
`runs.recover_publication`, `runs.cancel_publication`, `runs.publication_result`
and `runs.publication_artifact_chunk` require an exact operation-contract header.
Headerless calls refuse; old operation contracts and frozen legacy discovery
remain unchanged. Recovery/cancellation are owner-only mutations; ordinary agent
inspection cannot gain that authority by selecting the new operation. A stable
recovery key reconciles the original continuation, with no automatic retry.

Selected status/2 adds the saved continuation's actor, request key and exact
request hash, or null before a continuation exists. Status/1 and the original
domain projection stay unchanged. Clients correlate this metadata with the
source Ref, Run and stable request body before using it to reconcile an existing
CLI/UI continuation. The key is an identity, not a credential or grant; recovery
and cancellation still require current owner authority. No new request is
inferred from an unknown acknowledgement.

The new artifact-segment operation accepts the exact attached result Ref, flat
artifact name, expected whole SHA256, offset and at most 8 MiB per call. It checks
current transitive authority, attached Ref/proof, exact receipt/manifest and
inventory membership, then reads only the requested payload range through stable
owned no-follow descriptors. It does not scan all artifact payloads per chunk.
Its `segment_read_whole_hash_unverified` label is explicit; the whole result
reader retains its separate complete verification promise. Clients correlate the
returned Ref/Run/catalog/offset/hash and verify the assembled whole hash before
publishing bytes. No recovered result becomes an implicit input binding.

Ordinary AgentClient remains agent-only. The separate PublicationOwnerClient
accepts an existing owner configuration and only the five publication operations;
it cannot call unrelated owner operations. CLI `recover-publication` and
`cancel-publication` use that explicit client. `publication-status`,
`publication-result` and `download-publication` use ordinary agent configuration.
Ref/body JSON is bounded and downloaded files publish exclusively after whole
hash verification; existing destinations are preserved on refusal.

SDK `collect-publication` uses an explicitly hash-selected sealed public CLI and
an exact result Ref. It makes no admission/recovery call. It validates the result
and inventory identity, downloads into a new output directory, independently
hashes each file in bounded chunks and returns `collected` only when all selected
inventory bytes match. Its finite command deadline and 4 GiB collection ceiling
do not enlarge any Run/evidence contract. Partial local collections remain
inspectable on refusal; `numerical: not_evaluated` stays explicit. This command
does not substitute for original SDK execution conformance or science acceptance.

## Exact recovered field evidence and comparison

Selected-v1 `runs.publication_model_evidence` accepts the exact result Ref and
optional existing field selectors. Runs validates attached proof/manifest and
current transitive access, then invokes the supported extension verifier with
the original interrupted/failed Run and its recovered inventory. It never
substitutes completed state or widens old evidence readers. Checkpoint/member/
field/axis/index and validation-only restrictions retain their existing meaning.
Neutral external results without supported field evidence return unsupported.

Selected-v1 `runs.compare_publication_evidence` accepts two exact result Refs
and the existing complete checkpoint/evaluation/metric-definition selection.
Both manifests must match the inventory's explicitly selected evaluation hashes.
The field owner supplies authoritative preprocessing/output policies to the
existing exact scalar comparison, rather than treating a field model
specification as a classifier definition. Task, frozen membership/input/target,
metric, policy and field contract/geometry/gauge mismatches return incompatibility
with no paired delta. Side-by-side mode also returns no paired delta. Observed
and undefined arithmetic retain the existing explicit states and reasons.
All returned Ref/Run/catalog and selection identities are correlated by the
client; contradictions fail without an alternate request.

Readers have one shared 60-second budget across proof and semantic work and
recheck current inspect/transitive authority before disclosure. Segment capture
also rechecks authority after its bounded payload read; revocation withholds the
response without deleting the committed result. Legacy failed Run readers and
candidate/package promotion retain their refusal.

SDK `compare-publication` takes two Ref JSON files and an exact selection JSON
through the explicitly selected sealed public CLI. It collects no model state,
performs no inference/admission/recovery and marks numerical acceptance
`not_evaluated`. Compatible fixture arithmetic establishes comparison behavior,
not the scientific validity or performance of any model.

## Existing Run-panel publication controls

The current catalog's existing external Run panel selects `publication_status/2`
and exact selected-v1 recovery, cancellation, result, artifact-segment and field
inspection contracts. Missing or incompatible pins fail closed. Saved metadata
eligibility is displayed as requiring current byte verification; it does not
claim output readiness. The original failed/interrupted label, publication fault,
source Ref, finite attempt count and output copy bound stay visible.

Only a current owner may recover or pause publication. Recovery also requires
the retained original publication actor. The browser saves its source Ref and
request key before dispatch in catalog/actor/Run-scoped tab session storage,
mirrored into history. Unavailable or corrupt request storage disables recovery. Unknown write
acknowledgements retain that exact request. Selected status/2 can reconcile a
CLI-origin continuation using its actual actor/key/hash; the panel checks this
hash against the exact source and request body. Existing foreign-actor requests
can be paused by the current owner, but cannot be resumed under a new actor or
key. Navigation, Run selection and session changes fence late responses and
release panel polling; any server mutation already in progress remains owned by
Runs. Polling is bounded to 75 seconds per observation window and never retries
recovery automatically. Manual status refresh or same-request reconciliation is
explicit.

Published result inspection verifies its exact Ref/content identity before
showing artifact and field-inspection controls. Browser downloads use selected
segments, correlate the exact Ref/name/hash/offset and expose bytes only after
whole SHA256 verification. Each artifact is limited to 8 MiB in the browser,
with a 120-second download budget and at most 75 seconds per HTTP request.
Larger artifacts remain available through the sealed CLI's existing bounds.
Neutral results retain the typed unsupported field-evidence response. The panel
never retries compute, selects a candidate, imports a binding or widens legacy
failed-Run readers. Field metadata is structural/identity evidence; numerical
acceptance remains separate.

## Publication links in existing experiment lineage

The existing Trial detail keeps its actual saved failed/interrupted Run outcome.
For each such attempt in the bounded latest-five window, an explicit **Inspect
saved publication status** action reads selected `publication_status/2`. It never
fans out status reads when the graph loads and starts no publication polling.
The lineage and Run panel share one closed metadata/source/result-Ref/request-hash
decoder, correlating the original Run, catalog and original outcome. Contradictory
metadata refuses instead of manufacturing an empty or ready result.

Publication state and the exact recovered Ref appear separately from the
original Run label. Both remain labelled saved metadata. **Open original Run to
inspect this Ref** opens that same Run's existing panel, where current owner
recovery/pause and explicit byte inspection remain owned. Lineage supplies no
recovery, replay, promotion or import action. Selecting another node, refreshing
the graph, navigating or changing session clears inspected publication metadata;
late responses are fenced before disclosure.

A fresh real neutral Model/Study/Trial/admission/custodian fixture qualifies this
link through a retained copy fault and same-Run recovery. Its Study reservation,
conservative charge, original lineage projection, Run state and lifecycle events
remain unchanged. This is byte-custody and interaction evidence, with no
numerical producer, model-quality or scientific acceptance claim. Existing
lineage contracts, ancestry, intent and attempt schemas are unchanged.

## Current large-output storage observation

Selected v3 preflight checks the existing `captured_cpu_large_outputs_v1`
policy through Runs after fresh material preparation and before the final graph
recheck/report. Unknown capacity or insufficient free space refuses with the
existing typed `unavailable` result, without staging, admission, grant use,
reservation or process creation. Other resource profiles have no new capacity
claim. Old selected v1/v2 and headerless preflight behavior stays unchanged.

Before staging, required free bytes are `pending captures + 2 × declared maximum
output bytes + 1 GiB`. Pending captures include the exact material inventory and,
for model evidence, its existing generated-context byte limit. At admission those
captures/context have already been written, so the same owner checks its original
`2 × declared maximum output bytes + 1 GiB` bound. These observations reserve no
space and do not account for future concurrent consumers. The later admission
recheck and publication's separate actual-output-bytes plus 512 MiB check remain
required. A passing observation cannot promise durable publication or recovery.

The read-only [scientific comparison](scientific-comparison.md) accepts exact
attached publication-result Refs alongside completed Run operands. It reuses
publication-result identity and authority checks, preserves the original failed
or interrupted outcome, and grants no legacy promotion or candidate eligibility.

## Opt-in indexed diagnostic capture

The noncanonical `extension_field_policy_indexed_v1` policy adds a hash-bound
`diagnostic_capture_v1` declaration. Admission reserves its exact bounded index,
ordered shard outputs, record populations and complete mandatory coverage under
the existing output/file/aggregate caps. This opt-in variant reserves all
declared output maxima within the selected profile aggregate budget. Existing
policies and closed evidence/public projection grammars retain their meanings.

The current evidence owner verifies scientific evidence first and diagnostic
bytes against the same retained artifact inventory. Publication recovery and
exact-hash result readers expose the admitted index/shards under the original
Run and result Ref; no replay or alternate permission path is introduced. See
[Indexed diagnostics v1](indexed-diagnostics.md) for the complete producer/host
contract and the distinction between required coverage and explicit optional
omission ranges. This generic contract does not classify absent original lab
diagnostic bytes or repair an invalid original output.
