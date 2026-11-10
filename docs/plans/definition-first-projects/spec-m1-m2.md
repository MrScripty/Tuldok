# Implementation spec: milestones 1 and 2

This is the exact specification for milestones 1 and 2 of [the plan](plan.md). The plan says what and why; this file says how. Where the two differ, this file wins for these milestones. Later milestones get their own spec after these are accepted; section 6 records what is already settled for them.

Paths are relative to the Tuldok repository unless they start with `lab:`, which means the Rheon Surrogate Lab repository (`graphics-3d/rheon-surrogate-lab`).

## 1. Rules for implementers

- **New code lives in the package `tuldok_project/`** at the repository root. Milestones 1 and 2 change no existing Tuldok file except `docs/README.md` (one link) and the files a slice names.
- **Do not import from the old project modules** (`project_*.py`, `projects.py`, `retained_measurements.py`, `recipe_contract.py`, `pipeline.py`, `runs.py`). They will be deleted. Where a helper there is useful, copy the few lines into the new package. `metadata.connection_info` is the one allowed import from existing code.
- **Dependencies:** the standard library, `jsonschema` 4.26.0 and `psycopg` 3.3.6, all already in `requirements.txt`. Add nothing.
- **Python:** 3.12, run as `.venv/bin/python`. Module docstrings follow the house style: one summary line, then a short paragraph on what the module owns.
- **Tests:** `unittest`, in `tests/test_tuldok_project_*.py`. Run one file with `.venv/bin/python -m unittest discover -s tests -p 'test_tuldok_project_*.py' -v`. A test file starts with `sys.path.insert(0, str(Path(__file__).resolve().parents[1]))`.
- **Database tests** (milestone 2 only) are skipped unless `TULDOK_DATABASE_URL` is set, and must run against a disposable cluster, never the owner's working database: `python scripts/local_postgres.py init --directory <scratch>/pg`, then `eval "$(python scripts/local_postgres.py env --directory <scratch>/pg)"`, and `stop` when finished.
- **Standards:** if the tool `mcp__standards-engine__route` is available, call it with the facts `routing.activities = ["implementation", "verification"]`, `routing.details = ["topic.code-design"]`, every other fact `{"state": "known-absent"}`, and `content = {}`, and follow what it returns.
- **Git:** work in the checked-out branch, do not commit, do not push, do not switch branches.
- **Report:** end with the list of files written, the exact test command run and its result, and anything in this spec that turned out to be wrong or ambiguous. Do not silently work around a spec problem.

## 2. The project folder format (normative)

### 2.1 Layout

