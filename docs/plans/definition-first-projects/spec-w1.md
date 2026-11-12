# Implementation spec: the Map workspace, phase 1: what the map reads

This is phase 1 of [the Map workspace plan](workspace-plan.md). Section 1 of [spec-m1-m2.md](spec-m1-m2.md) (rules for implementers) applies, with the import rule as amended by [spec-m7.md](spec-m7.md). This phase adds fields to the project folder format and three read operations. It adds no page.

**Done when:** for the lab folder, one `map` answer holds its 206 models in their sections with the kind of change of each, the lines from a model to the one it was derived from, the 26 authored comparisons, and a track value for every model that has a result on the track's benchmark; `note` returns a model's card; and `recipe_results` returns one model's results across benchmarks.

## 1. Fields added to the format

All are optional. A folder without them is as valid as before.

**`tuldok.json`:**

| Field | Type | Rule |
| --- | --- | --- |
| `groups` | array | 0 to 200 objects, in the order their sections are shown. Each: `id` (1 to 64 characters, `[A-Za-z0-9][A-Za-z0-9_.-]*`, once), `title` (1 to 200 characters), `parent` (optional: the `id` of another group; a group is never its own ancestor), `description` (optional, at most 2000 characters). Unknown fields are refused |
| `map` | object | `chart`: the reference of a chart definition whose form is `progression`. Its benchmark, metric and statistic are the map's track. Unknown fields are refused |

**A recipe:**

| Field | Type | Rule |
| --- | --- | --- |
| `group` | text | the `id` of one of the project's groups |
| `change` | text | `training-policy`, `architecture`, `refinement` or `component`: the kind of change this model makes |
| `derived_from` | reference | another recipe: the model this one was branched from. Never itself, and following `derived_from` never returns to where it started |
| `compared_with` | array | at most 50 objects, each `recipe` (the reference of another recipe, once in the list), `explanation` (1 to 2000 characters) and `excerpt` (optional, at most 2000 characters). Unknown fields are refused |

The label `short`, when a recipe has it, is the text of its node on the map (at most 16 characters are shown). It is a label like `trained_at`, not a new field.

**The checker** reports as errors: a `group` that is no group of the project; a group whose `parent` is unknown or that is its own ancestor; a `derived_from` or a compared `recipe` that is not a recipe of the project or is the recipe itself; a loop of `derived_from`; a `map.chart` that is not a chart of the form `progression`.

**The graph** gains two edge roles, `derived` and `compared`, from the recipe that carries the field to the recipe it names. They appear in a definition's `uses` and `used_by`. They carry no state, the plan does not follow them, and `order` ignores them: a comparison may run both ways.

## 2. Operations

Three operations of the `project_folder` profile, all for a credential with `inspect`, none a mutation.

**`map`**, no arguments. Result:

| Key | Holds |
| --- | --- |
| `groups` | the project's groups in their order, each with `id`, `title`, `parent`, `description` and `models`, the number of recipes that name it |
| `models` | one object per recipe, ordered by the label `trained_at` ascending, then those without one, by name. Each: `reference`, `title`, `short` (the label, or null), `group`, `change`, `derived_from` (each null when absent), `trained_at` (or null), `state`, `adopted`, `card` (the recipe's `card` path, or null), `value` and `count` (the track's statistic for this recipe and how many cases it summarises, or null), `benchmarks` (in how many benchmarks it has result rows) |
| `edges` | `{from, to, kind}`: `derived` for each `derived_from`, and `input` for each recipe that uses another recipe as an input |
| `comparisons` | `{from, to, explanation, excerpt}` for each compared pair, as authored |
| `track` | null, or `{chart, benchmark, metric: {id, title, units, better}, statistic}` from `map.chart` |

The answer is made from the definitions and the summary rows in the database with a fixed number of queries. No results file, values file or note is read. When a recipe is the subject of the track's benchmark under several subject names, the best value by the metric's `better` is its value.

**`note`**, argument `path`: a path relative to the folder's `notes/` directory, in normal form. Result `{path, text}`. The file is read from the folder on disk without opening the project: a regular file, no link in the path, at most 1 MiB, UTF-8. Anything else is refused `not-found`.

**`recipe_results`**, arguments `recipe` (a reference) and optional `group` (as in `results`; absent means the ungrouped rows only). Result: `rows`, the summary rows of every benchmark subject whose recipe this is, each row as in `results` with `benchmark` and `subject` added, ordered by benchmark, subject and metric; and `benchmarks`, the names of those benchmarks.

**Command line:** `map FOLDER [--json]` prints, per group in order, its title, how many models it has and how many of each kind, then the totals, the lines and comparisons counted, and the track. `note FOLDER PATH` prints a note.

## 3. The lab folder

The lab's converter writes the new fields, and the notes file that held groups and comparisons (`notes/model-groups-and-comparisons.json`) is no longer written:

- `groups` in `tuldok.json`, from the groups it already extracts, in their order, and `group` on each recipe.
- `compared_with` on each recipe that has comparisons.
- `change`, `derived_from` and the label `short`, from a seed file in the lab, `scripts/earlier-model-map.json`, made once from the workspace mockup's data file: for each earlier fit, the mockup's short label (`C74`), its kind (`training` becomes `training-policy`, `composition` becomes `component`) and the first of its parents. The seed says where it came from: the mockup inferred kinds and parents from the text of the model cards, so they are starting values for the owner to correct in the definitions.
- `map.chart`: the lab's chart of the form `progression` for the benchmark the mockup's accuracy track used (worst pressure relative L2 on the consumed fitting requests), or a new chart definition for it when none of the lab's eight charts is that.

## 4. Slices

| Slice | Files | Notes |
| --- | --- | --- |
| T17 | the schemas, `check.py`, `graph.py`, a new `tuldok_project/workspace.py` for the three operations, their rows in `operations.py` and `service.py`, `map` and `note` in `__main__.py`, tests, and the sections of `docs/contracts/project-folder.md` | the `minimal` fixture gains groups, a derivation, a comparison and a `map.chart` |
| L6 | `lab:scripts/build_tuldok_project.py`, `lab:scripts/earlier-model-map.json`, `lab:scripts/tests/`, the regenerated `lab:projects/surrogate-lab/` | after T17 |
