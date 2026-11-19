# Implementation spec: generated annotation, more kinds, and quality control

This is phase 4 of [the training and curation plan](plan.md). It follows that plan's rule: Tuldok supplies a file contract, a reader and a view; a project's own script (or a model behind the Pumas endpoint) makes the annotations. It builds on [spec-d4.md](../definition-first-projects/spec-d4.md) (tasks, the line file, the working copy, the steps, the Annotate tab) and [spec-d5.md](../definition-first-projects/spec-d5.md) (the Pumas endpoint and suggestions); the viewers are spec-d1's (`inside.js`), and the page follows [spec-w4.md](../definition-first-projects/spec-w4.md). Section 1 of [spec-m1-m2.md](../definition-first-projects/spec-m1-m2.md) applies.

**Owner, 2026-11-19:** "Tuldok also needs a strong set of annotation types, however i dont nessisarly want everything that Label Studio has beacuse Tuldok centers on generated annotations rather than human made ones. That means we can do things like automated/ai segmentors, polygons, depth mapping, image masks, ranking, time series, object tracking, point cloud objects (selecting points that belong to an object), some quality control tools like agreement betwene different models, etc."

**After this phase** a task may be of nine more types. A project's annotator (its own script, or a model behind the Pumas endpoint) is built as a dataset with the step `annotate`; its product is an **annotation set** for one task. A task can have several sets side by side (one per annotator) and the **kept set**: the annotations in `annotations/<task>.jsonl` in Git, which people decide. Tuldok measures how far the sets agree, lists the records where they disagree most, draws each set over the record, and a person keeps one set's annotation, both, or neither; that decision is written by the existing working copy and Save. People review instead of drawing.

**Words.** As spec-d4: record, annotation, task, term. An **annotator** is what made a set: a model, a script or a person. A **set** is the annotations of one annotator for one task. The word "label" is not used.

## 1. The new types of task

A task's `task` may now also be one of these. Coordinates on an image are pixels with the origin at the top left, x right, y down; a point may lie on the far edge (`x ≤ width`).

| Task | An annotation's `value` | On records of kind | Vocabulary |
| --- | --- | --- | --- |
| `polygons` | a list of `{"term", "points": [[x, y], …]}`, 3 to 10,000 points each, inside the image | image | required |
| `mask` | an object: `{"file": <sidecar .png>}` or `{"rle": [[v, n], …]}`, and `"classes": {"<v>": term, …}` | image | required |
| `depth` | an object `{"file": <sidecar .npy>}` | image | none |
| `keypoints` | a list of `{"term", "points": [p, …]}`, one `p` per name of the task's `keypoints`, each `[x, y]`, `[x, y, v]` (v 0, 1 or 2 as COCO's visibility) or `null` | image | required |
| `ranking` | a list of different terms, best first, at least one | any but `file` | required: the candidates |
| `timeseries` | a list of `{"term", "start", "end"}`, `start` < `end`: seconds of a sound, or positions along the first axis of an array | audio, array | required |
| `track` | a list of `{"track", "term", "frames": [{"frame", "x", "y", "w", "h"}, …]}`, frames increasing; `track` an id of 1 to 64 characters, different in one annotation | array (frames on its first axis) | required |
| `points` | a list of `{"term", "indices": [i, …]}`, indices increasing, each below the cloud's point count; or an object `{"file": <sidecar .npy>, "classes": {"<id>": term}}` of one whole number per point (0: no object) | pointcloud | required |
| `box3d` | a list of `{"term", "center": [x, y, z], "size": [l, w, h], "yaw"}`, sizes above zero, `yaw` in radians about z | pointcloud | required |

