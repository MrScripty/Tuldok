# Project folder format

Owner: the package `tuldok_project/` (`folder.py` reads the folder, `documents.py`
and `schemas/*.json` check single files, `check.py` applies every rule,
`results.py` owns summary files, `store.py` and `result_rows.py` the database
copy and its results, `charts.py` charts and the report page). The format names are `tuldok_project_v1` for
the folder and `tuldok_definition_v1` for each definition.

A project folder describes a piece of research as a set of small JSON files that
people and agents write and keep in Git. Each file is a **definition**: it says
what a dataset, model, training recipe, benchmark, build step, environment or
chart is and, where something has to be produced, which command produces it.
What a command writes is a **product**. Products stay on the machine that made
them; the folder holds only what someone wrote, plus benchmark summaries.

`python -m tuldok_project check FOLDER` tells you whether a folder is valid. This
document says exactly what the checker accepts.

## What belongs in the folder

Put in the folder: the definitions, the result summary of each benchmark
(`results/`), and cards and notes written by people (`notes/`).

Keep out of the folder: generated datasets, weights, logs, run directories,
installed environments, caches, checksums of other files, and history. Git is
the history of every file in the folder. The scripts that commands run stay in
your code repository; definitions name them by path.

A rule of thumb: if a person or an agent wrote it, it belongs in the folder. If a
command produced it, it does not. Result summaries are the one exception, so that
results travel with the project.

## Layout

```
tuldok.json
README.md                optional, not read
.gitignore               optional, not read
datasets/<name>.json
models/<name>.json
recipes/<name>.json
benchmarks/<name>.json
steps/<name>.json
environments/<name>.json
charts/<name>.json
results/<benchmark name>.csv
notes/...
```

- `tuldok.json` is required. Every other entry is optional.
- Any other top-level entry is an error. Move such files into `notes/` or out of
  the folder.
- The seven **definition directories** (`datasets/` to `charts/`) hold only
  `<name>.json` files, one definition each, and no subdirectories.
- `results/` holds only `<name>.csv` files.
- `notes/` holds plain files and directories to any depth. Their contents are not
  read.
- Every file is a regular file and every directory a real directory. A symbolic
  link anywhere in the folder, including under `notes/`, is an error.
- Size limits: `tuldok.json` 64 KiB, a definition 1 MiB, a results file 16 MiB.

A **name** is 1 to 120 characters of lowercase letters, digits, `.`, `_` and `-`,
starting with a letter or digit (`^[a-z0-9][a-z0-9._-]{0,119}$`). The file
`recipes/pilot-dense-k1.json` defines the recipe named `pilot-dense-k1`.

## JSON rules

`tuldok.json` and every definition are UTF-8 JSON, without a byte order mark,
holding one JSON object. The checker refuses:

- a key that appears twice in one object;
- `NaN`, `Infinity` and `-Infinity`, and numbers too large to represent;
- any field this document does not define. The contents of `settings`, `config`
  and the keys of `labels` are free.

## `tuldok.json`

| Field | Required | Rule |
| --- | --- | --- |
| `format` | yes | exactly `tuldok_project_v1` |
| `id` | yes | 32 lowercase hexadecimal characters; make a new one per project |
| `name` | yes | 1 to 120 characters |
| `code_root` | no | the path from the project folder to the root of the code that commands run in; default `.`; not empty and not absolute; may contain `..` |

The **code root** is the directory that commands run in and that code paths in
definitions are relative to. It must be an existing directory. A folder kept at
`projects/surrogate-lab/` inside the code repository uses `../..`.

Example, `tuldok.json`:

```json
{
  "format": "tuldok_project_v1",
  "id": "0dcc3af1e6b84b89a0e70554d98e7326",
  "name": "Rheon surrogate lab",
  "code_root": "../.."
}
```

## References and inputs

A **reference** is the string `<directory>/<name>`, for example
`datasets/sinusoidal-v1`. It names the definition in `datasets/sinusoidal-v1.json`,
which must exist. Each field that takes a reference accepts only some
directories:

| Field | Accepts |
| --- | --- |
| `run.inputs` | `datasets/`, `recipes/`, `steps/` |
| `run.environment` | `environments/` |
| `model` (recipe) | `models/` |
| `subjects[].recipe` (benchmark) | `recipes/` |
| `cases.dataset` (benchmark) | `datasets/` |
| `benchmark` (chart) | `benchmarks/` |

An **input** is what a command reads from another definition's product. It is
written either as a reference, meaning the whole product, or as
`{"from": <reference>, "output": <output name>}`, meaning one named output that the
other definition declares in its `run.outputs`.

## Fields common to every definition

| Field | Required | Rule |
| --- | --- | --- |
| `format` | yes | exactly `tuldok_definition_v1` |
| `kind` | yes | `dataset`, `model`, `recipe`, `benchmark`, `step`, `environment` or `chart`; must match the directory |
| `title` | yes | 1 to 200 characters |
| `description` | no | at most 4,000 characters |
| `card` | no | path of an existing file under `notes/`, written from the project folder, for example `notes/fits/early-fit.md` |
| `labels` | no | object of at most 32 entries; any keys; string values of at most 400 characters |
| `earlier_work` | no | see below; allowed on `dataset`, `model`, `recipe`, `benchmark` and `step` |

`earlier_work` marks an item converted from work done before this format existed:

| Field | Required | Rule |
| --- | --- | --- |
| `rebuild` | yes | `yes`, `after-inputs`, `needs-work` or `no` |
| `reason` | when `rebuild` is `needs-work` or `no` | 1 to 1,000 characters |

The label states a fact about this item alone, never about what it uses:

- `yes`: its command, code and settings are in Git and the command runs as written.
- `after-inputs`: the same, and one of its inputs is an earlier model's weights.
- `needs-work`: nothing it names is lost, but the recorded command does not run as
  written. The reason says what has to change.
