# Saved-selection user-intent repair

Status: Verifying, 2026-10-06. Bounded successor to PR5, admitted by the parent's
independent-review task. Main/PR1–5 and the paused metadata-filter branch stay unchanged.

## Outcome and source

A delayed initial saved-set list must not reopen its URL selection after a newer
manual selection or clear. An earlier editor save may persist its annotation but
must not replace fixed references opened later. The actual release request retains
the stale fixed pair and stays blocked until explicit current-record reselection.
Ordinary editor saves retain their existing behavior only while they still own the
current selection generation and exact pair observed at submission.

Verified base: PR5 `991a22beb5a69272571dd3731cfb8392154725f7`, branch
`feature/saved-dataset-selections-20261006`. New branch
`fix/saved-selection-intent-20261006`, separate worktree
`/workspace/Tuldok-saved-selection-intent`; draft target PR5. PR4 remains
`a3f3cbead4137110dfa8af81c94178e6d53aa036`, main remains
`2fc4a46f12d73a0fa467d5482f68edb83d6df6af`. No merge or history rewrite.
This worktree is retained-protected for parent review and further corrections;
the parent owns its next integration or retirement disposition.

Write set: `static/workbench.js`, `static/saved-selections.js`,
`tests/test_saved_selection_intent.cjs`, `tests/browser_saved_selection_intent.cjs`,
CI registration, README, and this plan directory. Workbench persistence, saved-set
schema/API, Releases validation, bulk import and generation owners are unchanged.
The metadata-filter worktree `/workspace/Tuldok-metadata-filters` remains paused
with its existing uncommitted changes, outside this repair.

## Failure evidence and mechanism

The review's two P2 failures reproduce on unchanged PR5 controllers and real
Chromium. Browser transport holds real HTTP responses; stored fixed pairs are
ineligible while silently substituted current pairs become eligible. Related
empty-map clear and already-stale-pair cases also fail before the repair.

Workbench owns one selection-intent generation, distinct from editor and release
epochs. Explicit selection actions advance it even when membership is unchanged.
Saved open, cancellation and navigation also revoke earlier intent. Initial URL
opening captures generation, list generation and URL; all must still match after
listing. Saved open checks its shared generation alongside existing load/key fences.
Editor completion advances a selected reference only while its captured generation,
map entry and source/annotation pair are unchanged. This prevents release-eligibility
substitution without preventing the annotation's independent persistence.

No waits, retries, approval mutation, replacement endpoint or persisted browser
state is introduced. Existing Select page/checkbox actions explicitly adopt current
pairs. Standards remain the pinned `dcc56f26e884ade260770beceba2501d3746200d`
guidance already read for PR5, particularly concurrency, contracts/replay and
verification/oracle/GUI evidence; no new dependency or framework changes.

## Acceptance and exactly one next slice

Deterministic before/after ordering regressions must expose both reported failures,
preserve ordinary save behavior, and cover explicit empty clear/already-stale pairs.
Real Chromium must prove the actual chosen request remains ineligible after delayed
editor completion and becomes eligible only after explicit reselection. Complete
Python/controller and all eight browser suites must pass, with exact-head hosted
CI metadata when authorized. Inspect local screenshots; do not retry denied hosted
log transfers. Parent owns independent review and integration; no CodeRabbit request.

Exactly one next slice: publish this scoped successor after verification and report
exact source/CI identities to the parent. [Verification](reports/verification.md)
records failure and success separately. Metadata filtering resumes under the parent's
sequencing decision after this review repair; it is not included in this draft.
