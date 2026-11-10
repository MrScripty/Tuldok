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
