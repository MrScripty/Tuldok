# Implementation spec: native, predicted and signed error side by side

This is phase 6, the last, of [the data tools plan](data-tools-plan.md). It builds on [spec-d1.md](spec-d1.md) (reading inside a product) and [spec-d2.md](spec-d2.md) (weights), and their rules apply: standard library only, nothing unpickled, nothing written, bounded reads, a damaged file refused and not a failure, reads outside the service lock. The page follows [spec-w4.md](spec-w4.md) and updates in place: nothing is rebuilt by a timer or a return to the window.

**Owner, 2026-11-18:** "complete and test phase 6."

**After this phase** the Analysis tab shows, for the chosen subject, the fields its run kept: the native (reference) field, the model's prediction and the signed error (predicted minus native), side by side as slices through the volume, with the error's figures over the whole field. Nothing runs a model or a solver; only kept files are read.

## 1. What a run kept

A product **keeps fields** when the top of its directory holds `field-index.json`. The earlier lab runs write it (83 of them, one case each); it is read as Tuldok's format from here on and written into `docs/contracts/project-folder.md`:

```json
[{"run_id": "…", "cases": [{"member_ordinal": 0,
   "predicted": {"name": "pressure-prediction.npy", "bytes": 32896, "sha256": "…"},
   "reference": {"name": "pressure-reference.npy",  "bytes": 32896, "sha256": "…"},
   "mask": null, "time_units": "not_applicable"}]}]
```

- A list of entries; each has `cases`; each case names a `predicted` and a `reference` file by `name`, a plain file name at the top of the same product (no `/`, no `..`). Every other key is optional and kept as given for display (`member_ordinal`, `time_units`, `bytes`); `sha256` is not checked (no hash maps, as the owner ruled), but `bytes` is compared with the file and a mismatch is shown, not refused.
- `mask`: null, or `{"name": …}` of a boolean or integer `.npy` of the same shape; true or non-zero is inside. Where there is a mask, figures are over the inside only and the outside is drawn blank.
- Both files are `.npy` of a numeric type, the same shape, one to four dimensions, at most 16,777,216 values each (`too-large` beyond). Otherwise the case is listed with the reason it cannot be compared and refused `unsupported` when asked for.
- **Which case it is.** When the product holds `probe.json` of format `probe_v1`, a case's `member_ordinal` is looked up in its `members` and the member's `frozen_reference.member_id` and `split` are shown (for the lab: `baseline--water-validation-0000-frame-15`, validation). Otherwise the case is named by its position.
- **The run's own figure.** When the product holds a JSON file whose `format` ends in `_diagnostic_v1` and has numeric fields ending in `relative_l2`, they are listed as "the run reported" beside Tuldok's figures, by field name. They are never used to compute anything.

## 2. Operations

Two reads, `inspect`, in `INSIDE_READS` like the others, in the `project_folder` profile and absent from `catalog` (whose digest is unchanged). Both take `run`.

