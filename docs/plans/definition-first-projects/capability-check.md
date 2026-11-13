# Capability check: what deleting the old project mode removes

**Status: written 2026-11-12 for the owner's sign-off, and brought up to date the same evening after the Map workspace was built and the owner had looked at it. Not signed. Nothing is deleted until it is. The deletion is prepared and checked on a side branch ("The deletion as prepared", below) and reaches this branch only on sign-off.**

The [plan](plan.md) deletes the old project-files mode in milestone 8 on one condition: a written check that lists every capability of that mode as covered, moved or deliberately dropped, signed off by the owner. This is that check. It is a list of what Tuldok can do today through `python app.py --project-files-root ...` and what happens to each thing when that mode is gone.

## The short answer

For what the lab uses a project for (definitions, runs, results, charts, environments), the new format covers it, and since 2026-11-12 it has its own interface: the Map workspace ([plan](workspace-plan.md)), with the tabs Map, Data, Train, Benchmarks, Analysis and Overview, from which builds are planned, requested and approved and definitions are edited, branched and saved. The owner looked at it on the lab project that day ("looks ok. continue") and reported one fault, a full redraw where the page should update in place, which [spec-w4.md](spec-w4.md) repairs.

Five things are not covered and would be gone from projects:

1. **Annotated data inside a project.** Records, imports, annotation, review, saved searches, selections and frozen releases exist in the new format nowhere. They stay available in catalog mode, which this plan does not change. A project folder cannot hold them until the annotation plan is written.
2. **Looking inside the data from the project page.** The old page lists a project's records. The Map workspace shows each dataset as a card with its state and size; the record browser, the volume viewer, field slices and the Annotate tab of the mockup are not built (the workspace plan left them out, for a later plan).
3. **Studies, trials and candidate selection** as records Tuldok keeps. A trial becomes a recipe; the grouping lives in labels and notes.
4. **Producers and the built-in training graphs inside a project** (image generation, grounded review, caption and label proposals; the image, text and audio classifier trainings). Catalog mode keeps them.
5. **Reading a run's files through the agent interface.** An agent can read a run's record, its progress and the end of its logs, but not fetch its weights or other outputs; those are files on the same machine.

Two more follow from the deletion itself: the lab's old project folder (`projects/rheon-model-portfolio-unified-04`, still on this disk, no longer tracked) can no longer be opened by Tuldok, and forks and composing of projects go (a Git branch is a fork). The old code stays in Git history. Nothing in the database is dropped: the old project's working copy stays in PostgreSQL, unread.

## What would be deleted

| What | Size |
| --- | --- |
| 37 Python modules that only the old mode reaches | 20,437 lines |
| The old project page and the extraction page, with their scripts and styles under `static/` | 3,264 lines in 11 files |
| 145 `project_files.*` and 5 `project_transfer.*` operations in `agent_api.py`, the `project` capability profile, the two owner clients and their `mcp_stdio.py` flags | |
| The old mode's tests: 72 Python files and 18 JavaScript files | 22,675 lines |
| The documentation of the old mode under `docs/contracts/`, the runbooks and the READMEs. Its plans and ledgers under `docs/plans/` stay, as the record | |

The 37 modules: `project_artifacts`, `project_composition`, `project_custody`, `project_data`, `project_data_fork`, `project_dispatch`, `project_execution`, `project_extraction`, `project_files`, `project_fork`, `project_fork_composition`, `project_history`, `project_locks`, `project_material`, `project_material_fork`, `project_measurements`, `project_native_execution`, `project_native_preparation`, `project_native_process`, `project_producer_execution`, `project_producers`, `project_projection`, `project_record_dedupe`, `project_runtime`, `project_session`, `project_sources`, `project_store`, `project_study_execution`, `project_text`, `project_transfer`, `project_transfer_controller`, `project_validation_cache`, `project_validation_delta`, `project_working_store`, `project_workspace`, `retained_measurements`, `native_process_bootstrap`.

`project_cli.py` was listed here as a 38th module until the deletion was prepared. It stays: it is also catalog mode's command line for agents (`open`, `inspect`, `preflight`, `submit`, `status`, `download` and the rest), and tests that stay use it. It loses only the old mode's commands, `file-*` and `project-transfer`, and the flag `--owner-project-files`.

**What stays:** every remaining operation's contract, unchanged; catalog mode and everything it uses, including `projects.py` and `project_activity.py` (catalog mode's read-only inspection of project snapshots with `--project-root`), the access layer, the agent registry and clients, and the new `tuldok_project` package.

**Where the old code is tied to catalog mode.** Twelve import statements in three files reach into the 37 modules, so they change before anything is deleted:

| File | What it imports | What happens |
| --- | --- | --- |
| `app.py` | `project_workspace`, `project_transfer_controller`, `project_transfer.stop_source`, `project_store.ProjectStoreError` | the old mode's start-up flags, routes and error branches are removed |
| `candidate_packages.py` | `ProjectHistory`, `ProjectExecution`, for two `isinstance` branches | the two branches are removed |
| `pipeline.py` | `preparation_owner` (twice), `native_admission_wall_seconds` | the project-only branches are removed; the one small function catalog mode also uses moves into `pipeline.py` |

## Every capability

The old mode has 150 operations. They are grouped here by what they do; each group says what replaces it.

| Group | Operations | What it did | After deletion |
| --- | --- | --- | --- |
| Opening, saving and files on disk | 11: `status`, `new`, `open`, `save`, `close`, `files_inspect`, `file_get`, `file_history`, `file_adopt`, `files_adopt`, `file_adopt_deletion` | Create, open, save and close a project; see and adopt files changed on disk; a file's history | **Covered**, differently. `open`, `save`, `status`, `check`, `resolve_conflict`. Files changed on disk are imported on the next operation. Nothing stays open, so there is no close. History is Git's. A new folder is made by `new` |
| Forks and composing | 3: `save_as`, `compose`, `fork_info` | Copy a project to an independent fork; merge retained checkpoints of several projects | **Dropped**, as the plan decided: a Git branch is a fork |
| Data records and annotation | 30: `query`, `get`, `import_text`, `annotate`, the `data_*` reads and imports for text, image, audio, mesh, point cloud, volume, sequence and scientific fields, `data_annotate`, `data_rights`, responses and preferences, `source_register`, `source_references` | Hold data records in a project, annotate and review them, record rights, responses and preference judgments | **Not covered. Catalog mode only.** The plan put annotation data out of scope; it needs its own plan before a project folder can hold it |
| Selections, searches, releases | 11: `selections`, `selection_*`, `searches`, `search_*`, `release_preview`, `release_freeze` | Saved selections and searches over records; freezing a dataset release with its splits | **Not covered. Catalog mode only**, with the group above |
| Definitions | 27: `definitions`, `models`, `model_*`, `graphs`, `graph_*`, `recipes`, `recipe_*`, the material reads, `material_intent*`, `dependencies`, `policies`, `policy` | Model drafts, node graphs and recipes with revisions; immutable captured copies ("materials") of each; publishing a model | **Covered**, differently: seven kinds of plain definition file, `definitions`, `definition`, `graph`, `set_definition`, `remove_definition`, `save`. No revisions and no captured copies; Git has the history. **Not covered:** the built-in node graphs (image, text and audio classifier training), which remain in catalog mode |
| Studies, trials, candidates, lineage | 17: `studies`, `study`, `study_create`, `study_save`, `trial`, `trial_prepare`, `candidate`, `candidate_select`, `lineage`, `lineage_record`, `progression`, `progression_origins`, `snapshot`, `evidence`, `package_state`, `publication_result`, `expose_holdout` | A study of trials with a budget; choosing a candidate; recorded lineage between runs; the progression view; recording that held-out test results were looked at | **Partly covered.** Lineage is the graph's edges; progression is a chart form ordered by `trained_at`; evidence is a recipe's card and its results. **Dropped:** studies, trials and budgets as records, candidate selection, snapshots, and the record of held-out exposure. The lab's 205 earlier models keep their study and trial origin as labels and cards |
| Runs and execution | 24: `run`, `runs`, `run_document_segment`, `artifacts`, `artifact_status`, `artifact_resolve`, `execution_health`, the external preflight, approve, submit and cancel, the `execution_study_*` operations, `execution_reconcile_current`, `native_*` | Preflight, owner approval, submission, cancel, retry and recovery of runs; reading a run's documents and artifacts in pieces | **Covered:** `plan`, `request_build`, `approve_build`, `decline_build`, `cancel_build`, `build_requests`, `runs`, `run`, `progress`, `products`, `cancel_run`, `stop_run`. A retry is a new request. **Not covered:** reading a run's output files through the interface |
| Producers | 8: `producers`, `producer`, `execution_producer_*`, `execution_generation_resume`, `execution_grounded_review` | Image generation, grounded review and caption or label proposals run inside a project | **Not covered. Catalog mode only** |
| Measurements and analysis | 9: `measurement_*`, `retained_analysis`, `retained_analysis_export` | Import result sets, query and compare them, inspect one observation with its evidence, export an analysis | **Covered:** `import_values`, `results_overview`, `results`, `values`, `chart` (ranking, tradeoff, progression, comparison), `report`. Summaries are rows in the database, not documents re-read per request. On the page: the Benchmarks tab (accuracy against time with the frontier, error along the sequence, a compare set, the table of every fit) and the per-case values of the Analysis tab. **Not covered:** the pointer from one observation back to its evidence file |
| Runtimes | 5: `runtime_sources`, `runtime_inspect`, `runtime_capture`, `runtime_status`, `runtime_abandon` | Capture a copy of a Python environment with a listing of its files | **Covered**, differently: `environments`, `environment`, `connect_environment`, `check_environment`, and `set-up` on the command line. Versions are checked; nothing is copied or listed per file |
| Extraction from a catalog | 5: `project_transfer.*` | Stop a legacy catalog and extract it into a project | **Dropped.** The one project that needed converting is the lab, which its own script converts |