```
tuldok.json
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

- The seven definition directories hold only `.json` files, one definition each, no subdirectories. A directory may be absent.
- `<name>` matches `^[a-z0-9][a-z0-9._-]{0,119}$`.
- Top level may also hold `README.md` and `.gitignore`. Any other top-level entry is an error.
- `notes/` holds any plain files in any depth. They are not parsed.
- Every file is a regular file, not a symbolic link. A definition file is at most 1 MiB. `tuldok.json` is at most 64 KiB. A results file is at most 16 MiB.

### 2.2 JSON rules

Files are UTF-8 JSON objects. Duplicate keys, `NaN` and `Infinity` are refused. Unknown fields are refused everywhere except inside `settings`, `config` and `labels`, whose contents are free.

### 2.3 `tuldok.json`

| Field | Type | Rule |
| --- | --- | --- |
| `format` | string | exactly `tuldok_project_v1` |
| `id` | string | 32 lowercase hex characters |
| `name` | string | 1 to 120 characters |
| `code_root` | string | a relative path from the project folder to the root of the code the commands run in; default `.`; never absolute |

### 2.4 References

A reference is the string `<directory>/<name>`, for example `datasets/sinusoidal-v1`. It names the definition in `<directory>/<name>.json`. Each field that takes a reference states which directories it accepts.

An **input** is either a reference (the whole product of that definition) or `{"from": <reference>, "output": <output name>}` (one named output of it).

### 2.5 Fields common to every definition

| Field | Required | Type | Rule |
| --- | --- | --- | --- |
| `format` | yes | string | exactly `tuldok_definition_v1` |
| `kind` | yes | string | `dataset`, `model`, `recipe`, `benchmark`, `step`, `environment` or `chart`; must match the directory |
| `title` | yes | string | 1 to 200 characters |
| `description` | no | string | at most 4,000 characters |
| `card` | no | string | a path under `notes/`, relative to the project folder; the file must exist |
| `labels` | no | object | at most 32 entries, string values of at most 400 characters |
| `earlier_work` | no | object | see below; not allowed on `environment` and `chart` |

`earlier_work` marks an item converted from work done before this format:

| Field | Required | Rule |
| --- | --- | --- |
| `rebuild` | yes | `yes`, `after-inputs`, `needs-work` or `no` |
| `reason` | when `rebuild` is `no` or `needs-work` | 1 to 1,000 characters |

The label states a fact about this item alone, never about what it uses:

- `yes`: its command, code and settings are in Git and the command runs as written under this format.
- `after-inputs`: the same, and one of its inputs is an earlier model's weights.
- `needs-work`: nothing it names is lost, but the recorded command does not run as written under this format. The reason says what has to change.
- `no`: its command, its code or its producer is lost or was never in Git. The reason says which.

Whether an item can in fact be rebuilt also depends on everything it uses; Tuldok works that out from the graph (section 4.3).

### 2.6 The `run` block

`dataset`, `recipe`, `benchmark` and `step` carry a `run` object. It is required unless `earlier_work.rebuild` is `no`.

| Field | Required | Type | Rule |
| --- | --- | --- | --- |
| `command` | yes | array | 1 to 64 strings; when the first is `python` it means the environment's interpreter |
| `environment` | when the command starts with `python` | reference | `environments/` |
| `inputs` | no | object | at most 32; keys match `^[a-z][a-z0-9_]{0,31}$`; values are inputs from `datasets/`, `recipes/` or `steps/` |
| `settings` | no | object | free content; Tuldok writes it to a file whose path replaces `{settings}` |
| `settings_file` | no | string | a path relative to the code root; excludes `settings` |
| `env` | no | object | at most 32; keys match `^[A-Z_][A-Z0-9_]*$`; string values |
| `outputs` | no | object | keys like input keys; values `{"path": <relative path inside the output directory>, "role": <role>}` with role `data`, `weights`, `results`, `log`, `report` or `file` |
| `resources` | no | object | any of `gpu` (boolean), `cpu_threads` (integer ≥ 1), `memory_gb`, `wall_hours`, `disk_gb` (numbers > 0) |
| `sources` | no | array | at most 64 paths relative to the code root; a change in them means the code changed |
| `estimate` | no | object | `{"command": [...]}`; the command prints one JSON object with any of `disk_bytes`, `wall_seconds`, `items` |

**Placeholders** may appear in `command`, in `env` values and in `estimate.command`:

| Placeholder | Becomes |
| --- | --- |
| `{output}` | the directory the step writes into |
| `{settings}` | the path of the settings file |
| `{inputs.<name>}` | the path of that input; the name must be declared in `inputs` |
| `{subject}` and `{subject.name}` | benchmarks only, see 2.7 |

Any other `{...}` is an error. `{{` and `}}` are literal braces. `{settings}` requires `settings` or `settings_file`.

### 2.7 Kind-specific fields

**`dataset`**

| Field | Required | Rule |
| --- | --- | --- |
| `run` | per 2.6 | |
| `splits` | no | object, split name to a count of items (integer ≥ 0) |

**`model`**

| Field | Required | Rule |
| --- | --- | --- |
| `entry` | no | string, for example `surrogate.models:DivergenceFreeStepper` |
| `config` | no | object, free content; excludes `config_file` |
| `config_file` | no | path relative to the code root |
| `sources` | no | as in 2.6 |

**`recipe`**

| Field | Required | Rule |
| --- | --- | --- |
| `run` | per 2.6 | |
| `model` | no | reference to `models/` |

**`step`**: `run`, required.

**`benchmark`**

| Field | Required | Rule |
| --- | --- | --- |
| `run` | per 2.6 | the command runs once per subject; when present, `outputs` must contain exactly one output with role `results` |
| `metrics` | yes | 1 to 64 of `{"id", "title", "units"?, "better"}`; `id` matches `^[a-z][a-z0-9_]{0,63}$` and is unique; `better` is `lower`, `higher` or `none` |
| `subjects` | yes | 0 to 1,000 of `{"name", "title"?, "recipe"?, "argument"?}`; `name` follows the name rule in 2.1 and is unique; `recipe` is a reference to `recipes/`; `argument` is the string that replaces `{subject}` and may contain `{recipe}` (the path of that recipe's product) when `recipe` is given |
| `cases` | no | `{"dataset"?: reference to datasets/, "split"?: string, "count"?: integer ≥ 0}` |
| `summary` | no | `{"group_by"?: up to 8 strings matching the metric id pattern, "statistics"?: a subset of mean, median, p10, p90, min, max}` |

**`environment`**

| Field | Required | Rule |
| --- | --- | --- |
| `python` | yes | `3.<minor>`, for example `3.12` |
| `device` | yes | `cpu` or `cuda` |
| `packages` | yes | object, 1 to 64 entries, package name to exact version string; these are what a run checks |
| `install` | no | `{"requirements": <path relative to the code root>, "index_urls"?: up to 4 https URLs}` |

**`chart`**

| Field | Required | Rule |
| --- | --- | --- |
| `benchmark` | yes | reference to `benchmarks/` |
| `form` | yes | `ranking`, `tradeoff`, `progression` or `comparison` |
| `metric` | yes | a metric id of that benchmark |
| `metric_x` | when `form` is `tradeoff`, otherwise not allowed | a metric id of that benchmark |
| `statistic` | no | one of the six statistics; default `median` |
| `subjects` | no | names of that benchmark's subjects; default all |
| `group` | no | one of that benchmark's `summary.group_by` |

### 2.8 Results files

`results/<name>.csv` holds the summary of benchmark `benchmarks/<name>.json`, which must exist.

- UTF-8, `\n` line ends, RFC 4180 quoting, first line exactly:
  `subject,metric,group,count,unavailable,mean,median,p10,p90,min,max,commit,produced`
- `subject` is one of the benchmark's subject names; `metric` one of its metric ids.
- `group` is empty, or `key=value` pairs joined by `;` with keys sorted and each key in the benchmark's `summary.group_by`. A value is written as plain text and may not contain `;`, `=` or a line break.
- `count` and `unavailable` are integers ≥ 0. The six statistics are decimal numbers, all empty when `count` is 0.
- `commit` is 40 lowercase hex characters or empty. `produced` is `YYYY-MM-DD` or `YYYY-MM-DDTHH:MM:SSZ`.
- Rows are unique on (subject, metric, group) and sorted by those three as strings.

**Statistics.** Over the measured values of one (subject, metric, group): `count` is how many there are; `unavailable` how many values were not measured; `mean` the arithmetic mean; `min` and `max`; `median`, `p10` and `p90` by linear interpolation between closest ranks, position `p × (count − 1)` in the ascending values. Numbers are written with Python's `repr(float)`.

### 2.9 Checks across files

1. Every reference names an existing definition in an accepted directory.
2. Every `{"from", "output"}` input names an output the producer declares.
3. The uses-graph has no cycle. Its edges, each from user to used, with a role:

   | From | To | Role |
   | --- | --- | --- |
   | a `run.inputs` entry | the referenced definition | `input:<name>` |
   | `run.environment` | the environment | `environment` |
   | `recipe.model` | the model | `model` |
   | `benchmark.subjects[].recipe` | the recipe | `subject:<subject name>` |
   | `benchmark.cases.dataset` | the dataset | `cases` |
   | `chart.benchmark` | the benchmark | `benchmark` |

4. Paths relative to the code root (`settings_file`, `config_file`, `sources`, `install.requirements`) are normalised, contain no `..`, and exist under the code root. A missing path is a warning when the definition has `earlier_work`, an error otherwise. This check is skipped when the caller asks not to look at the code.
5. Results files obey 2.8.

A problem is reported as severity (`error` or `warning`), the file's path relative to the project folder, a JSON pointer to the field (empty for whole-file problems), and one sentence. All problems are collected; the check does not stop at the first.

## 3. Milestone 1: the folder

**Done when:** the converted lab folder exists, is under 20 MB, and `python -m tuldok_project check <folder>` reports no errors.

### Slice T1: documents, folder, graph, check (Tuldok)

Files to write:

- `tuldok_project/__init__.py`
- `tuldok_project/schemas/project.schema.json` and one `<kind>.schema.json` per kind (JSON Schema 2020-12), expressing every single-file rule of section 2 that JSON Schema can express.
- `tuldok_project/documents.py`: strict JSON decoding (2.2); the name, reference and placeholder rules as functions; loading and caching the schemas.
- `tuldok_project/folder.py`: reading a project folder safely: no symbolic links, regular files only, the size caps of 2.1, the layout rules. Returns each definition with its kind, name, path, bytes, SHA-256, text and decoded document.
- `tuldok_project/graph.py`: pure functions over decoded definitions: `edges(definitions)`, `order(definitions)` (dependencies first, ties broken by reference string), `cycles(definitions)`, `users_of(definitions, reference)`.
- `tuldok_project/check.py`: `check_folder(folder, *, code=True) -> Report`. `Report` has `problems`, `ok` (no errors), and the parsed project (the `tuldok.json` document, the definitions keyed by reference, the edges). It applies sections 2.1 to 2.9 and calls `results.check_results` for each results file.
- `tuldok_project/__main__.py`: `python -m tuldok_project check FOLDER [--no-code] [--json]`. Prints one line per problem (`severity  path  pointer  message`) and a final count; exit status 1 when there is an error, 2 on a usage error.
- `tests/fixtures/tuldok_project/minimal/project/`: a valid folder with at least one definition of every kind, an input chain three deep, one `{"from", "output"}` input, one earlier-work item with `rebuild: no`, one results file and one card. Beside it, `tests/fixtures/tuldok_project/minimal/code/` is a small code tree; the folder's `code_root` is `../code`.
- `tests/test_tuldok_project_check.py`: the fixture passes; and for each rule of section 2 at least one test that copies the fixture to a temporary directory, breaks that one rule, and asserts the problem's path, pointer and severity.

### Slice T2: result summaries (Tuldok)

Files to write:

- `tuldok_project/results.py`:
  - `summarise(values) -> dict` implementing the statistics of 2.8 for one list of measured numbers plus an unavailable count.
  - `SummaryRow` (the thirteen columns) and `write_results(rows) -> str`, `read_results(text) -> list[SummaryRow]`, which round-trip exactly.
  - `check_results(text, benchmark_document) -> list[problem]` applying 2.8. A problem here is `(severity, pointer, message)`, where the pointer is `line <n>`; `check.py` adds the path.
- `tests/test_tuldok_project_results.py`: statistics on hand-computed cases (one value, two values, an even and an odd count, ties, negative values, a count of zero), the round trip, and one failing case per rule of 2.8.

T1 and T2 can be written at the same time. `tuldok_project/__init__.py` and a skeleton of `tuldok_project/results.py` with these signatures exist before either starts; T2 fills the skeleton in. Until it does, `check_results` raises `NotImplementedError`, so T1 keeps its results-file tests in a class of their own.

### Slice D1: the format contract (Tuldok)

`docs/contracts/project-folder.md`: the format for users, taken from section 2 of this spec, with the two examples from the plan corrected to this format; plus a link to it from `docs/README.md` under "Installation, access and storage". Written after T1 and T2 are accepted, so it describes what the checker enforces.

### Slice L1: the lab's folder (lab repository)

Output folder: `lab:projects/surrogate-lab/`. It is written by `lab:scripts/build_tuldok_project.py`, which takes `--tuldok <path to the Tuldok repository>` (to import `tuldok_project`), `--source projects/rheon-model-portfolio-unified-04`, `--output projects/surrogate-lab`, and `--check` (write nothing; fail if the folder differs from what would be written).

The script owns every file that carries `earlier_work`, every file under `results/` and `notes/`, and `tuldok.json`. It never touches a definition without `earlier_work`; those are written by hand in this slice and kept.

**Written by hand (new work):**

| File | Content |
| --- | --- |
| `environments/lab-cpu.json` | Python 3.12, `cpu`, `torch` 2.8.0+cpu, `numpy` 2.3.5; install from `tuldok/requirements-cpu.lock` with index `https://download.pytorch.org/whl/cpu` |
| `environments/cuda-torch.json` | Python 3.14, `cuda`, `torch` 2.14.0+cu132, `numpy` 2.5.3; no `install` yet |
| `steps/reference-solver.json` | the `cargo build` of `probes/reference/` described in `surrogate/README.md` |
| `datasets/sinusoidal-v1.json`, `datasets/diversity-v1.json` | `python -m surrogate.datasets generate <name> --root {output}`, with the solver step as an input and the splits from `surrogate/datasets/definitions/` |
| `models/divergence-free-stepper.json` | the stepper in `surrogate/models/` |
| `recipes/pilot-dense-k1.json` | `python -m surrogate.train` with `surrogate/configs/pilot-dense-k1.json` |
| `benchmarks/<suite>.json` | one per suite listed by `python -m surrogate.bench suites`, with the subjects and metrics that `surrogate/bench/` defines |

