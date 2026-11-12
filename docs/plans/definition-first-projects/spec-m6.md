# Implementation spec: milestone 6, build

This continues the earlier specs in this folder. Section 1 of [spec-m1-m2.md](spec-m1-m2.md) (rules for implementers) applies unchanged. The milestone changes no existing Tuldok file outside `tuldok_project/`, `tests/`, `docs/` and `examples/`.

**Owner decision, 2026-11-12:** spec, code and tests, and one tiny real end-to-end build on the GPU as the acceptance run. That run is done by the orchestrating session, not by an implementing agent. Agents run only stand-in commands that train nothing and never use the GPU.

**Done when:** on the example project in `examples/tiny-project/`, with the owner's two existing environments connected, `build` makes a tiny dataset, trains a tiny model on the GPU while `progress` shows its progress lines, benchmarks it, and `chart` draws the result; a second `build` does nothing because everything is built; and after a change to the recipe's settings the recipe and the benchmark show as out of date.

## 1. Decisions

- **The build is a foreground command.** `python -m tuldok_project build` makes the plan, asks for confirmation, runs the steps one after another and exits. There is no background service in this milestone; the queue is the command's own loop. Serving builds from the Tuldok app comes with milestone 7.
- **The launcher is new code in `tuldok_project/`**, not a change to `recipe_process.py`. That file's custodian is bound to the old recipe documents and is used by catalog mode; changing it risks code this plan does not own. The new launcher keeps its safety rules (section 3). This replaces the "reuse the custodian" note in section 6 of the first spec.
- **Every process of a run carries its run id.** The launcher sets `TULDOK_RUN_ID` in the child's environment. Descendants inherit it, so Tuldok can find and stop anything a run left behind, even after its own process died.
- **The project lock is not held while a step runs.** The build opens the project to plan and to record, and closes it while a command is executing, so `progress`, `runs` and `list` work during a build.

## 2. The code a run sees

`tuldok.json` gains an optional field:

| Field | Type | Rule |
| --- | --- | --- |
| `code_paths` | array | 1 to 64 paths relative to the code root, in normal form, no repeats; the parts of the repository a run needs. Absent means the whole code root |

`snapshot.prepare(code_root, code_paths, *, home) -> Snapshot`:

1. The code root must be inside a Git work tree; otherwise refuse and say a scratch run is the only option.
2. `commit` is `git rev-parse HEAD`. The run is **clean** when `git status --porcelain --untracked-files=no -- <code paths>` prints nothing.
3. A dirty tree is refused, naming up to ten changed files, unless the caller asked for a scratch run.
4. For a clean run the snapshot directory is `<local home>/code/<commit>/`, or `<local home>/code/<commit>-<digest>/` when there are `code_paths`, the digest being the first 12 hex characters of the SHA-256 of the sorted paths joined by newlines. If it does not exist it is made by `git archive <commit> -- <code paths>` extracted into a temporary directory beside it, made read-only, then renamed into place. It is shared by every run at that commit with those paths. The path of the code root inside the repository is preserved, so the snapshot's code root is `<snapshot>/<prefix>`.
5. A scratch run uses the code root in place and has `scratch` true.

`snapshot.changed_since(code_root, commit) -> set of paths` is `git diff --name-only <commit> HEAD` plus the paths `git status --porcelain --untracked-files=no` reports, relative to the code root; used for the out-of-date state.

Git is run with `git -C <dir>`, a fixed argument list, no shell, `GIT_OPTIONAL_LOCKS=0`, and a 60 second limit (ten minutes for `git archive`). `prepare` takes a `scratch` keyword, and errors are `SnapshotError` with a code.

## 3. The launcher

`launcher.run(argv, *, cwd, env, run_id, directory, limits, on_tick=None) -> Outcome` starts one command and stays with it until every process of the run is gone.

- **Start:** the child gets a new session, standard input from `/dev/null`, standard output and error appended to `<directory>/stdout.log` and `<directory>/stderr.log`, and `PR_SET_PDEATHSIG` set to `SIGKILL` so it dies if the launcher does. The launcher makes itself a child subreaper first, so orphaned descendants are reparented to it and can be reaped.
- **Environment:** exactly what the caller passes, plus `TULDOK_RUN_ID`.
- **While it runs,** every half second: has the child exited; is the wall-time limit passed; does `<directory>/cancel` exist. Every five seconds: is the size of `<directory>` over the disk limit. `on_tick` is called with the elapsed seconds.
- **Stopping** (limit passed, cancel, or the launcher receiving `SIGINT` or `SIGTERM`): `SIGTERM` to the child's process group, up to ten seconds of grace, then `SIGKILL` to the group.
- **After the child has exited, always:** find every process of this user whose environment contains `TULDOK_RUN_ID=<run_id>` (reading `/proc/<pid>/environ`), kill them, reap, and repeat until none is left or ten seconds have passed.
- **Outcome:** `state` is `succeeded` (exit status 0, nothing forced), `failed` (non-zero exit), `timed-out`, `over-disk`, `cancelled`, or `unknown` (a process of the run could not be stopped). It also carries the exit status, the elapsed seconds, the number of stray processes that had to be killed, and the directory's final size. A run that left strays behind after a zero exit is still `succeeded`, with the count recorded.

