# Execution ledger: definition-first projects

## 2026-11-10 — milestone 1, the folder

**Branch:** `feat/definition-first-projects` from `d8d91fbf`, nothing committed. Lab work on `reorg/reproducible-lab-20261102`, nothing committed.

**Done by:** three Opus 5.5 agents at medium effort, one per slice, from [spec-m1-m2.md](spec-m1-m2.md); each slice reviewed and re-run by the orchestrating session.

| Slice | Files | Result |
| --- | --- | --- |
| T1 checker | `tuldok_project/{documents,folder,graph,check,__main__}.py`, `tuldok_project/schemas/*.json`, `tests/test_tuldok_project_check.py`, `tests/fixtures/tuldok_project/minimal/` | 59 tests pass. Independent check: eight hand-broken folders (symbolic link, duplicate key, stray directory, cycle, bad placeholder, unknown field, missing reference, clean) all reported correctly |
| T2 summaries | `tuldok_project/results.py`, `tests/test_tuldok_project_results.py` | 56 tests pass. Independent check: statistics and file round trip recomputed by hand |
| L1 lab folder | `lab:scripts/build_tuldok_project.py`, `lab:scripts/tests/`, `lab:projects/surrogate-lab/` | 21 tests pass; `--check` passes; folder is 12 MB in 486 files; checker reports 0 errors, 8 warnings. Independent check: all 645 ungrouped rows of `results/original-pressure-cases.csv` recomputed from the nine source result sets, none disagree |

Command for the Tuldok tests: `.venv/bin/python -m unittest discover -s tests -p 'test_tuldok_project_*.py'` (115 tests, 2 s).

**The lab folder holds** 206 recipes, 32 datasets, 18 benchmarks with summaries (4,589 rows), 4 steps, 2 environments, 1 model, 205 cards. 459 of 477 result subjects are linked to a model; the other 18 are solver assemblies or execution variants.

**Format changes made during the milestone** (all in the spec):

- `earlier_work.rebuild` gained `needs-work`: nothing is lost, but the recorded command does not run as written. Labels state a fact about the item alone; Tuldok derives from the graph whether anything upstream blocks a rebuild.
- Earlier items name tracked files, not the staged copies under `runs/`; files the old Tuldok generated for a run are not sources.
- Checker choices accepted as implemented: paths must already be in normal form; a missing field is reported at the field's own pointer; knock-on problems from one broken reference are suppressed; a missing final newline in a results file is a warning.

**Findings:**

- Of the 205 earlier models, 177 are labelled `no` and 28 `needs-work`; carried through inputs, 183 and 22. No earlier training command runs as written: all 203 take arguments the old Tuldok supplied.
- 173 earlier recipes name code or run material that is in Git only inside the old project folder's blob store, or not at all: 375 distinct files, 7.8 MB (1.1 MB Python, 1.9 MB JSON, one 4.0 MB zip, 0.8 MB arrays).
- Of the 26 earlier training sets and their recording groups, 13 have an exact command; the rest have none or several.
- Authored content in the old notes that the new folder does not carry: 19 task groups and 26 comparisons between models (`notes/00-models.portfolio.json`).

**Open for the owner:** whether to bring the earlier runs' code into the lab repository; whether to carry the authored groups and comparisons as notes; commit of both repositories' new files.

**Lab changes the new-work definitions need** (for milestones 4 and 6): a `--json` option on `surrogate.datasets plan`; the benchmark result in Tuldok's results format; `spectral-composition` cannot run on a fresh clone; no lock file yet for the GPU environment; the reference solver needs Rust, which the format's environments do not describe.

**Remaining in milestone 1:** slice D1, the format contract under `docs/contracts/`, after the owner has read the folder.

## 2026-11-10 — milestone 1 follow-up and milestone 2, open and save

**Owner decisions:** bring the earlier runs' code into the lab; keep the authored comparisons; commit on branches, no push and nothing on `main`; start milestone 2.

**Commits** (none pushed). Tuldok `feat/definition-first-projects`: plan and spec `d55903f8`, checker and summaries `3297f8dd`, format contract `3e787e06`, store `e027ed3f`, then the commands. Lab `reorg/reproducible-lab-20261102`: folder and build script `d0df92180`, earlier run code and comparisons `89cac8b4d`.

| Slice | Files | Result |
| --- | --- | --- |
| L2 earlier code (lab) | `lab:earlier-run-code/` (184 files, 1.6 MB), `lab:projects/surrogate-lab/notes/model-groups-and-comparisons.json`, build script and tests | 26 tests pass; `--check` passes; checker 0 errors, 8 warnings (sources of two recipes that are not on this machine) |
| D1 contract | `docs/contracts/project-folder.md`, link in `docs/README.md` | every example in it passes the checker |
| T3, T4 store | `tuldok_project/store.py`, `graph.states`, `tests/test_tuldok_project_store.py` | 37 tests. Independent check: bad edit refused, removal of a used definition refused, save refused after the file changed on disk, reopen with that conflict refused until told to discard, no schema left behind |
| T5 commands | `tuldok_project/__main__.py`, `tests/test_tuldok_project_cli.py`; helpers shared with the store made public in `folder.py` and `check.py` | 16 tests |
| T6 lab check | timing below | targets met |

Command for all tests: `.venv/bin/python -m unittest discover -s tests -p 'test_tuldok_project_*.py'` with `TULDOK_DATABASE_URL` set to a disposable cluster (168 tests, 16 s; 45 are skipped without a database).

