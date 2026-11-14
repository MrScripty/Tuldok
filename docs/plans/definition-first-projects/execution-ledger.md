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

## 2026-11-10 — milestone 4, the rebuild plan

**Owner instruction:** continue with milestone 4. Spec: [spec-m4.md](spec-m4.md).

**Commits** (none pushed). Tuldok `feat/definition-first-projects`: spec `58cd0d14`, then the plan. Lab `reorg/reproducible-lab-20261102`: `plan --json` and declared disk `391d1e188`.

| Slice | Files | Result |
| --- | --- | --- |
| T9 plan | `tuldok_project/plan.py`, `plan` in `__main__.py`, `tests/test_tuldok_project_plan.py`, the "Planning a build" contract section | 30 new tests, including one that makes process creation and file opening fail while a plan of every target is made |
| L4 lab | `lab:surrogate/datasets/__main__.py` (`plan --json`), its test, and `resources.disk_gb` in the two new dataset definitions (1.4 GB and 135.2 GB) | the lab's 72 `surrogate` tests pass |

Command for all Tuldok tests as before: 261 tests.

**Acceptance, on the lab project:**

- `plan recipes/pilot-dense-k1`: two environments to set up, then the reference solver, `datasets/sinusoidal-v1` (1.4 GB declared) and the recipe (GPU), in that order; nothing run.
- `plan recipes/water-residual-linear-cuda-training--72953af8f73b705f`: one blocked step, with its two causes and their reasons (its own command needs adapting; its training set has no single command line).
- `plan --all`: 17 steps to build, 2 to set up, 243 of 260 targets blocked; 137 GB of disk declared.

**Settled during the milestone** (in the spec):

- Making a plan never runs a definition's `estimate` command. A step's figures are those its definition declares; running estimates is an explicit action that arrives with environments.
- Edges are not followed out of a blocked step, and a benchmark subject whose recipe is blocked is named as skipped without becoming a step. A plan lists work that can be done, and each blocked target once.
- A benchmark with no subject that would run is blocked, with no cause listed.
- An absent `resources.gpu` means no GPU is needed.
- Targets and `--all` can be combined; giving neither is a usage error.

**Follow-ups, none blocking:** `plan.py` reads all documents through the private `Project._documents`; a public accessor belongs with the other private-name cleanups. No lab definition declares `wall_hours`, so plans show no time.

**Next:** milestone 5, environments. Its acceptance installs packages (about 1 GB for the CPU environment, several GB for the GPU one), which needs the owner's go-ahead.

## 2026-11-12 — milestone 5, environments

**Owner decision:** code and tests only, plus connecting the two environments that already exist on the owner's machine. Nothing downloaded or installed. Spec: [spec-m5.md](spec-m5.md).

**Commits** (none pushed). Tuldok `feat/definition-first-projects`: spec `1a788494`, then the environments slice.

| Slice | Files | Result |
| --- | --- | --- |
| T10 environments | `tuldok_project/environments.py`, `tuldok_project/local.py`, hooks in `store.py`, `graph.states(definitions, local)`, the `ready` action in `plan.py`, five commands, `tests/test_tuldok_project_environments.py`, the "Environments" contract section | 41 new tests; every install in tests runs a stand-in for `uv` |

Command for all Tuldok tests as before: 302 tests, 71 s.

**Acceptance, on the lab project** (throwaway database, local home in a scratch directory):

| Step | Result |
| --- | --- |
| `connect lab-cpu <lab>/.venv/bin/python` | ready: Python 3.12.3, numpy 2.3.5, torch 2.8.0+cpu |
| `connect cuda-torch <Pumas>/torch-versions/v2.14.0/venv/bin/python` | ready: Python 3.14.7, numpy 2.5.3, torch 2.14.0+cu132, CUDA 13.2 on the RTX 5090 Laptop GPU |
| `set-up lab-cpu --dry-run` | prints `uv venv --python 3.12 <target>` and `uv pip install ... -r tuldok/requirements-cpu.lock --extra-index-url https://download.pytorch.org/whl/cpu`; nothing run, nothing created |
| `set-up cuda-torch --dry-run` | refused: the definition has no `install.requirements` |
| `plan recipes/pilot-dense-k1` | both environments `ready`, nothing to set up |

**Accepted as implemented:**

- The check reads versions with `importlib.metadata` and imports nothing, except `torch` for a `cuda` environment.
- A failed check is a stored result with problems; the record is kept so they can be read.
- Editing an environment definition does not clear its stored result; the state is as of the last check.
- An environment's record is dropped when its definition is removed.
- A dry run still refuses for a missing `install` section, a missing installer or a non-empty target.
- The installer's commands inherit the caller's environment and run in their own process group with a one-hour limit; the log is replaced on each set-up.
- New `ProjectError` codes: `not-set-up`, `no-install`, `no-installer`, `target-exists`, `install-failed`.

**Not verified:** a real `uv venv` or `uv pip install`; the probe on Python other than 3.12 and 3.14 (it ran on both in the acceptance run); a failing GPU.

**One deviation by the implementing agent:** it ran `connect` once against `/usr/bin/python3`, outside the repository's virtual environment, during a manual demonstration. The probe is read-only and the demonstration project was removed.

**Open:** the lab has no lock file for the GPU environment, so `cuda-torch` can be connected but not installed. Running a definition's `estimate` command moved to milestone 6.

**Next:** milestone 6, build: runs from a commit, the launcher and queue, products, live progress, results published by the run. Its acceptance trains one tiny model on the GPU, which needs the owner's go-ahead.

## 2026-11-12 — milestone 6, build

**Owner decision:** spec, code and tests, and one tiny real end-to-end build on the GPU as the acceptance run. Spec: [spec-m6.md](spec-m6.md). No implementing agent used the GPU; the acceptance run was done by the orchestrating session.

**Commits** (none pushed), Tuldok `feat/definition-first-projects`: spec `fe2dd56a` and `b9d32e9a`; snapshot `4191d46f`; launcher `e49635b9`, then its custodian `35fdafc6`; builds `f8367c17`; run commands and estimates `419d6ed2`; the example project `d3340b5f`.

