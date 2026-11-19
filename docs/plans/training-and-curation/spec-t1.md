# Implementation spec: autologging and live training views

This is phase 1 of [the training and curation plan](plan.md), and it follows "The rule every phase follows": a file contract, a reader and a view in Tuldok, and a thin optional helper, `tuldok_log`. The rules of the data tools apply to the reader ([spec-d1.md](../definition-first-projects/spec-d1.md), [spec-d2.md](../definition-first-projects/spec-d2.md), [spec-d6.md](../definition-first-projects/spec-d6.md)): standard library only, nothing unpickled, nothing of the project's code run inside Tuldok's server, nothing written, bounded reads, a damaged line or file refused or reported and never a failure, reads outside the service lock. The page follows [spec-w4.md](../definition-first-projects/spec-w4.md): it updates in place, and nothing is rebuilt by a timer or a return to the window.

**Owner, 2026-11-19:** "Tuldok needs live training views … We should also have … autologging." And on how Tuldok is built: projects write their own Python scripts; Tuldok supplies the contracts, the orchestration and the views.

**After this phase** a project's training script writes a few plain files into its run's output directory while it trains, by hand or through `tuldok_log` (three lines with `autolog`). On the Train tab, the drawer of a run shows its curves while it runs, growing in place every two seconds, with other runs overlaid, smoothing and a log scale; the distributions of each layer's weights and gradients over the steps as small heat strips; and the samples the script kept, as a strip. Nothing trains a real model; nothing reads the lab's runs.

## 1. Rules

- **The script writes, Tuldok reads.** Tuldok never runs the project's code, never imports it, never opens a pickle. `tuldok_log` is imported by the project's script in the project's environment, never by Tuldok's server.
- **A running run is readable.** The training files are read from a run's output directory whatever its state, as soon as the run has a directory: queued with none yet answers "nothing logged"; running, succeeded, adopted, failed, cancelled or timed out are read alike (a failed run's curves are often what one most wants to see). The other reads inside a product (spec-d1) still need a finished run.
- **Files are appended while they are read.** A reader takes only complete lines (ending in a newline); a partial last line is left for the next read. A file that became shorter, or another file under the same name, is read again from its start.
- **Bounded.** Every read has a bound on bytes, lines, series and points (section 4), and long series are reduced on the server before they are sent.
- **Cheap when nothing changed.** What has been read of a file is kept in memory with its offset, so reading again reads only what was appended since.

## 2. The contract: `training/` in a run's output directory

Everything is under `training/` at the top of the run's output (`{output}/training/`). Every file is optional; a run with no `training/` has nothing logged. JSON is UTF-8, one object per line (JSON Lines), and Python's `NaN`, `Infinity` and `-Infinity` are read as non-finite.

### 2.1 `training/metrics.jsonl`

One object per log:

```json
{"step": 120, "time": 14.2, "epoch": 3, "loss": 0.0213, "lr": 0.001, "grad_norm": 0.84, "val/loss": 0.031}
```

- `step`: required, an integer ≥ 0. Steps normally increase; they need not (a resumed run may log a step again), and the page draws points in the order of the file.
- `time`: required, seconds since the run started (a finite number ≥ 0).
- `epoch`: optional, a number.
- **Every other key whose value is a number is a scalar series** named by the key (1 to 200 characters). `null` or a non-finite number is a gap in that series, counted as `nonfinite`. A key absent from a line is no point of that series (a validation loss logged every hundred steps is a series of its own with fewer points).
- Keys whose value is not a number (a string, an object, a boolean) are kept as the line has them and listed by name as `other_keys`; they are not series.
- A line that is not such an object (not JSON, no integer `step`, no `time`) is counted and its line number reported; the rest are read.

### 2.2 `training/histograms.jsonl`

One object per tensor per log:

```json
{"step": 100, "time": 12.1, "name": "encoder.0.weight", "kind": "weights", "edges": [-0.5, -0.4, …, 0.5], "counts": [3, 11, …, 2]}
```