`launcher.strays(run_id) -> list of pids` and `launcher.stop_strays(run_id)` do the search and kill alone, for a run whose launcher is gone.

`launcher.progress(directory) -> dict` reads at most the last 8 KiB of each log, without following links, and returns `stdout` and `stderr` as text (invalid bytes replaced, control characters other than newline and tab removed), their total sizes, and `event`: the last complete standard-output line in the existing closed format `{"format": "tuldok_progress_v1", "stage", "completed", "total", "metrics"}` with the same bounds as today (stage and up to eight metric names match `[A-Za-z0-9][A-Za-z0-9_.-]{0,63}`, `0 <= completed <= total <= 1000000`, metrics finite numbers, lines over 4096 bytes ignored), or null.

## 4. Runs and products

```sql
CREATE TABLE plans (
  id text PRIMARY KEY, created_at timestamptz NOT NULL,
  targets jsonb NOT NULL, steps jsonb NOT NULL, scratch boolean NOT NULL);

CREATE TABLE runs (
  id text PRIMARY KEY,
  reference text NOT NULL, subject text NOT NULL DEFAULT '',   -- a benchmark's subject name, else ''
  plan_id text NOT NULL,
  state text NOT NULL,              -- queued, running, succeeded, failed, timed-out, over-disk, cancelled, unknown
  scratch boolean NOT NULL, commit text NOT NULL,
  definition text NOT NULL,         -- the definition file's text as run
  settings text,                    -- the settings file's text as run, when the step has one
  inputs jsonb NOT NULL,            -- input name -> {reference, run_id, output}
  environment jsonb,                -- {reference, interpreter, found}
  argv jsonb NOT NULL, env jsonb NOT NULL,
  directory text NOT NULL,          -- <local home>/runs/<id>
  owner_pid integer, owner_boot text,
  queued_at timestamptz NOT NULL, started_at timestamptz, finished_at timestamptz,
  exit_status integer, seconds double precision, bytes bigint, strays integer,
  problem text);

CREATE TABLE products (
  run_id text PRIMARY KEY,
  reference text NOT NULL, subject text NOT NULL DEFAULT '',
  directory text NOT NULL,          -- <run directory>/output
  outputs jsonb NOT NULL,           -- output name -> {path, role, bytes}
  current boolean NOT NULL);
CREATE UNIQUE INDEX products_current ON products (reference, subject) WHERE current;
```

A run directory holds `output/` (what `{output}` names), `settings.json` when the definition has inline `settings`, the two logs, and `cancel` when cancellation was asked for. A product is a succeeded run's `output/`; it stays where it was written. Making a product current makes the previous one for the same reference and subject not current. Nothing is deleted in this milestone.

**A run that was left `queued` or `running`** by a build whose process is gone (its `owner_pid` is not running, or `owner_boot` is not this boot) becomes `unknown` the next time builds are looked at, with a problem saying so. It is never restarted. `stop RUN` kills its strays.

## 5. States

Added to the states a `Project` reports, through the same `local` argument as environments:

| State | When |
| --- | --- |
| `running` | it has a `queued` or `running` run |
| `built` | it has a current product, and none of the conditions for `out-of-date` holds |
| `out-of-date` | it has a current product, and: the definition's text differs from the run's; or its settings file's text differs; or an input's current product is not the run recorded in `inputs`, or that input has none; or the run was not a scratch run and one of the definition's `sources` (or a path under one) is in `snapshot.changed_since(code root, run commit)` |
| `failed` | it has no current product and its latest run ended `failed`, `timed-out`, `over-disk` or `unknown` |

A scratch product is `built` with a mark that it is a scratch product; it never becomes out of date because of code. A benchmark has one product per subject: it is `built` when every subject that would run has a current product and none is out of date, `not-built` when none has one, and `out-of-date` otherwise. `cannot-rebuild` and `needs-work` are unchanged and take precedence only when there is no current product.

`plan` gains the action `built` for a step that is `built`, which is not counted as work; an `out-of-date` or `failed` step is `build`, and the text says why.

## 6. Running a step

`builds.execute(project_folder, plan, *, confirm, extra_env=None)` does, for each step in order:

1. **Environment steps:** check the environment again. If it is not `ready`, stop the build and say to set it up or connect it.
2. **`built` steps:** skip.
3. **`build` steps**, once per subject for a benchmark:
   - Resolve placeholders: `{output}` is `<run directory>/output` (created empty); `{settings}` is `<run directory>/settings.json` for inline `settings` or `<snapshot code root>/<settings_file>`; `{inputs.<name>}` is the input's current product directory, or the named output's path inside it; `{subject.name}` is the subject's name; `{subject}` is the subject's `argument` with `{recipe}` replaced by that recipe's current product directory, or the subject's name when it has no `argument`.
   - `argv[0]` of `python` becomes the environment's recorded interpreter. Any other program is looked up on `PATH`.
   - The child's environment is: `PATH`, `HOME`, `USER`, `LOGNAME`, `LANG`, `LC_ALL` and `TZ` from the caller where set; `PYTHONDONTWRITEBYTECODE=1` and `PYTHONUNBUFFERED=1`; `CUDA_VISIBLE_DEVICES` set to the empty string unless the step declares `gpu: true`, in which case it is left as the caller has it; then the definition's `env` with placeholders filled; then `extra_env`.
   - The working directory is the snapshot's code root (or the code root for a scratch run).
   - Limits: `wall_hours` as declared, default 24; `disk_gb` as declared, default 50.
   - A step that declares `gpu: true` holds an exclusive lock on `$TULDOK_PROJECT_HOME/gpu.lock` while it runs, waiting for it if another build has it.
   - The run row is written before the command starts and updated when it ends. The project is closed while the command runs.
