# P6 focused verification checkpoint

2026-10-13. Canonical plan: [generic scientific projects](../plan.md).
Admission: [P6](p6-admission.md). Contract: [agent operations](../../../contracts/agent-operations.md).

The scoped agent interface is implemented in the isolated P6 worktree and its
focused checks passed. This is a reviewable implementation checkpoint, not final
P6/G5 acceptance: the final full regression/CI remain pending. The read-only qualification against
retained real scientific Runs has now passed. No merge or deployment.

## Implemented boundary

The stdlib-importable registry publishes versioned request/output schemas,
operation names and a deterministic digest through authenticated HTTP discovery.
The optional MCP stdio adapter uses the official SDK with protocol2025-06-18;
it calls the existing loopback HTTP owners and opens no catalog or scheduler.
The agent-only client checks catalog identity, live authorization and registry
agreement, bounds framing/deadlines/response sizes, and never retries mutations
automatically. Standard Draft202012Validator semantics are preserved; stricter
integer/source/revision checks stay with domain owners.

The admitted matrix covers all eight data kinds and twelve draft annotation
tasks, bounded native imports, proposal draft decisions, canonical release
preview/freeze, graph editing/preflight, exact owner-granted external submission,
status/progress/cancellation and explicit scoped holdout exposure. Human review,
credential/grant issuance and ordinary owner-only retry remain outside agent
tools. External new attempts require explicit new submission and a valid grant;
identical-key reconciliation creates no new attempt.

Stateless artifact segments retain the existing Runs owner and explicitly mark
whole-file identity unverified. Client reassembly must verify the final complete
SHA256 before acceptance. Existing full verified HTTP downloads remain intact.
The new segment path does not rehash the entire payload for each chunk and does
not create a bridge-owned file cache or arbitrary filesystem operation.

## Recorded focused test runs

| Suite / checkpoint | Result | What it establishes |
| --- | --- | --- |
| `test_agent_api` initial focused suite | 14 passed, zero skips | Registry/schema projection, stdlib-only import, bounds, authentication/configuration, framing/deadline, no replay, hash checks |
| Agent API post-integration fix selection | 4 passed, zero skips | Raw-base64 image projection; revoked discovery preserves401/code; schema projections and framing regressions |
| `test_mcp_stdio` final NUL-framing revision | 13 passed, zero skips | Official SDK subprocess lifecycle, fixed protocol, typed tools, bounded framing and errors |
| `test_artifact_segments` | 5 passed | Exact multichunk reconstruction, linear selected reads, mutation/nonregular/size refusals, revocation and cross-catalog denial |
| `test_agent_http` | 3 passed | Authenticated registry discovery, real HTTP segment/restart parity and exposure eligibility denial |
| `test_agent_workflow` + `test_agent_domain_parity` | 3 passed | Public stdio/HTTP workflow, all twelve annotations/native variants and real authored classifier holdout exposure |

These counts describe recorded runs, not an additive unique-test total. The
four-test post-fix selection overlaps the initial suite and includes newly added
regressions; it is not a claim that eighteen distinct client tests ran together.
The initial agent suite took16.598s; the affected post-fix selection took10.884s.
The final protocol module passed13 tests in8.052s. Other timings are not asserted here.

Public workflow coverage used isolated fixture catalogs and explicit owner
HTTP review/grants outside MCP. It exercised draft→owner review→freeze→graph
save/preflight→grant→agent submit, two distinct real neutral executable Runs,
same-key reconciliation, artifact reassembly, cold reopen and credential
revocation. Native import/annotation parity covered image/text/audio/mesh,
pointcloud/volume, sequencev1/v2 and project scientific fields. A separate tiny
real text classifier established positive holdout exposure under the existing
`expose-holdout` scope; this is not a scientific surrogate benchmark or GPU test.

Two integration defects were corrected before this checkpoint: image transport
now forwards raw base64 expected by the existing image owner; discovery auth
failure now retains its actual401/unauthenticated response instead of being
misreported as registry_mismatch409. A successful unequal registry still refuses
mutation with registry_mismatch. No domain authorization was relaxed.

## Dependency evidence and remaining gates

[Dependency decision](p6-dependency-review.md) and
[resolved artifacts](p6-agent-dependencies.json) record optional MCP1.30.0 and
jsonschema4.26.0 with a hash-locked29-package wheel closure. Provisioning occurred
only after the P5c benchmark was terminal/completed/drained. It used the isolated
P6 `.venv-agent`; the captured scientific runtime and P5c source were unchanged.
The measured lock is Linux x86_64 CPython3.12 evidence, not cross-platform acceptance.