- `step` and `time` as above; `name` (1 to 1,000 characters): the tensor; `kind`: `weights` or `gradients`.
- `edges`: n + 1 finite numbers, not decreasing; `counts`: n numbers ≥ 0 (counts of values in each bin; the last bin includes its upper edge). 1 ≤ n ≤ 1,024.
- Optional `nonfinite`: values left out because they were not finite.

### 2.3 `training/samples/` and `training/samples.jsonl`

What the model made every N steps, so one can watch it learn: an image (PNG) or an array (`.npy`, the forms spec-d1 reads). Each file is written whole under `training/samples/` (written to a temporary name and renamed, by `tuldok_log`), named by its step and name: `samples/000000120-prediction.png`. Then one line is appended to `training/samples.jsonl`:

```json
{"step": 120, "time": 14.2, "name": "prediction", "path": "samples/000000120-prediction.png"}
```

`path` is relative to `training/`, a plain address under `samples/` (no `..`, no `!`). The kind follows the extension: `.png` (also `.jpg`, `.jpeg`, `.webp`) is an image; `.npy` is an array. A line naming a file that is missing is listed with that problem.

### 2.4 `training/checkpoints.jsonl` and how the checkpoint index relates

The project-folder format has no checkpoint index today: a run's final weights are its declared outputs (role `weights`, or found by name, spec-d2), and the earlier CLI's `checkpoint` role names one output. A script that keeps checkpoints during the run may list them here, one line each:

```json
{"step": 1000, "time": 120.5, "path": "checkpoints/step-1000.safetensors", "loss": 0.012}
```

`path` is relative to the run's output directory. The other numeric keys are figures of that checkpoint. Tuldok lists them and marks their steps on the curves; it does not open them here (the Weights block of the model's drawer reads the run's final weights as before).

### 2.5 `training/training.json`

Optional, written once by `tuldok_log` at the start: `{"format": "tuldok_training_v1", "started_at": "<ISO 8601 UTC>", "helper": "tuldok_log 1"}`. A reader shows `started_at`; nothing depends on it.

### 2.6 The earlier lab runs

The lab's earlier runs keep their history in `history.json`, in the lab's own form. Converting it into `training/metrics.jsonl` is a **lab script**, not Tuldok code, and it is deferred: this phase writes nothing into the lab repository or into any run's product. Until it exists, those runs show "nothing logged".

## 3. `tuldok_log`

A package at the top of the Tuldok repository, `tuldok_log/`, installed into a project's environment like any dependency (or put on its path). Standard library only; PyTorch is imported only inside `autolog`, and the helpers that take a model or a tensor use the object's own methods (`named_parameters`, `detach`, `histc`) without importing anything.

```python
from tuldok_log import Logger, autolog

log = Logger(output)                     # writes into <output>/training/
log.log(step, loss=0.21, lr=1e-3)        # one metrics line; epoch=... optional
log.log_histograms(step, model)          # weights and gradients of every parameter; or tensors={"name": values}
log.log_sample(step, "prediction", png_bytes_or_array)
log.checkpoint(step, "checkpoints/step-1000.safetensors", loss=0.012)

track = autolog(model, optimizer, directory=output, every=10, loss=criterion)
```

