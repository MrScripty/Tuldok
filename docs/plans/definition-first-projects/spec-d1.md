# Implementation spec: looking inside a product

This is phase 1 of [the data tools plan](data-tools-plan.md). Section 1 of [spec-m1-m2.md](spec-m1-m2.md) (rules for implementers) applies, with the import rule as amended by [spec-m7.md](spec-m7.md), and the page follows [spec-w4.md](spec-w4.md) (it updates in place). The old project mode named in those rules is deleted; catalog mode's modules (`scientific_fields.py`, `volume_assets.py`, `pointclouds.py`, `meshes.py`, `audio_assets.py`) may be read for how they parse a format, and nothing is imported from them.

**After this phase** Tuldok can open the output of any finished run of a project folder: page through its records, show a text, an image, an audio clip, a point cloud, a mesh or an array, and browse its files and archives. Nothing is written anywhere: no file, no row. Nothing here annotates, generates or calls Pumas.

## 1. Terms

- **Product:** the `output` directory of a run in state succeeded or adopted. It is named by its run id.
- **Record:** one item of a dataset. Its **kind** is one of `text`, `image`, `audio`, `pointcloud`, `mesh`, `array`, or `file` for anything else (listed, never opened).
- **Address:** a POSIX path relative to the product, never absolute, never containing `..`. A member of a zip archive is addressed by `!`: `training-view.zip!samples/a.npz`. At most two `!`. An `.npz` is a zip of `.npy` members; one of its arrays is named separately (`array`), without the `.npy`.

## 2. Where a product's records come from

In this order:

1. **`records.jsonl` at the product's root.** One JSON object per line:

   | Key | |
   | --- | --- |
   | `id` | required; unique; 1 to 200 characters of `A-Z a-z 0-9 . _ -` |
   | `kind` | required; one of the six |
   | `path` | an address; required unless `kind` is `text` and `text` is given |
   | `text` | the text itself, for a short text record (at most 64 KiB) |
   | `array` | for kind `array` in an `.npz`: the array to show first |
   | `split`, `rights` | optional strings |
   | `origin`, `meta` | optional objects, kept and shown as they are |

   Other keys are kept and shown with `meta`. A line that is not such an object is counted and its line number reported (the first 20), and the rest are read.
2. **`view` on the dataset's definition** (new, optional, datasets only):

   ```json
   "view": {"records": "lists/all.jsonl"}
   "view": {"files": "training-view.zip!samples/*.npz", "kind": "array", "show": "target_pressure"}
   ```

   `records` names a record list elsewhere in the product. `files` is a pattern: `*` and `?` within one path segment, `**` across segments; it may reach into one archive. Each match is a record whose id is its address. `kind` (default: by extension) and `show` (the array drawn first) apply to every match. `records` and `files` exclude each other. `check` validates the shape of `view` and nothing about the product.
3. **Otherwise every regular file** under the product is a record, sorted by address, its id its address, its kind by extension:

   | Kind | Extensions |
   | --- | --- |
   | text | `.txt .md .json .jsonl .csv .tsv .yaml .yml .log` |
   | image | `.png .jpg .jpeg .webp .gif .bmp` |
   | audio | `.wav .flac .mp3 .ogg .opus .m4a` |
   | pointcloud | `.xyz`, and `.ply` with no faces |
   | mesh | `.obj .stl`, and `.ply` with faces |
   | array | `.npy .npz` |
   | file | everything else |

## 3. Operations

All five are `inspect` reads in `tuldok_project/operations.py`, served and published like the others. Every one takes `run`. A run that does not exist, is not finished or has no output directory is refused `not-found`.

