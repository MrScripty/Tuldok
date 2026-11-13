# Implementation spec: annotation in a project folder

This is phase 4 of [the data tools plan](data-tools-plan.md). It builds on [spec-d1.md](spec-d1.md) (records and their viewers). Section 1 of [spec-m1-m2.md](spec-m1-m2.md) (rules for implementers) applies, with the import rule as amended by [spec-m7.md](spec-m7.md); the page follows [spec-w4.md](spec-w4.md).

**Owner, 2026-11-13:** "Right now we just need the basic modality support for data generation and annotation. text, image, audio, 3D (point clouds, mesh). We dont have a specific need for the surrogate lab. This is more a setup so other projects can setup what they need to generate." And on Git: "there has to be enough info to understand what the project/models/itterations/etc is withought carrying unessisary data, binaries, easily calculate info."

**After this phase** a project can bring files on this machine into a dataset, a person (or an agent allowed to edit) can annotate its records from the page, the annotations are text in the Git folder, and a dataset with splits can be frozen from them and trained on. Nothing here calls Pumas: suggestions and generation are phase 5.

**Words.** A **record** is one item of a dataset (spec-d1). An **annotation** is what was recorded about one record under one task. A **task** is a definition saying what is recorded and on which dataset. A **term** is one entry of a task's vocabulary. The word "label" is not used for any of these: a definition's `labels` are its own key and value tags, as before.

## 1. The task: a new kind of definition

`annotations/<name>.json`, kind `annotation`:

| Field | |
| --- | --- |
| `format`, `kind`, `title` | as every definition |
| `description`, `card`, `labels` | as every definition; `card` is where the guide for annotators is written |
| `dataset` | required; a reference to a dataset. An edge of the graph, as a chart's benchmark is |
| `task` | required; one of the seven below |
| `vocabulary` | the terms: 1 to 500 different strings of 1 to 200 characters. Required for `class`, `tags`, `boxes`, `spans`, `segments`; not allowed for `review` and `text` |

| Task | An annotation's `value` | On records of kind |
| --- | --- | --- |
| `review` | null | any but `file` |
| `class` | one term | any but `file` |
| `tags` | a list of different terms, possibly empty | any but `file` |
| `text` | a string of at most 64 KiB: a caption, a transcript, a summary | any but `file` |
| `boxes` | a list of `{"term", "x", "y", "w", "h"}` in pixels of the image, inside it, `w` and `h` above zero | image |
| `spans` | a list of `{"term", "start", "end"}` in characters (code points) of the text, `start` below `end`, inside it | text |
| `segments` | a list of `{"term", "start", "end"}` in seconds, `start` below `end`, with an optional `"text"` | audio |

A task is never built: it has no `run` and no product. Planning a task plans its dataset, as planning a chart plans its benchmark.

## 2. The annotations: a file of lines

`annotations/<name>.jsonl`, beside the task's `.json` and only there (a `.jsonl` with no task of its name is a problem `check` reports). One JSON object per line, keys in this order:

| Key | |
| --- | --- |
| `record` | the record's id: 1 to 600 characters, no control characters. One line per record |
| `sha256` | the hash of the record's content when it was annotated, or null (section 3) |
| `state` | `draft`, `accepted`, `needs-work` or `rejected` |
| `value` | as the task says; may be null in any state but `accepted` (a `review` task's is always null) |
| `note` | optional; at most 4,000 characters |
| `by` | `owner`, or `agent:` and the credential's label cut to 80 characters. Never an id, a token or a scope |
| `at` | UTC, `YYYY-MM-DDTHH:MM:SSZ` |
| `from` | optional; an object of at most 2 KiB saying what suggested the value (phase 5 fills it). Kept as it is |

Lines are sorted by `record`, bytewise in UTF-8; each is written with `ensure_ascii` false, separators `,` and `:`, and ends with a newline. The file is at most 64 MiB. A record with no line is not annotated. A file with no line left is deleted on save.

`check` reads every line: a line that is not such an object, a duplicate record, lines out of order, a value its task does not allow, a term not in the vocabulary. Each is a problem with its line number (the first 20 per file, then a count). A term removed from the vocabulary while annotations use it is a warning naming how many do.

Example lines, one per task:

```
{"record":"a1","sha256":"9f…","state":"rejected","value":null,"note":"blurry","by":"owner","at":"2026-11-13T10:02:11Z"}
{"record":"a2","sha256":"…","state":"accepted","value":"cat","by":"owner","at":"…"}
{"record":"a3","sha256":"…","state":"accepted","value":["indoor","night"],"by":"owner","at":"…"}
{"record":"a4","sha256":"…","state":"draft","value":"a dog on a sofa","by":"agent:helper","at":"…"}
{"record":"a5","sha256":"…","state":"accepted","value":[{"term":"cat","x":10,"y":4,"w":80,"h":60}],"by":"owner","at":"…"}
{"record":"a6","sha256":"…","state":"accepted","value":[{"term":"PER","start":0,"end":5}],"by":"owner","at":"…"}
{"record":"a7","sha256":"…","state":"accepted","value":[{"term":"speech","start":1.25,"end":3.5,"text":"hello"}],"by":"owner","at":"…"}
```

## 3. Tying an annotation to what it describes

An annotation belongs to a record's content, so that it survives the dataset being built again and is noticed when the content differs.

- **The hash** is SHA-256 of the record's file, of an archive member's bytes once decompressed, or of the UTF-8 of an inline `text`. A record list may carry it (`sha256` joins the keys of `records.jsonl` that spec-d1 knows); `import` and `freeze` write it. Otherwise Tuldok computes it when the record is first annotated and keeps it per run and record. A record over 1 GiB is not hashed: its annotations carry null and are tied by id alone.
- **Stale.** An annotation is stale when the dataset's current product has no record of its id, or has one whose hash differs. Stale is computed, never stored. Stale annotations are kept, counted, shown, and never dropped by Tuldok; a person removes or redoes them.
- Only the records that have annotations are ever hashed to find the stale ones, never a whole product.

## 4. The working copy

Annotations are edited in the database and written by Save, as definitions are.

- **Kept until Save.** `set_annotation` changes rows and marks them unsaved. `status` gains `annotations_unsaved` (per task, how many records) and `annotations_changed` (files changed on disk since the last import); it counts flagged rows and never renders a file. `save` writes each task's file that has unsaved rows, whole, by a temporary file and a rename, and gains `annotations_written` and `annotations_deleted`; it refuses `changed-on-disk` as it does for definitions.
- **A file changed on disk** (a pull, a hand edit) is imported on the next operation. Where it changes a record that also has an unsaved edit here, the project does not open: the refusal is `conflict` and names the file, and `resolve_conflict` keeps the edits here or takes the file, as for definitions. Size and time are compared before a file is hashed.
- **Revert.** `revert_annotations` puts back the saved line of the named records, or of every record of the task.
- **A task with annotations cannot be removed** by `remove_definition`; the refusal says how many there are.
- Every mutation writes one activity row (the task and how many records), as other mutations do.

## 5. Operations

| Operation | Who | Arguments | Result |
| --- | --- | --- | --- |
| `annotation_tasks` | inspect | none | `tasks`: each with `task`, `title`, `dataset`, `type`, `vocabulary`, `run` (the dataset's current product, or null), `records`, `counts` (`unannotated`, `draft`, `accepted`, `needs-work`, `rejected`, `stale`, `invalid`), `unsaved` |
| `annotated_records` | inspect | `task`; `state` (one of the counts' names, or absent for all); `kind`; `offset`; `limit` (at most 200) | `records` (as spec-d1's `records`, each with `annotation`: null or `state`, `value`, `note`, `by`, `at`, `stale`, `unsaved`), `total`, `counts` |
| `annotation` | inspect | `task`, `record` | `task`, `record`, `annotation` (the line as it now is, or null), `saved` (the line in the file, or null), `unsaved`, `stale`, `sha256` |
| `set_annotation` | edit, changes | `task`; `items`: at most 200 of `{record, state, value, note}` or `{record, remove: true}`; `from` (optional, applied to every item) | `task`, `set`, `removed`, `unsaved` |
| `revert_annotations` | edit, changes | `task`; `records` (optional) | `task`, `reverted` |

`set_annotation` checks every item against the task, the vocabulary and the record's kind before changing anything; one bad item refuses the call, naming it. It sets `by` from the caller and `at` from the clock. An agent allowed to edit annotates through the same operation, and its lines say `agent:` and its label.

The reads that look into a product are answered outside the service's lock, as spec-d1's are.

## 6. Steps Tuldok provides

A dataset's `run` names either a `command`, as now, or a `step`: one of `import` and `freeze` (phase 5 adds `generate`). A `step` excludes `command` and `environment`; its outputs are fixed and are not declared. It is planned, requested, approved, run, cancelled and recorded like any build, from a commit as builds are, and shows as `tuldok <step>` in a plan.

Tuldok runs `python -m tuldok_project.steps <step>` with its own interpreter, its own code first on the path and the snapshot's code not on it (`PYTHONSAFEPATH`), the run's settings and output directory as arguments. A step reads files and writes its output; it never opens the database. It prints progress in the existing form.

**`import`.** Settings:

| | |
| --- | --- |
| `source` | a directory: relative to the code root (it is then read from the commit, and the dataset can be built anywhere), or absolute (this machine only; `check` warns) |
| `pattern` | which files, in spec-d1's pattern form; default `**/*` |
| `kind` | the kind of every file; default by extension |
| `rights` | required: a sentence on what may be done with the files |
| `lines` | for text: true makes each non-empty line of each file a record of its own. A line of a `.jsonl` file that is an object with a string `text` gives that string; any other line gives itself |

Output: the files under `files/`, hard-linked (copied across file systems), and `records.jsonl` with `id`, `kind`, `path` or `text`, `sha256`, `bytes`, `rights` and `origin` (the file's path under the source, and its line). Ids are made from the path: `/` becomes `__`, any other character outside `A-Z a-z 0-9 . _ -` becomes `_`, and a number is added to one that repeats. Symbolic links leaving the source are skipped and counted.

**`freeze`.** A dataset whose `run` has `step: "freeze"`, `inputs: {"records": <a dataset>}`, `annotations` (one or more tasks on that dataset: new edges of the graph) and settings:

| | |
| --- | --- |
| `seed` | an integer |
| `shares` | the splits and their relative sizes, for example `{"train": 8, "validation": 1, "test": 1}` |
| `include` | which states of the first task's annotations take a record in; default `["accepted"]` |

It reads the tasks' line files from the commit it is built from (annotations not saved and committed are not frozen, as code is not), takes the records of the input's product that the first task includes and that are not stale, orders them by the SHA-256 of the seed and the record's hash, and cuts that order by the shares. Output: the included records' files linked under `files/` and `records.jsonl` with each record's `split` and `annotations` (per task: `state` and `value`), which join the keys spec-d1 knows. Stale and excluded records are counted in the run's progress and log.

A frozen dataset is out of date when the line file of any of its tasks differs from the one its run read, as it is when its definition or its input changed.

## 7. The page

**The strip** counts annotations with definitions: "3 definitions, 41 annotations unsaved". Save writes both.

**A tab, Annotate,** between Data and Train, laid out as the mockup's (`docs/plans/project-workspace-redesign/mockups/shared/screens.js`, lines 263 to 325):

- **Bar:** the task (a select of the project's tasks, with "New task"), a filter by state (All, To do, Accepted, Needs work, Rejected, Stale; "To do" is unannotated and draft together), progress ("412 of 1,000 decided"), and the keys.
- **Left:** the records as a paged grid of 48, each with a dot for its state; a record that is stale or unsaved is marked.
- **Middle:** the record in its viewer (spec-d1's), with previous and next.
- **Right:** the form for the task, a note, and the decision.

| Task | The form |
| --- | --- |
| `review` | the decision alone |
| `class` | the terms as radio buttons, the first nine on the keys 1 to 9 |
| `tags` | the terms as checkboxes, the same keys |
| `text` | a text area |
| `boxes` | drag on the image to draw a box, choose its term; boxes are selected, moved, resized by their corners and deleted; they are listed beside the image |
| `spans` | select text to mark a span, choose its term; spans are shown in the text and listed |
| `segments` | drag on the waveform to mark a stretch, choose its term, optionally type what is said; a stretch can be played |

- **The decision:** Accept, Needs work, Reject. "Keep and next" (Enter) keeps the form's value with the chosen decision and moves on; without a decision it is kept as a draft. "Skip" moves on and keeps nothing. Left and right arrows move without keeping. Keys are ignored while typing in a field.
- **New task:** a form with title, dataset, task and vocabulary, which keeps a new definition as an unsaved edit, as the editor does.
- **Stale:** the form shows the annotation with what changed (the record is gone, or its content differs), and "Still right" sets its hash to the record's.
- A task whose dataset has no product says so and offers to plan the dataset.

**The Data tab** gains two forms that write a dataset definition as an unsaved edit: **Import** (name, source, pattern, kind, rights, lines) and **Freeze** (name, the dataset, its tasks, seed, shares, which states). Building them is the existing plan and request.

Canvas 2D, no library, light and dark, every control reachable by keyboard; nothing is redrawn by a timer or a return to the window when nothing changed, and what is typed in the form is never lost to a reading.

## 8. Slices

| | Slice | Mainly |
| --- | --- | --- |
| D4a | The kind and its schema; the line file read, checked and written; `check`, the folder reader, the graph and the plan know both | `documents.py`, `schemas/`, `folder.py`, `check.py`, `graph.py`, `plan.py`, a new `annotations.py`, `operations.KINDS`, the page's kind lists |
| D4b | The working copy (tables, import, status, save, conflict, revert, the hash cache) and the five operations | `store.py`, a new `annotation_rows.py`, `service.py`, `operations.py`, `inside.py` (the `sha256` key) |
| D4c | `run.step`; `import` and `freeze`; out of date by the line files | `schemas/` (`$defs/run`), `check.py`, `plan.py`, `builds.py`, a new `steps.py`, `inside.py` (the `annotations` key) |
| D4d | The Annotate tab, the strip, the two forms of the Data tab | `static/project-workspace/annotate.js`, `tabs.js`, `actions.js`, `app.js`, `adapter.js`, `base.css`, `app.py` (the asset list) |

D4a first; D4b and D4c after it; D4d last. `docs/contracts/project-folder.md` is brought up to date by each slice for what it adds.

## 9. Tests

- **D4a,** `tests/test_tuldok_project_annotations.py`: a task of each kind checks; each rule of sections 1 and 2 broken once gives its problem with its line; a file written from rows equals the file it was read from, byte for byte; order and escaping; a `.jsonl` without its task; a fresh open of a folder with tasks lists them and their edge; planning a task plans its dataset.
- **D4b,** `tests/test_tuldok_project_annotation_rows.py`: set, status counts, save writes the file and clears the count; a second open reads the same; revert; a file changed on disk with and without an unsaved edit on the same record (import, and conflict resolved both ways); stale by a missing record and by different content; the hash is computed once per run and record and not for a record over the bound (lowered for the test); every refusal of `set_annotation`; an agent's line says `agent:` and its label and nothing else of it; removing a task with annotations is refused; 100,000 annotations set in batches, counted, saved and reopened within a time the test states.
- **D4c,** `tests/test_tuldok_project_steps.py`: `import` of a tree holding each kind, by pattern, with `lines`, from a relative and an absolute source, ids made unique, links out skipped; the product is read by spec-d1's operations with the hashes given; `freeze` splits by the shares, the same for the same seed and different for another, includes by state, leaves out stale ones, carries the annotations; it goes out of date when a line file changes and not when another task's does; a step runs with no environment and cannot import the snapshot's code.
- **D4d,** `tests/browser_project_workspace_annotate.cjs`, on a fixture with a record of each kind imported: a task of each kind is made from the page and one record annotated with it, by pointer for boxes, spans and segments and by keys for class and tags; the strip's count; Save, then the file on disk has the lines; a reload shows them; a filter by state; a stale record marked and put right; nothing rebuilt on a return to the window while the form holds typed text, and the text still there.
- **The example.** `examples/tiny-project` gains a few small files of each kind and an `import` of them from a relative source, a `class` task with annotations, and a `freeze`. The plan's test for this phase is run on it: import, annotate from the page, save, a fresh clone shows the same annotations, the frozen dataset builds with its splits.

## 10. Out of scope

Suggestions from a model and generation (phase 5); the history of one annotation (Git has it); several people's annotations of one record side by side and agreement between them; export to COCO and other formats; annotating arrays beyond the tasks that fit any kind; polygons, masks, keypoints and 3D boxes; importing from a URL.

## As built

### D4a, the task and the file of lines

What differs from the text above, and what was chosen where it was silent.

- **A term that is not in the vocabulary is a warning in `check` and an error in an edit.** Section 2 lists it among a line's problems and also calls a removed term a warning; in a folder the two cannot be told apart. `check` warns once per term, with how many annotations use it and up to 20 line numbers. `annotations.validate`, which edits go through, refuses it.
- **Form and content are separate.** A line whose content is right but which is not written exactly as Tuldok writes it (key order, spacing, escapes, the form of a number), a blank line, a missing final newline and an empty file are warnings. A wrong value, a duplicate record and lines out of order are errors. A file with no problem at all is written back byte for byte.
- **The cap of 20 problems per file** counts errors and warnings together; one more problem counts the rest, and is an error if any of the rest is.
- **Bounds the text did not give:** at most 1,000 boxes, spans or segments in one annotation; a segment's `text` at most 64 KiB; `note` and `from` may be absent but not null; `agent:` is followed by 1 to 80 characters; a term holds no control character. The 64 KiB of a `text` value are UTF-8 bytes; the 2 KiB of `from` are of its compact form.
- **Inside an item** the keys are written in the order `term`, `x`, `y`, `w`, `h`, `start`, `end`, `text`.
- **A line file whose task has errors** is not checked and says so, as a results file whose benchmark has errors does.
- **The edge** from a task to its dataset has the role `dataset`. Planning a task plans its dataset and says so in the plan's notes; a task is never a step.
- **The store,** for now, neither lists nor refuses a task's line file: its lines reach the database in D4b. A line file without its task sends the open to `check`, which refuses it. Removing a task today would leave its line file behind; D4b refuses that removal.
- **The fixture project of the tests** gained a task and its lines, since a test requires a definition of every kind; three tests that count definitions moved from 12 to 13.
- **Checked in review** with annotations generated at random: 400 of each task, with ids holding `/`, `!`, non-Latin letters and upper case, values holding quotes, backslashes, line separators and emoji, written and read back equal, byte for byte and in order; 3,000 corrupted files read without an error escaping; 100,000 lines written in 0.2 s and read and checked in 1.4 s (16 MiB).
- **Tests:** `tests/test_tuldok_project_annotations.py`, 22; project suite 632; agent interface 43 (4 skipped). The catalog profile's digest is unchanged.
- **Not verified:** the editor's list of kinds in a browser.

### D4b, the working copy and the operations

What differs from sections 3 to 5, and what was chosen where they were silent.

- **A file's size and time are trusted only once its time is old** (found in review). A line file written a moment ago can be written again within the same tick of the clock, to the same size, and by size and time it would look untouched: the edit would not be imported, and the next Save would write over it. A file whose time is less than two seconds old when it is recorded is recorded as unsettled, and is read and compared by content on every operation until it is seen settled, as Git does for the same case. A test writes such an edit and fails without the rule.
- **A removed annotation** is a row with no state until Save, which keeps its saved line so that the file can be rewritten or deleted.
- **`from` is kept as text** (`json`, not `jsonb`), since the database's own form reorders keys and `from` is kept as it is. `value` is `jsonb`: a number of 1e16 or more written as a float in a file becomes a whole number the next time that task is saved.
- **Invalid is kept, not computed on every count.** Each row holds a digest of the task's type and vocabulary it was last judged against, and the verdict; a count judges again only the rows of a task that changed. Invalid judges the value alone, not the record's kind.
- **A task whose dataset has no product:** `stale` and `unannotated` are 0, a record's `stale` is null, setting an annotation is refused `not-found`, and removing one still works.
- **A task deleted on disk while it has unsaved annotations** is a `conflict` that only `discard` resolves. A line file that is gone never conflicts: unsaved rows stay, with no saved line.
- **U+0000** in a line or an item is refused `invalid`: PostgreSQL cannot store it.
- **Removing a task** that has annotations is refused `in-use` with their number. With none left, Save deletes the task and its line file together.
- **`set_annotation` works in two stages:** it finds and hashes the records outside the service's lock, then checks and stores under it; when the task or the product's run changed in between, it is refused `busy`.
- **Activity rows** carry "N set, M removed" or "N reverted".
- **A record's hash** is also computed, and kept, when `annotation` reads a record that has no annotation.
- **An agent with an empty label** is written `agent:agent`.
- **Names.** Every operation answers the task as `annotations/<name>` and takes a bare name or that reference; `status` and `save` name files as `annotations/<name>.jsonl`. `annotated_records` also answers `task`, `run` and, for each record, `sha256` and `in_product`; annotations whose record is not in the product come last, with `in_product` false and no kind. "Still right" on a stale annotation is setting it again.
- **Measured with 100,000 annotations** (the test's bound in brackets): setting them in 500 calls of 200, 28 to 36 s, about 66 ms a call (120); counting them, 0.2 s (2); `status`, 0.03 s; Save, 2 s (10); opening again, 0.02 s (2); importing the file into an empty database, 5 s (30).
- **Tests:** `tests/test_tuldok_project_annotation_rows.py`, 22; the project suite and the agent interface are in the ledger. The catalog profile's digest is unchanged.
- **Not verified:** hashes kept for runs that are later forgotten are never pruned; a sound's length is read from WAV files only, so a segment in another format is not checked against the sound's end; the command line has no annotation commands.