- `no`: its command, its code or its producer is lost or was never in Git. The
  reason says which.

Whether an item can in fact be rebuilt also depends on everything it uses; Tuldok
works that out from the references, so do not record it here. An item with
`rebuild: no` may leave out `run`. Code paths that are missing in an item with
`earlier_work` are warnings, not errors.

Example, `recipes/pressure-fit-0042.json`:

```json
{
  "format": "tuldok_definition_v1",
  "kind": "recipe",
  "title": "Pressure fit 0042",
  "card": "notes/fits/pressure-fit-0042.md",
  "labels": {"fit_id": "fit-0042", "trained_at": "2026-03-14"},
  "earlier_work": {"rebuild": "no", "reason": "Trained by the earlier study harness; its command and training data were not recorded."},
  "model": "models/divergence-free-stepper"
}
```

## The `run` block

`dataset`, `recipe`, `benchmark` and `step` say how they are produced in a `run`
object. It is required unless `earlier_work.rebuild` is `no`.

| Field | Required | Rule |
| --- | --- | --- |
| `command` | yes | 1 to 64 strings, the program and its arguments; run in the code root. When the first string is exactly `python` it means the environment's interpreter |
| `environment` | when the first string of `command` is `python` | reference to `environments/` |
| `inputs` | no | at most 32 entries; keys `^[a-z][a-z0-9_]{0,31}$`; values are inputs from `datasets/`, `recipes/` or `steps/` |
| `settings` | no | object, free content, written to a file whose path replaces `{settings}`; not together with `settings_file` |
| `settings_file` | no | code path of a settings file whose path replaces `{settings}` |
| `env` | no | at most 32 environment variables; names `^[A-Z_][A-Z0-9_]*$`; string values |
| `outputs` | no | keys as for `inputs`; each value `{"path": <path inside the output directory>, "role": <role>}`; role `data`, `weights`, `results`, `log`, `report` or `file` |
| `resources` | no | any of `gpu` (boolean), `cpu_threads` (integer ≥ 1), `memory_gb`, `wall_hours`, `disk_gb` (numbers > 0) |
| `sources` | no | at most 64 code paths (files or directories); a change in them means the code changed |
| `estimate` | no | `{"command": [...]}`, 1 to 64 strings; the command prints one JSON object with any of `disk_bytes`, `wall_seconds`, `items` |

A **code path** is a path relative to the code root, at most 1,024 characters.
`settings_file`, `sources`, a model's `config_file` and `sources`, and an
environment's `install.requirements` are code paths. A code path, and an output's
`path`, must be in normal form: not absolute, no `..`, no `.` or empty parts, no
trailing `/`. A code path must exist under the code root (as a file or a
directory) and may not lead outside it through a symbolic link.

**Placeholders** are written in braces in `command`, in `env` values and in
`estimate.command`:

| Placeholder | Becomes |
| --- | --- |
| `{output}` | the directory the command writes into |
| `{settings}` | the path of the settings file; requires `settings` or `settings_file` |
| `{inputs.<name>}` | the path of that input; `<name>` must be a key of `inputs` |
| `{subject}` | benchmarks only: the current subject's `argument` |
| `{subject.name}` | benchmarks only: the current subject's name |

Any other placeholder is an error, and so is a brace without its partner. Write
`{{` and `}}` for literal braces.

## The seven kinds

The examples below come from one project. References in them point at the other
examples, except `environments/cuda-torch`, a second environment not shown.

### `dataset`

| Field | Required | Rule |
| --- | --- | --- |
| `run` | unless `earlier_work.rebuild` is `no` | see the `run` block |
| `splits` | no | object, split name to a number of items (integer ≥ 0) |

Example, `datasets/sinusoidal-v1.json`:

```json
{
  "format": "tuldok_definition_v1",
  "kind": "dataset",
  "title": "Sinusoidal-forcing scenes v1",
  "run": {
    "command": ["python", "-m", "surrogate.datasets", "generate", "sinusoidal-v1", "--root", "{output}"],
    "environment": "environments/lab-cpu",
    "inputs": {"solver": {"from": "steps/reference-solver", "output": "probe"}},
    "env": {"SURROGATE_PROBE": "{inputs.solver}"},
    "outputs": {"bank": {"path": "sinusoidal-v1/bank.json", "role": "data"}},
    "resources": {"cpu_threads": 1},
    "sources": ["surrogate/datasets", "surrogate/scenes.py", "surrogate/solver.py"],
    "estimate": {"command": ["python", "-m", "surrogate.datasets", "plan", "sinusoidal-v1", "--root", "{output}"]}
  },
  "splits": {"train": 16, "development": 8, "reserved": 88}
}
```

### `model`

A model is an architecture. It produces nothing by itself; recipes train it.

| Field | Required | Rule |
| --- | --- | --- |
| `entry` | no | non-empty string naming the code entry point, for example `surrogate.models:DivergenceFreeStepper` |
| `config` | no | object, free content; not together with `config_file` |
| `config_file` | no | code path |
| `sources` | no | at most 64 code paths |

Example, `models/divergence-free-stepper.json`:

```json
{
  "format": "tuldok_definition_v1",
  "kind": "model",
  "title": "Divergence-free U-Net stepper",
  "entry": "surrogate.models:DivergenceFreeStepper",
  "sources": ["surrogate/models/stepper.py", "surrogate/models/unet3d.py"]
}
```

### `recipe`

A recipe trains a model; its product is weights.

| Field | Required | Rule |
| --- | --- | --- |
| `run` | unless `earlier_work.rebuild` is `no` | see the `run` block |
| `model` | no | reference to `models/` |

Example, `recipes/pilot-dense-k1.json`:

