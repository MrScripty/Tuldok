# PR7 lossless exact-criterion entry

## Reproduction and preserved source

Review source: `e925514671743883b6ff9fe34c851cf36560f036`, tree
`cbd47ae8370c234e6630e101be3cb24583a8f64f`. Original commit remains an ancestor;
repair appends to `feature/explicit-metadata-filters-20261006`, existing PR7 against
unchanged provisional PR6 `2311f7cd0eaaf6c6a89e259ddf5c340f3a9ca887`.
The original tree was extracted with `git archive` to `/tmp/tuldok-pr7-e925514`;
no existing branch/worktree was switched, rewritten or merged. Test-only
`TULDOK_SOURCE_ROOT` selects that local source for browser/controller reproduction.

Actual retained values `left` + line ending + `right` have these codepoints:

| Ending | Original internal codepoints | Single-line value | Exact API count | Sanitized count |
| --- | --- | --- | --- | --- |
| LF | 10 | `leftright` | 1 | 0 |
| CR | 13 | `leftright` | 1 | 0 |
| CRLF | 13, 10 | `leftright` | 1 | 0 |

Real browser regression confirms each positive/negative API control, then fails on
the missing lossless entry control on unchanged original source. No runtime
exceptions. Log: `/tmp/tuldok-line-endings-browser-before.log`. Deterministic
controller regression also fails on the unchanged source because JSON entry is
sent verbatim rather than decoded: `/tmp/tuldok-line-endings-controller-before.log`.
Backend line-ending regression already passes before production edits, proving
existing storage/HTTP exact semantics are sufficient and should remain unchanged.

## Repair and exact behavior

The user can choose **Exact filter entry → JSON strings**, then enter quoted values
containing `\n`, `\r` or `\r\n`. Parsing preserves the decoded characters before
URL percent encoding; raw single-line input remains the default for ordinary values.
Literal backslashes and quotes use JSON escaping. Blank remains unrestricted.
Only strings are accepted; malformed/non-string JSON shows an error without a
query. Switching formats converts all three criteria atomically. A switch back to
plain is blocked while any decoded value contains CR/LF, retaining the format and
fields. Encoded lengths support the full backend limits, including all characters
escaped as supplementary Unicode surrogate pairs. Backend code-point limits still
validate the decoded values. No stored metadata, exact matching, schema or review
rule changes. No textarea normalization fallback.

## Local qualification

Linux x86_64, Python 3.12.14, Node 24.19.0, Pillow 12.3.0 and Chromium
151.0.7922.173; same isolated headless CDP/local fixture procedure as PR7. No new
dependencies or external provider/model/dataset downloads.

- **150 Python tests passed in 35.593s**, including nine metadata-filter tests.
  New storage and real HTTP contract proves all three criteria distinguish LF,
  CR, CRLF, ordinary values and literal backslash text, with no persistence mutation.
  `/tmp/tuldok-line-endings-python.log`; focused pre-edit backend log:
  `/tmp/tuldok-line-endings-backend.log`.
- Page-load, workbench/saved-set controllers and all six PR6 intent cases pass.
  New controller transport asserts decoded exact values, fixed-pair/token stability
  and rejected invalid/non-string JSON without dispatch.
  `/tmp/tuldok-line-endings-controller-after.log`.
- All **nine real Chromium suites** pass: workbench, grounded, captions, release
  preview, saved sets, saved-selection intent, metadata filters, corner studio and
  controlled image generation. Logs: `/tmp/tuldok-line-endings-*.cjs.log`.
- The new browser regression captures actual production fetch query parameters and
  checks decoded LF/CR/CRLF codepoints for label/group/rights, corresponding exact
  record IDs and unchanged full stored records. Ordinary values, literal backslash
  and quote text, maximum fully escaped Unicode, format conversion/blocking, error
  recovery and no-query failures pass. A loaded two-record fixed selection and its
  actual preview token remain unchanged throughout. A dynamic result grows from
  41 to 42 without adopting new records; exact ZIP export/download still succeeds.
- [Desktop](filters-desktop.png) and [390px](filters-narrow.png) screenshots were
  regenerated and visually inspected: entry control/help readable, no horizontal
  overflow or runtime exceptions. Existing-suite screenshots were retained under
  `/tmp/tuldok-line-endings-existing-suite-screenshots`; inherited committed bytes
  restored only in the task's initially clean worktree. JS syntax and diff checks pass.

## Publication and limits

Final head/tree and exact hosted run/job receipts belong in the updated PR7 body.
Published source e925514 and its CI evidence remain historical evidence, not the
repair's qualification. Inspect metadata for the new exact head and all registered
steps; no hosted log transfer/artifact download, denied-endpoint retry, credential
repair, network-setting change or manual CodeRabbit request. Only PR7's branch is
pushed. Main/PR5/6 and generation modules are unchanged. Worktree is retained for
parent review/integration; final UI decisions and provisional-base review remain
parent-owned. JSON entry requires explicit escaping; rights notes remain arbitrary
metadata and confer no permission or human review.
