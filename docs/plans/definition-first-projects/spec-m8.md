# Implementation spec: milestone 8, part 1: where products live, and adopting the earlier ones

This continues the earlier specs in this folder. Section 1 of [spec-m1-m2.md](spec-m1-m2.md) (rules for implementers) applies. This part changes nothing outside `tuldok_project/`, `tests/`, `docs/` and the lab's converter. It deletes nothing.

**Owner decisions, 2026-11-12:**

- The model weights stay with Tuldok on the local system, in Tuldok's own per-project directory. They are never in the Git repository. No product archive is built.
- On the owner's machine that directory is on the OrangeCream disk.

**Assumed until the owner says otherwise:** no earlier model is dropped. Keeping a definition is the reversible choice; one can be deleted later.

**Done when:** the machine's project directory is a saved setting that every command and the app use; `adopt` makes the lab's earlier weights the products of their definitions without copying them; and the definitions that have their weights show as built.

## 1. The project directory is a saved setting

Until now the directory that holds every project's local home came from the environment variable `TULDOK_PROJECT_HOME` or a default under the home directory. A forgotten variable would send the next build's products to the default, on another disk, without a word. It becomes a setting.

**Settings file:** `~/.local/share/tuldok/settings.json`, or the file named by `TULDOK_SETTINGS` (for tests). Strict JSON as in section 2.2 of the first spec, at most 64 KiB:

```json
{"format": "tuldok_settings_v1", "project_home": "/absolute/path"}
```

`project_home` is optional. Unknown fields are refused.

**Which directory is used,** first that applies: `TULDOK_PROJECT_HOME` when set and not empty; `project_home` of the settings file; `~/.local/share/tuldok/projects`.

**A settings file that cannot be read or is not valid stops the command** with a message naming the file and the fault. It never falls back to the default. `local.projects_home()` raises `local.SettingsError`; the command line prints it and exits with status 2, and the app ends start-up with it.

| Command | Does |
| --- | --- |
| `home` | prints the directory in use, where that came from (the environment variable, the settings file or the default), the free space on its disk, and how many project directories it holds. Needs no database |
| `home --set PATH` | `PATH` must be absolute. It is created with its parents when missing, and must be a directory this user can write. The settings file is written through a temporary file renamed into place, mode 0600. Says when the directory used before holds project directories (they are not moved) and when `TULDOK_PROJECT_HOME` is set and so overrides the setting |

## 2. A new project

`new FOLDER --name NAME [--code-root PATH]` makes `FOLDER` (which must not exist, or be an empty directory) and writes `tuldok.json` with the format, a new random id, the name and `code_root` (`.` when not given). It writes nothing else and needs no database. It refuses a name the project schema refuses.

## 3. Adopting existing files as products

Some files were made before Tuldok could build them and cannot be made again: the lab's earlier weights. Adoption makes such files the product of a definition, so the definition shows as built and later steps can use it as an input.

**The manifest** is written by whoever knows where the files are (for the lab, its converter). Format `tuldok_adoption_v1`, strict JSON, at most 16 MiB:

```json
{"format": "tuldok_adoption_v1",
 "products": [
   {"reference": "recipes/pilot-a",
    "note": "Tuldok run acb748bc of 2026-10-21",
    "files": {"weights.npz": "/absolute/path/to/the/file",
              "history.json": "/absolute/path/to/another"}}
 ]}
```

| Field | Rule |
| --- | --- |
| `products` | 1 to 5000 entries; a reference appears once |
| `reference` | a dataset, recipe or step of the project, not removed |
| `note` | optional, 1 to 400 characters; kept as the run's `problem` text, which is where a run's remark is shown |
| `files` | 1 to 200 entries. Each key is a relative path in normal form. When the definition declares outputs, the key is the `path` of one of them or a path under one. When it declares none, its product is the directory as a whole, which is what a step that uses it as an input is given, and any relative path is accepted. Each value is the absolute path of an existing regular file; a link is refused |

Unknown fields are refused.

**Checking.** Every entry is checked before anything is adopted, and one refused entry stops the command with nothing adopted. For a definition that declares outputs, an entry none of whose declared outputs has a file is refused; declared outputs without a file are reported as missing, and the entry is still adopted.

**What adopting an entry does:**

1. Makes `<local home>/runs/<run id>/output/` holding the files at their keys, as hard links to the sources. A source on another filesystem is copied, and `--copy` copies always. The directory is made under a temporary name and renamed into place.
2. Inserts a run: state `adopted`, no commit, no command, the definition's text as it is now, the note, all three times now, the bytes of the files.
3. Inserts its product, current, with the declared outputs that have a file. A product that was current before stays in the database, no longer current.

