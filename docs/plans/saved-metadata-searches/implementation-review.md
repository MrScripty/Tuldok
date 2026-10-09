# Independent saved metadata search implementation review

Reviewed the working candidate against base
`2ebe101f88e1ef50d9e0fb449d6f1fda8dfaeae2` on 2026-10-08. Reviewed the new
storage owner, strict HTTP routes, pure query-criteria extraction, browser
controller and panel, CI/QA routing, tests and browser evidence. No production
edits, provider execution or public actions were performed by this reviewer.

**Admitted for local commit and exact-head aggregate qualification. No remaining
blocking finding.** This is implementation admission, not a claim that an
uncommitted browser run qualifies the future committed head.

- Storage is metadata-only and additive. Criteria remain immutable; rename and
  delete use revision CAS under the existing lock/transaction. The 100-search
  cap, bounded listing, exact schema/index/trigger rejection and malformed stored
  state checks fail closed without record, asset, review or history mutation.
- Saving captures entered criteria before casefolding. The extracted query
  helper preserves existing matching, ordering, pagination and casefolded query
  response behavior. The saved-only single-line `q` subset is explicit; JSON
  restoration retains normalized exact metadata containing LF, CR and CRLF.
- Open validates identity and the closed receipt before restoration, fences raw
  filter snapshots and query/filter/lifecycle epochs, and guards collection
  publication after restoration. Held reads, cancellation, departure and
  no-event edits retain current ownership. CRUD/list callbacks do not acquire
  editor, fixed-selection, review, release-proof or history ownership. Reload
  lists searches without applying one.
- The reported complete deep-JSON failure is repaired: UTF-8/duplicate/finite
  parsing also catches recursion errors; the actual HTTP regression rejects a
  32,000-byte nested value with 400 and an unchanged list. Stored criteria use the
  same parser. Listing now selects at most 101 IDs before materialization.
- QA output validation now precedes temporary allocation and child launch,
  honors `TULDOK_SOURCE_ROOT`, and passes actual caller default/override probes.
  Network and 5xx write failures give unknown-outcome/list-inspection guidance
  and never replay automatically. Positive delete ownership is covered.

Independently reran eight saved-search Python tests, nine existing metadata-filter
tests, the production-controller VM suite and the QA routing suite (25 actual
caller probes); all passed. Inspected the final precommit real Chromium oracle
and session at `build/qa/saved-searches/run-gUaYpz`, its frozen one-record archive,
and the 390px JPEG. The session reports PASS and demonstrates changing dynamic
matches while preserving dirty editor contents, exact fixed revision pairs and
the existing release proof/URL; deliberate stale fixed pairs block release.
Rename, cancel/delete, reload, exact multiline metadata and held real GET
ownership are exercised. The narrow panel is visible and fits the viewport.

One optional UI refinement remains: after an acknowledged write, a failed list
refresh can leave the truthful success message and an older dropdown because
the write's list epoch has retired. It neither replays the write nor modifies
dataset owners; explicit Refresh searches remains available. This is not an
admission blocker.

Final acceptance still requires the committed source's full registered aggregate,
source/fixture stability and direct ignored artifact audit. No tracked review
updates should occur during that exact-head run.