- `Logger(directory)`: the run's output directory; creates `training/` and writes `training.json` when it is absent. Its clock starts when it is made. Every line is written with one `write` call on a file opened for appending, so a reader sees whole lines or none (a partial line at worst while the write lands). `close()` and a context manager.
- `log(step, *, epoch=None, **scalars)`: values are converted with `float()`; a value that is not finite is written as `null`.
- `log_histograms(step, model=None, *, tensors=None, kinds=('weights', 'gradients'), bins=32, most=64)`: for a model, every parameter (the first `most`) and its gradient when it has one; for `tensors`, a mapping of name to values (a nested list, an object with `tolist()`, or a tensor). Histograms are computed by the tensor's own `histc` when it has one, else in Python.
- `log_sample(step, name, value)`: `bytes` beginning with the PNG signature are written as a `.png`; an object with `__array_interface__` or `dtype`/`shape`/`tobytes` (a NumPy array), a tensor (`detach().cpu()`), or a nested list of numbers is written as an `.npy` of its numeric type (float32 for a list). Written to a temporary name, renamed, then indexed.
- `autolog(model, optimizer, *, directory=None, logger=None, every=50, histograms_every=None, loss=None, bins=32)`: registers the optimizer's step hooks (PyTorch 2.0 or later). Each optimizer step counts one step. Every `every` steps it writes one metrics line with the learning rate (`lr`, or `lr/<group>` for several parameter groups), the gradient norm over all parameters before the step (`grad_norm`) and, when it knows it, the loss: the mean of the losses seen since the last line. It knows the loss when `loss` is the loss module (a forward hook reads its output) or when the script calls `track.note(loss=…)` (any named scalars). Every `histograms_every` steps (default: `every`) it writes the histograms of the weights and of the gradients. `track.close()` removes the hooks. The script names none of these.

## 4. Operations

Five reads, `inspect`, in the `project_folder` profile and absent from `catalog` (whose digest is unchanged). Each takes `run`; a run with no directory answers as having nothing logged (`training`) or `not-found` (the others).

