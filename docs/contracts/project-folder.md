# Project folder format

Owner: the package `tuldok_project/` (`folder.py` reads the folder, `documents.py`
and `schemas/*.json` check single files, `check.py` applies every rule,
`results.py` owns summary files, `annotations.py` the files of annotations,
`store.py` and `result_rows.py` the database copy and its results, `charts.py` charts and the report page, `plan.py`
plans, `environments.py` environments, and `builds.py`, `launcher.py` and
`snapshot.py` building). The format names are `tuldok_project_v1` for
the folder and `tuldok_definition_v1` for each definition.

A project folder describes a piece of research as a set of small JSON files that
people and agents write and keep in Git. Each file is a **definition**: it says
what a dataset, model, training recipe, benchmark, build step, environment,
chart or annotation task is and, where something has to be produced, which
command produces it.
What a command writes is a **product**. Products stay on the machine that made
them; the folder holds only what someone wrote, plus benchmark summaries.

`python -m tuldok_project check FOLDER` tells you whether a folder is valid. This
document says exactly what the checker accepts.

## What belongs in the folder

Put in the folder: the definitions, the result summary of each benchmark
(`results/`), the annotations of each annotation task (`annotations/`), and
cards and notes written by people (`notes/`).

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
annotations/<name>.json
annotations/<name>.jsonl   the annotations of task <name>
results/<benchmark name>.csv
notes/...
```

- `tuldok.json` is required. Every other entry is optional.
- Any other top-level entry is an error. Move such files into `notes/` or out of
  the folder.
- The eight **definition directories** (`datasets/` to `annotations/`) hold only
  `<name>.json` files, one definition each, and no subdirectories.
  `annotations/` also holds `<name>.jsonl`, the annotations of the task in
  `<name>.json`, which must exist.
- `results/` holds only `<name>.csv` files.
- `notes/` holds plain files and directories to any depth. Their contents are not
  read.
- Every file is a regular file and every directory a real directory. A symbolic
  link anywhere in the folder, including under `notes/`, is an error.
- Size limits: `tuldok.json` 64 KiB, a definition 1 MiB, a results file 16 MiB,
  a file of annotations 64 MiB.

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
| `code_paths` | no | 1 to 64 paths relative to the code root, in normal form (no `..`, no empty or `.` parts, no trailing `/`), each listed once and each existing under the code root; default: the whole code root |
| `groups` | no | 0 to 200 objects, in the order their sections are shown on the map. Each: `id` (1 to 64 characters, `[A-Za-z0-9][A-Za-z0-9_.-]*`, each id once), `title` (1 to 200 characters), `parent` (optional: the `id` of another group; a group is never its own ancestor), `description` (optional, at most 2,000 characters); no other field |
| `map` | no | `{"chart": <reference to charts/>}`, no other field: a chart of the form `progression`, whose benchmark, metric and statistic are the map's track |

`code_paths` names the parts of the repository a run needs: a run sees a
read-only copy of only those paths at the commit it runs from, and only
changes to tracked files under them stop a run that is not a scratch run.

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
| `dataset` (annotation) | `datasets/` |

An **input** is what a command reads from another definition's product. It is
written either as a reference, meaning the whole product, or as
`{"from": <reference>, "output": <output name>}`, meaning one named output that the
other definition declares in its `run.outputs`.

## Fields common to every definition

| Field | Required | Rule |
| --- | --- | --- |
| `format` | yes | exactly `tuldok_definition_v1` |
| `kind` | yes | `dataset`, `model`, `recipe`, `benchmark`, `step`, `environment`, `chart` or `annotation`; must match the directory |
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

## The eight kinds

The examples below come from one project. References in them point at the other
examples, except `environments/cuda-torch`, a second environment not shown.

### `dataset`

| Field | Required | Rule |
| --- | --- | --- |
| `run` | unless `earlier_work.rebuild` is `no` | see the `run` block |
| `splits` | no | object, split name to a number of items (integer ≥ 0) |
| `view` | no | how its product is shown as records; see [Looking inside a product](#looking-inside-a-product) |

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
| `group` | no | the `id` of one of the project's `groups` in `tuldok.json`: the section of the map it is shown in |
| `change` | no | `training-policy`, `architecture`, `refinement` or `component`: the kind of change this model makes |
| `derived_from` | no | reference to another recipe in `recipes/`: the model this one was branched from. Never the recipe itself, and following `derived_from` never comes back to where it started |
| `compared_with` | no | at most 50 objects, each `recipe` (reference to another recipe, each once in the list), `explanation` (1 to 2,000 characters) and `excerpt` (optional, at most 2,000 characters); no other field |

The label `short`, when a recipe has it, is the text of its node on the map
(at most 16 characters are shown). `derived_from` and `compared_with` say how
recipes relate on the map; they are not inputs, so building never follows
them, and a comparison may run both ways.

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

### `annotation`

An annotation task says what is recorded about the records of one dataset
(see [Looking inside a product](#looking-inside-a-product) for records). Its
annotations are the lines of `annotations/<name>.jsonl` beside it. A task is
never built: it has no `run`, no product, and the state `none`. Planning a task
plans its dataset in its place.

| Field | Required | Rule |
| --- | --- | --- |
| `dataset` | yes | reference to `datasets/` |
| `task` | yes | `review`, `class`, `tags`, `text`, `boxes`, `spans` or `segments` |
| `vocabulary` | for `class`, `tags`, `boxes`, `spans` and `segments`; not allowed for `review` and `text` | 1 to 500 different **terms**, each 1 to 200 characters without control characters |

`earlier_work` is not allowed here. `card` is where the guide for the people
and agents who annotate is written.

What an annotation's `value` is, by task, and which records it may describe:

| Task | `value` | Records of kind |
| --- | --- | --- |
| `review` | always null; the state is the decision | any but `file` |
| `class` | one term | any but `file` |
| `tags` | a list of different terms, possibly empty | any but `file` |
| `text` | a string of at most 64 KiB in UTF-8: a caption, a transcript, a summary | any but `file` |
| `boxes` | a list of `{"term", "x", "y", "w", "h"}`, numbers in pixels of the image; `x` and `y` at least 0, `w` and `h` above 0, the box inside the image | `image` |
| `spans` | a list of `{"term", "start", "end"}`, whole numbers of characters (code points) of the text; 0 ≤ `start` < `end` ≤ the text's length | `text` |
| `segments` | a list of `{"term", "start", "end"}` with an optional `"text"` (a string of at most 64 KiB), numbers of seconds; 0 ≤ `start` < `end` ≤ the sound's length | `audio` |

A list holds at most 1,000 items, and an item no other key. The value may be
null in any state but `accepted`. The record's kind, an image's size, a text's
length and a sound's length are known only from the dataset's product, so the
folder check cannot apply those rules; Tuldok applies them when an annotation
is made.

Example, `annotations/scene-quality.json`:

```json
{
  "format": "tuldok_definition_v1",
  "kind": "annotation",
  "title": "Scene quality",
  "card": "notes/annotating/scene-quality.md",
  "dataset": "datasets/sinusoidal-v1",
  "task": "class",
  "vocabulary": ["clean", "noisy", "broken"]
}
```

#### The annotations file

`annotations/<name>.jsonl` holds the annotations of task `<name>`, one JSON
object per line, one line per record. A record with no line is not annotated.
The keys, in this order:

| Key | Required | Rule |
| --- | --- | --- |
| `record` | yes | the record's id: 1 to 600 characters, no control characters; each record once |
| `sha256` | yes | the SHA-256 of the record's content when it was annotated (64 lowercase hexadecimal characters), or null |
| `state` | yes | `draft`, `accepted`, `needs-work` or `rejected` |
| `value` | yes | as the task says, or null |
| `note` | no | a string of at most 4,000 characters |
| `by` | yes | `owner`, or `agent:` followed by 1 to 80 characters (the agent credential's name, cut) |
| `at` | yes | a real UTC time, `YYYY-MM-DDTHH:MM:SSZ` |
| `from` | no | an object of at most 2 KiB, written compact, saying what suggested the value; kept as it is |

The file is written in one exact form, so that Git shows one changed line per
changed annotation:

- lines sorted by `record`, comparing the bytes of its UTF-8;
- each line written compact (`,` and `:` with no spaces), with characters
  other than ASCII written as themselves rather than as `\u` escapes, the keys
  in the order above and the keys of a `boxes`, `spans` or `segments` item in
  the order of the table of tasks;
- each line ending with `\n`, the last one included.

A file with no line left is deleted when it is saved. The JSON rules above
apply to each line: no repeated key, no `NaN` or `Infinity`, and no escaped
half of a surrogate pair.

The check reads every line. A line that is not such an object, a value the task
does not allow, a record that an earlier line has, and a line whose record
does not sort after the one above it are errors; a term outside the
vocabulary is a warning, so that a term can be removed from a vocabulary
while annotations still use it. Each problem names its line (`line <n>`): the
first 20 of a file, then one problem counting the rest. A file of annotations
is not checked while its task has errors.

Example, `annotations/scene-quality.jsonl`:

```
{"record":"scene-0001","sha256":"9f2c0e5d1b8a7f6e5d4c3b2a19087f6e5d4c3b2a19087f6e5d4c3b2a19087f6e","state":"accepted","value":"clean","by":"owner","at":"2026-11-13T10:02:11Z"}
{"record":"scene-0002","sha256":null,"state":"rejected","value":null,"note":"blurry","by":"owner","at":"2026-11-13T10:02:40Z"}
{"record":"scene-0003","sha256":null,"state":"draft","value":"noisy","by":"agent:helper","at":"2026-11-13T10:05:02Z"}
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
   | an annotation task's `dataset` | `dataset` |

   Two more fields of a recipe are edges with a role, shown in a definition's
   uses and used-by, but are not uses in this sense: they may run both ways,
   carry no state, and the plan and the build order do not follow them.

   | Field | Role of the edge |
   | --- | --- |
   | a recipe's `derived_from` | `derived` |
   | a recipe's `compared_with[].recipe` | `compared` |

4. A chart's `metric`, `metric_x`, `subjects` and `group` exist in its benchmark.
5. Code paths exist under the code root (see the `run` block).
6. Every results file has its benchmark and follows the rules above. Every
   file of annotations has its task and follows the rules of its task.
7. A recipe's `group` is a group of `tuldok.json`; a group's `parent` is another
   group and no group is its own ancestor; a recipe is never derived from or
   compared with itself; following `derived_from` never comes back to where it
   started; `map.chart` is a chart of the form `progression`.

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
in a results file or a file of annotations), and one sentence. Text output prints one line per problem,
with the parts separated by two spaces and `-` for an empty pointer, sorted by
path and pointer, then a count:

```
error  recipes/pilot-dense-k1.json  /run/inputs/training  datasets/sinusoidal-v2 does not exist; add datasets/sinusoidal-v2.json or fix the reference.
warning  results/dense-development-240.csv  -  The results file does not end with a line end.
1 error, 1 warning in /home/me/lab/projects/surrogate-lab
```

With `--json` the object is `{"folder", "ok", "errors", "warnings", "problems"}`,
each problem being `{"severity", "path", "pointer", "message"}`.

These are warnings; every other problem is an error:

- a code path that does not exist, in a definition with `earlier_work`;
- a results file without a final line end;
- a results file that is not checked because its benchmark has errors;
- in a file of annotations: a term that is not in the task's vocabulary (one
  warning per term, saying how many annotations use it and on which lines), a
  blank line, a line not written in the exact form below, a missing final line
  end, and a file with no lines;
