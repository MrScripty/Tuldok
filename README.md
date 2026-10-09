# Tuldok

A local dataset studio for image, text, mesh, and native simulation evidence. Acquire original assets, author explicit targets, review exact revisions, and export immutable datasets through named consumer contracts. The book-corner editor remains available. Tuldok is a separate developer tool; it does not depend on Book-Be-Gone. The UI remains provisional.

## Run

Requires Python 3.12+ with the pinned dependencies in `requirements.txt` (Pillow and NumPy2.5.3). There is no JavaScript build step. Manual labeling needs no external service.

    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
    .venv/bin/python app.py

Open http://127.0.0.1:8091. Change the port or data location with --port and --data. Camera access works on localhost; accessing a machine over the network requires HTTPS for browser camera access. Image import also works without camera access.

## Workflow

1. Set a book ID and recording session ID. Use a new session for a different lighting/background setup. Leave the book ID empty for no-book scenes.
2. Start the camera and capture immediately or with the seven-second timer. Import JPEG, PNG, or WebP images individually or in batches.
3. Select a corner using its numbered control (or keys 1–4), then click its location. Drag to refine; arrow keys nudge, Shift makes a larger nudge. Initial ghost markers are not labels: all visible corners must be placed explicitly.
4. Label the whole open spread or closed cover, clockwise from the book’s top-left as it would appear upright, without padding. Mark corners hidden or outside the frame rather than guessing coordinates. Choose “No” for empty scenes.
5. Save, or Save & next to advance to the next unlabeled image. Returning to Camera keeps the live camera available.
6. Export labeled images as a ZIP containing images/, labels.jsonl, and schema.json. Unlabeled samples are excluded. Unassigned splits remain explicitly unassigned.

Select an image in the collection and click **Delete image** to permanently remove
its original file, thumbnail, normalized image, and saved label. The confirmation
also covers unsaved edits. The next image opens automatically. Deleted images are
excluded from future exports; previously downloaded exports are unchanged. Generated
images stay deleted when their job resumes, and job progress shows the deleted count.
If another tab has edited an image, reload before deleting it.

## Import a real corpus

In the dataset workbench, **Import a real corpus** accepts a local UTF-8 JSONL
manifest with one raw asset per physical line and explicitly selected image
files. Start with raw assets; annotate and review them afterward. For example:

```jsonl
{"kind":"text","name":"Note","text":"A real source note","groups":["document-01"],"rights":"Authored"}
{"kind":"image","file":"photo.png","groups":["shoot-01"],"rights":"Permission granted"}
```

`kind`, a nonempty `groups` list and the matching `text` or `file` field are
required. `name`, `parents` (existing record IDs) and `rights` are optional;
omitted rights remain `unknown`. Each image reference must be a flat filename
matching exactly one selected file, with exact spelling and case. Missing or
ambiguous matches are row errors. No server paths, URL fetches or archives are
used. Supplied annotations, tasks, review states, provenance, duplicate JSON
keys and other unknown fields are rejected. Existing annotated corpus formats
require a separate field/coordinate contract.

Limits: 8 MiB per manifest, 1,000 physical lines (blank lines keep their source
number but are skipped), 3 MiB per UTF-8 JSON row, existing 200,000-code-point
text and 25 MiB / 40-megapixel image limits. LF and CRLF are supported; source
text remains original while its canonical form uses NFC and LF. Image originals
remain intact while the existing owner normalizes EXIF orientation/RGB pixels.
All imported records are unlabeled drafts, independent of supplied source claims.

Imports run sequentially and show per-row outcomes and record IDs. Valid rows
remain when another row fails. Repeated canonical text or exact original image
bytes are rejected without modifying existing records, review or provenance.
Storage failures stop scheduling. **Stop after current row** prevents the next
admission; an in-flight row may complete and remains in the collection.

Lost or malformed responses pause the batch without automatic retry. **Check
pending row** reads a saved acquisition marker and verifies the row proof before
crediting creation. No visible result does not prove the request stopped.
**Dismiss pending check** does not roll back an import; inspect the collection
before retrying. These controls retain existing editor edits and selection.

After the batch stops, **Add confirmed imports to selection** adds its confirmed
records across collection pages. Existing selected revision pairs take precedence;
repeated clicks retain them. Pairs reflect admission or saved-result confirmation,
so later edits can make them stale. The entire action is rejected above 5,000
selected records. Then use **Save selected records as a new set** to retain fixed
membership. Selection grants no review or export approval. Results remain in this
page until another batch or reload; explicitly saved sets persist.

Provenance records the server-computed source-row SHA-256 and the existing
source-byte/pixel hashes. Manifest filename, physical row number and image-file
label are caller-declared context, stored separately from those derived facts.
The manifest itself is not copied or independently authenticated. Result lookup
is read-only; the request marker does not grant annotation review or source rights.

## AI corner suggestions

Open **AI model**, choose Codex, OpenRouter, llama.cpp, or Pumas, and select a vision model. With an image selected, click **Suggest corners**. Adjust the returned pins and visibility flags, then **Save**. Suggestions remain unsaved until reviewed; invalid results leave your current pins intact.

- **Codex:** install and sign in to the Codex CLI on the Tuldok computer. Uses its app-server interface, cached model catalog, and selected thinking level. `TULDOK_CODEX_MODEL` overrides the default model.
- **OpenRouter:** enter an API key or set `OPENROUTER_API_KEY` on the server. Refresh models lists image-capable models advertising structured outputs. The entered key stays in the current page; it is not written to browser storage, labels, or exports.
- **llama.cpp:** run a vision model with its required image projector and supply the server URL (default `http://127.0.0.1:8080`). Refresh models reads its model list. The server must be reachable from the Tuldok computer and support image input and JSON schema output.
- **Pumas:** serve a vision model and click **Scan local ports**. Tuldok lists ready Pumas gateways and local llama.cpp model endpoints, including a separate endpoint when Pumas manages the model there. Select the endpoint that lists your VLM, or enter its URL manually, then refresh models. The model must support image input and JSON output.

The adapters follow Book-Be-Gone's provider interfaces without depending on that repository. Each request sends a JPEG copy of the selected image, at most 1600 pixels on its longest side, preserving orientation and aspect ratio. Original dataset images remain intact. The prompt in `prompts/corners.md` asks for screen-relative corner positions plus an explicit identification of the book’s upright top-left from its text or artwork. Tuldok rotates the handle identities into book order while preserving image coordinates and visibility. Ambiguous orientation requires manual labeling; no-book scenes remain supported. Saved suggestions include provider/model provenance in `suggested_by`; they still need human review before use as training labels.

Requests time out after 180 seconds (`TULDOK_AI_TIMEOUT` overrides this), with a 60-second response-progress limit. Requests are not automatically retried. Model settings are remembered locally; API keys are excluded.

## Generate images with Pumas

In Pumas, install and activate a compatible Torch runtime, create a Torch runtime
profile, and serve the supported image model. Copy the **Pumas gateway URL** into
Tuldok’s **Generation** settings, then refresh the model list. Alternatively, click
**Scan local ports** to find Pumas on the Tuldok computer, including automatically
assigned high ports. The only gateway with ready image models is selected automatically, even when
other idle Pumas instances are running. An already selected gateway with ready image
models is retained; if several usable gateways remain, choose from the results. Selection fills the URL and refreshes image
and prompt models (unless a separate prompt server is configured). Discovery checks
Pumas model ownership or its read-only launcher RPC, including gateways with no
loaded models. The scan uses Linux listening-port information and probes loopback
HTTP services with a ten-second scan budget. Remote or HTTPS gateways can still be
entered manually. The image list
includes only ready models advertising image generation. A llama.cpp router URL
will not provide this image workflow.

Use the **Camera capture / Generation** toggle above the workspace. Set the collection
book/session metadata, describe the dataset, and choose an image count (1–10,000).
Select one of two strategies:

- **Create unique prompts with an LLM:** select a Pumas prompt LLM (and optionally a
  separate server URL). Tuldok prepares prompts in batches of 10 before rendering.
  Each batch receives the brief, its position in the dataset, and at most 10 recent
  prompts. Exact duplicates, ignoring whitespace and case, are removed across the
  whole job. Repeated duplicate output stops preparation with a resumable error.
  Semantic variety and adherence to the brief still depend on the selected models.
