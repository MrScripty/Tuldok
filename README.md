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

## AI corner suggestions

Open **AI model**, choose Codex, OpenRouter, or llama.cpp, and select or enter a vision model. With an image selected, click **Suggest corners**. Adjust the returned pins and visibility flags, then **Save**. Suggestions remain unsaved until reviewed; invalid results leave your current pins intact.

- **Codex:** install and sign in to the Codex CLI on the Tuldok computer. Uses its app-server interface, cached model catalog, and selected thinking level. `TULDOK_CODEX_MODEL` overrides the default model.
- **OpenRouter:** enter an API key or set `OPENROUTER_API_KEY` on the server. Refresh models lists image-capable models advertising structured outputs. The entered key stays in the current page; it is not written to browser storage, labels, or exports.
- **llama.cpp:** run a vision model with its required image projector and supply the server URL (default `http://127.0.0.1:8080`). Refresh models reads its model list. The server must be reachable from the Tuldok computer and support image input and JSON schema output.

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

Choose the image size and an optional starting seed. The seed increments for each
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

Image requests have a 630-second deadline. GPU cancellation may need to reach the
runtime’s next cancellation checkpoint. After a server restart, explicitly resume
unfinished jobs. Keep the dataset backed up and review synthetic images and labels
before using them for training.

## Workbench image captions

Open **Dataset workbench** from the corner studio. Existing imported and Pumas-generated images share the original Dataset source ID and bytes. Select **image caption**, write a caption describing the visible result, save as a draft, then explicitly review it. Editing a target resets the editor's review choice to draft. Generation prompts remain source provenance; they are never used as automatic captions. Each record has one current workbench task, with previous targets retained in revision history. Corner labels remain a separate annotation.

Filter by task, review state or caption text. Select human-reviewed caption records and choose **Image captions · train/val/test** when freezing a release. The `/api/workbench/releases` request adds `format: "image_caption_v1"`; omission retains the canonical mixed-task release. Captions use exactly `{"caption": "..."}` and are bounded to 4,000 Unicode code points. Unknown formats and invalid caption fields are rejected.

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
    node tests/browser_workbench.cjs
    node tests/browser_grounded.cjs
    node tests/browser_captions.cjs

The browser smoke test requires Node 22+ and Chromium/Brave. Set BROWSER to the browser executable. It uses a synthetic camera, a temporary dataset, and local fixtures for all three AI providers. Tests do not contact paid models.

## Repository

Source is hosted at [MrScripty/Tuldok](https://github.com/MrScripty/Tuldok). A distribution license has not yet been selected.
