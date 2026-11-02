# Authored model organization

The project workspace can display an adopted `.portfolio.json` note as an
authored guide to model fits/components. This is separate from **Experiment
progression**, which retains genuine Study/Trial ancestry. Group edges mean
authored grouping; they do not establish derivation, admission or scientific
acceptance. Relationship notes have explicit comparison/parameter meanings and
source excerpts. Missing historical Trial ancestry stays unknown.

## Retained document

`project_model_portfolio_v1` is a UTF-8 JSON note of at most1MiB with exactly:

- `format`: the fixed string above; `project_id`: the owning32hex project ID;
- `title` (1–200characters), `description` (1–8,000characters), and
  `authorship`: `retrospective`;
- `groups`: at most64records with exact fields `id`, `label`, `parent`,
  `description`. IDs are unique, parent is null or another group, and grouping
  is acyclic;
- `models`:1–1,000records with exact fields `id`, `label`, `group_id`, `aliases`,
  `review`, `card`, `summary`. Each unique ID names an authored model entry,
  not necessarily a complete generator, Trial or unique parameter state;
- `relationships`: at most2,000records with exact fields `from`, `to`, `kind`,
  `explanation`, `evidence_model`, `excerpt`. All model references exist, endpoints
  differ, and each ordered endpoint/kind tuple is unique.

Group/model IDs contain1–160ASCII letters/digits or `._:/-`, beginning with a
letter/digit. Group labels are at most200characters, model labels/aliases500.
Each model has at most128unique aliases. A card reference has exact fields
`file_id` (64hex), `path` (a relative `notes/` path up to512characters without
empty/dot/dot-dot components), positive integer `revision`, and64hex `sha256`.
These are exact captured note references, never source-reading capabilities.

Review is `source_reviewed` or `review_pending`. Reviewed summaries have exactly
six nonempty strings, each up to16,384characters: `method`, `purpose`,
`experiment`, `outcome`, `lesson`, `reproduction`. Pending summaries are null.
This status is an author's source-review statement, not numerical qualification.
Relationship kind is `comparison` or `parameter_derivation`; the latter points
from derived model to parameter source and must be acyclic. Explanation is at
most8,000characters and exact excerpt at most16,384. Comparisons are authored
context, not permission to combine incompatible metrics/populations.

## Ownership and reads

The ordinary project-file owner captures/revises the note, authenticates reads,
verifies captured UTF-8 bytes/hashes and retains previous revisions. There is no
new canonical family, SQL table, execution grant, recipe or mutation interface.
Existing `files_inspect` and `file_get` contracts are unchanged. Save/load keeps
the original guide and referenced note history. A fork whose new project/note
identities differ requires an explicitly re-authored guide; the reader refuses
foreign identities instead of retargeting them silently.

`ProjectModelPortfolioDocument` owns the presentation-document decoder and
cross-reference/literal checks. `ProjectModelPortfolio` owns selection,
presentation and its pending reads. Its injected `read` must be the host's
already negotiated, current-authority, byte-verified project-file reader.
The host owns transport/hash validation and context identity. The controller
checks the exact model card ID/path/revision/SHA/project, and that all six
summary strings and that card's relationship excerpts occur literally in its
captured text before displaying a selected summary. Text is inert; no markup,
scripts, parameter loading, scientific scoring or source execution occurs.

Only explicit actions read notes/cards. Discovery visits40adopted files per
page; no hidden scan/retry/polling occurs. The guide holds at most1,000models,
shows20per graph window with their ancestor groups, and reports exact total,
reviewed and filtered counts. Group/name/alias/review filters, paging and
textual relationship controls select the same entries as graph buttons.
Paragraphs wrap; exact source text remains in a disclosure.

The host's binding/project/checkpoint/credential/generation context owns every
read. A context change, permission loss or teardown aborts pending work, clears
old content and restores focus to the host status when needed. Late replies
cannot publish into another context. Errors show their declared diagnostic and
clear old detail instead of displaying a previous model as the new selection.
Unsupported format or foreign-project binding is `unsupported`; malformed
document/reference/summary is `invalid`; transport/availability failures retain
their owning diagnostic. No success or empty-data fallback substitutes for a
failed read.

## Verification scope

Pure codec tests cover contract decisions using literal fixtures. Controlled
read and real-browser tests cover selection, unavailable/obsolete responses,
repeated invocation, focus, keyboard activation and wrapping on desktop/mobile.
Those fixtures do not establish real project capture or save/load. Native
acceptance additionally requires an actual adopted guide, exact original cards,
current authority, real project reads and retained checkpoint/custody evidence.
