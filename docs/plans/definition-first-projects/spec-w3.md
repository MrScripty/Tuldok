# Implementation spec: the Map workspace, phase 3: acting from the page

This is phase 3 of [the Map workspace plan](workspace-plan.md); [spec-w1.md](spec-w1.md) and [spec-w2.md](spec-w2.md) are phases 1 and 2. Section 1 of [spec-m1-m2.md](spec-m1-m2.md) (rules for implementers) applies, with the import rule as amended by [spec-m7.md](spec-m7.md). The reference for how things look is still the mockup, `docs/plans/project-workspace-redesign/mockups/` (`b-map.html`, `shared/screens.js`: `inspectorPlanned`, `inspectorPlannedRun`, the `steps` list, the `form` and `actions` styles), and its brief.

**Done when:** on a copy of the tiny example, in a browser and with nothing typed in a terminal after Tuldok starts: a model is branched from the trained one, a setting of the branch is changed, it is kept, saved and its build planned and requested, the training runs on the GPU and its progress is seen on the page while it runs, and the new model appears on the map as built with a line from its parent; and a build an agent asked for is approved from the page and runs.

## 1. Decisions

- **Every control is one operation of the project.** After it answers, the page forgets what it can have changed and reads again. A refusal is shown where the control was pressed, in the server's words, with its problems listed under it. Nothing is retried on its own.
- **A control is drawn only for a session that may use it**, read from the signed-in identity's kind and scopes with the rules of `service._allowed`. Someone who may only inspect sees the page of phase 2.
- **Edits live in Tuldok until saved.** Keep stores an edit in the working copy as an unsaved edit; Save writes every unsaved edit to the project folder. The page writes nothing else to disk and never touches Git. The strip always says how many edits are unsaved.
- **No build is asked for without its plan on screen.** Request build is a button of the plan view, never of a row.
- **Costly or destructive controls take two presses in place:** the button becomes "Confirm" with what will happen in words, beside "Back". This applies to cancelling a build or a run, stopping what a run left behind, discarding an edit, removing a definition, disconnecting an environment and taking the files in a conflict. No `window.confirm`, `alert` or `prompt`.
- **A branch is a draft in the page until it is kept.** Tuldok stores only definitions that check, and a branch of an earlier model often does not check yet (its code is lost). The draft is drawn on the map from the moment it is made and survives a reload (`sessionStorage`, keyed by the project's id).
- **Not in this phase:** studies and trials; target metric and threshold; attempts; anything that changes code or Git; running a benchmark for one model from the Benchmarks tab; annotation and the viewers.

## 2. Additions to the core

Two operations of the `project_folder` profile and two additions to `map`.

**`draft_branch`**, for `inspect`, not a mutation. Arguments: `recipe` (a reference), `title` (1 to 200 characters), and optional `name`, `change` (one of the four kinds) and `description` (at most 4,000 characters). Result: `reference`, `text`, `parent`, `inlined`, `problems`. It stores nothing.

- `reference` is `recipes/<name>`. A given `name` must fit the format's name rule and be free (a removed definition's name is not free): otherwise `invalid`. Without `name` it is made from the title: lowercase, each run of characters outside `[a-z0-9]` becomes one `-`, trimmed of `-` at both ends and to 80 characters (`recipe` when nothing is left), then `-2`, `-3` and so on until it is free.
- `text` is a recipe written from the parent's document as it is in the working copy: `format`, `kind`, `title`, `description` when given, the parent's `model` and `group` when it has them, `change` (the argument, else the parent's), `derived_from` naming the parent, and the parent's `run` when it has one. Not carried over: `card`, `labels`, `earlier_work`, `compared_with`. It is JSON with the indentation of the parent's text (two spaces when the parent's has none) and ends with a newline.
- When the parent's `run` has `settings_file` and that file, read from the code root as it is on disk, is a JSON object of at most 256 KiB, the branch carries its content as `settings` in place of `settings_file`, and `inlined` is the file's path; otherwise `inlined` is null and `run` is carried as it is.
- `problems` is what `set_definition` would say of `text` at `reference`, errors and warnings, as a list of problems. A branch of a model without `run`, or whose code paths are missing, is returned with those errors for the caller to fix.
- A `recipe` that is no recipe of the project (or is removed) is refused `not-found`.