- a file of annotations that is not checked because its task has errors.

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
| `status` | Lists definitions edited or removed in the database and not yet saved, and definition files added, changed or missing on disk since the last import; and per annotation task, how many records have unsaved annotations, and the annotation files changed on disk. |
| `set REFERENCE FILE` | Replaces or adds the definition at `REFERENCE` with the text of `FILE`, in the database only. The text is checked on its own and against the rest of the project; an edit with any error is refused and changes nothing. |
| `remove REFERENCE` | Removes the definition in the database only. It is refused while another definition uses it, or while it is the chart `tuldok.json` names in `map.chart`. |
| `revert REFERENCE` | Undoes the unsaved edit or the removal of a definition, in the database only: the file in the folder takes its place again. A definition the folder has no file for is dropped instead (refused while another definition uses it). A file that no longer checks is refused, and a definition with neither an unsaved edit nor a removal has nothing to revert (exit status 1). |
| `branch RECIPE --title TITLE [--name NAME] [--change KIND] [--description TEXT] [--keep]` | Prints a new recipe branched from `RECIPE` (a bare name or `recipes/<name>`), as the operation `draft_branch` writes it: its reference, its problems in the form `check` prints them, and its text. Nothing is stored, unless `--keep` is given and the text has no error: then it is kept as an unsaved edit, as `set` keeps one. With `--keep` and an error, exit status 1. Here `--keep` keeps the branch; `branch` takes no `--keep` or `--discard` for a conflict. |
| `map` | Prints the project's map: per group in order, its title, how many models (recipes) it has and how many of each kind of change, then the models in no group and the totals, then how many lines (`derived_from`, and recipes used as inputs by recipes) and comparisons there are, and the track. Reads the database only, never a results file, values file or note. |
| `save` | Writes every unsaved definition to its file and deletes the files of removed ones, and writes the annotation file of each task with unsaved annotations. It writes nothing when one of those files changed on disk since it was imported, and names them. |
| `forget` | Drops the project's copy from the database, including unsaved edits. The folder is not touched. |