```json
{
  "format": "tuldok_definition_v1",
  "kind": "recipe",
  "title": "Pilot stepper on sinusoidal scenes, one output per pass",
  "model": "models/divergence-free-stepper",
  "run": {
    "command": ["python", "-m", "surrogate.train", "{settings}", "{output}", "--device", "cuda"],
    "environment": "environments/cuda-torch",
    "settings_file": "surrogate/configs/pilot-dense-k1.json",
    "inputs": {"training": "datasets/sinusoidal-v1"},
    "env": {"SURROGATE_DATA": "{inputs.training}"},
    "outputs": {
      "weights": {"path": "model.pt", "role": "weights"},
      "log": {"path": "log.jsonl", "role": "log"}
    },
    "resources": {"gpu": true},
    "sources": ["surrogate/train.py", "surrogate/models"]
  }
}
```

### `step`

A step is any other command whose output something needs, such as building a
solver.

| Field | Required | Rule |
| --- | --- | --- |
| `run` | unless `earlier_work.rebuild` is `no` | see the `run` block |

Example, `steps/reference-solver.json`:

```json
{
  "format": "tuldok_definition_v1",
  "kind": "step",
  "title": "Rheon reference solver probe",
  "run": {
    "command": ["cargo", "build", "--release", "--locked", "--manifest-path", "probes/reference/Cargo.toml"],
    "env": {"CARGO_TARGET_DIR": "{output}"},
    "outputs": {"probe": {"path": "release/rheon-reference-probe", "role": "file"}},
    "sources": ["probes/reference/Cargo.toml", "probes/reference/Cargo.lock", "probes/reference/src"]
  }
}
```

### `benchmark`

A benchmark measures **subjects** (the things being compared, usually trained
recipes) on **cases** (usually one split of a dataset) and reports **metrics**.
Its command runs once per subject.

| Field | Required | Rule |
| --- | --- | --- |
| `run` | unless `earlier_work.rebuild` is `no` | see the `run` block; `outputs` must declare exactly one output with role `results` |
| `metrics` | yes | 1 to 64 objects, see below |
| `subjects` | yes | 0 to 1,000 objects, see below |
| `cases` | no | `{"dataset"?: reference to datasets/, "split"?: non-empty string, "count"?: integer ≥ 0}` |
| `summary` | no | `{"group_by"?: up to 8 distinct ids, "statistics"?: distinct names from mean, median, p10, p90, min, max}` |

A metric is `{"id", "title", "units"?, "better"}`: `id` matches
`^[a-z][a-z0-9_]{0,63}$` and is unique in the benchmark; `title` is 1 to 200
characters; `units` is any string; `better` is `lower`, `higher` or `none`.

A subject is `{"name", "title"?, "recipe"?, "argument"?}`: `name` follows the name
rule and is unique in the benchmark; `title` is 1 to 200 characters; `recipe` is a
reference to `recipes/`; `argument` is the string that replaces `{subject}`. The
only placeholder an argument may hold is `{recipe}`, the path of that recipe's
product, and only when the subject has a `recipe`.

`summary.group_by` names the dimensions the summary is split by, written with the
metric id pattern. `summary.statistics` says which statistics every summary row
with measured values must fill; without it, all six.

Example, `benchmarks/dense-development-240.json`:

```json
{
  "format": "tuldok_definition_v1",
  "kind": "benchmark",
  "title": "Sinusoidal development scenes, 240-output rollouts",
  "run": {
    "command": ["python", "-m", "surrogate.bench", "run", "--suite", "dense-development-240", "--subject", "{subject}", "--output", "{output}/result.json"],
    "environment": "environments/cuda-torch",
    "inputs": {"cases": "datasets/sinusoidal-v1"},
    "env": {"SURROGATE_DATA": "{inputs.cases}"},
    "outputs": {"results": {"path": "result.json", "role": "results"}},
    "sources": ["surrogate/bench"]
  },
  "metrics": [
    {"id": "velocity_error_final", "title": "Final velocity error", "units": "ratio", "better": "lower"},
    {"id": "time_per_output_ms", "title": "Time per output", "units": "ms", "better": "lower"}
  ],
  "subjects": [
    {"name": "persistence", "title": "No change: the error any model must beat", "argument": "persistence"},
    {"name": "pilot-dense-k1", "recipe": "recipes/pilot-dense-k1", "argument": "checkpoint:{recipe}/model.pt"}
  ],
  "cases": {"dataset": "datasets/sinusoidal-v1", "split": "development", "count": 8},
  "summary": {"group_by": ["cells_per_metre"]}
}
```

### `environment`

An environment says which Python and packages a command needs. Commands whose
first word is `python` name one.

| Field | Required | Rule |
| --- | --- | --- |
| `python` | yes | `3.<minor>`, for example `3.12` |
| `device` | yes | `cpu` or `cuda` |
| `packages` | yes | 1 to 64 entries, package name to exact version. Names match `^[A-Za-z0-9]([A-Za-z0-9._-]*[A-Za-z0-9])?$`; versions match `^[0-9A-Za-z][0-9A-Za-z.+!_-]*$`, so `2.8.0+cpu` is allowed and `>=2.8` is not |
| `install` | no | `{"requirements": <code path>, "index_urls"?: up to 4 https:// URLs}` |

`earlier_work` is not allowed here.

Example, `environments/lab-cpu.json`:

```json
{
  "format": "tuldok_definition_v1",
  "kind": "environment",
  "title": "Lab CPU environment",
  "python": "3.12",
  "device": "cpu",
  "packages": {"numpy": "2.3.5", "torch": "2.8.0+cpu"},
  "install": {
    "requirements": "tuldok/requirements-cpu.lock",
    "index_urls": ["https://download.pytorch.org/whl/cpu"]
  }
}
```

