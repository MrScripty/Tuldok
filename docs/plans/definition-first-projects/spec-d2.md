# Implementation spec: a model's weights, layer by layer

This is phase 2 of [the data tools plan](data-tools-plan.md). It builds on [spec-d1.md](spec-d1.md) (reading inside a product) and its rules apply: standard library only, nothing unpickled, nothing written, bounded reads, a damaged file refused and not a failure. The page follows [spec-w4.md](spec-w4.md).

**Owner, 2026-11-13:** "It would be great if tuldok also had a layer visulization tool so we can visualize a models weights."

**After this phase** a model's drawer shows the weights its run produced: every layer with its shape and size, how its values are distributed, its kernels or matrix as images, and how much each layer changed from the weights it started from or from the model it derives from. Nothing runs the model: there are no activations and no drawn architecture, since nothing records one.

## 1. What a run's weights are

- The outputs of the run whose role is `weights`, as the product records them.
- When it records none: the files at the top of the product whose extension is `.npz`, `.safetensors`, `.pt`, `.pth`, `.ckpt`, `.bin` or `.onnx` and whose name contains `weight` or `model`, not beginning `initial-`.
- **Readable:** `.npz` and `.safetensors`. Anything else is listed with the reason it is not opened: a PyTorch file is a pickle, and Tuldok never opens a pickle (decision 4 of the plan: the training code writes `.npz` or `.safetensors` beside it).
- **The weights a run started from:** the file beside a weights file with the same name prefixed `initial-` (the earlier lab runs keep `initial-weights.npz`).

## 2. `.safetensors`

Read like an `.npz`: its tensors are its arrays, by name, in `inside`, `record`, `array_slice` and `array_summary`. The extension joins kind `array`.

The file is 8 bytes (the header's length, little-endian), the header (JSON: each tensor's `dtype`, `shape` and `data_offsets`, and `__metadata__`), then the data. Bounds: a header of at most 16 MiB; offsets inside the file, not overlapping the header. Types read: `F16 F32 F64 I8 I16 I32 I64 U8 U16 U32 U64 BOOL`, little-endian, row-major. A tensor of another type (`BF16` and the rest) is listed with its type and refused `unsupported` when read. Data on disk is read through `mmap` as an `.npy` is.

## 3. Operations

Three reads, `inspect`, in the table like the others. Every one takes `run` (a finished run, as in spec-d1).