| Slice | Files | Result |
| --- | --- | --- |
| T11 launcher | `tuldok_project/launcher.py` | 37 tests |
| T12 snapshot | `tuldok_project/snapshot.py`, `code_paths` in `tuldok.json` | 30 tests |
| T13 builds | `tuldok_project/builds.py`, the states, `build`, `runs`, `products`, the `buildable` fixture | 30 tests |
| T14 run commands and estimates | `run`, `progress`, `cancel`, `stop`, `estimate`, estimates in `plan`, the "Building" contract section | 17 tests |
| T15 example | `examples/tiny-project/` | checker 0 errors; scripts smoke-tested on the CPU |

Command for all Tuldok tests as before: 423 tests, about 2.5 minutes.

**Design change found in review.** The first launcher made the calling process a child subreaper. An independent test (a command that double-forks a daemon and leaves a background child) showed everything was stopped, but one zombie per run was left in the caller, and the same mechanism could take the exit status of a caller's unrelated child. Each run now has its own custodian process (`python -m tuldok_project.launcher`), which is the subreaper, reaps everything it adopts and writes the outcome. Repeating the test, with the daemon also clearing its environment: nothing alive, no zombie in the caller, and the caller's unrelated child reported its true exit status.

**Independent checks of the builds slice** (the `buildable` fixture in a scratch Git repository): first build, 4 runs; second build, nothing run; a committed settings change made the recipe and its benchmark out of date with the reason and rebuilt only those; an uncommitted change was refused without `--scratch`; with `code_paths` the snapshot held exactly the named files and a step whose script was not named failed; a failing step stopped the build; no process left carrying a run id.