**`revert_definition`**, for `edit`, a mutation. Argument `reference`. Result `{reference, dropped}`. For a definition that has an unsaved edit or is marked removed: when the folder holds its file, the file's text takes the edit's place and the definition is neither unsaved nor removed, checked as `set_definition` checks (a file that no longer checks is refused `invalid` with its problems, nothing changed); when the folder holds no file for it, it is dropped as `remove_definition` drops one that was never saved, refused `in-use` while anything uses it, and `dropped` is true. A definition with neither an unsaved edit nor the removed mark is refused `nothing-to-revert`.

**`map`:** each model gains `unsaved` (whether its definition has an unsaved edit). A model's `trained_at` is its label, and without the label the time the run of its current product finished (null when it has no product or the product was adopted).

**Command line:** `branch FOLDER RECIPE --title TITLE [--name NAME] [--change KIND] [--description TEXT] [--keep] [--json]` prints the draft's reference, its problems and its text; with `--keep` it stores the text as an unsaved edit when it has no error. `revert FOLDER REFERENCE` reverts.

The contract document gains both operations, the `map` additions and the two commands.

## 3. The page

### 3.1 Builds (slice T21)

| Where | What |
| --- | --- |
| Strip | When definitions are unsaved or marked removed: their count and **Save** (`save`). A save refused `changed-on-disk` shows the files and **Read the project again** |
| Needs you | Each item keeps its sentence and gains its controls. Awaiting approval: **Approve**, **Decline**, and a link to the request on Train. Unsaved edits: **Save**, and each named definition opens it. An environment not ready: **Check again** (`check_environment`), and a link to it on Train. A last run that ended badly: a link to the run, and **Plan build** |
| Plan view (drawer) | From `plan`, for one or more targets or everything buildable: the steps in order with what each would do (build, built already, blocked and why), how many use the GPU, disk and time (stated, estimated or unknown), the notes, and the targets that are blocked. A checkbox "Run from the code as it is on disk; the product is marked scratch". **Request build** (`request_build`). For an agent credential the button reads "Ask the owner for this build" |
| Train: to build | Each model not built, out of date or failed has **Plan build**; the section has **Plan everything buildable** |
| Train: a build request | Opening one reads `build_request`: who asked and when, what it covers (targets, the commit, scratch or not, how many definitions), its state with the problem or the reason when it has one, and its runs as links. Awaiting approval: **Approve** (`approve_build`), **Decline** with a reason of at most 400 characters (`decline_build`). Awaiting approval, queued or running: **Cancel** (`cancel_build`) |
| Train: a run | A queued or running run has **Cancel run** (`cancel_run`). A run still marked running whose builder is gone has **Stop what it left running** (`stop_run`). A running run shows its progress hairline, its latest progress line and the last lines of its two logs, read on with the offsets `progress` returns while it runs |
| Train: an environment | **Check again**; for the owner a field for an interpreter's absolute path with **Connect** (`connect_environment`), and **Disconnect** on a connected one |
| A model's drawer (Map) | **Plan build** when the model is not built, out of date or failed |
| Conflict | When a read is refused `conflict`, the main area shows the server's sentence, the definitions named, and **Keep my edits** and **Take the files** (`resolve_conflict` with `keep` or `discard`); then everything is read again |

While a build request is queued or running the page asks again every two seconds, as in phase 2, and now also for the open run's progress and logs and for `map` when a run ends, so a model turns to built without a reload.

### 3.2 Editing and branching (slice T22)

**The editor** opens in the drawer from **Edit** on any definition the page shows: a model on the Map, a dataset on Data, and every definition from a new list on Overview (by kind: name, title, state, an unsaved mark). It has two views of one text:

- **Text**, for every kind: the definition's JSON in a monospace field.
- **Form**, for a recipe: title; short label (the label `short`, at most 16 characters); kind of change (the four kinds, or not set); group (the project's groups, or none); derived from (the parent's name, **Pick on the map**, after which the next model pressed on the map becomes the parent, and **Clear**); description, labelled "What this model changes"; and, when the recipe has `run`: environment (the project's environments), each input that comes from a dataset (the project's datasets, keeping a named output), the settings, and the resources `gpu`, `wall_hours` and `disk_gb`. Settings: when `run.settings` is an object, one field per top-level key whose value is a number, a text or true/false, and a line naming the keys that are edited in the text; when the recipe has `settings_file`, its path and a sentence that a branch carries its own copy.

