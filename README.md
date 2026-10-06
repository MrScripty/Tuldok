# Tuldok

A local dataset studio for book-corner detection. Capture or import original images, label four corners, and export training data. Tuldok is a separate developer tool; it does not depend on Book-Be-Gone.

## Run

Requires Python 3.10+ and Pillow. There is no JavaScript build step. Manual labeling needs no external service.

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
There is no dynamic saved-search feature in this slice. Names may repeat; each set
has its own ID. Saving creates a separate set rather than replacing membership.

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

The unchanged pinned snapshot in `tests/fixtures/diffusion_check_image_data.py` is used for producer/consumer contract tests. An alternate checkout may be supplied through `TULDOK_CAPTION_CONSUMER`; tests reject a different hash. This milestone runs no model training or paid inference. [Scope and verification](docs/plans/image-caption-exports/plan.md).

## Dataset conventions

Coordinates are normalized against the oriented image: x/(width-1), y/(height-1). Each annotation has book_present, crop_suitable, and corners in the order top_left, top_right, bottom_right, bottom_left. A corner has visibility visible, occluded, or out_of_frame. Invisible corner coordinates are null. A no-book sample has crop_suitable=false and an empty corner list. Crop-suitable labels require four visible, placed corners. Visible quadrilaterals must be clockwise and convex. New labels use corner_reference=book: identities follow the book through rotation, so an upside-down book’s top-left corner is at the image bottom-right. Coordinate values always remain in image space. Existing labels without this field are interpreted and exported as corner_reference=image; untouched labels retain that convention. Placing, moving, or clearing corner positions switches the edited label to book orientation. The Corner reference control can explicitly retain image orientation when needed. Export schema version 2 records this distinction per annotation; training should select or explicitly convert conventions rather than mix them.

The original uploaded bytes are preserved at data/images/ID/source. The labeling and exported image.png is a lossless PNG of the decoded, EXIF-oriented RGB image; normalization makes browser display and training coordinates agree. Camera captures use full camera dimensions, with JPEG encoding. No crop, resize, or automatic detector alters the labeled frame.

Book IDs group related frames. Assigning a training/validation/test split applies to all previously unassigned images with the same book ID. No-book images without a book ID are grouped by session. Conflicting assigned splits are rejected. Reserve whole books and sessions for evaluation; this tool enforces group consistency, but you choose which groups to hold out.

Labels and metadata are stored in SQLite with optimistic revision checks. Stale tabs cannot overwrite newer labels. Exact duplicate source images are rejected. Unsaved editor changes are protected when navigating away. Back up the entire data directory, including source files, with the application stopped.

## Scope

This first version supports still capture and image import, including frames extracted from videos elsewhere. It does not yet record video, extract/deduplicate video frames, train models, or provide segmentation labels. Exports include images and metadata but omit original source bytes. Manual labeling stays local; optional AI suggestions send the selected image to the configured provider.

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

## Repository

Source is hosted at [MrScripty/Tuldok](https://github.com/MrScripty/Tuldok). A distribution license has not yet been selected.