**Acceptance run, `examples/tiny-project`** (throwaway database, local home in a scratch directory, the owner's two existing interpreters connected):

| Step | Result |
| --- | --- |
| `connect cpu`, `connect gpu` | both ready |
| `build benchmarks/held-out --yes` | exit 0 in 23.4 s: dataset 0.3 s, training 13.9 s on the GPU, benchmark 3.1 s and 1.7 s for its two subjects |
| progress read from another process while training ran | six observations, from update 1,300 to 6,000 of 6,000, loss falling from 0.0020 to 0.0006 |
| the training run's record | from the snapshot of commit `d3340b5f`, exit 0, 0 strays, outputs `model.pt` (349 KB) and `log.json` |
| `chart held-out-ranking` | `small-net-a` median error 0.0376, `predict-zero` 0.871, 400 cases each, from the results the benchmark runs published |
| `chart held-out-tradeoff`, `report` | drawn; the tradeoff drawing was viewed as a rendered image |
| second `build` | nothing run: everything built |
| an uncommitted change to the recipe's settings | the recipe and the benchmark show out of date with the reason; built again after the change was reverted |
| afterwards | no process carrying a run id; the GPU idle with no compute process of the run; the example unchanged in Git |

**Accepted as implemented:**

- A definition is also out of date when something it uses is out of date, so one build settles a change.
- A benchmark records its subject's recipe among the run's inputs, and rebuilds only the subjects that are not built.
- `running` takes precedence over every state; a current product over `cannot-rebuild` and `needs-work`.
- The snapshot is prepared before confirmation, so a dirty tree is refused without asking.
- An environment is checked once per build, and only when a step being built uses it. The project stays open during that check.
- `Outcome` has a `problem` text; a launcher that cannot start the command makes the step `failed`.
- Estimates: only `build` steps are measured; a benchmark's estimate command may not use `{subject}`; the disk limit is 100 MB; no GPU lock is taken; the throwaway directory is removed afterwards.
- `stop` refuses only while the run is `queued` or `running` and its builder is alive.

**Not verified:** cancellation and the disk limit through `build` on a real long run; a real interrupted build beyond a hand check with `SIGINT`; behaviour with Git submodules (not included in snapshots); the GPU lock with two real GPU builds.

**Known gaps:** leftover `.partial-*` snapshot directories from a crashed build are never removed; nothing is ever deleted from the local home (runs, old products, snapshots), so a `prune` command is needed before long use; the values file's `commit` is whatever the benchmark's command writes, since the command is not told its commit.

**Next:** milestone 7, serving the new core from the Tuldok app with agent operations; then milestone 8, converting the lab for good and retiring the old project-files code, which needs the owner's two open decisions (where the product archive goes; which earlier models to drop) and sign-off of the capability check.

## 2026-11-12 — milestone 7, the app and the agent interface

**Owner instruction:** continue, after the milestone 6 report said the next step was this milestone's spec and its implementation in the same way. Spec: [spec-m7.md](spec-m7.md); its section 12 lists where the code differs from the sections before it.

**Commits** (none pushed), Tuldok `feat/definition-first-projects`: spec `1b633ffb`; the operations table, the service, build requests and the worker `2e1f21d9`; the app, the agent contracts and the page `3f8f0f4b`.

| Slice | What | Tests |
| --- | --- | --- |
| T13 service | `tuldok_project/operations.py` (36 operations as data), `service.py`, `activity.py` | 25 |
| T14 build requests | `tuldok_project/build_requests.py`, the worker in `service.py`, `expect` and `stop` on `builds.execute`, the commands `requests`, `approve`, `decline` | 18 |
| T15 app | `tuldok_project/host.py`, additive blocks in `app.py` (59 lines), `agent_api.py` (59 lines) and `mcp_stdio.py` (4 lines), the page, the "Serving a project" contract section | 16 |

All Tuldok project tests: 482, about 3 minutes. The 14 existing agent and contract test modules named in the spec: 173 tests pass with 31 skipped, before the milestone and on its final code (run from the repository root with `PYTHONPATH=tests`).

**Nothing published changed.** The `catalog` profile (115 operations), the old `project` profile (152 operations) and the legacy discovery document have the SHA-256 digests they had before the milestone; a test pins the three. No pinned contract fixture was regenerated: the earlier note that they would need it was wrong, because they record earlier contracts and this milestone only adds.

**Changed in review:**

- `ERROR_STATUS` became `error_status`.
- The worker logs a failure that repeats every pass once, not every second.
- The page's sign-in bar and dialog kept their light colours in a dark browser; they now follow the page.
- Found in the acceptance run: a command such as `requests` failed at once with "already open" when the app had the project open for a moment. The store commands now wait up to 5 seconds, as `build` and `progress` already did.
- From the acceptance agent's remarks: a request has `expires_at` while it is queued, and the descriptions of `progress` and `request_build` say how to read on and where to see the state.

**One change outside the listed blocks:** `agent_api.AgentClient` accepted only refusal codes without hyphens, so every refusal of the new core reached an agent as a transport error. For a `project.*` selection it now passes on the code, `problems`, `references` and `files`. No existing line changed.

**Acceptance run, `examples/tiny-project/project`** (throwaway catalog and database, local home in a scratch directory, port 8197):

| Step | Result |
| --- | --- |
| `python app.py --project-folder ...` | serving in under a second |
| the owner signs in with a one-time code and issues an agent credential over HTTP | owner session; agent credential with `inspect`, `edit`, `execute`, `cancel` |
| the owner connects both environments with `ProjectFolderOwnerClient` | both ready; 36 operations offered |
| an agent given only the agent credential and `agent_api.AgentClient`, told to learn the operations from their descriptions | read the summary and the plan (3 steps to build), requested `benchmarks/held-out`: `awaiting-approval` |
| the owner's side: `approve` on the command line | showed who asked, the commit, the 3 steps and the 5 definitions held to; queued, then started within a second |
| the build | `succeeded` 23 s after approval: dataset 0.3 s, training 14.8 s on the GPU, benchmark 2.2 s and 1.3 s |
| the agent's polling of `progress` during training | 9 distinct events, from update 650 to 6,000 of 6,000, loss 0.0023 to 0.0006 |
| the agent's reading of the results and the ranking chart | `small-net-a` median error 0.0376, `predict-zero` 0.871, 400 cases each; the SVG saved |
| the agent's second request | refused 409 `nothing-to-build`; no request made |
| `activity` | four rows: two connects by the owner, the agent's request, the approval from the command line; then the refused second request |
| the page, in a headless browser as the signed-in owner | name, folder and the report with both charts, in light and dark, no script error, no sideways overflow |
| afterwards | the app stopped on `SIGINT` with exit status 0; no process carrying a run id; the GPU idle; the example unchanged in Git |

**The lab project through the app** (271 definitions, 18 benchmarks, results from `results/*.csv` only): `summary`, `definitions`, `graph`, `results_overview`, one benchmark's 1,125 summary rows and each chart with its drawing answered in 0.02 to 0.09 s; `report` in 0.18 s; `plan` for everything in 0.09 s; `check` in 0.5 s. A request to build everything was refused as `blocked` and made no request. Nothing of the lab was run.

**Not verified:** the MCP bridge with `--project-folder-owner` (the `mcp` and `anyio` packages are not installed here; the change is the flag and the client choice); the sign-in dialog typed by hand (the browser check was given the session cookie); a browser other than headless Chromium; cancelling a real long training through `cancel_build`; two apps on one project beyond the test of the worker lock.

**Known gaps:**

- While a build checks an environment, which takes a few seconds for the GPU one, every other operation waits. The agent saw one 4 second poll and so never observed `queued`.
- A request has no history of its states, and its runs appear in two shapes (`result` and `runs`).
- `context.get` and `identity.get` keep their generic descriptions; they are part of the pinned legacy discovery document.
- The example's benchmark reports one timing spread over its 400 cases, so `time_ms` has no spread.
- Carried over: the values file's `commit` is empty; nothing is ever deleted from the local home; installing an environment and measuring estimates are command-line only; the catalog queue does not take the GPU lock (spec section 9).

**Next:** milestone 8, converting the lab for good and retiring the old project-files code. It needs the owner's two open decisions (where the product archive for the earlier weights goes; which earlier models to drop) and sign-off of the written capability check before any old module is deleted.

## 2026-11-12 — milestone 8, part 1: where products live, and adopting the earlier ones

**Owner decisions:** "The model weights can stay with tuldok on the loca system. Tuldok should have an internal proj dir to store per project data including the weights. We do not want the weights in the git repo." Then: "yes make orangcream tuldoks project location." Then: "continue". No product archive is built. Spec: [spec-m8.md](spec-m8.md); the [capability check](capability-check.md) was written the same day and is not signed.

**Commits** (none pushed). Tuldok `feat/definition-first-projects`: the decision and the capability check `5a52bed5`; spec `1a9b9e73`; the setting, `new` and `adopt` `3af6b6a6`. Lab `reorg/reproducible-lab-20261102`: the adoption manifest `6dac9a160`.

| Slice | What | Tests |
| --- | --- | --- |
| T16 | `tuldok_project/local.py` (the saved setting), `adoption.py`, the adopted rule in `builds.py` and `plan.py`, the commands `home`, `new`, `adopt` | 24 |
| L4 | `lab:scripts/build_tuldok_project.py --adoption-output` | 40 in the lab's converter tests |

All Tuldok project tests: 507, about 4.5 minutes.

**Changed in review:**

- A definition that is built on this machine no longer carries `cannot-rebuild` or `needs-work` to what uses it. As implemented first, a new recipe could not use an adopted dataset as its input, which is what adoption is for.
- Closing a project now releases its lock by a statement. A full test run on a busy machine failed once with "already open" straight after a close; the lock had been left to the server to release when it noticed the session end.
- One existing test read the machine's settings file. The whole suite was then run with a decoy settings file in the environment: every test passed and nothing was written to the decoy directory, so no test can write into the real project directory.
- The spec was widened during the work: a definition that declares no outputs can be adopted as a whole directory. The lab's manifest showed why: the earlier weights are 0.8 GB, and 15 GB of the old folder is training data of 25 earlier datasets, which declare no outputs.

**What the old folder holds** (`projects/rheon-model-portfolio-unified-04/artifacts/sha256/`, 8,734 files, 16.5 GB, ignored by Git), by the lab's manifest:

| Part | Files | Size |
| --- | --- | --- |
| Outputs of 203 earlier recipes (weights, histories, receipts) | 2,264 distinct | 0.79 GB |
| Training data of 25 earlier datasets | 177 distinct, 34 of them also a recipe's output | 15.08 GB |
| Named by no entry: old-format records, staged code, custody proofs, outputs of runs with no recipe | 6,327 | 0.69 GB |

Every declared output of the 203 recipes was found at its recorded size; no dataset path was claimed by two different files. Two earlier recipes have no run and five earlier datasets were read by no recipe, so those seven have nothing to adopt.

**Acceptance on a throwaway database**, with a throwaway project directory on the OrangeCream disk:

| Step | Result |
| --- | --- |
| `adopt --dry-run` | would adopt 228 entries, 3,841 files, 16.9 GB, all to be linked; nothing changed |
| `adopt` | 228 adopted in 1.6 s; free space on the disk fell by 2.8 MB |
| The files | all 3,841 are hard links to files of the old folder, 2,407 distinct |
| States | before: 216 cannot rebuild, 27 need work, 17 not built. After: 228 built, 23 cannot rebuild, 9 not built |
| `plan --all` | before: 17 to build, 243 blocked. After: 9 to build, 23 blocked, 228 built |
| A second `adopt` | skipped all 228 |
| Removing the throwaway directory | the old folder still has its 8,734 files and 16,541,094,986 bytes, each with one link again |

**On the owner's machine** (done after the acceptance, on "continue"):

- `home --set` saved `/media/jeremy/OrangeCream/Linux Software/workspace/runtime-data/tuldok/projects` in `~/.local/share/tuldok/settings.json`. The path follows the disk's own layout notes, which put app data under `workspace/runtime-data/`. Before, the default was on the system disk with 16.5 GB free.
- The owner's Tuldok database was started, the lab project opened in it for the first time (0.9 s), both environments connected and ready, and the same 228 entries adopted in 0.7 s by link. The database was then stopped again, as it was found.
- The lab project there: 228 built (203 recipes, 25 datasets), 23 cannot rebuild (16 earlier benchmarks, 5 datasets, 2 recipes), 9 to build (the new datasets, the pilot recipe, its two benchmarks and four steps), 2 environments ready.

**Not verified:** adoption by copy across disks beyond its test; `home --set` when a previous directory holds projects, beyond its test.

**Known gaps:** no command rebuilds or sets aside an adopted product; the 0.69 GB the manifest does not name exists only in the old folder; the earlier weights and training data are single copies on this machine.

**Machine note:** the machine restarted during this work, which emptied `/tmp`: the throwaway database was made again, and the screenshots and chart from the milestone 7 acceptance, which were only there, are gone.

**Next:** part 2, the lab repository stops tracking the old project folder; then the deletion of the old project mode, which waits for the capability check to be signed.

## 2026-11-12 — milestone 8, part 2: the lab repository holds the new folder only

**Owner instruction:** "continue". Spec: section 9 of [spec-m8.md](spec-m8.md).

**Commits** (none pushed). Tuldok `feat/definition-first-projects`: spec `b202fce6`. Lab `reorg/reproducible-lab-20261102`: README, `.gitignore`, the converter's docstring and the removed equality test `076b04c98`; the old folder out of the index `fd18d8202`.

**What changed in the lab:**

- `projects/rheon-model-portfolio-unified-04/` is no longer tracked: 55,865 files left the index. All 63,133 files of the folder are still on disk (17 GB), now ignored. The lab tracks 6,987 files, and under `projects/` only `surrogate-lab` (495 files, 12 MB).
- `projects/surrogate-lab/` is the lab's Tuldok project from here on, edited directly or through Tuldok. The test that required it to equal the converter's output is removed; the converter's other 39 tests, all on synthetic folders, pass.
- The README says where the project is, how to check, open, report and plan it, and that weights, datasets and run logs live in Tuldok's project directory on the machine.

**Acceptance: the plan's test on fresh clones** (a local clone of the lab branch and of the Tuldok branch into a scratch directory, the Tuldok clone's code run with the existing interpreter, an empty database, an empty project directory):

