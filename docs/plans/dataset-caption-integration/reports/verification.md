# Staged caption integration qualification

The staged combined workbench passes raw/native-caption admission, explicit
fixture review, exact filters, fixed saved membership and exact release export.
This does not advance PR10 or adopt the UI/main. The last component addition is
exact ACKed `8c6e5fb5f5c2620a05ccb2707e94e10cd7fe4d1b`; newer curation is excluded.

[Actual desktop/narrow gallery](gallery.html) ·
[Preserved original walkthrough](../../workbench-ui-qualification/walkthrough.md) ·
[Normal merge ledger](../execution-ledger.md)

## Source and tests

The final screenshot-focused replay used source/test commit
`22d895056a89f053bdc64a862a1701a411c630d5`, tree
`0973519c1451a91eccc990e5928123ca89bdc81c`. Final staging evidence adds only docs,
screenshots and receipts after that source/test head. Source/file SHA-256 values,
commands, results and logs are in [source-and-gates.json](source-and-gates.json).

- **180 Python tests passed in 50.242s**, including the native import's 15 actual
  HTTP/SQLite/filesystem regressions and every accepted combined test.
- **Six controller/page-load gates passed**: workbench, saved selections, selection
  intent, bulk import, caption import and page-load tracker.
- **All 13 real Chromium suites passed**, including both raw and caption combined
  workflows, all original component browsers, retained corner studio and controlled
  image-provider/queued-job tests. Four workflow static syntax gates passed.
- All 44 accepted-base test files remain byte-identical. Every inherited workflow
  command, Chrome environment mapping and screenshot path remains registered.
  Caption module/controller/tests match exact ACKed component blobs. Generation,
  raw import, saved selections, workbench controller and release owner modules
  match accepted `e33144a` blobs.

Runtime is the selected Linux environment, Python 3.12, Node 24, headless Chromium
`151.0.7922.173`, explicit isolated profiles/XDG paths, `--no-sandbox`/`--disable-gpu`
for this browser fixture. No operator browser/session, external models/datasets,
provider credentials, inference or ONNX download is used. Provider suites use
existing controlled local test servers. These local results do not stand in for
independent review or claim hosted qualification on this new stage.

## Added combined workflow

The browser consumes the component's committed authored native folder: exact
manifest plus train/val/test metadata and four RGB PNGs. Every consumed file's
bytes/hash is in [caption-combined-session.json](caption-combined-session.json).
Manifest SHA-256 is
`e902b6543b45ac9fb4a24b477b6c975c93746a629e1b0e35989638f038d21e69`.

| Action | Actual result |
| --- | --- |
| Raw import/review/select/preview | Retained one-record editor, exact pairs and proof before caption import |
| Caption row response held after real commit; Stop; change rights filter | One completed admission, three not attempted; zero matching current results; existing editor/pairs/proof remain intact |
| Reselect expanded native folder | Three remaining rows created, already imported duplicate rejected unchanged; four local captions are draft, with new IDs and unknown rights |
| Save imported draft fixed set; preview image-caption release | Drafts remain draft and Freeze disabled; imported declared review never grants local review |
| Explicitly review each fixture in editor; reopen original draft set | Original revision-1 pairs remain fixed, all four report stale and release stays blocked |
| Human-reviewed/task/unknown-rights exact filters; one protected-group exact filter | Four results, then one validation-source result; dynamic search does not rewrite fixed membership |
| Explicit current reselection; save reviewed fixed set; reopen; change criteria; navigate hash URL | Exact revision-2/source-revision-1 pairs restore and remain fixed despite dynamic results/navigation |
| Preview and actual browser ZIP download | Four reviewed captions; preserved train/validation/test 2/1/1 allocation; four unknown-rights records remain warnings |

Downloaded manifest pairs equal the exact four selected current pairs. Caption
text, exported pixel SHA and split projections equal the original folder.
The unchanged chapter-26 consumer at SHA-256
`6a4394308a4cc69b4ca965aca7f8459d7711ac9d51ce70492562c6ec6d806f94` reports four
readable records, 2/1/1 splits, no exact pixel duplicates or cross-split group
leakage. The archive's byte count/hash and full manifest are retained in the receipt;
the temporary download itself is not a committed fixture. This is not an original
archive authenticity or provider/rights claim.

Fourteen ordinary viewport screenshots cover import outcomes, draft blocking,
caption/review controls, exact criteria, fixed opening, eligible preview and
download at 1400 × 1000 and 390 × 844. Image hashes/scroll positions are receipt-bound;
there is no horizontal page overflow. No mock DOM or visual replacement is used.
`File`/`DataTransfer` uses actual committed bytes with controlled relative-path
properties, so OS folder-picker interaction is not claimed. The input is an
**expanded native caption folder, not a ZIP upload**.

The existing 42 UI qualification artifacts stay byte-identical with their original
`e33144a` identities. New source captures remain separate. The same long stacked
layout and desktop whole-page scrolling are visible; conservative source-group
hashes and source filenames make imported record rows verbose. No UI fix or
curation feature was added. Scripted review choices are deliberate test actions on
authored fixtures, not evidence of human acceptance of user data.

## Review size, limits and handoff

Report both the full unfiltered range against original PR10 base `6bbde344` and
the incremental range from accepted `e33144a` in the final delivery receipt.
No evidence is removed, split into other PRs or path-filtered to evade a file cap.
The [official CodeRabbit plan table](https://docs.coderabbit.ai/management/plans)
currently lists OSS file allowances from 100 to 300 and counts files after path
exclusions. The actual repository-specific allowance is unconfirmed: PR10's bot
only says draft review was skipped. Do not claim that this full diff fits its cap.
Parent was asked for the exact notice and owns manual-review/quota coordination.

PR10, main and component published heads remain unchanged. Independent incremental
review is the next owner action. A separately published staging branch may run its
registered exact-head CI; that metadata is reported separately, with no denied
hosted log/artifact transfer. No new consolidation PR or manual CodeRabbit request.
