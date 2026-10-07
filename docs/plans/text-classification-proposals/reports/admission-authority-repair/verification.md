# Transactional classification qualification

Exact qualified source: `97144cb85b274cf68e20e0952907787b28b3026a`.
Tree: `04226dcdf5cf11c0683cad6f28e4af20dfce978f`.
Aggregate runtime/test source SHA256:
`d37c2f4cc4c19c20326752d96613897f148a3a9a769eaf1d3716188f12113c56`.
The following documentation/evidence commit changes no runtime, tests, dependencies,
qualification runner or CI configuration.

One existing unannotated text record can receive an author-requested proposal from
frozen exact labels. Exact source, source/target revisions and hashes, prompt/version,
provider/model, guidance, seed, labels, canonical request and complete bounded response
evidence remain inspectable. Only an offered label or explicit abstention is accepted;
unknown or malformed output fails without a fallback. Explicit Apply atomically saves
one draft and its idempotent receipt, preserves acquisition provenance and never grants
human review. Changed source/labels or deletion prevents Apply; fixed exports retain
captured revisions and become stale.

Classification admission now uses origin-wide IndexedDB readwrite transactions.
The exact bounded ID/body must commit before its localStorage mirror and POST.
Startup gates submission while authority is loaded. Web Locks provide additional
coordination; transaction authority also handles stale renderer storage views.
Lost acknowledgments and ambiguous 404s retain the original identity. Reload performs
no automatic POST; source/settings restoration and identical-ID retry require explicit
author actions. Read/write/delete/commit/mirror failures and malformed unresolved
records fail closed. An exact admitted receipt retires the canonical pending frame;
failed mirror cleanup retains the exact retirement evidence and blocks new POSTs until
cleanup succeeds. Corrupt evidence is never repaired by guessed IDs or default labels.

Final aggregate: **46/46 gates passed**, **273 Python tests**, zero failures,
blockers or stale passes, in **299.598 seconds**. Every gate records matching
start/end HEAD and source hash. See [summary](final-qualification/gates/summary.json),
[results](final-qualification/gates/results.json) and
[preservation receipt](final-qualification/qualification-and-preservation.json).
All **2,801** pre-run report files remain byte-identical: 2,478 older/incoming-caption
reports plus 323 first-attempt and review artifacts. The earlier 45/46 aggregate,
failed browser script and raw logs remain immutable; the corrected fixture now checks
real IndexedDB retirement evidence rather than a superseded in-memory expectation.

Independent review passes 26 native storage/authority boundary cases, five
independent HTTP recovery cases, 16 backend tests, and 14,058 classification input
cases with zero browser-accepted/backend-refused cases. All 1,254 accepted cases
preserve exact intent; 542 backend-accepted cases are conservatively rejected by the
browser. Native checks cover actual asynchronous request errors with cancelled default,
strict commit/abort, stale localStorage views, exact-ID retry, legacy migration,
corrupt/oversized/duplicate evidence, forged markers and receipt CAS. Three fresh-origin
native two-page races each admit one body and one synthetic provider request. Native
readiness/pagehide, committed-request reload, both-feature reload/two-tab storage and
held Apply pass, together with 16 composed ownership and 12 caption correction cases.
The final independent receipts link the unchanged reviewed runtime to this exact
aggregate and corrected fixture; the native artifacts include screenshots and an
actual reviewed ZIP. No remaining blocking finding was reported in these checks.
See the [backend audit](independent-review/backend/final_aggregate_audit_97144cb.json),
[interaction review](final-qualification/independent-review/interactions/review-971.md)
and [native artifact review](independent-review/fixtures/final-review.md).

Both proposal ownership and storage contracts are retained. Caption source/tests
exactly match authorized head `12690a58d9b2a781efd081f1a3e796313d5235c1`.
The normal development merge `2f1d68ee29ec98a524bdf0f14d20b6024a25364c`
has the same tree as that caption head and is retained in classification ancestry.
Both HTML panels remain intact with 202 unique IDs, 16 nonnested forms and ordered
script owners. The development comparison contains classification implementation,
tests, integration hooks and evidence; caption source/tests have no delta.

This branch starts at requested PR #17 head
`07ec464ba050cd532a2508ce86570a1ce9bcd394`. Repository-local attribution is
MrScripty; no global Git settings changed. Main stays at
`2fc4a46f12d73a0fa467d5482f68edb83d6df6af`. The parent independently landed
PR #17 on development at `2f1d68ee29ec98a524bdf0f14d20b6024a25364c`;
this feature writes only its classification branch and PR #18 metadata.

All model HTTP is bounded and synthetic. Instruction consumers use the previously
authorized pinned isolated CPU environment and tiny local random fixtures, with no
weights downloaded. No credentials change. Real-provider compatibility and semantic
quality remain unqualified. IndexedDB, readable/writable origin storage and Web Locks
are required; unrecoverable corrupt pending evidence blocks new admissions.

Authorized next publication step: push the evidence successor only to
`feature/text-classification-proposals`, retarget draft PR #18 to
`feature/image-caption-exports`, verify its classification-only diff and exact hosted
CI, then leave it for review. No merge or CodeRabbit request is authorized here.
Hosted/publication receipts are kept outside this immutable qualified report tree.

Exact first-parent feature history before the evidence successor:

```text
97144cb85b274cf68e20e0952907787b28b3026a merge: retain landed caption development ancestry for classification
11e3d3d66bec2b2c167b65c6a5bc172baa4e0d9a test(classification): assert authoritative retirement before mirror cleanup
f95cd5c95189165534d21c204a227f4dd8145c92 merge: integrate final caption validation into classification proposals
620a97a1494e228c5fcb4fc0407f5f371e89217e fix(classification): reserve admission identity with transactional origin storage
05e2745a6eb786674a060a3a1050172847b6208b docs(classification): preserve integration blockers and exact focused repair evidence
8235672a8482e10e95df7a6d5b05540325f66816 fix(classification): validate exact gateway intent before persistence
71752fadd68efd092f53ee356ffb64061fa064da merge: integrate final caption admission recovery into classification
12b174f7a7b2fd6aa36d71da450ad657a5443114 docs(classification): retain repaired exact qualification and publication evidence
c5500cba5021949bccf45d2124ee5e2910dc5c92 fix(classification): persist exact admission recovery across reloads
e32b407c6164f5650e1944c356ec0d00d7536667 fix(qualification): isolate rerun reports from prior evidence
0a143b276bc5a2ab992d814678d18a9fb6e34111 docs(classification): retain exact local qualification and independent reviews
7b1938e3ef9b7ba499bafde1fa02e44fb90e8dc7 feat(workbench): propose frozen-label text classifications as drafts
```