Where the lab's command line cannot yet take a placeholder the format needs (for example a results path), write the definition as the format requires and list the lab change needed in the report. Do not change `surrogate/` in this slice.

**Written by the script (earlier work):**

| Output | From | Rules |
| --- | --- | --- |
| `recipes/<card stem>.json`, 205 files | `notes/recipes/<stem>.json` and the card | `title` from the model name; `card` is `notes/fits/<stem>.md`; `labels` carry `fit_id`, `tuldok_run`, `trained_at`, `device`; `run` from the recorded command, settings, resources and inputs, with each recorded `<input: x>` turned into `{inputs.x}`; training-data inputs refer to `datasets/<training set id>`, earlier-weights inputs to `recipes/<that model's stem>` |
| `datasets/<id>.json` | `notes/recipes/training-sets.json` (the 26 training sets and the recording groups) | `run` from the recorded or reconstructed command; a recording group that is one of the new datasets refers to it and gets no file of its own |
| `benchmarks/<slug>.json` | the 31 result sets, grouped by the part of their title after the first `·` with any `(n subjects)` and `part n` removed | metrics from the result sets; one subject per result-set subject, named by its id in lower case with other characters turned into `-` and its original id and label in `title`; `recipe` set wherever the subject can be matched to a model (by `fit_item_id`, else by weights checksum or checkpoint number through the notes); `summary.group_by` is the per-value dimensions in use |
| `results/<slug>.csv` | the same result sets | statistics from `tuldok_project.results.summarise` |
| `notes/fits/*.md` and `notes/*.md` | copied | nothing else is copied from `notes/` |
| `tuldok.json` | fixed | name `Rheon surrogate lab`, a fixed new id, `code_root` `../..` |