**Milestone 2 acceptance, on the lab folder** (263 definitions, 2,266 edges):

| Command | Whole process | Reported by `open` | Target |
| --- | --- | --- | --- |
| first `open`, empty database | 0.93 s | 0.72 s | under 10 s |
| second `open`, nothing changed | 0.20 s | 0.01 s | under 1 s |
| `list`, `graph --order` | 0.2 s each | | |

States: 216 cannot be rebuilt, 27 need work, 17 not built, 2 environments not set up, 1 model.

**Earlier models after L2.** With their code in Git, 158 of the 205 are `needs-work` on their own label and 47 are `no` (25 start from weights whose producing model is not identified, 18 miss only arrays or an archive, 2 have no command, 2 name scripts not on this machine). Carried through inputs, 27 need work and 178 cannot be rebuilt, because most read a training set that cannot be rebuilt.

**Accepted as implemented:**

- A `Project` holds a session advisory lock while open; a second open, or `forget`, is refused as busy.
- The schema is created inside the import transaction, so a failed first open leaves nothing behind.
- The unchanged-folder fast path compares SHA-256 of definition files only. It does not see changed `results/*.csv`, notes or stray entries; milestone 3 must add results files to it.
- `keep` on a conflict keeps the database text and records the file's new digest, so the next save overwrites the file on purpose.
- `save` accepts a file that already holds the text to be written, so an interrupted save can be retried.
- Every command opens the project first, so the command-line `status` never shows pending disk changes; a conflict appears as a refusal. `Project.status()` remains meaningful for a long-lived process.
- Two settings files copied into `earlier-run-code/` (`fine-tuning.json`, `distillation.json`) carry per-tensor checksums of starting or teacher weights. They are kept as settings; the owner can reverse this in the build script's table.

**For milestone 3:** import `results/*.csv` into summary tables; result rows from runs; saved charts; the first changes to existing Tuldok files (`app.py`, `agent_api.py`) to serve the new core, with its own start-up flag, route prefix and agent profile.

## 2026-11-10 — milestone 3, results and charts

**Owner instruction:** continue with milestone 3. Spec: [spec-m3.md](spec-m3.md).

**Scope change.** Serving the new core from the Tuldok app moved from this milestone to milestone 7, where every operation of the new core is registered once and the pinned agent contract fixtures are regenerated once. In its place this milestone has a static report page. The plan's milestone table says so.

**Commits** (none pushed). Tuldok `feat/definition-first-projects`: spec `5ce63364` and `1bc187b0`, results in the database `e297f5ee`, charts and report `f352f5ec`. Lab `reorg/reproducible-lab-20261102`: summary shape, values files and charts `06c254ee9`, subject titles `fff10a4a1`.

| Slice | Files | Result |
| --- | --- | --- |
| T7 results | `tuldok_project/result_rows.py`, hooks in `store.py`, `results`, `values`, `import-values` | 39 new tests |
| T8 charts and report | `tuldok_project/charts.py`, `chart`, `report`, contract sections | 24 new tests, including one that makes every file read fail while each chart is answered |
| L3 lab | build script: one ungrouped row and one row per single group value; `--values-output`; eight chart definitions | 32 tests; `--check` passes |

Command for all Tuldok tests as before: 231 tests, 30 s.

**Acceptance, on the lab project:**

| Check | Result |
| --- | --- |
| Open into an empty database imports every summary row | 4,716 rows from 16 results files; first open 1.1 s, second 0.01 s |
| Import of the per-case values | 477 files, 478,660 values, 12 s; 296 MB in the local database |
| `save` after that import rewrites `results/*.csv` byte for byte | Nothing to save; the lab folder unchanged in Git |
| A chart is answered without reading a result file | proven by test; the lab's progression chart of 127 models answers from the summary table |
| An export of the committed lab alone draws its charts | `check` 0 errors, `open` 0.8 s, `report` writes 8 charts (four with data, four for the new benchmarks that have no results yet) |

The drawings were viewed as rendered images in both themes by the implementing agent and by the orchestrating session.

**Accepted as implemented:**

- Removing a benchmark keeps its `results_files` digest until `save` deletes the file, so the changed-on-disk check still applies.
- Setting a benchmark also drops summary rows for removed metrics and removed group keys.
- `status` gained `results_changed`; `save` returns `results_written` and `results_deleted`.
- A values file must have all six top-level fields and at least one value.
- A subject with no row, a count of 0, or no value for the chosen statistic is listed as missing and never drawn.
- Ranking bars on a linear axis start at zero; on a logarithmic axis at the decade below the smallest value.
- A metric's units of `1` are not shown.
- The report shows the folder's name, not its absolute path.

**Follow-ups, none blocking:**

- `charts.py` and `result_rows.py` call a few private names of `store.py` and `results.py` (`Project._execute`, `results._COMMIT`, `_produced_is_valid`, `_benchmark_names`); make them public when those files are next touched.
- The `result_values` table costs about 620 bytes a row with its two indexes; revisit if a project holds tens of millions of values.
- Text widths in the drawings are estimated without font metrics.
- The design tokens' "good" colour fails one of the palette validator's checks; it is always accompanied by a line, a label or a key.

**Next:** milestone 4, the rebuild plan with estimates. It needs the lab's `surrogate.datasets plan` to print JSON.