- **Use the same prompt for every image:** Tuldok renders the description repeatedly,
  creating only the next pending gallery entry as it proceeds.

Choose the image width and height (default 1280 by 720) and an optional starting seed. The seed increments for each
image; leaving it blank lets Pumas sample randomly. Click **Generate dataset**.
Prompt entries appear in the collection and become images as generation completes.
Click a pending entry to inspect its prompt. Completed images immediately support
manual labeling or **Suggest corners**, with the same review-and-save process as
camera captures. Original PNG bytes and generation provenance are retained; labeled
exports include the individual prompt and returned generation metadata.

Jobs and prompt entries are saved in SQLite. Generation continues while you label
images or reload the browser. **Stop generation** cancels the image request, or waits
for the current prompt batch to return (up to 180 seconds), then stops scheduling
work. **Resume remaining images** continues cancelled, failed, or server-interrupted
jobs without redoing saved images. One job runs at a time. A rendering failure stops
the queue for inspection; images are not automatically retried. Exact duplicate
images remain rejected by the dataset, including repeated deterministic output.

Image requests have no duration deadline: generation runs until it completes,
fails, or you explicitly cancel it. Only connection establishment stays bounded;
once admitted there is no total, read, idle, or elapsed timeout. GPU cancellation
may need to reach the runtime’s next cancellation checkpoint. If the response is
lost before completion, the outcome is uncertain — provider work may have
continued — and the request is not automatically retried. After a server restart,
explicitly resume unfinished jobs. Returned generation metadata may gain
additional public fields over time. Keep the dataset backed up and review
synthetic images and labels before using them for training.

## Explicit collection filters

In **Dataset workbench**, combine the existing search/type/task/review/sort controls
with **Target label (exact)**, **Protected source/group (exact)** and **Rights note
(exact)**. All criteria must match. Leave a criterion blank for any value; nonempty
values are trimmed and compared case-sensitively. A label matches a current class,
box or entity-span label, not words in a caption or source. A group matches an ID
stored directly in the record's protected `groups`, not all ancestors or connected
release-family members.

Rights notes remain arbitrary recorded text, not license categories or permission
decisions. Missing, null, blank and literal `unknown` notes display/filter as
`unknown`; other notes retain their text, including uppercase `UNKNOWN`. The
collection shows each record's group IDs and rights note so exact criteria can be
chosen. No metadata, annotation, revision or review changes during filtering.

`GET /api/workbench/records` accepts optional `label` (up to 80 Unicode code points),
`group` (120) and `rights` (1,000) alongside its existing parameters. Invalid values
return HTTP 400 / `invalid`. Returned page items include a read-only `rights_note`
projection; original `provenance.rights` is preserved. Analysis and total counts
describe the complete filtered result before pagination. Browser controls allow
the full valid Unicode lengths; the API remains the validation authority.

Use **Exact filter entry → JSON strings** for values containing internal line
breaks. Enter double-quoted strings: `"first\nsecond"` preserves LF,
`"first\rsecond"` preserves CR and `"first\r\nsecond"` preserves CRLF.
Escape a literal backslash as `\\` and a quote as `\"`. Blank fields still mean
any value. All three exact criteria use the selected entry format; ordinary
criteria convert without changing their meaning when switching formats. Invalid
or non-string JSON produces an error without issuing a query. Switching back to
plain text is blocked while any criterion contains a line break. This keeps
exact codepoints intact rather than relying on single-line or textarea line-ending
normalization; stored metadata and API matching semantics remain unchanged.

Filtered results are dynamic: later matching records can appear after searching
again. They do not join fixed saved membership or replace chosen revision pairs.
Opening a fixed set preserves the current filter; filtering never grants review,
creates release proof, or changes an existing exact-selection preview's membership.
Release export still rechecks source/revision/lineage freshness independently.

## Saved fixed selections

In **Dataset workbench**, choose records with the checkboxes, enter a selection
name, then **Save selected records as a new set**. A set contains fixed record IDs,
annotation/source revisions, and source hashes. Filters and searches remain live
collection controls; new matching records never join a saved set automatically.
Dynamic saved searches use a separate panel and never supply membership. Names may
repeat; each set has its own ID. Saving creates a separate set rather than replacing
membership.

Choose a saved set and **Open fixed selection** to replace the current selection,
including records outside the current filter. The current filter, release settings
and unsaved annotation edits stay intact. Opening always clears previous export
proof and requires a fresh release preview. **Cancel opening** keeps the current
selection and ignores a delayed response. The `#selection=ID` URL reopens the set
on reload and Back/Forward navigation. Saving or opening never changes annotations
or grants human review; draft records remain ineligible for release.

Initial URL opening stops if a newer selection action or navigation occurs while
the saved-set list is loading. Opening a fixed set also revokes an earlier editor
save's ability to advance its selected revisions. That annotation save may still
persist successfully; the older selected pair stays stale and release-blocked.
Explicitly select the current records to adopt their newer revisions. Ordinary
editor saves can advance the selected pair they observed only while that exact
pair and selection intent remain current.

Reopen reports stale revisions, missing records, deleted images, unavailable bytes,
and changed source identity while retaining every original saved reference. It
never substitutes newer revisions or replacement images. These are references,
not historical source/annotation copies: to release updated records, explicitly
select their current revisions and save a new set. Frozen ZIPs remain separate.
Rename and delete use saved-set revision checks; deleting a set retains records,
the current selection, and existing exports. Back up the whole data directory.

`GET /api/workbench/selections` lists metadata. `POST` on that route accepts exactly
`name` (1–120 characters) and `items` (1–5,000 distinct `{id, revision,
source_revision}` objects). `GET /api/workbench/selections/ID` returns `selection`
(`mode: "fixed"`, `schema_version: 1`, immutable `items` with source identity),
per-member `status`/`message`/current revision pairs, and `current`, which describes
currency rather than review or release eligibility. POST `.../ID/rename` accepts
`name` and saved-set `revision`; POST `.../ID/delete` accepts only `revision`.
Stale mutations return HTTP 409 / `conflict`; a deleted set returns 404 / `unavailable`.
For release preview, project saved items to `{id, revision, source_revision}`.

## Saved dynamic searches

**Saved searches · dynamic results** stores the entered search/filter values,
even before **Search collection** is clicked. **Open dynamic search** explicitly
applies them to the current collection, starting at page 1. New matching records
can appear; selected record/answer/preference revisions, editor drafts, fixed sets,
review decisions and history URLs remain separate. Reload lists saved searches
without automatically opening any. Exact metadata values restore through JSON
entry, preserving interior LF/CR/CRLF and literal backslashes. Search text is
single-line. Names may repeat; criteria are immutable, so save changed filters as
a new search. Rename/delete are revision-checked. Delete retains collection records.

`GET/POST /api/workbench/searches` lists or creates searches. Create accepts only
`name` (1–120 code points) and `criteria` with exactly `q`, `kind`, `task`, `review`,
`sort`, `label`, `group`, `rights`, using the existing filter limits and semantics.
`GET .../ID` returns explicit `mode: "dynamic"`, `schema_version: 1` metadata;
`POST .../ID/rename` accepts `revision`/`name`, and `.../ID/delete` accepts `revision`.
At most 100 searches and 32 KiB strict UTF-8 JSON per write. Saved searches contain
no membership or assets and grant no release authority. Unknown write responses
require list inspection before an explicit repeat; requests are not replayed.

## Selected-release preview

Select records, choose an export format and split targets, then click **Preview selected release**. This summary describes exactly the saved selected revisions, independently of the current collection filter. It shows task/review/class-target counts, eligibility blockers, connected source families (including unselected and deleted relatives), requested versus achievable splits, and format/rights warnings. Whole source families remain indivisible; ratios are targets, not guarantees of exact quotas.

Preview creates no ZIP and persists no record, annotation, review, split, or lazy image enrollment. **Freeze & export ZIP** becomes available only for an eligible current preview. Selection or release-control changes invalidate it, and late responses cannot restore an old preview. Unsaved editor changes are not part of a release.

