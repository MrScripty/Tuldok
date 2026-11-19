# Plan: Definition-first projects

**Plan status:** `Approved` by the owner on 2026-11-10, with the decisions recorded under [Decisions](#decisions). Implementation proceeds one milestone at a time from the specifications in this folder.

**Written:** 2026-11-10, against Tuldok `d8d91fbf`, with the Rheon Surrogate Lab project as the test case.

## Summary

A project folder becomes a small set of plain files that say what to build and how. Everything built from them (datasets, weights, raw results, logs, history) stays on the local machine, in Tuldok's database and a local product store. Tuldok builds the dependency graph in its database, rebuilds products from the definitions in order, stores results as rows with summaries computed once, and draws charts from the summaries.

The test is the lab: a fresh clone of the lab, Tuldok and Rheon opens in seconds, shows the models, recipes and result charts, and lists the ordered steps that regenerate every dataset and model defined in it.

## Why: what the lab project shows

The lab's project folder in Git is 682 MB in 55,865 files. What the owner needs from it is about 12 MB (the cards, the recipes and a summary of results), plus dataset and benchmark definitions that do not exist in the project today.

| In the folder today | Size | Why it is there |
| --- | ---: | --- |
| 31 benchmark result sets | 342.5 MB | Each embeds a copy of its raw source documents (189 MB) so every value can be checked against them; the 478,660 values take 146 MB at about 300 bytes each |
| Note and card records | 77.5 MB | The full text of every revision; the actual text is about 13 MB |
| Python environment listings | 56.2 MB | Every file of the Python install with its checksum, listed twice per record (25,765 files for the GPU install) |
| Run records (460) | 54.8 MB | Complete run documents with their admission proofs |
| Fork, extraction, composition, snapshot and operation records | 44.8 MB | Bookkeeping about the project's own history |
| `project.json` | 34.1 MB | Lists every one of the 53,977 records |
| Graphs, model definitions, recipes, studies, trials | 24.3 MB | Definitions together with every past revision |
| Run observations | 14.3 MB | Exact copies of earlier run documents |
| One record per stored file | 6.9 MB | 51,244 files, mostly one per file of a Python environment |
| Stored model source files | 11.0 MB | Captured copies of each model's source code |
| Cards, recipes and notes as plain files | 15.2 MB | The part the owner asked for |

These are not accidents. They follow from six properties of the current design:

1. **The folder is the whole record set, by rule.** "Only the inventory in .tuldok/project.json confers authority" (`project_store.py:3`), every record must be listed, and each commit carries a digest over all of them. There is no way to leave a family or a record out of the folder.
2. **History is stored inside the records.** Every save of a note, model, graph or study appends the complete new revision (`project_files.py:342`, `project_material.py:466`). A fork keeps both the old record and the new one.
3. **Everything is proven byte by byte.** Environments are recorded as per-file checksum lists and re-checked before and after each run. Every stored file needs its own record. Every result value must match a pointer into an embedded source document (`retained_measurements.py:230`).
4. **Nothing derived is stored.** The database holds records as opaque bytes in two tables (`project_working_store.py:37`). Every chart request re-reads and re-checks the whole result-set files; the only aggregate is the maximum per model; there are two fixed chart specifications and a chart cannot be saved.
5. **Runs are chained by hand.** The run queue is first-in, first-out (`runs.py:1909`). A step that uses another step's output names it by exact checksum. There is no dataset defined by a generator, and nothing can say "this is missing, build it".
6. **Two modes that cannot be combined.** GPU environments and live run progress exist only in the older catalog mode; projects use the project-files mode, which has neither.

## Goals

Stated by the owner on 2026-11-10:

- **G1.** The Git folder holds only the minimum needed to rebuild everything: recipes, definitions, the necessary scripts and the high-level benchmark results. It does not hold generated data, or the data the results were calculated from.
- **G2.** Generated data lives only in Tuldok's local storage and can be regenerated.
- **G3.** Tuldok builds the dependency graph in its database and uses it.
- **G4.** Charts are not rebuilt from raw data on each request.
- **G5.** A clean install reproduces: clone, open, rebuild.
- **G6.** New work must be fully reproducible. Earlier lab work that cannot be reproduced is an accepted exception, and not every earlier model needs to be kept.

## Design

### 1. Three places

| Place | Holds | In Git | If it is lost |
| --- | --- | --- | --- |
| Project folder | Definitions, notes and cards, result summaries | Yes | It is the source; Git has it |
| Tuldok database | The imported definitions, the graph, run history, result rows and summaries, the activity log | No | Re-import the folder, then re-run or restore products |
| Product store (Tuldok's own directory for the project, on the machine) | Generated files: datasets, weights, raw result files, logs | No | Re-run the steps. Files that cannot be regenerated, such as the earlier weights, are single copies (section 9) |

The rule for deciding where something goes: if a person or an agent wrote it, it is a definition and belongs in the folder. If a command produced it, it is a product and stays local. The one deliberate exception is the result summary, which Tuldok writes into the folder so the results travel with the project.

### 2. Definitions

A definition is one small JSON file. There are seven kinds:

| Kind | Says | Produces |
| --- | --- | --- |
| `dataset` | The command that generates or prepares the data, its settings, the splits, and which other datasets or models it is built from | A dataset |
| `model` | The architecture: the code entry point and its configuration | Nothing by itself |
| `recipe` | How to train: the model, the training datasets, the settings and seeds, the environment, the resources | Weights |
| `benchmark` | The cases (a dataset and split), the metrics, the subjects, and how to group the summary | Results |
| `step` | Any other command whose output something else needs, such as building the reference solver | Files |
| `environment` | The Python version, the package versions, the device and how to install it | An installed environment on this machine |
| `chart` | Which benchmark and metric to plot, how to group, which chart form | Nothing; it is drawn from summaries |

Underneath, `dataset`, `recipe`, `benchmark` and `step` are the same thing: a command, its named inputs and its named outputs. The kinds exist so Tuldok knows where to show each one.

Two illustrative files for the lab (field names are settled in milestone 1; numbers are placeholders):

```json
{
  "kind": "dataset",
  "title": "Diversity scenes v1",
  "command": ["python", "-m", "surrogate.datasets", "generate", "diversity-v1", "--root", "{output}"],
  "estimate": ["python", "-m", "surrogate.datasets", "plan", "diversity-v1"],
  "inputs": {"solver": "reference-solver"},
  "environment": "lab-cpu",
  "splits": {"train": 148, "development": 24, "reserved": 52}
}
```

```json
{
  "kind": "recipe",
  "title": "Pilot stepper on dense scenes",
  "model": "divergence-free-stepper",
  "inputs": {"training": "sinusoidal-v1"},
  "command": ["python", "-m", "surrogate.train", "surrogate/configs/pilot-dense-k1.json", "{output}", "--device", "cuda"],
  "environment": "cuda-torch",
  "resources": {"gpu": 1, "wall_hours": 12, "disk_gb": 5},
  "outputs": {"weights": "model.pt", "log": "log.jsonl"}
}
```

Rules:

- **One file per definition.** The file name is its name, and other definitions refer to it by that name.
- **No checksums of other documents.** A definition never records the checksum of another definition or of a script, so changing one file never forces a change in another.
- **Checked on import.** Each kind has a schema; unknown fields are refused with the file and field named.
- **One set of files for everyone.** Tuldok's screens, an agent and a text editor all edit the same files.

### 3. The project folder

```
tuldok.json            project name, id, format version, where the code root is
datasets/*.json
models/*.json
recipes/*.json
benchmarks/*.json
steps/*.json
environments/*.json
charts/*.json
results/*.csv          result summaries, written by Tuldok on Save
notes/                 cards and notes as plain files
```

There is no inventory of records, no `records/` tree, no receipts and no stored-file records. Scripts stay where they are in the repository; definitions name them by path. Git is the history of every file in the folder.

For the lab, this folder is expected to be about 12 MB: the 205 cards (8.3 MB), the recipes (1.9 MB), the summaries (0.4 MB) and the definitions.

### 4. The graph

On import, Tuldok reads each definition's `inputs` and stores the graph in the database: one node per definition, one edge per input. Every node has a state:

| State | Meaning |
| --- | --- |
| Not built | No product on this machine |
| Built | A product exists and matches the current definition |
| Out of date | A product exists, but the definition, its code or one of its inputs changed since |
| Running, failed | A run is in progress or ended in error |
| Cannot be rebuilt | An earlier lab item whose inputs or command are lost (section 10) |

The graph is what the lineage map, the rebuild plan and "what does changing this affect" all read. It is not exported; it is rebuilt from the definitions whenever they change.

"Out of date" is found without chains of checksums. Each product keeps a copy of its definition as it was when built, the Git commit of the code, and which products it consumed. Tuldok compares those with the present state and says what changed. It is information for the owner, never a reason to refuse to run.

### 5. Products and runs

**What a product records.** The definition as run, the Git commit, the input products, the package versions actually found, the device, start and end times, the output files with their sizes, and the log. Checksums are computed only for files that never change once written (weights, result files), and for large datasets only when they are archived or checked on request.

**Runs start from committed code.** Tuldok runs each step from a clean copy of the commit, so a run is tied to a commit and later edits cannot disturb it. A run on uncommitted code is possible but is marked as a scratch run, and its product is never reported as reproducible.

**Tuldok sets up environments.** On an explicit action Tuldok installs the environment a definition describes (the Python version and the listed package versions), or connects one that already exists on the machine. It never does this on Open. Which interpreter on this machine fulfils an environment is a local setting outside Git.

**Environments are checked by version.** At the start of a run Tuldok checks that the Python and package versions match the `environment` definition and records what it found, including the GPU and driver. There is no per-file listing and no re-hashing of the install.

**Limits belong to the definition.** Wall time, disk and GPU come from `resources`, with defaults, in place of fixed constants such as the 30-minute GPU limit and the 64 MiB output cap. Large outputs stay where the step wrote them in the product store; they are not copied.

**GPU runs and live progress** work for projects: the log tail and the last progress line are available while a run is executing, to the screens and to agents.

**Plan, then build.** "Plan" lists the steps needed to build a chosen definition, in dependency order, with what is already built and each step's own estimate of disk and time. It runs nothing. "Build" queues those steps on the existing run queue (one GPU slot, several CPU slots). There is one queue and one launcher, as now; the graph only decides the order.

**Nothing runs on Open.** Opening a project reads files and never executes project code, installs anything or regenerates data. Setting up an environment is its own explicit action. A build needs the owner's approval of the plan. An owner can give an agent a budget (GPU hours, disk) for named definitions.

### 6. Results and charts

**What a benchmark writes.** One plain results file: a header (metrics with units, subjects, cases, grouping labels) and one row per value (subject, case, metric, value or the reason it is unavailable). It has no embedded source documents and no pointers. Its provenance is the run that wrote it.

**What Tuldok stores.** On completion the rows go into a database table, and a summary table is computed once: for each benchmark, subject, metric and declared group, the count, the unavailable count, mean, median, 10th and 90th percentile, minimum and maximum. A benchmark definition can name further statistics.

**What charts read.** A chart is a saved definition. Tuldok answers it from the summary table with one query. Looking at the individual cases behind a point reads the rows table, also by query. No result file is opened to draw a chart.

**What goes to Git.** Save writes each benchmark's summary to `results/`, with the commit and date it was produced. For the lab's existing results that is 2,541 rows by model and metric (4,407 with the per-value settings), about 0.4 MB. A benchmark definition can ask for its per-case table to be saved as well; that is off by default.

**On a fresh clone.** Tuldok imports the summaries, so every chart works at once. Per-case detail shows as not present until the benchmark is rebuilt or its product is restored.

The first set of chart forms covers the Benchmarks screen of the workspace redesign (accuracy against speed with the best-trade-off line, error across checkpoints, comparison of selected models) and the two existing charts.

### 7. Notes, history and bookkeeping

- **Notes and cards** are plain files in `notes/`. Git keeps their history. Tuldok does not store revisions in the folder.
- **Run history and the activity log** (who did what, approvals, admissions) stay in the database.
- **Forks, extractions, compositions, snapshots and operation receipts** are dropped from the project format. A Git branch is a fork.

### 8. Agent control

Every operation in this plan is available through the agent interface and the command line, with the same checks as the screens: read and check definitions, read the graph and node states, plan, request a build, watch a run, query results and summaries, and create charts. Because definitions are plain files, an agent with access to the repository can also write them directly and ask Tuldok to check them.

### 9. Product archive

**Decided by the owner on 2026-11-12: not built now.** The weights stay with Tuldok on the local system, in Tuldok's own per-project directory, and never go into the Git repository. That directory is the product store of section 1, so the question this section answered, "where do the weights live", is answered without an archive.

What the section proposed, kept for when a second machine needs the products: a product archive is a folder Tuldok writes on request, containing chosen products with their records, which can be copied to another disk or host and restored into another install.

### 10. The lab project: conversion and the exception

A one-time converter, owned by the lab, turns the existing project into the new folder:

- **Models.** Each of the 205 earlier models becomes a `recipe` with its card and its extracted training recipe, marked as earlier work. Each carries one of three labels: can be rebuilt, can be rebuilt after another model, or cannot be rebuilt with the reason. Today 115 trace only to scenes and formulas and 88 depend on earlier models.
- **Training sets.** The 26 earlier training sets become `dataset` definitions where the command is known. Only 5 have a recorded command, 10 depend on earlier models' weights, and a few have unknown or lost producers; those are recorded as they are and labelled.
- **Results.** The 31 result sets are imported once into the rows table and summarised.
- **Products.** The existing weights and prepared inputs (16 GB, of which most files exist only on the owner's laptop) are registered in the product store where they are, so nothing is recomputed.
- **The old folder** stays on disk, outside Git.

The owner may drop earlier models that are neither the best of their line nor needed by a later one; the converter takes a list.

New work under `surrogate/` (dataset definitions, the pilot recipe, the benchmark suites, the reference solver build) is written as definitions from the start and must pass the clean-install test.

## What changes in Tuldok

| Area | Today | Under this plan |
| --- | --- | --- |
| Project folder | Record inventory, receipts and record families, 18 of them in the lab's project (`project_store.py`, `project_working_store.py`) | Definition files, notes, summaries |
| Definitions | Graphs, model drafts, materials, recipe materials, each with revisions (`project_material.py`, `pipeline.py`, `recipe_contract.py`) | Seven kinds of plain file, no revisions in the file |
| Environments | Per-file listings, captured copies, re-hashing (`runtime_snapshots.py`, `torch_runtime.py`) | Version check and a record of what was found |
| Runs | Hand-chained, fixed limits, GPU and progress in catalog mode only | Planned from the graph, limits per definition, GPU and progress for projects |
| Queue and launcher | `runs.py`, `run_capacity.py`, `recipe_process.py` | Kept |
| Results | Self-proving documents re-read per request (`retained_measurements.py`, `project_measurements.py`) | Rows and summaries in the database |
| Charts | Two fixed specifications | Saved chart definitions |
| History and bookkeeping | Records in the folder (`project_history.py`, `project_fork.py`, `project_extraction.py`, `project_composition.py`) | Database only, or dropped |
| Access, approvals, agent transport | `access.py`, `agent_api.py`, MCP, CLI | Kept; operations are replaced |
| Catalog mode | The older data workspaces | Not changed by this plan |

The current project-files code is about 20,900 lines in 38 modules. Its record families refer to each other, so none can be removed alone. The proposal is therefore to build the new project format as a new, small core beside it, reusing the queue, the launcher, the database and the access layer, convert the lab, and then delete the old project-files modules. Tuldok's standing policy since 2026-10-20 already permits breaking format changes with an owner-led one-time migration.

## Earlier decisions this plan changes

| Decision | Now |
| --- | --- |
| "The external project directory owns scientific records. PostgreSQL is a disposable projection" (`docs/decisions/external-project-authority.md`) | The folder owns definitions and summaries. The database and product store own what was built. They are a cache that can be rebuilt by running, or restored from a product archive, not something to discard freely |
| "Save writes byte-identical files" and records stored as exact bytes (`docs/plans/database-working-store.md`) | No longer needed: definitions are plain authored files and Tuldok writes one only when it was edited in Tuldok |
| A clone with no database must reopen with identical history (`external-project-save-load/plan.md`) | A clone reopens with identical definitions, notes and summaries. Run history is local |
| "Do not introduce a second graph engine or scheduler" (`generic-scientific-projects/plan.md`) | Still one queue and one launcher. A project-level dependency graph is added, which that plan deferred |
| "No package install" and runtime capture by file listing | Tuldok installs and configures an environment on an explicit owner action, never on Open. The file listings go |
| Out of scope: "saved view persistence", "computed-on-open analyses" (`retained-analysis/plan.md`) | Charts are saved; summaries are computed when results arrive, not on open |

Kept as they are: the database is the working copy and Save is explicit; Open never executes project code; one run queue; owner approval before anything runs; no per-file source checksum maps.

## Milestones

Each milestone ends with a check against the lab. Sizes are relative.

| # | Milestone | Size | Done when |
| --- | --- | --- | --- |
| 1 | The folder, on paper. Schemas for the seven kinds, and the lab's converter | Small | The converted lab folder exists for the owner to read, is under 20 MB, and every file passes its schema |
| 2 | Open and Save. Tuldok imports the folder into new database tables and builds the graph | Medium | A fresh clone of the lab opens with an empty database in seconds and lists every dataset, model, recipe and benchmark with its links and state |
| 3 | Results and charts. Rows, summaries, saved charts, summaries written on Save | Medium | The lab's 31 result sets import once; per-model maxima equal today's comparison; charts are answered from summaries without opening a result file; a fresh clone draws them from `results/` alone |
| 4 | Plan. The rebuild plan with estimates | Small | Planning the pilot model lists its steps in order with disk estimates and runs nothing |
| 5 | Environments. Tuldok installs or connects an environment from its definition and checks it | Medium | On a machine without the lab's environments, Tuldok sets up the CPU and the GPU environment from their definitions and reports the versions it found. The GPU install is a multi-gigabyte download and needs the owner's go-ahead |
| 6 | Build. Runs from a commit, per-definition limits, GPU, live progress, results published by the run | Large | On a fresh clone Tuldok builds one tiny dataset, trains one tiny model on the GPU with live progress, benchmarks it and charts it. This run needs the owner's go-ahead |
| 7 | Serve the new core from the Tuldok app, with agent operations for all of the above | Medium | The app opens a project folder; an agent repeats milestone 6 through the interface alone |
| 8 | Convert the lab for good, then retire the old code. Earlier weights adopted into Tuldok's per-project directory, tracked export replaced, old project-files modules removed | Medium | The lab repository holds the new folder only; the clean-install test in the summary passes. Before any old module is deleted, a written check lists every capability of the old project-files mode as covered, moved or deliberately dropped, and the owner signs it off |

The workspace redesign (the Map variant chosen on 2026-11-03) builds on milestones 2 and 3 and gets its own plan.

## Out of scope

- The workspace screens themselves, and how charts are drawn (Vega as now, or plain SVG as in the mockups).
- Annotation data. The same rule applies to it (annotations are authored, so they belong in Git; source media are referenced), but its file layout is a separate plan.
- Retiring catalog mode.
- Sandboxing. Steps remain ordinary local processes with the user's access.
- Hosting for product archives.

## Decisions

Decided by the owner on 2026-11-10:

1. **The new project format is built beside the old one, and the old one is then deleted.** The condition is that we know the old one is no longer needed: milestone 8 does not delete anything until the written capability check is signed off.
2. **Runs require committed code**, with a marked scratch-run escape.
3. **Tuldok installs and configures environments.** This replaces the proposal's "checked, not installed".

Decided by the owner on 2026-11-12:

4. **The earlier weights stay with Tuldok on the local system**, in Tuldok's own per-project directory, which holds each project's data including its weights. They are not in the Git repository. No product archive is built now (section 9).

Still open, and needed only before milestone 8:

5. **Which earlier models to drop**, if any.
6. **Sign-off of the [capability check](capability-check.md)** before any old module is deleted.

## Risks

- **Less proof in Git.** A result in Git can no longer be checked against its raw source from the folder alone. Its provenance is the run record in the local database. This is the trade the goals ask for.
- **Local products are single copies.** Losing the machine loses weights and raw results that have no archive. This is already true today for most of the lab's stored files.
- **Size of the change.** It replaces the project-files core over several milestones. Each milestone is usable by itself and is checked on the lab before the next starts.
- **Summaries can lag.** The summaries in Git are as fresh as the last Save. Tuldok shows when results are newer than the saved summaries.
