# Implementation spec: milestone 3, results and charts

This continues [spec-m1-m2.md](spec-m1-m2.md). Section 1 of that file (rules for implementers) applies unchanged, and so does its format section 2. The milestone has two parts: 3a adds results and charts to the new core and its command line, changing no existing Tuldok file; 3b serves the new core from the Tuldok app and gets its own section once 3a is accepted.

**Done when (3a):** the lab folder opens into an empty database with every summary row of `results/*.csv` in the database; a chart is answered from the summary table without any result file being read; a copy of the lab folder alone, with no `runs/`, draws its charts; and after the lab's per-case values are imported locally, `save` rewrites every `results/*.csv` byte for byte as the lab's build script wrote it.

## 1. What a benchmark run writes

One values file per benchmark and subject, format `tuldok_results_v1`:

```json
{
  "format": "tuldok_results_v1",
  "benchmark": "dense-development-240",
  "subject": "pilot-dense-k1",
  "commit": "",
  "produced": "2026-11-10",
  "values": [
    {"case": "scene-012", "metric": "velocity_relative_l2", "value": 0.0123, "group": {"cells_per_metre": "32"}},
    {"case": "scene-013", "metric": "velocity_relative_l2", "value": null, "reason": "diverged"}
  ]
}
```

| Field | Rule |
| --- | --- |
| `format` | exactly `tuldok_results_v1` |
| `benchmark`, `subject` | the benchmark's name and one of its subject names |
| `commit`, `produced` | as in the results file columns of the same names |
| `values[].case` | 1 to 200 characters |
| `values[].metric` | one of the benchmark's metric ids |
| `values[].value` | a finite number, or `null` for a value that was not measured |
| `values[].reason` | required when `value` is `null`, not allowed otherwise; 1 to 400 characters |
| `values[].group` | optional object; keys are from the benchmark's `summary.group_by`; values are strings, numbers or booleans and are stored as text (`true`, `false`, and numbers as written by `repr`) |

A file is at most 64 MiB, strict JSON as in section 2.2 of the first spec. (case, metric, group) is unique within a file. Unknown fields are refused.

## 2. Tables

Added to each project schema, created like the others:

```sql
CREATE TABLE results_files (
  benchmark text PRIMARY KEY,
  file_sha256 text NOT NULL);       -- results/<benchmark>.csv as last imported or saved

CREATE TABLE result_summaries (
  benchmark text NOT NULL, subject text NOT NULL, metric text NOT NULL, grp text NOT NULL,
  count integer NOT NULL, unavailable integer NOT NULL,
  mean double precision, median double precision, p10 double precision,
  p90 double precision, min double precision, max double precision,
  commit text NOT NULL, produced text NOT NULL,
  origin text NOT NULL CHECK (origin IN ('file', 'values')),
  PRIMARY KEY (benchmark, subject, metric, grp));

CREATE TABLE result_values (
  benchmark text NOT NULL, subject text NOT NULL, case_id text NOT NULL,
  metric text NOT NULL, grp text NOT NULL,   -- this value's group fields as 'k=v;k=v', keys sorted; '' if none
  value double precision, reason text,
  PRIMARY KEY (benchmark, subject, case_id, metric, grp));
CREATE INDEX result_values_lookup ON result_values (benchmark, metric, subject);
```

## 3. Rules

**Which summaries exist.** For one benchmark, subject and metric there is one row with an empty group, over all that subject's values of the metric, and one row for each single group key and value (`key=value`), over the values that carry that key. There are no rows for combinations of keys. A results file may contain other groups; they are imported as written.

**Where a subject's summaries come from.** If the database holds values for a (benchmark, subject), its summaries are computed from them with `results.summarise` and have origin `values`. Otherwise they come from `results/<benchmark>.csv` and have origin `file`.

**Open.** A results file whose SHA-256 differs from `results_files`, or that is new or gone, is part of what makes a folder "changed": the unchanged fast path compares results files as well as definition files. On import, the rows of origin `file` for that benchmark are replaced by the file's rows, except for subjects that have values in the database.

**Importing values.** `project.import_values(text)` checks the file against its benchmark, then in one transaction replaces that (benchmark, subject)'s rows in `result_values` and its summaries. It refuses a file with any problem and changes nothing.

**Save.** For each benchmark with summary rows, `save` writes `results/<benchmark>.csv` with `results.write_results` when the text differs from the file on disk, subject to the same changed-on-disk rule as definitions, and records its SHA-256. A benchmark with no rows and an existing file has the file removed.

**Status.** `status()` gains `results_unsaved` (benchmarks whose database summaries differ from their file) alongside the existing fields.

**Removing a benchmark definition** also removes its summaries, values and `results_files` row; removing a subject from a benchmark removes that subject's rows when the definition is set.

## 4. Reading results

