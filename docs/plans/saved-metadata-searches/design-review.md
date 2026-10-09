# Independent saved metadata search design review

Reviewed the plan against base `2ebe101f88e1ef50d9e0fb449d6f1fda8dfaeae2`,
including Workbench `_filtered`/`query`, exact-filter input conversion, guarded
collection refresh, Curation, SavedSelections and their UI/history owners. No
production edits, provider execution or public actions. No applicable local
AGENTS or skills found.

**Admitted for implementation with the decisions and requirements below.** The
existing fixed-set plan explicitly reserves a separate dynamic mode. An additive
metadata-only owner and a pure criteria helper satisfy that separation; opening
a dynamic search must not call fixed-set loading or editor/release mutators.

- Save entered criteria, independent of the applied collection page. Persist the
  existing trimmed normalization, with `q` before casefolding. Two hundred `ß`
  input characters produce four hundred casefolded characters; saving or validating
  `page.criteria.q` would reject a valid entered search. Keep casefolding solely
  in matching and the existing query response projection. Preserve current query
  defaults, exact-filter trimming, matching, sort/tie-breaks and pagination.
  Shared validation must accept the query owner's optional fields while the new
  saved-search envelope requires exactly its eight string criteria.
- Reject CR/LF in saved `q` as an explicit representability subset of the existing
  single-line control. Leave the existing query API unchanged. Restore normalized
  label/group/rights through JSON strings, retaining interior LF, CR, CRLF and
  literal backslashes; do not claim preservation of spelling already removed by
  existing outer-whitespace trimming. Set both exact-filter format owners together.
- Create/list/load/rename/delete must never call `_filtered`, `_all`, `_get` or
  image enrollment. Validate criteria directly without touching records, assets,
  review, rights, history or preview proofs. Enforce the 100-search cap and CAS
  mutation within the existing lock/transaction; booleans are not revisions.
  Keep criteria immutable, with explicit dynamic mode/schema version. Reject
  unsupported pre-existing table shapes/constraints/triggers rather than silently
  adopting them. Fail closed on malformed stored criteria or unsupported versions.
  Use the proposed strict UTF-8, duplicate-free, finite 32 KiB write routes and
  strict route/identifier/action handling; keep metadata listing bounded.
- Before a held Open may restore fields, compare lifecycle/Open epochs, filter
  intent, query epoch, chosen saved ID and a snapshot of all raw filter values and
  format. Event epochs alone miss no-event reset/programmatic changes. After the
  synchronous restoration, capture the restored raw snapshot and expected query
  ownership for guarded refresh. Later input/query/Open/cancel/departure retires
  its publication authority. Query cleanup must still retire Diagnostics pending
  ownership when publication loses authority, as in the existing shared refresh.
- Validate exact receipt keys, primitive types, bounds, dynamic mode/schema,
  unique list IDs and requested identity before touching form fields. Keep list,
  write and Open response ownership explicit: old list/write acknowledgements
  cannot overwrite a newer dropdown/status or reapply captured filters. Pagehide
  retires callbacks and releases owned controls; no automatic replay follows an
  unknown create/rename/delete acknowledgement. Duplicate names remain distinct
  IDs, with no durable exactly-once promise.
- Opening may refresh only the collection and filter controls. Preserve exact
  selected record/answer/preference revision maps, dirty editor contents, release
  proof ownership and the history URL. Saving and CRUD only update their own list
  and status; reload never automatically opens a saved search.

The parent's refinement to compare raw snapshots in addition to epochs and use
separate lifecycle-fenced write handling addresses the main async design risk.
The planned pure-validation/no-enrollment probes, query-equivalence tests,
casefold-boundary cases, persistence/CAS/cap failures, malformed receipts, held
Open/list/write/query controls and real browser fixed-set/editor/release coverage
are appropriate. Include invalid future SQLite schema and a no-event filter-reset
case explicitly. Independent implementation review and final exact-head aggregate
qualification remain required; this review identifies no fundamental blocker.
