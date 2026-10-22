# Implementation review result

The [plan](../plan.md) owns current acceptance and blockers. This report records
independent review scope and dispositions; it grants no execution or merge
authority. The separate [planning review](independent-review.md) remains intact.

## Reviewed subjects

The complete native integration review used an immutable source copy, manifest
SHA256 `d9f7fcc6e0a79483d8d48820acd78f4638b20f6077aff0fe81d62efec454da6e`.
All 824 product/test/static/schema files matched before and after review. Earlier
unchanged owner reviews remain valid only for their named subjects. The reviewer
examined actual producers, cold decoders, custody, public consumers and the
selected plan against Coding-Standards
`5bce3110fc64d61ff8b4f79468184bd6295855d5`.

Three medium findings required source changes:

| Finding | Resolution and deciding evidence |
| --- | --- |
| Individually valid native phase jobs could disagree with their Run's scientific context. | Compare exact jobs derived by the existing image/text/audio scientific owners, preserving observational paths. One pure case rejected 16 internally rehashed forgeries; exact-source rereview cleared `project_native_execution.py` SHA256 `28b51a914087ac29a17d7665960b5d19d36b6edbe18858514b2cf96fc3ee4fe9`. |
| An exception after entering spawn but before returning a Handle left dispatch available. | Typed `outcome_unknown` fences the Session/coordinator. An actual HTTP/PostgreSQL control covered callback-entry/OSError, no Handle, denied redispatch and unknown recovery; rereview cleared the same source. Receipt SHA256 `454dcee734d258b76e1213a1966324477daa028b4f180864b7f6c479af3453f6`. |
| Explicit note deletion promised by the plan was absent. | CAS-bound note-only tombstones retain all prior text; restoring uses ordinary explicit adoption. Ten backend PostgreSQL cases, real SDK/CLI/MCP and Chromium/cold-fork controls passed. Full bounded public/backend rereview cleared manifest SHA256 `dc276867f7e1095a6c8a6a2578450dd0eaf6c974775d2adc7ad7f85c53f3214f`. |

Actual native Save As subsequently exposed a fork-intent decoder error. The
finite preparation adapter now distinguishes an explicit draft intent before
complete-graph execution hashing, while requiring the original complete graph's
observation closure. A no-fit PostgreSQL regression and the actual retained Run's
independent fork/cold path passed. Targeted rereview cleared
`project_native_preparation.py` SHA256
`967a368da9faa476e366ec66f047c1c463d08edfe71a1a4ae9faa15476f68404`.

Other resolved findings are indexed in [issues](../issues.md): immutable Run
observations, original-host recovery correlation, source/control separation,
native unique-payload precedence, bounded phase capacity and original staged
source extraction. Their reports retain the narrower evidence and exact source
subjects. No unresolved material product finding remains in these reviewed
subjects. This does not assert exact-head CI success.

## Evidence and final gate boundaries

The direct native case trained and separately verified a real CPU Run, copied
an independent project and reconstructed it through a separate PostgreSQL role.
Its metadata-only Git tail initially expected the wrong typed missing-artifact
error. The corrected tail passed against the same retained Run without fitting
again; the original whole-case result remains ERROR.

The Study's original case and retained tail each stopped at a fixture assertion:
fresh continuation legitimately creates a new operation receipt, and a new Run
completed after the fixture's arbitrary 180-second deadline. Both Runs and both
settled reservations were subsequently verified from the exact retained proof,
including 79 artifact hashes. Final original-host active-SQL counts were not
observed. A test-only deadline derived from the existing native admission budget
was independently approved; final full cases remain selected for CI.

Final targeted review cleared portable CI selection at workflow SHA256
`9bbe1cf75444310b0214a365bc6db89600ee960ae326996bcc92e91e8c71aad0`,
the exact bounded wait corrections (Study `6c08d170…`, Run `5429fdef…`), current
issue dispositions and the enabled Workspace matching the qualified copy.
Exact/nonzero counts and no-skip requirements remain in every named real gate.
The original full discovery has no native GO flag, so it does not duplicate
those fits. Current documentation finalization is separately reviewed before
commit. Evidence is reused only across unchanged claim boundaries; no identical
training campaign or evidence-volume target is required.


The final bounded contract/status read is clear with no remaining finding.
Contract SHA256 `b349f1765440d369ede7f06d68b5ddae02f1a5685775796124b41d3799dc578b`
and plan SHA256 `d5bcbb141b82aaba11de1c64dac05a101e391ac9c10cacb87f7b90d8932d4c1f`
match the finite native/deletion owners and truthful Verifying/conditional CI
status. The reviewer performed read-only inspection, no tests or edits. This
clears the commit/publication review gate, not runtime acceptance or merge.