**Code paths.** The earlier runs executed staged copies of their scripts under `runs/`, which is not in Git. For every script and source path of an earlier item, the script looks for a tracked file with identical content (outside the old project folder) and writes that path. Files the old Tuldok generated for a run (for example under `runtime-bootstrap/`) are not sources and are left out.

**The `earlier_work.rebuild` label** (section 2.5 defines the four values):

- `no` when the item has no recorded command or no single command line, when its producer is unknown or lost, or when its script or one of its sources has no tracked file. Earlier benchmarks are all `no`, with the reason that they were measured by the earlier study harness.
- `needs-work` when everything it names is in Git but the recorded command cannot run as written. This is the case for the earlier training recipes, whose commands take two arguments that the old Tuldok supplied.
- `after-inputs` and `yes` only when the command line is exact. When the command was reconstructed and not recorded at the time, say so in `description`.

**The script's report** (printed, and required in the agent's final report): counts of each kind; how many of each `rebuild` label; how many result-set subjects were matched to a model and how many were not, with the unmatched listed; the folder's size; and a list of what the `notes/*.json` files and `notes/checkpoints/` contain that the new folder does not carry, so the owner can decide whether any of it should be kept.

Tests: `lab:surrogate/tests/` is for the surrogate package; put the script's tests in `lab:scripts/tests/test_build_tuldok_project.py` and run them with the lab's `.venv/bin/python -m unittest`.