- **Fields of the task** for these types: `keypoints` (1 to 100 different names, required for and only for `keypoints`), `skeleton` (pairs of those names, optional), `units` (a string of 1 to 40 characters for `depth`, such as `m`, required for it), `mask` (`semantic` or `instance`, default `semantic`, only for `mask`).
- **Confidence.** Any item of a list value, and the object of a `mask`, `depth` or `points` file value, may carry `"confidence"`: a number from 0 to 1. A set's line may carry one too (section 3).
- **A mask.** `classes` maps a pixel value (1 to 65,535, written as its decimal text) to a term; 0 is nothing. In a `semantic` mask a pixel's value is its class; in an `instance` mask each value is one object and `classes` names its term. `rle` is the mask row by row from the top left as runs `[value, count]`, counts above zero, summing to width × height. A sidecar PNG is 8- or 16-bit greyscale, not interlaced, of the image's size.
- **A depth map** is a 2-D `.npy` of float32, float64 or uint16 of shape (height, width); 0 and values that are not finite mean no depth; its units are the task's.
- **A point-id file** is a 1-D `.npy` of whole numbers (8 to 64 bits), one per point of the cloud.
- **Checked against the record** where cheap: an image's size (polygons, keypoints, masks, depth maps), a cloud's point count (points), an array's shape (track: frames below its first axis's length, boxes inside its second and third; timeseries on an array: ends at most its first axis's length), a sound's length (timeseries, from WAV only, as segments).
- **Bounds:** 1,000 items in a list value (as spec-d4), 10,000 points in a polygon, 1,000,000 indices in a `points` value, 10,000 frames in a track, 4,000 runs of `rle` per image row on average and 16 Mpx for a mask or depth map, 256 classes.
- **Key order** of an item: `track`, `frame`, `term`, `x`, `y`, `w`, `h`, `start`, `end`, `text`, `points`, `indices`, `center`, `size`, `yaw`, `frames`, `confidence`; of an object value: `file`, `rle`, `classes`, `confidence`; `classes` by number. Inside `frames` the same order.

`spans`, `segments`, `boxes`, `class`, `tags`, `text` and `review` are unchanged, but their list items may carry `confidence` too.

## 2. Sidecars: payloads too large for a line

A value that names a `file` names a **sidecar**: a file beside the annotations it belongs to.

- **In the kept set** (Git): `annotations/<task>/<name>`, where `<name>` is the first 16 hexadecimal characters of the file's SHA-256 and `.png` or `.npy`. Content-addressed: the same mask kept twice is one file, a name never changes meaning, and a file is never rewritten. The directory holds such files only (no links, no subdirectories).
- **In a set made by an annotator:** `files/<path>` of its product, any relative path.
- `check`: a sidecar directory with no task of its name is an error; a line naming a sidecar that is not there is an error; a file of the directory no line names is a warning ("Save removes it").
- **Kept from a set** (section 6), a sidecar is copied into the working copy (the database), and written to `annotations/<task>/` by Save, with the line that names it; Save also removes the files of that task's directory that no saved line names. A sidecar is at most 64 MiB.

## 3. The annotation set: what an annotator writes

The product of a dataset whose `run.step` is `annotate`:

```
annotator.json        {"format": "tuldok_annotator_v1", "task": "annotations/<task>", "by": {...}, "records": n, "made": m, "at": "…Z"}
annotations.jsonl     one line per record annotated, sorted by record
files/                the sidecars its lines name
```

A line is `{"record", "sha256", "value", "confidence"?, "note"?}`: the record's id, its hash as the input's `records.jsonl` gives it (or null), a value as section 1 and spec-d4 say for the task (never null), an optional confidence for the whole annotation, and an optional note of at most 4,000 characters.

**Provenance.** `by` is `{"kind": "model" | "script" | "person", "name", "version"?, "settings"?}`: names of 1 to 200 characters, `version` up to 200, `settings` an object of at most 8 KiB. It holds for every line of the set. A line kept from a set into Git carries it in `from` (section 6), so the kept annotation still says what made it.

## 4. The step `annotate`

A dataset whose `run` has `step: "annotate"`, `inputs: {"records": <the task's dataset>}`, `annotations: [<one task>]`, and settings:

| | |
| --- | --- |
| `by` | required: `kind`, `name`, `version` as section 3 (Tuldok adds `settings`: the run's settings without `by`) |
| `pumas` | `{"model", "profile"?, "instruction"?}`: ask a model the endpoint serves. Excludes `run.command` |
| `limit` | at most this many records, 1 to 1,000,000 (default all) |
| `options` | any JSON object of at most 8 KiB, passed to the command (in `TULDOK_ANNOTATE_OPTIONS`) and recorded in `by.settings` |

Exactly one of `run.command` and `settings.pumas`. Unlike `import`, `freeze` and `generate`, an `annotate` with a command also takes `run.environment` (and `env`), since the command is the project's: **the project's code runs in its environment, not in Tuldok.**

**With a command.** Tuldok's step process (as for every step) reads the input's records, writes the records still to do to `<run>/todo.jsonl` (lines of the input's `records.jsonl`, the files' paths made absolute), then runs the command, from the code snapshot, with the environment's interpreter, with:

| Variable | |
| --- | --- |
| `TULDOK_RECORDS` | the input product's directory |
| `TULDOK_TODO` | the records to annotate |
| `TULDOK_TASK` | the task's definition, as a file |
| `TULDOK_ANNOTATIONS` | the file to append lines to: `<output>/annotations.jsonl` |
| `TULDOK_FILES` | the directory for sidecars: `<output>/files` |
| `TULDOK_ANNOTATE_OPTIONS` | `settings.options` as JSON, or `{}` |

The command appends one line per record, in any order, and may print `tuldok_progress_v1` lines (they pass through). When it ends with status 0, the step reads what it wrote, keeps the last line of each record of the input with a valid value, counts and drops the rest (an unknown record, an invalid value, a sidecar that is missing or outside `files/`), writes the lines sorted, and `annotator.json`. A command that fails fails the step.

**With the Pumas endpoint.** Only what a served model can produce, from what spec-d5 already asks:

| Task | Record | Asked as |
| --- | --- | --- |
| `text`, `class`, `tags` | text, image, audio | as `suggest_annotation` (spec-d5 section 4, as built) |
| `boxes`, `polygons` | image | `image_to_text` with an instruction asking for a JSON list of `{"term", "x", "y", "w", "h"}` (or `points`) in pixels of the image of the size given, terms from the vocabulary; an answer that is not such a list is a refusal for that record |

A record the model's answer does not fit is counted as refused and skipped; the step fails only when the endpoint cannot be reached or refuses every record of the first ten. `by` gets `kind: model`, the model, profile and capability.

**Bounded, resumable, with progress.** Progress is records done of records to do. Lines are appended as they are made. A run of the same definition that failed or was cancelled leaves its lines: the next build starts from them (`--resume`), copying the valid lines (and their sidecars) of records whose hash is unchanged, and annotates only the others. A run never reads or writes outside its output and run directory.

**`by.settings`** is the run's `settings` without `by`, so a set's provenance is what its definition says; the definition, in Git, is what made it.

## 5. Quality control: agreement between sets

The **sets of a task** are its kept set (`kept`: the working copy's annotations with a value, in any state but rejected) and the current product of every dataset that annotates it (`annotate` with `annotations` naming it), each named by that dataset's reference.

**Pairs.** For two sets, a record is compared when either has an annotation for it. One without an annotation (or with one emptied by the confidence filter, below) scores 0 on that record and is listed as missing. Each record gets an **agreement** from 0 to 1; a pair's agreement is the mean over its records. With more than two sets, a record's agreement is the mean over the pairs that compare it, and its **disagreement** is 1 minus that. The **most disputed** records are those of greatest disagreement, ties broken by record id.

**Per type** (what one record scores for one pair, and what the pair also reports):

| Task | A record's agreement | The pair also reports |
| --- | --- | --- |
| `class` | 1 when the terms are equal, else 0 | Cohen's kappa over the records both annotated; with three or more sets, Fleiss' kappa over the records every set annotated |
| `tags` | Jaccard of the two term sets (1 when both are empty) | |
| `text` | `difflib.SequenceMatcher` ratio of the first 4,000 characters | exact matches |
| `ranking` | (τ + 1) / 2, Kendall's τ over the candidates both rank (1 when fewer than two are shared and those agree) | mean τ |
| `boxes`, `polygons`, `box3d`, `points` (both forms), `mask` (`instance`) | matched IoU: objects of the same term matched one to one maximising the summed IoU; the sum of the matched IoUs over the larger of the two counts (1 when both are empty) | mean IoU of matches, matches, F1 at IoU 0.5 |
| `mask` (`semantic`) | mean over the terms either uses of their pixel IoU | |
| `keypoints` | as matched IoU with OKS in place of IoU | mean OKS of matches |
| `depth` | 1 − min(1, mean ‖a − b‖ / mean (‖a‖ + ‖b‖) / 2) over pixels with depth in both | mean absolute difference in the task's units, δ < 1.25 |
| `spans`, `segments`, `timeseries` | mean over the terms either uses of the interval IoU (length of the intersection of the unions over that of the union) | |
| `track` | tracks of the same term matched as above by their track IoU (the mean box IoU over the frames either has, a frame one lacks scoring 0) | identity switches, fragments |
| `review` | not compared | |

- **IoU.** Boxes: exact. Polygons: both drawn on a grid over their joint bounding box at most 128 × 128 cells, pixel centres, even-odd rule (so IoU is exact to the grid). Masks: by pixel, decoded. Point sets: of the index sets (a point-id file becomes one object per id). 3-D boxes: the area of the intersection of the two rotated rectangles seen from above (convex clipping) times the overlap of their heights, over the union of volumes.
- **Matching.** The Hungarian method (minimising 1 − IoU) when both sides have at most 64 objects of a term; otherwise greedy, the pair of greatest IoU first. Pairs with IoU 0 are not matches.
- **OKS** of two instances: the mean over the keypoints both have (visibility above 0 where given) of exp(−d² / (2 s² κ²)), s² the mean of the areas of the two instances' bounding boxes of their points (at least 1 px²), κ = 0.1 (the task may say `sigma`). A keypoint one has and the other lacks scores 0.
- **Tracks.** An identity switch: for a track of the first set, its box in each frame is matched to the box of greatest IoU (above 0.5) of the second set; a change of the matched track from one matched frame to the next counts one. A fragment: a gap in a track's frames (its frames are not consecutive). Both are counted per set and per pair.
- **Kappa.** Cohen's: (p_o − p_e) / (1 − p_e) with p_e from each side's term frequencies; 1 when p_e is 1. Fleiss': with n sets per record, P̄ from the agreeing pairs per record and P̄_e from the overall term shares; 1 when P̄_e is 1.
- **Confidence filter** (`min_confidence`): items below it are dropped from list values; a line (or a mask, depth or point-id object) below it is treated as no annotation. A value with no confidence passes.
- **Bounds.** At most 8 sets; the agreement reads at most 20,000 records per set and stops there, saying so; masks and depth maps over 16 Mpx are not compared (listed with the reason).

## 6. Operations

All in the `project_folder` profile, absent from `catalog` (its digest unchanged).

| Operation | Who | Arguments | Result |
| --- | --- | --- | --- |
| `annotation_sets` | inspect | `task` | `task`, `type`, `sets`: each `set` (`kept` or a dataset reference), `title`, `by`, `run`, `annotated`, `skipped` (lines not valid), `problem` (a set that cannot be read, with why) |
| `annotation_agreement` | inspect | `task`; `sets` (2 to 8; default every set that can be read); `min_confidence`; `offset`, `limit` (of the disputed list, at most 200) | `task`, `type`, `sets`, `measure` (what the score is, in words), `pairs` (`a`, `b`, `records`, `agreement`, and the type's figures), `fleiss`, `records` (compared), `disputed` (`record`, `disagreement`, `pairs` {`a|b`: agreement}, `missing`), `total`, `offset`, `limit`, `truncated` |
| `annotation_compare` | inspect | `task`, `record`, `sets` (1 to 8), `min_confidence` | `task`, `type`, `record`, `sets`: each `set`, `value` (null when none), `confidence`, `drawn` (masks as `{width, height, rle}` by term, depth as `{width, height, low, high, values_u8}` downsampled to at most 256 px a side, point-id files as `points` lists), `problem`; `pairs` (this record's agreement per pair and the type's figures); `frames` (for `track`: the array's frames as 8-bit grey, at most 64 frames of at most 128 px a side) or `series` (for `timeseries` on an array: at most 1,024 positions of at most 8 channels) |
| `keep_annotation` | edit, changes | `task`, `record`, `keep` (`one`, `both` or `none`), `sets` (one set for `one`, two for `both`, any for `none`), `note` | `task`, `record`, `state`, `unsaved` |

`keep_annotation` writes the kept set through the same path as `set_annotation` (checked against the task and the record, unsaved until Save, one activity row): `one` keeps that set's value as `accepted` with `from` `{"set", "run", "by"}` (`by` without `settings` when it would pass 2 KiB); `both` keeps the union of two list values (refused `invalid` for a type whose value is not a list) with `from` naming both; `none` keeps `rejected` with a null value and `from` naming the sets rejected. A kept value's sidecars are copied (section 2). `kept` cannot be named for `one` or `both` (it is already kept).

## 7. The page

**The Annotate tab gains a second mode, Review**, chosen in the bar when the task has at least one set made by an annotator. Annotate mode stays as spec-d4 built it; for the new types its form shows the kept value drawn over the record and the decision, with no drawing tools.

Review mode, in the tab's three columns:

- **Left: the agreement and the most disputed records.** Two set choosers (A and B; any two of the task's sets), the confidence filter, the measure in words, A–B's agreement and the type's figures (with Fleiss' kappa when there are three or more sets), then the disputed records in order, each with its disagreement as a number and a bar; selecting one shows it.
- **Middle: the record with the sets drawn over it.** Side by side (A left, B right) or overlaid (A and B in two colours, what only one has marked), switched by a toggle. On an image: boxes, polygons, keypoints (with the skeleton), masks (as colour by term or instance, half transparent), depth (as a colour map, with its scale). On a point cloud: each point object's points coloured by its term, the 3-D boxes as wireframes. On a sound or an array of one or two axes: timeseries, segments as bands under the waveform or the series. On an array of frames: the frame with each track's box and id, a frame slider and the arrow keys. Text: spans marked.
- **Right: the decision.** Each set's value in words (count of objects, terms, confidences), this record's agreement, **Keep A**, **Keep B**, **Keep both** (for list values), **Reject both**, a note; then **Save** (the strip's). A record already kept shows what was kept and from which set.
- **Light correction**, only on the kept value and only where cheap: a kept polygon's vertex can be dragged or deleted (select it, then Delete); a kept point object's points can be removed by dragging a rectangle on the cloud's view while "Remove points" is on. Each correction is kept with `set_annotation`, as an unsaved edit.

Updating in place (spec-w4): the disputed list, the record and the decision are drawn in parts, each put in place only when what it shows differs; a reading that changed nothing redraws nothing; the choice of sets, the filter, the mode and the frame are the page's and survive readings.

## 8. Slices

| | Slice | Mainly |
| --- | --- | --- |
| T4a | The nine types, their fields, values and checks against the record; sidecars in the folder, `check` | `annotations.py`, `schemas/annotation.schema.json`, `annotation_records.py` (`facts`), `folder.py`, `store.py` (listing), `check.py` |
| T4b | The set format and its reader; the step `annotate` with a command and with Pumas; resume | new `annotation_sets.py`, `steps.py`, `builds.py`, `check.py`, `schemas/` (run) |
| T4c | Agreement: the measures, matching, the disputed list | new `annotation_agreement.py` |
| T4d | The four operations; the sidecar copy and Save | `operations.py`, `service.py`, `annotation_rows.py`, `store.py` |
| T4e | Review mode and the overlays, light correction | new `static/project-workspace/review.js`, `annotate.js`, `inside.js` (exports), `base.css`, `app.py`, `project-workspace.html` |
| T4f | The example's small data and stand-in annotators; the browser check | `examples/tiny-project`, `tests/` |

`docs/contracts/project-folder.md` is brought up to date for the types, sidecars, sets and the step.

## 9. Tests

- **T4a,** `tests/test_tuldok_project_annotation_kinds.py`: a valid value of each type checks and each rule of section 1 broken once gives its error; checks against an image's size, a cloud's count, an array's shape and a sound's length; a sidecar PNG and `.npy` read and refused when of another size or type; RLE that does not sum; a line file of each type written and read back byte for byte, key order included; a sidecar directory without its task, a missing sidecar and an unreferenced one in `check`.
- **T4b,** `tests/test_tuldok_project_annotate_step.py`: two stand-in segmentors (scripts in the test, run in a test environment) annotate four small images and two small clouds of a dataset built by `import`; each set has the lines, sidecars and `annotator.json` expected; a line with a bad value or unknown record is dropped and counted; a failed run is resumed and annotates only the rest; the Pumas route against the fake endpoint for `class` and for `boxes`, an answer that is not a list refused; nothing contacts a real Pumas.
- **T4c,** `tests/test_tuldok_project_annotation_agreement.py`: every measure of section 5 against the test's own arithmetic on hand-made values: kappa and Fleiss on a known table, Kendall's τ, interval IoU, box, polygon (a square in a square), mask (instance and semantic), point-set and 3-D box IoU (a rotated pair), OKS, track switches and fragments, the Hungarian matching against brute force, the confidence filter, the disputed order.
- **T4d,** in the same file and `test_tuldok_project_service.py`: the four operations on the stand-ins' sets; `keep_annotation` one, both and none, Save writing the line and the sidecar, a second Save removing an unreferenced sidecar; refusals.
- **T4e and T4f,** `tests/browser_project_workspace_annotation_kinds.cjs`: on a project whose stand-ins have run, overlays drawn for each type of the fixture (masks, polygons, depth, keypoints, point objects, 3-D boxes, timeseries, tracks across frames), two sets compared side by side and overlaid, the agreement shown, the disputed list in the computed order, one record reviewed and kept (Save writes `annotations/`), a polygon vertex moved, nothing rebuilt by a reading that changed nothing; light and dark at 1440 and 390 px, nothing overflowing sideways, no script error.

## 10. Out of scope

A drawing editor (drawing masks, polygons, keypoints or 3-D boxes by hand); video files as records (frames are an array); agreement for `review` tasks; exporting sets to COCO or other formats; per-term confusion matrices; a set made by a person outside the kept set (a second person's set is an annotator's product like any other); weighting annotators.

## As built

What differs from the text above, and what was chosen where it was silent.

### T4a, the types and the sidecars

- **The fields a task's values are checked against** (`keypoints`, `skeleton`, `units`, `mask`, `sigma`) are passed as `annotations.task_fields(document)`; `value_problems`, `validate` and `read` take them, and the working copy's fingerprint of a task now includes them (the fingerprint of a task without them is unchanged, so no row is judged again on upgrade). `check` also refuses a skeleton naming a point that is not in `keypoints`.
- **Sidecar names** are the first 16 hexadecimal characters of the SHA-256 and `.png` or `.npy`. The folder reader lists `annotations/<task>/` (names and sizes, nothing read); a file not named that way is an error, as a link or a subdirectory is. The store's listing skips such a directory when its task exists, and never compares it for changes on disk: content-addressed files are never rewritten.
- **The byte formats** are in a new pure module, `annotation_payloads.py` (the step process imports it): a PNG reader for 8- and 16-bit greyscale with every row filter, a PNG writer, runs (`[value, count]`, row by row), and an `.npy` reader and writer (C order, floats and whole numbers; never unpickled). `rle` in a value is checked for its shape in a line, and against the image's size only where the size is known (an edit, a set's line in the step).
- **A test changed:** `test_tuldok_project_annotations.py` used `polygons` as its example of an unknown task; it now uses `video`.
- **Not checked against the record:** a JPEG's size in the step (PNG only); a sound's length in the step (the set reader in Tuldok checks it as before for `segments`; `timeseries` on a sound is checked when kept); `rle` in the folder check (the image's size is not known there).

### T4b, the step `annotate`

- **`run` in all four run schemas:** `step` gains `annotate`; `command`, `environment` and `env` are refused only for `import`, `freeze` and `generate`; `annotations` belongs to `freeze` or `annotate`. `check` asks for one input `records`, one task, exactly one of `run.command` and `settings.pumas`, `by` as section 3, `limit` and `options` in their bounds, and that the task annotates the input.
- **The command's process.** Tuldok's step process (`python -m tuldok_project.steps annotate … --command-json …`) runs the command with `subprocess.call`, from the code snapshot, its argv filled and its program found as a build's are (`python` is the environment's interpreter). The command's environment is the run's without `PYTHONSAFEPATH` and `PYTHONPATH` (which make Tuldok's own code importable to the step); a `PYTHONPATH` the run's `env` set is given back to it. Its output goes to the run's log, so its progress lines are the run's. The task file is `<run>/tasks.json` (`{reference, document}`) and `<run>/task.json` (the document) for the command.
- **Resume** takes the latest run of the same reference whose state is neither succeeded, running nor queued and whose definition text is the same, when its output holds `annotations.jsonl`.
- **What is dropped and counted:** a line that is not JSON, not a line of section 3 (unknown keys, no record, no value), a record the input lacks, a value the task does not allow (null included), a sidecar missing, outside `files/` or not of the record's size or point count; a record annotated twice keeps its last valid line.
- **The Pumas route** asks `pumas.suggest` record by record (`by.model` records model, profile and capability); `boxes` and `polygons` on an image are asked of `image_to_text` with an instruction naming the image's size and the terms, and the first JSON list in the answer (a fenced block too) is kept when it is a value of the task. The step fails when each of the first `min(10, records)` is refused. `pumas.routes` now offers this route to `suggest_annotation` and `suggestion_models` as well; the page still asks only for `text`, `class` and `tags` (`test_tuldok_project_pumas.py`'s table of routes was brought up to date). A plan marks an `annotate` with `pumas` blocked when no endpoint is set, as a `generate`.
- **Not verified:** a real Pumas; polygons asked of a model (only boxes against the fake); cancelling a run while its command runs (the launcher stops the process group, as for any run); a set of many records.

### T4c, agreement

- As section 5. **Polygon IoU** is exact to the grid (1 px cells up to 128 px across, coarser above). **3-D IoU** clips the footprints with Sutherland–Hodgman. **Greedy matching** above 64 objects a term per side. A pair's figures are pooled over its records: mean IoU weighted by matches, F1 averaged per record.
- **Not measured:** time on large sets. Masks and depth maps are compared pixel by pixel in Python (a second or so per megapixel, by estimate).

### T4d, the operations

- **`keep_annotation`** reads the sets outside the service's lock, stages a kept sidecar in a new table `annotation_sidecars` (task, name, bytes), then goes through `_prepare_annotations` and `_set_annotation` as `set_annotation` does: the same checks against the record, one activity row (`"<record> accepted"` or `rejected`). `from` is `{"set", "run", "by"}` for one set, `{"both": [...]}` for two, `{"rejected": [...]}` for none, each cut to the 2 KiB `from` allows (first `by.settings`, then `by`). Keeping both tracks renames the second set's repeated track ids (`-2`, …).
- **Save** writes a task's staged sidecars that its saved lines name, removes from `annotations/<task>/` the content-named files no saved line names (and the directory when empty), and drops the task's staged rows. A revert leaves staged rows until that task's next Save.
- **The kept set** for agreement and review is the working copy's annotations with a value and not rejected, unsaved ones included, stale ones not left out.
- **Operations:** 76 (four new, `keep_annotation` a mutation); the catalog profile is unchanged.

### T4e, the page

- **Review** is a mode of the Annotate tab (`Annotate | Review` in the bar, offered when a task has a set made by an annotator); `review.js` (`window.LabReview`) draws it into the tab's own three columns, and `review.css` styles it (base.css is untouched). `annotate.js` gained the nine types (New task asks for keypoints, units and the mask's kind), the mode, and, for the new types in Annotate mode, the kept value in words and drawn read-only over an image or a point cloud.
- **Colours:** A is `--ramp-neg`, B `--ramp-pos`, both `--good`; one set alone is coloured by term. Overlaid, an object with no counterpart of the same term at a box IoU of 0.5 is drawn dashed (a quick greedy test in the page, for marking only); masks are coloured A only, B only and both by pixel; depth maps show A − B on the diverging ramp.
- **inside.js** exports `space` and `turned`; `space` draws `m.lines` (wireframes) and, with `m.select` and `st.selecting`, a dragged rectangle whose shown points it reports (`stride` is accounted for by the caller).
- Each panel carries `data-drawn` (what it drew per set), read by the browser check.
- **Not covered:** keyboard-only correction of polygons (the vertex is chosen and dragged by pointer; Delete needs the canvas focused); a session that may only inspect (the decision buttons are hidden by the usual rule); more than 200 disputed records listed (the list says how many are not); screen readers.

### T4f, the example and the checks

- `examples/tiny-project` gained `code/make_scenes.py` (writing `code/scenes`, 3,897 bytes: three 24 × 16 images, two point clouds of 20 and 30 points, 6 frames of 16 × 20, a series of 48 × 2), `code/annotators/standin.py` (one stand-in for mask, polygons, depth, keypoints, points, box3d, timeseries and track), `datasets/scenes`, `annotations/scene-masks` and `scene-objects`, and four annotators. `check` reports nothing. The example's annotators were not built here: its environment `cpu` needs numpy, which this checkout's interpreter lacks; the same stand-in is built by the browser check in an environment of its own.
- **Tests:** `test_tuldok_project_annotation_kinds.py` 15, `test_tuldok_project_annotate_step.py` 6, `test_tuldok_project_annotation_agreement.py` 21; project suite 828 (786 before), agent interface 43 (4 skipped). `tests/browser_project_workspace_annotation_kinds.cjs` passes (steps 1 to 6 of its header, 4b being the point correction; 4b's rectangle happens to take all nine points of the kept object, so a partial removal is not shown).
- **Regression checks:** `browser_project_workspace.cjs` passes (24). `browser_project_workspace_inside.cjs`, `_annotate.cjs` and `_endpoint.cjs` fail here exactly as they do on the base of this branch (`7a0b3665`, run from an archive of it): at 1000 px the page overflows sideways by 65 px (`page` 65, the main area 0), and `_annotate.cjs` also still expects the tab list without phase 3's Compare. With that one expectation updated (in a throwaway copy), `_annotate.cjs` passes the same nine steps before the same overflow on both trees; `_inside.cjs` and `_endpoint.cjs` pass six steps on both. The overflow is not this phase's and was not fixed here.
