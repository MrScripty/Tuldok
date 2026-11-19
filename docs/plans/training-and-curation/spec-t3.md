# Implementation spec: comparing chosen models deeply

This is phase 3 of [the training and curation plan](plan.md). It follows that plan's rule (Tuldok reads what a project's scripts wrote; nothing of the project's code runs in Tuldok), and it adds no file contract: everything here is read from what Tuldok already holds, the definitions, the per-case values of [the values files](../../contracts/project-folder.md#values-files) and the fields a run kept ([spec-d6.md](../definition-first-projects/spec-d6.md)). The readers follow spec-d1 and spec-d6: standard library only, nothing written, bounded work, an unusable input listed with its reason rather than failing the whole answer. The page follows [spec-w4.md](../definition-first-projects/spec-w4.md): nothing is rebuilt by a timer or a return to the window, and a person's own moves are drawn in place.

**Owner, 2026-11-19:** "Tuldok already kinda has comparison view for models in the ancestory tree/list, but it would be great if it could compare selected models deeper like also showing output results next to eachother. Im not sure how the GUI would work for that." And: "Parallel coordinates sound very usful for Tuldok."

**After this phase** the models a person chose (two to four) open a **Compare** tab: one column per model, rows of who each is and what differs between their recipes, their metrics on every benchmark that measures them with a 95 % interval where this machine holds per-case values, where each sits on the frontier, and then their outputs on one case they all kept, the native field, each prediction and each signed error, moved together by one slice control. The Benchmarks tab gains **parallel coordinates** over the benchmark's metrics and the recipe settings that vary between its subjects (a range dragged on an axis keeps the subjects inside it, in the table and in the other charts), and **intervals**: whiskers on the ranking charts and in the table, and a mark on the frontier where two neighbours are not told apart by their per-case values.

## 1. What differs between recipes

A recipe's definition is a JSON document. To compare two to four of them, and to put their settings on axes, each document is **flattened** to its leaves:

- A leaf is `null`, a boolean, a number, a string, or an empty object or list (shown as `{}` and `[]`). An object's keys are joined with `.`; a list's items are `[0]`, `[1]`, …; a key that is not a plain name (holding `.`, `[`, `]`, `"` or a space, or empty) is written `["key"]`. So the lab's learning rate is `run.settings.captures[0].experiment.training.learning_rate`.
- The keys of who a model is and how it is described are not settings: `format`, `kind`, `title`, `description`, `card`, `labels`, `earlier_work` and `compared_with` are left out. `group`, `change` and `derived_from` are compared on their own rows (kinds `group`, `change`, `parent`); the leaves under `run.inputs` are of kind `data`; every other leaf is of kind `setting`.
- **Bounds:** at most 5,000 leaves a document and 32 levels deep (past either, the rest is left out and the document marked `truncated`); a string is compared whole but shown to 200 characters.
- A settings file a recipe names (`run.settings_file`) is not opened: only what the definition holds is compared (doubt: a recipe whose settings live in its file shows none here).

Two leaves are **the same** when both models have the path and the values are equal as JSON values (`1` and `1.0` are equal; `true` and `1` are not). A path **differs** when any model lacks it or holds another value. The comparison lists every differing path, `group`, `change` and `parent` first, then `data`, then the settings in path order, at most 400 rows (`more` says how many past them), and counts the paths that are the same.

## 2. Intervals from per-case values

A summary row of a benchmark (count, mean, median, p10, p90, min, max) made from per-case values (`origin` `values`) can carry an interval; one read from a results file cannot, as the cases are not on this machine.