Outside the operations:

| Capability | After deletion |
| --- | --- |
| The old mode's commands in `project_cli.py` (`file-*`, `project-transfer`) | Gone. A project folder has `python -m tuldok_project`. The rest of `project_cli.py` is catalog mode's and stays |
| Opening the lab's old folder (`projects/rheon-model-portfolio-unified-04`) in Tuldok | Gone. The lab's converter reads that folder's files directly, and the old code stays in Git history |
| The old project page (`/project-files`), about twenty stacked form panels | Gone. The Map workspace is the project's interface |
| Byte-identical save, receipts, custody and checkpoint proofs | Dropped, as the plan decided |

## Before deletion, in milestone 8

These come first, so the deletion removes nothing the lab still needs:

1. **Done.** The lab's earlier weights and prepared inputs are adopted as products into Tuldok's per-project directory (owner decision, 2026-11-12: they stay on this machine and never go into Git): 203 recipes' outputs and 25 datasets' training data, 16.9 GB.
2. **Done.** The lab repository holds the new folder only, and the clean-install test of the plan's summary passed on fresh clones.
3. **Done.** A `new` command exists.
4. **Done.** The Map workspace is built in three phases and the owner has looked at each.
5. **Part of the deletion.** The twelve import statements above are cut and catalog mode's tests pass.

## The deletion as prepared

Prepared 2026-11-12 on the branch `chore/retire-old-project-mode`, in a working tree of its own. It is not on this branch. What it changes file by file, and each check with its result, is section 10.6 of [spec-m8.md](spec-m8.md) on that branch. In short:

| | |
| --- | --- |
| Removed | 143 files, 47,099 lines: 37 modules, 72 Python and 18 JavaScript test files, 11 files under `static/`, one script, four documents. 2,450 more lines are cut from 17 files that stay |
| Contracts | Every operation that remains is published byte for byte as before, in the `catalog` and the `project_folder` profile. The catalog's list goes from 115 operations to 110: the five `project_transfer.*` entries, which it listed as unavailable. The `project` profile is refused. The 145 `project_files.*` and 5 `project_transfer.*` operations are offered nowhere |
| Python tests | 3,149 before; 2,397 after, which is 3,149 less the 751 tests of the deleted files and one test of a deleted client class. No test that stays is newly skipped. One test that stays had to change: it pinned the digest of the whole catalog list and of the `project` profile, so it now pins the list without the five entries and checks that the old profile is refused. 23 tests fail before and after alike, none of them from the change: this machine has no training environment (numpy, scikit-learn), the test database's user may not create databases, and three tests of the CPU snapshot refuse this machine's Python directories |
| Project folder tests | 585 before, 586 after (the new test of the refused profile), all passing |
| JavaScript | All 49 remaining `tests/test_*.cjs` pass; `node --check` passes on all 54 scripts under `static/` |
| Browser | The workspace checks pass on their fixture and on the lab folder, read only. Of the 62 catalog checks the workflow runs, 49 ran here and 45 pass. One fails in its own clean-up of a temporary directory, the same way on the unchanged code; three need packages only the workflow installs. 13 were not run: they need training, a GPU or generated fixtures |
| Start-up | `--help` shows none of the removed flags and each is an argument error; Tuldok starts in catalog mode on an empty data directory and with `--project-folder` on the tiny example |

**Left for a later change.** About thirty lines in ten of catalog mode's files (`runs.py`, `synthetic.py`, the proposal modules and others) still ask the catalog for an attribute only the deleted modules set (`project_execution`, `project_sources`, `project_asset`, `project_availability`, `project_study_execution`). They can no longer be reached. They run through the code that starts and recovers runs, so removing them is its own reviewed change. `docs/decisions/external-project-authority.md`, the decision record of the old mode, stays as a record.

## Sign-off

The owner signs by saying so; the date and the words are recorded here and in the ledger.

- [ ] I accept that projects lose annotated data, looking inside the data from the project page, studies and trials, producers and the built-in training graphs, reading run files through the interface, forks, and opening the lab's old folder, as listed above, and the old project mode may be deleted.