### `chart`

A chart is drawn from one benchmark's summary.

| Field | Required | Rule |
| --- | --- | --- |
| `benchmark` | yes | reference to `benchmarks/` |
| `form` | yes | `ranking`, `tradeoff`, `progression` or `comparison` |
| `metric` | yes | a metric id of that benchmark |
| `metric_x` | when `form` is `tradeoff`; otherwise not allowed | a metric id of that benchmark |
| `statistic` | no | `mean`, `median`, `p10`, `p90`, `min` or `max`; default `median` |
| `subjects` | no | distinct subject names of that benchmark; default all |
| `group` | no | one of that benchmark's `summary.group_by` |

`earlier_work` is not allowed here.

Example, `charts/final-velocity-ranking.json`:

```json
{
  "format": "tuldok_definition_v1",
  "kind": "chart",
  "title": "Final velocity error by subject",
  "benchmark": "benchmarks/dense-development-240",
  "form": "ranking",
  "metric": "velocity_error_final",
  "group": "cells_per_metre"
}
```

## Results files

`results/<name>.csv` is the summary of benchmark `benchmarks/<name>.json`, which
must exist. One row summarises the values of one metric for one subject, either
over all cases or over one group of them.

- UTF-8, `\n` line ends (a `\r` is an error), CSV quoting as in RFC 4180, no
  empty lines. The file should end with a line end; a missing one is a warning.
- The first line is exactly
  `subject,metric,group,count,unavailable,mean,median,p10,p90,min,max,commit,produced`
  and every other line has these 13 cells.

| Column | Rule |
| --- | --- |
| `subject` | a subject name of the benchmark |
| `metric` | a metric id of the benchmark |
| `group` | empty for all cases, or `key=value` pairs joined by `;`, keys distinct, sorted, and each in the benchmark's `summary.group_by`; a value may not contain `;`, `=` or a line break |
| `count` | integer ≥ 0, digits only |
| `unavailable` | integer ≥ 0, digits only |
| `mean`, `median`, `p10`, `p90`, `min`, `max` | a decimal number matching `-?[0-9]+(\.[0-9]+)?([eE][-+]?[0-9]+)?`, or empty. All six are empty when `count` is 0. When `count` is above 0, each statistic in the benchmark's `summary.statistics` (all six by default) is filled; the others may be empty |
| `commit` | 40 lowercase hexadecimal characters (the Git commit of the code that measured), or empty |
| `produced` | a real date `YYYY-MM-DD` or time `YYYY-MM-DDTHH:MM:SSZ` |

Rows are unique on (`subject`, `metric`, `group`) and sorted by those three
compared as plain strings, so `cells_per_metre=16` comes before
`cells_per_metre=8`.

**Statistics.** For one subject, metric and group, take the measured values in
ascending order, v₀ … vₙ₋₁. `count` is n; `unavailable` is how many values could
not be measured. `mean` is the arithmetic mean, `min` is v₀ and `max` is vₙ₋₁.
`median`, `p10` and `p90` are the value at position p × (n − 1) for p = 0.5, 0.1
and 0.9, interpolating linearly between the two closest values when the position
is not whole. For 0.12, 0.15, 0.2, 0.31, `p10` is at position 0.3:
0.12 + 0.3 × (0.15 − 0.12) = 0.129. Numbers are written as Python's
`repr(float)` writes them. `tuldok_project.results.summarise` computes them.

Example, `results/dense-development-240.csv`:

```csv
subject,metric,group,count,unavailable,mean,median,p10,p90,min,max,commit,produced
persistence,time_per_output_ms,,0,8,,,,,,,,2026-11-09
persistence,velocity_error_final,cells_per_metre=8,4,0,0.9875,0.975,0.915,1.07,0.9,1.1,,2026-11-09
pilot-dense-k1,time_per_output_ms,,8,0,43.825,43.8,40.76,46.99,40.2,47.9,4f1c0e9a7b2d3c5e6f708192a3b4c5d6e7f80912,2026-11-09T14:30:00Z
pilot-dense-k1,velocity_error_final,cells_per_metre=16,4,0,0.2625,0.235,0.192,0.355,0.18,0.4,4f1c0e9a7b2d3c5e6f708192a3b4c5d6e7f80912,2026-11-09T14:30:00Z
pilot-dense-k1,velocity_error_final,cells_per_metre=8,4,0,0.195,0.175,0.129,0.277,0.12,0.31,4f1c0e9a7b2d3c5e6f708192a3b4c5d6e7f80912,2026-11-09T14:30:00Z
```

## Rules across files

1. Every reference names an existing definition in a directory its field accepts.
2. Every `{"from", "output"}` input names an output that the definition it comes
   from declares in `run.outputs`.
3. Definitions may not use each other in a cycle. A definition uses another
   through these fields:

   | Field | Role of the use |
   | --- | --- |
   | an entry of `run.inputs` | `input:<key>` |
   | `run.environment` | `environment` |
   | a recipe's `model` | `model` |
   | a benchmark subject's `recipe` | `subject:<subject name>` |
   | a benchmark's `cases.dataset` | `cases` |
   | a chart's `benchmark` | `benchmark` |

4. A chart's `metric`, `metric_x`, `subjects` and `group` exist in its benchmark.
5. Code paths exist under the code root (see the `run` block).
6. Every results file has its benchmark and follows the rules above.

## Checking a folder

From the Tuldok repository:

```sh
.venv/bin/python -m tuldok_project check FOLDER [--no-code] [--json]
```

`FOLDER` is the directory that holds `tuldok.json`. `--no-code` skips looking
into the code root: the code root and code paths are not required to exist, but
paths are still checked for normal form. `--json` prints one JSON object instead
of text.