| Step | Result |
| --- | --- |
| The lab clone | 254 MB working tree, no old project folder, no `runs/` |
| `check` | 0 errors, 81 warnings. 73 of them are earlier recipes naming source files under `runs/`, which only the original machine has; the other 8 are the two recipes already known |
| `open` | 1.4 s |
| `list` | 271 definitions: 206 recipes, 32 datasets, 18 benchmarks, 8 charts, 4 steps, 2 environments, 1 model |
| `report` | 0.5 s; 172 KiB with 8 charts drawn from `results/` alone; no script and no external reference |
| `plan --all` | 0.3 s; 17 steps to build in order, 3 on a GPU, 137 GB of disk declared |

The clone was not built: that needs the reference solver and the dataset generation, which the owner has not approved. Rheon was not cloned; nothing before a build needs it.

**Left as they are:** `scripts/track_project_results.py` and `scripts/extract_model_recipes.py`, which served the old format and which nothing current refers to; the historical plans and the migration scripts under `experiments/model-portfolio-migration-v1/` that name the old folder; the README's link to the older `tuldok/` folder, which a reader may confuse with the project.

**Next:** deleting the old project mode from Tuldok. It waits for the owner to sign the [capability check](capability-check.md).

## 2026-11-12 — the owner looks at the interface; the Map workspace plan

**What happened.** The owner asked to see the project open in the Tuldok interface. Tuldok was started on the lab folder in the new project-folder mode, whose only page is the report. The owner: "wtf happened to tuldoks ui? It doesnt have any of the pages it used to have." Started again the way it had been run before (`--project-files-root`), it showed the form-panel project page; the owner: "that is not the GUI it had before either", and described tabs along the top, a bench page and a model page with a horizontal ancestry tree. That is the Map layout of [the workspace redesign](../project-workspace-redesign/README.md), chosen on 2026-11-03, which exists only as mockups run from disk and was never part of the app. Shown the mockup, the owner confirmed: "yes, thts the gui i remember".

**What this changes.** Nothing had been deleted, but the new format has no real screens, and that was not made plain before the owner looked. [The Map workspace plan](workspace-plan.md) builds the Map layout into the app in three phases; the owner approved it the same day ("the plan looks good") with its three recommended decisions. The old project mode is not deleted before phase 3 is accepted, which replaces the earlier advice to sign the capability check.

**A fault found and repaired.** Adoption had hard-linked 2,407 files of the old project folder into Tuldok's project directory. The old project code refuses a stored file that has a second name ("Artifact source must be an ordinary file without hard-link aliases"), so those weights and training data would have been refused by the old mode. Each was replaced in Tuldok's directory by a real copy, compared byte for byte, and every file of the old folder has one name again. Cost: 15.9 GB on the OrangeCream disk. The old lab project was then opened in the old mode to check: it opened, in 166 s. The files' change times moved, so the old mode re-verifies them on first read. Adoption by link stays the command's default; a source that another tool manages should be adopted with `--copy`.

**Commits** (none pushed), Tuldok: the plan `55a5ac68`; the brief and mockups, without the baked data file, `4af5a74a`.

## 2026-11-12 — the Map workspace, phase 1: what the map reads

**Owner instruction:** "the plan looks good". Spec: [spec-w1.md](spec-w1.md).

