# Provisional combined dataset development candidate

## Scope and source authority

Parent explicitly authorized composing published queued-size repair, repaired
saved-selection/filter stack and raw bulk import in a separate branch/worktree.
This is a combined development candidate for coordinated consolidation and UI
review, not adoption into main. Publish only the integration branch; do not open a
new PR, close or merge existing drafts, force push or alter unrelated branches.
The annotated-corpus follow-on belongs to another worker and is excluded.

Worktree: `/workspace/Tuldok-dataset-integration`. Branch:
`integration/dataset-candidate-20261006`. Repo-local author/committer is
MrScripty <TheEnvironmentGuy@protonmail.com>. Existing source plans and pinned
Coding-Standards `dcc56f26e884ade260770beceba2501d3746200d` guide contracts,
verification and normal commit/integration handling. No applicable AGENTS.md or
local implementation skill was found. Main remains frozen for UI decisions.

## Verified published components

| Component | Exact published head |
| --- | --- |
| PR4 queued obsolete-size rejection | `801d598a1400afdc2360128a1657896b89da10c4` |
| Original repaired PR7 selection/filter stack | `3ce5b181decfbf40cc4b661fb07caa39d6bc8e3e` |
| PR8 raw JSONL import | `7c43e9b8fe6ff23d3e75d356361fe616c8365d9c` |
| Additional reviewed PR6 cached-preview repair | `bfbebbb1ef70ab30d8a5ba5f776b7babf27a4c01` |
| Additional reviewed PR7 surrogate repair + corrected PR6 merge | `e1336b0db419d11acb8788906f169ab3d29e33c3` |

Heads were checked against remote refs before fetching/branching. Fetch requested
only the published component branches; composition uses exact commits, not newer
or unpublished annotated-corpus source. Every component remains an ancestor.
See [merge ledger](execution-ledger.md) for parent identities and conflict decisions.

## Contracts retained

- New queued requests reject obsolete `size`; numeric width/height and omitted
  dimensions retain current behavior. Legacy saved-job normalization/resume remains.
- Raw local text/image JSONL creates unlabeled drafts through atomic owner-based
  acquisition. Per-row rejection, duplicate preservation, stop barriers and uncertain
  result lookup remain. No imported field grants annotation/human review.
- Saved sets retain fixed IDs/revisions/source identity; stale/deleted/missing
  members are reported without substitution. Initial listing, cancellation,
  browser navigation and earlier editor completion respect newer selection intent.
- Dynamic exact label/group/rights criteria remain separate from fixed membership.
  JSON entry preserves LF/CR/CRLF and rejects unpaired surrogates before encoding;
  valid supplementary Unicode and deliberate U+FFFD remain valid. Rights notes
  establish no permission decision.
- A successful older editor completion can prove a retained fixed pair stale and
  discard its cached proof without adopting the new pair. A completion older than
  a newer selected pair cannot falsely invalidate that newer proof.
- Exact selected preview/export still checks current sources, revisions and full
  lineage independently. No merge weakens the human-review or freshness boundaries.

## Acceptance and ownership

Preserve every inherited Python/controller/browser gate and screenshot path, add
real browser coverage for raw import → lossless filter → explicit review → fixed
saved set → exact preview/download. Exercise dynamic results and delayed query,
bulk acknowledgement, cancellation and editor completion with stale revisions.
Qualify desktop/narrow layout and all combined workflows on the exact candidate.

Parent relayed two new independently reproduced component findings during initial
composition. Existing PR6/PR7 branches were explicitly authorized for those repairs;
their original evidence/ancestors remain preserved and both corrected heads are
normally merged into this candidate before qualification. No other PR1–8 branch
is altered. Future independent findings must be incorporated and retested before
final consolidation. Parent owns review-thread disposition, PR consolidation,
main/UI adoption and eventual retirement of retained worktrees. This worktree stays
retained-protected for review. No manual CodeRabbit request, external dataset/model,
ONNX download, credential/global/network-setting change or denied-log retry.
