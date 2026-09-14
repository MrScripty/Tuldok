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

## AI corner suggestions

Open **AI model**, choose Codex, OpenRouter, or llama.cpp, and select or enter a vision model. With an image selected, click **Suggest corners**. Adjust the returned pins and visibility flags, then **Save**. Suggestions remain unsaved until reviewed; invalid results leave your current pins intact.

- **Codex:** install and sign in to the Codex CLI on the Tuldok computer. Uses its app-server interface, cached model catalog, and selected thinking level. `TULDOK_CODEX_MODEL` overrides the default model.
- **OpenRouter:** enter an API key or set `OPENROUTER_API_KEY` on the server. Refresh models lists image-capable models advertising structured outputs. The entered key stays in the current page; it is not written to browser storage, labels, or exports.
- **llama.cpp:** run a vision model with its required image projector and supply the server URL (default `http://127.0.0.1:8080`). Refresh models reads its model list. The server must be reachable from the Tuldok computer and support image input and JSON schema output.

The adapters follow Book-Be-Gone's provider interfaces without depending on that repository. Each request sends a JPEG copy of the selected image, at most 1600 pixels on its longest side, preserving orientation and aspect ratio. Original dataset images remain intact. The prompt in `prompts/corners.md` requests book-relative corner identities, normalized image coordinates, visibility, and no-book detection. Saved suggestions include provider/model provenance in `suggested_by`; they still need human review before use as training labels.

Requests time out after 180 seconds (`TULDOK_AI_TIMEOUT` overrides this), with a 60-second response-progress limit. Requests are not automatically retried. Model settings are remembered locally; API keys are excluded.

## Generate images with Pumas

In Pumas, install and activate a compatible Torch runtime, create a Torch runtime
profile, and serve the supported image model. Copy the **Pumas gateway URL** into
Tuldok’s **Generate images** settings, then refresh the model list. The image list
includes only ready models advertising image generation. A llama.cpp router URL
will not provide this image workflow.

Choose a model, enter a prompt, select a size, and optionally supply a seed. Click
**Generate**, then **Save PNG** to download the returned image or **Add to collection**
to label it using the existing dataset tools. Adding an image preserves its original
PNG bytes; it does not assign corner labels automatically. VLM corner detection
has its own unchanged provider settings.

Generation has a 630-second client deadline and is never automatically retried.
**Cancel** requests cancellation in Pumas; GPU work may need to reach its next
cancellation checkpoint before the runtime accepts another prompt. Invalid output
leaves the previous image available. A seed records the requested sampling seed;
GPU output is not guaranteed to be identical across runs.

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

The browser smoke test requires Node 22+ and Chromium/Brave. Set BROWSER to the browser executable. It uses a synthetic camera, a temporary dataset, and local fixtures for all three AI providers. Tests do not contact paid models.

## Repository

This is a local standalone repository. No remote host or public repository is configured. A distribution license has not yet been selected; add one before publishing.