`note FOLDER PATH` prints one file under the folder's `notes/` directory,
`PATH` being relative to `notes/` (for example `fits/early-fit.md`). Like
`check`, it needs no database: it reads the folder on disk, refusing a path
not in normal form, a link anywhere on the way, a file that is not regular,
larger than 1 MiB or not UTF-8 (exit status 1).

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
| `running`, `built`, `out-of-date`, `failed` | a dataset, recipe, benchmark or step, by what was built on this machine (see [Build states](#build-states)) |
| `not-set-up`, `ready`, `failing` | an environment, by what this machine records for it (see [Environments](#environments)) |
| `none` | a model or a chart |

Options:

| Option | Commands | Meaning |
| --- | --- | --- |
| `--database-url URL` | all but `check` and `note` | The Postgres database. Without it, the `TULDOK_DATABASE_URL` environment variable is used; with neither, the command stops with exit status 2. |
| `--json` | `open`, `list`, `show`, `graph`, `map`, `status`, `revert`, `branch`, `save`, `results`, `values`, `import-values`, `chart`, `plan`, `environments`, `connect`, `check-environment`, `set-up`, `runs`, `run`, `progress`, `cancel`, `stop`, `products`, `estimate` | Print one JSON document with the same content as the text. |
| `--rebind` | all that open | The copy is bound to the folder it was first opened from. Opening the same project from another path is refused unless `--rebind` is given, which binds the copy to the new path. |
| `--keep` | all that open but `branch` | Where a file changed on disk and the same definition has unsaved edits, keep the edits; the changed file becomes the version that `save` replaces. |
| `--discard` | all that open but `branch` | Where a file changed on disk and the same definition has unsaved edits, drop the edits and take the file. |

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

## Annotations in the database

Annotations are edited in the database copy and written to the folder by
`save`, as definitions are. The copy holds one row per task and record: the
line's fields as they now are, the line as it is in `annotations/<name>.jsonl`
(or nothing, for an annotation made here and not yet saved), and whether the
row is unsaved. An annotation removed here and not yet saved keeps its row,
with no fields, until `save`.

**Opening** notices an annotation file that is new, changed or gone. Its size
and time are compared with those recorded at the last import or save, and
only a file whose size or time differs is read and its SHA-256 compared; a
file with the same content and a new time is not imported again. A changed
file is read line by line: each record whose line changed takes the file's
line. Where the record also has an unsaved annotation here, the project does
not open: the refusal is `conflict` and names `annotations/<name>.jsonl`, and
opening again with `--keep` (or `resolve_conflict` `keep`) keeps the
annotations here, the file's lines becoming the saved ones, while `--discard`
takes the file's lines. An annotation file that is gone forgets the saved
lines; an annotation with an unsaved change here stays, unsaved. A task
removed from the folder while it has unsaved annotations here is a
conflict too; it can only be discarded. A line holding the character U+0000
cannot be kept in the database and refuses the open `invalid`.

**`save`** writes, whole, the file of each task that has an unsaved row, from
all its annotations in the exact form of [The annotations file](#the-annotations-file)
(by a temporary file and a rename), and deletes it when the task has no
annotation left; it also deletes the file of a removed task. It writes nothing
when such a file changed on disk since it was imported, and names it
(`changed-on-disk`). After a save no annotation is unsaved, and each row's
saved line is the line written.

**`status`** gains `annotations_unsaved`, a list of `{task, records}` (the
task's reference and how many of its records have an unsaved change), and
`annotations_changed`, the paths of the annotation files added, changed or
removed on disk since the last import or save, by size and time. Neither reads
nor writes an annotation file.

A task with annotations cannot be removed (`in-use`, saying how many); remove
or revert its annotations first.

**The hash of a record's content** ties an annotation to what it describes:
SHA-256 of the record's file, of an archive member's bytes once decompressed,
or of the UTF-8 of an inline `text`. A record list may give it as `sha256`.
Otherwise Tuldok computes it when the record is first annotated, or first
looked at for an annotation, and keeps it for that run and record; a run's
product never changes, so it is computed once. A record over 1 GiB is not
hashed: its annotations carry null and are tied by id alone.

**Stale.** An annotation is stale when its dataset's current product has no
record of its id, or has one whose hash differs from the annotation's (an
annotation or a record without a hash is never stale by content). It is
worked out when asked, never stored, and only the records that have
annotations are hashed to find it. When the dataset has no product, nothing
is stale (`stale` is null). Stale annotations are kept, counted and shown;
Tuldok never drops one.

**Invalid.** An annotation is invalid when its value is not one the task as it
now is allows (its `task` or `vocabulary` changed since it was made). Each row
remembers the task it was last checked against, so counting reads no value
until the task changes.

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
definition's `estimate` command, and opens no file of the folder; it asks Git
what changed in the code only when something was built (see
[Build states](#build-states)). The figures in a plan are the ones each
definition declares in `run.resources`, and beside them the ones its estimate
command printed when `estimate` last ran it (see [Estimates](#estimates)).

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
| `set-up` | an environment in state `not-set-up`, or `failing` (the text says its last check failed) |
| `ready` | an environment in state `ready`; it is not counted as something to set up |
| `build` | a dataset, recipe, step or benchmark in state `not-built`, `out-of-date`, `failed` or `running` (the text says why under the step; `build` refuses a step that is running) |
| `built` | a dataset, recipe, step or benchmark in state `built`; it is not counted as work |
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
- the sum of the declared `wall_hours`, and how many build steps declare none;
- when any build step has an estimate, the sum of the estimated bytes and
  seconds, and how many build steps each sum covers. Declared and estimated
  figures are never added together.

### Text output

The text is one opening sentence (how many steps there are to build, to set up
and blocked, how many environments are ready when any is, and whether the
targets can be built), then one line per step with
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
| `counts` | the number of steps of each action: `{"build", "set-up", "blocked", "ready", "built"}` |
| `gpu_steps` | how many build steps declare `gpu: true` |
| `disk_gb`, `disk_unknown` | the sum of the declared `disk_gb` over build steps, and how many build steps declare none |
| `wall_hours`, `wall_unknown` | the same for `wall_hours` |
| `estimated_disk_gb`, `estimated_disk_steps` | the sum of the estimated `disk_bytes` over build steps, in units of 10^9 bytes, and how many build steps have one |
| `estimated_wall_hours`, `estimated_wall_steps` | the same for the estimated `wall_seconds`, in hours |
| `notes` | sentences about targets that are not built themselves: a model, or a chart replaced by its benchmark |
| `steps` | the steps in order |

Each step:

| Field | Meaning |
| --- | --- |
| `number` | its place in the order, from 1 |
| `reference`, `kind`, `title`, `state` | from the definition; the state as `list` shows it |
| `action` | `build`, `set-up`, `blocked`, `ready` or `built` |
| `command`, `environment` | from `run`, placeholders not filled in; null when absent |
| `inputs` | each input name to `{"reference", "output"}`; `output` is null for a whole product |
| `resources` | `gpu`, `cpu_threads`, `memory_gb`, `wall_hours`, `disk_gb` as declared; null when not declared (a null `gpu` means no GPU is needed) |
| `estimate` | the stored estimate, `{"disk_bytes", "wall_seconds", "items", "measured_at"}` with null for a figure the command did not print, while the definition's text is the one it was measured for; otherwise null |
| `reasons` | why a `build` step is out of date, failed or running; empty otherwise |
| `scratch` | true when the step's current product was made by a scratch run |
| `blocked_by` | for a blocked step, up to five causes, each `{"reference", "rebuild", "reason"}`; empty otherwise |
| `blocked_by_more` | how many more causes there are |
| `subjects` | benchmarks only: `run`, the subject names that would run, and `skipped`, each `{"name", "recipe", "reason"}` |

## Environments

An `environment` definition says what an interpreter must be: a Python
version, a device and exact package versions. Which interpreter fulfils it is
a fact about one machine, so it is never written to the folder. Tuldok records
it in the project's database schema, in the table `environments`, one row per
environment that has an interpreter on this machine:

| Column | Content |
| --- | --- |
| `name` | the environment's name, as in `environments/<name>` |
| `interpreter` | the absolute path of the Python executable, exactly as it was given |
| `origin` | `connected` (an existing interpreter was named) or `installed` (Tuldok installed it) |
| `recorded_at` | when the interpreter was recorded |
| `checked_at` | when it was last checked; null before the first check |
| `ok` | whether the last check passed |
| `found` | what the last check saw: the Python version, each package's installed version (null when not installed), the interpreter's own path, and for a `cuda` check what torch says about CUDA |
| `problems` | the sentences saying why the last check failed; empty when it passed |

Removing an environment definition, or deleting its file, drops its row. The
row never deletes an installed directory.

Environments that Tuldok installs live in the project's local home,
`<project directory>/<project id>/`, where the project directory is the one
[the setting](#the-project-directory-on-this-machine) names. An installed environment is the directory
`<local home>/environments/<name>/`, with its log beside it as
`<local home>/environments/<name>.log`. The local home is made the first time
something is installed.

### States

| State | When |
| --- | --- |
| `not-set-up` | no interpreter is recorded for the environment on this machine |
| `ready` | its last check passed |
| `failing` | its last check did not pass |

The state comes from the stored result of the last check. Opening a project
never runs a check, so `list`, `show`, `graph` and `plan` show what the last
check found, however long ago it ran; `check-environment` runs it again. No
other definition's state depends on an environment's. A change to an
environment definition does not change the stored result until the next check.

### The check

The check runs the recorded interpreter once, as a child process:

```
INTERPRETER -I -c PROBE '{"device": ..., "packages": {...}}'
```

The child gets an environment of `PATH=/usr/bin:/bin`, `LANG=C.UTF-8` and
`HOME` set to a new empty temporary directory, which is also its working
directory and is removed afterwards. It has 180 seconds. Its output is
captured and never shown as it is. No project code is involved.

The probe reads each package's installed version with `importlib.metadata`
and imports no package, with one exception: when the device is `cuda` and
`torch` is among the packages, it imports `torch` and reports whether CUDA is
available, the CUDA version, the first device's name and the first line of
`/proc/driver/nvidia/version` when that file exists. It works on Python 3.10
to 3.14 and prints one JSON object.

The check passes when all of these hold:

| Rule | A failure reads |
| --- | --- |
| the Python version's major.minor is the definition's `python` | `Python is 3.11.9; the definition asks for 3.12.` |
| every package is installed | `numpy is not installed; the definition asks for 2.3.5.` |
| every package's version is exactly the definition's | `jsonschema is 4.26.0; the definition asks for 4.25.0.` |
| for device `cuda`, `torch` is among the packages | `The device is cuda but torch is not among the packages, so the check cannot see the GPU.` |
| for device `cuda`, torch reports CUDA as available | `CUDA is not available to torch.` |

A probe that cannot be started, takes longer than 180 seconds, exits with an
error, or prints anything other than the expected object is a failed check
with one problem saying which, followed by the first 400 characters of its
error output. A failed check is recorded like any other result.

### Connect

`connect` records an existing interpreter, with origin `connected`, and then
checks it. The interpreter is named by an absolute path to an executable
file. A symbolic link is allowed, and the path is stored as given, not
resolved, so a virtual environment's `bin/python` stays that environment's.
The record is kept whether or not the check passes, so its problems can be
read with `environments`.

### Set-up

`set-up` installs the environment its definition describes, then records it
with origin `installed` and checks it. It needs the definition's
`install.requirements`; without it, the refusal says to connect an existing
interpreter instead. The installer is `uv`: the program named by the
`TULDOK_UV` environment variable, otherwise `uv` on `PATH`; with neither, it is
refused.

These two commands run in order, with the code root as the working directory
and up to one hour each:

```
uv venv --python PYTHON TARGET
uv pip install --python TARGET/bin/python -r CODE_ROOT/REQUIREMENTS [--extra-index-url URL]...
```

`TARGET` is `<local home>/environments/<name>`, `PYTHON` the definition's
`python`, `REQUIREMENTS` its `install.requirements`, and there is one
`--extra-index-url` for each of its `install.index_urls`. The output of both
goes to `TARGET.log`, which is replaced each time.

| Option | Meaning |
| --- | --- |
| `--dry-run` | Prints each command on its own line as it would be run, then the target and the log path. Nothing is made and nothing is run. |
| `--replace` | A target that exists and is not empty is refused without this option; with it, the target is removed first. |

When a command fails or runs out of time, the half-made target is removed,
the log is kept, nothing is recorded, and the refusal ends with the last lines
of the log. Any record the environment had before is left as it was; when
that record was the installed target that `--replace` removed, its next check
fails.

### Disconnect

`disconnect` removes the record, so the environment is `not-set-up` again. It
never deletes an installed directory; when the origin was `installed` it
prints that directory's path, to delete by hand when it is no longer needed.

### Commands

| Command | Does |
| --- | --- |
| `environments` | Prints one row per environment: reference, state, origin, when it was last checked and the interpreter; under it the versions the last check found (with what the definition asks for where they differ) and its problems, or how to set it up. A closing line says how many are ready. |
| `connect ENVIRONMENT INTERPRETER` | Records and checks an existing interpreter. Exit status 1 when the check fails. |
| `check-environment [ENVIRONMENT...]` | Checks the named environments again, or every recorded one when none is named. Exit status 1 when any fails, or when a named one is not set up. |
| `set-up ENVIRONMENT [--dry-run] [--replace]` | Installs, records and checks the environment, or with `--dry-run` prints what it would run. Exit status 1 when it is refused, a command fails, or the check fails. |
| `disconnect ENVIRONMENT` | Removes the record. |

An environment may be named bare (`lab-cpu`) or as a reference
(`environments/lab-cpu`). `--json` prints one JSON document for
`environments`, `connect`, `check-environment` and `set-up`; each environment
in it has the definition's `python`, `device` and `packages`, whether it has
an install section (`installable`), its `state`, and the record's columns
(null when there is no record).

In these examples `FOLDER` is a copy of the test project whose `lab-cpu`
asks for `jsonschema` and is connected to Tuldok's own `.venv/bin/python`.
Long paths are shortened: `VENV` is that `.venv`, `CODE` the code root,
`LOCAL` the project's local home and `UV` the `uv` found on `PATH`.

```
$ .venv/bin/python -m tuldok_project environments FOLDER
environment           state       origin  last check  interpreter
environments/lab-cpu  not-set-up  -       -           -
    not set up on this machine; run set-up or connect an interpreter

0 of 1 environment ready on this machine.
$ .venv/bin/python -m tuldok_project set-up FOLDER lab-cpu --dry-run
Would set up environments/lab-cpu by running, in CODE:
UV venv --python 3.12 LOCAL/environments/lab-cpu
UV pip install --python LOCAL/environments/lab-cpu/bin/python -r CODE/requirements.txt --extra-index-url https://pypi.org/simple
target  LOCAL/environments/lab-cpu
log     LOCAL/environments/lab-cpu.log
Nothing was run.
$ .venv/bin/python -m tuldok_project connect FOLDER lab-cpu VENV/bin/python
Recorded VENV/bin/python for environments/lab-cpu.
environments/lab-cpu is ready: the check passed.
  python 3.12.3 (asks 3.12)
  jsonschema 4.26.0
$ .venv/bin/python -m tuldok_project environments FOLDER
environment           state  origin     last check        interpreter
environments/lab-cpu  ready  connected  2026-11-12 00:31  VENV/bin/python
    python 3.12.3 (asks 3.12)
    jsonschema 4.26.0

1 of 1 environment ready on this machine.
```

A path with spaces or other characters the shell would split is quoted in
`--dry-run`'s commands, so a line can be pasted into a shell as it is. When
the check fails, `connect` exits with status 1 and the plan sets the
environment up again:

```
$ .venv/bin/python -m tuldok_project connect FOLDER lab-cpu VENV/bin/python
Recorded VENV/bin/python for environments/lab-cpu.
environments/lab-cpu is failing: the check found 1 problem.
  python 3.12.3 (asks 3.12)
  jsonschema 4.26.0 (asks 4.25.0)
  problem: jsonschema is 4.26.0; the definition asks for 4.25.0.
$ .venv/bin/python -m tuldok_project plan FOLDER steps/solver
1 step to build, 1 to set up, 0 blocked: steps/solver can be built.

#  action  gpu  disk  time   reference
1  set-up  -    -     -      environments/lab-cpu
                               its last check failed; see environments
2  build   -    ?     0.1 h  steps/solver
                               in environments/lab-cpu
...
```

With the environment ready, the same plan begins
`1 step to build, 0 to set up, 0 blocked, 1 ready: steps/solver can be built.`
and the environment's line has the action `ready`.

## Building

`build` runs the commands of a plan on this machine and records what they
made. What a command writes is a **product**; it stays on this machine, in the
project's local home, and is never written to the folder. Each command that is
started is a **run**, recorded in the project's database schema with its
state, its command line, the code and inputs it used and how it ended.

### What a build does

1. It makes the plan for its targets, as `plan` does, and prints it.
2. It refuses the plan, before asking anything, when a target is blocked or
   when another build is running one of its steps.
3. When something is to be built, it prepares the code the runs will see (see
   below). A tree with uncommitted changes is refused here.
4. It asks `Build this? [y/N]`, unless `--yes` is given or nothing is to be
   built. Any answer but `y` or `yes` builds nothing.
5. It records the plan, then takes the steps in order:
   - an environment that a step to build runs in is checked again, once per
     build; one that is not ready stops the build, with a message saying to
     set it up or connect an interpreter;
   - a step whose action is `built` is skipped;
   - a step whose action is `build` is run, once for each subject of a
     benchmark that would run and is not built already.
6. For each run, it fills the placeholders, records the run with state
   `running`, and runs the command. The project is closed while the command
   runs, so `list`, `plan`, `runs`, `run`, `progress` and the other commands
   work during a build; `build` waits up to a minute when another command has
   the project open.
7. When the command ends with exit status 0, every declared output must exist
   under the output directory, and a benchmark's results are imported. Then
   the output directory becomes the definition's current product (one per
   subject for a benchmark).
8. A run that does not succeed stops the build. Later steps are not run.

A step whose command cannot even be started (a program that is not found, an
input with no current product, a settings file that cannot be read) is
recorded as a `failed` run with the reason, and its run directory is not made.

### The code a run sees

The code root must be inside a Git work tree. A run uses the commit that
`HEAD` names, and the tree is **clean** when no tracked file under the code
paths (`code_paths` in `tuldok.json`, or the whole code root) differs from that
commit, staged or not. Untracked files do not count. A tree that is not clean
is refused, naming up to ten changed files.

For a clean tree, the run sees a read-only copy of the commit, the
**snapshot**, made once with `git archive` and shared by every run at that
commit:

| Code | Snapshot directory |
| --- | --- |
| the whole code root | `<local home>/code/<commit>/` |
| `code_paths` | `<local home>/code/<commit>-<digest>/`, where the digest is the first 12 hexadecimal characters of the SHA-256 of the sorted paths, one per line |

The snapshot keeps the repository's layout, so the command's working
directory is the code root's place inside it. A settings file named by
`settings_file` is read from the snapshot too.

A **scratch** run, asked for with `--scratch`, uses the code root in place,
uncommitted changes included, and is allowed outside Git. It records the
commit when there is one. Its product is marked as a scratch product and never
becomes out of date because of the code.

### The run directory

Each run has its own directory, `<local home>/runs/<run id>/`, where the run id
is 32 hexadecimal characters:

| Entry | Content |
| --- | --- |
| `output/` | what `{output}` names, made empty before the command starts; a succeeded run's `output/` is its product |
| `settings.json` | the inline `settings` as the run saw them, when the definition has them |
| `stdout.log`, `stderr.log` | the command's standard output and error |
| `cancel` | present when cancellation was asked for |
| `outcome.json` | how the command ended, written when every process of the run is gone |

A product stays where its run wrote it. A newer product of the same definition
(and subject) becomes the current one and the earlier one is kept, no longer
current. Tuldok deletes no run directory and no product. Removing a definition
drops its runs, products and estimate from the database and leaves the
directories on disk.

### The command and its environment

The command is `run.command` with its placeholders filled. When its first word
is `python`, it is the interpreter recorded for the run's environment. A first
word containing `/` is an executable file under the code root. Any other first
word is looked up on `PATH`.

The command's environment holds exactly these variables, later ones replacing
earlier ones:

1. `PATH`, `HOME`, `USER`, `LOGNAME`, `LANG`, `LC_ALL` and `TZ`, from `build`'s
   own environment where they are set;
2. `PYTHONDONTWRITEBYTECODE=1` and `PYTHONUNBUFFERED=1`;
3. `CUDA_VISIBLE_DEVICES` set to the empty string, unless the step declares
   `gpu: true`, in which case it is passed on as `build` has it (and left
   unset when `build` has none);
4. the definition's `env`, with its placeholders filled;
5. every `--env NAME=VALUE` given to `build`;
6. `TULDOK_RUN_ID`, the run id. Every process the command starts inherits it,
   which is how Tuldok finds anything a run left behind.

The working directory is the code root in the snapshot (or the code root
itself for a scratch run). Standard input is `/dev/null`; standard output and
error are appended to the two logs.

### Placeholders at run time

| Placeholder | Filled with |
| --- | --- |
| `{output}` | `<run directory>/output` |
| `{settings}` | `<run directory>/settings.json` for inline `settings`; the settings file's path in the snapshot for `settings_file` |
| `{inputs.<name>}` | the input's current product directory; for `{"from", "output"}`, the path of that output inside it |
| `{subject.name}` | the subject's name |
| `{subject}` | the subject's `argument`, with `{recipe}` replaced by the current product directory of the subject's recipe; the subject's name when it has no `argument` |

An input or a subject's recipe with no current product fails the run before it
starts; the plan puts what it needs earlier, so this happens only when that
earlier step was not built.

### Limits

| Limit | From | Default |
| --- | --- | --- |
| wall time | `resources.wall_hours` | 24 hours |
| disk | `resources.disk_gb`, in units of 10^9 bytes, for the whole run directory | 50 GB |

The wall time is looked at every half second and the size of the run
directory every five seconds, and once more when the command has ended. A
run past either limit, a run whose `cancel` file appears, and a run whose
`build` receives `SIGINT` (Ctrl-C) or `SIGTERM` is stopped: `SIGTERM` to every
process of the run, up to ten seconds of grace, then `SIGKILL`. After the
command has ended, however it ended, every process of this user that still
carries the run's `TULDOK_RUN_ID` is killed; such a process does not change a
zero exit status into a failure, but the count is recorded as the run's
strays.

### The GPU lock

A step that declares `gpu: true` holds an exclusive lock on
`<project directory>/gpu.lock` while its command runs. The lock is shared by
every project on this machine, so two GPU steps never run at the same time; a
build that finds the lock taken waits for it. Steps without `gpu: true` take no
lock.

### Results published by a benchmark

A benchmark's output with role `results` must be a values file (see
[Values files](#values-files)) for that benchmark and the subject that was
run. After the command succeeds, the file is checked and imported, replacing
that subject's values and summary rows in the database. A file that fails the
check makes the run `failed`; its problem names the first five problems, and
nothing is imported. `save` writes the new summaries to `results/` like any
others.

### Run states

| State | Meaning |
| --- | --- |
| `queued` | recorded and not started yet |
| `running` | its command is running |
| `succeeded` | exit status 0, every declared output written, and a benchmark's results imported |
| `failed` | a non-zero exit status, a missing output, a refused results file, or a command that could not be started |
| `timed-out` | stopped at its wall-time limit |
| `over-disk` | stopped at, or ended over, its disk limit |
| `cancelled` | stopped because cancellation was asked for, with `cancel` or by a signal to `build` |
| `unknown` | how it ended is not known: its build is gone, or a process of the run could not be stopped |
| `adopted` | nothing was run: `adopt` made files made elsewhere its product (see [Adopting existing files](#adopting-existing-files)) |

### Build states

What was built gives datasets, recipes, steps and benchmarks four more states,
in the place of `not-built`:

| State | When |
| --- | --- |
| `running` | it has a `queued` or `running` run |
| `built` | it has a current product and nothing makes it out of date |
| `out-of-date` | it has a current product, and one of the causes below holds |
| `failed` | it has no current product, and its latest run ended `failed`, `timed-out`, `over-disk` or `unknown` |

A current product is **out of date** when:

- the definition's text differs from the text its run used;
- its `settings_file` reads differently now from what the run used;
- an input, or a benchmark subject's recipe, has a different current product
  than the one the run used, or none, or is itself out of date;
- the run was not a scratch run, and one of the definition's `sources` (or a
  file under one) changed since the run's commit: in a later commit or as an
  uncommitted change to a tracked file. When Git no longer has that commit,
  the code is taken to have changed.

A benchmark has a product per subject. It is `built` when every subject that
would run has a current product that is not out of date, and `out-of-date`
when one of them is out of date or only some have a product. When none has a
product it is `not-built`, or `failed` when its latest run ended badly. A product built by a scratch run is `built`, and
`plan` notes that it is a scratch product. A definition with a current product
is `built` or `out-of-date` even when its label would make it
`cannot-rebuild` or `needs-work`; those take precedence only when there is no
current product. A `cancelled` run never makes a definition `failed`, and a
definition with a current product keeps it. A definition whose current
product was adopted is `built` and never out of date: none of the causes above
is looked at.

In a plan, `built` is the action `built` and is not counted as work;
`out-of-date`, `failed` and `running` are `build`, and the plan says why under
the step. A step another build is running is refused by `build`.

### When a builder dies

A run is watched by a small custodian process that `build` starts for each
command. When `build` dies, even by `SIGKILL`, the custodian notices, stops
the run and kills every process that carries its run id. Its row in the
database still says `running`. The next time builds are looked at (`list`,
`plan`, `runs`, `run` and the others), a `queued` or `running` run whose build
process is not running on this boot becomes `unknown`, with a problem saying
so. It is never restarted; build again to make the product.

`stop` is for a run whose build is gone: it kills every process of this user
that carries the run's id, whatever is left after the custodian, and marks the
run `unknown` when it was still `queued` or `running`. It is refused while the
run's build is alive; use `cancel` for that.

### Commands

| Command | Does |
| --- | --- |
| `build TARGET... [--all] [--scratch] [--yes] [--env NAME=VALUE]...` | Prints the plan, asks to proceed unless `--yes`, and runs it. Prints a line when each run starts and ends, with the run id, and a closing line. |
| `runs [REFERENCE]` | The runs, newest first: run id, reference, subject, state, when it started and how long it took. |
| `run RUN` | One run: its row (state, plan, code, environment, command, directory, build process, times, exit status, seconds, size, strays), what it used, its product and outputs when it made one, its last progress event and its problem. |
| `progress RUN [--follow]` | The run's state, its last progress event and the last 8 KiB of each log. `--follow` looks again every two seconds and prints what is new, until the run is no longer `queued` or `running`. |
| `cancel RUN` | Asks a `queued` or `running` run to stop by creating its `cancel` file. The build running it stops it within a second or so and records it as `cancelled`; `cancel` does not wait. |
| `stop RUN` | For a run whose build is gone: kills the processes it left and marks it `unknown`. |
| `products [REFERENCE]` | The current products: reference, subject, run id, size of the declared outputs, whether a scratch run made it, and the directory. |
| `estimate TARGET... [--all] [--scratch] [--env NAME=VALUE]...` | Runs the estimate commands of the steps the plan would build and stores what they print (see [Estimates](#estimates)). |

`RUN` is a run id or a prefix of at least six of its characters that no other
run's id starts with. A prefix that matches several runs is refused, and the
matching runs are listed. `run`, `progress`, `cancel` and `stop` open the
project only for a moment to find the run, waiting while a build has it open,
and read the logs with the project closed, so they work while another process
builds. `progress --follow` does not hold the project open between passes.

Options:

| Option | Commands | Meaning |
| --- | --- | --- |
| `--all` | `build`, `estimate` | every dataset, recipe, step and benchmark, together with any `TARGET` given |
| `--scratch` | `build`, `estimate` | run from the code root as it is, uncommitted changes included |
| `--yes` | `build` | do not ask for confirmation |
| `--env NAME=VALUE` | `build`, `estimate` | add a variable to every command's environment; may be repeated |
| `--follow` | `progress` | repeat until the run ends |
| `--json` | `runs`, `run`, `progress`, `cancel`, `stop`, `products`, `estimate` | print one JSON document; `progress --follow --json` prints one JSON object per line, one per pass |

Exit statuses:

| Command | 0 | 1 |
| --- | --- | --- |
| `build` | every step succeeded or was built already | refused (a blocked target, a step being built elsewhere, uncommitted changes, an environment that is not ready), not confirmed, or a run did not succeed |
| `run`, `progress`, `runs`, `products` | shown | no such run, or a prefix that matches several |
| `cancel` | the `cancel` file was made, or was there already | the run is not `queued` or `running`, or no such run |
| `stop` | nothing of the run is left running | its build is alive, a process could not be stopped, or no such run |
| `estimate` | every estimate that ran was measured | an estimate failed, or the code was refused |

Every command exits with status 2 on a usage error, such as `build` or
`estimate` without a target or an `--env` that is not `NAME=VALUE`.

In these examples `FOLDER` is a committed copy of Tuldok's test project
`tests/fixtures/tuldok_project/buildable`, whose environment is connected to
Tuldok's own `.venv/bin/python`. `LOCAL` is the project's local home and
`VENV` that `.venv`.

```
$ .venv/bin/python -m tuldok_project build FOLDER benchmarks/score --yes
3 steps to build, 0 to set up, 0 blocked, 1 ready: benchmarks/score can be
built.

#  action  gpu  disk     time    reference
1  ready   -    -        -       environments/test-python
2  build   -    0.01 GB  0.05 h  datasets/numbers
                                   in environments/test-python
3  build   -    ?        ?       recipes/fit-a
                                   data: datasets/numbers (data)
                                   in environments/test-python
4  build   -    ?        ?       benchmarks/score
                                   data: datasets/numbers (data)
                                   in environments/test-python
                                   runs 2 subjects

To build: 3 steps, 0 on a GPU.
Disk: 0.01 GB declared; 2 of 3 declare none.
Time: 0.05 h declared; 2 of 3 declare none.
Figures are as the definitions declare them; no command was run.
start  datasets/numbers  run 8064e90ac31441bfb72ae1a892fde0b8
end    datasets/numbers  run 8064e90ac31441bfb72ae1a892fde0b8  succeeded  0.0 s
start  recipes/fit-a  run a14415f556a645d8aa209af956504b82
end    recipes/fit-a  run a14415f556a645d8aa209af956504b82  succeeded  0.0 s
start  benchmarks/score fit-a  run aeef824dfaad4c9eb0d95bc684738444
end    benchmarks/score fit-a  run aeef824dfaad4c9eb0d95bc684738444  succeeded  0.0 s
start  benchmarks/score zero  run 9916ff56c61e471b840157155b4bdf83
end    benchmarks/score zero  run 9916ff56c61e471b840157155b4bdf83  succeeded  0.0 s
Done: 4 runs succeeded, 0 already built.
$ .venv/bin/python -m tuldok_project runs FOLDER
run                               reference         subject  state      started           seconds
9916ff56c61e471b840157155b4bdf83  benchmarks/score  zero     succeeded  2026-11-12 01:26  0.0 s
aeef824dfaad4c9eb0d95bc684738444  benchmarks/score  fit-a    succeeded  2026-11-12 01:26  0.0 s
a14415f556a645d8aa209af956504b82  recipes/fit-a     -        succeeded  2026-11-12 01:26  0.0 s
8064e90ac31441bfb72ae1a892fde0b8  datasets/numbers  -        succeeded  2026-11-12 01:26  0.0 s
$ .venv/bin/python -m tuldok_project products FOLDER
reference         subject  run                               size   scratch  directory
benchmarks/score  fit-a    aeef824dfaad4c9eb0d95bc684738444  955 B  -        LOCAL/runs/aeef824dfaad4c9eb0d95bc684738444/output
benchmarks/score  zero     9916ff56c61e471b840157155b4bdf83  910 B  -        LOCAL/runs/9916ff56c61e471b840157155b4bdf83/output
datasets/numbers  -        8064e90ac31441bfb72ae1a892fde0b8  74 B   -        LOCAL/runs/8064e90ac31441bfb72ae1a892fde0b8/output
recipes/fit-a     -        a14415f556a645d8aa209af956504b82  66 B   -        LOCAL/runs/a14415f556a645d8aa209af956504b82/output
$ .venv/bin/python -m tuldok_project run FOLDER a14415
run             a14415f556a645d8aa209af956504b82
reference       recipes/fit-a
subject         -
state           succeeded
plan            e7bf709a3f2f44b9a743401873dc34ae
code            commit 51eb0263cdd0, from its snapshot
environment     environments/test-python  VENV/bin/python
command         VENV/bin/python train.py --data LOCAL/runs/8064e90ac31441bfb72ae1a892fde0b8/output/numbers.json --settings LOCAL/code/51eb0263cdd0954fd47e700e718043887939d6c7/code/settings/fit-a.json --out LOCAL/runs/a14415f556a645d8aa209af956504b82/output
directory       LOCAL/runs/a14415f556a645d8aa209af956504b82
builder         process 1362748
queued          2026-11-12 01:26:54
started         2026-11-12 01:26:54
finished        2026-11-12 01:26:54
exit status     0
seconds         0.0 s
size            532 B
strays          0
input data      datasets/numbers (data), run 8064e90ac31441bfb72ae1a892fde0b8
product         LOCAL/runs/a14415f556a645d8aa209af956504b82/output
output weights  weights.json  weights  66 B
progress        fit 4 of 4 (100%)  guess=-0.1727
$ .venv/bin/python -m tuldok_project progress FOLDER a14415
run        a14415f556a645d8aa209af956504b82
reference  recipes/fit-a
state      succeeded
progress   fit 4 of 4 (100%)  guess=-0.1727
stdout.log: 466 B:
  {"format": "tuldok_progress_v1", "stage": "fit", "completed": 1, "total": 4, "metrics": {"guess": -0.09211366666666666}}
  {"format": "tuldok_progress_v1", "stage": "fit", "completed": 2, "total": 4, "metrics": {"guess": -0.1381705}}
  {"format": "tuldok_progress_v1", "stage": "fit", "completed": 3, "total": 4, "metrics": {"guess": -0.16119891666666666}}
  {"format": "tuldok_progress_v1", "stage": "fit", "completed": 4, "total": 4, "metrics": {"guess": -0.172713125}}
stderr.log: empty
```

The command line in `run` is quoted so it can be pasted into a shell. The
progress event is the last complete line of standard output, within the last
8 KiB, that is exactly one JSON object of this form, at most 4,096 bytes:

```json
{"format": "tuldok_progress_v1", "stage": "fit", "completed": 3, "total": 4, "metrics": {"guess": -0.16}}
```

`stage` and each metric name match `[A-Za-z0-9][A-Za-z0-9_.-]{0,63}`;
`completed` and `total` are whole numbers with `0 <= completed <= total <=
1000000`; `metrics` holds up to eight finite numbers. Any other line is just
output. Invalid bytes in a log are shown replaced, and control characters
other than tab and newline are left out.
`run --json` prints every column of the run's row, including the definition
text and the environment it ran with, plus `product`, `builder_alive` and
`event`.

While a build runs in another terminal, `progress --follow` prints the run's
first line, then each new line of the logs as it is written (`out` for
standard output, `err` for standard error), a `progress` line when the event
changes, and a last line when the run ends:

```
$ .venv/bin/python -m tuldok_project progress FOLDER 3b4a4509 --follow
run 3b4a45097c0f44b3a651763d599289aa  recipes/fit-a  running
out  {"format": "tuldok_progress_v1", "stage": "fit", "completed": 1, "total": 4, "metrics": {"guess": -0.09211366666666666}}
out  {"format": "tuldok_progress_v1", "stage": "fit", "completed": 2, "total": 4, "metrics": {"guess": -0.1381705}}
out  {"format": "tuldok_progress_v1", "stage": "fit", "completed": 3, "total": 4, "metrics": {"guess": -0.16119891666666666}}
out  {"format": "tuldok_progress_v1", "stage": "fit", "completed": 4, "total": 4, "metrics": {"guess": -0.172713125}}
progress  fit 4 of 4 (100%)  guess=-0.1727
Run 3b4a45097c0f44b3a651763d599289aa ended succeeded after 4.3 s.
$ .venv/bin/python -m tuldok_project stop FOLDER 3b4a4509
Run 3b4a45097c0f44b3a651763d599289aa (recipes/fit-a) is still being run by its build (process 1365836); use cancel to stop it.
```

(`stop` above was run while the build was still going.) Cancelling a running
build, and what the build prints:

```
$ .venv/bin/python -m tuldok_project cancel FOLDER 4cc81737
Asked run 4cc81737b8b04686942a24d60e39c9bc (recipes/fit-a) to stop: its build stops it within a second or so and records it as cancelled.
```

```
start  recipes/fit-a  run 4cc81737b8b04686942a24d60e39c9bc
end    recipes/fit-a  run 4cc81737b8b04686942a24d60e39c9bc  cancelled  1.1 s
       It was cancelled.
Stopped: recipes/fit-a did not succeed; later steps were not run.
```

```
$ .venv/bin/python -m tuldok_project cancel FOLDER 4cc81737
Run 4cc81737b8b04686942a24d60e39c9bc (recipes/fit-a) is cancelled; only a queued or running run can be cancelled.
```

After the build running `48856079` was killed with `SIGKILL`:

```
$ .venv/bin/python -m tuldok_project stop FOLDER 48856079
No process of the run was left running: run 48856079a1694a8391a8083fafe7fbb1 (recipes/fit-a).
It was running; it is now unknown, and is never restarted.
```

### Estimates

A definition's `run.estimate.command` says how big and how long its build will
be without doing it. `estimate` runs it; `plan` and `build` never do, because
it is project code. For each step the plan would build:

- a step without an estimate command is skipped;
- the estimate command runs from the same code as a build (a clean commit's
  snapshot, or the code root with `--scratch`), with the child environment and
  working directory a build step gets, in a throwaway directory
  `<local home>/estimates/<id>/` that is removed afterwards;
- `{output}` names a path that does not exist, `{settings}` and
  `{inputs.<name>}` are filled as for a build, and `{subject}` and
  `{subject.name}` cannot be used, since an estimate is made once per
  definition;
- a step whose estimate command or `env` names an input with no current
  product is skipped, with that reason;
- the command has five minutes and may write 100 MB (10^8 bytes) in its
  directory; it takes no GPU lock.

The command's standard output must be exactly one JSON object, at most 64 KiB,
with any of these fields; other fields are ignored:

| Field | Meaning |
| --- | --- |
| `disk_bytes` | how many bytes the build will write |
| `wall_seconds` | how many seconds the build will take |
| `items` | how many items it will make or read, for example cases or examples |

Each one present must be a number of at least 0, and at least one must be
present. A command that fails, runs out of time, prints anything else or a
value of the wrong kind is a failed estimate for that step, reported with the
reason; the other steps still run, and an earlier estimate of that step is
kept. A measured estimate replaces the step's earlier one.

An estimate is stored in the database with the SHA-256 of the definition's
text it was measured for, and `plan` shows it only while the definition's text
is that one. In the text of a plan, the declared figure comes first and the
estimate follows it marked `~... est.`; the totals keep the declared sums and
add a line with the estimated sums, saying how many steps they cover.

```
$ .venv/bin/python -m tuldok_project estimate FOLDER recipes/fit-a
Ran from the code at commit 51eb0263cdd0.

step              estimate  disk  time  items
datasets/numbers  skipped   -     -     -
  It has no estimate command.
recipes/fit-a     skipped   -     -     -
  It needs {inputs.data}, but its input data (datasets/numbers) has no current
  product.

0 measured, 2 skipped, 0 failed. plan shows each estimate while its definition is unchanged.
```

Once `datasets/numbers` is built and `recipes/fit-a` declares
`wall_hours: 0.1`:

```
$ .venv/bin/python -m tuldok_project estimate FOLDER recipes/fit-a
Ran from the code at commit 060271be67fe.

step           estimate  disk    time  items
recipes/fit-a  measured  4.8 KB  2 s   6

1 measured, 0 skipped, 0 failed. plan shows each estimate while its definition is unchanged.
$ .venv/bin/python -m tuldok_project plan FOLDER benchmarks/score
2 steps to build, 0 to set up, 0 blocked, 1 ready, 1 built: benchmarks/score
can be built.

#  action  gpu  disk            time             reference
1  ready   -    -               -                environments/test-python
2  built   -    0.01 GB         0.05 h           datasets/numbers
                                                   in environments/test-python
3  build   -    ? ~4.8 KB est.  0.1 h ~2 s est.  recipes/fit-a
                                                   data: datasets/numbers (data)
                                                   in environments/test-python
                                                   out of date: its definition changed since run a14415f556a6
4  build   -    ?               ?                benchmarks/score
                                                   data: datasets/numbers (data)
                                                   in environments/test-python
                                                   runs 2 subjects
                                                   out of date: subject fit-a: the recipe recipes/fit-a of its subject is out of date

To build: 2 steps, 0 on a GPU.
Disk: no step declares it.
Time: 0.1 h declared; 1 of 2 declares none.
Estimated: disk ~4.8 KB (1 of 2 steps); time ~2 s (1 of 2 steps).
Declared figures are as the definitions declare them; figures marked est. are
what their estimate commands printed when estimate last ran them. No command
was run now.
```

A measured time reads in seconds below 100 s, in minutes below 100 minutes,
and in hours above that. With `--json`, `estimate` prints `{"targets",
"scratch", "commit", "steps"}`, each step `{"reference", "result"`
(`measured`, `skipped` or `failed`), `"reason", "values", "seconds"}`.

## Serving a project

The Tuldok app can serve one project folder to its owner and to agents:

```
python app.py --data CATALOG --project-folder FOLDER
```

`--data` names the catalog directory, which holds the credentials; the
database is the one `TULDOK_DATABASE_URL` names. One app serves one folder and
nothing else: `--project-folder` cannot be combined with `--project-root`.
A folder that does not open stops start-up with the message and its first problems, exit
status 2. The app opens the project only for each operation, as the commands
do, so files changed on disk are imported before an operation answers and
the command line keeps working beside the app.

The page at `/` is the Map workspace: the tabs Map, Data, Train, Benchmarks,
Analysis and Overview over the project, read through the operations below.
Each of its controls calls one operation and is drawn only for a session that
may call it, so a credential that may only inspect sees a page that changes
nothing. The report is linked from the Overview tab. The page reads again
every two seconds while a build is queued or running and every fifteen
seconds otherwise, when its window regains focus, and after a control's
answer: it asks again for `summary`, `status`, `build_requests`,
`environments` and `runs` (and `map`, except on the timer unless a run or a
request ended or `status` changed) and compares each answer with the one it
holds. When none differs nothing on the page is drawn again but the time it
was read and the progress of a running build; when one does, what is on screen is drawn again in place, keeping
the scroll and the focus, and a drawer holding the editor or the branch form
is left alone except after a control's answer. A reading that fails leaves
the page as it is; the status strip says the project was not read, and why.

### Signing in and issuing an agent credential

The owner makes a one-time code and enters it in the page's sign-in bar:

```
python access.py login --data CATALOG --out /private/owner-code
```

(`bootstrap` instead of `login` the first time a catalog has no owner.) Signed
in, the owner issues an agent credential with `POST /api/access/credentials`
and the body `{"label": ..., "scopes": [...], "ttl_seconds": ...}` (60 seconds
to 30 days, one hour by default). The answer holds the token once; keep it
in a file only the agent's user can read. An agent credential must include
`inspect`, may include `edit`, `execute` and `cancel`, and can never approve.

### Connecting an agent

An agent uses `agent_api.AgentClient` with its credential, or the MCP bridge
on the same private configuration file (`endpoint`, `catalog_id`, `token_file`
and optional `timeout`; see [agent operations](agent-operations.md)):

```python
import agent_api
client = agent_api.AgentClient.from_config('/private/agent.json')
client.call('project.summary', {})
client.call('project.plan', {'targets': ['benchmarks/held-out']})
```

```
python mcp_stdio.py --config /private/agent.json
```

The owner uses `agent_api.ProjectFolderOwnerClient`, or `mcp_stdio.py
--project-folder-owner`, with an owner credential. `catalog_id` is the
`dataset_id` that `GET /api/workspace/context` answers.

Every operation is `POST /api/project/<name>` with a JSON object of its
arguments, and must name its contract in the `Tuldok-Operation-Contract`
header, as `GET /api/agent/capabilities` lists it; the clients do this. A
call answers its result object, or a refusal `{"error", "code"}` with
`problems`, `references` and `files` when there are any. The status is 404
for `not-found`, 400 for `invalid`, 403 for `forbidden` and 409 for every
other code. Other `/api/` routes answer 409 `unavailable`, except sign-in,
credentials, `GET /api/agent/capabilities`, `GET /api/agent/operations`,
`GET /api/workspace/context` and `GET /api/project/file` (see
[Looking inside a product](#looking-inside-a-product)).

### Requests and approval

Nothing runs without the owner's approval. A build asked for with
`request_build` is a **build request**. The owner's own request is queued at
once. An agent's waits as `awaiting-approval` until the owner approves it
(`approve_build`, or `python -m tuldok_project approve FOLDER REQUEST`) or
declines it. The approval covers exactly what the request showed: the commit
and the text of every definition in its plan. If either changed, approving
is refused (`stale`) and the request is declined. The app runs queued
requests one at a time; an approval not started within an hour expires. An
agent may request a build only when its credential includes `execute`.

### Operations

**Who** is the rule for the caller: `inspect`, `edit` or `cancel` means any
credential with that scope; `request` means the owner, or an agent whose
credential includes `execute`; `owner` means the owner only. The arguments
and result keys of each operation are in its contract.

| Operation | Who | Does |
| --- | --- | --- |
| `summary` | inspect | Read the project's name, folder, counts of definitions by kind and state, and whether its build worker runs. |
| `status` | inspect | List the unsaved and removed definitions and the files changed on disk since the last import or save. |
| `check` | inspect | Check the project folder on disk and list its errors and warnings, even when it does not open. |
| `definitions` | inspect | List the definitions, optionally of one kind, with their states. |
| `definition` | inspect | Read one definition: its text, document, state, what it uses and what uses it. |
| `graph` | inspect | Read every definition with its kind and state, and the edges between them. |
| `results_overview` | inspect | List, per benchmark, how many subjects have results and whether they differ from the results file. |
| `results` | inspect | Read one page of a benchmark's summary rows, optionally for one subject, metric or group. |
| `values` | inspect | Read one page of a benchmark subject's per-case values. |
| `chart` | inspect | Read a chart's data, and its SVG drawing when asked. |
| `report` | inspect | Read the HTML report of the project: where it stands, every chart, the results and the definitions. |
| `plan` | inspect | Plan building the targets (or every buildable definition) without running anything. |
| `estimates` | inspect | List the stored estimates of disk and time for the definitions as they now are. |
| `environments` | inspect | List the environments with the interpreter recorded on this machine and their last check. |
| `environment` | inspect | Read one environment with the interpreter recorded on this machine and its last check. |
| `runs` | inspect | List the runs, newest first, optionally of one definition. |
| `run` | inspect | Read one run's record, its product and whether its build is alive, without variable values. |
| `progress` | inspect | Read a run's latest progress event and its logs from the given offsets; to read on, pass each log's returned offset back as `stdout_offset` and `stderr_offset`. |
| `products` | inspect | List the current products, optionally of one definition. |
| `build_requests` | inspect | List the build requests, newest first, optionally in one state. |
| `build_request` | inspect | Read one build request with what it covers and the runs of its build. |
| `activity` | inspect | List the changes asked of this project through the interface, newest first, and how each ended. |
| `map` | inspect | Read the map of the project: its groups, every recipe as a model with its group, kind of change, state and track value, the lines between them and the comparisons. |
| `note` | inspect | Read one file under the notes directory of the project folder, given relative to it. |
| `recipe_results` | inspect | Read the summary rows of every benchmark subject made from one recipe, ungrouped or for one group. |
| `draft_branch` | inspect | Write the text of a new recipe branched from one of the project's, with its name and what keeping it would find wrong; nothing is stored. |
| `records` | inspect | Read one page of the records of a finished run's product, optionally of one kind or split, with the counts by kind and split. |
| `record` | inspect | Read one record of a finished run's product with its content: text, image size, sound peaks, points, mesh or arrays. |
| `inside` | inspect | List a directory, an archive or the arrays of an .npz in a finished run's product. |
| `array_slice` | inspect | Read a slice along two axes of an array in a finished run's product, as 32-bit floats. |
| `array_summary` | inspect | Read the range, mean, deviation and histogram of an array in a finished run's product. |
| `weights` | inspect | List the weights files of a finished run's product, each with its size, the file it started from and, when Tuldok reads it, its layers and parameter count. |
| `weights_compare` | inspect | Compare, array by array, a weights file of a finished run's product with one of the same or another finished run: norms, relative change, cosine and largest change. |
| `array_tiles` | inspect | Read tiles of two axes of an array in a finished run's product, one per position along a third axis, as 32-bit floats. |
| `set_definition` | edit | Check a definition's text and keep it as an unsaved edit. |
| `remove_definition` | edit | Mark a definition that nothing uses as removed, until the project is saved. |
| `revert_definition` | edit | Put back the file in the folder in place of a definition's unsaved edit or removal, or drop a definition the folder has no file for. |
| `save` | edit | Write the unsaved edits and changed results files to the project folder. |
| `resolve_conflict` | edit | Open a project whose files changed on disk where it has unsaved edits, keeping or discarding those edits. |
| `import_values` | edit | Import one per-case values file, replacing that subject's values and summaries. |
| `check_environment` | edit | Check an environment's recorded interpreter against its definition and keep the result. |
| `connect_environment` | owner | Record an existing interpreter for an environment on this machine and check it. |
| `disconnect_environment` | owner | Forget an environment's recorded interpreter on this machine; nothing is deleted. |
| `request_build` | request | Ask for a build of the targets: the owner's request is queued, an agent's waits for the owner's approval (read `build_request` for its state), and a queued request not started by its `expires_at` expires. |
| `approve_build` | owner | Approve a build request awaiting approval, if what it covers is unchanged. |
| `decline_build` | owner | Decline a build request awaiting approval, with a reason. |
| `cancel_build` | cancel | Cancel a build request, stopping its build when it is running. |
| `cancel_run` | cancel | Ask a queued or running run to stop. |
| `stop_run` | cancel | Kill what a run whose build is gone left running, and mark it unknown. |
| `annotation_tasks` | inspect | List the annotation tasks, each with its dataset, current product and counts of its records by the state of their annotations. |
| `annotated_records` | inspect | Read one page of the records of a task's dataset with their annotations, optionally in one state or of one kind, with the counts. |
| `annotation` | inspect | Read one record's annotation under a task as it now is and as it is in the file, whether it is unsaved or stale, and the hash of the record's content. |
| `set_annotation` | edit | Check annotations of a task's records, or their removal, and keep them as unsaved edits; one item that does not check refuses them all. |
| `revert_annotations` | edit | Put back the saved annotations of a task's named records, or of all its records, in place of their unsaved edits. |

`map` answers `groups` (in their order, each with `id`, `title`, `parent`,
`description` and `models`, the number of recipes naming it), `models` (one per
recipe, by `trained_at` and then by name: `reference`, `title`,
`short`, `group`, `change`, `derived_from`, `trained_at`, `state`, `unsaved`
(whether the definition has an unsaved edit), `adopted`, `card`, `value` and
`count`, `benchmarks`), `edges` (`{from, to, kind}`,
`derived` or `input`), `comparisons` (`{from, to, explanation, excerpt}` as
authored) and `track` (null, or `{chart, benchmark, metric, statistic}` from
`map.chart`). A model's `value` and `count` are the track's statistic on the
ungrouped row of its subject and how many cases it summarises; when a recipe
is the subject under several names, the best by the metric's `better` is
taken. A model's `trained_at` is its label `trained_at`; without the label,
the time the run that made its current product finished (ISO 8601 in UTC),
and null when it has no product or its product was adopted. Models with a
`trained_at` come first, earliest first. `map` runs the same few queries
whatever the number of recipes and reads no file. `note` takes `path`, relative to `notes/`, and reads it from
the folder without opening the project; anything it refuses is `not-found`.
`recipe_results` takes `recipe` and an optional `group` (absent: the
ungrouped rows only) and answers `rows`, each as in `results` with
`benchmark` added, ordered by benchmark, subject and metric, and
`benchmarks`, the benchmarks with a subject made from that recipe.

`draft_branch` takes `recipe` (the parent, a bare name or `recipes/<name>`),
`title` (1 to 200 characters) and optionally `name`, `change` (one of the four
kinds of change) and `description` (at most 4,000 characters). It stores
nothing and answers `reference`, `text`, `parent`, `inlined` and `problems`:

- `reference` is `recipes/<name>`. A given `name` must follow the name rule and
  be free, and a removed definition's name is not free; otherwise the call is
  refused `invalid`. Without `name` it is made from the title: lowercase, each
  run of characters outside `[a-z0-9]` one `-`, trimmed of `-` at both ends and
  to 80 characters (`recipe` when nothing is left), then `-2`, `-3` and so on
  until it is free.
- `text` is the new recipe, written from the parent's text as it is in the
  working copy: `format`, `kind`, `title`, `description` when given, the
  parent's `model` and `group` when it has them, `change` (the argument, else
  the parent's), `derived_from` naming the parent, and the parent's `run` when
  it has one. `card`, `labels`, `earlier_work` and `compared_with` are not
  carried. It is JSON indented as the parent's text is (two spaces when the
  parent's has no indentation) and ends with a newline.
- When the parent's `run` has `settings_file` and that file, read from the code
  root as it is on disk, is a regular file holding one JSON object of at most
  256 KiB, the new `run` carries that object as `settings` in place of
  `settings_file`, and `inlined` is the file's path. A file reached through a
  link that leaves the code root is not read. Otherwise `inlined` is null and
  `run` is carried as it is.
- `problems` is what `set_definition` would find in `text` at `reference`,
  errors and warnings, each `{severity, path, pointer, message}`. A branch of a
  model without `run`, or whose code paths are missing, comes back with those
  errors for the caller to fix before keeping it.

A `recipe` that is not a recipe of the project, or is removed, is refused
`not-found`.

`revert_definition` takes `reference` and answers `{reference, dropped}`. It
applies to a definition with an unsaved edit or marked removed:

- When the folder holds its file, the file's text takes its place as an import
  of that file would put it (text, title, kind, the file's digest and the uses
  it makes), and it is neither unsaved nor removed; `dropped` is false. The text
  is checked as `set_definition` checks it, and a file that no longer checks, or
  that cannot be read, is refused `invalid` with its problems and nothing
  changes. A benchmark's summary rows are kept to what fits it, as
  `set_definition` keeps them; when its results file on disk is still the one
  last imported, that file is imported again, so a benchmark whose removal is
  reverted has the rows of its results file back (per-case values imported
  from values files went with the removal and are not).
- When the folder holds no file for it, it is dropped as `remove_definition`
  drops a definition never saved, and `dropped` is true; this is refused
  `in-use` while another definition uses it.

A definition with neither an unsaved edit nor the removed mark is refused
`nothing-to-revert`, and an unknown one `not-found`.

Installing an environment (`set-up`), measuring estimates (`estimate`),
variables passed to a build (`build --env`), rebinding and forgetting a
project stay command-line actions.

### Looking inside a product

A **product** is the `output` directory of a run in state `succeeded` or
`adopted`, named by its run id (or an unambiguous prefix of it). The
operations `records`, `record`, `inside`, `array_slice`, `array_summary`,
`array_tiles`, `weights` and `weights_compare` read it; each takes `run`, and a run that does not exist, has not finished or
has no output directory is refused `not-found`. Like every operation they
open the project for a moment, to find the run and the view of its dataset;
they read the product after closing it and write nothing: no file, no row.

An **address** is a path relative to the product, never absolute, never with
`..`. A member of a zip archive is named after `!`, as
`training-view.zip!samples/a.npz`; an address has at most two `!`. An `.npz`
is a zip of `.npy` members; one of its arrays is named by the argument
`array`, without `.npy`. An address that is not one is refused `invalid`. An
address is resolved under the product, and its real path must lie inside
it: a missing file, and a symbolic link that leaves the product, are refused
`not-found`. Archive members are read where they are, never extracted.

**Records.** A record is one item of the product. Its kind is `text`,
`image`, `audio`, `pointcloud`, `mesh`, `array`, or `file` for anything else
(listed, never opened). The records come from the first of:

1. `records.jsonl` at the product's root, one JSON object per line:

   | Key | |
   | --- | --- |
   | `id` | required; unique; 1 to 200 characters of `A-Z a-z 0-9 . _ -` |
   | `kind` | required; one of the seven kinds |
   | `path` | an address; required unless `kind` is `text` and `text` is given |
   | `text` | the text itself, for a short text record (at most 64 KiB) |
   | `array` | for kind `array` in an `.npz`: the array to show first |
   | `split`, `rights` | optional strings |
   | `origin`, `meta` | optional objects, kept and shown as they are |
   | `sha256` | optional; the SHA-256 of the record's content, 64 lowercase hexadecimal characters (see [Annotations in the database](#annotations-in-the-database)) |

   Other keys are kept and shown in `meta` (a key of `meta` itself wins). A
   line that is not such a record, or is longer than 64 KiB, is skipped and
   reported in `problems` with its line number (the first 20, then one
   problem with the number of such lines); blank lines are skipped.
2. `view` on the dataset's definition (datasets only):

   ```json
   "view": {"records": "lists/all.jsonl"}
   "view": {"files": "training-view.zip!samples/*.npz", "kind": "array", "show": "target_pressure"}
   ```

   `records` is the address of a record list in the format above, anywhere
   in the product; its paths are addresses in the product. `files` is a
   pattern: `*` and `?` match within one path segment, `**` across segments,
   and one `!` may reach into the archives it matches. Each match is a record
   whose id is its address. `kind` (by default by extension) and `show` (the
   array shown first) apply to every match and only to `files`. A view has
   `records` or `files`, not both. `check` checks the shape of `view` and its
   addresses, and nothing about any product.
3. Otherwise every regular file under the product, sorted by address, its id
   its address and its kind by extension. At most 200,000 files are listed,
   and `problems` says when there are more.

| Kind | Extensions |
| --- | --- |
| text | `.txt .md .json .jsonl .csv .tsv .yaml .yml .log` |
| image | `.png .jpg .jpeg .webp .gif .bmp` |
| audio | `.wav .flac .mp3 .ogg .opus .m4a` |
| pointcloud | `.xyz`, and `.ply` with no faces |
| mesh | `.obj .stl`, and `.ply` with faces |
| array | `.npy .npz .safetensors` |
| file | everything else |

The index of a product's records is kept for the 8 products read last and
made again when its list (or, without a list, the product directory) changes
size or time.

**`records`** takes `offset`, `limit` (at most 200, 50 by default), `kind` and
`split`, and answers `records` (each `id`, `kind`, `path`, `bytes`, `split`,
`rights`, `origin`, `meta`, `sha256` (null unless the list gives it), `array`
when the list gives one, and for a text
record its first 400 characters as `preview`), `total` (after the filters),
`source` (`records.jsonl`, `view` or `files`), `kinds` and `splits` (counts
over all the records; records without a split are not counted in `splits`)
and `problems` (each `{line, message}`, `line` null for a problem of the whole
list).

**`record`** takes `id` and answers `record` (as above, with `media_type`:
the type of the file route for an image or a sound, with `url`, the file
route's address for it; `text/plain` for text; else
`application/octet-stream`) and `content`, by kind:

| Kind | `content` |
| --- | --- |
| text | `text` (at most 262,144 characters), `characters` (of the whole text; null when it is longer than 16 MiB), `truncated`, `replaced` (bytes that were not UTF-8, each shown as U+FFFD) |
| image | `width`, `height`, from the header of a PNG, JPEG, GIF, WebP or BMP; null when not found |
| audio | for a WAV of PCM (8, 16, 24, 32 bit) or 32-bit float: `channels`, `rate`, `frames`, `seconds`, `peaks` (at most 1,000 pairs of lowest and highest sample over all channels, scaled to -1..1); for other sounds all null |
| pointcloud | `count`, `stride`, `bounds` (`[[x, y, z] lowest, [x, y, z] highest]` of the points returned), `points_f32` (base64 of little-endian 32-bit x, y, z; at most 100,000 points, every `stride`-th above that), `colors_u8` (base64 of r, g, b, or null). From PLY (ASCII or binary little-endian, colours from `red`, `green`, `blue`), XYZ text (colours when columns 4 to 6 are whole numbers 0 to 255), or an `.npy` of shape (N, 3 or more) when the record's kind is `pointcloud` |
| mesh | `vertices`, `triangles`, `bounds`, `positions_f32`, `triangles_u32` (base64, little-endian; polygons split into triangles as a fan). From PLY (ASCII or binary little-endian), OBJ (`v` and `f`, with `/` forms and negative indexes) and STL (binary or ASCII; equal corners are one vertex) |
| array | `arrays` (each `array`, `shape`, `dtype`, `bytes`; a plain `.npy` has one array, named null) and `show` (the record's `array`, else the view's `show`, else the first array with two or more dimensions, else the first) |
| file | an empty object |

A point cloud or mesh file of more than 256 MiB is refused `too-large`, and
so is a mesh of more than 200,000 vertices or 400,000 triangles, with the
counts. A file that cannot be read as its kind is refused `invalid`.

**`inside`** takes `path` (an address; the product's root by default),
`offset` and `limit` (at most 500, 200 by default), and answers `entries` and
`total`. A directory lists its children, an archive the members at its top
(an address `a.zip!samples` lists the members under `samples/`), and an
`.npy`, `.npz` or `.safetensors` its arrays. Each entry has `name`, `path` (its address),
`type` (`directory`, `file`, `archive` or `array`), `bytes` (decompressed, for
a member) and `kind`; an array also has `array`, `shape` and `dtype`, and its
`path` is the address of its file. Directories come first, then by name. A
zip nested deeper than an address can name is a `file`. A plain file is
refused `invalid`. A `.safetensors` file is listed with `type` `archive`, as
an `.npz` is, though no address reaches into it with `!`.

**Arrays.** NPY versions 1, 2 and 3 are read, in C or Fortran order, little-
or big-endian, of floats of 2, 4 and 8 bytes, signed and unsigned integers of
1, 2, 4 and 8 bytes and booleans; `dtype` is named as `float32`, `int16`,
`uint8`, `bool`. Anything else (objects, complex numbers, strings,
structured types) is listed with its type as written and refused
`unsupported` when read; an object array is never unpickled. The header is
parsed as a literal of at most 64 KiB.

A `.safetensors` file is read like an `.npz`: its tensors are its arrays, named
by `array` as they are in its header, listed in the order of its header. The
file is 8 bytes (the header's length, little-endian), a JSON header of at most
16 MiB (each tensor's `dtype`, `shape` and `data_offsets`, and
`__metadata__`, which is not shown), then the data, read where it lies. The
types `F16 F32 F64 I8 I16 I32 I64 U8 U16 U32 U64 BOOL` are read, little-endian
and in C order, and named as an NPY array's are; a tensor of another type
(`BF16` and the rest) is listed with its type as written and refused
`unsupported` when read. A header longer than the file, data offsets outside
the file or reaching into the header, and data whose length does not match
its shape and type are refused `unsupported`.

**`array_slice`** takes `path`, `array` (for an `.npz`), `axes` (the two axes
drawn, by default the last two), `index` (one position per axis, by default
the middle of each; ignored for the two drawn) and `most` (rows and columns
at most, 256 by default, at most 512). It answers `shape`, `dtype`, `axes`,
`index`, `rows`, `columns`, `stride` (one for both axes; 1 unless every
`stride`-th row and column is taken to fit `most`), `values_f32` (base64 of
little-endian 32-bit floats, row by row), `min` and `max` (of the finite
values) and `nonfinite`. An array of one axis is drawn as one row and one of
none as one value; `axes` is then left out.

**`array_summary`** takes `path`, `array` and `bins` (64 by default, at most
256), and answers `shape`, `dtype`, `count`, `min`, `max`, `mean`, `std`,
`zeros`, `nonfinite`, `histogram` (`low`, `high`, `counts`: equal bins from
the lowest to the highest finite value) and `stride`. At most 4,000,000
values are read: beyond that every n-th value in storage order, and `stride`
is n. All but `count` and `stride` are of the values read.

**`array_tiles`** takes `path`, `array`, `across` (the axis counted over; by
default the first axis not drawn), `axes` (the two drawn in each tile; by
default the last two other than `across`), `index` (one position per axis, by
default the middle of each; used for the axes neither drawn nor counted
over), `first` (0 by default) and `most` (tiles at most, 16 by default, at most
64). The array has three axes or more; otherwise, or when `first` is outside
`across`, the call is refused `invalid`. It answers `shape`, `dtype`,
`across`, `axes`, `index` (with the position of `first` on `across`), `first`,
`tiles` (how many follow `first`, at most `most`), `rows`, `columns`,
`stride` (as for `array_slice`, one for every tile, each tile at most 64 by
64), `values_f32` (base64 of little-endian 32-bit floats, tile by tile, each
row by row; tile `t` is the slice at position `first + t` on `across`), `min`,
`max` (of the finite values of all the tiles) and `nonfinite`.

**Reading no more than is needed.** A file on disk is mapped read only, and a
member stored uncompressed in a zip is read at its offsets in its archive's
bytes, so a slice reads only the bytes it draws and listing an archive reads
only its central directory. A compressed member (deflate or bzip2) is
decompressed whole into memory; one of more than 256 MiB, by the size the
archive declares and again while decompressing, is refused `too-large` with
its size. What was decompressed is kept for the next read, at most 512 MiB
for all products together, the least recently used dropped first. Other
compression methods and encrypted members are refused `unsupported`.

A file that is damaged, or is not what its name says, is refused `unsupported`
and the product stays readable: the file is one record among the others.
Arguments that do not fit (an address that is not one, axes or positions
outside an array) are refused `invalid`.

**The bytes of an image or a sound.** `GET /api/project/file?run=<id>&path=<address>`
answers the bytes of a file of a product, or of an archive member of at most
256 MiB, to whoever may call an `inspect` operation, and is refused as such an
operation is otherwise (401 without a credential). `run` and `path` are given
once each and nothing else, or the request is refused 400 `invalid`; refusals
of the product and the address are as for the operations. The media type
comes from the extension, for the image and audio extensions above only, and
those are sent `inline`; everything else is `application/octet-stream` with
`Content-Disposition: attachment`, so no product file is sent as HTML, SVG or
script. Every answer carries `X-Content-Type-Options: nosniff` and
`Cache-Control: no-store`. For a file on disk one `Range: bytes=a-b` (or
`bytes=a-`) is answered 206 with `Content-Range`; any other `Range` gets the
whole file. This route is not an operation and is not in the capability
manifest: an agent reads records, arrays and text through the operations.

### A model's weights

`weights`, `weights_compare` and `array_tiles` (above) read a product as the
operations above do: the same addresses and confinement, nothing written, and
a damaged file refused `unsupported`. Nothing runs the model.

**A run's weights** are the outputs its product records with role
`weights`; a declared output that is a directory gives the files directly in
it with one of the extensions below. When the product records none, they are
the files at the top of the product whose extension is `.npz`,
`.safetensors`, `.pt`, `.pth`, `.ckpt`, `.bin` or `.onnx` and whose name
contains `weight` or `model` (in any case), not beginning `initial-`. Only
`.npz` and `.safetensors` files are read. A PyTorch file (`.pt`, `.pth`,
`.ckpt`, `.bin`) is a pickle: it is listed by name and size with the reason,
and never opened, not even to look at its first bytes. The weights a file
started from are the file beside it with the same name prefixed `initial-`.

**Layers.** A tensor's layer is its name without its last dotted part:
`encoders.0.layers.0.weight` and `encoders.0.layers.0.bias` are the tensors
`weight` and `bias` of the layer `encoders.0.layers.0`; a name with no dot is
its own layer. Layers are in the order of the file (an `.npz`'s members in the
order of its central directory, a safetensors file's tensors in the order of
its header), each where its first tensor is.

**`weights`** takes only `run` and answers `files`, each with `path` (its
address), `output` (the output's name, or null when found by name), `bytes`
(null when a declared output is missing), `readable`, `reason` (null when
readable; otherwise a sentence: a pickle, ONNX, another format, a file that is
missing, or one that could not be read and why), `starts_from` (the address of
its `initial-` file, or null) and, when readable, `parameters` (the count of
the tensors listed), `tensors` (how many the file holds) and `layers` (each
`name`, `parameters` and `tensors`, each tensor `array`, `name`, `shape`,
`dtype` and `parameters`). At most 10,000 tensors of a file are listed. A
damaged weights file is listed as not readable with its reason; the call is
not refused for it.

**`weights_compare`** takes `path`, `other_run` (the same run, for its
`initial-` file, or any other finished run of the project) and `other_path`,
both weights files that are read (otherwise refused `unsupported` with the
reason). For each array in both with the same shape, in the order of `path`,
`tensors` gives `array`, `parameters`, `norm`, `other_norm`,
`difference_norm` (of this minus the other), `relative_change` (the
difference's norm over the other's; null when that is zero), `cosine` (null
when either norm is zero), `largest_change` (the largest absolute difference)
and `nonfinite` (non-finite values in either). `total` gives the same over all
of them together, without `array`. `only_here` and `only_there` name the
arrays of one file only, `reshaped` gives `array`, `shape` and `other_shape`
of those whose shapes differ, and `unread` gives `array`, `dtype` and
`other_dtype` of those with the same shape that one side's type keeps from
being read; neither is compared. Norms are Euclidean, over 64-bit floats; a
quantity that includes a non-finite value is null. Arrays are compared
element by element in C order, whichever order each is stored in. At most
32,000,000 values are read in all (both files together) and at most 10,000
tensors per file; beyond either the call is refused `too-large`, saying how
many there are.

### Annotating

The five operations on annotations (see [Annotations in the database](#annotations-in-the-database))
name a task by `task`, its name or its reference `annotations/<name>`, and
answer it as the reference. A task that the project does not have (or has
removed) is refused `not-found`. The records are those of the current product
of the task's dataset, read as `records` reads them; the reads find the product
with the project open for a moment and read it after, as the reads above do.

**`annotation_tasks`** takes nothing and answers `tasks`, by name, each with
`task`, `title`, `dataset`, `type` (the task's `task`), `vocabulary` (empty for
`review` and `text`), `run` (the dataset's current product, or null),
`records` (how many records it has, or null), `counts` and `unsaved` (how many
records have an unsaved change). `counts` has `unannotated` (records of the
product without an annotation), `draft`, `accepted`, `needs-work`, `rejected`
(annotations by state, stale ones included), `stale` and `invalid`.

**`annotated_records`** takes `task`, `state` (one of the names of `counts`;
absent for all), `kind`, `offset` and `limit` (at most 200, 50 by default),
and answers `task`, `run`, `records` (the page), `total` (after the filters)
and `counts`. The records are those of the product in its order, each as
`records` gives it with `in_product` true, followed (unless `kind` is given)
by the annotated records the product does not have, by id, with `in_product`
false and null `kind`, `path`, `bytes`, `split`, `rights`, `origin`, `meta`
and `sha256`. Each has `annotation`: null, or `state`, `value`, `note` (null
when there is none), `by`, `at`, `stale` and `unsaved`.

**`annotation`** takes `task` and `record` and answers `task`, `record`,
`annotation` (the line as it now is, as an object with the keys of the
annotations file, or null), `saved` (the line in the file, likewise, or
null), `unsaved`, `stale` (null when there is no annotation or no product)
and `sha256` (the hash of the record's content now, or null).

**`set_annotation`** takes `task`, `items` (1 to 200, each
`{record, state, value?, note?}` or `{record, remove: true}`) and `from`
(optional, an object written as every item's `from`), and answers `task`,
`set`, `removed` (how many annotations went) and `unsaved` (how many of the
task's records now have an unsaved change). Every item is checked before
anything changes: the record must be in the product (refused `not-found`
when the dataset has none), named once, and its line must be one the
annotations file allows, its value checked against the task, the vocabulary
and the record's kind, and, where the product makes it cheap to know, an
image's size, a text's length (a file of at most 16 MiB) and a WAVE sound's
length. One item that does not check refuses the call `invalid`, with one
problem per such item whose pointer is `/items/<n>`. The line takes `sha256`
from the record now, `by` from the caller (`owner`, or `agent:` and the
credential's name cut to 80 characters; never its id, token or scopes) and
`at` from the clock. Setting an annotation again takes the record's hash
again, which is how a stale annotation that is still right is put right.
Removing a record that has no annotation does nothing.

**`revert_annotations`** takes `task` and `records` (optional, at most 10,000)
and answers `task` and `reverted`: how many of those records (all the task's,
without `records`) had an unsaved change and now have their saved line
again, or no annotation when the file has none.

Each call of `set_annotation` and `revert_annotations` writes one activity
row whose target is the task's reference and whose detail says how many
records it set, removed or reverted.

## The project directory on this machine

Everything a project keeps on one machine alone (installed environments, code
snapshots, run directories and products) is in its local home,
`<project directory>/<project id>/`. The project directory is, first that
applies:

1. the environment variable `TULDOK_PROJECT_HOME`, when it is set and not empty;
2. `project_home` of the settings file;
3. `~/.local/share/tuldok/projects`.

The settings file is `~/.local/share/tuldok/settings.json`, or the file the
environment variable `TULDOK_SETTINGS` names. It is strict JSON as in
[JSON rules](#json-rules), at most 64 KiB, and has no other fields:

```json
{"format": "tuldok_settings_v1", "project_home": "/absolute/path"}
```

`project_home` is optional and must be absolute. The file is read only when
the environment variable does not decide. A settings file that cannot be read
or is not valid stops the command with a message naming the file and the
fault, exit status 2, and stops the app's start-up; Tuldok never falls back to
the default then.

| Command | Does |
| --- | --- |
| `home [--json]` | Prints the project directory, where it came from (the environment variable, the settings file or the default), the free space on its disk and how many project directories it holds. Needs no database. |
| `home --set PATH [--json]` | Saves `PATH`, which must be absolute, as `project_home`. `PATH` is made with its parents when missing and must be a directory this user can write. The settings file is written through a temporary file renamed into place, mode 0600. Says when the directory the setting or the default gave before holds project directories (they are not moved), and when `TULDOK_PROJECT_HOME` is set and so overrides the setting. |

```
$ .venv/bin/python -m tuldok_project home
directory  /mnt/data/tuldok/projects
from       the settings file /home/me/.local/share/tuldok/settings.json
free       812 GB on its disk
projects   2
```

## A new project

`new FOLDER --name NAME [--code-root PATH] [--json]` makes `FOLDER`, which must
not exist or must be an empty directory, and writes `tuldok.json` in it with
the format, a new random id, the name and `code_root` (`.` when not given). It
writes nothing else and needs no database. A name or code root that
[`tuldok.json`](#tuldokjson) does not allow is refused with exit status 2, and
nothing is made.

## Adopting existing files

Some files were made before Tuldok could build them and cannot be made again,
such as an earlier model's weights. `adopt` makes such files the product of a
dataset, recipe or step, so it is `built` and what uses it can be built. It is
a command-line action only, since a manifest names files anywhere on the
machine.

The manifest is strict JSON, at most 16 MiB:

```json
{"format": "tuldok_adoption_v1",
 "products": [
   {"reference": "recipes/pilot-a",
    "note": "Tuldok run acb748bc of 2026-10-21",
    "files": {"weights.npz": "/absolute/path/to/the/file",
              "history.json": "/absolute/path/to/another"}}
 ]}
```

| Field | Rule |
| --- | --- |
| `products` | 1 to 5000 entries; a reference appears once |
| `reference` | a dataset, recipe or step of the project, not removed |
| `note` | optional, 1 to 400 characters; kept as the run's problem text, where a run's remark is shown |
| `files` | 1 to 200 entries. Each key is a relative path in normal form where the file goes in the product. When the definition declares outputs, the key is the `path` of one of them or a path under one; when it declares none, its product is the directory as a whole (what a step that uses it as an input is given) and any relative path is accepted. No key may have another under it. Each value is the absolute path of an existing regular file this user can read; a link is refused |

Unknown fields are refused. Every entry is checked before anything is
adopted: one refused entry stops the command, every problem is printed, and
nothing is adopted. Declared outputs without a file are reported as missing,
and the entry is still adopted. An entry whose definition already has a
current product is skipped, unless `--replace`.

Adopting an entry makes `<local home>/runs/<run id>/output/` holding the files
at their keys, as hard links to the sources; a source on another filesystem
is copied, and `--copy` copies always. The directory is made under a temporary
name and renamed into place. Then a run is recorded in state `adopted`, with
no commit and no command, the definition's text as it is now, the note, all
three times set to now and the total size of the files; and its product, made
current, with the declared outputs that have a file and the size of each. A
product that was current before stays in the database, no longer current. No
checksum is taken, and Tuldok never writes to an adopted file.

A definition whose current product was adopted is `built` and never out of
date: its text, settings, inputs and code are not compared. `plan` shows it as
`built` (noting `adopted, not built here`) and plans nothing it uses. A
benchmark subject whose recipe has a current product runs even when the
recipe's own label is `no` or `needs-work`. `runs` and `run` show the state
`adopted`; `products` and `run` mark the product `(adopted)`, and their JSON,
like `status` entries and the app's `runs`, `run` and `products` results,
carries `adopted: true`. A real build of the definition replaces it like any
other product.

| Command | Does |
| --- | --- |
| `adopt FOLDER MANIFEST [--dry-run] [--copy] [--replace] [--json]` | Checks the manifest and prints what it would do: the entries to adopt, those skipped because they have a product, the declared outputs missing, the files and bytes, and whether they are linked or copied. Without `--dry-run` it then does it and prints the same, with each new run id. |

Exit statuses: 0 done (or, with `--dry-run`, checked); 1 when an entry is
refused, the manifest is not strict JSON, or copying or linking failed (the
entries printed before the failure were adopted); 2 when the manifest cannot
be read.

```
$ .venv/bin/python -m tuldok_project adopt FOLDER manifest.json --dry-run
Would adopt 1 entry, skip 0 that already have a product.
1 file, 61 B: 1 to be linked, 0 copied.

adopt  datasets/numbers  1 file  61 B  linked

Nothing was changed (--dry-run).
```

## What the format does not do yet

A project folder can be made with `new`, files made elsewhere can be adopted
as products, and the folder is checked, can be opened, edited and saved through the database
copy, its results can be read and drawn, its environments can be connected,
checked and installed, and its definitions can be planned, estimated and
built on this machine, one build at a time per step, from the command line
or, through build requests, by the Tuldok app that serves the folder. Tuldok
does not yet install an environment or measure estimates from the app,
delete old products, run directories or code snapshots, use `cpu_threads` or
`memory_gb` (they are shown, not enforced), or read the contents of notes.

Background: [the design notes for this format](../plans/definition-first-projects/).