| Member of `Project` | Returns |
| --- | --- |
| `result_summaries(benchmark, subject=None, metric=None, group=None)` | the summary rows as `results.SummaryRow` plus origin; `group=None` means every group, `''` only the ungrouped rows, `'key'` the rows for that key |
| `result_values(benchmark, subject, metric=None, offset=0, limit=200)` | the per-case rows and their total, or an empty list when this machine holds no values for the subject |
| `results_overview()` | per benchmark: subjects with results, subjects with values, rows, and whether it differs from its file |

## 5. Charts

`charts.chart_data(project, reference)` answers a chart definition from `result_summaries` and the definitions, with SQL only. It never opens a results or values file. It returns:

```
{"chart", "title", "form", "benchmark", "statistic", "group",
 "metric": {"id", "title", "units", "better"}, "metric_x": {...} or null,
 "series": [{"group": "" or the group value, "points": [...]}],
 "missing": [subject names with no usable row]}
```

Each point has `subject`, `title`, `recipe` (a reference or null), `value`, `count`, `unavailable` and `produced`. With `group` set on the chart there is one series per value of that key, ordered numerically when every value is a number and as text otherwise; without it there is one series with an empty group. A subject with no row, or a row whose count is 0, is listed in `missing`.

| Form | Points |
| --- | --- |
| `ranking` | sorted best first by `value` according to the metric's `better` (`lower` ascending, `higher` descending, `none` ascending), ties by subject name |
| `tradeoff` | each also has `x`, the statistic of `metric_x`; a point lacking either value is missing; sorted by `x`; `frontier` is true when no other point in the series is at least as good on both metrics and better on one |
| `progression` | ordered by the `labels.trained_at` of the subject's recipe, ascending, then subjects without one by name; each has `position` from 0 and `best_so_far`, the best `value` up to and including it |
| `comparison` | `series` is replaced by `metrics` (every metric of the benchmark) and `rows`: one per subject with `values`, an object from metric id to the statistic or null; rows follow the chart's `subjects` order, or the ranking order of `metric` when it has none |

`charts.render_svg(data, *, theme='light') -> str` draws that data as one self-contained SVG document: no scripts, no external references, deterministic output for the same input.

- Colours and type come from the design tokens in `docs/plans/project-workspace-redesign/README.md` (surface, hairline, ink, secondary ink, accent, and the good colour for the frontier and the running best), in their light and dark values. One hue for marks; no decoration.
- `ranking`: horizontal bars, one row per subject, best at the top, each labelled with the subject's title and its value; the height grows with the number of rows.
- `tradeoff`: points, with a step line through the frontier points and labels on the frontier points only.
- `progression`: points in order with a step line for `best_so_far`.
- `comparison`: a grid of numbers, one row per subject and one column per metric, the best value in each column marked.
- An axis is logarithmic when all its values are positive and the largest is at least 100 times the smallest; otherwise linear from a rounded minimum. Axes carry the metric's title and units. Numbers show three significant digits.
- Missing subjects are counted in a one-line note under the chart. A chart with no points says so in place of the plot.

## 6. Command line

| Command | Does |
| --- | --- |
| `results FOLDER [BENCHMARK] [--subject S] [--metric M] [--group G]` | without a benchmark, the overview; with one, its summary rows |
| `values FOLDER BENCHMARK --subject S [--metric M] [--limit N]` | per-case rows, or a sentence saying this machine holds none |
| `import-values FOLDER FILE...` | imports values files; all are checked before any is imported |
| `chart FOLDER CHART [--svg FILE] [--theme light|dark]` | prints the chart's data as text, or as JSON with `--json`; with `--svg` writes the drawing |

`save` and `status` report results as section 3 says. `--json` applies to `results`, `values` and `chart`.

## 7. Slices

| Slice | Files | Notes |
| --- | --- | --- |
| T7 results | `tuldok_project/result_rows.py` (new: the values-file check, the SQL for sections 2 to 4), hooks in `store.py` (tables, open, save, status, definition removal), `results`, `values` and `import-values` in `__main__.py`, `tests/test_tuldok_project_result_rows.py` | database tests |
| T8 charts | `tuldok_project/charts.py` (new), `chart` in `__main__.py`, `tests/test_tuldok_project_charts.py`, and the results, values and chart sections of `docs/contracts/project-folder.md` | after T7 |
| L3 lab | `lab:scripts/build_tuldok_project.py`: results files hold the ungrouped row and one row per single group key and value; with `--values-output DIR` it also writes one `tuldok_results_v1` file per earlier benchmark and subject (outside Git, default `runs/tuldok-results/`); hand-written chart definitions under `lab:projects/surrogate-lab/charts/` | parallel with T7 |

The fixture gains a values file for its benchmark under `tests/fixtures/tuldok_project/minimal/values/` and a `progression` and a `comparison` chart.
