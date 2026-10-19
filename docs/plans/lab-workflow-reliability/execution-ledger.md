# Lab workflow reliability execution ledger

## 2026-10-19 — Plan preparation

- Parent requested a standards-compliant implementation plan only, with a
  separate documentation branch/worktree, independent review, validation and
  draft publication. No product implementation or merge is authorized here.
- Inspected local status/worktrees, repository tree, current main and PR89/90.
  Main is `300f12df6f48e028fd9379911703f7c89337952a`; PR89/90 remain open at
  `33069a859836953960a06dfd6001cba54aba0aa0` /
  `429d0c4ff44dba16bc95313d2a0980169dbc9b9f`.
- Created `docs/lab-workflow-reliability-plan` at main in the separate
  `/workspace/Tuldok-lab-workflow-plan` worktree. Existing worktrees and refs
  were preserved. Only this plan directory is an allowed write set.
- Coordinated with the integration lead in
  [PR90 comment](https://github.com/MrScripty/Tuldok/pull/90#issuecomment-6272255247).
  Lead retains PR89/90 and all integration/merge authority.
- Inspected completed D1, current material/preflight/publication/CLI/evidence/
  lineage ownership and PR90's RES-1. Wrote six implementation milestones;
  no new design-discovery phase or product worker was started.
- Read adopted Coding Standards at `dcc56f26e884ade260770beceba2501d3746200d`.
  The available skill is standards-authoring-specific and explicitly excludes
  ordinary application work. No repository AGENTS.md/local skills were found.
  Application-purpose Engine invocation is unavailable; exact source structural
  validation and manual review are recorded separately, without Engine certification.
- Independent review and actual validation results are recorded in
  [reports](reports/validation.md). All product claims A1–A8 remain pending.
- Independent GPT-6.1 Sol High review found one blocking draft gap: legacy
  completed-state gates made recovered evidence inaccessible. Revised C2/M1/T2
  with an exact attached publication-result Ref/new readers and explicit legacy
  failed/promotion-refusal semantics. Also made scientific per-case criteria and
  recovery operation budgets explicit. Focused re-review cleared all findings;
  [the exact subject hashes and limits](reports/independent-plan-review.md) remain
  distinct from future implementation acceptance.
- A disconnect notice was investigated: actual commands and source reads
  succeeded, all draft hashes were intact, and no work was lost. Reported this
  to lead/parent in [PR90](https://github.com/MrScripty/Tuldok/pull/90#issuecomment-6272545966).
- Final plan-creation validation passed: unchanged upstream structural checker,
  all23 relative links/anchors, new-file whitespace and all8 paths confined to
  the new documentation directory. No application/runtime/catalog test ran.
  The coherent documentation commit contains the plan, exact contract/test
  handoff, issues, ledger and review/validation evidence. The draft PR identifies
  its final Git SHA; branch/worktree remain retained for lead review, with no merge.

## 2026-10-19 — M1 start on explicit composed dependencies

- Later user instruction authorizes continued implementation with verified
  persistent storage. `start` selects this plan, changing its implementation
  copy to Active. Original PR91 plan source remains unchanged/unmerged.
- Existing configured workspace GitHub authentication recovered; published
  independently reviewed test repairs cd5c029 (PR89) and76d3c6a (PR90). Fresh
  lifecycle CI is pending; no merge has been attempted.
- Pushed checkpoint96afae5 to the repository, then restored it through a fresh
  standalone clone. Verified22 file sizes/SHA256 values, every task repair's
  history reachability and separately fetched exact PR91b446d9a. Only public
  task source, test logs and review receipts are included, no runtime/catalog
  data or credentials. Restoration is documented in its RESTORE.md.
- Admitted first bounded slice: required field array payloads must fit declared
  per-file, shard and aggregate budgets before compute. Keep the existing
  evidence-policy owner, output verifier and operation identities. Shared
  reference filenames count once; declared maxima are not actual/minimum sizes.
- Regression witnesses on the prior code: five failures for prediction,
  reference, probe-input, face-array shard and aggregate bounds. After change:
  nine deterministic cases pass, including actual synthetic writer/verifier
  and cold retained-byte reader round trip. One real PostgreSQL no-effect test
  remains locally skipped; hosted execution is required. This is no training,
  recovery, indexed-diagnostic, hardware or scientific acceptance claim.
- Independent review, affected evidence regressions and exact implementation
  head CI remain pending. Next: qualify this slice, then extend the complete
  exact preflight report/publication continuation. A1–A8 remain pending.

- Affected focused group:43 tests,40 passed and3 PostgreSQL skips in4.611s.
  [Exact reports/logs](reports/m1-output-bounds/validation.json) retain the
  before/after witnesses and evidence limits. No local PostgreSQL pass claimed.
