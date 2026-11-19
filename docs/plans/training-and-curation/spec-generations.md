# Implementation spec: data generations

A small feature beside [the training and curation plan](plan.md). A project can say which **generation** of its source its data comes from (the solver, simulator, sensor or corpus release that made it), and Tuldok keeps the generations apart: a model trains on one generation's data, a dataset made from others keeps their generation, and mixing them is an error unless the definition says it is meant. The label is general, not of one project; it is opt-in, so a project that writes none checks as before.

**Owner, 2026-11-19,** about the lab's fluid models: "I want to make sure that we maintain the separation where our data sets that we currently have continue to be used for the models that we currently have. And then from this point onwards, we will use only the new version of Rheon with new models. That way we don't poison our data."

## 1. Decisions

- **A label, not a kind.** A generation is a name (`rheon-reference-v1`, `rheon-v2`), 1 to 64 characters of `a-z0-9._-`, written on the definitions that bring data in. There is no list of generations to declare first; the names in use are the project's generations. `mixed` is not a generation name (it is the word of the escape below).
- **Declared where data enters, inherited downstream.** A dataset or a step may declare `generation`. A dataset or step that declares none takes the generation of its data inputs (the entries of `run.inputs` that name a dataset or a step), whatever made it: `freeze`, `select`, `embed`, `annotate`, `import` with dataset inputs, or the project's own command. Inputs without a generation are left out of this (they are unlabelled, not another generation).
- **Data never mixes silently.** A dataset or step whose labelled inputs have more than one generation is an error naming each input and its generation; declaring a generation does not settle it, because a declared generation that differs from an input's is an error too. There is no escape for data: a cross-generation dataset is made from two that are each one generation, under a recipe that says it mixes.
- **A recipe's generation is computed, never written.** It is the generation of the datasets and steps it trains on (its data inputs). A recipe whose data inputs have more than one generation is an error ("mixes data generations …") unless it declares `"generations": "mixed"`, a deliberate cross-generation experiment, which is then a warning, and its generation is `mixed`. A recipe derived from a parent of another generation is allowed (fine-tuning across generations) and shown on the Map.
- **A benchmark says what it measures.** Its subjects may span generations only when it declares `"generations": "mixed"`; otherwise a warning lists the subjects' generations (a warning, so that projects that label their data later still check). It may declare `"generation"` for its cases; its cases' data (`cases.dataset` and the data inputs of its run) is checked against that as a dataset's inputs are, and without a declaration its generation is that data's.
- **Unlabelled stays unlabelled.** Nothing without a generation and without labelled inputs gets one, and nothing is reported about it. The answers of projects without generations are what they were: the reads add `generation` only where there is one.

## 2. Fields

| Kind | Field | Rule |
| --- | --- | --- |
| `dataset`, `step` | `generation` | optional; the name rule above. Its data inputs' generations must equal it |
| `recipe` | `generations` | optional; only `"mixed"` |
| `benchmark` | `generation` | optional; the name rule. Its cases' data must equal it |
| `benchmark` | `generations` | optional; only `"mixed"`: its subjects may span generations |

The schemas (dataset, step, recipe, benchmark) hold the syntax; `tuldok_project/generations.py` the rules across files, called at the end of `check.check_map`, so the folder's check and the working copy's `set_definition` both report them. A cycle of inputs is the cycle rule's problem; the generation walk stops at it.

## 3. Reads

- `map`: a model has `generation` (its computed generation, `mixed` included) when it has one.
- `definition`: a dataset, step, recipe or benchmark has `generation` when it has one (computed as above).
- `definitions`: a row of a dataset, step, recipe or benchmark has `generation` when it has one.

## 4. The page

- **The Map:** a model's generation is a small chip after its name in the list and in its drawer, and a line of its tooltip. A model whose parent has another generation shows it (the drawer: "from a model of `<generation>`"; the chip's title). A filter group **Generation** in the Map's bar, beside the kinds of change, when any model has one: one chip per generation and one for models without; pressing them filters as the kinds do (faint on the lane map, hidden in the list).
- **The Data tab:** a dataset's card and drawer show its generation as the same chip.
- Everything is drawn where it already is; no node of a live block is rebuilt on a reading for it.