`POST /api/workbench/releases/preview` accepts the same `items`, `ratios`, `seed`, and optional `format` as the release endpoint. It returns `eligible`, `analysis`, `blockers`, `warnings`, `lineage`, `split_report`, `assignments`, and a `preview_token` for eligible selections. Invalid/stale selections are blocked without a token; their analysis is unavailable. Lineage uses stable complete-family IDs, not a count of the visible filter's group labels.

The UI includes `preview_token` in the final release request. Export revalidates source bytes, selected revisions, relevant transitive lineage and controls under the source lock, then hashes the bytes actually archived. A stale token requires a fresh preview. Existing API clients may omit the token and still receive full final validation; an explicitly supplied invalid token is rejected. A preview is a point-in-time check, not a frozen release or a claim about rights, semantic independence, or model quality.

## Workbench image captions

Open **Dataset workbench** from the corner studio. Existing imported and Pumas-generated images share the original Dataset source ID and bytes. Select **image caption**, write a caption describing the visible result, save as a draft, then explicitly review it. Editing a target resets the editor's review choice to draft. Generation prompts remain source provenance; they are never used as automatic captions. Each record has one current workbench task, with previous targets retained in revision history. Corner labels remain a separate annotation.

Filter by task, review state or caption text. Select human-reviewed caption records and choose **Image captions · train/val/test** when previewing a release, then freeze the eligible selection. The `/api/workbench/releases` request adds `format: "image_caption_v1"`; omission retains the canonical mixed-task release. Captions use exactly `{"caption": "..."}` and are bounded to 4,000 Unicode code points. Unknown formats and invalid caption fields are rejected.

Caption ZIPs contain PNGs beside `train/metadata.jsonl`, `val/metadata.jsonl` and `test/metadata.jsonl`. Every row has exactly `file_name`, `text` (the accepted caption), and `group`. The existing `validation` assignment is explicitly projected to `val`. All three splits must be nonempty. Connected protected groups, parents, duplicate identities, book/session assignments and retained deleted ancestry share a component ID; the export never chooses an arbitrary first group. Existing source splits are preserved. Conflicts, insufficient independent families, missing lineage, draft targets, stale revisions, missing/tampered bytes, unnormalized PNGs and exact decoded-pixel duplicates fail before publication. Images below 512 pixels are exported with warnings.

`manifest.json` freezes canonical annotations, source/target revisions, byte/pixel hashes, provenance, split mapping and complete relevant protected-component lineage snapshots. ZIP identity is the SHA-256 of its frozen bytes. Later edits or source deletion cannot change an existing release. Back up the full data directory, including releases. Human review does not establish rights, remove sensitive image metadata, detect near-duplicates or prove training quality.

The consumer is the training companion's `examples/diffusion/check_image_data.py`, pinned to SHA-256 `6a4394308a4cc69b4ca965aca7f8459d7711ac9d51ce70492562c6ec6d806f94`. Extract the ZIP and run:

    python3 /path/to/check_image_data.py /path/to/extracted-release

The unchanged pinned snapshot in `tests/fixtures/diffusion_check_image_data.py` is used for producer/consumer contract tests. An alternate checkout may be supplied through `TULDOK_CAPTION_CONSUMER`; tests reject a different hash. This milestone runs no model training or paid inference. [Contract](docs/contracts/dataset-releases.md).

## Dataset conventions

Coordinates are normalized against the oriented image: x/(width-1), y/(height-1). Each annotation has book_present, crop_suitable, and corners in the order top_left, top_right, bottom_right, bottom_left. A corner has visibility visible, occluded, or out_of_frame. Invisible corner coordinates are null. A no-book sample has crop_suitable=false and an empty corner list. Crop-suitable labels require four visible, placed corners. Visible quadrilaterals must be clockwise and convex. New labels use corner_reference=book: identities follow the book through rotation, so an upside-down book’s top-left corner is at the image bottom-right. Coordinate values always remain in image space. Existing labels without this field are interpreted and exported as corner_reference=image; untouched labels retain that convention. Placing, moving, or clearing corner positions switches the edited label to book orientation. The Corner reference control can explicitly retain image orientation when needed. Export schema version 2 records this distinction per annotation; training should select or explicitly convert conventions rather than mix them.

The original uploaded bytes are preserved at data/images/ID/source. The labeling and exported image.png is a lossless PNG of the decoded, EXIF-oriented RGB image; normalization makes browser display and training coordinates agree. Camera captures use full camera dimensions, with JPEG encoding. No crop, resize, or automatic detector alters the labeled frame.

Book IDs group related frames. Assigning a training/validation/test split applies to all previously unassigned images with the same book ID. No-book images without a book ID are grouped by session. Conflicting assigned splits are rejected. Reserve whole books and sessions for evaluation; this tool enforces group consistency, but you choose which groups to hold out.

Labels and metadata are stored in SQLite with optimistic revision checks. Stale tabs cannot overwrite newer labels. Exact duplicate source images are rejected. Unsaved editor changes are protected when navigating away. Back up the entire data directory, including source files, with the application stopped.

## Scope

This first version supports still capture and image import, including frames extracted from videos elsewhere. It does not yet record video, extract/deduplicate video frames, or train models. Bounded human-authored polygon labels are available through the dataset workbench; see the [polygon contract](docs/contracts/polygon-segmentation.md). Exports include images and metadata but omit original source bytes. Manual labeling stays local; optional AI suggestions send the selected image to the configured provider.

## Tests

    python3 -m unittest discover -s tests
    node tests/browser.cjs
    node tests/browser_images.cjs
    node tests/test_workbench_controller.cjs
    node tests/test_saved_selections_controller.cjs
    node tests/test_saved_selection_intent.cjs
    node tests/browser_workbench.cjs
    node tests/browser_grounded.cjs
    node tests/browser_captions.cjs
    node tests/browser_release_preview.cjs
    node tests/browser_saved_selections.cjs
    node tests/browser_saved_selection_intent.cjs
    node tests/browser_metadata_filters.cjs
    node tests/browser_bulk_import.cjs
    node tests/browser_dataset_integration.cjs

The browser smoke test requires Node 22+ and Chromium/Brave. Set BROWSER to the browser executable. It uses a synthetic camera, a temporary dataset, and local fixtures for all four AI providers. Tests do not contact paid models.

Generated QA outputs use fresh ignored `build/qa/` directories. Ordinary screenshots
use JPEG quality 85; authored fixture images remain lossless. See [QA commands,
retained inputs and fixture provenance](docs/qa/README.md).

## Native simulation and mesh assets

The development workbench can import a complete bounded Rheon simulation sequence
from **Import Rheon simulation sequence**. For version 1 select `run.json` and
`frames.jsonl`. For producer version 2 also select the original `controls.json`. Give it a name and a rights note, then open the imported collection
record to inspect its original metadata and nine-entry frame index. Imports remain
**draft** until a person inspects the data and explicitly saves **Human reviewed**
with a review note. Contract checks do not grant human review or establish permission.

