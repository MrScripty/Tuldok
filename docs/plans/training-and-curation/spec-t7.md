# Implementation spec: hyperparameter search on this machine

This is phase 7, the last, of [the training and curation plan](plan.md). It follows that plan's rule: Tuldok does not grow a training framework. A sweep varies the settings of a recipe the project already has and runs the project's own script for each trial, one after another, under the build machinery that already exists ([spec-m6.md](../definition-first-projects/spec-m6.md), [spec-m7.md](../definition-first-projects/spec-m7.md) section 4). What Tuldok adds is a definition (`sweep`), the schedule of trials, the decision to stop a poor trial early read from the metrics the script logs anyway ([spec-t1.md](spec-t1.md) section 2.1), and the views. Standard library only on the server; nothing of the project's code runs in Tuldok's server; the page follows [spec-w4.md](../definition-first-projects/spec-w4.md) and updates in place.

**Owner, 2026-11-19:** "Hyperparameter search could be usful, Tuldok is a little bit limited for that since it is not distributed, but it could still work well on tiny models localy."

**After this phase** a project can hold `sweeps/<name>.json`: the recipe it varies, the settings it varies and their ranges, a strategy (grid, random, or successive halving that stops poor trials early), one or two objectives read from the trials' training logs, and a budget (trials, minutes; one trial at a time). A build request for the sweep, approved once, runs the trials one after another. Each trial is a real recipe, derived from the varied one, drawn on the Map in a section of the sweep. The **Sweeps** tab shows a sweep's state live (trials done, running, pruned; best so far; budget used), its trials through parallel coordinates (its main view), its frontier when it has two objectives, and every trial in a table that opens it on the Map.

## 1. Decisions