**Commits** (none pushed). Tuldok `feat/definition-first-projects`: spec `ecca58d1`; the fields and operations `a4047b68`. Lab `reorg/reproducible-lab-20261102`: the fields on the lab's models `d9e8960a0`.

| Slice | What | Tests |
| --- | --- | --- |
| T17 | `groups` and `map.chart` in `tuldok.json`; `group`, `change`, `derived_from`, `compared_with` on a recipe; the checker's rules; graph roles `derived` and `compared`; `tuldok_project/workspace.py` with the operations `map`, `note`, `recipe_results`; the commands `map` and `note` | 47 new; 554 in all, about 4 minutes |
| L6 | the lab's converter writes the fields; `scripts/earlier-model-map.json`; a ninth chart for the track; the folder regenerated | 44 in the lab's converter tests |

**As built, beyond the spec:**

- The kind of change is `change` on a recipe, not a field of a group as the plan first said: in the mockup one group holds 31 architecture and 20 refinement models.
- `derived_from` was added. The plan had lines come only from recorded inputs; a model branched from another without taking its weights has no such input, and "Branch from here" needs the field.
- `tuldok.json` is now kept in the database (a new column of the state row), so `map` reads no file; a change to `tuldok.json` alone now imports the folder again.
- Removing the chart that `map.chart` names is refused.
- `note` takes a path relative to `notes/`; a recipe's `card` value starts with `notes/`.

**Acceptance on the lab** (throwaway database):

| Check | Result |
| --- | --- |
| `map` through the service | 0.04 s, 133 KiB: 206 models, 19 groups, 43 derived and 63 input lines, 26 comparisons |
| Kinds | 48 training policy, 95 architecture, 36 refinement, 26 component, 1 with none (the new pilot model) |
| Track | worst pressure error on the 128 consumed requests; 150 of 206 models have a value |
| C53 | 36 models derived from it; its card read by `note` (28,684 characters); `recipe_results` gives 15 rows over 3 benchmarks |
| The plan for everything, on an empty machine | unchanged: 17 to build, 243 blocked |
| The lab folder | `tuldok.json` and 205 recipes changed, one chart added, the notes file removed; every other file byte-identical; checker 0 errors and the same 8 warnings |

**Starting values to correct.** Kinds, parents and short labels were carried from the mockup, which inferred kinds and parents from card text: 128 models have a short label, 43 a parent (36 from C53, 4 from C37, 3 from C44). The group "Pressure proposal fits" has no model of its own, only child groups.

**Next:** phase 2, the page, read-only.

## 2026-11-12 — the Map workspace, phase 2: the page, read-only

Spec: [spec-w2.md](spec-w2.md).

**Commits** (none pushed). Tuldok `feat/definition-first-projects`: spec `e7eae194`; the shell, the map, the drawer and Overview `1f66f5a0`; Benchmarks, Train, Data and Analysis `50e73ddb`. Lab `reorg/reproducible-lab-20261102`: descriptions that lead with each model's purpose `7774816a5`.

| Slice | What |
| --- | --- |
| T18 | `static/project-workspace.html` and `static/project-workspace/` (the adapter, the shell, the map, the charts helper, a Markdown renderer, the Map and Overview screens), Ubuntu Sans vendored with its licence, `description` on each model of `map`, the stand-in report page removed, `tests/browser_project_workspace.cjs` |
| T19 | `static/project-workspace/tabs.js`: Benchmarks, Train, Data, Analysis; the charts by form; the browser check extended |
| L7 | each earlier recipe's description leads with the Purpose paragraph of its card (205 of 205 cards have one) |

Tuldok project tests: 561, about 4 minutes. The browser check passes on its fixture and on the lab folder: every tab in light and dark at 1440 by 900, no script error, no failed request, no sideways overflow, nothing added to the activity log.

**Reviewed against the mockup** on the lab's 206 models, screenshot by screenshot: the top bar and tabs, the status strip, the map with its sections, the lanes "from C37" and "from C44", the minimap and the track, the list with short label, title, purpose, kind and bar, and the drawer with the card rendered, in light and dark.

**Changed in review:**

- A product with no declared outputs reported a size of zero, so the lab's adopted dataset directories read as empty on the Data tab. `products` now gives the size the run recorded; on the owner's project the 25 adopted datasets show 15.67 GB.
- The label of the fastest end of the frontier was printed over the frontier line; it now sits on the side the line does not leave by.

**Where the page differs from the mockup, on purpose:** no Layout switch; no control that changes anything (phase 3); the drawer's figures are the track metric, cases, benchmarks with results and state; the track scale fits the project's values; inputs are drawn only for the selected model; the Benchmarks picker chooses a benchmark where the mockup chose a population, and each chart definition is drawn by its own form; no studies, planned models, thumbnails, volume viewer or field slices.

**Not verified:** the hairline and progress line of a run while it runs, and the two-second refresh during a build: no fixture has a running run with a progress event. They are checked in phase 3, whose acceptance runs a real build.

**On the owner's machine.** A preview of the committed page runs from an export of the commit in `workspace/scratch/tuldok-preview` on port 8092, on the owner's database, catalog and project directory; the older page still runs on port 8091.

**Next:** phase 3, acting from the page, after the owner has looked at phase 2.

## 2026-11-12 — the Map workspace, phase 3: acting from the page

Spec: [spec-w3.md](spec-w3.md). The owner looked at phase 2 and said to continue ("its ok so far, continue").

**Commits** (none pushed), Tuldok `feat/definition-first-projects`: spec `b15c979d`; the core additions `0864c98c`; the build controls `a7ed05ea`; the editor, branching, the idle refresh and the acceptance script `597452df`.