- **The cases** of a subject and metric are its held values that are numbers, over every group (the cases the ungrouped summary row is made from), each keyed by its case and group.
- **The resampling** (a percentile bootstrap): the values sorted ascending; a fresh `random.Random(20261119)`; 2,000 resamples, each `rng.choices(values, k=n)` sorted; the six statistics of each resample computed as `results.summarise` computes them (the mean with `math.fsum`, the percentiles by its linear interpolation); the interval of each statistic is the 2.5th and 97.5th percentiles of its 2,000 values, by linear interpolation at `q × 1999`. A subject with fewer than 2 values has no interval. The same seed for every interval makes an answer the same on every reading and lets a test do the arithmetic itself.
- **The difference between two subjects** on a metric and a statistic: when they share at least 2 case keys, *paired*: the shared keys in sorted order, each resample `rng.choices(range(m), k=m)`, the statistic of each side over the drawn keys and their difference (first minus second); otherwise *independent*: each resample draws the first's values then the second's. The interval is taken as above. The difference is **significant** when its interval does not hold zero.
- **The frontier.** For a tradeoff chart that is not grouped, its frontier points (chart_data's, in its order by x) are taken in pairs of neighbours; a pair is compared on both of the chart's metrics with the chart's statistic. A pair is **separated** when both differences are significant; otherwise each of its points is **not separated from** the other. A pair where either side lacks values on either metric is left unknown (null). Grouped tradeoff charts are listed with no pairs (doubt: the cases of one group value would do; not built).
- **Cost.** 2,000 resamples of 128 values take about 25 ms in CPython; a benchmark of 150 subjects, five metrics and 128 cases each takes about 20 s. The intervals of a benchmark are therefore computed outside the service's lock and kept (8 benchmarks, least recently used dropped) while its held values are the same; the page draws the tab first and the intervals when they arrive (section 5.2).

## 3. Parallel coordinates

For one benchmark and a statistic, every subject is a line through:

- **the metric axes,** one per metric of the benchmark: the subject's statistic from its summary row (null when it has none). `positive` says whether every value is above zero, so the page may offer a logarithmic scale.
- **the setting axes:** the subjects' recipes flattened as in section 1 (the identity rows `group` and `change` and the `data` leaves included as settings may vary there too). A path is a candidate when at least two subjects have it and their values are not all the same. It is a **number** axis when every value is a number (not a boolean), and a **category** axis when its values are texts, booleans or a mix, with 2 to 12 distinct values; categories are ordered numbers first (by value), then `false` and `true`, then texts, then the rest, and a subject's value on the axis is the position of its category. A path with more than 12 distinct non-numeric values is left out.
- **Which settings first.** The candidates are ordered by how strongly they go with the first metric that has at least three values: the absolute Spearman rank correlation (ties given their mean rank) over the subjects that have both, null under three or when either side is constant; then by how many subjects have the path, then by path. At most 48 are answered (`left_out` counts the others).

The page shows the metrics and the first six settings by default, at most twelve axes at once, with a chooser for the rest.

## 4. Operations

Three reads, `inspect`, in the `project_folder` profile and absent from `catalog` (whose digest is unchanged). Nothing new is written to the contract file: these read the definitions and results it already describes.

| Operation | Arguments | Result |
| --- | --- | --- |
| `model_compare` | `recipes` (2 to 4 distinct recipe references), `statistic` (one of the six, default `median`) | `statistic`, `resamples`, `level`, `seed`; `models`: per recipe `reference`, `title`, `group`, `change`, `derived_from`, `truncated`; `differs`: each `kind`, `path`, `values` (one per model, JSON as held, null where absent), `present` (booleans); `same` (count of paths the same), `more`; `benchmarks`: each benchmark with a subject made from one of the recipes: `benchmark`, `title`, `metrics` (`id`, `title`, `units`, `better`), `models` (one per recipe: null, or its `subject`, `title`, `per_case`, and `values` by metric: `value`, `count`, `low`, `high`), `frontiers` (per tradeoff chart: `chart`, `title`, `statistic`, `metric`, `metric_x`, `grouped`, `models`: one per recipe, null when not drawn, else `on` (on the frontier), `x`, `value`, `not_separated_from` (subject names)) |
| `benchmark_axes` | `benchmark`, `statistic` (default `median`) | `benchmark`, `statistic`, `metrics` (`id`, `title`, `units`, `better`, `positive`, `low`, `high`), `settings` (`path`, `kind` `number` or `category`, `categories`, `low`, `high`, `count`, `distinct`, `association`), `left_out`, `subjects` (`subject`, `title`, `recipe`, `metrics` by id, `settings` by path) |
| `intervals` | `benchmark` | `benchmark`, `resamples`, `level`, `seed`, `intervals`: per subject and metric with values, `subject`, `metric`, `count`, and for each statistic `[low, high]` (or null); `frontiers`: per tradeoff chart `chart`, `title`, `statistic`, `metric`, `metric_x`, `grouped`, `pairs` (`subjects` [a, b], `metric` and `metric_x` each `low`, `high`, `paired`, `count`, `significant`, or null; `separated`), `not_separated` (subject names) |

`model_compare` refuses `not-found` for a recipe that is not defined, `invalid` for repeated ones; the values of `model_compare` are those of `intervals` for the subjects of its recipes (the frontier pairs only those that touch one of them). The three are reads of the database and the definitions: their answer is computed from what the project holds, under the service's lock for the reading and, for `intervals` and `model_compare`, outside it for the resampling.

## 5. The page

### 5.1 The Compare tab

The compare set (the page's `cmp`, kept in the address as before) may now hold **four** models; choosing another benchmark no longer empties it, since it is no longer only of one benchmark. It is filled from three places: the boxes of the Benchmarks table, **Compare** in a model's drawer on the Benchmarks tab, and **Compare** in a model's drawer on the **Map** (new). Each drawer with Compare also has **Open Compare** once the set holds two.

**Why a tab, not a view inside Benchmarks or a drawer:** the set is the page's, not one benchmark's; one column a model needs the full width (the drawer is 420 px); and a tab has an address (`#compare`), so a comparison can be reloaded and shared. The tab is after Benchmarks.

The tab, for the models of the set that are recipes on the map (a benchmark subject made from no recipe is named and left out):

- **Head:** the set as chips with × and Clear, the statistic (shared with Benchmarks), and, under two models, a sentence on how to choose them.
- **The table,** one column per model (its name opens its drawer, with Compare in it): *Who* (group, kind of change, derives from, state, trained); *What differs* (section 1: each differing path with each model's value; absent written as "—"; the count of the same); then per benchmark, its metrics, each cell the statistic, its interval as `low – high` and the number of cases, the best of a row marked; and for each tradeoff chart, the frontier row: "on the frontier", "on the frontier, not separated from …", "off the frontier", or "—". The table scrolls sideways in its own box when narrow.
- **Outputs.** The cases the models' runs kept (spec-d6 `fields` of every current product of each model), matched by name (the probe's member id, or "case N"); a case is offered when at least two models kept it, comparable and of the same shape (a model of another shape is said so in its column). A select chooses it (the most shared first). One control for all columns: the axis cut across, the position (and the fourth axis), "Remove the mean". Then a grid, a column per model and three rows, Native, Predicted and Signed error; Native and Predicted of every column on one sequential scale (over every column's `range`), the errors on one diverging scale (±the largest `error_limit`), a colour bar for each row with its ends; under each column the whole-field figures (relative L2, mean-free relative L2, RMSE). Hover shows the cell's position and the three values of that column. A move asks `field_compare` of every column at once (one request each, at most one round in flight, the latest wins) and draws the canvases again in place. The case, axis, position and mean option are kept in the address (`cmpCase`, `cmpAxis`, `cmpIndex`, `cmpMeanFree`).
- Read with the tab and put in place in one step (tabs.js's `paint`); the outputs' first slices are read with it.

### 5.2 Benchmarks: parallel coordinates and intervals

- **Settings and metrics** (parallel coordinates), after the charts, when the benchmark has two subjects or more: an SVG of one vertical axis per chosen axis, one line per subject (in the kind of change's colour, as the charts' points), each axis named with its ends (a category axis with its categories). Under it, the chooser: the metric axes and the 48 settings (each with its association), as toggles, at most twelve on. Each axis has buttons to move it left and right, and a metric axis whose values are all positive a "log" toggle. **Brushing:** a range dragged on an axis keeps the lines whose value on it lies inside (a line with no value there is out); ranges on several axes all apply; a range is cleared by a click on the axis without a drag, and all by "Clear ranges". The lines out of range are faint; the subjects table hides their rows and says how many are shown; the charts above draw their points faint. All of this is set in place (no reading, no rebuild of the tab); the order, the axes on, the log scales and the ranges are the tab's settings, kept when the tab is drawn again.
- **Intervals:** read after the tab is put in place (section 2's cost); when they arrive the tab is drawn again in place with them (its scroll, focus and brushing kept). The ranking charts get a whisker from `low` to `high` of the chart's statistic for each subject with an interval; the table's metric cells a second line `low – high` of the tab's statistic; the tradeoff chart a dashed ring round each frontier point not separated from a neighbour, a tip line naming that neighbour, and a line of the legend. A line under the charts says how the intervals are made (2,000 resamples, seed, percentile 95 %).

## 6. Slices

| | Slice | Files |
| --- | --- | --- |
| T3a | Flattening, the differences, the intervals, the axes; the three operations | `tuldok_project/comparing.py` (new), `operations.py`, `service.py`, `tests/test_tuldok_project_comparing.py` (new), the count of the table's rows in `tests/test_tuldok_project_service.py` and its read test |
| T3b | The Compare tab | `static/project-workspace/compare.js` (new), `compare.css` (new), `fields.js` (its helpers shared), `tabs.js` (the limit of four, Compare in drawers), `screens.js` (Compare on the Map's drawer), `app.js` (the tab, the limit, the address), `adapter.js` (a kept answer peeked), `static/project-workspace.html`, `app.py` (the asset list) |
| T3c | Parallel coordinates and intervals on Benchmarks | `static/project-workspace/parallel.js` (new), `charts.js` (whiskers, the ring), `tabs.js`, `compare.css`; `tests/browser_project_workspace_compare.cjs` (new) and its fixture `tests/project_compare_browser_fixture.py` (new) |

## 7. Tests

**T3a, `tests/test_tuldok_project_comparing.py`:** flattening (nested objects and lists, quoted keys, empty containers, the identity keys left out, the bounds lowered for the test, `1` equal to `1.0` and not to `true`); the differences of three documents (each kind, an absent path, the order, `more`); the bootstrap against the test's own arithmetic (its own seeded `random.Random`, choices and percentiles: every statistic's interval equal), fewer than 2 values (none), the paired and the independent difference, significance; the axes on documents the test writes (a number axis, a category axis with its positions, a constant path left out, a path of 13 texts left out, the association against a Spearman correlation the test computes, the order, `left_out` with the bound lowered); the three operations on a project with per-case values imported (`model_compare` of three recipes: differences, values with intervals equal to the module's, frontier rows; `intervals` with frontier pairs; `benchmark_axes`); refusals (an unknown recipe, a repeated one, an unknown benchmark); the three in `project_folder` and not in `catalog`, the digest unchanged.

**T3b and T3c, `tests/browser_project_workspace_compare.cjs`,** on the minimal fixture with three recipes of earlier work whose adopted products keep fields of one shared case (and one more case kept by two of them), a benchmark whose subjects they are with per-case values imported for each and a tradeoff and a ranking chart, and recipes whose settings vary (a number, a category):

1. The Map drawer's Compare adds models; Open Compare shows the tab with three columns, the differing settings (and not the same ones), the metrics with intervals equal to `intervals`' answer, and the frontier rows.
2. Outputs: the shared case chosen, nine panels drawn; one slider move asks `field_compare` three times and redraws every canvas in place (the rest of the tab the same elements); the Native row of every column on one scale (the same colour where the fields are equal).
3. Benchmarks: parallel coordinates with the metric and setting axes; a range dragged on the metric axis hides the table rows outside it and dims the charts' points, with no request; reordering and the log toggle redraw in place; clearing shows every row again.
4. Intervals: the ranking chart has whiskers, the table has `low – high` lines, the tradeoff chart marks the frontier points the answer says are not separated.
5. Light and dark, 1440 and 390 wide: no sideways overflow of the page's main area outside the tables' own scrolling boxes, no blank canvas, no script error, no failed request.

**Regressions:** the project suite, the agent interface tests, `browser_project_workspace.cjs`, `_fields.cjs` and `_structure.cjs`.

**On the lab folder (acceptance, read only):** parallel coordinates over the 150-pressure-fits benchmark's 150 subjects (definitions and the results file only) filter to the best errors and show their settings; three earlier pressure models with kept fields compared on one case (the owner, on his database).

## 8. Out of scope

Running anything to make a prediction; comparing more than four models; intervals for grouped rows (by horizon, say) and for results read from a file; multiple-comparison corrections; settings read from a recipe's settings file; brushing on the Map; a hyperparameter search's own view (phase 7 reuses this).

## As built

What differs from the text above, and what was found. Built on `feat/t3-compare` beside phase 1, which owns the Train tab and `tuldok_log/`; neither is touched here. Edits to shared files are small: `app.js` (the tab, the bound of four, the address), `tabs.js` (Compare in drawers, intervals, the parallel-coordinates hook), `screens.js` (Compare in the Map's drawer), `adapter.js` (`peek`), `charts.js` (whiskers, ring), `operations.py`, `service.py`, the service test's count (64 to 67). `base.css` and `docs/contracts/project-folder.md` are not changed: the styles are in a new `compare.css`, and no file contract is added.

### T3a, the reader and the operations

- **The setting axes are ordered by the association weighed by its coverage**: `|ρ| × (subjects with both) / (subjects with a value of the first metric)`, then by count and path. Section 3 said the plain `|ρ|`. On the lab's 150 pressure fits the plain order led with list positions of `run.sources` that six subjects hold, at |ρ| 0.88 to 0.95 by chance. For the same reason **`run.command` and `run.sources` are of a sixth kind, `code`**: listed in what differs (last), never an axis. `association` in the answer is still the plain ρ.
- **Categories are ordered** numbers first by value, then `false`, `true`, then texts, then the rest (written into section 3 before the build: ordering by JSON text put `"wide"` before `16` and `8` after `40`).
- **`model_compare` resamples only for its statistic.** Its intervals equal those of `intervals` for that statistic (the draws are the same sequence; the browser check compares them).
- **The intervals of a benchmark are kept** by comparing what was gathered with what was kept (no hash), 8 benchmarks.
- **Tests:** `tests/test_tuldok_project_comparing.py`, 13 (three with the database, through `Service`): flattening and its bounds, the differences, every statistic's interval and the paired and independent differences against the test's own seeded resampling and percentiles, the frontier pairs (separated, not separated, unknown, grouped, `touching`), the axes (number, category with mixed values, constant and 13-text paths left out, ρ against the test's own Spearman, the weighed order, code never an axis, `left_out`), the three operations on the minimal fixture with its values imported, refusals, and the catalog digest unchanged. In the minimal fixture's tradeoff chart only one point is on the frontier, so its pairs are tested on hand-made chart data.

### T3b and T3c, the page

- **The tab is `#compare`, after Benchmarks.** Its drawer is the model's drawer with Compare. Choosing another benchmark keeps the set (it used to empty it).
- **The intervals arrive after the tab:** the Benchmarks tab is put in place without them; when `intervals` answers, the tab is drawn again in place (`act.setUI('ivFor', …)`, the whole tab built off the page with its scroll, focus and ranges kept); afterwards the kept answer is peeked (`P.peek`) and the tab draws them at once. A line under the charts says how they are made.
- **The frontier mark** is a dashed ring round each point (not a dashed segment of the line).
- **Brushing is by pointer only**; the axes' move, log and remove buttons and the chooser are buttons and checkboxes, but a range cannot be set from the keyboard (doubt; a pair of number fields per axis would do). The lines are SVG paths with a `<title>`, not focusable.
- **The outputs** take the shape and the first slice from the first model that kept the chosen case; a model that kept it in another shape says so in its cells. The colour bars sit with each row's title; under each column, relative L2, mean-free relative L2, RMSE and the largest error over the whole field.
- **Files beyond section 6's list:** `compare.css`, and the fixture writes recipes, a benchmark, two charts, values files and three products.

### Runs (a disposable PostgreSQL, no GPU)

Project suite 768 OK (755 before, and the 13 new); agent interface 43 OK (4 skipped); `browser_project_workspace_compare.cjs` 6 PASS (twice); unchanged `_fields.cjs` 8 PASS, `_structure.cjs` 8 PASS, `browser_project_workspace.cjs` 24 PASS. The page did not overflow sideways at 390 px on the Compare and Benchmarks tabs in the check.

### On the lab folder (read only, no database)

`benchmark_axes`' computation over `150-pressure-fits-complete-gpu-requests-128-consumed-cases`, from the folder's definitions and its results file only (a script giving `comparing.benchmark_axes` what `gather_axes` would read), in 0.03 s: 150 subjects, all 150 recipes found, 5 metric axes, 48 settings offered (39 more left out). The first settings: `run.resources.wall_hours`, `run.settings.training.learning_rate` (144 subjects, ρ 0.72 with the equation residual), `run.settings.resources.wall_seconds`, `run.settings.training.schedule[0].learning_rate`, the seeds, `group`, the datasets. Keeping the best tenth by mean-free pressure error (≤ 1.05e-4: 16 subjects) shows `wall_hours` 0.5 for all 16, and for the 10 of them that have it learning rate 1e-5, schedule learning rate 1e-6, `wall_seconds` 1800; 6 have no `run.settings.training` (their settings are elsewhere in their recipes). Not run in the browser on the lab folder.

**Not verified:** the kept-fields comparison of three lab models (the owner, on his database); the time of `intervals` on the lab's real per-case values (estimated 20 s the first time for 150 subjects, five metrics and 128 cases: 25 ms a subject and metric measured); four models in the browser (three were checked); a case kept in two shapes; a refused `field_compare` in a column; the slider dragged quickly; a grouped tradeoff chart (no pairs, by design); the chooser past twelve axes and many axes at 390 px (titles are cut to the space between axes); Tab order and focus rings, by eye in the screenshots only.