An entry whose definition already has a current product is skipped, unless `--replace`.

**The state of an adopted product.** A definition whose current product was adopted is `built` and is never out of date: it was not built here, so its definition text, inputs and code are not compared. `status`, `products`, `runs` and `run` show that it was adopted. A real build of the definition replaces it like any other product. Tuldok never writes to an adopted file.

**No checksum is recorded.** The size of each file is.

| Command | Does |
| --- | --- |
| `adopt FOLDER MANIFEST [--dry-run] [--copy] [--replace] [--json]` | checks the manifest and prints what it would do: entries to adopt, entries skipped because they have a product, declared outputs missing, files and bytes, and whether they will be linked or copied. Without `--dry-run` it then does it and prints the same with what was done. Exit status 1 when an entry is refused |

Adoption is a command-line action only: a manifest names files anywhere on the machine.

## 4. The lab's manifest

`lab:scripts/build_tuldok_project.py --adoption-output FILE` writes the manifest for the earlier recipes and datasets, from the old project folder it already reads. For each earlier recipe: the files of its old run that are present under the old folder's `artifacts/sha256/`, keyed by the recipe's declared output paths. The earlier datasets have no run of their own and declare no outputs; for each, the files the earlier recipes' runs read from it, keyed by each file's path inside the dataset's directory. Where two different stored files claim one path of a dataset, that path is left out and reported. The file holds absolute paths, so it belongs outside Git, by default under `runs/tuldok-adoption/`.

It prints how many earlier definitions have every declared output, some, or none; the files and bytes named; and the files in `artifacts/sha256/` that no definition claims, as a count and bytes. It reads the old folder and changes nothing in it. `--check` is unchanged.

## 5. Acceptance of this part

Done by the orchestrating session on a throwaway database, with a throwaway project directory on the same filesystem as the lab so that adoption links and does not copy:

- `home` reports the setting; a command run without the environment variable uses it.
- `adopt --dry-run` on the lab's manifest, then `adopt`: the counts of adopted, skipped and missing; free space on the disk before and after; the states of the lab's definitions before and after; `plan --all` before and after.
- A second `adopt` skips everything.
- Removing the throwaway directory leaves every file of the old folder in place.

## 6. What follows, each on the owner's word

1. Adopting into the owner's real project directory and database.
2. The lab repository: the tracked old project folder is replaced by the new one.
3. Deleting the old project mode, after the [capability check](capability-check.md) is signed.

## 7. Slices

| Slice | Files | Notes |
| --- | --- | --- |
| T16 settings, new, adopt | `tuldok_project/local.py`, a new `tuldok_project/adoption.py`, the adopted rule in `builds.py`, `home`, `new` and `adopt` in `__main__.py`, tests, and the sections of `docs/contracts/project-folder.md` | database tests on the `buildable` fixture |
| L4 lab manifest | `lab:scripts/build_tuldok_project.py`, `lab:scripts/tests/` | beside T16; reads the old folder only |

## 8. As built

Found while implementing; the code and its tests follow this section.

- **A built definition no longer blocks what uses it.** Until now `cannot-rebuild` and `needs-work` were carried from a definition to everything that uses it as an input, whatever was on the machine (spec-m4). A definition that is built on this machine, by a build or by adoption, now carries nothing to what uses it and nothing through it: its product is there to be used. Without this an adopted dataset could not be the input of a new recipe, which is the point of adopting it. A definition that is out of date still carries.
- **A recipe that is held but has a current product** can be a benchmark subject.
- **The refusal "none of whose declared outputs has a file" cannot occur:** every key lies under a declared output and `files` is not empty.
- **Also refused:** two keys of one entry where one lies under the other, and a source this user cannot read.
- **No command rebuilds an adopted definition.** It is never out of date, so `build` skips it. A way to set an adopted product aside is not written.
- **The settings file is read only when `TULDOK_PROJECT_HOME` does not decide** and only by a command that needs the directory.
- **The directory used before, for `home --set`,** is what the settings file or the default gave, the variable aside.
- **`adopt` holds the project open for its whole run.** With links that is seconds. A failure partway leaves the entries before it adopted, and the command says so.
- **Closing a project now releases its lock by a statement.** Closing the connection alone left the lock held until the server noticed, so a project opened again at once could be refused as already open. The full test run showed it once on a busy machine.
- **The lab's manifest** has one entry per earlier recipe with a run (203) and per earlier dataset that an earlier recipe read (25). A dataset's directory is its one folder, or the deepest directory that holds all its folders.