| Operation | Arguments | Result |
| --- | --- | --- |
| `training` | none besides `run` | `run` (`id`, `state`, `active`), `present` (whether `training/` exists), `started_at`, `series` (each: `name`, `points`, `nonfinite`, `first_step`, `last_step`, `last`, `min`, `max`), `lines` (complete metrics lines read), `last_step`, `last_time`, `other_keys`, `histograms` (each: `name`, `kind`, `rows`, `first_step`, `last_step`), `histogram_lines`, `samples` (each name with `count` and `last_step`), `sample_lines`, `checkpoints` (the last 200: `step`, `time`, `path`, figures), `problems` (the first 20: `file`, `line`, `problem`), `bad_lines`, `truncated` |
| `training_series` | `series`: up to 16 of `{name, size, since}`; `most` (default 1,000, at most 4,000) | `series`: each `name`, `points`, `nonfinite`, `size`, `first`, `buckets`; `lines` |
| `training_histograms` | `name`, `kind`, `most` (rows, default 120, at most 500), `bins` (default 48, at most 128) | `name`, `kind`, `rows` (each `step`, `time`), `stride`, `low`, `high`, `bins`, `counts` (row by row, re-binned), `nonfinite` |
| `training_samples` | `name`, `offset`, `limit` (at most 200) | `samples` (each `index`, `step`, `time`, `name`, `path`, `kind`, `bytes`, `problem`; an image's `url`), `total` (of that name, or all) |
| `training_sample` | `index` | `sample` (as above) and `content`: for an image `width`, `height`, `url`; for an array a slice as `array_slice` answers it (the last two axes, at most 128 by 128) |

**Reduced series.** A series of `n` points is sent in buckets of `size` consecutive points, `size` the smallest power of two for which there are at most `most` buckets (1 while `n ≤ most`). A bucket is `[first_step, last_step, last_time, mean, min, max]` over its finite values (`mean`, `min`, `max` null when it has none). The bucket boundaries depend only on `size`, so the page keeps what it has: it sends the `size` it holds and `since`, the bucket it wants from (its count less one, since the last may have grown); when the server's `size` is the same it answers from `since` (`first`), otherwise from 0, and the page replaces what it held. A live run thus sends a few buckets a reading.

**Histograms over steps.** The rows are the tensor's logs, evenly chosen when there are more than `most` (the first and the last always among them). Every row is re-binned onto `bins` equal bins over the lowest and highest edge of the chosen rows, a bin's count shared out by overlap (as if spread evenly inside it); `counts` are the shares, not rounded.

**Images of a running run.** `GET /api/project/file` serves a file under `training/` of any run that has a directory, as it serves a finished product's files (same checks: inside the output directory, no `..`).

## 5. Bounds

| | Bound | Beyond it |
| --- | --- | --- |
| A line of `metrics.jsonl`, `samples.jsonl`, `checkpoints.jsonl` | 64 KiB | counted as a bad line |
| A line of `histograms.jsonl` | 256 KiB | counted as a bad line |
| Lines of `metrics.jsonl` kept | 1,000,000 | later lines not read, `truncated` |
| Series | 200 | later names not kept, reported once |
| Lines of `histograms.jsonl` indexed | 1,000,000 | `truncated` |
| Tensor and kind pairs | 2,000 | later pairs not kept, reported once |
| Bins of one histogram line | 1,024 | a bad line |
| Lines of `samples.jsonl` and of `checkpoints.jsonl` | 100,000 and 10,000 | `truncated` |
| Files kept in memory | 16, least recently used dropped | read again from the start when asked again |

A histogram line is kept as its offset and length only; its bins are read again when a strip is drawn.

## 6. The page

In the run's drawer on the Train tab, a block **Training**, after "Latest progress", when the run has a directory. A run with nothing logged shows one line that says so, and how a script logs (`tuldok_log`), and nothing else.

- **Curves.** A chart (canvas 2D, no library) of the chosen series against the step (or the time since the run started). A chooser of series (the run's series, `loss` first when there is one; up to four shown). Controls: **Smoothing** (a slider, 0 to 0.99, exponential moving average over the drawn buckets; the raw line stays faint behind), **Log scale** (values ≤ 0 left out, said under the chart), **Step / Time**. When a series is reduced, the band between each bucket's min and max is shaded. Checkpoints are ticks on the step axis. Hover shows the step, the time and the value of each line at that step.
- **Overlay.** "Compare with" lists the other runs of the project (newest first, those of the same model first); each run added is drawn in its own colour, with a legend of run, model and state; a run is removed from its chip. Up to four runs.
- **Histograms.** Under the curves, for each tensor (weights, and gradients when logged; a switch between the two), a heat strip: steps across, bins down, each column's counts as shares of its own total so a narrowing distribution shows. The first eight tensors are drawn; "Show all" draws the rest. Each strip is read when it comes on screen.
- **Samples.** A strip of the last twelve samples of the chosen name (a select when there are several), newest last, with the step under each; an array is drawn as an image with `inside.js`'s colour ramp.
- **Live, in place.** While the run is active, every reading of the page (every two seconds, spec-w4 R7) asks `training` once; when its `lines` grew, `training_series` for the shown series from where the page is (appending buckets); when `histogram_lines` grew, the strips on screen are read again; when `sample_lines` grew, the new samples. The canvases are drawn again and new samples appended; **the block is never rebuilt** by a reading, and a reading that found nothing new touches no element. A run's answers are kept by the page while it is open, so the drawer drawn again (the run ended) puts the block back without "Reading…" and without reading the series again.
- **The address** keeps the overlay and the settings: `trWith` (run ids), `trSeries`, `trSmooth`, `trLog`, `trX`.
- Light and dark from the page's tokens; at 390 wide the controls wrap and the chart fills the drawer.

## 7. Slices

| | Slice | Files |
| --- | --- | --- |
| T1a | The contract text, the reader, the five operations, the file route | `docs/contracts/project-folder.md`, `tuldok_project/training.py` (new), `operations.py`, `service.py`, `tests/test_tuldok_project_training.py` (new), and the tests that count the project-folder operations |
| T1b | `tuldok_log` | `tuldok_log/__init__.py` (new), `tests/test_tuldok_log.py` (new) |
| T1c | The Training block | `static/project-workspace/training.js` (new), `tabs.js` (the run's drawer), `adapter.js`, `app.js` (the address, the reading), `base.css`, `app.py` and `static/project-workspace.html` (the asset), `tests/browser_project_workspace_training.cjs` (new) |

## 8. Tests

**T1a, `tests/test_tuldok_project_training.py`,** files written by the test:

- `training` on a run with no `training/`; on a metrics file with several series, a gap (`null`, `NaN`), a key that is not a number, a bad line, a line too long; on a file whose last line is partial (not counted), then completed by an append (counted); on a file replaced by a shorter one (read again).
- `training_series` against the test's arithmetic: raw points while `n ≤ most`; buckets of a power of two beyond, with mean, min and max per bucket; `since` with the same size answers only the later buckets; with a different size from 0; the bound on lines (lowered for the test).
- `training_histograms`: two rows with different edges re-binned onto one grid, the totals kept; row choice past `most`, first and last kept; a damaged line counted.
- `training_samples` and `training_sample`: a PNG (its size), an `.npy` (its slice), a missing file, a path with `..`.
- A running run (state `running`) is read; a queued run without directory answers nothing logged; the file route serves `training/` of a running run and not its other files.
- The five are in `project_folder` and absent from `catalog`; the catalog digest is unchanged.

**T1b, `tests/test_tuldok_log.py`:** `Logger` writes lines the reader reads back (series, gaps as `null`, histograms from lists, samples PNG and `.npy` and the index); every line is whole; `autolog` with PyTorch on the CPU (a tiny model, ten steps, `every=2`): metrics lines with `loss`, `lr`, `grad_norm`; weights and gradients histograms for every parameter; the hooks removed by `close()`. Skipped when PyTorch is not importable; run with the lab's interpreter, which has it (read only, nothing installed).

**T1c, `tests/browser_project_workspace_training.cjs`,** in a headless browser, the owner signed in, no GPU: a fixture with two finished runs of a small stand-in script that logs through `tuldok_log` (built before the server starts), and a third run of the same script for about ten seconds, asked for and run while the page watches:

1. The running run's drawer shows Training; its curve grows across readings (more points drawn, the last step larger) while a marker set on the block survives and no node of the block is added or removed by a reading.
2. The two finished runs overlaid: three lines and a legend of three.
3. Smoothing, log scale and Step / Time change the drawing (another image), the block the same element.
4. Histograms drawn (non-blank strips, one per tensor shown) and samples drawn (images loaded, steps under them).
5. Nothing is touched by a return to the window with the finished run open.
6. Light and dark, 1440 and 390 wide: no sideways overflow, no script error, no failed request.

## 9. Out of scope

A lab converter of `history.json` (a lab script, deferred); TensorBoard event files or any other format; logging from inside Tuldok's server; text or audio samples; comparing histograms of two runs; alerts on a diverging run; the Analysis or Benchmarks tabs; any change to how runs are started or to the lab's runs.

## As built

What differs from the text above, and what was found while building it.

### T1a, the reader and the operations

- **`tuldok_project/training.py`** holds the reader; `service.py` gains `TRAINING_READS` beside `INSIDE_READS`. The
  run is found under the service's lock (`_training_run`, any state, its `directory`) and its files read outside
  it. A run of any state with an output directory is read; one without (a queued run) answers `training` with
  `present` false and the other four `not-found`.
- **`training_histograms` also answers `totals`** (each row's count before re-binning), which the page uses to shade
  each column by its share. It is in the contract text.
- **Damaged lines.** A line that is not JSON, not an object, has no integer `step` or finite `time` (metrics), or
  fails the histogram, sample or checkpoint checks is counted in `bad_lines`; past the bound on series or tensor
  pairs the dropped name is reported once in `problems` but not counted as a bad line. A line longer than the bound
  is skipped up to its newline even when that arrives in a later read. A number too large for a float
  (`1e400` as an integer) is a non-finite value, a gap.
- **What is kept per file:** the metrics as arrays (step, time, epoch, and per series its line positions and
  values) with each series' least, greatest and last finite value kept as lines arrive, so `training` costs a
  `stat` and the appended bytes, not a pass over the series; a histogram line as its offset and length; samples and
  checkpoints as small dicts. 64 file states (four a run) are kept, least recently used dropped.
- **A symlink** under `training/` that leads outside the output directory is treated as absent.
- **`GET /api/project/file`** serves a `training/` address (no `!`) of a run in any state with a directory through
  `service.product_file`; `app.py` is unchanged.
- **Tests:** `tests/test_tuldok_project_training.py`, 18 (15 without a database, 3 with); the read test and the
  operation count (61 to 66) in `test_tuldok_project_service.py`. The catalog's digest is unchanged
  (`ad5cc7ac…`, 110 operations), checked in the new file and by the agent interface tests.

### T1b, `tuldok_log`

- As section 3, with `Logger.elapsed()` public and `log_sample` returning the path it wrote. `autolog` logs the
  first optimizer step as well as every `every`-th, so a curve starts at step 1. Gradient histograms are written in
  the optimizer's pre-step hook (gradients may be zeroed after the step), weight histograms after it; both carry the
  step number after the step.
- **The loss module's forward hook counts every call of the module**, so a script that also calls the same loss
  module for validation mixes those values into `loss`. The docstring says to pass the module or call `note()`;
  a separate validation loss module (or `note(val_loss=…)`) avoids it. Not otherwise guarded.
- `note()` scalars other than the loss are written with the next logged line and then forgotten; a note made on a
  step that is not logged waits for the next one.
- **Tests:** `tests/test_tuldok_log.py`, 8: 6 with the standard library (read back through the reader), and 2 of
  `autolog` that need PyTorch, skipped in Tuldok's environment. Run with the lab's interpreter
  (`<lab>/.venv/bin/python -m unittest tests/test_tuldok_log.py`, PyTorch 2.8.0+cpu, `PYTHONDONTWRITEBYTECODE=1`,
  read only, nothing installed): 8 OK on the CPU. The grad norm is checked against the test's own norm taken in a
  pre-step hook of its own; the loss against the mean of the losses it saw.

### T1c, the block

- **Where.** The block is in the run's drawer, after "Latest progress", read with the drawer (`LabTraining.read`
  in `runDrawer`'s load) and built with it (`LabTraining.block`). A failure to read it shows one line in the block,
  not a failed drawer. `tabs.js`'s `S.tick` calls `LabTraining.tick()` first on every reading.
- **One chart a series** rather than one chart with a series chooser: series of different scales (loss and learning
  rate) are never drawn on one axis. Up to four series and four runs. Runs are told apart by colour and a legend
  (swatch, model's short name, start of the run id, state), and the hover tip names each run with its value, step
  and time; there are no direct labels at the ends of the lines (the drawer is narrow). The four colours are new
  tokens `--run-1` … `--run-4` in `base.css`, light and dark, checked with the dataviz palette validator (lightness,
  chroma, colour-blind separation, contrast: all pass in both modes).
- **The overlay chooser** lists the project's other runs that are not queued (the run's own model's first), up to
  fifty; runs that logged nothing draw no line but stay in the legend.
- **Smoothing on a log scale** smooths the logarithms, so a falling loss is not pulled up by its early values. A
  value of 0 or less is left out on the log scale and a line under the chart says so; the same line says when a
  series is reduced (each point a mean of N, the band their range) and when it is smoothed.
- **Histograms**: one strip a tensor for the kind chosen (weights or gradients), 32 bins and at most 120 steps, each
  column shaded by the square root of its share of its column's total. The common range over all steps means a
  distribution that narrows a lot is drawn in a few bins at the end (visible in the check's gradients); a per-column
  range was not built. A strip is read when it comes on screen, and again when histograms were added since.
- **Live updates in place.** A reading asks `training` for each active run in view; new lines ask
  `training_series` from the last bucket held, and the charts are redrawn in their canvases; new histogram lines
  read again the strips already read; new samples are appended to the strip (the oldest removed past twelve). A
  name that was not there before (a validation loss first logged at step 10, the first samples, new tensors) adds
  its chooser button or draws its part again (histograms, samples); only a run that had logged nothing before draws
  the block's content anew. Texts (where the run is, a chart's caption) are set as the data of their text node, so
  a reading adds or removes no node. When the run ends, the page draws the drawer again (as before this phase),
  and the block is built again from what is held, without "Reading…" and without reading the series again.
- **The page reads every two seconds only while it knows a build runs** (spec-w4 R1): a build asked for elsewhere
  is seen on the next reading, up to fifteen seconds later, and only then is the block read live. The check makes
  that reading at once by a return to the window. Opening a run's drawer does not by itself start fast reading.
- **The address** keeps `trWith`, `trSeries`, `trSmooth`, `trLog`, `trX` (`app.js`'s `ADDRESSED`). The chosen
  sample name, weights or gradients and "Show all" are kept by the page for the run while it lives, not in the
  address.
- **The check** (`tests/browser_project_workspace_training.cjs`, with the stand-in `tests/project_training_stand_in.py`,
  plain Python, logging through `tuldok_log` put on the run's `PYTHONPATH` by the recipe's `env`): 7 PASS, on
  the last two runs (once before its commit, once at the end; the earlier runs failed on the check's own timing and
  on the block's first way of adding names, both fixed). In step 4 the live run (50 steps, 0.25 s each) grew 10 → 18 →
  27 → 35 points across readings with the block, its chart and its strips the same elements and no node added or
  removed outside the samples strip; the marker is set once the run has logged every name it will (from its tenth
  step), since a first name is drawn by adding its control.
- **Files beyond section 7's list:** `tests/project_training_stand_in.py`; `adapter.js` was not changed (the block
  calls `P.call` and keeps its own answers by run, since a running run's answers must not be kept by the adapter).

### Runs at the end

Disposable PostgreSQL under `/tmp/claude-1000/t1`, `TULDOK_PROJECT_HOME` and `TULDOK_SETTINGS` there:

- `PYTHONPATH=tests .venv/bin/python -m unittest discover -s tests -p 'test_tuldok_project_*.py'`: 753 OK (735
  before, plus the 18 of `test_tuldok_project_training`).
- `PYTHONPATH=tests .venv/bin/python -m unittest test_agent_api test_agent_negotiation test_agent_http`: 43 OK, 4
  skipped.
- `tests/test_tuldok_log.py`: 8 OK with the lab's interpreter (PyTorch on the CPU); 6 OK, 2 skipped with Tuldok's.
- Browser: `browser_project_workspace_training.cjs` 7 PASS; unchanged `browser_project_workspace.cjs` 24 PASS,
  `browser_project_workspace_fields.cjs` 8 PASS, `browser_project_workspace_still.cjs` 6 PASS (the run drawer
  changed).

### Not verified

A real training run (nothing was trained; `autolog` was exercised on a tiny model for ten steps on the CPU); the
lab's earlier runs (the converter of `history.json` is deferred and nothing was written into the lab); a metrics
file near the bound of 1,000,000 lines (its memory, about 16 bytes a line and 16 a value, and the first read's
time); bucket sizes above 1 in the page (the check's series are shorter than 800 points; the reader's buckets are
unit-tested); `training_histograms` past `most` in the page; a sample `.npy` of three or more axes in the page;
several parameter groups or the overlay of a run that is itself running; the hover tip in the check (drawn, not
asserted); keyboard order and focus rings beyond the screenshots; a theme changed while the drawer is open (each
theme is loaded); the coding-standards guidance (the Standards Engine answered that its guidance is awaiting
publication, so none was read).
