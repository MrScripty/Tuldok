# Project folder format

Owner: the package `tuldok_project/` (`folder.py` reads the folder, `documents.py`
and `schemas/*.json` check single files, `check.py` applies every rule,
`results.py` owns summary files). The format names are `tuldok_project_v1` for
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
| `--json` | `open`, `list`, `show`, `graph`, `status`, `save` | Print one JSON document with the same content as the text. |
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

## What the format does not do yet

The folder is checked and can be opened, edited and saved through the database
copy, nothing more. Tuldok does not yet run any command,
estimate, install an environment, compare installed package versions, write
settings files, import results files or read the contents of notes. The `run`, `resources`,
`estimate`, `install` and `settings` fields record what a later Tuldok will use.

Background: [the design notes for this format](../plans/definition-first-projects/).
