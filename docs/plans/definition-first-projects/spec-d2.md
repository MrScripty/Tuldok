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