The form writes the JSON with the indentation the text had, changing only the fields touched. What is typed stays in the page per definition until it is kept or discarded, so leaving the drawer loses nothing; a definition with typing not yet kept says so.

| Control | Does |
| --- | --- |
| **Keep** | `set_definition`. Problems are listed with where they are in the document; nothing is kept while there is an error |
| **Discard edit** | drops what was typed; on a definition with an unsaved edit, `revert_definition` |
| **Remove** | `remove_definition`; the refusal names what uses it |
| **Save** | `save`, as on the strip |

An unsaved definition carries an "unsaved" mark in the drawer's header, in its list row and on its map node.

**Branch from here**, in a model's drawer: a title (required), the kind of change (the parent's to begin with) and what the model changes. **Create** calls `draft_branch` and the page holds the answer as a draft:

- The draft is drawn on the map right after its parent, in its parent's lane, hollow and dashed, labelled "new", and is selected. In the list its chip reads "draft".
- Its drawer is the editor in the form view, opening with the draft's problems when it has them and, when settings were copied from a file, a line saying so.
- Below the form, the steps of the mockup's planned model with the real states: Kept, Saved, Build requested, Running, Built. The primary button is the next step: **Keep**, **Save**, **Plan build** (the plan view, with **Request build**), then **Open in Train**. **Discard** drops a draft, and on a kept one reverts it.
- Once kept it is a definition like any other: `map` returns it, not built and unsaved, and the page draws a model that has never been built hollow and dashed. A model without a date that names a parent is placed right after that parent (after the parent's earlier such children); the others stay where phase 2 put them.
- Train lists drafts first, under "Planned", with the models never built.

### 3.3 Rules for both slices

The rules of spec-w2 section 1 hold: no build step, no framework, no external reference, text through text nodes, both themes, the mockup's type, spacing and components (`btn`, `btn primary`, `btn ghost`, `form`, `actions`, `steps`, `radio`, `two`). A control that is waiting for its answer is disabled and says so. Keyboard: every control is reachable and operable, Escape leaves the two-press state and the pick-on-map state, and focus returns to what opened a view.

## 4. Checking

- **Unit tests** for section 2 in the project's test files, the operation count and the pinned contract digest updated the way spec-w1's were.
- **A browser check**, `tests/browser_project_workspace_actions.cjs`, beside the read-only one (which must still pass unchanged in what it asserts). It runs Tuldok on a copy of the fixture project committed to a Git repository of its own, with stand-in commands that train nothing; one of them takes about four seconds and prints progress lines. Signed in as the owner it: approves a build an agent asked for and sees the hairline partly filled while it runs, then the run succeeded; declines another with a reason and sees the reason; plans and requests a build and cancels it; branches a built model, changes a setting in the form, keeps, saves (the file is in the folder with `derived_from` and the changed setting), plans, requests, and sees the model built on the map with its line; edits an existing recipe in the form and discards the edit; saves a changed kind of change; types invalid JSON in the text view and sees the problem with nothing kept; sets a parent by picking on the map; makes a conflict (an unsaved edit and the same file changed on disk) and resolves it both ways; checks an environment again. It captures each new surface in light and dark and fails on any script error, failed request (other than the refusals it provokes), sideways overflow or control left disabled.
- **The acceptance run** of the "Done when" sentence is made by the orchestrating session on a copy of the tiny example with the machine's real interpreters and a throwaway database, driven in a headless browser, with screenshots.

## 5. Slices

| Slice | Files | Notes |
| --- | --- | --- |
| T20 core | `tuldok_project/operations.py`, `service.py`, `store.py`, `workspace.py`, `__main__.py`, their tests, the pinned digest, `docs/contracts/project-folder.md` | first; touches nothing under `static/` |
| T21 builds | `static/project-workspace/` (the controls of 3.1, the plan view, the conflict panel), asset rows in `app.py` for new files, `tests/browser_project_workspace_actions.cjs` | after T20 |
| T22 editing | `static/project-workspace/` (the editor, Branch from here, drafts on the map, the Overview list), the browser check extended | after T21 |
