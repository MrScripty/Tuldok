# Reject malformed Unicode before query encoding

Parent's independent review found JSON strings containing lone UTF-16 surrogates
were parsed successfully but replaced by URLSearchParams before submission. Review
source `3ce5b181decfbf40cc4b661fb07caa39d6bc8e3e` remains preserved; its tree is
archived locally at `/tmp/tuldok-pr7-3ce5b18` for reproduction without modifying any
existing source branch/worktree.

Real Chromium against that original source submits a parsed U+D800 as U+FFFD and
matches a separate deliberately stored replacement-character record:

    field=label, originalCodeUnit=55296, submitted="\ufffd", matchedRecords=1

Before evidence: `/tmp/tuldok-surrogate-browser-before.log`,
`/tmp/tuldok-surrogate-controller-before.log`. Controller test explicitly resolves
any unexpected query so the original failure is a missing rejection, not an
unresolved-promise false success. Backend direct malformed-Unicode validation is
already correct and remains unchanged.

Exact-value decoding now rejects any unpaired surrogate before URLSearchParams for
all three fields, in JSON and plain entry. Unicode-mode range matching sees valid
surrogate pairs as their single non-surrogate codepoint, so valid supplementary
Unicode remains accepted. It neither rewrites metadata nor substitutes U+FFFD.
Malformed/non-string JSON retains its existing error. Format conversion uses the
same decoder, so it cannot hide invalid characters. LF/CR/CRLF, quotes/backslashes,
ordinary and maximum escaped Unicode values retain the preceding repair contract.

Regression coverage: lone high/low surrogate, surrounded high surrogate, adjacent
high surrogates and reversed low/high pair across label/group/rights, with no query
dispatch and fixed membership/preview token unchanged. A deliberate U+FFFD value
still matches its actual record. Valid surrogate pairs are exercised by controller
and fully escaped maximum-Unicode browser cases. Backend invalid-value fixtures
also include high, low and surrounded surrogates. Focused after logs:
`/tmp/tuldok-surrogate-controller-after.log`,
`/tmp/tuldok-surrogate-browser-after.log`.

This existing PR7 branch also merges corrected PR6 cached-preview head through a
normal merge before full qualification, preserving both reviewed source ancestors.
The final commit/tree, complete Python/controller/browser counts and exact hosted
run/job metadata receipts are recorded in the PR7 body and this report's final
qualification section. Source e925514/3ce5b18 and earlier failure/CI evidence remain
historical; they do not qualify the corrected candidate. No new PR, force push,
main merge, credential/settings change, provider/model/dataset download or denied
log-endpoint retry. Parent owns independent review/thread disposition and the
preserved provisional integration candidate.

## Final local qualification with corrected PR6

Surrogate repair commit `dd18514` follows preserved PR7 `3ce5b18`. Corrected PR6
`bfbebbb1ef70ab30d8a5ba5f776b7babf27a4c01` merges cleanly into that descendant;
the normal merge retains both component ancestors and their before/after evidence.
No conflict choice drops either fix.

Full exact-source local qualification: **150 Python tests passed in 34.571s**;
page-load, workbench/saved-set controllers and all eight PR6 intent cases pass;
all **nine real Chromium suites** pass. Browser evidence preserves LF/CR/CRLF and
checks all 15 malformed JSON cases plus all three plain-field rejection cases,
maximum valid escaped surrogate pairs, intentional U+FFFD, fixed membership and
preview tokens. The merged PR6 real browser case reports retained old selection,
newer editor revision, null cached eligibility and disabled Freeze; stale server
export still rejects. No runtime exceptions or narrow-layout overflow.

Logs: `/tmp/tuldok-surrogate-python.log`, `/tmp/tuldok-surrogate-*.cjs.log`.
Production source remained unchanged throughout full qualification. Documentation
is appended afterward. Generated inherited screenshots are retained under
`/tmp/tuldok-surrogate-inherited-screenshots`; base PNG bytes were restored to keep
the source patch focused. JS syntax and whitespace checks pass. Final published
merge/head/tree and hosted receipts are recorded in PR7, not inferred from older CI.