| Operation | Arguments | Result |
| --- | --- | --- |
| `fields` | none besides `run` | `kept` (bool), `cases`: each with `entry`, `case` (positions), `name` (member id or "case N"), `split`, `predicted`, `reference`, `mask` (names), `shape`, `dtype`, `comparable`, `reason` (when not), `bytes_mismatch` (names, when any). `reported`: the run's own figures `{file, field, value}` |
| `field_compare` | `entry`, `case`, `axis` (default the last), `index` (positions on the other axes beyond the two drawn, default the middle), `mean_free` (bool, default false) | `shape`, `axes` (the two drawn), `axis`, `index`, `rows`, `columns`, `reference_f32`, `predicted_f32`, `error_f32` (base64, row by row; masked cells NaN), `range` (min and max over reference and predicted together, so both share one scale), `error_limit` (the largest absolute error of the slice, so the error scale is symmetric about zero), and `figures` over the whole field (not the slice): `count`, `nonfinite`, `max_abs_error`, `mean_error`, `rmse`, `relative_l2` (error norm over reference norm, null when that is zero), `mean_free_relative_l2` (the same with each field's mean removed first) |

- **The slice.** A 1-D field is one row. A 2-D field is drawn whole. A 3-D or 4-D field is drawn through the two axes other than `axis` (for 4-D, also fixing `index` on the remaining one); the position on `axis` is in `index`. Larger than 256 by 256: subsampled by a stride, as `array_slice` does.
- **`mean_free`** removes each field's mean (over the inside) before the slice's error is formed; the figures always include both `relative_l2` and `mean_free_relative_l2`. (Pressure is defined only up to a constant: the lab scores the mean-free figure.)
- Arithmetic in 64-bit floats with `math.fsum` and `math.sumprod`; non-finite values are counted and left out of figures.
- Reuse `inside_arrays` (`read_header`, `decode`, `gather`, `float32_base64`, the slicing) rather than writing a second `.npy` reader. A new module `tuldok_project/inside_fields.py`.

## 3. The page

In the Analysis tab, a section **Kept fields** below "Per case", for the chosen subject, when the subject's model has a current product that keeps fields (the products of a recipe are read as `weights.js` reads them). The section is absent, not empty, when nothing is kept; when the subject's model has a product that keeps none, one line says so.

- **Head:** the case (a select when there are several): its name, split and shape. The run it comes from, linked to Train.
- **Three panels side by side,** of equal size: Native, Predicted, Signed error (predicted − native). Native and Predicted share one sequential colour scale over `range`; the error uses a diverging scale symmetric about zero over `error_limit`. A colour bar under each with its ends in numbers. At narrow widths the panels stack.
- **Controls:** the axis cut across (x, y, z, named by position), a slider for the position on it (and for a 4-D field one more), and "Remove the mean". Moving the slider asks `field_compare` again, at most one request in flight, the last position wins; the panels are redrawn in place.
- **Hover** on any panel shows the cell's position and the three values in a tip.
- **Figures:** a small table of the whole-field figures, and beside it "the run reported" when there is one.
- Canvas 2D, no library, light and dark; reuse `inside.js`'s colour scales and canvas helpers where they fit. Opened state goes in the address like the rest of the tab (`anaCase`, `anaAxis`, `anaIndex`, `anaMeanFree`), so a reload restores it.

## 4. Slices

| | Slice | Files |
| --- | --- | --- |
| D6a | Format, the two operations, the contract text | `tuldok_project/inside_fields.py` (new), `inside.py` if a shared helper moves, `operations.py`, `service.py`, `docs/contracts/project-folder.md`, `tests/test_tuldok_project_fields.py` (new), and the tests that count the project-folder operations |
| D6b | The Kept fields section | `static/project-workspace/tabs.js` (the Analysis screen), a new `static/project-workspace/fields.js` if it keeps `tabs.js` smaller, `base.css`, `app.py` (the asset list), `tests/browser_project_workspace_fields.cjs` (new) |

## 5. Tests

**D6a, `tests/test_tuldok_project_fields.py`,** fixtures written by the test with the standard library (`.npy` by hand):

- `fields` on a product with no index (`kept` false), with one entry of two cases, with a `probe.json` (names and split), with a `*_diagnostic_v1` file (reported figures), with a case whose files differ in shape, whose file is missing, whose name has a `/` or `..`, whose type is not numeric, whose `bytes` differ from the file: each listed with its reason, the rest still listed; a damaged index refused `unsupported`.
- `field_compare` against arithmetic the test does itself: identical fields (all zeros, `relative_l2` 0), a known constant offset (`relative_l2` > 0, `mean_free_relative_l2` 0), a mask (outside NaN, figures over the inside), a non-finite value (counted, left out), a zero reference (null), each axis of a 3-D field and each slice equal to the matching `array_slice` of both files, a 1-D, a 2-D and a 4-D field, subsampling past 256, the size bound (lowered for the test).
- The two are in `project_folder` and absent from `catalog`; the catalog digest is unchanged.

**D6b, `tests/browser_project_workspace_fields.cjs`,** on a fixture with a benchmark whose subject's model has a product keeping a 3-D case (with `probe.json` and a diagnostic file) and another subject whose model keeps none:

1. Analysis on the first subject shows Kept fields with the case name, three panels and the figures equal to the fixture's arithmetic; the second subject shows no such section (or the one line).
2. The panels' pixels: Native and Predicted differ where the fixture differs; the error panel is the middle colour where they agree.
3. The slider and the axis select change the slice (a different image) with one request each and no rebuild of the rest of the tab (a marker element on the page survives).
4. "Remove the mean" changes the error panel on the constant-offset fixture to the middle colour.
5. Hover shows the three values of the cell.
6. Reload restores the case, axis, position and mean option. Nothing is redrawn on a return to the window or a timer reading.
7. Light and dark, 1440 and 390 wide, no sideways overflow, no script error.

**On the lab folder (acceptance, read only):** for one earlier model of the 150-pressure-fits benchmark, the case `baseline--water-validation-0000-frame-15` is shown; Tuldok's `mean_free_relative_l2` equals the run's reported `mean_free_same_request_pressure_relative_l2` to at least 6 significant figures (or the difference is explained).

## 6. Out of scope

Running a model or solver to make predictions; vector fields drawn as arrows; time series of fields; 3-D volume rendering; comparing two models' predictions with each other; any change to the lab's runs or files.

## As built

### D6a, the reader and the operations

What differs from the text above, and what was found.

- **`index` is one position per axis, as `array_slice` takes it**, not only the positions beyond the two drawn: the
  answer's `axes` and `index` have the form of an `array_slice` answer, so a slice can be checked against one, and
  the positions of the drawn axes are ignored. For a field of four axes the two drawn are the last two of the
  axes other than `axis` (the remaining one is fixed by `index`), as `array_tiles` chooses the axes it draws.
  `axis` is answered null for a field of one or two axes.
- **`range` and `error_limit` are of the slice** (the finite values inside the mask), as the text says for the
  error's limit; both are null when the slice has no such value. The answer also carries `entry`, `case`,
  `dtype`, `stride` and `mean_free`. `fields` also answers `more` (true past 10,000 cases) and gives each case
  `details`: the case's other keys as the index gives them (`member_ordinal`, `time_units`, the lab's hashes).