The exit status is 0 when there are no errors (warnings allowed), 1 when there is
at least one error, and 2 for a usage error such as an unknown option.

Every problem is reported; the check does not stop at the first. A problem has a
severity (`error` or `warning`), the file's path relative to the project folder,
a JSON pointer to the field (empty for a problem with the whole file; `line <n>`
in a results file), and one sentence. Text output prints one line per problem,
with the parts separated by two spaces and `-` for an empty pointer, sorted by
path and pointer, then a count:

```
error  recipes/pilot-dense-k1.json  /run/inputs/training  datasets/sinusoidal-v2 does not exist; add datasets/sinusoidal-v2.json or fix the reference.
warning  results/dense-development-240.csv  -  The results file does not end with a line end.
1 error, 1 warning in /home/me/lab/projects/surrogate-lab
```

With `--json` the object is `{"folder", "ok", "errors", "warnings", "problems"}`,
each problem being `{"severity", "path", "pointer", "message"}`.

There are three warnings; every other problem is an error:

- a code path that does not exist, in a definition with `earlier_work`;
- a results file without a final line end;
- a results file that is not checked because its benchmark has errors.

One mistake is reported once. A reference into the wrong directory is reported by
the field's own rule and not again as a missing definition, and a chart is not
compared with a benchmark that has errors of its own.

## Working with the database copy

Tuldok keeps a working copy of a project folder in Postgres: the exact text of
every definition, the uses between them, and edits that are not yet written back
to the folder. Each project has its own schema, `project_<id>`, named after the
`id` in `tuldok.json`. These commands work on that copy:

```sh
.venv/bin/python -m tuldok_project COMMAND FOLDER [options]
```

| Command | Does |
| --- | --- |
| `open` | Imports the folder into the database, or attaches to the copy when no definition file changed. Prints the number of definitions of each kind and in each state, and how long opening took. |
| `list [--kind K]` | Prints each definition's reference, state and title, one per line. `--kind` keeps one kind. |
| `show REFERENCE` | Prints a definition's reference, title, kind and state, what it uses and what uses it (each with its role), then the definition's text. |
| `graph [--order]` | Prints every definition with its kind and state, then every use as `from  role  to`. `--order` instead prints the build order: each definition after everything it uses, with its state. |
| `status` | Lists definitions edited or removed in the database and not yet saved, and definition files added, changed or missing on disk since the last import. |
| `set REFERENCE FILE` | Replaces or adds the definition at `REFERENCE` with the text of `FILE`, in the database only. The text is checked on its own and against the rest of the project; an edit with any error is refused and changes nothing. |
| `remove REFERENCE` | Removes the definition in the database only. It is refused while another definition uses it. |
| `save` | Writes every unsaved definition to its file and deletes the files of removed ones. It writes nothing when one of those files changed on disk since it was imported, and names them. |
| `forget` | Drops the project's copy from the database, including unsaved edits. The folder is not touched. |

Every command except `forget` opens the project first, which imports anything
that changed on disk, so `list`, `show`, `graph` and `status` always describe the
folder as it is now plus the unsaved edits. Opening runs the same check as
`check`; a folder with errors is not imported and the database is left as it was.

A state is worked out from the definitions, never stored in a file:

| State | When |
| --- | --- |
| `cannot-rebuild` | its `earlier_work.rebuild` is `no`, or something it uses through an input, directly or further up, is `cannot-rebuild` |
| `needs-work` | not `cannot-rebuild`, and its `earlier_work.rebuild` is `needs-work` or something it uses through an input is `needs-work` |
| `not-built` | any other dataset, recipe, benchmark or step |
| `not-set-up` | an environment |
| `none` | a model or a chart |

Options:

| Option | Commands | Meaning |
| --- | --- | --- |
| `--database-url URL` | all but `check` | The Postgres database. Without it, the `TULDOK_DATABASE_URL` environment variable is used; with neither, the command stops with exit status 2. |
| `--json` | `open`, `list`, `show`, `graph`, `status`, `save`, `results`, `values`, `import-values`, `chart`, `plan` | Print one JSON document with the same content as the text. |
| `--rebind` | all that open | The copy is bound to the folder it was first opened from. Opening the same project from another path is refused unless `--rebind` is given, which binds the copy to the new path. |
| `--keep` | all that open | Where a file changed on disk and the same definition has unsaved edits, keep the edits; the changed file becomes the version that `save` replaces. |
| `--discard` | all that open | Where a file changed on disk and the same definition has unsaved edits, drop the edits and take the file. |

Without `--keep` or `--discard`, such a conflict is refused and names the
definitions concerned.

An open project holds a lock in the database, so one command at a time works on
a project. Each command releases the lock before it exits. A command started
while the project is open elsewhere is refused.

The exit status is 0 when the command did its work, 1 when it was refused (the
folder has errors, an edit is not valid, a definition is in use or missing, a
conflict, a file changed on disk, the project is open elsewhere) or the database
failed, and 2 for a usage error, including a missing database setting or a `set`
file that cannot be read. A refusal is printed on standard error as one sentence,
followed by any problems in the same form `check` prints them:

```
datasets/waves cannot be set; see the problems.
error  datasets/waves.json  /title  Add the required field 'title'.
```

## Results in the database

When a project is opened, every results file is imported into the database copy
as summary rows, one row per line of the file. Each summary row has an origin:

| Origin | Where the row comes from |
| --- | --- |
| `file` | the line of `results/<benchmark>.csv` |
| `values` | computed from per-case values imported on this machine (see [Values files](#values-files)), with the statistics of [Results files](#results-files) |

For one benchmark and subject, when the database holds per-case values, all of
that subject's summary rows are computed from them and have origin `values`;
otherwise they come from the results file. The computed rows are one row with an
empty group over all of the subject's values of a metric, and one row for each
single group key and value (`cells_per_metre=8`) over the values that carry it.
There are no rows for combinations of keys.

Opening notices a results file that is new, changed or gone, the same way it
notices a changed definition file, and replaces that benchmark's `file` rows
with the file's lines, except for subjects that have values here.

`save` writes `results/<benchmark>.csv` from the summary rows of each benchmark
whose rows differ from the file, and removes the file of a benchmark that has no
rows left. Like definitions, it writes nothing when a results file changed on
disk since it was imported. `status` lists `results unsaved` (benchmarks whose
rows differ from their file) and `results changed on disk`. Removing a benchmark
removes its summary rows and values; removing a subject from a benchmark removes
that subject's rows.

Charts and the report read only these rows. A copy of the folder with its
`results/` files draws every chart; no run directory or values file is needed.

## Values files

A benchmark run writes one values file per benchmark and subject: the measured
value of every case and metric. Values files are not part of the project folder;
they stay on the machine that ran the benchmark, and `import-values` brings them
into the database copy. Format `tuldok_results_v1`, strict JSON as in
[JSON rules](#json-rules), at most 64 MiB:

| Field | Rule |
| --- | --- |
| `format` | exactly `tuldok_results_v1` |
| `benchmark` | the name of a benchmark of the project |
| `subject` | one of that benchmark's subject names |
| `commit` | 40 lowercase hexadecimal characters, or empty |
| `produced` | a date `YYYY-MM-DD` or a time `YYYY-MM-DDTHH:MM:SSZ` |
| `values` | a list of at least one value |

Each value:

| Field | Required | Rule |
| --- | --- | --- |
| `case` | yes | 1 to 200 characters |
| `metric` | yes | a metric id of the benchmark |
| `value` | yes | a finite number, or `null` for a value that was not measured |
| `reason` | when `value` is `null`; otherwise not allowed | 1 to 400 characters: why there is no value |
| `group` | no | an object whose keys are in the benchmark's `summary.group_by`; each value a string, number or boolean, without `;`, `=` or a line break |

Group values are stored as text: strings as written, `true` and `false`, and
numbers as Python's `repr` writes them (`8` stays `8`, `8.0` stays `8.0`).
(`case`, `metric`, `group`) is unique within a file. Unknown fields are refused.

Example, `rollout-stepper-k1.json`:

```json
{
  "format": "tuldok_results_v1",
  "benchmark": "rollout",
  "subject": "stepper-k1",
  "commit": "0123456789abcdef0123456789abcdef01234567",
  "produced": "2026-11-10",
  "values": [
    {"case": "scene-01", "metric": "rmse", "value": 0.25, "group": {"horizon": 1}},
    {"case": "scene-01", "metric": "rmse", "value": 1.0, "group": {"horizon": 8}},
    {"case": "scene-01", "metric": "seconds", "value": 1.0},
    {"case": "scene-02", "metric": "rmse", "value": 0.5, "group": {"horizon": 1}},
    {"case": "scene-02", "metric": "rmse", "value": null, "reason": "diverged before step 8", "group": {"horizon": 8}},
    {"case": "scene-02", "metric": "seconds", "value": 1.5}
  ]
}
```

## Reading results

| Command | Does |
| --- | --- |
| `results [BENCHMARK] [--subject S] [--metric M] [--group G]` | Without a benchmark, one line per benchmark: subjects with results, subjects with values on this machine, summary rows by origin, and whether the rows differ from the results file. With a benchmark, its summary rows; `--group` keeps the rows of one group key, and `--group ''` the rows over all cases. |
| `values BENCHMARK --subject S [--metric M] [--limit N]` | The per-case values held on this machine for one subject, at most `N` (default 200), or a sentence saying there are none. |
| `import-values FILE...` | Imports values files. Every file is checked first; if any has a problem, the problems are printed and nothing is imported. Each file replaces its subject's values and summary rows in one step. |

`BENCHMARK` is a benchmark's name (`rollout`) or its reference
(`benchmarks/rollout`). Anything else is a usage error. Example, with the values
file above:

```
$ .venv/bin/python -m tuldok_project import-values FOLDER rollout-stepper-k1.json
imported  benchmarks/rollout  stepper-k1  6 values  4 summary rows
$ .venv/bin/python -m tuldok_project results FOLDER benchmarks/rollout --subject stepper-k1
subject     metric   group      count  unavailable  mean    median  p10    p90    min   max  produced    origin
stepper-k1  rmse     -          3      1            0.5833  0.5     0.3    0.9    0.25  1    2026-11-10  values
stepper-k1  rmse     horizon=1  2      0            0.375   0.375   0.275  0.475  0.25  0.5  2026-11-10  values
stepper-k1  rmse     horizon=8  1      1            1       1       1      1      1     1    2026-11-10  values
stepper-k1  seconds  -          2      0            1.25    1.25    1.05   1.45   1     1.5  2026-11-10  values
$ .venv/bin/python -m tuldok_project values FOLDER rollout --subject stepper-k1 --metric rmse
case      metric  group      value
scene-01  rmse    horizon=1  0.25
scene-01  rmse    horizon=8  1.0
scene-02  rmse    horizon=1  0.5
scene-02  rmse    horizon=8  none (diverged before step 8)
```

A refused import prints each problem on standard error in the form `check`
uses and exits with status 1:

```
error  bad.json  /values/0/reason  A null value needs a reason of 1 to 400 characters.
Nothing was imported: 1 problem in the values files.
```

## Charts and the report

| Command | Does |
| --- | --- |
| `chart CHART [--svg FILE] [--theme light\|dark]` | Prints the chart's data as text, or as JSON with `--json`. With `--svg`, also writes the drawing to `FILE`. |
| `report --output FILE [--theme light\|dark]` | Writes one HTML page of the project to `FILE`. |

`CHART` is a chart's name (`rollout-ranking`) or its reference
(`charts/rollout-ranking`). `--theme` picks the light or the dark colours;
the default is light.

A chart is answered from the summary rows in the database and the definitions,
never from a file. It uses the chart's `statistic` (default `median`) of each
subject's rows for its `metric`, over all cases, or with `group` set one panel
per value of that group key, ordered as numbers when every value is a number and
as text otherwise. The subjects are the chart's `subjects`, or every subject of
the benchmark. A subject with no row, with a row whose `count` is 0, or whose
row lacks the statistic is not drawn; it is listed as missing, and the drawing
says how many are missing and names them.

"Best" follows the metric's `better`: `lower` and `none` put the lowest value
first, `higher` the highest.

| Form | What it shows |
| --- | --- |
| `ranking` | One horizontal bar per subject, best at the top, each labelled with the subject's title and its value. Ties are ordered by subject name. The drawing grows with the number of subjects. |
| `tradeoff` | One point per subject at (`metric_x`, `metric`). A subject lacking either value is missing. The frontier is the set of subjects that no other subject is at least as good as on both metrics and better than on one; a step line joins them, and they carry labels where labels fit without overlapping. |
| `progression` | The subjects in the order they were trained: by the `trained_at` label of the subject's recipe, earliest first, then the subjects without one by name. A step line shows the best value so far, and the subjects that set a new best carry labels where they fit. |
| `comparison` | A table of numbers: one row per subject, one column per metric of the benchmark, the best value in each column marked. Rows follow the chart's `subjects`, or the ranking of `metric` when the chart has none. A subject with no value for any metric is missing. |

An axis is logarithmic when all its values are positive and the largest is at
least 100 times the smallest; otherwise it is linear (bars always start at
zero). Axes carry the metric's title and units, and numbers show three
significant digits, very small and very large ones as `2.43e-6`. A chart with
no values says so in place of the plot.

The drawing is one SVG document with no scripts and no links, the same bytes
for the same data. Every bar, point and number carries the subject's full title
and its value as a tooltip; long subject titles are cut with an ellipsis.

Example:

```
$ .venv/bin/python -m tuldok_project chart FOLDER rollout-ranking --svg ranking.svg
chart      charts/rollout-ranking  ranking
title      Rollout error by subject
benchmark  benchmarks/rollout
metric     rmse: median Rollout RMSE (m/s), lower is better
group      horizon

horizon = 1
rank  subject     value   count
1     stepper-k2  0.3125  4
2     stepper-k1  0.375   2
3     early-fit   0.625   4

horizon = 8
rank  subject     value  count
1     stepper-k1  1      1
2     stepper-k2  1.25   4

1 of 3 subjects has no value: early-fit.
Wrote ranking.svg (6091 bytes).
```

With `--json`, `chart` prints one object:

| Field | Meaning |
| --- | --- |
| `chart`, `title`, `description`, `form`, `benchmark`, `statistic`, `group` | from the chart definition; `group` is null without one |
| `metric`, `metric_x` | `{"id", "title", "units", "better"}`; `metric_x` is null except for a `tradeoff` |
| `subject_count` | how many subjects the chart covers |
| `series` | all forms but `comparison`: one entry per group value (one entry with group `""` without a group), each `{"group", "points", "missing"}` |
| `metrics`, `rows` | `comparison` only: every metric of the benchmark, and one row per subject `{"subject", "title", "recipe", "group", "values"}`, `values` mapping each metric id to its number or null |
| `missing` | the names of the subjects not drawn, in the chart's subject order; with a group, those missing in any panel |

A point is `{"subject", "title", "recipe", "value", "count", "unavailable",
"produced"}`, where `recipe` is the subject's recipe reference or null. A
`tradeoff` point adds `x` and `frontier`; a `progression` point adds `position`
(from 0), `best_so_far` and `trained_at`.

The report page, from `report`, reads top to bottom: the project's name, folder
and id; how many definitions there are of each kind and in each state, and how
many benchmarks have results; every chart with its title, a one-line note on
what it shows and how many subjects are missing, and its drawing; the results
overview; then the definitions of each kind with their states, each kind in a
closed section that opens on a click. The page is one file with its style
embedded and its charts drawn inline, no scripts and no links, so it can be
sent or opened anywhere.

```
$ .venv/bin/python -m tuldok_project report FOLDER --output report.html --theme dark
Wrote report.html (4 charts, 24626 bytes).
```

## Planning a build

A plan says what has to be built on this machine to have one or more
definitions, in what order, and what stands in the way. Making a plan runs
nothing. It reads the database copy only: it starts no command, including a
definition's `estimate` command, and opens no file of the folder or the code.
The figures in a plan are the ones each definition declares in
`run.resources`.

| Command | Does |
| --- | --- |
| `plan TARGET... [--all]` | Prints the plan for the named definitions. `--all` plans every dataset, recipe, step and benchmark, together with any `TARGET` given. |

`TARGET` is a reference such as `recipes/stepper-k2`. A plan that cannot be
built is still a plan: the exit status is 0 whether or not it can be built.
A target that is not a definition of the project exits with status 1 and the
message `There is no definition datasets/nothing.`; no target and no `--all`
is a usage error, status 2.

### Which definitions are in a plan

Starting from the targets, the plan follows these uses, again and again:

| Use | Followed |
| --- | --- |
| `input:<name>` | yes |
| `environment` | yes |
| `subject:<name>` | only when the subject's recipe is not blocked |
| `model`, `cases` | no; nothing is built for them |
| `benchmark` | a chart target is replaced by its benchmark |

A model or a chart is never a step. A model target adds nothing to the plan and
a sentence saying that a model is not built, only the recipes that train it.

Nothing is followed out of a blocked step: what it would use is not work anyone
can do. Its causes are still found over the whole graph and reported with it,
but they are not steps unless they are targets themselves. A skipped subject's
recipe is named under the benchmark's subjects and is not a step either. So a
plan lists every step that can and must be done, and each blocked target once.

### Steps and their actions

The steps are in build order, each after everything it uses (ties broken by
reference), numbered from 1. Each step has one action:

| Action | For |
| --- | --- |
| `set-up` | an environment (state `not-set-up`) |
| `build` | a dataset, recipe, step or benchmark in state `not-built` |
| `blocked` | a definition in state `cannot-rebuild` or `needs-work`, and a benchmark with no subject to run |

A blocked step is explained by its causes: the definitions whose own
`earlier_work.rebuild` is `no` or `needs-work`, among the step itself and
everything it reaches through inputs, directly or further up. A definition
that is blocked only because of what it uses is not a cause. At most five
causes are listed, nearest first (fewest inputs away, then by reference), with
a count of the rest.

A benchmark runs once per subject. A subject whose recipe is blocked is
skipped, with the reason; a subject with no recipe is run. The benchmark is
`build` when at least one subject would run. It is never blocked because one of
its subjects is; when no subject would run, it is `blocked` with no cause of
its own.

The plan can be built when no target is blocked. Blocked steps are listed but
not counted in the totals.

### Totals

The totals count `build` steps only:

- how many steps there are to build, and how many of them declare `gpu: true`;
- the sum of the declared `disk_gb`, and how many build steps declare none;
- the sum of the declared `wall_hours`, and how many build steps declare none.

### Text output

The text is one opening sentence (how many steps there are to build, to set up
and blocked, and whether the targets can be built), then one line per step with
its number, action, GPU (`yes` for `gpu: true`, otherwise `-`: a step that
does not declare `gpu` needs none), disk and time as declared (`?` when not
declared) and its reference. Under a step are what it uses (each input by name,
with the named output in brackets), the environment it runs in, a benchmark's
subjects, and for a blocked step what blocks it. Then come the causes of each
blocked target with their reasons, and the totals last.

```
$ .venv/bin/python -m tuldok_project plan FOLDER recipes/stepper-k2
4 steps to build, 1 to set up, 0 blocked: recipes/stepper-k2 can be built.

#  action  gpu  disk    time   reference
1  set-up  -    -       -      environments/lab-cpu
2  build   -    ?       0.1 h  steps/solver
                                 in environments/lab-cpu
3  build   -    ?       ?      datasets/waves
                                 solver: steps/solver (binary)
                                 in environments/lab-cpu
4  build   -    0.1 GB  0.5 h  recipes/stepper-k1
                                 training: datasets/waves
                                 in environments/lab-cpu
5  build   -    ?       ?      recipes/stepper-k2
                                 start: recipes/stepper-k1 (weights)
                                 training: datasets/waves
                                 in environments/lab-cpu

To build: 4 steps, 0 on a GPU.
Disk: 0.1 GB declared; 3 of 4 declare none.
Time: 0.6 h declared; 2 of 4 declare none.
Figures are as the definitions declare them; no command was run.
$ .venv/bin/python -m tuldok_project plan FOLDER recipes/early-fit
0 steps to build, 0 to set up, 1 blocked: recipes/early-fit cannot be built.

#  action   gpu  disk  time  reference
1  blocked  -    ?     ?     recipes/early-fit
                               blocked: its own label is rebuild no

recipes/early-fit cannot be built:
  no  recipes/early-fit
    Trained by the earlier study harness; its command and training data were
    not recorded.

Nothing would be built, so there are no totals.
```

### JSON output

With `--json`, `plan` prints one object:

| Field | Meaning |
| --- | --- |
| `targets` | the references planned, in the order given, with each chart replaced by its benchmark and repeats left out |
| `every` | true with `--all` |
| `buildable` | true when no target is blocked |
| `blocked_targets` | the targets that are blocked |
| `counts` | the number of steps of each action: `{"build", "set-up", "blocked"}` |
| `gpu_steps` | how many build steps declare `gpu: true` |
| `disk_gb`, `disk_unknown` | the sum of the declared `disk_gb` over build steps, and how many build steps declare none |
| `wall_hours`, `wall_unknown` | the same for `wall_hours` |
| `notes` | sentences about targets that are not built themselves: a model, or a chart replaced by its benchmark |
| `steps` | the steps in order |

Each step:

| Field | Meaning |
| --- | --- |
| `number` | its place in the order, from 1 |
| `reference`, `kind`, `title`, `state` | from the definition; the state as `list` shows it |
| `action` | `build`, `set-up` or `blocked` |
| `command`, `environment` | from `run`, placeholders not filled in; null when absent |
| `inputs` | each input name to `{"reference", "output"}`; `output` is null for a whole product |
| `resources` | `gpu`, `cpu_threads`, `memory_gb`, `wall_hours`, `disk_gb` as declared; null when not declared (a null `gpu` means no GPU is needed) |
| `estimate` | always null: no estimate command is run |
| `blocked_by` | for a blocked step, up to five causes, each `{"reference", "rebuild", "reason"}`; empty otherwise |
| `blocked_by_more` | how many more causes there are |
| `subjects` | benchmarks only: `run`, the subject names that would run, and `skipped`, each `{"name", "recipe", "reason"}` |

## What the format does not do yet

The folder is checked, can be opened, edited and saved through the database
copy, its results can be read and drawn, and a build can be planned, nothing more. Tuldok does not yet run any command,
estimate, install an environment, compare installed package versions, write
settings files or read the contents of notes. The `run`, `resources`,
`estimate`, `install` and `settings` fields record what a later Tuldok will use.

Background: [the design notes for this format](../plans/definition-first-projects/).