| Operation | Arguments | Result |
| --- | --- | --- |
| `weights` | none besides `run` | `files`: each weights file with `path`, `output` (the output's name, or null when found by name), `bytes`, `readable`, `reason` (a sentence, when not readable), `starts_from` (the address of its `initial-` file, or null), and when readable `parameters` (a count) and `layers` |
| `weights_compare` | `path`, `other_run`, `other_path` | `tensors`: for each array in both with the same shape, `array`, `parameters`, `norm`, `other_norm`, `difference_norm`, `relative_change` (the difference's norm over the other's; null when that is zero), `cosine` (null when either norm is zero), `largest_change`. `total`: the same over all of them together. `only_here`, `only_there` (names), `reshaped` (name and both shapes) |
| `array_tiles` | `path`, `array`, `across` (the axis counted over), `axes` (the two drawn in each tile, default the last two), `index` (positions on the remaining axes, default the middle), `first` (default 0), `most` (tiles at most, default 16, at most 64) | `shape`, `dtype`, `across`, `axes`, `index`, `first`, `tiles`, `rows`, `columns`, `values_f32` (base64: tile by tile, each row by row), `min`, `max`, `nonfinite` |

**Layers.** A tensor's layer is its name without its last dotted part: `encoders.0.layers.0.weight` and `encoders.0.layers.0.bias` are the tensors `weight` and `bias` of the layer `encoders.0.layers.0`. A name with no dot is its own layer. Layers keep the order of the file. Each layer has `name`, `parameters` and `tensors` (each: `array`, `name`, `shape`, `dtype`, `parameters`).

**Norms** are Euclidean, over 64-bit floats, with `math.sumprod` and `math.fsum`. Non-finite values make the quantities that include them null, and `nonfinite` counts them.

**Bounds.** A tile is at most 64 by 64 (subsampled by a stride beyond, as a slice is); `weights_compare` reads at most 32,000,000 values in all and is refused `too-large` beyond, saying how many there are; `weights` lists at most 10,000 tensors per file.

`other_run` may be the same run (its `initial-` file) or any other finished run of the project.

## 4. The page

In a model's drawer, a block **Weights**, after "Runs and product", when the model has a current product with a weights file.

- **Head:** the file (a select when there are several), its size and parameter count. A file that is not readable shows its reason and nothing else.
- **Compare with:** nothing (the default), "the weights it started from" when the run kept them, "the model it derives from" for each model the map draws a line from that has readable weights. Choosing one asks `weights_compare` once.
- **The layers,** as a table: name, shape of its first tensor, parameters, a small drawing of how its values are distributed (asked for when the row comes on screen, 32 bins), and when comparing a bar of how much it changed with the figure. Sorting by name (file order), size or change.
- **A tensor opened** (a click on its layer, then on the tensor when there are several): range, mean, spread, zeros; the distribution, larger; and its values as images. Two dimensions: one image. Three or more: tiles across the first axis with the last two drawn, the other axes on sliders, and controls to change which axis is counted across and to page through the tiles. Colours diverge around zero. When comparing: this, the other, or their difference.
- A layer that exists on one side only, or changed shape, is marked so.

The drawings reuse the viewers of spec-d1's `inside.js` where they fit. No library, canvas 2D, light and dark, and nothing is redrawn by a timer or a return to the window.

## 5. Slices

| | Slice | Files |
| --- | --- | --- |
| D2a | `.safetensors`, the three operations, the contract text | `tuldok_project/inside_arrays.py`, `inside.py`, a new `tuldok_project/inside_weights.py`, `operations.py`, `service.py`, `docs/contracts/project-folder.md`, `tests/test_tuldok_project_weights.py`, and the tests that count the project-folder operations |
| D2b | The Weights block | `static/project-workspace/weights.js`, `screens.js`, `adapter.js`, `base.css`, `app.py` (the asset list), `tests/browser_project_workspace_weights.cjs` |

D2a is built on a branch of its own beside spec-d1's page; D2b after both.

## 6. Tests

**D2a, `tests/test_tuldok_project_weights.py`,** fixtures written by the test with the standard library:

- A `.safetensors` of several types read through `inside`, `array_slice` and `array_summary`, equal to the same values in an `.npz`; a `BF16` tensor listed and refused; a header longer than the file, offsets outside the file and overlapping the header, each refused `unsupported`.
- `weights` on a run with a declared weights output, on one found by name, on one with an `initial-` file, on one with `model.pt` (not readable, with its reason, and the file is never opened); layers grouped and ordered; parameter counts.
- `weights_compare` against arithmetic the test does itself: identical files (zero change, cosine 1), a known difference, a tensor missing on each side, a changed shape, a zero tensor (nulls), a non-finite value, the bound (lowered for the test).
- `array_tiles` on a five-dimensional kernel: each tile equals the matching `array_slice`; paging with `first`; subsampling.
- The three are in the `project_folder` profile and absent from `catalog`, whose digest is unchanged.

**D2b, `tests/browser_project_workspace_weights.cjs`,** on a fixture with a parent model and a model derived from it, each with a small `weights.npz` (and the derived one with `initial-weights.npz`), and a third whose only weights file is `model.pt`:

1. The derived model's drawer shows Weights with the right parameter count and layers in file order; the third model's shows the reason.
2. A layer's distribution is drawn when its row comes on screen and not before.
3. Opening a tensor shows its statistics (equal to the fixture's) and its tiles; the slider and the paging change them.
4. Comparing with the starting weights and with the parent shows the fixture's change per layer; "difference" draws a different image from "this".
5. Nothing is added or removed on a return to the window or a timer reading.
6. Light and dark.

## 7. Out of scope

Activations; a drawing of the architecture; reading `.pt`, `.ckpt`, ONNX or GGUF; comparing more than two files; any change to how a recipe declares its outputs.

## As built

### D2a, the readers and the operations

What differs from the text above, and what was found.

- **`weights_compare` also answers `unread`:** tensors of the same shape that one side holds in a type Tuldok does not read (`BF16`, say), with both types. They are left out of the comparison. Each tensor row and `total` also carry `nonfinite`.
- **`array_tiles` also answers `stride`,** as a slice does. `across` defaults to the first axis not drawn; an array of fewer than three axes is refused `invalid`.
- **`weights`** also answers `tensors` (how many the file holds; `parameters` counts those listed, at most 10,000). A declared weights output that is a directory gives the weights files at its top. A declared output that is missing is listed as not readable with `bytes` null. A damaged file is listed as not readable with its reason; the call is not refused.
- **`weights_compare`:** all four arguments are required; a file of more than 10,000 tensors is refused `too-large`; the bound of 32,000,000 values counts both files together.
- **Layer order:** an `.npz` follows its directory of members, a `.safetensors` its header.
- **In `inside.py`** the guard of the entry points, the list of what a damaged file raises and the function that finds an array are no longer private (`reading`, `DAMAGED`, `array_at`), since the weights module uses them. A product now carries the outputs its run recorded, so that no reader opens the database.
- **A summary never answers infinity** (found in review, feeding the readers 20,000 corrupted `.safetensors` files). 64-bit values near the largest a float holds overflowed the mean and the deviation of `array_summary`, which spec-d1 built: the answer held `Infinity`, which is not JSON, and a page could not have read it. A mean or deviation that overflows is null, and the histogram's positions are computed on halved values when the range itself overflows. `weights_compare` already answered null in that case.
- **Measured** on an earlier lab model (26 tensors in 14 layers, 163,068 parameters, 660 KB), through the readers alone: `weights` 0.002 s; `weights_compare` against its `initial-weights.npz` 0.024 s (total relative change 0.85, cosine 0.70; four layers started at zero, so their relative change is null); `array_tiles` of its largest tensor 0.0003 s.
- **Tests:** `tests/test_tuldok_project_weights.py`, 16; `tests/test_tuldok_project_inside.py`, 25; project suite 626 before the review's change, and the two files above after it; agent interface 43 (4 skipped). The catalog profile's digest is unchanged.
- **Not verified:** a `.safetensors` written by the library itself (the tests write their own); comparing a Fortran-ordered array with a C-ordered one is right but reorders value by value, which would be slow on a large tensor; a big-endian machine.

### D2b, the page

What differs from section 4, and why.

- **Where the block sits and when it shows.** `screens.js` puts an empty, hidden block between "Runs and product" and "Uses"; `weights.js` (`LabWeights.block`) reads the model's current products and their `weights`, and shows the block only when one of them lists a weights file. A model without one (no product, or no weights file in it) has no Weights block at all. Read again for the model on screen (spec-w4 R3), the block is one of the drawer's reads: it resolves only once complete (the comparison, the opened tensor and its images read), so the drawer is put in place in one step.
- **Several products.** A model with several current products (subjects) lists the weights files of all of them in the one select, each labelled with its subject.
- **"The model it derives from"** is the model's `derived_from` (the one derivation line the map draws to it); its current products' readable weights files are each a choice, labelled with the model's short name and title (and the file's path when it has several).
- **A layer's change** is not in the answer of `weights_compare`, which is per tensor. The page computes it over the layer's tensors that were compared: the square root of the summed squared `difference_norm` over that of the summed squared `other_norm`. For a layer of one tensor it is that tensor's `relative_change`. "From zero" when the other's norm is zero; "not finite" when a tensor's norms are null; "not compared" when none of its tensors was (only here, reshaped, not read), with the marks of those tensors under its name. The bar is scaled to the largest change among the layers. Sorting by change puts the layers that started at zero first (an unbounded relative change), then the largest, then those not compared.
- **The table in a narrow drawer:** a fixed layout of four columns (layer, parameters, the small distribution, the change); the shape of a layer's first tensor (and how many tensors it has) is a second line under its name rather than a column, and the marks of a comparison a third.
- **A tensor opened** is drawn in a row of its own under its layer's row, across the drawer's width, rather than below the table, so that it stays next to the layer it belongs to whatever the sort. Its first tensor is opened with it; a layer of several tensors offers them as a switch. The statistics and the larger distribution (64 bins) are of this file's tensor in every mode, and say so when comparing; the images follow the mode.
- **One axis** (a bias) is drawn as one strip of cells by `array_slice`; section 4 names only two and three or more. A scalar shows its statistics only.
- **Tiles.** `array_tiles` with 16 tiles a page; "Tiles across" chooses any axis (the two drawn are then the last two others, as the operation's default) and the sliders are for the axes neither drawn nor counted across. Every tile is its own canvas with its position under it and its own text alternative, in a grid that wraps (at least 72 px a tile). All the tiles of a page share one range, symmetric about zero; the difference is computed in the page from the two answers (the same arguments give the same tiles, rows, columns and stride on both sides) and drawn on its own symmetric range. A legend under the images shows the ramp from −m to +m and says the range.
- **What is kept.** `weights` and `weights_compare` are read through the adapter's kept answers (forgotten when a reading finds a change, so asked again then: one `weights_compare` per choice and per drawing after a change). A product does not change once its run finished, so the distributions (`array_summary`) and the tiles and slices are also kept in `weights.js` for the page's life (the tiles and slices at most 64, the least recently used dropped): a block drawn again draws a distribution already read at once and never asks for it again, and a slider moved back draws without asking. The slice and tile reads themselves are not kept by the adapter (asked fresh), as spec-d1 does for its slider.
- **What redraws what.** The person's choices (file, comparison, sort, a layer, a tensor, a mode) build the block again off the page and put it in place with its focus (by `data-key`) and the drawer's scroll kept; an axis or a page builds the images again the same way; a slider moves only the tiles (read again after 90 ms, the latest wins), so a drag is never interrupted. While something reads the block or the images carry `aria-busy`; "Reading…" is never shown, because the block is on screen.
- **`inside.js` exports its drawing parts** as `LabInside.drawing` (`floats`, `token`, `ramp`, `paints`, `fit`, `heat`, `contain`, `ordinal`); its own behaviour is unchanged. The diverging ramp is always asked for on a range symmetric about zero, so a tensor of one sign is still coloured from zero.
- **Files beyond section 5's list:** `static/project-workspace.html` gains the `<script>` of `weights.js`, `inside.js` its export, and the check's weights are written by `tests/project_weights_browser_fixture.py` (standard library), adopted by the check with the command line's `adopt` (recipes of earlier work, so no build and no GPU).
- **The check** also covers, beyond section 6: the parent offers nothing to compare with; a model without a product has no block; sorting by change; "the other" drawn on the initial weights' range; across another axis (4 tiles, sliders for the other two); and, in step 5, a change elsewhere (a definition added to the folder) drawing the drawer again in place with the comparison, the opened layer, the mode, the tiles and the drawer's scroll kept, no "Reading…" and no distribution asked again.

What the check does not cover: a model with several weights files or several products (the select); a `.safetensors` file in the page (D2a reads it like an `.npz`); the refusals (`too-large`, `unsupported`, `not-found`) of `weights_compare`, `array_summary` and `array_tiles` shown in the block (drawn with the page's refusal, not exercised); a `weights` call refused for a product; tensors `unread` or not finite; a file of more than 10,000 tensors ("the first … are listed"); a stride above 1 (tiles larger than 64 by 64); a theme changed while the drawer is open (the check loads the page in each theme); Tab order and the focus ring, checked by eye in the screenshots only; the lab's real weights (no `--lab-root`).
