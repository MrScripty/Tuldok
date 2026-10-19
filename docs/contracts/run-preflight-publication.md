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
its existing typed error and emits no successful report. Structured failure
diagnostics and complete M1 preflight/publication recovery are not yet implemented.

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
Negotiated HTTP/agent operations, SDK/CLI, browser/lineage integration, extension
result collection/comparison and indexed diagnostics remain pending M1 work.
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
Malformed or changed retained bytes return typed unavailable. These methods do
not add a negotiated transport operation yet. Segmented collection, evidence
queries/comparison and candidate/package promotion from recovered failed Runs
remain outside this core slice; existing promotion gates are unchanged.

No SQL migration, supported metadata version change, dependency or legacy wire
projection change is introduced. Existing stopped backup/restore retains the
private source/result documents and opaque Run continuation. Recovery resolves
current catalog-relative staging after restore while preserving original specs.
The neutral real-process/Study tests establish custody and accounting behavior;
synthetic field fixtures establish structural stop boundaries. Neither establishes
new numerical, CUDA, real-lab or full extension-result acceptance.

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
