# Explicit collection metadata filters

## Objective and authority

Expose the existing dataset-workflow collection's label, protected group and
rights-note dimensions as explicit criteria. Repository dataset-workflows plans
and the parent's independent next-slice delegation authorize this bounded work.
Main remains frozen for UI decisions. Bulk real-data import and generation-job
compatibility belong to another worker and are excluded.

The owner authorized independent branch development and draft publication. This
work uses its own `/workspace/Tuldok-metadata-filters` worktree and repo-local
MrScripty <TheEnvironmentGuy@protonmail.com> attribution. No global settings,
credential repair, history rewrite, merge, external model/dataset or ONNX download.

## Contract and acceptance

- Optional `label`, `group`, `rights` query parameters combine with all existing
  collection criteria using AND. Trimmed values match case-sensitively; blank
  means unrestricted. Limits are 80, 120 and 1,000 Unicode code points, respectively.
- Label means a current class, box or entity-span target label. Caption and source
  words do not become labels. Group means an ID stored directly on the record;
  release-family and ancestor expansion stay in the release subsystem.
- Rights means arbitrary provenance-note text, without permission or license
  classification. Absent, null, blank and literal lowercase `unknown` notes project
  as `unknown`; uppercase `UNKNOWN` remains arbitrary text. Original provenance
  remains intact. Page records gain only a read-only `rights_note` projection.
- Apply criteria before total/analysis/sort/pagination. UI transports Unicode and
  reserved characters, supports keyboard submission, shows errors and recovers.
- Results remain dynamic. Searching again can find new matching records without
  adopting them into selected pairs, saved fixed membership or existing preview
  proof. Opening a fixed set preserves criteria. Saving/loading/filtering never
  grants human review. Exact preview/export still validates freshness independently.
- Qualify real storage/API, deterministic controller ordering, real Chromium,
  pagination, combined criteria, maximum Unicode lengths and narrow layout.

## Provisional ancestry and integration touchpoints

The unpublished metadata patch originally targeted PR5
`991a22beb5a69272571dd3731cfb8392154725f7`. It was paused for the independently
reviewed ordering repair. Parent subsequently authorized resuming on provisional
PR6 `2311f7cd0eaaf6c6a89e259ddf5c340f3a9ca887`, branch
`fix/saved-selection-intent-20261006`. The unpublished feature ref fast-forwarded
to that descendant and the preserved patch replayed cleanly. Paused patch SHA256:
`c78128c010ad6a238c2207977e6fa7b251711486106494543d9e9ed388119c6c`.
The original feature commit `e925514671743883b6ff9fe34c851cf36560f036` has that
exact PR6 commit as its parent and remains preserved. Review repairs append commits
on the same PR7 branch. Draft targets PR6; parent owns reviewed integration and any
retargeting. PR6 stays stable.

Shared touchpoints, reported early: `Workbench.query`, the collection HTML/JS/CSS,
README and CI. Existing API route is unchanged. `app.py`, `saved_selections.py`,
`static/saved-selections.js`, release implementation, `synthetic.py` and
`image_generation.py` are unchanged from PR6. No new schema, saved-search storage,
taxonomies or persistence migrations. Exact queries are dynamic criteria, not a
new persisted-search feature.

Protected published refs include main
`2fc4a46f12d73a0fa467d5482f68edb83d6df6af`, PR4
`a3f3cbead4137110dfa8af81c94178e6d53aa036`, PR5 and PR6 above, plus every other
existing branch recorded immediately before publication. All must remain unchanged.
Applicable Coding-Standards guidance was read from pinned
`dcc56f26e884ade260770beceba2501d3746200d`. Standards authoring skill excludes this
ordinary source edit. No manual CodeRabbit request.

## Ownership and next step

Implementation and local qualification complete; publish the independent draft
and inspect exact-head hosted run/job metadata. Parent owns independent review,
PR6 integration, UI decisions and retirement of retained worktrees and guidance
checkouts. Worktree remains retained-protected for that review. See
[verification](reports/verification.md) for evidence and limits.

## PR7 line-ending review repair

Parent review identified valid internal CR/LF being stripped by single-line exact
filter inputs. Real Chromium against preserved e925514 confirms LF, CR and CRLF
each match one record via the API but zero after input sanitation. Backend/storage
semantics already preserve those distinctions; do not change them.

Add explicit JSON-string entry for all three exact criteria while retaining plain
entry. Decode before building the query; accept only JSON strings, or blank for
unrestricted. Ordinary values convert between formats. Conversion to plain is
atomic and rejects values with CR/LF, preserving previous fields/format. Input
length allows a maximum legal value even with every supplementary character encoded
as a JSON surrogate pair. API code-point limits and existing trimmed exact matching
remain authoritative. No textarea line-ending normalization or stored-value rewrite.

Regression evidence must inspect actual submitted codepoints for LF, CR, CRLF,
ordinary text, literal backslashes/quotes and maximum escaped Unicode, including
dynamic results, fixed pairs and preview-token preservation. Repair only PR7's
existing branch, with preserved before/after evidence; main/PR5/6 and generation
modules remain unchanged. See [repair evidence](reports/line-endings.md).
