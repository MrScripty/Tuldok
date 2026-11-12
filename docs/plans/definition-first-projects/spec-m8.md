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
