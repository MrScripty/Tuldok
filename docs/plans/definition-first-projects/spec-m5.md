# Implementation spec: milestone 5, environments

This continues the earlier specs in this folder. Section 1 of [spec-m1-m2.md](spec-m1-m2.md) (rules for implementers) applies unchanged. The milestone changes no existing Tuldok file outside `tuldok_project/`.

**Owner decision, 2026-11-12:** code and tests only for now, plus connecting the two environments that already exist on the owner's machine. No package is downloaded or installed in this milestone's acceptance; the install path is exercised with a stand-in installer in tests and with `--dry-run` on the lab.

**Done when:** on the lab project, `connect` records the lab's existing CPU and GPU interpreters for `environments/lab-cpu` and `environments/cuda-torch`, the check reports the Python and package versions it found and both are `ready`; `set-up --dry-run` prints the commands that would install `environments/lab-cpu`; and `plan` no longer lists a ready environment as something to set up.

## 1. What is local

Which interpreter fulfils an environment on this machine is local: it lives in the project's database schema, never in the folder. An environment that Tuldok installs is a directory under the project's local home:

- **Local home:** `$TULDOK_PROJECT_HOME/<project id>/`, where `TULDOK_PROJECT_HOME` defaults to `~/.local/share/tuldok/projects`. It is created when first needed. Installed environments go to `<local home>/environments/<name>/`. Later milestones put products beside it.

```sql
CREATE TABLE environments (
  name text PRIMARY KEY,              -- environments/<name>
  interpreter text NOT NULL,          -- absolute path of the Python executable
  origin text NOT NULL CHECK (origin IN ('connected', 'installed')),
  recorded_at timestamptz NOT NULL,
  checked_at timestamptz,
  ok boolean,                         -- result of the last check; NULL before the first
  found jsonb,                        -- what the last check saw
  problems jsonb);                    -- list of sentences from the last check
```

## 2. States

An environment's state comes from that table: `not-set-up` when it has no row, `ready` when its last check passed, `failing` when its last check did not. `graph.states(definitions, local=None)` takes an optional mapping from reference to state that overrides what it computes for environments; `Project` passes the table's states everywhere it reports a state. No other definition's state depends on an environment.

## 3. The check

`environments.check(project, reference)` runs the recorded interpreter once, as a child process, and compares what it reports with the definition.

- **How it runs:** `[interpreter, '-I', '-c', PROBE, <the definition's packages and device as JSON>]`, with a minimal environment (`PATH=/usr/bin:/bin`, `LANG=C.UTF-8`, `HOME` set to a fresh temporary directory), that temporary directory as the working directory, and a time limit of 180 seconds. No project code is involved.
- **What the probe reports**, as one JSON object on stdout: the Python version; for each package named in the definition, its installed version from `importlib.metadata` or null; the interpreter's own path. Packages are not imported, with one exception: when the definition's device is `cuda` and `torch` is among its packages, the probe imports `torch` and reports whether CUDA is available, the CUDA version, the first device's name, and the driver line from `/proc/driver/nvidia/version` when it exists.
- **What must hold:** the Python version's `major.minor` equals the definition's `python`; every package's installed version equals the definition's exactly; for device `cuda`, CUDA is available. A device of `cuda` with no `torch` among the packages is a problem that says the check cannot see the GPU.
- **Result:** `ok`, `found` and `problems` are stored with the time. A probe that fails to start, times out, exits with an error or prints something that is not the expected object is a failed check with one problem saying which, and the first 400 characters of its error output.

The check is an explicit action. Opening a project never runs it.

## 4. Connect, set up, disconnect

- **`environments.connect(project, reference, interpreter)`** records an existing interpreter (an absolute path to an executable regular file, after resolving nothing: the path is stored as given) with origin `connected`, then checks it. The record is kept whether or not the check passes, so the problems can be read.
- **`environments.set_up(project, reference, *, dry_run=False, replace=False)`** installs the environment the definition describes and then checks it.
  - It needs the definition's `install.requirements`; without it the refusal says to connect an existing interpreter instead.
  - The installer is `uv`: the program named by `TULDOK_UV`, else `uv` on `PATH`. If there is none the refusal says so.
  - Commands, run in order with the code root as the working directory:
    1. `uv venv --python <python> <target>`
    2. `uv pip install --python <target>/bin/python -r <code root>/<requirements>` followed by `--extra-index-url <url>` for each of `install.index_urls`
  - `<target>` is `<local home>/environments/<name>`. An existing non-empty target is refused unless `replace` is true, in which case it is removed first.
  - Output of both commands goes to `<target>.log`. Each command has a time limit of one hour. A failed command leaves the log, removes the half-made target, records nothing and raises with the last lines of the log.
  - On success the interpreter `<target>/bin/python` is recorded with origin `installed` and checked.
  - `dry_run` returns the commands, the target and the log path and does nothing else: no directory is made, no program is run.
- **`environments.disconnect(project, reference)`** removes the record. It never deletes an installed directory; it returns that directory's path when the origin was `installed`.

## 5. Plan

A `ready` environment in a plan has action `ready` and is not counted as something to set up. A `failing` environment has action `set-up`, and the text says its last check failed.

## 6. Command line

| Command | Does |
| --- | --- |
| `environments FOLDER` | one row per environment: reference, state, origin, interpreter, when it was last checked, and under it the versions found and any problems |
| `connect FOLDER ENVIRONMENT INTERPRETER` | section 4; exit status 1 when the check fails |
| `check-environment FOLDER [ENVIRONMENT...]` | runs the check again, for all recorded environments when none is named; exit status 1 when any fails |
| `set-up FOLDER ENVIRONMENT [--dry-run] [--replace]` | section 4; with `--dry-run` prints the commands, the target and the log path |
| `disconnect FOLDER ENVIRONMENT` | section 4 |

`--json` applies to `environments`, `connect`, `check-environment` and `set-up`. An environment may be named bare (`lab-cpu`) or as a reference.

## 7. Not in this milestone

Running a definition's `estimate` command. It is project code and belongs with the launcher in milestone 6, where a command runs from a clean copy of a commit.

## 8. Slice

| Slice | Files |
| --- | --- |
| T10 environments | `tuldok_project/environments.py` (new), `tuldok_project/local.py` (new: the local home), hooks in `store.py` (the table, states passed through), `graph.states` (the `local` argument), `plan.py` (section 5), the commands in `__main__.py`, `tests/test_tuldok_project_environments.py`, and an "Environments" section in `docs/contracts/project-folder.md` |
