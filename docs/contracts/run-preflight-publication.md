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

Same-Run publication continuation, indexed diagnostics, attached recovered-result
Refs and new result readers remain pending M1 work. This report does not recover,
publish, promote or reinterpret a failed Run, nor replay compute or consume grants.
Those capabilities require their separate storage/custody/authority acceptance
before being advertised.

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

This retention prerequisite does not expose a recovered-result Ref, reinterpret
a legacy failed Run as completed, or implement a recovery command. Current
authority, original hashes, semantic evidence, bounded partial-copy reconciliation,
accounting and supported result readers still need their separate continuation
acceptance before recovery can be advertised.

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