### Slice L2: the earlier runs' code and the authored comparisons (lab repository)

Decided by the owner on 2026-11-10: bring the earlier runs' code into the lab repository, and keep the authored comparisons.

- **`lab:earlier-run-code/`** holds the code and settings files that earlier items name and that have no tracked copy elsewhere. A file from `runs/<rest>` is copied to `earlier-run-code/<rest>`. Each distinct content is copied once: its home is the first of its paths in sorted order, and every item that names an identical file refers to that home. A `README.md` there says what the folder is and that `scripts/build_tuldok_project.py` writes it.
- **Copied:** Python code and settings files (the values a run was configured with).
- **Not copied:** archives and arrays (`.zip`, `.npz`, `.npy`, weights), which are generated data; and files that are records about other files and not settings (checksum listings, source witnesses, receipts, qualification records). Those are treated like files the old Tuldok generated: left out of `sources`, and named in the `needs-work` reason of an item whose command reads them.
- The script owns `earlier-run-code/` completely: it writes it, removes stale files, and `--check` covers it.
- Labels are recomputed with these files counted as tracked.
- **`notes/model-groups-and-comparisons.json`**, written by the script: the task groups and the comparisons between models from the old `notes/00-models.portfolio.json`, with each model named by its recipe reference.

## 4. Milestone 2: open and save