- **One approval covers the whole budget.** A sweep is asked for with `request_build` naming it as the only target; the owner's request is queued, an agent's awaits approval, as for any build. What the approval covers is the sweep's text, the varied recipe's text, the texts of what that recipe needs (its inputs and environment) and the commit. Every trial is made by Tuldok from those two texts alone (section 4), so a trial is within the approval though its own text did not exist when it was approved. Changing the sweep or the recipe before the request runs makes it stale, as for any build.
- **Trials are recipes, kept in the project like any edit.** Each trial is written into Tuldok's working copy as a definition `recipes/<sweep>-<NNN>` with `derived_from` the varied recipe, `change` `sweep-trial`, and a `sweep` block naming the sweep, its number and the values it was given; it is an unsaved edit, and Save writes it into the folder like any other. Why the folder, and not a store of Tuldok's own until the owner keeps the winners: a trial's product is recorded against its definition text, and a run is only explained by a definition someone can read again; trials are small (one recipe each, a few hundred bytes); the folder is the place for definitions and high-level results, and keeping the pruned and failed trials too keeps the record of what was tried honest. The raw logs stay in the runs' directories on this machine, never in the folder. The owner who does not want a sweep's trials in Git removes them before saving (Remove on each, as for any definition); keeping only the winners by one control is not built (section 9).
- **Trials are never overwritten.** A trial named `<sweep>-007` that already exists with other values (the sweep's ranges changed since) is left alone, and the new trial takes `<sweep>-007-2` (then `-3`, …). An existing trial of this sweep with the same values and the same text is reused: built already, it is not run again.
- **Concurrency is one.** Trials run one after another on this machine; there is no distributed or parallel search.
- **Objectives are training metrics.** An objective is a series of the trial's `training/metrics.jsonl` (its last or best value), or the trial's last logged `time` or `step`. **A benchmark objective is not built:** a trial measured by a benchmark must be one of its subjects, and adding a subject changes the benchmark's definition, which makes every other subject of it out of date (builds.status compares the whole text); that would need a per-subject definition hash. The way to benchmark a sweep's winners is the existing one: add them as subjects once chosen.
- **Pruning is successive halving without resuming.** A trial cannot be paused and taken up again (there is no checkpoint contract to resume from), so the asynchronous rule of ASHA is applied as a stop rule: at each rung a trial reaches, it goes on only when it is among the best `1/factor` of the values recorded at that rung so far (section 5).

## 2. The definition: `sweeps/<name>.json`

A new kind, `sweep`, in a new directory `sweeps/`. Fields (unknown ones refused):

| Field | Rule |
| --- | --- |
| `format`, `kind`, `title`, `description`, `card`, `labels` | as every definition; `kind` is `sweep` |
| `recipe` | required: `recipes/<name>`, the recipe whose settings it varies. It must have `run.settings` written in the definition (not `settings_file`); Branch from here gives a branch its own copy |
| `parameters` | required: 1 to 16 objects, each with `path` (a dotted path into `run.settings`: keys separated by `.`, a part of digits indexes a list; every part but the last must exist in the recipe's settings as an object or a list; the last may be absent) and either `values` (1 to 64 distinct numbers, texts, booleans or null) or a range: `low` < `high` (numbers), `scale` `linear` (default) or `log` (then `low` > 0), `integer` (default false; `low` and `high` then whole numbers), `count` (2 to 64: how many points of the range a grid takes). Each path once |
| `strategy` | required: `{"kind": "grid"}` (every range then needs `count`), `{"kind": "random", "seed": <0 … 2^63−1>}`, or `{"kind": "halving", "seed", "metric", "better", "unit", "min", "factor"}`: `metric` a series name (1 to 200 characters), `better` `lower` or `higher`, `unit` `step` (default) or `time` (seconds), `min` the first rung (> 0; a whole number for steps), `factor` a whole number from 2 to 8 (default 3) |
| `objectives` | required: one or two objects with distinct `metric` (a series name, or `time` or `step`: the last logged), `take` `last` (default) or `best`, `better` `lower` or `higher`, optional `title` (at most 200 characters) |
| `budget` | required: `trials` (1 to 1,000), optional `minutes` (> 0, at most 10,080), optional `concurrency` (only 1) |

The checker reports as errors also: a `recipe` that is not a recipe (as any reference); a recipe without `run.settings`, or with `settings_file`; a path whose parents are not in the recipe's settings, or not objects or lists; a grid with a range without `count`; a grid of more than 100,000 points. As a warning: a grid with more points than `budget.trials` (the first in order are run). The edge from a sweep to its recipe has the role `varies`; it carries no state, and a plan does not follow it.

A recipe gains two optional fields: `change` may be `sweep-trial`, and `sweep` is `{definition: "sweeps/<name>", trial: <1 or more>, values: {<path>: <value>}}` (at most 16 values). The edge from a trial to its sweep has the role `sweep`, a map role like `derived`. The flattening of spec-t3 section 1 leaves `sweep` out (its values are in `run.settings` already).

## 3. The schedule

The trials are numbered from 1 in the order the strategy gives them; the same definition gives the same schedule every time. A value drawn from a range is rounded to 6 significant digits (`float(f'{x:.6g}')`), and an integer range's to `floor(x + 0.5)` within `low` and `high`.

- **Grid:** the Cartesian product in the order of `parameters`, the first varying slowest (`itertools.product`). A range's points are `low + i (high − low) / (count − 1)`, or on a log scale `exp(ln low + i (ln high − ln low) / (count − 1))`, for `i` from 0 to `count − 1`, rounded, repeats dropped. The first `budget.trials` points are run.
- **Random and halving:** `random.Random(seed)`; for each trial, each parameter in order draws: from `values`, `values[rng.randrange(len(values))]`; from a range, `u = rng.random()`, then `low + u (high − low)` or `exp(ln low + u (ln high − ln low))`, rounded. A draw equal to an earlier trial's values is dropped and drawn again; after 1,000 draws in a row with none new the schedule ends (a small space is exhausted).

## 4. A trial's definition

Made from the varied recipe's document as it is in the working copy: `format`, `kind`, `title` "<sweep title> · trial <n>", `description` "Trial <n> of sweeps/<name>: <path> = <value>, …", the recipe's `model` and `group` when it has them, `labels` `{"short": "T<n>"}`, `change` `sweep-trial`, `derived_from` the recipe, `sweep` as in section 2, and the recipe's `run` with each path set to the trial's value. Not carried over: `card`, `labels`, `earlier_work`, `compared_with`. JSON with two spaces of indentation and a newline at the end. It is stored with `set_definition`; a trial that does not check is recorded failed with the first problems, and the sweep goes on.

## 5. Running a sweep

The worker takes a request whose target is a sweep as any other (section 4 of spec-m7.md: the order, the expiry, the covers checked again), and runs it with `sweeps.execute`, which returns what `builds.execute` returns, so the request ends the same way:

1. The code is prepared once, at the approved commit (or as it is on disk for a scratch request), and one plan id is used for every run of the sweep, so the request's runs are all of them and Cancel reaches the one running.
2. What the varied recipe needs and is not built is built first, as a build would. A failure there fails the sweep.
3. Then trial after trial in the schedule's order. Before each: the trials budget (trials recorded in this run of the sweep, reused ones included), the minutes budget (wall time since the sweep started), and a stop asked for (Cancel, or Tuldok closing). The trial's definition is made and kept (section 4); its SHA-256 is added to what the build expects, and it is run like a build step.
4. While a trial runs, a watcher reads its `training/metrics.jsonl` every quarter second (spec-t1's reader, only the lines appended) and records the trial's latest step, time and objective values. It stops the trial cleanly (the run's cancel file: SIGTERM, then SIGKILL after the launcher's grace) when the minutes budget is spent, when a stop is asked for, or when halving prunes it.
5. **Halving.** The rungs are `min × factor^k`, k = 0, 1, … (at most 32), in steps or seconds. A trial reaches rung k at the first line whose step (or time) is at least the rung; its value there is the latest finite value of the metric on that line or before (none: nothing is recorded at that rung and the trial goes on). It is then compared with the values recorded at rung k by the earlier trials of this sweep run: with n values including its own, while n < factor it goes on; otherwise it goes on when fewer than ceil(n / factor) values are strictly better than its own, and is pruned otherwise. A line crossing several rungs records each. Every value is recorded, the trial's own included, whether it goes on or not.
6. When the trial's run ends, its objectives are read from its log (a pruned or stopped trial's as far as it got), and it is recorded **completed** (the run succeeded), **pruned**, **stopped** (budget or a stop), or **failed** (the run failed, or the trial did not check). A pruned trial's run is cancelled and its problem says it was pruned and at which rung.
7. The sweep ends **finished** (the schedule or a budget is spent), **cancelled** or **failed**; its request succeeds when it finished.

A trial reused from before (section 1) costs nothing: its objectives are read from its current product's run. A pruned trial of an earlier run of the same sweep with the same text is not reused; it runs again.

**State.** Two tables of the project schema: `sweep_runs` (one row per run of a sweep: the sweep, the request, the plan, the state and why it ended, the texts' SHA-256 it ran with, the strategy, objectives and budget, when it started and finished, the owner process) and `sweep_trials` (per trial: number, reference, values, state, whether reused, run, start and finish, seconds, the rungs reached with their values and decisions, the objectives, the latest line seen, the problem). A run left running by a process that is gone is marked failed when sweeps are read. Nothing of these tables is written to the folder.

**A sweep in a plan.** `plan` with a sweep as its only target answers the plan of what its recipe needs (the recipe itself left out) and one more step, of kind `sweep`: its action `build`, or `built` when its last run finished with the sweep's and the recipe's texts as they are now, or `blocked` when the recipe cannot be built for a reason other than its own `earlier_work` label; its reasons say what it will run, its resources the minutes as `wall_hours`. A sweep with other targets, or with `every`, is refused `invalid`. `request_build` with such a plan covers the recipe's text as well.

## 6. Operations

Two reads, `inspect`, in the `project_folder` profile only (the catalog's digest is unchanged):

| Operation | Arguments | Result |
| --- | --- | --- |
| `sweeps` | none | `sweeps`: each `reference`, `title`, `recipe`, `strategy` (its kind), `objectives`, `budget`, `state` (as in a plan), and `run`: null or the latest run's `id`, `state`, `ended`, `started_at`, `finished_at`, `counts` (by trial state), `best` |
| `sweep` | `sweep` (a reference or a bare name), optional `run` (a run id; default the latest) | `reference`, `title`, `description`, `recipe`, `parameters`, `strategy`, `objectives`, `budget`, `state`, `changed` (the latest run ran another text), `request` (the newest build request naming it: `id`, `state`, `requested_by`), `run` (null, or `id`, `state`, `ended`, `problem`, `started_at`, `finished_at`, `seconds`, `trials`, `counts`), `runs` (the last 20: `id`, `state`, `started_at`, `trials`), `trials` (each `number`, `reference`, `values`, `state`, `reused`, `run_id`, `seconds`, `rungs`, `objectives`, `latest`, `problem`, `defined`), `best` (`number`, `reference`, `value`, or null), `frontier` (the numbers of the completed trials on the frontier of the two objectives; empty with one), `rungs` (the rung points up to the last reached and one more), `axes` (as `benchmark_axes` answers: `metrics` the objectives, `settings` the parameters, `subjects` the trials) |

`map` gains a group per sweep that has trials (`id` the sweep's reference, `title` its title, `parent` the varied recipe's group, `sweep` true), and a trial's model a `sweep` (the reference); a trial's `group` in the answer is its sweep's group. The folder's `groups` and the other models are answered as before.

## 7. The page: the Sweeps tab

A tab **Sweeps** after Train (`#sweeps`; the chosen sweep in the address, `?sweep=`).

- **Head:** the sweep chooser, its recipe (a link to it on the Map), the strategy, objectives and budget in words, and **New sweep** for a session that may edit: a recipe chosen, a sweep's text written from it (its numeric settings as ranges around their values, random, its first logged series as the objective, 8 trials) into the editor's text view, kept with Keep.
- **State, live:** the run's state; trials completed, running, pruned, stopped, failed of the budget's; the minutes used of the budget's; the running trial with its step and objective values; best so far; and the controls: **Plan sweep** (the plan view, with Request build), **Approve** and **Decline** when a request awaits approval, **Cancel** while it is queued or running. Updated in place on every reading while a sweep runs: texts and bar widths set, no node added or removed.
- **Trials, parallel coordinates** (its main view): `parallel.js` with the sweep's axes, one line per trial in the colour of its state (completed, pruned, stopped, failed, running); dragging ranges filters the table below.
- **Frontier** with two objectives: the tradeoff chart of `charts.js` over the completed trials, the frontier marked; with one objective, the progression chart (the objective by trial number, best so far as a step line).
- **The table:** every trial: number, values, state (and the rung it was pruned at), objectives, seconds; a row opens the trial's drawer (the model's drawer), and **Open on the Map** selects it there.
- **Updating in place:** a reading that finds the sweep's answer changed updates the state texts, appends rows for new trials and sets the changed cells, and draws the charts again in their hosts; the tab is never emptied, and a person's own choice (another sweep, an axis) draws it again in place (`putInPlace`).

Trials carry the kind of change **Sweep trial** on the Map (a chip and a colour of their own, `--k-sweep-trial`, light and dark).

## 8. Slices

| | Slice | Files |
| --- | --- | --- |
| T7a | The kind, the checks, the schedule, the plan, the runner and its tables, the two operations, the map's groups | `tuldok_project/sweeps.py` (new), `schemas/sweep.schema.json` (new), `schemas/recipe.schema.json`, `documents.py`, `check.py`, `graph.py`, `plan.py`, `build_requests.py` (covers), `service.py` (dispatch, the reads), `store.py` (the tables), `operations.py`, `workspace.py`, `comparing.py` (`sweep` left out), `docs/contracts/project-folder.md`, `tests/test_tuldok_project_sweeps.py` (new), `tests/project_sweep_stand_in.py` (new), the service test's count |
| T7b | The Sweeps tab | `static/project-workspace/sweeps.js`, `sweeps.css` (new), `app.js` (the tab, the address), `adapter.js` (the kind), `parallel.js` (its selection and colours given by the caller), `static/project-workspace.html`, `app.py` (assets), `tests/browser_project_workspace_sweeps.cjs` (new) |

## 9. Tests

**T7a, `tests/test_tuldok_project_sweeps.py`:** the definition (schema and checker: each field, the paths against the recipe, a grid without count, the warning past the budget, the trial's `sweep` block and its edge); the grid and random schedules against the test's own arithmetic (product order, log points, rounding, integers, duplicates dropped, exhaustion); halving's decisions on fixture metrics logs against the test's arithmetic (rungs crossed together, values before the rung, n < factor, ties); budget enforcement (trials, minutes); the trial's text and its derivation link, reuse and the `-2` name; the plan of a sweep and its covers; end to end through a started `Service` with the stand-in `tests/project_sweep_stand_in.py` (plain Python, logging through `tuldok_log`, about a second a trial, its loss falling to a floor set by its settings): an agent's request approved once, trials run one after another, the poor ones pruned by halving, within the trials budget; a second sweep stopped by its minutes; the trials on the map in the sweep's group; the two reads; the operations in `project_folder` and not in `catalog`, the digest unchanged.

**T7b, `tests/browser_project_workspace_sweeps.cjs`:** on a fixture with the stand-in: a sweep made with New sweep and kept; asked for by an agent and approved on the tab; while the trials run the state block's counts and the latest step change across readings with the block the same element and no node of it added or removed; the frontier and parallel coordinates show every trial; a trial opens on the Map; light and dark, 1440 and 390 wide, no sideways overflow, no script error, no failed request.

**Regressions:** the project suite, the agent interface tests, `browser_project_workspace.cjs`, `_actions.cjs`, `_training.cjs`, `_compare.cjs`.

## 10. Out of scope

Running trials at once or on other machines; resuming a pruned trial (no checkpoint contract); Bayesian or other model-based strategies; benchmark objectives (section 1); a control keeping only a sweep's winners; any GPU run (the strategy is the same, the owner's word is needed first); the lab's models.