| Slice | What |
| --- | --- |
| T20 | operations `draft_branch` (writes a new recipe from one of the project's, storing nothing, with the parent's settings file carried as its own settings and the problems keeping it would find) and `revert_definition` (the folder's file back in place of an unsaved edit or a removal; a definition never saved is dropped); `map` says which models are unsaved and dates a model without a `trained_at` label by the run of its current product; commands `branch` and `revert`; 41 operations |
| T21 | `static/project-workspace/actions.js`: who may use a control, one way to call a changing operation (waiting, the two-press state, typed text and the refusal survive every redraw), the plan view, the conflict panel, Needs you and the strip's Save; Train: Plan build, a request's Approve, Decline with a reason and Cancel, a run's Cancel and Stop, an environment's Check again, Connect and Disconnect; the live run (hairline, progress line, both logs read on) |
| T22 | `static/project-workspace/editor.js`: the editor (text for every kind, form for recipes), Pick on the map, Branch from here with drafts kept in the page and drawn hollow and dashed, the steps from draft to built, the Overview's list of every definition; Train's Planned section |

Tuldok project tests: 585 (561 before), about 4 minutes; the kept agent interface tests 44 pass (4 skipped). The pinned digests did not change: none of them is of the `project_folder` profile, which is checked against the operations table.

**Browser checks.** `tests/browser_project_workspace_actions.cjs` (new, about 1 min 45 s): on a fixture copy in a Git repository of its own with stand-in commands, every control of the spec's section 4 as the owner, fourteen refusals provoked on purpose, and with a credential that may only inspect no control drawn. `tests/browser_project_workspace.cjs` (the read-only check) now signs the browser in with an inspect-only credential, because the owner's page has controls its assertions forbid; its assertions are unchanged, and it passes on its fixture and on the lab folder.

**Acceptance run** (`tests/acceptance_project_workspace.cjs`, on a committed copy of `examples/tiny-project`, the owner's two interpreters, a throwaway database, a headless browser; everything after start-up done on the page):

| Step | Result |
| --- | --- |
| Connect `environments/cpu` and `environments/gpu` from Train | ready: Python 3.12.3 and 3.14.7 |
| Plan everything buildable, Request build | 4 runs succeeded; while `small-net-a` trained the hairline of the strip and of the run drawer stood between 3 % and 19 % with "train: 200 of 6000" and the like |
| Branch from here on `small-net-a`, title, kind, description | a draft on the map after its parent, hollow and dashed, its form holding the parent's settings copied from `settings/small-net-a.json` |
| Updates 6000 to 3000 in the form, Keep, Save | `recipes/small-net-3-000-updates.json` in the folder with `derived_from`, `change` and `settings.updates` 3000 as a number |
| Plan build, Request build | trained on the GPU with its progress on the page; the model drawn built with its line from the parent, without a reload, dated by its run |
| The benchmark edited in the text view (a third subject), Keep, Save from the strip | the file is the text typed, byte for byte |
| An agent asks for `benchmarks/held-out` | the idle page counted it in Needs you by itself after 13 s; Approve there; 3 runs succeeded |
| Results | median error 0.0376 (6,000 updates), 0.0407 (3,000 updates), 0.871 (predict zero); all three on the Benchmarks tab |
| The whole run | no script error, no failed request; 1 min 40 s; two small trainings and three benchmark runs on the GPU |

Screenshots: `build/qa/project-workspace-acceptance/final/` (21) and, for the owner's view of the lab folder at full size against the throwaway database with nothing kept or saved, `build/qa/project-workspace-acceptance/lab-owner-view/`: the map opens in 0.6 s, the editor of C53 in 0.2 s, a draft branched from C53 in 0.4 s, the lab's activity log empty afterwards and its folder unchanged.

**Found at the acceptance run and changed:**

- An idle page read again only when the window regained focus, so a build an agent asked for while the owner was looking at the page did not reach Needs you. The page now also asks again every fifteen seconds while nothing builds (summary, runs, build requests, status, environments: 13 to 60 ms each on the lab folder).
- Between two steps of a running build the strip said the request was queued. It now says a build is between two of its steps.
- A field with a hint beside one without (Short label and Group) stood at different heights.

**Deviations from the spec, kept:**

- `branch` does not take the other commands' `--keep` and `--discard` for a conflict; its own `--keep` stores the draft.
- Reverting a removed benchmark imports its results file again when it is still the file last imported; otherwise the next save would have deleted the file.
- A model that names a parent and has no date is drawn in the lane of its parent's branches, right after the parent, when it is in the parent's group.
- A never-built node is outlined in its kind's colour, not the accent, so the kind stays readable; a draft is labelled "new".
- Models branched and kept in this browser tab keep their steps list after they are built.
- The form writes the whole document again with the text's indentation: values and key order are kept, compact one-line objects are spread over lines.
- Environments on Train open a drawer for their controls; Decline takes two steps because its reason field opens on the first.

**Not verified:** Stop what a run left running (it needs a run whose builder died); Save refused `changed-on-disk` (the opening import reports a changed file as a conflict first); widths other than 1440 by 900. The read-only check once stopped early on the lab folder while the full test suite ran beside it, and passed the next four times: it presses before a view has painted when the machine is loaded.

**Seen, not Tuldok's:** this machine's zone is America/Vancouver, which the system clock gives as UTC−7 in November; the headless browser and Node carry older zone data and show times an hour earlier. A browser with current zone data shows the right hour.

**Next:** the owner looks at phase 3 on the lab project. Then the capability check can be signed and the old project mode deleted (milestone 8, part 3).

## 2026-11-12 — the owner looks at phase 3; the workspace updates in place

**Owner, on phase 3 on the lab project:** "looks ok. continue", and then: "one thing, im noticing there is a full page reset when it should just be updating info on the page instead". Phase 3 is accepted with that one fault. The capability check is not signed by these words; it was brought up to date and its losses put to the owner again.

Spec: [spec-w4.md](spec-w4.md). **Commits** (none pushed), Tuldok `feat/definition-first-projects`: the spec, part 3 of [spec-m8.md](spec-m8.md) and the capability check `4f206bbd`; the fix and its check, the commit before this entry.

**What was measured before** (the lab folder, owner signed in, nothing changing; elements of the main area that were new nodes afterwards):

| Tab | On return to the window | Every 15 s while idle |
| --- | --- | --- |
| Map | none | none |
| Data | all 356 | none |
| Train | all 64 | all 64 |
| Benchmarks | all 2,109 | none |
| Analysis | all 159 | none |
| Overview | all 2,336 | all 2,336 |

The tab bar was rebuilt with each of those, the strip on every reading, and the sideways scroll inside tables was lost. The reading every fifteen seconds had been added at phase 3's acceptance, where only its cost was measured, not what it redrew.

**After:** none, in every cell, with the model's drawer and the editor open as well; no strip or tab-bar node added; every scroll position kept. The same measurement is now a check, `tests/browser_project_workspace_still.cjs` (about 2 min 40 s on the fixture, 1 min on the lab folder read only): nothing touched on twelve places when nothing changed; a build asked for by a second session shown within one reading with the scroll and the focus kept and no "Reading…"; a drawer brought up to date in place; a running build's progress set in place in the strip, the run's drawer and its row of Train's list while the Map gains no node; the editor with typed text left alone; and the page kept as it is when the server cannot be reached.

**How.** One slice by an agent, then review. The page compares the text of each watched answer (`summary`, `status`, `build_requests`, `environments`, `runs`, and `map` when it can have changed) with the one it holds, and draws nothing when none differs. When one does, the tab and the drawer are built off the page and put in place whole, in one step. No element is kept from an older drawing when its content is drawn again, so a control never acts on older answers than it was drawn from.

**Changed in review:**

- As first built, a running run's progress line in Train's list and Overview's "Read at" went stale until a watched answer changed. Both are now set in place on every reading.
- As first specified, a watched answer that was refused counted as a change, which emptied the tab on screen whenever the server could not be reached for a moment. A reading that fails now changes nothing: the page stays, the strip says "Not read" and why, and the timer asks again.
- `tests/browser_project_workspace_actions.cjs` failed twice in a row at one assertion made the moment a control stopped being busy; the drawer is now redrawn by the reading that follows, a few milliseconds later. Its `settled()` waits for the page's own requests; no assertion changed, and it then passed twice.

**Tests on the final code:** project suite 585; agent interface 44 (4 skipped); HTTP 17; `browser_project_workspace.cjs` on its fixture and on the lab folder; `browser_project_workspace_actions.cjs` (27 steps, twice); `browser_project_workspace_still.cjs` on its fixture (twice) and on the lab folder. The lab folder was unchanged throughout.

**Not verified:** the new check in the dark theme; a reading that fails while a build runs; widths other than those the checks use (1280 and 1440). Each browser check asserts at one moment after waiting; on a busy machine a wait may still prove short.

**Next:** the owner looks at the page again. The deletion of the old project mode is being prepared on the side branch `chore/retire-old-project-mode` and lands only when the capability check is signed.

## 2026-11-12 — milestone 8, part 3: the deletion of the old project mode is prepared, not landed

**Status: prepared and checked on the side branch `chore/retire-old-project-mode`, one commit on top of this one. Nothing is deleted on this branch. The capability check is not signed.**

**Why it is not landed.** The plan deletes the old mode only when the owner signs the capability check, and the owner signs by saying so. The owner was told twice that the deletion lands on the word "signed"; the replies were "continue", which is taken as leave to prepare it and not as the sign-off.

**How.** Section 10 of [spec-m8.md](spec-m8.md). First the baseline: the capability manifests of both profiles saved, and the whole Python suite run on the unchanged branch. An agent cut the import statements that tied the old code to catalog mode; the machine was restarted at that point, which lost the agent and the first baseline run and kept the working tree. A second agent checked that first step, deleted, searched for what was left and gathered the evidence. In review every changed file's diff was read, the changed Python files were linted (no undefined name; the same warnings before and after), the manifests were compared again by a script of the reviewer's own, and the workflow file was parsed.

**Found while preparing** (each is corrected in the capability check and in section 10.6 of the spec on the side branch):

- `project_cli.py` is also catalog mode's command line, so it stays without its old-mode commands: 37 modules go, not 38.
- Twelve import statements tied the old code to catalog mode, not eight.
- A test of the kept code, `tests/test_tuldok_project_http.py`, pinned the digest of the whole catalog manifest and of the `project` profile, which the deletion changes by its own rule. It now pins the manifest without the five `project_transfer.*` entries (shown equal, entry by entry, to the earlier manifest with those five taken out) and a new test checks that the old profile is refused.
- About thirty lines in ten of catalog mode's files read an attribute that only the deleted modules set. They cannot be reached any more and are left for a change of their own, since they run through the code that starts and recovers runs.

**Size:** 143 files and 47,099 lines deleted; 2,450 lines cut from 17 files that stay.

**Tests:**

- Contracts: every remaining operation published byte for byte as before in both profiles; the catalog's list 115 to 110 (the five `project_transfer.*` entries, listed as unavailable before); the `project` profile refused.
- Whole Python suite: 3,149 tests before with 40 not passing; 2,397 after with 25 not passing, of which 23 are the same tests failing for the same reasons of this machine (no training environment, a database user that may not create databases, three CPU snapshot tests) and two lines are the pinned digest. After that test was changed: project suite 586, agent interface and command line 67 (4 skipped). The whole suite was not run again after that change.
- JavaScript: all 49 remaining `tests/test_*.cjs`; `node --check` on 54 scripts.
- Browser: the three workspace checks on the fixture, two of them on the lab folder read only (unchanged before and after); 45 of the 49 catalog checks that can run here.
- Start-up: the removed flags are argument errors; catalog mode and `--project-folder` both start.

**Not verified:** 13 catalog browser checks that need training, a GPU or generated fixtures, and three that need packages only the workflow installs; one catalog check fails removing its own temporary directory, on the unchanged code as well. The browser checks used Playwright's headless shell. Nothing ran on GitHub: nothing is pushed.

**Next:** the owner's sign-off of the capability check. Then section 10.5: the words and the date recorded there and here, and the side branch brought onto this one. Separately, the unreachable lines in catalog mode's run code.

## 2026-11-13 — milestone 8, part 3: the old project mode is deleted

**Owner's words, 2026-11-13**, after being told item by item what projects lose: "We still want tools for generating datasets and annotating them using pumas library v0.8.0 in tuldok. Tuldok also needs to be able to look inside data. It would be great if tuldok also had a layer visulization tool so we can visualize a models weights." Then: "the other stuff is all ok to go ahead on".

**What was done on them.** `feat/definition-first-projects` was fast-forwarded to the one commit of `chore/retire-old-project-mode` (section 10.5 of [spec-m8.md](spec-m8.md)). No old-mode app was running. Nothing is pushed. The words are recorded in the [capability check](capability-check.md) as a sign-off in part.

**How the words were read.** The owner accepted every loss on the list but two: tools for generating and annotating datasets, and looking inside data. The deletion was landed all the same because it takes neither out of Tuldok: both are catalog mode's and stay; only the old format's wrapping of them went, which could not serve a project folder. This reading is the assistant's. One revert undoes it.

**Requirements carried from here** (not planned yet):

1. In a project folder: generating datasets and annotating them, through Pumas Library 0.8.0. The client for 0.8.0 is on `feat/pumas-v080-api`, four commits not merged into this branch.
2. In a project folder: looking inside data.
3. A view of a model's weights layer by layer.

**Also carried:** the unreachable lines in catalog mode's run code that read attributes only the deleted modules set.

## 2026-11-13 — the data tools plan; reading inside a product (server); the Pumas 0.8.0 client

**Owner, 2026-11-13,** on the [data tools plan](data-tools-plan.md): "we will use the pumas endpoint. We wont be embedding pumas. What do you mean by lables? Right now we just need the basic modality support for data generation and annotation. text, image, audio, 3D (point clouds, mesh). We dont have a specific need for the surrogate lab. This is more a setup so other projects can setup what they need to generate. The rest sounds good. You can go ahead". The plan records what that changed: Pumas as an endpoint only, five kinds of record, "annotation" for "label", the lab's field comparison last.

**Commits** on `feat/definition-first-projects`, none pushed: the plan and specs (`c7693b0d`, `1c08b2b0`, `685be616`, `f26361dc`); reading inside a product `710a5f01`; the Pumas client `d3270202` (the earlier branch merged), `04e1ddb2`, merged here as `be7af731`.

**Phase 1, server side** ([spec-d1.md](spec-d1.md), slice D1a). Five read operations and one route open the output of any finished run: its records, one record, its files and archives, a slice and a summary of an array, and the bytes of an image or a sound. Kinds: text, image, audio, point cloud, mesh, array, file. Standard library only; nothing is unpickled, extracted or written.

**Changed in review:**

- The reads were answered under the service's one lock, so a large member being decompressed held up every other call. They now find the run under the lock and read outside it.
- The readers were fed 22,000 corrupted files. Compressed data that does not decompress and a binary PLY that ends early raised errors of their own; every entry point now refuses a damaged file as `unsupported` and logs it. A malformed `.npy` was coded `invalid`, which is kept for arguments; it is `unsupported` too.

**Measured** on the lab's largest product (9.77 GB), through the readers alone: listing 0.004 s, one sample's arrays 0.004 s, a slice 0.009 s, a summary of 645,120 values 0.12 s.

**Phase 3, the Pumas 0.8.0 client** ([spec-d3.md](spec-d3.md)), built beside phase 1 on a branch of its own. The client written on 2 November against a pre-release was merged, compared with the contract released at the tag `v0.8.0` (read only from the Pumas Library repository; the spec's "As built" has the table) and brought up to it. `served_models()` reads what an endpoint serves, with each model's modalities and capabilities. Nothing uses it yet. No running Pumas was contacted.

**What Pumas 0.8.0 can make:** text and PNG images. Its contract reserves audio output and has nothing for 3D. Audio and 3D datasets therefore come from import or a project's own generator command until a served model declares them.

**Tests:** project suite 610; `tests/test_tuldok_project_inside.py` 24; agent interface 43 (4 skipped); the Pumas client and its fakes 80, and the four catalog tools that call it (61); the two Pumas browser checks and the two controller checks. The catalog profile's manifest is unchanged by phase 1.

**Not verified:** a real Pumas endpoint; the schemas the release does not publish (four are the pre-release export, one is derived); what spec-d1's "As built" lists. The standards service the implementers' rules name answered "awaiting application publication" on 2026-11-13, so no standards text was read for these slices.

**Next:** the page of phase 1 (the record grid and a viewer per kind), and phase 2 (weights by layer, [spec-d2.md](spec-d2.md)), both being built.

## 2026-11-13 — data tools: looking inside a dataset (page), weights (server), annotation (server)

**Commits** on `feat/definition-first-projects`, none pushed: the page of phase 1 `7d376b61`; the weights readers `dfbeb10e`; annotation tasks and their file of lines `eefa274e`; the working copy and its operations `68aad8fb`; the steps `import` and `freeze` `e2ae4bb2`; merged here as `7262e8b4`. Specs: [spec-d2.md](spec-d2.md), [spec-d4.md](spec-d4.md), [spec-d5.md](spec-d5.md) (phase 5, written, not built).

**How.** Slices were built by agents in working trees of their own, several at once where they touched different files, and merged after review. Each "As built" section of the specs has what differs from the text and what was not verified.

**Phase 1, the page** ([spec-d1.md](spec-d1.md), slice D1b). A dataset with a product opens to its records as a paged grid with a viewer per kind: text, image, sound with its waveform, point cloud and mesh turned by dragging, array as a slice with the stacked-slice drawing and histogram; and a Files view of the product. Checked by `tests/browser_project_workspace_inside.cjs`, with screenshots read in light and dark at two widths.

**Open defect in it.** In the reviewer's twelve further runs of that check, one failed: the main area's scroll went back to its top once, in the first second after the dataset opened, with its content unchanged. The owner's one complaint about this page so far was a full reset where an update in place was wanted, so this is not accepted as a flake: it is being reproduced in a loop with every way of moving the scroll traced. Also open: the Files view cannot yet open a text, point cloud or mesh that is not one of the product's records.

**Phase 2, server side** (slice D2a): a run's weights by layer, a comparison of two files tensor by tensor, an array as tiles, `.safetensors` read like `.npz`. A PyTorch pickle is listed with its reason and never opened.

**Phase 4, server side** (slices D4a to D4c): the annotation task as an eighth kind of definition; its annotations as a file of lines in Git, tied to each record's content by a hash; the working copy in the database, written by Save, with conflicts handled as for definitions; five operations; and `import` and `freeze` as steps Tuldok itself runs as ordinary builds.

**Changed in review:**

- `array_summary` (phase 1) answered `Infinity` for 64-bit values too large to sum, which is not JSON; found by feeding the weights readers 20,000 corrupted files. An overflowing mean or deviation is null.
- A line file rewritten to the same size within one tick of the clock looked unchanged by size and time: the edit was not imported and Save would have written over it. A file's size and time are trusted only once its time is two seconds old; a test that writes such an edit fails without the rule.
- The annotation file module was checked with 2,800 random annotations of every task written and read back byte for byte, and 3,000 corrupted files; `import` on a directory holding links out of it, a loop, a named pipe and names that collide.

**Tests on the merged branch:** project suite 689; agent interface 43 (4 skipped). The catalog profile's manifest is unchanged throughout.

**Not verified:** what each spec's "As built" lists; a real `.safetensors` written by the library; a copy across file systems in `import`; the standards service was unavailable (see the entry above).

**Next:** the cause of the scroll going back; the Weights block of a model's drawer; the Annotate tab with the Import and Freeze forms; then phase 5.
