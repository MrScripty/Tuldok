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