| Operation | Arguments | Result |
| --- | --- | --- |
| `records` | `offset`, `limit` (at most 200), `kind`, `split` | `records` (each: `id`, `kind`, `path`, `bytes`, `split`, `rights`, `origin`, `meta`; a text record's first 400 characters as `preview`), `total`, `source` (`records.jsonl`, `view` or `files`), `kinds` and `splits` (counts), `problems` |
| `record` | `id` | `record` (as above, with `media_type` and, for image and audio, `url`) and `content`, by kind, below |
| `inside` | `path` (default the root), `offset`, `limit` (at most 500) | `entries` (each: `name`, `path`, `type` of `directory`, `file`, `archive` or `array`, `bytes`, `kind`; for an array `shape` and `dtype`), `total`. A directory lists its children, an archive its members as a tree, an `.npz` its arrays |
| `array_slice` | `path`, `array` (for an `.npz`), `axes` (the two axes drawn, default the last two), `index` (one position per axis, default the middle; ignored for the two drawn), `most` (rows and columns at most, default 256, at most 512) | `shape`, `dtype`, `axes`, `index`, `rows`, `columns`, `stride` (1 unless subsampled to fit `most`), `values_f32` (base64, little-endian 32-bit floats, row by row), `min`, `max`, `nonfinite` |
| `array_summary` | `path`, `array`, `bins` (default 64, at most 256) | `shape`, `dtype`, `count`, `min`, `max`, `mean`, `std`, `zeros`, `nonfinite`, `histogram` (`low`, `high`, `counts`), `stride` (1 unless sampled) |

**`content` of `record`, by kind:**

| Kind | Content | Read from |
| --- | --- | --- |
| text | `text` (at most 262,144 characters), `characters`, `truncated`, `replaced` (bytes that were not UTF-8) | the file or the record's own `text` |
| image | `width`, `height` (from the file's header; null when not found) | PNG, JPEG, GIF, WebP, BMP headers. The pixels reach the page by `url` |
| audio | for a WAV of PCM (8, 16, 24, 32 bit) or 32-bit float: `channels`, `rate`, `frames`, `seconds`, `peaks` (at most 1,000 pairs of lowest and highest sample, scaled to -1..1, over all channels). Other formats: nulls | the `wave` module and `struct`. The sound reaches the page by `url` |
| pointcloud | `count`, `bounds`, `points_f32` (base64 x, y, z; at most 100,000 points, evenly sampled above that with `stride`), `colors_u8` (base64 r, g, b, or null) | PLY (ASCII and binary little-endian), XYZ text, and an `.npy` of shape (N, 3 or more) when the record says its kind is `pointcloud` |
| mesh | `vertices`, `triangles` (counts), `bounds`, `positions_f32`, `triangles_u32` (base64; polygons split into triangles as a fan) | PLY (ASCII and binary little-endian), OBJ (`v` and `f`, with `/` forms and negative indexes), STL (binary and ASCII) |
| array | `arrays` (each: `array`, `shape`, `dtype`, `bytes`), `show` (the record's `array`, else the view's `show`, else the first with two or more dimensions) | the `.npy` header of each member |
| file | nothing | |

**Arrays.** NPY versions 1, 2 and 3; C and Fortran order; little- and big-endian; floats of 2, 4 and 8 bytes, signed and unsigned integers of 1 to 8 bytes, booleans. Anything else (complex, strings, structured types) is refused `unsupported`. An object array is refused and **nothing is ever unpickled**. The header is parsed with `ast.literal_eval` and is at most 64 KiB.

**Reading no more than is needed.** A file on disk, and a member stored uncompressed in a zip that is on disk, are read through `mmap` at the offsets the slice needs. A compressed member is decompressed whole into memory, so is an archive inside an archive. What was decompressed is kept for the next read of the same member, least recently used first out.

## 4. Bounds

| | Bound | Beyond it |
| --- | --- | --- |
| One line of a record list | 64 KiB | the line is a problem |
| Files walked when there is no list and no view | 200,000 | the rest are not listed, and `problems` says so |
| A member decompressed into memory | 256 MiB, by the size the archive declares, and enforced while reading | refused `too-large` with the size |
| Kept decompressed data, all products together | 512 MiB | least recently used dropped |
| Values read for one summary | 4,000,000 | every n-th value is read; `stride` says n |
| A point cloud or mesh file parsed | 256 MiB | refused `too-large` |
| A mesh returned | 200,000 vertices, 400,000 triangles | refused `too-large` with the counts |
| Record indexes kept in memory | 8 products | least recently used dropped; an index is rebuilt when the list's size or time changes |

## 5. The bytes of an image or a sound

`GET /api/project/file?run=<id>&path=<address>`, for whoever may call an `inspect` operation, and refused like one otherwise. It streams the file, or the archive member within the bound above.

- The media type comes from a closed table by extension, for the image and audio extensions of section 2 only; those are sent `inline`. Everything else is `application/octet-stream` with `Content-Disposition: attachment`. No product file is ever sent as HTML, SVG or script.
- `X-Content-Type-Options: nosniff`, `Cache-Control: no-store`.
- One `Range: bytes=a-b` is honoured for a file on disk (a sound must be seekable); anything else in `Range` gets the whole file.
- This route is not an operation and is not in the capability manifest: an agent reads records, arrays and text through the operations, and not media bytes.

In project-folder mode `app.py` refuses every other `/api/` GET as before.

## 6. Confinement

- An address is resolved under the product directory; the resolved real path must lie inside it. A symbolic link that leaves it is refused `not-found`, as is a missing file. Hard links are ordinary files.
- Archive members are read, never extracted to disk.
- No operation here opens the project for writing, imports files or changes a row.

## 7. The page

The Data tab has two states: the cards, as now, and one dataset opened (`#data/<reference>`).

- **A card and the dataset's drawer** gain "Look inside" when the dataset has a current product. A dataset with several products (subjects) offers them in a select.
- **The dataset opened:** its title and the product's run, date and size; the kinds and splits with counts, as filters; a pager; the records as a grid of 48 tiles; the selected record's viewer beside the grid (below it under 1,100 px). A "Files" switch shows the product as a tree instead (`inside`), from which any file or array opens in the same viewers. Left and right arrows move the selection.
- **Tiles.** Text: its first characters. Image: the image, scaled by the browser, loaded lazily. Array: a small middle slice of the array shown first, read lazily. Audio, point cloud, mesh, file: the kind's glyph. Every tile carries the record's id.
- **Viewers:**

  | Kind | Shows |
  | --- | --- |
  | text | the text, wrapped, with its length; "truncated" when it is |
  | image | the image fitted to the panel; a click toggles actual size; width and height |
  | audio | the waveform from `peaks` and the browser's own player; length, rate, channels |
  | pointcloud | the points on a canvas, turned by dragging, zoomed by the wheel; coloured by their own colours or by height; the count, and "every n-th shown" when sampled |
  | mesh | the triangles, flat shaded, turned and zoomed the same way; above 60,000 triangles the vertices as points, saying so; the counts |
  | array | the arrays with shape and type; for the chosen one a slice with the two axes, a slider per other axis, the range, and the value under the pointer; for three or more dimensions the stacked-slice drawing of the mockup (`drawVolume` in `docs/plans/project-workspace-redesign/mockups/screens.js`); the summary's histogram on request |
  | every kind | the record's `origin`, `meta`, `rights` and `split` when it has them |

- **Drawing.** Canvas 2D, no library, no external reference, the tokens of `base.css`, light and dark. New code in `static/project-workspace/inside.js`; `adapter.js` gains the calls. Catalog mode's `static/scientific-inspector.js` may be used through an adapter or its logic rewritten in the workspace's own module; whichever is chosen is recorded under "As built".
- **Updating in place** (spec-w4): the answers of these operations are not watched; they are forgotten when a watched answer changes, and the dataset opened is then drawn again in place, keeping page, selection and scroll. A timer or a return to the window with nothing changed touches nothing.

## 8. Slices

| | Slice | Files |
| --- | --- | --- |
| D1a | The readers, the five operations, `view` in the dataset schema and `check`, the file route, the contract text | `tuldok_project/inside.py` (and helpers beside it), `operations.py`, `service.py`, `schemas/dataset.schema.json`, `check.py`, `app.py`, `docs/contracts/project-folder.md`, `tests/test_tuldok_project_inside.py`, and the tests that count the project-folder operations |
| D1b | The page | `static/project-workspace/inside.js`, `tabs.js`, `adapter.js`, `base.css`, `app.py` (the asset list), `tests/browser_project_workspace_inside.cjs` |

## 9. Tests

**D1a, `tests/test_tuldok_project_inside.py`.** Every fixture is written by the test with the standard library (arrays with `struct`, sound with `wave`, a PNG with `zlib`), into a product made the way the existing tests make one.

- Records from a list, from each form of `view`, and from files; paging, the kind and split filters and counts; a bad line reported and skipped.
- Each kind's `content`, compared with values the test computed itself. For arrays: every supported type, both byte orders, both orders of storage, a slice on each pair of axes of a four-dimensional array, subsampling, non-finite values; stored, compressed and nested members; `.npy` versions 1 and 2.
- Each refusal: an object array, a complex array, an address with `..`, an absolute address, a symbolic link out of the product, a member over the bound (with the bound lowered for the test), a mesh over its bound, a run that is not finished.
- The file route: the media type and disposition of an image, a sound, an `.svg` and an `.html`; a range; refused without the right to inspect.
- The five operations are in the `project_folder` profile and absent from `catalog`, whose manifest digest is unchanged.

**D1b, `tests/browser_project_workspace_inside.cjs`**, on a fixture project whose product holds at least one record of every kind and more than 48 records in all, owner signed in, no GPU:

1. Data shows "Look inside" on that dataset and not on one without a product. The dataset opens to 48 tiles, the counts by kind are right, the pager reaches the rest, a kind filter narrows the grid.
2. Each kind's viewer shows its record: the text's content; the image decoded at its true size; a playable sound with the right length and a drawn waveform; a point cloud and a mesh whose canvases are not blank and change when dragged; an array whose value under the pointer equals the fixture's and whose slider moves the slice.
3. "Files" lists the tree, opens an archive and an array inside it.
4. With the dataset open and a record selected, a return to the window and one timer reading add and remove no node (the counting of `browser_project_workspace_still.cjs`).
5. Light and dark: no viewer is blank in either.
6. The existing workspace checks pass unchanged in what they assert.

With `--lab-root` nothing is asserted in this check (a fresh database has no products for the lab); the lab's own products are read by the reviewer through `tuldok_project/inside.py` directly, read only.

## 10. Out of scope

Annotating, importing, generating; thumbnails made on the server; video; glTF; a model's weights (phase 2 uses these operations); comparing predicted with native fields (phase 6).

## As built

### D1a, the readers and the operations

What differs from the text above, and what was found.

- **Seven kinds, not six.** `file` is a kind like the others in a record list and in `view.kind`.
- **The project is opened for a moment, like any read.** Section 6 says no operation here opens the project; finding the run and the dataset's `view` needs it. Each operation opens it as the other reads do (which imports files changed on disk), reads the run's state, directory and the definition's `view`, closes it, and only then reads files. It does not run the step that clears orphaned runs, which writes a row.
- **These reads do not hold the service's lock** (changed in review). The service answers one call at a time; as first built a large member being decompressed, or a large mesh being parsed, held up every other call, the page's own readings among them. The run is found under the lock and the files are read outside it. What `inside.py` keeps in memory has its own lock.
- **A damaged file is a refusal, never a failure** (found in review, by feeding the readers 22,000 corrupted files). Compressed data that does not decompress and a binary PLY that ends early raised errors of their own, which the app would have answered as an internal failure. Each of the six entry points now answers whatever a reader raises on bad bytes as `unsupported`, and logs it. A truncated or malformed `.npy` was coded `invalid`; it is `unsupported` too. `invalid` is kept for arguments.
- **A stored archive inside an archive is not decompressed.** Section 3 says an archive inside an archive is read into memory. Only a compressed one is; a stored one stays a part of the outer file's mapping. This is what makes the lab's 9.8 GB training view quick: its 783 inner `.npz` files are stored.
- **Tuldok reads zip archives with a parser of its own** (the central directory, zip64 included), because the standard library does not give a member's offset in the file without reading its local header through a file object.
- **Choices the text left open:** `problems` is a list of `{line, message}`; the one array of a plain `.npy` is named null; a one-dimensional array is drawn as one row; `characters` is null for a text over 16 MiB; a point cloud's `bounds` are those of the points returned; a malformed address is `invalid`, a missing file or a link out of the product `not-found`; `array` is required for an `.npz`; a summary's sampling takes every n-th value in the order stored.
- **Measured on the lab's largest product** (9.77 GB, 792 members), through the readers alone, no database: listing the archive 0.004 s; the arrays of one sample 0.004 s; a middle slice of its `features` 0.009 s; a summary of its 645,120 values 0.12 s. The disk's cache may have held the file.
- **Tests:** `tests/test_tuldok_project_inside.py`, 24; project suite 610; agent interface 43 (4 skipped, as before). The catalog profile's digest is unchanged.
- **Not verified:** a big-endian machine; a PLY whose lists are in an element other than its faces; a JPEG whose size is declared beyond its first megabyte; a product on a disk that is truly cold. A file of a finished run is read through `mmap`: if something truncated it while it was being read, the process would be killed. Tuldok never changes a finished run's output.

### D1b, the page

What differs from section 7, and why.

- **The opened state is `#data/inside:<reference>`, not `#data/<reference>`.** `#data/<reference>` already opens the dataset's drawer beside the cards, and the existing checks rely on it (`browser_project_workspace_actions.cjs` edits a dataset from that drawer; `browser_project_workspace_still.cjs` counts it). `inside:` is a prefix of the selection like `edit:` and `plan:`. The opened view has no drawer.
- **"Look inside" sits under the card**, in a `.ds-item` that wraps the card's button (a button cannot hold a button), and in the drawer above Edit; it is drawn only when the dataset has a product with a run. A dataset with several products offers them in a select in the opened view's head, not on the card.
- **What redraws what.** A person's selection (a click, or the left and right arrows) sets the tiles' `aria-pressed` in place and replaces only the viewer; it is not in the address. A page, a filter, the Files switch and a level of the tree draw the whole view again, built off the page and put in place (spec-w4 R8). The arrows cross to the next or previous page at the ends of one. While the next record is read the viewer keeps the one on screen for 250 ms, then says "Reading…" (it is not on screen yet). A reading that changed something draws the opened view again in place (spec-w4 R3): `tabs.js` passes the drawer's `_again` mark to `LabInside.open`.
- **Files is browsed a level at a time**, with a line of links back up (Product / bundles / training-view.zip / samples), not as an expanding tree; a directory, an archive and an `.npy` or `.npz` open in place, an array or a file opens in the viewer.
- **What opens from the tree.** Arrays are read by their place (`array_slice` and `array_summary` take a path); images and sounds by the file route. A text, a point cloud or a mesh is opened through `record` when its address is a record's id (in a product read from its files it is), because no operation reads those kinds by address. A text, point cloud or mesh inside an archive, or one not among the records of a `records.jsonl` or a view, says so instead of opening: the server has no read for it. Section 7's "any file … opens in the same viewers" is therefore true of arrays, images and sounds only; the server was not changed.
- **Tiles.** An image tile reads its record to use the `url` the operation gives (two requests a tile: the record, the bytes); an array tile reads its record (an `.npz` needs `show`, which `records` gives only from a list) and one `array_slice` of `most` 48. Tiles are filled by an `IntersectionObserver` on the main area, 48 at most a page. A tile's id is cut at its start when long, so the file's name shows; the whole id is its title and label.
- **The slice viewer is written in `inside.js`; catalog mode's `scientific-inspector.js` is not used.** That module is built around the catalog's field-sequence manifests (frames, fields named by the manifest, x, y and z axes, nested arrays of values) and writes its controls with `innerHTML`; an adapter would have had to make those manifests up from an `.npy` header. Here the slice is a heat map in a canvas, two axes chosen by selects when there are three or more, a slider for every other axis, the range, the value and full index under the pointer, and the summary's histogram on request.
- **The stacked-slice drawing** (the mockup's `drawVolume`) reads up to ten positions of the first axis not drawn, at `most` 24 each, coloured on one range across them, the slider's slice outlined. A one-dimensional array is drawn as a line, not as a single row of cells.
- **Point clouds and meshes** are drawn into an `ImageData` with a depth buffer (a mesh's triangles rasterised, flat shaded from a fixed light), z up; colours by height use the diverging ramp's two ends. Dragging turns, the wheel zooms, the arrow keys and + and − do the same on the focused canvas, "Reset view" puts it back. A frame is drawn on `requestAnimationFrame` only after one of these; canvases are drawn again when their box changes size or the theme changes, and at no other time.
- **Colours.** Five tokens were added to `base.css` in both themes, `--ramp-lo`, `--ramp-hi` (sequential), `--ramp-neg`, `--ramp-mid`, `--ramp-pos` (diverging about zero, used when a range has both signs).
- **The answers.** `adapter.js` has the five reads and the file route's address as `P.product`; their answers are kept like any other and forgotten when a reading finds a change. The slice drawn as a slider moves is asked for each time and not kept.
- **Files beyond section 8's list:** `static/project-workspace.html` gains the `<script>` of `inside.js` (without it the module never loads), and the check's product is written by `tests/project_inside_browser_fixture.py`, run as the fixture dataset's command.

What the check does not cover: the lab's products (with `--lab-root` it asserts nothing); a dataset with several products and its select; records from `records.jsonl` or a view, their problems shown, and the split filter (the fixture's product is read from its files and has no splits); a product with no records (the empty states are drawn, not exercised); Tab order and the focus ring, checked only by eye; turning a canvas by the keyboard; point clouds near 100,000 points and meshes near 60,000 triangles, whose drawing time was not measured; a theme changed while the view is open (the check reloads the page in each theme); the viewer's "Reading…" after 250 ms.

Found while running the check: twice in its first fifteen runs the press of Next landed on a tile instead. The main area had been scrolled to show the button, and its scroll was back at 0 when the press arrived. It did not recur in nine later runs traced for it (every `scrollTop` set to 0 and every `LabInside.open` logged), so what moved it is not known. The check now measures a target again when it is not the element under its point, and waits for the second page to be drawn rather than only for the page to settle. The cause was not found.

**Open defect, found again in review.** In twelve more runs of the check, one failed the same way: the press of Next, made right after the dataset opened, did not reach the button. The check's own record of it: the main area went from a scroll of 283 back to 0 with its content the same height (1,142 in a frame of 809), 681 ms after the page loaded, still on the first page. So the content was not shorter and nothing was clamped: something set the scroll, or moved the focus to an element at the top, in the first second after the dataset view is drawn. It is about one run in twelve on this machine. A person would see the view jump to its top once, just after opening a dataset, if they had already scrolled. It is not yet explained; it is being reproduced in a loop with every way of moving the scroll traced.