## 5. Tests

`tests/test_tuldok_project_generations.py`: inheritance through steps and datasets of several levels; inputs that disagree, and a declaration that differs; a recipe of one generation, of two (the error), of two declared mixed (the warning, `mixed`); a cross-generation parent (no problem); a benchmark whose subjects span generations (the warning), declared mixed (none), its cases against its declaration; the reserved name and the pattern through the schema; an unlabelled project unchanged (no problem, no `generation` in the reads); the reads of the working copy. `tests/browser_project_workspace_generations.cjs`: the chip in the Map's list and drawer and on the Data tab, and the Generation filter. Regressions: the project suite, the agent tests, `browser_project_workspace.cjs`, the lab's project checked with 0 errors.

## As built

Built on `feat/data-generations` from `main` d8a57a1d.

- **`tuldok_project/generations.py`** (new) holds the rule: `resolve(documents)` (pure, {reference: document}) gives every generation and every problem; `check_generations` is called at the end of `check.check_map`, so the folder's check and `set_definition` report the same; `labelled` feeds the reads. Datasets and steps are walked once each, a cycle of inputs stops the walk.
- **Schemas:** `generation` on dataset, step and benchmark (`^(?!mixed$)[a-z0-9._-]{1,64}$`), `generations` (`const "mixed"`) on recipe and benchmark. Branch from here and a sweep's trial carry a recipe's `generations` with its run (`workspace.draft_branch`, `sweeps.trial_document`).
- **Reads:** `map` (a model's `generation`), `definition` and `definitions` (a dataset's, step's, recipe's or benchmark's), each only where there is one, so the answers of unlabelled projects are byte for byte as before (the workspace tests compare whole answers). `definitions` and `definition` read every document once more for it; `map` adds no query. The operation descriptions and the catalog digest are unchanged.
- **Found while building:** a dataset declaring a generation while its input step has another is an error, as section 1 says; the browser check's second dataset therefore takes its own solver step. `mixed` counts as one generation in a benchmark's subjects, so a benchmark measuring a mixed recipe beside a one-generation recipe warns too.
- **The page:** `tree.js` (`genChip`, the filter in `visibleFor`), `screens.js` (the Generation group in the Map's bar, the chip and "from a model of …" in the drawer), `app.js` (`state.generations`, `toggleGeneration`), `adapter.js` (a model's `generation`), `tabs.js` (the Data tab's card and drawer), `base.css` (`.gen`, dashed `.gen.crosses`). In the list, a name with a chip is cut before the chip; below 600 px wide the list leaves the chip out so the name has the room (the drawer and the filter keep it). The filter is not kept in the address (the kinds are not either).
- **Tests:** `tests/test_tuldok_project_generations.py`, 18 (15 without a database, 3 with). `tests/browser_project_workspace_generations.cjs`, 7 PASS (`--shots <dir>` writes screenshots).

### Runs at the end

Disposable PostgreSQL under `/tmp/claude-1000/gen`, no GPU: the project suite 916 OK (898 before, plus 18); `test_agent_api test_agent_negotiation test_agent_http` 43 OK, 4 skipped; `browser_project_workspace_generations.cjs` 7 PASS; `browser_project_workspace.cjs` 24 PASS; `tuldok_project check` of the lab's `projects/surrogate-lab` 0 errors, 8 warnings (none about generations; the lab writes no generation yet).

### Not done

The lab's definitions are not labelled (that is the owner's edit: a `generation` on its reference solver step or its datasets, `rheon-reference-v1`, and `rheon-v2` on the new ones). Inputs without a generation do not count against a labelled one, so an unlabelled dataset can still be mixed into labelled data unnoticed. No filter or chip on the Train, Benchmarks or Compare tabs; no generation in the plan view or in a model card's text; the editor shows the problems as for any rule but has no control of its own for the field.
