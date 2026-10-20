# Local graph preflight refusal qualification

Graph preflight now returns an inspectable structured refusal to negotiated v4
consumers while retaining its original HTTP code/status/message. Pipeline extends
its existing report owner with version 2 request-only failure reports. Refused
material/execution hashes are null; no partial proof is presented as checked.
Invalid, unsupported and blocked outcomes remain distinct from deferred unknown
checks. Bare early authorization/contract errors remain bare.

The consumer validates all eleven required refusal checks, owner/phase/boundary
provenance, bounded details, request/catalog identity, report hash and original
typed outcome. Rehashed forged provenance, omitted checks, unexpected proof
hashes, null reports and credential-bearing reports refuse. CLI stderr and
WorkflowClient typed errors retain the selected report without retry or submit.

The source-frozen local suite passed **65 tests in 200.178s, zero skips/failures/
errors**. It includes actual PostgreSQL/HTTP/CLI refusal, old 1/2/3/headerless
projections, real authentication refusal, no process/grant/reservation effects,
successful inert captured preparation and finite Study regression, existing CLI
neutral execution/download, and focused client/report/storage fault cases.
All 126 pre-existing operation contract hashes and the complete legacy projection
match baseline 360bbda exactly; graph v4 is the only added contract.

The positive static capture fixture explicitly uses `/usr/bin/true` and dummy
Torch/NumPy 0.0 files. It proves static ownership/contracts, not runnable numerical
training or inference. The neutral CLI recipe is not a lab workload. Three exact
owned fresh schemas were removed after fixture closure; unrelated schemas,
branches/worktrees and historical failures were preserved.

[qualification.json](qualification.json) binds the eight changed Python/test
file hashes, final [test log](focused.log), environment, compatibility comparison
and earlier attempts. Initial failures remain retained: the default interpreter
lacked psycopg; an earlier 65-case run retained a v3 private-call expectation
failure and a correctly enforced host-source-drift refusal during an in-flight
edit. The v3 call was restored and the final run used unchanged source. Final
independent disposition is retained separately in `independent-review.json`.

This is local implementation/acceptance for the graph structured-refusal slice.
No hosted CI, publication or merge is claimed. It does not close the separate
retained-recipe/Study report, all C1/T1/M1, publication retention/abandonment or
scientific criterion work. PUB-1 and SCI-1 still need their exact real-lab inputs.