This adapter is pinned to [Rheon draft PR 20](https://github.com/MrScripty/Rheon/pull/20)
at `fee7b4a139574f87b259796b1ba8698a41d31ac1`; it does not assume that PR is merged.
The unchanged stdlib validator is retained in `rheon_sequence_contract.py`, derived
from the exact producer `tools/import_dense3d_sequence.py`. Producer provenance is
preserved as declared evidence; hashes detect byte changes, not source authenticity.
The producer's base commit and each run's declared source commit remain distinct
from the adapter's pinned contract commit. Contract changes need coordinated review.

Producer-v2 controls use [Rheon draft PR 32](https://github.com/MrScripty/Rheon/pull/32)
at exact `020437fa638ad56823b544ba1f9207ceef065f12`. The source-pinned
`rheon_controls_contract.py` preserves the producer validator except its v1 dependency
import alias. It validates all eight controls against adjacent native stamps and
times, raw hashes and the exact run binding. Producer origin remains a declaration;
these checks neither authenticate the executable nor grant human review. Version-1
authored sidecar inspection remains independent. The folder importer accepts v1 pairs and producer-v2 triples, including mixed folders.

Consumer limits are 64 KiB each for `run.json` and optional v2 `controls.json`,
2 MiB for `frames.jsonl`, 256 KiB per
JSONL line, exactly nine frames (constructor plus eight accepted steps), and exactly
16×8×4 cells. The HTTP import envelope is capped at 3 MiB. Completion, SHA256,
byte counts, exact geometry/axes/shapes/types/units/configuration, finite native
numbers, canonical decimal u64 stamps, accepted time/dt and diagnostic associations
are validated before any asset, record or initial history is published. Publication
shares one SQLite transaction with the existing Dataset owner.

Velocity X/Y/Z retain their named MAC staggering, separate shapes and f32 types;
tracer stays f32 appearance data, fraction/pressure stay f64. Pressure is the last
accepted interval projection, not independently evolved endpoint pressure. Download
the original bundle to inspect every dense field. No images, cell-centered vectors
or flattened-time records are synthesized. The fixed fixture supports represented
fraction donor transport with an all-fluid constant-density carrier. It does not
qualify free surfaces, two-phase inertia, material calibration, multidirectional
accuracy, performance or training quality. This import facility does not qualify a training model. The separate native
numerical reader is described below; an actual training objective remains an input.

Each trajectory is one indivisible record. Automatically protected trajectory and
initial-condition family groups cannot be removed; related initial families and
parent/source groups stay together in the existing connected split allocator.
Canonical releases require human-reviewed sequences and package each exact original
two- or three-file bundle as an `assets/ID.zip` with typed metadata in split `records.jsonl`.
Selected sequence bundles have a synchronous aggregate limit of 40 MiB, including
saved-selection source checks. Rights-note corrections, optimistic revisions and
append-only review history use the existing workbench controls.

The malformed-input Python suite and `tests/browser_sequences.cjs` use explicitly
source-derived synthetic data from the pinned producer tests, with synthetic
provenance placeholders. Separately, `tests/fixtures/rheon_actual_fee7b4a` retains
the unchanged output of one clean, exact-commit producer run: 16×8×4 cells and
eight accepted steps. `node tests/browser_sequences_actual.cjs` imports those
recorded bytes through the normal UI and checks review, family split protection,
and a byte-exact frozen release. It never runs the exporter or simulation.
No models, downloads or training are needed for these sequence checks.
Focused Python check: `python3 -m unittest discover -s tests -p test_sequences.py`.
Producer-v2 tests in `test_producer_v2_controls.py` and
`browser_producer_v2_controls.cjs` use explicitly synthetic source-derived bytes.
They exercise the local contract/import/inspection/release mechanism. Synthetic
fixtures do not grant original producer-packet acceptance and are not presented as
actual producer output. See the [simulation contract](docs/contracts/simulation-sequences.md).

The local follow-on **Import a folder of Rheon trajectories** accepts one selected
folder containing `<trajectory-label>/run.json` and `frames.jsonl`, plus original
`controls.json` for producer version 2. Preflight checks all rosters before reading:
at most 32 trajectories / 96 files / 40 MiB total raw files, 64 KiB each per
manifest/controls and 2 MiB per frames file. Each server request is independently
capped at 3 MiB and uses the appropriate pinned v1/v2 validator. These
selected-file limits do not impose a server-wide quota across independent imports.
The existing 40 MiB immutable selection/release budget includes ZIP overhead.

Each valid item commits one whole draft trajectory with initial history and a
computed acquisition marker/hash receipt. Invalid or duplicate items are rejected
without modifying existing records; earlier successful items remain. Stop prevents
the next admission, while an in-flight item may complete. Unknown responses or
storage failures pause without automatic replay. **Check pending trajectory** is
read-only and matches the marker, declared labels/index and all consumed-file hashes. V2 receipts additionally
require typed sequence version 2 and the original control hash; v1 receipts remain
unchanged and reject those v2 fields. It confirms admission only, never current source integrity, rights or
human review. Missing lookup does not prove cessation. Confirmation does not
resume later items; dismissal/departure/reload makes no rollback claim. Progress
is held in this page; inspect the collection after reload. Imports retain the
independent editor and exact selected revision pairs.

Folder labels remain declared context and do not automatically group independent
families. Use the optional shared protected group only when runs must stay together.
Review, rights/history, fixed saved selections and canonical whole-trajectory
export use their existing controls. No time flattening, frame split or scientific
training qualification is added. `tests/test_sequence_batch.py` and
`tests/browser_sequence_batch.cjs` use the retained actual fee7b4a pair and separately
labeled source-derived synthetic controls; they execute no simulation. The separate
`test_sequence_batch_v2.py`, `test_sequence_batch_v2_controller.cjs` and
`browser_sequence_batch_v2.cjs` verify mixed v1/synthetic-v2 acquisition, shared marker
races, exact control proofs and frozen three-file transport. They establish local
compatibility only; actual producer-v2 packet acceptance remains blocked.
This adapter remains pinned to its exact documented contract. Unsupported build/provenance forms require a separately reviewed versioned contract.


### Import an annotated caption corpus

The workbench imports one existing annotated format: an **expanded Tuldok
`image_caption_v1` release**, including `manifest.json`, the three
`train/val/test/metadata.jsonl` files and their normalized PNGs. Choose its folder
in “Import a frozen caption corpus.” Metadata rows use exactly:

```json
{"file_name":"0123456789abcdef0123456789abcdef.png","text":"A reviewed source caption.","group":"component:<complete-family-hash>"}
```

The native manifest must agree with every caption, group, image path, split and
asset/pixel hash. Original train/validation/test assignments remain active source
splits; foreign IDs, original acquisition hashes, review and provenance are
retained as declared origin evidence. Received PNGs get new local IDs and actual
source hashes. Imported captions are **drafts**, requiring your explicit human
review before export. Existing records are never overwritten. No archive
extraction, URL fetching, arbitrary imagefolder columns, coordinate conversion
or other annotation format is supported by this slice.

At most 1,000 combined physical metadata lines and 8 MiB source JSON are supported,
with existing image/caption/group limits and bounded prepared evidence. Choose
files again after a server restart. Successful rows remain when another row
fails; Stop prevents the next admission while an in-flight row may complete.
A lost response pauses for a read-only saved-result check without replay. Batch
progress is kept only in the current page; reload is not batch recovery.

Authored examples and an existing-owner design rehearsal are under
`tests/fixtures/native-caption-release/`. Native-import HTTP and
Chromium tests independently check admission, fresh review and actual downloaded
release consumption by the unchanged pinned chapter-26 validator.

### Independent instruction answers

Open an existing text record and use **Instruction answers** to add, edit and explicitly review separate completions. Each answer has its own stable ID, revision, review and history. The prompt and its classification/entity target remain unchanged; multiple answers coexist. Plain entry uses browser LF newlines; JSON-string entry preserves CR/CRLF. Completion whitespace and Unicode are stored exactly, with the existing 200,000-code-point bounded-text policy.

Select individual answers and use **Freeze selected answers**. Selection captures response and parent/source revisions and never expands to later answers. Download/open a fixed selection JSON file to retain those exact pairs across page reloads. Filters and record saved sets remain separate. Stale or draft answers require explicit current reselection/review.

The dedicated `text_instruction_v1` ZIP preserves canonical prompt/response snapshots, provenance, hashes and full related family evidence in manifest.json; prompt assets are under prompts/. Consumer rows have only prompt/completion in train/validation/test data.jsonl. rows.jsonl maps deterministic zero-based rows to exact revisions and family IDs. Splits weight selected examples and never divide a source family; reports also count unique prompts. Up to 5,000 responses and 40 MiB total uncompressed archive data are permitted, using existing synchronous resource contracts. Empty unused splits are declared but omitted from the consumer's loading map. Final export requires a fresh eligible proof.

Consumer verification uses unchanged hash-pinned TRL0.23.1 and Datasets4.1.1, isolated verification dependencies, a locally constructed tokenizer and tiny random CPU model. It checks actual browser-downloaded strings, row mapping, completion masks, EOS, padding and explicitly disabled truncation, with no pretrained download or training-quality claim. Dependencies belong to tests/instruction-consumer-requirements.txt, not app runtime. [Contract](docs/contracts/dataset-releases.md).

### Native text-classification releases

The workbench can import a locally selected frozen `canonical_v1` ZIP (manifest
`schema_version: 1`) through **Import native text-classification release**. It
checks exact manifest/JSONL row/text-asset bindings and hashes the consumed ZIP.
Only `text_classification` rows are admitted; per-row rejections leave other valid
rows available. Every imported label starts as a new draft, with rights unknown
and no inherited approval or source split. Existing canonical text and request
markers are rejected without overwriting annotations, review or provenance.

Exported text is the new import input, preserved exactly before the existing
NFC/LF normalization. Native releases omit upstream original text, so recovering
those bytes is unsupported. The new input hash is measured independently;
upstream record/hash/review/rights fields remain declared historical provenance
with `original_status: unavailable`. Measured acquisition evidence binds archive,
manifest, metadata, physical row and text asset. Native groups are retained, with
stable foreign identity links; upstream IDs are not restored as local parents.

Stop prevents later admissions; an in-flight record may finish. An uncertain
response pauses the batch and offers read-only saved-result reconciliation, never
automatic replay. Restart requires choosing the archive again for preparation;
committed records and receipts persist. Limits and qualification are recorded in
[the import contract](docs/contracts/native-imports.md).

### Choose an advertised Pumas gateway

In the workbench, open **Find Pumas for annotation** and **Scan advertised
gateways**. Select a gateway to inspect its advertised library context, separate
core and HTTP build identities, generations, endpoint and observation hash.
Choose an annotation workflow, then **Use selected gateway**. Tuldok rechecks
the descriptor before copying its URL into that workflow's existing form. List
served models and request a proposal separately; choosing a gateway makes no
model request and changes no source, annotation, review or selection.

This advertisement consumer retains historical Pumas-Library PR51 source at
`80f06ab17f9eea639fee143c86319ca9b5e1a21c`. HTTP advertisements are unauthenticated;
compiled features do not prove model readiness. Numeric-loopback HTTP descriptors
are bounded to 64 KiB, with no redirects, legacy fallback or automatic model
acquisition. Manual URLs remain available. Qualification uses an explicitly
source-derived fixture, not a live Pumas runtime or a v0.8 release.
[Contract and limits](docs/contracts/pumas-integration.md).

### Propose a caption from an existing image

Select one image in the workbench and open **Propose a caption for this image**.
List the served models at your Pumas-compatible gateway, choose a model, and
explicitly request a caption. A catalog entry does not prove vision or JSON
support. Unsupported image input, unavailable models and invalid responses fail
without fallback or automatic retries. The request sends an oriented JPEG copy
at most 1600 pixels on its longest side; original source bytes stay unchanged.
Only one caption request runs at a time, independently of existing generation jobs.

Inspect the proposal, reject it, or explicitly **Apply as draft**. Applying checks
both captured revisions and original/canonical image hashes; it updates the
existing image's target and proposal receipt atomically. It never grants review.
Explicitly review the draft and select its new revision before freezing a caption
release. Fixed selections retain their old revisions. Source acquisition evidence,
rights, parent relationships and protected groups are preserved. Target-associated
model evidence survives explicit review and frozen export; changing the caption
or task removes that evidence from the current target while retaining history.

Attempts retain the exact bounded submitted JPEG, prompt, requested provider/model,
seed, revisions, hashes, complete bounded response bytes and application receipt.
Seeds are requests, not reproduction guarantees. Stop cancels Tuldok's transport
and fences late output; it does not prove when backend inference stops. Interrupted
attempts remain inspectable after restart and never auto-resume. Refresh requests
and inspect the record after a lost acknowledgement; repeating the same request ID
or application reconciles existing state without another inference/target write.

Before submission, one bounded recovery intent is stored in this tab’s
`sessionStorage` and restored synchronously on reload. It contains the request ID,
source ID/revisions, credential-free gateway URL, model, guidance and seed, without
image/response bytes. Changed intent stays blocked until a persisted GET outcome
is reconciled; ambiguous 404 and refused repeats retain the original ID. An
explicit unchanged retry uses the same body/ID. No inference replays on reload.
Storage read/write/removal failures block new submissions; restore storage and
reload rather than abandoning an unknown request. Closing the tab ends this local
recovery scope; it is not cross-tab/device recovery.

This single-image slice is tested with local synthetic HTTP providers and real
Chromium. It asserts no real-model caption quality and adds no models, credentials,
provider registry or dependencies. [Contract](docs/contracts/pumas-integration.md).

### Propose a label for existing text

Open one unannotated text record and **Propose a class for this unannotated text**.
Enter the author's exact label choices as a JSON array, list served models at the
Pumas-compatible gateway, choose a model and explicitly request a proposal. Labels
are unique, case-sensitive strings (1–30 choices, up to 80 Unicode code points
each); leading/trailing whitespace is rejected rather than trimmed. The selected
source text, labels, guidance, provider/model, seed and revision evidence are
frozen for this attempt. Source text is sent exactly as stored; it is not rewritten.

The model may return exactly one offered label or explicitly abstain. Unknown or
malformed labels, partial output and incompatible models fail without fallback.
Abstention saves no target and offers no Apply action. Listing a model and passing
shape checks do not establish semantic correctness. Inspect the evidence, reject
the proposal, or explicitly **Apply as draft** after checking the label. Apply
requires the captured source revisions and unchanged label choices, preserves
acquisition provenance and atomically records one draft annotation with its
receipt. Explicit human review and reselecting the new revision are required
before export; fixed selections keep their old revisions.

Lost request acknowledgements reconcile through the same admission ID. An early
404 keeps that ID pending, and explicit unchanged repeats do not infer twice.
The exact pending ID and request commit to IndexedDB before their recovery mirror
and POST. Submission waits for origin authority after reload. Visible recovery
controls open the captured source and restore its settings; retry still requires
explicit submission. Transactions coordinate stale storage views across tabs,
with Web Locks providing additional coordination. Unavailable IndexedDB, origin
storage or locking support and invalid recovery evidence block new requests. An
exact admitted receipt retires the request; failed mirror cleanup retains its
retirement evidence and blocks new POSTs until cleanup succeeds.
Every explicit POST also commits an attempt generation bound to that exact
request. An initial rejection can release recovery only if its captured generation
is still current; a retry in another tab prevents the older rejection from
discarding its unresolved admission. Legacy or crash-restored evidence remains
unknown until an exact receipt reconciles it. No inference automatically retries.
Apply receipts likewise reconcile lost replies without another target write.
Cancellation fences late output; interrupted requests never resume automatically
after restart. Polling uses bounded summaries; individual request reads retain
the exact source, prompts and bounded complete response evidence. This first stage
uses synthetic local HTTP and Chromium fixtures, with no real-model qualification.
[Contract](docs/contracts/pumas-integration.md).
### Explicit preference pairs

Use **Comparative judgments** on a text prompt with two existing independent
answers. Choose each answer and explicitly prefer left/right, tie or abstain,
then independently review that exact comparison. Answer order, answer review
and model scores never grant preference. Judgment history retains exact prompt,
source and answer revisions; editing any bound evidence requires deliberate
rejudgment and fresh review. Deleting a judgment preserves history and frozen
exports. Stale judgments can be deleted without re-reviewing them.

Select fixed judgment revisions and use **Freeze selected preference pairs**.
The `text_preference_v1` ZIP emits only explicit `prompt/chosen/rejected` strings.
Reviewed ties/abstentions remain in the manifest and are excluded with reasons;
an all-excluded selection cannot export. Current opposing reviewed judgments
for the same exact pair block even when unselected. Current tie/abstention
judgments warn without vetoing a direction. Distinct answer IDs with identical
strings remain explicit degenerate pairs with a warning. Answer review is
retained as separate evidence; it is not required to grant comparative review.

The existing protected family graph and weighted allocator keep all related
pairs in one split. Manifest and row sidecar freeze both answers, judgments,
source/rights provenance, complete lineage, exact revisions and exclusions.
Stale selections and changed competing review invalidate proof. Selections are
held in the current page; reload requires deliberate reselection. Releases use
the existing 5,000-unit and 40 MiB synchronous bounds and immutable publication.

Qualification invokes unchanged hash-pinned TRL 0.23.1 DPO dataset preparation
and preference collator against actual browser-downloaded strings. A local byte
tokenizer tests prompt left padding, completion right padding, attention masks,
EOS and disabled truncation. DPO appends EOS unconditionally, including after
an existing EOS. No model is constructed or run; no pretrained download or
training-quality claim is involved. Reuse the isolated official dependencies
in `tests/instruction-consumer-requirements.txt`. Run `node
tests/browser_preferences.cjs` with `INSTRUCTION_CONSUMER_PYTHON` pointing to
that environment. [Contract](docs/contracts/dataset-releases.md).

Static mesh import: [bounded ASCII PLY/sidecar contract](docs/contracts/static-mesh.md), with native units/frame/provenance inspection and human review before export.

### Selected-model Pumas typed operations

The annotation workbench and image studio offer an explicit **Pumas typed v1** API choice. This consumer pins the historical draft [Pumas PR54](https://github.com/MrScripty/Pumas-Library/pull/54) source `40c5cbfed67a6f0e862a1197bb5105363d67bdb1`, including [PR53](https://github.com/MrScripty/Pumas-Library/pull/53) streaming/lifetime source `f3b3c770ca531f013c8e1f8b1f958b9dc0babbfb`. Existing compatible API settings remain the default. PR51 gateway advertisements belong to a separate producer stack; this consumer does not assume those drafts are merged together.

Choose the exact serving alias and optionally its exact profile; inspect capabilities before requesting a text label, grounded rewrite, or text-to-PNG image. The server resolves an omitted profile, and the consumer binds the provider POST to that exact returned profile. Catalog aliases may appear under multiple profiles; their listing alone proves no capability. Typed text has no seed or JSON-format option. Frozen typed text intent records `seed:null`, and complete stop-terminated results still need valid application JSON. Typed image batches currently require the explicit repeat-prompt strategy. Captioning requires image input, which this typed contract does not support; audio is also unavailable. No typed streaming UI is claimed: requests use `stream:false`.

Proposals preserve actual capability observations, their SHA-256, exact typed request/hash, response hash, selected alias/profile and producer source. Pumas request IDs are correlation only; local classification admission IDs separately reconcile without repeating inference. Authoritative `not_admitted` and `unknown` errors remain inspectable. A successful projected response is recorded locally as `result_received`. Transport loss, cancellation or an interrupted image attempt cannot replay automatically; uncertain image queues cannot resume that attempt. Cancellation retires local transport actors, and does not establish native provider cessation. Applying labels or admitting rewrites creates drafts through existing revision/history, rights and family owners. Human annotation review remains separate and required for release. Generated prompts remain provenance, never image captions.

Discovery limits are separate from inference lifetime: local scans share ten seconds; descriptor inspection, typed selected-alias catalogs and capability inspection use three-second observation budgets. Typed generation bounds connection establishment to ten seconds and has no total, read, idle or drain deadline afterward. Consumer limits: capability JSON 64 KiB, catalog JSON 1 MiB/512 served rows, text result 256 KiB, image result JSON 12 MiB/PNG 8 MiB, typed image dimensions 2048 per axis/4194304 pixels, profile 128 ASCII bytes and serving alias 256 UTF-8 bytes. Image dimensions are checked before POST and PNG decoding. Producer wire limits do not override these consumer allocation bounds. No provider redirects, fallback or automatic inference retry.

`tests/fixtures/pumas-typed-v1` labels its actual native controlled-gateway capability captures and authored harness. Offline CI uses a source-derived HTTP fixture. Separate native qualification runs the pinned production HTTP/admission/handler code with an external controlled text backend and an owned managed literal-PNG process compiled without `cfg(test)`. No model is loaded or downloaded, and these checks do not qualify model accuracy or training. With that harness already running:

```sh
python scripts/qualify_pumas_typed_actual.py --gateway-receipt /path/to/gateway.json --output /path/to/ignored/consumer-native.json
PUMAS_TYPED_GATEWAY_RECEIPT=/path/to/gateway.json node tests/browser_pumas_typed.cjs
```

Keep reports, generated datasets and JPEG85 screenshots in ignored `build/` or external qualification directories. The authored harness instructions document startup and owned shutdown; production source remains pinned and unchanged.

### Reviewed image classes for the Chapter 8 trainer

Choose **Image classes · Chapter 8 trainer** when freezing selected Workbench
records. This adapter targets the exact `train_image_classifier.py` fixture in
`tests/fixtures/` with Torch 2.8.0 / torchvision 0.23.0. It requires human-reviewed
single-class images, at least two classes, and every class in train, validation
and test. Preview shows missing class coverage; whole protected families and
existing source splits remain intact. These consumer-specific requirements do
not restrict the canonical format.

The ZIP contains `train/val/test/class_000000/ID.png`, with unchanged normalized
PNG bytes. `manifest.json` maps each opaque folder/index to the exact Unicode
label and retains annotation/review revisions, provenance, hashes and connected
lineage. Keep this mapping with the model: the unchanged trainer and prediction
utility report opaque folder names. Label text never becomes a filesystem path.
Same-split pixel repeats are retained with warnings, never silently discarded.
This is a training view, not an original-byte backup or a data-quality guarantee.

The actual-reader check needs the existing pinned consumer environment plus
CPU `torchvision==0.23.0` and `scikit-learn==1.7.2`:

```sh
INSTRUCTION_CONSUMER_PYTHON=/path/to/consumer-venv/bin/python node tests/check_image_classification_consumer.cjs
node tests/test_image_classification_export_controller.cjs
node tests/browser_image_classification_export.cjs
```

The reader gate also executes the unchanged tiny CPU trainer for one epoch,
without downloading model weights, using six authored transport fixtures. Its
metrics establish no training-quality claim. See the
[classification export contract](docs/contracts/dataset-releases.md).

### Reviewed plain-text corpora for Chapter 11

Import text, choose **text corpus**, add a corpus review note, and explicitly
save as **Human reviewed**. Classification/entity approval does not approve
corpus use. Choose **Text corpus · Chapter 11 byte transformer** in the existing
release menu, preview the saved selection, then freeze its exact revisions.

`text_corpus_v1` emits `train.txt`, `validation.txt`, `test.txt`, exact byte-range
mapping in `documents.jsonl`, duplicated canonical document assets, and frozen
review/provenance/family evidence. Existing NFC/LF text becomes UTF-8 without
further normalization or trimming. IDs are sorted within each split. Exactly two
LF bytes are appended after every document, including the last; existing trailing
newlines remain.

The unchanged published consumer uses raw-byte IDs, a 256-value vocabulary and
one-byte-shifted windows. Windows may cross document and UTF-8 character
boundaries. Separators are ordinary bytes, **not EOS or attention resets**. For
reference context 128, train must exceed 128 bytes; validation/test each need at
least 2 bytes. All three connected-family splits must be nonempty. Preview shows
byte, document and family counts separately. Allocation weights records, never
bytes; fixed splits and unselected lineage bridges remain protected. No document
is split, discarded or automatically moved to satisfy a quota.

A fresh preview is mandatory. Releases are immutable, deterministic,
content-addressed ZIPs bounded to 5,000 records and 40 MiB for the full logical
archive, including duplicated data and metadata. Human review and family
protection do not establish data quality, semantic independence or permission.

See the [consumer pin and byte contract](docs/contracts/dataset-releases.md).
The actual-consumer gate uses Torch 2.8.0 on CPU, synthetic authored fixtures and
the unchanged companion reader/trainer/evaluator. It downloads no models or data.

### Export reviewed single-object detection

Save and review image boxes, select their exact revisions, then choose **Chapter 9 · reviewed single-object detection**. Preview shows the exact label mapping, positive/negative coverage, protected splits, original category evidence and blockers. Freeze creates immutable RGB PNG / derived rectangular-mask pairs for the pinned reader. Integer edges, one class, zero/one object and nonempty train/validation/test are required; fractional/multiple boxes remain supported by canonical COCO. Masks are box transport, not segmentation truth.

New native imports preserve validated original category tables/IDs as source evidence, separately from later edits and the reader’s binary presence target. Legacy omitted IDs remain unavailable. The [export contract](docs/contracts/image-detection-export.md) gives bounds and the strictly reader-only QA scope. Test annotations and automated review actions do not constitute human-labelled training data; UI remains provisional.

### Native detection corpus imports

Choose **Import native detection release** for a detection-only `canonical_v1`
ZIP produced by this Workbench. Its manifest, all three COCO projections and
normalized RGB PNGs must agree on vocabulary, image indices, oriented geometry,
pixel/byte hashes and pixel-edge xywh boxes. Empty boxes remain negative images.
Mixed tasks and arbitrary third-party COCO archives require a separate contract.

Imports create new detection drafts with unknown rights and actual hashes of the
consumed exported PNGs. Upstream originals are unavailable; original identity,
review, rights and provenance remain declared evidence. Exported partitions become
fixed source splits. Native groups and foreign ID/parent/book-or-session links
remain protected; inconsistent retained or existing/deleted family splits reject
admission. The native manifest omits unselected upstream family members, so this
preserves declared links and partitions without reconstructing the entire graph
or proving semantic independence.

Limits: 1–100 images, 8 MiB stored ZIP, 16 MiB expanded bytes, 3 MiB per prepared
row including base64 PNG and historical metadata, and 16 MiB total signed row
evidence. Preparation validates the whole bundle without writes. Admission is
atomic per image; successful rows remain after another fails. Stop prevents the
next row while in-flight work may finish. Uncertain outcomes require read-only
saved-result inspection, with no automatic replay. Restart expires preparation;
committed records persist. Progress stays in the current page. Explicit human
review and current selection are required before release. [Scope and roadmap
inventory](docs/contracts/native-imports.md).

### Explicit selected-library authenticated owner observation

In the annotation workbench, **Reuse an existing Pumas library** lists the
operator-selected registry and its local model indexes. Select one exact library,
authenticate its existing HTTP owner, inspect the public observation, choose an
annotation destination, then **Reauthenticate and use URL**. This copies a URL only;
it starts no proposal, model query, owner or download. Local index references stay
scoped by library and are not evidence of served aliases or model readiness.

This adapter calls the unmodified Pumas SDK at
`ab9890fe3248ed7c435b958cded0b131b0700a35`, tree
`302a9ef3f2931d46d4a424d049725b15fc8291aa`. This is the historical PR48/PR51 snapshot, without an assumed v0.8 release
or current merge status. Typed PR54 `40c5cbfed67a6f0e862a1197bb5105363d67bdb1` remains a separate
stack, so this chooser refuses typed composition. Port advertisements alone
remain unauthenticated. Startup, bootstrap, reclamation, shutdown and acquisition
are unsupported here; ambiguous attachment never starts a replacement owner.

An operator must explicitly supply a clean exact SDK checkout, installed Rust
and cached dependencies. The offline helper verifies all producer source bytes
and builds a separate consumer adapter outside the producer checkout:

```sh
python tools/build_pumas_local_bridge.py --producer-source /path/to/exact/Pumas-Library --output /path/to/consumer-build
python app.py --data /path/to/dataset --pumas-local-bridge /path/to/consumer-build/target/debug/tuldok-pumas-local --pumas-local-bridge-sha256 EXACT_EXECUTABLE_SHA256 --pumas-registry /path/to/selected/registry.db
```

The build receipt records executable/source hashes and the consumer lockfile.
Application startup never installs or builds the bridge. Without these settings,
the panel returns an explicit unsupported configuration error.

Limits: 32 library contexts, 64 complete local-index rows per library (larger or
inconsistent counts refuse; no pagination), 16 KiB adapter input, 1 MiB output,
64 KiB stderr, and 15 seconds for each observation or full Use operation. The
owned process group and pipe actors must retire before another observation;
unresolved custody retains the slot and returns an error. Credentials and
registry metadata are not returned. Receipts are signed for the application
lifetime and are not restored after page reload. Fresh SDK core authentication,
HTTP descriptor equality and final core reauthentication precede URL use.
Authentication is observed at selection; it grants no lifetime lease or guarantee
for later inference. Editor changes, restored settings and page departure fence
late results. Existing dataset rights, review, history and family splits retain
their owners.

The ordinary browser gate checks the real unsupported configuration path. Native
qualification additionally requires explicitly configured, separately built owned
fixtures (`--fixture`); these use the original SDK core/IPC and an authored HTTP
descriptor responder with controlled indexes, no inference runtime or assets:

```sh
python tests/check_pumas_owner_reuse_native.py --bridge /path/to/tuldok-pumas-local --fixture /path/to/tuldok-pumas-owner-fixture --output /path/to/fresh/evidence
TULDOK_PUMAS_NATIVE_BRIDGE=/path/to/tuldok-pumas-local TULDOK_PUMAS_OWNER_FIXTURE=/path/to/tuldok-pumas-owner-fixture node tests/browser_pumas_owner_reuse.cjs
```

See the [contract and scope](docs/contracts/pumas-integration.md).


### Inspect and reuse a selected typed text model

The classification and grounded rewrite forms offer **Inspect selected text model**
and **Use compatible selected model**. At the explicitly configured numeric-loopback
URL, the consumer reads the public `/v1/models` and `/v1/capabilities`, resolves an
exact served profile, and requires available `chat_generation` with `messages_text`
input, text output, and the existing worker token bounds (2000 classification,
6000 rewrite). Use rechecks the exact profile and original capability SHA-256,
then applies URL, alias, profile and protocol through ordinary form events. It
starts no proposal. Later generation retains its existing capability validation,
job, cancellation, recovery, draft review, rights, history and family ownership.
Edits, Restore epochs, source navigation, dirty state and page departure reject
late replies. Serving aliases are separate from local model references.

This slice pins typed PR54 `40c5cbfed67a6f0e862a1197bb5105363d67bdb1`
and discovery PR48 `ab9890fe3248ed7c435b958cded0b131b0700a35` as separate
historical draft snapshots, without assuming a merged producer stack. The discovery server lacks typed operation and
capability routes; the typed server lacks authenticated HTTP discovery publication.
There is no qualified joint producer. The selected-library panel therefore permits
only read-only serving inspection between two fresh complete SDK owner checks;
owner-bound typed configuration and inference remain unavailable. No local index
ID becomes an alias automatically. Image-to-Text, caption and audio selection are
unsupported; text-to-image capabilities do not establish Image-to-Text.

The standalone read shares a six-second deadline, with three seconds per public
HTTP read, a 1 MiB catalog and 64 KiB manifest bound, at most 512 raw catalog rows
and 64 distinct serving aliases, and an 8 KiB request. Owner inspection shares the
existing fifteen-second deadline across both fresh SDK borrows and public reads.
All observations retain exact source/profile and inspectable capability hashes;
they grant no owner lease or inference admission. Default test HTTP fixtures are
source-derived. An explicit `TULDOK_PUMAS_TEXT_SELECTION_GATEWAY_RECEIPT` allows
the Chromium selector gate to use pinned native typed production modules with an
authored external text backend, no model loaded. The original discovery SDK browser
fixture has authored HTTP descriptor responses and serving-route refusals; it does
not claim to execute the production PR48 HTTP router. Joint producer integration
requires a supported exact combined source and operation transport/identity contract.

### Native trajectory review

The native trajectory review workspace loads a named field at one native index and an x/y/z plane across all nine frames. The read-only `POST /api/workbench/sequence-review/<id>` requires exact `revision`, `source_revision`, `field`, `index: [i,j,k]` and `plane_axis`; its strict JSON request is capped at 4 KiB and response at 128 KiB. The largest plane contains 144 native samples (1,296 across nine frames), with a nine-sample native-index time trace. Shared stored-bundle verification precedes projection. MAC staggering, f32/f64 interpretation, units, original frame hashes/time/stamps/diagnostics and v2 accepted-interval controls remain associated; constructor controls and v1 emitted controls are explicitly unavailable. Pressure retains last-accepted-interval semantics.

Explicit Load admits the complete bounded response before showing native sample plots or enabling note append. Frame navigation/playback uses the nine loaded entries locally. Inputs, cancellation and departure revoke late reads. Inspection leaves annotation dirty state and selection unchanged. “Append current inspection reference” preserves the existing note, checks its complete 4,000-code-point Unicode limit and resets the draft review choice; it neither saves nor reviews. Existing save/revision/history and human review are separate actions, and releases still contain whole trajectories within protected initial-state/source families. SVG plots are inspection only; no model-training or scientific qualification is claimed.

Qualification uses retained recorded fee7b4a output for all-field/all-axis/all-frame native indexing and real HTTP/Chromium review/export, with separately labelled source-derived synthetic v2 controls. No producer or model runs. Focused gates are `python -m unittest discover -s tests -p test_sequence_review.py`, `node tests/test_sequence_review_controller.cjs` and `node tests/browser_sequence_review.cjs`; UI remains provisional.

### Human-defined temporal sequence targets

The supported `sequence_transport` task accepts optional version1 `temporal_labels` alongside the existing whole-trajectory review note. In **Human-defined temporal labels**, choose inclusive native first/last frames0..8, enter your own label and a rationale, then explicitly **Add draft range**. Edit, Remove and Clear operate on staged targets; pending controls must be explicitly Add/Update or Cancel before record Save. Drafts survive inspection and restored-page lifecycle events. Saving, then separately choosing human review, uses existing exact revision/source CAS and history. A competing edit returns409 and retains local staged labels until deliberate reload.

At most16 ranges, labels80 Unicode code points, rationales500, whole note4000 and complete canonical annotation64KiB UTF8. One-frame ranges and overlapping different labels are allowed; duplicate normalized label/start/end is refused. Empty ranges mean no authored temporal targets, not a physical negative. Human labels remain separate from declared producer provenance, numerical fields and authenticated physical truth. The versioned envelope binds whole source hashes and endpoint frame/time/hash/native stamp copies; requests accept JSON numeric time0 and normalize authoritative float0.0 where stored metadata requires it. Save and export revalidate the unchanged original bundle/index; noncanonical persisted targets fail preview/freeze. Existing note-only annotations/clients continue using their complete-target replacement contract.

Canonical releases retain these structured human targets in the manifest and typed JSONL beside the byte-exact original raw bundle. Whole trajectories and unselected constructor/source-family relatives retain the existing split boundary. No frame records, images, cell-centered vectors, continuous interpolated labels, solver-truth labels, new producer execution or training consumer is added. UI provisional. [Target contract](docs/contracts/sequence-temporal-labels.md).

The [whole-trajectory workflow](docs/trajectory-workflow.md) connects file import,
native inspection, temporal authoring, draft/reopen/human review, exact saved
selection and family-safe preview/export. Its joined browser gate also checks an
owned app restart and later stale saved references while frozen bytes remain
unchanged. The [remaining feature map](docs/remaining-feature-map.md) distinguishes
completed capabilities from corpus-diversity, downstream-objective, and broader
annotation gaps.

### Native simulation numerical datasets

Read a frozen sequence-only canonical ZIP with `native_sequence_dataset.py`, its exact release SHA256 and an explicit split. The NumPy API returns separate native MAC fields with time/x/y/z axes and original staggered shapes/f32-f64 representation; default whole trajectories or explicit contiguous windows retain record/family identity. Human range coverage and original source/endpoint anchors remain separate from numerical evidence. Inspect JSON or atomically export a pickle-free native NPZ sample. New sequence-only releases carry declared family closure; older train-only packets expose their missing-closure limitation. This adds numerical consumption, without qualifying a trainer, scientific truth or an independent train/evaluation corpus. [Consumer contract](docs/contracts/native-sequence-consumer.md). UI provisional.

### Native point-cloud numerical datasets

`native_pointcloud_dataset.py` reads existing reviewed point-cloud-only canonical
releases with their exact owner-supplied SHA256 and an explicit split. It returns
one whole cloud per sample as separate named native XYZ, optional normals and
uint8 RGB arrays, retaining mixed dtypes, signed zero, order, units/frame and
source/review/rights metadata. New point-only releases carry complete declared
known family proof; older proofless packets are refused. Provision the existing
`requirements-pointcloud-consumer.txt` separately, inspect the JSON sample or
write an atomic pickle-free NPZ. No geometry conversion, labels, inference or
training is performed. Mesh consumption remains deferred because the pinned
reader differs on demonstrated accepted decimal inputs. [Contract and CLI](docs/contracts/native-pointcloud-consumer.md).

### General COCO detection

Canonical export supports multiple objects and exact-case categories, fractional/subpixel pixel-edge boxes and explicitly reviewed empty-box negatives. Use the existing box editor, save drafts, review each record, save/open an exact selection, then preview and freeze **Canonical**. The preview shows the sorted category table shared by all three split files. IDs are stable within that release; changing the selected vocabulary can renumber them. Original imported category IDs remain separate provenance. Whole source families retain existing split boundaries. Actual COCO/torchvision readers and two-owner native roundtrip qualify transport and UI behavior, without training or a meaningful benchmark corpus. [Contract and limits](docs/contracts/general-coco-detection.md). UI provisional.

## Repository

Source is hosted at [MrScripty/Tuldok](https://github.com/MrScripty/Tuldok). A distribution license has not yet been selected.


## Reviewed retrieval judgments and release

Immutable text IDs now support retrieval document roles and explicit positive query judgments. Import raw queries with exact current document references, save and reopen drafts, review relevance separately, and save/open a fixed selection before preview/freeze. Declared import references grant no review. Every omitted relationship remains **UNJUDGED**, never an inferred negative; empty/negative/graded judgments are unsupported. Whole connected families, including former positive parents and unselected/deleted bridges, preserve split boundaries. The release keeps canonical text, original record IDs, exact revisions, provenance/rights/review, family evidence and hashes; train pairs contain train positives only and the selected inference corpus includes held-out documents.

Fresh qualification uses actual serialized files and unchanged published JSONL reading plus pure formatting/hash helpers. It performs no fitting, ranking, metrics, training or model downloads and makes no corpus-quality or trainer-compatibility claim. UI provisional. [Contract, exact source pins and limits](docs/contracts/retrieval-export.md).


### Human-authored polygon instance segmentation

Choose **image segmentation** for an oriented image. Capture vertices with primary pointer clicks or enter exact native pixel-edge x,y coordinates (including integral floats and signed zero), then explicitly Add or Clear unfinished vertices before Save. Save/reopen a draft and review its complete simple rings separately; an explicitly reviewed empty instance list is a negative image. Pending vertices and active capture fence late source opens and participate in discard/unload guards. Rights notes, original source evidence, history and exact saved selections keep their existing owners.

Canonical preview/freeze shares release-local COCO categories with detection boxes. Polygon bbox/area are continuous geometry; actual consumer masks are quantized and may be empty for a valid positive tiny polygon. Native canonical import supports polygon-only and mixed box/polygon packets as new local drafts with unknown rights and exact upstream evidence. Limits include 100 instances, 128 vertices/ring, 1,024 vertices/record; segmentation-bearing releases have 100 selected records, 100MP image pixels and 40MiB complete logical/stored ZIP bounds. Native import and reader QA have stricter separate limits. Actual pinned COCO mask/CocoDetection reading and Chromium downloads qualify compatibility and workflow, without models, evaluation, training or corpus-quality claims. [Contract, source pins and limits](docs/contracts/polygon-segmentation.md). UI provisional.

### Vertex-only point-cloud preparation

Import a complete points.ply/points.json pair in the workbench.
The [bounded point-cloud v1 profile](docs/contracts/point-clouds.md) retains XYZ,
optional complete normals/RGB, named native dtypes, units/frame/provenance and
immutable declared source/family/splits. Two MiB, 20,000 points; the first 512
points are inspection only. Float32 decimal incompatibilities are rejected, never
rewritten. Imports are drafts requiring a nonempty human review note. Canonical
release retains both raw files unchanged; this is preparation, not model training.

For actual pinned-parser QA, provision `requirements-pointcloud-consumer.txt`
separately, then run `node tests/check_pointcloud_consumer.cjs` and
`node tests/browser_pointclouds.cjs` (with Chromium). Native PLY arrays and exact
raw files are checked across fresh owners; no model is instantiated or trained.

Reviewed binary retrieval is a separate bounded `text_retrieval_binary_v2` profile: exact document revisions, relevant/not relevant/explicit unjudged, TREC1/0/-1 qrels, native second-owner drafts and protected whole-family splits. Positive-only v1 remains available. See [contract and limits](docs/contracts/retrieval-binary.md). This prepares/inspects source judgments; no ranking, metrics or training qualification.