**Done when:** with an empty database, `python -m tuldok_project open lab:projects/surrogate-lab` completes in under 10 seconds and `list` and `graph` show every definition with its links and state; a second `open` with nothing changed completes in under 1 second.

### 4.1 Database

One Postgres schema per project, named `project_<id>`, created on first open with `CREATE SCHEMA IF NOT EXISTS` and `CREATE TABLE IF NOT EXISTS`, under a session advisory lock, on a dedicated autocommit connection from `metadata.connection_info`. Later changes are additive `ALTER TABLE ... ADD COLUMN IF NOT EXISTS`.

```sql
CREATE TABLE state (
  singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
  project_id text NOT NULL, name text NOT NULL,
  folder text NOT NULL,            -- real path of the folder this copy is bound to
  code_root text NOT NULL,
  imported_at timestamptz NOT NULL);

CREATE TABLE definitions (
  directory text NOT NULL, name text NOT NULL,
  kind text NOT NULL, title text NOT NULL,
  text text NOT NULL,              -- the exact file content
  document jsonb NOT NULL,
  file_sha256 text,                -- of the file as last imported or saved; NULL if never on disk
  unsaved boolean NOT NULL DEFAULT false,
  removed boolean NOT NULL DEFAULT false,   -- deleted in the database, not yet saved
  PRIMARY KEY (directory, name));

CREATE TABLE edges (
  from_ref text NOT NULL, to_ref text NOT NULL, role text NOT NULL,
  PRIMARY KEY (from_ref, to_ref, role));
CREATE INDEX edges_to ON edges (to_ref);
```

### 4.2 Open

`store.open_project(folder, *, rebind=False, on_conflict=None) -> Project`:

