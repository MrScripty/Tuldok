# Local integration checkpoint; publication blocked

Published PR #18 remains at `12b174f7a7b2fd6aa36d71da450ad657a5443114`.
No new public writes, merge to development/main, PR #17 edits or CodeRabbit
requests occurred in this stage. The executor remained available after the
reported 09:47 disconnect; shell commands, native Chromium and tests succeeded.

Local normal merge `71752fadd68efd092f53ee356ffb64061fa064da` has parents
`12b174f7a7b2fd6aa36d71da450ad657a5443114` and exact authorized caption
`10de10b6710976570ace33b033ffb2349995edec`. Only the HTML conflict required
resolution: retain exact classification HTML, replace its old caption panel with
the exact successor panel. Both feature UIs, 202 unique IDs, non-nested forms and
script order were preserved. Preparation/merge receipts are retained separately.

Local classification repair `8235672a8482e10e95df7a6d5b05540325f66816`
addresses a confirmed fresh-input recovery trap. Browser validation had accepted
a 2,072-character URL and persisted its ID/body; actual backend HTTP400 occurred
before admission. Losing that refusal, then full reload/exact GET404, retained an
impossible request; corrected URL could not submit and identical retry HTTP400
could not release it. Seven URL parser/Unicode/length mismatches were identified.

The repair validates the raw URL at 2,048 Unicode code points, rejects lone
surrogates, checks actual HTTP authority and credentials, matches Python whitespace
handling, and preserves accepted raw spellings. Invalid fresh input creates no
pending/storage/POST state and can be corrected on the same page. Existing
ambiguous or corrupt stored evidence stays fail closed and is never normalized.

Focused checks passed on exact 823 source: independent 18 recovery/storage/cross-
page VM probes, 11 frontend/backend URL cases, 16 classification backend tests,
classification controller and standalone caption reload controller. The expanded
controller covers 23 baseline corrections, 12 rejected/corrected URL cases, six
accepted raw spellings, 12 stored unknown URL cases and exact same-ID recovery.
Native classification fixtures passed, including valid-looking long URL and
guidance rejection/correction, real reload/early404/explicit retry/storage/export.
Final native run-WcI9aV has matching start/end HEAD and module/controller/browser
hashes. Earlier run-WcVUvJ is preserved with its provisional HEAD qualification.

All 2,098 historical report files remain byte-identical, including the original
959 and earlier 1,457 baselines. See [preservation/focused receipt](classification-focused-qualification.json).
Full aggregate was not run on this checkpoint; it is pending the next caption
repair and classification authority repair, rather than claimed green from old
source. The existing caption controller invokes the new standalone reload suite.

## Confirmed blockers

1. Unchanged caption 10de source accepts whitespace-only guidance. Actual backend
   HTTP400 before admission, lost acknowledgement, full reload and exact GET404
   retain that invalid request; correction submits nothing and identical retry
   HTTP400 still retains it. Additional malformed URL/model/guidance cases were
   found. Caption source remains unchanged; its author is aligning the complete
   fresh-input validation contract before providing the next final SHA.
2. Two unmodified native two-page runs on exact 823 released a shared Web Lock,
   admitted two distinct classification POST IDs into held transport, and
   overwrote the origin recovery record with the second ID. Neither request ran
   inference while held. Instrumentation-only variants passed and do not supersede
   the concrete failures. Web Lock handoff does not make renderer-local storage
   snapshots coherent. Transactional origin authority is required; that separate
   local repair is in progress and is not qualified by this checkpoint.

[Backend focused review](independent-review/backend/review_focused.md) and
[interaction review](independent-review/interactions/review-823.md) retain exact
source checks, positive cross-feature cases and all negative reproductions.
Sixteen composed and native cross-feature reload/two-tab/separate-store/held Apply
cases passed. They do not establish approval while the two blockers remain.

Next: qualify transactional classification admission authority; receive the
parent's next final caption SHA, integrate it normally on the classification
branch, preserve historical evidence, run the complete aggregate and independent
cross-feature review, then push only PR #18 and verify its exact hosted CI. Real
provider compatibility and semantic quality remain unqualified.
