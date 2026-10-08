# Saved dynamic metadata searches

Status: implementation independently reviewed, 2026-10-08; final committed-head
aggregate qualification pending. Authorized continuation only after PR25 exact
`2ebe101f88e1ef50d9e0fb449d6f1fda8dfaeae2` passed hosted78/78steps and independent
fresh actual pinned Rheon import/export acceptance. Existing fixed-selection plan
explicitly identifies dynamic saved searches as unimplemented and requires a
separate explicit mode. Current metadata-filter contract already supplies the
eight criteria; no new query language or modality contract is needed.

Local branch `feature/saved-metadata-searches-20261008`, base exact PR25 head,
worktree `/workspace/Tuldok-saved-searches`. PR25/base/main remain unchanged;
this continuation is local only. Main stays `2fc4a46f12d73a0fa467d5482f68edb83d6df6af`.
No other saved-search implementation found in local branches or all-state PR search.
Standards remain Coding-Standards `dcc56f26e884ade260770beceba2501d3746200d`.
No AGENTS.md or applicable local skill exists in the verified workspace/tree.

## Outcome and ownership

Save a named copy of the currently entered search/filter values, independently of
whether Search has been clicked. Explicit Open applies those stored criteria to
the current collection, starting at page1; newly matching records can appear.
Saving/opening grants no review/rights/export authority and never changes selected
record/answer/preference revision pairs or editor drafts. Saved fixed sets and their
history URLs keep existing semantics. No automatic query application on reload.

`SavedSearches` owns one additive table, immutable criteria at schema_version1,
name/revision lifecycle, bounded to100 stored searches. Create validates exact
`{name,criteria}`; criteria requires precisely q/kind/task/review/sort/label/group/
rights with string values and existing limits/enums/normalization. Extract the
existing Workbench criteria validator, keep matching/query criteria output unchanged.
Save entered q before casefold expansion. Saved q excludes CR/LF, because its
existing single-line input cannot faithfully restore them; ordinary query API
semantics are unchanged. Exact metadata criteria retain LF/CR/CRLF losslessly.
New routes accept only strict UTF-8, duplicate-free finite JSON, at most32KiB.
Saving validates without enumerating records, enrolling images, reading assets or
touching record/history. Listing/loading returns metadata only. Rename/delete are
strict revision-checked; changing criteria means a new search. Duplicate names allowed.
Same Dataset SQLite connection/lock; no second catalog, job or browser persistence.

Dedicated UI/controller and panel explicitly say dynamic search and entered filters.
Open GET must validate the narrow saved-search receipt before restoring criteria;
restore exact label/group/rights in JSON entry so LF/CR/CRLF/backslashes survive.
Capture filter intent and queryEpoch before await. Later filter input/change/submit,
another Open/cancel, pagehide/popstate or a newer query retires the old operation.
After applying fields, the existing guarded refresh owns result publication; later
input/departure cannot publish old results. Opening cannot discard editors or mutate
selected maps, proofs or history URL. Save/mutation acknowledgements can refresh only
the list and status under their lifecycle fence; they never reapply captured criteria.
Unknown write acknowledgement reports uncertainty and invites list inspection;
there is no automatic replay. No durable exactly-once claim is made for search names.
Compare raw control values and format before apply and result publication too;
programmatic changes without events must retire stale operations. Dedicated write
and list lifecycle fences cover errors/status/cleanup as well as successful results.

Write set: saved_searches.py; shared criteria-only helper extraction in workbench.py;
app.py composition/typed routes/static route; static/saved-searches.js and narrow
panel in workbench.html; focused SQLite/HTTP/controller/browser tests; existing CI/
aggregate registration; README and this compact plan/review. Preserve fixed-set,
release/rights/review/history, image/provider/generator, producer pins/fixture bytes.

## Acceptance

Real persistence/reopen, strict malformed/enums/types/Unicode/limits/route rejection,
no record/history/enrollment mutation,100searchcap/atomic failed create, CAS rename/
delete, query matching grows with new records while fixed pairs stay fixed; exact
LF/CR/CRLF and literal-backslash metadata. Controller held GET/query/list/write,
manual input/search/open/cancel/departure and no replay/late publication. Real
Chromium save/open/reopen/new matching record/dirty editor/fixed selection/preview/
stale pair/export blockers, rename/delete/cancel, desktop390px captures. Full
registered local aggregate on final clean committed source, source/artifact audit
and independent review. No model inference/download/training or new simulation.

Independent implementation review cleared complete nested JSON handling, bounded
LIMIT101 listing, unknown5xx no-replay guidance and QA validation before allocation.
Focused eight saved-search Python tests, real collection controller tests, actual
QA25 caller probes and real Chromium workflow pass. Full final-head evidence is
kept in ignored build/qa and external qualification receipts, not in Git.