1. Read `tuldok.json`; find or create the schema.
2. If `state.folder` exists and is a different real path, refuse with a message naming both paths, unless `rebind` is true.
3. List the definition files with size and SHA-256. If every file matches `definitions.file_sha256` and none was added or removed, attach without checking anything else.
4. Otherwise run `check_folder`. If it has errors, refuse and leave the database unchanged; the error carries the problems.
5. If a changed or removed file has an `unsaved` row, refuse and name those definitions, unless `on_conflict` is `keep` (keep the database's version) or `discard` (take the file).
6. In one transaction: upsert changed definitions, delete rows for removed files, rebuild `edges` from `graph.edges`, update `state`.

### 4.3 States

Milestone 2 knows five states. They are computed from the definition and the graph, never stored in a file:

| State | When |
| --- | --- |
| `cannot-rebuild` | its `earlier_work.rebuild` is `no`, or something it uses through an input, directly or further up, is `cannot-rebuild` |
| `needs-work` | not `cannot-rebuild`, and its `earlier_work.rebuild` is `needs-work` or something it uses through an input is `needs-work` |
| `not-built` | any other dataset, recipe, benchmark or step |
| `not-set-up` | an environment |
| `none` | a model or a chart |

Only `input:` edges carry these states upward. A benchmark is not made `cannot-rebuild` by one of its subjects.

### 4.4 Edit and save

- `project.set_definition(reference, text)` checks the document alone and against the project as it would then be (references, cycles), stores it with `unsaved = true` and updates `edges`.
- `project.remove_definition(reference)` refuses when another definition uses it; otherwise sets `removed = true`.
- `project.save()` writes each unsaved definition to its file (temporary file in the same directory, `fsync`, rename) and deletes the files of removed ones. Before writing a file it checks the file on disk still has `file_sha256`; if any does not, it writes nothing and names them.

### 4.5 The `Project` object

`store.open_project` returns a `Project` bound to one open connection. It reads from the database on demand and keeps no copy of the definitions in memory.

| Member | Returns |
| --- | --- |
| `summary()` | project id, name, folder, code root, counts per kind, counts per state |
| `definitions(kind=None)` | one row per definition: reference, kind, title, state, unsaved, removed |
| `definition(reference)` | the text, the document, the state, what it uses and what uses it (each with its role) |
| `graph()` | the nodes with their states, and the edges |
| `order()` | the references in build order |
| `status()` | unsaved and removed definitions; files added, changed or missing on disk since the last import |
| `set_definition`, `remove_definition`, `save` | section 4.4 |
| `close()` | closes the connection |

`store.drop_project(project_id, dsn=None)` drops a project's schema; tests and the `forget` command use it. A `Project` holds a session advisory lock for as long as it is open, so one process at a time has a project open; every command closes its `Project` before it exits. States are computed by a pure function `graph.states(definitions)` so the checker, the store and later milestones agree.

### 4.6 Command line

`python -m tuldok_project <command> FOLDER`, with `--database-url` or `TULDOK_DATABASE_URL`, and `--json` on every reading command:

| Command | Does |
| --- | --- |
| `open [--rebind] [--keep | --discard]` | 4.2; prints counts per kind and the time taken |
| `list [--kind K]` | reference, title, state |
| `show REFERENCE` | the definition, what it uses and what uses it |
| `graph [--order]` | nodes with state and edges; `--order` prints build order |
| `status` | unsaved and removed definitions; files changed on disk since import |
| `set REFERENCE FILE`, `remove REFERENCE`, `save` | 4.4 |
| `forget` | drops this project's copy from the database (`store.drop_project`); the folder is not touched |

### 4.7 Slices

| Slice | Files | Tests |
| --- | --- | --- |
| T3 store | `tuldok_project/store.py` (4.1, 4.2, 4.5), `graph.states` in `tuldok_project/graph.py` (4.3) | `tests/test_tuldok_project_store.py`, database |
| T4 edit and save | `store.py` (4.4) | same file, database |
| T5 commands | `tuldok_project/__main__.py` additions (4.6) | `tests/test_tuldok_project_cli.py` |
| T6 lab check | a timing run of the lab folder, recorded in `execution-ledger.md` | none |

T3 and T4 are written together by one agent. T5 and T6 follow.

## 5. Not in milestones 1 and 2

No change to `app.py`, `agent_api.py`, the browser code or any existing module. No HTTP route, no agent operation, no screen. No products, runs, environments set-up or result rows. The summaries in `results/` are checked but not imported.

## 6. Already settled for later milestones

- **Wiring into the app (milestone 7; see [spec-m3.md](spec-m3.md) for why it moved from milestone 3).** The new core gets its own start-up flag, its own route prefix and its own agent profile, with operations named `project.*`. `app.py` routes by a mode attribute in about eight places and `agent_api.capabilities` filters by profile; both need a third case. The agent contract fixtures under `tests/fixtures/` are pinned and must be regenerated with that change.
- **Environments (milestone 5).** Tuldok has no installer code today. Set-up will use `uv` (a venv for the definition's Python version, then the pinned requirements with the index URLs), or connect an existing interpreter; the check imports each listed package in a child process and compares versions, as the existing run-start checks do.
- **Running (milestone 6).** The process custodian in `recipe_process.py` (`launch`, `Handle`, the child-reaping helper) can run a plain command with small local changes: limits from the caller, subdirectories allowed in the output, longer streams truncated and not fatal. The queue in `runs.py` cannot be reused: admission, saving and recovery all require the old recipe material and one-use grants. The new core gets a small queue of its own that shares one capacity object (one GPU slot, the CPU and memory budget) with the existing queue while catalog mode exists, and keeps its safety rules: only the custodian's own end-of-children proof counts as stopped, and a restart never replays started work.