- **What "damaged" means for the index:** not JSON, not UTF-8, not a list, or an entry that is not an object with a
  list `cases` refuses both operations `unsupported`; an index over 4 MiB is `too-large`. A case that is not an
  object or names no predicted or reference file is listed with that reason, the others still listed.
- **A plain file name** also may not hold `\`, `!` (which would address an archive member) or a NUL, and must end
  `.npy`. Booleans are not "a numeric type" for the predicted and reference files (they are for a mask). A file
  shorter than its shape says is listed with that reason, as is a mask of another shape or type.
- **A case's name and split from `probe.json`:** the member is found by its `ordinal` (by its position when it
  has none); the split is `frozen_reference.split`, else the member's `split`, else the probe's. A case is
  otherwise named `case N` by its position (0 first), `entry E case N` past the first entry.
- **"The run reported"** reads only the top-level numeric fields of each `*_diagnostic_v1` JSON file at the top
  of the product (at most 4 MiB a file, 500 files); a file is parsed only when its bytes hold `_diagnostic_v1`.
- **Mean-free figures** take each field's mean over the inside cells whose two values are finite, and form
  `(p − mean p) − (r − mean r)`; null when the reference is constant there. A figure that overflows is null.
- **Figures are kept** (16 cases, least recently used dropped) while the files' size, time and inode are unchanged,
  so a slider moved reads only the slice; spec-d2's reordering of a Fortran-ordered array moved into
  `inside_arrays` (`to_c_order`, `c_order_values`), used by `inside_weights` and `inside_fields` alike.
- **The acceptance on the lab folder** (read only, through `inside_fields` directly, no database), run
  `7a700731ead945aebefdb7798536c30f` of project `0dcc3af1…`: `fields` lists one case,
  `baseline--water-validation-0000-frame-15`, validation, 16 × 16 × 16 float64, comparable, and the run's
  `mean_free_same_request_pressure_relative_l2` 0.0028656154967496624; `field_compare` answers
  `mean_free_relative_l2` 0.00286561549674967, a difference of 7.4e-18 (relative 2.6e-15), so equal to 15
  significant figures (`relative_l2` 0.0027748834045040957, `rmse` 0.0711, 4,096 cells, no non-finite value).
  `fields` took 0.003 s and `field_compare` 0.002 s. This is the one run named for the check; the other 82 runs
  of the benchmark were not read.
- **Tests:** `tests/test_tuldok_project_fields.py`, 16; the two operations in `test_tuldok_project_service.py`'s
  read test, and its count of the table's rows (59 to 61). Project suite 735 OK on a disposable PostgreSQL; agent
  interface 43 OK (4 skipped). The catalog profile's digest is unchanged. Browser checks:
  `browser_project_workspace_fields.cjs` 8 PASS (run twice), and unchanged `_weights` (7 PASS), `_inside` (8 PASS)
  and `browser_project_workspace.cjs` (24 PASS).
- **Not verified:** a field near the bound of 16,777,216 values (its time and memory: the figures read both whole
  fields into 64-bit arrays, about 270 MB, once per case); a big-endian machine; an index written by the lab with
  a mask (none of the lab's runs has one).

### D6b, the section

What differs from section 3, and why.

- **The address.** The Analysis tab's settings were not in the address before this phase (only the benchmark and
  the compare set were). `app.js` now keeps `anaBench`, `anaSubject`, `anaMetric` and the four of this section in
  the query, so that a reload restores the subject as well as the case; `act.keepUI` sets one without drawing the
  tab again (the slider's moves). Choosing another benchmark or subject forgets the case, axis and position.
- **Where the reads live.** `tabs.js` reads the section's data with the rest of the tab (`LabFields.read`, so the
  tab is put in place in one step) and builds it with the tab (`LabFields.section`); `fields.js` draws the
  person's moves in place. `adapter.js` gained the two reads (`P.product.fields`, `fieldCompare`); it is not in
  section 4's list. The section's case select names cases of every current product of the model that keeps
  fields (with its subject when there are several).
- **The slider, the axis and "Remove the mean"** each ask `field_compare` at once (one request per change; a
  change while one is in flight waits and only the latest is asked), and draw the three canvases again; the axis
  also draws the controls again in place (its slider changes). Another case builds the section again and puts it
  in place in the same element. The panels' aria-labels and the line under them say what is drawn.
- **The scales.** `inside.js`'s `ramp` is diverging whenever a range has both signs, so the panels use two scales
  of their own on the same tokens: sequential `--ramp-lo` to `--ramp-hi` over `range` for Native and Predicted, and
  diverging `--ramp-neg` / `--ramp-mid` / `--ramp-pos` over ±`error_limit` (all `--ramp-mid` when the limit is 0).
  The canvas helpers (`fit`, `heat`, `contain`, `paints`, `token`, `floats`) are `inside.js`'s.
- **The figures and "the run reported"** are two small tables side by side (wrapping); a bytes mismatch is one
  warning line under the head. The run is a link to `#train/run:<id>`.
- **Axes are named x, y, z for a field of three**, `axis 0` … `axis 3` for four.
- **The check's fixture** (`tests/project_fields_browser_fixture.py`) makes the reference a multiple of 1/512 whose
  mean is exactly zero, so that the constant-offset case's mean-free error is exactly zero: with rounding noise of
  1e-16 the diverging scale, scaled to the slice's largest error, would colour the noise fully. The page has no
  tolerance for that; a real field whose error is pure rounding would be drawn at full colour, with `error_limit`
  under the bar saying how small it is.
- **Files beyond section 4's list:** `static/project-workspace.html` (the `<script>` of `fields.js`), `app.js`
  (the address), `adapter.js` (the reads), and the fixture above.

What the check does not cover: a mask (drawn blank outside, tested in D6a only); a field of one, two or four axes
in the page (the second slider of a four-axis field is drawn but not exercised); a case that cannot be compared
shown with its reason; several products of one model in the select; a refusal of `field_compare` shown in the
section; the slider dragged quickly (several moves while a request is in flight); a theme changed while the
section is open (the check loads each theme); Tab order and the focus ring, by eye in the screenshots only; the
lab's own products in the page.