## 9. Part 2: the lab repository holds the new folder only

- **The lab stops tracking `projects/rheon-model-portfolio-unified-04/`.** The folder stays on disk where it is, named in `.gitignore`: it is the converter's source and the origin of the adopted files. The orchestrating session removes it from the index; nothing on disk is deleted.
- **`projects/surrogate-lab/` is the lab's Tuldok project from here on.** It is edited directly or through Tuldok and committed like any source. The converter is no longer what that folder must equal, so its equality check stops being a test. The converter stays as the record of how the folder was made, and as the writer of the adoption manifest and the values files; it runs only where the old folder is.
- **The lab's README** says where the project is, how to open it, and that weights and data live in Tuldok's project directory on the machine and are adopted or rebuilt there, never committed. The paragraph that tells the reader to run the two scripts for the old format goes.
- **Tests that need the old folder** skip when it is absent, so a fresh clone's tests pass.

**Acceptance: the plan's test, on a fresh clone.** A new clone of the lab branch, opened by Tuldok into an empty database with an empty project directory: it opens in seconds; it lists the models, recipes and benchmarks; the report draws the result charts from `results/` alone; and `plan --all` lists the ordered steps for what can be built. The clone holds no old project folder.

## 10. Part 3: the old project mode is deleted

**Gate.** The plan deletes nothing before the owner signs the [capability check](capability-check.md). This part is therefore prepared on a side branch, `chore/retire-old-project-mode`, in a working tree of its own, and reaches `feat/definition-first-projects` only on the owner's word. Until then that branch, the running old-mode app and the owner's database are as they were.

**After this part** Tuldok has two ways to start: catalog mode, unchanged, and a project folder (`--project-folder`). `--project-files-root` and everything only it reaches is gone.

### 10.1 What goes

What the capability check lists, measured again when the work starts:

- The 38 modules it names.
- `app.py`: the flags `--project-files-root`, `--project-runtime-source`, `--project-transfer-control` and `--project-transfer-root`, their routes, pages and error branches. `--project-root` (catalog mode's read-only look at project snapshots, `projects.py` and `project_activity.py`) stays.
- `candidate_packages.py` and `pipeline.py`: the branches for the old project objects. The one small function catalog mode also uses moves into `pipeline.py`.
- `agent_api.py`: the `project_files.*` and `project_transfer.*` operations, the `project` capability profile, `ProjectFilesOwnerClient` and `ProjectTransferOwnerClient`; `mcp_stdio.py`: `--project-files-owner` and `--project-transfer-owner`.
- `static/`: the old project page, the extraction page and the scripts and styles only they load.
- Every test file, fixture, fake and qualification script that exists for the old mode, and the steps of `.github/workflows/` that run them.
- `scripts/generate_project_files_contracts.py`, and what it generates.
- Under `docs/contracts/`, `docs/runbooks/`, `docs/reference/` and the READMEs: what describes the old mode as something Tuldok does. A document that covers both loses the old mode's part.

### 10.2 What stays exactly as it is

- **Every remaining operation's contract.** For each operation id still offered, the entry in the capability manifest of the `catalog` and of the `project_folder` profile (versions, digests, schemas) is the same before and after, byte for byte. Where a catalog operation's contract is built from an old operation's (as `graphs.create` is from `project_files.graph_create`), the shared shape is kept under a name of its own. The ids that disappear are exactly those beginning `project_files.` and `project_transfer.`. Asking for the `project` profile is refused as unsupported.
- **Catalog mode's behaviour**, its pages and its tests.
- **`tuldok_project/`, the Map workspace and their tests.** Not touched.
- **The database.** Nothing is dropped, migrated or rewritten. The old project's schemas stay where they are, unread.
- **`docs/plans/`.** The plans and ledgers of the old mode are the record of what was built; they stay. (The capability check said they would go; keeping them deletes less.)
- **The lab repository.** Not touched.

### 10.3 Order

1. **Baseline, before any change:** the capability manifests of both profiles saved to a scratch file; the whole Python suite run once with its counts (passed, failed, skipped) and time; the remaining suites' names.
2. **Cut the eight import lines** (`app.py`, `candidate_packages.py`, `pipeline.py`) and remove what they served. Catalog mode's tests pass.
3. **Delete** modules, operations, clients, flags, pages, tests, scripts, workflow steps, documents.
4. **Look for what is left:** no import of a deleted module; outside `docs/plans/` and Git history, no mention of `project_files`, `project-files`, `project_transfer`, `project-transfer`, `--project-files-root` or a deleted module's name.

### 10.4 Done when

| Check | Passes when |
| --- | --- |
| Contracts | a script compares the saved manifests with the new ones as 10.2 says and prints the ids removed |
| Python suite | `python -m unittest discover -s tests` passes; its count is the baseline's less the tests of the deleted files; no test that passed before fails or is newly skipped |
| Project suite | the `test_tuldok_project_*.py` count is unchanged |
| JavaScript | every remaining `tests/test_*.cjs` passes; `node --check` on every remaining script under `static/` |
| Browser | the workspace checks pass on their fixture and on the lab folder read only; the catalog-mode browser checks that the workflow runs and that need no download or GPU pass, and those not run are named |
| Start-up | `python app.py --help` shows none of the removed flags; a removed flag is an argument error; Tuldok starts in catalog mode on an empty data directory and with `--project-folder` on the tiny example |
| Size | the lines and files removed, by kind, reported beside the capability check's figures |

### 10.5 Landing

On the owner's sign-off: their words and the date go into the capability check and the ledger; the old-mode app left running on port 8091 for comparison is stopped (its pages would be gone from under it); the side branch is brought onto `feat/definition-first-projects` without rewriting that branch's history. Nothing is pushed.

### 10.6 As prepared

Prepared 2026-11-12 on `chore/retire-old-project-mode`. This is what differs from 10.1 to 10.4 and what each check found. The logs are kept outside the repository, in the scratch directory `tuldok-retire-evidence`.

**What differs from the text above.**

- **`project_cli.py` stays; 37 modules go, not 38.** It is also catalog mode's command line for agents (`open`, `inspect`, `preflight`, `submit`, `status`, `download`, the publication and coordinator commands, `call`, the workflows); `mcp_observer.py` lists it as a runtime source and about twenty tests and qualification scripts that stay use it. It loses `--owner-project-files`, the `file-*` commands and `project-transfer`.
- **Twelve import statements, not eight,** tied the old code to catalog mode: seven in `app.py`, two in `candidate_packages.py`, three in `pipeline.py`. In `pipeline.py` both `preparation_owner` branches went (the function answered `None` in catalog mode), so `_prepare_builtin_recipe_material_current` is folded into `_prepare_builtin_recipe_material`; `native_admission_wall_seconds` and its two constants moved in and answer 990 seconds as before.
- **No shared shape needed a name of its own.** 10.2 says `graphs.create` is built from `project_files.graph_create`. It was the other way round: the old operations copied their input from `graphs.*`.
- **In catalog mode `/api/agent/capabilities` now returns the registry's answer as it is.** The code removed from `app.py` only switched the old operations between available and unavailable.
- **One test of the kept code changed,** against 10.2's "not touched". `tests/test_tuldok_project_http.py` pinned the digest of the whole catalog manifest (115 operations) and of the `project` profile (152), and 10.2 itself changes both. It now pins the catalog manifest of 110 operations, which is the earlier manifest with its five `project_transfer.*` entries taken out (compared entry by entry with the manifest saved before the change: none added, none changed, order kept), and a new test checks that the `project` profile is refused and that no `project_files.*` or `project_transfer.*` operation is published or known.
- **Two tests that stay lose a part.** `tests/test_agent_api.py` loses the one test of `ProjectFilesOwnerClient`'s own timeout; `tests/test_torch_runtime.py` loses one assertion that called `project_material.decode_runtime_material`.
- **Under `static/`** `retained-measurement-maxima.vl.json` goes with the page that loaded it. `workspace-project-activity.js` and `workspace-projects.js` stay: catalog mode's `workspaces.html` loads them.
- **`.github/workflows/tests.yml` loses 13 steps** (the training step of the native project, five steps of the agent environment, six Chromium steps and one Node step of the old mode). It parses, with 166 steps. It has not run on GitHub: nothing is pushed.
- **Step 4 of 10.3 is not met in full.** Outside `docs/plans/` these mentions remain:
  - About thirty lines in `runs.py`, `synthetic.py`, `caption_proposals.py`, `grounded_candidates.py`, `text_classification_proposals.py`, `experiments.py`, `audio_assets.py`, `immutable_assets.py`, `scientific_fields.py` and `workbench.py` read an attribute of the catalog that only the deleted modules set (`project_execution`, `project_sources`, `project_asset`, `project_availability`, `project_study_execution`). Nothing reaches them now. They run through the code that starts and recovers runs, and 10.1 does not name those files, so they are left for a change of their own.
  - The docstring of `tuldok_project/__init__.py` names the older modules.
  - `project_files` is a dictionary key in four qualification scripts of the extension system, where it means the files of an extension's project.
  - `docs/decisions/external-project-authority.md`, the decision record of the old mode, stays as a record.

**What the checks found.**

| Check | Result |
| --- | --- |
| Contracts | Pass. `catalog`: 115 operations before, 110 after; removed `project_transfer.extract`, `.preview`, `.report_page`, `.status`, `.stop` (each listed as unavailable before); none added, none changed, the rest of the manifest equal, order kept. `project_folder`: 43 before and after, identical. `project`: refused, "Unsupported capability profile". Of its 152 operations, the 145 `project_files.*` and 5 `project_transfer.*` are offered by no profile; `context.get` and `identity.get` remain. The discovery digest is unchanged |
| Python suite | Before: 3,149 tests, 40 not passing, 146 skipped, 92 minutes (two suites were running). After: 2,397 tests, 25 not passing, 122 skipped, 53 minutes. 3,149 less 751 tests of the deleted files less one removed test is 2,397; the tests that stay are the same set. No test is newly skipped (24 of the skips were in deleted files). One test that passed failed after: the pinned digest, above. With it changed and the new test added, the project suite and the agent tests were run again (below); the whole suite was not |
| The 23 that fail before and after | None from the change. No training environment on this machine (numpy, scikit-learn, `TULDOK_TRAINING_PYTHON`): `test_audio_training` (9), `test_one_fit_studies` (2), `test_text_training` (2), `test_runs.RealCPURunTests` (1), and `test_extension_canonical_release`, which cannot be imported. The test database's user may not create databases: one test each in `test_experiment_lineage`, `test_extension_http`, `test_extension_retention`, `test_integrated_retention_restore`, `test_run_publication_recovery`. "CPU snapshot contains unsafe or unlisted directories": `test_recipe_process.CpuSnapshotContractTests` (3). The other 17 failures of the baseline were in six deleted files |
| Project suite | 585 before. After, with the new test: 586 |
| JavaScript | `node --check`: 54 scripts under `static/`, none fails. All 49 remaining `tests/test_*.cjs` pass |
| Browser, workspace | `browser_project_workspace.cjs`, `browser_project_workspace_actions.cjs` and `browser_project_workspace_still.cjs` pass on the fixture; the first and the last pass on the lab folder, whose `git status` is empty before and after. `browser_project_workspace.cjs` failed once, while two whole suites ran beside it (a link of the Overview tab not yet drawn in the dark theme), and passed twice after |
| Browser, catalog | Of the 62 checks the workflow runs, 49 ran and 45 pass. `browser_saved_searches.cjs` passes every assertion and then fails removing its temporary directory, the same on the unchanged code. `browser_instruction_responses.cjs`, `browser_combined_workbench.cjs` and `browser_preferences.cjs` need packages the workflow installs. Not run, for want of training, a GPU, numpy or generated fixtures: `candidate_package`, `model_development`, `one_fit_model_evidence`, `retained_analysis_actual`, `scientific_fields`, `workspace_image_run`, `workspace_audio_run`, `workspace_mesh_run`, `workspace_sequence_run`, `workspace_export_run`, `workspace_project`, `workspace_spatial`, `workspace_text` |
| Start-up | `python app.py --help` shows none of the four flags; each is "unrecognized arguments", exit status 2, as are `mcp_stdio.py`'s two. Catalog mode on an empty data directory answers `/` ("Dataset studio"); `--project-folder` on a copy of `examples/tiny-project/project` in a Git repository of its own answers `/` ("Map · Tuldok"); `--project-folder` with `--project-root` is still refused |
| Size | 143 files deleted, 47,099 lines: 37 modules (20,437), 72 Python test files (20,732), 18 JavaScript tests and helpers (1,943), 11 files under `static/` (3,264), one script (35), four documents (688). 2,450 lines cut from the 17 other files that changed (65 added). The capability check had 38 modules (20,854 lines), 10 static files and 74 test files (21,791 lines): six of those 74 stay (five use `project_cli`, one lost an assertion), and four tests of the old mode that import none of the modules go |

**Not verified.** The browser checks used Playwright's headless shell, not the Chrome the workflow installs. The catalog checks named above were not run. Nothing ran on GitHub.
