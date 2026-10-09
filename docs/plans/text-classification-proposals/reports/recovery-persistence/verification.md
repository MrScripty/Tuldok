# Exact classification qualification and publication readiness

Qualified source commit: `c5500cba5021949bccf45d2124ee5e2910dc5c92`.
Tree: `be60326b4950fdd68a8fdfd35ca13a62a2e51113`.
Aggregate runtime source SHA256: `cace4aa85e7217e5428dafcf000dab1667692dab9a7a95ce2e16b34fdf6b608e`.
The subsequent evidence/documentation commit changes no runtime, tests, dependencies,
CI configuration or qualification runner.

## Behavior

One existing unannotated text record receives an author-requested proposal from a
frozen exact label list. Source bytes, hashes, source/target revisions, exact prompt,
provider/model input and canonical configuration, seed, labels and bounded complete
request/response evidence are retained. Only one offered label or explicit
abstention is accepted. Malformed, duplicate-key, unknown, partial and nonfinite
responses fail without a fallback. Abstention offers no Apply.

Explicit Apply atomically saves a draft and its idempotent evidence receipt after
rechecking source and label evidence. It never grants human review or changes
acquisition provenance. Existing exports retain captured revisions and become stale.
Cancellation/restart, summary projection and editor ownership reuse the established
proposal lifecycle. Reject cannot acquire an unrelated save's editor ownership.

Durable admission recovery was repaired after a preserved negative reproduction:
the former in-memory ID allowed a changed intent after full reload while exact GET
was held. The client now stores the bounded exact ID/body before POST, restores
synchronously, coordinates pages with Web Locks, checks authoritative job evidence,
and refuses changed intent until resolution. Ambiguous 404/transport failures retain
identity; reload never submits automatically. Visible source/settings restoration
requires author actions, followed by explicit identical-ID/body retry. Oversized,
malformed or unavailable storage and missing locks fail closed. A receipt cannot
clear another page's newer durable request.

## Validation

All 46 aggregate gates passed on the exact source, with zero failures, blockers or
stale passes; 271 Python tests passed (including 16 classification tests). Every
gate records matching start/end HEAD and source hash. Aggregate duration: 294.854s.
See [summary](gates/summary.json), [results](gates/results.json) and
[qualification/preservation receipt](qualification-and-preservation.json).

Bounded synthetic HTTP and native Chromium fixtures cover source/label changes,
deletion, exact Unicode labels, malformed/unknown responses, abstention, cancellation,
restart, lost admission and Apply acknowledgements, real early 404 across reload,
delayed exact GET, explicit same-ID retry, unrelated saves/rejection, atomic rollback,
idempotence, stale fixed exports and explicit human review. Storage failures and
cross-page admission races are exercised; actual two-page review admitted one intent,
one POST and one provider call. No test performs real inference.

[Independent backend review](independent-review/backend/review.md): 18 backend,
storage/receipt and actual-submit cross-page probes passed; all aggregate logs,
component hashes and preservation evidence independently verified.
[Independent interaction review](independent-review/interactions/review.md): six
storage/locking scenarios, eleven composed ownership probes, native reload/author
controls, native two-page fencing and both controller suites passed. No remaining
findings. Initial negative reproductions and the first two-page harness timeout are
retained with the successful diagnostic and final exact-candidate runs.

The two previously blocked instruction-consumer browsers now pass using an isolated
pinned environment: CPU torch 2.8.0+cpu, all 44 requirement pins, application Pillow
12.3.0, five verified consumer source hashes, and clean pip check. Dependencies came
from official PyTorch CPU and PyPI registries with authorization. Consumer execution
uses offline flags and tiny local random-model/tokenizer fixtures, with no model
weights downloaded. [Environment receipt](../publication-qualification/installed-consumer-environment.json).
The application virtual environment remains unchanged.

All 1,457 pre-recovery evidence files remained byte-identical, including the 1,185
tracked reports, original 959 historical reports and earlier e32 qualification.
See [baseline manifest](pre-recovery-evidence-manifest.json). Initial feature evidence,
dependency-blocked results, later e32 green results and recovery reproductions remain
separate and immutable. The e32 green candidate is superseded by this repaired source.

## Commits and integration boundary

- `7b1938e3ef9b7ba499bafde1fa02e44fb90e8dc7`: classification feature and fixtures.
- `0a143b276bc5a2ab992d814678d18a9fb6e34111`: initial immutable qualification evidence.
- `e32b407c6164f5650e1944c356ec0d00d7536667`: isolated qualification report roots.
- `c5500cba5021949bccf45d2124ee5e2910dc5c92`: durable reload/cross-page admission recovery.

Branch `feature/text-classification-proposals` begins at requested published PR #17
head `07ec464ba050cd532a2508ce86570a1ce9bcd394`. Repository-local author is MrScripty;
no global Git settings were changed. Main remains
`2fc4a46f12d73a0fa467d5482f68edb83d6df6af`, image-caption development remains
`c43a110c4b6ee1a85c932fa206b43091c0db7f3a`. This work makes no writes to those
branches or PR #17.

PR #17's author independently advanced its branch to
`4ed5466fd764e938999cca1d535e9a33379271a0`. A read-only merge-tree check found a
content conflict in `static/workbench.html`. The new draft PR targets that caption
branch, but the exact local qualification above covers our original-base candidate,
not an integrated successor. Resolve that conflict on the classification branch,
then requalify and independently review the integrated candidate before merge.
Publication authorizes only the classification branch and a new draft PR; no merge
or CodeRabbit request is included. Hosted push CI will verify the published exact
head; the base conflict prevents a pull-request merge CI run until integration.

## Limits

Synthetic contract/lifecycle validation establishes no real-provider compatibility
or semantic quality. Authors must inspect the proposal and explicitly review drafts
before release. Durable recovery requires available origin storage and Web Locks;
missing support fails closed. Unrecoverably corrupt pending evidence stays blocked
rather than silently losing an uncertain admission. Real-model qualification and
caption successor integration remain later stages. Hosted publication receipts are
kept outside the repository to avoid changing the already-qualified source.