4. **After a succeeded run:** every declared output must exist under `output/`; a missing one makes the run `failed` with a problem naming it. For a benchmark, the output with role `results` is read as a `tuldok_results_v1` values file for that benchmark and subject and imported; a file that fails the check makes the run `failed`, with the first problems in the run's `problem`. Then the product is recorded and made current.
5. **Any other outcome** stops the build. Later steps are not run.

`confirm` is called with the plan before anything runs and returns true to proceed. A plan with a blocked target is refused before `confirm`.

## 7. Estimates

`builds.estimate(project_folder, targets)` runs, for each `build` step in the plan that has `run.estimate.command`, that command through the launcher from the same snapshot, with a five minute limit, `{output}` naming a fresh path that does not exist, and the definition's `env`. A step whose estimate command or `env` names an input that has no current product is skipped with that reason. The command's standard output must be one JSON object; its numeric `disk_bytes`, `wall_seconds` and `items` are stored in `estimates(reference PRIMARY KEY, definition_sha256, values jsonb, measured_at)` and shown by `plan` beside the declared figures, marked as estimates, for as long as the definition's text is unchanged.

## 8. Command line

| Command | Does |
| --- | --- |
| `build FOLDER TARGET... [--all] [--scratch] [--yes] [--env NAME=VALUE]...` | prints the plan, asks to proceed unless `--yes`, runs it; prints one line when each step starts and ends, with the run id; exit status 0 when every step succeeded or was already built, 1 otherwise |
| `runs FOLDER [REFERENCE]` | the runs, newest first: id, reference, subject, state, started, seconds |
| `run FOLDER RUN` | one run: its row, its outputs, and the last progress event |
| `progress FOLDER RUN [--follow]` | the progress event and the log tails; `--follow` repeats every two seconds until the run ends |
| `cancel FOLDER RUN` | asks a running run to stop by creating its `cancel` file |
| `stop FOLDER RUN` | for a run whose builder is gone: kills its strays and marks it `unknown` |
| `products FOLDER [REFERENCE]` | current products: reference, subject, run, size, directory, scratch |
| `estimate FOLDER TARGET...` | section 7 |

A run may be named by its id or an unambiguous prefix of at least six characters. `--json` applies to `runs`, `run`, `progress`, `products` and `estimate`.

## 9. The example project

`examples/tiny-project/`, with `project/` (the folder) and `code/` (its code root, `code_root` `../code`):

| Definition | What it does |
| --- | --- |
| `environments/cpu`, `environments/gpu` | Python 3.12 with numpy 2.3.5, and Python 3.14 with torch 2.14.0+cu132 and numpy 2.5.3: the versions of the two environments on the owner's machine. No `install` |
| `datasets/waves` | `python make_waves.py` writes a small `.npz` of noisy sine curves, with train and test splits, from a fixed seed; a second or two on the CPU |
| `models/small-net` | a three-layer network in `net.py` |
| `recipes/small-net-a` | `python train.py` fits it for a number of updates from its settings, printing a `tuldok_progress_v1` line every 50 updates; needs a GPU and refuses to run without CUDA; about a minute |
| `benchmarks/held-out` | `python bench.py` scores one subject on the test split and writes a `tuldok_results_v1` file with a per-case error and a time per case; subjects are `small-net-a` and a `predict-zero` baseline |
| `charts/held-out-ranking`, `charts/held-out-tradeoff` | ranking of the error, and error against time |

The scripts are short and plain, with no dependencies beyond numpy and torch. A `README.md` says how to connect the two environments and build.

## 10. Slices

| Slice | Files | Depends on |
| --- | --- | --- |
| T11 launcher | `tuldok_project/launcher.py`, `tests/test_tuldok_project_launcher.py` | nothing |
| T12 snapshot | `tuldok_project/snapshot.py`, `code_paths` in the `tuldok.json` schema, checker and contract, `tests/test_tuldok_project_snapshot.py` | nothing |
| T13 builds | `tuldok_project/builds.py`, hooks in `store.py`, `plan.py`, the commands, `tests/test_tuldok_project_builds.py`, a "Building" section in the contract | T11, T12 |
| T14 example and estimates | `examples/tiny-project/`, section 7, its command and tests | T13 |

Tests use stand-in commands run by the test interpreter: scripts that print progress lines, write files, sleep, ignore `SIGTERM`, fork children that outlive them, or fill the disk limit. No test uses a GPU, torch, or the network.
