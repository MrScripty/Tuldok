# Implementation spec: milestone 4, the rebuild plan

This continues [spec-m1-m2.md](spec-m1-m2.md) and [spec-m3.md](spec-m3.md). Section 1 of the first (rules for implementers) applies unchanged. The milestone changes no existing Tuldok file outside `tuldok_project/`.

**Done when:** `python -m tuldok_project plan <lab folder> recipes/pilot-dense-k1` lists the steps that build the pilot model in dependency order, with the disk each step declares, and executes nothing; and planning an earlier model that cannot be rebuilt says so and names the cause.

## 1. What a plan is

A plan answers: to have this definition's product on this machine, what has to be built, in what order, and what stands in the way. Making a plan reads the database only. It never runs a command, including a definition's `estimate` command: that is project code, and running it is a separate, explicit action that arrives with environments in milestone 5. Until then a step's figures are the ones its definition declares in `resources`.

## 2. Which definitions are in a plan

Start from the targets and follow these edges, repeatedly:

| Edge role | Followed |
| --- | --- |
| `input:<name>` | yes |
| `environment` | yes |
| `subject:<name>` (a benchmark's subject recipe) | yes |
| `model`, `cases` | no; nothing is built for them |
| `benchmark` (from a chart) | a chart target is replaced by its benchmark |

A `model` or a `chart` is never a step. A target that is a model has an empty plan and a sentence saying a model is not built.

## 3. Steps

Steps are in `graph.order` (everything after what it uses), numbered from 1. Each step has:

| Field | Content |
| --- | --- |
| `reference`, `kind`, `title`, `state` | from the definition and `graph.states` |
| `action` | `set-up` for an environment that is `not-set-up`; `build` for a `not-built` dataset, recipe, step or benchmark; `blocked` for `cannot-rebuild` or `needs-work` |
| `command`, `environment` | from `run`, placeholders not filled in; null when absent |
| `inputs` | for each input name, the reference that provides it and the named output if one is given |
| `resources` | as declared: `gpu`, `cpu_threads`, `memory_gb`, `wall_hours`, `disk_gb` |
| `estimate` | null in this milestone |
| `blocked_by` | for a blocked step: the definitions that are the cause, each with its reference, its own `earlier_work.rebuild` label and its reason. A cause is the step itself or anything it reaches through `input:` edges whose own label is `no` or `needs-work`. At most five are listed, nearest first, with a count of the rest |
| `subjects` | benchmarks only: `run`, the subject names the benchmark would run, and `skipped`, each with a name and a reason. A subject is skipped when its recipe is blocked. A subject with no recipe is run |

A benchmark is `build` when it is `not-built` and at least one subject would run. It is never blocked by a subject.

## 4. Summary

| Field | Content |
| --- | --- |
| `targets` | the references asked for, after replacing charts |
| `buildable` | true when no target is blocked |
| `counts` | steps by action |
| `gpu_steps` | `build` steps that declare `gpu: true` |
| `disk_gb`, `disk_unknown` | the sum of declared `disk_gb` over `build` steps, and how many `build` steps declare none |
| `wall_hours`, `wall_unknown` | the same for `wall_hours` |

Blocked steps are listed but not counted in the totals.

## 5. Interface

- `plan.build_plan(project, targets) -> dict` with `steps` and the summary fields. An unknown reference raises `ProjectError` `not-found`. It reads through the `Project` and holds no state.
- `python -m tuldok_project plan FOLDER TARGET... [--all] [--json]`. `--all` plans every dataset, recipe, step and benchmark. Text output is one opening sentence (what is planned, how many steps to build, to set up and blocked), then one line per step in order with its number, action, reference, what it needs, and GPU, disk and time as declared (`?` when not), then for each blocked target its causes with their reasons, then the totals. Exit status 0 whether or not the plan is buildable; `--json` carries `buildable`.

## 6. Slices

| Slice | Files |
| --- | --- |
| T9 plan | `tuldok_project/plan.py` (new), `plan` in `__main__.py`, `tests/test_tuldok_project_plan.py`, a "Planning a build" section in `docs/contracts/project-folder.md` |
| L4 lab | `lab:surrogate/datasets/`: a `--json` option on `plan` that prints one JSON object with `disk_bytes` and `items`, with a test; `lab:projects/surrogate-lab/datasets/*.json` for the two new datasets: `resources.disk_gb` from that command's output |