Still pending:

- Final full regression, independent final integration review and hosted CI on
  the published exact source. The task integration owner records final status.
- Final integration of the separately tracked legacy actual-v2 packet gate;
  P5c scientific acceptance is already complete and published in PR52.

This checkpoint establishes bounded transport/domain behavior, not scientific
correctness of a model, source authenticity, remote multi-tenant security or
unlimited HTTP/UI parity. Inline imports remain512KiB/1MiB request bounded;
HTTP receive16MiB and encoded MCP32MiB limits are client restrictions. Segment
bytes remain provisional until whole-hash verification. No additional scientific
Run, new model fitting or evaluation was required by these focused P6 checks.

Final independent protocol review found initialization metadata could contain NUL
although the framing contract promised rejection. The framing owner now rejects
NUL in every string/key; the final 13-test stdio module passes with no skips
(8.052 seconds). No scientific model acceptance is inferred from these tests.

## Actual retained scientific MCP read

Official SDK qualification passed at source b02004a with 22 real MCP operations.
The retained P5c checkpoint (272,149 bytes, one segment) and scientific chunk
(38,196,421 bytes, five segments) exactly matched the previously qualified HTTP
inventory and complete hashes. The pressure slice also matched prior HTTP.
Runs, graphs and the reviewed record remained exactly unchanged. The inspect-only
credential was revoked and both server/stdio processes closed. This proves
transport parity, not another scientific/model acceptance run.
[Receipt](p6/scientific-mcp-receipt.json), SHA256
`f99cdd6654c5bd3a9271e6e79bc99aa0fed1c53bf36066f39099f74e52f920c2`.

Source is published as draft [PR53](https://github.com/MrScripty/Tuldok/pull/53).
Final local base, optional and JavaScript regression is running against the
frozen source. Hosted UI38474544619 passed; lifecycle38474544623 is pending.

The first base-only full discovery exposed missing optional-dependency skips in
14 client/schema tests. Production discovery still imports without optional
packages; the bridge correctly reports dependency_missing when they are absent.
A test-only correction is prepared, preserving cold discovery/config checks in
the base environment and qualifying all agent tests in the dedicated SDK
environment. The failing discovery is not counted as a passing final suite.

## Base-environment correction and recovered final run

The preserved full discovery completed900 tests in1,324.060s. Its onefailure and
12errors were confined to the optional-jsonschema client tests; all336 inventoried
source files remained unchanged. The test-only correction adds14 precise skips
when jsonschema is absent, retaining two base discovery/configuration checks.
The corrected base module passed16 tests with14 explicit skips in0.042s; the
dedicated SDK environment passed all16 with zero skips in15.356s. No production
runtime or base dependency was changed. Remaining dedicated/SDK/JavaScript gates
and fresh hosted full discovery determine final acceptance.

## Final local affected and optional gates

After the precise test-only correction, all remaining local gates passed:
dedicated point11/volume9/training12/evaluation9 with zero skips; official-SDK
agent22/22 in46.420s; MCP13/13 in8.047s;56/56 JavaScript/syntax commands.
All336 source hashes stayed stable during those gates, with the intentional
API-test patch the only change from the original full discovery inventory.
[Final test receipt](p6/final-test-receipt.json), SHA256
`7b1de6a33f76b3cf08ad45a91af346bfbb5ff13840a459937d73b5f4120e979a`.
The failed original900-test discovery remains recorded; fresh hosted full
discovery on the patched source is the final regression acceptance gate.

## Final hosted acceptance

Both final checks passed at PR53 head
`5c0e7f92914e5aeac6ec939e3a667fc85b22aa90`:
[lifecycle](https://github.com/MrScripty/Tuldok/actions/runs/38478255351) and
[workspace UI](https://github.com/MrScripty/Tuldok/actions/runs/38478255410).
Hosted full discovery passed 900 tests in 672.693 seconds with 36 explicit
skips. The separately recorded local optional environments cover the admitted
reader, training, evaluation and SDK paths with zero skips. Hosted agent
22-test and MCP 13-test modules also passed. The broader suite is not claimed
to have zero skips. Independent review and final JavaScript/browser checks
passed. This supersedes the pending full-regression status above and satisfies
G5 for the explicitly admitted operation matrix.

The later caption-browser change only waits for the loaded page before DOM
reads; it changes no scientific or MCP production behavior. Actual scientific
SDK evidence remains tied to source `b02004a`. Original v2 packet and A8
real-model acceptance remain separate blockers to overall completion.
